__author__ = 'frank'

import os
import os.path
import pprint
import traceback
import urllib2
import urlparse
import tempfile
import threading
import rados
import rbd
import cherrypy
import hashlib
from cherrypy.lib.static import _serve_fileobj
from cherrypy._cpreqbody import Entity, Part, SizedReader
from cherrypy._cprequest import Request

import zstacklib.utils.daemon as daemon
import zstacklib.utils.plugin as plugin
import zstacklib.utils.http as http
import zstacklib.utils.jsonobject as jsonobject
from zstacklib.utils import lock
from zstacklib.utils import linux
from zstacklib.utils import thread
from zstacklib.utils.bash import *
from zstacklib.utils.ceph import get_mon_addr
from zstacklib.utils.report import Report
from zstacklib.utils import shell
from zstacklib.utils import ceph
from zstacklib.utils import qemu_img
from zstacklib.utils import traceable_shell
from zstacklib.utils.rollback import rollback, rollbackable

logger = log.get_logger(__name__)
BUFFER_SIZE = 16 * 1024 ** 2


class CephPoolCapacity(object):
    def __init__(self, name, available, used, total, replicated_size, security_policy, disk_utilization, related_osds):
        self.name = name
        self.availableCapacity = available
        self.usedCapacity = used
        self.totalCapacity = total
        self.replicatedSize = replicated_size
        self.securityPolicy = security_policy
        self.diskUtilization = round(disk_utilization, 3)
        self.relatedOsds = related_osds


class AgentCommand(object):
    def __init__(self):
        pass


class AgentResponse(object):
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error if error else ''
        self.totalCapacity = None
        self.availableCapacity = None
        self.poolCapacities = None
        self.type = None

class InitRsp(AgentResponse):
    def __init__(self):
        super(InitRsp, self).__init__()
        self.fsid = None

class DownloadRsp(AgentResponse):
    def __init__(self):
        super(DownloadRsp, self).__init__()
        self.size = None
        self.actualSize = None


class CephToCephMigrateImageCmd(AgentCommand):
    @log.sensitive_fields("dstMonSshPassword")
    def __init__(self):
        super(CephToCephMigrateImageCmd, self).__init__()
        self.imageUuid = None
        self.imageSize = None  # type:long
        self.srcInstallPath = None
        self.dstInstallPath = None
        self.dstMonHostname = None
        self.dstMonSshUsername = None
        self.dstMonSshPassword = None
        self.dstMonSshPort = None  # type:int


class UploadProgressRsp(AgentResponse):
    def __init__(self):
        super(UploadProgressRsp, self).__init__()
        self.completed = False
        self.progress = 0
        self.size = 0
        self.actualSize = 0
        self.installPath = None
        self.lastOpTime = 0
        self.downloadSize = 0

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

class UploadParam(object):
    def __init__(self):
        self.image_uuid = None
        self.image_size = 0
        self.slice_index = 0
        self.slice_offset = 0
        self.slice_size = 0
        self.slice_md5 = None


class UploadTask(object):
    def __init__(self, imageUuid, installPath, dstPath, tmpPath):
        self.completed = False
        self.imageUuid = imageUuid
        self.installPath = installPath
        self.dstPath = dstPath # without 'ceph://'
        self.tmpPath = tmpPath # where image firstly imported to
        self.expectedSize = 0
        self.downloadSize = 0
        self.progress = 0
        self.lastError = None
        self.lastOpTime = linux.get_current_timestamp()
        self.image_format = "raw"
        self.close = None

        self.slice_uploaded = set()
        self.slice_count = 0
        self.slice_size = 0

        self.image_created = False
        self.image_completing = False

    def fail(self, reason):
        self.completed = True
        self.lastError = reason
        self.lastOpTime = linux.get_current_timestamp()
        if self.close:
            self.close()
        logger.info('task failed for %s: %s' % (self.imageUuid, reason))

    def success(self):
        self.completed = True
        self.progress = 100
        self.lastOpTime = linux.get_current_timestamp()
        if self.close:
            self.close()

    def is_started(self):
        return self.progress > 0

    def is_running(self):
        return not(self.completed or self.is_started())

    def renew(self):
        self.lastOpTime = linux.get_current_timestamp()

    def all_slice_uploaded(self):
        return 0 < self.slice_count == len(self.slice_uploaded)

    def checked_download_size(self):
        for i in range(self.slice_count):
            if i not in self.slice_uploaded:
                return i * self.slice_size

        return self.expectedSize

    def create_image_if_not_exists(self, ioctx, image_name):
        # type: (rados.Ioctx, str) -> None

        if self.image_created:
            return

        with lock.NamedLock("upload-image-%s" % self.imageUuid):
            if not self.image_created:
                rbd.RBD().create(ioctx, image_name, self.expectedSize)
                self.image_created = True

    def allow_image_completing(self):
        if self.all_slice_uploaded():
            with lock.NamedLock("upload-image-%s" % self.imageUuid):
                if not self.image_completing:
                    self.image_completing = True
                    return True
        return False

    def add_download_size(self, delta):
        with lock.NamedLock("upload-image-%s" % self.imageUuid):
            self.downloadSize += delta


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
        # type: (UploadTask) -> None
        if len(self.tasks) > self.MAX_RECORDS:
            self._expunge_oldest_task()
        self.tasks[t.imageUuid] = t

    @lock.lock('ceph-upload-task')
    def get_task(self, image_uuid):
        # type: (str) -> UploadTask
        return self.tasks.get(image_uuid)

# ------------------------------------------------------------------ #

def get_boundary(entity):
    # type: (Entity) -> str

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


def get_image_format_from_buf(qhdr):
    if qhdr[:4] == 'QFI\xfb':
        if qhdr[16:20] == '\x00\x00\x00\00':
            return "qcow2"
        else:
            return "derivedQcow2"

    if qhdr[:5] == 'KDMV\x03':
        return 'vmdk'

    if qhdr[0x8001:0x8006] == 'CD001':
        return 'iso'

    if qhdr[0x8801:0x8806] == 'CD001':
        return 'iso'

    if qhdr[0x9001:0x9006] == 'CD001':
        return 'iso'
    return "raw"


def stream_body(entity, boundary, param, task, ioctx):
    # type: (Entity, str, UploadParam, UploadTask, rados.Ioctx) -> None

    _, image_name = task.tmpPath.split('/')
    task.create_image_if_not_exists(ioctx, image_name)
    image_obj = ImageFileObject(rbd.Image(ioctx, image_name))
    image_obj.seek(param.slice_offset)

    while True:
        headers = Part.read_headers(entity.fp)
        p = Part(entity.fp, headers, boundary)
        if not p.filename:
            continue

        logger.debug("uploading image %s: %s slice, index: %d, offset: %d, content length: %d" %
                     (param.image_uuid, p.filename, param.slice_index, param.slice_offset, param.slice_size))

        slice_downloaded_size = 0
        try:
            reader = SizedReader(p.fp, None, param.slice_offset)
            remaining = param.slice_size
            bytes_read = 0
            md5 = hashlib.md5()
            chunks = []
            chunk_size = 32 * 1024
            while remaining > 0:
                if task.lastError:
                    raise Exception(task.lastError)
                tmp = reader.read(min(chunk_size, remaining))
                datalen = len(tmp)
                task.renew()
                chunks.append(tmp)
                md5.update(tmp)

                remaining -= datalen
                bytes_read += datalen
                if bytes_read >= BUFFER_SIZE or remaining <= 0:
                    image_obj.write(b''.join(chunks))
                    task.add_download_size(bytes_read)
                    slice_downloaded_size += bytes_read
                    chunks = []
                    bytes_read = 0
        finally:
            image_obj.close()
        break

    if param.slice_size != slice_downloaded_size:
        task.add_download_size(-slice_downloaded_size)
        raise Exception("incomplete image %s slice index %d, offset %d, completed %d, expected %d" %
                        (param.image_uuid, param.slice_index, param.slice_offset, slice_downloaded_size, param.slice_size))

    if param.slice_md5 and param.slice_md5 != md5.hexdigest():
        task.add_download_size(-slice_downloaded_size)
        raise cherrypy.HTTPError(406, "content md5 not match, expected: %s, actual: %s" % (param.slice_md5, md5.hexdigest()))

    task.slice_uploaded.add(param.slice_index)
    logger.debug("uploaded image %s slice, index: %d offset: %d, content length: %d" %
                 (param.image_uuid, param.slice_index, param.slice_offset, param.slice_size))


def complete_upload(task):
    # type: (UploadTask) -> None
    try:
        file_format = linux.get_img_fmt('rbd:' + task.tmpPath)
    except Exception as e:
        task.fail('upload image %s failed: %s' % (task.imageUuid, str(e)))
        shell.run('rbd rm %s' % task.tmpPath)
        return

    if file_format == 'qcow2' and linux.qcow2_get_backing_file('rbd:' + task.tmpPath):
        task.fail('Qcow2 image %s has backing file' % task.imageUuid)
        shell.run('rbd rm %s' % task.tmpPath)
        return

    if file_format in ['qcow2', 'vmdk']:
        conf_path = None
        try:
            with open('/etc/ceph/ceph.conf', 'r') as fd:
                conf = fd.read()
                conf = '%s\n%s\n' % (conf, 'rbd default format = 2')
                conf_path = linux.write_to_temp_file(conf)

            shell.check_run('%s -f %s -O rbd rbd:%s rbd:%s:conf=%s' % (qemu_img.subcmd('convert'), file_format,
                                                                       task.tmpPath, task.dstPath, conf_path))
        except Exception as e:
            task.fail('cannot convert %s image %s to rbd' % (file_format, task.imageUuid))
            logger.warn('convert image %s failed: %s', (task.imageUuid, str(e)))
            return
        finally:
            shell.run('rbd rm %s' % task.tmpPath)
            if conf_path:
                os.remove(conf_path)
    else:
        shell.check_run('rbd mv %s %s' % (task.tmpPath, task.dstPath))

    if task.lastError:
        raise Exception(task.lastError)
    task.success()


class ImageFileObject(object):
    def __init__(self, image):
        # type: (rbd.Image) -> None
        self.offset = 0
        self.image = image
        self.size = image.size()

    def seek(self, offset):
        self.offset = min(offset, self.size)

    def read(self, n):
        length = min(self.size - self.offset, n)
        content = self.image.read(self.offset, length)
        self.offset += length
        return content

    def write(self, content):
        self.image.write(content, self.offset)
        self.offset = min(self.offset + len(content), self.size)

    def close(self):
        self.image.close()
        logger.debug("%s closed" % str(self.image))

# ------------------------------------------------------------------ #

class CephAgent(object):
    INIT_PATH = "/ceph/backupstorage/init"
    DOWNLOAD_IMAGE_PATH = "/ceph/backupstorage/image/download"
    JOB_CANCEL = "/job/cancel"
    UPLOAD_IMAGE_PATH = "/ceph/backupstorage/image/upload"
    EXPORT_IMAGE_PATH = "/ceph/export/:pool/:image"
    UPLOAD_PROGRESS_PATH = "/ceph/backupstorage/image/progress"
    DELETE_IMAGE_PATH = "/ceph/backupstorage/image/delete"
    PING_PATH = "/ceph/backupstorage/ping"
    ECHO_PATH = "/ceph/backupstorage/echo"
    GET_IMAGE_SIZE_PATH = "/ceph/backupstorage/image/getsize"
    ADD_EXPORT_TOKEN_PATH = "/ceph/backupstorage/image/export/addtoken"
    REMOVE_EXPORT_TOKEN_PATH = "/ceph/backupstorage/image/export/removetoken"
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
    CEPH_CONF_PATH = "/etc/ceph/ceph.conf"

    http_server = http.HttpServer(port=7761)
    http_server.logfile_path = log.get_logfile_path()
    upload_tasks = UploadTasks()

    def __init__(self):
        self.http_server.register_async_uri(self.INIT_PATH, self.init)
        self.http_server.register_async_uri(self.DOWNLOAD_IMAGE_PATH, self.download)
        self.http_server.register_raw_uri(self.UPLOAD_IMAGE_PATH, self.upload)
        self.http_server.register_raw_stream_uri(self.EXPORT_IMAGE_PATH, self.export)
        self.http_server.register_async_uri(self.ADD_EXPORT_TOKEN_PATH, self.add_export_token)
        self.http_server.register_async_uri(self.REMOVE_EXPORT_TOKEN_PATH, self.remove_export_token)
        self.http_server.register_async_uri(self.UPLOAD_PROGRESS_PATH, self.get_upload_progress)
        self.http_server.register_async_uri(self.DELETE_IMAGE_PATH, self.delete)
        self.http_server.register_async_uri(self.JOB_CANCEL, self.cancel)
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
        self.http_server.register_async_uri(self.MIGRATE_IMAGE_PATH, self.migrate_image, cmd=CephToCephMigrateImageCmd())

        self.cluster = None
        self.ioctx = {}
        self.op_lock = threading.Lock()

    def get_ioctx(self, pool_name):
        # type: (str) -> rados.Ioctx

        if pool_name in self.ioctx:
            return self.ioctx[pool_name]

        with self.op_lock:
            if not self.cluster:
                self.cluster = rados.Rados(conffile=self.CEPH_CONF_PATH)
                self.cluster.connect()

            self.ioctx[pool_name] = self.cluster.open_ioctx(pool_name)

        return self.ioctx[pool_name]


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

        pool_capacities = []

        if not df.pools:
            return total, avail, pool_capacities

        pools = ceph.get_pools_capacity()
        if not pools:
            return total, avail, pool_capacities

        for pool in pools:
            pool_capacity = CephPoolCapacity(pool.pool_name,
                                             pool.available_capacity, pool.used_capacity, pool.pool_total_size,
                                             pool.replicated_size, pool.security_policy, pool.disk_utilization,
                                             pool.get_related_osds())
            pool_capacities.append(pool_capacity)

        return total, avail, pool_capacities

    def _set_capacity_to_response(self, rsp):
        total, avail, pool_capacities = self._get_capacity()

        rsp.totalCapacity = total
        rsp.availableCapacity = avail
        rsp.poolCapacities = pool_capacities
        rsp.type = ceph.get_ceph_manufacturer()

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
        linux.rm_file_force(local_file_name)
        bash_ro("rados -p bak-t-%s get %s %s" % (bs_uuid, file_name, local_file_name))

    def put_metadata_file(self, bs_uuid, file_name):
        local_file_name = "/tmp/%s" % file_name
        ret, output = bash_ro("rados -p bak-t-%s put %s %s" % (bs_uuid, file_name, local_file_name))
        if ret == 0:
            linux.rm_file_force(local_file_name)

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
        rsp = GetFactsRsp()

        monmap = bash_o('ceph mon dump -f json')
        rsp.monAddr = get_mon_addr(monmap, "kernel")
        if rsp.monAddr is None:
            rsp.monAddr = get_mon_addr(monmap)

        if not rsp.monAddr:
            raise Exception('cannot find mon address of the mon server[%s]' % cmd.monUuid)

        rsp.fsid = ceph.get_fsid()
        return jsonobject.dumps(rsp)

    @replyerror
    def init(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        existing_pools = shell.call('ceph osd lspools')
        for pool in cmd.pools:
            if pool.name in existing_pools:
                continue

            if pool.predefined:
                raise Exception('cannot find pool[%s] in the ceph cluster, you must create it manually' % pool.name)
            if ceph.is_xsky() or ceph.is_sandstone():
                raise Exception(
                    'The ceph storage type to be added does not support auto initialize pool, please create it manually')

            shell.call('ceph osd pool create %s 128' % pool.name)

        rsp = InitRsp()
        rsp.fsid = ceph.get_fsid()
        self._set_capacity_to_response(rsp)

        return jsonobject.dumps(rsp)

    def _parse_install_path(self, path):
        return path.lstrip('ceph:').lstrip('//').split('/')

    def _fail_task(self, task, reason):
        task.fail(reason)
        raise Exception(reason)

    # handler for multipart upload, requires:
    # - header X-IMAGE-UUID
    # - header X-IMAGE-SIZE
    # options:
    # - header X-SLICE-OFFSET
    # - header X-SLICE-SIZE
    # - header X-SLICE-INDEX
    # - header X-SLICE-MD5
    def upload(self, req):
        # type: (Request) -> None

        upload_param = self.get_upload_param(req.headers)
        task = self.get_upload_task(upload_param)
        self.upload_slice(req.body, upload_param, task)

        if task.allow_image_completing():
            complete_upload(task)

    @staticmethod
    def get_upload_param(req_header):
        # type: (dict[str, str]) -> UploadParam

        def get_long_field(key, default=None):
            v = req_header.get(key, default)
            try:
                lv = long(v)
                if lv < 0:
                    raise ValueError
                return lv
            except ValueError:
                raise Exception('invalid header "%s": %s' % (key, v))

        up = UploadParam()
        up.image_uuid = req_header['X-IMAGE-UUID']
        up.image_size = get_long_field('X-IMAGE-SIZE')
        up.slice_offset = get_long_field('X-SLICE-OFFSET', default=0)
        up.slice_size = get_long_field('X-SLICE-SIZE', default=up.image_size)
        up.slice_index = get_long_field('X-SLICE-INDEX', default=0)
        up.expected_md5 = req_header.get('X-SLICE-MD5', None)

        if up.slice_offset >= up.image_size:
            raise Exception('invalid slice offset header: %s, image_size: %d' % (up.slice_offset, up.image_size))

        return up

    def get_upload_task(self, param):
        # type: (UploadParam) -> UploadTask
        task = self.upload_tasks.get_task(param.image_uuid)
        if task is None:
            raise Exception('image not found %s' % param.image_uuid)

        if task.lastError:
            self._fail_task(task, task.lastError)

        if task.completed:
            raise Exception('image[uuid: %s] upload has completed' % param.image_uuid)

        task.expectedSize = param.image_size

        if param.slice_index == 0:
            task.slice_size = param.slice_size

            _, avail, _ = self._get_capacity()
            if avail <= task.expectedSize:
                self._fail_task(task, 'capacity not enough for size: %d' % param.image_size)

        if param.slice_offset + param.slice_size == param.image_size:
            slice_count = param.slice_index + 1
        else:
            slice_count = (param.image_size - 1) / param.slice_size + 1

        if not task.slice_count:
            task.slice_count = slice_count
        elif task.slice_count != slice_count:
            raise Exception("every upload request for image[uuid:%s] should has the same slice size and image size" % param.image_uuid)

        return task

    def upload_slice(self, entity, param, task):
        # type: (Entity, UploadParam, UploadTask) -> None

        boundary = get_boundary(entity)
        if not boundary:
            self._fail_task(task, 'unexpected post form')

        pool, _ = task.tmpPath.split('/')
        ioctx = self.get_ioctx(pool)

        try:
            stream_body(entity, boundary, param, task, ioctx)
        except cherrypy.HTTPError as e:
            raise cherrypy.HTTPError(e.status, e._message)
        except Exception as e:
            if str(e).lstrip() != 'timed out':
                shell.run('rbd rm %s' % task.tmpPath)
                self._fail_task(task, str(e))
            if param.slice_offset == 0:
                shell.run('rbd rm %s' % task.tmpPath)


    def _prepare_upload(self, cmd):
        class ImageUploadDaemon(plugin.TaskDaemon):
            def __init__(self, task):
                super(ImageUploadDaemon, self).__init__(cmd, 'imageUpload', report_progress=False)
                self.task = task
                self.task.close = self.close

            def _cancel(self):
                if self.task.completed:
                    return
                self.task.lastError = "image [uuid: %s] upload canceled" % cmd.imageUuid
                shell.run('rbd rm %s' % task.tmpPath)

            def _get_percent(self):
                pass

        start = len(self.UPLOAD_PROTO)
        imageUuid = cmd.url[start:start+self.LENGTH_OF_UUID]
        dstPath = self._normalize_install_path(cmd.installPath)

        pool, image_name = self._parse_install_path(cmd.installPath)
        tmp_image_name = 'tmp-%s' % image_name
        tmpPath = '%s/%s' % (pool, tmp_image_name)

        task = UploadTask(imageUuid, cmd.installPath, dstPath, tmpPath)
        self.upload_tasks.add_task(task)
        ImageUploadDaemon(task).start()

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
        rsp.downloadSize = task.checked_download_size()
        rsp.lastOpTime = long(task.lastOpTime) * 1000
        if task.expectedSize == 0:
            rsp.progress = 0
        elif task.completed and not task.lastError:
            rsp.size = self._get_file_size(task.dstPath)
            rsp.progress = 100
        else:
            rsp.progress = task.downloadSize * 90 / task.expectedSize

        if task.lastError is not None:
            rsp.success = False
            rsp.error = task.lastError
        return jsonobject.dumps(rsp)

    @replyerror
    @rollback
    def download(self, req):
        rsp = DownloadRsp()

        def _get_origin_format(path):
            qcow2_length = 0x9007
            if path.startswith('http://') or path.startswith('https://') or path.startswith('ftp://'):
                resp = urllib2.urlopen(path)
                qhdr = resp.read(qcow2_length)
                resp.close()
            elif path.startswith('sftp://'):
                fd, tmp_file = tempfile.mkstemp()
                get_header_from_pipe_cmd = "timeout 60 head --bytes=%d %s > %s" % (qcow2_length, pipe_path, tmp_file)
                clean_cmd = "pkill -f %s" % pipe_path
                shell.run('%s & %s && %s' % (scp_to_pipe_cmd, get_header_from_pipe_cmd, clean_cmd))
                qhdr = os.read(fd, qcow2_length)
                os.close(fd)
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
            else:
                resp = open(path)
                qhdr = resp.read(qcow2_length)
                resp.close()
            if len(qhdr) < qcow2_length:
                return "raw"

            return get_image_format_from_buf(qhdr)

        def get_origin_format(fpath, fail_if_has_backing_file=True):
            image_format = _get_origin_format(fpath)
            if image_format == "derivedQcow2" and fail_if_has_backing_file:
                raise Exception('image has backing file or %s is not exist!' % fpath)
            return image_format

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        shell = traceable_shell.get_shell(cmd)
        pool, image_name = self._parse_install_path(cmd.installPath)
        tmp_image_name = 'tmp-%s' % image_name

        @rollbackable
        def _1():
            shell.check_run('rbd rm %s/%s' % (pool, tmp_image_name))

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

        if isinstance(cmd.url, unicode):
            cmd.url = str(cmd.url)

        url = urlparse.urlparse(cmd.url)
        if url.scheme in ('http', 'https', 'ftp'):
            image_format = get_origin_format(cmd.url, True)
            cmd.url = linux.shellquote(cmd.url)
            # roll back tmp ceph file after import it
            _1()

            PFILE = linux.create_temp_file()
            content_length = shell.call("""curl -sLI %s|awk '/[cC]ontent-[lL]ength/{print $NF}'""" % cmd.url).splitlines()[-1]
            total = _getRealSize(content_length)

            def _getProgress(synced):
                last = linux.tail_1(PFILE).strip()
                if not last or len(last.split()) < 1 or 'HTTP request sent, awaiting response' in last:
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

            _, _, err = shell.bash_progress_1('set -o pipefail;wget --no-check-certificate -O - %s 2>%s| rbd import '
                                              '--image-format 2 - %s/%s ' % (cmd.url, PFILE, pool, tmp_image_name)
                                              , _getProgress)
            if err:
                raise err
            actual_size = linux.get_file_size_by_http_head(cmd.url)

            if os.path.exists(PFILE):
                os.remove(PFILE)

        elif url.scheme == 'sftp':
            port = (url.port, 22)[url.port is None]
            PFILE = linux.create_temp_file()
            ssh_pswd_file = None
            pipe_path = PFILE + "fifo"
            scp_to_pipe_cmd = "scp -P %d -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null %s@%s:%s %s" % (port, url.username, url.hostname, url.path, pipe_path)
            sftp_command = "sftp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=no -P %s -b /dev/stdin %s@%s" % (port, url.username, url.hostname) + " <<EOF\n%s\nEOF\n"
            if url.password is not None:
                ssh_pswd_file = linux.write_to_temp_file(url.password)
                scp_to_pipe_cmd = 'sshpass -f %s %s' % (ssh_pswd_file, scp_to_pipe_cmd)
                sftp_command = 'sshpass -f %s %s' % (ssh_pswd_file, sftp_command)

            actual_size = shell.call(sftp_command % ("ls -l " + url.path)).splitlines()[1].strip().split()[4]
            os.mkfifo(pipe_path)
            image_format = get_origin_format(cmd.url, True)
            cmd.url = linux.shellquote(cmd.url)
            # roll back tmp ceph file after import it
            _1()

            def _get_progress(synced):
                if not os.path.exists(PFILE):
                    return synced
                last = linux.tail_1(PFILE).strip()
                if not last or not last.isdigit():
                    return synced
                report.progress_report(int(last)*90/100, "report")
                return synced

            get_content_from_pipe_cmd = "pv -s %s -n %s 2>%s" % (actual_size, pipe_path, PFILE)
            import_from_pipe_cmd = "rbd import --image-format 2 - %s/%s" % (pool, tmp_image_name)
            _, _, err = shell.bash_progress_1('set -o pipefail; %s & %s | %s' %
                                        (scp_to_pipe_cmd, get_content_from_pipe_cmd, import_from_pipe_cmd), _get_progress)

            if ssh_pswd_file:
                linux.rm_file_force(ssh_pswd_file)

            linux.rm_file_force(PFILE)
            linux.rm_file_force(pipe_path)

            if err:
                raise err

        elif url.scheme == 'file':
            src_path = cmd.url.lstrip('file:')
            src_path = os.path.normpath(src_path)
            if not os.path.isfile(src_path):
                raise Exception('cannot find the file[%s]' % src_path)
            image_format = get_origin_format(src_path, True)
            # roll back tmp ceph file after import it
            _1()

            shell.check_run("rbd import --image-format 2 %s %s/%s" % (src_path, pool, tmp_image_name))
            actual_size = os.path.getsize(src_path)
        else:
            raise Exception('unknown url[%s]' % cmd.url)

        file_format = shell.call("set -o pipefail; %s rbd:%s/%s | grep 'file format' | cut -d ':' -f 2" % (
            qemu_img.subcmd('info'), pool, tmp_image_name))
        file_format = file_format.strip()
        if file_format not in ['qcow2', 'raw', 'vmdk']:
            raise Exception('unknown image format: %s' % file_format)

        if file_format in ['qcow2', 'vmdk']:
            conf_path = None
            try:
                with open('/etc/ceph/ceph.conf', 'r') as fd:
                    conf = fd.read()
                    conf = '%s\n%s\n' % (conf, 'rbd default format = 2')
                    conf_path = linux.write_to_temp_file(conf)

                shell.check_run('%s -f %s -O rbd rbd:%s/%s rbd:%s/%s:conf=%s' % (qemu_img.subcmd('convert'),
                                                                                 file_format, pool, tmp_image_name,
                                                                                 pool, image_name, conf_path))
                shell.check_run('rbd rm %s/%s' % (pool, tmp_image_name))
            finally:
                if conf_path:
                    os.remove(conf_path)
        else:
            shell.check_run('rbd mv %s/%s %s/%s' % (pool, tmp_image_name, pool, image_name))
        report.progress_report("100", "finish")

        @rollbackable
        def _2():
            shell.check_run('rbd rm %s/%s' % (pool, image_name))
        _2()

        o = shell.call('rbd --format json info %s/%s' % (pool, image_name))
        image_stats = jsonobject.loads(o)

        rsp.size = long(image_stats.size_)
        rsp.actualSize = actual_size
        if image_format in ['qcow2', 'vmdk']:
            rsp.format = "raw"
        else:
            rsp.format = image_format

        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    def export(self, req, rsp, **kwargs):
        def get_image_name(image):
            return image[len(image) - self.LENGTH_OF_UUID:]

        pool_name = kwargs['pool']
        image_name = get_image_name(kwargs['image'])

        if isinstance(pool_name, unicode):
            pool_name = pool_name.encode('unicode-escape').decode('string_escape')
        if isinstance(image_name, unicode):
            image_name = image_name.encode('unicode-escape').decode('string_escape')

        ioctx = self.get_ioctx(pool_name)
        try:
            token = ioctx.read(image_name + "-export")
            if 'token' not in kwargs or token != kwargs['token']:
                rsp.status = 403
                return "Forbidden"
        except rados.ObjectNotFound:
            rsp.status = 404
            return "Image not found."

        image_file_obj = ImageFileObject(rbd.Image(ioctx, image_name, read_only=True))

        rsp.headers['Content-Type'] = 'application/x-download'

        req_close = req.close

        # cherrypy cannot ensure file obj closed every time. so hack it in request close.
        def all_close():
            req_close()
            image_file_obj.close()

        req.close = all_close
        return _serve_fileobj(image_file_obj, 'application/x-download', image_file_obj.size)

    @replyerror
    def add_export_token(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)
        ioctx = self.get_ioctx(pool)
        ioctx.write_full(image_name + "-export", cmd.token)

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def remove_export_token(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)
        ioctx = self.get_ioctx(pool)
        try:
            ioctx.remove_object(image_name + "-export")
        except rados.ObjectNotFound:
            pass

        rsp = AgentResponse()
        self._set_capacity_to_response(rsp)
        return jsonobject.dumps(rsp)

    @replyerror
    def ping(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = PingRsp()

        monmap = bash_o('ceph mon dump -f json')
        found = False
        for mon in jsonobject.loads(monmap).mons:
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

        pool, objname = cmd.testImagePath.split('/')

        create_img = shell.ShellCmd("echo zstack | timeout 60 rados -p '%s' put '%s' -" % (pool, objname))
        create_img(False)
        if create_img.return_code != 0:
            rsp.success = False
            rsp.failure = 'UnableToCreateFile'
            rsp.error = "%s %s" % (create_img.stderr, create_img.stdout)
        else:
            shell.run("timeout 60 rados -p '%s' rm '%s'" % (pool, objname))

        linux.write_uuids("cephmonbs", "cephmonbs=%s" % cmd.monUuid)
        return jsonobject.dumps(rsp)

    @replyerror
    def delete(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        pool, image_name = self._parse_install_path(cmd.installPath)

        def delete_image(_):
            # in case image is deleted, we don't have to wait for timeout
            img = "%s/%s" % (pool, image_name)
            shell.check_run('rbd info %s && rbd rm %s' % (img, img))
            return True

        # 'rbd rm' might fail due to client crash. We wait for 30 seconds as suggested by 'rbd'.
        #
        # rbd: error: image still has watchers
        # This means the image is still open or the client using it crashed. Try again after
        # closing/unmapping it or waiting 30s for the crashed client to timeout.
        linux.wait_callback_success(delete_image, interval=5, timeout=30, ignore_exception_in_callback=True)

        pool, image_name = self._parse_install_path(cmd.installPath)
        ioctx = self.get_ioctx(pool)
        try:
            ioctx.remove_object(image_name + "-export")
        except rados.ObjectNotFound:
            pass

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

        ssh_cmd, tmp_file = linux.build_sshpass_cmd(dst_mon_addr, dst_mon_passwd, 'tee >(md5sum >/tmp/%s_dst_md5) | rbd import - %s' % (image_uuid, dst_install_path), dst_mon_user, dst_mon_port)
        rst = shell.run("rbd export %s - | tee >(md5sum >/tmp/%s_src_md5) | %s" % (src_install_path, image_uuid, ssh_cmd))
        linux.rm_file_force(tmp_file)
        if rst != 0:
            return rst

        src_md5 = self._read_file_content('/tmp/%s_src_md5' % image_uuid)
        dst_md5 = linux.sshpass_call(dst_mon_addr, dst_mon_passwd, 'cat /tmp/%s_dst_md5' % image_uuid, dst_mon_user, dst_mon_port)
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

    @replyerror
    def cancel(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        return jsonobject.dumps(plugin.cancel_job(cmd, rsp))

class CephDaemon(daemon.Daemon):
    def __init__(self, pidfile, py_process_name):
        super(CephDaemon, self).__init__(pidfile, py_process_name)

    def run(self):
        self.agent = CephAgent()
        self.agent.http_server.start()
