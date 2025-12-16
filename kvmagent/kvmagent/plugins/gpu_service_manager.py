from kvmagent import kvmagent
from zstacklib.utils import gpu, thread
from zstacklib.utils import log
import threading

log.configure_log('/var/log/zstack/zstack-kvmagent.log')
logger = log.get_logger(__name__)


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None


class GpuServiceManager(kvmagent.KvmAgent):
    """GPU service manager for managing GPU services of different vendors"""

    def __init__(self):
        self.config = None
        self._service_threads = {}
        self._lock = threading.Lock()
        self.vendor_service_map = {
            gpu.VendorEnum.NVIDIA: gpu.watch_and_ensure_nvidia_persistenced,
        }

    def configure(self, config):
        self.config = config

    def start(self):
        """Start all supported GPU vendor services"""
        # with self._lock:
        #     for vendor, service in self.vendor_service_map.items():
        #         self._service_threads[vendor] = thread.ThreadFacade.run_in_thread(service)
        #         logger.debug("Starting {0} gpu auxiliary service".format(vendor))

    def stop(self):
        """Stop all GPU vendor services"""
        # with self._lock:
        #     for vendor, service_thread in self._service_threads.items():
        #         if service_thread and service_thread.is_alive():
        #             logger.debug("Stopping {0} gpu auxiliary service".format(vendor))
        #             service_thread.stop()
        #             service_thread.join(timeout=5)
        #     self._service_threads.clear()
