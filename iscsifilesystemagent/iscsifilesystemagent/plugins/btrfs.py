__author__ = 'frank'

from zstacklib.utils import plugin
from zstacklib.utils import log
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import lock
import cherrypy
from iscsifilesystemagent import  iscsiagent
import time
import os

logger = log.get_logger(__name__)

class AgentCapacityResponse(object):
    def __init__(self):
        self.success = True
        self.error = ''
        self.availableCapacity = None
        self.totalCapacity = None

class InitRsp(AgentCapacityResponse):
    def __abs__(self):
        super(InitRsp, self).__init__()

class DownloadBitsFromSftpBackupStorageRsp(AgentCapacityResponse):
    def __abs__(self):
        super(DownloadBitsFromSftpBackupStorageRsp, self).__init__()

class CheckBitsExistenceRsp(object):
    def __init__(self):
        self.isExisting = True

class DeleteBitsRsp(AgentCapacityResponse):
    def __init__(self):
        super(DeleteBitsRsp, self).__init__()

class CreateRootVolumeFromTemplateRsp(AgentCapacityResponse):
    def __init__(self):
        super(CreateRootVolumeFromTemplateRsp, self).__init__()
        self.iscsiPath = None

class CreateEmptyVolumeRsp(AgentCapacityResponse):
    def __init__(self):
        super(CreateEmptyVolumeRsp, self).__init__()
        self.iscsiPath = None

class UploadToSftpRsp(AgentCapacityResponse):
    def __init__(self):
        super(UploadToSftpRsp, self).__init__()

class CreateIscsiTargetRsp(AgentCapacityResponse):
    def __init__(self):
        super(CreateIscsiTargetRsp, self).__init__()
        self.target = None
        self.lun = None

class CreateSubVolumeRsp(AgentCapacityResponse):
    def __init__(self):
        super(CreateSubVolumeRsp, self).__init__()
        self.path = None
        self.size = None

class CreateSymlinkRsp(AgentCapacityResponse):
    def __init__(self):
        super(CreateSymlinkRsp, self).__init__()

class DeleteSymlinkRsp(AgentCapacityResponse):
    def __init__(self):
        super(DeleteSymlinkRsp, self).__init__()

@lock.lock('tgt-admin-update')
def update_target(target_name):
    shell.call('tgt-admin --update %s --force' % target_name)

class BtrfsPlugin(plugin.Plugin):
    TYPE = "btrfs"
    INIT_PATH = "/%s/init" % TYPE
    DOWNLOAD_FROM_SFTP_PATH = "/%s/image/sftp/download" % TYPE
    CHECK_BITS_EXISTENCE = "/%s/bits/checkifexists" % TYPE
    DELETE_BITS_EXISTENCE = "/%s/bits/delete" % TYPE
    CREATE_ROOT_VOLUME_PATH = "/%s/volumes/createrootfromtemplate" % TYPE
    CREATE_EMPTY_VOLUME_PATH = "/%s/volumes/createempty" % TYPE
    UPLOAD_TO_SFTP = "/%s/bits/upload" % TYPE
    CREATE_TARGET_PATH = "/%s/target/create" % TYPE
    DELETE_TARGET_PATH = "/%s/target/delete" % TYPE
    DELETE_SUBVOLUME_PATH = "/%s/subvolume/delete" % TYPE
    CREATE_SUBVOLUME_PATH = "/%s/subvolume/create" % TYPE

    def _get_disk_capacity(self):
        total = linux.get_total_disk_size(self.root)

        out = shell.call('df')
        avail = None
        for l in out.split('\n'):
            if self.root in l:
                _, _, _, avail, _, _ = l.split()

        if not avail:
            raise Exception('cannot find available capacity, "df" output":\n %s' % out)

        return total, long(avail) * 1024

    @iscsiagent.replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = InitRsp()

        def check():
            out = shell.call('mount')
            for l in out.split('\n'):
                if 'btrfs' in l and cmd.rootFolderPath in l:
                    return

            raise Exception('%s is not mounted as btrfs in system' % cmd.rootFolderPath)

        check()
        self.root = cmd.rootFolderPath
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)

    @iscsiagent.replyerror
    def download_from_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DownloadBitsFromSftpBackupStorageRsp()
        sub_vol_dir = os.path.dirname(cmd.primaryStorageInstallPath)
        if not os.path.exists(sub_vol_dir):
            parent_dir = os.path.dirname(sub_vol_dir)
            shell.call('mkdir -p %s' % parent_dir)
            shell.call('btrfs subvolume create %s' % sub_vol_dir)

        linux.scp_download(cmd.hostname, cmd.sshKey, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath)

        def get_image_format():
            out = shell.call('qemu-img info %s' % cmd.primaryStorageInstallPath)
            for l in out.split('\n'):
                if 'file format' in l:
                    _, f = l.split(':')
                    return f.strip()
            raise Exception('cannot get image format of %s, qemu-img info outputs:\n%s\n' % (cmd.primaryStorageInstallPath, out))

        f = get_image_format()
        if 'qcow2' in f:
            shell.call('/usr/bin/qemu-img convert -f qcow2 -O raw %s %s.img' % (cmd.primaryStorageInstallPath, cmd.primaryStorageInstallPath))
            shell.call('mv %s.img %s' % (cmd.primaryStorageInstallPath, cmd.primaryStorageInstallPath))
        elif 'raw' in f:
            pass
        else:
            raise Exception('unsupported image format[%s] of %s' % (f, cmd.primaryStorageInstallPath))

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        logger.debug('downloaded %s:%s to %s' % (cmd.hostname, cmd.backupStorageInstallPath, cmd.primaryStorageInstallPath))
        return jsonobject.dumps(rsp)

    @iscsiagent.replyerror
    def check_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckBitsExistenceRsp()
        rsp.isExisting = os.path.exists(cmd.path)
        return jsonobject.dumps(rsp)

    def _delete_target(self, target_name, conf_uuid):
        conf_file = os.path.join('/etc/tgt/conf.d/%s.conf' % conf_uuid)
        shell.call('rm -f %s' % conf_file)

        output = shell.call('tgt-admin --show')
        if target_name not in output:
            return

        update_target(target_name)

    @iscsiagent.replyerror
    def delete_bits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteBitsRsp()

        if cmd.volumeUuid:
            iscsi_path = cmd.iscsiPath
            target_name = iscsi_path.lstrip('iscsi://').split('/')[1]
            self._delete_target(target_name, cmd.volumeUuid)

        sub_vol_dir = os.path.dirname(cmd.installPath)
        shell.call('btrfs subvolume delete %s' % sub_vol_dir)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        logger.debug('deleted %s' % cmd.installPath)
        return jsonobject.dumps(rsp)

    def _create_iscsi_target(self, vol_uuid, install_path, chapUsername=None, chapPassword=None):
        target_name = "iqn.%s.org.zstack:%s" % (time.strftime('%Y-%m'), vol_uuid)

        if not os.path.exists(install_path):
            raise Exception('unable to create iscsi target, file %s not found' % install_path)

        VOLUME_CONF = """\
<target %s>
backing-store %s
driver iscsi
write-cache on
</target>
"""

        VOLUME_CONF_WITH_CHAP_AUTH = """\
<target %s>
    backing-store %s
    driver iscsi
    %s
    write-cache on
</target>
"""

        if chapUsername and chapPassword:
            conf = VOLUME_CONF_WITH_CHAP_AUTH % (target_name, install_path, "incominguser %s %s" % (chapUsername, chapPassword))
        else:
            conf = VOLUME_CONF % (target_name, install_path)

        conf_dir = '/etc/tgt/conf.d'
        shell.call('mkdir -p %s' % conf_dir)

        conf_file = os.path.join(conf_dir, '%s.conf' % vol_uuid)
        if os.path.exists(conf_file):
            with open(conf_file, 'r') as fd:
                current_conf = fd.read()
                if current_conf == conf:
                    return target_name, conf_file

        with open(conf_file, 'w') as fd:
            fd.write(conf)

        return target_name, conf_file

    @iscsiagent.replyerror
    def create_root_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateRootVolumeFromTemplateRsp()

        if not os.path.exists(cmd.templatePathInCache):
            raise Exception('cannot find template[%s] in cache' % cmd.templatePathInCache)

        template_sub_vol = os.path.dirname(cmd.templatePathInCache)
        root_volume_sub_vol = os.path.dirname(cmd.installPath)
        parent_root_volume_sub_vol = os.path.dirname(root_volume_sub_vol)
        shell.call('mkdir -p %s' % parent_root_volume_sub_vol)
        shell.call('btrfs subvolume snapshot %s %s' % (template_sub_vol, root_volume_sub_vol))
        src_vol_name = os.path.join(root_volume_sub_vol, os.path.basename(cmd.templatePathInCache))
        if src_vol_name != cmd.installPath:
            shell.call('mv %s %s' % (src_vol_name, cmd.installPath))

        target_name, conf_file = self._create_iscsi_target(cmd.volumeUuid, cmd.installPath, cmd.chapUsername, cmd.chapPassword)
        update_target(target_name)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        rsp.iscsiPath = target_name

        logger.debug('create root volume[path:%s, iscsi target: %s, iscsi conf: %s]' % (cmd.installPath, target_name, conf_file))
        return jsonobject.dumps(rsp)


    def _create_subvolume(self, src, dst):
        src_volume = os.path.dirname(src)
        shell.call('mkdir -p %s' % os.path.dirname(dst))
        shell.call('btrfs subvolume snapshot %s %s' % (src_volume, dst))
        src_file_name = os.path.basename(src)
        dst_path = os.path.join(dst, src_file_name)
        return dst_path

    @iscsiagent.replyerror
    def create_subvolume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateSubVolumeRsp()
        if os.path.exists(cmd.dst):
            raise Exception('subvolume[%s] existing' % cmd.dst)

        rsp.path = self._create_subvolume(cmd.src, cmd.dst)
        rsp.size = os.path.getsize(rsp.path)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        logger.debug('created subvolume[%s]' % cmd.dst)
        return jsonobject.dumps(rsp)

    @iscsiagent.replyerror
    def create_empty_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateEmptyVolumeRsp()

        sub_vol_path = os.path.dirname(cmd.installPath)
        if os.path.exists(sub_vol_path):
            raise Exception('cannot create empty volume; %s already exists' % sub_vol_path)

        parent_dir = os.path.dirname(sub_vol_path)
        shell.call('mkdir -p %s' % parent_dir)
        shell.call('btrfs subvolume create %s' % sub_vol_path)

        linux.raw_create(cmd.installPath, cmd.size)
        target_name, conf_file = self._create_iscsi_target(cmd.volumeUuid, cmd.installPath, cmd.chapUsername, cmd.chapPassword)
        update_target(target_name)

        rsp.iscsiPath = target_name
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()

        logger.debug('created empty volume[path:%s, iscsi target:%s, iscsi conf:%s]' % (cmd.installPath, target_name, conf_file))
        return jsonobject.dumps(rsp)

    @iscsiagent.replyerror
    def upload_to_sftp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = UploadToSftpRsp()

        if not os.path.exists(cmd.primaryStorageInstallPath):
            raise Exception('cannot find %s' % cmd.primaryStorageInstallPath)

        linux.scp_upload(cmd.backupStorageHostName, cmd.backupStorageSshKey, cmd.primaryStorageInstallPath, cmd.backupStorageInstallPath)

        logger.debug('uploaded %s to sftp backup storage[hostname: %s, path:%s]' % (cmd.primaryStorageInstallPath, cmd.backupStorageHostName, cmd.backupStorageInstallPath))
        return jsonobject.dumps(rsp)

    @iscsiagent.replyerror
    def create_target(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateIscsiTargetRsp()

        target_name, conf_file = self._create_iscsi_target(cmd.volumeUuid, cmd.installPath, cmd.chapUsername, cmd.chapPassword)
        update_target(target_name)

        rsp.target = target_name
        rsp.lun = 1
        logger.debug('created ISCSI target[%s] in conf file[%s]' % (target_name, conf_file))
        return jsonobject.dumps(rsp)

    @iscsiagent.replyerror
    def delete_target(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._delete_target(cmd.target, cmd.uuid)
        logger.debug('deleted iscsi target[%s]' % cmd.target)
        rsp = AgentCapacityResponse()
        return jsonobject.dumps(rsp)

    def start(self):
        self.root = None

        http_server = self.config.http_server
        http_server.register_async_uri(self.INIT_PATH, self.init)
        http_server.register_async_uri(self.DOWNLOAD_FROM_SFTP_PATH, self.download_from_sftp)
        http_server.register_async_uri(self.CHECK_BITS_EXISTENCE, self.check_bits)
        http_server.register_async_uri(self.DELETE_BITS_EXISTENCE, self.delete_bits)
        http_server.register_async_uri(self.CREATE_ROOT_VOLUME_PATH, self.create_root_volume)
        http_server.register_async_uri(self.CREATE_EMPTY_VOLUME_PATH, self.create_empty_volume)
        http_server.register_async_uri(self.UPLOAD_TO_SFTP, self.upload_to_sftp)
        http_server.register_async_uri(self.CREATE_TARGET_PATH, self.create_target)
        http_server.register_async_uri(self.DELETE_TARGET_PATH, self.delete_target)
        http_server.register_async_uri(self.CREATE_SUBVOLUME_PATH, self.create_subvolume)

    def stop(self):
        pass

