from kvmagent import kvmagent
from kvmagent.crypto.http_error import log_failure
from kvmagent.crypto.ceph import operations
from zstacklib.utils import http, jsonobject


LUKS_CREATE_EMPTY_PATH = '/ceph/primarystorage/kvmhost/lukscreateempty'
LUKS_CLONE_PATH = '/ceph/primarystorage/kvmhost/luksclone'
VOLUME_ENCRYPT_IN_PLACE_PATH = '/ceph/primarystorage/kvmhost/encryptinplace'


def register_http_handlers(http_server):
    http_server.register_async_uri(LUKS_CREATE_EMPTY_PATH, create)
    http_server.register_async_uri(LUKS_CLONE_PATH, clone)
    http_server.register_async_uri(VOLUME_ENCRYPT_IN_PLACE_PATH, encrypt_in_place)


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
        rsp.error = str(error) if isinstance(error, (ValueError, FileNotFoundError)) else type(error).__name__
    return jsonobject.dumps(rsp)


def create(req):
    return _operation(req, operations.create_empty)


def clone(req):
    return _operation(req, operations.clone)


def encrypt_in_place(req):
    return _operation(req, operations.encrypt_in_place)
