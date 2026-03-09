"""
AJS Terminal — url_capture.py
Captures the active browser tab URL from Chrome or Safari.

Platform strategy:
  - macOS  : AppleScript via `osascript` — reads URL directly from Chrome/Safari.
  - Windows: PowerShell UIAutomation query against Chrome's address bar, with a
             window-title-parsing fallback (Chrome shows "Page Title — Google Chrome"
             in the taskbar).  If both fail, user is prompted to paste the URL manually
             (E-2).

Inputs : None (reads live system state)
Outputs: str — the full URL of the active tab, e.g. "https://www.youtube.com/watch?v=..."

Packages used:
  - subprocess (stdlib) — runs osascript / PowerShell
  - pygetwindow (third-party) — enumerates open windows by title on Windows
  - pyperclip  (third-party) — clipboard read as last-resort fallback on Windows
"""

import platform
import subprocess
import sys
from typing import Optional

print("[DEBUG] url_capture.py: module loading")

from logger import get_logger

log = get_logger("url_capture")

# ---------------------------------------------------------------------------
# macOS implementation
# ---------------------------------------------------------------------------

_APPLESCRIPT_CHROME = """
tell application "Google Chrome"
    get URL of active tab of front window
end tell
"""

_APPLESCRIPT_SAFARI = """
tell application "Safari"
    get URL of front document
end tell
"""


def _capture_macos() -> Optional[str]:
    """
    Try Chrome first, then Safari via AppleScript.
    Returns the URL string or None on failure.
    """
    print("[DEBUG] url_capture._capture_macos: trying Chrome AppleScript")
    log.debug("url_capture: attempting macOS AppleScript capture")

    for script, browser in [(_APPLESCRIPT_CHROME, "Chrome"), (_APPLESCRIPT_SAFARI, "Safari")]:
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                if url:
                    print(f"[DEBUG] url_capture._capture_macos: got URL from {browser}: {url}")
                    log.info("URL captured from %s: %s", browser, url)
                    return url
            else:
                print(f"[DEBUG] url_capture._capture_macos: {browser} script returned rc={result.returncode}: {result.stderr.strip()}")
                log.warning("%s AppleScript failed: %s", browser, result.stderr.strip())
        except FileNotFoundError:
            print("[DEBUG] url_capture._capture_macos: osascript not found")
            log.error("osascript not found — not running on macOS?")
            break
        except subprocess.TimeoutExpired:
            print(f"[DEBUG] url_capture._capture_macos: {browser} AppleScript timed out")
            log.warning("%s AppleScript timed out", browser)

    return None


# ---------------------------------------------------------------------------
# Windows implementation
# ---------------------------------------------------------------------------

_PS_CHROME_URL = r"""
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$chrome = [System.Diagnostics.Process]::GetProcessesByName("chrome") | Select-Object -First 1
if (-not $chrome) { exit 1 }

$desktop    = [System.Windows.Automation.AutomationElement]::RootElement
$condition  = New-Object System.Windows.Automation.PropertyCondition(
                  [System.Windows.Automation.AutomationElement]::ProcessIdProperty,
                  $chrome.Id)
$chromeWin  = $desktop.FindFirst([System.Windows.Automation.TreeScope]::Children, $condition)
if (-not $chromeWin) { exit 1 }

$editCondition = New-Object System.Windows.Automation.PropertyCondition(
                     [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
                     [System.Windows.Automation.ControlType]::Edit)
$addressBar = $chromeWin.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $editCondition)
if (-not $addressBar) { exit 1 }

$pattern = $addressBar.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
$pattern.Current.Value
"""


def _capture_windows_uiautomation() -> Optional[str]:
    """
    Use Windows UIAutomation via PowerShell to read Chrome's address bar.
    Returns URL string or None.
    """
    print("[DEBUG] url_capture._capture_windows_uiautomation: trying PS UIAutomation")
    log.debug("url_capture: attempting Windows UIAutomation capture")
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_CHROME_URL],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            if url.startswith("http"):
                print(f"[DEBUG] url_capture._capture_windows_uiautomation: got URL: {url}")
                log.info("UIAutomation URL captured: %s", url)
                return url
        print(f"[DEBUG] url_capture._capture_windows_uiautomation: rc={result.returncode} stderr={result.stderr.strip()}")
        log.warning("UIAutomation capture failed rc=%d: %s", result.returncode, result.stderr.strip())
    except FileNotFoundError:
        print("[DEBUG] url_capture._capture_windows_uiautomation: powershell not found")
        log.error("powershell not found")
    except subprocess.TimeoutExpired:
        print("[DEBUG] url_capture._capture_windows_uiautomation: powershell timed out")
        log.warning("UIAutomation PowerShell timed out")
    return None


def _capture_windows_window_title() -> Optional[str]:
    """
    Activate the Chrome window, send Ctrl+L to focus the address bar,
    Ctrl+A + Ctrl+C to copy the URL, then read the clipboard.
    """
    print("[DEBUG] url_capture._capture_windows_window_title: trying pygetwindow + pyautogui")
    log.debug("url_capture: attempting pygetwindow + keyboard shortcut capture")
    try:
        import pygetwindow as gw  # type: ignore
        import pyperclip          # type: ignore
        import time

        windows = gw.getWindowsWithTitle("Google Chrome")
        if not windows:
            print("[DEBUG] url_capture: no Chrome windows found")
            log.warning("No Chrome windows found via pygetwindow")
            return None

        chrome_win = windows[0]
        print(f"[DEBUG] url_capture: activating Chrome window: '{chrome_win.title}'")
        chrome_win.activate()
        time.sleep(0.5)

        # Send Ctrl+L (focus address bar) + Ctrl+A (select all) + Ctrl+C (copy)
        # via PowerShell SendInput — more reliable than SendKeys.
        import subprocess as sp
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.SendKeys]::SendWait('%d'); "  # Alt+D = address bar
            "Start-Sleep -Milliseconds 300; "
            "[System.Windows.Forms.SendKeys]::SendWait('^a'); "
            "Start-Sleep -Milliseconds 100; "
            "[System.Windows.Forms.SendKeys]::SendWait('^c'); "
            "Start-Sleep -Milliseconds 200"
        )
        sp.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
            capture_output=True, timeout=5,
        )
        time.sleep(0.3)

        url = pyperclip.paste().strip()
        print(f"[DEBUG] url_capture: clipboard='{url[:80]}'")
        if url.startswith("http"):
            log.info("Clipboard URL captured: %s", url)
            return url

        log.warning("Clipboard does not contain a URL: %s", url[:80])
    except ImportError as exc:
        print(f"[DEBUG] url_capture: import error — {exc}")
        log.warning("pygetwindow/pyperclip not available: %s", exc)
    except Exception as exc:
        print(f"[DEBUG] url_capture: window capture error — {exc}")
        log.exception("Window capture error: %s", exc)
    return None


def _capture_windows() -> Optional[str]:
    """Try UIAutomation first, fall back to window-title / clipboard method."""
    url = _capture_windows_uiautomation()
    if url:
        return url
    return _capture_windows_window_title()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_url() -> str:
    """
    Capture the active browser tab URL.

    Tries platform-specific automatic capture first.  If that fails, prompts the
    user to paste the URL manually (E-2 fallback).

    Returns:
        str — a non-empty URL string.

    Raises:
        SystemExit — if the user provides no URL when prompted.
    """
    print("[DEBUG] url_capture.get_url: starting URL capture")
    log.info("Starting URL capture on platform=%s", platform.system())

    system = platform.system()
    url: Optional[str] = None

    if system == "Darwin":
        url = _capture_macos()
    elif system == "Windows":
        url = _capture_windows()
    else:
        print(f"[DEBUG] url_capture.get_url: unsupported platform '{system}', skipping auto-capture")
        log.warning("Unsupported platform '%s' — skipping auto URL capture", system)

    if url:
        print(f"[DEBUG] url_capture.get_url: returning URL: {url}")
        return url

    # E-2 fallback: prompt the user.
    print("\n[AJS] Could not automatically read the browser URL.")
    print("      Make sure Google Chrome is the frontmost window, then try again.")
    print("      — OR — paste the YouTube URL below and press Enter:\n")
    try:
        url = input("URL: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[AJS] Aborted.")
        sys.exit(0)

    if not url:
        print("[AJS] No URL provided. Exiting.")
        log.error("User provided no URL — exiting")
        sys.exit(1)

    print(f"[DEBUG] url_capture.get_url: user-provided URL: {url}")
    log.info("User-provided URL: %s", url)
    return url
