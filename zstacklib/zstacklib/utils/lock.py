'''

@author: Frank
'''

import weakref
import threading
import functools
import log
import os
import fcntl
#import typing

_internal_lock = threading.RLock()
_locks = weakref.WeakValueDictionary()

logger = log.get_logger(__name__)

def _get_lock(name):
    with _internal_lock:
        lock = _locks.get(name, threading.RLock())
        if not name in _locks:
            _locks[name] = lock
        return lock

class NamedLock(object):
    def __init__(self, name):
        self.name = name
        self.lock = None

    def __enter__(self):
        self.lock = _get_lock(self.name)
        self.lock.acquire()
        #logger.debug('%s got lock %s' % (threading.current_thread().name, self.name))

    def __exit__(self, type, value, traceback):
        self.lock.release()
        #logger.debug('%s released lock %s' % (threading.current_thread().name, self.name))


def lock(name='defaultLock'):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            with NamedLock(name):
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
    def lock(self, lock_file):
        fcntl.flock(lock_file, fcntl.LOCK_EX)

    def unlock(self, lock_file):
        fcntl.flock(lock_file, fcntl.LOCK_UN)


class Lockf(Locker):
    def lock(self, lock_file):
        fcntl.lockf(lock_file, fcntl.LOCK_EX)

    def unlock(self, lock_file):
        fcntl.lockf(lock_file, fcntl.LOCK_UN)


# NOTE(weiw): caller should manually clean up lock file if not need anymore
def file_lock(name, locker=Lockf(), debug=True):
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
