'''
@author: qiuyu
'''
from __future__ import annotations

import subprocess

from zstacklib.utils import log

logger = log.get_logger(__name__)


def get_image_hash(img_path):
    (status, output) = subprocess.getstatusoutput("md5sum %s | cut -d ' ' -f 1" % img_path)
    if status != 0:
        raise Exception('get image %s hash failed: %s' % (img_path, output))
    return output
