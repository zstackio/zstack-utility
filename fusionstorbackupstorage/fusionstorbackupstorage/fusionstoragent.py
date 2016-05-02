__author__ = 'frank'

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.log as log
import zstacklib.utils.shell as shell
import zstacklib.utils.lichbd as lichbd
import zstacklib.utils.iptables as iptables
import zstacklib.utils.jsonobject as jsonobject
import zstacklib.utils.lock as lock
import zstacklib.utils.linux as linux
import zstacklib.utils.sizeunit as sizeunit
from zstacklib.utils import plugin
from zstacklib.utils.rollback import rollback, rollbackable
import os
import functools
import traceback
import pprint
import threading

logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None

class InitRsp(AgentResponse):
    def __init__(self):
        super(InitRsp, self).__init__()
        self.fsid = None

class DownloadRsp(AgentResponse):
    def __init__(self):
        super(DownloadRsp, self).__init__()
        self.size = None

def replyerror(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            content = traceback.format_exc()
            err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
            rsp = AgentResponse()
            rsp.success = False
            rsp.error = str(e)
            logger.warn(err)
            return jsonobject.dumps(rsp)
    return wrap

class FusionstorAgent(object):
    INIT_PATH = "/fusionstor/backupstorage/init"
    DOWNLOAD_IMAGE_PATH = "/fusionstor/backupstorage/image/download"
    DELETE_IMAGE_PATH = "/fusionstor/backupstorage/image/delete"
    PING_PATH = "/fusionstor/backupstorage/ping"
    ECHO_PATH = "/fusionstor/backupstorage/echo"

    http_server = http.HttpServer(port=7763)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.DOWNLOAD_IMAGE_PATH, self.download)
        self.http_server.register_async_uri(self.DELETE_IMAGE_PATH, self.delete)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)

    def _set_capacity_to_response(self, rsp):
        total = lichbd.lichbd_get_capacity()
        used = lichbd.lichbd_get_used()
        rsp.totalCapacity = total
        rsp.availableCapacity = total - used

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @replyerror
    def init(self, req):
        rsp = InitRsp()
        rsp.fsid = "96a91e6d-892a-41f4-8fd2-4a18c9002425"
        self._set_capacity_to_response(rsp)

        return jsonobject.dumps(rsp)

    def _parse_install_path(self, path):
        return path.lstrip('fusionstor:').lstrip('//').split('/')

    @replyerror
    @rollback
    def download(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)
        tmp_image_name = 'tmp-%s' % image_name

        lichbd_file = os.path.join(pool, image_name)
        tmp_lichbd_file = os.path.join(pool, tmp_image_name)

        lichbd.lichbd_mkpool(os.path.dirname(lichbd_file))
        shell.call('set -o pipefail; wget --no-check-certificate -q -O - %s | lichbd import - %s -p lichbd' % (cmd.url, tmp_lichbd_file))

        @rollbackable
        def _1():
            lichbd.lichbd_rm(lichbd_file)
        _1()

        qemu_img = lichbd.lichbd_get_qemu_img_path()
        file_format = shell.call("set -o pipefail;%s info rbd:%s/%s 2>/dev/null | grep 'file format' | cut -d ':' -f 2" % (qemu_img, pool, tmp_image_name))
        file_format = file_format.strip()
        if file_format not in ['qcow2', 'raw']:
            raise Exception('unknown image format: %s' % file_format)

        if file_format == 'qcow2':
            shell.call('%s convert -f qcow2 -O rbd rbd:%s/%s rbd:%s/%s' % (qemu_img, pool, tmp_image_name, pool, image_name))
            lichbd.lichbd_rm(tmp_lichbd_file)
        else:
            lichbd.lichbd_mv(lichbd_file, tmp_lichbd_file)

        size = lichbd.lichbd_file_size(lichbd_file)
        rsp = DownloadRsp()
        rsp.size = size
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)
        lichbd_file = os.path.join(pool, image_name)
        lichbd.lichbd_rm(lichbd_file)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)


class FusionstorDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(FusionstorDaemon, self).__init__(pidfile)

    def run(self):
        self.agent = FusionstorAgent()
        self.agent.http_server.start()


