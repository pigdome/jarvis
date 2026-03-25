import typer
import subprocess
import os
import sys
import shutil
from pathlib import Path
from typing import Optional
from jarvis.config import get_secrets, save_secrets, LEGACY_DIR, JARVIS_ROOT, CONFIG_DIR, BIN_DIR

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
