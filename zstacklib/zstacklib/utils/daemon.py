#!/usr/bin/env python

import sys, os, time, atexit
import traceback
import locale
import errno
import fcntl
from contextlib import contextmanager
from signal import SIGTERM,SIGKILL
from zstacklib.utils import linux
from zstacklib.utils import log

logger = log.get_logger(__name__)

class Daemon(object):
    """
    A generic daemon class.

    Usage: subclass the Daemon class and override the run() method
    """
    atexit_hooks = []

    def __init__(self, pidfile, py_process_name, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile
        self.py_process_name = py_process_name

    @staticmethod
    def register_atexit_hook(hook):
        Daemon.atexit_hooks.append(hook)

    @staticmethod
    def _log_and_dump_message(msg, fileobj=sys.stdout):
        logger.info(msg)
        if fileobj: fileobj.write(msg)

    @staticmethod
    def _atexit():
        for hook in Daemon.atexit_hooks:
            try:
                hook()
            except Exception:
                content = traceback.format_exc()
                err = 'Exception when calling atexit hook[%s]\n%s' % (hook.__name__, content)
                logger.error(err)

    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced
        Programming in the UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        Daemon._log_and_dump_message("Daemonizing...\n")

        try:
            pid = os.fork()
            if pid > 0:
                # exit first parent
                sys.exit(0)
        except OSError as e:
            message = "fork #1 failed: %d (%s)\n" % (e.errno, e.strerror)
            Daemon._log_and_dump_message(message, sys.stderr)
            sys.exit(1)

        # decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                os._exit(0)
        except OSError as e:
            message = "fork #2 failed: %d (%s)\n" % (e.errno, e.strerror)
            Daemon._log_and_dump_message(message, sys.stderr)
            os._exit(1)

        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = open(self.stdin, 'r')
        so = open(self.stdout, 'a+')
        se = open(self.stderr, 'a+', buffering=1)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        # write pidfile
        Daemon.register_atexit_hook(self.delpid)
        atexit.register(Daemon._atexit)

        # systemd needs this for non-native service
        pid = os.getpid()
        logger.info("writing pidfile (pid=%d)" % pid)
        try:
            with self._pidfile_lock():
                with open(self.pidfile, 'w') as stream:
                    stream.write("%d\n" % pid)
        except IOError as e:
            logger.error(str(e))

    @contextmanager
    def _pidfile_lock(self):
        # Use a separate stable inode: the pidfile itself is replaced/removed.
        with open(self.pidfile + '.lock', 'a') as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def delpid(self):
        # A retiring daemon must not remove its successor's pidfile.
        with self._pidfile_lock():
            try:
                with open(self.pidfile) as stream:
                    owner = int(stream.read().strip())
            except (IOError, ValueError):
                return
            if owner == os.getpid():
                linux.rm_file_force(self.pidfile)

    @staticmethod
    def _process_start_time(pid):
        try:
            with open('/proc/%s/stat' % pid) as stream:
                stat = stream.read()
            # comm may contain spaces and parentheses; starttime is field 22.
            fields = stat[stat.rfind(')') + 2:].split()
            if fields[0] == 'Z':
                return None
            return int(fields[19])
        except (IOError, ValueError, IndexError):
            return None

    def start(self):
        """
        Start the daemon
        """
        Daemon._log_and_dump_message("Start Daemon...")

        locale.setlocale(locale.LC_ALL, 'C')
        os.environ["LC_ALL"]="C"
        os.environ["COLUMNS"] = str(os.sysconf('SC_ARG_MAX'))

        # Get the pid from the pidfile
        try:
            pf = open(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if pid and linux.process_exists(pid):
            message = "Daemon already running, pid is %s\n" % pid
            Daemon._log_and_dump_message(message, sys.stderr)
            sys.exit(0)
        else:
            message = "pidfile %s does not exist. Daemon not running?\n" % self.pidfile
            Daemon._log_and_dump_message(message, sys.stderr)
            self.get_start_agent_by_name()

        Daemon._log_and_dump_message("configure hosts...")
        Daemon.configure_hosts()

        # Start the daemon
        self.daemonize()

        try:
            self.run()
        except Exception:
            content = traceback.format_exc()
            logger.error(content)
            sys.exit(1)

        print("Start Daemon Successfully")

    def stop(self):
        """
        Stop the daemon
        """
        # Bound this stop request to processes that existed before it started.
        # A delayed name lookup must never select a concurrent new start.
        cutoff = self._process_start_time(os.getpid())
        Daemon._log_and_dump_message("Stop Daemon...")

        #wait 2s for gracefully shutdown, then will force kill
        wait_stop = 2

        try:
            pf = open(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if pid and linux.process_exists(pid):
            self._stop_existing_agent(pid, wait_stop, cutoff)
        else:
            message = "pidfile %s does not exist. Daemon not running?\n" % self.pidfile
            Daemon._log_and_dump_message(message)

            pids = linux.get_agent_pid_by_name(self.py_process_name)

            if not pids:
                Daemon._log_and_dump_message("Daemon not running?\n", sys.stderr)
                return # not an error in a restart

            # exclude self pid
            for pid in pids.split('\n'):
                if pid and int(pid) != os.getpid():
                    pid = int(pid)
                    self._stop_existing_agent(pid, wait_stop, cutoff)

    def restart(self):
        """
        Restart the daemon
        """
        logger.debug("Restart Daemon...")
        self.stop()
        self.start()

    def run(self):
        """
        You should override this method when you subclass Daemon. It will be called after the process has been
        daemonized by start() or restart().
        """

    def get_start_agent_by_name(self):
        pids = linux.get_agent_pid_by_name(self.py_process_name)

        for pid in pids.split('\n'):
            if pid and int(pid) != os.getpid():
                pid = int(pid)
                if linux.process_exists(pid):
                    message = "Daemon already running, pid is %s\n" % pid
                    Daemon._log_and_dump_message(message)
                    sys.exit(0)

    def _stop_existing_agent(self, pid, wait_stop, cutoff):
        identity = self._process_start_time(pid)
        if identity is None or cutoff is None or identity >= cutoff:
            Daemon._log_and_dump_message("Skip new or unidentifiable process %s\n" % pid)
            return
        self.stop_agent_by_pid(pid, wait_stop, identity)

    def stop_agent_by_pid(self, pid, wait_stop, expected_start_time=None):
        # Recheck process identity before every signal, including SIGKILL.
        identity = expected_start_time
        if identity is None:
            identity = self._process_start_time(pid)
        if identity is None:
            return
        start_time = time.time()
        while self._process_start_time(pid) == identity:
            try:
                if time.time() - start_time > wait_stop:
                    os.kill(pid, SIGKILL)
                else:
                    os.kill(pid, SIGTERM)
            except OSError as error:
                if error.errno == errno.ESRCH:
                    break
                raise
            time.sleep(0.3)

        print("Stop Daemon Successfully")


    @staticmethod
    def configure_hosts():
        hosts_path = "/etc/hosts"
        hostname = linux.get_host_name()
        to_add_line = "127.0.0.1 %s  # added by ZStack" % hostname
        origin_lines = linux.read_file_lines(hosts_path)
        for line in origin_lines[:]:
            if line.strip().startswith(to_add_line):
                return

            if line.strip().find(hostname) != -1:
                return

        origin_lines.append(to_add_line + '\n')
        linux.write_file_lines(hosts_path, origin_lines)
