__author__ = 'frank'

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.log as log
import zstacklib.utils.shell as shell
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

class CephAgent(object):
    INIT_PATH = "/ceph/backupstorage/init"
    DOWNLOAD_IMAGE_PATH = "/ceph/backupstorage/image/download"
    DELETE_IMAGE_PATH = "/ceph/backupstorage/image/delete"
    PING_PATH = "/ceph/backupstorage/ping"
    ECHO_PATH = "/ceph/backupstorage/echo"

    http_server = http.HttpServer(port=7761)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.DOWNLOAD_IMAGE_PATH, self.download)
        self.http_server.register_async_uri(self.DELETE_IMAGE_PATH, self.delete)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)

    def _set_capacity_to_response(self, rsp):
        o = shell.call('ceph df -f json')
        df = jsonobject.loads(o)

        total = long(df.stats.total_bytes_)
        avail = long(df.stats.total_avail_bytes_)
        rsp.totalCapacity = total
        rsp.availableCapacity = avail

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        o = shell.call('ceph mon_status')
        mon_status = jsonobject.loads(o)
        fsid = mon_status.monmap.fsid_

        existing_pools = shell.call('ceph osd lspools')
        for pool in cmd.poolNames:
            if pool not in existing_pools:
                shell.call('ceph osd pool create %s 100' % pool)

        rsp = InitRsp()
        rsp.fsid = fsid
        self._set_capacity_to_response(rsp)

        return jsonobject.dumps(rsp)

    def _parse_install_path(self, path):
        path = path.lstrip('ceph://')
        return path.split('/')

    @replyerror
    @rollback
    def download(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        def get_file_size(url):
            output = shell.call('curl --head %s' % url)
            for l in output.split('\n'):
                if 'Content-Length' in l:
                    filesize = l.split(':')[1].strip()
                    return long(filesize)
            return None

        image_size = get_file_size(cmd.url)
        if not image_size:
            raise Exception('cannot get the size of %s through http header; we cannot create a rbd image because of this' % cmd.url)

        pool, image_name = self._parse_install_path(cmd.installPath)
        tmp_image_name = 'tmp-%s' % image_name
        # additional 1M
        image_size_M = sizeunit.Byte.toMegaByte(image_size) + 1
        shell.call('rbd create --size %s %s/%s' % (image_size_M, pool, tmp_image_name))

        @rollbackable
        def _1():
            shell.call('rbd rm %s/%s' % (pool, tmp_image_name))
        _1()

        rbd_path = shell.call('rbd map %s/%s' % (pool, tmp_image_name))
        rbd_path = rbd_path.strip(' \t\n\r')
        @rollbackable
        def _2():
            shell.call('ls %s &> /dev/null && rbd unmap %s' % (rbd_path, rbd_path), exception=False)
        _2()

        shell.call('wget --no-check-certificate %s -O %s' % (cmd.url, rbd_path))

        file_format = shell.call("qemu-img info %s | grep 'file format' | cut -d ':' -f 2" % rbd_path)
        file_format = file_format.strip()
        if file_format not in ['qcow2', 'raw']:
            raise Exception('unknown image format: %s' % file_format)

        if file_format == 'qcow2':
            shell.call('qemu-img convert -f qcow2 -O raw %s rbd:%s/%s' % (rbd_path, pool, image_name))
            shell.call('rbd unmap %s' % rbd_path)
            shell.call('rbd rm %s/%s' % (pool, tmp_image_name))
        else:
            shell.call('rbd unmap %s' % rbd_path)
            shell.call('rbd mv %s/%s %s/%s' % (pool, tmp_image_name, pool, image_name))

        o = shell.call('rbd --format json info %s/%s' % (pool, image_name))
        image_stats = jsonobject.loads(o)

        rsp = DownloadRsp()
        rsp.size = long(image_stats.size_)
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        return jsonobject.dumps(AgentResponse())

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)
        shell.call('rbd rm %s/%s' % (pool, image_name))

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)


class CephDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(CephDaemon, self).__init__(pidfile)

    def run(self):
        self.agent = CephAgent()
        self.agent.http_server.start()


