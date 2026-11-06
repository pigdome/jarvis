"""Rewrite mysqldump output: CREATE TABLE column maps and extended INSERTs.

Only statements of tables that carry rules (or are truncated) are parsed; every
other line is returned untouched so unrelated bytes stay byte-for-byte equal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .detect import looks_like_pii
from .errors import DumpFormatError
from .profile import Profile, Rule, TableRules
from .report import Report
from .strategies import Faker

_CREATE_RE = re.compile(
    rb"^CREATE TABLE\s+(?:IF NOT EXISTS\s+)?`([^`]+)`", re.IGNORECASE
)
_ANY_DATA_RE = re.compile(rb"^\s*(?:INSERT|REPLACE)\b", re.IGNORECASE)
_INSERT_RE = re.compile(
    rb"^\s*INSERT\s+INTO\s+`([^`]+)`(?:\s*\(([^)]*)\))?\s+VALUES\b", re.IGNORECASE
)
_OTHER_INSERT_RE = re.compile(
    rb"^\s*(?:INSERT\s+(?:IGNORE|DELAYED|LOW_PRIORITY|HIGH_PRIORITY)\s+(?:INTO\s+)?"
    rb"|REPLACE\s+(?:INTO\s+)?)`([^`]+)`",
    re.IGNORECASE,
)
_COLUMN_RE = re.compile(
    rb"(?:^|,)\s*`([^`]+)`\s+([A-Za-z]+)(?:\s*\(\s*(\d+)\s*(?:,\s*\d+\s*)?\))?",
    re.MULTILINE,
)
_CHAR_TYPES = frozenset({"char", "varchar"})

_QUOTE = 0x27
_BACKSLASH = 0x5C
_COMMA = 0x2C
_OPEN = 0x28
_CLOSE = 0x29
_SEMICOLON = 0x3B

_ESCAPES = {
    0x30: b"\x00",  # \0
    0x62: b"\x08",  # \b
    0x6E: b"\x0A",  # \n
    0x72: b"\x0D",  # \r
    0x74: b"\x09",  # \t
    0x5A: b"\x1A",  # \Z
    0x5C: b"\\",
    0x27: b"'",
    0x22: b'"',
}


@dataclass(slots=True)
class _Cell:
    start: int
    end: int
    kind: str
    value: bytes


def _skip_space(data: bytes, index: int) -> int:
    end = len(data)
    while index < end and data[index] in b" \t\r\n":
        index += 1
    return index


def _scan_string(data: bytes, index: int) -> tuple[int, bytes]:
    """Decode a MySQL quoted string starting at ``index`` (the opening quote)."""
    end = len(data)
    index += 1
    out = bytearray()
    while index < end:
        char = data[index]
        if char == _BACKSLASH:
            if index + 1 >= end:
                raise DumpFormatError("unterminated escape in INSERT string")
            escaped = data[index + 1]
            mapped = _ESCAPES.get(escaped)
            if mapped is None:
                out.append(escaped)
            else:
                out += mapped
            index += 2
            continue
        if char == _QUOTE:
            if index + 1 < end and data[index + 1] == _QUOTE:
                out.append(_QUOTE)
                index += 2
                continue
            return index + 1, bytes(out)
        out.append(char)
        index += 1
    raise DumpFormatError("unterminated string in INSERT statement")


def _parse_cell(data: bytes, index: int) -> tuple[_Cell, int]:
    end = len(data)
    if data[index] == _QUOTE:
        stop, value = _scan_string(data, index)
        return _Cell(index, stop, "string", value), stop

    if data[index : index + 8].lower() == b"_binary ":
        quote = _skip_space(data, index + 8)
        if data[quote : quote + 1] == b"'":
            stop, value = _scan_string(data, quote)
            return _Cell(index, stop, "binary", value), stop

    if data[index : index + 2].lower() == b"0x":
        stop = index + 2
        while stop < end and data[stop] in b"0123456789abcdefABCDEF":
            stop += 1
        return _Cell(index, stop, "hex", data[index:stop]), stop

    if data[index : index + 4].upper() == b"NULL":
        after = data[index + 4 : index + 5]
        if after == b"" or after in b" \t\r\n,);":
            return _Cell(index, index + 4, "null", b""), index + 4

    stop = index
    while stop < end and data[stop] not in b",)":
        stop += 1
    raw = data[index:stop].strip()
    if not raw:
        raise DumpFormatError("empty value in INSERT statement")
    return _Cell(index, stop, "bare", raw), stop


def _iter_rows(data: bytes):
    """Yield one list of cells per row of an extended INSERT body."""
    end = len(data)
    index = 0
    while True:
        while index < end and data[index] in b" \t\r\n,":
            index += 1
        if index >= end or data[index] == _SEMICOLON:
            return
        if data[index] != _OPEN:
            raise DumpFormatError("expected '(' in INSERT statement")
        index += 1
        cells: list[_Cell] = []
        while True:
            index = _skip_space(data, index)
            if index >= end:
                raise DumpFormatError("unterminated row in INSERT statement")
            cell, index = _parse_cell(data, index)
            cells.append(cell)
            index = _skip_space(data, index)
            if index >= end:
                raise DumpFormatError("unterminated row in INSERT statement")
            if data[index] == _COMMA:
                index += 1
                continue
            if data[index] == _CLOSE:
                index += 1
                break
            raise DumpFormatError(
                f"unexpected byte {data[index:index + 1]!r} in INSERT statement"
            )
        yield cells


def _count_rows(data: bytes) -> int:
    """Count top-level tuples without decoding any cell (used for truncate)."""
    count = 0
    depth = 0
    in_string = False
    index = 0
    end = len(data)
    while index < end:
        char = data[index]
        if in_string:
            if char == _BACKSLASH:
                index += 2
                continue
            if char == _QUOTE:
                in_string = False
            index += 1
            continue
        if char == _QUOTE:
            in_string = True
        elif char == _OPEN:
            if depth == 0:
                count += 1
            depth += 1
        elif char == _CLOSE and depth:
            depth -= 1
        index += 1
    return count


def _escape_mysql(value: str) -> bytes:
    out = bytearray()
    for char in value:
        if char == "\\":
            out += b"\\\\"
        elif char == "'":
            out += b"\\'"
        elif char == "\n":
            out += b"\\n"
        elif char == "\r":
            out += b"\\r"
        elif char == "\0":
            out += b"\\0"
        elif char == "\x1a":
            out += b"\\Z"
        else:
            out += char.encode("utf-8")
    return bytes(out)


def _decode_value(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        # Binary payload: still replace it, the original text is unusable.
        return "x"


def _conditions_match(
    conditions: dict[str, frozenset[str]],
    cells: list[_Cell],
    column_index: dict[str, int],
    *,
    missing_matches: bool = True,
) -> bool:
    """``missing_matches``: result for a column absent from this dump.

    True for ``when`` (row still anonymized), False for ``unless`` (row is
    not skipped) — both fail safe toward anonymizing.
    """
    for column, allowed in conditions.items():
        position = column_index.get(column.lower())
        if position is None:
            if missing_matches:
                continue
            return False
        cell = cells[position]
        if cell.kind == "null":
            return False
        if _decode_value(cell.value) not in allowed:
            return False
    return True


class MysqlRewriter:
    """Rewrite mysqldump extended INSERTs according to a profile."""

    def __init__(self, profile: Profile, faker: Faker, report: Report) -> None:
        self.profile = profile
        self.faker = faker
        self.report = report

        self._tables: dict[str, TableRules] = {
            name.lower(): rules for name, rules in profile.tables.items()
        }
        self._truncate = {name.lower() for name in profile.truncate}
        self._rule_maps: dict[str, dict[str, Rule]] = {
            name.lower(): {column.lower(): rule for column, rule in rules.columns.items()}
            for name, rules in profile.tables.items()
        }

        self._columns: dict[str, list[str]] = {}
        self._max_len: dict[str, list[int | None]] = {}
        self._column_index: dict[str, dict[str, int]] = {}

        self._create_table: str | None = None
        self._create_lines: list[bytes] = []
        self._pending: list[bytes] | None = None
        self._pending_table: str | None = None
        self._pending_drop = False
        self._saw_create = False
        self._saw_insert = False

    # -- stream -------------------------------------------------------------

    def feed(self, line: bytes) -> bytes | None:
        """Return the bytes to emit for ``line``, or None to drop them."""
        if self._pending is not None:
            self._pending.append(line)
            if not self._statement_complete(line):
                return None
            return self._flush_pending()

        if self._create_table is not None:
            if _ANY_DATA_RE.match(line) or _CREATE_RE.match(line):
                raise DumpFormatError(
                    f"CREATE TABLE `{self._create_table}` is not terminated"
                )
            self._create_lines.append(line)
            if self._create_complete(line):
                self._finish_create()
            return line

        create = _CREATE_RE.match(line)
        if create is not None:
            self._saw_create = True
            self._create_table = create.group(1).decode("utf-8", "surrogateescape")
            self._create_lines = [line]
            if self._create_complete(line):
                self._finish_create()
            return line

        other = _OTHER_INSERT_RE.match(line)
        if other is not None:
            table = other.group(1).decode("utf-8", "surrogateescape").lower()
            if table in self._tables or table in self._truncate:
                raise DumpFormatError(
                    f"unsupported statement for `{table}`: "
                    + line[:40].decode("utf-8", "replace")
                )
            return line

        if _ANY_DATA_RE.match(line):
            self._saw_insert = True
            if _INSERT_RE.match(line) is None:
                raise DumpFormatError(
                    "cannot parse INSERT statement (table name must be "
                    "`quoted` as mysqldump writes it)"
                )
            self._start_insert(line)
            if self._pending is not None:
                if self._statement_complete(line):
                    return self._flush_pending()
                return None
            return line

        return line

    def _flush_pending(self) -> bytes | None:
        pending = self._pending or []
        table = self._pending_table or ""
        drop = self._pending_drop
        self._pending = None
        self._pending_table = None
        self._pending_drop = False

        statement = b"".join(pending)
        if drop:
            rows = _count_rows(statement)
            stats = self.report.stats(table)
            stats.rows += rows
            stats.truncated_rows += rows
            return None
        return self._rewrite_statement(table, statement)

    def finish(self) -> None:
        """Reject a dump that was cut mid-statement or has no MySQL statements."""
        if self._pending is not None:
            raise DumpFormatError("unterminated INSERT statement at end of dump")
        if self._create_table is not None:
            raise DumpFormatError(
                f"CREATE TABLE `{self._create_table}` is not terminated at end of dump"
            )
        if not self._saw_create and not self._saw_insert:
            raise DumpFormatError(
                "no MySQL statements found (expected CREATE TABLE and INSERT INTO)"
            )
        # A ruled table that never appeared may be a typo in the profile.
        for table in self._tables:
            if table not in self._columns:
                self.report.missing_tables.add(table)

    # -- statement detection ------------------------------------------------

    @staticmethod
    def _statement_complete(line: bytes) -> bool:
        return line.rstrip().endswith(b";")

    @staticmethod
    def _create_complete(line: bytes) -> bool:
        stripped = line.lstrip()
        return (
            stripped.startswith(b")")
            or b") ENGINE" in line.upper()
            or line.rstrip().endswith(b";")
        )

    def _start_insert(self, line: bytes) -> None:
        match = _INSERT_RE.match(line)
        if match is None:
            return
        table = match.group(1).decode("utf-8", "surrogateescape")
        lower = table.lower()
        if lower in self._truncate:
            self._pending = [line]
            self._pending_table = lower
            self._pending_drop = True
            return
        rules = self._tables.get(lower)
        if rules is None:
            return
        if match.group(2) is not None:
            raise DumpFormatError(
                f"INSERT INTO `{table}` with a column list is not supported"
            )
        if lower not in self._columns:
            raise DumpFormatError(
                f"INSERT INTO `{table}` came before its CREATE TABLE"
            )
        self._pending = [line]
        self._pending_table = lower
        self._pending_drop = False

    # -- CREATE TABLE -------------------------------------------------------

    def _finish_create(self) -> None:
        table = self._create_table or ""
        text = b"".join(self._create_lines)
        self._create_table = None
        self._create_lines = []

        lower = table.lower()
        match = _CREATE_RE.match(text)
        open_paren = text.find(b"(", match.end()) if match else -1
        if open_paren == -1:
            raise DumpFormatError(f"cannot parse CREATE TABLE `{table}`")
        engine = text.upper().find(b") ENGINE", open_paren)
        close = engine if engine != -1 else text.rfind(b")")
        if close <= open_paren:
            raise DumpFormatError(f"cannot parse CREATE TABLE `{table}`")
        body = text[open_paren + 1 : close]

        names: list[str] = []
        widths: list[int | None] = []
        for column in _COLUMN_RE.finditer(body):
            name = column.group(1).decode("utf-8", "surrogateescape")
            kind = column.group(2).decode("ascii").lower()
            size = column.group(3)
            names.append(name)
            widths.append(int(size) if size is not None and kind in _CHAR_TYPES else None)

        self._columns[lower] = names
        self._max_len[lower] = widths
        self._column_index[lower] = {
            name.lower(): position for position, name in enumerate(names)
        }

        truncated = lower in self._truncate
        rules = self._tables.get(lower)
        if truncated:
            return
        rule_map = self._rule_maps.get(lower, {})
        if rules is not None:
            dumped = {name.lower() for name in names}
            for column in rules.columns:
                if column.lower() not in dumped:
                    self.report.missing_columns.add((lower, column))
        for name in names:
            if name.lower() in rule_map:
                continue
            if looks_like_pii(name):
                self.report.suspicious_columns.add((lower, name))

    # -- INSERT rewriting ---------------------------------------------------

    def _rewrite_statement(self, table: str, text: bytes) -> bytes:
        match = _INSERT_RE.match(text)
        if match is None:
            raise DumpFormatError(f"cannot parse INSERT INTO `{table}`")
        if match.group(2) is not None:
            raise DumpFormatError(
                f"INSERT INTO `{table}` with a column list is not supported"
            )

        names = self._columns[table]
        widths = self._max_len[table]
        column_index = self._column_index[table]
        rules = self._tables[table]
        rule_map = self._rule_maps[table]

        body_start = match.end()
        parts: list[bytes] = []
        cursor = 0
        stats = self.report.stats(table)

        for cells in _iter_rows(text[body_start:]):
            if len(cells) != len(names):
                raise DumpFormatError(
                    f"`{table}` INSERT has {len(cells)} values but the table has"
                    f" {len(names)} columns"
                )
            stats.rows += 1

            if rules.when and not _conditions_match(rules.when, cells, column_index):
                continue
            if any(
                allowed
                and _conditions_match(
                    {column: allowed}, cells, column_index, missing_matches=False
                )
                for column, allowed in rules.unless.items()
            ):
                continue

            for position, cell in enumerate(cells):
                rule = rule_map.get(names[position].lower())
                if rule is None or cell.kind == "null" or cell.value == b"":
                    continue
                value = self.faker.fake(
                    rule,
                    _decode_value(cell.value),
                    key=f"{table}.{names[position]}",
                    max_len=widths[position],
                )
                rendered = b"NULL" if value is None else b"'" + _escape_mysql(value) + b"'"
                parts.append(text[cursor : body_start + cell.start])
                parts.append(rendered)
                cursor = body_start + cell.end
                stats.cells += 1

        parts.append(text[cursor:])
        return b"".join(parts)
