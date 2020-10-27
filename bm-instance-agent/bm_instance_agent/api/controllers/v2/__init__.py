from pecan import expose
from pecan.rest import RestController

from bm_instance_agent.api.controllers.v2 import console
from bm_instance_agent.api.controllers.v2 import default_route
from bm_instance_agent.api.controllers.v2 import nic
from bm_instance_agent.api.controllers.v2 import password
from bm_instance_agent.api.controllers.v2 import ping
from bm_instance_agent.api.controllers.v2 import reboot
from bm_instance_agent.api.controllers.v2 import stop
from bm_instance_agent.api.controllers.v2 import volume


class Controller(RestController):

    _subcontroller_map = {
        'console': console.ConsoleController,
        'defaultRoute': default_route.DefaultRouteController,
        'nic': nic.NicController,
        'password': password.PasswordController,
        'ping': ping.PingController,
        'reboot': reboot.RebootController,
        'stop': stop.StopController,
        'volume': volume.VolumeController
    }

    # @expose()
    # def _lookup(self, bm_uuid, *remainder):
    #     if not remainder:
    #         return
    #     subcontroller = self._subcontroller_map.get(remainder[0])
    #     if subcontroller:
    #         return subcontroller(bm_uuid=bm_uuid), remainder[1:]

    @expose()
    def _lookup(self, *remainder):
        if not remainder:
            return
        subcontroller = self._subcontroller_map.get(remainder[0])
        if subcontroller:
            return subcontroller(), remainder[1:]

    @expose(template='json')
    def get(self):
        return {
            'name': 'Baremetal instance agent v2',
            'description': ''
        }


__all__ = ('Controller',)
