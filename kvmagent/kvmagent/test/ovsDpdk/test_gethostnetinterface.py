from kvmagent.plugins import host_plugin
from zstacklib.utils import jsonobject
from unittest import TestCase

import time
import pytest

class Test():

    @classmethod
    def setup_class(self):
        self.HOST_PLUGIN = host_plugin.HostPlugin()

    def test_getSmartNicWhenOfedNotInstall(self):
        response_json = self.HOST_PLUGIN.get_host_network_facts(None)
        print("get_host_network_facts() rsp: %s" % (response_json))
        hasSmartNic = "offloadStatus" in response_json
        assert hasSmartNic == True
