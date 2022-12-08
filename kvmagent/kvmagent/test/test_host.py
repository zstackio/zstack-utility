from kvmagent.test.utils import pytest_utils
from zstacklib.test.utils import misc
from kvmagent.test.utils.stub import *

from kvmagent.plugins import host_plugin

init_kvmagent()

__ENV_SETUP__ = {
    'self': {}
}


class TestHost(TestCase, pytest_utils.PytestExtension):
    @misc.test_for(handlers=[
        host_plugin.HostPlugin.CONNECT_PATH
    ])
    @pytest_utils.ztest_decorater
    def test_connect(self):
        uuid = misc.uuid()
        body = {
            'hostUuid': uuid,
            'iptablesRules': [],
            'ignoreMsrs': False,
            'pageTableExtensionDisabled': False,
            'version': '4.0'
        }

        host = host_plugin.HostPlugin()
        host.configure()
        host.start()
        host.connect(misc.make_a_request(body))
