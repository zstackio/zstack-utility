from kvmagent import kvmagent
from kvmagent.crypto.http_error import log_failure, response_error
from kvmagent.crypto.shared_block import operations
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock


LOCK_FILE = '/var/run/zstack/sharedblock.lock'
VOLUME_ENCRYPT_IN_PLACE_PATH = '/sharedblock/volume/encryptinplace'


def register_http_handlers(http_server):
    http_server.register_async_uri(VOLUME_ENCRYPT_IN_PLACE_PATH, encrypt_in_place)


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
