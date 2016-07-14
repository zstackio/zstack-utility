import os.path
import traceback

from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell

logger = log.get_logger(__name__)

class ImageStoreClient(object):

    ZSTORE_PROTOSTR = "zstore://"
    ZSTORE_CLI_PATH = "/usr/local/zstack/imagestore/bin/zstcli -rootca /var/lib/zstack/imagestorebackupstorage/certs/ca.pem"
    ZSTORE_DEF_PORT = 8000

    UPLOAD_BIT_PATH = "/imagestore/upload"
    DOWNLOAD_BIT_PATH = "/imagestore/download"
    COMMIT_BIT_PATH = "/imagestore/commit"

    def _get_image_json_file(self, primaryInstallPath):
        idx = primaryInstallPath.rfind('.')
        if idx == -1:
            return primaryInstallPath + ".json"
        return primaryInstallPath[:idx] + ".json"

    def _get_image_reference(self, primaryStorageInstallPath):
        try:
            with open(self._get_image_json_file(primaryStorageInstallPath)) as f:
                imf = jsonobject.loads(f.read())
                return imf.name, imf.id
        except IOError, e:
            errmsg = '_get_image_reference {0} failed: {1}'.format(primaryStorageInstallPath, e)
            raise kvmagent.KvmError(errmsg)

    def _parse_image_reference(self, backupStorageInstallPath):
        if not backupStorageInstallPath.startswith(self.ZSTORE_PROTOSTR):
            raise kvmagent.KvmError('unexpected backup storage install path %s' % backupStorageInstallPath)

        xs = backupStorageInstallPath[len(self.ZSTORE_PROTOSTR):].split('/')
        if len(xs) != 2:
            raise kvmagent.KvmError('unexpected backup storage install path %s' % backupStorageInstallPath)

        return xs[0], xs[1]

    def _build_install_path(self, name, imgid):
        return "{0}{1}/{2}".format(self.ZSTORE_PROTOSTR, name, imgid)

    def upload_to_imagestore(self, host, primaryStorageInstallPath):
        name, imageid = self._get_image_reference(primaryStorageInstallPath)
        cmdstr = '%s -url %s:%s push %s:%s' % (self.ZSTORE_CLI_PATH, host, self.ZSTORE_DEF_PORT, name, imageid)
        logger.debug('pushing %s:%s to image store' % (name, imageid))
        shell.call(cmdstr)
        logger.debug('%s:%s pushed to image store' % (name, imageid))

        rsp = kvmagent.AgentResponse()
        rsp.backupStorageInstallPath = self._build_install_path(name, imageid)
        return jsonobject.dumps(rsp)

    def commit_to_imagestore(self, primaryStorageInstallPath):
        fpath = primaryStorageInstallPath

        # Add the image to registry
        cmdstr = '%s -json add -file %s' % (self.ZSTORE_CLI_PATH, fpath)

        logger.debug('adding %s to local image store' % fpath)
        shell.call(cmdstr)
        logger.debug('%s added to local image store' % fpath)

        name, imageid = self._get_image_reference(fpath)

        rsp = kvmagent.AgentResponse()
        rsp.backupStorageInstallPath = self._build_install_path(name, imageid)
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(primaryStorageInstallPath)
        return jsonobject.dumps(rsp)

    def download_from_imagestore(self, host, backupStorageInstallPath, primaryStorageInstallPath):
        name, imageid = self._parse_image_reference(backupStorageInstallPath)
        cmdstr = '%s -url %s:%s pull -installpath %s %s:%s' % (self.ZSTORE_CLI_PATH, host, self.ZSTORE_DEF_PORT, primaryStorageInstallPath, name, imageid)
        logger.debug('pulling %s:%s from image store' % (name, imageid))
        shell.call(cmdstr)
        logger.debug('%s:%s pulled to local cache' % (name, imageid))
        return
