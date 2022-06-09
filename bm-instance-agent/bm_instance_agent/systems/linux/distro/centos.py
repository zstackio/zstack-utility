import copy

import os
import shutil

from jinja2 import Template
from oslo_concurrency import processutils
from oslo_log import log as logging

from bm_instance_agent.common import utils as agent_utils
from bm_instance_agent.systems.linux import driver as linux_driver
from bm_instance_agent import objects

LOG = logging.getLogger(__name__)


def get_vlan_port(port):
    vlan_port = copy.deepcopy(port)
    vlan_port.type = port.PORT_TYPE_VLAN
    setattr(vlan_port, 'underlay_if_name', port.iface_name)
    setattr(vlan_port, "conf_if_name", port.vlan_if_name)
    return vlan_port


class CentOSNetworkConfigOpt:
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

    @staticmethod
    def _write_network_conf(port):
        template = CentOSNetworkConfigOpt._load_template()
        conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
            port.conf_if_name)
        conf = template.render(
            if_type=port.conf_type,
            default_route=port.default_route,
            iface_name=port.conf_if_name,
            ip_address=port.ip_address,
            netmask=port.netmask,
            gateway=port.gateway,
            vlan_id=port.vlan_id,
            paras=port.conf_paras)
        LOG.info("_write_network_conf path={} conf= {}".format(conf_file_path, conf))
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    @staticmethod
    def _write_network_underlay_conf(port):
        template = CentOSNetworkConfigOpt._load_template('underlay')
        conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
            port.conf_if_name)
        conf = template.render(
            if_type=port.conf_type,
            iface_name=port.conf_if_name,
            paras=port.conf_paras)
        LOG.info("_write_network_underlay_conf  path={} conf= {}".format(conf_file_path, conf))
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    @staticmethod
    def _write_network_slave_conf(slave):
        template = CentOSNetworkConfigOpt._load_template('slave')
        conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
            slave["iface_name"])
        conf = template.render(
            iface_name=slave["iface_name"],
            master=slave["master"])
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    @staticmethod
    def persist_network_config(port):
        setattr(port, "conf_paras", None)
        setattr(port, "conf_type", None)
        setattr(port, "conf_if_name", port.iface_name)
        overlay_port = port
        if port.vlan_id:
            overlay_port = get_vlan_port(port)

        if port.type == port.PORT_TYPE_BOND:
            parasObj = objects.BondPortParasObj.from_json(port.paras)
            para_strs = 'BONDING_MASTER=yes\n'
            splice = []
            for key, value in parasObj.link_paras.items():
                splice.append(key + '=' + value)

            if len(splice) != 0:
                para_strs = para_strs + 'BONDING_OPTS="{paras}"\n'.format(paras=' '.join(splice))

            setattr(port, "conf_paras", para_strs)
            setattr(port, "conf_type", "Bond")
            if port.vlan_id:
                CentOSNetworkConfigOpt._write_network_underlay_conf(port)
            ''' overlay_port == port if not port.vlan_id
            '''
            CentOSNetworkConfigOpt._write_network_conf(overlay_port)

            for slave in parasObj.slave_list:
                CentOSNetworkConfigOpt._write_network_slave_conf(slave)
        else:
            CentOSNetworkConfigOpt._write_network_conf(overlay_port)

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
    def network_config_rectify(port, exist_conf_files):
        need_rectify = False
        overlay_if_name = port.iface_name
        if port.type == port.PORT_TYPE_BOND:
            # underlay check
            if port.vlan_id:
                path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
                    port.iface_name)
                if os.path.exists(path):
                    conf_file = 'ifcfg-{}'.format(port.iface_name)
                    if conf_file in exist_conf_files:
                        exist_conf_files.remove(conf_file)
                else:
                    need_rectify = True
                overlay_if_name = port.vlan_if_name

            bondPort = objects.BondPortParasObj.from_json(port.paras)
            for slave in bondPort.slave_list:
                conf_file = 'ifcfg-{}'.format(slave["iface_name"])
                path = '/etc/sysconfig/network-scripts/{}'.format(conf_file)
                if os.path.exists(path):
                    if conf_file in exist_conf_files:
                        exist_conf_files.remove(conf_file)
                else:
                    need_rectify = True
        else:
            if port.vlan_if_name:
                overlay_if_name = port.vlan_if_name

        path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(overlay_if_name)
        if os.path.exists(path):
            with open(path, 'r') as f:
                content = f.read()
                if overlay_if_name + '\n' not in content \
                        or port.ip_address + '\n' not in content \
                        or port.netmask + '\n' not in content \
                        or port.gateway + '\n' not in content:
                    need_rectify = True
            exist_conf_files.remove('ifcfg-{}'.format(overlay_if_name))
        else:
            need_rectify = True
        return need_rectify

    @staticmethod
    def if_down_up(if_name, down=False):
        cmd = 'ifdown' if down else 'ifup'
        cmd = [cmd, if_name]
        processutils.execute(*cmd)

    @staticmethod
    def nmcli_reload():
        try:
            cmd = ['nmcli', 'con', 'reload']
            processutils.execute(*cmd)
        except:
            pass


class CentOSDriver(linux_driver.LinuxDriver):
    driver_name = 'centos'

    def ping(self, instance_obj):
        iface_name = agent_utils.get_interface_by_mac(
            instance_obj.provision_mac)
        conf_dir = '/etc/sysconfig/network-scripts'
        src_file = os.path.join(conf_dir, 'ifcfg-{}'.format(iface_name))
        dst_file = os.path.join(conf_dir, '.ifcfg-{}'.format(iface_name))
        if os.path.exists(src_file):
            os.chmod(src_file, 0o000)
            shutil.move(src_file, dst_file)

        # Check the network config corrent. Remove unusable configuration
        # file, generate required configuration file if the conf not exist.
        if instance_obj.nics is None:
            return
        exist_conf_files = filter(
            lambda x: True if x.startswith('ifcfg-') else False,
            os.listdir('/etc/sysconfig/network-scripts/'))
        if 'ifcfg-lo' in exist_conf_files:
            exist_conf_files.remove('ifcfg-lo')
        for nic in instance_obj.nics:
            rectify = CentOSNetworkConfigOpt.network_config_rectify(nic, exist_conf_files)
            if rectify:
                LOG.info('rectify network config of port {}'.format(nic.iface_name))
                self._attach_port(nic)

        # flush the iface and remove the conf file
        for name in exist_conf_files:
            iface_name = name.split('-')[-1]
            try:
                if not agent_utils.is_physical_interface(iface_name):
                    # ifdown vlan nic
                    CentOSNetworkConfigOpt.if_down_up(iface_name, True)
                else:
                    # flush physical nic
                    cmd = ['ip', 'address', 'flush', 'dev', iface_name]
                    processutils.execute(*cmd)
            except Exception as e:
                LOG.error(
                    "Failed to flush {}, error: {}".format(iface_name, e))
            agent_utils.remove_file('/etc/sysconfig/network-scripts/{}'.format(name))
            CentOSNetworkConfigOpt.nmcli_reload()

    def _attach_bond_port(self, port):
        parasObj = objects.BondPortParasObj.from_json(port.paras)
        CentOSNetworkConfigOpt.if_down_up(port.iface_name)
        for slave in parasObj.slave_list:
            CentOSNetworkConfigOpt.if_down_up(slave["iface_name"], True)
            CentOSNetworkConfigOpt.if_down_up(slave["iface_name"])
        if port.vlan_if_name:
            CentOSNetworkConfigOpt.if_down_up(port.vlan_if_name)

    def _attach_phy_port(self, port):
        if_name = port.iface_name
        if port.vlan_if_name:
            if_name = port.vlan_if_name
        CentOSNetworkConfigOpt.if_down_up(if_name, True)
        CentOSNetworkConfigOpt.if_down_up(if_name)

    def _attach_port(self, port):
        CentOSNetworkConfigOpt.persist_network_config(port)
        if port.type == port.PORT_TYPE_BOND:
            self._attach_bond_port(port)
        else:
            self._attach_phy_port(port)

    def attach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            self._attach_port(port)

    def _detach_bond_port(self, port):
        CentOSNetworkConfigOpt.if_down_up(port.iface_name, True)

        bond_port = objects.BondPortParasObj.from_json(port.paras)
        for slave in bond_port.slave_list:
            CentOSNetworkConfigOpt.if_down_up(slave["iface_name"], True)
        if port.vlan_if_name:
            CentOSNetworkConfigOpt.if_down_up(port.vlan_if_name, True)

    def _detach_phy_port(self, port):
        if_name = port.iface_name
        if port.vlan_if_name:
            if_name = port.vlan_if_name
        CentOSNetworkConfigOpt.if_down_up(if_name, True)

    def _detach_port(self, port):
        if port.type == port.PORT_TYPE_BOND:
            self._detach_bond_port(port)
        else:
            self._detach_phy_port(port)

    def detach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            # Ensure that the conf file exist because command ifdown
            # requires it.
            CentOSNetworkConfigOpt.persist_network_config(port)
            self._detach_port(port)
            CentOSNetworkConfigOpt.remove_network_config(port)
            CentOSNetworkConfigOpt.nmcli_reload()

    def update_default_route(
            self, instance_obj, old_network_obj, new_network_obj):
        """ Update the default route(gateway) on CentOS

        If old_network_obj is not none, update the conf file.
        If new_network_obj is not none, update the conf file, change default
        gw if new gw is not equal to exist gw.
        """

        if old_network_obj:
            CentOSNetworkConfigOpt.persist_network_config(old_network_obj.ports[0])

        agent_utils.ip_route_del('default')

        if new_network_obj:
            port = new_network_obj.ports[0]
            CentOSNetworkConfigOpt.persist_network_config(port)

            cmd = ['ip', 'route', 'add', 'default', 'via',
                   port.gateway, 'dev', port.get_l3_interface()]
            processutils.execute(*cmd)


class CentOS8Driver(linux_driver.LinuxDriver):
    driver_name = 'centos8'

    def ping(self, instance_obj):
        iface_name = agent_utils.get_interface_by_mac(
            instance_obj.provision_mac)
        conf_dir = '/etc/sysconfig/network-scripts'
        src_file = os.path.join(conf_dir, 'ifcfg-{}'.format(iface_name))
        dst_file = os.path.join(conf_dir, '.ifcfg-{}'.format(iface_name))
        if os.path.exists(src_file):
            os.chmod(src_file, 0o000)
            shutil.move(src_file, dst_file)

        # Check the network config corrent. Remove unusable configuration
        # file, generate required configuration file if the conf not exist.
        if instance_obj.nics is None:
            return
        exist_conf_files = filter(
            lambda x: True if x.startswith('ifcfg-') else False,
            os.listdir('/etc/sysconfig/network-scripts/'))
        if 'ifcfg-lo' in exist_conf_files:
            exist_conf_files.remove('ifcfg-lo')
        for nic in instance_obj.nics:
            rectify = CentOSNetworkConfigOpt.network_config_rectify(nic, exist_conf_files)
            if rectify:
                self._attach_port(nic)

        # flush the iface and remove the conf file
        for name in exist_conf_files:
            iface_name = name.split('-')[-1]
            try:
                if not agent_utils.is_physical_interface(iface_name):
                    # ifdown vlan nic
                    cmd = ['nmcli', 'con', 'delete', iface_name]
                    agent_utils.nmcli_conn_delete(iface_name)
                else:
                    # flush physical nic
                    cmd = ['ip', 'address', 'flush', 'dev', iface_name]
                    processutils.execute(*cmd)
            except Exception as e:
                LOG.error(
                    "Failed to flush {}, error: {}".format(iface_name, e))
            agent_utils.remove_file('/etc/sysconfig/network-scripts/{}'.format(name))

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
        CentOSNetworkConfigOpt.persist_network_config(port)

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
            CentOSNetworkConfigOpt.persist_network_config(port)
            self._detach_port(port)

    def update_default_route(
            self, instance_obj, old_network_obj, new_network_obj):
        """ Update the default route(gateway) on CentOS

        If old_network_obj is not none, update the conf file.
        If new_network_obj is not none, update the conf file, change default
        gw if new gw is not equal to exist gw.
        """

        if old_network_obj:
            CentOSNetworkConfigOpt.persist_network_config(old_network_obj.ports[0])

        agent_utils.ip_route_del('default')

        if new_network_obj:
            port = new_network_obj.ports[0]
            CentOSNetworkConfigOpt.persist_network_config(port)

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
