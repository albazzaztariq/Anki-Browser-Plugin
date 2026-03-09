"""
AJS Anki Add-on — logger.py
Structured rotating-file logger for the Anki add-on layer.

Mirrors the terminal logger but writes to anki_addon.log so the two layers
produce separate log files.  Uses only Python stdlib so it runs in Anki's
bundled Python without any additional dependencies.

Usage:
    from .logger import get_logger
    log = get_logger("bridge")
    log.info("Pending card detected")
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from .config import LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT, LOG_DIR
except ImportError:
    # Fallback when imported directly (e.g. during testing outside Anki).
    LOG_DIR = Path.home() / ".ajs"
    LOG_FILE = LOG_DIR / "anki_addon.log"
    LOG_MAX_BYTES = 5 * 1024 * 1024
    LOG_BACKUP_COUNT = 3


class _JsonFormatter(logging.Formatter):
    """Serialises log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def _build_file_handler() -> logging.Handler | None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            str(LOG_FILE),
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        handler.setFormatter(_JsonFormatter())
        return handler
    except OSError:
        return None


_handlers: list[logging.Handler] = []

_fh = _build_file_handler()
if _fh:
    _handlers.append(_fh)



def get_logger(component: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Return a named logger wired to the AJS add-on rotating file + stderr handlers.

    Args:
        component: Short name for the calling module (e.g. "bridge", "preview").
        level:     Logging level (default DEBUG).

    Returns:
        Configured logging.Logger instance.
    """
    logger = logging.getLogger(f"ajs_addon.{component}")
    logger.setLevel(level)
    if not logger.handlers:
        for h in _handlers:
            logger.addHandler(h)
        logger.propagate = False
    return logger
