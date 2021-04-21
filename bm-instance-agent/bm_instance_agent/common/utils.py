import os
import re

import cpuinfo
import distro
from netaddr import IPAddress
import netifaces
from oslo_concurrency import processutils
import psutil

from bm_instance_agent import exception


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
    for iface in iface_name_list:
        af_link = netifaces.ifaddresses(iface).get(netifaces.AF_LINK)
        mac = af_link[0].get('addr')
        interfaces[mac] = iface
    return interfaces


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

    if distro_id == 'centos':
        if major_version == '7':
            return 'centos_v%s_%s' % (major_version, arch)
        return 'centos'

    if distro_id == 'ubuntu':
        return 'ubuntu'

    if distro_id == 'kylin':
        version = distro.version()
        if version == 'V10':
            return 'kylin_v10_%s' % arch
        return 'kylin'

    return 'linux'
