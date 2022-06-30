from concurrent import futures
import json
import sys

from oslo_concurrency import processutils
from oslo_log import log as logging
import pecan
from pecan import request
import requests

from bm_instance_agent.conf import CONF
from bm_instance_agent.objects import HeaderObj
from bm_instance_agent.common.utils import transcantion


THREAD_POOL = None


if not THREAD_POOL:
    workers = CONF.api.api_workers or processutils.get_worker_count()
    THREAD_POOL = futures.ThreadPoolExecutor(max_workers=workers)


LOG = logging.getLogger(__name__)


def sync_expose(func):
    @pecan.expose(template='json')
    @suppress_exception
    def wrap(*args, **kwargs):
        ret = func(*args, **kwargs)
        ret.update({
            'success': True,
            'error': None
        })
        return ret
    return wrap


def async_expose(func):
    @pecan.expose(template='json')
    @suppress_exception
    def wrap(*args, **kwargs):
        # FIXME(ya.wang) Construct the headers obj at expose decorate, do
        # the action here may cause nested import.
        headers_obj = HeaderObj.from_headers(request.headers)

        global THREAD_POOL
        f = THREAD_POOL.submit(func, *args, **kwargs)
        f.add_done_callback(async_callback(headers_obj))
        return
    return wrap


def async_callback(headers_obj):
    headers_obj = headers_obj

    def _async_callback(future):
        exc = future.exception()

        if exc:
            LOG.exception(exc)
            data = {
                'success': False,
                'error': '\n'.join([str(x) for x in exc.args])
            }
        else:
            ret = future.result()
            data = ret if ret else {}
            data.update({
                'success': True,
                'error': None
            })

        url = headers_obj.callback_url
        headers = {
            'taskuuid': headers_obj.task_uuid
        }

        with transcantion(retries=5, sleep_time=1) as cursor:
            # cursor.execute(_post, data)
            cursor.execute(_post, url, headers, data)

    return _async_callback


def _post(url, headers, data):
    """ Call the callback uri

    Place here for easy mock
    """
    requests.post(url=url,
                  headers=headers,
                  data=json.dumps(data),
                  timeout=3)


def suppress_exception(func):
    def wrap(*args, **kwargs):
        try:
            ret = func(*args, **kwargs)
            return ret
        except Exception:
            return format_exception()
    return wrap


def format_exception():
    exception_info = sys.exc_info()
    orig_exception = exception_info[1]
    traceback = exception_info[2]

    error_msg = '\n'.join([str(x) for x in orig_exception.args])

    data = {
        'success': False,
        'error': error_msg
    }

    LOG.error(orig_exception)
    LOG.exception(traceback)

    del exception_info

    return data
