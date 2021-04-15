import bm_instance_agent
import os
import shutil

from jinja2 import Template
from oslo_concurrency import processutils
from oslo_log import log as logging

from bm_instance_agent.common import utils as agent_utils
from bm_instance_agent.systems.linux import driver as linux_driver

LOG = logging.getLogger(__name__)


class KylinDriver(linux_driver.LinuxDriver):

    driver_name = 'kylin'

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
            lambda x : True if x.startswith('ifcfg-') else False,
            os.listdir('/etc/sysconfig/network-scripts/'))
        if 'ifcfg-lo' in exist_conf_files:
            exist_conf_files.remove('ifcfg-lo')
        for nic in instance_obj.nics:
            path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
                nic.iface_name)
            if os.path.exists(path):
                with open(path, 'r') as f:
                    content = f.read()
                    if nic.iface_name not in content \
                        or nic.ip_address not in content \
                        or nic.netmask not in content \
                        or nic.gateway not in content:
                        self._attach_port(nic)
                exist_conf_files.remove('ifcfg-{}'.format(nic.iface_name))
            else:
                self._attach_port(nic)

        # flush the iface and remove the conf file
        for name in exist_conf_files:
            iface_name = name.split('-')[-1]
            try:
                if '.' in iface_name:
                    # ifdown vlan nic
                    cmd = ['ifdown', iface_name]
                else:
                    # flush physical nic
                    cmd = ['ip', 'address', 'flush', 'dev', iface_name]
                processutils.execute(*cmd)
            except Exception as e:
                LOG.error(
                    "Failed to flush {}, error: {}".format(iface_name, e))
            os.remove('/etc/sysconfig/network-scripts/{}'.format(name))

    def _load_template(self):
        template_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'kylin_network_script.j2')
        with open(template_path, 'r') as f:
            return Template(f.read())

    def _write_network_conf(self, port):
        template = self._load_template()
        conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
            port.iface_name)
        conf = template.render(
            default_route=port.default_route,
            iface_name=port.iface_name,
            ip_address=port.ip_address,
            netmask=port.netmask,
            gateway=port.gateway,
            vlan_id=port.vlan_id)
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    def _attach_port(self, port):
        self._write_network_conf(port)

        cmd = ['ifdown', port.iface_name]
        processutils.execute(*cmd)

        cmd = ['ifup', port.iface_name]
        processutils.execute(*cmd)

    def attach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            self._attach_port(port)

    def detach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            # Ensure that the conf file exist because command ifdown
            # requires it.
            self._write_network_conf(port)

            cmd = ['ifdown', port.iface_name]
            processutils.execute(*cmd)

            conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
                port.iface_name)
            os.remove(conf_file_path)

    def update_default_route(
        self, instance_obj, old_network_obj, new_network_obj):
        """ Update the default route(gateway) on Kylin

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


class KylinV10ARM(KylinDriver):

    driver_name = 'kylin_v10_arm'
