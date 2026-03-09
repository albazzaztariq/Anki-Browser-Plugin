"""
AJS Installer — setup_token.py
Writes the GitHub issue-reporting token to ~/.ajs/.token at install time.

This token is a fine-grained GitHub PAT scoped to Issues: Read+Write on
albazzaztariq/Anki-Browser-Plugin only.  It allows end users to file bug
reports directly from the AJS crash reporter without needing a GitHub account.

To regenerate the token:
  1. Go to https://github.com/settings/personal-access-tokens/new
  2. Repository access: Only selected repositories → Anki-Browser-Plugin
  3. Permissions: Issues → Read and Write
  4. Generate token, copy it, paste it into TOKEN below.

Called by the installer after extracting files.
"""

from pathlib import Path

# Replace this value when the token is regenerated.
TOKEN = ""   # <-- paste fine-grained PAT here before building installer


def write_token() -> bool:
    """Write the token to ~/.ajs/.token. Returns True on success."""
    if not TOKEN:
        print("[setup_token] No token configured — skipping.")
        return False
    try:
        token_path = Path.home() / ".ajs" / ".token"
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(TOKEN, encoding="utf-8")
        # Restrict permissions on Unix (no-op on Windows).
        try:
            token_path.chmod(0o600)
        except Exception:
            pass
        print(f"[setup_token] Token written to {token_path}")
        return True
    except Exception as exc:
        print(f"[setup_token] Failed to write token: {exc}")
        return False


if __name__ == "__main__":
    write_token()
