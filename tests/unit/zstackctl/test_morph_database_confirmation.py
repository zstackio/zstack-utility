import argparse
import ast
import sys
import warnings
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def command():
    path = Path(__file__).resolve().parents[3] / 'zstackctl/zstackctl/ctl.py'
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', SyntaxWarning)
        tree = ast.parse(path.read_text())
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == 'StartExtraServicesCmd')
    error = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == 'error')
    service = Mock()
    service.zsha2_utils = Mock()
    namespace = dict(Command=object, MorphService=Mock(return_value=service),
                     IamService=Mock(), LicenseServerService=Mock(), ctl=Mock(), sys=sys,
                     colored=lambda message, *args: message)
    exec(compile(ast.Module(body=[error, node], type_ignores=[]), str(path), 'exec'), namespace)
    instance = namespace['StartExtraServicesCmd']()
    parser = argparse.ArgumentParser()
    instance.install_argparse_arguments(parser)
    return instance, parser, namespace, service


def test_confirmation_is_passed_before_morph_initialization(command):
    instance, parser, namespace, service = command
    service.init.side_effect = lambda: assert_confirmation(service)
    instance.run(parser.parse_args(['--name', 'morph', '--init', '--confirm-morph-db-vip']))
    service.init.assert_called_once()
    service.start.assert_called_once_with(True)


def assert_confirmation(service):
    assert service.allow_custom_database_endpoint is True


@pytest.mark.parametrize('arguments', [
    ['--name', 'iam', '--init', '--confirm-morph-db-vip'],
    ['--name', 'morph', '--confirm-morph-db-vip'],
])
def test_confirmation_requires_explicit_morph_initialization(command, arguments, capsys):
    instance, parser, namespace, service = command
    with pytest.raises(SystemExit) as exc:
        instance.run(parser.parse_args(arguments))
    assert exc.value.code == 1
    assert '--name morph --init' in capsys.readouterr().err
    namespace['MorphService'].assert_not_called()
    namespace['IamService'].assert_not_called()


def test_confirmation_rejects_single_node_before_initialization(command, capsys):
    instance, parser, namespace, service = command
    service.zsha2_utils = None
    with pytest.raises(SystemExit) as exc:
        instance.run(parser.parse_args(['--name', 'morph', '--init', '--confirm-morph-db-vip']))
    assert exc.value.code == 1
    assert 'HA' in capsys.readouterr().err
    service.init.assert_not_called()


def test_initialization_failure_exits_before_starting(command, capsys):
    instance, parser, namespace, service = command
    service.init.side_effect = RuntimeError('preparation failed')
    with pytest.raises(SystemExit) as exc:
        instance.run(parser.parse_args(['--name', 'morph', '--init']))
    assert exc.value.code == 1
    assert "Failed to start service 'morph': preparation failed" in capsys.readouterr().err
    service.start.assert_not_called()
    service.status.assert_not_called()
