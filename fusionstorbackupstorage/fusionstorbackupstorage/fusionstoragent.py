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
import zstacklib.utils.lichbd_factory as lichbdfactory
from zstacklib.utils import plugin
from zstacklib.utils.rollback import rollback, rollbackable
import os
import os.path
import errno
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
        self.actualSize = None

class GetImageSizeRsp(AgentResponse):
    def __init__(self):
        super(GetImageSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None

class PingRsp(AgentResponse):
    def __init__(self):
        super(PingRsp, self).__init__()
        self.operationFailure = False

class GetFactsRsp(AgentResponse):
    def __init__(self):
        super(GetFactsRsp, self).__init__()
        self.fsid = None

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
    GET_IMAGE_SIZE_PATH = "/fusionstor/backupstorage/image/getsize"
    GET_FACTS = "/fusionstor/backupstorage/facts"

    http_server = http.HttpServer(port=7763)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.DOWNLOAD_IMAGE_PATH, self.download)
        self.http_server.register_async_uri(self.DELETE_IMAGE_PATH, self.delete)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_async_uri(self.GET_IMAGE_SIZE_PATH, self.get_image_size)
        self.http_server.register_async_uri(self.GET_FACTS, self.get_facts)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)

    def _set_capacity_to_response(self, rsp):
        total, used = lichbd.lichbd_get_capacity()
        rsp.totalCapacity = total
        rsp.availableCapacity = total - used

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    def _normalize_install_path(self, path):
        return path.lstrip('fusionstor:').lstrip('//')

    def _get_file_size(self, path):
        return lichbd.lichbd_file_size(path)

    @replyerror
    def get_image_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetImageSizeRsp()
        path = self._normalize_install_path(cmd.installPath)
        rsp.size = self._get_file_size(path)
        return jsonobject.dumps(rsp)

    @replyerror
    def get_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        rsp = GetFactsRsp()
        rsp.fsid = lichbd.lichbd_get_fsid()
        return jsonobject.dumps(rsp)

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        existing_pools = lichbd.lichbd_lspools()
        for pool in cmd.pools:
            if pool.predefined and pool.name not in existing_pools:
                raise Exception('cannot find pool[%s] in the fusionstor cluster, you must create it manually' % pool.name)
            elif pool.name not in existing_pools:
                lichbd.lichbd_mkpool(pool.name)

        rsp = InitRsp()
        rsp.fsid = lichbd.lichbd_get_fsid()
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

        protocol = lichbd.get_protocol()
        lichbd.lichbd_mkpool(os.path.dirname(lichbd_file))

        @rollbackable
        def _1():
            if lichbd.lichbd_file_exist(tmp_lichbd_file):
                lichbd.lichbd_rm(tmp_lichbd_file)
            if lichbd.lichbd_file_exist(lichbd_file):
                lichbd.lichbd_rm(lichbd_file)

        _1()

        if cmd.url.startswith('http://') or cmd.url.startswith('https://'):
            cmd.url = linux.shellquote(cmd.url)
            shell.call('set -o pipefail; wget --no-check-certificate -q -O - %s | %s - %s -p %s' % (cmd.url,lichbdfactory.get_lichbd_version_class().LICHBD_CMD_VOL_IMPORT, tmp_lichbd_file, protocol))
            actual_size = linux.get_file_size_by_http_head(cmd.url)
        elif cmd.url.startswith('file://'):
            src_path = cmd.url.lstrip('file:')
            src_path = os.path.normpath(src_path)
            if not os.path.isfile(src_path):
                raise Exception('cannot find the file[%s]' % src_path)
            lichbd.lichbd_import(src_path, tmp_lichbd_file)
            actual_size = os.path.getsize(src_path)
        else:
            raise Exception('unknown url[%s]' % cmd.url)



        file_format = lichbd.lichbd_get_format(tmp_lichbd_file)
        if file_format not in ['qcow2', 'raw']:
            raise Exception('unknown image format: %s' % file_format)


        lichbd.lichbd_mv(lichbd_file, tmp_lichbd_file)

        size = lichbd.lichbd_file_size(lichbd_file)

        rsp = DownloadRsp()
        rsp.size = size
        rsp.actualSize = actual_size
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = PingRsp()

        if cmd.testImagePath:
            pool = cmd.testImagePath.split('/')[0]
            testImagePath = '%s/this-is-a-test-image-with-long-name' % pool
            shellcmd = lichbd.lichbd_file_info(testImagePath)
            if shellcmd.return_code == errno.ENOENT:
                try:
                    lichbd.lichbd_create_raw(testImagePath, '1b')
                except Exception, e:
                    rsp.success = False
                    rsp.operationFailure = True
                    rsp.error = str(e)
                    logger.debug("%s" % rsp.error)
            elif shellcmd.return_code == 0:
                pass
            else:
                rsp.success = False
                rsp.operationFailure = True
                rsp.error = "%s %s" % (shellcmd.cmd, shellcmd.stderr)
                logger.debug("%s: %s" % (shellcmd.cmd, shellcmd.stderr))

        return jsonobject.dumps(rsp)

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)
        protocol = lichbd.get_protocol()
        lichbd_file = os.path.join(pool, image_name)
        lichbd.lichbd_rm(lichbd_file)
        if protocol == 'lichbd':
            lichbd.lichbd_rm(lichbd_file, "iscsi")

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)


class FusionstorDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(FusionstorDaemon, self).__init__(pidfile)

    def run(self):
        self.agent = FusionstorAgent()
        self.agent.http_server.start()


