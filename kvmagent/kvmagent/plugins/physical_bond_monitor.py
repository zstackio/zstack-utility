import glob
import os
import threading
import time

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import linux
from zstacklib.utils import bash

try:
    unicode
except NameError:
    unicode = str

log.configure_log('/var/log/zstack/zstack-kvmagent.log')
logger = log.get_logger(__name__)


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None


class BondScenario(object):
    ACTIVE_BACKUP = 'ACTIVE_BACKUP'
    LACP = 'LACP'


class BondSlaveInfo(object):
    def __init__(self, name):
        self.name = name
        self.mii_up = False
        self.aggregator_id = None
        self.actor_state = None
        self.partner_state = None
        self._current_pdu = None

    def consume_line(self, line):
        if ':' not in line:
            return
        key, value = [chunk.strip() for chunk in line.split(':', 1)]
        key_lower = key.lower()

        if key_lower.startswith('details') and 'lacp' in key_lower:
            if 'actor' in key_lower:
                self._current_pdu = 'actor'
            elif 'partner' in key_lower:
                self._current_pdu = 'partner'
            else:
                self._current_pdu = None
            return

        if key_lower == 'port state' and self._current_pdu:
            bits = self._parse_state_bits(value)
            if self._current_pdu == 'actor':
                self.actor_state = bits
            elif self._current_pdu == 'partner':
                self.partner_state = bits
            self._current_pdu = None
            return
        if key_lower == 'mii status':
            self.mii_up = value.lower() == 'up'
            return

        if key_lower == 'aggregator id':
            try:
                self.aggregator_id = int(value)
            except ValueError:
                self.aggregator_id = None
            return

        if key_lower in ('actor oper port state', 'actor state'):
            self.actor_state = self._parse_state_bits(value)
            return

        if key_lower in ('partner oper port state', 'partner state'):
            self.partner_state = self._parse_state_bits(value)
            return

    @staticmethod
    def _parse_state_bits(value):
        value = value.strip().lower()
        if value.startswith('0x'):
            try:
                return int(value, 16)
            except ValueError:
                return None

        try:
            return int(value)
        except ValueError:
            return None

    def is_lacp_usable(self):
        if not self.mii_up or not self.aggregator_id:
            return False
        state_bits = self.actor_state if self.actor_state is not None else self.partner_state
        if state_bits is None:
            return False
        collecting = bool(state_bits & 0x10)
        distributing = bool(state_bits & 0x20)
        return collecting and distributing


class BondInfo(object):
    def __init__(self, name):
        self.name = name
        self.mode = ''
        self.active_slave = None
        self.slaves = {}

    @classmethod
    def from_string(cls, name, content):
        info = cls(name)
        current_slave = None
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            lower = line.lower()
            if lower.startswith('bonding mode:'):
                info.mode = line.split(':', 1)[1].strip()
                continue

            if lower.startswith('currently active slave:'):
                slave_name = line.split(':', 1)[1].strip()
                info.active_slave = slave_name if slave_name and slave_name != 'None' else None
                continue

            if lower.startswith('slave interface:'):
                slave_name = line.split(':', 1)[1].strip()
                current_slave = BondSlaveInfo(slave_name)
                info.slaves[slave_name] = current_slave
                continue

            if current_slave is not None:
                current_slave.consume_line(line)

        return info


class BondControl(object):
    def __init__(self, bond_name, scenario, debounce):
        self.bond_name = bond_name
        self.scenario = scenario
        self.debounce = debounce
        self.applied_state = {}
        self.pending_state = None
        self.pending_since = 0
        self.initialized = False

    def update_settings(self, scenario, debounce):
        scenario_changed = scenario and scenario != self.scenario
        if scenario_changed:
            self.scenario = scenario
            self.initialized = False
            self.applied_state = {}
            self.pending_state = None

        if debounce is not None:
            self.debounce = debounce

    def update_desired(self, desired_state, now, agent):
        if not desired_state:
            return

        desired = dict(desired_state)
        for pf in list(self.applied_state.keys()):
            desired.setdefault(pf, False)

        if not self.initialized:
            self._apply(desired, agent, 'initial sync')
            self.applied_state = desired
            self.initialized = True
            self.pending_state = None
            return

        if desired == self.applied_state:
            self.pending_state = None
            return

        if self.pending_state is not None and desired == self.pending_state:
            return

        self.pending_state = desired
        self.pending_since = now

    def try_apply(self, now, agent):
        if not self.pending_state:
            return
        if now - self.pending_since < self.debounce:
            return

        self._apply(self.pending_state, agent, 'stable for %.3fs' % (now - self.pending_since))
        self.applied_state = self.pending_state
        self.pending_state = None

    def _apply(self, states, agent, reason):
        for pf, desired in states.items():
            previous = self.applied_state.get(pf)
            if self.initialized and previous == desired:
                continue

            try:
                agent._set_pf_vfs_state(pf, desired)
                logger.info('bond %s pf %s: %s -> %s (%s)',
                            self.bond_name, pf,
                            'usable' if previous else 'blocked',
                            'usable' if desired else 'blocked',
                            reason)
            except Exception as err:
                logger.warn('failed to set pf %s state for bond %s: %s', pf, self.bond_name, err)


class PhysicalBondMonitor(kvmagent.KvmAgent):
    UPDATE_PHYSICAL_BOND_MONITOR = "/host/physicalBond/update"
    DEFAULT_POLL_INTERVAL = 0.3
    MIN_POLL_INTERVAL = 0.05
    DEFAULT_STABILIZE_WINDOW = 0.5
    MIN_STABILIZE_WINDOW = 0.1

    def __init__(self):
        super(PhysicalBondMonitor, self).__init__()
        self.config = {}
        self._bond_settings = {}
        self._bond_states = {}
        self._poll_interval = self.DEFAULT_POLL_INTERVAL
        self._default_stabilize = self.DEFAULT_STABILIZE_WINDOW
        self._enabled = False
        self._state_lock = threading.RLock()
        self._worker = None
        self._stop_event = threading.Event()
        self._bond_whitelist = None

    def configure(self, config):
        self.config = config

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.UPDATE_PHYSICAL_BOND_MONITOR, self.update_physical_bond_monitor)

    def stop(self):
        with self._state_lock:
            self._enabled = False
            self._stop_worker_locked()

    @kvmagent.replyerror
    def update_physical_bond_monitor(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        state = getattr(cmd, 'state', None)
        polling_interval = getattr(cmd, 'pollingInterval', None) or getattr(cmd, 'interval', None)
        stabilize = getattr(cmd, 'stabilizeWindow', None)
        bond_settings = self._parse_bond_settings(cmd)
        whitelist = getattr(cmd, 'bondNames', None)

        with self._state_lock:
            if polling_interval is not None:
                try:
                    interval = max(self.MIN_POLL_INTERVAL, float(polling_interval))
                    self._poll_interval = interval
                except (TypeError, ValueError):
                    logger.warn('ignore invalid pollingInterval value %s', polling_interval)

            if stabilize is not None:
                try:
                    window = max(self.MIN_STABILIZE_WINDOW, float(stabilize))
                    self._default_stabilize = window
                except (TypeError, ValueError):
                    logger.warn('ignore invalid stabilizeWindow value %s', stabilize)

            if bond_settings is not None:
                self._bond_settings = bond_settings

            if whitelist is not None:
                if isinstance(whitelist, (str, unicode)):
                    whitelist = [whitelist]
                cleaned = [name for name in whitelist if name]
                self._bond_whitelist = set(cleaned) if cleaned else None

            if state is None:
                state = True

            if state:
                self._enabled = True
                self._ensure_worker_locked()
                self._sync_once_locked()
            else:
                self._enabled = False
                self._stop_worker_locked()
                self._bond_states.clear()

        return jsonobject.dumps(AgentRsp())

    def _ensure_worker_locked(self):
        if self._worker and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self._run_loop, name='PhysicalBondMonitor')
        self._worker.daemon = True
        self._worker.start()

    def _stop_worker_locked(self):
        if not self._worker:
            return
        self._stop_event.set()
        self._worker.join()
        self._worker = None
        self._stop_event = threading.Event()

    def _run_loop(self):
        while not self._stop_event.is_set():
            start = time.time()
            try:
                self._sync_once()
            except Exception as e:
                logger.warn('physical bond monitor loop failed: %s', str(e))
            elapsed = time.time() - start
            wait_for = max(self.MIN_POLL_INTERVAL, self._poll_interval - elapsed)
            if self._stop_event.wait(wait_for):
                break

    def _sync_once(self):
        with self._state_lock:
            self._sync_once_locked()

    def _sync_once_locked(self):
        if not self._enabled:
            return

        bond_names = self._list_bonds()
        now = time.time()
        active_bonds = set()

        for bond_name in bond_names:
            info = self._read_bond_info(bond_name)
            if info is None or not info.slaves:
                continue

            scenario = self._resolve_scenario(bond_name, info.mode)
            if not scenario:
                continue

            debounce = self._bond_settings.get(bond_name, {}).get('stabilize') or self._default_stabilize
            control = self._bond_states.get(bond_name)
            if control is None:
                control = BondControl(bond_name, scenario, debounce)
                self._bond_states[bond_name] = control
            else:
                control.update_settings(scenario, debounce)

            desired = self._build_desired_state(info, scenario)
            control.update_desired(desired, now, self)
            control.try_apply(now, self)
            active_bonds.add(bond_name)

        stale = set(self._bond_states.keys()) - active_bonds
        for bond in stale:
            logger.debug('remove stale bond control %s', bond)
            self._bond_states.pop(bond, None)

    def _list_bonds(self):
        try:
            masters = linux.read_file("/sys/class/net/bonding_masters")
        except IOError:
            return []

        if not masters:
            return []

        names = [name.strip() for name in masters.replace('\n', ' ').split(' ') if name.strip()]

        if self._bond_whitelist is None:
            return []

        return [name for name in names if name in self._bond_whitelist]

    def _read_bond_info(self, bond_name):
        path = "/proc/net/bonding/%s" % bond_name
        try:
            content = linux.read_file(path)
        except IOError:
            logger.debug('bond info %s not found', bond_name)
            return None

        return BondInfo.from_string(bond_name, content)

    def _resolve_scenario(self, bond_name, bond_mode):
        config = self._bond_settings.get(bond_name)
        if config:
            if config.get('enabled') is False:
                return None
            if config.get('scenario'):
                return config.get('scenario')

        if not bond_mode:
            return None

        mode_lower = bond_mode.lower()
        if 'active-backup' in mode_lower or 'active backup' in mode_lower:
            return BondScenario.ACTIVE_BACKUP
        if '802.3ad' in mode_lower or 'lacp' in mode_lower:
            return BondScenario.LACP

        logger.debug('skip bond %s, unsupported bonding mode %s', bond_name, bond_mode)
        return None

    def _build_desired_state(self, bond_info, scenario):
        desired = {}
        if scenario == BondScenario.ACTIVE_BACKUP:
            active_slave = bond_info.active_slave
            for name, slave in bond_info.slaves.items():
                desired[name] = bool(active_slave and active_slave == name and slave.mii_up)
            return desired

        if scenario == BondScenario.LACP:
            for name, slave in bond_info.slaves.items():
                desired[name] = slave.is_lacp_usable()
            return desired

        return desired

    def _parse_bond_settings(self, cmd):
        raw = getattr(cmd, 'bonds', None)
        if raw is None:
            raw = getattr(cmd, 'bondSettings', None)
        if raw is None:
            return None

        configs = {}
        for item in raw:
            name = getattr(item, 'bondName', None) or getattr(item, 'name', None)
            if not name:
                continue

            scenario = getattr(item, 'scenario', None) or getattr(item, 'policy', None)
            scenario = self._normalize_scenario(scenario)
            stabilize = getattr(item, 'stabilizeWindow', None) or getattr(item, 'debounce', None)

            window_value = None
            if stabilize is not None:
                try:
                    window_value = max(self.MIN_STABILIZE_WINDOW, float(stabilize))
                except (TypeError, ValueError):
                    logger.warn('invalid stabilize window %s for bond %s, use default', stabilize, name)

            enabled = getattr(item, 'enabled', None)

            configs[name] = {
                'scenario': scenario,
                'stabilize': window_value,
                'enabled': None if enabled is None else bool(enabled)
            }

        return configs

    @staticmethod
    def _normalize_scenario(value):
        if not value:
            return None

        text = value.strip().lower()
        if text in ('ab', 'active-backup', 'active_backup', 'activebackup'):
            return BondScenario.ACTIVE_BACKUP
        if text in ('lacp', '802.3ad', '8023ad', 'lacp_xor', 'xor'):
            return BondScenario.LACP
        return None

    def _set_pf_vfs_state(self, pf_name, enable):
        vf_indexes = self._get_vf_indexes(pf_name)
        if not vf_indexes:
            logger.debug('pf %s has no vf to operate on', pf_name)
            return

        driver = self._get_pf_driver(pf_name)
        if enable:
            # ixgbe do not support virtual function state enable
            state = 'auto' if driver == 'ixgbe' else 'enable'
        else:
            state = 'disable'

        success_count = 0
        for vf_index in vf_indexes:
            rc, out, err = bash.bash_roe("ip link set %s vf %d state %s" % (pf_name, vf_index, state))
            if rc != 0:
                logger.warn('failed to set pf %s vf %d state %s: %s %s', pf_name, vf_index, state, out, err)
            else:
                success_count += 1

        if success_count > 0:
            logger.debug('pf %s vfs(%d/%d) state set to %s (driver: %s)', pf_name, success_count, len(vf_indexes), state, driver or 'unknown')

    def _get_pf_driver(self, pf_name):
        path = '/sys/class/net/{0}/device/driver'.format(pf_name)
        if not os.path.islink(path):
            return None
        try:
            return os.path.basename(os.path.realpath(path))
        except OSError:
            return None

    def _get_vf_indexes(self, pf_name):
        base_path = os.path.join("/sys/class/net", pf_name, "device")
        if not os.path.isdir(base_path):
            logger.debug('pf %s device path %s not found', pf_name, base_path)
            return []

        indexes = []
        for vf_path in glob.glob(os.path.join(base_path, "virtfn*")):
            name = os.path.basename(vf_path)
            suffix = name.replace('virtfn', '')
            try:
                indexes.append(int(suffix))
            except ValueError:
                continue

        indexes.sort()
        return indexes
