import os

import tempfile
import shutil
import ast

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import http
from zstacklib.utils import ovn
from zstacklib.utils import bash
from zstacklib.utils import thread
from kvmagent.plugins.vm_plugin import get_running_vms

OVN_INSTALL_PACKAGE = '/network/ovn/install'
OVN_UNINSTALL_PACKAGE = '/network/ovn/uninstall'
OVN_START_SERVICE = '/network/ovn/start'
OVN_STOP_SERVICE = '/network/ovn/stop'
OVN_ADD_PORT = '/network/ovn/addport'
OVN_DEL_PORT = '/network/ovn/delport'
OVN_SYNC_PORT = '/network/ovn/syncports'
OVN_CHECK_LOCAL_PORT = '/network/ovn/checklocalport'
OVN_SET_REQUESTED_CHASSIS = '/network/ovn/setrequestedchassis'
OVN_SB_DBSERVER_LISTEN_PORT = '6642'
OVN_NB_DBSERVER_LISTEN_PORT = '6641'

logger = log.get_logger(__name__)

OVN_ROTATE_FILE = "/etc/logrotate.d/ovn"
OVS_ROTATE_FILE = "/etc/logrotate.d/openvswitch"

class OvnInstallPackageCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(OvnInstallPackageCmd, self).__init__()
        self.ovnControllerIp = None


class OvnInstallPackageResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(OvnInstallPackageResponse, self).__init__()


class OvnUninstallPackageCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(OvnUninstallPackageCmd, self).__init__()


class OvnUninstallPackageResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(OvnUninstallPackageResponse, self).__init__()


class OvnStartServiceCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(OvnStartServiceCmd, self).__init__()
        self.physicalInterfaceName = None
        self.bridgeName = None


class OvnStartServiceResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(OvnStartServiceResponse, self).__init__()


class OvnStopServiceCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(OvnStopServiceCmd, self).__init__()
        self.physicalInterfaceName = None
        self.bridgeName = None


class OvnStopServiceResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(OvnStopServiceResponse, self).__init__()


class OvnAddPortCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(OvnAddPortCmd, self).__init__()
        self.vSwitchType = None
        self.nicMap = None


class OvnAddPortResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(OvnAddPortResponse, self).__init__()


class OvnDelPortCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(OvnDelPortCmd, self).__init__()
        self.vSwitchType = None
        self.nicMap = None


class OvnDelPortResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(OvnDelPortResponse, self).__init__()


class OvnCheckLocalPortCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(OvnCheckLocalPortCmd, self).__init__()
        self.vSwitchType = None
        self.hostUuid = None


class OvnCheckLocalPortResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(OvnCheckLocalPortResponse, self).__init__()
        self.vmNicsMap = {}
        self.vnicVmMap = {}
        self.lspRequestedChassisMap = {}


class OvnSyncPortCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(OvnSyncPortCmd, self).__init__()
        self.vSwitchType = None
        self.nicMap = None
        self.vmUuid = None


class OvnSyncPortResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(OvnSyncPortResponse, self).__init__()


class OvnSetRequestedChassisCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(OvnSetRequestedChassisCmd, self).__init__()
        self.vSwitchType = None
        self.lspRequestedChassisMap = None


class OvnSetRequestedChassisResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(OvnSetRequestedChassisResponse, self).__init__()


class OvnNetworkPlugin(kvmagent.KvmAgent):

    @kvmagent.replyerror
    @bash.in_bash
    def install_ovn_package(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OvnInstallPackageResponse()

        controllerIp = cmd.ovnControllerIp
        '''
            4 bundle of packages need to be installed: ofed, dpdk, ovs, ovn
        '''
        packages = ["dpdk", "ovs", "ovn"]
        '''
        dpdkNics = ovn.getAllDpdkNic()
        for nic in dpdkNics:
            if nic.driver == "mlx5_core":
                # packages = ["ofed", "dpdk", "ovs", "ovn"]
                packages = ["dpdk", "ovs", "ovn"]
                break
        '''

        temp_dir = tempfile.mkdtemp()
        for pack in packages:
            # TODO: add arch and os
            r, _, e = bash.bash_roe("wget --recursive --no-parent -q --directory-prefix=%s http://%s/chassis/%s/"
                                    % (temp_dir, controllerIp, pack))
            if r != 0:
                rsp.success = False
                rsp.error = "fail to download package {} from ovn controller, because: {}".format(pack, e)
                break

            installFile = os.path.join(temp_dir, cmd.ovnControllerIp, "chassis", pack, "install.sh")
            r, _, e = bash.bash_roe("bash -x {}".format(installFile))
            if r != 0:
                rsp.success = False
                rsp.error = "fail to install package {} from ovn controller, because: {}".format(pack, e)
                break
            else:
                logger.debug("successfully install package {} from ovn controller".format(pack))

        shutil.rmtree(temp_dir)

        # change ovs-switchd and ovn-controller user to root
        bash.bash_roe("sed -i 's/^OVS_USER_ID=\"openvswitch:hugetlbfs\"/OVS_USER_ID=\"root:root\"/' "
                      "/etc/sysconfig/openvswitch")
        bash.bash_roe("sed -i 's/^OVN_USER_ID=\"openvswitch:openvswitch\"/OVN_USER_ID=\"root:root\"/' "
                      "/etc/sysconfig/ovn")
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def uninstall_ovn_package(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OvnUninstallPackageResponse()

        # we will not uninstall ovn package
        return jsonobject.dumps(rsp)

    """
    this api will be called on multiple scenarios:
    1. add host to sdn controller
    2. reconnect host which is added to sdn controller
    3. change host parameters
    """
    @kvmagent.replyerror
    @bash.in_bash
    def start_ovn_service(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OvnStartServiceResponse()

        # bond nics to dpdk driver
        r, e = ovn.changeNicToDpdkDriver(cmd.nicNamePciAddressMap)
        if r != 0:
            msg = "start ovn service, fail {err}".format(err=e)
            return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd, needRestore=False)

        vsctl = ovn.VsCtl()
        dpdkEnv = ovn.OvsDpdkEnv(cmd.lcores, cmd.pmdcores,
                                 int(cmd.hugePageNumber), int(cmd.hugePageSize), int(cmd.socketMem),
                                 cmd.nicNamePciAddressMap, cmd.nicRxQueueNumber, cmd.nicRxQueueDescNumber)

        if not vsctl.isOvsRunning():
            r, o, e = bash.bash_roe("systemctl restart ovsdb-server")
            if r != 0:
                msg = "restart ovsdb-server service, failed: {err}".format(err=e)
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)
            # clean vnic
            r, o, e = bash.bash_roe("ovs-vsctl --bare --columns=name list Port")
            if r != 0:
                msg = "get ovs port failed: {err}".format(err=e)
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)
            vms = get_running_vms()
            if len(vms) == 0:
                vnics = [vnic.strip() for vnic in o.split('\n') if vnic.strip()]
                for vnic in vnics:
                    if vnic.startswith("vnic"):
                        # delete vnic from ovs
                        r, o = bash.bash_ro("ovs-vsctl --no-wait --if-exists del-port br-int {vnic}".format(vnic=vnic))
                        if r != 0:
                            logger.warning("delete vnic:{vnic} failed: {err}".format(vnic=vnic, err=o))

            r, o, e = bash.bash_roe("systemctl restart openvswitch;systemctl restart ovn-controller")
            if r != 0:
                msg = "restart openvswitch service, failed: {err}".format(err=e)
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)

        err, socketMem = vsctl.getOvsOtherConfig("dpdk-socket-mem")
        if err or socketMem != cmd.socketMem:
            r = dpdkEnv.checkHugePagesMem()
            if r != 0:
                msg = "check ovs dpdk huge page mem error!"
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)

        err, dpdkInit = vsctl.getOvsOtherConfig("dpdk-init")
        if err or dpdkInit != 'true':
            r = vsctl.setOvsOtherConfig("dpdk-init", 'true')
            if r != 0:
                msg = "set ovs dpdk init failed!"
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)

        # TODO only dpdk is supported, ovs-kernel is not supported
        r, _, e = bash.bash_roe("ovs-vsctl --may-exist add-br br-int;"
                                "ovs-vsctl set bridge br-int datapath_type=netdev;")
        if r != 0:
            msg = "add br-int failed: {err}".format(err=e)
            return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)

        logger.debug("set ovs-ctl parameters")

        lMask, pmdMask = dpdkEnv.getCpuMask()
        err1, curLcoreMask = vsctl.getOvsOtherConfig("dpdk-lcore-mask")
        err2, curPmdMask = vsctl.getOvsOtherConfig("dpdk-pmd-mask")
        if err1 or err2 or pmdMask != curPmdMask or curLcoreMask != lMask:
            r = vsctl.bindCpuCores(lMask, pmdMask)
            if r != 0:
                msg = "set ovs dpdk lcore mask failed!"
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)

        # ovn-monitor-all = "true"
        # ovn-remote-probe-interval="100000"
        err1, ovn_monitor_all = vsctl.getOvsExternalIdsConfig("ovn-monitor-all")
        if err1 or ovn_monitor_all == 'false':
            r = vsctl.setOvsExternalIdsConfig("ovn-monitor-all", 'true')
            if r != 0:
                msg = "set ovs ovn-monitor-all failed!"
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)

        err1, ovn_remote_probe_interval = vsctl.getOvsExternalIdsConfig("ovn-remote-probe-interval")
        if err1 or ovn_remote_probe_interval != '100000':
            r = vsctl.setOvsExternalIdsConfig("ovn-remote-probe-interval", '100000')
            if r != 0:
                msg = "set ovs ovn-remote-probe-interval failed!"
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)

        # get interface of Port dpdkbond
        # check bond name and mode
        # check pci address
        # check queue num and queue desc num
        needAddUplink = True
        err, bondName = vsctl.getTableAttr("Port", "dpdkbond", "name")
        if not err and bondName == 'dpdkbond':
            err1, bondMode = vsctl.getTableAttr("Port", "dpdkbond", "bond_mode")
            err2, lacpMode = vsctl.getTableAttr("Port", "dpdkbond", "lacp")
            if not err1 and not err2 and bondMode == cmd.bondingMode and lacpMode == cmd.lacpMode:
                err, interfaces = vsctl.getTableAttr("Port", "dpdkbond", "interfaces")
                interfaces = [item.strip() for item in interfaces.strip("[]").split(",")]
                interfaces_names = []
                for interface in interfaces:
                    _, name = vsctl.getTableAttr("Interface", interface, "name")
                    interfaces_names.append(name)
                if set(interfaces_names) == set(cmd.nicNamePciAddressMap.__dict__.keys()):
                    for nicName, pciAddress in cmd.nicNamePciAddressMap.__dict__.items():
                        err, pci = vsctl.getTableAttr("Interface", nicName, "options:dpdk-devargs")
                        if err or pci != pciAddress:
                            needAddUplink = True
                            break
                        err1, nicRxQueueNum = vsctl.getNicRxQueueNumConfig(nicName)
                        err2, nicRxQueueDescNum = vsctl.getNicRxQueueDescNumConfig(nicName)
                        if err1 or err2 or nicRxQueueNum != cmd.nicRxQueueNumber or nicRxQueueDescNum != cmd.nicRxQueueDescNumber:
                            r = vsctl.setNicRxQueueConfig(nicName, cmd.nicRxQueueNumber, cmd.nicRxQueueDescNumber)
                            if r != 0:
                                msg = "set ovs dpdk rx queue config failed!"
                                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)
                        needAddUplink = False
        if needAddUplink:
            # create external bridge: br-phy
            logger.debug("began to create br-phy")
            r, e = vsctl.addUplink(cmd.nicNamePciAddressMap, cmd.bondingMode, cmd.lacpMode,
                                   cmd.ovnEncapIP, cmd.ovnEncapNetmask)
            if r != 0:
                msg = "add up link failed: %s!" % e
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)
            else:
                for nicName, pciAddress in cmd.nicNamePciAddressMap.__dict__.items():
                    err1, nicRxQueueNum = vsctl.getNicRxQueueNumConfig(nicName)
                    err2, nicRxQueueDescNum = vsctl.getNicRxQueueDescNumConfig(nicName)
                    if err1 or err2 or nicRxQueueNum != cmd.nicRxQueueNumber or nicRxQueueDescNum != cmd.nicRxQueueDescNumber:
                        r = vsctl.setNicRxQueueConfig(nicName, cmd.nicRxQueueNumber, cmd.nicRxQueueDescNumber)
                        if r != 0:
                            msg = "set ovs dpdk rx queue config failed!"
                            return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)

        err1, ovn_remote = vsctl.getOvsExternalIdsConfig("ovn-remote")
        err2, ovn_encap_ip = vsctl.getOvsExternalIdsConfig("ovn-encap-ip")
        err3, ovn_encap_type = vsctl.getOvsExternalIdsConfig("ovn-encap-type")
        err4, ovn_bridge_mappings = vsctl.getOvsExternalIdsConfig("ovn-bridge-mappings")
        err5, hostname = vsctl.getOvsExternalIdsConfig("hostname")

        if err1 or err2 or err3 or err4 or err5 or \
                ovn_remote != cmd.ovnRemoteConnection or \
                ovn_encap_ip != cmd.ovnEncapIP or \
                ovn_encap_type != cmd.ovnEncapType or \
                ovn_bridge_mappings != 'flat:{}'.format(cmd.brExName) or \
                hostname != cmd.hostIp:
            logger.debug("began to set ovs external-ids")
            r, _, e = bash.bash_roe("ovs-vsctl set Open_vSwitch . "
                                    "external-ids:ovn-remote={ovn_remote} "
                                    "external-ids:ovn-encap-ip={ovn_encap_ip} "
                                    "external-ids:ovn-encap-type={ovn_encap_type} "
                                    "external-ids:ovn-bridge-mappings=flat:{br_ex} "
                                    "external-ids:hostname={hostIp} "
                                    .format(ovn_remote=cmd.ovnRemoteConnection,
                                            ovn_encap_ip=cmd.ovnEncapIP,
                                            ovn_encap_type=cmd.ovnEncapType,
                                            br_ex=cmd.brExName,
                                            hostIp=cmd.hostIp))
            if r != 0:
                msg = "set ovs external-ids failed: %s!" % e
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)

        err, userspace_tso_enable = vsctl.getOvsOtherConfig('userspace-tso-enable')
        if err or userspace_tso_enable != 'true':
            r, _, e = bash.bash_roe("ovs-vsctl set Open_vSwitch . other_config:userspace-tso-enable=true")
            if r != 0:
                msg = "set ovs config userspace-tso-enable failed: {err}".format(err=e)
                return self._logRestoreNicDriverMakeRsp(rsp, msg, cmd)

        return jsonobject.dumps(rsp)

    def _logRestoreNicDriverMakeRsp(self, rsp, msg, cmd, needRestore=True):
        if needRestore:
            ovn.restoreNicDriver(cmd.nicNameDriverMap, cmd.nicNameDriverMap)
        logger.debug(msg)
        rsp.success = False
        rsp.error = msg
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def stop_ovn_service(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OvnStopServiceResponse()

        r, _, e = bash.bash_roe("systemctl stop ovsdb-server;"
                                "systemctl stop openvswitch;"
                                "systemctl stop ovn-controller")
        if r != 0:
            rsp.success = False
            rsp.error = "stop ovn service, fail {err}".format(err=e)

        logger.debug("starting change nic driver")
        r, e = ovn.restoreNicDriver(cmd.nicNamePciAddressMap, cmd.nicNameDriverMap)
        if r != 0:
            rsp.success = False
            rsp.error = e
        else:
            logger.debug("successfully change nic driver")

        bash.bash_roe("mv /etc/openvswitch/conf.db /etc/openvswitch/conf.db.bak")

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def ovn_add_port(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        logger.debug("cmd: %s: %s" % (cmd, cmd.__dict__))
        logger.debug("cmd nicMap: %s: %s" % (cmd.nicMap, cmd.nicMap.__dict__))
        vsctl = ovn.VsCtl()
        
        if cmd.sync:
            oldNics = vsctl.getVnics()
            
            for oldNic in oldNics:
                found = False
                for nicName, nicUuid in cmd.nicMap.__dict__.items():
                    if oldNic == nicName:
                        found = True
                        break
                        
                if not found:
                    vsctl.delVnic(oldNic)

        reinstall = False
        if cmd.reInstall is not None:
            reinstall = cmd.reInstall

        for nicName, nicUuid in cmd.nicMap.__dict__.items():
            vm_uuid = cmd.nicVmInstanceUuidMap.__dict__.get(nicName, None)
            vsctl.addVnic(nicName, nicUuid, vm_uuid, reinstall)
        rsp = OvnAddPortResponse()

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def ovn_del_port(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OvnDelPortResponse()

        logger.debug("cmd: %s: %s" % (cmd, cmd.__dict__))
        logger.debug("cmd nicMap: %s: %s" % (cmd.nicMap, cmd.nicMap.__dict__))
        vsctl = ovn.VsCtl()
        for nicName, _ in cmd.nicMap.__dict__.items():
            vsctl.delVnic(nicName)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def ovn_check_local_port(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OvnCheckLocalPortResponse()

        vsctl = ovn.VsCtl()
        if not vsctl.isOvsRunning():
            r = bash.bash_r("systemctl restart openvswitch && systemctl restart ovn-controller")
            if r != 0:
                rsp.success = False
                rsp.error = "restart openvswitch service failed"
                return jsonobject.dumps(rsp)

        localPorts = vsctl.getVnicsAndVmUuid()
        rsp.vnicVmMap = localPorts

        vms = get_running_vms()
        vmNicsMap = {}

        for vm in vms:
            nics = vsctl.getVnicsByVmUuid(vm.uuid)
            if len(nics) == 0:
                vmNicsMap[vm.uuid] = []
            vmNicsMap[vm.uuid] = nics
        rsp.vmNicsMap = vmNicsMap

        allVnics = []
        for nics in vmNicsMap.values():
            allVnics.extend(nics)

        vnicsIfaceId = vsctl.getVnicsIfaceId(allVnics)
        lspRequestedChassisMap = {}
        r, sb_ovn_remote = bash.bash_ro('ovs-vsctl get Open_vSwitch . external_ids:ovn-remote')
        if r != 0:
            rsp.success = False
            rsp.error = "Failed to get ovn-remote from ovs-vsctl"
            return jsonobject.dumps(rsp)
        sb_ovn_remote = sb_ovn_remote.strip().strip('"')
        errStr = []
        for lsp in vnicsIfaceId.values():
            r, requestedChassis = bash.bash_ro('ovn-sbctl --db=%s  --column=requested_chassis find port_binding logical_port=%s | awk \'{print $3}\'' % (sb_ovn_remote, lsp))
            if r != 0:
                errStr.append("Failed to get requested_chassis for lsp %s" % lsp)
                continue
            if requestedChassis == "":
                continue
            requestedChassis = ast.literal_eval(requestedChassis.strip())
            if not requestedChassis:
                continue
            lspRequestedChassisMap[lsp] = requestedChassis
        rsp.lspRequestedChassisMap = lspRequestedChassisMap

        if len(errStr) > 0:
            rsp.success = False
            rsp.error = ";".join(errStr)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def ovn_sync_ports(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OvnSyncPortResponse()

        logger.debug("cmd: %s: %s" % (cmd, cmd.__dict__))
        logger.debug("cmd nicMap: %s: %s" % (cmd.nicMap, cmd.nicMap.__dict__))
        vsctl = ovn.VsCtl()

        localVnics = vsctl.getVnicsByVmUuid(cmd.vmUuid)

        for localVnic in localVnics:
            if localVnic not in cmd.nicMap.__dict__.keys():
                vsctl.delVnic(localVnic)

        for nicName, nicUuid in cmd.nicMap.__dict__.items():
            if nicName not in localVnics:
                vsctl.addVnic(nicName, nicUuid, cmd.vmUuid, False)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @bash.in_bash
    def ovn_set_requested_chassis(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = OvnSetRequestedChassisResponse()

        logger.debug("cmd: %s: %s" % (cmd, cmd.__dict__))
        logger.debug("cmd lspRequestedChassisMap: %s: %s" % (cmd.lspRequestedChassisMap, cmd.lspRequestedChassisMap.__dict__))
        errStr = []
        sb_ovn_remote = bash.bash_o('ovs-vsctl get Open_vSwitch . external_ids:ovn-remote').strip().strip('"')
        nb_ovn_remote = sb_ovn_remote.replace(OVN_SB_DBSERVER_LISTEN_PORT, OVN_NB_DBSERVER_LISTEN_PORT)
        for lsp, mgmtIpList in cmd.lspRequestedChassisMap.__dict__.items():
            chassis_names = []
            for mgmtIp in mgmtIpList:
                r, chassis_name = bash.bash_ro('ovn-sbctl --db=%s  --column=name find chassis hostname=%s | awk \'{print $3}\'' % (sb_ovn_remote, mgmtIp))
                if r != 0:
                    rsp.success = False
                    errStr.append("Failed to find chassis hostname %s" % mgmtIp)
                    continue
                chassis_names.append(chassis_name.strip().strip('"'))
            if len(chassis_names) == 0:
                r = bash.bash_r('ovn-nbctl --wait=hv --db=%s remove Logical_Switch_Port %s options requested-chassis' % (nb_ovn_remote, lsp))
            elif len(chassis_names) == 1:
                r = bash.bash_r('ovn-nbctl --wait=hv --db=%s lsp-set-options %s requested-chassis=%s' % (nb_ovn_remote, lsp, chassis_names[0]))
            else:
                r = bash.bash_r('ovn-nbctl --wait=hv --db=%s lsp-set-options %s requested-chassis=%s,%s' % (nb_ovn_remote, lsp, chassis_names[0], chassis_names[1]))
            if r != 0:
                rsp.success = False
                errStr.append("Failed to set requested_chassis:%s for lsp:%s" % (chassis_names, lsp))
        if len(errStr) > 0:
            rsp.error = ";".join(errStr)
        return jsonobject.dumps(rsp)

    def start(self):

        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(
            OVN_INSTALL_PACKAGE, self.install_ovn_package)
        http_server.register_async_uri(
            OVN_UNINSTALL_PACKAGE, self.uninstall_ovn_package)
        http_server.register_async_uri(
            OVN_START_SERVICE, self.start_ovn_service)
        http_server.register_async_uri(
            OVN_STOP_SERVICE, self.stop_ovn_service)
        http_server.register_async_uri(
            OVN_ADD_PORT, self.ovn_add_port)
        http_server.register_async_uri(
            OVN_DEL_PORT, self.ovn_del_port)
        http_server.register_async_uri(
            OVN_SET_REQUESTED_CHASSIS, self.ovn_set_requested_chassis)
        http_server.register_async_uri(
            OVN_SYNC_PORT, self.ovn_sync_ports)
        http_server.register_async_uri(
            OVN_CHECK_LOCAL_PORT, self.ovn_check_local_port)

        self.register_ovn_logRotate()

    def stop(self):
        http.AsyncUirHandler.STOP_WORLD = True

    def _create_ovn_rotate_file(self):
        content = """/var/log/ovn/*.log {
#    su openvswitch openvswitch
    daily
    size 50M
    rotate 30
    compress
    sharedscripts
    missingok
    postrotate
        # Tell OVN daemons to reopen their log files
        if [ -d /var/run/ovn ]; then
            for ctl in /var/run/ovn/*.ctl; do
                ovs-appctl -t "$ctl" vlog/reopen 2>/dev/null || :
            done
        fi
    endscript
}
"""

        with open(OVN_ROTATE_FILE, 'w') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(OVN_ROTATE_FILE, 0o644)

        content = """/var/log/openvswitch/*.log {
#    su openvswitch hugetlbfs
    daily
    size 50M
    rotate 30
    compress
    sharedscripts
    missingok
    postrotate
        # Tell Open vSwitch daemons to reopen their log files
        if [ -d /run/openvswitch ]; then
            for ctl in /run/openvswitch/*.ctl; do
                ovs-appctl -t "$ctl" vlog/reopen 2>/dev/null || :
            done
        fi
    endscript
}

        """

        with open(OVS_ROTATE_FILE, 'w') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(OVS_ROTATE_FILE, 0o644)

    def register_ovn_logRotate(self):
        def ovn_logRotate():
            bash.bash_r("logrotate -f " + OVS_ROTATE_FILE)
            bash.bash_r("logrotate -f " + OVN_ROTATE_FILE)

            thread.timer(24*3600, ovn_logRotate).start()

        self._create_ovn_rotate_file()
        thread.timer(60, ovn_logRotate).start()
