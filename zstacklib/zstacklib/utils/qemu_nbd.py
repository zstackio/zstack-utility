import errno
import os
import signal
import subprocess

from zstacklib.utils import linux


def export(port, *args):
    command = ['qemu-nbd', '-p', str(port)]
    command.extend(str(arg) for arg in args)
    process = subprocess.Popen(command, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process


def find_qemu_nbd_process(pattern):
    return 0 if linux.find_process_list_by_command('qemu-nbd', [pattern]) else 1


def kill_nbd_process_by_flag(flag, timeout=60, interval=1):
    pids = linux.find_process_list_by_command('qemu-nbd', [flag])
    if not pids:
        return 1

    for pid in pids:
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError as e:
            if e.errno != errno.ESRCH:
                raise

    def gone(_):
        return find_qemu_nbd_process(flag) != 0

    if not linux.wait_callback_success(gone, timeout=timeout, interval=interval):
        raise Exception('timeout waiting qemu-nbd process[%s] gone after SIGTERM' % flag)
    return 0
