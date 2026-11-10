import subprocess
import unittest
import xml.etree.ElementTree as etree
from unittest import mock

from kvmagent.plugins import ramfb


QEMU_NS = 'http://libvirt.org/schemas/domain/qemu/1.0'


def domain(values=(), ramfb_video=True, raw=False, emulator='/qemu-under-test'):
    root = etree.Element('domain')
    if raw:
        root.set('xmlns:qemu', QEMU_NS)
    devices = etree.SubElement(root, 'devices')
    if emulator:
        etree.SubElement(devices, 'emulator').text = emulator
    video = etree.SubElement(devices, 'video')
    etree.SubElement(video, 'model', type='ramfb' if ramfb_video else 'virtio')
    etree.SubElement(video, 'alias', name='video-original')
    if values:
        prefix = 'qemu:' if raw else '{%s}' % QEMU_NS
        commandline = etree.SubElement(root, prefix + 'commandline')
        for value in values:
            etree.SubElement(commandline, prefix + 'arg', value=value)
        etree.SubElement(commandline, prefix + 'env', name='KEEP_ENV', value='present')
    return root


def arguments(root):
    parsed = etree.fromstring(etree.tostring(root))
    return [arg.get('value') for node in parsed.findall('{%s}commandline' % QEMU_NS)
            for arg in node.findall('{%s}arg' % QEMU_NS)]


class TestRamfb(unittest.TestCase):
    @mock.patch.object(ramfb.subprocess, 'run')
    def test_capable_binary_enables_actual_ramfb_and_keeps_other_arguments(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '', 'ramfb options:\n  x-migrate=<bool>\n')
        root = domain(['-qmp', 'unix:current.sock', '-global', 'mch.extended-tseg-mbytes=288'])
        self.assertTrue(ramfb.enable_migration(root))
        self.assertEqual(arguments(root), ['-qmp', 'unix:current.sock', '-global',
                         'mch.extended-tseg-mbytes=288', '-global', 'ramfb.x-migrate=on'])
        self.assertEqual(run.call_args[0][0], ['/qemu-under-test', '-device', 'ramfb,help'])
        self.assertEqual(root.find('devices/video/alias').get('name'), 'video-original')
        self.assertIsNotNone(root.find('.//{%s}env' % QEMU_NS))

    @mock.patch.object(ramfb.subprocess, 'run')
    def test_old_binary_keeps_the_legacy_xml(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, 'There are no options for ramfb.\n', '')
        root = domain(['-qmp', 'unix:current.sock']); before = etree.tostring(root)
        self.assertFalse(ramfb.enable_migration(root))
        self.assertEqual(etree.tostring(root), before)

    @mock.patch.object(ramfb.subprocess, 'run')
    def test_failed_help_is_not_a_capability(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, '  x-migrate=<bool>\n', '')
        self.assertFalse(ramfb.supports_migration('/broken-qemu'))

    @mock.patch.object(ramfb.subprocess, 'run')
    def test_probe_errors_preserve_legacy_behavior(self, run):
        for error in [OSError('missing binary'), subprocess.TimeoutExpired(['qemu'], 5)]:
            with self.subTest(error=type(error).__name__):
                run.side_effect = error
                self.assertFalse(ramfb.supports_migration('/unavailable-qemu'))

    @mock.patch.object(ramfb.subprocess, 'run')
    def test_other_video_does_not_probe_or_change_xml(self, run):
        root = domain(ramfb_video=False); before = etree.tostring(root)
        self.assertFalse(ramfb.enable_migration(root))
        self.assertEqual(etree.tostring(root), before); run.assert_not_called()

    @mock.patch.object(ramfb.subprocess, 'run')
    def test_missing_emulator_does_not_guess_another_binary(self, run):
        root = domain(emulator=None); before = etree.tostring(root)
        self.assertFalse(ramfb.enable_migration(root))
        self.assertEqual(etree.tostring(root), before); run.assert_not_called()

    @mock.patch.object(ramfb.subprocess, 'run')
    def test_explicit_existing_off_is_preserved(self, run):
        root = domain(['-global', 'ramfb.x-migrate=off'])
        self.assertFalse(ramfb.enable_migration(root))
        self.assertEqual(arguments(root), ['-global', 'ramfb.x-migrate=off'])
        run.assert_not_called()

    @mock.patch.object(ramfb.subprocess, 'run')
    def test_raw_builder_xml_is_valid_and_activation_is_idempotent(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '  x-migrate=<bool>\n', '')
        for values in [(), ('-qmp', 'unix:current.sock')]:
            with self.subTest(values=values):
                root = domain(values, raw=True)
                self.assertTrue(ramfb.enable_migration(root))
                self.assertFalse(ramfb.enable_migration(root))
                self.assertEqual(arguments(root).count('ramfb.x-migrate=on'), 1)
        self.assertEqual(run.call_count, 2)

    def test_legacy_snapshot_removes_new_flag_and_keeps_current_qmp(self):
        current = domain(['-qmp', 'unix:current.sock', '-global', 'other.setting=on',
                          '-global', 'ramfb.x-migrate=on'])
        saved = domain(['-qmp', 'unix:old-host.sock'])
        ramfb.restore_migration(current, saved)
        self.assertEqual(arguments(current), ['-qmp', 'unix:current.sock',
                                              '-global', 'other.setting=on'])
        self.assertIsNotNone(current.find('.//{%s}env' % QEMU_NS))

    def test_enabled_snapshot_restores_flag_without_old_host_arguments(self):
        current = domain(['-qmp', 'unix:current.sock'])
        saved = domain(['-qmp', 'unix:old-host.sock', '-global', 'ramfb.x-migrate=on'])
        ramfb.restore_migration(current, saved)
        self.assertEqual(arguments(current), ['-qmp', 'unix:current.sock',
                                              '-global', 'ramfb.x-migrate=on'])

    def test_explicit_saved_off_replaces_new_on(self):
        current = domain(['-global', 'ramfb.x-migrate=on'])
        saved = domain(['-global', 'ramfb.x-migrate=off'])
        ramfb.restore_migration(current, saved)
        self.assertEqual(arguments(current), ['-global', 'ramfb.x-migrate=off'])

    def test_pre_ramfb_snapshot_has_no_migration_flag(self):
        current = domain(['-global', 'ramfb.x-migrate=on'])
        saved = domain(ramfb_video=False)
        ramfb.restore_migration(current, saved)
        self.assertEqual(arguments(current), [])

    def test_source_override_order_and_unrelated_current_globals_survive(self):
        current = domain(['-global', 'unrelated.one=on', '-global', 'ramfb.x-migrate=off',
                          '-global', 'unrelated.two=off'])
        saved = domain(['-global', 'ramfb.x-migrate=on', '-global', 'ramfb.x-migrate=off'])
        ramfb.restore_migration(current, saved)
        self.assertEqual(arguments(current), ['-global', 'unrelated.one=on',
                         '-global', 'unrelated.two=off', '-global', 'ramfb.x-migrate=on',
                         '-global', 'ramfb.x-migrate=off'])


if __name__ == '__main__':
    unittest.main()
