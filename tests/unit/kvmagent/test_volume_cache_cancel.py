# -*- coding: utf-8 -*-

import contextlib
from concurrent.futures import ThreadPoolExecutor
import importlib
import os
import platform
import shutil
import signal
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import PropertyMock, patch


_TEST_LOG_DIR = tempfile.mkdtemp(prefix="zstack-test-log-")
from zstacklib.utils import log as zstack_log
if hasattr(zstack_log, "LogConfig"):
    zstack_log.LogConfig.LOG_FOLER = _TEST_LOG_DIR
elif hasattr(zstack_log, "set_logfile_path"):
    zstack_log.set_logfile_path(os.path.join(_TEST_LOG_DIR, "zstack.log"))

try:
    platform.freedesktop_os_release()
except (AttributeError, OSError):
    platform.freedesktop_os_release = lambda: {}


def tearDownModule():
    shutil.rmtree(_TEST_LOG_DIR, ignore_errors=True)


def _decorator_passthrough(*args, **kwargs):
    def decorator(func):
        return func
    return decorator


class _Info(object):
    pass


class _HttpServerStub(object):
    def register_async_uri(self, *args, **kwargs):
        pass


class _KvmAgentStub(types.ModuleType):
    class AgentCommand(object):
        pass

    class AgentResponse(object):
        pass

    class KvmAgent(object):
        pass

    @staticmethod
    def replyerror(func):
        return func

    @staticmethod
    def get_http_server():
        return _HttpServerStub()


sys.modules.setdefault("kvmagent.kvmagent", _KvmAgentStub("kvmagent.kvmagent"))


class _TaskResultStub(object):
    def __init__(self):
        self.success = True
        self.error = None

    def fail(self, error):
        self.success = False
        self.error = error


class _TaskDaemonStub(object):
    def __init__(self, task_spec, *args, **kwargs):
        self.api_id = getattr(getattr(task_spec, "threadContext", None), "api", None)
        self.stage = None
        self.timeout = 0
        self.deadline = None
        self.result = _TaskResultStub()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


_plugin_stub = types.ModuleType("zstacklib.utils.plugin")
_plugin_stub.Plugin = object
_plugin_stub.TaskDaemon = _TaskDaemonStub
_plugin_stub.TaskManager = object
_plugin_stub.TaskResult = object

_http_utils_stub = types.ModuleType("zstacklib.utils.http")
_http_utils_stub.REQUEST_BODY = "body"
_http_utils_stub.json_dump_post = lambda *args, **kwargs: None
sys.modules.setdefault("zstacklib.utils.http", _http_utils_stub)
sys.modules.setdefault("netaddr", types.ModuleType("netaddr"))


class _TemplateStub(object):
    def __init__(self, template):
        self.template = template

    def render(self, *args, **kwargs):
        return self.template


_jinja2_stub = types.ModuleType("jinja2")
_jinja2_stub.Template = _TemplateStub
sys.modules.setdefault("jinja2", _jinja2_stub)
sys.modules.setdefault("zstacklib.utils.ip", types.ModuleType("zstacklib.utils.ip"))
sys.modules.setdefault("zstacklib.utils.iptables", types.ModuleType("zstacklib.utils.iptables"))
sys.modules.setdefault("zstacklib.utils.iproute", types.ModuleType("zstacklib.utils.iproute"))
_lvm_stub = types.ModuleType("zstacklib.utils.lvm")
_lvm_stub.get_lvm_objects = lambda *args, **kwargs: None
_lvm_stub.rescan_lvm = lambda *args, **kwargs: None
_lvm_stub.PVInfo = _Info
_lvm_stub.VGInfo = _Info
_lvm_stub.LVInfo = _Info
sys.modules.setdefault("zstacklib.utils.lvm", _lvm_stub)
_virsh_stub = types.ModuleType("zstacklib.utils.virsh")
_virsh_stub.block_cache_attach = lambda *args, **kwargs: None
_virsh_stub.block_cache_detach = lambda *args, **kwargs: None
_virsh_stub.get_secret_value = lambda *args, **kwargs: None
sys.modules.setdefault("zstacklib.utils.virsh", _virsh_stub)


def _import_with_plugin_stub(module_name):
    old_module = sys.modules.get("zstacklib.utils.plugin")
    old_target = sys.modules.pop(module_name, None)
    old_machine = platform.machine
    if module_name == "kvmagent.plugins.vm_plugin" and old_machine() == "arm64":
        platform.machine = lambda: "aarch64"
    utils_module = sys.modules.get("zstacklib.utils")
    old_attr = getattr(utils_module, "plugin", None) if utils_module else None
    had_attr = utils_module is not None and hasattr(utils_module, "plugin")
    parent_name, attr_name = module_name.rsplit(".", 1)
    parent_module = sys.modules.get(parent_name)
    old_parent_attr = getattr(parent_module, attr_name, None) if parent_module else None
    had_parent_attr = parent_module is not None and hasattr(parent_module, attr_name)
    if parent_module and had_parent_attr:
        delattr(parent_module, attr_name)
    sys.modules["zstacklib.utils.plugin"] = _plugin_stub
    if utils_module:
        setattr(utils_module, "plugin", _plugin_stub)
    try:
        return importlib.import_module(module_name)
    finally:
        if old_module is None:
            sys.modules.pop("zstacklib.utils.plugin", None)
        else:
            sys.modules["zstacklib.utils.plugin"] = old_module
        if utils_module:
            if had_attr:
                setattr(utils_module, "plugin", old_attr)
            elif hasattr(utils_module, "plugin"):
                delattr(utils_module, "plugin")
        if old_target is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = old_target
        if parent_module:
            if had_parent_attr:
                setattr(parent_module, attr_name, old_parent_attr)
            elif hasattr(parent_module, attr_name):
                delattr(parent_module, attr_name)
        platform.machine = old_machine


class _LibvirtStub(types.ModuleType):
    def __getattr__(self, name):
        if name == "libvirtError":
            return Exception
        if name.startswith("VIR_"):
            return 0
        def noop(*args, **kwargs):
            return None
        return noop


sys.modules.setdefault("libvirt", _LibvirtStub("libvirt"))
sys.modules.setdefault("libvirt_qemu", types.ModuleType("libvirt_qemu"))


class _LibvirtConnStub(object):
    def getCapabilities(self):
        return "<capabilities><host><uuid>test-host</uuid></host></capabilities>"


class _LibvirtEventManagerStub(object):
    EVENT_DEFINED = "Defined"
    EVENT_UNDEFINED = "Undefined"
    EVENT_STARTED = "Started"
    EVENT_SUSPENDED = "Suspended"
    EVENT_RESUMED = "Resumed"
    EVENT_STOPPED = "Stopped"
    EVENT_SHUTDOWN = "Shutdown"
    EVENT_PMSUSPENDED = "PMSuspended"
    EVENT_CRASHED = "Crashed"

    @staticmethod
    def event_to_string(index):
        return str(index)

    @staticmethod
    def suspend_event_to_string(index):
        return str(index)

    @staticmethod
    def block_job_type_to_string(index):
        return str(index)

    @staticmethod
    def block_job_status_to_string(index):
        return str(index)


_libvirt_singleton_stub = types.ModuleType("zstacklib.utils.libvirt_singleton")
_libvirt_singleton_stub.LibvirtEventManager = _LibvirtEventManagerStub
_libvirt_singleton_stub.LibvirtEventManagerSingleton = lambda: object()
_libvirt_singleton_stub.LibvirtSingleton = lambda: _Obj(
    conn=_LibvirtConnStub(),
    libvirt_event_callbacks={},
)
sys.modules.setdefault("zstacklib.utils.libvirt_singleton", _libvirt_singleton_stub)


class _LinuxStub(types.ModuleType):
    FileSystemInfo = _Info
    MountPointInfo = _Info

    retry = staticmethod(_decorator_passthrough)
    retry_with_check = staticmethod(_decorator_passthrough)
    with_arch = staticmethod(_decorator_passthrough)

    def is_virtual_machine(self):
        return False

    def get_max_vm_ipa_size(self):
        return 34359738368 * 1024 * 16

    def __getattr__(self, name):
        def noop(*args, **kwargs):
            return None
        return noop


sys.modules.setdefault("zstacklib.utils.linux", _LinuxStub("zstacklib.utils.linux"))


class _QemuStub(types.ModuleType):
    QEMU_VERSION = "6.2.0"

    def get_version(self):
        return self.QEMU_VERSION


sys.modules.setdefault("zstacklib.utils.qemu", _QemuStub("zstacklib.utils.qemu"))
sys.modules.setdefault("zstacklib.utils.image", types.ModuleType("zstacklib.utils.image"))
sys.modules.setdefault("zstacklib.utils.ovs", types.ModuleType("zstacklib.utils.ovs"))
_ovn_stub = types.ModuleType("zstacklib.utils.ovn")
_ovn_stub.delVnicFromOvsByVmUuidIfExist = lambda *args, **kwargs: None
sys.modules.setdefault("zstacklib.utils.ovn", _ovn_stub)
sys.modules.setdefault("zstacklib.utils.drbd", types.ModuleType("zstacklib.utils.drbd"))
sys.modules.setdefault("zstacklib.utils.qemu_nbd", types.ModuleType("zstacklib.utils.qemu_nbd"))


class _BaremetalGatewayStub(types.ModuleType):
    class BaremetalV2GatewayAgentPlugin(object):
        pass


class _ImagestoreStub(types.ModuleType):
    class ImageStoreClient(object):
        pass


class _SharedBlockPluginStub(types.ModuleType):
    MAX_ACTUAL_SIZE_FACTOR = 1


sys.modules.setdefault("kvmagent.plugins.baremetal_v2_gateway_agent",
                       _BaremetalGatewayStub("kvmagent.plugins.baremetal_v2_gateway_agent"))
sys.modules.setdefault("kvmagent.plugins.bmv2_gateway_agent.utils",
                       types.ModuleType("kvmagent.plugins.bmv2_gateway_agent.utils"))
sys.modules.setdefault("kvmagent.plugins.host_pushgateway",
                       types.ModuleType("kvmagent.plugins.host_pushgateway"))
sys.modules.setdefault("kvmagent.plugins.imagestore",
                       _ImagestoreStub("kvmagent.plugins.imagestore"))
sys.modules.setdefault("kvmagent.plugins.shared_block_plugin",
                       _SharedBlockPluginStub("kvmagent.plugins.shared_block_plugin"))


class _Obj(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _ThreadContext:
    api = "api-volume-cache-cancel"

    def __getitem__(self, key):
        if key == "task-stage":
            return None
        raise KeyError(key)


def _task_spec():
    return _Obj(
        sendCommandUrl=None,
        taskContext=None,
        threadContext=_ThreadContext(),
        threadContextStack=None,
    )


class VolumeCacheCancelCase(unittest.TestCase):
    def test_flush_cache_cancel_uses_traceable_shell_api_id(self):
        volume_cache_plugin = _import_with_plugin_stub("kvmagent.plugins.volume_cache_plugin")

        class _Cache:
            volume = _Obj(volumeUuid="volume-1")
            install_path = "/cache/volume-1.qcow2"

        daemon = volume_cache_plugin.FlushCacheTaskDaemon(_task_spec(), _Cache())

        with patch.object(volume_cache_plugin.traceable_shell, "cancel_job_by_api", create=True) as cancel:
            daemon._cancel()
            cancel.assert_called_once_with("api-volume-cache-cancel")

    def test_flush_cache_uses_traceable_shell_and_progress_file(self):
        volume_cache_plugin = _import_with_plugin_stub("kvmagent.plugins.volume_cache_plugin")

        captured = {}

        class _Cache:
            volume = _Obj(volumeUuid="volume-1")
            install_path = "/cache/volume-1.qcow2"

            def flush(self, shell=None, progress_output=None):
                captured["shell"] = shell
                captured["progress_output"] = progress_output

        daemon = volume_cache_plugin.FlushCacheTaskDaemon(_task_spec(), _Cache())

        with patch.object(volume_cache_plugin.traceable_shell, "get_shell", return_value="trace-shell"):
            daemon.flush()

        self.assertEqual("trace-shell", captured["shell"])
        self.assertEqual(daemon.progress_file, captured["progress_output"])
        self.assertEqual(100, daemon.progress)

    def test_flush_cache_cancel_after_qemu_img_zero_keeps_cancel_error(self):
        volume_cache_plugin = _import_with_plugin_stub("kvmagent.plugins.volume_cache_plugin")

        class _Cache:
            volume = _Obj(volumeUuid="volume-1")
            install_path = "/cache/volume-1.qcow2"

            def flush(self, shell=None, progress_output=None):
                daemon._cancel()

        daemon = volume_cache_plugin.FlushCacheTaskDaemon(_task_spec(), _Cache())

        with patch.object(volume_cache_plugin.traceable_shell, "cancel_job_by_api", create=True), \
                patch.object(volume_cache_plugin.traceable_shell, "get_shell", return_value="trace-shell"):
            with self.assertRaises(Exception) as exc:
                daemon.flush()

        self.assertIn("cache flush task cancelled", str(exc.exception))

    def test_flush_cache_cancel_after_qemu_img_nonzero_keeps_cancel_error(self):
        volume_cache_plugin = _import_with_plugin_stub("kvmagent.plugins.volume_cache_plugin")

        class _Cache:
            volume = _Obj(volumeUuid="volume-1")
            install_path = "/cache/volume-1.qcow2"

            def flush(self, shell=None, progress_output=None):
                daemon._cancel()
                raise Exception("qemu-img convert return code: 143")

        daemon = volume_cache_plugin.FlushCacheTaskDaemon(_task_spec(), _Cache())

        with patch.object(volume_cache_plugin.traceable_shell, "cancel_job_by_api", create=True), \
                patch.object(volume_cache_plugin.traceable_shell, "get_shell", return_value="trace-shell"):
            with self.assertRaises(Exception) as exc:
                daemon.flush()

        self.assertIn("cache flush task cancelled", str(exc.exception))

    def test_flush_cache_progress_reads_qemu_img_progress_file(self):
        volume_cache_plugin = _import_with_plugin_stub("kvmagent.plugins.volume_cache_plugin")

        cache = _Obj(volume=_Obj(volumeUuid="volume-1"), install_path="/cache/volume-1.qcow2")
        daemon = volume_cache_plugin.FlushCacheTaskDaemon(_task_spec(), cache)

        with patch.object(volume_cache_plugin.linux, "tail_1", return_value="(75.65/100%)"), \
                patch.object(volume_cache_plugin.report, "get_exact_percent", side_effect=lambda percent, _: int(percent)):
            self.assertEqual(75, daemon._get_percent())

    def test_detach_block_cache_cancel_uses_api_shell_sigint(self):
        vm_plugin = _import_with_plugin_stub("kvmagent.plugins.vm_plugin")

        cache_path = "/cache/volume-1.qcow2"
        volume = _Obj(
            installPath="/primary/volume-1",
            cache=_Obj(installPath=cache_path, timeout=30, delete=False),
        )
        daemon = vm_plugin.DetachBlockCacheTaskDaemon(_task_spec(), "vm-1", volume, "vdb")

        with patch.object(vm_plugin.qmp, "execute_qmp_command", return_value=[
                    {"file": "/cache/other.qcow2", "status": "detached"},
                    {"file": cache_path, "status": "flushing"},
                ]), \
                patch.object(vm_plugin.traceable_shell, "cancel_job_by_api", create=True) as cancel, \
                patch.object(vm_plugin.virsh, "block_cache_detach") as detach:
            daemon._cancel()
            cancel.assert_called_once_with(daemon.api_id, sig=signal.SIGINT)
            detach.assert_not_called()

    def test_detach_block_cache_cancel_rejects_after_cache_node_removed(self):
        vm_plugin = _import_with_plugin_stub("kvmagent.plugins.vm_plugin")

        volume = _Obj(
            installPath="/primary/volume-1",
            cache=_Obj(installPath="/cache/volume-1.qcow2", timeout=30, delete=False),
        )
        daemon = vm_plugin.DetachBlockCacheTaskDaemon(_task_spec(), "vm-1", volume, "vdb")

        with patch.object(vm_plugin.qmp, "execute_qmp_command", return_value=[]), \
                patch.object(vm_plugin.traceable_shell, "cancel_job_by_api", create=True) as cancel, \
                patch.object(vm_plugin.virsh, "block_cache_detach") as detach:
            with self.assertRaisesRegex(Exception, "already detached"):
                daemon._cancel()

        self.assertTrue(daemon.result.success)
        self.assertEqual(100, daemon.progress)
        cancel.assert_not_called()
        detach.assert_not_called()

    def test_detach_block_cache_cancel_falls_back_when_cache_query_fails(self):
        vm_plugin = _import_with_plugin_stub("kvmagent.plugins.vm_plugin")

        volume = _Obj(
            installPath="/primary/volume-1",
            cache=_Obj(installPath="/cache/volume-1.qcow2", timeout=30, delete=False),
        )
        daemon = vm_plugin.DetachBlockCacheTaskDaemon(_task_spec(), "vm-1", volume, "vdb")

        with patch.object(vm_plugin.qmp, "execute_qmp_command", return_value=None), \
                patch.object(vm_plugin.traceable_shell, "cancel_job_by_api", create=True) as cancel:
            daemon._cancel()

        cancel.assert_called_once_with(daemon.api_id, sig=signal.SIGINT)
        self.assertFalse(daemon.result.success)

    def test_detach_block_cache_cancel_finishes_detached_cache_and_rejects_cancel(self):
        vm_plugin = _import_with_plugin_stub("kvmagent.plugins.vm_plugin")

        cache_path = "/cache/volume-1.qcow2"
        volume = _Obj(
            installPath="/primary/volume-1",
            cache=_Obj(installPath=cache_path, timeout=30, delete=False),
        )
        daemon = vm_plugin.DetachBlockCacheTaskDaemon(_task_spec(), "vm-1", volume, "vdb")
        daemon.timeout = 300
        daemon.deadline = 2147483647
        first_detach_started = threading.Event()
        finish_first_detach = threading.Event()
        terminal_detach_started = threading.Event()
        finish_terminal_detach = threading.Event()

        def _detach(**kwargs):
            if detach.call_count == 1:
                first_detach_started.set()
                self.assertTrue(finish_first_detach.wait(3))
                raise Exception("original virsh process was terminated")
            terminal_detach_started.set()
            self.assertTrue(finish_terminal_detach.wait(3))

        with patch.object(vm_plugin.qmp, "execute_qmp_command", return_value=[{
                    "file": cache_path,
                    "status": "detached",
                }]), \
                patch.object(vm_plugin.traceable_shell, "cancel_job_by_api", create=True) as cancel, \
                patch.object(vm_plugin.traceable_shell, "TraceableShell", create=True,
                             side_effect=lambda api_id, deadline: _Obj(id=api_id, deadline=deadline)), \
                patch.object(vm_plugin.virsh, "block_cache_detach", side_effect=_detach) as detach:
            with ThreadPoolExecutor(max_workers=2) as executor:
                detach_future = executor.submit(daemon.detach)
                self.assertTrue(first_detach_started.wait(3))
                cancel_future = executor.submit(daemon._cancel)
                self.assertTrue(terminal_detach_started.wait(3))
                finish_first_detach.set()
                self.assertFalse(detach_future.done())
                finish_terminal_detach.set()
                with self.assertRaisesRegex(Exception, "already detached"):
                    cancel_future.result(timeout=3)
                detach_future.result(timeout=3)

        self.assertEqual(2, detach.call_count)
        self.assertEqual(daemon.api_id, detach.call_args_list[0][1]["cmd_shell"].id)
        terminal_kwargs = detach.call_args_list[1][1]
        self.assertEqual("vm-1", terminal_kwargs["domain"])
        self.assertEqual("vdb", terminal_kwargs["path"])
        self.assertIsNone(terminal_kwargs["cmd_shell"].id)
        self.assertEqual(daemon.deadline, terminal_kwargs["cmd_shell"].deadline)
        self.assertEqual(daemon.progress_file, terminal_kwargs["progress_output"])
        self.assertTrue(daemon.result.success)
        self.assertEqual(100, daemon.progress)
        cancel.assert_not_called()

    def test_detach_block_cache_uses_traceable_shell_and_progress_file(self):
        vm_plugin = _import_with_plugin_stub("kvmagent.plugins.vm_plugin")

        volume = _Obj(
            installPath="/primary/volume-1",
            cache=_Obj(timeout=30, delete=False),
        )
        daemon = vm_plugin.DetachBlockCacheTaskDaemon(_task_spec(), "vm-1", volume, "vdb")

        with patch.object(vm_plugin.traceable_shell, "TraceableShell", return_value="trace-shell", create=True) as shell, \
                patch.object(vm_plugin.virsh, "block_cache_detach") as detach:
            daemon.detach()

        shell.assert_called_once_with(daemon.api_id, None)
        detach.assert_called_once_with(
            domain="vm-1",
            path="vdb",
            timeout=30,
            delete=False,
            cmd_shell="trace-shell",
            progress_output=daemon.progress_file)
        self.assertEqual(100, daemon.progress)

    def test_detach_block_cache_cancel_after_virsh_zero_keeps_cancel_error(self):
        vm_plugin = _import_with_plugin_stub("kvmagent.plugins.vm_plugin")

        volume = _Obj(
            installPath="/primary/volume-1",
            cache=_Obj(installPath="/cache/volume-1.qcow2", timeout=30, delete=False),
        )
        daemon = vm_plugin.DetachBlockCacheTaskDaemon(_task_spec(), "vm-1", volume, "vdb")

        def _detach(**kwargs):
            daemon._cancel()

        with patch.object(vm_plugin.qmp, "execute_qmp_command", return_value=None), \
                patch.object(vm_plugin.traceable_shell, "cancel_job_by_api", create=True), \
                patch.object(vm_plugin.traceable_shell, "TraceableShell", return_value="trace-shell", create=True), \
                patch.object(vm_plugin.virsh, "block_cache_detach", side_effect=_detach):
            with self.assertRaises(Exception) as exc:
                daemon.detach()

        self.assertIn("detach block-cache task cancelled", str(exc.exception))

    def test_detach_block_cache_cancel_after_virsh_nonzero_keeps_cancel_error(self):
        vm_plugin = _import_with_plugin_stub("kvmagent.plugins.vm_plugin")

        volume = _Obj(
            installPath="/primary/volume-1",
            cache=_Obj(installPath="/cache/volume-1.qcow2", timeout=30, delete=False),
        )
        daemon = vm_plugin.DetachBlockCacheTaskDaemon(_task_spec(), "vm-1", volume, "vdb")

        def _detach(**kwargs):
            daemon._cancel()
            raise Exception("virsh block-cache-detach return code: 130")

        with patch.object(vm_plugin.qmp, "execute_qmp_command", return_value=None), \
                patch.object(vm_plugin.traceable_shell, "cancel_job_by_api", create=True), \
                patch.object(vm_plugin.traceable_shell, "TraceableShell", return_value="trace-shell", create=True), \
                patch.object(vm_plugin.virsh, "block_cache_detach", side_effect=_detach):
            with self.assertRaises(Exception) as exc:
                daemon.detach()

        self.assertIn("detach block-cache task cancelled", str(exc.exception))

    def test_detach_block_cache_progress_reads_virsh_progress_file(self):
        vm_plugin = _import_with_plugin_stub("kvmagent.plugins.vm_plugin")

        volume = _Obj(installPath="/primary/volume-1", cache=_Obj(timeout=30, delete=False))
        daemon = vm_plugin.DetachBlockCacheTaskDaemon(_task_spec(), "vm-1", volume, "vdb")

        with patch.object(vm_plugin.linux, "tail_1", return_value="[ 42 %]"), \
                patch.object(vm_plugin, "get_exact_percent", side_effect=lambda percent, _: int(percent)):
            self.assertEqual(42, daemon._get_percent())

    def test_flush_cache_uses_qcow2_convert_without_bitmap_when_bitmap_missing(self):
        volume_cache_plugin = _import_with_plugin_stub("kvmagent.plugins.volume_cache_plugin")
        cache = object.__new__(volume_cache_plugin.CacheProcessor)
        cache._CacheProcessor__backing_volume = _Obj(
            output_format=_Obj(value="raw"),
            source_path="/dev/vg/volume",
            io_session=lambda _: contextlib.nullcontext())

        with patch.object(volume_cache_plugin.CacheProcessor, "is_instantiated", new_callable=PropertyMock, return_value=True), \
                patch.object(volume_cache_plugin.CacheProcessor, "install_path", new_callable=PropertyMock, return_value="/cache/volume.qcow2"), \
                patch.object(volume_cache_plugin.qemu_img, "get_qcow2_bitmaps", return_value=[]), \
                patch.object(volume_cache_plugin.linux, "qcow2_convert") as convert:
            cache.flush(shell="trace-shell", progress_output="/tmp/progress")

        convert.assert_called_once_with(
            "/cache/volume.qcow2",
            "/dev/vg/volume",
            dst_format="raw",
            shell="trace-shell",
            progress_output="/tmp/progress",
            opts="-W -n",
            bitmap=None)

    def test_flush_shared_block_with_bitmap_extends_lv_and_deactivates_on_convert_failure(self):
        volume_cache_plugin = _import_with_plugin_stub("kvmagent.plugins.volume_cache_plugin")
        events = []

        class _LvSession(object):
            def __enter__(self):
                events.append("active")

            def __exit__(self, exc_type, exc_val, exc_tb):
                events.append("deactive")

        def _convert(*args, **kwargs):
            events.append("convert")
            raise RuntimeError("convert failed")

        volume = _Obj(
            deviceType="file",
            installPath="/dev/vg/volume",
            format="qcow2",
            primaryStorageType="SharedBlock",
            size=1024,
            volumeUuid="volume-1")
        cache = volume_cache_plugin.CacheProcessor(_Obj(is_initialized=True), volume, auto_create=False)

        with patch.object(volume_cache_plugin.CacheProcessor, "is_instantiated", new_callable=PropertyMock, return_value=True), \
                patch.object(volume_cache_plugin.CacheProcessor, "install_path", new_callable=PropertyMock, return_value="/cache/volume.qcow2"), \
                patch.object(volume_cache_plugin.qemu_img, "get_qcow2_bitmaps", return_value=[{"name": "block-cache"}]), \
                patch.object(volume_cache_plugin.qemu_img, "QemuImgOutputFormat", side_effect=lambda fmt: _Obj(value=fmt)), \
                patch.object(volume_cache_plugin.lvm, "RecursiveOperateLv", return_value=_LvSession(), create=True) as operate_lv, \
                patch.object(volume_cache_plugin.qemu_img, "get_check_result", return_value=_Obj(image_end_offset=100)), \
                patch.object(volume_cache_plugin.linux, "qcow2_get_cluster_size", return_value=131072), \
                patch.object(volume_cache_plugin.linux, "qcow2_measure_required_size", return_value=200) as measure, \
                patch.object(volume_cache_plugin.lvm, "extend_lv", create=True) as extend_lv, \
                patch.object(volume_cache_plugin.linux, "qcow2_convert", side_effect=_convert) as convert:
            with self.assertRaises(RuntimeError):
                cache.flush(shell="trace-shell", progress_output="/tmp/progress")

        self.assertEqual(["active", "convert", "deactive"], events)
        operate_lv.assert_called_once_with("/dev/vg/volume", shared=False)
        measure.assert_called_once_with("/cache/volume.qcow2", cluster_size=131072)
        extend_lv.assert_called_once_with("/dev/vg/volume", 300, skip_if_sufficient=True)
        convert.assert_called_once_with(
            "/cache/volume.qcow2",
            "/dev/vg/volume",
            dst_format="qcow2",
            shell="trace-shell",
            progress_output="/tmp/progress",
            opts="-W -n",
            bitmap="block-cache")

    def test_file_backing_volume_io_session_is_noop_for_other_primary_storage(self):
        volume_cache_plugin = _import_with_plugin_stub("kvmagent.plugins.volume_cache_plugin")
        backing_volume = volume_cache_plugin.FileBackingVolume(_Obj(primaryStorageType="LocalStorage"))

        with patch.object(volume_cache_plugin.lvm, "RecursiveOperateLv", create=True) as operate_lv:
            with backing_volume.io_session("/cache/volume.qcow2"):
                pass

        operate_lv.assert_not_called()

    def test_shared_block_io_session_caps_extension_at_virtual_size(self):
        volume_cache_plugin = _import_with_plugin_stub("kvmagent.plugins.volume_cache_plugin")

        volume = _Obj(
            installPath="/dev/vg/volume",
            format="qcow2",
            primaryStorageType="SharedBlock",
            size=250,
            volumeUuid="volume-1")
        backing_volume = volume_cache_plugin.FileBackingVolume(volume)

        with patch.object(volume_cache_plugin.lvm, "RecursiveOperateLv", return_value=contextlib.nullcontext(), create=True), \
                patch.object(volume_cache_plugin.qemu_img, "get_check_result", return_value=_Obj(image_end_offset=100)), \
                patch.object(volume_cache_plugin.linux, "qcow2_get_cluster_size", return_value=131072), \
                patch.object(volume_cache_plugin.linux, "qcow2_measure_required_size", return_value=200), \
                patch.object(volume_cache_plugin.lvm, "extend_lv", create=True) as extend_lv:
            with backing_volume.io_session("/cache/volume.qcow2"):
                pass

        extend_lv.assert_called_once_with("/dev/vg/volume", 250, skip_if_sufficient=True)


class VolumeCacheXmlCase(unittest.TestCase):
    def test_add_caching_store_accepts_supported_device_type(self):
        vm_plugin = _import_with_plugin_stub("kvmagent.plugins.vm_plugin")
        disk = vm_plugin.etree.Element("disk")
        volume = _Obj(deviceType="file", cache=_Obj(installPath="/cache/volume-1.qcow2"))

        vm_plugin.add_caching_store(disk, volume)

        self.assertEqual("/cache/volume-1.qcow2", disk.find("cachingStore/source").get("file"))


if __name__ == "__main__":
    unittest.main()
