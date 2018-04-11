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

def createCommonPath(path, basepath, url):
    linux.is_valid_nfs_url(url)
    if not path.startswith(basepath):
        raise Exception('path[%s] is not subdir of basepath[%s], cannot create common path' % (path, basepath))

    if not linux.is_mounted(basepath, url):
        raise Exception('the common path[%s] is not mounted on [%s]' % (basepath, url))

    if not os.path.exists(path):
        shell.call('mkdir -p %s' % path)
    return
