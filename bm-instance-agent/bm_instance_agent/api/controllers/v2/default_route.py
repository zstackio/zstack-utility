from pecan.rest import RestController

from bm_instance_agent.api import utils as api_utils
from bm_instance_agent import manager


class ChangeController(RestController):

    def __init__(self):
        super(ChangeController, self).__init__()

    @api_utils.async_expose
    def post(self, old_default, new_default, bm_instance):
        agent_manager = manager.AgentManager()
        return agent_manager.update_default_route(
            bm_instance=bm_instance,
            old_default_port=old_default,
            new_default_port=new_default)


class DefaultRouteController(RestController):

    change = ChangeController()

    def __init__(self):
        super(DefaultRouteController, self).__init__()
