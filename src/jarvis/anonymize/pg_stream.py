"""Rewrite pg_dump plain output: CREATE TABLE widths and COPY blocks.

Only the data of tables that carry rules (or are truncated) is parsed; every
other line is returned untouched so unrelated bytes stay byte-for-byte equal.
"""

from __future__ import annotations

import re

from .detect import looks_like_pii
from .errors import DumpFormatError
from .profile import Profile, Rule, TableRules
from .report import Report
from .strategies import Faker

_IDENT = rb'"(?:[^"]|"")*"|[A-Za-z_][A-Za-z0-9_$]*'
_QUALIFIED = rb"(?:" + _IDENT + rb")(?:\s*\.\s*(?:" + _IDENT + rb"))?"

_CREATE_RE = re.compile(
    rb"^\s*CREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(" + _QUALIFIED + rb")\s*\(",
    re.IGNORECASE,
)
_COPY_RE = re.compile(
    rb"^\s*COPY\s+(" + _QUALIFIED + rb")\s*(?:\((.*)\))?\s+FROM\s+stdin\s*;\s*$",
    re.IGNORECASE,
)
_ANY_COPY_RE = re.compile(
    rb"^\s*COPY\s+(" + _QUALIFIED + rb")(?=[\s(;]|$)", re.IGNORECASE
)
_INSERT_RE = re.compile(
    rb"^\s*INSERT\s+INTO\s+(" + _QUALIFIED + rb")(?=[\s(;]|$)", re.IGNORECASE
)
_RESTRICT_RE = re.compile(rb"^\\restrict\s+(\S+)")

_IDENT_RE = re.compile(_IDENT)
_COLUMN_DEF_RE = re.compile(
    rb'^\s*(?:"((?:[^"]|"")*)"|([A-Za-z_][A-Za-z0-9_$]*))\s+(.+?)\s*,?\s*$'
)
_WIDTH_RE = re.compile(
    rb"^(?:character\s+varying|varchar|character|char)\s*\(\s*(\d+)\s*\)",
    re.IGNORECASE,
)
_CONSTRAINT_WORDS = (
    b"PRIMARY",
    b"UNIQUE",
    b"CONSTRAINT",
    b"CHECK",
    b"FOREIGN",
    b"EXCLUDE",
    b"LIKE",
)

_FIELD_REGISTRY = "metadatafieldregistry"
_SCHEMA_REGISTRY = "metadataschemaregistry"

_BACKSLASH = 0x5C
_QUOTE = 0x22
_DOT = 0x2E
_TAB = 0x09

_NULL = b"\\N"
_TERMINATOR = b"\\."

_SIMPLE_ESCAPES = {
    ord("b"): b"\x08",
    ord("f"): b"\x0c",
    ord("n"): b"\x0a",
    ord("r"): b"\x0d",
    ord("t"): b"\x09",
    ord("v"): b"\x0b",
    ord("\\"): b"\\",
}
_OCTAL = frozenset(b"01234567")
_HEX = frozenset(b"0123456789abcdefABCDEF")


def _split_ending(line: bytes) -> tuple[bytes, bytes]:
    if line.endswith(b"\r\n"):
        return line[:-2], b"\r\n"
    if line.endswith(b"\n"):
        return line[:-1], b"\n"
    return line, b""


def _split_qualified(raw: bytes) -> list[bytes]:
    parts: list[bytes] = []
    current = bytearray()
    quoted = False
    for char in raw:
        if char == _QUOTE:
            quoted = not quoted
            current.append(char)
        elif char == _DOT and not quoted:
            parts.append(bytes(current))
            current.clear()
        else:
            current.append(char)
    parts.append(bytes(current))
    return parts


def _unquote(raw: bytes) -> str:
    if len(raw) >= 2 and raw.startswith(b'"') and raw.endswith(b'"'):
        raw = raw[1:-1].replace(b'""', b'"')
    return raw.decode("utf-8", "surrogateescape")


def _table_name(raw: bytes) -> str:
    """Return the table part of a possibly schema-qualified name."""
    return _unquote(_split_qualified(raw)[-1])


def _column_list(raw: bytes) -> list[str]:
    return [_unquote(match.group(0)) for match in _IDENT_RE.finditer(raw)]


def _unescape(raw: bytes) -> bytes:
    """Decode one COPY text-format field."""
    out = bytearray()
    index = 0
    end = len(raw)
    while index < end:
        char = raw[index]
        if char != _BACKSLASH:
            out.append(char)
            index += 1
            continue
        index += 1
        if index >= end:
            raise DumpFormatError("trailing backslash in COPY data")
        escaped = raw[index]
        mapped = _SIMPLE_ESCAPES.get(escaped)
        if mapped is not None:
            out += mapped
            index += 1
        elif escaped in _OCTAL:
            stop = index
            while stop < end and stop < index + 3 and raw[stop] in _OCTAL:
                stop += 1
            out.append(int(raw[index:stop], 8) & 0xFF)
            index = stop
        elif escaped in b"xX":
            stop = index + 1
            while stop < end and stop < index + 3 and raw[stop] in _HEX:
                stop += 1
            if stop == index + 1:
                raise DumpFormatError("invalid \\x escape in COPY data")
            out.append(int(raw[index + 1 : stop], 16))
            index = stop
        else:
            out.append(escaped)
            index += 1
    return bytes(out)


def _escape_copy(value: str) -> bytes:
    out = bytearray()
    for byte in value.encode("utf-8"):
        if byte == _BACKSLASH:
            out += b"\\\\"
        elif byte == 0x0A:
            out += b"\\n"
        elif byte == 0x0D:
            out += b"\\r"
        elif byte == _TAB:
            out += b"\\t"
        elif byte == 0x08:
            out += b"\\b"
        elif byte == 0x0C:
            out += b"\\f"
        elif byte == 0x0B:
            out += b"\\v"
        else:
            out.append(byte)
    return bytes(out)


def _decode(value: bytes) -> str:
    return value.decode("utf-8", "surrogateescape")


def _conditions_match(
    conditions: dict[str, frozenset[str]],
    values: list[bytes | None],
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
        cell = values[position]
        if cell is None:
            return False
        if _decode(cell) not in allowed:
            return False
    return True


def _create_complete(line: bytes) -> bool:
    stripped = line.strip()
    return stripped.startswith(b")") or stripped.endswith(b";")


class PgRewriter:
    """Rewrite pg_dump ``COPY ... FROM stdin`` blocks according to a profile."""

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
        self._widths: dict[str, dict[str, int | None]] = {}

        self.in_copy = False
        self.restrict_key: str | None = None
        self._saw_copy = False

        self._create_table: str | None = None
        self._create_lines: list[bytes] = []

        self._copy_table = ""
        self._copy_columns: list[str] = []
        self._copy_widths: list[int | None] = []
        self._copy_index: dict[str, int] = {}
        self._copy_rules: TableRules | None = None
        self._copy_rule_map: dict[str, Rule] = {}
        self._copy_truncate = False
        self._copy_registry: str | None = None
        self._copy_metadata_rules: dict[str, Rule] = {}

        self._schemas: dict[str, str] = {}
        self._fields: dict[str, tuple[str, str, str | None]] = {}
        self._schema_seen = False
        self._field_seen = False

    # -- stream -------------------------------------------------------------

    def feed(self, line: bytes) -> bytes | None:
        """Return the bytes to emit for ``line``, or None to drop them."""
        if self._create_table is not None:
            if (
                _ANY_COPY_RE.match(line)
                or _INSERT_RE.match(line)
                or _CREATE_RE.match(line)
            ):
                raise DumpFormatError(
                    f"CREATE TABLE {self._create_table} is not terminated"
                )
            self._create_lines.append(line)
            if _create_complete(line):
                self._finish_create()
            return line

        if self.in_copy:
            return self._feed_copy(line)

        restrict = _RESTRICT_RE.match(line)
        if restrict is not None:
            self.restrict_key = restrict.group(1).decode("utf-8", "surrogateescape")
            return line

        create = _CREATE_RE.match(line)
        if create is not None:
            self._create_table = _table_name(create.group(1))
            self._create_lines = [line]
            if _create_complete(line):
                self._finish_create()
            return line

        copy = _COPY_RE.match(line)
        if copy is not None:
            self._start_copy(copy)
            return line

        other = _ANY_COPY_RE.match(line)
        if other is not None:
            table = _table_name(other.group(1)).lower()
            if table in self._tables or table in self._truncate:
                raise DumpFormatError(
                    f"unsupported COPY statement for {table}: "
                    + line[:60].decode("utf-8", "replace")
                )
            return line

        insert = _INSERT_RE.match(line)
        if insert is not None:
            table = _table_name(insert.group(1)).lower()
            if table in self._tables or table in self._truncate:
                raise DumpFormatError(
                    f"unsupported INSERT statement for {table} "
                    "(only COPY ... FROM stdin is supported)"
                )
            return line

        return line

    def finish(self) -> None:
        """Reject a dump that was cut mid-COPY or has no COPY blocks."""
        if self.in_copy:
            raise DumpFormatError("unterminated COPY block at end of dump")
        if self._create_table is not None:
            raise DumpFormatError(
                f"CREATE TABLE {self._create_table} is not terminated at end of dump"
            )
        if not self._saw_copy:
            raise DumpFormatError(
                "no PostgreSQL COPY blocks found (expected COPY ... FROM stdin)"
            )

    # -- CREATE TABLE -------------------------------------------------------

    def _finish_create(self) -> None:
        table = self._create_table or ""
        text = b"".join(self._create_lines)
        self._create_table = None
        self._create_lines = []

        match = _CREATE_RE.match(text)
        if match is None:
            raise DumpFormatError(f"cannot parse CREATE TABLE {table}")

        close = text.rfind(b")")
        body = text[match.end() : close] if close > match.end() else b""
        widths: dict[str, int | None] = {}
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.upper().startswith(_CONSTRAINT_WORDS):
                continue
            column = _COLUMN_DEF_RE.match(line)
            if column is None:
                continue
            name = column.group(1) if column.group(1) is not None else column.group(2)
            width = _WIDTH_RE.match(column.group(3))
            widths[_unquote(name).lower()] = int(width.group(1)) if width else None
        self._widths[table.lower()] = widths

    # -- COPY blocks --------------------------------------------------------

    def _start_copy(self, match: re.Match[bytes]) -> None:
        self._saw_copy = True
        self.in_copy = True

        table = _table_name(match.group(1))
        lower = table.lower()
        raw_columns = match.group(2)
        columns = _column_list(raw_columns) if raw_columns is not None else []

        self._copy_table = lower
        self._copy_columns = columns
        self._copy_index = {name.lower(): position for position, name in enumerate(columns)}
        widths = self._widths.get(lower, {})
        self._copy_widths = [widths.get(name.lower()) for name in columns]
        self._copy_truncate = lower in self._truncate
        self._copy_registry = None
        self._copy_metadata_rules = {}
        self._copy_rules = self._tables.get(lower)
        self._copy_rule_map = self._rule_maps.get(lower, {})

        if raw_columns is None and self._copy_rules is not None and not self._copy_truncate:
            raise DumpFormatError(
                f"COPY {table} without a column list is not supported"
            )
        if self._copy_truncate:
            return

        rules = self._copy_rules
        if rules is not None:
            dumped = {name.lower() for name in columns}
            for column in rules.columns:
                if column.lower() not in dumped:
                    self.report.missing_columns.add((lower, column))

        for name in columns:
            if name.lower() in self._copy_rule_map:
                continue
            if looks_like_pii(name):
                self.report.suspicious_columns.add((lower, name))

        if rules is not None and rules.by_metadata_field:
            if "metadata_field_id" not in self._copy_index:
                raise DumpFormatError(
                    f"{lower} has by_metadata_field rules but no metadata_field_id column"
                )
            self._copy_metadata_rules = self._resolve_metadata_rules(
                rules.by_metadata_field
            )

        if lower == _FIELD_REGISTRY:
            self._copy_registry = "field"
        elif lower == _SCHEMA_REGISTRY:
            self._copy_registry = "schema"

    def _feed_copy(self, line: bytes) -> bytes | None:
        body, ending = _split_ending(line)

        if body == _TERMINATOR:
            self._finish_copy()
            return line

        if self._copy_truncate:
            stats = self.report.stats(self._copy_table)
            stats.rows += 1
            stats.truncated_rows += 1
            return None

        if self._copy_registry is not None:
            self._collect_registry_row(body)

        rules = self._copy_rules
        if rules is None:
            return line
        if not rules.columns and not rules.by_metadata_field:
            return line
        return self._rewrite_row(body, ending)

    def _finish_copy(self) -> None:
        if self._copy_registry == "field":
            self._field_seen = True
        elif self._copy_registry == "schema":
            self._schema_seen = True

        self.in_copy = False
        self._copy_table = ""
        self._copy_columns = []
        self._copy_widths = []
        self._copy_index = {}
        self._copy_rules = None
        self._copy_rule_map = {}
        self._copy_truncate = False
        self._copy_registry = None
        self._copy_metadata_rules = {}

    def _collect_registry_row(self, body: bytes) -> None:
        cells = body.split(b"\t")
        if len(cells) != len(self._copy_columns):
            raise DumpFormatError(
                f"{self._copy_table} COPY row has {len(cells)} values but the"
                f" header lists {len(self._copy_columns)} columns"
            )

        def value(column: str) -> str | None:
            position = self._copy_index.get(column)
            if position is None:
                return None
            cell = cells[position]
            return None if cell == _NULL else _decode(_unescape(cell))

        if self._copy_registry == "field":
            field_id = value("metadata_field_id")
            schema_id = value("metadata_schema_id")
            element = value("element")
            if not (field_id and schema_id and element):
                raise DumpFormatError(
                    "metadatafieldregistry row lacks metadata_field_id, "
                    "metadata_schema_id or element"
                )
            self._fields[field_id] = (schema_id, element, value("qualifier"))
        else:
            schema_id = value("metadata_schema_id")
            short_id = value("short_id")
            if schema_id and short_id:
                self._schemas[schema_id] = short_id

    def _resolve_metadata_rules(
        self, by_metadata_field: dict[str, Rule]
    ) -> dict[str, Rule]:
        if not (self._field_seen and self._schema_seen):
            raise DumpFormatError(
                "COPY metadatavalue came before metadatafieldregistry and "
                "metadataschemaregistry were read"
            )

        lookup: dict[str, Rule] = {}
        for name, rule in by_metadata_field.items():
            lookup[name] = rule
            lookup.setdefault(name.lower(), rule)

        resolved: dict[str, Rule] = {}
        matched: set[str] = set()
        for field_id, (schema_id, element, qualifier) in self._fields.items():
            schema = self._schemas.get(schema_id)
            if schema is None:
                raise DumpFormatError(
                    f"metadatafieldregistry row {field_id} points to unknown "
                    f"metadata_schema_id {schema_id}"
                )
            name = f"{schema}.{element}"
            if qualifier is not None:
                name += f".{qualifier}"
            rule = lookup.get(name, lookup.get(name.lower()))
            if rule is not None:
                resolved[field_id] = rule
                matched.add(name.lower())
        for name in by_metadata_field:
            if name.lower() not in matched:
                # Field not registered in this install: nothing to rewrite,
                # but surface it in the report like a missing column.
                self.report.missing_columns.add(("metadatavalue", name))
        return resolved

    def _rewrite_row(self, body: bytes, ending: bytes) -> bytes:
        cells = body.split(b"\t")
        columns = self._copy_columns
        if len(cells) != len(columns):
            raise DumpFormatError(
                f"{self._copy_table} COPY row has {len(cells)} values but the"
                f" header lists {len(columns)} columns"
            )

        values = [None if cell == _NULL else _unescape(cell) for cell in cells]
        rules = self._copy_rules
        if rules is None:
            return body + ending

        stats = self.report.stats(self._copy_table)
        stats.rows += 1

        if rules.when and not _conditions_match(rules.when, values, self._copy_index):
            return body + ending
        if any(
            allowed
            and _conditions_match(
                {column: allowed}, values, self._copy_index, missing_matches=False
            )
            for column, allowed in rules.unless.items()
        ):
            return body + ending

        parts = list(cells)
        for position, name in enumerate(columns):
            rule = self._copy_rule_map.get(name.lower())
            if rule is None:
                continue
            value = values[position]
            if value is None or value == b"":
                continue
            fake = self.faker.fake(
                rule,
                _decode(value),
                key=f"{self._copy_table}.{name}",
                max_len=self._copy_widths[position],
            )
            parts[position] = _NULL if fake is None else _escape_copy(fake)
            stats.cells += 1

        if self._copy_metadata_rules:
            field_position = self._copy_index.get("metadata_field_id")
            text_position = self._copy_index.get("text_value")
            if field_position is None or text_position is None:
                raise DumpFormatError(
                    f"{self._copy_table} has by_metadata_field rules but no"
                    " metadata_field_id/text_value columns"
                )
            field_id = values[field_position]
            text = values[text_position]
            if field_id is not None and text not in (None, b""):
                rule = self._copy_metadata_rules.get(_decode(field_id))
                if rule is not None:
                    fake = self.faker.fake(
                        rule,
                        _decode(text),
                        key=f"{self._copy_table}.text_value",
                        max_len=self._copy_widths[text_position],
                    )
                    parts[text_position] = (
                        _NULL if fake is None else _escape_copy(fake)
                    )
                    stats.cells += 1

        return b"\t".join(parts) + ending
