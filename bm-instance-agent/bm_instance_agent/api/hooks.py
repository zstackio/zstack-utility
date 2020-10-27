import copy

from oslo_config import cfg
from oslo_log import log as logging
from oslo_serialization import jsonutils
from pecan import hooks

from bm_instance_agent.common import utils as bm_utils


LOG = logging.getLogger(__name__)


class ConfigHook(hooks.PecanHook):

    def before(self, state):
        state.request.cfg = cfg.CONF


class DataFormatHook(hooks.PecanHook):

    def on_route(self, state):
        body = copy.deepcopy(state.request.body)
        if body:
            # NOTE(ya.wang) The body is byte type in py35, therefore use
            # jsonutils to safe load the body
            body = bm_utils.camel_obj_to_snake(jsonutils.loads(body))
            state.request.json_body = body
