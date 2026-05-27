import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Detect Cloud Run environment
IS_CLOUD_RUN = os.getenv("K_SERVICE") is not None

# Define log directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Safe directory creation
os.makedirs(LOG_DIR, exist_ok=True)

# Generate log filename
log_filename = f"app_{datetime.now().strftime('%Y-%m-%d')}.log"
log_path = os.path.join(LOG_DIR, log_filename)

# Create logger
logger = logging.getLogger("AI-Microservices")
logger.setLevel(logging.DEBUG)

# Prevent duplicate handlers
if not logger.handlers:

    # Common detailed log format
    detailed_format = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] "
        "[%(filename)s:%(lineno)d] [%(funcName)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler (Cloud Run captures stdout)
    c_handler = logging.StreamHandler(sys.stdout)
    c_handler.setLevel(logging.DEBUG)
    c_handler.setFormatter(detailed_format)
    logger.addHandler(c_handler)

    # File logging only for local development
    if not IS_CLOUD_RUN:
        f_handler = RotatingFileHandler(
            log_path,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        f_handler.setLevel(logging.DEBUG)
        f_handler.setFormatter(detailed_format)
        logger.addHandler(f_handler)


def get_logger(name: str):
    return logger.getChild(name)