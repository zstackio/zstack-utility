from kvmagent.test.utils import shareblock_utils,pytest_utils,storage_device_utils, vm_utils,ha_utils
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
class SharedBlockPluginTestStub(pytest_utils.PytestExtension):
    def __init__(self):
        pass

    def logout(self, vgUuid, hostUuid):
        rsp = shareblock_utils.shareblock_disconnect(
             vgUuid=vgUuid,
             hostUuid=hostUuid
        )

    def login(self):
        r, o = bash.bash_ro("ip -4 a| grep BROADCAST|grep -v virbr | awk -F ':' 'NR==1{print $2}' | sed 's/ //g'")
        interF = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        r, o = bash.bash_ro(
            "ip a show %s|grep inet|grep -v inet6|awk 'NR==1{print $2}'|awk -F '/' 'NR==1{print $1}' | sed 's/ //g'" % interF)
        interf_ip = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        # iqn
        r, o = bash.bash_ro("cat /etc/target/saveconfig.json|grep iqn|awk '{print $2}'")
        iqn = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')

        # login
        rsp = storage_device_utils.iscsi_login(
            interf_ip, "3260"
        )
        return rsp

    def connect(self, hostUuid, vgUuid):
        # get block uuid
        r, o = bash.bash_ro("ls /dev/disk/by-id | grep scsi|awk -F '-' '{print $2}'")
        blockUuid = o.strip().replace(' ', '').replace('\n', '').replace('\r', '')
        rsp = shareblock_utils.shareblock_connect(
            sharedBlockUuids=[blockUuid],
            allSharedBlockUuids=[blockUuid],
            vgUuid=vgUuid,
            hostId=50,
            hostUuid=hostUuid
        )
        return rsp, blockUuid
