from __future__ import annotations

import errno
import importlib
import json
import sys
import pytest
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch, PropertyMock


# ---------------------------------------------------------------------------
# Import the ceph primary storage module with lock passthrough
# ---------------------------------------------------------------------------
try:
    # Ensure lock decorators are passthroughs before importing
    import tests.conftest  # noqa: F401

    from tests.conftest import passthrough_lock
    lock_mod = cast(object, importlib.import_module("zstacklib.utils.lock"))

    setattr(lock_mod, "lock", passthrough_lock)
    setattr(lock_mod, "file_lock", passthrough_lock)

    module = importlib.import_module("cephprimarystorage.cephagent")
    module = importlib.reload(module)
except (ImportError, ModuleNotFoundError) as e:
    pytest.skip(f"Cannot import cephprimarystorage: {e}", allow_module_level=True)


_REAL_CEPH_UTIL_PATH = Path(__file__).resolve().parents[3] / "zstacklib/zstacklib/utils/ceph.py"
_real_ceph_spec = importlib.util.spec_from_file_location("_real_zstacklib_utils_ceph", str(_REAL_CEPH_UTIL_PATH))
real_ceph_utils = importlib.util.module_from_spec(_real_ceph_spec)
_real_ceph_spec.loader.exec_module(real_ceph_utils)


def _make_req(body_dict=None):
    http = cast(object, importlib.import_module("zstacklib.utils.http"))
    body = json.dumps(body_dict or {})
    return {http.REQUEST_BODY: body, http.REQUEST_HEADER: {}}


def _load_rsp(result):
    return json.loads(result)


def _make_agent():
    """Create CephAgent via __new__ to skip __init__ side effects."""
    agent = module.CephAgent.__new__(module.CephAgent)
    agent.cluster = MagicMock()
    agent.ioctx = {}
    agent.op_lock = __import__("threading").Lock()
    agent.imagestore_client = MagicMock()
    return agent


def _mock_capacity(agent):
    """Mock _set_capacity_to_response to avoid shell calls."""
    agent._set_capacity_to_response = MagicMock()


def _mock_shell():
    shell_mod = sys.modules["zstacklib.utils.shell"]
    shell_mod.call = MagicMock(return_value="")
    shell_mod.run = MagicMock(return_value=0)
    shell_mod.check_run = MagicMock()
    return shell_mod


def _mock_ceph():
    ceph_mod = sys.modules["zstacklib.utils.ceph"]
    ceph_mod.get_fsid = MagicMock(return_value="fsid-001")
    ceph_mod.get_ceph_manufacturer = MagicMock(return_value="generic")
    ceph_mod.is_xsky = MagicMock(return_value=False)
    ceph_mod.is_sandstone = MagicMock(return_value=False)
    ceph_mod.support_defer_deleting = MagicMock(return_value=False)
    ceph_mod.get_pools_capacity = MagicMock(return_value=[])
    ceph_mod.find_rbd_trash = real_ceph_utils.find_rbd_trash
    ceph_mod.rbd_children = real_ceph_utils.rbd_children
    ceph_mod.rbd_trash_list = real_ceph_utils.rbd_trash_list
    ceph_mod.rbd_trash_rm = real_ceph_utils.rbd_trash_rm
    return ceph_mod


# ---------------------------------------------------------------------------
# echo
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryEcho:
    def test_echo_returns_empty_string(self):
        agent = _make_agent()
        result = agent.echo(_make_req())
        assert result == ""


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryConnect:
    def test_connect_reconnects_cluster(self):
        agent = _make_agent()
        _mock_capacity(agent)
        agent.reconnect_cluster = MagicMock()
        result = agent.connect(_make_req())
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        agent.reconnect_cluster.assert_called_once()


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryInit:
    def test_init_creates_missing_pools(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = _mock_shell()
        ceph_mod = _mock_ceph()
        shell_mod.call = MagicMock(return_value="existing-pool")

        result = agent.init(_make_req({
            "pools": [
                {"name": "existing-pool", "predefined": False},
                {"name": "new-pool", "predefined": False},
            ],
            "nocephx": True,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["fsid"] == "fsid-001"
        create_calls = [c for c in shell_mod.call.call_args_list
                        if "osd pool create" in str(c)]
        assert len(create_calls) == 1


# ---------------------------------------------------------------------------
# add_pool
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryAddPool:
    def test_add_pool_creates_new_pool(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = _mock_shell()
        _mock_ceph()
        shell_mod.call = MagicMock(return_value="other-pool\n")

        result = agent.add_pool(_make_req({
            "poolName": "new-pool",
            "isCreate": True,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True

    def test_add_pool_raises_on_missing_predefined(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = _mock_shell()
        _mock_ceph()
        shell_mod.call = MagicMock(return_value="other-pool\n")

        result = agent.add_pool(_make_req({
            "poolName": "not-exist",
            "isCreate": False,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is False


# ---------------------------------------------------------------------------
# check_pool
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCheckPool:
    def test_check_pool_success(self):
        agent = _make_agent()
        shell_mod = _mock_shell()
        shell_mod.call = MagicMock(return_value="pool-a pool-b")

        result = agent.check_pool(_make_req({
            "pools": [{"name": "pool-a"}],
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True

    def test_check_pool_missing_raises(self):
        agent = _make_agent()
        shell_mod = _mock_shell()
        shell_mod.call = MagicMock(return_value="pool-a")

        result = agent.check_pool(_make_req({
            "pools": [{"name": "pool-missing"}],
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is False


# ---------------------------------------------------------------------------
# delete_pool
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryDeletePool:
    def test_delete_pool_calls_shell(self):
        agent = _make_agent()
        shell_mod = _mock_shell()

        result = agent.delete_pool(_make_req({
            "poolNames": ["pool-1", "pool-2"],
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        delete_calls = [c for c in shell_mod.call.call_args_list
                        if "pool delete" in str(c)]
        assert len(delete_calls) == 2


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryPing:
    def test_ping_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        # bash_o is bound in module namespace via `from bash import *`
        module.bash_o = MagicMock(return_value='{"mons": [{"addr": "10.0.0.1:6789"}]}')
        module.bash_r = MagicMock(return_value=0)
        module.bash_roe = MagicMock(return_value=(0, "", ""))
        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.write_uuids = MagicMock()

        result = agent.ping(_make_req({
            "monAddr": "10.0.0.1",
            "monUuid": "mon-uuid-001",
            "testImagePath": "pool/test-heartbeat",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True

    def test_ping_mon_addr_changed(self):
        agent = _make_agent()
        _mock_capacity(agent)
        module.bash_o = MagicMock(return_value='{"mons": [{"addr": "10.0.0.2:6789"}]}')

        result = agent.ping(_make_req({
            "monAddr": "10.0.0.99",
            "monUuid": "mon-uuid-001",
            "testImagePath": "pool/test-heartbeat",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is False
        assert rsp["failure"] == "MonAddrChanged"


# ---------------------------------------------------------------------------
# get_facts
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryGetFacts:
    def test_get_facts_returns_mon_addr(self):
        agent = _make_agent()
        module.bash_o = MagicMock(return_value='{"mons": [{"addr": "10.0.0.1:6789/0"}]}')
        ceph_mod = _mock_ceph()
        iproute_mod = sys.modules["zstacklib.utils.iproute"]
        addr_obj = MagicMock()
        addr_obj.address = "192.168.1.10"
        addr_obj.ifname = "eth0"
        iproute_mod.query_addresses = MagicMock(return_value=[addr_obj])
        # get_mon_addr is imported at module level
        module.get_mon_addr = MagicMock(return_value="10.0.0.1:6789")

        result = agent.get_facts(_make_req({"monUuid": "mon-001"}))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["monAddr"] == "10.0.0.1:6789"
        assert rsp["fsid"] == "fsid-001"


# ---------------------------------------------------------------------------
# create (create empty volume)
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCreate:
    def test_create_volume_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        driver = MagicMock()
        rsp_obj = module.CreateEmptyVolumeRsp()
        rsp_obj.size = 1073741824
        driver.create_volume = MagicMock(return_value=rsp_obj)
        agent.get_driver = MagicMock(return_value=driver)
        agent._get_file_actual_size = MagicMock(return_value=0)

        result = agent.create(_make_req({
            "installPath": "ceph://pool/vol-001",
            "size": 1073741824,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryDelete:
    def test_delete_volume_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = _mock_shell()
        shell_mod.call = MagicMock(return_value="[]")
        driver = MagicMock()
        agent.get_driver = MagicMock(return_value=driver)
        agent._get_watcher = MagicMock(return_value=None)

        result = agent.delete(_make_req({
            "installPath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        driver.do_deletion.assert_called_once()

    def test_delete_volume_in_use(self):
        agent = _make_agent()
        shell_mod = _mock_shell()
        shell_mod.call = MagicMock(return_value="[]")
        agent._get_watcher = MagicMock(return_value="watcher=client.12345")

        result = agent.delete(_make_req({
            "installPath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is False
        assert "in use" in rsp["error"]


# ---------------------------------------------------------------------------
# clone
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryClone:
    def test_clone_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        _mock_ceph()
        driver = MagicMock()
        clone_rsp = module.CloneRsp()
        driver.clone_volume = MagicMock(return_value=clone_rsp)
        agent.get_driver = MagicMock(return_value=driver)
        agent._get_file_size = MagicMock(return_value=1073741824)
        agent._get_file_actual_size = MagicMock(return_value=524288)

        result = agent.clone(_make_req({
            "srcPath": "ceph://pool/src-vol",
            "dstPath": "ceph://pool/dst-vol",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["size"] == 1073741824


# ---------------------------------------------------------------------------
# flatten
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryFlatten:
    def test_flatten_no_parent(self):
        agent = _make_agent()
        _mock_capacity(agent)
        agent._get_parent = MagicMock(return_value=None)

        result = agent.flatten(_make_req({
            "path": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# create_snapshot
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCreateSnapshot:
    def test_create_snapshot_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = _mock_shell()
        driver = MagicMock()
        snap_rsp = module.CreateSnapshotRsp()
        snap_rsp.installPath = "ceph://pool/vol@snap1"
        driver.create_snapshot = MagicMock(return_value=snap_rsp)
        agent.get_driver = MagicMock(return_value=driver)
        agent._get_snapshot_actual_size = MagicMock(return_value=1024)

        result = agent.create_snapshot(_make_req({
            "snapshotPath": "ceph://pool/vol@snap1",
            "skipOnExisting": False,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# delete_snapshot
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryDeleteSnapshot:
    def test_delete_snapshot_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = _mock_shell()
        driver = MagicMock()
        agent.get_driver = MagicMock(return_value=driver)
        agent._unprotect_snapshot = MagicMock()

        result = agent.delete_snapshot(_make_req({
            "snapshotPath": "ceph://pool/vol@snap1",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        driver.delete_snapshot.assert_called_once()


# ---------------------------------------------------------------------------
# delete_image_cache
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryDeleteImageCacheTrash:
    def test_delete_image_cache_purges_matching_trash_child(self):
        agent = _make_agent()
        _mock_capacity(agent)
        ceph_mod = _mock_ceph()
        module.bash_r = MagicMock(return_value=0)
        module.bash_errorout = MagicMock()
        module.bash_roe = MagicMock(return_value=(0, "", ""))
        rbd_children = MagicMock(return_value=["pool/root-volume"])
        rbd_trash_list = MagicMock(return_value=(0, [{"id": "trash-id", "name": "root-volume"}], ""))
        rbd_trash_rm = MagicMock(return_value=(0, "", ""))

        with patch.object(ceph_mod, "rbd_children", rbd_children), \
                patch.object(ceph_mod, "rbd_trash_list", rbd_trash_list), \
                patch.object(ceph_mod, "rbd_trash_rm", rbd_trash_rm):
            result = agent.delete_image_cache(_make_req({
                "imagePath": "ceph://pool/image-cache",
                "snapshotPath": "ceph://pool/image-cache@snap",
            }))

        rsp = _load_rsp(result)
        assert rsp["success"] is True
        rbd_children.assert_called_once_with("pool/image-cache@snap")
        rbd_trash_rm.assert_called_once_with("pool", "trash-id", True)
        module.bash_errorout.assert_any_call('rbd snap unprotect {{SP_PATH}}')
        module.bash_errorout.assert_any_call('rbd rm {{IMAGE_PATH}}')

    def test_delete_image_cache_keeps_active_child_protected(self):
        agent = _make_agent()
        _mock_capacity(agent)
        ceph_mod = _mock_ceph()
        module.bash_r = MagicMock(return_value=0)
        module.bash_errorout = MagicMock()
        rbd_children = MagicMock(return_value=["pool/active-volume"])
        rbd_trash_list = MagicMock(return_value=(0, [{"id": "trash-id", "name": "old-volume"}], ""))
        rbd_trash_rm = MagicMock()

        with patch.object(ceph_mod, "rbd_children", rbd_children), \
                patch.object(ceph_mod, "rbd_trash_list", rbd_trash_list), \
                patch.object(ceph_mod, "rbd_trash_rm", rbd_trash_rm):
            result = agent.delete_image_cache(_make_req({
                "imagePath": "ceph://pool/image-cache",
                "snapshotPath": "ceph://pool/image-cache@snap",
            }))

        rsp = _load_rsp(result)
        assert rsp["success"] is False
        assert "still in used" in rsp["error"]
        assert not any("rbd snap unprotect" in str(c)
                       for c in module.bash_errorout.call_args_list)
        rbd_trash_rm.assert_not_called()

    def test_parse_legacy_trash_entries(self):
        ceph_mod = _mock_ceph()
        bash_roe = MagicMock(return_value=(0, '["trash-id", "root-volume"]', ""))

        with patch.object(real_ceph_utils.bash, "bash_roe", bash_roe):
            _, entries, _ = ceph_mod.rbd_trash_list("pool")

        assert entries == [{"id": "trash-id", "name": "root-volume"}]
        assert ceph_mod.find_rbd_trash(entries, "root-volume") == entries[0]


# ---------------------------------------------------------------------------
# protect_snapshot
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryProtectSnapshot:
    def test_protect_snapshot_success(self):
        agent = _make_agent()
        shell_mod = _mock_shell()

        result = agent.protect_snapshot(_make_req({
            "snapshotPath": "ceph://pool/vol@snap1",
            "ignoreError": False,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# unprotect_snapshot
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryUnprotectSnapshot:
    def test_unprotect_snapshot_success(self):
        agent = _make_agent()
        agent._unprotect_snapshot = MagicMock()

        result = agent.unprotect_snapshot(_make_req({
            "snapshotPath": "ceph://pool/vol@snap1",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# rollback_snapshot
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryRollbackSnapshot:
    def test_rollback_snapshot_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        driver = MagicMock()
        agent.get_driver = MagicMock(return_value=driver)
        agent._get_file_size = MagicMock(return_value=1073741824)
        agent.validate_snapshot_rollback = MagicMock()

        result = agent.rollback_snapshot(_make_req({
            "snapshotPath": "ceph://pool/vol@snap1",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        driver.rollback_snapshot.assert_called_once()


# ---------------------------------------------------------------------------
# purge_snapshots
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryPurgeSnapshots:
    def test_purge_snapshots_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = _mock_shell()

        result = agent.purge_snapshots(_make_req({
            "volumePath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# commit_image
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCommitImage:
    def test_commit_image_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = _mock_shell()
        agent._get_file_size = MagicMock(return_value=1073741824)

        result = agent.commit_image(_make_req({
            "snapshotPath": "ceph://pool/vol@snap1",
            "dstPath": "ceph://pool/cloned-vol",
            "ignoreError": False,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


@pytest.fixture
def rbd_info(monkeypatch):
    info = MagicMock(return_code=errno.ENOENT)
    monkeypatch.setattr(module.shell, 'ShellCmd', MagicMock(return_value=info))
    return info


# ---------------------------------------------------------------------------
# check_bits
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCheckBits:
    @pytest.mark.parametrize('rc, existing',
                             [(0, True), (errno.ENOENT, False)])
    def test_check_bits(self, rbd_info, rc, existing):
        rbd_info.return_code = rc
        rsp = _load_rsp(_make_agent().check_bits(_make_req({
            'installPath': 'ceph://pool/vol-001',
        })))
        assert rsp['success'] is True
        assert rsp['existing'] is existing

    def test_check_bits_reports_query_error(self, rbd_info):
        rbd_info.return_code = errno.EACCES
        rbd_info.raise_error.side_effect = RuntimeError('Permission denied')
        rsp = _load_rsp(_make_agent().check_bits(_make_req({
            'installPath': 'ceph://pool/vol-001',
        })))
        assert not rsp['success']
        assert rsp['error'] == 'Permission denied'


# ---------------------------------------------------------------------------
# resize_volume
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryResizeVolume:
    def test_resize_volume_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.qemu_img_resize = MagicMock()
        agent._get_file_size = MagicMock(return_value=2147483648)

        result = agent.resize_volume(_make_req({
            "installPath": "ceph://pool/vol-001",
            "size": 2147483648,
            "force": False,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["size"] == 2147483648


# ---------------------------------------------------------------------------
# get_volume_size
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryGetVolumeSize:
    def test_get_volume_size_success(self):
        agent = _make_agent()
        agent._get_file_size = MagicMock(return_value=1073741824)
        agent._get_file_actual_size = MagicMock(return_value=524288)

        result = agent.get_volume_size(_make_req({
            "installPath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["size"] == 1073741824
        assert rsp["actualSize"] == 524288


# ---------------------------------------------------------------------------
# batch_get_volume_size
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryBatchGetVolumeSize:
    def test_batch_get_volume_size_success(self):
        agent = _make_agent()
        agent._get_file_actual_size = MagicMock(return_value=524288)

        result = agent.batch_get_volume_size(_make_req({
            "volumeUuidInstallPaths": {
                "uuid-1": "ceph://pool/vol-1",
                "uuid-2": "ceph://pool/vol-2",
            },
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["actualSizes"]["uuid-1"] == 524288
        assert rsp["actualSizes"]["uuid-2"] == 524288


# ---------------------------------------------------------------------------
# get_volume_watchers
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryGetVolumeWatchers:
    def test_get_volume_watchers_with_watchers(self):
        agent = _make_agent()
        shell_mod = _mock_shell()
        shell_mod.call = MagicMock(return_value="Watchers:\n\twatcher=client.12345 cookie=1\n")

        result = agent.get_volume_watchers(_make_req({
            "volumePath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert len(rsp["watchers"]) == 1

    def test_get_volume_watchers_empty(self):
        agent = _make_agent()
        shell_mod = _mock_shell()
        shell_mod.call = MagicMock(return_value="")

        result = agent.get_volume_watchers(_make_req({
            "volumePath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# get_volume_snapshot_size
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryGetVolumeSnapshotSize:
    def test_get_volume_snapshot_size_success(self):
        agent = _make_agent()
        agent._get_file_size = MagicMock(return_value=1073741824)
        agent._get_snapshot_actual_size = MagicMock(return_value=262144)

        result = agent.get_volume_snapshot_size(_make_req({
            "installPath": "ceph://pool/vol@snap1",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["size"] == 1073741824
        assert rsp["actualSize"] == 262144


# ---------------------------------------------------------------------------
# delete_image_cache
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryDeleteImageCache:
    def test_delete_image_cache_not_exist(self):
        agent = _make_agent()
        _mock_capacity(agent)
        module.bash_r = MagicMock(return_value=1)

        result = agent.delete_image_cache(_make_req({
            "snapshotPath": "ceph://pool/img@snap",
            "imagePath": "ceph://pool/img",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True

    def test_delete_image_cache_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        module.bash_r = MagicMock(return_value=0)
        module.bash_o = MagicMock(return_value="")
        module.bash_errorout = MagicMock()
        module.bash_roe = MagicMock(return_value=(0, "", ""))

        result = agent.delete_image_cache(_make_req({
            "snapshotPath": "ceph://pool/img@snap",
            "imagePath": "ceph://pool/img",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# clean_trash
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCleanTrash:
    def test_clean_trash_no_pools(self):
        agent = _make_agent()
        ceph_mod = _mock_ceph()
        ceph_mod.support_defer_deleting = MagicMock(return_value=False)

        result = agent.clean_trash(_make_req({
            "pools": ["pool-1"],
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True

    def test_clean_trash_uses_shared_legacy_parser(self):
        agent = _make_agent()
        _mock_capacity(agent)
        ceph_mod = _mock_ceph()
        ceph_mod.support_defer_deleting = MagicMock(return_value=True)
        bash_roe = MagicMock(side_effect=[
            (0, '["trash-id", "root-volume"]', ""),
            (0, "", ""),
        ])

        with patch.object(real_ceph_utils.bash, "bash_roe", bash_roe):
            result = agent.clean_trash(_make_req({
                "pools": ["pool"],
                "force": True,
            }))

        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["pool2TrashResult"] == {"pool": ["root-volume"]}
        assert any("rbd trash rm pool/trash-id --force" in str(c)
                   for c in bash_roe.call_args_list)


# ---------------------------------------------------------------------------
# cp (volume copy)
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCp:
    def test_cp_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = _mock_shell()
        traceable_mod = sys.modules["zstacklib.utils.traceable_shell"]
        t_shell = MagicMock()
        t_shell.bash_progress_1 = MagicMock(return_value=(0, "", None))
        traceable_mod.get_shell = MagicMock(return_value=t_shell)
        agent._get_file_size = MagicMock(return_value=1073741824)
        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.create_temp_file = MagicMock(return_value="/tmp/test-pfile")

        with patch("os.path.exists", return_value=False):
            result = agent.cp(_make_req({
                "srcPath": "ceph://pool/src-vol",
                "dstPath": "ceph://pool/dst-vol",
                "sendCommandUrl": "",
                "threadContext": {"task-stage": None},
                "threadContextStack": [],
            }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["size"] == 1073741824


# ---------------------------------------------------------------------------
# upload_imagestore
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryUploadImagestore:
    def test_upload_imagestore_delegates(self):
        agent = _make_agent()
        agent.imagestore_client.upload_imagestore = MagicMock(
            return_value='{"success": true}')

        result = agent.upload_imagestore(_make_req({
            "key": "value",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# download_imagestore
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryDownloadImagestore:
    def test_download_imagestore_delegates(self):
        agent = _make_agent()
        driver = MagicMock()
        agent.get_driver = MagicMock(return_value=driver)
        agent.imagestore_client.download_imagestore = MagicMock(
            return_value='{"success": true}')

        result = agent.download_imagestore(_make_req({
            "key": "value",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# sftp_upload
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimarySftpUpload:
    def test_sftp_upload_success(self):
        agent = _make_agent()
        shell_mod = _mock_shell()
        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.write_to_temp_file = MagicMock(return_value="/tmp/prikey")

        with patch("os.remove"):
            result = agent.sftp_upload(_make_req({
                "primaryStorageInstallPath": "ceph://pool/vol-001",
                "sshKey": "fake-key",
                "hostname": "10.0.0.1",
                "sshPort": 22,
                "backupStorageInstallPath": "/backup/vol-001",
            }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# sftp_download
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimarySftpDownload:
    def test_sftp_download_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        agent.do_sftp_download = MagicMock()

        result = agent.sftp_download(_make_req({
            "primaryStorageInstallPath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# get_volume_snapinfos
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryGetVolumeSnapinfos:
    def test_get_volume_snapinfos_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = _mock_shell()
        shell_mod.call = MagicMock(return_value='[{"id": 1, "name": "snap1"}]')

        result = agent.get_volume_snapinfos(_make_req({
            "volumePath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# get_volume_backing_chain
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryGetVolumeBackingChain:
    def test_get_volume_backing_chain_no_parent(self):
        agent = _make_agent()
        _mock_capacity(agent)
        agent._get_parent = MagicMock(return_value=None)

        result = agent.get_volume_backing_chain(_make_req({
            "volumePath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["backingChain"] == []

    def test_get_volume_backing_chain_with_parent(self):
        agent = _make_agent()
        _mock_capacity(agent)
        parent = MagicMock()
        parent.__getitem__ = lambda self, key: {"pool": "pool", "image": "parent-img", "snapshot": "snap1"}[key]
        agent._get_parent = MagicMock(side_effect=[parent, None])

        result = agent.get_volume_backing_chain(_make_req({
            "volumePath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert len(rsp["backingChain"]) == 1


# ---------------------------------------------------------------------------
# delete_volume_backing_chain
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryDeleteVolumeBackingChain:
    def test_delete_chain_success(self):
        agent = _make_agent()
        shell_mod = _mock_shell()
        shell_mod.call = MagicMock(return_value="[]")
        driver = MagicMock()
        agent.get_driver = MagicMock(return_value=driver)
        agent._get_watcher = MagicMock(return_value=None)

        result = agent.delete_volume_backing_chain(_make_req({
            "installPaths": ["ceph://pool/vol-001"],
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# get_storage_backup_mode
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryGetStorageBackupMode:
    def test_get_backup_mode_full(self):
        agent = _make_agent()
        shell_mod = _mock_shell()

        result = agent.get_storage_backup_mode(_make_req({
            "volumePath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["mode"] == "full"

    def test_get_backup_mode_incremental(self):
        agent = _make_agent()
        shell_mod = _mock_shell()
        shell_mod.run = MagicMock(return_value=0)

        result = agent.get_storage_backup_mode(_make_req({
            "volumePath": "ceph://pool/vol-001",
            "lastBackupUuid": "backup-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["mode"] == "incremental"


# ---------------------------------------------------------------------------
# clean_storage_backup_cache
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCleanStorageBackupCache:
    def test_clean_no_snapshots(self):
        agent = _make_agent()
        shell_mod = _mock_shell()
        shell_mod.call = MagicMock(return_value="[]")

        result = agent.clean_storage_backup_cache(_make_req({
            "volumePath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# take_storage_backup
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryTakeStorageBackup:
    def test_take_storage_backup_delegates(self):
        agent = _make_agent()
        agent.imagestore_client.storage_backup = MagicMock(
            return_value='{"success": true}')

        result = agent.take_storage_backup(_make_req({"key": "value"}))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# cancel_storage_backup
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCancelStorageBackup:
    def test_cancel_storage_backup_delegates(self):
        agent = _make_agent()
        agent.imagestore_client.cancel_storage_backup = MagicMock(
            return_value='{"success": true}')

        result = agent.cancel_storage_backup(_make_req({"key": "value"}))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCancel:
    def test_cancel_delegates_to_plugin(self):
        agent = _make_agent()
        plugin_mod = sys.modules["zstacklib.utils.plugin"]
        cancel_rsp = module.AgentResponse()
        plugin_mod.cancel_job = MagicMock(return_value=cancel_rsp)

        result = agent.cancel(_make_req({"cancellationApiId": "api-001"}))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# get_download_bits_from_kvmhost_progress
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryGetDownloadProgress:
    def test_get_download_progress(self):
        agent = _make_agent()
        module.bash_r = MagicMock(return_value=0)
        agent._get_file_actual_size = MagicMock(return_value=1048576)

        result = agent.get_download_bits_from_kvmhost_progress(_make_req({
            "volumePaths": ["ceph://pool/vol-001"],
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["totalSize"] == 1048576


# ---------------------------------------------------------------------------
# download_from_remote_target
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryDownloadFromRemoteTarget:
    @pytest.fixture
    def download(self, monkeypatch, rbd_info):
        agent = _make_agent()
        target = MagicMock()
        driver = MagicMock()
        monkeypatch.setattr(
            module.remotetarget, 'get_remote_target_from_uri',
            MagicMock(return_value=target))
        agent._get_snapshots = MagicMock(return_value=[])
        agent._get_watcher = MagicMock(return_value=None)
        agent.get_driver = MagicMock(return_value=driver)
        agent._get_file_size = MagicMock(return_value=2147483648)
        return agent, target, driver

    @pytest.mark.parametrize('name', ['image-001', 'data-volume-001'])
    def test_existing_target_is_preserved(self, download, rbd_info, name):
        agent, target, driver = download
        rbd_info.return_code = 0
        rsp = _load_rsp(agent.download_from_remote_target(_make_req({
            'remoteTargetUri': 'nbd://source/export',
            'primaryStorageInstallPath': 'ceph://pool/' + name,
        })))

        assert not rsp['success']
        assert rsp['error'] == 'File exists: pool/' + name
        target.download.assert_not_called()
        driver.do_deletion.assert_not_called()

    def test_failed_target_check_stops_download(self, download, rbd_info):
        agent, target, driver = download
        rbd_info.return_code = errno.EACCES
        rbd_info.raise_error.side_effect = RuntimeError('Permission denied')
        rsp = _load_rsp(agent.download_from_remote_target(_make_req({
            'remoteTargetUri': 'nbd://source/export',
            'primaryStorageInstallPath': 'ceph://pool/vol-001',
        })))

        assert not rsp['success']
        assert rsp['error'] == 'Permission denied'
        target.download.assert_not_called()
        driver.do_deletion.assert_not_called()

    @pytest.mark.parametrize('name', ['image-001', 'data-volume-001'])
    def test_successful_download_does_not_clean_target(self, download, name):
        agent, target, driver = download
        rsp = _load_rsp(agent.download_from_remote_target(_make_req({
            'remoteTargetUri': 'nbd://source/export',
            'primaryStorageInstallPath': 'ceph://pool/' + name,
        })))

        assert rsp['success'] is True
        assert rsp['diskSize'] == 2147483648
        target.download.assert_called_once_with('rbd:pool/' + name)
        agent._get_snapshots.assert_not_called()
        agent._get_watcher.assert_not_called()
        driver.do_deletion.assert_not_called()

    @pytest.mark.parametrize('name', ['image-001', 'data-volume-001'])
    @pytest.mark.parametrize('error', [
        'NBD connection lost', 'Disk quota exceeded',
    ])
    def test_download_failure_cleans_target_and_preserves_error(
            self, download, name, error):
        agent, target, driver = download
        order = []

        def fail_download(_):
            order.append('download')
            raise RuntimeError(error)

        target.download.side_effect = fail_download
        driver.do_deletion.side_effect = lambda *_: order.append('delete')
        rsp = _load_rsp(agent.download_from_remote_target(_make_req({
            'remoteTargetUri': 'nbd://source/export',
            'primaryStorageInstallPath': 'ceph://pool/' + name,
        })))

        assert not rsp['success']
        assert rsp['error'] == error
        assert order == ['download', 'delete']
        assert driver.do_deletion.call_args.args[1] == 'pool/' + name
        agent._get_file_size.assert_not_called()

    @pytest.mark.parametrize('blocked', [
        'snapshot', 'watcher', 'inspection', 'delete',
    ])
    def test_cleanup_failure_preserves_original_download_error(
            self, download, blocked, monkeypatch):
        agent, target, driver = download
        target.download.side_effect = RuntimeError('original download error')
        warning = MagicMock()
        monkeypatch.setattr(module.logger, 'warning', warning)
        if blocked == 'snapshot':
            agent._get_snapshots.return_value = [{'name': 'image-001'}]
        if blocked == 'watcher':
            agent._get_watcher.return_value = 'watcher=client.1'
        if blocked == 'inspection':
            agent._get_snapshots.side_effect = RuntimeError(
                'cannot reach monitors')
        if blocked == 'delete':
            driver.do_deletion.side_effect = RuntimeError('RBD removal failed')

        rsp = _load_rsp(agent.download_from_remote_target(_make_req({
            'remoteTargetUri': 'nbd://source/export',
            'primaryStorageInstallPath': 'ceph://pool/vol-001',
        })))

        assert not rsp['success']
        assert rsp['error'] == 'original download error'
        target.download.assert_called_once()
        agent._get_file_size.assert_not_called()
        warning.assert_called_once()
        if blocked == 'watcher':
            assert 'after remote download failure' in str(
                warning.call_args.args[2])
        if blocked != 'delete':
            driver.do_deletion.assert_not_called()

    def test_retry_after_failed_download_succeeds(self, download):
        agent, target, driver = download
        target.download.side_effect = [
            RuntimeError('NBD connection lost'), None,
        ]
        request = _make_req({
            'remoteTargetUri': 'nbd://source/export',
            'primaryStorageInstallPath': 'ceph://pool/image-001',
        })

        failed = _load_rsp(agent.download_from_remote_target(request))
        assert not failed['success']
        assert failed['error'] == 'NBD connection lost'
        driver.do_deletion.assert_called_once()

        retried = _load_rsp(agent.download_from_remote_target(request))
        assert retried['success']
        driver.do_deletion.assert_called_once()
        assert target.download.call_count == 2

    def test_invalid_source_does_not_clean_target(self, download, monkeypatch):
        agent, target, driver = download
        monkeypatch.setattr(
            module.remotetarget, 'get_remote_target_from_uri',
            MagicMock(side_effect=RuntimeError('unsupported protocol')))

        rsp = _load_rsp(agent.download_from_remote_target(_make_req({
            'remoteTargetUri': 'unknown://source',
            'primaryStorageInstallPath': 'ceph://pool/image-001',
        })))

        assert not rsp['success']
        agent._get_snapshots.assert_not_called()
        driver.do_deletion.assert_not_called()
        target.download.assert_not_called()

    def test_download_failure_with_no_target_preserves_error(self, download):
        agent, target, driver = download
        target.download.side_effect = RuntimeError(
            'cannot connect to NBD source')
        agent._get_snapshots.side_effect = RuntimeError(
            'No such file or directory')
        rsp = _load_rsp(agent.download_from_remote_target(_make_req({
            'remoteTargetUri': 'nbd://source/export',
            'primaryStorageInstallPath': 'ceph://pool/image-001',
        })))

        assert not rsp['success']
        assert rsp['error'] == 'cannot connect to NBD source'
        agent._get_watcher.assert_not_called()
        driver.do_deletion.assert_not_called()


# ---------------------------------------------------------------------------
# download_from_nbd
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryDownloadFromNbd:
    def test_download_from_nbd_bad_scheme(self):
        agent = _make_agent()

        result = agent.download_from_nbd(_make_req({
            "nbdExportUrl": "http://10.0.0.1:10809/export",
            "primaryStorageInstallPath": "ceph://pool/vol-001",
        }))
        rsp = _load_rsp(result)
        # Should report error about unexpected protocol
        assert rsp["success"] is True  # replyerror catches, but error field set
        assert "unexpected protocol" in rsp.get("error", "")


# ---------------------------------------------------------------------------
# migrate_volume_segment
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryMigrateVolumeSegment:
    def test_migrate_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        _mock_ceph()
        agent._get_file_size = MagicMock(return_value=1073741824)
        agent._get_dst_volume_size = MagicMock(return_value=1073741824)
        agent._migrate_volume_segment = MagicMock(return_value=(0, None))

        result = agent.migrate_volume_segment(_make_req({
            "parentUuid": "",
            "resourceUuid": "res-001",
            "srcInstallPath": "ceph://pool/src-vol",
            "dstInstallPath": "ceph://pool/dst-vol",
            "dstMonHostname": "10.0.0.2",
            "dstMonSshUsername": "root",
            "dstMonSshPassword": "password",
            "dstMonSshPort": 22,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# cancel_download_from_kvmhost
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephPrimaryCancelDownloadFromKvmhost:
    def test_cancel_download_delegates(self):
        agent = _make_agent()
        agent.cancel_sftp_download = MagicMock(
            return_value='{"success": true}')

        result = agent.cancel_download_from_kvmhost(_make_req({}))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
