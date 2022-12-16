'''

@author: yyk
'''
import re
import os.path
import socket

import linux
import bash


class IpAddress(object):
    '''
    Help to save and compare IP Address. 
    '''

    def __init__(self, ip):
        self.ip_list = ip.split('.', 3)
        self.ips = []
        for item in self.ip_list:
            if not item.isdigit():
                raise Exception('%s is not digital' % item)
            if int(item) > 255 or item < 0:
                raise Exception('%s must be >=0 and <=255' % item)
            self.ips.append(int(item))

    def __cmp__(self, ip2):
        index = 0
        while index < 4:
            cmp_ret = cmp(self.ips[index], ip2.ips[index])
            if cmp_ret > 0:
                return 1
            elif cmp_ret < 0:
                return -1
            index += 1
        else:
            return 0

    def __gt__(self, ip2):
        if self.__cmp__(ip2) > 0:
            return True
        return False

    def __lt__(self, ip2):
        if self.__cmp__(ip2) < 0:
            return True
        return False

    def __eq__(self, ip2):
        if self.__cmp__(ip2) == 0:
            return True
        return False

    def __le__(self, ip2):
        if self.__cmp__(ip2) > 0:
            return False
        return True

    def __ge__(self, ip2):
        if self.__cmp__(ip2) < 0:
            return False
        return True

    def __str__(self):
        return '.'.join(self.ip_list)

    def __repr__(self):
        return self.__str__()

    def toInt32(self):
        ip32 = self.ips[0];
        for item in self.ips[1:]:
            ip32 = ip32 << 8
            ip32 += item
        return ip32

    def toCidr(self, netmask):
        ip32 = self.toInt32()
        mask32 = IpAddress(netmask).toInt32()
        cidr32 = ip32 & mask32
        cidr = [cidr32 >> 24, (cidr32 & 0x00FF0000) >> 16, (cidr32 & 0x0000FF00) >> 8, cidr32 & 0x00000FF]

        maskbits = linux.netmask_to_cidr(netmask)

        return '%s.%s.%s.%s/%s' % (cidr[0], cidr[1], cidr[2], cidr[3], maskbits)


class Ipv6Address(object):
    '''
        Help to save and compare IP Address.
        '''

    def __init__(self, ip):
        # ipv6 address includes 8 strings
        self.ips = ["", "", "", "", "", "", "", ""]
        self.prefix = ["", "", "", "", "", "", "", ""]
        temp = ip.split('::')
        pos = 0
        for item in temp[0].split(":"):
            self.ips[pos] = item
            self.prefix[pos] = item
            pos = pos + 1

        if len(temp) == 2:
            addr = temp[1].split(":")
            addr_len = len(addr)
            pos = 8 - addr_len
            for item in addr:
                self.ips[pos] = item
                pos = pos + 1

    def get_solicited_node_multicast_address(self):
        ip = "ff02::1:ff"
        if len(self.ips[6]) >= 2:
            ip += self.ips[6][-2:]
        else:
            ip += self.ips[6]
        return ip + ":" + self.ips[7]

    def get_prefix(self, prefixlen):
        temp = []
        for item in self.prefix:
            if item != "":
                temp.append(item)

        return ":".join(temp) + "::/" + str(prefixlen)


def get_link_local_address(mac):
    ''' get ipv6 link local address from 48bits mac address,
        details are described at the https://tools.ietf.org/html/rfc4291#section-2.5.1
        for example mac address 00:01:02:aa:bb:cc
        step 1. inverting the universal/local bit of mac address to 02:01:02:0a:0b:0c
        step 2. insert fffe in the middle of mac address to 02:01:02:ff:fe:0a:0b:0c
        step 3. convert to ip address with fe80::/64, strip the leading '0' in each sector between ':'
                fe80::201:2ff:fe0a:b0c
    '''
    macs = mac.strip("\n").split(":")

    # step 1. inverting the "u" bit of mac address
    macs[0] = hex(int(macs[0], 16) ^ 2)[2:]

    # step 2, insert "fffe"
    part1 = macs[0] + macs[1] + ":"
    part2 = macs[2] + "ff" + ":"
    part3 = "fe" + macs[3] + ":"
    part4 = macs[4] + macs[5]

    #step 3
    return "fe80::" + part1.lstrip("0") + part2.lstrip("0") + part3.lstrip("0") + part4.lstrip("0")

def removeZeroFromMacAddress(mac):
    '''
    mac address in iptables will remove leading zero, for example:
    00:01:aa:b0:02:04 --> 0:1:aa:b0:2:4
    :param mac:
    :return:
    '''
    newMac = mac.replace(":0", ":")
    if newMac[0] == '0':
        newMac = newMac[1:]
    return newMac

def is_sriovVf_nic(nic):
    return os.path.exists("/sys/class/net/%s/device/physfn/" % nic)

def get_nic_supported_max_speed(nic):
    if get_nic_driver_type(nic) == "virtio_net":
        return 0

    if is_sriovVf_nic(nic):
        return 0

    r, o = bash.bash_ro("ethtool %s" % nic)  # type: (int, str)
    if r != 0:
        return 0

    in_speed = False
    speed = 0
    for line in o.strip().splitlines():
        if "supported link modes" in line.lower():
            in_speed = True
        if in_speed is True and ":" in line and "supported link modes" not in line.lower():
            break
        if in_speed:
            nums = re.findall(r"\d+\.?\d*", line)
            if len(nums) == 0:
                continue
            max_num = max([int(n) for n in nums])
            if max_num > speed:
                speed = max_num

    if speed == 0:
        lines = linux.read_file("/sys/class/net/%s/speed" % nic)
        if not lines:
            return speed
        speed = lines.strip()
        try:
            speed = int(speed)
        except Exception:
            speed = 0
    if speed < 0:
        speed = 0

    return speed


def get_nic_driver_type(nic):
    r, o = bash.bash_ro("ethtool -i %s" % nic)
    if r != 0:
        return ""

    driver_info = None
    driver = ""
    for line in o.strip().splitlines():
        if "driver:" in line.lower():
            driver_info = line
            break

    if driver_info:
        driver_info = driver_info.split(":")
        if len(driver_info) == 2:
            driver = driver_info[1].strip()
    return driver


def get_namespace_id(namespace_name):
    NAMESPACE_NAME = namespace_name
    out = bash.bash_errorout("ip netns list-id | grep -w {{NAMESPACE_NAME}} | awk '{print $2}'").strip()
    if not out:
        out = bash.bash_errorout("ip netns list-id | awk 'END{print $2}'").strip()
        if not out:
            return 0
        return int(out) + 1
    return int(out)

def get_smart_nic_pcis():
    nic_pcis = []
    pci_devices = bash.bash_o("lspci -D -m | grep Mellanox | grep -v Virtual").splitlines()
    for pci_device in pci_devices:
        pci_info = pci_device.split(" ")
        nic_pcis.append(pci_info[0])
    return nic_pcis

def get_smart_nics_interfaces(nic_pcis = None):
    nics_interfaces = []
    if nic_pcis is None:
        nic_pcis = get_smart_nic_pcis()
    for nic_pci in nic_pcis:
        interface_path = os.path.join("/sys/bus/pci/devices/%s/net" % (nic_pci))
        if not os.path.exists(interface_path):
            break
        interface_list = os.listdir(interface_path)
        nics_interfaces.append(interface_list)
    return nics_interfaces

def get_smart_nic_representors():
    def is_representor(interface_name, interfaces_number):
        if interfaces_number == 1:
            ''' This is special case for Mellanox Technologies ConnectX-5.
                If ofed not installed, and after reboot, it's pf will not
                include "phy_stats" from the net directory. So the only way
                to judge if its representor is check its interface number
                under that pci device.
            '''
            return False
        physical_interface_path = os.path.join("/sys/class/net/%s/phy_stats" % (interface_name))
        if os.path.exists(physical_interface_path):
            return False
        return True
    nic_representors = []
    try:
        nics_interfaces = get_smart_nics_interfaces()
        for nic_interfaces in nics_interfaces:
            nic_interfaces_number = len(nic_interfaces)
            for nic_interface in nic_interfaces:
                if is_representor(nic_interface, nic_interfaces_number):
                    nic_representors.append(nic_interface)
    except Exception:
            return []
    return nic_representors

def get_host_physicl_nics():
    nic_all_physical = bash.bash_o("find /sys/class/net -type l -not -lname '*virtual*' -printf '%f\\n'").splitlines()
    if nic_all_physical is None or len(nic_all_physical) == 0:
        return []

    nic_without_sriov = []
    for nic in nic_all_physical:
        # exclude sriov vf nics
        if not is_sriovVf_nic(nic):
            nic_without_sriov.append(nic)

    nic_without_virtual = []
    for nic in nic_without_sriov:
        flag = True
        # exclude virtual nic
        if 'vnic' in nic:
            flag = False
        if 'outer' in nic:
            flag = False
        if 'br_' in nic:
            flag = False
        if flag:
            nic_without_virtual.append(nic)

    nic_without_smart_nic_representors = []
    smart_nic_representors = get_smart_nic_representors()
    for nic in nic_without_virtual:
        if nic not in smart_nic_representors:
            nic_without_smart_nic_representors.append(nic)

    return nic_without_smart_nic_representors

def get_prefix_len_by_netmask(netmask):
    ip_int = int(socket.inet_aton(netmask).encode('hex'), 16)
    i = 1
    prefix = 0
    while not ip_int & i:
        i = i << 1
        prefix += 1
    return 32 - prefix


def is_ipv4(ip_address):
    compile_ip = re.compile('^((25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(25[0-5]|2[0-4]\d|[01]?\d\d?)')
    if compile_ip.match(ip_address):
        return True
    else:
        return False
