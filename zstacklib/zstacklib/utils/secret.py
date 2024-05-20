'''
@author: qiuyu
'''

import os
import base64
import commands

from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import qemu_img

logger = log.get_logger(__name__)


def get_image_hash(img_path):
    (status, output) = commands.getstatusoutput("md5sum %s | cut -d ' ' -f 1" % img_path)
    if status != 0:
        raise Exception('get image %s hash failed: %s' % (img_path, output))
    return output
