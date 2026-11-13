from contextlib import ExitStack, contextmanager
from functools import partial

from kvmagent.crypto.http_error import log_failure


@contextmanager
def conversion_rollback(operation):
    cleanup = ExitStack()
    restore = ExitStack()
    failures = []

    def attempt(action, args, stage, resources):
        try:
            action(*args)
        except Exception as error:
            failures.append((stage, resources, error))

    def register(stack, stage, action, *args, **resources):
        stack.callback(attempt, action, args, stage, resources)

    try:
        yield partial(register, cleanup), partial(register, restore)
    except Exception:
        # Release published targets before restoring sources at the same path.
        cleanup.close()
        restore.close()
        if failures:
            unresolved = [(stage, resources, type(error).__name__) for stage, resources, error in failures]
            log_failure(operation, 'rollback_unresolved=%r' % unresolved, failures[0][2])
        raise
    else:
        cleanup.pop_all()
        restore.pop_all()
