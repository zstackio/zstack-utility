"""Isolated single-writer receipts: these tests never access host sysfs."""
import os
import shutil
import subprocess
import tempfile
import time
from unittest import TestCase
try:
    from mock import patch
except ImportError:
    from unittest.mock import patch

from kvmagent.plugins.memory_optimization import MemoryOptimizationPlugin


class TestKsmAppliedReceipt(TestCase):
    def test_disabled_policy_applies_all_values_without_starting_scans(self):
        self.write('marker', 'managed')
        self.policy(2, 321, sleep=30, zero=1, enabled=0)
        self.call('apply')
        status = self.call('status')
        for value in ('run=0', 'pages_to_scan=321', 'sleep_millisecs=30',
                      'use_zero_pages=1', 'configRevision=2'):
            self.assertIn(value + '\n', status)

    def test_disabled_apply_write_failure_does_not_advance_receipt(self):
        self.write('marker', 'managed')
        self.policy(1, 100)
        self.call('stop')
        self.policy(2, 321, sleep=30, zero=1, enabled=0)
        pages = os.path.join(self.root, 'pages_to_scan')
        os.unlink(pages)
        os.mkdir(pages)
        with self.assertRaises(subprocess.CalledProcessError):
            self.call('apply')
        self.assertIn('configRevision=1\n', self.call('status'))

    def test_disabled_apply_readback_mismatch_does_not_advance_receipt(self):
        self.write('marker', 'managed')
        self.policy(1, 100)
        self.call('stop')
        self.policy(2, 321, sleep=30, zero=1, enabled=0)
        self.write('bin/cat', '#!/bin/sh\ncase "$1" in */pages_to_scan) echo 999;; '
                   '*) exec /bin/cat "$@";; esac', executable=True)
        result = subprocess.run([self.script, 'apply'], env=self.env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertNotEqual(0, result.returncode)
        self.assertIn(b'KSM_PAGES_NOT_APPLIED', result.stdout)
        with open(self.env['KSMTUNED_LOCK'] + '.applied') as stream:
            self.assertEqual('1', stream.read().strip())

    def test_agent_rejects_stale_tuning_even_with_current_receipt(self):
        plugin = MemoryOptimizationPlugin()
        plugin.ksm_apply_timeout = 0
        self.configure_agent_plugin(plugin)
        self.install_native_systemctl_fixture()
        real_check_output = subprocess.check_output
        for field, expected in (('pages_to_scan', 'KSM_PAGES_NOT_APPLIED'),
                                ('sleep_millisecs', 'KSM_SLEEP_NOT_APPLIED')):
            values = {'run': '1', 'configRevision': '2', 'use_zero_pages': '0',
                      'pages_to_scan': '321', 'sleep_millisecs': '30'}
            values[field] = '10'
            output = ''.join('%s=%s\n' % item for item in values.items()).encode()
            def execute(command, **kwargs):
                if command[0] == self.script and command[1] == 'status':
                    return output
                if (command[0] == 'systemctl' and len(command) > 2 and
                        command[1] in ('enable', 'start') and
                        command[-1] == plugin.MANAGED_KSM_UNIT):
                    return b''  # only managed-unit process execution is represented by status below
                return real_check_output(command, **kwargs)
            with patch.dict(os.environ, self.env), \
                 patch.object(plugin, '_publish_ksm_config'), \
                 patch.object(subprocess, 'check_output', side_effect=execute):
                with self.assertRaisesRegex(RuntimeError, expected):
                    plugin._apply_ksm_policy({'desiredRevision': 2,
                        'policy': {'ksm': {'enabled': True, 'pagesToScan': 321, 'sleepMillis': 30}}})
            with patch.object(subprocess, 'check_output', return_value=output):
                self.assertFalse(plugin._ksm_readback_matches(
                    {'pagesToScan': 321, 'sleepMillis': 30}, 2))

    def test_disable_does_not_reconfigure_numa_or_require_takeover_snapshot(self):
        self.write('marker', 'managed')
        self.write('merge_across_nodes', '1')
        self.env['KSMTUNED_NUMA_TARGET'] = os.path.join(self.root, 'absent', 'numa-owner')
        self.policy(2, 321, sleep=30, zero=1)
        self.call('stop')
        with open(os.path.join(self.root, 'merge_across_nodes')) as stream:
            self.assertEqual('1', stream.read().strip())
        self.assertIn('run=0\n', self.call('status'))
        self.assertFalse(os.path.exists(self.env['KSMTUNED_NUMA_TARGET']))

    def test_agent_disabled_updates_apply_when_systemd_unit_already_stopped(self):
        plugin = MemoryOptimizationPlugin()
        self.configure_agent_plugin(plugin)
        plugin.ksm_apply_timeout = 4
        self.install_native_systemctl_fixture()
        with patch.dict(os.environ, self.env):
            for revision, pages in ((2, 321), (3, 322)):
                actual = plugin._apply_ksm_policy({'desiredRevision': revision,
                    'policy': {'ksm': {'enabled': False, 'pagesToScan': pages,
                                      'sleepMillis': 30, 'zeroPagesEnabled': True}}})
                self.assertEqual('0', actual['run'])
                self.assertEqual(str(pages), actual['pages_to_scan'])
                self.assertEqual(str(revision), actual['configRevision'])
                with open(self.env['KSMTUNED_SNAPSHOT']) as stream:
                    snapshot = stream.read()
                self.assertIn('native_ksm_present=1\n', snapshot)
                self.assertIn('native_ksmtuned_present=1\n', snapshot)
                self.assertTrue(os.path.exists(self.env['KSMTUNED_MARKER']))

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='ksmtuned-ack-')
        self.addCleanup(shutil.rmtree, self.root)
        self.script = os.path.abspath(os.path.join(os.path.dirname(__file__),
            '../../ansible/memory-optimization/ksmtuned/ksmtuned-zstack'))
        self.env = dict(os.environ)
        for key, name in [('CONF', 'conf'), ('LEASE', 'lease'), ('LOCK', 'lock'),
                          ('SNAPSHOT', 'snapshot'), ('MARKER', 'marker')]:
            self.env['KSMTUNED_' + key] = os.path.join(self.root, name)
        self.env['KSMTUNED_KSM_ROOT'] = self.root
        self.env['KSMTUNED_RUNTIME_DIR'] = os.path.join(self.root, 'runtime')
        self.env['KSMTUNED_MEMINFO'] = os.path.join(self.root, 'meminfo')
        with open(self.env['KSMTUNED_MEMINFO'], 'w') as stream:
            stream.write('MemTotal:       67108864 kB\nMemFree:        67108863 kB\n')
        self.env['KSMTUNED_ENGINE'] = os.path.join(self.root, 'engine')
        engine_source = os.path.abspath(os.path.join(os.path.dirname(__file__),
            '../../ansible/memory-optimization/ksmtuned/upstream-src-ksmtuned.sh.in'))
        shutil.copyfile(engine_source, self.env['KSMTUNED_ENGINE'])
        os.chmod(self.env['KSMTUNED_ENGINE'], 0o755)
        self.env['KSMTUNED_CONTROL_INTERVAL'] = '0.05'
        self.write('run', '0')
        self.write('pages_to_scan', '100')
        self.write('sleep_millisecs', '20')
        self.write('use_zero_pages', '0')
        self.write('merge_across_nodes', '0')
        os.mkdir(os.path.join(self.root, 'bin'))
        self.env['PATH'] = os.path.join(self.root, 'bin') + ':' + self.env['PATH']
        self.write('bin/pgrep', '#!/bin/sh\nexit 1\n', executable=True)
        self.write('bin/systemctl', '#!/bin/sh\nexit 1\n', executable=True)
        self.policy(1, 200)

    def write(self, name, content, executable=False):
        path = os.path.join(self.root, name)
        with open(path, 'w') as stream:
            stream.write(content + '\n')
        if executable:
            os.chmod(path, 0o755)

    def policy(self, revision, pages, sleep=10, zero=0, enabled=1):
        # Production publication holds this same lock; tests update while
        # holding it too, so a mixed configuration/lease is not observable.
        import fcntl
        with open(os.path.join(self.root, 'lock'), 'a') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            self.write('conf', 'CONFIG_REVISION=%d\nKSM_ENABLED=%d\nKSM_PAGES_TO_SCAN=%d\n'
                       'KSM_SLEEP_MILLISECS=%d\nKSM_ZERO_PAGES=%d\n'
                       % (revision, enabled, pages, sleep, zero))
            self.write('lease', 'owner=test\nexpires=%d\nrevision=%d' %
                       (int(time.time()) + 300, revision))

    def call(self, action):
        return subprocess.check_output([self.script, action], env=self.env).decode('utf-8')

    def test_requested_revision_is_not_an_application_receipt(self):
        self.assertIn('configRevision=0\n', self.call('status'))
        self.call('start')
        self.assertIn('configRevision=1\n', self.call('status'))
        self.policy(2, 75)
        status = self.call('status')
        self.assertIn('configRevision=1\n', status)
        self.assertIn('requestedRevision=2\n', status)
        self.call('apply')
        self.assertIn('configRevision=2\n', self.call('status'))

    def test_readback_exposes_four_ksm_values_without_cpu_budget(self):
        self.policy(3, 2000, sleep=20, zero=1)
        self.call('apply')
        status = self.call('status')
        self.assertIn('pages_to_scan=2000\n', status)
        self.assertIn('sleep_millisecs=20\n', status)
        self.assertIn('use_zero_pages=1\n', status)
        self.assertNotIn('cpuBudgetPercent=', status)

    def test_running_writer_acknowledges_and_enforces_new_lower_ceiling(self):
        process = subprocess.Popen([self.script, 'run'], env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.time() + 5
            while 'configRevision=1\n' not in self.call('status'):
                self.assertLess(time.time(), deadline)
                time.sleep(.02)
            self.policy(2, 3)
            while 'configRevision=2\n' not in self.call('status'):
                self.assertLess(time.time(), deadline)
                time.sleep(.02)
            with open(os.path.join(self.root, 'pages_to_scan')) as stream:
                self.assertLessEqual(int(stream.read()), 3)
            self.assertIsNone(process.poll())
        finally:
            process.terminate()
            process.communicate(timeout=5)

    def test_run_keeps_persisted_disabled_policy_after_restart(self):
        self.policy(2, 321, sleep=30, zero=1)
        with open(self.env['KSMTUNED_CONF'], 'a') as stream:
            stream.write('KSM_ENABLED=0\n')
        process = subprocess.Popen([self.script, 'run'], env=self.env)
        try:
            time.sleep(0.35)
            self.assertEqual('0', open(os.path.join(self.root, 'run')).read().strip())
            self.assertFalse(os.path.exists(os.path.join(self.root, 'runtime', 'ksmtuned-engine.conf')))
        finally:
            process.terminate()
            process.wait()

    def test_failed_legacy_restore_retains_recovery_evidence(self):
        self.write('snapshot', 'active=active\nrun=1\npages_to_scan=99')
        self.write('marker', 'managed')
        with self.assertRaises(subprocess.CalledProcessError):
            self.call('legacy-resume')
        self.assertTrue(os.path.exists(os.path.join(self.root, 'marker')))
        self.assertTrue(os.path.exists(os.path.join(self.root, 'snapshot')))

    def test_failed_stop_of_active_legacy_writer_prevents_takeover(self):
        self.write('bin/systemctl', '#!/bin/sh\ncase "$1" in\n'
                   'is-active) echo active;; is-enabled) echo enabled;; *) exit 1;; esac',
                   executable=True)
        with self.assertRaises(subprocess.CalledProcessError):
            self.call('takeover')
        with open(os.path.join(self.root, 'run')) as stream:
            self.assertEqual('0', stream.read().strip())

    def test_agent_waits_for_writer_receipt_not_systemd_start_return(self):
        plugin = MemoryOptimizationPlugin()
        self.configure_agent_plugin(plugin)
        self.install_native_systemctl_fixture()
        command = {'desiredRevision': 2, 'operationUuid': 'op-2',
                   'licensePermit': {'validForSeconds': 30,
                                     'expiresAt': int(time.time() * 1000) + 30000},
                   'policy': {'ksm': {'enabled': True,
                                      'zeroPagesEnabled': True,
                                      'pagesToScan': 2000,
                                      'sleepMillis': 20}}}
        real_check_output = subprocess.check_output
        status_outputs = iter((b'configRevision=1\nrun=1\nuse_zero_pages=0\n',
                               b'configRevision=2\nrun=1\nuse_zero_pages=1\n'
                               b'pages_to_scan=2000\nsleep_millisecs=20\n'))
        status_calls = []
        def execute(argv, **kwargs):
            if argv[0] == self.script and argv[1] == 'takeover':
                return real_check_output(argv, **kwargs)
            if argv[0] == self.script and argv[1] == 'status':
                status_calls.append(argv)
                return next(status_outputs)
            if (argv[0] == 'systemctl' and len(argv) > 2 and argv[1] in ('enable', 'start')
                    and argv[-1] == plugin.MANAGED_KSM_UNIT):
                return b''  # real managed writer is represented by the sequenced receipt reads
            return real_check_output(argv, **kwargs)
        with patch.dict(os.environ, self.env), \
                patch.object(subprocess, 'check_output', side_effect=execute):
            self.assertEqual('2', plugin._apply_ksm_policy(command)['configRevision'])
            self.assertEqual(2, len(status_calls))

    def install_native_systemctl_fixture(self):
        """Model only distro unit metadata; takeover and receipt remain real shell code."""
        state = os.path.join(self.root, 'systemd-state')
        os.makedirs(state, exist_ok=True)
        self.env['KSMTUNED_FAKE_SYSTEMD_DIR'] = state
        self.env['KSMTUNED_SCRIPT'] = self.script
        for unit in ('ksm.service', 'ksmtuned.service'):
            with open(os.path.join(state, unit + '.load'), 'w') as stream:
                stream.write('LoadState=loaded\n')
            with open(os.path.join(state, unit + '.enabled'), 'w') as stream:
                stream.write('enabled\n')
            with open(os.path.join(state, unit + '.active'), 'w') as stream:
                stream.write('inactive\n')
        systemctl = os.path.join(self.root, 'bin', 'systemctl')
        with open(systemctl, 'w') as stream:
            stream.write('''#!/bin/sh
set -eu
state=${KSMTUNED_FAKE_SYSTEMD_DIR:?}
cmd=$1; shift
unit=
for arg do unit=$arg; done
case "$cmd" in
  show)
    case "$*" in *"LoadState"*) cat "$state/$unit.load";; *) exit 2;; esac ;;
  is-enabled) cat "$state/$unit.enabled" ;;
  is-active) cat "$state/$unit.active" ;;
  stop) printf 'inactive\\n' > "$state/$unit.active" ;;
  start)
    if [ "$unit" = zstack-ksmtuned.service ]; then
      pidfile="$state/managed.pid"
      if [ ! -s "$pidfile" ] || ! kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        "$KSMTUNED_SCRIPT" run >/dev/null 2>&1 &
        printf '%s\\n' "$!" > "$pidfile"
      fi
    fi
    printf 'active\\n' > "$state/$unit.active" ;;
  mask) printf 'masked\\n' > "$state/$unit.enabled" ;;
  unmask) printf 'disabled\\n' > "$state/$unit.enabled" ;;
  enable) exit 0 ;;
  disable) printf 'disabled\\n' > "$state/$unit.enabled" ;;
  daemon-reload) exit 0 ;;
  *) exit 0 ;;
esac
''')
        os.chmod(systemctl, 0o755)
        self.addCleanup(self.stop_fake_writer)

    def stop_fake_writer(self):
        pidfile = os.path.join(self.root, 'systemd-state', 'managed.pid')
        try:
            with open(pidfile) as stream:
                pid = int(stream.read().strip())
            os.kill(pid, 15)
        except (IOError, OSError, ValueError):
            pass

    def configure_agent_plugin(self, plugin):
        plugin.KSM_SCRIPT = self.script
        plugin.KSM_CONF = self.env['KSMTUNED_CONF']
        plugin.KSM_LEASE = self.env['KSMTUNED_LEASE']
        plugin.KSM_LOCK = self.env['KSMTUNED_LOCK']
        plugin.KSM_SNAPSHOT = self.env['KSMTUNED_SNAPSHOT']
        plugin.MANAGED_KSM_MARKER = self.env['KSMTUNED_MARKER']

    def test_reconcile_rejects_old_applied_ksm_revision(self):
        plugin = MemoryOptimizationPlugin()
        with patch.object(subprocess, 'check_output', return_value=b'configRevision=1\nrun=1\n'):
            self.assertFalse(plugin._ksm_readback_matches({'enabled': True}, 2))
            self.assertTrue(plugin._ksm_readback_matches({'enabled': True}, 1))
