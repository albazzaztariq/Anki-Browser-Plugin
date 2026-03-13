"""
AJS Setup — installer.py
GUI installer for Anki Japanese Sensei (AJS).

Cross-platform: Windows 10+ and macOS 12+.

When frozen as a PyInstaller exe/app, all bundled assets are found via sys._MEIPASS.
When run from source (python installer.py), assets are resolved relative to project root.

Steps performed:
  1.  Check OS / platform
  2.  Install Ollama
  3.  Start Ollama service
  4.  Pull qwen2.5:3b model (~2 GB)
  5.  Install fzf
  6.  Install ajs binary and add to PATH
  7.  Install Anki add-on
  8.  Create desktop shortcut
  9.  Done

Idempotent: each step checks first and skips if already done.
"""

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Callable, Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

print("[DEBUG] installer.py: script starting")

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

print(f"[DEBUG] installer: platform={sys.platform}, IS_WIN={IS_WIN}, IS_MAC={IS_MAC}")

# ---------------------------------------------------------------------------
# Bundle / source path resolution
# ---------------------------------------------------------------------------

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    print(f"[DEBUG] installer: running as frozen exe, BUNDLE_DIR={BUNDLE_DIR}")
else:
    BUNDLE_DIR = Path(__file__).parent.parent
    print(f"[DEBUG] installer: running from source, BUNDLE_DIR={BUNDLE_DIR}")

# ---------------------------------------------------------------------------
# Platform-specific constants
# ---------------------------------------------------------------------------

if IS_WIN:
    INSTALL_DIR      = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "AJS"
    ANKI_ADDONS_DIR  = Path.home() / "AppData" / "Roaming" / "Anki2" / "addons21" / "ajs_addon"
    DESKTOP          = Path.home() / "Desktop"
    AJS_BIN_NAME     = "ajs.exe"
    OLLAMA_DOWNLOAD_URL = "https://ollama.ai/download/OllamaSetup.exe"
    FZF_ARCH         = "windows-amd64"
    FZF_FILENAME     = "fzf.exe"
elif IS_MAC:
    INSTALL_DIR      = Path.home() / ".ajs" / "bin"
    ANKI_ADDONS_DIR  = Path.home() / "Library" / "Application Support" / "Anki2" / "addons21" / "ajs_addon"
    DESKTOP          = Path.home() / "Desktop"
    AJS_BIN_NAME     = "ajs"
    OLLAMA_DOWNLOAD_URL = "https://ollama.ai/install.sh"   # used as reference; we run via curl
    _machine = platform.machine().lower()
    FZF_ARCH         = "darwin-arm64" if "arm" in _machine or "aarch" in _machine else "darwin-amd64"
    FZF_FILENAME     = "fzf"
else:
    # Linux fallback (not officially supported but best-effort)
    INSTALL_DIR      = Path.home() / ".local" / "bin"
    ANKI_ADDONS_DIR  = Path.home() / ".local" / "share" / "Anki2" / "addons21" / "ajs_addon"
    DESKTOP          = Path.home() / "Desktop"
    AJS_BIN_NAME     = "ajs"
    OLLAMA_DOWNLOAD_URL = "https://ollama.ai/install.sh"
    FZF_ARCH         = "linux-amd64"
    FZF_FILENAME     = "fzf"

FZF_DOWNLOAD_URL = (
    f"https://github.com/junegunn/fzf/releases/latest/download/fzf-{FZF_ARCH}.zip"
    if IS_WIN
    else f"https://github.com/junegunn/fzf/releases/latest/download/fzf-{FZF_ARCH}.tar.gz"
)
OLLAMA_CHECK_URL = "http://localhost:11434"
MODEL_NAME       = "qwen2.5:3b"

print(f"[DEBUG] installer: INSTALL_DIR={INSTALL_DIR}")
print(f"[DEBUG] installer: ANKI_ADDONS_DIR={ANKI_ADDONS_DIR}")
print(f"[DEBUG] installer: FZF_ARCH={FZF_ARCH}")

# ---------------------------------------------------------------------------
# Step result tokens
# ---------------------------------------------------------------------------

class R:
    OK      = "OK"
    SKIPPED = "SKIPPED"
    FAILED  = "FAILED"
    WARN    = "WARN"

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _find_ollama() -> Optional[str]:
    """
    Return the path to the ollama binary, or None if not found.
    After a fresh Windows install, Ollama may not be in the current process PATH yet,
    so we also check the known install locations directly.
    """
    # Check PATH first.
    found = shutil.which("ollama")
    if found:
        return found
    if IS_WIN:
        # Ollama installs to %LOCALAPPDATA%\Programs\Ollama\ollama.exe
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
            Path("C:/Program Files/Ollama/ollama.exe"),
        ]
        for c in candidates:
            if c.exists():
                print(f"[DEBUG] installer: found ollama at {c} (not in PATH)")
                # Inject into PATH so subsequent shutil.which calls work.
                os.environ["PATH"] = str(c.parent) + os.pathsep + os.environ.get("PATH", "")
                return str(c)
    return None


def _is_ollama_in_path() -> bool:
    return _find_ollama() is not None


def _is_ollama_service_up() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(OLLAMA_CHECK_URL, timeout=4) as resp:
            return resp.status < 500
    except Exception:
        return False


def _popen_kwargs() -> dict:
    """Extra kwargs for subprocess.Popen to suppress console windows on Windows."""
    if IS_WIN:
        return {"creationflags": subprocess.CREATE_NO_WINDOW}  # type: ignore[attr-defined]
    return {}


def _add_to_user_path_windows(directory: Path) -> None:
    """Append directory to user PATH via Windows registry + broadcast WM_SETTINGCHANGE."""
    print(f"[DEBUG] installer: (win) adding {directory} to user PATH via registry")
    import winreg  # type: ignore
    import ctypes

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_ALL_ACCESS
    )
    try:
        current, reg_type = winreg.QueryValueEx(key, "Path")
    except FileNotFoundError:
        current, reg_type = "", winreg.REG_EXPAND_SZ

    dir_str = str(directory)
    if dir_str.lower() not in current.lower():
        new_val = current.rstrip(";") + ";" + dir_str
        winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_val)
        print("[DEBUG] installer: PATH registry updated")
    else:
        print(f"[DEBUG] installer: {dir_str} already in PATH registry")
    winreg.CloseKey(key)

    # Broadcast so running shells pick it up without a reboot.
    HWND_BROADCAST  = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002
    result = ctypes.c_long()
    ctypes.windll.user32.SendMessageTimeoutW(  # type: ignore
        HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment",
        SMTO_ABORTIFHUNG, 5000, ctypes.byref(result),
    )
    print("[DEBUG] installer: WM_SETTINGCHANGE broadcast sent")


def _add_to_user_path_mac(directory: Path) -> None:
    """Append export PATH line to ~/.zshrc (and ~/.bash_profile as fallback)."""
    print(f"[DEBUG] installer: (mac) adding {directory} to PATH via shell rc files")
    export_line = f'\nexport PATH="{directory}:$PATH"  # Added by AJS installer\n'
    for rc_file in [Path.home() / ".zshrc", Path.home() / ".bash_profile"]:
        try:
            existing = rc_file.read_text(errors="ignore") if rc_file.exists() else ""
            if str(directory) not in existing:
                with open(rc_file, "a") as f:
                    f.write(export_line)
                print(f"[DEBUG] installer: wrote PATH export to {rc_file}")
        except Exception as exc:
            print(f"[DEBUG] installer: could not write to {rc_file}: {exc}")


def _add_to_user_path(directory: Path) -> None:
    if IS_WIN:
        _add_to_user_path_windows(directory)
    else:
        _add_to_user_path_mac(directory)


def _download_with_progress(
    url: str,
    dest: Path,
    log: Callable[[str], None],
    progress_cb: Optional[Callable[[float], None]] = None,
) -> bool:
    """
    Stream-download url → dest, calling progress_cb(0.0–1.0) as chunks arrive.
    Falls back to urllib if requests isn't available.
    Returns True on success.
    """
    print(f"[DEBUG] installer: downloading {url} → {dest}")
    try:
        import requests
    except ImportError:
        log("  [!] 'requests' not installed — using urllib (no progress)")
        import urllib.request as ur
        try:
            ur.urlretrieve(url, str(dest))
            return True
        except Exception as exc:
            log(f"  Download failed: {exc}")
            return False

    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if total and progress_cb:
                        progress_cb(downloaded / total)
        print(f"[DEBUG] installer: download complete, {downloaded} bytes")
        return True
    except Exception as exc:
        log(f"  Download error: {exc}")
        print(f"[DEBUG] installer: download error: {exc}")
        return False


# ---------------------------------------------------------------------------
# Step 1 — Check OS
# ---------------------------------------------------------------------------

def step_check_os(log: Callable[[str], None]) -> str:
    """Verify we're on a supported OS and show platform info."""
    print("[DEBUG] installer: step_check_os")
    log(f"Checking operating system...")

    os_name    = platform.system()
    os_version = platform.version()
    os_release = platform.release()
    machine    = platform.machine()

    log(f"  OS: {os_name} {os_release} ({os_version})")
    log(f"  Architecture: {machine}")
    print(f"[DEBUG] installer: OS={os_name}, release={os_release}, machine={machine}")

    if IS_WIN:
        major = int(os_release) if os_release.isdigit() else 0
        if major < 10:
            log("  [WARN] AJS is tested on Windows 10 and 11 only.")
            return R.WARN
        log("  [OK] Windows version supported.")
        return R.OK
    elif IS_MAC:
        log("  [OK] macOS detected.")
        log("  Note: AJS requires macOS 12 (Monterey) or newer for full functionality.")
        return R.OK
    else:
        log("  [WARN] Linux is not officially supported. Best-effort installation.")
        return R.WARN


# ---------------------------------------------------------------------------
# Step 2 — Install Ollama
# ---------------------------------------------------------------------------

def step_install_ollama(
    log: Callable[[str], None],
    progress_cb: Optional[Callable[[float], None]] = None,
) -> str:
    """Download and install Ollama if not already in PATH."""
    print("[DEBUG] installer: step_install_ollama")
    log("Checking for Ollama...")

    if _is_ollama_in_path():
        log("  [OK] Ollama is already installed.")
        return R.SKIPPED

    log("  Ollama not found — installing now...")

    if IS_WIN:
        return _install_ollama_windows(log, progress_cb)
    else:
        return _install_ollama_mac(log)


def _install_ollama_windows(
    log: Callable[[str], None],
    progress_cb: Optional[Callable[[float], None]] = None,
) -> str:
    log(f"  Downloading Ollama for Windows (~80 MB)...")
    tmp = Path(tempfile.mkdtemp()) / "OllamaSetup.exe"

    def _dl_progress(frac: float) -> None:
        if progress_cb:
            progress_cb(frac * 0.9)

    ok = _download_with_progress(OLLAMA_DOWNLOAD_URL, tmp, log, _dl_progress)
    if not ok:
        log("  [!!] Failed to download Ollama.")
        return R.FAILED

    log("  Running Ollama installer silently...")
    print(f"[DEBUG] installer: running {tmp} /S")
    try:
        result = subprocess.run([str(tmp), "/S"], timeout=300)
        if progress_cb:
            progress_cb(1.0)
        if result.returncode == 0:
            log("  [OK] Ollama installed.")
            return R.OK
        else:
            log(f"  [!!] Ollama installer exited with code {result.returncode}.")
            return R.FAILED
    except subprocess.TimeoutExpired:
        log("  [!!] Ollama installer timed out.")
        return R.FAILED
    except Exception as exc:
        log(f"  [!!] Installer error: {exc}")
        return R.FAILED


def _install_ollama_mac(log: Callable[[str], None]) -> str:
    """Install Ollama on macOS via the official install script (curl | sh)."""
    log("  Installing Ollama via official install script...")
    log("  Running: curl -fsSL https://ollama.ai/install.sh | sh")
    print("[DEBUG] installer: running ollama install script via curl | sh")
    try:
        result = subprocess.run(
            "curl -fsSL https://ollama.ai/install.sh | sh",
            shell=True,
            timeout=300,
            capture_output=False,
        )
        if result.returncode == 0:
            log("  [OK] Ollama installed.")
            return R.OK
        else:
            log(f"  [!!] Install script exited with code {result.returncode}.")
            log("       Try manually: https://ollama.ai/download")
            return R.FAILED
    except subprocess.TimeoutExpired:
        log("  [!!] Install script timed out.")
        return R.FAILED
    except Exception as exc:
        log(f"  [!!] Error running install script: {exc}")
        return R.FAILED


# ---------------------------------------------------------------------------
# Step 3 — Start Ollama service
# ---------------------------------------------------------------------------

def step_start_ollama(log: Callable[[str], None]) -> str:
    """Start the Ollama background service and verify it responds."""
    print("[DEBUG] installer: step_start_ollama")
    log("Starting Ollama service...")

    if _is_ollama_service_up():
        log("  [OK] Ollama is already running.")
        return R.SKIPPED

    log("  Launching 'ollama serve' in background...")
    ollama_bin = _find_ollama()
    print(f"[DEBUG] installer: spawning ollama serve ({ollama_bin})")
    if not ollama_bin:
        log("  [!!] 'ollama' binary not found. Did Ollama install correctly?")
        if IS_MAC:
            log("       Try: /usr/local/bin/ollama serve")
        return R.FAILED
    try:
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_popen_kwargs(),
        )
    except Exception as exc:
        log(f"  [!!] Could not start ollama serve: {exc}")
        return R.FAILED
    except Exception as exc:
        log(f"  [!!] Could not start ollama serve: {exc}")
        return R.FAILED

    log("  Waiting for Ollama to start (up to 15 seconds)...")
    for attempt in range(15):
        time.sleep(1)
        if _is_ollama_service_up():
            log(f"  [OK] Ollama is responding at {OLLAMA_CHECK_URL}")
            print(f"[DEBUG] installer: ollama up after {attempt+1}s")
            return R.OK

    log(f"  [!!] Ollama did not respond after 15 seconds.")
    log("       It may still be starting — the model pull step will retry.")
    return R.WARN


# ---------------------------------------------------------------------------
# Step 4 — Pull qwen2.5:3b model
# ---------------------------------------------------------------------------

def step_pull_model(log: Callable[[str], None]) -> str:
    """Pull the qwen2.5:3b model via `ollama pull`. Streams output lines."""
    print("[DEBUG] installer: step_pull_model")
    log(f"Checking for model '{MODEL_NAME}'...")
    log("  (~2 GB download — please be patient)")

    if not _is_ollama_service_up():
        log("  [!!] Ollama service is not responding. Cannot pull model.")
        return R.FAILED

    ollama_bin = _find_ollama() or "ollama"
    print(f"[DEBUG] installer: checking ollama list for existing model (bin={ollama_bin})")
    try:
        result = subprocess.run(
            [ollama_bin, "list"], capture_output=True, text=True, timeout=15
        )
        if MODEL_NAME in result.stdout:
            log(f"  [OK] '{MODEL_NAME}' is already downloaded.")
            return R.SKIPPED
    except Exception as exc:
        log(f"  Could not check model list: {exc} — attempting pull anyway.")

    log(f"  Pulling '{MODEL_NAME}'...")
    print(f"[DEBUG] installer: running 'ollama pull {MODEL_NAME}'")
    try:
        proc = subprocess.Popen(
            [ollama_bin, "pull", MODEL_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            **_popen_kwargs(),
        )
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            if line:
                log(f"  {line}")
                print(f"[DEBUG] ollama pull: {line}")
        proc.wait()
        if proc.returncode == 0:
            log(f"  [OK] '{MODEL_NAME}' downloaded successfully.")
            return R.OK
        else:
            log(f"  [!!] 'ollama pull' exited with code {proc.returncode}.")
            return R.FAILED
    except FileNotFoundError:
        log("  [!!] ollama binary not found in PATH.")
        return R.FAILED
    except Exception as exc:
        log(f"  [!!] Model pull error: {exc}")
        return R.FAILED


# ---------------------------------------------------------------------------
# Step 5 — Install fzf
# ---------------------------------------------------------------------------

def _resolve_fzf_url(log: Callable[[str], None]) -> Optional[str]:
    """
    Query GitHub API to find the correct fzf asset URL for this platform.
    fzf filenames changed to fzf-{version}-{os}_{arch}.zip format.
    """
    api_url = "https://api.github.com/repos/junegunn/fzf/releases/latest"
    print(f"[DEBUG] installer: resolving fzf URL via {api_url}")
    try:
        import urllib.request, json
        req = urllib.request.Request(api_url, headers={"User-Agent": "AJS-Installer"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        ext = ".zip" if IS_WIN else ".tar.gz"
        # Asset name format: fzf-{version}-windows_amd64.zip (underscore between os_arch)
        search = FZF_ARCH.replace("-", "_") + ext
        for asset in data.get("assets", []):
            if search in asset["name"]:
                url = asset["browser_download_url"]
                print(f"[DEBUG] installer: fzf asset found: {asset['name']} → {url}")
                log(f"  Found: {asset['name']}")
                return url
        log(f"  [WARN] No fzf asset matching '{search}' in latest release.")
        return None
    except Exception as exc:
        log(f"  Could not query GitHub API: {exc}")
        print(f"[DEBUG] installer: fzf API error: {exc}")
        return None


def step_install_fzf(log: Callable[[str], None]) -> str:
    """
    Copy fzf from the bundle (if present) or download from GitHub.
    On macOS also tries `brew install fzf` as a first option.
    """
    print("[DEBUG] installer: step_install_fzf")
    log("Installing fzf...")

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    dest_fzf = INSTALL_DIR / FZF_FILENAME

    if dest_fzf.exists():
        log(f"  [OK] fzf already at {dest_fzf}")
        return R.SKIPPED

    # Try bundle first.
    bundled_fzf = BUNDLE_DIR / FZF_FILENAME
    print(f"[DEBUG] installer: looking for bundled fzf at {bundled_fzf}")
    if bundled_fzf.exists():
        shutil.copy2(str(bundled_fzf), str(dest_fzf))
        if not IS_WIN:
            dest_fzf.chmod(0o755)
        log(f"  [OK] fzf extracted from bundle to {dest_fzf}")
        return R.OK

    # macOS: try Homebrew first (user-friendly, no manual download needed).
    if IS_MAC and shutil.which("brew"):
        log("  Homebrew detected — installing fzf via brew...")
        try:
            result = subprocess.run(["brew", "install", "fzf"], timeout=120)
            if result.returncode == 0:
                brew_fzf = Path(shutil.which("fzf") or "")
                if brew_fzf.exists():
                    shutil.copy2(str(brew_fzf), str(dest_fzf))
                    dest_fzf.chmod(0o755)
                    log(f"  [OK] fzf installed via brew and copied to {dest_fzf}")
                    return R.OK
        except Exception as exc:
            log(f"  brew install fzf failed: {exc} — falling back to direct download")

    # Download from GitHub — resolve actual asset URL via API first.
    log(f"  Downloading fzf from GitHub ({FZF_ARCH})...")
    fzf_url = _resolve_fzf_url(log)
    if not fzf_url:
        log("  [!!] Could not resolve fzf download URL.")
        return R.FAILED
    tmp_archive = Path(tempfile.mkdtemp()) / ("fzf.zip" if IS_WIN else "fzf.tar.gz")
    ok = _download_with_progress(fzf_url, tmp_archive, log)
    if not ok:
        log("  [!!] Failed to download fzf.")
        return R.FAILED

    try:
        if IS_WIN:
            with zipfile.ZipFile(str(tmp_archive), "r") as zf:
                for member in zf.namelist():
                    if member.lower().endswith("fzf.exe"):
                        zf.extract(member, str(INSTALL_DIR))
                        extracted = INSTALL_DIR / member
                        if extracted != dest_fzf:
                            extracted.rename(dest_fzf)
                        break
        else:
            import tarfile
            with tarfile.open(str(tmp_archive), "r:gz") as tf:
                for member in tf.getmembers():
                    if member.name.endswith("fzf") and not member.name.endswith(".bash"):
                        member.name = FZF_FILENAME
                        tf.extract(member, str(INSTALL_DIR))
                        break
            dest_fzf.chmod(0o755)

        log(f"  [OK] fzf installed to {dest_fzf}")
        return R.OK
    except Exception as exc:
        log(f"  [!!] fzf extraction failed: {exc}")
        return R.FAILED


# ---------------------------------------------------------------------------
# Step 6 — Install ajs binary and add to PATH
# ---------------------------------------------------------------------------

def _create_user_notes_on_install(log: Callable[[str], None]) -> None:
    """Create User Notes.txt once during install."""
    print("[DEBUG] installer: create User Notes.txt")
    fallback_dir = Path.home() / ".ajs" / "Clipped Audio"
    audio_dir = fallback_dir
    if IS_WIN:
        music_dir = Path.home() / "Music"
        preferred = music_dir / "Anki AJS"
        if music_dir.exists():
            try:
                preferred.mkdir(parents=True, exist_ok=True)
                audio_dir = preferred
            except Exception as exc:
                log(f"  [WARN] Could not create {preferred}: {exc}")
                audio_dir = fallback_dir

    try:
        audio_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        log(f"  [WARN] Could not create audio folder {audio_dir}: {exc}")
        return

    notes_path = audio_dir / "User Notes.txt"
    if notes_path.exists():
        return

    user_config_path = Path.home() / ".ajs" / "user_config.json"
    lines = [
        "Anki Japanese Sensei - User Notes",
        "",
        "Audio clips are saved in this folder.",
        f"Current audio folder: {audio_dir}",
        "",
        "Settings:",
        "Open Anki -> Tools -> Japanese Sensei - Settings.",
        "Changes are saved to:",
        f"{user_config_path}",
    ]
    try:
        notes_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception as exc:
        log(f"  [WARN] Could not write User Notes.txt: {exc}")


def step_install_ajs(log: Callable[[str], None]) -> str:
    """
    Install the ajs command.

    Frozen (PyInstaller exe): copy the bundled ajs binary to INSTALL_DIR.
    Source mode (python installer.py): copy terminal/ scripts to ~/.ajs/terminal/
      and write a thin launcher script so the user can just run 'ajs'.
    """
    print("[DEBUG] installer: step_install_ajs")
    log("Installing ajs...")

    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    _create_user_notes_on_install(log)

    if getattr(sys, 'frozen', False):
        # --- Frozen: copy pre-built binary ---
        dest_ajs    = INSTALL_DIR / AJS_BIN_NAME
        bundled_ajs = BUNDLE_DIR / AJS_BIN_NAME
        print(f"[DEBUG] installer: (frozen) looking for {AJS_BIN_NAME} at {bundled_ajs}")
        if not bundled_ajs.exists():
            log(f"  [!!] {AJS_BIN_NAME} not found in bundle.")
            return R.FAILED
        try:
            shutil.copy2(str(bundled_ajs), str(dest_ajs))
            if not IS_WIN:
                dest_ajs.chmod(0o755)
            log(f"  [OK] {AJS_BIN_NAME} copied to {dest_ajs}")
        except Exception as exc:
            log(f"  [!!] Failed to copy {AJS_BIN_NAME}: {exc}")
            return R.FAILED
    else:
        # --- Source mode: copy scripts + write launcher ---
        scripts_src = BUNDLE_DIR / "terminal"
        scripts_dst = Path.home() / ".ajs" / "terminal"
        print(f"[DEBUG] installer: (source) copying {scripts_src} → {scripts_dst}")
        log(f"  Installing terminal scripts to {scripts_dst} ...")
        def _force_remove(func, path, _):
            import stat as _stat
            os.chmod(path, _stat.S_IWRITE)
            func(path)

        try:
            if scripts_dst.exists():
                shutil.rmtree(str(scripts_dst), onerror=_force_remove)
            shutil.copytree(str(scripts_src), str(scripts_dst))
            log("  [OK] Scripts copied.")
        except Exception as exc:
            log(f"  [!!] Failed to copy scripts: {exc}")
            return R.FAILED

        # Write .env config file.
        env_file = INSTALL_DIR / ".env"
        if not env_file.exists():
            env_file.write_text("PYTHONDONTWRITEBYTECODE=1\n", encoding="utf-8")
            log(f"  [OK] .env created: {env_file}")
        else:
            log(f"  [OK] .env already exists: {env_file}")

        # Write launcher: loads .env then runs the pipeline.
        if IS_WIN:
            launcher = INSTALL_DIR / "ajs.bat"
            launcher.write_text(
                f'@echo off\n'
                f'for /f "usebackq tokens=*" %%i in ("{env_file}") do set "%%i"\n'
                f'python "{scripts_dst / "ajs.py"}" %*\n'
                f'if %errorlevel% neq 0 (\n'
                f'    echo.\n'
                f'    echo Press Enter to close...\n'
                f'    pause >nul\n'
                f')\n'
            )
            log(f"  [OK] Launcher written: {launcher}")
        else:
            launcher = INSTALL_DIR / "ajs"
            launcher.write_text(
                f'#!/bin/bash\n'
                f'set -a\n'
                f'source "{env_file}"\n'
                f'set +a\n'
                f'exec python3 "{scripts_dst / "ajs.py"}" "$@"\n'
            )
            launcher.chmod(0o755)
            log(f"  [OK] Launcher written: {launcher}")

    # Add INSTALL_DIR to PATH.
    log(f"  Updating PATH to include {INSTALL_DIR} ...")
    try:
        _add_to_user_path(INSTALL_DIR)
        log(f"  [OK] {INSTALL_DIR} added to PATH.")
        # Also inject into the current process so 'ajs' works immediately.
        os.environ["PATH"] = str(INSTALL_DIR) + os.pathsep + os.environ.get("PATH", "")
        if IS_WIN:
            log("       Open a new terminal for 'ajs' to be recognized.")
        else:
            log("       PATH updated — 'ajs' is available in this session.")
    except Exception as exc:
        log(f"  [WARN] Could not update PATH: {exc}")
        log(f"         Manually add {INSTALL_DIR} to your PATH.")
        return R.WARN

    return R.OK


# ---------------------------------------------------------------------------
# Step 7 — Install Anki add-on
# ---------------------------------------------------------------------------

def step_install_addon(log: Callable[[str], None]) -> str:
    """Copy the ajs_addon folder into Anki's addons21 directory."""
    print("[DEBUG] installer: step_install_addon")
    log("Installing Anki add-on...")

    bundled_addon = BUNDLE_DIR / "ajs_addon"
    print(f"[DEBUG] installer: addon source = {bundled_addon}")

    if not bundled_addon.exists():
        log(f"  [!!] Add-on source not found at {bundled_addon}")
        return R.FAILED

    anki_base = ANKI_ADDONS_DIR.parent
    if not anki_base.exists():
        log("  [WARN] Anki add-ons directory not found.")
        log(f"         Expected: {anki_base}")
        log("         Install Anki from https://apps.ankiweb.net, open it once,")
        log("         then re-run this installer to install the add-on.")
        return R.WARN

    log(f"  Destination: {ANKI_ADDONS_DIR}")
    try:
        def _force_rm(func, path, _):
            import stat as _stat
            os.chmod(path, _stat.S_IWRITE)
            func(path)

        if ANKI_ADDONS_DIR.exists():
            log("  Existing add-on found — updating...")
            shutil.rmtree(str(ANKI_ADDONS_DIR), onerror=_force_rm)
        shutil.copytree(str(bundled_addon), str(ANKI_ADDONS_DIR))
        log("  [OK] Add-on installed. Restart Anki to activate it.")
        return R.OK
    except Exception as exc:
        log(f"  [!!] Failed to install add-on: {exc}")
        return R.FAILED


# ---------------------------------------------------------------------------
# Step 8 — Create desktop shortcut
# ---------------------------------------------------------------------------

def step_create_shortcut(log: Callable[[str], None]) -> str:
    """Create a desktop shortcut/launcher for ajs."""
    print("[DEBUG] installer: step_create_shortcut")
    log("Creating desktop shortcut...")

    # In source mode on Windows the launcher is ajs.bat, not ajs.exe.
    if IS_WIN and not getattr(sys, 'frozen', False):
        ajs_bin = INSTALL_DIR / "ajs.bat"
    else:
        ajs_bin = INSTALL_DIR / AJS_BIN_NAME

    if IS_WIN:
        return _create_shortcut_windows(log, ajs_bin)
    else:
        return _create_shortcut_mac(log, ajs_bin)


def _create_shortcut_windows(log: Callable[[str], None], ajs_exe: Path) -> str:
    shortcut_path = DESKTOP / "AJS.lnk"
    if shortcut_path.exists():
        log(f"  [OK] Shortcut already exists at {shortcut_path}")
        return R.SKIPPED
    if not ajs_exe.exists():
        log(f"  [WARN] {ajs_exe} not found — cannot create shortcut.")
        return R.WARN
    try:
        import win32com.client  # type: ignore
        shell    = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(shortcut_path))
        shortcut.Targetpath      = str(ajs_exe)
        shortcut.WorkingDirectory = str(INSTALL_DIR)
        shortcut.Description     = "Anki Japanese Sensei — queue a word as an Anki card"
        shortcut.save()
        log(f"  [OK] Shortcut created: {shortcut_path}")
        return R.OK
    except ImportError:
        log("  [WARN] pywin32 not available — skipping .lnk shortcut.")
        log(f"         Manually create a shortcut to {ajs_exe}")
        return R.WARN
    except Exception as exc:
        log(f"  [WARN] Could not create shortcut: {exc}")
        return R.WARN


def _create_shortcut_mac(log: Callable[[str], None], ajs_bin: Path) -> str:
    """Create a double-clickable .command file on the Desktop."""
    shortcut_path = DESKTOP / "AJS.command"
    if shortcut_path.exists():
        log(f"  [OK] Launcher already exists at {shortcut_path}")
        return R.SKIPPED

    script = f"""#!/bin/bash
# AJS — Anki Japanese Sensei launcher
export PATH="{INSTALL_DIR}:$PATH"
"{ajs_bin}"
"""
    try:
        shortcut_path.write_text(script)
        shortcut_path.chmod(0o755)
        log(f"  [OK] AJS.command created on Desktop — double-click to run.")
        return R.OK
    except Exception as exc:
        log(f"  [WARN] Could not create launcher: {exc}")
        return R.WARN


# ---------------------------------------------------------------------------
# Step registry
# ---------------------------------------------------------------------------

def step_install_python_deps(log: Callable[[str], None]) -> str:
    """Install required Python packages via pip."""
    print("[DEBUG] installer: step_install_python_deps")

    if getattr(sys, 'frozen', False):
        # Running as a frozen exe — all deps are bundled inside ajs.exe already.
        log("  [OK] Running as installer — dependencies bundled in ajs.exe.")
        print("[DEBUG] installer: frozen exe, skipping pip install")
        return R.SKIPPED

    log("Installing Python dependencies...")
    deps = ["yt-dlp", "pykakasi", "edge-tts", "pygetwindow", "pyperclip", "requests"]
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet"] + deps,
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode == 0:
            log(f"  [OK] Installed: {', '.join(deps)}")
            return R.OK
        else:
            log(f"  [!!] pip install failed: {result.stderr.strip()[:300]}")
            return R.FAILED
    except Exception as exc:
        log(f"  [!!] pip error: {exc}")
        return R.FAILED


STEPS = [
    ("Checking OS / platform",             step_check_os,             False),
    ("Installing Python dependencies",     step_install_python_deps,  False),
    ("Installing Ollama",                  step_install_ollama,       True ),
    ("Starting Ollama service",            step_start_ollama,         False),
    ("Pulling AI model (qwen2.5:3b)",      step_pull_model,           False),
    ("Installing fzf",                     step_install_fzf,          False),
    (f"Installing {AJS_BIN_NAME}",         step_install_ajs,          False),
    ("Installing Anki add-on",             step_install_addon,        False),
    ("Creating desktop shortcut",          step_create_shortcut,      False),
]

# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

def _open_anki() -> None:
    """Launch Anki on Windows or macOS, then close the installer."""
    try:
        if IS_MAC:
            subprocess.Popen(["open", "-a", "Anki"])
        else:
            candidates = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Anki" / "anki.exe",
                Path("C:/Program Files/Anki/anki.exe"),
                Path("C:/Program Files (x86)/Anki/anki.exe"),
            ]
            found = next((p for p in candidates if p.exists()), None)
            if not found:
                found = shutil.which("anki")
            if found:
                subprocess.Popen([str(found)])
            else:
                import webbrowser
                webbrowser.open("https://apps.ankiweb.net")
    except Exception:
        pass
    # Schedule exit on next event loop tick so we're not inside the button callback.
    if _installer_root is not None:
        _installer_root.after(50, lambda: os._exit(0))


_installer_root = None


def run_gui() -> None:
    """Launch the tkinter installer GUI."""
    print("[DEBUG] installer.run_gui: starting")
    import tkinter as tk
    from tkinter import ttk, scrolledtext

    global _installer_root
    root = tk.Tk()
    _installer_root = root
    root.title("AJS Setup — Anki Japanese Sensei")
    root.geometry("620x520")
    root.resizable(True, True)

    # Center on screen.
    root.update_idletasks()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"620x520+{(sw-620)//2}+{(sh-520)//2}")

    tk.Label(root, text="AJS", font=("Helvetica", 36, "bold"), fg="#e63946").pack(pady=(18, 0))
    tk.Label(root, text="Anki Japanese Sensei — Setup", font=("Helvetica", 13, "bold")).pack()
    tk.Label(
        root, text="Setting up everything automatically...",
        font=("Helvetica", 9), fg="#666"
    ).pack(pady=(2, 8))

    log_area = scrolledtext.ScrolledText(
        root, height=14, font=("Menlo" if IS_MAC else "Consolas", 9),
        state="disabled", bg="#1e1e1e", fg="#d4d4d4", relief="flat",
    )
    log_area.pack(fill="both", expand=True, padx=18, pady=(0, 6))

    progress_var = tk.DoubleVar(value=0.0)
    ttk.Progressbar(root, variable=progress_var, maximum=100, mode="determinate", length=580).pack(padx=18, pady=(0, 4))

    status_var = tk.StringVar(value="Preparing...")
    status_lbl = tk.Label(root, textvariable=status_var, font=("Helvetica", 9), fg="#333", anchor="w")
    status_lbl.pack(fill="x", padx=18)

    cancelled = threading.Event()

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=10)

    open_anki_btn = tk.Button(
        btn_frame, text="Open Anki Now", state="disabled",
        font=("Helvetica", 10), width=14, bg="#e63946", fg="white", relief="flat",
        command=_open_anki,
    )
    open_anki_btn.pack(side="left", padx=8)

    close_btn = tk.Button(
        btn_frame, text="Close", state="disabled",
        font=("Helvetica", 10), width=10, command=root.destroy,
    )
    close_btn.pack(side="left", padx=8)

    def _do_cancel() -> None:
        cancelled.set()
        cancel_btn.config(state="disabled", text="Cancelling...")
        _set_status("Cancelling...")
        print("[DEBUG] installer: cancel requested")

    cancel_btn = tk.Button(
        btn_frame, text="Cancel", state="normal",
        font=("Helvetica", 10), width=10, command=_do_cancel,
    )
    cancel_btn.pack(side="left", padx=8)

    # Window X button also cancels while running, closes when done.
    def _on_close() -> None:
        if close_btn.cget("state") == "normal":
            root.destroy()
        else:
            _do_cancel()
    root.protocol("WM_DELETE_WINDOW", _on_close)

    # Thread-safe UI helpers.
    def _log(msg: str) -> None:
        def _do() -> None:
            log_area.config(state="normal")
            log_area.insert("end", msg + "\n")
            log_area.see("end")
            log_area.config(state="disabled")
        root.after(0, _do)

    def _set_status(msg: str) -> None:
        root.after(0, lambda: status_var.set(msg))

    def _set_progress(pct: float) -> None:
        root.after(0, lambda: progress_var.set(max(0.0, min(100.0, pct))))

    failed: list[str] = []
    warned: list[str] = []
    TOTAL = len(STEPS)

    def _run_steps() -> None:
        print("[DEBUG] installer._run_steps: thread started")
        for idx, (step_name, step_fn, has_sub_progress) in enumerate(STEPS):
            if cancelled.is_set():
                _log("\n  Installation cancelled.")
                _set_status("Cancelled.")
                root.after(0, lambda: status_lbl.config(fg="#888"))
                root.after(0, lambda: close_btn.config(state="normal"))
                root.after(0, lambda: cancel_btn.config(state="disabled"))
                print("[DEBUG] installer: cancelled before step", step_name)
                return

            base_pct = (idx / TOTAL) * 100
            next_pct = ((idx + 1) / TOTAL) * 100
            _set_status(f"Step {idx+1}/{TOTAL}: {step_name}...")
            _log(f"\n── Step {idx+1}/{TOTAL}: {step_name}")
            _set_progress(base_pct)
            print(f"[DEBUG] installer: starting step '{step_name}'")

            def _sub_prog(frac: float, _b=base_pct, _n=next_pct) -> None:
                _set_progress(_b + frac * (_n - _b))

            try:
                result = step_fn(log=_log, progress_cb=_sub_prog) if has_sub_progress else step_fn(log=_log)
            except Exception as exc:
                result = R.FAILED
                _log(f"  [!!] Unhandled error: {exc}")
                print(f"[DEBUG] installer: step '{step_name}' threw: {exc}")

            _set_progress(next_pct)
            icon = {"OK": "✓", "SKIPPED": "–", "WARN": "!", "FAILED": "✗"}.get(result, "?")
            _log(f"  [{icon}] {result}")
            print(f"[DEBUG] installer: step '{step_name}' → {result}")

            if result == R.FAILED:
                failed.append(step_name)
            elif result == R.WARN:
                warned.append(step_name)

        _set_progress(100.0)
        if not failed:
            _log(
                "\n"
                "═══════════════════════════════════════════\n"
                "  Installation complete!\n\n"
                f"  AJS installed to: {INSTALL_DIR}\n\n"
                "  In Anki, press Ctrl+Shift+F (or go to\n"
                "  Tools → Japanese Sensei) to add a card.\n"
                "═══════════════════════════════════════════"
            )
            _set_status("Installation complete!" + (f" ({len(warned)} warning(s))" if warned else ""))
            root.after(0, lambda: status_lbl.config(fg="green"))
        else:
            _log(f"\n  Finished with {len(failed)} error(s): {', '.join(failed)}")
            _set_status(f"Finished with {len(failed)} error(s). See log.")
            root.after(0, lambda: status_lbl.config(fg="#c0392b"))

        root.after(0, lambda: close_btn.config(state="normal"))
        root.after(0, lambda: open_anki_btn.config(state="normal"))
        root.after(0, lambda: cancel_btn.config(state="disabled"))
        print("[DEBUG] installer._run_steps: thread finished")

    threading.Thread(target=_run_steps, daemon=True).start()
    root.mainloop()
    print("[DEBUG] installer.run_gui: mainloop exited")


# ---------------------------------------------------------------------------
# CLI fallback
# ---------------------------------------------------------------------------

def run_cli() -> None:
    print("\n" + "=" * 60)
    print("  AJS Setup — Anki Japanese Sensei (CLI mode)")
    print("=" * 60 + "\n")

    for idx, (step_name, step_fn, has_sub_progress) in enumerate(STEPS):
        print(f"\n[STEP {idx+1}/{len(STEPS)}] {step_name}")
        print("-" * 50)
        try:
            result = step_fn(log=print, progress_cb=None) if has_sub_progress else step_fn(log=print)
        except Exception as exc:
            result = R.FAILED
            print(f"  [!!] Unhandled error: {exc}")
        print(f"  → {result}")

    print("\n" + "=" * 60)
    print("  AJS Setup complete. Launching AJS...")
    print("=" * 60 + "\n")
    ajs_bin = shutil.which("ajs") or str(INSTALL_DIR / "ajs")
    if Path(ajs_bin).exists():
        os.execv(ajs_bin, [ajs_bin])
    else:
        print("  [WARN] Could not find ajs binary to launch. Run 'ajs' manually.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(prog="AJS_Setup", description="Anki Japanese Sensei installer.")
    parser.add_argument("--cli", action="store_true", help="Headless CLI mode — no GUI.")
    args = parser.parse_args()

    # macOS: always use CLI — tkinter on macOS has AppKit version constraints
    # that cause SIGABRT on some builds, and macOS users expect terminal output.
    if args.cli or IS_MAC:
        run_cli()
    else:
        try:
            run_gui()
        except Exception as exc:
            print(f"[DEBUG] installer: GUI failed ({exc}) — falling back to CLI")
            run_cli()


if __name__ == "__main__":
    print("[DEBUG] installer.py: __main__ entered")
    main()
