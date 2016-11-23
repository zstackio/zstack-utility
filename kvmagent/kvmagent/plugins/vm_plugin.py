'''
@author: Frank
'''
import Queue
import os.path
import time
import traceback
import xml.etree.ElementTree as etree

import libvirt
import zstacklib.utils.iptables as iptables
import zstacklib.utils.lock as lock
from kvmagent import kvmagent
from zstacklib.utils import generate_passwd
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lichbd
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import thread
from zstacklib.utils import uuidhelper
from zstacklib.utils import xmlobject

logger = log.get_logger(__name__)


class NicTO(object):
    def __init__(self):
        self.mac = None
        self.bridgeName = None
        self.deviceId = None


class StartVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(StartVmCmd, self).__init__()
        self.vmInstanceUuid = None
        self.vmName = None
        self.memory = None
        self.cpuNum = None
        self.cpuSpeed = None
        self.bootDev = None
        self.rootVolume = None
        self.dataVolumes = []
        self.isoPath = None
        self.nics = []
        self.timeout = None
        self.dataIsoPaths = None
        self.addons = None


class StartVmResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(StartVmResponse, self).__init__()


class GetVncPortCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(GetVncPortCmd, self).__init__()
        self.vmUuid = None


class GetVncPortResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(GetVncPortResponse, self).__init__()
        self.port = None
        self.protocol = None


class ChangeCpuMemResponse(kvmagent.AgentResponse):
    def _init_(self):
        super(ChangeCpuMemResponse, self)._init_()
        self.cpuNum = None
        self.memorySize = None
        self.vmuuid


class StopVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(StopVmCmd, self).__init__()
        self.uuid = None
        self.timeout = None


class StopVmResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(StopVmResponse, self).__init__()


class SuspendVmCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(SuspendVmCmd, self).__init__()
        self.uuid = None
        self.timeout = None


class SuspendVmResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(SuspendVmResponse, self).__init__()


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


class AttachDataVolumeCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(AttachDataVolumeCmd, self).__init__()
        self.volume = None
        self.uuid = None


class AttachDataVolumeResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(AttachDataVolumeResponse, self).__init__()


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


class TakeSnapshotResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(TakeSnapshotResponse, self).__init__()
        self.newVolumeInstallPath = None
        self.snapshotInstallPath = None
        self.size = None


class MergeSnapshotRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(MergeSnapshotRsp, self).__init__()


class LogoutIscsiTargetRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(LogoutIscsiTargetRsp, self).__init__()


class LoginIscsiTargetRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(LoginIscsiTargetRsp, self).__init__()


class ReportVmStateCmd(object):
    def __init__(self):
        self.hostUuid = None
        self.vmUuid = None
        self.vmState = None


class CheckVmStateRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(CheckVmStateRsp, self).__init__()
        self.states = {}


class ChangeVmPasswordRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(ChangeVmPasswordRsp, self).__init__()
        self.accountPerference = None


class AccountPerference(object):
    def __init__(self):
        self.userAccount = None
        self.accountPassword = None
        self.vmUuid = None


class SetRootPasswordRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(SetRootPasswordRsp, self).__init__()
        self.accountPerference = AccountPerference()
        self.qcowFile = None


class ReconnectMeCmd(object):
    def __init__(self):
        self.hostUuid = None
        self.reason = None


class VncPortIptableRule(object):
    def __init__(self):
        self.host_ip = None
        self.port = None
        self.vm_internal_id = None

    def _make_chain_name(self):
        return "vm-%s-vnc" % self.vm_internal_id

    @lock.file_lock('iptables')
    def apply(self):
        assert self.host_ip is not None
        assert self.port is not None
        assert self.vm_internal_id is not None

        ipt = iptables.from_iptables_save()
        chain_name = self._make_chain_name()
        ipt.add_rule('-A INPUT -p tcp -m tcp --dport %s -j %s' % (self.port, chain_name))
        ipt.add_rule('-A %s -d %s/32 -j ACCEPT' % (chain_name, self.host_ip))
        ipt.add_rule('-A %s ! -d %s/32 -j REJECT --reject-with icmp-host-prohibited' % (chain_name, self.host_ip))
        ipt.iptable_restore()

    @lock.file_lock('iptables')
    def delete(self):
        assert self.vm_internal_id is not None

        ipt = iptables.from_iptables_save()
        chain_name = self._make_chain_name()
        ipt.delete_chain(chain_name)
        ipt.iptable_restore()

    @lock.file_lock('iptables')
    def delete_stale_chains(self):
        vms = get_running_vms()
        ipt = iptables.from_iptables_save()
        tbl = ipt.get_table()

        internal_ids = []
        for vm in vms:
            if not vm.domain_xmlobject.has_element('metadata.internalId'):
                continue

            id = vm.domain_xmlobject.metadata.internalId.text_
            if id:
                internal_ids.append(id)

        # delete all vnc chains
        for chain in tbl.children:
            if 'vm' in chain.name and 'vnc' in chain.name:
                vm_internal_id = chain.name.split('-')[1]
                if vm_internal_id not in internal_ids:
                    chain.delete()
                    logger.debug('deleted a stale VNC iptable chain[%s]' % chain.name)

        ipt.iptable_restore()


def e(parent, tag, value=None, attrib={}):
    el = etree.SubElement(parent, tag, attrib)
    if value:
        el.text = value
    return el


class LibvirtEventManager(object):
    EVENT_DEFINED = "Defined"
    EVENT_UNDEFINED = "Undefined"
    EVENT_STARTED = "Started"
    EVENT_SUSPENDED = "Suspended"
    EVENT_RESUMED = "Resumed"
    EVENT_STOPPED = "Stopped"
    EVENT_SHUTDOWN = "Shutdown"

    event_strings = (
        EVENT_DEFINED,
        EVENT_UNDEFINED,
        EVENT_STARTED,
        EVENT_SUSPENDED,
        EVENT_RESUMED,
        EVENT_STOPPED,
        EVENT_SHUTDOWN
    )

    def __init__(self):
        self.stopped = False
        libvirt.virEventRegisterDefaultImpl()

        @thread.AsyncThread
        def run():
            logger.debug("virEventRunDefaultImpl starts")
            while not self.stopped:
                try:
                    if libvirt.virEventRunDefaultImpl() < 0:
                        logger.warn("virEventRunDefaultImpl quit with error")
                except:
                    content = traceback.format_exc()
                    logger.warn(content)

            logger.debug("virEventRunDefaultImpl stopped")

        run()

    def stop(self):
        self.stopped = True

    @staticmethod
    def event_to_string(index):
        return LibvirtEventManager.event_strings[index]


class LibvirtAutoReconnect(object):
    conn = libvirt.open('qemu:///system')

    if not conn:
        raise Exception('unable to get libvirt connection')

    evtMgr = LibvirtEventManager()

    libvirt_event_callbacks = {}

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

        LibvirtAutoReconnect.conn.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_REBOOT, reboot_callback,
                                                         None)

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
                return None
            except libvirt.libvirtError as ex:
                return ex

        ex = test_connection()
        if not ex:
            # the connection is ok
            return

        logger.warn("the libvirt connection is broken, there is no safeway to auto-reconnect without fd leak, we"
                    " will ask the mgmt server to reconnect us after self quit")
        VmPlugin.queue.put("exit")

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
            if 'client socket is closed' in err or 'Broken pipe' in err:
                logger.debug('socket to the libvirt is broken[%s], try reconnecting' % err)
                self._reconnect()
                return self.func(LibvirtAutoReconnect.conn)
            else:
                raise


class IscsiLogin(object):
    def __init__(self):
        self.server_hostname = None
        self.server_port = None
        self.target = None
        self.chap_username = None
        self.chap_password = None
        self.lun = 1

    @lock.lock('iscsiadm')
    def login(self):
        assert self.server_hostname, "hostname cannot be None"
        assert self.server_port, "port cannot be None"
        assert self.target, "target cannot be None"

        device_path = os.path.join('/dev/disk/by-path/', 'ip-%s:%s-iscsi-%s-lun-%s' % (
        self.server_hostname, self.server_port, self.target, self.lun))

        shell.call('iscsiadm -m discovery -t sendtargets -p %s:%s' % (self.server_hostname, self.server_port))

        if self.chap_username and self.chap_password:
            shell.call(
                'iscsiadm   --mode node  --targetname "%s"  -p %s:%s --op=update --name node.session.auth.authmethod --value=CHAP' % (
                self.target, self.server_hostname, self.server_port))
            shell.call(
                'iscsiadm   --mode node  --targetname "%s"  -p %s:%s --op=update --name node.session.auth.username --value=%s' % (
                self.target, self.server_hostname, self.server_port, self.chap_username))
            shell.call(
                'iscsiadm   --mode node  --targetname "%s"  -p %s:%s --op=update --name node.session.auth.password --value=%s' % (
                self.target, self.server_hostname, self.server_port, self.chap_password))

        shell.call('iscsiadm  --mode node  --targetname "%s"  -p %s:%s --login' % (
        self.target, self.server_hostname, self.server_port))

        def wait_device_to_show(_):
            return os.path.exists(device_path)

        if not linux.wait_callback_success(wait_device_to_show, timeout=30, interval=0.5):
            raise Exception('ISCSI device[%s] is not shown up after 30s' % device_path)

        return device_path


class BlkIscsi(object):
    def __init__(self):
        self.is_cdrom = None
        self.volume_uuid = None
        self.chap_username = None
        self.chap_password = None
        self.device_letter = None
        self.server_hostname = None
        self.server_port = None
        self.target = None
        self.lun = None

    def _login_portal(self):
        login = IscsiLogin()
        login.server_hostname = self.server_hostname
        login.server_port = self.server_port
        login.target = self.target
        login.chap_username = self.chap_username
        login.chap_password = self.chap_password
        return login.login()

    def to_xmlobject(self):
        device_path = self._login_portal()
        if self.is_cdrom:
            root = etree.Element('disk', {'type': 'block', 'device': 'cdrom'})
            e(root, 'driver', attrib={'name': 'qemu', 'type': 'raw', 'cache': 'none'})
            e(root, 'source', attrib={'dev': device_path})
            e(root, 'target', attrib={'dev': self.device_letter})
        else:
            root = etree.Element('disk', {'type': 'block', 'device': 'lun'})
            e(root, 'driver', attrib={'name': 'qemu', 'type': 'raw', 'cache': 'none'})
            e(root, 'source', attrib={'dev': device_path})
            e(root, 'target', attrib={'dev': 'sd%s' % self.device_letter})
        return root

    @staticmethod
    @lock.lock('iscsiadm')
    def logout_portal(dev_path):
        if not os.path.exists(dev_path):
            return

        device = os.path.basename(dev_path)
        portal = device[3:device.find('-iscsi')]
        target = device[device.find('iqn'):device.find('-lun')]
        try:
            shell.call('iscsiadm  -m node  --targetname "%s" --portal "%s" --logout' % (target, portal))
        except Exception as e:
            logger.warn('failed to logout device[%s], %s' % (dev_path, str(e)))


class IsoCeph(object):
    def __init__(self):
        self.iso = None

    def to_xmlobject(self):
        disk = etree.Element('disk', {'type': 'network', 'device': 'cdrom'})
        source = e(disk, 'source', None, {'name': self.iso.path.lstrip('ceph:').lstrip('//'), 'protocol': 'rbd'})
        auth = e(disk, 'auth', attrib={'username': 'zstack'})
        e(auth, 'secret', attrib={'type': 'ceph', 'uuid': self.iso.secretUuid})
        for minfo in self.iso.monInfo:
            e(source, 'host', None, {'name': minfo.hostname, 'port': str(minfo.port)})
        e(disk, 'target', None, {'dev': 'hdc', 'bus': 'ide'})
        e(disk, 'readonly', None)
        return disk


class IdeCeph(object):
    def __init__(self):
        self.volume = None
        self.dev_letter = None

    def to_xmlobject(self):
        disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
        source = e(disk, 'source', None,
                   {'name': self.volume.installPath.lstrip('ceph:').lstrip('//'), 'protocol': 'rbd'})
        auth = e(disk, 'auth', attrib={'username': 'zstack'})
        e(auth, 'secret', attrib={'type': 'ceph', 'uuid': self.volume.secretUuid})
        for minfo in self.volume.monInfo:
            e(source, 'host', None, {'name': minfo.hostname, 'port': str(minfo.port)})
        e(disk, 'target', None, {'dev': 'hd%s' % self.dev_letter, 'bus': 'ide'})
        return disk


class VirtioCeph(object):
    def __init__(self):
        self.volume = None
        self.dev_letter = None

    def to_xmlobject(self):
        disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
        source = e(disk, 'source', None,
                   {'name': self.volume.installPath.lstrip('ceph:').lstrip('//'), 'protocol': 'rbd'})
        auth = e(disk, 'auth', attrib={'username': 'zstack'})
        e(auth, 'secret', attrib={'type': 'ceph', 'uuid': self.volume.secretUuid})
        for minfo in self.volume.monInfo:
            e(source, 'host', None, {'name': minfo.hostname, 'port': str(minfo.port)})
        e(disk, 'target', None, {'dev': 'vd%s' % self.dev_letter, 'bus': 'virtio'})
        return disk


class VirtioSCSICeph(object):
    def __init__(self):
        self.volume = None
        self.dev_letter = None

    def to_xmlobject(self):
        disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
        source = e(disk, 'source', None,
                   {'name': self.volume.installPath.lstrip('ceph:').lstrip('//'), 'protocol': 'rbd'})
        auth = e(disk, 'auth', attrib={'username': 'zstack'})
        e(auth, 'secret', attrib={'type': 'ceph', 'uuid': self.volume.secretUuid})
        for minfo in self.volume.monInfo:
            e(source, 'host', None, {'name': minfo.hostname, 'port': str(minfo.port)})
        e(disk, 'target', None, {'dev': 'sd%s' % self.dev_letter, 'bus': 'scsi'})
        e(disk, 'wwn', self.volume.wwn)
        e(disk, 'shareable')
        return disk


class IsoFusionstor(object):
    def __init__(self):
        self.iso = None

    def to_xmlobject(self):
        protocol = lichbd.get_protocol()
        snap = self.iso.path.lstrip('fusionstor:').lstrip('//')
        path = self.iso.path.lstrip('fusionstor:').lstrip('//').split('@')[0]
        if protocol == 'lichbd':
            iqn = lichbd.lichbd_get_iqn()
            port = lichbd.lichbd_get_iscsiport()
            lichbd.makesure_qemu_img_with_lichbd()

            shellcmd = shell.ShellCmd('lichbd mkpool %s -p iscsi' % path.split('/')[0])
            shellcmd(False)
            if shellcmd.return_code != 0 and shellcmd.return_code != 17:
                shellcmd.raise_error()

            shellcmd = shell.ShellCmd(
                'lich.snapshot --clone %s %s' % (os.path.join('/lichbd/', snap), os.path.join('/iscsi/', path)))
            shellcmd(False)
            if shellcmd.return_code != 0 and shellcmd.return_code != 17:
                shellcmd.raise_error()

            pool = path.split('/')[0]
            image = path.split('/')[1]
            # iqn:pool.volume/0
            path = '%s:%s.%s/0' % (iqn, pool, image)
            protocol = 'iscsi'
        elif protocol == 'sheepdog' or protocol == 'nbd':
            pass
        else:
            raise shell.ShellError('Do not supprot protocols, only supprot lichbd, sheepdog and nbd')

        disk = etree.Element('disk', {'type': 'network', 'device': 'cdrom'})
        source = e(disk, 'source', None, {'name': path, 'protocol': protocol})
        if protocol == 'iscsi':
            e(source, 'host', None, {'name': '127.0.0.1', 'port': '3260'})
        elif protocol == 'sheepdog':
            e(source, 'host', None, {'name': '127.0.0.1', 'port': '7000'})
        elif protocol == 'nbd':
            e(source, 'host', None, {'name': 'unix', 'port': '/tmp/nbd-socket'})
        e(disk, 'target', None, {'dev': 'hdc', 'bus': 'ide'})
        e(disk, 'readonly', None)
        return disk


class IdeFusionstor(object):
    def __init__(self):
        self.volume = None
        self.dev_letter = None

    def to_xmlobject(self):
        protocol = lichbd.get_protocol()
        if protocol == 'lichbd':
            lichbd.makesure_qemu_img_with_lichbd()
        elif protocol == 'sheepdog' or protocol == 'nbd':
            pass
        else:
            raise shell.ShellError('Do not supprot protocols, only supprot lichbd, sheepdog and nbd')

        path = self.volume.installPath.lstrip('fusionstor:').lstrip('//')
        file_format = lichbd.lichbd_get_format(path)

        disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
        source = e(disk, 'source', None, {'name': path, 'protocol': protocol})
        if protocol == 'sheepdog':
            e(source, 'host', None, {'name': '127.0.0.1', 'port': '7000'})
        elif protocol == 'nbd':
            e(source, 'host', None, {'name': 'unix', 'port': '/tmp/nbd-socket'})
        e(disk, 'target', None, {'dev': 'hd%s' % self.dev_letter, 'bus': 'ide'})
        e(disk, 'driver', None, {'cache': 'none', 'name': 'qemu', 'io': 'native', 'type': file_format})
        return disk


class VirtioFusionstor(object):
    def __init__(self):
        self.volume = None
        self.dev_letter = None

    def to_xmlobject(self):
        protocol = lichbd.get_protocol()
        if protocol == 'lichbd':
            lichbd.makesure_qemu_img_with_lichbd()
        elif protocol == 'sheepdog' or protocol == 'nbd':
            pass
        else:
            raise shell.ShellError('Do not supprot protocols, only supprot lichbd, sheepdog and nbd')

        path = self.volume.installPath.lstrip('fusionstor:').lstrip('//')
        file_format = lichbd.lichbd_get_format(path)

        disk = etree.Element('disk', {'type': 'network', 'device': 'disk'})
        source = e(disk, 'source', None, {'name': path, 'protocol': protocol})
        if protocol == 'sheepdog':
            e(source, 'host', None, {'name': '127.0.0.1', 'port': '7000'})
        elif protocol == 'nbd':
            e(source, 'host', None, {'name': 'unix', 'port': '/tmp/nbd-socket'})
        e(disk, 'target', None, {'dev': 'vd%s' % self.dev_letter, 'bus': 'virtio'})
        e(disk, 'driver', None, {'cache': 'none', 'name': 'qemu', 'io': 'native', 'type': file_format})
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
        e(root, 'driver', attrib={'name': 'qemu', 'type': 'raw', 'cache': 'none'})

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


def get_vm_by_uuid(uuid, exception_if_not_existing=True):
    try:
        # libvirt may not be able to find a VM when under a heavy workload, we re-try here
        @LibvirtAutoReconnect
        def call_libvirt(conn):
            return conn.lookupByName(uuid)

        @linux.retry(times=3, sleep_time=1)
        def retry_call_libvirt():
            return call_libvirt()

        vm = Vm.from_virt_domain(retry_call_libvirt())
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


def get_running_vm_uuids():
    @LibvirtAutoReconnect
    def call_libvirt(conn):
        return conn.listDomainsID()

    ids = call_libvirt()
    uuids = []

    @LibvirtAutoReconnect
    def get_domain(conn):
        # i is for..loop's control variable
        # it's Python's local scope tricky
        return conn.lookupByID(i)

    for i in ids:
        domain = get_domain()
        uuids.append(domain.name())
    return uuids


def get_all_vm_states():
    ret = {}
    running = get_running_vm_uuids()
    for r in running:
        ret[r] = Vm.VM_STATE_RUNNING
    return ret


def get_running_vms():
    @LibvirtAutoReconnect
    def get_all_ids(conn):
        return conn.listDomainsID()

    ids = get_all_ids()
    vms = []

    @LibvirtAutoReconnect
    def get_domain(conn):
        return conn.lookupByID(i)

    for i in ids:
        vm = Vm.from_virt_domain(get_domain())
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

    # letter 'c' is reserved for cdrom
    DEVICE_LETTERS = 'abdefghijklmnopqrstuvwxyz'

    timeout_object = linux.TimeoutObject()

    def __init__(self):
        self.uuid = None
        self.domain_xmlobject = None
        self.domain_xml = None
        self.domain = None
        self.state = None

    def wait_for_state_change(self, state):
        try:
            self.refresh()
        except Exception as e:
            if not state:
                return True
            raise e

        return self.state == state

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

    def get_memory(self):
        return long(self.domain_xmlobject.currentMemory.text_) * 1024

    def get_name(self):
        return self.domain_xmlobject.description.text_

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

    def _wait_for_vm_running(self, timeout=60):
        if not linux.wait_callback_success(self.wait_for_state_change, self.VM_STATE_RUNNING, interval=0.5,
                                           timeout=timeout):
            raise kvmagent.KvmError('unable to start vm[uuid:%s, name:%s], vm state is not changing to '
                                    'running after %s seconds' % (self.uuid, self.get_name(), timeout))

        vnc_port = self.get_console_port()

        def wait_vnc_port_open(_):
            cmd = shell.ShellCmd('netstat -na | grep ":%s" > /dev/null' % vnc_port)
            cmd(is_exception=False)
            return cmd.return_code == 0

        if not linux.wait_callback_success(wait_vnc_port_open, None, interval=0.5, timeout=30):
            raise kvmagent.KvmError("unable to start vm[uuid:%s, name:%s]; its vnc port does"
                                    " not open after 30 seconds" % (self.uuid, self.get_name()))

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

    def start(self, timeout=60):
        # TODO: 1. enbale hair_pin mode
        logger.debug('creating vm:\n%s' % self.domain_xml)

        @LibvirtAutoReconnect
        def define_xml(conn):
            return conn.defineXML(self.domain_xml)

        domain = define_xml()
        self.domain = domain
        self.domain.createWithFlags(0)
        self._wait_for_vm_running(timeout)

    def stop(self, graceful=True, timeout=5, undefine=True):
        def cleanup_addons():
            for chan in self.domain_xmlobject.devices.get_child_node_as_list('channel'):
                if chan.type_ == 'unix':
                    path = chan.source.path_
                    shell.call('rm -f %s' % path)

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
                except Exception as ex:
                    if 'transient domain' not in str(ex):
                        raise

                    # the vm is in transient state, do our best to kill it
                    pid = linux.find_process_by_cmdline(['qemu', self.uuid])
                    if not pid:
                        logger.warn('cannot find the PID of the transient VM[uuid:%s]' % self.uuid)
                        raise

                    # force to kill the VM
                    shell.call('kill -9 %s' % pid)

            try:
                self.domain.undefineFlags(
                    libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE | libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA)
            except libvirt.libvirtError:
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

        do_destroy = True
        if graceful:
            if linux.wait_callback_success(loop_shutdown, None, timeout=60):
                do_destroy = False

        iscsi_cleanup()

        if do_destroy:
            if not linux.wait_callback_success(loop_destroy, None, timeout=60):
                raise kvmagent.KvmError('failed to destroy vm, timeout after 60 secs')

        cleanup_addons()
        if not linux.wait_callback_success(loop_undefine, None, timeout=60):
            raise kvmagent.KvmError('failed to undefine vm, timeout after 60 secs')

    def destroy(self):
        self.stop(graceful=False)

    def suspend(self, timeout=5):
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
            raise kvmagent.KvmError('failed to resume vm ,timeout after 60 secs')

    def harden_console(self, mgmt_ip):
        id = self.domain_xmlobject.metadata.internalId.text_
        vir = VncPortIptableRule()
        vir.vm_internal_id = id
        vir.delete()

        vir.host_ip = mgmt_ip
        vir.port = self.get_console_port()
        vir.apply()

    def get_console_port(self):
        for g in self.domain_xmlobject.devices.get_child_node_as_list('graphics'):
            if g.type_ == 'vnc' or g.type_ == 'spice':
                return g.port_

    def get_console_protocol(self):
        for g in self.domain_xmlobject.devices.get_child_node_as_list('graphics'):
            if g.type_ == 'vnc' or g.type_ == 'spice':
                return g.type_

        raise kvmagent.KvmError['no vnc console defined for vm[uuid:%s]' % self.uuid]

    def attach_data_volume(self, volume, addons):
        self._wait_vm_run_until_seconds(10)
        self.timeout_object.wait_until_object_timeout('detach-volume-%s' % self.uuid)
        self._attach_data_volume(volume, addons)
        self.timeout_object.put('attach-volume-%s' % self.uuid, 10)

    def _attach_data_volume(self, volume, addons):
        if volume.deviceId >= len(self.DEVICE_LETTERS):
            err = "vm[uuid:%s] exceeds max disk limit, device id[%s], but only 24 allowed" % (
            self.uuid, volume.deviceId)
            logger.warn(err)
            raise kvmagent.KvmError(err)

        def volume_qos(volume_xml_obj):
            if not addons:
                return

            vol_qos = addons['VolumeQos']
            if not vol_qos:
                return

            qos = vol_qos[volume.volumeUuid]
            if not qos:
                return

            if not qos.totalBandwidth and not qos.totalIops:
                return

            iotune = e(volume_xml_obj, 'iotune')
            if qos.totalBandwidth:
                e(iotune, 'total_bytes_sec', str(qos.totalBandwidth))
            if qos.totalIops:
                e(iotune, 'total_iops_sec', str(qos.totalIops))

        def filebased_volume():
            disk = etree.Element('disk', attrib={'type': 'file', 'device': 'disk'})
            e(disk, 'driver', None, {'name': 'qemu', 'type': 'qcow2', 'cache': volume.cacheMode})
            e(disk, 'source', None, {'file': volume.installPath})

            if volume.useVirtioSCSI:
                e(disk, 'target', None, {'dev': 'sd%s' % self.DEVICE_LETTERS[volume.deviceId], 'bus': 'scsi'})
                e(disk, 'wwn', volume.wwn)
                e(disk, 'shareable')
            else:
                if volume.useVirtio:
                    e(disk, 'target', None, {'dev': 'vd%s' % self.DEVICE_LETTERS[volume.deviceId], 'bus': 'virtio'})
                else:
                    e(disk, 'target', None, {'dev': 'hd%s' % self.DEVICE_LETTERS[volume.deviceId], 'bus': 'ide'})

            volume_qos(disk)
            return etree.tostring(disk)

        def iscsibased_volume():
            def virtio_iscsi():
                vi = VirtioIscsi()
                portal, vi.target, vi.lun = volume.installPath.lstrip('iscsi://').split('/')
                vi.server_hostname, vi.server_port = portal.split(':')
                vi.device_letter = self.DEVICE_LETTERS[volume.deviceId]
                vi.volume_uuid = volume.volumeUuid
                vi.chap_username = volume.chapUsername
                vi.chap_password = volume.chapPassword
                volume_qos(vi)
                return etree.tostring(vi.to_xmlobject())

            def blk_iscsi():
                bi = BlkIscsi()
                portal, bi.target, bi.lun = volume.installPath.lstrip('iscsi://').split('/')
                bi.server_hostname, bi.server_port = portal.split(':')
                bi.device_letter = self.DEVICE_LETTERS[volume.deviceId]
                bi.volume_uuid = volume.volumeUuid
                bi.chap_username = volume.chapUsername
                bi.chap_password = volume.chapPassword
                volume_qos(bi)
                return etree.tostring(bi.to_xmlobject())

            if volume.useVirtio:
                return virtio_iscsi()
            else:
                return blk_iscsi()

        def ceph_volume():
            def virtoio_ceph():
                vc = VirtioCeph()
                vc.volume = volume
                vc.dev_letter = self.DEVICE_LETTERS[volume.deviceId]
                xml_obj = vc.to_xmlobject()
                volume_qos(xml_obj)
                return etree.tostring(xml_obj)

            def blk_ceph():
                ic = IdeCeph()
                ic.volume = volume
                ic.dev_letter = self.DEVICE_LETTERS[volume.deviceId]
                xml_obj = ic.to_xmlobject()
                volume_qos(xml_obj)
                return etree.tostring(xml_obj)

            def virtio_scsi_ceph():
                sc = VirtioSCSICeph()
                sc.volume = volume
                sc.dev_letter = self.DEVICE_LETTERS[volume.deviceId]
                xml_obj = sc.to_xmlobject()
                volume_qos(xml_obj)
                return etree.tostring(xml_obj)

            if volume.useVirtioSCSI:
                return virtio_scsi_ceph()
            else:
                if volume.useVirtio:
                    return virtoio_ceph()
                else:
                    return blk_ceph()

        def fusionstor_volume():
            def virtoio_fusionstor():
                vc = VirtioFusionstor()
                vc.volume = volume
                vc.dev_letter = self.DEVICE_LETTERS[volume.deviceId]
                volume_qos(vc)
                return etree.tostring(vc.to_xmlobject())

            def blk_fusionstor():
                ic = IdeFusionstor()
                ic.volume = volume
                ic.dev_letter = self.DEVICE_LETTERS[volume.deviceId]
                volume_qos(ic)
                return etree.tostring(ic.to_xmlobject())

            if volume.useVirtio:
                return virtoio_fusionstor()
            else:
                return blk_fusionstor()

        if volume.deviceType == 'iscsi':
            xml = iscsibased_volume()
        elif volume.deviceType == 'file':
            xml = filebased_volume()
        elif volume.deviceType == 'ceph':
            xml = ceph_volume()
        elif volume.deviceType == 'fusionstor':
            xml = fusionstor_volume()
        else:
            raise Exception('unsupported volume deviceType[%s]' % volume.deviceType)

        logger.debug('attaching volume[%s] to vm[uuid:%s]:\n%s' % (volume.installPath, self.uuid, xml))
        try:
            # libvirt has a bug that if attaching volume just after vm created, it likely fails. So we retry three time here
            @linux.retry(times=3, sleep_time=5)
            def attach():
                def wait_for_attach(_):
                    me = get_vm_by_uuid(self.uuid)
                    for disk in me.domain_xmlobject.devices.get_child_node_as_list('disk'):
                        if volume.deviceType == 'iscsi':
                            if volume.useVirtio:
                                if xmlobject.has_element(disk,
                                                         'source') and disk.source.name__ and disk.source.name_ in volume.installPath:
                                    return True
                            else:
                                if xmlobject.has_element(disk,
                                                         'source') and disk.source.dev__ and volume.volumeUuid in disk.source.dev_:
                                    return True
                        elif volume.deviceType == 'file':
                            if xmlobject.has_element(disk,
                                                     'source') and disk.source.file__ and disk.source.file_ == volume.installPath:
                                return True
                        elif volume.deviceType == 'ceph':
                            if xmlobject.has_element(disk,
                                                     'source') and disk.source.name__ and disk.source.name_ in volume.installPath:
                                return True
                        elif volume.deviceType == 'fusionstor':
                            if xmlobject.has_element(disk,
                                                     'source') and disk.source.name__ and disk.source.name_ in volume.installPath:
                                return True

                    logger.debug('volume[%s] is still in process of attaching, wait it' % volume.installPath)
                    return False

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
            else:
                err = 'unable to attach the volume[%s] to vm[uuid: %s], %s.' % (volume.volumeUuid, self.uuid, err)
            logger.warn(linux.get_exception_stacktrace())
            raise kvmagent.KvmError(err)

    def detach_data_volume(self, volume):
        self._wait_vm_run_until_seconds(10)
        self.timeout_object.wait_until_object_timeout('attach-volume-%s' % self.uuid)
        self._detach_data_volume(volume)
        self.timeout_object.put('detach-volume-%s' % self.uuid, 10)

    def _detach_data_volume(self, volume):
        assert volume.deviceId != 0, 'how can root volume gets detached???'
        target_disk = None

        def get_disk_name():
            if volume.deviceType == 'iscsi':
                fmt = 'sd%s'
            elif volume.deviceType in ['file', 'ceph', 'fusionstor']:
                if volume.useVirtioSCSI:
                    fmt = 'sd%s'
                else:
                    if volume.useVirtio:
                        fmt = 'vd%s'
                    else:
                        fmt = 'hd%s'
            else:
                raise Exception('unsupported deviceType[%s]' % volume.deviceType)

            return fmt % self.DEVICE_LETTERS[volume.deviceId]

        disk_name = get_disk_name()
        for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
            if disk.target.dev_ == disk_name:
                target_disk = disk
                break

        if not target_disk:
            raise kvmagent.KvmError('unable to find data volume[%s] on vm[uuid:%s]' % (disk_name, self.uuid))

        xmlstr = target_disk.dump()
        logger.debug('detaching volume from vm[uuid:%s]:\n%s' % (self.uuid, xmlstr))
        try:
            # libvirt has a bug that if detaching volume just after vm created, it likely fails. So we retry three time here
            @linux.retry(times=3, sleep_time=5)
            def detach():
                def wait_for_detach(_):
                    me = get_vm_by_uuid(self.uuid)
                    for disk in me.domain_xmlobject.devices.get_child_node_as_list('disk'):
                        if volume.deviceType == 'file':
                            if xmlobject.has_element(disk,
                                                     'source') and disk.source.file__ and disk.source.file_ == volume.installPath:
                                logger.debug(
                                    'volume[%s] is still in process of detaching, wait for it' % volume.installPath)
                                return False
                        elif volume.deviceType == 'iscsi':
                            if volume.useVirtio:
                                if xmlobject.has_element(disk,
                                                         'source') and disk.source.name__ and disk.source.name_ in volume.installPath:
                                    logger.debug(
                                        'volume[%s] is still in process of detaching, wait for it' % volume.installPath)
                                    return False
                            else:
                                if xmlobject.has_element(disk,
                                                         'source') and disk.source.dev__ and volume.volumeUuid in disk.source.dev_:
                                    logger.debug(
                                        'volume[%s] is still in process of detaching, wait for it' % volume.installPath)
                                    return False
                        elif volume.deviceType == 'ceph':
                            if xmlobject.has_element(disk,
                                                     'source') and disk.source.name__ and disk.source.name_ in volume.installPath:
                                logger.debug(
                                    'volume[%s] is still in process of detaching, wait for it' % volume.installPath)
                                return False
                        elif volume.deviceType == 'fusionstor':
                            if xmlobject.has_element(disk,
                                                     'source') and disk.source.name__ and disk.source.name_ in volume.installPath:
                                logger.debug(
                                    'volume[%s] is still in process of detaching, wait for it' % volume.installPath)
                                return False

                    return True

                try:
                    self.domain.detachDeviceFlags(xmlstr, libvirt.VIR_DOMAIN_AFFECT_LIVE)

                    if not linux.wait_callback_success(wait_for_detach, None, 5, 1):
                        raise Exception("unable to detach the volume[uuid:%s] from the vm[uuid:%s];"
                                        "it's still attached after 5 seconds" %
                                        (volume.volumeUuid, self.uuid))
                except:
                    # check one more time
                    if not wait_for_detach(None):
                        raise

            detach()

            def logout_iscsi():
                BlkIscsi.logout_portal(target_disk.source.dev_)

            if volume.deviceType == 'iscsi':
                if not volume.useVirtio:
                    logout_iscsi()


        except libvirt.libvirtError as ex:
            vm = get_vm_by_uuid(self.uuid)
            logger.warn('vm dump: %s' % vm.domain_xml)
            logger.warn(linux.get_exception_stacktrace())
            raise kvmagent.KvmError(
                'unable to detach volume[%s] from vm[uuid:%s], %s' % (volume.installPath, self.uuid, str(ex)))

    def _get_back_file(self, volume):
        ret = shell.call('qemu-img info %s' % volume)
        for l in ret.split('\n'):
            l = l.strip(' \n\t\r')
            if l == '':
                continue

            k, v = l.split(':')
            if k == 'backing file':
                return v.strip()

        return None

    def _get_backfile_chain(self, current):
        back_files = []

        def get_back_files(volume):
            back_file = self._get_back_file(volume)
            if back_file is None:
                return

            back_files.append(back_file)
            get_back_files(back_file)

        get_back_files(current)
        return back_files

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
        except Exception as e:
            logger.warn(linux.get_exception_stacktrace())
            return False

        if wait_for_job_clean:
            job_ended = not status
        else:
            job_ended = cur == end

        return not job_ended

    def _get_target_disk(self, device_id):

        def find(disk_name):
            for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
                if disk.target.dev_ == disk_name:
                    return disk

            return None

        disk_name = 'vd%s' % self.DEVICE_LETTERS[device_id]
        target_disk = find(disk_name)

        if not target_disk:
            logger.debug('%s is not found on the vm[uuid:%s]' % (disk_name, self.uuid))
            disk_name = 'sd%s' % self.DEVICE_LETTERS[device_id]
            target_disk = find(disk_name)

        if not target_disk:
            logger.debug('%s is not found on the vm[uuid:%s]' % (disk_name, self.uuid))
            disk_name = 'hd%s' % self.DEVICE_LETTERS[device_id]
            target_disk = find(disk_name)

        if not target_disk:
            logger.debug('%s is not found on the vm[uuid:%s]' % (disk_name, self.uuid))
            raise kvmagent.KvmError('unable to find volume[device ID:%s] on vm[uuid:%s]' % (device_id, self.uuid))

        return target_disk, disk_name

    def take_volume_snapshot(self, device_id, install_path, full_snapshot=False):
        target_disk, disk_name = self._get_target_disk(device_id)
        snapshot_dir = os.path.dirname(install_path)
        if not os.path.exists(snapshot_dir):
            os.makedirs(snapshot_dir)

        previous_install_path = target_disk.source.file_
        back_file_len = len(self._get_backfile_chain(previous_install_path))
        # for RHEL, base image's back_file_len == 1; for ubuntu back_file_len == 0
        first_snapshot = full_snapshot and (back_file_len == 1 or back_file_len == 0)

        def take_delta_snapshot():
            snapshot = etree.Element('domainsnapshot')
            disks = e(snapshot, 'disks')
            d = e(disks, 'disk', None, attrib={'name': disk_name, 'snapshot': 'external', 'type': 'file'})
            e(d, 'source', None, attrib={'file': install_path})
            e(d, 'driver', None, attrib={'type': 'qcow2'})

            # QEMU 2.3 default create snapshots on all devices
            # but we only need for one
            for disk in self.domain_xmlobject.devices.get_child_node_as_list('disk'):
                if disk.target.dev_ != disk_name:
                    e(disks, 'disk', None, attrib={'name': disk.target.dev_, 'snapshot': 'no'})

            xml = etree.tostring(snapshot)
            logger.debug('creating snapshot for vm[uuid:{0}] volume[id:{1}]:\n{2}'.format(self.uuid, device_id, xml))
            snap_flags = libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY | libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_NO_METADATA

            try:
                self.domain.snapshotCreateXML(xml, snap_flags)
                return previous_install_path, install_path
            except libvirt.libvirtError as ex:
                logger.warn(linux.get_exception_stacktrace())
                raise kvmagent.KvmError(
                    'unable to take snapshot of vm[uuid:{0}] volume[id:{1}], {2}'.format(self.uuid, device_id, str(ex)))

        def take_full_snapshot():
            logger.debug('start rebasing to make a full snapshot')
            self.domain.blockRebase(disk_name, None, 0, 0)

            logger.debug('rebasing full snapshot is in processing')

            def wait_job(_):
                logger.debug('full snapshot is waiting for blockRebase job completion')
                return not self._wait_for_block_job(disk_name, abort_on_error=True)

            if not linux.wait_callback_success(wait_job, timeout=21600, ignore_exception_in_callback=True):
                raise kvmagent.KvmError('live full snapshot failed')

            return take_delta_snapshot()

        if first_snapshot:
            # the first snapshot is always full snapshot
            # at this moment, delta snapshot returns the original volume as full snapshot
            return take_delta_snapshot()

        if full_snapshot:
            return take_full_snapshot()
        else:
            return take_delta_snapshot()

    def migrate(self, cmd):
        current_hostname = shell.call('hostname')
        current_hostname = current_hostname.strip(' \t\n\r')
        if current_hostname == 'localhost.localdomain' or current_hostname == 'localhost':
            # set the hostname, otherwise the migration will fail
            shell.call('hostname %s.zstack.org' % cmd.srcHostIp.replace('.', '-'))

        destHostIp = cmd.destHostIp
        destUrl = "qemu+tcp://{0}/system".format(destHostIp)
        tcpUri = "tcp://{0}".format(destHostIp)
        flag = (libvirt.VIR_MIGRATE_LIVE |
                libvirt.VIR_MIGRATE_PEER2PEER |
                libvirt.VIR_MIGRATE_UNDEFINE_SOURCE |
                libvirt.VIR_MIGRATE_TUNNELLED)

        if cmd.withStorage == 'FullCopy':
            flag |= libvirt.VIR_MIGRATE_NON_SHARED_DISK
        elif cmd.withStorage == 'IncCopy':
            flag |= libvirt.VIR_MIGRATE_NON_SHARED_INC

        try:
            self.domain.migrateToURI(destUrl, flag, None, 0)
        except libvirt.libvirtError as ex:
            logger.warn(linux.get_exception_stacktrace())
            raise kvmagent.KvmError('unable to migrate vm[uuid:%s] to %s, %s' % (self.uuid, destUrl, str(ex)))

        try:
            logger.debug('migrating vm[uuid:{0}] to dest url[{1}]'.format(self.uuid, destUrl))
            if not linux.wait_callback_success(self.wait_for_state_change, callback_data=None, timeout=1800):
                raise kvmagent.KvmError('timeout after 1800 seconds')
        except kvmagent.KvmError:
            raise
        except:
            logger.debug(linux.get_exception_stacktrace())

        logger.debug('successfully migrated vm[uuid:{0}] to dest url[{1}]'.format(self.uuid, destUrl))

    def _interface_cmd_to_xml(self, cmd):
        nic = cmd.nic

        interface = etree.Element('interface', attrib={'type': 'bridge'})
        e(interface, 'mac', None, attrib={'address': nic.mac})
        e(interface, 'source', None, attrib={'bridge': nic.bridgeName})
        e(interface, 'target', None, attrib={'dev': nic.nicInternalName})
        e(interface, 'alias', None, {'name': 'net%s' % nic.nicInternalName.split('.')[1]})
        if nic.useVirtio:
            e(interface, 'model', None, attrib={'type': 'virtio'})
        else:
            e(interface, 'model', None, attrib={'type': 'e1000'})

        def nic_qos():
            if not cmd.addons:
                return

            qos = cmd.addons['NicQos']
            if not qos:
                return

            if not qos.outboundBandwidth and not qos.inboundBandwidth:
                return

            bandwidth = e(interface, 'bandwidth')
            if qos.outboundBandwidth:
                e(bandwidth, 'outbound', None, {'average': str(qos.outboundBandwidth)})
            if qos.inboundBandwidth:
                e(bandwidth, 'inbound', None, {'average': str(qos.inboundBandwidth)})

        nic_qos()

        return etree.tostring(interface)

    def _wait_vm_run_until_seconds(self, sec):
        vm_pid = linux.find_process_by_cmdline(['kvm', self.uuid])
        if not vm_pid:
            raise Exception('cannot find pid for vm[uuid:%s]' % self.uuid)

        up_time = linux.get_process_up_time_in_second(vm_pid)

        def wait(_):
            return linux.get_process_up_time_in_second(vm_pid) > sec

        if up_time < sec and not linux.wait_callback_success(wait, timeout=60):
            raise Exception("vm[uuid:%s] seems hang, its process[pid:%s] up-time is not increasing after %s seconds" %
                            (self.uuid, vm_pid, 60))

    def attach_iso(self, cmd):
        iso = cmd.iso
        if iso.path.startswith('http'):
            cdrom = etree.Element('disk', {'type': 'network', 'device': 'cdrom'})
            e(cdrom, 'driver', None, {'name': 'qemu', 'type': 'raw'})
            hostname, path = iso.path.lstrip('http://').split('/', 1)
            source = e(cdrom, 'source', None, {'protocol': 'http', 'name': path})
            e(source, 'host', None, {'name': hostname, 'port': '80'})
            e(cdrom, 'target', None, {'dev': 'hdc', 'bus': 'ide'})
            e(cdrom, 'readonly', None)
        elif iso.path.startswith('iscsi'):
            bi = BlkIscsi()
            bi.target = iso.target
            bi.lun = iso.lun
            bi.server_hostname = iso.hostname
            bi.server_port = iso.port
            bi.device_letter = 'hdc'
            bi.volume_uuid = iso.imageUuid
            bi.chap_username = iso.chapUsername
            bi.chap_password = iso.chapPassword
            bi.is_cdrom = True
            cdrom = bi.to_xmlobject()
        elif iso.path.startswith('ceph'):
            ic = IsoCeph()
            ic.iso = iso
            cdrom = ic.to_xmlobject()
        elif iso.path.startswith('fusionstor'):
            ic = IsoFusionstor()
            ic.iso = iso
            cdrom = ic.to_xmlobject()
        else:
            cdrom = etree.Element('disk', {'type': 'file', 'device': 'cdrom'})
            e(cdrom, 'driver', None, {'name': 'qemu', 'type': 'raw'})
            e(cdrom, 'source', None, {'file': iso.path})
            e(cdrom, 'target', None, {'dev': 'hdc', 'bus': 'ide'})
            e(cdrom, 'readonly', None)

        xml = etree.tostring(cdrom)

        logger.debug('attaching ISO to the vm[uuid:%s]:\n%s' % (self.uuid, xml))

        self.domain.updateDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)

        def check(_):
            me = get_vm_by_uuid(self.uuid)
            for disk in me.domain_xmlobject.devices.get_child_node_as_list('disk'):
                if disk.device_ == "cdrom":
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

        cdrom = etree.Element('disk', {'type': 'file', 'device': 'cdrom'})
        e(cdrom, 'driver', None, {'name': 'qemu', 'type': 'raw'})
        e(cdrom, 'target', None, {'dev': 'hdc', 'bus': 'ide', 'tray': 'open'})
        e(cdrom, 'readonly', None)

        xml = etree.tostring(cdrom)

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

        def check(_):
            me = get_vm_by_uuid(self.uuid)
            for disk in me.domain_xmlobject.devices.get_child_node_as_list('disk'):
                if disk.device_ == "cdrom" and xmlobject.has_element(disk, 'source'):
                    return False
            return True

        if not linux.wait_callback_success(check, None, 30, 1):
            raise Exception('cannot detach the cdrom from the VM[uuid:%s]. The device is still present after 30s' %
                            self.uuid)

    def hotplug_mem(self, memory_size):

        mem_size = (memory_size - self.get_memory()) / 1024
        xml = "<memory model='dimm'><target><size unit='KiB'>%d</size><node>0</node></target></memory>" % mem_size
        logger.debug('hot plug memory: %d KiB' % mem_size)
        try:
            self.domain.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_AFFECT_CONFIG)
        except libvirt.libvirtError as ex:
            err = str(ex)
            logger.warn('unable to hotplug memory in vm[uuid:%s], %s' % (self.uuid, err))
            raise kvmagent.KvmError(err)
        return

    def hotplug_cpu(self, cpu_num):

        logger.debug('set cpus: %d cpus' % cpu_num)
        try:
            self.domain.setVcpusFlags(cpu_num, libvirt.VIR_DOMAIN_AFFECT_LIVE | libvirt.VIR_DOMAIN_AFFECT_CONFIG)
        except libvirt.libvirtError as ex:
            err = str(ex)
            logger.warn('unable to set cpus in vm[uuid:%s], %s' % (self.uuid, err))
            raise kvmagent.KvmError(err)
        return

    @linux.retry(times=3, sleep_time=5)
    def _attach_nic(self, cmd):
        def check_device(_):
            self.refresh()
            for iface in self.domain_xmlobject.devices.get_child_node_as_list('interface'):
                if iface.mac.address_ == cmd.nic.mac:
                    s = shell.ShellCmd('ip link | grep %s > /dev/null' % cmd.nic.nicInternalName)
                    s(False)
                    return s.return_code == 0

            return False

        try:
            if check_device(None):
                return

            xml = self._interface_cmd_to_xml(cmd)
            logger.debug('attaching nic:\n%s' % xml)
            if self.state == self.VM_STATE_RUNNING or self.state == self.VM_STATE_PAUSED:
                self.domain.attachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
            else:
                self.domain.attachDevice(xml)

            if not linux.wait_callback_success(check_device, interval=0.5, timeout=30):
                raise Exception('nic device does not show after 30 seconds')
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
            else:
                err = 'unable to attach a L3 network to the vm[uuid:%s], %s' % (self.uuid, err)
            raise kvmagent.KvmError(err)

        # in 10 seconds, no detach-nic operation can be performed,
        # work around libvirt bug
        self.timeout_object.put('%s-detach-nic' % self.uuid, 10)

    @linux.retry(times=3, sleep_time=5)
    def _detach_nic(self, cmd):
        def check_device(_):
            self.refresh()
            for iface in self.domain_xmlobject.devices.get_child_node_as_list('interface'):
                if iface.mac.address_ == cmd.nic.mac:
                    return False

            s = shell.ShellCmd('ip link | grep %s > /dev/null' % cmd.nic.nicInternalName)
            s(False)
            return s.return_code != 0

        if check_device(None):
            return

        try:
            xml = self._interface_cmd_to_xml(cmd)
            logger.debug('detaching nic:\n%s' % xml)
            if self.state == self.VM_STATE_RUNNING or self.state == self.VM_STATE_PAUSED:
                self.domain.detachDeviceFlags(xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)
            else:
                self.domain.detachDevice(xml)

            if not linux.wait_callback_success(check_device, interval=0.5, timeout=10):
                raise Exception('nic device is still attached after 10 seconds')
        except:
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
        self.timeout_object.put('%s-attach-nic' % self.uuid, 10)

    def _check_qemuga_info(self, info):
        if info:
            for command in info["return"]["supported_commands"]:
                if command["name"] == "guest-set-user-password":
                    if command["enabled"]:
                        return True
        return False

    def _wait_until_qemuga_ready(self, timeout, uuid):
        finish_time = time.time()+(timeout/1000)
        while time.time() < finish_time:
            state = get_all_vm_states().get(uuid)
            if state != Vm.VM_STATE_RUNNING:
                raise kvmagent.KvmError("vm's state is %s, not running" % state)
            ping_json = shell.call('virsh qemu-agent-command %s \'{"execute":"guest-ping"}\'' % self.uuid, False)
            try:
                logger.debug("ping_json: %s" % ping_json)
                if ping_json.find("{\"return\":{}}") != -1:
                    time.sleep(0.5)
                    return True
            except Exception as err:
                logger.warn(err.message)
                # info_json = shell.call('virsh qemu-agent-command %s \'{"execute":"guest-info"}\'' % self.uuid, False)
                # try:
                #     info = jsonobject.loads(info_json)
                #     enable = self._check_qemuga_info(info)
                #     if enable:
                #         return enable
                # except Exception as err:
                #     logger.warn(err.message)
            time.sleep(0.1)
        raise kvmagent.KvmError("qemu-ga is not ready...")

    def _escape_char_password(self, password):
        enscape_str = "\*\#\(\)\<\>\|\"\'\/\\\$\`\&\{\}"
        des = ""
        for c in list(password):
            if c in enscape_str:
                des += "\\"
            des += c
        return des

    def change_vm_password(self, cmd):
        uuid = self.uuid
        # check the vm state first, then choose the method in different way
        state = get_all_vm_states().get(uuid)
        timeout = cmd.timeout
        if not timeout:
            timeout = 60000
        if state == Vm.VM_STATE_RUNNING:
            # before set-user-password, we must check if os ready in the guest
            self._wait_until_qemuga_ready(timeout, uuid)
            # running state: exec virsh set-user-password to connect the qemu-ga
            try:
                escape_password = self._escape_char_password(cmd.accountPerference.accountPassword)
                logger.debug("escape_password is: %s" % escape_password)
                shell.call('virsh set-user-password %s %s %s' % (self.uuid,
                                                             cmd.accountPerference.userAccount,
                                                             escape_password))
            except Exception as e:
                logger.warn(e.message)
                if e.message.find("child process has failed to set user password") > 0:
                    logger.warn('user [%s] not exist!' % cmd.accountPerference.userAccount)
                    raise kvmagent.KvmError('user [%s] not exist!' % cmd.accountPerference.userAccount)
                else:
                    raise e
        else:
            raise kvmagent.KvmError("vm may not be running, cannot connect to qemu-ga")

    def merge_snapshot(self, cmd):
        target_disk, disk_name = self._get_target_disk(cmd.deviceId)

        @linux.retry(times=3, sleep_time=3)
        def do_pull(base, top):
            logger.debug('start block rebase [active: %s, new backing: %s]' % (top, base))

            # Double check (c.f. issue #1323)
            def wait_previous_job(_):
                logger.debug('merge snapshot is checking previous block job')
                return not self._wait_for_block_job(disk_name, abort_on_error=True)

            if not linux.wait_callback_success(wait_previous_job, timeout=21600, ignore_exception_in_callback=True):
                raise kvmagent.KvmError('merge snapshot failed - pending previous block job')

            self.domain.blockRebase(disk_name, base, 0)

            def wait_job(_):
                logger.debug('merging snapshot chain is waiting for blockRebase job completion')
                return not self._wait_for_block_job(disk_name, abort_on_error=True)

            if not linux.wait_callback_success(wait_job, timeout=21600):
                raise kvmagent.KvmError('live merging snapshot chain failed, timeout after 6 hours')

            # Double check (c.f. issue #757)
            if self._get_back_file(top) != base:
                raise kvmagent.KvmError('[bug] live merge snapshot failed')

            logger.debug('end block rebase [active: %s, new backing: %s]' % (top, base))

        if cmd.fullRebase:
            do_pull(None, cmd.destPath)
        else:
            do_pull(cmd.srcPath, cmd.destPath)

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
        use_virtio = cmd.useVirtio
        instanceoffering_onliechange = cmd.instanceOfferingOnlineChange

        elements = {}

        def make_root():
            root = etree.Element('domain')
            root.set('type', 'kvm')
            # self._root.set('type', 'qemu')
            root.set('xmlns:qemu', 'http://libvirt.org/schemas/domain/qemu/1.0')
            elements['root'] = root

        def make_cpu():
            if instanceoffering_onliechange:
                root = elements['root']
                e(root, 'vcpu', '128', {'placement': 'static', 'current': str(cmd.cpuNum)})
                # e(root,'vcpu',str(cmd.cpuNum),{'placement':'static'})
                tune = e(root, 'cputune')
                e(tune, 'shares', str(cmd.cpuSpeed * cmd.cpuNum))
                # enable nested virtualization
                if cmd.nestedVirtualization == 'host-model':
                    cpu = e(root, 'cpu', attrib={'mode': 'host-model'})
                    e(cpu, 'model', attrib={'fallback': 'allow'})
                elif cmd.nestedVirtualization == 'host-passthrough':
                    cpu = e(root, 'cpu', attrib={'mode': 'host-passthrough'})
                    e(cpu, 'model', attrib={'fallback': 'allow'})
                else:
                    cpu = e(root, 'cpu')
                # e(cpu, 'topology', attrib={'sockets': str(cmd.socketNum), 'cores': str(cmd.cpuOnSocket), 'threads': '1'})
                mem = cmd.memory / 1024
                e(cpu, 'topology', attrib={'sockets': str(32), 'cores': str(32), 'threads': '1'})
                numa = e(cpu, 'numa')
                e(numa, 'cell', attrib={'id': '0', 'cpus': '0-127', 'memory': str(mem), 'unit': 'KiB'})
            else:
                root = elements['root']
                # e(root, 'vcpu', '128', {'placement': 'static', 'current': str(cmd.cpuNum)})
                e(root, 'vcpu', str(cmd.cpuNum), {'placement': 'static'})
                tune = e(root, 'cputune')
                e(tune, 'shares', str(cmd.cpuSpeed * cmd.cpuNum))
                # enable nested virtualization
                if cmd.nestedVirtualization == 'host-model':
                    cpu = e(root, 'cpu', attrib={'mode': 'host-model'})
                    e(cpu, 'model', attrib={'fallback': 'allow'})
                elif cmd.nestedVirtualization == 'host-passthrough':
                    cpu = e(root, 'cpu', attrib={'mode': 'host-passthrough'})
                    e(cpu, 'model', attrib={'fallback': 'allow'})
                else:
                    cpu = e(root, 'cpu')
                e(cpu, 'topology',
                  attrib={'sockets': str(cmd.socketNum), 'cores': str(cmd.cpuOnSocket), 'threads': '1'})

        def make_memory():
            root = elements['root']
            mem = cmd.memory / 1024
            if instanceoffering_onliechange:
                e(root, 'maxMemory', str(104857600), {'slots': str(16), 'unit': 'KiB'})
                # e(root,'memory',str(mem),{'unit':'k'})
                e(root, 'currentMemory', str(mem), {'unit': 'k'})
            else:
                e(root, 'memory', str(mem), {'unit': 'k'})
                e(root, 'currentMemory', str(mem), {'unit': 'k'})

        def make_os():
            root = elements['root']
            os = e(root, 'os')
            e(os, 'type', 'hvm', attrib={'machine': 'pc'})
            for boot_dev in cmd.bootDev:
                e(os, 'boot', None, {'dev': boot_dev})
            e(os, 'bootmenu', attrib={'enable': 'yes'})

        def make_features():
            root = elements['root']
            features = e(root, 'features')
            for f in ['acpi', 'apic', 'pae']:
                e(features, f)

        def make_devices():
            root = elements['root']
            devices = e(root, 'devices')
            if cmd.addons and cmd.addons['qemuPath']:
                e(devices, 'emulator', cmd.addons['qemuPath'])
            else:
                e(devices, 'emulator', kvmagent.get_qemu_path())
            e(devices, 'input', None, {'type': 'tablet', 'bus': 'usb'})
            elements['devices'] = devices

        def make_cdrom():
            devices = elements['devices']
            if not cmd.bootIso:
                cdrom = e(devices, 'disk', None, {'type': 'file', 'device': 'cdrom'})
                e(cdrom, 'driver', None, {'name': 'qemu', 'type': 'raw'})
                e(cdrom, 'target', None, {'dev': 'hdc', 'bus': 'ide'})
                e(cdrom, 'readonly', None)
                return

            iso = cmd.bootIso
            if iso.path.startswith('http'):
                cdrom = e(devices, 'disk', None, {'type': 'network', 'device': 'cdrom'})
                e(cdrom, 'driver', None, {'name': 'qemu', 'type': 'raw'})
                hostname, path = iso.path.lstrip('http://').split('/', 1)
                source = e(cdrom, 'source', None, {'protocol': 'http', 'name': path})
                e(source, 'host', None, {'name': hostname, 'port': '80'})
                e(cdrom, 'target', None, {'dev': 'hdc', 'bus': 'ide'})
                e(cdrom, 'readonly', None)
            elif iso.path.startswith('iscsi'):
                bi = BlkIscsi()
                bi.target = iso.target
                bi.lun = iso.lun
                bi.server_hostname = iso.hostname
                bi.server_port = iso.port
                bi.device_letter = 'hdc'
                bi.volume_uuid = iso.imageUuid
                bi.chap_username = iso.chapUsername
                bi.chap_password = iso.chapPassword
                bi.is_cdrom = True
                devices.append(bi.to_xmlobject())
            elif iso.path.startswith('ceph'):
                ic = IsoCeph()
                ic.iso = iso
                devices.append(ic.to_xmlobject())
            elif iso.path.startswith('fusionstor'):
                ic = IsoFusionstor()
                ic.iso = iso
                devices.append(ic.to_xmlobject())
            else:
                cdrom = e(devices, 'disk', None, {'type': 'file', 'device': 'cdrom'})
                e(cdrom, 'driver', None, {'name': 'qemu', 'type': 'raw'})
                e(cdrom, 'source', None, {'file': iso.path})
                e(cdrom, 'target', None, {'dev': 'hdc', 'bus': 'ide'})
                e(cdrom, 'readonly', None)

        def make_volumes():
            devices = elements['devices']
            volumes = [cmd.rootVolume]
            volumes.extend(cmd.dataVolumes)

            def filebased_volume(dev_letter, v):
                disk = etree.Element('disk', {'type': 'file', 'device': 'disk', 'snapshot': 'external'})
                e(disk, 'driver', None, {'name': 'qemu', 'type': 'qcow2', 'cache': v.cacheMode})
                e(disk, 'source', None, {'file': v.installPath})
                if v.useVirtioSCSI:
                    e(disk, 'target', None, {'dev': 'sd%s' % dev_letter, 'bus': 'scsi'})
                    e(disk, 'wwn', v.wwn)
                    e(disk, 'shareable')
                    return disk

                if v.useVirtio:
                    e(disk, 'target', None, {'dev': 'vd%s' % dev_letter, 'bus': 'virtio'})
                else:
                    e(disk, 'target', None, {'dev': 'sd%s' % dev_letter, 'bus': 'ide'})
                return disk

            def iscsibased_volume(dev_letter, virtio):
                def blk_iscsi():
                    bi = BlkIscsi()
                    portal, bi.target, bi.lun = v.installPath.lstrip('iscsi://').split('/')
                    bi.server_hostname, bi.server_port = portal.split(':')
                    bi.device_letter = dev_letter
                    bi.volume_uuid = v.volumeUuid
                    bi.chap_username = v.chapUsername
                    bi.chap_password = v.chapPassword

                    return bi.to_xmlobject()

                def virtio_iscsi():
                    vi = VirtioIscsi()
                    portal, vi.target, vi.lun = v.installPath.lstrip('iscsi://').split('/')
                    vi.server_hostname, vi.server_port = portal.split(':')
                    vi.device_letter = dev_letter
                    vi.volume_uuid = v.volumeUuid
                    vi.chap_username = v.chapUsername
                    vi.chap_password = v.chapPassword

                    return vi.to_xmlobject()

                if virtio:
                    return virtio_iscsi()
                else:
                    return blk_iscsi()

            def ceph_volume(dev_letter, virtio):
                def ceph_virtio():
                    vc = VirtioCeph()
                    vc.volume = v
                    vc.dev_letter = dev_letter
                    return vc.to_xmlobject()

                def ceph_blk():
                    ic = IdeCeph()
                    ic.volume = v
                    ic.dev_letter = dev_letter
                    return ic.to_xmlobject()

                if virtio:
                    return ceph_virtio()
                else:
                    return ceph_blk()

            def fusionstor_volume(dev_letter, virtio):
                def fusionstor_virtio():
                    vc = VirtioFusionstor()
                    vc.volume = v
                    vc.dev_letter = dev_letter
                    return vc.to_xmlobject()

                def fusionstor_blk():
                    ic = IdeFusionstor()
                    ic.volume = v
                    ic.dev_letter = dev_letter
                    return ic.to_xmlobject()

                if virtio:
                    return fusionstor_virtio()
                else:
                    return fusionstor_blk()

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

            for v in volumes:
                if v.deviceId >= len(Vm.DEVICE_LETTERS):
                    err = "%s exceeds max disk limit, it's %s but only 26 allowed" % v.deviceId
                    logger.warn(err)
                    raise kvmagent.KvmError(err)

                dev_letter = Vm.DEVICE_LETTERS[v.deviceId]
                if v.deviceType == 'file':
                    vol = filebased_volume(dev_letter, v)
                elif v.deviceType == 'iscsi':
                    vol = iscsibased_volume(dev_letter, v.useVirtio)
                elif v.deviceType == 'ceph':
                    vol = ceph_volume(dev_letter, v.useVirtio)
                elif v.deviceType == 'fusionstor':
                    vol = fusionstor_volume(dev_letter, v.useVirtio)
                else:
                    raise Exception('unknown volume deivceType: %s' % v.deviceType)

                assert vol is not None, 'vol cannot be None'
                volume_qos(vol)
                devices.append(vol)

        def make_nics():
            if not cmd.nics:
                return

            def nic_qos(nic_xml_object):
                if not cmd.addons:
                    return

                nqos = cmd.addons['NicQos']
                if not nqos:
                    return

                qos = nqos[nic.uuid]
                if not qos:
                    return

                if not qos.outboundBandwidth and not qos.inboundBandwidth:
                    return

                bandwidth = e(nic_xml_object, 'bandwidth')
                if qos.outboundBandwidth:
                    e(bandwidth, 'outbound', None, {'average': str(qos.outboundBandwidth)})
                if qos.inboundBandwidth:
                    e(bandwidth, 'inbound', None, {'average': str(qos.inboundBandwidth)})

            devices = elements['devices']
            for nic in cmd.nics:
                interface = e(devices, 'interface', None, {'type': 'bridge'})
                e(interface, 'mac', None, {'address': nic.mac})
                e(interface, 'alias', None, {'name': 'net%s' % nic.nicInternalName.split('.')[1]})
                e(interface, 'source', None, {'bridge': nic.bridgeName})
                if use_virtio:
                    e(interface, 'model', None, {'type': 'virtio'})
                else:
                    e(interface, 'model', None, {'type': 'e1000'})
                e(interface, 'target', None, {'dev': nic.nicInternalName})

                nic_qos(interface)

        def make_meta():
            root = elements['root']
            e(root, 'name', cmd.vmInstanceUuid)
            e(root, 'uuid', uuidhelper.to_full_uuid(cmd.vmInstanceUuid))
            e(root, 'description', cmd.vmName)
            e(root, 'clock', None, {'offset': cmd.clock})
            e(root, 'on_poweroff', 'destroy')
            e(root, 'on_crash', 'restart')
            e(root, 'on_reboot', 'restart')
            meta = e(root, 'metadata')
            e(meta, 'zstack', 'True')
            e(meta, 'internalId', str(cmd.vmInternalId))
            e(meta, 'hostManagementIp', str(cmd.hostManagementIp))

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
            spice = e(devices, 'graphics', None, {'type': 'spice', 'port': '5900', 'autoport': 'yes'})
            e(spice, "listen", None, {'type': 'address', 'address': '0.0.0.0'})

        def make_graphic_console():
            if cmd.consoleMode == 'spice':
                make_spice()
            else:
                make_vnc()

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

        def make_balloon_memory():
            devices = elements['devices']
            b = e(devices, 'memballoon', None, {'model': 'virtio'})
            e(b, 'stats', None, {'period': '10'})

        def make_console():
            devices = elements['devices']
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

        make_root()
        make_meta()
        make_cpu()
        make_memory()
        make_os()
        make_features()
        make_devices()
        make_nics()
        make_volumes()
        make_cdrom()
        make_graphic_console()
        make_addons()
        make_balloon_memory()
        make_console()
        make_sec_label()
        make_controllers()

        root = elements['root']
        xml = etree.tostring(root)

        vm = Vm()
        vm.uuid = cmd.vmInstanceUuid
        vm.domain_xml = xml
        vm.domain_xmlobject = xmlobject.loads(xml)
        return vm


class VmPlugin(kvmagent.KvmAgent):
    KVM_START_VM_PATH = "/vm/start"
    KVM_STOP_VM_PATH = "/vm/stop"
    KVM_SUSPEND_VM_PATH = "/vm/suspend"
    KVM_RESUME_VM_PATH = "/vm/resume"
    KVM_REBOOT_VM_PATH = "/vm/reboot"
    KVM_DESTROY_VM_PATH = "/vm/destroy"
    KVM_CHANGE_CPUMEM_PATH = "/vm/changecpumem"
    KVM_GET_CONSOLE_PORT_PATH = "/vm/getvncport"
    KVM_VM_SYNC_PATH = "/vm/vmsync"
    KVM_ATTACH_VOLUME = "/vm/attachdatavolume"
    KVM_DETACH_VOLUME = "/vm/detachdatavolume"
    KVM_MIGRATE_VM_PATH = "/vm/migrate"
    KVM_TAKE_VOLUME_SNAPSHOT_PATH = "/vm/volume/takesnapshot"
    KVM_MERGE_SNAPSHOT_PATH = "/vm/volume/mergesnapshot"
    KVM_LOGOUT_ISCSI_TARGET_PATH = "/iscsi/target/logout"
    KVM_LOGIN_ISCSI_TARGET_PATH = "/iscsi/target/login"
    KVM_ATTACH_NIC_PATH = "/vm/attachnic"
    KVM_DETACH_NIC_PATH = "/vm/detachnic"
    KVM_CREATE_SECRET = "/vm/createcephsecret"
    KVM_ATTACH_ISO_PATH = "/vm/iso/attach"
    KVM_DETACH_ISO_PATH = "/vm/iso/detach"
    KVM_VM_CHECK_STATE = "/vm/checkstate"
    KVM_VM_CHANGE_PASSWORD_PATH = "/vm/changepasswd"
    KVM_VM_SET_ROOT_PASSWORD_PATH = "/vm/setrootpasswd"
    KVM_HARDEN_CONSOLE_PATH = "/vm/console/harden"
    KVM_DELETE_CONSOLE_FIREWALL_PATH = "/vm/console/deletefirewall"

    VM_OP_START = "start"
    VM_OP_STOP = "stop"
    VM_OP_REBOOT = "reboot"
    VM_OP_MIGRATE = "migrate"
    VM_OP_DESTROY = "destroy"
    VM_OP_SUSPEND = "suspend"
    VM_OP_RESUME = "resume"

    timeout_object = linux.TimeoutObject()
    queue = Queue.Queue()

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

    def _start_vm(self, cmd):
        try:
            vm = get_vm_by_uuid(cmd.vmInstanceUuid)
        except kvmagent.KvmError:
            vm = None

        try:
            if vm:
                if vm.state == Vm.VM_STATE_RUNNING:
                    raise kvmagent.KvmError(
                        'vm[uuid:%s, name:%s] is already running' % (cmd.vmInstanceUuid, vm.get_name()))
                else:
                    vm.destroy()

            vm = Vm.from_StartVmCmd(cmd)
            vm.start(cmd.timeout)
        except libvirt.libvirtError as e:
            logger.warn(linux.get_exception_stacktrace())
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
        rsp = kvmagent.AgentResponse()

        vm = get_vm_by_uuid(cmd.vmUuid)
        vm.attach_nic(cmd)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def detach_nic(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = kvmagent.AgentResponse()

        vm = get_vm_by_uuid(cmd.vmUuid)
        vm.detach_nic(cmd)

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
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def check_vm_state(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        states = get_all_vm_states()
        rsp = CheckVmStateRsp()
        for uuid in cmd.vmUuids:
            s = states.get(uuid)
            if not s:
                s = Vm.VM_STATE_SHUTDOWN
            rsp.states[uuid] = s
        return jsonobject.dumps(rsp)

    def _change_stopped_vm_password(self, cmd):
        if not cmd.qcowFile:
            raise kvmagent.KvmError("vm is stopped or created, cmd must contain qcowFile parameter!")
            # shutdown state: inject password with locale scriptss
        #        zstack_home = os.path.expanduser('~zstack')
        #        logger.debug('zstack_home: %s' % zstack_home)
        #        passwd_script_path = os.path.join(zstack_home,"imagestore","qemu-ga","generate-passwd.sh")
        #        shell.call('%s %s %s %s' % (passwd_script_path, cmd.accountPerference.userAccount, \
        #                cmd.accountPerference.accountPassword, cmd.qcowFile))
        chp = generate_passwd.ChangePasswd()
        chp.password = cmd.accountPerference.accountPassword
        chp.account = cmd.accountPerference.userAccount
        chp.image = cmd.qcowFile
        if not chp.generate_passwd():
            raise kvmagent.KvmError('inject passwd failed.')

    @kvmagent.replyerror
    def set_root_password(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        # inject the root password
        rsp = SetRootPasswordRsp()
        try:
            self._change_stopped_vm_password(cmd)
        except Exception as e:
            logger.warn("catch exception while change stopped vm")
            rsp.error = str(e)
            rsp.success = False
        rsp.accountPerference = cmd.accountPerference
        rsp.accountPerference.accountPassword = "******"
        rsp.qcowFile = cmd.qcowFile
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def change_vm_password(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ChangeVmPasswordRsp()
        vm = get_vm_by_uuid(cmd.accountPerference.vmUuid, False)
        logger.debug('get vmUuid: %s' % cmd.accountPerference.vmUuid)
        try:
            if not vm:
                raise kvmagent.KvmError('vm is not in running state.')
            else:
                vm.change_vm_password(cmd)
        except kvmagent.KvmError as e:
            rsp.error = str(e)
            rsp.success = False
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

    @kvmagent.replyerror
    def vm_sync(self, req):
        rsp = VmSyncResponse()
        # vms = get_running_vms()
        # running_vms = {}
        # for vm in vms:
        #     if vm.state == Vm.VM_STATE_RUNNING:
        #         running_vms[vm.uuid] = Vm.VM_STATE_RUNNING
        #     else:
        #         try:
        #             logger.debug('VM[uuid:%s] is in state of %s, destroy it' % (vm.uuid, vm.state))
        #             vm.destroy()
        #         except:
        #             logger.warn(linux.get_exception_stacktrace())
        #
        # rsp.states = running_vms
        rsp.states = get_all_vm_states()
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def change_cpumem(self, req):
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

    @kvmagent.replyerror
    def get_console_port(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVncPortResponse()
        try:
            vm = get_vm_by_uuid(cmd.vmUuid)
            port = vm.get_console_port()
            rsp.port = port
            rsp.protocol = vm.get_console_protocol()
            logger.debug('successfully get vnc port[%s] of vm[uuid:%s]' % (port, cmd.uuid))
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    def _stop_vm(self, cmd):
        try:
            vm = get_vm_by_uuid(cmd.uuid)
            type = cmd.type
        except kvmagent.KvmError as e:
            logger.debug(linux.get_exception_stacktrace())
            logger.debug('however, the stop operation is still considered as success')
            return
        if str(type) == "cold":
            vm.stop(graceful=False)

        else:
            vm.stop(timeout=cmd.timeout / 2)

    @kvmagent.replyerror
    def stop_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = StopVmResponse()
        try:
            self._record_operation(cmd.uuid, self.VM_OP_STOP)

            self._stop_vm(cmd)
            logger.debug("successfully stopped vm[uuid:%s]" % cmd.uuid)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def suspend_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        try:
            self._record_operation(cmd.uuid, self.VM_OP_SUSPEND)
            rsp = SuspendVmResponse()
            vm = get_vm_by_uuid(cmd.uuid)
            vm.suspend()
            logger.debug('successfully, suspend vm [uuid:%s]' % cmd.uuid)
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
                vm.destroy()
                logger.debug('successfully destroyed vm[uuid:%s]' % cmd.uuid)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def attach_data_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AttachDataVolumeResponse()
        try:
            volume = cmd.volume
            vm = get_vm_by_uuid(cmd.vmInstanceUuid)
            if vm.state != Vm.VM_STATE_RUNNING:
                raise kvmagent.KvmError(
                    'unable to attach volume[%s] to vm[uuid:%s], vm must be running' % (volume.installPath, vm.uuid))
            vm.attach_data_volume(cmd.volume, cmd.addons)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def detach_data_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DetachDataVolumeResponse()
        try:
            volume = cmd.volume
            vm = get_vm_by_uuid(cmd.vmInstanceUuid)
            if vm.state != Vm.VM_STATE_RUNNING:
                raise kvmagent.KvmError(
                    'unable to detach volume[%s] to vm[uuid:%s], vm must be running' % (volume.installPath, vm.uuid))
            vm.detach_data_volume(volume)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def migrate_vm(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = MigrateVmResponse()
        try:
            self._record_operation(cmd.vmUuid, self.VM_OP_MIGRATE)

            vm = get_vm_by_uuid(cmd.vmUuid)
            vm.migrate(cmd)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def merge_snapshot_to_volume(self, req):
        rsp = MergeSnapshotRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=True)

        if vm.state != vm.VM_STATE_RUNNING:
            rsp.error = 'vm[uuid:%s] is not running, cannot do live snapshot chain merge' % vm.uuid
            rsp.success = False
            return jsonobject.dumps(rsp)

        vm.merge_snapshot(cmd)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def take_volume_snapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = TakeSnapshotResponse()

        def makedir_if_need(new_path):
            dirname = os.path.dirname(new_path)
            if not os.path.exists(dirname):
                os.makedirs(dirname, 0755)

        def take_full_snapshot_by_qemu_img_convert(previous_install_path, install_path):
            makedir_if_need(install_path)
            linux.qcow2_create_template(previous_install_path, install_path)
            new_volume_path = os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
            makedir_if_need(new_volume_path)
            linux.qcow2_clone(install_path, new_volume_path)
            return install_path, new_volume_path

        def take_delta_snapshot_by_qemu_img_convert(previous_install_path, install_path):
            new_volume_path = os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
            makedir_if_need(new_volume_path)
            linux.qcow2_clone(previous_install_path, new_volume_path)
            return previous_install_path, new_volume_path

        try:
            if not cmd.vmUuid:
                if cmd.fullSnapshot:
                    rsp.snapshotInstallPath, rsp.newVolumeInstallPath = take_full_snapshot_by_qemu_img_convert(
                        cmd.volumeInstallPath, cmd.installPath)
                else:
                    rsp.snapshotInstallPath, rsp.newVolumeInstallPath = take_delta_snapshot_by_qemu_img_convert(
                        cmd.volumeInstallPath, cmd.installPath)

            else:
                vm = get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)

                if vm and vm.state != vm.VM_STATE_RUNNING and vm.state != vm.VM_STATE_SHUTDOWN and vm.state != vm.VM_STATE_PAUSED:
                    raise kvmagent.KvmError(
                        'unable to take snapshot on vm[uuid:{0}] volume[id:{1}], because vm is not Running, Stopped or Suspended, current state is {2}'.format(
                            vm.uuid, cmd.deviceId, vm.state))

                if vm and (vm.state == vm.VM_STATE_RUNNING or vm.state == vm.VM_STATE_PAUSED):
                    rsp.snapshotInstallPath, rsp.newVolumeInstallPath = vm.take_volume_snapshot(cmd.deviceId,
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
                            cmd.vmUuid, cmd.deviceId, rsp.snapshotInstallPath, rsp.newVolumeInstallPath))
                else:
                    logger.debug(
                        'took delta snapshot on vm[uuid:{0}] volume[id:{1}], snapshot path:{2}, new volulme path:{3}'.format(
                            cmd.vmUuid, cmd.deviceId, rsp.snapshotInstallPath, rsp.newVolumeInstallPath))

            rsp.size = os.path.getsize(rsp.snapshotInstallPath)
        except kvmagent.KvmError as e:
            logger.warn(linux.get_exception_stacktrace())
            rsp.error = str(e)
            rsp.success = False

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

        login = IscsiLogin()
        login.server_hostname = cmd.hostname
        login.server_port = cmd.port
        login.chap_password = cmd.chapPassword
        login.chap_username = cmd.chapUsername
        login.target = cmd.target
        login.login()

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
        sh_cmd = shell.ShellCmd('virsh secret-list | grep %s > /dev/null' % cmd.uuid)
        sh_cmd(False)
        if sh_cmd.return_code == 0:
            return jsonobject.dumps(kvmagent.AgentResponse())

        # for some reason, ceph doesn't work with the secret created by libvirt
        # we have to use the command line here
        content = '''
<secret ephemeral='yes' private='no'>
    <uuid>%s</uuid>
    <usage type='ceph'>
        <name>%s</name>
    </usage>
</secret>
    ''' % (cmd.uuid, cmd.uuid)

        spath = linux.write_to_temp_file(content)
        try:
            o = shell.call("virsh secret-define %s" % spath)
            o = o.strip(' \n\t\r')
            _, uuid, _ = o.split()
            shell.call('virsh secret-set-value %s %s' % (uuid, cmd.userKey))
        finally:
            os.remove(spath)

        return jsonobject.dumps(kvmagent.AgentResponse())

    def start(self):
        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(self.KVM_START_VM_PATH, self.start_vm)
        http_server.register_async_uri(self.KVM_STOP_VM_PATH, self.stop_vm)
        http_server.register_async_uri(self.KVM_SUSPEND_VM_PATH, self.suspend_vm)
        http_server.register_async_uri(self.KVM_RESUME_VM_PATH, self.resume_vm)
        http_server.register_async_uri(self.KVM_REBOOT_VM_PATH, self.reboot_vm)
        http_server.register_async_uri(self.KVM_DESTROY_VM_PATH, self.destroy_vm)
        http_server.register_async_uri(self.KVM_GET_CONSOLE_PORT_PATH, self.get_console_port)
        http_server.register_async_uri(self.KVM_CHANGE_CPUMEM_PATH, self.change_cpumem)
        http_server.register_async_uri(self.KVM_VM_SYNC_PATH, self.vm_sync)
        http_server.register_async_uri(self.KVM_ATTACH_VOLUME, self.attach_data_volume)
        http_server.register_async_uri(self.KVM_DETACH_VOLUME, self.detach_data_volume)
        http_server.register_async_uri(self.KVM_ATTACH_ISO_PATH, self.attach_iso)
        http_server.register_async_uri(self.KVM_DETACH_ISO_PATH, self.detach_iso)
        http_server.register_async_uri(self.KVM_MIGRATE_VM_PATH, self.migrate_vm)
        http_server.register_async_uri(self.KVM_TAKE_VOLUME_SNAPSHOT_PATH, self.take_volume_snapshot)
        http_server.register_async_uri(self.KVM_MERGE_SNAPSHOT_PATH, self.merge_snapshot_to_volume)
        http_server.register_async_uri(self.KVM_LOGOUT_ISCSI_TARGET_PATH, self.logout_iscsi_target)
        http_server.register_async_uri(self.KVM_LOGIN_ISCSI_TARGET_PATH, self.login_iscsi_target)
        http_server.register_async_uri(self.KVM_ATTACH_NIC_PATH, self.attach_nic)
        http_server.register_async_uri(self.KVM_DETACH_NIC_PATH, self.detach_nic)
        http_server.register_async_uri(self.KVM_CREATE_SECRET, self.create_ceph_secret_key)
        http_server.register_async_uri(self.KVM_VM_CHECK_STATE, self.check_vm_state)
        http_server.register_async_uri(self.KVM_VM_CHANGE_PASSWORD_PATH, self.change_vm_password)
        http_server.register_async_uri(self.KVM_VM_SET_ROOT_PASSWORD_PATH, self.set_root_password)
        http_server.register_async_uri(self.KVM_HARDEN_CONSOLE_PATH, self.harden_console)
        http_server.register_async_uri(self.KVM_DELETE_CONSOLE_FIREWALL_PATH, self.delete_console_firewall_rule)

        self.register_libvirt_event()

        @thread.AsyncThread
        def wait_end_signal():
            while True:
                try:
                    self.queue.get(True)

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

        wait_end_signal()

        @thread.AsyncThread
        def monitor_libvirt():
            while True:
                if shell.run('pid=$(cat /var/run/libvirtd.pid); ps -p $pid > /dev/null') != 0:
                    logger.warn(
                        "cannot find the libvirt process, assume it's dead, ask the mgmt server to reconnect us")
                    self.queue.put("exit")

                time.sleep(20)

        monitor_libvirt()

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

    def _vm_reboot_event(self, conn, dom, opaque):
        try:
            domain_xml = dom.XMLDesc(0)
            domain_xmlobject = xmlobject.loads(domain_xml)
            vm_uuid = dom.name()
            boot_dev = domain_xmlobject.os.get_child_node_as_list('boot')[0]
            if boot_dev.dev_ != 'cdrom':
                logger.debug("the vm[uuid:%s]'s boot device is %s, nothing to do, skip this reboot event" % (
                vm_uuid, boot_dev.dev_))
                return

            logger.debug(
                'the vm[uuid:%s] is set to boot from the cdrom, for the policy[bootFromHardDisk], the reboot will'
                ' boot from hdd' % vm_uuid)

            self._record_operation(vm_uuid, VmPlugin.VM_OP_REBOOT)
            boot_dev = xmlobject.XmlObject('boot')
            boot_dev.put_attr('dev', 'hd')
            domain_xmlobject.os.replace_node('boot', boot_dev)
            dom.destroy()

            xml = domain_xmlobject.dump()
            domain = conn.defineXML(xml)
            domain.createWithFlags(0)
        except:
            content = traceback.format_exc()
            logger.warn(content)

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
            if not xmlobject.has_element(domain_xmlobject, 'metadata.internalId'):
                logger.debug('vm[uuid:%s] is not managed by zstack,  do not configure the vnc iptables rules' % vm_uuid)
                return

            id = domain_xmlobject.metadata.internalId.text_
            vir = VncPortIptableRule()
            if LibvirtEventManager.EVENT_STARTED == event:
                vir.host_ip = domain_xmlobject.metadata.hostManagementIp.text_

                if shell.run('ip addr | grep -w %s > /dev/null' % vir.host_ip) != 0:
                    logger.debug('the vm is migrated from another host, we do not need to set the console firewall, as '
                                 'the management node will take care')
                    return

                for g in domain_xmlobject.devices.get_child_node_as_list('graphics'):
                    if g.type_ == 'vnc' or g.type_ == 'spice':
                        vir.port = g.port_
                        break

                vir.vm_internal_id = id
                vir.apply()
            elif LibvirtEventManager.EVENT_STOPPED == event:
                vir.vm_internal_id = id
                vir.delete()

        except:
            content = traceback.format_exc()
            logger.warn(content)

    def register_libvirt_event(self):
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self._vm_lifecycle_event)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE,
                                                  self._set_vnc_port_iptable_rule)
        LibvirtAutoReconnect.add_libvirt_callback(libvirt.VIR_DOMAIN_EVENT_ID_REBOOT, self._vm_reboot_event)
        LibvirtAutoReconnect.register_libvirt_callbacks()

    def stop(self):
        pass

    def configure(self, config):
        self.config = config
