import os
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


class TestNpuSmiDeployment(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="npu ' test ")
        self.source = os.path.join(self.root, "usr/local/sbin/npu-smi")
        self.venv = os.path.join(self.root, "virtualenv/kvm")
        self.target = os.path.join(self.venv, "bin/npu-smi")
        os.makedirs(os.path.dirname(self.source))
        os.makedirs(os.path.dirname(self.target))

    def tearDown(self):
        shutil.rmtree(self.root)

    def deploy(self):
        with open(os.path.join(ROOT, "kvmagent/ansible/kvm.py")) as stream:
            source = stream.read()
        function = re.search(r"^def install_virtualenv\(\):.*?(?=^def )",
                             source, re.M | re.S).group(0)
        commands = []
        namespace = dict(
            check_and_install_virtual_env=lambda *args: True,
            virtualenv_version="12.1.1", trusted_host="test", pip_url="test",
            host_post_info=type("Host", (object,), {})(),
            virtenv_path=self.venv, run_remote_command=lambda cmd, host: commands.append(cmd))
        helper = os.path.join(ROOT, "kvmagent/ansible/gpu_tools.py")
        if os.path.exists(helper):
            module = {}
            with open(helper) as stream:
                eval(compile(stream.read(), helper, "exec"), module)
            build = module["build_npu_smi_link_command"]
            namespace["build_npu_smi_link_command"] = lambda venv: build(venv, self.source)
        eval(compile(function, "kvm.py", "exec"), namespace)
        namespace["install_virtualenv"]()
        for command in commands:
            if "npu-smi" in command:
                subprocess.check_call(command, shell=True)

    def write_tool(self, mode):
        with open(self.source, "w") as stream:
            stream.write("#!/bin/sh\nprintf 'npu-found\\n'\n")
        os.chmod(self.source, mode)

    def test_default_tool_runs_in_agent_path_after_deploy(self):
        self.write_tool(0o755)
        self.deploy()
        self.assertTrue(os.path.islink(self.target))
        self.assertEqual(os.path.realpath(self.target), self.source)
        output = subprocess.check_output("which npu-smi && npu-smi", shell=True,
                                         env={"PATH": os.path.dirname(self.target) + ":/usr/bin:/bin"})
        self.assertIn(b"npu-found", output)

    def test_redeploy_keeps_working_link(self):
        self.write_tool(0o755)
        self.deploy()
        self.deploy()
        self.assertTrue(os.path.islink(self.target))
        self.assertEqual(os.path.realpath(self.target), self.source)

    def test_missing_tool_does_not_fail_deployment(self):
        self.deploy()
        self.assertFalse(os.path.lexists(self.target))

    def test_non_executable_tool_is_skipped(self):
        self.write_tool(0o644)
        self.deploy()
        self.assertFalse(os.path.lexists(self.target))

    def test_existing_tool_remains_when_standard_tool_missing(self):
        with open(self.target, "w") as stream:
            stream.write("existing-tool")
        self.deploy()
        with open(self.target) as stream:
            self.assertEqual(stream.read(), "existing-tool")


if __name__ == "__main__":
    unittest.main()
