'''

@author: Frank
'''
import unittest

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin

class Test(unittest.TestCase):


    def testName(self):
        cmd = vm_plugin.StartVmCmd()
        cmd.bootDev = 'hd'
        cmd.cpuNum = 2
        cmd.cpuSpeed = 2600
        cmd.dataVolumePath = ['/tmp/data.qcow2']
        cmd.rootVolumePath = '/tmp/root.qcow2'
        cmd.memory = 2048
        cmd.nics = []
        nic1 = vm_plugin.NicTO()
        nic1.mac = 'xxxxxxxx'
        nic1.bridgeName = 'br0'
        nic1.deviceId = 0
        cmd.nics.append(nic1)
        cmd.vmName = 'test'
        cmd.vmUuid = 'uuid'
        
        vm = vm_plugin.Vm()
        vm.boot_dev = cmd.bootDev
        vm.cpu_num = cmd.cpuNum
        vm.cpu_speed = cmd.cpuSpeed
        vm.memory = cmd.memory
        vm.name = cmd.vmName
        vm.uuid = cmd.vmUuid
        vm.nics = cmd.nics
        vm.root_volume = cmd.rootVolumePath
        vm.data_volumes = cmd.dataVolumePath
        vm.qemu_args = ['-append', 'mgmtNicIp=192.168.0.216', 'mgmtNicNetmask=255.255.255.0']
        print vm.to_xml(True)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()