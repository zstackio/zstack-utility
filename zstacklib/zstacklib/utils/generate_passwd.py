'''
@author: mingjian
'''
import crypt
import os

from zstacklib.utils import log
from zstacklib.utils import shell

logger = log.get_logger(__name__)

class ChangePasswd(object):
    def __init__(self):
        self.password = None
        self.account = None
        self.image = None
        self.crypt = {'SHA512':crypt.METHOD_SHA512,
                      'SHA256': crypt.METHOD_SHA256,
                      'MD5': crypt.METHOD_MD5,
                      'CRYPT': crypt.METHOD_CRYPT}
        self._clean_up()
    def __del__(self):
        self._clean_up()
    def _clean_up(self):
        shell.call('rm -f shadow config login.defs')
    def _check_file(self, path, file_str):
        if not os.path.exists(file_str):
            logger.warn("file: %s%s is not exist..." % (path, file_str))
            return False
        return True
    def _enable_md5_crypt(self):
        md5_crypt = shell.call("grep MD5_CRYPT_ENAB login.defs", False).strip('\n')
        if not md5_crypt:
            logger.debug("we must close MD5_CRYPT_ENAB.")
            shell.call("sed -i \'s/^\\s*MD5_CRYPT_ENAB\\s*no/MD5_CRYPT_ENAB yes/\' login.defs")
            shell.call("virt-copy-in -a %s login.defs /etc/" % self.image)
    def _replace_shadow(self):
        crypt_method = shell.call('grep ENCRYPT_METHOD login.defs|awk \'{print $2}\'', False).strip('\n')
        if not self.crypt[crypt_method]:
            raise Exception("not support crypt algorithm, please check ENCRYPT_METHOD in /etc/login.defs... ")
        logger.debug("crypt_method is: %s" % str(self.crypt[crypt_method]))
        crypt_passwd = crypt.crypt(self.password, crypt.mksalt(self.crypt[crypt_method]))
        replace_cmd = "egrep \"^%s:\" shadow|awk -v passwd='%s' -F \":\" \'{$2=passwd;OFS=\":\";print}\'" % (self.account, crypt_passwd)
        replace_passwd = shell.call(replace_cmd, False).strip('\n')
        if not replace_passwd:
            logger.warn('user [%s] not exist!' % self.account)
            raise Exception('user [%s] not exist!' % self.account)
        logger.debug("crypt_passwd is: %s, replace_passwd is: %s" % (crypt_passwd, replace_passwd.replace('$', '\$')))
        sed_cmd = "sed -i \"s!^%s:.*\\$!%s!\" shadow" % (self.account, replace_passwd.replace('$', '\$'))
        shell.call(sed_cmd)
        shell.call("virt-copy-in -a %s shadow /etc/" % self.image)
        self._enable_md5_crypt()
    def _close_selinux(self):
        # close selinux under CentOS
        selinux = shell.call("egrep ^\\s*SELINUX= config|grep disable", False).strip('\n')
        if selinux:
            return
        logger.debug("we must close selinux.")
        # change /etc/selinux/config
        shell.call("sed -i \'s/^\\s*SELINUX=.*$/SELINUX=disabled/\' config")
        # shell.call("sed -i \'s/^\\s*GRUB_CMDLINE_LINUX=/{/selinux=0/!{s/\"\\s*$/ selinux=0\"/}}\' grub")
        # shell.call("sed -i \'1,${/^\\s*linux16 /{/selinux=0/!{s/\\s*$/ selinux=0/}}}\' grub.cfg")
        shell.call("virt-copy-in -a %s config /etc/selinux/" % self.image)
        # shell.call("virt-copy-in -a %s grub /etc/default/" % self.image)
        # shell.call("virt-copy-in -a %s grub.cfg /boot/grub2/" % self.image)

    def _check_parameters(self):
        if self.password is None or self.account is None or self.image is None:
            logger.warn("parameters must contain 3 parameters at least: account, password, qcow2")
            return False
        if not self._check_file("", self.image):
            return False
        return True
    def _is_centos(self):
        OSVersion = shell.call('virt-inspector -a %s |grep CentOS' % self.image, False)
        if not OSVersion:
            logger.debug("not CentOS, dont need to close selinux")
            return False
        return True

    def generate_passwd(self):
        if not self._check_parameters():
            return False
        version = self._is_centos()
        if version:
            try:
                shell.call("virt-copy-out -a %s /etc/shadow /etc/login.defs /etc/selinux/config ." % self.image)
                self._close_selinux()
            except Exception as e:
                logger.warn(e)
        else:
            shell.call("virt-copy-out -a %s /etc/shadow /etc/login.defs ." % self.image, False)
        if (not self._check_file("/etc/", "shadow")) or (not self._check_file("/etc/", "login.defs")):
            self._clean_up()
            return False
        try:
            self._replace_shadow()
        except Exception as e:
            logger.warn(e)
            self._clean_up()
            return False
        self._clean_up()
        return True

