'''
@author: qiuyu
'''

import os
import base64
import commands

from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import qemu_img
import zstacklib.utils.uuidhelper as uuidhelper

logger = log.get_logger(__name__)


def get_image_hash(img_path):
    _, md5 = commands.getstatusoutput("md5sum %s | cut -d ' ' -f 1" % img_path)
    return md5

def is_img_encrypted(img_path, chain=True):
    if chain:
        return not shell.run('/usr/bin/qemu-img info --backing-chain %s | grep "encrypted: yes"' % img_path)
    return not shell.run('/usr/bin/qemu-img info %s | grep "encrypted: yes"' % img_path)


def get_qemu_encrypt_options():
    return ' --object secret,id={0},file={1},format=base64'\
           ' -o encrypt.format=luks,encrypt.key-secret={0} '\
           .format(ZSTACK_SECRET_OBJECT_ID, ZSTACK_ENCRYPT_B64_PATH)


def get_qemu_rebase_encrypt_options():
    return ' --object secret,id={0},file={1},format=base64'\
           .format(ZSTACK_SECRET_OBJECT_ID, ZSTACK_ENCRYPT_B64_PATH)


def get_img_path_with_secret_objects(img_path):
    if not is_img_encrypted(img_path):
        return img_path

    return ' \'json:{"encrypt.key-secret": "%s", "driver": "qcow2",'\
           ' "file": {"driver": "file", "filename":"%s"}}\' '\
           % (ZSTACK_SECRET_OBJECT_ID, img_path)


def encrypt_img(img_path):
    if is_img_encrypted(img_path):
        return

    tmp_path = img_path + ".bck"
    os.rename(img_path, tmp_path)
    opt = get_qemu_encrypt_options()
    shell.call('%s -f qcow2 -O qcow2 %s %s %s' % (qemu_img.subcmd('convert'), opt, tmp_path, img_path))
    os.remove(tmp_path)


# memory snapshots are base64 encrypted, there is no luks encrypt uuid for it, so only return it's md5sum
# otherwise, return luks encrypt uuid and md5sum
def get_image_encrypt_uuid_and_hash(img_path, disk_encryption = True):
    if disk_encryption:
        _, uuid = commands.getstatusoutput("qemu-img info %s | grep uuid | awk -F ': ' '{ print $NF }'" % img_path)
    else:
        uuid = uuidhelper.uuid()
    _, md5 = commands.getstatusoutput("md5sum %s | cut -d ' ' -f 1" % img_path)
    return uuid, md5
