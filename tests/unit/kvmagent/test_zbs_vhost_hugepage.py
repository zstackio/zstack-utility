import pytest
from unittest.mock import patch

from zstacklib.utils import http, jsonobject, hugepages
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



class TestPrepareVhostTargetEnv:
    def test_ensures_2m_mount_and_free_hugepages(self):
        body = '{"hugepageNr":1024}'
        req = {http.REQUEST_BODY: body}
        with patch.object(t, 'ensure_docker'), \
             patch.object(t, 'ensure_2m_hugetlbfs_mount') as ensure_mount, \
             patch.object(hugepages, 'ensure_free_hugepages') as ensure_free:
            out = zbs_storage_plugin.ZbsStoragePlugin().prepare_vhost_target_env(req)
            rsp = jsonobject.loads(out)
            assert rsp.success is True
            ensure_mount.assert_called_once_with()
            ensure_free.assert_called_once_with(1024)



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
