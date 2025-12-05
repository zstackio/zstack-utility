'''

@author: haibiao.xiao
'''
import os
import shutil
import time
from os.path import split
from tarfile import DEFAULT_FORMAT

import yaml
import glob
import uuid
import re
from enum import Enum, unique

from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import bash
from zstacklib.utils import iproute
from zstacklib.utils import linux
from zstacklib.utils.lvm import lvm_check_operation

logger = log.get_logger(__name__)

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


class OvsError(Exception):
    '''ovs error'''


class OvsDpdkNic:
    def __init__(self):
        self.name = ""
        self.pciAddress = ""
        self.driver = ""


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
            if item.startswith("drv="):
                nic.driver = item.split("=")[1]

        logger.debug("dpdk nic[%s] name: %s, driver: %s" % (nic.pciAddress, nic.name, nic.driver))
        ret.append(nic)

    return ret


def getAllVfioPciNic():
    ret = []
    dpdkNics = getAllDpdkNic()
    for nic in dpdkNics:
        if nic.driver == "vfio-pci":
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
        logger.exception("Delete vnic for brdige {} failed. {}".format(brName, err))


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
def restoreNicDriver(nicNamePciAddressMap, nicNameDriverMap):
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
            continue

        targetDriver = nicNameDriverMap.__dict__[nicName]
        if driver == "mlx5_core" or driver == targetDriver:
            # mellanox nic(like cx-5) does not need vfio driver
            continue

        # for nested vm, the driver is should be uio_pci_generic
        r, _, e = bash.bash_roe(DevBindBin + " -b {driver} {pciAddress}"
                                .format(driver=targetDriver, pciAddress=pciAddress))
        if r != 0:
            logger.debug(
                "change change nic [pci address: {}] driver to {} failed: {}"
                .format(pciAddress, targetDriver, e))
        else:
            logger.debug(
                "successfully change change nic [pci address: {}] driver to {}".format(pciAddress, targetDriver))

        bash.bash_r("ip link set up dev {}".format(nicName))

    return 0, ""

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
                "Add port for brdige {} failed. {}".format(brName, err))
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
                "Add port from brdige {} failed. {}".format(brName, err))
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
                "Get interface id from brdige {} failed. {}".format(brName, err)
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
                "get port from brdige {} failed. {}".format(brName, err))
            return []

    @bash.in_bash
    def addVnic(self, nicName, nicUuid, vmUuid, reinstall=False, brName="br-int", nicType="dpdkvhostuserclient"):
        try:
            if vmUuid is not None and vmUuid.strip() != "":
                vmUuid = vmUuid.replace('-', '')
            srcPath = OVS_DPDK_SRC_PATH + nicName
            if reinstall:
                cmd = '{cmd} del-port {brName} {nicName}; ' \
                      '{cmd} add-port {brName} {nicName} ' \
                      '-- set Interface {nicName} type={nicType} options:vhost-server-path={srcPath} ' \
                      '-- set interface {nicName} external-ids:iface-id={nicName}_{nicUuid} ' \
                      '-- set interface {nicName} external-ids:vm-uuid={vmUuid}'.format(
                    cmd=CtlBin, brName=brName, nicName=nicName, nicType=nicType, srcPath=srcPath, nicUuid=nicUuid,
                    vmUuid=vmUuid)
            else:
                cmd = CtlBin + '--may-exist add-port {brName} {nicName} ' \
                               '-- set Interface {nicName} type={nicType} options:vhost-server-path={srcPath} ' \
                               '-- set interface {nicName} external-ids:iface-id={nicName}_{nicUuid} ' \
                               '-- set interface {nicName} external-ids:vm-uuid={vmUuid}'.format(
                    brName=brName, nicName=nicName, nicType=nicType, srcPath=srcPath, nicUuid=nicUuid,
                    vmUuid=vmUuid)
            bash.bash_r(cmd)
        except Exception as err:
            logger.error(
                "Add port for brdige {} failed. {}".format(brName, err))

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

        # TODO configure ip when we need overlay nrtwork
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
                with open(VSWITCHD_PID_PATH, 'r') as f:
                    pids[2] = int(f.read().strip())

        except OSError as err:
            logger.error("OSError: {}".format(err))
        finally:
            return pids[0] != -1 and pids[1] != -1 and pids[2] != -1

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
            r, o, e = bash.bash_roe(CtlBin + "get Interface {} options:rxq_desc".format(nicName))
            if r != 0:
                return True, None
            return False, o.strip("\n").strip('"')
        except Exception as e:
            logger.error("Error getting OVS config: {}".format(e))
            return True, None

    @bash.in_bash
    def setNicRxQueueConfig(self, nicName, queueNum, queueDescNum):
        queueCmd = CtlBin + " --no-wait set Interface {} options:n_rxq={}".format(nicName, queueNum)
        r1 = bash.bash_r(queueCmd)
        bufferCmd = CtlBin + " --no-wait set Interface {} options:rxq_desc={}".format(nicName, queueDescNum)
        r2 = bash.bash_r(bufferCmd)
        return 0 if r1 == 0 and r2 == 0 else 1

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

        if self.pageSize != 2 and self.socketMem == 512:
            logger.error("page size only can be 2MB or 1GB!")
            return 1
        cmd = "--no-wait set Open_vSwitch . other_config:dpdk-socket-mem="
        for numaNodePath in numaNodePaths:
            hugepagesPath = os.path.join(numaNodePath, self.hugepagesPaths[int(self.pageSize)*1024])
            osCurrentnrHugepages = int(_readSysfs(os.path.join(hugepagesPath, "nr_hugepages")))
            needAllocateHugepageNr = self.nr_hugepages
            if osCurrentnrHugepages < needAllocateHugepageNr:
                logger.warning('osCurrentnrHugepages:{} needAllocatedHugepageNr:{} is not enough to allocate hugepages for ovs dpdk!'.format(osCurrentnrHugepages, needAllocateHugepageNr))
            cmd = cmd + str(self.socketMem)
            cmd = cmd + ","
        return bash.bash_r(CtlBin + cmd[0:-1])
