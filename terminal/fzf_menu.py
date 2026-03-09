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

print("[DEBUG] fzf_menu.py: module loading")

from logger import get_logger

log = get_logger("fzf_menu")

_FZF_AVAILABLE: Optional[bool] = None  # cached after first check


def _check_fzf() -> bool:
    """Return True if fzf is available in PATH (result is cached)."""
    global _FZF_AVAILABLE
    if _FZF_AVAILABLE is None:
        _FZF_AVAILABLE = shutil.which("fzf") is not None
        print(f"[DEBUG] fzf_menu._check_fzf: fzf available={_FZF_AVAILABLE}")
        log.debug("fzf available: %s", _FZF_AVAILABLE)
    return _FZF_AVAILABLE


# ---------------------------------------------------------------------------
# fzf-based selection
# ---------------------------------------------------------------------------

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
    print(f"[DEBUG] fzf_menu._fzf_select: {len(items)} items, multi={multi}, read0={read0}, prompt='{prompt}'")
    log.debug("fzf_select: %d items, multi=%s, read0=%s, prompt='%s'", len(items), multi, read0, prompt)

    cmd = [
        "fzf",
        "--prompt", f"{prompt} > ",
        "--height", "70%",
        "--layout", "reverse",
        "--border",
        "--ansi",
    ]

    if read0:
        cmd.extend(["--read0", "--print0"])

    if multi:
        cmd.append("--multi")

    if header:
        cmd.extend(["--header", header])

    stdin_data = "\x00".join(items) if read0 else "\n".join(items)

    try:
        result = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        print(f"[DEBUG] fzf_menu._fzf_select: fzf rc={result.returncode}")
        log.debug("fzf rc=%d", result.returncode)

        if result.returncode == 0:
            if read0:
                selected = [s for s in result.stdout.split("\x00") if s.strip()]
            else:
                selected = [line for line in result.stdout.splitlines() if line.strip()]
            print(f"[DEBUG] fzf_menu._fzf_select: selected {len(selected)} item(s)")
            log.info("fzf selection: %d item(s) selected", len(selected))
            return selected
        elif result.returncode == 130:
            # User pressed Escape or Ctrl-C.
            print("[DEBUG] fzf_menu._fzf_select: user cancelled (rc=130)")
            log.info("fzf: user cancelled")
            return []
        else:
            print(f"[DEBUG] fzf_menu._fzf_select: fzf error rc={result.returncode} stderr={result.stderr.strip()}")
            log.warning("fzf error rc=%d: %s", result.returncode, result.stderr.strip())
            return []

    except FileNotFoundError:
        print("[DEBUG] fzf_menu._fzf_select: fzf binary not found at runtime")
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
    print(f"\n[DEBUG] fzf_menu._numbered_select: {len(items)} items, multi={multi}")
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
                print(f"[DEBUG] fzf_menu._numbered_select: selected {len(selected)} item(s)")
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
    print(f"[DEBUG] fzf_menu.select: called with {len(items)} items, prompt='{prompt}', multi={multi}, read0={read0}")
    log.info("select() called: %d items, prompt='%s', multi=%s, read0=%s", len(items), prompt, multi, read0)

    if not items:
        print("[DEBUG] fzf_menu.select: empty items list — returning empty")
        log.warning("select() called with empty items list")
        return []

    if _check_fzf():
        return _fzf_select(items, prompt, multi, read0=read0, header=header)
    else:
        print("[DEBUG] fzf_menu.select: fzf not found — using numbered fallback")
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
    print(f"[DEBUG] fzf_menu.input_prompt: prompt='{prompt}'")
    log.debug("input_prompt: '%s'", prompt)

    if _check_fzf():
        # fzf --print-query with no items lets user type freely and press Enter.
        cmd = [
            "fzf",
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
                print(f"[DEBUG] fzf_menu.input_prompt: fzf query='{value}'")
                log.debug("fzf input_prompt result: '%s'", value)
                return value
        except (FileNotFoundError, Exception) as exc:
            print(f"[DEBUG] fzf_menu.input_prompt: fzf failed — {exc}, falling back to input()")
            log.warning("fzf input_prompt failed: %s — falling back to input()", exc)

    # Plain fallback.
    try:
        value = input(f"{prompt}: ").strip()
        print(f"[DEBUG] fzf_menu.input_prompt: plain input='{value}'")
        log.debug("plain input_prompt result: '%s'", value)
        return value
    except (EOFError, KeyboardInterrupt):
        print("\n[AJS] Input cancelled.")
        log.info("KeyboardInterrupt in input_prompt")
        return ""
