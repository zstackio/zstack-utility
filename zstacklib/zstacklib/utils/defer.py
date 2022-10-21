import functools
import threading
import traceback

_local = threading.local()
_local.defer_stack = []


def defer(f):
    try:
        lst = _local.defer_stack[-1]
        lst.append(f)
    except IndexError as e:
        raise AttributeError('the function calling defer() must decorated by @defer.protect, %s' % str(e))


def protect(f):
    @functools.wraps(f)
    def inner(*args, **kwargs):

        _local.defer_stack.append([])

        try:
            return f(*args, **kwargs)
        finally:
            lst = _local.defer_stack.pop()
            for df in lst:
                try:
                    df()
                except Exception:
                    print('unhandled defer error:\n%s\n' % traceback.format_exc())

    return inner
