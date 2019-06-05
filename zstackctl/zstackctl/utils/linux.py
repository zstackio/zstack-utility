import shutil
import os

black_dpath_list = ["", "/", "*", "/root", "/var", "/bin", "/lib", "/sys"]


def rm_dir_force(dpath, only_check=False):
    if dpath.strip() in black_dpath_list:
        raise Exception("how dare you delete directory %s" % dpath)
    if os.path.exists(dpath) and not only_check:
        shutil.rmtree(dpath)
    else:
        return dpath
