from kvmagent.plugins import host_plugin
from unittest import TestCase
import subprocess
import mock
from zstacklib.utils import jsonobject
from zstacklib.utils import shell
import zstacklib.utils.log as log

logger = log.get_logger(__name__)

class TestHostFacts(TestCase):
    """
    Test case for host facts.
    """

    @mock.patch('zstacklib.utils.shell.call')
    def test(self, mock_call):
        host = host_plugin.HostPlugin()
        host.configure()

        dmidecode_output = "test dmidecode output"
        # mock shell.call
        def mock_shell_call(cmd, *args, **kwargs):
            if 'dmidecode' in cmd:
                return dmidecode_output
            elif 'qemu-img' in cmd:
                return "6.2.0"
            elif 'model name|cpu MHz' in cmd:
                return "model name\t: Intel(R) Xeon(R) CPU E5-2620 v4 @ 2.10GHz\n2100.000"
            elif 'per core' in cmd:
                return "2" 
            elif 'per socket' in cmd:
                return "2"
            elif 'per cluster' in cmd:
                return "2"
            else:
                return "not implemented"

        mock_call.side_effect = mock_shell_call

        rsp_json_str = host.fact(None)
        rsp = jsonobject.loads(rsp_json_str)

        # test dmidecode's output
        self.assertNotEqual(rsp.systemSerialNumber, 'unknown')

        # change to error chars
        error_char = open('kvmagent/test/host_testsuite/mock_error_chars', 'r').read()
        dmidecode_output = error_char

        shell.call('dmidecode -s system-product-name').strip()
        logger.debug(shell.call('dmidecode -s system-product-name').strip())

        rsp_json_str = host.fact(None)
        rsp = jsonobject.loads(rsp_json_str)
        self.assertEqual(rsp.systemSerialNumber, "unknown")

