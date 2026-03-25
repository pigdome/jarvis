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

# These point to bundled data
SCRIPTS_DIR = BUNDLE_DIR / "scripts"
CONFIG_DIR = BUNDLE_DIR / "config"
BIN_DIR = BUNDLE_DIR / "bin"
MODULE_DIR = BUNDLE_DIR / "module"
LIB_DIR = BUNDLE_DIR / "lib"
INTERNAL_DIR = SCRIPTS_DIR / "internal"
LEGACY_DIR = SCRIPTS_DIR / "legacy"

# Secrets paths
SECRETS_PATH = JARVIS_ROOT / "secrets.json"
BUNDLED_SECRETS_PATH = BUNDLE_DIR / "secrets.json"


def get_secrets():
    """
    Get secrets from home directory, fallback to bundled secrets.json.
    """
    # Priority 1: User's home dir
    if SECRETS_PATH.exists():
        with open(SECRETS_PATH, "r") as f:
            return json.load(f)
    
    # Priority 2: Bundled secrets in the package
    if BUNDLED_SECRETS_PATH.exists():
        with open(BUNDLED_SECRETS_PATH, "r") as f:
            return json.load(f)
            
    return {}


def save_secrets(secrets):
    """
    Saves secrets to ~/.jarvis/secrets.json
    """
    JARVIS_ROOT.mkdir(parents=True, exist_ok=True)
    with open(SECRETS_PATH, "w") as f:
        json.dump(secrets, f, indent=4)
