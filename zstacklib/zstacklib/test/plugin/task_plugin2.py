from zstacklib.utils import plugin


class TaskPlugin2(plugin.Plugin):

    def __init__(self):
        super(TaskPlugin2, self).__init__()

    def cancel_fake_task(self):
        return self.cancel_task('fakeApiId')

    def start(self):
        pass

    def stop(self):
        pass
