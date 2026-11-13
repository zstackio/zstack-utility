import re

from kvmagent import kvmagent
from zstacklib.utils import http, jsonobject, lock, log, sansec_utils
from zstacklib.utils.sansec_utils import OperationStatus
from kvmagent.crypto import sansec_health, sansec_operations

logger = log.get_logger(__name__)


class SansecDriver(object):
    def __init__(self):
        self.detector = sansec_health.SansecHealthDetector()
        self.operations = sansec_operations.SansecOperations(self.detector)

    def health(self, pci_addresses):
        if self.operations.is_busy():
            return self.detector.unavailable(pci_addresses, 'Previous Sansec command has not exited')
        try:
            self.operations.converge()
        except (OSError, sansec_utils.CommandError, sansec_utils.ValidationError) as error:
            return self.detector.unavailable(pci_addresses, 'Cannot load swcsm with the persisted VFnum: %s' % error)
        return self.detector.health(pci_addresses)

    def submit(self, command):
        return self.operations.submit(command)


class CryptoPlugin(kvmagent.KvmAgent):
    HEALTH_PATH = '/crypto/devices/health'
    OPERATION_PATH = '/crypto/devices/operation'

    def __init__(self):
        super(CryptoPlugin, self).__init__()
        self.driver = SansecDriver()

    @staticmethod
    def validate_addresses(addresses):
        if not addresses or len(addresses) != len(set(addresses)):
            raise ValueError('PCI addresses must be a nonempty unique list')
        for address in addresses:
            if not re.fullmatch(r'[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]', address):
                raise ValueError('Invalid PCI address; expected 0000:b3:00.0')

    @kvmagent.replyerror
    def health(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.validate_addresses(cmd.pciDeviceAddresses)
        rsp = kvmagent.AgentResponse()
        with lock.NamedLock('sansec-device-operation'):
            rsp.devices = self.driver.health(cmd.pciDeviceAddresses)
        reported = [d['pciDeviceAddress'] for d in rsp.devices]
        if sorted(reported) != sorted(cmd.pciDeviceAddresses):
            raise ValueError('Health response must cover exactly the requested physical devices')
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def operation(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.validate_addresses(cmd.pciDeviceAddresses)
        if cmd.operation not in ('Split', 'Unsplit'):
            raise ValueError('Unsupported crypto device operation')
        if cmd.operation == 'Split' and (type(cmd.vfCount) is not int or cmd.vfCount <= 0):
            raise ValueError('VF count must be a positive integer')
        if cmd.pciDeviceAddress not in cmd.pciDeviceAddresses:
            raise ValueError('Target PF must belong to the locked host-wide device scope')
        with lock.NamedLock('sansec-device-operation'):
            result = self.driver.submit(cmd)
        return self.operation_response(result)

    @staticmethod
    def operation_response(result):
        if result['status'] not in (OperationStatus.SUCCEEDED, OperationStatus.FAILED,
                                    OperationStatus.UNKNOWN):
            raise ValueError('Invalid crypto operation status')
        rsp = kvmagent.AgentResponse()
        rsp.status = result['status']
        rsp.vfCounts = result.get('vfCounts')
        rsp.reason = result.get('reason')
        return jsonobject.dumps(rsp)

    def start(self):
        try:
            with lock.NamedLock('sansec-device-operation'):
                self.driver.operations.converge()
        except (OSError, sansec_utils.CommandError, sansec_utils.ValidationError) as error:
            logger.error('Cannot load swcsm with the persisted VFnum at startup: %s' % error)
        server = kvmagent.get_http_server()
        server.register_async_uri(self.HEALTH_PATH, self.health)
        server.register_async_uri(self.OPERATION_PATH, self.operation)

    def stop(self):
        pass
