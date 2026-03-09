#!/usr/bin/env bash
# AJS Build Script — macOS
# Produces: installer/dist/AJS_Setup (app bundle or single binary)
#
# Prerequisites:
#   Python 3.10+, pip, internet connection
#   Homebrew (optional, for fzf)
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
echo "[AJS Build] Installing/upgrading PyInstaller and requests..."
pip3 install --upgrade pyinstaller requests

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
    --hidden-import pygetwindow \
    --hidden-import pyperclip \
    --hidden-import requests \
    --collect-all pykakasi \
    --collect-all edge_tts \
    --collect-all yt_dlp

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
    echo "[AJS Build] WARNING: Homebrew not found — fzf will be downloaded at install time."
fi

# ── Step 3: Build AJS_Setup ──
echo ""
echo "[AJS Build] Step 3: Building AJS_Setup..."
cd "$SCRIPT_DIR"

EXTRA_DATA=""
[ -f "$SCRIPT_DIR/dist_ajs/ajs" ] && EXTRA_DATA="$EXTRA_DATA --add-data dist_ajs/ajs:."
[ -f "$SCRIPT_DIR/fzf"          ] && EXTRA_DATA="$EXTRA_DATA --add-data fzf:."

pyinstaller \
    --onefile \
    --name AJS_Setup \
    --windowed \
    --distpath "$SCRIPT_DIR/dist" \
    --workpath "$SCRIPT_DIR/build" \
    --specpath "$SCRIPT_DIR" \
    installer.py \
    $EXTRA_DATA \
    --add-data "$PROJECT_ROOT/ajs_addon:ajs_addon" \
    --hidden-import tkinter \
    --hidden-import tkinter.ttk \
    --hidden-import tkinter.scrolledtext \
    --hidden-import requests

# ── Step 4: Build AJS_Setup.pkg ──
echo ""
echo "[AJS Build] Step 4: Building AJS_Setup.pkg..."

PKG_STAGE="$SCRIPT_DIR/pkg_stage"
PKG_SCRIPTS="$SCRIPT_DIR/pkg_scripts"
PKG_ROOT="$PKG_STAGE/root"
PKG_OUT="$SCRIPT_DIR/dist/AJS_Setup.pkg"

# Clean staging area
rm -rf "$PKG_STAGE"
mkdir -p "$PKG_ROOT/Applications"
mkdir -p "$PKG_SCRIPTS"

# Copy the frozen installer app into the package root.
# pkgbuild installs everything in root/ relative to /.
# We want the installer to land somewhere accessible, so we
# put it in /Applications temporarily; the postinstall script runs it.
cp "$SCRIPT_DIR/dist/AJS_Setup" "$PKG_ROOT/Applications/AJS_Setup"
chmod +x "$PKG_ROOT/Applications/AJS_Setup"

# postinstall script — runs as the logged-in user after files are placed.
cat > "$PKG_SCRIPTS/postinstall" << 'POSTINSTALL'
#!/bin/bash
# Run the AJS installer as the actual user (not root).
LOGGED_IN_USER=$(stat -f "%Su" /dev/console 2>/dev/null || echo "$USER")
if [ -n "$LOGGED_IN_USER" ] && [ "$LOGGED_IN_USER" != "root" ]; then
    sudo -u "$LOGGED_IN_USER" open -W /Applications/AJS_Setup
else
    open -W /Applications/AJS_Setup
fi
# Remove the launcher from Applications once setup is done.
rm -f /Applications/AJS_Setup
exit 0
POSTINSTALL
chmod +x "$PKG_SCRIPTS/postinstall"

# Build the component package
pkgbuild \
    --root "$PKG_ROOT" \
    --scripts "$PKG_SCRIPTS" \
    --identifier "com.ajs.setup" \
    --version "1.0.0" \
    --install-location "/" \
    "$SCRIPT_DIR/dist/ajs_component.pkg"

if [ $? -ne 0 ]; then
    echo "[AJS Build] ERROR: pkgbuild failed."
    exit 1
fi

# Wrap in a product archive with standard macOS installer UI.
# distribution.xml controls the welcome/licence/install screens.
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

# Welcome page shown in the macOS installer
mkdir -p "$PKG_STAGE/resources"
cat > "$PKG_STAGE/resources/welcome.html" << 'WELCOME'
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system; padding: 20px;">
<h2>Anki Japanese Sensei</h2>
<p>This installer will set up everything you need to turn Japanese YouTube videos into Anki flashcards:</p>
<ul>
  <li>Ollama (local AI — runs offline)</li>
  <li>qwen2.5:3b language model (~2 GB download)</li>
  <li>fzf (transcript selector)</li>
  <li>AJS Anki add-on</li>
</ul>
<p><b>Requires:</b> Anki installed, internet connection for initial setup.</p>
</body>
</html>
WELCOME

cat > "$PKG_STAGE/resources/conclusion.html" << 'CONCLUSION'
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system; padding: 20px;">
<h2>Setup complete!</h2>
<p>Open Anki and press <b>Ctrl+E</b> to create your first card.</p>
<p>Log file: <code>~/.ajs/anki_addon.log</code></p>
</body>
</html>
CONCLUSION

productbuild \
    --distribution "$DIST_XML" \
    --resources "$PKG_STAGE/resources" \
    --package-path "$SCRIPT_DIR/dist" \
    "$PKG_OUT"

if [ $? -ne 0 ]; then
    echo "[AJS Build] ERROR: productbuild failed."
    exit 1
fi

# Clean up component pkg — only the final .pkg is needed
rm -f "$SCRIPT_DIR/dist/ajs_component.pkg"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Build complete!                             ║"
echo "║  Output: installer/dist/AJS_Setup.pkg        ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
