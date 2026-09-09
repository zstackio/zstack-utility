'''
TensorFusion KVM Agent Plugin - HTTP API for GPU virtualization worker management.

@author: tensorfusion
'''

import threading
import time
import traceback

from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils.libvirt_singleton import LibvirtEventManager

from kvmagent.plugins.tensorfusion.models import WorkerCreateRequest
from kvmagent.plugins.tensorfusion.service import TensorFusionService

logger = log.get_logger(__name__)


def _redact_worker_credentials(text, cmd):
    redacted = text
    values = [value for value in (cmd.license, cmd.licenseSign) if value]
    for value in sorted(values, key=len, reverse=True):
        redacted = redacted.replace(value, '*****')
    return redacted


# --- Request / Response classes ---

class CreateWorkerCmd(kvmagent.AgentCommand):
    @log.sensitive_fields('license', 'licenseSign')
    def __init__(self):
        super(CreateWorkerCmd, self).__init__()
        self.vmUuid = None
        self.pciAddress = None
        self.memoryMb = 0
        self.shmemSize = 0
        self.license = None
        self.licenseSign = None
        self.enableLog = True
        self.logLevel = 'info'
        self.deviceUuid = None
        self.protocol = 'shmem'
        self.smPercentLimit = 0


class CreateWorkerRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CreateWorkerRsp, self).__init__()
        self.worker = None


class DestroyWorkerCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DestroyWorkerCmd, self).__init__()
        self.deviceUuid = None


class DestroyWorkerRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(DestroyWorkerRsp, self).__init__()
        self.destroyed = False


class DestroyWorkersByVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DestroyWorkersByVmCmd, self).__init__()
        self.vmUuid = None


class DestroyWorkersByVmRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(DestroyWorkersByVmRsp, self).__init__()
        self.destroyedCount = 0


class GetWorkerCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetWorkerCmd, self).__init__()
        self.deviceUuid = None


class GetWorkerRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetWorkerRsp, self).__init__()
        self.worker = None


class ListWorkersRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(ListWorkersRsp, self).__init__()
        self.workers = []


class ListWorkersByVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ListWorkersByVmCmd, self).__init__()
        self.vmUuid = None


class GetGpuUsageCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetGpuUsageCmd, self).__init__()
        self.pciAddress = None


class GetGpuUsageRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetGpuUsageRsp, self).__init__()
        self.usage = None


class ListGpuUsagesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(ListGpuUsagesRsp, self).__init__()
        self.usages = []


class ListGpuHardwareRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(ListGpuHardwareRsp, self).__init__()
        self.gpus = []


class CheckHealthCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CheckHealthCmd, self).__init__()
        self.deviceUuid = None


class CheckHealthRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckHealthRsp, self).__init__()
        self.alive = False


class CleanupRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CleanupRsp, self).__init__()
        self.cleanedDeviceUuids = []


# --- Plugin ---

class TensorFusionPlugin(kvmagent.KvmAgent):
    """TensorFusion GPU virtualization plugin for KVM Agent."""

    _instance = None

    @classmethod
    def get_service(cls):
        """Get the TensorFusionService instance for metrics collection."""
        if cls._instance:
            return cls._instance._service
        return None

    # HTTP endpoint paths
    CREATE_WORKER = '/tensorfusion/worker/create'
    DESTROY_WORKER = '/tensorfusion/worker/destroy'
    DESTROY_WORKERS_BY_VM = '/tensorfusion/worker/destroybyvm'
    GET_WORKER = '/tensorfusion/worker/get'
    LIST_WORKERS = '/tensorfusion/workers'
    LIST_WORKERS_BY_VM = '/tensorfusion/workers/byvm'
    GET_GPU_USAGE = '/tensorfusion/gpu/usage'
    LIST_GPU_USAGES = '/tensorfusion/gpu/usages'
    LIST_GPU_HARDWARE = '/tensorfusion/gpu/list'
    CHECK_HEALTH = '/tensorfusion/health/check'
    CLEANUP = '/tensorfusion/health/cleanup'

    # Seconds to suppress duplicate cleanup after one completes for the same VM.
    # VM stop produces Shutdown → Stopped → Undefined in sequence; without debounce
    # a later event can race with MN's next create_worker and kill the new container.
    CLEANUP_DEBOUNCE_SECS = 10

    def __init__(self):
        super(TensorFusionPlugin, self).__init__()
        self.config = None
        self._service = None
        self._cleanup_lock = threading.Lock()
        self._cleanup_threads = {}
        self._cleanup_done_ts = {}  # vm_uuid → monotonic timestamp of last successful cleanup

    def configure(self, config):
        self.config = config

    def start(self):
        http_server = kvmagent.get_http_server()

        # All endpoints registered as async
        http_server.register_async_uri(self.CREATE_WORKER, self.create_worker, cmd=CreateWorkerCmd())
        http_server.register_async_uri(self.DESTROY_WORKER, self.destroy_worker)
        http_server.register_async_uri(self.DESTROY_WORKERS_BY_VM, self.destroy_workers_by_vm)
        http_server.register_async_uri(self.CLEANUP, self.cleanup)
        http_server.register_async_uri(self.GET_WORKER, self.get_worker)
        http_server.register_async_uri(self.LIST_WORKERS, self.list_workers)
        http_server.register_async_uri(self.LIST_WORKERS_BY_VM, self.list_workers_by_vm)
        http_server.register_async_uri(self.GET_GPU_USAGE, self.get_gpu_usage)
        http_server.register_async_uri(self.LIST_GPU_USAGES, self.list_gpu_usages)
        http_server.register_async_uri(self.LIST_GPU_HARDWARE, self.list_gpu_hardware)
        http_server.register_async_uri(self.CHECK_HEALTH, self.check_health)

        self._service = TensorFusionService(event_notifier=self._make_event_notifier())
        self._service.initialize()
        TensorFusionPlugin._instance = self
        kvmagent.set_tf_service(self._service)

        self._register_vm_lifecycle_hook()

        logger.info('TensorFusion plugin started')

    def stop(self):
        kvmagent.set_tf_service(None)
        TensorFusionPlugin._instance = None
        if self._service is not None:
            self._service.stop()

        with self._cleanup_lock:
            cleanup_threads = list(self._cleanup_threads.values())

        current = threading.current_thread()
        for thread in cleanup_threads:
            if thread is current:
                continue
            thread.join(5)
            if thread.is_alive():
                logger.warning('TensorFusion: cleanup thread %s did not exit within 5s' % thread.name)

    # --- Event notifier (Agent -> Management node push) ---

    WORKER_EVENT_PATH = '/tensorfusion/worker/event'

    def _make_event_notifier(self):
        """
        Returns a callable that POSTs a worker event notification to the management node.
        Uses the same send-command URL / commandpath mechanism as other agent->MN pushes.
        """
        event_path = self.WORKER_EVENT_PATH

        def notifier(device_uuid, vm_uuid, pci_address, crash_count, event_type):
            mn_url = self.config.get(kvmagent.SEND_COMMAND_URL) if self.config else None
            if not mn_url:
                logger.warning('TensorFusion: skip worker event %s for worker %s: no management node URL in config' % (
                    event_type, device_uuid))
                return

            body = {
                'deviceUuid': device_uuid,
                'vmUuid': vm_uuid,
                'pciAddress': pci_address,
                'crashCount': crash_count,
                'eventType': event_type,
            }
            http.json_dump_post(mn_url, body, {'commandpath': event_path})

        return notifier

    # --- VM lifecycle hook ---

    def _register_vm_lifecycle_hook(self):
        """Register libvirt lifecycle callback to clean up workers when a VM stops."""
        from kvmagent.plugins.vm_plugin import LibvirtAutoReconnect
        import libvirt
        callbacks = LibvirtAutoReconnect.libvirt_event_callbacks.get(
            libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, []
        )
        if self._on_vm_lifecycle_event not in callbacks:
            LibvirtAutoReconnect.add_libvirt_callback(
                libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._on_vm_lifecycle_event
            )
        logger.info('TensorFusion: registered VM lifecycle hook')

    def _on_vm_lifecycle_event(self, conn, dom, event, detail, opaque):
        try:
            event_str = LibvirtEventManager.event_to_string(event)
            if event_str not in (
                LibvirtEventManager.EVENT_STOPPED,
                LibvirtEventManager.EVENT_SHUTDOWN,
                LibvirtEventManager.EVENT_CRASHED,
                LibvirtEventManager.EVENT_UNDEFINED,
            ):
                return

            vm_uuid = dom.name()
            self._schedule_vm_worker_cleanup(vm_uuid, event_str)
        except Exception:
            import traceback
            logger.warning('TensorFusion: VM lifecycle hook error: %s' % traceback.format_exc())

    def _schedule_vm_worker_cleanup(self, vm_uuid, event_str):
        with self._cleanup_lock:
            thread = self._cleanup_threads.get(vm_uuid)
            if thread is not None and thread.is_alive():
                logger.debug('TensorFusion: cleanup for VM %s already scheduled, ignore lifecycle event %s' % (
                    vm_uuid, event_str))
                return

            # Debounce: if a cleanup recently completed for this VM, skip.
            # This prevents Stopped/Undefined events (arriving seconds after Shutdown)
            # from racing with a new create_worker that MN issues after the first cleanup.
            last_done = self._cleanup_done_ts.get(vm_uuid, 0)
            if (time.monotonic() - last_done) < self.CLEANUP_DEBOUNCE_SECS:
                logger.debug('TensorFusion: cleanup for VM %s completed %.1fs ago (debounce=%ds), '
                             'ignore lifecycle event %s' % (
                    vm_uuid, time.monotonic() - last_done, self.CLEANUP_DEBOUNCE_SECS, event_str))
                return

            thread = threading.Thread(
                target=self._cleanup_workers_by_vm_async,
                args=(vm_uuid, event_str),
                name='tf-vm-cleanup-%s' % vm_uuid[:8]
            )
            thread.daemon = True
            self._cleanup_threads[vm_uuid] = thread

        thread.start()

    def _cleanup_workers_by_vm_async(self, vm_uuid, event_str):
        cleanup_succeeded = False
        try:
            count = self._service.destroy_workers_by_vm(vm_uuid)
            cleanup_succeeded = True
            if count > 0:
                logger.info('TensorFusion: cleaned up %d workers for VM %s after lifecycle event %s' % (
                    count, vm_uuid, event_str))
        except Exception:
            import traceback
            logger.warning('TensorFusion: async cleanup for VM %s after lifecycle event %s failed: %s' % (
                vm_uuid, event_str, traceback.format_exc()))
        finally:
            with self._cleanup_lock:
                if cleanup_succeeded:
                    self._cleanup_done_ts[vm_uuid] = time.monotonic()
                thread = self._cleanup_threads.get(vm_uuid)
                if thread is threading.current_thread():
                    self._cleanup_threads.pop(vm_uuid, None)

    # --- Helper ---

    @staticmethod
    def _to_create_request(cmd):
        # type: (object) -> WorkerCreateRequest
        req = WorkerCreateRequest()
        req.vm_uuid = cmd.vmUuid
        req.pci_address = cmd.pciAddress
        req.memory_mb = cmd.memoryMb or 0
        req.shmem_size = cmd.shmemSize or 0
        req.license = cmd.license
        req.license_sign = cmd.licenseSign
        req.enable_log = cmd.enableLog if cmd.enableLog is not None else True
        req.log_level = cmd.logLevel or 'info'
        req.device_uuid = cmd.deviceUuid
        req.protocol = cmd.protocol or 'shmem'
        req.sm_percent_limit = cmd.smPercentLimit or 0
        return req

    # --- Async handlers ---

    def create_worker(self, req):
        cmd = None
        try:
            cmd = jsonobject.loads(req[http.REQUEST_BODY])
            rsp = CreateWorkerRsp()

            create_req = self._to_create_request(cmd)
            worker = self._service.create_worker(create_req)
            rsp.worker = worker.to_dict()
            return jsonobject.dumps(rsp)
        except Exception as e:
            error = str(e)
            content = traceback.format_exc()
            if cmd is not None:
                error = _redact_worker_credentials(error, cmd)
                content = _redact_worker_credentials(content, cmd)

            rsp = kvmagent.AgentResponse()
            rsp.success = False
            rsp.error = error
            logger.warn('%s\n%s' % (error, content))
            return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def destroy_worker(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DestroyWorkerRsp()

        rsp.destroyed = self._service.destroy_worker(cmd.deviceUuid)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def destroy_workers_by_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DestroyWorkersByVmRsp()

        rsp.destroyedCount = self._service.destroy_workers_by_vm(cmd.vmUuid)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def cleanup(self, req):
        rsp = CleanupRsp()
        rsp.cleanedDeviceUuids = self._service.cleanup_dead_workers()
        return jsonobject.dumps(rsp)

    # --- Sync handlers ---

    @kvmagent.replyerror
    def get_worker(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetWorkerRsp()

        worker = self._service.get_worker(cmd.deviceUuid)
        rsp.worker = worker.to_dict() if worker else None

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def list_workers(self, req):
        rsp = ListWorkersRsp()
        rsp.workers = [w.to_dict() for w in self._service.list_workers()]
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def list_workers_by_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ListWorkersRsp()
        rsp.workers = [w.to_dict() for w in self._service.list_workers_by_vm(cmd.vmUuid)]
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_gpu_usage(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetGpuUsageRsp()
        rsp.usage = self._service.get_gpu_usage(cmd.pciAddress).to_dict()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def list_gpu_usages(self, req):
        rsp = ListGpuUsagesRsp()
        rsp.usages = [u.to_dict() for u in self._service.get_all_gpu_usage()]
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def list_gpu_hardware(self, req):
        rsp = ListGpuHardwareRsp()
        rsp.gpus = [g.to_dict() for g in self._service.list_gpu_hardware()]
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_health(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckHealthRsp()
        rsp.alive = self._service.check_worker_health(cmd.deviceUuid)
        return jsonobject.dumps(rsp)
