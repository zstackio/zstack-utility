# -*- coding: utf-8 -*-
import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from xml.etree import ElementTree as ET

import pytest

from zstacklib.utils import http
from kvmagent.plugins import vm_plugin

VM_UUID = '05607bedecba455383b15721cc145c44'
COPY_JOB = {'type': 2, 'cur': 31457280, 'end': 1073741824}


def _fake_reconnect(conn):
    def decorator(func):
        def wrapper(*args, **kwargs):
            return func(conn, *args, **kwargs)
        return wrapper
    return decorator


def _wait_until(callback, callback_data=None, timeout=60, interval=1, ignore_exception_in_callback=False):
    for _ in range(3):
        if callback(callback_data):
            return True
    return False


@pytest.fixture
def libvirt_conn(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(vm_plugin, 'LibvirtAutoReconnect', _fake_reconnect(conn))
    return conn


class TestMemorySnapshotRestore:
    def _vm(self, monkeypatch):
        vm = vm_plugin.Vm.__new__(vm_plugin.Vm)
        vm.uuid = VM_UUID
        vm.domain_xml = '<domain><name>%s</name></domain>' % VM_UUID
        monkeypatch.setattr(vm, '_patch_cpu_xml_from_saved_image', lambda path: None, raising=False)
        return vm

    def test_restored_domain_is_defined_persistent(self, monkeypatch, libvirt_conn):
        vm = self._vm(monkeypatch)

        vm.restore('/memory/snapshot')

        libvirt_conn.restoreFlags.assert_called_once_with('/memory/snapshot', vm.domain_xml)
        libvirt_conn.defineXML.assert_called_once_with(vm.domain_xml)
        calls = [c[0] for c in libvirt_conn.method_calls]
        assert calls.index('restoreFlags') < calls.index('defineXML')

    def test_failed_restore_does_not_define_domain(self, monkeypatch, libvirt_conn):
        vm = self._vm(monkeypatch)
        libvirt_conn.restoreFlags.side_effect = Exception('restore failed')

        with pytest.raises(Exception, match='restore failed'):
            vm.restore('/memory/snapshot')

        libvirt_conn.defineXML.assert_not_called()

    def test_restored_domain_is_destroyed_when_define_fails(self, monkeypatch, libvirt_conn):
        vm = self._vm(monkeypatch)
        libvirt_conn.defineXML.side_effect = Exception('define failed')

        with pytest.raises(Exception, match='define failed'):
            vm.restore('/memory/snapshot')

        libvirt_conn.lookupByName.assert_called_once_with(VM_UUID)
        libvirt_conn.lookupByName.return_value.destroy.assert_called_once_with()

    @pytest.mark.parametrize('saved_models, current_models', [
        (['virtio'], ['ramfb', 'virtio']),
        (['ramfb', 'virtio'], ['ramfb', 'virtio']),
        (['ramfb', 'virtio'], ['virtio']),
    ])
    def test_restore_preserves_saved_video_topology(self, monkeypatch, libvirt_conn,
                                                  saved_models, current_models):
        vm = self._vm(monkeypatch)
        def domain(models):
            root = ET.fromstring('<domain><devices><disk type="file"/></devices></domain>')
            for i, model in enumerate(models):
                video = ET.SubElement(root.find('devices'), 'video')
                ET.SubElement(video, 'model', {'type': model})
                ET.SubElement(video, 'alias', {'name': 'video%s' % i})
            return ET.tostring(root, encoding='unicode')
        vm.domain_xml = domain(current_models)
        libvirt_conn.saveImageGetXMLDesc.return_value = domain(saved_models)

        vm.restore('/memory/snapshot')

        restored_xml = libvirt_conn.restoreFlags.call_args[0][1]
        root = ET.fromstring(restored_xml)
        assert [el.get('type') for el in root.findall('devices/video/model')] == saved_models
        assert [el.get('name') for el in root.findall('devices/video/alias')] == [
            'video%s' % i for i in range(len(saved_models))]
        assert root.find('devices/disk').get('type') == 'file'

    def test_restore_does_not_guess_video_when_saved_xml_unavailable(self, monkeypatch, libvirt_conn):
        vm = self._vm(monkeypatch)
        vm.domain_xml = '<domain><devices><video><model type="virtio"/></video></devices></domain>'
        libvirt_conn.saveImageGetXMLDesc.side_effect = Exception('saved XML unavailable')

        with pytest.raises(Exception, match='saved XML unavailable'):
            vm.restore('/memory/snapshot')

        libvirt_conn.restoreFlags.assert_not_called()


class TestTakeVolumesSnapshotsWithHostFiles:
    @pytest.fixture
    def env(self, monkeypatch):
        events = []
        vm = MagicMock()
        vm.VM_STATE_RUNNING = vm_plugin.Vm.VM_STATE_RUNNING
        vm.VM_STATE_PAUSED = vm_plugin.Vm.VM_STATE_PAUSED
        vm.state = vm_plugin.Vm.VM_STATE_RUNNING

        def pause(*args, **kwargs):
            events.append('pause')
            vm.state = vm_plugin.Vm.VM_STATE_PAUSED

        def resume(*args, **kwargs):
            events.append('resume')
            vm.state = vm_plugin.Vm.VM_STATE_RUNNING

        vm.pause.side_effect = pause
        vm.resume.side_effect = resume
        vm.take_live_volumes_delta_snapshots.side_effect = \
            lambda jobs: events.append('disk-snapshot') or []

        backup = MagicMock(side_effect=lambda jobs: jobs and events.append('backup-host-files'))
        monkeypatch.setattr(vm_plugin.vm_host_file, 'backup_vm_host_files', backup)
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', MagicMock(return_value=vm))
        monkeypatch.setattr(vm_plugin, 'touchQmpSocketWhenExists', MagicMock())
        monkeypatch.setattr(vm_plugin.Vm, 'ensure_no_internal_snapshot', MagicMock())
        monkeypatch.setattr(vm_plugin.Vm, 'ensure_delta_snapshot_not_exceed', MagicMock())
        return SimpleNamespace(vm=vm, events=events, backup=backup)

    @staticmethod
    def _take(memory=False, host_files=True):
        jobs = [{
            'vmInstanceUuid': VM_UUID, 'live': True, 'full': False, 'memory': False,
            'previousInstallPath': '/vol/root.qcow2', 'installPath': '/snap/root.qcow2',
            'newVolumeInstallPath': '/snap/root.qcow2', 'volumeUuid': 'root', 'deviceId': 0,
            'volume': {'installPath': '/vol/root.qcow2'},
        }]
        if memory:
            jobs.append(dict(jobs[0], memory=True, volumeUuid='memory', installPath='/snap/memory'))
        body = {'snapshotJobs': jobs}
        if host_files:
            body['vmHostFileBackupJobs'] = [{
                'srcPath': '/var/lib/libvirt/swtpm/05607bed-ecba-4553-83b1-5721cc145c44/',
                'destPath': '/var/lib/libvirt/swtpm/05607bed-ecba-4553-83b1-5721cc145c44.snapshot-backup',
                'type': 'TpmState',
            }]
        req = {http.REQUEST_BODY: json.dumps(body), http.REQUEST_HEADER: {}}
        plugin = vm_plugin.VmPlugin.__new__(vm_plugin.VmPlugin)
        plugin.config = {}
        return json.loads(plugin.take_volumes_snapshots(req))

    def test_running_vm_is_paused_around_host_file_backup_and_disk_snapshot(self, env):
        rsp = self._take()

        assert rsp['success'] is True
        assert env.events == ['pause', 'backup-host-files', 'disk-snapshot', 'resume']

    def test_vm_is_resumed_when_disk_snapshot_fails(self, env):
        env.vm.take_live_volumes_delta_snapshots.side_effect = vm_plugin.kvmagent.KvmError('snapshot failed')

        rsp = self._take()

        assert rsp['success'] is False
        assert 'snapshot failed' in rsp['error']
        assert env.events == ['pause', 'backup-host-files', 'resume']

    def test_vm_is_resumed_when_host_file_backup_fails(self, env):
        env.backup.side_effect = Exception('backup source does not exist')

        rsp = self._take()

        assert rsp['success'] is False
        assert 'failed to backup vm host files' in rsp['error']
        env.vm.take_live_volumes_delta_snapshots.assert_not_called()
        assert env.events == ['pause', 'resume']

    def test_resume_failure_keeps_successful_snapshot(self, env):
        env.vm.resume.side_effect = vm_plugin.kvmagent.KvmError('failed to resume vm')

        rsp = self._take()

        assert rsp['success'] is True
        env.vm.resume.assert_called_once()

    def test_vm_without_host_files_is_not_paused(self, env):
        rsp = self._take(host_files=False)

        assert rsp['success'] is True
        assert env.events == ['disk-snapshot']

    def test_paused_vm_is_not_resumed(self, env):
        env.vm.state = vm_plugin.Vm.VM_STATE_PAUSED

        rsp = self._take()

        assert rsp['success'] is True
        assert env.events == ['backup-host-files', 'disk-snapshot']

    def test_memory_snapshot_is_not_paused(self, env):
        rsp = self._take(memory=True)

        assert rsp['success'] is True
        assert 'pause' not in env.events


class TestBlockCopyFailureCleanup:
    class _ShellCmd(object):
        return_code = -15
        stderr = ''

        def __init__(self, cmd):
            self.cmd = cmd

        def __call__(self, is_exception=True):
            return ''

    @pytest.fixture
    def env(self, monkeypatch):
        domain = MagicMock()
        domain.blockJobInfo.return_value = {}
        vm = MagicMock(domain=domain)
        vm._get_target_disk_by_path.return_value = (MagicMock(), 'vdb')
        monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', MagicMock(return_value=vm))
        monkeypatch.setattr(vm_plugin, 'thread', MagicMock(), raising=False)
        monkeypatch.setattr(vm_plugin.libvirt, 'VIR_DOMAIN_BLOCK_JOB_TYPE_COPY', 2, raising=False)
        monkeypatch.setattr(vm_plugin.shell, 'ShellCmd', self._ShellCmd)
        monkeypatch.setattr(vm_plugin.linux, 'wait_callback_success', _wait_until)
        monkeypatch.setattr(vm_plugin, 'check_install_path_by_qmp', MagicMock(return_value=False))
        task_spec = SimpleNamespace(bandwidth=16, newVolume=SimpleNamespace(installPath='/local/vdb.qcow2'))
        plugin = vm_plugin.VmPlugin.__new__(vm_plugin.VmPlugin)
        plugin.config = {}
        copy = lambda: plugin._do_block_copy(VM_UUID, 'vdb', '/tmp/vdb.xml', task_spec)
        return SimpleNamespace(domain=domain, copy=copy)

    def test_unfinished_copy_job_is_aborted_without_pivot(self, env):
        jobs = [COPY_JOB, COPY_JOB, {}]
        env.domain.blockJobInfo.side_effect = lambda disk, flags: jobs.pop(0) if jobs else {}

        success, error = env.copy()

        assert success is False
        env.domain.blockJobAbort.assert_called_once_with('vdb', 0)
        assert 'signal 15' in error

    def test_copy_job_left_after_abort_is_reported(self, env):
        env.domain.blockJobInfo.return_value = COPY_JOB

        success, error = env.copy()

        assert success is False
        assert 'signal 15' in error
        assert 'still exists after abort' in error

    def test_other_block_job_is_not_aborted(self, env):
        env.domain.blockJobInfo.return_value = {'type': 3, 'cur': 1, 'end': 2}

        success, _ = env.copy()

        assert success is False
        env.domain.blockJobAbort.assert_not_called()

    def test_pivoted_disk_is_treated_as_success(self, env, monkeypatch):
        monkeypatch.setattr(vm_plugin, 'check_install_path_by_qmp', MagicMock(return_value=True))

        success, error = env.copy()

        assert success is True
        assert error is None
        env.domain.blockJobAbort.assert_not_called()

    def test_failure_without_job_or_pivot_reports_return_code(self, env, monkeypatch):
        monkeypatch.setattr(self._ShellCmd, 'return_code', 1)

        success, error = env.copy()

        assert success is False
        assert 'return code 1' in error
        env.domain.blockJobAbort.assert_not_called()
