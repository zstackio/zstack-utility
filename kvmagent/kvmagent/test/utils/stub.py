from zstacklib.test.utils import *  # DO NOT DELETE
from kvmagent import kvmagent
from zstacklib.utils import bash
from zstacklib.test.utils import env
import os


class PrepareOS(object):
    VAR_LIB_DIR = '/var/lib/zstack'
    USR_LOCAL_DIR = '/usr/local/zstack'

    def _delete_dnsmasq_binary(self):
        bash.bash_o('ps aux |grep dnsmasq.conf|awk \'{print $2}\'|xargs kill -9')

    def _copy_dnsmasq_binary(self):
        src = os.path.join(env.ZSTACK_UTILITY_SOURCE_DIR, 'kvmagent/ansible/dnsmasq')
        dst = os.path.join(self.USR_LOCAL_DIR)
        bash.bash_errorout('yes | cp %s %s' % (src, dst))

    def _create_dirs(self):
        dirs = [self.VAR_LIB_DIR, self.USR_LOCAL_DIR]

        for d in dirs:
            if not os.path.isdir(d):
                os.makedirs(d)

    def _close_firewall(self):
        bash.call_with_screen_output('iptables -F')

    def prepare(self):
        self._delete_dnsmasq_binary()
        self._create_dirs()
        self._close_firewall()

        self._copy_dnsmasq_binary()


def init_kvmagent():
    """
    init code for running kvm plugins
    """
    os.environ["COLUMNS"] = str(os.sysconf('SC_ARG_MAX'))
    PrepareOS().prepare()
    kvmagent.new_rest_service()
