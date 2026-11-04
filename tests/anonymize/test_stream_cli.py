"""Tests for the stream driver and the ``jarvis db anonymize`` CLI."""

import io
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from conftest import MYSQL_DUMP, PG_DUMP  # noqa: E402

from jarvis.anonymize.errors import DumpFormatError  # noqa: E402
from jarvis.anonymize.profile import load_profile  # noqa: E402
from jarvis.anonymize.report import PDPA_NOTE  # noqa: E402
from jarvis.anonymize.stream import POISON_SQL, run_stream  # noqa: E402
from jarvis.commands.db import app as db_app  # noqa: E402

runner = CliRunner()

# A COPY block for a table that has by_metadata_field rules, before the two
# registry tables were read: the rewriter must refuse it.
COPY_BEFORE_REGISTRY = (
    b"COPY public.metadatavalue (metadata_id, metadata_field_id, text_value)"
    b" FROM stdin;\n"
    b"1\t5\tSomchai Jaidee\n"
    b"\\.\n"
)

SMALL_MYSQL_DUMP = (
    b"CREATE TABLE `t` (\n"
    b"  `id` int(11) NOT NULL\n"
    b") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n"
    b"INSERT INTO `t` VALUES (1);\n"
)

TMP_PROFILE = """\
[profile]
name = "demo"
engine = "mysql"
description = "temporary profile"
"""


def invoke(args, stdin=b""):
    return runner.invoke(db_app, ["anonymize", *args], input=stdin)


def insert_statement(data, table):
    """Return every extended INSERT statement of ``table``."""
    marker = f"INSERT INTO `{table}`".encode()
    chunks = []
    inside = False
    for line in data.splitlines(keepends=True):
        if line.startswith(marker):
            inside = True
        if inside:
            chunks.append(line)
            if line.rstrip().endswith(b";"):
                inside = False
    return b"".join(chunks)


def borrower_count(data):
    # Every tuple opens with "(" and no profile value ever contains one, so the
    # count stays comparable between the input and the rewritten statement.
    return insert_statement(data, "borrowers").count(b"(")


def real_restrict_line():
    for line in PG_DUMP.read_bytes().splitlines(keepends=True):
        if line.startswith(b"\\restrict "):
            return line
    raise AssertionError("fixture has no \\restrict line")


def copy_rows(data, table):
    marker = f"COPY public.{table} ".encode()
    rows = []
    inside = False
    for line in data.splitlines():
        if line.startswith(marker):
            inside = True
            continue
        if inside:
            if line == b"\\.":
                return rows
            rows.append(line)
    raise AssertionError(f"no COPY block for {table}")


def test_run_stream_fills_report_and_rewrites():
    data = MYSQL_DUMP.read_bytes()
    out = io.BytesIO()

    report = run_stream(load_profile("koha"), io.BytesIO(data), out)

    assert report.profile == "koha"
    assert report.bytes_in == len(data)
    assert report.seconds > 0
    assert b"somchai@example.ac.th" not in insert_statement(out.getvalue(), "borrowers")
    assert report.stats("borrowers").rows == borrower_count(data)


def test_run_stream_poison_before_raising():
    out = io.BytesIO()

    with pytest.raises(DumpFormatError):
        run_stream(load_profile("koha"), io.BytesIO(PG_DUMP.read_bytes()), out)

    assert out.getvalue().endswith(POISON_SQL)


def test_stream_koha_fixture():
    result = invoke(["-p", "koha"], MYSQL_DUMP.read_bytes())

    assert result.exit_code == 0, result.stderr
    stdout = result.stdout_bytes
    rewritten = insert_statement(stdout, "borrowers")
    assert rewritten
    assert "สมชาย".encode() not in rewritten
    assert b"somchai@example.ac.th" not in rewritten
    assert b"patrick.obrien@example.ac.th" not in rewritten
    assert borrower_count(stdout) == borrower_count(MYSQL_DUMP.read_bytes())
    assert PDPA_NOTE in result.stderr


def test_stream_wrong_engine_input():
    result = invoke(["-p", "koha"], PG_DUMP.read_bytes())

    assert result.exit_code == 2
    assert result.stdout_bytes.endswith(POISON_SQL)
    assert "set -o pipefail" in result.stderr


def test_stream_dspace_fixture():
    data = PG_DUMP.read_bytes()

    result = invoke(["-p", "dspace"], data)

    assert result.exit_code == 0, result.stderr
    out = result.stdout_bytes
    restrict = real_restrict_line()
    key = restrict.split()[1]
    assert restrict in out
    assert b"\\unrestrict " + key + b"\n" in out
    epersons = copy_rows(out, "eperson")
    assert len(epersons) == len(copy_rows(data, "eperson"))
    assert b"example.ac.th" not in b"\n".join(epersons)
    assert PDPA_NOTE in result.stderr


def test_poison_pg_inside_copy():
    result = invoke(["-p", "dspace"], COPY_BEFORE_REGISTRY)

    assert result.exit_code == 2
    out = result.stdout_bytes
    assert POISON_SQL in out
    assert out.index(b"\\.\n") < out.index(b"\\set ON_ERROR_STOP on\n") < out.index(
        POISON_SQL
    )


def test_poison_pg_unrestricts_real_fixture_key():
    restrict = real_restrict_line()
    key = restrict.split()[1]

    result = invoke(["-p", "dspace"], restrict + COPY_BEFORE_REGISTRY)

    assert result.exit_code == 2
    out = result.stdout_bytes
    assert b"\\unrestrict " + key + b"\n" in out
    assert out.index(b"\\unrestrict " + key) < out.index(b"\\set ON_ERROR_STOP on\n")
    assert out.index(b"\\set ON_ERROR_STOP on\n") < out.index(POISON_SQL)


def test_type_mismatch():
    result = invoke(["-p", "koha", "-t", "psql", "-d", "x"])

    assert result.exit_code == 1
    assert "koha" in result.stderr


def test_direct_mode_not_implemented():
    result = invoke(["-p", "koha", "-t", "mysql", "-d", "koha_spu"])

    assert result.exit_code == 1
    assert "direct mode not implemented yet" in result.stderr


def test_type_without_database_rejected():
    result = invoke(["-p", "koha", "-t", "mysql"])

    assert result.exit_code == 1
    assert result.stdout_bytes == b""


def test_list():
    result = invoke(["--list"])

    assert result.exit_code == 0
    assert result.stdout_bytes == b""
    for name in ("koha", "dspace", "room_reservation", "linebrarian"):
        assert name in result.stderr
    assert "mysql" in result.stderr and "psql" in result.stderr


def test_profile_file(tmp_path):
    path = tmp_path / "demo.toml"
    path.write_text(TMP_PROFILE, encoding="utf-8")

    result = invoke(["--profile-file", str(path)], SMALL_MYSQL_DUMP)

    assert result.exit_code == 0, result.stderr
    assert PDPA_NOTE in result.stderr


def test_profile_and_profile_file_together_rejected(tmp_path):
    path = tmp_path / "demo.toml"
    path.write_text(TMP_PROFILE, encoding="utf-8")

    result = invoke(
        ["-p", "koha", "--profile-file", str(path)], SMALL_MYSQL_DUMP
    )

    assert result.exit_code == 1
    assert result.stdout_bytes == b""


def test_no_profile_rejected():
    result = invoke([], SMALL_MYSQL_DUMP)

    assert result.exit_code == 1
    assert result.stdout_bytes == b""


def test_quiet():
    result = invoke(["-p", "koha", "-q"], MYSQL_DUMP.read_bytes())

    assert result.exit_code == 0
    assert PDPA_NOTE not in result.stderr


def test_unexpected_error_still_poisons(monkeypatch):
    import io

    from jarvis.anonymize import stream as stream_mod
    from jarvis.anonymize.errors import DumpFormatError as DFE
    from jarvis.anonymize.profile import load_profile as lp

    def boom(self, line):
        raise KeyError("bug")

    monkeypatch.setattr(stream_mod.MysqlRewriter, "feed", boom)
    out = io.BytesIO()
    with pytest.raises(DFE):
        stream_mod.run_stream(lp("koha"), io.BytesIO(b"-- x\n"), out)
    assert out.getvalue().endswith(stream_mod.POISON_SQL)
