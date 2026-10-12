import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = (Path(__file__).resolve().parents[2] / 'zstackbuild/scripts' /
          'prepare_zstack_zram_build_metadata.py')
SPEC = importlib.util.spec_from_file_location('prepare_zstack_zram_build_metadata', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareZstackZramBuildMetadataTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source'
        self.source.mkdir()
        subprocess.check_call(['git', '-C', str(self.source), 'init', '-q'])
        for relative in ('service/go.mod', 'cli/go.mod', 'packaging/build-rpm.sh'):
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('base\n')
        subprocess.check_call(['git', '-C', str(self.source), 'add', '.'])
        subprocess.check_call(['git', '-C', str(self.source), '-c', 'user.name=Fixture',
                               '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'])
        self.snapshot = Path(self.temp.name) / 'snapshot'
        self.output = Path(self.temp.name) / 'build/metadata.properties'

    def test_freezes_checkout_and_emits_rpm_build_properties(self):
        (self.source / 'service/go.mod').write_text('changed\n')
        result = MODULE.prepare(self.source, self.snapshot, self.output,
                                '5.5.48.42', '1', '', 'test-builder',
                                'h84r,alinux4')
        manifest_bytes = (self.snapshot / 'SOURCE-SNAPSHOT.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(hashlib.sha256(manifest_bytes).hexdigest(),
                         result['zstackzram.sourceSnapshotSha256'])
        self.assertEqual(result['zstackzram.dirtyPatchSha256'], manifest['dirtyPatchSha256'])
        self.assertEqual('changed\n', (self.snapshot / 'source/service/go.mod').read_text())
        self.assertGreater(manifest['sourceDateEpoch'], 0)
        self.assertEqual('5.5.48.42', result['zstackzram.version'])
        self.assertEqual('1', result['zstackzram.release'])
        self.assertEqual(manifest['sourceDateEpoch'],
                         int(result['zstackzram.sourceDateEpoch']))
        self.assertEqual('alinux4,h84r', result['zstackzram.hostProfiles'])
        self.assertTrue(self.output.is_file())

    def test_rejects_untracked_inputs_and_existing_outputs(self):
        (self.source / 'service/extra.go').write_text('package service\n')
        with self.assertRaisesRegex(ValueError, 'UNTRACKED_SOURCE_INPUT_REFUSED'):
            MODULE.prepare(self.source, self.snapshot, self.output,
                           '5.5.48.42', '1', '', 'test-builder', 'h84r')
        self.assertFalse(self.snapshot.exists())
        self.assertFalse(self.output.exists())
        (self.source / 'service/extra.go').unlink()
        self.output.parent.mkdir(parents=True)
        self.output.write_text('existing\n')
        with self.assertRaisesRegex(ValueError, 'BUILD_METADATA_OUTPUT_EXISTS'):
            MODULE.prepare(self.source, self.snapshot, self.output,
                           '5.5.48.42', '1', '', 'test-builder', 'h84r')

    def test_explicit_source_date_epoch_cli_and_invalid_values(self):
        snapshot = Path(self.temp.name) / 'explicit-snapshot'
        output = Path(self.temp.name) / 'explicit-build/metadata.properties'
        subprocess.check_call([
            sys.executable, str(SCRIPT), '--source-checkout', str(self.source),
            '--snapshot-dir', str(snapshot), '--output', str(output),
            '--version', '5.5.48.42', '--release', '1',
            '--source-date-epoch', '1234567890',
            '--build-environment-id', 'test-builder', '--host-profiles', 'h84r',
        ], stdout=subprocess.DEVNULL)
        metadata = dict(line.split('=', 1) for line in output.read_text().splitlines())
        self.assertEqual('1234567890', metadata['zstackzram.sourceDateEpoch'])

        for invalid_epoch in ('not-a-number', '0'):
            with self.subTest(epoch=invalid_epoch):
                with self.assertRaisesRegex(ValueError, 'SOURCE_DATE_EPOCH_INVALID'):
                    MODULE.prepare(self.source,
                                   Path(self.temp.name) / ('invalid-snapshot-' + invalid_epoch),
                                   Path(self.temp.name) / ('invalid-build-' + invalid_epoch) / 'metadata.properties',
                                   '5.5.48.42', '1', invalid_epoch,
                                   'test-builder', 'h84r')

    def test_accepts_linked_worktree_and_rejects_nonroot_or_non_git_path(self):
        linked = Path(self.temp.name) / 'linked-checkout'
        subprocess.check_call(['git', '-C', str(self.source), 'worktree', 'add',
                               '--detach', str(linked), 'HEAD'],
                              stdout=subprocess.DEVNULL)
        self.assertTrue((linked / '.git').is_file())
        result = MODULE.prepare(linked, self.snapshot, self.output,
                                '5.5.48.42', '1', '', 'test-builder', 'h84r')
        self.assertEqual(subprocess.check_output(
            ['git', '-C', str(linked), 'rev-parse', 'HEAD'], text=True).strip(),
            result['zstackzram.sourceRevision'])
        clone_snapshot = Path(self.temp.name) / 'clone-snapshot'
        clone_output = Path(self.temp.name) / 'clone-build/metadata.properties'
        MODULE.prepare(self.source, clone_snapshot, clone_output,
                       '5.5.48.42', '1', '', 'test-builder', 'h84r')
        self.assertEqual((self.snapshot / 'SOURCE-SNAPSHOT.json').read_bytes(),
                         (clone_snapshot / 'SOURCE-SNAPSHOT.json').read_bytes())
        self.assertEqual((self.snapshot / 'dirty.patch').read_bytes(),
                         (clone_snapshot / 'dirty.patch').read_bytes())
        linked_files = sorted(path.relative_to(self.snapshot / 'source').as_posix()
                              for path in (self.snapshot / 'source').rglob('*') if path.is_file())
        clone_files = sorted(path.relative_to(clone_snapshot / 'source').as_posix()
                             for path in (clone_snapshot / 'source').rglob('*') if path.is_file())
        self.assertEqual(linked_files, clone_files)
        for relative in linked_files:
            self.assertEqual((self.snapshot / 'source' / relative).read_bytes(),
                             (clone_snapshot / 'source' / relative).read_bytes())

        nested_snapshot = Path(self.temp.name) / 'nested-snapshot'
        nested_output = Path(self.temp.name) / 'nested-build/metadata.properties'
        with self.assertRaisesRegex(ValueError, 'CANONICAL_GIT_CHECKOUT_REQUIRED'):
            MODULE.prepare(linked / 'service', nested_snapshot, nested_output,
                           '5.5.48.42', '1', '', 'test-builder', 'h84r')

        non_git = Path(self.temp.name) / 'non-git'
        non_git.mkdir()
        with self.assertRaisesRegex(ValueError, 'CANONICAL_GIT_CHECKOUT_REQUIRED'):
            MODULE.prepare(non_git, nested_snapshot, nested_output,
                           '5.5.48.42', '1', '', 'test-builder', 'h84r')


if __name__ == '__main__':
    unittest.main()
