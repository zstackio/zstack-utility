import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def request_log():
    path = Path(__file__).resolve().parents[3] / 'zstacklib/zstacklib/utils/log.py'
    spec = importlib.util.spec_from_file_location('zstacklib.utils.request_log_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('body', [
    {'SENSITIVE_FIELDS': ['password'], 'password': 'synthetic-credential'},
    {'SENSITIVE_FIELDS': ['vmInfo.password'], 'vmInfo': {'password': 'synthetic-credential'}},
])
def test_exception_does_not_log_a_request_with_only_declared_sensitive_fields(request_log, body):
    request = {'body': json.dumps(body)}
    diagnostic = request_log.format_exception_for_log(ValueError('synthetic-credential'), (request,), {}, 'body')

    assert request_log.SENSITIVE_REQUEST_OMITTED in diagnostic
    assert 'synthetic-credential' not in diagnostic
    assert request_log.mask_sensitive_field(None, request['body']) == request_log.SENSITIVE_REQUEST_OMITTED


def test_request_log_can_still_mask_fields_from_a_trusted_command(request_log):
    class Command(object):
        SENSITIVE_FIELDS = ["obj['vmInfo']['password']"]

    body = json.dumps({'SENSITIVE_FIELDS': ['vmInfo.password'], 'vmInfo': {'password': 'synthetic-credential'},
                       'installPath': '/disk'})
    assert json.loads(request_log.mask_sensitive_field(Command(), body)) == {
        'vmInfo': {'password': '*****'}, 'installPath': '/disk',
    }
