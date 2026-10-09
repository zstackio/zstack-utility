import ipaddress
import re
import subprocess


def _command_output(*command):
    return subprocess.check_output(command, stderr=subprocess.STDOUT, text=True, timeout=5)


def _field(output, name):
    match = re.search(r"^\s*" + re.escape(name) + r"\s*:\s*(\S+)\s*$", output, re.MULTILINE)
    return match.group(1) if match else None


def collect_devices(command_output=_command_output):
    """Read device IPs while the host driver still owns the NPUs."""
    output = command_output("npu-smi", "info", "-l")
    ids = re.findall(r"^\s*NPU ID\s*:\s*(\d+)\s*$", output, re.MULTILINE)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate host NPU ID")
    devices = []
    serials = set()
    pci_addresses = set()
    for device_id in ids:
        board = command_output("npu-smi", "info", "-t", "board", "-i", device_id)
        serial = _field(board, "Serial Number")
        pci_address = _field(board, "PCIe Bus Info")
        if not serial or not pci_address or not re.fullmatch(
                r"[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]", pci_address):
            raise ValueError("NPU board has no valid serial number or PCI address")
        pci_address = pci_address.lower()
        if serial in serials or pci_address in pci_addresses:
            raise ValueError("duplicate host NPU serial number or PCI address")
        serials.add(serial)
        pci_addresses.add(pci_address)
        try:
            ip_result = command_output("/usr/local/Ascend/driver/tools/hccn_tool", "-i", device_id, "-ip", "-g")
        except subprocess.CalledProcessError as error:
            if "no ip preset" not in str(error.output).lower():
                raise
            ip_result = ""
        address = _field(ip_result, "ipaddr")
        netmask = _field(ip_result, "netmask")
        if bool(address) != bool(netmask):
            raise ValueError("incomplete host NPU HCCN address")
        if address:
            parsed = ipaddress.IPv4Address(address)
            if parsed.is_unspecified or parsed.is_loopback or parsed.is_multicast or parsed.is_link_local:
                raise ValueError("host NPU has no usable HCCN address")
            address = str(parsed)
            netmask = str(ipaddress.IPv4Network("0.0.0.0/" + netmask).netmask)
            if netmask == "0.0.0.0":
                raise ValueError("host NPU has no usable HCCN netmask")
        devices.append({"pciDeviceAddress": pci_address, "serialNumber": serial,
                        "address": address, "netmask": netmask})
    configured = [device["address"] for device in devices if device["address"]]
    if len(configured) != len(set(configured)):
        raise ValueError("duplicate host NPU HCCN address")
    return devices
