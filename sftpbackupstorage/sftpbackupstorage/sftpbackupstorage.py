'''

@author: frank
'''

from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import jsonobject
from zstacklib.utils import sizeunit
from zstacklib.utils import linux
from zstacklib.utils import shell
from zstacklib.utils import daemon
import functools
import traceback
import pprint
import os.path
import os
import shutil

logger = log.get_logger(__name__)

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None

class AgentCommand(object):
    def __init__(self):
        pass

class PingCommand(AgentCommand):
    def __init__(self):
        super(PingCommand, self).__init__()

class PingResponse(AgentResponse):
    def __init__(self):
        super(PingResponse, self).__init__()
        self.uuid = None
    
class ConnectCmd(AgentCommand):
    def __init__(self):
        super(ConnectCmd, self).__init__()
        self.storagePath = None

class ConnectResponse(AgentResponse):
    def __init__(self):
        super(ConnectResponse, self).__init__()

class DeleteCmd(AgentCommand):
    def __init__(self):
        super(DeleteCmd, self).__init__()
        self.installUrl = None

class DeleteResponse(AgentResponse):
    def __init__(self):
        super(DeleteResponse, self).__init__()

class DownloadCmd(AgentCommand):
    def __init__(self):
        super(DownloadCmd, self).__init__()
        self.imageUuid = None
        self.name = None
        self.url = None
        self.format = None
        self.accountUuid = None
        self.hypervisorType = None
        self.guestOsType = None
        self.description = None
        self.bits = None
        self.timeout = None
        self.urlScheme = None
        self.installPath = None

class DownloadResponse(AgentResponse):
    def __init__(self):
        super(DownloadResponse, self).__init__()
        self.imageUuid = None
        self.md5Sum = None
        self.size = None

class WriteImageMetaDataResponse(AgentResponse):
    def __init__(self):
        super(WriteImageMetaDataResponse,self).__init__()

class WriteImageMetaDataCmd(AgentCommand):
    def __init__(self):
        super(WriteImageMetaDataCmd, self).__init__()
        self.metaData = None
        
class GetSshKeyCommand(AgentCommand):
    def __init__(self):
        super(GetSshKeyCommand, self).__init__()

class GetSshKeyResponse(AgentResponse):
    def __init__(self):
        self.sshKey = None
        super(GetSshKeyResponse, self).__init__()
        
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

class SftpBackupStorageAgent(object):
    '''
    classdocs
    '''

    
    CONNECT_PATH = "/sftpbackupstorage/connect"
    DOWNLOAD_IMAGE_PATH = "/sftpbackupstorage/download"
    DELETE_IMAGE_PATH = "/sftpbackupstorage/delete"
    PING_PATH = "/sftpbackupstorage/ping"
    GET_SSHKEY_PATH = "/sftpbackupstorage/sshkey"
    ECHO_PATH = "/sftpbackupstorage/echo"
    WRITE_IMAGE_METADATA = "/sftpbackupstorage/writeimagemetadata"
    
    IMAGE_TEMPLATE = 'template'
    IMAGE_ISO = 'iso'
    URL_HTTP = 'http'
    URL_HTTPS = 'https'
    URL_FILE = 'file'
    URL_NFS = 'nfs'
    PORT = 7171
    SSHKEY_PATH = "~/.ssh/id_rsa.sftp"
    
    http_server = http.HttpServer(PORT)
    http_server.logfile_path = log.get_logfile_path()
    
    def get_capacity(self):
        total = linux.get_total_disk_size(self.storage_path)
        used = linux.get_used_disk_size(self.storage_path)
        return (total, total - used)
        
    @replyerror
    def ping(self, req):
        rsp = PingResponse()
        rsp.uuid = self.uuid
        return jsonobject.dumps(rsp)
    
    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''
        
    @replyerror
    def connect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.storage_path = cmd.storagePath
        self.uuid = cmd.uuid
        if os.path.isfile(self.storage_path):
            raise Exception('storage path: %s is a file' % self.storage_path)
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path, 0755)
        (total, avail) = self.get_capacity()
        logger.debug(http.path_msg(self.CONNECT_PATH, 'connected, [storage path:%s, total capacity: %s bytes, available capacity: %s size]' % (self.storage_path, total, avail)))
        rsp = ConnectResponse()
        rsp.totalCapacity = total
        rsp.availableCapacity = avail
        return jsonobject.dumps(rsp)
    
    def _write_image_metadata(self, image_install_path, meta_data):
        image_dir = os.path.dirname(image_install_path)
        md5sum = linux.md5sum(image_install_path)
        size = os.path.getsize(image_install_path)
        meta = dict(meta_data.__dict__.items())
        meta['size'] = size
        meta['md5sum'] = md5sum
        metapath = os.path.join(image_dir, 'meta_data.json')
        with open(metapath, 'w') as fd:
            fd.write(jsonobject.dumps(meta, pretty=True))
        return (size, md5sum)
    
    @replyerror
    def write_image_metadata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        meta_data = cmd.metaData
        self._write_image_metadata(meta_data.installPath, meta_data)
        rsp = WriteImageMetaDataResponse()
        return jsonobject.dumps(rsp)
    
    @replyerror
    def download_image(self, req):
        #TODO: report percentage to mgmt server
        def percentage_callback(percent, url):
            logger.debug('Downloading %s ... %s%%' % (url, percent))
                
        def use_wget(url, name, workdir, timeout):
            return linux.wget(url, workdir=workdir, rename=name, timeout=timeout, interval=2, callback=percentage_callback, callback_data=url)
        
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DownloadResponse()
        supported_schemes = [self.URL_HTTP, self.URL_HTTPS, self.URL_FILE]
        if cmd.urlScheme not in supported_schemes:
            rsp.success = False
            rsp.error = 'unsupported url scheme[%s], SimpleSftpBackupStorage only supports %s' % (cmd.urlScheme, supported_schemes)
            return jsonobject.dumps(rsp)
        
        path = os.path.dirname(cmd.installPath)
        if not os.path.exists(path):
            os.makedirs(path, 0755)
        image_name = os.path.basename(cmd.installPath)
        install_path = cmd.installPath
        
        timeout = cmd.timeout if cmd.timeout else 7200
        if cmd.urlScheme in [self.URL_HTTP, self.URL_HTTPS]:
            try:
                ret = use_wget(cmd.url, image_name, path, timeout)
                if ret != 0:
                    rsp.success = False
                    rsp.error = 'http/https download failed, [wget -O %s %s] returns value %s' % (image_name, cmd.url, ret)
                    return jsonobject.dumps(rsp)
            except linux.LinuxError as e:
                traceback.format_exc()
                rsp.success = False
                rsp.error = str(e)
                return jsonobject.dumps(rsp)
        elif cmd.urlScheme == self.URL_FILE:
            src_path = cmd.url.lstrip('file:')
            src_path = os.path.normpath(src_path)
            if not os.path.isfile(src_path):
                raise Exception('cannot find the file[%s]' % src_path)

            shell.call('yes | cp %s %s' % (src_path, install_path))

        size = os.path.getsize(install_path)
        md5sum = 'not calculated'
        logger.debug('successfully downloaded %s to %s' % (cmd.url, install_path))
        (total, avail) = self.get_capacity()
        rsp.md5Sum = md5sum
        rsp.size = size
        rsp.totalCapacity = total
        rsp.availableCapacity = avail
        return jsonobject.dumps(rsp)
    
    @replyerror
    def delete_image(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = DeleteResponse()
        path = os.path.dirname(cmd.installUrl)
        shutil.rmtree(path)
        logger.debug('successfully deleted bits[%s]' % cmd.installUrl)
        (total, avail) = self.get_capacity()
        rsp.totalCapacity = total
        rsp.availableCapacity = avail
        return jsonobject.dumps(rsp)
    
    @replyerror
    def get_sshkey(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetSshKeyResponse()
        path = os.path.expanduser(self.SSHKEY_PATH)
        if not os.path.exists(path):
            err = "Cannot find private key of SftpBackupStorageAgent"
            rsp.error = err
            rsp.success = False
            logger.warn("%s at %s" %(err, self.SSHKEY_PATH))
            return jsonobject.dumps(rsp)
        
        with open(path) as fd:
            sshkey = fd.read()
            rsp.sshKey = sshkey
            logger.debug("Get sshkey as %s" % sshkey)
            return jsonobject.dumps(rsp)
        
    def __init__(self):
        '''
        Constructor
        '''
        self.http_server.register_sync_uri(self.CONNECT_PATH, self.connect)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.DOWNLOAD_IMAGE_PATH, self.download_image)
        self.http_server.register_async_uri(self.DELETE_IMAGE_PATH, self.delete_image)
        self.http_server.register_async_uri(self.GET_SSHKEY_PATH, self.get_sshkey)
        self.http_server.register_async_uri(self.WRITE_IMAGE_METADATA, self.write_image_metadata)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.storage_path = None
        self.uuid = None

class SftpBackupStorageDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(SftpBackupStorageDaemon, self).__init__(pidfile)
    
    def run(self):
        self.agent = SftpBackupStorageAgent()
        self.agent.http_server.start()

def _build_url_for_test(paths):
    builder = http.UriBuilder('http://localhost:%s' % SftpBackupStorageAgent.PORT)
    for p in paths:
        builder.add_path(p)
    return builder.build()
