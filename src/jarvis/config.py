import json
import os
import sys
from pathlib import Path

# Base directory for the application source or bundle
if getattr(sys, 'frozen', False):
    # If running as a bundled executable (PyInstaller)
    BUNDLE_DIR = Path(sys._MEIPASS)
else:
    # If running from source, project root is up from src/jarvis/
    # src/jarvis/config.py -> parent(jarvis) -> parent(src) -> parent(root)
    BUNDLE_DIR = Path(__file__).resolve().parent.parent.parent

# JARVIS_ROOT is where user data (runtime secrets) lives
JARVIS_ROOT = Path.home() / ".jarvis"

# Helper to find existing paths from a list of candidates
def find_first_existing(paths, default):
    for p in paths:
        if p.exists():
            return p
    return default

# 1. Look for 'config' directory in priority order
possible_configs = [
    Path.cwd() / "config",                          # Current Working Directory
    Path("/etc/jarvis"),                             # System-wide config (production)
    Path(sys.executable).parent / "config",         # Next to the jarvis binary
    JARVIS_ROOT / "config",                         # ~/.jarvis/config
    BUNDLE_DIR / "config",                          # Inside the bundled app (if any)
]
CONFIG_DIR = find_first_existing(possible_configs, BUNDLE_DIR / "config")

# These point to bundled data or fallbacks
SCRIPTS_DIR = BUNDLE_DIR / "scripts"
BIN_DIR = BUNDLE_DIR / "bin"
MODULE_DIR = find_first_existing([Path.cwd() / "module", Path(sys.executable).parent / "module", BUNDLE_DIR / "module"], BUNDLE_DIR / "module")
LIB_DIR = find_first_existing([Path.cwd() / "lib", Path(sys.executable).parent / "lib", BUNDLE_DIR / "lib"], BUNDLE_DIR / "lib")
INTERNAL_DIR = SCRIPTS_DIR / "internal"
LEGACY_DIR = SCRIPTS_DIR / "legacy"

# Secrets paths
SECRETS_PATH = JARVIS_ROOT / "secrets.json"


def get_secrets():
    """
    Get secrets from home directory, next to binary, or fallback to bundled secrets.json.
    """
    possible_secrets = [
        SECRETS_PATH,                                # 1. ~/.jarvis/secrets.json
        Path("/etc/jarvis/secrets.json"),            # 2. System-wide (production)
        Path.cwd() / "secrets.json",                 # 3. Current Working Directory
        Path(sys.executable).parent / "secrets.json",# 4. Next to the binary
        BUNDLE_DIR / "secrets.json",                 # 5. Bundled in the package
    ]
    
    secret_file = find_first_existing(possible_secrets, None)
    if secret_file and secret_file.exists():
        try:
            with open(secret_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
            
    return {}


def save_secrets(secrets):
    """
    Saves secrets to ~/.jarvis/secrets.json
    """
    JARVIS_ROOT.mkdir(parents=True, exist_ok=True)
    with open(SECRETS_PATH, "w") as f:
        json.dump(secrets, f, indent=4)
