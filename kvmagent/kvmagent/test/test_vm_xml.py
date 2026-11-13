'''

@author: Frank
'''
import unittest
from unittest import mock

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils
from lxml import etree

class Test(unittest.TestCase):

    def testVirtioSerialPort(self):
        cmd = vm_utils.create_startvm_body_jsonobject()
        cmd.addons.channel.targetName = 'applianceVm.vport'
        cmd.addons.channel.virtioSerialPort = 8

        vm = vm_plugin.Vm.from_StartVmCmd(cmd)
        channel = etree.fromstring(vm.domain_xml).xpath("./devices/channel[target[@name='applianceVm.vport']]")[0]
        address = channel.find('address')
        self.assertIsNotNone(address)
        self.assertEqual('virtio-serial', address.get('type'))
        self.assertEqual('8', address.get('port'))
        self.assertEqual('0', address.get('controller'))
        self.assertEqual('0', address.get('bus'))

        cmd = vm_utils.create_startvm_body_jsonobject()
        cmd.addons.channel.targetName = 'applianceVm.vport'
        vm = vm_plugin.Vm.from_StartVmCmd(cmd)
        channel = etree.fromstring(vm.domain_xml).xpath("./devices/channel[target[@name='applianceVm.vport']]")[0]
        self.assertIsNone(channel.find('address'))


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
        print(vm.to_xml(True))

    def testBlockVolumeDiscard(self):
        cmd = vm_utils.create_startvm_body_jsonobject()
        cmd.rootVolume.deviceType = 'block'
        cmd.rootVolume.installPath = '/dev/zstack-vg/root-volume'
        with mock.patch('kvmagent.plugins.vm_plugin.linux.get_img_fmt', return_value='qcow2'):
            vm = vm_plugin.Vm.from_StartVmCmd(cmd)

        disk = etree.fromstring(vm.domain_xml).xpath(
            "./devices/disk[source[@dev='/dev/zstack-vg/root-volume']]"
        )[0]
        self.assertEqual('unmap', disk.find('driver').get('discard'))

    @unittest.skipUnless(vm_plugin.HOST_ARCH == 'x86_64', 'i440fx is x86_64 only')
    def testLegacyI440fxAddsDiscardWithoutChangingMemoryBacking(self):
        cmd = vm_utils.create_startvm_body_jsonobject()
        cmd.bootMode = 'Legacy'
        cmd.machineType = 'pc-i440fx-rhel7.6.0'

        vm = vm_plugin.Vm.from_StartVmCmd(cmd)

        namespace = '{http://libvirt.org/schemas/domain/qemu/1.0}'
        root = etree.fromstring(vm.domain_xml)
        commandlines = root.findall('%scommandline' % namespace)
        self.assertEqual(1, len(commandlines))
        values = [arg.get('value') for commandline in commandlines
                  for arg in commandline.findall('%sarg' % namespace)]
        self.assertIn('virtio-blk-pci.discard=on', values)
        self.assertIsNone(root.find('memoryBacking'))

    @unittest.skipUnless(vm_plugin.HOST_ARCH == 'x86_64', 'i440fx is x86_64 only')
    def testMissingBootModeUsesLegacyDiscardDefault(self):
        cmd = vm_utils.create_startvm_body_jsonobject()
        cmd.bootMode = None
        cmd.machineType = 'pc-i440fx-rhel7.6.0'
        cmd.additionalQmp = False

        root = etree.fromstring(vm_plugin.Vm.from_StartVmCmd(cmd).domain_xml)
        namespace = '{http://libvirt.org/schemas/domain/qemu/1.0}'
        commandlines = root.findall('%scommandline' % namespace)
        self.assertEqual(1, len(commandlines))
        values = [arg.get('value') for commandline in commandlines
                  for arg in commandline.findall('%sarg' % namespace)]
        self.assertIn('virtio-blk-pci.discard=on', values)

    @unittest.skipUnless(vm_plugin.HOST_ARCH == 'x86_64', 'i440fx is x86_64 only')
    def testExplicitDiscardOffIsNotOverridden(self):
        cmd = vm_utils.create_startvm_body_jsonobject()
        cmd.bootMode = 'Legacy'
        cmd.machineType = 'pc-i440fx-rhel7.6.0'
        cmd.addons.qemuCommandLine = ['-global', 'virtio-blk-pci.discard=off']

        root = etree.fromstring(vm_plugin.Vm.from_StartVmCmd(cmd).domain_xml)
        namespace = '{http://libvirt.org/schemas/domain/qemu/1.0}'
        values = [arg.get('value') for commandline in root.findall('%scommandline' % namespace)
                  for arg in commandline.findall('%sarg' % namespace)]
        self.assertIn('virtio-blk-pci.discard=off', values)
        self.assertNotIn('virtio-blk-pci.discard=on', values)

    @unittest.skipUnless(vm_plugin.HOST_ARCH == 'x86_64', 'q35 is x86_64 only')
    def testQ35DoesNotAddGlobalDiscard(self):
        cmd = vm_utils.create_startvm_body_jsonobject()
        cmd.bootMode = 'Legacy'
        cmd.machineType = 'pc-q35-rhel8.6.0'

        vm = vm_plugin.Vm.from_StartVmCmd(cmd)

        namespace = '{http://libvirt.org/schemas/domain/qemu/1.0}'
        root = etree.fromstring(vm.domain_xml)
        values = [arg.get('value') for commandline in root.findall('%scommandline' % namespace)
                  for arg in commandline.findall('%sarg' % namespace)]
        self.assertNotIn('virtio-blk-pci.discard=on', values)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
