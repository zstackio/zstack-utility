from unittest.mock import patch

from zstacklib.utils import hugepages
from kvmagent.plugins import zbs_vhost_target as t
from kvmagent.plugins import zbs_storage_plugin


class TestEnsure2mHugetlbfsMount:
    def test_reuses_existing_default_hugepages_when_it_is_2mb(self):
        with patch.object(t.bash, 'bash_o', return_value="/dev/hugepages rw,pagesize=2M\n"), \
             patch.object(t.bash, 'bash_errorout') as errorout:
            assert t.ensure_2m_hugetlbfs_mount() == "/dev/hugepages"
            errorout.assert_not_called()

    def test_mounts_2mb_hugetlbfs_when_absent(self):
        with patch.object(t.bash, 'bash_o', return_value=""), \
             patch('os.path.exists', return_value=False), \
             patch('os.makedirs') as makedirs, \
             patch.object(t.bash, 'bash_r', return_value=1), \
             patch.object(t.bash, 'bash_errorout') as errorout:
            assert t.ensure_2m_hugetlbfs_mount() == t.DEFAULT_VHOST_TARGET_HUGEPAGE_DIR
            makedirs.assert_called_once_with(t.DEFAULT_VHOST_TARGET_HUGEPAGE_DIR)
            assert "pagesize=2M" in errorout.call_args[0][0]

    def test_reuses_existing_2mb_hugetlbfs_mount(self):
        with patch.object(t.bash, 'bash_o', return_value=""), \
             patch('os.path.exists', return_value=True), \
             patch.object(t.bash, 'bash_r', return_value=0), \
             patch.object(t.bash, 'bash_errorout') as errorout:
            assert t.ensure_2m_hugetlbfs_mount("/dev/hugepages2m") == "/dev/hugepages2m"
            errorout.assert_not_called()



def test_prepare_endpoint_is_retired():
    with patch.object(zbs_storage_plugin.kvmagent, 'get_http_server') as server:
        zbs_storage_plugin.ZbsStoragePlugin().start()
        paths = [call.args[0] for call in server.return_value.register_async_uri.call_args_list]
        assert '/zbs/primarystorage/vhost/target/prepareenv' not in paths


def test_reclaim_waits_for_target_startup_lock():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    started = Event()
    entered = Event()

    def reclaim():
        started.set()
        t.reclaim_hugepages()

    with patch.object(hugepages, 'reclaim_hugepages', side_effect=lambda slack: entered.set()), \
         ThreadPoolExecutor(max_workers=1) as executor:
        with t._TARGET_LOCK:
            future = executor.submit(reclaim)
            assert started.wait(1)
            assert not entered.wait(0.05)
        future.result(timeout=1)
        assert entered.is_set()
