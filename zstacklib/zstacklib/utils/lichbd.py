'''

@author: frank
'''
import errno
import subprocess
import zstacklib.utils.shell as shell
from zstacklib.utils import log

logcmd = True

logger = log.get_logger(__name__)

def __call_shellcmd(cmd, exception=False, workdir=None):
    shellcmd = ShellCmd(cmd, workdir)
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
    raise ShellError('\n'.join(err))

def lichbd_config():
    pass

def lichbd_get_iqn():
    shellcmd = call_try("""lich  configdump 2>/dev/null|grep iqn|awk -F":" '{print $2}'""")
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    iqn = shellcmd.stdout.strip()
    return iqn

def lichbd_get_iscsiport():
    shellcmd = call_try("""lich configdump 2>/dev/null|grep iscsi.port|awk -F":" '{print $2}'""")
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    port = shellcmd.stdout.strip()
    return int(port)

def lichbd_mkdir(path):
    shellcmd = call_try('lichfs --mkdir %s 2>/dev/null' % (path))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_touch(path):
    shellcmd = call_try('lichfs --touch %s 2>/dev/null' % (path))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

def lichbd_truncate(path, size):
    shellcmd = call_try('lichfs --truncate %s %s 2>/dev/null' % (path, size))
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.EEXIST:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_create_raw(path, size):
    lichbd_touch(path)
    lichbd_truncate(path, size)

def lichbd_copy(src_path, dst_path):
    shellcmd = None
    for i in range(5):
        shellcmd = call_try('lichfs --copy %s %s 2>/dev/null' % (src_path, dst_path))
        if shellcmd.return_code == 0:
            return shellcmd
        else:
            if dst_path.startswith(":"):
                call("rm -rf %s" % (dst_path.lstrip(":")))
            else:
                lichbd_unlink(dst_path)

    raise_exp(shellcmd)

def lichbd_unlink(path):
    shellcmd = call_try('lichfs --unlink %s 2>/dev/null' % path)
    if shellcmd.return_code != 0:
        if shellcmd.return_code == errno.ENOENT:
            pass
        else:
            raise_exp(shellcmd)

def lichbd_file_size(path):
    shellcmd = call_try("lichfs --stat %s 2>/dev/null | grep Size | awk '{print $2}'" % (path))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    size = shellcmd.stdout.strip()
    return long(size)

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
    shellcmd = call('/opt/fusionstack/libexec/lich.snapshot --create %s' % (snap_path))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_list(image_path):
    snaps = []
    shellcmd = call('/opt/fusionstack/lich/libexec/lich.snapshot --list %s 2>/dev/null' % (image_path))
    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    for snap in shellcmd.stdout.strip().split():
        snaps.append(snap.strip())

    return snaps

def lichbd_snap_delete(snap_path):
    cmd = '/opt/fusionstack/lich/libexec/lich.snapshot --remove %s' % (snap_path)
    shellcmd = call(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout
 
def lichbd_snap_clone(src, dst):
    cmd = '/opt/fusionstack/lich/libexec/lich.snapshot --clone %s %s' % (src, dst)
    shellcmd = call(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_rollback(snap_path):
    cmd = '/opt/fusionstack/lich/libexec/lich.snapshot --rollback %s' % (snap_path)
    shellcmd = call(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_protect(snap_path):
    cmd = '/opt/fusionstack/lich/libexec/lich.snapshot --protect %s' % (snap_path)
    shellcmd = call(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_snap_unprotect(snap_path):
    cmd = '/opt/fusionstack/lich/libexec/lich.snapshot --unprotect %s' % (snap_path)
    shellcmd = call(cmd)

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout

def lichbd_download(url, image_path):
    shellcmd = call('set -o pipefail; wget --no-check-certificate -q -O - %s | /opt/fusionstack/lich/libexec/lichfs --copy :- %s' % (url, image_path))

    if shellcmd.return_code != 0:
        raise_exp(shellcmd)

    return shellcmd.stdout
