from oslo_config import cfg

from bm_instance_agent.conf import api


CONF = cfg.CONF


api.register_opts(CONF)
