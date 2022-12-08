import functools
def checkParamNotNone(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        if args is None:
            raise ValueError("Missing argument")
        return func(*args, **kwargs)
    return wrap