"""Run installer function with fake transport; never execute a playbook."""
import ast
import hashlib
import json
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest import TestCase


class TestMemoryInstallerScope(TestCase):
    def install(self, facts, arch='x86_64', release='h84r', bundle='', required='false'):
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ansible/kvm.py'))
        with open(path) as stream:
            tree = ast.parse(stream.read(), filename=path)
        names = ('install_memory_optimization_materials', '_memory_supported_host',
                 '_memory_optimization_rpm_input', '_install_memory_optimization_rpm')
        module = ast.Module(body=[n for n in tree.body if
                                  (isinstance(n, ast.FunctionDef) and n.name in names) or
                                  (isinstance(n, ast.Import) and any(a.name in ('hashlib', 'json', 're', 'shlex') for a in n.names))],
                            type_ignores=[])
        # Exercise the no-payload/KSM-only case without accidentally finding
        # an incomplete checkout staging directory beside the real playbook.
        runtime_file = path
        if not bundle:
            runtime_root = tempfile.mkdtemp(prefix='memory-optimization-no-bundle-')
            self.addCleanup(shutil.rmtree, runtime_root, ignore_errors=True)
            runtime_file = os.path.join(runtime_root, 'ansible', 'kvm.py')
        calls = []
        env = {'os': os, 'hashlib':hashlib, 'json':json, 're':__import__('re'),
               'shlex':__import__('shlex'), '__file__':runtime_file, 'releasever':release,
               'host_info':SimpleNamespace(host_arch=arch, ansible_distribution=facts),
               'memory_optimization_bundle':bundle,
               'memory_optimization_bundle_required':required,
               'logger':SimpleNamespace(warn=lambda *args: None),
               'file_root':'/not-a-real-installer', 'host_post_info':object(),
               'run_remote_command':lambda *a, **kw: calls.append(('run',a)),
               'copy_to_remote':lambda *a, **kw: calls.append(('copy',a))}
        exec(compile(module, path, 'exec'), env)
        env['install_memory_optimization_materials']()
        return calls

    def test_host_ksm_refresh_skips_sysfs_write_during_managed_or_pending_ownership(self):
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../ansible/kvm.py'))
        with open(path) as stream:
            tree = ast.parse(stream.read(), filename=path)
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == 'do_ksm_config')
        calls = []
        env = {'isEnableKsm': 'true', 'host_post_info': SimpleNamespace(),
               'run_remote_command': lambda *args, **kwargs: calls.append(args)}
        exec(compile(ast.Module(body=[function], type_ignores=[]), path, 'exec'), env)
        env['do_ksm_config']()
        command = calls[0][0]
        self.assertIn('/etc/zstack/memory-optimization/ksm-controller', command)
        self.assertIn('/etc/zstack/memory-optimization/legacy-ksmtuned.state', command)
        self.assertIn('/sys/kernel/mm/ksm/run', command)

    def test_managed_systemd_unit_conflicts_with_both_native_writers(self):
        path = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                            '../../ansible/memory-optimization/ksmtuned/zstack-ksmtuned.service'))
        with open(path) as stream:
            unit = stream.read()
        self.assertIn('Before=ksm.service ksmtuned.service', unit)
        self.assertIn('Conflicts=ksm.service ksmtuned.service', unit)
        self.assertIn('ProtectSystem=full', unit)
        self.assertNotIn('ReadWritePaths=/etc/systemd/system', unit)

    def bundle(self, complete=True):
        root = tempfile.mkdtemp(prefix='memory-optimization-bundle-')
        filename = 'zstack-zram-1.2.3-1.x86_64.rpm'
        if complete:
            with open(os.path.join(root, filename), 'wb') as stream:
                stream.write(b'fixture-rpm-bytes')
        package_path = os.path.join(root, filename)
        if complete:
            with open(package_path, 'rb') as stream:
                package_sha = hashlib.sha256(stream.read()).hexdigest()
        else:
            package_sha = 'a' * 64
        required = sorted([
            '/etc/zram-memory/config.json',
            '/usr/lib/systemd/system/zram-memory.service',
            '/usr/local/libexec/zram-efficiency',
            '/usr/local/bin/zram-efficiencyctl',
            '/usr/local/libexec/zstack-zram/zramctl',
            '/usr/local/libexec/zstack-zram/bootstrap-config',
            '/usr/local/libexec/zstack/memory-optimization-bundle/bin/load-zram-module',
            '/usr/local/libexec/zstack/memory-optimization-bundle/bin/check-qualification',
            '/usr/share/zstack-zram/config.json'])
        build_manifest = {'schemaVersion': 1, 'package': 'zstack-zram',
                          'rpmVersion': '1.2.3', 'rpmRelease': '1',
                          'sourceRevision': 'a' * 40,
                          'sourceSnapshotSha256': 'c' * 64,
                          'dirtyPatchSha256': 'b' * 64,
                          'sourceFiles': [{'path': 'service/packaging/systemd/zram-memory.service',
                                           'sha256': 'd' * 64}]}
        build_manifest_path = os.path.join(root, 'BUILD-MANIFEST.json')
        with open(build_manifest_path, 'w') as stream:
            json.dump(build_manifest, stream)
        with open(build_manifest_path, 'rb') as stream:
            build_manifest_sha = hashlib.sha256(stream.read()).hexdigest()
        inventory = {
            'schemaVersion': 3, 'trustModel': 'content-hash-pinned-not-signed',
            'package': {'name': 'zstack-zram', 'version': '1.2.3', 'release': '1',
                        'architecture': 'x86_64', 'filename': filename,
                        'bytes': 17, 'sha256': package_sha},
            'source': {'sourceRevision': 'a' * 40, 'dirtyPatchSha256': 'b' * 64,
                       'sourceSnapshotSha256': 'c' * 64, 'buildManifestSha256': build_manifest_sha},
            'supportedHostProfiles': ['h84r', 'alinux4', 'ky10sp1', 'ky10sp2', 'ky10sp3', 'ky10sp3.2403'],
            'requiredFiles': required, 'kernelOrModuleIncluded': False,
            'configNoreplace': True, 'scriptletsEmpty': True,
            'systemdUnitSha256': 'd' * 64,
            'runtimeBinaries': {
                '/usr/local/libexec/zram-efficiency': {'bytes': 111, 'sha256': 'e' * 64},
                '/usr/local/bin/zram-efficiencyctl': {'bytes': 222, 'sha256': 'f' * 64},
            },
        }
        installer_path = os.path.join(root, 'install_memory_optimization_rpm.py')
        with open(installer_path, 'wb') as stream:
            stream.write(b'installer-fixture')
        with open(installer_path, 'rb') as stream:
            installer_bytes = stream.read()
        inventory['installer'] = {
            'filename': 'install_memory_optimization_rpm.py',
            'bytes': len(installer_bytes),
            'sha256': hashlib.sha256(installer_bytes).hexdigest()}
        inventory['rpmFiles'] = sorted(required)
        inventory['rpmFilesSha256'] = hashlib.sha256(
            ''.join(path + '\n' for path in inventory['rpmFiles']).encode()).hexdigest()
        with open(os.path.join(root, 'rpm-inventory.json'), 'w') as stream:
            json.dump(inventory, stream)
        return root

    def inventory_hash(self, root):
        with open(os.path.join(root, 'rpm-inventory.json')) as stream:
            return json.load(stream)['rpmFilesSha256']

    def test_supported_x86_os_gets_materials_without_implicit_activation(self):
        for facts, release in [('helix green obsidian 8.4r','h84r'),
                               ('alibaba cloud linux pro edition 4','alinux4'),
                               ('alibaba openanolis edition 4','alinux4'),
                               ('kylin_lance lance 10','ky10sp3'),
                               ('kylin_halberd halberd 10','ky10sp3.2403')]:
            with self.subTest(facts=facts):
                calls = self.install(facts, release=release)
                self.assertTrue(any(kind=='copy' for kind,args in calls))
                commands = '\n'.join(args[0] for kind,args in calls if kind=='run')
                self.assertNotIn('systemctl start', commands)
                self.assertNotIn('systemctl enable', commands)

    def test_management_node_fallback_does_not_qualify_unknown_host(self):
        for facts in ('rocky green obsidian 8.4', 'unknown anything 8.4', ''):
            self.assertEqual([], self.install(facts, release='h84r'))

    def test_non_x86_is_not_installed(self):
        self.assertEqual([], self.install('helix green obsidian 8.4r', arch='aarch64'))

    def test_rpm_package_manager_installs_without_activating_or_copying_service_files(self):
        root = self.bundle()
        calls = self.install('helix green obsidian 8.4r', bundle=root, required='true')
        commands = '\n'.join(args[0] for kind, args in calls if kind == 'run')
        self.assertIn('python3 "$installer_file" --inventory "$inventory_file" --rpm "$rpm_file"', commands)
        self.assertIn('sha256sum -c -', commands)
        self.assertIn('sha256sum -c -', commands)
        self.assertNotIn('/sys/block/zram0/mm_stat', commands)
        self.assertNotIn('bootstrap-control', commands)
        self.assertNotIn('install-runtime-assets', commands)
        self.assertNotIn('systemctl enable', commands)
        self.assertNotIn('systemctl start', commands)
        self.assertNotIn('systemctl restart', commands)
        self.assertTrue(any(kind == 'copy' and '.inventory.json' in args[1]
                            for kind, args in calls))
        self.assertTrue(any(kind == 'copy' and args[1].endswith('install_memory_optimization_rpm.py')
                            for kind, args in calls))
        copied_sources = [args[0] for kind, args in calls if kind == 'copy']
        self.assertEqual(1, sum('/zstack-zram-' in source for source in copied_sources))

    def test_required_missing_rpm_is_not_silently_ignored(self):
        with self.assertRaisesRegex(RuntimeError, 'MEMORY_OPTIMIZATION_RPM_INVALID'):
            self.install('helix green obsidian 8.4r', bundle=self.bundle(complete=False), required='true')

    def test_rendered_rpm_config_noreplace_query_uses_native_percent_syntax(self):
        root = self.bundle()
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        calls = self.install('helix green obsidian 8.4r', bundle=root, required='true')
        command = next(args[0] for kind, args in calls
                       if kind == 'run' and 'FILEFLAGS:fflags' in args[0])
        # This nested fragment is substituted as a %s value, not formatted a
        # second time. Assert the final wire command, not the source template.
        self.assertIn('rpm -qp --qf "[%{FILENAMES} %{FILEFLAGS:fflags}\\n]" "$rpm_file"', command)
        self.assertNotIn('%%{', command)
        self.assertIn("grep -Fxq '/etc/zram-memory/config.json cn'", command)
        self.assertLess(command.index('FILEFLAGS:fflags'),
                        command.index('python3 "$installer_file"'))

    def test_declared_rpm_hash_failure_is_not_silently_ignored(self):
        root = self.bundle()
        with open(os.path.join(root, 'zstack-zram-1.2.3-1.x86_64.rpm'), 'ab') as stream:
            stream.write(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, 'RPM_FILE_SIZE_MISMATCH|RPM_FILE_SHA256_MISMATCH'):
            self.install('helix green obsidian 8.4r', bundle=root, required='true')

    def test_rpm_inventory_rejects_unapproved_os_profile_and_non_x86_abi(self):
        with self.assertRaisesRegex(RuntimeError, 'RPM_HOST_ABI_PROFILE_UNSUPPORTED'):
            self.install('helix green obsidian 8.4r', release='unlisted-profile',
                         bundle=self.bundle(), required='true')

    def test_rpm_inventory_rejects_unpinned_or_unsorted_package_members(self):
        root = self.bundle()
        inventory_path = os.path.join(root, 'rpm-inventory.json')
        with open(inventory_path) as stream:
            inventory = json.load(stream)
        inventory['rpmFiles'].append('/usr/share/unlisted')
        with open(inventory_path, 'w') as stream:
            json.dump(inventory, stream)
        with self.assertRaisesRegex(RuntimeError, 'RPM_FILE_INVENTORY_INVALID'):
            self.install('helix green obsidian 8.4r', bundle=root, required='true')

    def test_osabi_refusal_happens_before_any_remote_mutation(self):
        self.assertEqual([], self.install('unknown linux 1', release='h84r',
                                          bundle=self.bundle(), required='true'))

    def test_agent_retry_is_package_manager_idempotent_without_service_activation(self):
        root = self.bundle()
        first = self.install('helix green obsidian 8.4r', bundle=root, required='true')
        second = self.install('helix green obsidian 8.4r', bundle=root, required='true')
        for calls in (first, second):
            commands = '\n'.join(args[0] for kind, args in calls if kind == 'run')
            self.assertIn('python3 "$installer_file" --inventory "$inventory_file" --rpm "$rpm_file"', commands)
            self.assertIn('systemctl daemon-reload', commands)
            for forbidden in ('systemctl start zram-memory', 'systemctl enable zram-memory',
                              'systemctl restart zram-memory', 'swapoff', 'zramctl reset'):
                self.assertNotIn(forbidden, commands)
