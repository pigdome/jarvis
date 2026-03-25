import typer
import subprocess
import os
import sys
from pathlib import Path
from typing import Optional
from jarvis.config import get_secrets, save_secrets, LEGACY_DIR, JARVIS_ROOT, CONFIG_DIR, BIN_DIR

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


def get_nicknames(ctx: typer.Context, incomplete: str):
    nicknames = ["nick", "man", "utt", "joe", "george", "je", "me"]
    return [name for name in nicknames if name.startswith(incomplete)]


@app.command()
def adduser(
    nickname: str = typer.Argument(
        ...,
        autocompletion=get_nicknames,
        help="Nickname of the user to add"
    ),
    sudo_privs: bool = typer.Option(
        False, "--sudo", "-s", help="Add sudo privileges"),
    authkeys: bool = typer.Option(
        False, "--authkeys", "-k", help="Add authorized_keys"),
):
    """
    Add a new user based on predefined nicknames or any name.
    """
    from rich.console import Console
    console = Console()
    
    console.print(f"👤 [bold blue]Adding user:[/bold blue] [cyan]{nickname}[/cyan]...")
    
    # 1. Create user
    subprocess.run(["sudo", "useradd", "-m", "-s", "/bin/bash", nickname])
    
    # 2. Add sudo if requested
    if sudo_privs:
        console.print(f"🔑 [bold yellow]Adding sudo privileges for {nickname}...[/bold yellow]")
        subprocess.run(["sudo", "usermod", "-aG", "sudo", nickname])
    
    # 3. Authkeys (Placeholder logic if no legacy script)
    if authkeys:
        console.print(f"📂 [bold yellow]Adding authorized_keys for {nickname}...[/bold yellow]")
        auth_file = Path("/home") / nickname / ".ssh" / "authorized_keys"
        # Since the legacy script is gone, we might lack the source keys
        console.print(f"[red]⚠️  Note: Legacy script for authkeys was removed. Please add keys manually to {auth_file}[/red]")


@app.command()
def clean_pc():
    """
    Clean the system (apt cleanup).
    """
    commands = [
        ["sudo", "apt", "autoremove", "-y"],
        ["sudo", "apt", "autoclean"],
        ["sudo", "apt", "clean"],
    ]
    for cmd in commands:
        print(f"🚀 Running: {' '.join(cmd)}")
        subprocess.run(cmd)


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
