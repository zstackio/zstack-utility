from __future__ import annotations

import importlib
import json
import sys
from types import ModuleType
from typing import Callable, Protocol, cast
from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.usefixtures('configured_volume_extensions')


class _HttpModule(Protocol):
    REQUEST_BODY: str
    REQUEST_HEADER: str


class _OsPathModule(Protocol):
    exists: Callable[[str], bool]
    realpath: Callable[[str], str]
    basename: Callable[[str], str]
    getsize: Callable[[str], int]
    isdir: Callable[[str], bool]


class _OsModule(Protocol):
    makedirs: Callable[..., None]
    path: _OsPathModule
    remove: Callable[[str], None]
    stat: Callable[[str], object]


class _LinuxModule(Protocol):
    get_total_file_size: Callable[[list[str]], int]
    get_img_fmt: Callable[[str], str]
    qcow2_create_with_cmd: Callable[..., None]
    qcow2_create_with_backing_file_and_cmd: Callable[..., None]
    qcow2_get_backing_file: Callable[[str], str]
    qcow2_get_backing_chain: Callable[..., list[str]]
    qcow2_get_file_chain: Callable[[str], list[str]]
    get_qcow2_base_images_recusively: Callable[[str, str], set[str]]
    get_qcow2_file_chain_size: Callable[[str], int]
    qcow2_size_and_actual_size: Callable[..., tuple[int, int]]
    qcow2_measure_required_size: Callable[[str], int]
    qcow2_get_virtual_size: Callable[[str], int]
    qcow2_clone_with_cmd: Callable[..., None]
    qcow2_rebase: Callable[..., None]
    qcow2_rebase_no_check: Callable[..., None]
    qcow2_commit: Callable[..., None]
    qcow2_virtualsize: Callable[..., int]
    qemu_img_resize: Callable[..., None]
    get_directory_used_physical_size: Callable[..., int]
    scp_upload: Callable[..., None]
    scp_download: Callable[..., None]
    write_to_temp_file: Callable[[str], str]
    rm_file_force: Callable[[str], None]
    rm_dir_checked: Callable[[str], None]
    tail_1: Callable[[str], str]
    unlink_file_checked: Callable[[str], None]
    list_all_file: Callable[[str], list[str]]
    link: Callable[[str, str], None]
    create_template: Callable[..., None]
    os: _OsModule


class _LocalStoragePluginProto(Protocol):
    config: dict[str, object]
    imagestore_client: object
    _get_disk_capacity: Callable[[str], tuple[int, int]]
    do_delete_bits: Callable[[str], None]
    load_and_save_task: Callable[..., object]
    wait_task_complete: Callable[[object], str]
    do_download_from_sftp: Callable[[object], None]
    do_create_volume_with_backing: Callable[..., None]
    hardlink_and_rebase: Callable[..., None]

    def cancel_download_from_kvmhost(self, req: dict[str, object]) -> str: ...
    def get_download_bits_from_kvmhost_progress(self, req: dict[str, object]) -> str: ...
    def check_initialized_file(self, req: dict[str, object]) -> str: ...
    def create_initialized_file(self, req: dict[str, object]) -> str: ...
    def resize_volume(self, req: dict[str, object]) -> str: ...
    def get_volume_size(self, req: dict[str, object]) -> str: ...
    def batch_get_volume_size(self, req: dict[str, object]) -> str: ...
    def get_backing_chain(self, req: dict[str, object]) -> str: ...
    def check_bits(self, req: dict[str, object]) -> str: ...
    def create_folder(self, req: dict[str, object]) -> str: ...
    def create_empty_volume(self, req: dict[str, object]) -> str: ...
    def cancel_download_from_sftp(self, req: dict[str, object]) -> str: ...
    def download_from_kvmhost(self, req: dict[str, object]) -> str: ...
    def convert_qcow2_to_raw(self, req: dict[str, object]) -> str: ...
    def get_qcow2_reference(self, req: dict[str, object]) -> str: ...
    def get_volume_base_image_path(self, req: dict[str, object]) -> str: ...
    def get_backing_file_path(self, req: dict[str, object]) -> str: ...
    def get_md5(self, req: dict[str, object]) -> str: ...
    def check_md5(self, req: dict[str, object]) -> str: ...
    def copy_bits_to_remote(self, req: dict[str, object]) -> str: ...
    def verify_backing_file_chain(self, req: dict[str, object]) -> str: ...
    def rebase_backing_files(self, req: dict[str, object]) -> str: ...
    def create_template_from_volume(self, req: dict[str, object]) -> str: ...
    def estimate_template(self, req: dict[str, object]) -> str: ...
    def revert_snapshot(self, req: dict[str, object]) -> str: ...
    def reinit_image(self, req: dict[str, object]) -> str: ...
    def merge_snapshot(self, req: dict[str, object]) -> str: ...
    def merge_and_rebase_snapshot(self, req: dict[str, object]) -> str: ...
    def offline_merge_snapshot(self, req: dict[str, object]) -> str: ...
    def offline_commit_snapshot(self, req: dict[str, object]) -> str: ...
    def get_physical_capacity(self, req: dict[str, object]) -> str: ...
    def rebase_root_volume_to_backing_file(self, req: dict[str, object]) -> str: ...
    def init(self, req: dict[str, object]) -> str: ...
    def create_volume_with_backing(self, req: dict[str, object]) -> str: ...
    def create_root_volume_from_template(self, req: dict[str, object]) -> str: ...
    def delete(self, req: dict[str, object]) -> str: ...
    def deletedir(self, req: dict[str, object]) -> str: ...
    def unlink(self, req: dict[str, object]) -> str: ...
    def upload_to_sftp(self, req: dict[str, object]) -> str: ...
    def upload_to_imagestore(self, req: dict[str, object]) -> str: ...
    def commit_to_imagestore(self, req: dict[str, object]) -> str: ...
    def download_from_sftp(self, req: dict[str, object]) -> str: ...
    def download_from_imagestore(self, req: dict[str, object]) -> str: ...
    def clean_image_meta(self, req: dict[str, object]) -> str: ...
    def hardlink_volume(self, req: dict[str, object]) -> str: ...
    def get_qcow2_hashvalue(self, req: dict[str, object]) -> str: ...


class _LocalStorageModule(Protocol):
    LocalStoragePlugin: type[_LocalStoragePluginProto]
    http: _HttpModule
    linux: _LinuxModule
    os: _OsModule
    uuidhelper: object
    secret: object
    kvmagent: object
    bash_progress_1: Callable[..., tuple[int, str, str]]
    bash_errorout: Callable[..., str]
    get_scale: Callable[[str], tuple[int, int]]
    localstorage_plugin: _LocalStoragePluginProto


class _ShellModule(Protocol):
    run: Callable[[str], object]
    call: Callable[[str], str]


class _TraceableShellModule(Protocol):
    get_shell: Callable[[object], object]


class _PluginModule(Protocol):
    completetask: Callable[[Callable[..., object]], Callable[..., object]]


class _UuidHelperModule(Protocol):
    uuid: Callable[[], str]


class _SecretModule(Protocol):
    get_image_hash: Callable[[str], str]


class _KvmAgentModule(Protocol):
    deleteImage: Callable[[str], None]

from collections.abc import MutableSet

collections = importlib.import_module("collections")
if not hasattr(collections, "MutableSet"):
    setattr(collections, "MutableSet", MutableSet)

# NOTE: sys.modules injection MUST stay at module level (not in a fixture).
# The localstorage module captures references to these mocks at import time;
# replacing them later in a per-test fixture does not propagate to already-
# bound module attributes, breaking 40+ tests.
_LEGACY_MODULES = ("plugin", "traceable_shell", "report", "linux", "bash", "shell")
for _name in _LEGACY_MODULES:
    sys.modules.setdefault(_name, MagicMock())

try:
    localstorage = cast(
        _LocalStorageModule,
        cast(object, importlib.import_module("kvmagent.plugins.localstorage")),
    )
except (ImportError, ModuleNotFoundError) as e:
    pytest.skip(f"Cannot import localstorage: {e}", allow_module_level=True)


def _make_req(body_dict: dict[str, object] | None = None) -> dict[str, object]:
    http = cast(_HttpModule, cast(object, importlib.import_module("zstacklib.utils.http")))
    body = json.dumps(body_dict or {})
    return {http.REQUEST_BODY: body, http.REQUEST_HEADER: {}}


def _make_plugin() -> _LocalStoragePluginProto:
    plugin = localstorage.LocalStoragePlugin.__new__(localstorage.LocalStoragePlugin)
    plugin.config = {}
    return plugin


def _load_rsp(result: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(result))


def _ensure_http() -> None:
    localstorage.http = cast(_HttpModule, cast(object, importlib.import_module("zstacklib.utils.http")))


def _identity(func: Callable[..., object]) -> Callable[..., object]:
    return func


def _snapshot_modules(*modules: object) -> list[tuple[object, dict[str, object]]]:
    """Capture module __dict__ for later restoration.

    MagicMock modules (injected by conftest) are skipped because their
    internal ``_mock_children`` dict cannot be safely restored via setattr.
    """
    return [
        (m, dict(vars(m)))
        for m in modules
        if m is not None and not isinstance(m, MagicMock)
    ]


def _restore_modules(snapshots: list[tuple[object, dict[str, object]]]) -> None:
    """Restore module attributes to their snapshotted state."""
    for mod, snap in snapshots:
        for key in set(vars(mod)) - set(snap):
            try:
                delattr(mod, key)
            except (AttributeError, TypeError):
                pass
        for key, val in snap.items():
            if vars(mod).get(key) is not val:
                try:
                    setattr(mod, key, val)
                except (AttributeError, TypeError):
                    pass


@pytest.fixture(autouse=True)
def _isolate_shared_modules():
    """Snapshot/restore shared module attrs to prevent test-to-test leakage.

    Direct attribute mutation (e.g. ``linux.foo = MagicMock()``) on shared
    module objects persists across tests.  This fixture saves module state
    before each test and restores it afterwards so mutations never leak.
    """
    snapshots = _snapshot_modules(
        importlib.import_module("zstacklib.utils.linux"),
        importlib.import_module("zstacklib.utils.shell"),
        importlib.import_module("os").path,
        importlib.import_module("zstacklib.utils.plugin"),
    )
    yield
    _restore_modules(snapshots)


@pytest.mark.kvmagent
class TestLocalStorageCancelDownloadFromKvmhost:
    def test_cancel_download_from_kvmhost_success(self):
        plugin = _make_plugin()
        plugin.cancel_download_from_sftp = MagicMock(return_value='{"success": true}')

        req = _make_req({'primaryStorageInstallPath': '/ps/path'})
        result = plugin.cancel_download_from_kvmhost(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageGetDownloadBitsFromKvmhostProgress:
    def test_get_download_bits_from_kvmhost_progress_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.get_total_file_size = MagicMock(return_value=123)

        req = _make_req({'volumePaths': ['/tmp/vol1']})
        result = plugin.get_download_bits_from_kvmhost_progress(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True
        assert rsp.get('totalSize') == 123


@pytest.mark.kvmagent
class TestLocalStorageCheckInitializedFile:
    def test_check_initialized_file_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        setattr(plugin, "_get_disk_capacity", MagicMock(return_value=(100, 50)))
        linux.os.path.exists = MagicMock(return_value=True)

        req = _make_req({'filePath': '/tmp/init', 'storagePath': '/tmp'})
        result = plugin.check_initialized_file(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageCreateInitializedFile:
    def test_create_initialized_file_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        os_module.path.exists = MagicMock(return_value=True)

        req = _make_req({'filePath': '/tmp/init'})
        result = plugin.create_initialized_file(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageResizeVolume:
    def test_resize_volume_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qemu_img_resize = MagicMock()
        linux.qcow2_virtualsize = MagicMock(return_value=512)

        req = _make_req({'installPath': '/tmp/vol', 'size': 512, 'force': False})
        result = plugin.resize_volume(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageGetVolumeSize:
    def test_get_volume_size_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(64, 32))

        req = _make_req({'installPath': '/tmp/vol'})
        result = plugin.get_volume_size(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageBatchGetVolumeSize:
    def test_batch_get_volume_size_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qcow2_size_and_actual_size = MagicMock(side_effect=[(1, 2), (3, 4)])

        req = _make_req({'volumeUuidInstallPaths': {'v1': '/tmp/v1', 'v2': '/tmp/v2'}})
        result = plugin.batch_get_volume_size(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageGetBackingChain:
    def test_get_backing_chain_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qcow2_get_backing_chain = MagicMock(return_value=['/base', '/snap'])
        linux.get_total_file_size = MagicMock(return_value=88)

        req = _make_req({'installPath': '/tmp/vol'})
        result = plugin.get_backing_chain(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageCheckBits:
    def test_check_bits_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        os_module.path.exists = MagicMock(return_value=True)

        req = _make_req({'installPath': '/tmp/vol'})
        result = plugin.check_bits(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageCreateFolder:
    def test_create_folder_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        os_module.path.exists = MagicMock(return_value=True)
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))

        req = _make_req({'installUrl': '/tmp/dir/vol', 'uuid': 'ps-uuid', 'storagePath': '/tmp'})
        result = plugin.create_folder(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageCreateEmptyVolume:
    def test_create_empty_volume_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.qcow2_create_with_cmd = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))
        setattr(plugin, "create_meta_file", MagicMock())
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))

        req = _make_req({
            'installUrl': '/tmp/vol',
            'size': 10,
            'uuid': 'vol-uuid',
            'name': 'vol',
            'backingFile': None,
            'storagePath': '/tmp',
        })
        result = plugin.create_empty_volume(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageCancelDownloadFromSftp:
    def test_cancel_download_from_sftp_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        shell.run = MagicMock()
        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.rm_file_force = MagicMock()
        _ensure_http()

        req = _make_req({'primaryStorageInstallPath': '/ps/path'})
        result = plugin.cancel_download_from_sftp(req)
        rsp = _load_rsp(result)

        shell.run.assert_called_once_with("pkill -9 -f '/ps/path'")
        linux.rm_file_force.assert_called_once_with('/ps/path')
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageDownloadFromKvmhost:
    def test_download_from_kvmhost_success(self):
        plugin_module = cast(_PluginModule, cast(object, importlib.import_module("zstacklib.utils.plugin")))
        old_completetask = cast(object, getattr(plugin_module, "completetask", None))
        plugin_module.completetask = cast(Callable[[Callable[..., object]], Callable[..., object]], _identity)
        try:
            reloaded = importlib.reload(cast(ModuleType, cast(object, localstorage)))
            plugin = reloaded.LocalStoragePlugin.__new__(reloaded.LocalStoragePlugin)
            plugin.config = {}
            linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
            linux.get_img_fmt = MagicMock(return_value='qcow2')
            setattr(plugin, "load_and_save_task", MagicMock(return_value=None))
            reloaded.os.path.exists = MagicMock(return_value=False)
            setattr(plugin, "wait_task_complete", MagicMock(return_value='{"success": true}'))
            setattr(plugin, "do_download_from_sftp", MagicMock())
            _ensure_http()

            req = _make_req({'primaryStorageInstallPath': '/ps/path'})
            result = plugin.download_from_kvmhost(req)
            rsp = _load_rsp(result)

            plugin.do_download_from_sftp.assert_called_once()
            assert rsp.get('success', True) is True
            assert rsp.get('format') == 'qcow2'
        finally:
            if old_completetask is not None:
                plugin_module.completetask = cast(Callable[[Callable[..., object]], Callable[..., object]], old_completetask)
            _ = importlib.reload(cast(ModuleType, cast(object, localstorage)))


@pytest.mark.kvmagent
class TestLocalStorageConvertQcow2ToRaw:
    def test_convert_qcow2_to_raw_success(self):
        plugin = _make_plugin()
        localstorage.localstorage_plugin = plugin
        localstorage.LocalStoragePlugin.imagestore_client = MagicMock()
        localstorage.LocalStoragePlugin.imagestore_client.convert_image_raw = MagicMock(return_value='{"success": true}')
        _ensure_http()

        req = _make_req({'imagePath': '/ps/path'})
        result = plugin.convert_qcow2_to_raw(req)
        rsp = _load_rsp(result)

        localstorage.LocalStoragePlugin.imagestore_client.convert_image_raw.assert_called_once()
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageGetQcow2Reference:
    def test_get_qcow2_reference_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        shell.call = MagicMock(return_value='/tmp/a\n/tmp/b')
        linux.qcow2_get_backing_file = MagicMock(side_effect=['/backing/a', '/backing/b'])
        _ensure_http()

        with patch('os.path.realpath', side_effect=lambda p: '/real/path' if p in ['/backing/a', '/target'] else p):
            req = _make_req({'searchingDir': '/search', 'path': '/target'})
            result = plugin.get_qcow2_reference(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True
        assert 'referencePaths' in rsp


@pytest.mark.kvmagent
class TestLocalStorageGetVolumeBaseImagePath:
    def test_get_volume_base_image_path_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.get_qcow2_base_images_recusively = MagicMock(return_value=set(['/cache/base', '/cache/other']))
        linux.qcow2_get_file_chain = MagicMock(return_value=['/cache/base'])
        linux.get_qcow2_file_chain_size = MagicMock(return_value=10)
        _ensure_http()

        with patch('os.path.basename', return_value='vol-uuid'), \
             patch('os.path.realpath', side_effect=lambda p: p):
            req = _make_req({
                'volumeInstallDir': '/ps/vol-uuid',
                'volumeUuid': 'vol-uuid',
                'imageCacheDir': '/cache',
                'volumeInstallPath': '/ps/vol-uuid/vol.qcow2',
            })
            result = plugin.get_volume_base_image_path(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True
        assert 'path' in rsp


@pytest.mark.kvmagent
class TestLocalStorageGetBackingFilePath:
    def test_get_backing_file_path_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.qcow2_get_backing_file = MagicMock(return_value='/backing')
        os_module.path.getsize = MagicMock(return_value=12)
        _ensure_http()

        req = _make_req({'path': '/ps/vol'})
        result = plugin.get_backing_file_path(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True
        assert 'backingFilePath' in rsp


@pytest.mark.kvmagent
class TestLocalStorageGetMd5:
    def test_get_md5_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        shell.call = MagicMock(return_value='/tmp/tmpfile')
        os_module.path.getsize = MagicMock(return_value=1)
        os_module.path.exists = MagicMock(return_value=True)
        os_module.remove = MagicMock()
        linux.tail_1 = MagicMock(return_value='1')
        setattr(localstorage, 'bash_progress_1', MagicMock(return_value=(0, 'md5value', '')))
        setattr(localstorage, 'get_scale', MagicMock(return_value=(0, 10)))
        _ensure_http()

        req = _make_req({
            'md5s': [{'resourceUuid': 'res', 'path': '/ps/vol', 'md5': 'md5value'}],
            'threadContext': 'ctx',
            'threadContextStack': [],
            'volumeUuid': 'vol',
        })
        result = plugin.get_md5(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True
        assert 'md5s' in rsp


@pytest.mark.kvmagent
class TestLocalStorageCheckMd5:
    def test_check_md5_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        shell.call = MagicMock(return_value='/tmp/tmpfile')
        os_module.path.getsize = MagicMock(return_value=1)
        os_module.path.exists = MagicMock(return_value=True)
        os_module.remove = MagicMock()
        linux.tail_1 = MagicMock(return_value='1')
        setattr(localstorage, 'bash_progress_1', MagicMock(return_value=(0, 'md5value', '')))
        setattr(localstorage, 'get_scale', MagicMock(return_value=(90, 100)))
        _ensure_http()

        req = _make_req({
            'md5s': [{'resourceUuid': 'res', 'path': '/ps/vol', 'md5': 'md5value'}],
            'threadContext': 'ctx',
            'threadContextStack': [],
            'volumeUuid': 'vol',
        })
        result = plugin.check_md5(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageCopyBitsToRemote:
    def test_copy_bits_to_remote_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        shell.call = MagicMock(return_value='/tmp/tmpfile')
        linux.write_to_temp_file = MagicMock(return_value='/tmp/pass')
        linux.qcow2_get_file_chain = MagicMock(return_value=['/ps/vol'])
        os_module.path.getsize = MagicMock(return_value=1)
        setattr(localstorage, 'bash_progress_1', MagicMock(return_value=(0, '', '')))
        setattr(localstorage, 'bash_errorout', MagicMock())
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        linux.rm_file_force = MagicMock()
        _ensure_http()

        req = _make_req({
            'paths': ['/ps/vol'],
            'dstIp': '1.1.1.1',
            'dstPassword': 'pass',
            'dstUsername': 'root',
            'dstPort': 22,
            'storagePath': '/ps',
            'threadContext': 'ctx',
            'threadContextStack': [],
            'volumeUuid': 'vol',
        })
        result = plugin.copy_bits_to_remote(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageVerifyBackingFileChain:
    def test_verify_backing_file_chain_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        os_module.path.exists = MagicMock(return_value=True)
        linux.qcow2_get_backing_file = MagicMock(return_value='/parent')
        _ensure_http()

        req = _make_req({
            'snapshots': [{'path': '/snap', 'parentPath': '/parent', 'snapshotUuid': 'snap'}],
        })
        result = plugin.verify_backing_file_chain(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageRebaseBackingFiles:
    def test_rebase_backing_files_success(self):
        plugin = _make_plugin()
        localstorage.linux.qcow2_rebase_no_check = MagicMock()
        _ensure_http()

        req = _make_req({
            'snapshots': [{'path': '/snap', 'parentPath': '/parent'}],
        })
        result = plugin.rebase_backing_files(req)
        rsp = _load_rsp(result)

        localstorage.linux.qcow2_rebase_no_check.assert_called_once_with('/parent', '/snap')
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageCreateTemplateFromVolume:
    def test_create_template_from_volume_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        traceable_shell = cast(_TraceableShellModule, cast(object, importlib.import_module("zstacklib.utils.traceable_shell")))

        os_module.path.exists = MagicMock(return_value=False)
        os_module.makedirs = MagicMock()
        linux.rm_file_force = MagicMock()
        traceable_shell.get_shell = MagicMock(return_value='shell')
        linux.create_template = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({
            'installPath': '/ps/template',
            'insallPath': '/ps/template',
            'volumePath': '/ps/vol',
            'storagePath': '/ps',
        })
        result = plugin.create_template_from_volume(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageEstimateTemplate:
    def test_estimate_template_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.qcow2_measure_required_size = MagicMock(return_value=8)
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))
        _ensure_http()

        req = _make_req({'volumePath': '/ps/vol'})
        result = plugin.estimate_template(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True
        assert rsp.get('actualSize') == 8


@pytest.mark.kvmagent
class TestLocalStorageRevertSnapshot:
    def test_revert_snapshot_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        uuidhelper = cast(_UuidHelperModule, localstorage.uuidhelper)
        uuidhelper.uuid = MagicMock(return_value='uuid')
        linux.qcow2_clone_with_cmd = MagicMock()
        linux.qcow2_virtualsize = MagicMock(return_value=12)
        _ensure_http()

        req = _make_req({'snapshotInstallPath': '/ps/snap', 'volumePath': '/ps/vol'})
        result = plugin.revert_snapshot(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True
        assert rsp.get('size') == 12


@pytest.mark.kvmagent
class TestLocalStorageReinitImage:
    def test_reinit_image_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        os_module.path.exists = MagicMock(return_value=True)
        uuidhelper = cast(_UuidHelperModule, localstorage.uuidhelper)
        uuidhelper.uuid = MagicMock(return_value='uuid')
        linux.qcow2_clone_with_cmd = MagicMock()
        _ensure_http()

        req = _make_req({'imagePath': '/ps/image', 'volumePath': '/ps/vol'})
        result = plugin.reinit_image(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageMergeSnapshot:
    def test_merge_snapshot_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        traceable_shell = cast(_TraceableShellModule, cast(object, importlib.import_module("zstacklib.utils.traceable_shell")))

        os_module.path.exists = MagicMock(return_value=False)
        os_module.makedirs = MagicMock()
        traceable_shell.get_shell = MagicMock(return_value='shell')
        linux.create_template = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({
            'workspaceInstallPath': '/ps/ws',
            'snapshotInstallPath': '/ps/snap',
            'storagePath': '/ps',
        })
        result = plugin.merge_snapshot(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageMergeAndRebaseSnapshot:
    def test_merge_and_rebase_snapshot_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        os_module.path.exists = MagicMock(return_value=False)
        os_module.makedirs = MagicMock()
        localstorage.linux.qcow2_rebase_no_check = MagicMock()
        linux.create_template = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({
            'snapshotInstallPaths': ['/ps/snap1', '/ps/snap2'],
            'workspaceInstallPath': '/ps/ws',
            'storagePath': '/ps',
        })
        result = plugin.merge_and_rebase_snapshot(req)
        rsp = _load_rsp(result)

        localstorage.linux.qcow2_rebase_no_check.assert_called_once_with('/ps/snap2', '/ps/snap1')
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageOfflineMergeSnapshot:
    def test_offline_merge_snapshot_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.qcow2_get_backing_file = MagicMock(return_value='/src')
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({
            'srcPath': '/src',
            'destPath': '/dest',
            'fullRebase': False,
            'storagePath': '/ps',
        })
        result = plugin.offline_merge_snapshot(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageOfflineCommitSnapshot:
    def test_offline_commit_snapshot_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        localstorage.linux.qcow2_get_backing_file = MagicMock(side_effect=['/base1', '/base2', '/other'])
        localstorage.linux.qcow2_commit = MagicMock()
        localstorage.linux.qcow2_rebase_no_check = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))
        plugin.imagestore_client = MagicMock()
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({
            'top': '/top',
            'base': '/base',
            'topChildrenInstallPathInDb': ['/child'],
            'storagePath': '/ps',
        })
        result = plugin.offline_commit_snapshot(req)
        rsp = _load_rsp(result)

        localstorage.linux.qcow2_commit.assert_called_once_with('/top', '/base')
        localstorage.linux.qcow2_rebase_no_check.assert_called_once_with('/base', '/child')
        plugin.imagestore_client.clean_meta.assert_called_once_with('/base')
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageGetPhysicalCapacity:
    def test_get_physical_capacity_success(self):
        plugin = _make_plugin()
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({'storagePath': '/ps'})
        result = plugin.get_physical_capacity(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageRebaseRootVolumeToBackingFile:
    def test_rebase_root_volume_to_backing_file_success(self):
        plugin = _make_plugin()
        localstorage.linux.qcow2_rebase_no_check = MagicMock()
        _ensure_http()

        req = _make_req({'backingFilePath': '/base', 'rootVolumePath': '/root'})
        result = plugin.rebase_root_volume_to_backing_file(req)
        rsp = _load_rsp(result)

        localstorage.linux.qcow2_rebase_no_check.assert_called_once_with('/base', '/root')
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageInit:
    def test_init_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        os_module.path.exists = MagicMock(return_value=True)
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        linux.get_directory_used_physical_size = MagicMock(return_value=20)
        _ensure_http()

        req = _make_req({'path': '/ps', 'initFilePath': '/ps/init'})
        result = plugin.init(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True
        assert rsp.get('localStorageUsedCapacity') == 20


@pytest.mark.kvmagent
class TestLocalStorageCreateVolumeWithBacking:
    def test_create_volume_with_backing_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        localstorage.LocalStoragePlugin.do_create_volume_with_backing = MagicMock()
        linux.qcow2_get_virtual_size = MagicMock(return_value=10)
        os_module.path.getsize = MagicMock(return_value=5)
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({'templatePathInCache': '/cache', 'installPath': '/ps/vol', 'storagePath': '/ps'})
        result = plugin.create_volume_with_backing(req)
        rsp = _load_rsp(result)

        localstorage.LocalStoragePlugin.do_create_volume_with_backing.assert_called_once()
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageCreateRootVolumeFromTemplate:
    def test_create_root_volume_from_template_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        os_module.path.exists = MagicMock(return_value=True)
        localstorage.LocalStoragePlugin.do_create_volume_with_backing = MagicMock()
        linux.qcow2_size_and_actual_size = MagicMock(return_value=(10, 5))
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({'templatePathInCache': '/cache', 'installUrl': '/ps/vol', 'storagePath': '/ps'})
        result = plugin.create_root_volume_from_template(req)
        rsp = _load_rsp(result)

        localstorage.LocalStoragePlugin.do_create_volume_with_backing.assert_called_once()
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageDelete:
    def test_delete_success(self):
        plugin = _make_plugin()
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        kvmagent_module = cast(_KvmAgentModule, localstorage.kvmagent)
        kvmagent_module.deleteImage = MagicMock()
        _ensure_http()

        req = _make_req({'path': '/ps/vol', 'storagePath': '/ps'})
        result = plugin.delete(req)
        rsp = _load_rsp(result)

        kvmagent_module.deleteImage.assert_called_once_with('/ps/vol')
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageDeleteDir:
    def test_deletedir_success(self):
        plugin = _make_plugin()
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))

        localstorage.linux.rm_dir_checked = MagicMock()
        _ensure_http()

        req = _make_req({'path': '/ps/dir', 'storagePath': '/ps'})
        result = plugin.deletedir(req)
        rsp = _load_rsp(result)

        localstorage.linux.rm_dir_checked.assert_called_once_with('/ps/dir')
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageUnlink:
    def test_unlink_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        os_module.path.isdir = MagicMock(return_value=True)
        linux.list_all_file = MagicMock(return_value=[])
        linux.unlink_file_checked = MagicMock()
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))

        req = _make_req({'installPath': '/ps/dir', 'storagePath': '/ps'})
        result = plugin.unlink(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageUploadToSftp:
    def test_upload_to_sftp_success(self):
        plugin = _make_plugin()
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        os_module.path.exists = MagicMock(return_value=True)
        localstorage.linux.scp_upload = MagicMock()
        _ensure_http()

        req = _make_req({
            'primaryStorageInstallPath': '/ps/vol',
            'backupStorageInstallPath': '/bs/vol',
            'hostname': 'host',
            'username': 'user',
            'sshKey': 'key',
            'sshPort': 22,
        })
        result = plugin.upload_to_sftp(req)
        rsp = _load_rsp(result)

        localstorage.linux.scp_upload.assert_called_once()
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageUploadToImagestore:
    def test_upload_to_imagestore_success(self):
        plugin = _make_plugin()
        localstorage.LocalStoragePlugin.imagestore_client = MagicMock()
        localstorage.LocalStoragePlugin.imagestore_client.upload_to_imagestore = MagicMock(return_value='{"success": true}')
        _ensure_http()

        req = _make_req({'primaryStorageInstallPath': '/ps/vol'})
        result = plugin.upload_to_imagestore(req)
        rsp = _load_rsp(result)

        localstorage.LocalStoragePlugin.imagestore_client.upload_to_imagestore.assert_called_once()
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageCommitToImagestore:
    def test_commit_to_imagestore_success(self):
        plugin = _make_plugin()
        localstorage.LocalStoragePlugin.imagestore_client = MagicMock()
        localstorage.LocalStoragePlugin.imagestore_client.commit_to_imagestore = MagicMock(return_value='{"success": true}')
        _ensure_http()

        req = _make_req({'primaryStorageInstallPath': '/ps/vol'})
        result = plugin.commit_to_imagestore(req)
        rsp = _load_rsp(result)

        localstorage.LocalStoragePlugin.imagestore_client.commit_to_imagestore.assert_called_once()
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageDownloadFromSftp:
    def test_download_from_sftp_success(self):
        plugin = _make_plugin()
        localstorage.LocalStoragePlugin.do_download_from_sftp = MagicMock()
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({
            'storagePath': '/ps',
            'primaryStorageInstallPath': '/ps/vol',
            'backupStorageInstallPath': '/bs/vol',
            'hostname': 'host',
            'username': 'user',
            'sshKey': 'key',
            'sshPort': 22,
            'bandWidth': 0,
        })
        result = plugin.download_from_sftp(req)
        rsp = _load_rsp(result)

        localstorage.LocalStoragePlugin.do_download_from_sftp.assert_called_once()
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageDownloadFromImagestore:
    def test_download_from_imagestore_success(self):
        plugin = _make_plugin()
        localstorage.LocalStoragePlugin.imagestore_client = MagicMock()
        localstorage.LocalStoragePlugin.imagestore_client.download_from_imagestore = MagicMock()
        localstorage.LocalStoragePlugin.imagestore_client.clean_meta = MagicMock()
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({
            'isData': True,
            'storagePath': '/ps',
            'hostname': 'host',
            'backupStorageInstallPath': '/bs/vol',
            'primaryStorageInstallPath': '/ps/vol',
            'concurrency': 1,
        })
        result = plugin.download_from_imagestore(req)
        rsp = _load_rsp(result)

        localstorage.LocalStoragePlugin.imagestore_client.download_from_imagestore.assert_called_once()
        localstorage.LocalStoragePlugin.imagestore_client.clean_meta.assert_called_once_with('/ps/vol')
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageCleanImageMeta:
    def test_clean_image_meta_success(self):
        plugin = _make_plugin()
        localstorage.LocalStoragePlugin.imagestore_client = MagicMock()
        localstorage.LocalStoragePlugin.imagestore_client.clean_meta = MagicMock()
        _ensure_http()

        req = _make_req({'primaryStorageInstallPath': '/ps/vol'})
        result = plugin.clean_image_meta(req)
        rsp = _load_rsp(result)

        localstorage.LocalStoragePlugin.imagestore_client.clean_meta.assert_called_once_with('/ps/vol')
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageHardlinkVolume:
    def test_hardlink_volume_success(self):
        plugin = _make_plugin()
        localstorage.LocalStoragePlugin.hardlink_and_rebase = MagicMock()
        setattr(plugin, '_get_disk_capacity', MagicMock(return_value=(100, 50)))
        _ensure_http()

        req = _make_req({'srcDir': '/src', 'dstDir': '/dst', 'storagePath': '/ps'})
        result = plugin.hardlink_volume(req)
        rsp = _load_rsp(result)

        localstorage.LocalStoragePlugin.hardlink_and_rebase.assert_called_once_with('/src', '/dst', '/ps')
        assert rsp.get('success', True) is True


@pytest.mark.kvmagent
class TestLocalStorageGetQcow2Hashvalue:
    def test_get_qcow2_hashvalue_success(self):
        plugin = _make_plugin()
        secret_module = cast(_SecretModule, localstorage.secret)
        secret_module.get_image_hash = MagicMock(return_value='hash')
        _ensure_http()

        req = _make_req({'installPath': '/ps/vol'})
        result = plugin.get_qcow2_hashvalue(req)
        rsp = _load_rsp(result)

        assert rsp.get('success', True) is True
        assert rsp.get('hashValue') == 'hash'
