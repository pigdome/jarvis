import typer
import subprocess
from jarvis.config import get_secrets, save_secrets

# Removed unused LEGACY_DIR

app = typer.Typer(
    help="Database related commands",
    no_args_is_help=True,
)


@app.command()
def mysql():
    """
    Open MySQL client (passwordless).
    """
    subprocess.run(["sudo", "mysql", "--defaults-file=/etc/mysql/debian.cnf"])


@app.command()
def psql():
    """
    Open PostgreSQL client (passwordless).
    """
    subprocess.run(["sudo", "-u", "postgres", "psql"])


@app.command()
def mysqldump(database: str = typer.Argument(..., help="Database name to dump")):
    """
    Dump a MySQL database.
    """
    subprocess.run(["sudo", "mysqldump", "--defaults-file=/etc/mysql/debian.cnf", database])


@app.command()
def mysqldump_fast(database: str = typer.Argument(..., help="Database name to dump")):
    """
    Dump a MySQL database using fast method.
    """
    # Simply use mysqldump with some common optimization flags
    subprocess.run(["sudo", "mysqldump", "--defaults-file=/etc/mysql/debian.cnf", "--opt", "--quick", database])


@app.command()
def pg_dump(database: str = typer.Argument(..., help="Database name to dump")):
    """
    Dump a PostgreSQL database.
    """
    subprocess.run(["sudo", "-u", "postgres", "pg_dump", database])


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
    subprocess.run(pipeline, shell=True)
    console.print(f"[bold green]✅ Restore complete for {database}.[/bold green]")
