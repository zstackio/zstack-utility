import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.kvmagent]


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / 'kvmagent' / 'scripts' / 'install_memory_optimization_rpm.py'
SPEC = importlib.util.spec_from_file_location('install_memory_optimization_rpm', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class InstallerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        boot = self.root / 'proc/sys/kernel/random/boot_id'
        boot.parent.mkdir(parents=True)
        boot.write_text('00000000-0000-4000-8000-000000000001\n')
        self.rpm = self.root / 'test.rpm'
        self.rpm.write_bytes(b'pinned rpm')
        self.unit_text = ('[Service]\nKillMode=process\nRestart=no\n' +
                          MODULE.EXPECTED_EXECSTART + '\n' +
                          MODULE.EXPECTED_EXECSTARTPRE + '\n')
        self.unit_sha = hashlib.sha256(self.unit_text.encode()).hexdigest()
        self.binary_bytes = b'#!/bin/sh\n# expected zram-efficiency build\nexit 0\n'
        self.ctl_bytes = b'#!/bin/sh\n# expected zram-efficiencyctl build\nexit 0\n'
        self.runtime_binaries = {
            MODULE.EXECUTABLE_PATH: {
                'bytes': len(self.binary_bytes),
                'sha256': hashlib.sha256(self.binary_bytes).hexdigest()},
            '/usr/local/bin/zram-efficiencyctl': {
                'bytes': len(self.ctl_bytes),
                'sha256': hashlib.sha256(self.ctl_bytes).hexdigest()},
        }
        self.factory_config = {
            'version': 2, 'mode': 'observe', 'managed': True,
            'resource_authorized': False, 'initial_efficiency_enabled': False,
            'vm_selection': 'all_running', 'vm_uuids': [],
            'state_dir': '/var/lib/zram-efficiency',
            'monitor_socket': '/run/zram-efficiency-admission/monitor.sock',
            'control_socket': '/run/zram-efficiency-admission/control.sock',
            'device': '/dev/zram0', 'internal_rule': {}, 'budget': {},
        }
        self.inventory_path = self.root / 'inventory.json'
        self.inventory_path.write_text(json.dumps({
            'schemaVersion': 3,
            'trustModel': 'content-hash-pinned-not-signed',
            'package': {'name': 'zstack-zram', 'architecture': 'x86_64',
                        'version': '1.2.3', 'release': '4',
                        'filename': 'test.rpm', 'bytes': self.rpm.stat().st_size,
                        'sha256': hashlib.sha256(self.rpm.read_bytes()).hexdigest()},
            'systemdUnitSha256': self.unit_sha,
            'runtimeBinaries': self.runtime_binaries,
            'kernelOrModuleIncluded': False, 'configNoreplace': True,
            'scriptletsEmpty': True,
        }))
        self.active = False
        self.installed = False
        self.installed_version = None
        self.rpm_owned = {}
        self.pid = '123'
        self.calls = []

    def runner(self, argv, **kwargs):
        argv = list(map(str, argv))
        self.calls.append(argv)
        if argv[:3] == ['systemctl', 'is-active', 'zram-memory.service']:
            if self.active:
                return 'active\n'
            raise subprocess.CalledProcessError(3, argv, output='inactive\n')
        if argv[:2] == ['systemctl', 'show']:
            fragment = MODULE.UNIT_PATH if self.installed else ''
            if self.active and getattr(self, 'fragment', None):
                fragment = self.fragment
            return 'FragmentPath=%s\nMainPID=%s\nDropInPaths=\nKillMode=process\nRestart=no\nExecStop=\nExecStopPost=\n' % (fragment, self.pid if self.active else '0')
        if argv[:2] == ['systemctl', 'is-enabled']:
            return 'enabled\n'
        if argv[:2] == ['systemctl', 'start']:
            self.active = True
            return ''
        if argv[:2] == ['rpm', '-q']:
            if not self.installed:
                raise subprocess.CalledProcessError(1, argv, output='not installed')
            if len(argv) > 3 and argv[2] == '--qf' and argv[3].startswith('['):
                return ''.join('%s\t%s\n' % (path, digest)
                               for path, digest in sorted(self.rpm_owned.items()))
            return (self.installed_version or '1.2.3-4') + '\n'
        if len(argv) >= 2 and argv[1] == '--version':
            return '{"version":"1.2.3-4"}\n'
        return ''

    def install_package(self, root, rpm):
        self.calls.append(['package-install', rpm])
        unit = Path(root) / MODULE.UNIT_PATH.lstrip('/')
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(self.unit_text)
        self.rpm_owned[MODULE.UNIT_PATH] = MODULE._hash(unit)
        binary = Path(root) / MODULE.EXECUTABLE_PATH.lstrip('/')
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(self.binary_bytes)
        binary.chmod(0o755)
        self.rpm_owned[MODULE.EXECUTABLE_PATH] = MODULE._hash(binary)
        ctl = Path(root) / 'usr/local/bin/zram-efficiencyctl'
        ctl.parent.mkdir(parents=True, exist_ok=True)
        ctl.write_bytes(self.ctl_bytes)
        ctl.chmod(0o755)
        self.rpm_owned['/usr/local/bin/zram-efficiencyctl'] = MODULE._hash(ctl)
        self.installed = True
        self.installed_version = '1.2.3-4'
        config = Path(root) / 'etc/zram-memory/config.json'
        config.parent.mkdir(parents=True, exist_ok=True)
        if not config.exists():
            config.write_text(json.dumps(self.factory_config, sort_keys=True) + '\n')
        default = Path(root) / 'usr/share/zstack-zram/config.json'
        default.parent.mkdir(parents=True, exist_ok=True)
        default.write_text(json.dumps(self.factory_config, sort_keys=True) + '\n')
        # Do not fabricate PID reuse after a product controller was retired.
        # During active upgrades prepare_active_upgrade changes pid to 0 at
        # SIGTERM and the fake systemd start allocates a distinct PID.
        if getattr(self, 'pid', None) != '0':
            proc = Path(root) / 'proc/123'
            proc.mkdir(parents=True, exist_ok=True)
            (proc / 'stat').write_text('123 (zram-efficiency) ' + ' '.join(
                ['S'] + ['0'] * 18 + ['456789']))
            exe = proc / 'exe'
            if exe.exists() or exe.is_symlink():
                exe.unlink()
            exe.symlink_to(binary)

    def test_installed_factory_package_starts_observe_controller_without_enabling_efficiency(self):
        first = MODULE.install(self.root, self.inventory_path, self.rpm,
                               runner=self.runner, installer=self.install_package)
        self.assertEqual('INSTALLED_OBSERVING', first['status'])
        self.assertTrue(self.active)
        config = json.loads((self.root / 'etc/zram-memory/config.json').read_text())
        self.assertEqual('observe', config['mode'])
        self.assertFalse(config['resource_authorized'])
        self.assertFalse(config['initial_efficiency_enabled'])
        self.assertTrue(any(call[:3] == ['systemctl', 'enable', 'zram-memory.service']
                            for call in self.calls))
        self.assertTrue(any(call[:3] == ['systemctl', 'start', 'zram-memory.service']
                            for call in self.calls))

    def test_custom_config_is_preserved_and_never_implicitly_started(self):
        custom = self.root / 'etc/zram-memory/config.json'
        custom.parent.mkdir(parents=True)
        custom.write_text('{"managed":true,"operator":"custom"}\n')
        before = custom.read_bytes()
        MODULE.install(self.root, self.inventory_path, self.rpm,
                       runner=self.runner, installer=self.install_package)
        self.assertEqual(before, custom.read_bytes())
        self.assertFalse(self.active)
        self.assertFalse(any(call[:2] == ['systemctl', 'start'] for call in self.calls))

    def test_unmanaged_override_fails_before_package_or_config_mutation(self):
        override = self.root / MODULE.OVERRIDE_PATH.lstrip('/')
        override.parent.mkdir(parents=True)
        override.write_text('operator custom unit')
        config = self.root / 'etc/zram-memory/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{"unchanged":true}')
        with self.assertRaisesRegex(MODULE.InstallError, 'UNMANAGED_UNIT_OVERRIDE_PRESENT'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=self.runner, installer=self.install_package)
        self.assertEqual('operator custom unit', override.read_text())
        self.assertEqual('{"unchanged":true}', config.read_text())
        self.assertFalse(any(call[0] == 'package-install' for call in self.calls))
    def test_unmanaged_dropin_is_rejected_before_package_mutation(self):
        dropin = self.root / 'etc/systemd/system/zram-memory.service.d/20-custom.conf'
        dropin.parent.mkdir(parents=True)
        dropin.write_text('[Service]\nRestart=always\n')
        with self.assertRaisesRegex(MODULE.InstallError, 'UNMANAGED_UNIT_DROPIN_PRESENT'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=self.runner, installer=self.install_package)
        self.assertTrue(dropin.exists())
        self.assertFalse(any(call[0] == 'package-install' for call in self.calls))

    def test_effective_dropin_from_other_location_is_rejected(self):
        def customized(argv, **kwargs):
            if argv[:2] == ['systemctl', 'show']:
                return 'FragmentPath=%s\nDropInPaths=/custom/unit.conf\n' % MODULE.UNIT_PATH
            return self.runner(argv, **kwargs)

        with self.assertRaisesRegex(MODULE.InstallError, 'UNMANAGED_UNIT_DROPIN_PRESENT'):
            MODULE.install(self.root, self.inventory_path, self.rpm, runner=customized,
                           installer=self.install_package)

    def test_first_rpm_adoption_preserves_existing_config_even_if_rpm_replaces_it(self):
        config = self.root / 'etc/zram-memory/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{"enabled":false,"policy":"existing"}')
        config.chmod(0o600)

        def replacing(root, rpm):
            self.install_package(root, rpm)
            config.write_text('{"new":"defaults"}')

        MODULE.install(self.root, self.inventory_path, self.rpm,
                       runner=self.runner, installer=replacing)
        self.assertEqual('{"enabled":false,"policy":"existing"}', config.read_text())
        self.assertEqual(0o600, config.stat().st_mode & 0o777)

    def prepare_active_upgrade(self):
        self.active = True
        self.installed = True
        self.installed_version = '1.2.2-3'
        self.pid = '123'
        self.fragment = MODULE.UNIT_PATH
        unit = self.root / MODULE.UNIT_PATH.lstrip('/')
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_text(self.unit_text + '# previous released RPM\n')
        self.rpm_owned[MODULE.UNIT_PATH] = MODULE._hash(unit)
        old = self.root / MODULE.EXECUTABLE_PATH.lstrip('/')
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_bytes(b'verified previous released RPM runtime')
        self.rpm_owned[MODULE.EXECUTABLE_PATH] = MODULE._hash(old)
        self.old_hash = MODULE._hash(old)
        self.old = old
        proc_dir = self.root / 'proc/123'
        proc_dir.mkdir(parents=True)
        (proc_dir / 'exe').symlink_to(old)
        (proc_dir / 'stat').write_text('123 (zram-efficiency) ' + ' '.join(['S'] + ['0'] * 18 + ['456789']))
        def upgrade_runner(argv, **kwargs):
            argv = list(map(str, argv))
            if argv[:2] == ['systemctl', 'show']:
                return ('FragmentPath=%s\nMainPID=%s\nDropInPaths=\n'
                        'KillMode=process\nRestart=no\nExecStop=\nExecStopPost=\n') % (self.fragment, self.pid)
            if argv[:2] == ['rpm', '-q']:
                return self.runner(argv, **kwargs)
            if argv[:2] == ['systemctl', 'kill']:
                self.calls.append(argv)
                self.active = False
                self.pid = '0'
                (proc_dir / 'stat').unlink()
                (proc_dir / 'exe').unlink()
                return ''
            if argv[:2] == ['systemctl', 'start']:
                self.calls.append(argv)
                self.active = True
                self.pid = '456'
                new_proc = self.root / 'proc/456'
                new_proc.mkdir()
                (new_proc / 'exe').symlink_to(self.old)
                (new_proc / 'stat').write_text('456 (current) ' + ' '.join(['S'] + ['0'] * 18 + ['789012']))
                return ''
            return self.runner(argv, **kwargs)

        def upgrade_install(root, rpm):
            self.assertFalse(self.active)
            self.install_package(root, rpm)
            self.installed = True
            self.fragment = MODULE.UNIT_PATH

        return upgrade_runner, upgrade_install

    def test_active_released_package_upgrade_preserves_policy_unknown_and_pool_without_drain(self):
        runner, installer = self.prepare_active_upgrade()
        preserved = []
        for name, body in (
                ('etc/zram-memory/config.json', b'{"enabled":false}'),
                ('var/lib/zram-efficiency/policy.json', b'{"vm_excluded":true}'),
                ('var/lib/zram-efficiency/operations/id/created.json', b'{"state":"Unknown"}'),
                ('sys/block/zram0/mm_stat', b'550000000 200000000')):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            preserved.append((path, body))
        result = MODULE.install(self.root, self.inventory_path, self.rpm,
                                runner=runner, installer=installer)
        self.assertEqual('UPGRADED_ACTIVE', result['status'])
        self.assertEqual(self.old_hash, result['previousController']['sha256'])
        for path, body in preserved:
            self.assertEqual(body, path.read_bytes())
        self.assertIn(['systemctl', 'kill', '--kill-who=main', '--signal=SIGTERM',
                       'zram-memory.service'], self.calls)
        self.assertFalse(any(any(word in call for word in ('stop', 'SIGKILL', 'swapoff', 'reset', 'enable'))
                             for call in self.calls))
        self.assertTrue(self.active)

    def test_active_empty_pool_is_not_required_for_userspace_upgrade(self):
        runner, installer = self.prepare_active_upgrade()
        result = MODULE.install(self.root, self.inventory_path, self.rpm,
                                runner=runner, installer=installer)
        self.assertEqual('UPGRADED_ACTIVE', result['status'])
        self.assertFalse((self.root / 'sys/block/zram0').exists())

    def test_graceful_exit_waits_for_systemd_deactivation_after_main_pid_exits(self):
        runner, _ = self.prepare_active_upgrade()
        observations = []

        def transitioning(argv, **kwargs):
            if argv[:2] == ['systemctl', 'is-active'] and self.pid == '0':
                observations.append('state')
                if len(observations) == 1:
                    raise subprocess.CalledProcessError(3, argv, output='deactivating\n')
            return runner(argv, **kwargs)

        inventory = json.loads(self.inventory_path.read_text())
        sleeps = []
        result = MODULE._graceful_old_controller_exit(
            self.root, transitioning, sleep=sleeps.append)
        self.assertEqual(self.old_hash, result['sha256'])
        self.assertEqual(2, len(observations))
        self.assertEqual([0.1], sleeps)

    def test_graceful_exit_does_not_hide_unreadable_systemd_state(self):
        runner, _ = self.prepare_active_upgrade()

        def unreadable(argv, **kwargs):
            if argv[:2] == ['systemctl', 'is-active'] and self.pid == '0':
                raise subprocess.CalledProcessError(1, argv, output='not-readable\n')
            return runner(argv, **kwargs)

        inventory = json.loads(self.inventory_path.read_text())
        with self.assertRaisesRegex(MODULE.InstallError, 'SERVICE_STATE_UNVERIFIABLE'):
            MODULE._graceful_old_controller_exit(self.root, unreadable)

    def test_unrecognized_active_binary_is_not_signalled(self):
        runner, installer = self.prepare_active_upgrade()
        self.rpm_owned[MODULE.EXECUTABLE_PATH] = '0' * 64
        with self.assertRaisesRegex(MODULE.InstallError, 'BINARY_UNKNOWN'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=runner, installer=installer)
        self.assertTrue(self.active)
        self.assertFalse(any(call[:2] == ['systemctl', 'kill'] for call in self.calls))

    def test_hung_controller_times_out_without_kill_or_package_write(self):
        runner, _ = self.prepare_active_upgrade()

        def hung(argv, **kwargs):
            if argv[:2] == ['systemctl', 'kill']:
                self.calls.append(list(argv))
                return ''
            return runner(argv, **kwargs)

        inventory = json.loads(self.inventory_path.read_text())
        with self.assertRaisesRegex(MODULE.InstallError, 'EXIT_TIMEOUT_POOL_PRESERVED'):
            MODULE._graceful_old_controller_exit(self.root, hung, timeout=0)
        self.assertTrue(self.active)
        self.assertFalse(any(call[0] == 'package-install' or 'SIGKILL' in call for call in self.calls))

    def test_failed_start_does_not_claim_upgrade_success(self):
        runner, installer = self.prepare_active_upgrade()

        def failed_start(argv, **kwargs):
            if argv[:2] == ['systemctl', 'start']:
                raise subprocess.CalledProcessError(1, argv)
            return runner(argv, **kwargs)

        with self.assertRaises(subprocess.CalledProcessError):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=failed_start, installer=installer)
        self.assertFalse(self.active)

    def test_failed_transaction_retry_restores_original_active_intent(self):
        runner, installer = self.prepare_active_upgrade()
        with self.assertRaisesRegex(RuntimeError, 'transaction failed'):
            MODULE.install(self.root, self.inventory_path, self.rpm, runner=runner,
                           installer=mock.Mock(side_effect=RuntimeError('transaction failed')))
        self.assertFalse(self.active)
        result = MODULE.install(self.root, self.inventory_path, self.rpm,
                                runner=runner, installer=installer)
        self.assertEqual('UPGRADED_ACTIVE', result['status'])
        self.assertTrue(self.active)
        self.assertFalse((self.root / MODULE.RECOVERY_PATH.lstrip('/')).exists())

    def test_failed_new_start_retry_restores_original_active_intent(self):
        runner, installer = self.prepare_active_upgrade()

        def failed_start(argv, **kwargs):
            if argv[:2] == ['systemctl', 'start']:
                raise subprocess.CalledProcessError(1, argv)
            return runner(argv, **kwargs)

        with self.assertRaises(subprocess.CalledProcessError):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=failed_start, installer=installer)
        result = MODULE.install(self.root, self.inventory_path, self.rpm,
                                runner=runner, installer=installer)
        self.assertEqual('UPGRADED_ACTIVE', result['status'])
        self.assertTrue(self.active)

    def test_retry_rejects_changed_config_without_overwriting_new_policy(self):
        runner, installer = self.prepare_active_upgrade()
        config = self.root / 'etc/zram-memory/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{"enabled":false}')
        with self.assertRaises(RuntimeError):
            MODULE.install(self.root, self.inventory_path, self.rpm, runner=runner,
                           installer=mock.Mock(side_effect=RuntimeError('transaction failed')))
        config.write_text('{"enabled":true}')
        self.calls.clear()
        with self.assertRaisesRegex(MODULE.InstallError, 'UPGRADE_RECOVERY_CONFIG_CHANGED'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=runner, installer=installer)
        self.assertEqual('{"enabled":true}', config.read_text())
        self.assertFalse(any(c[0] == 'package-install' or 'start' in c for c in self.calls))

    def test_retry_rejects_different_candidate_rpm(self):
        runner, installer = self.prepare_active_upgrade()
        with self.assertRaises(RuntimeError):
            MODULE.install(self.root, self.inventory_path, self.rpm, runner=runner,
                           installer=mock.Mock(side_effect=RuntimeError('transaction failed')))
        self.rpm.write_bytes(b'another candidate')
        inv = json.loads(self.inventory_path.read_text())
        inv['package'].update(bytes=self.rpm.stat().st_size, sha256=MODULE._hash(self.rpm))
        self.inventory_path.write_text(json.dumps(inv))
        with self.assertRaisesRegex(MODULE.InstallError, 'UPGRADE_RECOVERY_TARGET_MISMATCH'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=runner, installer=installer)

    def test_recovery_fsync_failure_cannot_signal_or_install(self):
        runner, installer = self.prepare_active_upgrade()
        sync = MODULE._sync_path

        def fail_recovery(path):
            if Path(path).name == 'zstack-zram':
                raise OSError('injected recovery fsync failure')
            sync(path)

        with mock.patch.object(MODULE, '_sync_path', side_effect=fail_recovery):
            with self.assertRaisesRegex(OSError, 'recovery fsync'):
                MODULE.install(self.root, self.inventory_path, self.rpm,
                               runner=runner, installer=installer)
        self.assertTrue(self.active)
        self.assertFalse(any(c[0] == 'package-install' or 'kill' in c for c in self.calls))

    def test_active_unmanaged_override_is_rejected_before_signal_or_package_change(self):
        runner, installer = self.prepare_active_upgrade()
        override = self.root / MODULE.OVERRIDE_PATH.lstrip('/')
        override.parent.mkdir(parents=True)
        override.write_text('unmanaged systemd override')
        with self.assertRaisesRegex(MODULE.InstallError, 'UNMANAGED_UNIT_OVERRIDE_PRESENT'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=runner, installer=installer)
        self.assertTrue(override.exists())
        self.assertFalse(any(c[0] == 'package-install' or 'kill' in c for c in self.calls))
        self.assertFalse((self.root / 'var/lib/zstack-zram/upgrade-config-archive').exists())
        self.assertFalse((self.root / MODULE.RECOVERY_PATH.lstrip('/')).exists())

    def test_invalid_recovery_record_is_rejected_without_install(self):
        path = self.root / MODULE.RECOVERY_PATH.lstrip('/')
        path.parent.mkdir(parents=True)
        for payload in ('[]', '{}', 'null', '{bad-json'):
            with self.subTest(payload=payload):
                path.write_text(payload)
                path.chmod(0o600)
                with self.assertRaisesRegex(MODULE.InstallError, 'UPGRADE_RECOVERY_INVALID'):
                    MODULE.install(self.root, self.inventory_path, self.rpm,
                                   runner=self.runner, installer=self.install_package)
        self.assertFalse(any(c[0] == 'package-install' for c in self.calls))

    def test_untrusted_recovery_permissions_and_symlink_are_rejected(self):
        path = self.root / MODULE.RECOVERY_PATH.lstrip('/')
        path.parent.mkdir(parents=True)
        path.write_text('{}')
        path.chmod(0o644)
        with self.assertRaisesRegex(MODULE.InstallError, 'UPGRADE_RECOVERY_NOT_REGULAR'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=self.runner, installer=self.install_package)
        path.unlink()
        path.symlink_to(self.inventory_path)
        with self.assertRaisesRegex(MODULE.InstallError, 'UPGRADE_RECOVERY_NOT_REGULAR'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=self.runner, installer=self.install_package)

    def test_retry_does_not_replace_binary_while_original_controller_is_still_alive(self):
        runner, installer = self.prepare_active_upgrade()
        inv = json.loads(self.inventory_path.read_text())
        identity = MODULE._old_controller_identity(self.root, runner)
        MODULE._write_recovery(self.root, inv['package'], identity, None)
        self.active = False  # inconsistent service manager observation
        with self.assertRaisesRegex(MODULE.InstallError, 'OLD_CONTROLLER_STILL_RUNNING'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=runner, installer=installer)
        self.assertFalse(any(c[0] == 'package-install' or 'kill' in c for c in self.calls))

    def test_successful_active_retry_removes_stale_recovery_without_reinstall(self):
        runner, installer = self.prepare_active_upgrade()
        with mock.patch.object(MODULE, '_clear_recovery', side_effect=OSError('clear failed')):
            with self.assertRaisesRegex(OSError, 'clear failed'):
                MODULE.install(self.root, self.inventory_path, self.rpm,
                               runner=runner, installer=installer)
        self.assertTrue(self.active)
        self.calls.clear()
        result = MODULE.install(self.root, self.inventory_path, self.rpm,
                                runner=runner, installer=installer)
        self.assertEqual('IDEMPOTENT_ACTIVE', result['status'])
        self.assertFalse((self.root / MODULE.RECOVERY_PATH.lstrip('/')).exists())
        self.assertFalse(any(c[0] == 'package-install' or 'kill' in c or 'start' in c for c in self.calls))

    def test_retry_after_host_reboot_preserves_intent_without_confusing_reused_pid(self):
        runner, installer = self.prepare_active_upgrade()
        with self.assertRaises(RuntimeError):
            MODULE.install(self.root, self.inventory_path, self.rpm, runner=runner,
                           installer=mock.Mock(side_effect=RuntimeError('transaction failed')))
        # A host boot change makes the persisted old PID identity obsolete;
        # restart intent and RPM/config guards remain valid across reboot.
        (self.root / 'proc/sys/kernel/random/boot_id').write_text(
            '00000000-0000-4000-8000-000000000002\n')
        (self.root / 'proc/123/stat').write_text(
            '123 (unrelated) ' + ' '.join(['S'] + ['0'] * 18 + ['456789']))
        result = MODULE.install(self.root, self.inventory_path, self.rpm,
                                runner=runner, installer=installer)
        self.assertEqual('UPGRADED_ACTIVE', result['status'])
        self.assertTrue(self.active)
        self.assertEqual(1, sum(c[:2] == ['systemctl', 'kill'] for c in self.calls))

    def test_retry_same_boot_distinct_starttime_does_not_signal_reused_pid(self):
        runner, installer = self.prepare_active_upgrade()
        with self.assertRaises(RuntimeError):
            MODULE.install(self.root, self.inventory_path, self.rpm, runner=runner,
                           installer=mock.Mock(side_effect=RuntimeError('transaction failed')))
        (self.root / 'proc/123/stat').write_text(
            '123 (unrelated) ' + ' '.join(['S'] + ['0'] * 18 + ['987654']))
        result = MODULE.install(self.root, self.inventory_path, self.rpm,
                                runner=runner, installer=installer)
        self.assertEqual('UPGRADED_ACTIVE', result['status'])
        self.assertEqual(1, sum(c[:2] == ['systemctl', 'kill'] for c in self.calls))

    def test_config_restore_is_attempted_when_package_transaction_fails(self):
        runner, installer = self.prepare_active_upgrade()
        config = self.root / 'etc/zram-memory/config.json'
        config.parent.mkdir(parents=True)
        config.write_text('{"enabled":false}')

        def fail_install(root, rpm):
            config.write_text('{"unexpected":"new default"}')
            raise RuntimeError('transaction failed')

        sync = MODULE._sync_path

        def fail_restored_config(path):
            if Path(path) == config:
                raise OSError('config restore failed')
            sync(path)

        with self.assertRaisesRegex(MODULE.InstallError, 'UPGRADE_ROLLBACK_INCOMPLETE'):
            with mock.patch.object(MODULE, '_sync_path', side_effect=fail_restored_config):
                MODULE.install(self.root, self.inventory_path, self.rpm,
                               runner=runner, installer=fail_install)
        self.assertEqual('{"enabled":false}', config.read_text())

    def test_loaded_stop_contract_must_match_safe_disk_unit_before_any_signal(self):
        runner, installer = self.prepare_active_upgrade()
        for before, after in (('KillMode=process', 'KillMode=control-group'),
                              ('Restart=no', 'Restart=always'),
                              ('ExecStop=\n', 'ExecStop=/custom/stop\n'),
                              ('ExecStopPost=\n', 'ExecStopPost=/custom/cleanup\n')):
            with self.subTest(property=after):
                def changed(argv, **kwargs):
                    result = runner(argv, **kwargs)
                    return result.replace(before, after) if argv[:2] == ['systemctl', 'show'] else result
                with self.assertRaisesRegex(MODULE.InstallError, 'EFFECTIVE_STOP_CONTRACT_UNKNOWN'):
                    MODULE.install(self.root, self.inventory_path, self.rpm,
                                   runner=changed, installer=installer)
                self.assertTrue(self.active)
                self.assertFalse((self.root / MODULE.RECOVERY_PATH.lstrip('/')).exists())
        self.assertFalse(any(c[0] == 'package-install' or 'kill' in c for c in self.calls))

    def test_systemd255_omitted_empty_stop_properties_require_typed_dbus_proof(self):
        runner, _installer = self.prepare_active_upgrade()
        cases = (
            ('both omitted', {'ExecStop', 'ExecStopPost'}),
            ('only ExecStop omitted', {'ExecStop'}),
            ('only ExecStopPost omitted', {'ExecStopPost'}),
        )
        for label, omitted in cases:
            with self.subTest(label=label):
                calls = []

                def query(argv, **kwargs):
                    argv = list(map(str, argv))
                    calls.append(argv)
                    result = runner(argv, **kwargs)
                    if argv[:2] == ['systemctl', 'show']:
                        return ''.join(line for line in result.splitlines(True)
                                       if line.split('=', 1)[0] not in omitted)
                    if argv[:2] == ['busctl', 'get-property']:
                        self.assertEqual(argv, [
                            'busctl', 'get-property', 'org.freedesktop.systemd1',
                            '/org/freedesktop/systemd1/unit/zram_2dmemory_2eservice',
                            'org.freedesktop.systemd1.Service', argv[-1]])
                        return 'a(sasbttttuii) 0\n'
                    return result

                identity = MODULE._old_controller_identity(self.root, query)
                self.assertEqual(123, identity['pid'])
                queried = [argv[-1] for argv in calls if argv[:2] == ['busctl', 'get-property']]
                self.assertEqual(omitted, set(queried))
                self.assertFalse((self.root / MODULE.RECOVERY_PATH.lstrip('/')).exists())
                self.assertFalse(any(c[0] == 'package-install' or 'kill' in c for c in self.calls))

    def test_nonempty_typed_stop_action_refuses_before_signal_install_or_archive(self):
        runner, installer = self.prepare_active_upgrade()

        def typed_nonempty(argv, **kwargs):
            argv = list(map(str, argv))
            if argv[:2] == ['systemctl', 'show']:
                output = runner(argv, **kwargs)
                return ''.join(line for line in output.splitlines(True)
                               if not line.startswith(('ExecStop=', 'ExecStopPost=')))
            if argv[:2] == ['busctl', 'get-property']:
                return 'a(sasbttttuii) 1 "systemd-exec-command"'
            return runner(argv, **kwargs)

        with self.assertRaisesRegex(MODULE.InstallError, 'STOP_CONTRACT_UNSAFE|STOP_CONTRACT_UNKNOWN'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=typed_nonempty, installer=installer)
        self.assertTrue(self.active)
        self.assertFalse(any(c[0] == 'package-install' or 'kill' in c for c in self.calls))
        self.assertFalse((self.root / MODULE.RECOVERY_PATH.lstrip('/')).exists())
        self.assertFalse((self.root / 'var/lib/zstack-zram/upgrade-config-archive').exists())

    def test_invalid_or_failed_typed_stop_queries_remain_unknown(self):
        runner, installer = self.prepare_active_upgrade()
        cases = {
            'wrong signature': 'as 0\n',
            'malformed count': 'a(sasbttttuii) empty\n',
            'missing output': '',
        }
        for label, response in cases.items():
            with self.subTest(label=label):
                self.calls.clear()

                def malformed(argv, **kwargs):
                    argv = list(map(str, argv))
                    if argv[:2] == ['systemctl', 'show']:
                        output = runner(argv, **kwargs)
                        return ''.join(line for line in output.splitlines(True)
                                       if not line.startswith(('ExecStop=', 'ExecStopPost=')))
                    if argv[:2] == ['busctl', 'get-property']:
                        return response
                    return runner(argv, **kwargs)

                with self.assertRaisesRegex(MODULE.InstallError, 'EFFECTIVE_STOP_CONTRACT_UNKNOWN'):
                    MODULE.install(self.root, self.inventory_path, self.rpm,
                                   runner=malformed, installer=installer)
                self.assertTrue(self.active)
                self.assertFalse(any(c[0] == 'package-install' or 'kill' in c for c in self.calls))
                self.assertFalse((self.root / MODULE.RECOVERY_PATH.lstrip('/')).exists())

        for label, error in (('command failure', subprocess.CalledProcessError(1, ['busctl'])),
                             ('timeout', subprocess.TimeoutExpired(['busctl'], 1))):
            with self.subTest(label=label):
                self.calls.clear()

                def failed(argv, **kwargs):
                    argv = list(map(str, argv))
                    if argv[:2] == ['systemctl', 'show']:
                        output = runner(argv, **kwargs)
                        return ''.join(line for line in output.splitlines(True)
                                       if not line.startswith(('ExecStop=', 'ExecStopPost=')))
                    if argv[:2] == ['busctl', 'get-property']:
                        raise error
                    return runner(argv, **kwargs)

                with self.assertRaisesRegex(MODULE.InstallError, 'EFFECTIVE_STOP_CONTRACT_UNKNOWN'):
                    MODULE.install(self.root, self.inventory_path, self.rpm,
                                   runner=failed, installer=installer)
                self.assertTrue(self.active)
                self.assertFalse(any(c[0] == 'package-install' or 'kill' in c for c in self.calls))
                self.assertFalse((self.root / MODULE.RECOVERY_PATH.lstrip('/')).exists())

    def test_explicit_systemctl_nonempty_stop_still_rejects_even_if_dbus_empty(self):
        runner, installer = self.prepare_active_upgrade()
        dbus_calls = []

        def conflicting(argv, **kwargs):
            argv = list(map(str, argv))
            if argv[:2] == ['systemctl', 'show']:
                return runner(argv, **kwargs) + 'ExecStop=/custom/stop\n'
            if argv[:2] == ['busctl', 'get-property']:
                dbus_calls.append(argv[-1])
                return 'a(sasbttttuii) 0\n'
            return runner(argv, **kwargs)

        with self.assertRaisesRegex(MODULE.InstallError, 'EFFECTIVE_STOP_CONTRACT_UNKNOWN'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=conflicting, installer=installer)
        self.assertEqual([], dbus_calls)
        self.assertTrue(self.active)
        self.assertFalse(any(c[0] == 'package-install' or 'kill' in c for c in self.calls))

    def test_concurrent_installer_cannot_signal_or_install(self):
        runner, installer = self.prepare_active_upgrade()
        lock = self.root / 'run/lock/zstack-zram-rpm-upgrade.lock'
        lock.parent.mkdir(parents=True)
        with lock.open('w') as stream:
            MODULE.fcntl.flock(stream.fileno(), MODULE.fcntl.LOCK_EX)
            with self.assertRaisesRegex(MODULE.InstallError, 'RPM_UPGRADE_OR_HOST_CONTROL_ALREADY_RUNNING'):
                MODULE.install(self.root, self.inventory_path, self.rpm,
                               runner=runner, installer=installer)
        self.assertTrue(self.active)
        self.assertFalse(any(call[0] == 'package-install' or 'kill' in call for call in self.calls))

    def test_agent_control_inflight_fences_upgrade_without_policy_write(self):
        runner, installer = self.prepare_active_upgrade()
        lock = self.root / 'var/lib/zstack/memory-optimization/operations/.host-control.flock'
        lock.parent.mkdir(parents=True)
        with lock.open('w') as stream:
            MODULE.fcntl.flock(stream.fileno(), MODULE.fcntl.LOCK_EX)
            with self.assertRaisesRegex(MODULE.InstallError, 'HOST_CONTROL_ALREADY_RUNNING'):
                MODULE.install(self.root, self.inventory_path, self.rpm,
                               runner=runner, installer=installer)
        self.assertTrue(self.active)
        self.assertFalse(any(call[0] == 'package-install' or 'kill' in call for call in self.calls))

    def test_service_starting_or_stopping_is_not_treated_as_inactive(self):
        for state in ('activating', 'deactivating', 'reloading', ''):
            def transient(argv, **kwargs):
                if argv[:2] == ['systemctl', 'is-active']:
                    raise subprocess.CalledProcessError(3, argv, output=state)
                return self.runner(argv, **kwargs)
            with self.subTest(state=state), self.assertRaisesRegex(
                    MODULE.InstallError, 'SERVICE_TRANSITION_IN_PROGRESS'):
                MODULE.install(self.root, self.inventory_path, self.rpm,
                               runner=transient, installer=self.install_package)
        self.assertFalse(any(call[0] == 'package-install' for call in self.calls))

    def test_process_exit_between_stat_and_starttime_read_is_accepted(self):
        runner, _ = self.prepare_active_upgrade()
        original_starttime = MODULE._proc_starttime
        calls = []

        def exit_race(root, pid):
            calls.append(pid)
            if len(calls) == 3:
                (self.root / 'proc/123/stat').unlink()
                self.active = False
                self.pid = '0'
                raise MODULE.InstallError('ACTIVE_PROCESS_IDENTITY_UNVERIFIABLE')
            return original_starttime(root, pid)

        def delayed(argv, **kwargs):
            if argv[:2] == ['systemctl', 'kill']:
                return ''
            return runner(argv, **kwargs)

        with mock.patch.object(MODULE, '_proc_starttime', side_effect=exit_race):
            result = MODULE._graceful_old_controller_exit(
                self.root, delayed, timeout=0)
        self.assertEqual(123, result['pid'])

    def test_active_mismatch_requires_maintenance_without_package_mutation(self):
        self.active = True
        with self.assertRaisesRegex(MODULE.InstallError, 'UNIT_UNKNOWN|OWNERSHIP_UNKNOWN'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=self.runner, installer=self.install_package)
        self.assertFalse(any(call[0] == 'package-install' for call in self.calls))

    def test_active_same_version_and_process_is_an_idempotent_noop(self):
        self.active = True
        self.installed = True
        self.installed_version = '1.2.3-4'
        unit = self.root / MODULE.UNIT_PATH.lstrip('/')
        unit.parent.mkdir(parents=True)
        unit.write_text(self.unit_text)
        self.rpm_owned[MODULE.UNIT_PATH] = MODULE._hash(unit)
        binary = self.root / MODULE.EXECUTABLE_PATH.lstrip('/')
        binary.parent.mkdir(parents=True)
        binary.write_bytes(self.binary_bytes)
        binary.chmod(0o755)
        self.rpm_owned[MODULE.EXECUTABLE_PATH] = MODULE._hash(binary)
        ctl = self.root / 'usr/local/bin/zram-efficiencyctl'
        ctl.parent.mkdir(parents=True, exist_ok=True)
        ctl.write_bytes(self.ctl_bytes)
        ctl.chmod(0o755)
        self.rpm_owned['/usr/local/bin/zram-efficiencyctl'] = MODULE._hash(ctl)
        proc_dir = self.root / 'proc/123'
        proc_dir.mkdir(parents=True, exist_ok=True)
        proc_exe = proc_dir / 'exe'
        proc_exe.symlink_to(binary)
        proc_stat = proc_dir / 'stat'
        proc_stat.write_text('123 (zram efficiency) ' + ' '.join(
            ['S'] + ['0'] * 18 + ['456789']) + '\n')
        result = MODULE.install(self.root, self.inventory_path, self.rpm,
                                runner=self.runner, installer=self.install_package)
        self.assertEqual('IDEMPOTENT_ACTIVE', result['status'])
        self.assertFalse(any(call[0] == 'package-install' for call in self.calls))

    def test_active_same_version_but_different_installed_binary_is_rejected(self):
        self.active = True
        self.installed = True
        self.installed_version = '1.2.3-4'
        self.fragment = MODULE.UNIT_PATH
        unit = self.root / MODULE.UNIT_PATH.lstrip('/')
        unit.parent.mkdir(parents=True)
        unit.write_text(self.unit_text)
        self.rpm_owned[MODULE.UNIT_PATH] = MODULE._hash(unit)
        binary = self.root / MODULE.EXECUTABLE_PATH.lstrip('/')
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b'#!/bin/sh\\n# different release, same version string\\nexit 0\\n')
        binary.chmod(0o755)
        self.rpm_owned[MODULE.EXECUTABLE_PATH] = self.runtime_binaries[MODULE.EXECUTABLE_PATH]['sha256']
        with self.assertRaisesRegex(MODULE.InstallError, 'ACTIVE:BINARY_HASH_MISMATCH'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=self.runner, installer=self.install_package)
        self.assertFalse(any(call[0] == 'package-install' for call in self.calls))

    def test_active_old_running_process_same_version_is_rejected_by_executable_hash(self):
        self.active = True
        self.installed = True
        self.installed_version = '1.2.3-4'
        self.fragment = MODULE.UNIT_PATH
        unit = self.root / MODULE.UNIT_PATH.lstrip('/')
        unit.parent.mkdir(parents=True)
        unit.write_text(self.unit_text)
        self.rpm_owned[MODULE.UNIT_PATH] = MODULE._hash(unit)
        binary = self.root / MODULE.EXECUTABLE_PATH.lstrip('/')
        binary.parent.mkdir(parents=True)
        binary.write_bytes(self.binary_bytes)
        binary.chmod(0o755)
        self.rpm_owned[MODULE.EXECUTABLE_PATH] = MODULE._hash(binary)
        old_binary = self.root / 'tmp/old-zram-efficiency'
        old_binary.parent.mkdir(parents=True)
        old_binary.write_bytes(b'#!/bin/sh\\n# old build with same version output\\nexit 0\\n')
        old_binary.chmod(0o755)
        ctl = self.root / 'usr/local/bin/zram-efficiencyctl'
        ctl.parent.mkdir(parents=True, exist_ok=True)
        ctl.write_bytes(self.ctl_bytes)
        proc_dir = self.root / 'proc/123'
        proc_dir.mkdir(parents=True)
        (proc_dir / 'exe').symlink_to(old_binary)
        (proc_dir / 'stat').write_text('123 (zram efficiency) ' + ' '.join(
            ['S'] + ['0'] * 18 + ['456789']) + '\n')
        with self.assertRaisesRegex(MODULE.InstallError, 'ACTIVE_PROCESS_MISMATCH'):
            MODULE.install(self.root, self.inventory_path, self.rpm,
                           runner=self.runner, installer=self.install_package)
        self.assertFalse(any(call[0] == 'package-install' for call in self.calls))


if __name__ == '__main__':
    unittest.main()
