from pecan.rest import RestController

from bm_instance_agent.api import utils as api_utils
from bm_instance_agent import manager


class ChangeController(RestController):

    def __init__(self):
        super(ChangeController, self).__init__()

    @api_utils.async_expose
    def post(self, username, password, bm_instance):
        agent_manager = manager.AgentManager()
        return agent_manager.update_password(
            bm_instance=bm_instance,
            username=username,
            password=password)


class PasswordController(RestController):

    change = ChangeController()

    def __init__(self):
        super(PasswordController, self).__init__()
