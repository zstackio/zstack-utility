import time
import unittest

from plugin import task_plugin1
from plugin import task_plugin2
from zstacklib.test.utils import misc
from zstacklib.utils import jsonobject, plugin
from zstacklib.utils.misc import ignore_exception


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

    def test_plugin_task_cancel_after_exception(self):
        task_tame = "task-test-cancel-after-exception"
        plugin1 = task_plugin1.TaskPlugin1()
        plugin2 = task_plugin2.TaskPlugin2()
        plugin1.run_fake_task(task_tame, secs=2, timeout=1, run_exception=True)
        time.sleep(2)
        self.assertEqual(task_tame in task_plugin1.canceld, True)
        self.assertEqual(task_tame in task_plugin1.exception_catched, True)
        self.assertEqual(0, plugin2.cancel_fake_task())

    def test_plugin_task_resume(self):
        task_tame = "task-test-resume"
        task_spec = jsonobject.from_dict(misc.make_context_dict(task_tame, api_id="fakeApiId"), include_protected_attr=True)
        plugin1 = task_plugin1.TaskPlugin1()
        plugin2 = task_plugin2.TaskPlugin2()
        # test wait a running task
        plugin1.run_fake_task(task_tame, secs=3, timeout=10)
        time.sleep(1)
        ret = plugin2.wait_task(task_spec, task_tame)
        self.assertEqual(ret.success, True)

        # test wait a finished failure task
        plugin1.run_fake_task(task_tame, secs=2, timeout=1)
        time.sleep(2)
        ret = plugin2.wait_task(task_spec, task_tame)
        self.assertEqual(ret.success, False)

        # test wait a finished success task
        plugin1.run_fake_task(task_tame, secs=2, timeout=3)
        time.sleep(3)
        ret = plugin2.wait_task(task_spec, task_tame, no_task_return=lambda task_name, api_id:
                plugin.TaskResult())
        self.assertEqual(ret.success, True)

    def test_plugin_task_handle_exception(self):
        task_tame = "task-test-handle-exception"
        plugin1 = task_plugin1.TaskPlugin1()
        plugin1.run_fake_task(task_tame, secs=2, timeout=3, run_exception=True, ignore_exception=True)
        self.assertEqual(task_tame in task_plugin1.exception_catched, False)


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
