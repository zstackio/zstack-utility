import threading
import time

from zstacklib.utils import linux
from zstacklib.utils import log

logger = log.get_logger(__name__)

class WatchThread_1(threading.Thread):
    def __init__(self, func):
        threading.Thread.__init__(self)
        self.func = func
        self.keepRunning = True

    def run(self):
        logger.debug("watch_thread_1: %s start" % self.__class__)
        try:
            synced = 0
            while self.keepRunning:
                synced = self.func(synced)
                time.sleep(1)
        except:
            logger.warning(linux.get_exception_stacktrace())

    def stop(self):
        self.keepRunning = False


def main():
    '''test'''

if __name__ == "__main__":
    main()

