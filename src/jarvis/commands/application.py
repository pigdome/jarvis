import typer
import subprocess
from rich.console import Console

app = typer.Typer(
    help="Application specific commands (Koha, DSpace, etc.)",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]}
)

# --- Koha Sub-commands ---
koha_app = typer.Typer(
    help="Koha Library System management",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]}
)
app.add_typer(koha_app, name="koha")

@koha_app.command(name="stats")
def koha_stats(
    database: str = typer.Argument("koha_punsarn", help="Koha database name")
):
    """
    Show Koha database statistics (biblios, items, issues, borrowers).
    """
    console = Console()
    queries = {
        "Biblios": "SELECT count(*) FROM biblio",
        "Items": "SELECT count(*) FROM items",
        "Issues (Active)": "SELECT count(*) FROM issues",
        "Old Issues": "SELECT count(*) FROM old_issues",
        "Borrowers": "SELECT count(*) FROM borrowers",
    }
    
    console.print(f"📊 [bold cyan]Koha Statistics[/bold cyan] for database: [bold yellow]{database}[/bold yellow]\n")
    
    for label, query in queries.items():
        # Using passwordless mysql call
        cmd = ["sudo", "mysql", "--defaults-file=/etc/mysql/debian.cnf", "-e", f"{query};", database, "-N"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            count = result.stdout.strip()
            console.print(f"  [bold]• {label:18}:[/bold] [green]{count}[/green]")
        else:
            console.print(f"  [bold]• {label:18}:[/bold] [red]Error or Database not found[/red]")


# --- DSpace Sub-commands ---
dspace_app = typer.Typer(
    help="DSpace Repository System management",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]}
)
app.add_typer(dspace_app, name="dspace")


@dspace_app.command(name="init-db")
def dspace_init_db(
    user: str = typer.Option("dspace", "--user", "-u", help="DSpace user to create"),
    database: str = typer.Option("dspace", "--database", "-d", help="DSpace database to create")
):
    """
    Setup DSpace user and database in PostgreSQL.
    """
    console = Console()
    
    console.print(f"👤 [bold blue]Creating DSpace user:[/bold blue] [cyan]{user}[/cyan]...")
    subprocess.run(["sudo", "-u", "postgres", "createuser", "-s", user])
    
    console.print(f"🗄️  [bold blue]Creating DSpace database:[/bold blue] [cyan]{database}[/cyan] (owner: [cyan]{user}[/cyan])...")
    subprocess.run(["sudo", "-u", "postgres", "createdb", database, "-O", user])
    
    console.print(f"\n[bold green]✅ DSpace DB initialization complete![/bold green]")


@dspace_app.command(name="stats")
def dspace_stats(
    database: str = typer.Argument("dspace", help="DSpace database name")
):
    """
    Show DSpace database statistics (communities, collections, items, bitstreams, epeople).
    """
    console = Console()
    queries = {
        "Communities": "SELECT count(*) FROM community",
        "Collections": "SELECT count(*) FROM collection",
        "Items": "SELECT count(*) FROM item",
        "Bitstreams": "SELECT count(*) FROM bitstream",
        "EPeople": "SELECT count(*) FROM eperson",
    }
    
    console.print(f"📊 [bold blue]DSpace Statistics[/bold blue] for database: [bold yellow]{database}[/bold yellow]\n")
    
    for label, query in queries.items():
        # Command: sudo -u postgres psql -d database -t -A -c "query"
        # -t: tuples only, -A: unaligned
        cmd = ["sudo", "-u", "postgres", "psql", "-d", database, "-t", "-A", "-c", query]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            count = result.stdout.strip()
            console.print(f"  [bold]• {label:18}:[/bold] [cyan]{count}[/cyan]")
        else:
            console.print(f"  [bold]• {label:18}:[/bold] [red]Error or Database not found[/red]")
