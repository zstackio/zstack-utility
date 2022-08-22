import unittest
from kvmagent.plugins import network_plugin
from kvmagent.plugins import vm_plugin
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import uuidhelper
from kvmagent.plugins import ovsdpdk_network
from zstacklib.utils import linux
from zstacklib.utils import jsonobject
from zstacklib.utils import bash
from zstacklib.utils import ovs
import time
import pytest

class Test_VmOperate_L2OvsDpdk():
    ofed_not_exsit = True

    @classmethod
    def setup_class(self):
        ret, _ = bash.bash_ro("ofed_info -l")
        if ret == 0:
            ofed_not_exsit = False
        else:
            return

        ret, _ = bash.bash_ro("lspci |grep -i eth|grep -i Mellanox")
        if ret == 0:
            ofed_not_exsit = False
        else:
            return

        self.NET_PLUGIN = network_plugin.NetworkPlugin()
        self.NET_PLUGIN.configure()

        self.DPDK_PLUGIN = ovsdpdk_network.OvsDpdkNetworkPlugin()
        self.DPDK_PLUGIN.configure()

        self.VM_PLUGIN = vm_plugin.VmPlugin()


    def test_startvm(self):
        #create ovs bridge
        cmd = ovsdpdk_network.CreateBridgeCmd()
        cmd.bridgeName = "br_enp101s0f0"
        cmd.physicalInterfaceName = "enp101s0f0"

        ## delete bridge manually
        ovsctl = ovs.getOvsCtl(with_dpdk=True)
        #if cmd.bridgeName in ovsctl.listBrs():
            #ovsctl.deleteBr(cmd.bridgeName)

        self.DPDK_PLUGIN.create_ovs_bridge(({"body": jsonobject.dumps(cmd)}))

        #start vm
        cmd = vm_plugin.StartVmCmd()
        cmd.vmName = 'test'
        cmd.vmInstanceUuid = "229lka53b2bd404ebae63d69c255555"
        cmd.imagePlatform = "Linux"
        cmd.vmInternalId = 391
        cmd.imageArchitecture = "x86_64"
        cmd.cpuNum = 2
        cmd.cpuSpeed = 0
        cmd.memory = 2147483648
        cmd.maxMemory = 6702710784
        cmd.socketNum = 1
        cmd.cpuOnSocket = 2
        cmd.bootDev = ["hd"]
        rootVolume = Volume()
        rootVolume.installPath = "/cloud_ps/rootVolumes/acct-36c27e8ff05c4780bf6d2fa65700f22e/vol-c58b7a53b2bd404ebae63d69c2207d38/c58b7a53b2bd404ebae63d69c2207d38.qcow2"
        rootVolume.deviceId = 0
        rootVolume.deviceType = "file"
        rootVolume.volumeUuid = "c58b7a53b2bd404ebae63d69c2207d38"
        rootVolume.useVirtio = True
        rootVolume.useVirtioSCSI = False
        rootVolume.shareable = False
        rootVolume.cacheMode = "none"
        rootVolume.wwn = "0x000f2517a55862a9"
        rootVolume.bootOrder = 1
        rootVolume.physicalBlockSize = 0
        cmd.rootVolume = rootVolume
        cmd.bootIso = []

        cdrom = CdRom()
        cdrom.deviceId = 0
        cdrom.isEmpty = True
        cdrom.bootOrder = 0
        cmd.cdRoms = [cdrom]

        cmd.dataVolumes = []
        cmd.cacheVolumes = []

        cmd.timeout = 300

        nics = vm_plugin.NicTO()
        # interface info
        nics.mac = "fa:46:e8:1b:ab:00"
        # last step create the ovs bridge
        nics.bridgeName = "br_enp101s0f0"
        nics.uuid = "886203c1c7dd462cbf91970841df121d"
        nics.nicInternalName = "vnic390.0"
        nics.deviceId = 2
        nics.useVirtio = True
        nics.bootOrder = 0
        nics.mtu = 1500
        nics.type = "vDPA"
        nics.vHostAddOn = vHostAddOn()
        nics.physicalInterface = "enp101s0f0"
        nics.pciDeviceAddress = "0000:65:00.3"
        cmd.nics = [nics]

        addon = Addon()
        channel = Channel()
        channel.socketPath = "/var/lib/libvirt/qemu/365242a14243442b9a22d8b00af82ac5"
        channel.targetName = "org.qemu.guest_agent.0"
        addon.channel = channel
        cmd.addons = addon

        cmd.instanceOfferingOnlineChange = False
        cmd.nestedVirtualization = "none"
        cmd.hostManagementIp = "172.25.102.128"
        cmd.clock = "utc"
        cmd.useBootMenu = True
        cmd.createPaused = False
        cmd.kvmHiddenState = False
        cmd.vmPortOff = False
        cmd.emulateHyperV = False
        cmd.vendorId = "Microsoft Hv"
        cmd.additionalQmp = True
        cmd.isApplianceVm = False
        cmd.systemSerialNumber = "6c00c26e-a14f-424f-952d-9b1f29a3f9ae"
        cmd.bootMode = "Legacy"
        cmd.fromForeignHypervisor = False
        cmd.machineType = "pc"
        cmd.useHugePage = False
        cmd.chassisAssetTag = "www.zstack.io"
        cmd.MemAccess = "shared"
        cmd.useNuma = True

        cmd.priorityConfigStruct = PriorityConfigStruct
        cmd.priorityConfigStruct.vmUuid = "229lka53b2bd404ebae63d69c255555"
        cmd.priorityConfigStruct.cpuShares = 512
        cmd.priorityConfigStruct.oomScoreAdj = 0

        cmd.coloPrimary = False
        cmd.coloSecondary = False
        cmd.consoleLogToFile = False
        cmd.acpi = False
        cmd.hygonCpu = False
        cmd.useColoBinary = False
        cmd.consoleMode = "vnc"
        cmd.videoType = "cirrus"
        cmd.spiceStreamingMode = "off"
        cmd.VDIMonitorNumber = 1
        cmd.kvmHostAddons = kvmHostAddons()
        cmd.kvmHostAddons.qcow2Options = "-o cluster_size=2097152"

        self.VM_PLUGIN.start_vm(({"body": jsonobject.dumps(cmd)}))



class Volume():

    def __init__(self):
        self.installPath = None
        self.deviceType = None
        self.volumeUuid = None
        self.useVirtio = None
        self.useVirtioSCSI = None
        self.shareable = None
        self.cacheMode = None
        self.wwn = None
        self.bootOrder = None
        self.physicalBlockSize = None

class Addon():
    def __init__(self):
        self.channel = None
        self.numaNodes = None
        self.usbDevice = []

class Channel():
    def __init__(self):
        self.socketPath = None
        self.targetName = None


class PriorityConfigStruct():
    def __init__(self):
        self.vmUuid = None
        self.cpuShares = None
        self.oomScoreAdj = None


class vHostAddOn():
    def __init__(self):
        self.queueNum = None

class CdRom():
    def __init__(self):
        self.deviceId = None
        self.isEmpty = True
        self.bootOrder = 0


class kvmHostAddons():
    def __init__(self):
        self.qcow2Options = None