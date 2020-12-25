from pecan.rest import RestController

from bm_instance_agent.api import utils as api_utils
from bm_instance_agent import manager


class PrepareController(RestController):

    def __init__(self):
        super(PrepareController, self).__init__()

    @api_utils.sync_expose
    def get(self):
        agent_manager = manager.AgentManager()
        return agent_manager.console()


class ConsoleController(RestController):

    prepare = PrepareController()

    def __init__(self):
        super(ConsoleController, self).__init__()
