from pecan.rest import RestController

from bm_instance_agent.api import utils as api_utils
from bm_instance_agent import manager


class AttachController(RestController):

    def __init__(self):
        super(AttachController, self).__init__()

    @api_utils.async_expose
    def post(self, volume, bm_instance, volume_access_path_gateway_ips):
        agent_manager = manager.AgentManager()
        return agent_manager.attach_volume(
            bm_instance=bm_instance,
            volume=volume, volume_access_path_gateway_ips=volume_access_path_gateway_ips)


class DetachController(RestController):

    def __init__(self):
        super(DetachController, self).__init__()

    @api_utils.async_expose
    def post(self, volume, bm_instance, volume_access_path_gateway_ips):
        agent_manager = manager.AgentManager()
        return agent_manager.detach_volume(
            bm_instance=bm_instance,
            volume=volume, volume_access_path_gateway_ips=volume_access_path_gateway_ips)


class VolumeController(RestController):

    attach = AttachController()
    detach = DetachController()

    def __init__(self):
        super(VolumeController, self).__init__()
