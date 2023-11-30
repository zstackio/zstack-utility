import os
import coverage
import mock

from zstacklib.test.utils import env
from zstacklib.utils import debug
from kvmagent.plugins.imagestore import ImageStoreClient

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

    @staticmethod
    def setup_modules_mock():
        modules_to_mock = {
            ImageStoreClient: {
                'stop_mirror': None,
                'query_mirror_volumes': None,
                'mirror_volume': None,
            }
        }

        for k, v in modules_to_mock.items():
            for m, r in v.items():
                p = mock.patch.object(k, m, return_value=r)
                p.start()


    def setup_class(self):
        self.start_coverage()
        self.setup_modules_mock()

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
