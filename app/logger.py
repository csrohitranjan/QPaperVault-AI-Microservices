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


class CustomFormatter(logging.Formatter):
    """Custom formatter for console logs."""

    blue = "🔵"
    green = "✅"
    orange = "🟠"
    red = "🔴"
    diamond = "💎"
    rocket = "🚀"

    format_str = "[%(asctime)s] %(icon)s %(message)s"

    def format(self, record):
        if not hasattr(record, "icon"):
            if record.levelno == logging.INFO:
                msg_lower = record.msg.lower() if isinstance(record.msg, str) else ""

                if "complete" in msg_lower or "success" in msg_lower:
                    record.icon = self.green
                elif "starting" in msg_lower:
                    record.icon = self.rocket
                elif "premium" in record.name.lower():
                    record.icon = self.diamond
                else:
                    record.icon = self.blue

            elif record.levelno == logging.WARNING:
                record.icon = self.orange

            elif record.levelno == logging.ERROR:
                record.icon = self.red

            else:
                record.icon = "📝"

        formatter = logging.Formatter(self.format_str, datefmt="%H:%M:%S")
        return formatter.format(record)


# Prevent duplicate handlers
if not logger.handlers:

    # Console handler (Cloud Run captures this automatically)
    c_handler = logging.StreamHandler(sys.stdout)
    c_handler.setLevel(logging.INFO)
    c_handler.setFormatter(CustomFormatter())
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

        file_format = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] - %(message)s'
        )

        f_handler.setFormatter(file_format)
        logger.addHandler(f_handler)


def get_logger(name: str):
    """Get child logger."""
    return logger.getChild(name)