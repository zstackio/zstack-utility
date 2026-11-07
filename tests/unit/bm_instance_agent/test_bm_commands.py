# -*- coding: utf-8 -*-
from __future__ import annotations
"""
Unit tests for bm-instance-agent data models and exception handling.

Tests for BmInstanceObj JSON deserialization, Base.body() extraction,
VolumeObj construction, and exception message formatting.
"""
import sys
from unittest.mock import MagicMock

import pytest

# bm-instance-agent uses oslo_log (NOT zstacklib.utils.log) — mock before import
if 'oslo_log' not in sys.modules:
    sys.modules['oslo_log'] = MagicMock()
if 'oslo_config' not in sys.modules:
    sys.modules['oslo_config'] = MagicMock()

# Mock bm_instance_agent.common.utils (has OS-level deps like get_interfaces)
if 'bm_instance_agent.common.utils' not in sys.modules:
    sys.modules['bm_instance_agent.common.utils'] = MagicMock()

from bm_instance_agent import exception
from bm_instance_agent.objects import Base, BmInstanceObj, VolumeObj


@pytest.mark.bm_instance
class TestBmInstanceObjects:
    """Test suite for bm-instance-agent data object deserialization."""

    def test_base_body_extracts_dict(self):
        """Test Base.body() extracts body dict from request."""
        req = {'body': {'uuid': 'test-uuid', 'name': 'instance-1'}}
        result = Base.body(req)

        assert result == {'uuid': 'test-uuid', 'name': 'instance-1'}

    def test_base_body_parses_json_string(self):
        """Test Base.body() parses JSON string body."""
        import json
        body_data = {'uuid': 'test-uuid'}
        req = {'body': json.dumps(body_data)}
        result = Base.body(req)

        assert result == body_data

    def test_base_body_empty_default(self):
        """Test Base.body() returns empty dict when no body present."""
        req = {}
        result = Base.body(req)

        assert result == {}

    def test_volume_obj_from_json(self):
        """Test VolumeObj.from_json() constructs volume with allowed keys."""
        volume_data = {
            'uuid': 'vol-12345',
            'device_id': 2,
            'iscsi_path': '/dev/sdb',
            'name': 'data-volume-1',
        }
        vol = VolumeObj.from_json(volume_data)

        assert vol.uuid == 'vol-12345'
        assert vol.device_id == 2
        assert vol.iscsi_path == '/dev/sdb'
        assert vol.name == 'data-volume-1'

    def test_volume_obj_ignores_unknown_keys(self):
        """Test VolumeObj.from_json() ignores keys not in allowed_keys."""
        volume_data = {
            'uuid': 'vol-99999',
            'unknown_field': 'should-be-ignored',
            'primaryStorageType': 'NFS',
        }
        vol = VolumeObj.from_json(volume_data)

        assert vol.uuid == 'vol-99999'
        assert not hasattr(vol, 'unknown_field') or vol.unknown_field is None
        assert not hasattr(vol, 'primaryStorageType') or vol.primaryStorageType is None


@pytest.mark.bm_instance
class TestBmInstanceExceptions:
    """Test suite for bm-instance-agent exception formatting."""

    def test_uuid_conflict_message(self):
        """Test BmInstanceUuidConflict formats error with instance UUIDs."""
        exc = exception.BmInstanceUuidConflict(
            req_instance_uuid='req-111',
            exist_instance_uuid='exist-222',
        )

        assert 'req-111' in str(exc)
        assert 'exist-222' in str(exc)
        assert 'not equal' in str(exc)

    def test_reboot_failed_message(self):
        """Test BmInstanceRebootFailed formats error with uuid and stderr."""
        exc = exception.BmInstanceRebootFailed(
            bm_uuid='bm-333',
            stderr='reboot: command failed',
        )

        assert 'bm-333' in str(exc)
        assert 'reboot: command failed' in str(exc)

    def test_stop_failed_message(self):
        """Test BmInstanceStopFailed formats with uuid and stderr."""
        exc = exception.BmInstanceStopFailed(
            bm_uuid='bm-444',
            stderr='permission denied',
        )

        assert 'bm-444' in str(exc)
        assert 'permission denied' in str(exc)

    def test_network_interface_not_found(self):
        """Test NewtorkInterfaceNotFound formats with mac and vlan_id."""
        exc = exception.NewtorkInterfaceNotFound(
            mac='aa:bb:cc:dd:ee:ff',
            vlan_id='100',
        )

        assert 'aa:bb:cc:dd:ee:ff' in str(exc)
        assert '100' in str(exc)

    def test_exception_inheritance_chain(self):
        """Test exception classes inherit from BmV2InstanceAgentException."""
        assert issubclass(exception.Conflict, exception.BmV2InstanceAgentException)
        assert issubclass(exception.BmInstanceUuidConflict, exception.Conflict)
        assert issubclass(exception.BmInstanceRebootFailed, exception.BmV2InstanceAgentException)
        assert issubclass(exception.NewtorkInterfaceNotFound, exception.BmV2InstanceAgentException)

    def test_base_exception_default_message(self):
        """Test BmV2InstanceAgentException uses class name when no msg given."""
        exc = exception.BmV2InstanceAgentException()

        assert str(exc) == 'BmV2InstanceAgentException'
        assert exc.msg == 'BmV2InstanceAgentException'

    def test_conflict_has_code(self):
        """Test Conflict exception has HTTP status code 409."""
        assert exception.Conflict.code == 409
