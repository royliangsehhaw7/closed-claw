import sys
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
import colorlog
from dotenv import load_dotenv

load_dotenv()

log_file = os.getenv("LOG_FILE", "logs/assistant.log")
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

Path(log_file).parent.mkdir(parents=True, exist_ok=True)

fmt = "%(asctime)s [%(levelname)s] %(name)s | %(message)s"
colored_fmt = "%(asctime)s [%(log_color)s%(levelname)s%(reset)s] %(name)s | %(message)s"

logger = logging.getLogger("app")
logger.setLevel(log_level)
logger.propagate = False

# Console handler with colors
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(colorlog.ColoredFormatter(
    colored_fmt,
    log_colors={
        "DEBUG": "white",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    }
))

# File handler without colors
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
file_handler.setFormatter(logging.Formatter(fmt))

logger.addHandler(stream_handler)
logger.addHandler(file_handler)