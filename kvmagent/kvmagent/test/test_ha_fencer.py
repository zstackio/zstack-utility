import ast
import os
import sys
import types
import unittest
from unittest import mock
from xml.etree import ElementTree as etree


# ============================================================
# VmStruct standalone copy for testing (avoids Py2 import chain)
# Keep in sync with zstacklib/zstacklib/utils/linux.py VmStruct
# ============================================================
class VmStruct(object):
    def __init__(self):
        self.pid = ""
        self.xml = ""
        self.root_volume = ""
        self.uuid = ""
        self.volumes = []
        self.bridges = []

    def load_from_xml(self, xml):
        def load_interface_source(element):
            for e in element:
                if e.tag == "source":
                    if "bridge" in e.attrib:
                        self.bridges.append(e.attrib["bridge"])

        def load_disk_source(element):
            is_root_vol = False
            path = None
            for e in element:
                if e.tag == "boot":
                    is_root_vol = True
                elif e.tag == "source":
                    if "file" in e.attrib:
                        path = e.attrib["file"]
                    elif "dev" in e.attrib:
                        path = e.attrib["dev"]
                    elif "protocol" in e.attrib and "name" in e.attrib:
                        path = "%s:%s" % (e.attrib["protocol"], e.attrib["name"])
                    if path and path.startswith("/dev/"):
                        self.volumes.append(path)
            if is_root_vol:
                self.root_volume = path

        self.xml = xml
        root = etree.fromstring(xml)
        for e1 in root:
            if e1.tag == "domain":
                for e2 in e1:
                    if e2.tag == "devices":
                        for e3 in e2:
                            if e3.tag == "disk":
                                load_disk_source(e3)
                            if e3.tag == "interface":
                                load_interface_source(e3)
                        return


# ============================================================
# Test VmStruct.load_from_xml with different disk source types
# ============================================================
class TestVmStructLoadFromXml(unittest.TestCase):
    """Test VmStruct.load_from_xml correctly parses different disk source types"""

    CEPH_RBD_XML = '''<domstatus state='running' reason='booted' pid='73873'>
  <domain type='kvm' id='4'>
    <name>abc123</name>
    <devices>
      <disk type='network' device='disk'>
        <driver name='qemu' type='raw' cache='none'/>
        <auth username='zstack'>
          <secret type='ceph' uuid='55a6169b-7b60-4c81-bb3e-dd881578acf3'/>
        </auth>
        <source protocol='rbd' name='pool-xxx/vol-xxx'/>
        <target dev='vda' bus='virtio'/>
        <boot order='1'/>
      </disk>
    </devices>
  </domain>
</domstatus>'''

    FILE_DISK_XML = '''<domstatus state='running' reason='booted' pid='12345'>
  <domain type='kvm' id='5'>
    <name>def456</name>
    <devices>
      <disk type='file' device='disk'>
        <driver name='qemu' type='qcow2'/>
        <source file='/mnt/ps-uuid/vol-uuid.qcow2'/>
        <target dev='vda' bus='virtio'/>
        <boot order='1'/>
      </disk>
    </devices>
  </domain>
</domstatus>'''

    BLOCK_DISK_XML = '''<domstatus state='running' reason='booted' pid='99999'>
  <domain type='kvm' id='6'>
    <name>ghi789</name>
    <devices>
      <disk type='block' device='disk'>
        <driver name='qemu' type='raw'/>
        <source dev='/dev/zvol/pool/vol-xxx'/>
        <target dev='vda' bus='virtio'/>
        <boot order='1'/>
      </disk>
    </devices>
  </domain>
</domstatus>'''

    NO_BOOT_XML = '''<domstatus state='running' reason='booted' pid='11111'>
  <domain type='kvm' id='7'>
    <name>noboot</name>
    <devices>
      <disk type='network' device='disk'>
        <source protocol='rbd' name='pool-xxx/vol-xxx'/>
        <target dev='vda' bus='virtio'/>
      </disk>
    </devices>
  </domain>
</domstatus>'''

    BRIDGE_XML = '''<domstatus state='running' reason='booted' pid='22222'>
  <domain type='kvm' id='8'>
    <name>bridgevm</name>
    <devices>
      <disk type='network' device='disk'>
        <source protocol='rbd' name='pool-xxx/vol-xxx'/>
        <target dev='vda' bus='virtio'/>
        <boot order='1'/>
      </disk>
      <interface type='bridge'>
        <source bridge='br_eth0'/>
      </interface>
    </devices>
  </domain>
</domstatus>'''

    def test_load_ceph_rbd_disk_sets_root_volume(self):
        """Ceph RBD disk (protocol+name) should be parsed as root_volume"""
        vm = VmStruct()
        vm.load_from_xml(self.CEPH_RBD_XML)
        self.assertEqual('rbd:pool-xxx/vol-xxx', vm.root_volume)

    def test_load_file_disk_sets_root_volume(self):
        """File-based disk should be parsed as root_volume"""
        vm = VmStruct()
        vm.load_from_xml(self.FILE_DISK_XML)
        self.assertEqual('/mnt/ps-uuid/vol-uuid.qcow2', vm.root_volume)

    def test_load_block_disk_sets_root_volume(self):
        """Block device disk should be parsed as root_volume"""
        vm = VmStruct()
        vm.load_from_xml(self.BLOCK_DISK_XML)
        self.assertEqual('/dev/zvol/pool/vol-xxx', vm.root_volume)
        self.assertIn('/dev/zvol/pool/vol-xxx', vm.volumes)

    def test_no_boot_element_leaves_root_volume_empty(self):
        """Disk without <boot> element should not set root_volume"""
        vm = VmStruct()
        vm.load_from_xml(self.NO_BOOT_XML)
        self.assertEqual('', vm.root_volume)

    def test_ceph_root_volume_contains_pool_name(self):
        """Verify mountPath matching works: pool name is substring of root_volume"""
        vm = VmStruct()
        vm.load_from_xml(self.CEPH_RBD_XML)
        mount_path = 'pool-xxx/'
        self.assertIn(mount_path, vm.root_volume)

    def test_bridge_interface_parsed(self):
        """Verify bridge interfaces are parsed from XML"""
        vm = VmStruct()
        vm.load_from_xml(self.BRIDGE_XML)
        self.assertIn('br_eth0', vm.bridges)
        self.assertEqual('rbd:pool-xxx/vol-xxx', vm.root_volume)


# ============================================================
# Verify fencers call kill_vm_by_xml (not kill_vm) via AST
# ============================================================
class TestFencerCallsKillVmByXml(unittest.TestCase):
    """Verify at source level that fencers call kill_vm_by_xml, not kill_vm"""

    @classmethod
    def setUpClass(cls):
        ha_plugin_path = os.path.join(
            os.path.dirname(__file__), '..', 'plugins', 'ha_plugin.py')
        with open(ha_plugin_path, 'r') as f:
            cls.tree = ast.parse(f.read())

    def _get_method_calls(self, class_name, method_name):
        """Extract all function call names from a method in a class"""
        calls = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in ast.walk(node):
                    if isinstance(item, ast.FunctionDef) and item.name == method_name:
                        for call_node in ast.walk(item):
                            if isinstance(call_node, ast.Call):
                                if isinstance(call_node.func, ast.Name):
                                    calls.append(call_node.func.id)
                                elif isinstance(call_node.func, ast.Attribute):
                                    calls.append(call_node.func.attr)
        return calls

    def test_filesystem_fencer_calls_kill_vm_by_xml(self):
        """FileSystemHeartbeatController.check_storage_heartbeat should call kill_vm_by_xml"""
        calls = self._get_method_calls('FileSystemHeartbeatController', 'check_storage_heartbeat')
        self.assertIn('kill_vm_by_xml', calls,
                      "check_storage_heartbeat must call kill_vm_by_xml")
        self.assertNotIn('kill_vm', calls,
                         "check_storage_heartbeat must NOT call kill_vm directly")

    def test_ceph_fencer_calls_kill_vm_by_xml(self):
        """CephHeartbeatController.handle_heartbeat_failure should call kill_vm_by_xml"""
        calls = self._get_method_calls('CephHeartbeatController', 'handle_heartbeat_failure')
        self.assertIn('kill_vm_by_xml', calls,
                      "handle_heartbeat_failure must call kill_vm_by_xml")
        self.assertNotIn('kill_vm', calls,
                         "handle_heartbeat_failure must NOT call kill_vm directly")

    def test_get_runnning_vm_calls_load_from_xml(self):
        """get_runnning_vm_root_volume_on_ps must call vm.load_from_xml"""
        for node in ast.walk(self.tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'get_runnning_vm_root_volume_on_ps':
                source = ast.dump(node)
                self.assertIn('load_from_xml', source,
                              "get_runnning_vm_root_volume_on_ps must call load_from_xml")
                return
        self.fail("get_runnning_vm_root_volume_on_ps not found in source")


if __name__ == '__main__':
    unittest.main()
