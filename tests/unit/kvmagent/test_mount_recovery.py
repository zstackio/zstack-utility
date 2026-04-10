# -*- coding: utf-8 -*-
# Copyright (c) 2025, ZStack, Inc.
# ZSTAC-83157: Unit tests for JuiceFS mount point recovery

"""
Tests for mount recovery features:
- Registry persistence (_load/_save/_write)
- Mount health check (_check_mount_health)
- Remount logic (remount_model_center)
- Watchdog with consecutive failure threshold
- On-demand recovery in virtiofs attach flow
- Concurrency safety (no deadlock, no leaked state)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import pytest
from unittest.mock import patch, MagicMock, call

# Ensure jsonobject is available as top-level module
import zstacklib.utils.jsonobject as _jo
sys.modules['jsonobject'] = _jo

from zstacklib.utils import http

from kvmagent.plugins import host_model_mount_plugin
from kvmagent.plugins import virtiofs_plugin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_module_state():
    """Reset module-level mutable state between tests."""
    host_model_mount_plugin._health_failures.clear()
    host_model_mount_plugin._recovering.clear()
    host_model_mount_plugin._recovery_events.clear()
    host_model_mount_plugin._watchdog = None


def _make_req(body_dict=None):
    """Build a request dict in the format handlers expect."""
    body = json.dumps(body_dict or {})
    return {
        http.REQUEST_BODY: body,
        http.REQUEST_HEADER: {},
    }


def _make_plugin():
    """Create a HostModelMountPlugin instance without calling __init__."""
    return host_model_mount_plugin.HostModelMountPlugin.__new__(
        host_model_mount_plugin.HostModelMountPlugin
    )


SAMPLE_MC_UUID = "2cc1f4d6-b801-4b44-912f-92bb242e9675"
SAMPLE_STORAGE_URL = "redis://:secret123@redis-host:6379/0"
SAMPLE_MOUNT_POINT = "/opt/zstack/models/%s" % SAMPLE_MC_UUID

# Short module path alias for patch targets
_MOD = 'kvmagent.plugins.host_model_mount_plugin'
_SHELL = _MOD + '.shell.ShellCmd'


# ---------------------------------------------------------------------------
# Test Registry Persistence
# ---------------------------------------------------------------------------

class TestMountRegistry:
    """Tests for _load_mount_registry / _save_mount_registry_entry / _write_registry."""

    def setup_method(self):
        _reset_module_state()

    @patch('os.path.exists')
    def test_load_empty_registry_when_file_missing(self, mock_exists):
        """If registry file does not exist, return empty dict."""
        mock_exists.return_value = False
        registry = host_model_mount_plugin._load_mount_registry()
        assert registry == {}

    @patch('os.path.exists')
    def test_load_registry_handles_corrupt_json(self, mock_exists):
        """Corrupt JSON file should return empty dict, not raise."""
        mock_exists.return_value = True
        corrupt_json = "not valid json{"
        mock_file = MagicMock()
        mock_file.read.return_value = corrupt_json
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        with patch('builtins.open', return_value=mock_file):
            registry = host_model_mount_plugin._load_mount_registry()
            assert registry == {}

    @patch(_MOD + '._load_mount_registry', return_value={})
    @patch(_MOD + '._write_registry')
    @patch(_MOD + '.ensure_mount_base_dir')
    def test_save_entry_creates_new_registry(self, mock_ensure, mock_write, mock_load):
        """Saving first entry triggers write via _write_registry."""
        host_model_mount_plugin._save_mount_registry_entry(
            SAMPLE_MC_UUID, SAMPLE_STORAGE_URL, SAMPLE_MOUNT_POINT)
        mock_write.assert_called_once()
        written = mock_write.call_args[0][0]
        assert SAMPLE_MC_UUID in written

    @patch(_MOD + '._load_mount_registry')
    @patch(_MOD + '._write_registry')
    @patch(_MOD + '.ensure_mount_base_dir')
    def test_save_entry_preserves_existing_entries(self, mock_ensure, mock_write, mock_load):
        """Saving a new entry should preserve already existing entries."""
        existing = {
            "other-uuid": {
                "storageUrl": "redis://other:6379/0",
                "mountPoint": "/opt/zstack/models/other-uuid"
            }
        }
        mock_load.return_value = dict(existing)

        written_registries = []
        mock_write.side_effect = lambda reg: written_registries.append(dict(reg))

        host_model_mount_plugin._save_mount_registry_entry(
            SAMPLE_MC_UUID, SAMPLE_STORAGE_URL, SAMPLE_MOUNT_POINT)

        assert len(written_registries) == 1
        written = written_registries[0]
        # Existing entry must be preserved
        assert "other-uuid" in written
        assert written["other-uuid"]["storageUrl"] == "redis://other:6379/0"
        # New entry must be added
        assert SAMPLE_MC_UUID in written
        assert written[SAMPLE_MC_UUID]["storageUrl"] == SAMPLE_STORAGE_URL

    def test_save_entry_thread_safety(self):
        """Concurrent _save_mount_registry_entry calls don't lose data.

        Uses a shared in-memory dict so threads actually contend on the same
        data, verifying the lock prevents lost updates.
        """
        shared_registry = {}

        with patch(_MOD + '._load_mount_registry', side_effect=lambda: dict(shared_registry)), \
             patch(_MOD + '._write_registry', side_effect=lambda reg: shared_registry.update(reg)), \
             patch(_MOD + '.ensure_mount_base_dir'):

            def do_save(entry_id):
                host_model_mount_plugin._save_mount_registry_entry(
                    "uuid-%d" % entry_id,
                    "redis://host:6379/%d" % entry_id,
                    "/opt/zstack/models/uuid-%d" % entry_id,
                )

            threads = [threading.Thread(target=do_save, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

        # All 5 entries must be present in the shared registry
        assert len(shared_registry) == 5
        for i in range(5):
            key = "uuid-%d" % i
            assert key in shared_registry
            assert shared_registry[key]["storageUrl"] == "redis://host:6379/%d" % i
            assert shared_registry[key]["mountPoint"] == "/opt/zstack/models/uuid-%d" % i


# ---------------------------------------------------------------------------
# Test Mount Health Check
# ---------------------------------------------------------------------------

class TestCheckMountHealth:
    """Tests for _check_mount_health() dual verification."""

    def setup_method(self):
        _reset_module_state()

    @patch('os.path.ismount')
    def test_not_a_mount_point(self, mock_ismount):
        """If path is not a mount point, return False immediately."""
        mock_ismount.return_value = False
        assert host_model_mount_plugin._check_mount_health("/some/path") is False

    @patch(_SHELL)
    @patch('os.path.ismount')
    def test_healthy_mount(self, mock_ismount, mock_shell_cls):
        """Mount point exists and ls succeeds -> healthy."""
        mock_ismount.return_value = True
        mock_cmd = MagicMock()
        mock_cmd.return_code = 0
        mock_shell_cls.return_value = mock_cmd

        assert host_model_mount_plugin._check_mount_health(SAMPLE_MOUNT_POINT) is True

    @patch(_SHELL)
    @patch('os.path.ismount')
    def test_zombie_mount_ls_fails(self, mock_ismount, mock_shell_cls):
        """Mount point in VFS but ls fails (zombie FUSE) -> unhealthy."""
        mock_ismount.return_value = True
        mock_cmd = MagicMock()
        mock_cmd.return_code = 1
        mock_shell_cls.return_value = mock_cmd

        assert host_model_mount_plugin._check_mount_health(SAMPLE_MOUNT_POINT) is False

    @patch(_SHELL)
    @patch('os.path.ismount')
    def test_zombie_mount_ls_timeout(self, mock_ismount, mock_shell_cls):
        """Mount point in VFS but ls times out -> unhealthy.

        Also verifies the command string uses the configured timeout value,
        so a misconfigured timeout won't cause indefinite hangs in production.
        """
        mock_ismount.return_value = True
        mock_cmd = MagicMock()
        mock_cmd.return_code = 124  # timeout exit code
        mock_shell_cls.return_value = mock_cmd

        assert host_model_mount_plugin._check_mount_health(SAMPLE_MOUNT_POINT) is False

        cmd_arg = mock_shell_cls.call_args[0][0]
        assert "timeout %d" % host_model_mount_plugin.MOUNT_CHECK_TIMEOUT_SECS in cmd_arg

    @patch(_SHELL)
    @patch('os.path.ismount')
    def test_ls_raises_exception(self, mock_ismount, mock_shell_cls):
        """ls command raises unexpected exception -> unhealthy (not crash)."""
        mock_ismount.return_value = True
        mock_shell_cls.side_effect = OSError("command not found")

        assert host_model_mount_plugin._check_mount_health(SAMPLE_MOUNT_POINT) is False

    @patch(_SHELL)
    @patch('os.path.ismount')
    def test_health_check_escapes_path(self, mock_ismount, mock_shell_cls):
        """Verify mount point path is shell-escaped to prevent injection."""
        import shlex
        mock_ismount.return_value = True
        mock_cmd = MagicMock()
        mock_cmd.return_code = 0
        mock_shell_cls.return_value = mock_cmd

        malicious_path = "/opt/zstack/models/uuid; rm -rf /"
        host_model_mount_plugin._check_mount_health(malicious_path)

        cmd_arg = mock_shell_cls.call_args[0][0]
        # The raw path with shell metacharacters must not appear unescaped
        assert shlex.quote(malicious_path) in cmd_arg
        # Verify the dangerous semicolon is inside quotes, not a command separator
        assert "; " not in cmd_arg.replace("'%s'" % malicious_path, "").replace('"%s"' % malicious_path, "")


# ---------------------------------------------------------------------------
# Test Remount Logic
# ---------------------------------------------------------------------------

class TestRemountModelCenter:
    """Tests for remount_model_center() recovery function."""

    def setup_method(self):
        _reset_module_state()

    def _mock_registry(self):
        """Return a patch that loads a registry with one sample entry."""
        return patch(_MOD + '._load_mount_registry', return_value={
            SAMPLE_MC_UUID: {
                "storageUrl": SAMPLE_STORAGE_URL,
                "mountPoint": SAMPLE_MOUNT_POINT
            }
        })

    def test_remount_no_registry_entry(self):
        """If model center not in registry, return False."""
        with patch(_MOD + '._load_mount_registry', return_value={}):
            result = host_model_mount_plugin.remount_model_center(SAMPLE_MC_UUID)
        assert result is False

    @patch(_MOD + '._check_mount_health')
    def test_remount_already_healthy(self, mock_health):
        """If mount is already healthy, return True without remounting."""
        mock_health.return_value = True
        with self._mock_registry():
            result = host_model_mount_plugin.remount_model_center(SAMPLE_MC_UUID)
        assert result is True

    @patch(_MOD + '.mount_juicefs')
    @patch(_SHELL)
    @patch('os.path.ismount')
    @patch(_MOD + '._check_mount_health')
    def test_remount_after_umount_success(self, mock_health, mock_ismount,
                                           mock_shell, mock_mount):
        """Unhealthy mount -> umount -> mount_juicefs succeeds -> return True."""
        mock_health.return_value = False
        # ismount returns True initially, then False after umount
        mock_ismount.side_effect = [True, False]

        mock_umount_cmd = MagicMock()
        mock_umount_cmd.return_code = 0
        mock_shell.return_value = mock_umount_cmd

        mock_mount.return_value = (True, None, True)

        with self._mock_registry():
            result = host_model_mount_plugin.remount_model_center(SAMPLE_MC_UUID)
        assert result is True
        mock_mount.assert_called_once_with(SAMPLE_STORAGE_URL, SAMPLE_MOUNT_POINT)

    @patch(_MOD + '.mount_juicefs')
    @patch(_SHELL)
    @patch('os.path.ismount')
    @patch(_MOD + '._check_mount_health')
    def test_remount_lazy_umount_fallback(self, mock_health, mock_ismount,
                                            mock_shell, mock_mount):
        """If regular umount fails, fallback to lazy umount (-l)."""
        mock_health.return_value = False
        # ismount: True initially (enter umount), False after lazy umount succeeds
        mock_ismount.side_effect = [True, False]

        call_count = [0]
        def shell_side_effect(cmd):
            mock_cmd = MagicMock()
            call_count[0] += 1
            mock_cmd.return_code = 1 if call_count[0] == 1 else 0
            return mock_cmd
        mock_shell.side_effect = shell_side_effect
        mock_mount.return_value = (True, None, True)

        with self._mock_registry():
            result = host_model_mount_plugin.remount_model_center(SAMPLE_MC_UUID)
        assert result is True
        calls = mock_shell.call_args_list
        assert len(calls) == 2
        assert "umount -l" in calls[1][0][0]

    @patch(_MOD + '.mount_juicefs')
    @patch('os.path.ismount')
    @patch(_MOD + '._check_mount_health')
    def test_remount_failure_returns_false(self, mock_health, mock_ismount, mock_mount):
        """If remount fails, return False."""
        mock_health.return_value = False
        mock_ismount.return_value = False  # not mounted, skip umount
        mock_mount.return_value = (False, "connection refused", False)

        with self._mock_registry():
            result = host_model_mount_plugin.remount_model_center(SAMPLE_MC_UUID)
        assert result is False

    def test_remount_invalid_registry_entry(self):
        """Registry entry with empty storageUrl or mountPoint -> return False."""
        with patch(_MOD + '._load_mount_registry') as mock_load:
            mock_load.return_value = {
                SAMPLE_MC_UUID: {"storageUrl": "", "mountPoint": SAMPLE_MOUNT_POINT}
            }
            assert host_model_mount_plugin.remount_model_center(SAMPLE_MC_UUID) is False

            mock_load.return_value = {
                SAMPLE_MC_UUID: {"storageUrl": SAMPLE_STORAGE_URL, "mountPoint": ""}
            }
            assert host_model_mount_plugin.remount_model_center(SAMPLE_MC_UUID) is False

    @patch(_MOD + '.mount_juicefs')
    @patch('os.path.ismount')
    @patch(_MOD + '._check_mount_health')
    def test_remount_cleans_up_recovering_on_exception(self, mock_health, mock_ismount, mock_mount):
        """If mount_juicefs raises exception, _recovering set is still cleaned up."""
        mock_health.return_value = False
        mock_ismount.return_value = False
        mock_mount.side_effect = RuntimeError("unexpected error")

        with self._mock_registry():
            result = host_model_mount_plugin.remount_model_center(SAMPLE_MC_UUID)
        assert result is False
        assert SAMPLE_MC_UUID not in host_model_mount_plugin._recovering

    @patch(_MOD + '.mount_juicefs')
    @patch('os.path.ismount')
    @patch(_MOD + '._check_mount_health')
    def test_remount_skips_when_already_recovering(self, mock_health, mock_ismount, mock_mount):
        """If UUID is already in _recovering set, remount returns False without
        calling mount_juicefs. Tests the concurrent-protection logic directly."""
        mock_health.return_value = False
        mock_ismount.return_value = False

        # Simulate UUID already being recovered by another thread
        host_model_mount_plugin._recovering.add(SAMPLE_MC_UUID)

        with self._mock_registry():
            result = host_model_mount_plugin.remount_model_center(SAMPLE_MC_UUID)

        assert result is None
        # mount_juicefs should NOT have been called (another thread handles it)
        mock_mount.assert_not_called()
        # UUID should still be in _recovering (this thread didn't add it, so can't remove it)
        assert SAMPLE_MC_UUID in host_model_mount_plugin._recovering


# ---------------------------------------------------------------------------
# Test Watchdog
# ---------------------------------------------------------------------------

class TestMountWatchdog:
    """Tests for _MountWatchdog health check loop."""

    def setup_method(self):
        _reset_module_state()

    def test_check_all_mounts_healthy_resets_failures(self):
        """Healthy mount resets failure counter to zero."""
        host_model_mount_plugin._health_failures[SAMPLE_MC_UUID] = 2

        with patch(_MOD + '._load_mount_registry') as mock_load, \
             patch(_MOD + '._check_mount_health') as mock_health:
            mock_load.return_value = {
                SAMPLE_MC_UUID: {
                    "storageUrl": SAMPLE_STORAGE_URL,
                    "mountPoint": SAMPLE_MOUNT_POINT
                }
            }
            mock_health.return_value = True

            watchdog = host_model_mount_plugin._MountWatchdog()
            watchdog._check_all_mounts()

        assert SAMPLE_MC_UUID not in host_model_mount_plugin._health_failures

    def test_check_all_mounts_increments_failure_counter(self):
        """Unhealthy mount increments failure counter without triggering recovery."""
        with patch(_MOD + '._load_mount_registry') as mock_load, \
             patch(_MOD + '._check_mount_health') as mock_health, \
             patch(_MOD + '.remount_model_center') as mock_remount:
            mock_load.return_value = {
                SAMPLE_MC_UUID: {
                    "storageUrl": SAMPLE_STORAGE_URL,
                    "mountPoint": SAMPLE_MOUNT_POINT
                }
            }
            mock_health.return_value = False

            watchdog = host_model_mount_plugin._MountWatchdog()
            watchdog._check_all_mounts()

        assert host_model_mount_plugin._health_failures.get(SAMPLE_MC_UUID) == 1
        mock_remount.assert_not_called()

    def test_check_all_mounts_triggers_recovery_at_threshold(self):
        """Consecutive failures reaching threshold triggers remount."""
        with patch(_MOD + '._load_mount_registry') as mock_load, \
             patch(_MOD + '._check_mount_health') as mock_health, \
             patch(_MOD + '.remount_model_center') as mock_remount:
            mock_load.return_value = {
                SAMPLE_MC_UUID: {
                    "storageUrl": SAMPLE_STORAGE_URL,
                    "mountPoint": SAMPLE_MOUNT_POINT
                }
            }
            mock_health.return_value = False
            mock_remount.return_value = True

            threshold = host_model_mount_plugin.MOUNT_UNHEALTHY_THRESHOLD
            host_model_mount_plugin._health_failures[SAMPLE_MC_UUID] = threshold - 1

            watchdog = host_model_mount_plugin._MountWatchdog()
            watchdog._check_all_mounts()

        mock_remount.assert_called_once_with(SAMPLE_MC_UUID)
        assert SAMPLE_MC_UUID not in host_model_mount_plugin._health_failures

    def test_check_all_mounts_recovery_failure_keeps_counter_near_threshold(self):
        """Failed recovery keeps counter near threshold so next cycle retries promptly."""
        with patch(_MOD + '._load_mount_registry') as mock_load, \
             patch(_MOD + '._check_mount_health') as mock_health, \
             patch(_MOD + '.remount_model_center') as mock_remount:
            mock_load.return_value = {
                SAMPLE_MC_UUID: {
                    "storageUrl": SAMPLE_STORAGE_URL,
                    "mountPoint": SAMPLE_MOUNT_POINT
                }
            }
            mock_health.return_value = False
            mock_remount.return_value = False

            threshold = host_model_mount_plugin.MOUNT_UNHEALTHY_THRESHOLD
            host_model_mount_plugin._health_failures[SAMPLE_MC_UUID] = threshold - 1

            watchdog = host_model_mount_plugin._MountWatchdog()
            watchdog._check_all_mounts()

        mock_remount.assert_called_once()
        # Counter set to THRESHOLD-1 so the next watchdog cycle triggers recovery again
        assert host_model_mount_plugin._health_failures.get(SAMPLE_MC_UUID) == threshold - 1

    def test_check_all_mounts_empty_registry(self):
        """Empty registry should not trigger any checks."""
        with patch(_MOD + '._load_mount_registry', return_value={}):
            watchdog = host_model_mount_plugin._MountWatchdog()
            watchdog._check_all_mounts()  # Should not raise

    def test_check_all_mounts_missing_mount_point_in_entry(self):
        """Registry entry with no mountPoint should be skipped."""
        with patch(_MOD + '._load_mount_registry') as mock_load, \
             patch(_MOD + '._check_mount_health') as mock_health:
            mock_load.return_value = {
                SAMPLE_MC_UUID: {"storageUrl": SAMPLE_STORAGE_URL, "mountPoint": ""}
            }

            watchdog = host_model_mount_plugin._MountWatchdog()
            watchdog._check_all_mounts()

        mock_health.assert_not_called()

    def test_transient_failure_does_not_trigger_recovery(self):
        """A single transient failure (then healthy) resets counter, no recovery."""
        with patch(_MOD + '._load_mount_registry') as mock_load, \
             patch(_MOD + '._check_mount_health') as mock_health, \
             patch(_MOD + '.remount_model_center') as mock_remount:
            mock_load.return_value = {
                SAMPLE_MC_UUID: {
                    "storageUrl": SAMPLE_STORAGE_URL,
                    "mountPoint": SAMPLE_MOUNT_POINT
                }
            }

            watchdog = host_model_mount_plugin._MountWatchdog()

            # Cycle 1: unhealthy
            mock_health.return_value = False
            watchdog._check_all_mounts()
            assert host_model_mount_plugin._health_failures.get(SAMPLE_MC_UUID) == 1

            # Cycle 2: back to healthy
            mock_health.return_value = True
            watchdog._check_all_mounts()
            assert SAMPLE_MC_UUID not in host_model_mount_plugin._health_failures

            # Cycle 3: unhealthy again - counter restarts from 1
            mock_health.return_value = False
            watchdog._check_all_mounts()
            assert host_model_mount_plugin._health_failures.get(SAMPLE_MC_UUID) == 1

        mock_remount.assert_not_called()

    def test_watchdog_start_stop(self):
        """Watchdog thread starts and stops cleanly."""
        with patch(_MOD + '._load_mount_registry', return_value={}):
            watchdog = host_model_mount_plugin._MountWatchdog()
            watchdog.start()
            assert watchdog._thread is not None
            assert watchdog._thread.is_alive()

            watchdog.stop()
            watchdog._thread.join(timeout=5)
            assert not watchdog._thread.is_alive()

    def test_watchdog_start_idempotent(self):
        """Calling start() twice does not create duplicate threads."""
        with patch(_MOD + '._load_mount_registry', return_value={}):
            watchdog = host_model_mount_plugin._MountWatchdog()
            watchdog.start()
            thread1 = watchdog._thread
            watchdog.start()  # should be no-op
            thread2 = watchdog._thread
            assert thread1 is thread2
            watchdog.stop()

    def test_watchdog_stop_without_start(self):
        """Calling stop() without start() should not raise."""
        watchdog = host_model_mount_plugin._MountWatchdog()
        watchdog.stop()  # should not raise

    def test_multiple_mounts_independent_counters(self):
        """Multiple mount points maintain independent failure counters."""
        mc1 = "uuid-00000000-0000-0000-0000-000000000001"
        mc2 = "uuid-00000000-0000-0000-0000-000000000002"
        mp1 = "/opt/zstack/models/%s" % mc1
        mp2 = "/opt/zstack/models/%s" % mc2

        def health_side_effect(mp):
            return mp == mp1  # mc1 healthy, mc2 unhealthy

        with patch(_MOD + '._load_mount_registry') as mock_load, \
             patch(_MOD + '._check_mount_health') as mock_health:
            mock_load.return_value = {
                mc1: {"storageUrl": "redis://h1:6379/0", "mountPoint": mp1},
                mc2: {"storageUrl": "redis://h2:6379/0", "mountPoint": mp2},
            }
            mock_health.side_effect = health_side_effect

            watchdog = host_model_mount_plugin._MountWatchdog()
            watchdog._check_all_mounts()

        assert mc1 not in host_model_mount_plugin._health_failures
        assert host_model_mount_plugin._health_failures.get(mc2) == 1


# ---------------------------------------------------------------------------
# Test On-Demand Recovery in Virtiofs Attach
# ---------------------------------------------------------------------------

class TestVerifySourcePathWithRecovery:
    """Tests for _verify_source_path_with_recovery() in virtiofs_plugin."""

    def test_healthy_path_returns_directly(self):
        """Healthy source path passes through without recovery attempt."""
        with patch(_MOD.replace('host_model_mount', 'virtiofs') + '.verify_source_path') as mock_verify:
            mock_verify.return_value = "/opt/zstack/models/uuid/model"
            result = virtiofs_plugin._verify_source_path_with_recovery(
                "/opt/zstack/models/uuid/model")
        assert result == "/opt/zstack/models/uuid/model"

    def test_non_model_path_raises_without_recovery(self):
        """Path outside /opt/zstack/models/ raises original error, no recovery."""
        with patch('kvmagent.plugins.virtiofs_plugin.verify_source_path') as mock_verify, \
             patch('kvmagent.plugins.virtiofs_plugin.remount_model_center') as mock_remount:
            mock_verify.side_effect = Exception("sourcePath[/root/data] does not exist")

            with pytest.raises(Exception, match="/root/data"):
                virtiofs_plugin._verify_source_path_with_recovery("/root/data")

        mock_remount.assert_not_called()

    def test_recovery_success_retries_verify(self):
        """Failed verify -> recovery succeeds -> retry verify succeeds."""
        call_count = [0]
        def verify_side_effect(path):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("sourcePath[%s] does not exist" % path)
            return "/opt/zstack/models/%s/qwen" % SAMPLE_MC_UUID

        with patch('kvmagent.plugins.virtiofs_plugin.verify_source_path') as mock_verify, \
             patch('kvmagent.plugins.virtiofs_plugin.remount_model_center') as mock_remount, \
             patch('time.sleep'):
            mock_verify.side_effect = verify_side_effect
            mock_remount.return_value = True

            result = virtiofs_plugin._verify_source_path_with_recovery(
                "/opt/zstack/models/%s/qwen" % SAMPLE_MC_UUID)

        assert result == "/opt/zstack/models/%s/qwen" % SAMPLE_MC_UUID
        assert mock_verify.call_count == 2

    @patch('time.sleep')
    def test_recovery_failure_raises_original_error(self, mock_sleep):
        """Failed verify -> recovery fails -> original error raised."""
        with patch('kvmagent.plugins.virtiofs_plugin.verify_source_path') as mock_verify, \
             patch('kvmagent.plugins.virtiofs_plugin.remount_model_center') as mock_remount:
            mock_verify.side_effect = Exception("sourcePath[/opt/zstack/models/uuid/model] does not exist")
            mock_remount.return_value = False

            with pytest.raises(Exception, match="does not exist"):
                virtiofs_plugin._verify_source_path_with_recovery(
                    "/opt/zstack/models/%s/model" % SAMPLE_MC_UUID)

    def test_short_path_no_uuid_raises_without_recovery(self):
        """Path like /opt/zstack/models/ (no UUID segment) raises without recovery.

        /opt/zstack/models/ splits to ['', 'opt', 'zstack', 'models', '']
        parts[4] is '' (falsy) → correctly skips recovery.
        """
        with patch('kvmagent.plugins.virtiofs_plugin.verify_source_path') as mock_verify, \
             patch('kvmagent.plugins.virtiofs_plugin.remount_model_center') as mock_remount:
            mock_verify.side_effect = Exception("not accessible")

            with pytest.raises(Exception, match="not accessible"):
                virtiofs_plugin._verify_source_path_with_recovery("/opt/zstack/models/")

        mock_remount.assert_not_called()

    def test_empty_path_raises_without_recovery(self):
        """Empty path raises without recovery attempt."""
        with patch('kvmagent.plugins.virtiofs_plugin.verify_source_path') as mock_verify, \
             patch('kvmagent.plugins.virtiofs_plugin.remount_model_center') as mock_remount:
            mock_verify.side_effect = Exception("sourcePath is required")

            with pytest.raises(Exception, match="sourcePath is required"):
                virtiofs_plugin._verify_source_path_with_recovery("")

        mock_remount.assert_not_called()

    def test_concurrent_recovery_waits_then_succeeds(self):
        """remount returns None → wait_for_recovery → retry verify until success."""
        call_count = [0]
        def verify_side_effect(path):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise Exception("sourcePath[%s] does not exist" % path)
            return "/opt/zstack/models/%s/qwen" % SAMPLE_MC_UUID

        with patch('kvmagent.plugins.virtiofs_plugin.verify_source_path') as mock_verify, \
             patch('kvmagent.plugins.virtiofs_plugin.remount_model_center') as mock_remount, \
             patch('kvmagent.plugins.virtiofs_plugin.wait_for_recovery', return_value=True), \
             patch('time.sleep'):
            mock_verify.side_effect = verify_side_effect
            mock_remount.return_value = None  # another thread is recovering

            result = virtiofs_plugin._verify_source_path_with_recovery(
                "/opt/zstack/models/%s/qwen" % SAMPLE_MC_UUID)

        assert result == "/opt/zstack/models/%s/qwen" % SAMPLE_MC_UUID

    def test_concurrent_recovery_wait_still_fails_raises(self):
        """remount returns None, wait_for_recovery done, verify still fails → raise original error."""
        with patch('kvmagent.plugins.virtiofs_plugin.verify_source_path') as mock_verify, \
             patch('kvmagent.plugins.virtiofs_plugin.remount_model_center') as mock_remount, \
             patch('kvmagent.plugins.virtiofs_plugin.wait_for_recovery', return_value=True), \
             patch('time.sleep'):
            mock_verify.side_effect = Exception("sourcePath[/opt/zstack/models/uuid/model] does not exist")
            mock_remount.return_value = None

            with pytest.raises(Exception, match="does not exist"):
                virtiofs_plugin._verify_source_path_with_recovery(
                    "/opt/zstack/models/%s/model" % SAMPLE_MC_UUID)


# ---------------------------------------------------------------------------
# Test List Filters Hidden Files
# ---------------------------------------------------------------------------

class TestListModelCentersFilters:
    """Tests that list_model_centers skips hidden files (like .registry)."""

    def setup_method(self):
        _reset_module_state()

    @patch('os.path.exists')
    @patch('os.listdir')
    @patch('os.path.ismount')
    def test_hidden_files_excluded(self, mock_ismount, mock_listdir, mock_exists):
        """Hidden files like .registry should not appear in listing."""
        mock_exists.return_value = True
        mock_listdir.return_value = [
            '.registry',
            '.registry.tmp',
            'uuid-1111',
            'uuid-2222',
            '..',
            '.',
        ]
        mock_ismount.return_value = False

        req = _make_req({})
        plugin = _make_plugin()
        result = plugin.list_model_centers(req)
        rsp = json.loads(result)

        assert rsp['success'] is True
        uuids = [m['modelCenterUuid'] for m in rsp['mounts']]
        assert 'uuid-1111' in uuids
        assert 'uuid-2222' in uuids
        assert '.registry' not in uuids
        assert '.registry.tmp' not in uuids
        assert '..' not in uuids
        assert '.' not in uuids


# ---------------------------------------------------------------------------
# Test Plugin Start/Stop Lifecycle
# ---------------------------------------------------------------------------

class TestPluginLifecycle:
    """Tests for plugin start/stop with watchdog."""

    def setup_method(self):
        _reset_module_state()

    @patch(_MOD + '._start_watchdog')
    @patch(_MOD + '.kvmagent.get_http_server')
    def test_start_launches_watchdog(self, mock_http, mock_watchdog):
        """Plugin.start() should call _start_watchdog()."""
        plugin = _make_plugin()
        plugin.start()
        mock_watchdog.assert_called_once()

    @patch(_MOD + '._stop_watchdog')
    def test_stop_stops_watchdog(self, mock_watchdog):
        """Plugin.stop() should call _stop_watchdog()."""
        plugin = _make_plugin()
        plugin.stop()
        mock_watchdog.assert_called_once()
