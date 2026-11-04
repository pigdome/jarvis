"""Tests for the mysqldump rewriter, using the synthetic real-dump fixture."""

import random
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from conftest import MYSQL_DUMP  # noqa: E402

from jarvis.anonymize.errors import DumpFormatError  # noqa: E402
from jarvis.anonymize.mysql_stream import MysqlRewriter  # noqa: E402
from jarvis.anonymize.profile import load_profile  # noqa: E402
from jarvis.anonymize.report import Report  # noqa: E402
from jarvis.anonymize.strategies import Faker  # noqa: E402

CREATE_BORROWERS = [
    b"CREATE TABLE `borrowers` (\n",
    b"  `borrowernumber` int(11) NOT NULL AUTO_INCREMENT,\n",
    b"  `email` varchar(100) DEFAULT NULL,\n",
    b"  PRIMARY KEY (`borrowernumber`)\n",
    b") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n",
]

TARGET_TABLES = (b"`borrowers`", b"`borrower_attributes`", b"`sessions`")


def make(profile="koha", seed=1):
    return MysqlRewriter(
        load_profile(profile),
        Faker(random.Random(seed)),
        Report(profile=profile),
    )


def rewrite(data: bytes, profile="koha", seed=1):
    rewriter = make(profile, seed)
    chunks = [rewriter.feed(line) for line in data.splitlines(keepends=True)]
    rewriter.finish()
    return b"".join(chunk for chunk in chunks if chunk), rewriter


def table_rows(data: bytes, table: str) -> list[bytes]:
    """Return the raw row lines of every INSERT statement for ``table``."""
    marker = f"INSERT INTO `{table}`".encode()
    rows: list[bytes] = []
    inside = False
    for line in data.splitlines():
        if line.startswith(marker):
            inside = True
            if line.rstrip().endswith(b";"):
                inside = False
            continue
        if inside:
            if line.startswith(b"("):
                rows.append(line)
            if line.rstrip().endswith(b";"):
                inside = False
    return rows


def borrowernumbers(rows: list[bytes]) -> list[bytes]:
    return [re.match(rb"\((\d+),", row).group(1) for row in rows]


def test_passthrough_unrelated_bytes():
    data = MYSQL_DUMP.read_bytes()
    rewriter = make()
    inside = False
    dropping = False
    for line in data.splitlines(keepends=True):
        if line.startswith(b"INSERT INTO "):
            header = line.split(b" VALUES")[0]
            inside = any(table in header for table in TARGET_TABLES)
            dropping = b"`sessions`" in header
        complete = line.rstrip().endswith(b";")
        chunk = rewriter.feed(line)
        if not inside:
            assert chunk == line
        elif dropping:
            assert chunk is None
        elif complete:
            assert chunk is not None
        else:
            assert chunk is None
        if inside and complete:
            inside = False
    rewriter.finish()


def test_borrowers_rewritten():
    data = MYSQL_DUMP.read_bytes()
    output, rewriter = rewrite(data)

    original_rows = table_rows(data, "borrowers")
    rows = table_rows(output, "borrowers")
    assert len(rows) == len(original_rows)
    assert output.count(b"INSERT INTO `borrowers`") == data.count(
        b"INSERT INTO `borrowers`"
    )
    assert borrowernumbers(rows) == borrowernumbers(original_rows)

    rewritten = b"\n".join(rows)
    for secret in (
        "สมชาย".encode(),
        "ใจดี".encode(),
        b"O\\'Brien",
        b"somchai@example.ac.th",
        b"patrick.obrien@example.ac.th",
        b"anna.smith@example.ac.th",
    ):
        assert secret not in rewritten, secret

    assert rewriter.report.stats("borrowers").rows == len(original_rows)


def test_null_and_empty_kept():
    output, _ = rewrite(MYSQL_DUMP.read_bytes())
    rows = {
        row.split(b",", 1)[0]: row.rstrip(b",;").rstrip()
        for row in table_rows(output, "borrowers")
    }

    assert rows[b"(5"].endswith(b",NULL,NULL,NULL,NULL,NULL,NULL)")

    row6 = rows[b"(6"]
    assert row6.endswith(b",'','','0000-00-00','','','')"), row6


def test_sessions_truncated():
    output, rewriter = rewrite(MYSQL_DUMP.read_bytes())

    assert b"INSERT INTO `sessions`" not in output
    assert rewriter.report.stats("sessions").truncated_rows == 3


def test_unique_cardnumber():
    output, _ = rewrite(MYSQL_DUMP.read_bytes())
    rows = table_rows(output, "borrowers")

    cardnumbers = [re.match(rb"\(\d+,'([^']*)'", row).group(1) for row in rows]
    assert len(cardnumbers) == len(set(cardnumbers))


def test_complete_insert_rejected():
    rewriter = make()
    for line in CREATE_BORROWERS:
        rewriter.feed(line)

    with pytest.raises(DumpFormatError):
        rewriter.feed(b"INSERT INTO `borrowers` (`borrowernumber`) VALUES (1);\n")


def test_insert_without_create_rejected():
    rewriter = make()
    with pytest.raises(DumpFormatError):
        rewriter.feed(b"INSERT INTO `borrowers` VALUES (1,'a@b.invalid');\n")


def test_finish_no_statements():
    rewriter = make()
    rewriter.feed(b"COPY public.x (a) FROM stdin;\n")
    with pytest.raises(DumpFormatError):
        rewriter.finish()


def test_missing_and_suspicious_columns():
    rewriter = make()
    for line in (
        b"CREATE TABLE `borrowers` (\n",
        b"  `borrowernumber` int(11) NOT NULL AUTO_INCREMENT,\n",
        b"  `nickname_email` varchar(100) DEFAULT NULL,\n",
        b"  PRIMARY KEY (`borrowernumber`)\n",
        b") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n",
    ):
        rewriter.feed(line)

    assert ("borrowers", "sort2") in rewriter.report.missing_columns
    assert ("borrowers", "nickname_email") in rewriter.report.suspicious_columns
    assert ("borrowers", "borrowernumber") not in rewriter.report.suspicious_columns


def test_unless_keep_code(tmp_path):
    profile = tmp_path / "unless.toml"
    profile.write_text(
        "[profile]\n"
        'name = "unless"\n'
        'engine = "mysql"\n'
        "\n"
        "[tables.borrower_attributes]\n"
        'attribute = "id"\n'
        "\n"
        "[tables.borrower_attributes.unless]\n"
        'code = ["FACULTY"]\n',
        encoding="utf-8",
    )
    rewriter = MysqlRewriter(
        load_profile(path=profile),
        Faker(random.Random(1)),
        Report(profile="unless"),
    )
    lines = [
        b"CREATE TABLE `borrower_attributes` (\n",
        b"  `id` int(11) NOT NULL,\n",
        b"  `borrowernumber` int(11) NOT NULL,\n",
        b"  `code` varchar(64) NOT NULL,\n",
        b"  `attribute` text DEFAULT NULL,\n",
        b"  PRIMARY KEY (`id`)\n",
        b") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n",
        b"INSERT INTO `borrower_attributes` VALUES\n",
        b"(1,1,'FACULTY','Engineering'),\n",
        b"(2,2,'CITIZENID','1234567890123');\n",
    ]
    output = b"".join(
        chunk for chunk in (rewriter.feed(line) for line in lines) if chunk
    )

    assert b"'FACULTY','Engineering'" in output
    assert b"'CITIZENID','1234567890123'" not in output


@pytest.mark.parametrize(
    "statement",
    [
        b"INSERT IGNORE INTO `borrowers` VALUES (1,'a@b.c');\n",
        b"REPLACE INTO `borrowers` VALUES (1,'a@b.c');\n",
        b"INSERT INTO borrowers VALUES (1,'a@b.c');\n",
    ],
)
def test_unsupported_insert_forms_rejected(statement):
    rewriter = make()
    for line in CREATE_BORROWERS:
        rewriter.feed(line)
    with pytest.raises(DumpFormatError):
        rewriter.feed(statement)


def test_insert_ignore_of_unruled_table_passes():
    rewriter = make()
    line = b"INSERT IGNORE INTO `biblio` VALUES (1,'x');\n"
    assert rewriter.feed(line) == line


def test_unless_column_missing_still_anonymizes(tmp_path):
    toml = tmp_path / "p.toml"
    toml.write_text(
        '[profile]\nname = "t"\nengine = "mysql"\n'
        '[tables.borrowers]\nemail = "email"\n'
        '[tables.borrowers.unless]\ncode = ["KEEP"]\n',
        encoding="utf-8",
    )
    from jarvis.anonymize.profile import load_profile as lp

    rewriter = MysqlRewriter(lp(path=toml), Faker(random.Random(1)), Report(profile="t"))
    for line in CREATE_BORROWERS:
        rewriter.feed(line)
    out = rewriter.feed(b"INSERT INTO `borrowers` VALUES (1,'real@person.th');\n")
    assert b"real@person.th" not in out
