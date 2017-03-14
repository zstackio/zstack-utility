__author__ = 'frank'


from virtualrouter import virtualrouter
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import lock
import zstacklib.utils.iptables as iptables

logger = log.get_logger(__name__)

class CreateEipRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(CreateEipRsp, self).__init__()

class RemoveEipRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(RemoveEipRsp, self).__init__()

class SyncEipRsp(virtualrouter.AgentResponse):
    def __init__(self):
        super(SyncEipRsp, self).__init__()

class Eip(virtualrouter.VRAgent):
    VR_CREATE_EIP = "/createeip"
    VR_REMOVE_EIP = "/removeeip"
    VR_SYNC_EIP = "/synceip"

    def _make_chain_name(self, vip_nic_name, priv_nic_name, prefix):
        name = 'eip-{0}-{1}-{2}'.format(prefix, vip_nic_name, priv_nic_name)
        if len(name) >= 28:
            name = name[0:26]
        return name

    def _make_dnat_name(self, vip_nic_name, priv_nic_name):
        return self._make_chain_name(vip_nic_name, priv_nic_name, 'dnat')

    def _make_snat_name(self, vip_nic_name, priv_nic_name):
        return self._make_chain_name(vip_nic_name, priv_nic_name, 'snat')

    def _make_gateway_snat_name(self, vip_nic_name, priv_nic_name):
        return self._make_chain_name(vip_nic_name, priv_nic_name, 'snat-gw')

    def _make_fwd_name(self, vip_nic_name, priv_nic_name):
        return self._make_chain_name(vip_nic_name, priv_nic_name, 'fwd')

    def _get_vip_nic_name_from_chain_name(self, chain_name):
        if not chain_name.startswith('eip'):
            return None

        return chain_name.split('-')[2]

    def _create_eip(self, eip):
        ipt = iptables.from_iptables_save()
        private_nic_name = linux.get_nic_name_by_mac(eip.privateMac)
        vip_nic_name = linux.get_nic_name_by_ip(eip.vipIp)
        guest_ip = eip.guestIp
        vip = eip.vipIp

        dnat_name = self._make_dnat_name(vip_nic_name, private_nic_name)
        snat_name = self._make_snat_name(vip_nic_name, private_nic_name)
        fwd_name = self._make_fwd_name(vip_nic_name, private_nic_name)

        #def check_eip(table):
            #if not table:
                #return

            #for chain in table.children:
                #vip_nic = self._get_vip_nic_name_from_chain_name(chain.name)
                #if vip_nic == vip_nic_name:
                    #raise virtualrouter.VirtualRouterError('eip[%s] has been occupied, this is an internal error' % vip)

        #check_eip(ipt.get_table(ipt.NAT_TABLE_NAME))
        #check_eip(ipt.get_table(ipt.FILTER_TABLE_NAME))

        order = 999
        ipt.add_rule('-A PREROUTING -d {0} -j {1}'.format(vip, dnat_name), ipt.NAT_TABLE_NAME, order=order)
        ipt.add_rule('-A {0} -j DNAT --to-destination {1}'.format(dnat_name, guest_ip), ipt.NAT_TABLE_NAME, order=order)

        ipt.add_rule('-A FORWARD -i {0} -o {1} -j {2}'.format(vip_nic_name, private_nic_name, fwd_name), order=order)
        ipt.add_rule('-A FORWARD -i {0} -o {1} -j {2}'.format(private_nic_name, vip_nic_name, fwd_name), order=order)
        ipt.add_rule('-A {0} -j ACCEPT'.format(fwd_name), order=order)

        ipt.add_rule('-A POSTROUTING -s {0} -j {1}'.format(guest_ip, snat_name), ipt.NAT_TABLE_NAME, order=order)
        ipt.add_rule('-A {0} -j SNAT --to-source {1}'.format(snat_name, vip), ipt.NAT_TABLE_NAME, order=order)

        if eip.snatInboundTraffic:
            gw_snat_name = self._make_gateway_snat_name(vip_nic_name, private_nic_name)
            guest_gw_ip = linux.get_ip_by_nic_name(private_nic_name)
            ipt.add_rule('-A POSTROUTING -d {0} -j {1}'.format(guest_ip, gw_snat_name), ipt.NAT_TABLE_NAME, order=order)
            ipt.add_rule('-A {0} -j SNAT --to-source {1}'.format(gw_snat_name, guest_gw_ip), ipt.NAT_TABLE_NAME, order=order)

        ipt.iptable_restore()
        logger.debug('successfully created eip[{0}] to guest ip[{1}] from device[{2}] to device[{3}]'.format(vip, guest_ip, vip_nic_name, private_nic_name))

    @virtualrouter.replyerror
    @lock.lock('eip')
    @lock.file_lock('/run/xtables.lock')
    def create_eip(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateEipRsp()

        try:
            self._create_eip(cmd.eip)
        except virtualrouter.VirtualRouterError as e:
            logger.warning(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    def _remove_eip(self, eip):
        ipt = iptables.from_iptables_save()
        private_nic_name = linux.get_nic_name_by_mac(eip.privateMac)
        assert private_nic_name, "cannot find private nic by MAC[%s]" % eip.privateMac
        vip_nic_name = linux.get_nic_name_by_ip(eip.vipIp)
        assert vip_nic_name, "cannot find vip nic by IP[%s]" % eip.vipIp
        guest_ip = eip.guestIp
        vip = eip.vipIp

        dnat_name = self._make_dnat_name(vip_nic_name, private_nic_name)
        snat_name = self._make_snat_name(vip_nic_name, private_nic_name)
        fwd_name = self._make_fwd_name(vip_nic_name, private_nic_name)
        gw_snat_name = self._make_gateway_snat_name(vip_nic_name, private_nic_name)

        ipt.delete_chain(dnat_name, ipt.NAT_TABLE_NAME)
        ipt.delete_chain(snat_name, ipt.NAT_TABLE_NAME)
        ipt.delete_chain(gw_snat_name, ipt.NAT_TABLE_NAME)
        ipt.delete_chain(fwd_name)

        ipt.iptable_restore()
        logger.debug('successfully deleted eip[{0}] to guest ip[{1}] from device[{2}] to device[{3}]'.format(vip, guest_ip, vip_nic_name, private_nic_name))

    @virtualrouter.replyerror
    @lock.lock('eip')
    @lock.file_lock('/run/xtables.lock')
    def remove_eip(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RemoveEipRsp()

        self._remove_eip(cmd.eip)

        return jsonobject.dumps(rsp)

    @virtualrouter.replyerror
    @lock.lock('eip')
    @lock.file_lock('/run/xtables.lock')
    def sync_eip(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SyncEipRsp()

        def remove_eip_chain(table):
            for c in table.children:
                if c.name.startswith('eip-'):
                    c.delete()

        ipt = iptables.from_iptables_save()
        nat = ipt.get_table(ipt.NAT_TABLE_NAME)
        if nat:
            remove_eip_chain(nat)
        filter_table = ipt.get_table(ipt.FILTER_TABLE_NAME)
        if filter_table:
            remove_eip_chain(filter_table)
        ipt.iptable_restore()

        try:
            for eip in cmd.eips:
                self._create_eip(eip)
        except virtualrouter.VirtualRouterError as e:
            logger.warning(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    def start(self):
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.VR_CREATE_EIP, self.create_eip)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.VR_REMOVE_EIP, self.remove_eip)
        virtualrouter.VirtualRouter.http_server.register_async_uri(self.VR_SYNC_EIP, self.sync_eip)

    def stop(self):
        pass
