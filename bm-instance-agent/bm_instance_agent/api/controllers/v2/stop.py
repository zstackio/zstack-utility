from pecan.rest import RestController

from bm_instance_agent.api import utils as api_utils
from bm_instance_agent import manager


class StopController(RestController):

    def __init__(self):
        super(StopController, self).__init__()

    @api_utils.async_expose
    def post(self, bm_instance):
        agent_manager = manager.AgentManager()
        return agent_manager.stop(bm_instance=bm_instance)
