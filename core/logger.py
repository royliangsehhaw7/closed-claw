import sys
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Log configuration
log_file = os.getenv("LOG_FILE", "logs/assistant.log")
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

# Create logs directory if it doesn't exist
Path(log_file).parent.mkdir(parents=True, exist_ok=True)

# ANSI color codes
class LogColors:
    RESET = "\033[0m"
    GRAY = "\033[38;20m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BOLD = "\033[1m"

# Custom formatter with colors
class ColoredFormatter(logging.Formatter):
    def __init__(self, fmt):
        super().__init__(fmt)

    def format(self, record):
        # Save the original levelname
        levelname = record.levelname

        # Apply colors based on log level
        if levelname == "DEBUG":
            record.levelname = f"{LogColors.GRAY}DEBUG{LogColors.RESET}"
        elif levelname == "INFO":
            record.levelname = f"{LogColors.GREEN}INFO{LogColors.RESET}"
        elif levelname == "WARNING":
            record.levelname = f"{LogColors.YELLOW}WARNING{LogColors.RESET}"
        elif levelname == "ERROR":
            record.levelname = f"{LogColors.RED}ERROR{LogColors.RESET}"
        elif levelname == "CRITICAL":
            record.levelname = f"{LogColors.RED}{LogColors.BOLD}CRITICAL{LogColors.RESET}"

        # Apply cyan to the logger name
        record.name = f"{LogColors.CYAN}{record.name}{LogColors.RESET}"

        return super().format(record)

# Log format
fmt = "%(asctime)s [%(levelname)s] %(name)s | %(message)s"

# Configure logging
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

# Get the root logger and clear existing handlers
logger = logging.getLogger("app")
logger.handlers.clear()

# Create new handlers with colored formatter
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
file_handler.setFormatter(logging.Formatter(fmt))

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(ColoredFormatter(fmt))

# Add handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)
logger.setLevel(log_level)