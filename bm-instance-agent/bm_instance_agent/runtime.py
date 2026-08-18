# -*- coding: utf-8 -*-

import datetime
import json
import logging
import os
import socket
import stat

try:
    import httplib
except ImportError:
    import http.client as httplib

try:
    from oslo_log import log as logging
except ImportError:
    pass

from bm_instance_agent import runtime_artifact


LOG = logging.getLogger(__name__)


class RuntimeProxyError(Exception):

    def __init__(self, status, code, message, retryable, owner, request_id=None,
                 details=None):
        super(RuntimeProxyError, self).__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.owner = owner
        self.request_id = request_id
        self.details = details or {}

    def to_dict(self):
        return {
            'code': self.code,
            'message': self.message,
            'retryable': self.retryable,
            'owner': self.owner,
            'requestId': self.request_id or '',
            'details': self.details,
            'observedAt': datetime.datetime.utcnow().replace(
                microsecond=0).isoformat() + 'Z'
        }


class UnixSocketHttpConnection(httplib.HTTPConnection):

    def __init__(self, socket_path, connect_timeout, read_timeout):
        httplib.HTTPConnection.__init__(
            self, 'localhost', timeout=connect_timeout)
        self.socket_path = socket_path
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.connect_timeout)
        sock.connect(self.socket_path)
        sock.settimeout(self.read_timeout)
        self.sock = sock


class RuntimeManager(object):

    RUNTIME_ROOT = '/var/lib/zstack/baremetalv2/runtime'
    SOCKET_PATH = '/var/lib/zstack/baremetalv2/runtime/runtime.sock'
    MOUNT_FACTS_DIR = '/var/lib/zstack/baremetalv2/runtime/mount-facts.d'
    MAX_REQUEST_BYTES = 4 * 1024 * 1024
    MAX_RESPONSE_BYTES = 4 * 1024 * 1024
    CONNECT_TIMEOUT_SECONDS = 2
    READ_TIMEOUT_SECONDS = 15
    MOUNTINFO_PATH = '/proc/self/mountinfo'

    def __init__(self, socket_path=None, connect_timeout=None,
                 read_timeout=None, require_root_ownership=True,
                 materializer_factory=None):
        self.socket_path = socket_path or self.SOCKET_PATH
        self.connect_timeout = (connect_timeout if connect_timeout is not None
                                else self.CONNECT_TIMEOUT_SECONDS)
        self.read_timeout = (read_timeout if read_timeout is not None
                             else self.READ_TIMEOUT_SECONDS)
        self.require_root_ownership = require_root_ownership
        self.materializer_factory = (materializer_factory
                                     or runtime_artifact.RuntimeArtifactMaterializer)

    def get_capabilities(self):
        return self.request('GET', '/v1/capabilities')

    def prepare_allocation(self, allocation_uuid, payload):
        return self.request(
            'PUT',
            '/v1/allocations/%s/prepare' % allocation_uuid,
            payload)

    def materialize_prepare_payload(self, payload):
        request_id = self._extract_request_id(payload)
        try:
            materializer = self.materializer_factory()
            return materializer.materialize_prepare_payload(
                payload,
                self.get_runtime_mount_facts())
        except runtime_artifact.RuntimeArtifactError as err:
            raise RuntimeProxyError(
                err.status,
                err.code,
                err.message,
                err.retryable,
                err.owner,
                request_id=request_id,
                details=err.details)

    def start_allocation(self, allocation_uuid, payload):
        return self.request(
            'POST',
            '/v1/allocations/%s/start' % allocation_uuid,
            payload)

    def inspect_allocation(self, allocation_uuid):
        return self.request('GET', '/v1/allocations/%s' % allocation_uuid)

    def release_allocation(self, allocation_uuid, payload):
        return self.request(
            'DELETE',
            '/v1/allocations/%s' % allocation_uuid,
            payload)

    def stop_allocation(self, allocation_uuid, payload):
        return self.request(
            'POST',
            '/v1/allocations/%s/stop' % allocation_uuid,
            payload)

    def reconcile(self, payload):
        return self.request('POST', '/v1/reconcile', payload)

    def get_runtime_mount_facts(self):
        return {
            'observedAt': datetime.datetime.utcnow().replace(
                microsecond=0).isoformat() + 'Z',
            'source': 'mountinfo',
            'factDirectory': self.MOUNT_FACTS_DIR,
            'juicefsReadOnlyMounts': self._collect_readonly_juicefs_mounts()
        }

    def request(self, method, path, payload=None):
        request_id = self._extract_request_id(payload)
        body = self._encode_payload(payload, request_id)
        self._validate_socket_path(request_id)

        headers = {
            'Host': 'localhost',
            'Accept': 'application/json'
        }
        if body is not None:
            headers['Content-Type'] = 'application/json'

        connection = UnixSocketHttpConnection(
            self.socket_path,
            self.connect_timeout,
            self.read_timeout)
        response = None
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            response_body = self._read_response_body(response, request_id)
        except RuntimeProxyError:
            raise
        except (socket.error, socket.timeout, IOError) as err:
            raise RuntimeProxyError(
                503,
                'BMR-PROXY-0001',
                'BM2 instance agent cannot connect to local runtime socket',
                True,
                'InstanceAgent',
                request_id=request_id,
                details={'cause': str(err)})
        finally:
            try:
                if response is not None:
                    response.close()
            except Exception:
                pass
            try:
                sock = getattr(connection, 'sock', None)
                if sock is not None:
                    sock.close()
                    connection.sock = None
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass

        if response.status >= 400:
            return response.status, response_body
        return response.status, response_body

    def _encode_payload(self, payload, request_id):
        if payload is None:
            return None
        body = json.dumps(payload, separators=(',', ':'))
        if not isinstance(body, bytes):
            body = body.encode('utf-8')
        if len(body) > self.MAX_REQUEST_BYTES:
            raise RuntimeProxyError(
                413,
                'BMR-REQUEST-0002',
                'request exceeds configured byte limit',
                False,
                'Caller',
                request_id=request_id,
                details={'maxRequestBytes': self.MAX_REQUEST_BYTES})
        return body

    def _validate_socket_path(self, request_id):
        socket_dir = os.path.dirname(self.socket_path)
        self._validate_path_type(socket_dir, request_id, is_dir=True)
        if os.path.exists(self.socket_path):
            self._validate_path_type(self.socket_path, request_id, is_dir=False)
        if self.require_root_ownership:
            self._validate_root_owned_path(socket_dir, request_id)
            if os.path.exists(self.socket_path):
                self._validate_root_owned_path(self.socket_path, request_id)
        if not os.path.exists(self.socket_path):
            raise RuntimeProxyError(
                503,
                'BMR-PROXY-0001',
                'BM2 instance agent cannot connect to local runtime socket',
                True,
                'InstanceAgent',
                request_id=request_id,
                details={'socketPath': self.socket_path})

    def _validate_path_type(self, path, request_id, is_dir):
        try:
            stat_result = os.lstat(path)
        except OSError:
            raise RuntimeProxyError(
                503,
                'BMR-PROXY-0001',
                'local runtime socket path is missing',
                True,
                'InstanceAgent',
                request_id=request_id,
                details={'path': path})
        if is_dir and not stat.S_ISDIR(stat_result.st_mode):
            raise RuntimeProxyError(
                503,
                'BMR-PROXY-0001',
                'local runtime socket directory is invalid',
                True,
                'InstanceAgent',
                request_id=request_id,
                details={'path': path})
        if not is_dir and not stat.S_ISSOCK(stat_result.st_mode):
            raise RuntimeProxyError(
                503,
                'BMR-PROXY-0001',
                'local runtime endpoint is not a unix socket',
                True,
                'InstanceAgent',
                request_id=request_id,
                details={'path': path})

    def _validate_root_owned_path(self, path, request_id):
        try:
            stat_result = os.lstat(path)
        except OSError:
            raise RuntimeProxyError(
                503,
                'BMR-PROXY-0001',
                'local runtime socket path is missing',
                True,
                'InstanceAgent',
                request_id=request_id,
                details={'path': path})
        if stat_result.st_uid != 0:
            raise RuntimeProxyError(
                503,
                'BMR-PROXY-0001',
                'local runtime socket path is not root-owned',
                True,
                'InstanceAgent',
                request_id=request_id,
                details={'path': path})
        mode = stat.S_IMODE(stat_result.st_mode)
        if mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise RuntimeProxyError(
                503,
                'BMR-PROXY-0001',
                'local runtime socket path is group/world-writable',
                True,
                'InstanceAgent',
                request_id=request_id,
                details={'path': path})

    def _read_response_body(self, response, request_id):
        content_length = response.getheader('Content-Length')
        if content_length is not None:
            try:
                expected_size = int(content_length)
            except (TypeError, ValueError):
                raise self._invalid_response_error(
                    request_id,
                    'runtime response content-length is invalid')
            if expected_size > self.MAX_RESPONSE_BYTES:
                raise self._invalid_response_error(
                    request_id,
                    'runtime response exceeds configured byte limit',
                    {'maxResponseBytes': self.MAX_RESPONSE_BYTES})
            raw_body = response.read(expected_size)
        else:
            raw_body = response.read(self.MAX_RESPONSE_BYTES + 1)
            if len(raw_body) > self.MAX_RESPONSE_BYTES:
                raise self._invalid_response_error(
                    request_id,
                    'runtime response exceeds configured byte limit',
                    {'maxResponseBytes': self.MAX_RESPONSE_BYTES})

        if not raw_body:
            raise self._invalid_response_error(
                request_id,
                'runtime response body is empty')

        if isinstance(raw_body, bytes):
            try:
                raw_body = raw_body.decode('utf-8')
            except Exception:
                raise self._invalid_response_error(
                    request_id,
                    'runtime response is not valid utf-8 json')

        try:
            data = json.loads(raw_body)
        except ValueError:
            raise self._invalid_response_error(
                request_id,
                'runtime response is not valid json')

        if not isinstance(data, dict):
            raise self._invalid_response_error(
                request_id,
                'runtime response must be a json object')
        return data

    def _invalid_response_error(self, request_id, message, details=None):
        return RuntimeProxyError(
            502,
            'BMR-PROXY-0002',
            message,
            True,
            'RuntimeAgent',
            request_id=request_id,
            details=details or {})

    @staticmethod
    def _extract_request_id(payload):
        if isinstance(payload, dict):
            return payload.get('requestId')
        return None

    def _collect_readonly_juicefs_mounts(self):
        mounts = []
        seen = set()
        try:
            with open(self.MOUNTINFO_PATH, 'r') as stream:
                for raw_line in stream:
                    mount = self._parse_mountinfo_line(raw_line)
                    if mount is None or not mount['readOnly']:
                        continue
                    if not self._is_juicefs_mount(mount):
                        continue
                    mount_key = (
                        mount['mountPoint'],
                        mount['mountSource'],
                        mount['root'])
                    if mount_key in seen:
                        continue
                    seen.add(mount_key)
                    mounts.append({
                        'mountId': mount['mountId'],
                        'mountPoint': mount['mountPoint'],
                        'root': mount['root'],
                        'fileSystemType': mount['fileSystemType'],
                        'mountSource': mount['mountSource'],
                        'readOnly': True
                    })
        except IOError:
            return []
        return mounts

    def _parse_mountinfo_line(self, line):
        line = line.strip()
        if not line:
            return None

        if ' - ' not in line:
            return None
        left, right = line.split(' - ', 1)
        left_fields = left.split()
        right_fields = right.split()
        if len(left_fields) < 6 or len(right_fields) < 3:
            return None

        mount_options = left_fields[5].split(',')
        return {
            'mountId': left_fields[0],
            'root': self._decode_mountinfo_path(left_fields[3]),
            'mountPoint': self._decode_mountinfo_path(left_fields[4]),
            'mountOptions': mount_options,
            'fileSystemType': right_fields[0],
            'mountSource': self._decode_mountinfo_path(right_fields[1]),
            'readOnly': 'ro' in mount_options
        }

    @staticmethod
    def _decode_mountinfo_path(value):
        return (value
                .replace('\\040', ' ')
                .replace('\\011', '\t')
                .replace('\\012', '\n')
                .replace('\\134', '\\'))

    @staticmethod
    def _is_juicefs_mount(mount):
        file_system = mount.get('fileSystemType') or ''
        return file_system in ('fuse.juicefs', 'juicefs')


__all__ = [
    'RuntimeManager',
    'RuntimeProxyError',
    'UnixSocketHttpConnection'
]
