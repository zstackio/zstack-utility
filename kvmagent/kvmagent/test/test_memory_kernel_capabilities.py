"""Use real discovery: sysfs presence alone does not qualify the service kernel."""
import json
import unittest
from unittest.mock import patch, mock_open
from kvmagent.plugins import memory_optimization as module
from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin

KERNEL = '4.18.0-553.162.1.memopt1.el8.x86_64'
ALINUX_KERNEL = '6.6.102-005.3.pro.ali6000.alnx4.x86_64'


class TestMemoryKernelCapabilities(unittest.TestCase):
    def discover(self, response):
        def call(action, payload):
            self.assertEqual('capabilities', action)
            if isinstance(response, Exception):
                raise response
            return response
        plugin = MemoryOptimizationPlugin(service_call=call)
        with patch.object(module.platform, 'machine', return_value='x86_64'), \
                patch.object(module.platform, 'release', return_value=KERNEL), \
                patch.object(module.os, 'sysconf', return_value=4096), \
                patch.object(module.os.path, 'exists', return_value=True), \
                patch.object(module, 'open', mock_open(read_data='ID=helix\nVERSION_ID=8.4\nVERSION="8.4 (Green Obsidian)"'), create=True):
            return plugin.discover_capabilities()

    def response(self, **updates):
        q = {'supported': True, 'kernel': KERNEL, 'reason_code': 'SUPPORTED',
             'architecture': 'amd64', 'page_size_bytes': 4096}
        q.update(updates)
        return {'abiProfile': 'zram-service-v1', 'schemaVersion': 1, 'reclaim_qualification': q}

    def test_candidate_service_support_is_required_but_ksm_is_independent(self):
        for reply in ({}, self.response(supported=False, reason_code='UNSUPPORTED_RECLAIM_KERNEL'),
                      self.response(kernel='other'), self.response(supported='true'),
                      self.response(page_size_bytes=65536), self.response(architecture='arm64'),
                      {'abiProfile': 'other', 'reclaim_qualification': self.response()['reclaim_qualification']},
                      IOError('service unavailable')):
            with self.subTest(reply=str(reply)):
                caps = self.discover(reply)
                self.assertTrue(caps['ksm'])
                self.assertTrue(caps['ksmZeroPages'])
                self.assertFalse(caps['zram'])
                self.assertFalse(caps['writeback'])
                self.assertNotEqual('SUPPORTED', caps['zramReasonCode'])
                MemoryOptimizationPlugin._validate_requested_capabilities({'policy': {'ksm': {'mode': 'Active'}}}, caps)
                with self.assertRaises(ValueError):
                    MemoryOptimizationPlugin._validate_requested_capabilities({'policy': {'zram': {'enabled': True}}}, caps)

    def test_candidate_service_support_allows_zram(self):
        caps = self.discover(self.response())
        self.assertTrue(caps['zram'])
        self.assertEqual('SUPPORTED', caps['zramReasonCode'])

    def discover_alinux(self, driver, service_supported=True):
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: self.response(
            kernel=ALINUX_KERNEL, supported=service_supported,
            reason_code='SUPPORTED' if service_supported else 'RECLAIM_UNSUPPORTED'))
        with patch.object(module.platform, 'machine', return_value='x86_64'), \
                patch.object(module.platform, 'release', return_value=ALINUX_KERNEL), \
                patch.object(module.os, 'sysconf', return_value=4096), \
                patch.object(module.os.path, 'exists', return_value=True), \
                patch.object(module, 'open', mock_open(read_data='ID=alinux\nVERSION_ID=4\n'), create=True), \
                patch.object(module.zram_driver, 'inspect', return_value=driver) as inspect:
            caps = plugin.discover_capabilities()
        inspect.assert_called_once_with(release='alinux4', architecture='x86_64',
                                        kernel=ALINUX_KERNEL)
        return caps

    def test_alinux_driver_rejections_keep_ksm_independent(self):
        for reason in ('ZRAM_DRIVER_NOT_LOADED', 'ZRAM_DRIVER_DISK_ABI_MISMATCH',
                       'ZRAM_DRIVER_LOADED_IDENTITY_MISSING',
                       'ZRAM_DRIVER_UPDATE_REQUIRES_MAINTENANCE',
                       'ZRAM_DRIVER_OBSERVATION_FAILED'):
            with self.subTest(reason=reason):
                driver = {'supported': False, 'reasonCode': reason,
                          'disk': {'version': '5.5.48.1'}, 'loaded': {'version': 'old'}}
                caps = self.discover_alinux(driver)
                self.assertTrue(caps['supported'])
                self.assertTrue(caps['ksm'])
                self.assertTrue(caps['ksmZeroPages'])
                self.assertFalse(caps['zram'])
                self.assertFalse(caps['writeback'])
                self.assertEqual(reason, caps['zramReasonCode'])
                self.assertEqual(driver, caps['zramDriver'])
                MemoryOptimizationPlugin._validate_requested_capabilities(
                    {'policy': {'ksm': {'mode': 'Active'}}}, caps)
                with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_HOST_CAPABILITY:zram'):
                    MemoryOptimizationPlugin._validate_requested_capabilities(
                        {'policy': {'zram': {'enabled': True}}}, caps)

    def test_alinux_qualified_driver_still_requires_service_qualification(self):
        driver = {'supported': True, 'reasonCode': 'SUPPORTED'}
        caps = self.discover_alinux(driver, service_supported=False)
        self.assertFalse(caps['zram'])
        self.assertFalse(caps['writeback'])
        self.assertEqual('RECLAIM_UNSUPPORTED', caps['zramReasonCode'])
        caps = self.discover_alinux(driver)
        self.assertTrue(caps['zram'])
        self.assertTrue(caps['writeback'])

    def test_alinux_driver_unknown_or_non_boolean_cannot_grant_support(self):
        for driver in ({}, {'supported': 'true'}, {'supported': 1}):
            with self.subTest(driver=driver):
                caps = self.discover_alinux(driver)
                self.assertFalse(caps['zram'])
                self.assertEqual('ZRAM_DRIVER_UNKNOWN', caps['zramReasonCode'])

    def test_non_alinux_does_not_consult_independent_kmod_profile(self):
        with patch.object(module.zram_driver, 'inspect', side_effect=AssertionError('Alinux only')):
            caps = self.discover(self.response())
        self.assertTrue(caps['zram'])
        self.assertNotIn('zramDriver', caps)

    def test_preview_rejects_unsupported_service_before_capacity_read(self):
        plugin = MemoryOptimizationPlugin(service_call=lambda *args: self.fail('must not read capacity'))
        plugin.configure({'hostUuid': 'host-1'})
        with patch.object(plugin, 'discover_capabilities', return_value={
                'supported': True, 'ksm': True, 'zram': False, 'zramReasonCode': 'UNSUPPORTED_RECLAIM_KERNEL'}):
            result = json.loads(plugin.preview({'body': json.dumps({'hostUuid': 'host-1', 'operationUuid': 'preflight-1'})}))
        self.assertFalse(result['success'])
        self.assertIn('UNSUPPORTED_RECLAIM_KERNEL', result['reason'])
