from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from kvmagent.plugins import vm_plugin as t
from zstacklib.utils import shell
from zstacklib.utils import hugepages as h
from zstacklib.system.filesystem import MountInfo


@pytest.fixture(autouse=True)
def mounted_hugepages():
    mounts = [MountInfo('none', '/dev/hugepages', 'hugetlbfs', 'rw')]
    with patch.object(h, 'get_mounts', return_value=mounts), \
         patch.object(h.os, 'statvfs', return_value=SimpleNamespace(f_bsize=2 * 1024 ** 2)) as stat:
        yield stat


@pytest.fixture
def startup():
    cmd = SimpleNamespace(vmInstanceUuid='vm-uuid', vmName='vm', memory=64 * 1024 ** 3, useHugePage=True,
                          useNuma=True, memorySnapshotPath=None, addons=None, timeout=60, createPaused=False, nics=[])
    plugin = t.VmPlugin.__new__(t.VmPlugin)
    vm = MagicMock(domain_xml='<domain/>')
    with patch.object(t.libvirt, 'libvirtError', type('LibvirtError', (Exception,), {})), \
         patch.object(t.os.path, 'exists', return_value=False), \
         patch.object(t, 'get_vm_by_uuid_no_retry', return_value=None) as lookup, \
         patch.object(t.Vm, 'from_StartVmCmd', return_value=vm), \
         patch.object(plugin, '_prepare_ebtables_for_mocbr'):
        yield plugin, cmd, vm, lookup


@pytest.mark.parametrize('page_size_kib', [2048, 32768, 524288, 1048576])
def test_start_uses_command_memory_and_host_default_pool(startup, mounted_hugepages, page_size_kib):
    plugin, cmd, vm, _ = startup
    events = []
    page_size = page_size_kib * 1024
    mounted_hugepages.return_value.f_bsize = page_size

    def allocate(count, size):
        assert (count, size) == (cmd.memory // page_size, page_size)
        events.append('allocate')

    vm.start.side_effect = lambda *args: events.append('start')
    with patch.object(h, 'read_file', return_value='Hugepagesize: %s kB\n' % page_size_kib), \
         patch.object(h, 'ensure_free_hugepages', side_effect=allocate):
        plugin._start_vm(cmd)
    assert events == ['allocate', 'start']
    vm.start.assert_called_once_with(60, False, True)


def test_start_rounds_up_partial_page(startup):
    plugin, cmd, _, _ = startup
    cmd.memory = 2 * 1024 ** 2 + 1024
    with patch.object(h, 'read_file', return_value='Hugepagesize: 2048 kB\n'), \
         patch.object(h, 'ensure_free_hugepages') as allocate:
        plugin._start_vm(cmd)
    allocate.assert_called_once_with(2, 2 * 1024 ** 2)


def test_normal_memory_does_not_prepare_hugepages(startup):
    plugin, cmd, vm, _ = startup
    cmd.useHugePage = False
    with patch.object(h, 'read_file') as read, patch.object(h, 'ensure_free_hugepages') as allocate:
        plugin._start_vm(cmd)
    read.assert_not_called()
    allocate.assert_not_called()
    vm.start.assert_called_once()


def test_running_vm_does_not_prepare_hugepages_again(startup):
    plugin, cmd, vm, lookup = startup
    lookup.return_value = MagicMock(state=t.Vm.VM_STATE_RUNNING)
    with patch.object(h, 'ensure_free_hugepages') as allocate:
        plugin._start_vm(cmd)
    allocate.assert_not_called()
    vm.start.assert_not_called()


def test_rbd_numa_start_grows_pool_by_missing_pages(startup):
    plugin, cmd, vm, _ = startup
    with patch.object(h, 'read_file', return_value='Hugepagesize: 2048 kB\n'), \
         patch.object(h, '_read_hugepage_nr', return_value=51200), \
         patch.object(h, '_read_hugepage_free', side_effect=[8703, 32768]), \
         patch.object(shell, 'call') as write:
        plugin._start_vm(cmd)
    write.assert_called_once_with('echo 75265 > %s' % h.HUGEPAGE_NR_PATH)
    vm.start.assert_called_once()


def test_sufficient_pages_do_not_modify_host_memory(startup):
    plugin, cmd, _, _ = startup
    with patch.object(h, 'read_file', return_value='Hugepagesize: 2048 kB\n'), \
         patch.object(h, '_read_hugepage_free', return_value=32768), \
         patch.object(shell, 'call') as write:
        plugin._start_vm(cmd)
    write.assert_not_called()


def test_insufficient_growth_prevents_start(startup):
    plugin, cmd, vm, _ = startup
    with patch.object(h, 'read_file', return_value='Hugepagesize: 2048 kB\n'), \
         patch.object(h, '_read_hugepage_nr', return_value=51200), \
         patch.object(h, '_read_hugepage_free', side_effect=[8703, 9000]), \
         patch.object(shell, 'call'):
        with pytest.raises(Exception, match='failed to free 32768 hugepages, only 9000 free'):
            plugin._start_vm(cmd)
    vm.start.assert_not_called()


@pytest.mark.parametrize('meminfo', ['', 'Hugepagesize: 0 kB\n', 'Hugepagesize: invalid kB\n'])
def test_unknown_default_page_size_prevents_start(startup, meminfo):
    plugin, cmd, vm, _ = startup
    with patch.object(h, 'read_file', return_value=meminfo), patch.object(h, 'ensure_free_hugepages') as allocate:
        with pytest.raises(ValueError):
            plugin._start_vm(cmd)
    allocate.assert_not_called()
    vm.start.assert_not_called()


def test_memory_snapshot_restore_keeps_its_existing_path(startup):
    plugin, cmd, vm, _ = startup
    cmd.memorySnapshotPath = '/snapshot/memory'
    with patch.object(h, 'ensure_free_hugepages') as allocate:
        plugin._start_vm(cmd)
    allocate.assert_not_called()
    vm.restore.assert_called_once_with(cmd.memorySnapshotPath)
    vm.start.assert_not_called()


@pytest.mark.parametrize('page_size_kib', [2048, 32768, 524288, 1048576])
def test_start_grows_the_selected_sysfs_pool(startup, mounted_hugepages, page_size_kib):
    plugin, cmd, vm, _ = startup
    mounted_hugepages.return_value.f_bsize = page_size_kib * 1024
    pool = '/sys/kernel/mm/hugepages/hugepages-%skB' % page_size_kib
    required = cmd.memory // (page_size_kib * 1024)
    counters = {pool + '/nr_hugepages': '100', pool + '/free_hugepages': '1'}

    def run_command(command):
        if command.startswith('cat '):
            return counters[command[4:]]
        assert command == 'echo %d > %s/nr_hugepages' % (100 + required - 1, pool)
        counters[pool + '/free_hugepages'] = str(required)
        return ''

    with patch.object(h, 'read_file', return_value='Hugepagesize: %s kB\n' % page_size_kib), \
         patch.object(t.os.path, 'exists', side_effect=lambda path: path.startswith(pool)), \
         patch.object(shell, 'call', side_effect=run_command):
        plugin._start_vm(cmd)
    assert counters[pool + '/free_hugepages'] == str(required)
    vm.start.assert_called_once()


def test_start_uses_first_mount_when_default_size_is_not_mounted(startup, mounted_hugepages):
    plugin, cmd, vm, _ = startup
    mounted_hugepages.return_value.f_bsize = 1024 ** 3
    with patch.object(h, 'read_file', return_value='Hugepagesize: 2048 kB\n'), \
         patch.object(h, 'ensure_free_hugepages') as allocate:
        plugin._start_vm(cmd)
    allocate.assert_called_once_with(64, 1024 ** 3)
    vm.start.assert_called_once()


def test_no_hugetlbfs_mount_prevents_start(startup):
    plugin, cmd, vm, _ = startup
    with patch.object(h, 'get_mounts', return_value=[]), \
         patch.object(h, 'read_file', return_value='Hugepagesize: 2048 kB\n'), \
         patch.object(h, 'ensure_free_hugepages') as allocate:
        with pytest.raises(RuntimeError, match='hugetlbfs'):
            plugin._start_vm(cmd)
    allocate.assert_not_called()
    vm.start.assert_not_called()


def test_growth_command_failure_prevents_start(startup):
    plugin, cmd, vm, _ = startup
    with patch.object(h, 'read_file', return_value='Hugepagesize: 2048 kB\n'), \
         patch.object(h, '_read_hugepage_nr', return_value=51200), \
         patch.object(h, '_read_hugepage_free', side_effect=[8703, 32768]), \
         patch.object(shell, 'call', side_effect=RuntimeError('permission denied')):
        with pytest.raises(RuntimeError, match='permission denied'):
            plugin._start_vm(cmd)
    vm.start.assert_not_called()
