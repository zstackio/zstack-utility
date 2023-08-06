import os
import re
import socket

import cpuinfo
import distro
from netaddr import IPAddress
import netifaces
from oslo_concurrency import processutils
import psutil
import pyroute2
import time
from oslo_log import log as logging

from bm_instance_agent import exception

LOG = logging.getLogger(__name__)
DEFAULT_SSH_PORT = 22

class transcantion(object):
    """ A tool class for retry
    """

    def __init__(self, retries, sleep_time=0):
        self.retries = retries
        self.sleep_time = sleep_time

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            return False
        return True

    def execute(self, func, *args, **kwargs):
        err = None
        for i in range(self.retries):
            try:
                if i > 0:
                    msg = 'Attempt rerun {name}: {i}'.format(
                        name=func.__name__, i=i)
                    LOG.warning(msg)
                return func(*args, **kwargs)
            except Exception as e:
                LOG.exception(e)
                err = e
            time.sleep(self.sleep_time)
        raise err


class IpLink:
    def __init__(self, chunk):
        self.index = chunk['index']
        self.ip_version = 4 if chunk['family'] == socket.AF_INET else 6
        # self.state = chunk['state'] # 'up'
        self.mac = chunk.get_attr('IFLA_ADDRESS')  # link/ether, mac address, type str
        self.ifname = chunk.get_attr('IFA_LABEL') or chunk.get_attr('IFLA_IFNAME')  # type: str | None
        self.mtu = chunk.get_attr('IFLA_MTU')  # type: int
        self.qlen = chunk.get_attr('IFLA_TXQLEN')  # type: int
        self.state = chunk.get_attr('IFLA_OPERSTATE')  # type: str
        self.qdisc = chunk.get_attr('IFLA_QDISC')  # type: tuple
        self.alias = chunk.get_attr('IFLA_IFALIAS')  # type: tuple. if no alias, self.alias = (None,)
        self.allmulticast = bool(chunk['flags'] & pyroute2.netlink.rtnl.ifinfmsg.IFF_ALLMULTI)  # type: tuple
        self.device_type = chunk.get_nested('IFLA_LINKINFO', 'IFLA_INFO_KIND')
        self.broadcast = chunk.get_attr('IFLA_BROADCAST')  # type: str
        self.group = chunk.get_attr('IFLA_GROUP')  # type: int
        self.chunk = chunk


def _query_index_by_ifname(if_name, iproute):
    rets = iproute.link_lookup(ifname=if_name)
    return rets[0] if rets else None


def _get_bond_slave_mac(if_name):
    path = '/sys/class/net/{}/bonding_slave/perm_hwaddr'.format(if_name)
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return None


def query_link(iface):
    with pyroute2.IPRoute() as ipr:
        if_index = None
        if isinstance(iface, int):
            if_index = iface
        elif isinstance(iface, (str, unicode)):
            if_index = _query_index_by_ifname(iface, ipr)

        if if_index:
            link = ipr.get_links(if_index)
            if link:
                return IpLink(link[0])
        return None


def get_interfaces():
    """ Get network interfaces on local system

    :return: A iface_name, iface_mac mapping::
    {
        'aa:bb:cc:dd:ee:ff': 'eth0',
        'ff:ee:dd:cc:bb:aa': 'enp37s0'
    }
    :rtype: dict
    """
    interfaces = {}
    iface_name_list = netifaces.interfaces()
    LOG.info("get iface list: %s" % iface_name_list)
    for iface in iface_name_list:
        af_link = netifaces.ifaddresses(iface).get(netifaces.AF_LINK)
        if af_link is None:
            LOG.info("%s aflink is None, continue" % iface)
            continue
        mac = af_link[0].get('addr')
        perm_mac = _get_bond_slave_mac(iface)
        if perm_mac:
            interfaces[perm_mac] = iface
        elif mac not in interfaces:
            interfaces[mac] = iface
    return interfaces


def get_phy_ifs_from_sys_class():
    interfaces = {}
    for net_dev in os.listdir('/sys/class/net'):
        abspath = os.path.join('/sys/class/net', net_dev)
        realpath = os.path.realpath(abspath)
        if 'virtual' in realpath or (net_dev == 'lo'):
            continue

        mac_path = os.path.join(abspath, 'address')
        if not os.path.exists(mac_path):
            continue

        with open(mac_path, 'r') as f:
            mac_address = f.read().strip()
        if len(mac_address) > 32:
            continue
        perm_mac = _get_bond_slave_mac(net_dev)
        if perm_mac:
            interfaces[perm_mac] = net_dev
        elif mac_address not in interfaces:
            interfaces[mac_address] = net_dev

    return interfaces


def get_phy_interfaces():
    """ Get physical interfaces on local system

    :return: A iface_name, iface_mac mapping::
    {
        'aa:bb:cc:dd:ee:ff': 'eth0',
        'ff:ee:dd:cc:bb:aa': 'enp37s0'
    }
    :rtype: dict
    """
    distro_id = distro.id()
    major_version = distro.major_version()
    if distro_id in ['centos', 'rhel'] and major_version == '6':
        return get_phy_ifs_from_sys_class()

    interfaces = {}
    iface_name_list = netifaces.interfaces()
    LOG.info("get iface list: %s" % iface_name_list)
    for iface in iface_name_list:
        link = query_link(iface)
        if not link or link.device_type:
            continue

        af_link = netifaces.ifaddresses(iface).get(netifaces.AF_LINK)
        if af_link is None:
            LOG.info("%s aflink is None, continue" % iface)
            continue
        mac = af_link[0].get('addr')
        perm_mac = _get_bond_slave_mac(iface)
        if perm_mac:
            interfaces[perm_mac] = iface
        elif mac not in interfaces:
            interfaces[mac] = iface

    return interfaces


def is_physical_interface(if_name):
    link = query_link(if_name)
    return link and not link.device_type


def get_interface_by_mac(mac):
    """ Get network interface name by mac address

    :param mac: A mac address
    :type mac: string
    :return: The network interface's name
    :rtype: string
    """
    iface_name = get_interfaces()[mac]
    return iface_name.split('.')[0]


def get_addr(iface):
    """ Get ipv4 address for a given network interface

    :param iface: The network interface name
    :return: The network interface's ipv4 address, if multiple addresses set
    on the nic, return the first one::
    {
        'addr': '127.0.0.2',
        'netmask': 255.255.255.0',
        'broadcast': '127.0.0.255
    }
    :rtype: dict
    """
    addr = netifaces.ifaddresses(iface).get(netifaces.AF_INET)
    return addr[0] if addr else {}


def convert_netmask(netmask):
    return IPAddress(netmask).netmask_bits()


def get_gateway():
    """ Get ipv4 gateway

    :return: The default gateway info, (gw_ip_address, iface_name)
    :rtype: tuple
    """
    default = netifaces.gateways().get('default')
    return default.get(netifaces.AF_INET) if default else (None, None)


def flush_dev_ip_conf(iface_name):
    """ Flush a network interface's ip configuration
    """
    cmd = ['ip', 'address', 'flush', 'dev', iface_name]
    return processutils.execute(*cmd)


def camel_string_to_snake(name):
    """ Convert a camelcase string to snakecase

    The camelcase string could be 'provisionIpAddress', after convert it
    could be 'provision_ip_address'.

    :param name: A camelcase string
    :type name: string
    :return: A snakecase string
    :rtype: string
    """
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


def camel_obj_to_snake(camel):
    """ Convert the camelcase key(in the dict) to snakecase

    :param camel: A dict which the keys are camelcase
    :type camel: dict or list
    :return: A dict which the keys are snakecase
    :rtype: dict or list
    """

    if isinstance(camel, dict):
        new_dict = {}
        for k, v in camel.items():
            new_k = camel_string_to_snake(k)
            new_dict[new_k] = camel_obj_to_snake(v)
        return new_dict
    elif isinstance(camel, list):
        new_list = []
        for item in camel:
            new_list.append(camel_obj_to_snake(item))
        return new_list
    else:
        return camel


def process_is_running(process_name):
    for process in psutil.process_iter():
        if process_name in process.name():
            return True
    return False


def get_distro():
    cpu_arch = cpuinfo.get_cpu_info().get('arch_string_raw')
    if 'x86_64' == cpu_arch:
        arch = 'x86'
    elif 'aarch64' in cpu_arch:
        arch = 'arm'
    else:
        raise exception.CPUArchNotSupport(cpu_arch=cpu_arch)

    if os.name == 'nt':
        return 'windows'

    distro_id = distro.id()
    major_version = distro.major_version()
    LOG.info("current distro id: %s, major_version: %s" % (distro.id(), distro.major_version()))

    if distro_id == 'centos' or distro_id == 'rhel':
        if major_version == '7' or major_version == '8':
            return 'centos_v%s_%s' % (major_version, arch)
        return 'centos'

    if distro_id == 'ubuntu':
        return 'ubuntu'

    if distro_id == 'kylin':
        version = distro.version()
        if version == 'V10' and arch == 'arm':
            return 'kylin_v10_arm'
        return 'kylin'

    return 'centos'


def ip_link_del(if_name):
    try:
        cmd = ['ip', 'link', 'delete', if_name]
        processutils.execute(*cmd)
    except processutils.ProcessExecutionError as e:
        if 'Cannot find device' not in e.stderr:
            raise e


def ip_route_del(route_key):
    try:
        cmd = ['ip', 'route', 'delete', route_key]
        processutils.execute(*cmd)
    except processutils.ProcessExecutionError as e:
        if 'No such process' not in e.stderr:
            raise e


def remove_file(file_path):
    try:
        os.remove(file_path)
    except OSError as e:
        if 'No such file or directory' not in str(e):
            raise e


def nmcli_conn_delete(conn_name):
    try:
        cmd = ['nmcli', 'con', 'delete', conn_name]
        processutils.execute(*cmd)
    except processutils.ProcessExecutionError as e:
        if 'unknown connection' not in e.stderr:
            raise e


def get_nmcli_system_conn(name):
    return "System " + name


def config_to_dict(config, item_split, key_value_split):
    """
        Parse configuration items as dict.
        e.g:
            config_to_dict('a=11,b=22,c=33', ',', '='), return {'a':11, 'b':22, 'c':33}
            config_to_dict('a:11 b:22 c:33', ' ', ':'), return {'a':11, 'b':22, 'c':33}
    """
    try:
        config_dict = dict([opts.split(key_value_split) for opts in config.split(item_split)])
    except ValueError:
        raise exception.NewtorkInterfaceConfigParasInvalid(exception_msg="config format error")
    return config_dict


def get_ssh_port():
    try:
        get_port_cmd = "grep '^Port' /etc/ssh/sshd_config | awk '{print $2}'"
        stdout, _ = processutils.execute(get_port_cmd, shell=True)
        if stdout == "":
            return DEFAULT_SSH_PORT
        return stdout.strip()
    except Exception:
        LOG.warning("get ssh port failed ,return default ssh port 22")
        return DEFAULT_SSH_PORT
