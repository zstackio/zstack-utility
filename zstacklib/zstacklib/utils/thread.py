'''

@author: frank
'''

import threading
import inspect
import pprint
import traceback
import log
import functools

logger = log.get_logger(__name__)

class AsyncThread(object):
    def __init__(self, func):
        self.func = func
        
    def __get__(self, obj, type=None):
        return self.__class__(self.func.__get__(obj, type))
    
    def __call__(self, *args, **kw):
        return ThreadFacade.run_in_thread(self.func, args=args, kwargs=kw)

class ThreadFacade(object):
    @staticmethod
    def run_in_thread(target, args=(), kwargs={}):
        def safe_run(*sargs, **skwargs):
            try:
                target(*sargs, **skwargs)
            except Exception as e:
                content = traceback.format_exc()
                err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
                logger.warn(err)
                
        t = threading.Thread(target=safe_run, name=target.__name__, args=args, kwargs=kwargs)
        t.start()
        return t

class PeriodicTimer(object):
    def __init__(self, interval, callback, args=[], kwargs={}, stop_on_exception=True):
        self.interval = interval
        self.args = args
        self.kwargs = kwargs
        self.stop_on_exception = stop_on_exception

        @functools.wraps(callback)
        def wrapper(*args, **kwargs):
            result = not self.stop_on_exception
            try:
                result = callback(*args, **kwargs)
            except Exception as e:
                content = traceback.format_exc()
                err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
                logger.warn(err)
                logger.warn('this timer thread will be terminated immediately due to the exception')
                
            if result:
                self.thread = threading.Timer(self.interval, self.callback, self.args, self.kwargs)
                self.thread.start()

        self.callback = wrapper

    @AsyncThread
    def start(self):
        self.thread = threading.Timer(self.interval, self.callback, self.args, self.kwargs)
        self.thread.start()

    def cancel(self):
        self.thread.cancel()

    def is_alive(self):
        return self.thread.is_alive()
        
def timer(interval, function, args=[], kwargs={}, stop_on_exception=True):
    return PeriodicTimer(interval, function, args, kwargs, stop_on_exception)

class AtomicInteger(object):
    def __init__(self, value=0):
        self._value = value
        self._lock = threading.Lock()

    def inc(self):
        with self._lock:
            self._value += 1
            return self._value

    def dec(self):
        with self._lock:
            self._value -= 1
            return self._value

    def get(self):
        with self._lock:
            return self._value
