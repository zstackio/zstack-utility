from zstacklib.utils import shell
from distutils.version import LooseVersion

__QEMU_IMG_VERSION = None

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
