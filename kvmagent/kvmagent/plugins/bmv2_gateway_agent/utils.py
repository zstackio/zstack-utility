import os
import shutil
import time

from zstacklib.utils import log


logger = log.get_logger(__name__)

class rollback(object):
    """ A tool class for rollback operation using context, not try.catch
    """

    def __init__(self, func, *args, **kwargs):
        self.rollback_func = func
        self.rollback_args = args
        self.rollback_kwargs = kwargs

    def __enter__(self):
        return

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback_func(*self.rollback_args, **self.rollback_kwargs)
            return False
        return


class transcantion(object):
    """ A tool class for retry
    """

    def __init__(self, retries, sleep_time=0):
        self.retries = retries
        self.sleep_time = sleep_time

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        return True

    def execute(self, func, *args, **kwargs):
        err = None
        for i in range(self.retries):
            try:
                msg = 'Attempt run {name}: {i}'.format(
                    name=func.__name__, i=i)
                logger.info(msg)
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(e)
                err = e
            time.sleep(self.sleep_time)
        raise err


def copy_dir_files_to_another_dir(src, dst):
    for item in os.listdir(src):
        src_file = os.path.join(src, item)
        dst_file = os.path.join(dst, item)
        shutil.copy(src_file, dst_file)
