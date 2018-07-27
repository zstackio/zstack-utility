'''

@author: mingjian
'''
# coding=utf-8
import os
import os.path
import socket
from zstacklib.utils import shell
from zstacklib.utils import log
from zstacklib.utils import linux

logger = log.get_logger(__name__)

def createCommonPath(path, basepath):
    if not path.startswith(basepath):
        raise Exception('path[%s] is not subdir of basepath[%s], cannot create common path' % (path, basepath))

    if not is_mounted(basepath):
        raise Exception('the common path[%s] is not mounted' % basepath)

    if not os.path.exists(path):
        shell.call('mkdir -p %s' % path)
    return

def is_mounted(path=None, url=None):
    mounted = linux.is_mounted(path, url)
    if not url:
        return mounted

    if mounted:
        return True

    return linux.is_mounted(path, url.replace(":/", "://"))

def remount(url, path, options=None):
    if not is_mounted(path):
        linux.mount(url, path, options)
        return

    o = shell.ShellCmd('timeout 180 mount -o remount %s' % path)
    o(False)
    if o.return_code == 124:
        raise Exception('unable to access the mount path[%s] of the nfs primary storage[url:%s] in 180s, timeout' %
                        (path, url))
    elif o.return_code != 0:
        o.raise_error()

def getMountInfo(url):
    if url:
        url = url.rstrip('/')
        cmdstr = "mount | grep ':/%s'" % url
    else:
        raise Exception('url cannot be None')
    cmd = shell.ShellCmd(cmdstr)
    cmd(is_exception=False)

    if cmd.return_code == 0:
        mounts = str(cmd.stdout).strip().split("\n")
        return mounts
    else:
        raise Exception('unable to execute mount on host, exception: %s' % cmd.stderr)

class InvalidMountDomainException(Exception):
    '''The mount domain is not work'''
    def __init__(self, url, msg):
        err = 'Invaild Mount Domain[%s], %s' % (url, msg)
        super(InvalidMountDomainException, self).__init__(err)

class InvalidMountPathException(Exception):
    '''The local mount path is something wrong'''
    def __init__(self, msg):
        err = 'Invaild Local Mount Path, %s' % msg
        super(InvalidMountPathException, self).__init__(err)

def checkMountStatus(url, path, info=None):
    if url and path:
        ts = url.split(':')
        if len(ts) != 2:
            raise Exception('url (%s) should have one and only one ":"' % url)
        host = ts[0]
        try:
            socket.gethostbyname(host)
        except socket.gaierror:
            raise InvalidMountDomainException(url, '%s cannont resolve to ip address' % host)

        if not os.path.exists(path):
            raise InvalidMountPathException('%s is not existed on host' % path)

    else:
        raise Exception('no url or path found in getMountStatus')

    if info:
        if "ro," in info or "ro)" in info:
            raise InvalidMountPathException('%s is read only on host' % path)
