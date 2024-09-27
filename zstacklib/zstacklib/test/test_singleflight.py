import unittest
import threading
import time

from zstacklib.utils.singleflight import Group


class TestSingleflight(unittest.TestCase):
    def setUp(self):
        self.stf = Group()

    def test_single_call(self):
        def fn():
            return "result"

        result = self.stf.do("key", fn)
        self.assertEqual(result.value, "result")
        self.assertIsNone(result.error)
        self.assertFalse(result.shared)

    def test_concurrent_calls(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            time.sleep(1)
            return time.time()

        results = []

        def worker():
            result = self.stf.do("key", fn)
            results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(call_count[0], 1)
        self.assertEqual(len(set(r.value for r in results)), 1)
        self.assertTrue(all(r.error is None for r in results))

    def test_error_handling(self):
        def fn():
            raise ValueError("Test error")

        result = self.stf.do("key", fn)
        self.assertIsNone(result.value)
        self.assertIsInstance(result.error, ValueError)
        self.assertEqual(str(result.error), "Test error")
        self.assertFalse(result.shared)

    def test_concurrent_calls_with_error(self):
        call_count = [0]

        def fn():
            call_count[0] += 1
            time.sleep(1)
            raise ValueError("Test error")

        results = []

        def worker():
            result = self.stf.do("key", fn)
            results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(call_count[0], 1)
        self.assertEqual(len(results), 5)
        self.assertTrue(all(r.value is None for r in results))
        self.assertTrue(all(isinstance(r.error, ValueError) for r in results))
        self.assertTrue(all(str(r.error) == "Test error" for r in results))


if __name__ == '__main__':
    unittest.main()
