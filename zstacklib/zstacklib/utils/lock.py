'''

@author: Frank
'''

import weakref
import threading
import functools
import time
import log
import os
import fcntl
import errno

_internal_lock = threading.RLock()
_locks = weakref.WeakValueDictionary()

logger = log.get_logger(__name__)

_LOCK_TIMEOUT = int(os.environ.get('KVMAGENT_LOCK_TIMEOUT', 1800))
_FILE_LOCK_TIMEOUT = int(os.environ.get('KVMAGENT_FILE_LOCK_TIMEOUT', 1800))


class LockTimeoutError(Exception):
    '''lock acquire timeout'''

def _get_lock(name):
    with _internal_lock:
        lock = _locks.get(name, threading.RLock())
        if not name in _locks:
            _locks[name] = lock
        return lock

class NamedLock(object):
    def __init__(self, name, acquire_timeout=None):
        self.name = name
        self.lock = None
        self.acquire_timeout = acquire_timeout if acquire_timeout is not None else _LOCK_TIMEOUT

    def __enter__(self):
        self.lock = _get_lock(self.name)
        # acquire_timeout == 0 means infinite wait (no deadline)
        if self.acquire_timeout == 0:
            self.lock.acquire(True)
            return
        deadline = time.time() + self.acquire_timeout
        while not self.lock.acquire(False):
            if time.time() >= deadline:
                raise LockTimeoutError(
                    'failed to acquire lock [%s] within %ss, '
                    'possible deadlock or hung thread holding the lock'
                    % (self.name, self.acquire_timeout))
            time.sleep(0.2)

    def __exit__(self, type, value, traceback):
        self.lock.release()


def lock(name='defaultLock', acquire_timeout=None):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            with NamedLock(name, acquire_timeout):
                retval = f(*args, **kwargs)
            return retval
        return inner
    return wrap


class Locker(object):
    def lock(self, lock_file):
        raise Exception('function lock not be implemented')

    def unlock(self, lock_file):
        raise Exception('function unlock not be implemented')


class Flock(Locker):
    def lock(self, lock_file, acquire_timeout=None):
        if acquire_timeout is None:
            acquire_timeout = _FILE_LOCK_TIMEOUT
        if acquire_timeout == 0:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            return
        deadline = time.time() + acquire_timeout
        while True:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except IOError as e:
                if e.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if time.time() >= deadline:
                    raise LockTimeoutError(
                        'failed to acquire flock within %ss' % acquire_timeout)
                time.sleep(0.5)

    def unlock(self, lock_file):
        fcntl.flock(lock_file, fcntl.LOCK_UN)


class Lockf(Locker):
    def lock(self, lock_file, acquire_timeout=None):
        if acquire_timeout is None:
            acquire_timeout = _FILE_LOCK_TIMEOUT
        if acquire_timeout == 0:
            fcntl.lockf(lock_file, fcntl.LOCK_EX)
            return
        deadline = time.time() + acquire_timeout
        while True:
            try:
                fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except IOError as e:
                if e.errno not in (errno.EACCES, errno.EAGAIN):
                    raise
                if time.time() >= deadline:
                    raise LockTimeoutError(
                        'failed to acquire lockf within %ss' % acquire_timeout)
                time.sleep(0.5)

    def unlock(self, lock_file):
        fcntl.lockf(lock_file, fcntl.LOCK_UN)


# NOTE(weiw): caller should manually clean up lock file if not need anymore
def file_lock(name, locker=Lockf(), debug=False):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            with NamedLock(name):
                if debug:
                    logger.debug("entering named lock %s with function %s.%s" % (name, f.__module__, f.__name__))
                with FileLock(name, locker):
                    retval = f(*args, **kwargs)
                if debug:
                    logger.debug("exit named lock %s with function %s.%s" % (name, f.__module__, f.__name__))
            return retval
        return inner
    return wrap

class FileLock(object):
    LOCK_DIR = '/var/lib/zstack/lock/'

    def __init__(self, lock_prefix, locker=Lockf()):
        def _prepare_lock_file(dname, fname):
            if not os.path.exists(dname):
                os.makedirs(dname, 0755)

            lock_file_path = os.path.join(dname, fname)
            self.lock_file = open(lock_file_path, 'w')
            os.chmod(lock_file_path, 0o600)

        self.locker = locker
        if os.path.isabs(lock_prefix):
            _prepare_lock_file(os.path.dirname(lock_prefix), os.path.basename(lock_prefix))
        else:
            _prepare_lock_file(self.LOCK_DIR, '%s.lock' % lock_prefix)

    def lock(self):
        self.locker.lock(self.lock_file)

    def unlock(self):
        try:
            self.locker.unlock(self.lock_file)
        finally:
            self.lock_file.close()

    def __enter__(self):
        self.lock()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unlock()
