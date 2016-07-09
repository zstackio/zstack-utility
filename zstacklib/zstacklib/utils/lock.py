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
        if not os.path.exists(self.LOCK_DIR):
            os.makedirs(self.LOCK_DIR, 0755)
        
        self.lock_file_path = os.path.join(self.LOCK_DIR, '%s.lock' % lock_prefix)
        self.lock_file = open(self.lock_file_path, 'w')
    
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