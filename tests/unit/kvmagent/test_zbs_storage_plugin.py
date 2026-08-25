import json
import shlex

import pytest

from kvmagent.plugins import zbs_storage_plugin


def test_query_allocated_extents_parses_existing_extents(monkeypatch):
    commands = []
    response = {
        'error': None,
        'result': [
            {'offset': 8388608, 'length': 65536, 'exists': 'true'},
            {'offset': 536870912, 'length': 131072, 'exists': True},
            {'offset': 900000000, 'length': 65536, 'exists': 'false'},
        ],
    }
    monkeypatch.setattr(zbs_storage_plugin.linux, 'shellquote', shlex.quote)
    monkeypatch.setattr(
        zbs_storage_plugin.shell,
        'call',
        lambda command: commands.append(command) or json.dumps(response),
    )

    result = zbs_storage_plugin.query_allocated_extents('lpool1/volume with space')

    assert result == {8388608: 65536, 536870912: 131072}
    assert commands == ["zbs query diff --path 'lpool1/volume with space' --format json"]


def test_query_allocated_extents_rejects_business_error(monkeypatch):
    monkeypatch.setattr(zbs_storage_plugin.linux, 'shellquote', shlex.quote)
    monkeypatch.setattr(
        zbs_storage_plugin.shell,
        'call',
        lambda _command: '{"error":{"code":-1,"message":"file is not a regular volume"},"result":null}',
    )

    with pytest.raises(RuntimeError, match='file is not a regular volume'):
        zbs_storage_plugin.query_allocated_extents('lpool1/clone-root')


def test_query_allocated_extents_rejects_invalid_result(monkeypatch):
    monkeypatch.setattr(zbs_storage_plugin.linux, 'shellquote', shlex.quote)
    monkeypatch.setattr(
        zbs_storage_plugin.shell,
        'call',
        lambda _command: '{"error":null,"result":null}',
    )

    with pytest.raises(ValueError, match='result must be a list'):
        zbs_storage_plugin.query_allocated_extents('lpool1/volume')
