from pecan import expose
from pecan.rest import RestController

from bm_instance_agent.api.controllers import base
from bm_instance_agent.api.controllers import v2


class RootController(RestController):

    _versions = [base.API_V2]
    """All supported API versions"""

    _default_version = base.API_V2
    """The default API version"""

    v2 = v2.Controller()

    @expose(template='json')
    def get(self):
        return {
            'name': 'Baremetal instance agent',
            'description': ''
        }

    @expose()
    def _route(self, args, request=None):
        """Overrides the default routing behavior.

        It redirects the request to the default version of the cyborg API
        if the version number is not specified in the url.
        """

        if args[0] and args[0] not in self._versions:
            args = [self._default_version] + args
        return super(RootController, self)._route(args)
