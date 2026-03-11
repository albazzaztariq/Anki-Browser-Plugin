"""
AJS Terminal — llm.py
HTTP interface to the local Ollama LLM server.

Sends a text prompt to the Ollama /api/generate endpoint and returns the
model's response text.  Handles connection errors, timeouts, and non-200
HTTP responses with clear messages (NFR-5).

Inputs:
  prompt (str) — the complete prompt string to send to the model
  stream (bool) — if True, stream tokens; if False (default), wait for full response

Outputs:
  str — the model's text response

Packages used:
  - requests (third-party, bundled with Anki's Python) — HTTP POST to Ollama REST API
      POST http://localhost:11434/api/generate
      Body: {"model": <OLLAMA_MODEL>, "prompt": <prompt>, "stream": false}
      Response JSON field: "response"
"""

import json
import sys
import threading


import requests  # type: ignore

from config import OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT
from logger import get_logger

log = get_logger("llm")

_GENERATE_ENDPOINT = f"{OLLAMA_URL}/api/generate"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(prompt: str, stream: bool = False) -> str:
    """
    Send a prompt to the local Ollama instance and return the model response.

    Args:
        prompt: Full prompt text.
        stream: If False (default), wait for complete response before returning.
                If True, stream tokens — in streaming mode the function yields
                concatenated text chunks (kept False for simplicity in AJS pipeline).

    Returns:
        str — the model's text output.

    Raises:
        RuntimeError — if Ollama is unreachable or returns an error (E-1 / E-6).
    """
    log.info("Sending prompt to Ollama model=%s len=%d", OLLAMA_MODEL, len(prompt))

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": stream,
    }

    # Spinner — prints a dot every 3s so the user knows we're not hung.
    _stop_spinner = threading.Event()
    def _spin():
        while not _stop_spinner.wait(timeout=3):
            print(".", end="", flush=True)
    _spinner = threading.Thread(target=_spin, daemon=True)
    _spinner.start()

    try:
        response = requests.post(
            _GENERATE_ENDPOINT,
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
    except requests.exceptions.ConnectionError as exc:
        _stop_spinner.set(); print()
        log.error("Cannot connect to Ollama at %s: %s", OLLAMA_URL, exc)
        raise RuntimeError(
            f"CONNECTION_ERROR: Cannot reach Ollama at {OLLAMA_URL}. "
            f"Ensure Ollama is running (https://ollama.com). Details: {exc}"
        ) from exc
    except requests.exceptions.Timeout as exc:
        _stop_spinner.set(); print()
        log.error("Ollama request timed out after %ds: %s", OLLAMA_TIMEOUT, exc)
        raise RuntimeError(
            f"TIMEOUT: Ollama took over {OLLAMA_TIMEOUT}s. "
            f"The model may still be loading — retrying may help."
        ) from exc

    _stop_spinner.set(); print()
    log.debug("Ollama response status: %d", response.status_code)

    if response.status_code != 200:
        log.error("Ollama returned HTTP %d: %s", response.status_code, response.text[:300])
        raise RuntimeError(
            f"Ollama returned HTTP {response.status_code}. "
            f"Check that the model '{OLLAMA_MODEL}' is pulled: ollama pull {OLLAMA_MODEL}"
        )

    if stream:
        # In streaming mode, Ollama sends newline-delimited JSON objects.
        full_text = ""
        for line in response.text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
                full_text += chunk.get("response", "")
                if chunk.get("done", False):
                    break
            except json.JSONDecodeError:
                continue
        log.debug("Streamed response length=%d", len(full_text))
        return full_text
    else:
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            log.error("Failed to parse Ollama JSON response: %s", exc)
            raise RuntimeError(f"Malformed response from Ollama: {exc}") from exc

        text = data.get("response", "")
        log.info("Ollama response received, length=%d chars", len(text))
        return text


def is_ollama_running() -> bool:
    """
    Quick health check — returns True if Ollama is reachable at localhost:11434.
    Used by installer and add-on bridge (E-1).
    """
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        running = r.status_code == 200
        log.debug("Ollama health check: status=%d", r.status_code)
        return running
    except Exception as exc:
        log.debug("Ollama not reachable: %s", exc)
        return False
