__author__ = 'zhouhaiping'

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
import commands
import json
import time

logger = log.get_logger(__name__)
class SurfsCmdManage(object):
    def __init__(self):
        pass
    def get_pool_msg(self):
        cmdstr='surfs connect'
        i=0
        while i < 5:
            ret,rslt=commands.getstatusoutput(cmdstr)
            if ret == 0:
                
                rmsg=json.loads(rslt)
                if rmsg["success"] is False:
                    i += 1 
                    time.sleep(1)
                    continue
                else:
                    return rmsg["data"]
        return None
    
    def download_image_to_surfs(self,url,image_uuid,image_fmt):
        cmdstr='surfs image-add %s %s %s'%(url,image_fmt,image_uuid)       
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        return True
        
    def get_iamge_size(self,imageid):
        cmdstr='surfs image-info ' + imageid
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            raise Exception('Error:%s'%rslt)
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            raise Exception('Error:%s'%rslt)
        size=rmsg['data']['size']
        return size
    
    def delete_image(self,imageuuid):
        cmdstr='surfs image-del %s'%imageuuid
        ret,rslt=commands.getstatusoutput(cmdstr)
        if ret !=0:
            logger.warn(rslt)
            return False
        rmsg=json.loads(rslt)
        if rmsg['success'] is False:
            logger.warn(rslt)
            return False
        return True                
                
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

class GetLocalFileSizeRsp(AgentResponse):
    def __init__(self):
        super(GetLocalFileSizeRsp, self).__init__()
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

class SurfsAgent(object):
    INIT_PATH = "/surfs/backupstorage/init"
    DOWNLOAD_IMAGE_PATH = "/surfs/backupstorage/image/download"
    DELETE_IMAGE_PATH = "/surfs/backupstorage/image/delete"
    PING_PATH = "/surfs/backupstorage/ping"
    ECHO_PATH = "/surfs/backupstorage/echo"
    GET_IMAGE_SIZE_PATH = "/surfs/backupstorage/image/getsize"
    GET_FACTS = "/surfs/backupstorage/facts"
    GET_LOCAL_FILE_SIZE = "/surfs/backupstorage/getlocalfilesize"


    http_server = http.HttpServer(port=6732)
    http_server.logfile_path = log.get_logfile_path()
    
    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.DOWNLOAD_IMAGE_PATH, self.download)
        self.http_server.register_async_uri(self.DELETE_IMAGE_PATH, self.delete)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_async_uri(self.GET_IMAGE_SIZE_PATH, self.get_image_size)
        self.http_server.register_async_uri(self.GET_FACTS, self.get_facts)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.GET_LOCAL_FILE_SIZE, self.get_local_file_size)
        self.fsid='surfsc48-2cef-454c-b0d0-b6e6b467c022'
        self.tmp_image_path='/usr/lib/surfstmpimages'
        if os.path.exists(self.tmp_image_path) is False:
            shell.call('mkdir %s'%self.tmp_image_path)
        self.surfs_mgr = SurfsCmdManage()
    
    def _normalize_install_path(self, path):
        return path.lstrip('surfs:').lstrip('//')    

    def _set_capacity_to_response(self, rsp):
        cmdstr='surfs connect'
        total = 0
        used = 0
        rmsg=self.surfs_mgr.get_pool_msg()
        for pl in rmsg:
            if pl["success"] is True:
                total=total + pl["total"]
                used=used + pl["used"]
        rsp.totalCapacity = total
        rsp.availableCapacity = total - used

    def _parse_install_path(self, path):
        return path.lstrip('surfs:').lstrip('//').split('/')
        
    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @replyerror
    def get_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetFactsRsp()
        rsp.fsid = self.fsid
        return jsonobject.dumps(rsp)

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = InitRsp()
        rsp.fsid = self.fsid
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    @rollback
    def download(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)
        tmp_image_name = 'tmp-%s' % image_name

        formated_file = os.path.join(self.tmp_image_path, image_name)
        tmp_image_file = os.path.join(self.tmp_image_path, tmp_image_name)

       
        if cmd.url.startswith('http://') or cmd.url.startswith('https://'):
            cmd.url = linux.shellquote(cmd.url)
            actual_size = linux.get_file_size_by_http_head(cmd.url)            
        elif cmd.url.startswith('file://'):
            src_path = cmd.url.lstrip('file:')
            src_path = os.path.normpath(src_path)
            if not os.path.isfile(src_path):
                raise Exception('cannot find the file[%s]' % src_path)
            actual_size = os.path.getsize(src_path)
        else:
            raise Exception('unknown url[%s]' % cmd.url)

        file_format = ''
        if "raw" in cmd.imageFormat:
            file_format = 'raw'
        if "qcow2" in cmd.imageFormat:
            file_format = 'qcow2'
        if file_format not in ['qcow2', 'raw']:
            raise Exception('unknown image format: %s' % file_format)
        
        if self.surfs_mgr.download_image_to_surfs(cmd.url, image_name,file_format) is False:
            raise Exception('Can not download image from %s'%cmd.url)
                                       
        size = self.surfs_mgr.get_iamge_size(image_name)
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
            rmsg=self.surfs_mgr.get_pool_msg()
            if rmsg is None:
                rsp.success = False
                rsp.operationFailure = True
                rsp.error = "can not to do surfs connect"
                logger.debug("%s" % rsp.error)
            else:
                if len(rmsg)> 0:
                    for rsg in rmsg:
                        if rsg['success'] is False:
                            rsp.success = False
                            rsp.operationFailure = True
                            rsp.error = "Surfs is ready,but pool is breaken"
                            logger.debug("Surfs is ready,but pool is breaken")
                            break
                else:
                    rsp.success = False
                    rsp.operationFailure = True
                    rsp.error = "Surfs is ready,but pool is Null"
                    logger.debug("Surfs is ready,but pool is Null")                    

        return jsonobject.dumps(rsp)

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)
        self.surfs_mgr.delete_image(image_name)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def get_local_file_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetLocalFileSizeRsp()
        filedir=cmd.path[7:]
        if os.path.exists(filedir):
            rsp.size = linux.get_local_file_size(filedir)
        else:
            rsp.size=0
            rsp.success=False
            rsp.error ="The file is not exist"
        return jsonobject.dumps(rsp)

    def _get_file_size(self,pool,image_name):
        return self.surfs_mgr.get_iamge_size(image_name)

    @replyerror
    def get_image_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetImageSizeRsp()
        pool, image_name = self._parse_install_path(cmd.installPath)
        rsp.size = self._get_file_size(pool,image_name)
        return jsonobject.dumps(rsp)



class SurfsDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(SurfsDaemon, self).__init__(pidfile)

    def run(self):
        self.agent = SurfsAgent()
        self.agent.http_server.start()
