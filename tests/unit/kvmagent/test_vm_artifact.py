# -*- coding: utf-8 -*-
from __future__ import annotations

from unittest.mock import mock_open, patch

import json
import pytest

from zstacklib.utils import http
from kvmagent.plugins import vm_artifact_plugin
from kvmagent.plugins import vm_artifact


class Statvfs(object):
    def __init__(self, available_bytes):
        self.f_frsize = 1
        self.f_bavail = available_bytes


def _set_roots(monkeypatch, tmp_path):
    source_root = tmp_path / 'virtiofs-sources'
    view_root = tmp_path / 'vm-views'
    source_root.mkdir()
    view_root.mkdir()
    monkeypatch.setattr(vm_artifact, 'HOST_SOURCE_ROOT', str(source_root))
    monkeypatch.setattr(vm_artifact, 'VM_VIEW_ROOT', str(view_root))
    return source_root, view_root


def _mountinfo_line(source, target):
    return '36 25 0:31 %s %s rw,relatime - ext4 /dev/root rw\n' % (source, target)


class TestArtifactPathValidation:

    def test_validate_relative_path_rejects_absolute_path(self):
        with pytest.raises(Exception) as exc_info:
            vm_artifact.validate_relative_path('/foo', 'relativePath')

        assert 'escapes its root' in str(exc_info.value)

    def test_validate_relative_path_rejects_traversal(self):
        with pytest.raises(Exception) as exc_info:
            vm_artifact.validate_relative_path('../foo', 'relativePath')

        assert 'escapes its root' in str(exc_info.value)

    def test_validate_relative_path_preserves_valid_relative_path(self):
        assert vm_artifact.validate_relative_path('foo/bar', 'relativePath') == 'foo/bar'

    def test_source_path_symlink_escape_rejected(self, tmp_path, monkeypatch):
        source_root, _ = _set_roots(monkeypatch, tmp_path)
        outside = tmp_path / 'outside'
        outside.mkdir()
        escaped = source_root / 'source' / 'escaped'
        escaped.parent.mkdir()
        escaped.symlink_to(str(outside))

        artifact = {
            'sourcePath': str(escaped),
            'relativePath': 'artifact',
        }

        with pytest.raises(Exception) as exc_info:
            vm_artifact.make_view_bind_specs('vm-uuid', [artifact])

        assert 'outside allowed root' in str(exc_info.value)


class TestVmArtifactViewSpec:

    def test_parse_vm_artifact_views_normalizes_addon_payload(self, tmp_path, monkeypatch):
        _, view_root = _set_roots(monkeypatch, tmp_path)
        source = view_root / 'vm-uuid'
        source.mkdir()
        addons = {
            vm_artifact.ADDON_VM_ARTIFACT_VIEWS: [{
                'vmInstanceUuid': 'vm-uuid',
                'tag': 'tag with spaces',
                'sourcePath': str(source),
                'cache': 'always',
                'queue': '2048',
                'readOnly': False,
            }]
        }

        views = vm_artifact.parse_vm_artifact_views(addons)

        assert len(views) == 1
        assert isinstance(views[0], vm_artifact.VmArtifactViewSpec)
        assert views[0].tag == 'tag_with_spaces'
        assert views[0].cache == 'always'
        assert views[0].queue == 2048
        assert views[0].read_only is False
        assert views[0].resolve_source_path() == str(source)

    def test_source_path_accepts_view_source_root(self, tmp_path):
        source_root = tmp_path / 'large-disk' / 'virtiofs-sources'
        source = source_root / 'model-centers' / 'mc' / 'root' / 'models' / 'qwen'
        source.mkdir(parents=True)
        addons = {
            vm_artifact.ADDON_VM_ARTIFACT_VIEWS: [{
                'vmInstanceUuid': 'vm-uuid',
                'tag': 'model',
                'sourcePath': str(source),
                'sourceRootPath': str(source_root),
            }]
        }

        views = vm_artifact.parse_vm_artifact_views(addons)

        assert views[0].resolve_source_path() == str(source)

    def test_source_path_capacity_error_is_not_hidden_by_vm_view_fallback(self, tmp_path, monkeypatch):
        source_root = tmp_path / 'large-disk' / 'virtiofs-sources'
        source = source_root / 'model-centers' / 'mc' / 'root' / 'models' / 'qwen'
        source.mkdir(parents=True)
        monkeypatch.setattr(vm_artifact.virtiofs_source.os, 'statvfs', lambda path: Statvfs(512))
        view = vm_artifact.VmArtifactViewSpec.from_raw({
            'vmInstanceUuid': 'vm-uuid',
            'tag': 'model',
            'sourcePath': str(source),
            'sourceRootPath': str(source_root),
            'requiredCapacityBytes': 1024,
        })

        with pytest.raises(Exception) as exc_info:
            view.resolve_source_path()

        assert 'available capacity[512 bytes] is less than required capacity[1024 bytes]' in str(exc_info.value)

    def test_parse_vm_artifact_views_rejects_missing_vm_uuid(self):
        addons = {
            vm_artifact.ADDON_VM_ARTIFACT_VIEWS: [{'tag': 'source'}]
        }

        with pytest.raises(Exception) as exc_info:
            vm_artifact.parse_vm_artifact_views(addons)

        assert 'invalid vmInstanceUuid' in str(exc_info.value)

    def test_view_spec_rejects_artifacts_and_source_path_together(self):
        with pytest.raises(Exception) as exc_info:
            vm_artifact.VmArtifactViewSpec(
                vm_uuid='vm-uuid',
                tag='source',
                artifacts=[{'name': 'a'}],
                source_path='/var/lib/zstack/aios/vm-views/vm-uuid',
            )

        assert 'both artifacts and sourcePath' in str(exc_info.value)


class TestArtifactBind:

    def test_bind_readonly_mounts_and_remounts_readonly(self, tmp_path, monkeypatch):
        source_root, view_root = _set_roots(monkeypatch, tmp_path)
        source = source_root / 'source' / 'artifact'
        source.mkdir(parents=True)
        target = view_root / 'vm-uuid' / 'artifact'

        calls = []
        monkeypatch.setattr(vm_artifact.linux, 'mkdir', lambda *args, **kwargs: None)
        monkeypatch.setattr(vm_artifact.linux, 'is_mounted', lambda path=None: False)
        monkeypatch.setattr(vm_artifact.bash, 'bash_r', lambda cmd: calls.append(cmd) or 0)

        vm_artifact.bind_readonly(str(source), str(target), True)

        assert len(calls) == 2
        assert calls[0].startswith('mount --bind ')
        assert calls[1].startswith('mount -o remount,bind,ro ')

    def test_bind_readonly_rebinds_when_source_changed(self, tmp_path, monkeypatch):
        source_root, view_root = _set_roots(monkeypatch, tmp_path)
        old_source = source_root / 'source' / 'old'
        new_source = source_root / 'source' / 'new'
        old_source.mkdir(parents=True)
        new_source.mkdir()
        target = view_root / 'vm-uuid' / 'artifact'
        target.mkdir(parents=True)

        mountinfo = _mountinfo_line(str(old_source), str(target))
        is_mounted = iter([True, True, False, False])
        bash_calls = []
        umount_calls = []

        monkeypatch.setattr(vm_artifact.linux, 'mkdir', lambda *args, **kwargs: None)
        monkeypatch.setattr(vm_artifact.linux, 'is_mounted', lambda path=None: next(is_mounted))
        monkeypatch.setattr(vm_artifact.linux, 'umount',
                            lambda path, is_exception=False: umount_calls.append(path) or True)
        monkeypatch.setattr(vm_artifact.bash, 'bash_r', lambda cmd: bash_calls.append(cmd) or 0)

        with patch('builtins.open', mock_open(read_data=mountinfo)):
            status = vm_artifact.bind_readonly(str(new_source), str(target), True)

        assert status == vm_artifact.BIND_REBOUND_STALE
        assert umount_calls == [str(target)]
        assert bash_calls[0].startswith('mount --bind ')
        assert str(new_source) in bash_calls[0]
        assert str(target) in bash_calls[0]
        assert bash_calls[1].startswith('mount -o remount,bind,ro ')

    def test_bind_readonly_keeps_same_source_mount(self, tmp_path, monkeypatch):
        source_root, view_root = _set_roots(monkeypatch, tmp_path)
        source = source_root / 'source' / 'artifact'
        source.mkdir(parents=True)
        target = view_root / 'vm-uuid' / 'artifact'
        target.mkdir(parents=True)

        mountinfo = _mountinfo_line(str(source), str(target))
        bash_calls = []
        umount_calls = []

        monkeypatch.setattr(vm_artifact.linux, 'mkdir', lambda *args, **kwargs: None)
        monkeypatch.setattr(vm_artifact.linux, 'is_mounted', lambda path=None: True)
        monkeypatch.setattr(vm_artifact.linux, 'umount',
                            lambda path, is_exception=False: umount_calls.append(path) or True)
        monkeypatch.setattr(vm_artifact.bash, 'bash_r', lambda cmd: bash_calls.append(cmd) or 0)

        with patch('builtins.open', mock_open(read_data=mountinfo)):
            status = vm_artifact.bind_readonly(str(source), str(target), True)

        assert status == vm_artifact.BIND_REUSED_EXISTING
        assert umount_calls == []
        assert len(bash_calls) == 1
        assert bash_calls[0].startswith('mount -o remount,bind,ro ')

    def test_bind_readwrite_remounts_existing_same_source_as_rw(self, tmp_path, monkeypatch):
        source_root, view_root = _set_roots(monkeypatch, tmp_path)
        source = source_root / 'source' / 'artifact'
        source.mkdir(parents=True)
        target = view_root / 'vm-uuid' / 'artifact'
        target.mkdir(parents=True)

        mountinfo = _mountinfo_line(str(source), str(target))
        bash_calls = []

        monkeypatch.setattr(vm_artifact.linux, 'mkdir', lambda *args, **kwargs: None)
        monkeypatch.setattr(vm_artifact.linux, 'is_mounted', lambda path=None: True)
        monkeypatch.setattr(vm_artifact.linux, 'umount',
                            lambda path, is_exception=False: True)
        monkeypatch.setattr(vm_artifact.bash, 'bash_r', lambda cmd: bash_calls.append(cmd) or 0)

        with patch('builtins.open', mock_open(read_data=mountinfo)):
            status = vm_artifact.bind_readonly(str(source), str(target), False)

        assert status == vm_artifact.BIND_REUSED_EXISTING
        assert bash_calls == ['mount -o remount,bind,rw %s' % str(target)]

    def test_bind_readonly_replaces_existing_directory_target_for_file_source(self, tmp_path, monkeypatch):
        source_root, view_root = _set_roots(monkeypatch, tmp_path)
        source = source_root / 'source' / 'artifact'
        source.parent.mkdir(parents=True)
        source.write_text('data')
        target = view_root / 'vm-uuid' / 'artifact'
        target.mkdir(parents=True)

        monkeypatch.setattr(vm_artifact.linux, 'is_mounted', lambda path=None: False)
        monkeypatch.setattr(vm_artifact.bash, 'bash_r', lambda cmd: 0)

        vm_artifact.bind_readonly(str(source), str(target), True)

        assert target.is_file()

    def test_bind_readonly_replaces_existing_file_target_for_directory_source(self, tmp_path, monkeypatch):
        source_root, view_root = _set_roots(monkeypatch, tmp_path)
        source = source_root / 'source' / 'artifact'
        source.mkdir(parents=True)
        target = view_root / 'vm-uuid' / 'artifact'
        target.parent.mkdir(parents=True)
        target.write_text('stale')

        monkeypatch.setattr(vm_artifact.linux, 'is_mounted', lambda path=None: False)
        monkeypatch.setattr(vm_artifact.bash, 'bash_r', lambda cmd: 0)

        vm_artifact.bind_readonly(str(source), str(target), True)

        assert target.is_dir()

    def test_mounted_source_uses_mountinfo_root_field(self, tmp_path):
        source = tmp_path / 'source'
        target = tmp_path / 'target'
        source.mkdir()
        target.mkdir()
        mountinfo = _mountinfo_line(str(source), str(target))

        with patch('builtins.open', mock_open(read_data=mountinfo)):
            assert vm_artifact.mounted_source(str(target)) == str(source)

    def test_mounted_source_decodes_mountinfo_escaped_paths(self, tmp_path):
        source = tmp_path / 'source with space'
        target = tmp_path / 'target with space'
        source.mkdir()
        target.mkdir()
        mountinfo = _mountinfo_line(str(source).replace(' ', '\\040'),
                                    str(target).replace(' ', '\\040'))

        with patch('builtins.open', mock_open(read_data=mountinfo)):
            assert vm_artifact.mounted_source(str(target)) == str(source)

    def test_list_mounts_under_decodes_mountinfo_escaped_targets(self, tmp_path):
        root = tmp_path / 'vm-uuid'
        target = root / 'target with space'
        source = tmp_path / 'source'
        target.mkdir(parents=True)
        source.mkdir()
        mountinfo = _mountinfo_line(str(source), str(target).replace(' ', '\\040'))

        with patch('builtins.open', mock_open(read_data=mountinfo)):
            assert vm_artifact.list_mounts_under(str(root)) == [str(target)]


class TestArtifactCleanup:

    def test_unmount_if_needed_returns_false_when_umount_fails(self, monkeypatch):
        monkeypatch.setattr(vm_artifact.linux, 'is_mounted', lambda path=None: True)
        monkeypatch.setattr(vm_artifact.linux, 'umount', lambda path, is_exception=False: False)

        assert vm_artifact.unmount_if_needed('/tmp/target') is False

    def test_cleanup_preserves_target_when_unmount_fails(self, tmp_path, monkeypatch):
        _, view_root = _set_roots(monkeypatch, tmp_path)
        root = view_root / 'vm-uuid'
        stale = root / 'stale'
        stale.mkdir(parents=True)

        monkeypatch.setattr(vm_artifact, 'list_mounts_under', lambda root_path: [str(stale)])
        monkeypatch.setattr(vm_artifact.linux, 'is_mounted', lambda path=None: True)
        monkeypatch.setattr(vm_artifact.linux, 'umount', lambda path, is_exception=False: False)

        vm_artifact.cleanup_view('vm-uuid')

        assert stale.exists()

    def test_cleanup_preserves_children_when_unmount_fails(self, tmp_path, monkeypatch):
        _, view_root = _set_roots(monkeypatch, tmp_path)
        root = view_root / 'vm-uuid'
        stale = root / 'stale'
        child = stale / 'child'
        child.mkdir(parents=True)
        child_file = child / 'data'
        child_file.write_text('keep')
        removed = []

        monkeypatch.setattr(vm_artifact, 'list_mounts_under', lambda root_path: [str(stale)])
        monkeypatch.setattr(vm_artifact, 'unmount_if_needed', lambda path: False)
        monkeypatch.setattr(vm_artifact, 'remove_path', lambda path: removed.append(path))

        vm_artifact.cleanup_view('vm-uuid')

        assert removed == []
        assert child_file.exists()

    def test_cleanup_preserves_escaped_space_mount_when_unmount_fails(self, tmp_path, monkeypatch):
        _, view_root = _set_roots(monkeypatch, tmp_path)
        root = view_root / 'vm-uuid'
        stale = root / 'stale with space'
        child_file = stale / 'data'
        stale.mkdir(parents=True)
        child_file.write_text('keep')
        removed = []

        monkeypatch.setattr(vm_artifact, 'list_mounts_under', lambda root_path: [str(stale)])
        monkeypatch.setattr(vm_artifact, 'unmount_if_needed', lambda path: False)
        monkeypatch.setattr(vm_artifact, 'remove_path', lambda path: removed.append(path))

        vm_artifact.cleanup_view('vm-uuid')

        assert removed == []
        assert child_file.exists()

    def test_cleanup_removes_unmounted_stale_path(self, tmp_path, monkeypatch):
        _, view_root = _set_roots(monkeypatch, tmp_path)
        root = view_root / 'vm-uuid'
        stale = root / 'stale'
        stale.mkdir(parents=True)

        monkeypatch.setattr(vm_artifact, 'list_mounts_under', lambda root_path: [])

        vm_artifact.cleanup_view('vm-uuid')

        assert not stale.exists()

    def test_cleanup_removes_nested_stale_sibling_and_keeps_parent(self, tmp_path, monkeypatch):
        _, view_root = _set_roots(monkeypatch, tmp_path)
        root = view_root / 'vm-uuid'
        kept = root / 'parent' / 'child'
        stale = root / 'parent' / 'stale'
        kept.mkdir(parents=True)
        stale.mkdir()
        keep_paths = [str(kept)]

        monkeypatch.setattr(vm_artifact, 'list_mounts_under', lambda root_path: [])

        vm_artifact.cleanup_view('vm-uuid', keep_paths)

        assert kept.exists()
        assert not stale.exists()
        assert kept.parent.exists()

    def test_cleanup_idempotent_for_nested_keep_paths(self, tmp_path, monkeypatch):
        _, view_root = _set_roots(monkeypatch, tmp_path)
        root = view_root / 'vm-uuid'
        kept = root / 'parent' / 'child'
        kept.mkdir(parents=True)
        keep_paths = [str(kept)]

        monkeypatch.setattr(vm_artifact, 'list_mounts_under', lambda root_path: [])

        vm_artifact.cleanup_view('vm-uuid', keep_paths)
        vm_artifact.cleanup_view('vm-uuid', keep_paths)

        assert kept.exists()

    def test_unmount_if_needed_returns_false_when_still_mounted(self, monkeypatch):
        states = iter([True, True])
        monkeypatch.setattr(vm_artifact.linux, 'is_mounted', lambda path=None: next(states))
        monkeypatch.setattr(vm_artifact.linux, 'umount', lambda path, is_exception=False: True)

        assert vm_artifact.unmount_if_needed('/tmp/target') is False

    def test_sync_artifact_view_removes_partial_targets_when_bind_fails(self, tmp_path, monkeypatch):
        source_root, view_root = _set_roots(monkeypatch, tmp_path)
        first = source_root / 'source' / 'first'
        second = source_root / 'source' / 'second'
        first.mkdir(parents=True)
        second.mkdir()
        removed = []
        unmounted = []

        def fake_bind(source_path, target_path, read_only=True):
            if source_path == str(second):
                raise Exception('bind failed')
            return vm_artifact.BIND_MOUNTED_NEW

        monkeypatch.setattr(vm_artifact, 'bind_readonly', fake_bind)
        monkeypatch.setattr(vm_artifact, 'unmount_if_needed',
                            lambda path: unmounted.append(path) or True)
        monkeypatch.setattr(vm_artifact, 'remove_path', lambda path: removed.append(path))

        with pytest.raises(Exception) as exc_info:
            vm_artifact.sync_artifact_view('vm-uuid', [
                {'sourcePath': str(first), 'relativePath': 'first'},
                {'sourcePath': str(second), 'relativePath': 'second'},
            ])

        assert 'bind failed' in str(exc_info.value)
        assert unmounted == [
            str(view_root / 'vm-uuid' / 'first'),
        ]
        assert removed == [
            str(view_root / 'vm-uuid' / 'first'),
        ]

    def test_sync_artifact_view_keeps_reused_targets_when_later_bind_fails(self, tmp_path, monkeypatch):
        source_root, view_root = _set_roots(monkeypatch, tmp_path)
        first = source_root / 'source' / 'first'
        second = source_root / 'source' / 'second'
        first.mkdir(parents=True)
        second.mkdir()
        reused_target = view_root / 'vm-uuid' / 'first'
        reused_target.mkdir(parents=True)
        removed = []
        unmounted = []

        def fake_bind(source_path, target_path, read_only=True):
            if source_path == str(first):
                return vm_artifact.BIND_REUSED_EXISTING
            raise Exception('bind failed')

        monkeypatch.setattr(vm_artifact, 'bind_readonly', fake_bind)
        monkeypatch.setattr(vm_artifact, 'unmount_if_needed',
                            lambda path: unmounted.append(path) or True)
        monkeypatch.setattr(vm_artifact, 'remove_path', lambda path: removed.append(path))

        with pytest.raises(Exception):
            vm_artifact.sync_artifact_view('vm-uuid', [
                {'sourcePath': str(first), 'relativePath': 'first'},
                {'sourcePath': str(second), 'relativePath': 'second'},
            ])

        assert unmounted == []
        assert removed == []
        assert reused_target.exists()

    def test_sync_artifact_view_keeps_reused_targets_on_success(self, tmp_path, monkeypatch):
        source_root, view_root = _set_roots(monkeypatch, tmp_path)
        first = source_root / 'source' / 'first'
        second = source_root / 'source' / 'second'
        first.mkdir(parents=True)
        second.mkdir()
        reused_target = view_root / 'vm-uuid' / 'first'
        new_target = view_root / 'vm-uuid' / 'second'
        stale_target = view_root / 'vm-uuid' / 'stale'
        reused_target.mkdir(parents=True)
        stale_target.mkdir()
        cleanup_calls = []

        def fake_bind(source_path, target_path, read_only=True):
            if source_path == str(first):
                return vm_artifact.BIND_REUSED_EXISTING
            return vm_artifact.BIND_MOUNTED_NEW

        def fake_cleanup(vm_uuid, keep_paths=None):
            cleanup_calls.append((vm_uuid, keep_paths))

        monkeypatch.setattr(vm_artifact, 'bind_readonly', fake_bind)
        monkeypatch.setattr(vm_artifact, 'cleanup_view', fake_cleanup)

        vm_artifact.sync_artifact_view('vm-uuid', [
            {'sourcePath': str(first), 'relativePath': 'first'},
            {'sourcePath': str(second), 'relativePath': 'second'},
        ])

        assert cleanup_calls == [('vm-uuid', [str(reused_target), str(new_target)])]

    def test_delete_view_preserves_relative_path_when_unmount_fails(self, tmp_path, monkeypatch):
        _, view_root = _set_roots(monkeypatch, tmp_path)
        root = view_root / 'vm-uuid'
        stale = root / 'stale'
        stale.mkdir(parents=True)
        removed = []

        monkeypatch.setattr(vm_artifact, 'unmount_if_needed', lambda path: False)
        monkeypatch.setattr(vm_artifact, 'remove_path', lambda path: removed.append(path))

        plugin = vm_artifact_plugin.VmArtifactViewPlugin.__new__(vm_artifact_plugin.VmArtifactViewPlugin)
        req = {
            http.REQUEST_BODY: json.dumps({
                'vmInstanceUuid': 'vm-uuid',
                'relativePath': 'stale',
            })
        }

        rsp = json.loads(plugin.delete_vm_artifact_view(req))

        assert rsp.get('success') is False
        assert 'failed to unmount' in rsp.get('error', '')
        assert removed == []
        assert stale.exists()

    def test_delete_view_preserves_subtree_when_child_mount_unmount_fails(self, tmp_path, monkeypatch):
        _, view_root = _set_roots(monkeypatch, tmp_path)
        root = view_root / 'vm-uuid'
        parent = root / 'parent'
        mounted_child = parent / 'mounted-child'
        mounted_child.mkdir(parents=True)
        removed = []

        monkeypatch.setattr(vm_artifact, 'list_mounts_under', lambda path: [str(mounted_child)])
        monkeypatch.setattr(vm_artifact, 'unmount_if_needed', lambda path: False)
        monkeypatch.setattr(vm_artifact, 'remove_path', lambda path: removed.append(path))

        plugin = vm_artifact_plugin.VmArtifactViewPlugin.__new__(vm_artifact_plugin.VmArtifactViewPlugin)
        req = {
            http.REQUEST_BODY: json.dumps({
                'vmInstanceUuid': 'vm-uuid',
                'relativePath': 'parent',
            })
        }

        rsp = json.loads(plugin.delete_vm_artifact_view(req))

        assert rsp.get('success') is False
        assert 'failed to unmount' in rsp.get('error', '')
        assert removed == []
        assert mounted_child.exists()

    def test_delete_view_rejects_empty_relative_path_without_full_cleanup(self, tmp_path, monkeypatch):
        _set_roots(monkeypatch, tmp_path)
        cleanup_calls = []
        monkeypatch.setattr(vm_artifact, 'cleanup_view', lambda vm_uuid: cleanup_calls.append(vm_uuid))

        plugin = vm_artifact_plugin.VmArtifactViewPlugin.__new__(vm_artifact_plugin.VmArtifactViewPlugin)
        req = {
            http.REQUEST_BODY: json.dumps({
                'vmInstanceUuid': 'vm-uuid',
                'relativePath': '',
            })
        }

        rsp = json.loads(plugin.delete_vm_artifact_view(req))

        assert rsp.get('success') is False
        assert 'relativePath cannot be empty' in rsp.get('error', '')
        assert cleanup_calls == []
