import pytest
from kvmagent.plugins import ha_plugin


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
