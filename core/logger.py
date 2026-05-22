import sys
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

log_file = os.getenv("LOG_FILE", "logs/assistant.log")
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

Path(log_file).parent.mkdir(parents=True, exist_ok=True)

fmt = "%(asctime)s [%(levelname)s] %(name)s | %(message)s"

logging.basicConfig(
    level=log_level,
    format=fmt,
    handlers=[
        RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("app")