from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils.bash import bash_r

logger = log.get_logger(__name__)


class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None


class ImageStoreClient(object):
    ZSTORE_CLI_PATH = "/usr/local/zstack/imagestore/bin/zstcli -rootca /var/lib/zstack/imagestorebackupstorage/package/certs/ca.pem"
    ZSTORE_PROTOSTR = "zstore://"
    ZSTORE_DEF_PORT = 8000

    def _parse_image_reference(self, bs_install_path):
        if not bs_install_path.startswith(self.ZSTORE_PROTOSTR):
            raise Exception('unexpected backup storage install path %s' % bs_install_path)

        xs = bs_install_path[len(self.ZSTORE_PROTOSTR):].split('/')
        if len(xs) != 2:
            raise Exception('unexpected backup storage install path %s' % bs_install_path)

        return xs[0], xs[1]

    def download_image_from_imagestore(self, cmd):
        rsp = AgentResponse()
        name, imageid = self._parse_image_reference(cmd.imageInstallPath)
        cmdstr = '%s -url %s:%s pull -installpath %s %s:%s' % (
            self.ZSTORE_CLI_PATH, cmd.hostname, self.ZSTORE_DEF_PORT, cmd.cacheInstallPath, name, imageid)
        logger.debug('pulling %s:%s from image store' % (name, imageid))
        ret = bash_r(cmdstr)
        if ret != 0:
            rsp.success = False
            rsp.error = "failed to download image from imagestore to baremetal image cache"
        else:
            logger.debug('%s:%s pulled to baremetal pxeserver' % (name, imageid))
        return rsp
