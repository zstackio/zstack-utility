import os

from zstacklib.utils import log, linux
import xml.etree.ElementTree as ET

logger = log.get_logger(__name__)


def is_gpu(type):
    return type in ['GPU_3D_Controller', 'GPU_Video_Controller', 'GPU_Processing_Accelerators']


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
    if max_addressable_memory_64bit <= DEFAULT_PCDPCIMMIO64SIZE_ON_32BIT:
        logger.info("max_addressable_memory %s is less than DEFAULT_PCDPCIMMIO64SIZE_ON_32BIT %s" %
                    (max_addressable_memory_64bit, DEFAULT_PCDPCIMMIO64SIZE_ON_32BIT))
        return False

    return True


def get_bars_max_addressable_memory():
    if max_addressable_memory_64bit is None:
        logger.warn("max_addressable_memory is None, please reconnect host and try again")

    if max_addressable_memory_64bit < DEFAULT_PCDPCIMMIO64SIZE_MIN_SIZE:
        return DEFAULT_PCDPCIMMIO64SIZE_MIN_SIZE / 1024 / 1024

    return max_addressable_memory_64bit / 1024 / 1024


def calculate_max_addressable_memory(pci_devices):
    global max_addressable_memory_32bit
    global max_addressable_memory_64bit
    max32bit = 2 * 1024 * 1024
    max64bit = 2 * 1024 * 1024

    for dev in pci_devices:
        if not is_gpu(dev.type):
            continue

        mem_size_32bit, mem_size_64bit = get_total_addressable_memory(get_pci_resources(dev.pciDeviceAddress))
        logger.info("get pci device: %s, name: %s, max addressable memory: %s" %
                    (dev.pciDeviceAddress, dev.name, mem_size_64bit))
        if max32bit < mem_size_32bit:
            max32bit = mem_size_32bit
        if max64bit < mem_size_64bit:
            max64bit = mem_size_64bit

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

    for key in resources.keys():
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

    mem_size_32bit = calc_next_power_of_2(mem_size_32bit)
    mem_size_64bit = calc_next_power_of_2(mem_size_64bit)

    return mem_size_32bit, mem_size_64bit


def get_pci_resources(device_address):
    device_path = os.path.join(PCI_DEVICES_ROOT, device_address)
    return parse_resources(device_path)


def parse_resources(device_path):
    resources = {}
    try:
        with open(os.path.join(device_path, "resource"), "r") as f:
            for i, line in enumerate(f):
                start, end, flags = map(lambda x: int(x, 16), line.strip().split())
                if start != 0 or end != 0:
                    resources[i] = MemoryResource(start, end, flags, os.path.join(device_path, "resource"))
    except Exception as e:
        logger.warn(linux.get_exception_stacktrace())
        logger.warn("Error parsing resources for %s: %s" % (device_path, str(e)))

    logger.info("get pci device[path: %s],resources: %s" % (device_path, resources))
    return resources

def get_pci_passthrough_mapping(vm_dom):
    pci_mapping = {}
    xml_tree = ET.fromstring(vm_dom.XMLDesc())
    for hostdev in xml_tree.find('devices').findall('hostdev'):
        source_address = hostdev.find('source/address')
        host_domain = source_address.get('domain').replace('0x', '')
        host_bus = source_address.get('bus').replace('0x', '')
        host_slot = source_address.get('slot').replace('0x', '')
        host_function = source_address.get('function').replace('0x', '')
        host_pci_address = "{}:{}:{}.{}".format(host_domain, host_bus, host_slot, host_function)

        vm_address = hostdev.find('address')
        vm_domain = vm_address.get('domain').replace('0x', '')
        vm_bus = vm_address.get('bus').replace('0x', '')
        vm_slot = vm_address.get('slot').replace('0x', '')
        vm_function = vm_address.get('function').replace('0x', '')
        vm_pci_address = "{}:{}:{}.{}".format(vm_domain, vm_bus, vm_slot, vm_function)
        pci_mapping[vm_pci_address] = host_pci_address

    return pci_mapping