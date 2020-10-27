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
            gateway=port.gateway)
        with open(conf_file_path, 'w') as f:
            f.write(conf)

    def _post_attach_port(self, instance_obj, network_obj):
        """ Setup configuration files
        """
        for port in network_obj.ports:
            self._write_network_conf(port)
        # FIXME(ya.wang) Should we restart/enable networking service here?

    def _post_detach_port(self, instance_obj, network_obj):
        """ Clean network configuration
        """
        for port in network_obj.ports:
            conf_file_path = '/etc/sysconfig/network-scripts/ifcfg-{}'.format(
                port.iface_name)
            if os.path.exists(conf_file_path):
                os.remove(conf_file_path)

    def update_default_route(
        self, instance_obj, old_network_obj, new_network_obj):
        """ Update the default route(gateway) on CentOS

        If old_network_obj is not none, update the conf file.
        If new_network_obj is not none, update the conf file, change default
        gw if new gw is not equal to exist gw.
        """

        # # Clean old gateway
        # gw_addr, gw_iface = bm_utils.get_gateway()
        # if not gw_addr and not old_network_obj.gateway:
        #     return

        # if gw_addr:
        #     if not gw_addr == old_network_obj.gateway:
        #         raise exception.DefaultGatewayAddressNotEqual(
        #             old_address=old_network_obj.ip_address,
        #             exist_address=gw_addr)
        #     cmd = ['ip', 'route', 'delete', 'default', 'via', gw_addr,
        #            'dev', gw_iface]
        #     processutils.execute(*cmd)

        # self._write_network_conf(old_network_obj)

        # # Add new gateway
        # if not new_network_obj.gateway:
        #     return

        # cmd = ['ip', 'route', 'add', 'default', 'via',
        #        new_network_obj.gateway, 'dev', new_network_obj.iface_name]
        # processutils.execute(*cmd)

        # self._write_network_conf(new_network_obj)
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
