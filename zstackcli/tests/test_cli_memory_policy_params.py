"""Exercise the real CLI command parser through message serialization/dispatch."""
import ast
import importlib.util
import json
import pathlib
import types

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI_SOURCE = ROOT / 'zstackcli' / 'zstackcli' / 'cli.py'
JSONOBJECT_SOURCE = ROOT / 'zstacklib' / 'zstacklib' / 'utils' / 'jsonobject.py'


class CliError(Exception):
    pass


class OptionalList:
    pass


class NotNoneList:
    pass


class Message:
    FULL_NAME = 'org.zstack.header.memory.APIUpdateMemoryPolicyMsg'

    def __init__(self):
        self.expectedSourceRevisions = {}
        self.expectedGlobalRevision = None
        self.resourceUuid = None
        self.scope = None
        self.policy = None
        self.timeout = 0


class Session:
    def __init__(self):
        self.uuid = None


class Inventory:
    api_names = ['APIUpdateMemoryPolicyMsg']
    APIUpdateMemoryPolicyMsg = Message
    OptionalList = OptionalList
    NotNoneList = NotNoneList
    Session = Session


class RecordingTransport:
    """Capture the production serialized request at the API transport edge."""

    def __init__(self, jsonobject):
        self.jsonobject = jsonobject
        self.calls = []
        self.api_url = 'http://unit-test.invalid/zstack/api'

    def async_call_wait_for_complete(self, msg, **kwargs):
        # Api.async_call_wait_for_complete serializes this exact command shape.
        payload = self.jsonobject.dumps({msg.FULL_NAME: msg})
        self.calls.append(json.loads(payload))
        return 'APIUpdateMemoryPolicyEvent', types.SimpleNamespace(success=True)


@pytest.fixture
def command_harness():
    tree = ast.parse(CLI_SOURCE.read_text())
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == 'do_command')
    method.decorator_list = []

    serializer_spec = importlib.util.spec_from_file_location(
        'zstackcli_test_jsonobject', str(JSONOBJECT_SOURCE))
    serializer = importlib.util.module_from_spec(serializer_spec)
    serializer_spec.loader.exec_module(serializer)

    transport = RecordingTransport(serializer)
    messages = []
    cli = types.SimpleNamespace(
        session_uuid='session-uuid', account_name=None, user_name=None,
        no_session_message=[], cli_cmd=[], cli_cmd_func={}, msg_creator={},
        api=transport, headers={}, write_more=lambda *args: None,
        print_error=lambda message: messages.append(message),
        LOGIN_MESSAGE_NAME='unused-login', LOGIN_BY_USER_NAME='unused-login-user',
        CREATE_ACCOUNT_NAME='unused-create-account', CREATE_USER_NAME='unused-create-user',
        LOGIN_BY_USER_IAM2='unused-login-user-iam2', CREATE_USER_IAM2='unused-create-user-iam2',
        GET_TWO_FACTOR_AUTHENTICATION_SECRET='unused-two-factor',
        POWER_OFF_HOST='unused-poweroff', USER_RESET_PASSWORD_NAME='unused-user-reset',
        ACCOUNT_RESET_PASSWORD_NAME='unused-account-reset',
        IAM2_USER_RESET_PASSWORD_NAME='unused-iam-reset', LOGOUT_MESSAGE_NAME='unused-logout',
        LOGIN_BY_LDAP_MESSAGE_NAME='unused-login-ldap', LOGIN_BY_LDAP_IAM2_NAME='unused-login-ldap-iam2',
        LOGIN_BY_IAM2_PROJECT_NAME='unused-login-project', LOGIN_BY_CAS_MESSAGE_NAME='unused-login-cas')
    globals_for_method = {
        'inventory': Inventory,
        'CliError': CliError,
        'jsonobject': serializer,
        'time': __import__('time'),
        'urllib3': types.SimpleNamespace(
            exceptions=types.SimpleNamespace(MaxRetryError=type('MaxRetryError', (Exception,), {}))),
        'prompt': '>>>',
        'NOT_QUERY_MYSQL_APIS': [],
        'query_param_keys': [],
    }
    module = ast.Module(body=[method], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(CLI_SOURCE), 'exec'), globals_for_method)
    return globals_for_method['do_command'], cli, transport, messages


def _command(revisions, *extra):
    return ['UpdateMemoryPolicy', 'expectedSourceRevisions=' + revisions] + list(extra)


def test_three_level_revisions_are_json_object_at_dispatch(command_harness):
    do_command, cli, transport, _ = command_harness
    revisions = '{"Global:global":0,"Cluster:cluster-uuid":0,"Host:host-uuid":70}'

    do_command(cli, _command(
        revisions, 'resourceUuid=host-uuid', 'scope=Host', 'policy={"ksm":{"enabled":true}}'))

    body = transport.calls[0][Message.FULL_NAME]
    assert body['expectedSourceRevisions'] == {
        'Global:global': 0, 'Cluster:cluster-uuid': 0, 'Host:host-uuid': 70}
    assert isinstance(body['expectedSourceRevisions'], dict)
    assert body['resourceUuid'] == 'host-uuid'
    assert body['scope'] == 'Host'
    assert body['policy'] == '{"ksm":{"enabled":true}}'
    assert cli.session_uuid == 'session-uuid'


def test_signed_java_long_maximum_is_preserved(command_harness):
    do_command, cli, transport, _ = command_harness

    do_command(cli, _command('{"Host:host-uuid":9223372036854775807}'))

    assert transport.calls[0][Message.FULL_NAME]['expectedSourceRevisions'] == {
        'Host:host-uuid': 9223372036854775807}


def test_signed_java_long_minimum_is_preserved(command_harness):
    do_command, cli, transport, _ = command_harness

    do_command(cli, _command('{"Host:host-uuid":-9223372036854775808}'))

    assert transport.calls[0][Message.FULL_NAME]['expectedSourceRevisions'] == {
        'Host:host-uuid': -9223372036854775808}


@pytest.mark.parametrize('value', [
    '{"Global:global":0,"Cluster:cluster-uuid":0,"Host:host-uuid":null}',
    '{"Global:global":0,"Cluster:cluster-uuid":0,"Host:host-uuid":true}',
    '{"Global:global":0,"Cluster:cluster-uuid":0,"Host:host-uuid":1.5}',
    '{"Global:global":0,"Cluster:cluster-uuid":0,"Host:host-uuid":"70"}',
    '{"Host:host-uuid":9223372036854775808}',
    '{"Host:host-uuid":-9223372036854775809}',
    '[]',
    'null',
    '{not-json}',
])
def test_invalid_revision_json_or_values_fail_before_dispatch(command_harness, value):
    do_command, cli, transport, _ = command_harness

    with pytest.raises(CliError, match='expectedSourceRevisions'):
        do_command(cli, _command(value))

    assert transport.calls == []


def test_legacy_revision_and_policy_arguments_keep_existing_wire_shape(command_harness):
    do_command, cli, transport, _ = command_harness

    do_command(cli, ['UpdateMemoryPolicy', 'expectedGlobalRevision=0',
                     'policy={"ksm":{"enabled":false}}'])

    body = transport.calls[0][Message.FULL_NAME]
    assert body['expectedGlobalRevision'] == '0'
    assert body['policy'] == '{"ksm":{"enabled":false}}'
    assert body['expectedSourceRevisions'] == {}
