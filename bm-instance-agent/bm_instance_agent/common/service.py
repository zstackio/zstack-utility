import time

from oslo_config import cfg
from oslo_log import log as logging
from oslo_service import service
from oslo_service import wsgi

from bm_instance_agent.api import app
from bm_instance_agent.conf import CONF
from bm_instance_agent import exception


LOG = logging.getLogger(__name__)


def parse_args(argv, default_config_files=None):
    cfg.CONF(argv[1:],
             project='bm-instance-agent',
             default_config_files=default_config_files)


def prepare_service(argv=None):
    logging.register_options(CONF)
    logging.set_defaults(default_log_levels=CONF.default_log_levels)

    argv = argv or []
    parse_args(argv)

    logging.setup(CONF, 'bm-instance-agent')


def process_launcher():
    return service.ProcessLauncher(CONF, restart_method='mutate')


def thread_launcher():
    return service.ServiceLauncher(CONF, restart_method='mutate')


class WSGIService(service.ServiceBase):
    """Provides ability to launch bm-instance-agent from wsgi app."""

    def __init__(self, name, use_ssl=False):
        """Initialize, but do not start the WSGI server.

        :param name: The name of the WSGI server given to the loader.
        :param use_ssl: Wraps the socket in an SSL context if True.
        :returns: None
        """
        self.name = name
        self.app = app.setup_app()
        # The agent works lightly, no more workers need
        self.workers = CONF.api.api_workers or 1
        if self.workers and self.workers < 1:
            raise exception.ConfigInvalid(
                ("api_workers value of %d is invalid, "
                 "must be greater than 0.") % self.workers)

        self.server = wsgi.Server(CONF, self.name, self.app,
                                  host=CONF.api.host_ip,
                                  port=CONF.api.port,
                                  use_ssl=use_ssl)

    def start(self):
        """Start serving this service using loaded configuration.

        :returns: None
        """
        self.server.start()

    def stop(self):
        """Stop serving this API.

        :returns: None
        """
        # NOTE: Sleep 3 seconds to send the api callback
        time.sleep(3)
        self.server.stop()

    def wait(self):
        """Wait for the service to stop serving this API.

        :returns: None
        """
        self.server.wait()

    def reset(self):
        """Reset server greenpool size to default.

        :returns: None
        """
        self.server.reset()
