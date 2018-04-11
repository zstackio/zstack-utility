# coding=utf-8
'''

@author: mingjian.deng
'''
import os.path
import traceback

import zstacklib.utils.uuidhelper as uuidhelper
from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils.bash import *

logger = log.get_logger(__name__)

class PingEBSRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(PingEBSRsp, self).__init__()
        self.echo = None

class AliyunEbsStoragePlugin(kvmagent.KvmAgent):
    INIT_PATH = "/aliyun/ebs/primarystorage/init"
    ECHO_PATH = "/aliyun/ebs/primarystorage/echo"
    PING_PATH = "/aliyun/ebs/primarystorage/ping"
    GET_FACTS = "/aliyun/ebs/primarystorage/facts"
    DELETE_IMAGE_CACHE = "/aliyun/ebs/primarystorage/deleteimagecache"

    CREATE_VOLUME_PATH = "/aliyun/ebs/primarystorage/volume/createempty"
    DELETE_PATH = "/aliyun/ebs/primarystorage/volume/delete"
    CLONE_PATH = "/aliyun/ebs/primarystorage/volume/clone"
    FLATTEN_PATH = "/aliyun/ebs/primarystorage/volume/flatten"
    PURGE_SNAPSHOT_PATH = "/aliyun/ebs/primarystorage/volume/purgesnapshots"
    CP_PATH = "/aliyun/ebs/primarystorage/volume/cp"
    GET_VOLUME_SIZE_PATH = "/aliyun/ebs/primarystorage/volume/getsize"
    RESIZE_VOLUME_PATH = "/aliyun/ebs/primarystorage/volume/resize"
    MIGRATE_VOLUME_PATH = "/aliyun/ebs/primarystorage/volume/migrate"
    MIGRATE_VOLUME_SNAPSHOT_PATH = "/aliyun/ebs/primarystorage/volume/snapshot/migrate"
    GET_VOLUME_SNAPINFOS_PATH = "/aliyun/ebs/primarystorage/volume/getsnapinfos"

    CREATE_SNAPSHOT_PATH = "/aliyun/ebs/primarystorage/snapshot/create"
    DELETE_SNAPSHOT_PATH = "/aliyun/ebs/primarystorage/snapshot/delete"
    COMMIT_IMAGE_PATH = "/aliyun/ebs/primarystorage/snapshot/commit"
    PROTECT_SNAPSHOT_PATH = "/aliyun/ebs/primarystorage/snapshot/protect"
    ROLLBACK_SNAPSHOT_PATH = "/aliyun/ebs/primarystorage/snapshot/rollback"
    UNPROTECT_SNAPSHOT_PATH = "/aliyun/ebs/primarystorage/snapshot/unprotect"
    CHECK_BITS_PATH = "/aliyun/ebs/primarystorage/snapshot/checkbits"

    UPLOAD_IMAGESTORE_PATH = "/aliyun/ebs/primarystorage/imagestore/backupstorage/commit"
    DOWNLOAD_IMAGESTORE_PATH = "/aliyun/ebs/primarystorage/imagestore/backupstorage/download"

    def start(self):
        http_server = kvmagent.get_http_server()
        # http_server.register_async_uri(self.INIT_PATH, self.init)
        # http_server.register_async_uri(self.DELETE_PATH, self.delete)
        # http_server.register_async_uri(self.CREATE_VOLUME_PATH, self.create)
        # http_server.register_async_uri(self.CLONE_PATH, self.clone)
        # http_server.register_async_uri(self.COMMIT_IMAGE_PATH, self.commit_image)
        # http_server.register_async_uri(self.CREATE_SNAPSHOT_PATH, self.create_snapshot)
        # http_server.register_async_uri(self.DELETE_SNAPSHOT_PATH, self.delete_snapshot)
        # http_server.register_async_uri(self.PURGE_SNAPSHOT_PATH, self.purge_snapshots)
        # http_server.register_async_uri(self.PROTECT_SNAPSHOT_PATH, self.protect_snapshot)
        # http_server.register_async_uri(self.UNPROTECT_SNAPSHOT_PATH, self.unprotect_snapshot)
        # http_server.register_async_uri(self.ROLLBACK_SNAPSHOT_PATH, self.rollback_snapshot)
        # http_server.register_async_uri(self.FLATTEN_PATH, self.flatten)
        # http_server.register_async_uri(self.CP_PATH, self.cp)
        # http_server.register_async_uri(self.UPLOAD_IMAGESTORE_PATH, self.upload_imagestore)
        # http_server.register_async_uri(self.DOWNLOAD_IMAGESTORE_PATH, self.download_imagestore)
        # http_server.register_async_uri(self.GET_VOLUME_SIZE_PATH, self.get_volume_size)
        # http_server.register_async_uri(self.PING_PATH, self.ping)
        # http_server.register_async_uri(self.GET_FACTS, self.get_facts)
        # http_server.register_async_uri(self.DELETE_IMAGE_CACHE, self.delete_image_cache)
        # http_server.register_async_uri(self.CHECK_BITS_PATH, self.check_bits)
        # http_server.register_async_uri(self.RESIZE_VOLUME_PATH, self.resize_volume)
        # http_server.register_sync_uri(self.ECHO_PATH, self.echo)
        # http_server.register_async_uri(self.MIGRATE_VOLUME_PATH, self.migrate_volume)
        # http_server.register_async_uri(self.MIGRATE_VOLUME_SNAPSHOT_PATH, self.migrate_volume_snapshot)
        # http_server.register_async_uri(self.GET_VOLUME_SNAPINFOS_PATH, self.get_volume_snapinfos)

        self.image_cache = None
        self.imagestore_client = ImageStoreClient()

    def stop(self):
        pass

    @kvmagent.replyerror
    def echo(self, req):
        logger.debug('get echoed')
        return ''

    @kvmagent.replyerror
    def ping(self, req):
        logger.debug('ping river master')
        rsp = PingEBSRsp()
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        ret = http.json_post(cmd.uri, body=cmd.body)
        rsp.echo = ret.echo
        return jsonobject.dumps(rsp)