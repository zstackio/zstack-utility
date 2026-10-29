# -*- coding: utf-8 -*-
"""
conftest.py - Pre-import mocks for ha_plugin tests under Python 3.12+.

The ha_plugin import chain pulls in kvmagent -> zstacklib -> imp (removed in 3.12),
plus C-extension libs (rados, rbd, libvirt). We mock them all, but provide a real
VmStruct so XML-based bridge detection tests exercise actual parsing logic.
"""
import sys
import types
import json
import threading
import time
import traceback
from unittest.mock import MagicMock
from xml.etree import ElementTree as etree


# ---- Real VmStruct (copied from zstacklib/utils/linux.py) -------------------
class _VmStruct(object):
    def __init__(self):
        super(_VmStruct, self).__init__()
        self.pid = ""
        self.xml = ""
        self.root_volume = ""
        self.uuid = ""
        self.volumes = []
        self.bridges = []

    def load_from_xml(self, xml):
        def load_interface_source(element):
            for e in element:
                if e.tag == "source":
                    if "bridge" in e.attrib:
                        self.bridges.append(e.attrib["bridge"])

        def load_disk_source(element):
            is_root_vol = False
            path = None
            for e in element:
                if e.tag == "boot":
                    is_root_vol = True
                elif e.tag == "source":
                    if "file" in e.attrib:
                        path = e.attrib["file"]
                    elif "dev" in e.attrib:
                        path = e.attrib["dev"]
                    if path and path.startswith("/dev/"):
                        self.volumes.append(path)
            if is_root_vol:
                self.root_volume = path

        self.xml = xml
        root = etree.fromstring(xml)
        for e1 in root:
            if e1.tag == "domain":
                for e2 in e1:
                    if e2.tag == "devices":
                        for e3 in e2:
                            if e3.tag == "disk":
                                load_disk_source(e3)
                            if e3.tag == "interface":
                                load_interface_source(e3)
                        return


# ---- Mock modules before any kvmagent import ---------------------------------

# imp (removed in Python 3.12)
try:
    import imp  # noqa: F401
except ImportError:
    sys.modules['imp'] = MagicMock()

# C-extension libs
for _mod in ['rados', 'rbd', 'libvirt']:
    sys.modules[_mod] = MagicMock()

# The legacy HA module imports a VM helper outside the Ceph setup path.
sys.modules['kvmagent.plugins.vm_plugin'] = MagicMock()

# zstacklib.utils.log - needs a real get_logger returning a mock logger
_mock_log = types.ModuleType('zstacklib.utils.log')
_mock_log.get_logger = lambda name: MagicMock()
_mock_log.sensitive_fields = lambda *fields: (lambda cls: cls)
sys.modules['log'] = _mock_log
sys.modules['zstacklib.utils.log'] = _mock_log

# zstacklib.utils.bash
_mock_bash = types.ModuleType('zstacklib.utils.bash')
_mock_bash.bash_roe = lambda *a, **kw: (0, '', '')
_mock_bash.bash_ro = lambda *a, **kw: (0, '')
_mock_bash.bash_r = lambda *a, **kw: 0
_mock_bash.in_bash = lambda fn: fn  # pass-through decorator
sys.modules['zstacklib.utils.bash'] = _mock_bash

# zstacklib.utils.linux - mock everything but provide real VmStruct
_mock_linux = MagicMock()
_mock_linux.VmStruct = _VmStruct
_mock_linux.monotime = time.monotonic
sys.modules['zstacklib.utils.linux'] = _mock_linux

# All other zstacklib.utils modules
_SIMPLE_MOCKS = [
    'zstacklib.utils.compat',
    'zstacklib.utils.shell',
    'zstacklib.utils.lock',
    'zstacklib.utils.daemon',
    'zstacklib.utils.filedb',
    'zstacklib.utils.salt',
    'zstacklib.utils.ovs',
    'zstacklib.utils.qemu',
    'zstacklib.utils.qemu_img',
    'zstacklib.utils.sizeunit',
    'zstacklib.utils.thread',
    'zstacklib.utils.qga',
    'zstacklib.utils.http',
    'zstacklib.utils.jsonobject',
    'zstacklib.utils.xmlobject',
    'zstacklib.utils.plugin',
    'zstacklib.utils.ip',
    'zstacklib.utils.iproute',
    'zstacklib.utils.lvm',
    'zstacklib.utils.ceph',
    'zstacklib.utils.sanlock',
    'zstacklib.utils.iscsi',
    'zstacklib.utils.ipmitool',
    'zstacklib.utils.ipUtils',
    'zstacklib.utils.version',
]
for _mod_name in _SIMPLE_MOCKS:
    sys.modules[_mod_name] = MagicMock()

# zstacklib top-level — use real module objects so `from X.Y import Z` works
_mock_zstacklib = types.ModuleType('zstacklib')
_mock_zstacklib_utils = types.ModuleType('zstacklib.utils')
_mock_zstacklib.utils = _mock_zstacklib_utils
sys.modules['zstacklib'] = _mock_zstacklib
sys.modules['zstacklib.utils'] = _mock_zstacklib_utils

# Wire sub-modules onto the utils namespace so `from zstacklib.utils.X import Y` works
for _mod_name in _SIMPLE_MOCKS:
    _short = _mod_name.rsplit('.', 1)[-1]
    setattr(_mock_zstacklib_utils, _short, sys.modules[_mod_name])

# Additional zstacklib.utils sub-modules referenced by ha_plugin
_EXTRA_MOCKS = [
    'zstacklib.utils.ovn',
    'zstacklib.utils.misc',
    'zstacklib.utils.report',
    'zstacklib.utils.secret',
]
for _mod_name in _EXTRA_MOCKS:
    _m = MagicMock()
    sys.modules[_mod_name] = _m
    setattr(_mock_zstacklib_utils, _mod_name.rsplit('.', 1)[-1], _m)

# Wire the special modules
setattr(_mock_zstacklib_utils, 'log', _mock_log)
setattr(_mock_zstacklib_utils, 'bash', _mock_bash)
setattr(_mock_zstacklib_utils, 'linux', _mock_linux)

# Provide the small amount of real threading used by fencer setup tests.
_mock_thread = sys.modules['zstacklib.utils.thread']
_mock_thread.started_threads = []
_mock_thread.worker_errors = []


class _AsyncThread(object):
    def __init__(self, func):
        self.func = func

    def __get__(self, obj, owner=None):
        return self.__class__(self.func.__get__(obj, owner))

    def __call__(self, *args, **kwargs):
        def safe_run():
            try:
                self.func(*args, **kwargs)
            except Exception as error:
                _mock_thread.worker_errors.append(
                    (self.func.__name__, error, traceback.format_exc()))

        worker = threading.Thread(target=safe_run)
        worker.daemon = True
        _mock_thread.started_threads.append(worker)
        worker.start()
        return worker


_mock_thread.AsyncThread = _AsyncThread

# JSON and HTTP helpers used by handler-level tests.
_mock_http = sys.modules['zstacklib.utils.http']
_mock_http.REQUEST_BODY = 'body'

_mock_jsonobject = sys.modules['zstacklib.utils.jsonobject']


class _JsonObject(object):
    def __getattr__(self, _name):
        return None


def _to_json_object(value):
    if isinstance(value, dict):
        obj = _JsonObject()
        for key, item in value.items():
            setattr(obj, key, _to_json_object(item))
        return obj
    if isinstance(value, list):
        return [_to_json_object(item) for item in value]
    return value


def _json_default(value):
    return value.__dict__


_mock_jsonobject.loads = lambda value: _to_json_object(json.loads(value))
_mock_jsonobject.dumps = lambda value: json.dumps(value, default=_json_default)

# kvmagent package itself. Keep decorators transparent so handler behavior is
# directly testable; unexpected exceptions should fail the test.
_mock_kvmagent_mod = types.ModuleType('kvmagent.kvmagent')
_mock_kvmagent_mod.AgentCommand = object
_mock_kvmagent_mod.KvmAgent = object
_mock_kvmagent_mod.replyerror = lambda func: func
_mock_kvmagent_mod.ha_cleanup_handlers = []
_mock_kvmagent_mod.HOST_UUID = 'hostUuid'
_mock_kvmagent_mod.SEND_COMMAND_URL = 'sendCommandUrl'
_mock_kvmagent_mod.get_http_server = lambda: MagicMock()
sys.modules['kvmagent.kvmagent'] = _mock_kvmagent_mod
