import functools
import time
import uuid as uid
from zstacklib.utils import jsonobject, log
from zstacklib.utils.http import REQUEST_BODY

logger = log.get_logger(__name__)


def uuid():
    return str(uid.uuid4()).replace('-', '')


def make_context_dict(api_msg_name, api_id=uuid(), timeout=1800):
    return {
        "threadContext": {
            "api": api_id,
            "task-name": api_msg_name
        },
        "threadContextStack": [],
        "taskContext": {
            "__messagetimeout__": str(timeout * 1000),
            "__messagedeadline__": str(int(time.time() + timeout) * 1000)
        }
    }

def make_a_request(body):
    # type: (dict) -> dict

    bodyStr = jsonobject.dumps(body, include_protected_attr=True)
    logger.debug("make request" + bodyStr)
    return {
        REQUEST_BODY: bodyStr
    }



def return_jsonobject():
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            r = f(*args, **kwargs)

            if isinstance(r, tuple):
                # for tuple, always assume the first return value is the string to convert
                lst = list(r)
                lst[0] = jsonobject.loads(lst[0])
                return tuple(lst)
            elif isinstance(r, str):
                return jsonobject.loads(r)
            else:
                return r

        return inner

    return wrap

