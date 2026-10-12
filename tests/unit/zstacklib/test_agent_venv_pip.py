"""Exercise the Agent bootstrap against the standard packaged PyPI layout."""
import ast
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.parse


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'zstacklib/ansible/zstacklib.py'
PYPI = ROOT / 'zstackbuild/pypi_source/pypi'


def load_bootstrap():
    tree = ast.parse(SOURCE.read_text())
    nodes = [node for node in tree.body if
             (isinstance(node, ast.Assign) and any(
                 isinstance(target, ast.Name) and target.id.startswith('AGENT_VENV_PIP_')
                 for target in node.targets)) or
             (isinstance(node, ast.FunctionDef) and
              node.name == 'build_agent_venv_pip_command')]
    namespace = {'os': os, 'urllib': urllib, 'shell_quote': shlex.quote}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace


class AgentVenvPipTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bootstrap = load_bootstrap()

    def command(self, venv, index):
        return self.bootstrap['build_agent_venv_pip_command'](
            str(venv), 'localhost', index)

    def test_declared_wheel_matches_the_index_and_hash(self):
        name = self.bootstrap['AGENT_VENV_PIP_WHEEL']
        digest = self.bootstrap['AGENT_VENV_PIP_WHEEL_SHA256']
        self.assertEqual(digest, hashlib.sha256((PYPI / 'simple/pip' / name).read_bytes()).hexdigest())
        self.assertIn(name + '#sha256=' + digest, (PYPI / 'simple/pip/index.html').read_text())
        command = self.command('/var/lib/zstack/virtualenv/kvm',
                               'http://localhost:8080/zstack/static/pypi/simple/')
        self.assertIn('/zstack/static/pypi/simple/pip/' + name + '#sha256=' + digest, command)

    def test_rejects_urls_that_are_not_a_simple_index(self):
        for index in ('https://example.invalid/pypi',
                      'https://example.invalid/simple?index=other',
                      'ftp://example.invalid/simple'):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.command('/tmp/venv', index)

    def test_packaged_layout_bootstraps_a_clean_venv_and_is_repeatable(self):
        with tempfile.TemporaryDirectory(prefix='agent-pip-') as directory:
            root = Path(directory)
            pypi = root / 'pypi'
            shutil.copytree(PYPI / 'simple/pip', pypi / 'simple/pip', symlinks=True)
            for link in (pypi / 'simple/pip').glob('*.whl'):
                shutil.copy2(PYPI / link.name, pypi / link.name)
            # Use the same link materialization as the normal WAR build.
            subprocess.run(['bash', str(ROOT / 'zstackbuild/scripts/remove_pypi_symlink.sh'),
                            str(pypi)], check=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
            venv = root / 'venv with spaces'
            subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            command = self.command(venv, (pypi / 'simple').as_uri())
            env = {key: value for key, value in os.environ.items()
                   if not key.startswith(('PIP_', 'PYTHON'))}
            env.update(PIP_CONFIG_FILE=os.devnull, PYTHONNOUSERSITE='1')
            for unused in range(2):
                result = subprocess.run(['sh', '-c', command], env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, timeout=90)
                self.assertEqual(0, result.returncode, result.stdout)
            installed = subprocess.check_output([
                str(venv / 'bin/python'), '-c',
                'import pip; print(pip.__version__)'], env=env, text=True).strip()
            self.assertEqual(self.bootstrap['AGENT_VENV_PIP_VERSION'], installed)


if __name__ == '__main__':
    unittest.main()
