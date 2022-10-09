import os
import signal


class PytestExtension(object):

    def setup_class(self):
        pass

    def teardown_class(self):
        os.kill(os.getpid(), signal.SIGKILL)
