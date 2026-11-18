import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock
from kvmagent.plugins import ha_plugin


@pytest.mark.parametrize('revoked', [False, True])
def test_fencer_rechecks_rules_after_dispatch_wait_and_keeps_volume_cleanup(monkeypatch, revoked):
    plugin = object.__new__(ha_plugin.HaPlugin)
    result = SimpleNamespace(failed=True, no_way=False, io_timeout=False, error='storage failure')
    checker = MagicMock(fail_if_no_path=False, fired_vgs={})
    checker.get_fencer_fire_cnt.return_value = 0
    checker.get_vg_fencer_cmd.return_value = SimpleNamespace(strategy='Permissive', storageCheckerTimeout=1)
    checker.write_fencer_heartbeat.return_value = {'vg': result}
    plugin.sblk_health_checker = checker
    plugin.fencer_fire_timestamp = {}
    plugin.storage_status = {}
    plugin.report_storage_status = MagicMock()
    plugin.report_self_fencer_triggered = MagicMock()
    changed = [False]
    vm = SimpleNamespace(uuid='vm', pid=12345, volumes=['volume'])
    monkeypatch.setattr(ha_plugin.thread, 'AsyncThread', lambda fn: fn)
    monkeypatch.setattr(ha_plugin, 'not_exec_kill_vm', lambda *args: changed[0] and revoked)
    def dispatch(vms, kill):
        changed[0] = True
        for item in vms:
            kill(item)
    monkeypatch.setattr(ha_plugin, '_run_fencer_vm_kills', dispatch)
    monkeypatch.setattr(ha_plugin.lvm, 'get_running_vm_root_volume_on_vg', lambda _: [vm])
    kill = MagicMock()
    deactivate = MagicMock()
    monkeypatch.setattr(ha_plugin.linux, 'kill_process', kill)
    monkeypatch.setattr(ha_plugin.linux, 'linux_lsof', lambda _: [])
    monkeypatch.setattr(ha_plugin.lvm, 'deactive_lv', deactivate)
    monkeypatch.setattr(ha_plugin.lvm, 'remove_partial_lv_dm', lambda _: None)
    monkeypatch.setattr(ha_plugin.lvm, 'check_vg_status', lambda *args: (True, None))
    monkeypatch.setattr(ha_plugin, 'clean_network_config', MagicMock())
    plugin.do_heartbeat_on_sharedblock(None)
    if revoked:
        kill.assert_not_called()
        plugin.report_self_fencer_triggered.assert_not_called()
    else:
        kill.assert_called_once_with(vm.pid, is_graceful=True)
        plugin.report_self_fencer_triggered.assert_called_once_with(['vg'], vm.uuid)
    deactivate.assert_called_once_with('volume', False)


@pytest.mark.parametrize("failed_index", [0, 1, 3])
def test_thread_start_failure_joins_started_work_and_preserves_all_results(monkeypatch, failed_index):
    vms = list("abcde")
    killed, joined = [], []
    class Handle:
        def __init__(self, vm):
            self.vm = vm
        def join(self):
            joined.append(self.vm)
    def asynchronous(kill):
        def start(vm):
            if vm == vms[failed_index]:
                raise RuntimeError('cannot start new thread')
            kill(vm)
            return Handle(vm)
        return start
    def kill(vm):
        if vm == vms[failed_index]:
            assert joined == vms[:failed_index]
        killed.append(vm)
    monkeypatch.setattr(ha_plugin.thread, 'AsyncThread', asynchronous)
    monkeypatch.setattr(ha_plugin, 'FENCER_KILL_VM_BATCH_SIZE', 2)
    ha_plugin._run_fencer_vm_kills(vms, kill)
    assert killed == vms
    assert joined == vms[:failed_index]


def test_fencer_parallel_dispatch_is_bounded(monkeypatch):
    active, peak, killed = [], [0], []
    class Handle:
        def __init__(self, vm):
            self.vm = vm
        def join(self):
            active.remove(self.vm)
    def asynchronous(kill):
        def start(vm):
            active.append(vm)
            peak[0] = max(peak[0], len(active))
            kill(vm)
            return Handle(vm)
        return start
    monkeypatch.setattr(ha_plugin, 'FENCER_KILL_VM_BATCH_SIZE', 2)
    monkeypatch.setattr(ha_plugin.thread, 'AsyncThread', asynchronous)
    ha_plugin._run_fencer_vm_kills(list(range(5)), killed.append)
    assert peak[0] <= 2
    assert killed == list(range(5)) and active == []
