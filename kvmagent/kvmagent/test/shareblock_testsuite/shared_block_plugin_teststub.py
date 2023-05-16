from kvmagent.test.utils import shareblock_utils,pytest_utils,storage_device_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
from zstacklib.test.utils import misc,env
from unittest import TestCase

shareblock_utils.init_shareblock_plugin()
storage_device_utils.init_storagedevice_plugin()
class SharedBlockPluginTestStub(pytest_utils.PytestExtension):
    def __init__():
        pass

    def logout(self, vgUuid, hostUuid):
        rsp = shareblock_utils.shareblock_disconnect(
             vgUuid=vgUuid,
             hostUuid=hostUuid
        )