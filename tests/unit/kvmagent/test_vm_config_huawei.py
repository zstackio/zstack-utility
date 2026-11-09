# -*- coding: utf-8 -*-
import base64
import json
from unittest.mock import MagicMock, patch

from kvmagent.plugins import vm_config
from zstacklib.utils import http


def test_guest_huawei_collection_merges_summary_before_pci_mapping():
    plugin = vm_config.VmConfigPlugin.__new__(vm_config.VmConfigPlugin)
    plugin.map_pci_addresses_in_gpu_info = MagicMock(
        side_effect=lambda infos, _: infos)

    qga = MagicMock()
    qga.guest_exec_cmd_no_exitcode.side_effect = [
        "/usr/bin/npu-smi",
        "NPU ID : 2",
        "PCIe Bus Info : 0000:95:00.0",
        "summary",
    ]
    board_infos = [{"pciAddress": "0000:95:00.0"}]
    merged_infos = [
        {"pciAddress": "0000:95:00.0", "chipId": "0"},
        {"pciAddress": "0000:97:00.0", "chipId": "1"},
    ]

    with patch.object(vm_config.gpu, "get_huawei_gpu_npu_id_cmd",
                      return_value="npu-smi info -l") as npu_id_cmd, \
            patch.object(vm_config.gpu, "get_huawei_npu_id",
                         return_value=["2"]), \
            patch.object(vm_config.gpu, "get_huawei_gpu_basic_info_cmd",
                         return_value="board") as basic_info_cmd, \
            patch.object(vm_config.gpu,
                         "parse_huawei_gpu_output_by_npu_id",
                         return_value=board_infos), \
            patch.object(vm_config.gpu, "merge_huawei_gpu_chip_infos",
                         return_value=merged_infos) as merge:
        result = plugin.get_vm_hauwei_gpu_info_by_guesttool(qga)

    merge.assert_called_once_with(
        [{"pciAddress": "0000:95:00.0", "npuId": "2"}], "summary")
    assert qga.guest_exec_cmd_no_exitcode.call_args_list[0].args == (
        "command -v npu-smi",)
    assert qga.guest_exec_cmd_no_exitcode.call_args_list[-1].args == (
        "/usr/bin/npu-smi info",)
    npu_id_cmd.assert_called_once_with("/usr/bin/npu-smi", False)
    basic_info_cmd.assert_called_once_with(
        "2", iswindows=False, npu_smi_path="/usr/bin/npu-smi")
    assert result == merged_infos


def test_guest_huawei_collection_keeps_board_data_when_summary_fails():
    plugin = vm_config.VmConfigPlugin.__new__(vm_config.VmConfigPlugin)
    plugin.map_pci_addresses_in_gpu_info = MagicMock(
        side_effect=lambda infos, _: infos)

    qga = MagicMock()
    qga.guest_exec_cmd_no_exitcode.side_effect = [
        "/usr/bin/npu-smi",
        "NPU ID : 1",
        "PCIe Bus Info : 0000:C2:00.0",
        None,
    ]
    board_infos = [{"pciAddress": "0000:c2:00.0"}]

    with patch.object(vm_config.gpu, "get_huawei_gpu_npu_id_cmd",
                      return_value="npu-smi info -l"), \
            patch.object(vm_config.gpu, "get_huawei_npu_id",
                         return_value=["1"]), \
            patch.object(vm_config.gpu, "get_huawei_gpu_basic_info_cmd",
                         return_value="board"), \
            patch.object(vm_config.gpu,
                         "parse_huawei_gpu_output_by_npu_id",
                         return_value=board_infos), \
            patch.object(vm_config.gpu, "merge_huawei_gpu_chip_infos") \
            as merge:
        result = plugin.get_vm_hauwei_gpu_info_by_guesttool(qga)

    merge.assert_not_called()
    assert result == [{"pciAddress": "0000:c2:00.0", "npuId": "1"}]


def test_vm_gpu_info_sync_returns_both_910c_chips():
    """The VM sync API exposes both host PCI devices from real guest output."""
    board_output = """
Serial Number : BOARD002
PCIe Bus Info : 0000:95:00.0
Total DDR Capacity(MB) : 131072
"""
    summary_output = """
| 2     Ascend910           | OK            | 163.1                |
| 0     4                   | 0000:95:00.0  | 0 / 0  2909 / 65536 |
| 2     Ascend910           | OK            | 160.8                |
| 1     5                   | 0000:97:00.0  | 0 / 0  2882 / 65536 |
"""

    domain = MagicMock()
    domain.name.return_value = "vm-uuid"
    domain.isActive.return_value = True
    qga = MagicMock()
    qga.domain = domain
    qga.state = "Running"
    qga.os = "centos"
    qga.os_version = "7"

    def guest_command(command, exception=True):
        if command == "npu-smi info -l":
            return "NPU ID : 2"
        if command == "command -v npu-smi":
            assert exception is False
            return "/usr/bin/npu-smi"
        if command == "/usr/bin/npu-smi info":
            return summary_output
        if command == "board-2":
            return board_output
        if command.startswith("lspci -s "):
            return "Huawei Technologies Device d802"
        raise AssertionError("unexpected guest command: %s" % command)

    qga.guest_exec_cmd_no_exitcode.side_effect = guest_command
    request = {
        http.REQUEST_BODY: json.dumps({
            "vmUuid": "vm-uuid",
            "vendors": ["Huawei"],
        })
    }
    pci_mapping = {
        "0000:95:00.0": "0000:42:00.0",
        "0000:97:00.0": "0000:43:00.0",
    }
    merged_infos = [
        {
            "pciAddress": "0000:95:00.0",
            "memory": "65536 MB",
            "npuId": "2",
            "chipId": "0",
            "physicalId": "4",
        },
        {
            "pciAddress": "0000:97:00.0",
            "memory": "65536 MB",
            "npuId": "2",
            "chipId": "1",
            "physicalId": "5",
        },
    ]

    class TestVendorEnum(object):
        NVIDIA = "NVIDIA"
        AMD = "AMD"
        HAIGUANG = "Haiguang"
        HUAWEI = "Huawei"
        TIANSHU = "TianShu"
        ENFLAME = "Enflame"
        ALIBABA = "Alibaba"
        KUNLUNXIN = "Kunlunxin"

    class QgaFactory(object):
        QGA_STATE_RUNNING = "Running"

        def __new__(cls, _domain):
            return qga

    plugin = vm_config.VmConfigPlugin.__new__(vm_config.VmConfigPlugin)
    with patch.object(vm_config, "get_virt_domain", return_value=domain), \
            patch.object(vm_config, "VmQga", QgaFactory), \
            patch.object(vm_config, "VendorEnum", TestVendorEnum), \
            patch.object(vm_config.VmConfigPlugin,
                         "VM_CONFIG_SYNC_OS_VERSION_SUPPORT",
                         {"centos": ("7",)}), \
            patch.object(vm_config.gpu, "get_huawei_gpu_npu_id_cmd",
                         return_value="npu-smi info -l"), \
            patch.object(vm_config.gpu, "get_huawei_npu_id",
                         return_value=["2"]), \
            patch.object(vm_config.gpu, "get_huawei_gpu_basic_info_cmd",
                         return_value="board-2"), \
            patch.object(vm_config.gpu,
                         "parse_huawei_gpu_output_by_npu_id",
                         return_value=[{
                             "pciAddress": "0000:95:00.0",
                             "memory": "131072 MB",
                         }]), \
            patch.object(vm_config.gpu, "merge_huawei_gpu_chip_infos",
                         return_value=merged_infos), \
            patch.object(vm_config.pci, "get_pci_passthrough_mapping",
                         return_value=pci_mapping):
        response = json.loads(plugin.vm_gpu_info_sync(request))

    assert response["success"] is True
    assert [item["pciAddress"] for item in response["gpuInfos"]] == [
        "0000:42:00.0", "0000:43:00.0"]
    assert [item["memory"] for item in response["gpuInfos"]] == [
        "65536 MB", "65536 MB"]
    assert [item["physicalId"] for item in response["gpuInfos"]] == [
        "4", "5"]
    assert all(item["isDriverLoaded"] for item in response["gpuInfos"])


def test_strict_host_probe_runs_real_dispatch_before_vm_lookup():
    plugin = vm_config.VmConfigPlugin.__new__(vm_config.VmConfigPlugin)
    raw = json.dumps({'hccnBootstrap': {'schemaVersion': 1, 'operation': 'capability', 'capabilityScope': 'host'}})
    with patch.object(vm_config, 'get_virt_domain', side_effect=AssertionError('host has no VM')):
        result = json.loads(plugin.vm_gpu_info_sync({http.REQUEST_BODY: raw}))
    assert result['success'] is True
    assert result['hccnBootstrap']['exitCode'] is None
    assert result['hccnBootstrap']['result']['releaseProbeVersion'] == 1
    assert result['gpuInfos'] == []


def test_strict_invalid_version_never_falls_through_to_legacy():
    plugin = vm_config.VmConfigPlugin.__new__(vm_config.VmConfigPlugin)
    raw = json.dumps({'hccnBootstrap': {'schemaVersion': 2, 'operation': 'capability', 'capabilityScope': 'host'}})
    with patch.object(vm_config, 'get_virt_domain', side_effect=AssertionError('invalid strict is not legacy')):
        result = json.loads(plugin.vm_gpu_info_sync({http.REQUEST_BODY: raw}))
    assert result['success'] is False
    assert result['hccnBootstrap']['errorCount'] == 1


def test_legacy_nvidia_empty_result_uses_original_collector_without_new_gate():
    plugin = vm_config.VmConfigPlugin.__new__(vm_config.VmConfigPlugin)
    domain = MagicMock()
    domain.isActive.return_value = True
    raw = json.dumps({'vmUuid': 'legacy-vm', 'vendors': ['NVIDIA']})
    with patch.object(vm_config, 'get_virt_domain', return_value=domain), \
            patch.object(plugin, 'get_vm_gpu_info_by_guesttool', return_value=(0, [])) as collector, \
            patch.object(vm_config.hccn_bootstrap, 'dispatch', side_effect=AssertionError('legacy must not run strict')):
        result = json.loads(plugin.vm_gpu_info_sync({http.REQUEST_BODY: raw}))
    collector.assert_called_once_with(domain, ['NVIDIA'])
    assert result['success'] is True
    assert result['gpuInfos'] == []
    assert 'hccnBootstrap' not in result



def _real_log_and_registered_gpu_sync_cmd(monkeypatch):
    # The shared conftest swaps log for a passthrough mock; load the real masker and decorator instead.
    import importlib.util
    import os
    import sys
    utils = sys.modules['zstacklib.utils']
    root = os.path.dirname(os.path.dirname(os.path.abspath(vm_config.__file__)))
    log_path = os.path.join(list(utils.__path__)[0], 'log.py')
    log_spec = importlib.util.spec_from_file_location('zstacklib.utils._real_log', log_path)
    real_log = importlib.util.module_from_spec(log_spec)
    log_spec.loader.exec_module(real_log)
    real_log.get_logger = lambda _name: MagicMock()
    monkeypatch.setitem(sys.modules, 'zstacklib.utils.log', real_log)
    monkeypatch.setattr(utils, 'log', real_log, raising=False)
    spec = importlib.util.spec_from_file_location('_vm_config_real_log', os.path.join(root, 'plugins', 'vm_config.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = MagicMock()
    plugin = module.VmConfigPlugin.__new__(module.VmConfigPlugin)
    with patch.object(module.kvmagent, 'get_http_server', return_value=server):
        plugin.start()
    for call in server.register_async_uri.call_args_list:
        if call.args[0] == module.VmConfigPlugin.VM_GPU_INFO_SYNC:
            return real_log, call.kwargs.get('cmd')
    raise AssertionError('gpu info sync uri not registered')


def test_strict_publish_yaml_is_masked_in_the_request_log(monkeypatch):
    # serviceYamlBase64 decodes to the service config with credentials; debug logs must never carry it.
    log, cmd = _real_log_and_registered_gpu_sync_cmd(monkeypatch)
    secret_yaml = base64.b64encode(b'password: hunter2\n').decode()
    raw = json.dumps({'vmUuid': 'a' * 32, 'vendors': ['Huawei'], 'hccnBootstrap': {
        'schemaVersion': 1, 'operation': 'publish', 'payload': {'serviceYamlBase64': secret_yaml}}})
    logged = log.mask_sensitive_field(cmd, raw)
    assert secret_yaml not in logged
    assert json.loads(logged)['vmUuid'] == 'a' * 32


def test_unparseable_strict_body_is_not_logged_and_does_not_raise(monkeypatch):
    # A body the masker cannot parse may still hold secrets, and the strict handler must still answer it.
    log, cmd = _real_log_and_registered_gpu_sync_cmd(monkeypatch)
    raw = '{"hccnBootstrap": {"payload": {"serviceYamlBase64": "c2VjcmV0"}'
    logged = log.mask_sensitive_field(cmd, raw)
    assert 'c2VjcmV0' not in logged
