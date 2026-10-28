import os
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


PATH = Path(__file__).resolve().parents[3] / 'zstackctl/zstackctl/ctl.py'


@pytest.fixture
def ui_status(tmp_path, monkeypatch):
    launcher = tmp_path / 'runuser'
    launcher.write_text('#!/bin/bash\n[[ "$LAUNCHER_FAIL" == 1 ]] && exit 1\nexec /bin/bash -c "${@: -1}"\n')
    launcher.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path) + os.pathsep + os.environ['PATH'])
    script = tmp_path / "status file's.sh"
    output = []

    class ShellCmd:
        def __init__(self, command, pipe=True):
            self.command, self.pipe = command, pipe

        def __call__(self, *args, **kwargs):
            result = subprocess.run(self.command, shell=True, executable='/bin/bash',
                                    capture_output=True, text=True, timeout=3)
            self.return_code = result.returncode
            self.stdout = result.stdout if self.pipe else ''
            self.stderr = result.stderr if self.pipe else ''
            return self.stdout

    source = PATH.read_text()
    quote = re.search(r'^def shell_quote\(.*?(?=^def |^class |\Z)', source, re.M | re.S).group(0)
    definition = re.search(r'^class UiStatusCmd\b.*?(?=^class |\Z)', source, re.M | re.S).group(0)
    namespace = dict(os=os, Command=object, ShellCmd=ShellCmd,
                     StartUiCmd=SimpleNamespace(HTTP_FILE=str(tmp_path / 'http')),
                     ctl=SimpleNamespace(read_property=lambda key: None),
                     info=output.append, colored=lambda text, color: text,
                     get_ui_address=lambda: None, shell_return_stdout_stderr=lambda cmd: (0, '123'))
    exec(compile(quote + '\n' + definition, str(PATH), 'exec'), namespace)
    cls = namespace['UiStatusCmd']
    cls.ZSTACK_UI_STATUS = str(script)
    cls.STATUS_TIMEOUT = '0.1s'
    cmd = cls.__new__(cls)

    def run(body, launcher_failure=False):
        script.write_text('#!/bin/bash\n' + body + '\n')
        monkeypatch.setenv('LAUNCHER_FAIL', '1' if launcher_failure else '0')
        cmd.run(SimpleNamespace(host='localhost', quiet=False))
        return output[-1]

    run.namespace = namespace
    run.command = cmd
    return run


@pytest.mark.parametrize('body,expected', [
    ('exit 1', 'UI status: Stopped'),
    ('exit 0', 'UI status: Running'),
    ('echo failed >&2; exit 1', 'UI status: Unknown'),
    ('echo diagnostic; exit 1', 'UI status: Unknown'),
    ('exit 2', 'UI status: Unknown'),
    ('exit 3', 'UI status: Unknown'),
    ('kill -TERM $$', 'UI status: Unknown'),
    ('sleep 1', 'UI status: Unknown'),
    ('echo ZSTACK_UI_STATUS_EXIT=0; exit 2', 'UI status: Unknown'),
])
def test_ui_status_distinguishes_stopped_from_probe_errors(ui_status, body, expected):
    assert ui_status(body).startswith(expected)


def test_failed_launcher_is_not_mistaken_for_stopped_ui(ui_status):
    assert ui_status('exit 1', launcher_failure=True).startswith('UI status: Unknown')


def test_mini_ui_retains_its_own_status_probe(ui_status):
    ui_status.namespace['ctl'].read_property = lambda key: 'mini'
    ui_status.namespace['get_ui_pid'] = lambda mode: None
    probe = MagicMock(return_code=1, stdout='')
    ui_status.namespace['create_check_ui_status_command'] = lambda **kwargs: probe
    ui_status.command._run_status_script = MagicMock(side_effect=AssertionError('mini used normal UI probe'))
    assert ui_status('exit 1') == 'UI status: Stopped'
    ui_status.command._run_status_script.assert_not_called()
