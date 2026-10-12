import unittest

from zstacklib.utils import zram_driver as module


KERNEL = '6.6.102-005.3.pro.ali6000.alnx4.x86_64'
MODULE = '/lib/modules/' + KERNEL + '/updates/zstack-zram/zram.ko'
SOURCE_VERSION = '28E0660C8D6A8636B59CF3C'


class ZramDriverTest(unittest.TestCase):
    def setUp(self):
        self.reads = {
            '/etc/os-release': 'ID=alinux\nVERSION_ID="4.0"\n',
            '/sys/module/zram/version': '5.5.48.1',
            '/sys/module/zram/srcversion': SOURCE_VERSION,
            '/sys/block/zram0/accounting_layout': 'schema 2\npage_size 4096\n',
        }
        self.disk = {'filename': MODULE, 'version': '5.5.48.1',
                     'vermagic': KERNEL + ' SMP preempt mod_unload modversions ',
                     'srcversion': SOURCE_VERSION}
        self.package = 'kmod-zstack-zram\n5.5.48.1\n1.alnx4\nx86_64'
        self.absent = set()
        self.calls = []

    def read(self, path):
        if path not in self.reads:
            raise FileNotFoundError(path)
        return self.reads[path]

    def command(self, argv):
        self.calls.append(argv)
        if argv[:1] == ['modinfo']:
            return self.disk[argv[4]]
        if argv[:2] == ['rpm', '-qf']:
            return self.package
        if argv == ['rpm', '-V', 'kmod-zstack-zram']:
            return ''
        self.fail('Unexpected or mutating command: %r' % argv)

    def inspect(self, **updates):
        kwargs = dict(kernel=KERNEL, architecture='x86_64', read=self.read,
                      run=self.command, exists=lambda path: path not in self.absent,
                      realpath=lambda path: path.replace('/lib/', '/usr/lib/', 1))
        kwargs.update(updates)
        return module.inspect(**kwargs)

    def test_matching_loaded_driver_is_qualified_without_mutation(self):
        for unused in range(2):
            state = self.inspect()
            self.assertTrue(state['supported'])
            self.assertEqual('SUPPORTED', state['reasonCode'])
            self.assertFalse(state['maintenanceRequired'])
            self.assertFalse(state['safeToLoad'])
        self.assertTrue(all(call[0] in ('modinfo', 'rpm') for call in self.calls))

    def test_matching_disk_not_loaded_is_not_runtime_support(self):
        self.absent.add('/sys/module/zram')
        state = self.inspect()
        self.assertFalse(state['supported'])
        self.assertTrue(state['safeToLoad'])
        self.assertEqual('ZRAM_DRIVER_NOT_LOADED', state['reasonCode'])

    def test_new_disk_old_loaded_requires_maintenance_even_when_refcount_zero(self):
        self.reads['/sys/module/zram/version'] = '5.5.38.1'
        self.reads['/sys/module/zram/refcnt'] = '0'
        state = self.inspect()
        self.assertFalse(state['supported'])
        self.assertTrue(state['maintenanceRequired'])
        self.assertFalse(state['safeToLoad'])
        self.assertEqual('5.5.38.1', state['loaded']['version'])
        self.assertEqual('5.5.48.1', state['disk']['version'])

    def test_missing_loaded_identity_is_not_guessed_from_disk(self):
        for name in ('version', 'srcversion'):
            with self.subTest(name=name):
                original = self.reads.pop('/sys/module/zram/' + name)
                state = self.inspect()
                self.assertFalse(state['supported'])
                self.assertTrue(state['maintenanceRequired'])
                self.assertEqual('ZRAM_DRIVER_LOADED_IDENTITY_MISSING', state['reasonCode'])
                self.reads['/sys/module/zram/' + name] = original

    def test_same_version_different_loaded_build_is_not_qualified(self):
        self.reads['/sys/module/zram/srcversion'] = 'OTHER'
        self.assertEqual('ZRAM_DRIVER_UPDATE_REQUIRES_MAINTENANCE', self.inspect()['reasonCode'])

    def test_same_unknown_build_on_disk_and_in_memory_is_not_a_release(self):
        self.disk['srcversion'] = 'OTHER'
        self.reads['/sys/module/zram/srcversion'] = 'OTHER'
        self.assertEqual('ZRAM_DRIVER_DISK_BUILD_MISMATCH', self.inspect()['reasonCode'])

    def test_wrong_disk_version_vermagic_srcversion_and_path_fail_closed(self):
        for field, value in [('version', '5.5.48.10'), ('vermagic', 'other SMP'),
                             ('srcversion', ''), ('filename', '/lib/modules/other/zram.ko'),
                             ('filename', '/lib/modules/' + KERNEL + '/weak-updates/zram.ko')]:
            with self.subTest(field=field, value=value):
                original = self.disk[field]
                self.disk[field] = value
                state = self.inspect()
                self.assertFalse(state['supported'])
                self.assertFalse(state['safeToLoad'])
                self.disk[field] = original

    def test_wrong_package_and_changed_bytes_cannot_qualify(self):
        self.package = self.package.replace('1.alnx4', '2.alnx4')
        self.assertEqual('ZRAM_DRIVER_PACKAGE_MISMATCH', self.inspect()['reasonCode'])
        self.package = self.package.replace('2.alnx4', '1.alnx4')
        def changed(argv):
            return 'S.5....T. ' + MODULE if argv[:2] == ['rpm', '-V'] else self.command(argv)
        self.assertEqual('ZRAM_DRIVER_PACKAGE_CONTENT_MISMATCH', self.inspect(run=changed)['reasonCode'])

    def test_missing_abi_and_bad_schema_never_grant_support(self):
        self.absent.add('/sys/block/zram0/writeback')
        state = self.inspect()
        self.assertEqual(['writeback'], state['missingInterfaces'])
        self.assertEqual('ZRAM_DRIVER_ABI_INCOMPLETE', state['reasonCode'])
        self.absent.clear()
        self.reads['/sys/block/zram0/accounting_layout'] = 'schema 1\npage_size 4096'
        self.assertEqual('ZRAM_DRIVER_ABI_MISMATCH', self.inspect()['reasonCode'])
        self.reads['/sys/block/zram0/accounting_layout'] = 'schema 2\nschema 2\npage_size 4096'
        self.assertEqual('ZRAM_DRIVER_OBSERVATION_FAILED', self.inspect()['reasonCode'])

    def test_unknown_kernel_arch_and_os_do_not_run_package_commands(self):
        for kwargs in ({'kernel': '6.6.102-unknown'}, {'architecture': 'aarch64'},
                       {'release': 'h84r'}, {'release': 'kylinV10'}):
            with self.subTest(kwargs=kwargs):
                state = self.inspect(**kwargs)
                self.assertFalse(state['supported'])
                self.assertEqual([], self.calls)

    def test_command_failure_preserves_loaded_facts_and_is_not_success(self):
        def failed(argv):
            raise module.subprocess.CalledProcessError(1, argv)
        state = self.inspect(run=failed)
        self.assertFalse(state['supported'])
        self.assertEqual('5.5.48.1', state['loaded']['version'])
        self.assertEqual('ZRAM_DRIVER_OBSERVATION_FAILED', state['reasonCode'])


if __name__ == '__main__':
    unittest.main()
