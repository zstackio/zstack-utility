"""Exercise the Alinux ZRAM installer branch without running the agent playbook."""
import ast
import json
import os
import re
import shlex
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def installer():
    path = Path(__file__).resolve().parents[3] / 'kvmagent/ansible/kvm.py'
    tree = ast.parse(path.read_text())
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef)
                    and node.name == 'check_alinux_zram_driver')
    messages = []
    calls = []
    responses = {
        'uname -r': (True, '6.6.102-005.3.pro.ali6000.alnx4.x86_64'),
    }

    def run(command, _host, return_status=False, return_output=False):
        calls.append(command)
        response = responses.get(command)
        if response is None:
            if 'repoquery --available' in command:
                response = (True, 'kmod-zstack-zram\t0\t1.0.0\t1.6.6.102.005.3.pro.ali6000.alnx4\tx86_64')
            elif 'repoquery --requires' in command:
                response = (True, 'kernel(x86-64) = 6.6.102-005.3.pro.ali6000.alnx4')
            elif 'rpm -qf --qf' in command:
                response = (True, '(none)\t6.6.102-005.3.pro.ali6000.alnx4\tx86_64')
            elif 'rpm -q --whatprovides' in command:
                response = (True, 'kernel(x86-64) = 6.6.101\n'
                                  'kernel(x86-64) = 6.6.102-005.3.pro.ali6000.alnx4')
            elif ' install ' in command:
                response = (True, '')
            elif '-m zstacklib.utils.zram_driver' in command:
                response = (True, json.dumps({'supported': True}))
            else:
                response = (False, '')
        if return_output:
            return response
        return response[0]

    scope = dict(
        releasever='alinux4', _memory_supported_host=lambda: True,
        virtenv_path='/opt/zstack/virtualenv', shlex=shlex, os=os, re=re,
        run_remote_command=run, host_post_info={}, zstack_repo='zstack-local',
        handle_ansible_info=lambda *args: messages.append(args), json=json)
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), scope)
    return scope['check_alinux_zram_driver'], calls, messages


def test_installs_unique_kernel_matching_repo_kmod_with_guards(installer):
    check, calls, messages = installer
    check()

    assert len(calls) == 7
    assert 'repoquery --available --arch=x86_64 --file' in calls[1]
    assert '--disablerepo="*" --enablerepo=zstack-local' in calls[1]
    assert '/lib/modules/6.6.102-005.3.pro.ali6000.alnx4.x86_64/updates/zstack-zram/zram.ko' in calls[1]
    assert 'repoquery --requires' in calls[2]
    assert ('rpm -qf --qf' in calls[3] and
            '/boot/vmlinuz-6.6.102-005.3.pro.ali6000.alnx4.x86_64' in calls[3])
    assert "rpm -q --whatprovides 'kernel(x86-64)' --provides" in calls[4]
    assert '--exclude="kernel*" --setopt=install_weak_deps=False install ' in calls[5]
    assert calls[5].endswith('kmod-zstack-zram-0:1.0.0-1.6.6.102.005.3.pro.ali6000.alnx4.x86_64')
    assert all('--disablerepo="*" --enablerepo=zstack-local' in calls[index]
               for index in (1, 2, 5))
    assert not messages


@pytest.mark.parametrize('requires, owner_evr, provider', [
    ('kernel(x86-64) = 6.6.103', '6.6.102-005.3.pro.ali6000.alnx4', True),
    ('kernel(x86-64) >= 6.6.102', '6.6.102-005.3.pro.ali6000.alnx4', True),
    ('', '6.6.102-005.3.pro.ali6000.alnx4', True),
    ('kernel(x86-64) = 6.6.102-005.3.pro.ali6000.alnx4', '', True),
    ('kernel(x86-64) = 6.6.102-005.3.pro.ali6000.alnx4',
     '6.6.102-005.3.pro.ali6000.alnx4', False),
])
def test_rejects_kmod_without_exact_installed_kernel_requirement(
        installer, requires, owner_evr, provider):
    check, calls, messages = installer
    original = calls

    def run(command, _host, return_status=False, return_output=False):
        original.append(command)
        if command == 'uname -r':
            result = (True, '6.6.102-005.3.pro.ali6000.alnx4.x86_64')
        elif 'repoquery --available' in command:
            result = (True, 'kmod-zstack-zram\t0\t1.0.0\t1.6.6.102.005.3.pro.ali6000.alnx4\tx86_64')
        elif 'repoquery --requires' in command:
            result = (True, requires)
        elif 'rpm -qf --qf' in command:
            result = (bool(owner_evr),
                      '(none)\t%s\tx86_64' % owner_evr if owner_evr else '')
        elif 'rpm -q --whatprovides' in command:
            result = (provider, 'kernel(x86-64) = 6.6.102-005.3.pro.ali6000.alnx4' if provider else '')
        else:
            result = (True, json.dumps({'supported': True}))
        return result if return_output else result[0]

    # The extracted function closes over its execution namespace; replace the runner there.
    check.__globals__['run_remote_command'] = run
    check()
    assert not any(' install ' in command for command in calls)
    assert messages


def test_rejects_ambiguous_repo_builds_before_install(installer):
    check, calls, messages = installer
    original = check.__globals__['run_remote_command']

    def run(command, *args, **kwargs):
        if 'repoquery --available' in command:
            response = (True, 'kmod-zstack-zram\t0\t1.0.0\trel1\tx86_64\n'
                              'kmod-zstack-zram\t0\t1.0.0\trel2\tx86_64')
            calls.append(command)
            return response if kwargs.get('return_output') else response[0]
        return original(command, *args, **kwargs)

    check.__globals__['run_remote_command'] = run
    check()
    assert not any(' install ' in command for command in calls)
    assert messages


def test_accepts_split_kernel_owner_and_exact_provider_with_nonzero_epoch(installer):
    check, calls, messages = installer
    original = check.__globals__['run_remote_command']

    def run(command, *args, **kwargs):
        if 'repoquery --requires' in command:
            response = (True, 'kernel(x86-64) = 1:6.6.102-005.3.pro.ali6000.alnx4')
            calls.append(command)
            return response if kwargs.get('return_output') else response[0]
        if 'rpm -qf --qf' in command:
            # The boot/module owner need not itself provide kernel(x86-64).
            response = (True, '1\t6.6.102-005.3.pro.ali6000.alnx4\tx86_64')
            calls.append(command)
            return response if kwargs.get('return_output') else response[0]
        if 'rpm -q --whatprovides' in command:
            response = (True, 'kernel-core = 6.6.102-005.3.pro.ali6000.alnx4\n'
                              'kernel(x86-64) = 2:6.6.102-005.3.pro.ali6000.alnx4\n'
                              'kernel(x86-64) = 1:6.6.102-005.3.pro.ali6000.alnx4')
            calls.append(command)
            return response if kwargs.get('return_output') else response[0]
        return original(command, *args, **kwargs)

    check.__globals__['run_remote_command'] = run
    check()
    assert any("--whatprovides 'kernel(x86-64)' --provides" in command
               for command in calls)
    assert any(' install ' in command for command in calls)
    assert not messages


def test_provider_lookup_uses_capability_name_then_matches_versioned_provides(installer):
    check, calls, messages = installer
    original = check.__globals__['run_remote_command']

    def run(command, *args, **kwargs):
        if 'rpm -q --whatprovides' in command:
            # RPM 4.14 rejects a version expression in --whatprovides; the
            # supported name query returns all installed capability versions.
            if ' = ' in command:
                response = (False, '')
            else:
                response = (True, 'kernel(x86-64) = 6.6.101\n'
                                  'kernel(x86-64) = 6.6.102-005.3.pro.ali6000.alnx4')
            calls.append(command)
            return response if kwargs.get('return_output') else response[0]
        return original(command, *args, **kwargs)

    check.__globals__['run_remote_command'] = run
    check()
    assert any("--whatprovides 'kernel(x86-64)' --provides" in command for command in calls)
    assert not any('--whatprovides' in command and ' = ' in command for command in calls)
    assert any(' install ' in command for command in calls)
    assert not messages


def test_rejects_shell_metacharacter_kernel_before_query(installer):
    check, calls, messages = installer
    original = check.__globals__['run_remote_command']

    def run(command, *args, **kwargs):
        if command == 'uname -r':
            return (True, '6.6.x; touch /tmp/pwned') if kwargs.get('return_output') else True
        return original(command, *args, **kwargs)

    check.__globals__['run_remote_command'] = run
    check()
    assert not any('repoquery' in command or ' install ' in command for command in calls)
    assert messages


def test_ignores_release_lines_the_yum_wrapper_prints_before_repoquery(installer):
    check, calls, messages = installer
    original = check.__globals__['run_remote_command']

    def run(command, *args, **kwargs):
        if 'repoquery --available' in command:
            response = (True, 'alinux4\nalinux4\n'
                              'kmod-zstack-zram\t0\t1.0.0\t1.6.6.102.005.3.pro.ali6000.alnx4\tx86_64')
            calls.append(command)
            return response if kwargs.get('return_output') else response[0]
        return original(command, *args, **kwargs)

    check.__globals__['run_remote_command'] = run
    check()
    assert any(' install ' in command and 'kmod-zstack-zram' in command for command in calls)
    assert not messages
