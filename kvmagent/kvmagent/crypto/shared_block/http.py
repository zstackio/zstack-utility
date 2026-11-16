from kvmagent import kvmagent
from kvmagent.crypto.http_error import log_failure, response_error
from kvmagent.crypto.shared_block import operations
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock


LOCK_FILE = '/var/run/zstack/sharedblock.lock'
VOLUME_CONVERT_ENCRYPTION_PATH = '/sharedblock/volume/convertencryption'
VOLUME_ENCRYPT_IN_PLACE_PATH = '/sharedblock/volume/encryptinplace'


def register_http_handlers(http_server):
    http_server.register_async_uri(VOLUME_ENCRYPT_IN_PLACE_PATH, encrypt_in_place)
    http_server.register_async_uri(VOLUME_CONVERT_ENCRYPTION_PATH, convert_volume)


@lock.file_lock(LOCK_FILE)
def convert_volume(req):
    rsp = kvmagent.AgentResponse()
    stage = 'decode_request'
    try:
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        stage = 'execute'
        rsp.actualSizes, rsp.totalCapacity, rsp.availableCapacity = operations.convert_items(cmd)
    except Exception as error:
        log_failure('shared_block.convert_volume', stage, error)
        rsp.success = False
        rsp.error = str(error) if isinstance(error, (ValueError, FileNotFoundError, FileExistsError)) else type(error).__name__
    return jsonobject.dumps(rsp)


@lock.file_lock(LOCK_FILE)
def encrypt_in_place(req):
    rsp = kvmagent.AgentResponse()
    stage = 'decode_request'
    try:
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        stage = 'execute'
        operations.encrypt_in_place(cmd)
    except Exception as error:
        log_failure('shared_block.encrypt_in_place', stage, error)
        rsp.success = False
        rsp.error = response_error(stage, error, (ValueError, FileNotFoundError, FileExistsError))
    return jsonobject.dumps(rsp)
