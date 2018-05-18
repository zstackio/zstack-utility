'''

@author: mingjian
'''
# coding=utf-8
import os
import os.path
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