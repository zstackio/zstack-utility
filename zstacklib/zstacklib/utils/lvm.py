import os
import os.path
import socket
import subprocess
import datetime
import time
import tempfile
import traceback
import struct
import netaddr
import functools
import threading
import re
import platform
import random

from zstacklib.utils import shell
from zstacklib.utils import log
from zstacklib.utils import lock
from zstacklib.utils import sizeunit
from zstacklib.utils import linux

logger = log.get_logger(__name__)

class RetryException(Exception):
    pass

def check_lvm_config_is_default():
    cmd = shell.ShellCmd("lvmconfig --type diff")
    cmd(is_exception=True)
    if cmd.stdout != "":
        return True
    else:
        return False

def config_lvm_conf(node, value):
    cmd = shell.ShellCmd("lvmconfig --config %s=%s -f /etc/lvm/lvm.conf" % (node, value))
    cmd(is_exception=True)

def config_lvmlocal_conf(node, value):
    cmd = shell.ShellCmd("lvmconfig --config %s=%s -f /etc/lvm/lvmlocal.conf" % (node, value))
    cmd(is_exception=True)

def start_lvmlockd():
    for service in ["lvmlockd", "wdmd", "sanlock"]:
        cmd = shell.ShellCmd("systemctl start %s" % service)
        cmd(is_exception=True)

def start_vg_lock(vgUuid):
    @linux.retry(times=3, sleep_time=random.uniform(0.1, 3))
    def start_lock(vgUuid):
        cmd = shell.ShellCmd("vgchange --lock-start %s" % vgUuid)
        cmd(is_exception=True)
        if cmd.return_code != 0:
            raise Exception("vgchange --lock-start failed")

        cmd = shell.ShellCmd("lvmlockctl -i | grep %s" % vgUuid)
        cmd(is_exception=True)
        if cmd.return_code != 0:
            raise RetryException("can not find lock space for vg %s via lvmlockctl" % vgUuid)

    try:
        start_lock(vgUuid)
    except RetryException as e:
        raise e

def get_vg_size(vgUuid):
    cmd = shell.ShellCmd("vgs --nolocking %s --noheadings --separator : --units b -o vg_size,vg_free" % vgUuid)
    cmd(is_exception=True)
    return cmd.stdout.strip().split(':')[0].strip("B"), cmd.stdout.strip().split(':')[1].strip("B")

def add_vg_tag(vgUuid, tag):
    cmd = shell.ShellCmd("vgchange --addtag %s %s" % (tag, vgUuid))
    cmd(is_exception=True)