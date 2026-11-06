"""Tests for the anonymize profile loader and validation."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.anonymize.errors import ProfileError  # noqa: E402
from jarvis.anonymize.profile import (  # noqa: E402
    Rule,
    list_profiles,
    load_profile,
)


def write_profile(tmp_path: Path, body: str, name: str = "p.toml") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_all_bundled_profiles_load():
    profiles = {profile.name: profile for profile in list_profiles()}
    assert set(profiles) == {"koha", "dspace", "room_reservation", "linebrarian"}
    assert profiles["koha"].engine == "mysql"
    assert profiles["dspace"].engine == "psql"
    assert profiles["room_reservation"].engine == "psql"
    assert profiles["linebrarian"].engine == "psql"


def test_rule_short_and_long_form():
    koha = load_profile("koha")
    borrowers = koha.tables["borrowers"].columns
    assert borrowers["surname"] == Rule("name")
    assert borrowers["cardnumber"] == Rule("digits", unique=True)


def test_when_unless_and_metadata():
    koha = load_profile("koha")
    assert koha.tables["additional_field_values"].when == {
        "record_table": frozenset({"borrowers"})
    }
    assert koha.tables["borrower_attributes"].unless == {"code": frozenset()}

    dspace = load_profile("dspace")
    field_rules = dspace.tables["metadatavalue"].by_metadata_field
    assert field_rules["eperson.firstname"] == Rule("name")


def test_truncate_and_tld():
    koha = load_profile("koha")
    assert "sessions" in koha.truncate
    assert isinstance(koha.truncate, frozenset)
    assert koha.email_tld == "invalid"


def test_unknown_strategy_rejected(tmp_path):
    path = write_profile(
        tmp_path,
        """
[profile]
name = "tmp"
engine = "mysql"

[tables.t]
x = "bogus"
""",
    )
    with pytest.raises(ProfileError) as excinfo:
        load_profile(path=path)
    assert "bogus" in str(excinfo.value)


def test_bad_engine_rejected(tmp_path):
    path = write_profile(
        tmp_path,
        """
[profile]
name = "tmp"
engine = "oracle"
""",
    )
    with pytest.raises(ProfileError):
        load_profile(path=path)


def test_unknown_profile_name():
    with pytest.raises(ProfileError):
        load_profile("nope")


def test_neither_or_both_args(tmp_path):
    with pytest.raises(ProfileError):
        load_profile()

    path = write_profile(
        tmp_path,
        """
[profile]
name = "tmp"
engine = "mysql"
""",
    )
    with pytest.raises(ProfileError):
        load_profile("koha", path=path)
