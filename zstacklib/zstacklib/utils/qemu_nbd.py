from zstacklib.utils import linux
from zstacklib.utils import shell
import subprocess


def export(port, *args):
    command = 'qemu-nbd -p %s' % port
    if args:
        command += ' ' + ' '.join(str(arg) for arg in args)
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process


def kill_nbd_process_by_flag(flag):
    regex = 'qemu-nbd.*%s' % flag
    return linux.pkill_by_pattern(regex)


def find_qemu_nbd_process(pattern):
    command = "pgrep -a qemu-nbd | grep %s" % pattern
    return shell.run(command)
