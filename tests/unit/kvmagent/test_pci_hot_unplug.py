"""Exercise the legacy handler without importing its Python 2/libvirt stack."""
import functools
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[3]
VM_PLUGIN = ROOT / 'kvmagent/kvmagent/plugins/vm_plugin.py'
LINUX = ROOT / 'zstacklib/zstacklib/utils/linux.py'
ACCEPTED_RESULTS = [
    (0, 'Device detached successfully', ''),
    (124, '', ''),
    (1, '', 'Device hostdev0 is already in the process of unplug'),
    (1, 'Device hostdev0 is already in the process of unplug', ''),
]


def _function_source(path, name, indent=''):
    source = path.read_text()
    match = re.search(
        r'^' + indent + r'def ' + name + r'\(.*?(?=^' + indent + r'(?:def |class |@)|\Z)',
        source, re.MULTILINE | re.DOTALL,
    )
    assert match is not None, name
    return match.group(0)


@pytest.fixture
def unplug():
    state = SimpleNamespace(now=0, accepted_at=None, remove_after=10, attached=True)

    def sleep(seconds):
        state.now += seconds

    # Keep the branch's actual retry and polling behavior; advance a fake clock.
    utilities = {'functools': functools,
                 'time': SimpleNamespace(time=lambda: state.now, sleep=sleep)}
    for name in ('retry', 'wait_callback_success'):
        exec(compile(_function_source(LINUX, name), str(LINUX), 'exec'), utilities)
    linux = SimpleNamespace(
        retry=utilities['retry'], wait_callback_success=utilities['wait_callback_success'],
        write_to_temp_file=MagicMock(return_value='/tmp/pci.xml'),
    )
    state.results = iter([ACCEPTED_RESULTS[0]])
    state.detach_commands = []

    def bash_roe(command):
        if 'dumpxml' in command:
            removed = state.accepted_at is not None and state.now - state.accepted_at >= state.remove_after
            return 0, 'device is attached' if state.attached and not removed else '', ''
        assert 'detach-device' in command, command
        state.detach_commands.append(command)
        result = next(state.results)
        if result in ACCEPTED_RESULTS:
            state.accepted_at = state.now
        return result

    state.vm = MagicMock(state='Running')
    namespace = {
        'linux': linux, 'bash': SimpleNamespace(bash_roe=bash_roe),
        'jsonobject': SimpleNamespace(
            loads=lambda body: SimpleNamespace(**json.loads(body)),
            dumps=lambda rsp: json.dumps(vars(rsp))),
        'http': SimpleNamespace(REQUEST_BODY='body'),
        'HotUnplugPciDeviceRsp': lambda: SimpleNamespace(success=True, error=None),
        'get_vm_by_uuid': lambda uuid: state.vm,
        'get_vm_by_uuid_no_retry': lambda *args, **kwargs: state.vm,
        'Vm': SimpleNamespace(VM_STATE_SHUTDOWN='Shutdown'),
        'logger': MagicMock(),
    }
    exec(compile(_function_source(VM_PLUGIN, 'parse_pci_device_address'), str(VM_PLUGIN), 'exec'), namespace)
    handler = 'class Handler:\n' + _function_source(VM_PLUGIN, 'hot_unplug_pci_device', '    ')
    exec(compile(handler, str(VM_PLUGIN), 'exec'), namespace)
    plugin = namespace['Handler']()
    plugin.timeout_object = MagicMock()
    request = {'body': json.dumps({'vmUuid': 'vm-uuid', 'pciDeviceAddress': '0000:00:01.0',
                                  'type': 'GPU_Video_Controller', 'vendor': 'NVIDIA'})}
    state.run = lambda: json.loads(plugin.hot_unplug_pci_device(request))
    return state


@pytest.mark.parametrize('result', ACCEPTED_RESULTS)
def test_accepted_detach_waits_for_xml_removal_without_resending(unplug, result):
    unplug.results = iter([result])
    response = unplug.run()
    assert response['success'] is True, response
    assert unplug.now == 10
    assert unplug.detach_commands == ['timeout -k 5 60 virsh detach-device vm-uuid /tmp/pci.xml']


@pytest.mark.parametrize('result', ACCEPTED_RESULTS)
def test_accepted_detach_fails_if_device_never_disappears(unplug, result):
    unplug.results = iter([result])
    unplug.remove_after = float('inf')
    response = unplug.run()
    assert response['success'] is False
    assert 'pci device 0000:00:01.0 still exists on vm vm-uuid after 60 seconds' == response['error']
    assert len(unplug.detach_commands) == 1
    assert unplug.now == 61


def test_rejected_detach_is_retried(unplug):
    unplug.results = iter([(1, '', 'device is busy'), ACCEPTED_RESULTS[0]])
    response = unplug.run()
    assert response['success'] is True, response
    assert len(unplug.detach_commands) == 2
    assert unplug.now == 15


def test_rejected_detach_exhausts_existing_retry_budget(unplug):
    unplug.results = iter([(1, '', 'device is busy')] * 4)
    response = unplug.run()
    assert response['success'] is False
    assert 'device is busy' in response['error']
    assert len(unplug.detach_commands) == 4


def test_absent_device_needs_no_detach(unplug):
    unplug.attached = False
    assert unplug.run()['success'] is True
    assert unplug.detach_commands == []


@pytest.mark.parametrize('vm', [None, SimpleNamespace(state='Shutdown')])
def test_stopped_vm_needs_no_detach(unplug, vm):
    unplug.vm = vm
    assert unplug.run()['success'] is True
    assert unplug.detach_commands == []
