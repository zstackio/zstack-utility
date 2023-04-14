from kvmagent.test.utils import shareblock_utils,pytest_utils,storage_device_utils, vm_utils, nfs_plugin_utils, ha_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import remote
from zstacklib.utils import linux, jsonobject, bash
from zstacklib.test.utils import misc,env
from unittest import TestCase

init_kvmagent()
shareblock_utils.init_shareblock_plugin()
storage_device_utils.init_storagedevice_plugin()
vm_utils.init_vm_plugin()
nfs_plugin_utils.init_nfs_plugin()
ha_utils.init_ha_plugin()

class NfsPluginTestStub(pytest_utils.PytestExtension):
    def __init__(self):
        pass

    def mount(self, primaryStorageUuid):
        r, o = bash.bash_ro("ip -4 a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        r, o = bash.bash_ro(
            "ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}'|awk -F '/' 'NR==1{print $1}' | sed 's/ //g'" % interF)
        interf_ip = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        url = "{}:/nfs_root/".format(interf_ip)
        path = "/opt/zstack/nfsprimarystorage/prim-{}".format(primaryStorageUuid)
        nfs_plugin_utils.mount(url, path, None, primaryStorageUuid)

        return url




