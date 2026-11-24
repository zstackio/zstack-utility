import ast
import copy
import json
import pathlib
import os
import re
import types
import threading
import weakref
import tempfile
import unittest
from unittest.mock import Mock
from lxml import etree

SOURCE = pathlib.Path(__file__).parents[3] / "kvmagent" / "kvmagent" / "plugins" / "vm_plugin.py"
TREE = ast.parse(SOURCE.read_text())

def production_method(class_name, method_name, scope):
    cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name))
    method.decorator_list = []
    module = ast.Module(body=[method], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(SOURCE), "exec"), scope)
    return scope[method_name]

LOCK_SOURCE = pathlib.Path(__file__).parents[3] / "zstacklib" / "zstacklib" / "utils" / "lock.py"
lock_scope = dict(threading=threading, weakref=weakref,
                  _internal_lock=threading.RLock(), _locks=weakref.WeakValueDictionary())
lock_nodes = [n for n in ast.parse(LOCK_SOURCE.read_text()).body
              if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in ("_get_lock", "NamedLock")]
exec(compile(ast.Module(body=lock_nodes, type_ignores=[]), str(LOCK_SOURCE), "exec"), lock_scope)

class LibvirtError(Exception):
    def __init__(self, message, code=None, str1=None, str2=None):
        super().__init__(message)
        self.code, self.str1, self.str2 = code, str1, str2

    def get_error_code(self):
        return self.code

    def get_str1(self):
        return self.str1

    def get_str2(self):
        return self.str2

class Domain:
    def __init__(self, persistent=True, fail_first=False):
        self.persistent = persistent
        self.defined = True
        self.flags = []
        self.fail_first = fail_first
        self.saved_state = {}

    def isPersistent(self):
        return self.persistent

    def info(self):
        if not self.defined:
            raise LibvirtError("domain no longer exists", 42)
        return 5, 0, 0, 0, 0

    def undefineFlags(self, flags):
        self.flags.append(flags)
        if self.fail_first:
            self.fail_first = False
            raise LibvirtError("unsupported cleanup flags")
        self.remove_saved_state(flags)
        self.defined = False

    def remove_saved_state(self, flags):
        reasons = {1: "Refusing to undefine while domain managed save image exists",
                   2: "cannot delete inactive domain with 1 snapshots"}
        for flag, path in self.saved_state.items():
            if path.exists():
                if not flags & flag:
                    raise LibvirtError(reasons[flag], 55)
                path.unlink()

    def undefine(self):
        self.defined = False

    def destroy(self):
        pass

class LegacyDomain(Domain):
    def __init__(self, xml, unsupported_error=None):
        super().__init__()
        self.xml = self.original_xml = xml
        self.definitions, self.xml_desc_flags = [], []
        self.unsupported_error = unsupported_error or LibvirtError(
            "Synthetic flag error", 8, "qemuDomainUndefineFlags", "flags")

    def XMLDesc(self, flags):
        self.xml_desc_flags.append(flags)
        return self.xml

    def defineXML(self, xml):
        self.definitions.append(xml)
        self.xml, self.defined = xml, True
        return self

    def undefineFlags(self, flags):
        self.flags.append(flags)
        if flags & ~7:
            raise self.unsupported_error
        self.remove_saved_state(flags)
        nvram = etree.fromstring(self.xml).find("./os/nvram")
        if nvram is not None and self.firmware.exists():
            if not flags & 4:
                raise LibvirtError("cannot delete inactive domain with nvram", 55)
            self.firmware.unlink()
        self.defined = False

    def undefine(self):
        self.undefineFlags(0)


class FirmwareCleanupTest(unittest.TestCase):
    def setUp(self):
        self.libvirt = types.SimpleNamespace(libvirtError=LibvirtError,
            VIR_DOMAIN_UNDEFINE_MANAGED_SAVE=1, VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA=2,
            VIR_DOMAIN_UNDEFINE_NVRAM=4, VIR_DOMAIN_UNDEFINE_KEEP_NVRAM=8,
            VIR_DOMAIN_XML_SECURE=1, VIR_DOMAIN_XML_INACTIVE=2, VIR_ERR_INVALID_ARG=8,
            VIR_ERR_NO_DOMAIN=42)
        self.linux = types.SimpleNamespace(
            wait_callback_success=lambda callback, arg, **kw: callback(arg),
            find_process_by_cmdline=Mock(return_value="123"), kill_process=Mock(),
            find_vm_pid_by_uuid=Mock(return_value=None),
            rm_file_force=Mock(), rm_file_checked=Mock(), VolumeInUseError=OSError)
        self.shell_command = Mock(stdout="", stderr="", return_code=1)
        self.shell = types.SimpleNamespace(ShellCmd=Mock(return_value=self.shell_command))
        self.os = types.SimpleNamespace(**vars(os))
        self.os.path = types.SimpleNamespace(**vars(os.path))
        self.os.path.exists = Mock(return_value=False)
        self.nvram = types.SimpleNamespace(build_nvram_fd_path=lambda uuid, managed=False:
                                           '/var/lib/libvirt/qemu/nvram/%s.fd' % uuid)
        self.scope = dict(libvirt=self.libvirt, linux=self.linux, logger=Mock(), nvram=self.nvram,
            tpm=types.SimpleNamespace(VIRSH_SUPPORT_KEEP_TPM=False), VIR_DOMAIN_UNDEFINE_KEEP_TPM=64,
            kvmagent=types.SimpleNamespace(KvmError=RuntimeError, AgentResponse=lambda: types.SimpleNamespace(success=True)),
            os=self.os, shell=self.shell, re=re, etree=etree,
            lock=types.SimpleNamespace(NamedLock=lock_scope["NamedLock"]))
        self.stop = production_method("Vm", "stop", self.scope)

    @staticmethod
    def device_info(uuid):
        return dict(nicInfos=[], virtualDeviceInfoList=[], memBalloonInfo=None, vmXml=None, edkRpm=None)

    def vm(self, **kwargs):
        domain = Domain(**kwargs)
        devices = types.SimpleNamespace(get_child_node_as_list=lambda name: [])
        vm = types.SimpleNamespace(uuid="a" * 32, domain=domain,
            domain_xmlobject=types.SimpleNamespace(devices=devices),
            is_alive=lambda: domain.defined, is_powered_off=lambda: True,
            wait_for_state_change=lambda state: not domain.defined)
        vm._get_undefine_flags = production_method("Vm", "_get_undefine_flags", self.scope)
        vm._undefine_for_firmware_cleanup = types.MethodType(
            production_method("Vm", "_undefine_for_firmware_cleanup", self.scope), vm)
        return vm

    def test_force_stop_preserves_inactive_domain_and_firmware(self):
        for legacy in [False, True]:
            with self.subTest(legacy=legacy):
                vm, firmware = self.legacy_vm() if legacy else (self.vm(), None)
                self.stop(vm, strategy="force")
                self.assertTrue(vm.domain.defined, "force stop must retain the upstream inactive definition")
                self.assertEqual([], vm.domain.flags, "force stop must not undefine or rewrite firmware")
                if firmware:
                    self.assertEqual(b"existing EFI boot entries", firmware.read_bytes())
                    self.assertEqual([], vm.domain.definitions)

    def legacy_vm(self, bios=False, **faults):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        firmware = pathlib.Path(directory.name) / ("a" * 32 + ".fd")
        firmware.write_bytes(b"existing EFI boot entries")
        tree = etree.fromstring('<domain><uuid>aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa</uuid>'
                                '<os><type>hvm</type></os><devices><graphics type="vnc" '
                                'passwd="test-only-password"/></devices></domain>')
        if not bios:
            os_node = tree.find("os")
            etree.SubElement(os_node, "loader", readonly="yes", type="pflash").text = "/firmware/code.fd"
            etree.SubElement(os_node, "nvram").text = "/var/lib/libvirt/qemu/nvram/" + "a" * 32 + ".fd"
        domain = LegacyDomain(etree.tostring(tree).decode(), **faults)
        domain.firmware = firmware
        vm = self.vm()
        vm.domain, vm.domain_xml = domain, domain.original_xml
        vm.is_alive = lambda: domain.defined
        vm.wait_for_state_change = lambda state: not domain.defined
        connection = types.SimpleNamespace(defineXML=domain.defineXML)
        self.scope["LibvirtAutoReconnect"] = lambda operation: lambda: operation(connection)
        return vm, firmware

    def test_transient_force_stop_does_not_undefine(self):
        vm = self.vm(persistent=False)
        self.stop(vm, strategy="force")
        self.assertEqual([], vm.domain.flags)
        self.linux.kill_process.assert_called_once()

    def test_explicit_no_undefine_is_respected(self):
        vm = self.vm()
        self.stop(vm, strategy="force", undefine=False)
        self.assertEqual([], vm.domain.flags)

    def test_normal_stop_preserves_nvram(self):
        for strategy in ["grace", "cold"]:
            with self.subTest(strategy=strategy):
                vm = self.vm()
                self.stop(vm, strategy=strategy)
                self.assertFalse(vm.domain.defined)
                self.assertFalse(vm.domain.flags[-1] & self.libvirt.VIR_DOMAIN_UNDEFINE_NVRAM,
                                 "ordinary stop must retain existing UEFI boot entries")
                self.assertTrue(vm.domain.flags[-1] & self.libvirt.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM)

    def test_destroy_removes_nvram(self):
        vm = self.vm()
        vm.stop = types.MethodType(self.stop, vm)
        destroy = production_method("Vm", "destroy", self.scope)
        destroy(vm)
        self.assertFalse(vm.domain.defined)
        self.assertTrue(vm.domain.flags[-1] & self.libvirt.VIR_DOMAIN_UNDEFINE_NVRAM)
        self.assertFalse(vm.domain.flags[-1] & self.libvirt.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM)

    def test_destroy_preserves_managed_nvram_and_tpm(self):
        vm = self.vm()
        self.nvram.build_nvram_fd_path = lambda uuid, managed=False: 'managed.fd' if managed else 'old.fd'
        self.scope['tpm'].VIRSH_SUPPORT_KEEP_TPM = True
        vm.stop = types.MethodType(self.stop, vm)
        production_method("Vm", "destroy", self.scope)(vm)
        self.assertTrue(vm.domain.flags[-1] & self.libvirt.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM)
        self.assertTrue(vm.domain.flags[-1] & 64)
        self.assertFalse(vm.domain.flags[-1] & self.libvirt.VIR_DOMAIN_UNDEFINE_NVRAM)

    def cleanup(self, identifier="a" * 32, domain=None, cleanup_inactive_domain=None):
        command = {"vmUuid": identifier}
        if cleanup_inactive_domain is not None:
            command["cleanupInactiveDomain"] = cleanup_inactive_domain
        self.scope.update(http=types.SimpleNamespace(REQUEST_BODY="body"),
            jsonobject=types.SimpleNamespace(loads=lambda text: types.SimpleNamespace(**json.loads(text)),
                dumps=lambda value: json.dumps(vars(value))),
            get_vm_by_uuid_no_retry=Mock(side_effect=lambda *args: domain
                if domain is not None and getattr(getattr(domain, "domain", None), "defined", True) else None))
        clean = production_method("VmPlugin", "clean_vm_firmware_flash", self.scope)
        plugin = types.SimpleNamespace(clean_vm_firmware_flash=clean)
        self.attach_file_check(plugin)
        endpoint = production_method("VmPlugin", "clean_firmware_flash", self.scope)
        return endpoint(plugin, {"body": json.dumps(command)})

    def attach_file_check(self, plugin):
        cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "VmPlugin")
        if any(isinstance(n, ast.FunctionDef) and n.name == "_check_vm_firmware_flash" for n in cls.body):
            plugin._check_vm_firmware_flash = production_method("VmPlugin", "_check_vm_firmware_flash", self.scope)

    def historical_vm(self, state=5):
        vm = self.vm()
        vm.VIR_DOMAIN_SHUTOFF = 5
        vm.domain.info = Mock(return_value=(state, 0, 0, 0, 0))
        vm.is_powered_off = types.MethodType(production_method("Vm", "is_powered_off", self.scope), vm)
        vm.stop = Mock(wraps=types.MethodType(self.stop, vm))
        self.linux.find_process_by_cmdline.return_value = None
        return vm

    def test_legacy_final_cleanup_uses_nvram_flag_without_redefining_xml(self):
        for bios, missing_constant in [(False, False), (False, True), (True, False)]:
            with self.subTest(bios=bios, missing_constant=missing_constant):
                vm, firmware = self.legacy_vm(bios=bios)
                if missing_constant:
                    del self.libvirt.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM
                self.os.path.exists.return_value = True
                response = json.loads(self.cleanup(domain=vm, cleanup_inactive_domain=True))
                self.assertTrue(response["cleanupCompleted"])
                self.assertEqual([8, 0 if bios else 4], vm.domain.flags)
                self.assertEqual([], vm.domain.definitions, "final cleanup must not temporarily replace domain XML")
                self.assertEqual(vm.domain.original_xml, vm.domain.xml)
                self.assertFalse(vm.domain.defined)
                self.assertEqual(bios, firmware.exists())
                self.shell.ShellCmd.assert_called()
                self.libvirt.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM = 8

    def test_legacy_final_cleanup_refuses_foreign_or_empty_nvram_path(self):
        for path in ["/var/lib/libvirt/qemu/nvram/" + "b" * 32 + ".fd", "", "/tmp/elsewhere.fd"]:
            with self.subTest(path=path):
                vm, firmware = self.legacy_vm()
                tree = etree.fromstring(vm.domain.xml)
                tree.find("./os/nvram").text = path
                vm.domain.xml = etree.tostring(tree).decode()
                with self.assertRaises((RuntimeError, LibvirtError)):
                    self.cleanup(domain=vm, cleanup_inactive_domain=True)
                self.assertTrue(vm.domain.defined)
                self.assertEqual([8], vm.domain.flags)
                self.assertEqual([], vm.domain.definitions)
                self.assertEqual(b"existing EFI boot entries", firmware.read_bytes())

    def test_legacy_final_cleanup_preserves_saved_state(self):
        for flag in [1, 2]:
            with self.subTest(saved_state_flag=flag), tempfile.TemporaryDirectory() as directory:
                vm, firmware = self.legacy_vm()
                state = pathlib.Path(directory) / "existing-state"
                state.write_bytes(b"existing user saved state")
                vm.domain.saved_state[flag] = state
                with self.assertRaises((RuntimeError, LibvirtError)):
                    self.cleanup(domain=vm, cleanup_inactive_domain=True)
                self.assertEqual([8, 4], vm.domain.flags)
                self.assertTrue(vm.domain.defined)
                self.assertEqual([], vm.domain.definitions)
                self.assertEqual(b"existing EFI boot entries", firmware.read_bytes())
                self.assertEqual(b"existing user saved state", state.read_bytes())

    def test_final_cleanup_propagates_other_libvirt_errors_without_fallback(self):
        for error in [LibvirtError("unsupported flags", 38, "qemuDomainUndefineFlags", "flags"),
                      LibvirtError("unsupported flags", 8, "otherApi", "flags"),
                      LibvirtError("unsupported flags", 8, "qemuDomainUndefineFlags", "domain")]:
            with self.subTest(error=vars(error)):
                vm, firmware = self.legacy_vm(unsupported_error=error)
                with self.assertRaises((RuntimeError, LibvirtError)):
                    self.cleanup(domain=vm, cleanup_inactive_domain=True)
                self.assertEqual([8], vm.domain.flags)
                self.assertTrue(vm.domain.defined)
                self.assertEqual([], vm.domain.definitions)
                self.assertEqual(b"existing EFI boot entries", firmware.read_bytes())

    def test_file_check_failure_keeps_domain_and_firmware_in_all_cleanup_modes(self):
        for legacy in [False, True, None]:
            for rc, stdout, stderr in [(124, "", ""), (127, "", "lsof missing"),
                                       (2, "", "permission denied"), (0, "", ""),
                                       (1, "", "permission denied"), (0, "p123\ncqemu\n", "")]:
                with self.subTest(legacy=legacy, rc=rc, stdout=stdout, stderr=stderr):
                    vm, firmware = self.legacy_vm() if legacy else (self.historical_vm() if legacy is False else None, None)
                    self.os.path.exists.return_value = True
                    self.shell_command.return_code, self.shell_command.stdout, self.shell_command.stderr = rc, stdout, stderr
                    with self.assertRaises((RuntimeError, LibvirtError, OSError)):
                        self.cleanup(domain=vm, cleanup_inactive_domain=True)
                    if vm:
                        self.assertTrue(vm.domain.defined)
                        self.assertEqual([], vm.domain.flags, "file-use check must happen before domain removal")
                    if firmware:
                        self.assertEqual(b"existing EFI boot entries", firmware.read_bytes())
                    self.linux.rm_file_checked.assert_not_called()

    def test_missing_file_skips_lsof_but_still_checks_domain(self):
        vm = self.historical_vm()
        self.os.path.exists.return_value = False
        response = json.loads(self.cleanup(domain=vm, cleanup_inactive_domain=True))
        self.assertTrue(response["cleanupCompleted"])
        self.assertFalse(vm.domain.defined)
        self.shell.ShellCmd.assert_not_called()

    def test_final_cleanup_removes_historical_powered_off_domain(self):
        vm = self.historical_vm()
        failure = None
        try:
            response = json.loads(self.cleanup(domain=vm, cleanup_inactive_domain=True))
        except (RuntimeError, LibvirtError) as error:
            failure = error
        self.assertIsNone(failure, "final deletion must reclaim an upgrade-era stopped domain: %s" % failure)
        self.assertTrue(response["success"])
        self.assertIs(response.get("cleanupCompleted"), True, "successful cleanup must acknowledge that the domain and file are gone")
        self.assertFalse(vm.domain.defined)
        self.assertEqual([8], vm.domain.flags, "historical domain removal must preserve NVRAM until checked cleanup")
        self.assertGreaterEqual(self.scope["get_vm_by_uuid_no_retry"].call_count, 2,
                                "cleanup must confirm that the domain disappeared before removing its file")
        self.linux.rm_file_checked.assert_called_once_with("/var/lib/libvirt/qemu/nvram/" + vm.uuid + ".fd")
        self.linux.kill_process.assert_not_called()

    def test_final_cleanup_does_not_stop_vm_or_logout_shared_iscsi_session(self):
        vm = self.historical_vm()
        disk = types.SimpleNamespace(type_="block", device_="lun",
                                     source=types.SimpleNamespace(dev_="/dev/disk/by-path/shared-iscsi-lun"))
        vm.domain_xmlobject.devices.get_child_node_as_list = lambda kind: [disk] if kind == "disk" else []
        logout = Mock()
        self.scope["BlkIscsi"] = types.SimpleNamespace(logout_portal=logout)
        response = json.loads(self.cleanup(domain=vm, cleanup_inactive_domain=True))
        self.assertTrue(response["success"])
        self.assertFalse(vm.domain.defined)
        logout.assert_not_called()
        vm.stop.assert_not_called()
        self.linux.kill_process.assert_not_called()

    def test_final_cleanup_refuses_active_or_unknown_domain(self):
        for state in [0, 1, 3, 4, 6, 9]:
            with self.subTest(state=state):
                vm = self.historical_vm(state)
                with self.assertRaises((RuntimeError, LibvirtError)):
                    self.cleanup(domain=vm, cleanup_inactive_domain=True)
                vm.stop.assert_not_called()
                self.assertTrue(vm.domain.defined)
        vm.domain.info.side_effect = LibvirtError("domain state unavailable", 38)
        with self.assertRaises((RuntimeError, LibvirtError)):
            self.cleanup(domain=vm, cleanup_inactive_domain=True)
        vm.stop.assert_not_called()
        self.linux.rm_file_checked.assert_not_called()
        self.linux.kill_process.assert_not_called()

    def test_final_cleanup_refuses_powered_off_domain_with_qemu_pid(self):
        vm = self.historical_vm()
        self.linux.find_vm_pid_by_uuid.return_value = "123"
        with self.assertRaises((RuntimeError, LibvirtError)):
            self.cleanup(domain=vm, cleanup_inactive_domain=True)
        vm.stop.assert_not_called()
        self.assertTrue(vm.domain.defined)
        self.linux.rm_file_checked.assert_not_called()
        self.linux.kill_process.assert_not_called()

    def test_generic_cleanup_never_removes_historical_domain(self):
        for option in [None, False]:
            with self.subTest(cleanup_inactive_domain=option):
                vm = self.historical_vm()
                with self.assertRaisesRegex(RuntimeError, "still has a libvirt domain"):
                    self.cleanup(domain=vm, cleanup_inactive_domain=option)
                vm.stop.assert_not_called()
                self.assertTrue(vm.domain.defined)
        self.linux.rm_file_checked.assert_not_called()

    def test_only_boolean_true_allows_inactive_domain_cleanup(self):
        for option in [0, 1, 1.0, "false", "true", "0", "1", "", [], [True], {}, {"enabled": True}]:
            with self.subTest(cleanup_inactive_domain=option):
                vm = self.historical_vm()
                with self.assertRaisesRegex(RuntimeError, "still has a libvirt domain"):
                    self.cleanup(domain=vm, cleanup_inactive_domain=option)
                self.assertTrue(vm.domain.defined)
                self.assertEqual([], vm.domain.flags)
        self.linux.rm_file_checked.assert_not_called()

    def test_final_cleanup_preserves_saved_state_and_reports_reason(self):
        for flag, reason in [(1, "managed save image exists"), (2, "with 1 snapshots")]:
            with self.subTest(resource_flag=flag), tempfile.TemporaryDirectory() as directory:
                vm = self.historical_vm()
                state_file = pathlib.Path(directory) / "existing-state"
                state_file.write_bytes(b"existing user saved state")
                vm.domain.saved_state[flag] = state_file
                with self.assertRaisesRegex((RuntimeError, LibvirtError), reason):
                    self.cleanup(domain=vm, cleanup_inactive_domain=True)
                self.assertEqual(b"existing user saved state", state_file.read_bytes())
                self.assertTrue(vm.domain.defined)
        self.linux.rm_file_checked.assert_not_called()

    def test_final_cleanup_refuses_domain_still_present_after_stop(self):
        vm = self.historical_vm()
        vm.wait_for_state_change = lambda state: True
        vm.domain.undefineFlags = Mock()
        with self.assertRaisesRegex(RuntimeError, "still has a libvirt domain"):
            self.cleanup(domain=vm, cleanup_inactive_domain=True)
        self.linux.rm_file_checked.assert_not_called()

    def test_domain_absent_cleans_only_the_exact_vm_file(self):
        response = json.loads(self.cleanup())
        self.assertTrue(response["success"])
        self.assertIs(response.get("cleanupCompleted"), True, "successful cleanup must acknowledge that the file was checked and removed")
        self.linux.rm_file_checked.assert_called_once_with("/var/lib/libvirt/qemu/nvram/" + "a" * 32 + ".fd")

    def test_domain_absent_with_qemu_pid_refuses_all_cleanup_modes(self):
        self.linux.find_vm_pid_by_uuid.return_value = "123"
        for option in [None, False, True]:
            with self.subTest(cleanup_inactive_domain=option):
                with self.assertRaises(RuntimeError):
                    self.cleanup(cleanup_inactive_domain=option)
        self.linux.rm_file_checked.assert_not_called()

    def test_any_remaining_domain_refuses_cleanup(self):
        for domain in [types.SimpleNamespace(state="Running"), types.SimpleNamespace(state="Stopped")]:
            with self.assertRaisesRegex(RuntimeError, "still has a libvirt domain"):
                self.cleanup(domain=domain)
        self.linux.rm_file_checked.assert_not_called()

    def test_invalid_uuid_does_not_reach_file_cleanup(self):
        for identifier in ["../other", "", None, "a" * 31, "a" * 32 + "/../other", "a" * 32 + "\n"]:
            with self.assertRaisesRegex(RuntimeError, "invalid vm UUID"):
                self.cleanup(identifier)
        self.linux.rm_file_checked.assert_not_called()

    def observe_start_lock_contention(self, identifier, thread_name):
        contended = threading.Event()
        case = self

        class ObservedNamedLock(lock_scope["NamedLock"]):
            def __enter__(self):
                if self.name == "vm-firmware-" + identifier and threading.current_thread().name == thread_name:
                    mutex = lock_scope["_get_lock"](self.name)
                    acquired = mutex.acquire(False)
                    if acquired:
                        mutex.release()
                    case.assertFalse(acquired, "same-UUID start must attempt the held real lock")
                    contended.set()
                return super().__enter__()

        self.scope["lock"].NamedLock = ObservedNamedLock
        return contended

    def test_recreated_uuid_start_and_cleanup_are_serialized(self):
        checked, release, started = threading.Event(), threading.Event(), threading.Event()
        errors, results, domain = [], {}, []
        identifier = "a" * 32
        with tempfile.TemporaryDirectory() as directory:
            firmware = pathlib.Path(directory) / (identifier + ".fd")
            firmware.write_bytes(b"old firmware")

            def remove_file(path):
                self.assertEqual("/var/lib/libvirt/qemu/nvram/" + identifier + ".fd", path)
                checked.set()
                if not release.wait(5):
                    raise AssertionError("cleanup barrier timed out")
                firmware.unlink()

            def start_vm(command):
                started.set()
                firmware.write_bytes(b"new firmware")
                domain.append(types.SimpleNamespace(state="Running"))

            self.scope.update(http=types.SimpleNamespace(REQUEST_BODY="body"),
                jsonobject=types.SimpleNamespace(loads=lambda text: types.SimpleNamespace(**json.loads(text)),
                    dumps=lambda value: json.dumps(vars(value))),
                StartVmResponse=lambda: types.SimpleNamespace(success=True, virtualizerInfo={}, virtualDeviceInfoList=[]),
                get_vm_by_uuid_no_retry=lambda *args: domain[0] if domain else None)
            self.linux.rm_file_checked = remove_file
            self.linux.find_vm_pid_by_uuid = Mock(side_effect=lambda uuid: "123" if domain else None)
            self.linux.enable_process_coredump = Mock()
            self.linux.set_vm_priority = Mock()
            plugin = types.SimpleNamespace(_record_operation=Mock(), VM_OP_START="Start", _start_vm=start_vm,
                get_vm_device_info=self.device_info, collect_vm_virtualizer_info=Mock(),
                _register_vm_host_file_monitor=Mock())
            plugin.clean_vm_firmware_flash = production_method("VmPlugin", "clean_vm_firmware_flash", self.scope)
            self.attach_file_check(plugin)
            clean = production_method("VmPlugin", "clean_firmware_flash", self.scope)
            start = production_method("VmPlugin", "start_vm", self.scope)
            req = {"body": json.dumps(dict(vmUuid=identifier, vmInstanceUuid=identifier,
                                             vmName="recreated", priorityConfigStruct=None))}

            def run(name, operation):
                try:
                    results[name] = json.loads(operation(plugin, req))
                except Exception as error:
                    errors.append(error)

            cleanup_thread = threading.Thread(target=run, args=("cleanup", clean))
            contended = self.observe_start_lock_contention(identifier, "firmware-recreated-start")
            start_thread = threading.Thread(target=run, args=("start", start), name="firmware-recreated-start")
            cleanup_thread.start()
            try:
                self.assertTrue(checked.wait(2), "cleanup must reach the checked file boundary")
                start_thread.start()
                self.assertTrue(contended.wait(2), "same-UUID start must attempt the held firmware lock")
                self.assertFalse(started.is_set(), "same-UUID start must wait until old cleanup releases its lock")
            finally:
                release.set()
                cleanup_thread.join(6)
                if start_thread.ident is not None:
                    start_thread.join(6)
            self.assertFalse(cleanup_thread.is_alive() or start_thread.is_alive())
            self.assertEqual([], errors)
            self.assertTrue(results["cleanup"]["success"] and results["start"]["success"])
            self.assertEqual(b"new firmware", firmware.read_bytes())
            with self.assertRaises(RuntimeError):
                clean(plugin, req)
            self.assertEqual(b"new firmware", firmware.read_bytes())

    def test_force_stop_and_recreated_uuid_start_are_serialized(self):
        for boundary in ["lookup", "stop", "ovs", "finalkill"]:
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as directory:
                identifier = "a" * 32
                firmware = pathlib.Path(directory) / (identifier + ".fd")
                firmware.write_bytes(b"old firmware")
                reached, release, started, other_started = (threading.Event() for _ in range(4))
                errors, results = [], {}
                old_vm = self.vm()
                old_domain = old_vm.domain
                current = dict(domain=old_domain, running=True, backend=True)

                def barrier(stage):
                    if stage == boundary:
                        reached.set()
                        if not release.wait(5):
                            raise AssertionError("stop barrier timed out at " + stage)

                def lookup(vm_uuid, **kwargs):
                    self.assertEqual(identifier, vm_uuid)
                    barrier("lookup")
                    return old_vm

                def stop(**kwargs):
                    barrier("stop")
                    self.stop(old_vm, **kwargs)

                def destroy_backend(vm_uuid):
                    barrier("ovs")
                    current["backend"] = False

                def kill(vm_uuid):
                    barrier("finalkill")
                    current["running"] = False

                def start_vm(command):
                    if command.vmInstanceUuid != identifier:
                        other_started.set()
                        return
                    started.set()
                    current.update(domain=Domain(), running=True, backend=True)
                    firmware.write_bytes(b"new firmware")

                old_vm.stop = stop
                old_vm.is_powered_off = lambda: not current["running"]
                old_domain.undefineFlags = lambda flags: Domain.undefineFlags(current["domain"], flags)
                self.linux.kill_process = Mock(side_effect=lambda *args, **kwargs: current.update(running=False))
                self.linux.find_vm_pid_by_uuid = Mock(return_value="123")
                self.linux.enable_process_coredump, self.linux.set_vm_priority = Mock(), Mock()
                self.scope.update(http=types.SimpleNamespace(REQUEST_BODY="body"),
                    jsonobject=types.SimpleNamespace(loads=lambda text: types.SimpleNamespace(**json.loads(text)),
                        dumps=lambda value: json.dumps(vars(value))),
                    StartVmResponse=lambda: types.SimpleNamespace(success=True, virtualizerInfo={}, virtualDeviceInfoList=[]),
                    get_vm_by_uuid=lookup, delVnicFromOvsByVmUuidIfExist=Mock(),
                    ovs=types.SimpleNamespace(isVmUseOpenvSwitch=lambda uuid: True,
                        getOvsCtl=lambda **kwargs: types.SimpleNamespace(destoryNicBackend=destroy_backend)))
                plugin = types.SimpleNamespace(_record_operation=Mock(), VM_OP_START="Start", _start_vm=start_vm,
                    kill_vm=kill, get_vm_device_info=self.device_info, collect_vm_virtualizer_info=Mock(),
                    _register_vm_host_file_monitor=Mock())
                stop_handler = production_method("VmPlugin", "_stop_vm", self.scope)
                start_handler = production_method("VmPlugin", "start_vm", self.scope)
                command = types.SimpleNamespace(uuid=identifier, type="force", timeout=10)

                def request(uuid):
                    return {"body": json.dumps(dict(vmInstanceUuid=uuid, vmName="recreated", priorityConfigStruct=None))}

                def run(name, operation):
                    try:
                        results[name] = operation()
                    except Exception as error:
                        errors.append(error)

                stop_thread = threading.Thread(target=run, args=("stop", lambda: stop_handler(plugin, command)))
                contended = self.observe_start_lock_contention(identifier, "force-stop-recreated-start")
                start_thread = threading.Thread(target=run, args=("start", lambda: start_handler(plugin, request(identifier))),
                                                name="force-stop-recreated-start")
                other_thread = threading.Thread(target=run, args=("other", lambda: start_handler(plugin, request("b" * 32))))
                stop_thread.start()
                try:
                    self.assertTrue(reached.wait(2), "stop must reach its " + boundary + " boundary")
                    start_thread.start()
                    other_thread.start()
                    self.assertTrue(contended.wait(2), "same-UUID start must attempt the held firmware lock")
                    self.assertTrue(other_started.wait(2), "stopping one VM must not block another UUID")
                    self.assertFalse(started.is_set(), "same-UUID start must wait through " + boundary)
                finally:
                    release.set()
                    for worker in [stop_thread, start_thread, other_thread]:
                        if worker.ident is not None:
                            worker.join(6)
                self.assertFalse(any(worker.is_alive() for worker in [stop_thread, start_thread, other_thread]))
                self.assertEqual([], errors)
                self.assertTrue(json.loads(results["start"])["success"])
                self.assertTrue(current["domain"].defined and current["running"] and current["backend"])
                self.assertEqual(b"new firmware", firmware.read_bytes())

    def test_open_file_error_is_propagated_without_forced_removal(self):
        self.linux.rm_file_checked.side_effect = OSError("file is still open")
        with self.assertRaisesRegex(OSError, "still open"):
            self.cleanup()
        self.linux.rm_file_force.assert_not_called()

if __name__ == "__main__":
    unittest.main()
