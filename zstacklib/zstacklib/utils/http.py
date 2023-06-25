'''

@author: frank
'''
import copy
import traceback
import types

import cherrypy
import thread
import threading

import os
import urllib3
from zstacklib.utils import jsonobject
from zstacklib.utils import log
from zstacklib.utils import linux
from zstacklib.utils import debug

TASK_UUID = 'taskuuid'
ERROR_CODE = 'error'
REQUEST_HEADER = 'header'
REQUEST_BODY = 'body'
CALLBACK_URI = 'callbackurl'

logger = log.get_logger(__name__)
debug.install_runtime_tracedumper()

class SyncUri(object):
    def __init__(self):
        self.uri = None
        self.func = None
        self.controller = None
        self.cmd = None

class RawUri(object):
    def __init__(self):
        self.uri = None
        self.func = None
        self.controller = None

class AsyncUri(SyncUri):
    def __init__(self):
        super(AsyncUri, self).__init__()
        self.callback_uri = None

class Request(object):
    def __init__(self):
        self.headers = None
        self.body = None
        self.method = None
        self.query_string = None

    @staticmethod
    def from_cherrypy_request(creq):
        req = Request()
        req.headers = copy.copy(creq.headers)
        req.body = creq.body.fp.read() if creq.body else None
        req.method = copy.copy(creq.method)
        req.query_string = copy.copy(creq.query_string) if creq.query_string else None
        return req

class SyncUriHandler(object):
    def _check_response(self, rsp):
        if rsp is not None and not isinstance(rsp, types.StringType):
            raise Exception('Response body must be string')

    def __init__(self, uri_obj):
        # type:(SyncUri) -> None
        self.uri_obj = uri_obj

    def _do_index(self, req):
        task_uuid = cherrypy.request.headers.get(TASK_UUID)
        if task_uuid:
            err = '[ERROR]: find async task uuid[%s] in header, did you wrongly register sync uri for async call???' % task_uuid
            logger.debug(err)
            raise Exception(err)

        entity = {REQUEST_HEADER : req.headers}
        entity[REQUEST_BODY] = req.body if req.body else None
        return self.uri_obj.func(entity)

    @cherrypy.expose
    def index(self):
        req = Request.from_cherrypy_request(cherrypy.request)
        logger.debug('sync http call: %s' % req.body)
        rsp = self._do_index(req)
        self._check_response(rsp)
        logger.debug("sync http reply to %s: \"%s\"" % (cherrypy.url(), rsp))
        return rsp

class RawUriHandler(object):
    def __init__(self, uri_obj):
        self.uri_obj = uri_obj

    @cherrypy.config(**{'response.timeout': 7200}) # default is 300s
    @cherrypy.expose
    def index(self):
        logger.debug('raw http handler: %s' % self.uri_obj.uri)
        try:
            return self.uri_obj.func(cherrypy.request)
        except Exception as e:
            content = traceback.format_exc()
            logger.warn('[WARN]: %s]' % content)
            if isinstance(e, cherrypy.HTTPError):
                cherrypy.response.status = e.status
                return e._message
            else:
                cherrypy.response.status = 500
                return str(e)

class RawUriStreamHandler(object):
    def __init__(self, uri_obj):
        self.uri_obj = uri_obj

    @cherrypy.config(**{'response.timeout': 7200}) # default is 300s
    @cherrypy.expose
    def index(self, **kwargs):
        logger.debug('raw http handler: %s' % self.uri_obj.uri)
        try:
            return self.uri_obj.func(cherrypy.request, cherrypy.response, **kwargs)
        except Exception as e:
            content = traceback.format_exc()
            logger.warn('[WARN]: %s]' % content)
            cherrypy.response.status = 500
            return str(e)

    index._cp_config = {'response.stream': True}


class AsyncUirHandler(SyncUriHandler):
    HANDLER_DICT = {}
    HANDLER_DICT_LOCK = threading.Lock()
    STOP_WORLD = False

    def __init__(self, uri_obj):
        # type:(AsyncUri) -> None
        super(AsyncUirHandler, self).__init__(uri_obj)

    @thread.AsyncThread
    def _run_index(self, task_uuid, request):
        callback_uri = self._get_callback_uri(request)
        with self.HANDLER_DICT_LOCK:
            if task_uuid in self.HANDLER_DICT:
                logger.info("ignored duplicated task: {}".format(task_uuid))
                return
            self.HANDLER_DICT[task_uuid] = callback_uri

        headers = {TASK_UUID : task_uuid}
        try:
            content = super(AsyncUirHandler, self)._do_index(request)
            self._check_response(content)
        except Exception:
            content = traceback.format_exc()
            logger.warn('[WARN]: %s]' % content)
            headers[ERROR_CODE] = content

        try:
            json_post(callback_uri, content, headers)
            logger.debug("async http reply[task uuid: %s] to %s: %s" % (task_uuid, callback_uri, content))
        finally:
            with self.HANDLER_DICT_LOCK:
                self.HANDLER_DICT.pop(task_uuid, None)

    def _get_callback_uri(self, req):
        callback_uri = None
        if req.headers.has_key(CALLBACK_URI):
            callback_uri = req.headers[CALLBACK_URI]
        else:
            callback_uri = self.uri_obj.callback_uri

        if not callback_uri:
            raise Exception('Unable to find callback uri either in headers of request or in registered uri object')

        return callback_uri

    @cherrypy.expose
    def index(self):
        if self.STOP_WORLD:
            err = 'kvmagent is stopping'
            logger.warn(err)
            raise cherrypy.HTTPError(400, err)

        if not cherrypy.request.headers.has_key(TASK_UUID):
            err = 'taskUuid missing in request header'
            logger.warn(err)
            raise cherrypy.HTTPError(400, err)

        task_uuid = cherrypy.request.headers[TASK_UUID]
        req = Request.from_cherrypy_request(cherrypy.request)

        filter_body = log.mask_sensitive_field(self.uri_obj.cmd, req.body)
        logger.debug('async http call[task uuid: %s], body: %s' % (task_uuid, filter_body))
        self._run_index(task_uuid, req)

def tool_disable_multipart_preprocessing():
    """A cherrypy Tool extension to disable default multipart processing"""
    cherrypy.request.body.processors.pop('multipart', None)
    cherrypy.request.body.processors.pop('multipart/form-data', None)

class HttpServer(object):
    '''
    classdocs
    '''

    def __init__(self, port=7070, async_callback_uri = None):
        '''
        Constructor
        '''
        self.async_callback_uri = async_callback_uri
        self.async_uri_handlers = {}
        self.sync_uri_handlers = {}
        self.raw_uri_handlers = {}
        self.server = None
        self.server_conf = None
        self.logfile_path = log.get_logfile_path()
        self.port = port
        self.mapper = None

    def register_async_uri(self, uri, func, callback_uri=None, cmd=None):
        # type:(str, function, str, object) -> None
        async_uri_obj = AsyncUri()
        async_uri_obj.callback_uri = callback_uri
        if async_uri_obj.callback_uri is None:
            async_uri_obj.callback_uri = self.async_callback_uri
        async_uri_obj.uri = uri
        async_uri_obj.func = func
        async_uri_obj.cmd = cmd
        async_uri_obj.controller = AsyncUirHandler(async_uri_obj)

        self.async_uri_handlers[uri] = async_uri_obj

    def register_sync_uri(self, uri, func, cmd=None):
        # type:(str, function, object) -> None
        sync_uri = SyncUri()
        sync_uri.func = func
        sync_uri.uri = uri
        sync_uri.cmd = cmd
        sync_uri.controller = SyncUriHandler(sync_uri)
        self.sync_uri_handlers[uri] = sync_uri

    def register_raw_uri(self, uri, func):
        raw_uri = RawUri()
        raw_uri.func = func
        raw_uri.uri = uri
        raw_uri.controller = RawUriHandler(raw_uri)
        self.raw_uri_handlers[uri] = raw_uri

    def register_raw_stream_uri(self, uri, func):
        raw_uri = RawUri()
        raw_uri.func = func
        raw_uri.uri = uri
        raw_uri.controller = RawUriStreamHandler(raw_uri)
        self.raw_uri_handlers[uri] = raw_uri

    def unregister_uri(self, uri):
        del self.async_callback_uri[uri]

    def _add_mapping(self, uri_obj):
        if not self.mapper: self.mapper = cherrypy.dispatch.RoutesDispatcher()
        self.mapper.connect(name=uri_obj.uri, route=uri_obj.uri, controller=uri_obj.controller, action="index")
        if not uri_obj.uri.endswith('/'):
            nuri = uri_obj.uri + '/'
            self.mapper.connect(name=nuri, route=nuri, controller=uri_obj.controller, action="index")
            logger.debug('function[%s] registered uri: %s' % (uri_obj.func.__name__, nuri))
        else:
            nuri = uri_obj.uri.rstrip('/')
            self.mapper.connect(name=nuri, route=nuri, controller=uri_obj.controller, action="index")
            logger.debug('function[%s] registered uri: %s' % (uri_obj.func.__name__, nuri))

    def _build(self):
        for akey in self.async_uri_handlers.keys():
            aval = self.async_uri_handlers[akey]
            self._add_mapping(aval)
        for skey in self.sync_uri_handlers.keys():
            sval = self.sync_uri_handlers[skey]
            self._add_mapping(sval)
        for skey in self.raw_uri_handlers.keys():
            sval = self.raw_uri_handlers[skey]
            self._add_mapping(sval)

        self.server_conf = {'request.dispatch': self.mapper}

        cherrypy.engine.autoreload.unsubscribe()
        site_config = {}
        site_config['server.socket_host'] = '0.0.0.0'
        site_config['server.socket_port'] = self.port
        site_config['server.thread_pool'] = int(os.getenv('POOLSIZE', '10'))

        # remove limitation of request body size, default is 100MB.
        site_config['server.max_request_body_size'] = 0

        # disable cherrypy multipart preprocessing
        cherrypy.tools.disable_multipart = cherrypy.Tool(
                'on_start_resource',
                tool_disable_multipart_preprocessing)
        site_config['tools.disable_multipart.on'] = True
        site_config['engine.timeout_monitor.on'] = False

        cherrypy.config.update(site_config)
        cherrypy.log.error_log.propagate = 0  # NOTE(weiw): disable cherrypy logging

        self.server = cherrypy.tree.mount(root=None, config={'/' : self.server_conf})

        if not self.logfile_path:
            self.logfile_path = '/var/log/zstack/zstack.log'

        cherrypy.log.error_file = ""
        cherrypy.log.access_file = ""
        cherrypy.log.screen = False
        self.server.log.error_file = ''
        self.server.log.access_file = ''
        self.server.log.screen = False
        self.server.log.access_log = logger
        self.server.log.error_log = logger

    def start(self):
        self._build()
        cherrypy.quickstart(self.server)

    @thread.AsyncThread
    def start_in_thread(self):
        self.start()

    @staticmethod
    def query_string_to_object(query_string):
        params = {}
        pairs = query_string.split('&')
        for p in pairs:
            (k, v) = p.split('=')
            params[k] = v
        return params

    def stop(self):
        cherrypy.engine.exit()

def print_curl_command(uri, methmod, headers, body):
    hstr = ""
    for k in headers:
        hstr += "-H '%s:%s' " % (k, headers[k])
    mstr = "-X %s" % methmod
    bstr = "-d '%s'" % body if body != None and body.strip() != "" else ""
    cstr = " ".join(["curl %s" % uri, mstr, hstr, bstr])
    print("\n\033[34mCopy as cURL: %s \033[0m\n" % cstr)

def json_post(uri, body=None, headers={}, method='POST', fail_soon=False, print_curl=False):
    ret = []
    def post(_):
        try:
            pool = urllib3.PoolManager(timeout=120.0, retries=urllib3.util.retry.Retry(15))
            header = {'Content-Type': 'application/json', 'Connection': 'close'}
            content = None
            for k in headers.keys():
                header[k] = headers[k]

            if body is not None:
                assert isinstance(body, types.StringType)
                header['Content-Length'] = str(len(body))
                if print_curl: print_curl_command(uri, method, header, body)
                resp = pool.urlopen(method, uri, headers=header, body=str(body))
                content = resp.data
                resp.close()
            else:
                header['Content-Length'] = '0'
                if print_curl: print_curl_command(uri, method, header, body)
                resp = pool.urlopen(method, uri, headers=header)
                content = resp.data
                resp.close()

            pool.clear()
            ret.append(content)
            return True
        except Exception as e:
            if fail_soon:
                raise e

            logger.warn('[WARN]: %s' % linux.get_exception_stacktrace())
            return False

    if fail_soon:
        post(None)
    else:
        if not linux.wait_callback_success(post, ignore_exception_in_callback=True):
            raise Exception('unable to post to %s, body: %s, see before error' % (uri, body))

    return ret[0]


def json_dump_post(uri, body=None, headers={}, fail_soon=False, print_curl=False):
    content = None
    if body is not None:
        content = jsonobject.dumps(body)
    return json_post(uri, content, headers, fail_soon=fail_soon, print_curl=print_curl)

def json_dump_get(uri, body=None, headers={}, fail_soon=False, print_curl=False):
    content = None
    if body is not None:
        content = jsonobject.dumps(body)
    return json_post(uri, content, headers, 'GET', fail_soon=fail_soon, print_curl=print_curl)

class LimitedSizedReader(cherrypy._cpreqbody.SizedReader):
    maxlinesize = 16 << 20 # 16 MB

    def readline(self, size=None):
        """Read a line from the request body and return it."""
        chunks = []
        total = 0
        while size is None or size > 0:
            chunksize = self.bufsize
            if size is not None and size < self.bufsize:
                chunksize = size
            data = self.read(chunksize)
            if not data:
                break
            pos = data.find(cherrypy._cpcompat.ntob('\n')) + 1
            if pos:
                chunks.append(data[:pos])
                remainder = data[pos:]
                self.buffer += remainder
                self.bytes_read -= len(remainder)
                break
            else:
                chunks.append(data)

            total += len(data)
            if total >= self.maxlinesize:
                break

        return cherrypy._cpcompat.ntob('').join(chunks)

cherrypy._cpreqbody.SizedReader = LimitedSizedReader

class UriBuilder(object):
    def _invalid_uri(self, uri):
        raise Exception('invalid uri[%s]' % uri)

    def _parse(self, uri):
        scheme = uri[0:4]
        if scheme not in ['http', 'https']:
            raise Exception('uri[%s] is not started with scheme[http, https]' % uri)
        self.scheme = scheme

        rest = uri.lstrip(scheme)
        if not rest.startswith('://'):
            self._invalid_uri(uri)

        rest = rest.lstrip('://')
        colon = rest.find(':')
        if colon != -1:
            self.host = rest[0:colon]
            rest = rest.lstrip(self.host).lstrip(':%s' % self.port)
        else:
            self.port = 80
            slash = rest.find('/')
            if slash == -1:
                self.host = rest[0:]
                return
            else:
                self.host = rest[0:slash]
                rest = rest.lstrip(self.host)

        self.paths = [p.strip('/') for p in rest.split('/')]
        self.paths = filter(lambda x: x != '', self.paths)
        print(self.paths)
        self.paths = [] if not self.paths else self.paths


    def __init__(self, uri=None):
        self.scheme = 'http'
        self.host = None
        self.port = 7070
        self.paths = []
        if uri:
            self._parse(uri)


    def add_path(self, p):
        self.paths.append(p)

    def build(self):
        if not self.host:
            raise Exception('host cannot be None')

        self.paths = [p.strip('/') for p in self.paths]
        path = '/'.join(self.paths)
        ret = '%s://%s:%s/%s' % (self.scheme, self.host, self.port, path)
        return ret + '/' if not ret.endswith('/') else ret


def build_url(args):
    builder = UriBuilder()
    builder.scheme = args[0]
    builder.host = args[1]
    builder.port = args[2]
    builder.paths = args[3:]
    return builder.build()

def path_msg(path, msg=None):
    return path if not msg else '%s %s' % (path, msg)
