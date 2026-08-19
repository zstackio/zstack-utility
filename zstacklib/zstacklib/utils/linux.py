'''

@author: frank
'''
import abc
import contextlib
import os
import os.path
import resource
import socket
import datetime
import time
import tempfile
import traceback
import shutil
import struct
import netaddr
import functools
import threading
import re
import platform
import pprint
import errno
import json
import fcntl
import simplejson
import xxhash
import glob
import sys
import ctypes
import ctypes.util
import stat

from inspect import stack
import xml.etree.ElementTree as etree
from zstacklib.utils import thread
from zstacklib.utils import qemu_img
from zstacklib.utils import lock
from zstacklib.utils import xmlobject
from zstacklib.utils import shell
from zstacklib.utils import log
from zstacklib.utils import iproute
from zstacklib.utils import network_ipv6


logger = log.get_logger(__name__)

RPM_BASED_OS = ['redhat', 'centos', 'alibaba', 'alinux', 'kylin10', 'rocky', 'helix']
DEB_BASED_OS = ['uos', 'kylin4.0.2', 'debian', 'ubuntu', 'uniontech']
ARM_ACPI_SUPPORT_OS = ['kylin10', 'openEuler20.03', 'openEuler22.03']
SUPPORTED_ARCH = ['x86_64', 'aarch64', 'mips64el', 'loongarch64']
DIST_WITH_RPM_DEB = ['kylin']
HOST_ARCH = platform.machine()
tcp_port_lock = threading.Lock()
LOONGSON_3C5000L_CORES_PER_SOCKET = 16


'''
[root@10-0-67-98 ~]# ip link set mtu 65522 dev vnic2.0
RTNETLINK answers: Invalid argument
[root@10-0-67-98 ~]# ip link set mtu 65521 dev vnic2.0
[root@10-0-67-98 ~]# ip link set mtu 9601 dev eth0.100
RTNETLINK answers: Numerical result out of range
[root@10-0-67-98 ~]# ip link set mtu 9600 dev eth0.100
'''
MAX_MTU_OF_VNIC = 65500
KVM_DEVICE = '/dev/kvm'
KVM_CAP_ARM_VM_IPA_SIZE = 165
KVM_CHECK_EXTENSION = 44547
DEFAULT_VM_IPA_SIZE = 40
LIVE_LIBVIRT_XML_DIR = "/var/run/libvirt/qemu"
MAX_NBD_READ_SIZE = 32768000
NFS_URL_SEPARATOR = ':'
IPV6_HOST_PREFIX = '['
IPV6_HOST_SUFFIX = ']'

def ignoreerror(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            content = traceback.format_exc()
            err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
            logger.warn(err)
    return wrap

class VolumeInUseError(Exception):
    pass

class LinuxError(Exception):
    ''' some utils failed '''

class InvalidNfsUrlError(Exception):
    '''The NFS url is invalid'''
    def __init__(self, url, msg):
        err = 'Invaild NFS URL[%s], %s' % (url, msg)
        super(InvalidNfsUrlError, self).__init__(err)

class MountError(Exception):
    '''Error happened when mounting'''
    def __init__(self, url, msg):
        err = 'Failed to mount NFS URL[%s], %s' % (url, msg)
        super(MountError, self).__init__(msg)

class EthernetInfo(object):
    def __init__(self):
        self.mac = None
        self.broadcast_address = None
        self.link_encap = None
        self.netmask = None
        self.interface = None
        self.ip = None

    def __str__(self):
        return 'interface:%s, mac:%s, ip:%s, netmask:%s' % (self.interface, self.mac, self.ip, self.netmask)

    def __repr__(self):
        return self.__str__()

class VmStruct(object):
    def __init__(self):
        super(VmStruct, self).__init__()
        self.pid = ""
        self.xml = ""
        self.root_volume = ""
        self.uuid = ""
        self.volumes = []
        self.bridges = []

    def load_from_xml(self, xml):
        def load_interface_source(element):
            for e in element:
                if e.tag == "source":
                    if "bridge" in e.attrib:
                        self.bridges.append(e.attrib["bridge"])

        def load_disk_source(element):
            is_root_vol = False
            path = None
            for e in element:
                if e.tag == "boot":
                    is_root_vol = True
                elif e.tag == "source":
                    if "file" in e.attrib:
                        path = e.attrib["file"]
                    elif "dev" in e.attrib:
                        path = e.attrib["dev"]
                    elif "protocol" in e.attrib and "name" in e.attrib:
                        path = "%s:%s" % (e.attrib["protocol"], e.attrib["name"])
                    if path and path.startswith("/dev/"):
                        self.volumes.append(path)

            if is_root_vol:
                self.root_volume = path

        self.xml = xml
        root = etree.fromstring(xml)
        for e1 in root:
            if e1.tag == "domain":
                for e2 in e1:
                    if e2.tag == "devices":
                        for e3 in e2:
                            if e3.tag == "disk":
                                load_disk_source(e3)
                            if e3.tag == "interface":
                                load_interface_source(e3)
                        return


def retry(times=3, sleep_time=3):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            orig_except = None
            for i in range(0, times):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    orig_except = e
                    time.sleep(sleep_time)
            raise orig_except

        return inner
    return wrap

def retry_if_unexpected_value(unexpected_value, times=3, sleep_time=3):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            ret = None
            for i in range(0, times):
                try:
                    ret = f(*args, **kwargs)
                    if ret == unexpected_value:
                        time.sleep(sleep_time)
                    else:
                        return ret
                except Exception as e:
                    time.sleep(sleep_time)
            return ret

        return inner
    return wrap

def ignore_error_retry(times=3, sleep_time=3, return_after_exception=None):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            orig_except = None
            for i in range(0, times):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    orig_except = e
                    time.sleep(sleep_time)
            logger.warn(str(orig_except))
            return return_after_exception

        return inner
    return wrap

def retry_with_check(handler=None):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except Exception as e:
                if handler is not None and handler(args, e):
                    return f(*args, **kwargs)
                else:
                    raise e

        return inner
    return wrap


def timeout_defer(timeout_in_seconds=0, handler=None):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            deanline = get_current_timestamp() + timeout_in_seconds - 10
            try:
                return f(*args, **kwargs)
            finally:
                # timeout=0 means there will be no timeout
                end_time = get_current_timestamp()
                if handler is not None and timeout_in_seconds > 0 and end_time > deanline:
                    logger.debug("method %s.%s execution timeout, deadline is %d, now is %d, start to execute defer func"
                                 % (__file__, f.__name__, deanline, end_time))
                    handler(args)

        return inner
    return wrap


def with_arch(todo_list=SUPPORTED_ARCH, host_arch=HOST_ARCH):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            if set(todo_list) - set(SUPPORTED_ARCH):
                raise Exception("Unknown arch in {}".format(todo_list))
            if host_arch in todo_list:
                return f(*args, **kwargs)
            else :
                logger.info("Skip function[{}] on {} host.".format(f.__name__, host_arch))
        return inner
    return wrap

def on_redhat_based(distro=None, exclude=[]):
    def wrap(f):
        @functools.wraps(f)
        def innner(*args, **kwargs):
            if not distro:
                raise Exception("Distro info is needed.")
            if distro in list(set(RPM_BASED_OS) - set(exclude)):
                return f(*args, **kwargs)
        return innner
    return wrap

def on_debian_based(distro=None, exclude=[]):
    def wrap(f):
        @functools.wraps(f)
        def innner(*args, **kwargs):
            if not distro:
                raise Exception("Distro info is needed.")
            if distro in list(set(DEB_BASED_OS) - set(exclude)):
                return f(*args, **kwargs)
        return innner
    return wrap


def get_current_timestamp():
    return time.mktime(datetime.datetime.now().timetuple())

def exception_on_opened_file(f):
    s = shell.call("timeout 10 lsof -Fc %s" % f, exception=False)
    if s:
        raise VolumeInUseError('file %s is still opened: %s' % (f, ' '.join(s.splitlines())))

def exception_on_opened_dir(d):
    s = shell.call("timeout 10 lsof -Fc +D %s" % d, exception=False)
    if s:
        raise VolumeInUseError('dir %s is still opened: %s' % (d, ' '.join(s.splitlines())))

def rm_file_force(fpath):
    try:
        os.remove(fpath)
    except:
        pass

black_dpath_list = ["", "/", "*", "/root", "/var", "/bin", "/lib", "/sys"]

def rm_dir_force(dpath):
    if dpath.strip() in black_dpath_list:
        raise Exception("how dare you delete directory %s" % dpath)
    if not os.path.exists(dpath):
        return
    if os.path.isdir(dpath):
        shutil.rmtree(dpath, ignore_errors=True)
    else:
        rm_file_force(dpath)

def rm_file_checked(fpath):
    if not os.path.exists(fpath):
        return

    exception_on_opened_file(fpath)
    os.remove(fpath)

def rm_dir_checked(dpath):
    if not os.path.exists(dpath):
        return

    exception_on_opened_dir(dpath)
    shutil.rmtree(dpath)


def unlink_file_checked(fpath):
    if not os.path.exists(fpath):
        return

    exception_on_opened_file(fpath)
    os.unlink(fpath)


def process_exists(pid):
    return os.path.exists("/proc/" + str(pid))

def netmask_to_broadcast(ip, netmask):
    ip = ip.split('.')
    netmask = netmask.split('.')
    ip = [int(bin(int(octet)), 2) for octet in ip]
    netmask = [int(bin(int(octet)), 2) for octet in netmask]
    broadcast = [(ioctet | ~moctet) & 0xff for ioctet, moctet in zip(ip, netmask)]
    return ".".join('%s' % n for n in broadcast)

def cidr_to_netmask(cidr):
    cidr = int(cidr)
    return socket.inet_ntoa(struct.pack(">I", (0xffffffff << (32 - cidr)) & 0xffffffff))

def netmask_to_cidr(netmask):
    return sum([bin(int(x)).count('1') for x in netmask.split('.')])

def get_ethernet_info():
    link_info = shell.call('ip -o link show')
    inet_info = shell.call('ip -o -f inet addr show')

    devices = {}
    for link in link_info.split('\n'):
        link = link.strip('\t\n\r ')
        if not link:
            continue

        link = link.replace('\\', '')
        tokens = link.split()
        ethname = tokens[1].strip(':')
        # NOTE(ya.wang) VLAN nic's iface name in `link show`('eth0.1024@eth0')
        # is different to `addr show`('eth0.1024')
        ethname = ethname.split('@')[0] if '@' in ethname else ethname
        if ethname == 'lo':
            continue

        eth = EthernetInfo()
        eth.interface = ethname
        devices[ethname] = eth
        mac = None
        for i in range(0, len(tokens)):
            if tokens[i].endswith('/ether') or tokens[i].endswith('/infiniband'):
                mac = tokens[i+1]
                break

        assert mac, 'cannot find mac for ethernet device[%s], %s' % (ethname, link)
        eth.mac = mac

    for addr in inet_info.split('\n'):
        addr = addr.strip('\t\n\r ')
        if not addr:
            continue

        addr = addr.replace('\\', '')
        tokens = addr.split()
        ethname = tokens[1]
        if ethname == 'lo':
            continue

        eth = devices[ethname]
        assert eth, 'cannot find ethernet device[%s]' % ethname
        ip = None
        brd = None
        alias = None
        netmask = None
        for i in range(0, len(tokens)):
            if tokens[i] == 'brd':
                brd = tokens[i+1]
            if tokens[i] == 'inet':
                subnet = tokens[i+1]
                ip, cidr = subnet.split("/")
                netmask = cidr_to_netmask(cidr)
            if tokens[i] == 'secondary':
                alias = tokens[i+1]

        assert ip, 'cannot find ip for ethernet device[%s]' % ethname
        assert netmask, 'cannot find netmask for ethernet device[%s]' % ethname
        if alias:
            alias_eth = EthernetInfo()
            alias_eth.mac = eth.mac
            alias_eth.interface = alias
            alias_eth.broadcast_address = brd
            alias_eth.netmask = netmask
            alias_eth.ip = ip
            devices[alias_eth.interface] = alias_eth
        else:
            eth.ip = ip
            eth.broadcast_address = brd
            eth.netmask = netmask

    return list(devices.values())

# only for novlan and vlan networks
def set_bridge_alias_using_phy_nic_name(bridge_name, nic_name):
    shell.call("ip link set %s alias 'phy_nic: %s'" % (bridge_name, nic_name))

def get_bridge_phy_nic_name_from_alias(bridge_name):
    return shell.call("ip link show %s | awk '/alias/{ print $NF; exit }'" % bridge_name).strip()

def get_bridge_alias_related_slave(bridge_name):
    phy_nic_alias = get_bridge_phy_nic_name_from_alias(bridge_name)
    slaves = shell.call("bridge link show | grep 'master %s'"
                        " | awk '{print $2}' | sed 's/://' | sed 's/@.*$//'" % bridge_name).strip().split('\n')
    for slave in slaves:
        if slave.startswith(phy_nic_alias):
            return slave
    return None

def get_total_disk_size(dir_path):
    stat = os.statvfs(dir_path)
    return stat.f_blocks * stat.f_frsize

def get_free_disk_size(dir_path):
    stat = os.statvfs(dir_path)
    return stat.f_frsize * stat.f_bavail

def get_used_disk_size(dir_path):
    return get_total_disk_size(dir_path) - get_free_disk_size(dir_path)

def get_used_disk_apparent_size(dir_path, max_depth = 1, block_size = 1):
    output = shell.call('du --apparent-size --block-size=%s --max-depth=%s %s | tail -1' % (block_size, max_depth, dir_path))
    return int(output.split()[0])

def get_directory_used_physical_size(dir_path, max_depth = 1, block_size = 1):
    output = shell.call('du --block-size=%s --max-depth=%s %s | tail -1' % (block_size, max_depth, dir_path))
    return int(output.split()[0])

def get_total_file_size(paths):
    total = 0
    for path in paths:
        if not os.path.exists(path):
            continue
        if not os.path.isfile(path):
            continue
        total += os.path.getsize(path)

    return total

def get_disk_capacity_by_df(dir_path):
    total, avail = shell.call("df %s|tail -1|awk '{print $(NF-4), $(NF-2)}'" % dir_path).split()
    return int(total) * 1024, int(avail) * 1024

def get_folder_size(path = "."):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += (get_local_file_disk_usage(fp) if os.path.isfile(fp) else 0)
    return total_size

def get_filesystem_folder_size(path = "."):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += (os.path.getsize(fp) if os.path.isfile(fp) else 0)
    return total_size

def is_mounted(path=None, url=None):
    if url:
        url = re.sub(r'/{2,}','/',url.rstrip('/'))

    if url and path:
        cmdstr = "mount | grep -F '%s on ' | grep -F '%s ' " % (url, path)
    elif not url:
        cmdstr = "mount | grep -F '%s '" % path
    elif not path:
        cmdstr = "mount | grep -F '%s on '" % url
    else:
        raise Exception('path and url cannot both be None')

    return shell.run(cmdstr) == 0

def mount(url, path, options=None, fstype=None):
    cmd = shell.ShellCmd("mount | grep '%s'" % path)
    cmd(is_exception=False)
    if cmd.return_code == 0: raise MountError(url, '%s is occupied by another device. Details[%s]' % (path, cmd.stdout))

    if not os.path.exists(path):
        try:
            os.makedirs(path, 0o775)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

    cmdstr = "mount"

    if fstype and not options:
        cmdstr += " -t %s" % fstype

    if options:
        cmdstr += " -o %s" % options

    cmdstr = "%s %s %s" % (cmdstr, url, path)
    if "$" in cmdstr or ";" in cmdstr or "(" in cmdstr or "`" in cmdstr:
        raise MountError(url, 'unexpected options: %s' % cmdstr)

    o = shell.ShellCmd("timeout 180 " + cmdstr)
    o(False)
    if o.return_code == 124:
        raise Exception('unable to mount the nfs primary storage[url:%s] in 180s, timed out' % url)
    elif o.return_code != 0:
        raise Exception('mount failed: %s' % cmdstr)

def umount(path, is_exception=True):
    cmd = shell.ShellCmd('umount -f -l %s' % path)
    cmd(is_exception=is_exception)
    return cmd.return_code == 0

def remount(url, path, options=None):
    if not is_mounted(path, url):
        mount(url, path, options)
        return

    o = shell.ShellCmd('timeout 180 mount -o remount %s' % path)
    o(False)
    if o.return_code == 124:
        raise Exception('unable to access the mount path[%s] of the nfs primary storage[url:%s] in 180s, timeout' %
                        (path, url))
    elif o.return_code != 0:
        o.raise_error()

def get_host_name():
    return os.uname()[1]

def native_io_disk_exists(vm_xml_obj):
    return any(xmlobject.has_element(disk, 'driver.io_') and disk.driver.io_ == 'native'
               for disk in vm_xml_obj.devices.get_child_node_as_list('disk'))

def sshfs_mount_with_vm_xml(vm_xml_obj, username, hostname, port, password, url, mountpoint, writebandwidth=None):
    vmuuid = vm_xml_obj.name.text_
    out = shell.call("pgrep -a 'qemu-kvm|qemu-system' | grep -w %s | grep [-]machine" % vmuuid)
    is_aio, uid = False, 0

    if out:
        is_aio = native_io_disk_exists(vm_xml_obj)
        uid = int(out.split(" ", 2)[0])
    return sshfs_mount(username, hostname, port, password, url, mountpoint, writebandwidth, not is_aio, uid)

def sshfs_mount(username, hostname, port, password, url, mountpoint, writebandwidth=None, direct_io=True, uid=0):
    fd, fname = tempfile.mkstemp()
    os.chmod(fname, 0o500)

    if not writebandwidth:
        content = "#!/bin/bash\n/usr/bin/sshpass -p %s ssh " \
                  "-o StrictHostKeyChecking=no " \
                  "-o UserKnownHostsFile=/dev/null -p %d $*\n" % (
                      shellquote(password), port)
    else:
        content = "#!/bin/bash\n/usr/bin/sshpass -p %s ssh " \
                  "-o 'ProxyCommand pv -q -L %sk | nc %s %s' " \
                  "-o StrictHostKeyChecking=no " \
                  "-o UserKnownHostsFile=/dev/null -p %d $*\n" % (
                      shellquote(password), writebandwidth // 1024 // 8, hostname, port, port)
    os.write(fd, content.encode())
    os.close(fd)

    allow = 'allow_root' if uid == 0 else 'allow_other'
    direct_io_opt = 'direct_io,' if direct_io else ''
    try:
        return shell.check_run("/usr/bin/sshfs %s@%s:%s %s -o %s%s,compression=no,ConnectTimeout=30,ssh_command='%s'" % (
            username, hostname, url, mountpoint, direct_io_opt, allow, fname))
    finally:
        os.remove(fname)

def fumount(mountpoint, timeout = 10):
    return shell.run("timeout %s fusermount -u %s" % (timeout, mountpoint))

def is_valid_address(address):
    for family in (socket.AF_INET, socket.AF_INET6):
        try:
            socket.inet_pton(family, address)
            return True
        except socket.error:
            pass
    return False

def is_valid_hostname(hostname):
    if is_valid_address(hostname):
        return True

    try:
        socket.getaddrinfo(hostname, None)
        return True
    except socket.error:
        return False

def get_host_by_name(host):
    if is_valid_address(host):
        return host
    return socket.getaddrinfo(host, None)[0][4][0]

def get_hostname():
    return socket.gethostname()

def get_hostname_fqdn():
    import sys
    if sys.version_info.major < 3:
        return socket.getaddrinfo(socket.gethostname(), 0, 0, 0, 0, socket.AI_CANONNAME)[0][3]
    return socket.getaddrinfo(socket.gethostname(), 0, flags=socket.AI_CANONNAME)[0][3]

def parse_nfs_url(url):
    if url.startswith(IPV6_HOST_PREFIX):
        end = url.find(IPV6_HOST_SUFFIX)
        if end <= 0:
            raise InvalidNfsUrlError(url, 'IPv6 host must be enclosed by []')

        host = url[len(IPV6_HOST_PREFIX):end]
        suffix = url[end + len(IPV6_HOST_SUFFIX):]
        if not suffix.startswith(NFS_URL_SEPARATOR):
            raise InvalidNfsUrlError(url, 'url should be [IPv6]:/absolute/path')

        return host, suffix[len(NFS_URL_SEPARATOR):]

    ts = url.split(NFS_URL_SEPARATOR)
    if len(ts) != 2:
        raise InvalidNfsUrlError(url, 'url should have one and only one ":"')

    return ts[0], ts[1]


def is_valid_nfs_url(url):
    host, path = parse_nfs_url(url)
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise InvalidNfsUrlError(url, '%s cannont resolve to ip address' % host)

    if not os.path.isabs(path): raise InvalidNfsUrlError(url, '%s is not an absolute path' % path)
    return True

def get_mount_url(path):
    cmdstr = "findmnt %s | tail -1" % path
    cmd = shell.ShellCmd(cmdstr)
    out = cmd(is_exception=False)
    if len(out) != 0:
        return out.strip('\n').split(' ')[1]

def get_mounted_url_by_dir(path):
    paths = []
    cmdstr = "mount | grep '%s'" % path
    cmd = shell.ShellCmd(cmdstr)
    out = cmd(is_exception=False)
    if cmd.return_code: return paths
    lst = out.split('\n')
    if '' in lst: lst.remove('')
    paths = [l.split(' ')[2] for l in lst]
    return paths

def get_mounted_path(url):
    paths = []
    if not is_mounted(url=url): return paths
    cmdstr = "mount | grep '%s'" % url
    cmd = shell.ShellCmd(cmdstr)
    out = cmd(is_exception=False)
    if cmd.return_code: return paths
    lst = out.split('\n')
    if '' in lst: lst.remove('')
    paths = [l.split(' ')[2] for l in lst]
    return paths

def umount_by_url(url):
    paths = get_mounted_path(url)
    if not paths: return
    for p in paths:
        umount(p, is_exception=False)

def umount_by_path(path):
    paths = get_mounted_url_by_dir(path)
    if not paths: return
    for p in paths:
        umount(p, is_exception=False)

def get_file_size_by_http_head(url):
    output = shell.call('curl --head %s' % url)
    for l in output.split('\n'):
        if 'Content-Length' in l:
            filesize = l.split(':')[1].strip()
            return int(filesize)
    return None

def shellquote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"

def remote_shell_quote(s: str) -> str:
    return ("\\''" + s.replace("'", "'\\''") + "'\\'")

def wget(url, workdir, rename=None, timeout=0, interval=1, callback=None, callback_data=None, cert_check=False):
    def get_percentage(filesize, dst):
        try:
            curr_size = get_local_file_size(dst)
            p = round(float(curr_size)/float(filesize) * 100, 2)
            return p
        except Exception as e:
            logger.debug('%s may have not been ready, %s' % (dst, str(e)))
            return None

    def get_file_size(url):
        output = shell.call('curl --head %s' % url)
        for l in output.split('\n'):
            if 'Content-Length' in l:
                filesize = l.split(':')[1].strip()
                return True, int(filesize)
        return False, 0

    cmdlst = ['wget']
    dst_file = os.path.join(workdir, os.path.basename(url))
    src_file = os.path.join(workdir, os.path.basename(url))
    if os.path.exists(src_file):
        os.remove(src_file)

    if not cert_check:
        cmdlst.append('--no-check-certificate')
    cmdlst.append(url)
    if rename:
        cmdlst.append('-O %s' % rename)
        dst_file = os.path.join(workdir, rename)
    cmdlst.append('2>/dev/null')

    cmd = ' '.join(cmdlst)

    is_support_file_size, filesize = get_file_size(url)
    if is_support_file_size:
        process = shell.get_process(cmd, shell=True, executable='/bin/sh', workdir=workdir)
        is_timeout = False
        count = 0
        logger.debug('start to download %s, total size: %s' % (url, filesize))
        try:
            while process.poll() is None:
                time.sleep(interval)
                count += interval
                if timeout > 0 and count > timeout:
                    process.kill()
                    is_timeout = True
                    break

                if callback:
                    p = get_percentage(filesize, dst_file)
                    if p:
                        try:
                            callback(p, callback_data)
                        except Exception:
                            pass

            if is_timeout:
                raise LinuxError('wget %s timeout after %s seconds' % (url, timeout))

            return process.returncode
        except Exception as e:
            logger.warn(get_exception_stacktrace())
            if process.poll() is None:
                process.kill()
            raise LinuxError('unhandled exception happened when downloading %s, %s' % (url, str(e)))
    else:
        shell.call(cmd, workdir=workdir)
        return 0

def md5sum(file_path):
    return 'md5sum is not calculated due to time cost'

    #cmd = shell.ShellCmd('md5sum %s' % file_path)
    #cmd()
    #output = cmd.stdout
    #sum5 = output.split(' ')[0]
    #return sum5.strip()

def mkdir(path, mode=0o755):
    if os.path.isdir(path):
        return True

    if os.path.isfile(path):
        try:
           os.rename(path, path+"-bak")
        except OSError as e:
           logger.warn('mv -f %s %s-bak failed: %s' % (path, path, e))
           return False

    #This fix for race condition when two processes make the dir at the same time
    try:
        os.makedirs(path, mode)
        return True
    except OSError as e:
        logger.warn("mkdir for path %s failed: %s " % (path, e))

    return False


def create_temp_file(dir=None):
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dir)
    os.close(tmp_fd)
    return tmp_path


def write_to_temp_file(content):
    (tmp_fd, tmp_path) = tempfile.mkstemp()
    tmp_fd = os.fdopen(tmp_fd, 'w')
    tmp_fd.write(content)
    tmp_fd.close()
    return tmp_path

def ssh(hostname, sshkey, cmd, user='root', sshPort=22):
    def create_ssh_key_file():
        return write_to_temp_file(sshkey)

    sshkey_file = create_ssh_key_file()
    os.chmod(sshkey_file, 0o600)

    try:
        return shell.call('ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s %s "%s"' % (sshPort, sshkey_file, format_ssh_target(user, hostname), cmd))
    finally:
        if sshkey_file:
            os.remove(sshkey_file)

def format_ssh_target(user, hostname):
    return '%s@%s' % (user, network_ipv6.format_url_host(hostname))

def sshpass_run(hostname, password, cmd, user='root', port=22):
    sshpass_file = write_to_temp_file(password)
    os.chmod(sshpass_file, 0o600)

    try:
        s = shell.ShellCmd('sshpass -f %s ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null %s "%s"' % (
            sshpass_file, port, format_ssh_target(user, hostname), cmd))
        s(False)
        return s.return_code, s.stdout, s.stderr
    finally:
        rm_file_force(sshpass_file)

def sshpass_call(hostname, password, cmd, user='root', port=22):
    sshpass_file = write_to_temp_file(password)
    os.chmod(sshpass_file, 0o600)

    try:
        return shell.call('sshpass -f %s ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null %s "%s"' % (
            sshpass_file, port, format_ssh_target(user, hostname), cmd))
    finally:
        rm_file_force(sshpass_file)

def build_sshpass_cmd(hostname, password, cmd, user='root', port=22):
    sshpass_file = write_to_temp_file(password)
    os.chmod(sshpass_file, 0o600)

    cmd = 'sshpass -f %s ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null %s@%s "%s"' % (
            sshpass_file, port, user, hostname, cmd)
    return cmd, sshpass_file

def get_local_file_size(path):
    return os.path.getsize(path)

def get_local_file_disk_usage(path):
    if os.path.isdir(path):
        return os.path.getsize(path)
    fmt = get_img_fmt(path)
    if fmt == 'qcow2':
        return int(shell.call("du -a --block-size=1 %s | awk '{print $1}'" % path).strip())
    return os.path.getsize(path)

def scp_download(hostname, sshkey, src_filepath, dst_filepath, host_account='root', sshPort=22, bandWidth=None):
    def create_ssh_key_file():
        return write_to_temp_file(sshkey)

    # scp bandwidth limit
    if bandWidth is not None:
        bandWidth = '-l %s' % (int(bandWidth) // 1024)
    else:
        bandWidth = ''

    filename_check_option = '`scp -T 2>&1 | grep -q "unknown option" || echo "-T"`'

    sshkey_file = create_ssh_key_file()
    os.chmod(sshkey_file, 0o600)
    try:
        dst_dir = os.path.dirname(dst_filepath)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        scp_cmd = 'scp {6} {5} -P {0} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i {1} {2}:{3} {4}'\
            .format(sshPort, sshkey_file, format_ssh_target(host_account, hostname), shellquote(src_filepath).replace(" ", "\\ "), dst_filepath, bandWidth, filename_check_option)
        shell.call(scp_cmd)
        os.chmod(dst_filepath, 0o664)
    finally:
        if sshkey_file:
            os.remove(sshkey_file)

def scp_upload(hostname, sshkey, src_filepath, dst_filepath, host_account='root', sshPort=22):
    def create_ssh_key_file():
        return write_to_temp_file(sshkey)

    if not os.path.exists(src_filepath):
        raise LinuxError('cannot find file[%s] to upload to %s@%s:%s' % (src_filepath, host_account, hostname, dst_filepath))

    sshkey_file = create_ssh_key_file()
    os.chmod(sshkey_file, 0o600)
    try:
        dst_dir = os.path.dirname(dst_filepath)
        ssh_cmd = 'ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s %s "mkdir -m 777 -p %s"' % (sshPort, sshkey_file, format_ssh_target(host_account, hostname), dst_dir)
        shell.call(ssh_cmd)
        scp_cmd = 'scp -P %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s %s %s:%s' % (sshPort, sshkey_file, src_filepath, format_ssh_target(host_account, hostname), dst_filepath)
        shell.call(scp_cmd)
    finally:
        if sshkey_file:
            os.remove(sshkey_file)

def sftp_get(hostname, sshkey, filename, download_to, timeout=0, interval=1, callback=None, callback_data=None, sshPort=22, get_size=False):
    def create_ssh_key_file():
        return write_to_temp_file(sshkey)

    def get_file_size():
        try:
            keyfile_path = create_ssh_key_file()
            batch_cmd = "ls -s '%s'" % filename
            cmdstr = '/usr/bin/ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s %s "%s"' % (sshPort, keyfile_path, hostname, batch_cmd)
            cmd = shell.ShellCmd(cmdstr)
            cmd()
            output = cmd.stdout.strip()
            outputs = output.split('\n')
            size_pair = outputs[0]
            return int(size_pair.split()[0])
        finally:
            if keyfile_path:
                os.remove(keyfile_path)
            if batch_file_path:
                os.remove(batch_file_path)

    def caculate_percentage(total_size):
        if os.path.exists(download_to):
            curr_size = get_local_file_size(download_to)
            #print 'curr:%s total: %s' % (curr_size, total_size)
            return round(float(curr_size)/float(total_size) * 100, 2)
        else:
            return 0.0


    keyfile_path = None
    batch_file_path = None
    try:
        file_size = get_file_size() * 1024
        if get_size:
            return file_size
        keyfile_path = create_ssh_key_file()
        batch_file_path = write_to_temp_file("get '%s' %s" % (filename, download_to))
        cmd = '/usr/bin/sftp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o IdentityFile=%s -b %s %s' % (keyfile_path, batch_file_path, hostname)
        process = shell.get_process(cmd, shell=True, executable='/bin/sh')
        is_timeout = False
        count = 0
        while process.poll() is None:
            time.sleep(interval)
            count += interval
            if timeout > 0 and count > timeout:
                process.kill()
                is_timeout = True
                break

            if callback:
                percentage = caculate_percentage(file_size)
                try:
                    callback(str(percentage), callback_data)
                except Exception:
                    pass

        src_file = '%s/%s' % (hostname, filename)
        if is_timeout: raise LinuxError('sftp get %s timeout after %s seconds' % (src_file, timeout))
        if process.returncode != 0 : raise LinuxError('sftp get %s failed, because %s' % (src_file, process.stderr))
        if callback:
            callback("100.0", callback_data)

        return process.returncode
    except Exception as e:
        try:
            process.terminate()
        except:
            pass

        if os.path.exists(download_to):
            os.remove(download_to)

        raise e
    finally:
        if keyfile_path:
            os.remove(keyfile_path)
        if batch_file_path:
            os.remove(batch_file_path)

def qcow2_size_and_actual_size(file_path):
    cmd = shell.ShellCmd('''set -o pipefail; %s %s --output=json''' % (qemu_img.subcmd('info'), file_path))
    cmd(False)
    if cmd.return_code != 0:
        raise Exception('cannot get the virtual/actual size of the file[%s], %s %s' % (shellquote(file_path), cmd.stdout, cmd.stderr))

    logger.debug('qcow2_info: %s' % cmd.stdout)

    out = json.loads(cmd.stdout.strip())
    virtual_size, actual_size = out.get('virtual-size'), out.get('actual-size')
    if not virtual_size and not actual_size:
        raise Exception('cannot get the virtual/actual size of the file[%s], %s %s' % (shellquote(file_path), cmd.stdout, cmd.stderr))

    virtual_size = int(virtual_size) if virtual_size else None
    return virtual_size, actual_size

'''  
   file command output:
   # file FusionStack-1.5.iso 
     FusionStack-1.5.iso: # ISO 9660 CD-ROM filesystem data 'ZS' (bootable) 
'''
def get_img_file_fmt(src):
    fmt = get_img_fmt(src)
    if fmt == "raw":
        result = shell.call("set -o pipefail; file %s | awk '{print $2, $3}'" % src)
        if "ISO" in result:
            fmt = "iso"
    return fmt


def get_img_fmt(src):
    if os.path.exists(src):
        with open(src, 'rb') as f:
            return get_fmt_from_magic(f.read(4))

    fmt = shell.call(
        "set -o pipefail; %s %s | grep -w '^file format' | awk '{print $3}'" % (qemu_img.subcmd('info'), src))
    fmt = fmt.strip()
    if fmt not in ['raw', 'qcow2', 'vmdk']:
        logger.debug("/usr/bin/qemu-img info %s" % src)
        raise Exception('unknown format[%s] of the image file[%s]' % (fmt, src))
    return fmt


def get_fmt_from_magic(magic: bytes):
    if magic == b'QFI\xfb':
        return 'qcow2'
    elif magic == b'KDMV':
        return 'vmdk'
    else:
        return 'raw'


def qcow2_clone(src, dst, size=""):
    fmt = get_img_fmt(src)
    shell.check_run('/usr/bin/qemu-img create -F %s -b %s -f qcow2 %s %s' % (fmt, src, dst, size))
    os.chmod(dst, 0o660)

def qcow2_clone_with_cmd(src, dst, cmd=None):
    size = cmd.virtualSize if cmd.virtualSize else ""
    if cmd is None or cmd.kvmHostAddons is None or cmd.kvmHostAddons.qcow2Options is None:
        qcow2_clone(src, dst, size)
    else:
        qcow2_clone_with_option(src, dst, cmd.kvmHostAddons.qcow2Options, size)

def qcow2_clone_with_option(src, dst, opt="", size=""):
    # NOTE(weiw): qcow2 doesn't support specify backing file and preallocation at same time
    pattern = re.compile("\-o\ preallocation\=\w+ ")
    opt = re.sub(pattern, " ", opt)

    fmt = get_img_fmt(src)
    shell.check_run('/usr/bin/qemu-img create -F %s %s -b %s -f qcow2 %s %s' % (fmt, opt, src, dst, size))
    os.chmod(dst, 0o660)

def raw_clone(src, dst):
    shell.check_run('/usr/bin/qemu-img create -b %s -f raw %s' % (src, dst))
    os.chmod(dst, 0o660)


def qcow2_create(dst, size, chmod=True):
    shell.check_run('/usr/bin/qemu-img create -f qcow2 %s %s' % (dst, size))
    if (chmod):
        os.chmod(dst, 0o660)

def qemu_img_resize(target, size, fmt='qcow2', force=False):
    fmt_option = '-f %s' % fmt
    force_option = '--shrink' if force else ''
    shell.check_run('/usr/bin/qemu-img resize %s %s %s %s' % (fmt_option, force_option, target, size))

def qcow2_create_with_cmd(dst, size, cmd=None, discard_on_metadata=True):
    if cmd is None or cmd.kvmHostAddons is None or cmd.kvmHostAddons.qcow2Options is None:
        qcow2_create(dst, size)
    else:
        qcow2_create_with_option(dst, size, cmd.kvmHostAddons.qcow2Options, discard_on_metadata)

def qcow2_create_with_option(dst, size, opt="", discard_on_metadata=True):
    shell.check_run('/usr/bin/qemu-img create -f qcow2 %s %s %s' % (opt, dst, size))
    if discard_on_metadata and 'preallocation=metadata' in opt and 'extended_l2=on' not in opt:
        qcow2_discard(dst)
    os.chmod(dst, 0o660)

def qcow2_create_with_backing_file(backing_file, dst, size=""):
    fmt = get_img_fmt(backing_file)
    shell.call('/usr/bin/qemu-img create -F %s -f qcow2 -b %s %s %s' % (fmt, backing_file, dst, size))
    os.chmod(dst, 0o660)

def qcow2_create_with_backing_file_and_cmd(backing_file, dst, cmd=None, size=""):
    if cmd is None or cmd.kvmHostAddons is None or cmd.kvmHostAddons.qcow2Options is None:
        qcow2_create_with_backing_file(backing_file, dst, size)
    else:
        qcow2_create_with_backing_file_and_option(backing_file, dst, cmd.kvmHostAddons.qcow2Options, size)

def qcow2_create_with_backing_file_and_option(backing_file, dst, opt="", size=""):
    fmt = get_img_fmt(backing_file)

    # NOTE(weiw): qcow2 doesn't support specify backing file and preallocation at same time
    pattern = re.compile("\-o\ preallocation\=\w+ ")
    opt = re.sub(pattern, " ", opt)

    shell.call('/usr/bin/qemu-img create -F %s -f qcow2 %s -b %s %s %s' % (fmt, opt, backing_file, dst, size))
    os.chmod(dst, 0o660)

def raw_create(dst, size):
    shell.check_run('/usr/bin/qemu-img create -f raw %s %s' % (dst, size))
    os.chmod(dst, 0o660)


def create_template(src, dst, dst_format='qcow2', compress=False, shell=shell, progress_output=None, opts=None):
    fmt = get_img_fmt(src)
    if fmt == 'raw':
        return raw_create_template(src, dst, dst_format=dst_format, shell=shell, progress_output=progress_output)
    if fmt == 'qcow2':
        return qcow2_create_template(src, dst, compress, dst_format=dst_format, shell=shell, progress_output=progress_output, opts=opts)
    raise Exception('unknown format[%s] of the image file[%s]' % (fmt, src))


def qcow2_create_template(src, dst, compress, dst_format='qcow2', shell=shell, progress_output=None, opts=None, bitmap=None):
    redirect, ext_opts = "", []
    if progress_output:
        redirect = " > " + progress_output
        ext_opts.append("-p")

    if compress:
        ext_opts.append("-c")

    if opts:
        ext_opts.append(opts)

    if bitmap:
        ext_opts.extend(["--bitmap", shellquote(bitmap)])

    shell.call('%s %s -f qcow2 -O %s %s %s %s' % (qemu_img.subcmd('convert'), " ".join(ext_opts), dst_format, src, dst, redirect))

def raw_create_template(src, dst, dst_format='qcow2', shell=shell, progress_output=None):
    redirect, ext_opts = "", []
    if progress_output:
        redirect = " > " + progress_output
        ext_opts.append("-p")

    shell.call('%s %s -f raw -O %s %s %s %s' % (qemu_img.subcmd('convert'), " ".join(ext_opts), dst_format, src, dst, redirect))

def qcow2_convert_to_raw(src, dst):
    shell.call('%s -f qcow2 -O raw %s %s' % (qemu_img.subcmd('convert'), src, dst))

def qcow2_convert(src, dst, dst_format='qcow2', shell=shell, progress_output=None, opts=None, bitmap=None):
    qcow2_create_template(src, dst, False, dst_format=dst_format, shell=shell,
                          progress_output=progress_output, opts=opts, bitmap=bitmap)

def qcow2_commit(top, base):
    shell.call('%s -f qcow2 -b %s %s' % (qemu_img.subcmd('commit'), base, top))

def nbd_qemu_img_convert(src, out_format, dst):
    shell.call('%s -W -m 16 -f nbd -O %s %s %s' % (qemu_img.subcmd('convert'), out_format, src, dst))

def qcow2_rebase(backing_file, target):
    if backing_file:
        fmt = get_img_fmt(backing_file)
        backing_option = '-F %s -b "%s"' % (fmt, backing_file)
    else:
        backing_option = '-b "%s"' % backing_file

    def resize_backing_if_need():
        top_virtual_size = int(qcow2_get_virtual_size(target))
        backing_chain = qcow2_get_backing_chain(target)
        for idx, bf in enumerate(backing_chain):
            if idx == len(backing_chain)-1 and get_img_fmt(bf) != 'qcow2':
                break
            bf_virtual_size = int(qcow2_get_virtual_size(bf))
            if bf_virtual_size < top_virtual_size:
                qemu_img_resize(bf, top_virtual_size)
            if bf == backing_file:
                break

    if qemu_img.resize_backing_before_rebase():
        resize_backing_if_need()

    with TempAccessible(target):
        shell.call('%s -f qcow2 %s %s' % (qemu_img.subcmd('rebase'), backing_option, target))

def qcow2_rebase_no_check(backing_file, target, backing_fmt=None):
    fmt = backing_fmt if backing_fmt else get_img_fmt(backing_file)
    with TempAccessible(target):
        shell.call('%s -F %s -u -f qcow2 -b "%s" %s' % (qemu_img.subcmd('rebase'), fmt, backing_file, target))

def qcow2_virtualsize(file_path):
    file_path = shellquote(file_path)
    cmd = shell.ShellCmd("set -o pipefail; %s %s | grep -w 'virtual size' | awk -F '(' '{print $2}' | awk '{print $1}'" %
            (qemu_img.subcmd('info'), file_path))
    cmd(False)
    if cmd.return_code != 0:
        raise Exception('cannot get the virtual size of the file[%s], %s %s' % (file_path, cmd.stdout, cmd.stderr))
    out = cmd.stdout.strip()
    return int(out)

def qcow2_get_backing_file(path):
    if not os.path.exists(path) and ":" in path:
        # find through protocol
        out = shell.call("%s %s" %(qemu_img.subcmd('info'), path))
        for line in out.splitlines():
            if "backing file:" in line:
                return line.replace("backing file:", "", 1).strip()
        return ""

    with open(path, 'rb') as resp:
        magic = resp.read(4)
        if magic != b'QFI\xfb':
            return ""

        # read backing file info from header
        resp.seek(8)
        backing_file_info = resp.read(12)
        backing_file_offset = struct.unpack('>Q', backing_file_info[:8])[0]
        if backing_file_offset == 0:
            return ""

        backing_file_size = struct.unpack('>L', backing_file_info[8:])[0]
        resp.seek(backing_file_offset)
        return resp.read(backing_file_size).decode()

def qcow2_get_virtual_size(path):
    # type: (str) -> int
    if not os.path.exists(path):
        # for rbd image
        out = shell.call("%s %s | grep -P -o 'virtual size:\K.*' | awk -F '[()a-zA-Z]' '{print $3}'" %
                (qemu_img.subcmd('info'), path))
        return int(out.strip())

    with open(path, 'rb') as resp:
        magic = resp.read(4)
        if magic != b'QFI\xfb':
            return os.path.getsize(path)

        # read virtual size info from header
        resp.seek(24)
        return struct.unpack('>Q', resp.read(8))[0]

def qcow2_direct_get_backing_file(path):
    o = shell.call('dd if=%s bs=4k count=1 iflag=direct' % path, output_bytes=True)
    magic = o[:4]
    if magic != b'QFI\xfb':
        return ""

    # read backing file info from header
    backing_file_info = o[8:20]
    backing_file_offset = struct.unpack('>Q', backing_file_info[:8])[0]
    if backing_file_offset == 0:
        return ""

    backing_file_size = struct.unpack('>L', backing_file_info[8:])[0]
    return o[backing_file_offset:backing_file_offset+backing_file_size].decode()

# Get derived file and all its backing files
def qcow2_get_file_chain(path):
    out = shell.call("%s --backing-chain %s | grep 'image:' | awk '{print $2}'" %
            (qemu_img.subcmd('info'), path))
    return out.splitlines()

# Get derived file all backing files
def qcow2_get_backing_chain(path):
    ret = []
    backing = qcow2_get_backing_file(path)
    while backing:
        ret.append(backing)
        backing = qcow2_get_backing_file(backing)

    return ret

def get_qcow2_file_chain_size(path):
    chain = qcow2_get_file_chain(path)
    size = 0
    for path in chain:
        size += get_local_file_disk_usage(path)
    return size

def get_qcow2_base_backing_file_recusively(path):
    chain = qcow2_get_file_chain(path)
    return chain[-1]

def get_qcow2_base_images_recusively(vol_install_dir, image_cache_dir):
    real_vol_dir = os.path.realpath(vol_install_dir)
    real_cache_dir = os.path.realpath(image_cache_dir)

    base_image = set()
    for p in list_all_file(real_vol_dir):
        backing_file = qcow2_get_backing_file(p)
        if backing_file:
            real_image_path = os.path.realpath(backing_file)
            if real_image_path.startswith(real_cache_dir):
                base_image.add(real_image_path)

    return base_image

def qcow2_fill(seek, length, path, raise_excpetion=False):
    cmd = shell.ShellCmd("qemu-io -c 'write %s %s' %s -n" % (seek, length, path))
    cmd(raise_excpetion)
    logger.debug("qcow2_fill return code: %s, stdout: %s, stderr: %s" % (cmd.return_code, cmd.stdout, cmd.stderr))


def qcow2_measure_required_size(path, cluster_size=0):
    opts = "" if cluster_size == 0 else "-o cluster_size=%s" % cluster_size

    out = shell.call("%s --output=json -f qcow2 -O qcow2 %s %s" % (qemu_img.subcmd('measure'), opts, path))
    return int(simplejson.loads(out)["required"])


def qcow2_get_cluster_size(path):
    out = shell.call("%s --output=json %s" % (qemu_img.subcmd('info'), path))
    ret = simplejson.loads(out)
    return 0 if 'cluster-size' not in ret else ret['cluster-size']


def qcow2_discard(path):
    virtual_size = int(qcow2_get_virtual_size(path))
    cmd = shell.ShellCmd('''
#!/bin/bash
i=0
while(($i < {0}))
do
qemu-io -c "discard $[i*2145386496] 2145386496" -f qcow2 -d unmap {1}
let i+=1
done
qemu-io -c "discard $[i*2145386496] {2}" -f qcow2 -d unmap {1}
    '''.format(virtual_size // 2145386496, path, virtual_size % 2145386496))

    cmd(False)
    logger.debug("qcow2 discard return code: %s, stderr: %s" % (cmd.return_code, cmd.stderr))

def get_block_discard_max_bytes(path):
    base_name = os.path.basename(path)
    file_max_bytes = "/sys/class/block/%s/queue/discard_max_bytes" % base_name
    if not os.path.exists(path) or not os.path.exists(file_max_bytes):
        raise Exception("cannot get block %s discard max bytes" % path)

    return int(read_file(file_max_bytes))

def get_block_discard_granularity(path):
    base_name = os.path.basename(path)
    file_granularity = "/sys/class/block/%s/queue/discard_granularity" % base_name
    if not os.path.exists(path) or not os.path.exists(file_granularity):
        raise Exception("cannot get block %s discard granularity" % path)

    return int(read_file(file_granularity))

def support_blkdiscard(path):
    return get_block_discard_max_bytes(path) > 0


def pkill_by_pattern(*args):
    command = "pkill -15 -f '%s'" % "' '".join(str(arg) for arg in args)
    return shell.run(command)


class AbstractFileConverter(object, metaclass=abc.ABCMeta):
    def __init__(self):
        pass

    @abc.abstractmethod
    def convert_to_file(self, src, dst):
        pass

    @abc.abstractmethod
    def convert_from_file_with_backing(self, src, dst, backing, backing_fmt):
        # type: (str, str, str, str) -> int
        pass

    @abc.abstractmethod
    def get_backing_file(self, path):
        pass

    @abc.abstractmethod
    def get_size(self, path):
        # type: (str) -> int
        pass

    @abc.abstractmethod
    def exists(self, path):
        # type: (str) -> bool
        pass

def upload_chain_to_filesystem(converter, first_node_path, dst_vol_dir, overwrite=False):
    # type: (AbstractFileConverter, str, str, bool) -> None

    def upload(src_path):
        dst_path = os.path.join(dst_vol_dir, os.path.basename(src_path))
        if os.path.exists(dst_path):
            if overwrite:
                rm_file_force(dst_path)
            else:
                return dst_path

        converter.convert_to_file(src_path, dst_path)
        return dst_path

    dst_current_node_path = upload(first_node_path)
    parent_path = converter.get_backing_file(first_node_path)
    while parent_path:
        dst_parent_path = upload(parent_path)
        qcow2_rebase_no_check(dst_parent_path, dst_current_node_path)

        dst_current_node_path = dst_parent_path
        parent_path = converter.get_backing_file(parent_path)


def download_chain_from_filesystem(converter, first_node_path, dst_vol_dir, overwrite=False):
    # type: (AbstractFileConverter, str, str, bool) -> list[tuple[str, int]]
    downloaded_chain_info = []
    def download(src_path):
        dst_path = os.path.join(dst_vol_dir, os.path.basename(src_path))
        src_backing_path = qcow2_get_backing_file(src_path)
        dst_backing_path = os.path.join(dst_vol_dir, os.path.basename(src_backing_path)) if src_backing_path else ''
        if converter.exists(dst_path) and not overwrite:
            size = converter.get_size(dst_path)
        else:
            backing_fmt = get_img_fmt(src_backing_path) if src_backing_path else None
            size = converter.convert_from_file_with_backing(src_path, dst_path, dst_backing_path, backing_fmt)

        downloaded_chain_info.append((dst_path, size))
        if src_backing_path:
            download(src_backing_path)

    download(first_node_path)
    return downloaded_chain_info


def rmdir_if_empty(dirpath):
    try:
        os.rmdir(dirpath)
    except:
        pass

def flush_device_ip(dev):
    if is_network_device_existing(dev):
        cmd = shell.ShellCmd("ip addr flush dev %s" % dev)
        cmd(is_exception=False)
        return cmd.stdout

def set_device_ip(dev, ip, netmask):
    if not is_network_device_existing(dev):
        raise LinuxError('cannot find ethernet device %s' % dev)

    if not get_device_ip(dev) == ip:
        iproute.add_address(ip, netmask_to_cidr(netmask), 4, dev, broadcast = netmask_to_broadcast(ip, netmask))

def get_device_ip(dev):
    cmd = shell.ShellCmd("ip addr show dev %s|grep inet|grep -v inet6|awk -F'inet' '{print $2}'|awk '{print $1}'|awk -F'/24' '{print $1}'" % dev)
    cmd(is_exception=False)
    return cmd.stdout if cmd.stdout != "" else None

def remove_device_ip(dev):
    if not is_network_device_existing(dev):
        return None

    ip = get_device_ip(dev)
    if ip:
        cmd = shell.ShellCmd("ip addr del %s/32 dev %s" % (ip, dev))
        cmd(is_exception=False)
        return cmd.return_code == 0

def is_ip_existing(ip):
    cmd = shell.ShellCmd('ip -4 a|grep -m 1 -w "%s"' % ip)
    cmd(is_exception=False)
    return cmd.return_code == 0

def is_network_device_existing(dev):
    return os.path.exists("/sys/class/net/%s" % dev)

def is_network_ip_using(interface):
    if not is_network_device_existing(interface):
        return False

    ipv4_out = shell.call('ip -4 addr show dev %s | grep "inet "' % interface, exception=False)
    ipv6_out = shell.call('ip -6 addr show dev %s | grep "inet6 " | grep -v " scope link" | grep -v "inet6 fe80:"' % interface, exception=False)
    return bool(ipv4_out.strip() or ipv6_out.strip())

def is_bridge(dev):
    path = "/sys/class/net/%s/bridge" % dev
    return os.path.exists(path)

def is_bridge_slave(dev):
    path = "/sys/class/net/%s/brport" % dev
    return os.path.exists(path)


def is_vif_on_bridge(bridge_name, interface):
    vifs = get_all_bridge_interface(bridge_name)
    if interface in vifs:
        return True

def get_all_bridge_interface(bridge_name):
    cmd = shell.ShellCmd("brctl show %s|sed -n '2,$p'|cut -f 6-10" % bridge_name)
    cmd(is_exception=False)
    vifs = cmd.stdout.split('\n')
    return [v.strip() for v in vifs]

def get_vf_index_by_pci_address(pci_address):
    if not pci_address:
        return None
    physfn_path = "/sys/bus/pci/devices/%s/physfn" % pci_address
    if not os.path.exists(physfn_path):
        return None
    virtfn_path = glob.glob("%s/virtfn*" % physfn_path)
    if not virtfn_path:
        return None
    for virtfn_link in virtfn_path:
        if os.readlink(virtfn_link).split('/')[-1] == pci_address:
            return int(virtfn_link.split('/')[-1].split('virtfn')[-1])

def get_pf_name_by_vf_pci_address(pci_address):
    if not pci_address:
        return None
    physfn_path = "/sys/bus/pci/devices/%s/physfn" % pci_address
    if not os.path.exists(physfn_path):
        return None
    netdev_dirs = glob.glob("%s/net/*" % physfn_path)
    if not netdev_dirs:
        return None
    return netdev_dirs[0].split('/')[-1]

def delete_bridge(bridge_name):
    vifs = get_all_bridge_interface(bridge_name)
    for vif in vifs:
        if vif == '':
            continue
        shell.run("brctl delif %s %s" % (bridge_name, vif))

    shell.run("ip link set %s down" % bridge_name)
    shell.run("brctl delbr %s" % bridge_name)

def check_interface_configuration_exist(ifnames):
    existing_interfaces = []
    for ifname in ifnames:
        config_path = os.path.join("/etc/sysconfig/network-scripts", "ifcfg-%s" % ifname)
        if os.path.exists(config_path):
            existing_interfaces.append(ifname)
    return existing_interfaces

def check_bridge_with_interface(vlan_interface, expected_bridge_name):
    bridge_name = find_bridge_having_physical_interface(vlan_interface)
    if bridge_name and bridge_name != expected_bridge_name:
        raise Exception('failed to check vlan interface[%s], it has been occupied by bridge[%s]'
                        % (vlan_interface, bridge_name))

def update_bridge_interface_configuration(old_interface, new_interface, bridge_name, l2_network_uuid):
    check_bridge_with_interface(old_interface, bridge_name)
    # Check if configuration files exist for the old or new interface to prevent conflicts due to automatic reload
    interfaces_conf_exist = check_interface_configuration_exist([new_interface, old_interface])
    if interfaces_conf_exist:
        raise Exception(
            "Detected static config files for interfaces: [%s]. "
            "Please manually verify the '/etc/sysconfig/network-scripts/ifcfg-*' directory to ensure no outdated configurations exist, "
            "as they may cause conflicts after the update."
            % ", ".join(interfaces_conf_exist)
        )
    if get_device_ip(bridge_name) is not None:
        raise Exception(
            "The bridge [%s] is currently assigned an IP address. "
            "Modifying the bridge binding while it has an active IP may cause network disruptions. "
            "Please manually remove the IP configuration before proceeding."
            % bridge_name
        )
    ip_link_set_net_device_nomaster(old_interface)
    ip_link_set_net_device_master(new_interface, bridge_name)
    set_device_uuid_alias(new_interface, l2_network_uuid)


def find_bridge_having_physical_interface(ifname):
    if is_bridge_slave(ifname):
        br_name = shell.call("cat /sys/class/net/%s/master/uevent | grep 'INTERFACE' | awk -F '=' '{printf $2}'" % ifname)
        if br_name == "":
            return None
        return br_name
    return None

def find_route_interface_by_destination_ip(ip_addr):
    '''
        find the interface for route, when connect to the destination ip.
    '''
    route = shell.call("ip r get {}".format(ip_addr))
    if route:
        return route.split('dev')[1].strip().split()[0]

def find_route_interface_ip_by_destination_ip(ip_addr):
    route = shell.call("ip r get {}".format(ip_addr))
    if route:
        return route.split('src')[1].strip().split()[0]

def get_interface_master_device(interface):
    lines = read_file_lines("/sys/class/net/%s/master/uevent" % interface)
    if not lines:
        return None

    for line in lines:
        if line.startswith('INTERFACE='): return line.split('=')[1].strip()
    return None


def get_interface_ip_addresses(interface):
    output = shell.call("ip -4 -o a show %s | awk '{print $4}'" % interface.strip())
    return output.splitlines() if output else []

def is_uplink_interface(iface):
    if iface.startswith('vxlan'):
        return True
    sys_net_path = "/sys/class/net/%s" % iface
    if not os.path.exists(sys_net_path):
        return False
    try:
        if os.path.islink(sys_net_path):
            link_target = os.readlink(sys_net_path)
            if link_target and 'virtual' not in link_target:
                return True
    except OSError:
        return False
    uevent_file = os.path.join(sys_net_path, 'uevent')
    if os.path.isfile(uevent_file):
        with open(uevent_file, 'r') as f:
            for line in f:
                if line.strip().startswith('DEVTYPE=') and 'vlan' in line:
                    return True
    return False

def get_bridge_lower_interfaces(bridge):
    result = []
    sys_bridge_dir = "/sys/class/net/%s" % bridge
    if not os.path.isdir(sys_bridge_dir):
        return result

    try:
        for entry in os.listdir(sys_bridge_dir):
            if entry.startswith("lower_"):
                iface = entry.replace("lower_", "", 1)
                result.append(iface)
    except OSError:
        pass
    return result

@retry(times=2, sleep_time=1)
def ip_link_set_net_device_master(net_device, master):
    lower_ifaces = get_bridge_lower_interfaces(master)
    for iface in lower_ifaces:
        if iface != net_device and is_uplink_interface(iface):
            raise Exception(
                "Bridge [%s] already has another uplink interface [%s] "
                "besides [%s], cannot add set it now!" %
                (master, iface, net_device)
            )

    shell.call("ip link set %s master %s" % (net_device, master))

    # double check, because sometimes the master is not set successfully, see jira: ZSTAC-54905, ZSV-3260
    actual_result = shell.call("cat /sys/class/net/%s/master/uevent | grep 'INTERFACE' | awk -F '=' '{printf $2}'" % net_device).strip('\n')
    if not actual_result or actual_result != master:
        raise Exception("set net device[%s] master to [%s] failed, try again now" % (net_device, master))

@retry(times=2, sleep_time=1)
def ip_link_set_net_device_nomaster(net_device):
    shell.call("ip link set %s nomaster" % net_device)
    # Double check, because sometimes the master might not be removed successfully
    actual_result = shell.call("cat /sys/class/net/%s/master/uevent | grep 'INTERFACE'" % net_device, exception=False).strip('\n')
    if actual_result:
        raise Exception("set net device[%s] nomaster failed, try again now" % net_device)

def delete_novlan_bridge(bridge_name, interface, move_route=True):
    if not is_network_device_existing(bridge_name):
        logger.debug("can not find bridge %s" % bridge_name)
        return

    if is_vif_on_bridge(bridge_name, interface):
        route_info = _get_dev_route_info(bridge_name) if move_route else None

        delete_bridge(bridge_name)

        shell.call("ip link set %s up" % interface)
        if route_info is not None:
            _restore_dev_route(interface, route_info)

    else:
        logger.debug("bridge %s do not have interface %s. only delete bridge. " % (bridge_name,interface))
        delete_bridge(bridge_name)


def create_bridge(bridge_name, interface, move_route=True):
    if not is_network_device_existing(interface):
        raise LinuxError("network device[%s] is not existing" % interface)
    if is_bridge(interface):
        raise Exception('interface %s is bridge' % interface)

    br_name = find_bridge_having_physical_interface(interface)
    if br_name and br_name != bridge_name:
        raise Exception('failed to create bridge[{0}], physical interface[{1}] has been occupied by bridge[{2}]'.format(bridge_name, interface, br_name))

    route_info = _get_dev_route_info(interface) if move_route else None

    if not is_bridge(bridge_name):
        shell.call("brctl addbr %s" % bridge_name)
    else:
        logger.debug('%s is a bridge device, no need to create bridge' % bridge_name)

    shell.call("brctl stp %s off" % bridge_name)
    shell.call("brctl setfd %s 0" % bridge_name)
    shell.call("ip link set %s up" % bridge_name)

    def modify_device_state_in_networkmanager(device_name, state):
        shell.call("nmcli device set %s managed %s" % (device_name, state), exception=False)

    if br_name == bridge_name:
        logger.debug('%s is a bridge device. Interface %s is attached to bridge. No need to create bridge or attach device interface' % (bridge_name, interface))
    else:
        ip_link_set_net_device_master(interface, bridge_name)

    #Set bridge MAC address as network device MAC address. It will avoid of
    # bridge MAC address is reset to other new added dummy network device's 
    # MAC address.
    shell.call("ip link set %s address `cat /sys/class/net/%s/address`" % (bridge_name, interface))

    if move_route and route_info is not None:
        try:
            move_dev_route(interface, bridge_name, route_info, ignore_missing_source=True)
        except Exception:
            if br_name != bridge_name:
                try:
                    shell.call("ip link set %s nomaster" % interface, exception=False)
                    shell.call("ip link set %s up" % interface, exception=False)
                    _restore_dev_route(interface, route_info)
                except Exception:
                    logger.warning("failed to rollback routes from bridge %s to interface %s: %s" %
                                   (bridge_name, interface, traceback.format_exc()))
            raise
    elif move_route:
        logger.debug("Source device %s doesn't have an IP address set. No need to move routes." % interface)


def move_dev_route(src_dev, dest_dev, route_info=None, ignore_missing_source=False):
    """
    Move IP address and routes from one network device (src_dev) to another (dest_dev).

    Args:
    - src_dev: The source device from which the IP and routes will be moved.
    - dest_dev: The destination device to which the IP and routes will be moved.
    """
    if route_info is None:
        route_info = _get_dev_route_info(src_dev)
    if route_info is None:
        logger.debug("Source device %s doesn't have an IP address set. No need to move routes." % src_dev)
        return

    _delete_dev_route(src_dev, route_info, ignore_missing_source)
    _restore_dev_route(dest_dev, route_info)

    # Migrate DNS settings for systems using systemd-resolved (e.g. alinux4).
    # On these systems DNS servers are bound per-link; after bridging, the
    # physical interface no longer carries an IP so its DNS config becomes
    # unreachable.  We read DNS servers from the source device and apply them
    # to the destination bridge device.
    _migrate_resolved_dns(src_dev, dest_dev)


def _get_dev_route_info(src_dev):
    ipv4_out = shell.call('ip addr show dev %s | grep "inet "' % src_dev, exception=False)
    ipv6_out = shell.call('ip addr show dev %s | grep "inet6 " | grep -v " scope link"' % src_dev, exception=False)
    if not ipv4_out and not ipv6_out:
        return None

    routes = []
    r_out = shell.call("ip route show dev %s | grep via | sed 's/onlink//g'" % src_dev)
    for line in r_out.split('\n'):
        if line != "":
            routes.append(line)

    routes6 = []
    r_out = shell.call("ip -6 route show dev %s | grep via | sed 's/onlink//g'" % src_dev)
    for line in r_out.split('\n'):
        if line != "":
            routes6.append(line)

    direct_routes6 = []
    r_out = shell.call("ip -6 route show dev %s | grep -v via | grep -v ' proto kernel ' | grep -v '^fe80::' | sed 's/onlink//g'" % src_dev)
    for line in r_out.split('\n'):
        if line != "":
            direct_routes6.append(line)

    connected_routes6 = []
    r_out = shell.call("ip -6 route show dev %s proto kernel | grep -v '^fe80::' | sed 's/onlink//g'" % src_dev)
    for line in r_out.split('\n'):
        if line != "":
            connected_routes6.append(line)

    return {
        'ipv4_addresses': _parse_ip_addresses(ipv4_out),
        'ipv6_addresses': _parse_ip_addresses(ipv6_out),
        'routes': routes,
        'routes6': routes6,
        'direct_routes6': direct_routes6,
        'connected_routes6': connected_routes6,
    }


def _delete_dev_route(src_dev, route_info, ignore_missing_source=False):
    exception = not ignore_missing_source
    for r in route_info['routes']:
        shell.call('ip route del %s' % r, exception=exception)
    for r in route_info['routes6']:
        shell.call('ip -6 route del %s' % r, exception=exception)
    for r in route_info['direct_routes6']:
        shell.call('ip -6 route del %s' % _route_with_dev(r, src_dev), exception=exception)

    for ip in route_info['ipv4_addresses']:
        _move_ip_address(ip, src_dev, None, "inet")

    for ip in route_info['ipv6_addresses']:
        _move_ip_address(ip, src_dev, None, "inet6")
    for r in route_info['connected_routes6']:
        shell.call('ip -6 route del %s' % _route_with_dev(r, src_dev), exception=False)


def _restore_dev_route(dest_dev, route_info):
    if route_info is None:
        return

    for ip in route_info['ipv4_addresses']:
        _add_ip_address(ip, dest_dev, "inet")

    for ip in route_info['ipv6_addresses']:
        _add_ip_address(ip, dest_dev, "inet6")

    for r in route_info['routes']:
        shell.call('ip route add %s' % _route_with_dev(r, dest_dev))
    for r in route_info['direct_routes6']:
        shell.call('ip -6 route add %s' % _build_ipv6_route(r, dest_dev))
    for r in route_info['routes6']:
        shell.call('ip -6 route add %s' % _build_ipv6_route(r, dest_dev))


def _parse_ip_addresses(ip_addr_output):
    return [line.strip().split()[1] for line in ip_addr_output.split('\n') if line.strip()]


def _move_ip_address(ip, src_dev, dest_dev, family):
    shell.call('ip addr del %s dev %s' % (ip, src_dev), exception=False)
    if dest_dev is None:
        return
    _add_ip_address(ip, dest_dev, family)


def _add_ip_address(ip, dest_dev, family):
    r_out = shell.call('ip addr show dev %s | grep "%s %s"' % (dest_dev, family, ip), exception=False)
    if not r_out:
        shell.call('ip addr add %s dev %s' % (ip, dest_dev))


def _route_with_dev(route, dev):
    parts = route.split()
    if not parts:
        return route
    if 'dev' in parts:
        index = parts.index('dev')
        if index + 1 < len(parts):
            parts[index + 1] = dev
        return ' '.join(parts)
    if 'via' in parts:
        index = parts.index('via')
        if index + 1 < len(parts):
            return ' '.join(parts[:index + 2] + ['dev', dev] + parts[index + 2:])
    return ' '.join([parts[0], 'dev', dev] + parts[1:])


def _build_ipv6_route(route, dev):
    """Build an IPv6 route from the stable values supported by ip route add."""
    parts = route.split()
    if not parts:
        return route

    route_parts = [parts[0]]
    value_fields = {'via', 'proto', 'metric', 'hoplimit', 'pref'}
    index = 1
    while index < len(parts):
        field = parts[index]
        if field == 'dev':
            route_parts.extend(['dev', dev])
            index += 2
        elif field in value_fields and index + 1 < len(parts):
            route_parts.extend([field, parts[index + 1]])
            index += 2
        else:
            index += 2 if field == 'expires' else 1

    if 'dev' not in route_parts:
        route_parts[1:1] = ['dev', dev]
    return ' '.join(route_parts)


def _migrate_resolved_dns(src_dev, dest_dev):
    """Migrate systemd-resolved per-link DNS from *src_dev* to *dest_dev*."""
    # Only act when systemd-resolved is in use
    if not os.path.exists('/run/systemd/resolve/stub-resolv.conf'):
        return

    try:
        # resolvectl dns <dev> prints: "Link 2 (enp1s0): 223.5.5.5 8.8.8.8"
        # Force LC_ALL=C so the format is locale-independent
        out = shell.call('LC_ALL=C resolvectl dns %s' % src_dev, exception=False)
        if not out or ':' not in out:
            return

        dns_part = out.split(':', 1)[1].strip()
        if not dns_part:
            return

        dns_servers = dns_part.split()
        if not dns_servers:
            return

        # Check if dest already has DNS configured
        dest_out = shell.call('LC_ALL=C resolvectl dns %s' % dest_dev, exception=False)
        if dest_out and ':' in dest_out:
            dest_dns = dest_out.split(':', 1)[1].strip()
            if dest_dns:
                logger.debug("Destination device %s already has DNS [%s], skip migration" % (dest_dev, dest_dns))
                return

        # Apply DNS servers to the bridge device
        shell.call('LC_ALL=C resolvectl dns %s %s' % (dest_dev, ' '.join(dns_servers)))
        # Set the bridge as a default-route DNS link so it handles all domains
        shell.call('LC_ALL=C resolvectl domain %s "~."' % dest_dev)
        logger.debug("Migrated DNS servers [%s] from %s to %s" % (' '.join(dns_servers), src_dev, dest_dev))
    except Exception as e:
        logger.warning("Failed to migrate resolved DNS from %s to %s: %s" % (src_dev, dest_dev, str(e)))


def pretty_xml(xmlstr):
    # dom cannot handle namespace tag like <qemu:commandline>
    #x = xml.dom.minidom.parseString(xmlstr)
    #return x.toprettyxml()
    return xmlstr

def get_exception_stacktrace():
    return traceback.format_exc()

def wait_callback_success(callback, callback_data=None, timeout=60,
        interval=1, ignore_exception_in_callback = False):
    '''
    Wait for callback(callback_data) return none 'False' result, until the
    timeout. After each 'False' return, will sleep for an interval, before
    next calling. When callback result is not 'False', will directly return
    the result. When timeout, it will return False.

    If callback meets exception, it will defaultly directly return False,
    unless exception_result is set to True.
    '''
    count = time.time()
    timeout = timeout + count
    while count <= timeout:
        try:
            rsp = callback(callback_data)
            if rsp:
                return rsp
            time.sleep(interval)
        except Exception as e:
            if not ignore_exception_in_callback:
                logger.debug('Meet exception when call %s through wait_callback_success: %s' % (callback.__name__, get_exception_stacktrace()))
                raise e
            time.sleep(interval)
        finally:
            count = time.time()

    return False

def get_process_up_time_in_second(pid):
    output = shell.call('ps -p %s -o etime=' % pid)
    output = output.strip()
    if '-' in output:
        day, output = output.split('-')
        day = int(day)
    else:
        day = 0

    time_pair = output.split(':')
    if len(time_pair) == 3:
        hour = int(time_pair[0])
        minute = int(time_pair[1])
        second = int(time_pair[2])
    elif len(time_pair) == 2:
        hour = 0
        minute = int(time_pair[0])
        second = int(time_pair[1])
    else:
        hour = 0
        minute = 0
        second = int(time_pair[0])

    return day * 24 * 3600 + hour * 3600 + minute * 60 + second


def get_process_start_time(pid):
    if not os.path.exists('/proc/%s/stat' % pid):
        return

    with open('/proc/%s/stat' % pid, 'r') as f:
        stats = f.read().split()
    start_time = float(stats[21]) / os.sysconf('SC_CLK_TCK')

    with open('/proc/uptime', 'r') as f:
        uptime = float(f.read().split()[0])
    current_time = time.time()
    boot_time = current_time - uptime
    return boot_time + start_time


def get_cpu_num():
    out = shell.call("grep -c processor /proc/cpuinfo")
    return int(out)

def get_cpu_core_num():
    sockets = get_socket_num()
    if is_loongson_3c5000l_cpu():
        return LOONGSON_3C5000L_CORES_PER_SOCKET * sockets

    cpu_cores_per_socket = shell.call("lscpu | awk -F':' '/per socket/{print $NF}'")
    return int(cpu_cores_per_socket.strip()) * sockets

def get_cpu_model():
    vendor_id = shell.call("lscpu |awk -F':' '{IGNORECASE=1}/^ *Vendor ID/{print $2}'").strip()
    model_name = shell.call("lscpu |awk -F':' '{IGNORECASE=1}/^ *Model name/{print $2}'").strip()
    return vendor_id, model_name

def is_loongson_3c5000l_cpu(model_name=None):
    if model_name is None:
        _, model_name = get_cpu_model()
    return "3C5000L" in (model_name or "").upper()

def get_loongson_3c5000l_socket_num():
    cpu_num = get_cpu_num()
    return max(1, (cpu_num + LOONGSON_3C5000L_CORES_PER_SOCKET - 1) // LOONGSON_3C5000L_CORES_PER_SOCKET)

def get_socket_num():
    if is_loongson_3c5000l_cpu():
        return get_loongson_3c5000l_socket_num()

    num_dmidecode = int(shell.call("dmidecode -t processor | grep 'Socket Designation' | wc -l").strip())
    num_lscpu = int(shell.call("lscpu | awk '/Socket\(s\)/{print $2}'").strip())
    num_cpuinfo = int(shell.call("grep 'physical id' /proc/cpuinfo | sort -u | wc -l").strip())
    '''
    Seems not all platforms can get these values correctly, 
    depending on the system and the version of tools like util-linux and dmidecode.
    
    Return the value if two or three values are equal, else treated as 1 cpu.
    '''
    freq = {}
    for num in [num_dmidecode, num_lscpu, num_cpuinfo]:
        if num in freq:
            freq[num] += 1
            if freq[num] >= 2:
                return num
        else:
            freq[num] = 1
    return 1

@retry(times=3, sleep_time=3)
def get_cpu_speed():
    max_freq = '/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq'
    if os.path.exists(max_freq):
        out = open(max_freq).read()
        return int(float(out) / 1000)

    if platform.machine() == 'aarch64':
        cmd = shell.ShellCmd("dmidecode | grep 'Max Speed' | tail -n 1 | awk -F ' ' '{ print $1 $2 $3 }'")
    else:
        cmd = shell.ShellCmd("grep 'cpu MHz' /proc/cpuinfo | tail -n 1")
    out = cmd(False)
    try:
        (name, speed) = out.split(':')
        speed = speed.strip()
    except Exception:
        speed = "0"
    #logger.warn('%s is not existing, getting cpu speed from "cpu MHZ" of /proc/cpuinfo which may not be accurate' % max_freq)
    return int(float(speed))

def get_iscsi_initiator_name():
    content = read_file('/etc/iscsi/initiatorname.iscsi')
    if not content:
        return None
    for line in content.splitlines():
        if line.startswith('InitiatorName='):
            return line.split('=')[1].strip()

def full_path(path):
    if path.startswith('~'):
        return os.path.expanduser(path)
    else:
        return os.path.abspath(path)

def get_pid_by_process_param(param):
    cmd = shell.ShellCmd('''set -o pipefail; ps -aux | grep "[%s]%s" | sed 's/\s\s*/ /g' | cut -f 2 -d " "''' % (param[0], param[1:]))
    output = cmd(False)
    if cmd.return_code != 0:
        return None
    output = output.strip()
    return int(output)

def get_pid_by_process_name(name):
    cmd = shell.ShellCmd('ps -ae | grep -w %s' % name)
    output = cmd(False)
    if cmd.return_code != 0:
        return None
    return output.split()[0]

def get_pids_by_process_name(name):
    cmd = shell.ShellCmd("ps -ae | grep -w %s | awk '{ print $1 }'" % name)
    output = cmd(False)
    if cmd.return_code != 0:
        return None
    return output.split('\n')

def get_pids_by_process_fullname(name):
    return kill_process_by_fullname(name, 0)

def kill_process_by_fullname(name, sig):
    #type: (str, int) -> list[str]
    cmd = shell.ShellCmd("pkill -%d -e -f '%s'" % (sig, name))
    output = cmd(False)
    if cmd.return_code != 0:
        return []

    # format from 'bash killed (pid 32162)'
    pids = [line.split()[-1][0:-1] for line in output.splitlines()]
    logger.debug("killed -%d process details: %s" % (sig, output))
    return pids

def get_ipv4_addr_by_bond(bond):
    ip = ['%s/%d' % (x.address, x.prefixlen) for x in
          iproute.query_addresses(ifname=bond, ip_version=4)]
    if len(ip) == 0:
        master = read_file("/sys/class/net/%s/master/ifindex" % bond)
        if master:
            ip = ['%s/%d' % (x.address, x.prefixlen) for x in
                  iproute.query_addresses(index=int(master.strip()), ip_version=4)]
    return ip

def get_ipv4_addr_by_nic(nic):
    ip = ['%s/%d' % (x.address, x.prefixlen) for x in
          iproute.query_addresses(ifname=nic, ip_version=4)]
    return ip

def get_nic_state_by_name(nic):
    try:
        if nic :
            return read_nic_carrier("/sys/class/net/%s/carrier" % nic).strip() == "1"
        else:
            return False
    except IOError:
        return False

def get_bond_info_by_nic(nic):
    bonds = read_file("/sys/class/net/bonding_masters")
    if bonds:
        for bond in bonds.strip().split(" "):
            slaves = read_file("/sys/class/net/%s/bonding/slaves" % bond)
            if slaves:
                for slave in slaves.strip().split(" "):
                    if slave == nic:
                        return bond

def get_nic_name_by_mac(mac):
    names = get_nic_names_by_mac(mac)
    if len(names) > 1:
        raise LinuxError('more than one nic name matching to mac[%s], %s' % (mac, names))
    elif not names:
        return None
    else:
        return names[0]

def get_nic_names_by_mac(mac):
    eths = get_ethernet_info()
    names = []
    mac = mac.lower()
    for e in eths:
        if not e.mac or e.mac != mac:
            continue

        if e.interface:
            names.append(e.interface)
    return names

def get_nic_name_by_ip(ip):
    eths = get_ethernet_info()
    for e in eths:
        if e.ip and e.ip == ip:
            return e.interface
    return None

def get_ip_by_nic_name(nicname):
    eths = get_ethernet_info()
    for e in eths:
        if e.interface == nicname:
            return e.ip
    return None

def get_nic_name_from_alias(nicnames):
    for name in nicnames:
        if ":" not in name:
            return name

    raise LinuxError('cannot find original nic name from alias%s' % nicnames)


#     info = shell.call('ip link')
#     infos = info.split('\n')
#     lines = []
#     for i in infos:
#         i = i.strip().strip('\t').strip('\r').strip('\n')
#         if i == '':
#             continue
#         lines.append(i)
#
#     i = 0
#     nic_names = []
#     while(i < len(lines)):
#         l1 = lines[i]
#         dev_name = l1.split(':')[1].strip()
#         i += 1
#         l2 = lines[i]
#         tmac = l2.split()[1].strip()
#         i += 1
#         if tmac.lower() == mac.lower():
#             nic_names.append(dev_name)
#     return nic_names

def ip_string_to_int(ip):
    ips = ip.split('.')
    return int(ips[0]) << 24 | int(ips[1]) << 16 | int(ips[2]) << 8 | int(ips[3])

def int_to_ip_string(ip):
    return (
            str((ip & 0xff000000) >> 24) + '.' +
            str((ip & 0x00ff0000) >> 16) + '.' +
            str((ip & 0x0000ff00) >> 8) + '.' +
            str((ip & 0x000000ff))
            )

def vlan_eth_exists(ethname, vlan):
    vlan = int(vlan)
    if not is_network_device_existing(ethname):
        raise LinuxError('cannot find ethernet device %s' % ethname)
    vlan_dev_name = make_vlan_eth_name(ethname, vlan)
    return is_network_device_existing(vlan_dev_name)


def delete_vlan_eth(vlan_dev_name):
    if not is_network_device_existing(vlan_dev_name):
        return
    shell.call('ip link set dev %s down' % vlan_dev_name)
    iproute.delete_link_no_error(vlan_dev_name)

def make_vlan_eth_name(ethname, vlan):
    return '%s.%s' % (ethname, vlan)

def create_vlan_eth(ethname, vlan, ip=None, netmask=None):
    vlan = int(vlan)
    if not is_network_device_existing(ethname):
        raise LinuxError('cannot find ethernet device %s' % ethname)

    vlan_dev_name = make_vlan_eth_name(ethname, vlan)
    if not is_network_device_existing(vlan_dev_name):
        shell.call('ip link add link %s name %s type vlan id %s' % (ethname, vlan_dev_name, vlan))
        if ip:
            iproute.add_address(ip, netmask_to_cidr(netmask), 4, vlan_dev_name, broadcast=netmask_to_broadcast(ip, netmask))
    else:
        if ip is not None and ip.strip() != "" and get_device_ip(vlan_dev_name) != ip:
            # recreate device and configure ip
            delete_vlan_eth(vlan_dev_name)
            shell.call('ip link add link %s name %s.%s type vlan id %s' % (ethname, ethname, vlan, vlan))
            iproute.add_address(ip, netmask_to_cidr(netmask), 4, vlan_dev_name, broadcast=netmask_to_broadcast(ip, netmask))

    iproute.set_link_up(vlan_dev_name)
    return vlan_dev_name


def delete_vlan_bridge(bridge_name, vlan_interface):
    if not is_network_device_existing(bridge_name):
        logger.debug("can not find bridge %s" % bridge_name)
        return

    if is_network_ip_using(bridge_name):
        logger.debug("can not delete bridge %s, this interface ip was using" % bridge_name)
        return

    if is_vif_on_bridge(bridge_name, vlan_interface):
        delete_bridge(bridge_name)
        delete_vlan_eth(vlan_interface)

    else:
        logger.debug("bridge %s do not have interface %s. only delete bridge. " % (bridge_name, vlan_interface))
        delete_bridge(bridge_name)



def create_vlan_bridge(bridgename, ethname, vlan, ip=None, netmask=None):
    vlan = int(vlan)
    vlan_dev_name = create_vlan_eth(ethname, vlan, ip, netmask)
    move_route = True
    create_bridge(bridgename, vlan_dev_name, move_route)

def enable_process_coredump(pid):
    memsize = 4 * 1024 * 1024
    shell.run('prlimit --core=%d --pid %s' % (memsize, pid))

def set_vm_priority(pid, priorityConfig):
    for scope in ["--live", "--config"]:
        cmd = shell.ShellCmd("virsh schedinfo %s --set cpu_shares=%s %s" % (priorityConfig.vmUuid, priorityConfig.cpuShares, scope))
        cmd(is_exception=False)
        if cmd.return_code != 0:
            logger.warn("set vm %s %s cpu_shares failed" % (priorityConfig.vmUuid, scope[2:]))

    oom_score_adj_path = "/proc/%s/oom_score_adj" % pid
    if write_file(oom_score_adj_path, priorityConfig.oomScoreAdj) is None:
        logger.warn("set vm %s oomScoreAdj failed" % priorityConfig.vmUuid)


def get_vm_pid(uuid):
    pid = read_file(os.path.join(LIVE_LIBVIRT_XML_DIR, uuid + ".pid"))
    if pid:
        return pid.strip()

    return find_vm_pid_by_uuid(uuid)


def find_vm_pid_by_uuid(uuid):
    return shell.call("""ps x | awk '/qemu[-].*%s/{print $1; exit}'""" % uuid).strip()

def find_vm_process_by_uuid(uuid):
    return shell.call("""ps aux | egrep "qemu[-]kvm|qemu[-]system" | awk '/%s/'""" % uuid).strip()

def find_process_by_cmdline(cmdlines):
    pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]
    for pid in pids:
        try:
            with open(os.path.join('/proc', pid, 'cmdline'), 'rb') as fd:
                cmdline = fd.read().decode('utf-8', errors='replace')

            is_find = True
            for c in cmdlines:
                if c not in cmdline:
                    is_find = False
                    break

            if not is_find:
                continue

            return pid
        except IOError:
            continue

    return None

def find_all_process_by_cmdline(cmdlines):
    ret = []
    pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]
    for pid in pids:
        try:
            with open(os.path.join('/proc', pid, 'cmdline'), 'rb') as fd:
                cmdline = fd.read().decode('utf-8', errors='replace')

            is_find = True
            for c in cmdlines:
                if c not in cmdline:
                    is_find = False
                    break

            if not is_find:
                continue

            ret.append(pid)
        except IOError:
            continue

    return ret

def find_process_by_command(comm, cmdlines=None):
    pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]
    for pid in pids:
        try:
            comm_path = os.readlink(os.path.join('/proc', pid, 'exe')).split(";")[0]
            if comm_path.endswith("(deleted)") and not os.path.exists(comm_path):
                comm_path = comm_path[0:-9].strip()

            if comm_path != comm and os.path.basename(comm_path) != comm:
                continue

            if not cmdlines:
                return pid

            with open(os.path.join('/proc', pid, 'cmdline'), 'rb') as fd:
                cmdline = fd.read().replace(b'\x00', b' ').decode('utf-8', errors='replace').strip()
                if all(c in cmdline for c in cmdlines):
                    return pid
        except (IOError, OSError):
            continue
    return None


def find_process_list_by_command(comm, cmdlines=None):
    pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]
    match_pids = []
    for pid in pids:
        try:
            comm_path = os.readlink(os.path.join('/proc', pid, 'exe')).split(";")[0]
            if comm_path.endswith("(deleted)") and not os.path.exists(comm_path):
                comm_path = comm_path[0:-9].strip()

            if comm_path != comm and os.path.basename(comm_path) != comm:
                continue

            if not cmdlines:
                match_pids.append(pid)
                continue

            with open(os.path.join('/proc', pid, 'cmdline'), 'rb') as fd:
                cmdline = fd.read().replace(b'\x00', b' ').decode('utf-8', errors='replace').strip()
                if all(c in cmdline for c in cmdlines):
                    match_pids.append(pid)
                    continue
        except (IOError, OSError):
            continue
    return match_pids

def error_if_path_missing(path):
    if not os.path.exists(path):
        raise LinuxError('cannot find file or dir at path[%s]' % path)

def property_file_to_list(filepath):
    error_if_path_missing(filepath)
    with open(filepath, 'r') as fd:
        content = fd.read()

    ps = []
    for p in content.split('\n'):
        p = p.strip()
        # skip comments
        if p == '' or p.startswith('#'):
            continue

        kv = p.split('=', 1)
        if len(kv) != 2:
            err = '%s is not a valid property, property must be defined as "property_name=property_value"' % p
            raise LinuxError(err)
        ps.append((kv[0].strip(), kv[1].strip()))
    return ps

def get_command_by_pid(pid):
    with open(os.path.join('/proc', str(pid), 'cmdline'), 'rb') as fd:
        return fd.read().decode('utf-8', errors='replace')

def get_netmask_of_nic(nic_name):
    nic_addrs = iproute.query_addresses_by_ifname(nic_name)
    netmask = cidr_to_netmask(nic_addrs[0].prefixlen)

    netmask = netmask.strip()
    if netmask == '':
        raise LinuxError('cannot find netmask of %s, it may have no ip assigned' % nic_name)
    return netmask

def arping(nic_name, ip):
    shell.call('arping -q -U -c 3 -I %s %s' % (nic_name, ip))

def create_vip_if_not_exists(nic_mac, ip, netmask):
    if get_nic_name_by_ip(ip):
        return

    create_vip(nic_mac, ip, netmask)

def create_vip(nic_mac, ip, netmask):
    nic_names = get_nic_names_by_mac(nic_mac)
    if not nic_names:
        raise LinuxError('cannot find any nic matching to mac[%s]' % nic_mac)

    def find_next_device_id():
        base_name = None
        devids = []
        for n in nic_names:
            name_pair = n.split(':')
            assert len(name_pair) <= 2
            if len(name_pair) == 1:
                base_name = name_pair[0]
                continue
            devids.append(int(name_pair[1]))

        assert base_name
        if len(nic_names) == 1:
            return (base_name, 0)

        devids.sort()

        length = len(devids)
        target_dev_id = None
        for did in devids:
            devid = int(did)
            index = devids.index(did)

            if index == length-1:
                # last item
                target_dev_id = devid+1
                break
            else:
                next_id = devids[index+1]
                if devid+1 != int(next_id):
                    # found first consecutive number
                    target_dev_id = devid+1
                    break
        return (base_name, target_dev_id)

    (base_name, dev_id) = find_next_device_id()
    dev_name =  '%s:%s' % (base_name, dev_id)
    iproute.add_address(ip, netmask_to_cidr(netmask), 4, dev_name, broadcast=netmask_to_broadcast(ip, netmask))
    iproute.set_link_up(dev_name)
    #arping(dev_name, ip)

def delete_vip_by_ip_if_exists(vip):
    nic_name = get_nic_name_by_ip(vip)
    if nic_name:
        iproute.set_link_down(nic_name)

def delete_vip_by_ip(vip):
    nic_name = get_nic_name_by_ip(vip)
    if not nic_name:
        raise LinuxError('cannot find nic having ip[%s]' % vip)
    iproute.set_link_down(nic_name)

def listPath(path):
    if os.path.isabs(path):
        return [ os.path.join(path, p) for p in os.listdir(path) ]
    return [ os.path.realpath(os.path.join(path, p)) for p in os.listdir(path) ]

def listdir(d):
    try:
        return os.listdir(d)
    except:
        return []

def list_all_file(path):
    for fi in os.listdir(path):
        fi_d = os.path.join(path, fi)
        if os.path.isdir(fi_d):
            for f in list_all_file(fi_d):
                yield f
        else:
            yield fi_d


def walk(path, depth=-1):
    if depth == 0:
        return
    for fi in os.listdir(path):
        fi_d = os.path.join(path, fi)
        if os.path.isdir(fi_d):
            yield fi_d
            for f in walk(fi_d, depth-1):
                yield f
        else:
            yield fi_d


def find_file(file_name, current_path, parent_path_depth=2, sub_folder_first=False):
    ''' find_file will return a file path, when finding a file in given path.
        The default search parent path depth is 2. It means loader will only
        try to find the component in its parent folder and all sub folders in
        current path.

        If parent path depth is -1, the parent path will be up to '/' root
        folder.

        The default search sequence is current folder, +1 folder, +2 folder,
        ... , '/' folder, all sub folders.

        Set sub_folder_first=True to search sub folders earlier than parents
        folders.

        The first matched file will be returned. '''

    def __compare_file_name(path):
        if not os.path.exists(path):
            return
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        for f in os.listdir(path):
            if f == file_name:
                return os.path.join(path, f)

    def __search_sub_folders(path):
        if not os.path.exists(current_path):
            return
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        for pa, dirs, files in os.walk(path):
            f = __compare_file_name(pa)
            if f:
                return f

    def __only_search_current_folder(path):
        return __compare_file_name(path)

    def __search_parents_folders():
        if parent_path_depth == 1:
            return None

        dir_list = os.path.abspath(current_path).split('/')[:-1]
        for i in range(len(dir_list)):
            if parent_path_depth == i + 1:
                return None

            if i == 0:
                path = '/'.join(dir_list)
            elif i == len(dir_list):
                path = '/'
            else:
                path = '/'.join(dir_list[:-i])

            f = __compare_file_name(path)
            if f:
                return f

    f = __only_search_current_folder(current_path)
    if f:
        return f

    if sub_folder_first:
        f = __search_sub_folders(current_path)
        if not f:
            f = __search_parents_folders()
        return f
    else:
        f = __search_parents_folders()
        if not f:
            f = __search_sub_folders(current_path)
        return f

def get_free_port():
    s = socket.socket()
    s.bind(('', 0))
    port = s.getsockname()[1]
    s.close()
    return port

@lock.lock('port_lock')
def get_free_port_in_range(start_port, end_port):
    for port in range(start_port, end_port):
        if tcp_port_is_free(port):
            return port

    raise Exception("no free port found in range[%d, %d]" % (start_port, end_port))

def tcp_port_is_free(port):
    sock = None
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        network_ipv6.bind_dual_stack_probe_socket(sock, port)
        return True
    except socket.error:
        pass
    finally:
        if sock is not None:
            sock.close()

    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        network_ipv6.bind_ipv4_probe_socket(sock, port)
        return True
    except socket.error:
        return False
    finally:
        if sock is not None:
            sock.close()

def find_free_port_with_locking(start_port, end_port):
    keep_lock = False
    tcp_port_lock.acquire()
    try:
        for p in range(start_port, end_port + 1):
            if tcp_port_is_free(p):
                keep_lock = True
                return p, tcp_port_lock
        raise Exception("no free port found in range[%d, %d]" % (start_port, end_port))
    finally:
        if not keep_lock:
            tcp_port_lock.release()

def parse_port_range(port_range):
    start_port, end_port = map(int, port_range.split(':'))
    return start_port, end_port

def check_socket_available(host, port, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            sock = network_ipv6.create_tcp_socket_for_host(host)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
        except:
            pass
        time.sleep(1)
    return False

def is_port_available(port):
    with contextlib.closing(socket.socket(socket.AF_INET6, socket.SOCK_STREAM)) as s:
        try:
            network_ipv6.bind_dual_stack_probe_socket(s, port)
            return True
        except (socket.error, OSError):
            with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as ipv4_sock:
                try:
                    network_ipv6.bind_ipv4_probe_socket(ipv4_sock, port)
                    return True
                except (socket.error, OSError):
                    return False

def get_all_ethernet_device_names():
    return os.listdir('/sys/class/net/')

def is_systemd_enabled():
    try:
        shell.call('which systemctl')
    except:
        return False
    return True

class TimeoutObject(object):
    def __init__(self):
        self.objects = {}
        self._start()
        self.p_timer = None # type: thread.PeriodicTimer

    def put(self, name, val=None, timeout=30):
        self.objects[name] = (val, time.time() + timeout)

    def has(self, name):
        return name in list(self.objects.keys())

    def get(self, name):
        return self.objects.get(name)

    def remove(self, name):
        del self.objects[name]

    def print_objects(self):
        logger.warn(self.objects)

    def wait_until_object_timeout(self, name, timeout=60):
        def wait(_):
            return not self.has(name)

        self._restart_if_needed()
        if not wait_callback_success(wait, timeout=timeout):
            self.print_objects()
            raise Exception('after %s seconds, the object[%s] is still there, not timeout' % (timeout, name))

    def _restart_if_needed(self):
        if self.p_timer is None:
            self._start()
            return

        try:
            if not self.p_timer.is_alive():
                self._start()
                return
        except:
            logger.warn(traceback.format_exc())
            logger.warn('get period timer thread status failed, try to restart it')
            self._start()

    def _start(self):
        def clean_timeout_object():
            current_time = time.time()
            for name, obj in list(self.objects.items()):
                timeout = obj[1]
                if current_time >= timeout:
                    del self.objects[name]
            return True

        self.objects = {}
        self.p_timer = thread.timer(1, clean_timeout_object, stop_on_exception=False)
        self.p_timer.start()


def kill_process(pid, timeout=5, is_exception=True, is_graceful=True):
    def kill(sig):
        try:
            logger.debug("kill -%d process[pid %s]" % (sig, pid))
            os.kill(int(pid), sig)
        except OSError as e:
            if e.errno != errno.ESRCH:
                raise e

    @ignoreerror
    def get_cmdline():
        return read_file("/proc/%s/cmdline" % pid)

    def check(_):
        return not os.path.exists('/proc/%s' % pid)

    if check(None):
        return

    logger.debug("killing process[pid: %s, cmdline: %s]" % (pid, get_cmdline()))
    if is_graceful:
        kill(15)
        if wait_callback_success(check, None, timeout):
            return

    kill(9)
    if not wait_callback_success(check, None, timeout) and is_exception:
        raise Exception('cannot kill -9 process[pid:%s];the process still exists after %s seconds' % (pid, timeout))


def kill_all_child_process(ppid, timeout=5, sig=15):
    def check(_):
        return not os.path.exists('/proc/%s' % ppid)

    if check(None):
        return

    shell.run("pkill -%s -P %s" % (sig, ppid))
    if wait_callback_success(check, None, timeout):
        return

    shell.run("pkill -9 -P %s" % ppid)
    if not wait_callback_success(check, None, timeout):
        raise Exception('cannot kill -9 child process[ppid:%s];the process still exists after %s seconds' % (ppid, timeout))

def get_gateway_by_default_route():
    cmd = shell.ShellCmd("ip route | awk '/^default/{print $3; exit}'")
    cmd(False)
    if cmd.return_code != 0:
        return None

    out = cmd.stdout.strip()
    if not out:
        return None

    return out

def delete_lines_from_file(filename, is_line_to_delete):
    lines = []
    with open(filename, 'r') as fd:
        for l in fd.readlines():
            if not is_line_to_delete(l):
                lines.append(l)

    with open(filename, 'w') as fd:
        fd.write('\n'.join(lines))


class Interface(object):
    def __init__(self, args):
        self.status = args.get('status')
        self.name = args.get('name')
        self.ips = args.get('ips')

    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return str({'status':self.status,
                'name':self.name,
                'ips':self.ips})

IP_ADDR_INTERFACE_MARKER = 'mtu'
IP_ADDR_ADDRESS_FAMILIES = ('inet', 'inet6')
IP_ADDR_LIST_CMD = "ip a | grep -E 'mtu| inet | inet6 '"


def get_eth_ips():
    nics = shell.call(IP_ADDR_LIST_CMD)
    result = dict()
    interf = ''

    for i in nics.splitlines():
        fields = i.strip().split()
        if i.find(IP_ADDR_INTERFACE_MARKER) >= 0:
            interf = re.findall(r':\ .*:\ ', i)[0].split(': ')[1]
            status = True if re.findall(r'UP', i) else False
            result[interf] = Interface({'name':interf, 'status':status, 'ips':list()})
        elif fields and fields[0] in IP_ADDR_ADDRESS_FAMILIES:
            result[interf].ips.append(fields[1].split('/')[0])

    return result

def get_nics_by_cidr(cidr):
    eths = get_eth_ips()
    nics = []
    for e in eths.values():
        if e.status == False:
            continue
        for ip in e.ips:
            if ip and netaddr.IPAddress(ip) in netaddr.IPNetwork(cidr):
                nics.append({e.name:ip})

    return nics

def get_vxlan_details(vxlan_interface):
    cmd = shell.ShellCmd("ip -d link show dev {name}".format(name=vxlan_interface))
    cmd(is_exception=False)
    if cmd.return_code == 0:
        for line in cmd.stdout.split("\n"):
            if "vxlan id" in line:
                vtep_ip = line.split("local ")[1].split(" ")[0]
                dst_port = line.split("dstport ")[1].split(" ")[0]
                return vtep_ip, dst_port
    return None, None


def change_vxlan_interface(old_vni, new_vni):
    old_vxlan = "vxlan" + str(old_vni)
    vtep_ip, dst_port = get_vxlan_details(old_vxlan)
    if not vtep_ip or not dst_port:
        raise Exception("Failed to get details for VXLAN interface: {}".format(old_vxlan))
    new_vxlan = "vxlan" + str(new_vni)
    create_vxlan_interface(new_vni, vtep_ip, dst_port)
    cmd = shell.ShellCmd("ip link set %s address `cat /sys/class/net/%s/address`" % (new_vxlan, old_vxlan))
    cmd(is_exception=False)
    cmd = shell.ShellCmd("ip link set {name} down".format(name=old_vxlan))
    cmd(is_exception=False)
    cmd = shell.ShellCmd("ip link set {name} up".format(name=new_vxlan))
    cmd(is_exception=False)
    if cmd.return_code != 0:
        raise Exception("Failed to set new VXLAN interface up: {}".format(new_vxlan))

    logger.debug("Successfully changed VXLAN interface from {old} to {new}.".format(old=old_vxlan, new=new_vxlan))


def create_vxlan_interface(vni, vtepIp,dstport):
    vni = str(vni)
    cmd = shell.ShellCmd("ip -d -o link show dev {name} | grep -w {ip} ".format(**{"name": "vxlan" + vni, "ip": vtepIp}))
    cmd(is_exception=False)
    if cmd.return_code != 0:
        cmd = shell.ShellCmd("ip link del {name}".format(**{"name": "vxlan" + vni}))
        cmd(is_exception=False)

        cmd = shell.ShellCmd("ip link add {name} type vxlan id {id} dstport {dstport} local {ip} learning noproxy nol2miss nol3miss".format(
            **{"name": "vxlan" + vni, "id": vni, "dstport":dstport,"ip": vtepIp}))

        cmd(is_exception=False)

    cmd = shell.ShellCmd("ip link set %s up" % ("vxlan" + vni))
    cmd(is_exception=False)
    return cmd.return_code == 0

def create_vxlan_bridge(interf, bridgeName, ips):
    if not is_bridge(bridgeName):
        create_bridge(bridgeName, interf, False)
    elif is_vif_on_bridge(bridgeName, interf) is None:
        ip_link_set_net_device_master(interf, bridgeName)

    # Fix ZSTAC-54704. It is expected that the bridge to be reset when the host reconnects. However, the above code
    # does not necessarily execute create_bridge(), and additional testing is required if it must be executed.
    shell.call("brctl stp %s off" % bridgeName)
    shell.call("brctl setfd %s 0" % bridgeName)
    if ips is not None:
        populate_vxlan_fdbs([interf], ips)


def delete_vxlan_bridge(bridge_name, vxlan_interface):
    if not is_network_device_existing(bridge_name):
        logger.debug("can not find bridge %s" % bridge_name)
        return

    if is_network_ip_using(bridge_name):
        logger.debug("can not delete bridge %s, this interface ip was using" % bridge_name)
        return

    if is_vif_on_bridge(bridge_name, vxlan_interface):
        delete_bridge(bridge_name)
        cmd = shell.ShellCmd("ip link del %s" % vxlan_interface)
        cmd(is_exception=False)
    else:
        logger.debug("bridge %s do not have interface %s. only delete bridge. " % (bridge_name, vxlan_interface))
        delete_bridge(bridge_name)


def populate_vxlan_fdbs(interf, ips):
    try:
        iproute.batch_populate_vxlan_fdbs(interf, "00:00:00:00:00:00", ips)
    except Exception as e:
        logger.debug(e)
        return False

    return True

def delete_vxlan_fdbs(interf, ips):
    try:
        iproute.batch_delete_vxlan_fdbs(interf, "00:00:00:00:00:00", ips)
    except Exception as e:
        logger.debug(e)
        return False

    return True

def bridge_fdb_has_self_rule(mac, dev):
    return shell.run("bridge fdb show dev %s | grep -m 1 '%s dev %s self permanent'" % (dev, mac, dev)) == 0

def get_interfs_from_uuids(uuids):
    strUuids = "\|".join(uuids)

    cmd = shell.ShellCmd("ip link | grep '%s' -B2 | awk '/vxlan/{ print $2}' | tr ':' ' '" % strUuids)
    o = cmd(is_exception=False)

    if o == "":
        return []
    else:
        return o.split("\n")[:-1] # remove last ""

def timeout_isdir(path):
    o = shell.ShellCmd("timeout 10 ls -d -l %s" % path)
    o(False)
    if o.return_code == 124:
        raise Exception('cannot access the mount point[%s], timeout after 10s' % path)
    if o.return_code != 0 or o.stdout[0] != 'd' or not path:
        return False
    else:
        return True

def set_device_uuid_alias(interf, l2NetworkUuid):
    cmd = shell.ShellCmd("ip link set dev %s alias \"uuid: %s\"" % (interf, l2NetworkUuid))
    cmd(is_exception=False)

def is_zstack_vm(vmUuid):
    cmd = shell.ShellCmd("virsh metadata %s --uri http://zstack.org | grep zstack" % vmUuid)
    cmd(is_exception=False)
    return cmd.return_code == 0

class ShowLibvirtErrorOnException(object):
    def __init__(self, vmUuid):
        self.vmUuid = vmUuid

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            try:
                logger.info(shell.call('virsh domblkerror %s' % self.vmUuid))
                logger.info(shell.call('virsh domjobinfo %s' % self.vmUuid))
            except:
                pass


class TempAccessible(object):
    def __init__(self, fpath):
        self.fpath = fpath
        self.fmode = None

    def __enter__(self):
        st = os.stat(self.fpath)
        if st.st_mode & 0o600 == 0o600:
            return

        self.fmode = st.st_mode
        os.chmod(self.fpath, st.st_mode | 0o600)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fmode is not None:
            os.chmod(self.fpath, self.fmode)


def get_libvirt_package_version():
    return shell.call("rpm -q libvirt --qf ' %{VERSION}-%{RELEASE}'")


def get_libvirt_version():
    return shell.call("libvirtd --version").split()[-1]


def get_libvirt_rpm_info():
    cmd_get_version = shell.ShellCmd("rpm -q --qf '%{VERSION}' libvirt")
    cmd_get_version(False)
    cmd_get_release = shell.ShellCmd("rpm -q --qf '%{RELEASE}' libvirt")
    cmd_get_release(False)
    if cmd_get_version.return_code != 0 or cmd_get_release.return_code != 0:
        return '', ''
    libvirt_release = cmd_get_release.stdout.strip().split('.')[0]
    libvirt_version = cmd_get_version.stdout.strip()
    return libvirt_version, libvirt_release


def get_unmanaged_vms(include_not_zstack_but_in_virsh = False):
    libvirt_uuid_pattern = "'[0-9a-z]{8}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12}'"
    cmd = shell.ShellCmd("pgrep -a 'qemu-kvm|qemu-system' | grep -E -o '\-uuid %s' | awk '{print $2}'" % libvirt_uuid_pattern)
    cmd(is_exception=False)
    vms_by_ps = cmd.stdout.strip().split() # type: list

    cmd = shell.ShellCmd("virsh list --uuid")
    cmd(is_exception=False)
    vms_by_virsh = cmd.stdout.strip().split()  # type: list

    unmanaged_vms = []
    for vm in vms_by_ps:
        if vm not in vms_by_virsh:
            unmanaged_vms.append(vm)

    if not include_not_zstack_but_in_virsh:
        return unmanaged_vms

    for vm in vms_by_virsh:
        if not is_zstack_vm(vm):
            unmanaged_vms.append(vm)
    return unmanaged_vms


def linux_lsof(abs_path, process="qemu-kvm", find_rpath=True):
    """

    :param abs_path: target file to run lsof
    :param process: process name to find, it can't find correctly in CentOS 7.4, so give process name is necessary
    :param find_rpath: use realpath to find deeper, it should be true in most cases
    :return: stdout of lsof
    """

    r = ""
    if find_rpath:
        r_path = os.path.realpath(abs_path)
        if r_path != abs_path:
            abs_path += "|%s" % r_path

    o = shell.call("lsof -b -c %s | grep -wE '%s'" % (process, abs_path), False).strip().splitlines()
    if len(o) != 0:
        for line in o:
            if line not in r:
                r = r.strip() + "\n" + line

    return r.strip()

def lsof(abs_path):
    o = shell.call("lsof -nP %s" % abs_path, exception=False)
    return o.strip()


class QemuStruct(object):
    def __init__(self, pid):
        self.pid = pid
        args = shell.call("ps -o args --width 99999 --pid %s" % pid, exception=False)
        self.name = args.split(' -uuid ')[-1].split(' ')[0].replace("-", "")
        self.state = shell.call("virsh domstate %s" % self.name, exception=False).strip()


def find_qemu_for_volume_in_use(volume_path):
    # type: (str) -> list[QemuStruct]
    real_path = os.path.realpath(volume_path)
    pids = [x.strip() for x in shell.call("lsof -b -c qemu-kvm -c qemu-system| grep -w %s | awk '{print $2}'" % real_path, exception=False).splitlines()]
    return [QemuStruct(pid) for pid in pids]


def touch_file(fpath):
    with open(fpath, 'a'):
        os.utime(fpath, None)

def read_file(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as fd:
            return fd.read()
    except IOError as e:
        stack_info = stack()
        err_str = """{}\ncaused by reading file {}\n""".format(e, path)
        cur_err_info = stack_info[0]
        err_str += "\t{}, line {}, {}\n".format(cur_err_info[1], cur_err_info[2], cur_err_info[3])
        for s in stack_info[1:4]:
            err_str += """\t{}, line {},  {}:\n{}""".format(s[1], s[2], s[3], s[4][0])
        logger.error(err_str)
        return None

def read_file_strip(path):
    context = read_file(path)
    return context.strip() if context else context

def read_nic_carrier(path):
    if not os.path.exists(path):
        raise IOError("file {} not found.".format(path))
    try:
        with open(path, 'r') as fd:
            return fd.read()
    except IOError as e:
        raise e


def read_file_lines(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r') as fd:
            return fd.readlines()
    except IOError as e:
        logger.error(e)
        return []


def filter_file_lines_by_regex(path, regex):
    if not os.path.exists(path):
        return None
    try:
        lines = []
        with open(path, 'r') as f:
            for line in f:
                if re.search(regex, line):
                    lines.append(line)
            return lines
    except IOError as e:
        logger.error(e)
        return None


def filter_lines_by_str_list(lines, filter_str_list):
    if len(lines) == 0:
        return None
    try:
        filter_lines = []
        for line in lines:
            if any(filter_str in line for filter_str in filter_str_list):
                filter_lines.append(line)
        return filter_lines
    except IOError as e:
        logger.error(e)
        return None

def write_file(path, content, create_if_not_exist=False):
    if not os.path.exists(path) and not create_if_not_exist:
        logger.warn("write file failed because the path %s was not found", path)
        return None

    with open(path, "w") as f:
        f.write(str(content))
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    return path


def write_file_lines(path, contents, create_if_not_exist=False):
    if not os.path.exists(path) and not create_if_not_exist:
        logger.warn("write file failed because the path %s was not found", path)
        return None

    with open(path, "w") as f:
        f.writelines(contents)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    return path


def link(source, link_name):
    if os.path.exists(link_name) and os.stat(link_name).st_ino == os.stat(source).st_ino:
        return

    if not os.path.exists(os.path.dirname(link_name)):
        os.makedirs(os.path.dirname(link_name), 0o755)

    os.link(source, link_name)
    logger.debug("link %s to %s" % (source, link_name))

def tail_1(path, split=b"\n"):
    if not os.path.exists(path):
        return None
    if os.path.getsize(path) <= 2:
        return read_file(path)

    with open(path, 'rb') as f:
        f.seek(-2, os.SEEK_END)
        while f.tell() > 0 and f.read(1) != split:
            f.seek(-2, os.SEEK_CUR)
        return f.readline().decode('utf-8', errors='replace')


# check if file 'fpath' contains .conf style configurations
def file_has_config(fpath):
    blank = re.compile(r'^\s*$')
    comment = re.compile(r'^\s*#')

    try:
        with open(fpath) as f:
            while True:
                line = f.readline()
                if not line:  # EOF
                    return False
                if comment.search(line) or blank.search(line):
                    continue

                return True

        return False
    except:
        return None

def get_libvirtd_pid():
    if not os.path.exists('/var/run/libvirtd.pid'):
        return None

    with open('/var/run/libvirtd.pid') as f:
        return int(f.read())

def fake_dead(name):
    fakedead_file = '/tmp/fakedead-%s' % name
    if not os.path.exists(fakedead_file):
        return False
    ctx = open(fakedead_file).read().strip()
    if ctx == 'fakedead':
        return True
    return False

def recover_fake_dead(name):
    fakedead_file = '/tmp/fakedead-%s' % name
    if os.path.exists(fakedead_file):
        os.remove(fakedead_file)

def get_agent_pid_by_name(name):
    cmd = shell.ShellCmd('ps -auxww | grep \'%s\' | grep -E \'start|restart\' | grep -v grep | awk \'{print $2}\'' % name)
    output = cmd(False)
    print(output)
    if cmd.return_code != 0:
        return None
    output = output.strip(" \t\r")
    return output

libc = ctypes.CDLL("libc.so.6")

def sync_file(fpath):
    if not os.path.isfile(fpath):
        return

    fd = os.open(fpath, os.O_RDONLY|os.O_NONBLOCK)
    try:
        libc.syncfs(fd)
    except:
        pass
    finally:
        os.close(fd)


def set_fail_if_no_path():
    s = shell.ShellCmd("dmsetup table --target multipath | grep 'queue_if_no_path' | awk '{print $1}' | tr -d ':'")
    s(is_exception=False, logcmd=False)
    o = s.stdout.strip()

    if len(o) == 0:
        return

    logger.debug("find mpath config with queue_if_no_path: %s" % o.splitlines())
    queued_mpaths = o.splitlines()
    for mpath in queued_mpaths:
        mpath = mpath.strip()
        s = shell.ShellCmd('pgrep -af "dmsetup message %s 0"' % mpath)
        s(is_exception=False, logcmd=True)
        if s.return_code == 0:
            logger.debug("there is other process messaging %s [%s], skip" % (mpath, s.stdout))
            continue

        s = shell.ShellCmd('dmsetup message %s 0 "fail_if_no_path"' % mpath)
        s(is_exception=False, logcmd=True)


def get_physical_disk(disk=None, logCommand=True) -> list[str]:
    def remove_digits(str_list):
        pattern = '[0-9]'
        str_list = [re.sub(pattern, '', i) for i in str_list]
        return str_list

    if disk is None:
        disk = shell.call("mount | grep 'on / ' | grep -o '/dev/.* on' | cut -d ' ' -f1", False).strip()
    cmd = shell.ShellCmd("dmsetup table %s" % disk)
    cmd(is_exception=False, logcmd=logCommand)
    if cmd.return_code != 0:
        return remove_digits([disk])
    dm_name = os.path.basename(os.path.realpath(disk))
    slaves = listdir("/sys/block/%s/slaves/" % dm_name)

    return remove_digits(["/dev/%s" % slave for slave in slaves])

def check_nping_result(port, result):
    # Starting Nping 0.6.40 ( http://nmap.org/nping ) at 2019-11-28 11:14 CST
    # SENT (0.0180s) TCP x.x.x.x:33243 > x.x.x.x:22 S ttl=64 id=3565 iplen=40  seq=1425405791 win=1480
    # RCVD (0.0189s) TCP x.x.x.x:22 > x.x.x.x:33243 SA ttl=64 id=0 iplen=44  seq=4279460929 win=29200 <mss 1460>
    #
    # Max rtt: 0.614ms | Min rtt: 0.614ms | Avg rtt: 0.614ms
    # Raw packets sent: 1 (40B) | Rcvd: 1 (44B) | Lost: 0 (0.00%)
    # Nping done: 1 IP address pinged in 1.04 seconds
    port_state = {}
    r = result.strip('\t\n\r')
    if "Lost: 0 (0.00%)" in r:
        port_state[port] = "open"
    else:
        port_state[port] = "close"
    return port_state


def write_uuids(type, str):
    if str is None or len(str) == 0:
        return
    uuids = read_file('/etc/zstack-uuids')
    if uuids is None:
        write_file('/etc/zstack-uuids', str, True)
        return
    if "%s=" % type in uuids:
        uuids = re.sub('%s=.*' % type, str, uuids)
    else:
        uuids += "\n%s" % str
    write_file('/etc/zstack-uuids', uuids.strip())


def get_max_vm_ipa_size():
    try:
        with open(KVM_DEVICE, 'r+b') as kvm_fd:
            ipa_max = fcntl.ioctl(kvm_fd, KVM_CHECK_EXTENSION, KVM_CAP_ARM_VM_IPA_SIZE)
            ipa_max = ipa_max if (ipa_max > 0) else DEFAULT_VM_IPA_SIZE
            return pow(2, ipa_max)
    except Exception as e:
        logger.warn("failed to get max vm ipa size, because %s", str(e))
        return pow(2, DEFAULT_VM_IPA_SIZE)


def hdev_get_max_transfer_via_ioctl(blk_path):
    cmd = shell.ShellCmd('blockdev --getmaxsect %s' % blk_path)
    ret = cmd(False)
    return int(ret.strip(' \t\r')) << 9 if cmd.return_code == 0 else 0


def hdev_get_max_transfer_via_segments(blk_path):
    segments_path = '/sys/block/%s/queue/max_segments' % os.path.basename(
        os.path.realpath(blk_path))
    if not os.path.exists(segments_path):
        return 0
    with open(segments_path, 'r') as f:
        max_segments = int(f.read())
    return max_segments * resource.getpagesize()


class RetryException(Exception):
    pass


@retry(3, 3)
def check_port(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # set timeout to avoid socket hang on
    s.settimeout(1)
    try:
        s.connect((ip, port))
        return True, None
    except socket.error as ex:
        raise RetryException("Failed connect to address[%s:%s], because %s" % (ip, port, ex))
    finally:
        s.close()


def get_fs_type(path):
    if os.path.isabs(path) is False:
        raise Exception("Make sure you path name with absolute path")
    return shell.call("""stat -f -c '%T' {}""".format(path)).strip()


def check_nbd():
    cmd = shell.ShellCmd("modinfo nbd")
    cmd(is_exception=False)
    if cmd.return_code != 0:
        raise Exception('nbd kernel module not found. try load nbd by `modprobe nbd`.')

def get_file_xxhash(path, blocksize=1048576):
    hasher = xxhash.xxh64()
    with open(path, 'r') as fd:
        buf = fd.read(blocksize)
        while len(buf) > 0:
            hasher.update(buf)
            buf = fd.read(blocksize)
    return hasher.hexdigest()

def compare_segmented_xxhash(src_path, dst_path, total_size, raise_exception=False, blocksize=1048576):
    ## size <= 10G, compute xxhash directly
    if total_size <= 10*1024**3:
        src_hash = get_file_xxhash(src_path, blocksize=blocksize)
        dst_hash = get_file_xxhash(dst_path, blocksize=blocksize)
        if src_hash != dst_hash:
            if raise_exception:
                raise Exception("check hash value not match between %s with hash[%s] and %s with hash[%s]" % (src_path, src_hash, dst_path, dst_hash))
            else:
                return False
        return True

    seg_size = 2*1024**3 ## 2G
    seg_offset = [total_size//5*x for x in range(0, 5)]
    def _get_seg_xxhash(fd, offset):
        hasher = xxhash.xxh64()
        fd.seek(offset)
        buf = fd.read(blocksize)
        while len(buf) > 0 and fd.tell() <= offset+seg_size:
            hasher.update(buf)
            buf = fd.read(blocksize)
        return hasher.hexdigest()

    with open(src_path, 'rb') as srcFile:
        with open(dst_path, 'rb') as dstFile:
            for offset in seg_offset:
                src_hash = _get_seg_xxhash(srcFile, offset)
                dst_hash = _get_seg_xxhash(dstFile, offset)
                if src_hash != dst_hash:
                    if raise_exception:
                        raise Exception("check hash value not match between %s with hash[%s] and %s with hash[%s] at offset %s" % (src_path, src_hash, dst_path, dst_hash, offset))
                    else:
                        return False
    return True

def check_unixsock_connection(socket_path, timeout=10):
    # NOTE: -z option may not be supported in some lower versions of Ncat, such as 6.40
    return shell.run("nc -z -U %s -w %s" % (socket_path, timeout))

def is_virtual_machine():
    virtual_machine_names = ["KVM Virtual Machine", "KVM", "vmware"]
    product_name = shell.call("dmidecode -s system-product-name").strip()
    return any(name.lower() in product_name.lower() for name in virtual_machine_names)

def is_support_bmc():
    cmd = shell.ShellCmd("ipmitool mc info")
    cmd(is_exception=False)
    if cmd.return_code != 0:
        return False
    return True

class VmUsbManager(object):
    def __init__(self):
        self.usb_slots = {
            0: 1,
            1: 6,
            2: 4
        }
        self.usb_version_map = {
            1: {0, 2},
            2: {1, 2},
            3: {2}
        }

    def request_slot(self, usb_type):
        if usb_type not in list(self.usb_version_map.keys()):
            raise Exception("Invalid USB type: %s" % usb_type)

        bus_set = self.usb_version_map.get(usb_type)
        for current_bus in bus_set:
            if self.usb_slots[current_bus] > 0:
                self.usb_slots[current_bus] -= 1
                return current_bus

        self.print_status()
        raise Exception("No enough USB slots available")

    def print_status(self):
        logger.info("Current USB slot status:")
        for usb_type, count in self.usb_slots.items():
            logger.info("bus:%s: %d" % (usb_type, count))


def is_rpm_installed(rpm_name):
    cmd = shell.ShellCmd('rpm -q %s' % rpm_name)
    cmd(False)
    if ('not installed' in cmd.stdout or 'command not found' in cmd.stdout or
        cmd.return_code != 0):
        return False
    return True


def get_rpm_version(rpm_name):
    return shell.call(
        'rpm -q --queryformat "%%{VERSION}-%%{RELEASE}" %s' % rpm_name)

class timespec(ctypes.Structure):
    _fields_ = [
        ('tv_sec', ctypes.c_long),
        ('tv_nsec', ctypes.c_long)
    ]

CLOCK_MONOTONIC = 1
librt = None
try:
    libname = ctypes.util.find_library('rt')
    if not libname:
        raise OSError("unable to find librt library")
    librt = ctypes.CDLL(libname, use_errno=True)
except Exception as e:
    logger.debug("load librt library err: %s" % str(e))

def monotime():
    if sys.version_info[:2] >= (3, 3):
        return time.monotonic()

    if librt is None:
        raise Exception("librt library is not found")

    t = timespec()
    if librt.clock_gettime(CLOCK_MONOTONIC, ctypes.byref(t)) != 0:
        errno = ctypes.get_errno()
        raise OSError(errno, os.strerror(errno))
    return t.tv_sec + t.tv_nsec / 1e9

def catch_bad_alloc_exception(return_code, error_detail):
    if return_code == 134 and 'std::bad_alloc' in error_detail:
        logger.warn('insufficient allocatable physical memory, error[%s]' % error_detail)
        return True
    
    return False

def get_free_memory():
    """ example
# cat /proc/meminfo
MemTotal:       16247260 kB
MemFree:         7344348 kB
MemAvailable:   14068964 kB
Buffers:            2108 kB
Cached:          6403684 kB
SwapCached:            0 kB
Active:          4667796 kB
Inactive:        2498796 kB
Active(anon):     713080 kB
Inactive(anon):    49308 kB
Active(file):    3954716 kB
Inactive(file):  2449488 kB
Unevictable:           0 kB
Mlocked:               0 kB
SwapTotal:       8257532 kB
SwapFree:        8257532 kB
Dirty:                28 kB
Writeback:             0 kB
AnonPages:        760384 kB
Mapped:            93788 kB
Shmem:              1588 kB
Slab:            1033048 kB
SReclaimable:     658676 kB
SUnreclaim:       374372 kB
KernelStack:        7568 kB
PageTables:        16160 kB
NFS_Unstable:          0 kB
Bounce:                0 kB
WritebackTmp:          0 kB
CommitLimit:    16381160 kB
Committed_AS:    1915944 kB
VmallocTotal:   34359738367 kB
VmallocUsed:      201560 kB
VmallocChunk:   34359375868 kB
Percpu:            27648 kB
HardwareCorrupted:     0 kB
AnonHugePages:    366592 kB
CmaTotal:              0 kB
CmaFree:               0 kB
HugePages_Total:       0
HugePages_Free:        0
HugePages_Rsvd:        0
HugePages_Surp:        0
Hugepagesize:       2048 kB
DirectMap4k:      139104 kB
DirectMap2M:     5103616 kB
DirectMap1G:    13631488 kB
    """
    try:
        mem_available = None
        memfree = buffers = cached = 0

        with open('/proc/meminfo') as f:
            for line in f:
                if line.startswith('MemAvailable:'):
                    mem_available = int(line.split()[1]) * 1024  # kB -> bytes
                elif line.startswith('MemFree:'):
                    memfree = int(line.split()[1]) * 1024
                elif line.startswith('Buffers:'):
                    buffers = int(line.split()[1]) * 1024
                elif line.startswith('Cached:'):
                    cached = int(line.split()[1]) * 1024

        # if MemAvailable is not existed, return MemFree + Buffers + Cached
        if mem_available is not None:
            return mem_available
        return memfree + buffers + cached

    except Exception as e:
        logger.warn("failed to parse /proc/meminfo: %s" % e)
        return 0

class _CrashSafeFileContent:
    def __init__(self, text):
        self.text = text

class CrashSafeFileEditor(object):
    def __init__(self, dest):
        self.dest = dest

    def __enter__(self):
        if not os.path.exists(self.dest):
            raise Exception("write file failed because file %s not exist" % self.dest)

        self.old_content = read_file(self.dest)
        self.buffer = _CrashSafeFileContent(self.old_content)
        return self.buffer

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            logger.debug("exception found when edit file %s, %s" % (self.dest, str(exc)))
            traceback.print_tb(tb)
            return

        new_content = self.buffer.text
        if new_content == self.old_content:
            logger.debug("%s file not changed, skip overwrite" % self.dest)
            return

        st = os.stat(self.dest)
        mode = stat.S_IMODE(st.st_mode)
        uid = st.st_uid
        gid = st.st_gid
        dirpath = os.path.dirname(self.dest) or "."
        tmp_path = create_temp_file(dir=dirpath)
        renamed = False
        try:
            os.chmod(tmp_path, mode)
            if uid != -1 and gid != -1:
                os.chown(tmp_path, uid, gid)

            write_file(tmp_path, str(new_content))

            os.rename(tmp_path, self.dest)
            renamed = True
            dir_fd = os.open(dirpath, os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            except OSError:
                pass
            finally:
                os.close(dir_fd)

        finally:
            if not renamed:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

BLKSSZGET = 0x1268  # get dev sector size
def get_dev_sector_size(dev_path):
    with open(dev_path, 'rb') as f:
        fd = f.fileno()
        buf = fcntl.ioctl(fd, BLKSSZGET, "    ")
        sector_size = struct.unpack('I', buf)[0]
        return sector_size


class FileSystemInfo(object):
    def __init__(self, block_device):
        # type: (str) -> None
        self.block_device = block_device
        self._info = None # type: dict[str, str] | None

    def reload(self):
        # type: () -> None
        self._info = None

    def _load(self):
        # type: () -> dict[str, str]
        if not self.block_device:
            raise Exception("Block device is not specified for FileSystemInfo")
        info = _get_filesystem_object(self.block_device)
        if not info:
            raise Exception("No filesystem found on block device: %s" % self.block_device)
        return info

    def __getitem__(self, name):
        # type: (str) -> str
        if self._info is None:
            self._info = self._load()
        return self._info.get(name, "")


class MountPointInfo(object):
    def __init__(self, filesystem_uuid, mount_path):
        # type: (str, str) -> None
        self.filesystem_uuid = filesystem_uuid
        self.mount_path = mount_path
        self._info = None # type: dict[str, str] | None

    def reload(self):
        # type: () -> None
        self._info = None

    def _load(self):
        # type: () -> dict[str, str]
        if not self.filesystem_uuid or not self.mount_path:
            raise Exception("Block device or mount path is not specified for MountPointInfo")
        if not is_mounted(path=self.mount_path):
            raise Exception("No mount point found for device %s on mount path: %s" % (self.filesystem_uuid, self.mount_path))
        stat = os.statvfs(self.mount_path)
        size = stat.f_frsize * stat.f_blocks
        return {
            "target": self.mount_path,
            "size": size,
            "avail": stat.f_frsize * stat.f_bavail,
            "used": size - stat.f_frsize * stat.f_bfree,
        }

    def __getitem__(self, name):
        # type: (str) -> str
        if self._info is None:
            self._info = self._load()
        return self._info.get(name, "")


def wipe_block_device_superblock(device_path, force=False):
    if not os.path.exists(device_path):
        raise Exception("Device path %s does not exist" % device_path)
    if not force:
        cmd = shell.ShellCmd("wipefs --noheadings --no-act --output TYPE %s" % shellquote(device_path))
        cmd(is_exception=True)
        if cmd.stdout.strip():
            raise Exception("Device %s has existing filesystem signatures, refuse to wipe without force" % device_path)
    shell.ShellCmd("wipefs --all --force %s" % shellquote(device_path))(is_exception=True)


def _get_filesystem_object(device_path):
    cmd = shell.ShellCmd("wipefs --json --no-act --output uuid,usage %s" % shellquote(device_path))
    cmd(is_exception=True)
    filesystems = json.loads(cmd.stdout.strip()).get("signatures", []) if cmd.stdout.strip() else []
    if not filesystems:
        return None
    obj = filesystems.pop()
    return obj if obj.get("usage") == "filesystem" else None


def create_xfs_filesystem(device_path, force=False):
    args = ["-t", "xfs"]
    if force:
        args.append("-f")
    args.append(device_path)
    shell.ShellCmd("mkfs %s" % ' '.join(shellquote(arg) for arg in args))(is_exception=True)
    return device_path


def extend_xfs_filesystem(device_path):
    cmd = shell.ShellCmd("xfs_growfs %s" % shellquote(device_path))
    cmd()
    if cmd.return_code != 0:
        raise Exception("Failed to extend filesystem on device %s: %s" % (device_path, cmd.stderr))


def check_filesystem(directory, tmp_file=None, timeout=5):
    tmp_file_path = os.path.join(directory, tmp_file or ".tmp")
    cmd = shell.ShellCmd("timeout %s touch %s" % (int(timeout), shellquote(tmp_file_path)))
    cmd(is_exception=False)
    return cmd.return_code == 0


def is_block_device_mounted(device_path):
    cmd = shell.ShellCmd("lsblk -nr -o MOUNTPOINT %s" % shellquote(device_path))
    cmd(is_exception=True)
    return bool(cmd.stdout.strip())
