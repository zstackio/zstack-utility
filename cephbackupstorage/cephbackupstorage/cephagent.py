__author__ = 'frank'

import os
import os.path
import pprint
import re
import traceback
import urllib2

import zstacklib.utils.daemon as daemon
import zstacklib.utils.http as http
import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils import lock
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import thread
from zstacklib.utils.bash import *
from zstacklib.utils.report import Report
from zstacklib.utils import shell
from zstacklib.utils.rollback import rollback, rollbackable

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

class UploadProgressRsp(AgentResponse):
    def __init__(self):
        super(UploadProgressRsp, self).__init__()
        self.completed = False
        self.progress = 0
        self.size = 0
        self.actualSize = 0
        self.installPath = None

class GetImageSizeRsp(AgentResponse):
    def __init__(self):
        super(GetImageSizeRsp, self).__init__()
        self.size = None
        self.actualSize = None

class PingRsp(AgentResponse):
    def __init__(self):
        super(PingRsp, self).__init__()
        self.failure = None

class GetFactsRsp(AgentResponse):
    def __init__(self):
        super(GetFactsRsp, self).__init__()
        self.fsid = None
        self.monAddr = None

class DeleteImageMetaDataResponse(AgentResponse):
    def __init__(self):
        super(DeleteImageMetaDataResponse,self).__init__()
        self.ret = None

class WriteImageMetaDataResponse(AgentResponse):
    def __init__(self):
        super(WriteImageMetaDataResponse,self).__init__()

class GetImageMetaDataResponse(AgentResponse):
    def __init__(self):
        super(GetImageMetaDataResponse,self).__init__()
        self.imagesMetadata= None

class DumpImageMetaDataToFileResponse(AgentResponse):
    def __init__(self):
        super(DumpImageMetaDataToFileResponse,self).__init__()

class CheckImageMetaDataFileExistResponse(AgentResponse):
    def __init__(self):
        super(CheckImageMetaDataFileExistResponse, self).__init__()
        self.backupStorageMetaFileName = None
        self.exist = None

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

class UploadTask(object):

    def __init__(self, imageUuid, installPath, dstPath, tmpPath):
        self.completed = False
        self.imageUuid = imageUuid
        self.installPath = installPath
        self.dstPath = dstPath # without 'ceph://'
        self.tmpPath = tmpPath # where image firstly imported to
        self.expectedSize = 0
        self.downloadedSize = 0
        self.progress = 0
        self.lastError = None
        self.lastOpTime = linux.get_current_timestamp()

    def fail(self, reason):
        self.completed = True
        self.lastError = reason
        self.lastOpTime = linux.get_current_timestamp()
        logger.info('task failed for %s: %s' % (self.imageUuid, reason))

    def success(self):
        self.completed = True
        self.progress = 100
        self.lastOpTime = linux.get_current_timestamp()

    def is_started(self):
        return self.progress > 0

    def is_running(self):
        return not(self.completed or self.is_started())

class UploadTasks(object):
    MAX_RECORDS = 80

    def __init__(self):
        self.tasks = {}

    def _expunge_oldest_task(self):
        key, ts = '',  linux.get_current_timestamp()
        for k in self.tasks:
            task = self.tasks[k]

            if task.is_running():
                continue

            if task.lastOpTime < ts:
                key, ts = k, task.lastOpTime

        if key != '': del(self.tasks[key])


    @lock.lock('ceph-upload-task')
    def add_task(self, t):
        if len(self.tasks) > self.MAX_RECORDS:
            self._expunge_oldest_task()
        self.tasks[t.imageUuid] = t

    @lock.lock('ceph-upload-task')
    def get_task(self, imageUuid):
        return self.tasks.get(imageUuid)

# ------------------------------------------------------------------ #

class ProgressedFileWriter(object):
    def __init__(self, wfd, pfunc):
        self.wfd = wfd
        self.pfunc = pfunc
        self.bytesWritten = 0

    def write(self, s):
        self.wfd.write(s)
        self.bytesWritten += len(s)
        self.pfunc(self.bytesWritten)

    def seek(self, offset, whence=None):
        pass

import cherrypy
class CustomPart(cherrypy._cpreqbody.Part):
    """A customized multipart"""
    maxrambytes = 0

    def __init__(self, fp, headers, boundary, fifopath, pfunc):
        cherrypy._cpreqbody.Part.__init__(self, fp, headers, boundary)
        self.wfd = None
        self.file = None
        self.value = None
        self.fifopath = fifopath
        self.pfunc = pfunc

    def make_file(self):
        self.wfd = open(self.fifopath, 'w')
        return ProgressedFileWriter(self.wfd, self.pfunc)

def get_boundary(entity):
    ib = ""
    if 'boundary' in entity.content_type.params:
        # http://tools.ietf.org/html/rfc2046#section-5.1.1
        # "The grammar for parameters on the Content-type field is such that it
        # is often necessary to enclose the boundary parameter values in quotes
        # on the Content-type line"
        ib = entity.content_type.params['boundary'].strip('"')

    if not re.match("^[ -~]{0,200}[!-~]$", ib):
        raise ValueError('Invalid boundary in multipart form: %r' % (ib,))

    ib = ('--' + ib).encode('ascii')

    # Find the first marker
    while True:
        b = entity.readline()
        if not b:
            return

        b = b.strip()
        if b == ib:
            break

    return ib

def stream_body(task, fpath, entity, boundary):
    def _progress_consumer(total):
        task.downloadedSize = total

    @thread.AsyncThread
    def _do_import(task, fpath):
        shell.call("cat %s | rbd import --image-format 2 - %s" % (fpath, task.tmpPath))

    while True:
        headers = cherrypy._cpreqbody.Part.read_headers(entity.fp)
        p = CustomPart(entity.fp, headers, boundary, fpath, _progress_consumer)
        if not p.filename:
            continue

        # start consumer
        _do_import(task, fpath)
        try:
            p.process()
        except Exception as e:
            logger.warn('process image %s failed: %s' % (task.imageUuid, str(e)))
            pass
        finally:
            if p.wfd is not None:
                p.wfd.close()
        break

    if task.downloadedSize != task.expectedSize:
        task.fail('incomplete upload, got %d, expect %d' % (task.downloadedSize, task.expectedSize))
        shell.call('rbd rm %s' % task.tmpPath)
        return

    file_format = None

    try:
        file_format = linux.get_img_fmt('rbd:'+task.tmpPath)
    except Exception as e:
        task.fail('upload image %s failed: %s' % (task.imageUuid, str(e)))
        return

    if file_format == 'qcow2':
        if linux.qcow2_get_backing_file('rbd:'+task.tmpPath):
            task.fail('Qcow2 image %s has backing file' % task.imageUuid)
            shell.call('rbd rm %s' % task.tmpPath)
            return

        conf_path = None
        try:
            with open('/etc/ceph/ceph.conf', 'r') as fd:
                conf = fd.read()
                conf = '%s\n%s\n' % (conf, 'rbd default format = 2')
                conf_path = linux.write_to_temp_file(conf)

            shell.call('qemu-img convert -f qcow2 -O rbd rbd:%s rbd:%s:conf=%s' % (task.tmpPath, task.dstPath, conf_path))
            shell.call('rbd rm %s' % task.tmpPath)
        finally:
            if conf_path:
                os.remove(conf_path)
    else:
        shell.call('rbd mv %s %s' % (task.tmpPath, task.dstPath))

    task.success()

# ------------------------------------------------------------------ #

class CephAgent(object):
    INIT_PATH = "/ceph/backupstorage/init"
    DOWNLOAD_IMAGE_PATH = "/ceph/backupstorage/image/download"
    UPLOAD_IMAGE_PATH = "/ceph/backupstorage/image/upload"
    UPLOAD_PROGRESS_PATH = "/ceph/backupstorage/image/progress"
    DELETE_IMAGE_PATH = "/ceph/backupstorage/image/delete"
    PING_PATH = "/ceph/backupstorage/ping"
    ECHO_PATH = "/ceph/backupstorage/echo"
    GET_IMAGE_SIZE_PATH = "/ceph/backupstorage/image/getsize"
    GET_FACTS = "/ceph/backupstorage/facts"
    GET_IMAGES_METADATA = "/ceph/backupstorage/getimagesmetadata"
    DELETE_IMAGES_METADATA = "/ceph/backupstorage/deleteimagesmetadata"
    DUMP_IMAGE_METADATA_TO_FILE = "/ceph/backupstorage/dumpimagemetadatatofile"
    CHECK_IMAGE_METADATA_FILE_EXIST = "/ceph/backupstorage/checkimagemetadatafileexist"
    CHECK_POOL_PATH = "/ceph/backupstorage/checkpool"
    GET_LOCAL_FILE_SIZE = "/ceph/backupstorage/getlocalfilesize/"
    MIGRATE_IMAGE_PATH = "/ceph/backupstorage/image/migrate"

    CEPH_METADATA_FILE = "bs_ceph_info.json"
    UPLOAD_PROTO = "upload://"
    LENGTH_OF_UUID = 32

    http_server = http.HttpServer(port=7761)
    http_server.logfile_path = log.get_logfile_path()
    upload_tasks = UploadTasks()

    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.DOWNLOAD_IMAGE_PATH, self.download)
        self.http_server.register_raw_uri(self.UPLOAD_IMAGE_PATH, self.upload)
        self.http_server.register_async_uri(self.UPLOAD_PROGRESS_PATH, self.get_upload_progress)
        self.http_server.register_async_uri(self.DELETE_IMAGE_PATH, self.delete)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_async_uri(self.GET_IMAGE_SIZE_PATH, self.get_image_size)
        self.http_server.register_async_uri(self.GET_FACTS, self.get_facts)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.GET_IMAGES_METADATA, self.get_images_metadata)
        self.http_server.register_async_uri(self.CHECK_IMAGE_METADATA_FILE_EXIST, self.check_image_metadata_file_exist)
        self.http_server.register_async_uri(self.DUMP_IMAGE_METADATA_TO_FILE, self.dump_image_metadata_to_file)
        self.http_server.register_async_uri(self.DELETE_IMAGES_METADATA, self.delete_image_metadata_from_file)
        self.http_server.register_async_uri(self.CHECK_POOL_PATH, self.check_pool)
        self.http_server.register_async_uri(self.GET_LOCAL_FILE_SIZE, self.get_local_file_size)
        self.http_server.register_async_uri(self.MIGRATE_IMAGE_PATH, self.migrate_image)

    def _get_capacity(self):
        o = shell.call('ceph df -f json')
        df = jsonobject.loads(o)

        if df.stats.total_bytes__ is not None :
            total = long(df.stats.total_bytes_)
        elif df.stats.total_space__ is not None:
            total = long(df.stats.total_space__) * 1024
        else:
            raise Exception('unknown ceph df output: %s' % o)

        if df.stats.total_avail_bytes__ is not None:
            avail = long(df.stats.total_avail_bytes_)
        elif df.stats.total_avail__ is not None:
            avail = long(df.stats.total_avail_) * 1024
        else:
            raise Exception('unknown ceph df output: %s' % o)

        return total, avail

    def _set_capacity_to_response(self, rsp):
        total, avail = self._get_capacity()

        rsp.totalCapacity = total
        rsp.availableCapacity = avail

    @replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    def _normalize_install_path(self, path):
        return path.lstrip('ceph:').lstrip('//')

    def _get_file_size(self, path):
        o = shell.call('rbd --format json info %s' % path)
        o = jsonobject.loads(o)
        return long(o.size_)

    @replyerror
    def get_image_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetImageSizeRsp()
        path = self._normalize_install_path(cmd.installPath)
        rsp.size = self._get_file_size(path)
        return jsonobject.dumps(rsp)

    def _read_file_content(self, path):
        with open(path) as f:
            return f.read()

    @in_bash
    @replyerror
    def get_images_metadata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool_name = cmd.poolName
        bs_uuid = pool_name.split("-")[-1]
        valid_images_info = ""
        self.get_metadata_file(bs_uuid, self.CEPH_METADATA_FILE)
        last_image_install_path = ""
        bs_ceph_info_file = "/tmp/%s" % self.CEPH_METADATA_FILE
        with open(bs_ceph_info_file) as fd:
            images_info = fd.read()
            for image_info in images_info.split('\n'):
                if image_info != '':
                    image_json = jsonobject.loads(image_info)
                    # todo support multiple bs
                    image_uuid = image_json['uuid']
                    image_install_path = image_json["backupStorageRefs"][0]["installPath"]
                    ret = bash_r("rbd info %s" % image_install_path.split("//")[1])
                    if ret == 0 :
                        logger.info("Check image %s install path %s successfully!" % (image_uuid, image_install_path))
                        if image_install_path != last_image_install_path:
                            valid_images_info = image_info + '\n' + valid_images_info
                            last_image_install_path = image_install_path
                    else:
                        logger.warn("Image %s install path %s is invalid!" % (image_uuid, image_install_path))

        self.put_metadata_file(bs_uuid, self.CEPH_METADATA_FILE)
        rsp = GetImageMetaDataResponse()
        rsp.imagesMetadata= valid_images_info
        return jsonobject.dumps(rsp)

    @in_bash
    @replyerror
    def check_image_metadata_file_exist(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool_name = cmd.poolName
        bs_uuid = pool_name.split("-")[-1]
        rsp = CheckImageMetaDataFileExistResponse()
        rsp.backupStorageMetaFileName = self.CEPH_METADATA_FILE
        ret, output = bash_ro("rados -p bak-t-%s stat %s" % (bs_uuid,self.CEPH_METADATA_FILE))
        if ret == 0:
            rsp.exist = True
        else:
            rsp.exist = False
        return jsonobject.dumps(rsp)

    def get_metadata_file(self, bs_uuid, file_name):
        local_file_name = "/tmp/%s" % file_name
        bash_ro("rm -rf %s" % local_file_name)
        bash_ro("rados -p bak-t-%s get %s %s" % (bs_uuid, file_name, local_file_name))

    def put_metadata_file(self, bs_uuid, file_name):
        local_file_name = "/tmp/%s" % file_name
        ret, output = bash_ro("rados -p bak-t-%s put %s %s" % (bs_uuid, file_name, local_file_name))
        if ret == 0:
            bash_ro("rm -rf %s" % local_file_name)

    @in_bash
    @replyerror
    def dump_image_metadata_to_file(self, req):

        def _write_info_to_metadata_file(fd):
            strip_list_content = content[1:-1]
            data_list = strip_list_content.split('},')
            for item in data_list:
                if item.endswith("}") is not True:
                    item = item + "}"
                    fd.write(item + '\n')

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool_name = cmd.poolName
        bs_uuid = pool_name.split("-")[-1]
        content = cmd.imageMetaData
        dump_all_metadata = cmd.dumpAllMetaData
        if dump_all_metadata is True:
            # this means no metadata exist in ceph
            bash_r("touch /tmp/%s" % self.CEPH_METADATA_FILE)
        else:
            self.get_metadata_file(bs_uuid, self.CEPH_METADATA_FILE)
        bs_ceph_info_file = "/tmp/%s" % self.CEPH_METADATA_FILE
        if content is not None:
            if '[' == content[0] and ']' == content[-1]:
                if dump_all_metadata is True:
                    with open(bs_ceph_info_file, 'w') as fd:
                        _write_info_to_metadata_file(fd)
                else:
                    with open(bs_ceph_info_file, 'a') as fd:
                        _write_info_to_metadata_file(fd)
            else:
                # one image info
                if dump_all_metadata is True:
                    with open(bs_ceph_info_file, 'w') as fd:
                        fd.write(content + '\n')
                else:
                    with open(bs_ceph_info_file, 'a') as fd:
                        fd.write(content + '\n')

        self.put_metadata_file(bs_uuid, self.CEPH_METADATA_FILE)
        rsp = DumpImageMetaDataToFileResponse()
        return jsonobject.dumps(rsp)

    @in_bash
    @replyerror
    def delete_image_metadata_from_file(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        image_uuid = cmd.imageUuid
        pool_name = cmd.poolName
        bs_uuid = pool_name.split("-")[-1]
        self.get_metadata_file(bs_uuid, self.CEPH_METADATA_FILE)
        bs_ceph_info_file = "/tmp/%s" % self.CEPH_METADATA_FILE
        ret, output = bash_ro("sed -i.bak '/%s/d' %s" % (image_uuid, bs_ceph_info_file))
        self.put_metadata_file(bs_uuid, self.CEPH_METADATA_FILE)
        rsp = DeleteImageMetaDataResponse()
        rsp.ret = ret
        return jsonobject.dumps(rsp)



    @replyerror
    @in_bash
    def get_facts(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        o = bash_o('ceph mon_status')
        mon_status = jsonobject.loads(o)
        fsid = mon_status.monmap.fsid_

        rsp = GetFactsRsp()

        facts = bash_o('ceph -s -f json')
        mon_facts = jsonobject.loads(facts)
        for mon in mon_facts.monmap.mons:
            ADDR = mon.addr.split(':')[0]
            if bash_r('ip route | grep -w {{ADDR}} > /dev/null') == 0:
                rsp.monAddr = ADDR
                break

        if not rsp.monAddr:
            raise Exception('cannot find mon address of the mon server[%s]' % cmd.monUuid)

        rsp.fsid = fsid
        return jsonobject.dumps(rsp)

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        o = shell.call('ceph mon_status')
        mon_status = jsonobject.loads(o)
        fsid = mon_status.monmap.fsid_

        existing_pools = shell.call('ceph osd lspools')
        for pool in cmd.pools:
            if pool.predefined and pool.name not in existing_pools:
                raise Exception('cannot find pool[%s] in the ceph cluster, you must create it manually' % pool.name)
            elif pool.name not in existing_pools:
                shell.call('ceph osd pool create %s 128' % pool.name)

        rsp = InitRsp()
        rsp.fsid = fsid
        self._set_capacity_to_response(rsp)

        return jsonobject.dumps(rsp)

    def _parse_install_path(self, path):
        return path.lstrip('ceph:').lstrip('//').split('/')

    def _fail_task(self, task, reason):
        task.fail(reason)
        raise Exception(reason)

    def _get_fifopath(self, uu):
        import tempfile
        d = tempfile.gettempdir()
        return os.path.join(d, uu)

    # handler for multipart upload, requires:
    # - header X-IMAGE-UUID
    # - header X-IMAGE-SIZE
    def upload(self, req):
        imageUuid = req.headers['X-IMAGE-UUID']
        imageSize = req.headers['X-IMAGE-SIZE']

        task = self.upload_tasks.get_task(imageUuid)
        if task is None:
            raise Exception('image not found %s' % imageUuid)

        task.expectedSize = long(imageSize)
        total, avail = self._get_capacity()
        if avail <= task.expectedSize:
            self._fail_task(task, 'capacity not enough for size: ' + imageSize)

        entity = req.body
        boundary = get_boundary(entity)
        if not boundary:
            self._fail_task(task, 'unexpected post form')

        try:
            # prepare the fifo to save image upload
            fpath = self._get_fifopath(imageUuid)
            linux.rm_file_force(fpath)
            os.mkfifo(fpath)
            stream_body(task, fpath, entity, boundary)
        except Exception as e:
            self._fail_task(task, str(e))
        finally:
            linux.rm_file_force(fpath)

    def _prepare_upload(self, cmd):
        start = len(self.UPLOAD_PROTO)
        imageUuid = cmd.url[start:start+self.LENGTH_OF_UUID]
        dstPath = self._normalize_install_path(cmd.installPath)

        pool, image_name = self._parse_install_path(cmd.installPath)
        tmp_image_name = 'tmp-%s' % image_name
        tmpPath = '%s/%s' % (pool, tmp_image_name)

        task = UploadTask(imageUuid, cmd.installPath, dstPath, tmpPath)
        self.upload_tasks.add_task(task)

    def _get_upload_path(self, req):
        host = req[http.REQUEST_HEADER]['Host']
        return 'http://' + host + self.UPLOAD_IMAGE_PATH

    @replyerror
    def get_upload_progress(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        task = self.upload_tasks.get_task(cmd.imageUuid)
        if task is None:
            raise Exception('image not found %s' % cmd.imageUuid)

        rsp = UploadProgressRsp()
        rsp.completed = task.completed
        rsp.installPath = task.installPath
        rsp.size = task.expectedSize
        rsp.actualSize = task.expectedSize
        if task.expectedSize == 0:
            rsp.progress = 0
        elif task.completed:
            rsp.progress = 100
        else:
            rsp.progress = task.downloadedSize * 90 / task.expectedSize

        if task.lastError is not None:
            rsp.success = False
            rsp.error = task.lastError

        return jsonobject.dumps(rsp)

    @replyerror
    @rollback
    def download(self, req):
        rsp = DownloadRsp()

        def isDerivedQcow2Image(path):
            if path.startswith('http://') or path.startswith('https://'):
                resp = urllib2.urlopen(path)
                qhdr = resp.read(72)
                resp.close()
            else:
                resp = open(path)
                qhdr = resp.read(72)
                resp.close
            if len(qhdr) != 72:
                return False
            if qhdr[:4] != 'QFI\xfb':
                return False
            return qhdr[16:20] != '\x00\x00\x00\00'

        def fail_if_has_backing_file(fpath):
            if isDerivedQcow2Image(fpath):
                raise Exception('image has backing file or %s is not exist!' % fpath)

        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        pool, image_name = self._parse_install_path(cmd.installPath)
        tmp_image_name = 'tmp-%s' % image_name

        @rollbackable
        def _1():
            shell.call('rbd rm %s/%s' % (pool, tmp_image_name))

        def _getRealSize(length):
            '''length looks like: 10245K'''
            logger.debug(length)
            if not length[-1].isalpha():
                return length
            units = {
                "g": lambda x: x * 1024 * 1024 * 1024,
                "m": lambda x: x * 1024 * 1024,
                "k": lambda x: x * 1024,
            }
            try:
                if not length[-1].isalpha():
                    return length
                return units[length[-1].lower()](int(length[:-1]))
            except:
                logger.warn(linux.get_exception_stacktrace())
                return length

        # whether we have an upload request
        if cmd.url.startswith(self.UPLOAD_PROTO):
            self._prepare_upload(cmd)
            rsp.size = 0
            rsp.uploadPath = self._get_upload_path(req)
            self._set_capacity_to_response(rsp)
            return jsonobject.dumps(rsp)

        if cmd.sendCommandUrl:
            Report.url = cmd.sendCommandUrl

        report = Report(cmd.threadContext, cmd.threadContextStack)
        report.processType = "AddImage"
        report.resourceUuid = cmd.imageUuid
        report.progress_report("0", "start")

        if cmd.url.startswith('http://') or cmd.url.startswith('https://'):
            fail_if_has_backing_file(cmd.url)
            cmd.url = linux.shellquote(cmd.url)
            # roll back tmp ceph file after import it
            _1()

            PFILE = shell.call('mktemp /tmp/tmp-XXXXXX').strip()
            content_length = shell.call('curl -sI %s|grep Content-Length' % cmd.url).strip().split()[1]
            total = _getRealSize(content_length)

            def _getProgress(synced):
                logger.debug("getProgress in ceph-bs-agent, synced: %s, total: %s" % (synced, total))
                last = shell.call('tail -1 %s' % PFILE).strip()
                if not last or len(last.split()) < 1:
                    return synced
                logger.debug("last synced: %s" % last)
                written = _getRealSize(last.split()[0])
                if total > 0 and synced < written:
                    synced = written
                    if synced < total:
                        percent = int(round(float(synced) / float(total) * 90))
                        report.progress_report(percent, "report")
                return synced

            logger.debug("content-length is: %s" % total)

            _, _, err = bash_progress_1('set -o pipefail;wget --no-check-certificate -O - %s 2>%s| rbd import --image-format 2 - %s/%s'
                       % (cmd.url, PFILE, pool, tmp_image_name), _getProgress)
            if err:
                raise err
            actual_size = linux.get_file_size_by_http_head(cmd.url)

            if os.path.exists(PFILE):
                os.remove(PFILE)

        elif cmd.url.startswith('file://'):
            src_path = cmd.url.lstrip('file:')
            src_path = os.path.normpath(src_path)
            if not os.path.isfile(src_path):
                raise Exception('cannot find the file[%s]' % src_path)
            fail_if_has_backing_file(src_path)
            # roll back tmp ceph file after import it
            _1()
            shell.call("rbd import --image-format 2 %s %s/%s" % (src_path, pool, tmp_image_name))
            actual_size = os.path.getsize(src_path)
        else:
            raise Exception('unknown url[%s]' % cmd.url)

        file_format = shell.call(
            "set -o pipefail; qemu-img info rbd:%s/%s | grep 'file format' | cut -d ':' -f 2" % (pool, tmp_image_name))
        file_format = file_format.strip()
        if file_format not in ['qcow2', 'raw']:
            raise Exception('unknown image format: %s' % file_format)

        if file_format == 'qcow2':
            conf_path = None
            try:
                with open('/etc/ceph/ceph.conf', 'r') as fd:
                    conf = fd.read()
                    conf = '%s\n%s\n' % (conf, 'rbd default format = 2')
                    conf_path = linux.write_to_temp_file(conf)

                shell.call('qemu-img convert -f qcow2 -O rbd rbd:%s/%s rbd:%s/%s:conf=%s' % (pool, tmp_image_name, pool, image_name, conf_path))
                shell.call('rbd rm %s/%s' % (pool, tmp_image_name))
            finally:
                if conf_path:
                    os.remove(conf_path)
        else:
            shell.call('rbd mv %s/%s %s/%s' % (pool, tmp_image_name, pool, image_name))
        report.progress_report("100", "finish")

        @rollbackable
        def _2():
            shell.call('rbd rm %s/%s' % (pool, image_name))
        _2()


        o = shell.call('rbd --format json info %s/%s' % (pool, image_name))
        image_stats = jsonobject.loads(o)

        rsp.size = long(image_stats.size_)
        rsp.actualSize = actual_size
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = PingRsp()

        facts = bash_o('ceph -s -f json')
        mon_facts = jsonobject.loads(facts)
        found = False
        for mon in mon_facts.monmap.mons:
            if cmd.monAddr in mon.addr:
                found = True
                break

        if not found:
            rsp.success = False
            rsp.failure = "MonAddrChanged"
            rsp.error = 'The mon addr is changed on the mon server[uuid:%s], not %s anymore.' \
                        'Reconnect the ceph primary storage' \
                        ' may solve this issue' % (cmd.monUuid, cmd.monAddr)
            return jsonobject.dumps(rsp)


        create_img = shell.ShellCmd('rbd create %s --image-format 2 --size 1' % cmd.testImagePath)
        create_img(False)
        if create_img.return_code != 0 and 'File exists' not in create_img.stderr and 'File exists' not in create_img.stdout:
            rsp.success = False
            rsp.failure = 'UnableToCreateFile'
            rsp.error = "%s %s" % (create_img.stderr, create_img.stdout)
        else:
            rm_img = shell.ShellCmd('rbd rm %s' % cmd.testImagePath)
            rm_img(False)

        return jsonobject.dumps(rsp)

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)

        def delete_image(_):
            # in case image is deleted, we don't have to wait for timeout
            img = "%s/%s" % (pool, image_name)
            shell.call('rbd info %s && rbd rm %s' % (img, img))
            return True

        # 'rbd rm' might fail due to client crash. We wait for 30 seconds as suggested by 'rbd'.
        #
        # rbd: error: image still has watchers
        # This means the image is still open or the client using it crashed. Try again after
        # closing/unmapping it or waiting 30s for the crashed client to timeout.
        linux.wait_callback_success(delete_image, interval=5, timeout=30, ignore_exception_in_callback=True)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def check_pool(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        existing_pools = shell.call('ceph osd lspools')
        for pool in cmd.pools:
            if pool.name not in existing_pools:
                raise Exception('cannot find pool[%s] in the ceph cluster, you must create it manually' % pool.name)

        return jsonobject.dumps(AgentResponse())

    @replyerror
    def get_local_file_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetLocalFileSizeRsp()
        rsp.size = linux.get_local_file_size(cmd.path)
        return jsonobject.dumps(rsp)

    def _migrate_image(self, image_uuid, image_size, src_install_path, dst_install_path, dst_mon_addr, dst_mon_user, dst_mon_passwd, dst_mon_port):
        src_install_path = self._normalize_install_path(src_install_path)
        dst_install_path = self._normalize_install_path(dst_install_path)

        rst = shell.run('rbd export %s - | tee >(md5sum >/tmp/%s_src_md5) | sshpass -p "%s" ssh -o StrictHostKeyChecking=no %s@%s -p %s \'tee >(md5sum >/tmp/%s_dst_md5) | rbd import - %s\'' % (src_install_path, image_uuid, dst_mon_passwd, dst_mon_user, dst_mon_addr, dst_mon_port, image_uuid, dst_install_path))
        if rst != 0:
            return rst

        src_md5 = self._read_file_content('/tmp/%s_src_md5' % image_uuid)
        dst_md5 = shell.call('sshpass -p "%s" ssh -o StrictHostKeyChecking=no %s@%s -p %s \'cat /tmp/%s_dst_md5\'' % (dst_mon_passwd, dst_mon_user, dst_mon_addr, dst_mon_port, image_uuid))
        if src_md5 != dst_md5:
            return -1
        else:
            return 0

    @replyerror
    @in_bash
    def migrate_image(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        rst = self._migrate_image(cmd.imageUuid, cmd.imageSize, cmd.srcInstallPath, cmd.dstInstallPath, cmd.dstMonHostname, cmd.dstMonSshUsername, cmd.dstMonSshPassword, cmd.dstMonSshPort)
        if rst != 0:
            rsp.success = False
            rsp.error = "Failed to migrate image from one ceph backup storage to another."
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

class CephDaemon(daemon.Daemon):
    def __init__(self, pidfile):
        super(CephDaemon, self).__init__(pidfile)

    def run(self):
        self.agent = CephAgent()
        self.agent.http_server.start()
