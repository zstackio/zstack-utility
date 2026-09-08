import pytest
from unittest.mock import patch

from zstacklib.utils import shell
from zstacklib.utils import hugepages as t

HP = t.HUGEPAGE_SIZE_BYTES


class TestMemToPages:
    def test_exact_multiple(self):
        assert t.mem_to_pages(300 * 1024 * 1024) == 150

    def test_rounds_up_partial_page(self):
        assert t.mem_to_pages(HP + 1) == 2

    def test_zero(self):
        assert t.mem_to_pages(0) == 0

    @pytest.mark.parametrize('page_size', [2 * 1024 ** 2, 512 * 1024 ** 2, 1024 ** 3])
    def test_rounds_up_using_selected_page_size(self, page_size):
        assert t.mem_to_pages(page_size + 1, page_size) == 2



class TestReadHugepageFree:
    # regression guard for the aarch64 bug: free count MUST come from the 2MB pool's own
    # sysfs, never /proc/meminfo (which reports only the kernel default size, 512MB on ARM64).
    def test_reads_pool_sysfs_not_meminfo(self):
        with patch('os.path.exists', return_value=True), \
             patch.object(shell, 'call', return_value="100\n") as bo:
            assert t._read_hugepage_free() == 100
            called = " ".join(str(c) for c in bo.call_args_list)
            assert t.HUGEPAGE_FREE_PATH in called
            assert "meminfo" not in called

    def test_free_path_targets_2mb_pool(self):
        assert t.HUGEPAGE_FREE_PATH == t.HUGEPAGE_DIR + "/free_hugepages"
        assert "hugepages-2048kB" in t.HUGEPAGE_FREE_PATH

    def test_raises_when_pool_sysfs_absent(self):
        with patch('os.path.exists', return_value=False):
            with pytest.raises(Exception):
                t._read_hugepage_free()



class TestEnsureFreeHugepages:
    def test_noop_when_free_sufficient(self):
        with patch.object(t, '_read_hugepage_nr', return_value=768), \
             patch.object(t, '_read_hugepage_free', return_value=200), \
             patch.object(shell, 'call') as bo:
            t.ensure_free_hugepages(150)
            assert not any('nr_hugepages' in str(c) for c in bo.call_args_list)

    def test_grows_total_by_deficit(self):
        reads = {'free': [71, 150]}
        with patch.object(t, '_read_hugepage_nr', return_value=256), \
             patch.object(t, '_read_hugepage_free', side_effect=reads['free']), \
             patch.object(shell, 'call') as bo:
            t.ensure_free_hugepages(150)
            bo.assert_called_once_with('echo 335 > %s' % t.HUGEPAGE_NR_PATH)

    def test_raises_when_cannot_satisfy(self):
        with patch.object(t, '_read_hugepage_nr', return_value=256), \
             patch.object(t, '_read_hugepage_free', side_effect=[71, 90]), \
             patch.object(shell, 'call'):
            with pytest.raises(Exception):
                t.ensure_free_hugepages(150)



class TestReclaimHugepages:
    def test_shrinks_to_used_plus_slack(self):
        with patch.object(t, '_read_hugepage_nr', return_value=768), \
             patch.object(t, '_read_hugepage_free', return_value=433), \
             patch.object(shell, 'call') as bo:
            t.reclaim_hugepages(slack=0)
            bo.assert_called_once_with('echo 335 > %s' % t.HUGEPAGE_NR_PATH)

    def test_noop_when_nothing_free_to_reclaim(self):
        with patch.object(t, '_read_hugepage_nr', return_value=335), \
             patch.object(t, '_read_hugepage_free', return_value=0), \
             patch.object(shell, 'call') as bo:
            t.reclaim_hugepages(slack=0)
            assert not any('nr_hugepages' in str(c) for c in bo.call_args_list)



@pytest.mark.parametrize('operation,args', [(t.ensure_free_hugepages, (1,)), (t.reclaim_hugepages, ())])
def test_pool_operations_share_lock(operation, args):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    started = Event()
    read = Event()

    def invoke():
        started.set()
        operation(*args)

    def read_free(*args):
        read.set()
        return 1

    with patch.object(t, '_read_hugepage_free', side_effect=read_free), \
         patch.object(t, '_read_hugepage_nr', return_value=1), patch.object(shell, 'call'), \
         ThreadPoolExecutor(max_workers=1) as executor:
        with t._HUGEPAGE_LOCK:
            future = executor.submit(invoke)
            assert started.wait(1)
            assert not read.wait(0.05)
        future.result(timeout=1)
        assert read.is_set()


@pytest.mark.parametrize('mounts,sizes,expected', [
    ('none /huge1g hugetlbfs rw 0 0\nnone /huge2m hugetlbfs rw 0 0\n',
     {'/huge1g': 1024 ** 3, '/huge2m': HP}, HP),
    ('none /huge1g hugetlbfs rw 0 0\nnone /huge32m hugetlbfs rw 0 0\n',
     {'/huge1g': 1024 ** 3, '/huge32m': 32 * 1024 ** 2}, 1024 ** 3),
    ('none /huge32m hugetlbfs rw 0 0\nnone /huge1g hugetlbfs rw 0 0\n',
     {'/huge1g': 1024 ** 3, '/huge32m': 32 * 1024 ** 2}, 32 * 1024 ** 2),
    ('none /tmp tmpfs rw 0 0\nnone /huge1g hugetlbfs rw 0 0\n', {'/huge1g': 1024 ** 3}, 1024 ** 3),
    ('none /tmp tmpfs rw 0 0\n', {}, None),
    ('', {}, None),
    ('none /huge\\040pages hugetlbfs rw 0 0\n', {'/huge pages': 1024 ** 3}, 1024 ** 3),
])
def test_default_page_size_follows_libvirt_mount_selection(mounts, sizes, expected):
    from types import SimpleNamespace
    from unittest.mock import mock_open

    def stat(path):
        return SimpleNamespace(f_bsize=sizes[path])

    with patch.object(t, 'read_file', return_value='Hugepagesize: 2048 kB\n'), \
         patch('builtins.open', mock_open(read_data=mounts)), patch.object(t.os, 'statvfs', side_effect=stat):
        if expected is None:
            with pytest.raises(RuntimeError, match='hugetlbfs'):
                t.get_default_page_size()
        else:
            assert t.get_default_page_size() == expected


def test_unreadable_mount_does_not_select_another_pool():
    from unittest.mock import mock_open

    mounts = 'none /missing hugetlbfs rw 0 0\nnone /huge2m hugetlbfs rw 0 0\n'
    with patch.object(t, 'read_file', return_value='Hugepagesize: 2048 kB\n'), \
         patch('builtins.open', mock_open(read_data=mounts)), \
         patch.object(t.os, 'statvfs', side_effect=OSError('mount disappeared')):
        with pytest.raises(OSError, match='mount disappeared'):
            t.get_default_page_size()


@pytest.mark.parametrize('read', [t._read_hugepage_nr, t._read_hugepage_free])
def test_counter_read_failure_is_not_treated_as_zero(read):
    with patch.object(t.os.path, 'exists', return_value=True), \
         patch.object(shell, 'call', side_effect=RuntimeError('permission denied')):
        with pytest.raises(RuntimeError, match='permission denied'):
            read()


def test_failed_growth_command_is_not_masked_by_later_free_pages():
    with patch.object(t, '_read_hugepage_nr', return_value=256), \
         patch.object(t, '_read_hugepage_free', side_effect=[71, 150]) as free, \
         patch.object(shell, 'call', side_effect=RuntimeError('permission denied')):
        with pytest.raises(RuntimeError, match='permission denied'):
            t.ensure_free_hugepages(150)
    assert free.call_count == 1


def test_reclaim_command_failure_is_reported():
    with patch.object(t, '_read_hugepage_nr', return_value=768), \
         patch.object(t, '_read_hugepage_free', return_value=433), \
         patch.object(shell, 'call', side_effect=RuntimeError('permission denied')):
        with pytest.raises(RuntimeError, match='permission denied'):
            t.reclaim_hugepages()


@pytest.mark.parametrize('page_size_kib', [2048, 32768, 524288, 1048576])
def test_reclaim_reads_and_writes_selected_pool(page_size_kib):
    from unittest.mock import call

    pool = '/sys/kernel/mm/hugepages/hugepages-%skB' % page_size_kib
    with patch.object(t.os.path, 'exists', return_value=True), \
         patch.object(shell, 'call', side_effect=['433\n', '768\n', '']) as run:
        t.reclaim_hugepages(3, page_size=page_size_kib * 1024)
    assert run.call_args_list == [call('cat %s/free_hugepages' % pool), call('cat %s/nr_hugepages' % pool),
                                  call('echo 338 > %s/nr_hugepages' % pool)]


@pytest.mark.parametrize('meminfo', ['', 'Hugepagesize: 0 kB\n', 'Hugepagesize: invalid kB\n'])
def test_default_page_size_rejects_invalid_meminfo(meminfo):
    with patch.object(t, 'read_file', return_value=meminfo):
        with pytest.raises(ValueError):
            t.get_default_page_size()


@pytest.mark.parametrize('reader', ['read_file', 'get_mounts'])
def test_default_page_size_preserves_read_error(reader):
    error = OSError('permission denied')
    with patch.object(t, 'read_file', return_value='Hugepagesize: 2048 kB\n'), \
         patch.object(t, reader, side_effect=error):
        with pytest.raises(OSError) as exc:
            t.get_default_page_size()
    assert exc.value is error
