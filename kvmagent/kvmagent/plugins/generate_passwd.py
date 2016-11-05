'''
@author: mingjian
'''
from kvmagent import kvmagent
from zstacklib.utils import log
from zstacklib.utils import shell
import os
import crypt

logger = log.get_logger(__name__)

class ChangePasswd(object):
    def __init__(self):
        self.password = None
        self.account = None
        self.image = None
        shell.call('rm -f shadow config grub.cfg grub')
    def __del__(self):
        shell.call('rm -f shadow config grub.cfg grub')
    def _check_file(self, path, file):
        if not os.path.exists(file):
            logger.warn("file: %s%s is not exist..." % (path, file))
            return False
        return True
    def _replace_shadow(self):
        crypt_passwd=crypt.crypt(self.password, crypt.mksalt(crypt.METHOD_SHA512))
        replace_cmd="egrep \"^%s:\" shadow|awk -v passwd=%s -F \":\" \'{$2=passwd;OFS=\":\";print}\'" \
            % (self.account, crypt_passwd)
        replace_passwd=shell.call(replace_cmd)
        logger.debug("crypt_passwd is: %s, replace_cmd is %s: " % (crypt_passwd, replace_passwd))
        sed_cmd="sed -i \"s!^%s:.*\\$!%s!\" shadow" % (self.account, replace_passwd)
        shell.call(sed_cmd)
        shell.call("virt-copy-in -a %s shadow /etc/" % self.image)
    def _close_selinux(self):
        #close selinux under CentOS
        _check_file("/etc/selinux/", "config")
        _check_file("/etc/selinux/", "grub.cfg")
        _check_file("/etc/selinux/", "config")
        #change /etc/selinux/config
        shell.call("sed -i \'s/^\\s*SELINUX=.*$/SELINUX=disabled\' config")
        shell.call("sed -i \'s/^\\s*GRUB_CMDLINE_LINUX=/{/selinux=0/!{s/\"\\s*$/ selinux=0\"/}}\' grub")
        shell.call("sed -i \'1,${/^\\s*linux16 /{/selinux=0/!{s/\\s*$/ selinux=0/}}}\' grub.cfg")

        shell.call("virt-copy-in -a %s config /etc/selinux/" % self.image)
        shell.call("virt-copy-in -a %s grub /etc/default/" % self.image)
        shell.call("virt-copy-in -a %s grub.cfg /boot/grub2/" % self.image)
    def _check_parameters(self):
        if self.password == None or self.account == None or self.image == None:
            logger.warn("parameters must contain 3 parameters at least: account, password, qcow2")
            return False
        if not _check_file("", self.image):
            return False
        return True
    def _is_CentOS(self):
        OSVersion=shell.call('virt-inspector -a %s |grep CentOS' % self.image)
        if not OSVersion:
            logger.debug("not CentOS, dont need to close selinux")
            return False
        return True


    @kvmagent.replyerror
    def generate_passwd(self):
        if not _check_parameters():
            return False
        version = _is_CentOS()
        if version:
            try:
                shell.call("virt-copy-out -a %s /etc/shadow /etc/selinux/config /boot/grub.cfg /etc/default/grub ." % self.image)
                _close_selinux()
            except Exception as e:
                logger.warn(e)
        if not _check_file("/etc/", "shadow"):
            return False
        _replace_shadow()
        shell.call('rm -f shadow config grub.cfg grub')
        return True

