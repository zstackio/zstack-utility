import unittest
import contextlib
import json
import os
import sys
import types


def _install_import_stubs():
    package_dir = os.path.dirname(os.path.dirname(__file__))

    kvmagent_pkg = types.ModuleType("kvmagent")
    kvmagent_pkg.__path__ = [package_dir]
    kvmagent_mod = types.ModuleType("kvmagent.kvmagent")

    class KvmAgent(object):
        pass

    class AgentResponse(object):
        def __init__(self):
            self.success = True
            self.error = None

    kvmagent_mod.KvmAgent = KvmAgent
    kvmagent_mod.AgentResponse = AgentResponse
    kvmagent_mod.replyerror = lambda func: func
    kvmagent_mod.get_http_server = lambda: None
    kvmagent_pkg.kvmagent = kvmagent_mod
    sys.modules["kvmagent"] = kvmagent_pkg
    sys.modules["kvmagent.kvmagent"] = kvmagent_mod

    zstacklib_pkg = types.ModuleType("zstacklib")
    zstacklib_utils_pkg = types.ModuleType("zstacklib.utils")
    sys.modules["zstacklib"] = zstacklib_pkg
    sys.modules["zstacklib.utils"] = zstacklib_utils_pkg

    http_mod = types.ModuleType("zstacklib.utils.http")
    http_mod.REQUEST_BODY = "body"
    zstacklib_utils_pkg.http = http_mod
    sys.modules["zstacklib.utils.http"] = http_mod

    class AttrDict(dict):
        def __getattr__(self, item):
            return self[item]

        def hasattr(self, item):
            return item in self

    def to_attr(value):
        if isinstance(value, dict):
            ret = AttrDict()
            for k, v in value.items():
                ret[k] = to_attr(v)
            return ret
        if isinstance(value, list):
            return [to_attr(v) for v in value]
        return value

    jsonobject_mod = types.ModuleType("zstacklib.utils.jsonobject")
    jsonobject_mod.loads = lambda value: to_attr(json.loads(value)) if isinstance(value, str) else to_attr(value)
    jsonobject_mod.dumps = lambda value: json.dumps(value if isinstance(value, dict) else value.__dict__)
    zstacklib_utils_pkg.jsonobject = jsonobject_mod
    sys.modules["zstacklib.utils.jsonobject"] = jsonobject_mod

    log_mod = types.ModuleType("zstacklib.utils.log")

    class Logger(object):
        def warn(self, msg):
            pass

        def debug(self, msg):
            pass

    log_mod.get_logger = lambda name: Logger()
    zstacklib_utils_pkg.log = log_mod
    sys.modules["zstacklib.utils.log"] = log_mod

    bash_mod = types.ModuleType("zstacklib.utils.bash")
    bash_mod.bash_errorout = lambda cmd: ""
    bash_mod.bash_roe = lambda cmd: (0, "", "")
    bash_mod.in_bash = lambda func: func
    zstacklib_utils_pkg.bash = bash_mod
    sys.modules["zstacklib.utils.bash"] = bash_mod

    linux_mod = types.ModuleType("zstacklib.utils.linux")
    linux_mod.shellquote = lambda value: value
    linux_mod.rm_file_force = lambda path: None
    linux_mod.get_exception_stacktrace = lambda: ""
    linux_mod.catch_bad_alloc_exception = lambda ret, err: False
    zstacklib_utils_pkg.linux = linux_mod
    sys.modules["zstacklib.utils.linux"] = linux_mod

    plugins_pkg = types.ModuleType("kvmagent.plugins")
    plugins_pkg.__path__ = [os.path.join(package_dir, "plugins")]
    sys.modules["kvmagent.plugins"] = plugins_pkg

    volume_secret_mod = types.ModuleType("kvmagent.plugins.volume_secret")

    @contextlib.contextmanager
    def luks_secret_channel(encrypted_dek):
        yield "/tmp/luks-secret"

    volume_secret_mod.luks_secret_channel = luks_secret_channel
    plugins_pkg.volume_secret = volume_secret_mod
    sys.modules["kvmagent.plugins.volume_secret"] = volume_secret_mod


_install_import_stubs()

from kvmagent.plugins import zbs_storage_plugin
from zstacklib.utils import jsonobject


class TestZbsStoragePlugin(unittest.TestCase):
    def test_start_registers_luks_resize_path(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        paths = []

        class HttpServer(object):
            def register_async_uri(self, path, handler):
                paths.append((path, handler.__name__))

        original_get_http_server = zbs_storage_plugin.kvmagent.get_http_server
        try:
            zbs_storage_plugin.kvmagent.get_http_server = lambda: HttpServer()

            plugin.start()

            self.assertIn((plugin.LUKS_RESIZE_PATH, "luks_resize"), paths)
        finally:
            zbs_storage_plugin.kvmagent.get_http_server = original_get_http_server

    def test_snapshot_install_path_is_passed_to_qemu_without_zbs_cli_lookup(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()

        path = plugin._cbd_qemu_path("cbd:physical/logical/volume@42")

        self.assertEqual("cbd:physical/logical/volume@42_zbs_:/etc/zbs/client.conf", path)

    def test_snapshot_path_adds_cbd_prefix_without_zbs_cli_lookup(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()

        path = plugin._cbd_qemu_path("physical/logical/volume@1")

        self.assertEqual("cbd:physical/logical/volume@1_zbs_:/etc/zbs/client.conf", path)

    def test_luks_clone_preserves_luks_source_bits(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        commands = []
        original_errorout = zbs_storage_plugin.bash.bash_errorout
        try:
            zbs_storage_plugin.bash.bash_errorout = lambda cmd: commands.append(cmd) or ""
            plugin._is_luks_volume = lambda install_path, encrypted_dek=None: True
            plugin._raw_cbd_size = lambda install_path: 4096
            plugin._resize_luks_target = lambda install_path, virtual_size, encrypted_dek: None

            plugin._clone_plain_to_luks("cbd:physical/logical/source", "cbd:physical/logical/target",
                                        "sealed-dek", 1024)

            self.assertEqual(1, len(commands))
            self.assertIn("-n", commands[0])
            self.assertIn("-f raw", commands[0])
            self.assertIn("-O raw", commands[0])
            self.assertNotIn("-O luks", commands[0])
            self.assertNotIn("key-secret=luks_sec", commands[0])
        finally:
            zbs_storage_plugin.bash.bash_errorout = original_errorout

    def test_luks_clone_converts_plain_source_to_luks_target(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        commands = []
        removed = []
        original_errorout = zbs_storage_plugin.bash.bash_errorout
        original_rm = zbs_storage_plugin.linux.rm_file_force
        original_secret_channel = zbs_storage_plugin.volume_secret.luks_secret_channel
        try:
            zbs_storage_plugin.bash.bash_errorout = lambda cmd: commands.append(cmd) or ""
            zbs_storage_plugin.linux.rm_file_force = lambda path: removed.append(path)
            secret_paths = iter(["/tmp/luks-secret-create", "/tmp/luks-secret-convert"])

            @contextlib.contextmanager
            def secret_channel(encrypted_dek):
                yield next(secret_paths)

            zbs_storage_plugin.volume_secret.luks_secret_channel = secret_channel
            plugin._is_luks_volume = lambda install_path, encrypted_dek=None: False
            plugin._new_luks_temp_path = lambda: "/tmp/zbs-luks-test.img"
            plugin._resize_luks_target = lambda install_path, virtual_size, encrypted_dek: None

            plugin._clone_plain_to_luks("cbd:physical/logical/source", "cbd:physical/logical/target",
                                        "sealed-dek", 13631488)

            self.assertEqual(3, len(commands))
            self.assertIn("-f luks", commands[0])
            self.assertIn("key-secret=luks_sec", commands[0])
            self.assertIn("file=/tmp/luks-secret-create", commands[0])
            self.assertIn("/tmp/zbs-luks-test.img", commands[0])
            self.assertIn("convert -n -S 4k", commands[1])
            self.assertIn("-O raw", commands[1])
            self.assertIn("/tmp/zbs-luks-test.img", commands[1])
            self.assertIn("convert -n --target-image-opts", commands[2])
            self.assertIn("driver=luks,key-secret=luks_sec,file.driver=cbd", commands[2])
            self.assertIn("file=/tmp/luks-secret-convert", commands[2])
            self.assertIn("cbd:physical/logical/target_zbs_:/etc/zbs/client.conf", commands[2])
            self.assertNotIn("/tmp/zbs-luks-test.img", commands[2])
            self.assertEqual(["/tmp/zbs-luks-test.img"], removed)
        finally:
            zbs_storage_plugin.bash.bash_errorout = original_errorout
            zbs_storage_plugin.linux.rm_file_force = original_rm
            zbs_storage_plugin.volume_secret.luks_secret_channel = original_secret_channel

    def test_luks_clone_assumes_target_exists_without_zbs_cli(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        commands = []
        original_errorout = zbs_storage_plugin.bash.bash_errorout
        try:
            def run(cmd):
                commands.append(cmd)
                if cmd.startswith("/usr/bin/zbs"):
                    raise AssertionError("kvmagent must not execute zbs CLI")
                return ""

            zbs_storage_plugin.bash.bash_errorout = run
            plugin._is_luks_volume = lambda install_path, encrypted_dek=None: False
            plugin._new_luks_temp_path = lambda: "/tmp/zbs-luks-test.img"
            plugin._resize_luks_target = lambda install_path, virtual_size, encrypted_dek: None

            plugin._clone_plain_to_luks("cbd:physical/logical/source", "cbd:physical/logical/target",
                                        "sealed-dek", 13631488)

            self.assertEqual(3, len(commands))
            self.assertTrue(all(not cmd.startswith("/usr/bin/zbs") for cmd in commands))
        finally:
            zbs_storage_plugin.bash.bash_errorout = original_errorout

    def test_luks_create_empty_formats_local_luks_before_copying_to_cbd(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        commands = []
        removed = []
        original_errorout = zbs_storage_plugin.bash.bash_errorout
        original_rm = zbs_storage_plugin.linux.rm_file_force
        try:
            zbs_storage_plugin.bash.bash_errorout = lambda cmd: commands.append(cmd) or ""
            zbs_storage_plugin.linux.rm_file_force = lambda path: removed.append(path)
            plugin._new_luks_temp_path = lambda: "/tmp/zbs-luks-empty.img"

            plugin._create_luks_volume("cbd:physical/logical/target", 13631488, "sealed-dek")

            self.assertEqual(2, len(commands))
            self.assertIn("qemu-img create", commands[0])
            self.assertIn("-f luks", commands[0])
            self.assertIn("/tmp/zbs-luks-empty.img", commands[0])
            self.assertIn("convert -n", commands[1])
            self.assertIn("-O raw", commands[1])
            self.assertIn("cbd:physical/logical/target_zbs_:/etc/zbs/client.conf", commands[1])
            self.assertEqual(["/tmp/zbs-luks-empty.img"], removed)
        finally:
            zbs_storage_plugin.bash.bash_errorout = original_errorout
            zbs_storage_plugin.linux.rm_file_force = original_rm

    def test_luks_create_empty_assumes_target_exists_without_zbs_cli(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        commands = []
        original_errorout = zbs_storage_plugin.bash.bash_errorout
        try:
            def run(cmd):
                commands.append(cmd)
                if cmd.startswith("/usr/bin/zbs"):
                    raise AssertionError("kvmagent must not execute zbs CLI")
                return ""

            zbs_storage_plugin.bash.bash_errorout = run
            plugin._new_luks_temp_path = lambda: "/tmp/zbs-luks-empty.img"

            plugin._create_luks_volume("cbd:physical/logical/target", 13631488, "sealed-dek")

            self.assertEqual(2, len(commands))
            self.assertTrue(all(not cmd.startswith("/usr/bin/zbs") for cmd in commands))
        finally:
            zbs_storage_plugin.bash.bash_errorout = original_errorout

    def test_luks_clone_stops_when_source_format_probe_fails(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        commands = []
        original_errorout = zbs_storage_plugin.bash.bash_errorout
        try:
            def fail_probe(cmd):
                commands.append(cmd)
                raise Exception("probe failed")

            zbs_storage_plugin.bash.bash_errorout = fail_probe

            with self.assertRaises(Exception):
                plugin._clone_plain_to_luks("pool/source", "pool/target", "sealed-dek", 1024)

            self.assertEqual(1, len(commands))
            self.assertIn("qemu-img info", commands[0])
        finally:
            zbs_storage_plugin.bash.bash_errorout = original_errorout

    def test_luks_handlers_return_failure_when_required_path_is_missing(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        cases = [
            (plugin.luks_clone, {"encryptedDek": "sealed-dek"}, "failed to clone ZBS LUKS volume"),
            (plugin.luks_create_empty, {"size": 1024, "encryptedDek": "sealed-dek"},
             "failed to create empty ZBS LUKS volume"),
            (plugin.luks_encrypt_in_place, {"encryptedDek": "sealed-dek"},
             "failed to encrypt ZBS volume"),
            (plugin.luks_resize, {"virtualSize": 2048, "encryptedDek": "sealed-dek"},
             "failed to resize ZBS LUKS volume"),
        ]

        for handler, body, err in cases:
            rsp = jsonobject.loads(handler({"body": json.dumps(body)}))

            self.assertFalse(rsp.success)
            self.assertIn(err, rsp.error)
            self.assertIn("<missing>", rsp.error)

    def test_luks_resize_expands_raw_cbd_before_luks_virtual_size(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        commands = []
        original_errorout = zbs_storage_plugin.bash.bash_errorout
        sizes = iter([1024, 1024, 2048])
        try:
            plugin._is_luks_volume = lambda install_path, encrypted_dek=None: True
            plugin._raw_cbd_size = lambda install_path: 4096
            plugin._resize_raw_cbd_if_needed = lambda install_path, required_size: commands.append(
                "raw-resize %s %s" % (install_path, required_size))

            def info(cmd):
                commands.append(cmd)
                return json.dumps({"virtual-size": next(sizes)})

            zbs_storage_plugin.bash.bash_errorout = info

            plugin._resize_luks_target("cbd:physical/logical/volume", 2048, "sealed-dek")

            self.assertEqual(4, len(commands))
            self.assertIn("qemu-img info", commands[0])
            self.assertEqual("raw-resize cbd:physical/logical/volume 5120", commands[1])
            self.assertIn("qemu-img info", commands[2])
            self.assertIn("qemu-img resize", commands[3])
            self.assertIn("2048", commands[3])
        finally:
            zbs_storage_plugin.bash.bash_errorout = original_errorout

    def test_luks_resize_does_not_shrink(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        commands = []
        original_errorout = zbs_storage_plugin.bash.bash_errorout
        try:
            plugin._is_luks_volume = lambda install_path, encrypted_dek=None: True
            zbs_storage_plugin.bash.bash_errorout = lambda cmd: commands.append(cmd) or json.dumps({"virtual-size": 2048})

            plugin._resize_luks_target("cbd:physical/logical/volume", 1024, "sealed-dek")

            self.assertEqual(1, len(commands))
            self.assertIn("qemu-img info", commands[0])
        finally:
            zbs_storage_plugin.bash.bash_errorout = original_errorout

    def test_luks_resize_handler_resizes_target_and_reports_actual_size(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        calls = []
        try:
            plugin._resize_luks_target = lambda install_path, virtual_size, encrypted_dek: calls.append(
                (install_path, virtual_size, encrypted_dek))
            plugin._raw_cbd_actual_size = lambda install_path: 4096

            rsp = jsonobject.loads(plugin.luks_resize({
                "body": json.dumps({
                    "installPath": "cbd:physical/logical/volume",
                    "virtualSize": 2048,
                    "encryptedDek": "sealed-dek"
                })
            }))

            self.assertTrue(rsp.success)
            self.assertEqual(4096, rsp.actualSize)
            self.assertEqual([("cbd:physical/logical/volume", 2048, "sealed-dek")], calls)
        finally:
            pass

    def test_luks_resize_handler_requires_positive_virtual_size(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        calls = []
        plugin._resize_luks_target = lambda install_path, virtual_size, encrypted_dek: calls.append(
            (install_path, virtual_size, encrypted_dek))

        for body in [
            {"installPath": "cbd:physical/logical/volume", "encryptedDek": "sealed-dek"},
            {"installPath": "cbd:physical/logical/volume", "virtualSize": 0, "encryptedDek": "sealed-dek"},
        ]:
            rsp = jsonobject.loads(plugin.luks_resize({"body": json.dumps(body)}))

            self.assertFalse(rsp.success)
            self.assertIn("virtualSize is required", rsp.error)

        self.assertEqual([], calls)

    def test_luks_encrypt_in_place_returns_new_install_path_without_replacing_original(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        calls = []
        try:
            plugin._is_luks_volume = lambda install_path, encrypted_dek=None: False
            plugin._clone_plain_to_luks = lambda src_path, dst_path, encrypted_dek: calls.append(
                ("clone", src_path, dst_path, encrypted_dek))

            new_path = plugin._encrypt_luks_in_place("cbd:physical/logical/volume",
                                                     "cbd:physical/logical/volume-encrypted-new",
                                                     "sealed-dek")

            self.assertEqual("cbd:physical/logical/volume-encrypted-new", new_path)
            self.assertEqual([
                ("clone", "cbd:physical/logical/volume", new_path, "sealed-dek")
            ], calls)
        finally:
            pass

    def test_luks_encrypt_in_place_fails_when_bits_are_already_luks(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        calls = []
        plugin._is_luks_volume = lambda install_path, encrypted_dek=None: True
        plugin._clone_plain_to_luks = lambda src_path, dst_path, encrypted_dek: calls.append(
            ("clone", src_path, dst_path, encrypted_dek))

        with self.assertRaises(Exception) as ctx:
            plugin._encrypt_luks_in_place("cbd:physical/logical/volume",
                                          "cbd:physical/logical/volume-encrypted-new",
                                          "sealed-dek")

        self.assertIn("already LUKS", str(ctx.exception))
        self.assertEqual([], calls)

    def test_luks_encrypt_in_place_handler_reports_new_install_path(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        try:
            plugin._encrypt_luks_in_place = lambda install_path, target_install_path, encrypted_dek: target_install_path
            plugin._raw_cbd_actual_size = lambda install_path: 4096

            rsp = jsonobject.loads(plugin.luks_encrypt_in_place({
                "body": json.dumps({
                    "installPath": "cbd:physical/logical/volume",
                    "targetInstallPath": "cbd:physical/logical/volume-encrypted-new",
                    "encryptedDek": "sealed-dek"
                })
            }))

            self.assertTrue(rsp.success)
            self.assertEqual("cbd:physical/logical/volume-encrypted-new", rsp.installPath)
            self.assertEqual(4096, rsp.actualSize)
        finally:
            pass

    def test_luks_encrypt_in_place_handler_uses_supplied_target_without_zbs_cli(self):
        plugin = zbs_storage_plugin.ZbsStoragePlugin()
        calls = []
        original_errorout = zbs_storage_plugin.bash.bash_errorout
        try:
            def run(cmd):
                if cmd.startswith("/usr/bin/zbs"):
                    raise AssertionError("kvmagent must not execute zbs CLI")
                return ""

            zbs_storage_plugin.bash.bash_errorout = run
            plugin._is_luks_volume = lambda install_path, encrypted_dek=None: False
            plugin._clone_plain_to_luks = lambda src_path, dst_path, encrypted_dek: calls.append(
                ("clone", src_path, dst_path, encrypted_dek))
            plugin._raw_cbd_actual_size = lambda install_path: 4096

            rsp = jsonobject.loads(plugin.luks_encrypt_in_place({
                "body": json.dumps({
                    "installPath": "cbd:physical/logical/source",
                    "targetInstallPath": "cbd:physical/logical/target",
                    "encryptedDek": "sealed-dek"
                })
            }))

            self.assertTrue(rsp.success)
            self.assertEqual("cbd:physical/logical/target", rsp.installPath)
            self.assertEqual([("clone", "cbd:physical/logical/source", "cbd:physical/logical/target",
                               "sealed-dek")], calls)
        finally:
            zbs_storage_plugin.bash.bash_errorout = original_errorout


if __name__ == "__main__":
    unittest.main()
