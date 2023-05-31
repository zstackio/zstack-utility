import time
import unittest

from plugin import task_plugin1
from plugin import task_plugin2


class TestTaskManager(unittest.TestCase):
    def test_plugin_cancel_task(self):
        plugin1 = task_plugin1.TaskPlugin1()
        plugin2 = task_plugin2.TaskPlugin2()

        for i in range(4):
            plugin1.run_fake_task('fake task' + str(i), secs=2, timeout=3)
        time.sleep(1)
        self.assertEqual(4, plugin2.cancel_fake_task())
        self.assertEqual(0, plugin2.cancel_fake_task())

    def test_plugin_task_timeout(self):
        plugin1 = task_plugin1.TaskPlugin1()
        plugin2 = task_plugin2.TaskPlugin2()
        plugin1.run_fake_task('other fake task', secs=2, timeout=1)
        time.sleep(2)
        self.assertEqual(0, plugin2.cancel_fake_task())
        time.sleep(1)
        self.assertEqual(1, plugin1.progress_count)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
