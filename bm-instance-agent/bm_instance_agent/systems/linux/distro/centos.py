from oslo_concurrency import processutils
from oslo_log import log as logging

from bm_instance_agent.common import utils as agent_utils
from bm_instance_agent.systems.linux import driver as linux_driver
from bm_instance_agent import objects
from centos_network_config import CentOSNetworkConfig as config

LOG = logging.getLogger(__name__)


class CentOSDriver(linux_driver.LinuxDriver):
    driver_name = 'centos'

    def ping(self, instance_obj):
        # Check the network config corrent. Remove unusable configuration
        # file, generate required configuration file if the conf not exist.
        if instance_obj.nics is None:
            return
        for nic in instance_obj.nics:
            rectify = config.network_config_rectify(nic)
            if rectify:
                LOG.info('rectify network config of port {}'.format(nic.iface_name))
                self._attach_port(nic)

    def _attach_bond_port(self, port):
        parasObj = objects.BondPortParasObj.from_json(port.paras)
        config.if_down_up(port.iface_name)
        for slave in parasObj.slave_list:
            config.if_down_up(slave["iface_name"], True)
            config.if_down_up(slave["iface_name"])
        if port.vlan_if_name:
            config.if_down_up(port.vlan_if_name)

    def _attach_phy_port(self, port):
        if_name = port.iface_name
        if port.vlan_if_name:
            if_name = port.vlan_if_name
        config.if_down_up(if_name, True)
        config.if_down_up(if_name)

    def _attach_port(self, port):
        config.persist_network_config(port)
        if port.type == port.PORT_TYPE_BOND:
            self._attach_bond_port(port)
        else:
            self._attach_phy_port(port)

    def attach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            self._attach_port(port)

    def _detach_bond_port(self, port):
        config.if_down_up(port.iface_name, True)

        bond_port = objects.BondPortParasObj.from_json(port.paras)
        for slave in bond_port.slave_list:
            config.if_down_up(slave["iface_name"], True)
        if port.vlan_if_name:
            config.if_down_up(port.vlan_if_name, True)

    def _detach_phy_port(self, port):
        if_name = port.iface_name
        if port.vlan_if_name:
            if_name = port.vlan_if_name
        config.if_down_up(if_name, True)

    def _detach_port(self, port):
        # Ensure that the conf file exist because command ifdown
        # requires it.
        config.persist_network_config(port)
        if port.type == port.PORT_TYPE_BOND:
            self._detach_bond_port(port)
        else:
            self._detach_phy_port(port)
        config.remove_network_config(port)

    def detach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            self._detach_port(port)

    def update_default_route(
            self, instance_obj, old_network_obj, new_network_obj):
        """ Update the default route(gateway) on CentOS

        If old_network_obj is not none, update the conf file.
        If new_network_obj is not none, update the conf file, change default
        gw if new gw is not equal to exist gw.
        """

        if old_network_obj:
            config.persist_network_config(old_network_obj.ports[0])

        agent_utils.ip_route_del('default')

        if new_network_obj:
            port = new_network_obj.ports[0]
            config.persist_network_config(port)

            cmd = ['ip', 'route', 'add', 'default', 'via',
                   port.gateway, 'dev', port.get_l3_interface()]
            processutils.execute(*cmd)


class CentOS8Driver(linux_driver.LinuxDriver):
    driver_name = 'centos8'

    def ping(self, instance_obj):
        # Check the network config corrent. Remove unusable configuration
        # file, generate required configuration file if the conf not exist.
        if instance_obj.nics is None:
            return
        for nic in instance_obj.nics:
            rectify = config.network_config_rectify(nic)
            if rectify:
                self._attach_port(nic)

    def _attach_bond_port(self, port):
        cmd = ['nmcli', 'con', 'reload']
        processutils.execute(*cmd)

        cmd = ['nmcli', 'con', 'up', port.iface_name]
        processutils.execute(*cmd)
        parasObj = objects.BondPortParasObj.from_json(port.paras)
        for slave in parasObj.slave_list:
            cmd = ['nmcli', 'con', 'up', agent_utils.get_nmcli_system_conn(slave["iface_name"])]
            processutils.execute(*cmd)

        if port.vlan_if_name:
            cmd = ['nmcli', 'con', 'up', port.vlan_if_name]
            processutils.execute(*cmd)

    def _attach_phy_port(self, port):
        cmd = ['nmcli', 'con', 'reload']
        processutils.execute(*cmd)

        if_name = port.iface_name
        if port.vlan_if_name:
            if_name = port.vlan_if_name

        cmd = ['nmcli', 'con', 'up', if_name]
        processutils.execute(*cmd)

    def _attach_port(self, port):
        config.persist_network_config(port)

        if port.type == port.PORT_TYPE_BOND:
            self._attach_bond_port(port)
        else:
            self._attach_phy_port(port)

    def attach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            self._attach_port(port)

    def _detach_port(self, port):
        if port.type == port.PORT_TYPE_BOND:
            if port.vlan_if_name:
                agent_utils.nmcli_conn_delete(port.vlan_if_name)

            agent_utils.nmcli_conn_delete(port.iface_name)
            bond_port = objects.BondPortParasObj.from_json(port.paras)
            for slave in bond_port.slave_list:
                agent_utils.nmcli_conn_delete(agent_utils.get_nmcli_system_conn(slave["iface_name"]))
        else:
            if_name = port.iface_name
            if port.vlan_if_name:
                if_name = port.vlan_if_name
            agent_utils.nmcli_conn_delete(if_name)

    def detach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            config.persist_network_config(port)
            self._detach_port(port)

    def update_default_route(
            self, instance_obj, old_network_obj, new_network_obj):
        """ Update the default route(gateway) on CentOS

        If old_network_obj is not none, update the conf file.
        If new_network_obj is not none, update the conf file, change default
        gw if new gw is not equal to exist gw.
        """

        if old_network_obj:
            config.persist_network_config(old_network_obj.ports[0])

        agent_utils.ip_route_del('default')

        if new_network_obj:
            port = new_network_obj.ports[0]
            config.persist_network_config(port)

            cmd = ['ip', 'route', 'add', 'default', 'via',
                   port.gateway, 'dev', port.get_l3_interface()]
            processutils.execute(*cmd)


class CentOSV7X86(CentOSDriver):
    driver_name = 'centos_v7_x86'


class CentOSV7ARM(CentOSDriver):
    driver_name = 'centos_v7_arm'


class CentOSV8X86(CentOS8Driver):
    driver_name = 'centos_v8_x86'


class CentOSV8ARM(CentOS8Driver):
    driver_name = 'centos_v8_arm'
