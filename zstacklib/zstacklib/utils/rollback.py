__author__ = 'frank'

import threading
import functools
import traceback
import log

logger = log.get_logger(__name__)

tlocal = threading.local()
tlocal.rollback_structs = []

def rollbackable(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        if not hasattr(tlocal, 'rollback_structs'):
            tlocal.rollback_structs = []
        tlocal.rollback_structs.append((func, args, kwargs))

    return wrap

def rollback(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if not hasattr(tlocal, 'rollback_structs'):
                raise e

            tlocal.rollback_structs.reverse()

            for (f, fargs, fkwargs) in tlocal.rollback_structs:
                try:
                    f(*fargs, **fkwargs)
                except:
                    content = traceback.format_exc()
                    logger.warn(content)

            tlocal.rollback_structs = []

            raise e

    return wrap
