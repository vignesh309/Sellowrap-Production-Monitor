import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler


class _LoggerStream:
    def __init__(self, logger, level):
        self.logger = logger
        self.level = level
        self.buffer = ""

    def write(self, message):
        self.buffer += message
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line:
                self.logger.log(self.level, line.rstrip("\r"))
        return len(message)

    def flush(self):
        if self.buffer:
            self.logger.log(self.level, self.buffer.rstrip("\r"))
            self.buffer = ""

    def isatty(self):
        return False


def configure_service_logging(log_name):
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(log_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Create a shared formatter
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")

    # 1. File Handler (Saves output to the /logs/ folder)
    file_handler = TimedRotatingFileHandler(
        os.path.join(log_dir, f"{log_name}.log"),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 2. Console Handler (Prints output to the CMD window)
    # 🚨 Using sys.__stdout__ bypasses our custom _LoggerStream to prevent infinite loops
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Redirect standard output and errors into our logger
    sys.stdout = _LoggerStream(logger, logging.INFO)
    sys.stderr = _LoggerStream(logger, logging.ERROR)