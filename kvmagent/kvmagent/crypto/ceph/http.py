from kvmagent import kvmagent
from kvmagent.crypto.http_error import log_failure, response_error
from kvmagent.crypto.ceph import operations
from zstacklib.utils import http, jsonobject


LUKS_CREATE_EMPTY_PATH = '/ceph/primarystorage/kvmhost/lukscreateempty'
LUKS_CLONE_PATH = '/ceph/primarystorage/kvmhost/luksclone'
LUKS_CONVERT_PATH = '/ceph/primarystorage/kvmhost/luksconvert'
VOLUME_ENCRYPT_IN_PLACE_PATH = '/ceph/primarystorage/kvmhost/encryptinplace'
LUKS_RESIZE_PATH = '/ceph/primarystorage/kvmhost/luksresize'
IMAGESTORE_ENCRYPTED_DOWNLOAD_PATH = '/ceph/primarystorage/kvmhost/imagestore/encrypteddownload'


def register_http_handlers(http_server):
    http_server.register_async_uri(LUKS_CREATE_EMPTY_PATH, create)
    http_server.register_async_uri(LUKS_CLONE_PATH, clone)
    http_server.register_async_uri(LUKS_CONVERT_PATH, convert)
    http_server.register_async_uri(VOLUME_ENCRYPT_IN_PLACE_PATH, encrypt_in_place)
    http_server.register_async_uri(LUKS_RESIZE_PATH, resize)
    http_server.register_async_uri(IMAGESTORE_ENCRYPTED_DOWNLOAD_PATH, encrypted_download)


def _operation(req, operation):
    rsp = kvmagent.AgentResponse()
    stage = 'decode_request'
    try:
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        stage = 'execute'
        result = operation(cmd)
        if not isinstance(result, bool):
            rsp.installPath = result
        install_path = (getattr(cmd, 'targetInstallPath', None) or getattr(cmd, 'dstPath', None)
                        or getattr(cmd, 'primaryStorageInstallPath', None) or cmd.installPath)
        stage = 'read_actual_size'
        rsp.actualSize = operations.actual_size(install_path, cmd)
    except Exception as error:
        log_failure('ceph.' + operation.__name__, stage, error)
        rsp.success = False
        rsp.error = response_error(stage, error, (ValueError, FileNotFoundError))
    return jsonobject.dumps(rsp)


def create(req):
    return _operation(req, operations.create_empty)


def clone(req):
    return _operation(req, operations.clone)


def convert(req):
    return _operation(req, operations.convert)


def encrypt_in_place(req):
    return _operation(req, operations.encrypt_in_place)


def resize(req):
    return _operation(req, operations.resize)


def encrypted_download(req):
    def download_encrypted_imagestore(cmd):
        from kvmagent.plugins.imagestore import ImageStoreClient
        return operations.download_encrypted_imagestore(cmd, ImageStoreClient())

    return _operation(req, download_encrypted_imagestore)
