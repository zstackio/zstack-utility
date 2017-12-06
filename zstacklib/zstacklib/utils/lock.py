'''

@author: Frank
'''

import weakref
import threading
import functools
import log
import os
import fcntl

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

def file_lock(name):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            with NamedLock(name):
                with FileLock(name):
                    retval = f(*args, **kwargs)
            return retval
        return inner
    return wrap

class FileLock(object):
    LOCK_DIR = '/var/lib/zstack/lock/'
    
    def __init__(self, lock_prefix):
        def _prepare_lock_file(dname, fname):
            if not os.path.exists(dname):
                os.makedirs(dname, 0755)

            lock_file_path = os.path.join(dname, fname)
            self.lock_file = open(lock_file_path, 'w')
            os.chmod(lock_file_path, 0o600)

        if os.path.isabs(lock_prefix):
            _prepare_lock_file(os.path.dirname(lock_prefix), os.path.basename(lock_prefix))
        else:
            _prepare_lock_file(self.LOCK_DIR, '%s.lock' % lock_prefix)
    
    def lock(self):
        fcntl.lockf(self.lock_file, fcntl.LOCK_EX)
        
    def unlock(self):
        try:
            fcntl.lockf(self.lock_file, fcntl.LOCK_UN)
        finally:
            self.lock_file.close()
        
    def __enter__(self):
        self.lock()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unlock()
