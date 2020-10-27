from oslo_log import log as logging
import pecan

from bm_instance_agent.api import config
from bm_instance_agent.api import hooks
from bm_instance_agent.api import middleware


LOG = logging.getLogger(__name__)


def get_pecan_config():
    filename = config.__file__.replace('.pyc', '.py')
    return pecan.configuration.conf_from_file(filename)


def setup_app(config=None):
    if not config:
        config = get_pecan_config()

    app_hooks = [
        hooks.ConfigHook(),
        hooks.DataFormatHook()
    ]

    app_conf = dict(config.app)

    app = pecan.make_app(
        app_conf.pop('root'),
        force_canonical=getattr(config.app, 'force_canonical', True),
        hooks=app_hooks,
        wrap_app=middleware.ParsableErrorMiddleware,
        **app_conf
    )

    return app
