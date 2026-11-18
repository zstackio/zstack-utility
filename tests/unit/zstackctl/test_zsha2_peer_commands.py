import ast
import shlex
import subprocess
import warnings
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


CTL = Path(__file__).resolve().parents[3] / 'zstackctl/zstackctl/ctl.py'


@pytest.mark.parametrize('command,status,output', [
    ("printf '%s' 'peer ok'", 0, 'peer ok'),
    ('exit 7', 7, ''),
    ('false', 1, ''),
])
@pytest.mark.parametrize('sudo', [False, True])
def test_peer_command_preserves_remote_exit_status(command, status, output, sudo):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)
        tree = ast.parse(CTL.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Zsha2Utils')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'execute_on_peer')
    template = next(node for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'script_text' for target in node.targets))
    token = 'zstack-peer-test-' + uuid4().hex

    class Transport:
        def __init__(self, cmd):
            self.command = cmd

        def __call__(self, raise_on_error):
            wrappers = 'sudo() { shift 2; "$@"; }; ssh() { /bin/bash -c "${!#}"; }; '
            result = subprocess.run(['/bin/bash', '-c', wrappers + self.command], capture_output=True, text=True)
            self.return_code, self.stdout = result.returncode, result.stdout

        def raise_error(self):
            raise RuntimeError('remote exit %s' % self.return_code)

    namespace = dict(script_text=ast.literal_eval(template.value), ShellCmd=Transport,
                     uuid=SimpleNamespace(uuid4=lambda: token), shell_quote=shlex.quote)
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(CTL), 'exec'), namespace)
    peer = SimpleNamespace(config={'peerip': '192.0.2.10', 'peerport': 22}, ssh_exec_user='root')
    execute = namespace['execute_on_peer']
    if status:
        with pytest.raises(RuntimeError, match='remote exit %s' % status):
            execute(peer, command, sudo)
    else:
        assert execute(peer, command, sudo) == output
    assert not Path('/tmp/%s.sh' % token).exists()
