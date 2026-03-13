"""
AJS Terminal — fzf_menu.py
Interactive fuzzy-search selection menus using fzf.

Provides a unified interface for presenting lists of choices to the user.
If fzf is not found in PATH, falls back to a simple numbered list printed
to the terminal (so the pipeline never crashes due to a missing fzf binary).

Inputs (select function):
  items  (list[str]) — list of choices to display
  prompt (str)       — prompt label shown above the list
  multi  (bool)      — if True, allow selecting multiple items (fzf --multi)

Outputs:
  list[str] — list of selected items (empty list if user cancels)

Packages used:
  - subprocess (stdlib) — spawns fzf process with stdin/stdout pipes
  - shutil     (stdlib) — checks for fzf in PATH
"""

import shutil
import subprocess
import sys
from typing import Optional


from logger import get_logger

log = get_logger("fzf_menu")

_FZF_AVAILABLE: Optional[bool] = None  # cached after first check
_FZF_PATH: Optional[str] = None        # resolved fzf binary path


def _check_fzf() -> bool:
    """
    Return True if fzf is available (result is cached).
    Checks PATH first, then known install locations so ajs works even when
    the installer's PATH update hasn't propagated to the current process.
    """
    global _FZF_AVAILABLE, _FZF_PATH
    if _FZF_AVAILABLE is None:
        import os
        from pathlib import Path

        _FZF_PATH = shutil.which("fzf")

        if not _FZF_PATH:
            # Installer puts fzf alongside ajs in %APPDATA%\AJS (Windows)
            # or ~/.ajs/bin (macOS/Linux).
            candidates = [
                Path(os.environ.get("APPDATA", "")) / "AJS" / "fzf.exe",
                Path.home() / ".ajs" / "bin" / "fzf",
                Path.home() / ".local" / "bin" / "fzf",
            ]
            for c in candidates:
                if c.exists():
                    _FZF_PATH = str(c)
                    break

        _FZF_AVAILABLE = _FZF_PATH is not None
        log.debug("fzf available: %s path: %s", _FZF_AVAILABLE, _FZF_PATH)
    return _FZF_AVAILABLE


# ---------------------------------------------------------------------------
# fzf-based selection
# ---------------------------------------------------------------------------

def fzf_select_with_query(items: list[str], prompt: str, header: str = "",
                          read0: bool = False, initial_query: str = "",
                          start_pos: int = 0) -> tuple[str, list[str], int]:
    """
    Like select() but also captures the fzf query string and raw exit code.
    Uses --print-query so we get both what the user typed and what they selected.

    Returns:
        (query, selected_items, exit_code)
        exit_code: 0 = item selected, 1 = no match (Enter with empty list),
                   130 = Esc/Ctrl-C, other = error.
    """

    if not _check_fzf():
        # Fallback: plain input for word, numbered list for segment.
        query = input_prompt(prompt)
        display = [s.splitlines()[0] if s.strip() else s for s in items]
        first_line_to_item = {s.splitlines()[0]: s for s in items if s.strip()}
        chosen_display = _numbered_select(display, prompt, multi=False)
        chosen = [first_line_to_item.get(c, c) for c in chosen_display]
        rc = 0 if chosen else 130
        return (query, chosen, rc)

    cmd = [
        _FZF_PATH,
        "--print-query",
        "--prompt", f"{prompt} > ",
        "--height", "85%",
        "--layout", "reverse",
        "--border",
        "--ansi",
        "--exact",
        "--no-hscroll",
    ]
    if read0:
        cmd.extend(["--read0", "--print0"])
    if header:
        cmd.extend(["--header", header])
    if initial_query:
        cmd.extend(["--query", initial_query])

    # Keep original order, but move cursor to the target segment on load.
    if start_pos > 0:
        cmd.extend(["--bind", f"load:pos({start_pos})"])

    # Binary stdin avoids Windows text-mode \n→\r\n translation which garbles items.
    # stderr=None lets it flow to the terminal (fzf may use it for rendering on some builds).
    stdin_sep = "\x00" if read0 else "\n"
    stdin_bytes = (stdin_sep.join(items) + stdin_sep).encode("utf-8")

    try:
        result = subprocess.run(
            cmd,
            input=stdin_bytes,
            stdout=subprocess.PIPE,
            stderr=None,
        )
        rc = result.returncode

        stdout_text = (result.stdout or b"").decode("utf-8", errors="replace")
        parts = stdout_text.split("\x00") if read0 else stdout_text.splitlines()
        query = parts[0].strip() if parts else ""
        selected = [p for p in parts[1:] if p.strip()]

        return (query, selected, rc)

    except FileNotFoundError:
        return ("", [], 130)
    except KeyboardInterrupt:
        return ("", [], 130)


def _fzf_select(items: list[str], prompt: str, multi: bool, read0: bool = False,
                header: str = "") -> list[str]:
    """
    Launch fzf with items piped to stdin.

    Args:
        items:  List of strings to display.
        prompt: Prompt label for the fzf header.
        multi:  Enable multi-select (--multi flag).
        read0:  If True, use NUL-delimited I/O so items can contain newlines
                (enables true multi-line entries in the fzf list).

    Returns:
        List of selected item strings. Empty list if user pressed Escape/Ctrl-C.
        When read0=True, each returned string is the full multi-line item text.
    """
    log.debug("fzf_select: %d items, multi=%s, read0=%s, prompt='%s'", len(items), multi, read0, prompt)

    cmd = [
        _FZF_PATH,
        "--prompt", f"{prompt} > ",
        "--height", "85%",
        "--layout", "reverse",
        "--border",
        "--ansi",
        "--exact",
        "--no-hscroll",
    ]

    if read0:
        cmd.extend(["--read0", "--print0"])

    if multi:
        cmd.append("--multi")

    if header:
        cmd.extend(["--header", header])

    if read0:
        stdin_bytes = ("\x00".join(items) + "\x00").encode("utf-8")
    else:
        stdin_text = "\n".join(items)

    try:
        if read0:
            result = subprocess.run(
                cmd,
                input=stdin_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout_text = (result.stdout or b"").decode("utf-8", errors="replace")
            stderr_text = (result.stderr or b"").decode("utf-8", errors="replace")
        else:
            result = subprocess.run(
                cmd,
                input=stdin_text,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            stdout_text = result.stdout
            stderr_text = result.stderr
        log.debug("fzf rc=%d", result.returncode)

        if result.returncode == 0:
            if read0:
                selected = [s for s in stdout_text.split("\x00") if s.strip()]
            else:
                selected = [line for line in stdout_text.splitlines() if line.strip()]
            log.info("fzf selection: %d item(s) selected", len(selected))
            return selected
        elif result.returncode == 130:
            # User pressed Escape or Ctrl-C.
            log.info("fzf: user cancelled")
            return []
        else:
            log.warning("fzf error rc=%d: %s", result.returncode, stderr_text.strip())
            return []

    except FileNotFoundError:
        log.error("fzf binary not found at runtime")
        return []
    except KeyboardInterrupt:
        print("\n[AJS] Selection cancelled.")
        log.info("KeyboardInterrupt during fzf selection")
        return []


# ---------------------------------------------------------------------------
# Numbered-list fallback (no fzf)
# ---------------------------------------------------------------------------

def _numbered_select(items: list[str], prompt: str, multi: bool) -> list[str]:
    """
    Simple numbered-list fallback when fzf is not available.

    Prints each item with a number, then reads the user's choice.
    For multi-select, accepts comma-separated numbers.

    Args:
        items:  List of choices.
        prompt: Display label.
        multi:  If True, accept comma-separated indices.

    Returns:
        List of selected items.
    """
    log.debug("Numbered fallback: %d items, multi=%s", len(items), multi)

    print(f"\n{'='*60}")
    print(f"  {prompt}")
    print(f"{'='*60}")

    for i, item in enumerate(items, 1):
        # Truncate long lines for display.
        display = item if len(item) <= 120 else item[:117] + "..."
        print(f"  {i:3d}. {display}")

    print(f"{'='*60}")

    if multi:
        hint = "(enter comma-separated numbers, e.g. 1,3,5 — or 'q' to cancel)"
    else:
        hint = "(enter a number — or 'q' to cancel)"

    print(f"  {hint}")

    while True:
        try:
            raw = input("Choice: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[AJS] Selection cancelled.")
            log.info("KeyboardInterrupt in numbered_select")
            return []

        if raw.lower() in ("q", "quit", "exit", ""):
            print("[AJS] Selection cancelled.")
            return []

        try:
            if multi:
                indices = [int(x.strip()) for x in raw.split(",")]
            else:
                indices = [int(raw)]

            selected = []
            valid = True
            for idx in indices:
                if 1 <= idx <= len(items):
                    selected.append(items[idx - 1])
                else:
                    print(f"  [!] Invalid choice: {idx} (must be 1–{len(items)})")
                    valid = False
                    break

            if valid and selected:
                log.info("Numbered selection: %d item(s) selected", len(selected))
                return selected

        except ValueError:
            print(f"  [!] Please enter a number{', or comma-separated numbers' if multi else ''}.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select(items: list[str], prompt: str = "Select", multi: bool = False,
           read0: bool = False, header: str = "") -> list[str]:
    """
    Present a selection menu to the user and return chosen items.

    Uses fzf if available; otherwise falls back to a numbered list.

    Args:
        items:  List of strings to choose from.
        prompt: Label shown at the top of the menu.
        multi:  If True, allow selecting multiple items.
        read0:  If True, use NUL-delimited I/O — items may contain newlines
                (multi-line display in fzf). Each returned string is the full
                multi-line item text; callers should split on '\\n' as needed.

    Returns:
        list[str] — selected items (may be empty if user cancelled).
    """
    log.info("select() called: %d items, prompt='%s', multi=%s, read0=%s", len(items), prompt, multi, read0)

    if not items:
        log.warning("select() called with empty items list")
        return []

    if _check_fzf():
        return _fzf_select(items, prompt, multi, read0=read0, header=header)
    else:
        log.info("fzf not found — using numbered list fallback")
        # Numbered fallback: display each item's first line as the list entry.
        display_items = [s.splitlines()[0] if s.strip() else s for s in items]
        chosen = _numbered_select(display_items, prompt, multi)
        # Map the display-only first line back to the full item.
        first_line_to_item = {s.splitlines()[0]: s for s in items if s.strip()}
        return [first_line_to_item.get(c, c) for c in chosen]


def input_prompt(prompt: str) -> str:
    """
    Show a simple text input prompt in the terminal and return the entered string.

    If fzf is available, uses fzf's --print-query mode so the user can type freely.
    Otherwise uses a plain input() call.

    Args:
        prompt: The question/label to show the user.

    Returns:
        str — user's input, stripped. Empty string if cancelled.
    """
    log.debug("input_prompt: '%s'", prompt)

    if _check_fzf():
        # fzf --print-query with no items lets user type freely and press Enter.
        cmd = [
            _FZF_PATH,
            "--print-query",
            "--prompt", f"{prompt} > ",
            "--height", "10%",
            "--layout", "reverse",
            "--border",
        ]
        try:
            result = subprocess.run(
                cmd,
                input="",
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            # --print-query prints the query on the first line even if nothing was selected.
            lines = result.stdout.splitlines()
            if lines:
                value = lines[0].strip()
                log.debug("fzf input_prompt result: '%s'", value)
                return value
        except (FileNotFoundError, Exception) as exc:
            log.warning("fzf input_prompt failed: %s — falling back to input()", exc)

    # Plain fallback.
    try:
        value = input(f"{prompt}: ").strip()
        log.debug("plain input_prompt result: '%s'", value)
        return value
    except (EOFError, KeyboardInterrupt):
        print("\n[AJS] Input cancelled.")
        log.info("KeyboardInterrupt in input_prompt")
        return ""
