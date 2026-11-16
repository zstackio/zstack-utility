from kvmagent import kvmagent
from kvmagent.crypto.http_error import log_failure, response_error
from kvmagent.crypto.file_volume import operations
from zstacklib.utils import http, jsonobject


LOCAL_VOLUME_ENCRYPT_IN_PLACE_PATH = '/localstorage/volume/encryptinplace'
LOCAL_VOLUME_CONVERT_ENCRYPTION_PATH = '/localstorage/volume/convertencryption'
NFS_VOLUME_ENCRYPT_IN_PLACE_PATH = '/nfsprimarystorage/volume/encryptinplace'
NFS_VOLUME_CONVERT_ENCRYPTION_PATH = '/nfsprimarystorage/volume/convertencryption'


def register_http_handlers(http_server):
    http_server.register_async_uri(LOCAL_VOLUME_ENCRYPT_IN_PLACE_PATH, encrypt_in_place)
    http_server.register_async_uri(LOCAL_VOLUME_CONVERT_ENCRYPTION_PATH, convert_volume)
    http_server.register_async_uri(NFS_VOLUME_ENCRYPT_IN_PLACE_PATH, encrypt_in_place)
    http_server.register_async_uri(NFS_VOLUME_CONVERT_ENCRYPTION_PATH, convert_volume)


def encrypt_in_place(req):
    rsp = kvmagent.AgentResponse()
    stage = 'decode_request'
    try:
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        stage = 'execute'
        operations.encrypt_in_place(cmd)
    except Exception as error:
        log_failure('file_volume.encrypt_in_place', stage, error)
        rsp.success = False
        rsp.error = response_error(stage, error, (ValueError, FileNotFoundError, FileExistsError))
    return jsonobject.dumps(rsp)


def convert_volume(req):
    rsp = kvmagent.AgentResponse()
    stage = 'decode_request'
    try:
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        stage = 'execute'
        rsp.actualSizes = operations.convert_items(cmd)
    except Exception as error:
        log_failure('file_volume.convert_volume', stage, error)
        rsp.success = False
        rsp.error = str(error) if isinstance(error, (ValueError, FileNotFoundError, FileExistsError)) else type(error).__name__
    return jsonobject.dumps(rsp)
