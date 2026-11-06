import ast
import json
import os
import re
import textwrap
import types
try:
    import builtins
except ImportError:
    import __builtin__ as builtins
try:
    from unittest.mock import MagicMock, call, patch
except ImportError:
    from mock import MagicMock, call, patch

import pytest


class SimpleNamespace(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
NETWORK_PLUGIN_PATH = os.path.join(ROOT, 'kvmagent/kvmagent/plugins/network_plugin.py')
LINUX_PATH = os.path.join(ROOT, 'zstacklib/zstacklib/utils/linux.py')
IPROUTE_PATH = os.path.join(ROOT, 'zstacklib/zstacklib/utils/iproute.py')


def _read_text(path):
    with open(path, 'r') as f:
        return f.read()


def _extract_func_source(path, name, indent=''):
    source = _read_text(path)
    pattern = r'^%sdef %s\(.*?(?=^%s(?:def |class |@)|\Z)' % (indent, name, indent)
    matches = list(re.finditer(pattern, source, re.MULTILINE | re.DOTALL))
    assert matches, 'missing function %s in %s' % (name, path)
    return textwrap.dedent(matches[0].group(0))


def _load_linux_module():
    mod = types.ModuleType('real_linux')
    mod.__dict__.update({
        'os': os,
        'shell': SimpleNamespace(
            call=MagicMock(return_value=''),
            run=MagicMock(return_value=0),
            ShellCmd=MagicMock(),
        ),
        'iproute': SimpleNamespace(
            set_link_up=MagicMock(),
            add_address=MagicMock(),
            delete_link_no_error=MagicMock(),
            batch_populate_vxlan_fdbs=MagicMock(),
            batch_delete_vxlan_fdbs=MagicMock(),
        ),
        'logger': MagicMock(),
        'LinuxError': RuntimeError,
        'read_file_strip': MagicMock(return_value=None),
        'read_file_lines': MagicMock(return_value=[]),
        'write_file': MagicMock(return_value='/sys/mock'),
        'is_bridge': MagicMock(return_value=True),
        'is_bridge_slave': MagicMock(return_value=True),
        'get_all_bridge_interface': MagicMock(return_value=[]),
        'get_device_ip': MagicMock(return_value=None),
        'netmask_to_cidr': MagicMock(return_value=24),
        'netmask_to_broadcast': MagicMock(return_value='192.168.1.255'),
    })
    func_names = [
        'set_bridge_alias_using_phy_nic_name',
        'is_network_device_existing',
        'is_network_device_up',
        'write_sysfs_if_changed',
        'is_vif_on_bridge',
        'find_bridge_having_physical_interface',
        'get_interface_master_device',
        'ip_link_set_net_device_master',
        'create_bridge',
        'make_vlan_eth_name',
        'delete_vlan_eth',
        'create_vlan_eth',
        'get_devices_with_ip',
        'create_vlan_bridge',
        'get_vxlan_interfaces_vtep_map',
        'create_vxlan_interface',
        'create_vxlan_bridge',
        'populate_vxlan_fdbs',
        'get_interfs_from_uuids',
        'set_device_uuid_alias',
    ]
    for fname in func_names:
        src = _extract_func_source(LINUX_PATH, fname)
        exec(compile(src, LINUX_PATH, 'exec'), mod.__dict__)
    return mod


def _load_iproute_query():
    mod = types.ModuleType('real_iproute')
    mod.__dict__.update({
        'os': os,
        'socket': SimpleNamespace(),
        'pyroute2': SimpleNamespace(IPRoute=type('IPRoute', (object,), {})),
    })
    src = _extract_func_source(IPROUTE_PATH, '_query_index_by_ifname')
    exec(compile(src, IPROUTE_PATH, 'exec'), mod.__dict__)
    return mod


def _load_network_plugin():
    class _Resp(object):
        def __init__(self):
            self.success = True
            self.error = None

    def _loads(s):
        def _to_ns(val):
            if isinstance(val, dict):
                return SimpleNamespace(**dict((k, _to_ns(v)) for k, v in val.items()))
            if isinstance(val, list):
                return [_to_ns(x) for x in val]
            return val
        return _to_ns(json.loads(s))

    def _dumps(obj):
        return json.dumps({'success': getattr(obj, 'success', True), 'error': getattr(obj, 'error', None)})

    ns = {
        'os': os,
        'traceback': SimpleNamespace(format_exc=lambda: 'tb'),
        'logger': MagicMock(),
        'http': SimpleNamespace(REQUEST_BODY='body'),
        'jsonobject': SimpleNamespace(loads=_loads, dumps=_dumps),
        'linux': SimpleNamespace(
            create_bridge=MagicMock(),
            create_vlan_bridge=MagicMock(),
            set_device_uuid_alias=MagicMock(),
            set_bridge_alias_using_phy_nic_name=MagicMock(),
            read_file_strip=MagicMock(return_value=None),
            write_file=MagicMock(return_value=True),
            get_devices_with_ip=MagicMock(return_value=set()),
            get_vxlan_interfaces_vtep_map=MagicMock(return_value={}),
            create_vxlan_interface=MagicMock(),
            create_vxlan_bridge=MagicMock(),
        ),
        'iproute': SimpleNamespace(
            query_link=MagicMock(return_value=SimpleNamespace(mtu=1500)),
            set_link_attribute=MagicMock(),
        ),
        'shell': SimpleNamespace(
            call=MagicMock(return_value=''),
            ShellCmd=MagicMock(),
        ),
        'CreateBridgeResponse': _Resp,
        'CreateVlanBridgeResponse': _Resp,
        'CreateVlanBridgesResponse': _Resp,
        'CreateVxlanBridgeResponse': _Resp,
        'CreateVxlanBridgesResponse': _Resp,
        'VXLAN_DEFAULT_PORT': 8472,
    }
    methods = [
        '_get_interface_mtu',
        '_configure_bridge_mtu',
        '_configure_bridge_learning',
        '_enable_bridge_igmp_snooping',
        'create_novlan_bridge',
        '_realize_single_vlan_bridge',
        'create_vlan_bridge',
        'create_vlan_bridges',
        'create_single_vxlan_bridge',
        'create_vxlan_bridge',
        'create_vxlan_bridges',
    ]
    cls_dict = {
        '_ifup_device_if_down': MagicMock(),
        '_configure_bridge': MagicMock(),
    }
    for mname in methods:
        src = _extract_func_source(NETWORK_PLUGIN_PATH, mname, indent='    ')
        local_ns = dict(ns)
        exec(compile(src, NETWORK_PLUGIN_PATH, 'exec'), local_ns)
        cls_dict[mname] = local_ns[mname]
    plugin_cls = type('NetworkPluginUnderTest', (object,), cls_dict)
    return plugin_cls(), SimpleNamespace(**ns)


def test_python2_syntax_compatibility_of_modified_functions():
    checked = [
        (IPROUTE_PATH, '_query_index_by_ifname', ''),
        (IPROUTE_PATH, 'batch_populate_vxlan_fdbs', ''),
        (IPROUTE_PATH, 'batch_delete_vxlan_fdbs', ''),
        (LINUX_PATH, 'set_bridge_alias_using_phy_nic_name', ''),
        (LINUX_PATH, 'is_network_device_up', ''),
        (LINUX_PATH, 'write_sysfs_if_changed', ''),
        (LINUX_PATH, 'is_vif_on_bridge', ''),
        (LINUX_PATH, 'find_bridge_having_physical_interface', ''),
        (LINUX_PATH, 'ip_link_set_net_device_master', ''),
        (LINUX_PATH, 'create_bridge', ''),
        (LINUX_PATH, 'create_vlan_eth', ''),
        (LINUX_PATH, 'get_devices_with_ip', ''),
        (LINUX_PATH, 'create_vlan_bridge', ''),
        (LINUX_PATH, 'get_vxlan_interfaces_vtep_map', ''),
        (LINUX_PATH, 'create_vxlan_interface', ''),
        (LINUX_PATH, 'create_vxlan_bridge', ''),
        (LINUX_PATH, 'get_interfs_from_uuids', ''),
        (LINUX_PATH, 'set_device_uuid_alias', ''),
        (NETWORK_PLUGIN_PATH, '_get_interface_mtu', '    '),
        (NETWORK_PLUGIN_PATH, '_configure_bridge_mtu', '    '),
        (NETWORK_PLUGIN_PATH, '_configure_bridge_learning', '    '),
        (NETWORK_PLUGIN_PATH, '_enable_bridge_igmp_snooping', '    '),
        (NETWORK_PLUGIN_PATH, '_realize_single_vlan_bridge', '    '),
        (NETWORK_PLUGIN_PATH, 'create_vlan_bridge', '    '),
        (NETWORK_PLUGIN_PATH, 'create_vlan_bridges', '    '),
        (NETWORK_PLUGIN_PATH, 'create_single_vxlan_bridge', '    '),
        (NETWORK_PLUGIN_PATH, 'create_vxlan_bridges', '    '),
    ]
    py3_only_nodes = tuple(
        getattr(ast, name) for name in (
            'JoinedStr', 'FormattedValue', 'AnnAssign', 'Nonlocal',
            'YieldFrom', 'AsyncFunctionDef', 'AsyncFor', 'AsyncWith', 'Await',
        ) if hasattr(ast, name)
    )
    for path, fname, indent in checked:
        src = _extract_func_source(path, fname, indent=indent)
        tree = ast.parse(src, filename=path)
        for node in ast.walk(tree):
            assert not isinstance(node, py3_only_nodes), (
                'Python 3-only syntax %s in %s:%s' % (type(node).__name__, path, fname)
            )
            if isinstance(node, ast.FunctionDef):
                assert getattr(node, 'returns', None) is None
                if hasattr(node.args, 'kwonlyargs'):
                    assert not node.args.kwonlyargs
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'super':
                assert len(node.args) == 2, 'bare super() in %s:%s' % (path, fname)


def test_create_vlan_bridges_batch_and_fail_fast():
    plugin, env = _load_network_plugin()
    env.linux.get_devices_with_ip.return_value = set(['eth0.100'])

    req = {
        'body': json.dumps({
            'bridgeCmds': [
                {
                    'bridgeName': 'br_eth0_0',
                    'physicalInterfaceName': 'eth0',
                    'vlan': 0,
                    'l2NetworkUuid': 'l2-0',
                    'disableIptables': False,
                    'mtu': 1500,
                },
                {
                    'bridgeName': 'br_eth0_100',
                    'physicalInterfaceName': 'eth0',
                    'vlan': 100,
                    'l2NetworkUuid': 'l2-100',
                    'disableIptables': False,
                    'mtu': 1500,
                },
                {
                    'bridgeName': 'br_eth0_200',
                    'physicalInterfaceName': 'eth0',
                    'vlan': 200,
                    'l2NetworkUuid': 'l2-200',
                    'disableIptables': False,
                    'mtu': 1500,
                },
            ]
        })
    }
    rsp = json.loads(plugin.create_vlan_bridges(req))
    assert rsp['success'] is True
    env.linux.create_bridge.assert_called_once_with('br_eth0_0', 'eth0')
    assert env.linux.create_vlan_bridge.call_args_list == [
        call('br_eth0_100', 'eth0', 100),
        call('br_eth0_200', 'eth0', 200, move_route=False),
    ]
    assert plugin._configure_bridge.call_count == 2

    # Fail-fast on 2nd VLAN bridge stops batch and reports error
    def _fail_on_200(br, nic, vlan, **_kw):
        if vlan == 200:
            raise RuntimeError('vlan 200 error')

    env.linux.create_vlan_bridge.reset_mock()
    env.linux.create_vlan_bridge.side_effect = _fail_on_200
    fail_req = {
        'body': json.dumps({
            'bridgeCmds': [
                {'bridgeName': 'br_eth0_100', 'physicalInterfaceName': 'eth0', 'vlan': 100, 'l2NetworkUuid': 'u1', 'disableIptables': False, 'mtu': 1500},
                {'bridgeName': 'br_eth0_200', 'physicalInterfaceName': 'eth0', 'vlan': 200, 'l2NetworkUuid': 'u2', 'disableIptables': False, 'mtu': 1500},
                {'bridgeName': 'br_eth0_300', 'physicalInterfaceName': 'eth0', 'vlan': 300, 'l2NetworkUuid': 'u3', 'disableIptables': False, 'mtu': 1500},
            ]
        })
    }
    fail_rsp = json.loads(plugin.create_vlan_bridges(fail_req))
    assert fail_rsp['success'] is False
    assert 'br_eth0_200' in fail_rsp['error']
    assert env.linux.create_vlan_bridge.call_count == 2


def test_create_vxlan_bridges_prefetches_vteps_and_iproute_py2_ifindex_fallback(tmp_path):
    plugin, env = _load_network_plugin()
    env.linux.get_vxlan_interfaces_vtep_map.return_value = {'vxlan10': '10.0.0.1'}

    req = {
        'body': json.dumps({
            'bridgeCmds': [
                {'bridgeName': 'br_vx_10', 'vni': 10, 'vtepIp': '10.0.0.1', 'peers': ['10.0.0.2'], 'mtu': 1450, 'l2NetworkUuid': 'u10', 'dstport': None},
                {'bridgeName': 'br_vx_11', 'vni': 11, 'vtepIp': '10.0.0.1', 'peers': ['10.0.0.2'], 'mtu': 1450, 'l2NetworkUuid': 'u11', 'dstport': None},
            ]
        })
    }
    rsp = json.loads(plugin.create_vxlan_bridges(req))
    assert rsp['success'] is True
    env.linux.get_vxlan_interfaces_vtep_map.assert_called_once()
    assert env.linux.create_vxlan_interface.call_args_list == [
        call(10, '10.0.0.1', 8472, existing_vxlan_vteps={'vxlan10': '10.0.0.1'}),
        call(11, '10.0.0.1', 8472, existing_vxlan_vteps={'vxlan10': '10.0.0.1'}),
    ]

    # Verify _query_index_by_ifname in both Python 3 (socket.if_nametoindex) and Python 2 (/sys/class/net/<if>/ifindex)
    ipr_mod = _load_iproute_query()
    real_ipr = ipr_mod.pyroute2.IPRoute()
    real_ipr.link_lookup = MagicMock(return_value=[99])

    # 1. Python 2 mode (socket has no if_nametoindex): reads /sys/class/net/<if>/ifindex without calling link_lookup
    with patch.object(ipr_mod.os.path, 'isdir', return_value=True), \
         patch.object(ipr_mod.os.path, 'exists', side_effect=lambda p: p == '/sys/class/net/vxlan10/ifindex'):
        ifidx_file = tmp_path / 'ifindex'
        ifidx_file.write_text(u'77\n')
        real_open = builtins.open
        with patch.object(builtins, 'open', side_effect=lambda p, *a, **kw: real_open(str(ifidx_file), *a, **kw) if p == '/sys/class/net/vxlan10/ifindex' else real_open(p, *a, **kw)):
            assert ipr_mod._query_index_by_ifname('vxlan10', real_ipr) == 77
            assert ipr_mod._query_index_by_ifname('vxlan_missing', real_ipr) is None
            real_ipr.link_lookup.assert_not_called()

    # 2. Python 3 mode (socket.if_nametoindex available)
    ipr_mod.socket.if_nametoindex = MagicMock(return_value=42)
    assert ipr_mod._query_index_by_ifname('eth0', real_ipr) == 42
    ipr_mod.socket.if_nametoindex.assert_called_once_with('eth0')
    real_ipr.link_lookup.assert_not_called()


def test_read_compare_repair_skips_unchanged_and_heals_drift():
    real_linux = _load_linux_module()
    shell_calls = []
    shell_cmds = []
    written_files = []
    link_up_calls = []

    class _FakeShellCmd(object):
        def __init__(self, cmd_str):
            self.cmd_str = cmd_str
            self.return_code = 0
            self.stdout = ''
            if 'ip link | grep' in cmd_str and 'vx-200-uuid' in cmd_str:
                self.stdout = 'vxlan200\n'

        def __call__(self, is_exception=True):
            shell_cmds.append(self.cmd_str)
            return self.stdout

    sysfs_state = {
        '/sys/class/net/eth0': 'dir',
        '/sys/class/net/eth0.100': 'dir',
        '/sys/class/net/eth0.100/flags': '0x1003',
        '/sys/class/net/eth0.100/address': '52:54:00:11:22:33',
        '/sys/class/net/eth0.100/ifalias': 'uuid: vlan-100-uuid',
        '/sys/class/net/eth0.100/brport': 'dir',
        '/sys/class/net/eth0.100/master/uevent': 'INTERFACE=br_eth0_100\n',
        '/sys/class/net/br_eth0_100': 'dir',
        '/sys/class/net/br_eth0_100/bridge': 'dir',
        '/sys/class/net/br_eth0_100/brif': 'dir',
        '/sys/class/net/br_eth0_100/brif/eth0.100': 'dir',
        '/sys/class/net/br_eth0_100/flags': '0x1003',
        '/sys/class/net/br_eth0_100/address': '52:54:00:11:22:33',
        '/sys/class/net/br_eth0_100/ifalias': 'phy_nic: eth0',
        '/sys/class/net/br_eth0_100/bridge/stp_state': '0',
        '/sys/class/net/br_eth0_100/bridge/forward_delay': '0',
        '/sys/class/net/vxlan100': 'dir',
        '/sys/class/net/vxlan100/flags': '0x1003',
        '/sys/class/net/vxlan100/address': 'aa:bb:cc:dd:ee:ff',
        '/sys/class/net/vxlan100/ifalias': 'uuid: vx-100-uuid',
        '/sys/class/net/br_vx_100': 'dir',
        '/sys/class/net/br_vx_100/bridge': 'dir',
        '/sys/class/net/br_vx_100/brif': 'dir',
        '/sys/class/net/br_vx_100/brif/vxlan100': 'dir',
        '/sys/class/net/br_vx_100/flags': '0x1003',
        '/sys/class/net/br_vx_100/address': 'aa:bb:cc:dd:ee:ff',
        '/sys/class/net/br_vx_100/bridge/stp_state': '0',
        '/sys/class/net/br_vx_100/bridge/forward_delay': '0',
    }

    def _write_file(p, content, *_a, **_kw):
        val = str(content).strip()
        sysfs_state[p] = val
        written_files.append((p, val))
        return p

    with patch.object(real_linux.shell, 'ShellCmd', _FakeShellCmd), \
         patch.object(real_linux.shell, 'call', MagicMock(side_effect=lambda cmd, *a, **kw: shell_calls.append(cmd) or '')), \
         patch.object(real_linux.iproute, 'set_link_up', MagicMock(side_effect=lambda dev: link_up_calls.append(dev))), \
         patch.object(real_linux, 'read_file_strip', MagicMock(side_effect=lambda p: sysfs_state.get(p))), \
         patch.object(real_linux, 'read_file_lines', MagicMock(side_effect=lambda p: sysfs_state[p].splitlines() if p in sysfs_state else [])), \
         patch.object(real_linux, 'write_file', MagicMock(side_effect=_write_file)), \
         patch.object(real_linux, 'is_bridge', MagicMock(side_effect=lambda d: sysfs_state.get('/sys/class/net/%s/bridge' % d) == 'dir')), \
         patch.object(real_linux, 'is_bridge_slave', MagicMock(side_effect=lambda d: sysfs_state.get('/sys/class/net/%s/brport' % d) == 'dir')), \
         patch.object(real_linux.os.path, 'exists', side_effect=lambda p: p in sysfs_state), \
         patch.object(real_linux.os.path, 'isdir', side_effect=lambda p: p == '/sys/class/net' or sysfs_state.get(p) == 'dir'), \
         patch.object(real_linux.os, 'listdir', side_effect=lambda p: ['eth0', 'eth0.100', 'br_eth0_100', 'vxlan100', 'br_vx_100'] if p == '/sys/class/net' else []):
        # 1. All existing states match -> 0 shell calls, 0 link_up calls, 0 sysfs writes
        real_linux.create_vlan_bridge('br_eth0_100', 'eth0', 100, move_route=False)
        real_linux.set_bridge_alias_using_phy_nic_name('br_eth0_100', 'eth0')
        real_linux.set_device_uuid_alias('eth0.100', 'vlan-100-uuid')
        real_linux.create_vxlan_interface(100, '10.0.0.1', 8472, existing_vxlan_vteps={'vxlan100': '10.0.0.1'})
        real_linux.create_vxlan_bridge('vxlan100', 'br_vx_100', None)
        real_linux.set_device_uuid_alias('vxlan100', 'vx-100-uuid')
        assert real_linux.get_interfs_from_uuids(['vx-100-uuid']) == ['vxlan100']

        assert shell_calls == []
        assert shell_cmds == []
        assert written_files == []
        assert link_up_calls == []

        # Partial sysfs match merges with fallback
        assert real_linux.get_interfs_from_uuids(['vx-100-uuid', 'vx-200-uuid']) == ['vxlan100', 'vxlan200']
        del shell_cmds[:]

        # 2. Drift injection: DOWN, MAC mismatch, STP=1, forward_delay=200, alias mismatch, detached slave
        sysfs_state['/sys/class/net/eth0.100/flags'] = '0x1002'
        sysfs_state['/sys/class/net/br_eth0_100/flags'] = '0x1002'
        sysfs_state['/sys/class/net/br_eth0_100/address'] = '00:11:22:33:44:55'
        sysfs_state['/sys/class/net/br_eth0_100/bridge/stp_state'] = '1'
        sysfs_state['/sys/class/net/br_eth0_100/bridge/forward_delay'] = '200'
        sysfs_state['/sys/class/net/br_eth0_100/ifalias'] = 'phy_nic: wrong'
        sysfs_state['/sys/class/net/vxlan100/flags'] = '0x1002'
        sysfs_state['/sys/class/net/br_vx_100/flags'] = '0x1002'
        sysfs_state['/sys/class/net/br_vx_100/address'] = '00:11:22:33:44:55'
        sysfs_state['/sys/class/net/br_vx_100/bridge/stp_state'] = '1'
        sysfs_state['/sys/class/net/br_vx_100/bridge/forward_delay'] = '200'
        sysfs_state['/sys/class/net/vxlan100/ifalias'] = 'uuid: wrong'
        del sysfs_state['/sys/class/net/br_vx_100/brif/vxlan100']

        real_linux.create_vlan_bridge('br_eth0_100', 'eth0', 100, move_route=False)
        real_linux.set_bridge_alias_using_phy_nic_name('br_eth0_100', 'eth0')
        real_linux.create_vxlan_interface(100, '10.0.0.1', 8472, existing_vxlan_vteps={'vxlan100': '10.0.0.1'})
        real_linux.create_vxlan_bridge('vxlan100', 'br_vx_100', None)
        real_linux.set_device_uuid_alias('vxlan100', 'vx-100-uuid')

    assert link_up_calls == ['eth0.100']
    assert 'ip link set br_eth0_100 up' in shell_calls
    assert 'ip link set br_eth0_100 address 52:54:00:11:22:33' in shell_calls
    assert 'ip link set vxlan100 up' in shell_cmds
    assert 'brctl addif br_vx_100 vxlan100' in shell_cmds
    assert 'ip link set br_vx_100 up' in shell_calls
    assert 'ip link set br_vx_100 address aa:bb:cc:dd:ee:ff' in shell_calls
    assert ('/sys/class/net/br_eth0_100/bridge/stp_state', '0') in written_files
    assert ('/sys/class/net/br_eth0_100/bridge/forward_delay', '0') in written_files
    assert ('/sys/class/net/br_vx_100/bridge/stp_state', '0') in written_files
    assert ('/sys/class/net/br_vx_100/bridge/forward_delay', '0') in written_files
    assert ('/sys/class/net/br_eth0_100/ifalias', 'phy_nic: eth0') in written_files
    assert ('/sys/class/net/vxlan100/ifalias', 'uuid: vx-100-uuid') in written_files


def test_network_plugin_sysfs_mtu_learning_igmp_skip_and_repair():
    plugin, env = _load_network_plugin()
    sysfs_values = {
        '/sys/class/net/eth0.100/mtu': '1500',
        '/sys/class/net/eth0.100/brport/learning': '1',
        '/sys/class/net/br_eth0_100/bridge/multicast_querier': '1',
        '/sys/class/net/br_eth0_100/bridge/multicast_snooping': '1',
    }
    with patch.object(env.os.path, 'exists', side_effect=lambda p: p in sysfs_values):
        env.linux.read_file_strip.side_effect = lambda p: sysfs_values.get(p)
        assert plugin._get_interface_mtu('eth0.100') == 1500
        plugin._configure_bridge_mtu('br_eth0_100', 'eth0.100', 1500)
        plugin._configure_bridge_learning('br_eth0_100', 'eth0.100', 'on')
        plugin._enable_bridge_igmp_snooping('br_eth0_100')

        env.iproute.query_link.assert_not_called()
        env.iproute.set_link_attribute.assert_not_called()
        env.linux.write_file.assert_not_called()
        env.shell.call.assert_not_called()

        # Drift MTU, learning, and multicast_querier -> repaired
        sysfs_values['/sys/class/net/eth0.100/mtu'] = '1400'
        sysfs_values['/sys/class/net/eth0.100/brport/learning'] = '0'
        sysfs_values['/sys/class/net/br_eth0_100/bridge/multicast_querier'] = '0'
        plugin._configure_bridge_mtu('br_eth0_100', 'eth0.100', 1500)
        plugin._configure_bridge_learning('br_eth0_100', 'eth0.100', 'on')
        plugin._enable_bridge_igmp_snooping('br_eth0_100')

        env.iproute.set_link_attribute.assert_called_once_with('eth0.100', mtu=1500)
        assert env.linux.write_file.call_args_list == [
            call('/sys/class/net/eth0.100/brport/learning', '1'),
            call('/sys/class/net/br_eth0_100/bridge/multicast_querier', '1'),
        ]
