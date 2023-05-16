from kvmagent.test.utils import pytest_utils,storage_device_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
from zstacklib.test.utils import misc,env
from unittest import TestCase

storage_device_utils.init_storagedevice_plugin()
class StorageDevicePluginTestStub(pytest_utils.PytestExtension):
    def __init__():
        pass

    def logout(self, iscsiServerIp, iscsiServerPort):
        rsp = storage_device_utils.iscsi_logout(
             iscsiServerIp=iscsiServerIp,
             iscsiServerPort=iscsiServerPort
        )