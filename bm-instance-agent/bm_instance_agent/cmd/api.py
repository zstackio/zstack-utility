import os
import sys

from oslo_config import cfg

from bm_instance_agent.common import service as agent_service


CONF = cfg.CONF


def main():
    # Parse config file and command line options, then start logging
    agent_service.prepare_service(sys.argv)

    # Build and start the WSGI app
    server = agent_service.WSGIService(
        'bm_instance_agent_api', CONF.api.enable_ssl_api)
    if os.name == 'nt':
        launcher = agent_service.thread_launcher()
        launcher.launch_service(server)
    else:
        launcher = agent_service.process_launcher()
        launcher.launch_service(server, workers=server.workers)
    launcher.wait()
