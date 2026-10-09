"""
Structured logging system for MediNexus AI.
"""

import logging
import sys
from pathlib import Path
from config.constants import LOGS_DIR

LOGS_DIR.mkdir(parents=True, exist_ok=True)
APP_LOG_FILE = LOGS_DIR / "app.log"
AUDIT_LOG_FILE = LOGS_DIR / "audit.log"


def get_logger(name: str = "medinexus") -> logging.Logger:
    """Return a configured logger with console and file handlers."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # File handler
        fh = logging.FileHandler(APP_LOG_FILE, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        # Stream handler
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(formatter)
        logger.addHandler(sh)

    return logger
