'''
@author: Frank
'''
import contextlib
import difflib
import os.path
import string
import glob
import tempfile
import time
import datetime
import traceback
import xml.etree.ElementTree as etree
import re
import platform
import netaddr
import uuid
import shutil
import simplejson
import base64
import uuid
import urlparse
import json
import socket
from signal import SIGKILL
import syslog
import threading

import libvirt
import xml.dom.minidom as minidom
#from typing import List, Any, Union
from distutils.version import LooseVersion
from collections import Counter
from collections import deque

import zstacklib.utils.ip as ip
import zstacklib.utils.ebtables as ebtables
import zstacklib.utils.iptables as iptables
import zstacklib.utils.lock as lock

from jinja2 import Template
from kvmagent import kvmagent
from kvmagent.plugins.baremetal_v2_gateway_agent import \
    BaremetalV2GatewayAgentPlugin as BmV2GwAgent
from kvmagent.plugins.bmv2_gateway_agent import utils as bm_utils
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import bash, plugin, iscsi
from zstacklib.utils.bash import in_bash
from zstacklib.utils import lvm
from zstacklib.utils import ft
from zstacklib.utils import shell
from zstacklib.utils import uuidhelper
from zstacklib.utils import xmlobject
from zstacklib.utils import xmlhook
from zstacklib.utils import misc
from zstacklib.utils import qemu_img, qemu, qmp
from zstacklib.utils import ebtables
from zstacklib.utils import vm_operator
from zstacklib.utils import pci
from zstacklib.utils import image
from zstacklib.utils import iproute
from zstacklib.utils import ovs
from zstacklib.utils import drbd
from zstacklib.utils.jsonobject import JsonObject
from zstacklib.utils.qga import *
from zstacklib.utils import jsonobject
from zstacklib.utils.qmp import get_block_node_name_and_file, QmpResult
from zstacklib.utils.report import *
from zstacklib.utils.vm_plugin_queue_singleton import VmPluginQueueSingleton
from zstacklib.utils.libvirt_singleton import LibvirtEventManager
from zstacklib.utils.libvirt_singleton import LibvirtEventManagerSingleton
from zstacklib.utils.libvirt_singleton import LibvirtSingleton

logger = log.get_logger(__name__)

HOST_ARCH = platform.machine()
DIST = platform.dist()
DIST_NAME = DIST[0]
DIST_NAME_VERSION = "%s%s" % (DIST[0], DIST[1])

ZS_XML_NAMESPACE = 'http://zstack.org'

etree.register_namespace('zs', ZS_XML_NAMESPACE)

GUEST_TOOLS_ISO_PATH = "/var/lib/zstack/guesttools/GuestTools.iso"
GUEST_TOOLS_ISO_LINUX_PATH = "/var/lib/zstack/guesttools/GuestTools_linux.iso"

VM_CORE_DUMP_DIR = "/var/lib/zstack/kvmcoredump"

SYSTEM_VIRTIO_DRIVER_PATHS = {
    'VFD_X86' : '/var/lib/zstack/virtio-drivers/virtio-win_x86.vfd',
    'VFD_AMD64' : '/var/lib/zstack/virtio-drivers/virtio-win_amd64.vfd'
}
QMP_SOCKET_PATH = "/var/lib/libvirt/qemu/zstack"
PCI_ROM_PATH = "/var/lib/zstack/pcirom"
MAX_MEMORY = 34359738368 if (HOST_ARCH != "aarch64") else linux.get_max_vm_ipa_size()/1024/16

MIPS64EL_CPU_MODEL = "Loongson-3A4000-COMP"
LOONGARCH64_CPU_MODEL = "Loongson-3A5000"

LINUX_SCRIPT_LIB_PATH = "/var/lib/zstack/script/"
WINDOWS_SCRIPT_LIB_PATH = "C:/Program Files/Qemu-ga/script/"

DEFAULT_ZBS_CONF_PATH = "/etc/zbs/client.conf"
DEFAULT_ZBS_USER_NAME = "zbs"
PROTOCOL_CBD_PREFIX = "cbd:"


class RetryException(Exception):
    pass


# vm memory stat in bytes
class DomainMemoryStats(object):
    def __init__(self):
        self.max = None
        self.swap_out = None
        self.swap_in = None
        self.available = None
        self.usable = None
        self.actual = None
        self.unused = None
        self.major_fault = None
        self.minor_fault = None
        self.last_update = None
        self.rss = None


class NicTO(object):
    def __init__(self):
        self.mac = None
        self.bridgeName = None
        self.deviceId = None


class DomainVolume(object):
    def __init__(self):
        self.type = ''
        self.source = ''
        self.source_type =''
        self.driver_type = ''
        self.backing_store = None
        self.deviceType = ''
        self.disk_device = ''

        self._origin_xml_obj = None

    @classmethod
    def from_xmlobject(cls, xml_obj):
        ret = cls()
        ret._origin_xml_obj = xml_obj
        ret.type = xml_obj.attrib['type']
        ret.deviceType = ret.type
        ret.disk_device = xml_obj.attrib['device']
        ret.backing_store = DomainVolumeBackingStore.from_xmlobject(xml_obj)

        source = xml_obj.find('source')
        if source is None:
            return ret
        if 'file' in source.attrib:
            ret.source_type = 'file'
            ret.source = source.attrib['file']
        elif 'dev' in source.attrib:
            ret.source_type = 'dev'
            ret.source = source.attrib['dev']

        driver = xml_obj.find('driver')
        if driver is not None and 'type' in driver.attrib:
            ret.driver_type = driver.attrib['type']
        return ret

    @property
    def installPath(self):
        return self.source

    @property
    def format(self):
        return self.driver_type

    @property
    def is_cdrom(self):
        return self.disk_device == 'cdrom'

    def over_incorrect_driver(self):
        return block_device_use_block_type() \
            and (block_volume_over_incorrect_driver(self) \
                or self._backing_store_over_incorrect_driver())

    def _backing_store_over_incorrect_driver(self):
        return False if not self.backing_store else self.backing_store.over_incorrect_driver()


class DomainVolumeBackingStore(object):
    def __init__(self):
        self.type = ''
        self.format_type = ''
        self.source = ''
        self.source_type = ''
        self.backing_store = None

        self._origin_xml_obj = None

    @property
    def deviceType(self):
        return self.type

    @property
    def installPath(self):
        return self.source

    @classmethod
    def from_xmlobject(cls, xml_obj):
        '''
    <disk type='block' device='disk' snapshot='external'>
      <driver name='qemu' type='qcow2' cache='none'/>
      <source dev='/dev/94db02a247614ddaaf574076c6b58677/dc3641c1c7824e9bbbfdd906e7d86177'/>
      <backingStore type='file' index='1'>
        <format type='qcow2'/>
        <source file='/dev/94db02a247614ddaaf574076c6b58677/d63ebad7d76e45ccbd69b192f26f7c8a'/>
        <backingStore type='block' index='2'>
          <format type='qcow2'/>
          <source dev='/dev/94db02a247614ddaaf574076c6b58677/176756835c27443e95f6a34d49eb0628'/>
          <backingStore/>
        </backingStore>
      </backingStore>
      <target dev='vda' bus='virtio'/>
      <serial>d63ebad7d76e45ccbd69b192f26f7c8a</serial>
      <boot order='1'/>
      <alias name='virtio-disk0'/>
      <address type='pci' domain='0x0000' bus='0x00' slot='0x0a' function='0x0'/>
    </disk>
        '''
        backing_store = xml_obj.find('backingStore')
        if backing_store is None or not backing_store.attrib:
            return None
        ret = cls()
        ret._origin_xml_obj = backing_store
        ret.type = backing_store.attrib['type']

        backing_store_format = backing_store.find('format')
        ret.format_type = backing_store_format.attrib['type']

        source = backing_store.find('source')
        if 'file' in source.attrib:
            ret.source_type = 'file'
            ret.source = source.attrib['file']
        elif 'dev' in source.attrib:
            ret.source_type = 'dev'
            ret.source = source.attrib['dev']

        ret.backing_store = cls.from_xmlobject(backing_store)
        return ret

    def over_incorrect_driver(self):
        if not self.backing_store:
            return self._over_incorrect_driver()
        return self._over_incorrect_driver() \
            or self.backing_store.over_incorrect_driver()

    def _over_incorrect_driver(self):
        return block_volume_over_incorrect_driver(self)

    def update_backing_store_type_to_block(self):
        if self.backing_store is not None:
            self.backing_store.update_backing_store_type_to_block()

        if self._over_incorrect_driver():
            self._update_backing_store_type_to_block()

    def _update_backing_store_type_to_block(self):
        bs = self._origin_xml_obj
        bs.attrib['type'] = 'block'
        self.type = 'block'

        source = bs.find('source')
        source.attrib = {'dev': self.source}
        self.source_type = 'dev'


class RemoteStorageFactory(object):
    @staticmethod
    def get_remote_storage(cmd):
        if cmd.storageInfo:
            if cmd.storageInfo.type == 'nfs':
                return NfsRemoteStorage(cmd)
            elif cmd.storageInfo.type == 'sshfs':
                return SshfsRemoteStorage(cmd)
            elif cmd.storageInfo.type == 'nbd':
                return NbdRemoteStorage(cmd)
        return SshfsRemoteStorage(cmd)


class RemoteStorage(object):
    def __init__(self):
        pass

    def connect(self):
        raise Exception('function connect not be implemented')

    def disconnect(self):
        raise Exception('function disconnect not be implemented')

    def workspace(self):
        raise Exception('function workspace not be implemented')

    def worktarget(self, target_name):
        raise Exception('function worktarget not be implemented')


class NbdRemoteStorage(RemoteStorage):
    def __init__(self, cmd):
        super(NbdRemoteStorage, self).__init__()
        self.url = cmd.storageInfo.url

    def connect(self):
        pass

    def disconnect(self):
        pass

    def workspace(self):
        return self.url

    def worktarget(self, target_name):
        return self.url


class RemoteFileSystem(RemoteStorage):
    def __init__(self):
        self.mount_point = tempfile.mkdtemp(prefix="zs-backup")

    def mount(self):
        raise Exception('function mount not be implemented')

    def umount(self):
        raise Exception('function umount not be implemented')

    def clean(self):
        linux.rmdir_if_empty(self.mount_point)

    def connect(self):
        self.mount()

    def disconnect(self):
        self.umount()
        self.clean()

    def worktarget(self, fname):
        return os.path.join(self.workspace(), fname)


class NfsRemoteStorage(RemoteFileSystem):
    def __init__(self, cmd):
        super(NfsRemoteStorage, self).__init__()
        self.options = cmd.storageInfo.options
        self.url = cmd.storageInfo.url
        relative_work_dir = cmd.uploadDir.replace(os.path.normpath(cmd.bsPath), '').lstrip(os.path.sep)
        self.local_work_dir = os.path.join(self.mount_point, relative_work_dir)
        self.remote_work_dir = os.path.join(self.url, relative_work_dir)

    def mount(self):
        linux.mount(self.url, self.mount_point, self.options)

    def umount(self):
        if linux.is_mounted(path=self.mount_point):
            linux.umount(self.mount_point)

    def workspace(self):
        return self.local_work_dir


class SshfsRemoteStorage(RemoteFileSystem):
    def __init__(self, cmd):
        super(SshfsRemoteStorage, self).__init__()
        self.bandwidth = cmd.networkWriteBandwidth
        self.username = cmd.username
        self.hostname = cmd.hostname
        self.port = cmd.sshPort
        self.password = cmd.password
        self.dst_dir = cmd.uploadDir
        self.vm_uuid = cmd.vmUuid
        self.remote_work_dir = cmd.uploadDir
        self.local_work_dir = self.mount_point

    def mount(self):
        if 0 != linux.sshfs_mount_with_vm_xml(get_vm_by_uuid(self.vm_uuid).domain_xmlobject, self.username, self.hostname, self.port,
                                              self.password, self.dst_dir, self.mount_point, self.bandwidth):
            raise kvmagent.KvmError("failed to prepare backup space for [vm:%s]" % self.vm_uuid)

    def umount(self):
        for i in xrange(6):
            if linux.fumount(self.mount_point, 5) == 0:
                break
            else:
                time.sleep(5)

    def workspace(self):
        return self.local_work_dir


class StartVmCmd(kvmagent.AgentCommand):
    @log.sensitive_fields("consolePassword")
    def __init__(self):
        super(StartVmCmd, self).__init__()
        self.vmInstanceUuid = None
        self.vmName = None
        self.memory = None
        self.cpuNum = None
        self.maxVcpuNum = None
        self.cpuSpeed = None
        self.socketNum = None
        self.cpuOnSocket = None
        self.threadsPerCore = None
        self.bootDev = None
        self.rootVolume = None
        self.dataVolumes = []
        self.cacheVolumes = []
        self.isoPath = None
        self.nics = []
        self.timeout = None
        self.dataIsoPaths = None
        self.addons = None
        self.useBootMenu = True
        self.bootMenuSplashTimeout = None
        self.vmCpuModel = None
        self.emulateHyperV = False
        self.additionalQmp = True
        self.isApplianceVm = False
        self.systemSerialNumber = None
        self.bootMode = None
        self.consolePassword = None
        self.memBalloon = None # type:VirtualDeviceInfo
        self.suspendToRam = None
        self.suspendToDisk = None

class StartVmResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(StartVmResponse, self).__init__()
        self.nicInfos = []  # type:list[VmNicInfo]
        self.virtualDeviceInfoList = []  # type:list[VirtualDeviceInfo]
        self.memBalloonInfo = None  # type:VirtualDeviceInfo
        self.virtualizerInfo = VirtualizerInfoTO()  # type:VirtualizerInfoTO

class SyncVmDeviceInfoCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SyncVmDeviceInfoCmd, self).__init__()
        self.vmInstanceUuid = None

class SyncVmDeviceInfoResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(SyncVmDeviceInfoResponse, self).__init__()
        self.nicInfos = []  # type:list[VmNicInfo]
        self.virtualDeviceInfoList = []  # type:list[VirtualDeviceInfo]
        self.memBalloonInfo = None  # type:VirtualDeviceInfo
        self.virtualizerInfo = VirtualizerInfoTO()  # type:VirtualizerInfoTO


class VirtualDeviceInfo():
    def __init__(self):
        self.deviceAddress = DeviceAddress()
        self.resourceUuid = None

class VmNicInfo():
    def __init__(self):
        self.deviceAddress = DeviceAddress()
        self.macAddress = None

class DeviceAddress():
    def __init__(self):
        self.type = None
        self.bus = None

        # for pci address
        self.domain = None
        self.slot = None
        self.function = None

        # for driver address
        self.controller = None
        self.target = None
        self.unit = None

class AttachNicResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(AttachNicResponse, self).__init__()
        self.virtualDeviceInfoList = []

class GetVncPortCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetVncPortCmd, self).__init__()
        self.vmUuid = None


class GetVncPortResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetVncPortResponse, self).__init__()
        self.port = None
        self.protocol = None
        self.vncPort = None
        self.spicePort = None
        self.spiceTlsPort = None


class ChangeCpuMemResponse(kvmagent.AgentResponse):
    def _init_(self):
        super(ChangeCpuMemResponse, self)._init_()
        self.cpuNum = None
        self.memorySize = None
        self.vmuuid

class IncreaseCpuResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(IncreaseCpuResponse, self).__init__()
        self.cpuNum = None
        self.vmUuid = None

class IncreaseMemoryResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(IncreaseMemoryResponse, self).__init__()
        self.memorySize = None
        self.vmUuid = None

class StopVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(StopVmCmd, self).__init__()
        self.uuid = None
        self.timeout = None


class StopVmResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(StopVmResponse, self).__init__()


class PauseVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(PauseVmCmd, self).__init__()
        self.uuid = None
        self.timeout = None


class PauseVmResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(PauseVmResponse, self).__init__()


class ResumeVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ResumeVmCmd, self).__init__()
        self.uuid = None
        self.timeout = None


class ResumeVmResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ResumeVmResponse, self).__init__()


class RebootVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(RebootVmCmd, self).__init__()
        self.uuid = None
        self.timeout = None


class RebootVmResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(RebootVmResponse, self).__init__()
        self.virtualizerInfo = VirtualizerInfoTO()  # type:VirtualizerInfoTO


class DestroyVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DestroyVmCmd, self).__init__()
        self.uuid = None


class DestroyVmResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DestroyVmResponse, self).__init__()


class VmSyncCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(VmSyncCmd, self).__init__()


class VmSyncResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(VmSyncResponse, self).__init__()
        self.states = None
        self.vmInShutdowns = None


last_inactive_vol_paths = {}  # type: dict[str, set[str]]
class VolumeSyncResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(VolumeSyncResponse, self).__init__()
        self.inactiveVolumePaths = {}  # type: dict[str, list[str]]


class AttachDataVolumeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(AttachDataVolumeCmd, self).__init__()
        self.volume = None
        self.uuid = None


class AttachDataVolumeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(AttachDataVolumeResponse, self).__init__()
        self.virtualDeviceInfoList = []  # type:list[VirtualDeviceInfo]


class DetachDataVolumeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DetachDataVolumeCmd, self).__init__()
        self.volume = None
        self.uuid = None


class DetachDataVolumeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DetachDataVolumeResponse, self).__init__()

class MigrateVmResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(MigrateVmResponse, self).__init__()

class GetCpuXmlResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetCpuXmlResponse, self).__init__()
        self.cpuXml = None
        self.cpuModelName = None

class CompareCpuFunctionResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CompareCpuFunctionResponse, self).__init__()

class TakeSnapshotResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(TakeSnapshotResponse, self).__init__()
        self.newVolumeInstallPath = None
        self.snapshotInstallPath = None
        self.size = None


class TakeVolumeBackupCommand(kvmagent.AgentCommand):
    @log.sensitive_fields("password")
    def __init__(self):
        super(TakeVolumeBackupCommand, self).__init__()
        self.hostname = None
        self.username = None
        self.password = None
        self.sshPort = 22
        self.bsPath = None
        self.uploadDir = None
        self.vmUuid = None
        self.volume = None
        self.bitmap = None
        self.lastBackup = None
        self.networkWriteBandwidth = 0L
        self.volumeWriteBandwidth = 0L
        self.maxIncremental = 0
        self.mode = None
        self.storageInfo = None


class TakeVolumeMirrorResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(TakeVolumeMirrorResponse, self).__init__()


class CancelVolumeMirrorResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CancelVolumeMirrorResponse, self).__init__()


class QueryVolumeMirrorResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(QueryVolumeMirrorResponse, self).__init__()
        self.mirrorVolumes = [] # type:list[str]
        self.extraMirrorVolumes = [] # type:list[str]


class GetVolumeMirrorModeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetVolumeMirrorModeResponse, self).__init__()
        self.mode = None


class QueryBlockJobStatusResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(QueryBlockJobStatusResponse, self).__init__()

class QueryVmLatenciesThread(threading.Thread):
    def __init__(self, func, uuids, times):
        threading.Thread.__init__(self)
        self.func = func
        self.uuids = uuids
        self.times = times
        self.res = []

    def run(self):
        self.res = self.func(self.uuids, self.times)

    def getResult(self):
        return self.res


class TakeVolumeBackupResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(TakeVolumeBackupResponse, self).__init__()
        self.backupFile = None
        self.parentInstallPath = None
        self.bitmap = None


class QueryMirrorLatencyResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(QueryMirrorLatencyResponse, self).__init__()
        self.vmCurrentMaxCdpLatencyInfos = {}
        self.vmCurrentMinCdpLatencyInfos = {}



class VolumeBackupInfo(object):
    def __init__(self, deviceId, bitmap, backupFile, parentInstallPath):
        self.deviceId = deviceId
        self.bitmap = bitmap
        self.backupFile = backupFile
        self.parentInstallPath = parentInstallPath


class TakeVolumesBackupsCommand(kvmagent.AgentCommand):
    @log.sensitive_fields("password")
    def __init__(self):
        super(TakeVolumesBackupsCommand, self).__init__()
        self.hostname = None
        self.username = None
        self.password = None
        self.sshPort = 22
        self.bsPath = None
        self.uploadDir = None
        self.vmUuid = None
        self.backupInfos = []
        self.deviceIds = []  # type:list[int]
        self.networkWriteBandwidth = 0L
        self.volumeWriteBandwidth = 0L
        self.maxIncremental = 0
        self.mode = None
        self.volumes = []
        self.storageInfo = None


class TakeVolumesBackupsResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(TakeVolumesBackupsResponse, self).__init__()
        self.backupInfos = [] # type: list[VolumeBackupInfo]


class TakeSnapshotsCmd(kvmagent.AgentCommand):
    snapshotJobs = None  # type: list[VolumeSnapshotJobStruct]

    def __init__(self):
        super(TakeSnapshotsCmd, self).__init__()
        self.snapshotJobs = []


class TakeSnapshotsResponse(kvmagent.AgentResponse):
    snapshots = None  # type: List[VolumeSnapshotResultStruct]

    def __init__(self):
        super(TakeSnapshotsResponse, self).__init__()
        self.snapshots = []


class CancelBackupJobsCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(CancelBackupJobsCmd, self).__init__()
        self.vmUuid = None


class CancelBackupJobsResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CancelBackupJobsResponse, self).__init__()


class CancelBackupJobResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CancelBackupJobResponse, self).__init__()


class MergeSnapshotRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(MergeSnapshotRsp, self).__init__()


class LogoutIscsiTargetRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(LogoutIscsiTargetRsp, self).__init__()


class LoginIscsiTargetCmd(kvmagent.AgentCommand):
    @log.sensitive_fields("chapPassword")
    def __init__(self):
        super(LoginIscsiTargetCmd, self).__init__()
        self.hostname = None
        self.port = None  # type:int
        self.target = None
        self.chapUsername = None
        self.chapPassword = None


class LoginIscsiTargetRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(LoginIscsiTargetRsp, self).__init__()


class ReportVmStateCmd(object):
    def __init__(self):
        self.hostUuid = None
        self.vmUuid = None
        self.vmState = None

class ReportVmShutdownEventCmd(object):
    def __init__(self):
        self.vmUuid = None

class ReportVmStartEventCmd(object):
    def __init__(self):
        self.vmUuid = None

class ReportVmRebootEventCmd(object):
    def __init__(self):
        self.vmUuid = None

class ReportVmCrashEventCmd(object):
    def __init__(self):
        self.vmUuid = None

class CheckVmStateRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckVmStateRsp, self).__init__()
        self.states = {}

class CheckColoVmStateRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckColoVmStateRsp, self).__init__()
        self.state = None
        self.mode = None

class ChangeVmPasswordCmd(kvmagent.AgentCommand):
    @log.sensitive_fields("accountPerference.accountPassword")
    def __init__(self):
        super(ChangeVmPasswordCmd, self).__init__()
        self.accountPerference = AccountPerference()  # type:AccountPerference
        self.timeout = 0L


class ChangeVmPasswordRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(ChangeVmPasswordRsp, self).__init__()
        self.accountPerference = None


class AccountPerference(object):
    def __init__(self):
        self.userAccount = None
        self.accountPassword = None
        self.vmUuid = None


class ReconnectMeCmd(object):
    def __init__(self):
        self.hostUuid = None
        self.reason = None

class FailOverCmd(object):
    def __init__(self):
        self.vmInstanceUuid = None
        self.hostUuid = None
        self.reason = None
        self.primaryVmFailure = None

class HotPlugPciDeviceCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(HotPlugPciDeviceCommand, self).__init__()
        self.pciDeviceAddress = None
        self.vmUuid = None

class HotPlugPciDeviceRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(HotPlugPciDeviceRsp, self).__init__()

class HotUnplugPciDeviceCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(HotUnplugPciDeviceCommand, self).__init__()
        self.pciDeviceAddress = None
        self.vmUuid = None

class HotUnplugPciDeviceRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(HotUnplugPciDeviceRsp, self).__init__()

class HotPlugMdevDeviceCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(HotPlugMdevDeviceCommand, self).__init__()
        self.MdevDeviceUuid = None
        self.vmUuid = None

class HotPlugMdevDeviceRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(HotPlugMdevDeviceRsp, self).__init__()

class HotUnplugMdevDeviceCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(HotUnplugMdevDeviceCommand, self).__init__()
        self.MdevDeviceUuid = None
        self.vmUuid = None

class HotUnplugMdevDeviceRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(HotUnplugMdevDeviceRsp, self).__init__()

class AttachPciDeviceToHostCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(AttachPciDeviceToHostCommand, self).__init__()
        self.pciDeviceAddress = None

class AttachPciDeviceToHostRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(AttachPciDeviceToHostRsp, self).__init__()

class DetachPciDeviceFromHostCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(DetachPciDeviceFromHostCommand, self).__init__()
        self.pciDeviceAddress = None

class DetachPciDeviceFromHostRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(DetachPciDeviceFromHostRsp, self).__init__()

class KvmAttachUsbDeviceRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(KvmAttachUsbDeviceRsp, self).__init__()

class KvmDetachUsbDeviceRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(KvmDetachUsbDeviceRsp, self).__init__()

class ReloadRedirectUsbRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(ReloadRedirectUsbRsp, self).__init__()

class CheckMountDomainRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckMountDomainRsp, self).__init__()
        self.active = False
class KvmResizeVolumeCommand(kvmagent.AgentCommand):
    def __init__(self):
        super(KvmResizeVolumeCommand, self).__init__()
        self.vmUuid = None
        self.size = None
        self.deviceId = None

class KvmResizeVolumeRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(KvmResizeVolumeRsp, self).__init__()

class UpdateVmPriorityRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(UpdateVmPriorityRsp, self).__init__()

class BlockStreamResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(BlockStreamResponse, self).__init__()

class BlockCommitResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(BlockCommitResponse, self).__init__()

class AttachGuestToolsIsoToVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(AttachGuestToolsIsoToVmCmd, self).__init__()
        self.vmInstanceUuid = None
        self.needTempDisk = None

class AttachGuestToolsIsoToVmRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(AttachGuestToolsIsoToVmRsp, self).__init__()

class DetachGuestToolsIsoFromVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DetachGuestToolsIsoFromVmCmd, self).__init__()
        self.vmInstanceUuid = None

class DetachGuestToolsIsoFromVmRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(DetachGuestToolsIsoFromVmRsp, self).__init__()

class IsoTo(object):
    def __init__(self):
        super(IsoTo, self).__init__()
        self.path = None
        self.imageUuid = None
        self.deviceId = None
        self.isEmpty = False
        self.protocol = None

class AttachIsoCmd(object):
    def __init__(self):
        super(AttachIsoCmd, self).__init__()
        self.iso = None
        self.vmUuid = None

class DetachIsoCmd(object):
    def __init__(self):
        super(DetachIsoCmd, self).__init__()
        self.vmUuid = None
        self.deviceId = None

class GetVmGuestToolsInfoCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetVmGuestToolsInfoCmd, self).__init__()
        self.vmInstanceUuid = None
        self.platform = None

class GetVmGuestToolsInfoRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetVmGuestToolsInfoRsp, self).__init__()
        self.version = None
        self.status = None
        self.features = {}

class GetVmMetricsRoutingStatusRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetVmMetricsRoutingStatusRsp, self).__init__()
        self.values = {}

class GetVmFirstBootDeviceCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetVmFirstBootDeviceCmd, self).__init__()
        self.uuid = None

class GetVmFirstBootDeviceRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetVmFirstBootDeviceRsp, self).__init__()
        self.firstBootDevice = None

class FailColoPrimaryVmCmd(kvmagent.AgentCommand):
    @log.sensitive_fields("targetHostPassword")
    def __init__(self):
        super(FailColoPrimaryVmCmd, self).__init__()
        self.vmInstanceUuid = None
        self.targetHostIp = None
        self.targetHostPort = None
        self.targetHostPassword = None

class QgaExecOutputRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(QgaExecOutputRsp, self).__init__()
        self.exitCode = 0
        self.stdout = ""
        self.stderr = ""

class QgaOpenFileRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(QgaOpenFileRsp, self).__init__()
        self.fileHandle = 0

class QgaUploadfileRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(QgaUploadfileRsp, self).__init__()
        self.fileSize = ""


class GetVirtualizerInfoRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetVirtualizerInfoRsp, self).__init__()
        self.hostInfo = VirtualizerInfoTO()
        self.vmInfoList = []  # type: list[VirtualizerInfoTO]

class VirtualizerInfoTO(object):
    def __init__(self):
        self.uuid = None
        self.virtualizer = None
        self.version = None

class GetVmDeviceAddressRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetVmDeviceAddressRsp, self).__init__()
        self.addresses = {}  # type:map[str, list[VmDeviceAddress]]


class CheckVmRecoveryResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckVmRecoveryResponse, self).__init__()
        self.status = ""  # type:str


class SetVmIoThreadPinCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SetVmIoThreadPinCmd, self).__init__()
        self.vmUuid = None
        self.ioThreadId = None
        self.pin = None


class SetVmIoThreadPinRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(SetVmIoThreadPinRsp, self).__init__()
        self.ioThreadId = None


class DelVmIoThreadPinCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DelVmIoThreadPinCmd, self).__init__()
        self.vmUuid = None
        self.ioThreadId = None


class DelVmIoThreadPinRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(DelVmIoThreadPinRsp, self).__init__()
        self.ioThreadId = None


class GetVmIoThreadPinCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetVmIoThreadPinCmd, self).__init__()
        self.vmUuid = None


class GetVmIoThreadPinRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(GetVmIoThreadPinRsp, self).__init__()
        self.ioThreadInfo = None


class SetVmScsiControllerCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SetVmScsiControllerCmd, self).__init__()
        self.vmUuid = None
        self.ioThreadId = None


class SetVmScsiControllerRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(SetVmScsiControllerRsp, self).__init__()
        self.vmUuid = None
        self.ioThreadId = None
        self.controllerIndex = None


class DelVmScsiControllerCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(DelVmScsiControllerCmd, self).__init__()
        self.vmUuid = None
        self.ioThreadId = None


class DelVmScsiControllerRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(DelVmScsiControllerRsp, self).__init__()
        self.vmUuid = None
        self.ioThreadId = None


class VmDeviceAddress(object):
    def __init__(self, uuid, device_type, address_type, address):
        self.uuid = uuid
        self.deviceType = device_type
        self.addressType = address_type
        self.address = address


class TakeVmConsoleScreenshotCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(TakeVmConsoleScreenshotCmd, self).__init__()
        self.vmUuid = None


class TakeVmConsoleScreenshotRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(TakeVmConsoleScreenshotRsp, self).__init__()
        self.imageData = None


class ChangeVfNicHaStateCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ChangeVfNicHaStateCmd, self).__init__()
        self.vmUuid = None
        self.nic = None
        self.haState = None


class ChangeVfNicHaStateRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(ChangeVfNicHaStateRsp, self).__init__()


class VncPortIptableRule(object):
    def __init__(self):
        self.host_ip = None
        self.port = None
        self.vm_internal_id = None

    def _make_chain_name(self):
        return "vm-%s-vnc" % self.vm_internal_id

    @lock.file_lock('/run/xtables.lock')
    def apply(self):
        assert self.host_ip is not None
        assert self.port is not None
        assert self.vm_internal_id is not None

        ipt = iptables.from_iptables_save()
        chain_name = self._make_chain_name()
        current_ip = linux.get_host_by_name(self.host_ip)

        # get ipv4 subnet
        current_ip_addr_list = filter(lambda addr: addr.scope == 'universe', iproute.query_addresses_by_ip(current_ip, 4))
        if not current_ip_addr_list:
            err = 'cannot get host ip with netmask for %s' % self.host_ip
            logger.warn(err)
            raise kvmagent.KvmError(err)
        current_ip_with_netmask = '%s/%d' % (current_ip_addr_list[0].address, current_ip_addr_list[0].prefixlen)

        ipt.add_rule('-A INPUT -p tcp -m tcp --dport %s -j %s' % (self.port, chain_name))
        ipt.add_rule('-A %s -d %s -j ACCEPT' % (chain_name, current_ip_with_netmask))
        ipt.add_rule('-A %s ! -d %s -j REJECT --reject-with icmp-host-prohibited' % (chain_name, current_ip_with_netmask))
        ipt.iptable_restore()

    @lock.file_lock('/run/xtables.lock')
    def delete(self):
        assert self.vm_internal_id is not None

        ipt = iptables.from_iptables_save()
        chain_name = self._make_chain_name()
        ipt.delete_chain(chain_name)
        ipt.iptable_restore()

    def find_vm_internal_ids(self, vms):
        internal_ids = []
        namespace_used = is_namespace_used()
        for vm in vms:
            if namespace_used:
                vm_id_node = find_zstack_metadata_node(etree.fromstring(vm.domain_xml), 'internalId')
                if vm_id_node is None:
                    continue

                vm_id = vm_id_node.text
            else:
                if not vm.domain_xmlobject.has_element('metadata.internalId'):
                    continue

                vm_id = vm.domain_xmlobject.metadata.internalId.text_

            if vm_id:
                internal_ids.append(vm_id)
        return internal_ids

    @lock.file_lock('/run/xtables.lock')
    def delete_stale_chains(self):
        ipt = iptables.from_iptables_save()
        tbl = ipt.get_table()
        if not tbl:
            ipt.iptable_restore()
            return

        vms = get_running_vms()
        internal_ids = self.find_vm_internal_ids(vms)

        # delete all vnc chains
        chains = tbl.children[:]
        for chain in chains:
            if 'vm' in chain.name and 'vnc' in chain.name:
                vm_internal_id = chain.name.split('-')[1]
                if vm_internal_id not in internal_ids:
                    ipt.delete_chain(chain.name)
                    logger.debug('deleted a stale VNC iptable chain[%s]' % chain.name)

        ipt.iptable_restore()


def e(parent, tag, value=None, attrib=None, usenamesapce = False):
    if attrib is None:
        attrib = {}
    if usenamesapce:
        tag = '{%s}%s' % (ZS_XML_NAMESPACE, tag)
    el = etree.SubElement(parent, tag, attrib)
    if value:
        el.text = value
    return el


def find_namespace_node(root, path, name):
    ns = {'zs': ZS_XML_NAMESPACE}

    ps = path.split('.')
    cnode = root
    for p in ps:
        cnode = cnode.find(p)
        if cnode is None:
            return None

    return cnode.find('zs:%s' % name, ns)

def find_zstack_metadata_node(root, name):
    zs = find_namespace_node(root, 'metadata', 'zstack')
    if zs is None:
        return None

    return zs.find(name)

def find_domain_cdrom_address(domain_xml, target_dev):
    domain_xmlobject = xmlobject.loads(domain_xml)
    disks = domain_xmlobject.devices.get_children_nodes()['disk']
    for d in disks:
        if d.device_ != 'cdrom':
            continue
        if d.get_child_node('target').dev_ != target_dev:
            continue
        return d.get_child_node('address')
    return None

def find_domain_first_boot_device(domain_xml):
    domain_xmlobject = xmlobject.loads(domain_xml)
    disks = domain_xmlobject.devices.get_child_node_as_list('disk')
    ifaces = domain_xmlobject.devices.get_child_node_as_list('interface')
    for d in disks:
        if d.get_child_node('boot') is None:
            continue
        if d.device_ == 'disk' and d.get_child_node('boot').order_ == '1':
            return "HardDisk"
        if d.device_ == 'cdrom' and d.get_child_node('boot').order_ == '1':
            return "CdRom"
    for i in ifaces:
        if i.get_child_node('boot') is None:
            continue
        if i.get_child_node('boot').order_ == '1':
            return "Network"

    devs = domain_xmlobject.os.get_child_node_as_list('boot')
    if devs and devs[0].dev_ == 'cdrom':
        return "CdRom"
    return "HardDisk"


def is_nbd_disk(disk_xml):
    if disk_xml.type_ != 'network': return False
    return hasattr(disk_xml, 'source') and disk_xml.source.protocol_ == 'nbd'


def compare_version(version1, version2):
    def normalize(v):
        return [int(x) for x in re.sub(r'(\.0+)*$','', v).split(".")]
    return cmp(normalize(version1), normalize(version2))


KERNEL_VERSION = platform.release()
LIBVIRT_VERSION = linux.get_libvirt_version()
LIBVIRT_MAJOR_VERSION = LIBVIRT_VERSION.split('.')[0]

QEMU_VERSION = qemu.get_version()

def is_namespace_used():
    return compare_version(LIBVIRT_VERSION, '1.3.3') >= 0

def is_hv_freq_supported():
    return compare_version(QEMU_VERSION, '2.12.0') >= 0 and LooseVersion(KERNEL_VERSION) >= LooseVersion('3.10.0-957')

def is_hv_synic_supported():
    return compare_version(QEMU_VERSION, '2.12.0') >= 0 and LooseVersion(KERNEL_VERSION) > LooseVersion('3.10.0-1160')

@linux.with_arch(todo_list=['x86_64'])
def is_ioapic_supported():
    return compare_version(LIBVIRT_VERSION, '3.4.0') >= 0

def user_specify_driver():
    return LooseVersion(LIBVIRT_VERSION) >= LooseVersion("6.0.0")

def file_type_support_block_device():
    return LooseVersion(QEMU_VERSION) < LooseVersion("6.0.0")

def is_qemu_support_migrate_with_bitmap(version):
    return LooseVersion(version) >= LooseVersion("4.2.0-640")

def is_libvirt_support_migrate_with_bitmap(version):
    return LooseVersion(version) < LooseVersion('6.0.0')

def is_libvirt_support_blockdev(version):
    return LooseVersion(version) > LooseVersion('6.0.0')

def block_device_use_block_type():
    return user_specify_driver() or not file_type_support_block_device()

def is_kylin402():
    zstack_release = linux.read_file('/etc/zstack-release')
    if zstack_release is None:
        return False
    return "kylin402" in zstack_release.splitlines()[0]

def is_spiceport_driver_supported():
    # qemu-system-aarch64 not supported char driver: spiceport
    return shell.run("%s -h | grep 'chardev spiceport'" % kvmagent.get_qemu_path()) == 0

def is_virtual_machine():
    product_name = shell.call("dmidecode -s system-product-name").strip()
    return product_name == "KVM Virtual Machine" or product_name == "KVM"

def get_domain_type():
    return "qemu" if HOST_ARCH == "aarch64" and is_virtual_machine() else "kvm"

def get_gic_version(cpu_num):
    kernel_release = platform.release().split("-")[0]
    if is_kylin402() and cpu_num <= 8 and LooseVersion(kernel_release) < LooseVersion('4.15.0'):
        return 2

# Occasionally, libvirt might fail to list VM ...
def get_console_without_libvirt(vmUuid):
    output = bash.bash_o("""ps x | awk '/qemu[-]kvm.*%s/{print $1, index($0, " -vnc ")}'""" % vmUuid).splitlines()
    if len(output) != 1:
        return None, None, None, None

    pid, idx = output[0].split()
    output = bash.bash_o(
        """lsof -p %s -aPi4 | grep LISTEN | awk '$8 == "TCP" { n=split($9,a,":"); print a[n] }'""" % pid).splitlines()
    if len(output) < 1:
        logger.warn("get_port_without_libvirt: no port found")
        return None, None, None, None
    # There is a port in vnc, there may be one or two porters in the spice, and two or three ports may exist in vncAndSpice.
    output.sort()
    if len(output) == 1 and int(idx) == 0:
        protocol = "spice"
        return protocol, None, int(output[0]), None

    if len(output) == 1 and int(idx) != 0:
        protocol = "vnc"
        return protocol, int(output[0]), None, None

    if len(output) == 2 and int(idx) == 0:
        protocol = "spice"
        return protocol, None, int(output[0]), int(output[1])

    if len(output) == 2 and int(idx) != 0:
        protocol = "vncAndSpice"
        return protocol, int(output[0]), int(output[1]), None

    if len(output) == 3:
        protocol = "vncAndSpice"
        return protocol, int(output[0]), int(output[1]), int(output[2])

    logger.warn("get_port_without_libvirt: more than 3 ports")
    return None, None, None, None

def check_vdi_port(vncPort, spicePort, spiceTlsPort):
    if vncPort is None and spicePort is None and spiceTlsPort is None:
        return False
    if vncPort is not None and int(vncPort) <= 0:
        return False
    if spicePort is not None and int(spicePort) <= 0:
        return False
    if spiceTlsPort is not None and int(spiceTlsPort) <= 0:
        return False
    return True

# get domain/bus/slot/function from pci device address
def parse_pci_device_address(addr):
    domain = '0000' if len(addr.split(":")) == 2 else addr.split(":")[0]
    bus  = addr.split(":")[-2]
    slot = addr.split(":")[-1].split(".")[0]
    function = addr.split(".")[-1]
    return domain, bus, slot, function

def get_machineType(machine_type):
    if HOST_ARCH == "aarch64":
        return "virt"
    return machine_type if machine_type else "pc"

def get_sgio_value():
    device_name = [x for x in os.listdir("/sys/block") if not x.startswith("loop")][0]
    return "unfiltered" if os.path.isfile("/sys/block/{}/queue/unpriv_sgio".format(device_name)) else "filtered"

class LibvirtCapabilities(object):
    def __init__(self, capabilities):
        self.str_cap = capabilities
        self.xml_cap = minidom.parseString(capabilities)

    def host(self):
        host = self.xml_cap.getElementsByTagName('host')[0]
        return LibvirtHostCapabilities(host)

    def guests(self):
        return self.xml_cap.getElementsByTagName('guest')

class LibvirtHostCapabilities(object):
    def __init__(self, host):
        self.host = host

    @property
    def uuid(self):
        return self.host.getElementsByTagName('uuid')[0].firstChild.nodeValue

    def cpu(self):
        return self.host.getElementsByTagName('cpu')[0]

    def cells(self):
        return self.host.getElementsByTagName('cells')[0]

class LibvirtGuestCapabilities(object):
    def __init__(self, guest):
        self.guest = guest

    @property
    def os_type(self):
        return self.guest.getElementsByTagName('os_type')[0].firstChild.nodeValue

class LibvirtAutoReconnect(object):
    libvirt_singleton = LibvirtSingleton()
    conn = libvirt_singleton.conn

    if not conn:
        raise Exception('unable to get libvirt connection')

    evtMgr = LibvirtEventManagerSingleton()

    libvirt_event_callbacks = libvirt_singleton.libvirt_event_callbacks
    capabilities = LibvirtCapabilities(conn.getCapabilities())

    def __init__(self, func):
        self.func = func
        self.exception = None

    @staticmethod
    def add_libvirt_callback(id, cb):
        cbs = LibvirtAutoReconnect.libvirt_event_callbacks.get(id, None)
        if cbs is None:
            cbs = []
            LibvirtAutoReconnect.libvirt_event_callbacks[id] = cbs
        cbs.append(cb)

    @staticmethod
    def register_libvirt_callbacks():
        def lifecycle_callback(conn, dom, event, detail, opaque):
            cbs = LibvirtAutoReconnect.libvirt_event_callbacks.get(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE)
            if not cbs:
                return

            for cb in cbs:
                try:
                    cb(conn, dom, event, detail, opaque)
                except:
                    content = traceback.format_exc()
                    logger.warn(content)

        LibvirtAutoReconnect.conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
                                                         lifecycle_callback, None)

        def record_block_job_event(conn, dom, disk, type, status, opaque):
            logger.debug("record block job: vm %s on disk %s type %s status %s. %s" % (dom.name(), disk,
             LibvirtEventManager.block_job_type_to_string(type),
             LibvirtEventManager.block_job_status_to_string(status), opaque))

        def reboot_callback(conn, dom, opaque):
            cbs = LibvirtAutoReconnect.libvirt_event_callbacks.get(libvirt.VIR_DOMAIN_EVENT_ID_REBOOT)
            if not cbs:
                return

            for cb in cbs:
                try:
                    cb(conn, dom, opaque)
                except:
                    content = traceback.format_exc()
                    logger.warn(content)

        LibvirtAutoReconnect.conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_BLOCK_JOB, record_block_job_event, None)
        LibvirtAutoReconnect.conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_REBOOT, reboot_callback, None)

        def libvirtClosedCallback(conn, reason, opaque):
            reasonStrings = (
              "Error", "End-of-file", "Keepalive", "Client",
            )
            logger.debug("got libvirt closed callback: %s: %s" % (conn.getURI(), reasonStrings[reason]))

        LibvirtAutoReconnect.conn.registerCloseCallback(libvirtClosedCallback, None)
        # NOTE: the keepalive doesn't work on some libvirtd even the versions are the same
        # the error is like "the caller doesn't support keepalive protocol; perhaps it's missing event loop implementation"

        # def start_keep_alive(_):
        #     try:
        #         LibvirtAutoReconnect.conn.setKeepAlive(5, 3)
        #         return True
        #     except Exception as e:
        #         logger.warn('unable to start libvirt keep-alive, %s' % str(e))
        #         return False
        #
        # if not linux.wait_callback_success(start_keep_alive, timeout=5, interval=0.5):
        #     raise Exception('unable to start libvirt keep-alive after 5 seconds, see the log for detailed error')

    @lock.lock('libvirt-reconnect')
    def _reconnect(self):
        def test_connection():
            try:
                LibvirtAutoReconnect.conn.getLibVersion()
                VmPlugin._reload_ceph_secret_keys()
                return None
            except libvirt.libvirtError as ex:
                return ex

        ex = test_connection()
        if not ex:
            # the connection is ok
            return
        # 2nd version: 2015
        logger.warn("the libvirt connection is broken, there is no safeway to auto-reconnect without fd leak, we"
                    " will ask the mgmt server to reconnect us after self quit")
        _stop_world()


        # old_conn = LibvirtAutoReconnect.conn
        # LibvirtAutoReconnect.conn = libvirt.open('qemu:///system')
        # if not LibvirtAutoReconnect.conn:
        #     raise Exception('unable to get a libvirt connection')
        #
        # for cid in LibvirtAutoReconnect.callback_id:
        #     logger.debug("remove libvirt event callback[id:%s]" % cid)
        #     old_conn.domainEventDeregisterAny(cid)
        #
        # # stop old event manager
        # LibvirtAutoReconnect.evtMgr.stop()
        # # create a new event manager
        # LibvirtAutoReconnect.evtMgr = LibvirtEventManager()
        # LibvirtAutoReconnect.register_libvirt_callbacks()
        #
        # # try to close the old connection anyway
        # try:
        #     old_conn.close()
        # except Exception as ee:
        #     logger.warn('unable to close an old libvirt exception, %s' % str(ee))
        # finally:
        #     del old_conn
        #
        # ex = test_connection()
        # if ex:
        #     # unable to reconnect, raise the error
        #     raise Exception('unable to get a libvirt connection, %s' % str(ex))
        #
        # logger.debug('successfully reconnected to the libvirt')

    def __call__(self, *args, **kwargs):
        try:
            return self.func(LibvirtAutoReconnect.conn)
        except libvirt.libvirtError as ex:
            err = str(ex)
            if 'client socket is closed' in err or 'Broken pipe' in err or 'invalid connection' in err:
                logger.debug('socket to the libvirt is broken[%s], try reconnecting' % err)
                self._reconnect()
                return self.func(LibvirtAutoReconnect.conn)
            else:
                raise


class BlkIscsi(object):
    def __init__(self):
        self.is_cdrom = None
        self.volume_uuid = None
        self.chap_username = None
        self.chap_password = None
        self.device_letter = None
        self.addressBus = None
        self.addressUnit = None
        self.server_hostname = None
        self.server_port = None
        self.target = None
        self.lun = None

    def _login_portal(self):
        login = iscsi.IscsiLogin()
        login.server_hostname = self.server_hostname
        login.server_port = self.server_port
        login.target = self.target
        login.chap_username = self.chap_username
        login.chap_password = self.chap_password
        return login.login()

    def to_xmlobject(self):
        # type: () -> etree.Element
        device_path = self._login_portal()
        if self.is_cdrom:
            root = etree.Element('disk', {'type': 'block', 'device': 'cdrom'})
            e(root, 'driver', attrib={'name': 'qemu', 'type': 'raw', 'cache': 'none'})
            e(root, 'source', attrib={'dev': device_path})
            e(root, 'target', attrib={'dev': self.device_letter})
            if self.addressBus and self.addressUnit:
                e(root, 'address', None,{'type' : 'drive', 'bus' : self.addressBus, 'unit' : self.addressUnit})
        else:
            root = etree.Element('disk', {'type': 'block', 'device': 'lun'})
            e(root, 'driver', attrib={'name': 'qemu', 'type': 'raw', 'cache': 'none', 'discard':'unmap'})
            e(root, 'source', attrib={'dev': device_path})
            e(root, 'target', attrib={'dev': 'sd%s' % self.device_letter})
        return root

    @staticmethod
    @lock.lock('iscsiadm')
    def logout_portal(dev_path):
        if not os.path.exists(dev_path):
            return

        device = os.path.basename(dev_path)
        dir_name = os.path.dirname(dev_path)
        if dir_name != "/dev/disk/by-path" or not device.startswith("ip-"):
            return

        portal = device[3:device.find('-iscsi')]
        target = device[device.find('iqn'):device.find('-lun')]
        try:
            shell.call('iscsiadm  -m node  --targetname "%s" --portal "%s" --logout' % (target, portal))
        except Exception as e:
            logger.warn('failed to logout device[%s], %s' % (dev_path, str(e)))


class IsoCbd(object):
    def __init__(self):
        self.iso = None

    def to_xmlobject(self, target_dev, target_bus_type, bus=None, unit=None, bootOrder=None):
        disk = etree.Element('disk', {'type': 'network', 'device': 'cdrom'})
        e(disk, 'source', None, {'name': make_cbd_conf(self.iso.path.split("@")[0]), 'protocol': 'cbd'})
        e(disk, 'target', None, {'dev': target_dev, 'bus': target_bus_type})
        if bus and unit:
            e(disk, 'address', None, {'type': 'drive', 'bus': bus, 'unit': unit})
        e(disk, 'readonly', None)
        if bootOrder is not None and bootOrder > 0:
            e(disk, 'boot', None, {'order': str(bootOrder)})
        return disk


class IsoCeph(object):
    def __init__(self):
        self.iso = None

    def to_xmlobject(self, target_dev, target_bus_type, bus=None, unit=None, bootOrder=None):
        disk = etree.Element('disk', {'type': 'network', 'device': 'cdrom'})
        source = e(disk, 'source', None, {'name': self.iso.path.lstrip('ceph:').lstrip('//').split("@")[0], 'protocol': 'rbd'})
        if self.iso.secretUuid:
            auth = e(disk, 'auth', attrib={'username': 'zstack'})
            e(auth, 'secret', attrib={'type': 'ceph', 'uuid': self.iso.secretUuid})
        for minfo in self.iso.monInfo:
            e(source, 'host', None, {'name': minfo.hostname, 'port': str(minfo.port)})

        e(disk, 'target', None, {'dev': target_dev, 'bus': target_bus_type})
        if bus and unit:
            e(disk, 'address', None, {'type': 'drive', 'bus': bus, 'unit': unit})
        e(disk, 'readonly', None)
        if bootOrder is not None and bootOrder > 0:
            e(disk, 'boot', None, {'order': str(bootOrder)})
        return disk


class BlkCeph(object):
    def __init__(self):
        self.volume = None
        self.dev_letter = None
        self.bus_type = None

    def to_xmlobject(self):
        disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
        e(disk, 'driver', None, {'name': 'qemu', 'type': 'raw', 'cache': 'none', 'discard': 'unmap'})
        source = e(disk, 'source', None,
                   {'name': self.volume.installPath.lstrip('ceph:').lstrip('//'), 'protocol': 'rbd'})
        if self.volume.secretUuid:
            auth = e(disk, 'auth', attrib={'username': 'zstack'})
            e(auth, 'secret', attrib={'type': 'ceph', 'uuid': self.volume.secretUuid})
        for minfo in self.volume.monInfo:
            e(source, 'host', None, {'name': minfo.hostname, 'port': str(minfo.port)})

        dev_format = Vm._get_disk_target_dev_format(self.bus_type)
        e(disk, 'target', None, {'dev': dev_format % self.dev_letter, 'bus': self.bus_type})
        if self.volume.physicalBlockSize:
            e(disk, 'blockio', None, {'physical_block_size': str(self.volume.physicalBlockSize)})
        return disk


class VirtioCeph(object):
    def __init__(self):
        self.volume = None
        self.dev_letter = None

    def to_xmlobject(self):
        disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
        driver_elements = {'name': 'qemu', 'type': 'raw', 'cache': 'none', 'discard': 'unmap'}
        if self.volume.hasattr("multiQueues") and self.volume.multiQueues:
            driver_elements["queues"] = self.volume.multiQueues
        if self.volume.hasattr("ioThreadId") and self.volume.ioThreadId:
            driver_elements["iothread"] = str(self.volume.ioThreadId)

        e(disk, 'driver', None, driver_elements)
        source = e(disk, 'source', None,
                   {'name': self.volume.installPath.lstrip('ceph:').lstrip('//'), 'protocol': 'rbd'})
        if self.volume.secretUuid:
            auth = e(disk, 'auth', attrib={'username': 'zstack'})
            e(auth, 'secret', attrib={'type': 'ceph', 'uuid': self.volume.secretUuid})
        for minfo in self.volume.monInfo:
            e(source, 'host', None, {'name': minfo.hostname, 'port': str(minfo.port)})
        e(disk, 'target', None, {'dev': 'vd%s' % self.dev_letter, 'bus': 'virtio'})
        if self.volume.physicalBlockSize:
            e(disk, 'blockio', None, {'physical_block_size': str(self.volume.physicalBlockSize)})
        return disk


class VirtioSCSICeph(object):
    def __init__(self):
        self.volume = None
        self.dev_letter = None

    def to_xmlobject(self):
        disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
        e(disk, 'driver', None, {'name': 'qemu', 'type': 'raw', 'cache': 'none', 'discard': 'unmap'})
        source = e(disk, 'source', None,
                   {'name': self.volume.installPath.lstrip('ceph:').lstrip('//'), 'protocol': 'rbd'})
        if self.volume.secretUuid:
            auth = e(disk, 'auth', attrib={'username': 'zstack'})
            e(auth, 'secret', attrib={'type': 'ceph', 'uuid': self.volume.secretUuid})
        for minfo in self.volume.monInfo:
            e(source, 'host', None, {'name': minfo.hostname, 'port': str(minfo.port)})
        e(disk, 'target', None, {'dev': 'sd%s' % self.dev_letter, 'bus': 'scsi'})
        e(disk, 'wwn', self.volume.wwn)
        if self.volume.shareable:
            e(disk, 'shareable')
        if self.volume.physicalBlockSize:
            e(disk, 'blockio', None, {'physical_block_size': str(self.volume.physicalBlockSize)})
        return disk

class VirtioIscsi(object):
    def __init__(self):
        self.volume_uuid = None
        self.chap_username = None
        self.chap_password = None
        self.device_letter = None
        self.server_hostname = None
        self.server_port = None
        self.target = None
        self.lun = None

    def to_xmlobject(self):
        root = etree.Element('disk', {'type': 'network', 'device': 'disk'})
        e(root, 'driver', attrib={'name': 'qemu', 'type': 'raw', 'cache': 'none', 'discard':'unmap'})

        if self.chap_username and self.chap_password:
            auth = e(root, 'auth', attrib={'username': self.chap_username})
            e(auth, 'secret', attrib={'type': 'iscsi', 'uuid': self._get_secret_uuid()})

        source = e(root, 'source', attrib={'protocol': 'iscsi', 'name': '%s/%s' % (self.target, self.lun)})
        e(source, 'host', attrib={'name': self.server_hostname, 'port': self.server_port})
        e(root, 'target', attrib={'dev': 'sd%s' % self.device_letter, 'bus': 'scsi'})
        e(root, 'shareable')
        return root

    def _get_secret_uuid(self):
        root = etree.Element('secret', {'ephemeral': 'yes', 'private': 'yes'})
        e(root, 'description', self.volume_uuid)
        usage = e(root, 'usage', attrib={'type': 'iscsi'})
        e(usage, 'target', self.target)
        xml = etree.tostring(root)
        logger.debug('create secret for virtio-iscsi volume:\n%s\n' % xml)

        @LibvirtAutoReconnect
        def call_libvirt(conn):
            return conn.secretDefineXML(xml)

        secret = call_libvirt()
        secret.setValue(self.chap_password)
        return secret.UUIDString()


class BlockCommitDaemon(plugin.TaskDaemon):
    def __init__(self, task_spec, vm, disk_name, top, base=None, timeout=0, active_commit=False):
        # type: (object, Vm, str, str, str, int, bool) -> None
        super(BlockCommitDaemon, self).__init__(task_spec, 'blockCommit', timeout)
        self.vm = vm  # type: Vm
        self.top = top
        self.base = base
        self.disk_name = disk_name
        self.active_commit = active_commit

    def _cancel(self):
        # if canceled with task success, need pivot abort
        self.vm.domain.blockJobAbort(self.disk_name, libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_ASYNC)

    def _get_percent(self):  # type: () -> int
        cur, end = self.vm.get_block_job_info(self.disk_name)
        if end != 0:
            percent = min(99, cur * 100.0 / end)
            return get_exact_percent(percent, self.stage)


class MergeSnapshotDaemon(plugin.TaskDaemon):
    def __init__(self, task_spec, vm, disk_name, top, base=None):
        # type: (object, Vm, str, str, str, int) -> None
        super(MergeSnapshotDaemon, self).__init__(task_spec, 'mergeSnapshot')
        self.vm = vm  # type: Vm
        self.top = top
        self.base = base
        self.disk_name = disk_name

    def _cancel(self):
        # cancel block job async
        self.vm.domain.blockJobAbort(self.disk_name, 0)

    def _get_percent(self):  # type: () -> int
        cur, end = self.vm.get_block_job_info(self.disk_name)
        if end != 0:
            percent = min(99, cur * 100.0 / end)
            return get_exact_percent(percent, self.stage)

    def check_vm_xml_backing_file_consistency(self, base_disk_install_path, dest_disk_install_path):
        expected = False
        for disk_backing_file_chain in self.vm.get_backing_store_source_recursively():
            chain_depth = len(disk_backing_file_chain)
            if dest_disk_install_path in disk_backing_file_chain.keys():
                dest_disk_install_path_depth = disk_backing_file_chain[dest_disk_install_path]
                # for fullRebase, new top layer do not depend on image cache
                # the depth of disk chain depth will reset
                if base_disk_install_path is None:
                    expected = dest_disk_install_path_depth == chain_depth - 1
                # for not fullRebase, check the current_install_path depth increased 1
                if base_disk_install_path is not None:
                    expected = disk_backing_file_chain[base_disk_install_path] == dest_disk_install_path_depth + 1
                break
        return expected

    def _exit(self, exc_type, ex, exc_tb):
        if exc_type is None:
            return

        current_backing = self.vm._get_back_file(self.top)
        if current_backing != self.base:
            logger.debug("live merge snapshot failed. expected backing %s, "
                         "actually backing %s" % (self.base, current_backing))
            raise ex

        consistent_backing_store_by_libvirt = False
        for i in xrange(5):
            self.vm.refresh()
            consistent_backing_store_by_libvirt = self.check_vm_xml_backing_file_consistency(self.base, self.top)
            if consistent_backing_store_by_libvirt:
                break
            time.sleep(1)

        if consistent_backing_store_by_libvirt:
            logger.debug("libvirt return live merge snapshot failure, but it succeed actually! "
                         "expected volume[install path: %s] backing file is %s. "
                         "check the vm xml meets expectations" % (self.base, current_backing))
            return True
        else:
            logger.debug("live merge snapshot failed. expected backing %s, actually backing %s. "
                         "check the vm xml does not meet expectations" % (self.base, current_backing))
            raise ex


class VmVolumesRecoveryTask(plugin.TaskDaemon):
    def __init__(self, cmd, rvols):
        super(VmVolumesRecoveryTask, self).__init__(cmd, 'recoverVM')
        self.vmUuid = cmd.vmUuid
        self.bandwidth = cmd.recoverBandwidth
        self.volumes = cmd.volumes
        self.rvols = rvols
        self.idx = 0
        self.stage = cmd.threadContext['task-stage']
        self.total = len(cmd.volumes)
        self.cancelled = False
        self.percent = 0
        vm = get_vm_by_uuid(cmd.vmUuid)
        self.domain = vm.domain
        self.domain_xmlobject = vm.domain_xmlobject

    def _cancel(self):
        logger.warn("cancelling vm recovery: %s" % self.vmUuid)
        self.cancelled = True

    def update_progress(self, cur, end):
        base = self.idx * 100 / self.total
        curr = cur * 100 / end / self.total if end > 0 else 0
        self.percent = base + curr

    def wait_and_pivot(self, bdev):
        while True:
            time.sleep(2)
            if self.cancelled:
                self.domain.blockJobAbort(bdev, libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_ASYNC)
                logger.info("blockjob cancelled: %s:%s" % (self.vmUuid, bdev))
                break

            info = self.domain.blockJobInfo(bdev, 0)
            if not info:
                logger.info("blockjob not found: %s:%s" % (self.vmUuid, bdev))
                self.cancelled = True
                return "copy failed: vm %s: disk %s" % (self.vmUuid, bdev)

            if info['cur'] != 0 and info['end'] == info['cur']:
                try:
                    self.domain.blockJobAbort(bdev, libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_PIVOT)
                    break
                except libvirt.libvirtError as e:
                    if e.get_error_code() == libvirt.VIR_ERR_BLOCK_COPY_ACTIVE:
                        continue
                    raise e

            self.update_progress(info['cur'], info['end'])
        return None

    def get_job_params(self):
        if self.bandwidth <= 0:
            return None

        # bps -> MiB/s (limit: 10 GiB/s)
        return { libvirt.VIR_DOMAIN_BLOCK_COPY_BANDWIDTH: max(1<<20, self.bandwidth) }

    def get_source_file(self, d):
        # d->type: etree.Element
        try:
            attr_name = Vm.disk_source_attrname.get(d.attrib['type'])
            return d.find('source').attrib[attr_name]
        except (AttributeError, KeyError):
            return None

    def add_backing_chain_to_disk(self, disk_ele):
        fpath = self.get_source_file(disk_ele)
        # no need to add backing chain on rbd img
        if not fpath:
            return disk_ele
        # zsblk-agent might auto-deactivate idle LV
        if fpath.startswith('/dev/') and not os.path.exists(fpath):
            lvm.active_lv(fpath, False)

        backing_chain = Vm._get_backfile_chain(fpath)
        disk_type = disk_ele.attrib['type']

        def add_backing(ele):
            if not backing_chain:
                return

            backing_path = backing_chain.pop(0)
            backing_store = e(ele, 'backingStore', attrib={'type': disk_type})
            e(backing_store, 'source', None, {Vm.disk_source_attrname.get(disk_type): backing_path})
            e(backing_store, 'format', None, {'type':linux.get_img_fmt(backing_path)})
            add_backing(backing_store)

        add_backing(disk_ele)
        return disk_ele

    def do_copy_and_wait(self, target_dev, disk_ele, params, flags):
        disk_ele = self.add_backing_chain_to_disk(disk_ele)
        diskxml = etree.tostring(disk_ele)

        logger.info("[%d/%d] will recover %s with: %s" % (self.idx+1, self.total, target_dev, diskxml))
        # see ZSTAC-54725: after BlockCopy completed, need double check xml results
        self.domain.blockCopy(target_dev, diskxml, params, flags)
        msg = self.wait_and_pivot(target_dev)
        if msg is not None:
            raise kvmagent.KvmError(msg)
        if self.cancelled:
            raise kvmagent.KvmError('Recovery cancelled for VM: %s' % self.vmUuid)

    def do_recover_with_rvols(self, params, flags):
        for target_dev, disk_ele in self.rvols.items():
            self.do_copy_and_wait(target_dev, disk_ele, params, flags)
            self.idx += 1

    def retrieve_diskele(self, nbddisk):
        for v in self.volumes:
            dstpath, rpath = v.installPath.split('?')
            if rpath.endswith(nbddisk.source.name_):
                saved = v.installPath
                v.installPath = dstpath
                ele = VmPlugin._get_new_disk(etree.fromstring(nbddisk.dump()), v)
                v.installPath = saved
                return ele
        raise kvmagent.KvmError("VM: %s: recover volume not found: %s" % (self.vmUuid, v.installPath))

    # list all disk nodes:
    #  - check and wait existing blockjob;
    #  - initiate blockjob for disks with missed blockjob.
    def do_recover_with_volumes(self, params, flags):
        for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
            if disk.device_ == 'cdrom':
                continue

            try:
                target_dev = disk.target.dev_
                if not is_nbd_disk(disk):
                    logger.info("[%d/%d] skipped recover %s for VM: %s" % (self.idx+1, self.total, target_dev, self.vmUuid))
                    continue

                info = self.domain.blockJobInfo(target_dev, 0)
                if info:
                    logger.info("[%d/%d] picked recover %s for VM: %s" % (self.idx+1, self.total, target_dev, self.vmUuid))
                    self.wait_and_pivot(target_dev)
                    continue

                disk_ele = self.retrieve_diskele(disk)
                diskxml = etree.tostring(disk_ele)
                logger.info("[%d/%d] pickup recover %s with: %s" % (self.idx+1, self.total, target_dev, diskxml))
                self.do_copy_and_wait(target_dev, disk_ele, params, flags)
            finally:
                self.idx += 1
                self.update_progress(0, 0)

    def recover_vm_volumes(self):
        flags = libvirt.VIR_DOMAIN_BLOCK_COPY_TRANSIENT_JOB | libvirt.VIR_DOMAIN_BLOCK_COPY_REUSE_EXT
        params = self.get_job_params()
        if self.rvols != None:
            self.do_recover_with_rvols(params, flags)
        else:
            self.do_recover_with_volumes(params, flags)

    def _get_percent(self):
        return get_exact_percent(self.percent, self.stage)


@linux.retry(times=3, sleep_time=1)
def get_connect(src_host_ip):
    conn = libvirt.open('qemu+tcp://{0}/system'.format(src_host_ip))
    if conn is None:
        logger.warn('unable to connect qemu on host {0}'.format(src_host_ip))
        raise kvmagent.KvmError('unable to connect qemu on host %s' % (src_host_ip))
    return conn


def get_vm_by_uuid(uuid, exception_if_not_existing=True, conn=None, log_vm_xml=False):
    try:
        # libvirt may not be able to find a VM when under a heavy workload, we re-try here
        @LibvirtAutoReconnect
        def call_libvirt(conn):
            return conn.lookupByName(uuid)

        @linux.retry(times=3, sleep_time=1)
        def retry_call_libvirt():
            if conn is None:
                return call_libvirt()
            else:
                return conn.lookupByName(uuid)

        vm = Vm.from_virt_domain(retry_call_libvirt())
        if log_vm_xml:
            logger.debug("find vm xml: %s" % vm.domain_xml)
        return vm
    except libvirt.libvirtError as e:
        error_code = e.get_error_code()
        if error_code == libvirt.VIR_ERR_NO_DOMAIN:
            if exception_if_not_existing:
                raise kvmagent.KvmError('unable to find vm[uuid:%s]' % uuid)
            else:
                return None

        err = 'error happened when looking up vm[uuid:%(uuid)s], libvirt error code: %(error_code)s, %(e)s' % locals()
        raise libvirt.libvirtError(err)

def get_vm_by_uuid_no_retry(uuid, exception_if_not_existing=True):
    try:
        # do not retry to fix create vm slow issue 4175
        @LibvirtAutoReconnect
        def call_libvirt(conn):
            return conn.lookupByName(uuid)

        vm = Vm.from_virt_domain(call_libvirt())
        return vm
    except libvirt.libvirtError as e:
        error_code = e.get_error_code()
        if error_code == libvirt.VIR_ERR_NO_DOMAIN:
            if exception_if_not_existing:
                raise kvmagent.KvmError('unable to find vm[uuid:%s]' % uuid)
            else:
                return None

        err = 'error happened when looking up vm[uuid:%(uuid)s], libvirt error code: %(error_code)s, %(e)s' % locals()
        raise libvirt.libvirtError(err)

def get_active_vm_uuids_states():
    @LibvirtAutoReconnect
    def call_libvirt(conn):
        return conn.listDomainsID()

    ids = call_libvirt()
    uuids_states = {}
    uuids_vmInShutdown = []

    @LibvirtAutoReconnect
    def get_domain(conn):
        # i is for..loop's control variable
        # it's Python's local scope tricky
        try:
            return conn.lookupByID(i)
        except libvirt.libvirtError as ex:
            if ex.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                return None
            raise ex

    for i in ids:
        domain = get_domain()
        if domain == None:
            continue

        uuid = domain.name()
        if uuid.startswith("guestfs-"):
            logger.debug("ignore the temp vm generate by guestfish.")
            continue
        if uuid == "ZStack Management Node VM":
            logger.debug("ignore the vm used for MN HA.")
            continue
        (state, _, _, _, _) = domain.info()
        if state == Vm.VIR_DOMAIN_SHUTDOWN:
            uuids_vmInShutdown.append(uuid)

        state = Vm.power_state[state]
        # or use
        uuids_states[uuid] = state
    return uuids_states, uuids_vmInShutdown


def get_all_vm_states():
    return get_active_vm_uuids_states()[0]

def get_all_vm_sync_states():
    return get_active_vm_uuids_states()

vm_state_cache = {}
def get_vm_states_from_cache():
    return vm_state_cache

def put_vm_state_to_cache(uuid, state):
    vm_state_cache[uuid] = state

def remove_vm_state_from_cache(uuid):
    if uuid in vm_state_cache:
        del vm_state_cache[uuid]

def get_all_vm_states_with_process():
    states = {}

    # Occasionally, virsh might not be able to list all VM instances with
    # uri=qemu://system.  To prevend this situation, we double check the
    # 'rsp.states' agaist QEMU process lists.
    output = bash.bash_o("ps -ef | grep -P -o '(qemu-kvm|qemu-system).*?-name\s+(guest=)?\K.*?,' | sed 's/.$//'").splitlines()
    for guest in output:
        if guest.lower() == "ZStack Management Node VM".lower()\
                or guest.startswith("guestfs-"):
            continue

        states[guest] = Vm.VM_STATE_RUNNING

    return states

def get_running_vms():
    @LibvirtAutoReconnect
    def get_all_ids(conn):
        return conn.listDomainsID()

    ids = get_all_ids()
    vms = []

    @LibvirtAutoReconnect
    def get_domain_vm(conn):
        try:
            domain = conn.lookupByID(i)
            if domain is None:
                return None
            return Vm.from_virt_domain(domain)
        except libvirt.libvirtError as ex:
            if ex.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                return None
            raise ex

    for i in ids:
        vm = get_domain_vm()
        if vm is not None:
            vms.append(vm)

    return vms


def get_cpu_memory_used_by_running_vms():
    runnings = get_running_vms()
    used_cpu = 0
    used_memory = 0
    for vm in runnings:
        used_cpu += vm.get_cpu_num()
        used_memory += vm.get_memory()

    return (used_cpu, used_memory)


def cleanup_stale_vnc_iptable_chains():
    VncPortIptableRule().delete_stale_chains()


def get_volume_actual_installpath(install_path):
    if install_path.startswith('sharedblock'):
        return install_path.replace("sharedblock:/", "/dev")
    elif install_path.startswith('block'):
        return install_path.replace("block://", "/dev/disk/by-id/wwn-0x")
    return install_path


class VmOperationJudger(object):
    def __init__(self, op):
        self.op = op
        self.expected_events = {}

        if self.op == VmPlugin.VM_OP_START:
            self.expected_events[LibvirtEventManager.EVENT_STARTED] = LibvirtEventManager.EVENT_STARTED
        elif self.op == VmPlugin.VM_OP_MIGRATE:
            self.expected_events[LibvirtEventManager.EVENT_STOPPED] = LibvirtEventManager.EVENT_STOPPED
        elif self.op == VmPlugin.VM_OP_STOP:
            self.expected_events[LibvirtEventManager.EVENT_STOPPED] = LibvirtEventManager.EVENT_STOPPED
        elif self.op == VmPlugin.VM_OP_DESTROY:
            self.expected_events[LibvirtEventManager.EVENT_STOPPED] = LibvirtEventManager.EVENT_STOPPED
        elif self.op == VmPlugin.VM_OP_REBOOT:
            self.expected_events[LibvirtEventManager.EVENT_STARTED] = LibvirtEventManager.EVENT_STARTED
            self.expected_events[LibvirtEventManager.EVENT_STOPPED] = LibvirtEventManager.EVENT_STOPPED
        elif self.op == VmPlugin.VM_OP_SUSPEND:
            self.expected_events[LibvirtEventManager.EVENT_SUSPENDED] = LibvirtEventManager.EVENT_SUSPENDED
        elif self.op == VmPlugin.VM_OP_RESUME:
            self.expected_events[LibvirtEventManager.EVENT_RESUMED] = LibvirtEventManager.EVENT_RESUMED
        else:
            raise Exception('unknown vm operation[%s]' % self.op)

    def remove_expected_event(self, evt):
        del self.expected_events[evt]
        return len(self.expected_events)

    def ignore_libvirt_events(self):
        if self.op == VmPlugin.VM_OP_START:
            return [LibvirtEventManager.EVENT_STARTED]
        elif self.op == VmPlugin.VM_OP_MIGRATE:
            return [LibvirtEventManager.EVENT_STOPPED, LibvirtEventManager.EVENT_UNDEFINED]
        elif self.op == VmPlugin.VM_OP_STOP:
            return [LibvirtEventManager.EVENT_STOPPED, LibvirtEventManager.EVENT_SHUTDOWN]
        elif self.op == VmPlugin.VM_OP_DESTROY:
            return [LibvirtEventManager.EVENT_STOPPED, LibvirtEventManager.EVENT_SHUTDOWN,
                    LibvirtEventManager.EVENT_UNDEFINED]
        elif self.op == VmPlugin.VM_OP_REBOOT:
            return [LibvirtEventManager.EVENT_STARTED, LibvirtEventManager.EVENT_STOPPED]
        else:
            raise Exception('unknown vm operation[%s]' % self.op)


def make_spool_conf(imgfmt, dev_letter, volume):
    d = tempfile.gettempdir()
    fname = "{0}_{1}".format(os.path.basename(volume.installPath), dev_letter)
    fpath = os.path.join(d, fname) + ".conf"
    vsize, _ = linux.qcow2_size_and_actual_size(volume.installPath)
    with open(fpath, "w") as fd:
       fd.write("device_type  0\n")
       fd.write("local_storage_type 0\n")
       fd.write("device_owner blockpmd\n")
       fd.write("device_format {0}\n".format(imgfmt))
       fd.write("cluster_id 1000\n")
       fd.write("device_id {0}\n".format(ord(dev_letter)))
       fd.write("device_uuid {0}\n".format(fname))
       fd.write("mount_point {0}\n".format(volume.installPath))
       fd.write("device_size {0}\n".format(vsize))

    os.chmod(fpath, 0o600)
    return fpath


def make_cbd_conf(install_path):
    return install_path[len(PROTOCOL_CBD_PREFIX):] + "_" + DEFAULT_ZBS_USER_NAME + "_:" + DEFAULT_ZBS_CONF_PATH


def is_spice_tls():
    return bash.bash_r("grep '^[[:space:]]*spice_tls[[:space:]]*=[[:space:]]*1' /etc/libvirt/qemu.conf")


def get_dom_error(uuid):
    try:
        domblkerror = shell.call('virsh domblkerror %s' % uuid)
    except:
        return None

    if 'No errors found' in domblkerror:
        return None
    return domblkerror.replace('\n', '')

VM_RECOVER_DICT = {}
VM_RECOVER_TASKS = {}
LIVE_SNAPSHOT = "liveSnapshot"
OFFLINE_SNAPSHOT = "offlineSnapshot"

def notify_vrouter(vrouter_cmd):
    result = shell.run(' '.join(vrouter_cmd))
    if result != 0:
        raise Exception('Vrouter agent call failed.')
    else:
        logger.info('Vrouter agent call success.')


def transform_to_tf_uuid(src):
    if not src:
        return None
    tmp = [src[:8], src[8:12], src[12:16], src[16:20], src[20:]]
    return '-'.join(tmp)

class Vm(object):
    VIR_DOMAIN_NOSTATE = 0
    VIR_DOMAIN_RUNNING = 1
    VIR_DOMAIN_BLOCKED = 2
    VIR_DOMAIN_PAUSED = 3
    VIR_DOMAIN_SHUTDOWN = 4
    VIR_DOMAIN_SHUTOFF = 5
    VIR_DOMAIN_CRASHED = 6
    VIR_DOMAIN_PMSUSPENDED = 7

    VM_STATE_NO_STATE = 'NoState'
    VM_STATE_RUNNING = 'Running'
    VM_STATE_PAUSED = 'Paused'
    VM_STATE_SHUTDOWN = 'Shutdown'
    VM_STATE_CRASHED = 'Crashed'
    VM_STATE_SUSPENDED = 'Suspended'

    ALLOW_SNAPSHOT_STATE = (VM_STATE_RUNNING, VM_STATE_PAUSED, VM_STATE_SHUTDOWN)
    SNAPSHOT_VM_STATE_DICT = {
        LIVE_SNAPSHOT: (VM_STATE_RUNNING, VM_STATE_PAUSED),
        OFFLINE_SNAPSHOT: (VM_STATE_SHUTDOWN)
    }

    power_state = {
        VIR_DOMAIN_NOSTATE: VM_STATE_NO_STATE,
        VIR_DOMAIN_RUNNING: VM_STATE_RUNNING,
        VIR_DOMAIN_BLOCKED: VM_STATE_RUNNING,
        VIR_DOMAIN_PAUSED: VM_STATE_PAUSED,
        VIR_DOMAIN_SHUTDOWN: VM_STATE_SHUTDOWN,
        VIR_DOMAIN_SHUTOFF: VM_STATE_SHUTDOWN,
        VIR_DOMAIN_CRASHED: VM_STATE_CRASHED,
        VIR_DOMAIN_PMSUSPENDED: VM_STATE_SUSPENDED,
    }

    # IDE and SATA is not supported in aarch64/i440fx
    # so cdroms and volumes need to share sd[a-z]
    #
    # IDE is supported in x86_64/i440fx
    # so cdroms use hd[c-e]
    # virtio and virtioSCSI volumes share (sd[a-z] - sdc)
    device_letter_config = {
        'aarch64': 'abfghijklmnopqrstuvwxyzde',
        'mips64el': 'abfghijklmnopqrstuvwxyz',
        'loongarch64': 'abfghijklmnopqrstuvwxyz',
        'x86_64': 'abdefghijklmnopqrstuvwxyz'
    }
    DEVICE_LETTERS = device_letter_config[HOST_ARCH]
    ISO_DEVICE_LETTERS = 'cde'
    disk_source_attrname = {
        "file": "file",
        "block": "dev",
        "network": "name"
    }

    timeout_detached_vol = set()

    @staticmethod
    def check_device_exceed_limit(device_id):
        # type: (int) -> None
        if device_id >= len(Vm.DEVICE_LETTERS):
            err = "exceeds max disk limit, device id[%s], but only 0 ~ %d are allowed" % (device_id, len(Vm.DEVICE_LETTERS) - 1)
            logger.warn(err)
            raise kvmagent.KvmError(err)

    @staticmethod
    def get_device_unit(device_id):
        # type: (int) -> int
        Vm.check_device_exceed_limit(device_id)

        # e.g. sda -> unit 0    sdf -> unit 5, same as libvirt
        return ord(Vm.DEVICE_LETTERS[device_id]) - ord(Vm.DEVICE_LETTERS[0])

    @staticmethod
    def get_iso_device_unit(device_id):
        if device_id >= len(Vm.ISO_DEVICE_LETTERS):
            err = "exceeds max iso limit, device id[%s], but only 0 ~ %d are allowed" % (device_id, len(Vm.ISO_DEVICE_LETTERS) - 1)
            logger.warn(err)
            raise kvmagent.KvmError(err)
        return str(ord(Vm.ISO_DEVICE_LETTERS[device_id]) - ord(Vm.DEVICE_LETTERS[0]))

    timeout_object = linux.TimeoutObject()

    @staticmethod
    def set_device_address(disk_element, vol, vm_to_attach=None):
        #  type: (etree.Element, jsonobject.JsonObject, Vm) -> None

        target = disk_element.find('target')
        bus = target.get('bus') if target is not None else None

        if vol.deviceAddress and vol.deviceAddress.type == 'pci' and Vm._get_disk_address_type(bus) == 'pci':
            attributes = {}
            if vol.deviceAddress.domain:
                attributes['domain'] = vol.deviceAddress.domain
            if vol.deviceAddress.bus:
                attributes['bus'] = vol.deviceAddress.bus
            if vol.deviceAddress.slot:
                attributes['slot'] = vol.deviceAddress.slot
            if vol.deviceAddress.function:
                attributes['function'] = vol.deviceAddress.function

            attributes['type'] = vol.deviceAddress.type
            e(disk_element, 'address', None, attributes)
        elif vol.deviceAddress and vol.deviceAddress.type == 'drive' and Vm._get_disk_address_type(bus) == 'drive':
            e(disk_element, 'address', None, {'type': 'drive', 'controller': vol.deviceAddress.controller, 'unit': str(vol.deviceAddress.unit)})
        elif bus == 'scsi':
            occupied_units = vm_to_attach.get_occupied_disk_address_units(bus='scsi', controller=0) if vm_to_attach else []
            default_unit = Vm.get_device_unit(vol.deviceId)
            unit = default_unit if default_unit not in occupied_units else max(occupied_units) + 1
            controller = '0'
            if vol.useVirtioSCSI and vol.hasattr("controllerIndex") and vol.controllerIndex:
               controller = str(vol.controllerIndex)
            e(disk_element, 'address', None, {'type': 'drive', 'controller': controller, 'unit': str(unit)})

    def __init__(self):
        self.uuid = None
        self.domain_xmlobject = None
        self.domain_xml = None
        self.domain = None
        self.state = None
        self.vm_user_defined_xml_hook = False
        self.vm_xml_hook_script = None

    def dump_vm_xml_to_log(self):
        logger.debug('dump vm xml:\n%s' % self.domain_xml)

    def set_user_defined_xml_hook(self, xml_hook_script):
        self.vm_xml_hook_script = xml_hook_script
        self.vm_user_defined_xml_hook = True

    def get_user_defined_xml_hook(self):
        if self.vm_user_defined_xml_hook is True:
            self.vm_user_defined_xml_hook = False
            return self.vm_xml_hook_script
        else:
            return None

    def wait_for_state_change(self, state):
        try:
            self.refresh()
        except Exception as e:
            if not state:
                return True
            raise e

        if isinstance(state, list):
            return self.state in state
        else:
            return self.state == state

    def get_occupied_disk_address_units(self, bus, controller):
        # type: (str, int) -> list[int]
        result = []
        for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
            if not xmlobject.has_element(disk, 'address') or not xmlobject.has_element(disk, 'target'):
                continue

            if not disk.target.bus__ or not disk.target.bus_ == bus:
                continue

            if not disk.address.controller__ or not str(disk.address.controller_) == str(controller):
                continue

            result.append(int(disk.address.unit_))

        return result

    def get_cpu_num(self):
        cpuNum = self.domain_xmlobject.vcpu.current__
        if cpuNum:
            return int(cpuNum)
        else:
            return int(self.domain_xmlobject.vcpu.text_)

    def get_cpu_speed(self):
        cputune = self.domain_xmlobject.get_child_node('cputune')
        if cputune:
            return int(cputune.shares.text_) / self.get_cpu_num()
        else:
            # TODO: return system cpu capacity
            return 512


    def get_memory_stats(self):
        # type: () -> dict[str, int]
        memory_stats_dict = self.domain.memoryStats()
        memory_stats = DomainMemoryStats()
        memory_stats.swap_out = memory_stats_dict.get('swap_out', None)
        memory_stats.available = memory_stats_dict.get('available', None)
        memory_stats.usable = memory_stats_dict.get('usable', None)
        memory_stats.actual = memory_stats_dict.get('actual', None)
        memory_stats.major_fault = memory_stats_dict.get('major_fault', None)
        memory_stats.swap_in = memory_stats_dict.get('swap_in', None)
        memory_stats.last_update = memory_stats_dict.get('last_update', None)
        memory_stats.unused = memory_stats_dict.get('unused', None)
        memory_stats.minor_fault = memory_stats_dict.get('minor_fault', None)
        memory_stats.rss = memory_stats_dict.get('rss', None)

        max_memory = self.domain.maxMemory()
        memory_stats.max = max_memory

        return memory_stats

    def set_memory(self, memory_size_in_mega_bytes):
        self.domain.setMemoryFlags(memory_size_in_mega_bytes)

    def get_memory(self):
        return long(self.domain_xmlobject.currentMemory.text_) * 1024

    def get_name(self):
        return self.domain_xmlobject.description.text_

    def get_migratable_xml(self):
        try:
            libvirt_version, libvirt_release = linux.get_libvirt_rpm_info()
            if ((libvirt_version != '' and libvirt_release != '')
                and (LooseVersion(libvirt_version) == LooseVersion('6.0.0'))
                and (LooseVersion(libvirt_release) < LooseVersion('560'))):
                return self.domain_xml

            return self.domain.XMLDesc(libvirt.VIR_DOMAIN_XML_MIGRATABLE)
        except Exception as e:
            logger.warn("unable to get migratable xml for vm[uuid:%s], %s" % (self.uuid, str(e)))
            return self.domain_xml

    def refresh(self):
        (state, _, _, _, _) = self.domain.info()
        self.state = self.power_state[state]
        self.domain_xml = self.domain.XMLDesc(0)
        self.domain_xmlobject = xmlobject.loads(self.domain_xml)
        self.uuid = self.domain_xmlobject.name.text_

    def is_alive(self):
        try:
            self.domain.info()
            return True
        except:
            return False

    def _wait_for_vm_running(self, timeout=60, wait_console=True):
        if not linux.wait_callback_success(self.wait_for_state_change, [self.VM_STATE_RUNNING, self.VM_STATE_PAUSED], interval=0.5,
                                           timeout=timeout):
            raise kvmagent.KvmError('unable to start vm[uuid:%s, name:%s], vm state is not changing to '
                                    'running/paused after %s seconds' % (self.uuid, self.get_name(), timeout))

        if not wait_console:
            return

        vnc_port = self.get_console_port()

        def wait_vnc_port_open(_):
            cmd = shell.ShellCmd('netstat -na | grep ":%s" > /dev/null' % vnc_port)
            cmd(is_exception=False)
            return cmd.return_code == 0

        if not linux.wait_callback_success(wait_vnc_port_open, None, interval=0.5, timeout=30):
            raise kvmagent.KvmError("unable to start vm[uuid:%s, name:%s]; its vnc port does"
                                    " not open after 30 seconds" % (self.uuid, self.get_name()))

    def _wait_for_vm_paused(self, timeout=60):
        if not linux.wait_callback_success(self.wait_for_state_change, self.VM_STATE_PAUSED, interval=0.5,
                                           timeout=timeout):
            raise kvmagent.KvmError('unable to start vm[uuid:%s, name:%s], vm state is not changing to '
                                    'paused after %s seconds' % (self.uuid, self.get_name(), timeout))

    def reboot(self, cmd):
        self.stop(timeout=cmd.timeout)

        # set boot order
        boot_dev = []
        for bdev in cmd.bootDev:
            xo = xmlobject.XmlObject('boot')
            xo.put_attr('dev', bdev)
            boot_dev.append(xo)

        self.domain_xmlobject.os.replace_node('boot', boot_dev)
        self.domain_xml = self.domain_xmlobject.dump()

        self.start(cmd.timeout)

    def restore(self, path):
        @LibvirtAutoReconnect
        def restore_from_file(conn):
            return conn.restoreFlags(path, self.domain_xml)

        logger.debug('restoring vm:\n%s' % self.domain_xml)
        restore_from_file()

    def start(self, timeout=60, create_paused=False, wait_console=True):
        # TODO: 1. enable hair_pin mode
        logger.debug('creating vm:\n%s' % self.domain_xml)

        @LibvirtAutoReconnect
        def define_xml(conn):
            xml_hook_script_from_user = self.get_user_defined_xml_hook()
            if xml_hook_script_from_user is not None:
                self.domain_xml = xmlhook.get_modified_xml_from_hook(xml_hook_script_from_user, self.domain_xml)
            return conn.defineXML(self.domain_xml)

        flag = (0, libvirt.VIR_DOMAIN_START_PAUSED)[create_paused]
        domain = define_xml()
        self.domain = domain
        self.domain.createWithFlags(flag)
        if create_paused:
            self._wait_for_vm_paused(timeout)
        else:
            self._wait_for_vm_running(timeout, wait_console)

    def dump_guest_memory(self, path):
        # flags
        # memory_only which could be load by gdb or crash
        flags = libvirt.VIR_DUMP_MEMORY_ONLY
        dumpformat = libvirt.VIR_DOMAIN_CORE_DUMP_FORMAT_KDUMP_ZLIB
        self.domain.coreDumpWithFormat(path, dumpformat, flags)

    def stop(self, strategy='grace', timeout=5, undefine=True):
        def cleanup_addons():
            for chan in self.domain_xmlobject.devices.get_child_node_as_list('channel'):
                if chan.type_ == 'unix':
                    path = chan.source.path_
                    linux.rm_file_force(path)

        def loop_shutdown(_):
            try:
                self.domain.shutdown()
            except:
                # domain has been shut down
                pass

            try:
                return self.wait_for_state_change(self.VM_STATE_SHUTDOWN)
            except libvirt.libvirtError as ex:
                error_code = ex.get_error_code()
                if error_code == libvirt.VIR_ERR_NO_DOMAIN:
                    return True
                else:
                    raise

        def iscsi_cleanup():
            disks = self.domain_xmlobject.devices.get_child_node_as_list('disk')

            for disk in disks:
                if disk.type_ == 'block' and disk.device_ == 'lun':
                    BlkIscsi.logout_portal(disk.source.dev_)

        def loop_undefine(_):
            if not undefine:
                return True

            if not self.is_alive():
                return True

            def force_undefine():
                try:
                    self.domain.undefine()
                except:
                    logger.warn('cannot undefine the VM[uuid:%s]' % self.uuid)
                    pid = linux.find_process_by_cmdline(['qemu', self.uuid])
                    if pid:
                        # force to kill the VM
                        linux.kill_process(pid, is_exception=False)

            try:
                flags = 0
                for attr in [ "VIR_DOMAIN_UNDEFINE_MANAGED_SAVE", "VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA", "VIR_DOMAIN_UNDEFINE_NVRAM" ]:
                    if hasattr(libvirt, attr):
                        flags |= getattr(libvirt, attr)
                self.domain.undefineFlags(flags)
            except libvirt.libvirtError as ex:
                logger.warn('undefine domain[%s] failed: %s' % (self.uuid, str(ex)))
                force_undefine()

            return self.wait_for_state_change(None)

        def loop_destroy(_):
            try:
                self.domain.destroy()
            except:
                # domain has been destroyed
                pass

            try:
                return self.wait_for_state_change(self.VM_STATE_SHUTDOWN)
            except libvirt.libvirtError as ex:
                error_code = ex.get_error_code()
                if error_code == libvirt.VIR_ERR_NO_DOMAIN:
                    return True
                else:
                    raise

        do_destroy, isPersistent = strategy == 'grace' or strategy == 'cold', self.domain.isPersistent()
        if strategy == 'grace':
            if linux.wait_callback_success(loop_shutdown, None, timeout=60):
                do_destroy = False

        iscsi_cleanup()

        if do_destroy:
            if not linux.wait_callback_success(loop_destroy, None, timeout=60):
                logger.warn('failed to destroy vm, timeout after 60 secs')
                raise kvmagent.KvmError('failed to stop vm, timeout after 60 secs')

        cleanup_addons()

        if strategy == 'force':
            pid = linux.find_process_by_cmdline(['qemu', self.uuid])
            if pid:
                # force to kill the VM
                try:
                    linux.kill_process(int(pid), 60, True, False)
                except Exception as e:
                    logger.warn('failed to kill vm, timeout after 60 secs')
                    raise kvmagent.KvmError('failed to kill vm, timeout after 60 secs')
            return

        # undefine domain only if it is persistent
        if not isPersistent:
            return

        if not linux.wait_callback_success(loop_undefine, None, timeout=60):
            logger.warn('failed to undefine vm, timeout after 60 secs')
            raise kvmagent.KvmError('failed to stop vm, timeout after 60 secs')

    def destroy(self):
        self.stop(strategy='cold')

    def pause(self, timeout=5):
        def loop_suspend(_):
            try:
                self.domain.suspend()
            except:
                pass
            try:
                return self.wait_for_state_change(self.VM_STATE_PAUSED)
            except libvirt.libvirtError as ex:
                error_code = ex.get_error_code()
                if error_code == libvirt.VIR_ERR_NO_DOMAIN:
                    return True
                else:
                    raise

        if not linux.wait_callback_success(loop_suspend, None, timeout=10):
            raise kvmagent.KvmError('failed to suspend vm ,timeout after 10 secs')

    def resume(self, timeout=5):
        def loop_resume(_):
            try:
                self.domain.resume()
            except:
                pass
            try:
                return self.wait_for_state_change(self.VM_STATE_RUNNING)
            except libvirt.libvirtError as ex:
                error_code = ex.get_error_code()
                if error_code == libvirt.VIR_ERR_NO_DOMAIN:
                    return True
                else:
                    raise

        if not linux.wait_callback_success(loop_resume, None, timeout=60):
            domblkerror = get_dom_error(self.uuid)
            if domblkerror is None:
                raise kvmagent.KvmError('failed to resume vm ,timeout after 60 secs')
            else:
                raise kvmagent.KvmError('failed to resume vm , because  %s' % domblkerror)

    def harden_console(self, mgmt_ip):
        if is_namespace_used():
            id_node = find_zstack_metadata_node(etree.fromstring(self.domain_xml), 'internalId')
            id = id_node.text
        else:
            id = self.domain_xmlobject.metadata.internalId.text_

        vir = VncPortIptableRule()
        vir.vm_internal_id = id
        vir.delete()

        vir.host_ip = mgmt_ip
        vir.port = self.get_console_port()
        vir.apply()

    def get_vdi_connect_port(self):
        rsp = GetVncPortResponse()
        for g in self.domain_xmlobject.devices.get_child_node_as_list('graphics'):
            if g.type_ == 'vnc':
                rsp.vncPort = g.port_
                rsp.protocol = "vnc"
            elif g.type_ == 'spice':
                if g.hasattr('port_'):
                    rsp.spicePort = g.port_
                if g.hasattr('tlsPort_'):
                    rsp.spiceTlsPort = g.tlsPort_
                rsp.protocol = "spice"

        if rsp.vncPort is not None and rsp.spicePort is not None:
            rsp.protocol = "vncAndSpice"
        return rsp.protocol, rsp.vncPort, rsp.spicePort, rsp.spiceTlsPort

    def get_console_port(self):
        for g in self.domain_xmlobject.devices.get_child_node_as_list('graphics'):
            if g.type_ == 'vnc' or g.type_ == 'spice':
                return g.port_

    def get_console_protocol(self):
        for g in self.domain_xmlobject.devices.get_child_node_as_list('graphics'):
            if g.type_ == 'vnc' or g.type_ == 'spice':
                return g.type_

        raise kvmagent.KvmError('no vnc console defined for vm[uuid:%s]' % self.uuid)

    def attach_data_volume(self, volume, addons):
        self._wait_vm_run_until_seconds(10)
        self.timeout_object.wait_until_object_timeout('detach-volume-%s' % self.uuid)
        self._attach_data_volume(volume, addons)
        self.timeout_object.put('attach-volume-%s' % self.uuid, timeout=10)

    @staticmethod
    def set_volume_qos(addons, volume_uuid, volume_xml_obj):
        if not addons:
            return

        vol_qos = addons["VolumeQos"]
        if not vol_qos:
            return
        qos = vol_qos[volume_uuid]
        if not qos:
            return

        io_tune = e(volume_xml_obj, 'iotune')
        if qos.readBandwidth and qos.readBandwidth != -1:
            e(io_tune, 'read_bytes_sec', str(qos.readBandwidth))

        if qos.writeBandwidth and qos.writeBandwidth != -1:
            e(io_tune, 'write_bytes_sec', str(qos.writeBandwidth))

        if qos.totalBandwidth and qos.totalBandwidth != -1:
            e(io_tune, 'total_bytes_sec', str(qos.totalBandwidth))

        if qos.readIOPS and qos.readIOPS != -1:
            e(io_tune, 'read_iops_sec', str(qos.readIOPS))

        if qos.writeIOPS and qos.writeIOPS != -1:
            e(io_tune, 'write_iops_sec', str(qos.writeIOPS))

        if qos.totalIOPS and qos.totalIOPS != -1:
            e(io_tune, 'total_iops_sec', str(qos.totalIOPS))

    @staticmethod
    def set_volume_serial_id(vol_uuid, volume_xml_obj):
        vol_type = volume_xml_obj.get('type')
        if vol_type == 'vhostuser':
            return
        if vol_type == 'block' and volume_xml_obj.get('device') == 'lun':
            return
        e(volume_xml_obj, 'serial', vol_uuid)

    def _attach_data_volume(self, volume, addons):
        Vm.check_device_exceed_limit(volume.deviceId)

        def volume_native_aio(volume_xml_obj):
            if not addons:
                return

            vol_aio = addons['NativeAio']
            if not vol_aio:
                return

            drivers = volume_xml_obj.getiterator("driver")
            if drivers is None or len(drivers) == 0:
                return

            drivers[0].set("io", "native")

        def filebased_volume():
            disk = etree.Element('disk', attrib={'type': 'file', 'device': 'disk'})
            driver_elements = {'name': 'qemu', 'type': linux.get_img_fmt(volume.installPath), 'cache': volume.cacheMode, 'discard': 'unmap'}
            if volume.useVirtio and volume.hasattr("multiQueues") and volume.multiQueues:
                driver_elements["queues"] = volume.multiQueues
            if (not volume.useVirtioSCSI) and volume.useVirtio and volume.hasattr("ioThreadId") and volume.ioThreadId:
                driver_elements["iothread"] = str(volume.ioThreadId)
            e(disk, 'driver', None, driver_elements)
            e(disk, 'source', None, {'file': volume.installPath})

            if volume.shareable:
                e(disk, 'shareable')

            if volume.useVirtioSCSI:
                e(disk, 'target', None, {'dev': 'sd%s' % dev_letter, 'bus': 'scsi'})
                e(disk, 'wwn', volume.wwn)
            elif volume.useVirtio:
                e(disk, 'target', None, {'dev': 'vd%s' % self.DEVICE_LETTERS[volume.deviceId], 'bus': 'virtio'})
            else:
                bus_type = self._get_controller_type()
                dev_format = Vm._get_disk_target_dev_format(bus_type)
                e(disk, 'target', None, {'dev': dev_format % dev_letter, 'bus': bus_type})

            return disk

        def scsilun_volume():
            # default value of sgio is 'filtered'
            #NOTE(weiw): scsi lun not support aio or qos
            disk = etree.Element('disk', attrib={'type': 'block', 'device': 'lun', 'sgio': get_sgio_value()})
            e(disk, 'driver', None, {'name': 'qemu', 'type': 'raw', 'cache': 'none'})
            e(disk, 'source', None, {'dev': volume.installPath})
            e(disk, 'target', None, {'dev': 'sd%s' % dev_letter, 'bus': 'scsi'})
            return disk

        def iscsibased_volume():
            # type: () -> etree.Element
            def virtio_iscsi():
                vi = VirtioIscsi()
                portal, vi.target, vi.lun = volume.installPath.lstrip('iscsi://').split('/')
                vi.server_hostname, vi.server_port = portal.split(':')
                vi.device_letter = dev_letter
                vi.volume_uuid = volume.volumeUuid
                vi.chap_username = volume.chapUsername
                vi.chap_password = volume.chapPassword
                return vi.to_xmlobject()

            def blk_iscsi():
                bi = BlkIscsi()
                portal, bi.target, bi.lun = volume.installPath.lstrip('iscsi://').split('/')
                bi.server_hostname, bi.server_port = portal.split(':')
                bi.device_letter = dev_letter
                bi.volume_uuid = volume.volumeUuid
                bi.chap_username = volume.chapUsername
                bi.chap_password = volume.chapPassword
                return bi.to_xmlobject()

            if volume.useVirtio:
                return virtio_iscsi()
            else:
                return blk_iscsi()

        def ceph_volume():
            # type: () -> etree.Element
            def virtoio_ceph():
                vc = VirtioCeph()
                vc.volume = volume
                vc.dev_letter = dev_letter
                return vc.to_xmlobject()

            def blk_ceph():
                ic = BlkCeph()
                ic.volume = volume
                ic.dev_letter = dev_letter
                ic.bus_type = self._get_controller_type()
                return ic.to_xmlobject()

            def virtio_scsi_ceph():
                vsc = VirtioSCSICeph()
                vsc.volume = volume
                vsc.dev_letter = dev_letter
                return vsc.to_xmlobject()

            if volume.useVirtioSCSI:
                return virtio_scsi_ceph()
            else:
                if volume.useVirtio:
                    return virtoio_ceph()
                else:
                    return blk_ceph()

        def block_volume():
            # type: () -> etree.Element
            def blk():
                disk = etree.Element('disk', {'type': 'block', 'device': 'disk', 'snapshot': 'external'})
                driver_elements = {'name': 'qemu', 'type': linux.get_img_fmt(volume.installPath), 'cache': 'none', 'io': 'native'}
                if volume.useVirtio and volume.hasattr("multiQueues") and volume.multiQueues:
                    driver_elements["queues"] = volume.multiQueues
                if (not volume.useVirtioSCSI) and volume.useVirtio and volume.hasattr("ioThreadId") and volume.ioThreadId:
                    driver_elements["iothread"] = str(volume.ioThreadId)
                e(disk, 'driver', None, driver_elements)
                e(disk, 'source', None, {'dev': volume.installPath})

                if volume.shareable:
                    e(disk, 'shareable')

                if volume.useVirtioSCSI:
                    e(disk, 'target', None, {'dev': 'sd%s' % dev_letter, 'bus': 'scsi'})
                    e(disk, 'wwn', volume.wwn)
                elif volume.useVirtio:
                    e(disk, 'target', None, {'dev': 'vd%s' % dev_letter, 'bus': 'virtio'})
                else:
                    bus_type = self._get_controller_type()
                    dev_format = Vm._get_disk_target_dev_format(bus_type)
                    e(disk, 'target', None, {'dev': dev_format % dev_letter, 'bus': bus_type})

                return disk
            return blk()

        def spool_volume():
            # type: () -> etree.Element
            def blk():
                imgfmt = linux.get_img_fmt(volume.installPath)
                disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
                e(disk, 'driver', None,
                  {'name': 'qemu', 'type': 'raw', 'cache': 'none', 'io': 'native'})
                e(disk, 'source', None,
                  {'protocol': 'spool', 'name': make_spool_conf(imgfmt, dev_letter, volume)})
                e(disk, 'target', None, {'dev': 'vd%s' % dev_letter, 'bus': 'virtio'})
                return disk

            return blk()

        def vhost_volume():
            if not os.path.exists(volume.installPath):
                raise Exception("vhostuser disk %s does not exist" % volume.installPath)

            disk = etree.Element('disk', {'type': 'vhostuser', 'device': 'disk', 'snapshot': 'no'})

            driver_elements = {'name': 'qemu', 'type': volume.format}
            if volume.hasattr("multiQueues") and volume.multiQueues:
                driver_elements["queues"] = volume.multiQueues
            e(disk, 'driver', None, driver_elements)

            source = e(disk, 'source', None, {'type': 'unix', 'path': volume.installPath})
            e(source, 'reconnect', None, {'enabled': 'yes', 'timeout': '10'})

            if volume.shareable:
                e(disk, 'shareable')

            if volume.useVirtioSCSI:
                e(disk, 'target', None, {'dev': 'sd%s' % dev_letter, 'bus': 'scsi'})
                e(disk, 'wwn', volume.wwn)
            elif volume.useVirtio:
                e(disk, 'target', None, {'dev': 'vd%s' % self.DEVICE_LETTERS[volume.deviceId], 'bus': 'virtio'})
            else:
                bus_type = self._get_controller_type()
                dev_format = Vm._get_disk_target_dev_format(bus_type)
                e(disk, 'target', None, {'dev': dev_format % dev_letter, 'bus': bus_type})
            return disk

        def cbd_volume():
            disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
            e(disk, 'driver', None, {'name': 'qemu', 'type': 'raw', 'cache': 'none'})
            e(disk, 'source', None, {'protocol': 'cbd', 'name': make_cbd_conf(volume.installPath)})
            e(disk, 'target', None, {'dev': 'vd%s' % self.DEVICE_LETTERS[volume.deviceId], 'bus': 'virtio'})
            return disk

        dev_letter = self._get_device_letter(volume, addons)
        volume = file_volume_check(volume)

        if volume.hasattr("ioThreadId") and volume.ioThreadId:
            err_info = self.create_iothread(self.uuid, volume.ioThreadId, volume.ioThreadPin)
            if err_info:
                raise kvmagent.KvmError("set iothread[{}:{}] on volume[uuid:{}] err: {}".format(volume.ioThreadId, volume.ioThreadPin, volume.volumeUuid, err_info))
        if volume.useVirtioSCSI and volume.hasattr("ioThreadId") and volume.ioThreadId:
            volume.controllerIndex = self.create_scsi_controller(self.uuid, volume.ioThreadId)

        if volume.deviceType == 'iscsi':
            disk_element = iscsibased_volume()
        elif volume.deviceType == 'file':
            disk_element = filebased_volume()
        elif volume.deviceType == 'ceph':
            disk_element = ceph_volume()
        elif volume.deviceType == 'scsilun':
            disk_element = scsilun_volume()
        elif volume.deviceType == 'block':
            disk_element = block_volume()
        elif volume.deviceType == 'spool':
            disk_element = spool_volume()
        elif volume.deviceType == 'vhost':
            disk_element = vhost_volume()
        elif volume.deviceType == 'cbd':
            disk_element = cbd_volume()
        else:
            raise Exception('unsupported volume deviceType[%s]' % volume.deviceType)

        Vm.set_device_address(disk_element, volume, get_vm_by_uuid(self.uuid))
        Vm.set_volume_qos(addons, volume.volumeUuid, disk_element)
        Vm.set_volume_serial_id(volume.volumeUuid, disk_element)
        volume_native_aio(disk_element)
        xml = etree.tostring(disk_element)
        logger.debug('attaching volume[%s] to vm[uuid:%s]:\n%s' % (volume.installPath, self.uuid, xml))
        try:
            # libvirt has a bug that if attaching volume just after vm created, it likely fails. So we retry three time here
            @linux.retry(times=3, sleep_time=5)
            def attach():
                def wait_for_attach(_):
                    me = get_vm_by_uuid(self.uuid)
                    disk, _ = me._get_target_disk(volume, is_exception=False)

                    if not disk:
                        logger.debug('volume[%s] is still in process of attaching, wait it' % volume.installPath)
                    return bool(disk)

                try:
                    self.domain.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)

                    if not linux.wait_callback_success(wait_for_attach, None, 5, 1):
                        raise Exception("cannot attach a volume[uuid: %s] to the vm[uuid: %s];"
                                        "it's still not attached after 5 seconds" % (volume.volumeUuid, self.uuid))
                except:
                    # check one more time
                    if not wait_for_attach(None):
                        raise

            attach()

        except libvirt.libvirtError as ex:
            err = str(ex)
            if 'Duplicate ID' in err:
                err = ('unable to attach the volume[%s] to vm[uuid: %s], %s. This is a KVM issue, please reboot'
                       ' the VM and try again' % (volume.volumeUuid, self.uuid, err))
            elif 'No more available PCI slots' in err:
                err = ('vm[uuid: %s] has no more PCI slots for volume[%s]. This is a Libvirt issue, please reboot'
                       ' the VM and try again' % (self.uuid, volume.volumeUuid))
            else:
                err = 'unable to attach the volume[%s] to vm[uuid: %s], %s.' % (volume.volumeUuid, self.uuid, err)
            logger.warn(linux.get_exception_stacktrace())
            raise kvmagent.KvmError(err)

    def _get_device_letter(self, volume, addons):
        default_letter = Vm.DEVICE_LETTERS[volume.deviceId]
        if not volume.useVirtioSCSI:
            return default_letter

        # usually, device_letter_index equals device_id, but reversed when volume use VirtioSCSI because of ZSTAC-9641
        # so when attach SCSI volume again after detached it, device_letter should be same as origin name,
        # otherwise it will fail for duplicate device name.

        def get_reversed_disks():
            results = {}
            for vol in addons.attachedDataVolumes:
                _, disk_name = self._get_target_disk(vol)
                if disk_name and disk_name[-1] != Vm.DEVICE_LETTERS[vol.deviceId]:
                    results[disk_name[-1]] = vol.deviceId

            return results

        # {actual_dev_letter: device_id_in_db}
        # type: dict[str, int]
        reversed_disks = get_reversed_disks()
        if default_letter not in reversed_disks.keys():
            return default_letter
        else:
            # letter has been occupied, so return reversed letter
            logger.debug("reversed disk name: %s" % reversed_disks)
            return Vm.DEVICE_LETTERS[reversed_disks[default_letter]]


    def create_iothread(self, vm_uuid, iothread_id, iothread_pin):
        iothread_info = VmPlugin.get_iothread_info(vm_uuid)
        iothread_ids = [i[0] for i in iothread_info]

        err_info = None
        if str(iothread_id) not in iothread_ids:
            err_info = VmPlugin.add_io_thread(vm_uuid, iothread_id)
        if err_info:
            logger.error("add iothread[{}] on vm[{}] failed: {}".format(iothread_id, vm_uuid, err_info))

        err_info = VmPlugin.pin_io_thread(vm_uuid, iothread_id, iothread_pin)
        if err_info:
            logger.error("pin iothread[{}] on vm[{}] failed: {}".format(iothread_id, vm_uuid, err_info))
        return err_info


    def create_scsi_controller(self, vm_uuid, iothread_id):
        return VmPlugin.add_scsi_controller(vm_uuid, iothread_id)


    def detach_data_volume(self, volume):
        self._wait_vm_run_until_seconds(60)
        self.timeout_object.wait_until_object_timeout('attach-volume-%s' % self.uuid)
        self._detach_data_volume(volume)
        self.timeout_object.put('detach-volume-%s' % self.uuid, timeout=10)

    def _detach_data_volume(self, volume):
        assert volume.deviceId != 0, 'how can root volume gets detached???'

        target_disk, disk_name = self._get_target_disk(volume)
        xmlstr = target_disk.dump()
        logger.debug('detaching volume from vm[uuid:%s]:\n%s' % (self.uuid, xmlstr))
        try:
            # libvirt has a bug that if detaching volume just after vm created, it likely fails. So we retry three time here
            @linux.retry(times=3, sleep_time=5)
            def detach():
                def wait_for_detach(_):
                    me = get_vm_by_uuid(self.uuid)
                    disk, _ = me._get_target_disk(volume, is_exception=False)

                    if disk:
                        logger.debug('volume[%s] is still in process of detaching, wait for it' % volume.installPath)

                    return not bool(disk)

                try:
                    disk_is_unplugging = "is already in the process of unplug"
                    with misc.ignore_exception(libvirt.libvirtError, disk_is_unplugging):
                        self.domain.detachDeviceFlags(xmlstr, libvirt.VIR_DOMAIN_AFFECT_LIVE)

                    if not linux.wait_callback_success(wait_for_detach, None, 5, 1):
                        raise Exception("unable to detach the volume[uuid:%s] from the vm[uuid:%s];"
                                        "it's still attached after 5 seconds" %
                                        (volume.volumeUuid, self.uuid))
                except:
                    # check one more time
                    if not wait_for_detach(None):
                        self._record_volume_detach_timeout(volume)
                        logger.debug("detach timeout, record volume install path: %s" % volume.installPath)
                        raise

            detach()

            if self._volume_detach_timed_out(volume):
                self._clean_timeout_record(volume)
                logger.debug("detach success finally, remove record of volume install path: %s" % volume.installPath)

            def logout_iscsi():
                BlkIscsi.logout_portal(target_disk.source.dev_)

            if volume.deviceType == 'iscsi':
                if not volume.useVirtio:
                    logout_iscsi()

            def clean_block_node():
                if volume.deviceType == 'ceph':
                    node_name_and_file = None
                    with misc.ignore_exception(Exception):
                        node_name_and_file = get_block_node_name_and_file(self.uuid)
                    if node_name_and_file is None:
                        return

                    installPath = volume.installPath.replace('ceph://', '').split('/')
                    # ceph file example: "json:{"driver": "raw", "file": {"pool": "pool", "image": "ca46af50ab8742b68e464e9b23b05598"}"
                    format_nodes = []
                    storage_nodes = []
                    other_nodes = []
                    for node_name, file in node_name_and_file.items():
                        if installPath[0] in file and '"' + installPath[1] + '"' in file:
                            if 'format' in node_name:
                                format_nodes.append(node_name)
                            elif 'storage' in node_name:
                                storage_nodes.append(node_name)
                            else:
                                other_nodes.append(node_name)

                    orphan_block_nodes = format_nodes + storage_nodes + other_nodes

                    @linux.retry(times=10, sleep_time=30)
                    def do_clean_orphan_block_nodes(node):
                        _, err = execute_qmp_command(self.uuid, '{ "execute": "blockdev-del", "arguments": { "node-name": "%s" } }' % node)
                        if err:
                            logger.debug(err)
                            raise Exception(err)
                        else:
                            logger.debug("delete vm[%s] orphan block node[%s] success" % (self.uuid, node))

                    for block_node in orphan_block_nodes:
                        try:
                            do_clean_orphan_block_nodes(block_node)
                        except Exception as exc:
                            logger.debug(str(exc))

            if not is_libvirt_support_blockdev(linux.get_libvirt_version()):
                clean_block_node()

        except libvirt.libvirtError as ex:
            vm = get_vm_by_uuid(self.uuid)
            logger.warn('vm dump: %s' % vm.domain_xml)
            logger.warn(linux.get_exception_stacktrace())
            raise kvmagent.KvmError(
                'unable to detach volume[%s] from vm[uuid:%s], %s' % (volume.installPath, self.uuid, str(ex)))

    def _record_volume_detach_timeout(self, volume):
        Vm.timeout_detached_vol.add(volume.installPath + "-" + self.uuid)

    def _volume_detach_timed_out(self, volume):
        return volume.installPath + "-" + self.uuid in Vm.timeout_detached_vol

    def _clean_timeout_record(self, volume):
        Vm.timeout_detached_vol.remove(volume.installPath + "-" + self.uuid)

    @staticmethod
    def _get_back_file(volume):
        back = linux.qcow2_get_backing_file(volume)
        return None if not back else back

    @staticmethod
    def _get_backfile_chain(current):
        back_files = []

        def get_back_files(volume):
            back_file = Vm._get_back_file(volume)
            if not back_file:
                return

            back_files.append(back_file)
            get_back_files(back_file)

        get_back_files(current)
        return back_files

    @staticmethod
    def ensure_no_internal_snapshot(volume):
        if os.path.exists(volume) and shell.run("%s --backing-chain %s | grep 'Snapshot list:'"
                                                        % (qemu_img.subcmd('info'), volume)) == 0:
            raise kvmagent.KvmError('found internal snapshot in the backing chain of volume[path:%s].' % volume)


    @staticmethod
    def ensure_delta_snapshot_not_exceed(volume_install_path):
        qcow2_chain_length = len(linux.qcow2_get_backing_chain(volume_install_path)) + 1
        # ZSTAC-67846: too many snapshots will result in qmp 'query block' command to fail
        if qcow2_chain_length >= 121:
            raise Exception("the chain length of qcow2 %s has reached maximum length 121. Please modify the global config "
                            "'incrementalSnapshot.maxNum' to a smaller value to ensure that the next snapshot "
                            "is full snapshot or delete some incremental snapshots." % volume_install_path)


    def get_block_job_info(self, disk_path):
        status = self.domain.blockJobInfo(disk_path, 0)
        if status == -1:
            return 0, 0

        return status.get('cur', 0), status.get('end', 0)


    # NOTE: code from Openstack nova
    def _wait_for_block_job(self, disk_path, abort_on_error=False,
                            wait_for_job_clean=False):
        """Wait for libvirt block job to complete.

        Libvirt may return either cur==end or an empty dict when
        the job is complete, depending on whether the job has been
        cleaned up by libvirt yet, or not.

        :returns: True if still in progress
                  False if completed
        """

        status = self.domain.blockJobInfo(disk_path, 0)
        if status == -1 and abort_on_error:
            raise kvmagent.KvmError('libvirt error while requesting blockjob info.')

        try:
            cur = status.get('cur', 0)
            end = status.get('end', 0)
            job_type = LibvirtEventManager.block_job_type_to_string(status.get('type'))
            logger.debug("block job[type:%s] of disk:%s current progress cur:%s end:%s" % (job_type, disk_path, cur, end))
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            return False

        if wait_for_job_clean:
            job_ended = not status
        else:
            job_ended = cur == end

        return not job_ended

    def _check_target_disk_existing_by_path(self, install_path, refresh=True):
        if refresh:
            self.refresh()
        d, n = self._get_target_disk_by_path(install_path, is_exception=False)
        return d and n

    def _get_target_disk_by_path(self, installPath, is_exception=True):
        installPath = get_volume_actual_installpath(installPath)

        for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
            if not xmlobject.has_element(disk, 'source'):
                continue

            # file
            if disk.source.file__ and disk.source.file_ == installPath:
                return disk, disk.target.dev_

            # ceph
            if disk.source.name__ and disk.source.name_ in installPath:
                return disk, disk.target.dev_

            # 'block':
            if disk.source.dev__ and disk.source.dev_ in installPath:
                return disk, disk.target.dev_
            
            # vhost
            if disk.source.path__ and disk.source.path_ == installPath:
                return disk, disk.target.dev_

        if not is_exception:
            return None, None

        logger.debug('%s is not found on the vm[uuid:%s]' % (installPath, self.uuid))
        raise kvmagent.KvmError('unable to find volume[installPath:%s] on vm[uuid:%s]' % (installPath, self.uuid))

    def _get_all_volume_alias_names(self, volumes):
        volumes.sort(key=lambda d: d.deviceId)
        target_disk_alias_names = []
        for volume in volumes:
            target_disk, _ = self._get_target_disk(volume)
            target_disk_alias_names.append(target_disk.alias.name_)

        if len(volumes) != len(target_disk_alias_names):
            raise Exception('not all disk have alias names, skip rollback')

        return target_disk_alias_names

    def _get_target_disk(self, volume, is_exception=True):
        volume.installPath = get_volume_actual_installpath(volume.installPath)
        volume = file_volume_check(volume)

        for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
            if not xmlobject.has_element(disk, 'source') and not volume.deviceType == 'quorum':
                continue

            if volume.deviceType == 'iscsi':
                if volume.useVirtio:
                    if disk.source.name__ and disk.source.name_ in volume.installPath:
                        return disk, disk.target.dev_
                else:
                    if disk.source.dev__ and volume.volumeUuid in disk.source.dev_:
                        return disk, disk.target.dev_
            elif volume.deviceType == 'ceph':
                if disk.source.name__ and disk.source.name_ in volume.installPath:
                    return disk, disk.target.dev_
            elif volume.deviceType == 'scsilun':
                if disk.source.dev__ and volume.installPath in disk.source.dev_:
                    return disk, disk.target.dev_
            elif volume.deviceType == 'block' or volume.deviceType == 'file':
                if disk.source.dev__ and disk.source.dev_ in volume.installPath:
                    return disk, disk.target.dev_
                if disk.source.file__ and disk.source.file_ == volume.installPath:
                    return disk, disk.target.dev_
            elif volume.deviceType == 'quorum':
                logger.debug("quorum file path is %s" % disk.backingStore.source.file_)
                if disk.backingStore.source.file_ and disk.backingStore.source.file_ in volume.installPath:
                    disk.driver.type_ = "qcow2"
                    disk.source = disk.backingStore.source
                    return disk, disk.backingStore.source.file_
            elif volume.deviceType == 'vhost':
                if disk.source.path__ and disk.source.path_ == volume.installPath:
                    return disk, disk.target.dev_
            elif volume.deviceType == 'cbd':
                if disk.source.name__ and disk.source.name_ == make_cbd_conf(volume.installPath):
                    return disk, disk.target.dev_

        if not is_exception:
            return None, None

        logger.debug('%s is not found on the vm[uuid:%s], xml: %s' % (volume.installPath, self.uuid, self.domain_xml))
        raise kvmagent.KvmError('unable to find volume[installPath:%s] on vm[uuid:%s]' % (volume.installPath, self.uuid))

    def _is_ft_vm(self):
        return any(disk.type_ == "quorum" for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'))


    def resize_volume(self, volume, size):
        device_id = volume.deviceId
        target_disk, disk_name = self._get_target_disk(volume)

        r, o, e = bash.bash_roe("virsh blockresize {} {} --size {}B".format(self.uuid, disk_name, size))

        logger.debug("resize volume[%s] of vm[%s]" % (target_disk.alias.name_, self.uuid))
        if r != 0:
            raise kvmagent.KvmError(
                'unable to resize volume[id:{1}] of vm[uuid:{0}] because {2}'.format(device_id, self.uuid, e))

    def take_live_volumes_delta_snapshots(self, vs_structs):
        """
        :type vs_structs: list[VolumeSnapshotJobStruct]
        :rtype: list[VolumeSnapshotResultStruct]
        """
        disk_names = []
        return_structs = []
        memory_snapshot_struct = None

        snapshot = etree.Element('domainsnapshot')
        disks = e(snapshot, 'disks')
        logger.debug(snapshot)

        if len(vs_structs) == 0:
            return return_structs

        def get_size(install_path):
            """
            :rtype: long
            """
            return VmPlugin._get_snapshot_size(install_path)

        logger.debug(vs_structs)
        memory_snapshot_required = False
        for vs_struct in vs_structs:
            if vs_struct.live is False or vs_struct.full is True:
                raise kvmagent.KvmError("volume %s is not live or full snapshot specified, "
                                        "can not proceed")

            VmPlugin.active_volume_if_need(vs_struct.installPath)
            if vs_struct.memory:
                memory_snapshot_required = True
                snapshot_dir = os.path.dirname(vs_struct.installPath)
                if not os.path.exists(snapshot_dir):
                    os.makedirs(snapshot_dir)

                memory_snapshot_path = None
                if vs_struct.installPath.startswith("/dev/"):
                    shell.call("mkfs.xfs -f %s" % vs_struct.installPath)
                    mount_path = vs_struct.installPath.replace("/dev/", "/tmp/")
                    if not os.path.exists(mount_path):
                        linux.mkdir(mount_path)

                    if not linux.is_mounted(mount_path):
                        linux.mount(vs_struct.installPath, mount_path)

                    memory_snapshot_path = mount_path + '/' + mount_path.rsplit('/', 1)[-1]
                else:
                    memory_snapshot_path = vs_struct.installPath

                e(snapshot, 'memory', None, attrib={'snapshot': 'external', 'file': memory_snapshot_path})
                memory_snapshot_struct = vs_struct
                continue

            target_disk, disk_name = self._get_target_disk(vs_struct.volume)
            if target_disk is None:
                logger.debug("can not find %s" % vs_struct.volume.deviceId)
                continue

            snapshot_dir = os.path.dirname(vs_struct.installPath)
            if not os.path.exists(snapshot_dir):
                os.makedirs(snapshot_dir)

            disk_names.append(disk_name)
            source_file = VmPlugin.get_source_file_by_disk(target_disk)
            d = e(disks, 'disk', None, attrib={'name': disk_name, 'snapshot': 'external', 'type': target_disk.type_})
            e(d, 'source', None, attrib={'file' if target_disk.type_ == 'file' else 'dev': vs_struct.installPath})
            e(d, 'driver', None, attrib={'type': 'qcow2'})
            return_structs.append(VolumeSnapshotResultStruct(
                vs_struct.volumeUuid,
                source_file,
                vs_struct.installPath,
                get_size(source_file),
                vs_struct.memory))

        self.refresh()
        for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
            if disk.target.dev_ not in disk_names:
                e(disks, 'disk', None, attrib={'name': disk.target.dev_, 'snapshot': 'no'})

        xml = etree.tostring(snapshot)
        logger.debug('creating live snapshot for vm[uuid:{0}] volumes[id:{1}]:\n{2}'.format(self.uuid, disk_names, xml))

        snap_flags = libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA | libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_ATOMIC
        if not memory_snapshot_required:
            snap_flags |= libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY

        try:
            self.domain.snapshotCreateXML(xml, snap_flags)

            if memory_snapshot_struct:
                return_structs.append(VolumeSnapshotResultStruct(
                    memory_snapshot_struct.volumeUuid,
                    memory_snapshot_struct.installPath,
                    memory_snapshot_struct.installPath,
                    get_size(memory_snapshot_struct.installPath),
                    True))

            return return_structs
        except libvirt.libvirtError as ex:
            logger.warn(linux.get_exception_stacktrace())
            ret = []
            for i in xrange(5):
                self.refresh()
                ret = filter(lambda s: self._check_target_disk_existing_by_path(s.installPath, refresh=False), return_structs)
                if len(ret) == len(return_structs):
                    break
                time.sleep(1)

            for r in ret:
                logger.warn("libvirt return snapshot[path:%s] failure, but it succeed actually!" % r.installPath)

            if ret:
                return ret
            raise kvmagent.KvmError(
                'unable to take live snapshot of vm[uuid:{0}] volumes[id:{1}], {2}'.format(self.uuid, disk_names, str(ex)))

        finally:
            for struct in return_structs:
                existing = self._check_target_disk_existing_by_path(struct.installPath)
                logger.debug("after create snapshot by libvirt, expected volume[install path: %s] does%s exist."
                             % (struct.installPath, "" if existing else " not"))

            if memory_snapshot_required:
                self.dump_vm_xml_to_log()
                self.rollback_memory_snapshot(memory_snapshot_struct.installPath)


    def rollback_memory_snapshot(self, install_path):
        if not install_path.startswith("/dev/"):
            logger.debug("skip rollback memory snapshot %s, because install path is not a block device" % install_path)
            return

        mount_path = install_path.replace("/dev/", "/tmp/")
        ret = linux.umount(mount_path)
        if ret != 0:
            logger.debug("umount %s failed, %s" % (mount_path, ret))

        try:
            lvm.deactive_lv(install_path)
        except Exception as e:
            logger.debug("deactivate volume %s for memory snapshot failed on vm %s failed, %s" % (
                install_path, self.uuid, str(e)))
        


    def do_block_commit(self, task_spec, volume):
        def do_block_commit_disk(task_spec, disk_name, top, base, active_commit):
            def wait_job(_):
                logger.debug('block commit is waiting for %s blockCommit job completion' % disk_name)
                return not self._wait_for_block_job(disk_name, abort_on_error=True)

            def check_overlay_file(path):
                if not active_commit:
                    return True

                return self._check_target_disk_existing_by_path(path, True)

            def abort_block_commit_job(_):
                flag = libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_ASYNC
                if active_commit:
                    logger.debug('active commit, abort with pivot flag')
                    flag = libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_PIVOT

                try:
                    if not self.domain.blockJobInfo(disk_name, 0):
                        logger.info("block commit job finished automatic, no need to abort")
                        return True

                    self.domain.blockJobAbort(disk_name, flag)
                    logger.debug('block commit abort success, check overlay file path')
                    return True
                except Exception as e:
                    logger.warn("pivot active layer failed, %s" % e)
                    return False

            logger.debug('start block commit for disk %s, from %s, to %s, active commit: %s'
                         % (disk_name, top, base, active_commit))
            flags = libvirt.VIR_DOMAIN_BLOCK_COMMIT_RELATIVE

            # currently we only handle active commit
            if active_commit:
                # Pass a flag to libvirt to indicate that we expect a two phase
                # block job. We must tell libvirt to pivot to the new active layer (base).
                flags |= libvirt.VIR_DOMAIN_BLOCK_COMMIT_ACTIVE

            self.domain.blockCommit(disk_name, base, top, 0, flags)
            touchQmpSocketWhenExists(task_spec.vmUuid)
            logger.debug('block commit for disk %s in processing' % disk_name)

            if not linux.wait_callback_success(wait_job, timeout=d.get_remaining_timeout(),
                                               ignore_exception_in_callback=True):
                if not check_overlay_file(base):
                    raise kvmagent.KvmError('block commit failed')
                logger.debug("although the block commit job failed, device install path has been changed to %s" % base)

            if not linux.wait_callback_success(abort_block_commit_job, d.get_remaining_timeout(),
                                               ignore_exception_in_callback=True):
                raise kvmagent.KvmError('block commit abort failed')

            if not linux.wait_callback_success(check_overlay_file, base, d.get_remaining_timeout(),
                                               ignore_exception_in_callback=True):
                raise kvmagent.KvmError('block commit succeeded, but overlay file is not cleared')

            return base

        target_disk, disk_name = self._get_target_disk(volume)
        top = get_volume_actual_installpath(task_spec.top)
        base = get_volume_actual_installpath(task_spec.base)
        install_path = VmPlugin.get_source_file_by_disk(target_disk)
        active_commit = top == install_path
        with BlockCommitDaemon(task_spec, self, disk_name, top=top, base=base, active_commit=active_commit) as d:
            return do_block_commit_disk(task_spec, disk_name, task_spec.top, task_spec.base, active_commit)

    def take_volume_snapshot(self, task_spec, volume, install_path, full_snapshot=False):
        device_id = volume.deviceId
        target_disk, disk_name = self._get_target_disk(volume)
        snapshot_dir = os.path.dirname(install_path)
        if not os.path.exists(snapshot_dir):
            os.makedirs(snapshot_dir)

        previous_install_path = VmPlugin.get_source_file_by_disk(target_disk)
        back_file_len = len(self._get_backfile_chain(previous_install_path))
        # for RHEL, base image's back_file_len == 1; for ubuntu back_file_len == 0
        first_snapshot = full_snapshot and (back_file_len == 1 or back_file_len == 0)

        def take_delta_snapshot():
            backing_store_type = target_disk.type_
            source_type = 'file' if target_disk.type_ == 'file' else 'dev'
            if block_device_use_block_type() \
                and install_path.startswith('/dev/'):
                backing_store_type = 'block'
                source_type = 'dev'

            snapshot = etree.Element('domainsnapshot')
            disks = e(snapshot, 'disks')
            d = e(disks, 'disk', None, attrib={'name': disk_name, 'snapshot': 'external', 'type': backing_store_type})
            e(d, 'source', None, attrib={source_type: install_path})
            e(d, 'driver', None, attrib={'type': 'qcow2'})

            # QEMU 2.3 default create snapshots on all devices
            # but we only need for one
            self.refresh()
            for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
                if disk.target.dev_ != disk_name:
                    e(disks, 'disk', None, attrib={'name': disk.target.dev_, 'snapshot': 'no'})

            xml = etree.tostring(snapshot)
            logger.debug('creating snapshot for vm[uuid:{0}] volume[id:{1}]:\n{2}'.format(self.uuid, device_id, xml))
            snap_flags = libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY | libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA
            if os.path.exists(install_path):
                snap_flags = snap_flags | libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_REUSE_EXT

            try:
                self.domain.snapshotCreateXML(xml, snap_flags)
                return previous_install_path, install_path
            except libvirt.libvirtError as ex:
                logger.warn(linux.get_exception_stacktrace())
                if previous_install_path != install_path and \
                        linux.wait_callback_success(self._check_target_disk_existing_by_path, install_path, timeout=5):
                    logger.warn("libvirt return snapshot[path:%s] failure, but it succeed actually!" % install_path)
                    return previous_install_path, install_path

                raise kvmagent.KvmError(
                    'unable to take snapshot of vm[uuid:{0}] volume[id:{1}], {2}'.format(self.uuid, device_id, str(ex)))
            finally:
                existing = self._check_target_disk_existing_by_path(install_path)
                logger.debug("after create snapshot by libvirt, expected volume[install path: %s] does%s exist."
                             % (install_path, "" if existing else " not"))

        def take_full_snapshot():
            self.block_stream_disk(task_spec, volume)
            VmPlugin.active_volume_if_need(install_path)
            return take_delta_snapshot()

        if first_snapshot:
            # the first snapshot is always full snapshot
            # at this moment, delta snapshot returns the original volume as full snapshot
            return take_delta_snapshot()

        if full_snapshot:
            return take_full_snapshot()
        else:
            Vm.ensure_delta_snapshot_not_exceed(previous_install_path)
            return take_delta_snapshot()

    def _do_block_stream_disk(self, task_spec, target_disk, disk_name):
        install_path = VmPlugin.get_source_file_by_disk(target_disk)
        logger.debug('start block stream for disk %s' % disk_name)
        self.domain.blockRebase(disk_name, None, 0, 0)

        logger.debug('block stream for disk %s in processing' % disk_name)

        def wait_job(_):
            logger.debug('block stream is waiting for %s blockRebase job completion' % disk_name)
            return not self._wait_for_block_job(disk_name, abort_on_error=True)

        if not linux.wait_callback_success(wait_job, timeout=get_timeout(task_spec), ignore_exception_in_callback=True):
            raise kvmagent.KvmError('block stream failed')

        def wait_backing_file_cleared(_):
            return not linux.qcow2_get_backing_file(install_path)

        if not linux.wait_callback_success(wait_backing_file_cleared, timeout=60, ignore_exception_in_callback=True):
            raise kvmagent.KvmError('block stream succeeded, but backing file is not cleared')

    def block_stream_disk(self, task_spec, volume):
        target_disk, disk_name = self._get_target_disk(volume)
        top = get_volume_actual_installpath(volume.installPath)
        with MergeSnapshotDaemon(task_spec, self, disk_name, top=top):
            self._do_block_stream_disk(task_spec, target_disk, disk_name)

    def list_blk_sources(self):
        """list domain blocks (aka. domblklist) -- but with sources only"""
        tree = etree.fromstring(self.domain_xml)
        res = []

        for disk in tree.findall("devices/disk"):
            for src in disk.findall("source"):
                src_file = src.get("file")
                if src_file is None:
                    continue

                res.append(src_file)

        return res

    def get_backing_store_source_recursively(self):
        # type: () -> list
        all_disks_backing_file_chain = []
        disk_backing_file_chain = {}

        '''
        <disk type='file' device='disk'>
          <driver name='qemu' type='qcow2'/>
          <source file='/tmp/pull4.qcow2'/>
          <backingStore type='file'>
            <format type='qcow2'/>
            <source file='/tmp/pull3.qcow2'/>
            <backingStore type='file'>
              <format type='qcow2'/>
              <source file='/tmp/pull2.qcow2'/>
              <backingStore/>
            </backingStore>
          </backingStore>
          <target dev='vda' bus='virtio'/>
          <address type='pci' domain='0x0000' bus='0x00' slot='0x0a' function='0x0'/>
        </disk>
        
        An empty <backingStore/> element signals the end of the chain. 
        '''

        def get_backing_store_source(backingStore, depth):
            if backingStore.find("source") is None:
                return
            depth += 1
            disk_backing_file_chain[etree.tostring(backingStore.find('source')).split('"')[1]] = depth
            get_backing_store_source(backingStore.find('backingStore'), depth)

        tree = etree.fromstring(self.domain_xml)
        for disk in tree.findall('devices/disk'):
            depth = 0
            if disk.get("device") == 'cdrom':
                continue
            if disk.find("source") is not None:
                disk_backing_file_chain[etree.tostring(disk.find('source')).split('"')[1]] = depth
            if disk.find("backingStore") is not None:
                get_backing_store_source(disk.find('backingStore'), depth)

            all_disks_backing_file_chain.append(disk_backing_file_chain)
            disk_backing_file_chain = {}

        return all_disks_backing_file_chain

    def _build_domain_new_xml(self, volumeDicts):
        migrate_disks = {}

        for oldpath, volume in volumeDicts.items():
            _, disk_name = self._get_target_disk_by_path(oldpath)
            migrate_disks[disk_name] = volume

        xml_changed = False
        tree = etree.ElementTree(etree.fromstring(self.get_migratable_xml()))
        devices = tree.getroot().find('devices')
        for disk in tree.iterfind('devices/disk'):
            dev = disk.find('target').attrib['dev']
            new_disk = VmPlugin._get_new_disk(disk, migrate_disks.get(dev, None))
            if new_disk != disk:
                parent_index = list(devices).index(disk)
                devices.remove(disk)
                devices.insert(parent_index, new_disk)
                xml_changed = True

        if xml_changed:
            return migrate_disks.keys(), etree.tostring(tree.getroot())
        else:
            return None, None

    def migrate(self, cmd):
        if self.state == Vm.VM_STATE_SHUTDOWN:
            raise kvmagent.KvmError('vm[uuid:%s] is stopped, cannot live migrate,' % cmd.vmUuid)

        current_hostname = linux.get_host_name()
        if cmd.migrateFromDestination:
            hostname = cmd.destHostIp.replace('.', '-')
        else:
            hostname = cmd.srcHostIp.replace('.', '-')

        if current_hostname == 'localhost.localdomain' or current_hostname == 'localhost':
            # set the hostname, otherwise the migration will fail
            shell.call('hostname %s.zstack.org' % hostname)

        destUrl = "qemu+tcp://{0}/system".format(cmd.destHostManagementIp)
        tcpUri = "tcp://{0}".format(cmd.destHostIp)
        bandwidth = cmd.bandwidth if cmd.bandwidth > 0 else 0

        storage_migration_required = cmd.disks and len(cmd.disks.__dict__) != 0
        parameter_map = {}
        if storage_migration_required:
            disks, destXml = self._build_domain_new_xml(cmd.disks.__dict__)
            parameter_map[libvirt.VIR_MIGRATE_PARAM_MIGRATE_DISKS] = disks
            parameter_map[libvirt.VIR_MIGRATE_PARAM_URI] = tcpUri
            parameter_map[libvirt.VIR_MIGRATE_PARAM_DEST_XML] = destXml
            if bandwidth != 0:
                parameter_map[libvirt.VIR_MIGRATE_PARAM_BANDWIDTH] = (bandwidth + len(disks) - 1) // len(disks)
        else:
            disks, destXml = self._build_domain_new_xml({})
        logger.debug("migrate dest xml:%s" % destXml)

        flag = (libvirt.VIR_MIGRATE_LIVE |
                libvirt.VIR_MIGRATE_PEER2PEER |
                libvirt.VIR_MIGRATE_UNDEFINE_SOURCE)

        if cmd.downTime:
            self.domain.migrateSetMaxDowntime(cmd.downTime)

        if cmd.autoConverge:
            flag |= libvirt.VIR_MIGRATE_AUTO_CONVERGE

        if cmd.xbzrle:
            flag |= libvirt.VIR_MIGRATE_COMPRESSED

        if cmd.storageMigrationPolicy == 'FullCopy':
            flag |= libvirt.VIR_MIGRATE_NON_SHARED_DISK
        elif cmd.storageMigrationPolicy == 'IncCopy':
            flag |= libvirt.VIR_MIGRATE_NON_SHARED_INC

        def is_external_shared_storage():
            from zstacklib.utils.linux import get_fs_type
            share_list_type = ["fuseblk", "gpfs"] 
            vdisk_source_type = (get_fs_type(s) for s in self.list_blk_sources())
            if any(s.startswith('/dev/') for s in self.list_blk_sources()) or any(item in share_list_type for item in vdisk_source_type):
                return True

        # to workaround libvirt bug (c.f. RHBZ#1494454)
        if LIBVIRT_MAJOR_VERSION >= 4:
            if is_external_shared_storage():
                flag |= libvirt.VIR_MIGRATE_UNSAFE

        if cmd.useNuma or storage_migration_required:
            flag |= libvirt.VIR_MIGRATE_PERSIST_DEST

        stage = get_task_stage(cmd)
        timeout = get_timeout(cmd)
        class MigrateDaemon(plugin.TaskDaemon):
            def __init__(self, domain, uuid):
                super(MigrateDaemon, self).__init__(cmd, 'MigrateVm')
                self.domain = domain
                self.uuid = uuid
                self.progress_status =deque(maxlen=60)

            def _get_percent(self):
                try:
                    stats = self.domain.jobStats()
                    if libvirt.VIR_DOMAIN_JOB_DATA_REMAINING in stats and libvirt.VIR_DOMAIN_JOB_DATA_TOTAL in stats:
                        remain = stats[libvirt.VIR_DOMAIN_JOB_DATA_REMAINING]
                        total = stats[libvirt.VIR_DOMAIN_JOB_DATA_TOTAL]
                        if total == 0:
                            return

                        percent = min(99, 100.0 - remain * 100.0 / total)
                        return get_exact_percent(percent, stage)
                except libvirt.libvirtError:
                    pass
                except:
                    logger.debug(linux.get_exception_stacktrace())

            def _get_detail(self):
                try:
                    stats = self.domain.jobStats()
                    result = jsonobject.JsonObject()
                    if libvirt.VIR_DOMAIN_JOB_DATA_REMAINING in stats and libvirt.VIR_DOMAIN_JOB_DATA_TOTAL in stats:
                        remain = stats[libvirt.VIR_DOMAIN_JOB_DATA_REMAINING]
                        total = stats[libvirt.VIR_DOMAIN_JOB_DATA_TOTAL]
                        if total == 0:
                            logger.debug('the total amount of data migrated is 0')
                            return

                        result.put("remain", remain)
                        result.put("total", total)

                        if remain == 0:
                            return result

                        self.progress_status.append(remain)
                        average = sum(self.progress_status) / len(self.progress_status)
                        jobBlocked = len(self.progress_status) >= 60 and self.progress_status[0] == average
                        jobRunning = self.progress_status[0] != 0
                        if jobBlocked and jobRunning:
                            raise kvmagent.BlockJobError(
                                "the block job status is abnormal, details is ioHung. Please check backup storage and backup network.")

                        if self.progress_reporter.report.detail and self.progress_reporter.report.detail.hasattr('remain'):
                            speed = self.progress_reporter.report.detail.__getitem__('remain') - remain
                            remaining_migration_time = (remain / speed) if speed != 0 else self.progress_reporter.report.detail.__getitem__('remaining_migration_time')
                            result.put("speed", speed)
                            result.put("remaining_migration_time", remaining_migration_time)
                        return result
                except libvirt.libvirtError:
                    pass
                except kvmagent.BlockJobError as e:
                    logger.error(e)
                    self._cancel()
                except:
                    logger.debug(linux.get_exception_stacktrace())

            def _cancel(self):
                logger.debug('cancelling vm[uuid:%s] migration' % cmd.vmUuid)
                vm_block_job_cancel(self.uuid)

            def _exit(self, exc_type, exc_val, exc_tb):
                if exc_type == libvirt.libvirtError:
                    err = str(exc_val)
                    logger.warn('unable to migrate vm[uuid:%s] to %s, %s' % (cmd.vmUuid, destUrl, err))
                    if "cannot set up guest memory" in err:
                        raise kvmagent.KvmError("No enough physical memory for guest")
                    else:
                        raise kvmagent.KvmError(err)

        self._is_vm_paused_with_readonly_flag_on_disk()
        is_migrate_without_bitmaps = self._is_vm_migrate_without_dirty_bitmap()
        check_mirror_jobs(cmd.vmUuid, is_migrate_without_bitmaps)

        with MigrateDaemon(self.domain, self.uuid):
            logger.debug('migrating vm[uuid:{0}] to dest url[{1}]'.format(self.uuid, destUrl))

            if storage_migration_required:
                self.domain.migrateToURI3(destUrl, parameter_map, flag)
            else:
                self.domain.migrateToURI2(destUrl, tcpUri, destXml, flag, None, bandwidth)

        try:
            logger.debug('migrating vm[uuid:{0}] to dest url[{1}]'.format(self.uuid, destUrl))
            if not linux.wait_callback_success(self.wait_for_state_change, callback_data=None, timeout=timeout):
                try: self.domain.abortJob()
                except: pass
                raise kvmagent.KvmError('timeout after %d seconds' % timeout)
        except kvmagent.KvmError:
            raise
        except:
            logger.debug(linux.get_exception_stacktrace())

        logger.debug('successfully migrated vm[uuid:{0}] to dest url[{1}]'.format(self.uuid, destUrl))

    def _is_vm_paused_with_readonly_flag_on_disk(self):
        states = get_all_vm_states()
        state = states.get(self.uuid)
        if state != Vm.VM_STATE_PAUSED:
            return

        source_files = []
        for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
            source_file = VmPlugin.get_source_file_by_disk(disk)
            if not source_file or not source_file.startswith("/dev/"):
                continue
            source_files.append(source_file)

        fds = self._get_qemu_fd_for_lvs_in_use(source_files)
        if not fds:
            return

        if any('r' in fd for fd in fds):
            raise kvmagent.KvmError('cannot migrate vm [uuid: %s], it has read-only flags on disks' % self.uuid)

    @bash.in_bash
    def _get_qemu_fd_for_lvs_in_use(self, lv_paths):
        dm_paths = [os.path.realpath(lv_path) for lv_path in lv_paths]
        vm_pid = linux.get_vm_pid(self.uuid)
        if not vm_pid:
            return None

        lsof_lines = bash.bash_o("lsof -p %s" % vm_pid).splitlines()
        lines = linux.filter_lines_by_str_list(lsof_lines, dm_paths)
        return [line.split()[3] for line in lines]

    def _is_vm_migrate_without_dirty_bitmap(self):
        # From ZSTAC-57974, qemu version like '6.2.0-201.gca43b80.el7'
        qemu_version = qemu.get_running_version(self.uuid)
        if qemu_version == "":
            qemu_version = QEMU_VERSION
        if not is_qemu_support_migrate_with_bitmap(qemu_version):
            return True

        libvirt_version = linux.get_libvirt_version()
        if is_libvirt_support_migrate_with_bitmap(libvirt_version):
            return False

        disks_index = []
        for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
            index = VmPlugin.get_source_index_by_disk(disk)
            if not index:
                continue
            disks_index.append(index)

        if len(disks_index) > 1 and len(disks_index) != int(max(disks_index)) - int(min(disks_index)) + 1:
            return True

        # node-name : libvirt-10-format
        pattern = r'libvirt\-[0-9]+\-format'
        block_nodes, err = execute_qmp_command(self.uuid, '{ "execute": "query-named-block-nodes" }')
        if err:
            logger.warn("query-named-block-nodes failed of vm[uuid: %s]" % self.uuid)
            return True

        vm_pid = linux.find_process_by_cmdline([kvmagent.get_qemu_path(), self.uuid])
        if not vm_pid:
            logger.warn("can not find pid of vm[uuid: %s]" % self.uuid)
            return True

        qemu_command = linux.get_command_by_pid(vm_pid)
        if not qemu_command:
            logger.warn("can not find process of vm pid[pid: %s]" % vm_pid)
            return True

        #Deduplicate and verify that both contain the same elements
        qmp_node_names = list(set(re.findall(pattern, str(block_nodes))))
        qemu_command_node_names = list(set(re.findall(pattern, qemu_command)))
        if dict(Counter(qmp_node_names)) == dict(Counter(qemu_command_node_names)):
            return False

        return True

    def _interface_cmd_to_xml(self, cmd, action=None):
        vhostSrcPath = cmd.addons['vhostSrcPath'] if cmd.addons else None
        brMode = cmd.addons['brMode'] if cmd.addons else None

        if cmd.nic.type in ovs.OvsDpdkSupportVnic:
            vhostSrcPath = cmd.nic.srcPath

        if cmd.nic.type == "TFVNIC":
            interface = Vm._build_interface_xml(cmd.nic, action=action, cmd=cmd)
        else:
            interface = Vm._build_interface_xml(cmd.nic, None, vhostSrcPath, action, brMode)

        def addon():
            if cmd.addons and cmd.addons['NicQos']:
                qos = cmd.addons['NicQos']
                Vm._add_qos_to_interface(interface, qos)

        addon()

        return etree.tostring(interface)

    def _wait_vm_run_until_seconds(self, sec):
        vm_pid = linux.find_process_by_cmdline([kvmagent.get_qemu_path(), self.uuid])
        if not vm_pid:
            raise Exception('cannot find pid for vm[uuid:%s]' % self.uuid)

        up_time = linux.get_process_up_time_in_second(vm_pid)

        def wait(_):
            return linux.get_process_up_time_in_second(vm_pid) > sec

        if up_time < sec and not linux.wait_callback_success(wait, timeout=max(60, sec+5)):
            raise Exception("vm[uuid:%s] seems hang, its process[pid:%s] up-time is not increasing after %s seconds" %
                            (self.uuid, vm_pid, max(60, sec+5)))

    def attach_iso(self, cmd):
        iso = cmd.iso

        if iso.deviceId >= len(self.ISO_DEVICE_LETTERS):
            err = 'vm[uuid:%s] exceeds max iso limit, device id[%s], but only 0 ~ %d are allowed' % (self.uuid, iso.deviceId, len(self.ISO_DEVICE_LETTERS) - 1)
            logger.warn(err)
            raise kvmagent.KvmError(err)

        device_letter = self.ISO_DEVICE_LETTERS[iso.deviceId]
        dev = self._get_iso_target_dev(device_letter)
        bus = self._get_controller_type()

        if iso.path.startswith('ceph'):
            ic = IsoCeph()
            ic.iso = iso
            cdrom = ic.to_xmlobject(dev, bus)
        elif iso.path.startswith('cbd'):
            ic = IsoCbd()
            ic.iso = iso
            cdrom = ic.to_xmlobject(dev, bus)
        else:
            iso.path = get_volume_actual_installpath(iso.path)
            if iso.path.startswith('iscsi://'):
                iso.path = iscsi.connect_iscsi_target(iso.path)
                iso.type = 'block'

            iso = iso_check(iso)
            cdrom = etree.Element('disk', {'type': iso.type, 'device': 'cdrom'})
            e(cdrom, 'driver', None, {'name': 'qemu', 'type': 'raw'})
            if iso.type == 'vhostuser':
                source = e(cdrom, 'source', None, {'type': 'unix', 'path': iso.path})
                e(source, 'reconnect', None, {'enabled': 'yes', 'timeout': '10'})
            else:
                e(cdrom, 'source', None, {Vm.disk_source_attrname.get(iso.type): iso.path})
            e(cdrom, 'target', None, {'dev': dev, 'bus': bus})
            e(cdrom, 'readonly', None)

        xml = etree.tostring(cdrom)

        if LIBVIRT_MAJOR_VERSION >= 4:
            addr = find_domain_cdrom_address(self.domain.XMLDesc(0), dev)
            ridx = xml.rindex('<')
            xml = xml[:ridx] + addr.dump() + xml[ridx:]

        logger.debug('attaching ISO to the vm[uuid:%s]:\n%s' % (self.uuid, xml))

        try:
            self.domain.updateDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
        except libvirt.libvirtError as ex:
            err = str(ex)
            logger.warn('unable to attach the iso to the VM[uuid:%s], %s' % (self.uuid, err))

            if "QEMU command 'change': error connecting: Operation not supported" in err:
                raise Exception('cannot hotplug ISO to the VM[uuid:%s]. It is a libvirt bug: %s.'
                                ' you can power-off the vm and attach again.' %
                                (self.uuid, 'https://bugzilla.redhat.com/show_bug.cgi?id=1541702'))
            elif 'timed out waiting for disk tray status update' in err \
                    or 'timed out waiting to open tray' in err:
                raise Exception(
                    'unable to attach the iso to the VM[uuid:%s]. It seems met some internal error,'
                    ' you can reboot the vm and try again' % self.uuid)
            else:
                raise Exception('unable to attach the iso to the VM[uuid:%s].' % self.uuid)

        def check(_):
            me = get_vm_by_uuid(self.uuid)
            for disk in me.domain_xmlobject.devices.get_child_node_as_list('disk'):
                if disk.device_ == "cdrom" and xmlobject.has_element(disk, 'source'):
                    if disk.target.dev__ and disk.target.dev_ == dev:
                        return True
            return False

        if not linux.wait_callback_success(check, None, 30, 1):
            raise Exception('cannot attach the iso[%s] for the VM[uuid:%s]. The device is not present after 30s' %
                            (iso.path, cmd.vmUuid))

    def detach_iso(self, cmd):
        cdrom = None
        for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
            if disk.device_ == "cdrom":
                cdrom = disk
                break

        if not cdrom:
            return

        device_letter = self.ISO_DEVICE_LETTERS[cmd.deviceId]
        dev = self._get_iso_target_dev(device_letter)
        bus = self._get_controller_type()

        cdrom = etree.Element('disk', {'type': 'file', 'device': 'cdrom'})
        e(cdrom, 'driver', None, {'name': 'qemu', 'type': 'raw'})
        e(cdrom, 'target', None, {'dev': dev, 'bus': bus})
        e(cdrom, 'readonly', None)

        xml = etree.tostring(cdrom)

        if LIBVIRT_MAJOR_VERSION >= 4:
            addr = find_domain_cdrom_address(self.domain.XMLDesc(0), dev)
            ridx = xml.rindex('<')
            xml = xml[:ridx] + addr.dump() + xml[ridx:]

        logger.debug('detaching ISO from the vm[uuid:%s]:\n%s' % (self.uuid, xml))

        try:
            self.domain.updateDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_DEVICE_MODIFY_FORCE)
        except libvirt.libvirtError as ex:
            err = str(ex)
            logger.warn('unable to detach the iso from the VM[uuid:%s], %s' % (self.uuid, err))
            if 'is locked' in err and 'eject' in err:
                raise Exception(
                    'unable to detach the iso from the VM[uuid:%s]. It seems the ISO is still mounted in the operating system'
                    ', please umount it first' % self.uuid)
            else:
                raise Exception(
                    'unable to detach the iso from the VM[uuid:%s]' % self.uuid)

        def check(_):
            me = get_vm_by_uuid(self.uuid)
            for disk in me.domain_xmlobject.devices.get_child_node_as_list('disk'):
                if disk.device_ != "cdrom":
                    continue
                source_ = disk.get_child_node('source')
                if not source_ or not source_.hasattr("file"):
                    if disk.target.dev__ and disk.target.dev_ == dev:
                        return True
            return False

        if not linux.wait_callback_success(check, None, 30, 1):
            raise Exception('cannot detach the cdrom from the VM[uuid:%s]. The device is still present after 30s' %
                            self.uuid)

    def _get_controller_type(self):
        is_q35 = 'q35' in self.domain_xmlobject.os.type.machine_
        return ('ide', 'sata', 'scsi')[max(is_q35, (HOST_ARCH in ['aarch64', 'mips64el', 'loongarch64']) * 2)]

    @staticmethod
    def _get_iso_target_dev(device_letter):
        return "sd%s" % device_letter if (HOST_ARCH in ['aarch64', 'mips64el', 'loongarch64']) else 'hd%s' % device_letter

    @staticmethod
    def _get_disk_target_dev_format(bus_type):
        return {'virtio': 'vd%s', 'scsi': 'sd%s', 'sata': 'hd%s', 'ide': 'hd%s'}[bus_type]

    @staticmethod
    def _get_disk_address_type(bus_type):
        return {'virtio': 'pci', 'scsi': 'drive', 'sata': 'drive', 'ide': 'drive'}[bus_type]

    def hotplug_mem(self, memory_size):
        mem_size = (memory_size - self.get_memory()) / 1024
        if mem_size == 0:
            logger.warning('cannot online increase memory with size 0 KB, skip this operate.')
            return

        xml = "<memory model='dimm'><target><size unit='KiB'>%d</size><node>0</node></target></memory>" % mem_size
        logger.debug('hot plug memory: %d KiB' % mem_size)
        try:
            self.domain.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_AFFECT_CONFIG)
        except libvirt.libvirtError as ex:
            err = str(ex)
            logger.warn('unable to hotplug memory in vm[uuid:%s], %s' % (self.uuid, err))
            if "cannot set up guest memory" in err:
                raise kvmagent.KvmError("No enough physical memory for guest")
            elif "would exceed domain's maxMemory config" in err:
                raise kvmagent.KvmError(err + "; please check if you have rebooted the VM to make Instance Offering Online Modification take effect")
            else:
                raise kvmagent.KvmError(err)
        return

    def hotplug_cpu(self, cpu_num):

        logger.debug('set cpus: %d cpus' % cpu_num)
        try:
            self.domain.setVcpusFlags(cpu_num, libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_AFFECT_CONFIG)
        except libvirt.libvirtError as ex:
            err = str(ex)
            logger.warn('unable to set cpus in vm[uuid:%s], %s' % (self.uuid, err))

            if "requested vcpus is greater than max" in err:
                err += "; please check if you have rebooted the VM to make Instance Offering Online Modification take effect"

            raise kvmagent.KvmError(err)
        return

    @linux.retry(times=3, sleep_time=5)
    def _attach_nic(self, cmd):
        def check_device(_):
            self.refresh()
            for iface in self.domain_xmlobject.devices.get_child_node_as_list('interface'):
                if iface.mac.address_ != cmd.nic.mac:
                    continue

                if iface.mac.address_ == cmd.nic.mac:
                    # vf nic doesn't have internal name
                    if cmd.nic.pciDeviceAddress is not None:
                        return True
                    if cmd.nic.type in ovs.OvsDpdkSupportVnic:
                        return True
                    else:
                        return linux.is_network_device_existing(cmd.nic.nicInternalName)

            return False

        try:
            if check_device(None):
                return

            # if nic type is vDPA/dpdkvhostuser, create vDPA/dpdkvhostuser backends in thread.
            if cmd.nic.type in ovs.OvsDpdkSupportVnic:
                cmd.nic.srcPath = ovs.getOvsCtl(with_dpdk=True).createNicBackend(cmd.vmUuid, cmd.nic)

            # Make sure key:vmInstanceUuid exists
            if cmd.nic.type == "TFVNIC":
                cmd.put('vmInstanceUuid', cmd.vmUuid)

            xml = self._interface_cmd_to_xml(cmd, action='Attach')
            logger.debug('attaching nic:\n%s' % xml)

            if self.state == self.VM_STATE_RUNNING or self.state == self.VM_STATE_PAUSED:
                self.domain.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
            else:
                self.domain.attachDevice(xml)

            if not linux.wait_callback_success(check_device, interval=0.5, timeout=30):
                raise Exception('nic device does not show after 30 seconds')

            if cmd.nic.isolated:
                iproute.config_link_isolated(cmd.nic.nicInternalName)

        except:
            #  check one more time
            if not check_device(None):
                raise

    def attach_nic(self, cmd):
        self._wait_vm_run_until_seconds(10)
        self.timeout_object.wait_until_object_timeout('%s-attach-nic' % self.uuid)
        try:
            self._attach_nic(cmd)
        except libvirt.libvirtError as ex:
            err = str(ex)
            if 'Duplicate ID' in err:
                err = ('unable to attach a L3 network to the vm[uuid:%s], %s. This is a KVM issue, please reboot'
                       ' the vm and try again' % (self.uuid, err))
            elif 'No more available PCI slots' in err:
                err = ('vm[uuid: %s] has no more PCI slots for vm nic[mac:%s]. This is a Libvirt issue, please reboot'
                       ' the VM and try again' % (self.uuid, cmd.nic.mac))
            else:
                err = 'unable to attach a L3 network to the vm[uuid:%s], %s' % (self.uuid, err)
            raise kvmagent.KvmError(err)

        # in 10 seconds, no detach-nic operation can be performed,
        # work around libvirt bug
        self.timeout_object.put('%s-detach-nic' % self.uuid, timeout=10)

    @linux.retry(times=3, sleep_time=5)
    def _detach_nic(self, cmd):
        def check_device(_):
            self.refresh()
            for iface in self.domain_xmlobject.devices.get_child_node_as_list('interface'):
                if iface.mac.address_ == cmd.nic.mac:
                    return False

            return not iproute.is_device_ifname_exists(cmd.nic.nicInternalName)

        def wait_for_detach():
            if not linux.wait_callback_success(check_device, interval=0.5, timeout=10):
                raise Exception('NIC device is still attached after 10 seconds. Please check virtio driver or stop VM and detach again.')

        def find_vf_device_xml():
            for iface in self.domain_xmlobject.devices.get_child_node_as_list('interface'):
                if iface.type_ == 'hostdev' and iface.mac.address_ == cmd.nic.mac:
                    return iface.dump()

        if check_device(None):
            return

        try:
            # if nic type is vDPA/dpdkvhostuser, release it before detach.
            if cmd.nic.type in ovs.OvsDpdkSupportVnic:
                cmd.nic.srcPath = ovs.getOvsCtl(with_dpdk=True).destoryNicBackend(cmd.vmUuid, cmd.nic.nicInternalName)

            xml = None
            if cmd.nic.type == 'VF':
                xml = find_vf_device_xml()
            else:
                xml = self._interface_cmd_to_xml(cmd, action='Detach')
            logger.debug('detaching nic:\n%s' % xml)
            if self.state == self.VM_STATE_RUNNING or self.state == self.VM_STATE_PAUSED:
                self.domain.detachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
            else:
                self.domain.detachDevice(xml)

            wait_for_detach()
        except libvirt.libvirtError as e:
            logger.warn(linux.get_exception_stacktrace())

            # c.f. https://bugzilla.redhat.com/show_bug.cgi?id=1878659
            # support new qemu version which will raise exception when detach a nic which is already in the process of unplug
            if "is already in the process of unplug" in str(e.message):
                wait_for_detach()
            # check one more time
            if not check_device(None):
                logger.warn('failed to detach a nic[mac:%s], dump vm xml:\n%s' % (cmd.nic.mac, self.domain_xml))
                raise

    def detach_nic(self, cmd):
        self._wait_vm_run_until_seconds(10)
        self.timeout_object.wait_until_object_timeout('%s-detach-nic' % self.uuid)
        self._detach_nic(cmd)
        # in 10 seconds, no attach-nic operation can be performed,
        # to work around libvirt bug
        self.timeout_object.put('%s-attach-nic' % self.uuid, timeout=10)

    def check_device_exists(self, cmd):
        self.refresh()
        for iface in self.domain_xmlobject.devices.get_child_node_as_list('interface'):
            if iface.mac.address_ == cmd.nic.mac:
                return False
        return not iproute.is_device_ifname_exists(cmd.nic.nicInternalName)

    @linux.retry(times=3, sleep_time=5)
    def _disable_nic(self, cmd):
        if self.check_device_exists(cmd):
            return
        o = shell.call("virsh domif-setlink %s %s down" % (cmd.vmUuid, cmd.nic.nicInternalName))
        if "successfully" not in o:
            raise Exception('nic device update failed')

    def disable_nic(self, cmd):
        self._wait_vm_run_until_seconds(10)
        self.timeout_object.wait_until_object_timeout('%s-disable-nic' % self.uuid)
        self._disable_nic(cmd)
        self.timeout_object.put('%s-disable-nic' % self.uuid, timeout=10)

    @linux.retry(times=3, sleep_time=5)
    def _enable_nic(self, cmd):
        if self.check_device_exists(cmd):
            return
        o = shell.call("virsh domif-setlink %s %s up" % (cmd.vmUuid, cmd.nic.nicInternalName))
        if "successfully" not in o:
            raise Exception('nic device update failed')

    def enable_nic(self, cmd):
        self._wait_vm_run_until_seconds(10)
        self.timeout_object.wait_until_object_timeout('%s-enable-nic' % self.uuid)
        self._enable_nic(cmd)
        self.timeout_object.put('%s-enable-nic' % self.uuid, timeout=10)

    def update_nic(self, cmd):
        self._wait_vm_run_until_seconds(10)
        self.timeout_object.wait_until_object_timeout('%s-update-nic' % self.uuid)
        self._update_nic(cmd)
        self.timeout_object.put('%s-update-nic' % self.uuid, timeout=10)

    def _update_nic(self, cmd):
        if not cmd.nics:
            return

        def check_device(nic):
            self.refresh()
            for iface in self.domain_xmlobject.devices.get_child_node_as_list('interface'):
                if iface.mac.address_ == nic.mac:
                    return linux.is_network_device_existing(nic.nicInternalName)

            return False

        def get_interface(nic):
            self.refresh()
            for iface in self.domain_xmlobject.devices.get_child_node_as_list('interface'):
                if iface.mac.address_ == nic.mac:
                    return iface
            return None

        def mtu_addon(nic_xml_object, iface):
            if iface is None or iface.hasattr("mtu") is False:
                mtu_element_tmp = nic_xml_object.find("mtu")
                if mtu_element_tmp is not None:
                    nic_xml_object.remove(mtu_element_tmp)
                return

            mtu_element = nic_xml_object.find("mtu")
            if mtu_element is not None:
                mtu_element.set("size", iface.mtu.size_)
                return

            e(nic_xml_object, 'mtu', None, attrib={'size': '%d' % int(iface.mtu.size_)})

        def addon(nic_xml_object, nic):
            if cmd.addons and cmd.addons['NicQos'] and cmd.addons['NicQos'][nic.uuid]:
                qos = cmd.addons['NicQos'][nic.uuid]
                Vm._add_qos_to_interface(nic_xml_object, qos)

            iface = get_interface(nic)
            mtu_addon(nic_xml_object, iface)

        for nic in cmd.nics:
            interface = Vm._build_interface_xml(nic, action='Update')
            addon(interface, nic)
            xml = etree.tostring(interface)
            logger.debug('updating nic:\n%s' % xml)
            if self.state == self.VM_STATE_RUNNING or self.state == self.VM_STATE_PAUSED:
                self.domain.updateDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
            else:
                self.domain.updateDeviceFlags(xml)
            if not linux.wait_callback_success(check_device, nic, interval=0.5, timeout=30):
                raise Exception('nic device does not show after 30 seconds')
            if nic.isolated:
                iproute.config_link_isolated(nic.nicInternalName)

    def _check_qemuga_info(self, info):
        if info:
            for command in info["return"]["supported_commands"]:
                if command["name"] == "guest-set-user-password":
                    if command["enabled"]:
                        return True
        return False

    def _wait_until_qemuga_ready(self, timeout, uuid):
        finish_time = time.time() + (timeout / 1000)
        while time.time() < finish_time:
            state = get_all_vm_states().get(uuid)
            if state != Vm.VM_STATE_RUNNING and state != Vm.VM_STATE_PAUSED:
                raise kvmagent.KvmError("vm's state is %s, not running" % state)
            r, o, e = bash.bash_roe("virsh qemu-agent-command %s --cmd '{\"execute\":\"guest-info\"}'" % self.uuid)
            if r != 0:
                logger.warn("get guest info from vm[uuid:%s]: %s, %s" % (self.uuid, o, e))
            else:
                logger.debug("qga_json: %s" % o)
                return json.loads(o)['return']
            time.sleep(2)
        raise kvmagent.KvmError("qemu-agent service is not ready in vm...")

    def _escape_char_password(self, password):
        escape_str = "\*\#\(\)\<\>\|\"\'\/\\\$\`\&\{\}\;"
        des = ""
        for c in list(password):
            if c in escape_str:
                des += "\\"
            des += c
        return des

    def change_vm_password(self, cmd):
        uuid = self.uuid
        # check the vm state first, then choose the method in different way
        state = get_all_vm_states().get(uuid)
        timeout = 60000
        if state != Vm.VM_STATE_RUNNING:
            raise kvmagent.KvmError("vm is not running, cannot connect to qemu-ga")

        if not is_qga_connected(self.domain):
            raise kvmagent.KvmError("vm qga channel is not connected")

        # before set-user-password, we must check if os ready in the guest
        self._wait_until_qemuga_ready(timeout, uuid)
        try:
            escape_password = self._escape_char_password(cmd.accountPerference.accountPassword)
            shell.call('virsh set-user-password %s %s %s' % (self.uuid,
                                                                 cmd.accountPerference.userAccount,
                                                                 escape_password))
        except Exception as e:
            logger.warn(e.message)
            if e.message.find("child process has failed to set user password") < 0:
                raise e

            raise kvmagent.KvmError('unable to execute "chpasswd" in guest[uuid:%s], check if user[%s] existing or guest system log.'
                                    % (uuid, cmd.accountPerference.userAccount))

    def _check_snapshot_can_livemerge(self, base, top, fullrebase):
        """Check live mrege/block stream can be processed

        When qemu version <= 2.12.0, if take a block stream request and the
        blk device's max sectors << 9 less that qcow2' cluster size, the VM
        will be crashed.
        Therefore, check qemu version whether <= 2.12.0, and check all the
        block devices on the snapshot chain.
        For more detail info, ref to ZSTAC-42068.

        :param:base: string, The base qcow2 image path
        :param:top: string, The top qcow2 image path
        :param:fullrebase: bool, adjust to do full rebase, if true, the
                           base param will be ignored.
        """
        if not top.startswith('/dev'):
            return
        if LooseVersion(qemu.get_version()) > LooseVersion('2.12.0'):
            return
        checking_file = top
        while checking_file:
            max_transfer = min(
                linux.hdev_get_max_transfer_via_ioctl(checking_file),
                linux.hdev_get_max_transfer_via_segments(checking_file))
            cluster_size = linux.qcow2_get_cluster_size(checking_file)
            if cluster_size > 0 and max_transfer < cluster_size:
                msg = ('Live merge snapshot precheck failed, the qcow2 image '
                       'cluster size %s larger than the block device max '
                       'transfer  %s.') % (cluster_size, max_transfer)
                raise kvmagent.KvmError(msg)
            if checking_file == base and not fullrebase:
                break
            checking_file = self._get_back_file(checking_file)

    def merge_snapshot(self, cmd):
        _, disk_name = self._get_target_disk(cmd.volume)

        def do_pull(base, top):
            logger.debug('start block rebase [active: %s, new backing: %s]' % (top, base))

            # Double check (c.f. issue #1323)
            logger.debug('merge snapshot is checking previous block job of disk:%s' % disk_name)

            def wait_previous_job(_):
                return not self._wait_for_block_job(disk_name, abort_on_error=True)

            if not linux.wait_callback_success(wait_previous_job, timeout=d.get_remaining_timeout(), ignore_exception_in_callback=True):
                raise kvmagent.KvmError('merge snapshot failed - pending previous block job')

            self.domain.blockRebase(disk_name, base, 0)

            logger.debug('merging snapshot chain is waiting for blockRebase job of %s completion' % disk_name)

            def wait_job(_):
                return not self._wait_for_block_job(disk_name, abort_on_error=True)

            if not linux.wait_callback_success(wait_job, timeout=d.get_remaining_timeout()):
                raise kvmagent.KvmError('live merging snapshot chain failed, block job not finished')

            # Double check (c.f. issue #757)
            current_backing = self._get_back_file(top)
            if current_backing != base:
                logger.debug("live merge snapshot failed. Expected backing %s, actually backing %s" % (base, current_backing))
                raise kvmagent.KvmError('[libvirt bug] live merge snapshot failed')

            logger.debug('end block rebase [active: %s, new backing: %s]' % (top, base))

        self._check_snapshot_can_livemerge(cmd.srcPath, cmd.destPath,
                                           cmd.fullRebase)
        # confirm MergeSnapshotDaemon's cancel will be invoked before block job wait
        base = None if cmd.fullRebase else cmd.srcPath
        with MergeSnapshotDaemon(cmd, self, disk_name, top=cmd.destPath, base=base) as d:
            do_pull(base, cmd.destPath)

    def take_volumes_shallow_backup(self, task_spec, volumes, dst_backup_paths):
        if self._is_ft_vm():
            self._take_volumes_top_drive_backup(task_spec, volumes, dst_backup_paths)
        else:
            self._take_volumes_shallow_block_copy(task_spec, volumes, dst_backup_paths)

    def _take_volumes_top_drive_backup(self, task_spec, volumes, dst_backup_paths):
        class DriveBackupDaemon(plugin.TaskDaemon):
            def __init__(self, domain_uuid):
                super(DriveBackupDaemon, self).__init__(task_spec, 'TakeVolumeBackup')
                self.domain_uuid = domain_uuid

            def _exit(self, exc_type, exc_val, exc_tb):
                os.unlink(tmp_workspace)

            def _cancel(self):
                logger.debug("cancel vm[uuid:%s] backup" % self.domain_uuid)
                ImageStoreClient().stop_backup_jobs(self.domain_uuid)

        tmp_workspace = os.path.join(tempfile.gettempdir(), uuidhelper.uuid())
        with DriveBackupDaemon(self.uuid):
            self._do_take_volumes_top_drive_backup(volumes, dst_backup_paths, tmp_workspace)

    def _do_take_volumes_top_drive_backup(self, volumes, dst_backup_paths, tmp_workspace):
        args = {}
        for volume in volumes:
            target_disk, _ = self._get_target_disk(volume)
            # type: (node_name<str>, backupSpeed<int>)
            args[str(volume.deviceId)] = VmPlugin.get_disk_device_name(target_disk), 0

        dst_workspace = os.path.join(os.path.dirname(dst_backup_paths['0']), 'workspace')
        linux.mkdir(dst_workspace)
        os.symlink(dst_workspace, tmp_workspace)

        res = ImageStoreClient().top_backup_volumes(self.uuid, args.values(), tmp_workspace)

        job_res = jsonobject.loads(res)
        for device_id, dst_path in dst_backup_paths.items():
            node_name = args[device_id][0]
            back_path = os.path.join(dst_workspace, job_res[node_name].backupFile)
            linux.mkdir(os.path.dirname(dst_path))
            shutil.move(back_path, dst_path)

    def _take_volumes_shallow_block_copy(self, task_spec, volumes, dst_backup_paths):
        # type: (Vm, jsonobject.JsonObject, list[xmlobject.XmlObject], dict[str, str]) -> None
        class VolumeInfo(object):
            def __init__(self, dev_name):
                self.dev_name = dev_name  # type: str
                self.end_time = None  # type: float

        class ShallowBackupDaemon(plugin.TaskDaemon):
            def __init__(self, domain):
                super(ShallowBackupDaemon, self).__init__(task_spec, 'TakeVolumeBackup')
                self.domain = domain

            def _cancel(self):
                logger.debug("cancel vm[uuid:%s] backup" % self.domain.name())
                for v in volume_backup_info.values():
                    if self.domain.blockJobInfo(v.dev_name, 0):
                        self.domain.blockJobAbort(v.dev_name)

        volume_backup_info = {}
        for volume in volumes:
            target_disk, _ = self._get_target_disk(volume)
            volume_backup_info[str(volume.deviceId)] = VolumeInfo(target_disk.target.dev_)

        with ShallowBackupDaemon(self.domain):
            self._do_take_volumes_shallow_block_copy(volume_backup_info, dst_backup_paths)

    def _do_take_volumes_shallow_block_copy(self, volume_backup_info, dst_backup_paths):
        dom = self.domain
        flags = libvirt.VIR_DOMAIN_BLOCK_COPY_TRANSIENT_JOB | libvirt.VIR_DOMAIN_BLOCK_COPY_SHALLOW
        for device_id, v in volume_backup_info.items():
            vol_dir = os.path.dirname(dst_backup_paths[device_id])
            linux.mkdir(vol_dir)

            logger.info("start copying {}/{} ...".format(self.uuid, v.dev_name))
            dom.blockCopy(v.dev_name, "<disk type='file'><source file='{}'/><driver type='qcow2'/></disk>"
                          .format(dst_backup_paths[device_id]), None, flags)

        while time.sleep(5) or any(not v.end_time for v in volume_backup_info.values()):
            for v in volume_backup_info.values():
                if v.end_time:
                    continue

                info = dom.blockJobInfo(v.dev_name, 0)
                if not info:
                    raise Exception('blockjob not found on disk: ' + v.dev_name)
                elif info['cur'] == info['end']:
                    v.end_time = time.time()
                    logger.info("completed copying {}/{} ...".format(self.uuid, v.dev_name))

        with vm_operator.TemporaryPauseVmOperator(dom):
            for v in volume_backup_info.values():
                dom.blockJobAbort(v.dev_name)

    def find_scsi_controller_by_iothread(self, io_thread_id):
        controller_index = "0"
        vm_xml_obj = get_vm_by_uuid(self.uuid)
        for controller in vm_xml_obj.domain_xmlobject.devices.get_child_node_as_list('controller'):
            if controller.type_ == "scsi" and hasattr(controller, "driver") and controller.driver.iothread_ == str(io_thread_id):
                controller_index = controller.index_
                break
        return controller_index


    @staticmethod
    def from_virt_domain(domain):
        vm = Vm()
        vm.domain = domain
        (state, _, _, _, _) = domain.info()
        vm.state = Vm.power_state[state]
        vm.domain_xml = domain.XMLDesc(0)
        vm.domain_xmlobject = xmlobject.loads(vm.domain_xml)
        vm.uuid = vm.domain_xmlobject.name.text_

        return vm

    @staticmethod
    def from_StartVmCmd(cmd):
        use_numa = cmd.useNuma
        numa_nodes = cmd.addons.numaNodes
        machine_type = get_machineType(cmd.machineType)
        if HOST_ARCH == "aarch64" and cmd.bootMode == 'Legacy':
            raise kvmagent.KvmError("Aarch64 does not support legacy, please change boot mode to UEFI instead of Legacy on your VM or Image.")
        if cmd.architecture and cmd.architecture != HOST_ARCH:
            raise kvmagent.KvmError("Image architecture[{}] not matched host architecture[{}].".format(cmd.architecture, HOST_ARCH))
        default_bus_type = ('ide', 'sata', 'scsi')[max(machine_type == 'q35', (HOST_ARCH in ['aarch64', 'mips64el', 'loongarch64']) * 2)]
        image_platform_in_lower = cmd.imagePlatform.lower()

        # platform support use no virtio for ide/sata disk on other platform vms
        # in this case we need to deduplicate the device address because cdrom and disk can't share the same address
        # and the default address is hd[a-z] for ide/sata disk logically
        hd_device_address_deduplicate = False
        if default_bus_type in ('ide', 'sata') and image_platform_in_lower == 'other':
            hd_device_address_deduplicate = True

        elements = {}

        def make_root():
            root = etree.Element('domain')
            root.set('type', get_domain_type())
            root.set('xmlns:qemu', 'http://libvirt.org/schemas/domain/qemu/1.0')
            elements['root'] = root

        def make_memory_backing():
            root = elements['root']
            backing = e(root, 'memoryBacking')
            if cmd.useHugePage:
                e(backing, "hugepages")
                e(backing, "allocation", attrib={'mode': 'immediate'})

            if cmd.noSharePages or cmd.useHugePage:
                e(backing, "nosharepages")

            if cmd.MemAccess in "shared":
                # <access mode="shared|private"/>
                e(backing, "access", attrib={'mode': 'shared'})

        def make_cpu():
            if use_numa:
                root = elements['root']
                tune = e(root, 'cputune')

                if cmd.addons and cmd.addons.hasattr("ioThreadPins") and cmd.addons.ioThreadPins:
                    for pin in cmd.addons.ioThreadPins:
                        e(tune, "iothreadpin", attrib={"iothread": str(pin["ioThreadId"]), "cpuset": pin["pin"]})

                def on_x86_64():
                    max_vcpu = cmd.maxVcpuNum if cmd.maxVcpuNum else 128
                    e(root, 'vcpu', str(max_vcpu), {'placement': 'static', 'current': str(cmd.cpuNum)})
                    # e(root,'vcpu',str(cmd.cpuNum),{'placement':'static'})
                    if cmd.nestedVirtualization == 'host-model':
                        cpu = e(root, 'cpu', attrib={'mode': 'host-model'})
                        e(cpu, 'model', attrib={'fallback': 'allow'})
                    elif cmd.nestedVirtualization == 'host-passthrough':
                        cpu = e(root, 'cpu', attrib={'mode': 'host-passthrough'})
                        e(cpu, 'model', attrib={'fallback': 'allow'})
                    elif cmd.nestedVirtualization == 'custom':
                        cpu = e(root, 'cpu', attrib={'mode': 'custom'})
                        e(cpu, 'model', cmd.vmCpuModel, attrib={'fallback': 'allow'})
                    else:
                        cpu = e(root, 'cpu')

                    mem = cmd.memory / 1024

                    if cmd.socketNum:
                        e(cpu, 'topology', attrib={'sockets': str(cmd.socketNum), 'cores': str(cmd.cpuOnSocket), 'threads': str(cmd.threadsPerCore)})
                    else:
                        e(cpu, 'topology', attrib={'sockets': '32', 'cores': '4', 'threads': '1'})
                    numa = e(cpu, 'numa')
                    e(numa, 'cell', attrib={'id': '0', 'cpus': '0-%d' % (max_vcpu - 1), 'memory': str(mem), 'unit': 'KiB'})

                def on_aarch64():
                    max_vcpu = 8 if is_virtual_machine() else (cmd.maxVcpuNum if cmd.maxVcpuNum else 128)
                    e(root, 'vcpu', str(max_vcpu), {'placement': 'static', 'current': str(cmd.cpuNum)})
                    if is_virtual_machine():
                        cpu = e(root, 'cpu')
                        e(cpu, 'model', 'cortex-a57')
                    elif cmd.nestedVirtualization == 'host-model':
                        cpu = e(root, 'cpu', attrib={'mode': 'host-model'})
                        e(cpu, 'model', attrib={'fallback': 'allow'})
                    elif cmd.nestedVirtualization == 'custom':
                        cpu = e(root, 'cpu', attrib={'mode': 'custom'})
                        e(cpu, 'model', cmd.vmCpuModel, attrib={'fallback': 'allow'})
                    else:
                        cpu = e(root, 'cpu', attrib={'mode': 'host-passthrough'})
                        e(cpu, 'model', attrib={'fallback': 'allow'})
                    mem = cmd.memory / 1024

                    if cmd.socketNum:
                        e(cpu, 'topology', attrib={'sockets': str(cmd.socketNum), 'cores': str(cmd.cpuOnSocket), 'threads': '1'})
                    else:
                        socketNum = LibvirtAutoReconnect.capabilities.host().cells().getAttribute('num')
                        cores = str(int(max_vcpu / int(socketNum)))
                        e(cpu, 'topology', attrib={'sockets': socketNum, 'cores': cores, 'threads': '1'})
                    numa = e(cpu, 'numa')
                    e(numa, 'cell', attrib={'id': '0', 'cpus': '0-%d' % (max_vcpu - 1), 'memory': str(mem), 'unit': 'KiB'})

                def on_mips64el():
                    max_vcpu = cmd.maxVcpuNum if cmd.maxVcpuNum else 8
                    e(root, 'vcpu', str(max_vcpu), {'placement': 'static', 'current': str(cmd.cpuNum)})
                    # e(root,'vcpu',str(cmd.cpuNum),{'placement':'static'})
                    cpu = e(root, 'cpu', attrib={'mode': 'custom', 'match': 'exact', 'check': 'partial'})
                    e(cpu, 'model', str(MIPS64EL_CPU_MODEL), attrib={'fallback': 'allow'})
                    sockets = cmd.socketNum if cmd.socketNum else 2
                    mem = cmd.memory / 1024 / sockets
                    cores = max_vcpu / sockets
                    e(cpu, 'topology', attrib={'sockets': str(sockets), 'cores': str(cores), 'threads': '1'})
                    numa = e(cpu, 'numa')
                    for i in range(sockets):
                        cpus = "{0}-{1}".format(i * cores, i * cores + (cores - 1))
                        e(numa, 'cell', attrib={'id': str(i), 'cpus': str(cpus), 'memory': str(mem), 'unit': 'KiB'})

                def on_loongarch64():
                    max_vcpu = cmd.maxVcpuNum if cmd.maxVcpuNum else 32
                    e(root, 'vcpu', str(max_vcpu), {'placement': 'static', 'current': str(cmd.cpuNum)})
                    cpu = e(root, 'cpu', attrib={'mode': 'custom', 'match': 'exact', 'check': 'partial'})
                    e(cpu, 'model', str(LOONGARCH64_CPU_MODEL), attrib={'fallback': 'allow'})
                    sockets = cmd.socketNum if cmd.socketNum else 8
                    mem = cmd.memory / 1024 / sockets
                    cores = max_vcpu / sockets
                    e(cpu, 'topology', attrib={'sockets': str(sockets), 'cores': str(cores), 'threads': '1'})
                    numa = e(cpu, 'numa')
                    for i in range(sockets):
                        cpus = "{0}-{1}".format(i * cores, i * cores + (cores - 1))
                        e(numa, 'cell', attrib={'id': str(i), 'cpus': str(cpus), 'memory': str(mem), 'unit': 'KiB'})

                eval("on_{}".format(HOST_ARCH))()
            else:
                root = elements['root']
                e(root, 'vcpu', str(cmd.cpuNum), {'placement': 'static'})
                tune = e(root, 'cputune')

                if cmd.addons and cmd.addons.hasattr("ioThreadPins") and cmd.addons.ioThreadPins:
                    for pin in cmd.addons.ioThreadPins:
                        e(tune, "iothreadpin", attrib={"iothread": str(pin["ioThreadId"]), "cpuset": pin["pin"]})

                # enable nested virtualization
                def on_x86_64():
                    if cmd.nestedVirtualization == 'host-model':
                        cpu = e(root, 'cpu', attrib={'mode': 'host-model'})
                        e(cpu, 'model', attrib={'fallback': 'allow'})
                    elif cmd.nestedVirtualization == 'host-passthrough':
                        cpu = e(root, 'cpu', attrib={'mode': 'host-passthrough'})
                        e(cpu, 'model', attrib={'fallback': 'allow'})
                    elif cmd.nestedVirtualization == 'custom':
                        cpu = e(root, 'cpu', attrib={'mode': 'custom'})
                        e(cpu, 'model', cmd.vmCpuModel, attrib={'fallback': 'allow'})
                    else:
                        cpu = e(root, 'cpu')
                    return cpu

                def on_aarch64():
                    if is_virtual_machine():
                        cpu = e(root, 'cpu')
                        e(cpu, 'model', 'cortex-a57')
                    elif cmd.nestedVirtualization == 'host-model':
                        cpu = e(root, 'cpu', attrib={'mode': 'host-model'})
                        e(cpu, 'model', attrib={'fallback': 'allow'})
                    elif cmd.nestedVirtualization == 'custom':
                        cpu = e(root, 'cpu', attrib={'mode': 'custom'})
                        e(cpu, 'model', cmd.vmCpuModel, attrib={'fallback': 'allow'})
                    else:
                        cpu = e(root, 'cpu', attrib={'mode': 'host-passthrough'})
                        e(cpu, 'model', attrib={'fallback': 'allow'})
                    return cpu

                def on_mips64el():
                    cpu = e(root, 'cpu', attrib={'mode': 'custom', 'match': 'exact', 'check': 'partial'})
                    e(cpu, 'model', str(MIPS64EL_CPU_MODEL), attrib={'fallback': 'allow'})
                    return cpu

                def on_loongarch64():
                    cpu = e(root, 'cpu', attrib={'mode': 'custom', 'match': 'exact', 'check': 'partial'})
                    e(cpu, 'model', str(LOONGARCH64_CPU_MODEL), attrib={'fallback': 'allow'})
                    return cpu

                cpu = eval("on_{}".format(HOST_ARCH))()

                if cmd.socketNum:
                    e(cpu, 'topology', attrib={'sockets': str(cmd.socketNum), 'cores': str(cmd.cpuOnSocket), 'threads': str(cmd.threadsPerCore)})

                if numa_nodes:
                    numa = e(cpu, 'numa')
                    numatune = e(root, 'numatune')
                    for _, numa_node in enumerate(numa_nodes):
                        e(numatune, 'memnode', attrib={'cellid': str(numa_node.nodeID), 'mode':'preferred', 'nodeset': str(numa_node.hostNodeID)})
                        cell = e(numa, 'cell', attrib={'id': str(numa_node.nodeID), 'cpus': str(numa_node.cpus), 'memory': str(int(numa_node.memorySize)/1024), 'unit': 'KiB'})
                        distances = e(cell, 'distances')
                        for node_index, distance in enumerate(numa_node.distance):
                            e(distances, 'sibling', attrib={'id': str(node_index), 'value': str(distance)})

            if cmd.addons.cpuPinning:
                for rule in cmd.addons.cpuPinning:
                    e(tune, 'vcpupin', attrib={'vcpu': str(rule.vCpu), 'cpuset': rule.pCpuSet})

            if cmd.addons.emulatorPinning:
                e(tune, 'emulatorpin', attrib={'cpuset': str(cmd.addons.emulatorPinning)})

            def make_cpu_features():
                if cmd.nestedVirtualization == 'none':
                    return

                cpu = root.find('cpu')
                if cmd.x2apic is False:
                    # http://jira.zstack.io/browse/ZSTAC-50418
                    # for cpu mode is none, there are too many uncertain factors, so the feature will not be set.

                    e(cpu, 'feature', attrib={'name': 'x2apic', 'policy': 'disable'})

                if cmd.cpuHypervisorFeature is False:
                    e(cpu, 'feature', attrib={'name': 'hypervisor', 'policy': 'disable'})

            def make_cpu_vendor():
                if HOST_ARCH != "x86_64":
                    return
                
                if cmd.vmCpuVendorId and cmd.vmCpuVendorId != "None":
                    if cmd.nestedVirtualization in ['host-model', 'custom']:
                        model = root.find('cpu/model')
                        if model is not None:
                            model.set('vendor_id', cmd.vmCpuVendorId)
                        else:
                            model = e(cpu, 'model', attrib={'vendor_id': cmd.vmCpuVendorId})

            make_cpu_features()

            make_cpu_vendor()

        def make_memory():
            root = elements['root']
            mem = cmd.memory / 1024
            if use_numa:
                e(root, 'maxMemory', str(MAX_MEMORY), {'slots': str(16), 'unit': 'KiB'})
                # e(root,'memory',str(mem),{'unit':'k'})
                e(root, 'currentMemory', str(mem), {'unit': 'k'})
            else:
                e(root, 'memory', str(mem), {'unit': 'k'})
                e(root, 'currentMemory', str(mem), {'unit': 'k'})

        def make_os():
            root = elements['root']
            os = e(root, 'os')
            host_arch = kvmagent.host_arch

            def on_x86_64():
                e(os, 'type', 'hvm', attrib={'machine': machine_type})
                # if boot mode is UEFI
                if cmd.bootMode == "UEFI":
                    e(os, 'loader', '/usr/share/edk2.git/ovmf-x64/OVMF_CODE-pure-efi.fd', attrib={'readonly': 'yes', 'type': 'pflash'})
                    e(os, 'nvram', '/var/lib/libvirt/qemu/nvram/%s.fd' % cmd.vmInstanceUuid, attrib={'template': '/usr/share/edk2.git/ovmf-x64/OVMF_VARS-pure-efi.fd'})
                elif cmd.bootMode == "UEFI_WITH_CSM":
                    e(os, 'loader', '/usr/share/edk2.git/ovmf-x64/OVMF_CODE-with-csm.fd', attrib={'readonly': 'yes', 'type': 'pflash'})
                    e(os, 'nvram', '/var/lib/libvirt/qemu/nvram/%s.fd' % cmd.vmInstanceUuid, attrib={'template': '/usr/share/edk2.git/ovmf-x64/OVMF_VARS-with-csm.fd'})
                elif cmd.addons['loaderRom'] is not None:
                    e(os, 'loader', cmd.addons['loaderRom'], {'type': 'rom'})

            def on_aarch64():

                def on_redhat():
                    e(os, 'type', 'hvm', attrib={'arch': 'aarch64', 'machine': machine_type})
                    e(os, 'loader', '/usr/share/edk2/aarch64/QEMU_EFI-pflash.raw', attrib={'readonly': 'yes', 'type': 'pflash'})
                    e(os, 'nvram', '/var/lib/libvirt/qemu/nvram/%s.fd' % cmd.vmInstanceUuid, attrib={'template': '/usr/share/edk2/aarch64/vars-template-pflash.raw'})

                def on_debian():
                    e(os, 'type', 'hvm', attrib={'arch': 'aarch64', 'machine': machine_type})
                    e(os, 'loader', '/usr/share/OVMF/QEMU_EFI-pflash.raw', attrib={'readonly': 'yes', 'type': 'rom'})
                    e(os, 'nvram', '/var/lib/libvirt/qemu/nvram/%s.fd' % cmd.vmInstanceUuid, attrib={'template': '/usr/share/OVMF/vars-template-pflash.raw'})

                eval("on_{}".format(kvmagent.get_host_os_type()))()

            def on_mips64el():
                e(os, 'type', 'hvm', attrib={'arch': 'mips64el', 'machine': 'loongson7a'})
                e(os, 'loader', '/usr/share/qemu/ls3a_bios.bin', attrib={'readonly': 'yes', 'type': 'rom'})

            def on_loongarch64():
                e(os, 'type', 'hvm', attrib={'arch': 'loongarch64', 'machine': 'loongson7a'})
                e(os, 'loader', '{}loongarch_bios.bin'.format(qemu.get_bin_dir()), attrib={'readonly': 'yes', 'type': 'rom'})

            VmPlugin.clean_vm_firmware_flash(cmd.vmInstanceUuid)
            eval("on_{}".format(host_arch))()

            if cmd.useBootMenu:
                boot_menu_attrib = {'enable': 'yes'}

                if cmd.bootMenuSplashTimeout:
                    boot_menu_attrib['timeout'] = str(cmd.bootMenuSplashTimeout)

                e(os, 'bootmenu', attrib=boot_menu_attrib)

            if cmd.systemSerialNumber and HOST_ARCH != 'mips64el':
                e(os, 'smbios', attrib={'mode': 'sysinfo'})

        def make_sysinfo():
            if not cmd.systemSerialNumber:
                return

            root = elements['root']
            sysinfo = e(root, 'sysinfo', attrib={'type': 'smbios'})
            system = e(sysinfo, 'system')
            e(system, 'entry', cmd.systemSerialNumber, attrib={'name': 'serial'})

            if cmd.chassisAssetTag is not None:
                chassis = e(sysinfo, 'chassis')
                e(chassis, 'entry', cmd.chassisAssetTag, attrib={'name': 'asset'})

            if cmd.oemStrings is not None:
                oem_strings = e(sysinfo, 'oemStrings')
                for oem in cmd.oemStrings:
                    e(oem_strings, 'entry', oem)

        def make_features():
            root = elements['root']
            features = e(root, 'features')
            for f in ['apic', 'pae']:
                e(features, f)

            def make_acpi():
                if cmd.acpi:
                    e(features, 'acpi')

            make_acpi()
            if cmd.kvmHiddenState is True:
                kvm = e(features, "kvm")
                e(kvm, 'hidden', None, {'state': 'on'})
            if cmd.vmPortOff is True:
                e(features, 'vmport', attrib={'state': 'off'})
            if cmd.emulateHyperV is True:
                hyperv = e(features, "hyperv")
                e(hyperv, 'relaxed', attrib={'state': 'on'})
                e(hyperv, 'vapic', attrib={'state': 'on'})
                if is_hv_freq_supported(): e(hyperv, 'frequencies', attrib={'state': 'on'})
                if is_hv_synic_supported() and cmd.hypervClock:
                    e(hyperv, 'vpindex', attrib={'state': 'on'})
                    # Requires: hv-vpindex
                    e(hyperv, 'synic', attrib={'state': 'on'})
                    # Requires: hv-vpindex, hv-synic, hv-time
                    e(hyperv, 'stimer', attrib={'state': 'on'})
                # refer to: https://access.redhat.com/articles/2470791
                # increase spinlocks retries
                e(hyperv, 'spinlocks', attrib={'state': 'on', 'retries': '8191'})
                e(hyperv, 'vendor_id', attrib={'state': 'on', 'value': cmd.vendorId})
            # always set ioapic driver to kvm after libvirt 3.4.0
            if is_ioapic_supported():
                e(features, "ioapic", attrib={'driver': 'kvm'})

            if get_gic_version(cmd.cpuNum) == 2:
                e(features, "gic", attrib={'version': '2'})


        def make_qemu_commandline():
            if not os.path.exists(QMP_SOCKET_PATH):
                os.mkdir(QMP_SOCKET_PATH)

            root = elements['root']
            qcmd = e(root, 'qemu:commandline')
            vendor_id, model_name = linux.get_cpu_model()

            e(qcmd, "qemu:arg", attrib={"value": "-qmp"})
            e(qcmd, "qemu:arg", attrib={"value": "unix:{}/{}.sock,server,nowait".format(QMP_SOCKET_PATH, cmd.vmInstanceUuid)})

            args = cmd.addons['qemuCommandLine']
            if args is not None:
                for arg in args:
                    e(qcmd, "qemu:arg", attrib={"value": arg.strip('"')})

            if cmd.useColoBinary:
                e(qcmd, "qemu:arg", attrib={"value": '-L'})
                e(qcmd, "qemu:arg", attrib={"value": '/usr/share/qemu-kvm/'})

            if cmd.qemu64BitPciMmioSetup:
                if pci.need_config_pcimmio():
                    e(qcmd, "qemu:arg", attrib={"value": '-fw_cfg'})
                    e(qcmd, "qemu:arg", attrib={"value": 'opt/ovmf/X-PciMmio64Mb,string=%s'
                                                         % pci.get_bars_max_addressable_memory()})

            if cmd.coloPrimary:
                e(qcmd, "qemu:arg", attrib={"value": '-L'})
                e(qcmd, "qemu:arg", attrib={"value": '/usr/share/qemu-kvm/'})

                count = 0
                primary_host_ip = cmd.addons['primaryVmHostIp']
                for config in cmd.addons['primaryVmNicConfig']:
                    e(qcmd, "qemu:arg", attrib={"value": '-chardev'})
                    e(qcmd, "qemu:arg", attrib={"value": 'socket,id=zs-mirror-%s,host=%s,port=%s,server,nowait'
                                                          % (count, primary_host_ip, config.mirrorPort)})

                    e(qcmd, "qemu:arg", attrib={"value": '-chardev'})
                    e(qcmd, "qemu:arg", attrib={"value": 'socket,id=primary-in-s-%s,host=%s,port=%s,server,nowait'
                                                          % (count, primary_host_ip, config.primaryInPort)})
                    e(qcmd, "qemu:arg", attrib={"value": '-chardev'})
                    e(qcmd, "qemu:arg", attrib={"value": 'socket,id=secondary-in-s-%s,host=%s,port=%s,server,nowait'
                                                          % (count, primary_host_ip, config.secondaryInPort)})
                    e(qcmd, "qemu:arg", attrib={"value": '-chardev'})
                    e(qcmd, "qemu:arg", attrib={"value": 'socket,id=primary-in-c-%s,host=%s,port=%s,reconnect=1,nowait'
                                                          % (count, primary_host_ip, config.primaryInPort)})
                    e(qcmd, "qemu:arg", attrib={"value": '-chardev'})
                    e(qcmd, "qemu:arg", attrib={"value": 'socket,id=primary-out-s-%s,host=%s,port=%s,server,nowait'
                                                          % (count, primary_host_ip, config.primaryOutPort)})
                    e(qcmd, "qemu:arg", attrib={"value": '-chardev'})
                    e(qcmd, "qemu:arg", attrib={"value": 'socket,id=primary-out-c-%s,host=%s,port=%s,reconnect=1,nowait'
                                                          % (count, primary_host_ip, config.primaryOutPort)})

                    count += 1

                e(qcmd, "qemu:arg", attrib={"value": '-monitor'})
                e(qcmd, "qemu:arg", attrib={"value": 'tcp:%s:%s,server,nowait' % (primary_host_ip, cmd.addons['primaryMonitorPort'])})
            elif cmd.coloSecondary:
                e(qcmd, "qemu:arg", attrib={"value": '-L'})
                e(qcmd, "qemu:arg", attrib={"value": '/usr/share/qemu-kvm/'})
                count = 0
                for config in cmd.addons['ftSecondaryVmNicConfig']:
                    e(qcmd, "qemu:arg", attrib={"value": '-chardev'})
                    e(qcmd, "qemu:arg", attrib={"value": 'socket,id=red-mirror-%s,host=%s,port=%s'
                                                         % (count, cmd.addons['primaryVmHostIp'], config.mirrorPort)})
                    e(qcmd, "qemu:arg", attrib={"value": '-chardev'})
                    e(qcmd, "qemu:arg", attrib={"value": 'socket,id=red-secondary-%s,host=%s,port=%s'
                                                         % (count, cmd.addons['primaryVmHostIp'], config.secondaryInPort)})
                    e(qcmd, "qemu:arg", attrib={"value": '-object'})
                    if config.driverType == 'virtio':
                        e(qcmd, "qemu:arg", attrib={"value": 'filter-redirector,id=fr-mirror-%s,netdev=hostnet%s,queue=tx,'
                                                             'indev=red-mirror-%s,vnet_hdr_support' % (count, count, count)})
                        e(qcmd, "qemu:arg", attrib={"value": '-object'})
                        e(qcmd, "qemu:arg", attrib={"value": 'filter-redirector,id=fr-secondary-%s,netdev=hostnet%s,'
                                                             'queue=rx,outdev=red-secondary-%s,vnet_hdr_support' % (count, count, count)})
                        e(qcmd, "qemu:arg", attrib={"value": '-object'})
                        e(qcmd, "qemu:arg", attrib={"value": 'filter-rewriter,id=rew-%s,netdev=hostnet%s,queue=all,vnet_hdr_support'
                                                             % (count, count)})
                    else:
                        e(qcmd, "qemu:arg", attrib={"value": 'filter-redirector,id=fr-mirror-%s,netdev=hostnet%s,queue=tx,'
                                                             'indev=red-mirror-%s' % (count, count, count)})
                        e(qcmd, "qemu:arg", attrib={"value": '-object'})
                        e(qcmd, "qemu:arg", attrib={"value": 'filter-redirector,id=fr-secondary-%s,netdev=hostnet%s,'
                                                             'queue=rx,outdev=red-secondary-%s' % (count, count, count)})
                        e(qcmd, "qemu:arg", attrib={"value": '-object'})
                        e(qcmd, "qemu:arg", attrib={"value": 'filter-rewriter,id=rew-%s,netdev=hostnet%s,queue=all'
                                                             % (count, count)})
                    count += 1

                block_replication_port = cmd.addons['blockReplicationPort']
                secondary_vm_host_ip = cmd.addons['secondaryVmHostIp']
                e(qcmd, "qemu:arg", attrib={"value": '-incoming'})
                e(qcmd, "qemu:arg", attrib={"value": 'tcp:%s:%s' % (secondary_vm_host_ip, block_replication_port)})

                secondary_monitor_port = cmd.addons['secondaryMonitorPort']
                e(qcmd, "qemu:arg", attrib={"value": '-monitor'})
                e(qcmd, "qemu:arg", attrib={"value": 'tcp:%s:%s,server,nowait' % (secondary_vm_host_ip, secondary_monitor_port)})

        def make_devices():
            root = elements['root']
            devices = e(root, 'devices')
            if cmd.addons and cmd.addons['qemuPath']:
                e(devices, 'emulator', cmd.addons['qemuPath'])
            else:
                if cmd.coloPrimary or cmd.coloSecondary or cmd.useColoBinary:
                    e(devices, 'emulator', qemu.get_colo_path())
                else:
                    e(devices, 'emulator', kvmagent.get_qemu_path())

            @linux.with_arch(todo_list=['aarch64', 'mips64el', 'loongarch64'])
            def set_keyboard():
                keyboard = e(devices, 'input', None, {'type': 'keyboard', 'bus': 'usb'})
                e(keyboard, 'address', None, {'type': 'usb', 'bus': '0', 'port': '2'})

            def set_tablet():
                tablet = e(devices, 'input', None, {'type': 'tablet', 'bus': 'usb'})
                e(tablet, 'address', None, {'type':'usb', 'bus':'0', 'port':'1'})

            # no default usb controller and tablet device for appliance vm
            if cmd.isApplianceVm:
                e(devices, 'controller', None, {'type': 'usb', 'model': 'nec-xhci'})
                set_keyboard()
            else:
                set_keyboard()
                set_tablet()

            elements['devices'] = devices

        def make_cdrom():
            devices = elements['devices']

            max_cdrom_num = len(Vm.ISO_DEVICE_LETTERS)
            empty_cdrom_configs = None

            if HOST_ARCH in ['aarch64', 'mips64el', 'loongarch64']:
                # SCSI controller only supports 1 bus
                empty_cdrom_configs = [
                    EmptyCdromConfig('sd%s' % Vm.ISO_DEVICE_LETTERS[0], '0', Vm.get_iso_device_unit(0)),
                    EmptyCdromConfig('sd%s' % Vm.ISO_DEVICE_LETTERS[1], '0', Vm.get_iso_device_unit(1)),
                    EmptyCdromConfig('sd%s' % Vm.ISO_DEVICE_LETTERS[2], '0', Vm.get_iso_device_unit(2))
                ]
            else:
                if cmd.fromForeignHypervisor:
                    cdroms = cmd.addons['FIXED_CDROMS']

                    if cdroms is None:
                        empty_cdrom_configs = [
                            EmptyCdromConfig('hd%s' % Vm.ISO_DEVICE_LETTERS[0], '0', '1')
                        ]
                    else:
                        cdrom_device_id_list = cdroms.split(',')

                        empty_cdrom_configs = []
                        for i in xrange(len(cdrom_device_id_list)):
                            empty_cdrom_configs.append(
                                EmptyCdromConfig('hd%s' % Vm.ISO_DEVICE_LETTERS[i], str(i / 2), str(i % 2)))
                elif machine_type == 'q35':
                    # bus 0 unit 0 already use by root volume if it is on sata
                    empty_cdrom_configs = [
                        EmptyCdromConfig('hd%s' % Vm.ISO_DEVICE_LETTERS[0], '0', '1'),
                        EmptyCdromConfig('hd%s' % Vm.ISO_DEVICE_LETTERS[1], '0', '2'),
                        EmptyCdromConfig('hd%s' % Vm.ISO_DEVICE_LETTERS[2], '0', '3'),
                    ]
                else:  # machine_type=pc
                    # bus 0 unit 0 already use by root volume if it is on ide
                    empty_cdrom_configs = [
                        EmptyCdromConfig('hd%s' % Vm.ISO_DEVICE_LETTERS[0], '0', '1'),
                        EmptyCdromConfig('hd%s' % Vm.ISO_DEVICE_LETTERS[1], '1', '0'),
                        EmptyCdromConfig('hd%s' % Vm.ISO_DEVICE_LETTERS[2], '1', '1')
                    ]

            if len(empty_cdrom_configs) != max_cdrom_num:
                logger.error('ISO_DEVICE_LETTERS or EMPTY_CDROM_CONFIGS config error')

            # legacy_cdrom_config used for cdrom without deivce address
            # cdrom given address record from management node side
            def make_empty_cdrom(iso, legacy_cdrom_config, bootOrder, resourceUuid):
                cdrom = e(devices, 'disk', None, {'type': iso.type, 'device': 'cdrom'})
                e(cdrom, 'driver', None, {'name': 'qemu', 'type': 'raw'})
                e(cdrom, 'target', None, {'dev': legacy_cdrom_config.targetDev, 'bus': default_bus_type})

                if iso.deviceAddress:
                    e(cdrom, 'address', None, {'type': 'drive', 'controller': iso.deviceAddress.controller, 'bus': iso.deviceAddress.bus,
                     'target': iso.deviceAddress.target, 'unit': iso.deviceAddress.unit})
                else:
                    e(cdrom, 'address', None, {'type': 'drive', 'bus': legacy_cdrom_config.bus, 'unit': legacy_cdrom_config.unit})
                e(cdrom, 'readonly', None)
                e(cdrom, 'serial', resourceUuid)
                if bootOrder is not None and bootOrder > 0:
                    e(cdrom, 'boot', None, {'order': str(bootOrder)})
                return cdrom

            @linux.with_arch(['x86_64'])
            def make_floppy(file_path_list):
                if len(file_path_list) > 2:
                    raise Exception("up to 2 floppy devices can be attached")
                target_dev_index = 0
                for file_path in file_path_list:
                    if not os.path.exists(file_path):
                        continue
                    floppy = e(devices, 'disk', None, {'type': 'file', 'device': 'floppy'})
                    e(floppy, 'driver', None, {'name': 'qemu', 'type': 'raw'})
                    e(floppy, 'source', None, {'file': file_path})
                    e(floppy, 'readonly', None)
                    e(floppy, 'target', None, {'dev': generate_floppy_device_id(target_dev_index), 'type': 'fdc'})
                    target_dev_index = target_dev_index + 1

            def generate_floppy_device_id(index):
                return 'fd' + Vm.DEVICE_LETTERS[index]

            """
            if not cmd.bootIso:
                for config in empty_cdrom_configs:
                    makeEmptyCdrom(config.targetDev, config.bus, config.unit)
                return
            """
            virtio_driver_type = cmd.addons['systemVirtioDriverDeviceType'] if cmd.addons is not None else None
            if virtio_driver_type == 'VFD':
                make_floppy([SYSTEM_VIRTIO_DRIVER_PATHS['VFD_X86'], SYSTEM_VIRTIO_DRIVER_PATHS['VFD_AMD64']])

            if not cmd.cdRoms:
                return

            for iso in cmd.cdRoms:
                iso = iso_check(iso)
                cdrom_config = empty_cdrom_configs[iso.deviceId]

                if iso.isEmpty:
                    make_empty_cdrom(iso, cdrom_config, iso.bootOrder, iso.resourceUuid)
                    continue

                if iso.path.startswith('ceph'):
                    ic = IsoCeph()
                    ic.iso = iso
                    devices.append(ic.to_xmlobject(cdrom_config.targetDev, default_bus_type, cdrom_config.bus, cdrom_config.unit, iso.bootOrder))
                elif iso.path.startswith('cbd'):
                    ic = IsoCbd()
                    ic.iso = iso
                    devices.append(ic.to_xmlobject(cdrom_config.targetDev, default_bus_type, cdrom_config.bus, cdrom_config.unit, iso.bootOrder))
                elif iso.type == "vhostuser":
                    cdrom = make_empty_cdrom(iso, cdrom_config, iso.bootOrder, iso.resourceUuid)
                    source = e(cdrom, 'source', None, {'type': 'unix', 'path': iso.path})
                    e(source, 'reconnect', None, {'enabled': 'yes', 'timeout': '10'})
                else:
                    if iso.path.startswith('iscsi://'):
                        iso.path = iscsi.connect_iscsi_target(iso.path)
                        iso.type = 'block'

                    cdrom = make_empty_cdrom(iso, cdrom_config, iso.bootOrder, iso.resourceUuid)
                    e(cdrom, 'source', None, {Vm.disk_source_attrname.get(iso.type): iso.path})

        @linux.with_arch(todo_list=['x86_64'])
        def make_pm():
            root = elements['root']
            pm = e(root, 'pm')
            e(pm, 'suspend-to-disk', None, {'enabled': 'yes' if cmd.suspendToDisk else 'no'})
            e(pm, 'suspend-to-mem', None, {'enabled': 'yes' if cmd.suspendToRam else 'no'})


        def make_volumes():
            devices = elements['devices']
            #guarantee rootVolume is the first of the set
            volumes = [cmd.rootVolume]
            volumes.extend(cmd.dataVolumes)
            #When platform=other and default_bus_type=ide, the maximum number of volume is three
            if machine_type == 'q35':
                volume_hd_configs = [
                    VolumeIDEConfig('0', '0'),
                    VolumeIDEConfig('0', '4'),
                    VolumeIDEConfig('0', '5')
                ]
            else:
                volume_hd_configs = [
                    VolumeIDEConfig('0', '0'),
                    VolumeIDEConfig('1', '1'),
                    VolumeIDEConfig('1', '0')
                ]

            def quorumbased_volume(_dev_letter, _v):
                def make_backingstore(volume_path):
                    disk = etree.Element('disk', {'type': 'quorum', 'device': 'disk', 'threshold': '1', 'mode': 'primary' if cmd.coloPrimary else 'secondary'})
                    paths = linux.qcow2_get_file_chain(volume_path)
                    if len(paths) == 0:
                    # could not read qcow2
                        raise Exception("could not read qcow2")

                    backingStore = None
                    for path in paths:
                        logger.debug('disk path %s' % path)
                        xml = etree.tostring(disk)
                        logger.debug('disk xml is %s' % xml)

                        if backingStore:
                            backingStore = e(backingStore, 'backingStore', None, {'type': 'file'})
                        else:
                            backingStore = e(disk, 'backingStore', None, {'type': 'file'})

                        # if backingStore:
                        #     backingStore = e(backingStore, 'backingStore', None, {'type': 'file'})
                        # else:
                        #     backingStore = e(disk, 'backingStore', None, {'type': 'file'})

                        e(backingStore, 'format', None, {'type': 'qcow2'})
                        xml = etree.tostring(disk)
                        logger.debug('disk xml is %s' % xml)
                        if cmd.coloSecondary:
                            e(backingStore, 'active', None, {'file': cmd.cacheVolumes[0].installPath})
                            e(backingStore, 'hidden', None, {'file': cmd.cacheVolumes[1].installPath})

                        e(backingStore, 'source', None, {'file': path})

                    return disk

                disk = make_backingstore(_v.installPath)

                if _v.useVirtio:
                    e(disk, 'target', None, {'dev': 'vd%s' % _dev_letter, 'bus': 'virtio'})
                else:
                    dev_format = Vm._get_disk_target_dev_format(default_bus_type)
                    e(disk, 'target', None, {'dev': dev_format % _dev_letter, 'bus': default_bus_type})
                    if hd_device_address_deduplicate:
                        preserve_hd_device_config(disk, _v)

                return disk

            def filebased_volume(_dev_letter, _v):
                disk = etree.Element('disk', {'type': 'file', 'device': 'disk', 'snapshot': 'external'})
                driver_elements = {'name': 'qemu', 'type': linux.get_img_fmt(_v.installPath), 'cache': _v.cacheMode, 'discard': 'unmap'}
                if cmd.addons and cmd.addons['useDataPlane'] is True:
                    driver_elements['dataplane'] = 'on'
                    driver_elements['queues'] = 1
                if _v.useVirtio and _v.hasattr("multiQueues") and _v.multiQueues:
                    driver_elements["queues"] = _v.multiQueues
                if (not _v.useVirtioSCSI) and _v.useVirtio and _v.hasattr("ioThreadId") and _v.ioThreadId:
                    driver_elements["iothread"] = str(_v.ioThreadId)

                e(disk, 'driver', None, driver_elements)
                # if cmd.addons and cmd.addons['useDataPlane'] is True:
                #     e(disk, 'driver', None, {'name': 'qemu', 'type': linux.get_img_fmt(_v.installPath), 'cache': _v.cacheMode, 'queues':'1', 'dataplane': 'on'})
                # else:
                #     e(disk, 'driver', None, {'name': 'qemu', 'type': linux.get_img_fmt(_v.installPath), 'cache': _v.cacheMode})
                e(disk, 'source', None, {'file': _v.installPath})

                if _v.shareable:
                    e(disk, 'shareable')

                if _v.useVirtioSCSI:
                    e(disk, 'target', None, {'dev': 'sd%s' % _dev_letter, 'bus': 'scsi'})
                    e(disk, 'wwn', _v.wwn)
                    return disk

                if _v.useVirtio:
                    e(disk, 'target', None, {'dev': 'vd%s' % _dev_letter, 'bus': 'virtio'})
                else:
                    dev_format = Vm._get_disk_target_dev_format(default_bus_type)
                    e(disk, 'target', None, {'dev': dev_format % _dev_letter, 'bus': default_bus_type})
                    if hd_device_address_deduplicate:
                        preserve_hd_device_config(disk, _v)
                return disk

            def iscsibased_volume(_dev_letter, _v):
                def blk_iscsi():
                    bi = BlkIscsi()
                    portal, bi.target, bi.lun = _v.installPath.lstrip('iscsi://').split('/')
                    bi.server_hostname, bi.server_port = portal.split(':')
                    bi.device_letter = _dev_letter
                    bi.volume_uuid = _v.volumeUuid
                    bi.chap_username = _v.chapUsername
                    bi.chap_password = _v.chapPassword

                    return bi.to_xmlobject()

                def virtio_iscsi():
                    vi = VirtioIscsi()
                    portal, vi.target, vi.lun = _v.installPath.lstrip('iscsi://').split('/')
                    vi.server_hostname, vi.server_port = portal.split(':')
                    vi.device_letter = _dev_letter
                    vi.volume_uuid = _v.volumeUuid
                    vi.chap_username = _v.chapUsername
                    vi.chap_password = _v.chapPassword

                    return vi.to_xmlobject()

                if _v.useVirtio:
                    return virtio_iscsi()
                else:
                    return blk_iscsi()

            def nbd_volume(_dev_letter, _v, _r = None):
                if _v.shareable:
                    raise Exception('cannot recover shared volume: %s' % _v.installPath)

                r = _r if _r else get_recover_path(_v)
                if not r:
                    raise Exception('no recover path found: %s' % _v.installPath)

                if not r.startswith("nbd://"):
                    raise Exception('unexpected recover path: %s' % _v.installPath)

                disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
                driver_elements = {'name': 'qemu', 'type': 'raw', 'cache': 'none', 'discard': 'unmap'}
                if _v.useVirtio and _v.hasattr("multiQueues") and _v.multiQueues:
                    driver_elements["queues"] = _v.multiQueues
                e(disk, 'driver', None, driver_elements)

                u = urlparse.urlparse(r)
                src = e(disk, 'source', None, {'protocol': 'nbd', 'name': os.path.basename(u.path)})
                e(src, 'host', None, {'name':u.hostname, 'port': str(u.port)})

                if _v.useVirtioSCSI:
                    e(disk, 'target', None, {'dev': 'sd%s' % _dev_letter, 'bus': 'scsi'})
                    e(disk, 'wwn', _v.wwn)
                    return disk

                if _v.useVirtio:
                    e(disk, 'target', None, {'dev': 'vd%s' % _dev_letter, 'bus': 'virtio'})
                else:
                    dev_format = Vm._get_disk_target_dev_format(default_bus_type)
                    e(disk, 'target', None, {'dev': dev_format % _dev_letter, 'bus': default_bus_type})
                    if hd_device_address_deduplicate:
                        preserve_hd_device_config(disk, _v)
                return disk

            def ceph_volume(_dev_letter, _v):
                def ceph_virtio():
                    vc = VirtioCeph()
                    vc.volume = _v
                    vc.dev_letter = _dev_letter
                    return vc.to_xmlobject()

                def ceph_blk():
                    ic = BlkCeph()
                    ic.volume = _v
                    ic.dev_letter = _dev_letter
                    ic.bus_type = default_bus_type
                    return ic.to_xmlobject()

                def ceph_virtio_scsi():
                    vsc = VirtioSCSICeph()
                    vsc.volume = _v
                    vsc.dev_letter = _dev_letter
                    return vsc.to_xmlobject()

                def build_ceph_disk():
                    if _v.useVirtioSCSI:
                        disk = ceph_virtio_scsi()
                        if _v.shareable:
                            e(disk, 'shareable')
                        return disk

                    if _v.useVirtio:
                        return ceph_virtio()
                    else:
                        disk = ceph_blk()
                        if hd_device_address_deduplicate:
                            preserve_hd_device_config(disk, _v)
                        return disk

                d = build_ceph_disk()
                if _v.physicalBlockSize:
                    e(d, 'blockio', None, {'physical_block_size': str(_v.physicalBlockSize)})
                return d

            def spool_volume(_dev_letter, _v):
                imgfmt = linux.get_img_fmt(_v.installPath)
                disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
                e(disk, 'driver', None,
                  {'name': 'qemu', 'type': 'raw', 'cache': 'none', 'io': 'native'})
                e(disk, 'source', None,
                  {'protocol': 'spool', 'name': make_spool_conf(imgfmt, _dev_letter, _v)})
                e(disk, 'target', None, {'dev': 'vd%s' % _dev_letter, 'bus': 'virtio'})
                return disk

            def block_volume(_dev_letter, _v):
                disk = etree.Element('disk', {'type': 'block', 'device': 'disk', 'snapshot': 'external'})
                driver_elements = {'name': 'qemu', 'type': linux.get_img_fmt(_v.installPath), 'cache': 'none', 'io': 'native'}
                if _v.useVirtio and _v.hasattr("multiQueues") and _v.multiQueues:
                    driver_elements["queues"] = _v.multiQueues
                if (not _v.useVirtioSCSI) and _v.useVirtio and _v.hasattr("ioThreadId") and _v.ioThreadId:
                    driver_elements["iothread"] = str(_v.ioThreadId)
                e(disk, 'driver', None, driver_elements)
                e(disk, 'source', None, {'dev': _v.installPath})
                
                if _v.shareable:
                    e(disk, 'shareable')

                if _v.useVirtioSCSI:
                    e(disk, 'target', None, {'dev': 'sd%s' % _dev_letter, 'bus': 'scsi'})
                    e(disk, 'wwn', _v.wwn)
                elif _v.useVirtio:
                    e(disk, 'target', None, {'dev': 'vd%s' % _dev_letter, 'bus': 'virtio'})
                else:
                    dev_format = Vm._get_disk_target_dev_format(default_bus_type)
                    e(disk, 'target', None, {'dev': dev_format % _dev_letter, 'bus': default_bus_type})
                    if hd_device_address_deduplicate:
                        preserve_hd_device_config(disk, _v)

                return disk

            def vhost_volume(_dev_letter, _v):
                if not os.path.exists(_v.installPath):
                    raise Exception("vhostuser disk %s does not exist" % _v.installPath)
            
                disk = etree.Element('disk', {'type': 'vhostuser', 'device': 'disk', 'snapshot': 'no'})

                driver_elements = {'name': 'qemu', 'type': _v.format}
                if _v.hasattr("multiQueues") and _v.multiQueues:
                    driver_elements["queues"] = _v.multiQueues
                e(disk, 'driver', None, driver_elements)

                source = e(disk, 'source', None, {'type': 'unix', 'path': _v.installPath})
                e(source, 'reconnect', None, {'enabled': 'yes', 'timeout': '10'})

                if _v.shareable:
                    e(disk, 'shareable')

                if _v.useVirtioSCSI:
                    e(disk, 'target', None, {'dev': 'sd%s' % _dev_letter, 'bus': 'scsi'})
                    e(disk, 'wwn', _v.wwn)
                    return disk

                if _v.useVirtio:
                    e(disk, 'target', None, {'dev': 'vd%s' % _dev_letter, 'bus': 'virtio'})
                else:
                    dev_format = Vm._get_disk_target_dev_format(default_bus_type)
                    e(disk, 'target', None, {'dev': dev_format % _dev_letter, 'bus': default_bus_type})
                    if hd_device_address_deduplicate:
                        preserve_hd_device_config(disk, _v)
                return disk

            def cbd_volume(_dev_letter, _v):
                disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
                e(disk, 'driver', None, {'name': 'qemu', 'type': 'raw', 'cache': 'none'})
                e(disk, 'source', None, {'protocol': 'cbd', 'name': make_cbd_conf(_v.installPath)})
                e(disk, 'target', None, {'dev': 'vd%s' % _dev_letter, 'bus': 'virtio'})
                return disk

            def volume_qos(volume_xml_obj):
                if not cmd.addons:
                    return

                vol_qos = cmd.addons['VolumeQos']
                if not vol_qos:
                    return

                qos = vol_qos[v.volumeUuid]
                if not qos:
                    return

                if not qos.totalBandwidth and not qos.totalIops:
                    return

                iotune = e(volume_xml_obj, 'iotune')
                if qos.totalBandwidth:
                    e(iotune, 'total_bytes_sec', str(qos.totalBandwidth))
                if qos.totalIops:
                    # e(iotune, 'total_iops_sec', str(qos.totalIops))
                    e(iotune, 'read_iops_sec', str(qos.totalIops))
                    e(iotune, 'write_iops_sec', str(qos.totalIops))
                    # e(iotune, 'read_iops_sec_max', str(qos.totalIops))
                    # e(iotune, 'write_iops_sec_max', str(qos.totalIops))
                    # e(iotune, 'total_iops_sec_max', str(qos.totalIops))

            def volume_native_aio(volume_xml_obj):
                if not cmd.addons:
                    return

                vol_aio = cmd.addons['NativeAio']
                if not vol_aio:
                    return

                drivers = volume_xml_obj.getiterator("driver")
                if drivers is None or len(drivers) == 0:
                    return

                drivers[0].set("io", "native")

            def get_recover_path(v):
                u = urlparse.urlparse(v.installPath)
                qs = dict(urlparse.parse_qsl(u.query))
                return qs.get("r")

            def preserve_hd_device_config(_disk, _volume):
                if _volume.deviceAddress:
                    # just pop config and deviceAddress will be set in the next step
                    volume_hd_configs.pop(0)
                else:
                    if len(volume_hd_configs) == 0:
                        err = "insufficient IDE address."
                        logger.warn(err)
                        raise kvmagent.KvmError(err)
                    volume_ide_config = volume_hd_configs.pop(0)
                    e(_disk, 'address', None, {'type': 'drive', 'bus': volume_ide_config.bus, 'unit': volume_ide_config.unit})

            def make_volume(dev_letter, v, r, dataSourceOnly=False):
                v = file_volume_check(v)
                if r:
                    vol = nbd_volume(dev_letter, v, r)
                elif v.deviceType == 'quorum':
                    vol = quorumbased_volume(dev_letter, v)
                elif v.deviceType == 'file':
                    vol = filebased_volume(dev_letter, v)
                elif v.deviceType == 'iscsi':
                    vol = iscsibased_volume(dev_letter, v)
                elif v.deviceType == 'ceph':
                    vol = ceph_volume(dev_letter, v)
                elif v.deviceType == 'block':
                    vol = block_volume(dev_letter, v)
                elif v.deviceType == 'spool':
                    vol = spool_volume(dev_letter, v)
                elif v.deviceType == 'vhost':
                    vol = vhost_volume(dev_letter, v)
                elif v.deviceType == 'cbd':
                    vol = cbd_volume(dev_letter, v)
                else:
                    raise Exception('unknown volume deviceType: %s' % v.deviceType)

                assert vol is not None, 'vol cannot be None'
                if dataSourceOnly:
                    return vol

                Vm.set_device_address(vol, v)
                if v.bootOrder is not None and v.bootOrder > 0 and v.deviceId == 0:
                    e(vol, 'boot', None, {'order': str(v.bootOrder)})
                Vm.set_volume_qos(cmd.addons, v.volumeUuid, vol)
                Vm.set_volume_serial_id(v.volumeUuid, vol)
                volume_native_aio(vol)
                return vol

            all_ide = default_bus_type == "ide" and cmd.imagePlatform.lower() == "other"
            DEVICE_LETTERS = Vm.DEVICE_LETTERS if not all_ide else Vm.DEVICE_LETTERS.replace(Vm.ISO_DEVICE_LETTERS, "")

            volumes.sort(key=lambda d: d.deviceId)
            Vm.check_device_exceed_limit(volumes[-1].deviceId)

            def need_reverse(v):
                return v.useVirtioSCSI and v.deviceId != 0

            scsi_device_ids = [v.deviceId for v in volumes if need_reverse(v)]
            # {
            #     'vm-uuid': { 'target-dev': etree.Element-object, ...},
            # }
            rvols = {}
            for v in volumes:
                dev_letter_index = v.deviceId if not need_reverse(v) else scsi_device_ids.pop()
                dev_letter = DEVICE_LETTERS[dev_letter_index]

                r = get_recover_path(v)
                vol = make_volume(dev_letter, v, r)
                if r:
                    v.bootOrder = None
                    v.installPath = v.installPath.split('?', 1)[0]
                    target_dev = vol.find("./target").attrib['dev']
                    rvols[target_dev] = make_volume(dev_letter, v, None, True)

                devices.append(vol)

            if len(rvols) > 0:
                logger.info("vm[%s] is recovering with disks: %s" % (cmd.vmInstanceUuid, rvols.keys()))
                global VM_RECOVER_DICT
                VM_RECOVER_DICT[cmd.vmInstanceUuid] = rvols

        def make_nics():
            if not cmd.nics:
                return

            def addon(nic_xml_object):
                if cmd.addons and cmd.addons['NicQos'] and cmd.addons['NicQos'][nic.uuid]:
                    qos = cmd.addons['NicQos'][nic.uuid]
                    Vm._add_qos_to_interface(nic_xml_object, qos)

                if cmd.coloPrimary or cmd.coloSecondary:
                    Vm._ignore_colo_vm_nic_rom_file_on_interface(nic_xml_object)

            devices = elements['devices']
            vhostSrcPath = cmd.addons['vhostSrcPath'] if cmd.addons else None
            brMode = cmd.addons['brMode'] if cmd.addons else None

            for index, nic in enumerate(cmd.nics):
                if nic.type in ovs.OvsDpdkSupportVnic:
                    ovsctl = ovs.getOvsCtl(with_dpdk=True)
                    nic.srcPath = ovsctl.createNicBackend(cmd.priorityConfigStruct.vmUuid, nic)
                    interface = Vm._build_interface_xml(nic, devices, nic.srcPath, 'Attach', brMode, index)
                elif nic.type == 'TFVNIC':
                    interface = Vm._build_interface_xml(nic, devices, vhostSrcPath, 'Attach', brMode, index, cmd)
                else:
                    interface = Vm._build_interface_xml(nic, devices, vhostSrcPath, 'Attach', brMode, index)
                addon(interface)

        def make_meta():
            root = elements['root']

            e(root, 'name', cmd.vmInstanceUuid)

            io_thread_num = 0
            if cmd.coloPrimary or cmd.coloSecondary:
                io_thread_num += len(cmd.nics)
            if cmd.addons and cmd.addons.hasattr("ioThreadNum") and cmd.addons.ioThreadNum:
                io_thread_num += int(cmd.addons.ioThreadNum)
                io_thread_ids = e(root, "iothreadids")
                for pin in cmd.addons.ioThreadPins:
                    e(io_thread_ids, "iothread", None, {"id": str(pin["ioThreadId"])})
            if io_thread_num != 0:
                e(root, 'iothreads', str(io_thread_num))

            e(root, 'uuid', uuidhelper.to_full_uuid(cmd.vmInstanceUuid))
            e(root, 'description', cmd.vmName)
            e(root, 'on_poweroff', 'destroy')
            e(root, 'on_reboot', 'restart')
            e(root, 'on_crash', 'preserve' if cmd.addons['onCrash'] is None else cmd.addons['onCrash'])
            meta = e(root, 'metadata')
            zs = e(meta, 'zstack', usenamesapce=True)
            e(zs, 'internalId', str(cmd.vmInternalId))
            e(zs, 'hostManagementIp', str(cmd.hostManagementIp))
            # <clock offset="utc" />
            clock = e(root, 'clock', None, {'offset': cmd.clock})
            # <rom bar='off'/>
            if cmd.clock == 'localtime':
                if cmd.clockTrack:
                    e(clock, 'timer', None, {'name': 'rtc', 'tickpolicy': 'catchup', 'track': cmd.clockTrack})
                else:
                    e(clock, 'timer', None, {'name': 'rtc', 'tickpolicy': 'catchup'})
                e(clock, 'timer', None, {'name': 'pit', 'tickpolicy': 'delay'})
                e(clock, 'timer', None, {'name': 'hpet', 'present': 'no'})

                if cmd.hypervClock:
                    e(clock, 'timer', None, {'name': 'hypervclock', 'present': 'yes'})

        def make_vnc():
            devices = elements['devices']
            if cmd.consolePassword == None:
                vnc = e(devices, 'graphics', None, {'type': 'vnc', 'port': '5900', 'autoport': 'yes'})
            else:
                vnc = e(devices, 'graphics', None,
                        {'type': 'vnc', 'port': '5900', 'autoport': 'yes', 'passwd': str(cmd.consolePassword)})
            e(vnc, "listen", None, {'type': 'address', 'address': '0.0.0.0'})

        def make_spice():
            devices = elements['devices']
            if cmd.consolePassword == None:
                spice = e(devices, 'graphics', None, {'type': 'spice', 'port': '5900', 'autoport': 'yes'})
            else:
                spice = e(devices, 'graphics', None,
                          {'type': 'spice', 'port': '5900', 'autoport': 'yes', 'passwd': str(cmd.consolePassword)})
            e(spice, "listen", None, {'type': 'address', 'address': '0.0.0.0'})

            if is_spice_tls() == 0 and cmd.spiceChannels != None:
                for channel in cmd.spiceChannels:
                    e(spice, "channel", None, {'name': channel, 'mode': "secure"})
            e(spice, "image", None, {'compression': 'auto_glz'})
            e(spice, "jpeg", None, {'compression': 'always'})
            e(spice, "zlib", None, {'compression': 'never'})
            e(spice, "playback", None, {'compression': 'off'})
            e(spice, "streaming", None, {'mode': cmd.spiceStreamingMode})
            e(spice, "mouse", None, {'mode': 'client'})
            e(spice, "filetransfer", None, {'enable': 'yes'})
            e(spice, "clipboard", None, {'copypaste': 'yes'})

        def make_folder_sharing():
            devices = elements['devices']
            chan = e(devices, 'channel', None, {'type': 'spiceport'})
            e(chan, 'source', None, {'channel': 'org.spice-space.webdav.0'})
            e(chan, 'target', None, {'type': 'virtio', 'name': 'org.spice-space.webdav.0'})

        def make_usb_redirect():
            devices = elements['devices']
            e(devices, 'controller', None, {'type': 'usb', 'index': '0'})
            # make sure there are three usb controllers, each for USB 1.1/2.0/3.0
            @linux.on_redhat_based(DIST_NAME)
            @linux.with_arch(todo_list=['aarch64'])
            def set_default():
                # for aarch64 centos, only support default controller(qemu-xhci 3.0) on current qemu version(2.12_0-18)
                e(devices, 'controller', None, {'type': 'usb', 'index': '1'})
                e(devices, 'controller', None, {'type': 'usb', 'index': '2'})
                return True


            def set_usb2_3():
                if HOST_ARCH == 'loongarch64':
                    e(devices, 'controller', None, {'type': 'usb', 'index': '1', 'model': 'nec-xhci'})
                else:
                    e(devices, 'controller', None, {'type': 'usb', 'index': '1', 'model': 'ehci'})
                e(devices, 'controller', None, {'type': 'usb', 'index': '2', 'model': 'nec-xhci'})

                # USB2.0 Controller for redirect
                if HOST_ARCH == 'loongarch64':
                    e(devices, 'controller', None, {'type': 'usb', 'index': '3', 'model': 'nec-xhci'})
                else:
                    e(devices, 'controller', None, {'type': 'usb', 'index': '3', 'model': 'ehci'})
                e(devices, 'controller', None, {'type': 'usb', 'index': '4', 'model': 'nec-xhci'})

            def set_redirdev():
                chan = e(devices, 'channel', None, {'type': 'spicevmc'})
                e(chan, 'target', None, {'type': 'virtio', 'name': 'com.redhat.spice.0'})
                e(chan, 'address', None, {'type': 'virtio-serial'})

                redirdev1 = e(devices, 'redirdev', None, {'type': 'spicevmc', 'bus': 'usb'})
                e(redirdev1, 'address', None, {'type': 'usb', 'bus': '3', 'port': '1'})
                redirdev2 = e(devices, 'redirdev', None, {'type': 'spicevmc', 'bus': 'usb'})
                e(redirdev2, 'address', None, {'type': 'usb', 'bus': '3', 'port': '2'})
                redirdev3 = e(devices, 'redirdev', None, {'type': 'spicevmc', 'bus': 'usb'})
                e(redirdev3, 'address', None, {'type': 'usb', 'bus': '4', 'port': '1'})
                redirdev4 = e(devices, 'redirdev', None, {'type': 'spicevmc', 'bus': 'usb'})
                e(redirdev4, 'address', None, {'type': 'usb', 'bus': '4', 'port': '2'})

            if set_default():
                return
            set_usb2_3()
            not_colo_vm = not cmd.coloPrimary and not cmd.coloSecondary and not cmd.useColoBinary
            if cmd.usbRedirect and not_colo_vm:
                set_redirdev()

        def make_video():
            devices = elements['devices']
            if cmd.videoType != "qxl":
                video = e(devices, 'video')
                e(video, 'model', None, {'type': str(cmd.videoType)})
            else:
                for monitor in range(cmd.VDIMonitorNumber):
                    video = e(devices, 'video')
                    if cmd.qxlMemory is not None:
                        e(video, 'model', None, {'type': str(cmd.videoType), 'ram': str(cmd.qxlMemory.ram), 'vram': str(cmd.qxlMemory.vram),
                                                 'vgamem': str(cmd.qxlMemory.vgamem)})
                    else:
                        e(video, 'model', None, {'type': str(cmd.videoType)})


        def make_sound():
            if cmd.consoleMode == 'spice' or cmd.consoleMode == 'vncAndSpice':
                devices = elements['devices']
                if cmd.soundType is not None:
                    e(devices, 'sound', None, {'model': str(cmd.soundType)})
                else:
                    e(devices, 'sound', None, {'model': 'ich6'})

        def make_graphic_console():
            if cmd.consoleMode == 'spice':
                make_spice()
            elif cmd.consoleMode == "vnc":
                make_vnc()
            elif cmd.consoleMode == "vncAndSpice":
                make_vnc()
                make_spice()
            else:
                return

        def make_addons():
            if not cmd.addons:
                return

            devices = elements['devices']
            channel = cmd.addons['channel']
            if channel:
                basedir = os.path.dirname(channel.socketPath)
                linux.mkdir(basedir, 0777)
                chan = e(devices, 'channel', None, {'type': 'unix'})
                e(chan, 'source', None, {'mode': 'bind', 'path': channel.socketPath})
                e(chan, 'target', None, {'type': 'virtio', 'name': channel.targetName})

            cephSecretKey = cmd.addons['ceph_secret_key']
            cephSecretUuid = cmd.addons['ceph_secret_uuid']
            if cephSecretKey and cephSecretUuid:
                VmPlugin._create_ceph_secret_key(cephSecretKey, cephSecretUuid)

            pciDevices = cmd.addons['pciDevice']
            if pciDevices:
                make_pci_device(pciDevices)

            mdevDevices = cmd.addons['mdevDevice']
            if mdevDevices:
                make_mdev_device(mdevDevices)

            storageDevices = cmd.addons['storageDevice']
            if storageDevices:
                make_storage_device(storageDevices)

            usbDevices = cmd.addons['usbDevice']
            if usbDevices:
                make_usb_device(usbDevices)

            make_pvpanic(cmd.addons['panicIsa'], cmd.addons['panicHyperv'])

        # FIXME: manage scsi device in one place.
        def make_storage_device(storageDevices):
            lvm.unpriv_sgio()
            devices = elements['devices']
            for volume in storageDevices:
                if match_storage_device(volume.installPath):
                    disk = e(devices, 'disk', None, attrib={'type': 'block', 'device': 'lun', 'sgio': get_sgio_value()})
                    e(disk, 'driver', None, {'name': 'qemu', 'type': 'raw', 'cache': 'none'})
                    e(disk, 'source', None, {'dev': volume.installPath})
                    e(disk, 'target', None, {'dev': 'sd%s' % Vm.DEVICE_LETTERS[volume.deviceId], 'bus': 'scsi'})
                    Vm.set_device_address(disk, volume)

        def make_pci_device(pciDevices):
            devices = elements['devices']
            for pci in pciDevices:
                addr, spec_uuid = pci.split(',')

                if os.path.exists('/usr/lib/nvidia/sriov-manage'):
                    r, o, stderr = bash.bash_roe("/usr/lib/nvidia/sriov-manage -d %s" % addr)
                    if r != 0:
                        raise kvmagent.KvmError('failed to /usr/lib/nvidia/sriov-manage -d %s: %s, %s' % (addr, o, stderr))


                ret, out, err = bash.bash_roe("virsh nodedev-detach pci_%s" % addr.replace(':', '_').replace('.', '_'))
                if ret != 0:
                    raise kvmagent.KvmError('failed to nodedev-detach %s: %s, %s' % (addr, out, err))

                if match_pci_device(addr):
                    hostdev = e(devices, "hostdev", None, {'mode': 'subsystem', 'type': 'pci', 'managed': 'no'})
                    e(hostdev, "driver", None, {'name': 'vfio'})
                    source = e(hostdev, "source")
                    e(source, "address", None, {
                        "domain": hex(0) if len(addr.split(":")) == 2 else hex(int(addr.split(":")[0], 16)),
                        "bus": hex(int(addr.split(":")[-2], 16)),
                        "slot": hex(int(addr.split(":")[-1].split(".")[0], 16)),
                        "function": hex(int(addr.split(":")[-1].split(".")[1], 16))
                    })
                else:
                    raise kvmagent.KvmError(
                       'can not find pci device for address %s' % addr)
                if spec_uuid:
                    rom_file = os.path.join(PCI_ROM_PATH, spec_uuid)
                    # only turn bar on when rom file exists
                    if os.path.exists(rom_file):
                        e(hostdev, "rom", None, {'bar': 'on', 'file': rom_file})

        def make_mdev_device(mdevUuids):
            devices = elements['devices']
            for mdevUuid in mdevUuids:
                hostdev = e(devices, "hostdev", None, {'mode': 'subsystem', 'type': 'mdev', 'model': 'vfio-pci', 'managed': 'yes'})
                source = e(hostdev, "source")
                # convert mdevUuid to 8-4-4-4-12 format
                e(source, "address", None, { "uuid": uuidhelper.to_full_uuid(mdevUuid) })

        def make_usb_device(usbDevices):
            def reserve_port(bus):
                port = usb_port_dict[bus]
                usb_port_dict[bus] += 1
                return port

            usb_manger = linux.VmUsbManager()
            if HOST_ARCH in ['aarch64', 'mips64el', 'loongarch64']:
                next_uhci_port = 3
            else:
                next_uhci_port = 2
            next_ehci_port = 1
            next_xhci_port = 1
            usb_port_dict = {
                0: next_uhci_port,
                1: next_ehci_port,
                2: next_xhci_port
            }

            devices = elements['devices']
            for usb in usbDevices:
                if match_usb_device(usb):
                    if usb.split(":")[5] == "PassThrough":
                        hostdev = e(devices, "hostdev", None, {'mode': 'subsystem', 'type': 'usb', 'managed': 'yes'})
                        source = e(hostdev, "source")
                        e(source, "address", None, {
                            "bus": str(int(usb.split(":")[0])),
                            "device": str(int(usb.split(":")[1]))
                        })
                        e(source, "vendor", None, {
                            "id": hex(int(usb.split(":")[2], 16))
                        })
                        e(source, "product", None, {
                            "id": hex(int(usb.split(":")[3], 16))
                        })

                        # get controller index from usbVersion
                        # eg. 1.1 -> 0
                        # eg. 2.0.0 -> 1
                        # eg. 3 -> 2
                        bus = usb_manger.request_slot(int(usb.split(":")[4][0]))
                        e(hostdev, "address", None, {'type': 'usb', 'bus': str(bus), 'port': str(reserve_port(bus))})

                    if usb.split(":")[5] == "Redirect":
                        redirdev = e(devices, "redirdev", None, {'bus': 'usb', 'type': 'tcp'})
                        e(redirdev, "source", None, {'mode': 'connect', 'host': usb.split(":")[7], 'service': usb.split(":")[6]})

                        # get controller index from usbVersion
                        # eg. 1.1 -> 0
                        # eg. 2.0.0 -> 1
                        # eg. 3 -> 2
                        bus = usb_manger.request_slot(int(usb.split(":")[4][0]))
                        e(redirdev, "address", None,
                                        {'type': 'usb', 'bus': str(bus), 'port': str(reserve_port(bus))})

                else:
                    raise kvmagent.KvmError('cannot find usb device %s', usb)

        @linux.with_arch(['x86_64'])
        def make_pvpanic(panic_isa, panic_hyperv):
            devices = elements['devices']
            if panic_hyperv: # maybe None
                e(devices, 'panic', None, {'model' : 'hyperv'})
            if panic_isa: # maybe None
                isa_panic = e(devices, 'panic', None, {'model' : 'isa'})
                e(isa_panic, 'address', None, {'type' : 'isa', 'iobase' : '0x505'})

        #TODO(weiw) validate here
        def match_storage_device(install_path):
            return True

        # TODO(WeiW) Validate here
        def match_pci_device(addr):
            return True

        def match_usb_device(addr):
            if len(addr.split(':')) == 8:
                return True
            else:
                return False

        def make_balloon_memory():
            if cmd.memBalloon is None:
                return
            devices = elements['devices']
            b = e(devices, 'memballoon', None, {'model': 'virtio'})
            e(b, 'stats', None, {'period': '10'})
            if cmd.memBalloon.deviceAddress:
                e(b, 'address', None, {'type': 'pci', 'domain': cmd.memBalloon.deviceAddress.domain, 'bus': cmd.memBalloon.deviceAddress.bus,
                 'slot': cmd.memBalloon.deviceAddress.slot, 'function': cmd.memBalloon.deviceAddress.function})
            if kvmagent.get_host_os_type() == "debian":
                e(b, 'address', None, {'type': 'pci', 'controller': '0', 'bus': '0x00', 'slot': '0x04', 'function':'0x0'})

        def make_console():
            devices = elements['devices']
            if cmd.consoleLogToFile:
                logfilename = '%s-vm-kernel.log' % cmd.vmInstanceUuid
                logpath = os.path.join(tempfile.gettempdir(), logfilename)

                serial = e(devices, 'serial', None, {'type': 'pty'})
                e(serial, 'target', None, {'port': '0'})
                e(serial, 'log', None, {'file': logpath})
                console = e(devices, 'console', None, {'type': 'pty'})
                e(console, 'target', None, {'type': 'serial', 'port': '0'})
                e(console, 'log', None, {'file': logpath})
            else:
                serial = e(devices, 'serial', None, {'type': 'pty'})
                e(serial, 'target', None, {'port': '0'})
                console = e(devices, 'console', None, {'type': 'pty'})
                e(console, 'target', None, {'type': 'serial', 'port': '0'})

        def make_sec_label():
            root = elements['root']
            e(root, 'seclabel', None, {'type': 'none'})

        def make_controllers():
            devices = elements['devices']
            e(devices, 'controller', None, {'type': 'scsi', 'model': 'virtio-scsi'})

            for vol in cmd.dataVolumes:
                if not vol.useVirtioSCSI:
                    continue
                if vol.hasattr("ioThreadId") and vol.ioThreadId:
                    controller_xml = e(devices, 'controller', None, {'type': 'scsi', 'model': 'virtio-scsi', 'index': str(vol.controllerIndex)})
                    e(controller_xml, 'address', None, {'type': 'pci'})
                    e(controller_xml, 'driver', None, {'iothread': str(vol.ioThreadId)})
                    e(controller_xml, 'alias', None, {'name': 'scsi{0}'.format(vol.ioThreadId)})

            if machine_type in ['q35', 'virt']:
                if HOST_ARCH != 'loongarch64':
                    controller = e(devices, 'controller', None, {'type': 'sata', 'index': '0'})
                    e(controller, 'alias', None, {'name': 'sata'})
                    e(controller, 'address', None, {'type': 'pci', 'domain': '0', 'bus': '0', 'slot': '0x1f', 'function': '2'})
                pci_idx_generator = range(cmd.pciePortNums + 3).__iter__()
                e(devices, 'controller', None, {'type': 'pci', 'model': 'pcie-root', 'index': str(pci_idx_generator.next())})
                e(devices, 'controller', None, {'type': 'pci', 'model': 'dmi-to-pci-bridge', 'index': str(pci_idx_generator.next())})

                for _ in xrange(cmd.predefinedPciBridgeNum):
                    e(devices, 'controller', None, {'type': 'pci', 'model': 'pci-bridge', 'index': str(pci_idx_generator.next())})

                for i in pci_idx_generator:
                    e(devices, 'controller', None, {'type': 'pci', 'model': 'pcie-root-port', 'index': str(i)})
            else:
                if not cmd.predefinedPciBridgeNum:
                    return

                for i in xrange(cmd.predefinedPciBridgeNum):
                    e(devices, 'controller', None, {'type': 'pci', 'index': str(i + 1), 'model': 'pci-bridge'})

        def add_cpu_vendor_id_to_cpu_flags():

            def get_cpu_flags_from_xml(libvirtXml):
                with tempfile.NamedTemporaryFile(delete=False) as f:
                    f.write(libvirtXml)
                    tmpFile = f.name

                cmd = r'''virsh domxml-to-native qemu-argv --xml %s | grep -oE "\-cpu '[^']+'|\-cpu [^ ]+" | awk -F '-cpu[ ]*' '{print $2}' | sed -e "s/^'//;s/'$//" ''' % tmpFile
                r, o, e = bash.bash_roe(cmd)
                os.remove(tmpFile)

                if r == 0 and o.strip() != "":
                    return o.strip()

            if cmd.nestedVirtualization not in ['host-passthrough', 'none']:
                return
            
            root = elements['root']
            libvirtXml = etree.tostring(root)
            cpuFlags = get_cpu_flags_from_xml(libvirtXml)

            # qemu64 is used for x86_64 guests, when no -cpu argument is given to QEMU, 
            # or no <cpu> is provided in libvirt XML.
            if not cpuFlags and cmd.nestedVirtualization == 'none':
                cpuFlags = "qemu64"

            if cpuFlags:
                qcmd = e(root, 'qemu:commandline')
                e(qcmd, "qemu:arg", attrib={"value": "-cpu"})
                e(qcmd, "qemu:arg", attrib={"value": "{},vendor={}".format(cpuFlags, cmd.vmCpuVendorId)})

        make_root()
        make_meta()
        make_cpu()
        make_memory()
        make_os()
        make_sysinfo()
        make_features()
        make_devices()
        make_video()
        make_sound()
        make_nics()
        make_volumes()
        make_pm()

        if not cmd.addons or cmd.addons['noConsole'] is not True:
            make_graphic_console()
        make_addons()
        make_balloon_memory()
        make_console()
        make_sec_label()
        make_controllers()
        if is_spiceport_driver_supported() and cmd.consoleMode in ["spice", "vncAndSpice"] and not cmd.coloPrimary and not cmd.coloSecondary:
            make_folder_sharing()
        # appliance vm doesn't need any cdrom or usb controller
        if not cmd.isApplianceVm:
            make_cdrom()
            make_usb_redirect()

        if cmd.additionalQmp:
            make_qemu_commandline()

        if cmd.useHugePage or cmd.MemAccess in "shared" or cmd.noSharePages:
            make_memory_backing()

        if HOST_ARCH == "x86_64" and cmd.vmCpuVendorId and cmd.vmCpuVendorId != "None":
            add_cpu_vendor_id_to_cpu_flags()    

        root = elements['root']
        xml = etree.tostring(root)

        vm = Vm()
        vm.uuid = cmd.vmInstanceUuid

        if cmd.addons["userDefinedXmlHookScript"] is not None:
            xml_hook_script = base64.b64decode(cmd.addons["userDefinedXmlHookScript"])
            vm.set_user_defined_xml_hook(xml_hook_script)

        if cmd.addons["userDefinedXml"] is not None:
            vm.domain_xml = base64.b64decode(cmd.addons["userDefinedXml"])
            vm.domain_xmlobject = xmlobject.loads(vm.domain_xml)
        else:
            vm.domain_xml = xml
            vm.domain_xmlobject = xmlobject.loads(xml)
        return vm

    @staticmethod
    def _build_interface_xml(nic, devices=None, vhostSrcPath=None, action=None, brMode=None, index=0, cmd=None):
        if nic.pciDeviceAddress is not None and nic.srcPath is None:
            iftype = 'hostdev'
            device_attr = {'type': iftype, 'managed': 'yes'}
        elif vhostSrcPath is not None:
            iftype = 'vhostuser'
            device_attr = {'type': iftype}
        elif nic.type == "MACVLAN":
            iftype = 'direct'
        elif nic.type == 'TFVNIC':
            iftype = 'ethernet'
            device_attr = {'type': iftype}
        else:
            iftype = 'bridge'
            device_attr = {'type': iftype}

        if devices:
            interface = e(devices, 'interface', None, device_attr)
        else:
            interface = etree.Element('interface', attrib=device_attr)

        e(interface, 'mac', None, attrib={'address': nic.mac})
        if action != 'Update' and action != 'Detach':
            e(interface, 'alias', None, {'name': 'net%s' % nic.nicInternalName.split('.')[1]})

        if iftype != 'hostdev' and iftype != "direct" and nic.type not in ovs.OvsDpdkSupportVnic:
            e(interface, 'mtu', None, attrib={'size': '%d' % nic.mtu})

        # logger.warn("nic.state : [%s]" % nic.state)
        if hasattr(nic, 'state') and nic.state == 'disable' :
            e(interface, 'link', None, attrib={'state': 'down'})

        if iftype == 'hostdev':
            domain, bus, slot, function = parse_pci_device_address(nic.pciDeviceAddress)
            source = e(interface, 'source')
            e(source, 'address', None, attrib={'type': 'pci', 'domain': '0x' + domain, 'bus': '0x' + bus, 'slot': '0x' + slot, 'function': '0x' + function})
            e(interface, 'driver', None, attrib={'name': 'vfio'})
            if nic.vlanId is not None:
                vlan = e(interface, 'vlan')
                e(vlan, 'tag', None, attrib={'id': nic.vlanId})
        elif iftype == 'vhostuser':
            if brMode != 'mocbr' and nic.type not in ovs.OvsDpdkSupportVnic:
                e(interface, 'source', None, attrib={'type': 'unix', 'path': vhostSrcPath, 'mode': 'client'})
                e(interface, 'driver', None, attrib={'queues': '16', 'vhostforce': 'on'})
            elif nic.type in ovs.OvsDpdkSupportVnic:
                e(interface, 'source', None, attrib={'type': 'unix', 'path': vhostSrcPath, 'mode': 'server'})
            else:
                e(interface, 'source', None, attrib={'type': 'unix', 'path': '/var/run/phynic{}'.format(index+1), 'mode':'server'})
                e(interface, 'driver', None, attrib={'queues': '8'})
        elif iftype == 'direct':
            nicDev = nic.physicalInterface
            if nic.vlanId is not None:
                nicDev = linux.make_vlan_eth_name(nic.physicalInterface, nic.vlanId)
            e(interface, 'source', None, attrib={'dev': nicDev, 'mode': 'vepa'})
        elif nic.type == 'TFVNIC':
            e(interface, 'target', None, attrib={'dev': nic.nicInternalName})
        else:
            e(interface, 'source', None, attrib={'bridge': nic.bridgeName})
            e(interface, 'target', None, attrib={'dev': nic.nicInternalName})

        if nic.pci is not None and (iftype == 'bridge' or iftype == 'direct' or iftype == 'vhostuser'):
            e(interface, 'address', None, attrib={'type': nic.pci.type, 'domain': nic.pci.domain, 'bus': nic.pci.bus, 'slot': nic.pci.slot, "function": nic.pci.function})
        else:
            e(interface, 'address', None, attrib={'type': "pci"})

        if nic.cleanTraffic and iftype == 'bridge':
            if nic.ips:
                ip4Addr = None
                ip6Addrs = []
                for addr in nic.ips:
                    version = netaddr.IPAddress(addr).version
                    if version == 4:
                        ip4Addr = addr
                    else:
                        ip6Addrs.append(addr)
                # ipv4 nic
                if ip4Addr is not None:
                    filterref = e(interface, 'filterref', None, {'filter': 'clean-traffic'})
                    e(filterref, 'parameter', None, {'name': 'IP', 'value': ip4Addr})
            else:
                # no ip nic only filter by mac
                filterref = e(interface, 'filterref', None, {'filter': 'clean-traffic'})

        if iftype != 'hostdev':
            if nic.driverType:
                e(interface, 'model', None, attrib={'type': nic.driverType})
            elif nic.useVirtio:
                e(interface, 'model', None, attrib={'type': 'virtio'})
            else:
                e(interface, 'model', None, attrib={'type': 'e1000'})

            if nic.driverType == 'virtio' and nic.vHostAddOn.queueNum != 1:
                e(interface, 'driver ', None, attrib={'name': 'vhost', 'txmode': 'iothread', 'ioeventfd': 'on', 'event_idx': 'off', 'queues': str(nic.vHostAddOn.queueNum), 'rx_queue_size': str(nic.vHostAddOn.rxBufferSize) if nic.vHostAddOn.rxBufferSize is not None else '1024', 'tx_queue_size': str(nic.vHostAddOn.txBufferSize) if nic.vHostAddOn.txBufferSize is not None else '1024'})

        if nic.bootOrder is not None and nic.bootOrder > 0:
            e(interface, 'boot', None, attrib={'order': str(nic.bootOrder)})

        if iftype == 'ethernet' and action == 'Attach':
            vrouter_cmd = [
                'vrouter-port-control',
                '--oper=add',
                '--vm_project_uuid=%s' % transform_to_tf_uuid(cmd.accountUuid),
                '--instance_uuid=%s' % transform_to_tf_uuid(cmd.vmInstanceUuid),
                '--vm_name=',
                '--uuid=%s' % transform_to_tf_uuid(nic.uuid),
                '--vn_uuid=%s' % transform_to_tf_uuid(nic.l2NetworkUuid),
                '--port_type=NovaVMPort',
                '--tap_name=%s' % nic.nicInternalName,
                '--mac=%s' % nic.mac,
                '--ip_address=%s' % nic.ipForTf,
                '--ipv6_address=',
                '--tx_vlan_id=-1',
                '--rx_vlan_id=-1',
            ]
            notify_vrouter(vrouter_cmd)

        return interface

    @staticmethod
    def _ignore_colo_vm_nic_rom_file_on_interface(interface):
        e(interface, 'driver', None, attrib={'name': 'qemu'})
        e(interface, 'rom', None, attrib={'file': ''})

    @staticmethod
    def _add_qos_to_interface(interface, qos):
        if not qos.outboundBandwidth and not qos.inboundBandwidth:
            return

        bandwidth = e(interface, 'bandwidth')
        if qos.outboundBandwidth:
            e(bandwidth, 'outbound', None, {'average': str(qos.outboundBandwidth / 1024 / 8)})
        if qos.inboundBandwidth:
            e(bandwidth, 'inbound', None, {'average': str(qos.inboundBandwidth / 1024 / 8)})

def _stop_world():
    http.AsyncUirHandler.STOP_WORLD = True
    VmPlugin.queue_singleton.queue.put("exit")

def block_volume_over_incorrect_driver(volume):
    return volume.deviceType == "file" and volume.installPath.startswith("/dev/")

def volume_support_block_node(volume):
    return volume.deviceType != "vhost"

def file_volume_check(volume):
    # `file` support has been removed with block/char devices since qemu-6.0.0
    # https://github.com/qemu/qemu/commit/8d17adf34f501ded65a106572740760f0a75577c

    # libvirt 6.0 use -blockdev to define disk, driver is specified rather than inferred
    if block_volume_over_incorrect_driver(volume) and block_device_use_block_type():
        volume.deviceType = 'block'
    return volume


def iso_check(iso):
    iso.type = "file"

    if iso.isEmpty:
        return iso
    if iso.path.startswith("/dev/") and block_device_use_block_type():
        iso.type = "block"

    if iso.protocol and iso.protocol.lower() == "vhost":
        iso.type = "vhostuser"

    return iso

def execute_qmp_command(domain_id, command):
    return qmp.execute_qmp_command(domain_id, command)

def get_vm_blocks(domain_id):
    blocks, err = execute_qmp_command(domain_id, '{ "execute": "query-block" }')
    if err:
        raise kvmagent.KvmError(err)

    if not blocks:
        raise kvmagent.KvmError("No blocks found on vm[uuid:{}]".format(domain_id))

    return blocks


# Deprecation, use get_disk_device_name instead.
def get_block_node_name_by_disk_name(domain_id, disk_name):
    all_blocks = get_vm_blocks(domain_id)
    block = filter(lambda b: disk_name in b['qdev'].split("/"), all_blocks)[0]
    if LooseVersion(LIBVIRT_VERSION) < LooseVersion("6.0.0"):
        return block['device']
    return block["inserted"]['node-name']


def get_vm_migration_caps(domain_id, cap_key):
    caps, err = execute_qmp_command(domain_id, '{"execute": "query-migrate-capabilities"}')
    if err:
        logger.warn("query-migrate-capabilities: %s: %s" % (domain_id, err))
        return None

    for cap in caps:
        if cap["capability"] == cap_key:
            return cap["state"]
    return None


def check_mirror_jobs(domain_id, migrate_without_bitmaps):
    try:
        ImageStoreClient().stop_backup_jobs(domain_id)
    except Exception as e:
        raise kvmagent.KvmError('clear backup jobs error %s' % str(e))

    if not get_vm_migration_caps(domain_id, "dirty-bitmaps"):
        return

    if migrate_without_bitmaps:
        execute_qmp_command(domain_id, '{"execute": "migrate-set-capabilities","arguments":'
                                       '{"capabilities":[ {"capability": "dirty-bitmaps", "state":false}]}}')


def get_block_file_content_by_disk_name(domain_id, disk_name):
    all_blocks = get_vm_blocks(domain_id)
    no_prefix_name = disk_name.replace("drive-", "")
    block = filter(lambda b: b.get('device') == disk_name or b.get('device') == no_prefix_name or
                             (b.get('inserted') and b['inserted'].get('node-name') == disk_name) or
                             (b.get('qdev') and no_prefix_name in b['qdev'].split("/")), all_blocks)

    if len(block) == 0:
        raise kvmagent.KvmError("No blocks found[uuid:{}, disk_name:{}]".format(domain_id, disk_name))
    return block[0]['inserted']['file']


def check_install_path_by_qmp(domain_id, disk_name, path):
    file_content = get_block_file_content_by_disk_name(domain_id, disk_name)
    logger.info("get %s file content from qmp: %s" % (disk_name, file_content))
    r_path = get_volume_actual_installpath(path)
    if r_path in file_content:
        return True

    # ceph file example: "json:{\"driver\": \"raw\", \"file\": {\"pool\": \"11111\", \"image\": \"ca46af50ab8742b68e464e9b23b05598\"}"
    if r_path.startswith("ceph://"):
        strs = path.replace('ceph://', '').split('/')
        return strs[0] in file_content and strs[1] in file_content

    return False


def vm_block_job_cancel(vm):
    retry_times = 30
    interval = 2
    for times in range(retry_times):
        try:
            job_ids = qmp.get_block_job_ids(vm)
            if not job_ids:
                logger.debug('Block job successfully cancelled.')
                return
            for job_id in job_ids:
                qmp.block_job_cancel(vm, job_id)
        except libvirt.libvirtError as e:
            logger.debug('failed to cancel vm[uuid:%s] block copy, details is %s' % (vm, e))
            return
        time.sleep(interval)
    vm_block_job_yank(vm)


def vm_block_job_yank(vm):
    if not qmp.do_yank(vm):
        return

    retry_times = 20
    interval = 3
    for times in range(retry_times):
        try:
            if not qmp.get_block_job_ids(vm):
                logger.debug("Block job successfully cancelled.")
                return
        except libvirt.libvirtError as e:
            logger.debug('failed to force cancel vm[uuid:%s] block copy, details is %s' % (vm, e))
            return
        time.sleep(interval)


class VmPlugin(kvmagent.KvmAgent):
    KVM_START_VM_PATH = "/vm/start"
    KVM_STOP_VM_PATH = "/vm/stop"
    KVM_PAUSE_VM_PATH = "/vm/pause"
    KVM_RESUME_VM_PATH = "/vm/resume"
    KVM_REBOOT_VM_PATH = "/vm/reboot"
    KVM_DESTROY_VM_PATH = "/vm/destroy"
    KVM_ONLINE_CHANGE_CPUMEM_PATH = "/vm/online/changecpumem"
    KVM_ONLINE_INCREASE_CPU_PATH = "/vm/increase/cpu"
    KVM_ONLINE_INCREASE_MEMORY_PATH = "/vm/increase/mem"
    KVM_GET_CONSOLE_PORT_PATH = "/vm/getvncport"
    KVM_VM_SYNC_PATH = "/vm/vmsync"
    KVM_VOLUME_SYNC_PATH = "/vm/volumesync"
    KVM_ATTACH_VOLUME = "/vm/attachdatavolume"
    KVM_DETACH_VOLUME = "/vm/detachdatavolume"
    KVM_MIGRATE_VM_PATH = "/vm/migrate"
    KVM_GET_CPU_XML_PATH = "/vm/get/cpu/xml"
    KVM_COMPARE_CPU_FUNCTION_PATH = "/vm/compare/cpu/function"
    KVM_BLOCK_LIVE_MIGRATION_PATH = "/vm/blklivemigration"
    KVM_VM_CHECK_VOLUME_PATH = "/vm/volume/check"
    KVM_TAKE_VOLUME_SNAPSHOT_PATH = "/vm/volume/takesnapshot"
    KVM_CHECK_VOLUME_SNAPSHOT_PATH = "/vm/volume/checksnapshot"
    KVM_TAKE_VOLUME_BACKUP_PATH = "/vm/volume/takebackup"
    KVM_TAKE_VOLUME_MIRROR_PATH = "/vm/volume/takemirror"
    KVM_GET_VOLUME_MIRROR_MODE_PATH = "/vm/volume/getmirrormode"
    KVM_CANCEL_VOLUME_MIRROR_PATH = "/vm/volume/cancelmirror"
    KVM_QUERY_VOLUME_MIRROR_PATH = "/vm/volume/querymirror"
    KVM_QUERY_MIRROR_LATENCY_BOUNDARY_PATH = "/vm/volume/querylatencyboundary"
    KVM_QUERY_BLOCKJOB_STATUS = "/vm/volume/queryblockjobstatus"
    KVM_BLOCK_STREAM_VOLUME_PATH = "/vm/volume/blockstream"
    KVM_BLOCK_COMMIT_VOLUME_PATH = "/vm/volume/blockcommit"
    KVM_TAKE_VOLUMES_SNAPSHOT_PATH = "/vm/volumes/takesnapshot"
    KVM_TAKE_VOLUMES_BACKUP_PATH = "/vm/volumes/takebackup"
    KVM_CANCEL_VOLUME_BACKUP_JOBS_PATH = "/vm/volume/cancel/backupjobs"
    KVM_CANCEL_VOLUME_BACKUP_JOB_PATH = "/vm/volume/cancel/backupjob"
    KVM_MERGE_SNAPSHOT_PATH = "/vm/volume/mergesnapshot"
    KVM_LOGOUT_ISCSI_TARGET_PATH = "/iscsi/target/logout"
    KVM_LOGIN_ISCSI_TARGET_PATH = "/iscsi/target/login"
    KVM_ATTACH_NIC_PATH = "/vm/attachnic"
    KVM_DETACH_NIC_PATH = "/vm/detachnic"
    KVM_CHANGE_NIC_STATE_PATH = "/vm/changenicstate"
    KVM_UPDATE_NIC_PATH = "/vm/updatenic"
    KVM_CREATE_SECRET = "/vm/createcephsecret"
    KVM_ATTACH_ISO_PATH = "/vm/iso/attach"
    KVM_DETACH_ISO_PATH = "/vm/iso/detach"
    KVM_VM_RECOVER_VOLUMES_PATH = "/vm/recover/volumes"
    KVM_VM_CHECK_RECOVER_PATH = "/vm/recover/check"
    KVM_VM_CHECK_STATE = "/vm/checkstate"
    KVM_VM_CHANGE_PASSWORD_PATH = "/vm/changepasswd"
    KVM_SET_VOLUME_BANDWIDTH = "/set/volume/bandwidth"
    KVM_DELETE_VOLUME_BANDWIDTH = "/delete/volume/bandwidth"
    KVM_GET_VOLUME_BANDWIDTH = "/get/volume/bandwidth"
    KVM_SET_NIC_QOS = "/set/nic/qos"
    KVM_GET_NIC_QOS = "/get/nic/qos"
    KVM_HARDEN_CONSOLE_PATH = "/vm/console/harden"
    KVM_DELETE_CONSOLE_FIREWALL_PATH = "/vm/console/deletefirewall"
    HOT_PLUG_PCI_DEVICE = "/pcidevice/hotplug"
    HOT_UNPLUG_PCI_DEVICE = "/pcidevice/hotunplug"
    ATTACH_PCI_DEVICE_TO_HOST = "/pcidevice/attachtohost"
    DETACH_PCI_DEVICE_FROM_HOST = "/pcidevice/detachfromhost"
    HOT_PLUG_MDEV_DEVICE = "/mdevdevice/hotplug"
    HOT_UNPLUG_MDEV_DEVICE = "/mdevdevice/hotunplug"
    KVM_ATTACH_USB_DEVICE_PATH = "/vm/usbdevice/attach"
    KVM_DETACH_USB_DEVICE_PATH = "/vm/usbdevice/detach"
    RELOAD_USB_REDIRECT_PATH = "/vm/usbdevice/reload"
    CHECK_MOUNT_DOMAIN_PATH = "/check/mount/domain"
    KVM_RESIZE_VOLUME_PATH = "/volume/resize"
    VM_PRIORITY_PATH = "/vm/priority"
    UPLOAD_FILE_GUEST_TOOLS_FOR_VM_PATH = "/vm/guesttools/upload_file"
    EXEC_CMD_IN_VM_PATH = "/vm/guesttools/exec"
    ATTACH_GUEST_TOOLS_ISO_TO_VM_PATH = "/vm/guesttools/attachiso"
    DETACH_GUEST_TOOLS_ISO_FROM_VM_PATH = "/vm/guesttools/detachiso"
    GET_VM_GUEST_TOOLS_INFO_PATH = "/vm/guesttools/getinfo"
    GET_VM_METRICS_ROUTING_STATUS_PATH = "/vm/guesttools/getroutingstatus"
    KVM_GET_VM_FIRST_BOOT_DEVICE_PATH = "/vm/getfirstbootdevice"
    KVM_CONFIG_PRIMARY_VM_PATH = "/primary/vm/config"
    KVM_CONFIG_SECONDARY_VM_PATH = "/secondary/vm/config"
    KVM_START_COLO_SYNC_PATH = "/start/colo/sync"
    KVM_REGISTER_PRIMARY_VM_HEARTBEAT = "/register/primary/vm/heartbeat"
    CHECK_COLO_VM_STATE_PATH = "/check/colo/vm/state"
    WAIT_COLO_VM_READY_PATH = "/wait/colo/vm/ready"
    ROLLBACK_QUORUM_CONFIG_PATH = "/rollback/quorum/config"
    FAIL_COLO_PVM_PATH = "/fail/colo/pvm"
    GET_VM_DEVICE_ADDRESS_PATH = "/vm/getdeviceaddress"
    GET_VIRTUALIZER_INFO_PATH = "/vm/getvirtualizerinfo"
    SET_EMULATOR_PINNING_PATH = "/vm/emulatorpinning"
    SYNC_VM_CLOCK_PATH = "/vm/clock/sync"
    SET_SYNC_VM_CLOCK_TASK_PATH = "/vm/clock/sync/task"
    KVM_SYNC_VM_DEVICEINFO_PATH = "/sync/vm/deviceinfo"
    CLEAN_FIRMWARE_FLASH = "/clean/firmware/flash"
    APPLY_MEMORY_BALLOON_PATH = "/vm/apply/memory/balloon"
    KVM_NOTIFY_TF_NIC_PATH = "/vm/nodifytfnic"
    TAKE_VM_CONSOLE_SCREENSHOT_PATH = "/vm/console/screenshot"
    FSTRIM_VM_PATH = "/vm/fstrim"
    VM_CONSOLE_LOGROTATE_PATH = "/etc/logrotate.d/vm-console-log"

    SET_VM_IOTHREADPIN_PATH = "/vm/setiothreadpin"
    DEL_VM_IOTHREADPIN_PATH = "/vm/deliothreadpin"
    GET_VM_IOTHREADPIN_PATH = '/vm/getiothreadpin'
    SET_VM_SCSI_CONTROLLER = '/vm/setscsicontroller'
    DEL_VM_SCSI_CONTROLLER = '/vm/delscsicontroller'

    SSH_KEY_PAIR_ATTACH_TO_VM = "/sshkeypair/attach"
    SSH_KEY_PAIR_DETACH_FROM_VM = "/sshkeypair/detach"

    DETACH_VIRTIO_DRIVER_PATH = "/vm/virtio/detach"

    SET_VM_VF_NIC_STATE = "/vm/vfnic/state"

    VM_OP_START = "start"
    VM_OP_STOP = "stop"
    VM_OP_REBOOT = "reboot"
    VM_OP_MIGRATE = "migrate"
    VM_OP_DESTROY = "destroy"
    VM_OP_SUSPEND = "suspend"
    VM_OP_RESUME = "resume"

    GUESTTOOLS_STATE_NOT_CONNECT = "Not Connected"
    GUESTTOOLS_STATE_NOT_RUNNING = "NotRunning"
    GUESTTOOLS_STATE_RUNNING = "Running"

    timeout_object = linux.TimeoutObject()
    queue_singleton = VmPluginQueueSingleton()
    secret_keys = {}
    vm_heartbeat = {}

    if not os.path.exists(QMP_SOCKET_PATH):
        os.mkdir(QMP_SOCKET_PATH)

    def _record_operation(self, uuid, op):
        j = VmOperationJudger(op)
        self.timeout_object.put(uuid, j, 300)

    def _remove_operation(self, uuid):
        self.timeout_object.remove(uuid)

    def _get_operation(self, uuid):
        o = self.timeout_object.get(uuid)
        if not o:
            return None
        return o[0]

    def _prepare_ebtables_for_mocbr(self, cmd):
        brMode = cmd.addons['brMode'] if cmd.addons else None
        if brMode != 'mocbr':
            return

        l3mapping = cmd.addons['l3mapping'] if cmd.addons else None
        if not l3mapping:
            return

        if not cmd.nics:
            return

        mappings = {}  # mac -> l3uuid
        for ele in l3mapping:
            m = ele.split("-")
            mappings[m[0]] = m[1]

        EBTABLES_CMD = ebtables.get_ebtables_cmd()
        for nic in cmd.nics:
            ns = "{}_{}".format(nic.bridgeName, mappings[nic.mac])
            outerdev = "outer%s" % ip.get_namespace_id(ns)
            rule = " -t nat -A PREROUTING -i {} -d {} -j dnat --to-destination ff:ff:ff:ff:ff:ff".format(outerdev, nic.mac)
            bash.bash_r(EBTABLES_CMD + rule)
        bash.bash_r("ebtables-save | uniq | ebtables-restore")

    def umount_snapshot_path(self, mount_path):
        @linux.retry(times=15, sleep_time=1)
        def wait_path_unused(path):
            used_process = linux.linux_lsof(path)
            if len(used_process) != 0:
                raise RetryException("path %s still used: %s" % (path, used_process))

        try:
            wait_path_unused(mount_path)
        finally:
            used_process = linux.linux_lsof(mount_path)
            if len(used_process) == 0:
                linux.umount(mount_path)
                linux.rm_dir_force(mount_path)

    def _start_vm(self, cmd):
        try:
            vm = get_vm_by_uuid_no_retry(cmd.vmInstanceUuid, False)

            if vm:
                if vm.state == Vm.VM_STATE_RUNNING:
                    # http://jira.zstack.io/browse/ZSTAC-26937
                    #raise kvmagent.KvmError(
                    #    'vm[uuid:%s, name:%s] is already running' % (cmd.vmInstanceUuid, vm.get_name()))
                    logger.debug('vm[uuid:%s, name:%s] is already running' % (cmd.vmInstanceUuid, vm.get_name()))
                    return
                else:
                    vm.destroy()

            vm = Vm.from_StartVmCmd(cmd)

            if cmd.memorySnapshotPath:
                snapshot_path = None
                mount_path = None
                if cmd.memorySnapshotPath.startswith("/dev/"):
                    if not os.path.exists(cmd.memorySnapshotPath):
                        lvm.active_lv(cmd.memorySnapshotPath, False)

                    mount_path = cmd.memorySnapshotPath.replace("/dev/", "/tmp/")
                    if not linux.is_mounted(mount_path):
                        linux.mount(cmd.memorySnapshotPath, mount_path)

                    snapshot_path = mount_path + '/' + mount_path.rsplit('/', 1)[-1]
                else:
                    snapshot_path = cmd.memorySnapshotPath

                try:
                    vm.restore(snapshot_path)
                finally:
                    if mount_path:
                        self.umount_snapshot_path(mount_path)

                        lvm.deactive_lv(cmd.memorySnapshotPath)
                return

            wait_console = True if not cmd.addons or cmd.addons['noConsole'] is not True else False
            self._prepare_ebtables_for_mocbr(cmd)
            vm.start(cmd.timeout, cmd.createPaused, wait_console)
            for nic in cmd.nics:
                if nic.isolated:
                    iproute.config_link_isolated(nic.nicInternalName)
        except libvirt.libvirtError as e:
            logger.warn(linux.get_exception_stacktrace())

            # c.f. https://access.redhat.com/solutions/2735671
            if "org.fedoraproject.FirewallD1 was not provided" in str(e.message):
                _stop_world()  # to trigger libvirtd restart
                raise kvmagent.KvmError(
                    'unable to start vm[uuid:%s, name:%s], libvirt error: %s' % (
                    cmd.vmInstanceUuid, cmd.vmName, str(e)))

            if "Device or resource busy" in str(e.message):
                raise kvmagent.KvmError(
                    'unable to start vm[uuid:%s, name:%s], libvirt error: %s' % (
                    cmd.vmInstanceUuid, cmd.vmName, str(e)))

            # c.f. http://jira.zstack.io/browse/ZSTAC-54965
            if "could not find capabilities for domaintype=kvm" in str(e.message) \
                    or "does not support virt type 'kvm'" in str(e.message):
                # check kvm is available
                if not os.path.exists("/dev/kvm"):
                    raise kvmagent.KvmError(
                        'unable to start vm[uuid:%s, name:%s], missing directory %s, libvirt error: %s' % (
                        cmd.vmInstanceUuid, cmd.vmName, "/dev/kvm", str(e)))

                # check kvm_intel or kvm_amd mod is loaded
                if not os.path.exists("/sys/module/kvm_intel") and not os.path.exists("/sys/module/kvm_amd"):
                    raise kvmagent.KvmError(
                        'unable to start vm[uuid:%s, name:%s], missing kvm_intel or kvm_amd module, libvirt error: %s' % (
                        cmd.vmInstanceUuid, cmd.vmName, str(e)))

                # check qemu --version
                try:
                    qemu.get_version_from_exe_file(qemu.get_path(), error_out=True)
                except Exception as e:
                    raise kvmagent.KvmError(
                        'unable to start vm[uuid:%s, name:%s], check qemu --version failed, libvirt error: %s' % (
                        cmd.vmInstanceUuid, cmd.vmName, str(e)))
            try:
                vm = get_vm_by_uuid(cmd.vmInstanceUuid)
                if vm and vm.state != Vm.VM_STATE_RUNNING:
                    raise kvmagent.KvmError(
                       'vm[uuid:%s, name:%s, state:%s] is not in running state, libvirt error: %s' % (
                        cmd.vmInstanceUuid, cmd.vmName, vm.state, str(e)))

            except kvmagent.KvmError:
                raise kvmagent.KvmError(
                    'unable to start vm[uuid:%s, name:%s], libvirt error: %s' % (cmd.vmInstanceUuid, cmd.vmName, str(e)))



    def _cleanup_iptable_chains(self, chain, data):
        if 'vnic' not in chain.name:
            return False

        vnic_name = chain.name.split('-')[0]
        if vnic_name not in data:
            logger.debug('clean up defunct vnic chain[%s]' % chain.name)
            return True
        return False

    @kvmagent.replyerror
    def attach_iso(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        vm = get_vm_by_uuid(cmd.vmUuid)
        vm.attach_iso(cmd)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def detach_iso(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        vm = get_vm_by_uuid(cmd.vmUuid)
        vm.detach_iso(cmd)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def attach_nic(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AttachNicResponse()

        vm = get_vm_by_uuid(cmd.vmUuid)
        vm.attach_nic(cmd)

        for iface in vm.domain_xmlobject.devices.get_child_node_as_list('interface'):
            if iface.mac.address_ != cmd.nic.mac:
                continue

            virtualDeviceInfo = VirtualDeviceInfo()
            virtualDeviceInfo.deviceAddress.bus = iface.address.bus_
            virtualDeviceInfo.deviceAddress.function = iface.address.function_
            virtualDeviceInfo.deviceAddress.type = iface.address.type_
            virtualDeviceInfo.deviceAddress.domain = iface.address.domain_
            virtualDeviceInfo.deviceAddress.slot = iface.address.slot_
            rsp.virtualDeviceInfoList.append(virtualDeviceInfo)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def detach_nic(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        # Deal with notify vrouter when vm expunge
        if cmd.nic.type == 'TFVNIC':
            vrouter_cmd = [
                'vrouter-port-control',
                '--oper=delete',
                '--uuid=%s' % transform_to_tf_uuid(cmd.nic.uuid)
            ]
            notify_vrouter(vrouter_cmd)
        vm = get_vm_by_uuid(cmd.vmUuid, False)
        if not vm:
            return jsonobject.dumps(rsp)

        vm.detach_nic(cmd)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def change_nic_state(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        vm = get_vm_by_uuid(cmd.vmUuid, False)
        if not vm:
            return jsonobject.dumps(rsp)
        if cmd.state == "enable":
            vm.enable_nic(cmd)
        elif cmd.state == "disable":
            vm.disable_nic(cmd)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def notify_tf_nic(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        # Deal with update nic request form migration
        for nic in cmd.nics:
            if nic.type != 'TFVNIC':
                continue
            if "add" == cmd.sugonSdnAction:
                vrouter_cmd = [
                    'vrouter-port-control',
                    '--oper=add',
                    '--vm_project_uuid=%s' % transform_to_tf_uuid(cmd.accountUuid),
                    '--instance_uuid=%s' % transform_to_tf_uuid(cmd.vmInstanceUuid),
                    '--vm_name=',
                    '--uuid=%s' % transform_to_tf_uuid(nic.uuid),
                    '--vn_uuid=%s' % transform_to_tf_uuid(nic.l2NetworkUuid),
                    '--port_type=NovaVMPort',
                    '--tap_name=%s' % nic.nicInternalName,
                    '--mac=%s' % nic.mac,
                    '--ip_address=%s' % nic.ipForTf,
                    '--ipv6_address=',
                    '--tx_vlan_id=-1',
                    '--rx_vlan_id=-1',
                ]
                notify_vrouter(vrouter_cmd)
            elif "delete" == cmd.sugonNicCfg.sugonSdnAction:
                # notify vrouter agent nic removed from dest host when migrate failed
                # when migrate success, notify vrouter agent removed src host.
                vrouter_cmd = [
                    'vrouter-port-control',
                    '--oper=delete',
                    '--uuid=%s' % transform_to_tf_uuid(nic.uuid)
                ]
                notify_vrouter(vrouter_cmd)
        return jsonobject.dumps(rsp)
    
    @kvmagent.replyerror
    def update_nic(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        vm = get_vm_by_uuid(cmd.vmInstanceUuid)
        vm.update_nic(cmd)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def start_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = StartVmResponse()
        try:
            self._record_operation(cmd.vmInstanceUuid, self.VM_OP_START)

            self._start_vm(cmd)
            logger.debug('successfully started vm[uuid:%s, name:%s]' % (cmd.vmInstanceUuid, cmd.vmName))
        except kvmagent.KvmError as e:
            e_str = linux.get_exception_stacktrace()
            logger.warn(e_str)
            if "burst" in e_str and "Illegal" in e_str and "rate" in e_str:
                rsp.error = "QoS exceed max limit, please check and reset it in zstack"
            elif "cannot set up guest memory" in e_str:
                logger.warn('unable to start vm[uuid:%s], %s' % (cmd.vmInstanceUuid, e_str))
                rsp.error = "No enough physical memory for guest"
            else:
                rsp.error = e_str
            err = self.handle_vfio_irq_conflict(cmd.vmInstanceUuid)
            if err != "":
                rsp.error = "%s, details: %s" % (err, rsp.error)
            rsp.success = False

        if rsp.success:
            vm_pid = None
            try:
                vm_pid = linux.find_vm_pid_by_uuid(cmd.vmInstanceUuid)
                if vm_pid:
                    linux.enable_process_coredump(vm_pid)
                    linux.set_vm_priority(vm_pid, cmd.priorityConfigStruct)
                else:
                    # libvirt report start vm succeed but vm's process not exists
                    # we treat create vm failure
                    rsp.success = False
                    rsp.error = 'failed to start vm[uuid:%s, name:%s],'\
                        ' libvirt report success but qemu process can not be found' % (cmd.vmInstanceUuid, cmd.vmName)
            except Exception as e:
                logger.warn("enable coredump for VM: %s: %s" % (cmd.vmInstanceUuid, str(e)))

        if rsp.success == True:
            rsp.nicInfos, rsp.virtualDeviceInfoList, rsp.memBalloonInfo = self.get_vm_device_info(cmd.vmInstanceUuid)
            self.collect_vm_virtualizer_info(cmd.vmInstanceUuid, rsp.virtualizerInfo)

        return jsonobject.dumps(rsp)

    def get_vm_device_info(self, uuid):
        vm = get_vm_by_uuid(uuid)
        nicInfos = []
        virtualDeviceInfoList = []
        for iface in vm.domain_xmlobject.devices.get_child_node_as_list('interface'):
            vmNicInfo = VmNicInfo()
            vmNicInfo.deviceAddress.bus = iface.address.bus_
            vmNicInfo.deviceAddress.function = iface.address.function_
            vmNicInfo.deviceAddress.type = iface.address.type_
            vmNicInfo.deviceAddress.domain = iface.address.domain_
            vmNicInfo.deviceAddress.slot = iface.address.slot_
            vmNicInfo.macAddress = iface.mac.address_
            nicInfos.append(vmNicInfo)

        for disk in vm.domain_xmlobject.devices.get_child_node_as_list('disk'):
            virtualDeviceInfoList.append(self.get_device_address_info(disk))

        memBalloonPci = vm.domain_xmlobject.devices.get_child_node('memballoon')
        if memBalloonPci is not None:
            memBalloonInfo = self.get_device_address_info(memBalloonPci)
            return nicInfos, virtualDeviceInfoList, memBalloonInfo

        return nicInfos, virtualDeviceInfoList, None

    @kvmagent.replyerror
    def sync_vm_deviceinfo(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SyncVmDeviceInfoResponse()
        rsp.nicInfos, rsp.virtualDeviceInfoList, rsp.memBalloonInfo = self.get_vm_device_info(cmd.vmInstanceUuid)
        self.collect_vm_virtualizer_info(cmd.vmInstanceUuid, rsp.virtualizerInfo)
        return jsonobject.dumps(rsp)

    def get_vm_stat_with_ps(self, uuid):
        """In case libvirtd is stopped or misbehaved"""
        if not linux.find_vm_pid_by_uuid(uuid):
            return Vm.VM_STATE_SHUTDOWN
        return Vm.VM_STATE_RUNNING

    @kvmagent.replyerror
    def check_vm_state(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckVmStateRsp()
        r = bash.bash_r("timeout 5 virsh list")
        if r == 0:
            states = get_all_vm_states()
        else:
            states = get_all_vm_states_with_process()

        for uuid in cmd.vmUuids:
            s = states.get(uuid)
            if not s or s == Vm.VM_STATE_RUNNING:
                s = self.get_vm_stat_with_ps(uuid)
            rsp.states[uuid] = s
        
        return jsonobject.dumps(rsp)

    def _escape(self, size):
        unit = size.strip().lower()[-1]
        num = size.strip()[:-1]
        units = {
            "g": lambda x: x * 1024,
            "m": lambda x: x,
            "k": lambda x: x / 1024,
        }
        return int(units[unit](int(num)))

    def _get_image_mb_size(self, image):
        backing = shell.call('%s %s | grep "backing file:" | awk -F \'backing file:\' \'{print $2}\' ' %
                (qemu_img.subcmd('info'), image)).strip()
        size    = shell.call('%s %s | grep "disk size:" | awk -F \'disk size:\' \'{print $2}\' ' %
                (qemu_img.subcmd('info'), image)).strip()
        if not backing:
            return self._escape(size)
        else:
            return self._get_image_mb_size(backing) + self._escape(size)

    def _get_volume_bandwidth_value(self, vm_uuid, device_id, mode):
        cmd_base = "virsh blkdeviotune %s %s" % (vm_uuid, device_id)
        if mode == "total":
            return shell.call('%s | grep -w total_bytes_sec | awk \'{print $2}\'' % cmd_base).strip()
        elif mode == "read":
            return shell.call('%s | grep -w read_bytes_sec | awk \'{print $3}\'' % cmd_base).strip()
        elif mode == "write":
            return shell.call('%s | grep -w write_bytes_sec | awk \'{print $2}\'' % cmd_base).strip()

    @kvmagent.replyerror
    def set_volume_bandwidth(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        vm = get_vm_by_uuid(cmd.vmUuid)
        _, device_id = vm._get_target_disk(cmd.volume)

        ## total and read/write of bytes_sec cannot be set at the same time
        ## http://confluence.zstack.io/pages/viewpage.action?pageId=42599772#comment-42600879
        cmd_base = "virsh blkdeviotune %s %s" % (cmd.vmUuid, device_id)
        if cmd.mode == "overwrite":
            shell.call(
                '%s --total_bytes_sec %s --read_bytes_sec %s --write_bytes_sec %s --total_iops_sec %s --read_iops_sec '
                '%s --write_iops_sec %s' % (cmd_base, cmd.totalBandwidth, cmd.readBandwidth, cmd.writeBandwidth,
                                            cmd.totalIOPS, cmd.readIOPS, cmd.writeIOPS))
        elif (cmd.mode == "total") or (cmd.mode is None):  # to set total(read/write reset)
            shell.call('%s --total_bytes_sec %s' % (cmd_base, cmd.totalBandwidth))
        elif cmd.mode == "all":
            shell.call(
                '%s --read_bytes_sec %s --write_bytes_sec %s' % (cmd_base, cmd.readBandwidth, cmd.writeBandwidth))
        elif cmd.mode == "read":  # to set read(write reserved, total reset)
            write_bytes_sec = self._get_volume_bandwidth_value(cmd.vmUuid, device_id, "write")
            shell.call('%s --read_bytes_sec %s --write_bytes_sec %s' % (cmd_base, cmd.readBandwidth, write_bytes_sec))
        elif cmd.mode == "write":  # to set write(read reserved, total reset)
            read_bytes_sec = self._get_volume_bandwidth_value(cmd.vmUuid, device_id, "read")
            shell.call('%s --read_bytes_sec %s --write_bytes_sec %s' % (cmd_base, read_bytes_sec, cmd.writeBandwidth))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def upload_vm_file(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        cmd.dstPath = cmd.dstPath.replace("\\\\", "/")
        cmd.dstPath = cmd.dstPath.replace("\\", "/")
        logger.info("distPath %s" % cmd.dstPath)
        rsp = QgaUploadfileRsp()

        @LibvirtAutoReconnect
        def call_libvirt(conn):
            return conn.lookupByName(cmd.vmUuid)

        def conversion_template(template_text, param):
            template = Template(template_text)
            return template.render(param)

        def create_path(qga, file):
            exit_code = 0
            path = os.path.dirname(file)
            if qga.os == "mswindows":
                noExist, _, _ = qga.guest_exec_cmd(["/c", "dir", "/ad", path.replace("/", "\\")])
                if noExist:
                    exit_code, _, _ = qga.guest_exec_cmd(["/c", "md", path.replace("/", "\\")])
            else:
                noExist, _, _ = qga.guest_exec_bash("test -d {}".format(path))
                if noExist:
                    exit_code, _, _ = qga.guest_exec_bash("mkdir -p {}".format(path))
            return not exit_code

        script_type_dict = {
            "Python": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + ".py"),
            "Perl": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + ".pl"),
            "Shell": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + ".sh"),
            "Bat": os.path.join(WINDOWS_SCRIPT_LIB_PATH, cmd.vmUuid + ".bat"),
            "Powershell": os.path.join(WINDOWS_SCRIPT_LIB_PATH, cmd.vmUuid + ".ps1"),
        }

        qga = VmQga(call_libvirt())

        fw = 0
        dst = ""
        if cmd.fileType == "Script":
            # text wrote
            dst = script_type_dict.get(cmd.scriptType)
            if create_path(qga, dst):
                fw = qga.guest_file_open(dst, True)
        else:
            # binary wrote
            create_path(qga, cmd.dstPath)
            fw = qga.call_qga_command("guest-file-open", {"path": cmd.dstPath, "mode": "wb"})
            cmd.fileContent = base64.b64decode(cmd.fileContent)

        if fw == 0:
            rsp.success = False
            rsp.error = "do not open file {}".format(dst)
            return jsonobject.dumps(rsp)

        fileSize = 0
        dict_param = {}

        if cmd.param is not None and cmd.param != "":
            param = jsonobject.loads(cmd.param)
            for i in param:
                dict_param.setdefault(i.key, i.value)
            cmd.fileContent = conversion_template(cmd.fileContent, dict_param)

        try:
            if cmd.fileContent != "":
                ret = qga.call_qga_command("guest-file-write", {"handle": fw, "buf-b64": cmd.fileContent})
                fileSize = ret["count"]
                rsp.fileSize = fileSize
        except Exception as e:
            rsp.success = False
            rsp.error = "copy file exception {}".format(e)
        finally:
            logger.info("upload finished file size {}".format(fileSize))
            if fw != 0:
                qga.guest_file_close(fw)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def script_exec_on_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = QgaExecOutputRsp()

        @LibvirtAutoReconnect
        def call_libvirt(conn):
            return conn.lookupByName(cmd.vmUuid)

        def streamSplit(stream, lineNum):
            streamLines = stream.split("\n")
            streamLineNum = streamLines.__len__()
            if streamLineNum < lineNum:
                streamLines = streamLines[-streamLineNum:]
                streamLines = "\n".join(streamLines)
            else:
                streamLines = streamLines[-lineNum:]
                streamLines = "\n".join(streamLines)
            if streamLines.__sizeof__() >= (2 << 19):
                streamLines = streamLines[-(2 << 19):]
            return streamLines

        def createLog(logDir, logName, log):
            if not os.path.exists(logDir):
                os.makedirs(logDir)
            with open(os.path.join(logDir, logName), mode="a", buffering=4096) as logFile:
                if logFile.tell() != 0:
                    logFile.write("\n")
                logFile.write(log)

        script_type_dict = {
            "Python": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + ".py"),
            "Perl": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + ".pl"),
            "Shell": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + ".sh"),
            "Bat": os.path.join(WINDOWS_SCRIPT_LIB_PATH, cmd.vmUuid + ".bat"),
            "Powershell": os.path.join(WINDOWS_SCRIPT_LIB_PATH, cmd.vmUuid + ".ps1"),
        }

        timestamp = str(int(time.time()))
        stdout_dict = {
            "Python": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + "_stdout_" + timestamp + ".log"),
            "Perl": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + "_stdout_" + timestamp + ".log"),
            "Shell": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + "_stdout_" + timestamp + ".log"),
            "Bat": os.path.join(WINDOWS_SCRIPT_LIB_PATH, cmd.vmUuid + "_stdout_" + timestamp + ".log"),
            "Powershell": os.path.join(WINDOWS_SCRIPT_LIB_PATH, cmd.vmUuid + "_stdout_" + timestamp + ".log"),
        }
        stderr_dict = {
            "Python": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + "_stderr_" + timestamp + ".log"),
            "Perl": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + "_stderr_" + timestamp + ".log"),
            "Shell": os.path.join(LINUX_SCRIPT_LIB_PATH, cmd.vmUuid + "_stderr_" + timestamp + ".log"),
            "Bat": os.path.join(WINDOWS_SCRIPT_LIB_PATH, cmd.vmUuid + "_stderr_" + timestamp + ".log"),
            "Powershell": os.path.join(WINDOWS_SCRIPT_LIB_PATH, cmd.vmUuid + "_stderr_" + timestamp + ".log"),
        }

        qga = VmQga(call_libvirt())
        dst = script_type_dict.get(cmd.scriptType)
        stdout_dst = stdout_dict.get(cmd.scriptType)
        stderr_dst = stderr_dict.get(cmd.scriptType)
        exitCode = 0
        stdout = ""
        stderr = ""
        if cmd.scriptType == "Python":
            qga.guest_exec_bash("chmod 777 {}".format(dst), retry=cmd.scriptTimeout)
            qga.guest_exec_bash("{} > {} 2> {}".format(dst, stdout_dst, stderr_dst), retry=cmd.scriptTimeout)
            exitCode, stdout, stderr = qga.guest_exec_bash("tail -n 1000 {}".format(stdout_dst), retry=cmd.scriptTimeout)
            if qga.guest_file_is_exist(stderr_dst):
                exitCode, err_std_out, err_std_err = qga.guest_exec_bash("tail -n 1000 {}".format(stderr_dst), retry=cmd.scriptTimeout)
                stderr = "" if stderr is None else stderr
                stderr += err_std_out if err_std_out is not None else ""
                stderr += err_std_err if err_std_err is not None else ""
        if cmd.scriptType == "Perl":
            qga.guest_exec_bash("chmod 777 {}".format(dst), retry=cmd.scriptTimeout)
            qga.guest_exec_bash("perl {} > {} 2> {}".format(dst, stdout_dst, stderr_dst), retry=cmd.scriptTimeout)
            exitCode, stdout, stderr = qga.guest_exec_bash("tail -n 1000 {}".format(stdout_dst),  retry=cmd.scriptTimeout)
            if qga.guest_file_is_exist(stderr_dst):
                exitCode, err_std_out, err_std_err = qga.guest_exec_bash("tail -n 1000 {}".format(stderr_dst), retry=cmd.scriptTimeout)
                stderr = "" if stderr is None else stderr
                stderr += err_std_out if err_std_out is not None else ""
                stderr += err_std_err if err_std_err is not None else ""
        if cmd.scriptType == "Shell":
            qga.guest_exec_bash("chmod 777 {}".format(dst), retry=cmd.scriptTimeout)
            qga.guest_exec_bash("{} > {} 2> {}".format(dst, stdout_dst, stderr_dst), retry=cmd.scriptTimeout)
            exitCode, stdout, stderr = qga.guest_exec_bash("tail -n 1000 {}".format(stdout_dst), retry=cmd.scriptTimeout)
            if qga.guest_file_is_exist(stderr_dst):
                exitCode, err_std_out, err_std_err = qga.guest_exec_bash("tail -n 1000 {}".format(stderr_dst), retry=cmd.scriptTimeout)
                stderr = "" if stderr is None else stderr
                stderr += err_std_out if err_std_out is not None else ""
                stderr += err_std_err if err_std_err is not None else ""
        if cmd.scriptType == "Bat":
            exitCode, stdout, stderr = qga.guest_exec_cmd(["/c", "call", dst], retry=cmd.scriptTimeout)
        if cmd.scriptType == "Powershell":
            exitCode, stdout, stderr = qga.guest_exec_powershell_script(dst, retry=cmd.scriptTimeout)

        if cmd.logPath is not None:
            createLog(cmd.logPath, cmd.vmUuid, stdout)
            createLog(cmd.logPath, cmd.vmUuid, stderr)

        logger.info("exitCode=%s stdout=%s stderr=%s" % (exitCode, stdout, stderr))
        rsp.exitCode = exitCode
        if exitCode != 0 or (stderr is not None and stderr != ""):
            rsp.success = False
        if stdout is not None:
            rsp.stdout = streamSplit(stdout, 1000)
        if stderr is not None:
            rsp.stderr = streamSplit(stderr, 1000)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_volume_bandwidth(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        vm = get_vm_by_uuid(cmd.vmUuid)
        _, device_id = vm._get_target_disk(cmd.volume)

        ## total and read/write of bytes_sec cannot be set at the same time
        ## http://confluence.zstack.io/pages/viewpage.action?pageId=42599772#comment-42600879
        cmd_base = "virsh blkdeviotune %s %s" % (cmd.vmUuid, device_id)
        is_total_mode = self._get_volume_bandwidth_value(cmd.vmUuid, device_id, "total") != "0"
        if cmd.mode == "overwrite":
            shell.call(
                '%s --total_bytes_sec 0 --read_bytes_sec 0 --write_bytes_sec 0 --total_iops_sec 0 --read_iops_sec 0 '
                '--write_iops_sec 0' % cmd_base
            )
        elif cmd.mode == "all":  # to delete all(read/write reset)
            shell.call('%s --total_bytes_sec 0' % (cmd_base))
        elif (cmd.mode == "total") or (cmd.mode is None):  # to delete total
            if is_total_mode:
                shell.call('%s --total_bytes_sec 0' % (cmd_base))
        elif cmd.mode == "read":  # to delete read(write reserved, total reset)
            if not is_total_mode:
                write_bytes_sec = self._get_volume_bandwidth_value(cmd.vmUuid, device_id, "write")
                shell.call('%s --read_bytes_sec 0 --write_bytes_sec %s' % (cmd_base, write_bytes_sec))
        elif cmd.mode == "write":  # to delete write(read reserved, total reset)
            if not is_total_mode:
                read_bytes_sec = self._get_volume_bandwidth_value(cmd.vmUuid, device_id, "read")
                shell.call('%s --read_bytes_sec %s --write_bytes_sec 0' % (cmd_base, read_bytes_sec))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_volume_bandwidth(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        vm = get_vm_by_uuid(cmd.vmUuid)
        _, device_id = vm._get_target_disk(cmd.volume)

        io_tune_info = shell.call('virsh blkdeviotune %s %s' % (cmd.vmUuid, device_id))
        for io_tune in io_tune_info.splitlines():
            info = io_tune.split(':')
            if len(info) != 2:
                continue
            k = info[0].strip()
            if k == "total_bytes_sec":
                v = info[1].strip()
                rsp.bandWidth = v if long(v) > 0 else -1
            elif k == "read_bytes_sec":
                v = info[1].strip()
                rsp.bandWidthRead = v if long(v) > 0 else -1
            elif k == "write_bytes_sec":
                v = info[1].strip()
                rsp.bandWidthWrite = v if long(v) > 0 else -1
            elif k == "total_iops_sec":
                v = info[1].strip()
                rsp.iopsTotal = v if long(v) > 0 else -1
            elif k == "read_iops_sec":
                v = info[1].strip()
                rsp.iopsRead = v if long(v) > 0 else -1
            elif k == "write_iops_sec":
                v = info[1].strip()
                rsp.iopsWrite = v if long(v) > 0 else -1

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def set_nic_qos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        try:
            if cmd.inboundBandwidth != -1:
                shell.call('virsh domiftune %s %s --inbound %s' % (cmd.vmUuid, cmd.internalName, cmd.inboundBandwidth/1024/8))
            if cmd.outboundBandwidth != -1:
                shell.call('virsh domiftune %s %s --outbound %s' % (cmd.vmUuid, cmd.internalName, cmd.outboundBandwidth/1024/8))
        except Exception as e:
            e_str = linux.get_exception_stacktrace()
            logger.warn(e_str)
            if "burst" in e_str and "Illegal" in e_str and "rate" in e_str:
                rsp.error = "QoS exceed the max limit, please check and reset it in zstack"
            else:
                rsp.error = e_str
            rsp.success = False
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_nic_qos(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        inbound = shell.call('virsh domiftune %s %s | grep "inbound.average:"|awk \'{print $2}\'' % (cmd.vmUuid, cmd.internalName)).strip()
        outbound = shell.call('virsh domiftune %s %s | grep "outbound.average:"|awk \'{print $2}\'' % (cmd.vmUuid, cmd.internalName)).strip()

        rsp.inbound = long(inbound) * 8 * 1024 if long(inbound) > 0 else -1
        rsp.outbound = long(outbound) * 8 * 1024 if long(outbound) > 0 else -1

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_mount_domain(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckMountDomainRsp()

        finish_time = time.time() + (cmd.timeout / 1000)
        while time.time() < finish_time:
            try:
                logger.debug("check mount url: %s" % cmd.url)
                linux.is_valid_nfs_url(cmd.url)
                rsp.active = True
                return jsonobject.dumps(rsp)
            except Exception as err:
                if 'cannont resolve to ip address' in err.message:
                    logger.warn(err.message)
                    logger.warn('wait 1 seconds')
                else:
                    raise err
            time.sleep(1)
        rsp.active = False
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def change_vm_password(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ChangeVmPasswordRsp()
        vm = get_vm_by_uuid(cmd.accountPerference.vmUuid, False)
        vm.change_vm_password(cmd)
        rsp.accountPerference = cmd.accountPerference
        rsp.accountPerference.accountPassword = "******"
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def harden_console(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        vm = get_vm_by_uuid(cmd.vmUuid)
        vm.harden_console(cmd.hostManagementIp)

        return jsonobject.dumps(rsp)

    def get_vm_state_from_libvirt(self, rsp):
        rsp.states, rsp.vmInShutdowns = get_all_vm_sync_states()

        # In case of an reboot inside the VM.  Note that ZS will only define transient VM's.
        retry_for_paused = []
        for uuid in rsp.states:
            if rsp.states[uuid] == Vm.VM_STATE_SHUTDOWN:
                rsp.states[uuid] = Vm.VM_STATE_RUNNING
            elif rsp.states[uuid] == Vm.VM_STATE_PAUSED:
                retry_for_paused.append(uuid)

        time.sleep(0.5)
        if len(retry_for_paused) > 0:
            states, in_shutdown = get_all_vm_sync_states()
            for uuid in states:
                if states[uuid] == Vm.VM_STATE_SHUTDOWN:
                    rsp.states[uuid] = Vm.VM_STATE_RUNNING
                elif states[uuid] != Vm.VM_STATE_PAUSED:
                    rsp.states[uuid] = states[uuid]

    @kvmagent.replyerror
    def vm_sync(self, req):
        rsp = VmSyncResponse()

        r = bash.bash_r("timeout 5 virsh list")
        if r == 0:
            self.get_vm_state_from_libvirt(rsp)

        if rsp.states is None:
            rsp.states = {}

        states_from_qemu_process = get_all_vm_states_with_process()
        for guest, state in states_from_qemu_process.items():
            if guest not in rsp.states:
                rsp.states[guest] = state

        libvirt_running_vms = rsp.states.keys()
        no_qemu_process_running_vms = list(set(libvirt_running_vms).difference(set(states_from_qemu_process.keys())))
        for vm in no_qemu_process_running_vms:
            rsp.states[vm] = Vm.VM_STATE_SHUTDOWN

        states_from_qemu_process = get_all_vm_states_with_process()
        for guest, state in states_from_qemu_process.items():
            if guest not in rsp.states:
                logger.warn('guest [%s] not found in virsh list' % guest)
                rsp.states[guest] = state

        states_from_cache = get_vm_states_from_cache()
        for guest, state in states_from_cache.items():
            if guest not in rsp.states:
                logger.warn('guest [%s] not found in virsh list and qemu process, load from cache' % guest)
                rsp.states[guest] = state

        libvirt_running_vms = rsp.states.keys()
        no_qemu_process_running_vms = list(set(libvirt_running_vms).difference(set(states_from_qemu_process.keys())))
        state_cached_vms = states_from_cache.keys()
        # if vm cached means kvmagent manually control the sync result, should be used 
        # as filter.
        # if vm not have qemu process means libvirt and qemu is inconsistent use filter
        # to make sure the vm state is correct.
        # vm meet both the above conditions should be shutdown
        for vm in no_qemu_process_running_vms:
            if vm in state_cached_vms:
                logger.warn('guest [%s] not found in qemu process, but in cache, keep the state' % vm)
                continue

            rsp.states[vm] = Vm.VM_STATE_SHUTDOWN

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.lock('volume-sync-task')
    def volume_sync(self, req):
        rsp = VolumeSyncResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        global last_inactive_vol_paths
        current_inactive_vol_paths = {}  # type: dict[str, set[str]]

        def get_inactive_vols_from_file_path(fpath):
            file_dir = fpath if os.path.isdir(fpath) else os.path.dirname(fpath)
            o = bash.bash_o('grep -Eo "%s[_/a-z0-9\\-]*" %s' % (file_dir, os.path.join(linux.LIVE_LIBVIRT_XML_DIR, "*.xml")))
            active_vol_paths = set(line.split(":")[-1].strip() for line in o.splitlines())

            file_name = "" if os.path.isdir(fpath) else os.path.basename(fpath)
            wildcard_name = file_name if "*" in file_name else "%s*" % file_name
            all_vol_paths = set(glob.glob(os.path.join(file_dir, wildcard_name)))

            return all_vol_paths - active_vol_paths

        for storage_url in cmd.storagePaths:
            # TODO support other protocols
            if storage_url.startswith("file://"):
                inactive_vol_paths = get_inactive_vols_from_file_path(storage_url[7:])
            else:
                inactive_vol_paths = set()

            current_inactive_vol_paths[storage_url] = inactive_vol_paths

        for storage_url in current_inactive_vol_paths:
            if storage_url in last_inactive_vol_paths:
                twice_inactive_vol_paths = current_inactive_vol_paths[storage_url] & last_inactive_vol_paths[storage_url]
                if twice_inactive_vol_paths:
                    rsp.inactiveVolumePaths[storage_url] = list(twice_inactive_vol_paths)

        last_inactive_vol_paths = current_inactive_vol_paths
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def online_increase_mem(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = IncreaseMemoryResponse()

        try:
            vm = get_vm_by_uuid(cmd.vmUuid)
            memory_size = cmd.memorySize
            vm.hotplug_mem(memory_size)
            vm = get_vm_by_uuid(cmd.vmUuid)
            rsp.memorySize = vm.get_memory()
            logger.debug('successfully increase memory of vm[uuid:%s] to %s Kib' % (cmd.vmUuid, vm.get_memory()))
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def online_increase_cpu(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = IncreaseCpuResponse()

        try:
            vm = get_vm_by_uuid(cmd.vmUuid)
            cpu_num = cmd.cpuNum
            vm.hotplug_cpu(cpu_num)
            vm = get_vm_by_uuid(cmd.vmUuid)
            rsp.cpuNum = vm.get_cpu_num()
            logger.debug('successfully increase cpu number of vm[uuid:%s] to %s' % (cmd.vmUuid, vm.get_cpu_num()))
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def online_change_cpumem(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ChangeCpuMemResponse()
        try:
            vm = get_vm_by_uuid(cmd.vmUuid)
            cpu_num = cmd.cpuNum
            memory_size = cmd.memorySize
            vm.hotplug_mem(memory_size)
            vm.hotplug_cpu(cpu_num)
            vm = get_vm_by_uuid(cmd.vmUuid)
            rsp.cpuNum = vm.get_cpu_num()
            rsp.memorySize = vm.get_memory()
            logger.debug('successfully add cpu and memory on vm[uuid:%s]' % (cmd.vmUuid))
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False
        return jsonobject.dumps(rsp)

    def get_vm_console_info(self, vmUuid):
        try:
            vm = get_vm_by_uuid(vmUuid)
            protocol, vncPort, spicePort, spiceTlsPort = vm.get_vdi_connect_port()
            ret = check_vdi_port(vncPort, spicePort, spiceTlsPort)
            if ret is True:
                return protocol, vncPort, spicePort, spiceTlsPort
            # Occasionally, 'virsh list' would list nothing but conn.lookupByName()
            # can find the VM and dom.XMLDesc(0) will return VNC port '-1'.
            err = 'libvirt failed to get console port for VM %s' % vmUuid
            logger.warn(err)
            raise kvmagent.KvmError(err)
        except kvmagent.KvmError as e:
            protocol, vncPort, spicePort, spiceTlsPort = get_console_without_libvirt(vmUuid)
            ret = check_vdi_port(vncPort, spicePort, spiceTlsPort)
            if ret is True:
                return protocol, vncPort, spicePort, spiceTlsPort
            raise e

    @kvmagent.replyerror
    def get_console_port(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVncPortResponse()
        try:
            protocol, vncPort, spicePort, spiceTlsPort = self.get_vm_console_info(cmd.vmUuid)
            rsp.protocol = protocol
            rsp.vncPort = vncPort
            rsp.spicePort = spicePort
            rsp.spiceTlsPort = spiceTlsPort

            if vncPort is not None:
                rsp.port = vncPort
            else:
                rsp.port = spicePort

            logger.debug('successfully get vncPort[%s], spicePort[%s], spiceTlsPort[%s] of vm[uuid:%s]' % (
                vncPort, spicePort, spiceTlsPort, cmd.vmUuid))
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def take_console_screenshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = TakeVmConsoleScreenshotRsp()
        
        @LibvirtAutoReconnect
        def create_stream(conn):
            return conn.newStream()

        def read_stream_to_file(stream, file_path):
            with open(file_path, 'wb') as f:
                for data in iter(lambda: stream.recv(262120), b''):
                    f.write(data)
        
        stream = create_stream()
        if stream is None:
            rsp.success = False
            rsp.error = "failed to create libvirt stream"
            return jsonobject.dumps(rsp)
        
        tmp_ppm = "/tmp/%s.ppm" % cmd.vmUuid
        tmp_img = "/tmp/%s.png" % cmd.vmUuid
        try:
            vm = get_vm_by_uuid(cmd.vmUuid)
            vm.domain.screenshot(stream, 0)
            read_stream_to_file(stream, tmp_ppm)

            tmp_img = image.convert_image(tmp_ppm)
            with open(tmp_img, 'rb') as f:
                img_data = f.read()

            rsp.imageData = 'data:image/png;base64,' + base64.b64encode(img_data).decode('utf-8')
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False
        finally:
            stream.finish()
            linux.rm_file_force(tmp_ppm)
            linux.rm_file_force(tmp_img)
        return jsonobject.dumps(rsp)


    def _dump(self, vm_instance_uuid):
        try:
            vm = get_vm_by_uuid(vm_instance_uuid)
            vm.dump_guest_memory("%s/%s" % (VM_CORE_DUMP_DIR, vm_instance_uuid))
            logger.debug("successfully dump vm[uuid:%s] guest memory" % vm_instance_uuid)
        except Exception as e:
            logger.warn("failed to dump vm[uuid:%s] guest memory, %s" % (vm_instance_uuid, str(e)))


    def _stop_vm(self, cmd):
        try:
            vmUuid = cmd.uuid
            strategy = str(cmd.type)
            vm = get_vm_by_uuid(vmUuid)
            vmUseOpenvSwitch = ovs.isVmUseOpenvSwitch(vmUuid)

            if strategy == "cold" or strategy == "force":
                vm.stop(strategy=strategy)
            else:
                vm.stop(timeout=cmd.timeout / 2)

            if vmUseOpenvSwitch:
                ovs.getOvsCtl(with_dpdk=True).destoryNicBackend(vmUuid)
        except kvmagent.KvmError as e:
            logger.debug(linux.get_exception_stacktrace())
        finally:
            # libvirt is not reliable, c.f. ZSTAC-15412
            self.kill_vm(vmUuid)

    def kill_vm(self, vm_uuid):
        output = bash.bash_o("ps -ef | grep -P -o '(qemu-kvm|qemu-system).*?-name\s+(guest=)?\K%s,' | sed 's/.$//'" % vm_uuid)

        if vm_uuid not in output:
            return

        logger.debug('killing vm %s' % vm_uuid)
        vm_pid = linux.find_vm_pid_by_uuid(vm_uuid)
        if vm_pid:
            linux.kill_process(vm_pid)

    @kvmagent.replyerror
    def stop_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = StopVmResponse()
        try:
            if cmd.debug:
                self._dump(cmd.uuid)
            self._record_operation(cmd.uuid, self.VM_OP_STOP)
            self._stop_vm(cmd)
            # notify vrouter agent nic removed from source host
            for nic in cmd.vmNics:
                if nic.type == 'TFVNIC':
                    vrouter_cmd = [
                        'vrouter-port-control',
                        '--oper=delete',
                        '--uuid=%s' % transform_to_tf_uuid(nic.uuid)
                    ]
                    notify_vrouter(vrouter_cmd)
            logger.debug("successfully stopped vm[uuid:%s]" % cmd.uuid)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def pause_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        try:
            self._record_operation(cmd.uuid, self.VM_OP_SUSPEND)
            rsp = PauseVmResponse()
            vm = get_vm_by_uuid(cmd.uuid)
            vm.pause()
            logger.debug('successfully, pause vm [uuid:%s]' % cmd.uuid)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def resume_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        try:
            self._record_operation(cmd.uuid, self.VM_OP_RESUME)
            rsp = ResumeVmResponse()
            vm = get_vm_by_uuid(cmd.uuid)
            vm.resume()
            logger.debug('successfully, resume vm [uuid:%s]' % cmd.uuid)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def reboot_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RebootVmResponse()
        try:
            self._record_operation(cmd.uuid, self.VM_OP_REBOOT)

            vm = get_vm_by_uuid(cmd.uuid)
            vm.reboot(cmd)
            self.collect_vm_virtualizer_info(cmd.uuid, rsp.virtualizerInfo)
            logger.debug('successfully, reboot vm[uuid:%s]' % cmd.uuid)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def destroy_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DestroyVmResponse()
        try:
            self._record_operation(cmd.uuid, self.VM_OP_DESTROY)

            vm = get_vm_by_uuid(cmd.uuid, False)
            if vm:
                vmUseOpenvSwitch = ovs.isVmUseOpenvSwitch(cmd.uuid)
                vm.destroy()
                if vmUseOpenvSwitch:
                    ovs.getOvsCtl(with_dpdk=True).destoryNicBackend(cmd.uuid)
                # notify vrouter agent nic removed from source host
                for nic in cmd.vmNics:
                    if nic.type == 'TFVNIC':
                        vrouter_cmd = [
                            'vrouter-port-control',
                            '--oper=delete',
                            '--uuid=%s' % transform_to_tf_uuid(nic.uuid)
                        ]
                        notify_vrouter(vrouter_cmd)
                logger.debug('successfully destroyed vm[uuid:%s]' % cmd.uuid)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    def get_device_address_info(self, device, resource_uuid=None):
        virtualDeviceInfo = VirtualDeviceInfo()
        virtualDeviceInfo.deviceAddress.bus = device.address.bus_ if device.address.bus__ else None
        virtualDeviceInfo.deviceAddress.domain = device.address.domain_ if device.address.domain__ else None
        virtualDeviceInfo.deviceAddress.controller = device.address.controller_ if device.address.controller__ else None
        virtualDeviceInfo.deviceAddress.slot = device.address.slot_ if device.address.slot__ else None
        virtualDeviceInfo.deviceAddress.target = device.address.target_ if device.address.target__ else None
        virtualDeviceInfo.deviceAddress.function = device.address.function_ if device.address.function__ else None
        virtualDeviceInfo.deviceAddress.unit = device.address.unit_ if device.address.unit__ else None
        virtualDeviceInfo.deviceAddress.type = device.address.type_ if device.address.type__ else None

        if device.has_element('serial'):
            virtualDeviceInfo.resourceUuid = device.serial.text_
        elif resource_uuid:
            virtualDeviceInfo.resourceUuid = resource_uuid

        return virtualDeviceInfo

    @staticmethod
    def get_source_file_by_disk(disk):
        # disk->type: zstacklib.utils.xmlobject.XmlObject, attr name is endwith '_'
        if not xmlobject.has_element(disk, 'source'):
            return None
        attr_name = Vm.disk_source_attrname.get(disk.type_)
        return getattr(disk.source, attr_name + "_") if attr_name else None

    @staticmethod
    def get_source_index_by_disk(disk):
        if not xmlobject.has_element(disk, 'source'):
            return None
        return disk.source.index_ if disk.source.index__ else None

    @kvmagent.replyerror
    def attach_data_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AttachDataVolumeResponse()
        try:
            volume = cmd.volume
            vm = get_vm_by_uuid(cmd.vmInstanceUuid)
            if vm.state != Vm.VM_STATE_RUNNING and vm.state != Vm.VM_STATE_PAUSED:
                raise kvmagent.KvmError(
                    'unable to attach volume[%s] to vm[uuid:%s], vm must be running or paused' % (volume.installPath, vm.uuid))
            vm.attach_data_volume(cmd.volume, cmd.addons)

            vm.refresh()

            disk, _ = vm._get_target_disk(volume)
            rsp.virtualDeviceInfoList.append(self.get_device_address_info(disk, volume.volumeUuid))
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        touchQmpSocketWhenExists(cmd.vmInstanceUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def detach_data_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DetachDataVolumeResponse()
        try:
            volume = cmd.volume
            vm = get_vm_by_uuid(cmd.vmInstanceUuid)
            if vm.state != Vm.VM_STATE_RUNNING and vm.state != Vm.VM_STATE_PAUSED:
                raise kvmagent.KvmError(
                    'unable to detach volume[%s] to vm[uuid:%s], vm must be running or paused' % (volume.installPath, vm.uuid))

            target_disk, _ = vm._get_target_disk(volume, is_exception=False)
            if not target_disk:
                if vm._volume_detach_timed_out(volume):
                    logger.debug('volume [installPath: %s] has been detached before' % volume.installPath)
                    vm._clean_timeout_record(volume)
                    return jsonobject.dumps(rsp)
                raise kvmagent.KvmError('unable to find data volume[%s] on vm[uuid:%s]' % (volume.installPath, vm.uuid))

            if volume_support_block_node(volume):
                node_name = self.get_disk_device_name(target_disk)
                isc = ImageStoreClient()
                isc.stop_mirror(cmd.vmInstanceUuid, True, node_name)

            vm.detach_data_volume(volume)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    def _check_vm_live_migate_status(self, cmd):
        def _check_vm_on_dsthost(retry_times=1):
            @linux.retry(times=retry_times, sleep_time=2)
            def _check():
                with contextlib.closing(get_connect(cmd.destHostIp)) as conn:
                    vm = get_vm_by_uuid(cmd.vmUuid, False, conn)
                    if vm is not None and vm.state == vm.VM_STATE_RUNNING:
                        return True
                    raise RetryException("")
            try:
                return _check()
            except Exception:
                return False

        if _check_vm_on_dsthost():
            return True

        vm = get_vm_by_uuid(cmd.vmUuid)
        if vm.state != vm.VM_STATE_RUNNING:
            logger.debug("vm[uuid:%s] state is not running, unable to recover live storage migration" % cmd.vmuuid)
            return False

        def _wait_job(_):
            vm.refresh()
            for oldpath, volume in cmd.disks.__dict__.items():
                _, disk_name = vm._get_target_disk_by_path(oldpath, is_exception=False)
                if disk_name is not None and vm._wait_for_block_job(disk_name, abort_on_error=False):
                    return False
            return True

        try:
            logger.debug('migrate vm[%s] with block is waiting for job completion' % vm.uuid)
            timeout = 259200 if get_timeout(cmd) <= 0 else get_timeout(cmd)
            linux.wait_callback_success(_wait_job, timeout=timeout, interval=10)
        except Exception as e:
            logger.warn("caught an exception on waiting for storage migration job completion: %s" % str(e))
        finally:
            return _check_vm_on_dsthost(retry_times=5)

    @kvmagent.replyerror
    def migrate_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = MigrateVmResponse()
        try:
            self._record_operation(cmd.vmUuid, self.VM_OP_MIGRATE)

            if cmd.migrateFromDestination:
                with contextlib.closing(get_connect(cmd.srcHostIp)) as conn:
                    vm = get_vm_by_uuid(cmd.vmUuid, False, conn)
                    if vm is None:
                        logger.warn('unable to find vm {0} on host {1}'.format(cmd.vmUuid, cmd.srcHostIp))
                        raise kvmagent.KvmError('unable to find vm %s on host %s' % (cmd.vmUuid, cmd.srcHostIp))
                    vm.migrate(cmd)
            elif cmd.reload and cmd.disks:
                ## storage migration recovery
                rsp.success = self._check_vm_live_migate_status(cmd)
                if not rsp.success:
                    rsp.error = 'unable to resume storage migration of vm %s' % cmd.vmUuid
                return jsonobject.dumps(rsp)
            else:
                vm = get_vm_by_uuid(cmd.vmUuid)
                vm.migrate(cmd)

        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_cpu_xml(self, req):
        rsp = GetCpuXmlResponse()
        sh_cmd = shell.ShellCmd('virsh capabilities | virsh cpu-baseline /dev/stdin')
        sh_cmd(False)
        logger.info("get cpu xml: " + sh_cmd.stdout)
        if sh_cmd.return_code != 0:
            rsp.error = sh_cmd.stderr
            rsp.success = False
        else:
            if sh_cmd.stdout.strip():
                rsp.cpuXml = sh_cmd.stdout.strip()

        _, rsp.cpuModelName = linux.get_cpu_model()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def compare_cpu_function(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CompareCpuFunctionResponse()
        fpath = linux.write_to_temp_file(cmd.cpuXml.strip())
        compare_cmd = shell.ShellCmd('virsh cpu-compare --error %s' % fpath)
        compare_cmd(False)
        logger.info("compare cpu function result: " + compare_cmd.stdout)
        if compare_cmd.return_code != 0:
            rsp.error = compare_cmd.stderr
            logger.info("compare cpu function error: " + compare_cmd.stderr)
            rsp.success = False
        linux.rm_file_force(fpath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        vm = get_vm_by_uuid(cmd.uuid)
        for volume in cmd.volumes:
            vm._get_target_disk(volume)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_recover(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckVmRecoveryResponse()

        if cmd.vmUuid in VM_RECOVER_TASKS:
            rsp.status = 'running'
        else:
            vm = get_vm_by_uuid(cmd.vmUuid)
            disks = vm.domain_xmlobject.devices.get_child_node_as_list('disk')
            rsp.status = 'interrupted' if any(is_nbd_disk(d) for d in disks) else 'done'

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def recover_volumes(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        def get_recover_task(cmd, rvols):
            if rvols != None:
                return True, VmVolumesRecoveryTask(cmd, rvols)

            t = VM_RECOVER_TASKS.get(cmd.vmUuid)
            if t != None:
                return False, t

            logger.info("reconstructing recovery task for VM: " + cmd.vmUuid)
            return True, VmVolumesRecoveryTask(cmd, rvols)

        def check_device_in_xml(install_path):
            if install_path is None:
                return False
            vm = get_vm_by_uuid(cmd.vmUuid)
            disk, disk_name = vm._get_target_disk_by_path(install_path, is_exception=False)
            return disk_name is not None or disk is not None

        # fix ZSTAC-54725: after recovery completed, need double check xml results
        def check_volume_recover_results():
            for volume in cmd.volumes:
                xml_path = volume.installPath.split('?', 1)[0]
                u = urlparse.urlparse(xml_path)
                if u.scheme:
                    xml_path = xml_path.replace(u.scheme + '://', '')
                if not linux.wait_callback_success(check_device_in_xml, xml_path, interval=2, timeout=10):
                    raise kvmagent.KvmError("libvirt return recovery vm successfully, but it is failure actually! "
                                            "because unable to find volume[installPath:%s] on vm[uuid:%s]" % (
                                                xml_path, cmd.vmUuid))

        logger.info("recovering VM: " + cmd.vmUuid)
        rvols = VM_RECOVER_DICT.pop(cmd.vmUuid, None)
        isnew, t = get_recover_task(cmd, rvols)

        if isnew:
            try:
                with t:
                    VM_RECOVER_TASKS[cmd.vmUuid] = t
                    t.recover_vm_volumes()
                    check_volume_recover_results()

                logger.info("recovery completed. VM: " + cmd.vmUuid)
            finally:
                VM_RECOVER_TASKS.pop(cmd.vmUuid, None)
        else:
            while not t.cancelled and t.percent < 100:
                time.sleep(2)
            if t.cancelled:
                rsp.error = "recovery cancelled for VM: %s" % cmd.vmUuid
                rsp.success = False

        return jsonobject.dumps(rsp)


    @staticmethod
    def _get_new_disk(old_disk, volume=None):
        def filebased_volume(_v):
            disk = etree.Element('disk', {'type': 'file', 'device': 'disk', 'snapshot': 'external'})
            e(disk, 'driver', None, {'name': 'qemu', 'type': driver_type, 'cache': _v.cacheMode, 'discard': 'unmap'})
            e(disk, 'source', None, {'file': _v.installPath})
            return disk

        def ceph_volume(_v):
            def ceph_virtio():
                vc = VirtioCeph()
                vc.volume = _v
                return vc.to_xmlobject()

            def ceph_blk():
                ic = BlkCeph()
                ic.volume = _v
                return ic.to_xmlobject()

            def ceph_virtio_scsi():
                vsc = VirtioSCSICeph()
                vsc.volume = _v
                return vsc.to_xmlobject()

            if _v.useVirtioSCSI:
                disk = ceph_virtio_scsi()
                if _v.shareable:
                    e(disk, 'shareable')
                return disk

            if _v.useVirtio:
                return ceph_virtio()
            else:
                return ceph_blk()

        def block_volume(_v):
            disk = etree.Element('disk', {'type': 'block', 'device': 'disk', 'snapshot': 'external'})
            e(disk, 'driver', None,
              {'name': 'qemu', 'type': driver_type, 'cache': 'none', 'io': 'native'})
            e(disk, 'source', None, {'dev': _v.installPath})
            return disk

        def block_iso(_v):
            cdrom = etree.Element('disk', {'type': 'block', 'device': 'cdrom'})
            e(cdrom, 'driver', None, {'name': 'qemu', 'type': 'raw'})
            e(cdrom, 'source', None, {'dev': _v.installPath})
            e(cdrom, 'readonly', None)
            return cdrom

        block_backing_store = None
        if volume is None:
            volume = DomainVolume.from_xmlobject(old_disk)
            if not volume.over_incorrect_driver():
                return old_disk  # no change

        # vm created by ISO image or storage migrated may not have backing store info
        if volume.backing_store is not None:
            volume.backing_store.update_backing_store_type_to_block()
            block_backing_store = volume.backing_store._origin_xml_obj

        driver_type = volume.format if volume.format else 'qcow2'
        volume = file_volume_check(volume)
        if volume.deviceType == 'file':
            ele = filebased_volume(volume)
        elif volume.deviceType == 'ceph':
            ele = ceph_volume(volume)
        elif volume.deviceType == 'block':
            ele = block_iso(volume) if volume.is_cdrom else block_volume(volume)
        else:
            raise Exception('unsupported volume deviceType[%s]' % volume.deviceType)

        tags_to_keep = [ 'target', 'boot', 'alias', 'address', 'wwn', 'serial']
        for c in old_disk.getchildren():
            if c.tag in tags_to_keep:
                child = ele.find(c.tag)
                if child is not None: ele.remove(child)
                ele.append(c)

        if block_backing_store is not None:
            ele.append(block_backing_store)

        logger.info("updated disk XML: " + etree.tostring(ele))
        return ele

    def _build_domain_new_xml(self, vm, volumeDicts):
        migrate_disks = {}

        for oldpath, volume in volumeDicts.items():
            _, disk_name = vm._get_target_disk_by_path(oldpath)
            migrate_disks[disk_name] = volume

        fpath = linux.write_to_temp_file(vm.domain_xml)

        tree = etree.parse(fpath)
        devices = tree.getroot().find('devices')
        for disk in tree.iterfind('devices/disk'):
            dev = disk.find('target').attrib['dev']
            if dev in migrate_disks:
                new_disk = VmPlugin._get_new_disk(disk, migrate_disks[dev])
                parent_index = list(devices).index(disk)
                devices.remove(disk)
                devices.insert(parent_index, new_disk)

        tree.write(fpath)
        return migrate_disks.keys(), fpath

    def _build_dest_disk_xml(self, vm, oldVolumePath, newVolume):
        _, disk_name = vm._get_target_disk_by_path(oldVolumePath)

        tree = etree.fromstring(vm.domain_xml)

        for disk in tree.iterfind('devices/disk'):
            dev = disk.find('target').attrib['dev']
            if dev == disk_name:
                new_disk = VmPlugin._get_new_disk(disk, newVolume)
                return dev, linux.write_to_temp_file(etree.tostring(new_disk))

    def _do_block_copy(self, vmUuid, disk_name, disk_xml, task_spec):
        class BlockCopyDaemon(plugin.TaskDaemon):
            def __init__(self, task_spec, domain, disk_name):
                super(BlockCopyDaemon, self).__init__(task_spec, 'blockCopy')
                self.domain = domain
                self.disk_name = disk_name

            def _cancel(self):
                logger.debug('cancelling vm[uuid:%s] blockCopy disk[%s]' % (vmUuid, self.disk_name))
                # cancel block job async
                self.domain.blockJobAbort(self.disk_name, libvirt.VIR_DOMAIN_BLOCK_JOB_ABORT_ASYNC)

            def _get_percent(self):
                # type: () -> int
                result = self._get_detail()
                if not result:
                    return

                percent = min(99, 100.0 - result.__getitem__('remain') * 100.0 / result.__getitem__('total'))
                return get_exact_percent(percent, get_task_stage(task_spec))

            def _get_detail(self):
                try:
                    result = jsonobject.JsonObject()
                    block_jobs, err = execute_qmp_command(vmUuid, '{"execute":"query-block-jobs"}')
                    if err:
                        return

                    job = next((job for job in block_jobs if job['status'] == 'running'), None)
                    if not job:
                        logger.debug("do_block_copy job finished. detail no found!")
                        return

                    remain = job['len'] - job['offset']
                    result.put("remain", remain)
                    result.put("total", job['len'])

                    if job['len'] == job['offset']:
                        return result

                    if self.progress_reporter.report.detail and self.progress_reporter.report.detail.hasattr('remain'):
                        speed = self.progress_reporter.report.detail.__getitem__('remain') - remain
                        remaining_migration_time = (remain / speed) if speed != 0 else self.progress_reporter.report.detail.__getitem__('remaining_migration_time')
                        result.put("speed", speed)
                        result.put("remaining_migration_time", remaining_migration_time)
                    return result
                except libvirt.libvirtError:
                    pass
                except:
                    logger.debug(linux.get_exception_stacktrace())

        def check_volume():
            # type: () -> tuple[bool, str]
            vm = get_vm_by_uuid(vmUuid)
            target_install_path = task_spec.newVolume.installPath
            logger.debug("start checking for volume[install_path=%s] in the VM[uuid=%s]" % (target_install_path, vmUuid))
            d, _ = vm._get_target_disk_by_path(target_install_path, is_exception=False)
            if d is None:
                return False, "fail to find disk[install_path=%s] in domain XML[VMUuid=%s]" % (target_install_path, vmUuid)

            valid = check_install_path_by_qmp(vmUuid, d.alias.name_, target_install_path)
            return (True, None) if valid else (False, "fail to find disk[install_path=%s] in VM[uuid=%s] by qemu-monitor-command" % (target_install_path, vmUuid))

        job_over = False
        @thread.AsyncThread
        @linux.retry(times=10, sleep_time=0.5)
        def _touch_qmp_socket():
            if job_over:
                return
            block_nodes, err = execute_qmp_command(vmUuid, '{ "execute": "query-named-block-nodes" }')
            if not err and task_spec.newVolume.installPath in str(block_nodes):
                logger.debug("touch qmp socket for block[diskName: %s, vmUuid: %s] migration" % (disk_name, vmUuid))
                touchQmpSocketWhenExists(vmUuid)
                return
            raise RetryException("cannot find dst volume block node for disk %s, vmUuid %s" % (disk_name, vmUuid))

        if task_spec.newVolume.installPath.startswith("/dev"):
            _touch_qmp_socket()

        logger.info("start copying %s:%s to %s ..." % (vmUuid, disk_name, task_spec.newVolume.installPath))
        with BlockCopyDaemon(task_spec, get_vm_by_uuid(vmUuid).domain, disk_name):
            bandwidth = ' --bandwidth {}'.format(task_spec.bandwidth) if task_spec.bandwidth > 0 else ''
            cmd = 'virsh blockcopy --domain {} {} --xml {} --pivot --wait --transient-job --reuse-external{}'.format(
                vmUuid, disk_name, disk_xml, bandwidth)

            shell_cmd = shell.ShellCmd(cmd)
            shell_cmd(False)
            job_over = True
            if shell_cmd.return_code != 0:
                if 'non-file destination not supported' in shell_cmd.stderr:
                    shell_cmd.stderr = 'the current libvirt does not support migrating storage to ceph ' \
                                       'from the same host. Please upgrade to libvirt-4.9.0-22.gef3a393 or higher'
                logger.debug("block copy failed from %s:%s to %s: %s" % (vmUuid, disk_name, task_spec.newVolume.installPath, shell_cmd.stderr))
                return False, shell_cmd.stderr
            valid, errText = check_volume()
            if not valid:
                return False, errText

        logger.info("completed copying %s:%s to %s ..." % (vmUuid, disk_name, task_spec.newVolume.installPath))
        return True, None

    def _migrate_vm_with_block(self, vmUuid, dstHostIp, volumeDicts):
        vm = get_vm_by_uuid(vmUuid)
        disks, fpath = self._build_domain_new_xml(vm, volumeDicts)

        dst = 'qemu+tcp://{0}/system'.format(dstHostIp)
        migurl = 'tcp://{0}'.format(dstHostIp)
        diskstr = ','.join(disks)

        flags = "--live --p2p --copy-storage-all --persistent"
        if LIBVIRT_MAJOR_VERSION >= 4:
            if any(s.startswith('/dev/') for s in vm.list_blk_sources()):
                flags += " --unsafe"

        check_mirror_jobs(vmUuid, bool(os.getenv("MIGRATE_WITHOUT_DIRTY_BITMAPS")))
        cmd = "virsh migrate {} --migrate-disks {} --xml {} {} {} {}".format(flags, diskstr, fpath, vmUuid, dst, migurl)

        shell_cmd = shell.ShellCmd(cmd)
        shell_cmd(False)
        os.remove(fpath)
        if shell_cmd.return_code == 0:
            return

        if shell_cmd.stderr and "Need a root block node" in shell_cmd.stderr:
            shell_cmd.stderr = "failed to block migrate %s, please check if volume backup job is in progress" % vmUuid

        shell_cmd.raise_error()

    def _check_block_copy(self, vm, cmd):
        def _check_dst_volume(retry_times=1):
            @linux.retry(times=retry_times, sleep_time=2)
            def _check():
                vm.refresh()
                vm._get_target_disk_by_path(cmd.newVolume.installPath)
                return True

            try:
                return _check()
            except Exception:
                return False

        if _check_dst_volume(1):
            return True

        def _wait_job(disk_name):
            return not vm._wait_for_block_job(disk_name, abort_on_error=False)

        try:
            _, disk_name = vm._get_target_disk_by_path(cmd.oldVolumePath)
            logger.debug('block[%s] migration of vm[%s] is waiting for job completion' % (disk_name, vm.uuid))
            timeout = 259200 if get_timeout(cmd) <= 0 else get_timeout(cmd)
            linux.wait_callback_success(_wait_job, callback_data=disk_name, timeout=timeout, interval=10)
        except Exception as e:
            logger.debug("caught an exception on waiting for block migration job completion: %s" % str(e))
        finally:
            return _check_dst_volume(5)

    @kvmagent.replyerror
    def block_migrate(self, req):
        rsp = kvmagent.AgentResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        vm = get_vm_by_uuid(cmd.vmUuid)
        if cmd.reload:
            rsp.success = self._check_block_copy(vm, cmd)
            if not rsp.success:
                rsp.error = 'unable to resume storage migration of vm %s' % cmd.vmUuid
            return jsonobject.dumps(rsp)

        self._record_operation(cmd.vmUuid, self.VM_OP_MIGRATE)
        disk_name, disk_xml = self._build_dest_disk_xml(vm, cmd.oldVolumePath, cmd.newVolume)

        check_mirror_jobs(vm.uuid, False)

        rsp.success, rsp.error = self._do_block_copy(vm.uuid, disk_name, disk_xml, cmd)
        os.remove(disk_xml)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def merge_snapshot_to_volume(self, req):
        rsp = MergeSnapshotRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=True)
        if os.path.exists("/root/mergefail"):
            raise Exception("on purpose")
        if vm.state not in Vm.SNAPSHOT_VM_STATE_DICT[LIVE_SNAPSHOT]:
            rsp.error = 'vm[uuid:%s] is not in [running, paused], cannot do live snapshot chain merge' % vm.uuid
            rsp.success = False
            return jsonobject.dumps(rsp)

        vm.merge_snapshot(cmd)
        return jsonobject.dumps(rsp)

    @staticmethod
    def _get_snapshot_size(install_path):
        size = linux.get_local_file_disk_usage(install_path)
        if size is None or size == 0:
            if install_path.startswith("/dev/"):
                size = int(lvm.get_lv_size(install_path))
            else:
                size = linux.qcow2_virtualsize(install_path)
        return size

    @kvmagent.replyerror
    def take_volumes_snapshots(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])  # type: TakeSnapshotsCmd
        rsp = TakeSnapshotsResponse()  # type: TakeSnapshotsResponse

        for snapshot_job in cmd.snapshotJobs:
            if snapshot_job.vmInstanceUuid != cmd.snapshotJobs[0].vmInstanceUuid:
                raise kvmagent.KvmError("can not take snapshot on multiple vms[%s and %s]" %
                                        snapshot_job.vmInstanceUuid, cmd.snapshotJobs[0].vmInstanceUuid)
            if snapshot_job.live != cmd.snapshotJobs[0].live:
                raise kvmagent.KvmError("can not take snapshot on different live status")

            Vm.ensure_no_internal_snapshot(snapshot_job.volume.installPath)

        def makedir_if_need(new_path):
            dirname = os.path.dirname(new_path)
            if not os.path.exists(dirname):
                os.makedirs(dirname, 0o755)

        def get_size(install_path):
            """
            :rtype: long
            """
            return VmPlugin._get_snapshot_size(install_path)

        def take_full_snapshot_by_qemu_img_convert(previous_install_path, install_path, new_volume_install_path):
            """
            :rtype: (str, str, long)
            """
            makedir_if_need(install_path)
            linux.create_template(previous_install_path, install_path)
            new_volume_path = new_volume_install_path if new_volume_install_path is not None else os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
            makedir_if_need(new_volume_path)
            linux.qcow2_clone_with_cmd(install_path, new_volume_path, cmd)

            return install_path, new_volume_path, get_size(install_path)

        def take_delta_snapshot_by_qemu_img_convert(previous_install_path, install_path, new_volume_install_path):
            """
            :rtype: (str, str, long)
            """
            new_volume_path = new_volume_install_path if new_volume_install_path is not None else os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
            makedir_if_need(new_volume_path)
            linux.qcow2_clone_with_cmd(previous_install_path, new_volume_path, cmd)

            return previous_install_path, new_volume_path, get_size(install_path)

        vm = get_vm_by_uuid(cmd.snapshotJobs[0].vmInstanceUuid, exception_if_not_existing=False)
        try:
            vm_state = Vm.VM_STATE_SHUTDOWN if vm is None else vm.state
            expected_snapshot_state = LIVE_SNAPSHOT if cmd.snapshotJobs[0].live else OFFLINE_SNAPSHOT
            if vm_state not in Vm.SNAPSHOT_VM_STATE_DICT[expected_snapshot_state]:
                raise kvmagent.KvmError(
                    'unable to take snapshot on vm[uuid:{0}] volume[id:{1}], because vm is {2} on host, it does not match the expected state[{3}] '
                    'when taking an {4}'.format(cmd.snapshotJobs[0].vmInstanceUuid, cmd.snapshotJobs[0].deviceId, vm_state,
                    Vm.SNAPSHOT_VM_STATE_DICT[expected_snapshot_state], expected_snapshot_state))

            volume_install_paths = map(lambda job: job.previousInstallPath, filter(lambda job: not job.full and not job.memory, cmd.snapshotJobs))
            for volume_install_path in volume_install_paths:
                Vm.ensure_delta_snapshot_not_exceed(volume_install_path)
            if vm and (vm.state == vm.VM_STATE_RUNNING or vm.state == vm.VM_STATE_PAUSED):
                rsp.snapshots = vm.take_live_volumes_delta_snapshots(cmd.snapshotJobs)
            else:
                for snapshot_job in cmd.snapshotJobs:
                    if snapshot_job.full:
                        rsp.snapshots.append(VolumeSnapshotResultStruct(
                            snapshot_job.volumeUuid, *take_full_snapshot_by_qemu_img_convert(
                                snapshot_job.previousInstallPath, snapshot_job.installPath, snapshot_job.newVolumeInstallPath)))
                    else:
                        rsp.snapshots.append(VolumeSnapshotResultStruct(
                            snapshot_job.volumeUuid, *take_delta_snapshot_by_qemu_img_convert(
                                snapshot_job.previousInstallPath, snapshot_job.installPath, snapshot_job.newVolumeInstallPath)))

        except kvmagent.KvmError as error:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(error)
            rsp.success = False

        touchQmpSocketWhenExists(cmd.snapshotJobs[0].vmInstanceUuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_volume_snapshot(self, req):
        """ Take snapshot for a volume

        :param req: The request obj, exmaple of req.body::
            {
                'vmUuid': '0dc62031678d404095e464fb217a2669',
                'volumeUuid': '2e9fd964ba334214aaadc6e16b9ae72b',
                'volumeChainToCheck': {"path1":1, "path2":0, "path3":2}
            }
        """
        rsp = kvmagent.AgentResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
        if vm and vm.state != vm.VM_STATE_RUNNING and vm.state != vm.VM_STATE_SHUTDOWN and vm.state != vm.VM_STATE_PAUSED:
            raise kvmagent.KvmError(
                'unable to take snapshot on vm[uuid:{0}] volume[id:{1}], because vm is not Running, Stopped or Paused, current state is {2}'.format(
                vm.uuid, cmd.volume.deviceId, vm.state))

        sorted_volume_chain = map(lambda x: x[0], sorted(cmd.volumeChainToCheck.items(), key=lambda item: item[1], reverse=True))

        # check if any inconsistent issue happened on top layer
        disk, disk_name = vm._get_target_disk_by_path(sorted_volume_chain[0], is_exception=False)
        if disk_name is None and disk is None:
            rsp.success = False
            rsp.error = "cannot found volume[uuid:%s] with install path %s. Please check volume's top layer" % (
                cmd.volumeUuid, sorted_volume_chain[0])
            return jsonobject.dumps(rsp)

        back_file_chain = vm._get_backfile_chain(cmd.currentInstallPath)
        # get backing files and insert currentInstallPath at first for compare
        back_file_chain.insert(0, cmd.currentInstallPath)

        # image cache should be excluded from host side
        if cmd.excludeInstallPaths and len(cmd.excludeInstallPaths) > 0:
            logger.debug("those paths %s should be exlcuded in back_file_chain" % cmd.excludeInstallPaths)
            back_file_chain = filter(lambda a: a not in cmd.excludeInstallPaths, back_file_chain)

        if back_file_chain == sorted_volume_chain:
            logger.debug('volume[uuid:%s] chain matched, return success' % cmd.volumeUuid)
            return jsonobject.dumps(rsp)

        logger.debug("""
CHECK VOLUME SNAPSHOT CHAIN
vm instance uuid: {0}
volume uuid: {1}
management node side snapshot files chain:
{2}
host side snapshot files chian:
{3}""".format(cmd.vmUuid, cmd.volumeUuid, '\n'.join(sorted_volume_chain), '\n'.join(back_file_chain)))

        result = list(difflib.context_diff(sorted_volume_chain, back_file_chain, 'Management Node Side', 'HostSide', lineterm=''))
        if len(result) > 0:
            rsp.success = False
            rsp.error = "%s%s%s" % ('\n', '\n'.join(result), '\n')

        return jsonobject.dumps(rsp)

    @staticmethod
    def active_volume_if_need(volume_path):
        if volume_path.startswith("/dev/") and not os.path.exists(volume_path):
            lvm.active_lv(volume_path)

    @kvmagent.replyerror
    def take_volume_snapshot(self, req):
        """ Take snapshot for a volume

        :param req: The request obj, exmaple of req.body::
            {
                'vmUuid': '0dc62031-678d-4040-95e4-64fb217a2669',
                'volumeUuid': '2e9fd964-ba33-4214-aaad-c6e16b9ae72b',
                'volume': {

                },
                'installPath': '',
                'volumeInstallPath': '',
                'newVolumeUuid': '',
                'newVolumeInstallPath': '',
                'fullSnapshot': False,
                'isBaremetal2InstanceOnlineSnapshot': False
            }
        """
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = TakeSnapshotResponse()

        def makedir_if_need(new_path):
            dirname = os.path.dirname(new_path)
            if not os.path.exists(dirname):
                os.makedirs(dirname, 0755)

        def take_full_snapshot_by_qemu_img_convert(previous_install_path, install_path):
            makedir_if_need(install_path)
            linux.create_template(previous_install_path, install_path)
            new_volume_path = cmd.newVolumeInstallPath if cmd.newVolumeInstallPath is not None else os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
            makedir_if_need(new_volume_path)
            self.active_volume_if_need(new_volume_path)
            linux.qcow2_clone_with_cmd(install_path, new_volume_path, cmd)
            return install_path, new_volume_path

        def take_delta_snapshot_by_qemu_img_convert(previous_install_path, install_path):
            Vm.ensure_delta_snapshot_not_exceed(previous_install_path)
            new_volume_path = cmd.newVolumeInstallPath if cmd.newVolumeInstallPath is not None else os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
            makedir_if_need(new_volume_path)
            linux.qcow2_clone_with_cmd(previous_install_path, new_volume_path, cmd)
            return previous_install_path, new_volume_path

        try:
            Vm.ensure_no_internal_snapshot(cmd.volumeInstallPath)
            if not cmd.vmUuid:
                if cmd.fullSnapshot:
                    rsp.snapshotInstallPath, rsp.newVolumeInstallPath = take_full_snapshot_by_qemu_img_convert(
                        cmd.volumeInstallPath, cmd.installPath)
                else:
                    rsp.snapshotInstallPath, rsp.newVolumeInstallPath = take_delta_snapshot_by_qemu_img_convert(
                        cmd.volumeInstallPath, cmd.installPath)

            else:
                # New params in cmd:
                # A flag to show the instance is bm instance and the instance
                # status is online
                if cmd.isBaremetal2InstanceOnlineSnapshot:
                    with bm_utils.NamedLock(name='baremetal_v2_volume_operator'):
                        src_vol_driver, dst_vol_driver = BmV2GwAgent.pre_take_volume_snapshot(cmd)
                        try:
                            rsp.snapshotInstallPath, rsp.newVolumeInstallPath = take_delta_snapshot_by_qemu_img_convert(
                                cmd.volumeInstallPath, cmd.installPath)
                            BmV2GwAgent.post_take_volume_snapshot(src_vol_driver, dst_vol_driver)
                        except Exception as e:
                            # Try to rollback the snapshot action
                            # BmV2GwAgent.resume_device(src_vol_driver)
                            BmV2GwAgent.rollback_volume_snapshot(
                                src_vol_driver, dst_vol_driver)
                            logger.error(traceback.format_exc())
                            raise e
                else:
                    vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)

                    vm_state = Vm.VM_STATE_SHUTDOWN if vm is None else vm.state
                    expected_snapshot_state = LIVE_SNAPSHOT if cmd.online else OFFLINE_SNAPSHOT
                    if vm_state not in Vm.SNAPSHOT_VM_STATE_DICT[expected_snapshot_state]:
                        raise kvmagent.KvmError('unable to take snapshot on vm[uuid:{0}] volume[id:{1}], because vm is {2} on host, it does not match the expected state[{3}] '
                            'when taking an {4}'.format(cmd.vmUuid, cmd.volume.deviceId, vm_state,
                            Vm.SNAPSHOT_VM_STATE_DICT[expected_snapshot_state], expected_snapshot_state))

                    if vm and (vm.state == vm.VM_STATE_RUNNING or vm.state == vm.VM_STATE_PAUSED):
                        rsp.snapshotInstallPath, rsp.newVolumeInstallPath = vm.take_volume_snapshot(cmd,
                                                                                                    cmd.volume,
                                                                                                    cmd.installPath,
                                                                                                    cmd.fullSnapshot)
                    else:
                        if cmd.fullSnapshot:
                            rsp.snapshotInstallPath, rsp.newVolumeInstallPath = take_full_snapshot_by_qemu_img_convert(
                                cmd.volumeInstallPath, cmd.installPath)
                        else:
                            rsp.snapshotInstallPath, rsp.newVolumeInstallPath = take_delta_snapshot_by_qemu_img_convert(
                                cmd.volumeInstallPath, cmd.installPath)

                if cmd.fullSnapshot:
                    logger.debug(
                        'took full snapshot on vm[uuid:{0}] volume[id:{1}], snapshot path:{2}, new volulme path:{3}'.format(
                            cmd.vmUuid, cmd.volume.deviceId, rsp.snapshotInstallPath, rsp.newVolumeInstallPath))
                else:
                    logger.debug(
                        'took delta snapshot on vm[uuid:{0}] volume[id:{1}], snapshot path:{2}, new volulme path:{3}'.format(
                            cmd.vmUuid, cmd.volume.deviceId, rsp.snapshotInstallPath, rsp.newVolumeInstallPath))

            linux.sync_file(rsp.snapshotInstallPath)
            rsp.size = VmPlugin._get_snapshot_size(rsp.snapshotInstallPath)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        if not cmd.isBaremetal2InstanceOnlineSnapshot:
            touchQmpSocketWhenExists(cmd.vmUuid)
        return jsonobject.dumps(rsp)

    def do_cancel_vm_backup_jobs(self, cmd):
        isc = ImageStoreClient()
        isc.stop_vm_backup_jobs(cmd.vmUuid, cmd.force)

    def do_cancel_volume_backup_job(self, cmd, drive):
        isc = ImageStoreClient()
        isc.stop_volume_backup_job(cmd.vmUuid, drive, cmd.force)

    # returns list[VolumeBackupInfo]
    def do_take_volumes_backup(self, cmd, target_disks, bitmaps, dest):
        isc = ImageStoreClient()
        backupArgs = {}
        final_backup_args = []
        speed = cmd.volumeWriteBandwidth if cmd.volumeWriteBandwidth else 0
        backing_files = {}

        device_ids = [volume.deviceId for volume in cmd.volumes]
        for deviceId in device_ids:
            target_disk = target_disks[deviceId]
            drivertype = target_disk.driver.type_
            nodename = self.get_disk_device_name(target_disk)
            source_file = self.get_source_file_by_disk(target_disk)
            bitmap = bitmaps[deviceId]

            bf = linux.qcow2_get_backing_file(source_file) if drivertype == 'qcow2' else None
            if bf:
                backing_files[deviceId] = bf

            def get_backup_args():
                if bitmap:
                    return bitmap, 'full' if cmd.mode == 'full' else 'auto', nodename, speed

                bm = 'zsbitmap%d' % deviceId
                if cmd.mode == 'full' or not bf:
                    return bm, 'full', nodename, speed

                return bm, 'top', nodename, speed

            args = get_backup_args()
            backupArgs[deviceId] = args
            final_backup_args.append(args)

        ext_args = []
        if cmd.pointInTime:
            ext_args.append('-point-in-time')
        if cmd.outOfBand:
            ext_args.append('-oob')

        logger.info('{api: %s} taking backup for vm: %s' % (cmd.threadContext["api"], cmd.vmUuid))
        res = isc.backup_volumes(cmd.vmUuid, final_backup_args, dest, task_spec=cmd, extra_args=ext_args)
        logger.info('{api: %s} completed backup for vm: %s' % (cmd.threadContext["api"], cmd.vmUuid))

        backres = jsonobject.loads(res)
        bkinfos = []

        for deviceId in device_ids:
            nodename = backupArgs[deviceId][2]
            nodebak = backres[nodename]

            parent = None
            if nodebak.mode == 'incremental':
                parent = self.getLastBackup(deviceId, cmd.backupInfos)
            elif (nodebak.mode == 'top' or backupArgs[deviceId][1] == 'top') and deviceId in backing_files:
                imf = isc.upload_image(cmd.hostname, backing_files[deviceId], cmd.uploadConcurrency)
                parent = isc._build_install_path(imf.name, imf.id)

            info = VolumeBackupInfo(deviceId,
                    backupArgs[deviceId][0],
                    nodebak.backupFile,
                    parent)

            bkinfos.append(info)

        return bkinfos

    # returns tuple: (bitmap, parent)
    def do_take_volume_backup(self, cmd, drivertype, nodename, source_file, dest):
        isc = ImageStoreClient()
        parent = None
        bf = None

        if drivertype == 'qcow2':
            bf = linux.qcow2_get_backing_file(source_file)

        def get_parent_bitmap_mode():
            if cmd.bitmap:
                return cmd.bitmap, 'full' if cmd.mode == 'full' else 'auto'

            bitmap = 'zsbitmap%d' % (cmd.volume.deviceId)
            if cmd.mode == 'full' or not bf:
                return bitmap, 'full'

            return bitmap, 'top'

        bitmap, mode = get_parent_bitmap_mode()

        ext_args = []
        if cmd.pointInTime:
            ext_args.append('-point-in-time')
        if cmd.outOfBand:
            ext_args.append('-oob')
        if cmd.volumeWriteBandwidth:
            ext_args.append('-speed %s' % cmd.volumeWriteBandwidth)
        actual_mode = isc.backup_volume(cmd.vmUuid, nodename, bitmap, mode, dest, task_spec=cmd, extra_args=ext_args)
        logger.info('{api: %s} finished backup volume with mode: %s' % (cmd.threadContext["api"], mode))

        if actual_mode == 'incremental':
            return bitmap, cmd.lastBackup

        if (actual_mode == 'top' or mode == 'top') and bf:
            imf = isc.upload_image(cmd.hostname, bf, cmd.uploadConcurrency)
            parent = isc._build_install_path(imf.name, imf.id)

        return bitmap, parent

    @staticmethod
    def get_disk_device_name(disk):
        # The disk type on FT-backup_vm is quorom
        return ('' if disk.type_ == 'quorum' else 'drive-') + disk.alias.name_

    def getLastBackup(self, deviceId, backupInfos):
        for info in backupInfos:
            if info.deviceId == deviceId:
                return info.lastBackup

        return None

    def getBitmap(self, deviceId, backupInfos):
        for info in backupInfos:
            if info.deviceId == deviceId:
                return info.bitmap

        return None

    @kvmagent.replyerror
    def cancel_backup_jobs(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CancelBackupJobsResponse()

        try:
            vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
            if not vm:
                raise kvmagent.KvmError("vm[uuid: %s] not found by libvirt" % cmd.vmUuid)

            self.do_cancel_vm_backup_jobs(cmd)
        except kvmagent.KvmError as e:
            logger.warn("cancel vm[uuid:%s] backup failed: %s" % (cmd.vmUuid, str(e)))
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def cancel_backup_job(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CancelBackupJobResponse()

        try:
            vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
            if not vm:
                raise kvmagent.KvmError("vm[uuid: %s] not found by libvirt" % cmd.vmUuid)

            target_disk, _ = vm._get_target_disk(cmd.volume)
            drive = self.get_disk_device_name(target_disk)

            self.do_cancel_volume_backup_job(cmd, drive)
        except kvmagent.KvmError as e:
            logger.warn("cancel volume[uuid:%s] backup failed: %s" % (cmd.volume.volumeUuid, str(e)))
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def take_volumes_backups(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = TakeVolumesBackupsResponse()

        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
        if not vm:
            raise kvmagent.KvmError("vm[uuid: %s] not found by libvirt" % cmd.vmUuid)

        storage = RemoteStorageFactory.get_remote_storage(cmd)
        try:
            storage.connect()
            target_disks = {}
            for volume in cmd.volumes:
                target_disk, _ = vm._get_target_disk(volume)
                target_disks[volume.deviceId] = target_disk

            bitmaps = {}
            device_ids = [volume.deviceId for volume in cmd.volumes]
            for deviceId in device_ids:
                bitmap = self.getBitmap(deviceId, cmd.backupInfos)
                bitmaps[deviceId] = bitmap

            res = self.do_take_volumes_backup(cmd,
                                              target_disks,
                                              bitmaps,
                                              storage.workspace())

            res.sort(key=lambda d: d.deviceId)
            for idx, r in enumerate(res):
                if r.backupFile:
                    r.backupFile = os.path.join(cmd.uploadDir, r.backupFile)
                else:
                    r.backupFile = cmd.backupPaths[idx]
            rsp.backupInfos = res

        except Exception as e:
            content = traceback.format_exc()
            logger.warn("take vm[uuid:%s] backup failed: %s\n%s" % (cmd.vmUuid, str(e), content))
            rsp.error = str(e)
            rsp.success = False
        finally:
            storage.disconnect()

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def cancel_volume_mirror(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CancelVolumeMirrorResponse()

        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
        if not vm:
            raise kvmagent.KvmError("vm[uuid: %s] not found by libvirt" % cmd.vmUuid)

        try:
            target_disk, _ = vm._get_target_disk(cmd.volume)
            node_name = self.get_disk_device_name(target_disk)
            isc = ImageStoreClient()
            isc.stop_mirror(cmd.vmUuid, cmd.complete, node_name, cmd.force)
        except Exception as e:
            content = traceback.format_exc()
            logger.warn("stop volume mirror failed: " + str(e) + '\n' + content)
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_volume_mirror_mode(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeMirrorModeResponse()

        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
        if not vm:
            raise kvmagent.KvmError("vm[uuid: %s] not found by libvirt" % cmd.vmUuid)

        target_disk, _ = vm._get_target_disk(cmd.volume)
        node_name = self.get_disk_device_name(target_disk)
        installPath = cmd.volume.installPath
        lastVolume, currVolume, volumeType = "", "", "raw"

        if not installPath.startswith("ceph://"):
            lastVolume = cmd.lastMirrorVolume
            currVolume = installPath.split(":/")[-1]
            volumeType = "qcow2"

        isc = ImageStoreClient()
        mode = isc.get_mirror_mode(cmd.vmUuid, node_name, lastVolume, currVolume, volumeType)
        rsp.mode = mode
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def query_volume_mirror(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = QueryVolumeMirrorResponse()

        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
        if not vm:
            raise kvmagent.KvmError("vm[uuid: %s] not found by libvirt" % cmd.vmUuid)

        isc = ImageStoreClient()
        volumes = isc.query_mirror_volumes(cmd.vmUuid)
        if volumes is None:
            return jsonobject.dumps(rsp)

        voldict = {}  # type: dict[str, str]
        for v in cmd.volumes:
            target_disk, _ = vm._get_target_disk(v)
            dev_name = self.get_disk_device_name(target_disk)
            voldict[dev_name] = v.volumeUuid
            # for compatibility
            if dev_name not in volumes:
                node_name = get_block_node_name_by_disk_name(cmd.vmUuid, target_disk.alias.name_)
                voldict[node_name] = v.volumeUuid

        for node_name in volumes:
            try:
                rsp.mirrorVolumes.append(voldict[node_name])
            except KeyError:
                rsp.extraMirrorVolumes.append(node_name)
                if cmd.stopExtra:
                    isc.stop_mirror(cmd.vmUuid, False, node_name)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def take_volume_mirror(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = TakeVolumeMirrorResponse()

        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
        if not vm:
            raise kvmagent.KvmError("vm[uuid: %s] not found by libvirt" % cmd.vmUuid)

        try:
            target_disk, _ = vm._get_target_disk(cmd.volume)
            node_name = self.get_disk_device_name(target_disk)

            isc = ImageStoreClient()
            installPath = cmd.volume.installPath
            lastVolume, currVolume, volumeType = "", "", "raw"

            if not installPath.startswith("ceph://"):
                lastVolume = cmd.lastMirrorVolume
                currVolume = installPath.split(":/")[-1]
                volumeType = "qcow2"

            try:
                vm = get_vm_by_uuid(cmd.vmUuid)
                states = vm.domain.jobStats()
                if libvirt.VIR_DOMAIN_JOB_DATA_REMAINING in states and libvirt.VIR_DOMAIN_JOB_DATA_TOTAL in states:
                    rsp.error = "domain already has migrate job, cannot do drive mirror right now."
                    rsp.success = False
                    return jsonobject.dumps(rsp)
            except libvirt.libvirtError:
                pass

            try:
                volumes = isc.query_mirror_volumes(cmd.vmUuid)
                if volumes is None:
                    volumes = {}
                target = volumes[node_name]
                if target != cmd.mirrorTarget:
                    isc.stop_mirror(cmd.vmUuid, False, node_name)
            except KeyError:
                pass

            isc.mirror_volume(cmd.vmUuid, node_name, cmd.mirrorTarget, lastVolume, currVolume, volumeType, cmd.mode, cmd.speed, Report.from_spec(cmd, "TakeMirror"))

            execute_qmp_command(cmd.vmUuid, '{"execute": "migrate-set-capabilities","arguments":'
                                            '{"capabilities":[ {"capability": "dirty-bitmaps", "state":true}]}}')
            logger.info('finished mirroring volume[%s]: %s' % (node_name, cmd.volume))

        except Exception as e:
            content = traceback.format_exc()
            logger.warn("take volume mirror failed: " + str(e) + '\n' + content)
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def query_vm_mirror_latencies_boundary(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = QueryMirrorLatencyResponse()

        threads = []
        isc = ImageStoreClient()
        maxVmInfoMap = {}
        minVmInfoMap = {}

        try:
            for uuid in cmd.vmUuids:
                threads.append(QueryVmLatenciesThread(isc.query_vm_mirror_latencies_boundary, uuid, cmd.times))
            for t in threads:
                t.start()
            for t in threads:
                t.join()
                vmUuid, maxInfoMap, minInfoMap = t.getResult()
                if not maxInfoMap and not minInfoMap:
                    continue
                maxVmInfoMap[vmUuid] = maxInfoMap
                minVmInfoMap[vmUuid] = minInfoMap

            rsp.vmCurrentMaxCdpLatencyInfos = maxVmInfoMap
            rsp.vmCurrentMinCdpLatencyInfos = minVmInfoMap
        except Exception as e:
            rsp.error = str(e)
            rsp.success = False
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def query_block_job_status(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()
        for i in range(0, 6):
            _, err = execute_qmp_command(cmd.vmUuid, '{"execute":"query-block-jobs"}')
            if err:
                rsp.success = False
                rsp.error = "Failed to query block jobs, report error"
                return jsonobject.dumps(rsp)
            time.sleep(0.5)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def take_volume_backup(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = TakeVolumeBackupResponse()

        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
        if not vm:
            raise kvmagent.KvmError("vm[uuid: %s] not found by libvirt" % cmd.vmUuid)

        storage = RemoteStorageFactory.get_remote_storage(cmd)
        fname = os.path.basename(cmd.backupPath) if cmd.backupPath else uuidhelper.uuid() + ".qcow2"
        try:
            storage.connect()
            target_disk, _ = vm._get_target_disk(cmd.volume)
            source_file = self.get_source_file_by_disk(target_disk)
            bitmap, parent = self.do_take_volume_backup(cmd,
                    target_disk.driver.type_, # 'qcow2' etc.
                    self.get_disk_device_name(target_disk), # 'drive-virtio-disk0', 'scsi-0-0-1' etc.
                    source_file,
                    storage.worktarget(fname))

            logger.info('{api: %s}  finished backup volume with parent: %s' % (cmd.threadContext["api"], cmd.parent))
            rsp.bitmap = bitmap
            rsp.parentInstallPath = parent
            rsp.backupFile = os.path.join(cmd.uploadDir, fname)

        except Exception as e:
            content = traceback.format_exc()
            logger.warn("take volume backup failed: " + str(e) + '\n' + content)
            rsp.error = str(e)
            rsp.success = False

        finally:
            storage.disconnect()

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def block_stream(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = BlockStreamResponse()
        if not cmd.vmUuid:
            rsp.success = True
            return jsonobject.dumps(rsp)

        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
        if not vm:
            rsp.success = True
            return jsonobject.dumps(rsp)

        vm.block_stream_disk(cmd, cmd.volume)
        rsp.success = True
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def block_commit(self, req):
        def block_commit_with_qemu_img():
            top = get_volume_actual_installpath(cmd.top)
            base = get_volume_actual_installpath(cmd.base)
            linux.qcow2_commit(top, base)
            return base

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = BlockCommitResponse()
        try:
            if not cmd.vmUuid:
                rsp.newVolumeInstallPath = block_commit_with_qemu_img()
            else:
                vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
                vm_state = Vm.VM_STATE_SHUTDOWN if vm is None else vm.state
                if vm and (vm_state == vm.VM_STATE_RUNNING or vm_state == vm.VM_STATE_PAUSED):
                    rsp.newVolumeInstallPath = vm.do_block_commit(cmd, cmd.volume)
                else:
                    rsp.newVolumeInstallPath = block_commit_with_qemu_img()

        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False
            return jsonobject.dumps(rsp)

        rsp.size = VmPlugin._get_snapshot_size(rsp.newVolumeInstallPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @lock.lock('iscsiadm')
    def logout_iscsi_target(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        shell.call(
            'iscsiadm  -m node  --targetname "%s" --portal "%s:%s" --logout' % (cmd.target, cmd.hostname, cmd.port))
        rsp = LogoutIscsiTargetRsp()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def login_iscsi_target(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        if cmd.url:
            iscsi.connect_iscsi_target(cmd.url)
        else:
            login = iscsi.IscsiLogin()
            login.server_hostname = cmd.hostname
            login.server_port = cmd.port
            login.chap_password = cmd.chapPassword
            login.chap_username = cmd.chapUsername
            login.target = cmd.target
            login.login()
            login.rescan()

        return jsonobject.dumps(LoginIscsiTargetRsp())

    @kvmagent.replyerror
    def delete_console_firewall_rule(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        vir = VncPortIptableRule()
        vir.vm_internal_id = cmd.vmInternalId
        vir.host_ip = cmd.hostManagementIp
        vir.delete()

        return jsonobject.dumps(kvmagent.AgentResponse())

    @kvmagent.replyerror
    def create_ceph_secret_key(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        VmPlugin._create_ceph_secret_key(cmd.userKey, cmd.uuid)
        return jsonobject.dumps(kvmagent.AgentResponse())

    @staticmethod
    def _reload_ceph_secret_keys():
        for u, k in VmPlugin.secret_keys.items():
            VmPlugin._create_ceph_secret_key(k, u)

    @staticmethod
    def _create_ceph_secret_key(userKey, uuid):
        VmPlugin.secret_keys[uuid] = userKey

        sh_cmd = shell.ShellCmd('virsh secret-get-value %s' % uuid)
        sh_cmd(False)
        if sh_cmd.stdout.strip() == userKey:
            return
        elif sh_cmd.return_code == 0:
            shell.call('virsh secret-set-value %s %s' % (uuid, userKey))
            return

        # for some reason, ceph doesn't work with the secret created by libvirt
        # we have to use the command line here
        content = '''
<secret ephemeral='yes' private='no'>
    <uuid>%s</uuid>
    <usage type='ceph'>
        <name>%s</name>
    </usage>
</secret>
    ''' % (uuid, uuid)

        spath = linux.write_to_temp_file(content)
        try:
            o = shell.call("virsh secret-define %s" % spath)
            o = o.strip(' \n\t\r')
            _, generateuuid, _ = o.split()
            shell.call('virsh secret-set-value %s %s' % (generateuuid, userKey))
        finally:
            os.remove(spath)

    @staticmethod
    def add_amdgpu_to_blacklist():
        r_amd = bash.bash_r("grep -E 'modprobe.blacklist.*amdgpu' /etc/default/grub")
        if r_amd != 0:
            r_amd, o_amd, e_amd = bash.bash_roe("sed -i 's/radeon/amdgpu,radeon/g' /etc/default/grub")
            if r_amd != 0:
                return False, "%s %s" % (e_amd, o_amd)
            r_amd, o_amd, e_amd = bash.bash_roe("grub2-mkconfig -o /boot/grub2/grub.cfg")
            if r_amd != 0:
                return False, "%s %s" % (e_amd, o_amd)
            r_amd, o_amd, e_amd = bash.bash_roe("grub2-mkconfig -o /etc/grub2-efi.cfg")
            if r_amd != 0:
                return False, "%s %s" % (e_amd, o_amd)

        return True, None

    @kvmagent.replyerror
    @in_bash
    def hot_plug_pci_device(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = HotPlugPciDeviceRsp()
        addr = cmd.pciDeviceAddress
        domain, bus, slot, function = parse_pci_device_address(addr)

        content = '''
<hostdev mode='subsystem' type='pci'>
     <driver name='vfio'/>
     <source>
       <address type='pci' domain='0x%s' bus='0x%s' slot='0x%s' function='0x%s'/>
     </source>
</hostdev>''' % (domain, bus, slot, function)
        spath = linux.write_to_temp_file(content)

        # do not attach pci device immediately after detach pci device from same vm
        vm = get_vm_by_uuid(cmd.vmUuid)
        vm._wait_vm_run_until_seconds(60)
        self.timeout_object.wait_until_object_timeout('hot-unplug-pci-device-from-vm-%s' % cmd.vmUuid)
        r, o, e = bash.bash_roe("virsh attach-device %s %s" % (cmd.vmUuid, spath))
        self.timeout_object.put('hot-plug-pci-device-to-vm-%s' % cmd.vmUuid, timeout=30)
        if r != 0:
            rsp.success = False
            err = self.handle_vfio_irq_conflict_with_addr(cmd.vmUuid, addr)
            if err == "":
                rsp.error = "failed to attach-device %s to %s: %s, %s" % (addr, cmd.vmUuid, o, e)
            else:
                rsp.error = "failed to handle_vfio_irq_conflict_with_addr: %s, details: %s %s" % (err, o, e)

        logger.debug("attach-device %s to %s: %s, %s" % (spath, cmd.vmUuid, o, e))
        return jsonobject.dumps(rsp)

    @in_bash
    def handle_vfio_irq_conflict_with_addr(self, vmUuid, addr):
        logger.debug("check irq conflict with %s, %s" % (vmUuid, addr))
        cmd = ("tail -n 5 /var/log/libvirt/qemu/%s.log | grep -E 'vfio: Error: Failed to setup INTx fd: Device or resource busy'" %
                vmUuid)
        r, o, e = bash.bash_roe(cmd)
        if r != 0:
            return ""
        cmd = "lspci -vs %s | grep IRQ | awk '{print $5}' | grep -E -o '[[:digit:]]+'" % addr
        r, o, e = bash.bash_roe(cmd)
        if o == "":
            return "can not get irq"
        hostname = linux.get_hostname_fqdn()

        cmd = "devices=`find /sys/devices/ -iname 'irq' | grep pci | xargs grep %s | grep -v '%s' | awk -F '/' '{ print \"/\"$2\"/\"$3\"/\"$4\"/\"$5 }' | sort | uniq`;" % (o.strip(), addr) + \
              " for dev in $devices; do wc -l $dev/msi_bus; done | grep -E '^.*0 /sys' | awk -F '/' '{ print \"/\"$2\"/\"$3\"/\"$4\"/\"$5 }'"
        r, o, e = bash.bash_roe(cmd)
        if o == "":
            return "there are irq conflict, but zstack can not get irq conflict device, you need fix it manually"
        ret = ""
        names = ""
        for dev in o.splitlines():
            if dev.strip() != "":
                ret += "echo 1 > %s/remove; " % dev
                cmd = "lspci -s %s" % dev.split('/')[-1]
                r, o, e = bash.bash_roe(cmd)
                names += o.strip()

        return "WARN: found irq conflict for pci device addr %s, please execute '%s', and then try to passthrough again. Please noted, the above command will remove the conflicted devices(%s) from system, ONLY reboot can bring the device back to service." % \
               (addr, ret, names)

    @in_bash
    def handle_vfio_irq_conflict(self, vmUuid):
        cmd = ("tail -n 5 /var/log/libvirt/qemu/%s.log | grep -E 'qemu.*vfio: Error: Failed to setup INTx fd: Device or resource busy' | awk -F'[=,]' '{ print $3 }'" %
                vmUuid)
        r, o, e = bash.bash_roe(cmd)
        if r != 0:
            return ""
        return self.handle_vfio_irq_conflict_with_addr(vmUuid, o.strip())

    @kvmagent.replyerror
    @in_bash
    def hot_unplug_pci_device(self, req):
        @linux.retry(3, 3)
        def find_pci_device(vm_uuid, pci_addr):
            domain, bus, slot, function = parse_pci_device_address(pci_addr)
            cmd = """virsh dumpxml %s | grep -A3 -E '<hostdev.*pci' | grep "<address domain='0x%s' bus='0x%s' slot='0x%s' function='0x%s'/>" """ % \
                  (vm_uuid, domain, bus, slot, function)
            r, o, e = bash.bash_roe(cmd)
            return o != ""

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = HotUnplugPciDeviceRsp()
        addr = cmd.pciDeviceAddress

        if not find_pci_device(cmd.vmUuid, addr):
            logger.debug("pci device %s not found" % addr)
            return jsonobject.dumps(rsp)

        domain, bus, slot, function = parse_pci_device_address(addr)
        content = '''
<hostdev mode='subsystem' type='pci'>
     <driver name='vfio'/>
     <source>
       <address type='pci' domain='0x%s' bus='0x%s' slot='0x%s' function='0x%s'/>
     </source>
</hostdev>''' % (domain, bus, slot, function)
        spath = linux.write_to_temp_file(content)

        # no need to detach pci device if vm is shutdown
        vm = get_vm_by_uuid_no_retry(cmd.vmUuid, exception_if_not_existing=False)
        if not vm or vm.state == Vm.VM_STATE_SHUTDOWN:
            logger.debug("vm[uuid:%s] is shutdown, no need to detach pci device" % cmd.vmUuid)
            return jsonobject.dumps(rsp)

        # do not detach pci device immediately after starting vm instance
        try:
            vm._wait_vm_run_until_seconds(60)
        except Exception:
            logger.debug("cannot find pid of vm[uuid:%s, state:%s], no need to detach pci device" % (cmd.vmUuid, vm.state))
            return jsonobject.dumps(rsp)

        # do not detach pci device immediately after attach pci device to same vm
        self.timeout_object.wait_until_object_timeout('hot-plug-pci-device-to-vm-%s' % cmd.vmUuid)
        self.timeout_object.put('hot-unplug-pci-device-from-vm-%s' % cmd.vmUuid, timeout=10)

        retry_num = 4
        retry_interval = 5
        logger.debug("try to virsh detach xml for %d times: %s" % (retry_num, content))
        for i in range(1, retry_num + 1):
            r, o, e = bash.bash_roe("virsh detach-device %s %s" % (cmd.vmUuid, spath))
            succ = linux.wait_callback_success(lambda args: not find_pci_device(args[0], args[1]), [cmd.vmUuid, addr], timeout=retry_interval)
            if succ:
                break

            if i < retry_num:
                continue

            if r != 0:
                rsp.success = False
                rsp.error = "failed to detach-device %s from %s: %s, %s" % (addr, cmd.vmUuid, o, e)
                return jsonobject.dumps(rsp)

            if not succ:
                rsp.success = False
                rsp.error = "pci device %s still exists on vm %s after %ds" % (addr, cmd.vmUuid, retry_num * retry_interval)
                return jsonobject.dumps(rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def hot_plug_mdev_device(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = HotPlugMdevDeviceRsp()

        logger.debug('mdev-device:%s' % cmd)

        _uuid = str(uuid.UUID(cmd.MdevDeviceUuid))

        content = '''
<hostdev mode='subsystem' type='mdev' managed='yes' model='vfio-pci' display='off'>
    <source>
        <address uuid='%s'/>
    </source>
</hostdev>''' % (_uuid)
        spath = linux.write_to_temp_file(content)

        r, o, e = bash.bash_roe("virsh attach-device %s %s" % (cmd.vmUuid, spath))
        if r != 0:
            rsp.success = False
            rsp.error = "failed to attach-device %s to %s: %s, %s" % (_uuid, cmd.vmUuid, o, e)

        logger.debug("attach-device %s to %s: %s, %s" % (spath, cmd.vmUuid, o, e))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def hot_unplug_mdev_device(self, req):
        @linux.retry(3, 3)
        def find_mdev_device(vm_uuid, mdev_uuid):
            cmd = """virsh dumpxml %s | grep -A3 -E '<hostdev.*mdev' | grep "<address uuid='%s'/>" """ % \
                  (vm_uuid, mdev_uuid)
            r, o, e = bash.bash_roe(cmd)
            return o != ""

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = HotUnplugMdevDeviceRsp()
        _uuid = str(uuid.UUID(cmd.MdevDeviceUuid))

        if not find_mdev_device(cmd.vmUuid, _uuid):
            logger.debug("mdev device %s not found" % _uuid)
            return jsonobject.dumps(rsp)

        content = '''
<hostdev mode='subsystem' type='mdev' managed='yes' model='vfio-pci' display='off'>
    <source>
        <address uuid='%s'/>
    </source>
</hostdev>''' % (_uuid)
        spath = linux.write_to_temp_file(content)

        retry_num = 4
        retry_interval = 5
        logger.debug("try to virsh detach xml for %d times: %s" % (retry_num, content))
        for i in range(1, retry_num + 1):
            r, o, e = bash.bash_roe("virsh detach-device %s %s" % (cmd.vmUuid, spath))
            succ = linux.wait_callback_success(lambda args: not find_mdev_device(args[0], args[1]), [cmd.vmUuid, _uuid], timeout=retry_interval)
            if succ:
                break

            if i < retry_num:
                continue

            if r != 0:
                rsp.success = False
                rsp.error = "failed to detach-device %s from %s: %s, %s" % (_uuid, cmd.vmUuid, o, e)
                return jsonobject.dumps(rsp)

            if not succ:
                rsp.success = False
                rsp.error = "mdev device %s still exists on vm %s after %ds" % (_uuid, cmd.vmUuid, retry_num * retry_interval)
                return jsonobject.dumps(rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def attach_pci_device_to_host(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AttachPciDeviceToHostRsp()
        addr = cmd.pciDeviceAddress

        r, o, e = bash.bash_roe("virsh nodedev-reattach pci_%s" % addr.replace(':', '_').replace('.', '_'))
        logger.debug("nodedev-reattach %s: %s, %s" % (addr, o, e))
        if r != 0:
            rsp.success = False
            rsp.error = "failed to nodedev-reattach %s: %s, %s" % (addr, o, e)
            return jsonobject.dumps(rsp)

        if os.path.exists('/usr/lib/nvidia/sriov-manage'):
            ret, out, err = self._exec_sriov_manage(addr, True)
            if ret != 0:
                rsp.success = False
                rsp.error = "failed to /usr/lib/nvidia/sriov-manage -e %s: %s, %s" % (addr, o, e)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def detach_pci_device_from_host(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DetachPciDeviceFromHostRsp()
        addr = cmd.pciDeviceAddress

        if os.path.exists('/usr/lib/nvidia/sriov-manage'):
            ret, out, err = self._exec_sriov_manage(addr, False)
            if ret != 0:
                rsp.success = False
                rsp.error = "failed to /usr/lib/nvidia/sriov-manage -d %s: %s, %s" % (addr, out, err)
                return jsonobject.dumps(rsp)

        r, o, e = bash.bash_roe("virsh nodedev-detach pci_%s" % addr.replace(':', '_').replace('.', '_'))
        logger.debug("nodedev-detach %s: %s, %s" % (addr, o, e))
        if r != 0:
            rsp.success = False
            rsp.error = "failed to nodedev-detach %s: %s, %s" % (addr, o, e)

        return jsonobject.dumps(rsp)

    @linux.retry(times=30, sleep_time=5)
    def _exec_sriov_manage(self, addr, is_enable = True):
        if is_enable:
            return bash.bash_roe("/usr/lib/nvidia/sriov-manage -e %s" % addr)
        else:
            return bash.bash_roe("/usr/lib/nvidia/sriov-manage -d %s" % addr)

    def _get_next_usb_port(self, dom, bus):
        domain_xml = dom.XMLDesc(0)
        domain_xmlobject = xmlobject.loads(domain_xml)
        # if arm or mips uhci, port 0, 1, 2 are hard-coded reserved
        # else uhci, port 0, 1 are hard-coded reserved
        if bus == 0 and HOST_ARCH in ['aarch64', 'mips64el', 'loongarch64']:
            usb_ports = [0, 1, 2]
        elif bus == 0:
            usb_ports = [0, 1]
        else:
            usb_ports = [0]
        for hostdev in domain_xmlobject.devices.get_child_node_as_list('hostdev'):
            if hostdev.type_ == 'usb':
                for address in hostdev.get_child_node_as_list('address'):
                    if address.type_ == 'usb' and address.bus_ == str(bus):
                        usb_ports.append(int(address.port_))
        for redirdev in domain_xmlobject.devices.get_child_node_as_list('redirdev'):
            if redirdev.type_ == 'tcp':
                for address in redirdev.get_child_node_as_list('address'):
                    if address.type_ == 'usb' and address.bus_ == str(bus):
                        usb_ports.append(int(address.port_))

        # get the first unused port number
        for i in range(len(usb_ports) + 1):
            if i not in usb_ports:
                return i

    @kvmagent.replyerror
    def kvm_attach_usb_device(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = KvmAttachUsbDeviceRsp()
        r, ex = self._attach_usb_by_libvirt(cmd)
        if not r:
            rsp.success = False
            rsp.error = ex
        return jsonobject.dumps(rsp)

    @linux.retry(times=5, sleep_time=2)
    def _detach_usb_by_libvirt(self, cmd):
        vm = get_vm_by_uuid(cmd.vmUuid)

        root = None
        if cmd.attachType == "PassThrough":
            root = etree.Element('hostdev', {'mode': 'subsystem', 'type': 'usb', 'managed': 'yes'})
            d = e(root, 'source')
            e(d, 'vendor', None, {'id': '0x%s' % cmd.idVendor})
            e(d, 'product', None, {'id': '0x%s' % cmd.idProduct})
            e(d, 'address', None, {'bus': str(cmd.busNum).lstrip('0'), 'device': str(cmd.devNum).lstrip('0')})

        if cmd.attachType == "Redirect":
            root = etree.Element('redirdev', {'bus': 'usb', 'type': 'tcp'})
            e(root, 'source', None, {'mode': 'connect', 'host': cmd.ip, 'service': str(cmd.port)})

        xml = etree.tostring(root)
        logger.info(xml)
        try:
            vm.domain.detachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
        except libvirt.libvirtError as ex:
            logger.warn('detach usb device to domain[%s] failed: %s' % (cmd.vmUuid, str(ex)))
            if "redirdev was not found" in str(ex):
                logger.debug(
                    "cannot find matching redirdev from vm %s domainxml, maybe usb has been detached" % cmd.vmUuid)
                return True

            raise RetryException("failed to detach usb device from %s: %s" % (cmd.vmUuid, str(ex)))

        logger.debug("detached usb device from %s successfully" % cmd.vmUuid)

    def _attach_usb_by_libvirt(self, cmd):
        vm = get_vm_by_uuid(cmd.vmUuid)

        root = None
        if cmd.attachType == "PassThrough":
            root = etree.Element('hostdev', {'mode': 'subsystem', 'type': 'usb', 'managed': 'yes'})
            d = e(root, 'source')
            e(d, 'vendor', None, {'id': '0x%s' % cmd.idVendor})
            e(d, 'product', None, {'id': '0x%s' % cmd.idProduct})
            e(d, 'address', None, {'bus': str(cmd.busNum).lstrip('0'), 'device': str(cmd.devNum).lstrip('0')})
            e(root, 'address', None, {'type': 'usb', 'bus': str(cmd.vmBusNum), 'port': str(self._get_next_usb_port(vm.domain, cmd.vmBusNum))})

        if cmd.attachType == "Redirect":
            root = etree.Element('redirdev', {'bus': 'usb', 'type': 'tcp'})
            e(root, 'source', None, {'mode': 'connect', 'host': cmd.ip, 'service': str(cmd.port)})
            e(root, 'address', None, {'type': 'usb', 'bus': str(cmd.vmBusNum), 'port': str(self._get_next_usb_port(vm.domain, cmd.vmBusNum))})

        xml = etree.tostring(root)
        logger.info(xml)
        try:
            vm.domain.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
        except libvirt.libvirtError as ex:
            logger.warn('attach usb device to domain[%s] failed: %s' % (cmd.vmUuid, str(ex)))
            return False, str(ex)

        return True, None

    # deprecated
    def _attach_usb(self, cmd, bus):
        vm = get_vm_by_uuid(cmd.vmUuid)
        content = ''
        if cmd.attachType == "PassThrough":
            content = '''
    <hostdev mode='subsystem' type='usb' managed='yes'>
      <source>
        <vendor id='0x%s'/>
        <product id='0x%s'/>
        <address bus='%s' device='%s'/>
      </source>
      <address type='usb' bus='%s' port='%s' />
    </hostdev>''' % (cmd.idVendor, cmd.idProduct, int(cmd.busNum), int(cmd.devNum), bus, self._get_next_usb_port(vm.domain, bus))
        if cmd.attachType == "Redirect":
            content = '''
    <redirdev bus='usb' type='tcp'>
      <source mode='connect' host='%s' service='%s'/>
      <address type='usb' bus='%s' port='%s'/>
    </redirdev>''' % (cmd.ip, int(cmd.port), bus, self._get_next_usb_port(vm.domain, bus))
        spath = linux.write_to_temp_file(content)
        r, o, e = bash.bash_roe("virsh attach-device %s %s" % (cmd.vmUuid, spath))
        os.remove(spath)
        logger.debug("attached %s to %s, %s, %s" % (
            spath, cmd.vmUuid, o, e))
        return r, o, e

    @kvmagent.replyerror
    def kvm_detach_usb_device(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = KvmDetachUsbDeviceRsp()
        try:
            self._detach_usb_by_libvirt(cmd)
        except Exception as e:
            rsp.success = False
            rsp.error = str(e)
        return jsonobject.dumps(rsp)

    # deprecated
    @linux.retry(times=5, sleep_time=2)
    def _detach_usb(self, cmd):
        content = ''
        if cmd.attachType == "PassThrough":
            content = '''
    <hostdev mode='subsystem' type='usb' managed='yes'>
      <source>
        <vendor id='0x%s'/>
        <product id='0x%s'/>
        <address bus='%s' device='%s'/>
      </source>
    </hostdev>''' % (cmd.idVendor, cmd.idProduct, int(cmd.busNum), int(cmd.devNum))
        if cmd.attachType == "Redirect":
            content = '''
    <redirdev bus='usb' type='tcp'>
      <source mode='connect' host='%s' service='%s'/>
    </redirdev>''' % (cmd.ip, int(cmd.port))
        spath = linux.write_to_temp_file(content)
        r, o, e = bash.bash_roe("virsh detach-device %s %s" % (cmd.vmUuid, spath))
        os.remove(spath)
        if r:
            if "redirdev was not found" in e:
                logger.debug("cannot find matching redirdev from vm %s domainxml, maybe usb has been detached" % cmd.vmUuid)
                return

            raise RetryException("failed to detach usb device from %s: %s, %s" % (cmd.vmUuid, o, e))
        else:
            logger.debug("detached usb device %s from %s" % (spath, cmd.vmUuid))

    @kvmagent.replyerror
    def reload_redirect_usb(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ReloadRedirectUsbRsp()

        self._detach_usb_by_libvirt(cmd)
        bus = int(cmd.usbVersion[0]) - 1
        r, ex = self._attach_usb_by_libvirt(cmd)
        if not r:
            rsp.success = False
            rsp.error = ex
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def vm_priority(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UpdateVmPriorityRsp()
        for pcs in cmd.priorityConfigStructs:
            pid = linux.find_vm_pid_by_uuid(pcs.vmUuid)
            linux.set_vm_priority(pid, pcs)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def kvm_resize_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = KvmResizeVolumeRsp()

        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)
        vm.resize_volume(cmd.volume, cmd.size)

        touchQmpSocketWhenExists(cmd.vmUuid)
        return jsonobject.dumps(rsp)

    def _guesttools_temp_disk_file_path(self, vm_uuid):
        return "/var/lib/zstack/guesttools/temp_disk_%s.qcow2" % vm_uuid

    def _create_xml_for_guesttools_temp_disk(self, vm_uuid):
        temp_disk_name = 'vdz'
        return """
<disk type='file' device='disk'>
<driver type='qcow2' cache='writeback'/>
<source file='%s'/>
<target dev='%s' bus='virtio'/>
</disk>
""" % (self._guesttools_temp_disk_file_path(vm_uuid), temp_disk_name)

    def _create_xml_file_for_guesttools_temp_disk(self, vm_uuid):
        return linux.write_to_temp_file(self._create_xml_for_guesttools_temp_disk(vm_uuid))

    @kvmagent.replyerror
    @in_bash
    def attach_guest_tools_iso_to_vm(self, req):
        rsp = AttachGuestToolsIsoToVmRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        vm_uuid = cmd.vmInstanceUuid
        if cmd.platform == "Linux":
            iso_path = GUEST_TOOLS_ISO_LINUX_PATH
        elif cmd.platform == "Windows":
            iso_path = GUEST_TOOLS_ISO_PATH
        else:
            rsp.success = False
            rsp.error = "not support platform %s" % cmd.platFrom
            return jsonobject.dumps(rsp)

        if not os.path.exists(iso_path):
            rsp.success = False
            rsp.error = "%s not exists" % iso_path
            return jsonobject.dumps(rsp)

        r, _, _ = bash.bash_roe("virsh dumpxml %s | grep \"%s\"" % (vm_uuid, self._guesttools_temp_disk_file_path(vm_uuid)))
        if cmd.needTempDisk and r != 0:
            temp_disk = self._guesttools_temp_disk_file_path(vm_uuid)
            if not os.path.exists(temp_disk):
                linux.qcow2_create(temp_disk, 1)

            spath = self._create_xml_file_for_guesttools_temp_disk(vm_uuid)
            r, o, e = bash.bash_roe("virsh attach-device %s %s" % (vm_uuid, spath))

            if r != 0:
                rsp.success = False
                rsp.error = "%s, %s" % (o, e)
                return jsonobject.dumps(rsp)
            else:
                logger.debug("attached temp disk %s to %s, %s, %s" % (spath, vm_uuid, o, e))

        # attach guest tools iso to [hs]dc, whose device id is 0
        vm = get_vm_by_uuid(vm_uuid, exception_if_not_existing=False)
        iso = IsoTo()
        iso.deviceId = 0
        iso.path = iso_path

        # in case same iso already attached
        detach_cmd = DetachIsoCmd()
        detach_cmd.vmUuid = vm_uuid
        detach_cmd.deviceId = iso.deviceId
        vm.detach_iso(detach_cmd)

        attach_cmd = AttachIsoCmd()
        attach_cmd.iso = iso
        attach_cmd.vmUuid = vm_uuid
        vm.attach_iso(attach_cmd)
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    @in_bash
    def detach_guest_tools_iso_from_vm(self, req):
        rsp = DetachGuestToolsIsoFromVmRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        vm_uuid = cmd.vmInstanceUuid

        vm = get_vm_by_uuid_no_retry(vm_uuid)

        # detach temp_disk from vm
        temp_disk = self._guesttools_temp_disk_file_path(vm_uuid)
        guesttool_path = "/var/lib/zstack/guesttools/"
        if os.path.exists(guesttool_path) and not os.path.exists(temp_disk):
            linux.qcow2_create(temp_disk, 1)

        @linux.retry(times=3, sleep_time=2)
        def detach_temp_disk_and_retry(vm):
            try:
                vm.domain.detachDevice(self._create_xml_for_guesttools_temp_disk(vm.uuid))
            except Exception:
                logger.info("detach device success, can not find disk vdz")
            if vm._check_target_disk_existing_by_path(self._guesttools_temp_disk_file_path(vm.uuid)):
                raise RetryException("current vm %s can not detach guest tools temp disk" % vm.uuid)

        if vm._check_target_disk_existing_by_path(self._guesttools_temp_disk_file_path(vm.uuid)):
            detach_temp_disk_and_retry(vm)

        # clean temp disk file
        # delete temp disk after device detached refer: http://jira.zstack.io/browse/ZSTAC-45490
        if os.path.exists(temp_disk):
            linux.rm_file_force(temp_disk)

        if cmd.platform == "Linux":
            iso_path = GUEST_TOOLS_ISO_LINUX_PATH
        elif cmd.platform == "Windows":
            iso_path = GUEST_TOOLS_ISO_PATH
        else:
            rsp.success = False
            rsp.error = "not support platform %s" % cmd.platFrom
            return jsonobject.dumps(rsp)

        # detach guesttools iso from vm
        if vm.domain_xml.find(iso_path) > 0:
            detach_cmd = DetachIsoCmd()
            detach_cmd.vmUuid = vm_uuid
            detach_cmd.deviceId = 0
            vm.detach_iso(detach_cmd)

        return jsonobject.dumps(rsp)

    def get_linux_vm_guest_tools_info(self, vmUuid):
        @LibvirtAutoReconnect
        def call_libvirt(conn):
            return conn.lookupByName(vmUuid)

        qga = VmQga(call_libvirt())
        if qga.state != VmQga.QGA_STATE_RUNNING:
            return VmPlugin.GUESTTOOLS_STATE_NOT_CONNECT, None
        try:
            version_data = qga.guest_exec_bash_no_exitcode(
                "/usr/local/zstack/zwatch-vm-agent/zwatch-vm-agent -version 2>/dev/null").strip()
        except:
            version_data = None
        running_data = qga.guest_exec_bash_no_exitcode(
            "ps -ef | grep zwatch-vm-agent | grep -v grep > /dev/null && echo 'True' || echo 'False'").strip()
        if running_data and version_data and "True" == running_data:
            return VmPlugin.GUESTTOOLS_STATE_RUNNING, version_data
        elif running_data and version_data and "False" == running_data:
            return VmPlugin.GUESTTOOLS_STATE_NOT_RUNNING, version_data

        return VmPlugin.GUESTTOOLS_STATE_NOT_RUNNING, None

    @kvmagent.replyerror
    def get_vm_guest_tools_info(self, req):
        rsp = GetVmGuestToolsInfoRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        # get guest tools info by reading VERSION file inside vm
        vm_uuid = cmd.vmInstanceUuid
        if cmd.platform.lower() == 'windows':
            self.get_vm_guest_tools_info_for_windows_guest(vm_uuid, rsp)
        elif cmd.platform.lower() == 'linux':
            try:
                rsp.status, rsp.version = self.get_linux_vm_guest_tools_info(vm_uuid)
            except Exception as e:
                rsp.success = False
                rsp.error = e.message
        return jsonobject.dumps(rsp)

    @in_bash
    def get_vm_guest_tools_info_for_windows_guest(self, vm_uuid, rsp):

        vm = get_vm_by_uuid_no_retry(vm_uuid, True)
        if vm.state != Vm.VM_STATE_RUNNING:
            rsp.success = False
            rsp.error = 'vm[uuid:%s] is not in running state' % vm_uuid
            return

        if not is_qga_connected(vm.domain):
            rsp.success = False
            rsp.error = 'vm[uuid:%s] qga channel is not connected' % vm_uuid
            return

        r, o, e = bash.bash_roe('virsh qemu-agent-command %s --cmd \'{"execute":"guest-file-open", \
                "arguments":{"path":"C:\\\Program Files\\\Common Files\\\GuestTools\\\VERSION", "mode":"r"}}\'' % vm_uuid)
        if r != 0:
            _r, _o, _e = bash.bash_roe("virsh qemu-agent-command %s --cmd '{\"execute\":\"guest-tools-info\"}'" % vm_uuid)
            if _r == 0:
                info = simplejson.loads(_o)['return']
                for k in info.keys():
                    setattr(rsp, k, info[k])
                return
            else:
                rsp.success = False
                rsp.error = "%s, %s" % (o, e)
                return

        fd = simplejson.loads(o)['return']

        def _close_version_file():
            bash.bash_roe('virsh qemu-agent-command %s --cmd \'{"execute":"guest-file-close", "arguments":{"handle":%s}}\'' % (vm_uuid, fd))

        r, o, e = bash.bash_roe('virsh qemu-agent-command %s --cmd \'{"execute":"guest-file-read", "arguments":{"handle":%s}}\'' % (vm_uuid, fd))
        if r != 0:
            _close_version_file()
            rsp.success = False
            rsp.error = "%s, %s" % (o, e)
            return

        version = base64.b64decode(simplejson.loads(o)['return']['buf-b64']).strip()
        rsp.version = version
        rsp.status = VmPlugin.GUESTTOOLS_STATE_RUNNING
        _close_version_file()

    @kvmagent.replyerror
    def get_vm_metrics_routing_status(self, req):
        rsp = GetVmMetricsRoutingStatusRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        if 'lighttpd' in cmd.items:
            self.get_lighttpd_status_for_vm(cmd.vmInstanceUuid, rsp)
        if 'pushgateway' in cmd.items:
            self.get_push_gateway_routing_for_vm(cmd.vmInstanceUuid, rsp)

        return jsonobject.dumps(rsp)

    @in_bash
    def get_lighttpd_status_for_vm(self, vm_uuid, rsp):
        pid_list = filter(lambda pid: pid != '', linux.get_pids_by_process_name('lighttpd'))
        rsp.values['lighttpd.pid'] = ', '.join(pid_list) if pid_list else 'None'

        r, o, _ = bash.bash_roe('ebtables -L | grep "ARP --arp-ip-dst 169.254.169.254 -j USERDATA"')
        # what is the 'o' like?
        #   -p ARP --arp-ip-dst 169.254.169.254 -j USERDATA-br_eth0-8b073443
        rsp.values['lighttpd.ebtables'] = o.strip() if r == 0 else 'None'

    @in_bash
    def get_push_gateway_routing_for_vm(self, vm_uuid, rsp):
        pid_list = filter(lambda pid: pid != '', linux.get_pids_by_process_name('pushgateway'))
        rsp.values['pushgateway.pid'] = ', '.join(pid_list) if pid_list else 'None'

        r, o, _ = bash.bash_roe("netstat -nap | awk '/pushgateway/ { print $4 }'")
        # what is the 'o' like?
        #   :::9092
        #   10.99.99.99:9092
        bind_addresses = list(set(o.strip().split('\n')))
        rsp.values['pushgateway.bind_address'] = ', '.join(bind_addresses) if r == 0 else 'None'

        try:
            if bind_addresses:
                port = bind_addresses[0].split(':')[-1]
                url = 'http://localhost:%s/metrics' % port
                result = http.json_post(url, body=None, headers={'Content-Type':'text/plain'}, method='GET')
                lines = filter(lambda line:
                        line.startswith('push_time_seconds') and line.find(vm_uuid) >= 0,
                        result.split('\n'))
                if lines:
                    push_time_seconds = float(lines[0].split(' ')[-1])
                    rsp.values['pushgateway.guest_tools.metrics.push_time_seconds'] = lines[0].split(' ')[-1]
                    rsp.values['pushgateway.guest_tools.last_time_bias_in_seconds'] = str(time.time() - push_time_seconds)
                else:
                    rsp.values['pushgateway.guest_tools.metrics.push_time_seconds'] = 'None'
        except Exception as ex:
            logger.warn('failed to read metrics from pushgateway: %s', str(ex))

    @kvmagent.replyerror
    @in_bash
    def fail_colo_pvm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        r, _, e = linux.sshpass_run(cmd.targetHostIp, cmd.targetHostPassword, "pkill -f 'qemu-system-x86_64 -name guest=%s'" % cmd.vmInstanceUuid, "root", cmd.targetHostPort)
        if r != 0 and r != 1:
            rsp.success = False
            rsp.error = 'failed to kill vm %s on host %s, cause: %s' % (cmd.vmInstanceUuid, cmd.targetHostIp, e)

        return jsonobject.dumps(rsp)

    @staticmethod
    def clean_vm_firmware_flash(vm_uuid):
        fpath = "/var/lib/libvirt/qemu/nvram/{}.fd".format(vm_uuid)
        linux.rm_file_checked(fpath)

    @kvmagent.replyerror
    def clean_firmware_flash(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        vm_uuid = cmd.vmUuid
        if not get_vm_by_uuid_no_retry(vm_uuid, False):
            self.clean_vm_firmware_flash(vm_uuid)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def apply_memory_balloon(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        for vm_uuid in cmd.vmUuids:
            reserved_memory = cmd.vmReservedMemory[vm_uuid] / 1024 if cmd.vmReservedMemory and cmd.vmReservedMemory.hasattr(vm_uuid) else 0
            self.do_apply_memory_balloon_to_vm(vm_uuid, cmd.direction, cmd.adjustPercent, reserved_memory)

        return jsonobject.dumps(rsp)

    def do_apply_memory_balloon_to_vm(self, vm_uuid, direction, precentage, preserved_memory):
        vm = get_vm_by_uuid_no_retry(vm_uuid, False)
        if not vm:
            logger.debug("vm[uuid:%s] is not running, skip memory balloon" % vm_uuid)
            return

        if vm.state != Vm.VM_STATE_RUNNING:
            logger.debug("vm[uuid:%s] is not running, skip memory balloon" % vm_uuid)
            return

        mem = vm.get_memory_stats()
        if not mem.usable:
            logger.debug("vm[uuid:%s] do not support virtio memory balloon, skip it" % vm_uuid)
            return

        actual_mem = mem.actual
        if actual_mem <= preserved_memory and direction == 'Decrease':
            logger.debug("vm[uuid:%s] actual memory[%s] is less than preserved memory[%s], skip memory balloon" % (vm_uuid, actual_mem, preserved_memory))
            return

        if direction == 'Decrease':
            # do not decrease memory over unused memory
            delta = actual_mem * precentage / 100
            delta = delta if delta < mem.usable else mem.usable
            changed_to = actual_mem - delta
        elif direction == 'Increase':
            # do not increase memory over max memory
            changed_to = actual_mem + mem.max * precentage / 100
            changed_to = changed_to if changed_to < mem.max else mem.max
        else:
            raise Exception('unknown direction[%s]' % direction)

        logger.debug("change vm[uuid:%s] memory from %s to %s" % (vm_uuid, mem.actual, changed_to))
        if mem.actual == changed_to:
            logger.debug("vm[uuid:%s] memory is already changed to %s, skip it" % (vm_uuid, changed_to))
            return

        if changed_to < mem.max * 30 / 100:
            logger.debug("vm[uuid:%s] memory can not changed lower than 30% of its max memory %s, skip it" % (vm_uuid, mem.max))
            return

        if changed_to < 1 * 1024 * 1024:
            logger.debug("vm[uuid:%s] memory can not changed lower than 1GB, skip it" % vm_uuid)
            return

        vm.set_memory(changed_to)
        self.wait_memory_changed(vm_uuid, changed_to)

        vm.set_memory(changed_to)
        self.wait_memory_changed(vm_uuid, changed_to)


    def wait_memory_changed(self, vm_uuid, changed_to):
        def wait_for_actual_memory_change(_):
            vm = get_vm_by_uuid_no_retry(vm_uuid, False)
            if not vm:
                raise Exception('vm[uuid:%s] not exists, failed' % vm_uuid)

            mem = vm.get_memory_stats()
            return mem.actual == changed_to

        if not linux.wait_callback_success(wait_for_actual_memory_change, None, interval=3, timeout=24):
            logger.warn('unable to wait vm[uuid:%s] memory changed, after %s seconds' % (vm_uuid, 24))


    @kvmagent.replyerror
    @in_bash
    def rollback_quorum_config(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        vm = get_vm_by_uuid_no_retry(cmd.vmInstanceUuid, False)
        if not vm:
            raise Exception('vm[uuid:%s] not exists, failed' % cmd.vmInstanceUuid)

        count = 0
        for alias_name in vm._get_all_volume_alias_names(cmd.volumes):
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "x-blockdev-change",'
                                                    ' "arguments": {"parent": "%s", "child": "children.1"}}' % alias_name)
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "human-monitor-command",'
                                                    ' "arguments":{"command-line": "drive_del replication%s"}}' % count)
            count += 1

        for i in xrange(0, cmd.nicNumber):
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                    '"arguments":{"id":"fm-%s"}}' % i)
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                    '"arguments":{"id":"primary-out-redirect-%s"}}' % i)
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                    '"arguments":{"id":"primary-in-redirect-%s"}}' % i)
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                    '"arguments":{"id":"comp-%s"}}' % i)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def fstrim_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        r, o, err = bash.bash_roe("virsh qemu-agent-command %s --cmd '{\"execute\":\"guest-fstrim\"}'" % cmd.vmUuid)
        if r != 0:
            logger.warn("vm[uuid:%s] failed to fstrim : %s, %s" % (self.uuid, o, err))
            rsp.success = False
            rsp.error = err

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def wait_secondary_vm_ready(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        def wait_for_colo_state_change(_):
            vm = get_vm_by_uuid_no_retry(cmd.vmInstanceUuid, False)
            if not vm:
                raise Exception('vm[uuid:%s] not exists, failed' % cmd.vmInstanceUuid)

            colo_status, err = execute_qmp_command(cmd.vmInstanceUuid, '{"execute":"query-colo-status"}')
            if err:
                raise Exception('Failed to check vm[uuid:%s] colo status by query-colo-status' % cmd.vmInstanceUuid)

            mode = colo_status['mode']
            return mode == 'secondary'

        if not linux.wait_callback_success(wait_for_colo_state_change, None, interval=3, timeout=cmd.coloCheckTimeout):
            raise Exception('unable to wait secondary vm[uuid:%s] ready, after %s seconds'
                            % (cmd.vmInstanceUuid, cmd.coloCheckTimeout))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def check_colo_vm_state(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        states = get_all_vm_states()
        rsp = CheckColoVmStateRsp()
        state = states.get(cmd.vmInstanceUuid)
        if state != Vm.VM_STATE_RUNNING or state != Vm.VIR_DOMAIN_PAUSED:
            rsp.state = state
            return jsonobject.dumps(rsp)

        colo_status, err = execute_qmp_command(cmd.vmInstanceUuid, '{"execute":"query-colo-status"}')
        if err:
            rsp.success = False
            rsp.error = "Failed to check vm colo status"
            return jsonobject.dumps(rsp)

        rsp.mode = colo_status['mode']

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def register_primary_vm_heartbeat(self, req):
        rsp = kvmagent.AgentResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        try:
            s.connect((cmd.targetHostIp, cmd.heartbeatPort))
            logger.debug("Successfully test heartbeat to address[%s:%s]" % (cmd.targetHostIp, cmd.heartbeatPort))
        except socket.error as ex:
            logger.debug("Failed to detect heartbeat connection return error")
            rsp.success = False
            rsp.error = "Failed connect to heartbeat address[%s:%s], because %s" % (cmd.targetHostIp, cmd.heartbeatPort, ex)
        finally:
            s.close()

        if not rsp.success:
            return jsonobject.dumps(rsp)

        if self.vm_heartbeat.get(cmd.vmInstanceUuid) is not None and self.vm_heartbeat.get(
                    cmd.vmInstanceUuid).is_alive():
            logger.debug("vm heartbeat thread exists, skip it")
            return jsonobject.dumps(rsp)

        self.vm_heartbeat[cmd.vmInstanceUuid] = thread.ThreadFacade.run_in_thread(self.start_vm_heart_beat, (cmd,))
        if self.vm_heartbeat.get(cmd.vmInstanceUuid).is_alive():
            logger.debug("successfully start vm heartbeat")
        else:
            logger.debug("Failed to start vm heartbeat")
            rsp.success = False
            rsp.error = "Failed to start vm heartbeat address[%s:%s]" % (cmd.targetHostIp, cmd.heartbeatPort)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def start_colo_sync(self, req):
        rsp = kvmagent.AgentResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "qmp_capabilities"}')

        vm = get_vm_by_uuid_no_retry(cmd.vmInstanceUuid, False)
        if not vm:
            raise Exception('vm[uuid:%s] not exists, failed' % cmd.vmInstanceUuid)

        count = 0
        replication_list = []

        def colo_qemu_replication_cleanup():
            for replication in replication_list:
                if replication.alias_name:
                    execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "x-blockdev-change",'
                                                        ' "arguments": {"parent": "%s", "child": "children.1"}}' % replication.alias_name)
                execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "human-monitor-command",'
                                                    ' "arguments":{"command-line": "drive_del replication%s"}}' % replication.replication_id)

        @linux.retry(times=3, sleep_time=0.5)
        def add_nbd_client_to_quorum(alias_name, count):
            ret, err = execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "x-blockdev-change","arguments":'
                                                '{"parent": "%s","node": "replication%s" } }' % (alias_name, count))

            if err:
                return False
            elif 'does not support adding a child' in str(ret):
                raise RetryException("failed to add child to %s" % alias_name)
            else:
                return True


        for alias_name in vm._get_all_volume_alias_names(cmd.volumes):
            if cmd.fullSync:
                execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "drive-mirror", "arguments":{ "device": "%s",'
                                                        ' "job-id": "zs-ft-resync", "target": "nbd://%s:%s/parent%s",'
                                                        ' "mode": "existing", "format": "nbd", "sync": "full"} }'
                                    % (alias_name, cmd.secondaryVmHostIp, cmd.nbdServerPort, count))
                while True:
                    time.sleep(3)
                    block_jobs, err = execute_qmp_command(cmd.vmInstanceUuid, '{"execute":"query-block-jobs"}')
                    if err:
                        rsp.success = False
                        rsp.error = "Failed to get zs-ft-resync job, report error"
                        return jsonobject.dumps(rsp)


                    job = next((job for job in block_jobs if job['device'] == 'zs-ft-resync'), None)

                    if not job:
                        logger.debug("job finished, start colo sync")
                        break

                    if job['status'] == 'ready':
                        break

                    logger.debug("current resync %s/%s, percentage %s" % (
                        job['len'], job['offset'], 100 * (float(job['offset'] / float(job['len'])))))

                execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "stop"}')
                execute_qmp_command(cmd.vmInstanceUuid,
                                '{"execute": "block-job-cancel", "arguments":{ "device": "zs-ft-resync"}}')

                while True:
                    time.sleep(1)
                    block_jobs, err = execute_qmp_command(cmd.vmInstanceUuid, '{"execute":"query-block-jobs"}')
                    if err:
                        rsp.success = False
                        rsp.error = "Failed to query block jobs, report error"
                        return jsonobject.dumps(rsp)

                    job = next((job for job in block_jobs if job['device'] == 'zs-ft-resync'), None)
                    if job:
                        continue

                    break

            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "human-monitor-command","arguments":'
                                                ' {"command-line":"drive_add -n buddy'
                                                ' driver=replication,mode=primary,file.driver=nbd,file.host=%s,'
                                                'file.port=%s,file.export=parent%s,node-name=replication%s"}}'
                                                % (cmd.secondaryVmHostIp, cmd.nbdServerPort, count, count))

            successed = False
            try:
                successed = add_nbd_client_to_quorum(alias_name, count)
            except Exception as e:
                logger.debug("ignore excetion raised by retry")

            if not successed:
                replication_list.append(ColoReplicationConfig(None, count))
                colo_qemu_replication_cleanup()
                execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "cont"}')
                rsp.success = False
                rsp.error = "Failed to setup quorum replication node, report error"
                return jsonobject.dumps(rsp)

            replication_list.append(ColoReplicationConfig(alias_name, count))

            count+=1

        domain_xml = vm.domain.XMLDesc(0)
        is_origin_secondary = 'filter-rewriter' in domain_xml
        for count in xrange(0, len(cmd.nics)):
            if cmd.nics[count].driverType == 'virtio':
                execute_qmp_command(cmd.vmInstanceUuid,
                                    '{"execute": "object-add", "arguments":{ "qom-type": "colo-compare", "id": "comp-%s",'
                                    ' "props": { "primary_in": "primary-in-c-%s", "secondary_in": "secondary-in-s-%s",'
                                    ' "outdev":"primary-out-c-%s", "iothread": "iothread%s", "vnet_hdr_support": true } } }'
                                    % (count, count, count, count, int(count) + 1))
                execute_qmp_command(cmd.vmInstanceUuid,
                                    '{"execute": "object-add", "arguments":{ "qom-type": "filter-mirror", "id": "fm-%s",'
                                    ' "props": { "netdev": "hostnet%s", "queue": "tx", "outdev": "zs-mirror-%s",'
                                    ' "vnet_hdr_support": true} } }'
                                    % (count, count, count))
                execute_qmp_command(cmd.vmInstanceUuid,
                                    '{"execute": "object-add", "arguments":{ "qom-type": "filter-redirector",'
                                    ' "id": "primary-out-redirect-%s", "props": { "netdev": "hostnet%s", "queue": "rx",'
                                    ' "indev": "primary-out-s-%s", "vnet_hdr_support": true}}}' % (count, count, count))
                execute_qmp_command(cmd.vmInstanceUuid,
                                    '{"execute": "object-add", "arguments":{ "qom-type": "filter-redirector", "id":'
                                    ' "primary-in-redirect-%s", "props": { "netdev": "hostnet%s", "queue": "rx",'
                                    ' "outdev": "primary-in-s-%s", "vnet_hdr_support": true}}}' % (count, count, count))
            else:
                execute_qmp_command(cmd.vmInstanceUuid,
                                    '{"execute": "object-add", "arguments":{ "qom-type": "colo-compare", "id": "comp-%s",'
                                    ' "props": { "primary_in": "primary-in-c-%s", "secondary_in": "secondary-in-s-%s",'
                                    ' "outdev":"primary-out-c-%s", "iothread": "iothread%s"} } }'
                                    % (count, count, count, count, int(count) + 1))
                execute_qmp_command(cmd.vmInstanceUuid,
                                    '{"execute": "object-add", "arguments":{ "qom-type": "filter-mirror", "id": "fm-%s",'
                                    ' "props": { "netdev": "hostnet%s", "queue": "tx", "outdev": "zs-mirror-%s"} } }'
                                    % (count, count, count))
                execute_qmp_command(cmd.vmInstanceUuid,
                                    '{"execute": "object-add", "arguments":{ "qom-type": "filter-redirector",'
                                    ' "id": "primary-out-redirect-%s", "props": { "netdev": "hostnet%s", "queue": "rx",'
                                    ' "indev": "primary-out-s-%s"}}}' % (count, count, count))
                execute_qmp_command(cmd.vmInstanceUuid,
                                    '{"execute": "object-add", "arguments":{ "qom-type": "filter-redirector", "id":'
                                    ' "primary-in-redirect-%s", "props": { "netdev": "hostnet%s", "queue": "rx",'
                                    ' "outdev": "primary-in-s-%s"}}}' % (count, count, count))

            count += 1

        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "migrate-set-capabilities","arguments":'
                                                '{"capabilities":[ {"capability": "x-colo", "state":true}]}}')

        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "migrate-set-parameters", "arguments":'
                                                '{ "max-bandwidth": 3355443200 }}')

        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "migrate", "arguments": {"uri": "tcp:%s:%s"}}'
                                                % (cmd.secondaryVmHostIp, cmd.blockReplicationPort))

        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "migrate-set-parameters",'
                                                ' "arguments": {"x-checkpoint-delay": %s}}'
                                                % cmd.checkpointDelay)

        def colo_qemu_object_cleanup():
            for i in xrange(cmd.nicNumber):
                execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                        '"arguments":{"id":"fm-%s"}}' % i)
                execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                        '"arguments":{"id":"primary-out-redirect-%s"}}' % i)
                execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                        '"arguments":{"id":"primary-in-redirect-%s"}}' % i)
                execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                        '"arguments":{"id":"comp-%s"}}' % i)

        # wait primary vm migrate job finished
        failure = 0
        while True:
            migrate_info, err = execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "query-migrate"}')
            if err:
                rsp.success = False
                rsp.error = "Failed to query migrate info, because %s" % err
                colo_qemu_object_cleanup()
                break

            if migrate_info['status'] == 'colo':
                logger.debug("migrate finished")
                break
            elif migrate_info['status'] == 'active':
                ram_info = migrate_info['ram']
                logger.debug("current migrate %s/%s, percentage %s"
                 % (ram_info['total'], ram_info['remaining'], 100 * (float(ram_info['remaining'] / float(ram_info['total'])))))
            elif migrate_info['status'] == 'failed':
                rsp.success = False
                rsp.error = "could not finish colo migration."
                try:
                    vm = get_vm_by_uuid_no_retry(cmd.vmInstanceUuid, False)
                    if vm:
                        vm.resume()
                        logger.debug('successfully, resume vm [uuid:%s]' % cmd.uuid)
                except kvmagent.KvmError as e:
                    logger.warn(linux.get_exception_stacktrace())
                break
            else:
                # those status are not handled but vm should not stuck in
                # MIGRATION_STATUS_POSTCOPY_ACTIVE:
                # MIGRATION_STATUS_POSTCOPY_PAUSED:
                # MIGRATION_STATUS_POSTCOPY_RECOVER:
                # MIGRATION_STATUS_SETUP:
                # MIGRATION_STATUS_PRE_SWITCHOVER:
                # MIGRATION_STATUS_DEVICE:
                if failure < 2:
                    failure += 1
                else:
                    rsp.success = False
                    rsp.error = "unknown migrate status: %s" % migrate_info['status']
                    # cancel migrate if vm stuck in unexpected status
                    execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "migrate_cancel"}')
                    break

            time.sleep(2)

        if not rsp.success:
            colo_qemu_object_cleanup()
            colo_qemu_replication_cleanup()

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def config_secondary_vm(self, req):
        rsp = kvmagent.AgentResponse()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "qmp_capabilities"}')
        execute_qmp_command(cmd.vmInstanceUuid, '{"execute":"nbd-server-start", "arguments":{"addr":{"type":"inet",'
                                                ' "data":{"host":"%s", "port":"%s"}}}}'
                            % (cmd.primaryVmHostIp, cmd.nbdServerPort))
        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "nbd-server-add",'
                                                ' "arguments": {"device": "parent0", "writable": true }}')
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def config_primary_vm(self, req):
        rsp = GetVmFirstBootDeviceRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "qmp_capabilities"}')

        ft.cleanup_vm_before_setup_colo_primary_vm(cmd.vmInstanceUuid)
        char_devices, err = execute_qmp_command(cmd.vmInstanceUuid, '{"execute":"query-chardev"}')
        if err:
            rsp.success = False
            rsp.error = "Failed to check qemu config, report error"
            return jsonobject.dumps(rsp)

        vm = get_vm_by_uuid(cmd.vmInstanceUuid)

        domain_xml = vm.domain.XMLDesc(0)

        is_origin_secondary = 'filter-rewriter' in domain_xml

        mirror_device_nums = [int(dev['label'][-1]) for dev in char_devices if dev['label'].startswith('zs-mirror')]
        logger.debug("get mirror char device of vm[uuid:%s] devices: %s" % (cmd.vmInstanceUuid, mirror_device_nums))
        if len(mirror_device_nums) == len(cmd.configs):
            logger.debug("config and devices matched, just return success")
            return jsonobject.dumps(rsp)
        elif len(mirror_device_nums) > len(cmd.configs):
            logger.debug("vm over config, please check what happened")
            return jsonobject.dumps(rsp)

        count = len(mirror_device_nums)
        for config in cmd.configs[len(mirror_device_nums):]:
            if not linux.is_port_available(config.mirrorPort):
                raise Exception("failed to config primary vm, because mirrorPort port %d is occupied" % config.mirrorPort)

            if not linux.is_port_available(config.primaryInPort):
                raise Exception("failed to config primary vm, because primaryInPort port %d is occupied" % config.primaryInPort)

            if not linux.is_port_available(config.secondaryInPort):
                raise Exception("failed to config primary vm, because secondaryInPort port %d is occupied" % config.secondaryInPort)

            if not linux.is_port_available(config.primaryOutPort):
                raise Exception("failed to config primary vm, because mirrorPort port %d is occupied" % config.primaryOutPort)

            execute_qmp_command(cmd.vmInstanceUuid,
                                '{"execute": "chardev-add", "arguments":{ "id": "zs-mirror-%s", "backend":'
                                ' {"type": "socket", "data": {"addr": { "type": "inet", "data":'
                                ' { "host": "%s", "port": "%s" } }, "server": true}}}}'
                                % (count, cmd.hostIp, config.mirrorPort))
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "chardev-add", "arguments":{ "id": "primary-in-s-%s",'
                                                    ' "backend": {"type": "socket", "data": {"addr": { "type":'
                                                    ' "inet", "data": { "host": "%s", "port": "%s" } },'
                                                    ' "server": true } } } }' % (count, cmd.hostIp, config.primaryInPort))
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "chardev-add", "arguments":{'
                                                    ' "id": "secondary-in-s-%s","backend": {"type":'
                                                    ' "socket", "data": {"addr": {"type":'
                                                    ' "inet", "data": { "host": "%s", "port": "%s" } },'
                                                    ' "server": true } } } }' % (count, cmd.hostIp, config.secondaryInPort))
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "chardev-add", "arguments":{ "id": "primary-in-c-%s",'
                                                    ' "backend": {"type": "socket", "data": {"addr": { "type":'
                                                    ' "inet", "data": { "host": "%s", "port": "%s" } },'
                                                    ' "server": false, "reconnect": 1 } } } }' % (count, cmd.hostIp, config.primaryInPort))
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "chardev-add", "arguments":{ "id": "primary-out-s-%s",'
                                                    ' "backend": {"type": "socket", "data": {"addr": { "type":'
                                                    ' "inet", "data": { "host": "%s", "port": "%s" } },'
                                                    ' "server": true } } } }' % (count, cmd.hostIp, config.primaryOutPort))
            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "chardev-add", "arguments":{ "id": "primary-out-c-%s",'
                                                    ' "backend": {"type": "socket", "data": {"addr": { "type":'
                                                    ' "inet", "data": { "host": "%s", "port": "%s" } },'
                                                    ' "server": false, "reconnect": 1 } } } }' % (count, cmd.hostIp, config.primaryOutPort))
            count += 1
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def get_vm_first_boot_device(self, req):
        rsp = GetVmFirstBootDeviceRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        vm_uuid = cmd.uuid
        vm = get_vm_by_uuid_no_retry(vm_uuid, False)
        boot_dev = find_domain_first_boot_device(vm.domain.XMLDesc(0))
        rsp.firstBootDevice = boot_dev
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def get_vm_device_address(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        vm_uuid = cmd.uuid
        rsp = GetVmDeviceAddressRsp()
        vm = get_vm_by_uuid_no_retry(vm_uuid, False)

        for resource_type in cmd.deviceTOs.__dict__.keys():
            tos = getattr(cmd.deviceTOs, resource_type)
            if resource_type == 'VolumeVO':
                addresses = VmPlugin._find_volume_device_address(vm, tos)
            else:
                addresses = []
            rsp.addresses[resource_type] = addresses

        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def get_virtualizer_info(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVirtualizerInfoRsp()

        rsp.hostInfo.uuid = self.config.get(kvmagent.HOST_UUID)
        rsp.hostInfo.virtualizer = "qemu-kvm"
        rsp.hostInfo.version = qemu.get_version_from_exe_file(qemu.get_path())

        for uuid in cmd.vmUuids:
            vm_info = VirtualizerInfoTO()
            self.collect_vm_virtualizer_info(uuid, vm_info)
            rsp.vmInfoList.append(vm_info)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def collect_vm_virtualizer_info(self, vm_uuid, vm_info):
        vm_info.uuid = vm_uuid
        vm_info.virtualizer = "qemu-kvm"
        vm_info.version = qemu.get_running_version(vm_uuid)

    @kvmagent.replyerror
    def set_emulator_pinning(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        cmd_base = "virsh emulatorpin %s " % (cmd.uuid)
        if (cmd.emulatorPinning == "-1") or (cmd.emulatorPinning == "") or (cmd.emulatorPinning is None):
            shell.call('%s %s' % ("cat /sys/devices/system/cpu/online|xargs", cmd_base))
        else:
            shell.call('%s %s' % (cmd_base, cmd.emulatorPinning))
        return jsonobject.dumps(rsp)

    def sync_vm_clock_now(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        vm = get_vm_by_uuid_no_retry(cmd.vmUuid, True)
        if vm.state != Vm.VM_STATE_RUNNING:
            rsp.success = False
            rsp.error = 'vm[uuid:%s, name:%s] is not in running state' % (cmd.vmUuid, vm.get_name())
            return jsonobject.dumps(rsp)

        if not is_qga_connected(vm.domain):
            rsp.success = False
            rsp.error = 'vm[uuid:%s, name:%s] qga channel is not connected' % (cmd.vmUuid, vm.get_name())
            return jsonobject.dumps(rsp)

        vm._wait_until_qemuga_ready(3000, cmd.vmUuid)
        script = '''virsh qemu-agent-command %s --cmd "{\\"execute\\":\\"guest-set-time\\",\\"arguments\\":{\\"time\\":`date +%%s%%N`}}"''' % cmd.vmUuid
        r, o, e = bash.bash_roe(script)
        if r != 0:
            rsp.success = False
            rsp.error = "failed to sync time for vm[uuid:%s]: %s, %s" % (cmd.vmUuid, o, e)
        return jsonobject.dumps(rsp)

    sync_clock_script = '''#!/bin/bash
    interval=$1
    if [[ ! -s /var/lib/zstack/kvm/sync-clock/interval-$interval-vms.txt ]]; then exit 0; fi
    running_vms=`virsh list | sed -n '3,$p' | awk '{printf $2 "\\n"}'`
    while IFS= read -r uuid
    do
        if [[ "$running_vms" == *"$uuid"* ]]; then
            virsh qemu-agent-command $uuid --cmd "{\\"execute\\":\\"guest-set-time\\",\\"arguments\\":{\\"time\\":`date +%s%N`}}" &> /dev/null
            if [ $? -ne 0 ]; then
                echo "$(date) failed to sync clock for vm: $uuid" >> "/var/log/zstack/sync-clock/interval-$interval.log"
            fi
        fi
    done < /var/lib/zstack/kvm/sync-clock/interval-$interval-vms.txt
    '''

    sync_clock_cron_exp_map = {
        60 : '*/1 * * * *',
        120 : '*/2 * * * *',
        180 : '*/3 * * * *',
        240 : '*/4 * * * *',
        300 : '*/5 * * * *',
        360 : '*/6 * * * *',
        600 : '*/10 * * * *',
        720 : '*/12 * * * *',
        900 : '*/15 * * * *',
        1200 : '*/20 * * * *',
        1800 : '*/30 * * * *',
        3600 : '0 */1 * * *',
        7200 : '0 */2 * * *',
        10800 : '0 */3 * * *',
        14400 : '0 */4 * * *',
        21600 : '0 */6 * * *',
        28800 : '0 */8 * * *',
        43200 : '0 */12 * * *',
        86400 : '0 0 */1 * *'
    }

    @bash.in_bash
    @kvmagent.replyerror
    def set_sync_vm_clock_task(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        r, o, e = bash.bash_roe('systemctl start crond')
        if r != 0:
            rsp.success = False
            rsp.error = "failed to start crond service to preform sync clock task: %s %s" % (o, e)
            return jsonobject.dumps(rsp)

        script_directory = '/var/lib/zstack/kvm/sync-clock'
        script_path = os.path.join(script_directory, 'sync-clock.sh')
        log_directory = '/var/log/zstack/sync-clock/'

        if not os.path.exists(script_directory):
            os.mkdir(script_directory)
        if not os.path.exists(log_directory):
            os.mkdir(log_directory)
        if not os.path.exists(script_path):
            with open(script_path, "w") as fd:
                fd.write(self.sync_clock_script)
            os.chmod(script_path, 0o755)

        # key: interval in seconds,  value: vm_uuid list
        interval_uuid_map = {}
        for vm_uuid in cmd.intervalMap.__dict__.keys():
            interval = cmd.intervalMap[vm_uuid]
            # check interval
            if not self.sync_clock_cron_exp_map.has_key(interval):
                rsp.success = False
                rsp.error = "failed to start sync vm clock task: unexpect interval %d" % interval
                return jsonobject.dumps(rsp)
            if interval_uuid_map.has_key(interval):
                interval_uuid_map[interval].append(vm_uuid)
            else:
                interval_uuid_map[interval] = [vm_uuid]

        # string list
        cron_scripts = []
        r, o, _ = bash.bash_roe('/usr/bin/crontab -l')
        if r == 0 and not o.startswith('\x00'): # crontab script is not empty
            for line in o.split('\n'):
                if line.strip() == "" or line.find("bash %s" % script_path) >= 0:
                    continue
                cron_scripts.append(line.strip())

        for interval in interval_uuid_map:
            vm_uuids = interval_uuid_map[interval]
            sync_vm_file_path = os.path.join(script_directory, 'interval-%d-vms.txt' % interval)
            with open(sync_vm_file_path, "w") as fd:
                fd.write('\n'.join(vm_uuids))
                fd.write('\n')
            os.chmod(sync_vm_file_path, 0o666)
            # '*/1 * * * * bash $script_path 60'
            cron_scripts.append('%s bash %s %d' % (self.sync_clock_cron_exp_map[interval], script_path, interval))

        tmp_path = tempfile.mktemp()
        with open(tmp_path, "w") as fd:
            fd.write('\n'.join(cron_scripts))
            fd.write('\n')

        r, o, e = bash.bash_roe('/usr/bin/crontab %s' % tmp_path)
        os.remove(tmp_path)
        if r != 0:
            rsp.success = False
            rsp.error = "failed to write crond script to preform sync clock task: %s %s" % (o, e)
        return jsonobject.dumps(rsp)

    @staticmethod
    def _find_volume_device_address(vm, volumes):
        #  type:(Vm, list[jsonobject.JsonObject]) -> list[VmDeviceAddress]
        addresses = []
        o = simplejson.loads(shell.call('virsh qemu-monitor-command %s --cmd \'{"execute":"query-pci"}\'' % vm.uuid))

        # only PCI buses up to 0 are available
        devices = o['return'][0]['devices']
        for vol in volumes:
            disk, _ = vm._get_target_disk(vol)
            if hasattr(disk, 'wwn'):
                addresses.append(VmDeviceAddress(vol.volumeUuid, 'disk', 'wwn', disk.wwn.text_))
                continue
            elif disk.address.type_ == 'pci':
                device = VmPlugin._find_pci_device(devices, disk.alias.name_)
                if device:
                    addresses.append(VmDeviceAddress(vol.volumeUuid, 'disk', 'pci', pci.fmt_pci_address(device)))
                    continue

            addresses.append(VmDeviceAddress(vol.volumeUuid, 'disk', disk.target.bus_, 'unknown'))
        return addresses

    @staticmethod
    def _find_pci_device(devices, qdev_id):
        for device in devices:
            if device['qdev_id'] == qdev_id:
                return device
            elif 'pci_bridge' in device:
                target = VmPlugin._find_pci_device(device['pci_bridge']['devices'], qdev_id)
                if target:
                    return target

        return None

    @kvmagent.replyerror
    def detach_virtio_driver(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        vm_uuid = cmd.vmInstanceUuid
        driver_format = cmd.driverFormat

        if driver_format == 'VFD':
            self.eject_floppy(vm_uuid, [SYSTEM_VIRTIO_DRIVER_PATHS['VFD_X86'], SYSTEM_VIRTIO_DRIVER_PATHS['VFD_AMD64']])
        else:
            rsp.error = "invalid virtio driver format: %s" % driver_format
            rsp.success = False

        return jsonobject.dumps(rsp)

    def eject_floppy(self, vm_uuid, file_path_list):
        """ Eject the floppy media and leave an empty floppy disk slot.
        :param file_path_list: list[str], exmaple of file_path_list::
            ['/var/lib/zstack/virtio-drivers/virtio-win_x86.vfd', '/var/lib/zstack/virtio-drivers/virtio-win_amd64.vfd']
        """
        @linux.retry(times=3, sleep_time=1)
        def eject_floppy_with_file_path(vm, file_path):
            (_, device_id) = vm._get_target_disk_by_path(file_path, False)
            if device_id is None:
                return

            floppy_without_source_xml = """
            <disk type='file' device='floppy'>
                <driver name='qemu' type='raw'/>
                <source/>
                <target dev='%s' bus='fdc'/>
                <readonly/>
            </disk>
            """ % (device_id)

            try:
                vm.domain.updateDeviceFlags(floppy_without_source_xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
            except Exception as e:
                logger.info("failed to eject floppy device: %s" % str(e))
            if vm._check_target_disk_existing_by_path(file_path):
                raise RetryException("current vm %s can not detach virtio floppy disk %s" % (vm.uuid, file_path))

        vm = get_vm_by_uuid_no_retry(vm_uuid)
        for file_path in file_path_list:
            eject_floppy_with_file_path(vm, file_path)

    def set_domain_network_device(self, vm_uuid, device_xml, operate_type='attach'):
        def check_nic_is_attached(expect_result=True):
            vm = get_vm_by_uuid(vm_uuid)
            tree = etree.fromstring(device_xml)
            for iface in vm.domain_xmlobject.devices.get_child_node_as_list('interface'):
                if iface.mac.address_ == tree.find('mac').attrib['address'] and iface.type_ == tree.attrib['type']:
                    if expect_result:
                        return True
                    else:
                        return False

            if expect_result:
                return False
            else:
                return True

        try:
            if not vm_uuid or not device_xml:
                raise Exception('vm_uuid or device_xml is None')
            if operate_type not in ['attach', 'detach']:
                raise Exception('operate_type: %s is invalid' % operate_type)
            logger.debug('operate_type: %s, device_xml: %s' % (operate_type, device_xml))
            vm_domain = get_vm_by_uuid(vm_uuid)
            if operate_type == 'attach':
                if vm_domain.state in [Vm.VM_STATE_RUNNING, Vm.VM_STATE_PAUSED]:
                    vm_domain.domain.attachDeviceFlags(device_xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
                else:
                    vm_domain.domain.attachDeviceFlags(device_xml)
                if not linux.wait_callback_success(check_nic_is_attached, callback_data=True, timeout=60, interval=5):
                    raise Exception('nic device is still detached after 60s. please check the device xml: %s' % device_xml)
            else:
                if vm_domain.state in [Vm.VM_STATE_RUNNING, Vm.VM_STATE_PAUSED]:
                    vm_domain.domain.detachDeviceFlags(device_xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
                else:
                    vm_domain.domain.detachDeviceFlags(device_xml)
                if not linux.wait_callback_success(check_nic_is_attached, callback_data=False, timeout=60, interval=5):
                    raise Exception('nic device is still attached after 60s. please check the device xml: %s' % device_xml)
        except Exception as e:
                raise Exception('failed to %s device, error: %s' % (operate_type, str(e)))

    def set_domain_iflink_state(self, vm_uuid, nic_name, link_state):
        if not vm_uuid or not nic_name:
            raise Exception('vm_uuid or nic_name is None')
        if link_state not in ['up', 'down']:
            raise Exception('link_state is invalid')
        o = shell.call('virsh domif-setlink %s %s %s' % (vm_uuid, nic_name, link_state))
        if "successfully" not in o:
            raise Exception('update nic device state failed')

    @kvmagent.replyerror
    def set_vf_nic_state(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ChangeVfNicHaStateRsp()

        DISABLED = 'Disabled'
        ENABLED = 'Enabled'
        DISCONNECTING = 'Disconnecting'
        RECONNECTING = 'Reconnecting'

        def _check_nic_is_attached(vm, nic, interface_type=None):
            if interface_type not in ['bridge', 'hostdev']:
                raise Exception('invalid interface type: %s' % interface_type)
            for iface in vm.domain_xmlobject.devices.get_child_node_as_list('interface'):
                if iface.mac.address_ != nic.mac:
                    continue
                if iface.type_ == interface_type:
                    if iface.hasattr('alias'):
                        iface.del_node('alias')
                    return iface.dump()

            return None

        def _build_xml_from_vf(vm, nic, nic_type=None):
            if nic_type not in ['VNIC', 'VF']:
                raise Exception('invalid nic type: %s' % nic_type)
            if nic_type == 'VNIC':
                interface = etree.Element('interface', attrib={'type': 'bridge'})
                e(interface, 'mac', None, attrib={'address': nic.mac})
                e(interface, 'mtu', None, attrib={'size': '%d' % nic.mtu})
                e(interface, 'source', None, attrib={'bridge': nic.bridgeName})
                e(interface, 'target', None, attrib={'dev': '%s.1' % nic.nicInternalName})
                e(interface, 'link', None, attrib={'state': 'down'})
                e(interface, 'model', None, attrib={'type': 'virtio'})
                queue_num = nic.vHostAddOn.queueNum if nic.vHostAddOn.queueNum else 1
                rx_buffer_size = nic.vHostAddOn.rxBufferSize if nic.vHostAddOn.rxBufferSize else 1024
                tx_buffer_size = nic.vHostAddOn.txBufferSize if nic.vHostAddOn.txBufferSize else 1024
                e(interface, 'driver ', None, attrib={'name': 'vhost',
                                'txmode': 'iothread',
                                'ioeventfd': 'on',
                                'event_idx': 'off',
                                'queues': str(queue_num),
                                'rx_queue_size': str(rx_buffer_size),
                                'tx_queue_size': str(tx_buffer_size)})
                return etree.tostring(interface)
            else:
                interface = Vm._build_interface_xml(nic, action='Update')
                return etree.tostring(interface)

        def _change_vf_ha_state_enable(vm, nic):
            # 1. attach temporary vnic to vm, and set link state to down
            vnic_xml = _check_nic_is_attached(vm, nic, interface_type='bridge')
            if vnic_xml is None:
                vnic_xml = _build_xml_from_vf(vm, nic, nic_type='VNIC')
                self.set_domain_network_device(vm.uuid, vnic_xml, operate_type='attach')
            else:
                self.set_domain_iflink_state(vm.uuid, '%s.1' % nic.nicInternalName, 'down')

            # 2. just check vf is attached to vm, if not, attach it
            vf_xml = _check_nic_is_attached(vm, nic, interface_type='hostdev')
            if vf_xml is None:
                vf_xml = _build_xml_from_vf(vm, nic, nic_type='VF')
                self.set_domain_network_device(vm.uuid, vf_xml, operate_type='attach')

        def _change_vf_ha_state_disconnect(vm, nic):
            # 1. set temporary vnic link state to up
            vnic_xml = _check_nic_is_attached(vm, nic, interface_type='bridge')
            if vnic_xml is None:
                vnic_xml = _build_xml_from_vf(vm, nic, nic_type='VNIC')
                self.set_domain_network_device(vm.uuid, vnic_xml, operate_type='attach')
            self.set_domain_iflink_state(vm.uuid, '%s.1' % nic.nicInternalName, 'up')

            # 2. detach vf from vm
            vf_xml = _check_nic_is_attached(vm, nic, interface_type='hostdev')
            if vf_xml is not None:
                self.set_domain_network_device(vm.uuid, vf_xml, operate_type='detach')

        def _change_vf_ha_state_reconnect(vm, nic):
            # 1. attach new vf to vm
            vf_xml = _check_nic_is_attached(vm, nic, interface_type='hostdev')
            if vf_xml is None:
                vf_xml = _build_xml_from_vf(vm, nic, nic_type='VF')
                self.set_domain_network_device(vm.uuid, vf_xml, operate_type='attach')

            # 2. detach temporary vnic from vm
            vnic_xml = _check_nic_is_attached(vm, nic, interface_type='bridge')
            if vnic_xml is not None:
                self.set_domain_network_device(vm.uuid, vnic_xml, operate_type='detach')

        def _change_vf_ha_state_disable(vm, nic):
            nic_xml = _check_nic_is_attached(vm, nic, interface_type='bridge')
            if nic_xml is not None:
                self.set_domain_network_device(vm.uuid, nic_xml, operate_type='detach')

        def _check_cmd(cmd):
            if cmd.haState not in [ENABLED, DISCONNECTING, RECONNECTING, DISABLED]:
                raise Exception('invalid vf nic ha state: %s' % cmd.haState)

            vm = get_vm_by_uuid(cmd.vmUuid)
            if not vm or vm.state != Vm.VM_STATE_RUNNING:
                raise Exception('vm[uuid:%s] is not running' % cmd.vmUuid)

            return vm

        try:
            vm = _check_cmd(cmd)
            if cmd.haState == ENABLED:
                _change_vf_ha_state_enable(vm, cmd.nic)
            elif cmd.haState == DISCONNECTING:
                _change_vf_ha_state_disconnect(vm, cmd.nic)
            elif cmd.haState == RECONNECTING:
                _change_vf_ha_state_reconnect(vm, cmd.nic)
            elif cmd.haState == DISABLED:
                _change_vf_ha_state_disable(vm, cmd.nic)
            else:
                raise Exception('not support vf nic ha state: %s' % cmd.haState)

            logger.debug('successfully change vf nic ha state to %s' % cmd.haState)
            rsp.success = True
        except Exception as err:
            logger.warn('failed to change vf nic ha state, error: %s' % str(err))
            rsp.success = False
            rsp.error = str(err)
        finally:
            return jsonobject.dumps(rsp)

    def start(self):
        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(self.KVM_START_VM_PATH, self.start_vm, cmd=StartVmCmd())
        http_server.register_async_uri(self.KVM_STOP_VM_PATH, self.stop_vm)
        http_server.register_async_uri(self.KVM_PAUSE_VM_PATH, self.pause_vm)
        http_server.register_async_uri(self.KVM_RESUME_VM_PATH, self.resume_vm)
        http_server.register_async_uri(self.KVM_REBOOT_VM_PATH, self.reboot_vm)
        http_server.register_async_uri(self.KVM_DESTROY_VM_PATH, self.destroy_vm)
        http_server.register_async_uri(self.KVM_GET_CONSOLE_PORT_PATH, self.get_console_port)
        http_server.register_async_uri(self.KVM_ONLINE_CHANGE_CPUMEM_PATH, self.online_change_cpumem)
        http_server.register_async_uri(self.KVM_ONLINE_INCREASE_CPU_PATH, self.online_increase_cpu)
        http_server.register_async_uri(self.KVM_ONLINE_INCREASE_MEMORY_PATH, self.online_increase_mem)
        http_server.register_async_uri(self.KVM_VM_SYNC_PATH, self.vm_sync)
        http_server.register_async_uri(self.KVM_VOLUME_SYNC_PATH, self.volume_sync)
        http_server.register_async_uri(self.KVM_ATTACH_VOLUME, self.attach_data_volume)
        http_server.register_async_uri(self.KVM_DETACH_VOLUME, self.detach_data_volume)
        http_server.register_async_uri(self.KVM_ATTACH_ISO_PATH, self.attach_iso)
        http_server.register_async_uri(self.KVM_DETACH_ISO_PATH, self.detach_iso)
        http_server.register_async_uri(self.KVM_MIGRATE_VM_PATH, self.migrate_vm)
        http_server.register_async_uri(self.KVM_GET_CPU_XML_PATH, self.get_cpu_xml)
        http_server.register_async_uri(self.KVM_COMPARE_CPU_FUNCTION_PATH, self.compare_cpu_function)
        http_server.register_async_uri(self.KVM_BLOCK_LIVE_MIGRATION_PATH, self.block_migrate)
        http_server.register_async_uri(self.KVM_VM_CHECK_VOLUME_PATH, self.check_volume)
        http_server.register_async_uri(self.KVM_VM_RECOVER_VOLUMES_PATH, self.recover_volumes)
        http_server.register_sync_uri(self.KVM_VM_CHECK_RECOVER_PATH, self.check_recover)
        http_server.register_async_uri(self.KVM_TAKE_VOLUME_SNAPSHOT_PATH, self.take_volume_snapshot)
        http_server.register_async_uri(self.KVM_CHECK_VOLUME_SNAPSHOT_PATH, self.check_volume_snapshot)
        http_server.register_async_uri(self.KVM_TAKE_VOLUME_BACKUP_PATH, self.take_volume_backup, cmd=TakeVolumeBackupCommand())
        http_server.register_async_uri(self.KVM_TAKE_VOLUME_MIRROR_PATH, self.take_volume_mirror)
        http_server.register_async_uri(self.KVM_GET_VOLUME_MIRROR_MODE_PATH, self.get_volume_mirror_mode)
        http_server.register_async_uri(self.KVM_CANCEL_VOLUME_MIRROR_PATH, self.cancel_volume_mirror)
        http_server.register_async_uri(self.KVM_QUERY_VOLUME_MIRROR_PATH, self.query_volume_mirror)
        http_server.register_async_uri(self.KVM_QUERY_MIRROR_LATENCY_BOUNDARY_PATH, self.query_vm_mirror_latencies_boundary)
        http_server.register_async_uri(self.KVM_QUERY_BLOCKJOB_STATUS, self.query_block_job_status)
        http_server.register_async_uri(self.KVM_TAKE_VOLUMES_SNAPSHOT_PATH, self.take_volumes_snapshots)
        http_server.register_async_uri(self.KVM_TAKE_VOLUMES_BACKUP_PATH, self.take_volumes_backups, cmd=TakeVolumesBackupsCommand())
        http_server.register_async_uri(self.KVM_CANCEL_VOLUME_BACKUP_JOBS_PATH, self.cancel_backup_jobs)
        http_server.register_async_uri(self.KVM_CANCEL_VOLUME_BACKUP_JOB_PATH, self.cancel_backup_job)
        http_server.register_async_uri(self.KVM_BLOCK_STREAM_VOLUME_PATH, self.block_stream)
        http_server.register_async_uri(self.KVM_BLOCK_COMMIT_VOLUME_PATH, self.block_commit)
        http_server.register_async_uri(self.KVM_MERGE_SNAPSHOT_PATH, self.merge_snapshot_to_volume)
        http_server.register_async_uri(self.KVM_LOGOUT_ISCSI_TARGET_PATH, self.logout_iscsi_target, cmd=LoginIscsiTargetCmd())
        http_server.register_async_uri(self.KVM_LOGIN_ISCSI_TARGET_PATH, self.login_iscsi_target)
        http_server.register_async_uri(self.KVM_ATTACH_NIC_PATH, self.attach_nic)
        http_server.register_async_uri(self.KVM_DETACH_NIC_PATH, self.detach_nic)
        http_server.register_async_uri(self.KVM_CHANGE_NIC_STATE_PATH, self.change_nic_state)
        http_server.register_async_uri(self.KVM_UPDATE_NIC_PATH, self.update_nic)
        http_server.register_async_uri(self.KVM_CREATE_SECRET, self.create_ceph_secret_key)
        http_server.register_async_uri(self.KVM_VM_CHECK_STATE, self.check_vm_state)
        http_server.register_async_uri(self.KVM_VM_CHANGE_PASSWORD_PATH, self.change_vm_password, cmd=ChangeVmPasswordCmd())
        http_server.register_async_uri(self.KVM_SET_VOLUME_BANDWIDTH, self.set_volume_bandwidth)
        http_server.register_async_uri(self.KVM_DELETE_VOLUME_BANDWIDTH, self.delete_volume_bandwidth)
        http_server.register_async_uri(self.KVM_GET_VOLUME_BANDWIDTH, self.get_volume_bandwidth)
        http_server.register_async_uri(self.KVM_SET_NIC_QOS, self.set_nic_qos)
        http_server.register_async_uri(self.KVM_GET_NIC_QOS, self.get_nic_qos)
        http_server.register_async_uri(self.KVM_HARDEN_CONSOLE_PATH, self.harden_console)
        http_server.register_async_uri(self.KVM_DELETE_CONSOLE_FIREWALL_PATH, self.delete_console_firewall_rule)
        http_server.register_async_uri(self.HOT_PLUG_PCI_DEVICE, self.hot_plug_pci_device)
        http_server.register_async_uri(self.HOT_UNPLUG_PCI_DEVICE, self.hot_unplug_pci_device)
        http_server.register_async_uri(self.ATTACH_PCI_DEVICE_TO_HOST, self.attach_pci_device_to_host)
        http_server.register_async_uri(self.DETACH_PCI_DEVICE_FROM_HOST, self.detach_pci_device_from_host)
        http_server.register_async_uri(self.HOT_PLUG_MDEV_DEVICE, self.hot_plug_mdev_device)
        http_server.register_async_uri(self.HOT_UNPLUG_MDEV_DEVICE, self.hot_unplug_mdev_device)
        http_server.register_async_uri(self.KVM_ATTACH_USB_DEVICE_PATH, self.kvm_attach_usb_device)
        http_server.register_async_uri(self.KVM_DETACH_USB_DEVICE_PATH, self.kvm_detach_usb_device)
        http_server.register_async_uri(self.RELOAD_USB_REDIRECT_PATH, self.reload_redirect_usb)
        http_server.register_async_uri(self.CHECK_MOUNT_DOMAIN_PATH, self.check_mount_domain)
        http_server.register_async_uri(self.KVM_RESIZE_VOLUME_PATH, self.kvm_resize_volume)
        http_server.register_async_uri(self.VM_PRIORITY_PATH, self.vm_priority)
        http_server.register_async_uri(self.UPLOAD_FILE_GUEST_TOOLS_FOR_VM_PATH, self.upload_vm_file)
        http_server.register_async_uri(self.EXEC_CMD_IN_VM_PATH, self.script_exec_on_vm)
        http_server.register_async_uri(self.ATTACH_GUEST_TOOLS_ISO_TO_VM_PATH, self.attach_guest_tools_iso_to_vm)
        http_server.register_async_uri(self.DETACH_GUEST_TOOLS_ISO_FROM_VM_PATH, self.detach_guest_tools_iso_from_vm)
        http_server.register_async_uri(self.GET_VM_GUEST_TOOLS_INFO_PATH, self.get_vm_guest_tools_info)
        http_server.register_async_uri(self.GET_VM_METRICS_ROUTING_STATUS_PATH, self.get_vm_metrics_routing_status)
        http_server.register_async_uri(self.KVM_GET_VM_FIRST_BOOT_DEVICE_PATH, self.get_vm_first_boot_device)
        http_server.register_async_uri(self.KVM_CONFIG_PRIMARY_VM_PATH, self.config_primary_vm)
        http_server.register_async_uri(self.KVM_CONFIG_SECONDARY_VM_PATH, self.config_secondary_vm)
        http_server.register_async_uri(self.KVM_START_COLO_SYNC_PATH, self.start_colo_sync)
        http_server.register_async_uri(self.KVM_REGISTER_PRIMARY_VM_HEARTBEAT, self.register_primary_vm_heartbeat)
        http_server.register_async_uri(self.CHECK_COLO_VM_STATE_PATH, self.check_colo_vm_state)
        http_server.register_async_uri(self.WAIT_COLO_VM_READY_PATH, self.wait_secondary_vm_ready)
        http_server.register_async_uri(self.ROLLBACK_QUORUM_CONFIG_PATH, self.rollback_quorum_config)
        http_server.register_async_uri(self.FAIL_COLO_PVM_PATH, self.fail_colo_pvm, cmd=FailColoPrimaryVmCmd())
        http_server.register_async_uri(self.GET_VM_DEVICE_ADDRESS_PATH, self.get_vm_device_address)
        http_server.register_async_uri(self.GET_VIRTUALIZER_INFO_PATH, self.get_virtualizer_info)
        http_server.register_async_uri(self.SET_EMULATOR_PINNING_PATH, self.set_emulator_pinning)
        http_server.register_async_uri(self.SYNC_VM_CLOCK_PATH, self.sync_vm_clock_now)
        http_server.register_async_uri(self.SET_SYNC_VM_CLOCK_TASK_PATH, self.set_sync_vm_clock_task)
        http_server.register_async_uri(self.KVM_SYNC_VM_DEVICEINFO_PATH, self.sync_vm_deviceinfo)
        http_server.register_async_uri(self.SET_VM_IOTHREADPIN_PATH, self.set_iothread_pin)
        http_server.register_async_uri(self.DEL_VM_IOTHREADPIN_PATH, self.del_iothread_pin)
        http_server.register_async_uri(self.GET_VM_IOTHREADPIN_PATH, self.get_iothread_pin)
        http_server.register_async_uri(self.SET_VM_SCSI_CONTROLLER, self.set_scsi_controller)
        http_server.register_async_uri(self.DEL_VM_SCSI_CONTROLLER, self.del_scsi_controller)
        http_server.register_async_uri(self.CLEAN_FIRMWARE_FLASH, self.clean_firmware_flash)
        http_server.register_async_uri(self.SSH_KEY_PAIR_ATTACH_TO_VM, self.attach_ssh_key_pair)
        http_server.register_async_uri(self.SSH_KEY_PAIR_DETACH_FROM_VM, self.detach_ssh_key_pair)
        http_server.register_async_uri(self.APPLY_MEMORY_BALLOON_PATH, self.apply_memory_balloon)
        http_server.register_async_uri(self.KVM_NOTIFY_TF_NIC_PATH, self.notify_tf_nic)
        http_server.register_async_uri(self.TAKE_VM_CONSOLE_SCREENSHOT_PATH, self.take_console_screenshot)
        http_server.register_async_uri(self.FSTRIM_VM_PATH, self.fstrim_vm)
        http_server.register_async_uri(self.DETACH_VIRTIO_DRIVER_PATH, self.detach_virtio_driver)
        http_server.register_async_uri(self.SET_VM_VF_NIC_STATE, self.set_vf_nic_state)

        self.clean_old_sshfs_mount_points()
        self.register_libvirt_event()
        self.register_qemu_log_cleaner()
        self.register_vm_console_logrotate_conf()

        self.enable_auto_extend = True
        self.auto_extend_size = 1073741824 * 2

        # the virtio-channel directory used by VR.
        # libvirt won't create this directory when migrating a VR,
        # we have to do this otherwise VR migration may fail
        linux.mkdir('/var/lib/zstack/kvm/agentSocket/')

        @thread.AsyncThread
        def wait_end_signal():
            while True:
                try:
                    self.queue_singleton.queue.get(True)

                    while bool(http.AsyncUirHandler.HANDLER_DICT):
                        time.sleep(0.1)

                    # the libvirt has been stopped or restarted
                    # to prevent fd leak caused by broken libvirt connection
                    # we have to ask mgmt server to reboot the agent
                    url = self.config.get(kvmagent.SEND_COMMAND_URL)
                    if not url:
                        logger.warn('cannot find SEND_COMMAND_URL, unable to ask the mgmt server to reconnect us')
                        os._exit(1)

                    host_uuid = self.config.get(kvmagent.HOST_UUID)
                    if not host_uuid:
                        logger.warn('cannot find HOST_UUID, unable to ask the mgmt server to reconnect us')
                        os._exit(1)

                    logger.warn("libvirt has been rebooted or stopped, ask the mgmt server to reconnt us")
                    cmd = ReconnectMeCmd()
                    cmd.hostUuid = host_uuid
                    cmd.reason = "libvirt rebooted or stopped"
                    http.json_dump_post(url, cmd, {'commandpath': '/kvm/reconnectme'})
                    os._exit(1)
                except:
                    content = traceback.format_exc()
                    logger.warn(content)
                finally:
                    os._exit(1)


        wait_end_signal()

        @thread.AsyncThread
        def monitor_libvirt():
            while True:
                pid = linux.get_libvirtd_pid()
                if not pid or not linux.process_exists(pid):
                    logger.warn(
                        "cannot find the libvirt process, assume it's dead, ask the mgmt server to reconnect us")
                    _stop_world()

                time.sleep(20)

        monitor_libvirt()

        @thread.AsyncThread
        def clean_stale_vm_vnc_port_chain():
            while True:
                logger.debug("do clean up stale vnc port iptable chains")
                cleanup_stale_vnc_iptable_chains()
                time.sleep(600)

        clean_stale_vm_vnc_port_chain()

        def monitor_vmcore_dump_path():
            while True:
                try:
                    vmcore_dump_path = VM_CORE_DUMP_DIR
                    if not os.path.exists(vmcore_dump_path):
                        os.makedirs(vmcore_dump_path)

                    dir_size = linux.get_filesystem_folder_size(vmcore_dump_path)
                    if dir_size > 2 * 4 * 1024 * 1024 * 1024:
                        logger.debug("vmcore dump path size is %s, clean up it" % dir_size)
                        linux.rm_dir_force(vmcore_dump_path)
                except:
                    content = traceback.format_exc()
                    logger.warn(content)
                finally:
                    time.sleep(600)



    def start_vm_heart_beat(self, cmd):
        def send_failover(vm_instance_uuid, host_uuid, primary_failure):
            url = self.config.get(kvmagent.SEND_COMMAND_URL)
            if not url:
                logger.warn('cannot find SEND_COMMAND_URL')
                return

            logger.warn("heartbeat of vm %s lost, failover" % vm_instance_uuid)
            fcmd = FailOverCmd()
            fcmd.vmInstanceUuid = vm_instance_uuid
            fcmd.reason = "network failure"
            fcmd.hostUuid = host_uuid
            fcmd.primaryVmFailure = primary_failure

            try:
                http.json_dump_post(url, fcmd, {'commandpath': '/kvm/reportfailover'})
            except Exception as e:
                logger.debug('failed to report fail')

        def test_heart_beat():
            logger.debug("vm [uuid:%s] heartbeat finished", cmd.vmInstanceUuid)
            with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.settimeout(0.5)
                try:
                    s.connect((cmd.targetHostIp, cmd.heartbeatPort))
                    logger.debug("successfully connect to address[%s:%s]" % (cmd.targetHostIp, cmd.heartbeatPort))
                except socket.error as ex:
                    logger.debug(
                        "lost heartbeat to %s:%s, because %s" % (cmd.targetHostIp, cmd.heartbeatPort, ex))

                    if cmd.coloPrimary:
                        vm = get_vm_by_uuid_no_retry(cmd.vmInstanceUuid, False)
                        if not vm:
                            raise Exception('vm[uuid:%s] not exists, failed' % cmd.vmInstanceUuid)

                        count = 0
                        for alias_name in vm._get_all_volume_alias_names(cmd.volumes):
                            execute_qmp_command(cmd.vmInstanceUuid,
                                                '{"execute": "x-blockdev-change", "arguments": {"parent":'
                                                ' "%s", "child": "children.1"}}' % alias_name)
                            execute_qmp_command(cmd.vmInstanceUuid,
                                                '{"execute": "human-monitor-command", "arguments":'
                                                '{"command-line": "drive_del replication%s" } }' % count)
                            count += 1

                        for i in xrange(cmd.redirectNum):
                            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                                    '"arguments":{"id":"fm-%s"}}' % i)
                            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                                    '"arguments":{"id":"primary-out-redirect-%s"}}' % i)
                            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                                    '"arguments":{"id":"primary-in-redirect-%s"}}' % i)
                            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                                    '"arguments":{"id":"comp-%s"}}' % i)
                        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "x-colo-lost-heartbeat"}')
                    else:
                        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "nbd-server-stop"}')
                        execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "x-colo-lost-heartbeat"}')
                        for i in xrange(cmd.redirectNum):
                            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                                    '"arguments":{"id":"fr-secondary-%s"}}' % i)
                            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "object-del",'
                                                                    '"arguments":{ "id": "fr-mirror-%s"}}' % i)
                            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "chardev-remove",'
                                                                    '"arguments":{"id":"red-secondary-%s"}}' % i)
                            execute_qmp_command(cmd.vmInstanceUuid, '{"execute": "chardev-remove",'
                                                                    '"arguments":{"id":"red-mirror-%s"}}' % i)

                    send_failover(cmd.vmInstanceUuid, cmd.hostUuid, not cmd.coloPrimary)
                    return True

                logger.debug("vm [uuid:%s] heartbeat finished", cmd.vmInstanceUuid)
                return False

        t = threading.currentThread()
        while getattr(t, "do_heart_beat", True):
            need_break = test_heart_beat()

            if need_break:
                break

            time.sleep(1)

        try:
            self.vm_heartbeat.pop(cmd.vmInstanceUuid)
        except KeyError:
            logger.debug("ignore error occurs when remove %s from heartbeat",
                         cmd.vmInstanceUuid)

    def _vm_lifecycle_event(self, conn, dom, event, detail, opaque):
        try:
            evstr = LibvirtEventManager.event_to_string(event)
            vm_uuid = dom.name()
            if evstr not in (LibvirtEventManager.EVENT_STARTED, LibvirtEventManager.EVENT_STOPPED):
                logger.debug("ignore event[%s] of the vm[uuid:%s]" % (evstr, vm_uuid))
                return
            if vm_uuid.startswith("guestfs-"):
                logger.debug("[vm_lifecycle]ignore the temp vm[%s] while using guestfish" % vm_uuid)
                return

            vm_op_judger = self._get_operation(vm_uuid)
            if vm_op_judger and evstr in vm_op_judger.ignore_libvirt_events():
                # this is an operation originated from ZStack itself
                logger.debug(
                    'ignore event[%s] for the vm[uuid:%s], this operation is from ZStack itself' % (evstr, vm_uuid))

                if vm_op_judger.remove_expected_event(evstr) == 0:
                    self._remove_operation(vm_uuid)
                    logger.debug(
                        'events happened of the vm[uuid:%s] meet the expectation, delete the operation judger' % vm_uuid)

                return

            # this is an operation outside zstack, report it
            url = self.config.get(kvmagent.SEND_COMMAND_URL)
            if not url:
                logger.warn('cannot find SEND_COMMAND_URL, unable to report abnormal operation[vm:%s, op:%s]' % (
                    vm_uuid, evstr))
                return

            host_uuid = self.config.get(kvmagent.HOST_UUID)
            if not host_uuid:
                logger.warn(
                    'cannot find HOST_UUID, unable to report abnormal operation[vm:%s, op:%s]' % (vm_uuid, evstr))
                return

            @thread.AsyncThread
            def report_to_management_node():
                cmd = ReportVmStateCmd()
                cmd.vmUuid = vm_uuid
                cmd.hostUuid = host_uuid
                if evstr == LibvirtEventManager.EVENT_STARTED:
                    cmd.vmState = Vm.VM_STATE_RUNNING
                elif evstr == LibvirtEventManager.EVENT_STOPPED:
                    cmd.vmState = Vm.VM_STATE_SHUTDOWN

                logger.debug(
                    'detected an abnormal vm operation[uuid:%s, op:%s], report it to %s' % (vm_uuid, evstr, url))
                http.json_dump_post(url, cmd, {'commandpath': '/kvm/reportvmstate'})

            report_to_management_node()
        except:
            content = traceback.format_exc()
            logger.warn(content)

    # WARNING: it contains quite a few hacks to avoid xmlobject#loads()
    def _vm_reboot_event(self, conn, dom, opaque):
        try:
            domain_xml = dom.XMLDesc(libvirt.VIR_DOMAIN_XML_MIGRATABLE)
            vm_uuid = dom.name()

            @thread.AsyncThread
            def report_to_management_node():
                cmd = ReportVmRebootEventCmd()
                cmd.vmUuid = vm_uuid
                syslog.syslog('report reboot event for vm ' + vm_uuid)
                http.json_dump_post(url, cmd, {'commandpath': '/kvm/reportvmreboot'})

            # make sure reboot event only report once
            op = self._get_operation(vm_uuid)
            if op is None or op.op != VmPlugin.VM_OP_REBOOT:
                url = self.config.get(kvmagent.SEND_COMMAND_URL)
                if not url:
                    logger.warn(
                        'cannot find SEND_COMMAND_URL, unable to report shutdown event of vm[uuid:%s]' % vm_uuid)
                    return

                report_to_management_node()

            self._record_operation(vm_uuid, VmPlugin.VM_OP_REBOOT)

            is_cdrom = self._check_boot_from_cdrom(domain_xml)
            if is_cdrom:
                logger.debug("the vm[uuid:%s]'s boot device is cdrom, for the policy[bootFromHardDisk], and it will boot from hdd" % (vm_uuid))
            else:
                return

            # use vm cache to avoid vmsync get empty vm state
            # because we known vm will be started after destroy
            put_vm_state_to_cache(vm_uuid, Vm.VM_STATE_RUNNING)
            try:
                dom.destroy()
            except:
                pass

            # cdrom
            xml = self.update_root_volume_boot_order(domain_xml)
            xml = re.sub(r"""\stray\s*=\s*'open'""", """ tray='closed'""", xml)
            domain = conn.defineXML(xml)
            domain.createWithFlags(0)
        except:
            content = traceback.format_exc()
            logger.warn(content)
        finally:
            remove_vm_state_from_cache(vm_uuid)

    # update the boot order of the root volume to 1, rely on the make_volumes() function
    def update_root_volume_boot_order(self, domain_xml):
        xml = minidom.parseString(domain_xml)
        disks = xml.getElementsByTagName('disk')
        boots = xml.getElementsByTagName("boot")
        for boot in boots:
            boot.parentNode.removeChild(boot);
        order = xml.createElement("boot")
        order.setAttribute("order", "1")
        disks[0].appendChild(order)
        xml = xml.toxml()
        return xml

    def _check_boot_from_cdrom(self, domain_xml):
        is_cdrom = False
        xml = minidom.parseString(domain_xml)
        disks = xml.getElementsByTagName('disk')
        for disk in disks:
            if disk.getAttribute("device") == "cdrom" and disk.getElementsByTagName("boot").length > 0 and \
                    disk.getElementsByTagName("boot")[0].getAttribute("order") == "1":
                is_cdrom = True
                break
        if not is_cdrom:
            os = xml.getElementsByTagName("os")[0]
            if os.getElementsByTagName("boot").length > 0 and os.getElementsByTagName("boot")[0].getAttribute(
                    "device") == "cdrom":
                is_cdrom = True
        return is_cdrom

    @bash.in_bash
    @misc.ignoreerror
    def _extend_sharedblock(self, conn, dom, event, detail, opaque):
        from shared_block_plugin import MAX_ACTUAL_SIZE_FACTOR
        logger.debug("got event from libvirt, %s %s %s %s" %
                     (dom.name(), LibvirtEventManager.event_to_string(event), detail, opaque))

        if not self.enable_auto_extend:
            return

        def check_lv(file, vm, device):
            logger.debug("sblk max actual size factor %s" % MAX_ACTUAL_SIZE_FACTOR)
            virtual_size, image_offest, _ = vm.domain.blockInfo(device)
            lv_size = int(lvm.get_lv_size(file))
            # image_offest = int(bash.bash_o("qemu-img check %s | grep 'Image end offset' | awk -F ': ' '{print $2}'" % file).strip())
            # virtual_size = int(linux.qcow2_virtualsize(file))
            return int(lv_size) < int(virtual_size) * MAX_ACTUAL_SIZE_FACTOR, image_offest, lv_size, virtual_size

        @bash.in_bash
        def extend_lv(event_str, path, vm, device):
            # type: (str, str, Vm, object) -> object
            r, image_offest, lv_size, virtual_size = check_lv(path, vm, device)
            logger.debug("lv %s image offest: %s, lv size: %s, virtual size: %s" %
                         (path, image_offest, lv_size, virtual_size))
            if not r:
                logger.debug("lv %s is larager than virtual size * %s, skip extend for event %s" % (path, MAX_ACTUAL_SIZE_FACTOR, event_str))
                return

            extend_size = lv_size + self.auto_extend_size
            try:
                lvm.extend_lv(path, extend_size)
            except Exception as e:
                logger.warn("extend lv[%s] to size[%s] failed" % (path, extend_size))
                if "incompatible mode" not in e.message.lower():
                    return
                try:
                    with lvm.OperateLv(path, shared=False, delete_when_exception=False):
                        lvm.extend_lv(path, extend_size)
                except Exception as e:
                    logger.warn("extend lv[%s] to size[%s] with operate failed" % (path, extend_size))
            else:
                logger.debug("lv %s extend to %s sucess" % (path, extend_size))

        @thread.AsyncThread
        @lock.lock("sharedblock-extend-vm-%s" % dom.name())
        def handle_event(dom, event_str):
            # type: (libvirt.virDomain, str) -> object
            vm_uuid = dom.name()
            syslog.syslog("got suspend event from libvirt, %s %s %s" %
                         (vm_uuid, event_str, LibvirtEventManager.suspend_event_to_string(detail)))
            disk_errors = dom.diskErrors()  # type: dict
            vm = get_vm_by_uuid_no_retry(vm_uuid, False)

            if len(disk_errors) == 0:
                syslog.syslog("no error in vm %s. skip to check and extend volume" % vm_uuid)
                return

            fixed = False

            def get_path_by_device(device_name, vm):
                for disk in vm.domain_xmlobject.devices.get_child_node_as_list('disk'):
                    if disk.target.dev_ == device_name:
                        return VmPlugin.get_source_file_by_disk(disk)

            try:
                for device, error in disk_errors.viewitems():
                    if error == libvirt.VIR_DOMAIN_DISK_ERROR_NO_SPACE:
                        path = get_path_by_device(device, vm)
                        syslog.syslog("disk %s:%s of vm %s got ENOSPC" % (device, path, vm_uuid))
                        if not lvm.lv_exists(path):
                            continue
                        extend_lv(event_str, path, vm, device)
                        fixed = True
            except Exception as e:
                syslog.syslog(str(e))

            if fixed:
                syslog.syslog("resume vm %s" % vm_uuid)
                vm.resume()
                touchQmpSocketWhenExists(vm_uuid)

        event_str = LibvirtEventManager.event_to_string(event)
        if event_str not in (LibvirtEventManager.EVENT_SUSPENDED,):
            return
        handle_event(dom, event_str)

    def _clean_colo_heartbeat(self, conn, dom, event, detail, opaque):
        event_str = LibvirtEventManager.event_to_string(event)
        if event_str not in (LibvirtEventManager.EVENT_SHUTDOWN, LibvirtEventManager.EVENT_STOPPED):
            return

        vm_uuid = dom.name()
        heartbeat_thread = self.vm_heartbeat.pop(vm_uuid, None)

        if heartbeat_thread and heartbeat_thread.is_alive():
            logger.debug("clean vm[uuid:%s] heartbeat, due to evnet %s" % (dom.name(), LibvirtEventManager.event_to_string(event)))
            heartbeat_thread.do_heart_beat = False
            heartbeat_thread.join()

    @bash.in_bash
    def _deactivate_drbd(self, conn, dom, event, detail, opaque):
        logger.debug("got event from libvirt, %s %s" % (dom.name(), LibvirtEventManager.event_to_string(event)))

        @thread.AsyncThread
        @bash.in_bash
        def deactivate_volume(event_str, file, vm_uuid):
            # type: (str, str, str) -> object
            minor = file.strip().split("'")[1].split('drbd')[-1]
            syslog.syslog("deactivating volume %s for vm %s" % (file, vm_uuid))
            configPath = bash.bash_o("grep 'minor %s;' /etc/drbd.d/*.res -l | awk -F '.res' '{print $1}'" % minor).strip()
            drbdResource = drbd.DrbdResource(configPath.split("/")[-1])
            try:
                drbdResource.demote()
                syslog.syslog(
                    "deactivated volume %s for event %s happend on vm %s success" % (file, event_str, vm_uuid))
            except Exception as e:
                syslog.syslog("deactivate volume %s for event %s happend on vm %s failed, %s" % (
                    file, event_str, vm_uuid, str(e)))

        try:
            event_str = LibvirtEventManager.event_to_string(event)
            if event_str not in (LibvirtEventManager.EVENT_SHUTDOWN, LibvirtEventManager.EVENT_STOPPED):
                return

            vm_uuid = dom.name()
            out = bash.bash_o("virsh dumpxml %s | grep \"source file='/dev/drbd\"" % vm_uuid).strip().splitlines()
            if len(out) != 0:
                for file in out:
                    deactivate_volume(event_str, file, vm_uuid)
            else:
                logger.debug("can not find drbd related volume for vm %s, skip to release" % vm_uuid)
        except:
            content = traceback.format_exc()
            logger.warn("traceback: %s" % content)

    @bash.in_bash
    def _release_sharedblocks(self, conn, dom, event, detail, opaque):
        logger.debug("got event from libvirt, %s %s" % (dom.name(), LibvirtEventManager.event_to_string(event)))

        @linux.retry(times=5, sleep_time=1)
        def wait_volume_unused(volume):
            used_process = linux.linux_lsof(volume)
            if len(used_process) != 0:
                raise RetryException("volume %s still used: %s" % (volume, used_process))

        @thread.AsyncThread
        @bash.in_bash
        def deactivate_colo_cache_volume(event_str, path, vm_uuid):
            try:
                wait_volume_unused(path)
            finally:
                used_process = linux.linux_lsof(path)

            if len(used_process) == 0:
                mount_path = path.rsplit('/',1)[0].replace("'", '')
                sblk_volume_path = linux.get_mount_url(mount_path)
                linux.umount(mount_path)
                linux.rm_dir_force(mount_path)

                if not sblk_volume_path:
                    syslog.syslog("vm: %s: no mount url found for %s" % (vm_uuid, mount_path))

                try:
                    lvm.deactive_lv(sblk_volume_path, False)
                    syslog.syslog(
                        "deactivated volume %s for event %s happend on vm %s" % (
                        sblk_volume_path, event_str, vm_uuid))
                except Exception as e:
                    logger.debug("deactivate volume %s for event %s happend on vm %s failed, %s" % (
                        sblk_volume_path, event_str, vm_uuid, str(e)))
            else:
                syslog.syslog("vm: %s, volume %s still used: %s, skip to deactivate" % (vm_uuid, path, used_process))


        @thread.AsyncThread
        @bash.in_bash
        def deactivate_volume(event_str, volume, vm_uuid):
            # type: (str, str, str) -> object
            syslog.syslog("deactivating volume %s for vm %s" % (volume, vm_uuid))
            lock_type = bash.bash_o("lvs --noheading --nolocking -t %s -ovg_lock_type" % volume).strip()
            if "sanlock" not in lock_type:
                syslog.syslog("%s has no sanlock, skip to deactive" % volume)
                return
            try:
                wait_volume_unused(volume)
            finally:
                used_process = linux.linux_lsof(volume)
            if len(used_process) == 0:
                try:
                    lvm.deactive_lv(volume, False)
                    syslog.syslog(
                        "deactivated volume %s for event %s happend on vm %s success" % (volume, event_str, vm_uuid))
                except Exception as e:
                    syslog.syslog("deactivate volume %s for event %s happend on vm %s failed, %s" % (
                        volume, event_str, vm_uuid, str(e)))
            else:
                syslog.syslog("vm: %s, volume %s still used: %s, skip to deactivate" % (vm_uuid, volume, used_process))

        try:
            event_str = LibvirtEventManager.event_to_string(event)
            if event_str not in (LibvirtEventManager.EVENT_SHUTDOWN, LibvirtEventManager.EVENT_STOPPED):
                return

            vm_uuid = dom.name()
            vm_op_judger = self._get_operation(vm_uuid)
            if vm_op_judger and event_str in vm_op_judger.ignore_libvirt_events():
                logger.info("expected event for zstack op %s, ignore event %s on vm %s" % (vm_op_judger.op, event_str, vm_uuid))
                return

            out = bash.bash_o("virsh dumpxml %s" % vm_uuid).strip()
            if len(out) != 0:
                tree = etree.ElementTree(etree.fromstring(out))
                for disk in tree.iterfind('devices/disk'):
                    volume = DomainVolume.from_xmlobject(disk)
                    if volume.source.startswith("/dev/"):
                        deactivate_volume(event_str, volume.source, vm_uuid)

            out = bash.bash_o('virsh dumpxml %s | grep -E "(active|hidden) file="' % vm_uuid).strip().splitlines()
            if len(out) != 0:
                for cache_config in out:
                    path = cache_config.split('=')[1].rsplit('/', 1)[0]
                    deactivate_colo_cache_volume(event_str, path, vm_uuid)

            else:
                logger.debug("can not find sharedblock related volume for vm %s, skip to release" % vm_uuid)
        except:
            content = traceback.format_exc()
            logger.warn("traceback: %s" % content)

    def _vm_shutdown_event(self, conn, dom, event, detail, opaque):
        try:
            event = LibvirtEventManager.event_to_string(event)
            if event not in (LibvirtEventManager.EVENT_SHUTDOWN,):
                return

            vm_uuid = dom.name()

            # this is an operation outside zstack, report it
            url = self.config.get(kvmagent.SEND_COMMAND_URL)
            if not url:
                logger.warn('cannot find SEND_COMMAND_URL, unable to report shutdown event of vm[uuid:%s]' % vm_uuid)
                return

            @thread.AsyncThread
            def report_to_management_node():
                cmd = ReportVmShutdownEventCmd()
                cmd.vmUuid = vm_uuid
                syslog.syslog('report shutdown event for vm ' + vm_uuid)
                http.json_dump_post(url, cmd, {'commandpath': '/kvm/reportvmshutdown'})

            report_to_management_node()
        except:
            content = traceback.format_exc()
            logger.warn("traceback: %s" % content)

    def _vm_shutdown_event_from_guest(self, conn, dom, event, detail, opaque):
        try:
            event = LibvirtEventManager.event_to_string(event)
            if event not in (LibvirtEventManager.EVENT_SHUTDOWN,):
                return

            if detail != libvirt.VIR_DOMAIN_EVENT_SHUTDOWN_GUEST:
                return

            vm_uuid = dom.name()
            logger.info("vm shutdown event from guest " + vm_uuid)
            # this is an operation outside zstack, report it
            url = self.config.get(kvmagent.SEND_COMMAND_URL)
            if not url:
                logger.warn('cannot find SEND_COMMAND_URL, unable to report shutdown event of vm[uuid:%s]' % vm_uuid)
                return

            @thread.AsyncThread
            def report_to_management_node():
                cmd = ReportVmShutdownEventCmd()
                cmd.vmUuid = vm_uuid
                syslog.syslog('report shutdown event for guest ' + vm_uuid)
                http.json_dump_post(url, cmd, {'commandpath': '/kvm/reportvmshutdown/from/guest'})

            report_to_management_node()
        except:
            content = traceback.format_exc()
            logger.warn("traceback: %s" % content)

    def _vm_start_event(self, conn, dom, event, detail, opaque):
        try:
            event = LibvirtEventManager.event_to_string(event)
            if event not in (LibvirtEventManager.EVENT_STARTED,):
                return

            vm_uuid = dom.name()

            # this is an operation outside zstack, report it
            url = self.config.get(kvmagent.SEND_COMMAND_URL)
            if not url:
                logger.warn('cannot find SEND_COMMAND_URL, unable to report start event of vm[uuid:%s]' % vm_uuid)
                return

            @thread.AsyncThread
            def report_to_management_node():
                cmd = ReportVmStartEventCmd()
                cmd.vmUuid = vm_uuid
                syslog.syslog('report start event for vm ' + vm_uuid)
                http.json_dump_post(url, cmd, {'commandpath': '/kvm/reportvmstart'})

            report_to_management_node()
        except:
            content = traceback.format_exc()
            logger.warn("traceback: %s" % content)

    def _vm_crashed_event(self, conn, dom, event, detail, opaque):
        try:
            event = LibvirtEventManager.event_to_string(event)
            if event not in (LibvirtEventManager.EVENT_CRASHED,):
                return

            vm_uuid = dom.name()

            # this is an operation outside zstack, report it
            url = self.config.get(kvmagent.SEND_COMMAND_URL)
            if not url:
                logger.warn('cannot find SEND_COMMAND_URL, unable to report crash event of vm[uuid:%s]' % vm_uuid)
                return

            logger.info('crashed event recieved from vm[uuid:%s]' % vm_uuid)
            logger.info('detail is %s, opaque is %s' % (detail, opaque))

            @thread.AsyncThread
            def report_to_management_node():
                cmd = ReportVmCrashEventCmd()
                cmd.vmUuid = vm_uuid
                syslog.syslog('report crash event for vm ' + vm_uuid)
                http.json_dump_post(url, cmd, {'commandpath': '/kvm/reportvmcrash'})

            report_to_management_node()
        except:
            content = traceback.format_exc()
            logger.warn("traceback: %s" % content)

    def _set_vnc_port_iptable_rule(self, conn, dom, event, detail, opaque):
        try:
            event = LibvirtEventManager.event_to_string(event)
            if event not in (LibvirtEventManager.EVENT_STARTED, LibvirtEventManager.EVENT_STOPPED):
                return
            vm_uuid = dom.name()
            if vm_uuid.startswith("guestfs-"):
                logger.debug("[set_vnc_port_iptable]ignore the temp vm[%s] while using guestfish" % vm_uuid)
                return

            domain_xml = dom.XMLDesc(0)
            domain_xmlobject = xmlobject.loads(domain_xml)

            if is_namespace_used():
                internal_id_node = find_zstack_metadata_node(etree.fromstring(domain_xml), 'internalId')
                vm_id = internal_id_node.text if internal_id_node is not None else None
            else:
                vm_id = domain_xmlobject.metadata.internalId.text_ if xmlobject.has_element(domain_xmlobject, 'metadata.internalId') else None

            if not vm_id:
                logger.debug('vm[uuid:%s] is not managed by zstack,  do not configure the vnc iptables rules' % vm_uuid)
                return

            vir = VncPortIptableRule()
            if LibvirtEventManager.EVENT_STARTED == event:

                if is_namespace_used():
                    host_ip_node = find_zstack_metadata_node(etree.fromstring(domain_xml), 'hostManagementIp')
                    vir.host_ip = host_ip_node.text
                else:
                    vir.host_ip = domain_xmlobject.metadata.hostManagementIp.text_

                if not iproute.query_addresses_by_ip(vir.host_ip):
                    logger.debug('the vm is migrated from another host, we do not need to set the console firewall, as '
                                 'the management node will take care')
                    return
                for g in domain_xmlobject.devices.get_child_node_as_list('graphics'):
                    if g.type_ == 'vnc' or g.type_ == 'spice':
                        vir.port = g.port_
                        break

                vir.vm_internal_id = vm_id
                vir.apply()
                logger.debug('Enable [port:%s] in firewall rule for vm[uuid:%s] console' % (vir.port, vm_id))
            elif LibvirtEventManager.EVENT_STOPPED == event:
                vir.vm_internal_id = vm_id
                vir.delete()
                logger.debug('Delete firewall rule for vm[uuid:%s] console' % vm_id)

        except:
            # if vm do live migrate the dom may not be found or the vm has been undefined
            vm = get_vm_by_uuid(dom.name(), False)
            if not vm:
                logger.debug("can not get domain xml of vm[uuid:%s], "
                             "the vm may be just migrated here or it has already been undefined" % dom.name())
                return

            content = traceback.format_exc()
            logger.warn(content)

    def _delete_pushgateway_metric(self, conn, dom, event, detail, opaque):
        try:
            event = LibvirtEventManager.event_to_string(event)
            if event != LibvirtEventManager.EVENT_STOPPED:
                return
            output = shell.call('ps aux | grep [p]ushgateway')
            if '/var/lib/zstack/kvm/pushgateway' not in output:
                return
            port = None
            lines = output.splitlines()
            for line in lines:
                if '/var/lib/zstack/kvm/pushgateway' in line:
                    port = line[line.rindex('web.listen-address :') + 20:]
                    port = port.split()[0]
                    break
            vm_uuid = dom.name()
            url = "http://localhost:%s/metrics/job/zwatch_vm_agent/vmUuid/%s" % (port, vm_uuid)
            shell.run('curl -X DELETE ' + url)
        except Exception as e:
            logger.warn("delete pushgateway metric when vm stoped failed: %s" % e.message)

    def register_libvirt_event(self):
        #LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._vm_lifecycle_event)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
                                                  self._set_vnc_port_iptable_rule)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_REBOOT, self._vm_reboot_event)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._vm_shutdown_event)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._vm_shutdown_event_from_guest)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._vm_start_event)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._vm_crashed_event)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._release_sharedblocks)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._deactivate_drbd)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._clean_colo_heartbeat)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._extend_sharedblock)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._delete_pushgateway_metric)
        LibvirtAutoReconnect.register_libvirt_callbacks()

    def register_qemu_log_cleaner(self):
        def pick_uuid_from_filename(filename):
            pattern = r'^([0-9a-f]{32})\.log'
            matcher = re.match(pattern, filename)
            if matcher:
                return matcher.group(1) # return uuid
            else:
                return None

        def qemu_log_cleaner():
            logger.debug('Clean libvirt log task start')
            try:
                log_paths = linux.listPath('/var/log/libvirt/qemu/')
                all_active_vm_uuids = set(get_all_vm_states())

                # log life : 180 days
                clean_time = datetime.datetime.now() - datetime.timedelta(days=180)

                for p in log_paths:
                    filename = os.path.basename(p)
                    uuid = pick_uuid_from_filename(filename)
                    if uuid and uuid in all_active_vm_uuids:
                        # vm exists
                        continue

                    try:
                        modify_time = datetime.datetime.fromtimestamp(os.stat(p).st_mtime)
                        if modify_time < clean_time:
                            linux.rm_file_force(p)

                    except Exception as ex_inner:
                        logger.warn('Failed to clean libvirt log files `%s` because : %s' % (p, str(ex_inner)))

            except Exception as ex_outer:
                logger.warn('Failed to clean libvirt log files because : %s' % str(ex_outer))

            # run cleaner : once a day
            thread.timer(24 * 3600, qemu_log_cleaner).start()

        # first time
        thread.timer(60, qemu_log_cleaner).start()

    def register_vm_console_logrotate_conf(self):
        if not os.path.exists(self.VM_CONSOLE_LOGROTATE_PATH):
            content = """/tmp/*-vm-kernel.log {
        rotate 10
        missingok
        copytruncate
        size 30M
        compress
}"""
            with open(self.VM_CONSOLE_LOGROTATE_PATH, 'w') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(self.VM_CONSOLE_LOGROTATE_PATH, 0o644)

        def vm_console_logRotate():
            ret = bash.bash_r("logrotate -vf %s" % self.VM_CONSOLE_LOGROTATE_PATH)

            thread.timer(24 * 3600, vm_console_logRotate).start()

        thread.timer(60, vm_console_logRotate).start()

    def clean_old_sshfs_mount_points(self):
        mpts = shell.call("mount -t fuse.sshfs | awk '{print $3}'").splitlines()
        for mpt in mpts:
            if mpt.startswith(tempfile.gettempdir()):
                linux.get_pids_by_process_fullname(mpt)
                linux.fumount(mpt, 2)

    def stop(self):
        self.clean_old_sshfs_mount_points()
        pass

    def configure(self, config=None):
        if config is None:
            config = {}
        self.config = config


    @staticmethod
    def get_iothread_info(vm_uuid):
        exec_cmd = "virsh iothreadinfo {}".format(vm_uuid)
        cmd_res = shell.call(exec_cmd)
        result = []
        if not cmd_res:
            return result
        if cmd_res.startswith("No IOThreads found for the domain"):
            return result
        if "IOThread ID" in cmd_res and "CPU Affinity" in cmd_res:
            temp = cmd_res.split("\n")
            temp = temp[2:]
            for t in temp:
                i = filter(lambda i: i, t.strip().split(" "))
                if not i:
                    continue
                if i[0].isdigit():
                    result.append([str(i[0]), str(i[1])])
        return result


    @kvmagent.replyerror
    def set_iothread_pin(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetVmIoThreadPinRsp()

        iothread_info = self.get_iothread_info(cmd.vmUuid)
        iothread_ids = [i[0] for i in iothread_info]

        err_info = None
        if str(cmd.ioThreadId) not in iothread_ids:
            err_info = self.add_io_thread(cmd.vmUuid, cmd.ioThreadId)
        if err_info:
            rsp.error = err_info
            logger.error("add iothread[{}] failed: {}".format(cmd.ioThreadId, err_info))
            return jsonobject.dumps(rsp)

        err_info = self.pin_io_thread(cmd.vmUuid, cmd.ioThreadId, cmd.pin)
        if err_info:
            rsp.error = err_info
            logger.error("pin iothread[{}] failed: {}".format(cmd.ioThreadId, err_info))
            return jsonobject.dumps(rsp)
        logger.info("set iothread[{}] pin[{}] on vm[{}] successfully.".format(cmd.ioThreadId, cmd.pin, cmd.vmUuid))
        rsp.ioThreadId = cmd.ioThreadId
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def del_iothread_pin(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DelVmIoThreadPinRsp()

        iothread_info = self.get_iothread_info(cmd.vmUuid)
        iothread_ids = [i[0] for i in iothread_info]

        err_info = None
        if str(cmd.ioThreadId) in iothread_ids:
            err_info = self.del_io_thread(cmd.vmUuid, cmd.ioThreadId)

        if err_info:
            rsp.error = err_info
            logger.error("del iothread[{}] failed: {}".format(cmd.ioThreadId, err_info))
        else:
            rsp.ioThreadId = cmd.ioThreadId
            logger.info("del iothread[{}] on vm[{}] successfully.".format(cmd.ioThreadId, cmd.vmUuid))
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def get_iothread_pin(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVmIoThreadPinRsp()

        iothread_info = self.get_iothread_info(cmd.vmUuid)
        res = [{"ioThreadId": i[0], "ioThreadPin": i[1]} for i in iothread_info]

        rsp.ioThreadInfo = res
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def set_scsi_controller(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SetVmScsiControllerRsp()

        scsi_controller_index = self.add_scsi_controller(cmd.vmUuid, cmd.ioThreadId)

        rsp.vmUuid = cmd.vmUuid
        rsp.ioThreadId = cmd.ioThreadId
        rsp.controllerIndex = str(scsi_controller_index)
        return jsonobject.dumps(rsp)


    @kvmagent.replyerror
    def del_scsi_controller(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DelVmScsiControllerRsp()

        vm = get_vm_by_uuid(cmd.vmUuid)
        for controller in vm.domain_xmlobject.devices.get_child_node_as_list('controller'):
            if controller.type_ == 'scsi' and hasattr(controller, 'driver') and hasattr(controller.driver, 'iothread_') \
                    and str(controller.driver.iothread_) == str(cmd.ioThreadId):
                self.detach_controller_by_alias(cmd.vmUuid, controller.alias.name_)
                break

        rsp.vmUuid = cmd.vmUuid
        rsp.ioThreadId = cmd.ioThreadId
        return jsonobject.dumps(rsp)

    @staticmethod
    def add_scsi_controller(vm_uuid, io_thread_id):
        vm_xml_obj = get_vm_by_uuid(vm_uuid)
        index = vm_xml_obj.find_scsi_controller_by_iothread(io_thread_id)
        if not index or index == "0":
            index = VmPlugin.get_next_scsi_controller_index(vm_xml_obj)
            controller_xml = etree.Element('controller',
                                           attrib={'type': 'scsi', 'model': 'virtio-scsi', 'index': str(index)})
            e(controller_xml, 'address', None, {'type': 'pci'})
            e(controller_xml, 'driver', None, {'iothread': str(io_thread_id)})
            e(controller_xml, 'alias', None, {'name': 'scsi{0}'.format(io_thread_id)})
            vm_xml_obj.domain.attachDeviceFlags(etree.tostring(controller_xml), libvirt.VIR_DOMAIN_AFFECT_LIVE)
        return index

    @staticmethod
    def get_next_scsi_controller_index(vm_xml_obj):
        old_index_list = []
        for controller in vm_xml_obj.domain_xmlobject.devices.get_child_node_as_list('controller'):
            if controller.type_ == "scsi":
                old_index_list.append(int(controller.index_))
        new_index_list = [i for i in range(0, len(old_index_list) + 1)]
        return set(new_index_list).difference(set(old_index_list)).pop()


    @linux.retry(times=3, sleep_time=1)
    def detach_controller_by_alias(self, vm_uuid, controller_alias):
        exec_cmd = "virsh detach-device-alias %s %s --current" % (vm_uuid, controller_alias)
        cmd_res = shell.call(exec_cmd)
        res = None
        if cmd_res and cmd_res.startswith("error:"):
            res = cmd_res
        return res

    @staticmethod
    def add_io_thread(vm_uuid, io_thread_id):
        exec_cmd = "virsh iothreadadd {} {} --current".format(vm_uuid, io_thread_id)
        cmd_res = shell.call(exec_cmd)
        res = None
        if cmd_res and cmd_res.startswith("error:"):
            res = cmd_res
        return res


    @staticmethod
    def pin_io_thread(vm_uuid, io_thread_id, cpus):
        exec_cmd = "virsh iothreadpin {} {} {} --current".format(vm_uuid, io_thread_id, cpus)
        cmd_res = shell.call(exec_cmd)
        res = None
        if cmd_res and  cmd_res.startswith("error:"):
            res = cmd_res
        return res

    @staticmethod
    @linux.retry(times=3, sleep_time=1)
    def del_io_thread(vm_uuid, io_thread_id):
        exec_cmd = "virsh iothreaddel {} {} --current".format(vm_uuid, io_thread_id)
        cmd_res = shell.call(exec_cmd)
        res = None
        if cmd_res and cmd_res.startswith("error:"):
            res = cmd_res
        return res

    @kvmagent.replyerror
    def attach_ssh_key_pair(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        self.do_attach_ssh_key_pair(cmd.vmInstanceUuid, cmd.publicKey)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def detach_ssh_key_pair(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        self.do_detach_ssh_key_pair(cmd.vmInstanceUuid, cmd.publicKey)

        return jsonobject.dumps(rsp)

    def do_attach_ssh_key_pair(self, vm_uuid, public_key):
        @LibvirtAutoReconnect
        def call_libvirt(conn):
            return conn.lookupByName(vm_uuid)

        def leagacy_add_authorized_keys():
            command = ("mkdir -p /root/.ssh; if ! cat "
                       "/root/.ssh/authorized_keys | grep -q '%s'; "
                       "then echo '%s' >> /root/.ssh/authorized_keys; fi" % (
                           public_key, public_key))
            args = {
                'path': '/bin/sh',
                'arg': ['-c', command],
                'capture-output': True
            }
            qga.guest_exec_bash_no_exitcode(command)

        def ga_add_authorized_keys():
            ret = qga.guest_ssh_add_authorized_keys(public_key)
            if ret:
                raise Exception(('Guest add ssh authrozed keys return '
                                 'unexpected result: %s') % ret)

        qga = VmQga(call_libvirt())
        if qga.state != VmQga.QGA_STATE_RUNNING:
            raise Exception(('The qemu guest agent not in running state'))

        ga_version = qga.guest_info()['version']
        if LooseVersion(ga_version) < LooseVersion('2.5'):
            raise Exception(('The guest agent version %s less '
                             'than minimum requirement 2.5.0') % ga_version)
        elif LooseVersion(ga_version) >= LooseVersion('5.2'):
            ga_add_authorized_keys()
        else:
            leagacy_add_authorized_keys()

    def do_detach_ssh_key_pair(self, vm_uuid, public_key):
        @LibvirtAutoReconnect
        def call_libvirt(conn):
            return conn.lookupByName(vm_uuid)

        def leagacy_remove_authorized_keys():
            command = ("if [ -f /root/.ssh/authorized_keys ]; "
                       "then sed -i '/%s/d' /root/.ssh/authorized_keys; "
                       "fi") % public_key.replace('/', '\/')
            args = {
                'path': '/bin/sh',
                'arg': ['-c', command],
                'capture-output': True
            }
            qga.guest_exec_bash_no_exitcode(command)

        def ga_remove_authorized_keys():
            ret = qga.guest_ssh_remove_authorized_keys(public_key)
            if ret:
                raise Exception(('Guest remove ssh authrozed keys return '
                                 'unexpected result: %s') % ret)

        qga = VmQga(call_libvirt())
        if qga.state != VmQga.QGA_STATE_RUNNING:
            raise Exception(('The qemu guest agent not in running state'))

        ga_version = qga.guest_info()['version']
        if LooseVersion(ga_version) < LooseVersion('2.5'):
            raise Exception(('The guest agent version %s less than '
                             'minimum requirement version 2.5') % ga_version)
        elif LooseVersion(ga_version) >= LooseVersion('5.2'):
            ga_remove_authorized_keys()
        else:
            leagacy_remove_authorized_keys()


class EmptyCdromConfig():
    def __init__(self, targetDev, bus, unit):
        self.targetDev = targetDev
        self.bus = bus
        self.unit = unit

class VolumeIDEConfig():
    def __init__(self, bus, unit):
        self.bus = bus
        self.unit = unit

class ColoReplicationConfig():
    def __init__(self, alias_name, replication_id):
        self.alias_name = alias_name
        self.replication_id = replication_id


class VolumeSnapshotJobStruct(object):
    def __init__(self, volumeUuid, volume, installPath, vmInstanceUuid, previousInstallPath,
                 newVolumeInstallPath, live=True, full=False, memory=False):
        self.volumeUuid = volumeUuid
        self.volume = volume
        self.installPath = installPath
        self.vmInstanceUuid = vmInstanceUuid
        self.previousInstallPath = previousInstallPath
        self.newVolumeInstallPath = newVolumeInstallPath
        self.memory = memory
        self.live = live
        self.full = full


class VolumeSnapshotResultStruct(object):
    def __init__(self, volumeUuid, previousInstallPath, installPath, size=None, memory=False):
        """

        :type volumeUuid: str
        :type size: long
        :type installPath: str
        :type previousInstallPath: str
        """
        self.volumeUuid = volumeUuid
        self.previousInstallPath = previousInstallPath
        self.installPath = installPath
        self.size = size
        self.memory = memory


@bash.in_bash
@misc.ignoreerror
def touchQmpSocketWhenExists(vmUuid):
    if vmUuid is None:
        return
    path = "%s/%s.sock" % (QMP_SOCKET_PATH, vmUuid)
    if os.path.exists(path):
        bash.bash_roe("touch %s" % path)

