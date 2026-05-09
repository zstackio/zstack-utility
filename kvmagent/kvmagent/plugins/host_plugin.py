'''

@author: frank
'''
import base64
import copy
import hashlib
import os
import os.path
import platform
import re
import tempfile
import time
import uuid
import string
import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

import yaml
import subprocess

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import http, lvm, ceph, form, pci, report, upload_task
from zstacklib.utils import qemu
from zstacklib.utils import linux
from zstacklib.utils import iptables
from zstacklib.utils import iproute
from zstacklib.utils import ebtables
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import pci
from zstacklib.utils import sizeunit
from zstacklib.utils import thread
from zstacklib.utils import xmlobject
from zstacklib.utils import ovs
from zstacklib.utils import shell
from zstacklib.utils.bash import *
from zstacklib.utils.file_downloader import FileDownloader
from zstacklib.utils.file_system_upload_task import FileSystemUploadTask
from zstacklib.utils.ip import get_nic_supported_max_speed
from zstacklib.utils.ip import get_nic_driver_type
from zstacklib.utils.ipmitool import get_sensor_info_from_ipmi
from zstacklib.utils.linux import filter_lines_by_str_list, is_virtual_machine
from zstacklib.utils.report import Report, get_timeout
import zstacklib.utils.ip as ip
from zstacklib.utils import netconfig
import zstacklib.utils.plugin as plugin
from kvmagent.plugins.prometheus import get_service_type_map, register_service_type
from zstacklib.utils.upload_task import UploadTasks, UploadHandler

try:
    import grpc
    from kvmagent.keyagent import key_agent_pb2
    from kvmagent.keyagent import key_agent_pb2_grpc
    KEY_AGENT_GRPC_AVAILABLE = True
except Exception:
    KEY_AGENT_GRPC_AVAILABLE = False

host_arch = platform.machine()
IS_AARCH64 = host_arch == 'aarch64'
IS_MIPS64EL = host_arch == 'mips64el'
IS_LOONGARCH64 = host_arch == 'loongarch64'
GRUB_ROCKY_ENVS = bash_o("find /boot -name grubenv").strip().split("\n")
GRUB_FILES = ["/boot/grub2/grub.cfg", "/boot/grub/grub.cfg", "/etc/grub2-efi.cfg", "/etc/grub-efi.cfg"] \
                + ["/boot/efi/EFI/{}/grub.cfg".format(platform.dist()[0])]
IPTABLES_CMD = iptables.get_iptables_cmd()
EBTABLES_CMD = ebtables.get_ebtables_cmd()

COLO_QEMU_KVM_VERSION = '/var/lib/zstack/colo/qemu_kvm_version'
COLO_LIB_PATH = '/var/lib/zstack/colo/'
HOST_TAKEOVER_FLAG_PATH = 'var/run/zstack/takeOver'
NODE_INFO_PATH = '/sys/devices/system/node/'
ISCSI_INITIATOR_NAME_PATH = '/etc/iscsi/initiatorname.iscsi'
HOST_NQN_PATH = '/etc/nvme/hostnqn'

KEY_AGENT_UNIX_SOCKET = 'unix:///var/run/key-agent/key-agent.sock'
KEY_AGENT_ERR_KEYS_NOT_ON_DISK = 'KEY_AGENT_KEYS_NOT_ON_DISK'
KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH = 'KEY_AGENT_KEY_FILES_INTEGRITY_MISMATCH'
KEY_AGENT_ERR_SECRET_NOT_FOUND = 'KEY_AGENT_SECRET_NOT_FOUND'

KEY_AGENT_SUPPORTED_SECRET_PURPOSES = ('vtpm', 'volume')


def is_valid_key_agent_secret_purpose(purpose):
    """True if purpose is in KEY_AGENT_SUPPORTED_SECRET_PURPOSES."""
    if not purpose:
        return False
    return purpose in KEY_AGENT_SUPPORTED_SECRET_PURPOSES


BOND_MODE_ACTIVE_0 = "balance-rr"
BOND_MODE_ACTIVE_1 = "active-backup"
BOND_MODE_ACTIVE_2 = "balance-xor"
BOND_MODE_ACTIVE_3 = "broadcast"
BOND_MODE_ACTIVE_4 = "802.3ad"
BOND_MODE_ACTIVE_5 = "balance-tlb"
BOND_MODE_ACTIVE_6 = "balance-alb"

DISTRO_USING_DNF = ['rl84', 'h84r', 'ky10sp1', 'ky10sp2', 'ky10sp3',
                    'oe2203sp1', 'h2203sp1o']


class ConnectResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ConnectResponse, self).__init__()

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
        self.libvirtVersion = None
        self.libvirtPackageVersion = None
        self.hvmCpuFlag = None
        self.cpuModelName = None
        self.systemSerialNumber = None
        self.eptFlag = None
        self.libvirtCapabilities = []
        self.virtualizerInfo = vm_plugin.VirtualizerInfoTO()
        self.iscsiInitiatorName = None
        self.nqn = None
        self.hostname = None
        self.cpuProcessorNum = 0
        self.cpuSockets = 0
        self.cpuCoresPerSocket = 0
        self.cpuThreadsPerCore = 0
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

class SetServiceTypeOnHostNetworkInterfaceRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(SetServiceTypeOnHostNetworkInterfaceRsp, self).__init__()

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

class HostPhysicalCpuStruct(object):
    def __init__(self):
        self.socketDesignation = ""
        self.version = ""
        self.serialNumber = ""
        self.currentSpeed = ""
        self.coreCount = ""
        self.threadCount = ""


class GetHostPhysicalMemoryFactsResponse(kvmagent.AgentResponse):
    physicalMemoryFacts = None  # type: list[HostPhysicalMemoryStruct]

    def __init__(self):
        super(GetHostPhysicalMemoryFactsResponse, self).__init__()
        self.physicalMemoryFacts = []


class GetHostPhysicalCpuFactsResponse(kvmagent.AgentResponse):
    physicalCpuFacts = None  # type: list[HostPhysicalCpuStruct]

    def __init__(self):
        super(GetHostPhysicalCpuFactsResponse, self).__init__()
        self.physicalCpuFacts = []


class UpdateHostNqnCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(UpdateHostNqnCmd, self).__init__()
        self.nqn = None

class UpdateHostNqnResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(UpdateHostNqnResponse, self).__init__()

class UpdateHostnameResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(UpdateHostnameResponse, self).__init__()

class UpdateHostIscsiInitiatorNameCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(UpdateHostIscsiInitiatorNameCmd, self).__init__()
        self.iscsiInitiatorName = None

class UpdateHostIscsiInitiatorNameResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(UpdateHostIscsiInitiatorNameResponse, self).__init__()


class SetHostKernelInterfaceCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SetHostKernelInterfaceCmd, self).__init__()
        self.interfaces = []  # type: list[HostKernelInterfaceTO]


class SetHostKernelInterfaceResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(SetHostKernelInterfaceResponse, self).__init__()


class GetHostKernelInterfaceCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetHostKernelInterfaceCmd, self).__init__()
        self.hostUuid = None
        self.targetIp = None


class GetHostKernelInterfaceResponse(kvmagent.AgentResponse):
    interfaces = None  # type: list[HostKernelInterfaceTO]

    def __init__(self):
        super(GetHostKernelInterfaceResponse, self).__init__()
        self.interfaces = None


class GetBlockDevicesResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetBlockDevicesResponse, self).__init__()
        self.blockDevices = []


class GetSensorsResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetSensorsResponse, self).__init__()
        self.sensors = []


class UsedIpTO(object):
    ACTION_CODE_ADD = 'add'
    ACTION_CODE_REMOVE = 'remove'

    def __init__(self, ipVersion=None, ip=None, netmask=None, gateway=None):
        super(UsedIpTO, self).__init__()
        self.ipVersion = ipVersion
        self.ip = ip
        self.netmask = netmask
        self.gateway = gateway
        self.actionCode = None


class HostKernelInterfaceTO(object):
    def __init__(self, interface_name=None, vlan_id=None, bridge_name=None):
        super(HostKernelInterfaceTO, self).__init__()
        self.interfaceName = interface_name
        self.vlanId = vlan_id
        self.bridgeName = bridge_name
        self.ips = []   # type: list[UsedIpTO]

class GetHostNetworkBongdingCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetHostNetworkBongdingCmd, self).__init__()
        self.managementServerIp = None


class GetHostBondingFactsCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetHostBondingFactsCmd, self).__init__()
        self.managementServerIp = None
        self.bondName = None


class GetHostNetworkBongdingResponse(kvmagent.AgentResponse):
    bondings = None  # type: list[HostNetworkBondingInventory]
    nics = None  # type: list[HostNetworkInterfaceInventory]

    def __init__(self):
        super(GetHostNetworkBongdingResponse, self).__init__()
        self.bondings = None
        self.nics = None


class GetHostBondingFactsResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetHostBondingFactsResponse, self).__init__()
        self.bonding = None


class HostNetworkBondingInventory(object):
    slaves = None  # type: list(HostNetworkInterfaceInventory)

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
        self.mode = linux.read_file("/sys/class/net/%s/bonding/mode" % self.bondingName).strip()
        self.xmitHashPolicy = linux.read_file("/sys/class/net/%s/bonding/xmit_hash_policy" % self.bondingName).strip()
        self.miiStatus = linux.read_file("/sys/class/net/%s/bonding/mii_status" % self.bondingName).strip()
        self.mac = linux.read_file("/sys/class/net/%s/address" % self.bondingName).strip()
        if len(bash_o("ip link show type bridge_slave %s" % self.bondingName).strip()) > 0:
            self.bondingType = "bridgeSlave"
        else:
            self.bondingType = "noBridge"
        self.callBackIp = managementServerIp
        if managementServerIp is not None:
            self.callBackIp = self._get_src_addr(managementServerIp)
        self.ipAddresses = ['%s/%d' % (x.address, x.prefixlen) for x in iproute.query_addresses(ifname=self.bondingName, ip_version=4)]
        if len(self.ipAddresses) == 0:
            master = linux.read_file("/sys/class/net/%s/master/ifindex" % self.bondingName)
            if master:
                self.ipAddresses = ['%s/%d' % (x.address, x.prefixlen)
                    for x in iproute.query_addresses(index=int(master.strip()), ip_version=4)]
        self.miimon = linux.read_file_strip("/sys/class/net/%s/bonding/miimon" % self.bondingName)
        self.allSlavesActive = linux.read_file_strip("/sys/class/net/%s/bonding/all_slaves_active" % self.bondingName) == "0"
        slave_info = linux.read_file_strip("/sys/class/net/%s/bonding/slaves" % self.bondingName)
        slave_names = slave_info.split() if slave_info else []
        if len(slave_names) == 0:
            return

        self.slaves = [None] * len(slave_names)
        threads = []
        for idx, name in enumerate(slave_names, start=0):
            threads.append(thread.ThreadFacade.run_in_thread(get_nic, [name.strip(), idx]))
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
        self.speed = get_nic_supported_max_speed(self.interfaceName)

        if not bondData.has_key('bond'):
            return

        if bondData['bond'].has_key('name'):
            self.bondingName = bondData['bond']['name']

        if bondData['bond'].has_key('mode'):
            if type(bondData['bond']['mode']) is int:
                self.mode = bondModeList[bondData['bond']['mode']]
            else:
                self.mode = bondData['bond']['mode']

        if bondData['bond'].has_key('policy'):
            self.xmitHashPolicy = bondPolicyMap[bondData['bond']['policy']]

        self.type = "OvsBonding"
        self.miiStatus = None
        self.mac = None
        self.ipAddresses = None
        self.miimon = None
        self.allSlavesActive = None

        if not bondData['bond'].has_key('slaves'):
            return

        self.slaves = [None] * len(bondData['bond']['slaves'])
        threads = []
        for idx, name in  enumerate(bondData['bond']['slaves'], start=0):
            threads.append(thread.ThreadFacade.run_in_thread(get_nic, [name.strip(), idx, self.bondingName]))
        for t in threads:
            t.join()

    def _to_dict(self):
        to_dict = self.__dict__
        for k in to_dict.keys():
            if k == "slaves":
                v = copy.deepcopy(to_dict[k])
                to_dict[k] = [i.__dict__ for i in v]
        return to_dict

    def _get_src_addr(self, ip_addr):
        output = subprocess.check_output(['ip', 'r', 'get', ip_addr]).decode('utf-8')

        pattern = r'src ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)'
        match = re.search(pattern, output)
        if match:
            src_addr = match.group(1)
            return src_addr
        else:
            return None

class HostNetworkInterfaceInventory(object):
    def init(self, name, master=None, managementServerIp=None):
        super(HostNetworkInterfaceInventory, self).__init__()
        self.interfaceName = name
        self.speed = None
        self.slaveActive = None
        self.carrierActive = None
        self.mac = None
        self.ipAddresses = None
        self.interfaceType = None
        self.master = master
        self.pciDeviceAddress = None
        self.offloadStatus = None
        self.callBackIp = None
        self.interfaceModel = None
        self.vendorId = None
        self.deviceId = None
        self.deviceName = None
        self.vendorName = None
        self.subvendorId = None
        self.subdeviceId = None
        self.subvendorName = None

        bonds = ovs.getAllBondFromFile()

        if bonds:
            for bond in bonds:
                if self.interfaceName in bond.slaves:
                    self.master = bond.name

        if self.master is not None:
            self._init_from_ovs()
        else:
            self._init_from_name(managementServerIp)
        self.driverType = None

    def __new__(cls, name, master=None, managementServerIp=None, *args, **kwargs):
        o = super(HostNetworkInterfaceInventory, cls).__new__(cls)
        o.init(name, master, managementServerIp)
        return o

    def _updateActiveState(self):
        if self.interfaceType == "bondingSlave":
            activeSlave = linux.read_file("/sys/class/net/%s/bonding/active_slave" % self.master)
            self.slaveActive = self.interfaceName in activeSlave if activeSlave is not None else None

    @in_bash
    def _init_from_name(self, managementServerIp):
        if self.interfaceName is None:
            return
        self.speed = get_nic_supported_max_speed(self.interfaceName)
        # cannot read carrier of vf nic
        if not os.path.exists("/sys/class/net/%s/device/physfn" % self.interfaceName):
            carrier = linux.read_file("/sys/class/net/%s/carrier" % self.interfaceName)
            if carrier:
                self.carrierActive = carrier.strip() == "1"

        self.mac = linux.read_file_strip("/sys/class/net/%s/address" % self.interfaceName)
        self.ipAddresses = linux.get_interface_ip_addresses(self.interfaceName)
        self.callBackIp = managementServerIp
        if managementServerIp is not None:
            self.callBackIp = self._get_src_addr(managementServerIp)

        self.master = linux.get_interface_master_device(self.interfaceName)
        if self.master is not None:
            self.master = self.master.strip()

        if len(self.ipAddresses) == 0:
            if self.master:
                self.ipAddresses = linux.get_interface_ip_addresses(self.master)
        if self.master is None:
            self.interfaceType = "noMaster"
        elif len(bash_o("ip link show type bond_slave %s" % self.interfaceName).strip()) > 0:
            self.interfaceType = "bondingSlave"
            activeSlave = linux.read_file("/sys/class/net/%s/bonding/active_slave" % self.master)
            self.slaveActive = self.interfaceName in activeSlave if activeSlave is not None else None
        else:
            self.interfaceType = "bridgeSlave"

        self.pciDeviceAddress = os.readlink("/sys/class/net/%s/device" % self.interfaceName).strip().split('/')[-1]

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
        if not os.path.exists("/sys/class/net/%s/device/physfn" % self.interfaceName):
            carrier = linux.read_file("/sys/class/net/%s/carrier" % self.interfaceName)
            if carrier:
                self.carrierActive = carrier.strip() == "1"
        self.mac = linux.read_file("/sys/class/net/%s/address" % self.interfaceName).strip()
        self.ipAddresses = linux.get_interface_ip_addresses(self.interfaceName)
        self.interfaceType = "bondingSlave"

        # TODO: check dpdk slave status
        # self.slaveActive = ovs.getOvsCtl(with_dpdk=True).checkDpdkSlaveStatus(self.interfaceName)
        self.pciDeviceAddress = os.readlink("/sys/class/net/%s/device" % self.interfaceName).strip().split('/')[-1]
        self.offloadStatus = ovs.getOffloadStatus(self.interfaceName)
        self._init_interfacemodel()

    @in_bash
    def _init_interfacemodel(self):
        pci_list = pci.lspci_s(self.pciDeviceAddress) # type: list[dict]
        if pci_list == None or len(pci_list) == 0:
            logger.warn('failed to init interfacemodel: pci device %s not found' % self.pciDeviceAddress)
            return

        pci_info = pci_list[0]
        if pci_info.has_key('Vendor'):
            self.vendorName = self._simplify_device_name(pci_info['Vendor'])
            self.vendorId = pci_info['VendorId']
        if pci_info.has_key('Device'):
            self.deviceName = self._simplify_device_name(pci_info['Device'])
            self.deviceId = pci_info['DeviceId']
        if pci_info.has_key('SVendor'):
            self.subvendorName = self._simplify_device_name(pci_info['SVendor'])
            self.subvendorId = pci_info['SVendorId']
        if pci_info.has_key('SDevice'):
            self.subvendorId = pci_info['SDeviceId']
        self.interfaceModel = "%s_%s" % (self.subvendorName if self.subvendorName and "Unknown" not in self.subvendorName else self.vendorName, self.deviceName)

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
        output = subprocess.check_output(['ip', 'r', 'get', ip_addr]).decode('utf-8')

        pattern = r'src ([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)'
        match = re.search(pattern, output)
        if match:
            src_addr = match.group(1)
            return src_addr
        else:
            return None

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

class GetPciDevicesResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetPciDevicesResponse, self).__init__()
        self.pciDevicesInfo = []
        self.hostIommuStatus = False

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
        super(kvmagent.AgentResponse, self).__init__()

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

class DownloadFileRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(DownloadFileRsp, self).__init__()
        self.md5sum = None
        self.size = None

class UploadFileRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(UploadFileRsp, self).__init__()
        self.directUploadUrl = None

class UploadProgressRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(UploadProgressRsp, self).__init__()
        self.apiId = None
        self.completed = False
        self.progress = 0
        self.size = 0
        self.actualSize = 0
        self.installPath = None
        self.lastOpTime = 0
        self.downloadSize = 0
        self.md5sum = None
        self.supportSuspend = False

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
        self.virtStatus = ""
        self.maxPartNum = "0"
        self.ramSize = ""
        self.mdevSpecifications = []
        self.rev = ""
        self.addonInfo = {}

class MttyDeviceTO(object):
    def __init__(self):
        self.name = ""
        self.description = ""
        self.type = ""
        self.virtStatus = ""

# moved from vm_plugin to host_plugin
class UpdateConfigration(object):
    def __init__(self):
        self.path = None
        self.enableIommu = None
        self.iommu_type = 'amd_iommu' if 'hygon' in linux.get_cpu_model()[1].lower() or 'amd' in linux.get_cpu_model()[1].lower() else 'intel_iommu'

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

        r_on, o_on, e_on = self.executeCmdOnFile("grep -E '{}(\ )*=(\ )*on'".format(self.iommu_type))
        r_off, o_off, e_off = self.executeCmdOnFile("grep -E '{}(\ )*=(\ )*off'".format(self.iommu_type))
        r_modprobe_blacklist, o_modprobe_blacklist, e_modprobe_blacklist = self.executeCmdOnFile("grep -E 'modprobe.blacklist(\ )*='")
        #When iommu has not changed,  No need to update /etc/default/grub
        if self.enableIommu is False:
            if r_on != 0 and r_off != 0 and r_modprobe_blacklist != 0:
                return True, None
        elif self.enableIommu is True:
            if r_on ==0 and r_off != 0 and r_modprobe_blacklist == 0:
                return True,None

        if r_on == 0:
            r, o, e = self.executeCmdOnFile( "sed -i '/GRUB_CMDLINE_LINUX/s/[[:blank:]]*{}[[:blank:]]*=[[:blank:]]*on//g'".format(self.iommu_type))
            if r != 0:
                return False, "%s %s" % (e, o)
        if r_off == 0:
            r, o, e = self.executeCmdOnFile("sed -i '/GRUB_CMDLINE_LINUX/s/[[:blank:]]*{}[[:blank:]]*=[[:blank:]]*off//g'".format(self.iommu_type))
            if r != 0:
                return False, "%s %s" % (e, o)
        if r_modprobe_blacklist == 0:
            r, o, e = self.executeCmdOnFile("grep -E '[[:blank:]]*modprobe.blacklist[[:blank:]]*=[[:blank:]]*[[:graph:]]*\"$'")
            if r == 0:
                r, o, e = self.executeCmdOnFile("sed -i '/GRUB_CMDLINE_LINUX/s/[[:blank:]]*modprobe.blacklist[[:blank:]]*=[[:blank:]]*[[:graph:]]*\"$/\"/g'")
                if r != 0:
                    return False, "%s %s" % (e, o)
            else:
                r, o, e = self.executeCmdOnFile("sed -i '/GRUB_CMDLINE_LINUX/s/[[:blank:]]*modprobe.blacklist[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g'")
                if r != 0:
                    return False, "%s %s" % (e, o)

        if self.enableIommu is True:
            r, o, e = self.executeCmdOnFile("sed -i '/GRUB_CMDLINE_LINUX/s/\"$/ {}=on modprobe.blacklist=snd_hda_intel,amd76x_edac,vga16fb,nouveau,rivafb,nvidiafb,rivatv,amdgpu,radeon\"/g'".format(self.iommu_type))
            if r != 0:
                return False, "%s %s" % (e, o)

        return True, None

    def updateGrubConfig(self):
        def updateGrubContent(content):
            content = re.sub('{0}\s*=\s*on'.format(self.iommu_type), '', content)
            content = re.sub('{0}\s*=\s*off'.format(self.iommu_type), '', content)
            content = re.sub('\s*modprobe.blacklist\s*=\s*\S*', '', content)
            return content

        for grub_path in GRUB_FILES:
            if os.path.exists(grub_path):
                content = updateGrubContent(linux.read_file(grub_path))
                if self.enableIommu:
                    content = re.sub(r'(/vmlinuz-.*)',
                                     r'\1 {0}=on modprobe.blacklist=snd_hda_intel,amd76x_edac,vga16fb,nouveau,rivafb,nvidiafb,rivatv,amdgpu,radeon'.format(
                                         self.iommu_type), content)
                linux.write_file(grub_path, content)
        for grub_rocky_env in GRUB_ROCKY_ENVS:
            if os.path.exists(grub_rocky_env) and self.enableIommu:
                env = updateGrubContent(linux.read_file(grub_rocky_env))
                env = re.sub(r'(kernelopts=.*)',
                             r'\1 {0}=on modprobe.blacklist=snd_hda_intel,amd76x_edac,vga16fb,nouveau,rivafb,nvidiafb,rivatv,amdgpu,radeon'.format(
                                 self.iommu_type), env)
                linux.write_file(grub_rocky_env, env)
        bash_o("modprobe vfio && modprobe vfio-pci")

logger = log.get_logger(__name__)

def _get_memory(word):
    out = shell.call("grep '%s' /proc/meminfo" % word)
    (name, capacity) = out.split(':')
    capacity = re.sub('[k|K][b|B]', '', capacity).strip()
    #capacity = capacity.rstrip('kB').rstrip('KB').rstrip('kb').strip()
    return sizeunit.KiloByte.toByte(long(capacity))

def _get_total_memory():
    return _get_memory('MemTotal')

def _get_free_memory():
    return _get_memory('MemFree')

def _get_used_memory():
    return _get_total_memory() - _get_free_memory()


@linux.ignoreerror
def _update_global_variables_for_net_config():
    if not os.path.exists('/usr/local/bin/zsha2'):
        return

    r, o = bash_ro("/usr/local/bin/zsha2 show-config")
    if r == 0:
        zsha2_config_info = jsonobject.loads(o)
        netconfig.save_zsha2_vip(zsha2_config_info.dbvip)


class HostPlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''

    CONNECT_PATH = '/host/connect'
    CAPACITY_PATH = '/host/capacity'
    ECHO_PATH = '/host/echo'
    FACT_PATH = '/host/fact'
    PING_PATH = "/host/ping"
    CREATE_ENVELOPE_KEY_PATH = '/host/key/envelope/createEnvelopeKey'
    ROTATE_ENVELOPE_KEY_PATH = '/host/key/envelope/rotateEnvelopeKey'
    GET_ENVELOPE_PUBLIC_KEY_PATH = '/host/key/envelope/getEnvelopePublicKey'
    CHECK_ENVELOPE_KEY_PATH = '/host/key/envelope/checkEnvelopeKey'
    ENSURE_SECRET_PATH = '/host/key/envelope/ensureSecret'
    WRITE_SECRET_MATERIAL_FILE_PATH = '/host/key/envelope/writeSecretMaterialFile'
    GET_SECRET_PATH = '/host/key/envelope/getSecret'
    DELETE_SECRET_PATH = '/host/key/envelope/deleteSecret'
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
    LOCATE_HOST_NETWORK_INTERFACE = "/host/locate/networkinterface";
    GET_HOST_PHYSICAL_MEMORY_FACTS = "/host/physicalmemoryfacts";
    GET_HOST_PHYSICAL_CPU_FACTS = "/host/physicalcpufacts";
    UPDATE_HOST_OVS_CPU_PINNING = "/host/ovs/cpu-pin/update"
    CHANGE_PASSWORD = "/host/changepassword"
    GET_HOST_NETWORK_FACTS = "/host/networkfacts"
    GET_HOST_BONDING_FACTS = "/host/networkfacts/bonding"
    SET_IP_ON_HOST_NETWORK_INTERFACE = "/host/setip/networkinterface"
    CHECK_INTERFACE_VLAN = "/host/checkvlan/networkinterface"
    GET_INTERFACE_VLAN = "/host/getvlan/networkinterface"
    GET_INTERFACE_NAME = "/host/getname/networkinterface"
    SET_SERVICE_TYPE_ON_HOST_NETWORK_INTERFACE = "/host/setservicetype/networkinterface"
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
    HOST_UPDATE_SPICE_CHANNEL_CONFIG_PATH = "/host/updateSpiceChannelConfig";
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
    GET_KERNEL_INTERFACE_PATH = "/host/kernelinterface/get"
    SET_KERNEL_INTERFACE_PATH = "/host/kernelinterface/set"
    GET_BLOCK_DEVICES_PATH = "/host/blockdevices/get"
    GET_SENSORS_PATH = "/host/sensors/get"
    UPDATE_NQN_PATH = "/host/nqn/update"
    UPDATE_HOSTNAME_PATH = "/host/hostname/update"

    UPDATE_ISCSI_INITIATOR_NAME_PATH = "/host/iscsiinitiatorname/update"
    KVM_HOST_FILE_DOWNLOAD_PATH = "/host/file/download"
    FILE_UPLOAD_PATH = "/host/file/upload"
    FILE_DIRECT_UPLOAD_PATH = "/host/file/direct/upload"
    FILE_UPLOAD_PROGRESS_PATH = "/host/file/progress"

    def __init__(self):
        self.IS_YUM = False
        self.IS_APT = False
        self.NVIDIA_SMI_INSTALLED = False

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

    def _create_key_via_key_agent(self):
        if not KEY_AGENT_GRPC_AVAILABLE:
            return (False, None, None)
        try:
            if not os.path.exists('/var/run/key-agent/key-agent.sock'):
                logger.debug('key-agent unix socket not found, skip create key')
                return (False, None, None)
            channel = grpc.insecure_channel(KEY_AGENT_UNIX_SOCKET)
            try:
                stub = key_agent_pb2_grpc.KeyAgentServiceStub(channel)
                req = key_agent_pb2.CreateEnvelopeKeyRequest()
                stub.CreateEnvelopeKey(req, timeout=5)
                return (True, None, None)
            finally:
                channel.close()
        except grpc.RpcError as e:
            details = e.details() if hasattr(e, 'details') and callable(getattr(e, 'details')) else str(e)
            logger.debug('key-agent CreateEnvelopeKey gRPC error: %s' % details)
            if KEY_AGENT_ERR_KEYS_NOT_ON_DISK in details:
                return (False, KEY_AGENT_ERR_KEYS_NOT_ON_DISK, details)
            if KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH in details:
                return (False, KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH, details)
            return (False, None, details or str(e))
        except Exception as e:
            logger.debug('key-agent CreateEnvelopeKey failed: %s' % e)
            return (False, None, None)

    def _rotate_key_via_key_agent(self):
        if not KEY_AGENT_GRPC_AVAILABLE:
            return (False, None, None)
        try:
            if not os.path.exists('/var/run/key-agent/key-agent.sock'):
                logger.debug('key-agent unix socket not found, skip rotate key')
                return (False, None, None)
            channel = grpc.insecure_channel(KEY_AGENT_UNIX_SOCKET)
            try:
                stub = key_agent_pb2_grpc.KeyAgentServiceStub(channel)
                req = key_agent_pb2.RotateEnvelopeKeyRequest()
                stub.RotateEnvelopeKey(req, timeout=5)
                return (True, None, None)
            finally:
                channel.close()
        except grpc.RpcError as e:
            details = e.details() if hasattr(e, 'details') and callable(getattr(e, 'details')) else str(e)
            logger.debug('key-agent RotateEnvelopeKey gRPC error: %s' % details)
            if KEY_AGENT_ERR_KEYS_NOT_ON_DISK in details:
                return (False, KEY_AGENT_ERR_KEYS_NOT_ON_DISK, details)
            if KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH in details:
                return (False, KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH, details)
            return (False, None, details or str(e))
        except Exception as e:
            logger.debug('key-agent RotateKey failed: %s' % e)
            return (False, None, None)

    def _get_public_key_from_key_agent(self):
        if not KEY_AGENT_GRPC_AVAILABLE:
            return (None, None, None)
        try:
            if not os.path.exists('/var/run/key-agent/key-agent.sock'):
                logger.debug('key-agent unix socket not found, skip get public key')
                return (None, None, None)
            channel = grpc.insecure_channel(KEY_AGENT_UNIX_SOCKET)
            try:
                stub = key_agent_pb2_grpc.KeyAgentServiceStub(channel)
                req = key_agent_pb2.GetPublicKeyRequest()
                resp = stub.GetPublicKey(req, timeout=5)
                if resp and getattr(resp, 'public_key', None):
                    pk = resp.public_key
                    if isinstance(pk, bytes):
                        pk = base64.b64encode(pk).decode('ascii')
                    return (pk, None, None)
                return (None, None, None)
            finally:
                channel.close()
        except grpc.RpcError as e:
            details = e.details() if hasattr(e, 'details') and callable(getattr(e, 'details')) else str(e)
            logger.debug('key-agent GetPublicKey gRPC error: %s' % details)
            if KEY_AGENT_ERR_KEYS_NOT_ON_DISK in details:
                return (None, KEY_AGENT_ERR_KEYS_NOT_ON_DISK, details)
            if KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH in details:
                return (None, KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH, details)
            return (None, None, details or str(e))
        except Exception as e:
            logger.debug('key-agent GetPublicKey failed: %s' % e)
            return (None, None, None)

    def _check_envelope_key_via_key_agent(self):
        if not KEY_AGENT_GRPC_AVAILABLE:
            return (False, None, None)
        try:
            if not os.path.exists('/var/run/key-agent/key-agent.sock'):
                logger.debug('key-agent unix socket not found, skip check envelope key')
                return (False, None, None)
            channel = grpc.insecure_channel(KEY_AGENT_UNIX_SOCKET)
            try:
                stub = key_agent_pb2_grpc.KeyAgentServiceStub(channel)
                req = key_agent_pb2.CheckEnvelopeKeyRequest()
                stub.CheckEnvelopeKey(req, timeout=5)
                return (True, None, None)
            finally:
                channel.close()
        except grpc.RpcError as e:
            details = e.details() if hasattr(e, 'details') and callable(getattr(e, 'details')) else str(e)
            logger.debug('key-agent CheckEnvelopeKey gRPC error: %s' % details)
            if KEY_AGENT_ERR_KEYS_NOT_ON_DISK in details:
                return (False, KEY_AGENT_ERR_KEYS_NOT_ON_DISK, details)
            if KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH in details:
                return (False, KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH, details)
            return (False, None, details or str(e))
        except Exception as e:
            logger.debug('key-agent CheckEnvelopeKey failed: %s' % e)
            return (False, None, None)

    def _ensure_secret_via_key_agent(self, encrypted_dek, vm_uuid, purpose, key_version, description=None, usage_instance='', secret_uuid=''):
        if not KEY_AGENT_GRPC_AVAILABLE:
            return (None, None, 'key_agent grpc not available')
        try:
            if not os.path.exists('/var/run/key-agent/key-agent.sock'):
                logger.debug('key-agent unix socket not found, skip ensure secret')
                return (None, None, 'key-agent socket not found')
            channel = grpc.insecure_channel(KEY_AGENT_UNIX_SOCKET)
            try:
                stub = key_agent_pb2_grpc.KeyAgentServiceStub(channel)
                req = key_agent_pb2.EnsureSecretRequest(
                    encrypted_dek=encrypted_dek,
                    description=description or '',
                    vm_uuid=vm_uuid,
                    purpose=purpose,
                    key_version=int(key_version),
                    usage_instance=usage_instance or '',
                )
                if secret_uuid and hasattr(req, 'secret_uuid'):
                    req.secret_uuid = secret_uuid
                resp = stub.EnsureSecret(req, timeout=5)
                if resp and getattr(resp, 'secret_uuid', None):
                    return (resp.secret_uuid, None, None)
                return (None, None, 'key-agent EnsureSecret returned no secret_uuid')
            finally:
                channel.close()
        except grpc.RpcError as e:
            details = e.details() if hasattr(e, 'details') and callable(getattr(e, 'details')) else str(e)
            logger.debug('key-agent EnsureSecret gRPC error: %s' % details)
            if KEY_AGENT_ERR_KEYS_NOT_ON_DISK in details:
                return (None, KEY_AGENT_ERR_KEYS_NOT_ON_DISK, details)
            if KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH in details:
                return (None, KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH, details)
            return (None, None, details or str(e))
        except Exception as e:
            logger.debug('key-agent EnsureSecret failed: %s' % e)
            return (None, None, str(e))

    def _prepare_luks_secret_material_channel(self, encrypted_dek):
        if not KEY_AGENT_GRPC_AVAILABLE:
            return (None, None, 'key_agent grpc not available')
        if not encrypted_dek:
            return (None, None, 'encrypted_dek is required')
        try:
            if not os.path.exists('/var/run/key-agent/key-agent.sock'):
                logger.debug('key-agent unix socket not found, skip PrepareLuksSecretMaterialChannel')
                return (None, None, 'key-agent socket not found')
            channel = grpc.insecure_channel(KEY_AGENT_UNIX_SOCKET)
            try:
                stub = key_agent_pb2_grpc.KeyAgentServiceStub(channel)
                req = key_agent_pb2.PrepareLuksSecretMaterialChannelRequest(encrypted_dek=encrypted_dek)
                resp = stub.PrepareLuksSecretMaterialChannel(req, timeout=60)
                path = getattr(resp, 'channel_path', None) if resp else None
                path = str(path).strip() if path else ''
                if path:
                    return (path, None, None)
                return (None, None, 'key-agent PrepareLuksSecretMaterialChannel returned empty channel_path')
            finally:
                channel.close()
        except grpc.RpcError as e:
            details = e.details() if hasattr(e, 'details') and callable(getattr(e, 'details')) else str(e)
            logger.debug('key-agent PrepareLuksSecretMaterialChannel gRPC error: %s' % details)
            if KEY_AGENT_ERR_KEYS_NOT_ON_DISK in details:
                return (None, KEY_AGENT_ERR_KEYS_NOT_ON_DISK, details)
            if KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH in details:
                return (None, KEY_AGENT_ERR_KEY_FILES_INTEGRITY_MISMATCH, details)
            return (None, None, details or str(e))
        except Exception as e:
            logger.debug('key-agent PrepareLuksSecretMaterialChannel failed: %s' % e)
            return (None, None, str(e))

    def _get_secret_via_key_agent(self, vm_uuid, key_version, purpose, usage_instance=''):
        if not KEY_AGENT_GRPC_AVAILABLE:
            return (None, None, 'key_agent grpc not available')
        try:
            if not os.path.exists('/var/run/key-agent/key-agent.sock'):
                logger.debug('key-agent unix socket not found, skip get secret')
                return (None, None, 'key-agent socket not found')
            channel = grpc.insecure_channel(KEY_AGENT_UNIX_SOCKET)
            try:
                stub = key_agent_pb2_grpc.KeyAgentServiceStub(channel)
                req = key_agent_pb2.GetSecretRequest(
                    vm_uuid=str(vm_uuid),
                    key_version=int(key_version),
                    purpose=purpose,
                    usage_instance=usage_instance or '',
                )
                resp = stub.GetSecret(req, timeout=5)
                if resp and getattr(resp, 'secret_uuid', None):
                    return (resp.secret_uuid, None, None)
                return (None, None, 'key-agent GetSecret returned no secret_uuid')
            finally:
                channel.close()
        except grpc.RpcError as e:
            details = e.details() if hasattr(e, 'details') and callable(getattr(e, 'details')) else str(e)
            logger.debug('key-agent GetSecret gRPC error: %s' % details)
            if e.code() == grpc.StatusCode.NOT_FOUND or KEY_AGENT_ERR_SECRET_NOT_FOUND in details:
                return (None, KEY_AGENT_ERR_SECRET_NOT_FOUND, details or 'secret not found')
            return (None, None, details or str(e))
        except Exception as e:
            logger.debug('key-agent GetSecret failed: %s' % e)
            return (None, None, str(e))

    def _delete_secret_via_key_agent(self, vm_uuid, key_version, purpose, usage_instance=''):
        if not KEY_AGENT_GRPC_AVAILABLE:
            return (False, None, 'key_agent grpc not available')
        try:
            if not os.path.exists('/var/run/key-agent/key-agent.sock'):
                logger.debug('key-agent unix socket not found, skip delete secret')
                return (False, None, 'key-agent socket not found')
            channel = grpc.insecure_channel(KEY_AGENT_UNIX_SOCKET)
            try:
                stub = key_agent_pb2_grpc.KeyAgentServiceStub(channel)
                req = key_agent_pb2.DeleteSecretRequest(
                    vm_uuid=str(vm_uuid),
                    key_version=int(key_version),
                    purpose=purpose,
                    usage_instance=usage_instance or '',
                )
                stub.DeleteSecret(req, timeout=5)
                return (True, None, None)
            finally:
                channel.close()
        except grpc.RpcError as e:
            details = e.details() if hasattr(e, 'details') and callable(getattr(e, 'details')) else str(e)
            if e.code() == grpc.StatusCode.NOT_FOUND or KEY_AGENT_ERR_SECRET_NOT_FOUND in details:
                logger.debug('key-agent DeleteSecret: not found, idempotent success (%s)' % details)
                return (True, None, None)
            logger.debug('key-agent DeleteSecret gRPC error: %s' % details)
            return (False, None, details or str(e))
        except Exception as e:
            logger.debug('key-agent DeleteSecret failed: %s' % e)
            return (False, None, str(e))

    @kvmagent.replyerror
    def connect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ConnectResponse()

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
        logger.debug(http.path_msg(self.CONNECT_PATH, 'host[uuid: %s] connected' % cmd.hostUuid))
        rsp.libvirtVersion = self.libvirt_version
        rsp.qemuVersion = self.qemu_version

        # create udev rule
        self.handle_usb_device_events()

        ignore_msrs = "1" if cmd.ignoreMsrs else "0"
        linux.write_file('/sys/module/kvm/parameters/ignore_msrs', ignore_msrs)

        linux.write_uuids("host", "host=%s" % self.host_uuid)

        vm_plugin.cleanup_stale_vnc_iptable_chains()
        self.apply_iptables_rules(cmd.iptablesRules)

        if self.host_socket is not None:
            self.host_socket.close()

        try:
            self.host_socket = socket.socket()
        except socket.error as e:
            self.host_socket = None

        ip_address = cmd.sendCommandUrl.split('/')[2].split(':')[0]
        try:
            self.host_socket.connect((ip_address, cmd.tcpServerPort))

        except socket.error as msg:
            self.host_socket.close()
            self.host_socket = None

        self.start_write_to_server()

        # remove old rules for vf nic
        bash_r(EBTABLES_CMD + ' -D FORWARD -j ZSTACK-VF-NICS')
        bash_r(EBTABLES_CMD + ' -X ZSTACK-VF-NICS')

        return jsonobject.dumps(rsp)

    @thread.AsyncThread
    def start_write_to_server(self):
        pkt_counter = 0
        while True:
            try:
                self.host_socket.send(str(pkt_counter))
            except Exception as e:
                logger.debug("failed to send pkg to mn")
                break

            if pkt_counter == sys.maxint:
                pkt_counter = 0

            pkt_counter += 1
            time.sleep(2)


    @kvmagent.replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        if cmd.configs:
            kvmagent.configs = cmd.configs.__dict__
        rsp = PingResponse()
        rsp.hostUuid = self.host_uuid
        rsp.sendCommandUrl = self.config.get(kvmagent.SEND_COMMAND_URL)
        rsp.version = self.config.get(kvmagent.VERSION)
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
                    rsp.existPaths[file_path] = hashlib.md5(data.read()).hexdigest()
                except IOError as err:
                    logger.debug('can not open file %s because IOError: %s' % (file_path, str(err)))
                    pass
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def create_envelope_key(self, req):
        rsp = kvmagent.AgentResponse()
        if not KEY_AGENT_GRPC_AVAILABLE:
            rsp.success = False
            rsp.error = 'key_agent grpc not available'
            return jsonobject.dumps(rsp)
        success, err_code, err_msg = self._create_key_via_key_agent()
        if err_code:
            rsp.success = False
            rsp.errorCode = err_code
            rsp.error = err_msg or err_code
            return jsonobject.dumps(rsp)
        if success:
            rsp.success = True
        else:
            rsp.success = False
            rsp.error = 'key-agent CreateEnvelopeKey failed or key-agent not running'
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def rotate_envelope_key(self, req):
        rsp = kvmagent.AgentResponse()
        if not KEY_AGENT_GRPC_AVAILABLE:
            rsp.success = False
            rsp.error = 'key_agent grpc not available'
            return jsonobject.dumps(rsp)
        success, err_code, err_msg = self._rotate_key_via_key_agent()
        if err_code:
            rsp.success = False
            rsp.errorCode = err_code
            rsp.error = err_msg or err_code
            return jsonobject.dumps(rsp)
        if success:
            rsp.success = True
        else:
            rsp.success = False
            rsp.error = 'key-agent RotateKey failed or key-agent not running'
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_envelope_public_key(self, req):
        rsp = kvmagent.AgentResponse()
        if not KEY_AGENT_GRPC_AVAILABLE:
            rsp.success = False
            rsp.error = 'key_agent grpc not available'
            return jsonobject.dumps(rsp)
        public_key, err_code, err_msg = self._get_public_key_from_key_agent()
        if err_code:
            rsp.success = False
            rsp.errorCode = err_code
            rsp.error = err_msg or err_code
            return jsonobject.dumps(rsp)
        if public_key is not None:
            rsp.success = True
            rsp.publicKey = public_key
        else:
            rsp.success = False
            rsp.error = 'key-agent GetPublicKey failed or no public key'
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_envelope_key(self, req):
        rsp = kvmagent.AgentResponse()
        if not KEY_AGENT_GRPC_AVAILABLE:
            rsp.success = False
            rsp.error = 'key_agent grpc not available'
            return jsonobject.dumps(rsp)
        ok, err_code, err_msg = self._check_envelope_key_via_key_agent()
        if err_code:
            rsp.success = False
            rsp.errorCode = err_code
            rsp.error = err_msg or err_code
            return jsonobject.dumps(rsp)
        if ok:
            rsp.success = True
        else:
            rsp.success = False
            rsp.error = err_msg or 'key-agent CheckEnvelopeKey failed or key-agent not running'
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def ensure_secret(self, req):
        rsp = kvmagent.AgentResponse()
        if not KEY_AGENT_GRPC_AVAILABLE:
            rsp.success = False
            rsp.error = 'key_agent grpc not available'
            return jsonobject.dumps(rsp)
        try:
            cmd = jsonobject.loads(req[http.REQUEST_BODY])
        except Exception as e:
            rsp.success = False
            rsp.error = 'invalid request body: %s' % e
            return jsonobject.dumps(rsp)
        encrypted_dek_b64 = getattr(cmd, 'encryptedDek', None)
        vm_uuid = getattr(cmd, 'vmUuid', None)
        purpose = getattr(cmd, 'purpose', None)
        key_version = getattr(cmd, 'keyVersion', None)
        description = getattr(cmd, 'description', None) or ''
        usage_instance = str(getattr(cmd, 'usageInstance', '') or '').strip()
        secret_uuid = str(getattr(cmd, 'secretUuid', '') or '').strip()
        if not is_valid_key_agent_secret_purpose(purpose):
            rsp.success = False
            rsp.error = 'unsupported purpose: %s (supported: %s)' % (purpose, ','.join(KEY_AGENT_SUPPORTED_SECRET_PURPOSES))
            return jsonobject.dumps(rsp)
        if not encrypted_dek_b64 or not vm_uuid or not purpose or key_version is None or not usage_instance:
            rsp.success = False
            rsp.error = 'missing encryptedDek, vmUuid, purpose, keyVersion or usageInstance (non-empty)'
            return jsonobject.dumps(rsp)
        if type(key_version) is not int or key_version < 0:
            rsp.success = False
            rsp.error = 'invalid keyVersion (must be non-negative int)'
            return jsonobject.dumps(rsp)
        normalized_b64 = encrypted_dek_b64.strip()
        vm_uuid = str(vm_uuid)
        purpose = str(purpose)
        if secret_uuid:
            try:
                uuid.UUID(secret_uuid)
            except Exception:
                rsp.success = False
                rsp.error = 'invalid secretUuid (must be UUID format)'
                return jsonobject.dumps(rsp)
        if not re.match(r'^[A-Za-z0-9+/]+={0,2}$', normalized_b64) or len(normalized_b64) % 4 != 0:
            rsp.success = False
            rsp.error = 'encryptedDek must be valid base64'
            return jsonobject.dumps(rsp)
        try:
            encrypted_dek = base64.b64decode(normalized_b64)
            enc_again = base64.b64encode(encrypted_dek)
            if not isinstance(enc_again, str):
                enc_again = enc_again.decode('ascii')
            if enc_again.rstrip('=') != normalized_b64.rstrip('='):
                raise ValueError('non-canonical base64 input')
        except Exception as e:
            rsp.success = False
            rsp.error = 'encryptedDek must be base64: %s' % e
            return jsonobject.dumps(rsp)
        secret_uuid, err_code, err_msg = self._ensure_secret_via_key_agent(
            encrypted_dek, vm_uuid, purpose, key_version, description, usage_instance, secret_uuid,
        )
        if secret_uuid:
            rsp.success = True
            rsp.secretUuid = secret_uuid
        else:
            rsp.success = False
            if err_code:
                rsp.errorCode = err_code
                rsp.error = err_msg or err_code
            else:
                rsp.error = err_msg or 'key-agent EnsureSecret failed or no secret_uuid'
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def write_secret_material_file(self, req):
        """
        MN → kvmagent: HPKE-sealed encryptedDek (base64); kvmagent → key-agent PrepareLuksSecretMaterialChannel.
        Response secFilePath is a FIFO under /tmp for qemu-img --object secret,...,file= (MN filePath on cmd is ignored).
        """
        rsp = kvmagent.AgentResponse()
        if not KEY_AGENT_GRPC_AVAILABLE:
            rsp.success = False
            rsp.error = 'key_agent grpc not available'
            return jsonobject.dumps(rsp)
        try:
            cmd = jsonobject.loads(req[http.REQUEST_BODY])
        except Exception as e:
            rsp.success = False
            rsp.error = 'invalid request body: %s' % e
            return jsonobject.dumps(rsp)
        encrypted_dek_b64 = getattr(cmd, 'encryptedDek', None)
        if not encrypted_dek_b64:
            rsp.success = False
            rsp.error = 'missing encryptedDek (non-empty)'
            return jsonobject.dumps(rsp)
        normalized_b64 = encrypted_dek_b64.strip()
        if not re.match(r'^[A-Za-z0-9+/]+={0,2}$', normalized_b64) or len(normalized_b64) % 4 != 0:
            rsp.success = False
            rsp.error = 'encryptedDek must be valid base64'
            return jsonobject.dumps(rsp)
        try:
            encrypted_dek = base64.b64decode(normalized_b64)
            enc_again = base64.b64encode(encrypted_dek)
            if not isinstance(enc_again, str):
                enc_again = enc_again.decode('ascii')
            if enc_again.rstrip('=') != normalized_b64.rstrip('='):
                raise ValueError('non-canonical base64 input')
        except Exception as e:
            rsp.success = False
            rsp.error = 'encryptedDek must be base64: %s' % e
            return jsonobject.dumps(rsp)
        channel_path, err_code, err_msg = self._prepare_luks_secret_material_channel(encrypted_dek)
        if channel_path:
            rsp.success = True
            rsp.secFilePath = channel_path
        else:
            rsp.success = False
            if err_code:
                rsp.errorCode = err_code
                rsp.error = err_msg or err_code
            else:
                rsp.error = err_msg or 'key-agent PrepareLuksSecretMaterialChannel failed'
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_secret(self, req):
        rsp = kvmagent.AgentResponse()
        if not KEY_AGENT_GRPC_AVAILABLE:
            rsp.success = False
            rsp.error = 'key_agent grpc not available'
            return jsonobject.dumps(rsp)
        try:
            cmd = jsonobject.loads(req[http.REQUEST_BODY])
        except Exception as e:
            rsp.success = False
            rsp.error = 'invalid request body: %s' % e
            return jsonobject.dumps(rsp)
        vm_uuid = getattr(cmd, 'vmUuid', None)
        purpose = getattr(cmd, 'purpose', None)
        key_version = getattr(cmd, 'keyVersion', None)
        usage_instance = str(getattr(cmd, 'usageInstance', '') or '').strip()
        if not is_valid_key_agent_secret_purpose(purpose):
            rsp.success = False
            rsp.error = 'unsupported purpose: %s (supported: %s)' % (purpose, ','.join(KEY_AGENT_SUPPORTED_SECRET_PURPOSES))
            return jsonobject.dumps(rsp)
        if not vm_uuid or key_version is None or not usage_instance:
            rsp.success = False
            rsp.error = 'missing vmUuid, keyVersion or usageInstance (non-empty)'
            return jsonobject.dumps(rsp)
        if type(key_version) is not int or key_version < 0:
            rsp.success = False
            rsp.error = 'invalid keyVersion (must be non-negative int)'
            return jsonobject.dumps(rsp)
        secret_uuid, err_code, err_msg = self._get_secret_via_key_agent(
            str(vm_uuid), key_version, str(purpose), usage_instance)
        if secret_uuid:
            rsp.success = True
            rsp.secretUuid = secret_uuid
        else:
            rsp.success = False
            if err_code:
                rsp.errorCode = err_code
                rsp.error = err_msg or err_code
            else:
                rsp.error = err_msg or 'key-agent GetSecret failed'
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_secret(self, req):
        rsp = kvmagent.AgentResponse()
        if not KEY_AGENT_GRPC_AVAILABLE:
            rsp.success = False
            rsp.error = 'key_agent grpc not available'
            return jsonobject.dumps(rsp)
        try:
            cmd = jsonobject.loads(req[http.REQUEST_BODY])
        except Exception as e:
            rsp.success = False
            rsp.error = 'invalid request body: %s' % e
            return jsonobject.dumps(rsp)
        vm_uuid = getattr(cmd, 'vmUuid', None)
        purpose = getattr(cmd, 'purpose', None)
        key_version = getattr(cmd, 'keyVersion', None)
        usage_instance = str(getattr(cmd, 'usageInstance', '') or '').strip()
        if not is_valid_key_agent_secret_purpose(purpose):
            rsp.success = False
            rsp.error = 'unsupported purpose: %s (supported: %s)' % (purpose, ','.join(KEY_AGENT_SUPPORTED_SECRET_PURPOSES))
            return jsonobject.dumps(rsp)
        if not vm_uuid or key_version is None or not usage_instance:
            rsp.success = False
            rsp.error = 'missing vmUuid, keyVersion or usageInstance (non-empty)'
            return jsonobject.dumps(rsp)
        if type(key_version) is not int or key_version < 0:
            rsp.success = False
            rsp.error = 'invalid keyVersion (must be non-negative int)'
            return jsonobject.dumps(rsp)
        ok, err_code, err_msg = self._delete_secret_via_key_agent(
            str(vm_uuid), key_version, str(purpose), usage_instance)
        if ok:
            rsp.success = True
        else:
            rsp.success = False
            if err_code:
                rsp.errorCode = err_code
                rsp.error = err_msg or err_code
            else:
                rsp.error = err_msg or 'key-agent DeleteSecret failed'
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
        return float(sizeunit.get_size(str) / 1024)

    def _get_iscsi_initiator_name(self):
        initiator_name = linux.read_file(ISCSI_INITIATOR_NAME_PATH)
        if not initiator_name:
            return None
        # The config file content format like below:
        # InitiatorName=iqn.1994-05.com.redhat:aa9bf5ec494c
        return initiator_name.strip().split('=')[-1]

    def _get_host_nqn(self):
        nqn = linux.read_file(HOST_NQN_PATH)
        return nqn.strip() if nqn else None

    def _get_hostname(self):
        return shell.call('hostname').strip()

    @kvmagent.replyerror
    def update_nqn(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UpdateHostNqnResponse()

        if os.path.exists(HOST_NQN_PATH):
            with open(HOST_NQN_PATH, 'w') as f:
                f.write("%s\n" % (cmd.nqn))
        else:
            rsp.success = False
            rsp.error = 'cannot find file %s' % HOST_NQN_PATH

        return jsonobject.dumps(rsp)

    def _update_hostname(self, new_hostname):
        origin_hostname = self._get_hostname()

        ret, out, err = bash_roe("hostnamectl set-hostname %s" % new_hostname)
        if ret != 0:
            raise Exception("failed to set hostname, because %s" % err)

        hosts_file = "/etc/hosts"
        updated = False

        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tmp_file:
            logger.debug("attempting to open system file: %s (requires root privileges)", hosts_file)
            # TODO: Handle non-root scenarios - current implementation requires root Consider adding sudo support or graceful fallback
            with open(hosts_file, 'r') as f:
                for line in f:
                    if line.strip().startswith('#') or not line.strip():
                        tmp_file.write(line)
                        continue

                    parts = line.split()
                    if len(parts) < 2:
                        tmp_file.write(line)
                        continue

                    ip = parts[0]
                    hostnames = parts[1:]

                    if origin_hostname in hostnames:
                        new_hostnames = [new_hostname if h == origin_hostname else h for h in hostnames]
                        new_line = ip + "\t" + "\t".join(new_hostnames) + "\n"
                        tmp_file.write(new_line)
                        updated = True
                        logger.debug("updated hosts entry: %s -> %s" % (line.strip(), new_line.strip()))
                    else:
                        tmp_file.write(line)

        if updated:
            shell.run("sudo chmod 644 %s && sudo chown root:root %s" % (tmp_file.name, tmp_file.name))
            shell.run("sudo mv -f %s %s" % (tmp_file.name, hosts_file))
            logger.debug("updated /etc/hosts file successfully.")
        else:
            os.unlink(tmp_file.name)
            logger.debug("no entry for %s found in /etc/hosts. file not modified." % origin_hostname)

    @kvmagent.replyerror
    def update_hostname(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UpdateHostnameResponse()

        if not cmd.hostname:
            rsp.success = False
            rsp.error = "hostname parameter is required"
            return jsonobject.dumps(rsp)

        try:
            self._update_hostname(cmd.hostname)
        except Exception as e:
            rsp.success = False
            rsp.error = str(e)
            return jsonobject.dumps(rsp)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def update_iscsi_initiator_name(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UpdateHostIscsiInitiatorNameResponse()

        old_initiator_name = self._get_iscsi_initiator_name()
        if old_initiator_name != cmd.iscsiInitiatorName:
            try:
                with open(ISCSI_INITIATOR_NAME_PATH, 'w') as f:
                    f.write("InitiatorName=%s" % cmd.iscsiInitiatorName)
            except Exception as e:
                logger.error("failed to write iscsi initiator name %s to %s, because %s",
                             cmd.iscsiInitiatorName, ISCSI_INITIATOR_NAME_PATH, str(e))
                rsp.success = False
                rsp.error = str(e)
                return jsonobject.dumps(rsp)

        logger.info("iscsi initiator name changed from %s to %s, restart iscsid",
                    old_initiator_name, cmd.iscsiInitiatorName)

        ret, out, err = bash_roe("systemctl restart iscsid")
        if ret == 0:
            logger.info("iscsid restarted successfully")
            return jsonobject.dumps(rsp)

        err_message = "failed to restart iscsid, and start rollback, return code: %s, stdout: %s, stderr: %s" % (ret, out, err)
        logger.error(err_message)
        rsp.success = False
        rsp.error = err_message

        try:
            with open(ISCSI_INITIATOR_NAME_PATH, 'w') as f:
                f.write("InitiatorName=%s" % old_initiator_name)
        except Exception as e:
            logger.error("failed to write iscsi initiator name %s to %s, because %s",
                    old_initiator_name, ISCSI_INITIATOR_NAME_PATH, str(e))
                
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def fact(self, req):
        rsp = HostFactResponse()
        rsp.osDistribution, rsp.osVersion, rsp.osRelease = platform.dist()
        if rsp.osDistribution == 'centos':
            rsp.osDistribution = platform.linux_distribution()[0].lower()
        if rsp.osDistribution == 'openEuler':
            rsp.osDistribution = platform.linux_distribution()[0].lower()
        rsp.osRelease = rsp.osRelease if rsp.osRelease else "Core"
        # compatible with Kylin SP2 HostOS ISO and standardized ISO
        rsp.osRelease = rsp.osRelease.replace('ZStack', 'Sword') if rsp.osDistribution == "kylin" else rsp.osRelease
        # to be compatible with both `2.6.0` and `2.9.0(qemu-kvm-ev-2.9.0-16.el7_4.8.1)`
        qemu_img_version = shell.call("qemu-img --version | grep 'qemu-img version' | cut -d ' ' -f 3 | cut -d '(' -f 1")
        qemu_img_version = qemu_img_version.strip('\t\r\n ,')
        ipV4Addrs = [chunk.address for chunk in filter(
            lambda x: x.address != '127.0.0.1' and not x.ifname.endswith('zs'), iproute.query_addresses(ip_version=4))]

        def run_dmidecode(cmd, default=''):
            try:
                ret = shell.call(cmd).strip()
                return ret if ret else default
            except Exception as e:
                logger.warn("run dmidecode cmd %s failed: %s" % (cmd, e))
                return default

        is_dmidecode = shell.run("dmidecode")
        if str(is_dmidecode) == '0':
            rsp.systemSerialNumber = run_dmidecode('dmidecode -s system-serial-number', 'unknown')
            system_product_name = run_dmidecode('dmidecode -s system-product-name')
            if system_product_name:
                rsp.systemProductName = system_product_name
            else:
                rsp.systemProductName = run_dmidecode('dmidecode -s baseboard-product-name')
            rsp.systemManufacturer = run_dmidecode('dmidecode -s system-manufacturer', 'unknown')
            rsp.systemUUID = run_dmidecode('dmidecode -s system-uuid', 'unknown')
            rsp.biosVendor = run_dmidecode('dmidecode -s bios-vendor', 'unknown')
            rsp.biosVersion = run_dmidecode('dmidecode -s bios-version', 'unknown')
            rsp.biosReleaseDate = run_dmidecode('dmidecode -s bios-release-date', 'unknown')
            rsp.memorySlotsMaximum = run_dmidecode('dmidecode -q -t memory | grep "Memory Device" | wc -l')
            rsp.powerSupplyManufacturer = run_dmidecode("dmidecode -t 39 | grep -vi 'not specified' | grep -m1 'Manufacturer' | awk -F ':' '{print $2}'", 'unknown')
            rsp.powerSupplyModelName = run_dmidecode("dmidecode -t 39 | grep -vi 'not specified' | grep -m1 'Name' | awk -F ':' '{print $2}'", 'unknown')
            power_supply_max_power_capacity = run_dmidecode("dmidecode -t 39 | grep -vi 'unknown' | grep -m1 'Max Power Capacity' | awk -F ':' '{print $2}'")
            if bool(re.search(r'\d', power_supply_max_power_capacity)):
                rsp.powerSupplyMaxPowerCapacity = filter(str.isdigit, power_supply_max_power_capacity.strip())

        rsp.qemuImgVersion = qemu_img_version
        rsp.libvirtVersion = self.libvirt_version
        rsp.libvirtPackageVersion = linux.get_libvirt_package_version()
        rsp.ipAddresses = ipV4Addrs
        rsp.cpuArchitecture = platform.machine()
        rsp.uptime = shell.call('uptime -s').strip()
        rsp.iscsiInitiatorName = linux.get_iscsi_initiator_name()

        rsp.iscsiInitiatorName = self._get_iscsi_initiator_name()
        rsp.nqn = self._get_host_nqn()
        try:
            rsp.hostname = self._get_hostname()
        except Exception as e:
            logger.warn("failed to get hostname: %s" % str(e))
            rsp.hostname = None

        if not IS_LOONGARCH64:
            libvirtCapabilitiesList = []
            features = self._get_features_in_libvirt()
            if features and features.hasattr("incrementaldrivemirror"):
                libvirtCapabilitiesList.append("incrementaldrivemirror")
            if features and features.hasattr("blockcopynetworktarget"):
                libvirtCapabilitiesList.append("blockcopynetworktarget")
            rsp.libvirtCapabilities = libvirtCapabilitiesList

        bmc_version = shell.call("ipmitool mc info | grep 'Firmware Revision' | awk -F ':' '{print $2}'").strip()
        rsp.bmcVersion = bmc_version if bmc_version else 'unknown'

        # To see which lan the BMC is listening on, try the following (1-11), https://wiki.docking.org/index.php/Configuring_IPMI
        for channel in range(1, 12):
            '''     
            example:
            except result:         IP Address              : xxx.xxx.xxx.xxx 
            set ipmi_address "None" when got results unexpected or happened some errors   
            '''
            ret, out, err = bash_roe("ipmitool lan print %s | grep -w 'IP Address'| grep -v 'Source'" % channel)
            if ret == 0 and out != "":
                rsp.ipmiAddress = out.split(":")[1].strip()
                break
            else:
                rsp.ipmiAddress = 'None'
                logger.debug("failed to get ipmi address from BMC lan channel [%s], because %s" % (channel, err))

        if IS_AARCH64:
            # FIXME how to check vt of aarch64?
            rsp.hvmCpuFlag = 'vt'
            cpu_model = None
            try:
                cpu_model = self._get_host_cpu_model()
            except AttributeError:
                logger.debug("maybe XmlObject has no attribute model, use uname -p to get one")
                if cpu_model is None:
                    cpu_model = os.uname()[-1]

            rsp.cpuModelName = cpu_model
            host_cpu_model_name = shell.call("lscpu | awk -F':' '/Model name/{print $2}'")
            rsp.hostCpuModelName = host_cpu_model_name.strip() if host_cpu_model_name  else "aarch64"

            cpuMHz = shell.call("lscpu | awk '/max MHz/{ print $NF }'")
            # in case lscpu doesn't show cpu max mhz
            cpuMHz = "2500.0000" if cpuMHz.strip() == '' else cpuMHz
            rsp.cpuGHz = '%.2f' % (float(cpuMHz) / 1000)
            cpu_cores_per_socket = shell.call("lscpu | awk -F':' '/per socket/{print $NF}'")
            # On openeuler, lscpu otuputs 'per cluster' instead of 'per socket'
            if not cpu_cores_per_socket:
                cpu_cores_per_socket = shell.call("lscpu | awk -F':' '/per cluster/{print $NF}'")
            cpu_threads_per_core = shell.call("lscpu | awk -F':' '/per core/{print $NF}'")

            rsp.cpuSockets = linux.get_socket_num()
            rsp.cpuCoresPerSocket = int(cpu_cores_per_socket.strip())
            rsp.cpuThreadsPerCore = int(cpu_threads_per_core)
            rsp.cpuProcessorNum = rsp.cpuCoresPerSocket * rsp.cpuThreadsPerCore * rsp.cpuSockets

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
            rsp.cpuModelName = self._get_host_cpu_model()

            host_cpu_info = shell.call("grep -m2 -P -o -i '(model name|cpu MHz)\s*:\s*\K.*' /proc/cpuinfo").splitlines()
            host_cpu_model_name = host_cpu_info[0]
            rsp.hostCpuModelName = host_cpu_model_name

            transient_cpuGHz = '%.2f' % (float(host_cpu_info[1]) / 1000)
            static_cpuGHz_re = re.search('[0-9.]*GHz', host_cpu_model_name)
            rsp.cpuGHz = static_cpuGHz_re.group(0)[:-3] if static_cpuGHz_re else transient_cpuGHz
        else:
            if shell.run('grep vmx /proc/cpuinfo') == 0:
                rsp.hvmCpuFlag = 'vmx'

            if not rsp.hvmCpuFlag:
                if shell.run('grep svm /proc/cpuinfo') == 0:
                    rsp.hvmCpuFlag = 'svm'

            if shell.run('grep -w ept /proc/cpuinfo') == 0:
                rsp.eptFlag = 'ept'

            rsp.cpuModelName = self._get_host_cpu_model()

            host_cpu_info = shell.call("grep -m2 -P -o '(model name|cpu MHz)\s*:\s*\K.*' /proc/cpuinfo").splitlines()
            host_cpu_model_name = host_cpu_info[0]
            rsp.hostCpuModelName = host_cpu_model_name

            transient_cpuGHz = '%.2f' % (float(host_cpu_info[1]) / 1000)
            static_cpuGHz_re = re.search('[0-9.]*GHz', host_cpu_model_name)
            rsp.cpuGHz = static_cpuGHz_re.group(0)[:-3] if static_cpuGHz_re else transient_cpuGHz

            cpu_cores_per_socket = shell.call("lscpu | awk -F':' '/per socket/{print $NF}'")
            # On openeuler, lscpu otuputs 'per cluster' instead of 'per socket'
            if not cpu_cores_per_socket:
                cpu_cores_per_socket = shell.call("lscpu | awk -F':' '/per cluster/{print $NF}'")
            cpu_threads_per_core = shell.call("lscpu | awk -F':' '/per core/{print $NF}'")

            rsp.cpuSockets = linux.get_socket_num()
            rsp.cpuCoresPerSocket = int(cpu_cores_per_socket.strip())
            rsp.cpuThreadsPerCore = int(cpu_threads_per_core)
            rsp.cpuProcessorNum = rsp.cpuCoresPerSocket * rsp.cpuThreadsPerCore * rsp.cpuSockets

            cpu_cache_list = self._get_cpu_cache()
            rsp.cpuCache = ",".join(str(cache) for cache in cpu_cache_list)

        # get virtualizer info
        rsp.virtualizerInfo.uuid = self.config.get(kvmagent.HOST_UUID)
        rsp.virtualizerInfo.virtualizer = "qemu-kvm"
        rsp.virtualizerInfo.version = qemu.get_version_from_exe_file(qemu.get_path())

        # get CPU feature MD5 for migration compatibility check
        sh_cmd = shell.ShellCmd('virsh capabilities | virsh cpu-baseline /dev/stdin')
        sh_cmd(False)
        if sh_cmd.return_code == 0 and sh_cmd.stdout.strip():
            rsp.cpuFeatureMd5 = hashlib.md5(sh_cmd.stdout.strip().encode()).hexdigest()

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
                cache.cpuL1dCache = self._cache_units_convert(c_line.split(':')[1].strip())
            elif re.search('L1i cache', c_line):
                cache.cpuL1iCache = self._cache_units_convert(c_line.split(':')[1].strip())
            elif re.search('L2 cache', c_line):
                cache.cpuL2Cache = self._cache_units_convert(c_line.split(':')[1].strip())
            elif re.search('L3 cache', c_line):
                cache.cpuL3Cache = self._cache_units_convert(c_line.split(':')[1].strip())

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
            if shell.run("modprobe -r kvm-intel") != 0 or shell.run("modprobe kvm-intel %s" % param) != 0:
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
                rsp.error = '%s is not mounted, setup heartbeat file[%s] failed' % (mount_path, hb)
                rsp.success = False
                return jsonobject.dumps(rsp)

        for hb in cmd.heartbeatFilePaths:
            t = self.heartbeat_timer.get(hb, None)
            if t:
                t.cancel()

            hb_dir = os.path.dirname(hb)
            if not os.path.exists(hb_dir):
                os.makedirs(hb_dir, 0755)

            t = thread.timer(cmd.heartbeatInterval, self._heartbeat_func, args=[hb], stop_on_exception=False)
            t.start()
            self.heartbeat_timer[hb] = t
            logger.debug('create heartbeat file at[%s]' % hb)

        return jsonobject.dumps(rsp)

    def _get_next_available_port(self):
        for port in range(4100, 4200):
            if bash_r("netstat -nap | grep :%s[[:space:]] | grep LISTEN" % port) != 0:
                return port
        raise kvmagent.KvmError('no more available port for start usbredirect server')

    @kvmagent.replyerror
    @in_bash
    def start_usb_redirect_server(self, req):
        def _start_usb_server(port, busNum, devNum):
            iptc = iptables.from_iptables_save()
            iptc.add_rule('-A INPUT -p tcp -m tcp --dport %s -j ACCEPT' % port)
            iptc.iptable_restore()
            systemd_service_name = "usbredir-%s-%s-%s" % (port, busNum, devNum)
            if bash_r("systemctl list-units |grep %s" % systemd_service_name) == 0:
                bash_r("systemctl start %s" % systemd_service_name)
            else:
                bash_r("systemd-run --unit %s usbredirserver -p %s %s-%s" % (systemd_service_name, port, busNum, devNum))

            ret, output = linux.check_port('127.0.0.1', port)
            if not ret:
                logger.info("usb %s-%s start failed on port %s" % (busNum, devNum, port))
                return False, output
            logger.info("usb %s-%s start successed on port %s" % (busNum, devNum, port))
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
            rsp.error = "usb device[busNum: %s, deviceNum: %s does not exists." % (cmd.busNum, cmd.devNum)
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
        if bash_r("netstat -nap | grep :%s[[:space:]] | grep LISTEN | grep usbredir" % cmd.port) != 0:
            logger.info("port %s is not occupied by usbredir" % cmd.port)
        bash_r("systemctl stop usbredir-%s-%s-%s" % (cmd.port, cmd.busNum, cmd.devNum))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def check_usb_server_port(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckUsbServerPortRsp()
        r, o, e = bash_roe("netstat -nap | grep LISTEN | grep usbredir  | awk '{print $4}' | awk -F ':' '{ print $4 }'")
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
                return self.busNum + ':' + self.devNum + ':' + self.idVendor + ':' + self.idProduct + ':' + self.iManufacturer + ':' + self.iProduct + ':' + self.iSerial + ':' + self.usbVersion + ";"

        def append_usb_device(info, dev_id):
            if info.busNum == '' or info.devNum == '' or info.idVendor == '' or info.idProduct == '':
                logger.debug("cannot get busNum/devNum/idVendor/idProduct info in usbDevice %s, skip append" % dev_id)
            elif '(error)' in info.iManufacturer or '(error)' in info.iProduct:
                logger.debug("cannot get iManufacturer or iProduct info in usbDevice %s" % dev_id)
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
                    info.iManufacturer = ' '.join(line[2:]) if len(line) > 2 else ""
                elif line[0] == 'idProduct':
                    info.iProduct = ' '.join(line[2:]) if len(line) > 2 else ""
                elif line[0] == 'bcdUSB':
                    info.usbVersion = line[1]
                    # special case: USB2.0 with speed 1.5MBit/s or 12MBit/s should be attached to USB1.1 Controller
                    rst = bash_r("/usr/local/bin/lsusb.py | grep -v 'grep' | grep '%s' | grep -E '1.5MBit/s|12MBit/s'" % dev_id)
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
        bash_str = """#!/usr/bin/env python
import urllib2
def post_msg(data, post_url):
    headers = {"content-type": "application/json", "commandpath": "/host/reportdeviceevent"}
    req = urllib2.Request(post_url, data, headers)
    response = urllib2.urlopen(req)
    response.close()

if __name__ == "__main__":
    post_msg("{'hostUuid':'%s'}", '%s')
""" % (self.config.get(kvmagent.HOST_UUID), self.config.get(kvmagent.SEND_COMMAND_URL))

        event_report_script = '/usr/bin/_report_device_event.py'
        with open(event_report_script, 'w') as f:
            f.write(bash_str)
        os.chmod(event_report_script, 0o755)

        rule_str = 'ACTION=="add|remove", SUBSYSTEM=="usb", RUN="%s"' % event_report_script
        rule_path = '/etc/udev/rules.d/'
        rule_file = os.path.join(rule_path, 'usb.rules')
        if not os.path.exists(rule_path):
            os.makedirs(rule_path)
        with open(rule_file, 'w') as f:
            f.write(rule_str)

    @kvmagent.replyerror
    @in_bash
    def update_os(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        exclude = "--exclude=" + cmd.excludePackages if cmd.excludePackages else ""
        updates = cmd.updatePackages if cmd.updatePackages else ""
        releasever = cmd.releaseVersion if cmd.releaseVersion else kvmagent.get_host_yum_release()
        yum_cmd = "yum --enablerepo=* clean all && echo {}>/etc/yum/vars/YUM0 && ".format(releasever)
        # If upgrade qemu-kvm and libvirt at the same time
        # you need to upgrade qemu-kvm and then upgrade libvirt
        # to ensure that libvirtd is rebooted after upgrading qemu-kvm
        if "qemu-kvm" in updates or (cmd.releaseVersion != '' and "qemu-kvm" not in exclude):
            update_qemu_cmd = "export YUM0={0};yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{1} swap -y -- remove qemu-img-ev -- install qemu-img " \
                              "&& yum remove qemu-kvm-ev qemu-kvm-common-ev -y && yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{1} update " \
                              "qemu-storage-daemon -y && yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{1} install qemu-kvm qemu-kvm-common -y && "
            yum_cmd = yum_cmd + update_qemu_cmd.format(releasever,
                                                       ',zstack-experimental-mn' if cmd.enableExpRepo else '')
        if "libvirt" in updates or (cmd.releaseVersion != '' and "libvirt" not in exclude):
            update_libvirt_cmd = "export YUM0={};yum remove libvirt libvirt-libs libvirt-client libvirt-python libvirt-admin libvirt-bash-completion libvirt-daemon-driver-lxc -y {} && export YUM0={};" \
                                 "yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{} install libvirt libvirt-client libvirt-python -y && "
            yum_cmd = yum_cmd + update_libvirt_cmd.format(releasever,
                                                          '--noautoremove' if releasever in DISTRO_USING_DNF else '', releasever,
                                                          ',zstack-experimental-mn' if cmd.enableExpRepo else '')
        upgrade_os_cmd = "export YUM0={};yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{} {} update {} -y"
        yum_cmd = yum_cmd + upgrade_os_cmd.format(releasever, ',zstack-experimental-mn' if cmd.enableExpRepo else '', exclude, updates)

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
                rsp.error = "failed to update host os using zstack-mn,qemu-kvm-ev-mn repo, stdout: %s, stderr: %s" % (shell_cmd.stdout, shell_cmd.stderr)

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
            bash_r("/usr/local/bin/iohub_mocbr.sh %s start >> /var/log/iohubmocbr.log 2>&1" % cmd.mode)
            if cmd.mode == 'mocbr':
                iproute.set_link_attribute_no_error(cmd.masterVethName, master=cmd.bridgeName)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def update_dependency(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UpdateDependencyRsp()
        if self.IS_YUM:
            shell.run("yum --disablerepo=* --enablerepo=zstack-mn list >/dev/null 2>&1 || (rm -f /var/lib/rpm/_db.*; rpm --rebuilddb)")
            releasever = kvmagent.get_host_yum_release()
            shell.run("yum remove -y qemu-kvm-tools-ev")
            yum_cmd = "export YUM0={};yum --enablerepo=* clean all && yum --disablerepo=* --enablerepo={} install `cat /var/lib/zstack/dependencies` -y"\
                .format(releasever, cmd.zstackRepo)
            if shell.run("export YUM0={};yum --disablerepo=* --enablerepo=zstack-mn repoinfo".format(releasever)) != 0:
                rsp.success = False
                rsp.error = "no zstack-mn repo found, cannot update kvmagent dependencies"
            elif shell.run("export YUM0={};yum --disablerepo=* --enablerepo=qemu-kvm-ev-mn repoinfo".format(releasever)) != 0:
                rsp.success = False
                rsp.error = "no qemu-kvm-ev-mn repo found, cannot update kvmagent dependencies"
            elif shell.run(yum_cmd) != 0:
                rsp.success = False
                rsp.error = "failed to update kvmagent dependencies using %s repo" % cmd.zstackRepo
            else :
                logger.debug("successfully run: {}".format(yum_cmd))

            if cmd.enableExpRepo:
                exclude = "--exclude=" + cmd.excludePackages if cmd.excludePackages else ""
                updates = cmd.updatePackages if cmd.updatePackages else ""
                yum_cmd = "export YUM0={};yum --enablerepo=* clean all && yum --disablerepo=* --enablerepo={},zstack-experimental-mn {} update {} -y"
                yum_cmd = yum_cmd.format(releasever, cmd.zstackRepo, exclude, updates)
                if shell.run("export YUM0={};yum --disablerepo=* --enablerepo=zstack-experimental-mn repoinfo".format(releasever)) != 0:
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
                rsp.error = "failed to update kvmagent dependencies by {}.".format(apt_cmd)
            else :
                logger.debug("successfully run: {}".format(apt_cmd))
        else :
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

        frag_percent = bash_o("xfs_db -c frag -r %s | awk '/fragmentation factor/{print $7}'" % root_path, True)
        if not str(frag_percent).strip().endswith("%"):
            rsp.error = "error format %s" % frag_percent
            rsp.success = False
            return jsonobject.dumps(rsp)
        else:
            rsp.hostFrag = frag_percent.strip()[:-1]

        volume_path_dict = cmd.volumePathMap.__dict__
        if volume_path_dict is not None:
            for key, value in volume_path_dict.items():
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

# enable nr_hugepages
sysctl vm.nr_hugepages=0

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
''' % (' '.join(GRUB_FILES), ' '.join(GRUB_ROCKY_ENVS))
        disable_hugepage_script_path = linux.create_temp_file()
        with open(disable_hugepage_script_path, 'w') as f:
            f.write(disable_hugepage_script)
        logger.info('close_hugepage_script_path is: %s' % disable_hugepage_script_path)
        cmd = shell.ShellCmd('bash %s' % disable_hugepage_script_path)
        cmd(False)

        os.remove(disable_hugepage_script_path)
        return cmd.return_code, cmd.stdout

    @kvmagent.replyerror
    @in_bash
    def enable_hugepage(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = EnableHugePageRsp()

        # clean old hugepage config
        return_code, stdout = self._close_hugepage()
        if return_code != 0 or "Error" in stdout:
            rsp.success = False
            rsp.error = stdout
            return jsonobject.dumps(rsp)

        pageSize = cmd.pageSize
        reserveSize = cmd.reserveSize
        enable_hugepage_script = '''#!/bin/sh
grubs="%s"

# byte to mib
let "reserveSize=%s/1024/1024"
pageSize=%s
grubRockyEnvs="%s"
memSize=`free -m | awk '/:/ {print $2;exit}'`
let "pageNum=(memSize-reserveSize)/pageSize"
if [ $memSize -lt $reserveSize ]                                                                                                                                                                                   
then
    echo "Error:reserve size is bigger than system memory size"
    exit 1
fi
#drop cache 
echo 3 > /proc/sys/vm/drop_caches

# enable Transparent HugePages
echo always > /sys/kernel/mm/transparent_hugepage/enabled

# config grub
sed -i '/GRUB_CMDLINE_LINUX=/s/\"$/ transparent_hugepage=always default_hugepagesz=\'\"$pageSize\"\'M hugepagesz=\'\"$pageSize\"\'M hugepages=\'\"$pageNum\"\'\"/g' /etc/default/grub

#config boot grub
for var in $grubs
do 
   if [ -f $var ]; then
       sed -i '/^[[:space:]]*linux/s/$/ transparent_hugepage=always default_hugepagesz=\'\"$pageSize\"\'M hugepagesz=\'\"$pageSize\"\'M hugepages=\'\"$pageNum\"\'/g' $var
   fi    
done

#config rocky grubenv related to huge pages
for env in $grubRockyEnvs
do 
   if [ -f $env ]; then
       sed -i '/^[[:space:]]*kernelopts/s/$/ transparent_hugepage=always default_hugepagesz=\'\"$pageSize\"\'M hugepagesz=\'\"$pageSize\"\'M hugepages=\'\"$pageNum\"\'/g' $env
   fi
done   
''' % (' '.join(GRUB_FILES), reserveSize, pageSize, ' '.join(GRUB_ROCKY_ENVS))


        enable_hugepage_script_path = linux.create_temp_file()
        with open(enable_hugepage_script_path, 'w') as f:
            f.write(enable_hugepage_script)
        logger.info('enable_hugepage_script_path is: %s' % enable_hugepage_script_path)
        cmd = shell.ShellCmd('bash %s' % enable_hugepage_script_path)
        cmd(False)
        if cmd.return_code != 0 or "Error" in cmd.stdout:
            rsp.success = False
            rsp.error = cmd.stdout
        os.remove(enable_hugepage_script_path)
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
        sc = shell.ShellCmd("ethtool --identify %s %s" % (cmd.networkInterface, cmd.interval))
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
                        size = str(int(v.split(" ")[0]) / 1024) + " GB"
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
                elif k in ["configured clock speed", "configured memory speed"]:
                    clock_speed = v
                elif "configured voltage" == k:
                    if serial_number.lower() != "no dimm" and serial_number.lower() != "unknown" and serial_number is not None:
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
    def get_host_physical_cpu_facts(self, req):
        rsp = GetHostPhysicalCpuFactsResponse()
        r, o, e = bash_roe("dmidecode -q -t processor")
        if r != 0:
            rsp.success = False
            rsp.error = e
            return jsonobject.dumps(rsp)

        results = []
        cpu_arr = o.split("Processor Information")
        for infos in cpu_arr[1:]:
            socket_designation = version = current_speed = core_count = None
            for line in infos.splitlines():
                if line.strip() == "" or ":" not in line:
                    continue
                k = line.split(":")[0].lower().strip()
                v = ":".join(line.split(":")[1:]).strip()

                if "socket designation" == k:
                    socket_designation = v
                elif "version" == k:
                    version = v
                elif "serial number" == k:
                    serial_number = v
                elif "current speed" == k:
                    current_speed = v
                elif "core count" == k:
                    core_count = v
                elif "thread count" == k:
                    m = HostPhysicalCpuStruct()
                    m.socketDesignation = socket_designation
                    m.version = version
                    m.serialNumber = serial_number
                    m.currentSpeed = current_speed
                    m.coreCount = core_count
                    m.threadCount = v
                    results.append(m)
        rsp.physicalCpuFacts = results
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

    @kvmagent.replyerror
    def get_host_bonding_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetHostBondingFactsResponse()

        if not cmd.bondName:
            rsp.success = False
            rsp.error = "bondName is required"
            return jsonobject.dumps(rsp)

        if not linux.is_bond(cmd.bondName):
            rsp.success = False
            rsp.error = "bond[%s] not found or unsupported bonding type" % cmd.bondName
            return jsonobject.dumps(rsp)

        rsp.bonding = HostNetworkBondingInventory(cmd.bondName, "kernalBond", cmd.managementServerIp)
        return jsonobject.dumps(rsp)

    def _make_host_kernel_interface(self, interface_name=None, vlan_id=None, bridge_name=None):
        if not interface_name or vlan_id is None:
            logger.debug("interface name or vlan id is None")
            return None
        to = HostKernelInterfaceTO()
        to.interfaceName = interface_name
        to.vlanId = vlan_id
        to.bridgeName = bridge_name
        return to

    @kvmagent.replyerror
    @in_bash
    def get_kernel_interface(self, req):
        # cmd format: {"hostUuid":"edfea52447f14b54b2f3f04eb3aee0f5","targetIp":"172.25.228.27"}
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetHostKernelInterfaceResponse()
        rsp.interfaces = []

        _update_global_variables_for_net_config()
        link_name = linux.get_nic_name_by_ip(cmd.targetIp)
        if not link_name:
            rsp.error = "cannot find interface by ip[%s]" % cmd.targetIp
            rsp.success = False
            return jsonobject.dumps(rsp)

        logger.debug('find management ip[%s] on interface: %s' % (cmd.targetIp, link_name))
        ip_list = linux.get_ip_list_by_nic_name(link_name)

        interface = None
        if linux.is_bridge(link_name):  # ip on bridge
            all_slaves = linux.get_all_bridge_interface(link_name)
            for slave in all_slaves:
                if not slave:
                    continue
                if linux.is_bond(slave) or linux.is_physical_nic(slave):
                    interface = self._make_host_kernel_interface(slave, 0, link_name)
                    break
                if linux.is_vlan(slave):
                    vlan_parent = linux.get_vlan_parent(slave)
                    if linux.is_bond(vlan_parent) or linux.is_physical_nic(vlan_parent):
                        interface = self._make_host_kernel_interface(vlan_parent, linux.get_vlan_id(slave), link_name)
                        break
        elif linux.is_bond(link_name) or linux.is_physical_nic(link_name):
            interface = self._make_host_kernel_interface(link_name, 0)
        elif linux.is_vlan(link_name):
            vlan_parent = linux.get_vlan_parent(link_name)
            if linux.is_bond(vlan_parent) or linux.is_physical_nic(vlan_parent):
                interface = self._make_host_kernel_interface(vlan_parent, linux.get_vlan_id(link_name))
        else:
            rsp.error = "cannot parse interface[%s] by ip[%s]" % (link_name, cmd.targetIp)
            rsp.success = False
            return jsonobject.dumps(rsp)

        if not interface:
            rsp.error = "cannot find interface by ip[%s]" % cmd.targetIp
            rsp.success = False
        else:
            logger.debug('host kernel interface is: %s, vlan id is: %s' % (interface.interfaceName, interface.vlanId))
            interface.ips = [UsedIpTO(ip=item.ip, netmask=item.netmask, ipVersion=item.version, gateway=item.gateway) for item in ip_list]
            rsp.interfaces.append(interface)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def set_kernel_interface(self, req):
        # cmd format: "{\"interfaces\":[{\"interfaceName\":\"bond2\",
        #                                \"vlanId\":222,
        #                                \"ips\":[{\"ipVersion\":4,\"ip\":\"1.1.1.1\",\"netmask\":\"255.255.255.0\"}]
        #                               }],
        #               \"actionCode\":\"updateAction\"}"
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetHostKernelInterfaceResponse()

        for iface in cmd.interfaces:
            if not iface.interfaceName and not linux.is_physical_nic(iface.interfaceName) and not linux.is_bond(iface.interfaceName):
                raise Exception('cannot find interface or bond[%s]' % iface.interfaceName)

            physical_dev = iface.interfaceName if iface.vlanId == 0 else '%s.%s' % (iface.interfaceName, iface.vlanId)
            if not linux.is_device_exists(physical_dev):
                raise Exception('cannot find device[%s]' % physical_dev)

            bridge_dev = linux.get_master_device(physical_dev)
            target_dev = bridge_dev if bridge_dev else physical_dev
            logger.debug('host kernel interface is %s' % target_dev)

            if bridge_dev:
                ifcfg = netconfig.NetBridgeConfig(bridge_dev)
            elif iface.vlanId != 0:
                ifcfg = netconfig.NetVlanConfig(physical_dev)
            else:
                ifcfg = linux.get_device_ifcfg(physical_dev)

            exist_ips = linux.get_ip_list_by_nic_name(target_dev)
            exist_ip_set = {obj.ip for obj in exist_ips}

            removed_ips = [item for item in iface.ips if item.actionCode == UsedIpTO.ACTION_CODE_REMOVE]
            removed_ip_set = {item.ip for item in removed_ips}

            for item in removed_ips:
                shell.call('ip addr del %s/%s dev %s || true' % (item.ip, item.netmask, target_dev))
                ifcfg.delete_ip_config(item.ip)

            exist_ip_set -= removed_ip_set
            added_ips = [item for item in iface.ips
                         if item.actionCode == UsedIpTO.ACTION_CODE_ADD
                         and item.ip not in exist_ip_set]

            if added_ips:
                added_ip_set = {item.ip for item in added_ips}
                # when there are ips to create, and the boot proto is dhcp,
                # we need to change it to none and keep the existing ips
                if ifcfg.is_boot_proto_dhcp:
                    ifcfg.boot_proto = netconfig.NET_CONFIG_BOOTPROTO_NONE
                    for item in exist_ips:
                        if item.ip in exist_ip_set and item.ip not in added_ip_set:
                            ifcfg.add_ip_config(item.ip, item.netmask, item.gateway, item.version, item.is_default)

                for item in added_ips:
                    shell.call('ip addr add %s/%s dev %s' % (item.ip, item.netmask, target_dev))
                    ifcfg.add_ip_config(item.ip, item.netmask, item.gateway, item.version, item.is_default)

            ifcfg.restore_config()

        return jsonobject.dumps(rsp)

    def _has_vlan_or_bridge(self, ifname):
        if linux.is_bridge_slave(ifname):
            return True

        vlan_dev_name = '%s.' % ifname
        output = subprocess.check_output(['ip', 'link', 'show', 'type', 'vlan'], universal_newlines=True)
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
                    raise Exception(cmd.interfaceName + ' has a sub-interface or a bridge port')
        except Exception as e:
            rsp.error = 'unable to update ip[%s], because %s' % (cmd.interfaceName, str(e))
            rsp.success = False
            return jsonobject.dumps(rsp)

        if cmd.ipAddress is not None:
            try:
                # zs-network-setting -i eth0 192.168.1.10 255.255.255.0 192.168.1.1
                if cmd.gateway is not None:
                    shell.call('/usr/local/bin/zs-network-setting -i %s %s %s %s' % (cmd.interfaceName, cmd.ipAddress, cmd.netmask, cmd.gateway))
                else:
                    # zs-network-setting -d eth0
                    shell.call('/usr/local/bin/zs-network-setting -d %s' % cmd.interfaceName)
                    bash_o('/usr/local/bin/zs-network-setting -i %s %s %s' % (cmd.interfaceName, cmd.ipAddress, cmd.netmask))
            except Exception as e:
                rsp.error = 'unable to add ip on %s, because %s' % (cmd.interfaceName, str(e))
                rsp.success = False

            # After configuring the ip, check the connectivity
            if cmd.gateway is not None and shell.run('ping -c 5 -W 1 %s > /dev/null 2>&1' % cmd.gateway) != 0:
                shell.call('/usr/local/bin/zs-network-setting -d %s' % cmd.interfaceName)

                # If it is not connected, it will fall back to the old ip address
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
                shell.call('/usr/local/bin/zs-network-setting -d %s' % cmd.interfaceName)
            except Exception as e:
                rsp.error = 'unable to delete ip on %s, because %s' % (cmd.interfaceName, str(e))
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
            output = shell.call("ip link show type vlan | grep %s | awk -F'[.@]' '{print $2}'" % interface_name)
            interface_vlan_ids = output.strip().split('\n')

            if not interface_vlan_ids:
                interface_vlan_ids = ['0']
            else:
                interface_vlan_ids.append('0')

            if not vlan_ids:
                vlan_ids = interface_vlan_ids
            vlan_ids = [vlan for vlan in vlan_ids if vlan and vlan in interface_vlan_ids]

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
            addresses = iproute.query_addresses_by_ifname(ifname=interface_name)
            ip_addresses = [addr.address for addr in addresses]
            for addr in ip_addresses:
                if addr in cmd.ipAddresses:
                    if interface_name.startswith('br_'):
                        output = shell.call("brctl show %s | awk '{print $NF}' | grep -vw interfaces" % interface_name).strip().split('\n')
                        non_virtual_eths = [name for name in output if
                                  not (name.startswith('outer') or name.startswith('ud') or name.startswith('vnic'))]
                        interface_name = non_virtual_eths[0]
                    interface_names.append(interface_name)

        rsp.success = True
        rsp.interfaceNames = interface_names
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def set_service_type_on_host_network_interface(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetServiceTypeOnHostNetworkInterfaceRsp()
        rsp.success = False

        dev_name = cmd.interfaceName
        if cmd.vlanId is not None and cmd.vlanId is not 0:
            dev_name = '%s.%s' % (cmd.interfaceName, cmd.vlanId)

        register_service_type(dev_name, cmd.serviceType)
        rsp.success = True

        return jsonobject.dumps(rsp)

    @staticmethod
    def get_host_networking_interfaces(managementServerIp):
        nics = []
        pcis = set()

        def get_nic_info(interfaceName, index):
            nics[index] = HostNetworkInterfaceInventory(interfaceName, None, managementServerIp)

        threads = []
        nic_names = ip.get_host_physicl_nics()
        if len(nic_names) == 0:
            return nics

        nics = [None] * len(nic_names)
        for index, nic in enumerate(nic_names, start=0):
            interfaceName = nic.strip()
            pciDeviceAddress = os.readlink("/sys/class/net/%s/device" % interfaceName).strip().split('/')[-1]
            # exclude vf representor
            if pciDeviceAddress not in pcis:
                threads.append(thread.ThreadFacade.run_in_thread(get_nic_info, [interfaceName, index]))
                pcis.add(pciDeviceAddress)
        for t in threads:
            t.join()
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
                bonds.append(HostNetworkBondingInventory(bond, "kernalBond", managementServerIp))

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

    def _get_sriov_info(self, to):
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
                    to.virtStatus = "SRIOV_VIRTUALIZED"
                else:
                    to.virtStatus = "SRIOV_VIRTUALIZABLE"
        elif os.path.exists(physfn):
            # for vf, to.maxPartNum means the number of current vfs
            numvfs = os.path.join(physfn, "sriov_numvfs")
            if os.path.exists(numvfs):
                with open(numvfs, 'r') as f:
                    to.maxPartNum = f.read().strip()
            # for NVIDIA A-Series, after driver successfully installed, virtfn files will be created
            # set deviceId and vendorId null
            virtfn = os.path.join(dev, os.readlink(physfn), 'virtfn0')
            if pci.is_gpu(to.type) and self.NVIDIA_SMI_INSTALLED and os.path.exists(virtfn):
                to.deviceId = ""
                to.vendorId = ""
            else:
                to.virtStatus = "SRIOV_VIRTUAL"

            to.parentAddress = os.readlink(physfn).split('/')[-1]
            if os.path.exists(gpuvf):
                with open(gpuvf, 'r') as f:
                    for line in f.readlines():
                        line = line.strip()
                        if 'VF FB Size' in line:
                            to.ramSize = line.split(':')[-1].strip()
                            to.description = "%s [RAM Size: %s]" % (to.description, to.ramSize)
                            break
        else:
            return False
        return True

    def _get_vfio_mdev_info(self, to):
        addr = to.pciDeviceAddress

        if not self.NVIDIA_SMI_INSTALLED:
            return False

        check_mdev_folder = '/sys/bus/pci/devices/%s/mdev_supported_types' % addr
        legacy_mdev_dir_exists = os.path.isdir(check_mdev_folder)
        check_virtfn_folder = '/sys/bus/pci/devices/%s/virtfn0/mdev_supported_types' % addr
        virt_function_dir_exits = os.path.isdir(check_virtfn_folder)

        if not legacy_mdev_dir_exists and not virt_function_dir_exits:
            return False

        # check if nvidia vgpu is supported by current device
        r, o, e = bash_roe("nvidia-smi vgpu -i %s -v -c" % addr)
        if r != 0:
            return False

        for line in o.splitlines()[1:]:
            parts = line.split(':')
            if len(parts) < 2: continue
            title = parts[0].strip()
            content = ' '.join(parts[1:]).strip()
            if title == "vGPU Type ID":
                spec = {'TypeId': content}
                to.mdevSpecifications.append(spec)
            else:
                to.mdevSpecifications[-1][title] = content

        if legacy_mdev_dir_exists:
            self._legacy_mdev(to)
        elif virt_function_dir_exits:
            self._virt_function(to)

        return True

    def _legacy_mdev(self, to):
        # if supported specs != creatable specs, means it's aleady virtualized
        _, support, _ = bash_roe("nvidia-smi vgpu -i %s -s | grep -v %s" % (to.pciDeviceAddress, to.pciDeviceAddress))
        _, creatable, _ = bash_roe("nvidia-smi vgpu -i %s -c | grep -v %s" % (to.pciDeviceAddress, to.pciDeviceAddress))
        if support != creatable:
            to.virtStatus = "VFIO_MDEV_VIRTUALIZED"
        else:
            to.virtStatus = "VFIO_MDEV_VIRTUALIZABLE"

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

            for virf in os.listdir(os.path.join(virtfn_dir, 'mdev_supported_types')):
                if "nvidia-" in virf:
                    with open(os.path.join(virtfn_dir, 'mdev_supported_types', virf, "available_instances"), 'r') as af:
                        max_instances = af.read().strip()

                    if max_instances == '1':
                        virtualizable = True
                        break
            if virtualizable or mdev_devices_exists:
                break
        if virtualizable is True and mdev_devices_exists is False:
            to.virtStatus = "VFIO_MDEV_VIRTUALIZABLE"
        elif virtualizable is False and mdev_devices_exists is True:
            to.virtStatus = "VFIO_MDEV_VIRTUALIZED"

    def _simplify_pci_device_name(self, name):
        if 'Intel Corporation' in name:
            return 'Intel'
        elif 'Advanced Micro Devices' in name:
            return 'AMD'
        elif 'NVIDIA Corporation' in name:
            return 'NVIDIA'
        elif 'Haiguang' in name:
            return 'Haiguang'
        else:
            return name.replace('Co., Ltd ', '')

    def _collect_format_pci_device_info(self, rsp):
        pci_list = pci.lspci_or_throw() # type: list[dict]

        for pci_info in pci_list:
            vendor_name = ""
            device_name = ""
            subvendor_name = ""
            to = PciDeviceTO()

            to.pciDeviceAddress = pci_info['Slot']
            group_path = os.path.join('/sys/bus/pci/devices/', to.pciDeviceAddress, 'iommu_group')
            to.iommuGroup = os.path.realpath(group_path)

            if pci_info.has_key('Class'):
                to.type = pci_info['Class']
                to.description = pci_info['Class'] + ": "
            if pci_info.has_key('Vendor'):
                to.vendor = self._simplify_pci_device_name(pci_info['Vendor'])
                vendor_name = to.vendor
                to.vendorId = pci_info['VendorId']
                to.description += to.vendor + " "
            if pci_info.has_key('Device'):
                to.device = '%s [%s]' % (pci_info['Device'], pci_info['DeviceId'])
                device_name = self._simplify_pci_device_name(pci_info['Device'])
                to.deviceId = pci_info['DeviceId']
                to.description += device_name
            if pci_info.has_key('SVendor'):
                subvendor_name = pci_info['SVendor']
                to.subvendorId = pci_info['SVendorId']
            if pci_info.has_key('SDevice'):
                to.subdeviceId = pci_info['SDeviceId']
            to.name = "%s_%s" % (subvendor_name if subvendor_name else vendor_name, device_name)

            def _set_pci_to_type():
                gpu_vendors = ["NVIDIA", "AMD"]
                if any(vendor in to.description for vendor in gpu_vendors) \
                        and 'VGA compatible controller' in to.type:
                    to.type = "GPU_Video_Controller"
                elif any(vendor in to.description for vendor in gpu_vendors) \
                        and 'Audio device' in to.type:
                    to.type = "GPU_Audio_Controller"
                elif any(vendor in to.description for vendor in gpu_vendors) \
                        and 'USB controller' in to.type:
                    to.type = "GPU_USB_Controller"
                elif any(vendor in to.description for vendor in gpu_vendors) \
                        and 'Serial bus controller' in to.type:
                    to.type = "GPU_Serial_Controller"
                elif any(vendor in to.description for vendor in gpu_vendors) \
                        and '3D controller' in to.type:
                    to.type = "GPU_3D_Controller"
                elif 'Ethernet controller' in to.type:
                    to.type = "Ethernet_Controller"
                elif 'Audio device' in to.type:
                    to.type = "Audio_Controller"
                elif 'USB controller' in to.type:
                    to.type = "USB_Controller"
                elif 'Serial controller' in to.type:
                    to.type = "Serial_Controller"
                elif 'RAID bus controller' in to.type:
                    to.type = "RAID_Controller"
                elif 'SATA controller' in to.type:
                    to.type = "SATA_Controller"
                elif 'Memory controller' in to.type:
                    to.type = "Memory_Controller"
                elif 'Non-Volatile memory controller' in to.type:
                    to.type = "Non_Volatile_Memory_Controller"
                elif 'Fibre Channel' in to.type:
                    to.type = "Fibre_Channel"
                elif 'Moxa Technologies' in to.type:
                    to.type = "Moxa_Device"
                elif 'System peripheral' in to.type:
                    to.type = "System_Peripheral"
                elif 'ISA bridge' in to.type:
                    to.type = "ISA_Bridge"
                elif 'Host bridge' in to.type:
                    to.type = "Host_Bridge"
                elif 'PCI bridge' in to.type:
                    to.type = "PCI_Bridge"
                elif 'Performance counters' in to.type:
                    to.type = "Performance_Counters"
                elif 'Signal processing controller' in to.type:
                    to.type = "Signal_Processing_Controller"
                elif 'Communication controller' in to.type:
                    to.type = "Communication_Controller"
                elif 'PIC' in to.type:
                    to.type = "PIC"
                elif 'SMBus' in to.type:
                    to.type = "SMBus"
                else:
                    to.type = "Generic"

            _set_pci_to_type()

            self._collect_gpu_addoninfo(to, vendor_name)

            # if support both mdev and sriov, then set the pci device to VFIO_MDEV_VIRTUALIZABLE
            if not self._get_vfio_mdev_info(to) and not self._get_sriov_info(to):
                to.virtStatus = "UNVIRTUALIZABLE"
            if to.vendorId != '' and to.deviceId != '':
                rsp.pciDevicesInfo.append(to)

        pci.calculate_max_addressable_memory(rsp.pciDevicesInfo)

    def _collect_gpu_addoninfo(self, to, vendor_name):
        if pci.is_gpu(to.type):
            if vendor_name == 'NVIDIA':
                self._collect_nvidia_gpu_info(to)
            if vendor_name == 'AMD':
                self._collect_amd_gpu_info(to)
            if vendor_name == 'Haiguang':
                self._collect_haiguang_gpu_info(to)

    @in_bash
    def _collect_haiguang_gpu_info(self, to):
        if shell.run("which hy-smi") != 0:
            logger.debug("no hy-smi")
            return

        r, o, e = bash_roe("hy-smi --showserial --showmaxpower --showmemavailable --showbus --json")
        if r != 0:
            logger.error("hy query gpu is error, %s " % e)
            return

        try:
            gpu_info_json = json.loads(o)
            for card_name, card_data in gpu_info_json.items():
                if to.pciDeviceAddress.lower() in card_data["PCI Bus"].lower():
                    to.addonInfo["memory"] = card_data["Available memory size (MiB)"] + " MiB"
                    to.addonInfo["power"] = card_data["Max Graphics Package Power (W)"]
                    to.addonInfo["serialNumber"] = card_data["Serial Number"]
                    to.addonInfo["isDriverLoaded"] = True
        except Exception as e:
            logger.error("hy query gpu is error, %s " % e)


    @in_bash
    def _collect_nvidia_gpu_info(self, to):
        if shell.run("which nvidia-smi") != 0:
            logger.debug("no nvidia-smi")
            return

        r, o, e = bash_roe("nvidia-smi --query-gpu=gpu_bus_id,memory.total,power.limit,gpu_serial"
                           " --format=csv,noheader")
        if r != 0:
            logger.error("nvidia query gpu is error, %s " % e)
            return

        for part in o.split('\n'):
            if len(part.strip()) == 0:
                continue
            gpuinfo = part.split(',')
            if to.pciDeviceAddress in gpuinfo[0].strip():
                to.addonInfo["memory"] = gpuinfo[1].strip()
                to.addonInfo["power"] = gpuinfo[2].strip()
                to.addonInfo["serialNumber"] = gpuinfo[3].strip()
                to.addonInfo["isDriverLoaded"] = True

    @in_bash
    def _collect_amd_gpu_info(self, to):
        #todo collect amd gpu info
        if shell.run("which rocm-smi") != 0:
            logger.debug("no rocm-smi")
            return

        r, o, e = bash_roe("rocm-smi --showbus --showmeminfo vram --showpower --showserial --json")
        if r != 0:
            logger.error("amd query gpu is error, %s " % e)
            return
        try:
            gpu_info_json = json.loads(o.strip())
            for card_name, card_data in gpu_info_json.items():
                if to.pciDeviceAddress.lower() in card_data['PCI Bus'].lower():
                    to.addonInfo["memory"] = card_data['VRAM Total Memory (B)']
                    to.addonInfo["power"] = card_data['Average Graphics Package Power (W)']
                    to.addonInfo["serialNumber"] = card_data['Serial Number']
                    to.addonInfo["isDriverLoaded"] = True
        except Exception as e:
            logger.error("amd query gpu is error, %s " % e)

    # moved from vm_plugin to host_plugin
    @kvmagent.replyerror
    def get_pci_info(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetPciDevicesResponse()

        if cmd.skipGrubConfig:
            rsp.hostIommuStatus = True
            self._collect_format_pci_device_info(rsp)
            return jsonobject.dumps(rsp)

        # update grub to enable/disable iommu in host
        updateConfigration = UpdateConfigration()
        updateConfigration.path = "/etc/default/grub"
        updateConfigration.enableIommu = cmd.enableIommu
        success, error = updateConfigration.updateHostIommu()
        if success is False:
            rsp.success = False
            rsp.error = error
            return jsonobject.dumps(rsp)

        updateConfigration.updateGrubConfig()
        iommu_type = updateConfigration.iommu_type
        # check whether /sys/class/iommu is empty, if not then iommu is activated in bios
        iommu_folder = '/sys/class/iommu'
        r_bios = os.path.isdir(iommu_folder) and os.listdir(iommu_folder)
        r_kernel, o_kernel, e_kernel = bash_roe("grep '{}=on' /proc/cmdline".format(iommu_type))
        if r_bios and r_kernel == 0:
            rsp.hostIommuStatus = True
        else:
            rsp.hostIommuStatus = False

        # get pci device info
        self._collect_format_pci_device_info(rsp)
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
                logger.debug("delete rom file %s because no content in db anymore" % rom_file)
                os.remove(rom_file)
        elif cmd.romMd5sum != hashlib.md5(cmd.romContent).hexdigest():
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
        # make install mxgpu driver if need to
        mxgpu_driver_tar = "/var/lib/zstack/mxgpu_driver.tar.gz"
        if os.path.exists(mxgpu_driver_tar):
            r, o, e = bash_roe("tar xvf %s -C /tmp; cd /tmp/mxgpu_driver; make; make install" % mxgpu_driver_tar)
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
            _, used, _ = bash_roe("modprobe -r gim; lsmod | grep gim | awk '{ print $3 }'")
            if used:
                rsp.success = False
                rsp.error = "failed to uninstall gim.ko, need to run `modprobe -r gim` manually"
                return

        # prepare gim_config
        gim_config = "/etc/gim_config"
        with open(gim_config, 'w') as f:
            f.write("vf_num=%s" % cmd.virtPartNum)

        # install gim.ko
        r, o, e = bash_roe("modprobe gim")
        if r != 0:
            rsp.success = False
            rsp.error = "failed to install gim.ko, %s, %s" % (o, e)
            return


    @in_bash
    def _generate_sriov_net_devices(self, cmd, rsp):
        numvfs = os.path.join('/sys/bus/pci/devices/', cmd.pciDeviceAddress, 'sriov_numvfs')
        if not os.path.exists(numvfs):
            rsp.success = False
            rsp.error = 'cannot find sriov_numvfs file for pci device[addr:%s, type:%s]' % (cmd.pciDeviceAddress, cmd.pciDeviceType)
            return

        r, o, e = bash_roe("echo %s > %s" % (cmd.virtPartNum, numvfs))
        if r != 0:
            rsp.success = False
            rsp.error = 'failed to generate virtual functions on pci device[addr:%s, type:%s]' % (cmd.pciDeviceAddress, cmd.pciDeviceType)
            return


    @kvmagent.replyerror
    def generate_sriov_pci_devices(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GenerateSriovPciDevicesRsp()
        logger.debug("generate_sriov_pci_devices: pciType[%s], pciAddr[%s], reSplite[%s]" % (cmd.pciDeviceType, cmd.pciDeviceAddress, cmd.reSplite))

        addr = cmd.pciDeviceAddress

        # ramdisk file in /dev/shm to mark host rebooting
        if cmd.pciDeviceType == 'Ethernet_Controller':
            ramdisk = "/dev/shm/pci_sriov_gim_" + addr
        else:
            ramdisk = "/dev/shm/pci_sriov_gim"

        if cmd.reSplite and os.path.exists(ramdisk):
            logger.debug("no need to re-splite pci device[addr:%s] into sriov pci devices" % addr)
            return jsonobject.dumps(rsp)

        if pci.is_gpu(cmd.pciDeviceType):
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
        # remote gim.ko
        r, o, e = bash_roe("modprobe -r gim")
        if r != 0:
            rsp.success = False
            rsp.error = "failed to remove gim.ko, %s, %s" % (o, e)
            return


    @in_bash
    def _ungenerate_sriov_net_devices(self, cmd, rsp):
        numvfs = os.path.join('/sys/bus/pci/devices/', cmd.pciDeviceAddress, 'sriov_numvfs')
        if not os.path.exists(numvfs):
            rsp.success = False
            rsp.error = 'cannot find sriov_numvfs file for pci device[addr:%s, type:%s]' % (cmd.pciDeviceAddress, cmd.pciDeviceType)
            return

        def _check_allocated_virtual_functions():
            _addr = cmd.pciDeviceAddress

            if len(_addr.split(':')) != 3:
                _addr = '0000:' + _addr

            pf = "pci_%s_%s_%s_%s" % tuple(re.split(':|\.', _addr))
            r, vf_lines, e = bash_roe("virsh nodedev-dumpxml %s | grep 'address domain'" % pf)
            if r != 0:
                return "failed to run `virsh nodedev-dumpxml %s`: %s" % (pf, e)

            pattern = re.compile(r'.*0x([0-9a-f]*).*0x([0-9a-f]*).*0x([0-9a-f]*).*0x([0-9a-f]*).*')
            for vf_line in vf_lines.split('\n'):
                vf_line = vf_line.strip()
                match = pattern.match(vf_line)
                if match:
                    vf = "pci_%s_%s_%s_%s" % tuple(match.groups())
                    r, o, e = bash_roe("virsh nodedev-dumpxml %s | grep vfio-pci" % vf)
                    if r == 0:
                        return "virtual function %s of pf %s still allocated to some vm" % (vf, pf)

        _error = _check_allocated_virtual_functions()
        if _error:
            rsp.success = False
            rsp.error = _error
            return

        r, o, e = bash_roe("lspci >/dev/null && echo 0 > %s" % numvfs)
        if r != 0:
            rsp.success = False
            rsp.error = 'failed to ungenerate virtual functions on pci device[addr:%s, type:%s]' % (cmd.pciDeviceAddress, cmd.pciDeviceType)
            return


    @kvmagent.replyerror
    def ungenerate_sriov_pci_devices(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UngenerateSriovPciDevicesRsp()

        addr = cmd.pciDeviceAddress

        if pci.is_gpu(cmd.pciDeviceType):
            self._ungenerate_sriov_gpu_devices(cmd, rsp)
        elif cmd.pciDeviceType == 'Ethernet_Controller':
            self._ungenerate_sriov_net_devices(cmd, rsp)
        else:
            rsp.success = False
            rsp.error = "do not support sriov of pci device [addr:%s]" % addr

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def generate_vfio_mdev_devices(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GenerateVfioMdevDevicesRsp()
        logger.debug("generate_vfio_mdev_devices: mdevUuids[%s]" % cmd.mdevUuids)

        # ramdisk file in /dev/shm to mark host rebooting
        addr = cmd.pciDeviceAddress

        # before 3.5.1, pciDeviceAddress is composed by only bus:slot.func
        no_domain_addr = addr if len(addr.split(':')) != 3 else ':'.join(addr.split(':')[1:])
        ramdisk = os.path.join('/dev/shm', 'pci-' + no_domain_addr)
        if cmd.mdevUuids and len(cmd.mdevUuids) != 0 and os.path.exists(ramdisk):
            logger.debug("no need to re-splite pci device[addr:%s] into mdev devices" % addr)
            return jsonobject.dumps(rsp)

        @linux.retry(times=30, sleep_time=5)
        def _exec_nvidia_sriov_manage(addr):
            bash_roe("/usr/lib/nvidia/sriov-manage -e %s" % addr)

        # virtualization needs to be enabled when restarting the host to sync vgpu mdev
        if os.path.exists('/usr/lib/nvidia/sriov-manage'):
            _exec_nvidia_sriov_manage(addr)

        # support nvidia gpu only
        type = int(cmd.mdevSpecTypeId, 0)
        spec_path = os.path.join("/sys/bus/pci/devices/", addr, "mdev_supported_types", "nvidia-%d" % type)
        legacy_spec_exists = os.path.exists(spec_path)
        virtfn_path = os.path.join("/sys/bus/pci/devices/", addr, "virtfn0", "mdev_supported_types", "nvidia-%d" % type)
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
                        logger.debug("re-generate mdev device[uuid:%s] from pci device[addr:%s]" % (_uuid, addr))
            else:
                with open(os.path.join(spec_path, "available_instances"), 'r') as af:
                    max_instances = af.read().strip()
                for i in range(int(max_instances)):
                    _uuid = str(uuid.uuid4())
                    rsp.mdevUuids.append(_uuid)
                    with open(os.path.join(spec_path, "create"), 'w') as cf:
                        cf.write(_uuid)
                        logger.debug("generate mdev device[uuid:%s] from pci device[addr:%s]" % (_uuid, addr))
        elif virt_function_spec_exits:
            r, o, e = bash_roe("ls /sys/bus/pci/devices/%s/ | grep virtfn" % addr)
            if r != 0:
                rsp.success = False
                rsp.error = e
                return jsonobject.dumps(rsp)

            if cmd.mdevUuids and len(cmd.mdevUuids) != 0:
                for _uuid, virtfn in zip(cmd.mdevUuids, o.splitlines()):
                    virtfn_dir = "/sys/bus/pci/devices/%s/%s/mdev_supported_types/nvidia-%d" % (addr, virtfn, type)
                    with open(os.path.join(virtfn_dir, "create"), 'w') as f:
                        f.write(str(uuid.UUID(_uuid)))
                        logger.debug("re-generate mdev device[uuid:%s] from pci device[addr:%s]" % (_uuid, addr))
            else:
                is_generate = False
                for virtfn in o.splitlines():
                    virtfn_dir =  "/sys/bus/pci/devices/%s/%s/mdev_supported_types/nvidia-%d" % (addr, virtfn, type)
                    with open(os.path.join(virtfn_dir, "available_instances"), 'r') as af:
                        max_instances = af.read().strip()
                        if int(max_instances) > 0:
                            is_generate = True
                    for i in range(int(max_instances)):
                        _uuid = str(uuid.uuid4())
                        rsp.mdevUuids.append(_uuid)
                        with open(os.path.join(virtfn_dir, "create"), 'w') as cf:
                            cf.write(_uuid)
                            logger.debug("generate mdev device[uuid:%s] from pci device[addr:%s]" % (_uuid, addr))

                if not is_generate:
                    with open(os.path.join(virtfn_path, "name"), 'r') as f:
                        name = f.read().strip()
                    rsp.success = False
                    rsp.error = "generate mdev device[name:%s] from pci device[addr:%s] is fail " % (name, addr)

        # create ramdisk file after pci device virtualization
        open(ramdisk, 'a').close()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def ungenerate_vfio_mdev_devices(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UngenerateVfioMdevDevicesRsp()

        # support nvidia gpu only
        addr = cmd.pciDeviceAddress
        type = int(cmd.mdevSpecTypeId, 0)
        device_path = os.path.join("/sys/bus/pci/devices/", addr, "mdev_supported_types", "nvidia-%d" % type, "devices")
        legacy_spec_exists = os.path.exists(device_path)
        virtfn_path = os.path.join("/sys/bus/pci/devices/", addr, "virtfn0", "mdev_supported_types", "nvidia-%d" % type, "devices")
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
            _, support, _ = bash_roe("nvidia-smi vgpu -i %s -s | grep -v %s" % (addr, addr))
            _, creatable, _ = bash_roe("nvidia-smi vgpu -i %s -c | grep -v %s" % (addr, addr))
            if support != creatable:
                rsp.success = False
                rsp.error = "failed to ungenerate vfio mdev devices from pci device[addr:%s]" % addr
        elif virt_function_dir_exits:
            r, o, e = bash_roe("ls /sys/bus/pci/devices/%s/ | grep virtfn" % addr)
            if r != 0:
                rsp.success = False
                rsp.error = e
                return jsonobject.dumps(rsp)

            for virtfn in o.splitlines():
                virtfn_dir =  os.path.join("/sys/bus/pci/devices/", addr, virtfn, "mdev_supported_types", "nvidia-%d" % type, "devices")
                for _uuid in os.listdir(virtfn_dir):
                    with open(os.path.join(virtfn_dir, _uuid, "remove"), "w") as f:
                        f.write("1")

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

        se_num_record_file =  "%s/mtty-2/available_instances" % check_virtfn_folder
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
        logger.debug("generate_se_vfio_mdev_devices: mdevUuids[%s]" % cmd.mdevUuids)

        mtty_uuid = cmd.mttyDeviceUuid
        ramdisk = os.path.join('/dev/shm', 'mtty-' + mtty_uuid)
        if cmd.reSplite and os.path.exists(ramdisk):
            logger.debug("no need to re-splite mtty device[uuid:%s] into mdev devices" % mtty_uuid)
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
                logger.debug('generate mdev device[uuid:%s] from mtty device[uuid:%s]'% (str(_uuid), mtty_uuid))

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
        r1 = bash_r("grep '^[[:space:]]*spice_tls[[:space:]]*=[[:space:]]*1' /etc/libvirt/qemu.conf")
        r2 = bash_r("grep '^[[:space:]]*spice_tls_x509_cert_dir[[:space:]]*=[[:space:]]*' /etc/libvirt/qemu.conf")

        if r1 == 0 and r2 == 0:
            return jsonobject.dumps(rsp)

        if r1 != 0:
            r = bash_r("sed -i '$a spice_tls = 1' /etc/libvirt/qemu.conf")
            if r != 0:
                rsp.success = False
                rsp.error = "update /etc/libvirt/qemu.conf failed, please check qemu.conf"
                return jsonobject.dumps(rsp)

        if r2 != 0:
            r = bash_r("sed -i '$a spice_tls_x509_cert_dir = \"/var/lib/zstack/kvm/package/spice-certs/\"' /etc/libvirt/qemu.conf")
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
            raise kvmagent.KvmError("cannot find SEND_COMMAND_URL, unable to transmit vm operation to management node")

        logger.debug('transmitting vm operation [uuid:%s, operation:%s] to management node'% (cmd.uuid, cmd.operation))
        http.json_dump_post(url, vm_operation, {'commandpath': '/host/transmitvmoperation'})
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
            raise kvmagent.KvmError("cannot find SEND_COMMAND_URL, unable to transmit zwatch install result to management node")

        logger.debug('transmitting zwatch install result [uuid:%s, version:%s] to management node' % (cmd.vmInstanceUuid, cmd.version))
        http.json_dump_post(url, result, {'commandpath': '/host/zwatchInstallResult'})
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
            os.makedirs(COLO_LIB_PATH, 0775)

        def get_dep_version_from_version_file(version_file):
            if not os.path.exists(version_file):
                return None
            else:
                with open(version_file, 'r') as vfd:
                    return vfd.readline()

        last_modified = shell.call("curl -I %s | grep 'Last-Modified'" % qemu_url).strip('\n\r')
        version = get_dep_version_from_version_file(COLO_QEMU_KVM_VERSION)
        if version != last_modified:
            cmdstr = 'cd {} && rm -f qemu-system-x86_64.tar.gz && wget -c {} -O qemu-system-x86_64.tar.gz && ' \
                     'tar zxf qemu-system-x86_64.tar.gz && chown root:root qemu-system-x86_64'.format(COLO_LIB_PATH, qemu_url)
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
            r, o, e = bash_roe("ip netns exec %s nping --tcp -p %s -c 1 %s" % (cmd.brname, port, cmd.ip))
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
                    node_path = os.path.join(NODE_INFO_PATH, "node{}".format(node_id))
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
                        cpu_list.extend([str(cpu_id) for cpu_id in range(int(temp[0]), int(temp[1]) + 1)])
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
                    temp = filter(lambda i: i, mem.strip().split(" "))[-2]
                    if temp == "0":
                        continue
                    if "MemTotal" in mem:
                        size = int(temp)*1024
                    if "MemFree:" in mem:
                        free = int(temp)*1024
                return size, free

            @staticmethod
            def get_distance(info_path):
                data = None
                with open(info_path, "r") as f:
                    data = f.read()
                if data is None or (not data):
                    return
                data = data.strip()
                return filter(lambda i: i, data.split(" "))

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
            rsp.device = lvm.LvmRemoteStorage(cmd.volumeInstallPath, cmd.mountPath, cmd.device).mount()
        elif cmd.volumeInstallPath.startswith('ceph'):
            rsp.device = ceph.NbdRemoteStorage(cmd.volumeInstallPath, cmd.mountPath, cmd.device, cmd.volumePrimaryStorageUuid).mount()
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
            lvm.LvmRemoteStorage(cmd.volumeInstallPath, cmd.mountPath, cmd.device).umount()
        elif cmd.volumeInstallPath.startswith('ceph'):
            ceph.NbdRemoteStorage(cmd.volumeInstallPath, cmd.mountPath, cmd.device).umount()
        else:
            raise Exception("do not support volume type")

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def download_file(self, req):
        rsp = DownloadFileRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        install_path, err = linux.validate_install_path(cmd.installPath)
        if err:
            rsp.success = False
            rsp.error = err
            return jsonobject.dumps(rsp)
        cmd.installPath = install_path

        reporter = report.Report.from_spec(cmd, "DownloadFile")
        fileDownloader = FileDownloader(reporter, cmd)
        success, error = fileDownloader.download()
        if not success:
            rsp.success = False
            rsp.error = error if error else 'download failed'
            return jsonobject.dumps(rsp)

        rsp.md5sum = linux.get_file_md5sum_hashlib(cmd.installPath)
        rsp.size = os.path.getsize(cmd.installPath)
        return jsonobject.dumps(rsp)

    def get_direct_upload_path(self, host):
        return 'http://' + host + self.FILE_DIRECT_UPLOAD_PATH

    @kvmagent.replyerror
    def upload_file(self, req):
        rsp = UploadFileRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        install_path, err = linux.validate_install_path(cmd.installPath)
        if err:
            rsp.success = False
            rsp.error = err
            return jsonobject.dumps(rsp)
        cmd.installPath = install_path

        def _prepare_upload():
            class FileUploadDaemon(plugin.TaskDaemon):
                def __init__(self, task):
                    super(FileUploadDaemon, self).__init__(cmd, 'fileUpload')
                    self.task = task
                    self.task.close = self.close

                def _cancel(self):
                    if self.task.completed:
                        return
                    self.task.fail("file[%s] upload canceled" % cmd.installPath)
                    linux.rm_file_force(cmd.installPath)

            task = FileSystemUploadTask(cmd.taskUuid, cmd.installPath)
            self.upload_tasks.add_task(task)
            FileUploadDaemon(task).start()

        _prepare_upload()
        rsp.directUploadUrl = self.get_direct_upload_path(req[http.REQUEST_HEADER]['Host'])
        return jsonobject.dumps(rsp)

    def direct_upload_file(self, req):
        try:
            UploadHandler(req, self.upload_tasks).handle_upload()
        except Exception as e:
            logger.exception("File upload failed: %s", str(e))

    @kvmagent.replyerror
    def get_upload_progress(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        task = self.upload_tasks.get_task(cmd.taskUuid)
        if task is None:
            raise Exception('task not found')

        def _get_file_size(file_path):
            return os.path.getsize(file_path) if os.path.exists(file_path) else 0

        rsp = UploadProgressRsp()
        rsp.apiId = cmd.taskUuid
        rsp.completed = task.completed
        rsp.size = task.expectedSize
        rsp.actualSize = task.expectedSize
        rsp.downloadSize = task.checked_download_size()
        rsp.lastOpTime = long(task.lastOpTime) * 1000
        rsp.supportSuspend = True
        if task.downloadSize == 0:
            rsp.progress = 0
            rsp.installPath = self.get_direct_upload_path(req[http.REQUEST_HEADER]['Host'])
        elif task.completed and not task.lastError:
            actual_size = _get_file_size(task.installPath)
            if actual_size == 0:
                rsp.success = False
                rsp.error = "Upload completed but file not found or empty"
                return jsonobject.dumps(rsp)
            rsp.size = actual_size
            rsp.md5sum = linux.get_file_md5sum_hashlib(task.installPath)
            rsp.installPath = task.installPath
            rsp.progress = 100
        else:
            if task.expectedSize > 0:
                rsp.progress = min(90, task.downloadSize * 90 // task.expectedSize)
            else:
                rsp.progress = 0
                logger.warning("upload task not yet fully initialized (expectedSize=%s)", task.expectedSize)
            rsp.installPath = self.get_direct_upload_path(req[http.REQUEST_HEADER]['Host'])

        if task.lastError is not None:
            rsp.success = False
            rsp.error = task.lastError
        return jsonobject.dumps(rsp)

    @property
    def libvirt_version(self):
        return linux.get_libvirt_version()

    @property
    def qemu_version(self):
        return qemu.get_version()

    @kvmagent.replyerror
    @in_bash
    def get_block_devices(self, req):
        rsp = GetBlockDevicesResponse()

        CDROM_PREFIX = '/dev/sr'

        def skip_get_smart_info(name):
            return name.startswith(CDROM_PREFIX)

        class BlockDevice:
            def __init__(self, name, type, size, model, serial_number, fs_type, mount_point):
                self.name = name
                self.type = type
                self.size = size
                self.used = None
                self.available = None
                self.children = []
                self.model = model
                self.serialNumber = serial_number
                self.fsType = fs_type
                self.mountPoint = mount_point
                self.partitionTable = None
                self.usedRatio = None
                self.mediaType = None
                self.smartPassed = None
                self.smartMessage = None

        def get_size_info(name):
            df_r, df_o = bash_ro('timeout 30 df %s' % name)
            if df_r != 0:
                return None, None, None
            used, available, usedRatio = None, None, None
            size_info = form.load(df_o)[0]
            if 'Used' in size_info.keys():
                used = long(size_info['Used']) * 1024
            if 'Available' in size_info.keys():
                available = long(size_info['Available']) * 1024
            if 'Use%' in size_info.keys():
                usedRatio = size_info['Use%'].replace('%', '')
            return used, available, usedRatio

        def get_smart_passed_and_message(name):
            smartPassed = None
            smartMessage = None
            _, status_o = bash_ro('timeout 30 smartctl -H %s -j' % name)
            if status_o is None or status_o == "":
                return smartPassed, smartMessage
            status_info = jsonobject.loads(status_o)
            if status_info['smartctl'] is not None:
                messages = status_info['smartctl']['messages']
                if messages is not None and messages[0] is not None:
                    smartMessage = "%s: %s" % (messages[0]['severity'], messages[0]['string'])

            if status_info['smart_status'] is not None:
                smartPassed = status_info['smart_status']['passed']

            if smartPassed is None or smartPassed == "":
                smartPassed = "true"

            return smartPassed, smartMessage

        def get_partition_table(name):
            partition_r, partition_o = bash_ro('timeout 30 parted -s %s print' % name)
            if partition_r != 0:
                return None
            return filter_lines_by_str_list(partition_o.splitlines(), ["Partition Table"])[0].split(':')[1].strip()

        def is_pcie_nvme(dev_name):
            transport = linux.read_file("/sys/class/block/%s/device/transport" % dev_name.replace("/dev/", ""))
            if transport:
                return transport.strip() == "pcie"
            return False

        def process_device(dev):
            name = dev['name']
            block_dev = BlockDevice(dev['name'], dev['type'], dev['size'], dev['model'], dev['serial'], dev['fstype'],
                                    dev['mountpoint'])
            if 'nvme' in name:
                block_dev.mediaType = 'SSD'
            else:
                block_dev.mediaType = 'SSD' if (dev['rota'] == '0' or dev['rota'] == False) else 'HDD'

            if dev['children'] is not None:
                for child in dev['children']:
                    child_dev = process_device(child)
                    block_dev.children.append(child_dev)

            block_dev.partitionTable = get_partition_table(name)
            block_dev.used, block_dev.available, block_dev.usedRatio = get_size_info(name)
            if not skip_get_smart_info(name):
                block_dev.smartPassed, block_dev.smartMessage = get_smart_passed_and_message(name)

            return block_dev

        r, o, e = bash_roe('lsblk -p -b -o NAME,TYPE,ROTA,SIZE,MOUNTPOINT,FSTYPE,SERIAL,MODEL -J')
        if r != 0:
            rsp.success = False
            rsp.error = e
            return jsonobject.dumps(rsp)

        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = [executor.submit(process_device, device)
                       for device in jsonobject.loads(o)['blockdevices']
                       if 'nvme' not in device['name'] or is_pcie_nvme(device['name'])]
            for future in as_completed(futures, timeout=60):
                try:
                    block_device = future.result()
                    if block_device:
                        rsp.blockDevices.append(block_device)
                except TimeoutError:
                    logger.warning("device processing timeout")

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def get_sensors(self, req):
        rsp = GetSensorsResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        class Sensor:
            def __init__(self, info):
                self.name = info['name'].strip() or ""
                self.value = info['value'].strip() or ""
                self.status = (info['event'] or '').strip().strip("'").lower()
                self.type = info['type'].strip() or ""

        if is_virtual_machine():
            rsp.success = False
            rsp.error = "the current environment does not support obtaining sensor information"
            return jsonobject.dumps(rsp)

        sensor_info = get_sensor_info_from_ipmi()
        if sensor_info is None:
            rsp.success = False
            rsp.error = "failed to get sensor info from ipmi"
            return jsonobject.dumps(rsp)

        sensors = []
        for info in form.load('id|name|type|value|units|event\n' + sensor_info, sep='|'):
            sensors.append(Sensor(info))
        rsp.sensors = sensors
        return jsonobject.dumps(rsp)

    def start(self):
        self.host_uuid = None
        self.host_socket = None

        http_server = kvmagent.get_http_server()
        http_server.register_sync_uri(self.CONNECT_PATH, self.connect)
        http_server.register_async_uri(self.PING_PATH, self.ping)
        http_server.register_async_uri(self.CHECK_FILE_ON_HOST_PATH, self.check_file_on_host)
        http_server.register_async_uri(self.CAPACITY_PATH, self.capacity)
        http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        http_server.register_async_uri(self.SETUP_MOUNTABLE_PRIMARY_STORAGE_HEARTBEAT, self.setup_heartbeat_file)
        http_server.register_async_uri(self.FACT_PATH, self.fact)
        http_server.register_async_uri(self.GET_USB_DEVICES_PATH, self.get_usb_devices)
        http_server.register_async_uri(self.UPDATE_OS_PATH, self.update_os)
        http_server.register_async_uri(self.INIT_HOST_MOC_PATH, self.init_host_moc)
        http_server.register_async_uri(self.UPDATE_DEPENDENCY, self.update_dependency)
        http_server.register_async_uri(self.ENABLE_HUGEPAGE, self.enable_hugepage)
        http_server.register_async_uri(self.DISABLE_HUGEPAGE, self.disable_hugepage)
        http_server.register_async_uri(self.CLEAN_LOCAL_CACHE, self.clean_local_cache)
        http_server.register_async_uri(self.HOST_START_USB_REDIRECT_PATH, self.start_usb_redirect_server)
        http_server.register_async_uri(self.HOST_STOP_USB_REDIRECT_PATH, self.stop_usb_redirect_server)
        http_server.register_async_uri(self.CHECK_USB_REDIRECT_PORT, self.check_usb_server_port)
        http_server.register_async_uri(self.IDENTIFY_HOST, self.identify_host)
        http_server.register_async_uri(self.LOCATE_HOST_NETWORK_INTERFACE, self.locate_host_network_interface)
        http_server.register_async_uri(self.GET_HOST_PHYSICAL_MEMORY_FACTS, self.get_host_physical_memory_facts)
        http_server.register_async_uri(self.GET_HOST_PHYSICAL_CPU_FACTS, self.get_host_physical_cpu_facts)
        http_server.register_async_uri(self.UPDATE_HOST_OVS_CPU_PINNING, self.update_ovs_cpu_pinning)
        http_server.register_async_uri(self.CHANGE_PASSWORD, self.change_password, cmd=ChangeHostPasswordCmd())
        http_server.register_async_uri(self.GET_HOST_NETWORK_FACTS, self.get_host_network_facts)
        http_server.register_async_uri(self.GET_HOST_BONDING_FACTS, self.get_host_bonding_facts)
        http_server.register_async_uri(self.SET_IP_ON_HOST_NETWORK_INTERFACE, self.set_ip_on_host_network_interface)
        http_server.register_async_uri(self.SET_SERVICE_TYPE_ON_HOST_NETWORK_INTERFACE, self.set_service_type_on_host_network_interface)
        http_server.register_async_uri(self.CHECK_INTERFACE_VLAN, self.check_interface_vlan)
        http_server.register_async_uri(self.GET_INTERFACE_VLAN, self.get_interface_vlan)
        http_server.register_async_uri(self.GET_INTERFACE_NAME, self.get_interface_name)
        http_server.register_async_uri(self.HOST_XFS_SCRAPE_PATH, self.get_xfs_frag_data)
        http_server.register_async_uri(self.HOST_SHUTDOWN, self.shutdown_host)
        http_server.register_async_uri(self.HOST_REBOOT, self.reboot_host)
        http_server.register_async_uri(self.GET_PCI_DEVICES, self.get_pci_info)
        http_server.register_async_uri(self.CREATE_PCI_DEVICE_ROM_FILE, self.create_pci_device_rom_file)
        http_server.register_async_uri(self.GENERATE_SRIOV_PCI_DEVICES, self.generate_sriov_pci_devices)
        http_server.register_async_uri(self.UNGENERATE_SRIOV_PCI_DEVICES, self.ungenerate_sriov_pci_devices)
        http_server.register_async_uri(self.GENERATE_VFIO_MDEV_DEVICES, self.generate_vfio_mdev_devices)
        http_server.register_async_uri(self.UNGENERATE_VFIO_MDEV_DEVICES, self.ungenerate_vfio_mdev_devices)
        http_server.register_async_uri(self.GET_MTTY_DEVICES, self.get_mtty_info)
        http_server.register_async_uri(self.GENERATE_SE_VFIO_MDEV_DEVICES, self.generate_se_vfio_mdev_devices)
        http_server.register_async_uri(self.UNGENERATE_SE_VFIO_MDEV_DEVICES, self.ungenerate_se_vfio_mdev_devices)
        http_server.register_async_uri(self.DELETE_VFIO_MDEV_DEVICE, self.delete_vfio_mdev_device)
        http_server.register_async_uri(self.HOST_UPDATE_SPICE_CHANNEL_CONFIG_PATH, self.update_spice_channel_config)
        http_server.register_async_uri(self.CANCEL_JOB, self.cancel)
        http_server.register_sync_uri(self.TRANSMIT_VM_OPERATION_TO_MN_PATH, self.transmit_vm_operation_to_vm)
        http_server.register_sync_uri(self.TRANSMIT_ZWATCH_INSTALL_RESULT_TO_MN_PATH, self.transmit_zwatch_install_result_to_mn)
        http_server.register_async_uri(self.SCAN_VM_PORT_PATH, self.scan_vm_port)
        http_server.register_async_uri(self.ENABLE_ZEROCOPY, self.enable_zerocopy)
        http_server.register_async_uri(self.DISABLE_ZEROCOPY, self.disable_zerocopy)
        http_server.register_async_uri(self.GET_DEV_CAPACITY, self.get_dev_capacity)
        http_server.register_async_uri(self.ADD_BRIDGE_FDB_ENTRY_PATH, self.add_bridge_fdb_entry)
        http_server.register_async_uri(self.DEL_BRIDGE_FDB_ENTRY_PATH, self.del_bridge_fdb_entry)
        http_server.register_async_uri(self.DEPLOY_COLO_QEMU_PATH, self.deploy_colo_qemu)
        http_server.register_async_uri(self.UPDATE_CONFIGURATION_PATH, self.update_host_configuration)
        http_server.register_async_uri(self.GET_NUMA_TOPOLOGY_PATH, self.get_numa_topology)
        http_server.register_async_uri(self.ATTACH_VOLUME_PATH, self.attach_volume_path)
        http_server.register_async_uri(self.DETACH_VOLUME_PATH, self.detach_volume__path)
        http_server.register_async_uri(self.GET_KERNEL_INTERFACE_PATH, self.get_kernel_interface)
        http_server.register_async_uri(self.SET_KERNEL_INTERFACE_PATH, self.set_kernel_interface)
        http_server.register_async_uri(self.GET_BLOCK_DEVICES_PATH, self.get_block_devices)
        http_server.register_async_uri(self.GET_SENSORS_PATH, self.get_sensors)
        http_server.register_async_uri(self.UPDATE_NQN_PATH, self.update_nqn)
        http_server.register_async_uri(self.UPDATE_HOSTNAME_PATH, self.update_hostname)
        http_server.register_async_uri(self.UPDATE_ISCSI_INITIATOR_NAME_PATH, self.update_iscsi_initiator_name)
        http_server.register_async_uri(self.KVM_HOST_FILE_DOWNLOAD_PATH, self.download_file)
        http_server.register_async_uri(self.FILE_UPLOAD_PATH, self.upload_file)
        http_server.register_raw_uri(self.FILE_DIRECT_UPLOAD_PATH, self.direct_upload_file)
        http_server.register_async_uri(self.FILE_UPLOAD_PROGRESS_PATH, self.get_upload_progress)
        http_server.register_async_uri(self.CREATE_ENVELOPE_KEY_PATH, self.create_envelope_key)
        http_server.register_async_uri(self.ROTATE_ENVELOPE_KEY_PATH, self.rotate_envelope_key)
        http_server.register_async_uri(self.GET_ENVELOPE_PUBLIC_KEY_PATH, self.get_envelope_public_key)
        http_server.register_async_uri(self.CHECK_ENVELOPE_KEY_PATH, self.check_envelope_key)
        http_server.register_async_uri(self.ENSURE_SECRET_PATH, self.ensure_secret)
        http_server.register_async_uri(self.WRITE_SECRET_MATERIAL_FILE_PATH, self.write_secret_material_file)
        http_server.register_async_uri(self.GET_SECRET_PATH, self.get_secret)
        http_server.register_async_uri(self.DELETE_SECRET_PATH, self.delete_secret)

        self.heartbeat_timer = {}
        filepath = r'/etc/libvirt/qemu/networks/autostart/default.xml'
        if os.path.exists(filepath):
            os.unlink(filepath)

        self.upload_tasks = UploadTasks()

    def stop(self):
        if self.host_socket is not None:
            self.host_socket.close()

        pass

    def configure(self, config={}):
        self.config = config
