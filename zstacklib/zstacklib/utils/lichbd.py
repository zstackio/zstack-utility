'''

@author: frank
'''
import errno
import time
import subprocess
import zstacklib.utils.shell as shell
from zstacklib.utils import log

logcmd = True

logger = log.get_logger(__name__)

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
        if shellcmd.return_code == 0:
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
    shellcmd = call_try('lichbd mkpool %s -p lichbd 2>/dev/null' % (path))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_rmpool(path):
    shellcmd = call_try('lichbd rmpool %s -p lichbd 2>/dev/null' % (path))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_create(path, size):
    shellcmd = call_try('lichbd create %s --size %s -p lichbd 2>/dev/null' % (path, size))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_create_raw(path, size):
    lichbd_create(path, size)

def lichbd_copy(src_path, dst_path):
    shellcmd = None
    for i in range(5):
        shellcmd = call_try('lichbd copy %s %s -p lichbd 2>/dev/null' % (src_path, dst_path))
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
    for i in range(5):
        shellcmd = call_try('lichbd import %s %s -p lichbd 2>/dev/null' % (src_path, dst_path))
        if shellcmd.return_code == 0:
            return shellcmd
        else:
            lichbd_rm(dst_path)

    raise_exp(shellcmd)

def lichbd_export(src_path, dst_path):
    shellcmd = None
    for i in range(5):
        shellcmd = call_try('lichbd export %s %s -p lichbd 2>/dev/null' % (src_path, dst_path))
        if shellcmd.return_code == 0:
            return shellcmd
        else:
            call("rm -rf %s" % dst_path)

    raise_exp(shellcmd)

def lichbd_rm(path):
    shellcmd = call_try('lichbd rm %s -p lichbd 2>/dev/null' % path)
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.ENOENT:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_mv(dist, src):
    shellcmd = call_try('lichbd mv %s %s -p lichbd 2>/dev/null' % (src, dist))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_file_size(path):
    shellcmd = call_try("lichbd info %s -p lichbd 2>/dev/null | grep Size | awk '{print $2}'" % (path))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    size = shellcmd.stdout.strip()
    return long(size)

def lichbd_file_exist(path):
    shellcmd = call_try("lichbd info %s -p lichbd" % (path))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == 2:
            return False
        else:
            raise_exp(shellcmd)
    return True

def lichbd_cluster_stat():
    shellcmd = call_try('lich stat 2>/dev/null')
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_get_used():
    o = lichbd_cluster_stat()
    for l in o.split("\n"):
        if 'used:' in l:
            used = long(l.split("used:")[-1])
            return used

    raise_exp("error: %s" % (0))

def lichbd_get_capacity():
    o = lichbd_cluster_stat()
    for l in o.split("\n"):
        if 'capacity:' in l:
            total = long(l.split("capacity:")[-1])
            return total

    raise_exp("error: %s" % (0))

def lichbd_snap_create(snap_path):
    shellcmd = call_try('lichbd snap create %s -p lichbd' % (snap_path))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_list(image_path):
    snaps = []
    shellcmd = call_try('lichbd snap ls %s -p lichbd 2>/dev/null' % (image_path))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    for snap in shellcmd.stdout.strip().split():
        snaps.append(snap.strip())

    return snaps

def lichbd_snap_delete(snap_path):
    cmd = 'lichbd snap remove %s -p lichbd' % (snap_path)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout
 
def lichbd_snap_clone(src, dst):
    cmd = 'lichbd clone %s %s -p lichbd' % (src, dst)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_rollback(snap_path):
    cmd = 'lichbd snap rollback %s -p lichbd' % (snap_path)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_protect(snap_path):
    cmd = 'lichbd snap protect %s -p lichbd' % (snap_path)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_unprotect(snap_path):
    cmd = 'lichbd snap unprotect %s -p lichbd' % (snap_path)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_get_format(path):
    qemu_img = lichbd_get_qemu_img_path()
    cmd = "set -o pipefail;%s info rbd:%s 2>/dev/null | grep 'file format' | cut -d ':' -f 2" % (qemu_img, path)
    shellcmd = call_try(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout.strip()
