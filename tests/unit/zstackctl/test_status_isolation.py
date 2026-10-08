# -*- coding: utf-8 -*-
import argparse
import ast
import json
import os
import shlex
import signal
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest


CTL_PATH = Path(__file__).resolve().parents[3] / 'zstackctl' / 'zstackctl' / 'ctl.py'
CTL_AST = ast.parse(CTL_PATH.read_text(encoding='utf-8'))


def _load(names, namespace):
    body = [node for node in CTL_AST.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    module = ast.Module(body=body, type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(CTL_PATH), 'exec'), namespace)
    return namespace


def test_restore_class_loading_does_not_enumerate_addresses():
    calls = []

    def slow_addresses(command):
        calls.append(command)
        time.sleep(0.1)
        return 0, 'inet 192.0.2.10/24'

    _load({'RestoreMysqlCmd'}, {
        'Command': object,
        'subprocess': SimpleNamespace(getstatusoutput=slow_addresses),
    })

    assert calls == [], 'loading ctl must not wait for ip a: %r' % calls


def _status_namespace(response, return_code=0, pid=123, mn_only=True):
    output, commands, side_effects = [], [], []

    def forbidden(*args, **kwargs):
        raise AssertionError('MN-only status reached database/version/UI work')

    class FakeCommand(object):
        def __init__(self, command):
            commands.append(command)
            is_api = 'APIIsReadyToGoMsg' in command
            self.return_code = return_code if is_api else 0
            self.stdout = response if is_api else ''
            self.stderr = ''

        def __call__(self, *args, **kwargs):
            pass

    control = SimpleNamespace(
        zstack_home='/unused/zstack', properties_file_path='/unused/zstack.properties',
        USER_ZSTACK_HOME_DIR='/unused', read_property=lambda key: '8888',
        get_live_mysql_portal=forbidden if mn_only else lambda: ('localhost', 3306, 'zstack', ''),
        internal_run=forbidden if mn_only else lambda *a, **k: output.append('UI status: Running'),
    )
    namespace = {
        'Command': object, 'ctl': control, 'os': os, 'json': json,
        'signal': signal, 'datetime': datetime, 'ShellCmd': FakeCommand,
        'CtlError': RuntimeError, 'info': output.append, 'info_and_debug': output.append,
        'colored': lambda text, color: text, 'colorize_output': lambda text, color: text,
        'get_management_node_pid': lambda: pid, 'get_detail_version': lambda: None,
        'is_hyper_converged_host': forbidden if mn_only else lambda: False,
        'is_zsv_env': forbidden if mn_only else lambda: False,
        'kill_process': lambda *args: side_effects.append(('kill', args)),
        'shell_return': lambda command: side_effects.append(('shell', command)),
        'build_url_host_port': lambda host, port: '%s:%s' % (host, port),
    }
    _load({'ShowStatusCmd', 'get_mn_port', 'build_mn_api_url',
           'create_check_mgmt_node_command', 'get_mgmt_node_state_from_result'}, namespace)
    return namespace, output, commands, side_effects


@pytest.mark.parametrize(('response', 'return_code', 'pid', 'expected'), [
    (json.dumps({'result': '{"success":true}'}), 0, 123, 'Running'),
    (json.dumps({'result': '{"success":false}'}), 0, 123, 'Starting'),
    ('malformed', 0, 123, 'Unknown'),
    (json.dumps({'result': '{}'}), 0, 123, 'Unknown'),
    ('', 1, None, 'Stopped'),
    ('', 1, 123, 'Unknown'),
])
def test_mn_only_uses_readiness_and_skips_other_checks(response, return_code, pid, expected):
    namespace, output, commands, _ = _status_namespace(response, return_code, pid)
    command = namespace['ShowStatusCmd'].__new__(namespace['ShowStatusCmd'])

    command.run(SimpleNamespace(quiet=False, host=None, mn_only=True))

    assert len(output) == 1
    assert output[0].startswith('MN status: ' + expected), output
    readiness = [line for line in commands if 'APIIsReadyToGoMsg' in line]
    assert len(readiness) == 1
    assert 'http://127.0.0.1:8888/zstack/api' in readiness[0]


def test_default_status_keeps_version_mn_and_ui_for_legacy_args():
    namespace, output, _, _ = _status_namespace(
        json.dumps({'result': '{"success":true}'}), mn_only=False)
    command = namespace['ShowStatusCmd'].__new__(namespace['ShowStatusCmd'])

    command.run(SimpleNamespace(quiet=False, host=None))

    assert any(line.startswith('version:') for line in output)
    assert any(line.startswith('MN status: Running') for line in output)
    assert output[-1] == 'UI status: Running'


@pytest.mark.parametrize(('tool', 'options'), [
    ('wget', ('--tries=10', '--timeout=1')),
    ('curl', ('--retry 10', '--retry-max-time 10', '--max-time 10')),
])
def test_mn_only_preserves_readiness_wait_and_retries(tool, options):
    namespace, output, commands, _ = _status_namespace(
        json.dumps({'result': '{"success":true}'}))
    fake_command = namespace['ShellCmd']

    class SelectReadinessTool(fake_command):
        def __init__(self, command):
            super().__init__(command)
            if command == 'which wget' and tool == 'curl':
                self.return_code = 1

    namespace['ShellCmd'] = SelectReadinessTool
    command = namespace['ShowStatusCmd'].__new__(namespace['ShowStatusCmd'])
    command.run(SimpleNamespace(quiet=False, host=None, mn_only=True))

    readiness, = [line for line in commands if 'APIIsReadyToGoMsg' in line]
    assert readiness.startswith(tool + ' ')
    for option in options:
        assert option in readiness
    assert output[0].startswith('MN status: Running')


@pytest.mark.parametrize('mn_only', [False, True, None])
def test_remote_status_forwards_only_requested_mn_flag(mn_only):
    commands = []
    namespace = _load({'ShowStatusCmd'}, {'Command': object, 'shell_no_pipe': commands.append})
    args = SimpleNamespace(quiet=False, host='root@192.0.2.10')
    if mn_only is not None:
        args.mn_only = mn_only

    namespace['ShowStatusCmd'].__new__(namespace['ShowStatusCmd']).run(args)

    suffix = ' --mn-only' if mn_only else ''
    assert commands == ['ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no '
                        'root@192.0.2.10 "/usr/bin/zstack-ctl status%s"' % suffix]


def test_status_registers_mn_only_option():
    namespace = _load({'ShowStatusCmd'}, {'Command': object})
    command = namespace['ShowStatusCmd'].__new__(namespace['ShowStatusCmd'])
    parser = argparse.ArgumentParser()
    command.install_argparse_arguments(parser)

    assert parser.parse_args(['--mn-only']).mn_only is True
    assert parser.parse_args([]).mn_only is False


@pytest.mark.parametrize(('host', 'expected_ip_calls', 'expected_host'), [
    ('localhost', [], ''),
    ('127.0.0.1', [], ''),
    ('192.0.2.10', ['ip a'], ''),
    ('192.0.2.20', ['ip a'], '--host 192.0.2.20'),
])
def test_mysql_enumerates_addresses_only_when_needed(host, expected_ip_calls, expected_host):
    addresses, commands = [], []

    def get_addresses(command):
        addresses.append(command)
        return 0, 'inet 192.0.2.10/24'

    def execute(command):
        commands.append(command)
        return 0, ' result \n', ''

    namespace = _load({'RestoreMysqlCmd', 'mysql'}, {
        'Command': object, 'subprocess': SimpleNamespace(getstatusoutput=get_addresses),
        'ctl': SimpleNamespace(get_live_mysql_portal=lambda: (host, 3307, 'zstack', 'test-password')),
        'shell_quote': shlex.quote, 'shell_return_stdout_stderr': execute,
    })

    assert namespace['mysql']('select 1') == 'result'
    assert addresses == expected_ip_calls
    assert len(commands) == 1
    assert '-uzstack --password=test-password -P 3307' in commands[0]
    assert ('--host' in commands[0]) == bool(expected_host)
    assert expected_host in commands[0]


def test_mysql_socket_failure_falls_back_to_original_host():
    commands = []
    namespace = _load({'RestoreMysqlCmd', 'mysql'}, {
        'Command': object, 'subprocess': SimpleNamespace(getstatusoutput=lambda command: (0, '192.0.2.10')),
        'ctl': SimpleNamespace(get_live_mysql_portal=lambda: ('192.0.2.20', 3307, 'zstack', 'test-password')),
        'shell_quote': shlex.quote,
        'shell_return_stdout_stderr': lambda command: (1, '', 'socket unavailable'),
        'shell': lambda command: commands.append(command) or 'fallback result\n',
    })

    assert namespace['mysql']('select 1', '192.0.2.10') == 'fallback result'
    assert '--host 192.0.2.20' in commands[0]
    assert '-P 3307' in commands[0]


def test_mysql_remote_failure_keeps_error_details():
    namespace = _load({'RestoreMysqlCmd', 'mysql'}, {
        'Command': object, 'subprocess': SimpleNamespace(getstatusoutput=lambda command: (0, '192.0.2.10')),
        'ctl': SimpleNamespace(get_live_mysql_portal=lambda: ('192.0.2.20', 3307, 'zstack', 'test-password')),
        'shell_quote': shlex.quote, 'CtlError': RuntimeError,
        'shell_return_stdout_stderr': lambda command: (2, 'out', 'remote unavailable'),
    })

    with pytest.raises(RuntimeError, match='remote unavailable'):
        namespace['mysql']('select 1')
