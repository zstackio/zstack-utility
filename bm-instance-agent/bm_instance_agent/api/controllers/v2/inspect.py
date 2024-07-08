from pecan.rest import RestController

from bm_instance_agent.api import utils as api_utils
from bm_instance_agent import manager


class InspectController(RestController):

    def __init__(self):
        super(InspectController, self).__init__()

    @api_utils.async_expose
    def post(self, provision_network, ipmi_address, ipmi_port):
        agent_manager = manager.AgentManager()
        return agent_manager.inspect(provision_network=provision_network,
                                     ipmi_address=ipmi_address, ipmi_port=ipmi_port)
