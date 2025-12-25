import logging
import sys
import os


def setup_logging():
    env = os.getenv("ENV", "development")
    if env == "production":
        log_level = logging.INFO
    else:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
