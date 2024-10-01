import os
import coverage
from zstacklib.test.utils import env
from zstacklib.utils import debug

Out_flag = True

debug.install_runtime_tracedumper()
class PytestExtension(object):

    cov = None

    @staticmethod
    def start_coverage():
        if not env.COVERAGE:
            return

        PytestExtension.cov = coverage.Coverage(config_file=os.path.join(env.ZSTACK_UTILITY_SOURCE_DIR, '.coveragerc'))
        PytestExtension.cov.start()

    @staticmethod
    def stop_coverage():
        if not env.COVERAGE:
            return

        PytestExtension.cov.stop()
        PytestExtension.cov.save()

    def setup_class(self):
        self.start_coverage()

    def teardown_class(self):
        self.stop_coverage()

        if Out_flag:
            os._exit(0)

        os._exit(1)


def ztest_decorater(func):
    def wrapper(*args, **kwargs):
        global Out_flag
        last_out_flag = Out_flag
        Out_flag = False
        func(*args, **kwargs)
        Out_flag = last_out_flag

    return wrapper
