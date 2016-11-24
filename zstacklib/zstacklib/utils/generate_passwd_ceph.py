'''
@author: mingjian
'''
import crypt
import os

from zstacklib.utils import log
from zstacklib.utils import shell

logger = log.get_logger(__name__)

class ChangePasswordError(Exception):
    '''test'''

class ChangePasswd(object):
    def __init__(self):
        self.password = None
        self.account = None
        self.root = None
        self.crypt = {'SHA512':crypt.METHOD_SHA512,
                      'SHA256': crypt.METHOD_SHA256,
                      'MD5': crypt.METHOD_MD5,
                      'CRYPT': crypt.METHOD_CRYPT}

    def _enable_md5_crypt(self):
        md5_crypt = shell.call("egrep ^\\s*MD5_CRYPT_ENAB %s/etc/login.defs" % self.root, False).strip('\n')
        if not md5_crypt:
            logger.debug("we must close MD5_CRYPT_ENAB.")
            shell.call("sed -i \'s/^\\s*MD5_CRYPT_ENAB\\s*no/MD5_CRYPT_ENAB yes/\' %s/etc/login.defs" % self.root)
    def _replace_shadow(self):
        crypt_method = shell.call('egrep ^\\s*ENCRYPT_METHOD %s/etc/login.defs|awk \'{print $2}\'' % self.root, False).strip('\n')
        pass_min_len = shell.call('egrep ^\\s*PASS_MIN_LEN %s/etc/login.defs|awk \'{print $2}\'' % self.root, False).strip('\n')
        if len(pass_min_len) > 0 and len(self.password) < int(pass_min_len):
            raise ChangePasswordError('pass_min_len is %s in this OS' % pass_min_len)
        if not self.crypt[crypt_method]:
            raise ChangePasswordError("not support crypt algorithm, please check ENCRYPT_METHOD in /etc/login.defs... ")
        logger.debug("crypt_method is: %s" % str(self.crypt[crypt_method]))
        crypt_passwd = crypt.crypt(self.password, crypt.mksalt(self.crypt[crypt_method]))
        replace_cmd = "egrep \"^%s:\" %s/etc/shadow|awk -v passwd='%s' -F \":\" \'{$2=passwd;OFS=\":\";print}\'" % (self.account, self.root, crypt_passwd)
        replace_passwd = shell.call(replace_cmd, False).strip('\n')
        if not replace_passwd:
            logger.warn('user [%s] not exist!' % self.account)
            raise ChangePasswordError('user [%s] not exist!' % self.account)
        logger.debug("crypt_passwd is: %s, replace_passwd is: %s" % (crypt_passwd, replace_passwd.replace('$', '\$')))
        sed_cmd = "sed -i \"s!^%s:.*\\$!%s!\" %s/etc/shadow" % (self.account, replace_passwd.replace('$', '\$'), self.root)
        shell.call(sed_cmd)
        self._enable_md5_crypt()
    def _close_selinux(self):
        # close selinux under CentOS
        if not os.path.isfile("%s/etc/selinux/config" % self.root):
            return
        selinux = shell.call("egrep ^\\s*SELINUX\\s*= %s/etc/config|grep disable" % self.root, False).strip()
        if selinux:
            return
        logger.debug("we must close selinux.")
        shell.call("sed -i \'s/^\\s*SELINUX\\s*=.*$/SELINUX=disabled/\' %s/etc/selinux/config" % self.root)

    def _check_parameters(self):
        logger.debug(self.password)
        logger.debug(self.account)
        logger.debug(self.root)
        if not self.password or not self.account or not self.root:
            logger.warn("parameters must contain 3 parameters at least: account, password, qcow2")
            return False
        if not os.path.isfile("%s/etc/shadow" % self.root):
            logger.warn("%s/etc/shadow not found" % self.root)
            return False
        return True
    def _is_centos(self):
        OSVersion = shell.call('cat /etc/system-release').strip()
        logger.debug("get OS info: %s" % OSVersion)
        if "CentOS" in OSVersion:
            logger.debug("if CentOS, we must close selinux")
            return True
        elif "Ubuntu" in OSVersion:
            return False
        else:
            raise ChangePasswordError("not support OS Version. Only support Ubuntu or CentOS")

    def generate_passwd(self):
        if not self._check_parameters():
            return False
        try:
            version = self._is_centos()
            if version:
                self._close_selinux()
            self._replace_shadow()
        except ChangePasswordError as e:
            raise e
        except Exception as e:
            logger.warn(e)
            return False
        return True

