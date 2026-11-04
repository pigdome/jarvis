import typer
import subprocess
import sys
from jarvis.config import get_secrets, save_secrets

from pathlib import Path
from typing import Optional

# Removed unused LEGACY_DIR

app = typer.Typer(
    help="Database related commands",
    no_args_is_help=True,
)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def mysql(
    ctx: typer.Context,
    database: Optional[str] = typer.Argument(None, help="Database name to connect to (optional)"),
):
    """
    Open MySQL client (passwordless).
    """
    cmd = ["sudo", "mysql", "--defaults-file=/etc/mysql/debian.cnf"]
    if database:
        cmd.append(database)
    if ctx.args:
        cmd.extend(ctx.args)
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise typer.Exit(res.returncode)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def psql(
    ctx: typer.Context,
    database: Optional[str] = typer.Argument(None, help="Database name to connect to (optional)"),
):
    """
    Open PostgreSQL client (passwordless).
    """
    cmd = ["sudo", "-u", "postgres", "psql"]
    if database:
        cmd.append(database)
    if ctx.args:
        cmd.extend(ctx.args)
    res = subprocess.run(cmd)
    if res.returncode != 0:
        raise typer.Exit(res.returncode)


KOHA_IGNORE_TABLES = [
    "biblioimages",
    "cover_images",
    "patronimage",
    "action_logs",
    "misc_files",
    "message_queue",
    "background_jobs",
]


@app.command()
def mysqldump(
    database: str = typer.Argument(..., help="Database name to dump"),
    single_transaction: bool = typer.Option(False, "-s", help="Use --single-transaction"),
    koha: bool = typer.Option(False, "-k", help="Ignore large Koha tables"),
):
    """
    Dump a MySQL database.
    """
    import datetime
    from rich.console import Console
    console = Console(stderr=True)

    cmd = ["sudo", "mysqldump", "--defaults-file=/etc/mysql/debian.cnf"]
    if single_transaction:
        cmd.append("--single-transaction")
    if koha:
        for table in KOHA_IGNORE_TABLES:
            cmd.append(f"--ignore-table={database}.{table}")
    cmd.append(database)

    dump_file = f"/tmp/{database}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.sql.gz"
    console.print(f"[yellow]Dumping {database} -> {dump_file}...[/yellow]")

    with open(dump_file, "wb") as f:
        dump = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        gzip = subprocess.Popen(["gzip"], stdin=dump.stdout, stdout=f)
        dump.stdout.close()
        gzip.wait()
        dump.wait()

    console.print(f"[green]Done: {dump_file}[/green]")


@app.command()
def pg_dump(database: str = typer.Argument(..., help="Database name to dump")):
    """
    Dump a PostgreSQL database.
    """
    res = subprocess.run(["sudo", "-u", "postgres", "pg_dump", database])
    if res.returncode != 0:
        raise typer.Exit(res.returncode)


@app.command()
def anonymize(
    profile: Optional[str] = typer.Option(
        None, "-p", "--profile", help="Bundled profile name (koha, dspace, …)"
    ),
    profile_file: Optional[Path] = typer.Option(
        None, "--profile-file", help="External profile TOML instead of -p"
    ),
    type_: Optional[str] = typer.Option(
        None, "-t", "--type", help="Database engine for direct mode (mysql|psql)"
    ),
    database: Optional[str] = typer.Option(
        None, "-d", "--database", help="Database to anonymize in place"
    ),
    yes: bool = typer.Option(False, "--yes", help="Skip the direct-mode confirmation"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print direct-mode SQL instead of running it"
    ),
    list_: bool = typer.Option(False, "--list", help="List bundled profiles"),
    quiet: bool = typer.Option(False, "-q", "--quiet", help="Do not print the summary"),
):
    """
    Replace personal data in a SQL dump (stdin -> stdout) or in a live database.
    """
    from rich.console import Console

    from jarvis.anonymize.direct import (
        ConfirmationError,
        DirectError,
        run_direct,
    )
    from jarvis.anonymize.errors import DumpFormatError, ProfileError
    from jarvis.anonymize.profile import list_profiles, load_profile
    from jarvis.anonymize.strategies import Faker
    from jarvis.anonymize.stream import run_stream

    console = Console(stderr=True)

    if list_:
        try:
            profiles = list_profiles()
        except ProfileError as exc:
            console.print(str(exc), markup=False, highlight=False)
            raise typer.Exit(1)
        for item in profiles:
            console.print(
                f"{item.name}  {item.engine}  {item.description}",
                markup=False,
                highlight=False,
            )
        raise typer.Exit(0)

    try:
        if profile is not None and profile_file is not None:
            raise ProfileError("pass either --profile or --profile-file, not both")
        if profile is None and profile_file is None:
            raise ProfileError("pass --profile NAME or --profile-file PATH")
        loaded = (
            load_profile(profile)
            if profile is not None
            else load_profile(path=profile_file)
        )
    except ProfileError as exc:
        console.print(str(exc), markup=False, highlight=False)
        raise typer.Exit(1)

    if type_ is not None or database is not None:
        if type_ is None or database is None:
            console.print(
                "direct mode needs both -t/--type and -d/--database",
                markup=False,
                highlight=False,
            )
            raise typer.Exit(1)
        if type_ != loaded.engine:
            console.print(
                f"profile {loaded.name!r} is for engine {loaded.engine!r}, not {type_!r}",
                markup=False,
                highlight=False,
            )
            raise typer.Exit(1)
        try:
            direct_report = run_direct(
                loaded,
                type_,
                database,
                dry_run=dry_run,
                assume_yes=yes,
                out=sys.stdout,
            )
        except ProfileError as exc:
            console.print(str(exc), markup=False, highlight=False)
            raise typer.Exit(1)
        except ConfirmationError as exc:
            console.print(str(exc), markup=False, highlight=False)
            raise typer.Exit(1)
        except DirectError as exc:
            console.print(
                f"anonymize failed: {exc}", markup=False, highlight=False
            )
            raise typer.Exit(3)

        if not quiet and not dry_run:
            direct_report.render(console)
        return

    if sys.stdin.isatty():
        console.print(
            "refusing to read a dump from a terminal; pipe one in, for example:",
            markup=False,
            highlight=False,
        )
        console.print(
            "  pv dump.sql.gz | gunzip | jarvis db anonymize -p koha"
            " | jarvis db mysql koha_spu",
            markup=False,
            highlight=False,
        )
        raise typer.Exit(1)

    faker = Faker(email_tld=loaded.email_tld)
    try:
        report = run_stream(loaded, sys.stdin.buffer, sys.stdout.buffer, faker)
    except DumpFormatError as exc:
        console.print(
            f"anonymize failed: {exc}", markup=False, highlight=False
        )
        console.print(
            "Hint: run the pipeline with 'set -o pipefail'",
            markup=False,
            highlight=False,
        )
        raise typer.Exit(2)

    if not quiet:
        report.render(console)


@app.command()
def pg_restore(
    database: str = typer.Argument(..., help="Database name to restore to"),
    dump_file: str = typer.Argument(..., help="Path to the .sql.gz dump file")
):
    """
    Drop, Create, and Restore a PostgreSQL database from a .sql.gz dump.
    """
    import subprocess
    from jarvis.config import get_secrets, save_secrets, JARVIS_ROOT, CONFIG_DIR, BIN_DIR
    from rich.console import Console
    console = Console()

    # 1. Drop DB
    console.print(f"[bold red]💣 Dropping database: {database}...[/bold red]")
    subprocess.run(["sudo", "-u", "postgres", "dropdb", "--if-exists", database])

    # 2. Create DB
    console.print(f"[bold green]✨ Creating database: {database}...[/bold green]")
    subprocess.run(["sudo", "-u", "postgres", "createdb", database])

    # 3. Restore
    console.print(f"[bold yellow]📂 Restoring from {dump_file}...[/bold yellow]")
    # Using the user's pipeline: pv $DUMP | gunzip | sudo -u postgres psql $DB
    # We use shell=True because of the pipes
    pipeline = f"pv {dump_file} | gunzip | sudo -u postgres psql {database}"
    res = subprocess.run(pipeline, shell=True)
    if res.returncode != 0:
        console.print(f"[bold red]❌ Restore failed for {database}.[/bold red]")
        raise typer.Exit(res.returncode)
    console.print(f"[bold green]✅ Restore complete for {database}.[/bold green]")
