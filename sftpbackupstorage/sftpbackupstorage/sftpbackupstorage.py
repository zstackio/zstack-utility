'''

@author: frank
'''
from zstacklib.utils import report
from zstacklib.utils import plugin, traceable_shell
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import shell
from zstacklib.utils import daemon
from zstacklib.utils.bash import *
from zstacklib.utils import secret
import functools
import urlparse
import traceback
import pprint
import os.path
import os
import shutil
import stat

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
        self.actualSize = None
        self.format = None

class DeleteImageMetaDataResponse(AgentResponse):
    def __init__(self):
        super(DeleteImageMetaDataResponse,self).__init__()
        self.ret = None

class DeleteImageMetaDataCmd(AgentCommand):
    def __init__(self):
        super(DeleteImageMetaDataCmd, self).__init__()
        self.uuid= None

class WriteImageMetaDataResponse(AgentResponse):
    def __init__(self):
        super(WriteImageMetaDataResponse,self).__init__()

class WriteImageMetaDataCmd(AgentCommand):
    def __init__(self):
        super(WriteImageMetaDataCmd, self).__init__()
        self.metaData = None

class GetImageMetaDataResponse(AgentResponse):
    def __init__(self):
        super(GetImageMetaDataResponse,self).__init__()
        self.imagesMetaData = None

class GetImageMetaDataCmd(AgentCommand):
    def __init__(self):
        super(GetImageMetaDataCmd, self).__init__()
        self.bsPath = None

class DumpImageMetaDataToFileResponse(AgentResponse):
    def __init__(self):
        super(DumpImageMetaDataToFileResponse,self).__init__()

class DumpImageMetaDataToFileCmd(AgentCommand):
    def __init__(self):
        super(DumpImageMetaDataToFileCmd, self).__init__()
        self.metaData = None

class GenerateImageMetaDataFileResponse(AgentResponse):
    def __init__(self):
        super(GenerateImageMetaDataFileResponse, self).__init__()
        self.bsFileName = None

class GenerateImageMetaDataFileCmd(AgentCommand):
    def __init__(self):
        super(GenerateImageMetaDataFileCmd, self).__init__()
        self.bsPath = None

class CheckImageMetaDataFileExistResponse(AgentResponse):
    def __init__(self):
        super(CheckImageMetaDataFileExistResponse, self).__init__()
        self.backupStorageMetaFileName = None
        self.exist = None

class CheckImageMetaDataFileExistCmd(AgentCommand):
    def __init__(self):
        super(CheckImageMetaDataFileExistCmd, self).__init__()
        self.bsPath = None

class GetSshKeyCommand(AgentCommand):
    def __init__(self):
        super(GetSshKeyCommand, self).__init__()

class GetSshKeyResponse(AgentResponse):
    def __init__(self):
        self.sshKey = None
        super(GetSshKeyResponse, self).__init__()

class GetImageSizeRsp(AgentResponse):
    def __init__(self):
        super(GetImageSizeRsp, self).__init__()
        self.actualSize = None
        self.size = None

class GetLocalFileSizeRsp(AgentResponse):
    def __init__(self):
        super(GetLocalFileSizeRsp, self).__init__()
        self.size = None


class GetImageHashRsp(AgentResponse):
    def __init__(self):
        super(GetImageHashRsp, self).__init__()
        self.hash = None


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
    DELETE_IMAGES_METADATA = "/sftpbackupstorage/deleteimagesmetadata"
    DUMP_IMAGE_METADATA_TO_FILE = "/sftpbackupstorage/dumpimagemetadatatofile"
    GENERATE_IMAGE_METADATA_FILE = "/sftpbackupstorage/generateimagemetadatafile"
    CHECK_IMAGE_METADATA_FILE_EXIST = "/sftpbackupstorage/checkimagemetadatafileexist"
    GET_IMAGES_METADATA = "/sftpbackupstorage/getimagesmetadata"
    GET_IMAGE_SIZE = "/sftpbackupstorage/getimagesize"
    GET_LOCAL_FILE_SIZE = "/sftpbackupstorage/getlocalfilesize"
    GET_IMAGE_HASH = "/sftpbackupstorage/gethash"
    JOB_CANCEL = "/job/cancel"

    IMAGE_TEMPLATE = 'template'
    IMAGE_ISO = 'iso'
    URL_HTTP = 'http'
    URL_HTTPS = 'https'
    URL_FILE = 'file'
    URL_SFTP = 'sftp'
    URL_FTP = 'ftp'
    URL_NFS = 'nfs'
    PORT = 7171
    SSHKEY_PATH = "~/.ssh/id_rsa.sftp"
    SFTP_METADATA_FILE = "bs_sftp_info.json"

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
    def get_image_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetImageSizeRsp()
        rsp.size, rsp.actualSize = linux.qcow2_size_and_actual_size(cmd.installPath)
        return jsonobject.dumps(rsp)

    @replyerror
    def get_local_file_size(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetLocalFileSizeRsp()
        rsp.size = linux.get_local_file_size(cmd.path)
        return jsonobject.dumps(rsp)

    @replyerror
    def connect(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self.storage_path = cmd.storagePath
        self.uuid = cmd.uuid
        report.Report.url = cmd.sendCommandUrl

        if os.path.isfile(self.storage_path):
            raise Exception('storage path: %s is a file' % self.storage_path)
        if not os.path.exists(self.storage_path):
            os.makedirs(self.storage_path, 0777)
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


    @in_bash
    def _generate_image_metadata_file(self, bs_path):
        bs_meta_file = bs_path + '/' + self.SFTP_METADATA_FILE
        if os.path.isfile(bs_meta_file) is False:
            #dir = '/'.join(bs_path.split("/")[:-1])
            if os.path.exists(bs_path) is False:
                os.makedirs(bs_path)
            ret, output = bash_ro("touch %s" % bs_meta_file)
            if ret == 0:
                return  bs_meta_file
            else:
                raise  Exception('can not create image metadata file %s' % output)
        else:
            return bs_meta_file

    @replyerror
    def generate_image_metadata_file(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        bs_path = cmd.backupStoragePath
        file_name = self._generate_image_metadata_file(bs_path)
        rsp = GenerateImageMetaDataFileResponse()
        rsp.bsFileName = file_name
        return jsonobject.dumps(rsp)

    @replyerror
    def check_image_metadata_file_exist(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        bs_path = cmd.backupStoragePath
        # todo change bs_sftp_info.json to bs_image_info.json
        bs_sftp_info_file = bs_path + '/' + self.SFTP_METADATA_FILE
        rsp = CheckImageMetaDataFileExistResponse()
        rsp.backupStorageMetaFileName = bs_sftp_info_file
        if os.path.isfile(bs_sftp_info_file):
            rsp.exist = True
        else:
            rsp.exist = False
        return jsonobject.dumps(rsp)

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
        bs_sftp_info_file = cmd.backupStoragePath + '/' + self.SFTP_METADATA_FILE
        content = cmd.imageMetaData
        dump_all_metadata = cmd.dumpAllMetaData
        if content is not None:
            if '[' == content[0] and ']' == content[-1]:
                if dump_all_metadata is True:
                    with open(bs_sftp_info_file, 'w') as fd:
                        _write_info_to_metadata_file(fd)
                else:
                    with open(bs_sftp_info_file, 'a') as fd:
                        _write_info_to_metadata_file(fd)
            else:
                #one image info
                if dump_all_metadata is True:
                    with open(bs_sftp_info_file, 'w') as fd:
                        fd.write(content + '\n')
                else:
                    with open(bs_sftp_info_file, 'a') as fd:
                        fd.write(content + '\n')

        rsp = DumpImageMetaDataToFileResponse()
        return jsonobject.dumps(rsp)

    @in_bash
    @replyerror
    def delete_image_metadata_from_file(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        image_uuid = cmd.imageUuid
        bs_sftp_info_file = cmd.backupStoragePath + '/' + self.SFTP_METADATA_FILE
        ret, output = bash_ro("sed -i.bak '/%s/d' %s" % (image_uuid, bs_sftp_info_file))
        rsp = DeleteImageMetaDataResponse()
        rsp.ret = ret
        return jsonobject.dumps(rsp)

    @in_bash
    @replyerror
    def get_images_metadata(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        valid_images_info = ""
        bs_sftp_info_file = cmd.backupStoragePath + '/' + self.SFTP_METADATA_FILE
        image_uuid_list = []
        with open(bs_sftp_info_file) as fd:
            images_info = fd.read()
            for image_info in images_info.split('\n'):
                if image_info != '':
                    image_json = jsonobject.loads(image_info)
                    # todo support multiple bs
                    image_uuid = image_json['uuid']
                    image_install_path = image_json["backupStorageRefs"][0]["installPath"]
                    if image_uuid in image_uuid_list:
                        logger.debug("duplicate uuid %s, ignore" % image_json["uuid"])
                        continue
                    image_uuid_list.append(image_uuid)
                    if os.path.exists(image_install_path):
                        logger.info("Check image %s install path %s successfully!" % (image_uuid, image_install_path))
                        valid_images_info = image_info + '\n' + valid_images_info
                    else:
                        logger.warn("Image %s install path %s is invalid!" % (image_uuid, image_install_path))

        rsp = GetImageMetaDataResponse()
        rsp.imagesMetaData = valid_images_info
        return jsonobject.dumps(rsp)

    @in_bash
    @replyerror
    def download_image(self, req):
        #TODO: report percentage to mgmt server
        def percentage_callback(percent, url):
            reporter.progress_report(int(percent))

        def use_wget(url, name, workdir, timeout):
            return linux.wget(url, workdir=workdir, rename=name, timeout=timeout, interval=2, callback=percentage_callback, callback_data=url)

        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        reporter = report.Report.from_spec(cmd, "DownloadImage")

        t_shell = traceable_shell.get_shell(cmd)
        rsp = DownloadResponse()
        # for download failure
        (total, avail) = self.get_capacity()
        rsp.totalCapacity = total
        rsp.availableCapacity = avail

        supported_schemes = [self.URL_HTTP, self.URL_HTTPS, self.URL_FTP, self.URL_SFTP, self.URL_FILE]
        if cmd.urlScheme not in supported_schemes:
            rsp.success = False
            rsp.error = 'unsupported url scheme[%s], SimpleSftpBackupStorage only supports %s' % (cmd.urlScheme, supported_schemes)
            return jsonobject.dumps(rsp)

        path = os.path.dirname(cmd.installPath)
        if not os.path.exists(path):
            os.makedirs(path, 0777)
        image_name = os.path.basename(cmd.installPath)
        install_path = cmd.installPath

        timeout = cmd.timeout if cmd.timeout else 7200
        url = urlparse.urlparse(cmd.url)
        if cmd.urlScheme in [self.URL_HTTP, self.URL_HTTPS, self.URL_FTP]:
            try:
                cmd.url = linux.shellquote(cmd.url)
                ret = use_wget(cmd.url, image_name, path, timeout)
                if ret != 0:
                    linux.rm_file_force(install_path)
                    rsp.success = False
                    rsp.error = 'http/https/ftp download failed, [wget -O %s %s] returns value %s' % (image_name, cmd.url, ret)
                    return jsonobject.dumps(rsp)
            except linux.LinuxError as e:
                linux.rm_file_force(install_path)
                traceback.format_exc()
                rsp.success = False
                rsp.error = str(e)
                return jsonobject.dumps(rsp)
        elif cmd.urlScheme == self.URL_SFTP:
            ssh_pass_file = None
            port = (url.port, 22)[url.port is None]

            class SftpDownloadDaemon(plugin.TaskDaemon):
                def _cancel(self):
                    pass

                def _get_percent(self):
                    return os.stat(install_path).st_size / (total_size / 100) if os.path.exists(install_path) else 0

                def __exit__(self, exc_type, exc_val, exc_tb):
                    super(SftpDownloadDaemon, self).__exit__(exc_type, exc_val, exc_tb)
                    if ssh_pass_file:
                        linux.rm_file_force(ssh_pass_file)
                    if exc_val is not None:
                        linux.rm_file_force(install_path)
                        traceback.format_exc()

            with SftpDownloadDaemon(cmd, "DownloadImage"):
                sftp_cmd = "sftp -P %d -o BatchMode=no -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -b /dev/stdin %s@%s " \
                           "<<EOF\n%%s\nEOF\n" % (port, url.username, url.hostname)
                if url.password is not None:
                    ssh_pass_file = linux.write_to_temp_file(url.password)
                    sftp_cmd = 'sshpass -f %s %s' % (ssh_pass_file, sftp_cmd)

                total_size = int(shell.call(sftp_cmd % ("ls -l " + url.path)).splitlines()[1].split()[4])
                t_shell.call(sftp_cmd % ("reget %s %s" % (url.path, install_path)))

        elif cmd.urlScheme == self.URL_FILE:
            src_path = cmd.url.lstrip('file:')
            src_path = os.path.normpath(src_path)
            if not os.path.isfile(src_path):
                raise Exception('cannot find the file[%s]' % src_path)
            logger.debug("src_path is: %s" % src_path)
            try:
                t_shell.call('yes | cp %s %s' % (src_path, linux.shellquote(install_path)))
            except shell.ShellError as e:
                linux.rm_file_force(install_path)
                raise e

        os.chmod(cmd.installPath, stat.S_IRUSR + stat.S_IRGRP + stat.S_IROTH)

        try:
            image_format = linux.get_img_file_fmt(linux.shellquote(install_path))
        except Exception as e:
            image_format = "raw"
        size = os.path.getsize(install_path)
        md5sum = 'not calculated'
        logger.debug('successfully downloaded %s to %s' % (cmd.url, install_path))
        (total, avail) = self.get_capacity()
        rsp.md5Sum = md5sum
        rsp.actualSize = size
        rsp.size = linux.qcow2_virtualsize(install_path)
        rsp.totalCapacity = total
        rsp.availableCapacity = avail
        rsp.format = image_format
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

    @replyerror
    def cancel(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = AgentResponse()
        if not traceable_shell.cancel_job(cmd):
            rsp.success = False
            rsp.error = "no matched job to cancel"
        return jsonobject.dumps(rsp)

    @replyerror
    def get_image_hash(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = GetImageHashRsp()

        rsp.hash = secret.get_image_hash(cmd.path)
        return jsonobject.dumps(rsp)

    def __init__(self):
        '''
        Constructor
        '''
        super(SftpBackupStorageAgent, self).__init__()
        self.http_server.register_sync_uri(self.CONNECT_PATH, self.connect)
        self.http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        self.http_server.register_async_uri(self.DOWNLOAD_IMAGE_PATH, self.download_image)
        self.http_server.register_async_uri(self.DELETE_IMAGE_PATH, self.delete_image)
        self.http_server.register_async_uri(self.GET_SSHKEY_PATH, self.get_sshkey)
        self.http_server.register_async_uri(self.WRITE_IMAGE_METADATA, self.write_image_metadata)
        self.http_server.register_async_uri(self.GENERATE_IMAGE_METADATA_FILE, self.generate_image_metadata_file)
        self.http_server.register_async_uri(self.CHECK_IMAGE_METADATA_FILE_EXIST, self.check_image_metadata_file_exist)
        self.http_server.register_async_uri(self.DUMP_IMAGE_METADATA_TO_FILE, self.dump_image_metadata_to_file)
        self.http_server.register_async_uri(self.DELETE_IMAGES_METADATA, self.delete_image_metadata_from_file)
        self.http_server.register_async_uri(self.GET_IMAGES_METADATA, self.get_images_metadata)
        self.http_server.register_async_uri(self.PING_PATH, self.ping)
        self.http_server.register_async_uri(self.GET_IMAGE_SIZE, self.get_image_size)
        self.http_server.register_async_uri(self.GET_LOCAL_FILE_SIZE, self.get_local_file_size)
        self.http_server.register_async_uri(self.JOB_CANCEL, self.cancel)
        self.http_server.register_async_uri(self.GET_IMAGE_HASH, self.get_image_hash)
        self.storage_path = None
        self.uuid = None

class SftpBackupStorageDaemon(daemon.Daemon):
    def __init__(self, pidfile, py_process_name):
        super(SftpBackupStorageDaemon, self).__init__(pidfile, py_process_name)

    def run(self):
        self.agent = SftpBackupStorageAgent()
        self.agent.http_server.start()

def _build_url_for_test(paths):
    builder = http.UriBuilder('http://localhost:%s' % SftpBackupStorageAgent.PORT)
    for p in paths:
        builder.add_path(p)
    return builder.build()
