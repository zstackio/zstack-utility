# encoding: utf-8

'''

@author: frank
'''
try:
    import mock
except ImportError:
    from unittest import mock
import subprocess
import time
import unittest

from kvmagent import kvmagent
from kvmagent.plugins import host_plugin
from zstacklib.utils import http
from zstacklib.utils import uuidhelper
from zstacklib.utils import jsonobject
from zstacklib.utils import log


logger = log.get_logger(__name__)

class ConnectCmd(kvmagent.AgentCommand):
    def __init__(self):
        self.hostUuid = uuidhelper.uuid()

class HostFactCmd(kvmagent.AgentCommand): pass



class TestHostPlugin(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.service = kvmagent.new_rest_service()
        self.service.start()
        time.sleep(1)

    @classmethod
    def tearDownClass(self):
        self.service.stop()


    def test_connect(self):
        url = kvmagent._build_url_for_test([host_plugin.HostPlugin.CONNECT_PATH])
        logger.debug('calling %s' % url)
        ret = http.json_dump_post(url, body=ConnectCmd())
        rsp = jsonobject.loads(ret)
        self.assertTrue(rsp.success)

    @mock.patch('subprocess.Popen')
    def test_hostfact(self, mock_popen):
        url = kvmagent._build_url_for_test([host_plugin.HostPlugin.FACT_PATH])
        cmd = HostFactCmd()
        ret = http.json_dump_post(url, body=cmd)
        rsp = jsonobject.loads(ret)
        self.assertTrue(rsp.success)
        self.assertEqual(host_plugin._get_cpu_num(), rsp.cpuNum)
        self.assertEqual(host_plugin._get_cpu_speed(), rsp.cpuSpeed)
        self.assertEqual(host_plugin._get_total_memory(), rsp.totalMemory)

    if __name__ == "__main__":
        #import sys;sys.argv = ['', 'Test.testName']
        unittest.main()


class TestHostPluginVirtStatusFallback(unittest.TestCase):
    """Unit tests for _apply_virt_status_fallback (ZSTAC-81834)."""

    def _make_to(self, virt_status=""):
        to = host_plugin.PciDeviceTO()
        to.pciDeviceAddress = "0000:00:01.0"
        to.virtStatus = virt_status
        return to

    def _make_context(self, gpu_info_map=None):
        return type('Context', (), {'gpu_info_map': gpu_info_map})()

    def test_fallback_neither_supported(self):
        """No virtStatus, neither vfio_mdev nor sriov -> UNVIRTUALIZABLE."""
        plugin = host_plugin.HostPlugin()
        to = self._make_to()
        context = self._make_context()
        with mock.patch.object(plugin, '_get_vfio_mdev_info', return_value=False):
            with mock.patch.object(plugin, '_get_sriov_info', return_value=False):
                plugin._apply_virt_status_fallback([to], context)
        self.assertEqual(to.virtStatus, "UNVIRTUALIZABLE")
        self.assertEqual(to.virtState, "UNVIRTUALIZABLE")

    def test_nvidia_audio_function_skips_legacy_vfio_probe(self):
        plugin = host_plugin.HostPlugin()
        to = self._make_to()
        to.pciDeviceAddress = "0000:1d:00.1"
        to.vendor = host_plugin.VendorEnum.NVIDIA
        to.type = "Audio_Controller"
        with mock.patch.object(host_plugin, 'bash_roe') as bash_roe:
            self.assertFalse(plugin._get_vfio_mdev_info(to))
        bash_roe.assert_not_called()

    def test_fallback_both_supported_virtualizable(self):
        """No virtStatus, both supported -> VFIO_MDEV_VIRTUALIZABLE."""
        plugin = host_plugin.HostPlugin()
        to = self._make_to()

        def vfio_mdev(to):
            to.virtStatus = "VFIO_MDEV_VIRTUALIZABLE"
            return True

        def sriov(to, gpu_info_map=None):
            to.virtStatus = "SRIOV_VIRTUALIZABLE"
            return True

        context = self._make_context()
        with mock.patch.object(plugin, '_get_vfio_mdev_info', side_effect=vfio_mdev):
            with mock.patch.object(plugin, '_get_sriov_info', side_effect=sriov):
                plugin._apply_virt_status_fallback([to], context)
        self.assertEqual(to.virtStatus, "VFIO_MDEV_VIRTUALIZABLE")
        self.assertEqual(to.virtState, "VIRTUALIZABLE")
        self.assertEqual(to.virtCapabilities, ["VFIO_MDEV", "SRIOV"])

    def test_fallback_both_supported_already_virtualized(self):
        """Both supported but vfio_mdev_status is VFIO_MDEV_VIRTUALIZED -> keep it."""
        plugin = host_plugin.HostPlugin()
        to = self._make_to()

        def vfio_mdev(to):
            to.virtStatus = "VFIO_MDEV_VIRTUALIZED"
            return True

        def sriov(to, gpu_info_map=None):
            to.virtStatus = "SRIOV_VIRTUALIZABLE"
            return True

        context = self._make_context()
        with mock.patch.object(plugin, '_get_vfio_mdev_info', side_effect=vfio_mdev):
            with mock.patch.object(plugin, '_get_sriov_info', side_effect=sriov):
                plugin._apply_virt_status_fallback([to], context)
        self.assertEqual(to.virtStatus, "SRIOV_VIRTUALIZABLE")
        self.assertEqual(to.virtState, "VIRTUALIZABLE")
        self.assertEqual(to.virtCapabilities, ["VFIO_MDEV", "SRIOV"])

    def test_fallback_only_sriov(self):
        """No virtStatus, only sriov (e.g. NIC) -> keep SRIOV_* from _get_sriov_info."""
        plugin = host_plugin.HostPlugin()
        to = self._make_to()

        def sriov(to, gpu_info_map=None):
            to.virtStatus = "SRIOV_VIRTUALIZABLE"
            return True

        context = self._make_context()
        with mock.patch.object(plugin, '_get_vfio_mdev_info', return_value=False):
            with mock.patch.object(plugin, '_get_sriov_info', side_effect=sriov):
                plugin._apply_virt_status_fallback([to], context)
        self.assertEqual(to.virtStatus, "SRIOV_VIRTUALIZABLE")
        self.assertEqual(to.virtState, "VIRTUALIZABLE")
        self.assertEqual(to.virtCapabilities, ["SRIOV"])

    def test_fallback_only_vfio_mdev(self):
        """No virtStatus, only vfio_mdev -> keep value from _get_vfio_mdev_info."""
        plugin = host_plugin.HostPlugin()
        to = self._make_to()

        def vfio_mdev(to):
            to.virtStatus = "VFIO_MDEV_VIRTUALIZABLE"
            return True

        context = self._make_context()
        with mock.patch.object(plugin, '_get_vfio_mdev_info', side_effect=vfio_mdev):
            with mock.patch.object(plugin, '_get_sriov_info', return_value=False):
                plugin._apply_virt_status_fallback([to], context)
        self.assertEqual(to.virtStatus, "VFIO_MDEV_VIRTUALIZABLE")
        self.assertEqual(to.virtState, "VIRTUALIZABLE")
        self.assertEqual(to.virtCapabilities, ["VFIO_MDEV"])

    def test_fallback_already_has_virt_status(self):
        """Device already has virtStatus (e.g. from GPU ops) -> unchanged."""
        plugin = host_plugin.HostPlugin()
        to = self._make_to(virt_status="UNVIRTUALIZABLE")
        context = self._make_context()
        with mock.patch.object(plugin, '_get_vfio_mdev_info', return_value=False):
            with mock.patch.object(plugin, '_get_sriov_info', return_value=False):
                plugin._apply_virt_status_fallback([to], context)
        self.assertEqual(to.virtStatus, "UNVIRTUALIZABLE")
        self.assertEqual(to.virtState, "UNVIRTUALIZABLE")

    def test_fallback_empty_after_detection_gets_unvirtualizable(self):
        """virtStatus still empty after detection (e.g. detection didn't set it) -> UNVIRTUALIZABLE."""
        plugin = host_plugin.HostPlugin()
        to = self._make_to()

        def vfio_mdev(to):
            return False

        def sriov(to, gpu_info_map=None):
            return True
            # intentionally do not set to.virtStatus to simulate edge case

        context = self._make_context()
        with mock.patch.object(plugin, '_get_vfio_mdev_info', side_effect=vfio_mdev):
            with mock.patch.object(plugin, '_get_sriov_info', side_effect=sriov):
                plugin._apply_virt_status_fallback([to], context)
        self.assertEqual(to.virtStatus, "UNVIRTUALIZABLE")
        self.assertEqual(to.virtState, "UNVIRTUALIZABLE")

    def test_existing_tensorfusion_status_fills_capability_and_state(self):
        """Existing TensorFusion virtStatus should backfill capability/state."""
        plugin = host_plugin.HostPlugin()
        to = self._make_to(virt_status="TENSORFUSION_VIRTUALIZABLE")
        context = self._make_context()
        with mock.patch.object(plugin, '_get_vfio_mdev_info', return_value=False):
            with mock.patch.object(plugin, '_get_sriov_info', return_value=False):
                plugin._apply_virt_status_fallback([to], context)
        self.assertEqual(to.virtStatus, "TENSORFUSION_VIRTUALIZABLE")
        self.assertEqual(to.virtState, "VIRTUALIZABLE")
        self.assertEqual(to.virtCapabilities, ["TENSORFUSION"])

    def test_existing_hami_status_fills_capability_and_state(self):
        """Existing HAMI virtStatus should backfill capability/state."""
        plugin = host_plugin.HostPlugin()
        to = self._make_to(virt_status="HAMI_VIRTUALIZED")
        context = self._make_context()
        with mock.patch.object(plugin, '_get_vfio_mdev_info', return_value=False):
            with mock.patch.object(plugin, '_get_sriov_info', return_value=False):
                plugin._apply_virt_status_fallback([to], context)
        self.assertEqual(to.virtStatus, "HAMI_VIRTUALIZED")
        self.assertEqual(to.virtState, "VIRTUALIZED")
        self.assertEqual(to.virtCapabilities, ["HAMI"])

    def test_existing_explicit_state_wins_over_status(self):
        """Explicit virtState should be preserved when host_plugin already filled it."""
        plugin = host_plugin.HostPlugin()
        to = self._make_to(virt_status="UNVIRTUALIZABLE")
        to.virtState = "VIRTUALIZABLE"
        to.virtCapabilities = ["TENSORFUSION"]
        context = self._make_context()
        with mock.patch.object(plugin, '_get_vfio_mdev_info', return_value=False):
            with mock.patch.object(plugin, '_get_sriov_info', return_value=False):
                plugin._apply_virt_status_fallback([to], context)
        self.assertEqual(to.virtStatus, "UNVIRTUALIZABLE")
        self.assertEqual(to.virtState, "VIRTUALIZABLE")
        self.assertEqual(to.virtCapabilities, ["TENSORFUSION"])


class TestHostPluginGetBlockDevices(unittest.TestCase):
    def _make_device(self, name):
        dev = host_plugin.lvm.SharedBlockCandidateStruct()
        dev.name = name
        return dev

    def _call_get_block_devices(self, body):
        plugin = host_plugin.HostPlugin()
        req = {http.REQUEST_BODY: body}
        return jsonobject.loads(plugin.get_block_devices(req))

    def test_get_block_devices_filters_mounted_by_default(self):
        devices = [self._make_device("/dev/sdb"), self._make_device("/dev/sdc")]
        with mock.patch.object(host_plugin.lvm, 'get_block_devices', return_value=devices):
            with mock.patch.object(host_plugin.linux, 'is_block_device_mounted',
                                   side_effect=lambda name: name == "/dev/sdc") as mock_mounted:
                rsp = self._call_get_block_devices("{}")

        self.assertEqual(["/dev/sdb"], [d.name for d in rsp.blockDevices])
        self.assertIsInstance(rsp.blockDevices, list)
        self.assertTrue(rsp.blockDevices[0].name)
        self.assertEqual(2, mock_mounted.call_count)

    def test_get_block_devices_filters_mounted_when_include_in_use_false(self):
        devices = [self._make_device("/dev/sdb"), self._make_device("/dev/sdc")]
        with mock.patch.object(host_plugin.lvm, 'get_block_devices', return_value=devices):
            with mock.patch.object(host_plugin.linux, 'is_block_device_mounted',
                                   side_effect=lambda name: name == "/dev/sdc") as mock_mounted:
                rsp = self._call_get_block_devices('{"includeInUse": false}')

        self.assertEqual(["/dev/sdb"], [d.name for d in rsp.blockDevices])
        self.assertIsInstance(rsp.blockDevices, list)
        self.assertTrue(rsp.blockDevices[0].name)
        self.assertEqual(2, mock_mounted.call_count)

    def test_get_block_devices_returns_all_when_include_in_use_true(self):
        devices = [self._make_device("/dev/sdb"), self._make_device("/dev/sdc")]
        with mock.patch.object(host_plugin.lvm, 'get_block_devices', return_value=devices):
            with mock.patch.object(host_plugin.linux, 'is_block_device_mounted') as mock_mounted:
                rsp = self._call_get_block_devices('{"includeInUse": true}')

        self.assertEqual(["/dev/sdb", "/dev/sdc"], [d.name for d in rsp.blockDevices])
        self.assertIsInstance(rsp.blockDevices, list)
        self.assertTrue(rsp.blockDevices[0].name)
        self.assertFalse(mock_mounted.called)
