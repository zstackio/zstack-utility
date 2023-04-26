import os
import coverage
from zstacklib.test.utils import env

Out_flag = True


class PytestExtension(object):

    cov = None

    @staticmethod
    def start_coverage():
        if not env.COVERAGE:
            return

        PytestExtension.cov = coverage.Coverage()
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
