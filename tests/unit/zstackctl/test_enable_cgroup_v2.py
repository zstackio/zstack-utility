import argparse
import ast
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


CTL_PATH = Path(__file__).resolve().parents[3] / 'zstackctl/zstackctl/ctl.py'
CLUSTER_UUID = 'a' * 32


@pytest.fixture
def command_module():
    tree = ast.parse(CTL_PATH.read_text())
    names = {'Command', 'EnableCgroupV2Cmd'}
    body = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name in names]
    assert len(body) == 2, 'enable_cgroup_v2 must exist as a standard ctl command'
    namespace = dict(os=os, re=re, tempfile=tempfile, sys=sys, shell_quote=shlex.quote,
                     logger=logging.getLogger(__name__))
    namespace.update(ctl=Mock(zstack_home='/opt/zstack'), HostPostInfo=lambda: SimpleNamespace(remote_pass=None),
                     ZstackRunnerArg=SimpleNamespace, MySqlCommandLineQuery=Mock(), info=Mock(), warn=Mock())
    namespace['ctl'].get_live_mysql_portal.return_value = ('localhost', 3306, 'root', 'db-password')
    namespace['error'] = Mock(side_effect=SystemExit(1))
    exec(compile(ast.Module(body=body, type_ignores=[]), str(CTL_PATH), 'exec'), namespace)
    return namespace


@pytest.fixture
def command_args():
    return SimpleNamespace(cluster_uuid=CLUSTER_UUID, host_uuids=None)


def test_command_is_registered_and_reports_manual_reboot(command_module):
    command = command_module['EnableCgroupV2Cmd']()
    assert command.name == 'enable_cgroup_v2'
    assert 'without rebooting' in command.description
    command_module['ctl'].register_command.assert_called_once_with(command)
    main = next(n for n in ast.parse(CTL_PATH.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'EnableCgroupV2Cmd'
               for n in ast.walk(main))


def test_cluster_is_required_and_host_list_is_optional(command_module):
    parser = argparse.ArgumentParser()
    command_module['EnableCgroupV2Cmd']().install_argparse_arguments(parser)
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(['--cluster-uuid', CLUSTER_UUID, '--host-uuids'])
    args = parser.parse_args(['--cluster-uuid', CLUSTER_UUID])
    assert args.cluster_uuid == CLUSTER_UUID and args.host_uuids is None
    host_uuids = ['1' * 32, '2' * 32]
    args = parser.parse_args(['--cluster-uuid', CLUSTER_UUID, '--host-uuids'] + host_uuids)
    assert args.host_uuids == host_uuids


def test_batch_queries_once_continues_after_failure_and_cleans_inventory(command_module, command_args):
    hosts = [dict(uuid='%032x' % i, managementIp='192.0.2.%d' % i, username='root', port='22', password='secret')
             for i in range(1, 4)]
    hosts[1].update(username='operator', port='2222')
    query = command_module['MySqlCommandLineQuery'].return_value
    query.query.return_value = hosts
    calls = []

    def runner(args):
        host = args.host_post_info
        calls.append(host)
        inventory = Path(host.host_inventory).read_text()
        assert inventory == '%s ansible_host=%s\n' % (host.host, hosts[len(calls) - 1]['managementIp'])
        assert 'secret' not in inventory
        result = {'rc': 0, 'stdout': 'args="ro systemd.unified_cgroup_hierarchy=1"'}
        if host.host == hosts[1]['uuid']:
            result = {'failed': True, 'msg': 'Host unreachable'}
        return SimpleNamespace(run=lambda: {'contacted': {host.host: result}})

    command_module['ZstackRunner'] = runner
    with pytest.raises(SystemExit):
        command_module['EnableCgroupV2Cmd']()(command_args)

    query.query.assert_called_once()
    assert 'JOIN KVMHostVO' in query.sql
    assert "h.clusterUuid = '%s'" % CLUSTER_UUID in query.sql
    assert [host.host for host in calls] == [host['uuid'] for host in hosts]
    assert calls[1].remote_user == 'operator' and calls[1].remote_port == '2222'
    assert calls[1].become and calls[1].remote_pass == 'secret'
    assert not calls[0].become
    assert calls[0].remote_pass is None
    assert calls[0].private_key.endswith('/WEB-INF/classes/ansible/rsaKeys/id_rsa')
    assert not Path(calls[0].host_inventory).exists()
    output = str(command_module['info'].call_args_list) + str(command_module['warn'].call_args_list)
    assert hosts[1]['uuid'] in output and 'Host unreachable' in output and hosts[2]['uuid'] in output
    assert 'secret' not in output
    assert command_module['info'].call_count == 2 and command_module['warn'].call_count == 1


def test_no_hosts_does_not_execute_remotely(command_module, command_args):
    command_module['MySqlCommandLineQuery'].return_value.query.return_value = []
    command_module['ZstackRunner'] = Mock()
    command_module['EnableCgroupV2Cmd']()(command_args)
    command_module['ZstackRunner'].assert_not_called()
    command_module['error'].assert_not_called()


def test_selected_hosts_are_scoped_and_deduplicated(command_module, command_args):
    host_uuid = 'b' * 32
    command_args.cluster_uuid = CLUSTER_UUID.upper()
    command_args.host_uuids = [host_uuid.upper(), host_uuid]
    query = command_module['MySqlCommandLineQuery'].return_value
    query.query.return_value = [dict(uuid=host_uuid, managementIp='192.0.2.1', username='root', port='22')]
    runner = Mock()
    runner.return_value.run.return_value = {
        'contacted': {host_uuid: {'rc': 0, 'stdout': 'args="ro systemd.unified_cgroup_hierarchy=1"'}}}
    command_module['ZstackRunner'] = runner
    command_module['EnableCgroupV2Cmd']()(command_args)
    query.query.assert_called_once()
    assert "h.clusterUuid = '%s'" % CLUSTER_UUID in query.sql
    assert "h.uuid IN ('%s')" % host_uuid in query.sql
    runner.assert_called_once()


@pytest.mark.parametrize('found_uuids', [[], ['1' * 32]])
def test_missing_or_outside_cluster_host_prevents_all_remote_execution(command_module, command_args, found_uuids):
    command_args.host_uuids = ['1' * 32, '2' * 32]
    query = command_module['MySqlCommandLineQuery'].return_value
    query.query.return_value = [dict(uuid=host_uuid) for host_uuid in found_uuids]
    command_module['ZstackRunner'] = Mock()
    with pytest.raises(SystemExit):
        command_module['EnableCgroupV2Cmd']()(command_args)
    command_module['ZstackRunner'].assert_not_called()
    assert '2' * 32 in str(command_module['error'].call_args)


@pytest.mark.parametrize('field,value', [
    ('cluster_uuid', "x' OR 1=1"), ('host_uuids', ['invalid']), ('cluster_uuid', CLUSTER_UUID + '\n'),
])
def test_invalid_uuid_is_rejected_before_query(command_module, command_args, field, value):
    setattr(command_args, field, value)
    command_module['ZstackRunner'] = Mock()
    with pytest.raises(SystemExit):
        command_module['EnableCgroupV2Cmd']()(command_args)
    command_module['MySqlCommandLineQuery'].assert_not_called()
    command_module['ZstackRunner'].assert_not_called()


@pytest.fixture
def boot_script(command_module, tmp_path):
    script = command_module['EnableCgroupV2Cmd'].boot_script
    state = tmp_path / 'entries.json'
    state.write_text(json.dumps(['ro quiet systemd.unified_cgroup_hierarchy=0', 'ro console=ttyS0']))
    log = tmp_path / 'commands'
    commands = {
        'uname': '#!/bin/sh\necho "${HOST_ARCH:-x86_64}"\n',
        'awk': '''#!/bin/sh
if [ "$2" = /etc/zstack-release ]; then
    printf 'ZStack release %s\\n' "${HOST_RELEASE-h84r}" | /usr/bin/awk "$1"
else
    exec /usr/bin/awk "$@"
fi
''',
        'grep': '#!/bin/sh\nexit "${CGROUP_CHECK_RC:-0}"\n',
        'docker': '#!/bin/sh\necho "Docker version ${DOCKER_VERSION:-20.10.0}, build example"\n',
        'grubby': '''#!%s
import json, os, sys
from pathlib import Path
state = Path(os.environ['BOOT_STATE'])
args = sys.argv[1:]
with open(os.environ['COMMAND_LOG'], 'a') as log:
    log.write(' '.join(args) + '\\n')
entries = json.loads(state.read_text())
if '--update-kernel=ALL' in args:
    if os.environ.get('WRITE_FAIL'):
        sys.exit(1)
    if not os.environ.get('IGNORE_UPDATE'):
        flag = args[1].split('=', 1)[1]
        entries = [' '.join([v for v in entry.split() if not v.startswith(flag.split('=')[0] + '=')] + [flag])
                   for entry in entries]
        state.write_text(json.dumps(entries))
else:
    for index, entry in enumerate(entries):
        print('index=%%d\\nargs="%%s"' %% (index, entry))
''' % sys.executable,
    }
    for name, content in commands.items():
        path = tmp_path / name
        path.write_text(content)
        path.chmod(0o755)
    environment = dict(os.environ, PATH=str(tmp_path) + ':/usr/bin:/bin', BOOT_STATE=str(state), COMMAND_LOG=str(log))
    return script, environment, state, log


def test_boot_update_is_idempotent_and_does_not_reboot(boot_script):
    script, environment, state, log = boot_script
    first = subprocess.run(['/bin/sh', '-c', script], env=environment, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    entries = json.loads(state.read_text())
    assert entries == ['ro quiet systemd.unified_cgroup_hierarchy=1',
                       'ro console=ttyS0 systemd.unified_cgroup_hierarchy=1']
    second = subprocess.run(['/bin/sh', '-c', script], env=environment, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    assert json.loads(state.read_text()) == entries
    assert 'reboot' not in log.read_text()
    assert 'restart' not in script and '/sys/fs/cgroup' not in script
    assert first.stdout == second.stdout and 'args="ro quiet systemd.unified_cgroup_hierarchy=1"' in first.stdout


@pytest.mark.parametrize('overrides', [
    {'DOCKER_VERSION': '19.03.15'}, {'CGROUP_CHECK_RC': '1'},
    {'HOST_ARCH': 'aarch64'}, {'HOST_RELEASE': 'rl84'}, {'HOST_RELEASE': ''},
])
def test_unsupported_hosts_are_rejected_before_writing(boot_script, overrides):
    script, environment, state, log = boot_script
    original = state.read_text()
    result = subprocess.run(['/bin/sh', '-c', script], env=dict(environment, **overrides), capture_output=True)
    assert result.returncode != 0
    assert state.read_text() == original
    assert not log.exists()


@pytest.mark.parametrize('overrides', [{'WRITE_FAIL': '1'}, {'IGNORE_UPDATE': '1'}])
def test_boot_write_or_verification_failure_is_not_success(boot_script, command_module, command_args, overrides):
    script, environment, state, log = boot_script
    host_uuid = '1' * 32
    command_module['MySqlCommandLineQuery'].return_value.query.return_value = [
        dict(uuid=host_uuid, managementIp='192.0.2.1', username='root', port='22')]

    def runner(args):
        result = subprocess.run(['/bin/sh', '-c', args.module_args], env=dict(environment, **overrides),
                                capture_output=True, text=True)
        return SimpleNamespace(run=lambda: {'contacted': {host_uuid: dict(
            rc=result.returncode, stdout=result.stdout, stderr=result.stderr)}})

    command_module['ZstackRunner'] = Mock(side_effect=runner)
    with pytest.raises(SystemExit):
        command_module['EnableCgroupV2Cmd']()(command_args)
    command_module['ZstackRunner'].assert_called_once()
    command_module['info'].assert_not_called()
    if overrides.get('IGNORE_UPDATE'):
        assert 'Failed to verify' in str(command_module['warn'].call_args)


@pytest.mark.parametrize('boot_args', [
    '', 'args="ro quiet"', 'args="systemd.unified_cgroup_hierarchy=0"',
    'args="systemd.unified_cgroup_hierarchy=1 systemd.unified_cgroup_hierarchy=1"',
    'args="systemd.unified_cgroup_hierarchy=1 systemd.unified_cgroup_hierarchy=0"',
    'args="systemd.unified_cgroup_hierarchy=1"\nargs="ro quiet"',
])
def test_incomplete_or_conflicting_boot_entries_are_not_success(command_module, command_args, boot_args):
    host_uuid = '1' * 32
    command_module['MySqlCommandLineQuery'].return_value.query.return_value = [
        dict(uuid=host_uuid, managementIp='192.0.2.1', username='root', port='22')]
    command_module['ZstackRunner'] = Mock()
    command_module['ZstackRunner'].return_value.run.return_value = {
        'contacted': {host_uuid: dict(rc=0, stdout=boot_args)}}
    with pytest.raises(SystemExit):
        command_module['EnableCgroupV2Cmd']()(command_args)
    assert 'Failed to verify' in str(command_module['warn'].call_args)
    command_module['info'].assert_not_called()
