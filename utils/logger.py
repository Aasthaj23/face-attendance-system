import logging
import os


_LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(levelname)-8s %(name)s %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
