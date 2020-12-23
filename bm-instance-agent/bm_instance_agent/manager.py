from oslo_log import log as logging
from stevedore import driver

from bm_instance_agent.common import utils as bm_utils
from bm_instance_agent import exception
from bm_instance_agent.objects import BmInstanceObj
from bm_instance_agent.objects import NetworkObj
from bm_instance_agent.objects import VolumeObj


LOG = logging.getLogger(__name__)


BM_INSTANCE_UUID = None
DRIVER = None


class AgentManager(object):

    def __init__(self):
        global DRIVER
        if not DRIVER:
            DRIVER = self._load_driver()
        self.driver = DRIVER

    def _load_driver(self):
        return driver.DriverManager(
            namespace='bm_instance_agent.systems.driver',
            name=bm_utils.get_distro(),
            invoke_on_load=True).driver

    def _check_uuid_corrent(self, bm_uuid):
        global BM_INSTANCE_UUID
        if not BM_INSTANCE_UUID == bm_uuid:
            raise exception.BmInstanceUuidConflict(
                req_instance_uuid=bm_uuid,
                exist_instance_uuid=BM_INSTANCE_UUID)

    def ping(self, bm_instance):
        instance_obj = BmInstanceObj.from_json(bm_instance)

        global BM_INSTANCE_UUID
        if not BM_INSTANCE_UUID:
            BM_INSTANCE_UUID = instance_obj.uuid
        self._check_uuid_corrent(instance_obj.uuid)
        self.driver.ping(instance_obj)
        return {'ping': {'bmInstanceUuid': BM_INSTANCE_UUID}}

    def reboot(self, bm_instance):
        instance_obj = BmInstanceObj.from_json(bm_instance)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to reboot the system: '
               '{bm_uuid}').format(bm_uuid=instance_obj.uuid)
        LOG.info(msg)
        self.driver.reboot(instance_obj)

    def stop(self, bm_instance):
        instance_obj = BmInstanceObj.from_json(bm_instance)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to stop the system: '
               '{bm_uuid}').format(bm_uuid=instance_obj.uuid)
        LOG.info(msg)
        self.driver.stop(instance_obj)

    def attach_volume(self, bm_instance, volume):
        instance_obj = BmInstanceObj.from_json(bm_instance)
        volume_obj = VolumeObj.from_json(volume)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to attach the volume: {volume_uuid} '
               'to the system: {bm_uuid}').format(
                   volume_uuid=volume_obj.uuid, bm_uuid=instance_obj.uuid)
        LOG.info(msg)
        self.driver.attach_volume(instance_obj, volume_obj)

    def detach_volume(self, bm_instance, volume):
        instance_obj = BmInstanceObj.from_json(bm_instance)
        volume_obj = VolumeObj.from_json(volume)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to detach the volume: {volume_uuid} '
               'from the system: {bm_uuid}').format(
                   volume_uuid=volume_obj.uuid, bm_uuid=instance_obj.uuid)
        LOG.info(msg)
        self.driver.detach_volume(instance_obj, volume_obj)

    def attach_port(self, bm_instance, port):
        instance_obj = BmInstanceObj.from_json(bm_instance)
        network_obj = NetworkObj.from_json(port)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to attach port: {port_mac} '
               'to the system: {bm_uuid}').format(
                   bm_uuid=instance_obj.uuid,
                   port_mac=[x.mac for x in network_obj.ports])
        LOG.info(msg)
        self.driver.attach_port(instance_obj, network_obj)

    def detach_port(self, bm_instance, port):
        instance_obj = BmInstanceObj.from_json(bm_instance)
        network_obj = NetworkObj.from_json(port)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to detach port: {port_mac} '
               'from the system: {bm_uuid}').format(
                   bm_uuid=instance_obj.uuid,
                   port_mac=[x.mac for x in network_obj.ports])
        LOG.info(msg)
        self.driver.detach_port(instance_obj, network_obj)

    def update_default_route(
            self, bm_instance, old_default_port, new_default_port):
        instance_obj = BmInstanceObj.from_json(bm_instance)
        old_network_obj = NetworkObj.from_json(old_default_port)
        new_network_obj = NetworkObj.from_json(new_default_port)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to update the gateway from the system: '
               '{bm_uuid}').format(bm_uuid=instance_obj.uuid)
        LOG.info(msg)
        self.driver.update_default_route(
            instance_obj, old_network_obj, new_network_obj)

    def update_password(self, bm_instance, password):
        instance_obj = BmInstanceObj.from_json(bm_instance)

        self._check_uuid_corrent(instance_obj.uuid)
        msg = ('Call the driver to update user password')
        LOG.info(msg)
        self.driver.update_password(instance_obj, password)

    def console(self):
        msg = ('Call the driver to start console')
        LOG.info(msg)
        return self.driver.console()
