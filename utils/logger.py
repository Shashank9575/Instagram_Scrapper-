"""
Logging Setup
=============
Structured, colored logging to both console and file.
"""

import logging
import os
from datetime import datetime

try:
    import colorlog
    HAS_COLOR = True
except ImportError:
    HAS_COLOR = False


def get_logger(name: str = "instagram_scraper") -> logging.Logger:
    """Return a configured logger instance."""

    os.makedirs("logs", exist_ok=True)
    log_filename = f"logs/scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger(name)

    # Avoid duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # ── File Handler (full debug logs) ─────────────────────────────────────
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(module)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    # ── Console Handler (info+ with color) ─────────────────────────────────
    if HAS_COLOR:
        console_handler = colorlog.StreamHandler()
        console_handler.setLevel(logging.INFO)
        color_fmt = colorlog.ColoredFormatter(
            fmt="%(log_color)s%(asctime)s%(reset)s | %(log_color)s%(levelname)-8s%(reset)s | %(message)s",
            datefmt="%H:%M:%S",
            log_colors={
                "DEBUG":    "cyan",
                "INFO":     "green",
                "WARNING":  "yellow",
                "ERROR":    "red",
                "CRITICAL": "bold_red",
            },
        )
        console_handler.setFormatter(color_fmt)
    else:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(file_fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info(f"Logger initialized → {log_filename}")
    return logger
