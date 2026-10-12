import pathlib
import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[3]
BUILD = ROOT / 'zstackbuild'


@pytest.mark.integration
class ZstackZramAntTests(unittest.TestCase):
    def test_standard_and_oss_builds_import_rpm_project(self):
        for name in ('build.xml', 'build.oss.xml'):
            with self.subTest(name=name):
                root = ET.parse(BUILD / name).getroot()
                imports = [item.attrib.get('file', '') for item in root.findall('import')]
                self.assertTrue(any(path.endswith('/projects/zstack-zram.xml') for path in imports))

    def test_project_requires_exact_snapshot_pins_and_stages_rpm_into_kvm_files_tree(self):
        project_path = BUILD / 'projects/zstack-zram.xml'
        root = ET.parse(project_path).getroot()
        targets = {target.attrib['name']: target for target in root.findall('target')}
        self.assertIn('build-zstack-zram-rpm', targets)
        self.assertIn('stage-zstack-zram-rpm', targets)
        self.assertIn('assemble-zstack-zram-rpm', targets)
        build_xml = ET.tostring(root, encoding='unicode')
        for pin in ('zstackzram.checkout', 'zstackzram.frozenSource',
                    'zstackzram.sourceSnapshotManifest',
                    'zstackzram.sourceSnapshotSha256', 'zstackzram.sourceRevision',
                    'zstackzram.dirtyPatchSha256'):
            self.assertIn(pin, build_xml)
        self.assertIn('${zstackzram.checkout}', build_xml)
        self.assertIn('${zstackzram.frozenSource}', build_xml)
        self.assertNotIn('${zstackzram.source}', build_xml)
        assemble_xml = ET.tostring(targets['assemble-zstack-zram-rpm'], encoding='unicode')
        self.assertIn('files/kvm/memory-optimization/zstack-zram', assemble_xml)
        self.assertIn('rpm-inventory.json', assemble_xml)
        self.assertIn('install_memory_optimization_rpm.py', assemble_xml)
        self.assertIn('zstackzram.enabled', ET.tostring(root, encoding='unicode'))
        self.assertIn('prepare_zstack_zram_build_metadata.py', build_xml)
        self.assertNotIn('freeze_zstack_zram_build_source.py', build_xml)
        self.assertNotIn('<antcall', build_xml)
        self.assertNotIn('verify-source-snapshot.py', build_xml)
        self.assertIn('zstackzram.targetArch', build_xml)

    def test_standard_build_properties_define_scoped_rpm_arch_and_canonical_source(self):
        for name in ('build.properties', 'build.oss.properties'):
            properties = (BUILD / name).read_text()
            self.assertIn('zstackzram.checkout=${zstack_build_root}/zstack-zram', properties)
            self.assertNotIn('zstackzram.source=', properties)
            self.assertIn('zstackzram.targetArch=x86_64', properties)
            self.assertIn('zstackzram.hostProfiles=', properties)

    def test_standard_ant_build_uses_prepared_snapshot_after_checkout_mutation(self):
        ant = shutil.which('ant')
        ant_home = os.environ.get('ANT_HOME')
        if ant is None and ant_home:
            candidate = pathlib.Path(ant_home) / 'bin/ant'
            ant = str(candidate) if candidate.is_file() else None
        if ant is None:
            candidate = pathlib.Path('/dev/shm/apache-ant-1.10.18/bin/ant')
            ant = str(candidate) if candidate.is_file() else None
        if ant is None:
            self.fail('PINNED_ANT_1_10_18_REQUIRED_FOR_SOURCE_SNAPSHOT_TEST')

        utility = ROOT
        build_file = BUILD / 'build.xml'
        with tempfile.TemporaryDirectory(prefix='ant-frozen-source-r3-') as temp:
            root = pathlib.Path(temp)
            checkout = root / 'checkout'
            for relative in ('service', 'cli', 'packaging/rpm', 'packaging/tests'):
                (checkout / relative).mkdir(parents=True, exist_ok=True)
            (checkout / 'service/go.mod').write_text('module example.invalid/service\n')
            (checkout / 'cli/go.mod').write_text('module example.invalid/cli\n')
            (checkout / 'packaging/rpm/zram-memory.spec').write_text('frozen-spec\n')
            (checkout / 'packaging/probe.txt').write_text('before-freeze\n')
            required = {
                'packaging/build-rpm.sh': (
                    '#!/bin/sh\nset -eu\nout=\n'
                    'while [ "$#" -gt 0 ]; do\n'
                    '  if [ "$1" = --output ]; then out=$2; shift 2; else shift; fi\n'
                    'done\nmkdir -p "$out"\n'
                    'sha256sum packaging/probe.txt > "$out/used-frozen-source.sha256"\n'),
                'packaging/load-zram-module.sh': '#!/bin/sh\nexit 0\n',
                'packaging/qualification-check.sh': '#!/bin/sh\nexit 0\n',
                'packaging/tests/test_rpm_packaging.py': '# fixture\n',
                'packaging/tests/test-rpm-package.sh': '#!/bin/sh\nexit 0\n',
            }
            for relative, content in required.items():
                target = checkout / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
                target.chmod(0o755 if relative.endswith('.sh') else 0o644)
            (checkout / '.gitignore').write_text('target/\n')
            subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
            subprocess.run(['git', '-C', str(checkout), 'add', '-A'], check=True)
            subprocess.run(['git', '-C', str(checkout), '-c', 'user.name=Snapshot Test',
                            '-c', 'user.email=snapshot@example.invalid', 'commit', '-qm', 'fixture'],
                           check=True)

            wrapper = root / 'bin'
            wrapper.mkdir()
            real_python = shutil.which('python3')
            self.assertIsNotNone(real_python)
            mutation_file = checkout / 'packaging/probe.txt'
            python_wrapper = wrapper / 'python3'
            python_wrapper.write_text(
                '#!/bin/sh\nset -eu\n'
                '"' + real_python + '" "$@"\n'
                'case "$1" in *prepare_zstack_zram_build_metadata.py) '
                'printf "changed-after-freeze\\n" > "' + str(mutation_file) + '" ;; esac\n')
            python_wrapper.chmod(0o755)
            output = root / 'build-output'
            env = dict(os.environ)
            env['PATH'] = str(wrapper) + os.pathsep + env.get('PATH', '')
            env['ZSTACK_BUILD_ENVIRONMENT_ID'] = 'ant-prepared-source-r4-ut'
            command = [ant, '-f', str(build_file), 'build-zstack-zram-rpm',
                       '-Dzstackutility.source=' + str(utility),
                       '-Dzstackzram.checkout=' + str(checkout),
                       '-Dzstackzram.targetArch=x86_64',
                       '-Dproduct.version=5.5.48.42', '-Dbuild.num=42',
                       '-Dbuild_version=feature-5.5.48-mem-optimize',
                       '-Dbuild.dir=' + str(output),
                       '-Dzstackzram.rpm.output=' + str(output / 'rpm-output')]
            subprocess.run(command, cwd=BUILD, env=env, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=180)
            source_note = output / 'rpm-output/used-frozen-source.sha256'
            self.assertTrue(source_note.is_file())
            self.assertEqual(hashlib.sha256(b'before-freeze\n').hexdigest(),
                             source_note.read_text().split()[0])
            self.assertEqual('changed-after-freeze\n', mutation_file.read_text())
            metadata = (output / 'zstack-zram-build/metadata.properties').read_text()
            self.assertIn('zstackzram.version=5.5.48.42\n', metadata)
            self.assertIn('zstackzram.release=1\n', metadata)

    def test_kvmagent_assembly_depends_on_rpm_stage(self):
        root = ET.parse(BUILD / 'projects/zstack-kvmagent.xml').getroot()
        project_text = (BUILD / 'projects/zstack-kvmagent.xml').read_text()
        build_target = next(node for node in root.findall('target')
                            if node.attrib.get('name') == 'build-kvmagent')
        target = next(node for node in root.findall('target')
                      if node.attrib.get('name') == 'assemble-kvmagent')
        self.assertIn('assemble-zstack-zram-rpm', target.attrib.get('depends', ''))
        self.assertIn('kvmagent.ansible.dir', project_text)
        self.assertIn('location="${ansible.dir}/kvm/"', project_text)
        self.assertIn('<include name="**/*" />', project_text)
        build_fileset = next(node for node in build_target.findall('copy/fileset')
                             if node.attrib.get('dir') == '${kvmagent.source}/')
        self.assertIn('ansible/memory-optimization/ksmtuned/tests/**',
                      [item.attrib.get('name') for item in build_fileset.findall('exclude')])
        self.assertFalse((ROOT / 'kvmagent/ansible/memory-optimization/ksmtuned/tests').exists(),
                         'shell regression tests must remain test-only, not runtime payload')
        kvm_source = (ROOT / 'kvmagent/ansible/kvm.py').read_text()
        self.assertIn("file_root = \"files/kvm\"", kvm_source)
        self.assertIn("os.path.join(file_root, 'memory-optimization', 'zstack-zram')",
                      kvm_source)
        # Standard Ant assembly maps the exact source directory to
        # WEB-INF/classes/ansible/kvm/files/kvm, relative to kvm.py's cwd.
        self.assertIn('files/kvm/memory-optimization/zstack-zram',
                      (BUILD / 'projects/zstack-zram.xml').read_text())


if __name__ == '__main__':
    unittest.main()
