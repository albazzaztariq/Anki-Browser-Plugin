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

# Ensure Python user-installed tools (pyinstaller, etc.) are on PATH
# Works for Python 3.9–3.13; also covers Homebrew Python locations
for _pyver in 3.9 3.10 3.11 3.12 3.13; do
    _pth="$HOME/Library/Python/$_pyver/bin"
    [ -d "$_pth" ] && export PATH="$_pth:$PATH"
done
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

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

# If this script is killed or the Terminal is closed before completion,
# write an incomplete marker so the user knows what happened.
AJS_STATUS_FILE="$HOME/.ajs/setup_status"
mkdir -p "$HOME/.ajs"
echo "incomplete" > "$AJS_STATUS_FILE"

_on_exit() {
    if [ "$(cat "$AJS_STATUS_FILE" 2>/dev/null)" != "complete" ]; then
        echo ""
        echo "════════════════════════════════════════════════════"
        echo "  ✗ Setup did NOT complete — it was interrupted."
        echo "  Re-run to finish:  /Library/AJS/setup.sh"
        echo "════════════════════════════════════════════════════"
        echo ""
    fi
}
trap _on_exit EXIT

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

# Add common Ollama CLI locations to PATH
export PATH="$PATH:/usr/local/bin:$HOME/.ollama/bin:/Applications/Ollama.app/Contents/Resources"

ollama_running() {
    ollama list &>/dev/null 2>&1
}

wait_for_ollama() {
    for i in $(seq 1 20); do
        sleep 3
        if ollama_running; then return 0; fi
    done
    return 1
}

if command -v ollama &>/dev/null; then
    ok "Ollama already installed."
else
    if command -v brew &>/dev/null; then
        info "Installing Ollama via Homebrew..."
        if ! brew install ollama; then
            err "Homebrew install of Ollama failed."
            err "Please install Ollama manually from https://ollama.com/download"
            err "Then re-run: /Library/AJS/setup.sh"
            read -p "  Press Enter to close..."
            exit 1
        fi
    else
        info "Downloading Ollama (~300 MB)..."
        if ! curl -fsSL --progress-bar -o /tmp/Ollama.zip \
                "https://ollama.com/download/Ollama-darwin.zip"; then
            err "Download failed. Check your internet connection."
            err "Then re-run: /Library/AJS/setup.sh"
            read -p "  Press Enter to close..."
            exit 1
        fi
        info "Unpacking Ollama..."
        rm -rf /tmp/ollama_unzipped
        if ! unzip -q /tmp/Ollama.zip -d /tmp/ollama_unzipped; then
            err "Failed to unpack Ollama.zip."
            rm -f /tmp/Ollama.zip
            read -p "  Press Enter to close..."
            exit 1
        fi
        # Extract the ollama binary directly — avoids macOS "damaged app" Gatekeeper block
        OLLAMA_BIN="/tmp/ollama_unzipped/Ollama.app/Contents/Resources/ollama"
        if [ ! -f "$OLLAMA_BIN" ]; then
            err "ollama binary not found inside downloaded package."
            err "The download may be corrupted. Try re-running: /Library/AJS/setup.sh"
            rm -rf /tmp/Ollama.zip /tmp/ollama_unzipped
            read -p "  Press Enter to close..."
            exit 1
        fi
        info "Installing ollama to /usr/local/bin..."
        sudo cp "$OLLAMA_BIN" /usr/local/bin/ollama
        sudo chmod +x /usr/local/bin/ollama
        xattr -d com.apple.quarantine /usr/local/bin/ollama 2>/dev/null || true
        rm -rf /tmp/Ollama.zip /tmp/ollama_unzipped
        ok "Ollama installed."
    fi
fi

# Verify ollama binary is actually on PATH now
if ! command -v ollama &>/dev/null; then
    err "ollama command not found after install. Something went wrong."
    err "Try re-running: /Library/AJS/setup.sh"
    read -p "  Press Enter to close..."
    exit 1
fi

# Start Ollama server if not already running
if ! ollama_running; then
    info "Starting Ollama server..."
    if command -v brew &>/dev/null && brew list ollama &>/dev/null 2>&1; then
        brew services start ollama
    else
        ollama serve > /tmp/ollama.log 2>&1 &
    fi
    info "Waiting for Ollama to start (up to 60 seconds)..."
    if ! wait_for_ollama; then
        err "Ollama did not start within 60 seconds."
        err "Check /tmp/ollama.log for details."
        err "Then re-run: /Library/AJS/setup.sh"
        read -p "  Press Enter to close..."
        exit 1
    fi
fi

if ! ollama_running; then
    err "Ollama is not responding after startup. Installation failed."
    err "Then re-run: /Library/AJS/setup.sh"
    read -p "  Press Enter to close..."
    exit 1
fi
ok "Ollama is running."

# ── 2. AI model ──
info "Checking AI model (qwen2.5:3b)..."
if ollama list 2>/dev/null | grep -q "qwen2.5:3b"; then
    ok "Model already present — skipping download."
else
    info "Downloading AI model qwen2.5:3b (~2 GB) — this will take a few minutes..."
    if ! ollama pull qwen2.5:3b; then
        err "Model download failed."
        err "Check your internet connection and re-run: /Library/AJS/setup.sh"
        read -p "  Press Enter to close..."
        exit 1
    fi
    ok "Model downloaded."
fi

# ── 3. Anki add-on ──
info "Installing Anki add-on..."
ANKI_ADDONS_BASE="$HOME/Library/Application Support/Anki2"

# If Anki is installed but hasn't been opened yet, open it so it creates its profile
if [ ! -d "$ANKI_ADDONS_BASE" ]; then
    if [ -d "/Applications/Anki.app" ]; then
        info "Opening Anki to initialize profile (this takes a moment)..."
        open -a Anki
        # Wait up to 40 s for Anki to create its data directory
        for i in $(seq 1 20); do
            sleep 2
            [ -d "$ANKI_ADDONS_BASE" ] && break
        done
        sleep 3   # let Anki finish writing its folder structure
        osascript -e 'tell application "Anki" to quit' 2>/dev/null || true
        sleep 2
    fi
fi

if [ -d "$ANKI_ADDONS_BASE" ]; then
    ADDONS_DIR=$(find "$ANKI_ADDONS_BASE" -maxdepth 2 -type d -name "addons21" 2>/dev/null | head -1)
    if [ -z "$ADDONS_DIR" ]; then
        # Profile folder exists but addons21 not yet created — make the default path
        ADDONS_DIR="$ANKI_ADDONS_BASE/User 1/addons21"
        mkdir -p "$ADDONS_DIR"
    fi
    rm -rf "$ADDONS_DIR/ajs_addon"
    cp -r /Library/AJS/ajs_addon "$ADDONS_DIR/ajs_addon"
    ok "Add-on installed to: $ADDONS_DIR/ajs_addon"
else
    warn "Anki not installed. Install Anki (ankiweb.net) and open it once."
    warn "The add-on files are at /Library/AJS/ajs_addon — copy them to:"
    warn "  ~/Library/Application Support/Anki2/<Profile>/addons21/"
fi

# ── Final verification ──
echo ""
echo "═══════════════════════════════════════════"
info "Verifying installation..."
echo ""
SETUP_ERRORS=0

if ollama_running; then
    ok "Ollama server:   running"
else
    err "FAIL: Ollama server is not running."
    SETUP_ERRORS=$((SETUP_ERRORS+1))
fi

if ollama list 2>/dev/null | grep -q "qwen2.5:3b"; then
    ok "AI model:        installed"
else
    err "FAIL: AI model qwen2.5:3b is not installed."
    SETUP_ERRORS=$((SETUP_ERRORS+1))
fi

if [ -f "/usr/local/bin/ajs" ]; then
    ok "ajs binary:      installed"
else
    err "FAIL: ajs binary missing from /usr/local/bin/ajs"
    SETUP_ERRORS=$((SETUP_ERRORS+1))
fi

ADDON_OK=0
if find "$HOME/Library/Application Support/Anki2" -maxdepth 3 -type d -name "ajs_addon" 2>/dev/null | grep -q .; then
    ADDON_OK=1
fi
if [ $ADDON_OK -eq 1 ]; then
    ok "Anki add-on:     installed"
else
    warn "Anki add-on:     not yet installed (open Anki, then re-run /Library/AJS/setup.sh)"
fi

echo ""
echo "═══════════════════════════════════════════"
if [ $SETUP_ERRORS -gt 0 ]; then
    err "Setup finished with $SETUP_ERRORS error(s) — see above."
    err "Fix the errors above, then re-run: /Library/AJS/setup.sh"
    echo ""
    read -p "  Press Enter to close..."
    exit 1
else
    echo "complete" > "$AJS_STATUS_FILE"
    ok "Setup complete! Everything verified OK."
    echo ""
    info "  → Open Anki"
    info "  → Watch a Japanese YouTube video in Chrome"
    info "  → Press Ctrl+Shift+E to create your first card"
    echo ""
    echo "═══════════════════════════════════════════"
    echo ""
    read -p "  Press Enter to close..."
fi
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
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system; padding: 20px;">
<h2>Anki Japanese Sensei</h2>
<p>This installer will set up everything you need to turn Japanese YouTube videos into Anki flashcards:</p>
<ul>
  <li><b>ajs</b> &mdash; the command-line tool (installed to /usr/local/bin)</li>
  <li><b>fzf</b> &mdash; fuzzy subtitle picker</li>
  <li><b>Ollama</b> &mdash; local AI runtime (offline, no API key)</li>
  <li><b>qwen2.5:3b</b> &mdash; AI language model (~2 GB)</li>
  <li><b>AJS Anki add-on</b> &mdash; adds the card to your deck</li>
</ul>
<p><b>Requires:</b> Anki installed, Chrome browser, internet for initial download only.</p>
</body>
</html>
WELCOME

cat > "$PKG_STAGE/resources/conclusion.html" << 'CONCLUSION'
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system; padding: 20px;">
<h2>Almost done!</h2>
<p>A Terminal window is setting up the AI model in the background.</p>
<p>Once it finishes, open Anki and press <b>Ctrl+Shift+E</b> while watching a Japanese YouTube video.</p>
<p style="color: #666; font-size: 0.9em;">Log: <code>~/.ajs/anki_addon.log</code></p>
</body>
</html>
CONCLUSION

# ── uninstall.sh ──
cat > "$SCRIPT_DIR/dist/uninstall.sh" << 'UNINSTALL'
#!/usr/bin/env bash
# AJS Uninstaller

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
echo "   Anki Japanese Sensei — Uninstaller"
echo "═══════════════════════════════════════════"
echo ""
warn "This will remove:"
info "  • /usr/local/bin/ajs"
info "  • /usr/local/bin/fzf  (if installed by AJS)"
info "  • /usr/local/bin/ollama"
info "  • /Library/AJS/"
info "  • Anki add-on (ajs_addon)"
info "  • ~/.ajs/ (logs and config)"
echo ""
read -p "  Continue? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    info "Cancelled."
    echo ""
    exit 0
fi
echo ""

# Remove binaries
info "Removing binaries..."
sudo rm -f /usr/local/bin/ajs && ok "Removed /usr/local/bin/ajs" || warn "/usr/local/bin/ajs not found"
sudo rm -f /usr/local/bin/ollama && ok "Removed /usr/local/bin/ollama" || warn "/usr/local/bin/ollama not found"

# Only remove fzf if it came from AJS (check if /Library/AJS exists as a signal)
if [ -d "/Library/AJS" ]; then
    sudo rm -f /usr/local/bin/fzf && ok "Removed /usr/local/bin/fzf" || true
fi

# Remove AJS system files
info "Removing /Library/AJS/..."
sudo rm -rf /Library/AJS && ok "Removed /Library/AJS/" || warn "/Library/AJS/ not found"

# Remove Anki add-on from all profiles
info "Removing Anki add-on..."
REMOVED_ADDON=0
for addon_dir in "$HOME/Library/Application Support/Anki2"/*/addons21/ajs_addon; do
    if [ -d "$addon_dir" ]; then
        rm -rf "$addon_dir"
        ok "Removed: $addon_dir"
        REMOVED_ADDON=1
    fi
done
[ $REMOVED_ADDON -eq 0 ] && warn "Anki add-on not found (may already be removed)"

# Remove ~/.ajs
info "Removing ~/.ajs/..."
rm -rf "$HOME/.ajs" && ok "Removed ~/.ajs/" || warn "~/.ajs/ not found"

# Offer to remove the AI model (it's 2 GB)
echo ""
if command -v ollama &>/dev/null || [ -d "$HOME/.ollama/models" ]; then
    read -p "  Remove the AI model (qwen2.5:3b, ~2 GB)? [y/N] " remove_model
    if [[ "$remove_model" == "y" || "$remove_model" == "Y" ]]; then
        if command -v ollama &>/dev/null; then
            ollama rm qwen2.5:3b 2>/dev/null && ok "Model removed." || warn "Model not found."
        fi
        # Also remove raw model files if ollama is gone
        rm -rf "$HOME/.ollama/models/manifests/registry.ollama.ai/library/qwen2.5" 2>/dev/null || true
        rm -rf "$HOME/.ollama/models/blobs" 2>/dev/null || true
    else
        info "Model kept."
    fi
fi

echo ""
echo "═══════════════════════════════════════════"
ok "Uninstall complete."
echo ""
read -p "  Press Enter to close..."
UNINSTALL
chmod +x "$SCRIPT_DIR/dist/uninstall.sh"

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
