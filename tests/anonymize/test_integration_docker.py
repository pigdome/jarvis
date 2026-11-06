"""Docker integration: restore round-trips, poison pipelines and direct mode.

Every test here uses the throwaway ``mariadb:11`` / ``postgres:16`` containers
that ``conftest.py`` starts for this session and the synthetic dumps under
``tests/fixtures/anonymize``.  No other container and no production database
is touched.
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from conftest import (  # noqa: E402
    MYSQL_DUMP,
    PG_DUMP,
    create_db,
    engine_of,
)

from jarvis.anonymize.direct import run_direct  # noqa: E402
from jarvis.anonymize.errors import DumpFormatError  # noqa: E402
from jarvis.anonymize.profile import load_profile  # noqa: E402
from jarvis.anonymize.stream import POISON_SQL, run_stream  # noqa: E402

pytestmark = pytest.mark.docker

SEED_BORROWERS = 3007  # 7 hand-written rows + 3000 filler rows
SEED_ISSUES = 3

PLAINTEXT_PASSWORD = "my$ecretPass"
BCRYPT_PASSWORD = (
    "$2a$08$pJ68fbzb53/sdyZ5Cdc.Ge1KGZ8Dwu4H1TSpyK49BEPsH7SN/qHBO"
)
PBKDF2_PASSWORD = "pbkdf2_sha256$870000$abc$XYZ="
PBKDF2_PREFIX = "pbkdf2_sha256$870000$abc$"

# A COPY block for a ruled table whose rows cannot be mapped: both registry
# tables are missing, so the rewriter must refuse it and poison the output.
COPY_BEFORE_REGISTRY = (
    b"COPY public.metadatavalue"
    b" (metadata_value_id, resource_id, metadata_field_id, text_value,"
    b" text_lang, place) FROM stdin;\n"
    b"1\t00000000-0000-4000-8000-000000000000\t1\tSomchai\t\\N\t0\n"
    b"\\.\n"
)


# -- client helpers --------------------------------------------------------


def client_with_db(client: list[str], db: str) -> list[str]:
    cmd = [*client]
    if engine_of(client) == "mysql":
        cmd.append(db)
    else:
        cmd.extend(["-d", db])
    return cmd


def run_sql(
    client: list[str],
    db: str,
    payload: bytes,
    *,
    on_error_stop: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    cmd = [*client]
    if not on_error_stop and "ON_ERROR_STOP=1" in cmd:
        index = cmd.index("ON_ERROR_STOP=1")
        if index and cmd[index - 1] == "-v":
            del cmd[index - 1 : index + 1]
    return subprocess.run(
        client_with_db(cmd, db), input=payload, capture_output=True
    )


def query(client: list[str], db: str, sql: str) -> list[list[str]]:
    if engine_of(client) == "mysql":
        cmd = [*client, "-B", "-N", "-e", sql, db]
    else:
        cmd = [*client, "-A", "-t", "-F", "\t", "-d", db, "-c", sql]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return [line.split("\t") for line in result.stdout.splitlines()]


def scalar(client: list[str], db: str, sql: str) -> str:
    rows = query(client, db, sql)
    assert rows, f"no rows for query: {sql}"
    return rows[0][0]


def stderr_of(result: subprocess.CompletedProcess[bytes]) -> str:
    return result.stderr.decode("utf-8", "replace")


def hex_of(value: str) -> str:
    return value.encode("utf-8").hex().upper()


def restore(client: list[str], db: str, dump: Path) -> None:
    create_db(client, db)
    result = run_sql(client, db, dump.read_bytes())
    assert result.returncode == 0, stderr_of(result)


# -- stream mode: anonymize, then restore for real -------------------------


def test_mysql_stream_restore(mariadb_container):
    db = "anon_stream"
    create_db(mariadb_container, db)
    out = io.BytesIO()

    report = run_stream(
        load_profile("koha"), io.BytesIO(MYSQL_DUMP.read_bytes()), out
    )
    restore_result = run_sql(mariadb_container, db, out.getvalue())

    assert restore_result.returncode == 0, stderr_of(restore_result)
    assert report.stats("borrowers").rows == SEED_BORROWERS

    assert (
        scalar(mariadb_container, db, "SELECT COUNT(*) FROM borrowers")
        == str(SEED_BORROWERS)
    )
    assert (
        scalar(
            mariadb_container,
            db,
            "SELECT COUNT(DISTINCT cardnumber) FROM borrowers",
        )
        == str(SEED_BORROWERS)
    )

    # HEX() keeps the Thai literals out of the client's character set.
    names = ", ".join(
        f"'{hex_of(value)}'" for value in ("สมชาย", "ใจดี", "O'Brien")
    )
    assert (
        scalar(
            mariadb_container,
            db,
            "SELECT COUNT(*) FROM borrowers"
            f" WHERE HEX(firstname) IN ({names}) OR HEX(surname) IN ({names})",
        )
        == "0"
    )
    emails = ", ".join(
        f"'{value}'"
        for value in (
            "somchai@example.ac.th",
            "patrick.obrien@example.ac.th",
            "anna.smith@example.ac.th",
        )
    )
    assert (
        scalar(
            mariadb_container,
            db,
            f"SELECT COUNT(*) FROM borrowers WHERE email IN ({emails})",
        )
        == "0"
    )

    # Foreign keys still resolve and the truncated table is empty.
    assert (
        scalar(
            mariadb_container,
            db,
            "SELECT COUNT(*) FROM issues i"
            " JOIN borrowers b USING (borrowernumber)",
        )
        == str(SEED_ISSUES)
    )
    assert (
        scalar(mariadb_container, db, "SELECT COUNT(*) FROM sessions") == "0"
    )


def test_pg_stream_restore(pg_container):
    baseline_db = "anon_pg_raw"
    dspace_db = "anon_dspace"
    room_db = "anon_room"
    raw = PG_DUMP.read_bytes()
    restore(pg_container, baseline_db, PG_DUMP)
    create_db(pg_container, dspace_db)
    create_db(pg_container, room_db)

    dspace_out = io.BytesIO()
    run_stream(load_profile("dspace"), io.BytesIO(raw), dspace_out)
    dspace_result = run_sql(pg_container, dspace_db, dspace_out.getvalue())

    assert dspace_result.returncode == 0, stderr_of(dspace_result)
    assert scalar(pg_container, dspace_db, "SELECT count(*) FROM eperson") == "4"
    assert (
        scalar(
            pg_container,
            dspace_db,
            "SELECT count(*) FROM eperson WHERE email LIKE '%.invalid'",
        )
        == "2"
    )
    assert (
        scalar(
            pg_container,
            dspace_db,
            "SELECT count(*) FROM eperson WHERE email IS NULL",
        )
        == "1"
    )
    assert (
        scalar(
            pg_container,
            dspace_db,
            "SELECT count(*) FROM eperson WHERE email = ''",
        )
        == "1"
    )
    assert (
        scalar(
            pg_container,
            dspace_db,
            "SELECT count(DISTINCT email) FROM eperson"
            " WHERE email IS NOT NULL AND email <> ''",
        )
        == "2"
    )

    uuids = (
        "SELECT string_agg(uuid::text, ',' ORDER BY uuid) FROM eperson"
    )
    assert scalar(pg_container, dspace_db, uuids) == scalar(
        pg_container, baseline_db, uuids
    )

    # dc.title (5) and dc.contributor.author (6) are public, not personal.
    for value_id in (9, 10):
        digest = (
            "SELECT md5(text_value) FROM metadatavalue"
            f" WHERE metadata_value_id = {value_id}"
        )
        assert scalar(pg_container, dspace_db, digest) == scalar(
            pg_container, baseline_db, digest
        )
    for value_id in (1, 2, 6, 7):
        digest = (
            "SELECT md5(text_value) FROM metadatavalue"
            f" WHERE metadata_value_id = {value_id}"
        )
        assert scalar(pg_container, dspace_db, digest) != scalar(
            pg_container, baseline_db, digest
        )

    room_out = io.BytesIO()
    run_stream(load_profile("room_reservation"), io.BytesIO(raw), room_out)
    room_result = run_sql(pg_container, room_db, room_out.getvalue())

    assert room_result.returncode == 0, stderr_of(room_result)
    assert (
        scalar(pg_container, room_db, "SELECT count(*) FROM django_session")
        == "0"
    )
    assert (
        scalar(pg_container, room_db, "SELECT count(*) FROM booking_actionlog")
        == "0"
    )
    assert (
        scalar(
            pg_container,
            room_db,
            "SELECT count(*) FROM booking_booking b"
            " JOIN booking_patron p ON p.uuid = b.patron_id",
        )
        == "2"
    )
    assert (
        scalar(
            pg_container,
            room_db,
            "SELECT count(*) FROM booking_patron"
            " WHERE email LIKE '%.invalid'",
        )
        == "2"
    )
    assert (
        scalar(
            pg_container,
            room_db,
            "SELECT count(*) FROM booking_patron"
            " WHERE patron_id IN"
            " ('STAFF0001', 'STUDENT-2024-0002', 'BACKSLASH01')",
        )
        == "0"
    )


# -- poison: a failure halfway through must break the restore --------------


def test_mysql_poison_fails_pipeline(mariadb_container):
    db = "anon_mysql_poison"
    create_db(mariadb_container, db)
    data = MYSQL_DUMP.read_bytes()
    broken = (
        data[: len(data) // 2]
        + b"\nINSERT INTO `borrowers` (`x`) VALUES (1);\n"
    )
    out = io.BytesIO()

    with pytest.raises(DumpFormatError):
        run_stream(load_profile("koha"), io.BytesIO(broken), out)

    assert out.getvalue().endswith(POISON_SQL)
    result = run_sql(mariadb_container, db, out.getvalue())
    assert result.returncode != 0


def test_pg_poison_fails_pipeline(pg_container):
    db = "anon_pg_poison"
    create_db(pg_container, db)
    out = io.BytesIO()

    with pytest.raises(DumpFormatError):
        run_stream(load_profile("dspace"), io.BytesIO(COPY_BEFORE_REGISTRY), out)

    assert POISON_SQL in out.getvalue()
    # `jarvis db psql` does not set ON_ERROR_STOP; the poison turns it on.
    result = run_sql(
        pg_container, db, out.getvalue(), on_error_stop=False
    )
    assert result.returncode != 0, stderr_of(result)


def test_pg_poison_fails_pipeline_inside_copy(pg_container):
    db = "anon_pg_poison_copy"
    create_db(pg_container, db)
    schema = (
        b"CREATE TABLE eperson (uuid uuid PRIMARY KEY, email varchar(64),"
        b" netid varchar(64), password varchar(128), salt varchar(32),"
        b" session_salt varchar(32));\n"
    )
    created = run_sql(pg_container, db, schema)
    assert created.returncode == 0, stderr_of(created)
    # A valid COPY header and one row, then a row with too few fields: the
    # header was already emitted, so the poison has to close the open COPY
    # before it can force ON_ERROR_STOP.
    broken = (
        b"COPY public.eperson"
        b" (uuid, email, netid, password, salt, session_salt) FROM stdin;\n"
        b"11111111-1111-4111-8111-111111111111"
        b"\tsomchai@example.ac.th\tsomchai\thash\tsalt\t\\N\n"
        b"22222222-2222-4222-8222-222222222222\tonly-two-fields\n"
    )
    out = io.BytesIO()

    with pytest.raises(DumpFormatError):
        run_stream(load_profile("dspace"), io.BytesIO(broken), out)

    poison = out.getvalue()
    assert (
        poison.index(b"\\.\n")
        < poison.index(b"\\set ON_ERROR_STOP on\n")
        < poison.index(POISON_SQL)
    )
    result = run_sql(pg_container, db, poison, on_error_stop=False)
    assert result.returncode != 0, stderr_of(result)
    # The row emitted before the failure was pseudonymized and the COPY was
    # closed properly, so psql restored exactly that one row.
    assert scalar(pg_container, db, "SELECT count(*) FROM eperson") == "1"
    assert (
        scalar(
            pg_container,
            db,
            "SELECT count(*) FROM eperson WHERE email LIKE '%.invalid'",
        )
        == "1"
    )


# -- direct mode -----------------------------------------------------------


def test_mysql_direct_mode(mariadb_container):
    db = "anon_mysql_direct"
    restore(mariadb_container, db, MYSQL_DUMP)

    insert = f"""\
INSERT INTO borrowers
  (cardnumber, userid, surname, firstname, email, phone, dateofbirth,
   password, borrowernotes, sort1)
VALUES
  ('9900000001', 'plainpass', 'Plaintext', 'Password',
   'plaintext@example.ac.th', '0899999001', '1984-04-05',
   '{PLAINTEXT_PASSWORD}', 'plain text password', 'S990001'),
  ('9900000002', 'hashpass', 'Hash', 'Prefix',
   'hash@example.ac.th', '0899999002', '1984-04-06',
   '{BCRYPT_PASSWORD}', 'bcrypt password', 'S990002');
"""
    inserted = run_sql(mariadb_container, db, insert.encode())
    assert inserted.returncode == 0, stderr_of(inserted)
    plain_id = scalar(
        mariadb_container,
        db,
        "SELECT borrowernumber FROM borrowers WHERE userid = 'plainpass'",
    )
    total = SEED_BORROWERS + 2

    run_direct(
        load_profile("koha"),
        "mysql",
        db,
        client=mariadb_container,
        assume_yes=True,
    )

    assert (
        scalar(mariadb_container, db, "SELECT COUNT(*) FROM borrowers")
        == str(total)
    )
    assert (
        scalar(
            mariadb_container,
            db,
            "SELECT COUNT(DISTINCT cardnumber) FROM borrowers",
        )
        == str(total)
    )
    names = ", ".join(
        f"'{hex_of(value)}'" for value in ("สมชาย", "ใจดี", "O'Brien")
    )
    assert (
        scalar(
            mariadb_container,
            db,
            "SELECT COUNT(*) FROM borrowers"
            f" WHERE HEX(firstname) IN ({names}) OR HEX(surname) IN ({names})",
        )
        == "0"
    )
    assert (
        scalar(mariadb_container, db, "SELECT COUNT(*) FROM sessions") == "0"
    )

    plaintext = scalar(
        mariadb_container,
        db,
        f"SELECT password FROM borrowers WHERE borrowernumber = {plain_id}",
    )
    assert not plaintext.startswith("my")
    assert "ecret" not in plaintext
    assert re.fullmatch(r"[0-9a-f]+", plaintext)

    # Every other non-empty hash is a bcrypt value whose prefix survived.
    bcrypt = (
        "password IS NOT NULL AND password <> '' AND password LIKE '$2a$08$%'"
    )
    assert (
        scalar(
            mariadb_container,
            db,
            f"SELECT COUNT(*) FROM borrowers WHERE {bcrypt}",
        )
        == str(SEED_BORROWERS - 1)
    )
    assert (
        scalar(
            mariadb_container,
            db,
            f"SELECT COUNT(*) FROM borrowers"
            f" WHERE {bcrypt} AND CHAR_LENGTH(password) = 60",
        )
        == str(SEED_BORROWERS - 1)
    )


def test_pg_direct_mode(pg_container):
    db = "anon_pg_direct"
    restore(pg_container, db, PG_DUMP)

    insert = f"""\
INSERT INTO eperson (uuid, email, netid, password, salt, session_salt) VALUES
  ('55555555-5555-4555-8555-555555555555', 'plaintext@example.ac.th',
   'plaintext', '{PLAINTEXT_PASSWORD}', repeat('deadbeef', 4), NULL),
  ('66666666-6666-4666-8666-666666666666', 'pbkdf2@example.ac.th',
   'pbkdf2user', '{PBKDF2_PASSWORD}', repeat('cafebabe', 4), NULL);
"""
    inserted = run_sql(pg_container, db, insert.encode())
    assert inserted.returncode == 0, stderr_of(inserted)

    title_before = scalar(
        pg_container,
        db,
        "SELECT md5(text_value) FROM metadatavalue WHERE metadata_value_id = 9",
    )
    author_before = scalar(
        pg_container,
        db,
        "SELECT md5(text_value) FROM metadatavalue WHERE metadata_value_id = 10",
    )
    run_direct(
        load_profile("dspace"),
        "psql",
        db,
        client=pg_container,
        assume_yes=True,
    )

    assert scalar(pg_container, db, "SELECT count(*) FROM eperson") == "6"
    assert (
        scalar(
            pg_container,
            db,
            "SELECT count(*) FROM eperson WHERE email LIKE '%.invalid'",
        )
        == "4"
    )
    emails = ", ".join(
        f"'{value}'"
        for value in (
            "somchai@example.ac.th",
            "patrick.obrien@example.ac.th",
            "plaintext@example.ac.th",
            "pbkdf2@example.ac.th",
        )
    )
    assert (
        scalar(
            pg_container,
            db,
            f"SELECT count(*) FROM eperson WHERE email IN ({emails})",
        )
        == "0"
    )
    # The uuid primary key of the seed row is untouched.
    assert (
        scalar(
            pg_container,
            db,
            "SELECT count(*) FROM eperson WHERE uuid ="
            " '11111111-1111-4111-8111-111111111111'",
        )
        == "1"
    )

    plaintext = scalar(
        pg_container,
        db,
        "SELECT password FROM eperson"
        " WHERE uuid = '55555555-5555-4555-8555-555555555555'",
    )
    assert not plaintext.startswith("my")
    assert "ecret" not in plaintext
    assert re.fullmatch(r"[0-9a-f]+", plaintext)

    pbkdf2 = scalar(
        pg_container,
        db,
        "SELECT password FROM eperson"
        " WHERE uuid = '66666666-6666-4666-8666-666666666666'",
    )
    assert pbkdf2.startswith(PBKDF2_PREFIX)
    assert pbkdf2 != PBKDF2_PASSWORD
    assert re.fullmatch(r"[0-9a-f]+", pbkdf2[len(PBKDF2_PREFIX) :])

    # The 128-character hex DSpace hashes keep their full length.
    assert (
        scalar(
            pg_container,
            db,
            "SELECT count(*) FROM eperson"
            " WHERE length(password) = 128"
            " AND uuid <> '55555555-5555-4555-8555-555555555555'"
            " AND uuid <> '66666666-6666-4666-8666-666666666666'",
        )
        == "4"
    )

    # Public metadata is byte-identical; the booking FK still resolves.
    assert (
        scalar(
            pg_container,
            db,
            "SELECT md5(text_value) FROM metadatavalue"
            " WHERE metadata_value_id = 9",
        )
        == title_before
    )
    assert (
        scalar(
            pg_container,
            db,
            "SELECT md5(text_value) FROM metadatavalue"
            " WHERE metadata_value_id = 10",
        )
        == author_before
    )
    assert (
        scalar(
            pg_container,
            db,
            "SELECT count(*) FROM booking_booking b"
            " JOIN booking_patron p ON p.uuid = b.patron_id",
        )
        == "2"
    )


def test_pg_direct_mode_room_reservation(pg_container):
    db = "anon_pg_direct_room"
    restore(pg_container, db, PG_DUMP)
    name_before = scalar(
        pg_container,
        db,
        "SELECT md5(name) FROM booking_patron"
        " WHERE uuid = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'",
    )

    run_direct(
        load_profile("room_reservation"),
        "psql",
        db,
        client=pg_container,
        assume_yes=True,
    )

    assert (
        scalar(pg_container, db, "SELECT count(*) FROM django_session") == "0"
    )
    assert (
        scalar(pg_container, db, "SELECT count(*) FROM booking_actionlog") == "0"
    )
    # patron_id is UNIQUE, so the two-pass update must not collide.
    assert (
        scalar(
            pg_container,
            db,
            "SELECT count(*) FROM booking_patron",
        )
        == "3"
    )
    assert (
        scalar(
            pg_container,
            db,
            "SELECT count(DISTINCT patron_id) FROM booking_patron",
        )
        == "3"
    )
    assert (
        scalar(
            pg_container,
            db,
            "SELECT count(*) FROM booking_booking b"
            " JOIN booking_patron p ON p.uuid = b.patron_id",
        )
        == "2"
    )
    assert (
        scalar(
            pg_container,
            db,
            "SELECT count(*) FROM booking_booking"
            " WHERE attendance_list IS NOT NULL",
        )
        == "2"
    )
    assert (
        scalar(
            pg_container,
            db,
            "SELECT md5(name) FROM booking_patron"
            " WHERE uuid = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'",
        )
        != name_before
    )
