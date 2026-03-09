import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Define the log directory in the parent folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")

if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Generate log filename based on current date
log_filename = f"app_{datetime.now().strftime('%Y-%m-%d')}.log"
log_path = os.path.join(LOG_DIR, log_filename)

# Create a custom logger
logger = logging.getLogger("AI-Microservices")
logger.setLevel(logging.DEBUG)

# Create handlers
c_handler = logging.StreamHandler(sys.stdout)
f_handler = RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
c_handler.setLevel(logging.INFO)
f_handler.setLevel(logging.DEBUG)

# Create formatters and add it to handlers
class CustomFormatter(logging.Formatter):
    """Custom formatter for consistent, premium-looking console logs."""
    
    blue = "🔵"
    green = "✅"
    orange = "🟠"
    red = "🔴"
    diamond = "💎"
    rocket = "🚀"
    reset = ""

    format_str = "[%(asctime)s] %(icon)s %(message)s"

    def format(self, record):
        # Set icon based on message content or level
        if not hasattr(record, "icon"):
            if record.levelno == logging.INFO:
                msg_lower = record.msg.lower() if isinstance(record.msg, str) else ""
                if "complete" in msg_lower or "success" in msg_lower or "✅" in msg_lower:
                    record.icon = self.green
                elif "starting" in msg_lower or "🚀" in msg_lower:
                    record.icon = self.rocket
                elif "💎" in msg_lower or "premium" in record.name.lower():
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

# File format includes level name and more detail
file_format = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] - %(message)s')

c_handler.setFormatter(CustomFormatter())
f_handler.setFormatter(file_format)

# Add handlers to the logger
if not logger.handlers:
    logger.addHandler(c_handler)
    logger.addHandler(f_handler)

def get_logger(name: str):
    """Get a child logger with the given name."""
    return logger.getChild(name)
