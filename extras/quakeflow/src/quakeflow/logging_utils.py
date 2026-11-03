"""Single place where logging is configured, so every module logs the same way."""

from __future__ import annotations

import logging
import sys

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-22s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:  # never double-configure (matters when pytest imports us twice)
        root.setLevel(level)
        return
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
