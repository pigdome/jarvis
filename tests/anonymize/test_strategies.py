"""Tests for the anonymize fake value strategies."""

import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.anonymize.errors import DumpFormatError  # noqa: E402
from jarvis.anonymize.profile import Rule  # noqa: E402
from jarvis.anonymize.strategies import Faker  # noqa: E402

NAME = re.compile(r"^[A-Z][a-z]{2,9}( [A-Z][a-z]{2,9}){0,2}$")
EMAIL = re.compile(r"^[a-z]{6,12}@[a-z]{4,10}\.invalid$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fake(faker, strategy, original, *, key="t.c", max_len=None, unique=False):
    return faker.fake(
        Rule(strategy, unique=unique), original, key=key, max_len=max_len
    )


def test_name_shape():
    faker = Faker(random.Random(1))
    for _ in range(100):
        value = fake(faker, "name", "Apirak")
        assert NAME.match(value), value


def test_email_shape():
    faker = Faker(random.Random(1))
    for _ in range(100):
        value = fake(faker, "email", "apirak@example.com")
        assert EMAIL.match(value), value

    other = Faker(random.Random(1), email_tld="net")
    assert fake(other, "email", "apirak@example.com").endswith(".net")


def test_phone_digits_id():
    faker = Faker(random.Random(1))
    phone = fake(faker, "phone", "0812345678")
    assert re.fullmatch(r"0\d{9}", phone), phone

    digits = fake(faker, "digits", "6401234")
    assert re.fullmatch(r"\d{7}", digits), digits
    assert digits != "6401234"

    ident = fake(faker, "id", "apirak.c")
    assert re.fullmatch(r"[a-z0-9]{8}", ident), ident


def test_date_variants():
    faker = Faker(random.Random(1))

    plain = fake(faker, "date", "1990-05-01")
    assert DATE.match(plain), plain
    assert 1950 <= int(plain[:4]) <= 2005

    stamped = fake(faker, "date", "1990-05-01 10:11:12")
    assert stamped.endswith(" 10:11:12"), stamped
    assert DATE.match(stamped[:10]), stamped
    assert 1950 <= int(stamped[:4]) <= 2005

    assert fake(faker, "date", "0000-00-00") == "0000-00-00"

    loose = fake(faker, "date", "c. 1980")
    assert DATE.match(loose), loose
    assert 1950 <= int(loose[:4]) <= 2005


def test_json_ip_null_empty():
    faker = Faker(random.Random(1))
    assert fake(faker, "json", '[{"id": 1}]') == "[]"
    assert fake(faker, "json", '{"a": 1}') == "{}"

    ip = fake(faker, "ip", "10.0.0.7")
    assert ip.startswith("192.0.2.")

    assert fake(faker, "null", "secret") is None
    assert fake(faker, "empty", "secret") == ""


def test_password_bcrypt():
    original = "$2a$08$pJ68fbzb53/sdyZ5Cdc.Ge1KGZ8Dwu4H1TSpyK49BEPsH7SN/qHBO"
    value = fake(Faker(random.Random(1)), "password", original)
    assert value.startswith("$2a$08$")
    assert len(value) == 60
    assert re.fullmatch(r"[./A-Za-z0-9]{53}", value[7:])
    assert value != original


def test_password_django():
    original = "pbkdf2_sha256$870000$abc$XYZ="
    value = fake(Faker(random.Random(1)), "password", original)
    assert value.startswith("pbkdf2_sha256$870000$abc$")
    assert len(value) == len(original)
    assert value != original


def test_password_hex():
    original = "ab" * 64
    value = fake(Faker(random.Random(1)), "password", original)
    assert re.fullmatch(r"[0-9a-f]{128}", value)
    assert value != original


def test_max_len():
    faker = Faker(random.Random(1))

    text = fake(faker, "text", "x" * 500, max_len=30)
    assert len(text) <= 30

    email = fake(faker, "email", "apirak@example.com", max_len=20)
    assert re.search(r"@.+\.invalid$", email), email
    assert len(email) <= 20


def test_unique_grows():
    faker = Faker(random.Random(1))
    seen = set()
    for _ in range(500):
        value = fake(
            faker,
            "digits",
            "12",
            key="borrowers.cardnumber",
            max_len=10,
            unique=True,
        )
        assert value not in seen, value
        assert value.isdigit()
        assert 1 <= len(value) <= 10
        seen.add(value)


def test_unique_exhausted():
    faker = Faker(random.Random(1))
    for _ in range(10):
        fake(faker, "digits", "1", key="t.c", max_len=1, unique=True)
    with pytest.raises(DumpFormatError):
        fake(faker, "digits", "1", key="t.c", max_len=1, unique=True)


def test_password_unknown_format_fully_replaced():
    faker = Faker(random.Random(3))
    for original in ("my$ecretPass", "plain-password", "$", "abc$"):
        value = faker.fake(Rule("password"), original, key="t.p")
        assert value != original
        assert "ecret" not in value and not value.startswith("my")


def test_date_drops_non_time_suffix():
    faker = Faker(random.Random(4))
    value = faker.fake(Rule("date"), "1990-05-01 สมชาย ใจดี", key="t.d")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
    value = faker.fake(Rule("date"), "1990-05-01T10:11:12+07:00", key="t.d")
    assert value.endswith("T10:11:12+07:00")
