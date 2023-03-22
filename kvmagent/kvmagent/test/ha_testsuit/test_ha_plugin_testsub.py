from kvmagent.test.utils import shareblock_utils,pytest_utils,storage_device_utils, vm_utils, ha_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
from zstacklib.test.utils import misc,env
from unittest import TestCase

init_kvmagent()
shareblock_utils.init_shareblock_plugin()
storage_device_utils.init_storagedevice_plugin()
vm_utils.init_vm_plugin()
ha_utils.init_ha_plugin()

class HaPluginTestStub(pytest_utils.PytestExtension):
    def __init__(self):
        pass
