__author__ = 'Xingwei Yu'

import traceback
import pprint

import zstacklib.utils.jsonobject as jsonobject

from zstacklib.utils import plugin
from zstacklib.utils import daemon
from zstacklib.utils.report import *
from zstacklib.utils.bash import *

log.configure_log('/var/log/zstack/zbs-primarystorage.log')
logger = log.get_logger(__name__)
import zbsutils


class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''

    def set_error(self, error):
        self.success = False
        self.error = error


class CreateVolumeRsp(AgentResponse):
    def __init__(self):
        super(CreateVolumeRsp, self).__init__()
        self.size = 0


class GetCapacityRsp(AgentResponse):
    def __init__(self):
        super(GetCapacityRsp, self).__init__()
        self.capacity = None
        self.storedSize = None


class GetFactsRsp(AgentResponse):
    def __init__(self):
        super(GetFactsRsp, self).__init__()
        self.version = None


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


class ZbsAgent(plugin.TaskManager):
    ECHO_PATH = "/zbs/primarystorage/echo"
    GET_FACTS_PATH = "/zbs/primarystorage/facts"
    GET_CAPACITY_PATH = "/zbs/primarystorage/capacity"
    CREATE_VOLUME_PATH = "/zbs/primarystorage/volume/create"
    DELETE_VOLUME_PATH = "/zbs/primarystorage/volume/delete"

    http_server = http.HttpServer(port=7763)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        super(ZbsAgent, self).__init__()
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.GET_FACTS_PATH, self.get_facts)
        self.http_server.register_async_uri(self.GET_CAPACITY_PATH, self.get_capacity)
        self.http_server.register_async_uri(self.CREATE_VOLUME_PATH, self.create_volume)
        self.http_server.register_async_uri(self.DELETE_VOLUME_PATH, self.delete_volume)

    @replyerror
    def delete_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()

        zbsutils.do_delete_volume(cmd.installPath)

        return jsonobject.dumps(rsp)

    @replyerror
    def create_volume(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateVolumeRsp()

        physicalPoolName = zbsutils.get_physical_pool_name(cmd.logicalPoolName)
        logicalPoolName = cmd.logicalPoolName
        volumeName = cmd.volumeName
        volumeSize = cmd.size

        if cmd.skipIfExisting and zbsutils.do_query_volume(logicalPoolName, volumeName) == 0:
            return jsonobject.dumps(rsp)

        o = zbsutils.do_create_volume(logicalPoolName, volumeName, volumeSize)
        ret = jsonobject.loads(o)
        if ret.error.code != 0:
            raise Exception('failed to create volume[%s] on zbs, error[%s]' % (volumeName, ret.error.message))

        o = zbsutils.do_query_volume_info(logicalPoolName, volumeName)
        rsp.size = jsonobject.loads(o).result.info.fileInfo.length
        rsp.installPath = "cbd:%s/%s/%s" % (physicalPoolName, logicalPoolName, volumeName)

        return jsonobject.dumps(rsp)

    @replyerror
    def get_capacity(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetCapacityRsp()

        o = zbsutils.do_query_logical_pool_info()

        found = False
        for lp in jsonobject.loads(o).result[0].logicalPoolInfos:
            if cmd.logicalPoolName in lp.logicalPoolName:
                rsp.capacity = lp.capacity
                rsp.storedSize = lp.storedSize
                found = True
                break

        if not found:
            raise Exception('cannot find logical pool[%s] in the zbs storage, you must create it manually' % cmd.logicalPoolName)

        return jsonobject.dumps(rsp)

    @replyerror
    def get_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetFactsRsp()

        o = zbsutils.do_query_mds_status_info()

        found = False
        for mds in jsonobject.loads(o).result:
            if cmd.mdsAddr in mds.addr:
                rsp.version = mds.version
                found = True
                break

        if not found:
            rsp.success = False
            rsp.error = 'The mds addr is not found on the zbs server[uuid:%s], not %s anymore.' % (cmd.psUuid, cmd.mdsAddr)
            return jsonobject.dumps(rsp)

        return jsonobject.dumps(rsp)

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''


class ZbsDaemon(daemon.Daemon):
    def __init__(self, pidfile, py_process_name):
        super(ZbsDaemon, self).__init__(pidfile, py_process_name)

    def run(self):
        self.agent = ZbsAgent()
        self.agent.http_server.start()
