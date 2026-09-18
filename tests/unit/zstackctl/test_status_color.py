# -*- coding: utf-8 -*-
import ast
import importlib.util
import os
import sys
import zipimport
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
CTL_PATH = REPO_ROOT / 'zstackctl' / 'zstackctl' / 'ctl.py'
TERMCOLOR_WHEEL = REPO_ROOT / 'zstackbuild' / 'pypi_source' / 'pypi' / 'termcolor-2.5.0-py3-none-any.whl'


def _ctl_module():
    return ast.parse(CTL_PATH.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def _vendored_colored():
    spec = zipimport.zipimporter(str(TERMCOLOR_WHEEL)).find_spec('termcolor')
    module = importlib.util.module_from_spec(spec)
    sys.modules['termcolor'] = module
    spec.loader.exec_module(module)
    return module.colored


def _load_colorize_output():
    for node in _ctl_module().body:
        if isinstance(node, ast.FunctionDef) and node.name == 'colorize_output':
            module = ast.Module(body=[node], type_ignores=[])
            namespace = {'os': os, 'colored': _vendored_colored()}
            exec(compile(ast.fix_missing_locations(module), str(CTL_PATH), 'exec'), namespace)
            return namespace['colorize_output']

    raise AssertionError('colorize_output not found')


def _load_status_commands(shell_no_pipe):
    helper_names = {'enable_status_color', 'build_remote_status_command', 'colorize_output'}
    body = [
        node for node in _ctl_module().body
        if (isinstance(node, ast.FunctionDef) and node.name in helper_names)
        or (isinstance(node, ast.ClassDef) and node.name in {'ShowStatusCmd', 'UiStatusCmd'})
    ]
    module = ast.Module(body=body, type_ignores=[])
    namespace = {
        'os': os,
        'colored': _vendored_colored(),
        'Command': object,
        'ctl': SimpleNamespace(register_command=lambda command: None),
        'shell_no_pipe': shell_no_pipe,
    }
    exec(compile(ast.fix_missing_locations(module), str(CTL_PATH), 'exec'), namespace)
    return namespace


def _class_function_calls(class_name, function_name):
    for node in _ctl_module().body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [
                call for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == function_name
            ]

    raise AssertionError('%s not found' % class_name)


def _clear_color_environment(monkeypatch):
    for name in ('FORCE_COLOR', 'NO_COLOR', 'ANSI_COLORS_DISABLED'):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(('environment', 'expected'), [
    ({'TERM': 'xterm'}, '\x1b[32mRunning\x1b[0m'),
    ({'TERM': 'xterm', 'NO_COLOR': '', 'FORCE_COLOR': '1'}, 'Running'),
    ({'TERM': 'xterm', 'ANSI_COLORS_DISABLED': '', 'FORCE_COLOR': '1'}, 'Running'),
    ({'TERM': 'dumb'}, '\x1b[32mRunning\x1b[0m'),
    ({'TERM': 'dumb', 'FORCE_COLOR': ''}, '\x1b[32mRunning\x1b[0m'),
])
def test_colorize_output_preserves_status_color_without_mutating_environment(
        monkeypatch, environment, expected):
    _clear_color_environment(monkeypatch)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    original_environment = dict(os.environ)

    output = _load_colorize_output()('Running', 'green')

    assert output == expected
    assert dict(os.environ) == original_environment


def test_status_commands_use_explicit_renderer_for_status_states():
    expected_calls = {'ShowStatusCmd': 3, 'UiStatusCmd': 8}

    for class_name, count in expected_calls.items():
        assert len(_class_function_calls(class_name, 'colorize_output')) == count
        assert not _class_function_calls(class_name, 'enable_status_color')


@pytest.mark.parametrize(('class_name', 'args', 'remote_command'), [
    (
        'ShowStatusCmd',
        SimpleNamespace(quiet=False, host='root@192.0.2.10'),
        'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no root@192.0.2.10 '
        '"/usr/bin/zstack-ctl status"',
    ),
    (
        'UiStatusCmd',
        SimpleNamespace(quiet=False, host='192.0.2.11'),
        'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no 192.0.2.11 '
        '"/usr/bin/zstack-ctl ui_status"',
    ),
])
def test_remote_status_commands_do_not_depend_on_forwarded_environment(
        monkeypatch, class_name, args, remote_command):
    _clear_color_environment(monkeypatch)
    monkeypatch.setenv('TERM', 'xterm')
    commands = []
    namespace = _load_status_commands(commands.append)

    namespace[class_name].__new__(namespace[class_name]).run(args)

    assert commands == [remote_command]
