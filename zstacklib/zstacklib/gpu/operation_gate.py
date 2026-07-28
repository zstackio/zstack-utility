# -*- coding: utf-8 -*-

import threading
from contextlib import contextmanager

try:
    import _thread as thread
except ImportError:
    import thread


class GPUOperationGate(object):
    def __init__(self):
        self._condition = threading.Condition(threading.Lock())
        self._owner = None
        self._critical_depth = 0
        self._critical_waiters = 0

    def acquire_critical(self):
        owner = thread.get_ident()
        with self._condition:
            if self._owner == owner:
                if self._critical_depth == 0:
                    raise RuntimeError('cannot upgrade a monitoring GPU operation')
                self._critical_depth += 1
                return

            self._critical_waiters += 1
            try:
                while self._owner is not None:
                    self._condition.wait()
                self._owner = owner
                self._critical_depth = 1
            finally:
                self._critical_waiters -= 1

    def try_acquire_monitoring(self):
        owner = thread.get_ident()
        with self._condition:
            if self._owner is not None or self._critical_waiters:
                return False
            self._owner = owner
            self._critical_depth = 0
            return True

    def release(self):
        owner = thread.get_ident()
        with self._condition:
            if self._owner != owner:
                raise RuntimeError('GPU operation gate released by non-owner')

            if self._critical_depth > 1:
                self._critical_depth -= 1
                return

            self._owner = None
            self._critical_depth = 0
            self._condition.notify_all()

    @contextmanager
    def critical(self):
        self.acquire_critical()
        try:
            yield
        finally:
            self.release()

    @contextmanager
    def monitoring(self):
        acquired = self.try_acquire_monitoring()
        try:
            yield acquired
        finally:
            if acquired:
                self.release()


gpu_operation_gate = GPUOperationGate()
