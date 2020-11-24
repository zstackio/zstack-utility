from pecan.rest import RestController

from bm_instance_agent.api import utils as api_utils
from bm_instance_agent import manager


class RebootController(RestController):

    def __init__(self):
        super(RebootController, self).__init__()

    @api_utils.async_expose
    def post(self, bm_instance):
        agent_manager = manager.AgentManager()
        return agent_manager.reboot(bm_instance=bm_instance)
