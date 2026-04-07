#!/bin/bash

# JARVIS Standalone Build Script
# Uses PyInstaller to bundle the CLI into a single executable

set -e

JARVIS_DIR=$(pwd)
DIST_DIR="$JARVIS_DIR/dist"
BUILD_DIR="$JARVIS_DIR/build"

echo "🏗️  Starting JARVIS build process..."

# 1. Ensure we are in the right directory
cd "$JARVIS_DIR"

# Detect Python executable (prefer venv if active or available)
if [ -f "venv/bin/python3" ]; then
    PYTHON_BIN="$JARVIS_DIR/venv/bin/python3"
    PIP_BIN="$JARVIS_DIR/venv/bin/pip"
elif [ -f ".venv/bin/python3" ]; then
    PYTHON_BIN="$JARVIS_DIR/.venv/bin/python3"
    PIP_BIN="$JARVIS_DIR/.venv/bin/pip"
else
    PYTHON_BIN="python3"
    PIP_BIN="pip3"
fi

# 2. Extract current version
CURRENT_VERSION=$($PYTHON_BIN -c "import sys; sys.path.insert(0, 'src'); from jarvis import __version__; print(__version__)")
echo "🏷️  Current Version: v$CURRENT_VERSION"

# 3. Version Bumping Stage
echo ""
echo "🔄 Version Management:"
echo "   [1] No Change (Stay at $CURRENT_VERSION)"
echo "   [2] Patch (v$CURRENT_VERSION -> $($PYTHON_BIN -c "v = '$CURRENT_VERSION'.split('.'); v[-1] = str(int(v[-1])+1); print('.'.join(v))"))"
echo "   [3] Minor (v$CURRENT_VERSION -> $($PYTHON_BIN -c "v = '$CURRENT_VERSION'.split('.'); v[1] = str(int(v[1])+1); v[2] = '0'; print('.'.join(v))"))"
echo "   [4] Major (v$CURRENT_VERSION -> $($PYTHON_BIN -c "v = '$CURRENT_VERSION'.split('.'); v[0] = str(int(v[0])+1); v[1] = '0'; v[2] = '0'; print('.'.join(v))"))"

# Use /dev/tty to read if available, otherwise read from stdin
if [ -t 0 ]; then
    read -p "👉 Choose an option [1-4] (default 1): " -n 1 -r BUMP_CHOICE
    echo
else
    # Non-interactive mode (e.g. piped input)
    read -r BUMP_CHOICE || BUMP_CHOICE="1"
fi
echo ""

case $BUMP_CHOICE in
    2)
        NEW_VERSION=$($PYTHON_BIN -c "v = '$CURRENT_VERSION'.split('.'); v[-1] = str(int(v[-1])+1); print('.'.join(v))")
        ;;
    3)
        NEW_VERSION=$($PYTHON_BIN -c "v = '$CURRENT_VERSION'.split('.'); v[1] = str(int(v[1])+1); v[2] = '0'; print('.'.join(v))")
        ;;
    4)
        NEW_VERSION=$($PYTHON_BIN -c "v = '$CURRENT_VERSION'.split('.'); v[0] = str(int(v[0])+1); v[1] = '0'; v[2] = '0'; print('.'.join(v))")
        ;;
    *)
        NEW_VERSION=$CURRENT_VERSION
        ;;
esac

if [ "$NEW_VERSION" != "$CURRENT_VERSION" ]; then
    echo "🆙 Bumping version to v$NEW_VERSION..."
    # Update src/jarvis/__init__.py
    sed -i "s/__version__ = .*/__version__ = \"$NEW_VERSION\"/" src/jarvis/__init__.py
    # Update pyproject.toml
    sed -i "s/^version = .*/version = \"$NEW_VERSION\"/" pyproject.toml
    echo "✅ Files updated."
else
    echo "⏺️  Keeping version at v$CURRENT_VERSION."
fi

VERSION=$NEW_VERSION

# 4. Setup build environment
echo "📦 Installing dependencies and PyInstaller..."
$PIP_BIN install -r requirements.txt || $PYTHON_BIN -m pip install -r requirements.txt
$PIP_BIN install -e . || $PYTHON_BIN -m pip install -e .

# 5. Build the executable
echo "🚀 Running PyInstaller..."
# Find pyinstaller in venv or path
PYI_BIN=$($PYTHON_BIN -c "import sys; import os; print(os.path.join(os.path.dirname(sys.executable), 'pyinstaller'))")
if [ ! -f "$PYI_BIN" ]; then
    PYI_BIN="pyinstaller"
fi

"$PYI_BIN" --onefile \
    --name jarvis \
    --add-data "config:config" \
    --add-data "config/.vimrc:config" \
    --add-data "config/authorized_keys:config" \
    --add-data "module:module" \
    --add-data "lib:lib" \
    --clean \
    src/jarvis/main.py

echo ""
echo "✨ Build complete!"
echo "📍 Executable: $DIST_DIR/jarvis"

# 6. Git Tag and Release
echo ""
if [ -t 0 ]; then
    read -p "❓ Do you want to create a git tag v$VERSION and push to GitHub? [y/N]: " -n 1 -r
    echo
else
    # Non-interactive skip tagging
    REPLY="n"
fi

if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Commiting version bump if any
    if [ "$NEW_VERSION" != "$CURRENT_VERSION" ]; then
        echo "💾 Committing version bump..."
        git add -u
        git commit -m "chore: bump version to v$VERSION"
        git push origin main
    fi

    echo "🐙 Tagging v$VERSION..."
    if git rev-parse "v$VERSION" >/dev/null 2>&1; then
        echo "⚠️  Tag v$VERSION already exists. Skipping tag creation."
    else
        git tag "v$VERSION"
        echo "✅ Created tag v$VERSION"
    fi
    
    echo "⬆️  Pushing tag to origin..."
    git push origin "v$VERSION"
    echo "🚀 Tag pushed! GitHub Actions should start the release process."
else
    echo "⏭️  Skipped git tagging."
fi

# 7. Install to ~/.local/bin
echo ""
if [ -t 0 ]; then
    read -p "❓ Do you want to copy jarvis to ~/.local/bin/jarvis? [y/N]: " -n 1 -r
    echo
else
    # Non-interactive skip installation
    REPLY="n"
fi

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📋 Copying to ~/.local/bin/jarvis..."
    mkdir -p ~/.local/bin
    cp "$DIST_DIR/jarvis" ~/.local/bin/jarvis
    chmod +x ~/.local/bin/jarvis
    echo "✅ Installed at ~/.local/bin/jarvis"
    echo "💡 Make sure ~/.local/bin is in your PATH."
else
    echo "⏭️  Skipped installation to ~/.local/bin."
fi

# 8. Copy executable to root for easy download
echo ""
echo "📂 Copying executable to root directory..."
cp "$DIST_DIR/jarvis" "$JARVIS_DIR/jarvis"
echo "✅ Done! You can now download the executable from the root folder ($JARVIS_DIR/jarvis)."
