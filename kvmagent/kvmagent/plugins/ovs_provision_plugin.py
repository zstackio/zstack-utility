# -*- coding: utf-8 -*-
import json
import os
import re
import shlex
import time
import traceback

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import bash
from zstacklib.utils import ovn
from zstacklib.utils import ovs as ovs_utils  # for getBDFOfInterface

logger = log.get_logger(__name__)

OVS_PROVISION_PATH = '/network/ovs/provision'
OVS_DEPROVISION_PATH = '/network/ovs/deprovision'
MANAGED_BY_KEY = 'managed-by'
MANAGED_BY_VALUE = 'zstack-agent'
CONFIG_VERSION_KEY = 'config-version'
PORT_ROLE_KEY = 'port-role'
PORT_ROLE_BOND = 'bond'
HOST_UUID_KEY = 'host-uuid'
UPLINK_PROFILE_UUID_KEY = 'uplink-profile-uuid'
SDN_CONTROLLER_UUID_KEY = 'sdn-controller-uuid'
OVS_SYSTEM_ID_CONF_PATH = '/etc/openvswitch/system-id.conf'

MANAGED_OVS_EXTERNAL_ID_KEYS = frozenset({
    'ovn-remote', 'ovn-encap-type', 'ovn-encap-ip',
    'system-id', 'ovn-bridge-mappings',
    'ovn-bfd-min-tx', 'ovn-bfd-min-rx', 'ovn-bfd-mult',
    SDN_CONTROLLER_UUID_KEY,
})

# DPDK-related other_config keys that must be cleared when switching from
# DPDK to kernel mode or during deprovision, to prevent dpdk_initialized
# from lingering as true.
DPDK_OTHER_CONFIG_KEYS = [
    'dpdk-init', 'dpdk-socket-mem', 'dpdk-lcore-mask',
    'pmd-cpu-mask', 'hw-offload', 'dpdk-extra', 'userspace-tso-enable',
]

# Allowed characters for OVS entity names (bridge, port, bond, interface).
# OVS names are typically alphanumeric with hyphens, underscores, and dots.
_OVS_NAME_RE = re.compile(r'^[a-zA-Z0-9._-]+$')

# Allowed characters for OVS column keys and map keys interpolated into commands.
_OVS_KEY_RE = re.compile(r'^[a-zA-Z0-9._:-]+$')

# Allowed characters for IP address with optional CIDR prefix (e.g. 10.0.0.1/24).
_IP_ADDR_RE = re.compile(r'^[0-9a-fA-F.:/%]+$')

# Allowed characters for OVS external_ids values interpolated into shell commands.
# Permits alphanumerics, dots, colons, commas, hyphens, underscores, slashes, and equals.
_OVS_EXT_ID_VALUE_RE = re.compile(r'^[a-zA-Z0-9.,_:/@=+-]+$')


def _validate_external_id_value(value):
    """Validate that an OVS external_ids value is safe for shell interpolation.

    Raises ValueError if the value contains shell meta-characters.
    """
    if not value or not _OVS_EXT_ID_VALUE_RE.match(value):
        raise ValueError('invalid OVS external_ids value: %r' % value)
    return value


def _validate_ovs_name(name):
    """Validate that an OVS entity name contains only safe characters.

    Raises ValueError if the name contains characters that could lead to
    command injection when interpolated into shell commands.
    """
    if not name or not _OVS_NAME_RE.match(name):
        raise ValueError('invalid OVS entity name: %r' % name)
    return name


def _validate_ovs_key(key):
    if not key or not _OVS_KEY_RE.match(key):
        raise ValueError('invalid OVS key: %r' % key)
    return key


def _quote_ovs_value(value):
    return shlex.quote(str(value))


def _validate_ip_address(addr):
    """Validate that an IP address string contains only safe characters.

    Raises ValueError if the address contains unexpected characters.
    """
    if not addr or not _IP_ADDR_RE.match(addr):
        raise ValueError('invalid IP address: %r' % addr)
    return addr


def _has_active_ipv4_route(route_output):
    """Return True if route output contains a non-link-local IPv4 route."""
    if not route_output:
        return False

    for line in route_output.splitlines():
        route = line.strip()
        if not route:
            continue
        if 'linkdown' in route or 'linklocal' in route:
            continue

        destination = route.split()[0]
        if destination == '169.254.0.0/16' or destination.startswith('169.254.'):
            continue

        return True

    return False


_PCI_ADDR_RE = re.compile(r'^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-9a-fA-F]$')

# Userspace drivers that take NICs away from the kernel networking stack.
_DPDK_USERSPACE_DRIVERS = ('vfio-pci', 'uio_pci_generic')


def _get_dpdk_bound_network_devices():
    """Detect network devices bound to DPDK userspace drivers via sysfs.

    Scans /sys/bus/pci/drivers/{vfio-pci,uio_pci_generic} for PCI devices
    whose class is 0x02xxxx (Network controller).

    Unlike pci.getAllVfioPciNic() which parses dpdk-devbind.py output with
    ``grep drv=`` (and misses devices listed under "Other Network devices"
    that lack a ``drv=`` field), this function reads sysfs directly and is
    reliable regardless of dpdk-devbind.py output format.

    Returns:
        list[str]: PCI addresses (e.g. ['0000:00:04.0']) of network devices
                   currently bound to a DPDK userspace driver.
    """
    result = []
    for drv_name in _DPDK_USERSPACE_DRIVERS:
        drv_path = '/sys/bus/pci/drivers/%s' % drv_name
        if not os.path.isdir(drv_path):
            continue
        try:
            entries = os.listdir(drv_path)
        except OSError as e:
            logger.warn('failed to list %s devices: %s' % (drv_name, e))
            continue
        for entry in entries:
            if not _PCI_ADDR_RE.match(entry):
                continue
            try:
                class_path = os.path.join(drv_path, entry, 'class')
                if not os.path.exists(class_path):
                    continue
                with open(class_path, 'r') as f:
                    pci_class = f.read().strip()
            except OSError as e:
                logger.warn('failed to inspect %s device %s: %s'
                            % (drv_name, entry, e))
                continue
            # PCI class 0x02xxxx = Network controller
            if pci_class.startswith('0x02'):
                result.append(entry)
                logger.debug('found %s bound network device: %s (class=%s)'
                             % (drv_name, entry, pci_class))

    return result


def _apply_tunnel_mtu(tunnel_mtu):
    """Apply tunnel MTU to all geneve interfaces and managed bridge internal ports.

    This sets mtu_request on:
    1. All OVS interfaces of type=geneve (tunnel ports created by ovn-controller)
    2. All managed bridge internal ports (bridges with managed-by=zstack-agent)
    """
    tunnel_mtu = int(tunnel_mtu)

    # 1. Find and update geneve tunnel interfaces
    r, o, _e = bash.bash_roe(
        "ovs-vsctl --no-headings --columns=name find interface type=geneve")
    if r == 0 and o.strip():
        for line in o.strip().splitlines():
            iface_name = line.split(':', 1)[-1].strip().strip('"')
            if not iface_name:
                continue
            try:
                _validate_ovs_name(iface_name)
            except ValueError:
                logger.warn('skip invalid interface name from ovsdb: %r' % iface_name)
                continue
            r2, _, e2 = bash.bash_roe(
                'ovs-vsctl set interface %s mtu_request=%s' % (iface_name, tunnel_mtu))
            if r2 != 0:
                logger.warn('failed to set mtu_request=%s on geneve interface %s: %s'
                            % (tunnel_mtu, iface_name, e2))
            else:
                logger.info('set mtu_request=%s on geneve interface %s'
                            % (tunnel_mtu, iface_name))

    # 2. Find managed bridges and set mtu_request on their internal ports
    vsctl = ovn.VsCtl()
    for br_name in vsctl.listBridges():
        _validate_ovs_name(br_name)
        ext_ids = vsctl.getBridgeExternalIds(br_name)
        if ext_ids.get(MANAGED_BY_KEY) == MANAGED_BY_VALUE:
            r3, _, e3 = bash.bash_roe(
                'ovs-vsctl set interface %s mtu_request=%s' % (br_name, tunnel_mtu))
            if r3 != 0:
                logger.warn('failed to set mtu_request=%s on bridge internal port %s: %s'
                            % (tunnel_mtu, br_name, e3))
            else:
                logger.info('set mtu_request=%s on bridge internal port %s'
                            % (tunnel_mtu, br_name))


# --- Data models ---

class ProvisionResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ProvisionResponse, self).__init__()
        self.hostUuid = None
        self.hostSwitches = []
        self.cloudCallbackUrl = None
        self.cloudTaskUuid = None
        self.triggerUrl = None


class DeprovisionResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DeprovisionResponse, self).__init__()
        self.hostUuid = None
        self.cloudCallbackUrl = None
        self.cloudTaskUuid = None
        self.triggerUrl = None


class ActualBridge(object):
    def __init__(self, name):
        self.name = name
        self.datapath_type = None
        self.external_ids = {}
        self.bonds = {}       # name -> ActualBond


class ActualBond(object):
    def __init__(self, name):
        self.name = name
        self.members = []
        self.bond_mode = None
        self.lacp = None
        self.external_ids = {}
        self.member_mtus = {}  # member_name -> mtu_request


class DefaultDpdkConfig(object):
    """Default DPDK config when dpdkConfig is not provided in the request.

    Mirrors the defaults used by ovn.py OvsDpdkEnv.
    """
    def __init__(self, nic_pci_map=None):
        self.lcores = '1'
        self.pmdcores = '4,5,6,7'
        self.hugePageNumber = 1024
        self.hugePageSize = 2           # 2MB pages
        self.socketMem = 1024           # MB
        self.nicNamePciAddressMap = nic_pci_map
        self.nicRxQueueNumber = 2
        self.nicRxQueueDescNumber = 2048


class BondSpec(object):
    """Desired state for a bond on an infrastructure bridge."""
    def __init__(self, name, members, mode='balance-slb',
                 mtu=None, switch_type=None, uplink_uuid=None,
                 transport_vlan=0):
        self.name = name
        self.members = members
        self.mode = mode
        self.mtu = mtu
        self.switch_type = switch_type   # 'dpdk' or None
        self.uplink_uuid = uplink_uuid
        self.transport_vlan = transport_vlan or 0


class InfraBridgeSpec(object):
    """Desired state for an infrastructure bridge."""
    def __init__(self, name, datapath_type='system', overlay_vlan=0):
        self.name = name
        self.datapath_type = datapath_type
        self.overlay_vlan = overlay_vlan or 0
        self.bonds = {}  # name -> BondSpec


class IpAddressSpec(object):
    """Desired state for an IP address on a device."""
    def __init__(self, device, address):
        self.device = device
        self.address = address


class OvsDesiredState(object):
    """Complete desired state."""

    # Linux IFNAMSIZ = 16 (including '\0'), so max interface name = 15 chars.
    # OVS uses the bridge name as the internal-port interface name, and when
    # it exceeds 15 characters the kernel netdev is silently NOT created,
    # causing all subsequent ip-addr/ip-link commands to fail.
    _MAX_IFNAME_LEN = 15

    def __init__(self):
        self.host_uuid = None
        self.config_version = None
        self.dpdk_config = None
        self.sdn_controller_uuid = None  # ZNS cluster UUID for ownership (ZCF-2786)
        self.infra_bridges = {}        # name -> InfraBridgeSpec
        self.ip_addresses = {}
        self.ovs_external_ids = {}
        self.tunnel_mtu = None         # tunnel MTU from globalConfig

    @staticmethod
    def _safe_ifname(name, label='interface'):
        """Truncate an OVS entity name to fit Linux IFNAMSIZ (max 15 chars).

        If the original name exceeds 15 characters, it is truncated to 9
        characters followed by a dash and a 5-character hash suffix derived
        from the full name so that different long names produce different
        short names.  For example:
            'br-provider1-bond0'  ->  'br-provid-a3f1c'
        """
        if len(name) <= OvsDesiredState._MAX_IFNAME_LEN:
            return name
        import hashlib
        suffix = hashlib.sha256(name.encode('utf-8')).hexdigest()[:5]
        prefix = name[:OvsDesiredState._MAX_IFNAME_LEN - 6]  # 15 - 1(dash) - 5(hash)
        short = '%s-%s' % (prefix, suffix)
        logger.info('%s name "%s" exceeds %d chars, shortened to "%s"'
                    % (label, name, OvsDesiredState._MAX_IFNAME_LEN, short))
        return short

    @staticmethod
    def _safe_bridge_name(name):
        """Truncate bridge name to fit Linux IFNAMSIZ (max 15 chars)."""
        return OvsDesiredState._safe_ifname(name, 'bridge')


class OvsActualState(object):
    """Complete actual state."""
    def __init__(self):
        self.all_bridges = {}           # name -> {'datapath_type': str}
        self.managed_bridge_names = set()  # bridge names with managed-by=zstack-agent
        self.managed_bonds = {}         # br_name -> {bond_name -> ActualBond}
        self.ip_addresses = {}
        self.ovs_external_ids = {}


# --- OVS State Querier ---

class OvsStateQuerier(object):

    def __init__(self):
        self.vsctl = ovn.VsCtl()

    def _list_ports_safe(self, bridge):
        """listPorts wrapper that raises on failure instead of returning []."""
        _validate_ovs_name(bridge)
        r, o, e = bash.bash_roe('ovs-vsctl list-ports %s' % bridge)
        if r != 0:
            raise Exception('failed to list ports on bridge %s: %s' % (bridge, e))
        return [line.strip() for line in o.strip().splitlines() if line.strip()]

    def _get_bridge_external_ids_safe(self, bridge):
        """getBridgeExternalIds wrapper that raises on failure instead of returning {}."""
        _validate_ovs_name(bridge)
        r, o, e = bash.bash_roe('ovs-vsctl br-get-external-id %s' % bridge)
        if r != 0:
            raise Exception('failed to get external_ids for bridge %s: %s' % (bridge, e))
        result = {}
        for line in o.strip().splitlines():
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                result[k.strip()] = v.strip()
        return result

    def _get_external_ids_safe(self, table, name):
        """getExternalIds wrapper that raises on failure instead of returning {}."""
        r, o, e = bash.bash_roe('ovs-vsctl get %s %s external_ids' % (table, name))
        if r != 0:
            raise Exception('failed to get external_ids for %s %s: %s' % (table, name, e))
        return self.vsctl.parseOvsMap(o.strip())

    def _list_bond_members_safe(self, port_name):
        """listBondMembers wrapper that raises on failure instead of returning []."""
        err, iface_uuids_raw = self.vsctl.getTableAttr('port', port_name, 'interfaces')
        if err or not iface_uuids_raw:
            raise Exception('failed to query interfaces for port %s' % port_name)
        uuids = [u.strip() for u in iface_uuids_raw.strip('[]').split(',') if u.strip()]
        names = []
        for iface_uuid in uuids:
            err, name = self.vsctl.getTableAttr('interface', iface_uuid, 'name')
            if err or not name:
                raise Exception('failed to resolve interface uuid %s for port %s'
                                % (iface_uuid, port_name))
            names.append(name)
        return sorted(names)

    def _query_managed_bridge_names(self):
        """Query names of all bridges managed by zstack-agent."""
        names = set()
        br_names = self.vsctl.listBridges()
        for br_name in br_names:
            ext_ids = self._get_bridge_external_ids_safe(br_name)
            if ext_ids.get(MANAGED_BY_KEY) == MANAGED_BY_VALUE:
                names.add(br_name)
        return names

    def _query_managed_bonds(self, managed_bridge_names, all_bridges):
        """Query managed bonds on all managed bridges."""
        result = {}
        for br_name in managed_bridge_names:
            if br_name not in all_bridges:
                continue
            ab = ActualBridge(br_name)
            self._query_bridge_ports(ab)
            if ab.bonds:
                result[br_name] = ab.bonds
        return result

    def _query_bridge_ports(self, ab):
        """Query all managed bond ports on a bridge."""
        port_names = self._list_ports_safe(ab.name)
        for port_name in port_names:
            port_ext_ids = self._get_external_ids_safe('port', port_name)
            if port_ext_ids.get(MANAGED_BY_KEY) != MANAGED_BY_VALUE:
                continue

            role = port_ext_ids.get(PORT_ROLE_KEY)
            if role == PORT_ROLE_BOND:
                self._query_bond(ab, port_name, port_ext_ids)

    def _query_bond(self, ab, port_name, port_ext_ids):
        """Query bond details for a port (or single-member uplink)."""
        bond = ActualBond(port_name)
        bond.external_ids = port_ext_ids

        err, bond_mode = self.vsctl.getTableAttr('port', port_name, 'bond_mode')
        if not err:
            bond.bond_mode = bond_mode

        err, lacp = self.vsctl.getTableAttr('port', port_name, 'lacp')
        if not err:
            bond.lacp = lacp

        ifaces = self._list_bond_members_safe(port_name)
        bond.members = ifaces

        for member in bond.members:
            err, val = self.vsctl.getTableAttr('interface', member, 'mtu_request')
            if not err and val and val != '[]':
                try:
                    bond.member_mtus[member] = int(val)
                except ValueError:
                    pass

        ab.bonds[port_name] = bond

    def query_full(self):
        """Query complete actual state for declarative reconciliation."""
        state = OvsActualState()
        state.all_bridges = self._query_all_bridges()
        state.managed_bridge_names = self._query_managed_bridge_names()
        state.managed_bonds = self._query_managed_bonds(state.managed_bridge_names, state.all_bridges)
        state.ip_addresses = self._query_ip_addresses(state.managed_bridge_names)
        state.ovs_external_ids = self._query_ovs_external_ids()
        return state

    def _query_all_bridges(self):
        """Query all OVS bridges and their datapath_type."""
        bridges = {}
        br_names = self.vsctl.listBridges()
        for br_name in br_names:
            err, dp_type = self.vsctl.getTableAttr('bridge', br_name, 'datapath_type')
            if err:
                dp_type = 'system'
            bridges[br_name] = {'datapath_type': dp_type if dp_type else 'system'}
        return bridges

    def _query_ip_addresses(self, managed_bridge_names):
        """Query IPv4 addresses on managed bridges."""
        ip_addresses = {}
        for br_name in managed_bridge_names:
            _validate_ovs_name(br_name)
            r, o, e = bash.bash_roe('ip -o -4 addr show dev %s' % br_name)
            if r != 0:
                continue
            addrs = []
            for line in o.strip().split('\n'):
                if not line.strip():
                    continue
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'inet' and i + 1 < len(parts):
                        addrs.append(parts[i + 1])
            if addrs:
                ip_addresses[br_name] = addrs
        return ip_addresses

    def _query_ovs_external_ids(self):
        """Query managed external_ids from Open_vSwitch table."""
        ext_ids = {}
        for key in MANAGED_OVS_EXTERNAL_ID_KEYS:
            err, val = self.vsctl.getOvsExternalIdsConfig(key)
            if not err and val is not None:
                ext_ids[key] = val
        return ext_ids


class DesiredStateBuilder(object):
    """Builds complete desired state from a provision command."""

    @staticmethod
    def build(cmd):
        state = OvsDesiredState()
        state.host_uuid = cmd.hostUuid
        state.config_version = cmd.configVersion
        state.sdn_controller_uuid = cmd.sdnControllerUuid
        raw_dpdk_config = getattr(cmd, 'dpdkConfig', None)
        state.dpdk_config = (OvsProvisionPlugin._normalize_dpdk_config(raw_dpdk_config)
                             if raw_dpdk_config else None)
        desired_switches = cmd.hostSwitches if cmd.hostSwitches else []

        bridge_mappings = []
        encap_ip = None

        for sw in desired_switches:
            br_name = OvsDesiredState._safe_bridge_name(sw.name)
            sw_type = getattr(sw, 'type_', None) or getattr(sw, 'type', None)
            dp_type = 'netdev' if sw_type == 'dpdk' else 'system'
            transport_zones = getattr(sw, 'transportZones', None) or []

            tep_ip = getattr(sw, 'tepIp', None)
            physical_network = None
            for tz in transport_zones:
                tz_type = getattr(tz, 'type_', None) or getattr(tz, 'type', None)
                if tz_type == 'vlan' and getattr(tz, 'physicalNetwork', None):
                    physical_network = tz.physicalNetwork

            # Bridge spec with bonds
            uplink_profile = getattr(sw, 'uplinkProfile', None)
            transport_vlan = 0
            overlay_vlan = 0
            if uplink_profile:
                transport_vlan = getattr(uplink_profile, 'transportVlan', 0) or 0
                overlay_vlan = getattr(uplink_profile, 'overlayVlan', 0) or 0

            br_spec = InfraBridgeSpec(br_name, dp_type, overlay_vlan)
            if uplink_profile and uplink_profile.lag:
                mtu = uplink_profile.mtu
                uplink_uuid = getattr(uplink_profile, 'uuid', '') or ''
                for lag in uplink_profile.lag:
                    members = lag.members if lag.members else []
                    mode = lag.mode if lag.mode else 'balance-slb'
                    bond_name = OvsDesiredState._safe_ifname(
                        '%s-%s' % (br_name, lag.name), 'bond')
                    br_spec.bonds[bond_name] = BondSpec(
                        bond_name, members, mode, mtu, sw_type, uplink_uuid,
                        transport_vlan)
            state.infra_bridges[br_name] = br_spec

            # TEP IP on this bridge
            if tep_ip:
                state.ip_addresses[br_name] = IpAddressSpec(br_name, tep_ip)
                if encap_ip is None:
                    encap_ip = tep_ip.split('/')[0] if '/' in tep_ip else tep_ip

            # Collect bridge-mappings
            if physical_network:
                bridge_mappings.append('%s:%s' % (physical_network, br_name))

        # OVS external_ids (global)
        # system-id = hostUuid
        if state.host_uuid:
            state.ovs_external_ids['system-id'] = state.host_uuid

        # sdn-controller-uuid = ZNS cluster UUID for ownership verification (ZCF-2786)
        state.ovs_external_ids[SDN_CONTROLLER_UUID_KEY] = state.sdn_controller_uuid

        # ovn-remote from controllerAddress
        controller_addrs = getattr(cmd, 'controllerAddress', None)
        if controller_addrs:
            remote_str = ','.join('tcp:%s:6642' % addr for addr in controller_addrs)
            state.ovs_external_ids['ovn-remote'] = remote_str

        # ovn-encap-type = geneve when overlay transport zone exists
        if encap_ip:
            state.ovs_external_ids['ovn-encap-type'] = 'geneve'

        if encap_ip:
            state.ovs_external_ids['ovn-encap-ip'] = encap_ip
        if bridge_mappings:
            state.ovs_external_ids['ovn-bridge-mappings'] = ','.join(bridge_mappings)

        # globalConfig -- tunnel MTU. BFD global parameters are applied by
        # zstack-zns through OVN NB_Global.options; legacy ovn-bfd-* external_ids
        # remain managed only so provision can clean up stale values.
        global_config = getattr(cmd, 'globalConfig', None)
        if global_config:
            tunnel_mtu = getattr(global_config, 'tunnelMtu', None)
            if tunnel_mtu is not None:
                state.tunnel_mtu = int(tunnel_mtu)

        return state


# --- OVS Command Builder ---

class OvsCommandBuilder(object):
    """Builds a single ovs-vsctl command with multiple operations joined by '--'."""

    def __init__(self):
        self._ops = []

    def add_br(self, name):
        _validate_ovs_name(name)
        self._ops.append('--may-exist add-br %s' % name)
        return self

    def set_bridge(self, name, key, value):
        _validate_ovs_name(name)
        _validate_ovs_key(key)
        self._ops.append('set bridge %s %s=%s' % (name, key, _quote_ovs_value(value)))
        return self

    def set_bridge_external_id(self, name, key, value):
        _validate_ovs_name(name)
        _validate_ovs_key(key)
        value = _validate_external_id_value(str(value))
        self._ops.append('br-set-external-id %s %s %s' % (name, key, value))
        return self

    def add_bond(self, bridge, name, members, bond_mode):
        _validate_ovs_name(bridge)
        _validate_ovs_name(name)
        for m in members:
            _validate_ovs_name(m)
        _validate_ovs_name(bond_mode)
        # balance-tcp mode requires LACP, auto-enable if not set
        lacp_opt = ''
        if bond_mode == 'balance-tcp':
            lacp_opt = ' lacp=active'
        if len(members) >= 2:
            self._ops.append('--may-exist add-bond %s %s %s bond_mode=%s%s' % (
                bridge, name, ' '.join(members), bond_mode, lacp_opt))
        else:
            # OVS add-bond requires 2+ interfaces; for single member,
            # create the interface and port via OVSDB ops directly
            self._ops.append('--id=@%s create Interface name=%s' % (
                members[0], members[0]))
            self._ops.append('--may-exist add-port %s %s' % (bridge, name))
            self._ops.append('set Port %s interfaces=@%s bond_mode=%s%s' % (
                name, members[0], bond_mode, lacp_opt))
        return self

    def set_port(self, name, key, value):
        _validate_ovs_name(name)
        _validate_ovs_key(key)
        self._ops.append('set port %s %s=%s' % (name, key, _quote_ovs_value(value)))
        return self

    def clear_port_attr(self, name, key):
        """Clear a column value from a port (e.g., clear VLAN tag)."""
        _validate_ovs_name(name)
        _validate_ovs_key(key)
        self._ops.append('clear port %s %s' % (name, key))
        return self

    def set_port_external_id(self, name, key, value):
        _validate_ovs_name(name)
        _validate_ovs_key(key)
        value = _validate_external_id_value(str(value))
        self._ops.append('set port %s external_ids:%s=%s' % (name, key, value))
        return self

    def set_interface(self, name, key, value):
        _validate_ovs_name(name)
        _validate_ovs_key(key)
        self._ops.append('set interface %s %s=%s' % (name, key, _quote_ovs_value(value)))
        return self

    def set_interface_external_id(self, name, key, value):
        _validate_ovs_name(name)
        _validate_ovs_key(key)
        value = _validate_external_id_value(str(value))
        self._ops.append('set interface %s external_ids:%s=%s' % (name, key, value))
        return self

    def add_port(self, bridge, name):
        _validate_ovs_name(bridge)
        _validate_ovs_name(name)
        self._ops.append('--may-exist add-port %s %s' % (bridge, name))
        return self

    def del_port(self, name, bridge=None):
        _validate_ovs_name(name)
        if bridge is not None:
            _validate_ovs_name(bridge)
            self._ops.append('--if-exists del-port %s %s' % (bridge, name))
        else:
            self._ops.append('--if-exists del-port %s' % name)
        return self

    def del_br(self, name):
        _validate_ovs_name(name)
        self._ops.append('--if-exists del-br %s' % name)
        return self

    def has_ops(self):
        return len(self._ops) > 0

    def build(self):
        if not self._ops:
            return None
        return 'ovs-vsctl ' + ' -- '.join(self._ops)


# --- OVS Reconciler ---

class OvsReconciler(object):
    """Reconciles desired state against actual state in dependency order."""

    def reconcile(self, desired, actual):
        """Execute all reconciliation phases in order."""
        ovsdb_system_id_changed = self._ovsdb_system_id_changed(desired, actual)
        self._reconcile_managed_bridges_delete(desired, actual)
        recreated = self._reconcile_infra_bridges_create(desired, actual)
        for br_name in recreated:
            actual.managed_bonds.pop(br_name, None)
        self._reconcile_bonds(desired, actual)
        self._reconcile_vlan_tags(desired)
        self._reconcile_ip_addresses(desired, actual)
        self._reconcile_ovs_system_id_conf(desired)
        self._reconcile_ovs_external_ids(desired, actual)
        if ovsdb_system_id_changed:
            self._restart_ovn_controller_after_system_id_change(desired, actual)
        self._reconcile_tunnel_mtu(desired)

    @staticmethod
    def _ovsdb_system_id_changed(desired, actual):
        desired_system_id = desired.ovs_external_ids.get('system-id')
        if not desired_system_id:
            return False
        return actual.ovs_external_ids.get('system-id') != desired_system_id

    @staticmethod
    def _reconcile_ovs_system_id_conf(desired):
        desired_system_id = desired.ovs_external_ids.get('system-id')
        if not desired_system_id:
            return

        _validate_external_id_value(desired_system_id)
        current_system_id = None
        if os.path.exists(OVS_SYSTEM_ID_CONF_PATH):
            with open(OVS_SYSTEM_ID_CONF_PATH, 'r') as f:
                current_system_id = f.read().strip()

        if current_system_id == desired_system_id:
            return

        conf_dir = os.path.dirname(OVS_SYSTEM_ID_CONF_PATH)
        if not os.path.isdir(conf_dir):
            os.makedirs(conf_dir)

        tmp_path = OVS_SYSTEM_ID_CONF_PATH + '.tmp'
        with open(tmp_path, 'w') as f:
            f.write(desired_system_id + '\n')
        os.rename(tmp_path, OVS_SYSTEM_ID_CONF_PATH)
        logger.info('updated %s with OVS system-id %s'
                    % (OVS_SYSTEM_ID_CONF_PATH, desired_system_id))

    @staticmethod
    def _restart_ovn_controller_after_system_id_change(desired, actual):
        old_system_id = actual.ovs_external_ids.get('system-id')
        ovn_remote = desired.ovs_external_ids.get('ovn-remote')

        r, o, e = bash.bash_roe('systemctl stop ovn-controller')
        if r != 0:
            raise Exception('failed to stop ovn-controller after OVS system-id change: %s' % e)

        OvsReconciler._delete_stale_ovn_chassis(old_system_id, ovn_remote)

        r, o, e = bash.bash_roe('systemctl start ovn-controller')
        if r != 0:
            raise Exception('failed to start ovn-controller after OVS system-id change: %s' % e)
        logger.info('restarted ovn-controller after OVS system-id change')

    @staticmethod
    def _delete_stale_ovn_chassis(old_system_id, ovn_remote):
        if not old_system_id or not ovn_remote:
            return

        _validate_external_id_value(old_system_id)
        _validate_external_id_value(ovn_remote)
        cmd = 'ovn-sbctl --timeout=5 --db=%s chassis-del %s' % (
            _quote_ovs_value(ovn_remote), _quote_ovs_value(old_system_id))
        r, o, e = bash.bash_roe(cmd)
        if r != 0:
            logger.warn('failed to delete stale OVN chassis %s: %s' % (old_system_id, e))
            return
        logger.info('deleted stale OVN chassis %s after OVS system-id change' % old_system_id)

    @staticmethod
    def _reconcile_managed_bridges_delete(desired, actual):
        """Delete managed bridges no longer in desired state."""
        for br_name in list(actual.managed_bridge_names):
            if br_name not in desired.infra_bridges:
                _validate_ovs_name(br_name)
                OvsProvisioner._run_ovs_cmd('ovs-vsctl --if-exists del-br %s' % br_name)
                logger.info('deleted managed bridge %s (no longer desired)' % br_name)

    @staticmethod
    def _reconcile_infra_bridges_create(desired, actual):
        """Create or update infrastructure bridges.

        Returns set of bridge names that were (re)created.
        """
        recreated = set()
        for br_name, spec in desired.infra_bridges.items():
            _validate_ovs_name(br_name)
            actual_br = actual.all_bridges.get(br_name)
            if actual_br:
                actual_dp = actual_br['datapath_type']
                if actual_dp != spec.datapath_type:
                    logger.info('%s datapath_type changed %s -> %s, recreating'
                                % (br_name, actual_dp, spec.datapath_type))
                    OvsProvisioner._run_ovs_cmd('ovs-vsctl --if-exists del-br %s' % br_name)
                else:
                    logger.debug('%s already exists with correct datapath_type=%s'
                                 % (br_name, spec.datapath_type))
                    builder = OvsCommandBuilder()
                    builder.set_bridge_external_id(br_name, MANAGED_BY_KEY, MANAGED_BY_VALUE)
                    builder.set_bridge_external_id(br_name, CONFIG_VERSION_KEY,
                                                   str(desired.config_version))
                    builder.set_bridge_external_id(br_name, HOST_UUID_KEY, desired.host_uuid)
                    builder.set_bridge_external_id(br_name, SDN_CONTROLLER_UUID_KEY,
                                                   desired.sdn_controller_uuid)
                    OvsProvisioner._run_ovs_cmd(builder.build())
                    continue

            builder = OvsCommandBuilder()
            builder.add_br(br_name)
            builder.set_bridge(br_name, 'datapath_type', spec.datapath_type)
            builder.set_bridge_external_id(br_name, MANAGED_BY_KEY, MANAGED_BY_VALUE)
            builder.set_bridge_external_id(br_name, CONFIG_VERSION_KEY,
                                           str(desired.config_version))
            builder.set_bridge_external_id(br_name, HOST_UUID_KEY, desired.host_uuid)
            builder.set_bridge_external_id(br_name, SDN_CONTROLLER_UUID_KEY,
                                           desired.sdn_controller_uuid)
            OvsProvisioner._run_ovs_cmd(builder.build())
            recreated.add(br_name)
            logger.info('ensured infra bridge %s with datapath_type=%s'
                         % (br_name, spec.datapath_type))
        return recreated

    @staticmethod
    def _effective_mtu(uplink_mtu, tunnel_mtu):
        """Return the larger of uplink MTU and tunnel MTU.

        The uplink interface carries both VLAN traffic (sized by uplink_mtu)
        and geneve-encapsulated tunnel traffic (sized by tunnel_mtu).
        To avoid drops, the physical interface must accommodate whichever is larger.
        """
        values = [v for v in (uplink_mtu, tunnel_mtu) if v is not None]
        return max(values) if values else None

    @staticmethod
    def _reconcile_bonds(desired, actual):
        """Reconcile bonds on all managed bridges."""
        nic_pci_map = (getattr(desired.dpdk_config, 'nicNamePciAddressMap', None)
                       if desired.dpdk_config else None)

        for br_name, spec in desired.infra_bridges.items():
            desired_bonds = spec.bonds
            actual_bonds = actual.managed_bonds.get(br_name, {})
            managed_port_names = OvsReconciler._get_managed_port_names_on_bridge(br_name)

            builder = OvsCommandBuilder()
            rebuilt_bonds = set()

            # Delete surplus bonds
            for bond_name in actual_bonds:
                if bond_name not in desired_bonds:
                    builder.del_port(bond_name, br_name)
                    managed_port_names.discard(bond_name)

            # Add / update bonds
            for bond_name, bond_spec in desired_bonds.items():
                if bond_name not in actual_bonds:
                    OvsReconciler._build_add_bond(builder, br_name, bond_spec,
                                                  desired.config_version, nic_pci_map,
                                                  managed_port_names,
                                                  desired.tunnel_mtu)
                    rebuilt_bonds.add(bond_name)
                else:
                    actual_bond = actual_bonds[bond_name]
                    if sorted(bond_spec.members) != sorted(actual_bond.members):
                        builder.del_port(bond_name, br_name)
                        managed_port_names.discard(bond_name)
                        OvsReconciler._build_add_bond(builder, br_name, bond_spec,
                                                      desired.config_version, nic_pci_map,
                                                      managed_port_names,
                                                      desired.tunnel_mtu)
                        rebuilt_bonds.add(bond_name)
                    else:
                        if bond_spec.mode and bond_spec.mode != (actual_bond.bond_mode or ''):
                            builder.set_port(bond_name, 'bond_mode', bond_spec.mode)

                        # Reconcile LACP independently of bond_mode change
                        if bond_spec.mode:
                            expected_lacp = 'active' if bond_spec.mode == 'balance-tcp' else 'off'
                            # Normalize OVS unset values (None, '', '[]') to 'off'
                            actual_lacp = actual_bond.lacp if actual_bond.lacp and actual_bond.lacp != '[]' else 'off'
                            if actual_lacp != expected_lacp:
                                builder.set_port(bond_name, 'lacp', expected_lacp)

            # MTU comparison (skip rebuilt bonds)
            for bond_name, bond_spec in desired_bonds.items():
                if bond_name in rebuilt_bonds or bond_name not in actual_bonds:
                    continue
                effective = OvsReconciler._effective_mtu(bond_spec.mtu, desired.tunnel_mtu)
                if effective is None:
                    continue
                for member in actual_bonds[bond_name].members:
                    if actual_bonds[bond_name].member_mtus.get(member) != effective:
                        builder.set_interface(member, 'mtu_request', str(effective))

            # Refresh config-version on bonds not rebuilt
            for bond_name, _ in desired_bonds.items():
                if bond_name in rebuilt_bonds:
                    continue
                if bond_name in actual_bonds:
                    builder.set_port_external_id(bond_name, CONFIG_VERSION_KEY,
                                                 str(desired.config_version))
                    actual_bond = actual_bonds[bond_name]
                    for member in actual_bond.members:
                        builder.set_interface_external_id(member, CONFIG_VERSION_KEY,
                                                          str(desired.config_version))

            if builder.has_ops():
                OvsProvisioner._run_ovs_cmd(builder.build())

    @staticmethod
    def _build_add_bond(builder, bridge_name, spec, config_version,
                        nic_pci_map=None, managed_port_names=None,
                        tunnel_mtu=None):
        """Add bond creation ops to the command builder."""
        members = spec.members if spec.members else []
        if not members:
            return

        managed_port_names = managed_port_names if managed_port_names is not None else set()

        # Only clean up ports managed by zstack-agent on the current bridge.
        if spec.name in managed_port_names:
            builder.del_port(spec.name, bridge_name)
            managed_port_names.discard(spec.name)

        for member in members:
            if member in managed_port_names:
                builder.del_port(member, bridge_name)
                managed_port_names.discard(member)

        mode = spec.mode if spec.mode else 'balance-slb'
        builder.add_bond(bridge_name, spec.name, members, mode)

        # DPDK: set interface type=dpdk and options:dpdk-devargs=PCI
        if spec.switch_type == 'dpdk' and nic_pci_map:
            for member in members:
                pci_addr = getattr(nic_pci_map, member, None)
                if pci_addr:
                    if not _PCI_ADDR_RE.match(pci_addr):
                        raise ValueError('invalid PCI address for %s: %r' % (member, pci_addr))
                    builder.set_interface(member, 'type', 'dpdk')
                    builder.set_interface(member, 'options:dpdk-devargs', pci_addr)

        # Port external_ids
        builder.set_port_external_id(spec.name, MANAGED_BY_KEY, MANAGED_BY_VALUE)
        builder.set_port_external_id(spec.name, CONFIG_VERSION_KEY, str(config_version))
        builder.set_port_external_id(spec.name, PORT_ROLE_KEY, PORT_ROLE_BOND)
        if spec.uplink_uuid:
            builder.set_port_external_id(spec.name, UPLINK_PROFILE_UUID_KEY, spec.uplink_uuid)

        # Interface external_ids and MTU
        effective = OvsReconciler._effective_mtu(spec.mtu, tunnel_mtu)
        for member in members:
            if effective is not None:
                builder.set_interface(member, 'mtu_request', str(effective))
            builder.set_interface_external_id(member, MANAGED_BY_KEY, MANAGED_BY_VALUE)
            builder.set_interface_external_id(member, CONFIG_VERSION_KEY, str(config_version))

    @staticmethod
    def _get_managed_port_names_on_bridge(bridge_name):
        """Return managed port names present on the specified bridge."""
        managed_port_names = set()
        vsctl = ovn.VsCtl()
        for port_name in vsctl.listPorts(bridge_name):
            port_ext_ids = vsctl.getExternalIds('port', port_name)
            if port_ext_ids.get(MANAGED_BY_KEY) == MANAGED_BY_VALUE:
                managed_port_names.add(port_name)
        return managed_port_names

    @staticmethod
    def _reconcile_vlan_tags(desired):
        """Set or clear VLAN tags on bridge internal ports and bond ports.

        - overlay_vlan on bridge internal port (port name == bridge name)
        - transport_vlan on bond ports (uplink ports)
        VLAN > 0 means set tag; VLAN == 0 means clear tag.
        """
        for br_name, br_spec in desired.infra_bridges.items():
            _validate_ovs_name(br_name)
            # Overlay VLAN on bridge internal port
            if br_spec.overlay_vlan and br_spec.overlay_vlan > 0:
                r, o, e = bash.bash_roe(
                    'ovs-vsctl set port %s tag=%s' % (br_name, br_spec.overlay_vlan))
                if r != 0:
                    raise Exception('failed to set overlay VLAN tag=%s on port %s: %s'
                                    % (br_spec.overlay_vlan, br_name, e))
                logger.info('set overlay VLAN tag=%s on bridge internal port %s'
                            % (br_spec.overlay_vlan, br_name))
            else:
                r, o, e = bash.bash_roe(
                    'ovs-vsctl clear port %s tag' % br_name)
                if r != 0:
                    logger.debug('clear overlay VLAN tag on port %s (may not have tag): %s'
                                 % (br_name, e))
                else:
                    logger.info('cleared overlay VLAN tag on bridge internal port %s' % br_name)

            # Transport VLAN on bond ports
            for bond_name, bond_spec in br_spec.bonds.items():
                _validate_ovs_name(bond_name)
                if bond_spec.transport_vlan and bond_spec.transport_vlan > 0:
                    r, _o, e = bash.bash_roe(
                        'ovs-vsctl set port %s tag=%s' % (bond_name, bond_spec.transport_vlan))
                    if r != 0:
                        raise Exception('failed to set transport VLAN tag=%s on port %s: %s'
                                        % (bond_spec.transport_vlan, bond_name, e))
                    logger.info('set transport VLAN tag=%s on bond port %s'
                                % (bond_spec.transport_vlan, bond_name))
                else:
                    r, _o, e = bash.bash_roe(
                        'ovs-vsctl clear port %s tag' % bond_name)
                    if r != 0:
                        logger.debug('clear transport VLAN tag on port %s (may not have tag): %s'
                                     % (bond_name, e))
                    else:
                        logger.info('cleared transport VLAN tag on bond port %s' % bond_name)

    @staticmethod
    def _reconcile_ip_addresses(desired, actual):
        """Assign IP addresses on infrastructure bridges when needed."""
        for device, spec in desired.ip_addresses.items():
            _validate_ovs_name(device)
            _validate_ip_address(spec.address)
            current_addresses = actual.ip_addresses.get(device, [])
            if spec.address in current_addresses:
                logger.debug('IP %s already exists on %s, skip reconcile'
                             % (spec.address, device))
                continue

            r, o, e = bash.bash_roe('ip addr flush dev %s' % device)
            if r != 0:
                raise Exception('failed to flush IP addresses on %s: %s'
                                % (device, e))
            r, o, e = bash.bash_roe('ip addr add %s dev %s' % (spec.address, device))
            if r != 0:
                raise Exception('failed to assign IP %s to %s: %s'
                                % (spec.address, device, e))
            r, o, e = bash.bash_roe('ip link set %s up' % device)
            if r != 0:
                raise Exception('failed to bring up %s: %s' % (device, e))
            logger.info('assigned IP %s to %s' % (spec.address, device))

    @staticmethod
    def _reconcile_ovs_external_ids(desired, actual):
        """Phase 7: Set desired and remove unmanaged external_ids."""
        updates = {}
        for key, desired_val in desired.ovs_external_ids.items():
            actual_val = actual.ovs_external_ids.get(key)
            if actual_val != desired_val:
                updates[key] = desired_val

        if updates:
            parts = ['external_ids:%s=%s' % (k, _validate_external_id_value(v))
                     for k, v in updates.items()]
            cmd_str = 'ovs-vsctl set Open_vSwitch . ' + ' '.join(parts)
            r, o, e = bash.bash_roe(cmd_str)
            if r != 0:
                raise Exception('failed to set OVS external_ids: %s' % e)
            logger.info('updated OVS external_ids: %s' % list(updates.keys()))

        for key in MANAGED_OVS_EXTERNAL_ID_KEYS:
            if key not in desired.ovs_external_ids and key in actual.ovs_external_ids:
                r, o, e = bash.bash_roe('ovs-vsctl remove Open_vSwitch . external_ids %s' % key)
                if r != 0:
                    raise Exception('failed to remove OVS external_id %s: %s' % (key, e))
                logger.info('removed OVS external_id %s (no longer desired)' % key)

    @staticmethod
    def _reconcile_tunnel_mtu(desired):
        """Phase 8: Apply tunnel MTU to geneve interfaces and bridge internal ports.

        During provision, geneve interfaces may not exist yet (created async
        by ovn-controller), so we also set MTU on overlay bridge internal ports
        directly using desired.ip_addresses (bridges with TEP IPs).
        """
        if desired.tunnel_mtu is None:
            return
        # Apply to any geneve interfaces that already exist
        _apply_tunnel_mtu(desired.tunnel_mtu)
        # Also set MTU on overlay bridge internal ports (bridges with TEP IP),
        # regardless of whether geneve interfaces exist yet
        for br_name in desired.ip_addresses:
            r, _, e = bash.bash_roe(
                'ovs-vsctl set interface %s mtu_request=%s' % (br_name, desired.tunnel_mtu))
            if r != 0:
                logger.warn('failed to set mtu_request=%s on bridge internal port %s: %s'
                            % (desired.tunnel_mtu, br_name, e))
            else:
                logger.info('set mtu_request=%s on overlay bridge internal port %s'
                            % (desired.tunnel_mtu, br_name))


# --- OVS Provisioner ---

class OvsProvisioner(object):

    def __init__(self):
        self.querier = OvsStateQuerier()
        self.reconciler = OvsReconciler()

    def apply(self, cmd):
        """
        Main entry point. Builds desired state, queries actual state,
        and reconciles the difference.

        Returns a ProvisionResponse.
        """
        desired = DesiredStateBuilder.build(cmd)
        actual = self.querier.query_full()
        logger.debug('queried actual state: %d all bridges, %d managed, %d bridges with bonds'
                     % (len(actual.all_bridges), len(actual.managed_bridge_names),
                        len(actual.managed_bonds)))
        self.reconciler.reconcile(desired, actual)
        return self._build_response(cmd)

    @staticmethod
    def _build_response(cmd):
        """Build provision response with switch status."""
        rsp = ProvisionResponse()
        rsp.hostUuid = cmd.hostUuid
        rsp.cloudCallbackUrl = getattr(cmd, 'cloudCallbackUrl', None)
        rsp.cloudTaskUuid = getattr(cmd, 'cloudTaskUuid', None)
        rsp.triggerUrl = getattr(cmd, 'triggerUrl', None)
        desired_switches = cmd.hostSwitches if cmd.hostSwitches else []

        for sw in desired_switches:
            switch_result = {'name': sw.name, 'status': 'realized'}
            tep_ip = getattr(sw, 'tepIp', None)
            if tep_ip:
                switch_result['tepIp'] = tep_ip
            rsp.hostSwitches.append(switch_result)
        return rsp

    @staticmethod
    def _run_ovs_cmd(cmd_str):
        """Execute an ovs-vsctl command and raise on failure."""
        if not cmd_str:
            return
        logger.debug('executing: %s' % cmd_str)
        r, o, e = bash.bash_roe(cmd_str)
        if r != 0:
            raise Exception('ovs-vsctl command failed (exit %d): %s\ncmd: %s' % (r, e, cmd_str))


def _verify_nics_not_in_use(desired_switches, managed_bridge_names=None):
    """Pre-check: verify NICs are not in use before provisioning.

    This check applies to both DPDK and Kernel modes.
    Using an in-use NIC for OVS bridge will cause network disruption.
    Raises Exception if any NIC fails the checks.

    Args:
        desired_switches: list of desired switch specs.
        managed_bridge_names: optional set of bridge names managed by this
            plugin.  NICs already attached to one of these bridges are
            considered "ours" and skipped so that re-provision is not blocked.
    """
    if managed_bridge_names is None:
        managed_bridge_names = set()

    nic_members = set()
    for sw in desired_switches:
        uplink_profile = getattr(sw, 'uplinkProfile', None)
        if not uplink_profile or not uplink_profile.lag:
            continue
        for lag in uplink_profile.lag:
            if lag.members:
                nic_members.update(lag.members)

    for nic_name in nic_members:
        try:
            _validate_ovs_name(nic_name)
        except ValueError:
            raise Exception(
                'cannot use NIC for provisioning: '
                'invalid NIC name %r' % nic_name)

        # Check 1: IP address configured
        r, o, e = bash.bash_roe(
            "ip -o addr show dev %s 2>/dev/null | grep -v 'inet6.*scope link' | head -1"
            % nic_name)
        if r == 0 and o.strip():
            raise Exception(
                'cannot use NIC for provisioning: '
                'nic %s has IP address configured and is in use. '
                'Please remove the IP first: "ip addr flush dev %s"'
                % (nic_name, nic_name))

        # Check 2: Already attached to an OVS bridge (including bond members)
        r2, o2, _e2 = bash.bash_roe(
            "ovs-vsctl iface-to-br %s 2>/dev/null" % nic_name)
        if r2 == 0 and o2.strip():
            br_name = o2.strip()
            if br_name not in managed_bridge_names:
                raise Exception(
                    'cannot use NIC for provisioning: '
                    'nic %s is already attached to OVS bridge %s. '
                    'Please remove it from the bridge first.'
                    % (nic_name, br_name))

        # Check 3: Bond slave
        r, o, e = bash.bash_roe(
            "ip -o link show dev %s 2>/dev/null | grep -o 'master [^ ]*' | head -1"
            % nic_name)
        if r == 0 and o.strip():
            master = o.strip().split()[-1] if o.strip().split() else ''
            if master and master != 'ovs-system':
                raise Exception(
                    'cannot use NIC for provisioning: '
                    'nic %s is a slave of bond/master %s. '
                    'Please remove it from the bond first.'
                    % (nic_name, master))

        # Check 4: Has routes (non-link-local)
        r, o, e = bash.bash_roe(
            "ip route show dev %s 2>/dev/null"
            % nic_name)
        if r == 0 and _has_active_ipv4_route(o):
            raise Exception(
                'cannot use NIC for provisioning: '
                'nic %s has active routes and is in use. '
                'Please remove routes first: "ip route flush dev %s"'
                % (nic_name, nic_name))

        # Check 5: NetworkManager managed (may auto-configure)
        r, o, e = bash.bash_roe(
            "nmcli -t -f DEVICE,STATE device status 2>/dev/null | grep '^%s:' | head -1"
            % nic_name)
        if r == 0 and o.strip():
            state = o.strip().split(':')[-1] if ':' in o.strip() else ''
            if state and state not in ('unmanaged', 'unavailable'):
                raise Exception(
                    'cannot use NIC for provisioning: '
                    'nic %s is managed by NetworkManager (state: %s). '
                    'Please set it unmanaged first: "nmcli device set %s managed no"'
                    % (nic_name, state, nic_name))

        # Check 6: Has VLAN sub-interfaces
        r, o, e = bash.bash_roe(
            "ip -o link show 2>/dev/null | grep -E '%s\\.[0-9]+@%s' | head -1"
            % (nic_name, nic_name))
        if r == 0 and o.strip():
            vlan_if = o.strip().split(':')[1].split('@')[0].strip() if ':' in o.strip() else ''
            if vlan_if:
                raise Exception(
                    'cannot use NIC for provisioning: '
                    'nic %s has VLAN sub-interface %s configured. '
                    'Please delete VLAN interfaces first: "ip link delete %s"'
                    % (nic_name, vlan_if, vlan_if))

        # Check 7: Has tc qdisc rules (traffic control)
        r, o, _e = bash.bash_roe(
            "tc qdisc show dev %s 2>/dev/null | grep -v 'qdisc noop\\|qdisc pfifo_fast\\|qdisc mq\\|qdisc fq_codel' | head -1"
            % nic_name)
        if r == 0 and o.strip():
            raise Exception(
                'cannot use NIC for provisioning: '
                'nic %s has tc qdisc rules configured. '
                'Please clear tc rules first: "tc qdisc del dev %s root"'
                % (nic_name, nic_name))


# --- Plugin Entry ---

class OvsProvisionPlugin(kvmagent.KvmAgent):

    def start(self):
        logger.info('OvsProvisionPlugin starting')
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(OVS_PROVISION_PATH, self.provision)
        http_server.register_async_uri(OVS_DEPROVISION_PATH, self.deprovision)
        logger.info('OvsProvisionPlugin started, registered %s and %s'
                     % (OVS_PROVISION_PATH, OVS_DEPROVISION_PATH))

    def stop(self):
        logger.info('OvsProvisionPlugin stopped')

    @staticmethod
    def _unwrap_spec(cmd):
        spec = getattr(cmd, 'spec', None)
        if spec is None:
            return

        for key in ('hostUuid', 'configVersion', 'sdnControllerUuid',
                    'hostSwitches', 'globalConfig', 'controllerAddress',
                    'dpdkConfig', 'restoreNicPciAddressList', 'force',
                    'cloudCallbackUrl', 'cloudTaskUuid', 'triggerUrl'):
            val = getattr(spec, key, None)
            if val is not None:
                setattr(cmd, key, val)

    @staticmethod
    def _check_deprovision_ownership(sdn_controller_uuid):
        try:
            err, existing_controller = ovn.VsCtl().getOvsExternalIdsConfig(
                SDN_CONTROLLER_UUID_KEY)
        except Exception as e:
            raise Exception('SdnController ownership check failed: %s' % e)

        if err:
            raise Exception('SdnController ownership check failed: unable to read %s'
                            % SDN_CONTROLLER_UUID_KEY)
        if existing_controller and existing_controller != sdn_controller_uuid:
            raise Exception(
                'host already managed by another SdnController: %s, '
                'current request from: %s'
                % (existing_controller, sdn_controller_uuid))

    @staticmethod
    def _fallback_dpdk_switches_to_system(cmd, desired_switches):
        cmd.dpdkConfig = None
        for sw in desired_switches:
            sw_type = getattr(sw, 'type_', None) or getattr(sw, 'type', None)
            if sw_type == 'dpdk':
                if hasattr(sw, 'type_'):
                    sw.type_ = 'system'
                if hasattr(sw, 'type'):
                    sw.type = 'system'

    @staticmethod
    def _stop_openvswitch_before_nic_restore():
        r, _o, e = bash.bash_roe('systemctl stop openvswitch')
        if r != 0:
            raise Exception('failed to stop openvswitch before restoring NIC drivers: %s' % e)

    @staticmethod
    def _normalize_dpdk_config(raw):
        """Normalize per-switch dpdkConfig from management plane format to agent internal format.

        Management plane sends fields like lcores(list), pmdCores(list), nrHugepages,
        pageSize(KB), nicNamePciPairs, etc.  Agent internal format uses lcores(str),
        pmdcores(str), hugePageNumber, hugePageSize(MB), nicNamePciAddressMap, etc.
        """
        cfg = DefaultDpdkConfig()

        # lcores: list["0","1","2"] -> "0,1,2"; or already a string
        val = getattr(raw, 'lcores', None)
        if val is not None:
            if isinstance(val, list):
                cfg.lcores = ','.join(str(v) for v in val)
            else:
                cfg.lcores = str(val)

        # pmdCores -> pmdcores: list["3","4"] -> "3,4"
        val = getattr(raw, 'pmdCores', None)
        if val is None:
            val = getattr(raw, 'pmdcores', None)
        if val is not None:
            if isinstance(val, list):
                cfg.pmdcores = ','.join(str(v) for v in val)
            else:
                cfg.pmdcores = str(val)

        # nrHugepages -> hugePageNumber
        val = getattr(raw, 'nrHugepages', None)
        if val is None:
            val = getattr(raw, 'hugePageNumber', None)
        if val is not None:
            cfg.hugePageNumber = int(val)

        # pageSize(KB) -> hugePageSize(MB): values > 1024 are KB, <= 1024 are MB
        val = getattr(raw, 'pageSize', None)
        if val is None:
            val = getattr(raw, 'hugePageSize', None)
        if val is not None:
            val = int(val)
            if val > 1024:
                val = val // 1024
            cfg.hugePageSize = val

        # socketMem: pass-through
        val = getattr(raw, 'socketMem', None)
        if val is not None:
            cfg.socketMem = int(val)

        # nicNamePciPairs -> nicNamePciAddressMap
        val = getattr(raw, 'nicNamePciPairs', None)
        if val is None:
            val = getattr(raw, 'nicNamePciAddressMap', None)
        if val is not None:
            cfg.nicNamePciAddressMap = val

        # nicRxQueueNum -> nicRxQueueNumber
        val = getattr(raw, 'nicRxQueueNum', None)
        if val is None:
            val = getattr(raw, 'nicRxQueueNumber', None)
        if val is not None:
            cfg.nicRxQueueNumber = int(val)

        # nicRxQueueDescNum -> nicRxQueueDescNumber
        val = getattr(raw, 'nicRxQueueDescNum', None)
        if val is None:
            val = getattr(raw, 'nicRxQueueDescNumber', None)
        if val is not None:
            cfg.nicRxQueueDescNumber = int(val)

        return cfg

    @staticmethod
    def _build_nic_pci_map_from_uplink(desired_switches):
        """Build nicNamePciAddressMap from uplinkProfile by querying system NICs.

        For each lag member, first tries sysfs via ovs_utils.getBDFOfInterface()
        (works for kernel-visible NICs), then falls back to ovn.getAllDpdkNic()
        (works for NICs already bound to DPDK driver).

        Returns a simple object with nic_name attributes mapped to PCI addresses,
        or None if no PCI addresses can be determined.
        """
        nic_pci = {}
        dpdk_nics = None  # lazy-loaded

        for sw in desired_switches:
            uplink_profile = getattr(sw, 'uplinkProfile', None)
            if not uplink_profile or not uplink_profile.lag:
                continue
            for lag in uplink_profile.lag:
                if not lag.members:
                    continue
                for member in lag.members:
                    # Try sysfs first (kernel-visible NIC)
                    try:
                        bdf = ovs_utils.getBDFOfInterface(member)
                        if bdf:
                            nic_pci[member] = bdf
                            continue
                    except Exception as ex:
                        logger.debug('getBDFOfInterface(%s) failed, will try DPDK fallback: %s'
                                     % (member, ex))

                    # Fallback: query DPDK-bound NICs
                    if dpdk_nics is None:
                        dpdk_nics = ovn.getAllDpdkNic()
                    for nic in dpdk_nics:
                        if nic.name == member:
                            nic_pci[member] = nic.pciAddress
                            break

        if not nic_pci:
            return None

        class NicPciMap(object):
            pass
        result = NicPciMap()
        for k, v in nic_pci.items():
            setattr(result, k, v)
        return result

    @staticmethod
    def _ensure_hugepages(nr_hugepages, page_size_mb):
        """Allocate hugepages if the system does not have enough free ones.

        ovn.py relies on GRUB for persistent hugepage configuration.  When GRUB
        is not configured we fall back to runtime allocation via sysfs so that
        OVS-DPDK EAL initialization can succeed.
        """
        page_size_kb = int(page_size_mb) * 1024
        hugepages_dir = '/sys/kernel/mm/hugepages/hugepages-%dkB' % page_size_kb

        if not os.path.exists(hugepages_dir):
            logger.warn('hugepages path %s not found' % hugepages_dir)
            return

        nr_path = os.path.join(hugepages_dir, 'nr_hugepages')
        free_path = os.path.join(hugepages_dir, 'free_hugepages')

        try:
            with open(nr_path, 'r') as f:
                current_nr = int(f.read().strip())
            with open(free_path, 'r') as f:
                free_nr = int(f.read().strip())
        except Exception as e:
            logger.warn('failed to read hugepages status: %s' % e)
            return

        if free_nr >= int(nr_hugepages):
            logger.debug('hugepages sufficient: free=%d required=%d' % (free_nr, nr_hugepages))
            return

        deficit = int(nr_hugepages) - free_nr
        target = current_nr + deficit
        logger.info('allocating hugepages: target=%d (current=%d free=%d required=%d)'
                     % (target, current_nr, free_nr, nr_hugepages))
        try:
            with open(nr_path, 'w') as f:
                f.write(str(target))
            logger.info('hugepages allocated: %d' % target)
        except Exception as e:
            raise Exception('failed to allocate hugepages via %s: %s. '
                            'Configure hugepages in GRUB: '
                            'hugepagesz=%dM hugepages=%d' % (
                                nr_path, e, page_size_mb, nr_hugepages))

    @staticmethod
    def _clear_dpdk_other_config(vsctl):
        """Remove all DPDK-related other_config keys from Open_vSwitch table.

        Called during deprovision and kernel-mode provision to ensure
        dpdk_initialized does not linger as true after a DPDK-to-kernel switch.
        """
        for key in DPDK_OTHER_CONFIG_KEYS:
            err, val = vsctl.getOvsOtherConfig(key)
            if not err and val is not None:
                r, _o, e = bash.bash_roe(
                    'ovs-vsctl --no-wait remove Open_vSwitch . other_config %s' % key)
                if r != 0:
                    logger.warn('failed to remove DPDK other_config %s: %s' % (key, e))
                else:
                    logger.info('removed DPDK other_config %s=%s' % (key, val))

    @staticmethod
    def _ensure_dpdk_init(vsctl, dpdk_config):
        """Initialize OVS DPDK mode.

        Follows ovn.py start_ovn_service order (line 261-307):
          1. Ensure hugepages are allocated
          2. checkHugePagesMem / dpdk-socket-mem
          3. dpdk-init=true
          4. CPU cores (dpdk-lcore-mask, pmd-cpu-mask)
          5. ovn-monitor-all, ovn-remote-probe-interval
        """
        # 1. Ensure hugepages (ovn.py relies on GRUB; we allocate at runtime)
        OvsProvisionPlugin._ensure_hugepages(
            dpdk_config.hugePageNumber, dpdk_config.hugePageSize)

        # 2. HugePages / dpdk-socket-mem (ovn.py line 261-266)
        if getattr(dpdk_config, 'socketMem', None):
            err, cur_mem = vsctl.getOvsOtherConfig("dpdk-socket-mem")
            if err or (cur_mem and len(cur_mem.split(',')) > 0
                       and cur_mem.split(',')[0] != str(dpdk_config.socketMem)):
                dpdk_env = ovn.OvsDpdkEnv(
                    getattr(dpdk_config, 'lcores', None),
                    getattr(dpdk_config, 'pmdcores', None),
                    int(dpdk_config.hugePageNumber),
                    int(dpdk_config.hugePageSize),
                    int(dpdk_config.socketMem),
                    getattr(dpdk_config, 'nicNamePciAddressMap', None),
                    getattr(dpdk_config, 'nicRxQueueNumber', None),
                    getattr(dpdk_config, 'nicRxQueueDescNumber', None))
                r = dpdk_env.checkHugePagesMem()
                if r != 0:
                    raise Exception('check OVS DPDK huge page mem error')

        # 3. dpdk-init=true (ovn.py line 268-273)
        # IMPORTANT: if dpdk-init changes from false/none to true, OVS must be
        # restarted for DPDK EAL initialization to take effect. Otherwise bridges
        # will be created with datapath_type=system instead of netdev.
        err, val = vsctl.getOvsOtherConfig("dpdk-init")
        dpdk_init_changed = (err or val != 'true')
        if dpdk_init_changed:
            r = vsctl.setOvsOtherConfig("dpdk-init", 'true')
            if r != 0:
                raise Exception('failed to set dpdk-init')
            logger.info('set dpdk-init=true')

            # Restart openvswitch to initialize DPDK EAL if it was already running.
            # This is critical when OVS was running before dpdk-init was set.
            r, o, e = bash.bash_roe('systemctl is-active openvswitch')
            if r == 0:
                logger.info('dpdk-init changed, restarting openvswitch for DPDK EAL init')
                r, o, e = bash.bash_roe('systemctl restart openvswitch')
                if r != 0:
                    raise Exception('failed to restart openvswitch after setting dpdk-init: %s' % e)
                r, o, e = bash.bash_roe('systemctl restart ovn-controller')
                if r != 0:
                    raise Exception('failed to restart ovn-controller after setting dpdk-init: %s' % e)

        # 4. CPU cores (ovn.py line 284-291)
        if getattr(dpdk_config, 'lcores', None):
            dpdk_env = ovn.OvsDpdkEnv(
                dpdk_config.lcores,
                getattr(dpdk_config, 'pmdcores', None),
                0, 0, 0, None, None, None)
            lmask, pmd_mask = dpdk_env.getCpuMask()
            err1, cur_lcore = vsctl.getOvsOtherConfig("dpdk-lcore-mask")
            err2, cur_pmd = vsctl.getOvsOtherConfig("pmd-cpu-mask")
            if err1 or err2 or cur_lcore != lmask or cur_pmd != pmd_mask:
                r = vsctl.bindCpuCores(lmask, pmd_mask)
                if r != 0:
                    raise Exception('failed to set DPDK CPU masks')
                logger.info('set dpdk-lcore-mask=%s pmd-cpu-mask=%s' % (lmask, pmd_mask))

        # 5. ovn-monitor-all, ovn-remote-probe-interval (ovn.py line 295-307)
        err, val = vsctl.getOvsExternalIdsConfig("ovn-monitor-all")
        if err or val == 'false':
            r = vsctl.setOvsExternalIdsConfig("ovn-monitor-all", 'true')
            if r != 0:
                raise Exception('failed to set ovn-monitor-all')
        err, val = vsctl.getOvsExternalIdsConfig("ovn-remote-probe-interval")
        if err or val != '100000':
            r = vsctl.setOvsExternalIdsConfig("ovn-remote-probe-interval", '100000')
            if r != 0:
                raise Exception('failed to set ovn-remote-probe-interval')

        # 6. Ensure br-int datapath_type=netdev for DPDK mode (ovn.py line 276-280)
        # ovn-controller may create br-int with datapath_type=system on startup,
        # we need to set it to netdev for DPDK mode.
        r, _o, e = bash.bash_roe('ovs-vsctl --may-exist add-br br-int -- set bridge br-int datapath_type=netdev')
        if r != 0:
            raise Exception('failed to set br-int datapath_type=netdev: %s' % e)
        logger.info('ensured br-int datapath_type=netdev for DPDK mode')

        logger.info('DPDK mode initialized')

    @staticmethod
    def _clean_stale_vnics():
        """Clean stale vnic ports from br-int when no VMs are running.

        Called after ovsdb-server is up but before ovs-vswitchd restarts.
        Same logic as ovn.py start_ovn_service line 242-254.
        """
        from kvmagent.plugins.vm_plugin import get_running_vms

        r, o, e = bash.bash_roe("ovs-vsctl --bare --columns=name list Port")
        if r != 0:
            logger.warn('failed to list ports for vnic cleanup: %s' % e)
            return

        vms = get_running_vms()
        if len(vms) == 0:
            vnics = [v.strip() for v in o.split('\n') if v.strip()]
            for vnic in vnics:
                if vnic.startswith('vnic'):
                    _validate_ovs_name(vnic)
                    r2, o2 = bash.bash_ro(
                        "ovs-vsctl --no-wait --if-exists del-port br-int %s" % vnic)
                    if r2 != 0:
                        logger.warn('delete stale vnic %s failed: %s' % (vnic, o2))

    @staticmethod
    def _reset_ovn_controller_sb_cluster_state():
        """Best-effort reset ovn-controller cached SB Raft state (ZCF-2129).

        Idempotent and lightweight -- safe to call on every provision.
        """
        cmd = 'timeout 5 ovn-appctl -t ovn-controller sb-cluster-state-reset'
        retries, interval = 3, 1
        last_err = None

        for i in range(retries):
            r, o, e = bash.bash_roe(cmd)
            if r == 0:
                logger.info('ovn-controller SB cluster state reset completed')
                return
            last_err = (r, o, e)
            if i < retries - 1:
                logger.warn('sb-cluster-state-reset failed (try %s/%s, rc=%s): '
                            'stdout=%s stderr=%s'
                            % (i + 1, retries, r, o, e))
                time.sleep(interval)

        r, o, e = last_err
        logger.warn('sb-cluster-state-reset failed after %s retries (rc=%s): '
                    'stdout=%s stderr=%s' % (retries, r, o, e))

    @staticmethod
    def _read_existing_sdn_controller_uuid(retries=1):
        """Read sdn-controller-uuid from Open_vSwitch.external_ids.

        Returns a tri-state tuple (state, value):
          - ('present', uuid)     -- key is set in external_ids
          - ('absent', None)      -- ovsdb is reachable but key not set
                                     (legitimate first-provision state)
          - ('unreachable', err)  -- ovsdb-server is down / hung / not installed

        Uses `ovs-vsctl --format=json --columns=external_ids list Open_vSwitch`
        and JSON parses the result. This is robust against value contents
        (commas, equals, quotes, escapes), unlike string-splitting the OVSDB
        map literal. A short `--timeout` prevents hanging on a half-dead
        ovsdb. Optionally retries once on unreachable to absorb the brief
        gap between `systemctl start ovsdb-server` returning and the unix
        socket actually accepting clients.

        :param retries: extra attempts after the first failure (default 1).
        """
        cmd = ('ovs-vsctl --timeout=5 --format=json --columns=external_ids '
               'list Open_vSwitch')
        last_err = ''
        for attempt in range(retries + 1):
            r, o, e = bash.bash_roe(cmd)
            if r != 0:
                last_err = (e or '').strip() or ('rc=%s' % r)
                if attempt < retries:
                    time.sleep(0.5)
                    continue
                return 'unreachable', last_err

            try:
                payload = json.loads(o)
            except Exception as ex:
                # If the output is not parseable JSON, treat as transient
                # and retry; otherwise report unreachable.
                last_err = 'json parse error: %s; raw=%r' % (ex, o[:200])
                if attempt < retries:
                    time.sleep(0.5)
                    continue
                return 'unreachable', last_err

            try:
                # payload format:
                #   {"data": [[ ["map", [["k1","v1"],["k2","v2"],...]] ]],
                #    "headings": ["external_ids"]}
                rows = payload.get('data') or []
                if not rows:
                    return 'absent', None
                cell = rows[0][0]
                if (isinstance(cell, list) and len(cell) == 2
                        and cell[0] == 'map'):
                    pairs = cell[1] or []
                    for kv in pairs:
                        if (isinstance(kv, list) and len(kv) == 2
                                and kv[0] == SDN_CONTROLLER_UUID_KEY):
                            return 'present', kv[1]
                    return 'absent', None
                # Unexpected shape -- fail-closed.
                return 'unreachable', ('unexpected json shape: %r'
                                       % (payload,))[:200]
            except Exception as ex:
                return 'unreachable', 'json shape error: %s' % ex

        return 'unreachable', last_err

    @lock.lock('ovs_provision')
    @bash.in_bash
    def provision(self, req):
        rsp = ProvisionResponse()
        dpdk_bound_pci_list = None
        try:
            cmd = jsonobject.loads(req[http.REQUEST_BODY])

            # Unwrap spec: hostSwitches, globalConfig etc. are nested under spec
            self._unwrap_spec(cmd)

            rsp.hostUuid = cmd.hostUuid
            rsp.cloudCallbackUrl = getattr(cmd, 'cloudCallbackUrl', None)
            rsp.cloudTaskUuid = getattr(cmd, 'cloudTaskUuid', None)
            rsp.triggerUrl = getattr(cmd, 'triggerUrl', None)

            logger.info('received OVS provision request, configVersion=%s' % cmd.configVersion)

            if not cmd.hostUuid:
                raise Exception('hostUuid is required')
            if cmd.configVersion is None:
                raise Exception('configVersion is required')

            # ZCF-2786: sdnControllerUuid is mandatory — reject early.
            sdn_controller_uuid = getattr(cmd, 'sdnControllerUuid', None)
            if not sdn_controller_uuid:
                raise Exception('sdnControllerUuid is required for provision')

            # ZCF-2786: best-effort early ownership check. If ovsdb happens
            # to be reachable right now and external_ids already records a
            # different controller, reject before doing anything destructive
            # (NIC validation, package install, DPDK driver bind, hugepage
            # alloc, systemctl restart, _clear_dpdk_other_config). When ovsdb
            # is down (e.g. deprovisioned host), this check is skipped and
            # the strict late check after ensureOvsRunning() takes over.
            early_state, early_value = self._read_existing_sdn_controller_uuid()
            if early_state == 'present' and early_value != sdn_controller_uuid:
                raise Exception(
                    'host already managed by another SdnController: %s, '
                    'current request from: %s'
                    % (early_value, sdn_controller_uuid))

            desired_switches = cmd.hostSwitches if cmd.hostSwitches else []
            dpdk_mode = any((getattr(sw, 'type_', None) or getattr(sw, 'type', None)) == 'dpdk'
                            for sw in desired_switches)

            # Collect managed bridge names so re-provision is not blocked
            # for NICs already belonging to our bridges.
            managed_bridge_names = set()
            for sw in desired_switches:
                sw_name = getattr(sw, 'name', None)
                if sw_name:
                    managed_bridge_names.add(OvsDesiredState._safe_bridge_name(sw_name))

            _verify_nics_not_in_use(desired_switches, managed_bridge_names)

            # Ensure OVS/OVN packages are installed
            vsctl = ovn.VsCtl()
            r = bash.bash_r('which ovs-vsctl')
            if r != 0:
                logger.info('ovs-vsctl not found, installing OVS/OVN packages')
                ovn.VsCtl.installOvsPackages()

            # --- Resolve dpdk_config ---
            # Level 1: normalize spec.dpdkConfig into agent internal field names
            raw_dpdk_config = getattr(cmd, 'dpdkConfig', None)
            dpdk_config = (self._normalize_dpdk_config(raw_dpdk_config)
                           if raw_dpdk_config else None)
            if dpdk_config:
                cmd.dpdkConfig = dpdk_config

            # Level 2: extract from per-switch dpdkConfig
            if dpdk_mode and not dpdk_config:
                for sw in desired_switches:
                    sw_type = getattr(sw, 'type_', None) or getattr(sw, 'type', None)
                    sw_dpdk_cfg = getattr(sw, 'dpdkConfig', None)
                    if sw_type == 'dpdk' and sw_dpdk_cfg:
                        dpdk_config = self._normalize_dpdk_config(sw_dpdk_cfg)
                        cmd.dpdkConfig = dpdk_config
                        logger.info('extracted dpdkConfig from switch %s' % sw.name)
                        break

            # Auto-populate nicNamePciAddressMap if missing (fallback)
            if dpdk_config and not getattr(dpdk_config, 'nicNamePciAddressMap', None):
                nic_pci_map = self._build_nic_pci_map_from_uplink(desired_switches)
                if nic_pci_map:
                    dpdk_config.nicNamePciAddressMap = nic_pci_map
                    logger.info('auto-discovered NIC PCI map for DPDK')
                else:
                    logger.warn('dpdk_config exists but nicNamePciAddressMap is missing '
                                'and _build_nic_pci_map_from_uplink(desired_switches) '
                                'returned no map; clearing cmd.dpdkConfig, setting '
                                'dpdk_mode=False, and converting desired_switches to system')
                    dpdk_config = None
                    dpdk_mode = False
                    self._fallback_dpdk_switches_to_system(cmd, desired_switches)

            # Level 3: no dpdkConfig at all -- construct from defaults
            if dpdk_mode and not dpdk_config:
                nic_pci_map = self._build_nic_pci_map_from_uplink(desired_switches)
                if nic_pci_map:
                    dpdk_config = DefaultDpdkConfig(nic_pci_map)
                    cmd.dpdkConfig = dpdk_config
                    logger.info('using default dpdkConfig with auto-discovered PCI map')
                else:
                    logger.warn('dpdk mode requested but cannot determine NIC PCI addresses, '
                                'falling back to kernel mode startup')
                    # Override switch types so DesiredStateBuilder produces
                    # datapath_type=system instead of netdev.
                    self._fallback_dpdk_switches_to_system(cmd, desired_switches)
                    dpdk_mode = False

            nic_pci_map = getattr(dpdk_config, 'nicNamePciAddressMap', None) if dpdk_config else None

            # Bring OVS services up so we can read external_ids for the late
            # ownership check below.
            if dpdk_config:
                # ----------------------------------------------------------
                # DPDK startup -- strictly follows ovn.py start_ovn_service.
                # Step 0 (NIC PCI driver rebind) MUST happen before
                # ovs-vswitchd starts: if dpdk-init=true persists in OVSDB
                # from a previous run, ovs-vswitchd attempts DPDK EAL init
                # on startup and needs the NIC already bound to a DPDK
                # driver. Moving this past the ownership check would break
                # cold-restart of a host that previously ran in DPDK mode.
                # The trade-off is that a wrong-controller DPDK request can
                # still rebind NICs; the early best-effort check above
                # mitigates the common case (ovsdb up, mismatched UUID).
                # ----------------------------------------------------------

                # Step 0: bind NIC drivers (ovn.py line 226)
                if nic_pci_map:
                    r, e = ovn.changeNicToDpdkDriver(nic_pci_map)
                    if r != 0:
                        raise Exception('failed to change NIC to DPDK driver: %s' % e)
                    dpdk_bound_pci_list = list(nic_pci_map.__dict__.values())

                    # Verify NIC drivers are actually bound after changeNicToDpdkDriver.
                    # dpdk-devbind.py may return exit code 0 but skip binding when
                    # the interface is active, so we must confirm the driver switched.
                    verify_nics = ovn.getAllDpdkNic()
                    for nic_name, pci_addr in nic_pci_map.__dict__.items():
                        found = False
                        for nic in verify_nics:
                            if nic.pciAddress == pci_addr:
                                found = True
                                if nic.driver not in ('vfio-pci', 'uio_pci_generic', 'mlx5_core'):
                                    raise Exception(
                                        'failed to change NIC to DPDK driver: '
                                        'nic %s [pci address: %s] driver binding verification failed: '
                                        'expected DPDK driver, got %s'
                                        % (nic_name, pci_addr, nic.driver))
                                break
                        if not found:
                            raise Exception(
                                'failed to change NIC to DPDK driver: '
                                'nic %s [pci address: %s] not found in dpdk-devbind status output'
                                % (nic_name, pci_addr))

                # Step 1: ensure OVS services running (ovn.py line 236-259)
                if not vsctl.isOvsRunning():
                    # Allocate hugepages BEFORE starting openvswitch.
                    # If dpdk-init=true persists in OVSDB from a previous run,
                    # ovs-vswitchd will attempt DPDK EAL init on startup and
                    # needs hugepages to be available.
                    self._ensure_hugepages(
                        dpdk_config.hugePageNumber, dpdk_config.hugePageSize)

                    ok, err = vsctl.ensureOvsRunning(
                        after_ovsdb_start_hook=self._clean_stale_vnics)
                    if not ok:
                        raise Exception('failed to ensure OVS running in DPDK mode: %s' % err)
            else:
                # ----------------------------------------------------------
                # Kernel mode startup
                # ----------------------------------------------------------
                ok, err = vsctl.ensureOvsRunning(
                    after_ovsdb_start_hook=self._clean_stale_vnics)
                if not ok:
                    raise Exception('failed to ensure OVS running: %s' % err)

            # ZCF-2786: late strict ownership check (must happen here).
            # ovsdb-server is now guaranteed to be running by the block
            # above. This is the last point before any code mutates OVSDB
            # content (DPDK init / clear-other-config / provisioner.apply);
            # wrong-controller kernel-mode requests are rejected here before
            # any such write.
            #
            # Note: in DPDK mode, NIC PCI rebind already happened above
            # (it must run before ovs-vswitchd starts, see comment there).
            # That side effect is only protected by the early best-effort
            # check, not by this strict one. Acceptable because DPDK
            # provision is always initiated by ZNS itself in practice.
            #
            # The reader does a single ovs-vsctl read with --timeout=5 and
            # JSON parsing (no ad-hoc string splitting), and retries once
            # to absorb the brief gap between systemctl returning and the
            # ovsdb unix socket accepting clients.
            state, value = self._read_existing_sdn_controller_uuid()
            if state == 'unreachable':
                # Should not happen here -- ovsdb was just started.
                # Fail-closed; reconciler will retry on the next pass.
                raise Exception(
                    'cannot verify SdnController ownership: '
                    'ovsdb unreachable after start (%s)' % value)
            if state == 'present' and value != sdn_controller_uuid:
                raise Exception(
                    'host already managed by another SdnController: %s, '
                    'current request from: %s'
                    % (value, sdn_controller_uuid))
            # state == 'absent' (first provision after deprovision or fresh
            # host) or state == 'present' with matching UUID: proceed.

            # ============================================================
            # OVSDB-content mutation below this line is only reached after
            # ownership has been verified by the late strict check.
            # ============================================================
            if dpdk_config:
                # DPDK Step 2: DPDK init (ovn.py line 261-307)
                # hugepages, dpdk-socket-mem, dpdk-init, CPU masks, monitor config
                self._ensure_dpdk_init(vsctl, dpdk_config)
            else:
                # Kernel mode: clear any residual DPDK other_config to prevent
                # dpdk_initialized from lingering after a DPDK-to-kernel switch.
                self._clear_dpdk_other_config(vsctl)

                # ZCF-1841 (reverse): when switching from DPDK to kernel mode
                # the previously-existing br-int (created by ovn-controller and
                # not deleted by deprovision because it lacks managed-by tag)
                # still has datapath_type=netdev from the prior DPDK provision.
                # That mismatches the system-mode user bridges and breaks
                # traffic. Force br-int back to datapath_type=system. Mirror
                # of the netdev-direction fix already done in _ensure_dpdk_init.
                r, _o, e = bash.bash_roe(
                    'ovs-vsctl --may-exist add-br br-int '
                    '-- set bridge br-int datapath_type=system')
                if r != 0:
                    raise Exception('failed to set br-int datapath_type=system: %s' % e)
                logger.info('ensured br-int datapath_type=system for kernel mode')

            # Step 3: bridge / bond / OVN config (ovn.py line 276-383)
            provisioner = OvsProvisioner()
            rsp = provisioner.apply(cmd)

            # Best-effort reset cached SB cluster state after provision
            self._reset_ovn_controller_sb_cluster_state()

            # Step 4: DPDK post-provisioning (ovn.py line 331-395)
            if dpdk_config:
                # rx queue (ovn.py line 331-355)
                if getattr(dpdk_config, 'nicRxQueueNumber', None) and nic_pci_map:
                    for nic_name in nic_pci_map.__dict__:
                        err1, cur_rxq = vsctl.getNicRxQueueNumConfig(nic_name)
                        err2, cur_desc = vsctl.getNicRxQueueDescNumConfig(nic_name)
                        if (err1 or err2
                                or str(cur_rxq) != str(dpdk_config.nicRxQueueNumber)
                                or str(cur_desc) != str(dpdk_config.nicRxQueueDescNumber)):
                            r = vsctl.setNicRxQueueConfig(
                                nic_name, dpdk_config.nicRxQueueNumber,
                                dpdk_config.nicRxQueueDescNumber)
                            if r != 0:
                                raise Exception('failed to set DPDK rx queue config for %s' % nic_name)

                # userspace-tso-enable (ovn.py line 385-390)
                err, val = vsctl.getOvsOtherConfig("userspace-tso-enable")
                if err or val != 'true':
                    r = vsctl.setOvsOtherConfig("userspace-tso-enable", 'true')
                    if r != 0:
                        raise Exception('failed to set userspace-tso-enable')

                # restoreNicDriver (ovn.py line 392-395)
                restore_list = getattr(cmd, 'restoreNicPciAddressList', None)
                if restore_list:
                    self._stop_openvswitch_before_nic_restore()
                    restore_ret, restore_err = ovn.restoreNicDriver(restore_list)
                    r, o, e = bash.bash_roe("systemctl start openvswitch")
                    if r != 0:
                        if restore_ret != 0:
                            raise Exception('failed to restore NIC drivers: %s; failed to start openvswitch after restoring NIC drivers: %s'
                                            % (restore_err, e))
                        raise Exception('failed to start openvswitch after restoring NIC drivers: %s' % e)
                    if restore_ret != 0:
                        raise Exception('failed to restore NIC drivers: %s' % restore_err)

            logger.info('OVS provision completed successfully, configVersion=%s' % cmd.configVersion)
            return jsonobject.dumps(rsp)
        except Exception as e:
            rollback_errors = []
            if dpdk_bound_pci_list:
                logger.error('OVS provision failed after binding NIC drivers, restoring PCI addresses: %s'
                             % dpdk_bound_pci_list)
                try:
                    self._stop_openvswitch_before_nic_restore()
                    restore_ret, restore_err = ovn.restoreNicDriver(dpdk_bound_pci_list)
                    if restore_ret != 0:
                        rollback_errors.append('failed to restore NIC drivers after provision failure: %s'
                                               % restore_err)
                except Exception as rollback_error:
                    rollback_errors.append(str(rollback_error))
                for rollback_error in rollback_errors:
                    logger.error(rollback_error)
            content = traceback.format_exc()
            logger.warn('OVS provision failed, hostUuid=%s, error=%s\n%s'
                        % (getattr(rsp, 'hostUuid', None), str(e), content))
            rsp.success = False
            rsp.error = str(e)
            if rollback_errors:
                rsp.error = '%s; rollback failed: %s' % (rsp.error, '; '.join(rollback_errors))
            return jsonobject.dumps(rsp)

    @lock.lock('ovs_provision')
    @bash.in_bash
    def deprovision(self, req):
        rsp = DeprovisionResponse()
        try:
            cmd = jsonobject.loads(req[http.REQUEST_BODY])
            self._unwrap_spec(cmd)

            rsp.hostUuid = getattr(cmd, 'hostUuid', None)
            rsp.cloudCallbackUrl = getattr(cmd, 'cloudCallbackUrl', None)
            rsp.cloudTaskUuid = getattr(cmd, 'cloudTaskUuid', None)
            rsp.triggerUrl = getattr(cmd, 'triggerUrl', None)

            if not getattr(cmd, 'hostUuid', None):
                raise Exception('hostUuid is required')

            force = getattr(cmd, 'force', False)
            logger.info('received OVS deprovision request, hostUuid=%s, force=%s' % (cmd.hostUuid, force))

            # ZCF-2786: verify SdnController ownership before deprovisioning.
            # sdnControllerUuid is mandatory — reject requests without it.
            # Skip ownership check when force=true (force ignores all safety checks).
            sdn_controller_uuid = getattr(cmd, 'sdnControllerUuid', None)
            if not sdn_controller_uuid:
                raise Exception('sdnControllerUuid is required for deprovision')

            if not force:
                self._check_deprovision_ownership(sdn_controller_uuid)

            # helper: check if a systemd service is active
            # Returns: 'active', 'inactive', or 'unknown'
            #  - 'active'   : service is running
            #  - 'inactive' : systemctl confirmed inactive/unknown/dead
            #  - 'unknown'  : query itself failed (e.g. D-Bus error)
            def _query_service_state(svc):
                r, o, e = bash.bash_roe('systemctl is-active %s' % svc)
                stdout = o.strip()
                if stdout == 'active':
                    return 'active'
                if stdout in ('inactive', 'unknown', 'dead', 'failed'):
                    return 'inactive'
                # Non-zero exit with unexpected output treat as query failure
                if r != 0:
                    logger.warn('systemctl is-active %s returned exit=%d stdout=%r stderr=%r'
                                % (svc, r, stdout, e.strip()))
                    return 'unknown'
                return 'inactive'

            # helper: check if ovsdb-server is reachable
            def _is_ovsdb_reachable():
                r, o, e = bash.bash_roe('timeout 5 ovs-vsctl show')
                return r == 0

            # 1. Stop ovn-controller
            ovn_ctl_state = _query_service_state('ovn-controller')
            if ovn_ctl_state == 'active':
                r, o, e = bash.bash_roe('systemctl stop ovn-controller')
                if r != 0:
                    raise Exception('failed to stop ovn-controller: %s' % e)
                logger.info('stopped ovn-controller')
            elif ovn_ctl_state == 'inactive':
                logger.info('ovn-controller already stopped, skipping')
            else:
                raise Exception('cannot determine ovn-controller state, aborting deprovision')

            # 2. Clear OVN external_ids from Open_vSwitch table
            # 3. Delete all managed-by=zstack-agent bridges
            if _is_ovsdb_reachable():
                vsctl = ovn.VsCtl()
                failed_keys = []
                for key in MANAGED_OVS_EXTERNAL_ID_KEYS:
                    err, val = vsctl.getOvsExternalIdsConfig(key)
                    if not err and val is not None:
                        r, o, e = bash.bash_roe('ovs-vsctl remove Open_vSwitch . external_ids %s'
                                                % key)
                        if r != 0:
                            failed_keys.append(key)
                            logger.warn('failed to remove OVN external_id %s: %s' % (key, e))
                if failed_keys:
                    raise Exception('failed to clear OVN external_ids: %s' % failed_keys)
                logger.info('cleared OVN external_ids')

                br_names = vsctl.listBridges()
                for br_name in br_names:
                    ext_ids = vsctl.getBridgeExternalIds(br_name)
                    if ext_ids.get(MANAGED_BY_KEY) == MANAGED_BY_VALUE:
                        _validate_ovs_name(br_name)
                        r, o, e = bash.bash_roe('ovs-vsctl --if-exists del-br %s' % br_name)
                        if r != 0:
                            raise Exception('failed to delete bridge %s: %s' % (br_name, e))
                        logger.info('deleted managed bridge %s' % br_name)

                # 3b. Clear DPDK other_config keys to prevent dpdk_initialized
                # from lingering after a DPDK-to-kernel mode switch.
                self._clear_dpdk_other_config(vsctl)
            else:
                if not force:
                    raise Exception('ovsdb not reachable and force is not set, cannot deprovision safely')
                logger.warn('ovsdb not reachable but force=True, skipping external_ids cleanup and bridge deletion')

            # 4. Discover DPDK-bound NICs before stopping OVS (so we know what to restore)
            restore_pci_list = getattr(cmd, 'restoreNicPciAddressList', None) or []
            auto_pci = _get_dpdk_bound_network_devices()
            if auto_pci:
                existing = set(restore_pci_list)
                for pci in auto_pci:
                    if pci not in existing:
                        restore_pci_list.append(pci)
                logger.info('found %d DPDK-bound NICs to restore: %s'
                            % (len(restore_pci_list), restore_pci_list))

            # 5. Stop openvswitch
            ovs_state = _query_service_state('openvswitch')
            if ovs_state == 'active':
                r, o, e = bash.bash_roe('systemctl stop openvswitch')
                if r != 0:
                    raise Exception('failed to stop openvswitch: %s' % e)
                logger.info('stopped openvswitch')
            elif ovs_state == 'inactive':
                logger.info('openvswitch already stopped, skipping')
            else:
                raise Exception('cannot determine openvswitch state, aborting deprovision')

            # 6. Stop ovsdb-server if it is a separate service unit
            ovsdb_state = _query_service_state('ovsdb-server')
            if ovsdb_state == 'active':
                r, o, e = bash.bash_roe('systemctl stop ovsdb-server')
                if r != 0:
                    # Non-zero may be a real failure, or a race where
                    # stopping openvswitch already took ovsdb-server down.
                    # Re-check the actual state before deciding.
                    recheck = _query_service_state('ovsdb-server')
                    if recheck != 'inactive':
                        raise Exception('failed to stop ovsdb-server: %s' % e)
                    logger.info('ovsdb-server already inactive after stop attempt (likely cascaded), continuing')
                else:
                    logger.info('stopped ovsdb-server')
            elif ovsdb_state == 'inactive':
                logger.info('ovsdb-server already stopped, skipping')
            else:
                raise Exception('cannot determine ovsdb-server state, aborting deprovision')

            # 7. Restore NIC drivers from DPDK to kernel drivers
            if restore_pci_list:
                logger.info('restoring NIC drivers for PCI addresses: %s' % restore_pci_list)
                r, e = ovn.restoreNicDriver(restore_pci_list)
                if r != 0:
                    raise Exception('failed to restore NIC drivers: %s' % e)
                logger.info('NIC driver restoration completed')

            logger.info('OVS deprovision completed, hostUuid=%s' % cmd.hostUuid)
            return jsonobject.dumps(rsp)
        except Exception as e:
            content = traceback.format_exc()
            logger.warn('OVS deprovision failed, hostUuid=%s, error=%s\n%s'
                        % (getattr(rsp, 'hostUuid', None), str(e), content))
            rsp.success = False
            rsp.error = str(e)
            return jsonobject.dumps(rsp)
