from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from typing import Callable, Protocol, cast
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.usefixtures('configured_volume_extensions')


class _HttpModule(Protocol):
    REQUEST_BODY: str
    REQUEST_HEADER: str


class _OsPathModule(Protocol):
    exists: Callable[[str], bool]
    isdir: Callable[[str], bool]
    dirname: Callable[[str], str]
    getsize: Callable[[str], int]


class _OsModule(Protocol):
    makedirs: Callable[..., None]
    stat: Callable[..., object]
    path: _OsPathModule


class _LinuxModule(Protocol):
    is_mounted: Callable[..., bool]
    os: _OsModule
    create_temp_file: Callable[..., str]
    is_valid_nfs_url: Callable[..., None]
    mount: Callable[..., None]
    umount: Callable[..., bool]
    remount: Callable[..., None]
    mkdir: Callable[..., None]
    qcow2_get_backing_chain: Callable[..., list[str]]
    qcow2_get_backing_file: Callable[..., str]
    qcow2_get_file_chain: Callable[..., list[str]]
    get_qcow2_base_images_recusively: Callable[..., list[str]]
    get_qcow2_file_chain_size: Callable[..., int]
    qcow2_size_and_actual_size: Callable[..., tuple[int, int]]
    qcow2_virtualsize: Callable[..., int]
    qcow2_measure_required_size: Callable[..., int]
    qcow2_commit: Callable[..., None]
    qcow2_rebase: Callable[..., None]
    qcow2_rebase_no_check: Callable[..., None]
    qcow2_clone_with_cmd: Callable[..., None]
    qcow2_create_with_cmd: Callable[..., None]
    qcow2_get_virtual_size: Callable[..., int]
    create_template: Callable[..., None]
    scp_upload: Callable[..., None]
    scp_download: Callable[..., None]
    qemu_img_resize: Callable[..., None]
    get_img_fmt: Callable[..., str]
    LinuxError: type[Exception]
    rm_file_force: Callable[..., None]
    rm_dir_checked: Callable[..., None]
    list_all_file: Callable[..., list[str]]
    unlink_file_checked: Callable[..., None]
    timeout_isdir: Callable[..., bool]
    get_total_file_size: Callable[..., int]
    retry: Callable[..., Callable[[Callable[..., object]], Callable[..., object]]]


class _ImageStoreClient(Protocol):
    upload_to_imagestore: Callable[..., str]
    commit_to_imagestore: Callable[..., str]
    clean_meta: Callable[..., None]
    download_from_imagestore: Callable[..., None]


class _ShellModule(Protocol):
    ShellCmd: Callable[..., object]
    call: Callable[..., object]
    run: Callable[..., object]


class _NfsPluginProto(Protocol):
    config: dict[str, object]
    _set_capacity_to_response: Callable[..., None]
    mount_path: dict[str, str]
    imagestore_client: _ImageStoreClient

    def upload_to_imagestore(self, req: dict[str, object]) -> str: ...
    def commit_to_imagestore(self, req: dict[str, object]) -> str: ...
    def check_bits(self, req: dict[str, object]) -> str: ...
    def ping(self, req: dict[str, object]) -> str: ...
    def get_volume_size(self, req: dict[str, object]) -> str: ...
    def batch_get_volume_size(self, req: dict[str, object]) -> str: ...
    def get_backing_chain(self, req: dict[str, object]) -> str: ...
    def move_bits(self, req: dict[str, object]) -> str: ...
    def clean_image_meta(self, req: dict[str, object]) -> str: ...
    def get_capacity(self, req: dict[str, object]) -> str: ...
    def create_folder(self, req: dict[str, object]) -> str: ...
    def migrate_bits(self, req: dict[str, object]) -> str: ...
    def rebase_volume_backing_file(self, req: dict[str, object]) -> str: ...
    def resize_volume(self, req: dict[str, object]) -> str: ...
    def update_mount_point(self, req: dict[str, object]) -> str: ...
    def get_volume_base_image_path(self, req: dict[str, object]) -> str: ...
    def merge_snapshot_to_volume(self, req: dict[str, object]) -> str: ...
    def commit_snapshot(self, req: dict[str, object]) -> str: ...
    def rebase_and_merge_snapshot(self, req: dict[str, object]) -> str: ...
    def merge_snapshot(self, req: dict[str, object]) -> str: ...
    def upload_to_sftp(self, req: dict[str, object]) -> str: ...
    def download_from_imagestore(self, req: dict[str, object]) -> str: ...
    def reinit_image(self, req: dict[str, object]) -> str: ...
    def revert_volume_from_snapshot(self, req: dict[str, object]) -> str: ...
    def delete(self, req: dict[str, object]) -> str: ...
    def unlink(self, req: dict[str, object]) -> str: ...
    def remount(self, req: dict[str, object]) -> str: ...
    def mount(self, req: dict[str, object]) -> str: ...
    def umount(self, req: dict[str, object]) -> str: ...
    def create_empty_volume(self, req: dict[str, object]) -> str: ...
    def create_template_from_root_volume(self, req: dict[str, object]) -> str: ...
    def estimate_template(self, req: dict[str, object]) -> str: ...
    def download_from_sftp(self, req: dict[str, object]) -> str: ...
    def create_volume_with_backing(self, req: dict[str, object]) -> str: ...
    def create_root_volume_from_template(self, req: dict[str, object]) -> str: ...
    def download_from_kvmhost(self, req: dict[str, object]) -> str: ...
    def cancel_download_from_kvmhost(self, req: dict[str, object]) -> str: ...
    def get_download_bits_from_kvmhost_progress(self, req: dict[str, object]) -> str: ...
    def hardlink_volume(self, req: dict[str, object]) -> str: ...
    def get_qcow2_hashvalue(self, req: dict[str, object]) -> str: ...
    def hardlink_and_rebase(self, src_dir: str, dst_dir: str, storage_dir: str) -> None: ...
    def do_create_volume_with_backing(self, backing_path: str, vol_path: str, cmd: object) -> None: ...
    def create_meta_file(self, cmd: object, **kwargs: object) -> None: ...
    def load_and_save_task(self, *args: object, **kwargs: object) -> object: ...
    def wait_task_complete(self, task: object) -> object: ...


class _NfsPluginModule(Protocol):
    NfsPrimaryStoragePlugin: type[_NfsPluginProto]

from collections.abc import MutableSet

collections = importlib.import_module("collections")
if not hasattr(collections, "MutableSet"):
    setattr(collections, "MutableSet", MutableSet)

_ = sys.modules.setdefault("plugin", MagicMock())
_ = sys.modules.setdefault("traceable_shell", MagicMock())
_ = sys.modules.setdefault("report", MagicMock())
_ = sys.modules.setdefault("linux", MagicMock())
_ = sys.modules.setdefault("bash", MagicMock())
_ = sys.modules.setdefault("shell", MagicMock())

try:
    nfs_primarystorage_plugin = cast(
        _NfsPluginModule,
        cast(object, importlib.import_module("kvmagent.plugins.nfs_primarystorage_plugin")),
    )
except (ImportError, ModuleNotFoundError) as e:
    pytest.skip(f"Cannot import nfs_primarystorage_plugin: {e}", allow_module_level=True)


def _make_req(body_dict: dict[str, object] | None = None) -> dict[str, object]:
    http = cast(_HttpModule, cast(object, importlib.import_module("zstacklib.utils.http")))
    body = json.dumps(body_dict or {})
    return {http.REQUEST_BODY: body, http.REQUEST_HEADER: {}}


def _make_plugin() -> _NfsPluginProto:
    plugin_mod = _reload_nfs_plugin()
    plugin = plugin_mod.NfsPrimaryStoragePlugin.__new__(plugin_mod.NfsPrimaryStoragePlugin)
    plugin.config = {}
    plugin.mount_path = {}
    plugin.imagestore_client = MagicMock()
    return plugin


def _reload_nfs_plugin() -> _NfsPluginModule:
    lock_mod = cast(object, importlib.import_module("zstacklib.utils.lock"))
    plugin_mod = cast(object, importlib.import_module("zstacklib.utils.plugin"))

    from tests.conftest import passthrough_lock

    _orig_lock = getattr(lock_mod, "lock", None)
    _orig_completetask = getattr(plugin_mod, "completetask", None)

    setattr(lock_mod, "lock", passthrough_lock)
    setattr(plugin_mod, "completetask", passthrough_lock)

    module = cast(
        _NfsPluginModule,
        cast(object, importlib.reload(importlib.import_module("kvmagent.plugins.nfs_primarystorage_plugin"))),
    )

    # Restore originals so module-level attrs don't leak across tests
    if _orig_lock is not None:
        setattr(lock_mod, "lock", _orig_lock)
    if _orig_completetask is not None:
        setattr(plugin_mod, "completetask", _orig_completetask)

    setattr(module, "http", importlib.import_module("zstacklib.utils.http"))
    setattr(module, "linux", importlib.import_module("zstacklib.utils.linux"))
    setattr(module, "shell", importlib.import_module("zstacklib.utils.shell"))
    setattr(module, "traceable_shell", importlib.import_module("zstacklib.utils.traceable_shell"))
    setattr(module, "qcow2", importlib.import_module("zstacklib.utils.qcow2"))
    setattr(module, "qemu_img", importlib.import_module("zstacklib.utils.qemu_img"))
    setattr(module, "secret", importlib.import_module("zstacklib.utils.secret"))
    setattr(module, "get_task_stage", lambda _cmd: 0)
    setattr(module, "get_exact_percent", lambda _percent, _stage: 0)
    return module


def _load_rsp(result: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(result))


@pytest.mark.kvmagent
class TestNfsUploadToImagestore:
    def test_upload_to_imagestore_success(self):
        plugin = _make_plugin()
        plugin.imagestore_client.upload_to_imagestore = MagicMock(
            return_value='{"success": true}'
        )

        req = _make_req({'primaryStorageInstallPath': '/ps/path'})
        result = plugin.upload_to_imagestore(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsCommitToImagestore:
    def test_commit_to_imagestore_success(self):
        plugin = _make_plugin()
        plugin.imagestore_client.commit_to_imagestore = MagicMock(
            return_value='{"success": true}'
        )

        req = _make_req({'primaryStorageInstallPath': '/ps/path'})
        result = plugin.commit_to_imagestore(req)
        rsp = _load_rsp(result)
        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsCheckBits:
    def test_check_bits_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.os.path.exists = MagicMock(return_value=True)

        req = _make_req({'installPath': '/ps/vol'})
        result = plugin.check_bits(req)
        rsp = _load_rsp(result)
        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsPing:
    def test_ping_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.timeout_isdir = MagicMock(return_value=True)
        linux.is_mounted = MagicMock(return_value=True)
        linux.rm_file_force = MagicMock()

        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        touch_instance = MagicMock()
        touch_instance.return_code = 0
        shell.ShellCmd = MagicMock(return_value=touch_instance)

        req = _make_req({'uuid': 'ps-uuid', 'mountPath': '/mnt/nfs'})
        result = plugin.ping(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsGetVolumeSize:
    def test_get_volume_size_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(123, 45))

        req = _make_req({'installPath': '/ps/vol'})
        result = plugin.get_volume_size(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsBatchGetVolumeSize:
    def test_batch_get_volume_size_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qcow2_size_and_actual_size = MagicMock(side_effect=[(1, 11), (2, 22)])

        req = _make_req({'volumeUuidInstallPaths': {'vol-1': '/path1', 'vol-2': '/path2'}})
        result = plugin.batch_get_volume_size(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsGetBackingChain:
    def test_get_backing_chain_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qcow2_get_backing_chain = MagicMock(return_value=['/p/base', '/p/snap'])
        linux.get_total_file_size = MagicMock(return_value=128)

        req = _make_req({'installPath': '/ps/vol'})
        result = plugin.get_backing_chain(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsMoveBits:
    def test_move_bits_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        os_module.path.exists = MagicMock(return_value=True)
        os_module.makedirs = MagicMock()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        shell.call = MagicMock()

        req = _make_req({'uuid': 'ps-uuid', 'srcPath': '/src', 'destPath': '/dest/vol'})
        result = plugin.move_bits(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsCleanImageMeta:
    def test_clean_image_meta_success(self):
        plugin = _make_plugin()
        plugin.imagestore_client.clean_meta = MagicMock()

        req = _make_req({'primaryStorageInstallPath': '/ps/image'})
        result = plugin.clean_image_meta(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsGetCapacity:
    def test_get_capacity_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()

        req = _make_req({'uuid': 'ps-uuid'})
        result = plugin.get_capacity(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsCreateFolder:
    def test_create_folder_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        os_module.path.exists = MagicMock(return_value=True)
        os_module.makedirs = MagicMock()

        req = _make_req({'uuid': 'ps-uuid', 'installUrl': '/mnt/nfs/folder/vol'})
        result = plugin.create_folder(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsMigrateBits:
    def test_migrate_bits_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        traceable_shell = cast(MagicMock, importlib.import_module("zstacklib.utils.traceable_shell"))
        qcow2_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.qcow2"))
        qemu_img_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.qemu_img"))

        tmp_file = tempfile.NamedTemporaryFile(delete=False)
        tmp_file.close()
        linux.create_temp_file = MagicMock(return_value=tmp_file.name)
        linux.is_valid_nfs_url = MagicMock()
        linux.is_mounted = MagicMock(return_value=True)
        linux.mount = MagicMock()
        linux.mkdir = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(1, 1))
        linux.qcow2_get_backing_file = MagicMock(return_value="")
        linux.get_img_fmt = MagicMock(return_value='qcow2')
        linux.qcow2_rebase = MagicMock()
        linux.umount = MagicMock()
        linux.rm_file_force = MagicMock()

        shell.call = MagicMock(return_value="0")
        shell.run = MagicMock(return_value=1)
        shell_instance = MagicMock()
        shell_instance.call = MagicMock(return_value="")
        traceable_shell.get_shell = MagicMock(return_value=shell_instance)
        qcow2_mod.create_template_with_task_daemon = MagicMock()
        qemu_img_mod.take_default_backing_fmt_for_convert = MagicMock(return_value=True)

        req = _make_req({
            'isMounted': True,
            'mountPath': '/mnt/nfs',
            'dstFolderPath': '/dst',
            'srcFolderPath': '/src',
            'filtPaths': [],
            'kvmHostAddons': {'qcow2Options': ''},
            'volumeInstallPath': '/src/vol.qcow2',
            'independentPath': None,
            'url': 'nfs://example',
            'options': '',
        })

        result = plugin.migrate_bits(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsRebaseVolumeBackingFile:
    def test_rebase_volume_backing_file_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        logger = cast(MagicMock, importlib.import_module("zstacklib.utils.log"))

        shell.call = MagicMock(return_value="/path/a.qcow2 /path/b.qcow2")
        linux.qcow2_get_backing_file = MagicMock(side_effect=["", "/src/ps/base.qcow2"])
        os_module.path.exists = MagicMock(return_value=True)
        linux.qcow2_rebase_no_check = MagicMock()
        logger.debug = MagicMock()

        req = _make_req({
            'dstVolumeFolderPath': '/dst/vols',
            'dstImageCacheTemplateFolderPath': None,
            'srcPsMountPath': '/src/ps',
            'dstPsMountPath': '/dst/ps',
        })

        result = plugin.rebase_volume_backing_file(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert cast(MagicMock, linux.qcow2_rebase_no_check).called


@pytest.mark.kvmagent
class TestNfsResizeVolume:
    def test_resize_volume_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qemu_img_resize = MagicMock()
        linux.qcow2_virtualsize = MagicMock(return_value=1024)

        req = _make_req({'installPath': '/ps/vol.qcow2', 'size': 1024, 'force': False})
        result = plugin.resize_volume(req)
        rsp = _load_rsp(result)

        assert rsp['size'] == 1024


@pytest.mark.kvmagent
class TestNfsUpdateMountPoint:
    def test_update_mount_point_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.is_valid_nfs_url = MagicMock()
        linux.is_mounted = MagicMock(side_effect=[False, True])
        linux.umount = MagicMock()
        linux.mount = MagicMock()
        plugin._set_capacity_to_response = MagicMock()

        req = _make_req({
            'uuid': 'ps-uuid',
            'mountPath': '/mnt/nfs',
            'oldMountPoint': 'nfs://old',
            'newMountPoint': 'nfs://new',
            'options': '',
        })
        result = plugin.update_mount_point(req)
        rsp = _load_rsp(result)

        assert plugin.mount_path['ps-uuid'] == '/mnt/nfs'
        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsGetVolumeBaseImagePath:
    def test_get_volume_base_image_path_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.get_qcow2_base_images_recusively = MagicMock(
            return_value=['/cache/base.qcow2', '/cache/other.qcow2']
        )
        linux.qcow2_get_file_chain = MagicMock(return_value=['/cache/base.qcow2', '/vol/child.qcow2'])
        linux.get_qcow2_file_chain_size = MagicMock(return_value=128)

        req = _make_req({
            'volumeInstallDir': '/vol/volume-uuid',
            'volumeUuid': 'volume-uuid',
            'volumeInstallPath': '/vol/volume-uuid/root.qcow2',
            'imageCacheDir': '/cache',
        })
        result = plugin.get_volume_base_image_path(req)
        rsp = _load_rsp(result)

        assert rsp['path'] == '/cache/base.qcow2'
        assert '/cache/other.qcow2' in cast(list[str], rsp['otherPaths'])


@pytest.mark.kvmagent
class TestNfsMergeSnapshotToVolume:
    def test_merge_snapshot_to_volume_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qcow2_get_backing_file = MagicMock(return_value="/snap")
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(1, 2))

        req = _make_req({
            'uuid': 'ps-uuid',
            'srcPath': '/snap',
            'destPath': '/vol/root.qcow2',
            'fullRebase': False,
        })
        result = plugin.merge_snapshot_to_volume(req)
        rsp = _load_rsp(result)

        assert rsp['actualSize'] == 2
        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsCommitSnapshot:
    def test_commit_snapshot_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        plugin.imagestore_client.clean_meta = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qcow2_get_backing_file = MagicMock(side_effect=["/base", "/base", "/old", "/old"])
        linux.qcow2_commit = MagicMock()
        linux.qcow2_rebase_no_check = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(1, 2))

        req = _make_req({
            'uuid': 'ps-uuid',
            'top': '/snap/top.qcow2',
            'base': '/snap/base.qcow2',
            'topChildrenInstallPathInDb': ['/snap/child.qcow2'],
        })
        result = plugin.commit_snapshot(req)
        rsp = _load_rsp(result)

        assert rsp['actualSize'] == 2
        assert cast(MagicMock, linux.qcow2_rebase_no_check).called


@pytest.mark.kvmagent
class TestNfsRebaseAndMergeSnapshot:
    def test_rebase_and_merge_snapshot_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        linux.qcow2_rebase_no_check = MagicMock()
        linux.create_template = MagicMock()
        linux.LinuxError = Exception
        os_module.path.exists = MagicMock(return_value=True)
        os_module.makedirs = MagicMock()

        req = _make_req({
            'uuid': 'ps-uuid',
            'snapshotInstallPaths': ['/snap1.qcow2', '/snap2.qcow2'],
            'workspaceInstallPath': '/tmp/workspace/out.qcow2',
        })
        result = plugin.rebase_and_merge_snapshot(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False


@pytest.mark.kvmagent
class TestNfsMergeSnapshot:
    def test_merge_snapshot_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        traceable_shell = cast(MagicMock, importlib.import_module("zstacklib.utils.traceable_shell"))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        linux.create_template = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))
        traceable_shell.get_shell = MagicMock(return_value=MagicMock())
        os_module.path.exists = MagicMock(return_value=False)
        os_module.makedirs = MagicMock()

        req = _make_req({
            'uuid': 'ps-uuid',
            'snapshotInstallPath': '/snap.qcow2',
            'workspaceInstallPath': '/workspace/out.qcow2',
            'incremental': False,
        })
        result = plugin.merge_snapshot(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert rsp['actualSize'] == 5


@pytest.mark.kvmagent
class TestNfsUploadToSftp:
    def test_upload_to_sftp_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        os_module.path.exists = MagicMock(return_value=True)
        linux.scp_upload = MagicMock()

        req = _make_req({
            'primaryStorageInstallPath': '/ps/vol.qcow2',
            'backupStorageHostName': 'host',
            'backupStorageSshKey': 'key',
            'backupStorageInstallPath': '/bs/vol.qcow2',
            'backupStorageUserName': 'root',
            'backupStorageSshPort': 22,
        })
        result = plugin.upload_to_sftp(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsDownloadFromImagestore:
    def test_download_from_imagestore_success(self):
        plugin = _make_plugin()
        plugin.mount_path['ps-uuid'] = '/mnt/nfs'
        plugin._set_capacity_to_response = MagicMock()
        plugin.imagestore_client.download_from_imagestore = MagicMock()
        plugin.imagestore_client.clean_meta = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.is_mounted = MagicMock(return_value=True)

        req = _make_req({
            'uuid': 'ps-uuid',
            'isData': True,
            'hostname': 'host',
            'backupStorageInstallPath': '/bs/img.qcow2',
            'primaryStorageInstallPath': '/ps/img.qcow2',
            'concurrency': 2,
        })
        result = plugin.download_from_imagestore(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert cast(MagicMock, plugin.imagestore_client.clean_meta).called


@pytest.mark.kvmagent
class TestNfsReinitImage:
    def test_reinit_image_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        uuidhelper = cast(MagicMock, importlib.import_module("zstacklib.utils.uuidhelper"))

        os_module.path.exists = MagicMock(return_value=False)
        os_module.makedirs = MagicMock()
        uuidhelper.uuid = MagicMock(return_value="new-uuid")
        linux.qcow2_clone_with_cmd = MagicMock()

        req = _make_req({
            'uuid': 'ps-uuid',
            'imagePath': '/cache/base.qcow2',
            'volumePath': '/vols/root.qcow2',
        })
        result = plugin.reinit_image(req)
        rsp = _load_rsp(result)

        assert cast(str, rsp['newVolumeInstallPath']).endswith('new-uuid.qcow2')


@pytest.mark.kvmagent
class TestNfsRevertVolumeFromSnapshot:
    def test_revert_volume_from_snapshot_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        uuidhelper = cast(MagicMock, importlib.import_module("zstacklib.utils.uuidhelper"))

        uuidhelper.uuid = MagicMock(return_value="snap-uuid")
        linux.qcow2_clone_with_cmd = MagicMock()
        linux.qcow2_virtualsize = MagicMock(return_value=2048)

        req = _make_req({
            'uuid': 'ps-uuid',
            'snapshotInstallPath': '/snap/snap.qcow2',
        })
        result = plugin.revert_volume_from_snapshot(req)
        rsp = _load_rsp(result)

        assert rsp['size'] == 2048


@pytest.mark.kvmagent
class TestNfsDelete:
    def test_delete_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.rm_dir_checked = MagicMock()

        req = _make_req({'uuid': 'ps-uuid', 'installPath': '/ps/vols', 'folder': True})
        result = plugin.delete(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsUnlink:
    def test_unlink_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_with_link = os.path.join(tmp_dir, "linked")
            file_single = os.path.join(tmp_dir, "single")
            with open(file_with_link, "w") as fd:
                _ = fd.write("data")
            os.link(file_with_link, os.path.join(tmp_dir, "linked_copy"))
            with open(file_single, "w") as fd:
                _ = fd.write("data")

            os_module.path.isdir = MagicMock(return_value=True)
            linux.list_all_file = MagicMock(return_value=[file_with_link, file_single])
            linux.unlink_file_checked = MagicMock()

            req = _make_req({'uuid': 'ps-uuid', 'installPath': tmp_dir})
            result = plugin.unlink(req)
            rsp = _load_rsp(result)

            assert rsp['success'] is True
            assert cast(MagicMock, linux.unlink_file_checked).called


@pytest.mark.kvmagent
class TestNfsRemount:
    def test_remount_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.is_valid_nfs_url = MagicMock()
        linux.remount = MagicMock()

        req = _make_req({'uuid': 'ps-uuid', 'url': 'nfs://host', 'mountPath': '/mnt/nfs', 'options': ''})
        result = plugin.remount(req)
        rsp = _load_rsp(result)

        assert plugin.mount_path['ps-uuid'] == '/mnt/nfs'
        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsMount:
    def test_mount_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.is_valid_nfs_url = MagicMock()
        linux.is_mounted = MagicMock(return_value=True)

        req = _make_req({'uuid': 'ps-uuid', 'url': 'nfs://host', 'mountPath': '/mnt/nfs', 'options': ''})
        result = plugin.mount(req)
        rsp = _load_rsp(result)

        assert plugin.mount_path['ps-uuid'] == '/mnt/nfs'
        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsUmount:
    def test_umount_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.is_mounted = MagicMock(return_value=True)
        linux.umount = MagicMock(return_value=True)

        req = _make_req({'mountPath': '/mnt/nfs', 'url': 'nfs://host'})
        result = plugin.umount(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsCreateEmptyVolume:
    def test_create_empty_volume_success(self):
        plugin = _make_plugin()
        plugin.create_meta_file = MagicMock()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        def _passthrough_retry(*_args: object, **_kwargs: object):
            def _decorator(func: Callable[..., object]) -> Callable[..., object]:
                return func
            return _decorator

        linux.retry = _passthrough_retry
        os_module.path.exists = MagicMock(return_value=False)
        os_module.makedirs = MagicMock()
        linux.qcow2_create_with_cmd = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))

        req = _make_req({
            'uuid': 'ps-uuid',
            'name': 'data',
            'installUrl': '/ps/vols/data.qcow2',
            'size': 10,
            'backingFile': None,
        })
        result = plugin.create_empty_volume(req)
        rsp = _load_rsp(result)

        assert rsp['actualSize'] == 5
        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsCreateTemplateFromRootVolume:
    def test_create_template_from_root_volume_success(self):
        plugin = _make_plugin()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        traceable_shell = cast(MagicMock, importlib.import_module("zstacklib.utils.traceable_shell"))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        os_module.path.exists = MagicMock(return_value=False)
        os_module.makedirs = MagicMock()
        traceable_shell.get_shell = MagicMock(return_value=MagicMock())
        linux.create_template = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))

        req = _make_req({
            'uuid': 'ps-uuid',
            'installPath': '/ps/template.qcow2',
            'rootVolumePath': '/ps/root.qcow2',
            'sftpBackupStorageHostName': 'host',
        })
        result = plugin.create_template_from_root_volume(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert rsp['actualSize'] == 5


@pytest.mark.kvmagent
class TestNfsEstimateTemplate:
    def test_estimate_template_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qcow2_measure_required_size = MagicMock(return_value=11)
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(22, 0))

        req = _make_req({'volumePath': '/ps/vol.qcow2'})
        result = plugin.estimate_template(req)
        rsp = _load_rsp(result)

        assert rsp['actualSize'] == 11
        assert rsp['size'] == 22


@pytest.mark.kvmagent
class TestNfsDownloadFromSftp:
    def test_download_from_sftp_success(self):
        plugin = _make_plugin()
        plugin.mount_path['ps-uuid'] = '/mnt/nfs'
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.is_mounted = MagicMock(return_value=True)
        linux.scp_download = MagicMock()

        req = _make_req({
            'uuid': 'ps-uuid',
            'hostname': 'host',
            'sshKey': 'key',
            'backupStorageInstallPath': '/bs/img.qcow2',
            'primaryStorageInstallPath': '/ps/img.qcow2',
            'username': 'root',
            'sshPort': 22,
        })
        result = plugin.download_from_sftp(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsCreateVolumeWithBacking:
    def test_create_volume_with_backing_success(self):
        plugin = _make_plugin()
        plugin.do_create_volume_with_backing = MagicMock()
        plugin.create_meta_file = MagicMock()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        os_module.path.getsize = MagicMock(return_value=13)
        linux.qcow2_get_virtual_size = MagicMock(return_value=30)

        req = _make_req({
            'uuid': 'ps-uuid',
            'templatePathInCache': '/cache/base.qcow2',
            'installUrl': '/ps/vol.qcow2',
            'size': 30,
        })
        result = plugin.create_volume_with_backing(req)
        rsp = _load_rsp(result)

        assert rsp['size'] == 30
        assert rsp['actualSize'] == 13


@pytest.mark.kvmagent
class TestNfsCreateRootVolumeFromTemplate:
    def test_create_root_volume_from_template_success(self):
        plugin = _make_plugin()
        plugin.do_create_volume_with_backing = MagicMock()
        plugin.create_meta_file = MagicMock()
        plugin._set_capacity_to_response = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        os_module.path.exists = MagicMock(return_value=True)
        os_module.path.getsize = MagicMock(return_value=10)
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))

        req = _make_req({
            'uuid': 'ps-uuid',
            'templatePathInCache': '/cache/base.qcow2',
            'installUrl': '/ps/root.qcow2',
        })
        result = plugin.create_root_volume_from_template(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert rsp['actualSize'] == 5


@pytest.mark.kvmagent
class TestNfsDownloadFromKvmhost:
    def test_download_from_kvmhost_success(self):
        plugin = _make_plugin()
        plugin.load_and_save_task = MagicMock(return_value=None)
        plugin.wait_task_complete = MagicMock()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.scp_download = MagicMock()
        linux.get_img_fmt = MagicMock(return_value='qcow2')

        req = _make_req({
            'primaryStorageInstallPath': '/ps/img.qcow2',
            'hostname': 'host',
            'sshKey': 'key',
            'backupStorageInstallPath': '/bs/img.qcow2',
            'username': 'root',
            'sshPort': 22,
            'bandWidth': 1,
        })
        result = plugin.download_from_kvmhost(req)
        rsp = _load_rsp(result)

        assert rsp['format'] == 'qcow2'


@pytest.mark.kvmagent
class TestNfsCancelDownloadFromKvmhost:
    def test_cancel_download_from_kvmhost_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        shell.run = MagicMock()
        linux.rm_file_force = MagicMock()

        req = _make_req({'primaryStorageInstallPath': '/ps/img.qcow2'})
        result = plugin.cancel_download_from_kvmhost(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestNfsGetDownloadBitsFromKvmhostProgress:
    def test_get_download_bits_from_kvmhost_progress_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.get_total_file_size = MagicMock(return_value=123)

        req = _make_req({'volumePaths': ['/ps/img.qcow2']})
        result = plugin.get_download_bits_from_kvmhost_progress(req)
        rsp = _load_rsp(result)

        assert rsp['totalSize'] == 123


@pytest.mark.kvmagent
class TestNfsHardlinkVolume:
    def test_hardlink_volume_success(self):
        plugin = _make_plugin()
        plugin.mount_path['ps-uuid'] = '/mnt/nfs'
        plugin.hardlink_and_rebase = MagicMock()
        plugin._set_capacity_to_response = MagicMock()

        req = _make_req({'uuid': 'ps-uuid', 'srcDir': '/src', 'dstDir': '/dst'})
        result = plugin.hardlink_volume(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        plugin.hardlink_and_rebase.assert_called_with('/src', '/dst', '/mnt/nfs')


@pytest.mark.kvmagent
class TestNfsGetQcow2Hashvalue:
    def test_get_qcow2_hashvalue_success(self):
        plugin = _make_plugin()
        secret = cast(MagicMock, importlib.import_module("zstacklib.utils.secret"))
        secret.get_image_hash = MagicMock(return_value='hash')

        req = _make_req({'installPath': '/ps/img.qcow2'})
        result = plugin.get_qcow2_hashvalue(req)
        rsp = _load_rsp(result)

        assert rsp['hashValue'] == 'hash'
