import copy
import os.path

from oslo_concurrency import processutils
from oslo_log import log as logging
import subprocess
import re
import time

from bm_instance_agent.common import utils as agent_utils
from bm_instance_agent import exception

from .centos_network_config import CentOSNetworkConfig as config
from .centos import CentOSDriver

LOG = logging.getLogger(__name__)
BOND_DRACUT_CONFIG_PATH = '/etc/dracut.conf.d/bonding.conf'


class KylinDriver(CentOSDriver):

    driver_name = 'kylin'

    def attach_port(self, instance_obj, network_obj):
        for port in network_obj.ports:
            self._attach_port(port)
            if port.type == port.PORT_TYPE_BOND \
                    and port.mac == instance_obj.provision_mac:
                self._write_bond_to_dracut_config(port)
                try:
                    subprocess.check_call(['dracut', '-f'])
                except subprocess.SubprocessError as e:
                    LOG.error("Failed to update dracut configuration: %s" % e)



    def detach_port(self, instance_obj, network_obj):
        provision_nic_restored = False
        for port in network_obj.ports:
            # Ensure that the conf file exist because command ifdown
            # requires it.
            if port.type == port.PORT_TYPE_BOND:
                if port.mac != instance_obj.provision_mac:
                    raise exception.NewtorkInterfaceConfigParasInvalid(
                        exception_msg="port type {} is not support".format(port.type))
                self._detach_provision_bond(port)
                provision_nic_restored = True
                continue
            self._detach_port(port)
        return provision_nic_restored

    def _detach_provision_bond(self, port):
        physical_port = copy.copy(port)
        physical_port.type = port.PORT_TYPE_PHY
        physical_port.iface_name = agent_utils.get_interface_by_mac(port.mac)
        old_config = None
        if os.path.exists(BOND_DRACUT_CONFIG_PATH):
            with open(BOND_DRACUT_CONFIG_PATH) as stream:
                old_config = stream.read()
        try:
            self._detach_port(port)
            self._attach_port(physical_port)
            with open(BOND_DRACUT_CONFIG_PATH, 'w') as stream:
                stream.write(
                    'add_dracutmodules+=" network "\n'
                    'kernel_cmdline+=" ip={interface}:dhcp bootdev={interface}"\n'.format(
                        interface=physical_port.iface_name))
            subprocess.check_call(['timeout', '-k', '5', '300', 'dracut', '-f'])
        except Exception as error:
            # The backend retains the Bond on failure, so restore its OS state.
            restore_errors = []
            try:
                if old_config is None:
                    agent_utils.remove_file(BOND_DRACUT_CONFIG_PATH)
                else:
                    with open(BOND_DRACUT_CONFIG_PATH, 'w') as stream:
                        stream.write(old_config)
            except Exception as restore_error:
                restore_errors.append(str(restore_error))
            try:
                self._attach_port(port)
            except Exception as restore_error:
                restore_errors.append(str(restore_error))
            if restore_errors:
                raise RuntimeError('failed to detach Bond: {}; failed to restore: {}'.format(
                    error, '; '.join(restore_errors)))
            raise

    def _write_bond_to_dracut_config(self, port):
        bonding_config = "/etc/sysconfig/network-scripts/ifcfg-%s" % port.iface_name
        if not os.path.exists(bonding_config):
            return

        slave_interfaces = self._read_slaves_from_sys(port.iface_name)
        bonding_opts = self._read_bonding_opts_from_ifcfg(bonding_config)
        content = (
            'add_dracutmodules+=" network "\n'
            'kernel_cmdline+=" bond={name}:{slaves}:{bonding_opts} ip={name}:dhcp bootdev={name}"\n'
        ).format(
            name=port.iface_name,
            slaves=slave_interfaces,
            bonding_opts=bonding_opts
        )

        try:
            with open(BOND_DRACUT_CONFIG_PATH, 'w') as stream:
                stream.write(content)
        except IOError as e:
            LOG.info("write config has error :%s" % e)

    def _read_slaves_from_sys(self, bond_name):
        slaves_file_path = '/sys/class/net/{}/bonding/slaves'.format(bond_name)
        max_retries = 3
        for attempt in range(3):
            try:
                with open(slaves_file_path, 'r') as f:
                    slaves = f.read().strip()

                if slaves:
                    LOG.info("the slaves file is %s", slaves)
                    return ','.join(slaves.split())

                LOG.warning("Attempt %d/%d: Slaves file is empty. Retrying...", attempt + 1, max_retries)
            except FileNotFoundError:
                LOG.error("Attempt %d/%d: Slaves file not found. Retrying...", attempt + 1, max_retries)

            time.sleep(3)

        LOG.error("Failed to read slaves after %d attempts.", max_retries)
        return None

    def _read_bonding_opts_from_ifcfg(self, ifcfg_file):
        bonding_opts = ""

        try:
            with open(ifcfg_file, 'r') as f:
                content = f.readlines()
                LOG.info("the bond ifcfg file is %s" % content)

            for line in content:
                match = re.search(r'^\s*BONDING_OPTS\s*=\s*"([^"]+)"', line)
                if match:
                    opts_str = match.group(1).strip()
                    bonding_opts = ','.join([opt.strip() for opt in opts_str.split()])
                    break

        except FileNotFoundError:
            LOG.error("Error: The file %s was not found." % ifcfg_file)
        except Exception as e:
            LOG.error("Failed to read bonding options from %s: %s" % (ifcfg_file, e))

        return bonding_opts

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
