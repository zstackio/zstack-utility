from zstacklib.utils import shell
from distutils.version import LooseVersion
import json

__QEMU_IMG_VERSION = None

class CheckResult(object):
    def __init__(self, offset, t_clusters, check_erorrs, a_clusters, filename, format):
        self.image_end_offset = offset
        self.total_clusters = t_clusters
        self.check_errors = check_erorrs
        self.allocated_clusters = a_clusters
        self.filename = filename
        self.format = format


def subcmd(subcmd):
    global __QEMU_IMG_VERSION
    if __QEMU_IMG_VERSION is None:
        command = "qemu-img --version | grep 'qemu-img version' | cut -d ' ' -f 3 | cut -d '(' -f 1"
        __QEMU_IMG_VERSION = shell.call(command).strip('\t\r\n ,')

    options = ''
    if LooseVersion(__QEMU_IMG_VERSION) >= LooseVersion('2.10.0'):
        if subcmd in ['info', 'check', 'compare', 'convert', 'rebase']:
            options += ' --force-share '
    return 'qemu-img %s %s ' % (subcmd, options)

def get_check_result(path):
    check_cmd = "%s --out json %s" % (subcmd('check'), path)
    result = json.loads(shell.call(check_cmd))
    return CheckResult(result.get("image-end-offset"), result.get("total-clusters"),
                       result.get("check-errors"), result.get("allocated-clusters"),
                       result.get("filename"), result.get("format"))


