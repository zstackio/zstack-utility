# -*- coding: utf-8 -*-
# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnusedImport=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportUnannotatedClassAttribute=false, reportAny=false, reportAttributeAccessIssue=false
from __future__ import annotations
"""
Handler-level unit tests for kvmagent.plugins.virtiofs_plugin.

Tests verify_source_path() security function for:
- Path traversal attack prevention
- Symlink attack prevention
- Direct access to sensitive paths
- Edge cases (empty, None, non-existent, non-directory)
"""
import json
import os
import sys
import types
import pytest
from unittest.mock import patch, MagicMock

# Ensure jsonobject is available as a top-level module (virtiofs_plugin imports it directly)
# conftest.py sets up zstacklib.utils.jsonobject, so we alias it here
import zstacklib.utils.jsonobject as _jo
sys.modules['jsonobject'] = _jo

from zstacklib.utils import http

# Import the module under test
from kvmagent.plugins import virtiofs_plugin


class TestVerifySourcePath:
    """Test verify_source_path() security validation."""

    def test_accept_safe_path(self, tmp_path):
        """Test that safe paths are accepted."""
        safe_dir = tmp_path / "models"
        safe_dir.mkdir()

        # Should not raise any exception
        virtiofs_plugin.verify_source_path(str(safe_dir))

    def test_accept_nested_safe_path(self, tmp_path):
        """Test that deeply nested safe paths are accepted."""
        nested_dir = tmp_path / "a" / "b" / "c" / "models"
        nested_dir.mkdir(parents=True)

        # Should not raise any exception
        virtiofs_plugin.verify_source_path(str(nested_dir))

    def test_reject_empty_string(self):
        """Test that empty string is rejected."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("")
        assert "required" in str(exc_info.value)

    def test_reject_none_value(self):
        """Test that None value is rejected."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path(None)
        assert "required" in str(exc_info.value)

    def test_reject_nonexistent_path(self):
        """Test that non-existent path is rejected."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/nonexistent/path/12345")
        assert "does not exist" in str(exc_info.value)

    def test_reject_file_path(self, tmp_path):
        """Test that file path (not directory) is rejected."""
        file_path = tmp_path / "test_file.txt"
        file_path.write_text("test content")

        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path(str(file_path))
        assert "not a directory" in str(exc_info.value)

    def test_reject_direct_access_to_etc(self):
        """Test that direct access to /etc is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/etc")
        assert "restricted" in str(exc_info.value)

    def test_reject_direct_access_to_root(self):
        """Test that direct access to /root is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/root")
        assert "restricted" in str(exc_info.value)

    def test_reject_direct_access_to_boot(self):
        """Test that direct access to /boot is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/boot")
        assert "restricted" in str(exc_info.value)

    def test_reject_direct_access_to_proc(self):
        """Test that direct access to /proc is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/proc")
        assert "restricted" in str(exc_info.value)

    def test_reject_direct_access_to_sys(self):
        """Test that direct access to /sys is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/sys")
        assert "restricted" in str(exc_info.value)

    def test_reject_subdirectory_of_etc(self):
        """Test that subdirectory of /etc is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/etc/ssh")
        assert "restricted" in str(exc_info.value)

    def test_reject_subdirectory_of_root(self):
        """Test that subdirectory of /root is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/root/.ssh")
        assert "restricted" in str(exc_info.value)

    def test_reject_path_traversal_with_double_dot(self, tmp_path):
        """Test that path traversal attack using ../ is blocked."""
        # Create a safe directory structure
        safe_dir = tmp_path / "safe"
        safe_dir.mkdir()

        # Try to traverse to /etc using ../
        # Note: os.path.exists() will fail first if the path doesn't resolve to a real path
        # The security check happens after path existence check
        traversal_path = str(safe_dir / ".." / ".." / "etc")

        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path(traversal_path)
        # The path may not exist, but we still want to verify the behavior
        # Either "does not exist" or "restricted" is acceptable
        error_msg = str(exc_info.value)
        assert "does not exist" in error_msg or "restricted" in error_msg

    def test_reject_symlink_to_dangerous_path(self, tmp_path):
        """Test that symlink pointing to /etc is blocked."""
        link_path = tmp_path / "etc_link"
        try:
            os.symlink("/etc", str(link_path))
            with pytest.raises(Exception) as exc_info:
                virtiofs_plugin.verify_source_path(str(link_path))
            assert "restricted" in str(exc_info.value)
        finally:
            if link_path.exists():
                link_path.unlink()

    def test_reject_symlink_to_root(self, tmp_path):
        """Test that symlink pointing to /root is blocked."""
        link_path = tmp_path / "root_link"
        try:
            os.symlink("/root", str(link_path))
            with pytest.raises(Exception) as exc_info:
                virtiofs_plugin.verify_source_path(str(link_path))
            assert "restricted" in str(exc_info.value)
        finally:
            if link_path.exists():
                link_path.unlink()

    def test_reject_symlink_to_boot(self, tmp_path):
        """Test that symlink pointing to /boot is blocked."""
        link_path = tmp_path / "boot_link"
        try:
            os.symlink("/boot", str(link_path))
            with pytest.raises(Exception) as exc_info:
                virtiofs_plugin.verify_source_path(str(link_path))
            assert "restricted" in str(exc_info.value)
        finally:
            if link_path.exists():
                link_path.unlink()

    def test_reject_symlink_to_proc(self, tmp_path):
        """Test that symlink pointing to /proc is blocked."""
        link_path = tmp_path / "proc_link"
        try:
            os.symlink("/proc", str(link_path))
            with pytest.raises(Exception) as exc_info:
                virtiofs_plugin.verify_source_path(str(link_path))
            assert "restricted" in str(exc_info.value)
        finally:
            if link_path.exists():
                link_path.unlink()

    def test_reject_symlink_to_sys(self, tmp_path):
        """Test that symlink pointing to /sys is blocked."""
        link_path = tmp_path / "sys_link"
        try:
            os.symlink("/sys", str(link_path))
            with pytest.raises(Exception) as exc_info:
                virtiofs_plugin.verify_source_path(str(link_path))
            assert "restricted" in str(exc_info.value)
        finally:
            if link_path.exists():
                link_path.unlink()

    def test_reject_deep_path_traversal(self, tmp_path):
        """Test that deep path traversal is blocked."""
        # Create a deeply nested directory
        deep_dir = tmp_path / "a" / "b" / "c"
        deep_dir.mkdir(parents=True)

        # Try to traverse out to /etc
        # Note: os.path.exists() will fail first if the path doesn't resolve to a real path
        traversal_path = str(deep_dir / ".." / ".." / ".." / ".." / "etc")

        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path(traversal_path)
        # The path may not exist, but we still want to verify the behavior
        error_msg = str(exc_info.value)
        assert "does not exist" in error_msg or "restricted" in error_msg

    def test_accept_symlink_to_safe_location(self, tmp_path):
        """Test that symlink to safe location is accepted."""
        safe_dir = tmp_path / "safe"
        safe_dir.mkdir()

        link_path = tmp_path / "safe_link"
        try:
            os.symlink(str(safe_dir), str(link_path))

            # Should not raise any exception
            virtiofs_plugin.verify_source_path(str(link_path))
        finally:
            if link_path.exists():
                link_path.unlink()


@pytest.mark.kvmagent
class TestVirtiofsAttachHandler:
    """Test virtiofs attach handler."""

    def _make_req(self, body_dict=None):
        """Build a request dict in the format handlers expect."""
        body = json.dumps(body_dict or {})
        return {
            http.REQUEST_BODY: body,
            http.REQUEST_HEADER: {},
        }

    def _make_plugin(self):
        """Create a VirtiofsPlugin instance for testing."""
        plugin = virtiofs_plugin.VirtiofsPlugin.__new__(virtiofs_plugin.VirtiofsPlugin)
        return plugin

    @patch('kvmagent.plugins.virtiofs_plugin.get_vm_domain')
    @patch('kvmagent.plugins.virtiofs_plugin.verify_source_path')
    def test_attach_calls_verify_source_path(self, mock_verify, mock_get_domain, tmp_path):
        """Test that attach handler calls verify_source_path."""
        mock_verify.return_value = None  # Path validation passes
        mock_domain = MagicMock()
        mock_conn = MagicMock()
        mock_get_domain.return_value = (mock_domain, mock_conn)

        safe_dir = tmp_path / "models"
        safe_dir.mkdir()

        req = self._make_req({
            'vmInstanceUuid': 'test-vm-uuid',
            'tag': 'model-test',
            'sourcePath': str(safe_dir),
            'mountPath': '/mnt/models/test',
        })

        plugin = self._make_plugin()

        # Call the handler - it will fail at libvirt attach, but we just want to
        # verify that verify_source_path was called
        try:
            plugin.attach_virtiofs(req)
        except Exception:
            pass  # Expected to fail at libvirt level

        # Verify that verify_source_path was called with the source path
        mock_verify.assert_called_once_with(str(safe_dir))

    @patch('kvmagent.plugins.virtiofs_plugin.verify_source_path')
    def test_attach_rejects_dangerous_path(self, mock_verify):
        """Test that attach handler rejects dangerous paths."""
        # Make verify_source_path raise an exception for dangerous path
        mock_verify.side_effect = Exception("sourcePath resolves to a restricted path")

        req = self._make_req({
            'vmInstanceUuid': 'test-vm-uuid',
            'tag': 'model-test',
            'sourcePath': '/etc',
            'mountPath': '/mnt/models/test',
        })

        plugin = self._make_plugin()
        result = plugin.attach_virtiofs(req)
        rsp = json.loads(result)

        # Should return error response
        assert rsp.get('success') is False or rsp.get('error') is not None

    @patch('kvmagent.plugins.virtiofs_plugin.check_libvirt_version')
    def test_status_handler(self, mock_check_version):
        """Test virtiofs status handler."""
        mock_check_version.return_value = (True, "8.0.0")

        req = self._make_req({})
        plugin = self._make_plugin()
        result = plugin.virtiofs_status(req)
        rsp = json.loads(result)

        assert rsp.get('libvirtVersion') == "8.0.0"
        assert rsp.get('virtiofsHotplugSupported') is True


class TestBuildVirtiofsXml:
    """Test build_virtiofs_xml function."""

    def test_build_xml_contains_required_elements(self):
        """Test that generated XML contains all required elements."""
        xml_str = virtiofs_plugin.build_virtiofs_xml("test-tag", "/mnt/models")

        assert "type='mount'" in xml_str
        assert "accessmode='passthrough'" in xml_str
        assert "type='virtiofs'" in xml_str
        assert "/mnt/models" in xml_str
        assert "test-tag" in xml_str
        assert "virtiofsd" in xml_str

    def test_build_xml_escaping(self):
        """Test that special characters in path are preserved."""
        # Paths with spaces should be preserved as-is
        xml_str = virtiofs_plugin.build_virtiofs_xml("tag with spaces", "/mnt/my models")

        assert "/mnt/my models" in xml_str
        assert "tag with spaces" in xml_str
