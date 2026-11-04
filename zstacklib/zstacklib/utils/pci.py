import os
import platform
import re
import time

from zstacklib.utils import log, linux, sizeunit
import xml.etree.ElementTree as ET

from zstacklib.utils.bash import bash_roe

logger = log.get_logger(__name__)

_pci_device_cache = {}


class PciDeviceProcessingContext(object):
    """
    Context object for PCI device processing.

    This replaces the dict-based context to provide better structure and type safety.
    Processors can access and modify context data through this object.
    """

    def __init__(self, pci_device_mapper=None, opaque=None):
        """
        Initialize PCI device processing context.

        Args:
            pci_device_mapper: dict mapping PCI class names (for type detection)
            opaque: Optional opaque data for vendor-specific enrichment
        """
        self.pci_device_mapper = pci_device_mapper or {}
        self.opaque = opaque

        # Device-type-specific data (populated by processors during prepare phase)
        self.gpu_info_map = None  # Populated by GPU processor

        # Device capabilities storage: pciDeviceAddress -> capabilities dict
        # Note: This is now primarily used for non-GPU devices or legacy code
        # GPU capabilities are detected via vendor methods in GPU processor
        self.device_capabilities = {}

    def get_device_capabilities(self, pci_device_to):
        """
        Get capabilities for a PCI device.

        Args:
            pci_device_to: PciDeviceTO object

        Returns:
            dict: Capabilities dict, or empty dict if not found
        """
        return self.device_capabilities.get(pci_device_to.pciDeviceAddress, {})

    def set_device_capabilities(self, pci_device_to, capabilities):
        """
        Set capabilities for a PCI device.

        Args:
            pci_device_to: PciDeviceTO object
            capabilities: dict with capability information
        """
        self.device_capabilities[pci_device_to.pciDeviceAddress] = capabilities


# PCI device operations registry (Linux kernel style)
# Similar to pci_driver in Linux kernel, each ops contains:
#   - probe: (pci_device_to, context) -> bool, returns True if device matches (like pci_driver.id_table matching)
#   - init: (pci_device_to, context) -> bool, processes the device (like pci_driver.probe)
#   - prepare: (context) -> callable or None, optional, called once before processing devices
#     Can return a post-prepare hook (device_list, context) -> None to refine capabilities
# Reference: Linux kernel pci_driver structure and pci_register_driver()
_pci_device_ops_list = []

# Vendor name mapping for simplification (lightweight, no GPU vendor system dependency)
# Maps full vendor names from lspci to simplified names
_VENDOR_NAME_MAPPING = {
    'Intel Corporation': 'Intel',
    'Advanced Micro Devices': 'AMD',
    'NVIDIA Corporation': 'NVIDIA',
    'Chengdu Haiguang': 'Haiguang',
    'Chengdu C-3000': 'Haiguang',
    'Haiguang': 'Haiguang',
    'Hygon': 'Haiguang',
    'Huawei': 'Huawei',
    'TianShu': 'TianShu',
    'Vastai': 'Vastai',
    'Enflame': 'Enflame',
    'Alibaba': 'Alibaba',
    'Kunlunxin': 'Kunlunxin',
}

# Vendor ID mapping (for cases where name matching fails)
# Format: lowercase vendor_id -> simplified name
_VENDOR_ID_MAPPING = {
    '10de': 'NVIDIA',     # NVIDIA vendor ID
    '8086': 'Intel',      # Intel vendor ID
    '1002': 'AMD',        # AMD vendor ID
    '1d94': 'Haiguang',   # Hygon / Chengdu C-3000
    '1ded': 'Alibaba',    # Alibaba vendor ID
    '1e3e': 'TianShu',    # TianShu vendor ID
    '19e5': 'Huawei',     # Huawei vendor ID (NPU, etc.)
    '2057': 'Kunlunxin',  # Kunlunxin vendor ID (P800 etc.)
    '1d22': 'Kunlunxin',  # Kunlunxin vendor ID (alt)
}


def simplify_vendor_name(name, vendor_id=None):
    """
    Simplify PCI vendor name using lightweight configuration mapping.

    This function does not depend on the GPU vendor system, making it suitable
    for use in a generic PCI library. It uses simple string matching and
    configuration dictionaries.

    Args:
        name: Full vendor name from lspci (e.g., "NVIDIA Corporation")
        vendor_id: Optional vendor ID (e.g., "10de" for NVIDIA)

    Returns:
        str: Simplified vendor name (e.g., "NVIDIA"), or cleaned original name
    """
    if not name:
        return name

    # Try name-based matching first
    name_lower = name.lower()
    for full_name, short_name in _VENDOR_NAME_MAPPING.items():
        if full_name.lower() in name_lower:
            return short_name

    # If name matching fails and vendor_id is provided, try vendor_id mapping
    if vendor_id:
        vendor_id_lower = vendor_id.lower().strip()
        if vendor_id_lower in _VENDOR_ID_MAPPING:
            return _VENDOR_ID_MAPPING[vendor_id_lower]

    # Fallback: clean common suffixes and extract bracketed name if present
    result = name.replace('Co., Ltd ', '').replace('Corporation', '').strip()
    matches = re.findall(r'\[([^\]]+)]', result)
    if matches:
        result = ' '.join(m.strip() for m in matches)
    return result


def simplify_device_name(name):
    """
    Simplify PCI device name from lspci output.

    lspci device names often contain chip codenames followed by the product
    name in brackets, e.g.:
    - 'GA102 [GeForce RTX 3090]' → 'GeForce RTX 3090'
    - 'TU104 [GeForce RTX 2080 SUPER]' → 'GeForce RTX 2080 SUPER'
    - 'GP107 [GeForce GTX 1050 Ti Rev. A]' → 'GeForce GTX 1050 Ti Rev. A'
    - 'Chip [PartA] [PartB]' → 'PartA PartB'  (multiple brackets, concatenated)
    - 'Ascend 310P3' → 'Ascend 310P3'  (no brackets, kept as-is)
    - 'Device 3686' → 'Device 3686'  (no brackets, kept as-is)

    Args:
        name: Device name string from lspci

    Returns:
        str: Simplified device name
    """
    if not name:
        return name
    matches = re.findall(r'\[([^\]]+)]', name)
    if matches:
        return ' '.join(m.strip() for m in matches)
    return name


def normalize_pci_address(pci_address):
    """
    Normalize PCI address to standard format for exact matching.

    Handles various input formats:
    - "00000000:3B:00.0" -> "0000:3b:00.0"
    - "0000:3B:00.0" -> "0000:3b:00.0"
    - "3B:00.0" -> "0000:3b:00.0"
    - "0x0000:0x3b:0x00.0x0" -> "0000:3b:00.0"

    Args:
        pci_address: PCI address string in any format

    Returns:
        str: Normalized PCI address in format "xxxx:xx:xx.x" (lowercase), or None if invalid
    """
    if not pci_address:
        return None

    # Convert to string and strip whitespace
    addr = str(pci_address).strip()
    if not addr:
        return None

    match = re.search(
        r'(?:0x)?[0-9a-fA-F]{1,8}:(?:0x)?[0-9a-fA-F]{1,2}:'
        r'(?:0x)?[0-9a-fA-F]{1,2}\.(?:0x)?[0-9a-fA-F]+',
        addr)
    if match:
        addr = match.group(0)

    # Remove 0x prefixes if present
    addr = re.sub(r'0x', '', addr, flags=re.IGNORECASE)

    # Parse components
    parts = addr.split(':')
    if len(parts) == 2:
        # Format: "3B:00.0" -> bus:slot.function (domain defaults to "0000")
        # Check if parts[1] contains '.' to distinguish from invalid formats
        if '.' in parts[1]:
            domain = '0000'
            bus = parts[0]
            bus_slot_func = parts[1]  # This is slot.function
        else:
            # Invalid format
            return None
    elif len(parts) == 3:
        # Format: "0000:3B:00.0" or "00000000:3B:00.0"
        domain = parts[0]
        bus = parts[1]
        bus_slot_func = parts[2]  # This is slot.function
    else:
        # Invalid format
        return None

    # Normalize domain (remove leading zeros, pad to 4 chars)
    try:
        domain_num = int(domain, 16)
        domain = format(domain_num, '04x')
    except ValueError:
        return None

    # Handle 8-char domain (e.g., "00000000" -> "0000")
    if len(domain) == 8:
        domain = domain[4:]

    # Parse slot.function
    if '.' not in bus_slot_func:
        return None

    slot, function = bus_slot_func.split('.', 1)

    # Normalize bus, slot, function
    try:
        bus_num = int(bus, 16)
        slot_num = int(slot, 16)
        func_num = int(function, 16)
        bus = format(bus_num, '02x')
        slot = format(slot_num, '02x')
        function = format(func_num, 'x')
    except ValueError:
        return None

    return "%s:%s:%s.%s" % (domain, bus, slot, function)


def get_cached_device(pci_address):
    return _pci_device_cache.get(pci_address)


def clear_pci_cache():
    _pci_device_cache.clear()


def update_cache_devices(devices_dict):
    _pci_device_cache.clear()
    _pci_device_cache.update(devices_dict)


def fmt_pci_address(pci_device):
    # type: (dict) -> str
    domain = pci_device['domain'] if 'domain' in pci_device else 0
    return "%s:%s:%s.%s" % (format(domain, '04x'),
                            format(pci_device['bus'], '02x'),
                            format(pci_device['slot'], '02x'),
                            format(pci_device['function'], 'x'))


PCI_IOV_NUM_BAR = 6
PCI_BASE_ADDRESS_MEM_TYPE_MASK = 0x06
PCI_BASE_ADDRESS_MEM_TYPE_32 = 0x00  # 32 bit address
PCI_BASE_ADDRESS_MEM_TYPE_64 = 0x04  # 64 bit address
PCI_DEVICES_ROOT = "/sys/bus/pci/devices"

DEFAULT_PCDPCIMMIO64SIZE_ON_32BIT = 0x100000000
DEFAULT_PCDPCIMMIO64SIZE_MIN_SIZE = 0x800000000
DEFAULT_ARM_PCI_MMIO64_SIZE = 0x8000000000
max_addressable_memory_32bit = 2 * 1024 * 1024
max_addressable_memory_64bit = 2 * 1024 * 1024


class MemoryResource:
    def __init__(self, start, end, flags, path):
        self.start = start
        self.end = end
        self.flags = flags
        self.path = path

    def __str__(self):
        return "start: %s, end: %s, flags: %s, path: %s" % (self.start, self.end, self.flags, self.path)

    def __repr__(self):
        return str(self)


def calc_next_power_of_2(n):
    """
    Calculate the next power of 2 for a given number.

    :param n: The input number
    :return: The next power of 2
    """
    n -= 1
    n |= n >> 1
    n |= n >> 2
    n |= n >> 4
    n |= n >> 8
    n |= n >> 16
    n |= n >> 32
    n += 1
    return n


def need_config_pcimmio():
    if platform.machine() == 'aarch64':
        if max_addressable_memory_64bit <= DEFAULT_ARM_PCI_MMIO64_SIZE:
            logger.info("max_addressable_memory %s is less than DEFAULT_ARM_PCI_MMIO64_SIZE %s" %
                        (max_addressable_memory_64bit, DEFAULT_ARM_PCI_MMIO64_SIZE))
            return False
    else:
        if max_addressable_memory_64bit <= DEFAULT_PCDPCIMMIO64SIZE_ON_32BIT:
            logger.info("max_addressable_memory %s is less than DEFAULT_PCDPCIMMIO64SIZE_ON_32BIT %s" %
                        (max_addressable_memory_64bit, DEFAULT_PCDPCIMMIO64SIZE_ON_32BIT))
            return False

    return True


def get_bars_max_addressable_memory():
    if max_addressable_memory_64bit is None:
        logger.warn(
            "max_addressable_memory is None, please reconnect host and try again")

    if platform.machine() == 'aarch64':
        return "%sG" % sizeunit.Byte.toGigaByte(calc_next_power_of_2(max_addressable_memory_64bit))

    if max_addressable_memory_64bit < DEFAULT_PCDPCIMMIO64SIZE_MIN_SIZE:
        return DEFAULT_PCDPCIMMIO64SIZE_MIN_SIZE // 1024 // 1024

    return max_addressable_memory_64bit // 1024 // 1024


def calculate_max_addressable_memory(pci_devices):
    """
    Calculate max addressable memory for all GPU devices.

    Optimized: Batch query all GPU information once, then filter by PCI address.
    Uses gpu.get_all_gpu_infos_by_pci() for efficient batch processing.
    """
    global max_addressable_memory_32bit
    global max_addressable_memory_64bit
    max32bit = 2 * 1024 * 1024
    max64bit = 2 * 1024 * 1024

    # Batch query all GPU information once (optimized approach)
    # Uses unified gpu.get_all_gpu_infos_by_pci() interface for efficient batch processing
    try:
        from zstacklib.utils import gpu
        gpu_info_map = gpu.get_all_gpu_infos_by_pci()
    except Exception as e:
        logger.debug("Failed to batch query GPU infos: %s" % str(e))
        gpu_info_map = {}

    for dev in pci_devices:
        # Normalize PCI address for lookup
        normalized_pci = normalize_pci_address(dev.pciDeviceAddress)
        if not normalized_pci:
            continue

        # Check if this PCI address is in the GPU info map (O(1) lookup)
        if normalized_pci not in gpu_info_map:
            continue

        mem_size_32bit, mem_size_64bit = get_total_addressable_memory(
            get_pci_resources(dev.pciDeviceAddress))
        logger.info("get pci device: %s, name: %s, max addressable memory: %s" %
                    (dev.pciDeviceAddress, dev.name, mem_size_64bit))
        max32bit += calc_next_power_of_2(mem_size_32bit)
        max64bit += calc_next_power_of_2(mem_size_64bit)

    max_addressable_memory_32bit = max32bit * 2
    max_addressable_memory_64bit = max64bit
    logger.info("calculate max addressable memory: 32bit: "
                "%s, 64bit: %s", max_addressable_memory_32bit, max_addressable_memory_64bit)


def get_total_addressable_memory(resources):
    # type: (dict) -> (int, int)
    """
        Calculate the total addressable memory for 32-bit and 64-bit addresses.

        :param resources: A dictionary of memory resources
        :return: A tuple containing the 32-bit and 64-bit addressable memory sizes
    """
    mem_size_32bit = 0
    mem_size_64bit = 0

    for key in list(resources.keys()):
        # The PCIe spec only defines 5 BARs per device, we're
        # discarding everything after the 5th entry of the resources
        # file, see lspci.c
        if key >= PCI_IOV_NUM_BAR:
            break

        region = resources[key]
        flags = region.flags & PCI_BASE_ADDRESS_MEM_TYPE_MASK
        mem_size = (region.end - region.start) + 1

        if flags == PCI_BASE_ADDRESS_MEM_TYPE_32:
            mem_size_32bit += mem_size
        if flags == PCI_BASE_ADDRESS_MEM_TYPE_64:
            mem_size_64bit += mem_size

    return mem_size_32bit, mem_size_64bit


def get_pci_resources(device_address):
    device_path = os.path.join(PCI_DEVICES_ROOT, device_address)
    return parse_resources(device_path)


def parse_resources(device_path):
    resources = {}
    try:
        with open(os.path.join(device_path, "resource"), "r") as f:
            for i, line in enumerate(f):
                start, end, flags = [int(x, 16) for x in line.strip().split()]
                if start != 0 or end != 0:
                    resources[i] = MemoryResource(
                        start, end, flags, os.path.join(device_path, "resource"))
    except Exception as e:
        logger.warn(linux.get_exception_stacktrace())
        logger.warn("Error parsing resources for %s: %s" %
                    (device_path, str(e)))

    logger.info("get pci device[path: %s],resources: %s" %
                (device_path, resources))
    return resources


def _query_pci_info_by_qmp(vm_uuid, timeout=None):
    """Execute QEMU monitor command and return output."""
    if timeout is None:
        cmd = 'virsh qemu-monitor-command {} --hmp "info pci"'.format(vm_uuid)
        return bash_roe(cmd)
    if type(timeout) is not int or timeout != 5:
        raise ValueError('strict QMP timeout must be exactly five seconds')
    import signal
    import subprocess
    from zstacklib.utils import shell
    deadline = time.monotonic() + timeout
    process = shell.get_process(['/usr/bin/timeout', '--signal=KILL', '5s', 'virsh',
                                 'qemu-monitor-command', vm_uuid, '--hmp', 'info pci'])
    try:
        output, error = process.communicate(timeout=max(0, deadline - time.monotonic() - 0.1))
        return process.returncode, output.decode('utf-8', 'replace'), error.decode('utf-8', 'replace')
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
        output = exc.output or b''
        return process.returncode, output.decode('utf-8', 'replace'), \
            'strict QMP deadline exceeded; process pid=%s exitCode=%s' % (process.pid, process.returncode)
    finally:
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()


def _parse_pci_info_by_qmp_output(qemu_output, aliases, alias_to_host, mapping_builder):
    """Parse QEMU output and build device mapping."""
    mapping = {}
    lines = qemu_output.strip().split('\n')
    current_device_info = None
    
    for line in lines:
        line = line.strip()
        
        # Match bus/device/function line
        device_match = re.match(r'^Bus\s+(\d+),\s+device\s+(\d+),\s+function\s+(\d+):', line)
        if device_match:
            current_device_info = (int(device_match.group(1)), 
                                 int(device_match.group(2)), 
                                 int(device_match.group(3)))
            continue
        
        # Match alias and build mapping
        if current_device_info:
            for alias in aliases:
                if '"{}"'.format(alias) in line:
                    key, value = mapping_builder(current_device_info, alias, alias_to_host)
                    mapping[key] = value
                    current_device_info = None  # Reset after successful match
                    break
    
    return mapping


def _query_vm_pci_address_mapping(vm_uuid, aliases, alias_to_host, mapping_builder):
    """
    Query QEMU monitor and build device mapping with retry mechanism.
    
    Args:
        vm_uuid: VM UUID
        aliases: List of device aliases
        alias_to_host: Dict mapping alias to host device identifier
        mapping_builder: Function to build mapping entry (current_device_info, alias, alias_to_host) -> (key, value)
    
    Returns:
        Dict mapping VM device addresses to host device identifiers
    """
    if not aliases:
        return {}

    max_retries = 3
    retry_interval = 2
    mapping = {}

    for attempt in range(max_retries):
        try:
            r, qemu_output, e = _query_pci_info_by_qmp(vm_uuid)

            if r != 0:
                logger.debug("Failed to execute qemu-monitor-command for VM {} on attempt {}: {}".format(
                    vm_uuid, attempt + 1, e))
            else:
                new_entries = _parse_pci_info_by_qmp_output(qemu_output, aliases, alias_to_host, mapping_builder)
                mapping.update(new_entries)

                if len(mapping) >= len(aliases):
                    logger.debug("Successfully got all {}/{} PCI mappings for VM {} on attempt {}".format(
                        len(mapping), len(aliases), vm_uuid, attempt + 1))
                    return mapping
                else:
                    logger.debug("Got {}/{} PCI mappings for VM {} on attempt {}, will retry".format(
                        len(mapping), len(aliases), vm_uuid, attempt + 1))

        except Exception as ex:
            logger.debug("Error querying info pci for VM {} on attempt {}: {}".format(
                vm_uuid, attempt + 1, str(ex)))

        # Wait before next retry (except for last attempt)
        if attempt < max_retries - 1:
            logger.debug("Waiting {} seconds before retry {} for VM {}".format(
                retry_interval, attempt + 2, vm_uuid))
            time.sleep(retry_interval)

    if mapping:
        logger.warn("Partial PCI mapping for VM {}: got {}/{} after {} attempts".format(
            vm_uuid, len(mapping), len(aliases), max_retries))
        return mapping

    logger.warn("Failed to get PCI mapping for VM {} after {} attempts".format(
        vm_uuid, max_retries))
    return {}



def normalize_strict_pci_address(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]', value):
        raise ValueError('invalid complete PCI BDF')
    domain, bus, slot, function = re.split(r'[:.]', value)
    if int(slot, 16) > 31:
        raise ValueError('PCI slot out of range')
    return '%04x:%02x:%02x.%x' % (int(domain, 16), int(bus, 16), int(slot, 16), int(function, 16))


def _strict_xml_pci_address(element):
    if element is None:
        raise ValueError('missing active XML PCI address')
    fields = []
    for key, maximum in (('domain', 65535), ('bus', 255), ('slot', 31), ('function', 7)):
        value = element.get(key)
        if not isinstance(value, str) or not re.fullmatch(r'0x[0-9a-fA-F]+', value):
            raise ValueError('invalid active XML PCI address field')
        number = int(value, 16)
        if number > maximum:
            raise ValueError('active XML PCI address out of range')
        fields.append(number)
    return '%04x:%02x:%02x.%x' % tuple(fields)


def get_strict_pci_passthrough_observation(vm_dom):
    if not vm_dom.isActive() or type(vm_dom.ID()) is not int or vm_dom.ID() < 0:
        raise ValueError('strict PCI observation requires active runtime')
    xml = vm_dom.XMLDesc()
    if not isinstance(xml, str) or len(xml.encode('utf-8')) > 1048576:
        raise ValueError('invalid/oversized active domain XML')
    tree = ET.fromstring(xml)
    expected, hosts, guests = {}, set(), set()
    for device in tree.findall('./devices/hostdev'):
        if device.get('type') != 'pci':
            raise ValueError('unsupported non-PCI hostdev in strict allocation')
        alias_element = device.find('alias')
        alias = None if alias_element is None else alias_element.get('name')
        if not alias:
            raise ValueError('missing PCI hostdev alias')
        host = _strict_xml_pci_address(device.find('source/address'))
        guest = _strict_xml_pci_address(device.find('address'))
        if alias in expected or host in hosts or guest in guests:
            raise ValueError('duplicate active XML alias/PCI BDF')
        expected[alias] = {'alias': alias, 'hostPciAddress': host, 'guestPciAddress': guest}
        hosts.add(host)
        guests.add(guest)
    if not expected:
        raise ValueError('strict PCI observation has no hostdev devices')
    runtime_id, vm_uuid, vm_name = vm_dom.ID(), vm_dom.UUIDString(), vm_dom.name()
    # One complete observation: never merge partial mappings across retries.
    rc, output, error = _query_pci_info_by_qmp(vm_uuid, timeout=5)
    if rc != 0 or not isinstance(output, str) or len(output.encode('utf-8')) > 1048576:
        raise ValueError('strict QMP query failed: rc=%s %s' % (rc, str(error)[:4096]))
    observed, addresses, current = {}, set(), None
    for line in output.splitlines():
        match = re.match(r'^\s*Bus\s+(\d+),\s+device\s+(\d+),\s+function\s+(\d+):', line)
        if match:
            bus, slot, function = [int(value) for value in match.groups()]
            if bus > 255 or slot > 31 or function > 7:
                raise ValueError('QMP PCI address out of range')
            current = '0000:%02x:%02x.%x' % (bus, slot, function)
        alias_match = re.search(r'\bid\s+"([^"]+)"', line)
        if alias_match and alias_match.group(1) in expected:
            alias = alias_match.group(1)
            if current is None:
                raise ValueError('QMP alias missing guest address')
            if alias in observed or current in addresses:
                raise ValueError('duplicate raw QMP alias/guest BDF')
            if expected[alias]['guestPciAddress'] != current:
                raise ValueError('QMP guest address differs from active XML')
            observed[alias] = expected[alias]
            addresses.add(current)
    if set(observed) != set(expected):
        raise ValueError('incomplete single QMP observation')
    if not vm_dom.isActive() or (vm_dom.ID(), vm_dom.UUIDString(), vm_dom.name()) != (runtime_id, vm_uuid, vm_name):
        raise ValueError('active runtime changed during QMP observation')
    return {'vmUuid': vm_uuid, 'name': vm_name, 'runtimeId': runtime_id,
            'devices': sorted(observed.values(), key=lambda item: item['alias'])}


def get_pci_passthrough_mapping(vm_dom):
    vm_uuid = vm_dom.UUIDString()
    xml_tree = ET.fromstring(vm_dom.XMLDesc())

    # Collect alias to host PCI mapping in one pass
    alias_to_host = {}
    aliases = []

    devices = xml_tree.find('devices')
    if devices is None:
        return {}

    for hostdev in devices.findall('hostdev'):
        if hostdev.get('type') != 'pci':
            continue
            
        alias_elem = hostdev.find('alias')
        if alias_elem is not None:
            alias_name = alias_elem.get('name')
            aliases.append(alias_name)
            
            # Get host PCI address
            source_address = hostdev.find('source/address')
            host_domain = source_address.get('domain').replace('0x', '')
            host_bus = source_address.get('bus').replace('0x', '')
            host_slot = source_address.get('slot').replace('0x', '')
            host_function = source_address.get('function').replace('0x', '')
            host_pci_address = "{}:{}:{}.{}".format(
                host_domain, host_bus, host_slot, host_function)
            alias_to_host[alias_name] = host_pci_address
    
    if not aliases:
        return {}

    # Query actual PCI addresses inside VM
    def build_pci_mapping(current_device_info, alias, alias_to_host):
        bus, device, function = current_device_info
        vm_pci_address = "{:04x}:{:02x}:{:02x}.{:x}".format(0, bus, device, function)
        host_pci_address = alias_to_host[alias]
        return vm_pci_address, host_pci_address

    return _query_vm_pci_address_mapping(
        vm_uuid, aliases, alias_to_host, build_pci_mapping)


def get_mdev_passthrough_mapping(vm_dom):
    vm_uuid = vm_dom.UUIDString()
    xml_tree = ET.fromstring(vm_dom.XMLDesc())

    # Collect alias to host mdev mapping in one pass
    alias_to_host = {}
    aliases = []

    devices = xml_tree.find('devices')
    if devices is None:
        return {}

    for hostdev in devices.findall('hostdev'):
        if hostdev.get('type') != 'mdev':
            continue

        alias_elem = hostdev.find('alias')
        if alias_elem is not None:
            alias_name = alias_elem.get('name')
            aliases.append(alias_name)

            # Get host mdev UUID
            source_address = hostdev.find('source/address')
            mdev_uuid = source_address.get('uuid').replace('-', '')
            alias_to_host[alias_name] = mdev_uuid

    if not aliases:
        return {}

    # Query actual mdev addresses inside VM
    def build_mdev_mapping(current_device_info, alias, alias_to_host):
        bus, device, function = current_device_info
        vm_mdev_address = "{:04x}:{:02x}:{:02x}.{:x}".format(0, bus, device, function)
        host_mdev_uuid = alias_to_host[alias]
        return host_mdev_uuid, vm_mdev_address

    return _query_vm_pci_address_mapping(
        vm_uuid, aliases, alias_to_host, build_mdev_mapping)


def get_vm_pci_device_address_by_host_address(vm_dom, host_address):
    pci_mapping = get_pci_passthrough_mapping(vm_dom)
    host_to_vm_mapping = {v: k for k, v in pci_mapping.items()}
    return host_to_vm_mapping.get(host_address)


def get_pci_device_ids():
    # Get IDs using -Dmmnv (without second 'n' to avoid truncation)
    return bash_roe("lspci -Dmmnv")


def get_pci_device_names():
    # Get names using -Dmmv (without 'nn' to get full names)
    return bash_roe("lspci -Dmmv")


def collect_pci_devices_with_dependencies(pciDeviceAddress):
    devices = []
    base_address = pciDeviceAddress.rsplit('.', 1)[0]
    r, o, e = bash_roe("lspci -s %s" % base_address)
    if r != 0:
        return devices

    for line in o.splitlines():
        device = line.split()[0]
        full_address = "{}:{}".format(pciDeviceAddress.split(':')[0], device)
        if full_address != pciDeviceAddress:
            devices.append(full_address)
    return devices


class PciDeviceOps(object):
    """
    PCI device operations structure (Linux kernel style).

    Similar to pci_driver in Linux kernel, this defines operations for handling
    specific types of PCI devices (e.g., GPU, Ethernet, etc.).

    Reference: Linux kernel pci_driver structure
    """

    def __init__(self, probe, init, prepare=None):
        """
        Initialize PCI device operations.

        Args:
            probe: Function (pci_device_to, context: PciDeviceProcessingContext) -> bool
                Probe function to match devices (like pci_driver.id_table matching).
                Returns True if this ops should handle the device.
                Context is available so probe can use prepared data (e.g. gpu_info_map).
            init: Function (pci_device_to, context: PciDeviceProcessingContext) -> bool
                Initialize function to process the device (like pci_driver.probe).
                Returns True if device was processed.
            prepare: Function (context: PciDeviceProcessingContext) -> callable or None, optional
                Prepare function called once before processing devices (like driver init).
                Can modify context to add prepared data (e.g., gpu_info_map).
                Can return a post-prepare hook (device_list, context) -> None to refine capabilities.
        """
        self.probe = probe
        self.init = init
        self.prepare = prepare


def pci_register_device_ops(ops):
    """
    Register PCI device operations (Linux kernel style).

    Similar to pci_register_driver() in Linux kernel, this registers operations
    for handling specific types of PCI devices.

    Architecture (similar to Linux kernel device driver model):
    1. Abstract layer: Generic PCI capabilities are detected in main loop
    2. Registry layer: Device ops are registered here (like pci_register_driver)
    3. Device-specific layer: Each ops handles its device type (like pci_driver.probe)

    Args:
        ops: PciDeviceOps object containing probe, init, and optional prepare functions

    Reference: Linux kernel pci_register_driver()
    """
    if not isinstance(ops, PciDeviceOps):
        raise TypeError("ops must be a PciDeviceOps instance")
    _pci_device_ops_list.append(ops)


# Backward compatibility: keep old function name as alias
def register_pci_device_processor(matcher_func, processor_func, prepare_func=None):
    """
    Register a PCI device processor (deprecated, use pci_register_device_ops instead).

    This is kept for backward compatibility. New code should use pci_register_device_ops()
    with a PciDeviceOps object.
    """
    ops = PciDeviceOps(probe=matcher_func,
                       init=processor_func, prepare=prepare_func)
    pci_register_device_ops(ops)


def pci_device_prepare_chain(context):
    """
    Call prepare hooks of all registered device operations (Linux kernel style).

    Similar to calling driver init functions before device probing in Linux kernel.
    This allows device ops to do batch preparation (e.g., collect GPU info map)
    before individual device processing begins.

    Device ops can also register post-prepare hooks to refine capabilities
    (e.g., update sriov detection with GPU info map).

    Args:
        context: PciDeviceProcessingContext object that ops can modify

    Returns:
        list: List of post-prepare hooks (device_list, context) -> None

    Reference: Linux kernel driver initialization before device probing
    """
    post_prepare_hooks = []
    for ops in _pci_device_ops_list:
        if ops.prepare:
            try:
                result = ops.prepare(context)
                # If prepare function returns a post-prepare hook, collect it
                if result and callable(result):
                    post_prepare_hooks.append(result)
            except Exception as e:
                logger.debug("PCI device ops prepare error: %s" % str(e))
                continue
    return post_prepare_hooks


# Backward compatibility: keep old function name as alias
def prepare_pci_device_processors(context):
    """
    Call prepare functions of all registered processors (deprecated, use pci_device_prepare_chain instead).
    """
    return pci_device_prepare_chain(context)


def pci_device_probe(pci_device_to, context):
    """
    Probe PCI device to find matching device operations (Linux kernel style).

    Similar to pci_device_probe() in Linux kernel, this probes the device
    by calling probe() functions of registered device operations until a match is found.

    Flow (similar to Linux kernel device driver matching):
    1. Probe device by calling ops.probe() of each registered ops (like pci_driver.id_table matching)
    2. If match found, call ops.init() to initialize the device (like pci_driver.probe)
    3. Device ops handles: type refinement, virtStatus, addon info, etc.

    Args:
        pci_device_to: PciDeviceTO object (with _pci_capabilities set)
        context: PciDeviceProcessingContext object containing processing context

    Returns:
        bool: True if device was processed by a registered ops, False otherwise

    Reference: Linux kernel pci_device_probe() and pci_driver.probe()
    """
    if not pci_device_to:
        return False

    # Try each registered ops in order (like Linux kernel driver matching)
    for ops in _pci_device_ops_list:
        try:
            # Probe: check if this ops should handle the device (like pci_driver.id_table matching)
            if ops.probe(pci_device_to, context):
                # Init: process the device (like pci_driver.probe)
                if ops.init(pci_device_to, context):
                    return True
        except Exception as e:
            logger.debug("PCI device ops error: %s" % str(e))
            continue

    return False


# Backward compatibility: keep old function name as alias
def enrich_pci_device(pci_device_to, context):
    """
    Enrich PCI device by finding and calling the appropriate processor (deprecated, use pci_device_probe instead).
    """
    return pci_device_probe(pci_device_to, context)
