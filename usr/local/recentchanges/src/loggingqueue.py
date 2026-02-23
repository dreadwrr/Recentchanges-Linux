import logging
from queue import Queue


class LoggingQueue(Queue):
    def __init__(self, logger=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = logger if logger else logging

    def put(self, item, block=True, timeout=None):

        super().put(item, block, timeout)

        if item is not None:
            level, message = item
            lvl = level.upper()

            log_levels = {
                'ERROR': self.logger.error,
                'DEBUG': self.logger.debug,
                'INFO': self.logger.info,
                'WARNING': self.logger.warning,
            }
            log_func = log_levels.get(lvl)
            if log_func:
                log_func(message)
            elif lvl == 'STOP':
                pass
            else:
                self.logger.warning("Unknown log level: %s - %s", lvl, message)
