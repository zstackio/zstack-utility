import ast
import errno
import os
import shutil
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import Mock, patch


class TestCleanPycache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctl_py = Path(__file__).resolve().parents[3] / "zstackctl" / "zstackctl" / "ctl.py"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            module = ast.parse(ctl_py.read_text(encoding="utf-8"))
        start = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "StartCmd")
        local = next(node for node in start.body if isinstance(node, ast.FunctionDef) and node.name == "_start_local")
        clean = next(node for node in local.body if isinstance(node, ast.FunctionDef) and node.name == "clean_pycache")
        cls.clean_code = compile(ast.Module(body=[clean], type_ignores=[]), str(ctl_py), "exec")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)
        self.files = self.home / "ansible" / "files"
        self.warn = Mock()
        namespace = {"os": os, "rmtree": shutil.rmtree, "warn": self.warn}
        exec(self.clean_code, namespace)
        self.clean_pycache = namespace["clean_pycache"]
        expanduser = patch("os.path.expanduser", return_value=str(self.home))
        expanduser.start()
        self.addCleanup(expanduser.stop)

    def write_file(self, relative):
        path = self.files / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture content")
        return path

    def test_removes_legacy_bytecode_from_all_module_depths(self):
        caches = [self.write_file(name) for name in (
            "zstacklib.pyc", "zstacklib/zstacklib.pyc", "kvm/kvm.pyo", "kvm/nested/helper.pyc")]

        self.clean_pycache()

        for cache in caches:
            self.assertFalse(cache.exists(), str(cache))

    def test_removes_python3_cache_directories_recursively(self):
        for name in ("__pycache__/root.pyc", "kvm/__pycache__/nested/__pycache__/helper.pyc"):
            self.write_file(name)

        self.clean_pycache()

        self.assertFalse((self.files / "__pycache__").exists())
        self.assertFalse((self.files / "kvm/__pycache__").exists())

    def test_keeps_sources_and_non_cache_files_across_repeated_cleanup(self):
        kept = [self.write_file(name) for name in (
            "zstacklib.py", "config.yaml", "module.tar.gz", "module.pyc.bak", "module.pyc/source.py")]
        cache = self.write_file("module.pyo")

        self.clean_pycache()
        self.clean_pycache()

        self.assertFalse(cache.exists())
        for path in kept:
            self.assertEqual(b"fixture content", path.read_bytes())
        self.assertTrue((self.files / "module.pyc").is_dir())

    def test_does_not_follow_directory_links_or_change_pycache_link_behavior(self):
        external = self.home / "external"
        external.mkdir()
        for name in ("external.pyc", "source.py"):
            (external / name).write_bytes(b"external content")
        self.files.mkdir(parents=True)
        directory_link = self.files / "linked-module"
        directory_link.symlink_to(external, target_is_directory=True)
        cache_link = self.files / "__pycache__"
        cache_link.symlink_to(external, target_is_directory=True)

        self.clean_pycache()

        self.assertTrue(directory_link.is_symlink())
        self.assertTrue(cache_link.is_symlink())
        for name in ("external.pyc", "source.py"):
            self.assertEqual(b"external content", (external / name).read_bytes())
        self.warn.assert_called_once()
        self.assertIn(str(cache_link), self.warn.call_args[0][0])

    def test_unlinks_cache_file_links_including_broken_links_without_removing_target(self):
        external = self.home / "external.pyc"
        external.write_bytes(b"external content")
        self.files.mkdir(parents=True)
        cache_link = self.files / "linked.pyc"
        cache_link.symlink_to(external)
        broken_link = self.files / "broken.pyo"
        broken_link.symlink_to(self.home / "missing.pyo")

        self.clean_pycache()

        self.assertFalse(os.path.lexists(cache_link))
        self.assertFalse(os.path.lexists(broken_link))
        self.assertEqual(b"external content", external.read_bytes())

    def test_missing_root_is_noop(self):
        self.clean_pycache()

        self.assertFalse(self.files.exists())
        self.warn.assert_not_called()

    def test_empty_root_is_noop(self):
        self.files.mkdir(parents=True)

        self.clean_pycache()
        self.clean_pycache()

        self.assertEqual([], list(self.files.iterdir()))
        self.warn.assert_not_called()

    def test_cache_file_removal_failure_propagates_original_error(self):
        cache = self.write_file("zstacklib.pyc")
        failure = OSError(errno.EACCES, "Permission denied", str(cache))

        with patch("os.remove", side_effect=failure):
            with self.assertRaises(OSError) as raised:
                self.clean_pycache()

        self.assertIs(failure, raised.exception)
        self.assertEqual(str(cache), raised.exception.filename)
        self.assertTrue(cache.exists())
        self.warn.assert_not_called()
