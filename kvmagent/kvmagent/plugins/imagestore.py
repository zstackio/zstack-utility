import os.path
import traceback

from os import symlink
from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell

logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self):
        self.totalCapacity = None
        self.availableCapacity = None
        self.success = None
        self.error = None

class ImageStorePlugin(kvmagent.KvmAgent):

    ZSTORE_PROTOSTR = "zstore://"
    ZSTORE_CLI_PATH = "/usr/local/zstack/imagestore/zstcli"
    UPLOAD_BIT_PATH = "/imagestore/upload"
    DOWNLOAD_BIT_PATH = "/imagestore/download"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.DOWNLOAD_BIT_PATH, self.download_from_imagestore)
        http_server.register_async_uri(self.UPLOAD_BIT_PATH, self.upload_to_imagestore)

        self.path = None

    def stop(self):
        pass

    def _get_disk_capacity(self):
        return linux.get_disk_capacity_by_df(self.path)

    def _getImageJSONFile(primaryInstallPath):
        idx = primaryInstallPath.rfind('.')
        if idx == -1:
            return primaryInstallPath + ".json"
        return primaryInstallPath[:idx] + ".json"

    def _get_image_reference(self, primaryStorageInstallPath):
        try:
            with open(self._getImageJSONFile(primaryStorageInstallPath)) as f:
                imf = jsonobject.loads(f.read())
                return imf.Name, imf.ID
        except IOError:
            raise kvmagent.KvmError('unexpected primary storage install path %s' % primaryStorageInstallPath)

    def _parse_image_reference(self, backupStorageInstallPath):
        if not primaryStorageInstallPath.startswith(self.ZSTORE_PROTOSTR):
            raise kvmagent.KvmError('unexpected primary storage install path %s' % primaryStorageInstallPath)

        xs = primaryStorageInstallPath[len(self.ZSTORE_PROTOSTR):].split('/')
        if len(xs) != 2:
            raise kvmagent.KvmError('unexpected primary storage install path %s' % primaryStorageInstallPath)

        return xs[0], xs[1]

    def _build_install_path(self, name, imgid):
        return "{0}{1}/{2}".format(self.ZSTORE_PROTOSTR, name, imgid)

    @kvmagent.replyerror
    def upload_to_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        name, imgid = self._get_image_reference(cmd.primaryStorageInstallPath)
        cmdstr = '%s push %s' % (self.ZSTORE_CLI_PATH, name)
        logger.debug('pushing %s:%s to image store' % (name, imageid))
        shell.call(cmdstr)
        logger.debug('%s:%s pushed to image store' % (name, imageid))

        rsp.backupStorageInstallPath = self._build_install_path(name, imgid)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def download_from_imagestore(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        name, imgid = self._parse_image_reference(cmd.backupStorageInstallPath)
        cmdstr = '%s pull %s:%s' % (self.ZSTORE_CLI_PATH, name, imageid)
        logger.debug('pulling %s:%s from image store' % (name, imageid))
        shell.call(cmdstr)
        logger.debug('%s:%s pulled to local cache' % (name, imageid))

        # get the image JSON path, and generate a symbolic link
        cmdstr = "%s mfpath %s:%s" % (self.ZSTORE_CLI_PATH, name, imageid)
        mfpath = shell.call(cmdstr)
        symlink(mfpath, self._getImageJSONFile(cmd.primaryStorageInstallPath))

        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity()
        return jsonobject.dumps(rsp)
