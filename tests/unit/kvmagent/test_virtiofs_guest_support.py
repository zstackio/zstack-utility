import json
from unittest.mock import MagicMock, call

import pytest

from kvmagent.plugins import virtiofs_plugin
from zstacklib.utils import http


@pytest.fixture
def guest(monkeypatch):
    domain = MagicMock()
    qga = MagicMock(state='Running', os='linux')
    qga_class = MagicMock(return_value=qga)
    qga_class.QGA_STATE_RUNNING = 'Running'
    monkeypatch.setattr(virtiofs_plugin, 'VmQga', qga_class)
    monkeypatch.setattr(virtiofs_plugin, 'is_qga_connected', lambda _: True)
    return domain, qga


@pytest.mark.parametrize('responses,commands,expected_error', [
    ([(0, 'nodev\tvirtiofs\n', '')], ['cat /proc/filesystems'], None),
    ([(0, 'nodev\tfuse\n', ''), (0, '', ''), (0, 'nodev\tvirtiofs\n', '')],
     ['cat /proc/filesystems', 'modprobe virtiofs', 'cat /proc/filesystems'], None),
    ([(0, 'nodev\tfuse\n', ''), (1, '', 'Module virtiofs not found')],
     ['cat /proc/filesystems', 'modprobe virtiofs'], 'Module virtiofs not found'),
    ([(0, 'nodev\tvirtiofs_other\n', ''), (1, '', 'Module virtiofs not found')],
     ['cat /proc/filesystems', 'modprobe virtiofs'], 'Module virtiofs not found'),
    ([(0, 'nodev\tfuse\n', ''), (0, '', ''), (0, 'nodev\tfuse\n', '')],
     ['cat /proc/filesystems', 'modprobe virtiofs', 'cat /proc/filesystems'],
     'not available'),
    ([(1, '', 'Permission denied')], ['cat /proc/filesystems'], 'Permission denied'),
    ([(0, '', ''), (0, '', ''), (1, '', 'read failed')],
     ['cat /proc/filesystems', 'modprobe virtiofs', 'cat /proc/filesystems'], 'read failed'),
    ([(0, '', ''), (127, '', 'modprobe: command not found')],
     ['cat /proc/filesystems', 'modprobe virtiofs'], 'modprobe: command not found'),
    ([RuntimeError('QGA command timeout')], ['cat /proc/filesystems'], 'QGA command timeout'),
])
def test_checks_actual_guest_filesystem_capability(guest, responses, commands, expected_error):
    domain, qga = guest
    qga.guest_exec_bash.side_effect = responses

    success, error = virtiofs_plugin.check_guest_virtiofs_support(domain)

    assert success is (expected_error is None)
    if expected_error is None:
        assert error is None
    else:
        assert expected_error in error
    assert [c.args[0] for c in qga.guest_exec_bash.call_args_list] == commands


def test_disconnected_qga_is_not_reported_as_unsupported_kernel(guest, monkeypatch):
    domain, qga = guest
    monkeypatch.setattr(virtiofs_plugin, 'is_qga_connected', lambda _: False)

    success, error = virtiofs_plugin.check_guest_virtiofs_support(domain)

    assert success is False
    assert 'QGA not connected' in error
    qga.guest_exec_bash.assert_not_called()


@pytest.mark.parametrize('state,os_type,error_text', [
    ('NotRunning', 'linux', 'QGA is not running'),
    ('Running', 'mswindows', 'Windows VM'),
])
def test_unusable_guest_execution_channel_is_rejected(guest, state, os_type, error_text):
    domain, qga = guest
    qga.state, qga.os = state, os_type

    success, error = virtiofs_plugin.check_guest_virtiofs_support(domain)

    assert success is False
    assert error_text in error
    qga.guest_exec_bash.assert_not_called()


def make_attach_request(mount_path='/mnt/models/test'):
    return {http.REQUEST_BODY: json.dumps({
        'vmInstanceUuid': 'vm-uuid', 'tag': 'model-tag',
        'sourcePath': '/var/lib/zstack/aios/vm-views/vm-uuid',
        'mountPath': mount_path,
    }), http.REQUEST_HEADER: {}}


@pytest.fixture
def attach_guest(guest, monkeypatch):
    domain, qga = guest
    domain.XMLDesc.return_value = '<domain><devices/></domain>'
    connection = MagicMock()
    monkeypatch.setattr(virtiofs_plugin, '_ensure_source_for_attach',
                        lambda _: MagicMock(path='/var/lib/zstack/aios/vm-views/vm-uuid'))
    monkeypatch.setattr(virtiofs_plugin, 'get_vm_domain', lambda _: (domain, connection))
    monkeypatch.setattr(virtiofs_plugin, 'check_vm_memory_backing', lambda _: (True, None))
    monkeypatch.setattr(virtiofs_plugin, 'get_virtiofsd_path', lambda: '/usr/libexec/virtiofsd')
    monkeypatch.setattr(virtiofs_plugin.time, 'sleep', lambda _: None)
    return domain, qga, connection


def test_unsupported_guest_returns_error_before_device_attach(attach_guest):
    domain, qga, connection = attach_guest
    qga.guest_exec_bash.side_effect = [
        (0, 'nodev\tfuse\n', ''), (1, '', 'Module virtiofs not found'),
    ]

    response = json.loads(virtiofs_plugin.VirtiofsPlugin().attach_virtiofs(make_attach_request()))

    assert response['success'] is False
    assert 'Module virtiofs not found' in response['error']
    assert response['qgaMountAttempted'] is False
    domain.attachDeviceFlags.assert_not_called()
    domain.detachDeviceFlags.assert_not_called()
    connection.close.assert_called_once()


@pytest.mark.parametrize('mount_result,success', [
    ((32, '', 'mount: permission denied'), False),
    ((0, '', ''), True),
    (RuntimeError('QGA command timeout'), False),
])
def test_mount_result_reaches_response_without_device_rollback(attach_guest, mount_result, success):
    domain, qga, connection = attach_guest
    qga.guest_exec_bash.side_effect = [
        (0, 'nodev\tvirtiofs\n', ''),  # Capability check.
        (0, '', ''),                   # Create guest mount directory.
        (1, '', ''),                   # Directory is not mounted yet.
        mount_result, mount_result,   # Existing mount retry, if needed.
    ]
    steps = MagicMock()
    steps.attach_mock(qga.guest_exec_bash, 'guest_exec')
    steps.attach_mock(domain.attachDeviceFlags, 'attach')

    response = json.loads(virtiofs_plugin.VirtiofsPlugin().attach_virtiofs(make_attach_request()))

    assert response['success'] is success
    assert response['qgaMountSuccess'] is success
    assert response['qgaMountAttempted'] is True
    if not success:
        assert response['error'] == response['qgaMountError']
        assert 'permission denied' in response['error'] or 'timed out' in response['error']
    assert domain.attachDeviceFlags.call_count == 2
    assert steps.mock_calls[0] == call.guest_exec(
        'cat /proc/filesystems', retry=virtiofs_plugin._qga_retry_count(
            virtiofs_plugin.QGA_MKDIR_TIMEOUT_SECS))
    domain.detachDeviceFlags.assert_not_called()
    connection.close.assert_called_once()


def test_device_only_attach_does_not_require_guest_mount_support(attach_guest):
    domain, qga, _ = attach_guest

    response = json.loads(virtiofs_plugin.VirtiofsPlugin().attach_virtiofs(
        make_attach_request(mount_path=None)))

    assert response['success'] is True
    assert response['qgaMountAttempted'] is False
    assert domain.attachDeviceFlags.call_count == 2
    qga.guest_exec_bash.assert_not_called()
    domain.detachDeviceFlags.assert_not_called()


@pytest.fixture
def stateful_attach(attach_guest):
    domain, qga, connection = attach_guest
    state = {'live_xml': None, 'config_xml': None, 'mount_calls': 0, 'failures_left': 2}

    def domain_xml(flags):
        xml = state['live_xml'] if flags == 0 else state['config_xml']
        return '<domain><devices>%s</devices></domain>' % (xml or '')

    def attach(xml, flags):
        key = 'live_xml' if flags == virtiofs_plugin.libvirt.VIR_DOMAIN_AFFECT_LIVE else 'config_xml'
        if state[key] is not None:
            raise RuntimeError('filesystem target already exists')
        state[key] = xml

    def execute(command, **kwargs):
        if command == 'cat /proc/filesystems':
            return 0, 'nodev\tvirtiofs\n', ''
        if command.startswith('mkdir '):
            return 0, '', ''
        if command.startswith('mountpoint '):
            return 1, '', ''
        if command.startswith('mount -t virtiofs '):
            assert state['live_xml'] is not None
            state['mount_calls'] += 1
            if state['failures_left'] > 0:
                state['failures_left'] -= 1
                return 32, '', 'temporary guest mount failure'
            return 0, '', ''
        raise AssertionError(command)

    domain.XMLDesc.side_effect = domain_xml
    domain.attachDeviceFlags.side_effect = attach
    qga.guest_exec_bash.side_effect = execute
    return domain, qga, state


def test_retry_reuses_attached_device_and_reaches_guest_mount(stateful_attach):
    domain, _, state = stateful_attach
    plugin = virtiofs_plugin.VirtiofsPlugin()

    first = json.loads(plugin.attach_virtiofs(make_attach_request()))
    second = json.loads(plugin.attach_virtiofs(make_attach_request()))

    assert first['success'] is False
    assert 'temporary guest mount failure' in first['error']
    assert second['success'] is True
    assert second['qgaMountSuccess'] is True
    assert state['mount_calls'] == 3
    assert domain.attachDeviceFlags.call_count == 2  # One LIVE and one CONFIG attach.
    domain.detachDeviceFlags.assert_not_called()


def test_repeated_mount_failure_preserves_device_and_error(stateful_attach):
    domain, _, state = stateful_attach
    state['failures_left'] = 12
    plugin = virtiofs_plugin.VirtiofsPlugin()

    replies = [json.loads(plugin.attach_virtiofs(make_attach_request())) for _ in range(6)]

    assert all(r['success'] is False and 'temporary guest mount failure' in r['error'] for r in replies)
    assert state['mount_calls'] == 12
    assert state['live_xml'] is not None and state['config_xml'] is not None
    assert domain.attachDeviceFlags.call_count == 2
    domain.detachDeviceFlags.assert_not_called()


@pytest.mark.parametrize('existing_scope', ['live_xml', 'config_xml'])
def test_restore_checks_running_device_instead_of_persistent_config(stateful_attach, existing_scope):
    domain, _, state = stateful_attach
    state[existing_scope] = virtiofs_plugin.build_virtiofs_xml(
        'model-tag', '/var/lib/zstack/aios/vm-views/vm-uuid')
    state['failures_left'] = 0

    reply = json.loads(virtiofs_plugin.VirtiofsPlugin().attach_virtiofs(make_attach_request()))

    assert reply['success'] is True
    assert state['mount_calls'] == 1
    live_calls = [c for c in domain.attachDeviceFlags.call_args_list
                  if c.args[1] == virtiofs_plugin.libvirt.VIR_DOMAIN_AFFECT_LIVE]
    assert len(live_calls) == (0 if existing_scope == 'live_xml' else 1)
    domain.detachDeviceFlags.assert_not_called()


@pytest.mark.parametrize('source,driver', [
    ('/another/model', 'virtiofs'),
    ('/var/lib/zstack/aios/vm-views/vm-uuid', 'path'),
])
def test_existing_tag_cannot_be_reused_for_another_source_or_driver(attach_guest, source, driver):
    domain, qga, _ = attach_guest
    domain.XMLDesc.return_value = (
        '<domain><devices><filesystem type="mount"><driver type="%s"/>'
        '<source dir="%s"/><target dir="model-tag"/></filesystem></devices></domain>'
        % (driver, source))
    qga.guest_exec_bash.return_value = (0, 'nodev\tvirtiofs\n', '')

    reply = json.loads(virtiofs_plugin.VirtiofsPlugin().attach_virtiofs(make_attach_request()))

    assert reply['success'] is False
    assert 'conflict' in reply['error'].lower()
    assert reply['qgaMountAttempted'] is False
    domain.attachDeviceFlags.assert_not_called()
    domain.detachDeviceFlags.assert_not_called()


def test_unreadable_device_state_returns_error_without_attaching(attach_guest):
    domain, qga, _ = attach_guest
    domain.XMLDesc.side_effect = RuntimeError('domain XML unavailable')
    qga.guest_exec_bash.return_value = (0, 'nodev\tvirtiofs\n', '')

    reply = json.loads(virtiofs_plugin.VirtiofsPlugin().attach_virtiofs(make_attach_request()))

    assert reply['success'] is False
    assert 'domain XML unavailable' in reply['error']
    domain.attachDeviceFlags.assert_not_called()
    domain.detachDeviceFlags.assert_not_called()
