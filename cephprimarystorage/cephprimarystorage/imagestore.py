from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import http

logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None

class CpRsp(AgentResponse):
    def __init__(self):
        super(CpRsp, self).__init__()
        self.installPath = None

class ImageStoreClient(object):
    ZSTORE_CLI_PATH = "/usr/local/zstack/imagestore/bin/zstcli -rootca /var/lib/zstack/imagestorebackupstorage/package/certs/ca.pem"
    ZSTORE_PROTOSTR = "zstore://"
    ZSTORE_DEF_PORT = 8000

    def _get_image_json_file(self, path):
        idx = path.rfind('.')
        if idx == -1:
            return path + ".imf2"
        return path[:idx] + ".imf2"

    def _get_id_name_from_install(self, path):
        if path.startswith("ceph://") == False:
            raise Exception("primary install path should starts with ceph://")
        strs = path.replace('ceph://', '').split('/')
        return strs[0], strs[1]

    def _ceph_file_existed(self, path):
        pool, meta = self._get_id_name_from_install(path)
        checkstr = 'rados -p pool %s stat %s' % (pool, meta)
        if shell.run(checkstr.encode(encoding="utf-8")) == 0:
            return True
        return False

    def _get_image_reference(self, path):
        try:
            pool, meta = self._get_id_name_from_install(path)
            metastr = 'rados get %s - -p %s' % (meta+'.imf2', pool)

            imf = jsonobject.loads(shell.call(metastr).strip())
            return imf.name, imf.id
        except IOError as e:
            errmsg = '_get_image_reference {0} failed: {1}'.format(path, e)
            raise Exception(errmsg)

    def _build_install_path(self, name, imgid):
        return "{0}{1}/{2}".format(self.ZSTORE_PROTOSTR, name, imgid)

    def upload_imagestore(self, cmd, req):
        imf = self._get_image_json_file(cmd.srcPath)
        if not self._ceph_file_existed(imf):
            self.commit_to_imagestore(cmd, req)

        extpara = ""
        taskid = req[http.REQUEST_HEADER].get(http.TASK_UUID)
        if cmd.threadContext:
            if cmd.threadContext['task-stage']:
                extpara += " -stage %s" % cmd.threadContext['task-stage']
            if cmd.threadContext.api:
                taskid = cmd.threadContext.api

        cmdstr = '%s -url %s:%s -callbackurl %s -taskid %s -imageUuid %s %s push %s' % (
            self.ZSTORE_CLI_PATH, cmd.hostname, self.ZSTORE_DEF_PORT, req[http.REQUEST_HEADER].get(http.CALLBACK_URI),
            taskid, cmd.imageUuid, extpara, cmd.srcPath)
        logger.debug('pushing %s to image store' % cmd.srcPath)
        shell.call(cmdstr.encode(encoding="utf-8"))
        logger.debug('%s pushed to image store' % cmd.srcPath)

        name, imageid = self._get_image_reference(cmd.srcPath)
        rsp = CpRsp()
        rsp.installPath = self._build_install_path(name, imageid)
        return jsonobject.dumps(rsp)

    def _parse_image_reference(self, backupStorageInstallPath):
        if not backupStorageInstallPath.startswith(self.ZSTORE_PROTOSTR):
            raise Exception('unexpected backup storage install path %s' % backupStorageInstallPath)

        xs = backupStorageInstallPath[len(self.ZSTORE_PROTOSTR):].split('/')
        if len(xs) != 2:
            raise Exception('unexpected backup storage install path %s' % backupStorageInstallPath)

        return xs[0], xs[1]

    def download_imagestore(self, cmd):
        rsp = AgentResponse()
        name, imageid = self._parse_image_reference(cmd.bsInstallPath)
        cmdstr = '%s -url %s:%s pull -installpath %s %s:%s' % (
        self.ZSTORE_CLI_PATH, cmd.hostname, self.ZSTORE_DEF_PORT, cmd.psInstallPath, name, imageid)
        logger.debug('pulling %s:%s from image store' % (name, imageid))
        shell.call(cmdstr)
        logger.debug('%s:%s pulled to ceph storage' % (name, imageid))
        return jsonobject.dumps(rsp)

    def commit_to_imagestore(self, cmd, req):
        fpath = cmd.srcPath

        # Add the image to registry
        cmdstr = '%s -json  -callbackurl %s -taskid %s -imageUuid %s add -desc \'%s\' -file %s' % (
        self.ZSTORE_CLI_PATH, req[http.REQUEST_HEADER].get(http.CALLBACK_URI),
        req[http.REQUEST_HEADER].get(http.TASK_UUID), cmd.imageUuid, cmd.description, fpath)

        logger.debug('adding %s to local image store' % fpath)
        shell.call(cmdstr.encode(encoding="utf-8"))
        logger.debug('%s added to local image store' % fpath)

