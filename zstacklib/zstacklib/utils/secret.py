'''
@author: qiuyu
'''

import base64
import commands

from zstacklib.utils import log
from zstacklib.utils import shell

logger = log.get_logger(__name__)


def get_image_hash(img_path):
    _, md5 = commands.getstatusoutput("md5sum %s | cut -d ' ' -f 1" % img_path)
    return md5

def is_img_encrypted(img_path):
    return not shell.run('/usr/bin/qemu-img info %s | grep "encrypted: yes"' %
                         img_path)

def is_encrypted_by_cmd(cmd):
    if cmd and cmd.kvmHostAddons:
        if cmd.kvmHostAddons.encryptKey:
            return True
    return False

def get_qemu_encrypt_options(cmd):
    b64_key = base64.b64encode(cmd.kvmHostAddons.encryptKey)
    if cmd.size:
        return ' --object secret,id={0},data={1},format=base64'\
               ' -o encrypt.format=luks,encrypt.key-secret={0},'\
               'encrypt.cipher-alg=sm4,size={2} '\
               .format('sec_' + cmd.volumeUuid, b64_key, cmd.size)
    return ' --object secret,id={0},data={1},format=base64'\
           ' -o encrypt.format=luks,encrypt.key-secret={0},'\
           'encrypt.cipher-alg=sm4 '\
           .format('sec_' + cmd.volumeUuid, b64_key)

def get_img_path_with_secret_objects(img_path, cmd=None):
    if not is_img_encrypted(img_path):
        return img_path

    return ' \'json:{"encrypt.key-secret": "%s", "driver": "qcow2",'\
           ' "file": {"driver": "file", "filename":"%s"}}\' '\
           % ('sec_' + cmd.volumeUuid, img_path)

def get_qemu_resize_encrypt_options(cmd, install_abs_path):
    b64_key = base64.b64encode(cmd.kvmHostAddons.encryptKey)
    return ' --object secret,id={0},data={1},format=base64 --image-opts ' \
           'driver=qcow2,encrypt.key-secret={0},file.filename={2} '\
        .format('sec_' + cmd.volumeUuid, b64_key, install_abs_path)
