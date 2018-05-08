# coding=utf-8
'''

@author: mingjian.deng
'''
import os.path
from zstacklib.utils.bash import *
from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import shell
import zstacklib.utils.uuidhelper as uuidhelper
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import naslinux

logger = log.get_logger(__name__)

class AliyunNasResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(AliyunNasResponse, self).__init__()
        self.totalCapacity = None
        self.availableCapacity = None

class InitResponse(AliyunNasResponse):
    def __init__(self):
        super(InitResponse, self).__init__()
        self.mounted = False

class IsMountResponse(AliyunNasResponse):
    def __init__(self):
        super(IsMountResponse, self).__init__()
        self.ismounted = False

class ListResponse(AliyunNasResponse):
    def __init__(self):
        super(ListResponse, self).__init__()
        self.paths = []

class CheckIsBitsExistingResponse(AliyunNasResponse):
    def __init__(self):
        super(CheckIsBitsExistingResponse, self).__init__()
        self.existing = None

class VolumeMeta(object):
    def __init__(self):
        self.name = None
        self.account_uuid = None
        self.uuid = None
        self.hypervisor_type = None
        self.size = None

class GetVolumeSizeRsp(AliyunNasResponse):
    def __init__(self):
        super(GetVolumeSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None

class RevertVolumeFromSnapshotRsp(AliyunNasResponse):
    def __init__(self):
        super(RevertVolumeFromSnapshotRsp, self).__init__()
        self.newVolumeInstallPath = None
        self.size = None

class ResizeVolumeRsp(AliyunNasResponse):
    def __init__(self):
        super(ResizeVolumeRsp, self).__init__()
        self.size = None

class MergeSnapshotRsp(AliyunNasResponse):
    def __init__(self):
        super(MergeSnapshotRsp, self).__init__()
        self.size = None
        self.actualSize = None

class ReInitImageRsp(AliyunNasResponse):
    def __init__(self):
        super(ReInitImageRsp, self).__init__()
        self.newVolumeInstallPath = None


class AliyunNasStoragePlugin(kvmagent.KvmAgent):
    MOUNT_PATH = "/aliyun/nas/primarystorage/mount"
    IS_MOUNT_PATH = "/aliyun/nas/primarystorage/ismount"
    MOUNT_DATA_PATH = "/aliyun/nas/primarystorage/mountdata"
    INIT_PATH = "/aliyun/nas/primarystorage/init"
    PING_PATH = "/aliyun/nas/primarystorage/ping"
    GET_CAPACITY_PATH = "/aliyun/nas/primarystorage/getcapacity"
    LIST_PATH = "/aliyun/nas/primarystorage/list"
    UPDATE_MOUNT_POINT_PATH = "/aliyun/nas/primarystorage/updatemountpoint"
    REMOUNT_PATH = "/aliyun/nas/primarystorage/remount"
    UNMOUNT_PATH = "/aliyun/nas/primarystorage/unmount"
    CHECK_BITS_PATH = "/aliyun/nas/primarystorage/checkbits"
    CREATE_EMPTY_VOLUME_PATH = "/aliyun/nas/primarystorage/createempty"
    CREATE_VOLUME_FROM_CACHE_PATH = "/aliyun/nas/primarystorage/createvolume"
    DELETE_BITS_PATH = "/aliyun/nas/primarystorage/deletebits"
    GET_VOLUME_SIZE_PATH = "/aliyun/nas/primarystorage/getvolumesize"
    REVERT_VOLUME_FROM_SNAPSHOT_PATH = "/aliyun/nas/primarystorage/revertvolume"
    DOWNLOAD_BIT_TO_IMAGESTORE_PATH = "/aliyun/nas/primarystorage/imagestore/download"
    UPLOAD_BIT_TO_IMAGESTORE__PATH = "/aliyun/nas/primarystorage/imagestore/upload"
    REINIT_VOLUME_PATH = "/aliyun/nas/primarystorage/reinit"
    RESIZE_VOLUME_PATH = "/aliyun/nas/primarystorage/resize"
    COMMIT_PATH = "/aliyun/nas/primarystorage/commit"
    CREATE_TEMPLATE_FROM_VOLUME_PATH = "/aliyun/nas/primarystorage/createtemplatefromvolume"
    MERGE_SNAPSHOT_PATH = "/aliyun/nas/primarystorage/mergesnapshot"
    OFFLINE_MERGE_SNAPSHOT_PATH = "/aliyun/nas/primarystorage/snapshot/offlinemerge"


    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.MOUNT_PATH, self.mount)
        http_server.register_async_uri(self.IS_MOUNT_PATH, self.ismount)
        http_server.register_async_uri(self.MOUNT_DATA_PATH, self.mountdata)
        http_server.register_async_uri(self.INIT_PATH, self.init)
        http_server.register_async_uri(self.PING_PATH, self.ping)
        http_server.register_async_uri(self.LIST_PATH, self.list)
        http_server.register_async_uri(self.UPDATE_MOUNT_POINT_PATH, self.updateMount)
        http_server.register_async_uri(self.REMOUNT_PATH, self.remount)
        http_server.register_async_uri(self.UNMOUNT_PATH, self.umount)
        http_server.register_async_uri(self.CHECK_BITS_PATH, self.checkbits)
        http_server.register_async_uri(self.CREATE_EMPTY_VOLUME_PATH, self.createempty)
        http_server.register_async_uri(self.CREATE_VOLUME_FROM_CACHE_PATH, self.createvolume)
        http_server.register_async_uri(self.DELETE_BITS_PATH, self.deletebits)
        http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.getvolumesize)
        http_server.register_async_uri(self.REVERT_VOLUME_FROM_SNAPSHOT_PATH, self.revertvolume)
        http_server.register_async_uri(self.REINIT_VOLUME_PATH, self.reinit)
        http_server.register_async_uri(self.UPLOAD_BIT_TO_IMAGESTORE__PATH, self.uploadtoimagestore)
        http_server.register_async_uri(self.DOWNLOAD_BIT_TO_IMAGESTORE_PATH, self.downloadfromimagestore)
        http_server.register_async_uri(self.RESIZE_VOLUME_PATH, self.resize)
        http_server.register_async_uri(self.COMMIT_PATH, self.commit_to_imagestore)
        http_server.register_async_uri(self.CREATE_TEMPLATE_FROM_VOLUME_PATH, self.createtemplate)
        http_server.register_async_uri(self.MERGE_SNAPSHOT_PATH, self.mergesnapshot)
        http_server.register_async_uri(self.OFFLINE_MERGE_SNAPSHOT_PATH, self.offlinemerge)
        http_server.register_async_uri(self.GET_CAPACITY_PATH, self.getcapacity)
        self.mount_path = {}
        self.uuid = None
        self.imagestore_client = ImageStoreClient()

    def stop(self):
        pass

    def _set_capacity_to_response(self, uuid, rsp):
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(uuid)

    def _get_disk_capacity(self, uuid):
        path = self.mount_path.get(uuid)
        if not path:
            raise Exception('cannot find mount path of primary storage[uuid: %s]' % uuid)
        return linux.get_disk_capacity_by_df(path)

    @kvmagent.replyerror
    def mount(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()
        linux.is_valid_nfs_url(cmd.url)

        if not naslinux.is_mounted(cmd.mountPath, cmd.url):
            linux.mount(cmd.url, cmd.mountPath, cmd.options)
            logger.debug(http.path_msg(self.MOUNT_PATH, 'mounted %s on %s' % (cmd.url, cmd.mountPath)))
            rsp.mounted = True

        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def ismount(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = IsMountResponse()
        linux.is_valid_nfs_url(cmd.url)

        if naslinux.is_mounted(cmd.mountPath, cmd.url):
            rsp.ismounted = True

        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def mountdata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()
        naslinux.createCommonPath(cmd.mountPath, cmd.basePath)

        if not naslinux.is_mounted(cmd.dataPath, cmd.url):
            linux.mount(cmd.url, cmd.dataPath, cmd.options)
            logger.debug(http.path_msg(self.MOUNT_DATA_PATH, 'mounted %s on %s' % (cmd.url, cmd.dataPath)))
            rsp.mounted = True

        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def init(self, req):
        '''
            cmd.url --> domain:/ps-[uuid]
            cmd.mountPath --> /opt/ps
            cmd.common --> /opt/ps/commons
            cmd.data --> /opt/ps/datas
            cmd.dirs --> []
        '''
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = InitResponse()
        linux.is_valid_nfs_url(cmd.url)

        '''
            example:
                1. mount url: /opt/ps
                2. mkdir /opt/ps/ps-[uuid]
                3. mkdir /opt/ps/ps-[uuid]/commons/xxx..  (such as heartbeat, cache, ..)
                at last we get url:/ps-[uuid] for hosts mount
        '''
        domain = cmd.url.split(':')[0] + ":/"
        psDir = cmd.url.split(':')[1].lstrip('/')
        basedir = os.path.join(cmd.mountPath, psDir)

        '''
          check if mounted {cmd.mountPath}
        '''
        if linux.is_mounted(path=cmd.mountPath) and not naslinux.is_mounted(cmd.mountPath, cmd.url):
            raise Exception('mountPath[%s] already mount to another url' % cmd.mountPath)

        linux.mount(domain, cmd.mountPath, cmd.options)
        shell.call('mkdir -p %s' % basedir)
        for dir in cmd.dirs:
            shell.call('mkdir -p %s' % os.path.join(basedir, dir))
        linux.umount(cmd.mountPath)
        common_dir = os.path.join(cmd.mountPath, cmd.common)
        data_dir = os.path.join(cmd.mountPath, cmd.data)
        shell.call('mkdir -p %s' % common_dir)
        shell.call('mkdir -p %s' % data_dir)
        linux.mount(cmd.url, common_dir, cmd.options)

        rsp.mounted = True
        self.mount_path[cmd.uuid] = common_dir
        self._set_capacity_to_response(cmd.uuid, rsp)
        self.uuid = cmd.uuid
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        mount_path = cmd.mountPath
        # if nfs service stop, os.path.isdir will hung
        if not linux.timeout_isdir(mount_path) or not linux.is_mounted(path=mount_path):
            raise Exception(
                'the mount path[%s] of the nas primary storage[uuid:%s] is not existing' % (mount_path, cmd.uuid))

        test_file = os.path.join(mount_path, cmd.heartbeat, '%s-ping-test-file' % cmd.uuid)
        touch = shell.ShellCmd('timeout 60 touch %s' % test_file)
        touch(False)
        if touch.return_code == 124:
            raise Exception('unable to access the mount path[%s] of the nas primary storage[uuid:%s] in 60s, timeout' %
                            (mount_path, cmd.uuid))
        elif touch.return_code != 0:
            touch.raise_error()

        shell.call('rm -f %s' % test_file)
        return jsonobject.dumps(AliyunNasResponse())

    @kvmagent.replyerror
    def getvolumesize(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetVolumeSizeRsp()
        self._set_capacity_to_response(cmd.uuid, rsp)
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.installPath)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def list(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ListResponse()

        rsp.paths = kvmagent.listPath(cmd.path)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def updateMount(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()
        linux.is_valid_nfs_url(cmd.newUrl)

        if not naslinux.is_mounted(cmd.mountPath, cmd.newUrl):
            # umount old one
            if naslinux.is_mounted(cmd.mountPath, cmd.url):
                linux.umount(cmd.mountPath)
            # mount new
            linux.mount(cmd.newUrl, cmd.mountPath, cmd.options)

        self.mount_path[cmd.uuid] = cmd.mountPath
        logger.debug('updated the mount path[%s] mounting point from %s to %s' % (
        cmd.mountPath, cmd.url, cmd.newUrl))
        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def remount(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()
        linux.is_valid_nfs_url(cmd.url)
        naslinux.remount(cmd.url, cmd.mountPath, cmd.options)

        self.mount_path[cmd.uuid] = cmd.mountPath
        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def umount(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()
        if linux.is_mounted(path=cmd.mountPath):
            ret = linux.umount(cmd.mountPath)
            if not ret:
                logger.warn(http.path_msg(self.UNMOUNT_PATH, 'unmount %s failed' % cmd.mountPath))
        logger.debug(http.path_msg(self.UNMOUNT_PATH, 'umounted %s' % cmd.mountPath))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def checkbits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckIsBitsExistingResponse()
        rsp.existing = os.path.exists(cmd.path)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def createempty(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()

        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        if cmd.backingFile:
            linux.qcow2_create_with_backing_file(cmd.backingFile, cmd.installPath)
        else:
            linux.qcow2_create(cmd.installPath, cmd.size)

        logger.debug(
            'successfully create empty volume[uuid:%s, size:%s] at %s' % (cmd.volumeUuid, cmd.size, cmd.installPath))
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.uuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def createvolume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()

        if not os.path.exists(cmd.templatePathInCache):
            rsp.error = "unable to find image in cache"
            rsp.success = False
            return jsonobject.dumps(rsp)

        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0775)

        linux.qcow2_clone(cmd.templatePathInCache, cmd.installPath)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.uuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def deletebits(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()
        self.delNasBits(cmd.folder, cmd.path)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.uuid)
        return jsonobject.dumps(rsp)

    def delNasBits(self, folder, path):
        if folder:
            shell.call('rm -rf %s' % path)
        else:
            kvmagent.deleteImage(path)
        # pdir = os.path.dirname(path)
        # if os.path.exists(pdir) or not os.listdir(pdir):
        #     linux.umount(pdir, False)

    @kvmagent.replyerror
    def revertvolume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = RevertVolumeFromSnapshotRsp()

        install_path = cmd.snapshotInstallPath
        new_volume_path = os.path.join(os.path.dirname(install_path), '{0}.qcow2'.format(uuidhelper.uuid()))
        linux.qcow2_clone(install_path, new_volume_path)
        size = linux.qcow2_virtualsize(new_volume_path)
        rsp.newVolumeInstallPath = new_volume_path
        rsp.size = size
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def reinit(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ReInitImageRsp()

        install_path = cmd.imagePath
        new_volume_path = os.path.join(os.path.dirname(cmd.volumePath), '{0}.qcow2'.format(uuidhelper.uuid()))
        linux.qcow2_clone(install_path, new_volume_path)
        rsp.newVolumeInstallPath = new_volume_path
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.uuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def uploadtoimagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.upload_to_imagestore(cmd, req)

    @kvmagent.replyerror
    def downloadfromimagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.imagestore_client.download_from_imagestore(cmd.cacheDir, cmd.hostname, cmd.backupStorageInstallPath,
                                                        cmd.primaryStorageInstallPath)
        rsp = AliyunNasResponse()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.uuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def resize(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        install_path = cmd.installPath
        rsp = ResizeVolumeRsp()
        shell.call("qemu-img resize %s %s" % (install_path, cmd.size))
        ret = linux.qcow2_virtualsize(install_path)
        rsp.size = ret
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def commit_to_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        return self.imagestore_client.commit_to_imagestore(cmd, req)

    @kvmagent.replyerror
    def createtemplate(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()
        dirname = os.path.dirname(cmd.installPath)
        if not os.path.exists(dirname):
            os.makedirs(dirname, 0755)
        linux.create_template(cmd.volumePath, cmd.installPath)

        logger.debug('successfully created template[%s] from volume[%s]' % (cmd.installPath, cmd.volumePath))
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.uuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def mergesnapshot(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = MergeSnapshotRsp()

        workspace_dir = os.path.dirname(cmd.workspaceInstallPath)
        if not os.path.exists(workspace_dir):
            os.makedirs(workspace_dir)

        linux.create_template(cmd.snapshotInstallPath, cmd.workspaceInstallPath)
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.workspaceInstallPath)

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.uuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def offlinemerge(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()
        if not cmd.fullRebase:
            linux.qcow2_rebase(cmd.srcPath, cmd.destPath)
        else:
            tmp = os.path.join(os.path.dirname(cmd.destPath), '%s.qcow2' % uuidhelper.uuid())
            linux.create_template(cmd.destPath, tmp)
            shell.call("mv %s %s" % (tmp, cmd.destPath))

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.uuid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def getcapacity(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AliyunNasResponse()
        self._set_capacity_to_response(cmd.uuid, rsp)
        return jsonobject.dumps(rsp)