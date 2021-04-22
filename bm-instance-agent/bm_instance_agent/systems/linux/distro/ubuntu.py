import bm_instance_agent
import os
import shutil

from jinja2 import Template
from oslo_concurrency import processutils
from oslo_log import log as logging

from bm_instance_agent.common import utils as agent_utils
from bm_instance_agent.systems.linux import driver as linux_driver

LOG = logging.getLogger(__name__)


class UbuntuDriver(linux_driver.LinuxDriver):

    driver_name = 'ubuntu'

    def ping(self, instance_obj):
        iface_name = agent_utils.get_interface_by_mac(
            instance_obj.provision_mac)
        conf_dir = '/etc/netplan/'
        src_file = os.path.join(conf_dir, '{}.yaml'.format(iface_name))
        dst_file = os.path.join(conf_dir, '.{}.yaml.bck'.format(iface_name))
        if os.path.exists(src_file):
            os.chmod(src_file, 0o000)
            shutil.move(src_file, dst_file)

        # Check the network config corrent. Remove unusable configuration
        # file, generate required configuration file if the conf not exist.
        if instance_obj.nics is None:
            return
        exist_conf_files = filter(
            lambda x : True if x.endswith('yaml') else False,
            os.listdir('/etc/netplan/'))
        for nic in instance_obj.nics:
            prefix_size = agent_utils.convert_netmask(nic.netmask)
            ip_address = "{}/{}".format(nic.ip_address, prefix_size)
            path = '/etc/netplan/{}.yaml'.format(nic.iface_name)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    content = f.read()
                    if nic.iface_name not in content \
                        or ip_address not in content \
                        or nic.gateway not in content \
                        or nic.mac not in content:
                        self._attach_port(nic)
                exist_conf_files.remove('{}.yaml'.format(nic.iface_name))
            else:
                self._attach_port(nic)

        # flush the iface and remove the conf file
        for name in exist_conf_files:
            iface_name = name[:-5]
            try:
                if '.' in iface_name:
                    # ifdown vlan nic
                    cmd = ['ip', 'link', 'delete', iface_name]
                else:
                    # flush physical nic
                    cmd = ['ip', 'address', 'flush', 'dev', iface_name]
                processutils.execute(*cmd)
            except Exception as e:
                LOG.error(
                    "Failed to flush {}, error: {}".format(iface_name, e))
            os.remove('/etc/netplan/{}'.format(name))

    def _load_template(self):
        template_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'ubuntu_netplan_conf.j2')
        with open(template_path, 'r') as f:
            return Template(f.read())

    def _write_network_conf(self, port):
        iface_name = port.iface_name.split('.')[0]
        prefix_size = agent_utils.convert_netmask(port.netmask)
        default_route = 'true' if port.default_route else 'false'
        template = self._load_template()
        conf_file_path = '/etc/netplan/{}.yaml'.format(port.iface_name)
        conf = template.render(
            iface_name=iface_name,
            mac_address=port.mac,
            ip_address=port.ip_address,
            prefix_size=prefix_size,
            gateway=port.gateway,
            default_route=default_route,
            vlan_id=port.vlan_id)
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    def _attach_port(self, port):
        self._write_network_conf(port)

        cmd = ['netplan', 'apply']
        processutils.execute(*cmd)

    def attach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            self._attach_port(port)

    def detach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            conf_file_path = '/etc/netplan/{}.yaml'.format(port.iface_name)
            os.remove(conf_file_path)

            cmd = ['netplan', 'apply']
            processutils.execute(*cmd)

            if '.' in port.iface_name:
                cmd = ['ip', 'link', 'delete', port.iface_name]
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
            self._write_network_conf(old_network_obj.ports[0])

        cmd = ['ip', 'route', 'delete', 'default']
        processutils.execute(*cmd)

        if new_network_obj:
            port = new_network_obj.ports[0]
            self._write_network_conf(port)

            cmd = ['ip', 'route', 'add', 'default', 'via',
                   port.gateway, 'dev', port.iface_name]
            processutils.execute(*cmd)
