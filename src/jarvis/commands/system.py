import typer
import subprocess
import os
import sys
import shutil
import time
from pathlib import Path
from typing import Optional, Iterable
from jarvis.config import get_secrets, save_secrets, LEGACY_DIR, JARVIS_ROOT, CONFIG_DIR, BIN_DIR, BUNDLE_DIR

app = typer.Typer(
    help="System and Infrastructure related commands",
    no_args_is_help=True,
)


@app.callback()
def callback():
    """
    System and Infrastructure related commands.
    """
    pass


USER_CONFIGS = {
    "nick": {
        "user": "satrawut",
        "pass": "Hei4chuo",
        "key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIH+aScDXWUU+HMKXqxCNV7RcDaCDYQW4sX7vdtNVPcuo satrawut@Satrawut-Punsarn"
    },
    "man": {
        "user": "praphas",
        "pass": "Eeghi2ah",
        "key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIE4UAa9/WB+upCioRQ1PhnySmCcnaMWq/NDn049T2dww praphas@Manzybecalos"
    },
    "utt": {
        "user": "uttakran",
        "pass": "La4weegh",
        "key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJ7SeMOoxMoRCMYKHu2fc0a6APKYLDSgq2/s4eCoVLEK uttakran@utkrn-HP"
    },
    "joe": {
        "user": "pongtawat",
        "pass": "TaD9eiho",
        "key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMR27WU+nKSR4j8SKrRB0M6E7jaf8IbncKFqXpZ9ypsV pongtawat@erawan"
    },
    "george": {
        "user": "aekavute",
        "pass": "KXdA0jcf"
    },
    "je": {
        "user": "pichchai",
        "pass": "vD97BuS8",
        "key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDA3kxqiMOWG5m4kp72AflALaBzn+epVU8leFqVIzDhm kotorisn@kotorisn-GL552JX"
    },
    "me": {
        "user": "apirak",
        "key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDA3kxqiMOWG5m4kp72AflALaBzn+epVU8leFqVIzDhm kotorisn@kotorisn-GL552JX"
    },
}


def get_nicknames(ctx: typer.Context, incomplete: str):
    return [name for name in USER_CONFIGS.keys() if name.startswith(incomplete)]


@app.command()
def adduser(
    nickname: str = typer.Argument(
        ...,
        autocompletion=get_nicknames,
        help="Nickname of the user to add (e.g., nick, man, utt, joe, george, je, me)"
    ),
    sudo_privs: bool = typer.Option(
        False, "--sudo", "-s", help="Add sudo privileges"),
    authkeys: bool = typer.Option(
        False, "--authkeys", "-k", help="Add authorized_keys"),
):
    """
    Add a new user based on predefined nicknames.
    """
    from rich.console import Console
    console = Console()
    
    config = USER_CONFIGS.get(nickname)
    if not config:
        console.print(f"[red]❌ Error: Nickname '{nickname}' not found in predefined list.[/red]")
        return

    username = config["user"]
    password = config.get("pass")
    authorized_keys = config.get("key")

    # 1. Check if user exists, add if not
    result = subprocess.run(["id", "-u", username], capture_output=True)
    if result.returncode == 0:
        console.print(f"⚠️  [yellow]Alert: User {username} already exists[/yellow]")
    else:
        if password:
            console.print(f"👤 [bold blue]Adding user:[/bold blue] [cyan]{username}[/cyan] with password...")
            subprocess.run(["sudo", "adduser", "--disabled-password", "--gecos", "", username], check=True)
            subprocess.run(["sudo", "chpasswd"], input=f"{username}:{password}", text=True, check=True)
        else:
            console.print(f"👤 [bold blue]Adding user:[/bold blue] [cyan]{username}[/cyan] (no password)...")
            subprocess.run(["sudo", "adduser", "--disabled-password", "--gecos", "", username], check=True)
    
    # 2. Add sudo if requested
    if sudo_privs:
        console.print(f"🔑 [bold yellow]Adding sudo privileges for {username}...[/bold yellow]")
        subprocess.run(["sudo", "adduser", username, "sudo"], check=True)
    
    # 3. Authorized Keys
    if authkeys:
        if not authorized_keys:
            console.print(f"[red]⚠️  Warning: No authorized_keys defined for {nickname}[/red]")
        else:
            ssh_dir = Path("/home") / username / ".ssh"
            auth_file = ssh_dir / "authorized_keys"
            
            # Check if file exists via sudo (since it's in user's home)
            check_exists = subprocess.run(["sudo", "test", "-f", str(auth_file)])
            if check_exists.returncode == 0:
                console.print(f"⚠️  [yellow]Warn: authorized_keys exists for {username}[/yellow]")
            else:
                console.print(f"📂 [bold yellow]Adding authorized_keys for {username}...[/bold yellow]")
                subprocess.run(["sudo", "mkdir", "-p", str(ssh_dir)], check=True)
                subprocess.run(["sudo", "tee", str(auth_file)], input=authorized_keys, text=True, capture_output=True, check=True)
                subprocess.run(["sudo", "chmod", "700", str(ssh_dir)], check=True)
                subprocess.run(["sudo", "chmod", "600", str(auth_file)], check=True)
                subprocess.run(["sudo", "chown", f"{username}:{username}", "-R", str(ssh_dir)], check=True)
    
    console.print(f"[green]✅ Done for user {username}[/green]")


def _sudo_cmd(command: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return command
    return ["sudo"] + command


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _run_cleanup_command(command: list[str], dry_run: bool = False) -> bool:
    printable = " ".join(command)
    if dry_run:
        print(f"DRY RUN: {printable}")
        return True

    print(f"🚀 Running: {printable}")
    result = subprocess.run(command)
    if result.returncode != 0:
        print(f"⚠️  Command failed ({result.returncode}): {printable}")
        return False
    return True


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0

    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() or item.is_symlink():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _remove_path_contents(paths: Iterable[Path], dry_run: bool = False) -> int:
    freed = 0
    for path in paths:
        expanded = path.expanduser()
        if not expanded.exists():
            continue

        targets = list(expanded.iterdir()) if expanded.is_dir() else [expanded]
        for target in targets:
            size = _path_size(target)
            freed += size
            if dry_run:
                print(f"DRY RUN: remove {target} ({_format_bytes(size)})")
                continue

            try:
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                print(f"🧹 Removed {target} ({_format_bytes(size)})")
            except OSError as exc:
                print(f"⚠️  Could not remove {target}: {exc}")
    return freed


@app.command()
def clean_pc(
    yes: bool = typer.Option(False, "--yes", "-y", help="Run without confirmation"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show cleanup actions without deleting anything"),
    include_docker: bool = typer.Option(False, "--docker", help="Also prune unused Docker data"),
    skip_apt: bool = typer.Option(False, "--skip-apt", help="Skip apt autoremove/autoclean/clean"),
    skip_user_cache: bool = typer.Option(False, "--skip-user-cache", help="Skip Trash, thumbnails, and user cache cleanup"),
    skip_journal: bool = typer.Option(False, "--skip-journal", help="Skip systemd journal vacuum"),
    journal_days: int = typer.Option(14, "--journal-days", min=1, help="Keep this many days of systemd journal logs"),
    journal_size: Optional[str] = typer.Option(None, "--journal-size", help="Vacuum systemd journal logs to max size (e.g. 100M)"),
):
    """
    Clean a local Linux PC: apt packages, user caches, trash, journals, Flatpak/Snap, and optional Docker.
    """
    from rich.console import Console
    from rich.prompt import Confirm

    console = Console()
    home = Path.home()
    user_cache_paths = [
        home / ".local/share/Trash",
        home / ".cache/thumbnails",
        home / ".cache/pip",
        home / ".cache/uv",
        home / ".npm/_cacache",
        home / ".cache/yarn",
        home / ".cache/pnpm",
        home / ".bun/install/cache",
        home / ".gradle/caches",
        home / ".cache/Cypress",
        home / ".cache/ms-playwright",
        home / ".cache/ms-playwright-mcp",
        home / ".cache/mesa_shader_cache",
        home / ".cache/mesa_shader_cache_db",
        home / ".cache/fontconfig",
        home / ".cache/google-chrome",
        home / ".cache/zen",
        home / ".cache/chromium",
        home / ".cache/mozilla",
    ]

    actions = []
    if not skip_apt and _command_exists("apt"):
        actions.append("apt autoremove/autoclean/clean")
    if not skip_user_cache:
        actions.append("Trash, thumbnails, and common user package caches")
    if not skip_journal and _command_exists("journalctl"):
        journal_desc = f"systemd journal older than {journal_days} days"
        if journal_size:
            journal_desc += f" (or exceeding {journal_size})"
        actions.append(journal_desc)
    if _command_exists("flatpak"):
        actions.append("unused Flatpak runtimes/apps")
    if _command_exists("snap"):
        actions.append("disabled Snap revisions")
    if include_docker and _command_exists("docker"):
        actions.append("unused Docker containers/images/networks/build cache")

    console.print("[bold cyan]Linux PC cleanup plan[/bold cyan]")
    for action in actions:
        console.print(f"  • {action}")

    if dry_run:
        console.print("[yellow]Dry run enabled; no files or packages will be removed.[/yellow]")
    elif not yes and not Confirm.ask("Continue with cleanup?", default=False):
        console.print("[yellow]Cancelled.[/yellow]")
        raise typer.Exit(0)

    failures = 0

    if not skip_apt and _command_exists("apt"):
        apt_commands = [
            _sudo_cmd(["apt", "autoremove", "-y"]),
            _sudo_cmd(["apt", "autoclean"]),
            _sudo_cmd(["apt", "clean"]),
        ]
        for command in apt_commands:
            failures += 0 if _run_cleanup_command(command, dry_run) else 1
    elif not skip_apt:
        console.print("[yellow]Skipping apt cleanup: apt command not found.[/yellow]")

    if not skip_user_cache:
        before = sum(_path_size(path.expanduser()) for path in user_cache_paths)
        freed = _remove_path_contents(user_cache_paths, dry_run)
        console.print(f"[green]User cache cleanup target:[/green] {_format_bytes(before or freed)}")

    if not skip_journal and _command_exists("journalctl"):
        failures += 0 if _run_cleanup_command(
            _sudo_cmd(["journalctl", f"--vacuum-time={journal_days}d"]),
            dry_run,
        ) else 1
        if journal_size:
            failures += 0 if _run_cleanup_command(
                _sudo_cmd(["journalctl", f"--vacuum-size={journal_size}"]),
                dry_run,
            ) else 1
    elif not skip_journal:
        console.print("[yellow]Skipping journal cleanup: journalctl command not found.[/yellow]")

    if _command_exists("flatpak"):
        failures += 0 if _run_cleanup_command(["flatpak", "uninstall", "--unused", "-y"], dry_run) else 1

    if _command_exists("snap"):
        if dry_run:
            print("DRY RUN: remove disabled Snap revisions")
        else:
            result = subprocess.run(["snap", "list", "--all"], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 6 and "disabled" in parts:
                        name, revision = parts[0], parts[2]
                        failures += 0 if _run_cleanup_command(
                            _sudo_cmd(["snap", "remove", name, "--revision", revision])
                        ) else 1
            else:
                failures += 1
                console.print("[yellow]Could not list Snap revisions.[/yellow]")

    if include_docker:
        if _command_exists("docker"):
            failures += 0 if _run_cleanup_command(["docker", "system", "prune", "-af"], dry_run) else 1
        else:
            console.print("[yellow]Skipping Docker cleanup: docker command not found.[/yellow]")

    if failures:
        console.print(f"[yellow]Cleanup completed with {failures} warning(s).[/yellow]")
        raise typer.Exit(1)

    console.print(f"[green]✅ Cleanup complete at {time.strftime('%Y-%m-%d %H:%M:%S')}[/green]")


@app.command()
def upload(
    file_path: str = typer.Argument(..., help="Path to the file to upload"),
    host: str = typer.Option("https://transfer.eval.plus", "--host", "-h", help="Upload host")
):
    """
    Upload a file to a transfer service.
    """
    if not os.path.exists(file_path):
        print(f"❌ Error: File {file_path} not found.")
        return

    base_name = os.path.basename(file_path)
    # Sanitize name
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '-', base_name)
    
    print(f"📤 Uploading {file_path} to {host}...")
    cmd = ["curl", "--progress-bar", "--upload-file", file_path, f"{host}/{safe_name}"]
    subprocess.run(cmd)
    print("\n✅ Upload complete.")


@app.command(hidden=True)
def keepass():
    """
    Open KeePass database using kpcli.
    """
    kdb_path = CONFIG_DIR / "keepass/apirak.kdbx"
    if not kdb_path.exists():
        print(f"❌ Error: KeePass database not found at {kdb_path}")
        return

    print(f"🔐 Opening KeePass database: {kdb_path.name}")
    subprocess.run(["kpcli", "--kdb", str(kdb_path)])


@app.command()
def init():
    """
    Initialize a new Debian/Ubuntu server (must run as root).
    Sets up packages, timezone, locale, working dir, and SSH hardening.
    """
    from rich.console import Console
    console = Console()

    if os.geteuid() != 0:
        console.print("[red]❌ Please run as root (sudo jarvis sys init)[/red]")
        raise typer.Exit(1)

    DEFAULT_PACKAGES = (
        "unattended-upgrades sudo wget curl pv git screen htop nmon iotop vim locales tzdata procps"
    )
    WORKING_DIR = Path("/srv/punsarn")

    # 1. Update & install packages
    console.print("[yellow]📦 Installing default packages...[/yellow]")
    subprocess.run(["apt", "update"], check=True)
    subprocess.run(["apt", "upgrade", "-y"], check=True)
    subprocess.run(["apt", "install", "-y"] + DEFAULT_PACKAGES.split(), check=True)

    # 2. Timezone & locales
    console.print("[yellow]🕐 Setting timezone to Asia/Bangkok...[/yellow]")
    Path("/etc/localtime").unlink(missing_ok=True)
    Path("/etc/localtime").symlink_to("/usr/share/zoneinfo/Asia/Bangkok")
    subprocess.run(["dpkg-reconfigure", "-f", "noninteractive", "tzdata"])

    console.print("[yellow]🌐 Setting locales (en_US.UTF-8, th_TH.UTF-8)...[/yellow]")
    locale_gen = Path("/etc/locale.gen")
    content = locale_gen.read_text()
    content = content.replace("# en_US.UTF-8 UTF-8", "en_US.UTF-8 UTF-8")
    content = content.replace("# th_TH.UTF-8 UTF-8", "th_TH.UTF-8 UTF-8")
    locale_gen.write_text(content)
    subprocess.run(["dpkg-reconfigure", "--frontend=noninteractive", "locales"])

    # 3. Working directory /srv/punsarn
    console.print("[yellow]📁 Setting up working directory /srv/punsarn...[/yellow]")
    if not WORKING_DIR.exists():
        WORKING_DIR.mkdir(mode=0o2775, parents=True)
    result = subprocess.run(["getent", "group", "punsarn"], capture_output=True)
    if result.returncode != 0:
        subprocess.run(["addgroup", "punsarn"], check=True)
    subprocess.run(["chgrp", "punsarn", "/srv/punsarn", str(WORKING_DIR)])

    # 4. SSH hardening
    console.print("[yellow]🔒 Hardening SSH (PermitRootLogin no)...[/yellow]")
    sshd_config = Path("/etc/ssh/sshd_config")
    content = sshd_config.read_text()
    import re
    content = re.sub(r"#?PermitRootLogin.*", "PermitRootLogin no", content)
    sshd_config.write_text(content)
    subprocess.run(["sshd", "-t"], check=True)
    subprocess.run(["systemctl", "restart", "ssh"])

    console.print("\n[green]✅ Server initialization complete![/green]")
    console.print("[red]⚠️  Add your ~/.ssh/authorized_keys and set PasswordAuthentication no in /etc/ssh/sshd_config[/red]")


@app.command(hidden=True)
def setup_ssh():
    """
    Decrypt SSH keys to /tmp/.ssh (move to ~/.ssh manually when ready).
    """
    encrypted = CONFIG_DIR / "id.tar.gz.gpg"
    if not encrypted.exists():
        print(f"❌ Error: {encrypted} not found.")
        raise typer.Exit(1)

    out_dir = Path("/tmp/.ssh")
    out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    tar_tmp = Path("/tmp/id.tar.gz")

    print(f"🔑 Decrypting {encrypted.name}...")
    result = subprocess.run(
        ["gpg", "--quiet", "--batch", "--yes", "--output", str(tar_tmp), "--decrypt", str(encrypted)]
    )
    if result.returncode != 0:
        print("❌ Decryption failed.")
        raise typer.Exit(1)

    print(f"📂 Extracting to {out_dir} ...")
    subprocess.run(["tar", "-xzf", str(tar_tmp), "-C", str(out_dir)], check=True)
    tar_tmp.unlink()

    # chmod 600 all files
    for f in out_dir.iterdir():
        f.chmod(0o600)

    print(f"✅ SSH keys extracted to {out_dir}")
    print(f"👉 Move to ~/.ssh when ready:  mv /tmp/.ssh/* ~/.ssh/")


@app.command(name="claude-skill")
def claude_skill(
    list_only: bool = typer.Option(False, "--list", "-l", help="List skills without installing"),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing skills without prompting"),
):
    """
    Install or update all Claude skills to ~/.claude/commands/.

    Skills are sourced from config/claude-skills/ in the JARVIS project.
    Run this after adding or editing a skill file to deploy it globally.
    """
    from rich.console import Console
    from rich.table import Table
    from rich.prompt import Confirm

    console = Console()
    _candidates = [
        BUNDLE_DIR / "config" / "claude-skills",             # bundled binary (after rebuild) or source tree
        Path(sys.executable).parent / "config" / "claude-skills",  # next to the binary
        JARVIS_ROOT / "claude-skills",                        # ~/.jarvis/claude-skills/ (user override)
    ]
    skills_src = next((p for p in _candidates if p.exists()), None)

    if skills_src is None:
        console.print("[red]❌ Skills source directory not found.[/red]")
        console.print("[dim]Searched:[/dim]")
        for p in _candidates:
            console.print(f"  [dim]• {p}[/dim]")
        console.print(f"\n[yellow]Tip:[/yellow] Copy skill .md files to [cyan]{JARVIS_ROOT / 'claude-skills'}[/cyan] to use them without rebuilding.")
        raise typer.Exit(1)

    skill_files = sorted(skills_src.glob("*.md"))
    if not skill_files:
        console.print(f"[yellow]⚠️  No skill files found in {skills_src}[/yellow]")
        raise typer.Exit(0)

    dest_dir = Path.home() / ".claude" / "commands"

    if list_only:
        table = Table(title="Available Claude Skills", show_lines=True)
        table.add_column("Skill", style="cyan")
        table.add_column("Source", style="dim")
        table.add_column("Installed", style="green")
        for sf in skill_files:
            dest = dest_dir / sf.name
            installed = "✅ yes" if dest.exists() else "❌ no"
            table.add_row(sf.stem, str(sf), installed)
        console.print(table)
        return

    dest_dir.mkdir(parents=True, exist_ok=True)
    installed, updated, skipped = [], [], []

    for sf in skill_files:
        dest = dest_dir / sf.name
        already_exists = dest.exists()

        if already_exists and not force and not Confirm.ask(f"  Overwrite existing skill [cyan]{sf.stem}[/cyan]?", default=True):
            skipped.append(sf.stem)
            continue

        shutil.copy2(sf, dest)
        (updated if already_exists else installed).append(sf.stem)

    if installed:
        console.print(f"[green]✅ Installed:[/green] {', '.join(installed)}")
    if updated:
        console.print(f"[blue]🔄 Updated:[/blue]  {', '.join(updated)}")
    if skipped:
        console.print(f"[yellow]⏭️  Skipped:[/yellow]  {', '.join(skipped)}")

    console.print(f"\n[dim]Skills live at: {dest_dir}[/dim]")
    console.print("[dim]Use /project-review (or the skill name) inside Claude Code to invoke.[/dim]")


@app.command()
def update():
    """
    Update Ubuntu/Linux system (apt update, upgrade, clean, autoremove).
    """
    commands = [
        ["sudo", "apt", "update"],
        ["sudo", "apt", "upgrade", "-y"],
        ["sudo", "apt", "autoremove", "-y"],
        ["sudo", "apt", "autoclean"],
        ["sudo", "apt", "clean"],
    ]
    for cmd in commands:
        print(f"🚀 Running: {' '.join(cmd)}")
        subprocess.run(cmd)


@app.command()
def discord_update():
    """
    Download and update Discord for Linux (deb package).
    """
    print("🎮 Updating Discord...")
    # 1. Download the latest deb
    url = "https://discord.com/api/download/stable?platform=linux&format=deb"
    target = "/tmp/discord.deb"
    print(f"📥 Downloading from {url} to {target}...")
    subprocess.run(["wget", "-O", target, url], check=True)

    # 2. Install using dpkg
    print("📦 Installing Discord package...")
    subprocess.run(["sudo", "dpkg", "-i", target], check=True)
    
    # 3. Cleanup
    if os.path.exists(target):
        os.remove(target)
    
    print("✅ Discord update complete!")


@app.command()
def email_test(
    to: str = typer.Option("apirak@punsarn.com", "--to", "-t", help="Recipient email address"),
    subject: Optional[str] = typer.Option(None, "--subject", "-s", help="Email subject")
):
    """
    Send a test email using the system mail command.
    """
    import socket
    from datetime import datetime
    import getpass

    hostname = socket.gethostname()
    current_user = getpass.getuser()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not subject:
        subject = f"test email from {hostname} by jarvis at {now}"

    print(f"📧 Sending test email to {to}...")

    # Use 'mail' command via subprocess
    try:
        process = subprocess.Popen(
            ["mail", "-s", subject, to],
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        process.communicate(input=current_user)

        if process.returncode == 0:
            print("✅ Email sent successfully.")
        else:
            print(f"❌ Failed to send email. Return code: {process.returncode}")
    except FileNotFoundError:
        print("❌ Error: 'mail' command not found. Please install mailutils or similar.")
