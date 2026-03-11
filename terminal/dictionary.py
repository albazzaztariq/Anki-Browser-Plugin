"""
AJS Terminal — dictionary.py
Retrieves a structured Japanese dictionary entry for a word using the local LLM.

Sends a carefully crafted prompt to Ollama instructing it to return a JSON object
with all required fields.  Retries up to LLM_MAX_RETRIES times on malformed responses
(FR-10 / E-6).

Inputs:
  word             (str) — the Japanese word (Hiragana/Kanji/Romaji)
  context_sentence (str) — a transcript sentence providing usage context

Outputs:
  dict — {
      "word":             str  (kanji form, e.g. "甚だしい"),
      "reading":          str  (hiragana, e.g. "はなはだしい"),
      "definition_en":    str  (English definition),
      "example_sentence": str  (Japanese example sentence),
      "part_of_speech":   str  (e.g. "い-adjective"),
  }

Packages used:
  - llm.py (local) — sends prompt to Ollama
  - json   (stdlib) — parses LLM JSON response
  - re     (stdlib) — strips markdown code fences from LLM output
"""

import json
import re
import sys
import time
from typing import Dict, Optional


from config import LLM_MAX_RETRIES

# Seconds to wait before each retry attempt (exponential: 2s, 4s, 8s).
_RETRY_DELAYS = [2, 4, 8]
from logger import get_logger
from llm import generate

log = get_logger("dictionary")

# Required fields in every valid LLM dictionary response.
_REQUIRED_FIELDS = {"word", "reading", "definition_en", "example_sentence", "part_of_speech"}

# Prompt template.  We use explicit JSON schema to constrain the LLM output.
_PROMPT_TEMPLATE = """\
You are a precise Japanese dictionary assistant. The user wants a dictionary entry for a Japanese word.

Word to look up: {word}
Context sentence from a Japanese video: {context}

Return ONLY valid JSON with EXACTLY these fields and NO other text:
{{
  "word": "<the word in its most common kanji/kana form>",
  "reading": "<full hiragana reading of the word>",
  "definition_en": "<clear English definition, 1-2 sentences, matching the nuance shown in the context>",
  "example_sentence": "<a natural Japanese example sentence using this word>",
  "part_of_speech": "<e.g. noun, verb, い-adjective, な-adjective, adverb, particle>"
}}

Rules:
- Respond with ONLY the JSON object. No markdown, no explanation, no code fences.
- The example_sentence must be in Japanese (kanji + kana).
- The reading must be in hiragana only.
- Match the meaning to the context sentence if possible.
"""


def _strip_code_fences(text: str) -> str:
    """Remove markdown ```json ... ``` or ``` ... ``` wrappers from LLM output."""
    # Remove ```json ... ``` or ``` ... ``` blocks
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


def _extract_json(text: str) -> Optional[Dict]:
    """
    Attempt to extract a JSON object from text that may contain extra prose.
    Returns the parsed dict or None.
    """
    # First try: parse the whole stripped text.
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Second try: find the first {...} block via regex.
    match = re.search(r"\{.*?\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _validate(data: dict) -> bool:
    """Return True if all required fields are present and non-empty."""
    for field in _REQUIRED_FIELDS:
        value = data.get(field, "")
        if not isinstance(value, str) or not value.strip():
            log.warning("LLM response missing required field: '%s'", field)
            return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_definition(word: str, context_sentence: str) -> dict:
    """
    Retrieve a dictionary entry for the given word using the local LLM.

    Retries up to LLM_MAX_RETRIES times on malformed/invalid responses (FR-10).

    Args:
        word:             Japanese word in any script.
        context_sentence: A sentence from the video transcript for context.

    Returns:
        dict with keys: word, reading, definition_en, example_sentence, part_of_speech.

    Raises:
        RuntimeError: If all retries fail (E-6).
    """
    log.info("get_definition called: word='%s'", word)

    prompt = _PROMPT_TEMPLATE.format(word=word, context=context_sentence or "(no context)")

    last_error: str = "Unknown error"

    for attempt in range(1, LLM_MAX_RETRIES + 1):
        log.debug("Dictionary LLM attempt %d/%d for word='%s'", attempt, LLM_MAX_RETRIES, word)

        try:
            raw_response = generate(prompt)
        except RuntimeError as exc:
            err_str = str(exc)
            log.error("LLM generate failed on attempt %d: %s", attempt, exc)
            last_error = err_str

            # Connection refused = Ollama is down.  No point retrying — fail fast.
            if "CONNECTION_ERROR" in err_str:
                print(f"\n[AJS] Ollama is not running. Start it and try again.")
                raise RuntimeError(err_str) from exc

            # Timeout = model loading or busy.  Retry with backoff.
            delay = _RETRY_DELAYS[min(attempt - 1, len(_RETRY_DELAYS) - 1)]
            print(f"\n[AJS] LLM attempt {attempt}/{LLM_MAX_RETRIES} failed (timeout). "
                  f"Retrying in {delay}s...")
            log.warning("Timeout on attempt %d — sleeping %ds before retry", attempt, delay)
            time.sleep(delay)
            continue

        log.debug("Raw LLM response (attempt %d): %s", attempt, raw_response[:300])

        data = _extract_json(raw_response)
        if data is None:
            last_error = f"Could not extract JSON from LLM response: {raw_response[:200]}"
            log.warning("JSON extraction failed on attempt %d", attempt)
            if attempt < LLM_MAX_RETRIES:
                print(f"[AJS] LLM returned malformed output (attempt {attempt}/{LLM_MAX_RETRIES}). Retrying...")
            continue

        if not _validate(data):
            last_error = f"LLM response missing required fields. Got: {list(data.keys())}"
            log.warning("Validation failed on attempt %d. Fields present: %s", attempt, list(data.keys()))
            if attempt < LLM_MAX_RETRIES:
                print(f"[AJS] LLM response incomplete (attempt {attempt}/{LLM_MAX_RETRIES}). Retrying...")
            continue

        # Normalise — strip extra whitespace from all string values.
        clean = {k: (v.strip() if isinstance(v, str) else v) for k, v in data.items()}
        log.info("Dictionary entry retrieved on attempt %d: word='%s' reading='%s'",
                 attempt, clean.get("word"), clean.get("reading"))
        return clean

    # All retries exhausted.
    log.error("All %d LLM attempts failed for word='%s'. Last error: %s",
              LLM_MAX_RETRIES, word, last_error)
    raise RuntimeError(
        f"[AJS] Failed to get dictionary entry for '{word}' after {LLM_MAX_RETRIES} attempts.\n"
        f"Last error: {last_error}\n"
        f"Check that Ollama is running and the model '{__import__('config').OLLAMA_MODEL}' is pulled."
    )
