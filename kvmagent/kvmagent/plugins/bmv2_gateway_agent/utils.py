import functools
import os
import shutil
import threading
import time

from zstacklib.utils import linux
from zstacklib.utils import log

from kvmagent.plugins.bmv2_gateway_agent import exception


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


_internal_lock = threading.Lock()


_locks = {}


def get_lock(name, timeout):
    @linux.retry(times=timeout, sleep_time=1)
    def _get_lock():
        with _internal_lock:
            lockinfo = _locks.get(name)

            if not lockinfo:
                l = threading.Lock()
                _locks[name] = {
                    'lock': l,
                    'acquire_time': time.time(),
                    'timeout': timeout,
                    'thread': threading.current_thread().ident}
                return l

            l = lockinfo['lock']
            if l.locked():
                if lockinfo['acquire_time'] + lockinfo['timeout'] > \
                        time.time():
                    raise exception.LockNotRelease(
                        name=name,
                        thread=lockinfo['thread'],
                        time=lockinfo['acquire_time'],
                        timeout=lockinfo['timeout'])
                logger.info('Release the timeout lock: {name}, locked by: '
                            '{lock_t}, released by: '
                            '{release_t}'.format(
                                name=name,
                                lock_t=lockinfo['thread'],
                                release_t=threading.current_thread().ident))
                l.release()
            return l

    return _get_lock()


class NamedLock(object):
    def __init__(self, name, timeout=120):
        self.name = name
        self.timeout = timeout
        self.lock = None

    def __enter__(self):
        self.lock = get_lock(self.name, self.timeout)
        self.lock.acquire()
        lockinfo = {
            'lock': self.lock,
            'acquire_time': time.time(),
            'timeout': self.timeout,
            'thread': threading.current_thread().ident}
        _locks[self.name] = lockinfo
        logger.debug('Acquire lock {name} in thread {thread}'.format(
            name=self.name, thread=threading.current_thread().ident))

    def __exit__(self, type, value, trackback):
        try:
            self.lock.release()
        except Exception as e:
            # The lock was released, therefore log it only
            logger.warn(e)
        finally:
            logger.debug('Relese lock {name} in thread {thread}'.format(
              name=self.name, thread=threading.current_thread().ident))


def lock(name='default_lock', timeout=120):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            with NamedLock(name, timeout):
                ret = f(*args, **kwargs)
            return ret
        return inner
    return wrap


def copy_dir_files_to_another_dir(src, dst):
    for item in os.listdir(src):
        src_file = os.path.join(src, item)
        dst_file = os.path.join(dst, item)
        shutil.copy(src_file, dst_file)


def flush_dir(dir_path):
    if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
        return

    for f in os.listdir(dir_path):
        os.remove(os.path.join(dir_path, f))
