import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _load_script(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(REPO_ROOT, relative_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ZStackZramPackageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="zstack-zram-package-")
        self.source = os.path.join(self.temp_dir, "zstack-zram")
        files = {
            "packaging/rpm/zram-memory.spec": (
                "%global zram_rpm_version_default 5.5.48\n"
                "%global zram_rpm_release_default 3\n"
            ),
            "packaging/build-rpm.sh": "#!/bin/sh\nexit 0\n",
            "service/go.mod": "module example.invalid/zstack-zram/service\n",
            "service/packaging/systemd/zram-memory.service": "[Unit]\nDescription=test\n",
            "cli/go.mod": "module example.invalid/zstack-zram/cli\n",
        }
        for relative, content in files.items():
            path = os.path.join(self.source, relative)
            if not os.path.isdir(os.path.dirname(path)):
                os.makedirs(os.path.dirname(path))
            with open(path, "w") as stream:
                stream.write(content)
        subprocess.check_call(["git", "init", "-q"], cwd=self.source)
        subprocess.check_call(["git", "add", "."], cwd=self.source)
        subprocess.check_call(
            ["git", "-c", "user.name=ZRAM Test", "-c",
             "user.email=zram-test@example.invalid", "commit", "-q", "-m", "fixture"],
            cwd=self.source,
        )
        self.prepare = _load_script(
            "prepare_zstack_zram_build_metadata_test",
            "zstackbuild/scripts/prepare_zstack_zram_build_metadata.py",
        )
        self.stage = _load_script(
            "stage_memory_optimization_rpm_test",
            "kvmagent/scripts/stage_memory_optimization_rpm.py",
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_prepare_uses_spec_defaults_and_explicit_overrides(self):
        profiles = "h84r,alinux4"
        default = self.prepare.prepare(
            self.source, os.path.join(self.temp_dir, "snapshot-default"),
            os.path.join(self.temp_dir, "default", "metadata.properties"),
            "", "", None, "unit-test", profiles,
        )
        override = self.prepare.prepare(
            self.source, os.path.join(self.temp_dir, "snapshot-override"),
            os.path.join(self.temp_dir, "override", "metadata.properties"),
            "5.5.38", "fixture", None, "unit-test", profiles,
        )
        self.assertEqual(("5.5.48", "3"),
                         (default["zstackzram.version"], default["zstackzram.release"]))
        self.assertEqual(("5.5.38", "fixture"),
                         (override["zstackzram.version"], override["zstackzram.release"]))

    def _stage_fixture(self, output):
        rpm_path = os.path.join(self.temp_dir, "downloaded-rpm")
        with open(rpm_path, "wb") as stream:
            stream.write(b"fixture rpm")
        manifest_path = os.path.join(self.temp_dir, "BUILD-MANIFEST.json")
        manifest = self._build_manifest()
        with open(manifest_path, "w") as stream:
            json.dump(manifest, stream)
        files = set(self.stage.REQUIRED_RPM_FILES)
        runtime = {path: {"bytes": 1, "sha256": "e" * 64}
                   for path in self.stage.RUNTIME_BINARIES}
        metadata = (
            "zstack-zram", "5.5.48", "3.el8", "x86_64", files, sorted(files), "",
            {"/etc/zram-memory/config.json"},
            "/etc/zram-memory/config.json cn", runtime,
        )
        with mock.patch.object(self.stage, "_query_package", return_value=metadata):
            inventory = self.stage.stage(rpm_path, manifest_path, output, None, None, ["h84r"])
        return inventory, manifest

    @staticmethod
    def _build_manifest():
        return {
            "schemaVersion": 1, "package": "zstack-zram", "rpmVersion": "5.5.48",
            "rpmRelease": "3", "sourceRevision": "a" * 40,
            "sourceSnapshotSha256": "b" * 64, "dirtyPatchSha256": "c" * 64,
            "sourceFiles": [{
                "path": "service/packaging/systemd/zram-memory.service",
                "sha256": "d" * 64,
            }],
        }

    def test_stage_uses_manifest_pins_and_canonical_nevra_filename(self):
        output = os.path.join(self.temp_dir, "stage")
        inventory, manifest = self._stage_fixture(output)
        filename = "zstack-zram-5.5.48-3.el8.x86_64.rpm"
        self.assertEqual(filename, inventory["package"]["filename"])
        self.assertEqual(manifest["sourceSnapshotSha256"],
                         inventory["source"]["sourceSnapshotSha256"])
        self.assertTrue(os.path.isfile(os.path.join(output, filename)))

    def test_stage_rejects_mismatched_explicit_source_pins(self):
        rpm_path = os.path.join(self.temp_dir, "downloaded-rpm")
        with open(rpm_path, "wb") as stream:
            stream.write(b"fixture rpm")
        manifest_path = os.path.join(self.temp_dir, "BUILD-MANIFEST.json")
        with open(manifest_path, "w") as stream:
            json.dump(self._build_manifest(), stream)
        with self.assertRaisesRegex(ValueError, "SOURCE_SNAPSHOT_PIN_MISMATCH"):
            self.stage.stage(
                rpm_path, manifest_path, os.path.join(self.temp_dir, "rejected"),
                "f" * 64, "c" * 64, ["h84r"],
            )


if __name__ == "__main__":
    unittest.main()
