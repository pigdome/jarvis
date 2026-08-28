import typer
import subprocess
from jarvis.config import get_secrets, save_secrets

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
