"""Direct-mode tests: SQL generation, schema reading and the client driver.

Nothing here needs a database: the schema is built by hand and the client is a
small python script that answers the information_schema queries with TSV and
records every payload it receives.
"""

from __future__ import annotations

import dataclasses
import io
import shlex
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from jarvis.anonymize.direct import (  # noqa: E402
    Column,
    ConfirmationError,
    DirectError,
    TableInfo,
    build_sql,
    default_client,
    fetch_schema,
    run_direct,
)
from jarvis.anonymize.errors import ProfileError  # noqa: E402
from jarvis.anonymize.profile import (  # noqa: E402
    Profile,
    Rule,
    TableRules,
    load_profile,
)
from jarvis.anonymize.report import Report  # noqa: E402
from jarvis.commands.db import app as db_app  # noqa: E402

runner = CliRunner()


# -- helpers ---------------------------------------------------------------


def column(name, data_type="varchar", max_len=255, nullable=True):
    return Column(name=name, data_type=data_type, max_len=max_len, nullable=nullable)


def mysql_schema():
    return {
        "borrowers": TableInfo(
            columns={
                "borrowernumber": column("borrowernumber", "int", None, False),
                "cardnumber": column("cardnumber", "varchar", 32),
                "userid": column("userid", "varchar", 75),
                "surname": column("surname", "longtext", None),
                "firstname": column("firstname", "longtext", None),
                "email": column("email", "varchar", 100),
                "dateofbirth": column("dateofbirth", "date", None),
                "sort1": column("sort1", "varchar", 25),
            },
            pk=("borrowernumber",),
        ),
        "borrower_attributes": TableInfo(
            columns={
                "id": column("id", "int", None, False),
                "borrowernumber": column("borrowernumber", "int", None, False),
                "code": column("code", "varchar", 32),
                "attribute": column("attribute", "longtext", None),
            },
            pk=("id",),
        ),
        "additional_field_values": TableInfo(
            columns={
                "id": column("id", "int", None, False),
                "record_id": column("record_id", "int", None, False),
                "record_table": column("record_table", "varchar", 32),
                "value": column("value", "longtext", None),
            },
            pk=("id",),
        ),
        "sessions": TableInfo(
            columns={
                "id": column("id", "varchar", 32, False),
                "a_session": column("a_session", "longblob", None),
            },
            pk=("id",),
        ),
    }


def psql_schema():
    return {
        "booking_patron": TableInfo(
            columns={
                "id": column("id", "integer", None, False),
                "patron_id": column("patron_id", "character varying", 64),
                "cardnumber": column("cardnumber", "character varying", 32),
                "name": column("name", "character varying", 255),
                "email": column("email", "character varying", 254),
                "phone": column("phone", "character varying", 32),
                "organization": column("organization", "text", None),
            },
            pk=("id",),
        ),
        "booking_booking": TableInfo(
            columns={
                "id": column("id", "integer", None, False),
                "patron_id": column("patron_id", "integer", None, False),
                "attendance_list": column("attendance_list", "jsonb", None),
                "phone": column("phone", "character varying", 32),
                "reason_description": column("reason_description", "text", None),
            },
            pk=("id",),
        ),
    }


def test_non_text_columns_skip_empty_string_guard():
    statements, _ = build(load_profile("koha"), "mysql", mysql_schema())
    date_update = [
        statement
        for statement in statements
        if statement.startswith("UPDATE `borrowers` SET `dateofbirth`")
    ]
    assert len(date_update) == 1
    assert "<> ''" not in date_update[0]
    assert "<> '0000-00-00'" in date_update[0]

    statements, _ = build(
        load_profile("room_reservation"), "psql", psql_schema()
    )
    json_update = [
        statement
        for statement in statements
        if statement.startswith('UPDATE "booking_booking" SET "attendance_list"')
    ]
    assert len(json_update) == 1
    assert "<> ''" not in json_update[0]
    assert "IS NOT NULL" in json_update[0]
    assert '"attendance_list"::text' in json_update[0]
    assert "'[]'" in json_update[0] and "'{}'" in json_update[0]
    assert "::jsonb" in json_update[0]


def dspace_schema():
    return {
        "eperson": TableInfo(
            columns={
                "uuid": column("uuid", "uuid", None, False),
                "email": column("email", "character varying", 64),
                "netid": column("netid", "character varying", 64),
                "password": column("password", "character varying", 128),
                "salt": column("salt", "character varying", 32),
                "session_salt": column("session_salt", "character varying", 32),
            },
            pk=("uuid",),
        ),
        "metadatavalue": TableInfo(
            columns={
                "metadata_id": column("metadata_id", "bigint", None, False),
                "metadata_field_id": column("metadata_field_id", "integer", None, False),
                "text_value": column("text_value", "text", None),
            },
            pk=("metadata_id",),
        ),
        "metadatafieldregistry": TableInfo(
            columns={
                "metadata_field_id": column("metadata_field_id", "integer", None, False),
                "metadata_schema_id": column(
                    "metadata_schema_id", "integer", None, False
                ),
                "element": column("element", "character varying", 64),
                "qualifier": column("qualifier", "character varying", 64),
            },
            pk=("metadata_field_id",),
        ),
        "metadataschemaregistry": TableInfo(
            columns={
                "metadata_schema_id": column(
                    "metadata_schema_id", "integer", None, False
                ),
                "short_id": column("short_id", "character varying", 32),
            },
            pk=("metadata_schema_id",),
        ),
    }


def tiny_profile(engine, unless=None, when=None):
    return Profile(
        name="tiny",
        engine=engine,
        description="",
        truncate=frozenset(),
        email_tld="invalid",
        tables={
            "t": TableRules(
                columns={"name": Rule("name")},
                when=when or {},
                unless=unless or {},
                by_metadata_field={},
            )
        },
    )


def tiny_schema():
    columns = {
        "id": column("id", "int", None, False),
        "code": column("code", "varchar", 32),
        "name": column("name", "varchar", 255),
    }
    return {"t": TableInfo(columns=columns, pk=("id",))}


def with_table(profile, table, **changes):
    tables = dict(profile.tables)
    tables[table] = dataclasses.replace(profile.tables[table], **changes)
    return dataclasses.replace(profile, tables=tables)


def build(profile, engine, schema, report=None):
    report = report if report is not None else Report(profile.name)
    return build_sql(profile, engine, schema, report), report


def all_sql(statements):
    return "\n".join(statements)


def fake_client(tmp_path, rows=(), pk_rows=(), update_exit=0, schema_exit=0):
    """Write a schema-answering client; every payload is appended to a log."""
    log = tmp_path / "client.log"
    script = tmp_path / "client.py"
    script.write_text(
        "import sys\n"
        f"log = {str(log)!r}\n"
        "sql = sys.stdin.read()\n"
        "with open(log, 'a', encoding='utf-8') as handle:\n"
        "    handle.write(sql + '\\n#---#\\n')\n"
        "if 'information_schema' in sql.lower():\n"
        "    if 'primary' in sql.lower():\n"
        f"        rows = {list(pk_rows)!r}\n"
        "    else:\n"
        f"        rows = {list(rows)!r}\n"
        "    for row in rows:\n"
        "        print('\\t'.join(row))\n"
        f"    raise SystemExit({schema_exit})\n"
        f"raise SystemExit({update_exit})\n",
        encoding="utf-8",
    )
    return [sys.executable, str(script)], log


MYSQL_COLUMN_ROWS = [
    ("borrowers", "borrowernumber", "int", "-1", "NO"),
    ("borrowers", "cardnumber", "varchar", "32", "YES"),
    ("borrowers", "email", "varchar", "100", "YES"),
    ("sessions", "id", "varchar", "32", "NO"),
]
MYSQL_PK_ROWS = [
    ("borrowers", "borrowernumber"),
    ("sessions", "id"),
]


# -- SQL generation --------------------------------------------------------


def test_mysql_truncate_and_fk_wrap():
    statements, _ = build(load_profile("koha"), "mysql", mysql_schema())

    assert statements[0] == "SET FOREIGN_KEY_CHECKS=0;"
    assert statements[-1] == "SET FOREIGN_KEY_CHECKS=1;"
    assert "TRUNCATE `sessions`;" in statements


def test_psql_transaction():
    statements, _ = build(
        load_profile("room_reservation"), "psql", psql_schema()
    )

    assert statements[0] == "BEGIN;"
    assert statements[-1] == "COMMIT;"
    assert "CASCADE" not in all_sql(statements)
    assert "TRUNCATE" not in all_sql(statements)


def test_skip_missing_table_and_column():
    report = Report("koha")
    statements, report = build(
        load_profile("koha"), "mysql", mysql_schema(), report
    )

    sql = all_sql(statements)
    assert "deletedborrowers" not in sql
    assert "sort2" not in sql
    assert ("borrowers", "sort2") in report.missing_columns


def test_unique_two_pass():
    statements, _ = build(load_profile("koha"), "mysql", mysql_schema())

    cardnumber = [
        statement
        for statement in statements
        if statement.startswith("UPDATE `borrowers` SET `cardnumber` =")
    ]
    assert len(cardnumber) == 2
    assert "'~'" in cardnumber[0]
    assert "'~'" not in cardnumber[1]
    assert "borrowernumber" in cardnumber[1]


def test_unique_without_pk_rejected():
    schema = mysql_schema()
    borrowers = schema["borrowers"]
    schema["borrowers"] = TableInfo(columns=borrowers.columns, pk=())

    with pytest.raises(ProfileError):
        build(load_profile("koha"), "mysql", schema)


def test_when_unless_clauses():
    statements, _ = build(load_profile("koha"), "mysql", mysql_schema())
    sql = all_sql(statements)

    assert "`record_table` IN ('borrowers')" in sql
    # The bundled profile uses an empty keep_codes list: no rows are excluded.
    assert "NOT IN" not in sql

    profile = with_table(
        load_profile("koha"),
        "borrower_attributes",
        unless={"code": frozenset({"FACULTY"})},
    )
    statements, _ = build(profile, "mysql", mysql_schema())
    assert "`code` NOT IN ('FACULTY')" in all_sql(statements)


def test_when_on_absent_column_still_anonymizes():
    profile = with_table(
        load_profile("koha"),
        "additional_field_values",
        when={"record_table": frozenset({"borrowers"})},
    )
    schema = mysql_schema()
    info = schema["additional_field_values"]
    schema["additional_field_values"] = TableInfo(
        columns={
            name: col for name, col in info.columns.items() if name != "record_table"
        },
        pk=info.pk,
    )

    statements, _ = build(profile, "mysql", schema)

    value_updates = [
        statement
        for statement in statements
        if statement.startswith("UPDATE `additional_field_values` SET `value` =")
    ]
    assert len(value_updates) == 1
    assert "record_table" not in value_updates[0]


def test_unless_on_absent_column_does_not_exclude_rows():
    profile = with_table(
        load_profile("koha"),
        "borrower_attributes",
        unless={"code": frozenset({"FACULTY"})},
    )
    schema = mysql_schema()
    info = schema["borrower_attributes"]
    schema["borrower_attributes"] = TableInfo(
        columns={name: col for name, col in info.columns.items() if name != "code"},
        pk=info.pk,
    )

    statements, _ = build(profile, "mysql", schema)

    attribute_updates = [
        statement
        for statement in statements
        if statement.startswith("UPDATE `borrower_attributes` SET `attribute` =")
    ]
    assert len(attribute_updates) == 1
    assert "NOT IN" not in attribute_updates[0]
    assert "code" not in attribute_updates[0]


def test_ip_and_json_casts():
    ip_profile = dataclasses.replace(
        tiny_profile("psql"),
        tables={
            "t": TableRules(
                columns={"addr": Rule("ip"), "payload": Rule("json")},
                when={},
                unless={},
                by_metadata_field={},
            )
        },
    )
    schema = {
        "t": TableInfo(
            columns={
                "id": column("id", "integer", None, False),
                "addr": column("addr", "inet", None),
                "payload": column("payload", "jsonb", None),
            },
            pk=("id",),
        )
    }

    sql = all_sql(build(ip_profile, "psql", schema)[0])

    assert "192.0.2." in sql
    assert "::inet" in sql
    assert "::jsonb" in sql
    assert '"payload"::text' in sql


def test_metadata_field_update():
    statements, _ = build(load_profile("dspace"), "psql", dspace_schema())

    metadata = [
        statement
        for statement in statements
        if statement.startswith('UPDATE "metadatavalue"')
    ]
    assert metadata
    firstname = [s for s in metadata if "f.element = 'firstname'" in s]
    assert firstname
    assert "s.short_id = 'eperson'" in firstname[0]
    assert "mv.text_value IS NOT NULL" in firstname[0]


def test_metadata_registry_missing_rejected():
    schema = dspace_schema()
    del schema["metadatafieldregistry"]

    with pytest.raises(ProfileError):
        build(load_profile("dspace"), "psql", schema)


def test_literal_escaping():
    statements, _ = build(
        tiny_profile("mysql", unless={"code": frozenset({"O'X"})}),
        "mysql",
        tiny_schema(),
    )
    assert "'O\\'X'" in all_sql(statements)

    statements, _ = build(
        tiny_profile("mysql", unless={"code": frozenset({"back\\slash"})}),
        "mysql",
        tiny_schema(),
    )
    assert "'back\\\\slash'" in all_sql(statements)

    statements, _ = build(
        tiny_profile("psql", unless={"code": frozenset({"O'X"})}),
        "psql",
        tiny_schema(),
    )
    assert "'O''X'" in all_sql(statements)

    statements, _ = build(
        tiny_profile("psql", unless={"code": frozenset({"back\\slash"})}),
        "psql",
        tiny_schema(),
    )
    assert "'back\\slash'" in all_sql(statements)


def test_unique_expression_is_width_safe():
    statements, _ = build(load_profile("koha"), "mysql", mysql_schema())

    cardnumber = [s for s in statements if "`cardnumber` =" in s]
    # varchar(32) with a 10-character integer pk leaves room for the random part.
    assert all(s.endswith(";") for s in cardnumber)
    assert "LEFT(" in cardnumber[1]


# -- client and schema -----------------------------------------------------


def test_default_client():
    assert default_client("mysql", "koha_spu") == [
        "sudo",
        "mysql",
        "--defaults-file=/etc/mysql/debian.cnf",
        "koha_spu",
    ]
    assert default_client("psql", "dspace8") == [
        "sudo",
        "-u",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-X",
        "-q",
        "dspace8",
    ]


def test_fetch_schema_mysql(tmp_path):
    client, _ = fake_client(
        tmp_path, rows=MYSQL_COLUMN_ROWS, pk_rows=MYSQL_PK_ROWS
    )

    schema = fetch_schema(client, "mysql", "koha_spu")

    borrowers = schema["borrowers"]
    assert borrowers.pk == ("borrowernumber",)
    assert borrowers.columns["cardnumber"].max_len == 32
    assert borrowers.columns["cardnumber"].data_type == "varchar"
    assert borrowers.columns["borrowernumber"].max_len is None
    assert borrowers.columns["borrowernumber"].nullable is False


def test_fetch_schema_psql(tmp_path):
    rows = [
        ("booking_patron", "id", "integer", "-1", "NO"),
        ("booking_patron", "patron_id", "character varying", "64", "YES"),
    ]
    client, _ = fake_client(
        tmp_path, rows=rows, pk_rows=[("booking_patron", "id")]
    )

    schema = fetch_schema(client, "psql", "booking")

    patron = schema["booking_patron"]
    assert patron.pk == ("id",)
    assert patron.columns["patron_id"].max_len == 64
    assert patron.columns["patron_id"].data_type == "character varying"


def test_fetch_schema_client_failure(tmp_path):
    client, _ = fake_client(tmp_path, schema_exit=1)

    with pytest.raises(DirectError):
        fetch_schema(client, "mysql", "nowhere")


# -- run_direct ------------------------------------------------------------


def test_run_direct_confirm_mismatch(tmp_path):
    client, log = fake_client(
        tmp_path, rows=MYSQL_COLUMN_ROWS, pk_rows=MYSQL_PK_ROWS
    )

    with pytest.raises(ConfirmationError):
        run_direct(
            load_profile("koha"),
            "mysql",
            "koha_spu",
            client=client,
            confirm=lambda _prompt: "wrong",
            out=io.StringIO(),
        )

    assert "UPDATE" not in log.read_text(encoding="utf-8")


def test_dry_run_prints_sql(tmp_path):
    client, log = fake_client(
        tmp_path, rows=MYSQL_COLUMN_ROWS, pk_rows=MYSQL_PK_ROWS
    )
    out = io.StringIO()

    run_direct(
        load_profile("koha"),
        "mysql",
        "koha_spu",
        client=client,
        dry_run=True,
        out=out,
    )

    assert "UPDATE `borrowers`" in out.getvalue()
    assert "UPDATE" not in log.read_text(encoding="utf-8")


def test_run_direct_summary_before_confirmation(tmp_path, capsys):
    client, _ = fake_client(
        tmp_path, rows=MYSQL_COLUMN_ROWS, pk_rows=MYSQL_PK_ROWS
    )

    run_direct(
        load_profile("koha"),
        "mysql",
        "koha_spu",
        client=client,
        confirm=lambda _prompt: "koha_spu",
        out=io.StringIO(),
    )

    err = capsys.readouterr().err
    assert "koha_spu" in err
    assert "mysql" in err
    assert "tables to truncate: 1" in err
    assert "UPDATE statements:" in err
    assert "MySQL changes are not transactional" in err


def test_run_direct_client_failure(tmp_path):
    client, _ = fake_client(
        tmp_path, rows=MYSQL_COLUMN_ROWS, pk_rows=MYSQL_PK_ROWS, update_exit=1
    )

    with pytest.raises(DirectError):
        run_direct(
            load_profile("koha"),
            "mysql",
            "koha_spu",
            client=client,
            assume_yes=True,
            out=io.StringIO(),
        )


def test_run_direct_no_profile_table(tmp_path):
    client, _ = fake_client(
        tmp_path,
        rows=[("unrelated", "id", "int", "-1", "NO")],
        pk_rows=[("unrelated", "id")],
    )

    with pytest.raises(ProfileError):
        run_direct(
            load_profile("koha"),
            "mysql",
            "koha_spu",
            client=client,
            assume_yes=True,
            out=io.StringIO(),
        )


# -- CLI wiring ------------------------------------------------------------


def cli_env(client):
    return {"JARVIS_ANON_CLIENT": shlex.join(client)}


def test_cli_direct_dry_run(tmp_path):
    client, log = fake_client(
        tmp_path, rows=MYSQL_COLUMN_ROWS, pk_rows=MYSQL_PK_ROWS
    )

    result = runner.invoke(
        db_app,
        ["anonymize", "-p", "koha", "-t", "mysql", "-d", "koha_spu", "--dry-run"],
        env=cli_env(client),
    )

    assert result.exit_code == 0, result.stderr
    assert "UPDATE `borrowers`" in result.stdout
    assert "UPDATE" not in log.read_text(encoding="utf-8")


def test_cli_direct_client_failure_exits_3(tmp_path):
    client, _ = fake_client(
        tmp_path, rows=MYSQL_COLUMN_ROWS, pk_rows=MYSQL_PK_ROWS, update_exit=1
    )

    result = runner.invoke(
        db_app,
        ["anonymize", "-p", "koha", "-t", "mysql", "-d", "koha_spu", "--yes"],
        env=cli_env(client),
    )

    assert result.exit_code == 3


def test_cli_direct_confirmation_mismatch_exits_1(tmp_path):
    client, log = fake_client(
        tmp_path, rows=MYSQL_COLUMN_ROWS, pk_rows=MYSQL_PK_ROWS
    )

    result = runner.invoke(
        db_app,
        ["anonymize", "-p", "koha", "-t", "mysql", "-d", "koha_spu"],
        input="not-the-name\n",
        env=cli_env(client),
    )

    assert result.exit_code == 1
    assert "UPDATE" not in log.read_text(encoding="utf-8")


def test_cli_direct_success(tmp_path):
    client, log = fake_client(
        tmp_path, rows=MYSQL_COLUMN_ROWS, pk_rows=MYSQL_PK_ROWS
    )

    result = runner.invoke(
        db_app,
        ["anonymize", "-p", "koha", "-t", "mysql", "-d", "koha_spu", "--yes"],
        env=cli_env(client),
    )

    assert result.exit_code == 0, result.stderr
    assert "UPDATE `borrowers`" in log.read_text(encoding="utf-8")


@pytest.mark.parametrize("engine", ["mysql", "psql"])
def test_password_prefix_only_for_known_hashes(engine):
    from jarvis.anonymize.direct import _password_expr

    expr = _password_expr(engine, "`p`" if engine == "mysql" else '"p"')
    assert "pbkdf2_" in expr and "2[abxy]" in expr
    assert ("REGEXP" in expr) if engine == "mysql" else (" ~ " in expr)
