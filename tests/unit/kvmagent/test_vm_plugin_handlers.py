# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownParameterType=false
# pyright: reportMissingParameterType=false
# pyright: reportAny=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownLambdaType=false
# pyright: reportAttributeAccessIssue=false
from __future__ import annotations
"""Handler-level unit tests for kvmagent.plugins.vm_plugin."""
import json
import tempfile
import urllib.parse
from collections.abc import Iterator
from typing import Callable
import pytest
from unittest.mock import patch, MagicMock
from xml.etree import ElementTree as ET

from zstacklib.utils import http, jsonobject
from kvmagent.plugins import vm_artifact
from kvmagent.plugins import vm_plugin


def _make_req(body_dict=None):
    body = json.dumps(body_dict or {})
    return {http.REQUEST_BODY: body, http.REQUEST_HEADER: {}}


vm_plugin.http = http
vm_plugin.jsonobject = jsonobject


def test_console_listen_address_uses_ipv4_default_for_ipv4_host():
    assert vm_plugin.get_console_listen_address('192.168.1.10') == '0.0.0.0'


def test_console_listen_address_uses_dual_stack_for_ipv6_host():
    assert vm_plugin.get_console_listen_address('2001:db8::10') == '::'


def test_build_migration_hostname_supports_ipv4():
    assert vm_plugin.build_migration_hostname('172.24.1.2') == '172-24-1-2.zstack.org'


def test_build_migration_hostname_supports_ipv6():
    assert vm_plugin.build_migration_hostname('fd00:5:5:28::62:d0e5') == \
        'fd00-5-5-28--62-d0e5.zstack.org'


def test_build_migration_hostname_supports_bracketed_ipv6():
    assert vm_plugin.build_migration_hostname('[fd00:5:5:28::62:d0e5]') == \
        'fd00-5-5-28--62-d0e5.zstack.org'


def test_build_nbd_url_wraps_ipv6_host():
    assert vm_plugin.build_nbd_url('192.168.10.10', 10401) == 'nbd://192.168.10.10:10401'
    assert vm_plugin.build_nbd_url('fd00:5:5:28::5e:508b', 10401) == 'nbd://[fd00:5:5:28::5e:508b]:10401'
    assert vm_plugin.build_nbd_url('fd00:5:5:28::5e:508b', 10401, 'parent0') == \
        'nbd://[fd00:5:5:28::5e:508b]:10401/parent0'


def _make_vm_plugin():
    plugin = vm_plugin.VmPlugin.__new__(vm_plugin.VmPlugin)
    plugin.config = {}
    return plugin


@pytest.mark.kvmagent
class TestMigrateVmFalseFailure:
    def test_destination_running_confirms_false_migration_failure(self, monkeypatch):
        conn = MagicMock()
        cmd = MagicMock(
            vmUuid='vm-uuid',
            destHostManagementIp='10.0.0.2',
            destHostIp='172.24.0.2',
            useTls=False,
        )
        dst_vm = MagicMock(state=vm_plugin.Vm.VM_STATE_RUNNING)
        get_connect = MagicMock(return_value=conn)
        get_vm_by_uuid = MagicMock(return_value=dst_vm)

        monkeypatch.setattr(vm_plugin, 'get_connect', get_connect)
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', get_vm_by_uuid)

        assert vm_plugin.Vm.is_running_on_destination(cmd) is True
        get_connect.assert_called_once_with('10.0.0.2', False)
        get_vm_by_uuid.assert_called_once_with('vm-uuid', False, conn)
        conn.close.assert_called_once()

    def test_destination_not_running_keeps_migration_failure(self, monkeypatch):
        conn = MagicMock()
        cmd = MagicMock(
            vmUuid='vm-uuid',
            destHostManagementIp='10.0.0.2',
            destHostIp='172.24.0.2',
            useTls=False,
        )
        dst_vm = MagicMock(state=vm_plugin.Vm.VM_STATE_PAUSED)

        monkeypatch.setattr(vm_plugin, 'get_connect', MagicMock(return_value=conn))
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', MagicMock(return_value=dst_vm))

        assert vm_plugin.Vm.is_running_on_destination(cmd) is False

    def test_destination_verify_error_confirms_false_migration_failure(self, monkeypatch):
        cmd = MagicMock(
            vmUuid='vm-uuid',
            destHostManagementIp='10.0.0.2',
            destHostIp='172.24.0.2',
            useTls=False,
        )

        monkeypatch.setattr(vm_plugin, 'get_connect', MagicMock(side_effect=Exception('connect failed')))

        assert vm_plugin.Vm.is_running_on_destination(cmd) is True


@pytest.mark.kvmagent
class TestAttachIsoHandler:
    def test_attach_iso(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'vmUuid': 'vm-uuid'})
        result = plugin.attach_iso(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.get_vm_by_uuid.assert_called_once_with('vm-uuid')
        mock_vm.attach_iso.assert_called_once()


@pytest.mark.kvmagent
class TestDetachIsoHandler:
    def test_detach_iso(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'vmUuid': 'vm-uuid'})
        result = plugin.detach_iso(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.get_vm_by_uuid.assert_called_once_with('vm-uuid')
        mock_vm.detach_iso.assert_called_once()


@pytest.mark.kvmagent
class TestUpdateNicHandler:
    def test_update_nic(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'vmInstanceUuid': 'vm-uuid'})
        result = plugin.update_nic(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.get_vm_by_uuid.assert_called_once_with('vm-uuid')
        mock_vm.update_nic.assert_called_once()

@pytest.mark.kvmagent
class TestHardenConsoleHandler:
    def test_harden_console(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'vmUuid': 'vm-uuid', 'hostManagementIp': '10.0.0.1'})
        result = plugin.harden_console(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.harden_console.assert_called_once_with('10.0.0.1')


@pytest.mark.kvmagent
class TestCreateCephSecretKeyHandler:
    def test_create_ceph_secret_key(self):
        plugin = _make_vm_plugin()
        vm_plugin.VmPlugin._create_ceph_secret_key = MagicMock()

        req = _make_req({'userKey': 'secret', 'uuid': 'secret-uuid'})
        result = plugin.create_ceph_secret_key(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.VmPlugin._create_ceph_secret_key.assert_called_once_with('secret', 'secret-uuid')


@pytest.mark.kvmagent
class TestVmPriorityHandler:
    def test_vm_priority(self):
        plugin = _make_vm_plugin()
        from zstacklib.utils import linux
        linux.find_vm_pid_by_uuid = MagicMock(return_value=12345)
        linux.set_vm_priority = MagicMock()

        req = _make_req({
            'priorityConfigStructs': [
                {'vmUuid': 'vm-uuid', 'priority': 10},
            ]
        })
        result = plugin.vm_priority(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        linux.find_vm_pid_by_uuid.assert_called_once_with('vm-uuid')
        linux.set_vm_priority.assert_called_once()


@pytest.mark.kvmagent
class TestKvmResizeVolumeHandler:
    def test_kvm_resize_volume(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        vm_plugin.touchQmpSocketWhenExists = MagicMock()

        req = _make_req({'vmUuid': 'vm-uuid', 'volume': {'uuid': 'vol-uuid'}, 'size': 1024})
        result = plugin.kvm_resize_volume(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.get_vm_by_uuid.assert_called_once_with('vm-uuid', exception_if_not_existing=False)
        mock_vm.resize_volume.assert_called_once()
        vm_plugin.touchQmpSocketWhenExists.assert_called_once_with('vm-uuid')


@pytest.mark.kvmagent
class TestApplyMemoryBalloonHandler:
    def test_apply_memory_balloon(self):
        plugin = _make_vm_plugin()
        plugin.do_apply_memory_balloon_to_vm = MagicMock()

        req = _make_req({
            'vmUuids': ['vm-uuid'],
            'direction': 'Increase',
            'adjustPercent': 10,
            'vmReservedMemory': None,
        })
        result = plugin.apply_memory_balloon(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.do_apply_memory_balloon_to_vm.assert_called_once_with('vm-uuid', 'Increase', 10, 0)


@pytest.mark.kvmagent
class TestCleanFirmwareFlashHandler:
    def test_clean_firmware_flash(self):
        plugin = _make_vm_plugin()
        vm_plugin.get_vm_by_uuid_no_retry = MagicMock(return_value=None)
        plugin.clean_vm_firmware_flash = MagicMock()

        req = _make_req({'vmUuid': 'vm-uuid'})
        result = plugin.clean_firmware_flash(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.clean_vm_firmware_flash.assert_called_once_with('vm-uuid')


@pytest.mark.kvmagent
class TestChangeNicStateHandler:
    def test_change_nic_state(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'vmUuid': 'vm-uuid', 'state': 'enable'})
        result = plugin.change_nic_state(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.enable_nic.assert_called_once()


@pytest.mark.kvmagent
class TestDetachNicHandler:
    def test_detach_nic(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'nic': {'type': 'VNIC', 'uuid': 'nic-uuid'},
        })
        result = plugin.detach_nic(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.get_vm_by_uuid.assert_called_once_with('vm-uuid', False)
        mock_vm.detach_nic.assert_called_once()


@pytest.mark.kvmagent
class TestGetNicQosHandler:
    def test_get_nic_qos(self):
        plugin = _make_vm_plugin()
        from zstacklib.utils import shell
        shell.call = MagicMock(side_effect=['1000\n', '2000\n'])

        req = _make_req({'vmUuid': 'vm-uuid', 'internalName': 'eth0'})
        result = plugin.get_nic_qos(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['inbound'] == 1000 * 8 * 1024
        assert rsp['outbound'] == 2000 * 8 * 1024


@pytest.mark.kvmagent
class TestChangeVmPasswordHandler:
    def test_change_vm_password(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({
            'accountPerference': {
                'vmUuid': 'vm-uuid',
                'accountPassword': 'secret',
                'accountName': 'root',
            }
        })
        result = plugin.change_vm_password(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.change_vm_password.assert_called_once()
        assert rsp['accountPerference']['accountPassword'] == '******'


@pytest.mark.kvmagent
class TestCheckVolumeHandler:
    def test_check_volume(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({
            'uuid': 'vm-uuid',
            'volumes': [{'installPath': '/path/vol1'}, {'installPath': '/path/vol2'}],
        })
        result = plugin.check_volume(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert mock_vm._get_target_disk.call_count == 2


@pytest.mark.kvmagent
class TestDeleteConsoleFirewallRuleHandler:
    def test_delete_console_firewall_rule(self):
        plugin = _make_vm_plugin()
        mock_rule = MagicMock()

        with patch.object(vm_plugin, 'VncPortIptableRule', return_value=mock_rule):
            req = _make_req({'vmInternalId': 123, 'hostManagementIp': '10.0.0.2'})
            result = plugin.delete_console_firewall_rule(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_rule.delete.assert_called_once()


@pytest.mark.kvmagent
class TestVncPortIptableRule:
    def test_cleanup_iptables_skips_missing_ip6tables(self):
        ipv4_iptables = MagicMock()

        with patch.object(vm_plugin.iptables, 'from_iptables_save', return_value=ipv4_iptables), \
                patch.object(vm_plugin.iptables, 'from_ip6tables_save', side_effect=RuntimeError('no ip6tables')):
            rule = vm_plugin.VncPortIptableRule()

            assert rule._load_cleanup_iptables() == [ipv4_iptables]


@pytest.mark.kvmagent
class TestGetIothreadPinHandler:
    def test_get_iothread_pin(self):
        plugin = _make_vm_plugin()
        plugin.get_iothread_info = MagicMock(return_value=[('1', '0-3'), ('2', '4-7')])

        req = _make_req({'vmUuid': 'vm-uuid'})
        result = plugin.get_iothread_pin(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['ioThreadInfo'] == [
            {'ioThreadId': '1', 'ioThreadPin': '0-3'},
            {'ioThreadId': '2', 'ioThreadPin': '4-7'},
        ]


@pytest.mark.kvmagent
class TestQueryBlockJobStatusHandler:
    def test_query_block_job_status(self):
        plugin = _make_vm_plugin()
        vm_plugin.qmp.execute_qmp_command = MagicMock(return_value=[])
        with patch('time.sleep', return_value=None):
            req = _make_req({'vmUuid': 'vm-uuid'})
            result = plugin.query_block_job_status(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['status'] == 'completed'
        assert rsp['percent'] == 100
        assert vm_plugin.qmp.execute_qmp_command.call_count == 6


@pytest.mark.kvmagent
class TestSetEmulatorPinningHandler:
    def test_set_emulator_pinning(self):
        plugin = _make_vm_plugin()
        from zstacklib.utils import shell
        shell.call = MagicMock()

        req = _make_req({'uuid': 'vm-uuid', 'emulatorPinning': '0-3'})
        result = plugin.set_emulator_pinning(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        shell.call.assert_called_once_with('virsh emulatorpin vm-uuid  0-3')


@pytest.mark.kvmagent
class TestAttachSshKeyPairHandler:
    def test_attach_ssh_key_pair(self):
        plugin = _make_vm_plugin()
        plugin.do_attach_ssh_key_pair = MagicMock()

        req = _make_req({'vmInstanceUuid': 'vm-uuid', 'publicKey': 'ssh-rsa AAA'})
        result = plugin.attach_ssh_key_pair(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.do_attach_ssh_key_pair.assert_called_once_with('vm-uuid', 'ssh-rsa AAA')


@pytest.mark.kvmagent
class TestDetachSshKeyPairHandler:
    def test_detach_ssh_key_pair(self):
        plugin = _make_vm_plugin()
        plugin.do_detach_ssh_key_pair = MagicMock()

        req = _make_req({'vmInstanceUuid': 'vm-uuid', 'publicKey': 'ssh-rsa AAA'})
        result = plugin.detach_ssh_key_pair(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.do_detach_ssh_key_pair.assert_called_once_with('vm-uuid', 'ssh-rsa AAA')


@pytest.mark.kvmagent
class TestLogoutIscsiTargetHandler:
    def test_logout_iscsi_target(self):
        def _identity_lock(*_args, **_kwargs):
            def _decorator(func):
                return func
            return _decorator

        vm_plugin.lock.lock = _identity_lock
        import importlib
        reloaded = importlib.reload(vm_plugin)
        reloaded.http = http
        reloaded.jsonobject = jsonobject
        plugin = reloaded.VmPlugin.__new__(reloaded.VmPlugin)
        plugin.config = {}
        from zstacklib.utils import shell
        shell.call = MagicMock()

        req = _make_req({'target': 'iqn.test', 'hostname': '127.0.0.1', 'port': 3260})
        result = plugin.logout_iscsi_target(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        shell.call.assert_called_once_with(
            'iscsiadm  -m node  --targetname "iqn.test" --portal "127.0.0.1:3260" --logout'
        )


@pytest.mark.kvmagent
class TestSyncVmDeviceinfoHandler:
    def test_sync_vm_deviceinfo(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        plugin.get_vm_device_info = MagicMock(return_value=(['nic'], ['dev'], None))
        plugin.collect_vm_virtualizer_info = MagicMock()
        vm_plugin.pci.get_pci_passthrough_mapping = MagicMock(return_value={'host': 'guest'})
        vm_plugin.pci.get_mdev_passthrough_mapping = MagicMock(return_value={'mdev': 'info'})

        req = _make_req({'vmInstanceUuid': 'vm-uuid'})
        result = plugin.sync_vm_deviceinfo(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['pciDeviceInfos'] == {'guest': 'host'}
        assert rsp['mdevDeviceInfos'] == {'mdev': 'info'}
        plugin.get_vm_device_info.assert_called_once_with('vm-uuid')
        vm_plugin.get_vm_by_uuid.assert_called_once_with('vm-uuid')


@pytest.mark.kvmagent
class TestCheckVmStateHandler:
    def test_check_vm_state(self):
        plugin = _make_vm_plugin()
        vm_plugin.bash.bash_r = MagicMock(return_value=0)
        vm_plugin.get_all_vm_states = MagicMock(return_value={})
        vm_plugin.get_all_vm_states_with_process = MagicMock(return_value={'vm1': vm_plugin.Vm.VM_STATE_RUNNING})
        plugin.get_vm_stat_with_ps = MagicMock(return_value=vm_plugin.Vm.VM_STATE_SHUTDOWN)

        req = _make_req({'vmUuids': ['vm-uuid']})
        result = plugin.check_vm_state(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['states']['vm-uuid'] == vm_plugin.Vm.VM_STATE_SHUTDOWN


@pytest.mark.kvmagent
class TestStopVmHandler:
    def test_stop_vm(self):
        plugin = _make_vm_plugin()
        plugin._dump = MagicMock()
        plugin._record_operation = MagicMock()
        plugin._stop_vm = MagicMock()
        vm_plugin.notify_vrouter = MagicMock()
        vm_plugin.transform_to_tf_uuid = MagicMock(return_value='tf-uuid')

        req = _make_req({'uuid': 'vm-uuid', 'debug': False, 'timeout': 10, 'vmNics': [{'uuid': 'nic-uuid', 'type': 'TFVNIC'}]})
        result = plugin.stop_vm(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin._stop_vm.assert_called_once()
        vm_plugin.notify_vrouter.assert_called_once()

    def test_stop_vm_ignore_not_found_error(self):
        plugin = _make_vm_plugin()
        plugin.kill_vm = MagicMock()
        cmd = MagicMock()
        cmd.uuid = 'vm-uuid'
        cmd.type = 'grace'
        cmd.ignoreNotFoundError = True

        vm_plugin.get_vm_by_uuid = MagicMock(return_value=None)
        vm_plugin.delVnicFromOvsByVmUuidIfExist = MagicMock()

        plugin._stop_vm(cmd)

        vm_plugin.get_vm_by_uuid.assert_called_once_with('vm-uuid', exception_if_not_existing=False)
        vm_plugin.delVnicFromOvsByVmUuidIfExist.assert_called_once_with('vm-uuid')
        plugin.kill_vm.assert_called_once_with('vm-uuid')


@pytest.mark.kvmagent
class TestPauseVmHandler:
    def test_pause_vm(self):
        plugin = _make_vm_plugin()
        plugin._record_operation = MagicMock()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'uuid': 'vm-uuid'})
        result = plugin.pause_vm(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.pause.assert_called_once()


@pytest.mark.kvmagent
class TestResumeVmHandler:
    def test_resume_vm(self):
        plugin = _make_vm_plugin()
        plugin._record_operation = MagicMock()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'uuid': 'vm-uuid'})
        result = plugin.resume_vm(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.resume.assert_called_once()


@pytest.mark.kvmagent
class TestRebootVmHandler:
    def test_reboot_vm(self):
        plugin = _make_vm_plugin()
        plugin._record_operation = MagicMock()
        plugin.collect_vm_virtualizer_info = MagicMock()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'uuid': 'vm-uuid'})
        result = plugin.reboot_vm(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.reboot.assert_called_once()
        plugin.collect_vm_virtualizer_info.assert_called_once()


@pytest.mark.kvmagent
class TestDestroyVmHandler:
    def test_destroy_vm(self):
        plugin = _make_vm_plugin()
        plugin._record_operation = MagicMock()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        vm_plugin.ovs.isVmUseOpenvSwitch = MagicMock(return_value=False)
        vm_plugin.delVnicFromOvsByVmUuidIfExist = MagicMock()
        vm_plugin.notify_vrouter = MagicMock()
        vm_plugin.transform_to_tf_uuid = MagicMock(return_value='tf-uuid')

        req = _make_req({'uuid': 'vm-uuid', 'vmNics': [{'uuid': 'nic-uuid', 'type': 'TFVNIC'}]})
        result = plugin.destroy_vm(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.destroy.assert_called_once()


@pytest.mark.kvmagent
class TestAttachDataVolumeHandler:
    def test_attach_data_volume(self):
        plugin = _make_vm_plugin()
        plugin.get_device_address_info = MagicMock(return_value=vm_plugin.VirtualDeviceInfo())
        vm_plugin.touchQmpSocketWhenExists = MagicMock()
        mock_vm = MagicMock()
        mock_vm.state = vm_plugin.Vm.VM_STATE_RUNNING
        mock_vm._get_target_disk = MagicMock(return_value=(MagicMock(), 'vda'))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'vmInstanceUuid': 'vm-uuid', 'volume': {'installPath': '/path/vol', 'volumeUuid': 'vol-uuid'}, 'addons': {}})
        result = plugin.attach_data_volume(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.attach_data_volume.assert_called_once()
        mock_vm.refresh.assert_called_once()


@pytest.mark.kvmagent
class TestDetachDataVolumeHandler:
    def test_detach_data_volume(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.state = vm_plugin.Vm.VM_STATE_RUNNING
        mock_vm._get_target_disk = MagicMock(return_value=(MagicMock(), 'vda'))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        vm_plugin.volume_support_block_node = MagicMock(return_value=False)

        req = _make_req({'vmInstanceUuid': 'vm-uuid', 'volume': {'installPath': '/path/vol', 'volumeUuid': 'vol-uuid'}})
        result = plugin.detach_data_volume(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.detach_data_volume.assert_called_once()


@pytest.mark.kvmagent
class TestSetVolumeBandwidthHandler:
    def test_set_volume_bandwidth(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm._get_target_disk = MagicMock(return_value=(None, 'vda'))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        from zstacklib.utils import shell
        shell.call = MagicMock()

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'volume': {'installPath': '/path/vol'},
            'mode': 'total',
            'totalBandwidth': 1024,
            'readBandwidth': 0,
            'writeBandwidth': 0,
            'totalIOPS': 0,
            'readIOPS': 0,
            'writeIOPS': 0,
        })
        result = plugin.set_volume_bandwidth(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        shell.call.assert_called()


@pytest.mark.kvmagent
class TestDeleteVolumeBandwidthHandler:
    def test_delete_volume_bandwidth(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm._get_target_disk = MagicMock(return_value=(None, 'vda'))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        plugin._get_volume_bandwidth_value = MagicMock(return_value='0')
        from zstacklib.utils import shell
        shell.call = MagicMock()

        req = _make_req({'vmUuid': 'vm-uuid', 'volume': {'installPath': '/path/vol'}, 'mode': 'all'})
        result = plugin.delete_volume_bandwidth(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        shell.call.assert_called()


@pytest.mark.kvmagent
class TestGetVolumeBandwidthHandler:
    def test_get_volume_bandwidth(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm._get_target_disk = MagicMock(return_value=(None, 'vda'))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        from zstacklib.utils import shell
        shell.call = MagicMock(return_value=(
            'total_bytes_sec: 1024\n'
            'read_bytes_sec: 2048\n'
            'write_bytes_sec: 4096\n'
            'total_iops_sec: 12\n'
            'read_iops_sec: 3\n'
            'write_iops_sec: 4\n'
        ))

        req = _make_req({'vmUuid': 'vm-uuid', 'volume': {'installPath': '/path/vol'}})
        result = plugin.get_volume_bandwidth(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['bandWidth'] == '1024'
        assert rsp['bandWidthRead'] == '2048'
        assert rsp['bandWidthWrite'] == '4096'
        assert rsp['iopsTotal'] == '12'
        assert rsp['iopsRead'] == '3'
        assert rsp['iopsWrite'] == '4'


@pytest.mark.kvmagent
class TestSetNicQosHandler:
    def test_set_nic_qos(self):
        plugin = _make_vm_plugin()
        from zstacklib.utils import shell
        shell.call = MagicMock()

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'internalName': 'eth0',
            'inboundBandwidth': 1024 * 8 * 1024,
            'outboundBandwidth': 2048 * 8 * 1024,
        })
        result = plugin.set_nic_qos(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        shell.call.assert_called()


@pytest.mark.kvmagent
class TestAttachNicHandler:
    def test_attach_nic(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        iface = MagicMock()
        iface.mac.address_ = '00:11:22:33:44:55'
        iface.address.bus_ = '0x00'
        iface.address.function_ = '0x0'
        iface.address.type_ = 'pci'
        iface.address.domain_ = '0x0000'
        iface.address.slot_ = '0x05'
        mock_vm.domain_xmlobject.devices.get_child_node_as_list = MagicMock(return_value=[iface])
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'vmUuid': 'vm-uuid', 'nic': {'mac': '00:11:22:33:44:55'}})
        result = plugin.attach_nic(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.attach_nic.assert_called_once()


@pytest.mark.kvmagent
class TestNotifyTfNicHandler:
    def test_notify_tf_nic(self):
        plugin = _make_vm_plugin()
        vm_plugin.notify_vrouter = MagicMock()
        vm_plugin.transform_to_tf_uuid = MagicMock(side_effect=lambda v: 'tf-%s' % v)

        req = _make_req({
            'accountUuid': 'acct-uuid',
            'vmInstanceUuid': 'vm-uuid',
            'sugonSdnAction': 'add',
            'nics': [{
                'type': 'TFVNIC',
                'uuid': 'nic-uuid',
                'l2NetworkUuid': 'l2-uuid',
                'nicInternalName': 'tap0',
                'mac': '00:11:22:33:44:55',
                'ipForTf': '10.0.0.1',
            }]
        })
        result = plugin.notify_tf_nic(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.notify_vrouter.assert_called_once()


@pytest.mark.kvmagent
class TestGetConsolePortHandler:
    def test_get_console_port(self):
        plugin = _make_vm_plugin()
        plugin.get_vm_console_info = MagicMock(return_value=('vnc', 5901, None, None))

        req = _make_req({'vmUuid': 'vm-uuid'})
        result = plugin.get_console_port(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['port'] == 5901


@pytest.mark.kvmagent
class TestTakeConsoleScreenshotHandler:
    def test_take_console_screenshot(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        vm_plugin.image.convert_image = MagicMock(return_value='/tmp/vm-uuid.png')
        vm_plugin.linux.rm_file_force = MagicMock()
        stream = MagicMock()
        stream.recv = MagicMock(side_effect=[b''])
        stream.finish = MagicMock()

        def _fake_reconnect(_func):
            def _wrapper(*_args, **_kwargs):
                return stream
            return _wrapper

        vm_plugin.LibvirtAutoReconnect = _fake_reconnect

        from unittest.mock import mock_open
        m_write = mock_open()
        m_read = mock_open(read_data=b'img')

        def _open_side_effect(file, mode='r', *args, **kwargs):
            if 'rb' in mode:
                return m_read(file, mode, *args, **kwargs)
            return m_write(file, mode, *args, **kwargs)

        with patch('builtins.open', side_effect=_open_side_effect):
            req = _make_req({'vmUuid': 'vm-uuid'})
            result = plugin.take_console_screenshot(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.domain.screenshot.assert_called_once()


@pytest.mark.kvmagent
class TestOnlineIncreaseMemHandler:
    def test_online_increase_mem(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.get_memory = MagicMock(return_value=2048)
        vm_plugin.get_vm_by_uuid = MagicMock(side_effect=[mock_vm, mock_vm])

        req = _make_req({'vmUuid': 'vm-uuid', 'memorySize': 2048})
        result = plugin.online_increase_mem(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.hotplug_mem.assert_called_once_with(2048)


@pytest.mark.kvmagent
class TestOnlineIncreaseCpuHandler:
    def test_online_increase_cpu(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.get_cpu_num = MagicMock(return_value=4)
        vm_plugin.get_vm_by_uuid = MagicMock(side_effect=[mock_vm, mock_vm])

        req = _make_req({'vmUuid': 'vm-uuid', 'cpuNum': 4})
        result = plugin.online_increase_cpu(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.hotplug_cpu.assert_called_once_with(4)


@pytest.mark.kvmagent
class TestOnlineChangeCpuMemHandler:
    def test_online_change_cpumem(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.get_cpu_num = MagicMock(return_value=4)
        mock_vm.get_memory = MagicMock(return_value=4096)
        vm_plugin.get_vm_by_uuid = MagicMock(side_effect=[mock_vm, mock_vm])

        req = _make_req({'vmUuid': 'vm-uuid', 'cpuNum': 4, 'memorySize': 4096})
        result = plugin.online_change_cpumem(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.hotplug_mem.assert_called_once_with(4096)
        mock_vm.hotplug_cpu.assert_called_once_with(4)


@pytest.mark.kvmagent
class TestGetCpuXmlHandler:
    def test_get_cpu_xml(self):
        plugin = _make_vm_plugin()
        from zstacklib.utils import shell
        mock_cmd = MagicMock()
        mock_cmd.stdout = 'cpu-xml'
        mock_cmd.stderr = ''
        mock_cmd.return_code = 0
        mock_cmd.__call__ = MagicMock()
        shell.ShellCmd = MagicMock(return_value=mock_cmd)
        vm_plugin.linux.get_cpu_model = MagicMock(return_value=('x86', 'Intel'))

        req = _make_req()
        result = plugin.get_cpu_xml(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['cpuXml'] == 'cpu-xml'
        assert rsp['cpuModelName'] == 'Intel'


@pytest.mark.kvmagent
class TestCompareCpuFunctionHandler:
    def test_compare_cpu_function(self):
        plugin = _make_vm_plugin()
        from zstacklib.utils import shell
        mock_cmd = MagicMock()
        mock_cmd.stdout = 'ok'
        mock_cmd.stderr = ''
        mock_cmd.return_code = 0
        mock_cmd.__call__ = MagicMock()
        shell.ShellCmd = MagicMock(return_value=mock_cmd)
        vm_plugin.linux.write_to_temp_file = MagicMock(return_value='/tmp/cpu.xml')
        vm_plugin.linux.rm_file_force = MagicMock()

        req = _make_req({'cpuXml': '<cpu></cpu>'})
        result = plugin.compare_cpu_function(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.linux.rm_file_force.assert_called_once_with('/tmp/cpu.xml')


@pytest.mark.kvmagent
class TestMergeSnapshotToVolumeHandler:
    def test_merge_snapshot_to_volume(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.state = vm_plugin.Vm.VM_STATE_RUNNING
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        with patch('os.path.exists', return_value=False):
            req = _make_req({'vmUuid': 'vm-uuid'})
            result = plugin.merge_snapshot_to_volume(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.merge_snapshot.assert_called_once()


@pytest.mark.kvmagent
class TestBlockStreamHandler:
    def test_block_stream(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'vmUuid': 'vm-uuid', 'volume': {'installPath': '/path/vol'}})
        result = plugin.block_stream(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.block_stream_disk.assert_called_once()


@pytest.mark.kvmagent
class TestBlockCommitHandler:
    def test_block_commit(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.state = vm_plugin.Vm.VM_STATE_RUNNING
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        vm_plugin.VmPlugin._get_snapshot_size = MagicMock(return_value=123)

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'volume': {'installPath': '/path/vol'},
            'base': '/path/base',
            'topChildrenInstallPathInDb': [],
        })
        result = plugin.block_commit(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['size'] == 123
        mock_vm.do_block_commit.assert_called_once()


@pytest.mark.kvmagent
class TestBlockPullHandler:
    def test_block_pull(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.state = vm_plugin.Vm.VM_STATE_RUNNING
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        vm_plugin.get_volume_actual_installpath = MagicMock(return_value='/path/vol')
        vm_plugin.VmPlugin._get_snapshot_size = MagicMock(return_value=456)

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'volume': {'installPath': '/path/vol'},
            'base': '/path/base',
        })
        result = plugin.block_pull(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['size'] == 456
        mock_vm.block_stream_disk.assert_called_once()


@pytest.mark.kvmagent
class TestCheckRecoverHandler:
    @pytest.mark.parametrize(('state', 'expected'), [
        (vm_plugin.Vm.VM_STATE_RUNNING, 'done'),
        (vm_plugin.Vm.VM_STATE_PAUSED, 'interrupted'),
    ])
    def test_check_recover(self, state, expected):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock(state=state)
        mock_vm.domain_xmlobject.devices.get_child_node_as_list = MagicMock(return_value=[])
        vm_plugin.VM_RECOVER_TASKS = {}
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        vm_plugin.is_nbd_disk = MagicMock(return_value=False)

        req = _make_req({'vmUuid': 'vm-uuid'})
        result = plugin.check_recover(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['status'] == expected


@pytest.mark.kvmagent
class TestLoginIscsiTargetHandler:
    def test_login_iscsi_target(self):
        plugin = _make_vm_plugin()
        vm_plugin.iscsi.connect_iscsi_target = MagicMock()

        req = _make_req({'url': 'iscsi://127.0.0.1/iqn.test'})
        result = plugin.login_iscsi_target(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.iscsi.connect_iscsi_target.assert_called_once_with('iscsi://127.0.0.1/iqn.test')


@pytest.mark.kvmagent
class TestFstrimVmHandler:
    def test_fstrim_vm(self):
        plugin = _make_vm_plugin()
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))

        req = _make_req({'vmUuid': 'vm-uuid'})
        result = plugin.fstrim_vm(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestGetVmFirstBootDeviceHandler:
    def test_get_vm_first_boot_device(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.domain.XMLDesc = MagicMock(return_value='<xml/>')
        vm_plugin.get_vm_by_uuid_no_retry = MagicMock(return_value=mock_vm)
        vm_plugin.find_domain_first_boot_device = MagicMock(return_value='hd')

        req = _make_req({'uuid': 'vm-uuid'})
        result = plugin.get_vm_first_boot_device(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['firstBootDevice'] == 'hd'


@pytest.mark.kvmagent
class TestGetVmDeviceAddressHandler:
    def test_get_vm_device_address(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid_no_retry = MagicMock(return_value=mock_vm)
        vm_plugin.VmPlugin._find_volume_device_address = MagicMock(return_value=['addr1'])

        req = _make_req({'uuid': 'vm-uuid', 'deviceTOs': {'VolumeVO': [{'uuid': 'vol-uuid'}]}})
        result = plugin.get_vm_device_address(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['addresses']['VolumeVO'] == ['addr1']


@pytest.mark.kvmagent
class TestGetVirtualizerInfoHandler:
    def test_get_virtualizer_info(self):
        plugin = _make_vm_plugin()
        plugin.config = {vm_plugin.kvmagent.HOST_UUID: 'host-uuid'}
        vm_plugin.qemu.get_path = MagicMock(return_value='/usr/bin/qemu')
        vm_plugin.qemu.get_version_from_exe_file = MagicMock(return_value='6.2')
        plugin.collect_vm_virtualizer_info = MagicMock()

        req = _make_req({'vmUuids': ['vm-uuid']})
        result = plugin.get_virtualizer_info(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.collect_vm_virtualizer_info.assert_called_once()


@pytest.mark.kvmagent
class TestSetIothreadPinHandler:
    def test_set_iothread_pin(self):
        plugin = _make_vm_plugin()
        plugin.get_iothread_info = MagicMock(return_value=[])
        plugin.add_io_thread = MagicMock(return_value=None)
        plugin.pin_io_thread = MagicMock(return_value=None)

        req = _make_req({'vmUuid': 'vm-uuid', 'ioThreadId': 1, 'pin': '0-3'})
        result = plugin.set_iothread_pin(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['ioThreadId'] == 1


@pytest.mark.kvmagent
class TestDelIothreadPinHandler:
    def test_del_iothread_pin(self):
        plugin = _make_vm_plugin()
        plugin.get_iothread_info = MagicMock(return_value=[('1', '0-3')])
        plugin.del_io_thread = MagicMock(return_value=None)

        req = _make_req({'vmUuid': 'vm-uuid', 'ioThreadId': 1})
        result = plugin.del_iothread_pin(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['ioThreadId'] == 1


@pytest.mark.kvmagent
class TestSetScsiControllerHandler:
    def test_set_scsi_controller(self):
        plugin = _make_vm_plugin()
        plugin.add_scsi_controller = MagicMock(return_value=2)

        req = _make_req({'vmUuid': 'vm-uuid', 'ioThreadId': 1})
        result = plugin.set_scsi_controller(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['controllerIndex'] == '2'


@pytest.mark.kvmagent
class TestDelScsiControllerHandler:
    def test_del_scsi_controller(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        controller = MagicMock()
        controller.type_ = 'scsi'
        controller.driver.iothread_ = '1'
        controller.alias.name_ = 'scsi1'
        mock_vm.domain_xmlobject.devices.get_child_node_as_list = MagicMock(return_value=[controller])
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'vmUuid': 'vm-uuid', 'ioThreadId': 1})
        result = plugin.del_scsi_controller(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.detach_controller_by_alias.assert_called_once_with('scsi1')


@pytest.mark.kvmagent
class TestSyncVmClockNowHandler:
    def test_sync_vm_clock_now(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.state = vm_plugin.Vm.VM_STATE_RUNNING
        mock_vm.get_name = MagicMock(return_value='vm')
        mock_vm._wait_until_qemuga_ready = MagicMock()
        vm_plugin.get_vm_by_uuid_no_retry = MagicMock(return_value=mock_vm)
        vm_plugin.is_qga_connected = MagicMock(return_value=True)
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))

        req = _make_req({'vmUuid': 'vm-uuid'})
        result = plugin.sync_vm_clock_now(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestConfigSecondaryVmHandler:
    def test_config_secondary_vm(self):
        plugin = _make_vm_plugin()
        vm_plugin.execute_qmp_command = MagicMock()

        req = _make_req({'vmInstanceUuid': 'vm-uuid', 'primaryVmHostIp': '10.0.0.1', 'nbdServerPort': 1234})
        result = plugin.config_secondary_vm(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert vm_plugin.execute_qmp_command.call_count == 2


@pytest.mark.kvmagent
class TestConfigPrimaryVmHandler:
    def test_config_primary_vm(self):
        plugin = _make_vm_plugin()
        vm_plugin.ft.cleanup_vm_before_setup_colo_primary_vm = MagicMock()
        vm_plugin.qmp.execute_qmp_command = MagicMock(return_value=[])
        vm_plugin.linux.is_port_available = MagicMock(return_value=True)
        mock_vm = MagicMock()
        mock_vm.domain.XMLDesc = MagicMock(return_value='')
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({
            'vmInstanceUuid': 'vm-uuid',
            'hostIp': '10.0.0.1',
            'configs': [{
                'mirrorPort': 7000,
                'primaryInPort': 7001,
                'secondaryInPort': 7002,
                'primaryOutPort': 7003,
            }],
        })
        result = plugin.config_primary_vm(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.qmp.execute_qmp_command.assert_called()


@pytest.mark.kvmagent
class TestVmSyncHandler:
    def test_vm_sync(self):
        plugin = _make_vm_plugin()
        vm_plugin.bash.bash_r = MagicMock(return_value=0)

        def _set_states(rsp):
            rsp.states = {'vm1': vm_plugin.Vm.VM_STATE_RUNNING}

        plugin.get_vm_state_from_libvirt = MagicMock(side_effect=_set_states)
        vm_plugin.get_all_vm_states_with_process = MagicMock(return_value={'vm1': vm_plugin.Vm.VM_STATE_RUNNING})
        vm_plugin.get_vm_states_from_cache = MagicMock(return_value={})

        req = _make_req()
        result = plugin.vm_sync(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['states']['vm1'] == vm_plugin.Vm.VM_STATE_RUNNING


@pytest.mark.kvmagent
class TestVolumeSyncHandler:
    def test_volume_sync(self):
        plugin = _make_vm_plugin()
        vm_plugin.last_inactive_vol_paths = {}
        vm_plugin.bash.bash_o = MagicMock(return_value='')
        vm_plugin.glob.glob = MagicMock(return_value=[])
        vm_plugin.os.path.isdir = MagicMock(return_value=True)

        req = _make_req({'storagePaths': ['file:///tmp/vols']})
        result = plugin.volume_sync(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestRollbackQuorumConfigHandler:
    def test_rollback_quorum_config(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm._get_all_volume_alias_names = MagicMock(return_value=['drive0'])
        vm_plugin.get_vm_by_uuid_no_retry = MagicMock(return_value=mock_vm)
        vm_plugin.qmp.execute_qmp_command = MagicMock()

        with patch.object(vm_plugin, 'xrange', range, create=True):
            req = _make_req({'vmInstanceUuid': 'vm-uuid', 'volumes': [], 'nicNumber': 0})
            result = plugin.rollback_quorum_config(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.qmp.execute_qmp_command.assert_called()


@pytest.mark.kvmagent
class TestCheckMountDomainHandler:
    def test_check_mount_domain(self):
        plugin = _make_vm_plugin()
        vm_plugin.linux.is_valid_nfs_url = MagicMock(return_value=True)

        req = _make_req({'url': 'nfs://127.0.0.1:/export', 'timeout': 1000})
        result = plugin.check_mount_domain(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['active'] is True


@pytest.mark.kvmagent
class TestAttachGuestToolsIsoToVmHandler:
    def test_attach_guest_tools_iso_to_vm(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        with patch('os.path.exists', return_value=True):
            req = _make_req({'vmInstanceUuid': 'vm-uuid', 'platform': 'Linux', 'needTempDisk': False})
            result = plugin.attach_guest_tools_iso_to_vm(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.detach_iso.assert_called_once()
        mock_vm.attach_iso.assert_called_once()


@pytest.mark.kvmagent
class TestDetachGuestToolsIsoFromVmHandler:
    def test_detach_guest_tools_iso_from_vm(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.domain_xml = 'prefix-%s' % vm_plugin.GUEST_TOOLS_ISO_LINUX_PATH
        mock_vm._check_target_disk_existing_by_path = MagicMock(return_value=False)
        vm_plugin.get_vm_by_uuid_no_retry = MagicMock(return_value=mock_vm)
        vm_plugin.linux.rm_file_force = MagicMock()
        with patch('os.path.exists', return_value=False):
            req = _make_req({'vmInstanceUuid': 'vm-uuid', 'platform': 'Linux'})
            result = plugin.detach_guest_tools_iso_from_vm(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.detach_iso.assert_called_once()


@pytest.mark.kvmagent
class TestAttachPciDeviceToHostHandler:
    def test_attach_pci_device_to_host(self):
        plugin = _make_vm_plugin()
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))
        with patch('os.path.exists', return_value=False):
            req = _make_req({'pciDeviceAddress': '0000:00:01.0'})
            result = plugin.attach_pci_device_to_host(req)
            rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestDetachPciDeviceFromHostHandler:
    def test_detach_pci_device_from_host(self):
        plugin = _make_vm_plugin()
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))
        with patch('os.path.exists', return_value=False):
            req = _make_req({'pciDeviceAddress': '0000:00:01.0'})
            result = plugin.detach_pci_device_from_host(req)
            rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestMigrateDomainXml:
    def test_split_legacy_rbd_cdrom_snapshot(self):
        domain_xml = """
<domain type='kvm'>
  <name>vm-uuid</name>
  <devices>
    <disk type='network' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source protocol='rbd' name='pool/image@snapshot'>
        <host name='172.24.1.1' port='6789'/>
      </source>
      <target dev='hdc' bus='ide'/>
      <readonly/>
    </disk>
  </devices>
</domain>
"""
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.get_migratable_xml = MagicMock(return_value=domain_xml)

        disks, dest_xml = vm._build_domain_new_xml({})

        assert disks == []
        root = ET.fromstring(dest_xml)
        source = root.find("devices/disk/source")
        assert source.attrib["name"] == "pool/image"
        assert source.find("snapshot").attrib["name"] == "snapshot"

    def test_split_legacy_rbd_data_disk_snapshot(self):
        domain_xml = """
<domain type='kvm'>
  <name>vm-uuid</name>
  <devices>
    <disk type='network' device='disk'>
      <driver name='qemu' type='raw'/>
      <source protocol='rbd' name='pool/image@snapshot'>
        <host name='172.24.1.1' port='6789'/>
      </source>
      <target dev='vda' bus='virtio'/>
    </disk>
  </devices>
</domain>
"""
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.get_migratable_xml = MagicMock(return_value=domain_xml)

        disks, dest_xml = vm._build_domain_new_xml({})

        assert disks == []
        root = ET.fromstring(dest_xml)
        source = root.find("devices/disk/source")
        assert source.attrib["name"] == "pool/image"
        assert source.find("snapshot").attrib["name"] == "snapshot"

    def test_keeps_existing_rbd_cdrom_snapshot(self):
        domain_xml = """
<domain type='kvm'>
  <name>vm-uuid</name>
  <devices>
    <disk type='network' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source protocol='rbd' name='pool/image@legacy-snapshot'>
        <host name='172.24.1.1' port='6789'/>
        <snapshot name='existing-snapshot'/>
      </source>
      <target dev='hdc' bus='ide'/>
      <readonly/>
    </disk>
  </devices>
</domain>
"""
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.get_migratable_xml = MagicMock(return_value=domain_xml)

        _, dest_xml = vm._build_domain_new_xml({})

        root = ET.fromstring(dest_xml)
        source = root.find("devices/disk/source")
        assert source.attrib["name"] == "pool/image"
        assert source.find("snapshot").attrib["name"] == "existing-snapshot"
        assert len(source.findall("snapshot")) == 1

    def test_does_not_split_rbd_data_disk_without_snapshot(self):
        domain_xml = """
<domain type='kvm'>
  <name>vm-uuid</name>
  <devices>
    <disk type='network' device='disk'>
      <driver name='qemu' type='raw'/>
      <source protocol='rbd' name='pool/image'>
        <host name='172.24.1.1' port='6789'/>
      </source>
      <target dev='vda' bus='virtio'/>
    </disk>
  </devices>
</domain>
"""
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.get_migratable_xml = MagicMock(return_value=domain_xml)

        disks, dest_xml = vm._build_domain_new_xml({})

        assert disks is None
        assert dest_xml is None

    def test_splits_snapshot_when_replacing_migration_disk(self):
        domain_xml = """
<domain type='kvm'>
  <name>vm-uuid</name>
  <devices>
    <disk type='network' device='cdrom'>
      <driver name='qemu' type='raw'/>
      <source protocol='rbd' name='pool/iso@snapshot'>
        <host name='172.24.1.1' port='6789'/>
      </source>
      <target dev='hdc' bus='ide'/>
      <readonly/>
    </disk>
    <disk type='network' device='disk'>
      <driver name='qemu' type='raw'/>
      <source protocol='rbd' name='pool/data-image'>
        <host name='172.24.1.1' port='6789'/>
      </source>
      <target dev='vda' bus='virtio'/>
    </disk>
  </devices>
</domain>
"""
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.get_migratable_xml = MagicMock(return_value=domain_xml)
        vm._get_target_disk_by_path = MagicMock(return_value=(None, "vda"))
        volume = jsonobject.loads(json.dumps({
            "deviceType": "ceph",
            "installPath": "ceph://pool/replaced-data-image",
            "useVirtioSCSI": False,
            "useVirtio": True,
            "shareable": False,
            "secretUuid": None,
            "monInfo": [],
            "physicalBlockSize": None,
            "format": "raw",
            "backing_store": None,
        }))

        disks, dest_xml = vm._build_domain_new_xml({"ceph://pool/data-image": volume})

        assert disks == ["vda"]
        root = ET.fromstring(dest_xml)
        sources = root.findall("devices/disk/source")
        cdrom_source = sources[0]
        disk_source = sources[1]
        assert cdrom_source.attrib["name"] == "pool/iso"
        assert cdrom_source.find("snapshot").attrib["name"] == "snapshot"
        assert disk_source.attrib["name"] == "pool/replaced-data-image"

    def test_does_not_split_non_rbd_network_disk_snapshot(self):
        domain_xml = """
<domain type='kvm'>
  <name>vm-uuid</name>
  <devices>
    <disk type='network' device='disk'>
      <driver name='qemu' type='raw'/>
      <source protocol='cbd' name='pool/image@snapshot'>
        <host name='172.24.1.1' port='7777'/>
      </source>
      <target dev='vda' bus='virtio'/>
    </disk>
  </devices>
</domain>
"""
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.get_migratable_xml = MagicMock(return_value=domain_xml)

        disks, dest_xml = vm._build_domain_new_xml({})

        assert disks is None
        assert dest_xml is None


@pytest.mark.kvmagent
class TestBlockMigrateHandler:
    def test_block_migrate(self):
        plugin = _make_vm_plugin()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=MagicMock())
        plugin._record_operation = MagicMock()
        plugin._build_dest_disk_xml = MagicMock(return_value=('vda', '/tmp/disk.xml'))
        plugin._do_block_copy = MagicMock(return_value=(True, None))
        vm_plugin.os.remove = MagicMock()

        req = _make_req({'vmUuid': 'vm-uuid', 'oldVolumePath': '/path/old', 'newVolume': {}})
        result = plugin.block_migrate(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin._record_operation.assert_called_once()
        vm_plugin.os.remove.assert_called_once_with('/tmp/disk.xml')


@pytest.mark.kvmagent
class TestCancelBackupJobsHandler:
    def test_cancel_backup_jobs(self):
        plugin = _make_vm_plugin()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=MagicMock())
        plugin.do_cancel_vm_backup_jobs = MagicMock()

        req = _make_req({'vmUuid': 'vm-uuid', 'force': False})
        result = plugin.cancel_backup_jobs(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.do_cancel_vm_backup_jobs.assert_called_once()


@pytest.mark.kvmagent
class TestCancelBackupJobHandler:
    def test_cancel_backup_job(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm._get_target_disk = MagicMock(return_value=(MagicMock(), None))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        plugin.get_disk_device_name = MagicMock(return_value='drive-0')
        plugin.do_cancel_volume_backup_job = MagicMock()

        req = _make_req({'vmUuid': 'vm-uuid', 'volume': {'volumeUuid': 'vol-uuid'}, 'force': False})
        result = plugin.cancel_backup_job(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.do_cancel_volume_backup_job.assert_called_once()


@pytest.mark.kvmagent
class TestCancelVolumeCbtBackupHandler:
    def test_cancel_volume_cbt_backup(self):
        plugin = _make_vm_plugin()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=MagicMock())
        client = MagicMock()
        client.stop_vm_cbt_backup_jobs = MagicMock()
        vm_plugin.ImageStoreClient = MagicMock(return_value=client)

        req = _make_req({'vmUuid': 'vm-uuid', 'records': []})
        result = plugin.cancel_volume_cbt_backup(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        client.stop_vm_cbt_backup_jobs.assert_called_once_with('vm-uuid', [])

    def test_rollback_volume_cbt_backup(self):
        plugin = _make_vm_plugin()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=MagicMock())
        client = MagicMock()
        vm_plugin.ImageStoreClient = MagicMock(return_value=client)

        records = [{
            'scratchNodeName': 'source-scratch', 'target': '/tmp/scratch.qcow2',
            'lastBitmapName': 'previous-bitmap', 'bitmapName': 'new-bitmap',
        }]
        req = _make_req({'vmUuid': 'vm-uuid', 'records': records})
        result = plugin.rollback_volume_cbt_backup(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        client.rollback_vm_cbt_backup_jobs.assert_called_once()
        rollback_records = client.rollback_vm_cbt_backup_jobs.call_args.args[1]
        assert rollback_records[0].lastBitmapName == 'previous-bitmap'
        assert rollback_records[0].bitmapName == 'new-bitmap'
        client.stop_vm_cbt_backup_jobs.assert_not_called()

    def test_rollback_volume_cbt_backup_reports_cleanup_failure(self):
        plugin = _make_vm_plugin()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=MagicMock())
        client = MagicMock()
        client.rollback_vm_cbt_backup_jobs.side_effect = RuntimeError('rollback failed')
        vm_plugin.ImageStoreClient = MagicMock(return_value=client)

        req = _make_req({'vmUuid': 'vm-uuid', 'records': []})
        result = plugin.rollback_volume_cbt_backup(req)
        rsp = json.loads(result)

        assert rsp['success'] is False
        assert 'rollback failed' in rsp['error']


@pytest.mark.kvmagent
class TestCancelVolumeMirrorHandler:
    def test_cancel_volume_mirror(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm._get_target_disk = MagicMock(return_value=(MagicMock(), None))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        plugin.get_disk_device_name = MagicMock(return_value='drive-0')
        client = MagicMock()
        client.stop_mirror = MagicMock()
        vm_plugin.ImageStoreClient = MagicMock(return_value=client)

        req = _make_req({'vmUuid': 'vm-uuid', 'volume': {}, 'complete': False, 'force': False})
        result = plugin.cancel_volume_mirror(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        client.stop_mirror.assert_called_once()


@pytest.mark.kvmagent
class TestCheckColoVmStateHandler:
    def test_check_colo_vm_state(self):
        plugin = _make_vm_plugin()
        vm_plugin.get_all_vm_states = MagicMock(return_value={'vm-uuid': vm_plugin.Vm.VM_STATE_RUNNING})

        req = _make_req({'vmInstanceUuid': 'vm-uuid'})
        result = plugin.check_colo_vm_state(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['state'] == vm_plugin.Vm.VM_STATE_RUNNING


@pytest.mark.kvmagent
class TestCheckVolumeSnapshotHandler:
    def test_check_volume_snapshot(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.state = vm_plugin.Vm.VM_STATE_RUNNING
        mock_vm.VM_STATE_RUNNING = vm_plugin.Vm.VM_STATE_RUNNING
        mock_vm.VM_STATE_SHUTDOWN = vm_plugin.Vm.VM_STATE_SHUTDOWN
        mock_vm.VM_STATE_PAUSED = vm_plugin.Vm.VM_STATE_PAUSED
        mock_vm._get_target_disk_by_path = MagicMock(return_value=(MagicMock(), 'vda'))
        mock_vm._get_backfile_chain = MagicMock(return_value=[])
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        vm_plugin.difflib.context_diff = MagicMock(return_value=[])
        mock_vm.domain_xmlobject.devices.get_child_node_as_list = MagicMock(return_value=[])

        cmd = MagicMock(
            vmUuid='vm-uuid',
            volumeUuid='vol-uuid',
            currentInstallPath='/path1',
            volumeChainToCheck={'/path1': 1},
            volume=MagicMock(deviceId=0),
            excludeInstallPaths=None,
        )
        from builtins import map as builtin_map
        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd), \
                patch('builtins.map', side_effect=lambda *args, **kwargs: list(builtin_map(*args, **kwargs))):
            req = _make_req({})
            result = plugin.check_volume_snapshot(req)
            rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestDetachVirtioDriverHandler:
    def test_detach_virtio_driver(self):
        plugin = _make_vm_plugin()
        plugin.eject_floppy = MagicMock()

        req = _make_req({'vmInstanceUuid': 'vm-uuid', 'driverFormat': 'VFD'})
        result = plugin.detach_virtio_driver(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.eject_floppy.assert_called_once()


@pytest.mark.kvmagent
class TestExportNbdVolumesHandler:
    def test_export_nbd_volumes(self):
        plugin = _make_vm_plugin()
        vm_plugin.linux.parse_port_range = MagicMock(return_value=(6000, 6001))
        lock = MagicMock()
        vm_plugin.linux.find_free_port_with_locking = MagicMock(return_value=(6000, lock))
        plugin.get_cbt_volume_actual_install_path = MagicMock(return_value='/path/vol')
        plugin.active_volume_chain_if_need = MagicMock()
        vm_plugin.qemu_nbd.export = MagicMock(return_value=MagicMock())
        vm_plugin.linux.check_socket_available = MagicMock(return_value=True)

        req = _make_req({
            'portRange': '6000-6001',
            'volumeInfos': [{'volume': {'format': 'qcow2', 'installPath': '/path/vol', 'volumeUuid': 'vol-uuid'}}],
        })
        result = plugin.export_nbd_volumes(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert len(rsp['volumeInfos']) == 1

    def test_export_nbd_volumes_uses_configured_cbd_path(self):
        plugin = _make_vm_plugin()
        cbd_path = 'cbd:pool_physical/pool/volume'
        configured_path = cbd_path + '_zbs_:/etc/zbs/client.conf'
        vm_plugin.linux.parse_port_range = MagicMock(return_value=(6000, 6001))
        lock = MagicMock()
        vm_plugin.linux.find_free_port_with_locking = MagicMock(return_value=(6000, lock))
        plugin.active_volume_chain_if_need = MagicMock()
        vm_plugin.qemu_nbd.export = MagicMock(return_value=MagicMock())
        vm_plugin.linux.check_socket_available = MagicMock(return_value=True)

        with patch.object(vm_plugin, 'get_volume_actual_installpath', return_value=configured_path):
            req = _make_req({
                'portRange': '6000-6001',
                'volumeInfos': [{'volume': {'format': 'qcow2', 'installPath': cbd_path, 'volumeUuid': 'vol-uuid'}}],
            })
            result = plugin.export_nbd_volumes(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.active_volume_chain_if_need.assert_called_once_with(configured_path)
        vm_plugin.qemu_nbd.export.assert_called_once_with(
            6000, '-b', '0.0.0.0', '-f', 'qcow2', configured_path, '-x', 'vol-uuid'
        )


@pytest.mark.kvmagent
class TestFailColoPvmHandler:
    def test_fail_colo_pvm(self):
        plugin = _make_vm_plugin()
        vm_plugin.linux.sshpass_run = MagicMock(return_value=(0, '', ''))

        req = _make_req({
            'vmInstanceUuid': 'vm-uuid',
            'targetHostIp': '10.0.0.1',
            'targetHostPassword': 'password',
            'targetHostPort': 22,
        })
        result = plugin.fail_colo_pvm(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestGetVmGuestToolsInfoHandler:
    def test_get_vm_guest_tools_info(self):
        plugin = _make_vm_plugin()
        plugin.get_linux_vm_guest_tools_info = MagicMock(return_value=(vm_plugin.VmPlugin.GUESTTOOLS_STATE_RUNNING, '1.0'))

        req = _make_req({'vmInstanceUuid': 'vm-uuid', 'platform': 'linux'})
        result = plugin.get_vm_guest_tools_info(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestGetVmMetricsRoutingStatusHandler:
    def test_get_vm_metrics_routing_status(self):
        plugin = _make_vm_plugin()
        plugin.get_lighttpd_status_for_vm = MagicMock()
        plugin.get_push_gateway_routing_for_vm = MagicMock()

        cmd = MagicMock(vmInstanceUuid='vm-uuid', items=['lighttpd', 'pushgateway'])
        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
            req = _make_req({})
            result = plugin.get_vm_metrics_routing_status(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.get_lighttpd_status_for_vm.assert_called_once()
        plugin.get_push_gateway_routing_for_vm.assert_called_once()


@pytest.mark.kvmagent
class TestGetVolumeMirrorModeHandler:
    def test_get_volume_mirror_mode(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm._get_target_disk = MagicMock(return_value=(MagicMock(), None))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        plugin.get_disk_device_name = MagicMock(return_value='drive-0')
        client = MagicMock()
        client.get_mirror_mode = MagicMock(return_value='full')
        vm_plugin.ImageStoreClient = MagicMock(return_value=client)

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'volume': {'installPath': '/path/vol'},
            'lastMirrorVolume': 'last',
        })
        result = plugin.get_volume_mirror_mode(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['mode'] == 'full'


@pytest.mark.kvmagent
class TestGetVolumesCbtBitmapsHandler:
    def test_get_incremental_volume_cbt_bitmap_uses_dirty_bitmap_context(self):
        plugin = _make_vm_plugin()
        cmd = MagicMock()
        volume_info = MagicMock()
        volume_info.mode = 'incremental'
        volume_info.scratchNodeName = 'node'
        volume_info.nbdServer = '127.0.0.1'
        volume_info.nbdPort = 10809
        cmd.bitmapTimestamp = 'ts'
        cmd.volumeInfos = [volume_info]
        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd), \
                patch.object(vm_plugin.qemu, 'get_data_bitmap', return_value={0: 1}) as get_bitmap, \
                patch.object(vm_plugin.qemu, 'compress_and_encode_bitmap', return_value='encoded'):
            req = _make_req({})
            result = plugin.get_volumes_cbt_bitmaps(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        assert len(rsp['volumeInfos']) == 1
        get_bitmap.assert_called_once_with(
            'driver=nbd,export=node,server.type=inet,server.host=127.0.0.1,server.port=10809,'
            'x-dirty-bitmap=qemu:dirty-bitmap:ts',
            vm_plugin.MAX_NBD_READ_SIZE,
            False,
            False,
            '--image-opts',
        )

    def test_get_full_zbs_bitmap_unions_source_diff_and_scratch_qcow2(self):
        plugin = _make_vm_plugin()
        cmd = MagicMock(bitmapTimestamp='ts')
        volume_info = MagicMock(mode='full', target='cbd:physical/logical/scratch')
        volume_info.volume = MagicMock(
            primaryStorageType='Addon',
            installPath='cbd:physical/logical/volume',
        )
        cmd.volumeInfos = [volume_info]

        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd), \
                patch.object(
                    vm_plugin,
                    'get_volume_actual_installpath',
                    return_value='cbd:physical/logical/scratch_zbs_:/etc/zbs/client.conf',
                ), \
                patch.object(vm_plugin.zbs_storage_plugin, 'query_allocated_extents', return_value={0: 65536}) as get_zbs, \
                patch.object(vm_plugin.qemu, 'get_data_bitmap', return_value={32768: 65536}) as get_scratch, \
                patch.object(vm_plugin.qemu, 'merge_data_bitmaps', return_value={0: 98304}) as merge, \
                patch.object(vm_plugin.qemu, 'compress_and_encode_bitmap', return_value='encoded') as encode:
            result = plugin.get_volumes_cbt_bitmaps(_make_req({}))
            rsp = json.loads(result)

        assert rsp['success'] is True
        get_zbs.assert_called_once_with('logical/volume')
        get_scratch.assert_called_once_with(
            'cbd:physical/logical/scratch_zbs_:/etc/zbs/client.conf',
            vm_plugin.MAX_NBD_READ_SIZE,
            False,
            True,
            '-f qcow2',
        )
        merge.assert_called_once_with(
            [{0: 65536}, {32768: 65536}], vm_plugin.MAX_NBD_READ_SIZE)
        encode.assert_called_once_with({0: 98304})

    def test_get_full_zbs_bitmap_propagates_clone_diff_business_error(self):
        plugin = _make_vm_plugin()
        cmd = MagicMock(bitmapTimestamp='ts')
        volume_info = MagicMock(mode='full', target='cbd:physical/logical/scratch')
        volume_info.volume = MagicMock(
            primaryStorageType='Addon',
            installPath='cbd:physical/logical/clone-root',
        )
        cmd.volumeInfos = [volume_info]

        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd), \
                patch.object(
                    vm_plugin.zbs_storage_plugin,
                    'query_allocated_extents',
                    side_effect=RuntimeError('file is not a regular volume'),
                ), \
                patch.object(vm_plugin.qemu, 'get_data_bitmap') as get_scratch:
            result = plugin.get_volumes_cbt_bitmaps(_make_req({}))
            rsp = json.loads(result)

        assert rsp['success'] is False
        assert 'file is not a regular volume' in rsp['error']
        assert rsp['volumeInfos'] == []
        get_scratch.assert_not_called()


@pytest.mark.kvmagent
class TestHotPlugMdevDeviceHandler:
    def test_hot_plug_mdev_device(self):
        plugin = _make_vm_plugin()
        vm_plugin.linux.write_to_temp_file = MagicMock(return_value='/tmp/mdev.xml')
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        vm_plugin.pci.get_mdev_passthrough_mapping = MagicMock(return_value={'11111111-1111-1111-1111-111111111111': 'mdev-addr'})

        with patch.object(vm_plugin.uuid, 'UUID', side_effect=lambda value: value):
            req = _make_req({'vmUuid': 'vm-uuid', 'MdevDeviceUuid': '11111111-1111-1111-1111-111111111111'})
            result = plugin.hot_plug_mdev_device(req)
            rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestHotPlugPciDeviceHandler:
    def test_hot_plug_pci_device(self):
        plugin = _make_vm_plugin()
        plugin.timeout_object = MagicMock()
        vm_plugin.linux.write_to_temp_file = MagicMock(return_value='/tmp/pci.xml')
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        vm_plugin.pci.get_vm_pci_device_address_by_host_address = MagicMock(return_value='0000:00:00.0')

        req = _make_req({'vmUuid': 'vm-uuid', 'pciDeviceAddress': '0000:00:01.0'})
        result = plugin.hot_plug_pci_device(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['vmPciDeviceAddress'] == '0000:00:00.0'


@pytest.mark.kvmagent
class TestHotUnplugMdevDeviceHandler:
    def test_hot_unplug_mdev_device(self):
        plugin = _make_vm_plugin()
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))
        vm_plugin.linux.wait_callback_success = MagicMock(return_value=True)
        vm_plugin.linux.write_to_temp_file = MagicMock(return_value='/tmp/mdev.xml')

        with patch.object(vm_plugin.uuid, 'UUID', side_effect=lambda value: value):
            req = _make_req({'vmUuid': 'vm-uuid', 'MdevDeviceUuid': '11111111-1111-1111-1111-111111111111'})
            result = plugin.hot_unplug_mdev_device(req)
            rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestHotUnplugPciDeviceHandler:
    def test_hot_unplug_pci_device(self):
        plugin = _make_vm_plugin()
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=MagicMock())

        req = _make_req({'vmUuid': 'vm-uuid', 'pciDeviceAddress': '0000:00:01.0'})
        result = plugin.hot_unplug_pci_device(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestKvmAttachUsbDeviceHandler:
    def test_kvm_attach_usb_device(self):
        plugin = _make_vm_plugin()
        plugin._attach_usb_by_libvirt = MagicMock(return_value=(True, None))

        req = _make_req({'vmUuid': 'vm-uuid', 'attachType': 'PassThrough'})
        result = plugin.kvm_attach_usb_device(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestKvmDetachUsbDeviceHandler:
    def test_kvm_detach_usb_device(self):
        plugin = _make_vm_plugin()
        plugin._detach_usb_by_libvirt = MagicMock()

        req = _make_req({'vmUuid': 'vm-uuid', 'attachType': 'PassThrough'})
        result = plugin.kvm_detach_usb_device(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestListExportedVolumesHandler:
    def test_list_exported_volumes(self):
        plugin = _make_vm_plugin()
        volume_one = MagicMock(volumeUuid='vol-1', installPath='/path/vol1')
        volume_two = MagicMock(volumeUuid='vol-2', installPath='/path/vol2')
        cmd = MagicMock(volumes=[volume_one, volume_two])
        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
            with patch.object(vm_plugin.qemu_nbd, 'find_qemu_nbd_process', side_effect=[0, 1]) as find:
                req = _make_req({})
                result = plugin.list_exported_volumes(req)
                rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['volumeExportInfos']['vol-1'] is True
        assert rsp['volumeExportInfos']['vol-2'] is False
        assert [call.args[0] for call in find.call_args_list] == ['/path/vol1', '/path/vol2']

    def test_list_exported_volumes_checks_converted_real_path(self):
        plugin = _make_vm_plugin()
        volume = MagicMock(volumeUuid='vol-1', installPath='sharedblock://vg/vol')
        cmd = MagicMock(volumes=[volume])

        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
            with patch.object(vm_plugin.qemu_nbd, 'find_qemu_nbd_process', return_value=0) as find:
                req = _make_req({})
                result = plugin.list_exported_volumes(req)
                rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['volumeExportInfos']['vol-1'] is True
        find.assert_called_once_with('/dev/vg/vol')

    def test_list_exported_volumes_falls_back_to_install_path(self):
        plugin = _make_vm_plugin()
        volume = MagicMock(volumeUuid='vol-1', installPath='sharedblock://vg/vol')
        cmd = MagicMock(volumes=[volume])

        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
            with patch.object(vm_plugin.qemu_nbd, 'find_qemu_nbd_process', side_effect=[1, 0]) as find:
                req = _make_req({})
                result = plugin.list_exported_volumes(req)
                rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['volumeExportInfos']['vol-1'] is True
        assert [call.args[0] for call in find.call_args_list] == ['/dev/vg/vol', 'sharedblock://vg/vol']

    def test_list_exported_volumes_uses_configured_cbd_path(self):
        plugin = _make_vm_plugin()
        cbd_path = 'cbd:pool_physical/pool/volume'
        configured_path = cbd_path + '_zbs_:/etc/zbs/client.conf'
        volume = MagicMock(volumeUuid='vol-1', installPath=cbd_path)
        cmd = MagicMock(volumes=[volume])

        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd), \
                patch.object(vm_plugin, 'get_volume_actual_installpath', return_value=configured_path):
            with patch.object(vm_plugin.qemu_nbd, 'find_qemu_nbd_process', return_value=0) as find:
                result = plugin.list_exported_volumes(_make_req({}))
                rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['volumeExportInfos']['vol-1'] is True
        find.assert_called_once_with(configured_path)


@pytest.mark.kvmagent
class TestMigrateVmHandler:
    def test_migrate_vm(self):
        plugin = _make_vm_plugin()
        plugin._record_operation = MagicMock()
        mock_vm = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        cmd = MagicMock(vmUuid='vm-uuid', reload=False, migrateFromDestination=False)
        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
            req = _make_req({})
            result = plugin.migrate_vm(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        mock_vm.migrate.assert_called_once()


@pytest.mark.kvmagent
class TestQueryVmMirrorLatenciesBoundaryHandler:
    def test_query_vm_mirror_latencies_boundary(self):
        plugin = _make_vm_plugin()
        thread_obj = MagicMock()
        thread_obj.getResult = MagicMock(return_value=('vm-uuid', {'max': 1}, {'min': 2}))
        vm_plugin.QueryVmLatenciesThread = MagicMock(return_value=thread_obj)

        req = _make_req({'vmUuids': ['vm-uuid'], 'times': [1]})
        result = plugin.query_vm_mirror_latencies_boundary(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestQueryVolumeMirrorHandler:
    def test_query_volume_mirror(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        target_disk = MagicMock()
        target_disk.alias.name_ = 'virtio-disk0'
        mock_vm._get_target_disk = MagicMock(return_value=(target_disk, None))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        plugin.get_disk_device_name = MagicMock(return_value='drive-virtio-disk0')
        vm_plugin.get_block_node_name_by_disk_name = MagicMock(return_value='node-0')
        client = MagicMock()
        client.query_mirror_volumes = MagicMock(return_value={'drive-virtio-disk0': True})
        vm_plugin.ImageStoreClient = MagicMock(return_value=client)

        volume = MagicMock(volumeUuid='vol-uuid')
        cmd = MagicMock(vmUuid='vm-uuid', volumes=[volume], stopExtra=False)
        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
            req = _make_req({})
            result = plugin.query_volume_mirror(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['mirrorVolumes'] == ['vol-uuid']


@pytest.mark.kvmagent
class TestRecoverVolumesHandler:
    def test_recover_volumes(self):
        plugin = _make_vm_plugin()
        events = []
        vm_plugin.VM_RECOVER_DICT = {'vm-uuid': MagicMock()}
        vm_plugin.VM_RECOVER_TASKS = {}
        vm_plugin.parse_url = MagicMock(return_value=MagicMock(scheme=None))
        task = MagicMock()
        task.__enter__.return_value = task
        task.__exit__.return_value = None
        task.recover_vm_volumes = MagicMock(side_effect=lambda: events.append('recover'))
        vm_plugin.VmVolumesRecoveryTask = MagicMock(return_value=task)
        mock_vm = MagicMock()
        mock_vm.pause.side_effect = lambda: events.append('pause')
        mock_vm.resume.side_effect = lambda: events.append('resume')
        vm_plugin.linux.wait_callback_success = MagicMock(
            side_effect=lambda *_args, **_kwargs: events.append('check') or True)
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        req = _make_req({'vmUuid': 'vm-uuid', 'volumes': [{'installPath': '/path/vol'}]})
        result = plugin.recover_volumes(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert events == ['pause', 'recover', 'check', 'resume']


@pytest.mark.kvmagent
class TestRegisterPrimaryVmHeartbeatHandler:
    def test_register_primary_vm_heartbeat(self):
        plugin = _make_vm_plugin()
        plugin.vm_heartbeat = {}
        thread_obj = MagicMock()
        thread_obj.is_alive = MagicMock(return_value=True)
        vm_plugin.thread = MagicMock()
        vm_plugin.thread.ThreadFacade.run_in_thread = MagicMock(return_value=thread_obj)

        with patch('socket.socket') as mock_socket:
            sock = MagicMock()
            mock_socket.return_value = sock
            req = _make_req({'vmInstanceUuid': 'vm-uuid', 'targetHostIp': '10.0.0.1', 'heartbeatPort': 1234})
            result = plugin.register_primary_vm_heartbeat(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.thread.ThreadFacade.run_in_thread.assert_called_once()


@pytest.mark.kvmagent
class TestReloadRedirectUsbHandler:
    def test_reload_redirect_usb(self):
        plugin = _make_vm_plugin()
        plugin._detach_usb_by_libvirt = MagicMock()
        plugin._attach_usb_by_libvirt = MagicMock(return_value=(True, None))

        req = _make_req({'vmUuid': 'vm-uuid', 'attachType': 'Redirect', 'usbVersion': '2.0'})
        result = plugin.reload_redirect_usb(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin._detach_usb_by_libvirt.assert_called_once()
        plugin._attach_usb_by_libvirt.assert_called_once()


@pytest.mark.kvmagent
class TestVmShmemHotplugHandlers:
    def test_build_vm_shmem_xml_validates_size(self):
        plugin = _make_vm_plugin()

        xml, mem_path, shmem_name, shmem_size_mb = plugin._build_vm_shmem_xml({
            'path': '/dev/shm/tf_vm-uuid',
            'size': 2 * 1024 * 1024,
        })

        root = ET.fromstring(xml)
        assert root.tag == 'shmem'
        assert root.get('name') == 'tf_vm-uuid'
        assert root.find('model').get('type') == 'ivshmem-plain'
        assert root.find('size').text == '2'
        assert root.find('size').get('unit') == 'M'
        assert mem_path == '/dev/shm/tf_vm-uuid'
        assert shmem_name == 'tf_vm-uuid'
        assert shmem_size_mb == 2

    def test_build_vm_shmem_xml_keeps_management_node_size(self):
        plugin = _make_vm_plugin()

        xml, _, _, shmem_size_mb = plugin._build_vm_shmem_xml({
            'path': '/dev/shm/tf_vm-uuid',
            'size': 3 * 1024 * 1024,
        })

        root = ET.fromstring(xml)
        assert root.find('size').text == '3'
        assert root.find('size').get('unit') == 'M'
        assert shmem_size_mb == 3

    def test_is_vm_shmem_attached_requires_matching_size(self):
        plugin = _make_vm_plugin()
        vm = MagicMock()
        vm.domain.XMLDesc = MagicMock(return_value=(
            '<domain><devices>'
            '<shmem name="tf_vm-uuid"><size unit="M">1</size></shmem>'
            '<shmem name="tf_vm-uuid"><size unit="M">2</size></shmem>'
            '</devices></domain>'
        ))

        assert plugin._is_vm_shmem_attached(vm, 'tf_vm-uuid', 2) is True
        assert plugin._is_vm_shmem_attached(vm, 'tf_vm-uuid', 4) is False

    @pytest.mark.parametrize('size, expected', [
        (1024 * 1024, 1),
        (3 * 1024 * 1024, 3),
        (5 * 1024 * 1024, 5),
    ])
    def test_get_shmem_size_mb(self, size, expected):
        assert vm_plugin._get_shmem_size_mb(size) == expected

    @pytest.mark.parametrize('size', [
        1,
        1024 * 1024 + 1,
    ])
    def test_get_shmem_size_mb_rejects_unaligned_size(self, size):
        with pytest.raises(vm_plugin.kvmagent.KvmError):
            vm_plugin._get_shmem_size_mb(size)

    @pytest.mark.parametrize('path', [
        '/tmp/tf_vm-uuid',
        '/dev/shm/../tf_vm-uuid',
        '/dev/shm/tf.vm',
    ])
    def test_build_vm_shmem_xml_rejects_invalid_path(self, path):
        plugin = _make_vm_plugin()

        with pytest.raises(vm_plugin.kvmagent.KvmError):
            plugin._build_vm_shmem_xml({'path': path, 'size': 1024 * 1024})

    def test_hot_plug_vm_shmem_attaches_live_device(self, monkeypatch):
        plugin = _make_vm_plugin()
        vm = MagicMock()
        vm.domain.XMLDesc = MagicMock(return_value='<domain><devices></devices></domain>')
        vm.domain.attachDeviceFlags = MagicMock()
        wait_callback_success = MagicMock(return_value=True)
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', MagicMock(return_value=vm))
        monkeypatch.setattr(vm_plugin.linux, 'wait_callback_success', wait_callback_success)

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'shmem': {'path': '/dev/shm/tf_vm-uuid', 'size': 2 * 1024 * 1024},
        })

        result = plugin.hot_plug_vm_shmem(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm._wait_vm_run_until_seconds.assert_called_once_with(60)
        vm.domain.attachDeviceFlags.assert_called_once()
        xml_arg, flags_arg = vm.domain.attachDeviceFlags.call_args[0]
        assert ET.fromstring(xml_arg).get('name') == 'tf_vm-uuid'
        assert flags_arg == vm_plugin.libvirt.VIR_DOMAIN_AFFECT_LIVE
        wait_callback_success.assert_called_once()
        assert wait_callback_success.call_args[1]['ignore_exception_in_callback'] is True

    def test_hot_plug_vm_shmem_fails_when_device_does_not_appear(self, monkeypatch):
        plugin = _make_vm_plugin()
        vm = MagicMock()
        vm.domain.XMLDesc = MagicMock(return_value='<domain><devices></devices></domain>')
        vm.domain.attachDeviceFlags = MagicMock()
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', MagicMock(return_value=vm))
        monkeypatch.setattr(vm_plugin.linux, 'wait_callback_success', MagicMock(return_value=False))

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'shmem': {'path': '/dev/shm/tf_vm-uuid', 'size': 2 * 1024 * 1024},
        })

        result = plugin.hot_plug_vm_shmem(req)
        rsp = json.loads(result)

        assert rsp['success'] is False
        assert 'still not attached' in rsp['error']

    def test_hot_unplug_vm_shmem_waits_for_detach_before_cleanup(self, monkeypatch):
        plugin = _make_vm_plugin()
        vm = MagicMock(state=vm_plugin.Vm.VM_STATE_RUNNING)
        vm.domain.XMLDesc = MagicMock(return_value=(
            '<domain><devices><shmem name="tf_vm-uuid"><size unit="M">2</size></shmem></devices></domain>'
        ))
        vm.domain.detachDeviceFlags = MagicMock()
        wait_callback_success = MagicMock(return_value=True)
        rm_file_force = MagicMock()
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', MagicMock(return_value=vm))
        monkeypatch.setattr(vm_plugin.linux, 'wait_callback_success', wait_callback_success)
        monkeypatch.setattr(vm_plugin.linux, 'rm_file_force', rm_file_force)

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'shmem': {'path': '/dev/shm/tf_vm-uuid', 'size': 2 * 1024 * 1024},
        })

        result = plugin.hot_unplug_vm_shmem(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm.domain.detachDeviceFlags.assert_called_once()
        xml_arg, flags_arg = vm.domain.detachDeviceFlags.call_args[0]
        assert ET.fromstring(xml_arg).get('name') == 'tf_vm-uuid'
        assert flags_arg == vm_plugin.libvirt.VIR_DOMAIN_AFFECT_LIVE
        wait_callback_success.assert_called_once()
        assert wait_callback_success.call_args[1]['ignore_exception_in_callback'] is True
        rm_file_force.assert_called_once_with('/dev/shm/tf_vm-uuid')

    def test_hot_unplug_vm_shmem_fails_without_cleanup_when_vm_runtime_state_unknown(self, monkeypatch):
        plugin = _make_vm_plugin()
        vm = MagicMock(state=vm_plugin.Vm.VM_STATE_RUNNING)
        vm._wait_vm_run_until_seconds = MagicMock(side_effect=vm_plugin.kvmagent.KvmError('pid not ready'))
        vm.domain.XMLDesc = MagicMock(return_value=(
            '<domain><devices><shmem name="tf_vm-uuid"><size unit="M">2</size></shmem></devices></domain>'
        ))
        vm.domain.detachDeviceFlags = MagicMock()
        rm_file_force = MagicMock()
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', MagicMock(return_value=vm))
        monkeypatch.setattr(vm_plugin.linux, 'rm_file_force', rm_file_force)

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'shmem': {'path': '/dev/shm/tf_vm-uuid', 'size': 2 * 1024 * 1024},
        })

        result = plugin.hot_unplug_vm_shmem(req)
        rsp = json.loads(result)

        assert rsp['success'] is False
        assert 'unable to confirm vm vm-uuid runtime state' in rsp['error']
        vm.domain.detachDeviceFlags.assert_not_called()
        rm_file_force.assert_not_called()

    def test_hot_unplug_vm_shmem_fails_without_cleanup_when_device_remains(self, monkeypatch):
        plugin = _make_vm_plugin()
        vm = MagicMock(state=vm_plugin.Vm.VM_STATE_RUNNING)
        vm.domain.XMLDesc = MagicMock(return_value=(
            '<domain><devices><shmem name="tf_vm-uuid"><size unit="M">2</size></shmem></devices></domain>'
        ))
        vm.domain.detachDeviceFlags = MagicMock()
        rm_file_force = MagicMock()
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', MagicMock(return_value=vm))
        monkeypatch.setattr(vm_plugin.linux, 'wait_callback_success', MagicMock(return_value=False))
        monkeypatch.setattr(vm_plugin.linux, 'rm_file_force', rm_file_force)

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'shmem': {'path': '/dev/shm/tf_vm-uuid', 'size': 2 * 1024 * 1024},
        })

        result = plugin.hot_unplug_vm_shmem(req)
        rsp = json.loads(result)

        assert rsp['success'] is False
        assert 'still attached' in rsp['error']
        rm_file_force.assert_not_called()

    def test_hot_unplug_vm_shmem_cleans_file_for_stopped_vm(self, monkeypatch):
        plugin = _make_vm_plugin()
        vm = MagicMock(state=vm_plugin.Vm.VM_STATE_SHUTDOWN)
        vm.domain.detachDeviceFlags = MagicMock()
        wait_callback_success = MagicMock()
        rm_file_force = MagicMock()
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', MagicMock(return_value=vm))
        monkeypatch.setattr(vm_plugin.linux, 'wait_callback_success', wait_callback_success)
        monkeypatch.setattr(vm_plugin.linux, 'rm_file_force', rm_file_force)

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'shmem': {'path': '/dev/shm/tf_vm-uuid', 'size': 2 * 1024 * 1024},
        })

        result = plugin.hot_unplug_vm_shmem(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm.domain.detachDeviceFlags.assert_not_called()
        wait_callback_success.assert_not_called()
        rm_file_force.assert_called_once_with('/dev/shm/tf_vm-uuid')


@pytest.mark.kvmagent
class TestScriptExecOnVmHandler:
    def test_script_exec_on_vm(self):
        plugin = _make_vm_plugin()
        qga = MagicMock()
        qga.guest_exec_bash = MagicMock(side_effect=[(0, '', ''), (0, '', ''), (0, 'stdout', '')])
        qga.guest_file_is_exist = MagicMock(return_value=False)
        vm_plugin.VmQga = MagicMock(return_value=qga)
        def _fake_reconnect(_func):
            def _wrapper(*_args, **_kwargs):
                return MagicMock()
            return _wrapper
        vm_plugin.LibvirtAutoReconnect = _fake_reconnect

        cmd = MagicMock(vmUuid='vm-uuid', scriptType='Shell', scriptTimeout=1, logPath=None)
        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
            req = _make_req({})
            result = plugin.script_exec_on_vm(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['exitCode'] == 0


@pytest.mark.kvmagent
class TestSetSyncVmClockTaskHandler:
    def test_set_sync_vm_clock_task(self):
        plugin = _make_vm_plugin()
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))

        class _SyncMap(dict[int, str]):
            def has_key(self, key):
                return key in self

        plugin.sync_clock_cron_exp_map = _SyncMap({60: '*/1 * * * *'})

        from unittest.mock import mock_open
        class _IntervalMap(dict[int, str]):
            def has_key(self, key):
                return key in self

        with patch('os.path.exists', return_value=True), \
                patch('builtins.open', mock_open()), \
                patch('tempfile.mktemp', return_value='/tmp/cron'), \
                patch('os.chmod'), \
                patch('os.remove'):
            cmd = MagicMock(intervalMap=_IntervalMap())
            with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
                req = _make_req({})
                result = plugin.set_sync_vm_clock_task(req)
                rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestSetVfNicMacHandler:
    def test_set_vf_nic_mac(self):
        plugin = _make_vm_plugin()
        vm_plugin.linux.get_pf_name_by_vf_pci_address = MagicMock(return_value='pf0')
        vm_plugin.linux.get_vf_index_by_pci_address = MagicMock(return_value=1)
        vm_plugin.normalize_pci_address = MagicMock(return_value='0000:00:01.0')
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))

        req = _make_req({'nics': [{'mac': '00:11:22:33:44:55', 'pciDeviceAddress': '0000:00:01.0'}]})
        result = plugin.set_vf_nic_mac(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        vm_plugin.bash.bash_roe.assert_called()


@pytest.mark.kvmagent
class TestSetVfNicStateHandler:
    def test_set_vf_nic_state(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.state = vm_plugin.Vm.VM_STATE_RUNNING
        mock_vm.domain_xmlobject.devices.get_child_node_as_list = MagicMock(return_value=[])
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        plugin.set_domain_network_device = MagicMock()
        plugin.set_domain_iflink_state = MagicMock()
        vm_plugin.normalize_pci_address = MagicMock(return_value='0000:00:01.0')

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'haState': 'Enabled',
            'nic': {
                'mac': '00:11:22:33:44:55',
                'mtu': 1500,
                'bridgeName': 'br0',
                'nicInternalName': 'eth0',
                'vHostAddOn': {'queueNum': 1, 'rxBufferSize': 1024, 'txBufferSize': 1024},
            }
        })
        result = plugin.set_vf_nic_state(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin.set_domain_network_device.assert_called()


@pytest.mark.kvmagent
class TestStartColoSyncHandler:
    def test_start_colo_sync(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm._get_all_volume_alias_names = MagicMock(return_value=[])
        mock_vm.domain.XMLDesc = MagicMock(return_value='')
        vm_plugin.get_vm_by_uuid_no_retry = MagicMock(return_value=mock_vm)
        vm_plugin.qmp.execute_qmp_command = MagicMock(return_value={'status': 'colo'})
        vm_plugin.execute_qmp_command = MagicMock()

        with patch.object(vm_plugin, 'xrange', range, create=True):
            req = _make_req({
                'vmInstanceUuid': 'vm-uuid',
                'volumes': [],
                'nics': [],
                'fullSync': False,
                'secondaryVmHostIp': '10.0.0.2',
                'nbdServerPort': 6000,
                'blockReplicationPort': 7000,
                'checkpointDelay': 10,
                'nicNumber': 0,
            })
            result = plugin.start_colo_sync(req)
            rsp = json.loads(result)

        assert rsp['success'] is True, rsp.get('error', 'no error field')


@pytest.mark.kvmagent
class TestStartVmHandler:
    def test_start_vm(self):
        plugin = _make_vm_plugin()
        plugin._record_operation = MagicMock()
        plugin._start_vm = MagicMock()
        plugin.get_vm_device_info = MagicMock(return_value=([], [], None))
        plugin.collect_vm_virtualizer_info = MagicMock()
        vm_plugin.linux.find_vm_pid_by_uuid = MagicMock(return_value=123)
        vm_plugin.linux.enable_process_coredump = MagicMock()
        vm_plugin.linux.set_vm_priority = MagicMock()

        req = _make_req({'vmInstanceUuid': 'vm-uuid', 'vmName': 'vm', 'priorityConfigStruct': {}})
        result = plugin.start_vm(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        plugin._start_vm.assert_called_once()
        vm_plugin.linux.set_vm_priority.assert_called_once()


@pytest.mark.kvmagent
class TestTakeVolumeBackupHandler:
    def test_take_volume_backup(self):
        plugin = _make_vm_plugin()
        storage = MagicMock()
        storage.worktarget = MagicMock(return_value='/tmp/backup.qcow2')
        vm_plugin.RemoteStorageFactory.get_remote_storage = MagicMock(return_value=storage)
        mock_vm = MagicMock()
        disk = MagicMock()
        disk.driver.type_ = 'qcow2'
        mock_vm._get_target_disk = MagicMock(return_value=(disk, None))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        plugin.get_disk_device_name = MagicMock(return_value='drive-0')
        plugin.get_source_file_by_disk = MagicMock(return_value='/path/vol')
        plugin.do_take_volume_backup = MagicMock(return_value=('bitmap', 'parent'))

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'volume': {},
            'uploadDir': '/tmp',
            'backupPath': '/tmp/backup.qcow2',
            'threadContext': {'api': 'api'},
            'parent': 'parent',
        })
        result = plugin.take_volume_backup(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestTakeVolumeCbtBackupHandler:
    def test_take_volume_cbt_backup(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.domain.jobStats = MagicMock(return_value={})
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        client = MagicMock()
        client.query_mirror_volumes = MagicMock(return_value=None)
        call_order = []
        client.cbt_backup_volume = MagicMock(side_effect=lambda *args: call_order.append('cbtbak') or ['info'])
        vm_plugin.ImageStoreClient = MagicMock(return_value=client)
        vm_plugin.execute_qmp_command = MagicMock(side_effect=lambda *args: call_order.append('capability'))

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'volumeInfos': [],
            'bitmapTimestamp': '',
            'portRange': '6000-6001',
        })
        result = plugin.take_volume_cbt_backup(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['volumeInfos'] == ['info']
        assert call_order == ['capability', 'cbtbak']

    def test_take_volume_cbt_backup_returns_failure_with_partial_state(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.domain.jobStats = MagicMock(return_value={})
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        client = MagicMock()
        client.query_mirror_volumes = MagicMock(return_value=None)

        def fail(_vm, volume_infos, _bitmap, _ports):
            volume_infos[0].scratchNodeName = 'scratch'
            volume_infos[0].bitmapName = 'new-bitmap'
            raise RuntimeError('cbtbak failed')

        client.cbt_backup_volume.side_effect = fail
        vm_plugin.ImageStoreClient = MagicMock(return_value=client)
        vm_plugin.execute_qmp_command = MagicMock()

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'volumeInfos': [{'target': 'cbd:pool_physical/pool/volume'}],
            'bitmapTimestamp': 'previous-bitmap',
            'portRange': '6000-6001',
        })
        result = plugin.take_volume_cbt_backup(req)
        rsp = json.loads(result)

        assert rsp['success'] is False
        assert rsp['error'] == 'cbtbak failed'
        assert 'cleanupPending' not in rsp
        assert rsp['volumeInfos'][0]['scratchNodeName'] == 'scratch'
        assert rsp['volumeInfos'][0]['bitmapName'] == 'new-bitmap'


@pytest.mark.kvmagent
class TestTakeVolumeMirrorHandler:
    def test_take_volume_mirror(self):
        plugin = _make_vm_plugin()
        mock_vm = MagicMock()
        mock_vm.domain.jobStats = MagicMock(return_value={})
        target_disk = MagicMock()
        target_disk.alias.name_ = 'virtio-disk0'
        mock_vm._get_target_disk = MagicMock(return_value=(target_disk, None))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)
        plugin.get_disk_device_name = MagicMock(return_value='drive-0')
        client = MagicMock()
        client.query_mirror_volumes = MagicMock(return_value={})
        client.mirror_volume = MagicMock()
        vm_plugin.ImageStoreClient = MagicMock(return_value=client)
        vm_plugin.qmp.execute_qmp_command = MagicMock()

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'volume': {'installPath': '/path/vol'},
            'mirrorTarget': 'target',
            'lastMirrorVolume': 'last',
            'mode': 'full',
            'speed': 0,
        })
        result = plugin.take_volume_mirror(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        client.mirror_volume.assert_called_once()


@pytest.mark.kvmagent
class TestTakeVolumeSnapshotHandler:
    def test_take_volume_snapshot(self):
        plugin = _make_vm_plugin()
        vm_plugin.Vm.ensure_no_internal_snapshot = MagicMock()
        vm_plugin.Vm.ensure_delta_snapshot_not_exceed = MagicMock()
        vm_plugin.linux.qcow2_clone_with_cmd = MagicMock()
        vm_plugin.linux.sync_file = MagicMock()
        vm_plugin.VmPlugin._get_snapshot_size = MagicMock(return_value=123)
        vm_plugin.touchQmpSocketWhenExists = MagicMock()
        vm_plugin.uuidhelper.uuid = MagicMock(return_value='snap-uuid')
        with patch('os.path.exists', return_value=True):
            req = _make_req({
                'vmUuid': None,
                'volumeUuid': 'vol-uuid',
                'volume': {},
                'installPath': '/path/snap',
                'volumeInstallPath': '/path/vol',
                'newVolumeInstallPath': '/path/new',
                'fullSnapshot': False,
                'online': False,
                'isBaremetal2InstanceOnlineSnapshot': False,
            })
            result = plugin.take_volume_snapshot(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['size'] == 123


@pytest.mark.kvmagent
class TestTakeVolumesBackupsHandler:
    def test_take_volumes_backups(self):
        plugin = _make_vm_plugin()
        storage = MagicMock()
        storage.workspace = MagicMock(return_value='/tmp/work')
        vm_plugin.RemoteStorageFactory.get_remote_storage = MagicMock(return_value=storage)
        mock_vm = MagicMock()
        disk = MagicMock()
        mock_vm._get_target_disk = MagicMock(return_value=(disk, None))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=mock_vm)

        class _BackupInfo(object):
            def __init__(self, device_id, backup_file):
                self.deviceId: int = device_id
                self.backupFile: str = backup_file

        plugin.getBitmap = MagicMock(return_value=None)
        plugin.do_take_volumes_backup = MagicMock(return_value=[
            _BackupInfo(1, 'file1'),
            _BackupInfo(2, 'file2'),
        ])

        req = _make_req({
            'vmUuid': 'vm-uuid',
            'volumes': [{'deviceId': 1}, {'deviceId': 2}],
            'backupInfos': [],
            'backupPaths': ['fallback1', 'fallback2'],
            'uploadDir': '/tmp',
        })
        result = plugin.take_volumes_backups(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        assert len(rsp['backupInfos']) == 2


@pytest.mark.kvmagent
class TestTakeVolumesSnapshotsHandler:
    def test_take_volumes_snapshots(self):
        plugin = _make_vm_plugin()
        vm_plugin.Vm.ensure_no_internal_snapshot = MagicMock()
        vm_plugin.Vm.ensure_delta_snapshot_not_exceed = MagicMock()
        vm_plugin.linux.qcow2_clone_with_cmd = MagicMock()
        vm_plugin.VmPlugin._get_snapshot_size = MagicMock(return_value=123)
        vm_plugin.touchQmpSocketWhenExists = MagicMock()
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=None)
        with patch('os.path.exists', return_value=True):
            vm_plugin.uuidhelper.uuid = MagicMock(return_value='uuid')
            req = _make_req({
                'snapshotJobs': [{
                    'vmInstanceUuid': 'vm-uuid',
                    'live': False,
                    'full': False,
                    'memory': False,
                    'previousInstallPath': '/path/prev',
                    'installPath': '/path/snap',
                    'newVolumeInstallPath': '/path/new',
                    'volumeUuid': 'vol-uuid',
                    'deviceId': 0,
                    'volume': {'installPath': '/path/vol'},
                }]
            })
            result = plugin.take_volumes_snapshots(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        assert len(rsp['snapshots']) == 1


@pytest.mark.kvmagent
class TestUnexportNbdVolumesHandler:
    def test_unexport_nbd_volumes(self):
        plugin = _make_vm_plugin()
        plugin.get_cbt_volume_actual_install_path = MagicMock(return_value='/path/vol')
        plugin.deactive_volume_if_need = MagicMock()

        volume = MagicMock(installPath='/path/vol')
        cmd = MagicMock(volumes=[volume])
        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
            with patch.object(vm_plugin.qemu_nbd, 'kill_nbd_process_by_flag', return_value=0) as kill_nbd:
                req = _make_req({})
                result = plugin.unexport_nbd_volumes(req)
                rsp = json.loads(result)

        assert rsp['success'] is True
        kill_nbd.assert_called_once_with('/path/vol')
        plugin.deactive_volume_if_need.assert_called_once_with('/path/vol', False)

    def test_unexport_nbd_volumes_does_not_deactivate_when_kill_times_out(self):
        plugin = _make_vm_plugin()
        plugin.get_cbt_volume_actual_install_path = MagicMock(return_value='/path/vol')
        plugin.deactive_volume_if_need = MagicMock()

        volume = MagicMock(installPath='/path/vol')
        cmd = MagicMock(volumes=[volume])
        err = Exception('timeout waiting qemu-nbd process[/path/vol] gone after SIGTERM')
        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
            with patch.object(vm_plugin.qemu_nbd, 'kill_nbd_process_by_flag', side_effect=err) as kill_nbd:
                req = _make_req({})
                result = plugin.unexport_nbd_volumes(req)
                rsp = json.loads(result)

        assert rsp['success'] is False
        assert 'timeout waiting qemu-nbd process' in rsp['error']
        kill_nbd.assert_called_once_with('/path/vol')
        plugin.deactive_volume_if_need.assert_not_called()

    def test_unexport_nbd_volumes_uses_configured_cbd_path(self):
        plugin = _make_vm_plugin()
        cbd_path = 'cbd:pool_physical/pool/volume'
        configured_path = cbd_path + '_zbs_:/etc/zbs/client.conf'
        plugin.deactive_volume_if_need = MagicMock()
        volume = MagicMock(installPath=cbd_path)
        cmd = MagicMock(volumes=[volume])

        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd), \
                patch.object(vm_plugin, 'get_volume_actual_installpath', return_value=configured_path):
            with patch.object(vm_plugin.qemu_nbd, 'kill_nbd_process_by_flag', return_value=0) as kill_nbd:
                result = plugin.unexport_nbd_volumes(_make_req({}))
                rsp = json.loads(result)

        assert rsp['success'] is True
        kill_nbd.assert_called_once_with(configured_path)
        plugin.deactive_volume_if_need.assert_called_once_with(configured_path, False)

    def test_unexport_nbd_volumes_falls_back_to_legacy_cbd_path(self):
        plugin = _make_vm_plugin()
        cbd_path = 'cbd:pool_physical/pool/volume'
        configured_path = cbd_path + '_zbs_:/etc/zbs/client.conf'
        plugin.deactive_volume_if_need = MagicMock()
        volume = MagicMock(installPath=cbd_path)
        cmd = MagicMock(volumes=[volume])

        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd), \
                patch.object(vm_plugin, 'get_volume_actual_installpath', return_value=configured_path), \
                patch.object(vm_plugin.qemu_nbd, 'kill_nbd_process_by_flag', side_effect=[1, 0]) as kill_nbd:
            result = plugin.unexport_nbd_volumes(_make_req({}))
            rsp = json.loads(result)

        assert rsp['success'] is True
        assert [call.args[0] for call in kill_nbd.call_args_list] == [configured_path, cbd_path]
        plugin.deactive_volume_if_need.assert_called_once_with(configured_path, False)


@pytest.mark.kvmagent
class TestUploadVmFileHandler:
    def test_upload_vm_file(self):
        plugin = _make_vm_plugin()
        qga = MagicMock()
        qga.os = 'linux'
        qga.guest_exec_bash = MagicMock(return_value=(0, '', ''))
        qga.guest_file_open = MagicMock(return_value=1)
        qga.call_qga_command = MagicMock(return_value={'count': 3})
        qga.guest_file_close = MagicMock()
        vm_plugin.VmQga = MagicMock(return_value=qga)
        def _fake_reconnect(_func):
            def _wrapper(*_args, **_kwargs):
                return MagicMock()
            return _wrapper
        vm_plugin.LibvirtAutoReconnect = _fake_reconnect

        cmd = MagicMock(
            vmUuid='vm-uuid',
            fileType='Script',
            scriptType='Shell',
            fileContent='echo',
            dstPath='/tmp/file',
            param='',
        )
        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd):
            req = _make_req({})
            result = plugin.upload_vm_file(req)
            rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestWaitSecondaryVmReadyHandler:
    def test_wait_secondary_vm_ready(self):
        plugin = _make_vm_plugin()
        vm_plugin.linux.wait_callback_success = MagicMock(return_value=True)

        req = _make_req({'vmInstanceUuid': 'vm-uuid', 'coloCheckTimeout': 10})
        result = plugin.wait_secondary_vm_ready(req)
        rsp = json.loads(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestVmStartCmdXmlBuild:
    class _RangeCompat:
        def __init__(self, *args):
            self._iter: Iterator[int] = iter(range(*args))
        def __iter__(self):
            return self
        def __next__(self):
            return next(self._iter)
        def next(self):
            return next(self._iter)

    def _build_start_cmd(self, use_numa=False):
        cmd_dict: dict[str, object] = {
            'vmInstanceUuid': 'vm-uuid',
            'vmName': 'vm-name',
            'accountUuid': 'acct-uuid',
            'vmInternalId': 101,
            'hostManagementIp': '10.0.0.1',
            'useNuma': use_numa,
            'machineType': 'q35',
            'bootMode': 'UEFI',
            'imagePlatform': 'other',
            'architecture': None,
            'memory': 1024 * 1024,
            'cpuNum': 4,
            'maxVcpuNum': 8,
            'socketNum': 2,
            'cpuOnSocket': 2,
            'threadsPerCore': 1,
            'nestedVirtualization': 'host-model',
            'vmCpuModel': 'Icelake-Server',
            'vmCpuVendorId': 'GenuineIntel',
            'vmCpuVendorId': 'GenuineIntel',
            'cpuHypervisorFeature': False,
            'x2apic': False,
            'kvmHiddenState': True,
            'vmPortOff': True,
            'emulateHyperV': True,
            'hypervClock': True,
            'vendorId': 'zstack',
            'MemAccess': 'shared',
            'useHugePage': True,
            'noSharePages': True,
            'useBootMenu': True,
            'bootMenuSplashTimeout': 5,
            'systemSerialNumber': 'SERIAL',
            'chassisAssetTag': 'ASSET',
            'oemStrings': ['oem1', 'oem2'],
            'clock': 'localtime',
            'clockTrack': None,
            'consolePassword': 'secret',
            'consoleMode': 'spice',
            'spiceChannels': ['main'],
            'spiceStreamingMode': 'filter',
            'videoType': 'qxl',
            'VDIMonitorNumber': 2,
            'qxlMemory': {'ram': 65536, 'vram': 65536, 'vgamem': 16384},
            'soundType': None,
            'suspendToDisk': True,
            'suspendToRam': False,
            'additionalQmp': True,
            'qemu64BitPciMmioSetup': True,
            'useColoBinary': False,
            'coloPrimary': False,
            'coloSecondary': False,
            'isApplianceVm': False,
            'pciePortNums': 2,
            'predefinedPciBridgeNum': 1,
            'memBalloon': {
                'deviceAddress': {
                    'domain': '0x0000',
                    'bus': '0x00',
                    'slot': '0x04',
                    'function': '0x0',
                }
            },
            'rootVolume': {
                'deviceId': 0,
                'deviceType': 'file',
                'installPath': '/path/root.qcow2',
                'cacheMode': 'none',
                'useVirtio': True,
                'useVirtioSCSI': False,
                'volumeUuid': 'vol-root',
                'wwn': 'wwn-root',
                'shareable': False,
                'multiQueues': 4,
                'ioThreadId': 2,
                'bootOrder': 1,
            },
            'dataVolumes': [
                {
                    'deviceId': 1,
                    'deviceType': 'file',
                    'installPath': '/path/data1.qcow2',
                    'cacheMode': 'none',
                    'useVirtio': False,
                    'useVirtioSCSI': False,
                    'volumeUuid': 'vol-data1',
                    'shareable': True,
                },
                {
                    'deviceId': 2,
                    'deviceType': 'ceph',
                    'installPath': 'ceph://pool/vol2',
                    'useVirtio': True,
                    'useVirtioSCSI': True,
                    'volumeUuid': 'vol-data2',
                    'wwn': 'wwn-data2',
                    'secretUuid': 'ceph-secret',
                    'monInfo': [{'hostname': '10.0.0.2', 'port': 6789}],
                    'physicalBlockSize': 4096,
                    'shareable': True,
                },
                {
                    'deviceId': 3,
                    'deviceType': 'block',
                    'installPath': '/dev/sdb',
                    'useVirtio': True,
                    'useVirtioSCSI': False,
                    'volumeUuid': 'vol-data3',
                    'cacheMode': 'none',
                },
            ],
            'cacheVolumes': [],
            'cdRoms': [
                {
                    'deviceId': 0,
                    'isEmpty': True,
                    'bootOrder': 1,
                    'resourceUuid': 'cdrom-0',
                    'path': '',
                },
                {
                    'deviceId': 1,
                    'isEmpty': False,
                    'path': 'ceph://pool/iso',
                    'resourceUuid': 'cdrom-1',
                    'secretUuid': 'iso-secret',
                    'monInfo': [{'hostname': '10.0.0.3', 'port': 6789}],
                },
                {
                    'deviceId': 2,
                    'isEmpty': False,
                    'protocol': 'vhost',
                    'path': '/var/run/vhost.iso',
                    'resourceUuid': 'cdrom-2',
                },
            ],
            'nics': [
                {
                    'uuid': 'nic-1',
                    'type': 'VNIC',
                    'mac': '00:11:22:33:44:55',
                    'mtu': 1500,
                    'bridgeName': 'br0',
                    'nicInternalName': 'tap0',
                    'cleanTraffic': True,
                    'ips': ['192.168.0.10'],
                    'useVirtio': True,
                    'driverType': 'virtio',
                    'vHostAddOn': {'queueNum': 2, 'rxBufferSize': 512, 'txBufferSize': 256},
                    'bootOrder': 1,
                    'state': 'disable',
                    'pci': {'type': 'pci', 'domain': '0x0000', 'bus': '0x00', 'slot': '0x03', 'function': '0x0'},
                },
                {
                    'uuid': 'nic-2',
                    'type': 'VF',
                    'mac': '00:11:22:33:44:66',
                    'mtu': 1500,
                    'bridgeName': 'br1',
                    'nicInternalName': 'tap1',
                    'useVirtio': False,
                    'vHostAddOn': {'queueNum': 1, 'rxBufferSize': 1024, 'txBufferSize': 1024},
                    'pciDeviceAddress': '0000:00:05.0',
                    'extraPciDeviceAddresses': ['0000:00:05.1'],
                },
                {
                    'uuid': 'nic-3',
                    'type': 'TFVNIC',
                    'mac': '00:11:22:33:44:77',
                    'mtu': 1500,
                    'nicInternalName': 'tap2',
                    'l2NetworkUuid': 'l2-uuid',
                    'ipForTf': '10.0.0.10',
                },
            ],
            'addons': {
                'noConsole': False,
                'onCrash': 'preserve',
                'ioThreadNum': 1,
                'ioThreadPins': [{'ioThreadId': 1, 'pin': '0-3'}],
                'cpuPinning': [{'vCpu': 0, 'pCpuSet': '0'}],
                'emulatorPinning': '0-3',
                'qemuCommandLine': ['-smp', '2'],
                'qemuPath': None,
                'vhostSrcPath': None,
                'brMode': None,
                'useDataPlane': True,
                'VolumeQos': {'vol-root': {'totalBandwidth': 1024, 'totalIops': 100}},
                'NativeAio': False,
                'NicQos': {'nic-1': {'outboundBandwidth': 1024 * 8 * 1024, 'inboundBandwidth': 2048 * 8 * 1024}},
                'channel': {'socketPath': '/tmp/chan.sock', 'targetName': 'org.zstack.channel.0'},
                'channel_vr': {'socketPath': '/tmp/chan-vr.sock', 'targetName': 'org.zstack.vr.0'},
                'ceph_secret_key': None,
                'ceph_secret_uuid': None,
                'pciDevice': ['0000:00:01.0,'],
                'mdevDevice': ['11111111-1111-1111-1111-111111111111'],
                'storageDevice': [],
                'usbDevice': ['1:2:1d6b:0002:2.0:PassThrough:1234:127.0.0.1'],
                'panicIsa': True,
                'panicHyperv': True,
                'systemVirtioDriverDeviceType': None,
                'FIXED_CDROMS': None,
                'loaderRom': None,
                'userDefinedXmlHookScript': None,
                'userDefinedXml': None,
                'hygonMdevDevice': None,
                'l3mapping': None,
            },
        }
        addons = cmd_dict['addons']
        if use_numa:
            if isinstance(addons, dict):
                addons['numaNodes'] = []
        else:
            if isinstance(addons, dict):
                addons['numaNodes'] = [
                    {'nodeID': 0, 'hostNodeID': 0, 'cpus': '0-3', 'memorySize': 1024 * 1024, 'distance': [10, 20]}
                ]
        return jsonobject.loads(json.dumps(cmd_dict))

    def _driver_by_target(self, root, dev):
        for disk in root.findall('./devices/disk'):
            target = disk.find('target')
            if target is not None and target.get('dev') == dev:
                return disk.find('driver')
        raise AssertionError("disk target %s not found" % dev)

    def _driver_by_bus(self, root, bus):
        for disk in root.findall('./devices/disk'):
            target = disk.find('target')
            if target is not None and target.get('bus') == bus:
                return disk.find('driver')
        raise AssertionError("disk bus %s not found" % bus)

    def _driver_by_serial(self, root, serial_text):
        for disk in root.findall('./devices/disk'):
            serial = disk.find('serial')
            if serial is not None and serial.text == serial_text:
                return disk.find('driver')
        raise AssertionError("disk serial %s not found" % serial_text)

    def _scsi_controller_driver(self, root):
        for controller in root.findall('./devices/controller'):
            if controller.get('type') == 'scsi' and controller.find('driver') is not None:
                return controller.find('driver')
        raise AssertionError("virtio-scsi controller driver not found")

    def _iothread_queue_mapping(self, driver):
        return [
            (iothread.get('id'), [queue.get('id') for queue in iothread.findall('queue')])
            for iothread in driver.findall('./iothreads/iothread')
        ]

    def _build_start_vm_xml(self, cmd):
        vm_plugin.ovs.OvsDpdkSupportVnic = []
        vm_plugin.pci.need_config_pcimmio = MagicMock(return_value=True)
        vm_plugin.pci.get_bars_max_addressable_memory = MagicMock(return_value=256)
        vm_plugin.linux.get_cpu_model = MagicMock(return_value=('GenuineIntel', 'Intel'))
        vm_plugin.is_hv_freq_supported = MagicMock(return_value=True)
        vm_plugin.is_hv_synic_supported = MagicMock(return_value=True)
        vm_plugin.is_ioapic_supported = MagicMock(return_value=True)
        vm_plugin.is_spice_tls = MagicMock(return_value=0)
        vm_plugin.is_spiceport_driver_supported = MagicMock(return_value=True)
        vm_plugin.notify_vrouter = MagicMock()
        vm_plugin.VmPlugin.clean_vm_firmware_flash = MagicMock()
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))
        vm_plugin.linux.VmUsbManager = MagicMock(return_value=MagicMock(request_slot=MagicMock(return_value=1)))
        vm_plugin.netaddr.IPAddress = MagicMock(side_effect=lambda addr: MagicMock(version=4))
        vm_plugin.uuidhelper.to_full_uuid = MagicMock(side_effect=lambda value: value)
        def _real_parse_url(uri):
            normalized = vm_plugin.re.sub(r'^([a-zA-Z]+:)(?!/{2})', r'\1//', uri, count=1)
            return urllib.parse.urlparse(normalized)

        def _e_with_text(parent, tag, value=None, attrib=None, usenamesapce=False):
            _ = usenamesapce
            if attrib is None:
                attrib = {}
            attrib = {k: str(v) for k, v in attrib.items()}
            elem = vm_plugin.etree.SubElement(parent, tag, attrib)
            if value:
                elem.text = str(value)
            return elem

        orig_tostring = vm_plugin.etree.tostring
        with patch('os.path.exists', return_value=True), \
                patch.object(vm_plugin, 'parse_url', side_effect=_real_parse_url), \
                patch.object(vm_plugin, 'xrange', range, create=True), \
                patch.object(vm_plugin, 'range', self._RangeCompat), \
                patch.object(vm_plugin, 'e', side_effect=_e_with_text), \
                patch.object(vm_plugin.etree, 'tostring', side_effect=orig_tostring):
            vm = vm_plugin.Vm.from_StartVmCmd(cmd)
        return vm.domain_xml.decode() if isinstance(vm.domain_xml, bytes) else vm.domain_xml

    def _add_vm_artifact_view(self, cmd, tmp_path, monkeypatch):
        view_root = tmp_path / 'vm-views'
        view_path = view_root / cmd.vmInstanceUuid
        view_path.mkdir(parents=True)
        monkeypatch.setattr(vm_artifact, 'VM_VIEW_ROOT', str(view_root))
        cmd.addons.vmArtifactViews = [{
            'vmInstanceUuid': cmd.vmInstanceUuid,
            'tag': 'artifact-view',
            'sourcePath': str(view_path),
        }]
        return view_path

    def test_memory_backing_shared_memaccess_only(self):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.MemAccess = 'shared'
        cmd.useHugePage = False
        cmd.noSharePages = False

        xml_str = self._build_start_vm_xml(cmd)

        assert '<memoryBacking>' in xml_str
        assert '<source type="memfd"' in xml_str
        assert '<access mode="shared"' in xml_str
        assert '<hugepages' not in xml_str
        assert '<nosharepages' not in xml_str

    def test_memory_backing_memaccess_does_not_substring_match(self):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.MemAccess = 'sh'
        cmd.useHugePage = False
        cmd.noSharePages = False

        xml_str = self._build_start_vm_xml(cmd)

        assert '<memoryBacking>' not in xml_str
        assert '<access mode="shared"' not in xml_str

    def test_vm_artifact_views_force_shared_memory_backing(self, tmp_path, monkeypatch):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.MemAccess = 'private'
        cmd.useHugePage = False
        cmd.noSharePages = False
        self._add_vm_artifact_view(cmd, tmp_path, monkeypatch)

        xml_str = self._build_start_vm_xml(cmd)

        assert '<filesystem type="mount" accessmode="passthrough">' in xml_str
        assert '<target dir="artifact-view"' in xml_str
        assert '<memoryBacking>' in xml_str
        assert '<source type="memfd"' in xml_str
        assert '<access mode="shared"' in xml_str

    def test_vm_artifact_views_keep_explicit_shared_memory_backing(self, tmp_path, monkeypatch):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.MemAccess = 'shared'
        cmd.useHugePage = False
        cmd.noSharePages = False
        self._add_vm_artifact_view(cmd, tmp_path, monkeypatch)

        xml_str = self._build_start_vm_xml(cmd)

        assert '<filesystem type="mount" accessmode="passthrough">' in xml_str
        assert '<driver type="virtiofs" queue="1024"' in xml_str
        assert '<cache mode="none"' in xml_str
        assert '<readonly' in xml_str
        assert '<memoryBacking>' in xml_str
        assert '<access mode="shared"' in xml_str

    def test_memory_backing_hugepage_only(self):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.MemAccess = 'private'
        cmd.useHugePage = True
        cmd.noSharePages = False

        xml_str = self._build_start_vm_xml(cmd)

        assert '<memoryBacking>' in xml_str
        assert '<hugepages' in xml_str
        assert '<allocation mode="immediate"' in xml_str
        assert '<nosharepages' in xml_str
        assert '<access mode="shared"' not in xml_str
        assert '<source type="memfd"' not in xml_str

    def test_memory_backing_nosharepages_only(self):
        cmd = self._build_start_cmd(use_numa=False)
        cmd.MemAccess = 'private'
        cmd.useHugePage = False
        cmd.noSharePages = True

        xml_str = self._build_start_vm_xml(cmd)

        assert '<memoryBacking>' in xml_str
        assert '<nosharepages' in xml_str
        assert '<hugepages' not in xml_str
        assert '<access mode="shared"' not in xml_str
        assert '<source type="memfd"' not in xml_str

    def test_from_start_vm_cmd_builds_xml_with_features(self):
        vm_plugin.ovs.OvsDpdkSupportVnic = []
        vm_plugin.pci.need_config_pcimmio = MagicMock(return_value=True)
        vm_plugin.pci.get_bars_max_addressable_memory = MagicMock(return_value=256)
        vm_plugin.linux.get_cpu_model = MagicMock(return_value=('GenuineIntel', 'Intel'))
        vm_plugin.is_hv_freq_supported = MagicMock(return_value=True)
        vm_plugin.is_hv_synic_supported = MagicMock(return_value=True)
        vm_plugin.is_ioapic_supported = MagicMock(return_value=True)
        vm_plugin.is_spice_tls = MagicMock(return_value=0)
        vm_plugin.is_spiceport_driver_supported = MagicMock(return_value=True)
        vm_plugin.notify_vrouter = MagicMock()
        vm_plugin.VmPlugin.clean_vm_firmware_flash = MagicMock()
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))
        vm_plugin.linux.VmUsbManager = MagicMock(return_value=MagicMock(request_slot=MagicMock(return_value=1)))
        vm_plugin.netaddr.IPAddress = MagicMock(side_effect=lambda addr: MagicMock(version=4))
        vm_plugin.uuidhelper.to_full_uuid = MagicMock(side_effect=lambda value: value)
        def _real_parse_url(uri):
            normalized = vm_plugin.re.sub(r'^([a-zA-Z]+:)(?!/{2})', r'\1//', uri, count=1)
            return urllib.parse.urlparse(normalized)

        def _e_with_text(parent, tag, value=None, attrib=None, usenamesapce=False):
            _ = usenamesapce
            if attrib is None:
                attrib = {}
            attrib = {k: str(v) for k, v in attrib.items()}
            elem = vm_plugin.etree.SubElement(parent, tag, attrib)
            if value:
                elem.text = str(value)
            return elem

        orig_tostring = vm_plugin.etree.tostring
        with patch('os.path.exists', return_value=True), \
                patch.object(vm_plugin, 'parse_url', side_effect=_real_parse_url), \
                patch.object(vm_plugin, 'xrange', range, create=True), \
                patch.object(vm_plugin, 'range', self._RangeCompat), \
                patch.object(vm_plugin.kvmagent, 'get_host_os_type', return_value='ky10'), \
                patch.object(vm_plugin, 'e', side_effect=_e_with_text), \
                patch.object(vm_plugin.etree, 'tostring', side_effect=orig_tostring):
            cmd = self._build_start_cmd(use_numa=False)
            vm = vm_plugin.Vm.from_StartVmCmd(cmd)
        xml_str = vm.domain_xml.decode() if isinstance(vm.domain_xml, bytes) else vm.domain_xml
        assert '<memoryBacking>' in xml_str
        assert '<hyperv>' in xml_str
        assert 'qemu:commandline' in xml_str
        assert '-qmp' in xml_str
        assert 'fw_cfg' in xml_str
        assert 'org.spice-space.webdav.0' in xml_str
        assert 'protocol="rbd"' in xml_str
        assert 'clean-traffic' in xml_str
        assert 'net0-slave1' in xml_str
        root = vm_plugin.etree.fromstring(xml_str)
        iothread_ids = {iothread.get('id') for iothread in root.findall('./iothreadids/iothread')}
        assert iothread_ids == {'1', '2'}
        assert root.find('iothreads').text == '2'

    def test_from_start_vm_cmd_builds_xml_with_numa(self):
        vm_plugin.ovs.OvsDpdkSupportVnic = []
        vm_plugin.linux.get_cpu_model = MagicMock(return_value=('GenuineIntel', 'Intel'))
        vm_plugin.is_ioapic_supported = MagicMock(return_value=True)
        vm_plugin.is_spice_tls = MagicMock(return_value=0)
        vm_plugin.VmPlugin.clean_vm_firmware_flash = MagicMock()
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))
        vm_plugin.linux.VmUsbManager = MagicMock(return_value=MagicMock(request_slot=MagicMock(return_value=1)))
        vm_plugin.netaddr.IPAddress = MagicMock(side_effect=lambda addr: MagicMock(version=4))
        vm_plugin.uuidhelper.to_full_uuid = MagicMock(side_effect=lambda value: value)
        def _real_parse_url(uri):
            normalized = vm_plugin.re.sub(r'^([a-zA-Z]+:)(?!/{2})', r'\1//', uri, count=1)
            return urllib.parse.urlparse(normalized)

        def _e_with_text(parent, tag, value=None, attrib=None, usenamesapce=False):
            _ = usenamesapce
            if attrib is None:
                attrib = {}
            attrib = {k: str(v) for k, v in attrib.items()}
            elem = vm_plugin.etree.SubElement(parent, tag, attrib)
            if value:
                elem.text = str(value)
            return elem

        orig_tostring = vm_plugin.etree.tostring
        with patch('os.path.exists', return_value=True), \
                patch.object(vm_plugin, 'parse_url', side_effect=_real_parse_url), \
                patch.object(vm_plugin, 'xrange', range, create=True), \
                patch.object(vm_plugin, 'cmp', lambda a, b: (a > b) - (a < b), create=True), \
                patch.object(vm_plugin, 'is_hv_freq_supported', return_value=False), \
                patch.object(vm_plugin, 'is_hv_synic_supported', return_value=False), \
                patch.object(vm_plugin, 'range', self._RangeCompat), \
                patch.object(vm_plugin.kvmagent, 'get_host_os_type', return_value='ky10'), \
                patch.object(vm_plugin, 'e', side_effect=_e_with_text), \
                patch.object(vm_plugin.etree, 'tostring', side_effect=orig_tostring):
            cmd = self._build_start_cmd(use_numa=True)
            cmd.nics = []
            cmd.cdRoms = []
            cmd.consoleMode = 'vnc'
            vm = vm_plugin.Vm.from_StartVmCmd(cmd)
        xml_str = vm.domain_xml.decode() if isinstance(vm.domain_xml, bytes) else vm.domain_xml
        assert '<vcpu' in xml_str
        assert 'numa' in xml_str

    def test_cdp_cbd_recover_nbd_disk_keeps_iothread_vq_mapping(self):
        vm_plugin.ovs.OvsDpdkSupportVnic = []
        vm_plugin.linux.get_cpu_model = MagicMock(return_value=('GenuineIntel', 'Intel'))
        vm_plugin.is_ioapic_supported = MagicMock(return_value=True)
        vm_plugin.is_spice_tls = MagicMock(return_value=0)
        vm_plugin.VmPlugin.clean_vm_firmware_flash = MagicMock()
        vm_plugin.bash.bash_roe = MagicMock(return_value=(0, '', ''))
        vm_plugin.uuidhelper.to_full_uuid = MagicMock(side_effect=lambda value: value)
        vm_plugin.VM_RECOVER_DICT = {}

        def _real_parse_url(uri):
            normalized = vm_plugin.re.sub(r'^([a-zA-Z]+:)(?!/{2})', r'\1//', uri, count=1)
            return urllib.parse.urlparse(normalized)

        def _e_with_text(parent, tag, value=None, attrib=None, usenamesapce=False):
            _ = usenamesapce
            if attrib is None:
                attrib = {}
            attrib = {k: str(v) for k, v in attrib.items()}
            elem = vm_plugin.etree.SubElement(parent, tag, attrib)
            if value:
                elem.text = str(value)
            return elem

        cmd = self._build_start_cmd(use_numa=False)
        cmd.addons.ioThreadNum = 0
        cmd.addons.ioThreadPins = []
        cmd.addons.VolumeQos = None
        cmd.addons.NicQos = None
        cmd.addons.pciDevice = []
        cmd.addons.mdevDevice = []
        cmd.addons.storageDevice = []
        cmd.addons.usbDevice = []
        cmd.cdRoms = []
        cmd.nics = []
        cmd.rootVolume.deviceType = 'cbd'
        cmd.rootVolume.installPath = 'cbd://pool/root-volume?r=nbd://127.0.0.1:10809/root'
        cmd.rootVolume.volumeUuid = 'vol-root-cbd'
        cmd.rootVolume.multiQueues = 4
        cmd.rootVolume.ioThreads = 4
        cmd.rootVolume.ioThreadId = None
        cmd.rootVolume.physicalBlockSize = None
        cmd.dataVolumes = jsonobject.loads(json.dumps([
            {
                'deviceId': 1,
                'deviceType': 'cbd',
                'installPath': 'cbd://pool/data-volume?r=nbd://127.0.0.1:10810/data',
                'useVirtio': True,
                'useVirtioSCSI': False,
                'volumeUuid': 'vol-data-cbd',
                'shareable': False,
                'multiQueues': 4,
                'ioThreads': 4,
                'ioThreadId': None,
                'physicalBlockSize': None,
            },
            {
                'deviceId': 2,
                'deviceType': 'cbd',
                'installPath': 'cbd://pool/scsi-volume?r=nbd://127.0.0.1:10811/scsi',
                'useVirtio': True,
                'useVirtioSCSI': True,
                'volumeUuid': 'vol-scsi-cbd',
                'shareable': False,
                'multiQueues': 4,
                'ioThreads': 4,
                'ioThreadId': None,
                'physicalBlockSize': None,
                'wwn': 'wwn-scsi-cbd',
            },
            {
                'deviceId': 3,
                'deviceType': 'ceph',
                'installPath': 'ceph://pool/non-cbd-volume?r=nbd://127.0.0.1:10812/non-cbd',
                'useVirtio': True,
                'useVirtioSCSI': False,
                'volumeUuid': 'vol-non-cbd',
                'shareable': False,
                'multiQueues': 4,
                'ioThreads': 4,
                'ioThreadId': None,
                'physicalBlockSize': None,
                'secretUuid': 'ceph-secret',
                'monInfo': [{'hostname': '10.0.0.2', 'port': 6789}],
            },
            {
                'deviceId': 4,
                'deviceType': 'cbd',
                'installPath': 'cbd://pool/manual-iothread-volume?r=nbd://127.0.0.1:10813/manual',
                'useVirtio': True,
                'useVirtioSCSI': False,
                'volumeUuid': 'vol-manual-cbd',
                'shareable': False,
                'multiQueues': 4,
                'ioThreads': 4,
                'ioThreadId': 9,
                'physicalBlockSize': None,
            },
        ]))

        orig_tostring = vm_plugin.etree.tostring
        with patch('os.path.exists', return_value=True), \
                patch.object(vm_plugin, 'parse_url', side_effect=_real_parse_url), \
                patch.object(vm_plugin, 'xrange', range, create=True), \
                patch.object(vm_plugin, 'range', self._RangeCompat), \
                patch.object(vm_plugin, 'e', side_effect=_e_with_text), \
                patch.object(vm_plugin.etree, 'tostring', side_effect=orig_tostring):
            vm = vm_plugin.Vm.from_StartVmCmd(cmd)

        assert cmd.createPaused is True
        xml_str = vm.domain_xml.decode() if isinstance(vm.domain_xml, bytes) else vm.domain_xml
        root = vm_plugin.etree.fromstring(xml_str)
        root_driver = self._driver_by_target(root, 'vda')
        data_driver = self._driver_by_target(root, 'vdb')
        scsi_driver = self._driver_by_bus(root, 'scsi')
        non_cbd_driver = self._driver_by_serial(root, 'vol-non-cbd')
        manual_cbd_driver = self._driver_by_serial(root, 'vol-manual-cbd')

        assert root_driver.get('queues') == '4'
        assert data_driver.get('queues') == '4'
        assert non_cbd_driver.get('queues') == '4'
        assert manual_cbd_driver.get('queues') == '4'
        assert self._iothread_queue_mapping(root_driver) == [
            ('101', ['0']), ('102', ['1']), ('103', ['2']), ('104', ['3'])
        ]
        assert self._iothread_queue_mapping(data_driver) == [
            ('105', ['0']), ('106', ['1']), ('107', ['2']), ('108', ['3'])
        ]
        assert scsi_driver.find('iothreads') is None
        assert self._scsi_controller_driver(root).get('queues') == '4'
        assert self._iothread_queue_mapping(self._scsi_controller_driver(root)) == [
            ('109', ['0']), ('110', ['1']), ('111', ['2']), ('112', ['3'])
        ]
        assert non_cbd_driver.find('iothreads') is None
        assert manual_cbd_driver.find('iothreads') is None

        recover_root_driver = vm_plugin.VM_RECOVER_DICT['vm-uuid']['vda'].find('driver')
        recover_data_driver = vm_plugin.VM_RECOVER_DICT['vm-uuid']['vdb'].find('driver')
        assert self._iothread_queue_mapping(recover_root_driver) == self._iothread_queue_mapping(root_driver)
        assert self._iothread_queue_mapping(recover_data_driver) == self._iothread_queue_mapping(data_driver)


@pytest.mark.kvmagent
class TestVmPluginDiskXmlHelpers:
    _orig_fromstring: Callable[..., object] | None = None
    _orig_parse: Callable[..., object] | None = None
    _orig_tostring: Callable[..., object] | None = None

    def _build_parser(self):
        class _CompatElement(ET.Element):
            def getchildren(self):
                return list(self)

        return vm_plugin.etree.XMLParser(target=vm_plugin.etree.TreeBuilder(element_factory=_CompatElement))

    def _parse_with_getchildren(self, xml_str):
        parser = self._build_parser()
        if self._orig_fromstring is None:
            raise AssertionError("_orig_fromstring not set")
        return self._orig_fromstring(xml_str, parser=parser)

    def _parse_file_with_getchildren(self, file_path, **_kwargs):
        parser = self._build_parser()
        if self._orig_parse is None:
            raise AssertionError("_orig_parse not set")
        return self._orig_parse(file_path, parser=parser)

    def _write_temp_file(self, content):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            data = content.encode() if isinstance(content, str) else content
            _ = tmp.write(data)
            return tmp.name

    def test_get_new_disk_updates_block_source(self):
        disk_xml = (
            "<disk type='file' device='disk'>"
            "<driver name='qemu' type='qcow2'/>"
            "<source file='/dev/vol0'/>"
            "<target dev='vda' bus='virtio'/>"
            "<alias name='virtio-disk0'/>"
            "<serial>vol0</serial>"
            "<wwn>wwn0</wwn>"
            "<address type='pci' domain='0x0000' bus='0x00' slot='0x0a' function='0x0'/>"
            "</disk>"
        )
        vm_plugin.block_device_use_block_type = MagicMock(return_value=True)
        self._orig_fromstring = vm_plugin.etree.fromstring
        old_disk = self._parse_with_getchildren(disk_xml)
        orig_tostring = vm_plugin.etree.tostring
        with patch.object(vm_plugin.etree, 'tostring', return_value='disk-xml'), \
                patch.object(vm_plugin, 'logger', MagicMock()):
            new_disk = vm_plugin.VmPlugin._get_new_disk(old_disk)
        new_xml = orig_tostring(new_disk).decode()
        assert 'type="block"' in new_xml
        assert 'source dev="/dev/vol0"' in new_xml
        assert 'alias name="virtio-disk0"' in new_xml
        assert '<serial>' in new_xml
        assert '<wwn>' in new_xml

    def test_build_domain_new_xml_and_dest_disk_xml(self):
        plugin = _make_vm_plugin()
        vm = MagicMock()
        vm.domain_xml = (
            "<domain>"
            "<devices>"
            "<disk type='file' device='disk'>"
            "<driver name='qemu' type='qcow2'/>"
            "<source file='/dev/old'/>"
            "<target dev='vda' bus='virtio'/>"
            "<alias name='virtio-disk0'/>"
            "</disk>"
            "</devices>"
            "</domain>"
        )
        vm._get_target_disk_by_path = MagicMock(return_value=(None, 'vda'))
        vm_plugin.block_device_use_block_type = MagicMock(return_value=True)
        self._orig_parse = vm_plugin.etree.parse
        self._orig_fromstring = vm_plugin.etree.fromstring
        self._orig_tostring = vm_plugin.etree.tostring
        with patch.object(vm_plugin.linux, 'write_to_temp_file', side_effect=self._write_temp_file), \
                patch.object(vm_plugin.etree, 'parse', side_effect=self._parse_file_with_getchildren), \
                patch.object(vm_plugin.etree, 'fromstring', side_effect=self._parse_with_getchildren), \
                patch.object(vm_plugin.etree, 'tostring', return_value='disk-xml'), \
                patch.object(vm_plugin, 'logger', MagicMock()):
            volume = jsonobject.loads(json.dumps({
                'deviceType': 'file',
                'installPath': '/dev/new',
                'cacheMode': 'none',
                'useVirtio': True,
                'useVirtioSCSI': False,
                'volumeUuid': 'vol-uuid',
                'deviceId': 0,
            }))
            disks, fpath = plugin._build_domain_new_xml(vm, {'/dev/old': volume})
            assert 'vda' in list(disks)
            with open(fpath, 'r', encoding='utf-8') as f:
                updated = f.read()
            assert 'type="block"' in updated
            assert 'source dev="/dev/new"' in updated
            dev, disk_xml_path = plugin._build_dest_disk_xml(vm, '/dev/old', volume)
            assert dev == 'vda'
            with open(disk_xml_path, 'r', encoding='utf-8') as f:
                disk_xml = f.read()
            assert disk_xml == 'disk-xml'


@pytest.mark.kvmagent
class TestUsbLibvirtHelpers:
    def test_attach_and_detach_usb_by_libvirt(self):
        import importlib
        from zstacklib.utils import linux

        def _identity_retry(*_args, **_kwargs):
            def _decorator(func):
                return func
            return _decorator

        linux.retry = _identity_retry
        reloaded = importlib.reload(vm_plugin)
        reloaded.http = http
        reloaded.jsonobject = jsonobject
        plugin = reloaded.VmPlugin.__new__(reloaded.VmPlugin)
        plugin.config = {}
        vm = MagicMock()
        vm.domain.XMLDesc = MagicMock(return_value=(
            "<domain><devices>"
            "<hostdev type='usb'><address type='usb' bus='0' port='1'/></hostdev>"
            "<redirdev type='tcp'><address type='usb' bus='0' port='2'/></redirdev>"
            "</devices></domain>"
        ))
        vm.domain.attachDeviceFlags = MagicMock()
        vm.domain.detachDeviceFlags = MagicMock()
        reloaded.get_vm_by_uuid = MagicMock(return_value=vm)
        cmd = MagicMock(
            vmUuid='vm-uuid',
            attachType='PassThrough',
            idVendor='1d6b',
            idProduct='0002',
            busNum='001',
            devNum='002',
            vmBusNum=0,
            ip='127.0.0.1',
            port=1234,
        )
        ok, err = plugin._attach_usb_by_libvirt(cmd)
        assert ok is True
        assert err is None
        assert vm.domain.attachDeviceFlags.called

        class _LibvirtError(Exception):
            pass

        reloaded.libvirt.libvirtError = _LibvirtError
        vm.domain.detachDeviceFlags = MagicMock(side_effect=_LibvirtError('redirdev was not found'))
        cmd.attachType = 'Redirect'
        assert plugin._detach_usb_by_libvirt(cmd) is True


@pytest.mark.kvmagent
class TestVmAttachDetachDataVolume:
    def _identity_retry(self, *_args, **_kwargs):
        def _decorator(func):
            return func
        return _decorator

    def test_attach_data_volume_builds_xml_with_qos_and_iothread(self):
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.uuid = 'vm-uuid'
        vm.domain = MagicMock()
        vm.domain.attachDeviceFlags = MagicMock()
        vm.domain_xmlobject = MagicMock()
        vm.domain_xmlobject.os.type.machine_ = 'q35'

        volume = jsonobject.loads(json.dumps({
            'deviceId': 1,
            'deviceType': 'file',
            'installPath': '/path/data.qcow2',
            'cacheMode': 'none',
            'useVirtio': True,
            'useVirtioSCSI': True,
            'volumeUuid': 'vol-data',
            'wwn': 'wwn-data',
            'shareable': True,
            'multiQueues': 2,
            'ioThreadId': 2,
            'ioThreadPin': '0-3',
        }))

        addons = jsonobject.loads(json.dumps({
            'NativeAio': False,
            'VolumeQos': {
                'vol-data': {
                    'readBandwidth': 1024,
                    'writeBandwidth': 2048,
                    'totalBandwidth': 3072,
                    'readIOPS': 100,
                    'writeIOPS': 200,
                    'totalIOPS': 300,
                }
            },
            'attachedDataVolumes': [],
        }))

        vm_plugin.linux.get_img_fmt = MagicMock(return_value='qcow2')
        vm_plugin.linux.retry = self._identity_retry
        vm_plugin.linux.wait_callback_success = MagicMock(return_value=True)
        vm_plugin.VmPlugin.get_iothread_info = MagicMock(return_value=[('1', '0-3')])
        vm_plugin.VmPlugin.add_io_thread = MagicMock(return_value=None)
        vm_plugin.VmPlugin.pin_io_thread = MagicMock(return_value=None)
        vm_plugin.VmPlugin.add_scsi_controller = MagicMock(return_value=1)
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=MagicMock(get_occupied_disk_address_units=MagicMock(return_value=[0])))

        def _e_with_text(parent, tag, value=None, attrib=None, usenamesapce=False):
            _ = usenamesapce
            if attrib is None:
                attrib = {}
            attrib = {k: str(v) for k, v in attrib.items()}
            elem = vm_plugin.etree.SubElement(parent, tag, attrib)
            if value:
                elem.text = str(value)
            return elem

        orig_tostring = vm_plugin.etree.tostring
        with patch.object(vm_plugin, 'e', side_effect=_e_with_text), \
                patch.object(vm_plugin.etree, 'tostring', side_effect=orig_tostring):
            vm._attach_data_volume(volume, addons)

        assert vm.domain.attachDeviceFlags.called
        xml = vm.domain.attachDeviceFlags.call_args[0][0]
        assert 'iotune' in xml
        assert 'read_bytes_sec' in xml
        assert 'write_iops_sec' in xml
        assert 'serial' in xml

    def test_detach_data_volume_logs_out_iscsi(self):
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.uuid = 'vm-uuid'
        vm.domain = MagicMock()
        vm.domain.detachDeviceFlags = MagicMock()
        vm.domain_xml = (
            "<domain><devices>"
            "<disk type='block' device='disk'>"
            "<driver name='qemu' type='raw'/>"
            "<source dev='/dev/iscsi/vol-uuid'/>"
            "<target dev='vdb' bus='virtio'/>"
            "</disk>"
            "</devices></domain>"
        )
        vm.domain_xmlobject = vm_plugin.xmlobject.loads(vm.domain_xml)

        volume = jsonobject.loads(json.dumps({
            'deviceId': 1,
            'deviceType': 'iscsi',
            'installPath': 'iscsi://127.0.0.1:3260/iqn/1',
            'volumeUuid': 'vol-uuid',
            'useVirtio': False,
        }))

        vm_plugin.linux.retry = self._identity_retry
        vm_plugin.linux.wait_callback_success = MagicMock(return_value=True)
        vm_plugin.is_libvirt_support_blockdev = MagicMock(return_value=True)
        vm_plugin.BlkIscsi.logout_portal = MagicMock()

        vm._get_target_disk = MagicMock(return_value=(MagicMock(source=MagicMock(dev_='/dev/iscsi/vol-uuid')), 'vdb'))

        vm_plugin.Vm.timeout_detached_vol.add(volume.installPath + '-' + vm.uuid)
        vm._detach_data_volume(volume)

        assert vm.domain.detachDeviceFlags.called
        vm_plugin.BlkIscsi.logout_portal.assert_called_once_with('/dev/iscsi/vol-uuid')
        assert volume.installPath + '-' + vm.uuid not in vm_plugin.Vm.timeout_detached_vol

    def test_detach_data_volume_accepts_completed_async_unplug(self, monkeypatch):
        class _LibvirtError(Exception):
            pass

        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.uuid = 'vm-uuid'
        vm.domain = MagicMock()
        vm.domain.detachDeviceFlags = MagicMock(side_effect=_LibvirtError(
            "internal error: unable to execute QEMU command 'device_del': "
            "Hot-unplug failed: guest is busy (power indicator blinking)"
        ))

        target_disk = MagicMock(source=MagicMock(dev_='/path/data.qcow2'))
        target_disk.dump = MagicMock(return_value=(
            "<disk type='file' device='disk'>"
            "<source file='/path/data.qcow2'/>"
            "<target dev='vdb' bus='virtio'/>"
            "</disk>"
        ))

        volume = jsonobject.loads(json.dumps({
            'deviceId': 1,
            'deviceType': 'file',
            'installPath': '/path/data.qcow2',
            'volumeUuid': 'vol-uuid',
            'useVirtio': True,
        }))

        vm._get_target_disk = MagicMock(side_effect=[
            (target_disk, 'vdb'),
            (target_disk, 'vdb'),
            (None, None),
        ])
        record = volume.installPath + '-' + vm.uuid
        vm_plugin.Vm.timeout_detached_vol.discard(record)

        monkeypatch.setattr(vm_plugin.libvirt, 'libvirtError', _LibvirtError)
        monkeypatch.setattr(vm_plugin.linux, 'retry', self._identity_retry)
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', MagicMock(return_value=vm))
        monkeypatch.setattr(vm_plugin, 'is_libvirt_support_blockdev', MagicMock(return_value=True))

        try:
            vm._detach_data_volume(volume)
        finally:
            vm_plugin.Vm.timeout_detached_vol.discard(record)

        assert vm.domain.detachDeviceFlags.called
        assert record not in vm_plugin.Vm.timeout_detached_vol


@pytest.mark.kvmagent
class TestTakeVolumeSnapshotOnlineHandler:
    def test_take_volume_snapshot_online_running_vm(self):
        plugin = _make_vm_plugin()
        vm = MagicMock()
        vm.state = vm_plugin.Vm.VM_STATE_RUNNING
        vm.VM_STATE_RUNNING = vm_plugin.Vm.VM_STATE_RUNNING
        vm.VM_STATE_PAUSED = vm_plugin.Vm.VM_STATE_PAUSED
        vm.take_volume_snapshot = MagicMock(return_value=('/path/snap', '/path/new'))
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=vm)
        cmd = MagicMock(
            vmUuid='vm-uuid',
            volumeUuid='vol-uuid',
            volume=MagicMock(deviceId=0),
            installPath='/path/snap',
            volumeInstallPath='/path/vol',
            newVolumeInstallPath='/path/new',
            fullSnapshot=False,
            online=True,
            isBaremetal2InstanceOnlineSnapshot=False,
        )
        vm_plugin.Vm.SNAPSHOT_VM_STATE_DICT = {
            vm_plugin.LIVE_SNAPSHOT: (vm_plugin.Vm.VM_STATE_RUNNING,),
            vm_plugin.OFFLINE_SNAPSHOT: (vm_plugin.Vm.VM_STATE_SHUTDOWN,),
        }
        vm_plugin.Vm.ensure_no_internal_snapshot = MagicMock()
        vm_plugin.linux.sync_file = MagicMock()
        vm_plugin.VmPlugin._get_snapshot_size = MagicMock(return_value=321)
        vm_plugin.touchQmpSocketWhenExists = MagicMock()

        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd), \
                patch.object(vm_plugin.jsonobject, 'dumps',
                             side_effect=lambda obj: json.dumps(obj.__dict__)):
            req = _make_req({})
            result = plugin.take_volume_snapshot(req)
            rsp = json.loads(result)

        assert rsp['success'] is True
        assert rsp['size'] == 321
        vm.take_volume_snapshot.assert_called_once_with(cmd, cmd.volume, cmd.installPath, cmd.fullSnapshot)


@pytest.mark.kvmagent
class TestVmDiskHelpers:
    def test_cbt_cbd_path_uses_existing_path_conversion(self):
        plugin = _make_vm_plugin()
        path = 'cbd:pool_physical/pool/volume'
        configured_path = path + '_zbs_:/etc/zbs/client.conf'

        with patch.object(vm_plugin, 'get_volume_actual_installpath', return_value=configured_path) as get_actual_path:
            assert plugin.get_cbt_volume_actual_install_path(path) == configured_path
            assert vm_plugin.make_cbd_conf(path) == configured_path[len(vm_plugin.PROTOCOL_CBD_PREFIX):]
            get_actual_path.assert_called_once_with(path)

    def test_get_all_disk_backing_chain_parses_xml(self):
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.domain_xml = (
            "<domain><devices>"
            "<disk type='file' device='disk'>"
            "<source file='/tmp/pull4.qcow2'/>"
            "<backingStore type='file'>"
            "<source file='/tmp/pull3.qcow2'/>"
            "<backingStore type='file'>"
            "<source file='/tmp/pull2.qcow2'/>"
            "<backingStore/>"
            "</backingStore>"
            "</backingStore>"
            "<target dev='vda' bus='virtio'/>"
            "</disk>"
            "</devices></domain>"
        )
        orig_tostring = vm_plugin.etree.tostring
        with patch.object(vm_plugin.etree, 'tostring', side_effect=lambda elem, **kw: orig_tostring(elem).decode()):
            chains = vm.get_all_disk_backing_chain()
        assert chains == [['/tmp/pull4.qcow2', '/tmp/pull3.qcow2', '/tmp/pull2.qcow2']]

    def test_get_source_file_and_index(self):
        disk = MagicMock()
        disk.type_ = 'file'
        disk.source.file__ = True
        disk.source.file_ = '/tmp/vol.qcow2'
        disk.source.index__ = True
        disk.source.index_ = '2'
        assert vm_plugin.VmPlugin.get_source_file_by_disk(disk) == '/tmp/vol.qcow2'
        assert vm_plugin.VmPlugin.get_source_index_by_disk(disk) == '2'


@pytest.mark.kvmagent
class TestVmMigrateBitmapChecks:
    def test_is_vm_migrate_without_dirty_bitmap_returns_true_when_qemu_missing(self):
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.uuid = 'vm-uuid'
        vm.domain_xmlobject = MagicMock()
        vm.domain_xmlobject.devices.get_child_node_as_list = MagicMock(return_value=[])
        vm_plugin.qemu.get_running_version = MagicMock(return_value='')
        vm_plugin.is_qemu_support_migrate_with_bitmap = MagicMock(return_value=False)
        vm_plugin.linux.get_libvirt_version = MagicMock(return_value='8.0.0')
        vm_plugin.is_libvirt_support_migrate_with_bitmap = MagicMock(return_value=True)
        vm_plugin.qmp.execute_qmp_command = MagicMock(return_value=[{'name': 'node'}])
        vm_plugin.linux.find_process_by_cmdline = MagicMock(return_value=None)

        assert vm._is_vm_migrate_without_dirty_bitmap() is True


@pytest.mark.kvmagent
class TestMirrorJobHelpers:
    def test_check_mirror_jobs_sets_caps_when_needed(self):
        vm_plugin.ImageStoreClient = MagicMock(return_value=MagicMock(stop_backup_jobs=MagicMock()))
        vm_plugin.get_vm_migration_caps = MagicMock(return_value=True)
        vm_plugin.qmp.execute_qmp_command = MagicMock()

        vm_plugin.check_mirror_jobs('vm-uuid', True)

        vm_plugin.qmp.execute_qmp_command.assert_called_once()


@pytest.mark.kvmagent
class TestLiveVolumeSnapshots:
    def _identity_retry(self, *_args, **_kwargs):
        def _decorator(func):
            return func
        return _decorator

    def test_take_live_volumes_delta_snapshots_success(self):
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.uuid = 'vm-uuid'
        vm.domain = MagicMock()
        vm.domain.snapshotCreateXML = MagicMock()
        vm.refresh = MagicMock()
        vm.rollback_memory_snapshot = MagicMock()
        vm.dump_vm_xml_to_log = MagicMock()
        vm.domain_xmlobject = MagicMock()
        vm.domain_xmlobject.devices.get_child_node_as_list = MagicMock(return_value=[])

        volume = jsonobject.loads(json.dumps({
            'deviceId': 0,
            'deviceType': 'file',
            'installPath': '/path/root.qcow2',
        }))
        vs_struct = MagicMock(
            live=True,
            full=False,
            memory=False,
            installPath='/path/snap1',
            volume=volume,
            volumeUuid='vol-1',
        )

        vm._get_target_disk = MagicMock(return_value=(MagicMock(type_='file', target=MagicMock(dev_='vda')), 'vda'))
        vm_plugin.VmPlugin.get_source_file_by_disk = MagicMock(return_value='/path/root.qcow2')
        vm_plugin.VmPlugin._get_snapshot_size = MagicMock(return_value=100)
        vm_plugin.VmPlugin.active_volume_if_need = MagicMock()
        vm_plugin.linux.retry = self._identity_retry
        vm_plugin.linux.wait_callback_success = MagicMock(return_value=True)

        with patch('os.path.exists', return_value=True):
            result = vm.take_live_volumes_delta_snapshots([vs_struct])

        assert len(result) == 1
        assert result[0].installPath == '/path/snap1'


@pytest.mark.kvmagent
class TestBaremetalOnlineSnapshotHandler:
    def test_take_volume_snapshot_bm_online_rollback(self):
        plugin = _make_vm_plugin()
        cmd = MagicMock(
            vmUuid='vm-uuid',
            volumeUuid='vol-uuid',
            volume=MagicMock(deviceId=0),
            installPath='/path/snap',
            volumeInstallPath='/path/vol',
            newVolumeInstallPath='/path/new',
            fullSnapshot=False,
            online=True,
            isBaremetal2InstanceOnlineSnapshot=True,
        )
        vm_plugin.Vm.ensure_no_internal_snapshot = MagicMock()
        vm_plugin.bm_utils.NamedLock = MagicMock()
        vm_plugin.BmV2GwAgent.pre_take_volume_snapshot = MagicMock(return_value=('src', 'dst'))
        vm_plugin.BmV2GwAgent.rollback_volume_snapshot = MagicMock()
        vm_plugin.linux.qcow2_clone_with_cmd = MagicMock(side_effect=Exception('clone failed'))
        vm_plugin.VmPlugin._get_snapshot_size = MagicMock(return_value=1)
        vm_plugin.linux.sync_file = MagicMock()

        with patch.object(vm_plugin.jsonobject, 'loads', return_value=cmd), \
                patch.object(vm_plugin.jsonobject, 'dumps',
                             side_effect=lambda obj: json.dumps(obj.__dict__)):
            req = _make_req({})
            result = plugin.take_volume_snapshot(req)
            rsp = json.loads(result)

        assert rsp['success'] is False
        vm_plugin.BmV2GwAgent.rollback_volume_snapshot.assert_called_once()

@pytest.mark.kvmagent
class TestVmAttachVolumeVariants:
    def _identity_retry(self, *_args, **_kwargs):
        def _decorator(func):
            return func
        return _decorator

    def test_attach_data_volume_multiple_device_types(self):
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.uuid = 'vm-uuid'
        vm.domain = MagicMock()
        vm.domain.attachDeviceFlags = MagicMock()
        vm.domain_xmlobject = MagicMock()
        vm.domain_xmlobject.os.type.machine_ = 'q35'
        vm.domain_xmlobject.has_element = MagicMock(return_value=True)
        vm.domain_xmlobject.memoryBacking = MagicMock()
        vm.domain_xmlobject.memoryBacking.has_element = MagicMock(return_value=True)
        vm.domain_xmlobject.memoryBacking.access.mode_ = 'shared'

        vm_plugin.linux.get_img_fmt = MagicMock(return_value='qcow2')
        vm_plugin.linux.retry = self._identity_retry
        vm_plugin.linux.wait_callback_success = MagicMock(return_value=True)
        vm_plugin.get_vm_by_uuid = MagicMock(return_value=MagicMock(get_occupied_disk_address_units=MagicMock(return_value=[])))
        vm_plugin.get_sgio_value = MagicMock(return_value='filtered')

        def _e_with_text(parent, tag, value=None, attrib=None, usenamesapce=False):
            _ = usenamesapce
            if attrib is None:
                attrib = {}
            attrib = {k: str(v) for k, v in attrib.items()}
            elem = vm_plugin.etree.SubElement(parent, tag, attrib)
            if value:
                elem.text = str(value)
            return elem

        orig_tostring = vm_plugin.etree.tostring
        with patch.object(vm_plugin, 'e', side_effect=_e_with_text), \
                patch.object(vm_plugin.etree, 'tostring', side_effect=orig_tostring), \
                patch('os.path.exists', return_value=True):
            volumes = [
                {
                    'deviceId': 1,
                    'deviceType': 'ceph',
                    'installPath': 'ceph://pool/vol1',
                    'useVirtio': False,
                    'useVirtioSCSI': False,
                    'volumeUuid': 'vol-ceph-1',
                    'secretUuid': 'sec-1',
                    'monInfo': [{'hostname': '10.0.0.2', 'port': 6789}],
                },
                {
                    'deviceId': 2,
                    'deviceType': 'ceph',
                    'installPath': 'ceph://pool/vol2',
                    'useVirtio': True,
                    'useVirtioSCSI': True,
                    'volumeUuid': 'vol-ceph-2',
                    'secretUuid': 'sec-2',
                    'monInfo': [{'hostname': '10.0.0.3', 'port': 6789}],
                    'wwn': 'wwn-ceph-2',
                },
                {
                    'deviceId': 3,
                    'deviceType': 'block',
                    'installPath': '/dev/sdb',
                    'useVirtio': True,
                    'useVirtioSCSI': False,
                    'volumeUuid': 'vol-block',
                    'cacheMode': 'none',
                },
                {
                    'deviceId': 4,
                    'deviceType': 'cbd',
                    'installPath': 'cbd://pool/vol4',
                    'useVirtio': True,
                    'useVirtioSCSI': False,
                    'volumeUuid': 'vol-cbd',
                    'physicalBlockSize': 4096,
                },
                {
                    'deviceId': 5,
                    'deviceType': 'vhost',
                    'installPath': '/var/run/vhost.sock',
                    'useVirtio': True,
                    'useVirtioSCSI': False,
                    'volumeUuid': 'vol-vhost',
                    'format': 'raw',
                },
                {
                    'deviceId': 6,
                    'deviceType': 'iscsi',
                    'installPath': 'iscsi://127.0.0.1:3260/iqn.2004-01.example/0',
                    'useVirtio': True,
                    'volumeUuid': 'vol-iscsi-virtio',
                    'chapUsername': None,
                    'chapPassword': None,
                },
                {
                    'deviceId': 7,
                    'deviceType': 'iscsi',
                    'installPath': 'iscsi://127.0.0.1:3260/iqn.2004-02.example/0',
                    'useVirtio': False,
                    'volumeUuid': 'vol-iscsi-blk',
                    'chapUsername': None,
                    'chapPassword': None,
                },
                {
                    'deviceId': 8,
                    'deviceType': 'scsilun',
                    'installPath': '/dev/sg1',
                    'useVirtio': True,
                    'useVirtioSCSI': True,
                    'volumeUuid': 'vol-scsilun',
                },
            ]

            addons = jsonobject.loads(json.dumps({'NativeAio': False, 'VolumeQos': None, 'attachedDataVolumes': []}))
            addons.__getitem__ = lambda _self, _key: False
            for vol in volumes:
                volume = jsonobject.loads(json.dumps(vol))
                volume.deviceId = vol['deviceId']
                volume.deviceType = vol['deviceType']
                vm._attach_data_volume(volume, addons)
