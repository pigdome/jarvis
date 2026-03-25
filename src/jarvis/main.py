import random
from rich.console import Console
from rich.tree import Tree

import typer
from jarvis.commands import network, system, db, self, application
from jarvis import __version__

app = typer.Typer(
    name="jarvis",
    help="JARVIS - Tools for life hack",
    add_completion=True,
    no_args_is_help=True,
)
# Panels for grouping commands in --help
INFRA_PANEL = "🏗️  Infrastructure & System"
NET_PANEL = "🌐  Network & Security"
DB_PANEL = "🗄️  Database Utilities"
APP_PANEL = "🚀  Applications & Services"
CORE_PANEL = "🤖  JARVIS Core"

app.add_typer(
    network.app,
    name="net",
    help="Network and VPN related commands",
    rich_help_panel=NET_PANEL
)
app.add_typer(
    system.app,
    name="sys",
    help="System and Infrastructure related commands",
    rich_help_panel=INFRA_PANEL
)
app.add_typer(
    db.app,
    name="db",
    help="Database related commands",
    rich_help_panel=DB_PANEL
)
app.add_typer(
    application.app,
    name="app",
    help="Application specific commands (Koha, DSpace, etc.)",
    rich_help_panel=APP_PANEL
)
app.add_typer(
    self.app,
    name="self",
    help="Self-management and JARVIS setup",
    rich_help_panel=CORE_PANEL
)

# Common Aliases Grouped by Function - REMOVED root aliases as per user request
# Forcing strictly jarvis [category] [cmd]

@app.command(name="version", rich_help_panel=CORE_PANEL)
def version():
    """
    Show the JARVIS CLI version.
    """
    print(f"JARVIS CLI version: {__version__}")


@app.command(name="help", rich_help_panel=CORE_PANEL)
def help_tree(
    show_all: bool = typer.Option(False, "--all", help="Show all commands including hidden ones", hidden=True)
):
    """
    Show all available commands in a beautiful tree structure.
    """
    console = Console()
    console.print(generate_tree(app, show_all=show_all))


def generate_tree(typer_app, tree=None, show_all: bool = False):
    if tree is None:
        tree = Tree("🤖 [bold blue]JARVIS Command Tree[/bold blue]")

    # Commands in this level
    commands = sorted(typer_app.registered_commands, key=lambda x: (x.name or getattr(x.callback, "__name__", "")))
    for cmd in commands:
        name = cmd.name or getattr(cmd.callback, "__name__", None)
        if not name or name == "help":
            continue
        if cmd.hidden and not show_all:
            continue
        # Standardize name for display (replace _ with -)
        display_name = name.replace("_", "-")
        help_text = f" - [dim]{cmd.help}[/dim]" if cmd.help else ""
        tree.add(f"[green]{display_name}[/green]{help_text}")

    # Groups
    groups = sorted(typer_app.registered_groups, key=lambda x: (x.name or ""))
    for grp in groups:
        if not grp.name:
            continue
        help_text = f" - [dim]{grp.help}[/dim]" if grp.help else ""
        sub_tree = tree.add(f"[bold yellow]{grp.name}[/bold yellow]{help_text}")
        if grp.typer_instance:
            generate_tree(grp.typer_instance, sub_tree, show_all=show_all)
    return tree


@app.callback(invoke_without_command=True, no_args_is_help=True)
def callback(
    ctx: typer.Context,
):
    """
    JARVIS CLI - Automation and productivity tools.
    """
    if ctx.resilient_parsing:
        return

    if ctx.invoked_subcommand:
        # Don't speak for version command to keep it clean, but for others, let's have some fun
        if ctx.invoked_subcommand not in ["version", "help"]:
            quotes = [
                "At your service, sir.",
                "Right away, sir.",
                "Of course, sir. Processing now.",
                "I've allocated additional resources for this task.",
                "Always a pleasure to assist, sir.",
                "Shall I notify you when the task is complete?",
                "Scanning protocols initiated.",
                "I'm on it, sir. Just a moment.",
                "Everything appears to be in order.",
                "The system is performing within normal parameters.",
            ]
            import sys
            console = Console(stderr=True)
            console.print(f"[bold blue]jarvis:[/bold blue] [italic white]{random.choice(quotes)}[/italic white]\n")

    if ctx.invoked_subcommand is None:
        # If no command, Typer shows help by default due to no_args_is_help=True
        pass


if __name__ == "__main__":
    app()
