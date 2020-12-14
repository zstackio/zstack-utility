import shutil
import os

black_dpath_list = ["", "/", "*", "/root", "/var", "/bin", "/lib", "/sys"]


def _check_black_path(path):
    if path.strip() in black_dpath_list:
        raise Exception("how dare you delete directory %s" % path)


def get_checked_rm_dir_cmd(dpath):
    _check_black_path(dpath)
    return "rm -rf " + dpath


def rm_dir_force(dpath):
    _check_black_path(dpath)
    if not os.path.exists(dpath):
        return
    if os.path.isdir(dpath):
        shutil.rmtree(dpath, ignore_errors=True)
    else:
        rm_file_force(dpath)


def rm_file_force(fpath):
    try:
        os.remove(fpath)
    except:
        pass

def read_file(path):
    if not os.path.exists(path):
        return None
    with open(path, 'r') as fd:
        return fd.read()

import ctypes
libc = ctypes.CDLL("libc.so.6")

def sync_file(fpath):
    if not os.path.isfile(fpath):
        return

    fd = os.open(fpath, os.O_RDONLY|os.O_NONBLOCK)
    try:
        libc.syncfs(fd)
    except:
        pass
    finally:
        os.close(fd)
