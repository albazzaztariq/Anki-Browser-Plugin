"""
AJS Anki Add-on — __init__.py
Entry point loaded by Anki Desktop when it initialises add-ons.

Responsibilities:
  1. Add "AJS: Pending Cards" menu item under Tools (NFR-6).
  2. Start a QTimer that calls bridge.check_pending() every TIMER_INTERVAL_MS ms.
  3. Handle startup errors gracefully without crashing Anki.

Compatibility:
  - Anki 23.x and later (Python 3.9+ bundled)
  - PyQt6 (bundled with Anki 23.x)

Notes on Anki add-on loading:
  - This file is executed in the scope of Anki's main thread at startup.
  - `mw` (the main window) is available from `aqt`.
  - All imports must use relative paths or be from Anki's bundled packages.
  - Heavy work must NOT happen here — only lightweight registration.
"""

import os
import sys

# Disable .pyc bytecode caching — keeps __pycache__ folders out of the source tree.
sys.dont_write_bytecode = True

# ---------------------------------------------------------------------------
# Import Anki's public API
# ---------------------------------------------------------------------------
try:
    from aqt import mw, gui_hooks  # type: ignore
    from aqt.qt import QTimer, QAction, Qt  # type: ignore  (Anki's Qt re-export)
    from aqt.utils import showInfo, showWarning  # type: ignore
except ImportError as _imp_err:
    # If we're not inside Anki, skip registration silently.
    mw = None  # type: ignore

# ---------------------------------------------------------------------------
# Import add-on modules
# ---------------------------------------------------------------------------
try:
    from .config import TIMER_INTERVAL_MS
    from .logger import get_logger
    from . import bridge
except Exception as _mod_err:
    raise

log = get_logger("init")

# ---------------------------------------------------------------------------
# QTimer — polls for pending cards
# ---------------------------------------------------------------------------

_timer: "QTimer | None" = None
_shortcut = None  # module-level so it is only created once

# ---------------------------------------------------------------------------
# Tab server — on-demand request/response with the AJS Chrome extension
# ---------------------------------------------------------------------------

import threading as _threading

_youtube_tabs: list = []
_tab_pending  = _threading.Event()   # set when Ctrl+Shift+E wants tabs
_tab_ready    = _threading.Event()   # set when extension has responded
_tab_mode     = "yt"                 # "yt" = YouTube only, "all" = every tab
_tab_server: "object | None" = None
_tab_fail_count = 0                  # consecutive "no tabs" failures — drives escalating UX


def _start_tab_server() -> None:
    """Start a background HTTP server for the on-demand tab protocol."""
    import json
    from http.server import HTTPServer, BaseHTTPRequestHandler

    global _tab_server

    class _Handler(BaseHTTPRequestHandler):
        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            if self.path == "/ping":
                body = json.dumps({"pending": _tab_pending.is_set(), "mode": _tab_mode}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path == "/tabs":
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    data = json.loads(self.rfile.read(length))
                    global _youtube_tabs
                    _youtube_tabs = [(t["title"], t["url"]) for t in data]
                    _tab_pending.clear()
                    _tab_ready.set()
                except Exception:
                    pass
                self.send_response(200)
                self._cors()
                self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *_):
            pass  # silence access log

    class _ReuseServer(HTTPServer):
        allow_reuse_address = True  # survive Anki restarts (port in TIME_WAIT)

    try:
        _tab_server = _ReuseServer(("127.0.0.1", 27384), _Handler)
        t = _threading.Thread(target=_tab_server.serve_forever, daemon=True)
        t.start()
        log.info("AJS tab server listening on 127.0.0.1:27384")
    except OSError as exc:
        log.warning("AJS tab server could not start (port in use?): %s", exc)


def _stop_tab_server() -> None:
    """Shut down the tab server cleanly on Anki exit."""
    global _tab_server
    if _tab_server is not None:
        try:
            _tab_server.shutdown()
            _tab_server.server_close()
            log.info("AJS tab server stopped")
        except Exception as exc:
            log.warning("Error stopping tab server: %s", exc)
        _tab_server = None


def _start_timer() -> None:
    """Start the polling QTimer on the Qt main thread."""
    global _timer

    log.info("Starting AJS polling timer: interval=%dms", TIMER_INTERVAL_MS)

    _timer = QTimer()
    _timer.setInterval(TIMER_INTERVAL_MS)
    _timer.timeout.connect(_on_timer_tick)
    _timer.start()

    log.info("QTimer started successfully")


def _on_timer_tick() -> None:
    """
    Called every TIMER_INTERVAL_MS ms.
    Delegates to bridge.check_pending() which handles file detection and dialog.
    """
    try:
        bridge.check_pending()
    except Exception as exc:
        # Never let an exception propagate out of a QTimer callback —
        # that would crash the timer and disable future ticks.
        log.exception("Unhandled exception in timer tick: %s", exc)


# ---------------------------------------------------------------------------
# Tools menu item
# ---------------------------------------------------------------------------

def _show_status_dialog() -> None:
    """
    Show a status dialog when the user opens AJS from the Tools menu.
    Displays current pending card status and Ollama connectivity.
    """
    log.info("AJS status dialog opened from Tools menu")

    from .config import PENDING_CARD_PATH

    lines = ["Anki Japanese Sensei (AJS) — Status\n"]

    # Pending card status.
    if PENDING_CARD_PATH.exists():
        lines.append(f"Pending card file: FOUND\n  → {PENDING_CARD_PATH}")
        lines.append("(The card will be imported automatically in a few seconds.)")
    else:
        lines.append("No pending card. Run the AJS terminal pipeline to queue a card.")

    lines.append("")

    # Ollama status.
    try:
        import requests  # type: ignore  (bundled with Anki)
        r = requests.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            lines.append("Ollama: RUNNING (http://localhost:11434)")
        else:
            lines.append(f"Ollama: returned HTTP {r.status_code}")
    except Exception as exc:
        lines.append(f"Ollama: NOT REACHABLE — {exc}")
        lines.append("  Install and start Ollama: https://ollama.com")

    lines.append("")
    lines.append(f"Log file: {__import__('pathlib').Path.home() / '.ajs' / 'anki_addon.log'}")

    showInfo("\n".join(lines), title="Anki Japanese Sensei")


# ---------------------------------------------------------------------------
# Tab mode picker + on-demand collection via the AJS Chrome extension
# ---------------------------------------------------------------------------

def _pick_tab_mode() -> "str | None":
    """
    Ask the user how to find the video tab.
    Returns "yt" (auto-detect), "all" (show all tabs), or None (cancelled).
    """
    from aqt.qt import QDialog, QVBoxLayout, QLabel, QPushButton, QDialogButtonBox

    dlg = QDialog(mw)
    dlg.setWindowTitle("Anki Japanese Sensei")
    dlg.setMinimumWidth(400)
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel("How would you like to find the video?"))
    layout.addWidget(QLabel(""))

    result = [None]

    def pick(mode):
        result[0] = mode
        dlg.accept()

    btn_auto = QPushButton("Auto-detect YouTube tabs")
    btn_auto.setToolTip("Finds open youtube.com/watch tabs automatically")
    btn_auto.clicked.connect(lambda: pick("yt"))
    layout.addWidget(btn_auto)

    btn_all = QPushButton("Select tab manually  (safest)")
    btn_all.setToolTip("Shows all open browser tabs — use this if auto-detect misses your video")
    btn_all.clicked.connect(lambda: pick("all"))
    layout.addWidget(btn_all)

    btn_cancel = QPushButton("Cancel")
    btn_cancel.clicked.connect(dlg.reject)
    layout.addWidget(btn_cancel)

    dlg.exec()
    return result[0]


def _collect_tabs(mode: str) -> list:
    """Ask the Chrome extension for tabs using the given mode, wait up to 3s."""
    global _tab_mode
    _tab_mode = mode
    _tab_ready.clear()
    _tab_pending.set()
    _tab_ready.wait(timeout=3)
    return list(_youtube_tabs)


# ---------------------------------------------------------------------------
# Tab picker dialog
# ---------------------------------------------------------------------------

class _TabPickerDialog:
    """
    Show a simple Qt dialog listing open YouTube tabs.
    Returns the selected URL, or "" if cancelled.
    """
    @staticmethod
    def pick(tabs: list, parent=None) -> str:
        from aqt.qt import (QDialog, QVBoxLayout, QLabel, QListWidget,
                            QDialogButtonBox, QListWidgetItem, Qt)

        dlg = QDialog(parent)
        dlg.setWindowTitle("Anki Japanese Sensei — Select Video")
        dlg.setMinimumWidth(520)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Select the YouTube video you want to study:"))

        lst = QListWidget()
        for title, url in tabs:
            # Strip " - YouTube" suffix from title for cleaner display
            display = title.replace(" - YouTube", "").strip() or url
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, url)
            lst.addItem(item)
        lst.setCurrentRow(0)
        lst.itemActivated.connect(lambda _: dlg.accept())
        layout.addWidget(lst)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return ""
        item = lst.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""


def _launch_ajs() -> None:
    """
    Grab the current browser URL in a background thread (so Anki doesn't freeze),
    then launch the ajs pipeline in a terminal with the URL.
    """
    log.info("Launching AJS pipeline from Anki")
    import shutil
    from pathlib import Path

    # ── Find ajs launcher up-front (fast, no I/O) ──
    candidates = [
        Path(os.environ.get("APPDATA", "")) / "AJS" / "ajs.bat",
        Path(os.environ.get("APPDATA", "")) / "AJS" / "ajs.exe",
        Path.home() / ".ajs" / "bin" / "ajs",
        Path.home() / ".local" / "bin" / "ajs",
    ]
    ajs = next((p for p in candidates if p.exists()), None) or shutil.which("ajs")

    if not ajs:
        from aqt.utils import showWarning
        showWarning(
            "AJS launcher not found.\n\n"
            "Please run the AJS installer first."
        )
        return

    ajs_str = str(ajs)

    # ── Show mode picker on main thread, then collect in background ──
    mode = _pick_tab_mode()
    if mode is None:
        log.info("User cancelled mode picker")
        return

    def _collect():
        return _collect_tabs(mode)

    def _on_collected(fut) -> None:
        import subprocess
        global _tab_fail_count
        try:
            tabs = fut.result()
        except Exception:
            tabs = []

        if not tabs:
            _tab_fail_count += 1
            log.warning("No tabs found (failure #%d)", _tab_fail_count)

            if _tab_fail_count == 1:
                # First failure — gentle nudge.
                from aqt.utils import showWarning
                showWarning(
                    "No browser tabs found.\n\n"
                    "• Make sure your video is open in Chrome or Edge.\n"
                    "• Try refreshing the AJS extension:\n"
                    "  1. Go to chrome://extensions\n"
                    "  2. Find 'AJS Tab Helper' and click the reload ↺ button\n"
                    "  3. Press Ctrl+Shift+E again.\n\n"
                    "Supported browsers: Chrome, Edge (Chromium).\n"
                    "Firefox and Safari are not currently supported.",
                    title="Anki Japanese Sensei — No Browser Found",
                )
            else:
                # Second+ failure — escalate with Report Bug button.
                from aqt.qt import QDialog, QVBoxLayout, QLabel, QPushButton, QDialogButtonBox

                dlg = QDialog(mw)
                dlg.setWindowTitle("Anki Japanese Sensei — Still Not Working?")
                dlg.setMinimumWidth(460)
                layout = QVBoxLayout(dlg)
                layout.addWidget(QLabel(
                    "<b>Browser tabs still not found.</b><br><br>"
                    "This has happened more than once — something may be wrong "
                    "with the extension or your browser setup.<br><br>"
                    "Supported browsers: <b>Chrome, Edge (Chromium)</b><br>"
                    "Firefox and Safari are not currently supported.<br><br>"
                    "You can file a bug report and we'll investigate."
                ))
                layout.addWidget(QLabel(""))

                btn_report = QPushButton("Report Bug — We'll Fix This")
                btn_report.setStyleSheet("font-weight: bold;")
                def _file_report():
                    dlg.accept()
                    _file_addon_bug_report()
                btn_report.clicked.connect(_file_report)
                layout.addWidget(btn_report)

                btn_dismiss = QPushButton("Dismiss")
                btn_dismiss.clicked.connect(dlg.reject)
                layout.addWidget(btn_dismiss)

                dlg.exec()
            return

        _tab_fail_count = 0  # reset on success

        # One tab: use it directly.  Multiple: show picker.
        if len(tabs) == 1:
            url = tabs[0][1]
            log.info("Single tab auto-selected: %s", url)
        else:
            url = _TabPickerDialog.pick(tabs, parent=mw)
            if not url:
                log.info("User cancelled tab picker")
                return
            log.info("User selected tab: %s", url)

        cmd_args = [ajs_str, "--url", url]
        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    ["cmd", "/c"] + cmd_args,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                shell_cmd = " ".join(f'"{a}"' for a in cmd_args)
                subprocess.Popen([
                    "osascript", "-e",
                    f'tell application "Terminal" to do script "{shell_cmd}"'
                ])
            log.info("AJS pipeline launched: %s", cmd_args)
        except Exception as exc:
            from aqt.utils import showWarning
            showWarning(f"Failed to launch AJS:\n{exc}")
            log.exception("Failed to launch AJS: %s", exc)

    mw.taskman.run_in_background(_collect, _on_collected)


def _file_addon_bug_report() -> None:
    """
    Collect add-on diagnostics and file a GitHub issue.
    Runs in a background thread so Anki doesn't freeze.
    """
    import json
    import platform
    import subprocess as _sp
    import traceback as _tb
    from datetime import datetime, timezone
    from pathlib import Path

    GITHUB_REPO = "albazzaztariq/Anki-Browser-Plugin"
    crash_dir   = Path.home() / ".ajs" / "crash_reports"
    crash_dir.mkdir(parents=True, exist_ok=True)

    def _collect_and_file():
        # Extension server status
        try:
            import requests  # type: ignore
            r = requests.get("http://localhost:27384/ping", timeout=2)
            server_status = f"reachable — {r.text[:200]}"
        except Exception as exc:
            server_status = f"not reachable — {exc}"

        # Log tail
        try:
            log_path = Path.home() / ".ajs" / "anki_addon.log"
            lines    = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            log_tail = "\n".join(lines[-80:])
        except Exception as exc:
            log_tail = f"(could not read log: {exc})"

        body = f"""## AJS Add-on Bug Report — Browser Not Found

**Time:** {datetime.now(timezone.utc).isoformat()}
**Platform:** {platform.system()} {platform.release()} ({platform.machine()})
**Failure count:** {_tab_fail_count}

### Extension Server (localhost:27384)
{server_status}

### Add-on Log (last 80 lines)
```
{log_tail}
```
"""
        title    = f"[addon] Browser tabs not found (failure #{_tab_fail_count})"
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = crash_dir / f"addon_crash_{ts}.md"
        out_file.write_text(body, encoding="utf-8")
        log.info("Add-on bug report saved: %s", out_file)

        # Try gh CLI
        try:
            result = _sp.run(
                ["gh", "issue", "create",
                 "--repo",  GITHUB_REPO,
                 "--title", title,
                 "--body",  body,
                 "--label", "crash"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                log.info("Bug report filed: %s", url)
                from aqt.utils import showInfo
                showInfo(f"Bug report filed:\n{url}", title="Anki Japanese Sensei")
                return
        except Exception:
            pass

        from aqt.utils import showInfo
        showInfo(
            f"Could not auto-submit. Report saved at:\n{out_file}\n\n"
            f"Please paste it at:\nhttps://github.com/{GITHUB_REPO}/issues/new",
            title="Anki Japanese Sensei",
        )

    mw.taskman.run_in_background(_collect_and_file, lambda _: None)


def _show_help() -> None:
    """Open the AJS README if found, otherwise show where to look."""
    from pathlib import Path
    import webbrowser

    candidates = [
        Path.home() / ".ajs" / "README.md",
        Path(__file__).parent.parent / "README.md",
        Path(__file__).parent / "README.md",
    ]
    found = next((p for p in candidates if p.exists()), None)

    if found:
        webbrowser.open(found.as_uri())
        log.info("Opened README: %s", found)
    else:
        from aqt.utils import showInfo
        showInfo(
            "README not found on your system.\n\n"
            "You can find documentation and setup guides at:\n"
            "https://github.com/albazzaztariq/Anki-Browser-Plugin\n\n"
            "Or search your system for 'README.md' near your Anki add-ons folder:\n"
            "%APPDATA%\\Anki2\\addons21\\ajs_addon\\",
            title="Anki Japanese Sensei — Help",
        )


def _add_tools_menu_item() -> None:
    """Register Ctrl+E shortcut and Tools menu items."""
    global _shortcut
    if _shortcut is not None:
        return  # already registered — prevent duplicates on profile switch
    log.debug("Adding AJS menu items and shortcut")

    from aqt.qt import QKeySequence, QShortcut
    # Menu item — no shortcut set here to avoid ambiguity with QShortcut below.
    launch_action = QAction("Japanese Sensei — Add Card  [Ctrl+Shift+E]", mw)
    launch_action.triggered.connect(_launch_ajs)
    mw.form.menuTools.addAction(launch_action)
    # QShortcut — Ctrl+Shift+E avoids conflict with Anki's built-in Ctrl+E (Edit Note)
    _shortcut = QShortcut(QKeySequence("Ctrl+Shift+E"), mw)  # noqa: F841
    _shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
    _shortcut.activated.connect(_launch_ajs)

    status_action = QAction("Japanese Sensei — Status...", mw)
    status_action.triggered.connect(_show_status_dialog)
    mw.form.menuTools.addAction(status_action)

    help_action = QAction("Japanese Sensei — Help / Documentation", mw)
    help_action.triggered.connect(_show_help)
    mw.form.menuTools.addAction(help_action)

    log.info("AJS menu items and Ctrl+Shift+E shortcut registered")

def _register() -> None:
    """
    Main registration function.  Called after Anki's profile is loaded so
    that mw.col and the Qt event loop are ready.
    """
    log.info("AJS add-on registration starting")

    if mw is None:
        log.warning("mw is None — skipping registration (not inside Anki)")
        return

    try:
        _add_tools_menu_item()
        _start_timer()
        _start_tab_server()
        log.info("AJS add-on registered successfully")
    except Exception as exc:
        log.exception("Add-on registration failed: %s", exc)


# Hook into Anki's profile-loaded event so we register after the collection
# is open and mw.col is available.
if mw is not None:
    try:
        gui_hooks.profile_did_open.append(_register)
        log.debug("Registered on gui_hooks.profile_did_open")
    except Exception as exc:
        log.exception("Hook registration failed: %s", exc)

# Clean up the tab server on exit — RST is sent, port freed immediately.
import atexit as _atexit
_atexit.register(_stop_tab_server)
if mw is not None:
    try:
        gui_hooks.profile_will_close.append(lambda: _stop_tab_server())
        log.debug("Registered _stop_tab_server on profile_will_close")
    except Exception as exc:
        log.exception("Shutdown hook registration failed: %s", exc)

