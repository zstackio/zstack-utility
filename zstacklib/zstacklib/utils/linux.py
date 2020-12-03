'''

@author: frank
'''
import abc
import contextlib
import os
import os.path
import socket
import subprocess
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

from zstacklib.utils import thread
from zstacklib.utils import qemu_img
from zstacklib.utils import lock
from zstacklib.utils import shell
from zstacklib.utils import log


logger = log.get_logger(__name__)

RPM_BASED_OS = ['redhat', 'centos', 'alibaba', 'kylin10']
DEB_BASED_OS = ['uos', 'kylin4.0.2', 'debian', 'ubuntu', 'uniontech']
SUPPORTED_ARCH = ['x86_64', 'aarch64', 'mips64el']
DIST_WITH_RPM_DEB = ['kylin']
HOST_ARCH = platform.machine()


'''
[root@10-0-67-98 ~]# ip link set mtu 65522 dev vnic2.0
RTNETLINK answers: Invalid argument
[root@10-0-67-98 ~]# ip link set mtu 65521 dev vnic2.0
[root@10-0-67-98 ~]# ip link set mtu 9601 dev eth0.100
RTNETLINK answers: Numerical result out of range
[root@10-0-67-98 ~]# ip link set mtu 9600 dev eth0.100
'''
MAX_MTU_OF_VNIC = 65500

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

def with_arch(todo_list=SUPPORTED_ARCH, host_arch=HOST_ARCH):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            if set(todo_list) - set(SUPPORTED_ARCH):
                error("Unknown arch in {}".format(todo_list))
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
                error("Distro info is needed.")
            if distro in list(set(RPM_BASED_OS) - set(exclude)):
                return f(*args, **kwargs)
        return innner
    return wrap

def on_debian_based(distro=None, exclude=[]):
    def wrap(f):
        @functools.wraps(f)
        def innner(*args, **kwargs):
            if not distro:
                error("Distro info is needed.")
            if distro in list(set(DEB_BASED_OS) - set(exclude)):
                return f(*args, **kwargs)
        return innner
    return wrap


def get_current_timestamp():
    return time.mktime(datetime.datetime.now().timetuple())

def exception_on_opened_file(f):
    s = shell.call("timeout 10 lsof -Fc %s" % f, exception=False)
    if s:
        raise Exception('file %s is still opened: %s' % (f, ' '.join(s.splitlines())))

def exception_on_opened_dir(d):
    s = shell.call("timeout 10 lsof -Fc +D %s" % d, exception=False)
    if s:
        raise Exception('dir %s is still opened: %s' % (d, ' '.join(s.splitlines())))

def rm_file_force(fpath):
    try:
        os.remove(fpath)
    except:
        pass

black_dpath_list = ["", "/", "*", "/root", "/var", "/bin", "/lib", "/sys"]

def rm_dir_force(dpath, only_check=False):
    if dpath.strip() in black_dpath_list:
        raise Exception("how dare you delete directory %s" % dpath)
    if os.path.exists(dpath) and not only_check:
        if os.path.isdir(dpath):
            shutil.rmtree(dpath)
        else:
            rm_file_force(dpath)
    else:
        rm_cmd = "rm -rf %s" % dpath
        return rm_cmd

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

def process_exists(pid):
    return os.path.exists("/proc/" + str(pid))


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
        if ethname == 'lo':
            continue

        eth = EthernetInfo()
        eth.interface = ethname
        devices[ethname] = eth
        mac = None
        for i in range(0, len(tokens)):
            if tokens[i].endswith('/ether'):
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

    return devices.values()

# only for novlan and vlan networks
def set_bridge_alias_using_phy_nic_name(bridge_name, nic_name):
    shell.call("ip link set %s alias 'phy_nic: %s'" % (bridge_name, nic_name))

def get_bridge_phy_nic_name_from_alias(bridge_name):
    return shell.call("ip link show %s | awk '/alias/{ print $NF; exit }'" % bridge_name).strip()

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
    return long(output.split()[0])

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
    total = shell.call("df %s|tail -1|awk '{print $(NF-4)}'" % dir_path)
    avail = shell.call("df %s|tail -1|awk '{print $(NF-2)}'" % dir_path)
    return long(total) * 1024, long(avail) * 1024

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
        cmdstr = "mount | grep '%s on ' | grep '%s ' " % (url, path)
    elif not url:
        cmdstr = "mount | grep '%s '" % path
    elif not path:
        cmdstr = "mount | grep '%s on '" % url
    else:
        raise Exception('path and url cannot both be None')

    return shell.run(cmdstr) == 0

def mount(url, path, options=None, fstype=None):
    cmd = shell.ShellCmd("mount | grep '%s'" % path)
    cmd(is_exception=False)
    if cmd.return_code == 0: raise MountError(url, '%s is occupied by another device. Details[%s]' % (path, cmd.stdout))

    if not os.path.exists(path):
        os.makedirs(path, 0775)

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

def sshfs_mount_with_vm_uuid(vmuuid, username, hostname, port, password, url, mountpoint, writebandwidth=None):
    out = shell.call("pgrep -a 'qemu-kvm|qemu-system' | grep -w %s | grep [-]machine" % vmuuid)
    is_aio, uid = False, 0

    if out:
        is_aio = "aio=native" in out
        uid = int(out.split(" ", 2)[0])
    return sshfs_mount(username, hostname, port, password, url, mountpoint, writebandwidth, not is_aio, uid)

def sshfs_mount(username, hostname, port, password, url, mountpoint, writebandwidth=None, direct_io=True, uid=0):
    fd, fname = tempfile.mkstemp()
    os.chmod(fname, 0o500)

    if not writebandwidth:
        os.write(fd,
                 "#!/bin/bash\n/usr/bin/sshpass -p %s ssh "
                 "-o StrictHostKeyChecking=no "
                 "-o UserKnownHostsFile=/dev/null -p %d $*\n" % (
                 shellquote(password), port))
    else:
        os.write(fd,
                 "#!/bin/bash\n/usr/bin/sshpass -p %s ssh "
                 "-o 'ProxyCommand pv -q -L %sk | nc %s %s' "
                 "-o StrictHostKeyChecking=no "
                 "-o UserKnownHostsFile=/dev/null -p %d $*\n" % (
                     shellquote(password), writebandwidth / 1024 / 8, hostname, port, port))

    os.close(fd)

    allow = 'allow_root' if uid == 0 else 'allow_other'

    if direct_io:
        ret = shell.check_run("/usr/bin/sshfs %s@%s:%s %s -o %s,direct_io,compression=no,ssh_command='%s'" % (username, hostname, url, mountpoint, allow, fname))
    else:
        ret = shell.check_run("/usr/bin/sshfs %s@%s:%s %s -o %s,compression=no,ssh_command='%s'" % (username, hostname, url, mountpoint, allow, fname))
    os.remove(fname)
    return ret

def fumount(mountpoint, timeout = 10):
    return shell.run("timeout %s fusermount -u %s" % (timeout, mountpoint))

def is_valid_address(address):
    try:
        socket.inet_aton(address)
        return True
    except socket.error:
        return False

def is_valid_hostname(hostname):
    if is_valid_address(hostname):
        return True

    try:
        socket.gethostbyname(hostname)
        return True
    except socket.error:
        return False

def get_host_by_name(host):
    return socket.gethostbyname(host)

def is_valid_nfs_url(url):
    ts = url.split(':')
    if len(ts) != 2: raise InvalidNfsUrlError(url, 'url should have one and only one ":"')
    host = ts[0]
    path = ts[1]
    try:
        socket.gethostbyname(host)
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



def get_file_size_by_http_head(url):
    output = shell.call('curl --head %s' % url)
    for l in output.split('\n'):
        if 'Content-Length' in l:
            filesize = l.split(':')[1].strip()
            return long(filesize)
    return None

def shellquote(s):
    return "'" + s.replace("'", "'\\''") + "'"

def remote_shell_quote(s):
    return ("\\''" + s.replace("'", "'\\''") + "'\\'").encode('utf8')

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
                return True, long(filesize)
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
        process = subprocess.Popen(cmd, shell=True, executable='/bin/sh', cwd=workdir, close_fds=True)
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

    #This fix for race condition when two processes make the dir at the same time
    try:
        os.makedirs(path, mode)
    except OSError as e:
        logger.warn("mkdir for path %s failed: %s " % (path, e))

    return False


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
        return shell.call('ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s %s@%s "%s"' % (sshPort, sshkey_file, user, hostname, cmd))
    finally:
        if sshkey_file:
            os.remove(sshkey_file)

def sshpass_run(hostname, password, cmd, user='root', port=22):
    sshpass_file = write_to_temp_file(password)
    os.chmod(sshpass_file, 0o600)

    try:
        s = shell.ShellCmd('sshpass -f %s ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null %s@%s "%s"' % (
            sshpass_file, port, user, hostname, cmd))
        s(False)
        return s.return_code, s.stdout, s.stderr
    finally:
        rm_file_force(sshpass_file)

def sshpass_call(hostname, password, cmd, user='root', port=22):
    sshpass_file = write_to_temp_file(password)
    os.chmod(sshpass_file, 0o600)

    try:
        return shell.call('sshpass -f %s ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null %s@%s "%s"' % (
            sshpass_file, port, user, hostname, cmd))
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
        bandWidth = '-l %s' % (long(bandWidth) / 1024)
    else:
        bandWidth = ''

    filename_check_option = '`scp -T 2>&1 | grep -q "unknown option" || echo "-T"`'

    sshkey_file = create_ssh_key_file()
    os.chmod(sshkey_file, 0o600)
    try:
        dst_dir = os.path.dirname(dst_filepath)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        scp_cmd = 'scp {7} {6} -P {0} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i {1} {2}@{3}:{4} {5}'\
            .format(sshPort, sshkey_file, host_account, hostname, remote_shell_quote(src_filepath), dst_filepath, bandWidth, filename_check_option)
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
        ssh_cmd = 'ssh -p %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s %s@%s "mkdir -m 777 -p %s"' % (sshPort, sshkey_file, host_account, hostname, dst_dir)
        shell.call(ssh_cmd)
        scp_cmd = 'scp -P %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i %s %s %s@%s:%s' % (sshPort, sshkey_file, src_filepath, host_account, hostname, dst_filepath)
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
            return long(size_pair.split()[0])
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
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, executable='/bin/sh', universal_newlines=True, close_fds=True)
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

    out = json.loads(cmd.stdout.strip(" \t\n\r"))
    virtual_size, actual_size = out.get('virtual-size'), out.get('actual-size')
    if not virtual_size and not actual_size:
        raise Exception('cannot get the virtual/actual size of the file[%s], %s %s' % (shellquote(file_path), cmd.stdout, cmd.stderr))

    virtual_size = long(virtual_size) if virtual_size else None
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
    fmt = shell.call("set -o pipefail; %s %s | grep -w '^file format' | awk '{print $3}'" %
            (qemu_img.subcmd('info'), src))
    fmt = fmt.strip(' \t\r\n')
    if fmt != 'raw' and fmt != 'qcow2':
        logger.debug("/usr/bin/qemu-img info %s" % src)
        raise Exception('unknown format[%s] of the image file[%s]' % (fmt, src))
    return fmt

def qcow2_clone(src, dst):
    fmt = get_img_fmt(src)
    shell.check_run('/usr/bin/qemu-img create -F %s -b %s -f qcow2 %s' % (fmt, src, dst))
    os.chmod(dst, 0o660)

def qcow2_clone_with_cmd(src, dst, cmd=None):
    if cmd is None or cmd.kvmHostAddons is None or cmd.kvmHostAddons.qcow2Options is None:
        qcow2_clone(src, dst)
    else:
        qcow2_clone_with_option(src, dst, cmd.kvmHostAddons.qcow2Options)

def qcow2_clone_with_option(src, dst, opt=""):
    # NOTE(weiw): qcow2 doesn't support specify backing file and preallocation at same time
    pattern = re.compile("\-o\ preallocation\=\w+ ")
    opt = re.sub(pattern, " ", opt)

    fmt = get_img_fmt(src)
    shell.check_run('/usr/bin/qemu-img create -F %s %s -b %s -f qcow2 %s' % (fmt, opt, src, dst))
    os.chmod(dst, 0o660)

def raw_clone(src, dst):
    shell.check_run('/usr/bin/qemu-img create -b %s -f raw %s' % (src, dst))
    os.chmod(dst, 0o660)

def qcow2_create(dst, size):
    shell.check_run('/usr/bin/qemu-img create -f qcow2 %s %s' % (dst, size))
    os.chmod(dst, 0o660)

def qcow2_create_with_cmd(dst, size, cmd=None):
    if cmd is None or cmd.kvmHostAddons is None or cmd.kvmHostAddons.qcow2Options is None:
        qcow2_create(dst, size)
    else:
        qcow2_create_with_option(dst, size, cmd.kvmHostAddons.qcow2Options)

def qcow2_create_with_option(dst, size, opt=""):
    shell.check_run('/usr/bin/qemu-img create -f qcow2 %s %s %s' % (opt, dst, size))
    os.chmod(dst, 0o660)

def qcow2_create_with_backing_file(backing_file, dst):
    fmt = get_img_fmt(backing_file)
    shell.call('/usr/bin/qemu-img create -F %s -f qcow2 -b %s %s' % (fmt, backing_file, dst))
    os.chmod(dst, 0o660)

def qcow2_create_with_backing_file_and_cmd(backing_file, dst, cmd=None):
    if cmd is None or cmd.kvmHostAddons is None or cmd.kvmHostAddons.qcow2Options is None:
        qcow2_create_with_backing_file(backing_file, dst)
    else:
        qcow2_create_with_backing_file_and_option(backing_file, dst, cmd.kvmHostAddons.qcow2Options)

def qcow2_create_with_backing_file_and_option(backing_file, dst, opt=""):
    fmt = get_img_fmt(backing_file)

    # NOTE(weiw): qcow2 doesn't support specify backing file and preallocation at same time
    pattern = re.compile("\-o\ preallocation\=\w+ ")
    opt = re.sub(pattern, " ", opt)

    shell.call('/usr/bin/qemu-img create -F %s -f qcow2 %s -b %s %s' % (fmt, opt, backing_file, dst))
    os.chmod(dst, 0o660)

def raw_create(dst, size):
    shell.check_run('/usr/bin/qemu-img create -f raw %s %s' % (dst, size))
    os.chmod(dst, 0o660)

def create_template(src, dst, compress=False, shell=shell):
    fmt = get_img_fmt(src)
    if fmt == 'raw':
        return raw_create_template(src, dst, shell=shell)
    if fmt == 'qcow2':
        return qcow2_create_template(src, dst, compress, shell=shell)
    raise Exception('unknown format[%s] of the image file[%s]' % (fmt, src))

def qcow2_create_template(src, dst, compress, shell=shell):
    if compress:
        shell.call('%s -c -f qcow2 -O qcow2 %s %s' % (qemu_img.subcmd('convert'), src, dst))
    else:
        shell.call('%s -f qcow2 -O qcow2 %s %s' % (qemu_img.subcmd('convert'), src, dst))

def raw_create_template(src, dst, shell=shell):
    shell.call('%s -f raw -O qcow2 %s %s' % (qemu_img.subcmd('convert'), src, dst))

def qcow2_convert_to_raw(src, dst):
    shell.call('%s -f qcow2 -O raw %s %s' % (qemu_img.subcmd('convert'), src, dst))

def qcow2_rebase(backing_file, target):
    fmt = get_img_fmt(backing_file)
    shell.call('%s -F %s -f qcow2 -b %s %s' % (qemu_img.subcmd('rebase'), fmt, backing_file, target))

def qcow2_rebase_no_check(backing_file, target, backing_fmt=None):
    fmt = backing_fmt if backing_fmt else get_img_fmt(backing_file)
    shell.call('%s -F %s -u -f qcow2 -b "%s" %s' % (qemu_img.subcmd('rebase'), fmt, backing_file, target))

def qcow2_virtualsize(file_path):
    file_path = shellquote(file_path)
    cmd = shell.ShellCmd("set -o pipefail; %s %s | grep -w 'virtual size' | awk -F '(' '{print $2}' | awk '{print $1}'" %
            (qemu_img.subcmd('info'), file_path))
    cmd(False)
    if cmd.return_code != 0:
        raise Exception('cannot get the virtual size of the file[%s], %s %s' % (file_path, cmd.stdout, cmd.stderr))
    out = cmd.stdout.strip(' \t\r\n')
    return long(out)

def qcow2_get_backing_file(path):
    if not os.path.exists(path):
        # for rbd image
        out = shell.call("%s %s | grep 'backing file:' | cut -d ':' -f 2" %
                (qemu_img.subcmd('info'), path))
        return out.strip(' \t\r\n')

    with open(path, 'r') as resp:
        magic = resp.read(4)
        if magic != 'QFI\xfb':
            return ""

        # read backing file info from header
        resp.seek(8)
        backing_file_info = resp.read(12)
        backing_file_offset = struct.unpack('>Q', backing_file_info[:8])[0]
        if backing_file_offset == 0:
            return ""

        backing_file_size = struct.unpack('>L', backing_file_info[8:])[0]
        resp.seek(backing_file_offset)
        return resp.read(backing_file_size)

def qcow2_get_virtual_size(path):
    # type: (str) -> int
    if not os.path.exists(path):
        # for rbd image
        out = shell.call("%s %s | grep -P -o 'virtual size:\K.*' | awk -F '[()a-zA-Z]' '{print $3}'" %
                (qemu_img.subcmd('info'), path))
        return int(out.strip())

    with open(path, 'r') as resp:
        magic = resp.read(4)
        if magic != 'QFI\xfb':
            return os.path.getsize(path)

        # read virtual size info from header
        resp.seek(24)
        return struct.unpack('>Q', resp.read(8))[0]

def qcow2_direct_get_backing_file(path):
    o = shell.call('dd if=%s bs=4k count=1 iflag=direct' % path)
    magic = o[:4]
    if magic != 'QFI\xfb':
        return ""

    # read backing file info from header
    backing_file_info = o[8:20]
    backing_file_offset = struct.unpack('>Q', backing_file_info[:8])[0]
    if backing_file_offset == 0:
        return ""

    backing_file_size = struct.unpack('>L', backing_file_info[8:])[0]
    return o[backing_file_offset:backing_file_offset+backing_file_size]

# Get derived file and all its backing files
def qcow2_get_file_chain(path):
    out = shell.call("%s --backing-chain %s | grep 'image:' | awk '{print $2}'" %
            (qemu_img.subcmd('info'), path))
    return out.splitlines()

def get_qcow2_file_chain_size(path):
    chain = qcow2_get_file_chain(path)
    size = 0L
    for path in chain:
        size += get_local_file_disk_usage(path)
    return size

def get_qcow2_base_backing_file_recusively(path):
    chain = qcow2_get_file_chain(path)
    return chain[-1]

def get_qcow2_base_image_recusively(vol_install_dir, image_cache_dir):
    real_vol_dir = os.path.realpath(vol_install_dir)
    real_cache_dir = os.path.realpath(image_cache_dir)
    backing_files = shell.call(
        "set -o pipefail; find %s -type f -name '*.qcow2' -exec %s {} \;| grep 'backing file:' | awk '{print $3}'"
        % (real_vol_dir, qemu_img.subcmd('info'))).splitlines()

    base_image = set()
    for backing_file in backing_files:
        real_image_path = os.path.realpath(backing_file)
        if real_image_path.startswith(real_cache_dir):
            base_image.add(real_image_path)

    if len(base_image) == 1:
        return base_image.pop()

    if len(base_image) == 0:
        return None

    if len(base_image) > 1:
        raise Exception('more than one image file found in cache dir')

def qcow2_fill(seek, length, path, raise_excpetion=False):
    cmd = shell.ShellCmd("qemu-io -c 'write %s %s' %s -n" % (seek, length, path))
    cmd(raise_excpetion)
    logger.debug("qcow2_fill return code: %s, stdout: %s, stderr: %s" % (cmd.return_code, cmd.stdout, cmd.stderr))

def qcow2_measure_required_size(path):
    out = shell.call("/usr/bin/qemu-img measure -f qcow2 -O qcow2 %s | grep 'required size' | cut -d ':' -f 2" % path)
    return long(out.strip(' \t\r\n'))


class AbstractFileConverter(object):
    __metaclass__ = abc.ABCMeta

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
        shell.call("ifconfig %s %s netmask %s" % (dev, ip, netmask))

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

def is_bridge(dev):
    path = "/sys/class/net/%s/bridge" % dev
    return os.path.exists(path)


def is_vif_on_bridge(bridge_name, interface):
    vifs = get_all_bridge_interface(bridge_name)
    if interface in vifs:
        return True

def get_all_bridge_interface(bridge_name):
    cmd = shell.ShellCmd("brctl show %s|sed -n '2,$p'|cut -f 6-10" % bridge_name)
    cmd(is_exception=False)
    vifs = cmd.stdout.split('\n')
    return [v.strip(" \t\r\n") for v in vifs]

def delete_bridge(bridge_name):
    vifs = get_all_bridge_interface(bridge_name)
    for vif in vifs:
        shell.check_run("brctl delif %s %s" % (bridge_name, vif))

    shell.check_run("ip link set %s down" % bridge_name)
    shell.check_run("brctl delbr %s" % bridge_name)

def find_bridge_having_physical_interface(ifname):
    output = shell.call("brctl show|sed -n '2,$p'|cut -f 1,6")
    for l in output.split('\n'):
        l = l.strip(' \n\t\r')
        if l == '':
            continue

        try:
            (br_name, iface_name) = l.split()
        except:
            # bridge has no physical interface added
            continue

        if ifname == iface_name:
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
        if line.startswith('INTERFACE='): return line.split('=')[1]
    return None


def get_interface_ip_addresses(interface):
    output = shell.call("ip -4 -o a show %s | awk '{print $4}'" % interface.strip())
    return output.splitlines() if output else []


def create_bridge(bridge_name, interface, move_route=True):
    if is_bridge(interface):
        raise Exception('interface %s is bridge' % interface)
    br_name = find_bridge_having_physical_interface(interface)
    if br_name and br_name != bridge_name:
        raise Exception('failed to create bridge[{0}], physical interface[{1}] has been occupied by bridge[{2}]'.format(bridge_name, interface, br_name))

    if not is_network_device_existing(bridge_name):
        shell.call("brctl addbr %s" % bridge_name)
    shell.call("brctl setfd %s 0" % bridge_name)
    shell.call("brctl stp %s off" % bridge_name)
    shell.call("ip link set %s up" % bridge_name)

    if br_name == bridge_name:
        return

    if not is_network_device_existing(interface):
        raise LinuxError("network device[%s] is not existing" % interface)

    shell.call("brctl addif %s %s" % (bridge_name, interface))
    #Set bridge MAC address as network device MAC address. It will avoid of 
    # bridge MAC address is reset to other new added dummy network device's 
    # MAC address.
    shell.call("ip link set %s address `cat /sys/class/net/%s/address`" % (bridge_name, interface))

    if not move_route:
        return

    out = shell.call('ip addr show dev %s | grep "inet "' % interface, exception=False)
    if not out:
        logger.debug("Interface %s doesn't set ip address yet. No need to move route. " % interface)
        return

    #record old routes
    routes = []
    r_out = shell.call("ip route show dev %s | grep via | sed 's/onlink//g'" % interface)
    for line in r_out.split('\n'):
        if line != "":
            routes.append(line)
            shell.call('ip route del %s' % line)

    #mv ip on interface to bridge
    ip = out.strip().split()[1]
    shell.call('ip addr del %s dev %s' % (ip, interface))
    shell.call('ip addr add %s dev %s' % (ip, bridge_name))

    #restore routes on bridge
    for r in routes:
        shell.call('ip route add %s' % r)

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


def get_cpu_num():
    out = shell.call("grep -c processor /proc/cpuinfo")
    return int(out)

def get_cpu_model():
    vendor_id = shell.call("lscpu |awk -F':' '{IGNORECASE=1}/Vendor ID/{print $2}'").strip()
    model_name = shell.call("lscpu |awk -F':' '{IGNORECASE=1}/Model name/{print $2}'").strip()
    return vendor_id, model_name

@retry(times=3, sleep_time=3)
def get_cpu_speed():
    max_freq = '/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq'
    if os.path.exists(max_freq):
        out = file(max_freq).read()
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
    output = output.strip(" \t\n\r")
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

def delete_vlan_eth(vlan_dev_name):
    if not is_network_device_existing(vlan_dev_name):
        return
    shell.call('ip link set dev %s down' % vlan_dev_name)
    shell.call('vconfig rem %s' % vlan_dev_name)

def create_vlan_eth(ethname, vlan, ip=None, netmask=None):
    vlan = int(vlan)
    if not is_network_device_existing(ethname):
        raise LinuxError('cannot find ethernet device %s' % ethname)

    vlan_dev_name = '%s.%s' % (ethname, vlan)
    if not is_network_device_existing(vlan_dev_name):
        shell.call('vconfig add %s %s' % (ethname, vlan))
        if ip:
            shell.call('ifconfig %s %s netmask %s' % (vlan_dev_name, ip, netmask))
    else:
        if ip is not None and ip.strip() != "" and get_device_ip(vlan_dev_name) != ip:
            # recreate device and configure ip
            delete_vlan_eth(vlan_dev_name)
            shell.call('vconfig add %s %s' % (ethname, vlan))
            shell.call('ifconfig %s %s netmask %s' % (vlan_dev_name, ip, netmask))

    shell.call('ifconfig %s up' % vlan_dev_name)
    return vlan_dev_name

def create_vlan_bridge(bridgename, ethname, vlan, ip=None, netmask=None):
    vlan = int(vlan)
    vlan_dev_name = create_vlan_eth(ethname, vlan, ip, netmask)
    move_route = True
    create_bridge(bridgename, vlan_dev_name, move_route)

def enable_process_coredump(pid):
    memsize = 4 * 1024 * 1024
    shell.run('prlimit --core=%d --pid %s' % (memsize, pid))

def set_vm_priority(pid, priorityConfig):
    cmd = shell.ShellCmd("virsh schedinfo %s --set cpu_shares=%s --live" % (priorityConfig.vmUuid, priorityConfig.cpuShares))
    cmd(is_exception=False)
    if cmd.return_code != 0:
        logger.warn("set vm %s cpu_shares failed" % priorityConfig.vmUuid)

    oom_score_adj_path = "/proc/%s/oom_score_adj" % pid
    if write_file(oom_score_adj_path, priorityConfig.oomScoreAdj) is None:
        logger.warn("set vm %s oomScoreAdj failed" % priorityConfig.vmUuid)

def find_vm_pid_by_uuid(uuid):
    return shell.call("""ps aux | egrep "qemu[-]kvm|qemu[-]system" | awk '/%s/{print $2}'""" % uuid).strip()

def find_process_by_cmdline(cmdlines):
    pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]
    for pid in pids:
        try:
            with open(os.path.join('/proc', pid, 'cmdline'), 'r') as fd:
                cmdline = fd.read()

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

def find_process_by_command(comm, cmdlines):
    pids = [pid for pid in os.listdir('/proc') if pid.isdigit()]
    for pid in pids:
        try:
            comm_path = os.readlink(os.path.join('/proc', pid, 'exe')).split(";")[0]
            if comm_path != comm and os.path.basename(comm_path) != comm:
                continue

            with open(os.path.join('/proc', pid, 'cmdline'), 'r') as fd:
                cmdline = fd.read().replace('\x00', ' ').strip()
                if all(c in cmdline for c in cmdlines):
                    return pid
        except (IOError, OSError):
            continue
    return None

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
    return open(os.path.join('/proc', str(pid), 'cmdline'), 'r').read()

def get_netmask_of_nic(nic_name):
    netmask = shell.call("ifconfig %s | grep Mask | sed s/^.*Mask://" % nic_name)
    if not netmask:
        netmask = shell.call("ifconfig %s | grep netmask|awk -F'netmask' '{print $2}'|awk '{print $1}'" % nic_name)

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
    shell.call('ifconfig %s %s netmask %s' % (dev_name, ip, netmask))
    shell.call('ifconfig %s up' % dev_name)
    #arping(dev_name, ip)

def delete_vip_by_ip_if_exists(vip):
    nic_name = get_nic_name_by_ip(vip)
    if nic_name:
        shell.call('ifconfig %s down' % nic_name)

def delete_vip_by_ip(vip):
    nic_name = get_nic_name_by_ip(vip)
    if not nic_name:
        raise LinuxError('cannot find nic having ip[%s]' % vip)
    shell.call('ifconfig %s down' % nic_name)

def listPath(path):
    if os.path.isabs(path):
        return [ os.path.join(path, p) for p in os.listdir(path) ]
    return [ os.path.realpath(os.path.join(path, p)) for p in os.listdir(path) ]

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

def is_port_available(port):
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        try:
            s.bind(('', int(port)))
            return True
        except:
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

    def put(self, name, val=None, timeout=30):
        self.objects[name] = (val, time.time() + timeout)

    def has(self, name):
        return name in self.objects.keys()

    def get(self, name):
        return self.objects.get(name)

    def remove(self, name):
        del self.objects[name]

    def wait_until_object_timeout(self, name, timeout=60):
        def wait(_):
            return not self.has(name)

        if not wait_callback_success(wait, timeout=timeout):
            raise Exception('after %s seconds, the object[%s] is still there, not timeout' % (timeout, name))

    def _start(self):
        def clean_timeout_object():
            current_time = time.time()
            for name, obj in self.objects.items():
                timeout = obj[1]
                if current_time >= timeout:
                    del self.objects[name]
            return True

        thread.timer(1, clean_timeout_object, stop_on_exception=False).start()


def kill_process(pid, timeout=5, is_exception=True):
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
    kill(15)
    if wait_callback_success(check, None, timeout):
        return

    kill(9)
    if not wait_callback_success(check, None, timeout) and is_exception:
        raise Exception('cannot kill -9 process[pid:%s];the process still exists after %s seconds' % (pid, timeout))


def kill_all_child_process(ppid, timeout=5):
    def check(_):
        return not os.path.exists('/proc/%s' % ppid)

    if check(None):
        return

    shell.run("pkill -15 -P %s" % ppid)
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

def get_eth_ips():
    nics = shell.call("ip a | grep -E 'mtu| inet '")
    result = dict()
    interf = ''

    for i in nics.splitlines():
        if i.find('mtu') >= 0:
            interf = re.findall(r':\ .*:\ ', i)[0].split(': ')[1]
            status = True if re.findall(r'UP', i) else False
            result[interf] = Interface({'name':interf, 'status':status, 'ips':list()})
        elif i.find('inet') >= 0:
            result[interf].ips.append(re.findall(r'inet\ .*\ scope', i)[0].split(' ')[1].split('/')[0])

    return result

def get_nics_by_cidr(cidr):
    eths = get_eth_ips()
    nics = []
    for e in eths.itervalues():
        if e.status == False:
            continue
        for ip in e.ips:
            if ip and netaddr.IPAddress(ip) in netaddr.IPNetwork(cidr):
                nics.append({e.name:ip})

    return nics

def create_vxlan_interface(vni, vtepIp):
    vni = str(vni)
    cmd = shell.ShellCmd("ip -d -o link show dev {name} | grep -w {ip} ".format(**{"name": "vxlan" + vni, "ip": vtepIp}))
    cmd(is_exception=False)
    if cmd.return_code != 0:
        cmd = shell.ShellCmd("ip link del {name}".format(**{"name": "vxlan" + vni}))
        cmd(is_exception=False)

        cmd = shell.ShellCmd("ip link add {name} type vxlan id {id} local {ip} learning noproxy nol2miss nol3miss".format(
            **{"name": "vxlan" + vni, "id": vni, "ip": vtepIp}))
        cmd(is_exception=False)

    cmd = shell.ShellCmd("ip link set %s up" % ("vxlan" + vni))
    cmd(is_exception=False)
    return cmd.return_code == 0

def create_vxlan_bridge(interf, bridgeName, ips):
    if not is_bridge(bridgeName):
        create_bridge(bridgeName, interf, False)
    elif is_vif_on_bridge(bridgeName, interf) is None:
        cmd = shell.ShellCmd("brctl addif %s %s" % (bridgeName, interf))
        cmd(is_exception=False)

    if ips is not None:
        populate_vxlan_fdb(interf, ips)

def populate_vxlan_fdb(interf, ips):
    cmds = []
    for ip in ips:
        cmd = "bridge fdb append to 00:00:00:00:00:00 dev %s dst %s" % (interf, ip)
        cmds.append(cmd)

    cmd = shell.ShellCmd(";".join(cmds))
    cmd(is_exception=False)

    return cmd.return_code == 0


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


def get_libvirt_version():
    return shell.call("libvirtd --version").split()[-1]


def get_qemu_version():
    return shell.call("virsh version | awk '/hypervisor.*QEMU/{print $4}'").strip()


def get_unmanaged_vms(include_not_zstack_but_in_virsh = False):
    libvirt_uuid_pattern = "'[0-9a-z]{8}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{4}-[0-9a-z]{12}'"
    cmd = shell.ShellCmd("pgrep -a qemu-kvm | grep -E -o '\-uuid %s' | awk '{print $2}'" % libvirt_uuid_pattern)
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
        logger.error(e)
        return None


def read_file_lines(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as fd:
            return fd.readlines()
    except IOError as e:
        logger.error(e)
        return None


def write_file(path, content, create_if_not_exist = False):
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


def tail_1(path):
    if not os.path.exists(path):
        return None
    if os.path.getsize(path) <= 2:
        return read_file(path)

    with open(path, 'rb') as f:
        f.seek(-2, os.SEEK_END)
        while f.tell() > 0 and f.read(1) != b"\n":
            f.seek(-2, os.SEEK_CUR)
        return f.readline()


def get_libvirtd_pid():
    if not os.path.exists('/var/run/libvirtd.pid'):
        return None

    with open('/var/run/libvirtd.pid') as f:
        return int(f.read())

def fake_dead(name):
    fakedead_file = '/tmp/fakedead-%s' % name
    if not os.path.exists(fakedead_file):
        return False
    ctx = file(fakedead_file).read().strip()
    if ctx == 'fakedead':
        return True
    return False

def recover_fake_dead(name):
    fakedead_file = '/tmp/fakedead-%s' % name
    if os.path.exists(fakedead_file):
        os.remove(fakedead_file)

def get_agent_pid_by_name(name):
    cmd = shell.ShellCmd('ps -aux | grep \'%s\' | grep -E \'start|restart\' | grep -v grep | awk \'{print $2}\'' % name)
    output = cmd(False)
    print output
    if cmd.return_code != 0:
        return None
    output = output.strip(" \t\r")
    return output

import ctypes
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

def updateGrubFile(grepCmd, sedCmd, files):
    if not grepCmd is None:
        for file in files:            
            if os.path.exists(file):
                cmd = shell.ShellCmd("%s %s" % (grepCmd, file))
                cmd(is_exception = False)
                if cmd.return_code == 0:
                    cmd = shell.ShellCmd("%s %s" % (sedCmd, file))
                    cmd(is_exception=True)
    else:
        for file in files:
            if os.path.exists(file):
                cmd = shell.ShellCmd("%s %s" % (sedCmd, file))
                cmd(is_exception=True)
    return True, None

def set_fail_if_no_path():
    cmd = shell.ShellCmd('ms=`dmsetup ls --target multipath | awk \'{print $1}\'`; for m in $ms; do dmsetup message $m 0 "fail_if_no_path"; done')
    cmd(is_exception=False, logcmd=False)

def get_physical_disk(disk=None, logCommand=True):
    # type: () -> list[str]
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
    dm_name = shell.call("readlink -e %s | awk -F '/' '{print $NF}'" % disk).strip()
    slaves = shell.call("ls /sys/block/%s/slaves/" % dm_name).splitlines()

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
