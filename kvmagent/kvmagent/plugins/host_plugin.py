'''

@author: frank
'''
import base64
import concurrent.futures
import copy
import functools
import hashlib
import os
import os.path
import platform
import re
import uuid
import sys
import string
import socket
import yaml
import subprocess
import time
try:
    from shlex import quote as shell_quote
except ImportError:
    from pipes import quote as shell_quote

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import http, lvm, ceph, pci, gpu, linux
from zstacklib.utils import qemu
from zstacklib.utils import iptables
from zstacklib.utils import iproute
from zstacklib.utils import network_ipv6
from zstacklib.utils import ebtables
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import sizeunit
from zstacklib.utils import thread
from zstacklib.utils import xmlobject
from zstacklib.utils import ovs
from zstacklib.utils import misc
from zstacklib.utils.bash import *
from zstacklib.utils.ip import get_nic_supported_max_speed
from zstacklib.utils.ip import get_nic_driver_type
from zstacklib.utils.libvirt_singleton import LibvirtSingleton
from zstacklib.gpu.base import VendorEnum
from zstacklib.utils.report import Report
from zstacklib.utils import ovn
import zstacklib.utils.ip as ip
import zstacklib.utils.plugin as plugin
from zstacklib.utils.sizeunit import get_size

os_info = platform.freedesktop_os_release()
DIST_NAME = os_info.get('ID', '').lower()
# FIXME(py3): remove it
DIST_NAME = 'centos' if DIST_NAME == 'helix' else DIST_NAME

host_arch = platform.machine()
IS_AARCH64 = host_arch == 'aarch64'
IS_MIPS64EL = host_arch == 'mips64el'
IS_LOONGARCH64 = host_arch == 'loongarch64'
GRUB_FILES = ["/boot/grub2/grub.cfg", "/boot/grub/grub.cfg", "/etc/grub2-efi.cfg", "/etc/grub-efi.cfg"] \
    + ["/boot/efi/EFI/{}/grub.cfg".format(DIST_NAME)]


@functools.lru_cache(maxsize=1)
def get_grub_rocky_envs():
    return bash_o("find /boot -name grubenv").strip().split("\n")


@functools.lru_cache(maxsize=1)
def get_iptables_cmd():
    return iptables.get_iptables_cmd()


@functools.lru_cache(maxsize=1)
def get_ebtables_cmd():
    return ebtables.get_ebtables_cmd()

# =============================================================================
# GPU Plugin Configuration - Simplified, adapter no longer needed
# =============================================================================

# Cap concurrent virsh subprocess calls to avoid overwhelming the host.
# Most VMs hit the early-return path (no passthrough devices), so in
# practice far fewer than max_workers actually run virsh commands.
_PCI_QUERY_MAX_WORKERS = 16

COLO_QEMU_KVM_VERSION = '/var/lib/zstack/colo/qemu_kvm_version'
COLO_LIB_PATH = '/var/lib/zstack/colo/'
HOST_TAKEOVER_FLAG_PATH = '/var/run/zstack/takeOver'
NODE_INFO_PATH = '/sys/devices/system/node/'
PCI_CONFIG_PATH = '/etc/pci_config'
KVMAGENT_VERSION_PATH = '/var/lib/zstack/kvmagent_version'
KVMAGENT_SHUTDOWN_PATH = '/var/lib/zstack/kvm/shutdown_vm'
KVMAGENT_SHUTDOWN_INIT_PATH = '/etc/init.d/shutdown_vm'

BOND_MODE_ACTIVE_0 = "balance-rr"
BOND_MODE_ACTIVE_1 = "active-backup"
BOND_MODE_ACTIVE_2 = "balance-xor"
BOND_MODE_ACTIVE_3 = "broadcast"
BOND_MODE_ACTIVE_4 = "802.3ad"
BOND_MODE_ACTIVE_5 = "balance-tlb"
BOND_MODE_ACTIVE_6 = "balance-alb"

DISTRO_USING_DNF = ['rl84', 'h84r', 'ky10sp1', 'ky10sp2', 'ky10sp3',
                    'ky10sp3.2403', 'oe2203sp1', 'h2203sp1o', 'uos20r']


class ConnectResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ConnectResponse, self).__init__()
        self.firstConnect = False
        self.agentStartTimeMillis = 0


class HostCapacityResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(HostCapacityResponse, self).__init__()
        self.cpuNum = None
        self.cpuSpeed = None
        self.usedCpu = None
        self.totalMemory = None
        self.usedMemory = None
        self.cpuSockets = None
        self.cpuCoreNum = None


class HostFactResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(HostFactResponse, self).__init__()
        self.osDistribution = None
        self.osVersion = None
        self.osRelease = None
        self.qemuImgVersion = None
        self.qemuKvmPackageVersion = None
        self.libvirtVersion = None
        self.hvmCpuFlag = None
        self.cpuModelName = None
        self.systemSerialNumber = None
        self.eptFlag = None
        self.libvirtCapabilities = []
        self.virtualizerInfo = vm_plugin.VirtualizerInfoTO()
        self.iscsiInitiatorName = None
        self.deployMode = None
        self.cpuFeatureMd5 = None


class SetupMountablePrimaryStorageHeartbeatCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SetupMountablePrimaryStorageHeartbeatCmd, self).__init__()
        self.heartbeatFilePaths = None
        self.heartbeatInterval = None


class SetupMountablePrimaryStorageHeartbeatResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(SetupMountablePrimaryStorageHeartbeatResponse, self).__init__()


class PingResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(PingResponse, self).__init__()
        self.hostUuid = None


class CheckFileOnHostResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckFileOnHostResponse, self).__init__()
        self.existPaths = {}


class GetUsbDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetUsbDevicesRsp, self).__init__()
        self.usbDevicesInfo = None


class GetBlockDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetBlockDevicesRsp, self).__init__()
        self.blockDevices = None


class StartUsbRedirectServerRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(StartUsbRedirectServerRsp, self).__init__()
        self.port = None


class StopUsbRedirectServerRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(StopUsbRedirectServerRsp, self).__init__()


class CheckUsbServerPortRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckUsbServerPortRsp, self).__init__()
        self.uuids = []


class ReportDeviceEventCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ReportDeviceEventCmd, self).__init__()
        self.hostUuid = None


class UpdateHostOSCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(UpdateHostOSCmd, self).__init__()
        self.hostUuid = None
        self.excludePackages = None


class UpdateHostOSRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(UpdateHostOSRsp, self).__init__()


class UpdateDependencyCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(UpdateDependencyCmd, self).__init__()
        self.hostUuid = None


class UpdateDependencyRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(UpdateDependencyRsp, self).__init__()


class GetXfsFragDataRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetXfsFragDataRsp, self).__init__()
        self.fsType = None
        self.hostFrag = None
        self.volumeFragMap = {}


class EnableHugePageRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(EnableHugePageRsp, self).__init__()


class DisableHugePageRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(DisableHugePageRsp, self).__init__()


class SetIpOnHostNetworkInterfaceCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SetIpOnHostNetworkInterfaceCmd, self).__init__()
        self.interfaceName = None
        self.oldIpAddress = None
        self.oldNetmask = None
        self.oldGateway = None
        self.ipAddress = None
        self.netmask = None
        self.prefixLength = None
        self.gateway = None


class SetIpOnHostNetworkInterfaceRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(SetIpOnHostNetworkInterfaceRsp, self).__init__()


class CheckInterfaceVlanCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CheckInterfaceVlanCmd, self).__init__()
        self.interfaceName = None
        self.vlanId = None


class CheckInterfaceVlanRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckInterfaceVlanRsp, self).__init__()
        self.valid = None


class GetInterfaceVlanCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetInterfaceVlanCmd, self).__init__()
        self.interfaceNames = []


class GetInterfaceVlanRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetInterfaceVlanRsp, self).__init__()
        self.vlanIds = []


class GetInterfaceNameCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetInterfaceNameCmd, self).__init__()
        self.ipAddresses = []


class GetInterfaceNameRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetInterfaceNameRsp, self).__init__()
        self.interfaceNames = []


class SetServiceTypeOnHostNetworkInterfaceCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SetServiceTypeOnHostNetworkInterfaceCmd, self).__init__()
        self.interfaceName = None
        self.vlanId = None
        self.serviceType = []


class SetVmConsolePasswordLiveCmd(kvmagent.AgentCommand):
    @log.sensitive_fields("password")
    def __init__(self):
        super(SetVmConsolePasswordLiveCmd, self).__init__()
        self.vmUuid = None
        self.password = None


class HostPhysicalMemoryStruct(object):
    def __init__(self):
        self.size = ""
        self.locator = ""
        self.speed = ""
        self.clockSpeed = ""
        self.manufacturer = ""
        self.serialNumber = ""
        self.rank = ""
        self.voltage = ""
        self.type = ""


class GetHostPhysicalMemoryFactsResponse(kvmagent.AgentResponse):
    physicalMemoryFacts = None  # type: list[HostPhysicalMemoryStruct]

    def __init__(self):
        super(GetHostPhysicalMemoryFactsResponse, self).__init__()
        self.physicalMemoryFacts = []


class GetHostNetworkBongdingCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetHostNetworkBongdingCmd, self).__init__()
        self.managementServerIp = None


class GetHostNetworkBongdingResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetHostNetworkBongdingResponse, self).__init__()
        self.bondings = [] # type: list[HostNetworkBondingInventory]
        self.nics = [] # type: list[HostNetworkInterfaceInventory]


class HostNetworkBondingInventory(object):
    slaves = None  # type: list[HostNetworkInterfaceInventory]

    def __init__(self, bondingName=None, type=None, managementServerIp=None):
        super(HostNetworkBondingInventory, self).__init__()
        self.bondingName = bondingName
        self.speed = None
        self.type = type
        self.mode = None
        self.xmitHashPolicy = None
        self.miiStatus = None
        self.mac = None
        self.ipAddresses = None
        self.miimon = None
        self.allSlavesActive = None
        self.slaves = None
        self.bondingType = None
        self.callBackIp = None

        if self.type in ovs.OvsDpdkSupportBondType:
            self._init_from_ovs()
        else:
            self._init_from_name(managementServerIp)

    def _init_from_name(self, managementServerIp):
        def get_nic(n, i):
            o = HostNetworkInterfaceInventory(n, None, managementServerIp)
            self.slaves[i] = o

        if self.bondingName is None:
            return

        self.type = "LinuxBonding"
        self.speed = get_nic_supported_max_speed(self.bondingName)
        self.mode = linux.read_file(
            "/sys/class/net/%s/bonding/mode" % self.bondingName).strip()
        self.xmitHashPolicy = linux.read_file(
            "/sys/class/net/%s/bonding/xmit_hash_policy" % self.bondingName).strip()
        self.miiStatus = linux.read_file(
            "/sys/class/net/%s/bonding/mii_status" % self.bondingName).strip()
        self.mac = linux.read_file(
            "/sys/class/net/%s/address" % self.bondingName).strip()
        if len(bash_o("ip link show type bridge_slave %s" %
               self.bondingName).strip()) > 0:
            self.bondingType = "bridgeSlave"
        else:
            self.bondingType = "noBridge"
        self.callBackIp = managementServerIp
        if managementServerIp is not None:
            self.callBackIp = self._get_src_addr(managementServerIp)
        self.ipAddresses = ['%s/%d' % (x.address, x.prefixlen)
                            for x in iproute.query_addresses(ifname=self.bondingName, ip_version=4)]
        if len(self.ipAddresses) == 0:
            master = linux.read_file(
                "/sys/class/net/%s/master/ifindex" % self.bondingName)
            if master:
                self.ipAddresses = ['%s/%d' % (x.address, x.prefixlen)
                                    for x in iproute.query_addresses(index=int(master.strip()), ip_version=4)]
        self.miimon = linux.read_file_strip(
            "/sys/class/net/%s/bonding/miimon" % self.bondingName)
        self.allSlavesActive = linux.read_file_strip(
            "/sys/class/net/%s/bonding/all_slaves_active" % self.bondingName) == "0"
        slave_info = linux.read_file_strip(
            "/sys/class/net/%s/bonding/slaves" % self.bondingName)
        slave_names = slave_info.split() if slave_info else []
        if len(slave_names) == 0:
            return

        self.slaves = [None] * len(slave_names)
        threads = []
        for idx, name in enumerate(slave_names, start=0):
            threads.append(thread.ThreadFacade.run_in_thread(
                get_nic, [name.strip(), idx]))
        for t in threads:
            t.join()

    def _init_from_ovs(self):
        # dpdkBond
        bondModeList = [
            "balance-rr 0",
            "active-backup 1",
            "balance-xor 2",
            "broadcast 3",
            "802.3ad 4",
            "balance-tlb 5",
            "balance-alb 6"
        ]

        bondPolicyMap = {
            "l2": "layer 2",
            "l23": "layer 2+3",
            "l34": "layer 3+4"
        }

        def get_nic(n, i, b):
            o = HostNetworkInterfaceInventory(n, b)
            self.slaves[i] = o

        bondData = self.bondingName
        # TODO no test?
        self.speed = get_nic_supported_max_speed(self.bondingName)

        if 'bond' not in bondData:
            return

        if 'name' in bondData['bond']:
            self.bondingName = bondData['bond']['name']

        if 'mode' in bondData['bond']:
            if type(bondData['bond']['mode']) is int:
                self.mode = bondModeList[bondData['bond']['mode']]
            else:
                self.mode = bondData['bond']['mode']

        if 'policy' in bondData['bond']:
            self.xmitHashPolicy = bondPolicyMap[bondData['bond']['policy']]

        self.type = "OvsBonding"
        self.miiStatus = None
        self.mac = None
        self.ipAddresses = None
        self.miimon = None
        self.allSlavesActive = None

        if 'slaves' not in bondData['bond']:
            return

        self.slaves = [None] * len(bondData['bond']['slaves'])
        threads = []
        for idx, name in enumerate(bondData['bond']['slaves'], start=0):
            threads.append(thread.ThreadFacade.run_in_thread(
                get_nic, [name.strip(), idx, self.bondingName]))
        for t in threads:
            t.join()

    def _to_dict(self):
        to_dict = self.__dict__
        for k in list(to_dict.keys()):
            if k == "slaves":
                v = copy.deepcopy(to_dict[k])
                to_dict[k] = [i.__dict__ for i in v]
        return to_dict

    def _get_src_addr(self, ip_addr):
        output = subprocess.check_output(
            ['ip', 'r', 'get', ip_addr]).decode('utf-8')

        return network_ipv6.extract_route_source_address(output)


class HostNetworkInterfaceInventory(object):
    def init(self, name, master=None, managementServerIp=None,
             driverType=None, pciAddress=None):
        super(HostNetworkInterfaceInventory, self).__init__()
        self.interfaceName = name
        self.speed = None
        self.slaveActive = None
        self.carrierActive = None
        self.mac = None
        self.ipAddresses = None
        self.interfaceType = None
        self.master = master
        self.pciDeviceAddress = pciAddress
        self.offloadStatus = None
        self.callBackIp = None
        self.interfaceModel = None
        self.vendorId = None
        self.deviceId = None
        self.subvendorId = None
        self.subdeviceId = None
        self.rev = None
        self.driverType = driverType

        if driverType == "vfio-pci" or driverType == "uio_pci_generic":
            return

        bonds = ovs.getAllBondFromFile()

        if bonds:
            for bond in bonds:
                if self.interfaceName in bond.slaves:
                    self.master = bond.name

        if self.master is not None:
            self._init_from_ovs()
        else:
            self._init_from_name(managementServerIp)

    def __new__(cls, name, master=None, managementServerIp=None,
                driverType=None, pciAddress=None, *args, **kwargs):
        o = super(HostNetworkInterfaceInventory, cls).__new__(cls)
        o.init(name, master, managementServerIp, driverType, pciAddress)
        return o

    def _updateActiveState(self):
        if self.interfaceType == "bondingSlave":
            activeSlave = linux.read_file(
                "/sys/class/net/%s/bonding/active_slave" % self.master)
            self.slaveActive = self.interfaceName in activeSlave if activeSlave is not None else None

    @in_bash
    def _init_from_name(self, managementServerIp):
        if self.interfaceName is None:
            return
        self.speed = get_nic_supported_max_speed(self.interfaceName)
        # cannot read carrier of vf nic
        if not os.path.exists(
                "/sys/class/net/%s/device/physfn" % self.interfaceName):
            carrier = linux.read_file(
                "/sys/class/net/%s/carrier" % self.interfaceName)
            if carrier:
                self.carrierActive = carrier.strip() == "1"

        self.mac = linux.read_file_strip(
            "/sys/class/net/%s/address" % self.interfaceName)
        self.ipAddresses = linux.get_interface_ip_addresses(self.interfaceName)
        self.callBackIp = managementServerIp
        if managementServerIp is not None:
            self.callBackIp = self._get_src_addr(managementServerIp)

        self.master = linux.get_interface_master_device(self.interfaceName)
        if self.master is not None:
            self.master = self.master.strip()

        if len(self.ipAddresses) == 0:
            if self.master:
                self.ipAddresses = linux.get_interface_ip_addresses(
                    self.master)
        if self.master is None:
            self.interfaceType = "noMaster"
        elif len(bash_o("ip link show type bond_slave %s" % self.interfaceName).strip()) > 0:
            self.interfaceType = "bondingSlave"
            activeSlave = linux.read_file(
                "/sys/class/net/%s/bonding/active_slave" % self.master)
            self.slaveActive = self.interfaceName in activeSlave if activeSlave is not None else None
        else:
            self.interfaceType = "bridgeSlave"

        self.pciDeviceAddress = os.readlink(
            "/sys/class/net/%s/device" % self.interfaceName).strip().split('/')[-1]
        if "virtio" in self.pciDeviceAddress:
            # readlink  /sys/class/net/ens3/device
            # ../../../ virtio1
            # readlink -f /sys/class/net/ens3/device
            # /sys/devices/pci0000:00/0000:00:03.0/virtio1
            self.pciDeviceAddress = bash_o(
                "readlink -f /sys/class/net/%s/device | awk -F '/' '{print $5}'" % self.interfaceName)
            self.pciDeviceAddress = self.pciDeviceAddress.strip("\n")

        self.driverType = get_nic_driver_type(self.interfaceName)
        self.offloadStatus = ovs.getOffloadStatus(self.interfaceName)
        self._init_interfacemodel()

    @in_bash
    def _init_from_ovs(self):
        if self.interfaceName is None:
            return

        if ovs.isBDF(self.interfaceName):
            return

        self.speed = get_nic_supported_max_speed(self.interfaceName)
        # cannot read carrier of vf nic
        if not os.path.exists(
                "/sys/class/net/%s/device/physfn" % self.interfaceName):
            carrier = linux.read_file(
                "/sys/class/net/%s/carrier" % self.interfaceName)
            if carrier:
                self.carrierActive = carrier.strip() == "1"
        self.mac = linux.read_file(
            "/sys/class/net/%s/address" % self.interfaceName).strip()
        self.ipAddresses = linux.get_interface_ip_addresses(self.interfaceName)
        self.interfaceType = "bondingSlave"

        # TODO: check dpdk slave status
        # self.slaveActive = ovs.getOvsCtl(with_dpdk=True).checkDpdkSlaveStatus(self.interfaceName)
        self.pciDeviceAddress = os.readlink(
            "/sys/class/net/%s/device" % self.interfaceName).strip().split('/')[-1]
        self.offloadStatus = ovs.getOffloadStatus(self.interfaceName)
        self._init_interfacemodel()

    @in_bash
    def _init_interfacemodel(self):
        # todo: read file
        # Get IDs using -Dmmnv (without second 'n' to avoid truncation)
        r_id, o_id, e_id = bash_roe(
            "lspci -Dmmnv -s %s" % self.pciDeviceAddress)
        # Get names using -Dmmv (without 'nn' to get full names)
        r_name, o_name, e_name = bash_roe(
            "lspci -Dmmv -s %s" % self.pciDeviceAddress)

        if r_id == 0 and r_name == 0:
            vendor_name = ""
            device_name = ""
            subvendor_name = ""

            # Parse IDs from -Dmmnv output
            ids = {}
            for line in o_id.split('\n'):
                if len(line.split(':')) < 2:
                    continue
                title = line.split(':')[0].strip()
                content = line.split(':')[1].strip()
                if title in ['Vendor', 'Device', 'SVendor', 'SDevice', 'Rev']:
                    ids[title] = content.strip()

            # Parse names from -Dmmv output
            for line in o_name.split('\n'):
                if len(line.split(':')) < 2:
                    continue
                title = line.split(':')[0].strip()
                content = line.split(':')[1].strip()
                if title == 'Vendor':
                    vendor_name = self._simplify_device_name(content.strip())
                    self.vendorId = ids.get('Vendor', '')
                elif title == "Device":
                    device_name = self._simplify_device_name(content.strip())
                    self.deviceId = ids.get('Device', '')
                elif title == "SVendor":
                    subvendor_name = self._simplify_device_name(
                        content.strip())
                    self.subvendorId = ids.get('SVendor', '')
                elif title == "SDevice":
                    self.subdeviceId = ids.get('SDevice', '')
                elif title == "Rev":
                    self.rev = ids.get('Rev', '')
            self.interfaceModel = "%s_%s" % (
                subvendor_name if subvendor_name and "Unknown" not in subvendor_name else vendor_name, device_name)

    def _simplify_device_name(self, name):
        if 'Intel Corporation' in name:
            return 'Intel'
        elif 'Advanced Micro Devices' in name:
            return 'AMD'
        elif 'NVIDIA Corporation' in name:
            return 'NVIDIA'
        else:
            return name.replace('Co., Ltd ', '')

    def _to_dict(self):
        to_dict = self.__dict__
        return to_dict

    def _get_src_addr(self, ip_addr):
        output = subprocess.check_output(
            ['ip', 'r', 'get', ip_addr]).decode('utf-8')

        return network_ipv6.extract_route_source_address(output)


class GetNumaTopologyResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetNumaTopologyResponse, self).__init__()
        self.topology = None


class GetPciDevicesCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetPciDevicesCmd, self).__init__()
        self.filterString = None
        self.enableIommu = True
        self.skipGrubConfig = False


class GetBlockDevicesCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetBlockDevicesCmd, self).__init__()
        self.includeInUse = False


class GetPciDevicesResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetPciDevicesResponse, self).__init__()
        self.pciDevicesInfo = []
        self.hostIommuStatus = False
        self.mdevDeviceInfos = {}


class GetMttyDevicesCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetMttyDevicesCmd, self).__init__()


class GetMttyDevicesResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetMttyDevicesResponse, self).__init__()
        self.mttyDeviceInfo = None


class CreatePciDeviceRomFileCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(CreatePciDeviceRomFileCommand, self).__init__()
        self.specUuid = None
        self.romContent = None
        self.romMd5sum = None


class CreatePciDeviceRomFileRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CreatePciDeviceRomFileRsp, self).__init__()


class GenerateSriovPciDevicesCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(GenerateSriovPciDevicesCommand, self).__init__()
        self.pciDeviceAddress = None
        self.virtPartNum = None
        self.reSplite = False


class GenerateSriovPciDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GenerateSriovPciDevicesRsp, self).__init__()


class UngenerateSriovPciDevicesCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(UngenerateSriovPciDevicesCommand, self).__init__()
        self.pciDeviceAddress = None


class UngenerateSriovPciDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(UngenerateSriovPciDevicesRsp, self).__init__()


class GenerateVfioMdevDevicesCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(GenerateVfioMdevDevicesCommand, self).__init__()
        self.pciDeviceAddress = None
        self.mdevSpecTypeId = None
        self.mdevUuids = None


class GenerateVfioMdevDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GenerateVfioMdevDevicesRsp, self).__init__()
        self.mdevUuids = []


class UngenerateVfioMdevDevicesCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(UngenerateVfioMdevDevicesCommand, self).__init__()
        self.pciDeviceAddress = None
        self.mdevSpecTypeId = None


class UngenerateVfioMdevDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(UngenerateVfioMdevDevicesRsp, self).__init__()


class GenerateSeVfioMdevDevicesCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(GenerateSeVfioMdevDevicesCommand, self).__init__()
        self.mttyDeviceUuid = None
        self.mdevUuids = None
        self.reSplite = False


class GenerateSeVfioMdevDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GenerateSeVfioMdevDevicesRsp, self).__init__()
        self.mdevUuids = []


class UngenerateSeVfioMdevDevicesCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(UngenerateSeVfioMdevDevicesCommand, self).__init__()
        self.mttyDeviceUuid = None


class UngenerateSeVfioMdevDevicesRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(UngenerateSeVfioMdevDevicesRsp, self).__init__()


class DeleteVfioMdevDeviceCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteVfioMdevDeviceCommand, self).__init__()
        self.MdevDeviceUuid = None


class DeleteVfioMdevDeviceRsp(kvmagent.AgentCommand):
    def __init__(self):
        super(DeleteVfioMdevDeviceRsp, self).__init__()


class UpdateSpiceChannelConfigResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(UpdateSpiceChannelConfigResponse, self).__init__()
        self.restartLibvirt = False

# using kvmagent to transmit vm operations to management node
# like start/stop/reboot a specific vm instance


class VmOperation(object):
    def __init__(self):
        self.uuid = None
        self.operation = None


class TransmitVmOperationToMnCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(TransmitVmOperationToMnCmd, self).__init__()
        self.uuid = None
        self.operation = None


class TransmitVmOperationToMnRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(TransmitVmOperationToMnRsp, self).__init__()


class ChangeHostPasswordCmd(kvmagent.AgentCommand):
    @log.sensitive_fields("password")
    def __init__(self):
        super(ChangeHostPasswordCmd, self).__init__()
        self.password = None  # type:str


class ZwatchInstallResult(object):
    def __init__(self):
        self.vmInstanceUuid = None
        self.version = None


class ZwatchInstallResultRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(ZwatchInstallResultRsp, self).__init__()


class ScanVmPortRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(ScanVmPortRsp, self).__init__()
        self.portStatus = {}


class EnableZeroCopyRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(EnableZeroCopyRsp, self).__init__()


class DisableZeroCopyRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(DisableZeroCopyRsp, self).__init__()


class GetDevCapacityRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetDevCapacityRsp, self).__init__()
        self.totalSize = None
        self.availableSize = None
        self.dirSize = None


class AddBridgeFdbEntryRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(AddBridgeFdbEntryRsp, self).__init__()


class AttachVolumeRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(AttachVolumeRsp, self).__init__()
        self.device = None


class PciDeviceTO(object):
    def __init__(self):
        self.name = ""
        self.description = ""
        self.vendorId = ""
        self.vendor = ""
        self.deviceId = ""
        self.device = ""
        self.subvendorId = ""
        self.subdeviceId = ""
        self.pciDeviceAddress = ""
        self.parentAddress = ""
        self.iommuGroup = ""
        self.type = ""
        # Legacy compatibility field. New virtualization semantics should use
        # virtState/virtMode/virtCapabilities directly. virtStatus will be
        # deprecated once all consumers migrate.
        self.virtStatus = ""
        self.virtState = ""
        self.virtMode = ""
        self.virtCapabilities = []
        self.maxPartNum = "0"
        self.ramSize = ""
        self.mdevSpecifications = []
        self.rev = ""
        self.addonInfo = {}
        self.dependentDevices = []
        self.vmPciDeviceAddress = ""


class MttyDeviceTO(object):
    def __init__(self):
        self.name = ""
        self.description = ""
        self.type = ""
        self.virtStatus = ""


def set_pci_virt_metadata(
        to,
        virt_status,
        virt_state,
        virt_mode=None,
        virt_capabilities=None):
    # Keep virtStatus populated for backward compatibility only. New
    # virtualization semantics are carried by virtState/virtMode/
    # virtCapabilities, and virtStatus is expected to be deprecated later.
    to.virtStatus = virt_status or ""
    to.virtState = virt_state or ""
    to.virtMode = virt_mode or ""
    to.virtCapabilities = list(virt_capabilities or [])

# moved from vm_plugin to host_plugin


class UpdateConfigration(object):
    def __init__(self):
        self.path = None
        self.enableIommu = None
        self.iommu_type = 'amd_iommu' if 'hygon' in linux.get_cpu_model()[1].lower(
        ) or 'amd' in linux.get_cpu_model()[1].lower() else 'intel_iommu'

    def executeCmdOnFile(self, shellCmd):
        return bash_roe("%s %s" % (shellCmd, self.path))

    def updateHostIommu(self):
        # fix 'failed to set iommu for container: Operation not permitted'
        def _create_iommu_conf():
            _conf_lost = False
            _conf_file = '/etc/modprobe.d/iommu_unsafe_interrupts.conf'
            _conf_text = "options vfio_iommu_type1 allow_unsafe_interrupts=1"
            if not os.path.exists(_conf_file):
                _conf_lost = True
            else:
                with open(_conf_file, 'r') as f:
                    if _conf_text not in f.read():
                        _conf_lost = True

            if _conf_lost:
                with open(_conf_file, 'a') as f:
                    f.write(_conf_text)

        _create_iommu_conf()

        r_on, o_on, e_on = self.executeCmdOnFile(
            "grep -E '{}(\\ )*=(\\ )*on'".format(self.iommu_type))
        r_off, o_off, e_off = self.executeCmdOnFile(
            "grep -E '{}(\\ )*=(\\ )*off'".format(self.iommu_type))
        r_modprobe_blacklist, o_modprobe_blacklist, e_modprobe_blacklist = self.executeCmdOnFile(
            "grep -E 'modprobe.blacklist(\\ )*='")
        # When iommu has not changed,  No need to update /etc/default/grub
        if self.enableIommu is False:
            if r_on != 0 and r_off != 0 and r_modprobe_blacklist != 0:
                return True, None
        elif self.enableIommu is True:
            if r_on == 0 and r_off != 0 and r_modprobe_blacklist == 0:
                return True, None

        if r_on == 0:
            r, o, e = self.executeCmdOnFile(
                "sed -i '/GRUB_CMDLINE_LINUX/s/[[:blank:]]*{}[[:blank:]]*=[[:blank:]]*on//g'".format(self.iommu_type))
            if r != 0:
                return False, "%s %s" % (e, o)
        if r_off == 0:
            r, o, e = self.executeCmdOnFile(
                "sed -i '/GRUB_CMDLINE_LINUX/s/[[:blank:]]*{}[[:blank:]]*=[[:blank:]]*off//g'".format(self.iommu_type))
            if r != 0:
                return False, "%s %s" % (e, o)
        if r_modprobe_blacklist == 0:
            r, o, e = self.executeCmdOnFile(
                "grep -E '[[:blank:]]*modprobe.blacklist[[:blank:]]*=[[:blank:]]*[[:graph:]]*\"$'")
            if r == 0:
                r, o, e = self.executeCmdOnFile(
                    "sed -i '/GRUB_CMDLINE_LINUX/s/[[:blank:]]*modprobe.blacklist[[:blank:]]*=[[:blank:]]*[[:graph:]]*\"$/\"/g'")
                if r != 0:
                    return False, "%s %s" % (e, o)
            else:
                r, o, e = self.executeCmdOnFile(
                    "sed -i '/GRUB_CMDLINE_LINUX/s/[[:blank:]]*modprobe.blacklist[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g'")
                if r != 0:
                    return False, "%s %s" % (e, o)

        if self.enableIommu is True:
            r, o, e = self.executeCmdOnFile(
                "sed -i '/GRUB_CMDLINE_LINUX/s/\"$/ {}=on modprobe.blacklist=snd_hda_intel,amd76x_edac,vga16fb,nouveau,rivafb,nvidiafb,rivatv,amdgpu,radeon\"/g'".format(self.iommu_type))
            if r != 0:
                return False, "%s %s" % (e, o)

        return True, None

    def updateGrubConfig(self):
        def updateGrubContent(content):
            content = re.sub(
                '{0}\\s*=\\s*on'.format(self.iommu_type), '', content)
            content = re.sub(
                '{0}\\s*=\\s*off'.format(self.iommu_type), '', content)
            content = re.sub(
                '\\s*modprobe.blacklist\\s*=\\s*\\S*', '', content)
            return content

        for grub_path in GRUB_FILES:
            if os.path.exists(grub_path):
                content = updateGrubContent(linux.read_file(grub_path))
                if self.enableIommu:
                    content = re.sub(r'(/vmlinuz-.*)',
                                     r'\1 {0}=on modprobe.blacklist=snd_hda_intel,amd76x_edac,vga16fb,nouveau,rivafb,nvidiafb,rivatv,amdgpu,radeon'.format(
                                         self.iommu_type), content)
                linux.write_file(grub_path, content)
        for grub_rocky_env in get_grub_rocky_envs():
            if os.path.exists(grub_rocky_env) and self.enableIommu:
                env = updateGrubContent(linux.read_file(grub_rocky_env))
                env = re.sub(r'(kernelopts=.*)',
                             r'\1 {0}=on modprobe.blacklist=snd_hda_intel,amd76x_edac,vga16fb,nouveau,rivafb,nvidiafb,rivatv,amdgpu,radeon'.format(
                                 self.iommu_type), env)
                linux.write_file(grub_rocky_env, env)

        self.enable_vfio_module()

    def enable_vfio_module(self):
        bash_o("modprobe vfio && modprobe vfio-pci")


logger = log.get_logger(__name__)


def _get_memory(word):
    out = shell.call("grep '%s' /proc/meminfo" % word)
    (name, capacity) = out.split(':')
    capacity = re.sub('[k|K][b|B]', '', capacity).strip()
    # capacity = capacity.rstrip('kB').rstrip('KB').rstrip('kb').strip()
    return sizeunit.KiloByte.toByte(int(capacity))


def _get_total_memory():
    return _get_memory('MemTotal')


def _get_free_memory():
    return _get_memory('MemFree')


def _get_used_memory():
    return _get_total_memory() - _get_free_memory()


RPMDB_REPAIR_STALE_SECONDS = 60
RPMDB_REPAIR_WAIT_SECONDS = 60
RPMDB_YUM_CHECK_CMD = (
    "timeout -k 5s 30s yum --disablerepo=* list installed >/dev/null 2>&1"
)
RPMDB_CHECK_CMD = "timeout -k 5s 30s rpm -qa >/dev/null 2>&1"


def _yum_rpmdb_check():
    return shell.run(RPMDB_YUM_CHECK_CMD) == 0


def _rpmdb_check():
    return shell.run(RPMDB_CHECK_CMD) == 0


def _check_rpmdb_repair_prerequisites():
    cmd = ("command -v timeout >/dev/null 2>&1 && "
           "ps -eo pid=,ppid=,pgid=,stat=,etimes=,comm=,args= >/dev/null 2>&1")
    if shell.run(cmd) != 0:
        return False, "timeout and ps etimes are required to recover rpmdb safely"
    return True, None


def _remove_stale_yum_pid_files():
    cmd = r"""
for pid_file in /var/run/yum.pid /run/yum.pid; do
    [ -f "$pid_file" ] || continue
    pid="$(awk '{print $1}' "$pid_file" 2>/dev/null)"

    case "$pid" in
        ''|*[!0-9]*)
            echo "remove malformed yum pid file: $pid_file"
            rm -f "$pid_file" || exit 2
            continue
            ;;
    esac

    if ! kill -0 "$pid" 2>/dev/null; then
        echo "remove stale yum pid file: $pid_file"
        rm -f "$pid_file" || exit 2
        continue
    fi

    proc="$(ps -p "$pid" -o comm= -o args= 2>/dev/null)"
    case "$proc" in
        *yum*|*dnf*|*rpm*)
            ;;
        *)
            echo "remove yum pid file owned by non-package process: $pid_file"
            rm -f "$pid_file" || exit 2
            ;;
    esac
done
"""
    r, o, e = bash_roe(cmd)
    if r != 0:
        return False, e or o
    return True, None


def _parse_package_processes(output):
    processes = []
    for line in output.splitlines():
        fields = line.split(None, 4)
        if len(fields) < 4:
            continue

        try:
            pid = int(fields[0])
            etimes = int(fields[2])
        except ValueError:
            continue

        processes.append({
            'pid': pid,
            'stat': fields[1],
            'etimes': etimes,
            'comm': fields[3],
            'args': fields[4] if len(fields) > 4 else ''
        })
    return processes


def _list_package_processes():
    cmd = r"""
pgid="$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ')"
ps -eo pid=,ppid=,pgid=,stat=,etimes=,comm=,args= 2>/dev/null | awk \
    -v self="$$" -v parent="$PPID" -v pgid="$pgid" '
    {
        pid=$1
        ppid=$2
        proc_pgid=$3
        stat=$4
        etimes=$5
        comm=$6
        args=""
        for (i = 7; i <= NF; i++) {
            args = args " " $i
        }

        if (pid == self || pid == parent || proc_pgid == pgid) {
            next
        }

        if (comm ~ /^(yum|dnf|rpm)$/) {
            print pid, stat, etimes, comm, args
            next
        }

        if (comm ~ /(^|-)python[0-9.]*$/ &&
            args ~ /(\/usr\/bin\/yum|\/bin\/yum|\/usr\/bin\/dnf|\/bin\/dnf)/) {
            print pid, stat, etimes, comm, args
        }
    }'
"""
    r, o, e = bash_roe(cmd)
    if r != 0:
        return None, e or o
    return _parse_package_processes(o), None


def _format_package_process_pids(processes):
    return ','.join([str(p['pid']) for p in processes])


def _check_d_state_package_processes(processes):
    d_state_processes = [p for p in processes if p['stat'].startswith('D')]
    if d_state_processes:
        return ("package manager process is in D state; rpmdb recovery requires "
                "host reboot or manual intervention. pids: %s" %
                _format_package_process_pids(d_state_processes))
    return None


def _check_young_package_processes(processes):
    young_processes = [p for p in processes
                       if p['etimes'] < RPMDB_REPAIR_STALE_SECONDS]
    if young_processes:
        return ("package manager process is still active and below stale "
                "threshold; skip destructive rpmdb recovery. pids: %s" %
                _format_package_process_pids(young_processes))
    return None


def _yum_failed_without_package_processes(processes):
    return (not processes and _rpmdb_check(),
            "yum cannot list installed packages but rpmdb is healthy and no "
            "package manager process is blocking it; skip rpmdb rebuild and "
            "check yum configuration or plugins")


def _yum_failed_with_healthy_rpmdb(processes):
    return (bool(processes) and _rpmdb_check(),
            "yum cannot list installed packages because another package "
            "manager process is running, but rpmdb is healthy; skip killing "
            "the process and retry later. pids: %s" %
            _format_package_process_pids(processes))


def _core_rpmdb_is_in_use(processes):
    if not processes:
        return False, None

    rpmdb_users, error = _list_blocking_rpmdb_users()
    if error:
        return False, error
    if rpmdb_users:
        return True, ("package manager process is using rpmdb core files; "
                      "skip killing the process and retry later. pids: %s" %
                      ','.join(rpmdb_users))
    return False, None


def _terminate_package_processes(processes):
    if not processes:
        return True, None

    pids = ' '.join([str(p['pid']) for p in processes])
    cmd = """
pids="%s"
targets=""
for pid in $pids; do
    proc="$(ps -p "$pid" -o comm= -o args= 2>/dev/null)" || continue
    case "$proc" in
        *yum*|*dnf*|*rpm*)
            targets="$targets $pid"
            ;;
        *)
            echo "skip pid no longer owned by package manager: $pid"
            ;;
    esac
done

[ -n "$targets" ] || exit 0

echo "terminate stale package manager processes:$targets"
kill -TERM $targets 2>/dev/null || true
sleep 5

alive=""
for pid in $targets; do
    kill -0 "$pid" 2>/dev/null && alive="$alive $pid"
done

if [ -n "$alive" ]; then
    echo "force kill stale package manager processes:$alive"
    kill -KILL $alive 2>/dev/null || true
    sleep 2
fi

still_alive=""
for pid in $targets; do
    kill -0 "$pid" 2>/dev/null || continue
    stat="$(ps -o stat= -p "$pid" 2>/dev/null)"
    case "$stat" in
        Z*)
            ;;
        *)
            still_alive="$still_alive $pid"
            ;;
    esac
done

if [ -n "$still_alive" ]; then
    echo "package manager processes are still alive after SIGKILL:$still_alive"
    exit 2
fi
""" % pids
    r, o, e = bash_roe(cmd)
    if r != 0:
        return False, e or o
    return True, None


def _list_blocking_rpmdb_users(include_lock_files=False):
    cmd = r"""
dbpath="$(rpm --eval '%{_dbpath}' 2>/dev/null)"
[ -n "$dbpath" ] || exit 2
include_lock_files="__INCLUDE_LOCK_FILES__"
pgid="$(ps -o pgid= -p $$ 2>/dev/null | tr -d ' ')"
for fd in /proc/[0-9]*/fd/*; do
    target="$(readlink "$fd" 2>/dev/null)" || continue
    case "$target" in
        "$dbpath"/__db.*)
            [ "$include_lock_files" = "true" ] || continue
            pid="${fd#/proc/}"
            pid="${pid%%/*}"
            ;;
        "$dbpath"/*)
            pid="${fd#/proc/}"
            pid="${pid%%/*}"
            ;;
        *)
            continue
            ;;
    esac

    [ "$pid" = "$$" ] && continue
    [ "$pid" = "$PPID" ] && continue
    proc_pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
    [ -n "$pgid" ] && [ "$proc_pgid" = "$pgid" ] && continue
    echo "$pid"
done | sort -u
""".replace("__INCLUDE_LOCK_FILES__",
            "true" if include_lock_files else "false")
    r, o, e = bash_roe(cmd)
    if r != 0:
        return None, e or o
    return [pid for pid in o.split() if pid.isdigit()], None


def _backup_and_rebuild_rpmdb():
    cmd = r"""
dbpath="$(rpm --eval '%{_dbpath}' 2>/dev/null)"
[ -n "$dbpath" ] || exit 2
RPMDB_BACKUP_DIR="/var/lib/zstack/rpmdb-backups"
mkdir -p "$RPMDB_BACKUP_DIR" || exit 2
backup_file="$RPMDB_BACKUP_DIR/rpmdb-$(date +%Y%m%d%H%M%S).tar.gz"

if [ -d "$dbpath" ]; then
    timeout -k 10s 120s tar czf "$backup_file" -C "$(dirname "$dbpath")" "$(basename "$dbpath")" || exit 2
fi
ls -1t "$RPMDB_BACKUP_DIR"/rpmdb-*.tar.gz 2>/dev/null | awk 'NR > 5' | xargs -r rm -f

rm -f "$dbpath"/__db.* || exit 2
timeout -k 10s 180s rpm --rebuilddb || exit 2
timeout -k 5s 30s rpm -qa >/dev/null || exit 2
"""
    r, o, e = bash_roe(cmd)
    if r != 0:
        return False, e or o
    return True, None


def repair_rpmdb_if_damaged_on_host():
    if _yum_rpmdb_check():
        return True, None

    success, error = _check_rpmdb_repair_prerequisites()
    if not success:
        return False, error

    success, error = _remove_stale_yum_pid_files()
    if not success:
        return False, error
    if _yum_rpmdb_check():
        return True, None

    processes, error = _list_package_processes()
    if error:
        return False, error

    error = _check_d_state_package_processes(processes)
    if error:
        return False, error

    yum_failed_without_processes, error = _yum_failed_without_package_processes(
        processes)
    if yum_failed_without_processes:
        return False, error

    yum_failed_with_healthy_rpmdb, error = _yum_failed_with_healthy_rpmdb(
        processes)
    if yum_failed_with_healthy_rpmdb:
        return False, error

    core_rpmdb_is_in_use, error = _core_rpmdb_is_in_use(processes)
    if error:
        return False, error
    if core_rpmdb_is_in_use:
        return False, error

    young_processes = [p for p in processes
                       if p['etimes'] < RPMDB_REPAIR_STALE_SECONDS]
    if young_processes:
        time.sleep(RPMDB_REPAIR_WAIT_SECONDS)
        if _yum_rpmdb_check():
            return True, None

        processes, error = _list_package_processes()
        if error:
            return False, error

        error = _check_d_state_package_processes(processes)
        if error:
            return False, error

        yum_failed_without_processes, error = \
            _yum_failed_without_package_processes(processes)
        if yum_failed_without_processes:
            return False, error

        yum_failed_with_healthy_rpmdb, error = \
            _yum_failed_with_healthy_rpmdb(processes)
        if yum_failed_with_healthy_rpmdb:
            return False, error

        core_rpmdb_is_in_use, error = _core_rpmdb_is_in_use(processes)
        if error:
            return False, error
        if core_rpmdb_is_in_use:
            return False, error

        error = _check_young_package_processes(processes)
        if error:
            return False, error

    success, error = _terminate_package_processes(processes)
    if not success:
        return False, error

    processes, error = _list_package_processes()
    if error:
        return False, error

    error = _check_d_state_package_processes(processes)
    if error:
        return False, error

    yum_failed_with_healthy_rpmdb, error = _yum_failed_with_healthy_rpmdb(
        processes)
    if yum_failed_with_healthy_rpmdb:
        return False, error

    core_rpmdb_is_in_use, error = _core_rpmdb_is_in_use(processes)
    if error:
        return False, error
    if core_rpmdb_is_in_use:
        return False, error

    if processes:
        return False, ("package manager processes are still running after "
                       "stale process cleanup; skip rpmdb rebuild. pids: %s" %
                       _format_package_process_pids(processes))

    success, error = _remove_stale_yum_pid_files()
    if not success:
        return False, error

    if _yum_rpmdb_check():
        return True, None
    if _rpmdb_check():
        return False, ("yum cannot list installed packages but rpmdb is "
                       "healthy after clearing package manager processes; "
                       "skip rpmdb rebuild and check yum configuration or "
                       "plugins")

    rpmdb_users, error = _list_blocking_rpmdb_users(include_lock_files=True)
    if error:
        return False, error
    if rpmdb_users:
        return False, "rpmdb is still opened by processes: %s" % \
            ','.join(rpmdb_users)

    success, error = _backup_and_rebuild_rpmdb()
    if not success:
        return False, error

    if not _yum_rpmdb_check():
        return False, ("rpmdb repair finished but yum still cannot list "
                       "installed packages")

    return True, None


class HostPlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''

    CONNECT_PATH = '/host/connect'
    CAPACITY_PATH = '/host/capacity'
    ECHO_PATH = '/host/echo'
    FACT_PATH = '/host/fact'
    PING_PATH = "/host/ping"
    CHECK_FILE_ON_HOST_PATH = '/host/checkfile'
    GET_USB_DEVICES_PATH = "/host/usbdevice/get"
    SETUP_MOUNTABLE_PRIMARY_STORAGE_HEARTBEAT = "/host/mountableprimarystorageheartbeat"
    UPDATE_OS_PATH = "/host/updateos"
    INIT_HOST_MOC_PATH = "/host/initmoc"
    UPDATE_DEPENDENCY = "/host/updatedependency"
    ENABLE_HUGEPAGE = "/host/enable/hugepage"
    DISABLE_HUGEPAGE = "/host/disable/hugepage"
    CLEAN_LOCAL_CACHE = "/host/imagestore/cleancache"
    HOST_START_USB_REDIRECT_PATH = "/host/usbredirect/start"
    HOST_STOP_USB_REDIRECT_PATH = "/host/usbredirect/stop"
    CHECK_USB_REDIRECT_PORT = "/host/usbredirect/check"
    IDENTIFY_HOST = "/host/identify"
    LOCATE_HOST_NETWORK_INTERFACE = "/host/locate/networkinterface"
    GET_HOST_PHYSICAL_MEMORY_FACTS = "/host/physicalmemoryfacts"
    UPDATE_HOST_OVS_CPU_PINNING = "/host/ovs/cpu-pin/update"
    CHANGE_PASSWORD = "/host/changepassword"
    GET_HOST_NETWORK_FACTS = "/host/networkfacts"
    SET_IP_ON_HOST_NETWORK_INTERFACE = "/host/setip/networkinterface"
    CHECK_INTERFACE_VLAN = "/host/checkvlan/networkinterface"
    GET_INTERFACE_VLAN = "/host/getvlan/networkinterface"
    GET_INTERFACE_NAME = "/host/getname/networkinterface"

    HOST_XFS_SCRAPE_PATH = "/host/xfs/scrape"
    HOST_SHUTDOWN = "/host/shutdown"
    HOST_REBOOT = "/host/reboot"
    GET_PCI_DEVICES = "/pcidevice/get"
    CREATE_PCI_DEVICE_ROM_FILE = "/pcidevice/createrom"
    GENERATE_SRIOV_PCI_DEVICES = "/pcidevice/generate"
    UNGENERATE_SRIOV_PCI_DEVICES = "/pcidevice/ungenerate"
    GENERATE_VFIO_MDEV_DEVICES = "/mdevdevice/generate"
    UNGENERATE_VFIO_MDEV_DEVICES = "/mdevdevice/ungenerate"
    GET_MTTY_DEVICES = "/mttydevice/get"
    GENERATE_SE_VFIO_MDEV_DEVICES = "/semdevdevice/generate"
    UNGENERATE_SE_VFIO_MDEV_DEVICES = "/semdevdevice/ungenerate"
    DELETE_VFIO_MDEV_DEVICE = "/mdevdevice/delete"
    HOST_UPDATE_SPICE_CHANNEL_CONFIG_PATH = "/host/updateSpiceChannelConfig"
    TRANSMIT_VM_OPERATION_TO_MN_PATH = "/host/transmitvmoperation"
    TRANSMIT_ZWATCH_INSTALL_RESULT_TO_MN_PATH = "/host/zwatchInstallResult"
    SCAN_VM_PORT_PATH = "/host/vm/scanport"
    ENABLE_ZEROCOPY = "/host/enable/zerocopy"
    DISABLE_ZEROCOPY = "/host/disable/zerocopy"
    GET_DEV_CAPACITY = "/host/dev/capacity"
    ADD_BRIDGE_FDB_ENTRY_PATH = "/bridgefdb/add"
    DEL_BRIDGE_FDB_ENTRY_PATH = "/bridgefdb/delete"
    DEPLOY_COLO_QEMU_PATH = "/deploy/colo/qemu"
    UPDATE_CONFIGURATION_PATH = "/host/update/configuration"
    GET_NUMA_TOPOLOGY_PATH = "/numa/topology"
    ATTACH_VOLUME_PATH = "/host/volume/attach"
    DETACH_VOLUME_PATH = "/host/volume/detach"
    UPDATE_VM_CONSOLE_PASSWORD_LIVE_PATH = "/host/vm/updateConsolePassword/live"
    SETUP_VM_HA_ENABLED_METADATA_LIVE_PATH = '/host/vm/setupHaEnabledMetadata/live'
    RECONCILE_VM_HA_ENABLED_METADATA_LIVE_PATH = '/host/vm/reconcileHaEnabledMetadata/live'
    GET_BLOCK_DEVICES_PATH = "/host/blockdevices"

    def __init__(self):
        self.IS_YUM = False
        self.IS_APT = False
        self.NVIDIA_SMI_INSTALLED = False
        self._first_connect_after_boot = True
        self._agent_start_time_millis = int(time.time() * 1000)

        if shell.run("which yum") == 0:
            self.IS_YUM = True
        elif shell.run("which apt") == 0:
            self.IS_APT = True

        if shell.run("which nvidia-smi") == 0:
            self.NVIDIA_SMI_INSTALLED = True

    def get_clean_rule(self, item):
        rule = item.strip()
        if rule[0] == '"' or rule[0] == "'":
            rule = eval(rule).strip()
        return rule

    @lock.file_lock('/run/xtables.lock')
    @in_bash
    def apply_iptables_rules(self, rules):
        logger.debug("starting add iptables rules : %s" % rules)
        if len(rules) != 0 and rules is not None:
            for item in rules:
                rule = self.get_clean_rule(item)
                if ' '.join(rule.split(' ')[:1]) == '-N':
                    clean_rule = ' '.join(rule.split(' ')[1:])
                    ret = bash_r("iptables -w -S %s " % clean_rule)
                else:
                    clean_rule = ' '.join(rule.split(' ')[1:])
                    ret = bash_r("iptables -w -C %s " % clean_rule)
                if ret == 0:
                    continue
                elif ret == 1:
                    # didn't find this rule
                    set_rules_ret = bash_r("iptables -w %s" % rule)
                    if set_rules_ret != 0:
                        raise Exception('cannot set iptables rule: %s' % rule)
                else:
                    raise Exception('check iptables rule: %s failed' % rule)
        return True

    @kvmagent.replyerror
    def connect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConnectResponse()
        rsp.agentStartTimeMillis = self._agent_start_time_millis
        rsp.firstConnect = self._first_connect_after_boot

        # page table extension
        if shell.run('lscpu | grep -q -w GenuineIntel') == 0:
            new_ept = False if cmd.pageTableExtensionDisabled else True
            rsp.error = self._set_intel_ept(new_ept)
            if rsp.error is not None:
                rsp.success = False
                return jsonobject.dumps(rsp)

        self.host_uuid = cmd.hostUuid
        self.config[kvmagent.HOST_UUID] = self.host_uuid
        self.config[kvmagent.SEND_COMMAND_URL] = cmd.sendCommandUrl
        self.config[kvmagent.VERSION] = cmd.version
        Report.serverUuid = self.host_uuid
        Report.url = cmd.sendCommandUrl
        logger.debug(http.path_msg(self.CONNECT_PATH,
                     'host[uuid: %s] connected' % cmd.hostUuid))
        rsp.libvirtVersion = self.libvirt_version
        rsp.qemuVersion = self.qemu_version

        # save kvmagent version
        self.save_kvmagent_version(cmd.version)

        self.install_shutdown_hook(cmd)

        # create udev rule
        self.handle_usb_device_events()

        ignore_msrs = "1" if cmd.ignoreMsrs else "0"
        linux.write_file('/sys/module/kvm/parameters/ignore_msrs', ignore_msrs)

        linux.write_uuids("host", "host=%s" % self.host_uuid)

        vm_plugin.cleanup_stale_vnc_iptable_chains()
        self.apply_iptables_rules(cmd.iptablesRules)

        if self.host_socket is not None:
            self.host_socket.close()
            self.host_socket = None

        ip_address = network_ipv6.extract_url_host(cmd.sendCommandUrl)
        try:
            self.host_socket = network_ipv6.create_tcp_socket_for_host(ip_address)
            self.host_socket.connect((ip_address, cmd.tcpServerPort))

        except socket.error as msg:
            if self.host_socket is not None:
                self.host_socket.close()
            self.host_socket = None

        self.start_write_to_server()

        # remove old rules for vf nic
        bash_r(get_ebtables_cmd() + ' -D FORWARD -j ZSTACK-VF-NICS')
        bash_r(get_ebtables_cmd() + ' -X ZSTACK-VF-NICS')

        self._first_connect_after_boot = False
        return jsonobject.dumps(rsp)

    @thread.AsyncThread
    def start_write_to_server(self):
        pkt_counter = 0
        while True:
            try:
                self.host_socket.send(str(pkt_counter).encode())
            except Exception as e:
                logger.debug("failed to send pkg to mn")
                break

            if pkt_counter == sys.maxsize:
                pkt_counter = 0

            pkt_counter += 1
            time.sleep(2)

    @kvmagent.replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        kvmagent.kvmagent_physical_memory_usage_alarm_threshold = cmd.kvmagentPhysicalMemoryUsageAlarmThreshold
        kvmagent.kvmagent_physical_memory_usage_hardlimit = cmd.kvmagentPhysicalMemoryUsageHardLimit
        rsp = PingResponse()
        rsp.hostUuid = self.host_uuid
        rsp.sendCommandUrl = self.config.get(kvmagent.SEND_COMMAND_URL)
        rsp.version = self.config.get(kvmagent.VERSION)

        if rsp.version is None and os.path.exists(KVMAGENT_VERSION_PATH):
            with open(KVMAGENT_VERSION_PATH, 'r') as rfd:
                rsp.version = rfd.read().strip()

        if os.path.exists(HOST_TAKEOVER_FLAG_PATH):
            linux.touch_file(HOST_TAKEOVER_FLAG_PATH)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_file_on_host(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckFileOnHostResponse()
        for file_path in cmd.paths:
            if not os.path.exists(file_path):
                continue
            rsp.existPaths[file_path] = ""
            if not cmd.md5Return:
                continue
            with open(file_path, 'rb') as data:
                try:
                    rsp.existPaths[file_path] = hashlib.md5(
                        data.read()).hexdigest()
                except IOError as err:
                    logger.debug('can not open file %s because IOError: %s' % (
                        file_path, str(err)))
                    pass
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def echo(self, req):
        logger.debug('get echoed')
        loop = 0
        while linux.fake_dead('kvmagent') is True and loop < 1200:
            logger.debug('checked fake dead, sleep 3 secs')
            time.sleep(3)
            loop += 1
        return ''

    def _cache_units_convert(self, str):
        if str is None or str == '':
            return 0
        return float(sizeunit.get_size(str) // 1024)

    @kvmagent.replyerror
    def fact(self, req):
        rsp = HostFactResponse()
        os_info = platform.freedesktop_os_release()
        rsp.osDistribution = os_info['ID']
        rsp.osVersion = re.sub(r'[a-zA-Z]+$', '', os_info['VERSION_ID'])
        rsp.osRelease = "Core" # TODO get os release
        # compatible with Kylin SP2 HostOS ISO and standardized ISO
        if rsp.osDistribution == "kylin":
            rsp.osRelease = rsp.osRelease.replace('ZStack', 'Sword')
        elif rsp.osDistribution == "helix":
            rsp.osRelease = "release"
        elif rsp.osDistribution == "alinux":
            rsp.osRelease = "release"
        # to be compatible with both `2.6.0` and
        # `2.9.0(qemu-kvm-ev-2.9.0-16.el7_4.8.1)`
        qemu_img_version = shell.call(
            "qemu-img --version | grep 'qemu-img version' | cut -d ' ' -f 3 | cut -d '(' -f 1")
        qemu_img_version = qemu_img_version.strip('\t\r\n ,')
        ip_addrs = network_ipv6.collect_reportable_agent_addresses(iproute)


        def run_dmidecode(cmd, default=''):
            try:
                ret = shell.call(cmd).strip()
                return ret if ret else default
            except Exception as e:
                logger.warn("run dmidecode cmd %s failed: %s" % (cmd, e))
                return default

        is_dmidecode = shell.run("dmidecode")
        if str(is_dmidecode) == '0':
            rsp.systemSerialNumber = run_dmidecode(
                'dmidecode -s system-serial-number', 'unknown')
            system_product_name = run_dmidecode(
                'dmidecode -s system-product-name')
            if system_product_name:
                rsp.systemProductName = system_product_name
            else:
                rsp.systemProductName = run_dmidecode(
                    'dmidecode -s baseboard-product-name')
            rsp.systemManufacturer = run_dmidecode(
                'dmidecode -s system-manufacturer', 'unknown')
            rsp.systemUUID = run_dmidecode(
                'dmidecode -s system-uuid', 'unknown')
            rsp.biosVendor = run_dmidecode(
                'dmidecode -s bios-vendor', 'unknown')
            rsp.biosVersion = run_dmidecode(
                'dmidecode -s bios-version', 'unknown')
            rsp.biosReleaseDate = run_dmidecode(
                'dmidecode -s bios-release-date', 'unknown')
            rsp.memorySlotsMaximum = run_dmidecode(
                'dmidecode -q -t memory | grep "Memory Device" | wc -l')
            rsp.powerSupplyManufacturer = run_dmidecode(
                "dmidecode -t 39 | grep -vi 'not specified' | grep -m1 'Manufacturer' | awk -F ':' '{print $2}'", 'unknown')
            rsp.powerSupplyModelName = run_dmidecode(
                "dmidecode -t 39 | grep -vi 'not specified' | grep -m1 'Name' | awk -F ':' '{print $2}'", 'unknown')
            power_supply_max_power_capacity = run_dmidecode(
                "dmidecode -t 39 | grep -vi 'unknown' | grep -m1 'Max Power Capacity' | awk -F ':' '{print $2}'")
            if bool(re.search(r'\d', power_supply_max_power_capacity)):
                rsp.powerSupplyMaxPowerCapacity = ''.join(re.findall(r'\d+', power_supply_max_power_capacity.strip()))

        rsp.qemuImgVersion = qemu_img_version
        qemu_package_name = "qemu" if IS_AARCH64 else "qemu-kvm"
        if self.IS_YUM:
            try:
                rsp.qemuKvmPackageVersion = linux.get_rpm_version(qemu_package_name)
            except Exception as e:
                logger.error("failed to get %s rpm version for host[uuid:%s]: %s" % (qemu_package_name, self.host_uuid, str(e)))
                rsp.qemuKvmPackageVersion = None
        else:
            logger.debug("%s package version is only reported on RPM-based host[uuid:%s]; automatic IOThread VQ mapping capability will not be enabled" % (qemu_package_name, self.host_uuid))
        rsp.libvirtVersion = self.libvirt_version
        rsp.libvirtPackageVersion = linux.get_libvirt_package_version()
        rsp.ipAddresses = ip_addrs
        rsp.cpuArchitecture = platform.machine()
        rsp.uptime = shell.call('uptime -s').strip()
        rsp.iscsiInitiatorName = linux.get_iscsi_initiator_name()

        if not IS_LOONGARCH64:
            libvirtCapabilitiesList = []
            features = self._get_features_in_libvirt()
            if features and features.hasattr("incrementaldrivemirror"):
                libvirtCapabilitiesList.append("incrementaldrivemirror")
            if features and features.hasattr("blockcopynetworktarget"):
                libvirtCapabilitiesList.append("blockcopynetworktarget")
            rsp.libvirtCapabilities = libvirtCapabilitiesList

        bmc_version = shell.call(
            "ipmitool mc info | grep 'Firmware Revision' | awk -F ':' '{print $2}'").strip()
        rsp.bmcVersion = bmc_version if bmc_version else 'unknown'

        # To see which lan the BMC is listening on, try the following (1-11),
        # https://wiki.docking.org/index.php/Configuring_IPMI
        for channel in range(1, 12):
            '''
            example:
            except result:         IP Address              : xxx.xxx.xxx.xxx
            set ipmi_address "None" when got results unexpected or happened some errors
            '''
            ret, out, err = bash_roe(
                "ipmitool lan print %s | grep -w 'IP Address'| grep -v 'Source'" % channel)
            if ret == 0 and out != "":
                rsp.ipmiAddress = out.split(":")[1].strip()
                break
            else:
                rsp.ipmiAddress = 'None'
                logger.debug(
                    "failed to get ipmi address from BMC lan channel [%s], because %s" % (channel, err))

        rsp.deployMode = 'cube' if misc.isHyperConvergedHost() else 'cloud'

        if IS_AARCH64:
            # FIXME how to check vt of aarch64?
            rsp.hvmCpuFlag = 'vt'
            cpu_model = None
            try:
                cpu_model = self._get_host_cpu_model()
            except AttributeError:
                logger.debug(
                    "maybe XmlObject has no attribute model, use uname -p to get one")
                if cpu_model is None:
                    cpu_model = os.uname()[-1]

            rsp.cpuModelName = cpu_model
            host_cpu_model_name = shell.call(
                "lscpu | awk -F':' '/Model name/{print $2}'")
            rsp.hostCpuModelName = host_cpu_model_name.strip(
            ) if host_cpu_model_name else "aarch64"

            cpuMHz = shell.call("lscpu | awk '/max MHz/{ print $NF }'")
            # in case lscpu doesn't show cpu max mhz
            cpuMHz = "2500.0000" if cpuMHz.strip() == '' else cpuMHz
            rsp.cpuGHz = '%.2f' % (float(cpuMHz) / 1000)
            cpu_cores_per_socket = shell.call(
                "lscpu | awk -F':' '/per socket/{print $NF}'")
            # On openeuler, lscpu otuputs 'per cluster' instead of 'per socket'
            if not cpu_cores_per_socket:
                cpu_cores_per_socket = shell.call(
                    "lscpu | awk -F':' '/per cluster/{print $NF}'")
            cpu_threads_per_core = shell.call(
                "lscpu | awk -F':' '/per core/{print $NF}'")
            sockets = linux.get_socket_num()
            rsp.cpuProcessorNum = int(
                cpu_cores_per_socket.strip()) * int(cpu_threads_per_core) * sockets

            '''
            examples:
                    lscpu | grep 'L1i cache'
                    L1i cache:                       768 KiB
                    lscpu | grep 'L1d cache'
                    L1d cache:                       768 KiB
            '''

            cpu_cache_list = self._get_cpu_cache()
            rsp.cpuCache = ",".join(str(cache) for cache in cpu_cache_list)

        elif IS_MIPS64EL or IS_LOONGARCH64:
            rsp.hvmCpuFlag = 'vt'
            cpu_model = None
            try:
                cpu_model = self._get_host_cpu_model()
            except AttributeError:
                logger.debug("maybe XmlObject has no attribute model, use uname -p to get one")
                if cpu_model is None:
                    cpu_model = os.uname()[-1]
            rsp.cpuModelName = cpu_model

            host_cpu_info = shell.call(
                "grep -m2 -P -o -i '(model name|cpu MHz)\\s*:\\s*\\K.*' /proc/cpuinfo").splitlines()
            host_cpu_model_name = host_cpu_info[0]
            rsp.hostCpuModelName = host_cpu_model_name

            transient_cpuGHz = '%.2f' % (float(host_cpu_info[1]) / 1000)
            static_cpuGHz_re = re.search('[0-9.]*GHz', host_cpu_model_name)
            rsp.cpuGHz = static_cpuGHz_re.group(
                0)[:-3] if static_cpuGHz_re else transient_cpuGHz
        else:
            if shell.run('grep vmx /proc/cpuinfo') == 0:
                rsp.hvmCpuFlag = 'vmx'

            if not rsp.hvmCpuFlag:
                if shell.run('grep svm /proc/cpuinfo') == 0:
                    rsp.hvmCpuFlag = 'svm'

            if shell.run('grep -w ept /proc/cpuinfo') == 0:
                rsp.eptFlag = 'ept'

            rsp.cpuModelName = self._get_host_cpu_model()

            host_cpu_info = shell.call(
                "grep -m2 -P -o '(model name|cpu MHz)\\s*:\\s*\\K.*' /proc/cpuinfo").splitlines()
            host_cpu_model_name = host_cpu_info[0]
            rsp.hostCpuModelName = host_cpu_model_name

            transient_cpuGHz = '%.2f' % (float(host_cpu_info[1]) / 1000)
            static_cpuGHz_re = re.search('[0-9.]*GHz', host_cpu_model_name)
            rsp.cpuGHz = static_cpuGHz_re.group(
                0)[:-3] if static_cpuGHz_re else transient_cpuGHz

            cpu_cores_per_socket = shell.call(
                "lscpu | awk -F':' '/per socket/{print $NF}'")
            # On openeuler, lscpu otuputs 'per cluster' instead of 'per socket'
            if not cpu_cores_per_socket:
                cpu_cores_per_socket = shell.call(
                    "lscpu | awk -F':' '/per cluster/{print $NF}'")
            cpu_threads_per_core = shell.call(
                "lscpu | awk -F':' '/per core/{print $NF}'")
            sockets = linux.get_socket_num()
            rsp.cpuProcessorNum = int(
                cpu_cores_per_socket.strip()) * int(cpu_threads_per_core) * sockets

            cpu_cache_list = self._get_cpu_cache()
            rsp.cpuCache = ",".join(str(cache) for cache in cpu_cache_list)

        # get virtualizer info
        rsp.virtualizerInfo.uuid = self.config.get(kvmagent.HOST_UUID)
        rsp.virtualizerInfo.virtualizer = "qemu-kvm"
        rsp.virtualizerInfo.version = qemu.get_version_from_exe_file(
            qemu.get_path())

        # get CPU feature MD5 for migration compatibility check
        sh_cmd = shell.ShellCmd(
            'virsh capabilities | virsh cpu-baseline /dev/stdin')
        sh_cmd(False)
        if sh_cmd.return_code == 0 and sh_cmd.stdout.strip():
            rsp.cpuFeatureMd5 = hashlib.md5(
                sh_cmd.stdout.strip().encode()).hexdigest()

        return jsonobject.dumps(rsp)

    @vm_plugin.LibvirtAutoReconnect
    def _get_features_in_libvirt(conn):
        try:
            xml_object = xmlobject.loads(conn.getCapabilities())
            # The number of guest is one, and len will cause an error
            if not isinstance(xml_object.guest, list):
                return xml_object.guest
            if len(xml_object.guest) > 0:
                return xml_object.guest[0].features
            return None
        except (AttributeError, KeyError):
            return None

    @vm_plugin.LibvirtAutoReconnect
    def _get_host_cpu_model(conn):
        xml_object = xmlobject.loads(conn.getCapabilities())
        return str(xml_object.host.cpu.model.text_)

    @vm_plugin.LibvirtAutoReconnect
    def _get_node_info(conn):
        return conn.getInfo()

    @kvmagent.replyerror
    def _get_cpu_cache(self):
        class CpuCache(object):
            def __init__(self):
                self.cpuL1iCache = 0
                self.cpuL1dCache = 0
                self.cpuL2Cache = 0
                self.cpuL3Cache = 0

        cache = CpuCache()
        cpu_cache_lines = shell.call("lscpu")
        for c_line in cpu_cache_lines.splitlines():
            if re.search('L1d cache', c_line):
                cache.cpuL1dCache = self._cache_units_convert(
                    c_line.split(':')[1].strip())
            elif re.search('L1i cache', c_line):
                cache.cpuL1iCache = self._cache_units_convert(
                    c_line.split(':')[1].strip())
            elif re.search('L2 cache', c_line):
                cache.cpuL2Cache = self._cache_units_convert(
                    c_line.split(':')[1].strip())
            elif re.search('L3 cache', c_line):
                cache.cpuL3Cache = self._cache_units_convert(
                    c_line.split(':')[1].strip())

        cpu_l1_cache = cache.cpuL1dCache + cache.cpuL1iCache
        cpuCacheList = [cpu_l1_cache, cache.cpuL2Cache, cache.cpuL3Cache]
        return cpuCacheList

    @kvmagent.replyerror
    @in_bash
    def capacity(self, req):
        rsp = HostCapacityResponse()
        rsp.cpuNum = linux.get_cpu_num()
        rsp.cpuSpeed = linux.get_cpu_speed()
        (used_cpu, used_memory) = vm_plugin.get_cpu_memory_used_by_running_vms()
        rsp.usedCpu = used_cpu
        rsp.totalMemory = _get_total_memory()
        rsp.usedMemory = used_memory
        rsp.cpuSockets = linux.get_socket_num()
        rsp.cpuCoreNum = linux.get_cpu_core_num()

        return jsonobject.dumps(rsp)

    def _heartbeat_func(self, heartbeat_file):
        class Heartbeat(object):
            def __init__(self):
                self.current = None

        hb = Heartbeat()
        hb.current = time.time()
        with open(heartbeat_file, 'w') as fd:
            fd.write(jsonobject.dumps(hb))
        return True

    def _get_intel_ept(self):
        text = None
        with open('/sys/module/kvm_intel/parameters/ept', 'r') as reader:
            text = reader.read()
        return text is None or text.strip() == "Y"

    def _set_intel_ept(self, new_ept):
        error = None
        old_ept = self._get_intel_ept()
        if new_ept != old_ept:
            param = "ept=%d" % new_ept
            if shell.run(
                    "modprobe -r kvm-intel") != 0 or shell.run("modprobe kvm-intel %s" % param) != 0:
                error = "failed to reload kvm-intel, please stop the running VM on the host and try again."
            else:
                with open('/etc/modprobe.d/intel-ept.conf', 'w') as writer:
                    writer.write("options kvm_intel %s" % param)
                logger.info("_set_intel_ept(%s) OK." % new_ept)

        if error is not None:
            logger.warn("_set_intel_ept: %s" % error)
        return error

    @kvmagent.replyerror
    def setup_heartbeat_file(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetupMountablePrimaryStorageHeartbeatResponse()

        for hb in cmd.heartbeatFilePaths:
            hb_dir = os.path.dirname(hb)
            mount_path = os.path.dirname(hb_dir)
            if not linux.is_mounted(mount_path):
                rsp.error = '%s is not mounted, setup heartbeat file[%s] failed' % (
                    mount_path, hb)
                rsp.success = False
                return jsonobject.dumps(rsp)

        for hb in cmd.heartbeatFilePaths:
            t = self.heartbeat_timer.get(hb, None)
            if t:
                t.cancel()

            hb_dir = os.path.dirname(hb)
            if not os.path.exists(hb_dir):
                os.makedirs(hb_dir, 0o755)

            t = thread.timer(cmd.heartbeatInterval, self._heartbeat_func, args=[
                             hb], stop_on_exception=False)
            t.start()
            self.heartbeat_timer[hb] = t
            logger.debug('create heartbeat file at[%s]' % hb)

        return jsonobject.dumps(rsp)

    def _get_next_available_port(self):
        for port in range(4100, 4200):
            if bash_r(
                    "netstat -nap | grep :%s[[:space:]] | grep LISTEN" % port) != 0:
                return port
        raise kvmagent.KvmError(
            'no more available port for start usbredirect server')

    @kvmagent.replyerror
    @in_bash
    def start_usb_redirect_server(self, req):
        def _start_usb_server(port, busNum, devNum):
            iptc = iptables.from_iptables_save()
            iptc.add_rule('-A INPUT -p tcp -m tcp --dport %s -j ACCEPT' % port)
            iptc.iptable_restore()
            systemd_service_name = "usbredir-%s-%s-%s" % (port, busNum, devNum)
            if bash_r("systemctl list-units |grep %s" %
                      systemd_service_name) == 0:
                bash_r("systemctl start %s" % systemd_service_name)
            else:
                bash_r("systemd-run --unit %s usbredirserver -p %s %s-%s" %
                       (systemd_service_name, port, busNum, devNum))

            ret, output = linux.check_port('127.0.0.1', port)
            if not ret:
                logger.info("usb %s-%s start failed on port %s" %
                            (busNum, devNum, port))
                return False, output
            logger.info("usb %s-%s start successed on port %s" %
                        (busNum, devNum, port))
            return True, None

        def _check_usb_device_exist(busNum, devNum):
            ret, output = bash_ro("lsusb -s %s:%s" % (busNum, devNum))
            if ret == 0:
                return True

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = StartUsbRedirectServerRsp()
        port = cmd.port if cmd.port is not None else self._get_next_available_port()
        if not _check_usb_device_exist(cmd.busNum, cmd.devNum):
            rsp.success = False
            rsp.error = "usb device[busNum: %s, deviceNum: %s does not exists." % (
                cmd.busNum, cmd.devNum)
            return jsonobject.dumps(rsp)

        ret, output = _start_usb_server(int(port), cmd.busNum, cmd.devNum)
        if ret:
            rsp.port = int(port)
            return jsonobject.dumps(rsp)
        else:
            rsp.success = False
            rsp.error = output
            return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def stop_usb_redirect_server(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = StopUsbRedirectServerRsp()
        if bash_r(
                "netstat -nap | grep :%s[[:space:]] | grep LISTEN | grep usbredir" % cmd.port) != 0:
            logger.info("port %s is not occupied by usbredir" % cmd.port)
        bash_r("systemctl stop usbredir-%s-%s-%s" %
               (cmd.port, cmd.busNum, cmd.devNum))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def check_usb_server_port(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckUsbServerPortRsp()
        r, o, e = bash_roe(
            "netstat -nap | grep LISTEN | grep usbredir  | awk '{print $4}' | awk -F ':' '{ print $4 }'")
        if r != 0:
            rsp.success = False
            rsp.error = "unable to get started usb server port"
            return jsonobject.dumps(rsp)
        existPort = o.split("\n")
        for value in cmd.portList:
            uuid = str(value).split(":")[0]
            port = str(value).split(":")[1]
            if port not in existPort:
                rsp.uuids.append(uuid)
                continue
            existPort.remove(port)
        # kill stale usb server
        for port in existPort:
            bash_r("systemctl stop usbredir-%s" % port)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def get_usb_devices(self, req):
        usb_device_infos = []

        class UsbDeviceInfo(object):
            def __init__(self):
                self.busNum = ""
                self.devNum = ""
                self.idVendor = ""
                self.idProduct = ""
                self.iManufacturer = ""
                self.iProduct = ""
                self.iSerial = ""
                self.usbVersion = ""

            def toString(self):
                return self.busNum + ':' + self.devNum + ':' + self.idVendor + ':' + self.idProduct + ':' + \
                    self.iManufacturer + ':' + self.iProduct + ':' + \
                    self.iSerial + ':' + self.usbVersion + ";"

        def append_usb_device(info, dev_id):
            if info.busNum == '' or info.devNum == '' or info.idVendor == '' or info.idProduct == '':
                logger.debug(
                    "cannot get busNum/devNum/idVendor/idProduct info in usbDevice %s, skip append" % dev_id)
            elif '(error)' in info.iManufacturer or '(error)' in info.iProduct:
                logger.debug(
                    "cannot get iManufacturer or iProduct info in usbDevice %s" % dev_id)
                usb_device_infos.append(info)
            else:
                usb_device_infos.append(info)

        # use 'lsusb.py -U' to get device ID, like '0751:9842'
        rsp = GetUsbDevicesRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        r, o, e = bash_roe("timeout 5 /usr/local/bin/lsusb.py -U")
        if r != 0:
            rsp.success = False
            rsp.error = "%s %s" % (e, o)
            return jsonobject.dumps(rsp)

        id_set = set()
        for line in o.split('\n'):
            line = line.split()
            if len(line) < 2:
                continue
            id_set.add(line[1])

        for dev_id in id_set:
            # use 'lsusb -v -d ID' to get device info[s]
            r, o, e = bash_roe("lsusb -v -d %s" % dev_id)
            if r != 0:
                rsp.success = False
                rsp.error = "%s %s" % (e, o)
                return jsonobject.dumps(rsp)

            for line in o.split('\n'):
                line = line.strip().split()
                if len(line) < 2:
                    continue

                if line[0] == 'Bus' and len(line) > 3:
                    info = UsbDeviceInfo()
                    info.idVendor, info.idProduct = dev_id.split(':')
                    info.busNum = line[1]
                    info.devNum = line[3].rsplit(':')[0]
                elif line[0] == 'idVendor':
                    info.iManufacturer = ' '.join(
                        line[2:]) if len(line) > 2 else ""
                elif line[0] == 'idProduct':
                    info.iProduct = ' '.join(line[2:]) if len(line) > 2 else ""
                elif line[0] == 'bcdUSB':
                    info.usbVersion = line[1]
                    # special case: USB2.0 with speed 1.5MBit/s or 12MBit/s
                    # should be attached to USB1.1 Controller
                    rst = bash_r(
                        "/usr/local/bin/lsusb.py | grep -v 'grep' | grep '%s' | grep -E '1.5MBit/s|12MBit/s'" % dev_id)
                    info.usbVersion = info.usbVersion if rst != 0 else '1.1'
                elif line[0] == 'iManufacturer' and len(line) > 2:
                    info.iManufacturer = ' '.join(line[2:])
                elif line[0] == 'iProduct' and len(line) > 2:
                    info.iProduct = ' '.join(line[2:])
                elif line[0] == 'iSerial':
                    info.iSerial = ' '.join(line[2:]) if len(line) > 2 else ""
                    append_usb_device(info, dev_id)

        rsp.usbDevicesInfo = usb_device_infos
        return jsonobject.dumps(rsp)

    @lock.file_lock('/run/usb_rules.lock')
    def handle_usb_device_events(self):
        bash_str = """#!/usr/bin/env python3.11
import os
import fcntl
import subprocess
import sys
import time
import urllib.request

EVENT_SCRIPT = "/usr/bin/_report_device_event.py"
DEFER_ENV = "ZSTACK_USB_EVENT_DEFERRED"
LOG_FILE = %s
LOCK_FILE = LOG_FILE[:-4] + ".lock" if LOG_FILE.endswith(".log") else LOG_FILE + ".lock"
LOG_NAME = %s


def log_error(msg):
    now = time.time()
    timestamp = time.strftime("%%Y-%%m-%%d %%H:%%M:%%S", time.localtime(now))
    timestamp = "%%s,%%03d" %% (timestamp, int((now - int(now)) * 1000))
    line = "%%s ERROR [%%s] zstack usb device event: %%s\\n" %% (
        timestamp, LOG_NAME, msg)
    fd = None
    lock_fd = None
    try:
        lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        fd = os.open(LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        os.write(fd, line.encode())
    except Exception:
        sys.stderr.write(line)
    finally:
        if fd is not None:
            os.close(fd)
        if lock_fd is not None:
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
            finally:
                lock_fd.close()


def defer_to_systemd():
    if os.environ.get(DEFER_ENV) or not os.environ.get("DEVPATH"):
        return False

    unit = "zs-usb-evt-%%s" %% int(time.time() * 1000)
    cmd = [
        "systemd-run", "--quiet", "--no-block", "--unit", unit,
        "--property", "Environment=%%s=1" %% DEFER_ENV,
        EVENT_SCRIPT
    ]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        stdout, stderr = proc.communicate()
        if proc.returncode == 0:
            return True
        log_error("udev defer failed: return code: %%s, stdout: %%s, stderr: %%s" %% (
            proc.returncode, stdout.strip(), stderr.strip()))
        return False
    except Exception as e:
        log_error("udev defer failed: %%s" %% e)
        return False


def post_msg(data, post_url):
    headers = {"content-type": "application/json", "commandpath": "/host/reportdeviceevent"}
    req = urllib.request.Request(post_url, data.encode(), headers)
    response = urllib.request.urlopen(req)
    response.close()

if __name__ == "__main__":
    if defer_to_systemd():
        raise SystemExit(0)
    try:
        post_msg("{'hostUuid':'%s'}", '%s')
    except Exception as e:
        path = "udev fallback" if os.environ.get("DEVPATH") else "direct"
        log_error("%%s report failed: %%s" %% (path, e))
        raise
""" % (repr(log.get_logfile_path()), repr(__name__), self.config.get(kvmagent.HOST_UUID), self.config.get(kvmagent.SEND_COMMAND_URL))

        event_report_script = '/usr/bin/_report_device_event.py'
        with open(event_report_script, 'w') as f:
            f.write(bash_str)
        os.chmod(event_report_script, 0o755)

        rule_str = 'ACTION=="add|remove", SUBSYSTEM=="usb", RUN+="%s"\n' % event_report_script
        rule_path = '/etc/udev/rules.d/'
        rule_file = os.path.join(rule_path, 'usb.rules')
        if not os.path.exists(rule_path):
            os.makedirs(rule_path)
        with open(rule_file, 'w') as f:
            f.write(rule_str)
        os.chmod(rule_file, 0o644)
        ret, stdout, stderr = bash_roe("udevadm control --reload-rules")
        if ret != 0:
            logger.error("failed to reload udev rules, return code: %s, stdout: %s, stderr: %s",
                         ret, stdout, stderr)

    @thread.AsyncThread
    def save_kvmagent_version(self, version):
        if os.path.exists(KVMAGENT_VERSION_PATH):
            with open(KVMAGENT_VERSION_PATH, 'r') as rfd:
                flag = True if version != rfd.read().strip() else False
        else:
            flag = True

        if flag:
            with open(KVMAGENT_VERSION_PATH, 'w') as fd:
                fd.write(version)

    def install_shutdown_hook(self, cmd):
        if not cmd.isInstallHostShutdownHook:
            shell_cmd = shell.ShellCmd(
                "rm -rf /etc/init.d/shutdown_vm && rm -rf /etc/rc1.d/K01shutdown_vm && rm -rf /etc/rc6.d/K01shutdown_vm && rm -rf /etc/rc0.d/K01shutdown_vm",
                None, False)
            shell_cmd(False)
            return

        shell_cmd = shell.ShellCmd(
            "/bin/cp -f %s %s && chmod 755 %s" % (KVMAGENT_SHUTDOWN_PATH, KVMAGENT_SHUTDOWN_INIT_PATH, KVMAGENT_SHUTDOWN_INIT_PATH), None, False)
        shell_cmd(False)
        if shell_cmd.return_code != 0:
            logger.debug("failed to copy %s to %s, stdout: %s, stderr: %s" % (
                KVMAGENT_SHUTDOWN_PATH, KVMAGENT_SHUTDOWN_INIT_PATH, shell_cmd.stdout, shell_cmd.stderr))
            return

        shell_cmd = shell.ShellCmd(
            "sed -i 's/send_command_url/%s/g; s/host_uuid/%s/g' /etc/init.d/shutdown_vm" % (cmd.sendCommandUrl, cmd.hostUuid) +
            " && ln -s -f /etc/init.d/shutdown_vm /etc/rc1.d/K01shutdown_vm "
            "&& ln -s -f /etc/init.d/shutdown_vm /etc/rc6.d/K01shutdown_vm "
            "&& ln -s -f /etc/init.d/shutdown_vm /etc/rc0.d/K01shutdown_vm "
            "&& chkconfig shutdown_vm on", None, False)
        shell_cmd(False)
        if shell_cmd.return_code != 0:
            logger.debug(
                "failed to chkconfig shutdown_vm on, stdout: %s, stderr: %s" % (shell_cmd.stdout, shell_cmd.stderr))

    @kvmagent.replyerror
    @in_bash
    @lock.file_lock('/run/zstack-yum.lock', locker=lock.Flock())
    def update_os(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        exclude = "--exclude=" + cmd.excludePackages if cmd.excludePackages else ""
        updates = cmd.updatePackages if cmd.updatePackages else ""
        releasever = cmd.releaseVersion if cmd.releaseVersion else kvmagent.get_host_yum_release()
        yum_cmd = "yum --enablerepo=* clean all && echo {}>/etc/yum/vars/YUM0 && ".format(
            releasever)
        # If upgrade qemu-kvm and libvirt at the same time
        # you need to upgrade qemu-kvm and then upgrade libvirt
        # to ensure that libvirtd is rebooted after upgrading qemu-kvm
        if "qemu-kvm" in updates or (cmd.releaseVersion !=
                                     '' and "qemu-kvm" not in exclude):
            update_qemu_cmd = "export YUM0={0};"
            if releasever in ['c74', 'c76', 'c79', 'h76c', 'h79c']:
                update_qemu_cmd += "yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{1} swap -y -- remove qemu-img-ev -- install qemu-img " \
                    "&& yum remove qemu-kvm-ev qemu-kvm-common-ev -y && yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{1} update " \
                    "qemu-storage-daemon -y && yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{1} install qemu-kvm qemu-kvm-common -y && "
            else:
                update_qemu_cmd += " yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{1} update qemu-storage-daemon -y;"
            # centos, helix, rocky, kylin using edk2-ovmf, ipxe-roms-qemu
            # seabios-bin seavgabios-bin, but h2203sp1o was not using them.
            if releasever not in ['h2203sp1o']:
                update_qemu_cmd += " yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{1} update edk2-ovmf ipxe-roms-qemu seabios-bin seavgabios-bin -y;"
            yum_cmd = yum_cmd + update_qemu_cmd.format(releasever,
                                                       ',zstack-experimental-mn' if cmd.enableExpRepo else '')
        if "libvirt" in updates or (
                cmd.releaseVersion != '' and "libvirt" not in exclude):
            update_libvirt_cmd = "export YUM0={};yum remove libvirt libvirt-libs libvirt-client libvirt-python libvirt-admin libvirt-bash-completion libvirt-daemon-driver-lxc -y {} && export YUM0={};" \
                                 "yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{} install libvirt libvirt-client libvirt-python -y && "
            yum_cmd = yum_cmd + update_libvirt_cmd.format(releasever,
                                                          '--noautoremove' if releasever in DISTRO_USING_DNF else '', releasever,
                                                          ',zstack-experimental-mn' if cmd.enableExpRepo else '')
        upgrade_os_cmd = "export YUM0={};yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{} {} update {} -y"
        yum_cmd = yum_cmd + upgrade_os_cmd.format(
            releasever, ',zstack-experimental-mn' if cmd.enableExpRepo else '', exclude, updates)

        if "kernel" in updates or (
                cmd.releaseVersion != '' and "kernel" not in exclude):
            dracut_conf_map = {
                '/etc/dracut.conf.d/no_lvmconf.conf': 'lvmconf=no',
                '/etc/dracut.conf.d/no_hostonly.conf': 'hostonly=no'}
            for conf_path, conf_content in list(dracut_conf_map.items()):
                linux.mkdir(os.path.dirname(conf_path))
                with open(conf_path, 'w') as f:
                    f.write(conf_content)

        rsp = UpdateHostOSRsp()
        if shell.run("which yum") != 0:
            rsp.success = False
            rsp.error = "no yum command found, cannot update host os"
        elif shell.run("export YUM0={};yum --disablerepo=* --enablerepo=zstack-mn repoinfo".format(releasever)) != 0:
            rsp.success = False
            rsp.error = "no zstack-mn repo found, cannot update host os"
        elif shell.run("export YUM0={};yum --disablerepo=* --enablerepo=qemu-kvm-ev-mn repoinfo".format(releasever)) != 0:
            rsp.success = False
            rsp.error = "no qemu-kvm-ev-mn repo found, cannot update host os"
        else:
            shell_cmd = shell.ShellCmd(yum_cmd, None, False)
            shell_cmd(False)
            if shell_cmd.return_code == 0:
                logger.debug("successfully run: %s" % yum_cmd)
            else:
                rsp.success = False
                rsp.error = "failed to update host os using zstack-mn,qemu-kvm-ev-mn repo, stdout: %s, stderr: %s" % (
                    shell_cmd.stdout, shell_cmd.stderr)

        rsp.libvirtVersion = linux.get_libvirt_package_version()

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def init_host_moc(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        if cmd.mode not in ["iohub", "mocbr"]:
            rsp.success = False
            rsp.error = "unexpected mode: " + cmd.mode
        else:
            bash_r(
                "/usr/local/bin/iohub_mocbr.sh %s start >> /var/log/iohubmocbr.log 2>&1" % cmd.mode)
            if cmd.mode == 'mocbr':
                iproute.set_link_attribute_no_error(
                    cmd.masterVethName, master=cmd.bridgeName)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    @lock.file_lock('/run/zstack-yum.lock', locker=lock.Flock())
    def update_dependency(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UpdateDependencyRsp()
        if self.IS_YUM:
            success, error = repair_rpmdb_if_damaged_on_host()
            if not success:
                rsp.success = False
                rsp.error = error
                return jsonobject.dumps(rsp)

            releasever = kvmagent.get_host_yum_release()
            shell.run("yum remove -y qemu-kvm-tools-ev")
            yum_cmd = "export YUM0={};yum --enablerepo=* clean all && yum --disablerepo=* --enablerepo={} install `cat /var/lib/zstack/dependencies` -y"\
                .format(releasever, cmd.zstackRepo)
            if shell.run(
                    "export YUM0={};yum --disablerepo=* --enablerepo=zstack-mn repoinfo".format(releasever)) != 0:
                rsp.success = False
                rsp.error = "no zstack-mn repo found, cannot update kvmagent dependencies"
            elif shell.run("export YUM0={};yum --disablerepo=* --enablerepo=qemu-kvm-ev-mn repoinfo".format(releasever)) != 0:
                rsp.success = False
                rsp.error = "no qemu-kvm-ev-mn repo found, cannot update kvmagent dependencies"
            elif shell.run(yum_cmd) != 0:
                rsp.success = False
                rsp.error = "failed to update kvmagent dependencies using %s repo" % cmd.zstackRepo
            else:
                logger.debug("successfully run: {}".format(yum_cmd))

            if cmd.enableExpRepo:
                exclude = "--exclude=" + cmd.excludePackages if cmd.excludePackages else ""
                updates = cmd.updatePackages if cmd.updatePackages else ""
                yum_cmd = "export YUM0={};yum --enablerepo=* clean all && yum --disablerepo=* --enablerepo={},zstack-experimental-mn {} update {} -y"
                yum_cmd = yum_cmd.format(
                    releasever, cmd.zstackRepo, exclude, updates)
                if shell.run(
                        "export YUM0={};yum --disablerepo=* --enablerepo=zstack-experimental-mn repoinfo".format(releasever)) != 0:
                    rsp.success = False
                    rsp.error = "no zstack-experimental-mn repo found, cannot update host dependency"
                elif shell.run(yum_cmd) != 0:
                    rsp.success = False
                    rsp.error = "failed to update host dependency using zstack-experimental-mn repo"
                else:
                    logger.debug("successfully run: %s" % yum_cmd)
        elif self.IS_APT:
            apt_cmd = "apt-get clean && apt-get -y --allow-unauthenticated install `cat /var/lib/zstack/dependencies`"
            if shell.run(apt_cmd) != 0:
                rsp.success = False
                rsp.error = "failed to update kvmagent dependencies by {}.".format(
                    apt_cmd)
            else:
                logger.debug("successfully run: {}".format(apt_cmd))
        else:
            rsp.success = False
            rsp.error = "no yum or apt found, cannot update kvmagent dependencies"
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def get_xfs_frag_data(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetXfsFragDataRsp()
        o = bash_o("df -hlT | awk 'NR==2 {print $1,$2}'")
        o = str(o).strip().split(" ")
        if len(o) != 2:
            rsp.success = False
            rsp.error = "failed to get root path and file system type"
            return jsonobject.dumps(rsp)

        root_path = o[0]
        fs_type = o[1]
        rsp.fsType = fs_type
        if fs_type != "xfs":
            return jsonobject.dumps(rsp)
        if root_path is None:
            rsp.error = "failed to find root device"
            rsp.success = False
            return jsonobject.dumps(rsp)

        frag_percent = bash_o(
            "xfs_db -c frag -r %s | awk '/fragmentation factor/{print $7}'" % root_path, True)
        if not str(frag_percent).strip().endswith("%"):
            rsp.error = "error format %s" % frag_percent
            rsp.success = False
            return jsonobject.dumps(rsp)
        else:
            rsp.hostFrag = frag_percent.strip()[:-1]

        volume_path_dict = cmd.volumePathMap.__dict__
        if volume_path_dict is not None:
            for key, value in list(volume_path_dict.items()):
                r, o = bash_ro("xfs_bmap %s | wc -l" % value, True)
                if r == 0:
                    o = o.strip()
                    rsp.volumeFragMap[key] = int(o) - 1

        return jsonobject.dumps(rsp)

    def shutdown_host(self, req):
        self.do_shutdown_host()
        return jsonobject.dumps(kvmagent.AgentResponse())

    def reboot_host(self, req):
        self.do_reboot_host()
        return jsonobject.dumps(kvmagent.AgentResponse())

    @thread.AsyncThread
    def do_shutdown_host(self):
        logger.debug("It is going to shutdown host after 1 sec")
        time.sleep(1)
        shell.call("sudo init 0")

    @thread.AsyncThread
    def do_reboot_host(self):
        logger.debug("It is going to reboot host after 1 sec")
        time.sleep(1)
        shell.call("sudo shutdown -r now")

    @kvmagent.replyerror
    @in_bash
    def disable_hugepage(self, req):
        rsp = DisableHugePageRsp()
        return_code, stdout = self._close_hugepage()
        if return_code != 0 or "Error" in stdout:
            rsp.success = False
            rsp.error = stdout
        return jsonobject.dumps(rsp)

    def _close_hugepage(self):
        disable_hugepage_script = '''#!/bin/sh
grubs="%s"
grubRockyEnvs="%s"

# config nr_hugepages
sysctl -w vm.nr_hugepages=0

# config default grub
sed -i '/GRUB_CMDLINE_LINUX=/s/[[:blank:]]*default_[[:graph:]]*//g' /etc/default/grub
sed -i '/GRUB_CMDLINE_LINUX=/s/[[:blank:]]*hugepagesz[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' /etc/default/grub
sed -i '/GRUB_CMDLINE_LINUX=/s/[[:blank:]]*hugepages[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' /etc/default/grub
sed -i '/GRUB_CMDLINE_LINUX=/s/[[:blank:]]*transparent_hugepage[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' /etc/default/grub
line=`cat /etc/default/grub | grep GRUB_CMDLINE_LINUX`
result=$(echo $line | grep '\"$')
if [ ! -n "$result" ]; then
    sed -i '/GRUB_CMDLINE_LINUX/s/$/\"/g' /etc/default/grub
fi

#clear boot grub config
for var in $grubs
do
   if [ -f $var ]; then
       sed -i '/^[[:space:]]*linux/s/[[:blank:]]*default_[[:graph:]]*//g' $var
       sed -i '/^[[:space:]]*linux/s/[[:blank:]]*hugepagesz[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' $var
       sed -i '/^[[:space:]]*linux/s/[[:blank:]]*hugepages[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' $var
       sed -i '/^[[:space:]]*linux/s/[[:blank:]]*transparent_hugepage[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' $var
   fi
done

#clear boot config related to huge pages in rocky grubenv
for env in $grubRockyEnvs
do
  if [ -f $env ]; then
       sed -i '/^[[:space:]]*kernelopts/s/[[:blank:]]*default_[[:graph:]]*//g' $env
       sed -i '/^[[:space:]]*kernelopts/s/[[:blank:]]*hugepagesz[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' $env
       sed -i '/^[[:space:]]*kernelopts/s/[[:blank:]]*hugepages[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' $env
       sed -i '/^[[:space:]]*kernelopts/s/[[:blank:]]*transparent_hugepage[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' $env
  fi
done
''' % (' '.join(GRUB_FILES), ' '.join(get_grub_rocky_envs()))
        disable_hugepage_script_path = linux.create_temp_file()
        with open(disable_hugepage_script_path, 'w') as f:
            f.write(disable_hugepage_script)
        logger.info('close_hugepage_script_path is: %s' %
                    disable_hugepage_script_path)
        cmd = shell.ShellCmd('bash %s' % disable_hugepage_script_path)
        cmd(False)

        os.remove(disable_hugepage_script_path)
        return cmd.return_code, cmd.stdout

    @kvmagent.replyerror
    @in_bash
    def enable_hugepage(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = EnableHugePageRsp()

        pageSize = cmd.pageSize
        reserveSize = cmd.reserveSize
        # Calculate memory parameters
        reserveSize_mib = reserveSize // 1024 // 1024
        pageSize = cmd.pageSize

        # Get system memory size
        mem_output = shell.ShellCmd(
            'free -m | awk \'/:/ {print $2;exit}\'')(False)
        memSize = int(mem_output.strip())

        # Calculate page count
        pageNum = (memSize - reserveSize_mib) // pageSize
        if memSize < reserveSize_mib:
            logger.error(
                "Error: reserve size is bigger than system memory size")
            rsp.success = False
            rsp.error = "Error: reserve size is bigger than system memory size"
            return jsonobject.dumps(rsp)

        # Clear cache
        with open('/proc/sys/vm/drop_caches', 'w') as f:
            f.write('3')

        # Enable transparent hugepages
        with open('/sys/kernel/mm/transparent_hugepage/enabled', 'w') as f:
            f.write('always')

        # Configure grub files
        hugepage_params = ' transparent_hugepage=always default_hugepagesz=%sM hugepagesz=%sM hugepages=%s' % (
            pageSize, pageSize, pageNum)

        # Define grub configuration file processing function
        def configure_grub_file(
                file_path, pattern, replacement_pattern, description=""):
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    content = f.read()

                # logger.info("origin %s %s: %s" % (description, file_path, content))

                # First clean up all existing hugepage parameters
                content = re.sub(r'\s*transparent_hugepage=\w+', '', content)
                content = re.sub(r'\s*default_hugepagesz=\d+M', '', content)
                content = re.sub(r'\s*hugepagesz=\d+M', '', content)
                content = re.sub(r'\s*hugepages=\d+', '', content)

                # Then add new parameters
                new_content = re.sub(
                    pattern, replacement_pattern, content, flags=re.MULTILINE)

                with open(file_path, 'w') as f:
                    # logger.info("new %s %s: %s" % (description, file_path, new_content))
                    f.write(new_content)

        # Configure /etc/default/grub - GRUB_CMDLINE_LINUX
        configure_grub_file(
            '/etc/default/grub',
            r'(GRUB_CMDLINE_LINUX="[^"]*)"\s*\n',
            r'\1%s"\n' % hugepage_params,
            "grub"
        )

        # Configure boot grub files - linux line
        # TODO h84r: /etc/grub2-efi.cfg does not match
        for grub_file in GRUB_FILES:
            configure_grub_file(
                grub_file,
                r'(^\s*linux.*)$',
                r'\1%s' % hugepage_params,
                "boot grub"
            )

        # Configure rocky grubenv files - kernelopts line
        for grub_env in get_grub_rocky_envs():
            if os.path.exists(grub_env):
                r, o, e = bash_roe("grub2-editenv %s list" % grub_env)
                if r == 0:
                    m = re.search(r'^kernelopts=(.*)$', o, flags=re.MULTILINE)
                    current = m.group(1) if m else ''
                    # Clean existing hugepage parameters
                    current = re.sub(
                        r'\s*transparent_hugepage=\w+', '', current)
                    current = re.sub(
                        r'\s*default_hugepagesz=\d+M', '', current)
                    current = re.sub(r'\s*hugepagesz=\d+M', '', current)
                    current = re.sub(r'\s*hugepages=\d+', '', current)
                    # Set new kernelopts
                    new_opts = (current + hugepage_params).strip()
                    bash_roe("grub2-editenv %s set kernelopts='%s'" %
                             (grub_env, new_opts))

        # Set hugepage count
        r, _, e = bash_roe('sysctl -w vm.nr_hugepages=%s' % pageNum)
        if r != 0:
            rsp.success = False
            rsp.error = e
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def clean_local_cache(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        isc = ImageStoreClient()
        isc.clean_imagestore_cache(cmd.mountPath)
        return jsonobject.dumps(kvmagent.AgentResponse())

    @kvmagent.replyerror
    def change_password(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        tmpfile = linux.write_to_temp_file("root:" + str(cmd.password))
        shell.call("/usr/sbin/chpasswd < %s" % tmpfile)
        os.remove(tmpfile)
        return jsonobject.dumps(rsp)

    def identify_host(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        sc = shell.ShellCmd("ipmitool chassis identify %s" % cmd.interval)
        sc(True)
        return jsonobject.dumps(rsp)

    def locate_host_network_interface(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        # Intel 82599ES not support identify.
        sc = shell.ShellCmd("ethtool --identify %s %s" %
                            (cmd.networkInterface, cmd.interval))
        sc(False)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_host_physical_memory_facts(self, req):
        rsp = GetHostPhysicalMemoryFactsResponse()
        r, o, e = bash_roe("dmidecode -q -t memory")
        if r != 0:
            rsp.success = False
            rsp.error = e
            return jsonobject.dumps(rsp)

        results = []
        memory_arr = o.split("Memory Device")
        for infos in memory_arr[1:]:
            size = locator = speed = manufacturer = type = serial_number = rank = clock_speed = None
            for line in infos.splitlines():
                if line.strip() == "" or ":" not in line:
                    continue
                k = line.split(":")[0].lower().strip()
                v = ":".join(line.split(":")[1:]).strip()

                if "size" == k:
                    if "mb" in v.lower():
                        size = str(int(v.split(" ")[0]) // 1024) + " GB"
                    elif "no module installed" in v.lower():
                        size = None
                    else:
                        size = v
                elif "locator" == k:
                    locator = v
                elif "speed" == k:
                    speed = v
                elif "manufacturer" == k:
                    manufacturer = v
                elif "type" == k:
                    type = v
                elif "serial number" == k:
                    serial_number = v
                elif "rank" == k:
                    rank = v
                elif "configured clock speed" == k:
                    clock_speed = v
                elif "configured voltage" == k:
                    if serial_number.lower() != "no dimm" and serial_number.lower(
                    ) != "unknown" and serial_number is not None:
                        m = HostPhysicalMemoryStruct()
                        m.size = size
                        m.speed = speed
                        m.clockSpeed = clock_speed
                        m.locator = locator
                        m.manufacturer = manufacturer
                        m.type = type
                        m.serialNumber = serial_number
                        m.rank = rank
                        m.voltage = v
                        results.append(m)
        rsp.physicalMemoryFacts = results
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def update_ovs_cpu_pinning(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        ovsCpuPinning = None
        if cmd.hasattr("ovsCpuPinning"):
            ovsCpuPinning = cmd.ovsCpuPinning

        ovs.getOvsCtl(with_dpdk=True).configPmdCpuMaskForOvs(ovsCpuPinning)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_host_network_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetHostNetworkBongdingResponse()

        rsp.bondings = self.get_host_networking_bonds(cmd.managementServerIp)
        rsp.nics = self.get_host_networking_interfaces(cmd.managementServerIp)

        return jsonobject.dumps(rsp)

    def _has_vlan_or_bridge(self, ifname):
        if linux.is_bridge_slave(ifname):
            return True

        vlan_dev_name = '%s.' % ifname
        output = subprocess.check_output(
            ['ip', 'link', 'show', 'type', 'vlan'], universal_newlines=True)
        for line in output.split('\n'):
            if vlan_dev_name in line:
                return True

        return False

    @kvmagent.replyerror
    @in_bash
    def set_ip_on_host_network_interface(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetIpOnHostNetworkInterfaceRsp()

        try:
            if self._has_vlan_or_bridge(cmd.interfaceName):
                raise Exception(cmd.interfaceName +
                                ' has a sub-interface or a bridge port')
        except Exception as e:
            rsp.error = 'unable to update ip[%s], because %s' % (
                cmd.interfaceName, str(e))
            rsp.success = False
            return jsonobject.dumps(rsp)

        is_ipv6_address = cmd.ipAddress is not None and ':' in cmd.ipAddress
        old_is_ipv6_address = cmd.oldIpAddress is not None and ':' in cmd.oldIpAddress
        if cmd.ipAddress is not None:
            try:
                if is_ipv6_address:
                    prefix_length = cmd.prefixLength if cmd.prefixLength is not None else cmd.netmask
                    shell.call('ip -6 addr flush dev %s scope global' % shell_quote(cmd.interfaceName))
                    shell.call('ip -6 addr add %s/%s dev %s' %
                               (shell_quote(cmd.ipAddress), prefix_length, shell_quote(cmd.interfaceName)))
                    shell.call('ip link set dev %s up' % shell_quote(cmd.interfaceName))
                else:
                    # zs-network-setting -i eth0 192.168.1.10 255.255.255.0
                    # 192.168.1.1
                    if cmd.gateway is not None:
                        shell.call('/usr/local/bin/zs-network-setting -i %s %s %s %s' %
                                   (cmd.interfaceName, cmd.ipAddress, cmd.netmask, cmd.gateway))
                    else:
                        # zs-network-setting -d eth0
                        shell.call('/usr/local/bin/zs-network-setting -d %s' %
                                   cmd.interfaceName)
                        bash_o('/usr/local/bin/zs-network-setting -i %s %s %s' %
                               (cmd.interfaceName, cmd.ipAddress, cmd.netmask))
            except Exception as e:
                rsp.error = 'unable to add ip on %s, because %s' % (
                    cmd.interfaceName, str(e))
                rsp.success = False

            # After configuring the ip, check the connectivity
            if not is_ipv6_address and cmd.gateway is not None and shell.run(
                    'ping -c 5 -W 1 %s > /dev/null 2>&1' % cmd.gateway) != 0:
                shell.call('/usr/local/bin/zs-network-setting -d %s' %
                           cmd.interfaceName)

                # If it is not connected, it will fall back to the old ip
                # address
                if cmd.oldGateway is None:
                    shell.call('/usr/local/bin/zs-network-setting -i %s %s %s' % (cmd.interfaceName, cmd.ipAddress,
                               cmd.netmask))
                else:
                    shell.call('/usr/local/bin/zs-network-setting -i %s %s %s %s' % (cmd.interfaceName,
                               cmd.ipAddress, cmd.netmask, cmd.gateway))

        # If the parameter is empty, the ip will be deleted by default
        else:
            try:
                # mv ip on interface
                shell.call('/usr/local/bin/zs-network-setting -d %s' %
                           cmd.interfaceName)
                if old_is_ipv6_address:
                    shell.call('ip -6 addr flush dev %s scope global' % shell_quote(cmd.interfaceName))
            except Exception as e:
                rsp.error = 'unable to delete ip on %s, because %s' % (
                    cmd.interfaceName, str(e))
                rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def check_interface_vlan(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckInterfaceVlanRsp()
        rsp.success = False

        vlan_dev_name = '%s.%s' % (cmd.interfaceName, cmd.vlanId)
        output = shell.call('ip link show type vlan %s' % vlan_dev_name)
        if vlan_dev_name in output:
            rsp.success = True

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def get_interface_vlan(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetInterfaceVlanRsp()
        rsp.success = False

        vlan_ids = []
        for interface_name in cmd.interfaceNames:
            output = shell.call(
                "ip link show type vlan | grep '%s\\.' | awk -F'[.@]' '{print $2}'" % interface_name)
            interface_vlan_ids = output.strip().split('\n')

            if not interface_vlan_ids:
                interface_vlan_ids = ['0']
            else:
                interface_vlan_ids.append('0')

            if not vlan_ids:
                vlan_ids = interface_vlan_ids
            vlan_ids = [
                vlan for vlan in vlan_ids if vlan and vlan in interface_vlan_ids]

        rsp.success = True
        rsp.vlanIds = vlan_ids if vlan_ids != [] else ['0']

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_interface_name(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetInterfaceNameRsp()
        rsp.success = False
        rsp.interfaceNames = []

        interface_names = []
        interfaces = iproute.query_links()
        for interface in interfaces:
            interface_name = interface.ifname
            addresses = iproute.query_addresses_by_ifname(
                ifname=interface_name)
            ip_addresses = [addr.address for addr in addresses]
            for addr in ip_addresses:
                if addr in cmd.ipAddresses:
                    if interface_name.startswith('br_'):
                        output = shell.call(
                            "brctl show %s | awk '{print $NF}' | grep -vw interfaces" % interface_name).strip().split('\n')
                        non_virtual_eths = [name for name in output if
                                            not (name.startswith('outer') or name.startswith('ud') or name.startswith('vnic'))]
                        interface_name = non_virtual_eths[0]
                    interface_names.append(interface_name)

        rsp.success = True
        rsp.interfaceNames = interface_names
        return jsonobject.dumps(rsp)

    @staticmethod
    def get_host_networking_interfaces(managementServerIp):
        nics = []
        pcis = set()

        def get_nic_info(interfaceName, index,
                         driverType=None, pciAddress=None):
            nics[index] = HostNetworkInterfaceInventory(
                interfaceName, None, managementServerIp, driverType, pciAddress)

        threads = []
        nic_names = ip.get_host_physicl_nics()
        if len(nic_names) == 0:
            return nics

        vfioNics = ovn.getAllVfioPciNic()
        nics = [None] * (len(nic_names) + len(vfioNics))
        for index, nic in enumerate(nic_names, start=0):
            interfaceName = nic.strip()
            pciDeviceAddress = os.readlink(
                "/sys/class/net/%s/device" % interfaceName).strip().split('/')[-1]
            # exclude vf representor
            if pciDeviceAddress not in pcis:
                threads.append(thread.ThreadFacade.run_in_thread(
                    get_nic_info, [interfaceName, index]))
                pcis.add(pciDeviceAddress)
        for t in threads:
            t.join()

        index = len(nic_names)
        for nic in vfioNics:
            get_nic_info(nic.name, index, driverType=nic.driver,
                         pciAddress=nic.pciAddress)
            index = index + 1
        return nics

    @staticmethod
    def get_host_networking_bonds(managementServerIp):
        bonds = []
        bond_names = linux.read_file("/sys/class/net/bonding_masters")
        if bond_names:
            bond_names = bond_names.strip().split(" ")
            if len(bond_names) == 0:
                return bonds
            for bond in bond_names:
                bonds.append(HostNetworkBondingInventory(
                    bond, "kernalBond", managementServerIp))

        # get dpdk bond info
        dpdkBondFile = "/usr/local/etc/zstack-ovs/dpdk-bond.yaml"
        if not os.path.exists(dpdkBondFile):
            return bonds

        with open(dpdkBondFile, "r") as f:
            bondData = yaml.safe_load(f)

        if bondData is None:
            return bonds

        for b in bondData:
            bonds.append(HostNetworkBondingInventory(b, "dpdkBond"))

        return bonds

    def _get_sriov_info(self, to, gpu_info_map=None):
        addr = to.pciDeviceAddress
        dev = os.path.join("/sys/bus/pci/devices/", addr)
        totalvfs = os.path.join(dev, "sriov_totalvfs")
        numvfs = os.path.join(dev, "sriov_numvfs")
        physfn = os.path.join(dev, "physfn")
        gpuvf = os.path.join(dev, "gpuvf")

        if os.path.exists(totalvfs):
            # for pf, to.maxPartNum means the number of possible vfs
            with open(totalvfs, 'r') as f:
                to.maxPartNum = f.read().strip()

            with open(numvfs, 'r') as f:
                if f.read().strip() != '0':
                    set_pci_virt_metadata(
                        to, "SRIOV_VIRTUALIZED", "VIRTUALIZED", "SRIOV", ["SRIOV"])
                else:
                    set_pci_virt_metadata(
                        to, "SRIOV_VIRTUALIZABLE", "VIRTUALIZABLE", None, ["SRIOV"])
        elif os.path.exists(physfn):
            # for vf, to.maxPartNum means the number of current vfs
            numvfs = os.path.join(physfn, "sriov_numvfs")
            if os.path.exists(numvfs):
                with open(numvfs, 'r') as f:
                    to.maxPartNum = f.read().strip()
            # for NVIDIA A-Series, after driver successfully installed, virtfn files will be created
            # set deviceId and vendorId null
            # Optimized: Use pre-collected gpu_info_map if available, otherwise
            # fallback to individual query
            virtfn = os.path.join(dev, os.readlink(physfn), 'virtfn0')
            is_nvidia_gpu = False
            if hasattr(to, 'vendor') and to.vendor == VendorEnum.NVIDIA:
                # Known NVIDIA vendor, use pre-collected gpu_info_map if
                # available
                if gpu_info_map is not None:
                    normalized_pci = pci.normalize_pci_address(
                        to.pciDeviceAddress)
                    is_nvidia_gpu = normalized_pci in gpu_info_map if normalized_pci else False
                else:
                    # Fallback to individual query (backward compatibility)
                    gpu_info = gpu.get_info(
                        pci_device=to, vendor_name=VendorEnum.NVIDIA)
                    is_nvidia_gpu = gpu_info is not None
            else:
                # Unknown vendor: Use pre-collected gpu_info_map if available
                if gpu_info_map is not None:
                    normalized_pci = pci.normalize_pci_address(
                        to.pciDeviceAddress)
                    is_nvidia_gpu = normalized_pci in gpu_info_map if normalized_pci else False
                else:
                    # Fallback to batch query (backward compatibility)
                    gpu_info_map_local = gpu.get_all_gpu_infos_by_pci()
                    normalized_pci = pci.normalize_pci_address(
                        to.pciDeviceAddress)
                    is_nvidia_gpu = normalized_pci in gpu_info_map_local if normalized_pci else False

            if is_nvidia_gpu and self.NVIDIA_SMI_INSTALLED and os.path.exists(
                    virtfn):
                to.deviceId = ""
                to.vendorId = ""

            set_pci_virt_metadata(
                to, "SRIOV_VIRTUAL", "VIRTUAL", "SRIOV", [])

            to.parentAddress = os.readlink(physfn).split('/')[-1]
            if os.path.exists(gpuvf):
                with open(gpuvf, 'r') as f:
                    for line in f.readlines():
                        line = line.strip()
                        if 'VF FB Size' in line:
                            to.ramSize = line.split(':')[-1].strip()
                            to.description = "%s [RAM Size: %s]" % (
                                to.description, to.ramSize)
                            break
        else:
            return False
        return True

    def _get_nvidia_vfio_mdev_info(self, to):
        addr = to.pciDeviceAddress
        check_mdev_folder = '/sys/bus/pci/devices/%s/mdev_supported_types' % addr
        legacy_mdev_dir_exists = os.path.isdir(check_mdev_folder)
        check_virtfn_folder = '/sys/bus/pci/devices/%s/virtfn0/mdev_supported_types' % addr
        virt_function_dir_exits = os.path.isdir(check_virtfn_folder)

        # check if nvidia vgpu is supported by current device
        r, o, e = bash_roe("nvidia-smi vgpu -i %s -v -c" % addr)
        if r != 0:
            # SR-IOV backed vGPU cards (e.g. L20, RTX8000) report creatable types
            # only after VFs are created. Fall back to supported-types query which
            # works on the PF regardless of VF state. ZSTAC-67411 / ZSTAC-81403
            r2, _, _ = bash_roe("nvidia-smi vgpu -i %s -s" % addr)
            if r2 != 0:
                return False
            rs, support, _ = bash_roe("nvidia-smi vgpu -i %s -s | grep -v %s" %
                                      (addr, addr))
            rc, creatable, _ = bash_roe(
                "nvidia-smi vgpu -i %s -c | grep -v %s" % (addr, addr))
            if rs == 0 and support.strip() and (rc != 0 or support != creatable):
                set_pci_virt_metadata(
                    to, "VFIO_MDEV_VIRTUALIZED", "VIRTUALIZED",
                    "VFIO_MDEV", ["VFIO_MDEV"])
                return True
            if legacy_mdev_dir_exists:
                self._legacy_mdev(to)
            elif virt_function_dir_exits:
                self._virt_function(to)
            else:
                set_pci_virt_metadata(
                    to, "VFIO_MDEV_VIRTUALIZABLE", "VIRTUALIZABLE",
                    None, ["VFIO_MDEV"])
            return True

        for line in o.splitlines()[1:]:
            parts = line.split(':')
            if len(parts) < 2:
                continue
            title = parts[0].strip()
            content = ' '.join(parts[1:]).strip()
            if title == "vGPU Type ID":
                spec = {'TypeId': content}
                to.mdevSpecifications.append(spec)
            else:
                to.mdevSpecifications[-1][title] = content

        if legacy_mdev_dir_exists:
            rc, _, _ = bash_roe("nvidia-smi vgpu -i %s -c" % addr)
            if rc != 0:
                set_pci_virt_metadata(
                    to, "VFIO_MDEV_VIRTUALIZABLE", "VIRTUALIZABLE",
                    None, ["VFIO_MDEV"])
            else:
                self._legacy_mdev(to)
        elif virt_function_dir_exits:
            self._virt_function(to)
        else:
            set_pci_virt_metadata(
                to, "VFIO_MDEV_VIRTUALIZABLE", "VIRTUALIZABLE",
                None, ["VFIO_MDEV"])

        return True

    def _get_huawei_vfio_mdev_info(self, to):
        addr = to.pciDeviceAddress
        check_mdev_folder = '/sys/bus/pci/devices/%s/mdev_supported_types' % addr
        if not os.path.isdir(check_mdev_folder):
            return False

        if shell.run("which npu-smi") != 0:
            logger.debug("no npu-smi")
            return False

        r, npu_ids_out = bash_ro("npu-smi info -l")
        if r != 0:
            logger.error("npu query gpu is error, %s " % npu_ids_out)
            return False

        npu_ids = []
        for line in npu_ids_out.splitlines():
            line = line.strip()
            if not line:
                continue
            if "NPU ID" in line:
                npu_ids.append(line.split(":")[1].strip())

        if len(npu_ids) == 0:
            return False

        add_found = False
        for npu_id in npu_ids:
            r, o, e = bash_roe("npu-smi info -t board -i %s" % npu_id)
            if r != 0:
                logger.error("npu query gpu board is error, %s " % e)
                continue

            if to.pciDeviceAddress.lower() not in o.lower():
                continue

            add_found = True

            r, o, e = bash_roe("npu-smi info -t template-info -i %s" % npu_id)

            if r != 0:
                logger.error("npu query gpu template-info is error, %s " % e)
                continue

            for line in o.splitlines():
                match = re.match(
                    r'\|(\w+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+\|', line)
                if match and len(match.group(1)) > 0:
                    template = {
                        'Name': match.group(1),
                        'TypeId': match.group(1),
                        'AICORE': int(match.group(2)),
                        'Memory': int(match.group(3)),
                        'AICPU': int(match.group(4)),
                        'VPC': int(match.group(5)),
                        'VENC': int(match.group(6)),
                        'JPEGD': int(match.group(7))
                    }
                    to.mdevSpecifications.append(template)

        if not add_found:
            logger.error(
                "can't find gpu %s mdev spec in npu-smi output" % to.pciDeviceAddress)
            return False

        r, virtStatusOut = bash_ro("ls -l  /sys/bus/mdev/devices/")
        if r != 0:
            return False

        if addr.lower() in virtStatusOut.lower():
            set_pci_virt_metadata(
                to, "VFIO_MDEV_VIRTUALIZED", "VIRTUALIZED",
                "VFIO_MDEV", ["VFIO_MDEV"])
        else:
            set_pci_virt_metadata(
                to, "VFIO_MDEV_VIRTUALIZABLE", "VIRTUALIZABLE",
                None, ["VFIO_MDEV"])

        return True

    def _get_vfio_mdev_info(self, to):
        vendor_name = to.vendor
        if vendor_name == VendorEnum.NVIDIA:
            return self._get_nvidia_vfio_mdev_info(to)
        elif vendor_name == VendorEnum.HUAWEI:
            return self._get_huawei_vfio_mdev_info(to)
        else:
            return False

    def _legacy_mdev(self, to):
        # if supported specs != creatable specs, means it's aleady virtualized
        _, support, _ = bash_roe("nvidia-smi vgpu -i %s -s | grep -v %s" %
                                 (to.pciDeviceAddress, to.pciDeviceAddress))
        _, creatable, _ = bash_roe(
            "nvidia-smi vgpu -i %s -c | grep -v %s" % (to.pciDeviceAddress, to.pciDeviceAddress))
        if support != creatable:
            set_pci_virt_metadata(
                to, "VFIO_MDEV_VIRTUALIZED", "VIRTUALIZED",
                "VFIO_MDEV", ["VFIO_MDEV"])
        else:
            set_pci_virt_metadata(
                to, "VFIO_MDEV_VIRTUALIZABLE", "VIRTUALIZABLE",
                None, ["VFIO_MDEV"])

    def _virt_function(self, to):
        addr = to.pciDeviceAddress
        r, o, e = bash_roe("ls /sys/bus/pci/devices/%s/ | grep virtfn" % addr)
        if r != 0:
            return False

        mdev_r, mdev_o, _ = bash_roe("ls /sys/bus/mdev/devices/")

        virtualizable = False
        mdev_devices_exists = False
        for virtfn in o.splitlines():
            virtfn_dir = "/sys/bus/pci/devices/%s/%s/" % (addr, virtfn)
            for mdev in mdev_o.splitlines():
                if os.path.exists(os.path.join(virtfn_dir, mdev)):
                    mdev_devices_exists = True
                    break

            for virf in os.listdir(os.path.join(
                    virtfn_dir, 'mdev_supported_types')):
                if "nvidia-" in virf:
                    with open(os.path.join(virtfn_dir, 'mdev_supported_types', virf, "available_instances"), 'r') as af:
                        max_instances = af.read().strip()

                    if max_instances == '1':
                        virtualizable = True
                        break
            if virtualizable or mdev_devices_exists:
                break
        if mdev_devices_exists is True:
            set_pci_virt_metadata(
                to, "VFIO_MDEV_VIRTUALIZED", "VIRTUALIZED",
                "VFIO_MDEV", ["VFIO_MDEV"])
        elif virtualizable is True:
            set_pci_virt_metadata(
                to, "VFIO_MDEV_VIRTUALIZABLE", "VIRTUALIZABLE",
                None, ["VFIO_MDEV"])

    def _simplify_pci_device_name(self, name, vendor_id):
        """
        Simplify PCI device vendor name using lightweight PCI library function.

        This function uses the lightweight simplify_vendor_name from pci module,
        which does not depend on the GPU vendor system. This reduces dependencies
        and simplifies the logic.

        Returns VendorEnum values for known vendors, or cleaned original name.
        """
        # Use lightweight vendor name simplification from pci module
        simplified = pci.simplify_vendor_name(name, vendor_id)

        # Map simplified names to VendorEnum values for backward compatibility
        # Note: simplify_vendor_name already returns values matching VendorEnum
        # constants
        vendor_enum_map = {
            'Intel': VendorEnum.INTEL,
            'AMD': VendorEnum.AMD,
            'NVIDIA': VendorEnum.NVIDIA,
            'Haiguang': VendorEnum.HAIGUANG,
            'Huawei': VendorEnum.HUAWEI,
            'TianShu': VendorEnum.TIANSHU,
            'Vastai': VendorEnum.VASTAI,
            'Enflame': VendorEnum.ENFLAME,
            'Alibaba': VendorEnum.ALIBABA,
            'Kunlunxin': VendorEnum.KUNLUNXIN,
        }

        # Return VendorEnum value if mapped, otherwise return simplified name
        return vendor_enum_map.get(simplified, simplified)

    def _convert_pci_info_to_to(
            self, slot, ids, names, pci_device_mapper, host_mappings, context=None):
        """
        Convert PCI device information to PciDeviceTO object.

        Args:
            slot: PCI device slot address
            ids: Dictionary of PCI IDs (Vendor, Device, etc.)
            names: Dictionary of PCI names (Vendor, Device, etc.)
            pci_device_mapper: PCI device type mapper
            host_mappings: Host PCI address mappings
            context: PciDeviceProcessingContext (optional); used so generic type
                is not overwritten for devices in gpu_info_map (GPU identified by gpu.py).

        Returns:
            PciDeviceTO object or None if conversion fails
        """
        if slot not in names:
            logger.error("PCI device slot %s not found in names" % slot)
            return None

        # names is slot -> {field: name}; use per-slot field dict
        slot_names = names[slot]

        vendor_name = ""
        device_name = ""
        subvendor_name = ""
        to = PciDeviceTO()

        # Set basic info
        to.pciDeviceAddress = slot
        group_path = os.path.join(
            '/sys/bus/pci/devices/', to.pciDeviceAddress, 'iommu_group')
        to.iommuGroup = os.path.realpath(group_path)

        # Set class info
        if 'Class' in slot_names:
            to.type = slot_names['Class']
            to.description = slot_names['Class'] + ": "

        # Set vendor info
        if 'Vendor' in slot_names:
            vendor_name = self._simplify_pci_device_name(
                slot_names['Vendor'], ids.get('Vendor', ''))
            to.vendor = vendor_name
            to.vendorId = ids.get('Vendor', '')
            to.description += vendor_name + " "

        # Set device info
        if 'Device' in slot_names:
            to.device = slot_names['Device']
            device_name = self._simplify_pci_device_name(
                slot_names['Device'], ids.get('Device', ''))
            to.deviceId = ids.get('Device', '')
            to.description += device_name

        # Set subvendor info
        if 'SVendor' in slot_names:
            subvendor_name = self._simplify_pci_device_name(
                slot_names['SVendor'], ids.get('SVendor', ''))
            to.subvendorId = ids.get('SVendor', '')

        # Set subdevice info
        if 'SDevice' in slot_names:
            to.subdeviceId = ids.get('SDevice', '')

        # Set revision info
        if 'Rev' in slot_names:
            to.rev = ids.get('Rev', '')

        to.name = "%s_%s" % (
            subvendor_name if subvendor_name else vendor_name, device_name)
        to.dependentDevices = pci.collect_pci_devices_with_dependencies(
            to.pciDeviceAddress)
        to.vmPciDeviceAddress = host_mappings[to.pciDeviceAddress] if to.pciDeviceAddress in host_mappings else ""

        # Set generic PCI device type (base types only, not device-type-specific refinements)
        # Device-type-specific type refinement (e.g., GPU_Video_Controller) is
        # handled by GPU processor; context is used to skip overwriting type for
        # devices already identified as GPU in gpu_info_map (no hardcoded GPU class list).
        self._set_generic_pci_device_type(to, pci_device_mapper, context)

        return to

    def _parse_pci_device_info(self, rsp):
        """
        Parse PCI device information from lspci output and config file.

        Args:
            rsp: Response object to set error if parsing fails

        Returns:
            Tuple of (device_ids, device_names, pci_device_mapper) if successful,
            None if failed (error is set in rsp)
        """
        r_id, o_id, e_id = pci.get_pci_device_ids()
        r_name, o_name, e_name = pci.get_pci_device_names()

        if r_id != 0 or r_name != 0:
            rsp.success = False
            rsp.error = "%s, %s" % (
                e_id if r_id != 0 else e_name, o_id if r_id != 0 else o_name)
            return None

        pci_device_mapper = {}
        for line in linux.read_file_lines(PCI_CONFIG_PATH):
            parts = line.strip().split(':')
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                pci_device_mapper[key] = value

        # Build device info maps from both outputs
        device_ids = {}  # slot -> {field: id}
        device_names = {}  # slot -> {field: name}

        # Parse IDs from -Dmmnv output
        for part in o_id.split('\n\n'):
            slot = None
            ids = {}
            for line in part.split('\n'):
                if len(line.split(':')) < 2:
                    continue
                title = line.split(':')[0].strip()
                content = line.split(':')[1].strip()
                if title == 'Slot':
                    slot = line[5:].strip()
                elif title in ['Class', 'Vendor', 'Device', 'SVendor', 'SDevice', 'Rev']:
                    ids[title] = content.strip()

            if slot:
                device_ids[slot] = ids

        # Parse names from -Dmmv output
        for part in o_name.split('\n\n'):
            slot = None
            names = {}
            for line in part.split('\n'):
                if len(line.split(':')) < 2:
                    continue
                title = line.split(':')[0].strip()
                content = line.split(':')[1].strip()
                if title == 'Slot':
                    slot = line[5:].strip()
                elif title in ['Class', 'Vendor', 'Device', 'SVendor', 'SDevice', 'Rev']:
                    names[title] = content.strip()
            if slot:
                device_names[slot] = names

        return device_ids, device_names, pci_device_mapper

    def _apply_virt_status_fallback(self, pci_devices_info, context):
        """
        For PCI devices that don't have explicit virt metadata set by device
        ops (e.g., NICs), run host-level vfio_mdev and sriov detection and set
        the legacy status plus the new explicit fields.
        Restores behavior that previously ran for every PCI device before
        refactor (ZSTAC-81834).
        """
        for to in pci_devices_info:
            if not to.virtStatus or to.virtStatus == "":
                gpu_info_map = getattr(context, 'gpu_info_map', None) if context else None
                vfio_mdev_supported = self._get_vfio_mdev_info(to)
                vfio_mdev_status = to.virtStatus
                sriov_supported = self._get_sriov_info(to, gpu_info_map)
                if vfio_mdev_supported and sriov_supported:
                    virt_capabilities = list(getattr(to, 'virtCapabilities', []) or [])
                    if "VFIO_MDEV" not in virt_capabilities:
                        virt_capabilities.append("VFIO_MDEV")
                    if vfio_mdev_status == "VFIO_MDEV_VIRTUALIZED" and not getattr(to, 'virtMode', None):
                        set_pci_virt_metadata(
                            to, vfio_mdev_status, "VIRTUALIZED", "VFIO_MDEV", virt_capabilities)
                    else:
                        set_pci_virt_metadata(
                            to, to.virtStatus, getattr(to, 'virtState', None),
                            getattr(to, 'virtMode', None), virt_capabilities)
                elif not vfio_mdev_supported and not sriov_supported:
                    set_pci_virt_metadata(
                        to, "UNVIRTUALIZABLE", "UNVIRTUALIZABLE")
                # If only one of vfio_mdev or sriov is supported, keep the value
                # already set by _get_sriov_info or _get_vfio_mdev_info
            if not to.virtStatus or to.virtStatus == "":
                set_pci_virt_metadata(
                    to, "UNVIRTUALIZABLE", "UNVIRTUALIZABLE")

    def _collect_format_pci_device_info(self, rsp, opaque, pci_device_addresses=None):
        result = self._parse_pci_device_info(rsp)
        if result is None:
            return
        device_ids, device_names, pci_device_mapper = result

        if pci_device_addresses:
            device_ids = self._filter_pci_device_ids_by_addresses(device_ids, pci_device_addresses)

        pci_devices_dict = {}

        host_mappings = self.get_all_vm_pci_mappings()

        # Create processing context early so capabilities can be stored
        # directly
        context = pci.PciDeviceProcessingContext(
            pci_device_mapper=pci_device_mapper,
            opaque=opaque
        )

        # Run device ops prepare chain first so context has gpu_info_map etc.
        # This allows _set_generic_pci_device_type to skip overwriting type for
        # devices that gpu.py has identified as GPU (no hardcoded GPU class list).
        post_prepare_hooks = pci.pci_device_prepare_chain(context)

        # Create PciDeviceTO objects with generic PCI logic
        for slot in device_ids.keys():
            to = self._convert_pci_info_to_to(
                slot, device_ids[slot], device_names, pci_device_mapper, host_mappings, context)
            if not to:
                continue

            # Capabilities detection is now handled by device-type-specific processors
            # (e.g., GPU processor will call vendor methods to detect vfio_mdev and sriov)
            if to.vendorId != '' and to.deviceId != '':
                rsp.pciDevicesInfo.append(to)
                pci_devices_dict[to.pciDeviceAddress] = to
            else:
                logger.error(
                    "missing vendor or device id for PCI device: %s" %
                    to.pciDeviceAddress)

        # Device-type-specific enrichment phase: probe and init devices via registered ops
        # Architecture (Linux kernel style, similar to pci_driver model):
        # 1. Basic PCI info collection: Convert PCI info to PciDeviceTO objects
        # 2. Registry layer: Device ops are registered (GPU, Ethernet, etc.) via pci_register_device_ops()
        # 3. Preparation phase: Already run above so gpu_info_map is available before setting generic type
        # 4. Device-specific layer: pci_device_probe() finds matching ops by calling ops.probe() (like pci_driver.id_table)
        #    Then calls ops.init() to process device (like pci_driver.probe)
        #    Device ops handles: capability detection (via vendor methods), type refinement, virtStatus, addon info, post_process
        # Note: GPU vendors implement detect_vfio_mdev_capability and
        # detect_sriov_capability methods

        # Call post-prepare hooks after all PCI devices have been collected.
        for post_prepare_hook in post_prepare_hooks:
            try:
                post_prepare_hook(rsp.pciDevicesInfo, context)
            except Exception as e:
                logger.debug(
                    "PCI device ops post-prepare hook error: %s" %
                    str(e))
                continue

        # Probe and init each device via registered ops (like Linux kernel
        # pci_device_probe)
        for to in rsp.pciDevicesInfo:
            # Unified entry point: pci_device_probe() finds matching ops via ops.probe() and calls ops.init()
            # Device ops are registered via pci.pci_register_device_ops()
            pci.pci_device_probe(to, context)

        # Generic fallback: For devices that don't have virtStatus set by device
        # ops (e.g., NICs), run host-level vfio_mdev and sriov detection and set
        # virtStatus. Restores behavior that previously ran for every PCI device
        # before refactor (ZSTAC-81834).
        self._apply_virt_status_fallback(rsp.pciDevicesInfo, context)

        pci.update_cache_devices(pci_devices_dict)
        pci.calculate_max_addressable_memory(rsp.pciDevicesInfo)
        rsp.mdevDeviceInfos = self.get_all_vm_mdev_mappings()

    def _filter_pci_device_ids_by_addresses(self, device_ids, pci_device_addresses):
        normalized_addresses = set()
        for address in pci_device_addresses:
            normalized = pci.normalize_pci_address(address)
            normalized_addresses.add(address)
            if normalized:
                normalized_addresses.add(normalized)

        return {
            slot: info for slot, info in device_ids.items()
            if slot in normalized_addresses
            or (pci.normalize_pci_address(slot) or slot) in normalized_addresses
            or self._get_pci_parent_address(slot) in normalized_addresses
        }

    def _get_pci_parent_address(self, slot):
        physfn = os.path.join("/sys/bus/pci/devices/", slot, "physfn")
        if not os.path.exists(physfn):
            return None

        parent = os.readlink(physfn).split('/')[-1]
        return pci.normalize_pci_address(parent) or parent

    def list_vm_uuids(self):
        r, o, e = bash_roe(
            "virsh list --uuid --state-running --state-paused --state-other")
        if r != 0:
            logger.error(
                "failed to run 'virsh list --uuid --state-running --state-paused --state-other': %s" % e)
            return []
        uuids = [line.strip().replace('-', '')
                 for line in o.strip().splitlines() if line.strip()]
        return uuids

    def _collect_vm_mappings_parallel(self, mapping_func):
        """Query VM device mappings in parallel using a bounded thread pool.

        Dispatches *mapping_func(domain)* for every running VM.  The heavy
        work—``virsh qemu-monitor-command`` subprocesses spawned inside
        ``_query_pci_info_by_qmp``—runs outside the GIL, giving true
        parallelism.  The libvirt API itself (``conn.lookupByName``,
        ``domain.XMLDesc``) is thread-safe since libvirt 0.6.0.

        Args:
            mapping_func: callable(domain) -> dict or None,
                          e.g. ``pci.get_pci_passthrough_mapping``
        Returns:
            List of non-empty mapping dicts, one per VM that has passthrough
            devices.
        """
        libvirt_singleton = LibvirtSingleton()
        conn = libvirt_singleton.conn
        uuids = self.list_vm_uuids()
        if not uuids:
            return []

        task_uuid = log.get_task_uuid()

        def query_vm(vm_uuid):
            if task_uuid:
                log.set_task_uuid(task_uuid)
            try:
                domain = conn.lookupByName(vm_uuid)
                if domain is None:
                    return None
                return mapping_func(domain)
            except Exception as e:
                logger.debug("Failed to get device mapping for VM {}: {}".format(
                    vm_uuid, str(e)))
                return None

        max_workers = min(len(uuids), _PCI_QUERY_MAX_WORKERS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            return [m for m in executor.map(query_vm, uuids) if m]

    def get_all_vm_pci_mappings(self):
        """mapping: {host_pci_address: vm_pci_address}"""
        host_pci_mapping = {}
        for mapping in self._collect_vm_mappings_parallel(pci.get_pci_passthrough_mapping):
            for vm_pci_addr, host_pci_addr in mapping.items():
                host_pci_mapping[host_pci_addr] = vm_pci_addr
        return host_pci_mapping

    def get_all_vm_mdev_mappings(self):
        """mapping: {mdev_uuid: vm_pci_address}"""
        mdev_mapping = {}
        for mapping in self._collect_vm_mappings_parallel(pci.get_mdev_passthrough_mapping):
            mdev_mapping.update(mapping)
        return mdev_mapping

    def _set_generic_pci_device_type(self, to, pci_device_mapper, context=None):
        """
        Set generic PCI device type (non-GPU types only).

        Do not overwrite to.type when the device is already identified as a GPU
        by gpu.py (present in context.gpu_info_map). This uses the same source
        of truth as the GPU matcher (gpu_info_map) instead of hardcoding PCI
        class names; GPU type refinement is then done by the GPU processor.
        """
        if context and getattr(context, 'gpu_info_map', None):
            normalized = pci.normalize_pci_address(
                getattr(to, 'pciDeviceAddress', None) or '')
            if normalized and normalized in context.gpu_info_map:
                return
        if 'Ethernet controller' in to.type or (pci_device_mapper.get('Ethernet controller') is not None
                                                and pci_device_mapper.get('Ethernet controller') in to.type):
            to.type = "Ethernet_Controller"
        elif 'Audio device' in to.type or (pci_device_mapper.get('Audio device') is not None
                                           and pci_device_mapper.get('Audio device') in to.type):
            to.type = "Audio_Controller"
        elif 'USB controller' in to.type or (pci_device_mapper.get('USB controller') is not None
                                             and pci_device_mapper.get('USB controller') in to.type):
            to.type = "USB_Controller"
        elif 'Serial controller' in to.type or (pci_device_mapper.get('Serial controller') is not None
                                                and pci_device_mapper.get('Serial controller') in to.type):
            to.type = "Serial_Controller"
        elif 'Moxa Technologies' in to.type or (pci_device_mapper.get('Moxa Technologies') is not None
                                                and pci_device_mapper.get('Moxa Technologies') in to.type):
            to.type = "Moxa_Device"
        elif 'Host bridge' in to.type or (pci_device_mapper.get('Host bridge') is not None
                                          and pci_device_mapper.get('Host bridge') in to.type):
            to.type = "Host_Bridge"
        elif 'PCI bridge' in to.type or (pci_device_mapper.get('PCI bridge') is not None
                                         and pci_device_mapper.get('PCI bridge') in to.type):
            to.type = "PCI_Bridge"
        else:
            to.type = "Generic"

    # moved from vm_plugin to host_plugin
    @kvmagent.replyerror
    def get_pci_info(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetPciDevicesResponse()

        updateConfigration = UpdateConfigration()
        if not os.path.exists("/dev/vfio/vfio"):
            logger.info("enable vfio/vfio-pci module")
            updateConfigration.enable_vfio_module()

        if cmd.skipGrubConfig:
            rsp.hostIommuStatus = True
            self._collect_format_pci_device_info(rsp, cmd.opaque, cmd.pciDeviceAddresses)
            return jsonobject.dumps(rsp)

        # update grub to enable/disable iommu in host
        updateConfigration.path = "/etc/default/grub"
        updateConfigration.enableIommu = cmd.enableIommu
        success, error = updateConfigration.updateHostIommu()
        if success is False:
            rsp.success = False
            rsp.error = error
            return jsonobject.dumps(rsp)

        updateConfigration.updateGrubConfig()
        iommu_type = updateConfigration.iommu_type
        # check whether /sys/class/iommu is empty, if not then iommu is
        # activated in bios
        iommu_folder = '/sys/class/iommu'
        r_bios = os.path.isdir(iommu_folder) and os.listdir(iommu_folder)
        r_kernel, _, _ = bash_roe(
            "grep '{}=on' /proc/cmdline".format(iommu_type))
        if r_bios and r_kernel == 0:
            rsp.hostIommuStatus = True
        else:
            rsp.hostIommuStatus = False

        # get pci device info
        self._collect_format_pci_device_info(rsp, cmd.opaque, cmd.pciDeviceAddresses)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_pci_device_rom_file(self, req):
        PCI_ROM_PATH = "/var/lib/zstack/pcirom"
        if not os.path.exists(PCI_ROM_PATH):
            os.mkdir(PCI_ROM_PATH)

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreatePciDeviceRomFileRsp()
        rom_file = os.path.join(PCI_ROM_PATH, cmd.specUuid)
        if not cmd.romContent:
            if os.path.exists(rom_file):
                logger.debug(
                    "delete rom file %s because no content in db anymore" % rom_file)
                os.remove(rom_file)
        elif cmd.romMd5sum != hashlib.md5(cmd.romContent.encode()).hexdigest():
            rsp.success = False
            rsp.error = "md5sum of pci rom file[uuid:%s] does not match" % cmd.specUuid
            return jsonobject.dumps(rsp)
        else:
            content = base64.b64decode(cmd.romContent)
            with open(rom_file, 'wb') as f:
                f.write(content)
            logger.debug("successfully write rom content into %s" % rom_file)
        return jsonobject.dumps(rsp)

    @in_bash
    def _generate_sriov_gpu_devices(self, cmd, rsp):
        if cmd.vendor == "Vastai":
            self._configure_sriov_vfs(cmd, rsp)
            return
        # make install mxgpu driver if need to
        pci_device_mapper = {}
        mxgpu_driver_tar = "/var/lib/zstack/mxgpu_driver.tar.gz"
        if os.path.exists(mxgpu_driver_tar) and not os.path.exists(
                PCI_CONFIG_PATH):
            r, o, e = bash_roe(
                "tar xvf %s -C /tmp; cd /tmp/mxgpu_driver; make; make install" % mxgpu_driver_tar)
            if r != 0:
                rsp.success = False
                rsp.error = "failed to install mxgpu driver, %s, %s" % (o, e)
                return
            # rm mxgpu driver tar
            os.remove(mxgpu_driver_tar)

        # check installed ko and its usage
        _, used, _ = bash_roe("lsmod | grep gim | awk '{ print $3 }'")
        used = used.strip()

        if used and int(used) > 0:
            rsp.success = False
            rsp.error = "gim.ko already installed and being used, need to run `modprobe -r gim` first"
            return

        if used and int(used) == 0:
            _, used, _ = bash_roe(
                "modprobe -r gim; lsmod | grep gim | awk '{ print $3 }'")
            if used:
                rsp.success = False
                rsp.error = "failed to uninstall gim.ko, need to run `modprobe -r gim` manually"
                return

        # prepare gim_config
        gim_config = "/etc/gim_config"
        with open(gim_config, 'w') as f:
            f.write("vf_num=%s" % cmd.virtPartNum)

        command = 'modprobe gim'
        for line in linux.read_file_lines(PCI_CONFIG_PATH):
            parts = line.strip().split(':')
            if len(parts) == 2:
                key = parts[0].strip()
                value = parts[1].strip()
                pci_device_mapper[key] = value

        if 'command' in pci_device_mapper:
            command = pci_device_mapper['command'] % cmd.virtPartNum

        # install gim.ko
        r, o, e = bash_roe(command)
        if r != 0:
            rsp.success = False
            rsp.error = "failed to install gim.ko, %s, %s" % (o, e)

    @in_bash
    def _generate_sriov_net_devices(self, cmd, rsp):
        self._configure_sriov_vfs(cmd, rsp)

    @in_bash
    def _configure_sriov_vfs(self, cmd, rsp):
        numvfs = os.path.join('/sys/bus/pci/devices/',
                              cmd.pciDeviceAddress, 'sriov_numvfs')
        if not os.path.exists(numvfs):
            rsp.success = False
            rsp.error = 'cannot find sriov_numvfs file for gpu device[addr:%s, type:%s]' % (
                cmd.pciDeviceAddress, cmd.pciDeviceType)
            return

        r, o, e = bash_roe("echo %s > %s" % (cmd.virtPartNum, numvfs))
        if r != 0:
            rsp.success = False
            rsp.error = 'failed to generate virtual functions on gpu device[addr:%s, type:%s]' % (
                cmd.pciDeviceAddress, cmd.pciDeviceType)
            return

        for i in range(0, cmd.virtPartNum):
            bash_r("ip link set {interfaceName} vf {vf} spoofchk off; ip link set {interfaceName} vf {vf} trust on"
                   .format(interfaceName=cmd.interfaceName, vf=i))

    @kvmagent.replyerror
    def generate_sriov_pci_devices(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GenerateSriovPciDevicesRsp()
        logger.debug("generate_sriov_pci_devices: pciType[%s], pciAddr[%s], reSplite[%s]" % (
            cmd.pciDeviceType, cmd.pciDeviceAddress, cmd.reSplite))

        addr = cmd.pciDeviceAddress

        # ramdisk file in /dev/shm to mark host rebooting
        if cmd.pciDeviceType == 'Ethernet_Controller':
            ramdisk = "/dev/shm/pci_sriov_gim_" + addr
        else:
            ramdisk = "/dev/shm/pci_sriov_gim"

        if cmd.reSplite and os.path.exists(ramdisk):
            logger.debug(
                "no need to re-splite pci device[addr:%s] into sriov pci devices" % addr)
            return jsonobject.dumps(rsp)

        # Optimized: Check pciDeviceType first (fast path), then vendor, finally try all vendors
        # pciDeviceType may already indicate GPU type (e.g.,
        # 'GPU_3D_Controller')
        is_gpu_device = False
        if cmd.pciDeviceType and cmd.pciDeviceType.startswith('GPU_'):
            # Already identified as GPU type
            is_gpu_device = True
        elif hasattr(cmd, 'vendor') and cmd.vendor:
            # Check if vendor is a known GPU vendor (fast path)
            from zstacklib.gpu.base import VendorEnum
            gpu_vendors = {VendorEnum.NVIDIA, VendorEnum.AMD, VendorEnum.HUAWEI,
                           VendorEnum.HAIGUANG, VendorEnum.TIANSHU, VendorEnum.VASTAI,
                           VendorEnum.ENFLAME, VendorEnum.ALIBABA, VendorEnum.KUNLUNXIN,
                           VendorEnum.INTEL}
            if cmd.vendor in gpu_vendors:
                # Known GPU vendor, verify via get_info() (only queries that
                # vendor)
                gpu_info = gpu.get_info(
                    pci_address=cmd.pciDeviceAddress, vendor_name=cmd.vendor)
                is_gpu_device = gpu_info is not None
            else:
                # Vendor not in known set: fallback to batch query all vendors
                # This ensures devices detected by GPU CLI are not missed
                gpu_info_map = gpu.get_all_gpu_infos_by_pci()
                normalized_pci = pci.normalize_pci_address(
                    cmd.pciDeviceAddress)
                is_gpu_device = normalized_pci in gpu_info_map if normalized_pci else False
        else:
            # Unknown vendor/type: Try to get info from all vendors (batch query)
            # This is equivalent to is_gpu() but uses the same unified
            # interface
            gpu_info_map = gpu.get_all_gpu_infos_by_pci()
            normalized_pci = pci.normalize_pci_address(cmd.pciDeviceAddress)
            is_gpu_device = normalized_pci in gpu_info_map if normalized_pci else False

        if is_gpu_device:
            self._generate_sriov_gpu_devices(cmd, rsp)
        elif cmd.pciDeviceType == 'Ethernet_Controller':
            self._generate_sriov_net_devices(cmd, rsp)
        else:
            rsp.success = False
            rsp.error = "do not support sriov of pci device [addr:%s]" % addr

        if rsp.success:
            # create ramdisk file after pci device virtualization
            open(ramdisk, 'a').close()

        return jsonobject.dumps(rsp)

    @in_bash
    def _ungenerate_sriov_gpu_devices(self, cmd, rsp):
        if cmd.vendor == "Vastai":
            self._reset_sriov_vfs(cmd, rsp)
            return
        # remote gim.ko
        r, o, e = bash_roe("modprobe -r gim")
        if r != 0:
            rsp.success = False
            rsp.error = "failed to remove gim.ko, %s, %s" % (o, e)
            return

    @in_bash
    def _ungenerate_sriov_net_devices(self, cmd, rsp):
        self._reset_sriov_vfs(cmd, rsp)

    @in_bash
    def _reset_sriov_vfs(self, cmd, rsp):
        numvfs = os.path.join('/sys/bus/pci/devices/',
                              cmd.pciDeviceAddress, 'sriov_numvfs')
        if not os.path.exists(numvfs):
            rsp.success = False
            rsp.error = 'cannot find sriov_numvfs file for pci device[addr:%s, type:%s]' % (
                cmd.pciDeviceAddress, cmd.pciDeviceType)
            return

        def _check_allocated_virtual_functions():
            _addr = cmd.pciDeviceAddress

            if len(_addr.split(':')) != 3:
                _addr = '0000:' + _addr

            pf = "pci_%s_%s_%s_%s" % tuple(re.split('[:.]', _addr))
            r, vf_lines, e = bash_roe("virsh nodedev-dumpxml %s | grep 'address domain'" % pf)
            if r != 0:
                return "failed to run `virsh nodedev-dumpxml %s`: %s" % (pf, e)

            pattern = re.compile(
                r'.*0x([0-9a-f]*).*0x([0-9a-f]*).*0x([0-9a-f]*).*0x([0-9a-f]*).*')
            for vf_line in vf_lines.split('\n'):
                vf_line = vf_line.strip()
                match = pattern.match(vf_line)
                if match:
                    vf = "pci_%s_%s_%s_%s" % tuple(match.groups())
                    r, o, e = bash_roe(
                        "virsh nodedev-dumpxml %s | grep vfio-pci" % vf)
                    if r == 0:
                        return "virtual function %s of pf %s still allocated to some vm" % (
                            vf, pf)

        _error = _check_allocated_virtual_functions()
        if _error:
            rsp.success = False
            rsp.error = _error
            return

        r, o, e = bash_roe("lspci >/dev/null && echo 0 > %s" % numvfs)
        if r != 0:
            rsp.success = False
            rsp.error = 'failed to ungenerate virtual functions on pci device[addr:%s, type:%s]' % (
                cmd.pciDeviceAddress, cmd.pciDeviceType)
            return

    @kvmagent.replyerror
    def ungenerate_sriov_pci_devices(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UngenerateSriovPciDevicesRsp()

        addr = cmd.pciDeviceAddress

        # Optimized: Check pciDeviceType first (fast path), then vendor,
        # finally try all vendors
        is_gpu_device = False
        if cmd.pciDeviceType and cmd.pciDeviceType.startswith('GPU_'):
            # Already identified as GPU type
            is_gpu_device = True
        elif hasattr(cmd, 'vendor') and cmd.vendor:
            # Check if vendor is a known GPU vendor (fast path)
            from zstacklib.gpu.base import VendorEnum
            gpu_vendors = {VendorEnum.NVIDIA, VendorEnum.AMD, VendorEnum.HUAWEI,
                           VendorEnum.HAIGUANG, VendorEnum.TIANSHU, VendorEnum.VASTAI,
                           VendorEnum.ENFLAME, VendorEnum.ALIBABA, VendorEnum.KUNLUNXIN,
                           VendorEnum.INTEL}
            if cmd.vendor in gpu_vendors:
                # Known GPU vendor, verify via get_info() (only queries that
                # vendor)
                gpu_info = gpu.get_info(
                    pci_address=cmd.pciDeviceAddress, vendor_name=cmd.vendor)
                is_gpu_device = gpu_info is not None
            else:
                # Vendor not in known set: fallback to batch query all vendors
                # This ensures devices detected by GPU CLI are not missed
                gpu_info_map = gpu.get_all_gpu_infos_by_pci()
                normalized_pci = pci.normalize_pci_address(
                    cmd.pciDeviceAddress)
                is_gpu_device = normalized_pci in gpu_info_map if normalized_pci else False
        else:
            # Unknown vendor/type: Try to get info from all vendors (batch query)
            # This is equivalent to is_gpu() but uses the same unified
            # interface
            gpu_info_map = gpu.get_all_gpu_infos_by_pci()
            normalized_pci = pci.normalize_pci_address(cmd.pciDeviceAddress)
            is_gpu_device = normalized_pci in gpu_info_map if normalized_pci else False

        if is_gpu_device:
            self._ungenerate_sriov_gpu_devices(cmd, rsp)
        elif cmd.pciDeviceType == 'Ethernet_Controller':
            self._ungenerate_sriov_net_devices(cmd, rsp)
        else:
            rsp.success = False
            rsp.error = "do not support sriov of pci device [addr:%s]" % addr

        return jsonobject.dumps(rsp)

    def _generate_nvidia_vfio_mdev_devices(self, cmd):
        rsp = GenerateVfioMdevDevicesRsp()
        addr = cmd.pciDeviceAddress
        # before 3.5.1, pciDeviceAddress is composed by only bus:slot.func
        no_domain_addr = addr if len(addr.split(
            ':')) != 3 else ':'.join(addr.split(':')[1:])
        ramdisk = os.path.join('/dev/shm', 'pci-' + no_domain_addr)
        if cmd.mdevUuids and len(
                cmd.mdevUuids) != 0 and os.path.exists(ramdisk):
            logger.debug(
                "no need to re-splite pci device[addr:%s] into mdev devices" % addr)
            return jsonobject.dumps(rsp)

        @linux.retry(times=30, sleep_time=5)
        def _exec_nvidia_sriov_manage(addr):
            bash_roe("/usr/lib/nvidia/sriov-manage -e %s" % addr)

        # virtualization needs to be enabled when restarting the host to sync
        # vgpu mdev
        if os.path.exists('/usr/lib/nvidia/sriov-manage'):
            _exec_nvidia_sriov_manage(addr)

        # support nvidia gpu only
        type = int(cmd.mdevSpecTypeId, 0)
        spec_path = os.path.join(
            "/sys/bus/pci/devices/", addr, "mdev_supported_types", "nvidia-%d" % type)
        legacy_spec_exists = os.path.exists(spec_path)
        virtfn_path = os.path.join(
            "/sys/bus/pci/devices/", addr, "virtfn0", "mdev_supported_types", "nvidia-%d" % type)
        virt_function_spec_exits = os.path.exists(virtfn_path)

        if not legacy_spec_exists and not virt_function_spec_exits:
            rsp.success = False
            rsp.error = "cannot generate vfio mdev devices from pci device[addr:%s]" % addr
            return jsonobject.dumps(rsp)

        if legacy_spec_exists:
            if cmd.mdevUuids and len(cmd.mdevUuids) != 0:
                for _uuid in cmd.mdevUuids:
                    with open(os.path.join(spec_path, "create"), 'w') as f:
                        f.write(str(uuid.UUID(_uuid)))
                        logger.debug(
                            "re-generate mdev device[uuid:%s] from pci device[addr:%s]" % (_uuid, addr))
            else:
                with open(os.path.join(spec_path, "available_instances"), 'r') as af:
                    max_instances = af.read().strip()
                for i in range(int(max_instances)):
                    _uuid = str(uuid.uuid4())
                    rsp.mdevUuids.append(_uuid)
                    with open(os.path.join(spec_path, "create"), 'w') as cf:
                        cf.write(_uuid)
                        logger.debug(
                            "generate mdev device[uuid:%s] from pci device[addr:%s]" % (_uuid, addr))
        elif virt_function_spec_exits:
            r, o, e = bash_roe(
                "ls /sys/bus/pci/devices/%s/ | grep virtfn" % addr)
            if r != 0:
                rsp.success = False
                rsp.error = e
                return jsonobject.dumps(rsp)

            if cmd.mdevUuids and len(cmd.mdevUuids) != 0:
                for _uuid, virtfn in zip(cmd.mdevUuids, o.splitlines()):
                    virtfn_dir = "/sys/bus/pci/devices/%s/%s/mdev_supported_types/nvidia-%d" % (
                        addr, virtfn, type)
                    with open(os.path.join(virtfn_dir, "create"), 'w') as f:
                        f.write(str(uuid.UUID(_uuid)))
                        logger.debug(
                            "re-generate mdev device[uuid:%s] from pci device[addr:%s]" % (_uuid, addr))
            else:
                is_generate = False
                for virtfn in o.splitlines():
                    virtfn_dir = "/sys/bus/pci/devices/%s/%s/mdev_supported_types/nvidia-%d" % (
                        addr, virtfn, type)
                    with open(os.path.join(virtfn_dir, "available_instances"), 'r') as af:
                        max_instances = af.read().strip()
                        if int(max_instances) > 0:
                            is_generate = True
                    for i in range(int(max_instances)):
                        _uuid = str(uuid.uuid4())
                        rsp.mdevUuids.append(_uuid)
                        with open(os.path.join(virtfn_dir, "create"), 'w') as cf:
                            cf.write(_uuid)
                            logger.debug(
                                "generate mdev device[uuid:%s] from pci device[addr:%s]" % (_uuid, addr))

                if not is_generate:
                    with open(os.path.join(virtfn_path, "name"), 'r') as f:
                        name = f.read().strip()
                    rsp.success = False
                    rsp.error = "generate mdev device[name:%s] from pci device[addr:%s] is fail " % (
                        name, addr)

        # create ramdisk file after pci device virtualization
        open(ramdisk, 'a').close()
        return jsonobject.dumps(rsp)

    def _generate_huawei_vfio_mdev_devices(self, cmd):
        rsp = GenerateVfioMdevDevicesRsp()
        addr = cmd.pciDeviceAddress
        r, virtStatusOut = bash_ro("ls -l  /sys/bus/mdev/devices/")
        if r == 0 and addr in virtStatusOut:
            logger.debug(
                "no need to re-splite pci device[addr:%s] into mdev devices" % addr)
            return jsonobject.dumps(rsp)

        r, o = bash_ro("npu-smi set -t vnpu-mode -d 1")
        if r != 0:
            rsp.success = False
            rsp.error = o
            return jsonobject.dumps(rsp)

        spec_path = os.path.join("/sys/bus/pci/devices/", addr,
                                 "mdev_supported_types", "vnpu-%s" % cmd.mdevSpecTypeId)
        if not os.path.exists(spec_path):
            rsp.success = False
            rsp.error = "cannot generate vfio mdev devices from pci device[addr:%s]" % addr
            return jsonobject.dumps(rsp)

        if cmd.mdevUuids and len(cmd.mdevUuids) != 0:
            for _uuid in cmd.mdevUuids:
                with open(os.path.join(spec_path, "create"), 'w') as f:
                    f.write(str(uuid.UUID(_uuid)))
                    logger.debug(
                        "re-generate mdev device[uuid:%s] from pci device[addr:%s]" % (_uuid, addr))
            return jsonobject.dumps(rsp)

        with open(os.path.join(spec_path, "available_instances"), 'r') as af:
            max_instances = af.read().strip()
        for i in range(int(max_instances)):
            _uuid = str(uuid.uuid4())
            rsp.mdevUuids.append(_uuid)
            with open(os.path.join(spec_path, "create"), 'w') as cf:
                cf.write(_uuid)
                logger.debug(
                    "generate mdev device[uuid:%s] from pci device[addr:%s]" % (_uuid, addr))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def generate_vfio_mdev_devices(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GenerateVfioMdevDevicesRsp()
        logger.debug(
            "generate_vfio_mdev_devices: mdevUuids[%s]" % cmd.mdevUuids)
        if cmd.vendor == VendorEnum.NVIDIA:
            return self._generate_nvidia_vfio_mdev_devices(cmd)
        elif cmd.vendor == VendorEnum.HUAWEI:
            return self._generate_huawei_vfio_mdev_devices(cmd)
        else:
            rsp.success = False
            rsp.error = "%s device does not support being generated into mdev devices" % (
                cmd.vendor)
            return jsonobject.dumps(rsp)

    def _ungenerate_nvidia_vfio_mdev_devices(self, cmd):
        rsp = UngenerateVfioMdevDevicesRsp()
        # support nvidia gpu only
        addr = cmd.pciDeviceAddress
        type = int(cmd.mdevSpecTypeId, 0)
        device_path = os.path.join(
            "/sys/bus/pci/devices/", addr, "mdev_supported_types", "nvidia-%d" % type, "devices")
        legacy_spec_exists = os.path.exists(device_path)
        virtfn_path = os.path.join("/sys/bus/pci/devices/", addr, "virtfn0", "mdev_supported_types", "nvidia-%d" % type,
                                   "devices")
        virt_function_dir_exits = os.path.exists(virtfn_path)

        if not legacy_spec_exists and not virt_function_dir_exits:
            rsp.success = False
            rsp.error = "no vfio mdev devices to ungenerate from pci device[addr:%s]" % addr
            return jsonobject.dumps(rsp)
        # remove legacy device
        if legacy_spec_exists:
            for _uuid in os.listdir(device_path):
                with open(os.path.join(device_path, _uuid, "remove"), 'w') as f:
                    f.write("1")

            # check
            _, support, _ = bash_roe(
                "nvidia-smi vgpu -i %s -s | grep -v %s" % (addr, addr))
            _, creatable, _ = bash_roe(
                "nvidia-smi vgpu -i %s -c | grep -v %s" % (addr, addr))
            if support != creatable:
                rsp.success = False
                rsp.error = "failed to ungenerate vfio mdev devices from pci device[addr:%s]" % addr
        elif virt_function_dir_exits:
            r, o, e = bash_roe(
                "ls /sys/bus/pci/devices/%s/ | grep virtfn" % addr)
            if r != 0:
                rsp.success = False
                rsp.error = e
                return jsonobject.dumps(rsp)

            for virtfn in o.splitlines():
                virtfn_dir = os.path.join("/sys/bus/pci/devices/", addr, virtfn, "mdev_supported_types",
                                          "nvidia-%d" % type, "devices")
                for _uuid in os.listdir(virtfn_dir):
                    with open(os.path.join(virtfn_dir, _uuid, "remove"), "w") as f:
                        f.write("1")

        return jsonobject.dumps(rsp)

    def _ungenerate_huawei_vfio_mdev_devices(self, cmd):
        rsp = UngenerateVfioMdevDevicesRsp()
        device_path = os.path.join("/sys/bus/pci/devices/", cmd.pciDeviceAddress,
                                   "mdev_supported_types", "vnpu-%s" % cmd.mdevSpecTypeId, "devices")
        if not os.path.exists(device_path):
            rsp.success = False
            rsp.error = "no vfio mdev devices to ungenerate from pci device[addr:%s]" % cmd.pciDeviceAddress
            return jsonobject.dumps(rsp)

        for _uuid in os.listdir(device_path):
            with open(os.path.join(device_path, _uuid, "remove"), 'w') as f:
                f.write("1")

        r, virtStatusOut = bash_ro("ls -l  /sys/bus/mdev/devices/")
        if r == 0 and cmd.pciDeviceAddress in virtStatusOut:
            rsp.success = False
            rsp.error = "failed to ungenerate vfio mdev devices from pci device[addr:%s]" % cmd.pciDeviceAddress

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def ungenerate_vfio_mdev_devices(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UngenerateVfioMdevDevicesRsp()

        if cmd.vendor == VendorEnum.NVIDIA:
            return self._ungenerate_nvidia_vfio_mdev_devices(cmd)
        elif cmd.vendor == VendorEnum.HUAWEI:
            return self._ungenerate_huawei_vfio_mdev_devices(cmd)
        else:
            rsp.success = False
            rsp.error = "%s device does not support being ungenerate into mdev devices" % (
                cmd.vendor)
            return jsonobject.dumps(rsp)

    def _collect_format_mtty_device_info(self, rsp):
        r, o, e = bash_roe("ls /dev/wst-se")
        if r != 0:
            return

        check_virtfn_folder = '/sys/devices/virtual/mtty/mtty/mdev_supported_types'
        virt_function_dir_exits = os.path.isdir(check_virtfn_folder)
        if not virt_function_dir_exits:
            return

        # parse mtty output
        to = MttyDeviceTO()
        to.type = "SE_Controller"
        to.description = to.type + ": " + "computing encryption device"
        to.name = "SE"

        se_num_record_file = "%s/mtty-2/available_instances" % check_virtfn_folder
        se_num_record_file_exits = os.path.isfile(se_num_record_file)
        if not se_num_record_file_exits:
            to.virtStatus = "UNKNOWN"
            rsp.mttyDeviceInfo = to
            return

        mdev_r, mdev_o, _ = bash_roe("grep -w 12 %s" % se_num_record_file)
        if mdev_r != 0:
            to.virtStatus = "VFIO_MDEV_VIRTUALIZED"
        else:
            to.virtStatus = "VFIO_MDEV_VIRTUALIZABLE"
        rsp.mttyDeviceInfo = to
        return

    @kvmagent.replyerror
    def get_mtty_info(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetMttyDevicesResponse()

        # get mtty device info
        self._collect_format_mtty_device_info(rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def generate_se_vfio_mdev_devices(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GenerateSeVfioMdevDevicesRsp()
        logger.debug(
            "generate_se_vfio_mdev_devices: mdevUuids[%s]" % cmd.mdevUuids)

        mtty_uuid = cmd.mttyDeviceUuid
        ramdisk = os.path.join('/dev/shm', 'mtty-' + mtty_uuid)
        if cmd.reSplite and os.path.exists(ramdisk):
            logger.debug(
                "no need to re-splite mtty device[uuid:%s] into mdev devices" % mtty_uuid)
            return jsonobject.dumps(rsp)

        virt_path = "/sys/devices/virtual/mtty/mtty/mdev_supported_types/mtty-2/"
        virt_path_exits = os.path.exists(virt_path)
        if not virt_path_exits:
            rsp.success = False
            rsp.error = "cannot generate se vfio mdev devices from mtty device[uuid:%s]" % mtty_uuid
            return jsonobject.dumps(rsp)

        for _uuid in cmd.mdevUuids:
            with open(os.path.join(virt_path, "create"), 'w') as f:
                f.write(str(uuid.UUID(_uuid)))
                if not cmd.reSplite:
                    rsp.mdevUuids.append(str(uuid.UUID(_uuid)))
                logger.debug('generate mdev device[uuid:%s] from mtty device[uuid:%s]' % (
                    str(_uuid), mtty_uuid))

        # create ramdisk file after mtty device virtualization
        open(ramdisk, 'a').close()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def ungenerate_se_vfio_mdev_devices(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UngenerateSeVfioMdevDevicesRsp()

        mtty_uuid = cmd.mttyDeviceUuid
        virt_function = "/sys/devices/virtual/mtty/mtty/mdev_supported_types/mtty-2/devices"
        virt_function_exits = os.path.exists(virt_function)
        if not virt_function_exits:
            rsp.success = False
            rsp.error = "no vfio mdev device[uuid:%s] to delete" % mtty_uuid
            return jsonobject.dumps(rsp)

        for _uuid in os.listdir(virt_function):
            with open(os.path.join("/sys/bus/mdev/devices/", _uuid, "remove"), "w") as f:
                f.write("1")

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def delete_vfio_mdev_device(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteVfioMdevDeviceRsp()

        _uuid = str(uuid.UUID(cmd.MdevDeviceUuid))
        virt_function = "/sys/devices/virtual/mtty/mtty/mdev_supported_types/mtty-2/devices"
        virt_function_exits = os.path.exists(virt_function)
        if not virt_function_exits:
            rsp.success = False
            rsp.error = "no vfio mdev devices to ungenerate from mtty device[uuid:%s]" % _uuid
            return jsonobject.dumps(rsp)

        with open(os.path.join("/sys/bus/mdev/devices/", _uuid, "remove"), "w") as f:
            f.write("1")

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def update_spice_channel_config(self, req):
        # Note: /etc/libvirt/qemu.conf is overwritten when connect host
        rsp = UpdateSpiceChannelConfigResponse()
        r1 = bash_r(
            "grep '^[[:space:]]*spice_tls[[:space:]]*=[[:space:]]*1' /etc/libvirt/qemu.conf")
        r2 = bash_r(
            "grep '^[[:space:]]*spice_tls_x509_cert_dir[[:space:]]*=[[:space:]]*' /etc/libvirt/qemu.conf")

        if r1 == 0 and r2 == 0:
            return jsonobject.dumps(rsp)

        if r1 != 0:
            r = bash_r("sed -i '$a spice_tls = 1' /etc/libvirt/qemu.conf")
            if r != 0:
                rsp.success = False
                rsp.error = "update /etc/libvirt/qemu.conf failed, please check qemu.conf"
                return jsonobject.dumps(rsp)

        if r2 != 0:
            r = bash_r(
                "sed -i '$a spice_tls_x509_cert_dir = \"/var/lib/zstack/kvm/package/spice-certs/\"' /etc/libvirt/qemu.conf")
            if r != 0:
                rsp.success = False
                rsp.error = "update /etc/libvirt/qemu.conf failed, please check qemu.conf"
                return jsonobject.dumps(rsp)

        rsp.restartLibvirt = False
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def cancel(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        return jsonobject.dumps(plugin.cancel_job(cmd, rsp))

    @kvmagent.replyerror
    def transmit_vm_operation_to_vm(self, req):
        rsp = TransmitVmOperationToMnRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        vm_operation = VmOperation()
        vm_operation.uuid = cmd.uuid
        vm_operation.operation = cmd.operation
        url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not url:
            raise kvmagent.KvmError(
                "cannot find SEND_COMMAND_URL, unable to transmit vm operation to management node")

        logger.debug('transmitting vm operation [uuid:%s, operation:%s] to management node' % (
            cmd.uuid, cmd.operation))
        http.json_dump_post(url, vm_operation, {
                            'commandpath': '/host/transmitvmoperation'})
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def transmit_zwatch_install_result_to_mn(self, req):
        rsp = ZwatchInstallResultRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        result = ZwatchInstallResult()
        result.vmInstanceUuid = cmd.vmInstanceUuid
        result.version = cmd.version
        url = self.config.get(kvmagent.SEND_COMMAND_URL)
        if not url:
            raise kvmagent.KvmError(
                "cannot find SEND_COMMAND_URL, unable to transmit zwatch install result to management node")

        logger.debug('transmitting zwatch install result [uuid:%s, version:%s] to management node' % (
            cmd.vmInstanceUuid, cmd.version))
        http.json_dump_post(
            url, result, {'commandpath': '/host/zwatchInstallResult'})
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def update_host_configuration(self, req):
        rsp = kvmagent.AgentResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        self.config[kvmagent.SEND_COMMAND_URL] = cmd.sendCommandUrl
        Report.url = cmd.sendCommandUrl

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def deploy_colo_qemu(self, req):
        rsp = kvmagent.AgentResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        releasever = kvmagent.get_host_yum_release()
        tmpl = {'releasever': releasever}
        qemu_url = string.Template(cmd.qemuUrl).substitute(tmpl)

        if not os.path.exists(COLO_LIB_PATH):
            os.makedirs(COLO_LIB_PATH, 0o775)

        def get_dep_version_from_version_file(version_file):
            if not os.path.exists(version_file):
                return None
            else:
                with open(version_file, 'r') as vfd:
                    return vfd.readline()

        last_modified = shell.call(
            "curl -I %s | grep 'Last-Modified'" % qemu_url).strip('\n\r')
        version = get_dep_version_from_version_file(COLO_QEMU_KVM_VERSION)
        if version != last_modified:
            cmdstr = 'cd {} && rm -f qemu-system-x86_64.tar.gz && wget -c {} -O qemu-system-x86_64.tar.gz && ' \
                     'tar zxf qemu-system-x86_64.tar.gz && chown root:root qemu-system-x86_64'.format(
                         COLO_LIB_PATH, qemu_url)
            if shell.run(cmdstr) != 0:
                rsp.success = False
                rsp.error = "failed to download qemu-system-x86_64.tar.gz from management node"
                return jsonobject.dumps(rsp)

        with open(COLO_QEMU_KVM_VERSION, 'w') as fd:
            fd.write(last_modified)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def scan_vm_port(self, req):
        rsp = ScanVmPortRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        ports = []
        # r, o, e = bash_roe("ip netns exec %s nmap -sT -p %s %s" % (cmd.brname, cmd.port, cmd.ip))
        if "," in str(cmd.port):
            ports = str(cmd.port).split(",")
        else:
            ports.append(str(cmd.port))

        for port in ports:
            r, o, e = bash_roe(
                "ip netns exec %s nping --tcp -p %s -c 1 %s" % (cmd.brname, port, cmd.ip))
            if r != 0:
                rsp.success = False
                rsp.error = e
                return jsonobject.dumps(rsp)
            else:
                rsp.portStatus.update(linux.check_nping_result(port, o))

        return jsonobject.dumps(rsp)

    def _try_reload_modprobe(self, module_name):
        o = shell.ShellCmd("modprobe -r %s" % module_name)
        o(False)
        if o.return_code != 0:
            logger.warn("reload module %s failed" % module_name)
        else:
            shell.run("modprobe %s" % module_name)

    def _check_vhost_net_conf(self, expect_value):
        conf_path = "/etc/modprobe.d/vhost-net.conf"
        expect_conf = "options vhost_net experimental_zcopytx=%s" % expect_value
        if not os.path.exists(conf_path):
            linux.write_file(conf_path, expect_conf, True)
            return

        exist_conf = linux.read_file(conf_path)
        if exist_conf != expect_conf:
            linux.write_file(conf_path, expect_conf)

    @kvmagent.replyerror
    @in_bash
    def enable_zerocopy(self, req):
        rsp = EnableZeroCopyRsp()

        self._check_vhost_net_conf(1)
        self._try_reload_modprobe('vhost_net')

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def disable_zerocopy(self, req):
        rsp = EnableZeroCopyRsp()

        self._check_vhost_net_conf(0)
        self._try_reload_modprobe('vhost_net')

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_block_devices(self, req):
        rsp = GetBlockDevicesRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        all_devices = lvm.get_block_devices() # type: list[lvm.SharedBlockCandidateStruct]
        if not cmd.includeInUse:
            all_devices = list(filter(lambda dev: not linux.is_block_device_mounted(dev.name), all_devices))
        rsp.blockDevices = all_devices
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_dev_capacity(self, req):
        rsp = GetDevCapacityRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp.totalSize = linux.get_total_disk_size(cmd.dirPath)
        rsp.availableSize = linux.get_free_disk_size(cmd.dirPath)
        # a task may preoccupy some space by a sparse file and fill this file as the task goes on.
        # so we must check the apparent size of the cache directory here.
        rsp.dirSize = linux.get_used_disk_apparent_size(cmd.dirPath, 4, 1)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def add_bridge_fdb_entry(self, req):
        rsp = AddBridgeFdbEntryRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        errors = []
        if cmd.macs:
            for mac in cmd.macs:
                iproute.add_fdb_entry(cmd.physicalInterface, mac)

        if errors:
            rsp.success = False
            rsp.error = ';'.join(errors)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def del_bridge_fdb_entry(self, req):
        rsp = AddBridgeFdbEntryRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        errors = []
        if cmd.macs:
            for mac in cmd.macs:
                iproute.del_fdb_entry(cmd.physicalInterface, mac)

        if errors:
            rsp.success = False
            rsp.error = ';'.join(errors)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_numa_topology(self, req):
        class NumaTopology:
            def __init__(self):
                self.nodes = {}
                self.get_topology()

            def __call__(self, *args, **kwargs):
                return self.nodes

            def get_topology(self):
                node_id = 0
                while True:
                    node_path = os.path.join(
                        NODE_INFO_PATH, "node{}".format(node_id))
                    if not os.path.isdir(node_path):
                        break

                    cpulist_path = os.path.join(node_path, "cpulist")
                    meminfo_path = os.path.join(node_path, "meminfo")
                    distance_path = os.path.join(node_path, "distance")

                    size, free = self.get_meminfo(meminfo_path)
                    self.nodes[str(node_id)] = {
                        "cpus": self.get_cpu_list(cpulist_path),
                        "free": free,
                        "size": size,
                        "distance": self.get_distance(distance_path)
                    }

                    node_id += 1

            @staticmethod
            def get_cpu_list(info_path):
                data = None
                with open(info_path, "r") as f:
                    data = f.read()

                if data is None or (not data):
                    return

                data = data.strip()
                cpu_list = []
                info = data.split(",")
                for i in info:
                    if "-" in i:
                        temp = i.split("-")
                        cpu_list.extend([str(cpu_id) for cpu_id in range(
                            int(temp[0]), int(temp[1]) + 1)])
                    elif "^" in i:
                        cpu_list.remove(i[1:])
                    else:
                        cpu_list.append(i)
                return cpu_list

            @staticmethod
            def get_meminfo(info_path):
                data = None
                with open(info_path, "r") as f:
                    data = f.readlines()
                if data is None or (not data):
                    return

                free, size = 0, 0
                for mem in data:
                    temp = [i for i in mem.strip().split(" ") if i][-2]
                    if temp == "0":
                        continue
                    if "MemTotal" in mem:
                        size = int(temp) * 1024
                    if "MemFree:" in mem:
                        free = int(temp) * 1024
                return size, free

            @staticmethod
            def get_distance(info_path):
                data = None
                with open(info_path, "r") as f:
                    data = f.read()
                if data is None or (not data):
                    return
                data = data.strip()
                return [i for i in data.split(" ") if i]

        rsp = GetNumaTopologyResponse()
        rsp.topology = NumaTopology()()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def attach_volume_path(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AttachVolumeRsp()
        if cmd.volumeInstallPath is None:
            raise Exception("volume install path can not be null")
        if cmd.mountPath is None:
            raise Exception("mount path can not be null")

        if cmd.volumeInstallPath.startswith('sharedblock'):
            rsp.device = lvm.LvmRemoteStorage(
                cmd.volumeInstallPath, cmd.mountPath, cmd.device).mount()
        elif cmd.volumeInstallPath.startswith('ceph'):
            rsp.device = ceph.NbdRemoteStorage(
                cmd.volumeInstallPath, cmd.mountPath, cmd.device, cmd.volumePrimaryStorageUuid).mount()
        else:
            raise Exception("do not support volume type")

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def detach_volume__path(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        if cmd.volumeInstallPath is None:
            raise Exception("volume install path can not be null")
        if cmd.mountPath is None:
            raise Exception("mount path can not be null")
        if cmd.device is None:
            raise Exception("device can not be null")

        if cmd.volumeInstallPath.startswith('sharedblock'):
            lvm.LvmRemoteStorage(cmd.volumeInstallPath,
                                 cmd.mountPath, cmd.device).umount()
        elif cmd.volumeInstallPath.startswith('ceph'):
            ceph.NbdRemoteStorage(cmd.volumeInstallPath,
                                  cmd.mountPath, cmd.device).umount()
        else:
            raise Exception("do not support volume type")

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def setup_vm_ha_enabled_metadata_live(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        self._setup_vm_ha_enabled_metadata_live(cmd.vmUuid, self._to_bool(cmd.enableHa))
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def reconcile_vm_ha_enabled_metadata_live(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        never_stop_vm_uuids = set(cmd.neverStopVmUuids or [])
        running_vm_uuids = self._get_running_vm_uuids_on_host()
        failed_updates = []
        for vm_uuid in running_vm_uuids:
            enable_ha = vm_uuid in never_stop_vm_uuids
            try:
                self._setup_vm_ha_enabled_metadata_live(vm_uuid, enable_ha)
            except Exception as e:
                failed_updates.append('%s: %s' % (vm_uuid, e))

        if failed_updates:
            rsp.success = False
            rsp.error = '; '.join(failed_updates)
        return jsonobject.dumps(rsp)


    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            return value.lower() == 'true'

        return value is not None and bool(value)

    def _get_running_vm_uuids_on_host(self):
        running_vm_uuids = set(vm_plugin.get_all_vm_states_with_process().keys())
        for vm in vm_plugin.get_running_vms():
            running_vm_uuids.add(vm.uuid)

        return running_vm_uuids

    def _setup_vm_ha_enabled_metadata_live(self, vm_uuid, enable_ha):
        if enable_ha:
            self._setup_vm_zstack_metadata_live(vm_uuid, 'enableHa', 'true')
        else:
            self._delete_vm_zstack_metadata_live(vm_uuid, 'enableHa')

    def _setup_vm_zstack_metadata_live(self, vm_uuid, metadata_key, metadata_value):
        updated, old_metadata_value, reason = vm_plugin.set_zstack_metadata_live(vm_uuid, metadata_key, metadata_value)
        if reason == 'vmNotFound':
            logger.debug('cannot find vm[uuid:%s] when updating %s metadata, skip' % (vm_uuid, metadata_key))
            return

        if reason == 'vmStateNotSupport':
            vm = vm_plugin.get_vm_by_uuid(vm_uuid, exception_if_not_existing=False)
            vm_state = vm.state if vm else 'Unknown'
            logger.debug('vm[uuid:%s] state[%s] does not support live %s metadata update, skip' % (
                vm_uuid, vm_state, metadata_key))
            return

        if reason == 'unchanged':
            logger.debug('vm[uuid:%s] %s metadata already %s, skip live update' % (
                vm_uuid, metadata_key, metadata_value))
            return

        if not updated:
            logger.debug('vm[uuid:%s] skip updating %s metadata due to unexpected reason[%s]' % (
                vm_uuid, metadata_key, reason))
            return

        logger.debug('updated vm[uuid:%s] %s metadata from %s to %s on host' % (
            vm_uuid, metadata_key, old_metadata_value, metadata_value))

    def _delete_vm_zstack_metadata_live(self, vm_uuid, metadata_key):
        updated, old_metadata_value, reason = vm_plugin.delete_zstack_metadata_live(vm_uuid, metadata_key)
        if reason == 'vmNotFound':
            logger.debug('cannot find vm[uuid:%s] when deleting %s metadata, skip' % (vm_uuid, metadata_key))
            return

        if reason == 'vmStateNotSupport':
            vm = vm_plugin.get_vm_by_uuid(vm_uuid, exception_if_not_existing=False)
            vm_state = vm.state if vm else 'Unknown'
            logger.debug('vm[uuid:%s] state[%s] does not support live %s metadata deletion, skip' % (
                vm_uuid, vm_state, metadata_key))
            return

        if reason == 'unchanged':
            logger.debug('vm[uuid:%s] %s metadata already absent, skip live deletion' % (
                vm_uuid, metadata_key))
            return

        if not updated:
            logger.debug('vm[uuid:%s] skip deleting %s metadata due to unexpected reason[%s]' % (
                vm_uuid, metadata_key, reason))
            return

        logger.debug('deleted vm[uuid:%s] %s metadata, old value %s on host' % (
            vm_uuid, metadata_key, old_metadata_value))

    @kvmagent.replyerror
    def update_vm_console_password_live(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        if not cmd.password:
            raise kvmagent.KvmError('Password cannot be empty')
        vm = vm_plugin.get_vm_by_uuid(cmd.vmUuid)
        if vm.state != vm_plugin.Vm.VM_STATE_RUNNING:
            raise kvmagent.KvmError(
                'VM[uuid:%s] is not running, cannot set password live.' % cmd.vmUuid)

        console_modes = []
        graphics_devices = vm.domain_xmlobject.devices.get_child_node_as_list(
            'graphics')
        for g in graphics_devices:
            if g.type_ == 'vnc':
                console_modes.append('vnc')
            elif g.type_ == 'spice':
                console_modes.append('spice')

        if not console_modes:
            raise kvmagent.KvmError(
                'VM[uuid:%s] has no graphical console (VNC/SPICE) configured.' % cmd.vmUuid)

        logger.debug("Found console modes %s for VM[uuid:%s]" % (
            console_modes, cmd.vmUuid))

        errors = []
        if 'vnc' in console_modes:
            hmp_cmd = "set_password vnc %s" % cmd.password
            safe_hmp_arg = shell_quote(hmp_cmd)
            command = "virsh qemu-monitor-command %s --hmp %s" % (
                cmd.vmUuid, safe_hmp_arg)
            r, o, e = bash_roe(command)
            if r != 0:
                errors.append("Failed to set VNC password: %s" % e)
            else:
                logger.debug(
                    "Successfully set VNC password for VM[uuid:%s]" % cmd.vmUuid)

        if 'spice' in console_modes:
            hmp_cmd = "set_password spice %s" % cmd.password
            safe_hmp_arg = shell_quote(hmp_cmd)
            command = "virsh qemu-monitor-command %s --hmp %s" % (
                cmd.vmUuid, safe_hmp_arg)
            r, o, e = bash_roe(command)
            if r != 0:
                errors.append("Failed to set SPICE password: %s" % e)
            else:
                logger.debug(
                    "Successfully set SPICE password for VM[uuid:%s]" % cmd.vmUuid)

        if errors:
            raise kvmagent.KvmError(". ".join(errors))

        return jsonobject.dumps(rsp)

    @property
    def libvirt_version(self):
        return linux.get_libvirt_version()

    @property
    def qemu_version(self):
        return qemu.get_version()

    def start(self):
        self.host_uuid = None
        self.host_socket = None

        http_server = kvmagent.get_http_server()
        http_server.register_sync_uri(self.CONNECT_PATH, self.connect)
        http_server.register_async_uri(self.PING_PATH, self.ping)
        http_server.register_async_uri(
            self.CHECK_FILE_ON_HOST_PATH, self.check_file_on_host)
        http_server.register_async_uri(self.CAPACITY_PATH, self.capacity)
        http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        http_server.register_async_uri(
            self.SETUP_MOUNTABLE_PRIMARY_STORAGE_HEARTBEAT, self.setup_heartbeat_file)
        http_server.register_async_uri(self.FACT_PATH, self.fact)
        http_server.register_async_uri(
            self.GET_USB_DEVICES_PATH, self.get_usb_devices)
        http_server.register_async_uri(self.UPDATE_OS_PATH, self.update_os)
        http_server.register_async_uri(
            self.INIT_HOST_MOC_PATH, self.init_host_moc)
        http_server.register_async_uri(
            self.UPDATE_DEPENDENCY, self.update_dependency)
        http_server.register_async_uri(
            self.ENABLE_HUGEPAGE, self.enable_hugepage)
        http_server.register_async_uri(
            self.DISABLE_HUGEPAGE, self.disable_hugepage)
        http_server.register_async_uri(
            self.CLEAN_LOCAL_CACHE, self.clean_local_cache)
        http_server.register_async_uri(
            self.HOST_START_USB_REDIRECT_PATH, self.start_usb_redirect_server)
        http_server.register_async_uri(
            self.HOST_STOP_USB_REDIRECT_PATH, self.stop_usb_redirect_server)
        http_server.register_async_uri(
            self.CHECK_USB_REDIRECT_PORT, self.check_usb_server_port)
        http_server.register_async_uri(self.IDENTIFY_HOST, self.identify_host)
        http_server.register_async_uri(
            self.LOCATE_HOST_NETWORK_INTERFACE, self.locate_host_network_interface)
        http_server.register_async_uri(
            self.GET_HOST_PHYSICAL_MEMORY_FACTS, self.get_host_physical_memory_facts)
        http_server.register_async_uri(
            self.UPDATE_HOST_OVS_CPU_PINNING, self.update_ovs_cpu_pinning)
        http_server.register_async_uri(
            self.CHANGE_PASSWORD, self.change_password, cmd=ChangeHostPasswordCmd())
        http_server.register_async_uri(
            self.GET_HOST_NETWORK_FACTS, self.get_host_network_facts)
        http_server.register_async_uri(
            self.SET_IP_ON_HOST_NETWORK_INTERFACE, self.set_ip_on_host_network_interface)

        http_server.register_async_uri(
            self.CHECK_INTERFACE_VLAN, self.check_interface_vlan)
        http_server.register_async_uri(
            self.GET_INTERFACE_VLAN, self.get_interface_vlan)
        http_server.register_async_uri(
            self.GET_INTERFACE_NAME, self.get_interface_name)
        http_server.register_async_uri(
            self.HOST_XFS_SCRAPE_PATH, self.get_xfs_frag_data)
        http_server.register_async_uri(self.HOST_SHUTDOWN, self.shutdown_host)
        http_server.register_async_uri(self.HOST_REBOOT, self.reboot_host)
        http_server.register_async_uri(self.GET_PCI_DEVICES, self.get_pci_info)
        http_server.register_async_uri(
            self.CREATE_PCI_DEVICE_ROM_FILE, self.create_pci_device_rom_file)
        http_server.register_async_uri(
            self.GENERATE_SRIOV_PCI_DEVICES, self.generate_sriov_pci_devices)
        http_server.register_async_uri(
            self.UNGENERATE_SRIOV_PCI_DEVICES, self.ungenerate_sriov_pci_devices)
        http_server.register_async_uri(
            self.GENERATE_VFIO_MDEV_DEVICES, self.generate_vfio_mdev_devices)
        http_server.register_async_uri(
            self.UNGENERATE_VFIO_MDEV_DEVICES, self.ungenerate_vfio_mdev_devices)
        http_server.register_async_uri(
            self.GET_MTTY_DEVICES, self.get_mtty_info)
        http_server.register_async_uri(
            self.GENERATE_SE_VFIO_MDEV_DEVICES, self.generate_se_vfio_mdev_devices)
        http_server.register_async_uri(
            self.UNGENERATE_SE_VFIO_MDEV_DEVICES, self.ungenerate_se_vfio_mdev_devices)
        http_server.register_async_uri(
            self.DELETE_VFIO_MDEV_DEVICE, self.delete_vfio_mdev_device)
        http_server.register_async_uri(
            self.HOST_UPDATE_SPICE_CHANNEL_CONFIG_PATH, self.update_spice_channel_config)
        http_server.register_async_uri(self.CANCEL_JOB, self.cancel)
        http_server.register_sync_uri(
            self.TRANSMIT_VM_OPERATION_TO_MN_PATH, self.transmit_vm_operation_to_vm)
        http_server.register_sync_uri(
            self.TRANSMIT_ZWATCH_INSTALL_RESULT_TO_MN_PATH, self.transmit_zwatch_install_result_to_mn)
        http_server.register_async_uri(
            self.SCAN_VM_PORT_PATH, self.scan_vm_port)
        http_server.register_async_uri(
            self.ENABLE_ZEROCOPY, self.enable_zerocopy)
        http_server.register_async_uri(
            self.DISABLE_ZEROCOPY, self.disable_zerocopy)
        http_server.register_async_uri(
            self.GET_DEV_CAPACITY, self.get_dev_capacity)
        http_server.register_async_uri(
            self.ADD_BRIDGE_FDB_ENTRY_PATH, self.add_bridge_fdb_entry)
        http_server.register_async_uri(
            self.DEL_BRIDGE_FDB_ENTRY_PATH, self.del_bridge_fdb_entry)
        http_server.register_async_uri(
            self.DEPLOY_COLO_QEMU_PATH, self.deploy_colo_qemu)
        http_server.register_async_uri(
            self.UPDATE_CONFIGURATION_PATH, self.update_host_configuration)
        http_server.register_async_uri(
            self.GET_NUMA_TOPOLOGY_PATH, self.get_numa_topology)
        http_server.register_async_uri(
            self.ATTACH_VOLUME_PATH, self.attach_volume_path)
        http_server.register_async_uri(
            self.DETACH_VOLUME_PATH, self.detach_volume__path)
        http_server.register_async_uri(
            self.UPDATE_VM_CONSOLE_PASSWORD_LIVE_PATH, self.update_vm_console_password_live)
        http_server.register_async_uri(
            self.SETUP_VM_HA_ENABLED_METADATA_LIVE_PATH, self.setup_vm_ha_enabled_metadata_live)
        http_server.register_async_uri(
            self.RECONCILE_VM_HA_ENABLED_METADATA_LIVE_PATH, self.reconcile_vm_ha_enabled_metadata_live)
        http_server.register_async_uri(
            self.GET_BLOCK_DEVICES_PATH, self.get_block_devices)

        self.heartbeat_timer = {}
        filepath = r'/etc/libvirt/qemu/networks/autostart/default.xml'
        if os.path.exists(filepath):
            os.unlink(filepath)

    def stop(self):
        if self.host_socket is not None:
            self.host_socket.close()

        pass

    def configure(self, config=None):
        if config is None:
            config = {}
        self.config = config
