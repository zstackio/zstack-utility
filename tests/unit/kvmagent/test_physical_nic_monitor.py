from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from kvmagent.plugins import physical_nic_monitor as monitor_module


class LinkEvent(dict):
    def __init__(self, name, state, kind=None):
        super(LinkEvent, self).__init__(event='RTM_NEWLINK')
        self.name = name
        self.state = state
        self.kind = kind

    def get_attr(self, name):
        return {'IFLA_IFNAME': self.name, 'IFLA_OPERSTATE': self.state}.get(name)

    def get_nested(self, *names):
        assert names == ('IFLA_LINKINFO', 'IFLA_INFO_KIND')
        return self.kind


def nic(name, active=True):
    return SimpleNamespace(interfaceName=name, carrierActive=active)


def notify(monitor, name, state, kind=None):
    monitor.physical_nic_monitor_get(
        SimpleNamespace(get=lambda: [LinkEvent(name, state, kind)]))


@pytest.fixture
def monitor(monkeypatch):
    instance = monitor_module.PhysicalNicMonitor()
    # Also isolate the old class-level caches when exercising the regression.
    for name in ('nic_info', 'bond_info', 'ip_info', 'alarms_to_send'):
        setattr(instance, name, {})
    instance.history_nics = []
    instance.configure({monitor_module.kvmagent.HOST_UUID: 'host-uuid',
                        monitor_module.kvmagent.SEND_COMMAND_URL: 'http://mn'})
    monkeypatch.setattr(monitor_module.ip_utils, 'find_host_physicl_nics',
                        Mock(return_value=['eth0', 'enp2s0']))
    monkeypatch.setattr(monitor_module.iproute, 'query_link',
                        Mock(return_value=SimpleNamespace(device_type=None)))
    monkeypatch.setattr(monitor_module.linux, 'get_nic_state_by_name',
                        Mock(return_value=True))
    monkeypatch.setattr(monitor_module.http, 'json_dump_post', Mock(), raising=False)
    return instance


@pytest.mark.parametrize('name', ['43499419d_o', '43499419d_eo', 'custom-name'])
def test_initialization_excludes_veth_by_type(monitor, name):
    monitor_module.iproute.query_link.return_value.device_type = 'veth'
    monitor.initial_data([nic('eth0'), nic(name)])

    assert monitor.nic_info == {'eth0': 'up'}
    assert monitor.history_nics == ['eth0']


def test_initialization_keeps_missing_physical_nic(monitor):
    monitor_module.iproute.query_link.side_effect = Exception('device disappeared')
    monitor.initial_data([nic('removed-physical-port')])
    notify(monitor, 'removed-physical-port', 'DOWN')

    assert monitor.nic_info['removed-physical-port'] == 'down'
    assert [event.status for event in
            monitor.alarms_to_send['removed-physical-port']] == ['down']


def test_repeated_initialization_does_not_duplicate_history(monitor):
    monitor.initial_data([nic('eth0')])
    monitor.initial_data([nic('eth0')])

    assert monitor.history_nics == ['eth0']


@pytest.mark.parametrize('entry', ['initialization', 'event'])
def test_confirmed_veth_removes_stale_state_and_pending_alarm(monitor, entry):
    name = '43499419d_o'
    monitor.nic_info[name] = 'up'
    monitor.history_nics = [name, name, 'eth0']
    monitor.bond_info[name] = 'stale-bond'
    monitor.ip_info[name] = '192.0.2.1'
    monitor.alarms_to_send[name] = [monitor_module.NicStatusChangeEvent('down')]
    monitor_module.iproute.query_link.return_value.device_type = 'veth'

    if entry == 'initialization':
        monitor.initial_data([nic(name)])
    else:
        notify(monitor, name, 'DOWN', 'veth')

    assert monitor.history_nics == ['eth0']
    for cache in (monitor.nic_info, monitor.bond_info, monitor.ip_info,
                  monitor.alarms_to_send):
        assert name not in cache


@pytest.mark.parametrize('state', ['DOWN', 'LOWERLAYERDOWN', 'UP', None])
def test_veth_events_never_register_or_queue_alarm(monitor, state):
    # Even a polluted discovery result must not override the event's type.
    monitor_module.ip_utils.find_host_physicl_nics.return_value = ['43499419d_o']
    notify(monitor, '43499419d_o', state, 'veth')

    assert not monitor.nic_info
    assert not monitor.history_nics
    assert not monitor.alarms_to_send


def test_veth_event_without_kind_uses_existing_link_query(monitor):
    monitor.nic_info['43499419d_o'] = 'up'
    monitor.history_nics = ['43499419d_o']
    monitor_module.iproute.query_link.return_value.device_type = 'veth'
    notify(monitor, '43499419d_o', 'DOWN')

    monitor_module.iproute.query_link.assert_called_once_with('43499419d_o')
    assert not monitor.nic_info
    assert not monitor.history_nics
    assert not monitor.alarms_to_send


def test_physical_nic_down_and_recovery_are_queued(monitor):
    monitor.initial_data([nic('eth0')])
    notify(monitor, 'eth0', 'DOWN')
    notify(monitor, 'eth0', 'UP')

    assert [event.status for event in monitor.alarms_to_send['eth0']] == ['down', 'up']
    monitor_module.iproute.query_link.assert_not_called()


def test_physical_nic_with_eip_like_name_is_not_excluded(monitor):
    name = 'physical_o'
    monitor_module.ip_utils.find_host_physicl_nics.return_value = [name]
    monitor.initial_data([nic(name)])
    notify(monitor, name, 'DOWN')

    assert [event.status for event in monitor.alarms_to_send[name]] == ['down']


def test_unknown_interface_does_not_require_link_query(monitor):
    notify(monitor, 'unmonitored-interface', 'DOWN')

    monitor_module.iproute.query_link.assert_not_called()
    assert not monitor.alarms_to_send


def test_new_physical_nic_is_still_discovered(monitor):
    notify(monitor, 'enp2s0', 'UP')

    assert monitor.nic_info['enp2s0'] == 'up'
    assert [event.status for event in monitor.alarms_to_send['enp2s0']] == ['up']


def test_bond_member_down_keeps_bond_alarm_information(monitor, monkeypatch):
    monitor.initial_data([nic('eth0')])
    notify(monitor, 'eth0', 'DOWN')
    monkeypatch.setattr(monitor_module.linux, 'get_bond_info_by_nic',
                        Mock(return_value='bond0'))
    monkeypatch.setattr(monitor_module.linux, 'get_ipv4_addr_by_bond',
                        Mock(return_value=['192.0.2.1/24']))

    alarm = monitor.get_nic_info('eth0', 'down')
    assert (alarm.nic, alarm.bond, alarm.status) == ('eth0', 'bond0', 'down')


def test_send_rejects_already_queued_veth_alarm(monitor):
    monitor.history_nics = ['43499419d_o']
    monitor_module.iproute.query_link.return_value.device_type = 'veth'
    alarm = monitor_module.PhysicalNicAlarm()
    alarm.nic, alarm.status = '43499419d_o', 'down'
    # This also covers the delayed UP callback scheduled by send_alarms().
    monitor.send_to_mn(alarm)

    monitor_module.http.json_dump_post.assert_not_called()


@pytest.mark.parametrize('missing', [False, True])
def test_send_preserves_physical_nic_alarm(monitor, missing):
    monitor.history_nics = ['eth0']
    if missing:
        monitor_module.iproute.query_link.side_effect = Exception('device disappeared')
    alarm = monitor_module.PhysicalNicAlarm()
    alarm.nic, alarm.status = 'eth0', 'down'
    monitor.send_to_mn(alarm)

    monitor_module.http.json_dump_post.assert_called_once_with(
        'http://mn', alarm, {'commandpath': '/host/physicalNic/alarm'})
    assert alarm.host == 'host-uuid'


def test_delayed_callback_is_dropped_after_veth_disappears(monitor):
    alarm = monitor_module.PhysicalNicAlarm()
    alarm.nic, alarm.status = '43499419d_o', 'up'
    monitor.nic_info[alarm.nic] = 'up'
    monitor.history_nics = [alarm.nic]
    notify(monitor, alarm.nic, 'DOWN', 'veth')
    monitor_module.iproute.query_link.side_effect = Exception('device disappeared')
    monitor.send_to_mn(alarm)

    monitor_module.http.json_dump_post.assert_not_called()


@pytest.mark.parametrize('veth', [False, True])
def test_queued_down_and_up_are_filtered_at_dispatch(monitor, monkeypatch, veth):
    name = '43499419d_o' if veth else 'eth0'
    monitor.history_nics = [name]
    events = [monitor_module.NicStatusChangeEvent(status) for status in ('down', 'up')]
    for event in events:
        event.change_time -= monitor.ALARM_WAITING_TIME + 1
    monitor.alarms_to_send[name] = events
    monitor_module.iproute.query_link.return_value.device_type = 'veth' if veth else None
    monkeypatch.setattr(monitor, 'get_nic_info', Mock(side_effect=lambda nic, status:
                        SimpleNamespace(nic=nic, status=status)))
    callbacks = []
    monkeypatch.setattr(monitor_module.thread, 'timer',
                        lambda delay, callback, args: SimpleNamespace(
                            start=lambda: callbacks.append((callback, args))))

    monitor.send_alarms(monitor.time_lock)
    for callback, args in callbacks:
        callback(*args)

    sent = monitor_module.http.json_dump_post.call_args_list
    assert [call.args[1].status for call in sent] == ([] if veth else ['down', 'up'])


def test_monitor_instances_do_not_share_nic_state():
    first = monitor_module.PhysicalNicMonitor()
    second = monitor_module.PhysicalNicMonitor()
    first.nic_info['eth0'] = 'up'
    first.history_nics.append('eth0')
    first.alarms_to_send['eth0'] = []

    assert not second.nic_info
    assert not second.history_nics
    assert not second.alarms_to_send
