#!/bin/bash

# JARVIS Rework Installer
# Migrates to the new Python CLI

set -e

JARVIS_DIR="$HOME/.jarvis"
BIN_DIR="$JARVIS_DIR/bin"

echo "🚀 Starting JARVIS Rework Installation..."

# 1. Install dependencies
echo "📦 Installing Python dependencies..."
pip install -e "$JARVIS_DIR"

# 2. Migrate Secrets
echo "🔑 Migrating secrets from legacy scripts..."
export PYTHONPATH="$JARVIS_DIR/src:$PYTHONPATH"
python3 "$JARVIS_DIR/src/jarvis/migrate_secrets.py"

# 3. Setup Shell Completion
echo "⌨️ Setting up tab completion..."
# Typer automatically handles completion script generation
setup_completion() {
	local shell_bin=$1
	local profile_file=$2
	if [ -f "$profile_file" ]; then
		if ! grep -q "jarvis --show-completion" "$profile_file" && ! grep -q "_JARVIS_COMPLETE" "$profile_file"; then
			echo -e "\n# JARVIS Python CLI Completion" >>"$profile_file"
			echo "eval \"\$(jarvis --show-completion $shell_bin)\"" >>"$profile_file"
			echo "✅ Added completion to $profile_file"
		fi
	fi
}

setup_completion bash "$HOME/.bashrc"
setup_completion zsh "$HOME/.zshrc"

echo ""
echo "✨ JARVIS migration complete!"
echo "🔄 Please run: source ~/.bashrc (or restart your terminal)"
echo "💡 Try it out: jarvis --help"
