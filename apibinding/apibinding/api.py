'''

@author: frank
'''
import os
import time
from numbers import Integral
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import http
from . import inventory

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

    def _get_async_result_url(self, ret_uuid):
        url = '%s%s' % (self.api_result_url, ret_uuid)
        return url

    def _get_response(self, ret_uuid):
        url = self._get_async_result_url(ret_uuid)
        jstr = http.json_dump_get(url, print_curl=self.curl)
        rsp = jsonobject.loads(jstr)
        return rsp

    # Constants for error formatting
    _MAX_INDENT_LEVEL = 4
    _INDENT_SPACES = "  "
    _CIRCULAR_REF_MSG = '[circular reference detected]'
    _MAX_DEPTH_MSG_PREFIX = '[error details too deep'

    def _error_code_to_string(self, error, visited=None, max_depth=10, _depth=0):
        """Convert error object to formatted string with cause chain support.

        Args:
            error: Error object to format
            visited: Set of visited error IDs (for circular reference detection)
            max_depth: Maximum recursion depth (default: 10)
            _depth: Current recursion depth (internal use only)

        Returns:
            Formatted error string with cause chain, or empty string if error is None

        Examples:
            Simple error:
                [code: ERR001, description: Test error, details: Some details]

            Error with cause chain:
                [code: ERR001, description: Top error, details: Details]
                  caused by: [code: ERR002, description: Root cause, details: Root details]
        """
        if visited is None:
            visited = set()

        if error is None:
            return ''

        # Check depth limit based on recursion level, not visited count
        if _depth >= max_depth:
            return '{0} - max depth {1} reached]'.format(self._MAX_DEPTH_MSG_PREFIX, max_depth)

        error_id = id(error)
        # Check for circular reference
        if error_id in visited:
            return self._CIRCULAR_REF_MSG

        visited.add(error_id)

        # Safely get error attributes with defaults
        code = getattr(error, 'code', 'UNKNOWN')
        description = getattr(error, 'description', 'No description')
        details = getattr(error, 'details', 'No details')
        elaboration = getattr(error, 'elaboration', None)

        # Build error message parts efficiently
        msg_parts = []

        # Use safer string formatting to handle special characters
        try:
            msg_parts.append("[code: {0}, description: {1}, details: {2}".format(code, description, details))
        except (TypeError, ValueError):
            # Fallback if format fails
            msg_parts.append("[code: <format error>, description: <format error>, details: <format error>]")

        # Safely handle elaboration with proper error handling
        if elaboration is not None:
            try:
                elaboration_str = str(elaboration).strip()
                if elaboration_str:
                    msg_parts.append(", elaboration: \n{0}".format(elaboration_str))
            except Exception as e:
                # If str() fails, skip elaboration rather than crashing
                logger.warn("Failed to convert elaboration to string: %s", e)

        msg_parts.append("]")

        # Handle cause chain with limited indentation (max 4 levels = 8 spaces)
        if hasattr(error, 'cause') and error.cause is not None:
            indent = self._INDENT_SPACES * min(_depth + 1, self._MAX_INDENT_LEVEL)
            try:
                cause_str = self._error_code_to_string(error.cause, visited, max_depth, _depth + 1)
                # Only append if we got meaningful content
                if cause_str:
                    # Check if it's a special message (circular reference or max depth)
                    is_special_msg = (cause_str == self._CIRCULAR_REF_MSG or
                                     cause_str.startswith(self._MAX_DEPTH_MSG_PREFIX))
                    if not is_special_msg:
                        msg_parts.append("\n{0}caused by: {1}".format(indent, cause_str))
                    else:
                        # For special messages, show them without "caused by:" prefix
                        msg_parts.append("\n{0}{1}".format(indent, cause_str))
            except Exception as e:
                # Catch any unexpected errors in recursive call to prevent cascading failures
                try:
                    error_msg = str(e)
                except:
                    error_msg = repr(e) if hasattr(e, '__repr__') else 'unknown error'
                msg_parts.append("\n{0}[error processing cause: {1}]".format(indent, error_msg))

        return ''.join(msg_parts)

    def _check_not_none_field(self, apicmd):
        for k, v in list(apicmd.__dict__.items()):
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

    def async_call_wait_for_complete(self, apicmd, apievent=None, exception_on_error=True, interval=500, fail_soon=False,
                                     headers=None):
        if headers is None:
            headers = {}
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
        cmd = {apicmd.FULL_NAME: apicmd}
        log_cmd = '{"%s": "%s"}' % (apicmd.FULL_NAME, log.mask_sensitive_field(apicmd, jsonobject.dumps(apicmd)))
        logger.debug("async call[url: %s, request: %s]" % (self.api_url, log_cmd))
        jstr = http.json_dump_post(self.api_url, cmd, headers=headers, fail_soon=fail_soon, print_curl=self.curl)
        rsp = jsonobject.loads(jstr)
        if rsp.state == 'Done':
            logger.debug("async call[url: %s, response: %s]" % (self.api_url, mask_result(apievent, rsp.result)))
            reply = jsonobject.loads(rsp.result)
            (name, event) = (list(reply.__dict__.items())[0])
            if exception_on_error and not event.success:
                raise ApiError('API call[%s] failed because %s' % (name, self._error_code_to_string(event.error)))
            return name, event

        timeout = apicmd.timeout
        if not timeout:
            server_timeout = getattr(rsp, 'apiTimeout', None)
            timeout = server_timeout if (isinstance(server_timeout, Integral) and
                                         not isinstance(server_timeout, bool) and server_timeout > 0) else 1800000

        curr = 0
        finterval = float(float(interval) / float(1000))
        ret_uuid = rsp.uuid
        while rsp.state != 'Done' and curr < timeout:
            time.sleep(finterval)
            rsp = self._get_response(ret_uuid)
            curr += interval

        if curr >= timeout:
            raise ApiError('API call[%s] timeout after %dms, state[%s]. Request result url for details: %s' % (
                apicmd.FULL_NAME, timeout, rsp.state, self._get_async_result_url(ret_uuid)))

        logger.debug("async call[url: %s, response: %s] after %dms" % (self.api_url, mask_result(apievent, rsp.result), curr))
        reply = jsonobject.loads(rsp.result)
        (name, event) = (list(reply.__dict__.items())[0])
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
        (name, r) = list(reply.__dict__.items())[0]
        if exception_on_error:
            if not r.success:
                raise ApiError('API call[%s] failed because %s' % (name, self._error_code_to_string(r.error)))
        return name, r


def error_code_to_string(error):
    """Module-level helper function for error formatting.

    Note: This provides basic error formatting without cause chain handling.
    For full error chain formatting, use Api._error_code_to_string() instead.
    """
    if error is None:
        return ''

    code = getattr(error, 'code', 'UNKNOWN')
    description = getattr(error, 'description', 'No description')
    details = getattr(error, 'details', 'No details')
    return "[code: %s, description: %s, details: %s]" % (code, description, details)


# ZSTACK_BUILT_IN_HTTP_SERVER_IP should be set as environment variable.
def async_call(apicmd, session_uuid):
    api = Api(host=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_IP'),
              port=int(os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_PORT')))
    api.set_session_to_api_message(apicmd, session_uuid)
    (name, event) = api.async_call_wait_for_complete(apicmd)
    if not event.success:
        raise ApiError(
            "Async call: [%s] meets error: %s." % (apicmd.__class__.__name__, error_code_to_string(event.error)))
    print(("[Async call]: [%s] Success" % apicmd.__class__.__name__))
    return event


# ZSTACK_BUILT_IN_HTTP_SERVER_IP should be set as environment variable.
def sync_call(apicmd, session_uuid):
    api = Api(host=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_IP'),
              port=int(os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_PORT')))
    if session_uuid:
        api.set_session_to_api_message(apicmd, session_uuid)
    (name, reply) = api.sync_call(apicmd)
    if not reply.success:
        raise ApiError(
            "Sync call: [%s] meets error: %s." % (apicmd.__class__.__name__, error_code_to_string(reply.error)))
    print(("[Sync call]: [%s] Success" % apicmd.__class__.__name__))
    return reply


# ZSTACK_BUILT_IN_HTTP_SERVER_IP should be set as environment variable.
def login_as_admin():
    api = Api(host=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_IP'),
              port=int(os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_PORT')))
    return api.login_as_admin()


# ZSTACK_BUILT_IN_HTTP_SERVER_IP should be set as environment variable.
def logout(session_uuid):
    api = Api(host=os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_IP'),
              port=int(os.environ.get('ZSTACK_BUILT_IN_HTTP_SERVER_PORT')))
    api.log_out(session_uuid)
