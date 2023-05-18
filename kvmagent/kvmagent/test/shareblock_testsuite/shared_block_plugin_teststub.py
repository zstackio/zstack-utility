from kvmagent.test.utils import sharedblock_utils,pytest_utils,storage_device_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
from zstacklib.test.utils import misc,env
from unittest import TestCase


storage_device_utils.init_storagedevice_plugin()
class SharedBlockPluginTestStub(pytest_utils.PytestExtension):
    def __init__(self):
        pass

    def disconnect(self, vgUuid, hostUuid):
        return sharedblock_utils.shareblock_disconnect(vgUuid=vgUuid,hostUuid=hostUuid)

    def connect(self, sharedBlockUuids, allSharedBlockUuids, vgUuid, hostUuid, hostId, forceWipe=False):
        return sharedblock_utils.shareblock_connect(
            sharedBlockUuids=sharedBlockUuids,
            allSharedBlockUuids=allSharedBlockUuids,
            vgUuid=vgUuid,
            hostId=hostId,
            hostUuid=hostUuid,
            forceWipe=forceWipe
        )