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

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import http
from zstacklib.utils import qemu
from zstacklib.utils import linux
from zstacklib.utils import iptables
from zstacklib.utils import iproute
from zstacklib.utils import ebtables
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import sizeunit
from zstacklib.utils import thread
from zstacklib.utils import xmlobject
from zstacklib.utils import ovs
from zstacklib.utils.bash import *
from zstacklib.utils.ip import get_nic_supported_max_speed
from zstacklib.utils.ip import get_nic_driver_type
from zstacklib.utils.report import Report
import zstacklib.utils.ip as ip
import zstacklib.utils.plugin as plugin

host_arch = platform.machine()
IS_AARCH64 = host_arch == 'aarch64'
IS_MIPS64EL = host_arch == 'mips64el'
IS_LOONGARCH64 = host_arch == 'loongarch64'
GRUB_FILES = ["/boot/grub2/grub.cfg", "/boot/grub/grub.cfg", "/etc/grub2-efi.cfg", "/etc/grub-efi.cfg"] \
                + ["/boot/efi/EFI/{}/grub.cfg".format(platform.dist()[0])]
IPTABLES_CMD = iptables.get_iptables_cmd()
EBTABLES_CMD = ebtables.get_ebtables_cmd()

COLO_QEMU_KVM_VERSION = '/var/lib/zstack/colo/qemu_kvm_version'
COLO_LIB_PATH = '/var/lib/zstack/colo/'
HOST_TAKEOVER_FLAG_PATH = 'var/run/zstack/takeOver'
NODE_INFO_PATH = '/sys/devices/system/node/'

BOND_MODE_ACTIVE_0 = "balance-rr"
BOND_MODE_ACTIVE_1 = "active-backup"
BOND_MODE_ACTIVE_2 = "balance-xor"
BOND_MODE_ACTIVE_3 = "broadcast"
BOND_MODE_ACTIVE_4 = "802.3ad"
BOND_MODE_ACTIVE_5 = "balance-tlb"
BOND_MODE_ACTIVE_6 = "balance-alb"

class ConnectResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ConnectResponse, self).__init__()
        self.iptablesSucc = None

class HostCapacityResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(HostCapacityResponse, self).__init__()
        self.cpuNum = None
        self.cpuSpeed = None
        self.usedCpu = None
        self.totalMemory = None
        self.usedMemory = None
        self.cpuSockets = None

class HostFactResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(HostFactResponse, self).__init__()
        self.osDistribution = None
        self.osVersion = None
        self.osRelease = None
        self.qemuImgVersion = None
        self.libvirtVersion = None
        self.hvmCpuFlag = None
        self.cpuModelName = None
        self.systemSerialNumber = None
        self.eptFlag = None
        self.libvirtCapabilities = []

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


class GetHostNetworkBongdingResponse(kvmagent.AgentResponse):
    bondings = None  # type: list[HostNetworkBondingInventory]
    nics = None  # type: list[HostNetworkInterfaceInventory]

    def __init__(self):
        super(GetHostNetworkBongdingResponse, self).__init__()
        self.bondings = None
        self.nics = None


class HostNetworkBondingInventory(object):
    slaves = None  # type: list(HostNetworkInterfaceInventory)

    def __init__(self, bondingName=None):
        super(HostNetworkBondingInventory, self).__init__()
        self.bondingName = bondingName
        self.mode = None
        self.xmitHashPolicy = None
        self.miiStatus = None
        self.mac = None
        self.ipAddresses = None
        self.miimon = None
        self.allSlavesActive = None
        self.slaves = None
        self._init_from_name()

    def _init_from_name(self):
        def get_nic(n, i):
            o = HostNetworkInterfaceInventory(n)
            self.slaves[i] = o

        if self.bondingName is None:
            return
        self.mode = linux.read_file_strip("/sys/class/net/%s/bonding/mode" % self.bondingName)
        self.xmitHashPolicy = linux.read_file_strip("/sys/class/net/%s/bonding/xmit_hash_policy" % self.bondingName)
        self.miiStatus = linux.read_file_strip("/sys/class/net/%s/bonding/mii_status" % self.bondingName)
        self.mac = linux.read_file_strip("/sys/class/net/%s/address" % self.bondingName)
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

    def _to_dict(self):
        to_dict = self.__dict__
        for k in to_dict.keys():
            if k == "slaves":
                v = copy.deepcopy(to_dict[k])
                to_dict[k] = [i.__dict__ for i in v]
        return to_dict


class HostNetworkInterfaceInventory(object):
    __cache__ = dict()  # type: dict[str, list[int, HostNetworkInterfaceInventory]]

    def init(self, name):
        super(HostNetworkInterfaceInventory, self).__init__()
        self.interfaceName = name
        self.speed = None
        self.slaveActive = None
        self.carrierActive = None
        self.mac = None
        self.ipAddresses = None
        self.interfaceType = None
        self.master = None
        self.pciDeviceAddress = None
        self.offloadStatus = None
        self.driverType = None
        self._init_from_name()

    @classmethod
    def __get_cache__(cls, name):
        # type: (str) -> HostNetworkInterfaceInventory
        c = cls.__cache__.get(name)
        if c is None:
            return None
        if (time.time() - c[0]) < 60:
            c[1]._updateActiveState()
            return c[1]
        return None

    def __new__(cls, name, *args, **kwargs):
        o = cls.__get_cache__(name)
        if o:
            return o
        o = super(HostNetworkInterfaceInventory, cls).__new__(cls)
        o.init(name)
        cls.__cache__[name] = [int(time.time()), o]
        return o

    def _updateActiveState(self):
        if self.interfaceType == "bondingSlave":
            activeSlave = linux.read_file("/sys/class/net/%s/bonding/active_slave" % self.master)
            self.slaveActive = self.interfaceName in activeSlave if activeSlave is not None else None

    @in_bash
    def _init_from_name(self):
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
        self.offloadStatus = ovs.OvsCtl().ifOffloadStatus(self.interfaceName)
        self.driverType = get_nic_driver_type(self.interfaceName)

    def _to_dict(self):
        to_dict = self.__dict__
        return to_dict

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

class PciDeviceTO(object):
    def __init__(self):
        self.name = ""
        self.description = ""
        self.vendorId = ""
        self.deviceId = ""
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
        for grub_path in GRUB_FILES:
            content = linux.read_file(grub_path)
            if content is not None:
                content = re.sub('{0}\s*=\s*on'.format(self.iommu_type), '', content)
                content = re.sub('{0}\s*=\s*off'.format(self.iommu_type), '', content)
                content = re.sub('\s*modprobe.blacklist\s*=\s*\S*', '', content)
                if self.enableIommu:
                    content = re.sub(r'(/vmlinuz-.*)', r'\1 {0}=on modprobe.blacklist=snd_hda_intel,amd76x_edac,vga16fb,nouveau,rivafb,nvidiafb,rivatv,amdgpu,radeon'.format(self.iommu_type), content)
                linux.write_file(grub_path, content)
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
    LOCATE_HOST_NETWORK_INTERFACE = "/host/locate/networkinterface";
    GET_HOST_PHYSICAL_MEMORY_FACTS = "/host/physicalmemoryfacts";
    CHANGE_PASSWORD = "/host/changepassword"
    GET_HOST_NETWORK_FACTS = "/host/networkfacts"
    HOST_XFS_SCRAPE_PATH = "/host/xfs/scrape"
    HOST_SHUTDOWN = "/host/shutdown"
    GET_PCI_DEVICES = "/pcidevice/get"
    CREATE_PCI_DEVICE_ROM_FILE = "/pcidevice/createrom"
    GENERATE_SRIOV_PCI_DEVICES = "/pcidevice/generate"
    UNGENERATE_SRIOV_PCI_DEVICES = "/pcidevice/ungenerate"
    GENERATE_VFIO_MDEV_DEVICES = "/mdevdevice/generate"
    UNGENERATE_VFIO_MDEV_DEVICES = "/mdevdevice/ungenerate"
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

    host_network_facts_cache = {}  # type: dict[float, list[list, list]]
    cpu_sockets = 0

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
        apply_iptables_result = self.apply_iptables_rules(cmd.iptablesRules)
        rsp.iptablesSucc = apply_iptables_result

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

    @kvmagent.replyerror
    def fact(self, req):
        rsp = HostFactResponse()
        rsp.osDistribution, rsp.osVersion, rsp.osRelease = platform.dist()
        rsp.osRelease = rsp.osRelease if rsp.osRelease else "Core"
        # compatible with Kylin SP2 HostOS ISO and standardized ISO
        rsp.osRelease = "Sword" if rsp.osDistribution == "kylin" and host_arch in ["x86_64", "aarch64"] else rsp.osRelease
        # to be compatible with both `2.6.0` and `2.9.0(qemu-kvm-ev-2.9.0-16.el7_4.8.1)`
        qemu_img_version = shell.call("qemu-img --version | grep 'qemu-img version' | cut -d ' ' -f 3 | cut -d '(' -f 1")
        qemu_img_version = qemu_img_version.strip('\t\r\n ,')
        ipV4Addrs = [chunk.address for chunk in filter(
            lambda x: x.address != '127.0.0.1' and not x.ifname.endswith('zs'), iproute.query_addresses(ip_version=4))]
        rsp.systemProductName = 'unknown'
        rsp.systemSerialNumber = 'unknown'
        rsp.systemManufacturer = 'unknown'
        rsp.systemUUID = 'unknown'
        rsp.biosVendor = 'unknown'
        rsp.biosVersion = 'unknown'
        rsp.biosReleaseDate = 'unknown'
        is_dmidecode = shell.run("dmidecode")
        if str(is_dmidecode) == '0':
            system_product_name = shell.call('dmidecode -s system-product-name').strip()
            baseboard_product_name = shell.call('dmidecode -s baseboard-product-name').strip()
            system_serial_number = shell.call('dmidecode -s system-serial-number').strip()
            system_manufacturer = shell.call('dmidecode -s system-manufacturer').strip()
            system_uuid = shell.call('dmidecode -s system-uuid').strip()
            bios_vendor = shell.call('dmidecode -s bios-vendor').strip()
            bios_version = shell.call('dmidecode -s bios-version').strip()
            bios_release_date = shell.call('dmidecode -s bios-release-date').strip()
            rsp.systemSerialNumber = system_serial_number if system_serial_number else 'unknown'
            rsp.systemProductName = system_product_name if system_product_name else baseboard_product_name
            rsp.systemManufacturer = system_manufacturer if system_manufacturer else 'unknown'
            rsp.systemUUID = system_uuid if system_uuid else 'unknown'
            rsp.biosVendor = bios_vendor if bios_vendor else 'unknown'
            rsp.biosVersion = bios_version if bios_version else 'unknown'
            rsp.biosReleaseDate = bios_release_date if bios_release_date else 'unknown'
            memory_slots_maximum = shell.call('dmidecode -q -t memory | grep "Memory Device" | wc -l')
            rsp.memorySlotsMaximum = memory_slots_maximum.strip()
            # power not in presence cannot collect power info
            power_supply_manufacturer = shell.call("dmidecode -t 39 | grep -vi 'not specified' | grep -m1 'Manufacturer' | awk -F ':' '{print $2}'").strip()
            rsp.powerSupplyManufacturer = power_supply_manufacturer if power_supply_manufacturer != "" else "unknown"
            power_supply_model_name = shell.call("dmidecode -t 39 | grep -vi 'not specified' | grep -m1 'Name' | awk -F ':' '{print $2}'").strip()
            rsp.powerSupplyModelName = power_supply_model_name if power_supply_model_name != "" else "unknown"
            power_supply_max_power_capacity = shell.call("dmidecode -t 39 | grep -vi 'unknown' | grep -m1 'Max Power Capacity' | awk -F ':' '{print $2}'")
            if bool(re.search(r'\d', power_supply_max_power_capacity)):
                rsp.powerSupplyMaxPowerCapacity = filter(str.isdigit, power_supply_max_power_capacity.strip())

        rsp.qemuImgVersion = qemu_img_version
        rsp.libvirtVersion = self.libvirt_version
        rsp.ipAddresses = ipV4Addrs
        rsp.cpuArchitecture = platform.machine()
        rsp.uptime = shell.call('uptime -s').strip()

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
            cpu_threads_per_core = shell.call("lscpu | awk -F':' '/per core/{print $NF}'")
            rsp.cpuProcessorNum = int(cpu_cores_per_socket.strip()) * int(cpu_threads_per_core)

            '''
            examples:         
                    lscpu | grep 'L1i cache'
                    L1i cache:                       768 KiB
                    lscpu | grep 'L1d cache'
                    L1d cache:                       768 KiB
            '''

            cpu_cache_list = self._get_cpu_cache()
            rsp.cpuCache = ",".join(str(cache) for cache in cpu_cache_list)

        elif IS_MIPS64EL:
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
            cpu_threads_per_core = shell.call("lscpu | awk -F':' '/per core/{print $NF}'")
            rsp.cpuProcessorNum = int(cpu_cores_per_socket.strip()) * int(cpu_threads_per_core)

            cpu_cache_list = self._get_cpu_cache()
            rsp.cpuCache = ",".join(str(cache) for cache in cpu_cache_list)
            
        return jsonobject.dumps(rsp)

    @vm_plugin.LibvirtAutoReconnect
    def _get_features_in_libvirt(conn):
        try:
            xml_object = xmlobject.loads(conn.getCapabilities())
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

        if HostPlugin.cpu_sockets < 1:
            sockets = len(bash_o('grep "physical id" /proc/cpuinfo | sort -u').splitlines())
            HostPlugin.cpu_sockets = sockets if sockets > 0 else 1

        rsp.cpuSockets = HostPlugin.cpu_sockets

        ret = jsonobject.dumps(rsp)
        logger.debug('get host capacity: %s' % ret)
        return ret

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
                ret, output = bash_ro("systemd-run --unit %s usbredirserver -p %s %s-%s" % (systemd_service_name, port, busNum, devNum))
                if ret != 0:
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

        def _add_usb_device_info(info, usb_device_infos, dev_id):
            if info.busNum == '' or info.devNum == '' or info.idVendor == '' or info.idProduct == '':
                logger.debug("cannot get busNum/devNum/idVendor/idProduct info in usbDevice %s" % dev_id)
            elif '(error)' in info.iManufacturer or '(error)' in info.iProduct:
                logger.debug("cannot get iManufacturer or iProduct info in usbDevice %s" % dev_id)
                usb_device_infos += info.toString()
            else:
                usb_device_infos += info.toString()

            return usb_device_infos

        # use 'lsusb.py -U' to get device ID, like '0751:9842'
        rsp = GetUsbDevicesRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        r, o, e = bash_roe("timeout 5 lsusb.py -U")
        if r != 0:
            rsp.success = False
            rsp.error = "%s %s" % (e, o)
            return jsonobject.dumps(rsp)

        id_set = set()
        usb_device_infos = ''
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
                    rst = bash_r("lsusb.py | grep -v 'grep' | grep '%s' | grep -E '1.5MBit/s|12MBit/s'" % dev_id)
                    info.usbVersion = info.usbVersion if rst != 0 else '1.1'
                elif line[0] == 'iManufacturer' and len(line) > 2:
                    info.iManufacturer = ' '.join(line[2:])
                elif line[0] == 'iProduct' and len(line) > 2:
                    info.iProduct = ' '.join(line[2:])
                elif line[0] == 'iSerial':
                    info.iSerial = ' '.join(line[2:]) if len(line) > 2 else ""
                    usb_device_infos = _add_usb_device_info(info, usb_device_infos, dev_id)

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
        yum_cmd = "export YUM0={};yum --enablerepo=* clean all && yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn{} {} update {} -y"
        yum_cmd = yum_cmd.format(releasever, ',zstack-experimental-mn' if cmd.enableExpRepo else '', exclude, updates)
        #support update qemu-kvm and update OS
        if releasever in ['c74', 'c76'] and "qemu-kvm" in updates or cmd.releaseVersion is not None:
            update_qemu_cmd = "export YUM0={};yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn  swap -y -- remove qemu-img-ev -- install qemu-img " \
                              "&& yum remove qemu-kvm-ev qemu-kvm-common-ev -y && yum --disablerepo=* --enablerepo=zstack-mn,qemu-kvm-ev-mn install qemu-kvm qemu-kvm-common -y && "
            yum_cmd = update_qemu_cmd.format(releasever) + yum_cmd

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
        elif shell.run(yum_cmd) != 0:
            rsp.success = False
            rsp.error = "failed to update host os using zstack-mn,qemu-kvm-ev-mn repo"
        else:
            logger.debug("successfully run: %s" % yum_cmd)
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

    @thread.AsyncThread
    def do_shutdown_host(self):
        logger.debug("It is going to shutdown host after 1 sec")
        time.sleep(1)
        shell.call("sudo init 0")

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

#clean boot grub config
for var in $grubs 
do 
   if [ -f $var ]; then
       sed -i '/^[[:space:]]*linux/s/[[:blank:]]*default_[[:graph:]]*//g' $var
       sed -i '/^[[:space:]]*linux/s/[[:blank:]]*hugepagesz[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' $var
       sed -i '/^[[:space:]]*linux/s/[[:blank:]]*hugepages[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' $var
       sed -i '/^[[:space:]]*linux/s/[[:blank:]]*transparent_hugepage[[:blank:]]*=[[:blank:]]*[[:graph:]]*//g' $var
   fi    
done
''' % (' '.join(GRUB_FILES))
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
''' % (' '.join(GRUB_FILES), reserveSize, pageSize)

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
        # Fibre port not support command: ethtool --identify ethxx
        r = bash_r("ethtool %s | grep 'Supported ports' | grep 'FIBRE'" % cmd.networkInterface)
        if r == 0:
            sc = shell.ShellCmd("ethtool --test %s" % cmd.networkInterface)
            sc(False)
        else:
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
                elif "configured clock speed" == k:
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
    def get_host_network_facts(self, req):
        rsp = GetHostNetworkBongdingResponse()
        cache = HostPlugin.__get_cache__()
        if cache is not None:
            rsp.bondings = cache[0]
            rsp.nics = cache[1]
            return jsonobject.dumps(rsp)

        rsp.bondings = self.get_host_networking_bonds()
        rsp.nics = self.get_host_networking_interfaces()

        HostPlugin.__store_cache__(rsp.bondings, rsp.nics)
        return jsonobject.dumps(rsp)

    @classmethod
    def __get_cache__(cls):
        # type: () -> (list, list)
        keys = cls.host_network_facts_cache.keys()
        if keys is None or len(keys) == 0:
            return None
        if (time.time() - keys[0]) < 10:
            return cls.host_network_facts_cache.get(keys[0])
        return None

    @classmethod
    def __store_cache__(cls, bonds, nics):
        # type: (list, list) -> None
        cls.host_network_facts_cache.clear()
        cls.host_network_facts_cache.update({time.time(): [bonds, nics]})

    @staticmethod
    def get_host_networking_interfaces():
        nics = []

        def get_nic(n, i):
            o = HostNetworkInterfaceInventory(n)
            nics[i] = o

        threads = []
        nic_names = ip.get_host_physicl_nics()
        if len(nic_names) == 0:
            return nics

        nics = [None] * len(nic_names)
        for idx, nic in enumerate(nic_names, start=0):
            threads.append(thread.ThreadFacade.run_in_thread(get_nic, [nic.strip(), idx]))
        for t in threads:
            t.join()
        return nics

    @staticmethod
    def get_host_networking_bonds():
        bonds = []
        bond_names = linux.read_file("/sys/class/net/bonding_masters")
        if not bond_names:
            return bonds
        bond_names = bond_names.strip().split(" ")
        if len(bond_names) == 0:
            return bonds
        for bond in bond_names:
            bonds.append(HostNetworkBondingInventory(bond))
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
            if to.type in ('GPU_3D_Controller', 'GPU_Video_Controller') and self.NVIDIA_SMI_INSTALLED and os.path.exists(virtfn):
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
        else:
            return name.replace('Co., Ltd ', '')

    def _collect_format_pci_device_info(self, rsp):
        r, o, e = bash_roe("lspci -Dmmnnv")
        if r != 0:
            rsp.success = False
            rsp.error = "%s, %s" % (e, o)
            return

        # parse lspci output
        for part in o.split('\n\n'):
            vendor_name = ""
            device_name = ""
            subvendor_name = ""
            to = PciDeviceTO()
            for line in part.split('\n'):
                if len(line.split(':')) < 2: continue
                title = line.split(':')[0].strip()
                content = line.split(':')[1].strip()
                if title == 'Slot':
                    content = line[5:].strip()
                    to.pciDeviceAddress = content
                    group_path = os.path.join('/sys/bus/pci/devices/', to.pciDeviceAddress, 'iommu_group')
                    to.iommuGroup = os.path.realpath(group_path)
                elif title == 'Class':
                    _class = content.split('[')[0].strip()
                    to.type = _class
                    to.description = _class + ": "
                elif title == 'Vendor':
                    vendor_name = self._simplify_pci_device_name('['.join(content.split('[')[:-1]).strip())
                    to.vendorId = content.split('[')[-1].strip(']')
                    to.description += vendor_name + " "
                elif title == "Device":
                    device_name = self._simplify_pci_device_name('['.join(content.split('[')[:-1]).strip())
                    to.deviceId = content.split('[')[-1].strip(']')
                    to.description += device_name
                elif title == "SVendor":
                    subvendor_name = self._simplify_pci_device_name('['.join(content.split('[')[:-1]).strip())
                    to.subvendorId = content.split('[')[-1].strip(']')
                elif title == "SDevice":
                    to.subdeviceId = content.split('[')[-1].strip(']')
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
                elif 'Moxa Technologies' in to.type:
                    to.type = "Moxa_Device"
                elif 'Host bridge' in to.type:
                    to.type = "Host_Bridge"
                elif 'PCI bridge' in to.type:
                    to.type = "PCI_Bridge"
                else:
                    to.type = "Generic"

            _set_pci_to_type()

            # if support both mdev and sriov, then set the pci device to VFIO_MDEV_VIRTUALIZABLE
            if not self._get_vfio_mdev_info(to) and not self._get_sriov_info(to):
                to.virtStatus = "UNVIRTUALIZABLE"
            if to.vendorId != '' and to.deviceId != '':
                rsp.pciDevicesInfo.append(to)

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

        if cmd.pciDeviceType == 'GPU_Video_Controller' or cmd.pciDeviceType == 'GPU_3D_Controller':
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

        if cmd.pciDeviceType == 'GPU_Video_Controller' or cmd.pciDeviceType == 'GPU_3D_Controller':
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

        shell.call('systemctl restart libvirtd')
        rsp.restartLibvirt = True
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
        http_server.register_async_uri(self.LOCATE_HOST_NETWORK_INTERFACE,self.locate_host_network_interface)
        http_server.register_async_uri(self.GET_HOST_PHYSICAL_MEMORY_FACTS,self.get_host_physical_memory_facts)
        http_server.register_async_uri(self.CHANGE_PASSWORD, self.change_password, cmd=ChangeHostPasswordCmd())
        http_server.register_async_uri(self.GET_HOST_NETWORK_FACTS, self.get_host_network_facts)
        http_server.register_async_uri(self.HOST_XFS_SCRAPE_PATH, self.get_xfs_frag_data)
        http_server.register_async_uri(self.HOST_SHUTDOWN, self.shutdown_host)
        http_server.register_async_uri(self.GET_PCI_DEVICES, self.get_pci_info)
        http_server.register_async_uri(self.CREATE_PCI_DEVICE_ROM_FILE, self.create_pci_device_rom_file)
        http_server.register_async_uri(self.GENERATE_SRIOV_PCI_DEVICES, self.generate_sriov_pci_devices)
        http_server.register_async_uri(self.UNGENERATE_SRIOV_PCI_DEVICES, self.ungenerate_sriov_pci_devices)
        http_server.register_async_uri(self.GENERATE_VFIO_MDEV_DEVICES, self.generate_vfio_mdev_devices)
        http_server.register_async_uri(self.UNGENERATE_VFIO_MDEV_DEVICES, self.ungenerate_vfio_mdev_devices)
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

        self.heartbeat_timer = {}
        self.libvirt_version = linux.get_libvirt_version()
        self.qemu_version = qemu.get_version()
        filepath = r'/etc/libvirt/qemu/networks/autostart/default.xml'
        if os.path.exists(filepath):
            os.unlink(filepath)

    def stop(self):
        if self.host_socket is not None:
            self.host_socket.close()

        pass

    def configure(self, config):
        self.config = config
