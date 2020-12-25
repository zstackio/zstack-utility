# Server Specific Configurations
# See https://pecan.readthedocs.org/en/latest/configuration.html#server-configuration # noqa
server = {
    'port': 7090,
    'host': '0.0.0.0'
}

# Pecan Application Configurations
# See https://pecan.readthedocs.org/en/latest/configuration.html#application-configuration # noqa
app = {
    'root': 'bm_instance_agent.api.controllers.root.RootController',
    'modules': ['bm_instance_agent.api'],
    'debug': False
}
