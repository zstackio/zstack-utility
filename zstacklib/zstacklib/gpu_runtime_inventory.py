# -*- coding: utf-8 -*-

import datetime
import json
import re


def get_nvidia_runtime_inventory_cmd(is_windows=False):
    cmd = (
        'nvidia-smi --query-gpu=gpu_uuid,gpu_bus_id,memory.total,'
        'power.limit,gpu_serial,driver_version,name,index '
        '--format=csv,noheader')
    if is_windows:
        return cmd.replace(' ', '|')
    return cmd


def get_nvidia_topology_cmd(is_windows=False):
    cmd = 'nvidia-smi topo -m'
    if is_windows:
        return cmd.replace(' ', '|')
    return cmd


class RuntimeInventoryError(Exception):
    pass


class RuntimeGpuIdentity(object):

    def __init__(self, kind, value):
        self.kind = kind
        self.value = value

    def to_dict(self):
        return {
            'kind': self.kind,
            'value': self.value
        }


class RuntimeGpuDriver(object):

    def __init__(self, loaded, ready, version, reason=None):
        self.loaded = bool(loaded)
        self.ready = bool(ready)
        self.version = version
        self.reason = reason

    def to_dict(self):
        return {
            'loaded': self.loaded,
            'ready': self.ready,
            'version': self.version,
            'reason': self.reason
        }


class RuntimeDeviceNode(object):

    def __init__(self, path, major, minor):
        self.path = path
        self.major = int(major)
        self.minor = int(minor)

    def to_dict(self):
        return {
            'path': self.path,
            'major': self.major,
            'minor': self.minor
        }


class RuntimeGpuDevice(object):

    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return dict(self.payload)


def _utc_now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def _parse_integer(value):
    if value in (None, ''):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _value_to_bytes(value):
    amount = _parse_unit_value(value)
    if amount is None:
        return None

    text = (value or '').strip().lower()
    if text.endswith('gib') or text.endswith('gb'):
        return int(amount * 1024 * 1024 * 1024)
    if text.endswith('mib') or text.endswith('mb'):
        return int(amount * 1024 * 1024)
    if text.endswith('kib') or text.endswith('kb'):
        return int(amount * 1024)
    if text.endswith('b'):
        return int(amount)
    return int(amount)


def _value_to_milliwatts(value):
    amount = _parse_unit_value(value, 'W')
    if amount is None:
        return None
    return int(amount * 1000)


def _normalize_pci_address(value):
    if not value:
        return None
    addr = str(value).strip()
    if not addr:
        return None

    match = re.search(
        r'(?:0x)?[0-9a-fA-F]{1,8}:(?:0x)?[0-9a-fA-F]{1,2}:'
        r'(?:0x)?[0-9a-fA-F]{1,2}\.(?:0x)?[0-9a-fA-F]+',
        addr)
    if match:
        addr = match.group(0)

    addr = re.sub(r'0x', '', addr, flags=re.IGNORECASE)
    parts = addr.split(':')
    if len(parts) == 2:
        if '.' not in parts[1]:
            return None
        domain = '0000'
        bus = parts[0]
        slot_func = parts[1]
    elif len(parts) == 3:
        domain = parts[0]
        bus = parts[1]
        slot_func = parts[2]
    else:
        return None

    try:
        domain = format(int(domain, 16), '04x')
        bus = format(int(bus, 16), '02x')
    except ValueError:
        return None

    if '.' not in slot_func:
        return None
    slot, function = slot_func.split('.', 1)
    try:
        slot = format(int(slot, 16), '02x')
        function = format(int(function, 16), 'x')
    except ValueError:
        return None

    if len(domain) == 8:
        domain = domain[4:]
    return '%s:%s:%s.%s' % (domain, bus, slot, function)


def _parse_unit_value(value, target_unit=None):
    if not value:
        return None

    match = re.match(r'^([\d.]+)\s*(\S*)$', value.strip())
    if not match:
        return None

    parsed_value = match.group(1)
    parsed_unit = match.group(2).strip().lower()
    if target_unit:
        target_unit = target_unit.strip().lower()
        unit_aliases = {
            'mib': ['mib', 'mb', 'm'],
            'w': ['w', 'watts', 'watt'],
        }
        if parsed_unit != target_unit:
            matched = False
            for aliases in unit_aliases.values():
                if target_unit in aliases and parsed_unit in aliases:
                    matched = True
                    break
            if not matched:
                return None

    try:
        return float(parsed_value)
    except ValueError:
        return None


def _make_probe(name, kind, status, version=None, message=None):
    return {
        'name': name,
        'kind': kind,
        'status': status,
        'version': version,
        'message': message
    }


def build_runtime_inventory(
        target_uuid,
        observation_generation,
        observed_at,
        valid_until,
        collector_version,
        boot_id,
        probes,
        devices,
        topology):
    return {
        'schemaVersion': '1.0.0',
        'targetUuid': target_uuid,
        'observationGeneration': observation_generation,
        'observedAt': observed_at,
        'validUntil': valid_until,
        'source': {
            'collector': 'zstack-utility',
            'collectorVersion': collector_version,
            'bootId': boot_id,
            'probes': probes
        },
        'devices': devices,
        'topology': topology
    }


def build_unsupported_runtime_inventory(
        target_uuid,
        observation_generation,
        observed_at,
        valid_until,
        collector_version,
        boot_id,
        vendor_names,
        reason):
    vendor_names = [name for name in (vendor_names or []) if name]
    vendor_label = ', '.join(vendor_names) if vendor_names else 'Unknown'
    probes = [
        _make_probe(
            'vendor-runtime-query',
            'VendorCli',
            'Unavailable',
            None,
            reason),
        _make_probe(
            'gpu-pci-discovery',
            'PciDb',
            'Succeeded',
            None,
            'detected GPU vendors without qualified runtime support: %s'
            % vendor_label)
    ]
    topology = {
        'status': 'Unavailable',
        'observedAt': observed_at,
        'validUntil': valid_until,
        'source': 'None',
        'links': [],
        'reason': reason
    }
    return build_runtime_inventory(
        target_uuid=target_uuid,
        observation_generation=observation_generation,
        observed_at=observed_at,
        valid_until=valid_until,
        collector_version=collector_version,
        boot_id=boot_id,
        probes=probes,
        devices=[],
        topology=topology)


def parse_nvidia_runtime_query_output(output):
    devices = []
    if not output:
        return devices

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parts = [part.strip() for part in line.split(',')]
        if len(parts) < 8:
            raise RuntimeInventoryError(
                'nvidia runtime inventory row must contain 8 columns')

        gpu_uuid = parts[0]
        pci_address = _normalize_pci_address(parts[1])
        if not gpu_uuid or not gpu_uuid.startswith('GPU-'):
            raise RuntimeInventoryError(
                'nvidia runtime inventory row is missing stable GPU UUID')
        if not pci_address:
            raise RuntimeInventoryError(
                'nvidia runtime inventory row is missing PCI address')

        memory_bytes = _value_to_bytes(parts[2])
        if memory_bytes is None or memory_bytes <= 0:
            raise RuntimeInventoryError(
                'nvidia runtime inventory row is missing valid memory size')

        devices.append({
            'gpuUuid': gpu_uuid,
            'pciAddress': pci_address,
            'memoryBytes': memory_bytes,
            'powerLimitMilliwatts': _value_to_milliwatts(parts[3]),
            'serialNumber': parts[4] or None,
            'driverVersion': parts[5] or None,
            'model': parts[6] or 'NVIDIA GPU',
            'index': _parse_integer(parts[7]),
            'vendor': 'NVIDIA'
        })

    return devices


def parse_nvidia_topology_output(output, gpu_devices):
    observed_at = None
    valid_until = None
    links = []
    source = 'None'
    status = 'Unavailable'
    reason = None

    if not output:
        return {
            'status': status,
            'observedAt': observed_at,
            'validUntil': valid_until,
            'source': source,
            'links': links,
            'reason': 'topology output is empty'
        }

    hardware_ids = {}
    for device in gpu_devices:
        if device.get('index') is not None:
            hardware_ids['GPU%s' % device['index']] = device['hardwareId']

    header_tokens = []
    rows = []
    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith('Legend'):
            break
        tokens = re.findall(r'GPU\d+|NIC\d+|CPU Affinity|NUMA Affinity|GPU NUMA ID|\S+', line)
        if not tokens:
            continue
        if tokens[0].startswith('GPU') and not header_tokens:
            header_tokens = [token for token in tokens if token.startswith('GPU')]
            continue
        if tokens[0].startswith('GPU'):
            rows.append(tokens)

    if not header_tokens or not rows:
        return {
            'status': status,
            'observedAt': observed_at,
            'validUntil': valid_until,
            'source': source,
            'links': links,
            'reason': 'topology matrix is missing GPU rows'
        }

    for row in rows:
        row_name = row[0]
        from_hardware_id = hardware_ids.get(row_name)
        if not from_hardware_id:
            continue
        for offset, header in enumerate(header_tokens, start=1):
            if offset >= len(row):
                continue
            label = row[offset]
            to_hardware_id = hardware_ids.get(header)
            if not to_hardware_id or to_hardware_id == from_hardware_id:
                continue
            if from_hardware_id > to_hardware_id:
                continue
            if label in ('X', 'N/A'):
                continue

            link_kind = 'Unknown'
            lane_count = None
            if re.match(r'^NV\d+$', label):
                link_kind = 'NvLink'
                lane_count = int(label[2:])
            elif label in ('PIX', 'PXB', 'PHB', 'NODE', 'SYS'):
                link_kind = 'Pcie'

            links.append({
                'fromHardwareId': from_hardware_id,
                'toHardwareId': to_hardware_id,
                'kind': link_kind,
                'direction': 'Bidirectional',
                'laneCount': lane_count,
                'bandwidthBytesPerSecond': None,
                'hops': 0,
                'label': label
            })

    source = 'VendorCli'
    status = 'Complete' if links or len(gpu_devices) <= 1 else 'Partial'
    reason = None if status == 'Complete' else 'topology matrix reported no GPU links'
    return {
        'status': status,
        'observedAt': observed_at,
        'validUntil': valid_until,
        'source': source,
        'links': links,
        'reason': reason
    }


def build_nvidia_runtime_inventory(
        target_uuid,
        observation_generation,
        observed_at,
        valid_until,
        collector_version,
        boot_id,
        query_output,
        topology_output,
        pci_device_facts,
        topology_observed_at=None,
        topology_valid_until=None,
        gpu_specs=None):
    parsed_devices = parse_nvidia_runtime_query_output(query_output)
    runtime_devices = []
    query_probe_version = None

    for parsed_device in parsed_devices:
        pci_fact = pci_device_facts.get(parsed_device['pciAddress'])
        if not pci_fact:
            raise RuntimeInventoryError(
                'no PCI fact found for %s' % parsed_device['pciAddress'])

        hardware_id = 'nvidia:%s' % parsed_device['gpuUuid']
        driver_loaded = bool(pci_fact.get('driverLoaded', True))
        driver_ready = bool(pci_fact.get('driverReady', driver_loaded))
        dedicated_nodes = pci_fact.get('dedicatedDeviceNodes') or []
        shared_nodes = pci_fact.get('sharedDeviceNodes') or []
        if not dedicated_nodes:
            raise RuntimeInventoryError(
                'dedicated device nodes are required for %s' % hardware_id)

        driver_reason = pci_fact.get('driverReason')
        driver_version = parsed_device.get('driverVersion')
        if driver_version and not query_probe_version:
            query_probe_version = driver_version

        gpu_spec = None
        if gpu_specs:
            gpu_spec = gpu_specs.get(parsed_device['gpuUuid'])
            if gpu_spec is None:
                gpu_spec = gpu_specs.get(parsed_device['pciAddress'])

        runtime_device = RuntimeGpuDevice({
            'hardwareId': hardware_id,
            'identity': RuntimeGpuIdentity(
                'VendorUuid', parsed_device['gpuUuid']).to_dict(),
            'vendor': parsed_device['vendor'],
            'model': parsed_device['model'],
            'gpuSpec': gpu_spec,
            'serialNumber': parsed_device['serialNumber'],
            'memoryBytes': parsed_device['memoryBytes'],
            'powerLimitMilliwatts': parsed_device['powerLimitMilliwatts'],
            'driver': RuntimeGpuDriver(
                driver_loaded,
                driver_ready,
                driver_version,
                driver_reason).to_dict(),
            'pci': {
                'address': parsed_device['pciAddress'],
                'vendorId': pci_fact['vendorId'],
                'deviceId': pci_fact['deviceId'],
                'subsystemVendorId': pci_fact.get('subsystemVendorId'),
                'subsystemDeviceId': pci_fact.get('subsystemDeviceId'),
                'iommuGroup': pci_fact.get('iommuGroup')
            },
            'numaNode': pci_fact.get('numaNode'),
            'dedicatedDeviceNodes': [
                RuntimeDeviceNode(**node).to_dict() for node in dedicated_nodes
            ],
            'sharedDeviceNodes': [
                RuntimeDeviceNode(**node).to_dict() for node in shared_nodes
            ],
            'visibility': {
                'CUDA_VISIBLE_DEVICES': parsed_device['gpuUuid'],
                'NVIDIA_VISIBLE_DEVICES': parsed_device['gpuUuid']
            },
            'extensions': pci_fact.get('extensions') or {}
        })
        runtime_devices.append(runtime_device.to_dict())
        parsed_device['hardwareId'] = hardware_id

    topology = parse_nvidia_topology_output(topology_output, parsed_devices)
    topology['observedAt'] = topology_observed_at or observed_at
    topology['validUntil'] = topology_valid_until or valid_until

    probes = [
        _make_probe(
            'nvidia-smi-query',
            'VendorCli',
            'Succeeded',
            query_probe_version,
            None)
    ]
    topo_status = 'Succeeded'
    topo_message = None
    if topology['status'] == 'Unavailable':
        topo_status = 'Unavailable'
        topo_message = topology.get('reason')
    elif topology['status'] == 'Partial':
        topo_status = 'Degraded'
        topo_message = topology.get('reason')
    probes.append(_make_probe(
        'nvidia-smi-topo',
        'VendorCli',
        topo_status,
        query_probe_version,
        topo_message))
    probes.append(_make_probe(
        'sysfs-device-nodes',
        'Sysfs',
        'Succeeded',
        None,
        None))

    return build_runtime_inventory(
        target_uuid=target_uuid,
        observation_generation=observation_generation,
        observed_at=observed_at,
        valid_until=valid_until,
        collector_version=collector_version,
        boot_id=boot_id,
        probes=probes,
        devices=runtime_devices,
        topology=topology)


def runtime_inventory_to_legacy_pci_devices(inventory):
    legacy_devices = []
    topology = inventory.get('topology') or {}
    for device in inventory.get('devices') or []:
        addon_info = {
            'memory': '%s B' % device['memoryBytes'],
            'power': None if device.get('powerLimitMilliwatts') is None
            else '%s W' % (float(device['powerLimitMilliwatts']) / 1000),
            'serialNumber': device.get('serialNumber'),
            'isDriverLoaded': device['driver']['loaded'],
            'driverReady': device['driver']['ready'],
            'driverVersion': device['driver']['version'],
            'hardwareId': device['hardwareId'],
            'inventoryGeneration': inventory.get('observationGeneration'),
            'authoritativeIdentity': json.dumps(device['identity']),
            'dedicatedDeviceNodes': json.dumps(
                device.get('dedicatedDeviceNodes') or []),
            'sharedDeviceNodes': json.dumps(
                device.get('sharedDeviceNodes') or []),
            'visibility': json.dumps(
                device.get('visibility') or {}, sort_keys=True),
            'numaNode': device.get('numaNode'),
            'topologyStatus': topology.get('status'),
            'topologySource': topology.get('source'),
            'topologyObservedAt': topology.get('observedAt'),
            'topologyValidUntil': topology.get('validUntil'),
            'topology': json.dumps(topology, sort_keys=True)
        }
        legacy_devices.append({
            'name': device.get('model'),
            'description': '%s runtime inventory device' % device.get('vendor'),
            'vendorId': device['pci']['vendorId'],
            'vendor': device.get('vendor'),
            'deviceId': device['pci']['deviceId'],
            'device': device.get('model'),
            'subVendorId': device['pci'].get('subsystemVendorId') or '',
            'subDeviceId': device['pci'].get('subsystemDeviceId') or '',
            'pciDeviceAddress': device['pci']['address'],
            'iommuGroup': '' if device['pci'].get('iommuGroup') is None
            else str(device['pci']['iommuGroup']),
            'type': 'GPU_Runtime_Inventory',
            'addonInfo': addon_info
        })
    return legacy_devices


__all__ = [
    'get_nvidia_runtime_inventory_cmd',
    'get_nvidia_topology_cmd',
    'RuntimeInventoryError',
    'RuntimeGpuIdentity',
    'RuntimeGpuDriver',
    'RuntimeDeviceNode',
    'RuntimeGpuDevice',
    'build_runtime_inventory',
    'build_unsupported_runtime_inventory',
    'parse_nvidia_runtime_query_output',
    'parse_nvidia_topology_output',
    'build_nvidia_runtime_inventory',
    'runtime_inventory_to_legacy_pci_devices',
    '_utc_now'
]

