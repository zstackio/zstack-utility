import os
import re
import glob

from collections import OrderedDict

from zstacklib.utils import log
from zstacklib.utils import shell

logger = log.get_logger(__name__)

NET_CONFIG_PATH = '/etc/sysconfig/network-scripts'

NET_CONFIG_IPV4 = 4
NET_CONFIG_IPV6 = 6

NET_CONFIG_MTU_MIN = 576
NET_CONFIG_MTU_MAX = 9000
NET_CONFIG_MTU_DEFAULT = 1500

NET_CONFIG_VLAN_TYPE = 'VLAN'
NET_CONFIG_BRIDGE_TYPE = 'BRIDGE'
NET_CONFIG_BOND_TYPE = 'BOND'
NET_CONFIG_ETHER_TYPE = 'ETHER'

NET_CONFIG_BOOTPROTO_STATIC = 'static'
NET_CONFIG_BOOTPROTO_DHCP = 'dhcp'
NET_CONFIG_BOOTPROTO_NONE = 'none'

NET_CONFIG_ONBOOT_YES = 'yes'
NET_CONFIG_ONBOOT_NO = 'no'

NET_CONFIG_STP_YES = 'yes'
NET_CONFIG_STP_NO = 'no'

NET_CONFIG_NM_CONTROLLED_YES = 'yes'
NET_CONFIG_NM_CONTROLLED_NO = 'no'

NET_CONFIG_SERVICE_TYPE_NMCLI = 'NetworkManager'
NET_CONFIG_SERVICE_TYPE_NORMAL = 'network'


class NetConfigError(Exception):
    '''net config error'''


class IpConfig(object):
    '''netconfig: ip config'''

    def __init__(self, ip, netmask, gateway=None):
        self.ip = ip
        self.netmask = netmask
        self.gateway = gateway
        self.version = NET_CONFIG_IPV4
        self.priority = None
        self.is_default = False


class NetConfig(object):
    '''netconfig: net config'''

    def __init__(self, name, link_type=None):
        self.name = name
        self.device = None
        self.link_type = link_type
        self.boot_mode = NET_CONFIG_ONBOOT_YES
        self.boot_proto = NET_CONFIG_BOOTPROTO_NONE
        self.mtu = None
        self.alias = None
        self.config_dict = None
        self.ip_configs = []
        self.service_type = self._get_service_type()
        self.config_path = self._get_config_path()
        self._build_config()

    def _get_service_type(self):
        '''netconfig: get network service type(network or NetworkManager)'''
        cmd = shell.ShellCmd('nmcli general status')
        cmd(is_exception=False)
        if cmd.return_code == 0:
            return NET_CONFIG_SERVICE_TYPE_NMCLI

        return NET_CONFIG_SERVICE_TYPE_NORMAL

    def _get_config_path(self):
        '''netconfig: get network config path'''
        if os.path.exists(NET_CONFIG_PATH):
            return NET_CONFIG_PATH

        return None

    def add_ip_config(self, ip, netmask, gateway=None, version=NET_CONFIG_IPV4, is_default=False):
        '''add ip config'''
        ip_config = None
        for item in self.ip_configs:
            if item.ip == ip:
                ip_config = item
                break
        if ip_config is None:
            ip_config = IpConfig(ip=ip, netmask=netmask)

        if gateway:
            ip_config.gateway = gateway
            ip_config.is_default = is_default
        ip_config.version = version
        self.ip_configs.append(ip_config)

    def get_ip_configs(self):
        '''get ip config'''
        return self.ip_configs

    def delete_ip_config(self, ip):
        '''delete ip config'''
        self.ip_configs = [ip_config for ip_config in self.ip_configs if ip_config.ip != ip]

    def add_config(self, key, value):
        '''netconfig: add config(key=value) to config_dict'''
        if self.config_dict is None:
            self.config_dict = OrderedDict()
        if not key or not value:
            return
        self.config_dict[key] = value

    def pre_restore_config(self):
        '''netconfig: pre restore config'''

    def post_restore_config(self):
        '''netconfig: post restore config'''

    def build_ifcfg_file(self):
        '''netconfig: build ifcfg file'''
        self.add_config('NAME', self.name)
        self.add_config('DEVICE', self.device if self.device else self.name)
        self.add_config('ONBOOT', self.boot_mode)
        self.add_config('BOOTPROTO', self.boot_proto)
        if self.mtu:
            self.add_config('MTU', self.mtu)
        if self.alias:
            self.add_config('ALIAS', '"{}"'.format(self.alias))

    def build_ip_config(self):
        if not self.ip_configs:
            return []
        ip_list = []
        ip_dict = {}
        primary_ip_config = None
        secondary_ip_list = []

        for ip_config in self.ip_configs:
            if ip_config.is_default:
                primary_ip_config = ip_config
            else:
                secondary_ip_list.append(ip_config)

        if not primary_ip_config:
            primary_ip_config = secondary_ip_list.pop(0)

        if primary_ip_config:
            ip_dict[primary_ip_config.ip] = primary_ip_config
            ip_list.append('IPADDR=%s' % primary_ip_config.ip)
            ip_list.append('NETMASK=%s' % primary_ip_config.netmask)
            if primary_ip_config.gateway:
                ip_list.append('GATEWAY=%s' % primary_ip_config.gateway)
                ip_list.append('DEFROUTE=yes')

        for index, ip_config in enumerate(secondary_ip_list):
            if ip_config.ip in ip_dict:
                continue
            ip_dict[ip_config.ip] = ip_config
            ip_index = index + 1
            ip_list.append('IPADDR%s=%s' % (ip_index, ip_config.ip))
            ip_list.append('NETMASK%s=%s' % (ip_index, ip_config.netmask))
            if ip_config.gateway:
                ip_list.append('GATEWAY%s=%s' % (ip_index, ip_config.gateway))

        return ip_list

    def check_config(self):
        if not self.name or len(self.name) > 15:
            raise NetConfigError('configure error, netdev name must be between 1 and 15 characters')
        if not self.link_type and 'TYPE' not in self.config_dict:
            raise NetConfigError('configure error, can not get link type')
        if self.mtu and (self.mtu < NET_CONFIG_MTU_MIN or self.mtu > NET_CONFIG_MTU_MAX):
            raise NetConfigError('configure error, netdev mtu must be between 576 and 9000')
        if not self.boot_mode or not self.boot_proto:
            raise NetConfigError('configure error, boot mode and boot protocol must be specified')
        if self.boot_mode not in [NET_CONFIG_ONBOOT_YES, NET_CONFIG_ONBOOT_NO]:
            raise NetConfigError('configure error, boot mode must be yes or no')
        if self.boot_proto not in [NET_CONFIG_BOOTPROTO_STATIC, NET_CONFIG_BOOTPROTO_DHCP, NET_CONFIG_BOOTPROTO_NONE]:
            raise NetConfigError('configure error, boot protocol must be static, dhcp or none')
        if self.boot_proto == NET_CONFIG_BOOTPROTO_DHCP and self.ip_configs:
            raise NetConfigError('configure error, unable to set ip when boot protocol is [dhcp]')
        if not self.config_path:
            raise NetConfigError('configure error, ifcfg config path must be specified')
        if not self.service_type:
            raise NetConfigError('configure error, can not get network service type')

        default_count = 0
        for ip_config in self.ip_configs:
            if not ip_config.ip or not ip_config.netmask:
                raise NetConfigError('configure error, ip or netmask is empty')
            if ip_config.version == NET_CONFIG_IPV4 and not is_ipv4(ip_config.ip):
                raise NetConfigError('configure error, ip[%s] is not ipv4 address' % ip_config.ip)
            if ip_config.is_default:
                default_count += 1
        if default_count > 1:
            raise NetConfigError('configure error, only one ip can be default')

    def restore_config(self, is_reload=False):
        '''restore config'''
        self.check_config()
        self.pre_restore_config()
        self.build_ifcfg_file()
        if not self.config_dict:
            raise NetConfigError('configure error, ifcfg content is empty')

        config_list = ['# Auto generated by zstack']
        config_list.extend(['{}={}'.format(k, v) for k, v in self.config_dict.items()])
        ip_list = self.build_ip_config()
        config_list.extend(ip_list)

        ifcfg_content = '\n'.join(config_list) + '\n'

        ifcfg_file_path = os.path.join(self.config_path, 'ifcfg-%s' % self.name)
        logger.debug('netconfig: type: %s, ifcfg file path: %s, content: %s' % (self.service_type, ifcfg_file_path, ifcfg_content))

        with open(ifcfg_file_path, 'w') as file:
            file.write(ifcfg_content)

        if self.service_type == NET_CONFIG_SERVICE_TYPE_NMCLI:
            shell.call('nmcli c load %s' % ifcfg_file_path)

        self.post_restore_config()

        if is_reload:
            if self.service_type == NET_CONFIG_SERVICE_TYPE_NMCLI:
                shell.call('nmcli c up %s' % self.name)
            else:
                shell.call('ifdown %s' % self.name)
                shell.call('ifup %s' % self.name)

    def delete_config(self):
        '''delete config'''
        if not self.config_path:
            raise NetConfigError('configure error, ifcfg config path must be specified')
        config_path = os.path.join(self.config_path, 'ifcfg-%s' % self.name)
        if os.path.exists(config_path):
            os.remove(config_path)
            logger.debug('delete interface[%s] ifcfg file successfully' % self.name)

    def flush_config(self):
        '''flush config'''
        if not self.config_path:
            raise NetConfigError('configure error, ifcfg config path must be specified')

        if 'BRIDGE' in self.config_dict:
            self.config_dict.pop('BRIDGE')

        self.restore_config()
        logger.debug('flush interface[%s] config successfully' % self.name)

    def _build_config(self):
        '''netconfig: build config'''
        if self.config_dict is None:
            self.config_dict = OrderedDict()

        raw_dict = self._parse_ifcfg_file()
        if not raw_dict:
            return

        for key, value in raw_dict.items():
            if key.startswith('IPADDR'):
                index = key[len('IPADDR'):]
                if 'NETMASK' + index in raw_dict:
                    netmask = raw_dict['NETMASK' + index]
                    gateway = raw_dict.get('GATEWAY' + index, None)
                    is_default = False
                    if gateway and 'DEFROUTE' + index in raw_dict:
                        default_route = raw_dict.get('DEFROUTE' + index)
                        if default_route == 'yes':
                            is_default = True

                    self.add_ip_config(value, netmask, gateway, is_default)
                    continue
            elif 'NETMASK' in key or 'GATEWAY' in key or 'DEFROUTE' in key or 'PREFIX' in key:
                continue
            else:
                self.add_config(key, value)

    def _parse_ifcfg_file(self):
        '''netconfig: parse ifcfg file'''
        ifcfg_file_path = os.path.join(self.config_path, 'ifcfg-%s' % self.name)
        if not os.path.exists(ifcfg_file_path):
            cmd = shell.ShellCmd('grep -r "DEVICE=%s" %s' % (self.name, self.config_path))
            cmd(is_exception=False)
            if cmd.return_code != 0:
                return None

            old_ifcfg_path = cmd.stdout.strip().split(":")[0]
            old_ifcfg_name = old_ifcfg_path.split("/")[-1]
            old_name = old_ifcfg_name.replace('ifcfg-', '')
            logger.debug("the name[%s] of device[%s]'s ifcfg file does not match the device, now rename it"
                         % (old_ifcfg_name, self.name))
            try:
                os.rename(old_ifcfg_path, ifcfg_file_path)

                with open(ifcfg_file_path, 'r') as f:
                    file_data = f.read()

                name_line = "NAME=%s"
                file_data = file_data.replace(name_line % old_name, name_line % self.name)

                with open(ifcfg_file_path, 'w') as f:
                    f.write(file_data)

                logger.debug("successfully rename ifcfg file of %s" % self.name)

            except Exception as e:
                logger.debug("failed to rename ifcfg file of %s because %s" % (self.name, e))
                return None

        config_dict = OrderedDict()
        with open(ifcfg_file_path, 'r') as file:
            for line in file:
                if line.startswith('#') or line.strip() == '':
                    continue
                if '=' not in line:
                    continue
                key, value = line.split('=', 1)
                if key.strip() and value.strip():
                    key1 = key.strip()
                    value1 = value.strip()
                    if key1.startswith('PREFIX'):
                        index = key1[len('PREFIX'):]
                        config_dict['NETMASK' + index] = prefix_to_netmask(value1)
                    else:
                        config_dict[key1] = value1
        return config_dict


class NetVlanConfig(NetConfig):
    '''netconfig: net vlan config'''

    def __init__(self, name):
        super(NetVlanConfig, self).__init__(name, NET_CONFIG_VLAN_TYPE)
        self.link_type = NET_CONFIG_VLAN_TYPE
        self.vlan_id = None
        self.bridge = None
        self.bond = None

    def build_ifcfg_file(self):
        super(NetVlanConfig, self).build_ifcfg_file()
        self.add_config('IPV6INIT', 'no')
        self.add_config('IPV6_AUTOCONF', 'no')
        self.add_config('VLAN', 'yes')

        if self.service_type == NET_CONFIG_SERVICE_TYPE_NMCLI:
            self.add_config('REORDER_HDR', 'yes')
            self.add_config('GVRP', 'no')
            self.add_config('MVRP', 'no')
        if self.bond:
            self.add_config('MASTER', self.bond)
            self.add_config('SLAVE', 'yes')

        if self.vlan_id:
            self.add_config('VLAN_ID', self.vlan_id)
        if self.bridge:
            self.add_config('BRIDGE', self.bridge)

    def check_config(self):
        super(NetVlanConfig, self).check_config()
        if self.vlan_id:
            if self.vlan_id < 1 or self.vlan_id > 4094:
                raise NetConfigError('configure error, vlan id must be between 1 and 4094')
        if self.bridge and self.bond:
            raise NetConfigError('configure error, only one of bridge and bond can be specified')
        if self.bridge and len(self.bridge) > 15:
            raise NetConfigError('configure error, bridge name must be between 1 and 15 characters')
        if self.bond and len(self.bond) > 15:
            raise NetConfigError('configure error, bond name must be between 1 and 15 characters')

    def post_restore_config(self):
        super(NetVlanConfig, self).post_restore_config()

        if not self.bridge:
            return
        need_delete_files = find_bridge_files(self.config_path, self.bridge, self.name)
        for file in need_delete_files:
            logger.debug('ifcfg file[%s] config the same bridge[%s], will delete' % (file, self.bridge))
            os.remove(file)


class NetBridgeConfig(NetConfig):
    '''netconfig: net bridge config'''

    def __init__(self, name):
        super(NetBridgeConfig, self).__init__(name, NET_CONFIG_BRIDGE_TYPE)
        self.link_type = NET_CONFIG_BRIDGE_TYPE
        self.stp = NET_CONFIG_STP_NO
        self.delay = 5
        self.phys_dev = None

    def build_ifcfg_file(self):
        super(NetBridgeConfig, self).build_ifcfg_file()
        self.add_config('IPV6INIT', 'no')
        self.add_config('IPV6_AUTOCONF', 'no')
        self.add_config('TYPE', 'Bridge')

        if self.service_type == NET_CONFIG_SERVICE_TYPE_NMCLI:
            self.add_config('PROXY_METHOD', 'none')
            self.add_config('BROWSER_ONLY', 'no')
        if self.service_type == NET_CONFIG_SERVICE_TYPE_NORMAL:
            if self.delay:
                self.add_config('DELAY', self.delay)

        if self.stp:
            self.add_config('STP', self.stp)
        if self.phys_dev:
            self.add_config('PHYSDEV', self.phys_dev)

    def check_config(self):
        super(NetBridgeConfig, self).check_config()
        if self.stp not in [NET_CONFIG_STP_YES, NET_CONFIG_STP_NO]:
            raise NetConfigError('configure error, stp must be yes or no')
        if self.delay and self.delay < 0:
            raise NetConfigError('configure error, bridge delay must be greater than 0')
        if self.phys_dev and len(self.phys_dev) > 15:
            raise NetConfigError('configure error, phys dev name must be between 1 and 15 characters')


class NetBondConfig(NetConfig):
    '''netconfig: net bond config'''

    def __init__(self, name):
        super(NetBondConfig, self).__init__(name, NET_CONFIG_BOND_TYPE)
        self.link_type = NET_CONFIG_BOND_TYPE
        self.bond_options = None
        self.bridge = None

    def build_ifcfg_file(self):
        super(NetBondConfig, self).build_ifcfg_file()
        self.add_config('IPV6INIT', 'no')
        self.add_config('IPV6_AUTOCONF', 'no')
        self.add_config('TYPE', 'Bond')
        self.add_config('BONDING_MASTER', 'yes')

        if self.service_type == NET_CONFIG_SERVICE_TYPE_NMCLI:
            self.add_config('PROXY_METHOD', 'none')
            self.add_config('BROWSER_ONLY', 'no')
        if self.service_type == NET_CONFIG_SERVICE_TYPE_NORMAL:
            self.add_config('NM_CONTROLLED', 'no')

        if self.bond_options:
            self.add_config('BONDING_OPTS', '"{}"'.format(self.bond_options))
        if self.bridge:
            self.add_config('BRIDGE', self.bridge)

    def check_config(self):
        super(NetBondConfig, self).check_config()
        if not self.bond_options and 'BONDING_OPTS' not in self.config_dict:
            raise NetConfigError('configure error, bond options must be specified')
        if self.bridge and len(self.bridge) > 15:
            raise NetConfigError('configure error, bridge name must be between 1 and 15 characters')

    def post_restore_config(self):
        super(NetBondConfig, self).post_restore_config()

        if not self.bridge:
            return
        need_delete_files = find_bridge_files(self.config_path, self.bridge, self.name)
        for file in need_delete_files:
            logger.debug('ifcfg file[%s] config the same bridge[%s], will delete' % (file, self.bridge))
            os.remove(file)


class NetEtherConfig(NetConfig):
    '''netconfig: net ether config'''

    def __init__(self, name):
        super(NetEtherConfig, self).__init__(name, NET_CONFIG_ETHER_TYPE)
        self.link_type = NET_CONFIG_ETHER_TYPE
        self.bridge = None
        self.bond = None

    def build_ifcfg_file(self):
        super(NetEtherConfig, self).build_ifcfg_file()
        self.add_config('TYPE', 'Ethernet')
        self.add_config('PROXY_METHOD', 'none')
        self.add_config('BROWSER_ONLY', 'no')
        self.add_config('IPV4_FAILURE_FATAL', 'no')
        self.add_config('IPV6INIT', 'yes')
        self.add_config('IPV6_AUTOCONF', 'yes')
        self.add_config('IPV6_FAILURE_FATAL', 'no')

        if self.bond:
            self.add_config('MASTER', self.bond)
            self.add_config('SLAVE', 'yes')

        if self.bridge:
            self.add_config('BRIDGE', self.bridge)

    def check_config(self):
        super(NetEtherConfig, self).check_config()
        if self.bridge and self.bond:
            raise NetConfigError('configure error, only one of bridge and bond can be specified')
        if self.bridge and len(self.bridge) > 15:
            raise NetConfigError('configure error, bridge name must be between 1 and 15 characters')
        if self.bond and len(self.bond) > 15:
            raise NetConfigError('configure error, bond name must be between 1 and 15 characters')

    def post_restore_config(self):
        super(NetEtherConfig, self).post_restore_config()

        if not self.bridge:
            return
        need_delete_files = find_bridge_files(self.config_path, self.bridge, self.name)
        for file in need_delete_files:
            logger.debug('ifcfg file[%s] config the same bridge[%s], will delete' % (file, self.bridge))
            os.remove(file)


def find_bridge_files(file_path, bridge_name, exclude_dev=None):
    '''find bridge files'''
    if not os.path.exists(file_path) or not bridge_name:
        return []
    exclude_file = 'ifcfg-{}'.format(exclude_dev) if exclude_dev else None
    bridge_files = []

    files = glob.glob('{}/ifcfg-*'.format(file_path))
    for file in files:
        if file and file.endswith(exclude_file):
            continue
        with open(file, 'r') as fd:
            for line in fd:
                if line.startswith('BRIDGE={}'.format(bridge_name)):
                    bridge_files.append(file)
                    break
    return bridge_files


def is_ipv4(ip_address):
    compile_ip = re.compile('^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)')
    if compile_ip.match(ip_address):
        return True
    else:
        return False


def prefix_to_netmask(prefix):
    '''prefix to netmask'''
    prefix = int(prefix)
    netmask = (0xffffffff >> (32 - prefix)) << (32 - prefix)
    return (str((0xff000000 & netmask) >> 24) + '.' +
            str((0x00ff0000 & netmask) >> 16) + '.' +
            str((0x0000ff00 & netmask) >> 8) + '.' +
            str((0x000000ff & netmask)))

if __name__ == '__main__':
    logger.debug('start test netconfig')

    shell.call('ip link add vmnic0 type dummy || true')

    logger.debug('start test vmnic0')
    vmnic0 = NetConfig(name='vmnic0')
    vmnic0.device = 'vmnic0'
    vmnic0.add_ip_config('10.10.10.11', '255.255.255.0')
    vmnic0.mtu = 1450
    vmnic0.alias = 'lpc-test:vmnic0'
    vmnic0.restore_config(is_reload=False)
    logger.debug('restore vmnic0 config success')

    logger.debug('start test vmnic0.1235')
    vmnic0_1235 = NetVlanConfig(name='vmnic0.1235')
    vmnic0_1235.add_ip_config('10.10.10.22', '255.255.255.0')
    vmnic0_1235.mtu = 1450
    vmnic0_1235.bridge = 'br_vmnic0_1235'
    vmnic0_1235.vlan_id = 1235
    vmnic0_1235.alias = 'lpc-test:vmnic0_1235'
    vmnic0_1235.restore_config(is_reload=True)
    logger.debug('restore vmnic0.1235 config success')

    logger.debug('start test br_vmnic0_1235')
    br_vmnic0_1235 = NetBridgeConfig(name='br_vmnic0_1235')
    br_vmnic0_1235.add_ip_config('10.10.10.33', '255.255.255.0')
    br_vmnic0_1235.add_ip_config('10.10.10.34', '255.255.255.0')
    br_vmnic0_1235.mtu = 1450
    br_vmnic0_1235.phys_dev = 'vmnic0.1235'
    br_vmnic0_1235.stp = NET_CONFIG_STP_YES
    br_vmnic0_1235.delay = 3
    br_vmnic0_1235.alias = 'lpc-test:br_vmnic0_1235'
    br_vmnic0_1235.restore_config(is_reload=True)
    logger.debug('restore br_vmnic0_1235 config success')

    logger.debug('start test vmbond0')
    vmbond0 = NetBondConfig(name='vmbond0')
    vmbond0.add_ip_config('10.10.10.44', '255.255.255.0')
    vmbond0.add_ip_config('10.10.10.44', '255.255.255.0')
    vmbond0.add_ip_config('10.10.10.44', '255.255.255.0')
    vmbond0.add_ip_config('10.10.10.45', '255.255.255.0')
    vmbond0.add_ip_config('10.10.10.46', '255.255.255.0')
    vmbond0.add_ip_config('10.10.10.47', '255.255.255.0')
    vmbond0.mtu = 1450
    vmbond0.bond_options = 'miimon=1000 mode=802.3ad lacp_rate=1 xmit_hash_policy=layer3+4'
    vmbond0.alias = 'lpc-test:vmbond0'
    vmbond0.bridge = 'br_vmbond0'
    vmbond0.restore_config(is_reload=True)
    logger.debug('restore vmbond0 config success')

    logger.debug('start test br_vmbond0')
    br_vmbond0 = NetBridgeConfig(name='br_vmbond0')
    br_vmbond0.add_ip_config('10.10.10.55', '255.255.255.0')
    br_vmbond0.mtu = 1450
    br_vmbond0.phys_dev = 'vmbond0'
    br_vmbond0.stp = NET_CONFIG_STP_YES
    br_vmbond0.delay = 3
    br_vmbond0.alias = 'lpc-test:br_vmbond0'
    br_vmbond0.restore_config(is_reload=True)
    logger.debug('restore br_vmbond0 config success')

    logger.debug('start test delete br_vmbond0 and flush vmbond0')
    br_vmbond0 = NetConfig(name='br_vmbond0')
    br_vmbond0.delete_config()
    vmbond0 = NetConfig(name='vmbond0')
    vmbond0.delete_ip_config('10.10.10.46')
    vmbond0.flush_config()
    logger.debug('delete br_vmbond0 and flush vmbond0 success')
