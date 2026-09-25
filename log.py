import logging
from threading import Lock

_LOCK = Lock()


def configure(level="INFO"):
    """Configure the Aster logger once, while allowing its level to change."""
    logger = logging.getLogger("aster")
    numeric_level = getattr(logging, str(level).upper(), logging.INFO)
    with _LOCK:
        logger.setLevel(numeric_level)
        logger.propagate = False
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            logger.addHandler(handler)
    return logger


def _logger():
    logger = logging.getLogger("aster")
    if not logger.handlers:
        configure()
    return logger


def error(msg, *args):
    _logger().error(msg, *args)


def info(msg, *args):
    _logger().info(msg, *args)
