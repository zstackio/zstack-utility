'''

@author: frank
'''
import os
import errno
import json
import socket
import time
import subprocess
import zstacklib.utils.shell as shell
from zstacklib.utils import log

logcmd = True

logger = log.get_logger(__name__)

class FusionStor():
    PROTOCOL = None
    def __init__(self):
        #protocol: lichbd, sheepdog and nbd
        self.PROTOCOL = 'nbd'

    def set_protocol(self, protocol):
        self.PROTOCOL = protocol

    def get_protocol(self):
        return self.PROTOCOL

def get_protocol():
    fusionstor = FusionStor()
    return fusionstor.get_protocol()

def __call_shellcmd(cmd, exception=False, workdir=None):
    shellcmd = shell.ShellCmd(cmd, workdir)
    shellcmd(exception)
    return shellcmd

def call_try(cmd, exception=False, workdir=None, try_num = None):
    if try_num is None:
        try_num = 10

    shellcmd = None
    for i in range(try_num):
        shellcmd = __call_shellcmd(cmd, False, workdir)
        if shellcmd.return_code == 0 or shellcmd.return_code == errno.EEXIST:
            break

        time.sleep(1)

    return shellcmd

def raise_exp(shellcmd):
    err = []
    err.append('failed to execute shell command: %s' % shellcmd.cmd)
    err.append('return code: %s' % shellcmd.process.returncode)
    err.append('stdout: %s' % shellcmd.stdout)
    err.append('stderr: %s' % shellcmd.stderr)
    raise shell.ShellError('\n'.join(err))

def lichbd_config():
    pass

def lichbd_check_cluster_is_ready(monHostnames=None, sshUsernames=None, sshPasswords=None):
    fusionstorIsReady = False

    for sshUsername in sshUsernames:
        if sshUsername != 'root':
            raise Exception('When you create a stor cluster, you must use the root user.')

    password = sshPasswords[0]
    for sshPassword in sshPasswords:
        if sshPassword != password:
            raise Exception('When you create a stor cluster, the password of root user must be the same with all nodes.')

    for monHostname in monHostnames:
        try:
            socket.inet_aton(monHostname)
        except Exception, e:
            raise Exception('Invalid IP address, now only support IP, DNS will be supported in the future')
 
    nodes = ''
    for monHostname in monHostnames:
        nodes = nodes + ' ' + monHostname

    shell.call('/opt/fusionstack/lich/bin/lich sshkey %s -p "%s"' % (nodes, sshPasswords[0]))

    if os.path.exists('/opt/fusionstack/etc/cluster.conf'):
        fusionstorIsReady = True
    else:
        for monHostname in monHostnames:
            return_code = shell.run('ssh %s ls /opt/fusionstack/etc/cluster.conf' % monHostname)
            if return_code == 0:
                fusionstorIsReady = True
                break

    return fusionstorIsReady

def lichbd_check_node_in_cluster(fusionstorIsReady=False, monHostnames=None):
    nodesInCluster = []
    needAddHostname = []
    if fusionstorIsReady is True:
        with open('/opt/fusionstack/etc/cluster.conf', 'r') as fd:
            alllines = fd.readlines()

        for line in alllines:
            nodesInCluster.append(line.strip())

        for monHostname in monHostnames:
            if monHostname not in nodesInCluster:
                needAddHostname.append(monHostname)

    return needAddHostname

def lichbd_create_cluster(monHostnames, sshPasswords):
    if len(monHostnames) < 3:
        raise Exception('creating stor cluster needs three nodes at least')

    nodes = ''
    for monHostname in monHostnames:
        nodes = nodes + ' ' + monHostname

    shell.call("echo '#hosts list for nohost mode' > /opt/fusionstack/etc/hosts.conf")
    for monHostname in monHostnames:
        hostname = shell.call('ssh %s hostname' % monHostname)
        hostname = hostname.strip()
        shell.call('echo %s %s >> /opt/fusionstack/etc/hosts.conf' % (monHostname, hostname))

    fields = monHostnames[0].split('.')
    field1 = int(fields[0])
    if field1 > 0 and field1 < 127:
        net = fields[0] + '.0.0.0'
    elif field1 > 127 and field1 <= 191:
        net = fields[0] + '.' + fields[1] + '.0.0'
    elif field1 > 191 and field1 < 224:
        net = fields[0] + '.' + fields[1] + '.' + fields[2] + '.0'
    else:
        raise Exception('invalid ip')

    shell.call("sed -i 's/^\s*\([0-9]\{1,3\}\).*/                %s\/24;/g' /opt/fusionstack/etc/lich.conf" % net)
    shell.call("sed -i 's/^\s*\#nohosts on;/       nohosts on;/g' /opt/fusionstack/etc/lich.conf")

    shell.call('/opt/fusionstack/lich/bin/lich prep %s -p "%s"' % (nodes, sshPasswords[0]))
    shell.call('/opt/fusionstack/lich/bin/lich create %s' % nodes)

def lichbd_add_node(monHostname):
    disks = shell.call('/opt/fusionstack/lich/bin/lich addnode %s' % monHostname)

def lichbd_add_disks(monHostname):
    shell.call('ssh %s /opt/fusionstack/lich/bin/lich.node --raid_add all' % monHostname)
    shell.call('ssh %s /opt/fusionstack/lich/bin/lich.node --disk_add all' % monHostname)

def lichbd_get_iqn():
    shellcmd = call_try("""lich  configdump 2>/dev/null|grep iqn|awk -F":" '{print $2}'""")
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    iqn = shellcmd.stdout.strip()
    return iqn

def lichbd_get_qemu_path():
    qemu_path = "/opt/fusionstack/qemu/bin/qemu-system-x86_64"
    return qemu_path 

def lichbd_get_qemu_img_path():
    qemu_path = "/opt/fusionstack/qemu/bin/qemu-img"
    return qemu_path

def lichbd_get_iscsiport():
    shellcmd = call_try("""lich configdump 2>/dev/null|grep iscsi.port|awk -F":" '{print $2}'""")
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    port = shellcmd.stdout.strip()
    return int(port)

def lichbd_mkpool(path):
    protocol = get_protocol()
    shellcmd = call_try('lichbd mkpool %s -p %s 2>/dev/null' % (path, protocol))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_lspools():
    protocol = get_protocol()
    shellcmd = call_try('lichbd lspools -p %s 2>/dev/null' % protocol)
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_rmpool(path):
    protocol = get_protocol()
    shellcmd = call_try('lichbd rmpool %s -p %s 2>/dev/null' % (path, protocol))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_create(path, size):
    protocol = get_protocol()
    shellcmd = call_try('lichbd create %s --size %s -p %s 2>/dev/null' % (path, size, protocol))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_create_raw(path, size):
    lichbd_create(path, size)

def lichbd_copy(src_path, dst_path):
    shellcmd = None
    protocol = get_protocol()
    shellcmd = call_try('lichbd copy %s %s -p %s 2>/dev/null' % (src_path, dst_path, protocol))
    if shellcmd.return_code == 0:
        return shellcmd
    else:
        if dst_path.startswith(":"):
            call("rm -rf %s" % (dst_path.lstrip(":")))
        else:
            lichbd_rm(dst_path)

    raise_exp(shellcmd)

def lichbd_import(src_path, dst_path):
    shellcmd = None
    protocol = get_protocol()
    shellcmd = call_try('lichbd import %s %s -p %s 2>/dev/null' % (src_path, dst_path, protocol))
    if shellcmd.return_code == 0:
        return shellcmd
    else:
        lichbd_rm(dst_path)

    raise_exp(shellcmd)

def lichbd_export(src_path, dst_path):
    shellcmd = None
    protocol = get_protocol()
    shellcmd = call_try('lichbd export %s %s -p %s 2>/dev/null' % (src_path, dst_path, protocol))
    if shellcmd.return_code == 0:
        return shellcmd
    else:
        call("rm -rf %s" % dst_path)

    raise_exp(shellcmd)

def lichbd_rm(path):
    protocol = get_protocol()
    shellcmd = call_try('lichbd rm %s -p %s 2>/dev/null' % (path, protocol))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.ENOENT:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_mv(dist, src):
    protocol = get_protocol()
    shellcmd = call_try('lichbd mv %s %s -p %s 2>/dev/null' % (src, dist, protocol))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

"""
def lichbd_file_size(path):
    protocol = get_protocol()
    shellcmd = call_try("lichbd info %s -p %s 2>/dev/null | grep Size | awk '{print $2}'" % (path, protocol))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    size = shellcmd.stdout.strip()
    return long(size)
"""

def lichbd_file_size(path):
    protocol = get_protocol()
    shellcmd = call_try("lichbd info %s -p %s 2>/dev/null | grep chknum | awk '{print $3}'" % (path, protocol))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    size = shellcmd.stdout.strip()
    return long(size) * 1024 * 1024

def lichbd_file_actual_size(path):
    protocol = get_protocol()
    shellcmd = call_try("lichbd info %s -p %s 2>/dev/null | grep localized | awk '{print $3}'" % (path, protocol))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    size = shellcmd.stdout.strip()
    return long(size) * 1024 * 1024

def lichbd_file_exist(path):
    protocol = get_protocol()
    shellcmd = call_try("lichbd info %s -p %s" % (path, protocol))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == 2:
            return False
        elif shellcmd.return_code == 21:
            return True
        else:
            raise_exp(shellcmd)
    return True

def lichbd_cluster_stat():
    shellcmd = call_try('lich stat --human-unreadable 2>/dev/null')
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_get_used():
    o = lichbd_cluster_stat()
    for l in o.split("\n"):
        if 'used:' in l:
            used = long(l.split("used:")[-1])
            return used

    raise shell.ShellError('lichbd_get_used')

def lichbd_get_capacity():
    try:
        o = lichbd_cluster_stat()
    except Exception, e:
        raise shell.ShellError('lichbd_get_capacity')

    total = 0
    used = 0
    for l in o.split("\n"):
        if 'capacity:' in l:
            total = long(l.split("capacity:")[-1])
        elif 'used:' in l:
            used = long(l.split("used:")[-1])

    return total, used

def lichbd_snap_create(snap_path):
    protocol = get_protocol()
    shellcmd = call_try('lichbd snap create %s -p %s' % (snap_path, protocol))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_list(image_path):
    snaps = []
    protocol = get_protocol()
    shellcmd = call_try('lichbd snap ls %s -p %s 2>/dev/null' % (image_path, protocol))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    for snap in shellcmd.stdout.strip().split():
        snaps.append(snap.strip())

    return snaps

def lichbd_snap_delete(snap_path):
    protocol = get_protocol()
    cmd = 'lichbd snap remove %s -p %s' % (snap_path, protocol)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout
 
def lichbd_snap_clone(src, dst):
    protocol = get_protocol()
    cmd = 'lichbd clone %s %s -p %s' % (src, dst, protocol)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_rollback(snap_path):
    protocol = get_protocol()
    cmd = 'lichbd snap rollback %s -p %s' % (snap_path, protocol)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_protect(snap_path):
    protocol = get_protocol()
    cmd = 'lichbd snap protect %s -p %s' % (snap_path, protocol)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_unprotect(snap_path):
    protocol = get_protocol()
    cmd = 'lichbd snap unprotect %s -p %s' % (snap_path, protocol)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_get_format(path):
    o = shell.call('lich.node --stat 2>/dev/null')
    if 'running' not in o:
        raise shell.ShellError('the lichd process of this node is not running, Please check the lichd service')

    protocol = get_protocol()
    if protocol == 'lichbd':
        qemu_img = lichbd_get_qemu_img_path()
        cmd = "set -o pipefail;%s info rbd:%s 2>/dev/null | grep 'file format' | cut -d ':' -f 2" % (qemu_img, path)
    elif protocol == 'sheepdog':
        cmd = "set -o pipefail;qemu-img info sheepdog+unix:///%s?socket=/tmp/sheepdog.socket 2>/dev/null | grep 'file format' | cut -d ':' -f 2" % path
    elif protocol == 'nbd':
        cmd = "set -o pipefail;qemu-img info nbd:unix:/tmp/nbd-socket:exportname=%s 2>/dev/null | grep 'file format' | cut -d ':' -f 2" % path
    else:
        raise shell.ShellError('Do not supprot protocols, only supprot lichbd and sheepdog')

    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout.strip()

def get_system_qemu_path():
    _qemu_path = None
    if not _qemu_path:
        if os.path.exists('/usr/libexec/qemu-kvm'):
            _qemu_path = '/usr/libexec/qemu-kvm'
        elif os.path.exists('/bin/qemu-kvm'):
            _qemu_path = '/bin/qemu-kvm'
        elif os.path.exists('/usr/bin/qemu-system-x86_64'):
            # ubuntu
            _qemu_path = '/usr/bin/qemu-system-x86_64'
        else:
            raise shell.ShellError('Could not find qemu-kvm in /bin/qemu-kvm or /usr/libexec/qemu-kvm or /usr/bin/qemu-system-x86_64')

    return _qemu_path

def get_system_qemu_img_path():
    _qemu_img_path = None
    if not _qemu_img_path:
        if os.path.exists('/usr/bin/qemu-img'):
            _qemu_img_path = '/usr/bin/qemu-img'
        elif os.path.exists('/bin/qemu-img'):
            _qemu_img_path = '/bin/qemu-img'
        elif os.path.exists('/usr/local/bin/qemu-img'):
            # ubuntu
            _qemu_img_path = '/usr/local/bin/qemu-img'
        else:
            raise shell.ShellError('Could not find qemu-img in /bin/qemu-img or /usr/bin/qemu-img or /usr/local/bin/qemu-img')

    return  _qemu_img_path

def makesure_qemu_with_lichbd():
    _lichbd = lichbd_get_qemu_path()
    _system = get_system_qemu_path()
    need_link = True

    if os.path.islink(_system):
        link = shell.call("set -o pipefail; ls -l %s|cut -d '>' -f 2" % (_system)).strip()
        if link == _lichbd:
            need_link = False

    if need_link:
        rm_cmd = "rm -f %s.tmp" % (_system)
        shell.call(rm_cmd)

        ln_cmd = "ln -s %s %s.tmp" % (_lichbd, _system)
        shell.call(ln_cmd)

        mv_cmd = "mv %s.tmp %s -f" % (_system, _system)
        shell.call(mv_cmd)

def makesure_qemu_img_with_lichbd():
    _lichbd = lichbd_get_qemu_img_path()
    _system = get_system_qemu_img_path()
    need_link = True

    if os.path.islink(_system):
        link = shell.call("set -o pipefail; ls -l %s|cut -d '>' -f 2" % (_system)).strip()
        if link == _lichbd:
            need_link = False

    if need_link:
        rm_cmd = "rm -f %s.tmp" % (_system)
        shell.call(rm_cmd)

        ln_cmd = "ln -s %s %s.tmp" % (_lichbd, _system)
        shell.call(ln_cmd)

        mv_cmd = "mv %s.tmp %s -f" % (_system, _system)
        shell.call(mv_cmd)
