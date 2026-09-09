'''
WorkerRestartMonitor - auto-restarts dead TensorFusion Worker processes.

Strategy:
- Background thread polls worker liveness every POLL_INTERVAL seconds.
- On first crash, immediately pushes an event notification to the management node
  via event_notifier so the operator is alerted without waiting for the 60s sync.
- Keeps StateStore entry intact (restarting=True) during recovery to prevent
  the 60s sync from re-reporting Fault on every cycle.
- Retries up to MAX_CRASHES times within CRASH_WINDOW seconds, with backoff.
- On successful restart, clears the notified record; management plane
  auto-recovers via next 60s sync.
- After max retries: removes from store, releases GPU memory.
'''

import threading
import time

from zstacklib.utils import log
from zstacklib.gpu.operation_gate import gpu_operation_gate
from kvmagent.plugins.tensorfusion.base_executor import WorkerExecutor

logger = log.get_logger(__name__)


def _worker_label(w):
    """Return a human-readable worker identifier for logging."""
    return WorkerExecutor.worker_label(w)


class CrashState(object):
    BACKOFF_DELAYS = [5, 15, 30]   # seconds between restart attempts
    CRASH_WINDOW   = 300            # 5-minute sliding window
    MAX_CRASHES    = 3              # max crashes before giving up

    def __init__(self):
        self.crash_count   = 0
        self.window_start  = time.time()
        self.backoff_index = 0

    def record_crash(self):
        """Increment crash counter, reset window if expired. Returns new count."""
        now = time.time()
        if now - self.window_start > self.CRASH_WINDOW:
            self.crash_count   = 0
            self.window_start  = now
            self.backoff_index = 0
        self.crash_count += 1
        return self.crash_count

    def next_backoff(self):
        """Return next backoff delay in seconds."""
        idx = min(self.backoff_index, len(self.BACKOFF_DELAYS) - 1)
        self.backoff_index += 1
        return self.BACKOFF_DELAYS[idx]


class WorkerRestartMonitor(object):
    """
    Monitors all Workers in StateStore. On detecting a dead process:
      1. Marks worker.restarting = True (keeps it in store -> no false Fault).
      2. Waits backoff delay, then restarts the process.
      3. On success: updates worker, clears restarting flag.
      4. On persistent failure (>= MAX_CRASHES): removes worker, releases tracker.
    """

    POLL_INTERVAL = 10  # seconds between liveness checks
    STOP_JOIN_TIMEOUT = 5  # seconds to wait for worker monitor/restart threads on shutdown

    def __init__(self, store, executor, tracker, event_notifier=None, restart_worker=None):
        self._store           = store
        self._executor        = executor
        self._tracker         = tracker
        self._event_notifier  = event_notifier   # callable(device_uuid, vm_uuid, pci_address, crash_count, event_type)
        self._restart_worker  = restart_worker
        self._states          = {}   # {device_uuid: CrashState}
        self._notified_events = set()  # device_uuids already pushed this episode
        self._lock            = threading.Lock()
        self._thread          = None
        self._restart_threads = {}
        self._stop_event      = threading.Event()

    def start(self):
        self._stop_event.clear()
        self._thread  = threading.Thread(target=self._run, name='tf-worker-monitor')
        self._thread.daemon = True
        self._thread.start()
        logger.info('WorkerRestartMonitor: started (poll_interval=%ds)' % self.POLL_INTERVAL)

    def stop(self):
        self._stop_event.set()

        if self._thread and self._thread.is_alive() and threading.current_thread() is not self._thread:
            self._thread.join(self.STOP_JOIN_TIMEOUT)
            if self._thread.is_alive():
                logger.warning('WorkerRestartMonitor: monitor thread did not exit within %ss' % self.STOP_JOIN_TIMEOUT)

        with self._lock:
            restart_threads = list(self._restart_threads.values())

        current = threading.current_thread()
        for thread in restart_threads:
            if thread is current:
                continue
            thread.join(self.STOP_JOIN_TIMEOUT)
            if thread.is_alive():
                logger.warning('WorkerRestartMonitor: restart thread %s did not exit within %ss' % (
                    thread.name, self.STOP_JOIN_TIMEOUT))

    def clear(self, device_uuid):
        """Remove crash tracking when a worker is intentionally destroyed."""
        with self._lock:
            self._states.pop(device_uuid, None)
            self._notified_events.discard(device_uuid)

    # ---- background thread ----

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._check_all()
            except Exception as e:
                logger.error('WorkerRestartMonitor: unexpected error: %s' % e)
            if self._stop_event.wait(self.POLL_INTERVAL):
                break

    def _check_all(self):
        for w in self._store.list_all():
            if self._stop_event.is_set():
                break
            if w.restarting:
                continue  # already being restarted by another thread
            if not self._executor.is_alive(w):
                self._handle_dead(w)

    # ---- crash handling ----

    def _handle_dead(self, w):
        device_uuid = w.device_uuid
        logger.error('WorkerRestartMonitor: worker %s (%s) died for vm=%s' % (
            device_uuid, _worker_label(w), w.vm_uuid))

        with self._lock:
            state = self._states.get(device_uuid)
            if state is None:
                state = CrashState()
                self._states[device_uuid] = state
            count = state.record_crash()
            already_notified = device_uuid in self._notified_events
            if count <= CrashState.MAX_CRASHES:
                backoff = state.next_backoff()
            else:
                backoff = None

        if count > CrashState.MAX_CRASHES:
            logger.error(
                'WorkerRestartMonitor: worker %s exceeded max retries '
                '(%d crashes within %ds window), giving up' % (
                    device_uuid, count, CrashState.CRASH_WINDOW))
            current_worker = self._store.get(device_uuid)
            if current_worker is not w:
                self.clear(device_uuid)
                logger.info('WorkerRestartMonitor: worker %s changed before give-up, skipping stale fault handling' %
                            device_uuid)
                return

            if not already_notified:
                with self._lock:
                    self._notified_events.add(device_uuid)
                self._push_event(current_worker, count, 'fault')

            self._give_up(current_worker)
            return

        logger.warning(
            'WorkerRestartMonitor: scheduling restart for worker %s '
            'in %ds (attempt %d/%d)' % (device_uuid, backoff, count, CrashState.MAX_CRASHES))

        # Keep the canonical store entry alive during restart -> management plane won't see Fault.
        current_worker = self._store.set_restarting(device_uuid, True, expected_worker=w)
        if current_worker is None:
            self.clear(device_uuid)
            logger.info('WorkerRestartMonitor: worker %s changed before restart scheduling, skipping stale restart' %
                        device_uuid)
            return

        if not already_notified:
            with self._lock:
                self._notified_events.add(device_uuid)
            self._push_event(current_worker, count, 'fault')

        t = threading.Thread(target=self._do_restart, args=(current_worker, backoff),
                             name='tf-restart-%s' % device_uuid[:8])
        t.daemon = True
        with self._lock:
            self._restart_threads[device_uuid] = t
        t.start()

    def _do_restart(self, w, backoff):
        device_uuid = w.device_uuid
        try:
            if self._stop_event.wait(backoff):
                self._store.set_restarting(device_uuid, False, expected_worker=w)
                logger.info('WorkerRestartMonitor: stop requested during backoff, skipping restart for worker %s' %
                            device_uuid)
                return

            current_worker = self._store.get(device_uuid)
            if current_worker is not w:
                self.clear(device_uuid)
                logger.info('WorkerRestartMonitor: worker %s changed during backoff, skipping stale restart' %
                            device_uuid)
                return

            # Reap the old dead process to prevent zombie.
            try:
                with gpu_operation_gate.critical():
                    if self._store.get(device_uuid) is not w:
                        self.clear(device_uuid)
                        logger.info('WorkerRestartMonitor: worker %s changed during backoff, skipping stale restart' %
                                    device_uuid)
                        return
                    reaped = self._executor.reap_dead(w)
            except Exception as e:
                logger.warning('WorkerRestartMonitor: failed to reap dead worker %s (%s): %s' %
                            (device_uuid, _worker_label(w), e))
                self._store.set_restarting(device_uuid, False, expected_worker=w)
                return
            if reaped is False:
                logger.warning('WorkerRestartMonitor: worker %s (%s) is still running, skipping restart' %
                            (device_uuid, _worker_label(w)))
                self.clear(device_uuid)
                self._store.set_restarting(device_uuid, False, expected_worker=w)
                return

            # Guard: worker may have been intentionally destroyed or replaced while we waited.
            current_worker = self._store.get(device_uuid)
            if current_worker is not w:
                self.clear(device_uuid)
                logger.info('WorkerRestartMonitor: worker %s changed during backoff, skipping stale restart' %
                            device_uuid)
                return

            # Guard: skip restart if the owning VM no longer exists in libvirt
            # (e.g. VM was deleted/undefined while we were in backoff).
            # is_vm_running returns True/False/None; None means query failed
            # — proceed with restart to avoid dropping a healthy worker.
            from kvmagent.plugins.tensorfusion.utils import is_vm_running
            vm_state = is_vm_running(current_worker.vm_uuid)
            if vm_state is False:
                logger.info('WorkerRestartMonitor: VM %s no longer running, '
                            'skipping restart for worker %s' % (current_worker.vm_uuid, device_uuid))
                self._give_up(current_worker)
                return

            if self._stop_event.is_set():
                self._store.set_restarting(device_uuid, False, expected_worker=current_worker)
                logger.info('WorkerRestartMonitor: stop requested before restart, skipping worker %s' % device_uuid)
                return

            try:
                if self._restart_worker is None:
                    raise Exception('restart handler is not configured')

                new_worker = self._restart_worker(current_worker)
                if new_worker is None:
                    self.clear(device_uuid)
                    logger.warning('WorkerRestartMonitor: worker %s changed during restart, skipping stale replacement' %
                                device_uuid)
                    return

                with self._lock:
                    self._notified_events.discard(device_uuid)
                logger.info('WorkerRestartMonitor: restarted worker %s (%s)' % (
                    device_uuid, _worker_label(new_worker)))
            except Exception as e:
                logger.error('WorkerRestartMonitor: failed to restart worker %s: %s' % (device_uuid, e))
                self._store.set_restarting(device_uuid, False, expected_worker=current_worker)
                # Will be detected again on next poll cycle; crash counter already incremented
        finally:
            with self._lock:
                thread = self._restart_threads.get(device_uuid)
                if thread is threading.current_thread():
                    self._restart_threads.pop(device_uuid, None)

    def _give_up(self, w):
        device_uuid = w.device_uuid
        # Reap the dead process to prevent zombie.
        try:
            with gpu_operation_gate.critical():
                if self._store.get(device_uuid) is not w:
                    self.clear(device_uuid)
                    logger.info('WorkerRestartMonitor: worker %s changed before give-up cleanup, skipping stale purge' %
                                device_uuid)
                    return False
                reaped = self._executor.reap_dead(w)
                if reaped is False:
                    logger.warning('WorkerRestartMonitor: worker %s is still running during give_up' %
                                device_uuid)
                    self.clear(device_uuid)
                    self._store.set_restarting(device_uuid, False, expected_worker=w)
                    return False

                removed = self._store.remove(device_uuid, expected_worker=w)
                if removed is not None:
                    self._tracker.release(removed.pci_address, device_uuid)
        except Exception as e:
            logger.warning('WorkerRestartMonitor: failed to reap dead worker %s '
                        'during give_up: %s' % (device_uuid, e))
            self._store.set_restarting(device_uuid, False, expected_worker=w)
            return False
        if removed is None:
            self.clear(device_uuid)
            logger.info('WorkerRestartMonitor: worker %s changed before give-up cleanup, skipping stale purge' %
                        device_uuid)
            return False

        with self._lock:
            self._states.pop(device_uuid, None)
            self._notified_events.discard(device_uuid)
        logger.error(
            'WorkerRestartMonitor: purged dead worker %s, '
            'GPU memory released; management plane will confirm Fault on next sync' % device_uuid)
        return True

    def _push_event(self, w, crash_count, event_type):
        """Push event notification to management node. No-op if no notifier configured."""
        if not self._event_notifier:
            return
        try:
            self._event_notifier(w.device_uuid, w.vm_uuid, w.pci_address, crash_count, event_type)
            logger.warning('WorkerRestartMonitor: pushed %s event for worker %s '
                        '(crashCount=%d, vm=%s)' % (event_type, w.device_uuid, crash_count, w.vm_uuid))
        except Exception as e:
            logger.error('WorkerRestartMonitor: failed to push %s event '
                         'for worker %s: %s' % (event_type, w.device_uuid, e))
