import hashlib
import importlib.util
import json
import pathlib
import os
import tempfile
import unittest
from unittest.mock import patch

import pytest


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
PATH = REPOSITORY_ROOT / 'kvmagent/scripts/stage_memory_optimization_rpm.py'
SPEC = importlib.util.spec_from_file_location('stage_memory_optimization_rpm', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.integration
class StageRpmTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.rpm = self.root / 'zstack-zram-1.2.3-1.x86_64.rpm'
        self.rpm.write_bytes(b'fixture-rpm')
        self.build_manifest = self.root / 'BUILD-MANIFEST.json'
        self.snapshot_sha = '1' * 64
        self.patch_sha = '2' * 64
        self.build_manifest.write_text(json.dumps({
            'schemaVersion': 1,
            'package': 'zstack-zram',
            'rpmVersion': '1.2.3',
            'rpmRelease': '1',
            'sourceSnapshotSha256': self.snapshot_sha,
            'sourceRevision': 'a' * 40,
            'dirtyPatchSha256': self.patch_sha,
            'sourceFiles': [{'path': MODULE.UNIT_SOURCE_PATH, 'sha256': 'd' * 64}],
        }))

    def fake_query(self, argv, **kwargs):
        if '--scripts' in argv:
            return ''
        if '-qpl' in argv:
            return '\n'.join(sorted(MODULE.REQUIRED_RPM_FILES)) + '\n'
        if '--configfiles' in argv:
            return '/etc/zram-memory/config.json\n'
        if 'FILEDIGESTALGO' in ' '.join(argv):
            return '8\n'
        if 'FILEDIGESTS' in ' '.join(argv):
            return ('/usr/local/libexec/zram-efficiency 123 aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n'
                    '/usr/local/bin/zram-efficiencyctl 456 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n')
        if 'FILEFLAGS' in ' '.join(argv):
            return '/etc/zram-memory/config.json cn\n'
        return 'zstack-zram\n1.2.3\n1\nx86_64\n'

    @patch.object(MODULE.subprocess, 'check_output')
    def test_stage_records_exact_rpm_inventory_and_pins(self, query):
        query.side_effect = self.fake_query
        output = self.root / 'stage'
        MODULE.stage(self.rpm, self.build_manifest, output,
                     self.snapshot_sha, self.patch_sha,
                     ['h84r', 'alinux4', 'ky10sp3'])
        inventory = json.loads((output / 'rpm-inventory.json').read_text())
        staged_rpm = output / inventory['package']['filename']
        self.assertEqual(hashlib.sha256(b'fixture-rpm').hexdigest(),
                         inventory['package']['sha256'])
        self.assertEqual(self.snapshot_sha, inventory['source']['sourceSnapshotSha256'])
        self.assertEqual(self.patch_sha, inventory['source']['dirtyPatchSha256'])
        self.assertEqual(['alinux4', 'h84r', 'ky10sp3'], inventory['supportedHostProfiles'])
        self.assertEqual(sorted(MODULE.REQUIRED_RPM_FILES), inventory['rpmFiles'])
        self.assertEqual(3, inventory['schemaVersion'])
        self.assertEqual('d' * 64, inventory['systemdUnitSha256'])
        self.assertEqual({
            '/usr/local/libexec/zram-efficiency': {
                'bytes': 123, 'sha256': 'a' * 64},
            '/usr/local/bin/zram-efficiencyctl': {
                'bytes': 456, 'sha256': 'b' * 64},
        }, inventory['runtimeBinaries'])
        self.assertEqual(MODULE.INSTALLER_NAME, inventory['installer']['filename'])
        self.assertTrue((output / MODULE.INSTALLER_NAME).is_file())
        self.assertEqual(hashlib.sha256((''.join(path + '\n' for path in inventory['rpmFiles'])).encode()).hexdigest(),
                         inventory['rpmFilesSha256'])
        self.assertEqual(b'fixture-rpm', staged_rpm.read_bytes())

    @patch.object(MODULE.subprocess, 'check_output')
    def test_rejects_nonempty_output_and_rpm_with_kernel_file(self, query):
        query.side_effect = self.fake_query
        output = self.root / 'stage'
        output.mkdir()
        (output / 'unrelated').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'OUTPUT_EXISTS'):
            MODULE.stage(self.rpm, self.build_manifest, output,
                         self.snapshot_sha, self.patch_sha, ['h84r'])

        query.side_effect = lambda argv, **kwargs: (
            '\n'.join(sorted(MODULE.REQUIRED_RPM_FILES | {'/lib/modules/test/zram.ko'})) + '\n'
            if '-qpl' in argv else self.fake_query(argv, **kwargs))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'KERNEL_ARTIFACT_FORBIDDEN'):
                MODULE.stage(self.rpm, self.build_manifest, pathlib.Path(tmp) / 'out',
                             self.snapshot_sha, self.patch_sha, ['h84r'])

    @patch.object(MODULE.subprocess, 'check_output')
    def test_rejects_scriptlets_wrong_config_flag_and_snapshot_pin(self, query):
        query.side_effect = lambda argv, **kwargs: 'postinstall script\n' if '--scripts' in argv else self.fake_query(argv, **kwargs)
        with self.assertRaisesRegex(ValueError, 'SCRIPTLETS_FORBIDDEN'):
            MODULE.stage(self.rpm, self.build_manifest, self.root / 'out-one',
                         self.snapshot_sha, self.patch_sha, ['h84r'])
        query.side_effect = lambda argv, **kwargs: '/etc/zram-memory/config.json\n' if 'FILEFLAGS' in ' '.join(argv) else self.fake_query(argv, **kwargs)
        with self.assertRaisesRegex(ValueError, 'CONFIG_NOREPLACE_REQUIRED'):
            MODULE.stage(self.rpm, self.build_manifest, self.root / 'out-two',
                         self.snapshot_sha, self.patch_sha, ['h84r'])
        query.side_effect = self.fake_query
        with self.assertRaisesRegex(ValueError, 'SOURCE_SNAPSHOT_PIN_MISMATCH'):
            MODULE.stage(self.rpm, self.build_manifest, self.root / 'out-three',
                         'f' * 64, self.patch_sha, ['h84r'])

    @patch.object(MODULE.subprocess, 'check_output')
    def test_rejects_missing_or_ambiguous_effective_unit_source_pin(self, query):
        query.side_effect = self.fake_query
        data = json.loads(self.build_manifest.read_text())
        data['sourceFiles'] = []
        self.build_manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'SYSTEMD_UNIT_SOURCE_PIN_MISSING'):
            MODULE.stage(self.rpm, self.build_manifest, self.root / 'no-unit',
                         self.snapshot_sha, self.patch_sha, ['h84r'])
        data['sourceFiles'] = [
            {'path': MODULE.UNIT_SOURCE_PATH, 'sha256': 'd' * 64},
            {'path': MODULE.UNIT_SOURCE_PATH, 'sha256': 'e' * 64}]
        self.build_manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'SYSTEMD_UNIT_SOURCE_PIN_MISSING'):
            MODULE.stage(self.rpm, self.build_manifest, self.root / 'duplicate-unit',
                         self.snapshot_sha, self.patch_sha, ['h84r'])

    def test_source_snapshot_verifier_fails_closed_on_unlisted_or_mode_changed_input(self):
        zram_source = pathlib.Path(os.environ.get(
            'ZSTACK_ZRAM_SOURCE', str(REPOSITORY_ROOT.parent / 'zstack-zram'))).resolve()
        verifier_path = zram_source / 'packaging' / 'verify-source-snapshot.py'
        self.assertTrue(
            verifier_path.is_file(),
            'set ZSTACK_ZRAM_SOURCE to the pinned sibling zstack-zram checkout',
        )
        self.assertTrue(verifier_path.is_file())
        spec = importlib.util.spec_from_file_location('verify_zram_source_snapshot', verifier_path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        source = self.root / 'source'
        for root in verifier.ROOT_INPUTS:
            (source / root).mkdir(parents=True, exist_ok=True)
        expected = set(verifier.EXACT_INPUTS)
        expected.update(('service/main.go', 'cli/main.go', 'packaging/rpm/service.spec'))
        files = []
        for relative in sorted(expected):
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(relative.encode())
            path.chmod(0o755 if relative.endswith('.sh') or relative.endswith('.py') else 0o644)
            files.append({'path': relative,
                          'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                          'bytes': path.stat().st_size,
                          'mode': path.stat().st_mode & 0o7777})
        manifest = self.root / 'source-inputs.json'
        payload = {'schemaVersion': 1, 'sourceRevision': 'a' * 40,
                   'dirtyPatchSha256': 'b' * 64, 'files': files}
        manifest.write_text(json.dumps(payload, sort_keys=True))
        manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.assertEqual(len(expected), verifier.verify(source, manifest, manifest_sha,
                                                        'a' * 40, 'b' * 64)[1])
        extra = source / 'service/unpinned.go'
        extra.write_text('unlisted')
        with self.assertRaisesRegex(ValueError, 'UNPINNED_SOURCE_INPUT'):
            verifier.verify(source, manifest, manifest_sha, 'a' * 40, 'b' * 64)


if __name__ == '__main__':
    unittest.main()
