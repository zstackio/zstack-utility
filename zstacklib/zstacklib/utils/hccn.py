import ipaddress
import re
import subprocess
import threading
from collections import Counter


_SURVEY_LOCK = threading.Lock()


def _command_output(*command):
    return subprocess.check_output(command, stderr=subprocess.STDOUT, text=True, timeout=5)


def _field(output, name):
    values = re.findall(r"^[ \t]*" + re.escape(name) + r"[ \t]*:[ \t]*([^\r\n]*)\r?$", output, re.MULTILINE)
    if len(values) > 1:
        raise ValueError("ambiguous NPU field: " + name)
    return values[0].strip() if values else None


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


def _physical_chip_ids(output, npu_id, count):
    result = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0] != npu_id or not fields[1].isdigit() or not fields[3].isdigit():
            continue
        chip, physical = int(fields[1]), int(fields[3])
        if chip in result or physical in result.values():
            raise ValueError("duplicate host NPU chip physical mapping")
        result[chip] = physical
    if set(result) != set(range(count)):
        raise ValueError("incomplete host NPU chip physical mapping")
    return result


def _identities(command_output, ids):
    devices, serials, pci_addresses, physical_ids = [], set(), set(), set()
    board_serials = set()
    mapping = None
    for device_id in ids:
        board = command_output("npu-smi", "info", "-t", "board", "-i", device_id)
        serial = _field(board, "Serial Number")
        if serial in board_serials:
            raise ValueError("duplicate host NPU serial number on different cards")
        board_serials.add(serial)
        count_text = _field(board, "Chip Count")
        if count_text is not None and (not count_text.isdigit() or not 1 <= int(count_text) <= 16):
            raise ValueError("invalid host NPU chip count")
        count = int(count_text) if count_text is not None else 1
        if count > 1:
            if mapping is None:
                mapping = command_output("npu-smi", "info", "-m")
            chips = _physical_chip_ids(mapping, device_id, count)
        else:
            chips = {None: int(device_id)}
        for chip, physical in chips.items():
            chip_board = board if chip is None else command_output(
                "npu-smi", "info", "-t", "board", "-i", device_id, "-c", str(chip))
            pci = _field(chip_board, "PCIe Bus Info")
            if not serial or not pci or not re.fullmatch(
                    r"[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]", pci):
                raise ValueError("NPU board has no valid serial number or PCI address")
            pci = pci.lower()
            if (serial, chip) in serials or pci in pci_addresses:
                raise ValueError("duplicate host NPU serial number or PCI address")
            if physical in physical_ids:
                raise ValueError("duplicate host NPU physical ID")
            serials.add((serial, chip))
            pci_addresses.add(pci)
            physical_ids.add(physical)
            device = {"pciDeviceAddress": pci, "serialNumber": serial}
            if chip is not None:
                device.update(npuId=int(device_id), chipId=chip, physicalId=physical)
            devices.append((device, str(physical)))
    return devices


def collect_devices(command_output=_command_output):
    """Read device addresses while the host driver still owns the NPUs."""
    with _SURVEY_LOCK:
        return _collect_devices(command_output)


def _network_address(output, prefix="", network="HCCN"):
    address = _field(output, prefix + "ipaddr")
    netmask = _field(output, prefix + "netmask")
    if bool(address) != bool(netmask):
        raise ValueError("incomplete host NPU %s address" % network)
    if address:
        parsed = ipaddress.IPv4Address(address)
        if parsed.is_unspecified or parsed.is_loopback or parsed.is_multicast or parsed.is_link_local:
            raise ValueError("host NPU has no usable %s address" % network)
        address = str(parsed)
        netmask = str(ipaddress.IPv4Network("0.0.0.0/" + netmask).netmask)
        if netmask == "0.0.0.0":
            raise ValueError("host NPU has no usable %s netmask" % network)
    return address, netmask


def _probe_error(error):
    return (str(error) + ": " + str(getattr(error, "output", "") or "").strip())[:1000]


def _topology_number(output, field, minimum=0):
    value = _field(output, field)
    if value is None or not value.isdecimal() or not minimum <= int(value) <= 0xffffffff:
        raise ValueError("invalid HCCS %s: %s" % (field, value))
    return int(value)


def _hccs_observation(command_output, device, device_id):
    try:
        vnic = command_output("/usr/local/Ascend/driver/tools/hccn_tool", "-i", device_id, "-vnic", "-g")
        address, netmask = _network_address(vnic, "vnic ", "HCCS vNIC")
        if not address:
            raise ValueError("host NPU has no HCCS vNIC address")
        topology = command_output("npu-smi", "info", "-t", "spod-info", "-i", str(device["npuId"]),
                                  "-c", str(device["chipId"]))
        status = (_field(vnic, "vnic link status") or "UNKNOWN").upper()
        return {"address": address, "netmask": netmask,
                "linkStatus": status if status in ("UP", "DOWN") else "UNKNOWN",
                "sdid": _topology_number(topology, "SDID"),
                "superPodId": _topology_number(topology, "Super Pod ID"),
                "superPodSize": _topology_number(topology, "Super Pod Size", 2),
                "serverIndex": _topology_number(topology, "Server Index")}
    except (ValueError, subprocess.SubprocessError, OSError) as error:
        return {"error": _probe_error(error)}


def _roce_address(command_output, device_id):
    try:
        output = command_output("/usr/local/Ascend/driver/tools/hccn_tool", "-i", device_id, "-ip", "-g")
    except subprocess.CalledProcessError as error:
        if not re.search(r"\bno ip (?:was )?preset\b", str(error.output).lower()):
            raise
        output = ""
    return _network_address(output)


def _collect_devices(command_output):
    output = _list_npus(command_output)
    ids = re.findall(r"^\s*NPU ID\s*:\s*(\d+)\s*$", output, re.MULTILINE)
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate host NPU ID")
    devices = []
    identities = _identities(command_output, ids)
    for device, device_id in identities:
        if "chipId" in device:
            device["hccs"] = _hccs_observation(command_output, device, device_id)
            device["linkStatus"] = _link_status(command_output, device_id)
            address, netmask = None, None
            if device["linkStatus"] == "UP":
                try:
                    address, netmask = _roce_address(command_output, device_id)
                except (ValueError, subprocess.SubprocessError, OSError) as error:
                    device["roceError"] = _probe_error(error)
        else:
            address, netmask = _roce_address(command_output, device_id)
            device["linkStatus"] = _link_status(command_output, device_id)
        device.update(address=address, netmask=netmask)
        devices.append(device)
    configured = [device["address"] for device in devices if device["address"]]
    duplicates = {address for address, count in Counter(configured).items() if count > 1}
    if any(device["address"] in duplicates and "chipId" not in device for device in devices):
        raise ValueError("duplicate host NPU HCCN address")
    for device in devices:
        if device["address"] in duplicates:
            device.update(address=None, netmask=None, roceError="duplicate host NPU HCCN address")
    hccs = [device["hccs"] for device in devices if "hccs" in device and "error" not in device["hccs"]]
    invalid = set()
    for field in ("address", "sdid"):
        counts = Counter(profile[field] for profile in hccs)
        invalid.update(id(profile) for profile in hccs if counts[profile[field]] > 1)
    for device in devices:
        if id(device.get("hccs")) in invalid:
            device["hccs"] = {"error": "duplicate host NPU HCCS address or SDID"}
    return devices
