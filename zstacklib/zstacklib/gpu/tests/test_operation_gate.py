# -*- coding: utf-8 -*-

import threading
import time
import unittest

from zstacklib.gpu.operation_gate import GPUOperationGate


class TestGPUOperationGate(unittest.TestCase):
    def test_monitoring_is_rejected_while_critical_operation_is_active(self):
        gate = GPUOperationGate()
        critical_entered = threading.Event()
        release_critical = threading.Event()

        def run_critical():
            with gate.critical():
                critical_entered.set()
                release_critical.wait(1)

        thread = threading.Thread(target=run_critical)
        thread.start()
        self.assertTrue(critical_entered.wait(1))

        with gate.monitoring() as acquired:
            self.assertFalse(acquired)

        release_critical.set()
        thread.join(1)
        self.assertFalse(thread.is_alive())

    def test_waiting_critical_operation_prevents_new_monitoring(self):
        gate = GPUOperationGate()
        critical_entered = threading.Event()

        with gate.monitoring() as first_monitoring:
            self.assertTrue(first_monitoring)

            def run_critical():
                with gate.critical():
                    critical_entered.set()

            thread = threading.Thread(target=run_critical)
            thread.start()
            self._wait_for_critical_waiter(gate)

            with gate.monitoring() as second_monitoring:
                self.assertFalse(second_monitoring)

        self.assertTrue(critical_entered.wait(1))
        thread.join(1)
        self.assertFalse(thread.is_alive())

    def test_context_releases_gate_after_exception(self):
        gate = GPUOperationGate()

        with self.assertRaises(RuntimeError):
            with gate.critical():
                raise RuntimeError('failed GPU operation')

        with gate.monitoring() as acquired:
            self.assertTrue(acquired)

    def test_critical_operation_is_reentrant(self):
        gate = GPUOperationGate()

        with gate.critical():
            with gate.critical():
                with gate.monitoring() as acquired:
                    self.assertFalse(acquired)

        with gate.monitoring() as acquired:
            self.assertTrue(acquired)

    @staticmethod
    def _wait_for_critical_waiter(gate):
        deadline = time.time() + 1
        while time.time() < deadline:
            with gate._condition:
                if gate._critical_waiters:
                    return
            time.sleep(0.001)
        raise AssertionError('critical operation did not start waiting')


if __name__ == '__main__':
    unittest.main()
