import typer
import subprocess
import os
import sys
import shutil
from pathlib import Path
from typing import Optional
from jarvis.config import get_secrets, save_secrets, JARVIS_ROOT, CONFIG_DIR, BIN_DIR # Removed unused LEGACY_DIR

app = typer.Typer(
    help="Self-management and JARVIS setup commands",
    no_args_is_help=True,
)


def sync_ssh_keys():
    """
    Sync SSH authorized_keys from bundled config to ~/.ssh/authorized_keys.
    """
    auth_keys_src = CONFIG_DIR / "authorized_keys"
    auth_keys_dest = Path.home() / ".ssh/authorized_keys"

    if not auth_keys_src.exists():
        print(f"⚠️  Source authorized_keys not found at {auth_keys_src}")
        return

    # Ensure destination directory exists
    auth_keys_dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not auth_keys_dest.exists():
        auth_keys_dest.touch(mode=0o600)

    print(f"🔑 Syncing SSH authorized_keys from {auth_keys_src.name}...")

    # Read current keys to avoid duplicates
    try:
        with open(auth_keys_dest, "r") as f:
            current_keys = f.readlines()
            current_keys = [k.strip() for k in current_keys if k.strip()]
    except Exception:
        current_keys = []

    new_keys_count = 0
    with open(auth_keys_src, "r") as f_src:
        with open(auth_keys_dest, "a") as f_dest:
            for line in f_src:
                key = line.strip()
                if key and not key.startswith("#") and key not in current_keys:
                    f_dest.write(key + "\n")
                    new_keys_count += 1

    if new_keys_count > 0:
        print(f"✅ Added {new_keys_count} new SSH keys.")
    else:
        print("⏺️  All SSH keys are already present.")


def setup_vim():
    """
    Setup .vimrc by copying it from the jarvis config (internal step).
    """
    vimrc_src = CONFIG_DIR / ".vimrc"
    vimrc_dest = Path.home() / ".vimrc"
    if vimrc_src.exists():
        if vimrc_dest.exists() or vimrc_dest.is_symlink():
            print(f"⚠️  Overwriting existing {vimrc_dest}")
            if vimrc_dest.is_dir() and not vimrc_dest.is_symlink():
                shutil.rmtree(vimrc_dest)
            else:
                vimrc_dest.unlink()
        shutil.copy(vimrc_src, vimrc_dest)
        print(f"✅ Copied {vimrc_src} to {vimrc_dest}")
    else:
        print(f"❌ Error: {vimrc_src} not found.")


@app.command()
def deploy():
    """
    Run the full JARVIS deployment/setup process.
    """
    print("🚀 Starting JARVIS deployment...")

    # 1. Setup VIM
    setup_vim()

    # 2. SSH Sync
    sync_ssh_keys()

    print("\n✨ Deployment complete!")
@app.command()
def update():
    """
    Check for and install the latest version of JARVIS from GitHub.
    """
    from rich.console import Console
    console = Console()
    
    # Detect the current executable path
    if getattr(sys, 'frozen', False):
        current_exe = Path(sys.executable).resolve()
    else:
        # Fallback for development mode
        console.print("[yellow]⚠️  Running in development mode. Update will replace the binary in ~/.local/bin/jarvis if it exists.[/yellow]")
        current_exe = Path.home() / ".local/bin/jarvis"
        if not current_exe.exists():
            console.print("[red]❌ Error: Cannot find binary to update in development mode.[/red]")
            return
            
    console.print(f"🚀 [bold blue]Updating JARVIS at:[/bold blue] [bold yellow]{current_exe}[/bold yellow]")
    
    tmp_file = "/tmp/jarvis.tar.gz"
    repo_url = "https://github.com/pigdome/jarvis/releases/latest/download/jarvis.tar.gz"
    
    # Clear LD_LIBRARY_PATH to avoid library conflicts when running system binaries (like curl)
    # from within a frozen PyInstaller bundle.
    env = os.environ.copy()
    for var in ['LD_LIBRARY_PATH', 'PYTHONHOME', 'PYTHONPATH']:
        env.pop(var, None)
            
    try:
        console.print(f"📥 Downloading latest version from [cyan]{repo_url}[/cyan]...")
        subprocess.run(["curl", "-L", repo_url, "-o", tmp_file], check=True, env=env)
        
        console.print("📦 Extracting binary...")
        # Extract jarvis from the tarball into /tmp
        subprocess.run(["tar", "-xzf", tmp_file, "-C", "/tmp", "jarvis"], check=True, env=env)
        
        new_exe = Path("/tmp/jarvis")
        if not new_exe.exists():
            console.print("[red]❌ Error: Extracted binary not found in tarball.[/red]")
            return

        console.print("🔄 Replacing current binary...")
        # Use shutil.copy2 to preserve permissions
        # On Linux, we can overwrite a running binary if we have permissions
        shutil.copy2(new_exe, current_exe)
        os.chmod(current_exe, 0o755)
        
        console.print("\n✨ [bold green]JARVIS has been successfully updated to the latest version![/bold green]")
        
    except subprocess.CalledProcessError:
        console.print("[red]❌ Error: Failed to download or extract the latest version.[/red]")
    except PermissionError:
        console.print("[red]❌ Error: Permission denied. Try running with sudo if necessary.[/red]")
    except Exception as e:
        console.print(f"[red]❌ Update failed: {e}[/red]")
    finally:
        # Cleanup
        if os.path.exists(tmp_file): os.remove(tmp_file)
        if os.path.exists("/tmp/jarvis"): os.remove("/tmp/jarvis")
