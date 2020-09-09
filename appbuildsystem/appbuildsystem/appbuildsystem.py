__author__ = 'mingjian.deng'

import os
import os.path
import pprint
import traceback

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils.bash import *
from zstacklib.utils import shell
import shutil
import base64
import re

logger = log.get_logger(__name__)

pic_prefix = "data:image/png;base64,"

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

def checkParam(**kwargs):
    for k,v in kwargs.items():
        if v is None:
            raise Exception("%s cannot be None" % k)

class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None

class CheckPathRsp(AgentResponse):
    def __init__(self):
        super(CheckPathRsp, self).__init__()
        self.srcSize = None
        self.imageInfos = []

class CreateAppRsp(AgentResponse):
    def __init__(self):
        super(CreateAppRsp, self).__init__()
        self.dstSize = None
        self.dstPath = None
        self.imageInfos = None
        self.template = None
        self.dstInfo = None
        self.logo = None
        self.thumbs = []

class ExportAppRsp(AgentResponse):
    def __init__(self):
        super(ExportAppRsp, self).__init__()
        self.exportPath = None
        self.md5Sum = None
        self.size = None

class RawAppRsp(AgentResponse):
    def __init__(self):
        super(RawAppRsp, self).__init__()
        self.totalSize = None
        self.appCtx = None

class AppBuildSystemAgent(object):
    CHECK_BUILDSYSTEM_PATH = "/appcenter/buildsystem/checkpath"
    CONNECT_BUILDSYSTEM_PATH = "/appcenter/buildsystem/connect"
    ECHO_BUILDSYSTEM_PATH = "/appcenter/buildsystem/echo"
    PING_BUILDSYSTEM_PATH = "/appcenter/buildsystem/ping"
    CREATE_APPLICATION_PATH = "/appcenter/buildsystem/createapp"
    DELETE_APPLICATION_PATH = "/appcenter/buildsystem/deleteapp"
    EXPORT_APPLICATION_PATH = "/appcenter/buildsystem/exportapp"
    DELETE_EXPORT_APPLICATION_PATH = "/appcenter/buildsystem/deleteexportapp"

    UNZIP_BUILDAPP = "/appcenter/rawapp/unzip"
    CLEAN_UNZIP_BUILDAPP = "/appcenter/rawapp/cleanunzip"
    DOWNLOAD_BUILDAPP = "/appcenter/rawapp/download"
    DELETE_DOWNLOAD_BUILDAPP = "/appcenter/rawapp/deletedownload"

    LENGTH_OF_UUID = 32

    http_server = http.HttpServer(port=7079)
    http_server.logfile_path = log.get_logfile_path()

    def __init__(self):
        self.http_server.register_sync_uri(self.ECHO_BUILDSYSTEM_PATH, self.echo)
        self.http_server.register_async_uri(self.CHECK_BUILDSYSTEM_PATH, self.checkpath)
        self.http_server.register_async_uri(self.CONNECT_BUILDSYSTEM_PATH, self.collect)
        self.http_server.register_async_uri(self.PING_BUILDSYSTEM_PATH, self.ping)
        self.http_server.register_async_uri(self.CREATE_APPLICATION_PATH, self.create)
        self.http_server.register_async_uri(self.DELETE_APPLICATION_PATH, self.delete)
        self.http_server.register_async_uri(self.EXPORT_APPLICATION_PATH, self.export)
        self.http_server.register_async_uri(self.DELETE_EXPORT_APPLICATION_PATH, self.delexport)
        self.http_server.register_async_uri(self.UNZIP_BUILDAPP, self.unzipapp)
        self.http_server.register_async_uri(self.CLEAN_UNZIP_BUILDAPP, self.deleteunzip)
        self.http_server.register_async_uri(self.DOWNLOAD_BUILDAPP, self.downloadapp)
        self.http_server.register_async_uri(self.DELETE_DOWNLOAD_BUILDAPP, self.deletedownload)

    @staticmethod
    def _get_disk_capacity(path):
        if not path:
            raise Exception('storage path cannot be None')
        return linux.get_disk_capacity_by_df(path)

    def echo(self, req):
        return ''

    @replyerror
    def checkpath(self, req):
        def _get_image_meta(path):
            info = {}
            files = os.listdir(path)
            for file in files:
                if os.path.isfile(file):
                    info[file] = linux.md5sum(file)
            return info

        def _clean_dst_dir(basename, path):
            target = path + '/' + basename
            if os.path.isdir(target):
                shutil.rmtree(target)
            if os.path.isfile(target):
                os.remove(target)


        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CheckPathRsp()
        checkParam(srcPath=cmd.srcPath, dstPath=cmd.dstPath)

        imageDir = cmd.srcPath + "/images"

        if not os.path.isdir(imageDir):
            rsp.error = "cannot find image dir: [%s]" % imageDir
            rsp.success = False
            return jsonobject.dumps(rsp)

        rsp.srcSize = linux.get_folder_size(cmd.srcPath)
        rsp.imageInfos = _get_image_meta(imageDir)
        _clean_dst_dir(os.path.basename(cmd.srcPath), cmd.dstPath)

        if cmd.url is not None:
            rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.url)
        return jsonobject.dumps(rsp)

    @replyerror
    def collect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        rsp = AgentResponse()
        linux.mkdir(cmd.url, 0755)
        linux.mkdir(cmd.url + '/rawapps', 0755)
        linux.mkdir(cmd.url + '/builds', 0755)
        linux.mkdir(cmd.url + '/apps', 0755)
        linux.mkdir(cmd.url + '/exports', 0755)
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.url)

        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        rsp = AgentResponse()
        rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.url)

        return jsonobject.dumps(rsp)

    @replyerror
    def create(self, req):
        def _read_info(srcDir, filename):
            meta = srcDir + "/" + filename
            if not os.path.exists(meta):
                raise Exception("cannot find meta file: %s" % meta)
            fd = open(meta, 'r')
            ctx = fd.read()
            fd.close()
            return ctx

        def _copy_app(srcDir, dstDir):
            basename = os.path.basename(srcDir)
            target = dstDir + '/' + basename
            imageMeta = target + "/application-image-meta.json"
            shutil.copytree(srcDir, target)
            os.remove(imageMeta)
            return target

        def _encode_thumbs(srcDir, regex):
            files= os.listdir(srcDir)
            thumbs = []
            for f in files:
                if re.match(regex, f):
                    with open(srcDir+"/"+f, 'r') as thumb:
                        thumbs.append(pic_prefix + base64.b64encode(thumb.read()))
            return thumbs

# Note: cmd.srcPath drop the last '/' first
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = CreateAppRsp()
        srcPath = cmd.srcPath.rstrip('/')
        checkParam(srcPath=srcPath, dstPath=cmd.dstPath)

        rsp.imageInfos = _read_info(srcPath, "application-image-meta.json")
        rsp.dstInfo = _read_info(srcPath, "application-desc.json")
        rsp.template = _read_info(srcPath, "raw-cloudformation-template.json")
        with open(srcPath+"/logo.jpg", 'r') as logo:
            rsp.logo = pic_prefix + base64.b64encode(logo.read())
        rsp.thumbs = _encode_thumbs(srcPath, "thumbs.*.jpg")

        target = _copy_app(srcPath, cmd.dstPath)
        rsp.dstSize = linux.get_folder_size(target)
        rsp.dstPath = target
        if cmd.url is not None:
            rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.url)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        rsp = AgentResponse()
        if cmd.appPath is not None and os.path.isdir(cmd.appPath):
            shutil.rmtree(cmd.appPath)

        if cmd.url is not None:
            rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.url)

        return jsonobject.dumps(rsp)

    @replyerror
    def export(self, req):
        def _ready_dst_dir(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            if os.path.isfile(path):
                os.remove(path)
            linux.mkdir(path, 0755)
        def _tar_export(srcDir, dstDir, ctx):
            basename = os.path.basename(srcDir)
            metaPath = shell.call('mktemp XXXXXX-appmeta.json', True, srcDir).strip()  # metaPath is relative path
            tarPath = "/tmp/%s.tar" % basename
            dstPath = "%s/%s.tar.gz" % (dstDir, basename)

            if os.path.exists(tarPath):
                os.remove(tarPath)
            if os.path.exists(dstPath):
                os.remove(dstPath)

            fd = open("%s/%s" % (srcDir, metaPath), 'w')
            fd.write(ctx)
            fd.close()

            shell.call("tar cf %s images %s" % (tarPath, metaPath), True, srcDir)
            shell.call("gzip %s" % tarPath, True, srcDir)
            gzipPath = tarPath + ".gz"
            shutil.move(gzipPath, dstDir)
            os.remove("%s/%s" % (srcDir, metaPath))
            return dstPath

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        checkParam(exportDir=cmd.exportDir, appDir=cmd.appDir, exportCtx=cmd.exportCtx)

        rsp = ExportAppRsp()

        _ready_dst_dir(cmd.exportDir)
        rsp.exportPath = _tar_export(cmd.appDir, cmd.exportDir, cmd.exportCtx)

        rsp.md5Sum = linux.md5sum(cmd.exportDir)
        if cmd.url is not None:
            rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.url)

        return jsonobject.dumps(rsp)

    @replyerror
    def delexport(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        rsp = AgentResponse()
        checkParam(exportPath=cmd.exportPath)

        if os.path.isdir(cmd.exportPath):
            shutil.rmtree(cmd.exportPath)
        if os.path.isfile(cmd.exportPath):
            os.remove(cmd.exportPath)

        if cmd.url is not None:
            rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.url)

        return jsonobject.dumps(rsp)

    @replyerror
    def unzipapp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        checkParam(srcUrl=cmd.srcUrl, rawPath=cmd.rawPath)

        if os.path.isdir(cmd.rawPath):
            shutil.rmtree(cmd.rawPath)
        linux.mkdir(cmd.rawPath, 0755)

        if cmd.srcUrl.endswith(".gz"):
            shell.call("tar zxf %s -C %s" % (cmd.srcUrl, cmd.rawPath))
        else:
            shell.call("tar xf %s -C %s" % (cmd.srcUrl, cmd.rawPath))

        rsp = RawAppRsp()
        for file in os.listdir(cmd.rawPath):
            full_path = os.path.join(cmd.rawPath, file)
            if file.endswith("-appmeta.json"):
                f = open(full_path, 'r')
                rsp.appCtx = f.read()
                f.close()

        rsp.totalSize = linux.get_folder_size(cmd.rawPath)
        if cmd.url is not None:
            rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.url)

        return jsonobject.dumps(rsp)

    @replyerror
    def deleteunzip(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        checkParam(rawPath=cmd.rawPath)

        rsp = AgentResponse()
        if cmd.rawPath is not None and os.path.isdir(cmd.rawPath):
            shutil.rmtree(cmd.rawPath)

        if cmd.downloadPath:
            if os.path.isdir(cmd.downloadPath):
                shutil.rmtree(cmd.downloadPath)
            else:
                dir = os.path.dirname(cmd.downloadPath)
                shutil.rmtree(dir)

        if cmd.url is not None:
            rsp.totalCapacity, rsp.availableCapacity = self._get_disk_capacity(cmd.url)

        return jsonobject.dumps(rsp)

    @replyerror
    def downloadapp(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        checkParam(srcUrl=cmd.srcUrl, downloadPath=cmd.downloadPath)
        rsp = AgentResponse()

        dir = os.path.dirname(cmd.downloadPath)

        if os.path.isdir(dir):
            shutil.rmtree(dir)
        linux.mkdir(dir, 0755)
        cmd = shell.ShellCmd("wget -c -t 5 --no-check-certificate %s -O %s" % (cmd.srcUrl, cmd.downloadPath))
        cmd(False)
        if cmd.return_code != 0:
            rsp.error = cmd.stderr
            rsp.success = False

        return jsonobject.dumps(rsp)

    @replyerror
    def deletedownload(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        checkParam(downloadPath=cmd.downloadPath)
        rsp = AgentResponse()
        dir = os.path.dirname(cmd.downloadPath)
        if os.path.isdir(dir):
            shutil.rmtree(dir)

        return jsonobject.dumps(rsp)

class AppBuildSystemDaemon(daemon.Daemon):
    def __init__(self, pidfile, py_process_name):
        super(AppBuildSystemDaemon, self).__init__(pidfile, py_process_name)

    def run(self):
        self.agent = AppBuildSystemAgent()
        self.agent.http_server.start()