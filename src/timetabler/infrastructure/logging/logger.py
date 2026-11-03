import atexit
import logging.config
import pathlib
from logging import Handler
from logging.handlers import QueueHandler, QueueListener

import orjson

logger = logging.getLogger("main")


def setup_logging(path_to_config: str) -> None:
    config_file = pathlib.Path(path_to_config)
    with open(config_file, "rb") as f_in:
        config = orjson.loads(f_in.read())

    logging.config.dictConfig(config)
    queue_handler: Handler | None = logging.getHandlerByName("queue_handler")
    if isinstance(queue_handler, QueueHandler):
        assert isinstance(queue_handler.listener, QueueListener)
        queue_handler.listener.start()
        atexit.register(queue_handler.listener.stop)
