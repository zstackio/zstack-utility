'''

@author: frank
'''
import os
import inspect
import types
import time
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import http
import inventory

logger = log.get_logger(__name__)


class ApiError(Exception):
    ''' Api failure '''


class Api(object):
    '''
    classdocs
    '''

    def set_session_to_api_message(self, apicmd, session_uuid):
        session = inventory.Session()
        session.uuid = session_uuid
        apicmd.session = session
        return apicmd

    def __init__(self, host='localhost', port=8080, api_path='/zstack/api', result_path='/zstack/api/result', curl=False):
        '''
        Constructor
        '''
        if not host:
            host = '127.0.0.1'

        if not port:
            port = 8080

        self.api_url = http.build_url(('http', host, port, api_path))
        self.api_result_url = http.build_url(('http', host, port, result_path))
        self.curl = curl

    def _get_response(self, ret_uuid):
        url = '%s%s' % (self.api_result_url, ret_uuid)
        jstr = http.json_dump_get(url, print_curl=self.curl)
        rsp = jsonobject.loads(jstr)
        return rsp

    def _error_code_to_string(self, error):
        if error is None:
            return ''

        if error.elaboration is not None:
            return "[code: %s, description: %s, details: %s, elaboration: \n%s" % \
                   (error.code, error.description, error.details, error.elaboration)
        else:
            return "[code: %s, description: %s, details: %s]" % \
                   (error.code, error.description, error.details)

    def _check_not_none_field(self, apicmd):
        for k, v in apicmd.__dict__.items():
            if isinstance(v, inventory.NotNoneField):
                err = 'field[%s] of %s cannot be None' % (k, apicmd.FULL_NAME)
                raise ApiError(err)
            elif isinstance(v, inventory.NotNoneList):
                err = 'field[%s] of %s cannot be None, must be a list' % (k, apicmd.FULL_NAME)
                raise ApiError(err)
            elif isinstance(v, inventory.NotNoneMap):
                err = 'field[%s] of %s cannot be None, must be a map' % (k, apicmd.FULL_NAME)
                raise ApiError(err)
            elif isinstance(v, inventory.OptionalList):
                setattr(apicmd, k, None)
            elif isinstance(v, inventory.OptionalMap):
                setattr(apicmd, k, None)
            elif isinstance(v,str) and not v.strip():
                err = 'field[%s] of %s cannot be an empty string' % (k, apicmd.FULL_NAME)
                raise ApiError(err)

    def login_as_admin(self):
        apicmd = inventory.APILogInByAccountMsg()
        apicmd.timeout = 15000
        apicmd.accountName = inventory.INITIAL_SYSTEM_ADMIN_NAME
        apicmd.password = inventory.INITIAL_SYSTEM_ADMIN_PASSWORD
        # print jsonobject.dumps(apicmd)
        (name, reply) = self.sync_call(apicmd)
        if not reply.success: raise ApiError(
            "Cannot login as admin because %s" % self._error_code_to_string(reply.error))
        return reply.inventory.uuid

    def log_out(self, session_uuid):
        apicmd = inventory.APILogOutMsg()
        apicmd.timeout = 15000
        apicmd.sessionUuid = session_uuid
        (name, reply) = self.sync_call(apicmd)
        if not reply.success:
            logger.warn(
                'Logout session[uuid:%s] failed because %s' % (session_uuid, self._error_code_to_string(reply.error)))

    def async_call_wait_for_complete(self, apicmd, apievent=None, exception_on_error=True, interval=500, fail_soon=False):
        # try to find event class from inventory.py for masking sensitive fields
        def create_event(apicmd):
            if not apicmd:
                return None

            apiname = apicmd.__class__.__name__
            if apiname.endswith("Action"):
                event_name = "API" + apiname[0:-6] + "Event"
            else:
                event_name = apiname[0:-3] + "Event"

            try:
                return eval('inventory.%s()' % event_name)
            except:
                return None

        def mask_result(apievent, result):
            event_name, event_str = result[1:-1].split(':', 1)

            if not apievent:
                apievent = create_event(apicmd)

            log_event = log.mask_sensitive_field(apievent, event_str)
            return '{%s: %s}' % (event_name, log_event)

        self._check_not_none_field(apicmd)
        timeout = apicmd.timeout
        if not timeout:
            timeout = 1800000
        cmd = {apicmd.FULL_NAME: apicmd}
        log_cmd = '{"%s": "%s"}' % (apicmd.FULL_NAME, log.mask_sensitive_field(apicmd, jsonobject.dumps(apicmd)))
        logger.debug("async call[url: %s, request: %s]" % (self.api_url, log_cmd))
        jstr = http.json_dump_post(self.api_url, cmd, fail_soon=fail_soon, print_curl=self.curl)
        rsp = jsonobject.loads(jstr)
        if rsp.state == 'Done':
            logger.debug("async call[url: %s, response: %s]" % (self.api_url, mask_result(apievent, rsp.result)))
            reply = jsonobject.loads(rsp.result)
            (name, event) = (reply.__dict__.items()[0])
            if exception_on_error and not event.success:
                raise ApiError('API call[%s] failed because %s' % (name, self._error_code_to_string(event.error)))
            return name, event

        curr = 0
        finterval = float(float(interval) / float(1000))
        ret_uuid = rsp.uuid
        while rsp.state != 'Done' and curr < timeout:
            time.sleep(finterval)
            rsp = self._get_response(ret_uuid)
            curr += interval

        if curr >= timeout:
            raise ApiError('API call[%s] timeout after %dms' % (apicmd.FULL_NAME, curr))

        logger.debug("async call[url: %s, response: %s] after %dms" % (self.api_url, mask_result(apievent, rsp.result), curr))
        reply = jsonobject.loads(rsp.result)
        (name, event) = (reply.__dict__.items()[0])
        if exception_on_error and not event.success:
            raise ApiError('API call[%s] failed because %s' % (name, self._error_code_to_string(event.error)))
        return name, event

    def sync_call(self, apicmd, exception_on_error=True, fail_soon=False):
        self._check_not_none_field(apicmd)
        cmd = {apicmd.FULL_NAME: apicmd}
        logger.debug("sync_call[url: %s, request: %s]" % (self.api_url, jsonobject.dumps(cmd)))
        jstr = http.json_dump_post(self.api_url, cmd, fail_soon=fail_soon, print_curl=self.curl)
        logger.debug("sync_call[url: %s, response: %s]" % (self.api_url, jstr))
        rsp = jsonobject.loads(jstr)
        reply = jsonobject.loads(rsp.result)
        (name, r) = reply.__dict__.items()[0]
        if exception_on_error:
            if not r.success:
                raise ApiError('API call[%s] failed because %s' % (name, self._error_code_to_string(r.error)))
        return name, r


def error_code_to_string(self, error):
    return "[code: %s, description: %s, details: %s]" % (error.code, error.description, error.details)


# ZSTACK_BUILT_IN_HTTP_SERVER_IP should be set as environment variable.
def async_call(apicmd, session_uuid):
    api = Api(host=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_IP'),
              port=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_PORT'))
    api.set_session_to_api_message(apicmd, session_uuid)
    (name, event) = api.async_call_wait_for_complete(apicmd)
    if not event.success:
        raise ApiError(
            "Async call: [%s] meets error: %s." % (apicmd.__class__.__name__, error_code_to_string(event.error)))
    print("[Async call]: [%s] Success" % apicmd.__class__.__name__)
    return event


# ZSTACK_BUILT_IN_HTTP_SERVER_IP should be set as environment variable.
def sync_call(apicmd, session_uuid):
    api = Api(host=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_IP'),
              port=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_PORT'))
    if session_uuid:
        api.set_session_to_api_message(apicmd, session_uuid)
    (name, reply) = api.sync_call(apicmd)
    if not reply.success:
        raise ApiError(
            "Sync call: [%s] meets error: %s." % (apicmd.__class__.__name__, error_code_to_string(reply.error)))
    print("[Sync call]: [%s] Success" % apicmd.__class__.__name__)
    return reply


# ZSTACK_BUILT_IN_HTTP_SERVER_IP should be set as environment variable.
def login_as_admin():
    api = Api(host=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_IP'),
              port=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_PORT'))
    return api.login_as_admin()


# ZSTACK_BUILT_IN_HTTP_SERVER_IP should be set as environment variable.
def logout(session_uuid):
    api = Api(host=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_IP'),
              port=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_PORT'))
    api.log_out(session_uuid)
