"""
AJS Terminal — logger.py
Structured rotating-file logger for the terminal pipeline.

Outputs JSON log entries with fields: timestamp, level, component, message.
Falls back gracefully if the ~/.ajs directory cannot be created (e.g., permission error).

Usage:
    from logger import get_logger
    log = get_logger("url_capture")
    log.info("Captured URL: %s", url)
"""

import json
import logging
import logging.handlers
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# Import config carefully — if config itself fails we still want a logger.
try:
    from config import LOG_FILE, LOG_MAX_BYTES, LOG_BACKUP_COUNT, LOG_DIR
except ImportError:
    LOG_DIR = Path.home() / ".ajs"
    LOG_FILE = LOG_DIR / "ajs.log"
    LOG_MAX_BYTES = 5 * 1024 * 1024
    LOG_BACKUP_COUNT = 3



class _JsonFormatter(logging.Formatter):
    """
    Custom formatter that serialises each log record as a single JSON line.
    Fields: timestamp (ISO-8601 UTC), level, component (logger name), message.
    """

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


def _build_file_handler() -> Optional[logging.Handler]:
    """
    Creates a RotatingFileHandler writing to LOG_FILE.
    Returns None if the directory cannot be created or the file cannot be opened.
    """
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
    except OSError as exc:
        return None


# Build the handlers list once at module import.
_handlers: List[logging.Handler] = []

_file_handler = _build_file_handler()
if _file_handler:
    _handlers.append(_file_handler)

# Stream handler — WARNING and above only, so DEBUG/INFO stay out of the terminal.
_stream_handler = logging.StreamHandler(sys.stderr)
_stream_handler.setLevel(logging.WARNING)
_stream_handler.setFormatter(
    logging.Formatter("[%(levelname)s] %(name)s — %(message)s")
)
_handlers.append(_stream_handler)



def get_logger(component: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Return a named logger wired to the AJS rotating file + stderr handlers.

    Args:
        component: Short name identifying the calling module (e.g. "url_capture").
        level: Logging level (default DEBUG to capture all debug prints).

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(f"ajs.{component}")
    logger.setLevel(level)

    # Avoid adding duplicate handlers if get_logger is called multiple times.
    if not logger.handlers:
        for h in _handlers:
            logger.addHandler(h)
        logger.propagate = False

    return logger
