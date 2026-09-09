import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from kvmagent.plugins import prometheus


class RecordingMetric(object):
    def __init__(self):
        self.samples = []

    def add_metric(self, labels, value):
        self.samples.append((labels, value))


def _metric_families():
    return {name: RecordingMetric() for name in (
        "host_gpu_power_draw",
        "host_gpu_temperature",
        "host_gpu_fan_speed",
        "host_gpu_utilization",
        "host_gpu_memory_utilization",
        "host_gpu_rxpci_in_bytes",
        "host_gpu_txpci_in_bytes",
        "host_gpu_status",
        "vgpu_utilization",
        "vgpu_memory_utilization",
    )}


def test_gpu_metric_names_and_pcie_labels_remain_compatible():
    definitions = []

    def metric_family(name, help_text, _value=None, labels=None):
        definitions.append((name, tuple(labels or ())))
        return RecordingMetric()

    with patch.object(prometheus, "GaugeMetricFamily", side_effect=metric_family):
        metrics = prometheus.get_gpu_metrics()

    assert "host_gpu_rxpci_in_bytes" in metrics
    assert "host_gpu_txpci_in_bytes" in metrics
    assert ("host_gpu_rxpci_in_bytes", ("pci_device_address", "gpu_serial")) in definitions
    assert ("host_gpu_txpci_in_bytes", ("pci_device_address", "gpu_serial")) in definitions


def test_collector_exports_cached_pcie_values_under_existing_metric_contract():
    metrics = _metric_families()
    gpu_metric = SimpleNamespace(
        pci_address="0000:1a:00.0",
        serial_number="SN00",
        power_draw=65.0,
        temperature=58.0,
        fan_speed=None,
        utilization=45.0,
        memory_utilization=62.0,
        pcie_rx_bytes=2048.0,
        pcie_tx_bytes=1024.0,
        extra={},
    )
    vendor = MagicMock()
    vendor.VENDOR_NAME = "NVIDIA"
    vendor.is_available.return_value = True
    vendor.collect_metrics.return_value = [gpu_metric]
    vendor.collect_vgpu_metrics.return_value = []

    gpu_module = __import__("zstacklib.gpu", fromlist=["get_all_gpu_vendors"])
    with patch.object(gpu_module, "get_all_gpu_vendors", return_value=[vendor], create=True), \
            patch.object(prometheus, "get_gpu_metrics", return_value=metrics), \
            patch.object(prometheus, "add_gpu_pci_device_address"), \
            patch.object(prometheus, "check_gpu_status_and_save_gpu_status"), \
            patch.object(prometheus, "collect_gpu_xid_errors", return_value=[]):
        prometheus.collect_gpu_metrics_via_plugin()

    assert metrics["host_gpu_rxpci_in_bytes"].samples == [
        (["0000:1a:00.0", "SN00"], 2048.0)
    ]
    assert metrics["host_gpu_txpci_in_bytes"].samples == [
        (["0000:1a:00.0", "SN00"], 1024.0)
    ]
    vendor.collect_metrics.assert_called_once_with()
    vendor.collect_vgpu_metrics.assert_called_once_with()


def test_dgpu_collector_omits_samples_when_vendor_metrics_are_unavailable():
    service = MagicMock()
    workers = [SimpleNamespace(device_uuid="device-uuid")]
    service.list_workers.return_value = workers
    nvidia = MagicMock()
    nvidia.is_available.return_value = True
    nvidia.collect_dgpu_worker_metrics.return_value = []
    nvidia_module = types.ModuleType("zstacklib.gpu.vendors.nvidia")
    nvidia_module.NVIDIA = nvidia

    with patch.object(prometheus.kvmagent, "get_tf_service",
                      return_value=service), \
            patch.dict(sys.modules, {
                "zstacklib.gpu.vendors.nvidia": nvidia_module,
            }), \
            patch.object(prometheus, "GaugeMetricFamily",
                         side_effect=lambda *args, **kwargs: RecordingMetric()):
        metrics = list(prometheus.collect_dgpu_worker_metrics())

    assert len(metrics) == 2
    assert all(metric.samples == [] for metric in metrics)
    nvidia.collect_dgpu_worker_metrics.assert_called_once_with(workers)
