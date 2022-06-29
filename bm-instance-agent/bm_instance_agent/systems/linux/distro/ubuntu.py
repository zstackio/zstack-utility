import os
import shutil
import copy

from jinja2 import Template
from oslo_concurrency import processutils
from oslo_log import log as logging

from bm_instance_agent.common import utils as agent_utils
from bm_instance_agent.systems.linux import driver as linux_driver
from bm_instance_agent import objects

LOG = logging.getLogger(__name__)


class UbuntuDriver(linux_driver.LinuxDriver):
    driver_name = 'ubuntu'

    def ping(self, instance_obj):
        # Check the network config corrent. Remove unusable configuration
        # file, generate required configuration file if the conf not exist.
        if instance_obj.nics is None:
            return
        for nic in instance_obj.nics:
            prefix_size = agent_utils.convert_netmask(nic.netmask)
            ip_address = "{}/{}".format(nic.ip_address, prefix_size)
            l3_if = nic.get_l3_interface()
            path = '/etc/netplan/{}.yaml'.format(l3_if)
            content = ""
            if os.path.exists(path):
                with open(path, 'r') as f:
                    content = f.read()

            keywords = [nic.iface_name, ip_address, nic.gateway]
            if nic.vlan_if_name:
                keywords.append(nic.vlan_if_name)
            if any(key not in content for key in keywords):
                self._attach_port(nic)

    def _load_template(self):
        template_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'ubuntu_netplan_conf.j2')
        with open(template_path, 'r') as f:
            return Template(f.read())

    def _write_network_conf(self, port):
        prefix_size = agent_utils.convert_netmask(port.netmask)
        default_route = 'true' if port.default_route else 'false'
        template = self._load_template()
        conf_file_path = '/etc/netplan/{}.yaml'.format(port.get_l3_interface())
        conf = template.render(
            iface_name=port.iface_name,
            mac_address=port.mac,
            ip_address=port.ip_address,
            prefix_size=prefix_size,
            gateway=port.gateway,
            default_route=default_route,
            vlan_id=port.vlan_id)
        LOG.info('_write_network_conf conf={}'.format(conf))
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    bond_mode_transform = {
        "0": "balance-rr",
        "1": "active-backup",
        "2": "balance-xor",
        "3": "broadcast",
        "4": "802.3ad",
        "5": "balance-tlb",
        "6": "balance-alb"}

    def _write_network_bond_conf(self, port, paras):
        prefix_size = agent_utils.convert_netmask(port.netmask)
        default_route = 'true' if port.default_route else 'false'
        template = self._load_template()
        conf_file_path = '/etc/netplan/{}.yaml'.format(port.get_l3_interface())
        link_paras = copy.deepcopy(paras.link_paras)
        if "miimon" in link_paras.keys():
            link_paras["mii-monitor-interval"] = link_paras["miimon"]
            del link_paras["miimon"]
        if "mode" in link_paras.keys():
            link_paras["mode"] = self.bond_mode_transform[link_paras["mode"]]

        conf = template.render(
            type=port.type,
            iface_name=port.iface_name,
            mac_address=port.mac,
            ip_address=port.ip_address,
            prefix_size=prefix_size,
            gateway=port.gateway,
            default_route=default_route,
            vlan_id=port.vlan_id,
            slave_list=paras.slave_list,
            link_paras=link_paras)
        LOG.info('_write_network_bond_conf conf={}'.format(conf))
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    def _persist_network_config(self, port):
        if port.type == port.PORT_TYPE_BOND:
            paras = objects.BondPortParasObj.from_json(port.paras)
            self._write_network_bond_conf(port, paras)
        else:
            self._write_network_conf(port)

    def _attach_port(self, port):
        self._persist_network_config(port)

        cmd = ['netplan', 'apply']
        processutils.execute(*cmd)

    def attach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            self._attach_port(port)

    def detach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            conf_file_path = '/etc/netplan/{}.yaml'.format(port.get_l3_interface())
            agent_utils.remove_file(conf_file_path)

            cmd = ['netplan', 'apply']
            processutils.execute(*cmd)

            if port.vlan_if_name:
                agent_utils.ip_link_del(port.vlan_if_name)

            if port.type != port.PORT_TYPE_PHY:
                agent_utils.ip_link_del(port.iface_name)
            else:
                cmd = ['ip', 'address', 'flush', 'dev', port.iface_name]
                processutils.execute(*cmd)

    def update_default_route(
            self, instance_obj, old_network_obj, new_network_obj):
        """ Update the default route(gateway) on Ubuntu

        If old_network_obj is not none, update the conf file.
        If new_network_obj is not none, update the conf file, change default
        gw if new gw is not equal to exist gw.
        """

        if old_network_obj:
            self._persist_network_config(old_network_obj.ports[0])

        cmd = ['ip', 'route', 'delete', 'default']
        processutils.execute(*cmd)

        if new_network_obj:
            port = new_network_obj.ports[0]
            self._persist_network_config(port)

            cmd = ['ip', 'route', 'add', 'default', 'via',
                   port.gateway, 'dev', port.get_l3_interface()]
            processutils.execute(*cmd)
