import ast
import contextlib
import fcntl
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[3]
CTL_PATH = ROOT / 'zstackctl/zstackctl/ctl.py'
CTX = multiprocessing.get_context('fork')


class CtlError(Exception):
    pass


def load_start(tmp_path, shell, check_ready, cleanup):
    spec = importlib.util.spec_from_file_location(
        'start_test_lock', ROOT / 'zstackctl/zstackctl/utils/lock.py')
    real_lock = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(real_lock)
    ctl = MagicMock(USER_ZSTACK_HOME_DIR=str(tmp_path), zstack_home=str(tmp_path),
                    extra_arguments=[], properties_file_path=str(tmp_path / 'properties'))
    ctl.read_property.side_effect = lambda key: {
        'syncNodeTime': 'false', 'management.server.ip': '192.0.2.1'}.get(key)
    ctl.get_env.return_value = None
    ctl.get_live_mysql_portal.return_value = ('localhost', 3306, 'test', 'test')
    ctl.internal_run.side_effect = cleanup
    os_stub = SimpleNamespace(path=os.path, getuid=lambda: 0, walk=lambda path: [])
    network = MagicMock()
    network.management_server_requires_ipv6_stack.return_value = False
    network.build_java_ip_stack_opts.side_effect = lambda ip, opts: opts

    def remove(path):
        candidate = tmp_path / Path(path).name
        candidate.unlink(missing_ok=True)

    namespace = dict(
        Command=object, CtlError=CtlError, Ctl=SimpleNamespace(NEED_ENCRYPT_PROPERTIES=[]),
        ctl=ctl, os=os_stub, time=SimpleNamespace(sleep=lambda seconds: None), json=json,
        lock=SimpleNamespace(file_lock=lambda name: real_lock.file_lock(str(tmp_path / 'start.lock'))),
        linux=SimpleNamespace(rm_file_force=remove, sync_file=lambda path: None),
        get_management_node_pid=lambda: 123 if (tmp_path / 'management-server.pid').exists() else None,
        get_mn_port=lambda: 8080, shell_return_stdout_stderr=lambda cmd: (0, '', ''),
        shell=shell, ShellCmd=lambda cmd: lambda *args: None,
        on_error=lambda message: contextlib.nullcontext(), check_ip_port=lambda *args: True,
        shell_quote=lambda value: value, local_ip_exists=lambda ip: True,
        check_ha=lambda: False, is_invoked_by_ha_monitor=lambda: True,
        check_java_version=lambda: None, build_management_server_ip_stack_opts=lambda props: [],
        management_network_ipv6=network, AESCipher=MagicMock(),
        subprocess=SimpleNamespace(getstatusoutput=lambda cmd: (0, '')),
        platform=SimpleNamespace(freedesktop_os_release=lambda: {}),
        map_distro_id=lambda distro: 'test', RPM_BASED_OS=[], DEB_BASED_OS=[],
        loop_until_timeout=lambda timeout: lambda func: func,
        create_check_mgmt_node_command=check_ready,
        info=lambda message: None, info_and_debug=lambda message: None,
    )
    tree = ast.parse(CTL_PATH.read_text())
    node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'StartCmd')
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(CTL_PATH), 'exec'), namespace)
    command = namespace['StartCmd'].__new__(namespace['StartCmd'])
    command.check_cpu_mem = lambda: None
    command.SET_ENV_SCRIPT = 'setenv.sh'
    return command


def run_start(tmp_path, started, release, entered, results, fail=False, daemon=True):
    def record(event):
        with (tmp_path / 'events').open('a') as stream:
            stream.write(event + '\n')

    def cleanup(command):
        assert command == 'stop_node'
        record('cleanup')
        (tmp_path / 'management-server.pid').unlink(missing_ok=True)

    def shell(command, **kwargs):
        if 'startup.sh' in command:
            record('launch')
            started.set()
        elif 'systemctl start zstack' in command:
            child = CTX.Process(target=run_start, args=(tmp_path, started, release, CTX.Event(), results))
            child.start()
            child.join(5)
            if child.is_alive():
                child.terminate()
                child.join()
                raise AssertionError('systemd start blocked on the parent start lock')
            assert child.exitcode == 0
            record('systemd')
        return ''

    def check_ready(*args):
        assert release.wait(5), 'startup was not released'
        if fail:
            raise CtlError('startup failed')
        (tmp_path / 'management-server.pid').write_text('123')
        (tmp_path / 'bootError.log').write_text('preserve on duplicate start')
        return MagicMock(return_code=0)

    try:
        command = load_start(tmp_path, shell, check_ready, cleanup)
        entered.set()
        command.run(SimpleNamespace(host=None, daemon=daemon, mode=None, simulator=False,
                                    mysql_process_list=False, timeout=5))
        results.put('success')
    except Exception as error:
        results.put(str(error))


@pytest.mark.parametrize('first_fails', [False, True])
def test_concurrent_start_waits_for_readiness_and_failure_cleanup(tmp_path, first_fails):
    started, release, entered = CTX.Event(), CTX.Event(), CTX.Event()
    results = CTX.Queue()
    first = CTX.Process(target=run_start, args=(tmp_path, started, release, CTX.Event(), results, first_fails))
    second = CTX.Process(target=run_start, args=(tmp_path, started, release, entered, results))
    try:
        first.start()
        assert started.wait(5)
        second.start()
        assert entered.wait(5)
        with (tmp_path / 'start.lock').open('a') as stream:
            with pytest.raises(BlockingIOError):
                fcntl.lockf(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert (tmp_path / 'events').read_text().splitlines() == ['launch']
        release.set()
        first.join(5)
        second.join(5)
        assert first.exitcode == second.exitcode == 0
        expected = ['launch', 'cleanup', 'launch'] if first_fails else ['launch']
        assert (tmp_path / 'events').read_text().splitlines() == expected
        assert sorted([results.get(timeout=1), results.get(timeout=1)]) == (
            ['startup failed', 'success'] if first_fails else ['success', 'success'])
        assert (tmp_path / 'bootError.log').read_text() == 'preserve on duplicate start'
    finally:
        release.set()
        for process in (first, second):
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(5)


def test_systemd_reentry_happens_after_unlock(tmp_path):
    started, release = CTX.Event(), CTX.Event()
    release.set()
    results = CTX.Queue()
    run_start(tmp_path, started, release, CTX.Event(), results, daemon=False)
    assert [results.get(timeout=1), results.get(timeout=1)] == ['success', 'success']
    assert (tmp_path / 'events').read_text().splitlines() == ['launch', 'systemd']


def test_remote_start_does_not_take_local_lock(tmp_path):
    command = load_start(tmp_path, MagicMock(), MagicMock(), MagicMock())
    command._start_remote = MagicMock()
    args = SimpleNamespace(host='root@192.0.2.2')
    command.run(args)
    command._start_remote.assert_called_once_with(args)
    assert not (tmp_path / 'start.lock').exists()
