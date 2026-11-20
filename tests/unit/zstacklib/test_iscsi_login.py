import importlib.util
import shlex
from pathlib import Path
from unittest.mock import Mock

import pytest

from tests.unit.zstacklib.real_linux import load_real_linux


@pytest.fixture
def iscsi():
    path = Path(__file__).resolve().parents[3] / 'zstacklib/zstacklib/utils/iscsi.py'
    spec = importlib.util.spec_from_file_location('zstacklib.utils.iscsi_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.shell = Mock()
    module.shell.ShellCmd.return_value.return_code = 0
    module.linux = load_real_linux()
    module.linux.wait_callback_success = lambda *args, **kwargs: True
    module.config_iscsi_startup_if_needed = lambda: None
    return module


@pytest.mark.parametrize('userinfo', ["qa lab:p'a&ss $5\\east@", ''], ids=['chap', 'no-auth'])
def test_login_preserves_chap_arguments_and_skips_auth_without_credentials(iscsi, userinfo):
    portal = 'storage.example:3260'
    target = 'iqn.2026-01.example:disk'
    login = iscsi.IscsiLogin('iscsi://%s%s/%s/wwn_test' % (userinfo, portal, target))

    assert login.login() == '/dev/disk/by-path/ip-%s-iscsi-%s-lun-*' % (portal, target)

    commands = [shlex.split(call.args[0]) for call in iscsi.shell.method_calls]
    node = ['iscsiadm', '--mode', 'node', '--targetname', target, '-p', portal]
    expected = [['iscsiadm', '-m', 'discovery', '-t', 'sendtargets', '-p', portal]]
    if userinfo:
        for field, value in [('authmethod', 'CHAP'), ('username', 'qa lab'), ('password', "p'a&ss $5\\east")]:
            expected.append(node + ['--op=update', '--name', 'node.session.auth.' + field, '--value=' + value])
    assert commands == expected + [node + ['--login'], ['timeout', '30', 'iscsiadm', '-m', 'session', '-R']]
