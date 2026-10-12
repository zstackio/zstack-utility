import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = (Path(__file__).resolve().parents[2] / 'zstackbuild/scripts' /
          'freeze_zstack_zram_build_source.py')
SPEC = importlib.util.spec_from_file_location('freeze_zstack_zram_build_source', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FreezeZstackZramBuildSourceTest(unittest.TestCase):
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
        self.output = Path(self.temp.name) / 'snapshot'

    def test_freezes_git_revision_dirty_patch_and_epoch(self):
        (self.source / 'service/go.mod').write_text('changed\n')
        result = MODULE.freeze(self.source, self.output)
        manifest_bytes = (self.output / 'SOURCE-SNAPSHOT.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(hashlib.sha256(manifest_bytes).hexdigest(), result['manifestSha256'])
        self.assertEqual(result['dirtyPatchSha256'], manifest['dirtyPatchSha256'])
        self.assertEqual('changed\n', (self.output / 'source/service/go.mod').read_text())
        self.assertGreater(manifest['sourceDateEpoch'], 0)
        self.assertFalse(result['deployable'])

    def test_rejects_untracked_inputs_and_existing_output(self):
        (self.source / 'service/extra.go').write_text('package service\n')
        with self.assertRaisesRegex(ValueError, 'UNTRACKED_SOURCE_INPUT_REFUSED'):
            MODULE.freeze(self.source, self.output)
        self.assertFalse(self.output.exists())
        (self.source / 'service/extra.go').unlink()
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, 'ABSENT_EXTERNAL_OUTPUT_REQUIRED'):
            MODULE.freeze(self.source, self.output)


if __name__ == '__main__':
    unittest.main()
