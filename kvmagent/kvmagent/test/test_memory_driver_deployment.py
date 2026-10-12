"""Execute the real playbook function with a recording transport only."""
import ast
import json
import os
from pathlib import Path
import re
import shlex
from types import SimpleNamespace
import unittest


SOURCE = Path(__file__).resolve().parents[2] / 'ansible/kvm.py'


class DriverDeploymentTest(unittest.TestCase):
    def invoke(self, report, release='alinux4', install_ok=True):
        tree = ast.parse(SOURCE.read_text())
        function = next(item for item in tree.body if isinstance(item, ast.FunctionDef)
                        and item.name == 'check_alinux_zram_driver')
        calls, warnings = [], []
        def run(command, host, **options):
            calls.append(command)
            if options.get('return_output'):
                return True, json.dumps(report)
            return install_ok
        env = {'releasever': release, '_memory_supported_host': lambda: True,
               'os': os, 'shlex': shlex, 'json': json, 're': re,
               'virtenv_path': '/var/lib/zstack/virtualenv/kvm',
               'host_post_info': SimpleNamespace(), 'run_remote_command': run,
               'handle_ansible_info': lambda message, host, level: warnings.append((message, level))}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), 'exec'), env)
        env['check_alinux_zram_driver']()
        return calls, warnings

    def report(self, **extra):
        value = {'installationPackage': 'kmod-zstack-zram-5.5.48.1-1.alnx4.x86_64',
                 'supported': False, 'reasonCode': 'ZRAM_DRIVER_UPDATE_REQUIRES_MAINTENANCE'}
        value.update(extra)
        return value

    def test_actual_new_and_reconnect_deployment_checks_after_packages_before_agent_start(self):
        tree = ast.parse(SOURCE.read_text())
        calls = [item.value.func.id for item in tree.body if isinstance(item, ast.Expr)
                 and isinstance(item.value, ast.Call) and isinstance(item.value.func, ast.Name)]
        self.assertEqual(1, calls.count('check_alinux_zram_driver'))
        self.assertLess(calls.index('install_agent_pkg'), calls.index('check_alinux_zram_driver'))
        # Service RPM adoption may restart a previously active controller.
        # Its ExecStartPre must see the already installed exact-ABI driver.
        self.assertLess(calls.index('check_alinux_zram_driver'), calls.index('install_memory_optimization_materials'))
        self.assertLess(calls.index('check_alinux_zram_driver'), calls.index('start_kvmagent'))

    def test_exact_package_and_independent_loaded_check_without_module_mutation(self):
        calls, warnings = self.invoke(self.report())
        self.assertEqual(3, len(calls))
        self.assertEqual(calls[0], calls[2])
        self.assertIn('--exclude="kernel*"', calls[1])
        self.assertIn('install kmod-zstack-zram-5.5.48.1-1.alnx4.x86_64', calls[1])
        for forbidden in ('rmmod', 'modprobe', 'swapoff', '/reset', 'systemctl', '--force', '--nodeps'):
            self.assertNotIn(forbidden, '\n'.join(calls))
        self.assertIn('MAINTENANCE', warnings[-1][0])

    def test_missing_repo_is_warning_and_readback_still_runs(self):
        calls, warnings = self.invoke(self.report(), install_ok=False)
        self.assertEqual(3, len(calls))
        self.assertTrue(any('package unavailable' in message for message, level in warnings))

    def test_matching_runtime_does_not_warn(self):
        calls, warnings = self.invoke(self.report(supported=True, reasonCode='SUPPORTED'))
        self.assertEqual([], warnings)
        self.assertEqual(3, len(calls))

    def test_other_platform_and_unknown_kernel_do_not_install(self):
        self.assertEqual(([], []), self.invoke(self.report(), release='h84r'))
        calls, warnings = self.invoke({'reasonCode': 'ZRAM_DRIVER_KERNEL_UNSUPPORTED'})
        self.assertEqual(1, len(calls))
        self.assertTrue(warnings)

    def test_invalid_package_or_observation_cannot_enter_package_manager(self):
        for report in (None, [], self.report(installationPackage='kmod-zstack-zram; touch /tmp/bad')):
            calls, warnings = self.invoke(report)
            self.assertEqual(1, len(calls))
            self.assertTrue(warnings)


if __name__ == '__main__':
    unittest.main()
