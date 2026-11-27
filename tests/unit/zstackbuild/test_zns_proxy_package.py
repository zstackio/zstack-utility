import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..")
)
BUILD_FILE = os.path.join(REPO_ROOT, "zstackbuild", "build.xml")


class ZnsProxyPackageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="zns-proxy-package-")
        self.workspace = os.path.join(self.temp_dir, "bin")
        self.build_dir = os.path.join(self.temp_dir, "build")
        os.makedirs(self.workspace)
        os.symlink(REPO_ROOT, os.path.join(self.workspace, "zstack-utility"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _write_go(self, version):
        path = os.path.join(self.temp_dir, "go")
        with open(path, "w") as stream:
            stream.write("#!/bin/sh\n")
            stream.write("echo 'go version %s linux/amd64'\n" % version)
        os.chmod(path, 0o755)
        return path

    def _create_zns_source(self):
        source = os.path.join(self.workspace, "zstack-zns")
        os.makedirs(source)
        with open(os.path.join(source, "go.mod"), "w") as stream:
            stream.write("module example.com/zstack-zns\n\ngo 1.26\n")
        with open(os.path.join(source, "Makefile"), "w") as stream:
            stream.write(
                "zns-proxy:\n"
                "\t@mkdir -p target\n"
                "\t@\"$(GO)\" version > target/go-version.log\n"
                "\t@printf '%s\\n' \"$(ARCH)\" > target/zns-proxy-arch.log\n"
                "\t@printf 'fake-zns-proxy\\n' > target/zns-proxy.bin\n"
                "print-zns-proxy-version:\n"
                "\t@printf '1.2.0.1\\n'\n"
            )
        subprocess.check_call(["git", "init", "-q"], cwd=source)
        subprocess.check_call(["git", "add", "Makefile", "go.mod"], cwd=source)
        subprocess.check_call(
            [
                "git",
                "-c",
                "user.name=ZNS Build Test",
                "-c",
                "user.email=zns-build-test@example.invalid",
                "commit",
                "-q",
                "-m",
                "test fixture",
            ],
            cwd=source,
        )
        return source

    def _run_ant(self, go_path, targets):
        command = [
            "ant",
            "-f",
            BUILD_FILE,
            "-Dzstack_build_root=%s" % self.workspace,
            "-Dzstackzns.go=%s" % go_path,
            "-Dbuild.dir=%s" % self.build_dir,
            "-Dbin.version=5.5.28-test",
        ] + targets
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

    def test_build_fails_when_zns_source_is_missing(self):
        result = self._run_ant(
            self._write_go("go1.26.0"),
            ["build-zstack-zns-proxy"],
        )

        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("zstack-zns", result.stdout)

    def test_build_fails_when_go_is_not_1_26(self):
        self._create_zns_source()

        result = self._run_ant(
            self._write_go("go1.24.12"),
            ["build-zstack-zns-proxy"],
        )

        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("requires Go 1.26", result.stdout)
        self.assertFalse(
            os.path.exists(
                os.path.join(
                    self.workspace,
                    "zstack-zns",
                    "target",
                    "zns-proxy.bin",
                )
            )
        )

    def test_build_assemble_and_verify_proxy_only_package(self):
        source = self._create_zns_source()
        result = self._run_ant(
            self._write_go("go1.26.11"),
            [
                "build-zstack-zns-proxy",
                "assemble-zstack-zns-proxy",
                "verify-zstack-zns-proxy-package",
            ],
        )

        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("zstack-zns Go toolchain: go version go1.26.11", result.stdout)
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source, universal_newlines=True
        ).strip()
        self.assertIn("zstack-zns source commit: %s" % commit, result.stdout)

        package = os.path.join(self.build_dir, "zns-proxy", "zns-proxy.bin")
        manifest_path = os.path.join(
            self.build_dir,
            "zns-proxy",
            "zns-proxy-manifest.json",
        )
        self.assertTrue(os.path.isfile(package))
        self.assertTrue(os.path.isfile(manifest_path))
        with open(manifest_path) as stream:
            manifest = json.load(stream)
        with open(package, "rb") as stream:
            package_sha256 = hashlib.sha256(stream.read()).hexdigest()
        self.assertEqual(package_sha256, manifest["sha256"])
        self.assertEqual(["amd64"], manifest["arch"])
        with open(os.path.join(source, "target", "zns-proxy-arch.log")) as stream:
            self.assertEqual("amd64", stream.read().strip())
        self.assertEqual("zns-proxy", manifest["component"])
        self.assertEqual("1.2.0.1", manifest["version"])

        ansible_dir = os.path.join(
            self.build_dir,
            "zstack-assemble",
            "WEB-INF",
            "classes",
            "ansible",
        )
        expected = [
            os.path.join(ansible_dir, "znsproxy", "zns-proxy.bin"),
            os.path.join(
                ansible_dir,
                "znsproxy",
                "zns-proxy-manifest.json",
            ),
            os.path.join(ansible_dir, "znsproxy", "znsproxy.py"),
            os.path.join(ansible_dir, "znsproxy.py"),
        ]
        for path in expected:
            self.assertTrue(os.path.isfile(path), path)

        self.assertFalse(os.path.exists(os.path.join(ansible_dir, "znsagentansible")))
        for root, _, files in os.walk(ansible_dir):
            for name in files:
                self.assertFalse(
                    name.startswith("zns-agent") and name.endswith(".bin"),
                    os.path.join(root, name),
                )

        assembled_manifest = expected[1]
        invalid_fields = [
            ("version", 1, "manifest version must be a non-empty string"),
            ("sha256", None, "manifest sha256 must be a non-empty string"),
            ("arch", [0], "manifest arch must be a non-empty list of strings"),
            ("buildTime", True, "manifest buildTime must be a non-empty string"),
        ]
        for field, value, message in invalid_fields:
            invalid_manifest = manifest.copy()
            invalid_manifest[field] = value
            with open(assembled_manifest, "w") as stream:
                json.dump(invalid_manifest, stream)
            guard_result = self._run_ant(
                self._write_go("go1.26.11"),
                ["verify-zstack-zns-proxy-package"],
            )
            self.assertNotEqual(0, guard_result.returncode, guard_result.stdout)
            self.assertIn(message, guard_result.stdout)
        with open(assembled_manifest, "w") as stream:
            json.dump(manifest, stream)

        forbidden = os.path.join(ansible_dir, "znsproxy", "zns-agent.bin")
        with open(forbidden, "w") as stream:
            stream.write("must be rejected\n")
        guard_result = self._run_ant(
            self._write_go("go1.26.11"),
            ["verify-zstack-zns-proxy-package"],
        )
        self.assertNotEqual(0, guard_result.returncode, guard_result.stdout)
        self.assertIn("zns-agent binary must not be packaged", guard_result.stdout)

    def test_manifest_rejects_same_version_with_different_sha(self):
        package = os.path.join(self.temp_dir, "zns-proxy.bin")
        output = os.path.join(self.temp_dir, "zns-proxy-manifest.json")
        script = os.path.join(
            REPO_ROOT,
            "zstackbuild",
            "scripts",
            "zns_proxy_manifest.py",
        )

        with open(package, "wb") as stream:
            stream.write(b"first")
        command = [
            "python",
            script,
            "--package",
            package,
            "--output",
            output,
            "--version",
            "1.2.0.1",
            "--arch",
            "amd64",
            "--path",
            "zns-proxy.bin",
        ]
        subprocess.check_call(command)

        with open(output) as stream:
            legacy_manifest = json.load(stream)
        legacy_manifest.pop("component")
        with open(output, "w") as stream:
            json.dump(legacy_manifest, stream)

        subprocess.check_call(command)
        with open(output) as stream:
            refreshed_manifest = json.load(stream)
        self.assertEqual("zns-proxy", refreshed_manifest["component"])

        with open(package, "wb") as stream:
            stream.write(b"second")
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

        self.assertNotEqual(0, result.returncode, result.stdout)
        self.assertIn("already exists with a different sha256", result.stdout)


if __name__ == "__main__":
    unittest.main()
