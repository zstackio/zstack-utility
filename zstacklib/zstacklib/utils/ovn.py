'''

@author: haibiao.xiao
'''
import os
import yaml
import glob
import uuid
import re
import shlex
import simplejson
from enum import Enum, unique

from zstacklib.utils import log
from zstacklib.utils import bash
from zstacklib.utils import iproute
from zstacklib.utils import linux

logger = log.get_logger(__name__)

AppCtlBin = "/usr/bin/ovn-appctl"
CtlBin = "/usr/bin/ovs-vsctl "
DevBindBin = "/usr/bin/dpdk-devbind.py "
OVS_DPDK_SRC_PATH = "/var/run/openvswitch/"

VSWITCHD_PID_PATH = '/var/run/openvswitch/ovs-vswitchd.pid'
OVSDB_PID_PATH = '/var/run/openvswitch/ovsdb-server.pid'
OVN_CONTROLLER_PID_PATH = '/run/ovn/ovn-controller.pid'

BONDING_MODE_AB = "active-backup"
BONDING_MODE_SLB = "balance-slb"
BONDING_MODE_TCP = "balance-tcp"

LACP_MODE_OFF = "off"
LACP_MODE_ACTIVE = "active"
LACP_MODE_PASSIVE = "passive"

SAFE_IFACE_ID = re.compile(r'^[A-Za-z0-9_.:-]+$')


def getInterfaceId(nicName, nicUuid, ifaceId=None):
    if ifaceId is not None and str(ifaceId).strip() != "":
        return normalizeInterfaceId(ifaceId)
    return "{}_{}".format(nicName, nicUuid)


def normalizeInterfaceId(ifaceId):
    ifaceId = str(ifaceId).strip()
    if not SAFE_IFACE_ID.match(ifaceId):
        raise ValueError("invalid ifaceId: %s" % ifaceId)
    return ifaceId


class OvsError(Exception):
    '''ovs error'''


class OvsDpdkNic:
    def __init__(self):
        self.name = ""
        self.pciAddress = ""
        self.driver = ""
        self.oldDriver = ""


@bash.in_bash
def getAllDpdkNic():
    ret = []
    r, o, e = bash.bash_roe(DevBindBin + " --status-dev net | grep drv= | grep -v 'Virtual Function'")
    if r != 0:
        logger.debug(DevBindBin + " --status-dev net | grep drv=, failed {err}".format(err=e))
        return ret

    lines = o.split("\n")
    for line in lines:
        line = line.strip()
        if line == "":
            continue

        nic = OvsDpdkNic()
        items = line.split(" ")
        nic.pciAddress = items[0]
        for item in items:
            if item.startswith("if="):
                nic.name = item.split("=")[1]
            elif item.startswith("drv="):
                nic.driver = item.split("=")[1]
            elif item.startswith("unused="):
                oldDrivers = item.split("=")[1]
                nic.oldDriver = oldDrivers.split(",")[0]

        logger.debug("dpdk nic{} name: {}, driver: {}, unused:{}"
                     .format(nic.pciAddress, nic.name, nic.driver, nic.oldDriver))
        ret.append(nic)

    return ret


def getAllVfioPciNic():
    ret = []
    dpdkNics = getAllDpdkNic()
    for nic in dpdkNics:
        if nic.driver == "vfio-pci" or nic.driver == "uio_pci_generic":
            ret.append(nic)

    return ret

@bash.in_bash
def delVnicFromOvsByVmUuidIfExist(vmUuid, brName="br-int"):
    try:
        # if CtlBin not exists, return directly
        if not os.path.exists(CtlBin.strip()):
            return
        # find all vnic ports by vm uuid
        vm_uuid = vmUuid.replace('-', '')
        command = CtlBin + "--bare --columns=name find Interface external_ids:vm-uuid={}".format(vm_uuid)
        r, o = bash.bash_ro(command)
        if r != 0:
            logger.warn("failed to get vnic port list for vm[uuid:%s], command[%s], output[%s]" % (vm_uuid, command, o))
            return

        vnic_names = o.splitlines()
        for vnic_name in vnic_names:
            vnic_name = vnic_name.strip()
            if not vnic_name:
                continue
            logger.info('clean dpdk vnic port:%s from ovs' % vnic_name)

            bash.bash_o(CtlBin + '--if-exists del-port {} {}'.format(brName, vnic_name))
    except Exception as err:
        logger.exception("Delete vnic for bridge {} failed. {}".format(brName, err))


@bash.in_bash
def changeNicToDpdkDriver(nicNamePciAddressMap):
    # uio_pci_generic is used for nest virtual
    dpdkDriver = "vfio-pci"
    ret = bash.bash_r("lscpu | grep -i \"Hypervisor vendor\"")
    if ret == 0:
        dpdkDriver = "uio_pci_generic"

    ret, _, e = bash.bash_roe("modprobe {driver}".format(driver=dpdkDriver))
    if ret != 0:
        return ret, e

    dpdkNics = getAllDpdkNic()
    targetDpdkNic = []

    logger.debug("starting change nic driver")

    for nicName, pciAddress in nicNamePciAddressMap.__dict__.items():
        found = False
        driver = ""
        for dpdkNic in dpdkNics:
            if dpdkNic.pciAddress == pciAddress:
                found = True
                driver = dpdkNic.driver
                targetDpdkNic.append(dpdkNic)
                break

        if not found:
            return 1, "nic [pci address: {}] is not found by dpdk-devbind.py".format(pciAddress)

        if driver == "mlx5_core":
            # mellanox nic(like cx-5) does not need vfio driver
            continue

        if driver == dpdkDriver:
            logger.debug("nic {} already bond to dpdk driver{}".format(nicName, dpdkDriver))
            continue

        # for nested vm, the driver is should be uio_pci_generic
        r, _, e = bash.bash_roe(DevBindBin + " -b {driver} {pciAddress}"
                                .format(driver=dpdkDriver, pciAddress=pciAddress))
        if r != 0:
            return r, e

        logger.debug("change change nic [pci address: {}] driver to {}".format(pciAddress, dpdkDriver))

    return 0, ""


@bash.in_bash
def restoreNicDriver(pciAddressList):
    logger.debug("starting restore nic driver {}".format(simplejson.dumps(pciAddressList)))
    if not pciAddressList:
        return 0, ""

    dpdkNics = getAllDpdkNic()
    restoreTargets = []
    errors = []

    for pciAddress in pciAddressList:
        found = False
        targetNic = OvsDpdkNic()
        for dpdkNic in dpdkNics:
            if dpdkNic.pciAddress == pciAddress:
                found = True
                targetNic = dpdkNic
                break

        if not found:
            errors.append("nic [pci address: {}] is not found by dpdk-devbind.py before restore"
                          .format(pciAddress))
            continue

        # if nis is not use vfio, nothing to to
        if targetNic.driver != "vfio-pci" and targetNic.driver != "uio_pci_generic":
            logger.debug("nic [pci address: {}] already uses kernel driver {}"
                         .format(pciAddress, targetNic.driver))
            continue

        driverType = "virtio-pci" if targetNic.driver == "uio_pci_generic" else targetNic.oldDriver
        if not driverType:
            errors.append("nic [pci address: {}] has no original driver to restore"
                          .format(pciAddress))
            continue

        cmd = DevBindBin + " -u {pciAddress};".format(pciAddress=pciAddress)
        cmd = cmd + DevBindBin + " -b {driver} {pciAddress}".format(driver=driverType, pciAddress=pciAddress)
        logger.debug("cmd: {}".format(cmd))
        r, _, e = bash.bash_roe(cmd)
        if r != 0:
            errors.append(
                "change change nic [pci address: {}] driver to {} failed: {}"
                .format(pciAddress, driverType, e))
        else:
            logger.debug(
                "successfully change change nic [pci address: {}] driver to {}"
                .format(pciAddress, driverType))
            restoreTargets.append((pciAddress, driverType))

    # getAllDpdkNic does not return the nic name, so call it again
    dpdkNics = getAllDpdkNic()
    for pciAddress, expectedDriver in restoreTargets:
        found = False
        targetNic = OvsDpdkNic()
        for dpdkNic in dpdkNics:
            if dpdkNic.pciAddress == pciAddress:
                found = True
                targetNic = dpdkNic
                break

        if not found:
            errors.append("nic [pci address: {}] cannot be verified after restore"
                          .format(pciAddress))
            continue

        if targetNic.driver == "vfio-pci" or targetNic.driver == "uio_pci_generic":
            errors.append("nic [pci address: {}] is still bound to driver {} after restore"
                          .format(pciAddress, targetNic.driver))
            continue

        if targetNic.driver != expectedDriver:
            errors.append("nic [pci address: {}] restored to unexpected driver {}, expected {}"
                          .format(pciAddress, targetNic.driver, expectedDriver))
            continue

        if not targetNic.name:
            errors.append("nic [pci address: {}] has no interface name after restore"
                          .format(pciAddress))
            continue

        r, _, e = bash.bash_roe("ip link set up dev {}".format(targetNic.name))
        if r != 0:
            errors.append("set nic [pci address: {}] link up failed: {}"
                          .format(pciAddress, e))

    if errors:
        err = "; ".join(errors)
        logger.error("restore nic driver failed: {}".format(err))
        return 1, err

    return 0, ""

class ControllerCtl(object):
    def __init__(self):
        pass

    @bash.in_bash
    def resetOvnControllerClusterIndex(self):
        ret = 0
        try:
            cmd = '{cmd} -t ovn-controller sb-cluster-state-reset'.format(cmd=AppCtlBin)
            ret = bash.bash_r(cmd)
        except Exception as err:
            logger.error("ovn controller reset idl cache error when switching "
                         "to new database, %s", str(err))
            ret = 1
        finally:
            return ret

class VsCtl(object):
    def __init__(self):
        pass

    @bash.in_bash
    def getVnics(self, brName="br-int"):
        try:
            vnics = []
            cmd = CtlBin + 'list-ports {brName}'.format(brName=brName)
            _, o, _ = bash.bash_roe(cmd)
            o = o.strip()
            if o == "":
                return vnics

            lines = o.split("\n")
            for line in lines:
                line = line.strip()
                if line == "":
                    continue

                if line.startswith("vnic"):
                    vnics.append(line)

            return vnics
        except Exception as err:
            logger.error(
                "Get port for bridge {} failed. {}".format(brName, err))
            return []

    @bash.in_bash
    def getVnicsAndVmUuid(self, brName="br-int"):
        try:
            vnics = {}
            cmd = CtlBin + 'list-ports {brName}'.format(brName=brName)
            _, o, _ = bash.bash_roe(cmd)
            o = o.strip()
            if o == "":
                return vnics

            lines = o.split("\n")
            for line in lines:
                line = line.strip()
                if line == "":
                    continue

                if line.startswith("vnic"):
                    r, vmUuid, e = bash.bash_roe(
                        CtlBin + "get Interface {} external_ids:vm-uuid".format(line))
                    if r != 0:
                        logger.debug("get vm uuid of vnic {} failed: {}".format(line, e))
                        continue
                    vmUuid = vmUuid.strip("\n").strip('"')
                    vnics[line] = vmUuid

            return vnics
        except Exception as err:
            logger.error(
                "Get port from bridge {} failed. {}".format(brName, err))
            return {}


    @bash.in_bash
    def getVnicsIfaceId(self, vnics, brName="br-int"):
        try:
            ret = {}
            for vnic in vnics:
                iface_id = bash.bash_o('ovs-vsctl get Interface %s external_ids:iface-id' % vnic).strip().strip('"')
                ret[vnic] = iface_id
            return ret
        except Exception as err:
            logger.error(
                "Get interface id from bridge {} failed. {}".format(brName, err)
            )
            return {}

    @bash.in_bash
    def getVnicsByVmUuid(self, vmUuid, brName="br-int"):
        try:
            vnics = []
            vm_uuid = vmUuid.replace('-', '')
            cmd = CtlBin + "--bare --columns=name find Interface external_ids:vm-uuid={}".format(vm_uuid)
            r, o, e = bash.bash_roe(cmd)
            if r != 0:
                logger.debug("failed to get vnic port list for vm[uuid:%s], command[%s], output[%s]" % (vm_uuid, cmd, e))
                return vnics

            lines = o.split("\n")
            for line in lines:
                line = line.strip()
                if line == "":
                    continue

                if line.startswith("vnic"):
                    vnics.append(line)

            return vnics
        except Exception as err:
            logger.error(
                "get port from bridge {} failed. {}".format(brName, err))
            return []

    @bash.in_bash
    def addVnic(self, nicName, nicUuid, vmUuid, reinstall=False, brName="br-int", nicType="dpdkvhostuserclient",
                ifaceId=None):
        try:
            if vmUuid is not None and vmUuid.strip() != "":
                vmUuid = vmUuid.replace('-', '')
            srcPath = OVS_DPDK_SRC_PATH + nicName
            interfaceId = getInterfaceId(nicName, nicUuid, ifaceId)
            safeInterfaceId = shlex.quote(str(interfaceId))
            if reinstall:
                cmd = '{cmd} del-port {brName} {nicName}; ' \
                      '{cmd} add-port {brName} {nicName} ' \
                      '-- set Interface {nicName} type={nicType} options:vhost-server-path={srcPath} ' \
                      '-- set interface {nicName} external-ids:iface-id={interfaceId} ' \
                      '-- set interface {nicName} external-ids:vm-uuid={vmUuid}'.format(
                    cmd=CtlBin, brName=brName, nicName=nicName, nicType=nicType, srcPath=srcPath,
                    vmUuid=vmUuid, interfaceId=safeInterfaceId)
            else:
                cmd = CtlBin + '--may-exist add-port {brName} {nicName} ' \
                               '-- set Interface {nicName} type={nicType} options:vhost-server-path={srcPath} ' \
                               '-- set interface {nicName} external-ids:iface-id={interfaceId} ' \
                               '-- set interface {nicName} external-ids:vm-uuid={vmUuid}'.format(
                    brName=brName, nicName=nicName, nicType=nicType, srcPath=srcPath,
                    vmUuid=vmUuid, interfaceId=safeInterfaceId)
            bash.bash_r(cmd)
        except ValueError:
            raise
        except Exception as err:
            logger.error(
                "Add port {} for bridge {} failed. {}".format(nicName, brName, err))

    @bash.in_bash
    def delVnic(self, nicName, brName="br-int"):
        try:
            bash.bash_r(CtlBin + 'del-port {} {}'.format(brName, nicName))
        except Exception as err:
            logger.error(
                "Delete port of bridge {} failed. {}".format(brName, err))

    @bash.in_bash
    def getUplink(self, brName="br-phy"):
        r, o, e = bash.bash_roe(CtlBin + " br-exists {}".format(brName))
        if r != 0:
            return []

        r, o, e = bash.bash_roe(CtlBin + " list-ports {}".format(brName))
        if r != 0:
            logger.debug(CtlBin + " list-ports {}, failed {}".format(brName, e))
            return r

        ret = []
        lines = o.split("\n")
        for l in lines:
            l = l.strip()
            if l.startswith("vnic"):
                continue
            if l.startswith("patch"):
                continue
            ret.append(l)

        return ret

    @bash.in_bash
    def addUplink(self, portPciMap, bondMode, lacpmode, ip, netmask, brName="br-phy", bondName="dpdkbond"):
        bash.bash_roe("{binPath} --may-exist add-br {brName};"
                      "{binPath} set Bridge br-phy datapath_type=netdev;"
                      "{binPath} set bridge br-phy fail-mode=standalone"
                      .format(binPath=CtlBin, brName=brName))

        uplinks = self.getUplink(brName)
        for link in uplinks:
            bash.bash_roe(CtlBin + " del-port {} {}".format(brName, link))

        if len(portPciMap.__dict__) == 1:
            for nicName, pciAddress in portPciMap.__dict__.items():
                r, _, e = bash.bash_roe(CtlBin + " --may-exist add-port {brName} {nic} "
                                                 "-- set Interface {nic} type=dpdk options:dpdk-devargs={pci};"
                                        .format(brName=brName, nic=nicName, pci=pciAddress))
                if r != 0:
                    logger.debug(CtlBin + " add-port {} {} failed: {}".format(brName, nicName, e))
                    return r, e
        else:
            cmd = CtlBin + "--may-exist add-bond {} {} ".format(brName, bondName)
            for nicName, pciAddress in portPciMap.__dict__.items():
                cmd = cmd + " {} ".format(nicName)
            r, _, e = bash.bash_roe(cmd)
            if r != 0:
                logger.debug("{} faild {}".format(cmd, e))
                return r, e
            for nicName, pciAddress in portPciMap.__dict__.items():
                r, _, e = bash.bash_roe(CtlBin + " set Interface {nic} type=dpdk options:dpdk-devargs={pci} "
                                        .format(nic=nicName, pci=pciAddress))
                if r != 0:
                    logger.debug("ovs-vsctl set Interface {} type=dpdk options:dpdk-devargs={} faild {}"
                                 .format(nicName, pciAddress, e))
                    return r, e

            if bondMode is not None:
                bash.bash_roe(CtlBin + " set port dpdkbond bond_mode={mode} ".format(mode=bondMode))

            if lacpmode is not None:
                bash.bash_roe(CtlBin + " set port dpdkbond lacp={mode} ".format(mode=lacpmode))

        # TODO configure ip when we need overlay network
        # if ip is not None:
        #    iproute.flush_address_no_error(brName)
        #    iproute.add_address_no_error(ip, linux.netmask_to_cidr(netmask), 4, brName)

        return 0, ""

    def isOvsRunning(self):
        pids = [-1, -1, -1]
        try:
            if os.path.exists(OVSDB_PID_PATH):
                with open(OVSDB_PID_PATH, 'r') as f:
                    pids[0] = int(f.read().strip())

            if os.path.exists(VSWITCHD_PID_PATH):
                with open(VSWITCHD_PID_PATH, 'r') as f:
                    pids[1] = int(f.read().strip())

            if os.path.exists(OVN_CONTROLLER_PID_PATH):
                with open(OVN_CONTROLLER_PID_PATH, 'r') as f:
                    pids[2] = int(f.read().strip())

        except OSError as err:
            logger.error("OSError: {}".format(err))
        finally:
            return pids[0] != -1 and pids[1] != -1 and pids[2] != -1

    @bash.in_bash
    def ensureOvsRunning(self, after_ovsdb_start_hook=None):
        """Ensure ovsdb-server, ovs-vswitchd, and ovn-controller are running.

        If any of them is not running, restart them in order:
          1. restart ovsdb-server (or openvswitch if ovsdb-server is not a
             separate service unit, see ovn_check_local_port in ovn.py)
          2. call after_ovsdb_start_hook (if provided, e.g. clean stale vnics)
          3. restart openvswitch + ovn-controller (or just ovn-controller if
             openvswitch was already restarted in step 1)

        :param after_ovsdb_start_hook: optional callable invoked after ovsdb-server
               is up but before openvswitch restarts, useful for cleaning stale
               ports that require ovsdb access.
        :return: (success: bool, error: str)
        """
        if self.isOvsRunning():
            return True, ''

        logger.info('OVS services not fully running, attempting restart')

        # Step 1: bring up ovsdb-server so ovs-vsctl commands work.
        # Some distros have a separate ovsdb-server.service (see start_ovn_service
        # in ovn.py), while others bundle it into openvswitch.service.
        ovsdb_started_separately = False
        r, o, e = bash.bash_roe('systemctl restart ovsdb-server')
        if r == 0:
            ovsdb_started_separately = True
        else:
            if self._systemdUnitExists('ovsdb-server.service') is False:
                logger.info('ovsdb-server.service not available, restarting openvswitch instead')
                r, o, e = bash.bash_roe('systemctl restart openvswitch')
                if r != 0:
                    return False, 'restart openvswitch failed: %s' % e
            else:
                return False, 'restart ovsdb-server failed: %s' % e

        # Step 2: optional hook (e.g. clean stale vnics while ovsdb is up)
        if after_ovsdb_start_hook:
            try:
                after_ovsdb_start_hook()
            except Exception as ex:
                logger.warn('after_ovsdb_start_hook failed: %s' % str(ex))

        # Step 3: bring up remaining services
        if ovsdb_started_separately:
            r, o, e = bash.bash_roe('systemctl restart openvswitch')
            if r != 0:
                return False, 'restart openvswitch failed: %s' % e

        r, o, e = bash.bash_roe('systemctl restart ovn-controller')
        if r != 0:
            return False, 'restart ovn-controller failed: %s' % e

        logger.info('OVS services restarted successfully')
        return True, ''

    @staticmethod
    @bash.in_bash
    def _systemdUnitExists(unit):
        r, o, e = bash.bash_roe('systemctl list-unit-files %s --no-legend' % unit)
        output = (o or '').strip()
        error = (e or '').strip()
        if r == 0:
            return bool(output)
        if 'No files found' in output or 'No files found' in error:
            return False
        return None

    @staticmethod
    @bash.in_bash
    def installOvsPackages():
        """Install OVS/OVN packages from zstack-local repo and fix service user.

        Same logic as install_ovn_package in ovn.py.
        """
        packages = "dpdk openvswitch ovn ovn-host"
        r, o, e = bash.bash_roe("yum --disablerepo=* --enablerepo=zstack-local "
                                "--nogpgcheck install -y {}".format(packages))
        if r != 0:
            raise Exception('failed to install OVS/OVN packages: %s' % e)

        devbind = DevBindBin.strip()
        if not os.path.exists(devbind):
            r, o, e = bash.bash_roe("yum --disablerepo=* --enablerepo=zstack-local "
                                    "--nogpgcheck install -y dpdk-tools")
            if r != 0:
                raise Exception('failed to install dpdk-tools: %s' % (e or o))

        # change ovs-vswitchd and ovn-controller user to root
        r, o, e = bash.bash_roe("sed -i 's/^OVS_USER_ID=\"openvswitch:hugetlbfs\"/"
                                "OVS_USER_ID=\"root:root\"/' /etc/sysconfig/openvswitch")
        if r != 0:
            raise Exception('failed to configure openvswitch service user: %s' % e)
        r, o, e = bash.bash_roe("sed -i 's/^OVN_USER_ID=\"openvswitch:openvswitch\"/"
                                "OVN_USER_ID=\"root:root\"/' /etc/sysconfig/ovn")
        if r != 0:
            raise Exception('failed to configure ovn service user: %s' % e)

    @bash.in_bash
    def getOvsOtherConfig(self, key):
        try:
            r, o, e = bash.bash_roe(CtlBin + "get Open_vSwitch . other_config:{}".format(key))
            if r != 0:
                return True, None
            return False, o.strip("\n").strip('"')
        except Exception as e:
            logger.error("Error getting OVS config: {}".format(e))
            return True, None

    @bash.in_bash
    def getOvsExternalIdsConfig(self, key):
        try:
            r, o, e = bash.bash_roe(CtlBin + "get Open_vSwitch . external-ids:{}".format(key))
            if r != 0:
                return True, None
            return False, o.strip("\n").strip('"')
        except Exception as e:
            logger.error("Error getting OVS config: {}".format(e))
            return True, None

    @bash.in_bash
    def setOvsOtherConfig(self, key, value):
        queueCmd = CtlBin + " --no-wait set Open_vSwitch . other_config:{}={}".format(key, value)
        return bash.bash_r(queueCmd)

    @bash.in_bash
    def setOvsExternalIdsConfig(self, key, value):
        cmd = CtlBin + "--no-wait set Open_vSwitch . external-ids:{}={}".format(key, value)
        return bash.bash_r(cmd)

    @bash.in_bash
    def getNicRxQueueNumConfig(self, nicName):
        try:
            r, o, e = bash.bash_roe(CtlBin + "get Interface {} options:n_rxq".format(nicName))
            if r != 0:
                return True, None
            return False, o.strip("\n").strip('"')
        except Exception as e:
            logger.error("Error getting OVS config: {}".format(e))
            return True, None

    @bash.in_bash
    def getNicRxQueueDescNumConfig(self, nicName):
        try:
            r, o, e = bash.bash_roe(CtlBin + "get Interface {} options:n_rxq_desc".format(nicName))
            if r != 0:
                return True, None
            return False, o.strip("\n").strip('"')
        except Exception as e:
            logger.error("Error getting OVS config: {}".format(e))
            return True, None

    @bash.in_bash
    def setNicRxQueueConfig(self, nicName, queueNum, queueDescNum):
        cmd = CtlBin + "--no-wait set Interface {} options:n_rxq={} options:n_rxq_desc={} " \
              "-- remove Interface {} options rxq_desc".format(nicName, queueNum, queueDescNum, nicName)
        return bash.bash_r(cmd)

    @bash.in_bash
    def bindCpuCores(self, lMask, pmdMask):
        # ovs-vsctl --no-wait set Open_vSwitch . other_config:dpdk-lcore-mask=0x3ff00
        # ovs-vsctl --no-wait set Open_vSwitch . other_config:pmd-cpu-mask=0xff00
        lMaskCmd = CtlBin + " --no-wait set Open_vSwitch . other_config:dpdk-lcore-mask={}".format(lMask)
        pmdMaskCmd = CtlBin + " --no-wait set Open_vSwitch . other_config:pmd-cpu-mask={}".format(pmdMask)
        r1 = bash.bash_r(lMaskCmd)
        r2 = bash.bash_r(pmdMaskCmd)
        return 0 if r1 == 0 and r2 == 0 else 1

    @bash.in_bash
    def getTableAttr(self, table, object, attr):
        try:
            r, o, e = bash.bash_roe(CtlBin + "get {} {} {}".format(table, object, attr))
            if r != 0:
                return True, None
            return False, o.strip("\n").strip('"')
        except Exception as e:
            logger.error("Error getting OVS config: {}".format(e))
            return True, None

    # --- Generic OVS query methods ---

    @staticmethod
    def parseOvsMap(raw):
        """Parse OVS map format {key=value, key2="value2"} into a dict."""
        raw = raw.strip()
        if not raw or raw == '{}':
            return {}
        if raw.startswith('{') and raw.endswith('}'):
            raw = raw[1:-1]
        result = {}
        for pair in VsCtl._splitOvsMapItems(raw):
            pair = pair.strip()
            if '=' in pair:
                k, v = pair.split('=', 1)
                result[VsCtl._unquoteOvsValue(k.strip())] = VsCtl._unquoteOvsValue(v.strip())
        return result

    @staticmethod
    def _splitOvsMapItems(raw):
        items = []
        current = []
        in_quotes = False
        escaped = False
        for ch in raw:
            if escaped:
                current.append(ch)
                escaped = False
                continue
            if ch == '\\' and in_quotes:
                current.append(ch)
                escaped = True
                continue
            if ch == '"':
                in_quotes = not in_quotes
                current.append(ch)
                continue
            if ch == ',' and not in_quotes:
                item = ''.join(current).strip()
                if item:
                    items.append(item)
                current = []
                continue
            current.append(ch)

        item = ''.join(current).strip()
        if item:
            items.append(item)
        return items

    @staticmethod
    def _unquoteOvsValue(value):
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
            chars = []
            escaped = False
            for ch in value:
                if escaped:
                    chars.append(ch)
                    escaped = False
                    continue
                if ch == '\\':
                    escaped = True
                    continue
                chars.append(ch)
            if escaped:
                chars.append('\\')
            return ''.join(chars)
        return value

    @bash.in_bash
    def listBridges(self):
        """Return a list of all OVS bridge names."""
        r, o, e = bash.bash_roe(CtlBin + 'list-br')
        if r != 0:
            raise Exception('failed to list OVS bridges: %s' % e)
        return [line.strip() for line in o.strip().splitlines() if line.strip()]

    @bash.in_bash
    def listPorts(self, bridge):
        """Return a list of port names on the given bridge."""
        r, o, e = bash.bash_roe(CtlBin + 'list-ports %s' % bridge)
        if r != 0:
            logger.warn('failed to list ports on bridge %s: %s' % (bridge, e))
            return []
        return [line.strip() for line in o.strip().splitlines() if line.strip()]

    @bash.in_bash
    def listBridgeIfaces(self, bridge):
        """Return a sorted list of interface names on a bridge.

        Uses ``ovs-vsctl list-ifaces <bridge>`` which lists all interfaces
        on the given bridge (excluding the internal port with the same name
        as the bridge).
        """
        r, o, e = bash.bash_roe(CtlBin + 'list-ifaces %s' % bridge)
        if r != 0:
            return []
        return sorted([line.strip() for line in o.strip().splitlines() if line.strip()])

    @bash.in_bash
    def listBondMembers(self, port_name):
        """Return a sorted list of interface names belonging to a port (bond).

        Queries the OVSDB Port table for the interface UUIDs, then resolves
        each UUID to an interface name.  Returns an empty list on error.
        """
        err, iface_uuids_raw = self.getTableAttr('port', port_name, 'interfaces')
        if err or not iface_uuids_raw:
            return []
        # iface_uuids_raw is e.g. "[uuid1, uuid2]" or a single uuid
        uuids = [u.strip() for u in iface_uuids_raw.strip('[]').split(',') if u.strip()]
        names = []
        for iface_uuid in uuids:
            err, name = self.getTableAttr('interface', iface_uuid, 'name')
            if not err and name:
                names.append(name)
        return sorted(names)

    @bash.in_bash
    def getBridgeExternalIds(self, bridge):
        """Return external_ids dict for a bridge (via br-get-external-id)."""
        r, o, e = bash.bash_roe(CtlBin + 'br-get-external-id %s' % bridge)
        if r != 0:
            return {}
        result = {}
        for line in o.strip().splitlines():
            line = line.strip()
            if '=' in line:
                k, v = line.split('=', 1)
                result[k.strip()] = v.strip()
        return result

    @bash.in_bash
    def getExternalIds(self, table, name):
        """Return external_ids dict for a port or interface record."""
        r, o, e = bash.bash_roe(CtlBin + 'get %s %s external_ids' % (table, name))
        if r != 0:
            return {}
        return self.parseOvsMap(o.strip())

    @bash.in_bash
    def getInterfaceMacInUse(self, name):
        """Return the mac_in_use value of an interface, or None."""
        r, o, e = bash.bash_roe(CtlBin + 'get interface %s mac_in_use' % name)
        if r != 0:
            return None
        mac = o.strip().strip('"')
        if mac and mac != '[]':
            return mac
        return None

def _writeSysfs(path, value, suppressRaise=False):
    try:
        with open(path, 'w') as f:
            f.write(str(value))
    except Exception as e:
        logger.warn(str(e))
        if not suppressRaise:
            raise OvsError(str(e))

def _readSysfs(path, suppressRaise=False):
    ret = None
    try:
        with open(path, 'r') as f:
            ret = f.read().rstrip()
    except Exception as e:
        logger.warn(str(e))
        if not suppressRaise:
            raise OvsError(str(e))

    return ret

class OvsDpdkEnv(object):
    hugepagesPaths = {2048: "hugepages/hugepages-2048kB/",
                      1048576: "hugepages/hugepages-1048576kB/"}
    DEFAULT_PMDCORES = ['4', '5', '6', '7']
    DEFAULT_LCORES = ['1']

    def __init__(self, lcores, pmdcores,
                 nr_hugepages, pageSize, socketMem,
                 nicNamePciAddressMap, nicRxQueueNum, nicRxQueueDescNum):
        self.lcores = [] if lcores is None else lcores.strip().split(',')
        self.pmdcores = [] if pmdcores is None else pmdcores.strip().split(',')
        self.nr_hugepages = nr_hugepages
        self.pageSize = pageSize
        self.socketMem = socketMem
        self.nicNamePciAddressMap = nicNamePciAddressMap
        self.nicRxQueueNum = nicRxQueueNum
        self.nicRxQueueDescNum = nicRxQueueDescNum

    def getCpuMask(self):
        if not self.lcores:
            self.lcores = self.DEFAULT_LCORES
        if not self.pmdcores:
            self.pmdcores = self.DEFAULT_PMDCORES

        lmask = 0
        pmdMask = 0
        for core in self.lcores:
            lmask |= 1 << int(core)
        lmask = "0x{:08x}".format(lmask)

        for core in self.pmdcores:
            pmdMask |= 1 << int(core)
        pmdMask = "0x{:08x}".format(pmdMask)
        return lmask, pmdMask

    @bash.in_bash
    def checkHugePagesMem(self):
        '''
        1. OVS-DPDK requires the huge page memory configuration to be enabled in the current cluster.
        2. Enabling the large page memory configuration in the cluster involves configuring the large page type as 2MB in GRUB and setting the total number of large pages.
        3. After the system starts, large pages will be evenly distributed across all nodes.
        4. As a conservative consideration, reserve dpdk-socket-mem for OVS-DPDK on each node.
        '''
        numaNodePaths = glob.glob("/sys/devices/system/node/node*/")
        if len(numaNodePaths) < 1:
            logger.error("can not find numa node.")
            return -1
        try:
            ps_mb = int(self.pageSize)
        except (TypeError, ValueError):
            logger.error("invalid page size: {}".format(self.pageSize))
            return -1
        if ps_mb not in (2, 1024):
            logger.error("page size only can be 2MB or 1GB!")
            return -1
        cmd = "--no-wait set Open_vSwitch . other_config:dpdk-socket-mem="
        for numaNodePath in numaNodePaths:
            hugepagesPath = os.path.join(numaNodePath, self.hugepagesPaths[ps_mb * 1024])
            osCurrentnrHugepages = int(_readSysfs(os.path.join(hugepagesPath, "nr_hugepages")))
            needAllocateHugepageNr = self.nr_hugepages
            if osCurrentnrHugepages < needAllocateHugepageNr:
                logger.warning('osCurrentnrHugepages:{} needAllocatedHugepageNr:{} is not enough to allocate hugepages for ovs dpdk!'.format(osCurrentnrHugepages, needAllocateHugepageNr))
            cmd = cmd + str(self.socketMem//len(numaNodePaths))
            cmd = cmd + ","
        return bash.bash_r(CtlBin + cmd[0:-1])
