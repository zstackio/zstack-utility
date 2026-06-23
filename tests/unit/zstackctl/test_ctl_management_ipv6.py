# -*- coding: utf-8 -*-
import argparse
import json
import socket
import sys
import types
from types import SimpleNamespace

import pytest


def _install_module_stub(name):
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


simplejson = _install_module_stub('simplejson')
simplejson.dumps = json.dumps
simplejson.loads = json.loads

configobj = _install_module_stub('configobj')
configobj.ConfigObj = dict

termcolor = _install_module_stub('termcolor')
termcolor.colored = lambda value, *args, **kwargs: value

yaml = _install_module_stub('yaml')
yaml.load = lambda *args, **kwargs: {}
yaml.dump = lambda *args, **kwargs: ''

for module_name in ('OpenSSL', 'jinja2'):
    _install_module_stub(module_name)

for module_name in ('Crypto', 'Crypto.Cipher', 'Crypto.Cipher.AES', 'Crypto.Util', 'Crypto.Util.py3compat'):
    _install_module_stub(module_name)
sys.modules['Crypto.Cipher'].AES = sys.modules['Crypto.Cipher.AES']
sys.modules['Crypto.Util.py3compat'].__all__ = []

for module_name in (
        'cryptography',
        'cryptography.hazmat',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.serialization',
        'cryptography.hazmat.primitives.serialization.pkcs12'):
    _install_module_stub(module_name)
sys.modules['cryptography.hazmat.primitives'].serialization = sys.modules[
    'cryptography.hazmat.primitives.serialization']
sys.modules['cryptography.hazmat.primitives.serialization'].pkcs12 = sys.modules[
    'cryptography.hazmat.primitives.serialization.pkcs12']

from zstackctl import ctl


def _family_switch_reject_message(old_ip, new_ip):
    return '%s. %s %s' % (
        ctl.ChangeIpCmd.ADDRESS_FAMILY_CHANGE_ERROR % (old_ip, new_ip),
        ctl.ChangeIpCmd.ADDRESS_FAMILY_CHANGE_RISK,
        ctl.ChangeIpCmd.ADDRESS_FAMILY_CHANGE_CONFIRMATION_HINT,
    )


def test_split_host_port_endpoint_supports_bracketed_ipv6():
    assert ctl.split_host_port_endpoint('[2001:db8::10]:3307', '3306') == ('2001:db8::10', '3307')
    assert ctl.split_host_port_endpoint('[2001:db8::10]', '3306') == ('2001:db8::10', '3306')
    assert ctl.split_host_port_endpoint('192.168.10.10:3307', '3306') == ('192.168.10.10', '3307')
    assert ctl.split_host_port_endpoint('2001:db8::10', '22') == ('2001:db8::10', '22')


def test_parse_jdbc_hostname_ports_supports_bracketed_ipv6():
    assert ctl.parse_jdbc_hostname_ports(
        'jdbc:mysql://[2001:db8::10]:3307,[2001:db8::11]/zstack',
        'jdbc:mysql:',
    ) == [('2001:db8::10', '3307'), ('2001:db8::11', ctl.DEFAULT_MYSQL_PORT)]


def test_format_mysql_host_strips_ipv6_jdbc_brackets():
    assert ctl.format_mysql_host('[2001:db8::10]') == '2001:db8::10'
    assert ctl.format_mysql_host('192.168.10.10') == '192.168.10.10'


def test_check_host_info_format_accepts_ipv6_with_port():
    assert ctl.check_host_info_format('root:password@[2001:db8::10]:2222') == (
        'root', 'password', '2001:db8::10', '2222')
    assert ctl.check_host_info_format('root:password@2001:db8::10') == (
        'root', 'password', '2001:db8::10', ctl.DEFAULT_SSH_PORT)


def test_check_ip_port_uses_ipv6_socket_for_ipv6(monkeypatch):
    calls = []

    class FakeSocket(object):
        def __init__(self, family, socket_type):
            calls.append((family, socket_type))

        def connect_ex(self, address):
            calls.append(address)
            return 0

        def close(self):
            calls.append('closed')

    monkeypatch.setattr(ctl.socket, 'socket', FakeSocket)

    assert ctl.check_ip_port('[2001:db8::10]', 3306)
    assert calls == [
        (socket.AF_INET6, socket.SOCK_STREAM),
        ('2001:db8::10', 3306),
        'closed',
    ]


def test_validate_ip_versions_rejects_invalid_ip(monkeypatch):
    errors = []
    monkeypatch.setattr(ctl, 'error', lambda message: errors.append(message))

    zsha = ctl.Zsha2Utils.__new__(ctl.Zsha2Utils)
    zsha.config = {
        'nodeip': '2001:db8::10',
        'peerip': 'invalid-peer',
        'dbvip': '2001:db8::20',
    }

    zsha.validate_ip_versions()

    assert errors == [
        'zsha2 nodeip, peerip and dbvip must be valid IP addresses: peerip=invalid-peer'
    ]


def test_management_server_ip_stack_opts_enable_dual_stack_for_ip6():
    opts = ctl.build_management_server_ip_stack_opts({
        'management.server.ip': '172.24.196.95',
        'management.server.ip6': 'fd00:172:24:249::95',
    })

    assert '-Djava.net.preferIPv4Stack=false' in opts
    assert '-Djava.net.preferIPv6Addresses=true' in opts


def test_management_server_ip_stack_opts_enable_dual_stack_for_ipv4_primary():
    opts = ctl.build_management_server_ip_stack_opts({
        'management.server.ip': '172.24.196.95',
    })

    assert opts == ['-Djava.net.preferIPv4Stack=false']


def test_ui_ipv6_listen_helpers_update_nginx_conf(tmp_path):
    conf = tmp_path / 'extend.server.nginx.conf'
    conf.write_text('        listen 5000;\n        add_header zs-version 5.5.16;\n')

    assert ctl.ui_should_listen_ipv6('::')
    assert ctl.ensure_ui_nginx_ipv6_listen_conf(str(conf), '5000')
    assert 'listen [::]:5000;' in conf.read_text()

    assert not ctl.ensure_ui_nginx_ipv6_listen_conf(str(conf), '5000')


def test_ui_ipv6_listen_helpers_accept_literal_ipv6(tmp_path):
    conf = tmp_path / 'extend.server.nginx.conf'
    conf.write_text('        listen 5000;\n        add_header zs-version 5.5.16;\n')

    assert ctl.ui_should_listen_ipv6('2001:db8::10')
    assert ctl.ui_should_listen_ipv6('[2001:db8::10]')
    assert ctl.ensure_ui_nginx_ipv6_listen_conf(str(conf), '5000', False, False, '2001:db8::10')
    assert 'listen [2001:db8::10]:5000;' in conf.read_text()

    assert not ctl.ensure_ui_nginx_ipv6_listen_conf(str(conf), '5000', False, False, '2001:db8::10')


def test_ui_ipv6_listen_helpers_replace_obsolete_ipv6_listen(tmp_path):
    conf = tmp_path / 'extend.server.nginx.conf'
    conf.write_text(
        '        listen 5000;\n'
        '        listen [::]:5000;\n'
        '        add_header zs-version 5.5.16;\n'
    )

    assert ctl.ensure_ui_nginx_ipv6_listen_conf(str(conf), '5000', False, False, '2001:db8::10')

    content = conf.read_text()
    assert 'listen [2001:db8::10]:5000;' in content
    assert 'listen [::]:5000;' not in content


def test_ui_ipv6_ssl_listen_line_includes_http2():
    assert ctl.build_ui_nginx_ipv6_listen_line('5443', True, 'true') == \
        '        listen [::]:5443 ssl http2;'


def test_ui_ipv6_ssl_listen_line_accepts_literal_ipv6():
    assert ctl.build_ui_nginx_ipv6_listen_line('5443', True, 'true', '2001:db8::10') == \
        '        listen [2001:db8::10]:5443 ssl http2;'


def test_default_ui_hosts_use_local_webhook_in_ha():
    assert ctl.build_default_ui_db_and_webhook_hosts(
        True, ha_db_vip='fd00:5:5:28::54:cccc') == (
            'fd00:5:5:28::54:cccc',
            '127.0.0.1',
        )


def test_default_ui_hosts_use_local_webhook_without_ha():
    assert ctl.build_default_ui_db_and_webhook_hosts(
        False, default_ip='172.24.246.95') == (
            '172.24.246.95',
            '127.0.0.1',
        )


def test_default_ui_db_url_brackets_ipv6_host():
    assert ctl.build_default_ui_db_url('fd00:5:5:28::54:cccc') == \
        'jdbc:mysql://[fd00:5:5:28::54:cccc]:3306'
    assert ctl.build_default_ui_db_url('172.24.246.95') == \
        'jdbc:mysql://172.24.246.95:3306'


def test_ui_webhook_urls_bracket_ipv6_vip():
    assert ctl.build_ui_webhook_urls('fd00:5:5:28::54:cccc', '5000') == (
        'http://[fd00:5:5:28::54:cccc]:5000/webhook/ticket',
        'http://[fd00:5:5:28::54:cccc]:5000/webhook/zwatch',
    )


def test_ui_webhook_urls_keep_ipv4_and_hostname():
    assert ctl.build_ui_webhook_urls('172.24.246.95', '5000') == (
        'http://172.24.246.95:5000/webhook/ticket',
        'http://172.24.246.95:5000/webhook/zwatch',
    )
    assert ctl.build_ui_webhook_urls('localhost', '5000') == (
        'http://localhost:5000/webhook/ticket',
        'http://localhost:5000/webhook/zwatch',
    )


def test_ui_webhook_urls_use_https_for_ipv6_vip():
    assert ctl.build_ui_webhook_urls('fd00:5:5:28::54:cccc', '5443', True) == (
        'https://[fd00:5:5:28::54:cccc]:5443/webhook/ticket',
        'https://[fd00:5:5:28::54:cccc]:5443/webhook/zwatch',
    )


def test_mn_sendcommand_url_brackets_ipv6_host():
    assert ctl.build_mn_sendcommand_url('fd00:5:5:28::54:cccc', '8080') == \
        'http://[fd00:5:5:28::54:cccc]:8080/zstack/asyncrest/sendcommand'
    assert ctl.build_mn_sendcommand_url('172.24.246.95', '8080') == \
        'http://172.24.246.95:8080/zstack/asyncrest/sendcommand'


def test_mn_api_url_brackets_ipv6_host():
    assert ctl.build_mn_api_url('fd00:5:5:28::54:cccc', '8080') == \
        'http://[fd00:5:5:28::54:cccc]:8080/zstack/api'
    assert ctl.build_mn_api_url('172.24.246.95', '8080') == \
        'http://172.24.246.95:8080/zstack/api'


def test_http_call_cmd_quotes_ipv6_sendcommand_url():
    command = ctl.ctl.http_call_cmd % (
        '/report',
        '{}',
        '[fd00:5:5:28::54:cccc]',
        '8080',
    )
    assert '"http://[fd00:5:5:28::54:cccc]:8080/zstack/asyncrest/sendcommand"' in command


def test_check_mgmt_node_command_quotes_ipv6_api_url(monkeypatch):
    class FakeShellCmd(object):
        def __init__(self, command):
            self.command = command
            self.return_code = 1

        def __call__(self, is_exception=True):
            if self.command == 'which curl':
                self.return_code = 0
            if self.command.startswith("grep '^\\s*127.0.0.1\\s'"):
                self.return_code = 0
            return self

    monkeypatch.setattr(ctl, 'ShellCmd', FakeShellCmd)
    monkeypatch.setattr(ctl, 'get_mn_port', lambda: '8080')

    command = ctl.create_check_mgmt_node_command(
        timeout=3,
        mn_node='fd00:5:5:28::54:cccc',
    )

    assert '"http://[fd00:5:5:28::54:cccc]:8080/zstack/api"' in command.command


def test_change_ip_firewall_commands_keep_ipv4_iptables():
    assert ctl.build_change_ip_ipv4_firewall_delete_commands('172.24.246.1', {'3306'}) == [
        'iptables -D INPUT -p tcp --dport 3306 -d 172.24.246.1 -j ACCEPT',
        'iptables -D INPUT -p tcp --dport 3306 -d 127.0.0.1 -j ACCEPT',
    ]
    assert ctl.build_change_ip_ipv4_firewall_accept_commands('172.24.246.247', {'3306'}) == [
        'iptables -A INPUT -p tcp --dport 3306 -j REJECT',
        'iptables -I INPUT -p tcp --dport 3306 -d 172.24.246.247 -j ACCEPT',
        'iptables -I INPUT -p tcp --dport 3306 -d 127.0.0.1 -j ACCEPT',
    ]


def test_change_ip_firewall_commands_use_ip6tables_for_ipv6():
    assert ctl.build_change_ip_ipv6_firewall_delete_commands('fd00:172:24:246::1', {'3306'}) == [
        'ip6tables -D INPUT -p tcp --dport 3306 -d fd00:172:24:246::1 -j ACCEPT',
        'ip6tables -D INPUT -p tcp --dport 3306 -d ::1 -j ACCEPT',
    ]
    assert ctl.build_change_ip_ipv6_firewall_accept_commands('fd00:172:24:246::247', {'3306'}) == [
        'ip6tables -A INPUT -p tcp --dport 3306 -j REJECT',
        'ip6tables -I INPUT -p tcp --dport 3306 -d fd00:172:24:246::247 -j ACCEPT',
        'ip6tables -I INPUT -p tcp --dport 3306 -d ::1 -j ACCEPT',
    ]


def test_change_ip_ipv4_path_cleans_old_ipv6_rules(monkeypatch):
    calls = []
    monkeypatch.setattr(ctl, 'shell_return', lambda command: calls.append(command))
    monkeypatch.setattr(ctl, 'shell', lambda command: calls.append(command))

    ctl.update_change_ip_ipv4_firewall_rules(
        '172.24.246.247', '172.24.246.247', 'fd00:172:24:246::247', {'3306'})

    assert calls == [
        'ip6tables -D INPUT -p tcp --dport 3306 -d fd00:172:24:246::247 -j ACCEPT',
        'ip6tables -D INPUT -p tcp --dport 3306 -d ::1 -j ACCEPT',
        'iptables -A INPUT -p tcp --dport 3306 -j REJECT',
        'iptables -I INPUT -p tcp --dport 3306 -d 172.24.246.247 -j ACCEPT',
        'iptables -I INPUT -p tcp --dport 3306 -d 127.0.0.1 -j ACCEPT',
    ]


def test_change_ip_rejects_legacy_ip_for_dual_stack(monkeypatch):
    class ChangeIpRejected(Exception):
        pass

    errors = []

    def fail(message):
        errors.append(message)
        raise ChangeIpRejected(message)

    monkeypatch.setattr(ctl, 'check_ha', lambda: False)
    monkeypatch.setattr(ctl.os.path, 'isfile', lambda path: True)
    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: {
        'management.server.ip': '172.24.249.182',
        'management.server.ip6': 'fd00:172:24:249::182',
    }.get(name))
    monkeypatch.setattr(ctl, 'error', fail)

    cmd = ctl.ChangeIpCmd.__new__(ctl.ChangeIpCmd)
    monkeypatch.setattr(cmd, 'isVirtualIp', lambda ip: False)

    with pytest.raises(ChangeIpRejected):
        cmd.run(SimpleNamespace(
            ip='fd00:172:24:249::182',
            cloudbus_server_ip=None,
            mysql_ip=None,
            root_password=None,
            ip4=None,
            ip6=None,
        ))

    assert errors == [ctl.ChangeIpCmd.DUAL_STACK_LEGACY_IP_ERROR]


def test_change_ip_rejects_management_ip_address_family_switch(monkeypatch):
    class ChangeIpRejected(Exception):
        pass

    errors = []

    def fail(message):
        errors.append(message)
        raise ChangeIpRejected(message)

    monkeypatch.setattr(ctl, 'check_ha', lambda: True)
    monkeypatch.setattr(ctl.os.path, 'isfile', lambda path: True)
    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: {
        'management.server.ip': '172.24.249.182',
    }.get(name))
    monkeypatch.setattr(ctl, 'error', fail)

    cmd = ctl.ChangeIpCmd.__new__(ctl.ChangeIpCmd)
    monkeypatch.setattr(cmd, 'isVirtualIp', lambda ip: False)

    with pytest.raises(ChangeIpRejected):
        cmd.run(SimpleNamespace(
            ip='fd00:172:24:249::182',
            cloudbus_server_ip=None,
            mysql_ip=None,
            root_password=None,
            ip4=None,
            ip6=None,
        ))

    assert errors == [
        _family_switch_reject_message('172.24.249.182', 'fd00:172:24:249::182')
    ]


def test_change_ip_rejects_family_switch_without_risk_confirmation(monkeypatch):
    class ChangeIpRejected(Exception):
        pass

    errors = []

    def fail(message):
        errors.append(message)
        raise ChangeIpRejected(message)

    monkeypatch.setattr(ctl, 'check_ha', lambda: False)
    monkeypatch.setattr(ctl.os.path, 'isfile', lambda path: True)
    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: {
        'management.server.ip': '172.24.249.182',
    }.get(name))
    monkeypatch.setattr(ctl, 'error', fail)

    cmd = ctl.ChangeIpCmd.__new__(ctl.ChangeIpCmd)
    monkeypatch.setattr(cmd, 'isVirtualIp', lambda ip: False)

    with pytest.raises(ChangeIpRejected):
        cmd.run(SimpleNamespace(
            ip='fd00:172:24:249::182',
            cloudbus_server_ip=None,
            mysql_ip=None,
            root_password=None,
            ip4=None,
            ip6=None,
            allow_management_ip_family_change=True,
            yes_i_understand_management_network_risk=False,
        ))

    assert errors == [
        _family_switch_reject_message('172.24.249.182', 'fd00:172:24:249::182')
    ]


def test_change_ip_allows_confirmed_family_switch_and_keeps_old_primary(monkeypatch):
    writes = []
    deletes = []
    shell_calls = []
    firewall_calls = []

    old_ip = '172.24.249.182'
    new_ip = 'fd00:172:24:249::182'
    properties = {
        'management.server.ip': old_ip,
        'management.server.ip6': None,
        'CloudBus.serverIp.0': old_ip,
        'DB.url': 'jdbc:mysql://172.24.249.182:3306/zstack',
        'consoleProxyOverriddenIp': old_ip,
        'management.server.vip': None,
        'management.server.vip6': None,
    }

    monkeypatch.setattr(ctl, 'check_ha', lambda: False)
    monkeypatch.setattr(ctl.os.path, 'isfile', lambda path: True)
    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: properties.get(name))
    monkeypatch.setattr(ctl.ctl, 'read_property_list', lambda prefix: [])
    monkeypatch.setattr(ctl.ctl, 'write_properties', writes.extend)
    monkeypatch.setattr(ctl.ctl, 'write_property', lambda key, value: writes.append((key, value)))
    monkeypatch.setattr(ctl.ctl, 'delete_properties', deletes.extend)
    monkeypatch.setattr(ctl.ctl, 'read_ui_property', lambda name: 'jdbc:mysql://172.24.249.182:3306/zstack_ui')
    monkeypatch.setattr(ctl.ctl, 'write_ui_properties', writes.extend)
    monkeypatch.setattr(ctl, 'shell', lambda command, *args, **kwargs: 'mn-host\n' if command == 'hostname' else shell_calls.append(command) or '')
    monkeypatch.setattr(ctl, 'update_change_ip_firewall_rules', lambda *args: firewall_calls.append(args))
    monkeypatch.setattr(ctl, 'info', lambda *args, **kwargs: None)

    cmd = ctl.ChangeIpCmd.__new__(ctl.ChangeIpCmd)
    monkeypatch.setattr(cmd, 'isVirtualIp', lambda ip: False)
    monkeypatch.setattr(cmd, 'checkMysqlConnection', lambda *args: None)
    monkeypatch.setattr(cmd, 'update_morph_config', lambda ip: shell_calls.append(('morph', ip)))

    cmd.run(SimpleNamespace(
        ip=new_ip,
        cloudbus_server_ip=None,
        mysql_ip=None,
        root_password=None,
        ip4=None,
        ip6=None,
        allow_management_ip_family_change=True,
        yes_i_understand_management_network_risk=True,
    ))

    assert ('management.server.ip', new_ip) in writes
    assert ('management.server.ip4', old_ip) in writes
    assert deletes == ['management.server.ip6']
    assert ('CloudBus.serverIp.0', new_ip) in writes
    assert ('consoleProxyOverriddenIpv4', old_ip) in writes
    assert ('consoleProxyOverriddenIpv6', new_ip) in writes
    assert ('consoleProxyOverriddenIp', '') in writes
    assert ('DB.url', 'jdbc:mysql://[fd00:172:24:249::182]:3306/zstack') in writes
    assert ('db_url', 'jdbc:mysql://[fd00:172:24:249::182]:3306/zstack_ui') in writes
    assert ('morph', new_ip) in shell_calls
    assert firewall_calls == [(new_ip, new_ip, old_ip, {'3306'})]


def test_change_ip_ipv4_ipv6_aliases_parse_to_family_scoped_args():
    parser = argparse.ArgumentParser()
    cmd = ctl.ChangeIpCmd.__new__(ctl.ChangeIpCmd)

    cmd.install_argparse_arguments(parser)
    args = parser.parse_args([
        '--ipv4', '172.24.249.183',
        '--ipv6', 'fd00:172:24:249::183',
    ])

    assert args.ip4 == '172.24.249.183'
    assert args.ip6 == 'fd00:172:24:249::183'


def test_change_ip_rejects_ipv6_unspecified_address(monkeypatch):
    monkeypatch.setattr(ctl, 'check_ha', lambda: False)
    monkeypatch.setattr(ctl.os.path, 'isfile', lambda path: True)
    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: {
        'management.server.ip': 'fd00:172:24:249::182',
    }.get(name))

    cmd = ctl.ChangeIpCmd.__new__(ctl.ChangeIpCmd)
    monkeypatch.setattr(cmd, 'isVirtualIp', lambda ip: False)

    with pytest.raises(ctl.CtlError) as err:
        cmd.run(SimpleNamespace(
            ip='::',
            cloudbus_server_ip=None,
            mysql_ip=None,
            root_password=None,
            ip4=None,
            ip6=None,
        ))

    assert str(err.value) == 'for your data safety, please do NOT use :: as the listen address'


def test_change_ip4_on_dual_stack_updates_ipv4_scoped_properties(monkeypatch):
    writes = []
    shell_calls = []
    firewall_calls = []

    properties = {
        'management.server.ip': '172.24.249.182',
        'management.server.ip6': 'fd00:172:24:249::182',
        'CloudBus.serverIp.0': '172.24.249.182',
        'DB.url': 'jdbc:mysql://172.24.249.182:3306/zstack',
        'consoleProxyOverriddenIp': '172.24.249.182',
        'management.server.vip': None,
        'management.server.vip6': None,
    }

    monkeypatch.setattr(ctl, 'check_ha', lambda: False)
    monkeypatch.setattr(ctl.os.path, 'isfile', lambda path: True)
    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: properties.get(name))
    monkeypatch.setattr(ctl.ctl, 'read_property_list', lambda prefix: [])
    monkeypatch.setattr(ctl.ctl, 'write_properties', writes.extend)
    monkeypatch.setattr(ctl.ctl, 'write_property', lambda key, value: writes.append((key, value)))
    monkeypatch.setattr(ctl.ctl, 'read_ui_property', lambda name: 'jdbc:mysql://172.24.249.182:3306/zstack_ui')
    monkeypatch.setattr(ctl.ctl, 'write_ui_properties', writes.extend)
    monkeypatch.setattr(ctl, 'shell', lambda command, *args, **kwargs: 'mn-host\n' if command == 'hostname' else shell_calls.append(command) or '')
    monkeypatch.setattr(ctl, 'update_change_ip_firewall_rules', lambda *args: firewall_calls.append(args))

    cmd = ctl.ChangeIpCmd.__new__(ctl.ChangeIpCmd)
    monkeypatch.setattr(cmd, 'isVirtualIp', lambda ip: False)
    monkeypatch.setattr(cmd, 'checkMysqlConnection', lambda *args: None)
    monkeypatch.setattr(cmd, 'update_morph_config', lambda ip: shell_calls.append(('morph', ip)))

    cmd.run(SimpleNamespace(
        ip=None,
        ip4='172.24.249.183',
        ip6=None,
        cloudbus_server_ip=None,
        mysql_ip=None,
        root_password=None,
    ))

    assert ('management.server.ip', '172.24.249.183') in writes
    assert ('management.server.ip6', 'fd00:172:24:249::182') not in writes
    assert ('CloudBus.serverIp.0', '172.24.249.183') in writes
    assert ('consoleProxyOverriddenIpv4', '172.24.249.183') in writes
    assert ('consoleProxyOverriddenIp', '') in writes
    assert ('DB.url', 'jdbc:mysql://172.24.249.183:3306/zstack') in writes
    assert ('db_url', 'jdbc:mysql://172.24.249.183:3306/zstack_ui') in writes
    assert ('morph', '172.24.249.183') in shell_calls
    assert firewall_calls == [('172.24.249.183', '172.24.249.183', '172.24.249.182', {'3306'})]


def test_change_ip_dual_stack_updates_empty_console_proxy_to_primary(monkeypatch):
    writes = []
    shell_calls = []

    properties = {
        'management.server.ip': 'fd00:172:24:249::182',
        'management.server.ip4': '172.24.249.182',
        'CloudBus.serverIp.0': 'fd00:172:24:249::182',
        'DB.url': 'jdbc:mysql://[fd00:172:24:249::182]:3306/zstack',
        'consoleProxyOverriddenIp': '',
        'management.server.vip': None,
        'management.server.vip6': None,
    }

    monkeypatch.setattr(ctl, 'check_ha', lambda: False)
    monkeypatch.setattr(ctl.os.path, 'isfile', lambda path: True)
    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: properties.get(name))
    monkeypatch.setattr(ctl.ctl, 'read_property_list', lambda prefix: [])
    monkeypatch.setattr(ctl.ctl, 'write_properties', writes.extend)
    monkeypatch.setattr(ctl.ctl, 'write_property', lambda key, value: writes.append((key, value)))
    monkeypatch.setattr(ctl.ctl, 'read_ui_property', lambda name: 'jdbc:mysql://[fd00:172:24:249::182]:3306/zstack_ui')
    monkeypatch.setattr(ctl.ctl, 'write_ui_properties', writes.extend)
    monkeypatch.setattr(ctl, 'shell', lambda command, *args, **kwargs: 'mn-host\n' if command == 'hostname' else shell_calls.append(command) or '')
    monkeypatch.setattr(ctl, 'update_change_ip_firewall_rules', lambda *args: None)

    cmd = ctl.ChangeIpCmd.__new__(ctl.ChangeIpCmd)
    monkeypatch.setattr(cmd, 'isVirtualIp', lambda ip: False)
    monkeypatch.setattr(cmd, 'checkMysqlConnection', lambda *args: None)
    monkeypatch.setattr(cmd, 'update_morph_config', lambda ip: shell_calls.append(('morph', ip)))

    cmd.run(SimpleNamespace(
        ip=None,
        ip4='172.24.249.183',
        ip6='fd00:172:24:249::183',
        cloudbus_server_ip=None,
        mysql_ip=None,
        root_password=None,
    ))

    assert ('consoleProxyOverriddenIp', '172.24.249.183') not in writes
    assert ('consoleProxyOverriddenIpv4', '172.24.249.183') not in writes
    assert ('consoleProxyOverriddenIpv6', 'fd00:172:24:249::183') in writes


def test_change_ip6_on_dual_stack_preserves_ipv4_scoped_properties(monkeypatch):
    writes = []
    shell_calls = []
    firewall_calls = []

    properties = {
        'management.server.ip': '172.24.249.182',
        'management.server.ip6': 'fd00:172:24:249::181',
        'CloudBus.serverIp.0': '172.24.249.182',
        'DB.url': 'jdbc:mysql://172.24.249.182:3306/zstack',
        'consoleProxyOverriddenIp': '172.24.249.182',
        'management.server.vip': None,
        'management.server.vip6': None,
    }

    monkeypatch.setattr(ctl, 'check_ha', lambda: False)
    monkeypatch.setattr(ctl.os.path, 'isfile', lambda path: True)
    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: properties.get(name))
    monkeypatch.setattr(ctl.ctl, 'read_property_list', lambda prefix: [])
    monkeypatch.setattr(ctl.ctl, 'write_properties', writes.extend)
    monkeypatch.setattr(ctl.ctl, 'write_property', lambda key, value: writes.append((key, value)))
    monkeypatch.setattr(ctl.ctl, 'read_ui_property', lambda name: 'jdbc:mysql://172.24.249.182:3306/zstack_ui')
    monkeypatch.setattr(ctl.ctl, 'write_ui_properties', writes.extend)
    monkeypatch.setattr(ctl, 'shell', lambda command, *args, **kwargs: 'mn-host\n' if command == 'hostname' else shell_calls.append(command) or '')
    monkeypatch.setattr(ctl, 'update_change_ip_firewall_rules', lambda *args: firewall_calls.append(args))

    cmd = ctl.ChangeIpCmd.__new__(ctl.ChangeIpCmd)
    monkeypatch.setattr(cmd, 'isVirtualIp', lambda ip: False)
    monkeypatch.setattr(cmd, 'checkMysqlConnection', lambda *args: None)
    monkeypatch.setattr(cmd, 'update_morph_config', lambda ip: shell_calls.append(('morph', ip)))

    cmd.run(SimpleNamespace(
        ip=None,
        ip4=None,
        ip6='fd00:172:24:249::182',
        cloudbus_server_ip=None,
        mysql_ip=None,
        root_password=None,
    ))

    assert ('management.server.ip6', 'fd00:172:24:249::182') in writes
    assert ('management.server.ip', '172.24.249.182') not in writes
    assert ('CloudBus.serverIp.0', 'fd00:172:24:249::182') not in writes
    assert ('consoleProxyOverriddenIp', 'fd00:172:24:249::182') not in writes
    assert ('DB.url', 'jdbc:mysql://[fd00:172:24:249::182]:3306/zstack') not in writes
    assert ('morph', 'fd00:172:24:249::182') not in shell_calls
    assert firewall_calls == [('fd00:172:24:249::182', None, 'fd00:172:24:249::181', {'3306'})]


def test_change_ip_preserves_custom_same_family_chrony_server(monkeypatch):
    writes = []
    shell_calls = []

    properties = {
        'management.server.ip': '172.24.249.182',
        'DB.url': 'jdbc:mysql://172.24.249.182:3306/zstack',
        'consoleProxyOverriddenIp': '172.24.249.182',
        'management.server.vip': None,
        'management.server.vip6': None,
    }

    monkeypatch.setattr(ctl, 'check_ha', lambda: False)
    monkeypatch.setattr(ctl.os.path, 'isfile', lambda path: True)
    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: properties.get(name))
    monkeypatch.setattr(ctl.ctl, 'read_property_list', lambda prefix: [('chrony.serverIp.0', '172.24.249.10')])
    monkeypatch.setattr(ctl.ctl, 'write_properties', writes.extend)
    monkeypatch.setattr(ctl.ctl, 'write_property', lambda key, value: writes.append((key, value)))
    monkeypatch.setattr(ctl.ctl, 'read_ui_property', lambda name: 'jdbc:mysql://172.24.249.182:3306/zstack_ui')
    monkeypatch.setattr(ctl.ctl, 'write_ui_properties', writes.extend)
    monkeypatch.setattr(ctl, 'shell', lambda command, *args, **kwargs: 'mn-host\n' if command == 'hostname' else shell_calls.append(command) or '')
    monkeypatch.setattr(ctl, 'update_change_ip_firewall_rules', lambda *args: None)

    cmd = ctl.ChangeIpCmd.__new__(ctl.ChangeIpCmd)
    monkeypatch.setattr(cmd, 'isVirtualIp', lambda ip: False)
    monkeypatch.setattr(cmd, 'checkMysqlConnection', lambda *args: None)
    monkeypatch.setattr(cmd, 'update_morph_config', lambda ip: shell_calls.append(('morph', ip)))

    cmd.run(SimpleNamespace(
        ip='172.24.249.183',
        ip4=None,
        ip6=None,
        cloudbus_server_ip=None,
        mysql_ip=None,
        root_password=None,
    ))

    assert ('chrony.serverIp.0', '172.24.249.183') not in writes


def test_add_ip_sets_management_server_ip6_without_configuring_nic(monkeypatch):
    writes = []
    shell_calls = []

    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: {
        'management.server.ip': '172.24.249.182',
    }.get(name))
    monkeypatch.setattr(ctl.ctl, 'write_properties', writes.extend)
    monkeypatch.setattr(ctl, 'local_ip_exists', lambda ip: True)
    monkeypatch.setattr(ctl, 'shell', lambda *args, **kwargs: shell_calls.append(args))
    monkeypatch.setattr(ctl, 'shell_no_pipe', lambda command: shell_calls.append(command))

    cmd = ctl.AddIpCmd.__new__(ctl.AddIpCmd)
    assert cmd.add_management_server_ip_under_lock('fd00:172:24:249::182')

    assert writes == [('management.server.ip6', 'fd00:172:24:249::182')]
    assert shell_calls == []


def test_add_ip_sets_management_server_ip4_for_ipv6_primary(monkeypatch):
    writes = []

    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: {
        'management.server.ip': 'fd00:172:24:249::182',
    }.get(name))
    monkeypatch.setattr(ctl.ctl, 'write_properties', writes.extend)
    monkeypatch.setattr(ctl, 'local_ip_exists', lambda ip: True)

    cmd = ctl.AddIpCmd.__new__(ctl.AddIpCmd)
    assert cmd.add_management_server_ip_under_lock('172.24.249.182')

    assert writes == [('management.server.ip4', '172.24.249.182')]


def test_add_ip_requires_local_address(monkeypatch):
    class AddIpRejected(Exception):
        pass

    errors = []

    def fail(message):
        errors.append(message)
        raise AddIpRejected(message)

    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: {
        'management.server.ip': '172.24.249.182',
    }.get(name))
    monkeypatch.setattr(ctl, 'local_ip_exists', lambda ip: False)
    monkeypatch.setattr(ctl, 'error', fail)

    cmd = ctl.AddIpCmd.__new__(ctl.AddIpCmd)
    with pytest.raises(AddIpRejected):
        cmd.add_management_server_ip_under_lock('fd00:172:24:249::182')

    assert errors == [
        'IP address fd00:172:24:249::182 is not found on any device; '
        'please configure the OS network address before running add_ip'
    ]


def test_add_ip_rejects_existing_different_management_server_ip6(monkeypatch):
    class AddIpRejected(Exception):
        pass

    errors = []

    def fail(message):
        errors.append(message)
        raise AddIpRejected(message)

    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: {
        'management.server.ip': '172.24.249.182',
        'management.server.ip6': 'fd00:172:24:249::181',
    }.get(name))
    monkeypatch.setattr(ctl, 'local_ip_exists', lambda ip: True)
    monkeypatch.setattr(ctl, 'error', fail)

    cmd = ctl.AddIpCmd.__new__(ctl.AddIpCmd)
    with pytest.raises(AddIpRejected):
        cmd.add_management_server_ip_under_lock('fd00:172:24:249::182')

    assert errors == [
        'management.server.ip6 already configured as fd00:172:24:249::181, '
        'cannot add fd00:172:24:249::182'
    ]


def test_add_ip_skips_existing_same_management_server_ip6(monkeypatch):
    writes = []

    monkeypatch.setattr(ctl.ctl, 'read_property', lambda name: {
        'management.server.ip': '172.24.249.182',
        'management.server.ip6': 'fd00:172:24:249::182',
    }.get(name))
    monkeypatch.setattr(ctl.ctl, 'write_properties', writes.extend)
    monkeypatch.setattr(ctl, 'local_ip_exists', lambda ip: True)

    cmd = ctl.AddIpCmd.__new__(ctl.AddIpCmd)

    assert not cmd.add_management_server_ip_under_lock('fd00:172:24:249::182')
    assert writes == []
