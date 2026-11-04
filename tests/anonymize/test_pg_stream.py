"""Tests for the pg_dump COPY rewriter, using the synthetic real-dump fixture."""

import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from conftest import PG_DUMP  # noqa: E402

from jarvis.anonymize.errors import DumpFormatError  # noqa: E402
from jarvis.anonymize.pg_stream import PgRewriter  # noqa: E402
from jarvis.anonymize.profile import load_profile  # noqa: E402
from jarvis.anonymize.report import Report  # noqa: E402
from jarvis.anonymize.strategies import Faker  # noqa: E402

NOTE_DUMP = (
    b"CREATE TABLE public.note (\n"
    b"    id integer NOT NULL,\n"
    b"    body text,\n"
    b"    email character varying(64)\n"
    b");\n"
    b"COPY public.note (id, body, email) FROM stdin;\n"
    b"1\ta\\tb\\nc\\\\d\\101\\x42\treal@person.th\n"
    b"2\t\\N\t\\N\n"
    b"\\.\n"
)

NARROW_DUMP = (
    b"CREATE TABLE public.eperson (\n"
    b"    uuid uuid NOT NULL,\n"
    b"    email character varying(15),\n"
    b"    login_email text\n"
    b");\n"
    b"COPY public.eperson (uuid, email, login_email) FROM stdin;\n"
    b"11111111-1111-4111-8111-111111111111\treal@person.th\talt@person.th\n"
    b"\\.\n"
)


def make(profile="dspace", seed=1):
    return PgRewriter(
        load_profile(profile),
        Faker(random.Random(seed)),
        Report(profile=profile),
    )


def rewrite(data: bytes, profile="dspace", seed=1):
    rewriter = make(profile, seed)
    chunks = [rewriter.feed(line) for line in data.splitlines(keepends=True)]
    rewriter.finish()
    return b"".join(chunk for chunk in chunks if chunk is not None), rewriter


def copy_rows(data: bytes, table: str) -> list[bytes]:
    """Return the data rows of ``table``'s COPY block, without line endings."""
    header = ("COPY " + table).encode()
    rows: list[bytes] = []
    inside = False
    for line in data.splitlines():
        if line.startswith(header):
            inside = True
            continue
        if inside:
            if line == b"\\.":
                break
            rows.append(line)
    return rows


def copy_block(data: bytes, table: str) -> list[bytes]:
    """Return every line of ``table``'s COPY block, header and terminator too."""
    header = ("COPY " + table).encode()
    lines: list[bytes] = []
    inside = False
    for line in data.splitlines(keepends=True):
        if line.startswith(header):
            inside = True
        if inside:
            lines.append(line)
            if line.rstrip(b"\r\n") == b"\\.":
                break
    return lines


def write_profile(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "profile.toml"
    path.write_text(body, encoding="utf-8")
    return path


def rewrite_with(tmp_path, toml: str, data: bytes, name="t"):
    rewriter = PgRewriter(
        load_profile(path=write_profile(tmp_path, toml)),
        Faker(random.Random(1)),
        Report(profile=name),
    )
    chunks = [rewriter.feed(line) for line in data.splitlines(keepends=True)]
    rewriter.finish()
    return b"".join(chunk for chunk in chunks if chunk is not None)


@pytest.mark.parametrize(
    ("profile", "targets", "truncated"),
    [
        ("dspace", {b"public.eperson", b"public.metadatavalue"}, set()),
        (
            "room_reservation",
            {
                b"public.booking_patron",
                b"public.booking_booking",
                b"public.booking_actionlog",
                b"public.django_session",
            },
            {b"public.booking_actionlog", b"public.django_session"},
        ),
    ],
)
def test_passthrough_unrelated_bytes(profile, targets, truncated):
    data = PG_DUMP.read_bytes()
    rewriter = make(profile)
    inside: bytes | None = None
    for line in data.splitlines(keepends=True):
        header = re.match(rb"COPY\s+(\S+)", line)
        if header is not None:
            inside = header.group(1) if header.group(1) in targets else None
            assert rewriter.feed(line) == line
        elif inside is not None:
            if line.rstrip(b"\r\n") == b"\\.":
                assert rewriter.feed(line) == line
                inside = None
            elif inside in truncated:
                assert rewriter.feed(line) is None
            else:
                assert rewriter.feed(line) is not None
        else:
            assert rewriter.feed(line) == line
    rewriter.finish()


def test_eperson_rewritten():
    data = PG_DUMP.read_bytes()
    output, rewriter = rewrite(data, "dspace")
    before = copy_rows(data, "public.eperson")
    after = copy_rows(output, "public.eperson")

    assert len(after) == len(before)
    emails: list[bytes] = []
    for old, new in zip(before, after):
        old_fields = old.split(b"\t")
        new_fields = new.split(b"\t")
        assert new_fields[0] == old_fields[0], "uuid must be kept"
        if new_fields[1] in (b"\\N", b""):
            assert new_fields[1] == old_fields[1]
            continue
        assert new_fields[1].endswith(b".invalid")
        emails.append(new_fields[1])

    assert len(emails) == len(set(emails))
    rows = b"\n".join(after)
    for secret in (b"somchai@example.ac.th", b"patrick.obrien@example.ac.th"):
        assert secret not in rows
    assert rewriter.report.stats("eperson").rows == len(before)


def test_metadata_field_targeting():
    data = PG_DUMP.read_bytes()
    output, _ = rewrite(data, "dspace")
    before = copy_rows(data, "public.metadatavalue")
    after = copy_rows(output, "public.metadatavalue")

    assert len(after) == len(before)
    for old, new in zip(before, after):
        fields = old.split(b"\t")
        field_id = fields[2]
        if field_id in (b"1", b"2"):
            assert new != old, f"field {field_id!r} should be rewritten"
            text = new.split(b"\t")[3]
            assert all(byte < 0x80 for byte in text), text
        if field_id in (b"5", b"6"):
            assert new == old, f"field {field_id!r} must stay unchanged"


def test_metadata_before_registry_rejected():
    data = (
        b"COPY public.metadatavalue"
        b" (metadata_value_id, resource_id, metadata_field_id, text_value,"
        b" text_lang, place) FROM stdin;\n"
        b"1\t11111111-1111-4111-8111-111111111111\t1\tPatrick\t\\N\t0\n"
        b"\\.\n"
    )
    with pytest.raises(DumpFormatError):
        rewrite(data, "dspace")


def test_escapes_roundtrip(tmp_path):
    toml = (
        '[profile]\nname = "note"\nengine = "psql"\n\n'
        "[tables.note]\nemail = \"email\"\n"
    )
    output = rewrite_with(tmp_path, toml, NOTE_DUMP)

    before = copy_rows(NOTE_DUMP, "public.note")
    after = copy_rows(output, "public.note")
    assert after[0].split(b"\t")[1] == before[0].split(b"\t")[1]
    assert after[0].split(b"\t")[2].endswith(b".invalid")
    assert after[1].split(b"\t")[1] == b"\\N"


def test_escaped_value_rewritten(tmp_path):
    toml = (
        '[profile]\nname = "note"\nengine = "psql"\n\n'
        "[tables.note]\nbody = \"text\"\n"
    )
    output = rewrite_with(tmp_path, toml, NOTE_DUMP)

    body = copy_rows(output, "public.note")[0].split(b"\t")[1]
    assert body != copy_rows(NOTE_DUMP, "public.note")[0].split(b"\t")[1]
    assert b"\t" not in body
    assert b"\n" not in body


def test_jsonb_and_session_truncate():
    data = PG_DUMP.read_bytes()
    output, rewriter = rewrite(data, "room_reservation")

    for row in copy_rows(output, "public.booking_booking"):
        assert row.split(b"\t")[4] == b"[]"

    session = copy_block(output, "public.django_session")
    assert session[0].startswith(b"COPY public.django_session (")
    assert session[1] == b"\\.\n"
    assert len(session) == 2
    assert rewriter.report.stats("django_session").truncated_rows == 2
    assert len(copy_block(output, "public.booking_actionlog")) == 2


@pytest.mark.parametrize(
    ("profile", "statement"),
    [
        ("dspace", b"INSERT INTO public.eperson VALUES (1,'a@b.c');\n"),
        (
            "room_reservation",
            b"INSERT INTO public.django_session VALUES ('k','v','t');\n",
        ),
        ("dspace", b"COPY public.eperson TO stdout;\n"),
        ("dspace", b"COPY public.eperson FROM '/tmp/data.tsv';\n"),
    ],
)
def test_inserts_and_copies_rejected(profile, statement):
    rewriter = make(profile)
    with pytest.raises(DumpFormatError):
        rewriter.feed(statement)


def test_inserts_of_unruled_table_pass():
    rewriter = make("dspace")
    line = b"INSERT INTO public.other VALUES (1,'x');\n"
    assert rewriter.feed(line) == line


def test_restrict_key_captured():
    rewriter = make()
    line = b"\\restrict abc123\n"
    assert rewriter.feed(line) == line
    assert rewriter.restrict_key == "abc123"


def test_finish_no_copy():
    rewriter = make()
    rewriter.feed(b"SET statement_timeout = 0;\n")
    with pytest.raises(DumpFormatError):
        rewriter.finish()


def test_missing_and_suspicious_columns():
    output, rewriter = rewrite(NARROW_DUMP, "dspace")

    assert ("eperson", "netid") in rewriter.report.missing_columns
    assert ("eperson", "login_email") in rewriter.report.suspicious_columns
    assert ("eperson", "uuid") not in rewriter.report.suspicious_columns
    email = copy_rows(output, "public.eperson")[0].split(b"\t")[1]
    assert len(email) <= 15
    assert email.endswith(b".invalid")


def test_unless_absent_column_still_anonymizes(tmp_path):
    toml = (
        '[profile]\nname = "t"\nengine = "psql"\n\n'
        "[tables.note]\nemail = \"email\"\n\n"
        "[tables.note.unless]\ncode = [\"KEEP\"]\n"
    )
    data = (
        b"COPY public.note (id, email) FROM stdin;\n"
        b"1\treal@person.th\n"
        b"\\.\n"
    )
    output = rewrite_with(tmp_path, toml, data)
    assert b"real@person.th" not in output


def test_when_absent_column_ignored(tmp_path):
    toml = (
        '[profile]\nname = "t"\nengine = "psql"\n\n'
        "[tables.note]\nemail = \"email\"\n\n"
        "[tables.note.when]\ncode = [\"KEEP\"]\n"
    )
    data = (
        b"COPY public.note (id, email) FROM stdin;\n"
        b"1\treal@person.th\n"
        b"\\.\n"
    )
    output = rewrite_with(tmp_path, toml, data)
    assert b"real@person.th" not in output


def test_unless_matching_row_skipped(tmp_path):
    toml = (
        '[profile]\nname = "t"\nengine = "psql"\n\n'
        "[tables.note]\nemail = \"email\"\n\n"
        "[tables.note.unless]\ncode = [\"FACULTY\"]\n"
    )
    data = (
        b"COPY public.note (id, code, email) FROM stdin;\n"
        b"1\tFACULTY\tkeep@person.th\n"
        b"2\tCITIZENID\treal@person.th\n"
        b"\\.\n"
    )
    output = rewrite_with(tmp_path, toml, data)
    assert b"keep@person.th" in output
    assert b"real@person.th" not in output


def test_quoted_identifiers(tmp_path):
    toml = (
        '[profile]\nname = "t"\nengine = "psql"\n\n'
        "[tables.note]\nemail = \"email\"\n"
    )
    data = (
        b'CREATE TABLE "public"."note" (\n'
        b'    "id" integer NOT NULL,\n'
        b'    "email" character varying(30)\n'
        b");\n"
        b'COPY "public"."note" ("id", "email") FROM stdin;\n'
        b"1\treal@person.th\n"
        b"\\.\n"
    )
    output = rewrite_with(tmp_path, toml, data)
    assert b"real@person.th" not in output
    assert b'COPY "public"."note" ("id", "email") FROM stdin;' in output



def test_unterminated_create_rejected():
    rewriter = make()
    rewriter.feed(b"CREATE TABLE public.eperson (\n")
    rewriter.feed(b"    uuid uuid NOT NULL,\n")
    with pytest.raises(DumpFormatError):
        rewriter.feed(b"COPY public.eperson (uuid, email) FROM stdin;\n")


def test_create_open_at_end_rejected():
    rewriter = make()
    rewriter.feed(b"CREATE TABLE public.eperson (\n")
    with pytest.raises(DumpFormatError):
        rewriter.finish()


def test_lowercase_indented_copy_is_rewritten():
    rewriter = make()
    rewriter.feed(b"  copy public.eperson (uuid, email) from stdin;\n")
    out = rewriter.feed(b"11111111-1111-1111-1111-111111111111\treal@person.th\n")
    assert b"real@person.th" not in out


def test_unregistered_metadata_field_reported():
    _, rewriter = rewrite(PG_DUMP.read_bytes())
    # The fixture registers person.email but not person.telephone/birthDate.
    missing = rewriter.report.missing_columns
    assert ("metadatavalue", "person.telephone") in missing
    assert ("metadatavalue", "person.email") not in missing
