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


@patch('kvmagent.plugins.virtiofs_plugin._init_virtiofsd_path')
@patch('kvmagent.plugins.virtiofs_plugin.kvmagent.get_http_server')
def test_prepare_host_model_cache_registers_sensitive_command(
        mock_get_http_server, _mock_init_virtiofsd_path):
    server = MagicMock()
    mock_get_http_server.return_value = server

    virtiofs_plugin.VirtiofsPlugin().start()

    prepare_call = next(
        call for call in server.register_async_uri.call_args_list
        if call.args[0] == virtiofs_plugin.VirtiofsPlugin.HOST_MODEL_CACHE_PREPARE_PATH)
    assert isinstance(
        prepare_call.kwargs["cmd"],
        virtiofs_plugin.PrepareHostModelCacheCmd)


def test_report_host_model_cache_reports_missing_cache_leaf_without_creating_it(tmp_path, monkeypatch):
    parent = tmp_path / 'primary-storage'
    parent.mkdir()
    source_root = parent / 'ai-model-cache'
    monkeypatch.setattr(
        virtiofs_plugin.virtiofs_source,
        'statvfs_capacity',
        lambda path: {'physicalTotalBytes': 100, 'physicalAvailableBytes': 80})

    req = {
        http.REQUEST_BODY: json.dumps({'sourceRoot': str(source_root)})
    }
    rsp = json.loads(virtiofs_plugin.VirtiofsPlugin().report_host_model_cache(req))

    assert rsp['success'] is True
    assert not source_root.exists()
    assert rsp['sourceRoot'] == os.path.realpath(str(source_root))
    assert rsp['physicalTotalBytes'] == 100
    assert rsp['physicalAvailableBytes'] == 80
    assert rsp['cacheEntries'] == []


class TestVerifySourcePath:
    """Test verify_source_path() security validation."""

    def test_accept_safe_path(self, tmp_path, monkeypatch):
        """Test that safe paths are accepted."""
        safe_dir = tmp_path / "sources"
        safe_dir.mkdir()

        # Monkeypatch os.path.realpath to treat tmp_path as the allowed base
        original_realpath = os.path.realpath
        def mock_realpath(path):
            result = original_realpath(path)
            # If the path is under tmp_path, pretend it's under the virtiofs source root.
            tmp_real = original_realpath(str(tmp_path))
            if result == tmp_real or result.startswith(tmp_real + os.sep):
                return result.replace(tmp_real, '/var/lib/zstack/aios/virtiofs-sources')
            return result

        monkeypatch.setattr(os.path, 'realpath', mock_realpath)

        # Should not raise any exception
        virtiofs_plugin.verify_source_path(str(safe_dir))

    def test_accept_nested_safe_path(self, tmp_path, monkeypatch):
        """Test that deeply nested safe paths are accepted."""
        nested_dir = tmp_path / "a" / "b" / "c" / "sources"
        nested_dir.mkdir(parents=True)

        # Monkeypatch os.path.realpath to treat tmp_path as the allowed base
        original_realpath = os.path.realpath
        def mock_realpath(path):
            result = original_realpath(path)
            tmp_real = original_realpath(str(tmp_path))
            if result == tmp_real or result.startswith(tmp_real + os.sep):
                return result.replace(tmp_real, '/var/lib/zstack/aios/virtiofs-sources')
            return result

        monkeypatch.setattr(os.path, 'realpath', mock_realpath)

        # Should not raise any exception
        virtiofs_plugin.verify_source_path(str(nested_dir))

    def test_accept_vm_view_root_path(self, tmp_path, monkeypatch):
        """Test that projected VM artifact view paths are accepted."""
        view_dir = tmp_path / "vm-views" / "vm-uuid"
        view_dir.mkdir(parents=True)

        original_realpath = os.path.realpath
        def mock_realpath(path):
            result = original_realpath(path)
            tmp_real = original_realpath(str(tmp_path / "vm-views"))
            if result == tmp_real or result.startswith(tmp_real + os.sep):
                return result.replace(tmp_real, '/var/lib/zstack/aios/vm-views')
            return result

        monkeypatch.setattr(os.path, 'realpath', mock_realpath)

        virtiofs_plugin.verify_source_path(str(view_dir))

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
        assert "outside allowed virtiofs source directory" in str(exc_info.value)

    def test_reject_direct_access_to_root(self):
        """Test that direct access to /root is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/root")
        assert "outside allowed virtiofs source directory" in str(exc_info.value)

    def test_reject_direct_access_to_boot(self):
        """Test that direct access to /boot is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/boot")
        assert "outside allowed virtiofs source directory" in str(exc_info.value)

    def test_reject_direct_access_to_proc(self):
        """Test that direct access to /proc is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/proc")
        assert "outside allowed virtiofs source directory" in str(exc_info.value)

    def test_reject_direct_access_to_sys(self):
        """Test that direct access to /sys is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/sys")
        assert "outside allowed virtiofs source directory" in str(exc_info.value)

    def test_reject_subdirectory_of_etc(self):
        """Test that subdirectory of /etc is blocked."""
        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path("/etc/ssh")
        assert "outside allowed virtiofs source directory" in str(exc_info.value)

    def test_reject_subdirectory_of_root(self, tmp_path, monkeypatch):
        """Test that subdirectory of /root is blocked."""
        source_dir = tmp_path / "root-ssh"
        source_dir.mkdir()

        original_realpath = os.path.realpath
        def mock_realpath(path):
            result = original_realpath(path)
            if result == original_realpath(str(source_dir)):
                return "/root/.ssh"
            return result

        monkeypatch.setattr(os.path, 'realpath', mock_realpath)

        with pytest.raises(Exception) as exc_info:
            virtiofs_plugin.verify_source_path(str(source_dir))
        assert "outside allowed virtiofs source directory" in str(exc_info.value)

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
        # Either "does not exist" or an allowlist rejection is acceptable.
        error_msg = str(exc_info.value)
        assert "does not exist" in error_msg or "outside allowed virtiofs source directory" in error_msg

    def test_reject_symlink_to_dangerous_path(self, tmp_path):
        """Test that symlink pointing to /etc is blocked."""
        link_path = tmp_path / "etc_link"
        try:
            os.symlink("/etc", str(link_path))
            with pytest.raises(Exception) as exc_info:
                virtiofs_plugin.verify_source_path(str(link_path))
            assert "outside allowed virtiofs source directory" in str(exc_info.value)
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
            assert "outside allowed virtiofs source directory" in str(exc_info.value)
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
            assert "outside allowed virtiofs source directory" in str(exc_info.value)
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
            assert "outside allowed virtiofs source directory" in str(exc_info.value)
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
            assert "outside allowed virtiofs source directory" in str(exc_info.value)
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
        assert "does not exist" in error_msg or "outside allowed virtiofs source directory" in error_msg

    def test_accept_symlink_to_safe_location(self, tmp_path, monkeypatch):
        """Test that symlink to safe location is accepted."""
        safe_dir = tmp_path / "safe"
        safe_dir.mkdir()

        # Monkeypatch os.path.realpath to treat tmp_path as the allowed base
        original_realpath = os.path.realpath
        def mock_realpath(path):
            result = original_realpath(path)
            tmp_real = original_realpath(str(tmp_path))
            if result == tmp_real or result.startswith(tmp_real + os.sep):
                return result.replace(tmp_real, '/var/lib/zstack/aios/virtiofs-sources')
            return result

        monkeypatch.setattr(os.path, 'realpath', mock_realpath)

        link_path = tmp_path / "safe_link"
        try:
            os.symlink(str(safe_dir), str(link_path))

            # Should not raise any exception
            virtiofs_plugin.verify_source_path(str(link_path))
        finally:
            if link_path.exists():
                link_path.unlink()


@pytest.mark.kvmagent
class TestHostModelCachePrepareHandler:

    def test_dispatches_juicefs_model_center_source(self, monkeypatch):
        captured = {}

        def prepare(source_root, source_path, model_center_uuid, storage_url,
                    artifact_relative_path, required_capacity, storage_subdir,
                    register_cache, content_version=None):
            captured.update({
                'sourceRoot': source_root,
                'sourcePath': source_path,
                'modelCenterUuid': model_center_uuid,
                'storageUrl': storage_url,
                'artifactRelativePath': artifact_relative_path,
                'requiredCapacityBytes': required_capacity,
                'storageSubdir': storage_subdir,
                'registerCache': register_cache,
                'contentVersion': content_version,
            })
            return {'sourcePath': source_path, 'sizeBytes': 1024, 'contentVersion': 'v:abc'}

        monkeypatch.setattr(virtiofs_plugin.virtiofs_source, 'prepare_model_center_cache', prepare)
        plugin = virtiofs_plugin.VirtiofsPlugin()
        response = json.loads(plugin.prepare_host_model_cache({
            http.REQUEST_BODY: json.dumps({
                'sourceType': 'juicefsModelCenter',
                'sourceRoot': '/cache',
                'sourcePath': '/cache/models/model/v1',
                'modelCenterUuid': 'mc',
                'storageUrl': 'redis://model-center',
                'modelRelativePath': 'qwen/v1',
                'requiredCapacityBytes': 1024,
                'contentVersion': 'abc',
            })
        }))

        assert response['success'] is True
        assert response['cacheEntry']['sourcePath'] == '/cache/models/model/v1'
        assert captured['artifactRelativePath'] == 'qwen/v1'
        assert captured['storageSubdir'] == 'models'
        assert captured['registerCache'] is True
        assert captured['storageUrl'] == 'redis://model-center'
        assert captured['contentVersion'] == 'abc'

    def test_dispatches_non_model_artifact_source(self, monkeypatch):
        captured = {}

        def prepare(source_root, source_path, model_center_uuid, storage_url,
                    artifact_relative_path, required_capacity, storage_subdir,
                    register_cache, content_version=None):
            captured.update({
                'artifactRelativePath': artifact_relative_path,
                'storageSubdir': storage_subdir,
                'registerCache': register_cache,
                'contentVersion': content_version,
            })
            return {'sourcePath': source_path, 'sizeBytes': 256}

        monkeypatch.setattr(virtiofs_plugin.virtiofs_source, 'prepare_model_center_cache', prepare)
        plugin = virtiofs_plugin.VirtiofsPlugin()
        response = json.loads(plugin.prepare_host_model_cache({
            http.REQUEST_BODY: json.dumps({
                'sourceType': 'juicefsModelCenter',
                'sourceRoot': '/sources',
                'sourcePath': '/sources/model-centers/mc/root/datasets/eval',
                'modelCenterUuid': 'mc',
                'storageUrl': 'redis://model-center',
                'storageSubdir': 'datasets',
                'artifactRelativePath': 'eval',
                'registerCache': False,
                'requiredCapacityBytes': 256,
                'contentVersion': 'tpl-v2',
            })
        }))

        assert response['success'] is True
        assert captured == {
            'artifactRelativePath': 'eval',
            'storageSubdir': 'datasets',
            'registerCache': False,
            'contentVersion': 'tpl-v2',
        }


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
    @patch('kvmagent.plugins.virtiofs_plugin._ensure_source_for_attach')
    def test_attach_ensures_source_before_attach(self, mock_ensure_source, mock_get_domain, tmp_path):
        """Test that attach handler ensures the source before libvirt attach."""
        mock_ensure_source.return_value = MagicMock(path=str(tmp_path / "sources"))
        mock_domain = MagicMock()
        mock_conn = MagicMock()
        mock_get_domain.return_value = (mock_domain, mock_conn)

        safe_dir = tmp_path / "sources"
        safe_dir.mkdir()

        req = self._make_req({
            'vmInstanceUuid': 'test-vm-uuid',
            'tag': 'source-test',
            'sourcePath': str(safe_dir),
            'mountPath': '/mnt/virtiofs/test',
        })

        plugin = self._make_plugin()

        # Call the handler - it will fail at later checks, but source must be ensured first.
        try:
            plugin.attach_virtiofs(req)
        except Exception:
            pass  # Expected to fail at libvirt level

        mock_ensure_source.assert_called_once()
        assert mock_ensure_source.call_args[0][0].sourcePath == str(safe_dir)

    @patch('kvmagent.plugins.virtiofs_plugin._ensure_source_for_attach')
    def test_attach_rejects_dangerous_path(self, mock_ensure_source):
        """Test that attach handler rejects dangerous paths."""
        mock_ensure_source.side_effect = Exception(
            "sourcePath resolves to a restricted path")

        req = self._make_req({
            'vmInstanceUuid': 'test-vm-uuid',
            'tag': 'source-test',
            'sourcePath': '/etc',
            'mountPath': '/mnt/virtiofs/test',
        })

        plugin = self._make_plugin()
        result = plugin.attach_virtiofs(req)
        rsp = json.loads(result)

        # Should return error response
        assert rsp.get('success') is False or rsp.get('error') is not None

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    @patch('kvmagent.plugins.virtiofs_plugin.mount_virtiofs_in_vm', return_value=(False, 'QGA not connected'))
    @patch('kvmagent.plugins.virtiofs_plugin.check_vm_memory_backing', return_value=(True, None))
    @patch('kvmagent.plugins.virtiofs_plugin.get_vm_domain')
    @patch('kvmagent.plugins.virtiofs_plugin._ensure_source_for_attach')
    def test_attach_qga_failure_is_best_effort(self, mock_ensure_source, mock_get_domain,
                                               mock_memory_backing, mock_mount_qga,
                                               mock_get_virtiofsd_path):
        mock_ensure_source.return_value = MagicMock(path='/var/lib/zstack/aios/vm-views/vm-uuid')
        mock_domain = MagicMock()
        mock_conn = MagicMock()
        mock_get_domain.return_value = (mock_domain, mock_conn)

        req = self._make_req({
            'vmInstanceUuid': 'vm-uuid',
            'tag': 'artifact-view',
            'sourcePath': '/var/lib/zstack/aios/vm-views/vm-uuid',
            'mountPath': '/mnt/virtiofs',
            'cache': 'none',
            'queue': 2048,
        })

        plugin = self._make_plugin()
        result = plugin.attach_virtiofs(req)
        rsp = json.loads(result)

        assert rsp.get('success') is True
        assert rsp.get('qgaMountAttempted') is True
        assert rsp.get('qgaMountSuccess') is False
        assert rsp.get('qgaMountError') == 'QGA not connected'
        assert mock_domain.attachDeviceFlags.call_count == 2
        mock_domain.detachDeviceFlags.assert_not_called()
        xml_str = mock_domain.attachDeviceFlags.call_args_list[0][0][0]
        assert "queue='2048'" in xml_str
        assert "<cache mode='none'/>" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    @patch('kvmagent.plugins.virtiofs_plugin.mount_virtiofs_in_vm', return_value=(True, None))
    @patch('kvmagent.plugins.virtiofs_plugin.check_vm_memory_backing', return_value=(True, None))
    @patch('kvmagent.plugins.virtiofs_plugin.get_vm_domain')
    @patch('kvmagent.plugins.virtiofs_plugin._ensure_source_for_attach')
    def test_attach_uses_default_cache_and_queue(self, mock_ensure_source, mock_get_domain,
                                                 mock_memory_backing, mock_mount_qga,
                                                 mock_get_virtiofsd_path):
        mock_ensure_source.return_value = MagicMock(path='/var/lib/zstack/aios/vm-views/vm-uuid')
        mock_domain = MagicMock()
        mock_conn = MagicMock()
        mock_get_domain.return_value = (mock_domain, mock_conn)

        req = self._make_req({
            'vmInstanceUuid': 'vm-uuid',
            'tag': 'artifact-view',
            'sourcePath': '/var/lib/zstack/aios/vm-views/vm-uuid',
            'mountPath': '/mnt/virtiofs',
        })

        plugin = self._make_plugin()
        result = plugin.attach_virtiofs(req)
        rsp = json.loads(result)

        assert rsp.get('success') is True
        xml_str = mock_domain.attachDeviceFlags.call_args_list[0][0][0]
        assert "queue='1024'" in xml_str
        assert "<cache mode='none'/>" in xml_str

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

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    def test_build_xml_contains_required_elements(self, mock_path):
        """Test that generated XML contains all required elements."""
        xml_str = virtiofs_plugin.build_virtiofs_xml("test-tag", "/mnt/virtiofs")

        assert "type='mount'" in xml_str
        assert "accessmode='passthrough'" in xml_str
        assert "type='virtiofs'" in xml_str
        assert "/mnt/virtiofs" in xml_str
        assert "test-tag" in xml_str
        assert "virtiofsd" in xml_str
        assert "queue='1024'" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    def test_build_xml_escaping(self, mock_path):
        """Test that special characters in path are preserved."""
        # Paths with spaces should be preserved as-is
        xml_str = virtiofs_plugin.build_virtiofs_xml("tag with spaces", "/mnt/my sources")

        assert "/mnt/my sources" in xml_str
        assert "tag with spaces" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value="/usr/libexec/virtiofsd\"bad")
    def test_build_xml_quoteattr_escapes_attribute_quotes(self, mock_path):
        # quoteattr() should escape quotes in attribute values safely
        xml_str = virtiofs_plugin.build_virtiofs_xml("tag\"q", "/mnt/dir\"q")
        # Attributes should be properly quoted (quoteattr may choose single quotes)
        assert "<source dir='/mnt/dir\"q'/>" in xml_str or "<source dir=\"/mnt/dir&quot;q\"/>" in xml_str
        assert "<target dir='tag\"q'/>" in xml_str or "<target dir=\"tag&quot;q\"/>" in xml_str
        # virtiofsd path contains a quote, it must remain safely inside the attribute value
        assert "path='/usr/libexec/virtiofsd\"bad'" in xml_str or "path=\"/usr/libexec/virtiofsd&quot;bad\"" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    def test_build_xml_default_cache_mode(self, mock_path):
        """Test that default cache mode is 'none'."""
        xml_str = virtiofs_plugin.build_virtiofs_xml("test-tag", "/mnt/virtiofs")
        assert "<cache mode='none'/>" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    def test_build_xml_default_queue(self, mock_path):
        xml_str = virtiofs_plugin.build_virtiofs_xml("test-tag", "/mnt/virtiofs")
        assert "queue='1024'" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    def test_build_xml_custom_queue(self, mock_path):
        xml_str = virtiofs_plugin.build_virtiofs_xml("test-tag", "/mnt/virtiofs", queue=2048)
        assert "queue='2048'" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    def test_build_xml_custom_cache_mode_none(self, mock_path):
        """Test that cache mode 'none' can be specified."""
        xml_str = virtiofs_plugin.build_virtiofs_xml("test-tag", "/mnt/virtiofs", cache_mode='none')
        assert "<cache mode='none'/>" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    def test_build_xml_custom_cache_mode_auto(self, mock_path):
        """Test that cache mode 'auto' can be specified."""
        xml_str = virtiofs_plugin.build_virtiofs_xml("test-tag", "/mnt/virtiofs", cache_mode='auto')
        assert "<cache mode='auto'/>" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    def test_build_xml_custom_cache_mode_always(self, mock_path):
        """Test that cache mode 'always' can be specified."""
        xml_str = virtiofs_plugin.build_virtiofs_xml("test-tag", "/mnt/virtiofs", cache_mode='always')
        assert "<cache mode='always'/>" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    def test_build_xml_invalid_cache_mode_falls_back(self, mock_path):
        """Test that invalid cache mode falls back to default 'none'."""
        xml_str = virtiofs_plugin.build_virtiofs_xml("test-tag", "/mnt/virtiofs", cache_mode='invalid')
        assert "<cache mode='none'/>" in xml_str

    @patch('kvmagent.plugins.virtiofs_plugin.get_virtiofsd_path', return_value='/usr/libexec/virtiofsd')
    def test_build_xml_invalid_queue_falls_back(self, mock_path):
        xml_str = virtiofs_plugin.build_virtiofs_xml("test-tag", "/mnt/virtiofs", queue='invalid')
        assert "queue='1024'" in xml_str


class TestAttachVirtiofsCmd:
    """Test AttachVirtiofsCmd class."""

    def test_cache_mode_can_be_set(self):
        """Test that cacheMode can be set to custom value."""
        cmd = virtiofs_plugin.AttachVirtiofsCmd()
        cmd.vmInstanceUuid = "test-vm-uuid"
        cmd.tag = "test-tag"
        cmd.sourcePath = "/var/lib/zstack/aios/virtiofs-sources/test"
        cmd.mountPath = "/mnt/virtiofs"
        cmd.cacheMode = 'none'
        assert cmd.cacheMode == 'none'

    def test_cache_mode_none(self):
        """Test that cacheMode 'none' can be set."""
        cmd = virtiofs_plugin.AttachVirtiofsCmd()
        cmd.vmInstanceUuid = "test-vm-uuid"
        cmd.tag = "test-tag"
        cmd.sourcePath = "/var/lib/zstack/aios/virtiofs-sources/test"
        cmd.mountPath = "/mnt/virtiofs"
        cmd.cacheMode = 'none'
        assert cmd.cacheMode == 'none'

    def test_cache_mode_auto(self):
        """Test that cacheMode 'auto' can be set."""
        cmd = virtiofs_plugin.AttachVirtiofsCmd()
        cmd.vmInstanceUuid = "test-vm-uuid"
        cmd.tag = "test-tag"
        cmd.sourcePath = "/var/lib/zstack/aios/virtiofs-sources/test"
        cmd.mountPath = "/mnt/virtiofs"
        cmd.cacheMode = 'auto'
        assert cmd.cacheMode == 'auto'

    def test_cache_mode_always(self):
        """Test that cacheMode 'always' can be set."""
        cmd = virtiofs_plugin.AttachVirtiofsCmd()
        cmd.vmInstanceUuid = "test-vm-uuid"
        cmd.tag = "test-tag"
        cmd.sourcePath = "/var/lib/zstack/aios/virtiofs-sources/test"
        cmd.mountPath = "/mnt/virtiofs"
        cmd.cacheMode = 'always'
        assert cmd.cacheMode == 'always'


class TestCheckVmMemoryBacking:
    """Test check_vm_memory_backing function."""

    def _create_mock_domain_with_xml(self, xml_str):
        """Create a mock domain object that returns specific XML."""
        mock_domain = MagicMock()
        mock_domain.XMLDesc = MagicMock(return_value=xml_str)
        return mock_domain

    def test_vm_with_shared_memory_backing(self):
        """Test VM with correct memoryBacking configuration."""
        xml_str = '''<domain type='kvm'>
            <memoryBacking>
                <source type='memfd'/>
                <access mode='shared'/>
            </memoryBacking>
        </domain>'''
        mock_domain = self._create_mock_domain_with_xml(xml_str)

        has_backing, error = virtiofs_plugin.check_vm_memory_backing(mock_domain)
        assert has_backing is True
        assert error is None

    def test_vm_with_only_shared_access(self):
        """Test VM with only access mode='shared' (minimal required config)."""
        xml_str = '''<domain type='kvm'>
            <memoryBacking>
                <access mode='shared'/>
            </memoryBacking>
        </domain>'''
        mock_domain = self._create_mock_domain_with_xml(xml_str)

        has_backing, error = virtiofs_plugin.check_vm_memory_backing(mock_domain)
        assert has_backing is True
        assert error is None

    def test_vm_without_memory_backing(self):
        """Test VM without memoryBacking element."""
        xml_str = '''<domain type='kvm'>
            <name>test-vm</name>
        </domain>'''
        mock_domain = self._create_mock_domain_with_xml(xml_str)

        has_backing, error = virtiofs_plugin.check_vm_memory_backing(mock_domain)
        assert has_backing is False
        assert "does not have shared memory" in error

    def test_vm_with_private_access_mode(self):
        """Test VM with access mode='private' (not shared)."""
        xml_str = '''<domain type='kvm'>
            <memoryBacking>
                <access mode='private'/>
            </memoryBacking>
        </domain>'''
        mock_domain = self._create_mock_domain_with_xml(xml_str)

        has_backing, error = virtiofs_plugin.check_vm_memory_backing(mock_domain)
        assert has_backing is False
        assert "does not have shared memory access mode" in error

    def test_vm_with_memory_backing_but_no_access(self):
        """Test VM with memoryBacking but no access element."""
        xml_str = '''<domain type='kvm'>
            <memoryBacking>
                <nosharepages/>
            </memoryBacking>
        </domain>'''
        mock_domain = self._create_mock_domain_with_xml(xml_str)

        has_backing, error = virtiofs_plugin.check_vm_memory_backing(mock_domain)
        assert has_backing is False
        assert "does not have shared memory access mode" in error

    def test_vm_with_hugepages_but_not_shared(self):
        """Test VM with hugepages but not shared access."""
        xml_str = '''<domain type='kvm'>
            <memoryBacking>
                <hugepages/>
            </memoryBacking>
        </domain>'''
        mock_domain = self._create_mock_domain_with_xml(xml_str)

        has_backing, error = virtiofs_plugin.check_vm_memory_backing(mock_domain)
        assert has_backing is False
        assert "does not have shared memory access mode" in error

    def test_vm_with_hugepages_and_shared(self):
        """Test VM with both hugepages and shared access."""
        xml_str = '''<domain type='kvm'>
            <memoryBacking>
                <hugepages/>
                <access mode='shared'/>
            </memoryBacking>
        </domain>'''
        mock_domain = self._create_mock_domain_with_xml(xml_str)

        has_backing, error = virtiofs_plugin.check_vm_memory_backing(mock_domain)
        assert has_backing is True
        assert error is None

    def test_vm_with_invalid_xml(self):
        """Test VM with invalid XML (should allow operation to proceed)."""
        mock_domain = MagicMock()
        mock_domain.XMLDesc = MagicMock(side_effect=Exception("XML parse error"))

        # On exception, should return True to allow operation (let libvirt report actual error)
        has_backing, error = virtiofs_plugin.check_vm_memory_backing(mock_domain)
        assert has_backing is True
        assert error is None


class TestMountVirtiofsInVm:
    """Test mount_virtiofs_in_vm function."""

    QGA_STATE_RUNNING = "Running"
    QGA_STATE_NOT_RUNNING = "NotRunning"

    def _create_mock_domain(self, name="test-vm"):
        """Create a mock domain with basic properties."""
        mock_domain = MagicMock()
        mock_domain.name = MagicMock(return_value=name)
        return mock_domain

    def _create_mock_qga(self, os_type="linux", state=None):
        """Create a mock VmQga object."""
        if state is None:
            state = self.QGA_STATE_RUNNING
        mock_qga = MagicMock()
        mock_qga.state = state
        mock_qga.os = os_type
        return mock_qga

    @patch('kvmagent.plugins.virtiofs_plugin.VmQga')
    @patch('kvmagent.plugins.virtiofs_plugin.is_qga_connected', return_value=True)
    def test_mount_command_uses_readonly_option(self, mock_is_connected, mock_qga_class):
        """Test that mount command uses -o ro (read-only) option."""
        mock_domain = self._create_mock_domain()
        mock_qga = self._create_mock_qga()
        # Set QGA_STATE_RUNNING on the mock class
        mock_qga_class.QGA_STATE_RUNNING = self.QGA_STATE_RUNNING
        mock_qga_class.return_value = mock_qga

        # Mock QGA commands: mkdir succeeds, mountpoint check returns 1 (not mounted),
        # mount succeeds
        mock_qga.guest_exec_bash.side_effect = [
            (0, "", ""),           # mkdir succeeds
            (1, "", ""),           # mountpoint check (not a mount point)
            (0, "", ""),           # mount succeeds
        ]

        success, error = virtiofs_plugin.mount_virtiofs_in_vm(mock_domain, "test-tag", "/mnt/virtiofs")

        assert success is True
        assert error is None

        # Verify the mount command was called with -o ro
        # Check all calls for the mount command with -o ro
        all_calls = [str(call) for call in mock_qga.guest_exec_bash.call_args_list]
        mount_call_found = any('mount -t virtiofs -o ro' in call_str for call_str in all_calls)
        assert mount_call_found, "Mount command should use -o ro option. Calls: %s" % all_calls

    @patch('kvmagent.plugins.virtiofs_plugin.VmQga')
    @patch('kvmagent.plugins.virtiofs_plugin.is_qga_connected', return_value=True)
    @patch('time.sleep')  # Mock sleep to speed up test
    def test_mount_retries_on_failure(self, mock_sleep, mock_is_connected, mock_qga_class):
        """Test that mount retries once on failure."""
        mock_domain = self._create_mock_domain()
        mock_qga = self._create_mock_qga()
        mock_qga_class.QGA_STATE_RUNNING = self.QGA_STATE_RUNNING
        mock_qga_class.return_value = mock_qga

        # Mock QGA commands: mkdir succeeds, mountpoint check succeeds (not mounted),
        # mount fails twice
        mock_qga.guest_exec_bash.side_effect = [
            (0, "", ""),           # mkdir succeeds
            (1, "", ""),           # mountpoint check (not a mount point)
            (1, "", "mount error"),  # mount attempt 1 fails
            (1, "", "mount error"),  # mount attempt 2 fails
        ]

        success, error = virtiofs_plugin.mount_virtiofs_in_vm(mock_domain, "test-tag", "/mnt/virtiofs")

        assert success is False
        assert "Failed to mount virtiofs source in VM" in error

        # Verify sleep was called once (between retries)
        mock_sleep.assert_called_once_with(1)

    @patch('kvmagent.plugins.virtiofs_plugin.VmQga')
    @patch('kvmagent.plugins.virtiofs_plugin.is_qga_connected', return_value=True)
    @patch('time.sleep')
    def test_mount_succeeds_on_retry(self, mock_sleep, mock_is_connected, mock_qga_class):
        """Test that mount succeeds on second attempt."""
        mock_domain = self._create_mock_domain()
        mock_qga = self._create_mock_qga()
        mock_qga_class.QGA_STATE_RUNNING = self.QGA_STATE_RUNNING
        mock_qga_class.return_value = mock_qga

        # Mock QGA commands: mkdir succeeds, mountpoint check succeeds (not mounted),
        # mount fails first time, succeeds on retry
        mock_qga.guest_exec_bash.side_effect = [
            (0, "", ""),           # mkdir succeeds
            (1, "", ""),           # mountpoint check (not a mount point)
            (1, "", "mount error"),  # mount attempt 1 fails
            (0, "", ""),           # mount attempt 2 succeeds
        ]

        success, error = virtiofs_plugin.mount_virtiofs_in_vm(mock_domain, "test-tag", "/mnt/virtiofs")

        assert success is True
        assert error is None

        # Verify sleep was called once (between retries)
        mock_sleep.assert_called_once_with(1)

    @patch('kvmagent.plugins.virtiofs_plugin.is_qga_connected', return_value=False)
    def test_mount_fails_when_qga_not_connected(self, mock_is_connected):
        """Test that mount fails gracefully when QGA is not connected."""
        mock_domain = self._create_mock_domain()

        success, error = virtiofs_plugin.mount_virtiofs_in_vm(mock_domain, "test-tag", "/mnt/virtiofs")

        assert success is False
        assert "QGA not connected" in error

    @patch('kvmagent.plugins.virtiofs_plugin.VmQga')
    @patch('kvmagent.plugins.virtiofs_plugin.is_qga_connected', return_value=True)
    def test_mount_fails_on_windows_vm(self, mock_is_connected, mock_qga_class):
        """Test that mount fails on Windows VMs."""
        mock_domain = self._create_mock_domain()
        mock_qga = self._create_mock_qga(os_type="mswindows")
        mock_qga_class.QGA_STATE_RUNNING = self.QGA_STATE_RUNNING
        mock_qga_class.return_value = mock_qga

        success, error = virtiofs_plugin.mount_virtiofs_in_vm(mock_domain, "test-tag", "/mnt/virtiofs")

        assert success is False
        assert "Windows VM does not support virtiofs mount" in error

    @patch('kvmagent.plugins.virtiofs_plugin.VmQga')
    @patch('kvmagent.plugins.virtiofs_plugin.is_qga_connected', return_value=True)
    def test_mount_timeout_returns_timeout_error(self, mock_is_connected, mock_qga_class):
        """Test that QGA timeout during mount returns timeout-specific error."""
        mock_domain = self._create_mock_domain()
        mock_qga = self._create_mock_qga()
        mock_qga_class.QGA_STATE_RUNNING = self.QGA_STATE_RUNNING
        mock_qga_class.return_value = mock_qga

        # mkdir succeeds, mountpoint not mounted, then mount raises timeout
        mock_qga.guest_exec_bash.side_effect = [
            (0, "", ""),                    # mkdir succeeds
            (1, "", ""),                    # mountpoint check (not mounted)
            RuntimeError("command timeout after 30s"),  # mount times out
        ]

        success, error = virtiofs_plugin.mount_virtiofs_in_vm(mock_domain, "test-tag", "/mnt/virtiofs")

        assert success is False
        assert "timed out" in error

    @patch('kvmagent.plugins.virtiofs_plugin.VmQga')
    @patch('kvmagent.plugins.virtiofs_plugin.is_qga_connected', return_value=True)
    def test_mount_generic_exception_returns_error(self, mock_is_connected, mock_qga_class):
        """Test that unexpected QGA exception returns exception error message."""
        mock_domain = self._create_mock_domain()
        mock_qga = self._create_mock_qga()
        mock_qga_class.QGA_STATE_RUNNING = self.QGA_STATE_RUNNING
        mock_qga_class.return_value = mock_qga

        # mkdir succeeds, mountpoint not mounted, then mount raises generic error
        mock_qga.guest_exec_bash.side_effect = [
            (0, "", ""),              # mkdir succeeds
            (1, "", ""),              # mountpoint check (not mounted)
            RuntimeError("connection lost"),  # unexpected exception
        ]

        success, error = virtiofs_plugin.mount_virtiofs_in_vm(mock_domain, "test-tag", "/mnt/virtiofs")

        assert success is False
        assert "Exception during QGA mount in VM" in error
        assert "connection lost" in error


class TestUnmountVirtiofsInVm:
    """Test unmount_virtiofs_in_vm function."""

    QGA_STATE_RUNNING = "Running"
    QGA_STATE_NOT_RUNNING = "NotRunning"

    def _create_mock_domain(self, name="test-vm"):
        """Create a mock domain with basic properties."""
        mock_domain = MagicMock()
        mock_domain.name = MagicMock(return_value=name)
        return mock_domain

    def _create_mock_qga(self, os_type="linux", state=None):
        """Create a mock VmQga object."""
        if state is None:
            state = self.QGA_STATE_RUNNING
        mock_qga = MagicMock()
        mock_qga.state = state
        mock_qga.os = os_type
        return mock_qga

    @patch('kvmagent.plugins.virtiofs_plugin.VmQga')
    @patch('kvmagent.plugins.virtiofs_plugin.is_qga_connected', return_value=True)
    def test_unmount_succeeds(self, mock_is_connected, mock_qga_class):
        """Test successful unmount."""
        mock_domain = self._create_mock_domain()
        mock_qga = self._create_mock_qga()
        mock_qga_class.QGA_STATE_RUNNING = self.QGA_STATE_RUNNING
        mock_qga_class.return_value = mock_qga

        # Mock QGA commands
        mock_qga.guest_exec_bash.side_effect = [
            (0, "/mnt/virtiofs", ""),  # findmnt succeeds (is mounted)
            (0, "", ""),              # unmount succeeds
        ]

        success, error = virtiofs_plugin.unmount_virtiofs_in_vm(mock_domain, "test-tag")

        assert success is True
        assert error is None

    @patch('kvmagent.plugins.virtiofs_plugin.VmQga')
    def test_unmount_fails_when_qga_not_running(self, mock_qga_class):
        """Test that unmount fails gracefully when QGA is not running."""
        mock_domain = self._create_mock_domain()
        mock_qga = MagicMock()
        mock_qga.state = self.QGA_STATE_NOT_RUNNING  # Not running
        mock_qga_class.return_value = mock_qga

        success, error = virtiofs_plugin.unmount_virtiofs_in_vm(mock_domain, "test-tag")

        assert success is False
        assert "VM guest agent is not running" in error
