"""Anonymize a restored database in place with ``UPDATE``/``TRUNCATE``.

Direct mode reads the schema through the same client the operator uses
(``sudo mysql`` / ``sudo -u postgres psql``), builds one statement per ruled
column and feeds the whole script to that client.  The random values are
produced inside SQL, so no data ever passes through Python.
"""

from __future__ import annotations

import math
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, TextIO

from .detect import looks_like_pii
from .errors import ProfileError
from .profile import ENGINES, Profile, Rule, TableRules
from .report import Report


class DirectError(RuntimeError):
    """The database client failed or could not be run (CLI exit 3)."""


class ConfirmationError(Exception):
    """The operator did not confirm the database name (CLI exit 1)."""


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    max_len: int | None
    nullable: bool


@dataclass(frozen=True)
class TableInfo:
    columns: dict[str, Column]
    pk: tuple[str, ...]


# -- identifiers and literals ---------------------------------------------

_MD5 = {"mysql": "MD5(RAND())", "psql": "md5(random()::text)"}

# 2005-12-31 minus 1950-01-01, so every date stays inside the fake range.
_DATE_DAYS = 20454


def _ident(engine: str, name: str) -> str:
    if engine == "mysql":
        return "`" + name.replace("`", "``") + "`"
    return '"' + name.replace('"', '""') + '"'


def _literal(engine: str, value: str) -> str:
    if engine == "mysql":
        escaped = (
            value.replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace("\0", "\\0")
            .replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\x1a", "\\Z")
        )
        return "'" + escaped + "'"
    return "'" + value.replace("'", "''") + "'"


def _concat(engine: str, *parts: str) -> str:
    if len(parts) == 1:
        return parts[0]
    if engine == "mysql":
        return "CONCAT(" + ", ".join(parts) + ")"
    return "(" + " || ".join(parts) + ")"


def _take(engine: str, block: str, length: int | str) -> str:
    """Cut ``block`` (32 random hex chars) down to ``length`` characters."""
    repeats = max(1, math.ceil(length / 32)) if isinstance(length, int) else 2
    return f"LEFT({_concat(engine, *([block] * repeats))}, {length})"


def _char_length(engine: str, ref: str) -> str:
    if engine == "mysql":
        return f"CHAR_LENGTH({ref})"
    return f"length({ref})"


def _wrap(expr: str, max_len: int | None) -> str:
    return expr if max_len is None else f"LEFT({expr}, {max_len})"


def _digit_block(engine: str) -> str:
    if engine == "psql":
        return f"translate({_MD5['psql']}, 'abcdef', '012345')"
    expr = _MD5["mysql"]
    for source, target in zip("abcdef", "012345"):
        expr = f"REPLACE({expr}, '{source}', '{target}')"
    return expr


def _letter_block(engine: str) -> str:
    if engine == "psql":
        return f"translate({_MD5['psql']}, '0123456789', 'ghijklmnop')"
    expr = _MD5["mysql"]
    for source, target in zip("0123456789", "ghijklmnop"):
        expr = f"REPLACE({expr}, '{source}', '{target}')"
    return expr


def _name_expr(engine: str, ref: str) -> str:
    """One capital letter followed by random lowercase letters."""
    length = _char_length(engine, ref)
    first = f"UPPER({_take(engine, _letter_block(engine), 1)})"
    rest = _take(engine, _letter_block(engine), f"{length} - 1")
    return _concat(engine, first, rest)


# -- value expressions -----------------------------------------------------


def _email_expr(engine: str, tld: str, max_len: int | None) -> str:
    local, domain = 8, 6
    if max_len is not None and max_len < local + domain + len(tld) + 2:
        budget = max(2, max_len - len(tld) - 2)
        domain = max(1, min(6, budget // 2))
        local = max(1, budget - domain)
    return _concat(
        engine,
        _take(engine, _MD5[engine], local),
        "'@'",
        _take(engine, _MD5[engine], domain),
        _literal(engine, "." + tld),
    )


def _date_expr(engine: str, data_type: str) -> str:
    kind = data_type.lower()
    if engine == "mysql":
        base = f"DATE_ADD('1950-01-01', INTERVAL FLOOR(RAND() * {_DATE_DAYS}) DAY)"
        if kind == "date" or kind == "datetime" or kind.startswith("timestamp"):
            return base
        return f"DATE_FORMAT({base}, '%Y-%m-%d')"
    base = f"(date '1950-01-01' + floor(random() * {_DATE_DAYS})::int)"
    if kind in ("date", "timestamp without time zone", "timestamp with time zone"):
        return base
    return f"to_char({base}, 'YYYY-MM-DD')"


def _ip_expr(engine: str, data_type: str) -> str:
    if engine == "mysql":
        return "CONCAT('192.0.2.', 1 + FLOOR(RAND() * 254))"
    expr = "('192.0.2.' || (1 + floor(random() * 254))::int)"
    return expr + "::inet" if data_type.lower() == "inet" else expr


def _json_expr(engine: str, data_type: str, ref: str) -> str:
    kind = data_type.lower()
    if engine == "mysql":
        # MySQL 8 JSON needs an explicit cast for string functions.
        probe = f"CAST({ref} AS CHAR)" if kind == "json" else ref
        return (
            f"CASE WHEN LEFT(LTRIM({probe}), 1) = '[' THEN '[]' "
            "ELSE '{}' END"
        )
    cast = "::" + kind if kind in ("json", "jsonb") else ""
    # json/jsonb have no ltrim(); probe the text representation instead.
    probe = f"{ref}::text" if cast else ref
    expr = (
        f"(CASE WHEN left(ltrim({probe}), 1) = '[' THEN '[]' "
        "ELSE '{}' END)"
    )
    return expr + cast


# Keep a hash prefix (algorithm/cost/salt) only for known hash formats;
# anything else (e.g. a plaintext password containing "$") is fully replaced.
# "[$]" keeps the patterns free of backslashes in both engines.
_HASH_PREFIX_RE = (
    "^([$](2[abxy]?|1|5|6|argon2(id|i|d))[$]"
    "|(pbkdf2_[a-z0-9]+|argon2|bcrypt_sha256|scrypt)[$])"
)


def _password_expr(engine: str, ref: str) -> str:
    if engine == "mysql":
        prefix = (
            f"IF({ref} REGEXP '{_HASH_PREFIX_RE}', CONCAT(SUBSTRING_INDEX({ref},"
            f" '$', CHAR_LENGTH({ref}) - CHAR_LENGTH(REPLACE({ref}, '$', ''))),"
            f" '$'), '')"
        )
        return _concat(
            engine,
            prefix,
            _take(engine, _MD5[engine], _char_length(engine, ref)),
        )
    prefix = (
        f"CASE WHEN {ref} ~ '{_HASH_PREFIX_RE}'"
        f" THEN COALESCE(substring({ref} from '^(.*[$])'), '') ELSE '' END"
    )
    return _concat(
        engine,
        prefix,
        _take(engine, _MD5[engine], f"length({ref})"),
    )


def _plain_expr(
    engine: str, profile: Profile, strategy: str, ref: str, column: Column
) -> str:
    if strategy == "null":
        return "NULL"
    if strategy == "empty":
        return "''"
    if strategy == "name":
        body = _name_expr(engine, ref)
    elif strategy == "text":
        body = _take(engine, _letter_block(engine), _char_length(engine, ref))
    elif strategy == "email":
        return _email_expr(engine, profile.email_tld, column.max_len)
    elif strategy == "phone":
        body = _concat(engine, "'0'", _take(engine, _digit_block(engine), 9))
    elif strategy == "digits":
        body = _take(engine, _digit_block(engine), _char_length(engine, ref))
    elif strategy == "id":
        body = _take(engine, _MD5[engine], _char_length(engine, ref))
    elif strategy == "password":
        body = _password_expr(engine, ref)
    elif strategy == "date":
        body = _date_expr(engine, column.data_type)
    elif strategy == "ip":
        body = _ip_expr(engine, column.data_type)
    elif strategy == "json":
        body = _json_expr(engine, column.data_type, ref)
    else:
        raise ProfileError(f"unknown strategy {strategy!r}")
    return _wrap(body, column.max_len)


# -- primary keys and unique values ---------------------------------------

_PK_WIDTHS = {
    "uuid": 36,
    "tinyint": 3,
    "smallint": 5,
    "int2": 5,
    "mediumint": 8,
    "smallserial": 5,
    "int": 10,
    "integer": 10,
    "int4": 10,
    "serial": 10,
    "bigint": 20,
    "int8": 20,
    "bigserial": 20,
}

_UNIQUE_BLOCKS = {
    "digits": _digit_block,
    "phone": _digit_block,
    "name": _letter_block,
    "text": _letter_block,
    "id": lambda engine: _MD5[engine],
    "password": lambda engine: _MD5[engine],
}
_UNIQUE_UNSUPPORTED = frozenset({"date", "ip", "json", "null", "empty"})

# Comparing a non-text column to '' is an error in PostgreSQL and a warning in
# strict MySQL, so the empty-string guard is only added for these types.
_TEXTUAL_TYPES = frozenset(
    {
        "char",
        "varchar",
        "character",
        "character varying",
        "bpchar",
        "citext",
        "name",
        "enum",
        "set",
        "tinytext",
        "text",
        "mediumtext",
        "longtext",
    }
)
# MySQL's "zero date" is not personal data and must survive untouched.
_TEMPORAL_TYPES = frozenset({"date", "datetime", "timestamp"})


def _pk_width(column: Column) -> int:
    if column.max_len:
        return column.max_len
    return _PK_WIDTHS.get(column.data_type.lower(), 32)


def _pk_parts(
    engine: str, table: str, info: TableInfo
) -> list[tuple[str, int]]:
    if not info.pk:
        raise ProfileError(
            f"{table}: a column with unique=true needs a primary key"
        )
    parts: list[tuple[str, int]] = []
    for name in info.pk:
        column = _lookup_column(info, name)
        if column is None:
            raise ProfileError(
                f"{table}: primary key column {name!r} has no column definition"
            )
        if engine == "mysql":
            text = f"CAST({_ident(engine, column.name)} AS CHAR)"
        else:
            text = f"{_ident(engine, column.name)}::text"
        parts.append((text, _pk_width(column)))
    return parts


def _padded_pk(engine: str, parts: list[tuple[str, int]]) -> str:
    return _concat(
        engine, *[f"LPAD({text}, {width}, '0')" for text, width in parts]
    )


def _unique_exprs(
    engine: str,
    profile: Profile,
    table: str,
    rule: Rule,
    column: Column,
    info: TableInfo,
) -> tuple[str, str]:
    """Return ``(park_expression, final_expression)`` for a unique column.

    Pass one parks every matching row on ``'~' || padded pk`` so the random
    values of pass two can never collide with an original value.  Pass two
    appends the padded primary key to a fixed-length random prefix, which makes
    the result injective even if the column is cut to ``max_len``.
    """
    if rule.strategy in _UNIQUE_UNSUPPORTED:
        raise ProfileError(
            f"{table}.{column.name}: unique=true is not supported for"
            f" strategy {rule.strategy!r}"
        )
    parts = _pk_parts(engine, table, info)
    width = sum(part_width for _, part_width in parts)
    pk = _padded_pk(engine, parts)
    park = _concat(engine, _literal(engine, "~"), pk)
    max_len = column.max_len

    if rule.strategy == "email":
        fixed = width + len(profile.email_tld) + 8
        room = 8 if max_len is None else max_len - fixed
        if room < 4:
            raise ProfileError(
                f"{table}.{column.name}: varchar({max_len}) leaves no room for"
                " a unique email"
            )
        final = _concat(
            engine,
            _take(engine, _MD5[engine], room),
            pk,
            "'@'",
            _take(engine, _MD5[engine], 6),
            _literal(engine, "." + profile.email_tld),
        )
        return park, final

    room = 8 if max_len is None else max_len - width
    if room < 4:
        raise ProfileError(
            f"{table}.{column.name}: only {max_len} characters, too short for"
            " a unique value plus the primary key"
        )
    block = _UNIQUE_BLOCKS[rule.strategy](engine)
    return park, _concat(engine, _take(engine, block, room), pk)


# -- schema lookup ---------------------------------------------------------


def _lookup_column(info: TableInfo, name: str) -> Column | None:
    wanted = name.lower()
    for key, column in info.columns.items():
        if key.lower() == wanted or column.name.lower() == wanted:
            return column
    return None


def _conditions(
    engine: str,
    info: TableInfo,
    conditions: dict[str, frozenset[str]],
    prefix: str,
    *,
    invert: bool,
) -> list[str]:
    """Build ``IN``/``NOT IN`` clauses that fail safe toward anonymizing.

    A ``when`` on a column that does not exist is dropped, so the rows are
    still rewritten; an ``unless`` on a missing column is dropped too, so it
    never excludes rows.  An empty ``unless`` list excludes nothing.
    """
    clauses: list[str] = []
    for column_name, values in conditions.items():
        if not values:
            if not invert:
                clauses.append("1 = 0")
            continue
        column = _lookup_column(info, column_name)
        if column is None:
            continue
        ref = prefix + _ident(engine, column.name)
        literals = ", ".join(_literal(engine, value) for value in sorted(values))
        operator = "NOT IN" if invert else "IN"
        clauses.append(f"{ref} {operator} ({literals})")
    return clauses


# -- statement builders ----------------------------------------------------


def _base_where(engine: str, ref: str, column: Column) -> list[str]:
    """Return the always-on guards for one column.

    NULL and ``''`` stay untouched.  Non-text columns cannot be compared to
    ``''``, so they only get the NULL guard (plus the MySQL zero-date guard).
    """
    kind = column.data_type.lower()
    clauses = [f"{ref} IS NOT NULL"]
    if kind in _TEXTUAL_TYPES:
        clauses.append(f"{ref} <> ''")
    elif engine == "mysql" and kind in _TEMPORAL_TYPES:
        clauses.append(f"{ref} <> '0000-00-00'")
    return clauses


def _update_statements(
    engine: str,
    profile: Profile,
    table: str,
    info: TableInfo,
    rules: TableRules,
    column_name: str,
    rule: Rule,
    report: Report,
) -> list[str]:
    column = _lookup_column(info, column_name)
    if column is None:
        report.missing_columns.add((table, column_name))
        return []

    ref = _ident(engine, column.name)
    where = _base_where(engine, ref, column)
    where += _conditions(engine, info, rules.when, "", invert=False)
    where += _conditions(engine, info, rules.unless, "", invert=True)
    target = _ident(engine, table)

    if rule.unique:
        park, final = _unique_exprs(engine, profile, table, rule, column, info)
        expressions = [park, final]
    else:
        expressions = [
            _plain_expr(engine, profile, rule.strategy, ref, column)
        ]

    statements = [
        f"UPDATE {target} SET {ref} = {expression} WHERE {' AND '.join(where)};"
        for expression in expressions
    ]
    report.stats(table).cells += len(statements)
    return statements


def _metadata_statements(
    engine: str,
    profile: Profile,
    table: str,
    info: TableInfo,
    rules: TableRules,
    report: Report,
) -> list[str]:
    if engine != "psql":
        raise ProfileError("by_metadata_field rules are PostgreSQL-only")
    field_column = _lookup_column(info, "metadata_field_id")
    text_column = _lookup_column(info, "text_value")
    if field_column is None or text_column is None:
        raise ProfileError(
            f"{table}: by_metadata_field needs metadata_field_id and text_value"
        )

    conditions = _conditions(engine, info, rules.when, "mv.", invert=False)
    conditions += _conditions(engine, info, rules.unless, "mv.", invert=True)
    where = [
        "mv.metadata_field_id = f.metadata_field_id",
        "mv.text_value IS NOT NULL",
        "mv.text_value <> ''",
        *conditions,
    ]
    ref = f"mv.{_ident(engine, text_column.name)}"
    statements: list[str] = []

    for field, rule in sorted(rules.by_metadata_field.items()):
        if rule.unique:
            raise ProfileError(
                f"{table}.{field}: unique=true is not supported for"
                " by_metadata_field rules"
            )
        parts = field.split(".")
        if len(parts) < 2:
            raise ProfileError(
                f"{table}: by_metadata_field key {field!r} must look like"
                " schema.element[.qualifier]"
            )
        short_id, element = parts[0], parts[1]
        clauses = [
            f"s.short_id = {_literal(engine, short_id)}",
            f"f.element = {_literal(engine, element)}",
        ]
        if len(parts) > 2:
            qualifier = ".".join(parts[2:])
            clauses.append(
                f"f.qualifier IS NOT DISTINCT FROM {_literal(engine, qualifier)}"
            )
        else:
            clauses.append("f.qualifier IS NULL")

        expression = _plain_expr(
            engine, profile, rule.strategy, ref, text_column
        )
        # PostgreSQL does not accept an alias-qualified SET target.
        statements.append(
            f"UPDATE {_ident(engine, table)} mv"
            f" SET {_ident(engine, text_column.name)} = {expression}"
            f' FROM {_ident(engine, "metadatafieldregistry")} f'
            f' JOIN {_ident(engine, "metadataschemaregistry")} s'
            " ON s.metadata_schema_id = f.metadata_schema_id"
            f" WHERE {' AND '.join(where + clauses)};"
        )
        report.stats(table).cells += 1

    return statements


def build_sql(
    profile: Profile,
    engine: str,
    schema: dict[str, TableInfo],
    report: Report,
) -> list[str]:
    """Return the full SQL script that anonymizes ``schema`` in place."""
    if engine not in ENGINES:
        raise ProfileError(f"unsupported engine {engine!r}")
    if engine != profile.engine:
        raise ProfileError(
            f"profile {profile.name!r} is for engine {profile.engine!r},"
            f" not {engine!r}"
        )

    index = {name.lower(): (name, info) for name, info in schema.items()}
    truncated = {name.lower() for name in profile.truncate}

    truncates: list[str] = []
    for name in sorted(profile.truncate):
        hit = index.get(name.lower())
        if hit is None:
            continue
        truncates.append(f"TRUNCATE {_ident(engine, hit[0])};")
        report.stats(hit[0].lower())

    updates: list[str] = []
    for table in sorted(profile.tables):
        rules = profile.tables[table]
        hit = index.get(table.lower())
        if hit is None:
            for column in rules.columns:
                report.missing_columns.add((table.lower(), column))
            for field in rules.by_metadata_field:
                report.missing_columns.add((table.lower(), field))
            continue

        db_table, info = hit
        if table.lower() in truncated:
            continue

        rule_map = {
            column.lower(): rule for column, rule in rules.columns.items()
        }
        for column_name, rule in rules.columns.items():
            updates.extend(
                _update_statements(
                    engine,
                    profile,
                    db_table,
                    info,
                    rules,
                    column_name,
                    rule,
                    report,
                )
            )

        if rules.by_metadata_field:
            for registry in ("metadatafieldregistry", "metadataschemaregistry"):
                if registry not in index:
                    raise ProfileError(
                        f"{db_table}: by_metadata_field rules need the"
                        f" {registry} table, which is missing from the"
                        " database"
                    )
            updates.extend(
                _metadata_statements(
                    engine, profile, db_table, info, rules, report
                )
            )

        for key, column in info.columns.items():
            if key.lower() in rule_map:
                continue
            if looks_like_pii(column.name):
                report.suspicious_columns.add((db_table.lower(), column.name))

    if engine == "mysql":
        return [
            "SET FOREIGN_KEY_CHECKS=0;",
            *truncates,
            *updates,
            "SET FOREIGN_KEY_CHECKS=1;",
        ]
    return ["BEGIN;", *truncates, *updates, "COMMIT;"]


# -- client ----------------------------------------------------------------

_MYSQL_COLUMNS_SQL = """\
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE,
       COALESCE(CHARACTER_MAXIMUM_LENGTH, -1), IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, ORDINAL_POSITION;
"""

_MYSQL_PK_SQL = """\
SELECT TABLE_NAME, COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'PRIMARY'
ORDER BY TABLE_NAME, ORDINAL_POSITION;
"""

_PSQL_COLUMNS_SQL = """\
SELECT c.table_name, c.column_name, c.data_type,
       COALESCE(c.character_maximum_length, -1), c.is_nullable
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_schema = c.table_schema AND t.table_name = c.table_name
WHERE c.table_schema = current_schema() AND t.table_type = 'BASE TABLE'
ORDER BY c.table_name, c.ordinal_position;
"""

_PSQL_PK_SQL = """\
SELECT tc.table_name, kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_name = tc.constraint_name
 AND kcu.table_schema = tc.table_schema
 AND kcu.table_name = tc.table_name
WHERE tc.constraint_type = 'PRIMARY KEY'
  AND tc.table_schema = current_schema()
ORDER BY tc.table_name, kcu.ordinal_position;
"""

_MODES = {
    "mysql": {
        "columns": _MYSQL_COLUMNS_SQL,
        "pk": _MYSQL_PK_SQL,
        "flags": ("-B", "-N"),
    },
    "psql": {
        "columns": _PSQL_COLUMNS_SQL,
        "pk": _PSQL_PK_SQL,
        "flags": ("-A", "-t", "-F", "\t"),
    },
}


def default_client(engine: str, db: str) -> list[str]:
    """Return the passwordless client jarvis uses for ``engine``."""
    if engine == "mysql":
        return ["sudo", "mysql", "--defaults-file=/etc/mysql/debian.cnf", db]
    if engine == "psql":
        return [
            "sudo",
            "-u",
            "postgres",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-X",
            "-q",
            db,
        ]
    raise ProfileError(f"unsupported engine {engine!r}")


def _command(
    client: list[str], db: str, flags: tuple[str, ...]
) -> list[str]:
    """Insert engine flags before the database name (and add it if absent)."""
    cmd = list(client)
    if db in cmd:
        at = cmd.index(db)
        cmd[at:at] = list(flags)
        return cmd
    cmd.extend(flags)
    cmd.append(db)
    return cmd


def _run(client: list[str], sql: str) -> str:
    try:
        result = subprocess.run(
            client,
            input=sql,
            capture_output=True,
            text=True,
            errors="replace",
        )
    except OSError as exc:
        raise DirectError(f"cannot run {client[0]}: {exc}") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise DirectError(
            message
            or f"{client[0]} exited with status {result.returncode}"
        )
    return result.stdout


def fetch_schema(
    client: list[str], engine: str, db: str
) -> dict[str, TableInfo]:
    """Read ``information_schema`` through the client and return the tables."""
    if engine not in _MODES:
        raise ProfileError(f"unsupported engine {engine!r}")
    mode = _MODES[engine]
    flags = mode["flags"]

    columns_out = _run(
        _command(client, db, flags), mode["columns"]
    )
    pk_out = _run(_command(client, db, flags), mode["pk"])

    tables: dict[str, dict] = {}
    for line in columns_out.splitlines():
        fields = line.split("\t")
        if len(fields) < 5:
            continue
        table, name, data_type, max_len, nullable = fields[:5]
        try:
            width = int(max_len)
        except ValueError:
            width = -1
        tables.setdefault(table, {"columns": {}, "pk": []})["columns"][name] = (
            Column(
                name=name,
                data_type=data_type,
                max_len=None if width < 0 else width,
                nullable=nullable.upper() != "NO",
            )
        )

    primary_keys: dict[str, list[str]] = {}
    for line in pk_out.splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        primary_keys.setdefault(fields[0], []).append(fields[1])

    return {
        name: TableInfo(
            columns=data["columns"],
            pk=tuple(primary_keys.get(name, ())),
        )
        for name, data in tables.items()
    }


# -- driver ----------------------------------------------------------------


def _resolve_client(
    engine: str, db: str, client: list[str] | None
) -> list[str]:
    if client is not None:
        return list(client)
    override = os.environ.get("JARVIS_ANON_CLIENT")
    if override:
        return shlex.split(override)
    return default_client(engine, db)


def _print_summary(
    profile: Profile,
    engine: str,
    db: str,
    truncates: int,
    updates: int,
) -> None:
    print(
        f"Direct mode: database {db!r}, engine {engine},"
        f" profile {profile.name!r}",
        file=sys.stderr,
    )
    print(f"  tables to truncate: {truncates}", file=sys.stderr)
    print(f"  UPDATE statements: {updates}", file=sys.stderr)
    if engine == "mysql":
        print("  MySQL changes are not transactional", file=sys.stderr)


def run_direct(
    profile: Profile,
    engine: str,
    db: str,
    *,
    client: list[str] | None = None,
    dry_run: bool = False,
    assume_yes: bool = False,
    confirm: Callable[[str], str] = input,
    out: TextIO = sys.stdout,
) -> Report:
    """Anonymize ``db`` in place; return the report of what was generated."""
    if engine not in ENGINES:
        raise ProfileError(f"unsupported engine {engine!r}")
    if engine != profile.engine:
        raise ProfileError(
            f"profile {profile.name!r} is for engine {profile.engine!r},"
            f" not {engine!r}"
        )

    base = _resolve_client(engine, db, client)
    report = Report(profile=profile.name)
    schema = fetch_schema(base, engine, db)

    present = {name.lower() for name in schema}
    wanted = [*profile.tables, *profile.truncate]
    if not any(name.lower() in present for name in wanted):
        raise ProfileError(
            f"none of the tables in profile {profile.name!r} exist in"
            f" database {db!r}"
        )

    statements = build_sql(profile, engine, schema, report)
    if dry_run:
        print("\n".join(statements), file=out)
        return report

    truncates = sum(1 for s in statements if s.startswith("TRUNCATE "))
    updates = sum(1 for s in statements if s.startswith("UPDATE "))
    _print_summary(profile, engine, db, truncates, updates)

    if not assume_yes:
        # The prompt goes to stderr so stdout stays free for SQL.
        print(
            "Type the database name to continue: ",
            end="",
            file=sys.stderr,
            flush=True,
        )
        answer = confirm("")
        if answer.strip() != db:
            raise ConfirmationError(
                f"database name {answer.strip()!r} does not match {db!r};"
                " nothing was changed"
            )

    flags: tuple[str, ...] = ()
    if engine == "psql" and "ON_ERROR_STOP=1" not in base:
        flags = ("-v", "ON_ERROR_STOP=1")
    _run(_command(base, db, flags), "\n".join(statements) + "\n")
    return report
