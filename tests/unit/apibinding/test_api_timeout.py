# -*- coding: utf-8 -*-
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


EVENT = 'org.zstack.header.volume.APICreateDataVolumeFromVolumeSnapshotEvent'
RESULT_UUID = 'legacy-result-uuid'


class CreateDataVolumeFromVolumeSnapshotAction:
    FULL_NAME = 'org.zstack.header.volume.APICreateDataVolumeFromVolumeSnapshotMsg'

    def __init__(self, timeout=None):
        self.timeout = timeout


def inventory_types():
    inventory = types.ModuleType('apibinding.inventory')
    for name in ('NotNoneField', 'NotNoneList', 'NotNoneMap',
                 'OptionalList', 'OptionalMap', 'Session'):
        setattr(inventory, name, type(name, (object,), {}))
    return inventory


@pytest.fixture
def api(monkeypatch):
    import apibinding

    inventory = inventory_types()
    monkeypatch.setitem(sys.modules, 'apibinding.inventory', inventory)
    monkeypatch.setattr(apibinding, 'inventory', inventory, raising=False)
    source = Path(__file__).resolve().parents[3] / 'apibinding/apibinding/api.py'
    spec = importlib.util.spec_from_file_location('apibinding._timeout_test_api', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.log, 'mask_sensitive_field', lambda obj, text: text, raising=False)
    return module


def processing(**fields):
    return dict(state='Processing', uuid=RESULT_UUID, **fields)


def done(success=True):
    event = {'success': success, 'inventory': {'uuid': 'created-volume'}}
    if not success:
        event['error'] = {'code': 'TEST_ERROR', 'description': 'Create failed', 'details': 'volume unavailable'}
    return {'state': 'Done', 'uuid': RESULT_UUID, 'result': json.dumps({EVENT: event})}


def wire(monkeypatch, api, initial, results=()):
    calls = {'post': [], 'get': [], 'sleep': []}
    responses = iter(results)

    def post(url, cmd, **kwargs):
        calls['post'].append((url, api.jsonobject.dumps(cmd), kwargs))
        return json.dumps(initial)

    def get(url, **kwargs):
        calls['get'].append((url, kwargs))
        return json.dumps(next(responses, processing()))

    monkeypatch.setattr(api.http, 'json_dump_post', post, raising=False)
    monkeypatch.setattr(api.http, 'json_dump_get', get, raising=False)
    monkeypatch.setattr(api.time, 'sleep', calls['sleep'].append)
    return calls


def test_server_timeout_allows_completion_after_old_default(api, monkeypatch):
    action = CreateDataVolumeFromVolumeSnapshotAction()
    client = api.Api(result_path='/zstack/api/result/', curl=True)
    calls = wire(monkeypatch, api, processing(apiTimeout=10800000),
                 [processing(), processing(), done()])
    name, event = client.async_call_wait_for_complete(action, interval=900000,
                                                     fail_soon=True, headers={'test-header': 'kept'})
    assert name == EVENT
    assert event.success and event.inventory.uuid == 'created-volume'
    assert calls['sleep'] == [900.0] * 3
    assert calls['get'] == [(client.api_result_url + RESULT_UUID, {'print_curl': True})] * 3
    assert len(calls['post']) == 1
    assert calls['post'][0][2] == {'fail_soon': True, 'print_curl': True, 'headers': {'test-header': 'kept'}}
    assert 'timeout' not in json.loads(calls['post'][0][1])[action.FULL_NAME]
    assert action.timeout is None


@pytest.mark.parametrize('client_timeout,server_timeout', [(900000, 10800000), (2700000, 900000), (-1, 10800000)])
def test_explicit_client_timeout_has_priority(api, monkeypatch, client_timeout, server_timeout):
    client = api.Api(result_path='/zstack/api/result/')
    calls = wire(monkeypatch, api, processing(apiTimeout=server_timeout))
    action = CreateDataVolumeFromVolumeSnapshotAction(client_timeout)
    with pytest.raises(api.ApiError) as error:
        client.async_call_wait_for_complete(action, interval=900000)
    assert 'timeout after %dms' % client_timeout in str(error.value)
    assert client.api_result_url + RESULT_UUID in str(error.value)
    assert len(calls['get']) == max(0, client_timeout // 900000)
    assert len(calls['post']) == 1
    assert action.timeout == client_timeout


@pytest.mark.parametrize('fields', [{}, {'apiTimeout': None}, {'apiTimeout': 0}, {'apiTimeout': -1},
                                   {'apiTimeout': '10800000'}, {'apiTimeout': True},
                                   {'apiTimeout': False}, {'apiTimeout': 10800000.0}])
@pytest.mark.parametrize('client_timeout', [None, 0])
def test_old_or_invalid_server_timeout_uses_legacy_default(api, monkeypatch, fields, client_timeout):
    calls = wire(monkeypatch, api, processing(**fields))
    with pytest.raises(api.ApiError, match='timeout after 1800000ms'):
        api.Api().async_call_wait_for_complete(CreateDataVolumeFromVolumeSnapshotAction(client_timeout), interval=900000)
    assert calls['sleep'] == [900.0, 900.0]


@pytest.mark.parametrize('immediate', [True, False])
@pytest.mark.parametrize('success,exception_on_error', [(True, True), (False, True), (False, False)])
def test_completion_and_error_semantics(api, monkeypatch, immediate, success, exception_on_error):
    response = done(success)
    calls = wire(monkeypatch, api, response if immediate else processing(apiTimeout=10800000), [response])
    action = CreateDataVolumeFromVolumeSnapshotAction()
    if not success and exception_on_error:
        with pytest.raises(api.ApiError) as error:
            api.Api().async_call_wait_for_complete(action, exception_on_error=exception_on_error)
        assert str(error.value) == ('API call[%s] failed because [code: TEST_ERROR, description: Create failed, '
                                    'details: volume unavailable]' % EVENT)
    else:
        name, event = api.Api().async_call_wait_for_complete(action, exception_on_error=exception_on_error)
        assert name == EVENT
        assert event.success is success
        assert event.inventory.uuid == 'created-volume'
    assert len(calls['post']) == 1
    assert len(calls['get']) == (0 if immediate else 1)
    assert calls['sleep'] == ([] if immediate else [0.5])


def test_zero_client_falls_back_without_mutating_or_caching_server_timeout(api, monkeypatch):
    client = api.Api()
    action = CreateDataVolumeFromVolumeSnapshotAction(0)
    first = wire(monkeypatch, api, processing(apiTimeout=10800000), [processing(), processing(), done()])
    assert client.async_call_wait_for_complete(action, interval=900000)[1].success
    assert action.timeout == 0
    assert len(first['post']) == 1
    second = wire(monkeypatch, api, processing(), [processing(), processing(), done()])
    with pytest.raises(api.ApiError, match='timeout after 1800000ms'):
        client.async_call_wait_for_complete(action, interval=900000)
    assert len(second['post']) == 1
    assert len(second['get']) == 2
    assert action.timeout == 0


def test_completion_at_exact_deadline_keeps_timeout_behavior(api, monkeypatch):
    wire(monkeypatch, api, processing(apiTimeout=900000), [done()])
    with pytest.raises(api.ApiError, match=r'timeout after 900000ms, state\[Done\]'):
        api.Api().async_call_wait_for_complete(CreateDataVolumeFromVolumeSnapshotAction(900000), interval=900000)
