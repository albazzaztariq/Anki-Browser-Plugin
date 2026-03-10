"""
AJS Terminal — crash_reporter.py
Collects diagnostic info on unhandled exceptions and files a GitHub issue.

Collects:
  - Exception type, message, full traceback
  - Session event timeline (user actions + keypresses)
  - Last 100 lines of AJS log file
  - Running processes filtered to AJS-relevant ones
  - Platform / Python / config info
  - Extension server reachability (localhost:27384/ping)

Filing:
  1. Always writes a crash_YYYYMMDD_HHMMSS.md to ~/.ajs/crash_reports/
  2. Asks user permission before submitting
  3. Submits via `gh issue create` (gh CLI, already authenticated for dev)
  4. Falls back to GitHub API with GITHUB_ISSUE_TOKEN from config if gh unavailable
  5. Falls back to printing the manual submission URL
"""

import platform
import subprocess
import sys
import traceback
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path

print("[DEBUG] crash_reporter.py: module loading")

from config import LOG_FILE, GITHUB_REPO, GITHUB_ISSUE_TOKEN
from logger import get_logger

log = get_logger("crash_reporter")
CRASH_DIR   = Path.home() / ".ajs" / "crash_reports"

# ---------------------------------------------------------------------------
# Session event log — populated throughout the pipeline via log_event()
# ---------------------------------------------------------------------------

_session_events: list[dict] = []


def log_event(event_type: str, detail: str = "") -> None:
    """
    Record a user action or pipeline milestone for inclusion in crash reports.

    Call this at every meaningful point: word entered, segment selected,
    keypress confirmed, LLM attempt started, etc.

    Args:
        event_type: Short label, e.g. "word_entered", "segment_selected".
        detail:     Optional extra info (truncated to 200 chars).
    """
    _session_events.append({
        "ts":     datetime.now(timezone.utc).isoformat(),
        "type":   event_type,
        "detail": str(detail)[:200],
    })


# ---------------------------------------------------------------------------
# Diagnostic collectors
# ---------------------------------------------------------------------------

def _get_processes() -> str:
    """Return running processes relevant to AJS (Python, Anki, Chrome, Ollama, fzf)."""
    keywords = ("python", "anki", "chrome", "ollama", "fzf", "yt-dlp", "edge", "firefox")
    try:
        if sys.platform == "win32":
            r = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=10,
            )
            lines = [l for l in r.stdout.splitlines()
                     if any(kw in l.lower() for kw in keywords)]
        else:
            r = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=10)
            lines = r.stdout.splitlines()[:1]  # header
            lines += [l for l in r.stdout.splitlines()[1:]
                      if any(kw in l.lower() for kw in keywords)]
        return "\n".join(lines) if lines else "(no matching processes)"
    except Exception as exc:
        return f"(could not collect: {exc})"


def _get_log_tail(n: int = 100) -> str:
    """Return the last n lines of the AJS log file."""
    try:
        text  = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        return "\n".join(lines[-n:])
    except Exception as exc:
        return f"(could not read log: {exc})"


def _check_extension_server() -> str:
    """Ping the AJS tab server and return a one-line status."""
    try:
        import requests  # type: ignore
        r = requests.get("http://localhost:27384/ping", timeout=2)
        return f"reachable — {r.text[:200]}"
    except Exception as exc:
        return f"not reachable — {exc}"


def _get_config_info() -> str:
    """Return non-sensitive config values for diagnostics."""
    try:
        import config
        return (
            f"OLLAMA_MODEL={config.OLLAMA_MODEL}  "
            f"OLLAMA_TIMEOUT={config.OLLAMA_TIMEOUT}s  "
            f"LLM_MAX_RETRIES={config.LLM_MAX_RETRIES}  "
            f"TTS_VOICE={config.TTS_VOICE}"
        )
    except Exception as exc:
        return f"(could not read config: {exc})"


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _build_report(exc_info: tuple) -> str:
    """Assemble the full crash report as a GitHub-flavoured markdown string."""
    exc_type, exc_value, exc_tb = exc_info
    tb_str  = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    now_str = datetime.now(timezone.utc).isoformat()

    session_md = "\n".join(
        f"- `{e['ts']}` **{e['type']}** — {e['detail']}"
        for e in _session_events
    ) or "*(no events recorded)*"

    return f"""## AJS Crash Report

**Time:** {now_str}
**Platform:** {platform.system()} {platform.release()} ({platform.machine()})
**Python:** {sys.version}
**Config:** {_get_config_info()}

---

## Exception

```
{tb_str.strip()}
```

---

## Session Timeline

{session_md}

---

## Extension Server (localhost:27384)

{_check_extension_server()}

---

## Running Processes (AJS-related)

```
{_get_processes()}
```

---

## Log Tail (last 100 lines)

```
{_get_log_tail()}
```
"""


# ---------------------------------------------------------------------------
# Submission
# ---------------------------------------------------------------------------

def _try_gh_cli(title: str, body: str) -> Optional[str]:
    """Try `gh issue create`. Returns issue URL on success, None on failure."""
    try:
        result = subprocess.run(
            ["gh", "issue", "create",
             "--repo",  GITHUB_REPO,
             "--title", title,
             "--body",  body,
             "--label", "crash"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        log.warning("gh issue create failed: %s", result.stderr[:300])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _try_github_api(title: str, body: str) -> Optional[str]:
    """Try GitHub REST API with GITHUB_ISSUE_TOKEN. Returns issue URL or None."""
    if not GITHUB_ISSUE_TOKEN:
        return None
    try:
        import requests  # type: ignore
        r = requests.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues",
            json={"title": title, "body": body, "labels": ["crash"]},
            headers={
                "Authorization": f"Bearer {GITHUB_ISSUE_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
            timeout=15,
        )
        if r.status_code == 201:
            return r.json().get("html_url", "")
        log.warning("GitHub API returned %d: %s", r.status_code, r.text[:200])
    except Exception as exc:
        log.debug("GitHub API submission failed: %s", exc)
    return None


def _open_browser_issue(title: str, body: str, crash_file: Path) -> None:
    """
    Last-resort fallback: open a pre-filled GitHub new-issue page in the browser.

    The body is truncated to keep the URL under browser limits (~8 000 chars).
    The full report is always in crash_file which the user can attach manually.
    """
    import urllib.parse
    import webbrowser

    # Keep URL short — browsers cap around 8 000 chars.
    max_body = 4000
    short_body = body[:max_body]
    if len(body) > max_body:
        short_body += f"\n\n*(report truncated — full file: {crash_file})*"

    params = urllib.parse.urlencode({"title": title, "body": short_body})
    url    = f"https://github.com/{GITHUB_REPO}/issues/new?{params}"

    print(f"\n[AJS] Opening GitHub in your browser to submit the report...")
    print(f"      Full report file: {crash_file}")
    try:
        webbrowser.open(url)
        log.info("Opened browser issue URL for: %s", title)
    except Exception as exc:
        log.warning("webbrowser.open failed: %s", exc)
        print(f"[AJS] Could not open browser. Submit manually:")
        print(f"      https://github.com/{GITHUB_REPO}/issues/new")


def file_report(exc_info: tuple, ask_user: bool = True) -> None:
    """
    Collect diagnostics for the given exception and file a GitHub issue.

    Submission chain:
      1. gh CLI          (dev machines — already authenticated)
      2. GitHub API      (end users — requires token in ~/.ajs/.token)
      3. Browser open    (universal fallback — opens pre-filled issue form)

    Always writes a local crash file first.
    Asks the user's permission before submitting unless ask_user=False.

    Args:
        exc_info:  Tuple from sys.exc_info().
        ask_user:  If True (default), prompt before submitting to GitHub.
    """
    print("[DEBUG] crash_reporter.file_report: collecting diagnostics")

    CRASH_DIR.mkdir(parents=True, exist_ok=True)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    crash_file = CRASH_DIR / f"crash_{timestamp}.md"

    report   = _build_report(exc_info)
    exc_type, exc_value, _ = exc_info
    title    = f"[crash] {exc_type.__name__}: {str(exc_value)[:80]}"

    crash_file.write_text(report, encoding="utf-8")
    print(f"\n[AJS] Crash report saved: {crash_file}")
    log.error("Crash report written to %s", crash_file)

    if ask_user:
        print("\n[AJS] Something went wrong. Submit a bug report so we can fix it?")
        print("      Press Enter to open the report in your browser  /  Esc to skip: ",
              end="", flush=True)
        try:
            import msvcrt as _m  # Windows
            key = _m.getwch()
        except ImportError:
            try:
                import tty as _t, termios as _tr
                fd = __import__("sys").stdin.fileno()
                old = _tr.tcgetattr(fd)
                try:
                    _t.setraw(fd)
                    key = __import__("sys").stdin.read(1)
                finally:
                    _tr.tcsetattr(fd, _tr.TCSADRAIN, old)
            except Exception:
                key = input().strip()[:1] or "\r"
        except Exception:
            key = "\r"
        print()
        if key not in ("\r", "\n"):
            print(f"[AJS] Report not submitted. File: {crash_file}")
            return

    # Try automated submission first, fall back to browser.
    url = _try_gh_cli(title, report) or _try_github_api(title, report)
    if url:
        print(f"[AJS] Bug report filed: {url}")
        log.info("Crash issue filed: %s", url)
    else:
        _open_browser_issue(title, report, crash_file)
