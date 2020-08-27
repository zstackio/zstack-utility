import os.path
import platform

from zstacklib.utils import jsonobject
from kvmagent import kvmagent
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import http
from zstacklib.utils import misc

logger = log.get_logger(__name__)

class PerformanceTunePlugin(kvmagent.KvmAgent):

    @misc.ignoreerror
    def start(self):
        self.set_conntrack_table_size()

    def stop(self):
        pass

    def __check_module(self, module_name):
        cmd = "lsmod | grep ^" + module_name
        ret = shell.run(cmd)
        return ret

    def set_conntrack_table_size(self):

        # check the conntrack module
        if self.__check_module("nf_conntrack"):
            warn = 'could not find conntrack module'
            logger.warn(warn)
            return

        '''
        we want conntrack_table_size = 2G
        SIZEOF_LIST = 16, SIZEOF_CONNTRACK = 376
        conntrack_table_size = buckets * SIZEOF_LIST + totalsize * SIZEOF_CONNTRACK
        for more informations: http://confluence.zstack.io/pages/viewpage.action?pageId=87720365
        '''
        buckets = 710656
        totalsize = buckets * 8

        release = platform.release().split("-")[0].split(".")
        version = float(release[0] + '.' + release[1])
        
        # set buckets
        if  version > 4.8:
            shell.call('echo {} > /proc/sys/net/netfilter/nf_conntrack_buckets'.format(buckets))
        else:
            shell.call('echo {} > /sys/module/nf_conntrack/parameters/hashsize'.format(buckets))

        # set totalsize
        shell.call('echo {} > /proc/sys/net/netfilter/nf_conntrack_max'.format(totalsize))