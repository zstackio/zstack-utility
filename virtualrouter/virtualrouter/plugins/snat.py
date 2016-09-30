'''

@author: Frank
'''
from virtualrouter import virtualrouter
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import lock
from zstacklib.utils import iptables

logger = log.get_logger(__name__)

class SnatInfo(object):
    def __init__(self):
        self.publicNicMac = None
        self.privateNicMac = None
        self.privateNicIp = None
        self.snatNetmask = None
        self.publicIp = None

class SetSNATCmd(virtualrouter.AgentCommand):
    def __init__(self):
        super(SetSNATCmd, self).__init__()
        self.natInfo = None

class SetSNATRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(SetSNATRsp, self).__init__()

class RemoveSNATRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(RemoveSNATRsp, self).__init__()

class SyncSNATRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(SyncSNATRsp, self).__init__()

class Snat(virtualrouter.VRAgent):
    SET_SNAT_PATH = "/setsnat"
    REMOVE_SNAT_PATH = "/removesnat"
    SYNC_SNAT_PATH = "/syncsnat"
    
    def start(self):
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.SET_SNAT_PATH, self.set_snat)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.REMOVE_SNAT_PATH, self.remove_snat)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.SYNC_SNAT_PATH, self.sync_snat)

    def _make_name(self, prefix, private_nic_name):
        return 'snat-{0}-{1}'.format(prefix, private_nic_name)

    def _make_forward_chain_name(self, private_nic_name):
        return self._make_name('fwd', private_nic_name)

    def make_snat_chain_name(self, private_nic_name):
        return self._make_name('snat', private_nic_name)

    def _create_snat(self, info, iptc):
        privnicname = linux.get_nic_name_by_mac(info.privateNicMac)
        if not privnicname:
            raise virtualrouter.VirtualRouterError('cannot get private nic name for mac[%s]' % info.privateNicMac)
        pubnicnames = linux.get_nic_names_by_mac(info.publicNicMac)
        if not pubnicnames:
            raise virtualrouter.VirtualRouterError('cannot get public nic name for mac[%s]' % info.publicNicMac)
        pubnicname = pubnicnames[0].split(':')[0]

        snat_chain_name = self.make_snat_chain_name(privnicname)
        iptc.add_rule('-A POSTROUTING -j %s' % snat_chain_name, iptc.NAT_TABLE_NAME)
        iptc.add_rule('-A {0} -o {1} -j SNAT --to-source {2}'.format(snat_chain_name, pubnicname, info.publicIp), iptc.NAT_TABLE_NAME)

        fwd_chain_name = self._make_forward_chain_name(privnicname)
        iptc.add_rule('-A FORWARD -i {0} -o {1} -j {2}'.format(pubnicname, privnicname, fwd_chain_name))
        iptc.add_rule('-A FORWARD -i {0} -o {1} -j {2}'.format(privnicname, pubnicname, fwd_chain_name))
        iptc.add_rule('-A FORWARD -i {0} -o {1} -j {2}'.format(privnicname, privnicname, fwd_chain_name))
        iptc.add_rule('-A {0} -j ACCEPT'.format(fwd_chain_name))


    def _remove_snat(self, info, iptc):
        privnicname = linux.get_nic_name_by_mac(info.privateNicMac)
        if not privnicname:
            raise virtualrouter.VirtualRouterError('cannot get private nic name for mac[%s]' % info.privateNicMac)

        snat_chain_name = self.make_snat_chain_name(privnicname)
        iptc.delete_chain(snat_chain_name, iptc.NAT_TABLE_NAME)
        fwd_chain_name = self._make_forward_chain_name(privnicname)
        iptc.delete_chain(fwd_chain_name)

    @virtualrouter.replyerror
    @lock.lock('snat')
    @lock.file_lock('iptables')
    def remove_snat(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RemoveSNATRsp()
        try:
            iptc = iptables.from_iptables_save()
            for info in cmd.natInfo:
                self._remove_snat(info, iptc)
            iptc.iptable_restore()
        except virtualrouter.VirtualRouterError as e:
            logger.warn(linux.get_exception_stacktrace())
            err = 'unable to remove snat, %s' % str(e)
            rsp.error = err
            rsp.success = False
        return jsonobject.dumps(rsp)


    @virtualrouter.replyerror
    @lock.lock('snat')
    @lock.file_lock('iptables')
    def set_snat(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetSNATRsp()
        
        try:
            iptc = iptables.from_iptables_save()
            self._create_snat(cmd.snat, iptc)
            iptc.iptable_restore()
        except virtualrouter.VirtualRouterError as e:
            logger.warn(linux.get_exception_stacktrace())
            err = 'unable to create snat, %s' % str(e)
            rsp.error = err
            rsp.success = False
        
        return jsonobject.dumps(rsp)

    @virtualrouter.replyerror
    @lock.lock('snat')
    @lock.file_lock('iptables')
    def sync_snat(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SyncSNATRsp()
        try:
            iptc = iptables.from_iptables_save()
            for info in cmd.snats:
                self._create_snat(info, iptc)
            iptc.iptable_restore()
        except virtualrouter.VirtualRouterError as e:
            logger.warn(linux.get_exception_stacktrace())
            err = 'unable to create snat, %s' % str(e)
            rsp.error = err
            rsp.success = False

        return jsonobject.dumps(rsp)

    def stop(self):
        pass
