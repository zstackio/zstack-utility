"""Standalone daemon lifecycle regression tests; no host services are stopped."""
import errno
import imp
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest


def load_daemon(path):
    saved = {}
    for name in ['zstacklib', 'zstacklib.utils', 'zstacklib.utils.linux', 'zstacklib.utils.log']:
        saved[name] = sys.modules.get(name)
        sys.modules[name] = types.ModuleType(name)
    linux = sys.modules['zstacklib.utils.linux']
    linux.rm_file_force = lambda path: os.remove(path)
    linux.process_exists = lambda pid: os.path.exists('/proc/%s' % pid)
    log = sys.modules['zstacklib.utils.log']
    logger = types.ModuleType('test_logger')
    logger.info = logger.error = lambda *args: None
    log.get_logger = lambda name: logger
    sys.modules['zstacklib.utils'].linux = linux
    sys.modules['zstacklib.utils'].log = log
    try:
        module = imp.load_source('daemon_under_test', path)
    finally:
        for name, value in saved.items():
            if value is None:
                del sys.modules[name]
            else:
                sys.modules[name] = value
    return module


SOURCE = os.environ.get('DAEMON_SOURCE', os.path.abspath(os.path.join(os.path.dirname(__file__), '../utils/daemon.py')))


class DaemonStopRaceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix='zcf6727-')
        self.module = load_daemon(SOURCE)
        self.daemon = self.module.Daemon(os.path.join(self.directory, 'agent.pid'), 'test-agent')

    def tearDown(self):
        shutil.rmtree(self.directory)

    def test_old_cleanup_preserves_successor_pidfile(self):
        with open(self.daemon.pidfile, 'w') as stream:
            stream.write(str(os.getpid() + 1))
        self.daemon.delpid()
        self.assertTrue(os.path.exists(self.daemon.pidfile))
        with open(self.daemon.pidfile, 'w') as stream:
            stream.write(str(os.getpid()))
        self.daemon.delpid()
        self.assertFalse(os.path.exists(self.daemon.pidfile))

    def test_pid_reuse_is_not_signalled(self):
        killed = []
        starts = iter([20])
        self.daemon._process_start_time = lambda pid: next(starts)
        original = self.module.os.kill
        self.module.os.kill = lambda pid, sig: killed.append(pid)
        try:
            self.daemon.stop_agent_by_pid(1234, 0, 10)
        finally:
            self.module.os.kill = original
        self.assertEqual([], killed)

    def test_delayed_stop_does_not_kill_concurrent_start(self):
        old = subprocess.Popen(['sleep', '30'])
        worker = new = None
        try:
            # Separate clock ticks make process birth ordering explicit.
            time.sleep(0.05)
            worker = subprocess.Popen([sys.executable, __file__, 'worker', self.directory, SOURCE], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            deadline = time.time() + 5
            while not os.path.exists(os.path.join(self.directory, 'ready')):
                if time.time() > deadline:
                    self.fail('stop worker did not reach delayed lookup')
                time.sleep(0.01)
            time.sleep(0.05)
            new = subprocess.Popen(['sleep', '30'])
            with open(os.path.join(self.directory, 'candidates'), 'w') as stream:
                stream.write('%s\n%s' % (old.pid, new.pid))
            # Reap the old test process so legacy code also exits its kill loop.
            deadline = time.time() + 8
            while worker.poll() is None and time.time() < deadline:
                old.poll()
                new.poll()
                time.sleep(0.02)
            self.assertEqual(0, worker.poll(), 'stop worker hung')
            self.assertIsNotNone(old.poll(), 'old process was not stopped')
            self.assertIsNone(new.poll(), 'old stop killed the new process')
        finally:
            for process in [old, new, worker]:
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.communicate()


def worker_main(directory, source):
    module = load_daemon(source)
    def delayed_lookup(name):
        open(os.path.join(directory, 'ready'), 'w').close()
        deadline = time.time() + 5
        path = os.path.join(directory, 'candidates')
        while not os.path.exists(path):
            if time.time() > deadline:
                raise RuntimeError('missing test candidates')
            time.sleep(0.01)
        with open(path) as stream:
            return stream.read()
    module.linux.get_agent_pid_by_name = delayed_lookup
    module.Daemon(os.path.join(directory, 'missing.pid'), 'test-agent').stop()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'worker':
        worker_main(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
