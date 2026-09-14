import errno
import importlib.util
import socket
import sys
from contextlib import ExitStack, nullcontext
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _load_imagestore_module():
    bash_module = sys.modules['zstacklib.utils.bash']
    if not hasattr(bash_module, 'bash_progress_1'):
        bash_module.bash_progress_1 = lambda *args, **kwargs: (0, '', None)
    module_path = Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/plugins/imagestore.py'
    spec = importlib.util.spec_from_file_location('imagestore_nbd_under_test', str(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


imagestore = _load_imagestore_module()


@pytest.fixture
def backup(monkeypatch):
    client = imagestore.ImageStoreClient()
    linux = MagicMock()
    linux.create_temp_file.return_value = '/tmp/backup-progress'
    linux.ShowLibvirtErrorOnException.side_effect = lambda _vm: nullcontext()
    command = MagicMock(return_value=(0, 'full', None))
    monkeypatch.setattr(imagestore, 'linux', linux, raising=False)
    monkeypatch.setattr(imagestore, 'get_task_stage', lambda _spec: None, raising=False)
    monkeypatch.setattr(imagestore, 'bash_progress_1', command)
    monkeypatch.setattr(client, 'check_capacity', lambda _dest: None)

    def run(kind, dest):
        if kind == 'volume':
            return client.backup_volume('vm-uuid', 'drive-virtio-disk0', 'zsbitmap0', 'full', dest, {})
        args = [('zsbitmap0', 'full', 'drive-virtio-disk0', 0), ('zsbitmap1', 'full', 'drive-scsi0-0-0-1', 0)]
        return client.backup_volumes('vm-uuid', args, dest, {})

    return run, command, linux


@pytest.mark.parametrize('kind', ['volume', 'vm'])
def test_closed_nbd_port_stops_backup_before_qemu_or_progress_file(backup, kind):
    run, command, linux = backup
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0))
        endpoint = '127.0.0.1:%s' % reserved.getsockname()[1]
        with pytest.raises(imagestore.kvmagent.KvmError, match=endpoint):
            run(kind, 'nbd://' + endpoint)

    command.assert_not_called()
    linux.create_temp_file.assert_not_called()
    linux.ShowLibvirtErrorOnException.assert_not_called()


@pytest.mark.parametrize('kind', ['volume', 'vm'])
@pytest.mark.parametrize('host', ['127.0.0.1', '::1'])
def test_all_nbd_ports_are_probed_and_closed_before_backup(backup, kind, host):
    run, command, _linux = backup
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    with ExitStack() as stack:
        listeners = [stack.enter_context(socket.socket(family)) for _ in range(1 if kind == 'volume' else 2)]
        for listener in listeners:
            listener.bind((host, 0))
            listener.listen(1)
            listener.settimeout(0.2)
        ports = ','.join(str(listener.getsockname()[1]) for listener in listeners)
        dest = 'nbd://%s:%s' % (imagestore.network_ipv6.format_url_host(host), ports)

        def start_backup(_command, _progress):
            for listener in listeners:
                with listener.accept()[0] as probe:
                    probe.settimeout(0.2)
                    assert probe.recv(1) == b''
            return 0, 'full', None

        command.side_effect = start_backup
        assert run(kind, dest) == 'full'

    command.assert_called_once()
    assert dest in command.call_args[0][0]
    assert (' batbak ' if kind == 'vm' else ' backup ') in command.call_args[0][0]


@pytest.mark.parametrize('failure', [errno.ECONNREFUSED, errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EAGAIN])
def test_later_nbd_port_failure_blocks_entire_vm_backup(monkeypatch, backup, failure):
    run, command, linux = backup
    probes = [MagicMock(), MagicMock()]

    def connect(index, result, address):
        probes[index].settimeout.assert_called_once_with(3)
        assert address == ('172.30.0.4', 10405 + index)
        return result

    probes[0].connect_ex.side_effect = lambda address: connect(0, 0, address)
    probes[1].connect_ex.side_effect = lambda address: connect(1, failure, address)
    factory = MagicMock(side_effect=probes)
    monkeypatch.setattr(imagestore.network_ipv6, 'create_tcp_socket_for_host', factory)

    with pytest.raises(imagestore.kvmagent.KvmError, match='172.30.0.4:10406'):
        run('vm', 'nbd://172.30.0.4:10405,10406')

    assert factory.call_count == 2
    for probe in probes:
        probe.close.assert_called_once()
    command.assert_not_called()
    linux.create_temp_file.assert_not_called()
    linux.ShowLibvirtErrorOnException.assert_not_called()


def test_socket_exception_closes_probe_and_does_not_start_backup(monkeypatch, backup):
    run, command, _linux = backup
    probe = MagicMock()
    probe.connect_ex.side_effect = socket.timeout('timed out')
    monkeypatch.setattr(imagestore.network_ipv6, 'create_tcp_socket_for_host', lambda _host: probe)

    with pytest.raises(socket.timeout):
        run('volume', 'nbd://172.30.0.4:10405')

    probe.settimeout.assert_called_once_with(3)
    probe.close.assert_called_once()
    command.assert_not_called()


@pytest.mark.parametrize('kind', ['volume', 'vm'])
def test_local_backup_does_not_open_network_connections(monkeypatch, backup, kind):
    run, command, _linux = backup
    factory = MagicMock(side_effect=AssertionError('local backups must not require NBD connectivity'))
    monkeypatch.setattr(imagestore.network_ipv6, 'create_tcp_socket_for_host', factory)

    assert run(kind, '/backup/workspace') == 'full'

    factory.assert_not_called()
    command.assert_called_once()


def test_empty_target_preflight_does_not_open_connections(monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(imagestore.network_ipv6, 'create_tcp_socket_for_host', factory)
    imagestore.ImageStoreClient._check_nbd_connection(None)
    factory.assert_not_called()
