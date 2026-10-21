import pytest

from zstacklib.utils import zram_driver


KERNEL = '6.6.104-006.1.pro.ali6000.alnx4.x86_64'
MODULE = '/lib/modules/%s/updates/zstack-zram/zram.ko' % KERNEL


def _observe_driver(monkeypatch, *, filename=MODULE, disk_version='2.0.0',
                    disk_srcversion='NEWBUILD', loaded_version='2.0.0',
                    loaded_srcversion='NEWBUILD', package_release='1.kernel',
                    layout=('schema 2\npage_size 4096\nslot_entry_bytes 32\n'
                            'owner_entry_bytes 64\npreallocated_metadata_bytes 4096\n'),
                    missing_interfaces=()):
    reads = {
        '/etc/os-release': 'ID=alinux\nVERSION_ID="4.0"\n',
        '/sys/module/zram/version': loaded_version,
        '/sys/module/zram/srcversion': loaded_srcversion,
        '/sys/block/zram0/accounting_layout': layout,
    }
    commands = []

    def read(path):
        return reads[path]

    def run(argv):
        commands.append(argv)
        if argv[:3] == ['modinfo', '-k', KERNEL]:
            field = argv[4]
            return {'filename': filename, 'version': disk_version,
                    'vermagic': KERNEL + ' SMP mod_unload',
                    'srcversion': disk_srcversion}[field]
        if argv[:2] == ['rpm', '-qf']:
            return '\n'.join(['kmod-zstack-zram', '(none)', '2.0.0',
                               package_release, 'x86_64'])
        if argv[:2] == ['rpm', '-V']:
            return ''
        raise AssertionError('unexpected command: %r' % (argv,))

    def exists(path):
        if path in ('/sys/module/zram', '/sys/block/zram0/disksize'):
            return True
        if path.startswith('/sys/block/zram0/'):
            return path.rsplit('/', 1)[-1] not in missing_interfaces
        return False

    monkeypatch.setattr(zram_driver, '_read', read)
    monkeypatch.setattr(zram_driver, '_run', run)
    monkeypatch.setattr(zram_driver.os.path, 'exists', exists)
    monkeypatch.setattr(zram_driver.os.path, 'realpath', lambda path: path)
    result = zram_driver.inspect(kernel=KERNEL, architecture='x86_64')
    return result, commands


def test_compatible_new_kernel_module_build_identity_is_accepted(monkeypatch):
    result, commands = _observe_driver(monkeypatch)

    assert result['supported'] is True
    assert result['reasonCode'] == 'SUPPORTED'
    assert result['installationPackage'] == (
        'kmod-zstack-zram-0:2.0.0-1.kernel.x86_64')
    assert result['accountingSupported'] is True
    assert result['writebackSupported'] is True
    assert not any('weak-updates' in str(command) for command in commands)


def test_disk_loaded_module_identity_mismatch_requires_maintenance(monkeypatch):
    result, _ = _observe_driver(monkeypatch, loaded_srcversion='OLD-BUILD')

    assert result['supported'] is False
    assert result['maintenanceRequired'] is True
    assert result['reasonCode'] == 'ZRAM_DRIVER_UPDATE_REQUIRES_MAINTENANCE'


def test_weak_updates_module_is_rejected_for_current_kernel(monkeypatch):
    result, _ = _observe_driver(
        monkeypatch,
        filename='/lib/modules/%s/weak-updates/zram.ko' % KERNEL)

    assert result['supported'] is False
    assert result['reasonCode'] == 'ZRAM_DRIVER_DISK_PATH_MISMATCH'


def test_unknown_accounting_schema_does_not_claim_accounting_support(monkeypatch):
    result, _ = _observe_driver(monkeypatch, layout='schema 99\npage_size 4096\n')

    assert result['supported'] is True
    assert result['accountingSupported'] is False


@pytest.mark.parametrize('layout', [
    'schema 2\npage_size 4096\nowner_entry_bytes 64\npreallocated_metadata_bytes 4096\n',
    'schema 2\npage_size 4096\nslot_entry_bytes 32\npreallocated_metadata_bytes 4096\n',
    'schema 2\npage_size 4096\nslot_entry_bytes 32\nowner_entry_bytes 64\n',
    'schema 2\npage_size 4096\nslot_entry_bytes 0\nowner_entry_bytes 64\npreallocated_metadata_bytes 4096\n',
    'schema 2\npage_size 4096\nslot_entry_bytes 32\nowner_entry_bytes 0\npreallocated_metadata_bytes 4096\n',
    'schema 2\npage_size 4096\nslot_entry_bytes 32\nowner_entry_bytes 64\npreallocated_metadata_bytes 0\n',
    'schema 2\npage_size 4096\nslot_entry_bytes invalid\nowner_entry_bytes 64\npreallocated_metadata_bytes 4096\n',
    'schema +2\npage_size 4096\nslot_entry_bytes 32\nowner_entry_bytes 64\npreallocated_metadata_bytes 4096\n',
])
def test_invalid_accounting_layout_does_not_disable_base_driver(monkeypatch, layout):
    result, _ = _observe_driver(monkeypatch, layout=layout)

    assert result['supported'] is True
    assert result['accountingSupported'] is False


def test_missing_writeback_interfaces_do_not_disable_base_driver(monkeypatch):
    result, _ = _observe_driver(monkeypatch, missing_interfaces=('writeback',))

    assert result['supported'] is True
    assert result['accountingSupported'] is True
    assert result['writebackSupported'] is False
