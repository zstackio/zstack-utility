import unittest
from unittest import mock

from kvmagent.plugins.ha_plugin import PhysicalNicFencer, LIVE_LIBVIRT_XML_DIR


# Live XML in /var/run/libvirt/qemu/ uses <domstatus> as root, <domain> as child
SAMPLE_XML_WITH_BRIDGE = """<domstatus state='running'>
  <domain type='kvm'>
    <devices>
      <interface type='bridge'>
        <source bridge='br_eth0'/>
        <mac address='fa:da:21:ab:cd:01'/>
      </interface>
    </devices>
  </domain>
</domstatus>"""

SAMPLE_XML_NO_MATCH_BRIDGE = """<domstatus state='running'>
  <domain type='kvm'>
    <devices>
      <interface type='bridge'>
        <source bridge='br_eth1'/>
        <mac address='fa:da:21:ab:cd:02'/>
      </interface>
    </devices>
  </domain>
</domstatus>"""

SAMPLE_XML_NO_INTERFACE = """<domstatus state='running'>
  <domain type='kvm'>
    <devices>
      <disk type='file' device='disk'>
        <source file='/dev/null'/>
      </disk>
    </devices>
  </domain>
</domstatus>"""


def _make_fencer():
    """Create a PhysicalNicFencer with minimal init (mocked run_fencer_list)."""
    with mock.patch('kvmagent.plugins.ha_plugin.AbstractHaFencer.__init__', return_value=None):
        f = PhysicalNicFencer.__new__(PhysicalNicFencer)
        f.name = "hostBusinessNic"
        f.falut_nic_count = {}
        f.interval = 5
        f.max_attempts = 3
        f.ps_uuid = "test-ps"
        f.run_fencer_list = []
    return f


class TestIsBridgeRelatedToNic(unittest.TestCase):
    """Unit tests for bridge-to-NIC matching logic."""

    def setUp(self):
        self.fencer = _make_fencer()

    def test_bridge_with_underscore_matches(self):
        # br_eth0 → strip prefix → eth0, check in ['eth0']
        self.assertTrue(self.fencer.is_bridge_related_to_nic('br_eth0', ['eth0']))

    def test_bridge_with_dot_matches(self):
        # eth0.100 → strip suffix → eth0
        self.assertTrue(self.fencer.is_bridge_related_to_nic('eth0.100', ['eth0']))

    def test_bridge_with_underscore_and_dot(self):
        # br_eth0.100 → split _ → eth0.100 → split . → eth0
        self.assertTrue(self.fencer.is_bridge_related_to_nic('br_eth0.100', ['eth0']))

    def test_bridge_no_match(self):
        self.assertFalse(self.fencer.is_bridge_related_to_nic('br_eth1', ['eth0']))

    def test_empty_bridge(self):
        self.assertFalse(self.fencer.is_bridge_related_to_nic('', ['eth0']))

    def test_multiple_faulted_nics(self):
        self.assertTrue(self.fencer.is_bridge_related_to_nic('br_eth1', ['eth0', 'eth1']))
        self.assertFalse(self.fencer.is_bridge_related_to_nic('br_eth2', ['eth0', 'eth1']))


class TestVmMayUseFaultedNicByXml(unittest.TestCase):
    """Unit tests for the XML pre-filter added in ZSTAC-79557 v2."""

    def setUp(self):
        self.fencer = _make_fencer()
        self.vm_uuid = "test-vm-uuid-1234"
        self.falut_nic = ['eth0']

    @mock.patch('kvmagent.plugins.ha_plugin.linux.read_file')
    def test_xml_shows_matching_bridge_returns_true(self, mock_read_file):
        mock_read_file.return_value = SAMPLE_XML_WITH_BRIDGE
        result = self.fencer._vm_may_use_faulted_nic_by_xml(self.vm_uuid, self.falut_nic)
        self.assertTrue(result)
        mock_read_file.assert_called_once_with(LIVE_LIBVIRT_XML_DIR + "/%s.xml" % self.vm_uuid)

    @mock.patch('kvmagent.plugins.ha_plugin.linux.read_file')
    def test_xml_shows_no_matching_bridge_returns_false(self, mock_read_file):
        mock_read_file.return_value = SAMPLE_XML_NO_MATCH_BRIDGE
        result = self.fencer._vm_may_use_faulted_nic_by_xml(self.vm_uuid, self.falut_nic)
        self.assertFalse(result)

    @mock.patch('kvmagent.plugins.ha_plugin.linux.read_file')
    def test_xml_no_interface_returns_false(self, mock_read_file):
        mock_read_file.return_value = SAMPLE_XML_NO_INTERFACE
        result = self.fencer._vm_may_use_faulted_nic_by_xml(self.vm_uuid, self.falut_nic)
        self.assertFalse(result)

    @mock.patch('kvmagent.plugins.ha_plugin.linux.read_file')
    def test_xml_unreadable_returns_true_as_safe_fallback(self, mock_read_file):
        """When XML can't be read, return True so virsh is used as fallback."""
        mock_read_file.return_value = None
        result = self.fencer._vm_may_use_faulted_nic_by_xml(self.vm_uuid, self.falut_nic)
        self.assertTrue(result)

    @mock.patch('kvmagent.plugins.ha_plugin.linux.read_file')
    def test_multiple_faulted_nics_any_match(self, mock_read_file):
        mock_read_file.return_value = SAMPLE_XML_WITH_BRIDGE  # has br_eth0
        result = self.fencer._vm_may_use_faulted_nic_by_xml(self.vm_uuid, ['eth0', 'eth1'])
        self.assertTrue(result)


class TestFindVmUseFaultNicWithVirsh(unittest.TestCase):
    """Integration test: with_virsh path now skips virsh for non-matching VMs."""

    def setUp(self):
        self.fencer = _make_fencer()

    @mock.patch.object(PhysicalNicFencer, '_get_vm_pid')
    @mock.patch('kvmagent.plugins.ha_plugin.shell.call')
    @mock.patch('kvmagent.plugins.ha_plugin.linux.read_file')
    @mock.patch('kvmagent.plugins.ha_plugin.find_vm_uuid_list_by_virsh')
    @mock.patch.object(PhysicalNicFencer, 'get_vm_business_nic_route', return_value='hostBusinessNic')
    def test_skips_virsh_for_vms_not_using_faulted_nic(
            self, mock_skip, mock_virsh_list, mock_read_file, mock_shell_call, mock_find_pid):
        """Core scenario: 3 VMs on host, only vm-3 uses faulted NIC eth0.
        virsh domiflist should only be called for vm-3."""
        vm1 = "vm-uuid-1111"
        vm2 = "vm-uuid-2222"
        vm3 = "vm-uuid-3333"
        mock_virsh_list.return_value = [vm1, vm2, vm3]

        def read_xml(path):
            if vm1 in path:
                return SAMPLE_XML_NO_MATCH_BRIDGE  # eth1 only
            if vm2 in path:
                return SAMPLE_XML_NO_INTERFACE      # no NIC at all
            if vm3 in path:
                return SAMPLE_XML_WITH_BRIDGE        # eth0 — matches
            return None

        mock_read_file.side_effect = read_xml
        mock_shell_call.return_value = "br_eth0\n"  # virsh domiflist output for vm3
        mock_find_pid.return_value = "12345"

        result, affected_host_vms, affected_group_vms = (
            self.fencer.find_vm_use_falut_nic_with_virsh(['eth0'])
        )

        # Only vm3 should be in result
        self.assertEqual(result, {vm3: "12345"})
        self.assertEqual(affected_host_vms, [vm3])
        self.assertEqual(affected_group_vms, [])
        # virsh domiflist should be called exactly once (for vm3 only)
        self.assertEqual(mock_shell_call.call_count, 1)
        self.assertIn(vm3, mock_shell_call.call_args[0][0])

    @mock.patch('kvmagent.plugins.ha_plugin.shell.call')
    @mock.patch('kvmagent.plugins.ha_plugin.linux.read_file')
    @mock.patch('kvmagent.plugins.ha_plugin.find_vm_uuid_list_by_virsh')
    @mock.patch.object(PhysicalNicFencer, 'get_vm_business_nic_route', return_value='hostBusinessNic')
    def test_all_vms_no_match_zero_virsh_calls(
            self, mock_skip, mock_virsh_list, mock_read_file, mock_shell_call):
        """100-VM scenario from Jira: none use faulted NIC → zero virsh domiflist calls."""
        vm_uuids = ["vm-uuid-%04d" % i for i in range(100)]
        mock_virsh_list.return_value = vm_uuids
        mock_read_file.return_value = SAMPLE_XML_NO_MATCH_BRIDGE  # all have eth1 only

        result, affected_host_vms, affected_group_vms = (
            self.fencer.find_vm_use_falut_nic_with_virsh(['eth0'])
        )

        self.assertEqual(result, {})
        self.assertEqual(affected_host_vms, [])
        self.assertEqual(affected_group_vms, [])
        mock_shell_call.assert_not_called()

    @mock.patch.object(PhysicalNicFencer, '_get_vm_pid')
    @mock.patch('kvmagent.plugins.ha_plugin.shell.call')
    @mock.patch('kvmagent.plugins.ha_plugin.linux.read_file')
    @mock.patch('kvmagent.plugins.ha_plugin.find_vm_uuid_list_by_virsh')
    @mock.patch.object(PhysicalNicFencer, 'get_vm_business_nic_route', return_value='hostBusinessNic')
    def test_xml_unreadable_falls_back_to_virsh(
            self, mock_skip, mock_virsh_list, mock_read_file, mock_shell_call, mock_find_pid):
        """If XML can't be read, virsh domiflist is still called (safe fallback)."""
        vm1 = "vm-uuid-1111"
        mock_virsh_list.return_value = [vm1]
        mock_read_file.return_value = None  # XML unreadable
        mock_shell_call.return_value = "br_eth0\n"
        mock_find_pid.return_value = "99999"

        result, affected_host_vms, affected_group_vms = (
            self.fencer.find_vm_use_falut_nic_with_virsh(['eth0'])
        )

        self.assertEqual(result, {vm1: "99999"})
        self.assertEqual(affected_host_vms, [vm1])
        self.assertEqual(affected_group_vms, [])
        self.assertEqual(mock_shell_call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
