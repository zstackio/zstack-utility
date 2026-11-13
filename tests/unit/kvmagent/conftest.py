# -*- coding: utf-8 -*-
"""
kvmagent unit test conftest — protect stdlib globals from cross-test leaks.

Several tests monkey-patch ``os`` / ``uuid`` attributes directly (without
``unittest.mock.patch``).  This autouse fixture saves the originals before
each test and unconditionally restores them afterwards, preventing
contamination of later tests.

Additionally, some tests assign ``linux.read_file`` to a MagicMock with a
finite ``side_effect`` list, which exhausts across test boundaries.  We
save and restore the attribute on the shared ``linux`` mock as well.
"""
import os
import os.path
import sys
import uuid
from contextlib import ExitStack
from unittest.mock import patch

import pytest


@pytest.fixture
def configured_volume_extensions():
    from kvmagent.plugins.volume_crypto_plugin import VolumeCryptoPlugin
    from kvmagent.volume import disk_xml, driver_registry, imagestore_commands

    with ExitStack() as stack:
        for registry in (disk_xml._disk_xml_extensions, driver_registry._driver_registrations,
                         imagestore_commands._command_extensions):
            stack.enter_context(patch.dict(registry, {}, clear=True))
        VolumeCryptoPlugin().configure()
        yield


@pytest.fixture
def plain_volume_metadata(monkeypatch):
    from kvmagent.crypto import vm_xml

    monkeypatch.setattr(vm_xml, '_file_chain', lambda path: iter([(path, 'qcow2', False)]))


# ---------------------------------------------------------------------------
# Functions that tests are known to monkey-patch on the real ``os`` module.
# ---------------------------------------------------------------------------
_OS_ATTRS = {
    "remove": os.remove,
    "makedirs": os.makedirs,
}
_OS_PATH_ATTRS = {
    "exists": os.path.exists,
    "getsize": os.path.getsize,
    "isdir": os.path.isdir,
    "realpath": os.path.realpath,
    "basename": os.path.basename,
}
_UUID_ATTRS = {
    "UUID": uuid.UUID,
}

# The shared ``linux`` mock from the root conftest (sys.modules stub).
_mock_linux = sys.modules.get('zstacklib.utils.linux')


@pytest.fixture(autouse=True)
def _restore_stdlib_globals():
    """Save & restore stdlib globals that tests may monkey-patch."""
    # Snapshot mutable mock attributes before the test runs.
    _linux_read_file = getattr(_mock_linux, 'read_file', None) if _mock_linux else None
    _linux_read_file_strip = getattr(_mock_linux, 'read_file_strip', None) if _mock_linux else None

    yield

    # Restore os functions
    for name, orig in _OS_ATTRS.items():
        if getattr(os, name) is not orig:
            setattr(os, name, orig)
    # Restore os.path functions
    for name, orig in _OS_PATH_ATTRS.items():
        if getattr(os.path, name) is not orig:
            setattr(os.path, name, orig)
    # Restore uuid.UUID
    for name, orig in _UUID_ATTRS.items():
        if getattr(uuid, name) is not orig:
            setattr(uuid, name, orig)
    # Restore linux mock attributes that tests may replace with finite
    # side_effect lists (e.g. linux.read_file = MagicMock(side_effect=[...]))
    if _mock_linux is not None:
        if _linux_read_file is not None:
            _mock_linux.read_file = _linux_read_file
        if _linux_read_file_strip is not None:
            _mock_linux.read_file_strip = _linux_read_file_strip
