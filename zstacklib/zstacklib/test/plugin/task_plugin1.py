from zstacklib.utils import plugin
from zstacklib.utils import jsonobject
from zstacklib.utils.thread import AsyncThread
import time

canceld = set()
exception_catched = set()


class TaskPlugin1(plugin.Plugin):
    def __init__(self):
        super(TaskPlugin1, self).__init__()
        self.progress_count = 0

    @AsyncThread
    def run_fake_task(self, task_name, secs, timeout, report_progress=False, run_exception=False):
        cmd = jsonobject.loads('{"threadContext":{"api":"fakeApiId"}}')

        class FakeTaskDaemon(plugin.TaskDaemon):
            def __init__(self):
                super(FakeTaskDaemon, self).__init__(cmd, task_name, timeout=timeout, report_progress=report_progress)
                self.percent = 0

            def _get_percent(self):
                self.percent = self.percent + 1
                print 'percent' + str(self.percent)

            def _cancel(self):
                canceld.add(self.task_name)
                print self.task_name + ' canceled'
                # no need to call close() in real env. cancel func need to focus only on its own task,
                # and canceled task is supposed to end immediately,
                # then close() will be called automatically in __exit__.
                # calling it here is to mock task ending because it is not easy to end sleep.
                self.close()
        try:
            with FakeTaskDaemon() as daemon:
                if run_exception:
                    raise Exception("")
                time.sleep(secs)
                self.progress_count = daemon.percent
        except:
            exception_catched.add(task_name)

    def start(self):
        pass

    def stop(self):
        pass
