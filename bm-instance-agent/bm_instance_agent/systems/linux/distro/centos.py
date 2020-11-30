import os

from jinja2 import Template
from oslo_concurrency import processutils

from bm_instance_agent.systems.linux import driver as linux_driver


class CentOSDriver(linux_driver.LinuxDriver):

    driver_name = 'centos'

    def _load_template(self):
        template_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'centos_network_script.j2')
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

    def attach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            self._write_network_conf(port)

            cmd = ['ifdown', port.iface_name]
            processutils.execute(*cmd)

            cmd = ['ifup', port.iface_name]
            processutils.execute(*cmd)

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
        """ Update the default route(gateway) on CentOS

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


class CentOSV7X86(CentOSDriver):

    driver_name = 'centos_v7_x86'


class CentOSV7ARM(CentOSDriver):

    driver_name = 'centos_v7_arm'
