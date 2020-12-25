from pecan.rest import RestController

from bm_instance_agent.api import utils as api_utils
from bm_instance_agent import manager


class AttachController(RestController):

    def __init__(self):
        super(AttachController, self).__init__()

    @api_utils.async_expose
    def post(self, nic, bm_instance):
        agent_manager = manager.AgentManager()
        return agent_manager.attach_port(
            bm_instance=bm_instance,
            port=nic)


class DetachController(RestController):

    def __init__(self):
        super(DetachController, self).__init__()

    @api_utils.async_expose
    def post(self, nic, bm_instance):
        agent_manager = manager.AgentManager()
        return agent_manager.detach_port(
            bm_instance=bm_instance,
            port=nic)


class NicController(RestController):

    attach = AttachController()
    detach = DetachController()

    def __init__(self):
        super(NicController, self).__init__()
