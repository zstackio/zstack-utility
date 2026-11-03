import concurrent.futures
import ipaddress
import re
import subprocess


def _command_output(*command):
    return subprocess.check_output(command, stderr=subprocess.STDOUT, text=True, timeout=5)


def _field(output, name):
    match = re.search(r"^\s*" + re.escape(name) + r"\s*:\s*(\S+)\s*$", output, re.MULTILINE)
    return match.group(1) if match else None


def _link_status(command_output, device_id):
    try:
        output = command_output("/usr/local/Ascend/driver/tools/hccn_tool", "-i", device_id, "-link", "-g")
    except (subprocess.SubprocessError, OSError):
        return "UNKNOWN"
    match = re.search(r"^\s*link status\s*:\s*(\S+)\s*$", output, re.MULTILINE | re.IGNORECASE)
    status = match.group(1).upper() if match else None
    return status if status in ("UP", "DOWN") else "UNKNOWN"


class _DriverCommandError(subprocess.CalledProcessError):
    def __str__(self):
        return "%s: %s" % (super().__str__(), str(self.output or "").strip()[:200])


def _list_npus(command_output):
    try:
        return command_output("npu-smi", "info", "-l")
    except subprocess.CalledProcessError as error:
        raise _DriverCommandError(error.returncode, error.cmd, error.output, error.stderr) from error


def collect_devices(command_output=_command_output):
    """Read device IPs while the host driver still owns the NPUs."""
    output = _list_npus(command_output)
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
            if not re.search(r"\bno ip (?:was )?preset\b", str(error.output).lower()):
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
    if devices:
        # Each query can take its full timeout on a card whose port is resetting; run them
        # side by side so one slow card does not multiply the survey time.
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(devices)) as pool:
            statuses = list(pool.map(lambda device_id: _link_status(command_output, device_id), ids))
        for device, status in zip(devices, statuses):
            device["linkStatus"] = status
    return devices
