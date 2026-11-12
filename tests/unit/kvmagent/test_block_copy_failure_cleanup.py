# -*- coding: utf-8 -*-
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from kvmagent.plugins import vm_plugin

VM_UUID = '05607bedecba455383b15721cc145c44'
COPY_JOB = {'type': 2, 'cur': 31457280, 'end': 1073741824}


def _wait_until(callback, callback_data=None, timeout=60, interval=1, ignore_exception_in_callback=False):
    for _ in range(3):
        if callback(callback_data):
            return True
    return False


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
