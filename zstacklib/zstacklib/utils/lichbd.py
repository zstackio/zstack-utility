'''

@author: frank
'''
import errno
import subprocess
import zstacklib.utils.shell as shell
from zstacklib.utils import log

logcmd = True

logger = log.get_logger(__name__)

def lichbd_config():
    pass

def lichbd_get_iqn():
    shellcmd = shell.call_try("""lich  configdump 2>/dev/null|grep iqn|awk -F":" '{print $2}'""")
    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    iqn = shellcmd.stdout.strip()
    return iqn

def lichbd_get_iscsiport():
    shellcmd = shell.call_try("""lich configdump 2>/dev/null|grep iscsi.port|awk -F":" '{print $2}'""")
    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    port = shellcmd.stdout.strip()
    return int(port)

def lichbd_mkdir(path):
    shellcmd = shell.call_try('lichfs --mkdir %s 2>/dev/null' % (path))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            shell.raise_exp(shellcmd)

def lichbd_touch(path):
    shellcmd = shell.call_try('lichfs --touch %s 2>/dev/null' % (path))
    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

def lichbd_truncate(path, size):
    shellcmd = shell.call_try('lichfs --truncate %s %s 2>/dev/null' % (path, size))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            shell.raise_exp(shellcmd)

def lichbd_create_raw(path, size):
    lichbd_touch(path)
    lichbd_truncate(path, size)

def lichbd_copy(src_path, dst_path):
    shellcmd = None
    for i in range(5):
        shellcmd = shell.call_try('lichfs --copy %s %s 2>/dev/null' % (src_path, dst_path))
        if shellcmd.return_code == 0:
            return shellcmd
        else:
            if dst_path.startswith(":"):
                shell.call("rm -rf %s" % (dst_path.lstrip(":")))
            else:
                lichbd_unlink(dst_path)

    shell.raise_exp(shellcmd)

def lichbd_unlink(path):
    shellcmd = shell.call_try('lichfs --unlink %s 2>/dev/null' % path)
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.ENOENT:
            pass
        else:
            shell.raise_exp(shellcmd)

def lichbd_file_size(path):
    shellcmd = shell.call_try("lichfs --stat %s 2>/dev/null | grep Size | awk '{print $2}'" % (path))
    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    size = shellcmd.stdout.strip()
    return long(size)

def lichbd_cluster_stat():
    shellcmd = shell.call_try('lich stat 2>/dev/null')
    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_get_used():
    o = lichbd_cluster_stat()
    for l in o.split("\n"):
        if 'used:' in l:
            used = long(l.split("used:")[-1])
            return used

    shell.raise_exp("error: %s" % (0))

def lichbd_get_capacity():
    o = lichbd_cluster_stat()
    for l in o.split("\n"):
        if 'capacity:' in l:
            total = long(l.split("capacity:")[-1])
            return total

    shell.raise_exp("error: %s" % (0))

def lichbd_snap_create(snap_path):
    shellcmd = shell.call('/opt/fusionstack/libexec/lich.snapshot --create %s' % (snap_path))
    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_list(image_path):
    snaps = []
    shellcmd = shell.call('/opt/fusionstack/lich/libexec/lich.snapshot --list %s 2>/dev/null' % (image_path))
    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    for snap in shellcmd.stdout.strip().split():
        snaps.append(snap.strip())

    return snaps

def lichbd_snap_delete(snap_path):
    cmd = '/opt/fusionstack/lich/libexec/lich.snapshot --remove %s' % (snap_path)
    shellcmd = shell.call(cmd)

    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    return shellcmd.stdout
 
def lichbd_snap_clone(src, dst):
    cmd = '/opt/fusionstack/lich/libexec/lich.snapshot --clone %s %s' % (src, dst)
    shellcmd = shell.call(cmd)

    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_rollback(snap_path):
    cmd = '/opt/fusionstack/lich/libexec/lich.snapshot --rollback %s' % (snap_path)
    shellcmd = shell.call(cmd)

    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_download(url, image_path):
    shellcmd = shell.call('set -o pipefail; wget --no-check-certificate -q -O - %s | /opt/fusionstack/lich/libexec/lichfs --copy :- %s' % (url, image_path))

    if shellcmd.return_code != 0:
        shell.raise_exp(shellcmd)

    return shellcmd.stdout
