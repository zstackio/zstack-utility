import subprocess
import threading
import os
import sys
import time

import pytest

from zstacklib.utils import hccn


@pytest.fixture
def slow_npu_smi(tmp_path, monkeypatch):
    tool = tmp_path / "npu-smi"
    tool.write_text("#!%s\nimport os, time\ntime.sleep(float(os.environ['NPU_TEST_DELAY']))\n"
                    "print('Serial Number : card-4')\n" % sys.executable)
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))


def test_board_query_accepts_mcu_recovery_after_five_seconds(slow_npu_smi, monkeypatch):
    monkeypatch.setenv("NPU_TEST_DELAY", "5.2")
    assert "card-4" in hccn._command_output("npu-smi", "info", "-t", "board", "-i", "4", "-c", "1")


def test_stuck_board_query_still_fails_after_ten_seconds(slow_npu_smi, monkeypatch):
    monkeypatch.setenv("NPU_TEST_DELAY", "20")
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        hccn._command_output("npu-smi", "info", "-t", "board", "-i", "7")
    assert raised.value.timeout == 10


def test_hccn_tool_keeps_its_five_second_deadline(monkeypatch):
    def stuck(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    monkeypatch.setattr(subprocess, "check_output", stuck)
    with pytest.raises(subprocess.TimeoutExpired) as raised:
        hccn._command_output("/usr/local/Ascend/driver/tools/hccn_tool", "-i", "4", "-ip", "-g")
    assert raised.value.timeout == 5


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


def test_hccn_queries_do_not_overlap():
    guard = threading.Lock()
    active = [0]
    peak = [0]
    ids = ["0", "1", "2", "3"]
    def output(*command):
        if command == ("npu-smi", "info", "-l"):
            return "".join("NPU ID: %s\n" % i for i in ids)
        if command[0] == "npu-smi":
            return "Serial Number : card-%s\nPCIe Bus Info : 0000:0%s:00.0\n" % (command[-1], command[-1])
        with guard:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        try:
            time.sleep(.01)
            if command[3] == "-link":
                return "link status: UP\n"
            return "ipaddr:172.20.9.%s\nnetmask:255.255.0.0\n" % (60 + int(command[2]))
        finally:
            with guard:
                active[0] -= 1
    assert [device["linkStatus"] for device in hccn.collect_devices(output)] == ["UP"] * len(ids)
    assert peak[0] == 1, "hccn_tool does not support concurrent queries"


def test_unreadable_npu_list_keeps_the_driver_message():
    def output(*command):
        raise subprocess.CalledProcessError(191, command, output="dcmi module initialize failed. ret is -8001\n")

    # Callers may still catch CalledProcessError and read its fields; only the message gains the driver text.
    with pytest.raises(subprocess.CalledProcessError, match=r"191.*dcmi module initialize failed") as raised:
        hccn.collect_devices(output)
    assert raised.value.returncode == 191
    assert raised.value.output.startswith("dcmi module initialize failed")


def _dual_die_output(calls):
    def output(*command):
        calls.append(command)
        if command == ('npu-smi', 'info', '-l'):
            return 'NPU ID: 6\nChip Count: 2\n'
        if command == ('npu-smi', 'info', '-m'):
            return ('NPU ID Chip ID Chip Logic ID Chip Phy-ID Chip Name\n'
                    '6 0 8 12 Ascend910\n6 1 9 13 Ascend910\n6 2 - - Mcu\n')
        if command == ('npu-smi', 'info', '-t', 'board', '-i', '6'):
            return 'Serial Number : card-6\nPCIe Bus Info : 0000:85:00.0\nChip Count : 2\n'
        if command[:6] == ('npu-smi', 'info', '-t', 'board', '-i', '6') and command[6] == '-c':
            return 'PCIe Bus Info : %s\n' % ('0000:85:00.0' if command[7] == '0' else '0000:87:00.0')
        if command[:4] == ('npu-smi', 'info', '-t', 'spod-info'):
            sdid = 39321612 if command[-1] == '0' else 39387149
            return 'SDID : %s\nSuper Pod Size : 96\nSuper Pod ID : 1\nServer Index : 9\n' % sdid
        if command[0].endswith('/hccn_tool'):
            if command[3] == '-vnic':
                address = '192.9.2.187' if command[2] == '12' else '192.9.3.186'
                return 'vnic link status: UP\nvnic ipaddr: %s\nvnic netmask: 255.0.0.0\n' % address
            if command[3] == '-ip':
                return 'ipaddr:10.0.0.%s\nnetmask:255.255.255.0\n' % command[2]
            if command[3] == '-link':
                return 'link status: UP\n'
        raise AssertionError('unexpected hardware command %r' % (command,))
    return output


def test_dual_die_cards_use_physical_ids_and_preserve_both_pci_identities():
    calls = []
    devices = hccn.collect_devices(_dual_die_output(calls))
    assert [device['pciDeviceAddress'] for device in devices] == ['0000:85:00.0', '0000:87:00.0']
    assert [device['serialNumber'] for device in devices] == ['card-6', 'card-6']
    assert [(device['chipId'], device['physicalId']) for device in devices] == [(0, 12), (1, 13)]
    tool_ids = {command[2] for command in calls if command[0].endswith('/hccn_tool')}
    assert tool_ids == {'12', '13'}


def test_dual_die_mapping_never_falls_back_to_card_id_when_physical_id_is_missing():
    calls = []
    hardware = _dual_die_output(calls)
    def output(*command):
        if command == ('npu-smi', 'info', '-m'):
            return '6 0 8 12 Ascend910\n6 1 9 - Ascend910\n'
        return hardware(*command)
    with pytest.raises(ValueError, match='physical'):
        hccn.collect_devices(output)


def test_same_board_serial_on_two_cards_is_rejected_even_with_different_chip_layouts():
    calls = []
    hardware = _dual_die_output(calls)
    def output(*command):
        if command == ('npu-smi', 'info', '-l'):
            return 'NPU ID: 0\nNPU ID: 6\n'
        if command == ('npu-smi', 'info', '-t', 'board', '-i', '0'):
            return 'Serial Number : card-6\nPCIe Bus Info : 0000:01:00.0\n'
        return hardware(*command)
    with pytest.raises(ValueError, match='duplicate host NPU serial'):
        hccn.collect_devices(output)


def test_hccs_observation_uses_each_chips_actual_sdid_and_vnic():
    calls = []
    devices = hccn.collect_devices(_dual_die_output(calls))
    assert [device['hccs'] for device in devices] == [
        {'address': '192.9.2.187', 'netmask': '255.0.0.0', 'linkStatus': 'UP',
         'sdid': 39321612, 'superPodId': 1, 'superPodSize': 96, 'serverIndex': 9},
        {'address': '192.9.3.186', 'netmask': '255.0.0.0', 'linkStatus': 'UP',
         'sdid': 39387149, 'superPodId': 1, 'superPodSize': 96, 'serverIndex': 9},
    ]
    assert all('-s' not in command for command in calls)


def test_hccs_remains_observable_without_querying_a_down_roce_ports_ip():
    calls = []
    hardware = _dual_die_output(calls)
    def output(*command):
        if '-link' in command:
            return 'link status: DOWN\n'
        if '-ip' in command:
            pytest.fail('a down RoCE port must not delay HCCS admission with an IP query')
        return hardware(*command)
    devices = hccn.collect_devices(output)
    assert all(device['hccs']['linkStatus'] == 'UP' for device in devices)
    assert all(device['address'] is None and device['linkStatus'] == 'DOWN' for device in devices)


def test_roce_timeout_does_not_discard_independent_hccs_observation():
    hardware = _dual_die_output([])
    def output(*command):
        if '-ip' in command:
            raise subprocess.TimeoutExpired(command, 5, output='driver IP query timed out')
        return hardware(*command)
    devices = hccn.collect_devices(output)
    assert all(device['hccs']['linkStatus'] == 'UP' for device in devices)
    assert all(device['address'] is None and 'timed out' in device['roceError'] for device in devices)


def test_hccs_failure_keeps_working_roce_and_original_driver_reason():
    hardware = _dual_die_output([])
    def output(*command):
        if '-vnic' in command:
            raise subprocess.CalledProcessError(7, command, output='vNIC is not supported by this chip')
        return hardware(*command)
    devices = hccn.collect_devices(output)
    assert [device['address'] for device in devices] == ['10.0.0.12', '10.0.0.13']
    assert all('vNIC is not supported' in device['hccs']['error'] for device in devices)
    assert all('address' not in device['hccs'] for device in devices)


@pytest.mark.parametrize('field,value', [
    ('SDID', '-1'), ('SDID', '4294967296'), ('SDID', 'unknown'),
    ('Super Pod ID', '-1'), ('Super Pod Size', '1'), ('Server Index', '-1'),
])
def test_invalid_hccs_topology_is_not_advertised_as_a_valid_fabric(field, value):
    hardware = _dual_die_output([])
    def output(*command):
        original = hardware(*command)
        if 'spod-info' in command:
            lines = [field + ' : ' + value if line.startswith(field + ' :') else line
                     for line in original.splitlines()]
            return '\n'.join(lines) + '\n'
        return original
    devices = hccn.collect_devices(output)
    assert all('error' in device['hccs'] and 'sdid' not in device['hccs'] for device in devices)


@pytest.mark.parametrize('status,expected', [('DOWN', 'DOWN'), ('ERROR', 'UNKNOWN')])
def test_hccs_link_state_never_borrows_roce_up_status(status, expected):
    hardware = _dual_die_output([])
    def output(*command):
        original = hardware(*command)
        return original.replace('vnic link status: UP', 'vnic link status: ' + status)
    devices = hccn.collect_devices(output)
    assert all(device['linkStatus'] == 'UP' for device in devices)
    assert all(device['hccs']['linkStatus'] == expected for device in devices)


@pytest.mark.parametrize('line', ['vnic ipaddr: 0.0.0.0', 'vnic ipaddr: 127.0.0.1',
                               'vnic netmask: 255.0.255.0', 'vnic netmask: 0.0.0.0'])
def test_malformed_vnic_does_not_block_valid_roce_or_become_a_valid_hccs_profile(line):
    hardware = _dual_die_output([])
    def output(*command):
        original = hardware(*command)
        if '-vnic' in command:
            key = line.split(':')[0]
            return '\n'.join(line if item.startswith(key + ':') else item for item in original.splitlines())
        return original
    devices = hccn.collect_devices(output)
    assert all(device['address'] and 'error' in device['hccs'] for device in devices)


@pytest.mark.parametrize('field', ['address', 'sdid'])
def test_duplicate_hccs_endpoints_are_rejected_without_discarding_valid_roce(field):
    hardware = _dual_die_output([])
    def output(*command):
        original = hardware(*command)
        if field == 'address' and '-vnic' in command:
            return original.replace('192.9.3.186', '192.9.2.187')
        if field == 'sdid' and 'spod-info' in command:
            return original.replace('39387149', '39321612')
        return original
    devices = hccn.collect_devices(output)
    assert all(device['address'] and 'duplicate' in device['hccs']['error'] for device in devices)


def test_duplicate_roce_addresses_do_not_hide_independent_valid_hccs_endpoints():
    hardware = _dual_die_output([])
    def output(*command):
        original = hardware(*command)
        return original.replace('10.0.0.13', '10.0.0.12') if '-ip' in command else original
    devices = hccn.collect_devices(output)
    assert all(device['address'] is None and 'duplicate' in device['roceError'] for device in devices)
    assert all(device['hccs']['linkStatus'] == 'UP' for device in devices)


@pytest.mark.parametrize("extra_status", ["DOWN", "NOT SUPPORTED", ""])
def test_ambiguous_hccs_link_fields_cannot_be_advertised_as_up(extra_status):
    hardware = _dual_die_output([])
    def output(*command):
        original = hardware(*command)
        return original + 'vnic link status: ' + extra_status + '\n' if '-vnic' in command else original
    devices = hccn.collect_devices(output)
    assert all('error' in device['hccs'] and 'ambiguous' in device['hccs']['error'] for device in devices)


def test_hccs_driver_crlf_output_keeps_complete_chip_identities():
    hardware = _dual_die_output([])
    devices = hccn.collect_devices(lambda *command: hardware(*command).replace('\n', '\r\n'))
    assert {device['physicalId'] for device in devices} == {12, 13}
    assert all(device['hccs']['linkStatus'] == 'UP' for device in devices)
