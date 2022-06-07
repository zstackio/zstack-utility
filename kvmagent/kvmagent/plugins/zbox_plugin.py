import contextlib
import libvirt
import os
import time

from zstacklib.utils import vm_operator
from zstacklib.utils import log
from zstacklib.utils import uuidhelper, xmlobject
from zstacklib.utils import shell
from zstacklib.utils import jsonobject, http
from zstacklib.utils import linux
from zstacklib.utils.sqlite import Sqlite

from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin

logger = log.get_logger(__name__)


class TakeVolumesBackupsResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(TakeVolumesBackupsResponse, self).__init__()
        self.volumeBackupInfos = []  # type:list[VolumeBackupInfo]


class InitZBoxBackupResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(InitZBoxBackupResponse, self).__init__()


class VolumeBackupInfo(object):
    def __init__(self, install_path, uuid):
        self.installPath = install_path
        self.uuid = uuid


class InitZBoxResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(InitZBoxResponse, self).__init__()
        self.info = None  # type: ZBoxInfo


class EjectZBoxResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(EjectZBoxResponse, self).__init__()


class SyncZBoxResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(SyncZBoxResponse, self).__init__()
        self.info = None  # type: ZBoxInfo


class RefreshZBoxResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(RefreshZBoxResponse, self).__init__()
        self.infos = []  # type: list[ZBoxInfo]


class DeleteBitsResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(DeleteBitsResponse, self).__init__()


class ZBoxInfo(object):
    def __init__(self):
        self.busNum = None
        self.devNum = None
        self.uuid = None
        self.name = None
        self.mountPath = None
        self.status = 'Ready'
        self.totalCapacity = 0
        self.availableCapacity = 0


def find_usb_devices():
    devcmd = shell.ShellCmd("lsblk -p -oTRAN,NAME | grep  -oP '^usb\s*\K.*'")
    devcmd(False)
    return [] if devcmd.return_code != 0 else devcmd.stdout.splitlines()


def get_blk_fstype(devname):
    # type: (str) -> dict[str, str]
    devcmd = shell.ShellCmd("lsblk -prn -oNAME,FSTYPE %s" % devname)
    devcmd(False)
    ret = {}
    if devcmd.return_code == 0:
        for l in devcmd.stdout.splitlines():
            kv = l.split()
            if len(kv) == 2:
                ret[kv[0]] = kv[1]
    return ret


def label_zbox_on_formatted_storage(devname, label):
    for dev_path, fstype in get_blk_fstype(devname).items():
        if fstype == 'ext4':
            shell.call("e2label %s %s" % (dev_path, label))
            return label
        elif fstype == 'vfat':
            shell.call("fatlabel %s %s" % (dev_path, label[0:11]))
            return label[0:11]
        elif fstype == 'exfat':
            shell.call("exfatlabel %s %s" % (dev_path, label))
            return label

    raise Exception('filesystem type of storage must be ext4.')


def get_usb_bus_dev_num(devname):
    lines = shell.call("udevadm info -a -n %s | grep -Em 2 'busnum|devnum'" % devname).splitlines()
    busnum = lines[0].split("==")[1].strip('"')
    devnum = lines[1].split("==")[1].strip('"')
    return '0' * (3 - len(busnum)) + busnum, '0' * (3 - len(devnum)) + devnum,


def get_zbox_label(devname):
    cmd = shell.ShellCmd('lsblk %s -oLABEL | grep zbox' % devname)
    cmd(False)
    return None if cmd.return_code != 0 else cmd.stdout.strip()


def get_zbox_devname_path_and_label():
    cmd = shell.ShellCmd("lsblk -prn /dev/sd* -o NAME,LABEL | grep '/dev/sd\|zbox'")
    cmd(False)
    ret = []
    if cmd.return_code == 0:
        last_dev_name = ''
        for l in cmd.stdout.splitlines():
            if l.startswith('/dev/sd'):
                last_dev_name = l.split()[0]

            if 'zbox' in l:
                path, label = l.split()
                ret.append((last_dev_name, path, label))
    return ret


def mount_label(label, mount_path, raise_exception=True):
    if not os.path.exists(mount_path):
        os.mkdir(mount_path)

    cmd = shell.ShellCmd("timeout 180 mount -L %s %s" % (label, mount_path))
    cmd(False)
    if cmd.return_code != 0 and raise_exception:
        cmd.raise_error()

    return cmd.return_code == 0


def build_label(zbox_uuid):
    return "zbox-" + zbox_uuid[0:10]


def build_mount_path(label):
    return os.path.join("/var", label)


def merge_zbox_info(mount_path, uuid=None, name=None):
    if not uuid:
        uuid = uuidhelper.uuid()

    if not name:
        name = build_label(uuid)

    with Sqlite(os.path.join(mount_path, 'zbox.db')) as sql:
        sql.execute("create table if not exists ZBoxVO(uuid varchar PRIMARY KEY, name varchar);")
        ls = sql.execute("select * from ZBoxVO;").fetchall()
        if not ls:
            sql.execute("insert into  ZBoxVO(uuid, name) values (?, ?);", (uuid, name))
            return uuid, name
        else:
            return ls[0][0], ls[0][1]


def get_mounted_zbox_mountpath_and_devname():
    # type: () -> dict
    # do not use mount -l because label will disappear after remove usb device.
    lines = shell.call("mount | awk '/zbox-[0-9a-zA-Z]{6,10}/{print $1,$3}'").splitlines()
    dicts = {}
    for devname, mount_path in map(lambda l: l.split(), lines):
        dicts[mount_path] = devname
    return dicts


class SshfsRemoteStorage(object):
    def __init__(self, vm_uuid, info):
        self.vm_uuid = vm_uuid
        self.info = info

    def __enter__(self):
        if not os.path.exists(self.info.zboxPath):
            os.makedirs(self.info.zboxPath, 0755)

        vm = vm_plugin.get_vm_by_uuid(self.vm_uuid)
        linux.sshfs_mount_with_vm_xml(vm.domain_xmlobject, self.info.username, self.info.hostname, self.info.sshPort,
                                          self.info.password, self.info.zboxPath, self.info.zboxPath)

    def __exit__(self, exc_type, exc_val, exc_tb):
        for i in xrange(6):
            if linux.fumount(self.info.zboxPath, 5) == 0:
                break
            else:
                time.sleep(5)


class ZBoxPlugin(kvmagent.KvmAgent):
    KVM_TAKE_VOLUMES_SHALLOW_BACKUP_PATH = "/zbox/volumes/takeshallowbackup"
    KVM_ZBOX_BACKUP_INIT_PATH = "/zbox/backup/init"

    DELETE_BITS = "/zbox/deletebits"
    INIT_ZBOX = "/zbox/init"
    EJECT_ZBOX = "/zbox/eject"
    REFRESH_ZBOX = "/zbox/refresh"
    SYNC_ZBOX = "/zbox/sync"

    def __init__(self):
        super(ZBoxPlugin, self).__init__()

    @kvmagent.replyerror
    def take_volumes_shallow_backup(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = TakeVolumesBackupsResponse()
        vm = vm_plugin.get_vm_by_uuid(cmd.vmUuid, exception_if_not_existing=False)

        for path in cmd.dstDeviceIdPath.__dict__.values():
            linux.rm_dir_force(path)

        if not cmd.remoteInfo:
            vm.take_volumes_shallow_backup(cmd, cmd.volumes, cmd.dstDeviceIdPath.__dict__)
        else:
            with SshfsRemoteStorage(cmd.vmUuid, cmd.remoteInfo):
                vm.take_volumes_shallow_backup(cmd, cmd.volumes, cmd.dstDeviceIdPath.__dict__)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def init_zbox_backup(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = InitZBoxBackupResponse()

        if not linux.is_mounted(cmd.mountPath):
            raise Exception('zbox is not mounted on ' + cmd.mountPath)

        if not os.path.exists(cmd.installPath):
            logger.debug("init backup[uuid:%s] on zbox[uuid:%s]" % (cmd.backupUuid, cmd.zboxUuid))
            os.makedirs(cmd.installPath, 0755)
            linux.write_file(os.path.join(cmd.installPath, "name"), cmd.name, create_if_not_exist=True)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def init_zbox(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = InitZBoxResponse()
        info = ZBoxInfo()

        target_dev_name = None
        for devname in find_usb_devices():
            busnum, devnum = get_usb_bus_dev_num(devname)
            if busnum == cmd.usbDevice.busNum and devnum == cmd.usbDevice.devNum:
                target_dev_name = devname
                break

        if not target_dev_name:
            rsp.success = False
            rsp.error = "failed to find usb disk[Bus:%s, Device:%s], is it a disk?" % (cmd.usbDevice.busNum, cmd.usbDevice.devNum)
            return jsonobject.dumps(rsp)

        label = get_zbox_label(target_dev_name)
        if not label:
            info.uuid = uuidhelper.uuid()
            label = build_label(info.uuid)
            if cmd.skipFormat:
                label = label_zbox_on_formatted_storage(target_dev_name, label)
            else:
                shell.call("mkfs.ext4 -F -L %s %s" % (label, target_dev_name))

        mount_path = build_mount_path(label)
        mount_label(label, mount_path)

        info.mountPath = mount_path
        info.uuid, info.name = merge_zbox_info(mount_path, info.uuid, cmd.name)
        info.totalCapacity, info.availableCapacity = linux.get_disk_capacity_by_df(mount_path)
        rsp.info = info
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def refresh_zbox(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RefreshZBoxResponse()

        mounted_dev = get_mounted_zbox_mountpath_and_devname()
        time.sleep(5)
        for devname, path, label in get_zbox_devname_path_and_label():
            mount_path = build_mount_path(label)
            busnum, devnum = get_usb_bus_dev_num(devname)

            info = ZBoxInfo()
            info.mountPath = mount_path
            info.busNum = busnum
            info.devNum = devnum

            if mount_path in mounted_dev:
                if mounted_dev[mount_path] != path:
                    # zbox maybe removed before, remount
                    if shell.run("umount -f %s" % mount_path) == 0 and not mount_label(label, mount_path, raise_exception=False):
                        info.status = 'Error'
                        rsp.infos.append(info)
                        continue

                info.uuid, info.name = merge_zbox_info(mount_path)
                info.totalCapacity, info.availableCapacity = linux.get_disk_capacity_by_df(mount_path)
                rsp.infos.append(info)
                continue

            ejected_zbox = filter(lambda z: z.mountPath == mount_path and busnum == z.busNum and devnum == z.devNum,
                                  cmd.ignoreZBoxes)
            if ejected_zbox:
                info.uuid = ejected_zbox[0].uuid
                info.name = ejected_zbox[0].name
                info.status = 'Ejected'
                rsp.infos.append(info)
                continue

            if not mount_label(label, mount_path, raise_exception=False):
                info.status = 'Error'
            else:
                info.uuid, info.name = merge_zbox_info(mount_path)
                info.totalCapacity, info.availableCapacity = linux.get_disk_capacity_by_df(mount_path)

            rsp.infos.append(info)

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def eject_zbox(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = EjectZBoxResponse()
        shell.call("umount %s" % cmd.mountPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def sync_zbox(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = SyncZBoxResponse()
        if linux.is_mounted(cmd.mountPath):
            info = ZBoxInfo()
            info.totalCapacity, info.availableCapacity = linux.get_disk_capacity_by_df(cmd.mountPath)
            rsp.info = info
        else:
            rsp.error = "zbox is not mounted."
            rsp.success = False
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def delete_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteBitsResponse()

        dpath = cmd.installPath.strip()
        if not dpath.startswith("/var/zbox-"):
            raise Exception('you can only delete bits under zbox')

        def all_killed(_):
            return all(not os.path.exists('/proc/%s' % pid) for pid in pids)

        pids = linux.kill_process_by_fullname(dpath, 15)
        if not linux.wait_callback_success(all_killed, None, 5):
            linux.kill_process_by_fullname(dpath, 9)
            linux.wait_callback_success(all_killed, None, 5)

        if cmd.isDir:
            linux.rm_dir_force(dpath)
        else:
            linux.rm_file_force(dpath)

        return jsonobject.dumps(rsp)

    def start(self):
        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(self.KVM_TAKE_VOLUMES_SHALLOW_BACKUP_PATH, self.take_volumes_shallow_backup)
        http_server.register_async_uri(self.KVM_ZBOX_BACKUP_INIT_PATH, self.init_zbox_backup)
        http_server.register_async_uri(self.INIT_ZBOX, self.init_zbox)
        http_server.register_async_uri(self.EJECT_ZBOX, self.eject_zbox)
        http_server.register_async_uri(self.REFRESH_ZBOX, self.refresh_zbox)
        http_server.register_async_uri(self.SYNC_ZBOX, self.sync_zbox)
        http_server.register_async_uri(self.DELETE_BITS, self.delete_bits)

    def stop(self):
        pass
