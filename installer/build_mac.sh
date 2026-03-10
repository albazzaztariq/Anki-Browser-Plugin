#!/usr/bin/env bash
# AJS Build Script — macOS
# Produces: installer/dist/AJS_Setup.pkg
#
# What this does:
#   1. Builds the `ajs` binary with PyInstaller
#   2. Downloads fzf
#   3. Packages everything into a native macOS .pkg
#      - ajs  → /usr/local/bin/ajs        (already on PATH — no manual PATH setup)
#      - fzf  → /usr/local/bin/fzf
#      - ajs_addon/ → /Library/AJS/ajs_addon/
#      - setup.sh → /Library/AJS/setup.sh  (model download + Anki add-on install)
#   4. postinstall opens a Terminal window running setup.sh
#
# Usage:
#   cd installer && chmod +x build_mac.sh && ./build_mac.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║      AJS Build Script — macOS               ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "[AJS Build] Project root : $PROJECT_ROOT"
echo "[AJS Build] Installer dir: $SCRIPT_DIR"
echo ""

# ── Prerequisites ──
echo "[AJS Build] Installing Python dependencies..."
pip3 install --upgrade pyinstaller
pip3 install -r "$PROJECT_ROOT/terminal/requirements.txt"

# ── Step 1: Build ajs (CLI tool) ──
echo ""
echo "[AJS Build] Step 1: Building ajs binary..."
cd "$PROJECT_ROOT"
pyinstaller \
    --onefile \
    --name ajs \
    --distpath "$SCRIPT_DIR/dist_ajs" \
    --workpath "$SCRIPT_DIR/build_ajs" \
    --specpath "$SCRIPT_DIR" \
    terminal/ajs.py \
    --hidden-import pykakasi \
    --hidden-import edge_tts \
    --hidden-import yt_dlp \
    --hidden-import pyperclip \
    --hidden-import requests \
    --hidden-import faster_whisper \
    --collect-all pykakasi \
    --collect-all edge_tts \
    --collect-all yt_dlp \
    --collect-all faster_whisper

echo "[AJS Build] ajs binary built: $SCRIPT_DIR/dist_ajs/ajs"

# ── Step 2: Download fzf ──
echo ""
echo "[AJS Build] Step 2: Obtaining fzf..."
FZF_EXE="$SCRIPT_DIR/fzf"
if [ -f "$FZF_EXE" ]; then
    echo "[AJS Build] fzf already present — skipping."
elif command -v brew &>/dev/null; then
    brew install fzf
    FZF_BREW="$(brew --prefix)/bin/fzf"
    if [ -f "$FZF_BREW" ]; then
        cp "$FZF_BREW" "$FZF_EXE"
        echo "[AJS Build] fzf copied from Homebrew: $FZF_EXE"
    fi
else
    echo "[AJS Build] WARNING: Homebrew not found — downloading fzf from GitHub..."
    ARCH=$(uname -m)
    if [ "$ARCH" = "arm64" ]; then
        FZF_SUFFIX="darwin_arm64"
    else
        FZF_SUFFIX="darwin_amd64"
    fi
    # Get the latest release tag and build the correct asset URL
    FZF_TAG=$(curl -fsSL "https://api.github.com/repos/junegunn/fzf/releases/latest" | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"//;s/".*//')
    FZF_VER="${FZF_TAG#v}"  # strip leading 'v'
    FZF_URL="https://github.com/junegunn/fzf/releases/download/${FZF_TAG}/fzf-${FZF_VER}-${FZF_SUFFIX}.tar.gz"
    echo "[AJS Build] Downloading fzf from: $FZF_URL"
    curl -fsSL "$FZF_URL" | tar -xz -C "$SCRIPT_DIR"
    echo "[AJS Build] fzf downloaded: $FZF_EXE"
fi

# ── Step 3: Build AJS_Setup.pkg ──
echo ""
echo "[AJS Build] Step 3: Building AJS_Setup.pkg..."

PKG_STAGE="$SCRIPT_DIR/pkg_stage"
PKG_SCRIPTS="$SCRIPT_DIR/pkg_scripts"
PKG_ROOT="$PKG_STAGE/root"
PKG_OUT="$SCRIPT_DIR/dist/AJS_Setup.pkg"

# Clean staging area
rm -rf "$PKG_STAGE" "$PKG_SCRIPTS"
mkdir -p "$PKG_ROOT/usr/local/bin"
mkdir -p "$PKG_ROOT/Library/AJS"
mkdir -p "$PKG_SCRIPTS"
mkdir -p "$SCRIPT_DIR/dist"

# Place ajs binary
cp "$SCRIPT_DIR/dist_ajs/ajs" "$PKG_ROOT/usr/local/bin/ajs"
chmod +x "$PKG_ROOT/usr/local/bin/ajs"

# Place fzf binary (if available)
if [ -f "$FZF_EXE" ]; then
    cp "$FZF_EXE" "$PKG_ROOT/usr/local/bin/fzf"
    chmod +x "$PKG_ROOT/usr/local/bin/fzf"
fi

# Place Anki add-on
cp -r "$PROJECT_ROOT/ajs_addon" "$PKG_ROOT/Library/AJS/ajs_addon"

# setup.sh — the visible terminal script that runs after install
# (handles model download + Anki add-on copy + Ollama install)
cat > "$PKG_ROOT/Library/AJS/setup.sh" << 'SETUP_SH'
#!/usr/bin/env bash
# AJS post-install setup
# Runs in a Terminal window after the .pkg installs the binaries.

set -o pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✓ $*${NC}"; }
info() { echo -e "  $*"; }
warn() { echo -e "${YELLOW}  ⚠ $*${NC}"; }
err()  { echo -e "${RED}  ✗ $*${NC}"; }

echo ""
echo "═══════════════════════════════════════════"
echo "   Anki Japanese Sensei — Setup"
echo "═══════════════════════════════════════════"
echo ""

# ── 1. Ollama ──
info "Checking Ollama..."
if command -v ollama &>/dev/null; then
    ok "Ollama already installed."
else
    if command -v brew &>/dev/null; then
        info "Installing Ollama via Homebrew..."
        brew install ollama
    else
        info "Installing Ollama (may require admin password)..."
        curl -fsSL https://ollama.com/install.sh | sh
    fi
    if command -v ollama &>/dev/null; then
        ok "Ollama installed."
    else
        err "Ollama installation failed. Please install manually: https://ollama.com/download"
        err "Then re-run: /Library/AJS/setup.sh"
        read -p "  Press Enter to close..."
        exit 1
    fi
fi

# Ensure Ollama service is running
if ! pgrep -qf "ollama" &>/dev/null; then
    info "Starting Ollama service..."
    ollama serve &>/dev/null &
    sleep 5
fi

# ── 2. AI model ──
info "Checking AI model (qwen2.5:3b)..."
if ollama list 2>/dev/null | grep -q "qwen2.5:3b"; then
    ok "Model already present — skipping download."
else
    info "Downloading qwen2.5:3b (~2 GB) — this takes a few minutes..."
    ollama pull qwen2.5:3b
    ok "Model downloaded."
fi

# ── 3. Anki add-on ──
info "Installing Anki add-on..."
ANKI_ADDONS_BASE="$HOME/Library/Application Support/Anki2"
# Find the Anki profile (first one found)
if [ -d "$ANKI_ADDONS_BASE" ]; then
    ADDONS_DIR=$(find "$ANKI_ADDONS_BASE" -maxdepth 2 -type d -name "addons21" | head -1)
    if [ -n "$ADDONS_DIR" ]; then
        cp -r /Library/AJS/ajs_addon "$ADDONS_DIR/ajs_addon"
        ok "Add-on installed to: $ADDONS_DIR/ajs_addon"
    else
        warn "Anki addons21 folder not found. Open Anki once, then re-run:"
        warn "  cp -r /Library/AJS/ajs_addon ~/Library/Application\\ Support/Anki2/*/addons21/"
    fi
else
    warn "Anki not found. Install Anki (ankiweb.net), then re-run:"
    warn "  cp -r /Library/AJS/ajs_addon ~/Library/Application\\ Support/Anki2/*/addons21/"
fi

# ── Done ──
echo ""
echo "═══════════════════════════════════════════"
ok "Setup complete!"
echo ""
info "  → Open Anki"
info "  → Watch a Japanese YouTube video in Chrome"
info "  → Press Ctrl+Shift+E to create your first card"
echo ""
echo "═══════════════════════════════════════════"
echo ""
read -p "  Press Enter to close..."
SETUP_SH

chmod +x "$PKG_ROOT/Library/AJS/setup.sh"

# ── postinstall script ──
# Runs as root after files are placed.
# Opens a Terminal window running setup.sh as the logged-in user.
cat > "$PKG_SCRIPTS/postinstall" << 'POSTINSTALL'
#!/bin/bash
LOGGED_IN_USER=$(stat -f "%Su" /dev/console 2>/dev/null || echo "$USER")

# Ensure permissions
chmod +x /usr/local/bin/ajs
[ -f /usr/local/bin/fzf ] && chmod +x /usr/local/bin/fzf
chmod +x /Library/AJS/setup.sh

# Open Terminal running setup.sh as the actual user (not root)
if [ -n "$LOGGED_IN_USER" ] && [ "$LOGGED_IN_USER" != "root" ]; then
    sudo -u "$LOGGED_IN_USER" osascript \
        -e 'tell application "Terminal"' \
        -e '    do script "/Library/AJS/setup.sh"' \
        -e '    activate' \
        -e 'end tell'
else
    osascript \
        -e 'tell application "Terminal"' \
        -e '    do script "/Library/AJS/setup.sh"' \
        -e '    activate' \
        -e 'end tell'
fi

exit 0
POSTINSTALL
chmod +x "$PKG_SCRIPTS/postinstall"

# ── Build component package ──
pkgbuild \
    --root "$PKG_ROOT" \
    --scripts "$PKG_SCRIPTS" \
    --identifier "com.ajs.setup" \
    --version "1.0.0" \
    --install-location "/" \
    "$SCRIPT_DIR/dist/ajs_component.pkg"

# ── distribution.xml ──
DIST_XML="$PKG_STAGE/distribution.xml"
cat > "$DIST_XML" << 'DISTXML'
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>Anki Japanese Sensei</title>
    <welcome    file="welcome.html" mime-type="text/html" />
    <conclusion file="conclusion.html" mime-type="text/html" />
    <options customize="never" require-scripts="false" rootVolumeOnly="true" />
    <pkg-ref id="com.ajs.setup" />
    <choices-outline>
        <line choice="com.ajs.setup" />
    </choices-outline>
    <choice id="com.ajs.setup" title="Anki Japanese Sensei">
        <pkg-ref id="com.ajs.setup" />
    </choice>
    <pkg-ref id="com.ajs.setup" version="1.0.0">ajs_component.pkg</pkg-ref>
</installer-gui-script>
DISTXML

mkdir -p "$PKG_STAGE/resources"

cat > "$PKG_STAGE/resources/welcome.html" << 'WELCOME'
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system; padding: 20px;">
<h2>Anki Japanese Sensei</h2>
<p>This installer will set up everything you need to turn Japanese YouTube videos into Anki flashcards:</p>
<ul>
  <li><b>ajs</b> — the command-line tool (installed to /usr/local/bin)</li>
  <li><b>fzf</b> — fuzzy subtitle picker</li>
  <li><b>Ollama</b> — local AI runtime (offline, no API key)</li>
  <li><b>qwen2.5:3b</b> — AI language model (~2 GB)</li>
  <li><b>AJS Anki add-on</b> — adds the card to your deck</li>
</ul>
<p><b>Requires:</b> Anki installed · Chrome browser · internet for initial download only.</p>
</body>
</html>
WELCOME

cat > "$PKG_STAGE/resources/conclusion.html" << 'CONCLUSION'
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system; padding: 20px;">
<h2>Almost done!</h2>
<p>A Terminal window is setting up the AI model in the background.</p>
<p>Once it finishes, open Anki and press <b>Ctrl+Shift+E</b> while watching a Japanese YouTube video.</p>
<p style="color: #666; font-size: 0.9em;">Log: <code>~/.ajs/anki_addon.log</code></p>
</body>
</html>
CONCLUSION

productbuild \
    --distribution "$DIST_XML" \
    --resources "$PKG_STAGE/resources" \
    --package-path "$SCRIPT_DIR/dist" \
    "$PKG_OUT"

# Clean up component pkg
rm -f "$SCRIPT_DIR/dist/ajs_component.pkg"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Build complete!                             ║"
echo "║  Output: installer/dist/AJS_Setup.pkg        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
