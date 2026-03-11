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
from pathlib import Path

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
_tab_pending  = _threading.Event()   # set when Ctrl+Shift+F wants tabs
_tab_ready    = _threading.Event()   # set when extension has responded
_tab_mode     = "yt"                 # "yt" = YouTube only, "all" = every tab
_tab_server: "object | None" = None
_tab_fail_count = 0                  # kept for compatibility — no longer drives escalating UX
_tab_lock     = _threading.Lock()    # guards _youtube_tabs during multi-browser collection
_tab_cache: dict[str, tuple[str, str, float]] = {}  # url -> (title, browser, last_seen_monotonic)
_TAB_RESPONSE_TIMEOUT_S = 5.0
_TAB_CACHE_PATH = Path.home() / ".ajs" / "recent_tabs.json"

# Browser-triggered launch (Ctrl+Shift+F pressed while browser is active window)
_trigger_pending = _threading.Event()  # set when /trigger received from extension
_trigger_url: str = ""                 # URL passed by the extension


def _load_tab_cache_from_disk() -> None:
    """Load recent tabs so manual selection still works after restarting Anki."""
    import json
    import time as _time

    try:
        if not _TAB_CACHE_PATH.exists():
            return
        raw = json.loads(_TAB_CACHE_PATH.read_text(encoding="utf-8"))
        now = _time.monotonic()
        with _tab_lock:
            for item in raw:
                url = item.get("url", "").strip()
                if not url:
                    continue
                title = item.get("title", "").strip() or url
                browser = item.get("browser", "Browser").strip() or "Browser"
                age_s = float(item.get("age_s", 0.0))
                _tab_cache[url] = (title, browser, now - max(0.0, age_s))
    except Exception as exc:
        log.debug("Could not load tab cache: %s", exc)


def _save_tab_cache_to_disk() -> None:
    """Persist recent tabs so fallback works across Anki restarts."""
    import json
    import time as _time

    try:
        _TAB_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        now = _time.monotonic()
        with _tab_lock:
            payload = [
                {"title": title, "url": url, "browser": browser, "age_s": max(0.0, now - seen_at)}
                for url, (title, browser, seen_at) in _tab_cache.items()
            ]
        _TAB_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    except Exception as exc:
        log.debug("Could not save tab cache: %s", exc)


def _remember_tabs(tabs: list[tuple[str, str, str]]) -> None:
    """Remember recently seen browser tabs so manual mode can fall back to them."""
    import time as _time

    now = _time.monotonic()
    with _tab_lock:
        for title, url, browser in tabs:
            if url:
                _tab_cache[url] = (title, browser or "Browser", now)

        stale_before = now - 600.0
        stale_urls = [url for url, (_, _, seen_at) in _tab_cache.items() if seen_at < stale_before]
        for url in stale_urls:
            _tab_cache.pop(url, None)
    _save_tab_cache_to_disk()


def _get_cached_tabs(mode: str) -> list[tuple[str, str, str]]:
    """Return recent tabs as a fallback when the extension misses a live request."""
    with _tab_lock:
        items = sorted(_tab_cache.items(), key=lambda item: item[1][1], reverse=True)

    tabs = [(title, url, browser) for url, (title, browser, _seen_at) in items]
    if mode == "yt":
        tabs = [(title, url, browser) for title, url, browser in tabs if "youtube.com/watch" in url or "youtu.be/" in url]
    return tabs


_load_tab_cache_from_disk()


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
            import time as _time
            length = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(length))
            except Exception:
                self.send_response(400)
                self._cors()
                self.end_headers()
                return

            if self.path == "/tabs":
                # Merge tabs from all browsers (Chrome + Edge may both respond).
                # Ignore empty responses — don't let a browser with no YouTube tabs
                # preempt one that does have them.
                new_tabs = [
                    (t.get("title", "") or t.get("url", ""),
                     t.get("url", ""),
                     t.get("browser", "Browser"))
                    for t in data if t.get("url")
                ]
                if new_tabs:
                    _remember_tabs(new_tabs)
                    with _tab_lock:
                        existing_urls = {url for _, url, _ in _youtube_tabs}
                        for tab in new_tabs:
                            if tab[1] not in existing_urls:
                                _youtube_tabs.append(tab)
                                existing_urls.add(tab[1])
                        has_tabs = bool(_youtube_tabs)

                    if has_tabs and not _tab_ready.is_set():
                        # Give other browsers 1 s to also respond, then signal ready.
                        def _signal_after_window():
                            _time.sleep(1.0)
                            _tab_pending.clear()
                            _tab_ready.set()
                        _threading.Thread(target=_signal_after_window, daemon=True).start()

                self.send_response(200)
                self._cors()
                self.end_headers()

            elif self.path == "/trigger":
                # Browser pressed Ctrl+Shift+F — launch ajs directly with the given URL.
                global _trigger_url
                url = data.get("url", "").strip() if isinstance(data, dict) else ""
                if url:
                    title = data.get("title", "").strip() if isinstance(data, dict) else ""
                    browser = data.get("browser", "Browser").strip() if isinstance(data, dict) else "Browser"
                    _remember_tabs([(title or url, url, browser)])
                    _trigger_url = url
                    _trigger_pending.set()
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
        timeout = 0.2

        def handle_error(self, request, client_address):
            import sys
            exc = sys.exc_info()[1]
            if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
                return  # browser closed connection early — normal, not an error
            super().handle_error(request, client_address)

    if _tab_server is not None:
        return  # already running — don't bind twice
    try:
        _tab_server = _ReuseServer(("127.0.0.1", 27384), _Handler)
        t = _threading.Thread(target=lambda: _tab_server.serve_forever(poll_interval=0.2), daemon=True)
        t.start()
        log.info("AJS tab server listening on 127.0.0.1:27384")
    except OSError as exc:
        log.warning("AJS tab server could not start (port in use?): %s", exc)


def _stop_tab_server() -> None:
    """Shut down the tab server cleanly on Anki exit."""
    global _tab_server
    if _tab_server is not None:
        try:
            _tab_pending.clear()
            _tab_ready.set()
            _trigger_pending.clear()
            _tab_server.shutdown()
            _tab_server.server_close()
            log.info("AJS tab server stopped")
        except Exception as exc:
            log.warning("Error stopping tab server: %s", exc)
        _tab_server = None


def _stop_tab_server_async() -> None:
    """Trigger tab-server shutdown without blocking the Anki UI thread."""
    _threading.Thread(target=_stop_tab_server, daemon=True).start()


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
    Checks for browser-triggered launches (/trigger) and pending card imports.
    """
    try:
        # Browser-side Ctrl+Shift+F — extension POSTed /trigger with a URL.
        # Must run on Qt main thread so we can open dialogs and launch subprocesses.
        if _trigger_pending.is_set():
            _trigger_pending.clear()
            url = _trigger_url
            if url:
                log.info("Browser-triggered launch for URL: %s", url)
                _launch_ajs_with_url(url)

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
    """Ask the browser extension for tabs using the given mode, wait up to 15s."""
    global _tab_mode
    _tab_mode = mode
    with _tab_lock:
        _youtube_tabs.clear()
    _tab_ready.clear()
    _tab_pending.set()
    _tab_ready.wait(timeout=_TAB_RESPONSE_TIMEOUT_S)
    with _tab_lock:
        live_tabs = list(_youtube_tabs)

    if live_tabs:
        return live_tabs

    cached_tabs = _get_cached_tabs(mode)
    if cached_tabs:
        log.warning("Falling back to %d cached tab(s) for mode=%s", len(cached_tabs), mode)
        return cached_tabs

    return []


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
        for tab in tabs:
            if len(tab) == 3:
                title, url, browser = tab
            else:
                title, url = tab
                browser = "Browser"
            # Strip " - YouTube" suffix from title for cleaner display
            display = title.replace(" - YouTube", "").strip() or url
            display = f"({browser}) {display}"
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
        try:
            tabs = fut.result()
        except Exception:
            tabs = []

        if not tabs:
            log.warning("No tabs found")
            from aqt.utils import showWarning
            showWarning(
                "No browser tabs found.\n\n"
                "• Make sure your video is open in Chrome or Edge.\n"
                "• Try refreshing the AJS extension:\n"
                "  1. Go to edge://extensions (or chrome://extensions)\n"
                "  2. Find 'AJS Tab Helper' and click the reload ↺ button\n"
                "  3. Press Ctrl+Shift+F again.\n\n"
                "Supported browsers: Chrome, Edge (Chromium).",
                title="Anki Japanese Sensei",
            )
            return

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


def _launch_ajs_with_url(url: str) -> None:
    """
    Launch the ajs terminal pipeline directly with a known URL.
    Called when the browser extension triggers via /trigger (Ctrl+Shift+F in browser).
    Skips the tab picker — the extension already knows the active tab URL.
    Must be called on the Qt main thread.
    """
    import shutil, subprocess
    from pathlib import Path

    log.info("Browser-triggered AJS launch: %s", url)

    candidates = [
        Path(os.environ.get("APPDATA", "")) / "AJS" / "ajs.bat",
        Path(os.environ.get("APPDATA", "")) / "AJS" / "ajs.exe",
        Path.home() / ".ajs" / "bin" / "ajs",
        Path.home() / ".local" / "bin" / "ajs",
    ]
    ajs = next((p for p in candidates if p.exists()), None) or shutil.which("ajs")

    if not ajs:
        from aqt.utils import showWarning
        showWarning("AJS launcher not found.\n\nPlease run the AJS installer first.")
        return

    cmd_args = [str(ajs), "--url", url]
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["cmd", "/c"] + cmd_args,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            import tempfile, shlex as _shlex
            cmd_line = " ".join(_shlex.quote(str(a)) for a in cmd_args)
            with tempfile.NamedTemporaryFile(mode="w", suffix=".command", delete=False) as _f:
                _f.write("#!/bin/bash\n" + cmd_line + "\n")
                _tmpfile = _f.name
            os.chmod(_tmpfile, 0o755)
            subprocess.Popen(["open", _tmpfile])
        log.info("AJS pipeline launched from browser trigger: %s", cmd_args)
    except Exception as exc:
        from aqt.utils import showWarning
        showWarning(f"Failed to launch AJS:\n{exc}")
        log.exception("Failed to launch AJS from browser trigger: %s", exc)


def _file_addon_bug_report() -> None:
    """
    Collect add-on diagnostics and file a GitHub issue.

    Submission chain:
      1. gh CLI          (dev machines — already authenticated)
      2. GitHub API      (GITHUB_ISSUE_TOKEN from ~/.ajs/.token)
      3. Google Form     (FEEDBACK_FORM_URL from config — easiest for end users)
      4. Browser pre-fill GitHub new-issue page (universal fallback)

    Always saves a local crash file first.
    Runs in a background thread so Anki doesn't freeze.
    """
    import platform
    import subprocess as _sp
    import urllib.parse
    import webbrowser
    from datetime import datetime, timezone
    from pathlib import Path

    from . import config as _cfg

    GITHUB_REPO   = _cfg.GITHUB_REPO
    GITHUB_TOKEN  = _cfg.GITHUB_ISSUE_TOKEN
    FEEDBACK_FORM = _cfg.FEEDBACK_FORM_URL
    crash_dir     = Path.home() / ".ajs" / "crash_reports"
    crash_dir.mkdir(parents=True, exist_ok=True)

    def _collect_and_file():
        # --- Diagnostics ---------------------------------------------------
        try:
            import requests  # type: ignore
            r = requests.get("http://localhost:27384/ping", timeout=2)
            server_status = f"reachable — {r.text[:200]}"
        except Exception as exc:
            server_status = f"not reachable — {exc}"

        try:
            log_path = _cfg.LOG_FILE
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

        # --- 1. gh CLI -----------------------------------------------------
        try:
            result = _sp.run(
                ["gh", "issue", "create",
                 "--repo",  GITHUB_REPO,
                 "--title", title,
                 "--body",  body,
                 "--label", "bug",
                 "--label", "user-report"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                log.info("Bug report filed via gh CLI: %s", url)
                from aqt.utils import showInfo
                showInfo(f"Bug report filed — thank you!\n\n{url}",
                         title="Anki Japanese Sensei")
                return
        except Exception:
            pass

        # --- 2. GitHub API with token --------------------------------------
        if GITHUB_TOKEN:
            try:
                import requests  # type: ignore
                r = requests.post(
                    f"https://api.github.com/repos/{GITHUB_REPO}/issues",
                    json={"title": title, "body": body, "labels": ["bug", "user-report"]},
                    headers={
                        "Authorization": f"Bearer {GITHUB_TOKEN}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    timeout=15,
                )
                if r.status_code == 201:
                    url = r.json().get("html_url", "")
                    log.info("Bug report filed via API: %s", url)
                    from aqt.utils import showInfo
                    showInfo(f"Bug report filed — thank you!\n\n{url}",
                             title="Anki Japanese Sensei")
                    return
                log.warning("GitHub API %d: %s", r.status_code, r.text[:200])
            except Exception as exc:
                log.debug("GitHub API failed: %s", exc)

        # --- 3. Google Form ------------------------------------------------
        if FEEDBACK_FORM:
            log.info("Opening Google Form for bug report")
            try:
                webbrowser.open(FEEDBACK_FORM)
                from aqt.utils import showInfo
                showInfo(
                    "Opening the bug report form in your browser.\n\n"
                    f"Your crash log is saved at:\n{out_file}",
                    title="Anki Japanese Sensei",
                )
                return
            except Exception as exc:
                log.warning("webbrowser.open (form) failed: %s", exc)

        # --- 4. Browser pre-fill GitHub new issue (universal fallback) -----
        max_body = 4000
        short_body = body[:max_body]
        if len(body) > max_body:
            short_body += f"\n\n*(truncated — full log: {out_file})*"
        params = urllib.parse.urlencode({"title": title, "body": short_body})
        url    = f"https://github.com/{GITHUB_REPO}/issues/new?{params}"
        try:
            webbrowser.open(url)
            from aqt.utils import showInfo
            showInfo(
                "Opening GitHub in your browser to submit the report.\n\n"
                f"Full crash log saved at:\n{out_file}",
                title="Anki Japanese Sensei",
            )
        except Exception as exc:
            log.warning("webbrowser.open (GitHub) failed: %s", exc)
            from aqt.utils import showInfo
            showInfo(
                f"Could not open browser automatically.\n\n"
                f"Please submit manually:\nhttps://github.com/{GITHUB_REPO}/issues/new\n\n"
                f"Crash log: {out_file}",
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
    launch_action = QAction("Japanese Sensei — Add Card  [Ctrl+Shift+F]", mw)
    launch_action.triggered.connect(_launch_ajs)
    mw.form.menuTools.addAction(launch_action)
    # QShortcut — Ctrl+Shift+F avoids conflict with Anki's built-in Ctrl+E (Edit Note)
    _shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), mw)  # noqa: F841
    _shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
    _shortcut.activated.connect(_launch_ajs)

    status_action = QAction("Japanese Sensei — Status...", mw)
    status_action.triggered.connect(_show_status_dialog)
    mw.form.menuTools.addAction(status_action)

    help_action = QAction("Japanese Sensei — Help / Documentation", mw)
    help_action.triggered.connect(_show_help)
    mw.form.menuTools.addAction(help_action)

    log.info("AJS menu items and Ctrl+Shift+F shortcut registered")

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


# Start the tab server immediately at addon load time.
# The HTTP server has no Qt/Anki dependencies — safe to run before profile loads.
_start_tab_server()

# Register Qt UI (menu, shortcut, timer) via profile hook.
# If the profile is already open when the addon loads (Anki 24+), use a
# zero-delay QTimer.singleShot so Qt widgets are created on the event loop,
# not during module import.
if mw is not None:
    try:
        gui_hooks.profile_did_open.append(_register)
        log.debug("Registered on gui_hooks.profile_did_open")
        if getattr(mw, "col", None) is not None:
            log.info("Profile already open — scheduling _register via singleShot")
            from aqt.qt import QTimer as _QTimer
            _QTimer.singleShot(0, _register)
    except Exception as exc:
        log.exception("Hook registration failed: %s", exc)

# Server thread is daemon=True so it dies automatically when Anki exits.
# Do NOT call shutdown() from atexit or profile hooks — it blocks during
# Python teardown and causes Anki to hang/crash on exit.

