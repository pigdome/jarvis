"""Load anonymize profiles from TOML and validate them."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from .errors import ProfileError

STRATEGIES: frozenset[str] = frozenset(
    {
        "name",
        "text",
        "email",
        "phone",
        "digits",
        "id",
        "date",
        "ip",
        "json",
        "password",
        "null",
        "empty",
    }
)

ENGINES: frozenset[str] = frozenset({"mysql", "psql"})
DEFAULT_EMAIL_TLD = "invalid"

_PROFILE_KEYS = frozenset({"name", "engine", "description", "truncate", "email_tld"})
_TOP_LEVEL_KEYS = frozenset({"profile", "tables"})
_TABLE_SECTIONS = frozenset({"when", "unless", "by_metadata_field"})
_RULE_KEYS = frozenset({"strategy", "unique"})


@dataclass(frozen=True)
class Rule:
    strategy: str
    unique: bool = False


@dataclass(frozen=True)
class TableRules:
    columns: dict[str, Rule]
    when: dict[str, frozenset[str]]
    unless: dict[str, frozenset[str]]
    by_metadata_field: dict[str, Rule]


@dataclass(frozen=True)
class Profile:
    name: str
    engine: str
    description: str
    truncate: frozenset[str]
    email_tld: str
    tables: dict[str, TableRules]


def _make_rule(value: Any, where: str) -> Rule:
    unique = False
    if isinstance(value, str):
        strategy = value
    elif isinstance(value, dict):
        unknown = set(value) - _RULE_KEYS
        if unknown:
            raise ProfileError(
                f"{where}: unknown rule keys: {', '.join(sorted(unknown))}"
            )
        strategy = value.get("strategy")
        unique = value.get("unique", False)
        if not isinstance(unique, bool):
            raise ProfileError(f"{where}: 'unique' must be a boolean")
    else:
        raise ProfileError(f"{where}: a rule must be a string or a table")

    if not isinstance(strategy, str) or strategy not in STRATEGIES:
        raise ProfileError(f"{where}: unknown strategy {strategy!r}")
    return Rule(strategy=strategy, unique=unique)


def _match_values(value: Any, where: str) -> frozenset[str]:
    if isinstance(value, str):
        return frozenset({value})
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return frozenset(value)
    raise ProfileError(f"{where}: expected a string or a list of strings")


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProfileError(f"{where}: expected a table")
    return value


def _parse_table(table: str, raw: Any) -> TableRules:
    raw = _mapping(raw, f"tables.{table}")
    columns: dict[str, Rule] = {}
    when: dict[str, frozenset[str]] = {}
    unless: dict[str, frozenset[str]] = {}
    by_metadata_field: dict[str, Rule] = {}

    for key, value in raw.items():
        where = f"tables.{table}.{key}"
        if key == "when":
            when = {
                column: _match_values(patterns, f"{where}.{column}")
                for column, patterns in _mapping(value, where).items()
            }
        elif key == "unless":
            unless = {
                column: _match_values(patterns, f"{where}.{column}")
                for column, patterns in _mapping(value, where).items()
            }
        elif key == "by_metadata_field":
            by_metadata_field = {
                field: _make_rule(rule, f"{where}.{field}")
                for field, rule in _mapping(value, where).items()
            }
        else:
            columns[key] = _make_rule(value, where)

    return TableRules(
        columns=columns,
        when=when,
        unless=unless,
        by_metadata_field=by_metadata_field,
    )


def _build_profile(data: Any, source: str) -> Profile:
    data = _mapping(data, source)

    unknown = set(data) - _TOP_LEVEL_KEYS
    if unknown:
        raise ProfileError(f"{source}: unknown keys: {', '.join(sorted(unknown))}")

    meta = data.get("profile")
    if not isinstance(meta, dict):
        raise ProfileError(f"{source}: missing [profile] section")

    unknown = set(meta) - _PROFILE_KEYS
    if unknown:
        raise ProfileError(
            f"{source}: unknown [profile] keys: {', '.join(sorted(unknown))}"
        )

    name = meta.get("name")
    if not isinstance(name, str) or not name:
        raise ProfileError(f"{source}: [profile] needs a non-empty 'name'")

    engine = meta.get("engine")
    if engine not in ENGINES:
        raise ProfileError(
            f"{source}: unsupported engine {engine!r} (expected mysql or psql)"
        )

    description = meta.get("description", "")
    if not isinstance(description, str):
        raise ProfileError(f"{source}: 'description' must be a string")

    truncate_raw = meta.get("truncate", [])
    if isinstance(truncate_raw, str):
        truncate_raw = [truncate_raw]
    if not isinstance(truncate_raw, list) or not all(
        isinstance(table, str) for table in truncate_raw
    ):
        raise ProfileError(f"{source}: 'truncate' must be a list of table names")
    truncate = frozenset(truncate_raw)

    email_tld = meta.get("email_tld", DEFAULT_EMAIL_TLD)
    if not isinstance(email_tld, str) or not email_tld:
        raise ProfileError(f"{source}: 'email_tld' must be a non-empty string")

    tables_raw = _mapping(data.get("tables", {}), f"{source}: [tables]")
    tables = {table: _parse_table(table, raw) for table, raw in tables_raw.items()}

    return Profile(
        name=name,
        engine=engine,
        description=description,
        truncate=truncate,
        email_tld=email_tld,
        tables=tables,
    )


def load_profile(
    name: str | None = None, path: Path | str | None = None
) -> Profile:
    """Load one bundled profile by name, or an external TOML file by path."""
    if (name is None) == (path is None):
        raise ProfileError("pass exactly one of 'name' or 'path'")

    if path is not None:
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProfileError(f"cannot read profile {path}: {exc}") from exc
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ProfileError(f"invalid TOML in {path}: {exc}") from exc
        return _build_profile(data, str(path))

    resource = files("jarvis.anonymize").joinpath("profiles", f"{name}.toml")
    try:
        text = resource.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(f"unknown profile {name!r}") from exc
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"invalid TOML in profile {name!r}: {exc}") from exc
    return _build_profile(data, f"profile {name!r}")


def list_profiles() -> list[Profile]:
    """Return every profile bundled with jarvis, ordered by name."""
    folder = files("jarvis.anonymize").joinpath("profiles")
    return [
        load_profile(entry.name[: -len(".toml")])
        for entry in sorted(folder.iterdir(), key=lambda entry: entry.name)
        if entry.name.endswith(".toml")
    ]
