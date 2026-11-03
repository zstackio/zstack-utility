import subprocess
import threading

import pytest

from zstacklib.utils import hccn


def test_collects_pci_serial_and_address_before_passthrough():
    def output(*command):
        if command == ("npu-smi", "info", "-l"):
            return "Total Count: 2\nNPU ID: 0\nNPU ID: 7\n"
        if command[:4] == ("npu-smi", "info", "-t", "board"):
            number = command[-1]
            return ("Serial Number : card-" + number + "\nPCIe Bus Info : "
                    + ("0000:01:00.0" if number == "0" else "0000:42:00.0") + "\n")
        if command[3] == "-link":
            return "link status: UP\n"
        if command[2] == "0":
            return "ipaddr:172.20.9.79\nnetmask:255.255.0.0\n"
        return "ipaddr:172.20.9.86\nnetmask:255.255.0.0\n"

    assert hccn.collect_devices(output) == [
        {"pciDeviceAddress": "0000:01:00.0", "serialNumber": "card-0",
         "address": "172.20.9.79", "netmask": "255.255.0.0", "linkStatus": "UP"},
        {"pciDeviceAddress": "0000:42:00.0", "serialNumber": "card-7",
         "address": "172.20.9.86", "netmask": "255.255.0.0", "linkStatus": "UP"},
    ]


def test_missing_address_is_reported_for_control_plane_rejection():
    def output(*command):
        if command == ("npu-smi", "info", "-l"):
            return "NPU ID: 7\n"
        if command[0] == "npu-smi":
            return "Serial Number : card-7\nPCIe Bus Info : 0000:42:00.0\n"
        raise subprocess.CalledProcessError(1, command, output="no ip was preset there")

    assert hccn.collect_devices(output)[0]["address"] is None


def test_hccn_command_failure_is_not_treated_as_missing_address():
    def output(*command):
        if command == ("npu-smi", "info", "-l"):
            return "NPU ID: 7\n"
        if command[0] == "npu-smi":
            return "Serial Number : card-7\nPCIe Bus Info : 0000:42:00.0\n"
        raise subprocess.CalledProcessError(1, command, output="failed to read device")

    with pytest.raises(subprocess.CalledProcessError):
        hccn.collect_devices(output)


def test_duplicate_addresses_are_rejected():
    def output(*command):
        if command == ("npu-smi", "info", "-l"):
            return "NPU ID: 0\nNPU ID: 7\n"
        if command[0] == "npu-smi":
            return ("Serial Number : card-" + command[-1] + "\nPCIe Bus Info : 0000:"
                    + ("01" if command[-1] == "0" else "42") + ":00.0\n")
        return "ipaddr:172.20.9.86\nnetmask:255.255.0.0\n"

    with pytest.raises(ValueError, match="duplicate host NPU HCCN address"):
        hccn.collect_devices(output)


def _single_card(link):
    def output(*command):
        if command == ("npu-smi", "info", "-l"):
            return "NPU ID: 3\n"
        if command[0] == "npu-smi":
            return "Serial Number : card-3\nPCIe Bus Info : 0000:82:00.0\n"
        if command[3] == "-link":
            return link(command)
        return "ipaddr:172.20.9.59\nnetmask:255.255.0.0\n"
    return output


def test_down_link_is_reported_so_control_plane_skips_the_card():
    # A mapped card whose port is down passes the address checks but fails HCCL with EI0009.
    devices = hccn.collect_devices(_single_card(lambda command: "link status: DOWN\n"))
    assert devices[0]["address"] == "172.20.9.59"
    assert devices[0]["linkStatus"] == "DOWN"


def test_link_query_failure_keeps_the_survey_and_marks_status_unknown():
    def fail(command):
        raise subprocess.CalledProcessError(1, command, output="device busy")

    assert hccn.collect_devices(_single_card(fail))[0]["linkStatus"] == "UNKNOWN"
    assert hccn.collect_devices(_single_card(lambda command: "unexpected\n"))[0]["linkStatus"] == "UNKNOWN"


def test_only_up_and_down_are_reported_as_link_states():
    # The control plane only trusts UP; any other word must not look like a known state.
    assert hccn.collect_devices(_single_card(lambda command: "link status: ERROR\n"))[0]["linkStatus"] == "UNKNOWN"


def test_link_tool_that_cannot_start_does_not_abort_the_survey():
    def missing(command):
        raise FileNotFoundError(command[0])

    assert hccn.collect_devices(_single_card(missing))[0]["linkStatus"] == "UNKNOWN"


def test_link_queries_run_together_so_slow_cards_do_not_add_up():
    # The capacity page surveys on every change; one timeout per card in sequence would stall it.
    ids = ["0", "1", "2", "3"]
    together = threading.Barrier(len(ids), timeout=5)

    def output(*command):
        if command == ("npu-smi", "info", "-l"):
            return "".join("NPU ID: %s\n" % i for i in ids)
        if command[0] == "npu-smi":
            return "Serial Number : card-%s\nPCIe Bus Info : 0000:0%s:00.0\n" % (command[-1], command[-1])
        if command[3] == "-link":
            together.wait()
            return "link status: UP\n"
        return "ipaddr:172.20.9.%s\nnetmask:255.255.0.0\n" % (60 + int(command[2]))

    assert [d["linkStatus"] for d in hccn.collect_devices(output)] == ["UP"] * len(ids)


def test_unreadable_npu_list_keeps_the_driver_message():
    def output(*command):
        raise subprocess.CalledProcessError(191, command, output="dcmi module initialize failed. ret is -8001\n")

    # Callers may still catch CalledProcessError and read its fields; only the message gains the driver text.
    with pytest.raises(subprocess.CalledProcessError, match="191.*dcmi module initialize failed") as raised:
        hccn.collect_devices(output)
    assert raised.value.returncode == 191
    assert raised.value.output.startswith("dcmi module initialize failed")
