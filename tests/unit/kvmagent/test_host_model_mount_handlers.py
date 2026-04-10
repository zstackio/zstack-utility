# -*- coding: utf-8 -*-
# Copyright (c) 2025, ZStack, Inc.
# ZSTAC-83157: Unit tests for kvmagent.plugins.host_model_mount_plugin

"""
Handler-level unit tests for kvmagent.plugins.host_model_mount_plugin.

Tests cover:
- mount_model_center() handler
- list_model_centers() handler
- check_juicefs_installed() function
- _mask_url() function for sensitive URL masking
"""

from __future__ import annotations

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure jsonobject is available as top-level module
import zstacklib.utils.jsonobject as _jo
sys.modules['jsonobject'] = _jo

from zstacklib.utils import http

# Import the module under test
from kvmagent.plugins import host_model_mount_plugin


class TestMaskUrl:
    """Test _mask_url() function for sensitive URL masking."""

    def test_mask_redis_url_with_password(self):
        """Test that Redis URL password is masked."""
        url = "redis://:mysecretpassword@redis-host:6379/0"
        masked = host_model_mount_plugin._mask_url(url)
        assert "mysecretpassword" not in masked
        assert "***" in masked
        assert "redis-host" in masked

    def test_mask_redis_url_with_user_and_password(self):
        """Test that Redis URL with user:password is masked."""
        url = "redis://user:password@redis-host:6379/0"
        masked = host_model_mount_plugin._mask_url(url)
        assert "password" not in masked
        assert "user:***" in masked

    def test_mask_url_without_auth(self):
        """Test that URL without auth info is returned as-is."""
        url = "redis://redis-host:6379/0"
        masked = host_model_mount_plugin._mask_url(url)
        assert masked == url

    def test_mask_url_empty_password(self):
        """Test URL with empty password (redis://:password@...)."""
        url = "redis://:onlypassword@host:6379/0"
        masked = host_model_mount_plugin._mask_url(url)
        assert "onlypassword" not in masked
        assert ":***" in masked

    def test_mask_url_on_exception(self):
        """Test that exception during parsing returns masked string."""
        # This tests the edge case where url parsing fails
        # The function catches exception and returns '***'
        result = host_model_mount_plugin._mask_url(None)
        assert result == "***"


class TestCheckJuicefsInstalled:
    """Test check_juicefs_installed() function."""

    @patch('os.path.isfile')
    @patch('os.access')
    def test_juicefs_found_in_common_path(self, mock_access, mock_isfile):
        """Test that juicefs is found in common installation paths."""
        mock_isfile.return_value = True
        mock_access.return_value = True

        installed, error = host_model_mount_plugin.check_juicefs_installed()
        # Returns path string (truthy) when found, not strictly True
        assert installed is not None and installed  # path is truthy
        assert error is None

    @patch('os.path.isfile')
    def test_juicefs_not_found_anywhere(self, mock_isfile):
        """Test that juicefs not found returns appropriate error."""
        mock_isfile.return_value = False

        with patch('kvmagent.plugins.host_model_mount_plugin.shell.ShellCmd') as mock_shell:
            mock_instance = MagicMock()
            mock_instance.return_code = 1
            mock_shell.return_value = mock_instance

            installed, error = host_model_mount_plugin.check_juicefs_installed()
            assert installed is None  # Returns None when not found
            assert "juicefs binary not found" in error


class TestMountJuicefs:
    """Test mount_juicefs() function."""

    @patch('os.path.ismount')
    @patch('os.makedirs')
    def test_already_mounted(self, mock_makedirs, mock_ismount):
        """Test that if already mounted, returns success with did_mount=False."""
        mock_ismount.return_value = True

        success, error, did_mount = host_model_mount_plugin.mount_juicefs(
            "redis://localhost:6379/0",
            "/opt/zstack/models/test-uuid"
        )
        assert success is True
        assert error is None
        assert did_mount is False  # Already mounted, not a new mount
        # Should not call makedirs if already mounted
        mock_makedirs.assert_not_called()

    @patch('os.path.ismount')
    @patch('os.makedirs')
    @patch('kvmagent.plugins.host_model_mount_plugin.check_juicefs_installed')
    def test_juicefs_not_installed(self, mock_check, mock_makedirs, mock_ismount):
        """Test that juicefs not installed returns error."""
        mock_ismount.return_value = False
        mock_check.return_value = (False, "juicefs binary not found")

        success, error, did_mount = host_model_mount_plugin.mount_juicefs(
            "redis://localhost:6379/0",
            "/opt/zstack/models/test-uuid"
        )
        assert success is False
        assert "juicefs binary not found" in error
        assert did_mount is False

    @patch('os.path.ismount')
    @patch('os.makedirs')
    @patch('kvmagent.plugins.host_model_mount_plugin.check_juicefs_installed')
    @patch('kvmagent.plugins.host_model_mount_plugin.shell.ShellCmd')
    def test_mount_success(self, mock_shell, mock_check, mock_makedirs, mock_ismount):
        """Test successful juicefs mount."""
        mock_ismount.return_value = False
        # check_juicefs_installed returns (path, None) when found
        mock_check.return_value = ("/usr/local/bin/juicefs", None)

        mock_cmd = MagicMock()
        mock_cmd.return_code = 0
        mock_shell.return_value = mock_cmd

        success, error, did_mount = host_model_mount_plugin.mount_juicefs(
            "redis://localhost:6379/0",
            "/opt/zstack/models/test-uuid"
        )
        assert success is True
        assert error is None
        assert did_mount is True  # New mount was performed

        # Verify shell command was called with correct arguments
        mock_shell.assert_called_once()
        call_args = mock_shell.call_args[0][0]
        assert "juicefs mount" in call_args
        assert "--read-only" in call_args
        assert "--subdir models" in call_args

    @patch('os.path.ismount')
    @patch('os.makedirs')
    @patch('kvmagent.plugins.host_model_mount_plugin.check_juicefs_installed')
    @patch('kvmagent.plugins.host_model_mount_plugin.shell.ShellCmd')
    def test_mount_failure(self, mock_shell, mock_check, mock_makedirs, mock_ismount):
        """Test juicefs mount failure."""
        mock_ismount.return_value = False
        # check_juicefs_installed returns (path, None) when found
        mock_check.return_value = ("/usr/local/bin/juicefs", None)

        mock_cmd = MagicMock()
        mock_cmd.return_code = 1
        mock_cmd.stderr = "mount error: connection refused"
        mock_shell.return_value = mock_cmd

        success, error, did_mount = host_model_mount_plugin.mount_juicefs(
            "redis://localhost:6379/0",
            "/opt/zstack/models/test-uuid"
        )
        assert success is False
        assert "connection refused" in error
        assert did_mount is False


@pytest.mark.kvmagent
class TestMountModelCenterHandler:
    """Test mount_model_center() handler."""

    def _make_req(self, body_dict=None):
        """Build a request dict in the format handlers expect."""
        body = json.dumps(body_dict or {})
        return {
            http.REQUEST_BODY: body,
            http.REQUEST_HEADER: {},
        }

    def _make_plugin(self):
        """Create a HostModelMountPlugin instance for testing."""
        plugin = host_model_mount_plugin.HostModelMountPlugin.__new__(
            host_model_mount_plugin.HostModelMountPlugin
        )
        return plugin

    @patch.object(host_model_mount_plugin, 'ensure_mount_base_dir')
    def test_mount_with_non_empty_uuid_accepted(self, mock_ensure_dir):
        """Test that mount with any non-empty UUID is accepted (no format validation)."""
        # UUID format is no longer validated, any non-empty string is accepted
        req = self._make_req({
            'modelCenterUuid': '2cc1f4d6-b801-4b44-912f-92bb242e9675',  # Previously invalid format
            'storageUrl': 'redis://localhost:6379/0',
        })

        plugin = self._make_plugin()

        with patch.object(host_model_mount_plugin, 'mount_juicefs') as mock_mount:
            mock_mount.return_value = (True, None, True)

            result = plugin.mount_model_center(req)
            rsp = json.loads(result)

            # Should succeed because UUID is not empty
            assert rsp.get('success') is True
            # The mount point should use the exact UUID provided
            assert rsp.get('mountPoint') == '/opt/zstack/models/2cc1f4d6-b801-4b44-912f-92bb242e9675'

    def test_mount_with_empty_uuid(self):
        """Test that mount with empty UUID returns error."""
        req = self._make_req({
            'modelCenterUuid': '',
            'storageUrl': 'redis://localhost:6379/0',
        })

        plugin = self._make_plugin()
        result = plugin.mount_model_center(req)
        rsp = json.loads(result)

        assert rsp.get('success') is False
        assert 'invalid modelCenterUuid' in rsp.get('error', '')

    def test_mount_with_none_uuid(self):
        """Test that mount with None UUID returns error."""
        req = self._make_req({
            'modelCenterUuid': None,
            'storageUrl': 'redis://localhost:6379/0',
        })

        plugin = self._make_plugin()
        result = plugin.mount_model_center(req)
        rsp = json.loads(result)

        assert rsp.get('success') is False

    @patch.object(host_model_mount_plugin, 'ensure_mount_base_dir')
    def test_mount_with_valid_uuid_format(self, mock_ensure_dir):
        """Test that mount with any non-empty UUID is accepted."""
        req = self._make_req({
            'modelCenterUuid': '2cc1f4d6b8014b44912f92bb242e9675',
            'storageUrl': 'redis://localhost:6379/0',
        })

        plugin = self._make_plugin()

        with patch.object(host_model_mount_plugin, 'mount_juicefs') as mock_mount:
            mock_mount.return_value = (True, None, True)

            result = plugin.mount_model_center(req)
            rsp = json.loads(result)

            assert rsp.get('success') is True
            assert rsp.get('mountPoint') == '/opt/zstack/models/2cc1f4d6b8014b44912f92bb242e9675'

    @patch('os.path.exists')
    def test_list_model_centers_empty(self, mock_exists):
        """Test listing model centers when none exist."""
        mock_exists.return_value = False

        req = self._make_req({})
        plugin = self._make_plugin()
        result = plugin.list_model_centers(req)
        rsp = json.loads(result)

        assert rsp.get('success') is True
        assert rsp.get('mounts') == []

    @patch('os.path.exists')
    @patch('os.listdir')
    @patch('os.path.ismount')
    def test_list_model_centers_with_mounts(self, mock_ismount, mock_listdir, mock_exists):
        """Test listing model centers with mounted and unmounted entries."""
        mock_exists.return_value = True
        mock_listdir.return_value = ['uuid1', 'uuid2', 'uuid3']
        mock_ismount.side_effect = [True, False, True]  # uuid1 and uuid3 are mounted

        req = self._make_req({})
        plugin = self._make_plugin()
        result = plugin.list_model_centers(req)
        rsp = json.loads(result)

        assert rsp.get('success') is True
        assert len(rsp.get('mounts')) == 3

        # Check mount status
        mounts = {m['modelCenterUuid']: m['isMounted'] for m in rsp.get('mounts')}
        assert mounts['uuid1'] is True
        assert mounts['uuid2'] is False
        assert mounts['uuid3'] is True

    @patch.object(host_model_mount_plugin, 'ensure_mount_base_dir')
    def test_mount_already_mounted_registry_has_entry(self, mock_ensure_dir):
        """Test that did_mount=False with existing registry entry skips update."""
        req = self._make_req({
            'modelCenterUuid': '2cc1f4d6-b801-4b44-912f-92bb242e9675',
            'storageUrl': 'redis://localhost:6379/0',
        })

        plugin = self._make_plugin()

        with patch.object(host_model_mount_plugin, 'mount_juicefs') as mock_mount, \
             patch.object(host_model_mount_plugin, '_load_mount_registry') as mock_load, \
             patch.object(host_model_mount_plugin, '_save_mount_registry_entry') as mock_save:
            mock_mount.return_value = (True, None, False)  # did_mount=False
            mock_load.return_value = {
                '2cc1f4d6-b801-4b44-912f-92bb242e9675': {
                    'storageUrl': 'redis://localhost:6379/0',
                    'mountPoint': '/opt/zstack/models/2cc1f4d6-b801-4b44-912f-92bb242e9675'
                }
            }

            result = plugin.mount_model_center(req)
            rsp = json.loads(result)

            assert rsp.get('success') is True
            # Should NOT save registry since entry already exists
            mock_save.assert_not_called()

    @patch.object(host_model_mount_plugin, 'ensure_mount_base_dir')
    def test_mount_already_mounted_no_registry_matching_source(self, mock_ensure_dir):
        """Test that did_mount=False with no registry entry but matching source saves registry."""
        req = self._make_req({
            'modelCenterUuid': '2cc1f4d6-b801-4b44-912f-92bb242e9675',
            'storageUrl': 'redis://localhost:6379/0',
        })

        plugin = self._make_plugin()

        with patch.object(host_model_mount_plugin, 'mount_juicefs') as mock_mount, \
             patch.object(host_model_mount_plugin, '_load_mount_registry') as mock_load, \
             patch.object(host_model_mount_plugin, '_get_mount_source') as mock_source, \
             patch.object(host_model_mount_plugin, '_save_mount_registry_entry') as mock_save:
            mock_mount.return_value = (True, None, False)  # did_mount=False
            mock_load.return_value = {}  # No registry entry
            mock_source.return_value = 'redis://localhost:6379/0'  # Matching source

            result = plugin.mount_model_center(req)
            rsp = json.loads(result)

            assert rsp.get('success') is True
            # Should save registry since no entry and source matches
            mock_save.assert_called_once()

    @patch.object(host_model_mount_plugin, 'ensure_mount_base_dir')
    def test_mount_already_mounted_no_registry_mismatch_source(self, mock_ensure_dir):
        """Test that did_mount=False with no registry entry and mismatched source skips save."""
        req = self._make_req({
            'modelCenterUuid': '2cc1f4d6-b801-4b44-912f-92bb242e9675',
            'storageUrl': 'redis://localhost:6379/0',
        })

        plugin = self._make_plugin()

        with patch.object(host_model_mount_plugin, 'mount_juicefs') as mock_mount, \
             patch.object(host_model_mount_plugin, '_load_mount_registry') as mock_load, \
             patch.object(host_model_mount_plugin, '_get_mount_source') as mock_source, \
             patch.object(host_model_mount_plugin, '_save_mount_registry_entry') as mock_save:
            mock_mount.return_value = (True, None, False)  # did_mount=False
            mock_load.return_value = {}  # No registry entry
            mock_source.return_value = 'redis://other-host:6379/0'  # Different source

            result = plugin.mount_model_center(req)
            rsp = json.loads(result)

            assert rsp.get('success') is True
            # Should NOT save registry since source doesn't match
            mock_save.assert_not_called()


class TestEnsureMountBaseDir:
    """Test ensure_mount_base_dir() function."""

    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_create_base_dir_if_not_exists(self, mock_makedirs, mock_exists):
        """Test that base directory is created if it doesn't exist."""
        mock_exists.return_value = False

        host_model_mount_plugin.ensure_mount_base_dir()

        mock_makedirs.assert_called_once_with(
            host_model_mount_plugin.MODEL_MOUNT_BASE, exist_ok=True
        )

    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_skip_if_base_dir_exists(self, mock_makedirs, mock_exists):
        """Test that base directory is not created if it already exists."""
        mock_exists.return_value = True

        host_model_mount_plugin.ensure_mount_base_dir()

        mock_makedirs.assert_not_called()
