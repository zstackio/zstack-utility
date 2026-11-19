# -*- coding: utf-8 -*-
from types import SimpleNamespace
from unittest.mock import MagicMock

from tests.unit.zstackctl import test_ctl_management_ipv6  # noqa: F401 - installs ctl stubs
from zstackctl import ctl, zstacklib


def test_zstac_91565_map_distro_id_recognizes_kylin_2403_as_rpm_and_kylin4_as_deb():
    kylin_2403 = zstacklib.map_distro_id({'ID': 'kylin', 'VERSION_ID': 'V10'})
    assert kylin_2403 == 'kylin'
    assert kylin_2403 in zstacklib.RPM_BASED_OS

    kylin_4 = zstacklib.map_distro_id({'ID': 'kylin', 'VERSION_ID': '4.0.2'})
    assert kylin_4 == 'kylin4.0.2'
    assert kylin_4 in zstacklib.DEB_BASED_OS


def test_zstac_91565_build_ipv4_firewall_accept_command_guards_iptables_save():
    cmd = ctl.build_ipv4_firewall_accept_command(18201, 'kylin')
    assert '--dport 18201 -j ACCEPT' in cmd
    assert 'iptables.service' in cmd
    assert 'service iptables save' in cmd


def test_zstac_91565_license_server_service_uses_18201_and_opens_firewall(monkeypatch):
    assert ctl.LicenseServerService.default_port == 18201
    assert '18201' in ctl.LicenseServerService.https_health_url

    svc = ctl.LicenseServerService.__new__(ctl.LicenseServerService)
    svc.zsha2_utils = SimpleNamespace(execute_on_peer=MagicMock())

    shell_calls = []
    no_pipe_calls = []
    monkeypatch.setattr(ctl.platform, 'freedesktop_os_release', lambda: {'ID': 'kylin', 'VERSION_ID': 'V10'})
    monkeypatch.setattr(ctl, 'shell_return', lambda cmd: 0)
    monkeypatch.setattr(ctl, 'shell', lambda cmd: shell_calls.append(cmd) or '')
    monkeypatch.setattr(ctl, 'shell_no_pipe', lambda cmd: no_pipe_calls.append(cmd))
    svc._wait_for_license_server = lambda urls: urls[0]

    svc.start()

    assert any('--dport 18201 -j ACCEPT' in c for c in shell_calls)
    assert 'systemctl enable --now zstack-license-server' in no_pipe_calls
    assert svc.zsha2_utils.execute_on_peer.call_count == 2


def test_zstac_91565_start_ui_opens_8114_when_bundled_zcf_license_present(monkeypatch, tmp_path):
    ui_home = tmp_path / 'ui'
    manifest = ui_home / 'zstack-ui' / 'zcf-license' / 'mf-manifest.json'
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{}', encoding='utf-8')

    cmd_obj = ctl.StartUiCmd.__new__(ctl.StartUiCmd)
    cmd_obj._get_db_info = lambda: None
    cmd_obj._report_sns_global_property_updated = lambda _: None
    cmd_obj._configure_nginx_ipv6_listen = lambda *a, **kw: None
    cmd_obj.db_url = 'jdbc:mysql://127.0.0.1:3306/zstack'
    cmd_obj.db_username = 'root'
    cmd_obj.db_password = 'enc'

    ui_props = {
        'mn_host': '127.0.0.1',
        'mn_port': '8080',
        'webhook_host': '127.0.0.1',
        'webhook_port': '5000',
        'server_port': '5000',
        'log': str(tmp_path / 'logs'),
        'enable_ssl': 'false',
        'enable_http2': 'false',
        'ssl_keyalias': '',
        'ssl_keystore': '',
        'ssl_keystore_type': 'PKCS12',
        'ssl_keystore_password': '',
        'catalina_opts': '',
        'redis_password': '',
        'listen.host': '0.0.0.0',
        'zcf-license.host': '',
        'zcf-license.ui_port': '',
    }

    shell_calls = []
    monkeypatch.setattr(ctl.ctl, 'ZSTACK_UI_HOME', str(ui_home))
    monkeypatch.setattr(ctl.ctl, 'ZSTACK_UI_KEYSTORE_PEM', str(tmp_path / 'ui.pem'))
    monkeypatch.setattr(ctl.ctl, 'internal_run', lambda *a, **kw: None)
    monkeypatch.setattr(ctl.ctl, 'read_ui_property', lambda k: ui_props.get(k, ''))
    monkeypatch.setattr(ctl.ctl, 'read_all_ui_properties', lambda: list(ui_props.items()))
    monkeypatch.setattr(ctl.ctl, 'read_property', lambda k: '127.0.0.1' if k == 'management.server.vip' else None)
    monkeypatch.setattr(ctl.ctl, 'write_property', lambda k, v: None)
    monkeypatch.setattr(ctl, 'prepare_ui_ssl_cert', lambda *a, **kw: str(tmp_path / 'keystore.p12'))
    monkeypatch.setattr(ctl.StartUiCmd, 'HTTP_FILE', str(tmp_path / 'http'))
    monkeypatch.setattr(ctl.StartUiCmd, 'PORT_FILE', str(tmp_path / 'port'))
    monkeypatch.setattr(ctl.os, 'system', lambda c: 0)
    monkeypatch.setattr(ctl.platform, 'freedesktop_os_release', lambda: {'ID': 'kylin', 'VERSION_ID': 'V10'})
    monkeypatch.setattr(ctl, 'shell', lambda c, **kw: shell_calls.append(c) or '')
    monkeypatch.setattr(ctl, 'script', lambda *a, **kw: None)
    monkeypatch.setattr(ctl.subprocess, 'getstatusoutput', lambda c: (0, 'UI Running'))
    monkeypatch.setattr(ctl, 'get_ui_address', lambda: '127.0.0.1')

    args = SimpleNamespace(
        host='localhost',
        mn_host='',
        mn_port='',
        webhook_host='',
        webhook_port='',
        server_port='5443',
        log='',
        enable_ssl=True,
        enable_http2='false',
        ssl_keyalias='',
        ssl_keystore='',
        ssl_keystore_type='PKCS12',
        ssl_keystore_password='',
        catalina_opts='',
        redis_password='',
        db_url='jdbc:mysql://127.0.0.1:3306/zstack',
        db_username='root',
        db_password='enc',
        timeout='5',
    )
    monkeypatch.setattr(ctl, 'AESCipher', lambda: SimpleNamespace(is_encrypted=lambda _: True))

    cmd_obj.run(args)

    fw_cmds = [c for c in shell_calls if 'iptables-save' in c]
    assert any('--dport 5000 -j ACCEPT' in c for c in fw_cmds)
    assert any('--dport 5443 -j ACCEPT' in c for c in fw_cmds)
    assert any('--dport 8114 -j ACCEPT' in c for c in fw_cmds)
