from jinja2 import Template

from kvmagent import kvmagent
from kvmagent.plugins import host_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import log
from zstacklib.utils import thread
from zstacklib.utils import bash

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

class VmNic():
    def __init__(self, ip, mac):
        self.Ip = ip
        self.Mac = mac

class BridgeVmNic():
    def __init__(self, name):
        self.Name = name
        self.VmNics = []
        
class GracefulARP(kvmagent.KvmAgent):
    APPLY_GRACEFUL_ARP_PATH = "/flatnetworkprovider/garp/apply"
    RELEASE_GRACEFUL_ARP_PATH = "/flatnetworkprovider/garp/release"
    bridge_vmNics = {}

    def __init__(self):
        self.bridge_vmNics = {}
        self.bonds = host_plugin.HostPlugin.get_host_networking_bonds()

    def start(self):
        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(self.APPLY_GRACEFUL_ARP_PATH, self.apply_graceful_arp)
        http_server.register_async_uri(self.RELEASE_GRACEFUL_ARP_PATH, self.release_graceful_arp)
        thread.timer(5, self.monitor_bonding_master_change).start()

    def stop(self):
        pass

    @kvmagent.replyerror
    def apply_graceful_arp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._apply_graceful_arp(cmd.rebuild, cmd.infos)
        logger.debug("graceful arp info: %s", jsonobject.dumps(self.bridge_vmNics))
        return jsonobject.dumps(AgentRsp())

    @kvmagent.replyerror
    def release_graceful_arp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._release_graceful_arp(cmd.infos)
        logger.debug("graceful arp info: %s", jsonobject.dumps(self.bridge_vmNics))
        return jsonobject.dumps(AgentRsp())

    @lock.lock('gracefulArp')
    def _release_graceful_arp(self, infos):
        for info in infos:
            self._remove_info(info)

    @lock.lock('gracefulArp')
    def _apply_graceful_arp(self, rebuild, infos):
        if rebuild:
            self.bridge_vmNics = {}

        for eip in infos:
            self._add_info(eip)

    def _add_info(self, info):
        nic = VmNic(info.ip, info.mac)

        if info.bridgeName not in self.bridge_vmNics:
            bridge = BridgeVmNic(info.bridgeName)
            bridge.VmNics.append(nic)
            self.bridge_vmNics[info.bridgeName] = bridge
        else:
            if self.bridge_vmNics[info.bridgeName].VmNics is None:
                self.bridge_vmNics[info.bridgeName].VmNics = [nic]
            else:
                found = False
                for vNic in self.bridge_vmNics[info.bridgeName].VmNics:
                    if vNic.Mac == info.mac :
                        found = True
                        break
                if not found:
                    self.bridge_vmNics[info.bridgeName].VmNics.append(nic)

    def _remove_info(self, info):
        if info.bridgeName not in self.bridge_vmNics:
            return
        else:
            if self.bridge_vmNics[info.bridgeName].VmNics is not None:
                for vNic in self.bridge_vmNics[info.bridgeName].VmNics:
                    if vNic.Mac == info.mac:
                        self.bridge_vmNics[info.bridgeName].VmNics.remove(vNic)
                        break

        if self.bridge_vmNics[info.bridgeName].VmNics is None or len(self.bridge_vmNics[info.bridgeName].VmNics) == 0:
            del self.bridge_vmNics[info.bridgeName]


    def monitor_bonding_master_change(self):
        oldBonds = {}
        for b in self.bonds:
            oldBonds[b.bondingName] = b

        self.bonds = host_plugin.HostPlugin.get_host_networking_bonds()
        for b in self.bonds:
            if b.bondingName not in oldBonds:
                continue

            currentActiveNics = []
            for phyNic in b.slaves:
                if phyNic.master != b.bondingName:
                    logger.debug("master interface of physical %s is %s, not bonding interface %s"
                                 % (phyNic.interfaceName, phyNic.master, b.bondingName))
                    continue
                if phyNic.slaveActive:
                    currentActiveNics.append(phyNic.interfaceName)

            oldBond = oldBonds[b.bondingName]
            oldActiveNics = []
            for phyNic in oldBond.slaves:
                if phyNic.master != oldBond.bondingName:
                    logger.debug("master interface in old bond of physical %s is %s, not bonding interface %s"
                                 % (phyNic.interfaceName, phyNic.master, oldBond.bondingName))
                    continue
                if phyNic.slaveActive:
                    oldActiveNics.append(phyNic.interfaceName)

            if oldActiveNics != currentActiveNics:
                # active nic changed
                logger.debug("bonding interface %s active nic has been changed from %s to %s"
                             % (b.bondingName, oldActiveNics, currentActiveNics))
                self.sendGarp(b.bondingName)
            else:
                logger.debug("bonding interface %s active nic did not change: %s"
                             % (b.bondingName, currentActiveNics))

        thread.timer(5, self.monitor_bonding_master_change).start()

    @bash.in_bash
    @lock.lock('gracefulArp')
    def sendGarp(self, bondName):
        for bridgeNme in self.bridge_vmNics:
            bridge = self.bridge_vmNics[bridgeNme]
            name = bridgeNme.split("_")[1].strip()
            if bondName != name:
                continue

            cmds = ["ip add add 169.254.169.253 dev %s" % bridgeNme]
            for vmNic in bridge.VmNics:
                cmds.append(
                    "(nping --arp --arp-type ARP-request --arp-sender-mac {MAC} --arp-sender-ip {IP} --arp-target-ip {IP}  --arp-target-mac {MAC}  --source-mac {MAC} --dest-mac ff:ff:ff:ff:ff:ff --ether-type ARP -e {BRIDGE}  --dest-ip {IP} -q &)".format(
                        MAC=vmNic.Mac, IP=vmNic.Ip, BRIDGE=bridgeNme))

            cmd = ";".join(cmds)
            bash.bash_r(cmd)
