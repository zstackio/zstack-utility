from oslo_concurrency import processutils
from oslo_log import log as logging

from bm_instance_agent.common import utils as agent_utils
from bm_instance_agent import exception

from centos_network_config import CentOSNetworkConfig as config
from centos import CentOSDriver

LOG = logging.getLogger(__name__)


class KylinDriver(CentOSDriver):

    driver_name = 'kylin'

    def attach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            if port.type == port.PORT_TYPE_BOND:
                raise exception.NewtorkInterfaceConfigParasInvalid(
                    exception_msg="port type {} is not support".format(port.type))
            self._attach_port(port)

    def detach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            # Ensure that the conf file exist because command ifdown
            # requires it.
            if port.type == port.PORT_TYPE_BOND:
                raise exception.NewtorkInterfaceConfigParasInvalid(
                    exception_msg="port type {} is not support".format(port.type))
            self._detach_port(port)

    def update_default_route(
            self, instance_obj, old_network_obj, new_network_obj):
        """ Update the default route(gateway) on CentOS

        If old_network_obj is not none, update the conf file.
        If new_network_obj is not none, update the conf file, change default
        gw if new gw is not equal to exist gw.
        """

        if old_network_obj:
            old_port = old_network_obj.ports[0]
            if old_port.type == old_port.PORT_TYPE_BOND:
                raise exception.NewtorkInterfaceConfigParasInvalid(
                    exception_msg="port type {} is not support".format(old_port.type))
            config.persist_network_config(old_port)

        agent_utils.ip_route_del('default')

        if new_network_obj:
            port = new_network_obj.ports[0]
            if old_port.type == old_port.PORT_TYPE_BOND:
                raise exception.NewtorkInterfaceConfigParasInvalid(
                    exception_msg="port type {} is not support".format(old_port.type))
            config.persist_network_config(port)

            cmd = ['ip', 'route', 'add', 'default', 'via',
                   port.gateway, 'dev', port.get_l3_interface()]
            processutils.execute(*cmd)


class KylinV10ARM(KylinDriver):

    driver_name = 'kylin_v10_arm'
