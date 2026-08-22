# -*- coding: utf-8 -*-

import json
import os

import pytest

from kvmagent.plugins import virtiofs_source


class Obj(object):
    pass


class Statvfs(object):
    def __init__(self, available_bytes):
        self.f_frsize = 1
        self.f_bavail = available_bytes


def _provider_with_roots(*roots):
    provider = virtiofs_source.PreparedPathSourceProvider()
    provider.allowed_roots = roots
    return provider


def test_source_spec_from_command_uses_structured_spec():
    cmd = Obj()
    cmd.sourcePath = '/ignored'
    cmd.sourceSpec = {
        'type': 'local',
        'path': '/var/lib/zstack/aios/virtiofs-sources/source-a',
        'uuid': 'source-a',
    }

    spec = virtiofs_source.SourceSpec.from_command(cmd)

    assert spec.source_type == 'local'
    assert spec.path == '/var/lib/zstack/aios/virtiofs-sources/source-a'
    assert spec.source_uuid == 'source-a'


def test_source_spec_from_command_keeps_legacy_flat_fields():
    cmd = Obj()
    cmd.sourceType = 'preparedPath'
    cmd.sourcePath = '/var/lib/zstack/aios/virtiofs-sources/source-a'
    cmd.sourceUuid = 'source-a'

    spec = virtiofs_source.SourceSpec.from_command(cmd)

    assert spec.source_type == 'preparedPath'
    assert spec.path == '/var/lib/zstack/aios/virtiofs-sources/source-a'
    assert spec.source_uuid == 'source-a'


def test_prepare_path_source_records_ready_source(tmp_path):
    source_dir = tmp_path / 'virtiofs-sources' / 'source-a'
    source_dir.mkdir(parents=True)
    registry_file = tmp_path / 'registry.json'
    manager = virtiofs_source.SourceManager(
        providers=[_provider_with_roots(str(tmp_path / 'virtiofs-sources'))],
        registry=virtiofs_source.SourceRegistry(str(registry_file)),
    )

    host_source = manager.ensure_ready({
        'type': 'preparedPath',
        'sourcePath': str(source_dir),
        'sourceUuid': 'source-a',
    })

    assert host_source.sourceUuid == 'source-a'
    assert host_source.sourceType == 'preparedPath'
    assert host_source.path == os.path.realpath(str(source_dir))
    with open(str(registry_file), 'r') as fd:
        registry = json.load(fd)
    assert registry['source-a']['state'] == 'ready'
    assert registry['source-a']['capability']['persistent'] is True


def test_prepare_path_source_accepts_command_source_root(tmp_path):
    source_dir = tmp_path / 'large-disk' / 'model-centers' / 'mc' / 'root' / 'models' / 'qwen'
    source_dir.mkdir(parents=True)
    registry_file = tmp_path / 'registry.json'
    manager = virtiofs_source.SourceManager(
        registry=virtiofs_source.SourceRegistry(str(registry_file)),
    )

    host_source = manager.ensure_ready({
        'type': 'preparedPath',
        'sourcePath': str(source_dir),
        'sourceRootPath': str(tmp_path / 'large-disk'),
        'sourceUuid': 'source-a',
    })

    assert host_source.path == os.path.realpath(str(source_dir))


def test_prepare_path_source_copies_remote_source_to_target_root(tmp_path):
    remote_dir = tmp_path / 'virtiofs-sources' / 'model-centers' / 'mc' / 'root' / 'models' / 'qwen'
    remote_dir.mkdir(parents=True)
    (remote_dir / 'config.json').write_text('{}')
    target_dir = tmp_path / 'primary-storage' / 'ai-model-cache' / 'models' / 'model-uuid' / 'v1'
    registry_file = tmp_path / 'registry.json'
    manager = virtiofs_source.SourceManager(
        registry=virtiofs_source.SourceRegistry(str(registry_file)),
    )

    host_source = manager.ensure_ready({
        'type': 'preparedPath',
        'sourcePath': str(target_dir),
        'sourceRootPath': str(tmp_path / 'primary-storage'),
        'remoteSourcePath': str(remote_dir),
        'remoteSourceRootPath': str(tmp_path / 'virtiofs-sources'),
        'sourceUuid': 'model-cache',
    })

    assert host_source.path == os.path.realpath(str(target_dir))
    assert (target_dir / 'config.json').read_text() == '{}'


def test_prepare_model_center_cache_mounts_copies_and_unmounts(tmp_path, monkeypatch):
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    source_root.mkdir(parents=True)
    target = source_root / 'models' / 'model-uuid' / 'v1'
    provider_root = tmp_path / 'provider-mounts'
    lock_root = tmp_path / 'provider-locks'
    events = []

    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_PROVIDER_ROOT', str(provider_root))
    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_LOCK_ROOT', str(lock_root))

    def mount_model_center(storage_url, mount_path, storage_subdir):
        events.append(('mount', storage_url, mount_path, storage_subdir))
        model_dir = os.path.join(mount_path, 'qwen', 'v1')
        os.makedirs(model_dir)
        with open(os.path.join(model_dir, 'config.json'), 'w') as stream:
            stream.write('{}')

    def unmount_model_center(mount_path):
        events.append(('unmount', mount_path))

    monkeypatch.setattr(virtiofs_source, '_mount_model_center', mount_model_center)
    monkeypatch.setattr(virtiofs_source, '_unmount_model_center', unmount_model_center)

    entry = virtiofs_source.prepare_model_center_cache(
        str(source_root),
        str(target),
        'model-center-uuid',
        'redis://model-center',
        'qwen/v1',
        1024)

    assert entry['sourcePath'] == os.path.realpath(str(target))
    assert (target / 'config.json').read_text() == '{}'
    assert entry['contentVersion'].startswith('meta:')
    assert virtiofs_source.read_local_content_version(str(target)) == entry['contentVersion']
    assert entry['prepareDecision'] == 'cold_copy'
    assert entry['prepareReason'] == 'missing_local'
    assert entry['prepareActions'] == 'mount=1,copy=1'
    registry = json.loads((source_root / '.registry').read_text())
    assert list(registry.values())[0]['path'] == os.path.realpath(str(target))
    assert events[0][0] == 'mount'
    assert events[0][3] == 'models'
    assert events[-1][0] == 'unmount'


def test_mount_model_center_uses_packaged_juicefs_layout(tmp_path, monkeypatch):
    mount_path = tmp_path / 'provider-mount'
    cache_path = tmp_path / 'juicefs-cache'
    commands = []
    mount_checks = iter([False, True])

    monkeypatch.setattr(virtiofs_source, 'JUICEFS_CACHE_DIR', str(cache_path))
    monkeypatch.setattr(virtiofs_source, '_find_juicefs_binary', lambda: '/usr/local/bin/juicefs')
    monkeypatch.setattr(
        virtiofs_source,
        '_run_process',
        lambda args, error_message: commands.append(args))
    monkeypatch.setattr(os.path, 'ismount', lambda path: next(mount_checks))

    virtiofs_source._mount_model_center('redis://model-center', str(mount_path))

    assert commands == [[
        '/usr/local/bin/juicefs', 'mount',
        '--read-only', '-d', '--subdir', 'models',
        '--cache-dir', str(cache_path),
        'redis://model-center', str(mount_path),
    ]]
    assert cache_path.is_dir()


def test_prepare_model_center_cache_rejects_escaping_model_path(tmp_path):
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    source_root.mkdir(parents=True)

    with pytest.raises(Exception) as exc_info:
        virtiofs_source.prepare_model_center_cache(
            str(source_root),
            str(source_root / 'models' / 'model-uuid' / 'v1'),
            'model-center-uuid',
            'redis://model-center',
            '../outside',
            1024)

    assert 'escapes its source root' in str(exc_info.value)


def test_prepare_model_center_cache_unmounts_when_model_is_missing(tmp_path, monkeypatch):
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    source_root.mkdir(parents=True)
    provider_root = tmp_path / 'provider-mounts'
    lock_root = tmp_path / 'provider-locks'
    unmounted = []

    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_PROVIDER_ROOT', str(provider_root))
    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_LOCK_ROOT', str(lock_root))
    monkeypatch.setattr(
        virtiofs_source,
        '_mount_model_center',
        lambda storage_url, mount_path, storage_subdir: os.makedirs(mount_path))
    monkeypatch.setattr(
        virtiofs_source,
        '_unmount_model_center',
        lambda mount_path: unmounted.append(mount_path))

    with pytest.raises(Exception) as exc_info:
        virtiofs_source.prepare_model_center_cache(
            str(source_root),
            str(source_root / 'models' / 'model-uuid' / 'v1'),
            'model-center-uuid',
            'redis://model-center',
            'missing/model',
            1024)

    assert 'does not exist' in str(exc_info.value)
    assert unmounted == [str(provider_root / 'model-center-uuid')]


def test_prepare_model_center_artifact_uses_requested_subdir_without_cache_registration(tmp_path, monkeypatch):
    source_root = tmp_path / 'virtiofs-sources'
    source_root.mkdir()
    target = source_root / 'model-centers' / 'mc' / 'root' / 'datasets' / 'eval'
    provider_root = tmp_path / 'provider-mounts'
    lock_root = tmp_path / 'provider-locks'
    mounted_subdirs = []

    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_PROVIDER_ROOT', str(provider_root))
    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_LOCK_ROOT', str(lock_root))

    def mount_model_center(storage_url, mount_path, storage_subdir):
        mounted_subdirs.append(storage_subdir)
        artifact_dir = os.path.join(mount_path, 'eval')
        os.makedirs(artifact_dir)
        with open(os.path.join(artifact_dir, 'dataset.json'), 'w') as stream:
            stream.write('{}')

    monkeypatch.setattr(virtiofs_source, '_mount_model_center', mount_model_center)
    monkeypatch.setattr(virtiofs_source, '_unmount_model_center', lambda mount_path: None)
    monkeypatch.setattr(
        virtiofs_source,
        '_register_model_center_cache',
        lambda root, path: pytest.fail('non-model artifacts must not enter the model cache registry'))

    entry = virtiofs_source.prepare_model_center_cache(
        str(source_root),
        str(target),
        'mc',
        'redis://model-center',
        'eval',
        256,
        'datasets',
        False)

    assert mounted_subdirs == ['datasets']
    assert entry['sourcePath'] == str(target)
    assert (target / 'dataset.json').read_text() == '{}'


def test_prepare_model_center_cache_reuses_existing_cache_with_matching_strong_version(tmp_path, monkeypatch):
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    target = source_root / 'models' / 'model-uuid' / 'v1'
    target.mkdir(parents=True)
    (target / 'config.json').write_text('{}')
    virtiofs_source.write_local_content_version(str(target), 'v:checksum-abc')
    monkeypatch.setattr(
        virtiofs_source,
        'MODEL_CENTER_PROVIDER_ROOT',
        str(tmp_path / 'provider-mounts'))
    monkeypatch.setattr(
        virtiofs_source,
        'MODEL_CENTER_LOCK_ROOT',
        str(tmp_path / 'provider-locks'))
    monkeypatch.setattr(
        virtiofs_source,
        '_mount_model_center',
        lambda storage_url, mount_path, storage_subdir='models': pytest.fail(
            'existing cache with matching strong version must not remount model center'))
    monkeypatch.setattr(
        virtiofs_source,
        'check_available_capacity',
        lambda path, required: pytest.fail('existing cache must not reserve capacity again'))

    entry = virtiofs_source.prepare_model_center_cache(
        str(source_root),
        str(target),
        'model-center-uuid',
        'redis://model-center',
        'qwen/v1',
        1024,
        content_version='checksum-abc')

    assert entry['sourcePath'] == os.path.realpath(str(target))
    assert entry['contentVersion'] == 'v:checksum-abc'
    assert entry['prepareDecision'] == 'strong_hit'
    assert entry['prepareReason'] == 'strong_match'
    assert entry['prepareActions'] == 'mount=0,copy=0'


def test_report_source_root_uses_parent_capacity_without_creating_missing_leaf(tmp_path, monkeypatch):
    parent = tmp_path / 'primary-storage'
    parent.mkdir()
    source_root = parent / 'ai-model-cache'

    capacity_paths = []
    monkeypatch.setattr(
        virtiofs_source,
        'statvfs_capacity',
        lambda path: capacity_paths.append(path) or
        {'physicalTotalBytes': 100, 'physicalAvailableBytes': 80})

    report = virtiofs_source.report_source_root(str(source_root))

    assert not source_root.exists()
    assert capacity_paths == [os.path.realpath(str(parent))]
    assert report['sourceRoot'] == os.path.realpath(str(source_root))
    assert report['physicalTotalBytes'] == 100
    assert report['physicalAvailableBytes'] == 80
    assert report['cacheEntries'] == []


def test_report_source_root_initializes_managed_default_root(tmp_path, monkeypatch):
    source_root = tmp_path / 'zstack' / 'aios' / 'virtiofs-sources'
    monkeypatch.setattr(virtiofs_source, 'HOST_SOURCE_ROOT', str(source_root))
    monkeypatch.setattr(
        virtiofs_source,
        'statvfs_capacity',
        lambda path: {'physicalTotalBytes': 100, 'physicalAvailableBytes': 80})

    report = virtiofs_source.report_source_root(None)

    assert source_root.is_dir()
    assert report['sourceRoot'] == os.path.realpath(str(source_root))
    assert report['cacheEntries'] == []


def test_report_source_root_rejects_missing_parent_mount(tmp_path):
    source_root = tmp_path / 'missing-mount' / 'ai-model-cache'

    with pytest.raises(Exception) as exc_info:
        virtiofs_source.report_source_root(str(source_root))

    assert 'does not exist' in str(exc_info.value)


def test_report_source_root_rejects_non_directory_parent(tmp_path):
    parent_file = tmp_path / 'not-a-directory'
    parent_file.write_text('file parent')
    source_root = parent_file / 'ai-model-cache'

    with pytest.raises(Exception) as exc_info:
        virtiofs_source.report_source_root(str(source_root))

    assert 'parent[' in str(exc_info.value)
    assert 'is not a directory' in str(exc_info.value)


def test_prepare_model_center_cache_refreshes_when_strong_version_mismatches(tmp_path, monkeypatch):
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    target = source_root / 'models' / 'model-uuid' / 'v1'
    target.mkdir(parents=True)
    (target / 'config.json').write_text('stale')
    virtiofs_source.write_local_content_version(str(target), 'v:old')
    provider_root = tmp_path / 'provider-mounts'
    lock_root = tmp_path / 'provider-locks'
    events = []

    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_PROVIDER_ROOT', str(provider_root))
    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_LOCK_ROOT', str(lock_root))

    def mount_model_center(storage_url, mount_path, storage_subdir):
        events.append(('mount', storage_subdir))
        model_dir = os.path.join(mount_path, 'qwen', 'v1')
        os.makedirs(model_dir)
        with open(os.path.join(model_dir, 'config.json'), 'w') as stream:
            stream.write('fresh')

    monkeypatch.setattr(virtiofs_source, '_mount_model_center', mount_model_center)
    monkeypatch.setattr(virtiofs_source, '_unmount_model_center', lambda mount_path: events.append('unmount'))

    entry = virtiofs_source.prepare_model_center_cache(
        str(source_root),
        str(target),
        'model-center-uuid',
        'redis://model-center',
        'qwen/v1',
        1024,
        content_version='new')

    assert events[0] == ('mount', 'models')
    assert events[-1] == 'unmount'
    assert (target / 'config.json').read_text() == 'fresh'
    assert entry['contentVersion'] == 'v:new'
    assert virtiofs_source.read_local_content_version(str(target)) == 'v:new'
    assert entry['prepareDecision'] == 'refresh'
    assert entry['prepareReason'] == 'strong_mismatch'
    assert entry['prepareActions'] == 'mount=1,copy=1'


def test_prepare_model_center_cache_refreshes_when_meta_mismatches(tmp_path, monkeypatch):
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    target = source_root / 'models' / 'template' / 'root'
    target.mkdir(parents=True)
    (target / 'template.yaml').write_text('old-template')
    virtiofs_source.write_local_content_version(str(target), 'meta:1:1')
    provider_root = tmp_path / 'provider-mounts'
    lock_root = tmp_path / 'provider-locks'
    events = []

    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_PROVIDER_ROOT', str(provider_root))
    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_LOCK_ROOT', str(lock_root))

    def mount_model_center(storage_url, mount_path, storage_subdir):
        events.append('mount')
        model_dir = os.path.join(mount_path, 'template-id')
        os.makedirs(model_dir)
        with open(os.path.join(model_dir, 'template.yaml'), 'w') as stream:
            stream.write('new-template-content')

    monkeypatch.setattr(virtiofs_source, '_mount_model_center', mount_model_center)
    monkeypatch.setattr(virtiofs_source, '_unmount_model_center', lambda mount_path: events.append('unmount'))

    entry = virtiofs_source.prepare_model_center_cache(
        str(source_root),
        str(target),
        'model-center-uuid',
        'redis://model-center',
        'template-id',
        1024,
        'model_service',
        False)

    assert 'mount' in events
    assert (target / 'template.yaml').read_text() == 'new-template-content'
    assert entry['contentVersion'].startswith('meta:')
    assert entry['contentVersion'] != 'meta:1:1'
    assert entry['prepareDecision'] == 'refresh'
    assert entry['prepareReason'] == 'meta_mismatch'


def test_prepare_model_center_cache_reuses_when_meta_matches_after_mount(tmp_path, monkeypatch):
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    target = source_root / 'models' / 'template' / 'root'
    target.mkdir(parents=True)
    (target / 'template.yaml').write_text('same')
    provider_root = tmp_path / 'provider-mounts'
    lock_root = tmp_path / 'provider-locks'
    mounted = []

    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_PROVIDER_ROOT', str(provider_root))
    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_LOCK_ROOT', str(lock_root))

    def mount_model_center(storage_url, mount_path, storage_subdir):
        mounted.append(mount_path)
        model_dir = os.path.join(mount_path, 'template-id')
        os.makedirs(model_dir)
        with open(os.path.join(model_dir, 'template.yaml'), 'w') as stream:
            stream.write('same')
        # Align local sidecar to remote meta so prepare is a hit after mount.
        meta = virtiofs_source.remote_directory_meta(model_dir)
        virtiofs_source.write_local_content_version(str(target), meta)

    monkeypatch.setattr(virtiofs_source, '_mount_model_center', mount_model_center)
    monkeypatch.setattr(virtiofs_source, '_unmount_model_center', lambda mount_path: None)
    monkeypatch.setattr(
        virtiofs_source,
        'prepare_copy_source',
        lambda *args, **kwargs: pytest.fail('matching meta must not recopy'))

    entry = virtiofs_source.prepare_model_center_cache(
        str(source_root),
        str(target),
        'model-center-uuid',
        'redis://model-center',
        'template-id',
        1024,
        'model_service',
        False)

    assert mounted
    assert entry['contentVersion'].startswith('meta:')
    assert (target / 'template.yaml').read_text() == 'same'
    assert entry['prepareDecision'] == 'meta_hit'
    assert entry['prepareReason'] == 'meta_match'
    assert entry['prepareActions'] == 'mount=1,copy=0'


def test_prepare_model_center_cache_without_sidecar_refreshes_existing_dir(tmp_path, monkeypatch):
    """ZSTAC-87450: existence-only hit is wrong; no sidecar forces remount/refresh."""
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    target = source_root / 'models' / 'template' / 'root'
    target.mkdir(parents=True)
    (target / 'template.yaml').write_text('stale-no-sidecar')
    provider_root = tmp_path / 'provider-mounts'
    lock_root = tmp_path / 'provider-locks'
    events = []

    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_PROVIDER_ROOT', str(provider_root))
    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_LOCK_ROOT', str(lock_root))

    def mount_model_center(storage_url, mount_path, storage_subdir):
        events.append('mount')
        model_dir = os.path.join(mount_path, 'template-id')
        os.makedirs(model_dir)
        with open(os.path.join(model_dir, 'template.yaml'), 'w') as stream:
            stream.write('refreshed')

    monkeypatch.setattr(virtiofs_source, '_mount_model_center', mount_model_center)
    monkeypatch.setattr(virtiofs_source, '_unmount_model_center', lambda mount_path: events.append('unmount'))

    entry = virtiofs_source.prepare_model_center_cache(
        str(source_root),
        str(target),
        'model-center-uuid',
        'redis://model-center',
        'template-id',
        None,
        'model_service',
        False)

    assert events == ['mount', 'unmount']
    assert (target / 'template.yaml').read_text() == 'refreshed'
    assert entry['contentVersion'].startswith('meta:')
    assert entry['prepareDecision'] == 'refresh'
    assert entry['prepareReason'] == 'no_sidecar'


def test_prepare_model_center_cache_refresh_restores_backup_when_copy_fails(tmp_path, monkeypatch):
    """Refresh must not leave hosts without cache if the new copy fails."""
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    target = source_root / 'models' / 'template' / 'root'
    target.mkdir(parents=True)
    (target / 'template.yaml').write_text('usable-old-cache')
    virtiofs_source.write_local_content_version(str(target), 'meta:1:1')
    provider_root = tmp_path / 'provider-mounts'
    lock_root = tmp_path / 'provider-locks'

    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_PROVIDER_ROOT', str(provider_root))
    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_LOCK_ROOT', str(lock_root))

    def mount_model_center(storage_url, mount_path, storage_subdir):
        model_dir = os.path.join(mount_path, 'template-id')
        os.makedirs(model_dir)
        with open(os.path.join(model_dir, 'template.yaml'), 'w') as stream:
            stream.write('new-but-copy-will-fail')

    monkeypatch.setattr(virtiofs_source, '_mount_model_center', mount_model_center)
    monkeypatch.setattr(virtiofs_source, '_unmount_model_center', lambda mount_path: None)
    monkeypatch.setattr(
        virtiofs_source,
        'prepare_copy_source',
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception('simulated copy failure')))

    with pytest.raises(Exception) as exc_info:
        virtiofs_source.prepare_model_center_cache(
            str(source_root),
            str(target),
            'model-center-uuid',
            'redis://model-center',
            'template-id',
            1024,
            'model_service',
            False)

    assert 'simulated copy failure' in str(exc_info.value)
    assert target.is_dir()
    assert (target / 'template.yaml').read_text() == 'usable-old-cache'
    assert virtiofs_source.read_local_content_version(str(target)) == 'meta:1:1'
    leftovers = [p for p in target.parent.iterdir() if p.name.startswith(target.name + '.old.')]
    assert leftovers == []


def test_prepare_model_center_cache_refresh_removes_backup_after_success(tmp_path, monkeypatch):
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    target = source_root / 'models' / 'template' / 'root'
    target.mkdir(parents=True)
    (target / 'template.yaml').write_text('old')
    virtiofs_source.write_local_content_version(str(target), 'meta:1:1')
    provider_root = tmp_path / 'provider-mounts'
    lock_root = tmp_path / 'provider-locks'

    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_PROVIDER_ROOT', str(provider_root))
    monkeypatch.setattr(virtiofs_source, 'MODEL_CENTER_LOCK_ROOT', str(lock_root))

    def mount_model_center(storage_url, mount_path, storage_subdir):
        model_dir = os.path.join(mount_path, 'template-id')
        os.makedirs(model_dir)
        with open(os.path.join(model_dir, 'template.yaml'), 'w') as stream:
            stream.write('new')

    monkeypatch.setattr(virtiofs_source, '_mount_model_center', mount_model_center)
    monkeypatch.setattr(virtiofs_source, '_unmount_model_center', lambda mount_path: None)

    entry = virtiofs_source.prepare_model_center_cache(
        str(source_root),
        str(target),
        'model-center-uuid',
        'redis://model-center',
        'template-id',
        1024,
        'model_service',
        False)

    assert (target / 'template.yaml').read_text() == 'new'
    assert entry['prepareDecision'] == 'refresh'
    leftovers = [p for p in target.parent.iterdir() if p.name.startswith(target.name + '.old.')]
    assert leftovers == []


def test_prepare_path_source_rejects_empty_command_source_root(tmp_path):
    source_dir = tmp_path / 'virtiofs-sources' / 'source-a'
    source_dir.mkdir(parents=True)
    manager = virtiofs_source.SourceManager(
        registry=virtiofs_source.SourceRegistry(str(tmp_path / 'registry.json')),
    )

    with pytest.raises(Exception) as exc_info:
        manager.ensure_ready({
            'type': 'preparedPath',
            'sourcePath': str(source_dir),
            'sourceRootPath': ' ',
        })

    assert 'virtiofs sourceRootPath must not be empty' in str(exc_info.value)


def test_prepare_path_source_does_not_fallback_when_command_source_root_is_explicit(tmp_path, monkeypatch):
    default_root = tmp_path / 'virtiofs-sources'
    explicit_root = tmp_path / 'large-disk'
    source_dir = default_root / 'source-a'
    source_dir.mkdir(parents=True)
    explicit_root.mkdir()
    monkeypatch.setattr(virtiofs_source, 'HOST_SOURCE_ROOT', str(default_root))
    monkeypatch.setattr(virtiofs_source, 'VM_VIEW_ROOT', str(tmp_path / 'vm-views'))
    manager = virtiofs_source.SourceManager(
        registry=virtiofs_source.SourceRegistry(str(tmp_path / 'registry.json')),
    )

    with pytest.raises(Exception) as exc_info:
        manager.ensure_ready({
            'type': 'preparedPath',
            'sourcePath': str(source_dir),
            'sourceRootPath': str(explicit_root),
        })

    assert 'outside allowed virtiofs source directory' in str(exc_info.value)


def test_prepare_path_source_rejects_insufficient_capacity(tmp_path, monkeypatch):
    source_dir = tmp_path / 'large-disk' / 'source-a'
    source_dir.mkdir(parents=True)
    monkeypatch.setattr(virtiofs_source.os, 'statvfs', lambda path: Statvfs(512))
    manager = virtiofs_source.SourceManager(
        registry=virtiofs_source.SourceRegistry(str(tmp_path / 'registry.json')),
    )

    with pytest.raises(Exception) as exc_info:
        manager.ensure_ready({
            'type': 'preparedPath',
            'sourcePath': str(source_dir),
            'sourceRootPath': str(tmp_path / 'large-disk'),
            'requiredCapacityBytes': 1024,
        })

    assert 'available capacity[512 bytes] is less than required capacity[1024 bytes]' in str(exc_info.value)


def test_prepare_path_source_accepts_vm_view_root(tmp_path):
    view_dir = tmp_path / 'vm-views' / 'vm-a'
    view_dir.mkdir(parents=True)
    manager = virtiofs_source.SourceManager(
        providers=[_provider_with_roots(str(tmp_path / 'virtiofs-sources'), str(tmp_path / 'vm-views'))],
        registry=virtiofs_source.SourceRegistry(str(tmp_path / 'registry.json')),
    )

    host_source = manager.ensure_ready({
        'type': 'preparedPath',
        'sourcePath': str(view_dir),
    })

    assert host_source.path == os.path.realpath(str(view_dir))


def test_prepare_path_source_rejects_shared_root_itself(tmp_path):
    source_root = tmp_path / 'virtiofs-sources'
    source_root.mkdir()
    manager = virtiofs_source.SourceManager(
        providers=[_provider_with_roots(str(source_root))],
        registry=virtiofs_source.SourceRegistry(str(tmp_path / 'registry.json')),
    )

    with pytest.raises(Exception) as exc_info:
        manager.ensure_ready({
            'type': 'preparedPath',
            'sourcePath': str(source_root),
        })

    assert 'not a concrete virtiofs source' in str(exc_info.value)


def test_prepare_path_source_rejects_outside_roots(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    manager = virtiofs_source.SourceManager(
        providers=[_provider_with_roots(str(tmp_path / 'virtiofs-sources'))],
        registry=virtiofs_source.SourceRegistry(str(tmp_path / 'registry.json')),
    )

    with pytest.raises(Exception) as exc_info:
        manager.ensure_ready({
            'type': 'preparedPath',
            'sourcePath': str(outside),
        })

    assert 'outside allowed virtiofs source directory' in str(exc_info.value)


def test_prepare_path_source_rejects_unsupported_source_type(tmp_path):
    manager = virtiofs_source.SourceManager(
        providers=[_provider_with_roots(str(tmp_path / 'virtiofs-sources'))],
        registry=virtiofs_source.SourceRegistry(str(tmp_path / 'registry.json')),
    )

    with pytest.raises(Exception) as exc_info:
        manager.ensure_ready({
            'type': 'juicefs',
            'sourcePath': '/var/lib/zstack/aios/virtiofs-sources/source-a',
        })

    assert 'unsupported virtiofs source type[juicefs]' in str(exc_info.value)


def test_registry_load_ignores_invalid_json(tmp_path):
    registry_file = tmp_path / 'registry.json'
    registry_file.write_text('{broken')

    assert virtiofs_source.SourceRegistry(str(registry_file)).load() == {}


def test_cleanup_host_model_cache_removes_matching_registry_entry(tmp_path):
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    keep_dir = source_root / 'models' / 'keep' / 'v1'
    drop_dir = source_root / 'models' / 'drop' / 'v1'
    keep_dir.mkdir(parents=True)
    drop_dir.mkdir(parents=True)
    (drop_dir / 'weights.bin').write_bytes(b'1234')

    virtiofs_source._register_model_center_cache(str(source_root), str(keep_dir))
    virtiofs_source._register_model_center_cache(str(source_root), str(drop_dir))
    registry_file = source_root / '.registry'
    lock_file = source_root / '.registry.lock'
    before = json.loads(registry_file.read_text())
    assert len(before) == 2

    result = virtiofs_source.cleanup_host_model_cache(str(source_root), str(drop_dir))

    assert result['sourcePath'] == os.path.realpath(str(drop_dir))
    assert result['bytesReclaimed'] >= 4
    assert not drop_dir.exists()
    assert keep_dir.is_dir()
    assert registry_file.is_file()
    assert lock_file.is_file()
    after = json.loads(registry_file.read_text())
    assert len(after) == 1
    assert list(after.values())[0]['path'] == os.path.realpath(str(keep_dir))
    assert all(os.path.realpath(entry['path']) != os.path.realpath(str(drop_dir))
               for entry in after.values())


def test_cleanup_host_model_cache_clears_registry_when_directory_already_gone(tmp_path):
    source_root = tmp_path / 'primary-storage' / 'ai-model-cache'
    missing = source_root / 'models' / 'gone' / 'v1'
    missing.mkdir(parents=True)
    virtiofs_source._register_model_center_cache(str(source_root), str(missing))
    # Simulate prior physical delete that left registry dirty.
    import shutil
    shutil.rmtree(str(missing))
    assert not missing.exists()
    registry_file = source_root / '.registry'
    assert json.loads(registry_file.read_text())

    result = virtiofs_source.cleanup_host_model_cache(str(source_root), str(missing))

    assert result['bytesReclaimed'] == 0
    assert registry_file.is_file()
    assert json.loads(registry_file.read_text()) == {}
