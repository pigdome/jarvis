#!/bin/bash

# JARVIS Standalone Build Script
# Uses PyInstaller to bundle the CLI into a single executable

set -e
trap 'echo "❌ Build failed at line $LINENO: $BASH_COMMAND" >&2' ERR

JARVIS_DIR=$(pwd)
DIST_DIR="$JARVIS_DIR/dist"
BUILD_DIR="$JARVIS_DIR/build"

echo "🏗️  Starting JARVIS build process..."

read_one_char() {
    local var_name="$1"
    local prompt="$2"

    if [ -t 0 ]; then
        read -p "$prompt" -n 1 -r "$var_name"
        echo
        return 0
    fi

    if read -p "$prompt" -n 1 -r "$var_name" 2>/dev/null < /dev/tty; then
        echo
        return 0
    fi

    return 1
}

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
if ! read_one_char BUMP_CHOICE "👉 Choose an option [1-4] (default 1): "; then
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

# 4. Build the executable inside a Debian 10 (glibc 2.28) container.
# PyInstaller links libpython against the build machine's glibc, and glibc is
# forward-compatible only, so building locally (this machine has glibc 2.39)
# would produce a binary that can't run on older OSs like Debian 10/11 or
# Ubuntu 20.04/22.04. Building against glibc 2.28 keeps it runnable everywhere newer.
echo "🚀 Running PyInstaller inside debian:10 container for old-OS compatibility..."
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Error: docker is required to build a backward-compatible binary, but it's not installed."
    exit 1
fi

docker run --rm -v "$JARVIS_DIR":/repo -w /repo debian:10 bash -lc '
    set -e
    trap '\''echo "❌ Container build failed at line $LINENO: $BASH_COMMAND" >&2'\'' ERR
    export DEBIAN_FRONTEND=noninteractive
    # Debian 10 (buster) is EOL and removed from the regular mirrors; use the archive instead.
    sed -i "s|deb.debian.org|archive.debian.org|g; s|security.debian.org|archive.debian.org|g" /etc/apt/sources.list
    echo "Acquire::Check-Valid-Until \"false\";" > /etc/apt/apt.conf.d/99no-check-valid-until
    apt-get update
    apt-get install -y --no-install-recommends \
        build-essential wget ca-certificates \
        zlib1g-dev libffi-dev libssl-dev libbz2-dev \
        libreadline-dev libsqlite3-dev liblzma-dev libncurses5-dev

    if [ ! -x /usr/local/python3.12/bin/python3.12 ]; then
        PY_VERSION=3.12.7
        PY_BUILD_JOBS="${PYTHON_BUILD_JOBS:-2}"
        PY_BUILD_ROOT=/tmp/python-build
        rm -rf "$PY_BUILD_ROOT"
        mkdir -p "$PY_BUILD_ROOT"
        cd "$PY_BUILD_ROOT"

        wget -q https://www.python.org/ftp/python/${PY_VERSION}/Python-${PY_VERSION}.tgz
        tar -xzf Python-${PY_VERSION}.tgz
        cd Python-${PY_VERSION}
        ./configure --prefix=/usr/local/python3.12 --enable-shared --with-ensurepip=install
        make -j"$PY_BUILD_JOBS"
        make altinstall
        cd /repo
    fi

    export LD_LIBRARY_PATH="/usr/local/python3.12/lib:${LD_LIBRARY_PATH}"
    PYBIN=/usr/local/python3.12/bin/python3.12
    $PYBIN -m pip install --upgrade pip
    $PYBIN -m pip install -r requirements.txt
    $PYBIN -m pip install -e .
    $PYBIN -m pip install pyinstaller

    /usr/local/python3.12/bin/pyinstaller --onefile \
        --name jarvis \
        --add-data "config:config" \
        --add-data "config/.vimrc:config" \
        --add-data "config/authorized_keys:config" \
        --add-data "module:module" \
        --add-data "lib:lib" \
        --clean \
        src/jarvis/main.py
'

# Files written by the container are owned by root; reclaim them for the local user.
sudo -n chown -R "$(id -u):$(id -g)" "$DIST_DIR" "$BUILD_DIR" 2>/dev/null || true

echo ""
echo "✨ Build complete!"
echo "📍 Executable: $DIST_DIR/jarvis"

# 6. Git Tag and Release
echo ""
if ! read_one_char REPLY "❓ Do you want to create a git tag v$VERSION and push to GitHub? [y/N]: "; then
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
if ! read_one_char REPLY "❓ Do you want to copy jarvis to ~/.local/bin/jarvis? [y/N]: "; then
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
