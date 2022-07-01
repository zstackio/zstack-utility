import os

from jinja2 import Template
from oslo_concurrency import processutils
from oslo_log import log as logging

from bm_instance_agent.common import utils as agent_utils
from bm_instance_agent import objects

LOG = logging.getLogger(__name__)


class CentOSNetworkConfig:
    PORT_CONFIGTYPE_BOND = 'Bond'

    def __init__(self):
        self.if_name = None
        self.paras = None
        self.if_type = None
        self.ip_address = None
        self.default_route = None
        self.netmask = None
        self.gateway = None
        self.vlan_id = None
        self.master = None

    @classmethod
    def from_port_obj(cls, port):
        config = cls()
        config.if_name = port.iface_name
        config.ip_address = port.ip_address
        config.default_route = port.default_route
        config.netmask = port.netmask
        config.gateway = port.gateway
        config.vlan_id = port.vlan_id

        if port.type == port.PORT_TYPE_BOND:
            parasObj = objects.BondPortParasObj.from_json(port.paras)
            para_strs = 'BONDING_MASTER=yes\n'

            splice = []
            for key, value in parasObj.link_paras.items():
                splice.append(key + '=' + value)
            if len(splice) != 0:
                para_strs = para_strs + 'BONDING_OPTS="{paras}"\n'.format(paras=' '.join(splice))
            config.paras = para_strs
            config.if_type = cls.PORT_CONFIGTYPE_BOND

        return config

    @staticmethod
    def _load_template(temp_type=''):
        if temp_type == 'slave':
            template_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'centos_network_script_slave.j2')
        elif temp_type == 'underlay':
            template_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'centos_network_script_underlay.j2')
        else:
            template_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                'centos_network_script.j2')
        with open(template_path, 'r') as f:
            return Template(f.read())

    def _write_network_conf(self):
        template = CentOSNetworkConfig._load_template()
        conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
            self.if_name)
        conf = template.render(
            if_type=self.if_type,
            default_route=self.default_route,
            iface_name=self.if_name,
            ip_address=self.ip_address,
            netmask=self.netmask,
            gateway=self.gateway,
            vlan_id=self.vlan_id,
            paras=self.paras)
        LOG.info("_write_network_conf path={} conf= {}".format(conf_file_path, conf))
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    def _write_network_underlay_conf(self):
        template = CentOSNetworkConfig._load_template('underlay')
        conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
            self.if_name)
        conf = template.render(
            if_type=self.if_type,
            iface_name=self.if_name,
            paras=self.paras)
        LOG.info("_write_network_underlay_conf  path={} conf= {}".format(conf_file_path, conf))
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    def _write_network_slave_conf(self):
        template = CentOSNetworkConfig._load_template('slave')
        conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
            self.if_name)
        conf = template.render(
            iface_name=self.if_name,
            master=self.master)
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    @staticmethod
    def persist_network_config(port):
        port_config = CentOSNetworkConfig.from_port_obj(port)

        if port.type == port.PORT_TYPE_BOND:
            parasObj = objects.BondPortParasObj.from_json(port.paras)

            if port.vlan_if_name:
                # configure bond interface
                port_config._write_network_underlay_conf()
                # configure vlan interface, change some information.
                port_config.if_type = None
                port_config.paras = None
                port_config.if_name = port.vlan_if_name

            port_config._write_network_conf()
            # configure bond slave interfaces
            for slave in parasObj.slave_list:
                port_config.if_name = slave["iface_name"]
                port_config.master = slave["master"]
                port_config._write_network_slave_conf()
        else:
            if port.vlan_if_name:
                port_config.if_name = port.vlan_if_name
            port_config._write_network_conf()

    @staticmethod
    def remove_network_config(port):
        if port.type == port.PORT_TYPE_BOND:
            conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
                port.iface_name)
            agent_utils.remove_file(conf_file_path)

            bond_port = objects.BondPortParasObj.from_json(port.paras)
            for slave in bond_port.slave_list:
                conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
                    slave["iface_name"])
                agent_utils.remove_file(conf_file_path)
            if port.vlan_if_name:
                conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
                    port.vlan_if_name)
                agent_utils.remove_file(conf_file_path)
        else:
            if_name = port.iface_name
            if port.vlan_if_name:
                if_name = port.vlan_if_name
            conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
                if_name)
            agent_utils.remove_file(conf_file_path)

    @staticmethod
    def network_config_rectify(port):
        need_rectify = False
        overlay_if_name = port.iface_name
        if port.type == port.PORT_TYPE_BOND:
            # underlay check
            if port.vlan_id:
                path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
                    port.iface_name)
                if not os.path.exists(path):
                    return True
                overlay_if_name = port.vlan_if_name

            bondPort = objects.BondPortParasObj.from_json(port.paras)
            for slave in bondPort.slave_list:
                conf_file = 'ifcfg-{}'.format(slave["iface_name"])
                path = '/etc/sysconfig/network-scripts/{}'.format(conf_file)
                if not os.path.exists(path):
                    return True
        else:
            if port.vlan_if_name:
                overlay_if_name = port.vlan_if_name

        path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(overlay_if_name)
        content = ''
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read()
        ''' why '+ \n' ??
            for example: 
            we need '192.168.1.1, but the content is '192.168.1.11', 
            '192.168.1.1 in 192.168.1.11' is True, but we expect False
        '''
        keywords = [overlay_if_name + '\n', port.ip_address + '\n', port.netmask + '\n', port.gateway + '\n']
        if any(key not in content for key in keywords):
            need_rectify = True

        return need_rectify

    @staticmethod
    def if_down_up(if_name, down=False):
        cmd = 'ifdown' if down else 'ifup'
        cmd = [cmd, if_name]
        processutils.execute(*cmd)
        '''
        If NetworkManager is enabled on centos,
        we need to use nmcli to delete the configuration additionally.
        '''
        if down:
            try:
                path = '/sys/class/net/{}/bonding_slave'.format(if_name)
                conn_name = if_name if not os.path.exists(path) else agent_utils.get_nmcli_system_conn(if_name)
                cmd = ['nmcli', 'con', 'delete', conn_name]
                processutils.execute(*cmd)
            except:
                pass
