from __future__ import annotations

import importlib
import json
import pytest
import io
import sys
from unittest.mock import MagicMock, patch
from typing import Callable, Protocol, cast
from types import SimpleNamespace


class _HttpModule(Protocol):
    REQUEST_BODY: str
    REQUEST_HEADER: str


class _OvsDpdkCtl(Protocol):
    getBondFromFile: Callable[[str], object]


class _OvsModule(Protocol):
    OvsDpdkCtl: _OvsDpdkCtl


class _LinuxModule(Protocol):
    is_network_device_existing: Callable[[str], bool]
    is_bridge: Callable[[str], bool]
    create_bridge: Callable[..., None]
    delete_vlan_bridge: Callable[..., None]
    vlan_eth_exists: Callable[..., bool]
    read_file: Callable[..., str]
    find_process_by_command: Callable[..., object]
    get_hostname: Callable[[], str]
    create_vlan_bridge: Callable[..., None]
    set_bridge_alias_using_phy_nic_name: Callable[..., None]
    set_device_uuid_alias: Callable[..., None]
    create_vlan_eth: Callable[..., None]
    create_vxlan_interface: Callable[..., None]
    create_vxlan_bridge: Callable[..., None]
    update_bridge_interface_configuration: Callable[..., None]
    move_dev_route: Callable[..., None]
    change_vxlan_interface: Callable[..., None]
    get_nics_by_cidr: Callable[..., list[dict[str, str]]]
    get_interfs_from_uuids: Callable[..., list[str]]
    populate_vxlan_fdbs: Callable[..., bool]
    delete_vxlan_fdbs: Callable[..., bool]
    delete_vxlan_bridge: Callable[..., None]
    delete_vlan_eth: Callable[..., None]
    write_file: Callable[..., None]
    is_vif_on_bridge: Callable[..., bool]


class _OsPathModule(Protocol):
    exists: Callable[[str], bool]


class _OsModule(Protocol):
    path: _OsPathModule






class _IprouteModule(Protocol):
    query_link: Callable[..., object]
    set_link_attribute: Callable[..., None]
    set_link_up: Callable[[str], None]
    config_link_isolated: Callable[..., None]




class _ShellModule(Protocol):
    call: Callable[..., str]
    run: Callable[[str], int]
    check_run: Callable[[str], int]
    ShellCmd: Callable[..., object]


class _NetworkPluginProto(Protocol):
    config: dict[str, object]
    _ifup_device_if_down: Callable[[str], None]

    _has_vlan_or_bridge: Callable[[str], bool]
    _get_interface_mtu: Callable[[str], int]
    _add_interface_to_collectd_conf: Callable[..., None]
    _remove_interface_from_collectd_conf: Callable[..., None]
    _restart_collectd: Callable[..., None]
    _update_lldp_conf: Callable[..., None]
    _get_interface_lldp: Callable[..., object]
    _configure_bridge: Callable[..., None]
    _configure_bridge_mtu: Callable[..., None]
    _configure_bridge_learning: Callable[..., None]
    _enable_bridge_igmp_snooping: Callable[..., None]
    update_bridge_vlan: Callable[..., object]
    update_bridge_vxlan: Callable[..., object]
    create_single_vxlan_bridge: Callable[..., None]

    def check_physical_network_interface(self, req: dict[str, object]) -> str: ...
    def add_interface_to_bridge(self, req: dict[str, object]) -> str: ...
    def check_bridge(self, req: dict[str, object]) -> str: ...
    def check_vlan_bridge(self, req: dict[str, object]) -> str: ...
    def check_macvlan_vlan_eth(self, req: dict[str, object]) -> str: ...
    def create_bridge(self, req: dict[str, object]) -> str: ...
    def delete_vlan_bridge(self, req: dict[str, object]) -> str: ...
    def create_vxlan_bridge(self, req: dict[str, object]) -> str: ...
    def create_bonding(self, req: dict[str, object]) -> str: ...
    def update_bonding(self, req: dict[str, object]) -> str: ...
    def attach_nic_to_bonding(self, req: dict[str, object]) -> str: ...
    def detach_nic_from_bonding(self, req: dict[str, object]) -> str: ...
    def delete_bonding(self, req: dict[str, object]) -> str: ...
    def change_lldp_mode(self, req: dict[str, object]) -> str: ...
    def get_lldp_info(self, req: dict[str, object]) -> str: ...
    def apply_lldp_config(self, req: dict[str, object]) -> str: ...
    def update_vlan_bridge(self, req: dict[str, object]) -> str: ...
    def update_vxlan_bridge(self, req: dict[str, object]) -> str: ...
    def create_vlan_bridge(self, req: dict[str, object]) -> str: ...
    def create_mac_vlan_eth(self, req: dict[str, object]) -> str: ...
    def check_vxlan_cidr(self, req: dict[str, object]) -> str: ...
    def create_vxlan_bridges(self, req: dict[str, object]) -> str: ...
    def delete_vxlan_bridge(self, req: dict[str, object]) -> str: ...
    def populate_vxlan_fdb(self, req: dict[str, object]) -> str: ...
    def populate_vxlan_fdbs(self, req: dict[str, object]) -> str: ...
    def delete_vxlan_fdbs(self, req: dict[str, object]) -> str: ...
    def set_bridge_router_port(self, req: dict[str, object]) -> str: ...
    def delete_novlan_bridge(self, req: dict[str, object]) -> str: ...
    def delete_macvlan_vlan_eth(self, req: dict[str, object]) -> str: ...
    def attach_nic_to_ipset_path(self, req: dict[str, object]) -> str: ...
    def detach_nic_to_ipset_path(self, req: dict[str, object]) -> str: ...
    def sync_ipset_path(self, req: dict[str, object]) -> str: ...


class _NetworkPluginModule(Protocol):
    NetworkPlugin: type[_NetworkPluginProto]


from collections.abc import MutableSet

collections = importlib.import_module("collections")
if not hasattr(collections, "MutableSet"):
    setattr(collections, "MutableSet", MutableSet)

_ = sys.modules.setdefault("pyparsing", MagicMock())

try:
    network_plugin = cast(
        _NetworkPluginModule,
        cast(object, importlib.import_module("kvmagent.plugins.network_plugin")),
    )
except (ImportError, ModuleNotFoundError) as e:
    pytest.skip(f"Cannot import network_plugin: {e}", allow_module_level=True)


def _make_req(body_dict: dict[str, object] | None = None) -> dict[str, object]:
    http = cast(_HttpModule, cast(object, importlib.import_module("zstacklib.utils.http")))
    body = json.dumps(body_dict or {})
    return {http.REQUEST_BODY: body, http.REQUEST_HEADER: {}}


def _reload_network_plugin() -> _NetworkPluginModule:
    lock_mod = cast(object, importlib.import_module("zstacklib.utils.lock"))
    plugin_mod = cast(object, importlib.import_module("zstacklib.utils.plugin"))

    from tests.conftest import passthrough_lock

    _orig_lock = getattr(lock_mod, "lock", None)
    _orig_completetask = getattr(plugin_mod, "completetask", None)

    setattr(lock_mod, "lock", passthrough_lock)
    setattr(plugin_mod, "completetask", passthrough_lock)

    module = cast(
        _NetworkPluginModule,
        cast(object, importlib.reload(importlib.import_module("kvmagent.plugins.network_plugin"))),
    )

    # Restore originals so module-level attrs don't leak across tests
    if _orig_lock is not None:
        setattr(lock_mod, "lock", _orig_lock)
    if _orig_completetask is not None:
        setattr(plugin_mod, "completetask", _orig_completetask)

    setattr(module, "http", importlib.import_module("zstacklib.utils.http"))
    setattr(module, "linux", importlib.import_module("zstacklib.utils.linux"))
    setattr(module, "shell", importlib.import_module("zstacklib.utils.shell"))
    setattr(module, "iproute", importlib.import_module("zstacklib.utils.iproute"))
    return module


def _make_plugin() -> _NetworkPluginProto:
    plugin_mod = _reload_network_plugin()
    plugin = plugin_mod.NetworkPlugin.__new__(plugin_mod.NetworkPlugin)
    plugin.config = {}
    plugin_mod.kvmagent.get_host_distribution = MagicMock(return_value='centos')
    return plugin






def _snapshot_modules(*modules: object) -> list[tuple[object, dict[str, object]]]:
    """Capture module __dict__ for later restoration.

    MagicMock modules (injected by conftest) are skipped because their
    internal ``_mock_children`` dict cannot be safely restored via setattr.
    """
    return [
        (m, dict(vars(m)))
        for m in modules
        if m is not None and not isinstance(m, MagicMock)
    ]


def _restore_modules(snapshots: list[tuple[object, dict[str, object]]]) -> None:
    """Restore module attributes to their snapshotted state."""
    for mod, snap in snapshots:
        for key in set(vars(mod)) - set(snap):
            try:
                delattr(mod, key)
            except (AttributeError, TypeError):
                pass
        for key, val in snap.items():
            if vars(mod).get(key) is not val:
                try:
                    setattr(mod, key, val)
                except (AttributeError, TypeError):
                    pass


@pytest.fixture(autouse=True)
def _isolate_shared_modules():
    """Snapshot/restore shared module attrs to prevent test-to-test leakage."""
    snapshots = _snapshot_modules(
        importlib.import_module("zstacklib.utils.linux"),
        importlib.import_module("zstacklib.utils.shell"),
        importlib.import_module("os").path,
        importlib.import_module("zstacklib.utils.iproute"),
        importlib.import_module("zstacklib.utils.ovs"),
        importlib.import_module("kvmagent.kvmagent"),
    )
    yield
    _restore_modules(snapshots)


def _load_rsp(result: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(result))


def _make_open(data: str) -> Callable[..., object]:
    def _open(*_args: object, **_kwargs: object) -> object:
        return io.StringIO(data)

    return _open


@pytest.mark.kvmagent
class TestNetworkPluginNmL2Guard:
    def test_write_nm_conf_uses_device_name(self, tmp_path):
        plugin_mod = importlib.import_module("kvmagent.plugins.network_plugin")
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        original_dir = plugin_mod.NM_CONF_DIR
        plugin_mod.NM_CONF_DIR = str(tmp_path)
        shell.call = MagicMock()
        shell.run = MagicMock(return_value=0)
        try:
            plugin._write_nm_conf(
                'br_eth0_100', ['br_eth0_100', 'eth0.100'], config_nm=False)
        finally:
            plugin_mod.NM_CONF_DIR = original_dir

        config = (tmp_path / 'zstack-l2-br_eth0_100.conf').read_text()
        assert config == (
            '[keyfile]\nunmanaged-devices+='
            'interface-name:br_eth0_100;interface-name:eth0.100\n')
        shell.call.assert_not_called()

    def test_nm_conf_path_rejects_slash_without_regular_expression(self):
        plugin = _make_plugin()

        with pytest.raises(Exception, match='invalid uplink name'):
            plugin._get_nm_conf_path('../br0')

    @pytest.mark.parametrize('uplink_name', [None, '', '   '])
    def test_nm_conf_path_rejects_empty_name(self, uplink_name):
        plugin = _make_plugin()

        with pytest.raises(ValueError, match='invalid uplink name'):
            plugin._get_nm_conf_path(uplink_name)

    @pytest.mark.parametrize('physical_device', [None, '', '   '])
    def test_root_uplink_rejects_empty_device(self, physical_device):
        plugin = _make_plugin()

        with pytest.raises(ValueError, match='cannot be empty'):
            plugin._get_root_uplink_devices(physical_device)

    def test_root_uplink_rejects_missing_sysfs_device(self):
        plugin = _make_plugin()

        with patch('os.path.isdir', return_value=False):
            with pytest.raises(RuntimeError, match='cannot find sysfs path'):
                plugin._get_root_uplink_devices('eth0')

    def test_conf_write_does_not_reload_nm(self, tmp_path):
        plugin_mod = importlib.import_module("kvmagent.plugins.network_plugin")
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        original_dir = plugin_mod.NM_CONF_DIR
        plugin_mod.NM_CONF_DIR = str(tmp_path)
        shell.run = MagicMock(return_value=1)
        shell.call = MagicMock()
        try:
            plugin._write_nm_conf('eth0', ['eth0'], config_nm=False)
        finally:
            plugin_mod.NM_CONF_DIR = original_dir

        assert (tmp_path / 'zstack-l2-eth0.conf').exists()
        shell.call.assert_not_called()

    def test_write_nm_conf_applies_by_default(self, tmp_path):
        plugin_mod = importlib.import_module("kvmagent.plugins.network_plugin")
        plugin = _make_plugin()
        original_dir = plugin_mod.NM_CONF_DIR
        plugin_mod.NM_CONF_DIR = str(tmp_path)
        plugin._config_nm_devices = MagicMock()
        try:
            plugin._write_nm_conf('eth0', ['eth0'])
        finally:
            plugin_mod.NM_CONF_DIR = original_dir

        plugin._config_nm_devices.assert_called_once_with(['eth0'])

    def test_config_nm_devices_keeps_dependency_order_before_reload(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        plugin._is_nm_running = MagicMock(return_value=True)
        plugin._is_device_unmanaged = MagicMock(return_value=False)
        plugin._check_unmanaged_devices = MagicMock()
        linux.is_network_device_existing = MagicMock(return_value=True)
        shell.call = MagicMock()

        plugin._config_nm_devices(['bond0', 'eth1', 'br0'])

        assert [item.args[0] for item in shell.call.call_args_list] == [
            'nmcli device set bond0 managed no',
            'nmcli device set eth1 managed no',
            'nmcli device set br0 managed no',
            'nmcli general reload 1',
        ]
        plugin._check_unmanaged_devices.assert_called_once_with(['bond0', 'eth1', 'br0'])

    def test_bond_uplink_contains_root_and_slaves(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.read_file_strip = MagicMock(return_value='eth1 eth2')

        def is_file(path):
            return path == '/sys/class/net/bond0/bonding/slaves'

        with patch('os.path.isfile', side_effect=is_file), \
                patch('os.path.isdir', return_value=True), patch('os.listdir') as listdir:
            root, devices = plugin._get_root_uplink_devices('bond0')

        assert root == 'bond0'
        assert devices == ['bond0', 'eth1', 'eth2']
        listdir.assert_not_called()

    def test_physical_uplink_contains_only_physical_device(self):
        plugin = _make_plugin()

        with patch('os.path.isfile', return_value=False), patch('os.path.isdir', return_value=True):
            root, devices = plugin._get_root_uplink_devices('eth0')

        assert root == 'eth0'
        assert devices == ['eth0']

    def test_prebuilt_vlan_uses_its_lower_bond_as_root(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.read_file_strip = MagicMock(return_value='eth1 eth2')

        def is_file(path):
            return path in (
                '/proc/net/vlan/bond0.200',
                '/sys/class/net/bond0/bonding/slaves',
            )

        with patch('os.path.isfile', side_effect=is_file), patch('os.path.isdir', return_value=True), \
                patch('os.listdir', return_value=['lower_bond0']):
            root, devices = plugin._get_root_uplink_devices('bond0.200')

        assert root == 'bond0'
        assert devices == ['bond0', 'eth1', 'eth2']

    def test_ensure_base_conf_writes_new_bond_conf(self):
        plugin = _make_plugin()
        plugin._get_root_uplink_devices = MagicMock(side_effect=[
            ('bond0', ['bond0', 'eth1']),
            ('bond0', ['bond0', 'eth1', 'eth2']),
        ])
        plugin._get_nm_conf_path = MagicMock(return_value='/run/NetworkManager/conf.d/zstack-l2-bond0.conf')
        plugin._write_nm_conf = MagicMock()
        plugin._set_devices_up = MagicMock()

        plugin_mod = importlib.import_module("kvmagent.plugins.network_plugin")
        with patch.object(plugin_mod.lock, 'FileLock'), patch('os.path.isfile', return_value=False):
            root, devices = plugin._ensure_base_nm_conf('bond0')

        assert root == 'bond0'
        assert devices == ['bond0', 'eth1', 'eth2']
        plugin._write_nm_conf.assert_called_once_with('bond0', devices)

    def test_ensure_base_conf_does_not_rewrite_existing_conf(self):
        plugin = _make_plugin()
        plugin._get_root_uplink_devices = MagicMock(return_value=('bond0', ['bond0', 'eth1']))
        plugin._get_nm_conf_path = MagicMock(return_value='/run/NetworkManager/conf.d/zstack-l2-bond0.conf')
        plugin._write_nm_conf = MagicMock()
        plugin._set_devices_up = MagicMock()

        plugin_mod = importlib.import_module("kvmagent.plugins.network_plugin")
        with patch.object(plugin_mod.lock, 'FileLock'), patch('os.path.isfile', return_value=True):
            plugin._ensure_base_nm_conf('bond0')

        plugin._write_nm_conf.assert_not_called()
        plugin._set_devices_up.assert_not_called()

    def test_write_l2_conf_does_not_copy_base_devices(self):
        plugin = _make_plugin()
        plugin._ensure_base_nm_conf = MagicMock(return_value=(
            'bond0', ['bond0', 'eth1', 'eth2']))
        plugin._write_nm_conf = MagicMock()
        plugin._set_devices_up = MagicMock()

        devices = plugin._write_l2_nm_conf(
            'bond0', 'br_vlan1001', ['br_vlan1001', 'bond0.1001'])

        plugin._write_nm_conf.assert_called_once_with(
            'br_vlan1001', ['br_vlan1001', 'bond0.1001'])
        assert devices == ['bond0', 'eth1', 'eth2', 'br_vlan1001', 'bond0.1001']

    def test_prebuilt_vlan_is_written_to_bridge_conf(self):
        plugin = _make_plugin()
        plugin._ensure_base_nm_conf = MagicMock(return_value=(
            'bond0', ['bond0', 'eth1', 'eth2']))
        plugin._write_nm_conf = MagicMock()
        plugin._set_devices_up = MagicMock()

        plugin._write_l2_nm_conf('bond0.200', 'br0', ['br0'])

        plugin._write_nm_conf.assert_called_once_with('br0', ['bond0.200', 'br0'])

    def test_remove_l2_conf_does_not_remove_base_conf(self):
        plugin = _make_plugin()
        plugin._get_root_uplink_devices = MagicMock(return_value=('bond0', ['bond0', 'eth1']))
        plugin._get_nm_conf_path = MagicMock(side_effect=lambda name: '/run/NetworkManager/conf.d/zstack-l2-%s.conf' % name)
        plugin._is_nm_running = MagicMock(return_value=True)
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        linux.is_network_device_existing = MagicMock(return_value=True)
        shell.call = MagicMock()

        with patch('os.path.exists', return_value=True), patch('os.unlink') as unlink:
            plugin._remove_l2_nm_conf('bond0', 'br0', ['br0'])

        unlink.assert_called_once_with('/run/NetworkManager/conf.d/zstack-l2-br0.conf')
        assert '/run/NetworkManager/conf.d/zstack-l2-bond0.conf' not in [
            call.args[0] for call in unlink.call_args_list]

    def test_set_devices_up_uses_one_command_per_existing_device(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        linux.is_network_device_existing = MagicMock(return_value=True)
        shell.call = MagicMock()

        plugin._set_devices_up(['br0', 'eth0.100', 'eth0'])

        commands = []
        for item in shell.call.call_args_list:
            commands.append(item.args[0])
        assert commands == [
            'ip link set dev br0 up',
            'ip link set dev eth0.100 up',
            'ip link set dev eth0 up',
        ]

    def test_update_legacy_branch_does_not_enter_nm_logic(self):
        plugin = _make_plugin()
        plugin.update_bridge_vlan = MagicMock()

        req = _make_req({
            'bridgeName': 'br0', 'physicalInterfaceName': 'eth0',
            'oldVlan': 100, 'newVlan': 200, 'l2NetworkUuid': 'l2-uuid',
        })
        rsp = _load_rsp(plugin.update_vlan_bridge(req))

        assert rsp['success'] is True
        plugin.update_bridge_vlan.assert_called_once()

    def test_create_vlan_uses_nm_branch(self):
        plugin = _make_plugin()
        plugin_mod = importlib.import_module("kvmagent.plugins.network_plugin")
        plugin_mod.kvmagent.get_host_distribution = MagicMock(return_value='kylin')
        plugin.create_vlan_bridge_with_nm = MagicMock()
        plugin._get_interface_mtu = MagicMock(return_value=1500)

        req = _make_req({
            'bridgeName': 'br_eth0_100', 'physicalInterfaceName': 'eth0',
            'vlan': 100, 'l2NetworkUuid': 'l2-uuid', 'mtu': 1500,
        })
        rsp = _load_rsp(plugin.create_vlan_bridge(req))

        assert rsp['success'] is True
        assert plugin.create_vlan_bridge_with_nm.call_args.args[2] == 1500

    @pytest.mark.parametrize(('current_mtu', 'expected_mtu_calls'), [
        (1300, [(None, 'eth0', 1500), ('br0', 'eth0.100', 1500)]),
        (9000, [('br0', 'eth0.100', 1500)]),
    ])
    def test_create_vlan_nm_keeps_uplink_at_least_target_mtu(
            self, current_mtu, expected_mtu_calls):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        plugin._write_l2_nm_conf = MagicMock(return_value=['eth0', 'eth0.100', 'br0'])
        plugin._get_interface_mtu = MagicMock(return_value=current_mtu)
        plugin._configure_bridge_mtu = MagicMock()
        plugin._configure_bridge = MagicMock()
        plugin._configure_bridge_learning = MagicMock()
        plugin._configure_bridge_multicast = MagicMock()
        plugin._check_unmanaged_devices = MagicMock()
        linux.create_vlan_bridge = MagicMock()
        linux.set_bridge_alias_using_phy_nic_name = MagicMock()
        linux.set_device_uuid_alias = MagicMock()
        cmd = SimpleNamespace(
            bridgeName='br0', physicalInterfaceName='eth0', vlan=100,
            l2NetworkUuid='l2-uuid', disableIptables=False)

        plugin.create_vlan_bridge_with_nm(cmd, 'eth0.100', 1500)

        mtu_calls = [item.args for item in plugin._configure_bridge_mtu.call_args_list]
        assert mtu_calls == expected_mtu_calls

    def test_update_nm_branch_adds_new_device_before_removing_old_device(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        plugin._write_l2_nm_conf = MagicMock()
        plugin._ifup_device_if_down = MagicMock()
        linux.create_vlan_eth = MagicMock()
        linux.check_bridge_with_interface = MagicMock()
        linux.ip_link_set_net_device_nomaster = MagicMock()
        linux.ip_link_set_net_device_master = MagicMock()
        linux.set_device_uuid_alias = MagicMock()
        linux.delete_vlan_eth = MagicMock()
        cmd = SimpleNamespace(
            bridgeName='br0', physicalInterfaceName='eth0', oldVlan=100,
            newVlan=200, l2NetworkUuid='l2-uuid')

        plugin.update_bridge_vlan_with_nm(cmd)

        assert plugin._write_l2_nm_conf.call_args_list[0].args == (
            'eth0', 'br0', ['br0', 'eth0.100', 'eth0.200'])
        assert plugin._write_l2_nm_conf.call_args_list[1].args == (
            'eth0', 'br0', ['br0', 'eth0.200'])
        linux.delete_vlan_eth.assert_called_once_with('eth0.100')

    def test_update_nm_branch_from_novlan_to_vlan_keeps_nm_conf(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        plugin._write_l2_nm_conf = MagicMock()
        plugin._ifup_device_if_down = MagicMock()
        linux.create_vlan_eth = MagicMock()
        linux.check_bridge_with_interface = MagicMock()
        linux.ip_link_set_net_device_nomaster = MagicMock()
        linux.ip_link_set_net_device_master = MagicMock()
        linux.set_device_uuid_alias = MagicMock()
        linux.move_dev_route = MagicMock()
        cmd = SimpleNamespace(
            bridgeName='br0', physicalInterfaceName='eth0', oldVlan=None,
            newVlan=100, l2NetworkUuid='l2-uuid')

        plugin.update_bridge_vlan_with_nm(cmd)

        plugin._write_l2_nm_conf.assert_called_once_with(
            'eth0', 'br0', ['br0', 'eth0.100'])
        linux.ip_link_set_net_device_nomaster.assert_called_once_with('eth0')
        linux.ip_link_set_net_device_master.assert_called_once_with('eth0.100', 'br0')
        linux.move_dev_route.assert_called_once_with('br0', 'eth0')

    def test_update_nm_branch_from_vlan_to_novlan_removes_old_vlan_only(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        plugin._write_l2_nm_conf = MagicMock()
        plugin._ifup_device_if_down = MagicMock()
        linux.check_bridge_with_interface = MagicMock()
        linux.ip_link_set_net_device_nomaster = MagicMock()
        linux.ip_link_set_net_device_master = MagicMock()
        linux.set_device_uuid_alias = MagicMock()
        linux.move_dev_route = MagicMock()
        linux.delete_vlan_eth = MagicMock()
        cmd = SimpleNamespace(
            bridgeName='br0', physicalInterfaceName='eth0', oldVlan=100,
            newVlan=None, l2NetworkUuid='l2-uuid')

        plugin.update_bridge_vlan_with_nm(cmd)

        assert plugin._write_l2_nm_conf.call_args_list[0].args == (
            'eth0', 'br0', ['br0', 'eth0.100'])
        assert plugin._write_l2_nm_conf.call_args_list[1].args == (
            'eth0', 'br0', ['br0'])
        linux.ip_link_set_net_device_nomaster.assert_called_once_with('eth0.100')
        linux.ip_link_set_net_device_master.assert_called_once_with('eth0', 'br0')
        linux.move_dev_route.assert_called_once_with('eth0', 'br0')
        linux.delete_vlan_eth.assert_called_once_with('eth0.100')

    def test_update_nm_branch_skips_missing_old_vlan(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        plugin._write_l2_nm_conf = MagicMock()
        plugin._ifup_device_if_down = MagicMock()
        linux.create_vlan_eth = MagicMock()
        linux.is_network_device_existing = MagicMock(return_value=False)
        linux.check_bridge_with_interface = MagicMock()
        linux.ip_link_set_net_device_nomaster = MagicMock()
        linux.ip_link_set_net_device_master = MagicMock()
        linux.set_device_uuid_alias = MagicMock()
        linux.delete_vlan_eth = MagicMock()
        cmd = SimpleNamespace(
            bridgeName='br0', physicalInterfaceName='eth0', oldVlan=100,
            newVlan=200, l2NetworkUuid='l2-uuid')

        plugin.update_bridge_vlan_with_nm(cmd)

        linux.check_bridge_with_interface.assert_not_called()
        linux.ip_link_set_net_device_nomaster.assert_not_called()
        linux.ip_link_set_net_device_master.assert_called_once_with('eth0.200', 'br0')

    def test_delete_novlan_removes_bridge_from_nm_conf(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        plugin_mod = importlib.import_module("kvmagent.plugins.network_plugin")
        plugin_mod.kvmagent.get_host_distribution = MagicMock(return_value='kylin')
        plugin._remove_l2_nm_conf = MagicMock()
        linux.delete_novlan_bridge = MagicMock()
        linux.is_network_device_existing = MagicMock(return_value=False)

        req = _make_req({'bridgeName': 'br0', 'physicalInterfaceName': 'eth0'})
        rsp = _load_rsp(plugin.delete_novlan_bridge(req))

        assert rsp['success'] is True
        plugin._remove_l2_nm_conf.assert_called_once_with('eth0', 'br0', ['br0'])

    def test_delete_novlan_keeps_conf_when_bridge_is_still_in_use(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        plugin_mod = importlib.import_module("kvmagent.plugins.network_plugin")
        plugin_mod.kvmagent.get_host_distribution = MagicMock(return_value='kylin')
        plugin._remove_l2_nm_conf = MagicMock()
        linux.delete_novlan_bridge = MagicMock()
        linux.is_network_device_existing = MagicMock(return_value=True)

        req = _make_req({'bridgeName': 'br0', 'physicalInterfaceName': 'eth0'})
        rsp = _load_rsp(plugin.delete_novlan_bridge(req))

        assert rsp['success'] is True
        plugin._remove_l2_nm_conf.assert_not_called()

    def test_delete_vlan_keeps_conf_when_bridge_is_still_in_use(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        plugin_mod = importlib.import_module("kvmagent.plugins.network_plugin")
        plugin_mod.kvmagent.get_host_distribution = MagicMock(return_value='kylin')
        plugin._remove_l2_nm_conf = MagicMock()
        plugin._delete_isolated = MagicMock()
        linux.delete_vlan_bridge = MagicMock()
        linux.delete_vlan_eth = MagicMock()
        linux.is_network_device_existing = MagicMock(return_value=True)

        req = _make_req({
            'bridgeName': 'br0', 'physicalInterfaceName': 'eth0', 'vlan': 100,
        })
        rsp = _load_rsp(plugin.delete_vlan_bridge(req))

        assert rsp['success'] is True
        plugin._remove_l2_nm_conf.assert_not_called()
        linux.delete_vlan_eth.assert_not_called()

    def test_delete_vlan_removes_conf_without_extra_vlan_delete(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        plugin_mod = importlib.import_module("kvmagent.plugins.network_plugin")
        plugin_mod.kvmagent.get_host_distribution = MagicMock(return_value='kylin')
        plugin._remove_l2_nm_conf = MagicMock()
        plugin._delete_isolated = MagicMock()
        linux.delete_vlan_bridge = MagicMock()
        linux.delete_vlan_eth = MagicMock()
        linux.is_network_device_existing = MagicMock(return_value=False)

        req = _make_req({
            'bridgeName': 'br0', 'physicalInterfaceName': 'eth0', 'vlan': 100,
        })
        rsp = _load_rsp(plugin.delete_vlan_bridge(req))

        assert rsp['success'] is True
        plugin._remove_l2_nm_conf.assert_called_once_with(
            'eth0', 'br0', ['br0', 'eth0.100'])
        linux.delete_vlan_eth.assert_not_called()


@pytest.mark.kvmagent
class TestNetworkPluginCheckPhysicalNetworkInterface:
    def test_check_physical_network_interface_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        ovs = cast(_OvsModule, cast(object, importlib.import_module("zstacklib.utils.ovs")))

        linux.is_network_device_existing = MagicMock(return_value=True)
        ovs.OvsDpdkCtl.getBondFromFile = MagicMock(return_value=None)
        setattr(plugin, "_ifup_device_if_down", MagicMock())

        req = _make_req({
            'interfaceNames': ['eth0'],
        })

        result = plugin.check_physical_network_interface(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_check_physical_network_interface_skips_bonded(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        ovs = cast(_OvsModule, cast(object, importlib.import_module("zstacklib.utils.ovs")))
        iproute = cast(_IprouteModule, cast(object, importlib.import_module("zstacklib.utils.iproute")))
        iproute.set_link_up = MagicMock()

        def _is_existing(name: str) -> bool:
            return name == "eth1"

        def _bond_for(name: str) -> str | None:
            return "bond0" if name == "eth0" else None

        linux.is_network_device_existing = MagicMock(side_effect=_is_existing)
        ovs.OvsDpdkCtl.getBondFromFile = MagicMock(side_effect=_bond_for)
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        os_module.path.exists = MagicMock(return_value=True)
        with patch("builtins.open", new=_make_open("down")):
            req = _make_req({'interfaceNames': ['eth0', 'eth1']})
            result = plugin.check_physical_network_interface(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        iproute.set_link_up.assert_called_once_with('eth1')


@pytest.mark.kvmagent
class TestNetworkPluginAddInterfaceToBridge:
    def test_add_interface_to_bridge_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        shell.call = MagicMock(return_value='')
        shell.run = MagicMock(return_value=0)
        shell.check_run = MagicMock(return_value=0)

        req = _make_req({
            'physicalInterfaceName': 'eth0',
            'bridgeName': 'br-test',
        })

        result = plugin.add_interface_to_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_add_interface_to_bridge_moves_from_old_bridge(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        shell.call = MagicMock(return_value='br-old')
        shell.run = MagicMock(return_value=0)
        shell.check_run = MagicMock(return_value=0)

        req = _make_req({
            'physicalInterfaceName': 'eth0',
            'bridgeName': 'br-new',
        })
        result = plugin.add_interface_to_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        shell.run.assert_called_once_with('brctl delif br-old eth0')
        shell.check_run.assert_called_once_with('brctl addif br-new eth0')


@pytest.mark.kvmagent
class TestNetworkPluginCheckBridge:
    def test_check_bridge_when_exists(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.is_bridge = MagicMock(return_value=True)
        setattr(plugin, "_ifup_device_if_down", MagicMock())

        req = _make_req({
            'bridgeName': 'br-test',
            'physicalInterfaceName': 'eth0',
        })

        result = plugin.check_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_check_bridge_missing_sets_error(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.is_bridge = MagicMock(return_value=False)

        req = _make_req({
            'bridgeName': 'br-missing',
            'physicalInterfaceName': 'eth0',
        })
        result = plugin.check_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        assert 'can not find bridge' in cast(str, rsp['error'])


@pytest.mark.kvmagent
class TestNetworkPluginCheckBridgeMissing:
    def test_check_bridge_missing(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.is_bridge = MagicMock(return_value=False)

        req = _make_req({'bridgeName': 'br-missing', 'physicalInterfaceName': 'eth0'})
        result = plugin.check_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False


@pytest.mark.kvmagent
class TestNetworkPluginCheckVlanBridge:
    def test_check_vlan_bridge_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.is_bridge = MagicMock(return_value=True)
        setattr(plugin, "_ifup_device_if_down", MagicMock())

        req = _make_req({'bridgeName': 'br-vlan', 'physicalInterfaceName': 'eth0'})
        result = plugin.check_vlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_check_vlan_bridge_missing_sets_error(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.is_bridge = MagicMock(return_value=False)

        req = _make_req({'bridgeName': 'br-vlan', 'physicalInterfaceName': 'eth0'})
        result = plugin.check_vlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        assert 'can not find vlan bridge' in cast(str, rsp['error'])


@pytest.mark.kvmagent
class TestNetworkPluginCheckMacvlanVlanEth:
    def test_check_macvlan_vlan_eth_missing(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.vlan_eth_exists = MagicMock(return_value=False)

        req = _make_req({'physicalInterfaceName': 'eth0', 'vlan': 100})
        result = plugin.check_macvlan_vlan_eth(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False

    def test_check_macvlan_vlan_eth_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.vlan_eth_exists = MagicMock(return_value=True)
        ifup = MagicMock()
        setattr(plugin, "_ifup_device_if_down", ifup)

        req = _make_req({'physicalInterfaceName': 'eth0', 'vlan': 100})
        result = plugin.check_macvlan_vlan_eth(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        ifup.assert_called_once_with('eth0')


@pytest.mark.kvmagent
class TestNetworkPluginCreateBridge:
    def test_create_bridge_success(self):
        plugin = _make_plugin()
        setattr(plugin, "create_novlan_bridge", MagicMock())

        req = _make_req({'bridgeName': 'br0', 'physicalInterfaceName': 'eth0', 'mtu': 1500})
        result = plugin.create_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_create_bridge_runs_internal_config(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        iproute = cast(_IprouteModule, cast(object, importlib.import_module("zstacklib.utils.iproute")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        linux.create_bridge = MagicMock()
        linux.set_device_uuid_alias = MagicMock()
        linux.set_bridge_alias_using_phy_nic_name = MagicMock()
        linux.write_file = MagicMock(return_value=True)
        iproute.query_link = MagicMock(return_value=SimpleNamespace(mtu=1600))
        iproute.set_link_attribute = MagicMock()
        iproute.set_link_up = MagicMock()
        shell_call = MagicMock()
        shell.call = shell_call

        def _exists(path: str) -> bool:
            return path.endswith('/operstate')

        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        os_module.path.exists = MagicMock(side_effect=_exists)
        with patch("builtins.open", new=_make_open("down")):
            req = _make_req({
                'bridgeName': 'br0',
                'physicalInterfaceName': 'eth0',
                'mtu': 1500,
                'disableIptables': True,
                'l2NetworkUuid': 'l2-uuid',
            })
            result = plugin.create_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        linux.create_bridge.assert_called_once_with('br0', 'eth0')
        iproute.set_link_attribute.assert_called_once_with('eth0', mtu=1600)
        shell.call.assert_any_call('modprobe br_netfilter || true')


@pytest.mark.kvmagent
class TestNetworkPluginDeleteVlanBridge:
    def test_delete_vlan_bridge_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.delete_vlan_bridge = MagicMock()
        setattr(plugin, "_delete_isolated", MagicMock())

        req = _make_req({'bridgeName': 'br0', 'physicalInterfaceName': 'eth0', 'vlan': 100})
        result = plugin.delete_vlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_delete_vlan_bridge_for_novlan(self):
        plugin = _make_plugin()
        delete_bridge = cast(MagicMock, importlib.import_module("kvmagent.plugins.network_plugin"))

        delete_bridge.del_novlan_bridge = MagicMock()

        req = _make_req({'bridgeName': 'br0', 'physicalInterfaceName': 'eth0', 'vlan': 0})
        result = plugin.delete_vlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        cast(MagicMock, delete_bridge.del_novlan_bridge).assert_called_once()


@pytest.mark.kvmagent
class TestNetworkPluginCreateVxlanBridge:
    def test_create_vxlan_bridge_missing_params(self):
        plugin = _make_plugin()

        req = _make_req({'vni': None, 'vtepIp': None})
        result = plugin.create_vxlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False

    def test_create_vxlan_bridge_runs_internal(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        iproute = cast(_IprouteModule, cast(object, importlib.import_module("zstacklib.utils.iproute")))

        linux.create_vxlan_interface = MagicMock()
        linux.create_vxlan_bridge = MagicMock()
        linux.set_device_uuid_alias = MagicMock()
        iproute.query_link = MagicMock(return_value=SimpleNamespace(mtu=1400))
        iproute.set_link_attribute = MagicMock()

        req = _make_req({
            'bridgeName': 'br-vxlan',
            'vni': 10,
            'vtepIp': '10.0.0.1',
            'peers': ['10.0.0.2'],
            'mtu': 1300,
            'l2NetworkUuid': 'l2-uuid',
            'dstport': None,
        })
        result = plugin.create_vxlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        linux.create_vxlan_interface.assert_called_once_with(10, '10.0.0.1', 8472)
        linux.create_vxlan_bridge.assert_called_once_with('vxlan10', 'br-vxlan', ['10.0.0.2'])
        iproute.set_link_attribute.assert_called_once_with('vxlan10', mtu=1400)


@pytest.mark.kvmagent
class TestNetworkPluginCreateBonding:
    def test_create_bonding_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        setattr(plugin, "_has_vlan_or_bridge", MagicMock(return_value=False))
        setattr(plugin, "_get_interface_mtu", MagicMock(return_value=1500))
        setattr(plugin, "_add_interface_to_collectd_conf", MagicMock())
        setattr(plugin, "_restart_collectd", MagicMock())
        shell_call = MagicMock()
        shell.call = shell_call

        req = _make_req({
            'bondName': 'bond0',
            'slaves': [{'interfaceName': 'eth0'}, {'interfaceName': 'eth1'}],
            'mode': 'active-backup',
            'xmitHashPolicy': None,
        })
        result = plugin.create_bonding(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert shell_call.called

    def test_create_bonding_8023ad_uses_min_mtu(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        setattr(plugin, "_has_vlan_or_bridge", MagicMock(return_value=False))
        setattr(plugin, "_get_interface_mtu", MagicMock(side_effect=[9000, 1400]))
        setattr(plugin, "_add_interface_to_collectd_conf", MagicMock())
        setattr(plugin, "_restart_collectd", MagicMock())
        shell_call = MagicMock()
        shell.call = shell_call

        req = _make_req({
            'bondName': 'bond1',
            'slaves': [{'interfaceName': 'eth0'}, {'interfaceName': 'eth1'}],
            'mode': '802.3ad',
            'xmitHashPolicy': 'layer2+3',
        })
        result = plugin.create_bonding(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert any('xmit_hash_policy layer2+3' in call.args[0] for call in shell_call.mock_calls)
        assert any('zs-bond -u bond1 mtu 1400' in call.args[0] for call in shell_call.mock_calls)


@pytest.mark.kvmagent
class TestNetworkPluginUpdateBonding:
    def test_update_bonding_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        setattr(plugin, "_has_vlan_or_bridge", MagicMock(return_value=False))
        linux.read_file = MagicMock(side_effect=['mode active-backup', 'layer2', 'layer2'])
        shell_call = MagicMock()
        shell.call = shell_call

        req = _make_req({
            'bondName': 'bond0',
            'oldSlaves': [{'interfaceName': 'eth0'}],
            'slaves': [{'interfaceName': 'eth0'}, {'interfaceName': 'eth1'}],
            'mode': 'active-backup',
            'xmitHashPolicy': None,
        })
        result = plugin.update_bonding(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert shell_call.called

    def test_update_bonding_updates_mode_and_slaves(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        setattr(plugin, "_has_vlan_or_bridge", MagicMock(return_value=False))
        linux.read_file = MagicMock(side_effect=['mode active-backup', 'layer2', 'layer2'])
        shell_call = MagicMock()
        shell.call = shell_call

        req = _make_req({
            'bondName': 'bond0',
            'oldSlaves': [{'interfaceName': 'eth0'}, {'interfaceName': 'eth1'}],
            'slaves': [{'interfaceName': 'eth1'}, {'interfaceName': 'eth2'}],
            'mode': '802.3ad',
            'xmitHashPolicy': 'layer2+3',
        })
        result = plugin.update_bonding(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert any('zs-bond -u bond0 mode 802.3ad' in call.args[0] for call in shell_call.mock_calls)
        assert any('xmit_hash_policy layer2+3' in call.args[0] for call in shell_call.mock_calls)
        assert not any('xmitHashPolicy' in call.args[0] for call in shell_call.mock_calls)
        assert any('zs-nic-to-bond -a bond0 eth2' in call.args[0] for call in shell_call.mock_calls)
        assert any('zs-nic-to-bond -d bond0 eth0' in call.args[0] for call in shell_call.mock_calls)

    def test_update_bonding_hash_only_uses_current_mode(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.read_file = MagicMock(side_effect=['802.3ad 4', 'layer2 0'])
        shell.call = MagicMock()

        req = _make_req({
            'bondName': 'bond0',
            'oldSlaves': [{'interfaceName': 'eth0'}],
            'slaves': [{'interfaceName': 'eth0'}],
            'mode': None,
            'xmitHashPolicy': 'layer3+4',
        })
        rsp = _load_rsp(plugin.update_bonding(req))

        assert rsp['success'] is True
        shell.call.assert_called_once_with(
            '/usr/local/bin/zs-bond -u bond0 mode 802.3ad xmit_hash_policy layer3+4')


@pytest.mark.kvmagent
class TestNetworkPluginAttachNicToBonding:
    def test_attach_nic_to_bonding_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        setattr(plugin, "_has_vlan_or_bridge", MagicMock(return_value=False))
        shell_call = MagicMock()
        shell.call = shell_call

        req = _make_req({'bondName': 'bond0', 'slaves': [{'interfaceName': 'eth2'}]})
        result = plugin.attach_nic_to_bonding(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert shell_call.called

    def test_attach_nic_to_bonding_rejects_vlan_slave(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        setattr(plugin, "_has_vlan_or_bridge", MagicMock(return_value=True))
        shell_call = MagicMock()
        shell.call = shell_call

        req = _make_req({'bondName': 'bond0', 'slaves': [{'interfaceName': 'eth2'}]})
        result = plugin.attach_nic_to_bonding(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        shell_call.assert_not_called()


@pytest.mark.kvmagent
class TestNetworkPluginDetachNicFromBonding:
    def test_detach_nic_from_bonding_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        shell_call = MagicMock()
        shell.call = shell_call
        req = _make_req({'bondName': 'bond0', 'slaves': [{'interfaceName': 'eth2'}]})
        result = plugin.detach_nic_from_bonding(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert shell_call.called

    def test_detach_nic_from_bonding_handles_error(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        shell.call = MagicMock(side_effect=Exception("detach error"))

        req = _make_req({'bondName': 'bond0', 'slaves': [{'interfaceName': 'eth2'}]})
        result = plugin.detach_nic_from_bonding(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        assert 'unable to detach nic from bonding' in cast(str, rsp['error'])


@pytest.mark.kvmagent
class TestNetworkPluginDeleteBonding:
    def test_delete_bonding_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        setattr(plugin, "_has_vlan_or_bridge", MagicMock(return_value=False))
        setattr(plugin, "_remove_interface_from_collectd_conf", MagicMock())
        setattr(plugin, "_restart_collectd", MagicMock())
        shell_call = MagicMock()
        shell.call = shell_call

        req = _make_req({'bondName': 'bond0'})
        result = plugin.delete_bonding(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_delete_bonding_rejects_vlan(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        setattr(plugin, "_has_vlan_or_bridge", MagicMock(return_value=True))
        setattr(plugin, "_remove_interface_from_collectd_conf", MagicMock())
        setattr(plugin, "_restart_collectd", MagicMock())
        shell_call = MagicMock()
        shell.call = shell_call

        req = _make_req({'bondName': 'bond0'})
        result = plugin.delete_bonding(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        shell_call.assert_not_called()


@pytest.mark.kvmagent
class TestNetworkPluginChangeLldpMode:
    def test_change_lldp_mode_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        linux.find_process_by_command = MagicMock(return_value=True)
        os_module.path.exists = MagicMock(return_value=True)
        setattr(plugin, "_update_lldp_conf", MagicMock())

        req = _make_req({'physicalInterfaceNames': ['eth0'], 'mode': 'rx_only'})
        result = plugin.change_lldp_mode(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert cast(MagicMock, getattr(plugin, "_update_lldp_conf")).called

    def test_change_lldp_mode_initializes_lldpd(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        iproute = cast(_IprouteModule, cast(object, importlib.import_module("zstacklib.utils.iproute")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        linux.find_process_by_command = MagicMock(return_value=False)
        linux.get_hostname = MagicMock(return_value='host')
        iproute.set_link_up = MagicMock()
        shell_call = MagicMock()
        shell.call = shell_call
        setattr(plugin, "_update_lldp_conf", MagicMock())

        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        def _exists_first(path: str) -> bool:
            if path.endswith("/etc/lldpd.d/lldpd.conf"):
                return False
            if path.endswith("command"):
                return True
            return False

        os_module.path.exists = MagicMock(side_effect=_exists_first)
        with patch("kvmagent.plugins.network_plugin.bash_ro", return_value=(0, "0000:00:00.0 Ethernet controller")), \
                patch("builtins.open", new=_make_open("")), \
                patch("kvmagent.plugins.network_plugin.NetworkPlugin._restart_lldpd", MagicMock()), \
                patch("kvmagent.plugins.network_plugin.NetworkPlugin._init_lldpd", MagicMock()):
            req = _make_req({'physicalInterfaceNames': ['eth0'], 'mode': 'rx_only'})
            result = plugin.change_lldp_mode(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        cast(MagicMock, getattr(plugin, "_update_lldp_conf")).assert_called_once()


@pytest.mark.kvmagent
class TestNetworkPluginGetLldpInfo:
    def test_get_lldp_info_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        linux.find_process_by_command = MagicMock(return_value=True)
        os_module.path.exists = MagicMock(return_value=True)
        setattr(plugin, "_get_interface_lldp", MagicMock())
        setattr(plugin, "_get_interface_lldp", MagicMock(return_value={'lldp': 'info'}))

        req = _make_req({'physicalInterfaceName': 'eth0'})
        result = plugin.get_lldp_info(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert rsp['lldpInfo'] == {'lldp': 'info'}

    def test_get_lldp_info_parses_json(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        linux.find_process_by_command = MagicMock(return_value=True)
        os_module.path.exists = MagicMock(return_value=True)

        lldp_json = json.dumps({
            "lldp": {
                "interface": {
                    "eth0": {
                        "chassis": {
                            "sw1": {
                                "id": {"value": "00:11"},
                                "descr": "desc\nline",
                                "mgmt-ip": "10.0.0.1",
                                "capability": [{"type": "bridge", "enabled": True}],
                            }
                        },
                        "port": {
                            "ttl": 100,
                            "id": {"value": "p1"},
                            "descr": "port-desc",
                            "aggregation": "lag1",
                            "mfs": 1500,
                        },
                        "vlan": {"vlan-id": 100},
                    }
                }
            }
        })

        with patch("kvmagent.plugins.network_plugin.bash_ro", return_value=(0, lldp_json)):
            req = _make_req({'physicalInterfaceName': 'eth0'})
            result = plugin.get_lldp_info(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        cast(MagicMock, getattr(plugin, "_get_interface_lldp")).assert_called_once_with('eth0')


@pytest.mark.kvmagent
class TestNetworkPluginApplyLldpConfig:
    def test_apply_lldp_config_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        linux.find_process_by_command = MagicMock(return_value=True)
        os_module.path.exists = MagicMock(return_value=True)
        setattr(plugin, "_update_lldp_conf", MagicMock())

        req = _make_req({'lldpConfig': [{'physicalInterfaceName': 'eth0', 'mode': 'rx_only'}]})
        result = plugin.apply_lldp_config(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert cast(MagicMock, getattr(plugin, "_update_lldp_conf")).called

    def test_apply_lldp_config_updates_multiple(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))

        linux.find_process_by_command = MagicMock(return_value=True)
        os_module.path.exists = MagicMock(return_value=True)
        setattr(plugin, "_update_lldp_conf", MagicMock())

        req = _make_req({
            'lldpConfig': [
                {'physicalInterfaceName': 'eth0', 'mode': 'rx_only'},
                {'physicalInterfaceName': 'eth1', 'mode': 'tx_only'},
            ]
        })
        result = plugin.apply_lldp_config(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert cast(MagicMock, getattr(plugin, "_update_lldp_conf")).call_count == 2


@pytest.mark.kvmagent
class TestNetworkPluginUpdateVlanBridge:
    def test_update_vlan_bridge_success(self):
        plugin = _make_plugin()
        update_vlan = MagicMock()
        plugin.update_bridge_vlan = update_vlan

        req = _make_req({'bridgeName': 'br0', 'physicalInterfaceName': 'eth0', 'oldVlan': 0, 'newVlan': 100})
        result = plugin.update_vlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert update_vlan.called

    def test_update_vlan_bridge_updates_routes(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.create_vlan_eth = MagicMock()
        linux.update_bridge_interface_configuration = MagicMock()
        linux.move_dev_route = MagicMock()
        ifup = MagicMock()
        setattr(plugin, "_ifup_device_if_down", ifup)

        req = _make_req({
            'bridgeName': 'br0',
            'physicalInterfaceName': 'eth0',
            'oldVlan': 100,
            'newVlan': 0,
            'l2NetworkUuid': 'l2-uuid',
        })
        result = plugin.update_vlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        linux.update_bridge_interface_configuration.assert_called_once_with('eth0.100', 'eth0', 'br0', 'l2-uuid')
        linux.move_dev_route.assert_called_once_with('eth0', 'br0')


@pytest.mark.kvmagent
class TestNetworkPluginUpdateVxlanBridge:
    def test_update_vxlan_bridge_success(self):
        plugin = _make_plugin()
        update_vxlan = MagicMock()
        plugin.update_bridge_vxlan = update_vxlan

        req = _make_req({'bridgeName': 'br0', 'oldVlan': 1, 'newVlan': 2, 'peers': []})
        result = plugin.update_vxlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert update_vxlan.called

    def test_update_vxlan_bridge_updates_interfaces(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.delete_vxlan_fdbs = MagicMock()
        linux.change_vxlan_interface = MagicMock()
        linux.update_bridge_interface_configuration = MagicMock()
        linux.populate_vxlan_fdbs = MagicMock()

        req = _make_req({
            'bridgeName': 'br0',
            'oldVlan': 1,
            'newVlan': 2,
            'peers': ['1.1.1.1'],
            'l2NetworkUuid': 'l2-uuid',
        })
        result = plugin.update_vxlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        linux.delete_vxlan_fdbs.assert_called_once_with(['vxlan1'], ['1.1.1.1'])
        linux.populate_vxlan_fdbs.assert_called_once_with(['vxlan2'], ['1.1.1.1'])

    def test_update_vxlan_bridge_missing_vlan_error(self):
        plugin = _make_plugin()

        req = _make_req({
            'bridgeName': 'br0',
            'oldVlan': None,
            'newVlan': 2,
            'peers': [],
        })
        result = plugin.update_vxlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        assert 'both oldVlan and newVlan' in cast(str, rsp['error'])


@pytest.mark.kvmagent
class TestNetworkPluginCreateVlanBridge:
    def test_create_vlan_bridge_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        setattr(plugin, "_get_interface_mtu", MagicMock(return_value=1500))
        setattr(plugin, "_configure_bridge", MagicMock())
        setattr(plugin, "_configure_bridge_mtu", MagicMock())
        setattr(plugin, "_configure_bridge_learning", MagicMock())
        setattr(plugin, "_enable_bridge_igmp_snooping", MagicMock())
        linux.create_vlan_bridge = MagicMock()
        linux.set_bridge_alias_using_phy_nic_name = MagicMock()
        linux.set_device_uuid_alias = MagicMock()

        req = _make_req({
            'bridgeName': 'br0',
            'physicalInterfaceName': 'eth0',
            'vlan': 100,
            'l2NetworkUuid': 'l2-uuid',
            'disableIptables': False,
            'mtu': 1500,
        })
        result = plugin.create_vlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_create_vlan_bridge_isolated(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        iptables = cast(MagicMock, importlib.import_module("zstacklib.utils.iptables_v2"))

        setattr(plugin, "_get_interface_mtu", MagicMock(return_value=1500))
        linux.create_vlan_bridge = MagicMock()
        linux.set_bridge_alias_using_phy_nic_name = MagicMock()
        linux.set_device_uuid_alias = MagicMock()
        linux.write_file = MagicMock(return_value=True)
        shell_call = MagicMock()
        shell.call = shell_call

        forward_chain = MagicMock()
        isolated_chain = MagicMock()
        filter_table_v4 = MagicMock()
        filter_table_v6 = MagicMock()

        def _get_chain(name: str) -> object | None:
            if name == getattr(iptables, "FORWARD_CHAIN_NAME", "FORWARD"):
                return forward_chain
            return None

        filter_table_v4.get_chain_by_name = MagicMock(side_effect=_get_chain)
        filter_table_v6.get_chain_by_name = MagicMock(side_effect=_get_chain)
        filter_table_v4.add_chain_if_not_exist = MagicMock(return_value=isolated_chain)
        filter_table_v6.add_chain_if_not_exist = MagicMock(return_value=isolated_chain)
        iptables.from_iptables_save = MagicMock(side_effect=[filter_table_v4, filter_table_v6])

        req = _make_req({
            'bridgeName': 'br0',
            'physicalInterfaceName': 'eth0',
            'vlan': 100,
            'l2NetworkUuid': 'l2-uuid',
            'disableIptables': False,
            'mtu': 1500,
            'isolated': True,
        })
        result = plugin.create_vlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        linux.create_vlan_bridge.assert_called_once_with('br0', 'eth0', 100)
        assert shell_call.called

    def test_create_vlan_bridge_zero_vlan_uses_novlan_path(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        iproute = cast(_IprouteModule, cast(object, importlib.import_module("zstacklib.utils.iproute")))
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        linux.create_bridge = MagicMock()
        linux.set_device_uuid_alias = MagicMock()
        linux.set_bridge_alias_using_phy_nic_name = MagicMock()
        linux.write_file = MagicMock(return_value=True)
        iproute.query_link = MagicMock(return_value=SimpleNamespace(mtu=1450))
        iproute.set_link_attribute = MagicMock()
        iproute.set_link_up = MagicMock()
        shell_call = MagicMock()
        shell.call = shell_call

        def _exists(path: str) -> bool:
            return path.endswith('/operstate')

        os_module = cast(_OsModule, cast(object, importlib.import_module("os")))
        os_module.path.exists = MagicMock(side_effect=_exists)
        with patch("builtins.open", new=_make_open("down")):
            req = _make_req({
                'bridgeName': 'br0',
                'physicalInterfaceName': 'eth0',
                'vlan': 0,
                'l2NetworkUuid': 'l2-uuid',
                'disableIptables': False,
                'mtu': 1400,
            })
            result = plugin.create_vlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        linux.create_bridge.assert_called_once_with('br0', 'eth0')


@pytest.mark.kvmagent
class TestNetworkPluginCreateMacVlanEth:
    def test_create_mac_vlan_eth_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        setattr(plugin, "_get_interface_mtu", MagicMock(return_value=1500))
        linux.create_vlan_eth = MagicMock()
        linux.set_device_uuid_alias = MagicMock()

        req = _make_req({
            'physicalInterfaceName': 'eth0',
            'vlan': 100,
            'l2NetworkUuid': 'l2-uuid',
            'mtu': 1500,
        })
        result = plugin.create_mac_vlan_eth(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_create_mac_vlan_eth_uses_larger_mtu(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        setattr(plugin, "_get_interface_mtu", MagicMock(return_value=1600))
        linux.create_vlan_eth = MagicMock()
        linux.set_device_uuid_alias = MagicMock()

        req = _make_req({
            'physicalInterfaceName': 'eth0',
            'vlan': 200,
            'l2NetworkUuid': 'l2-uuid',
            'mtu': 1500,
        })
        result = plugin.create_mac_vlan_eth(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        linux.create_vlan_eth.assert_called_once_with('eth0', 200)


@pytest.mark.kvmagent
class TestNetworkPluginCheckVxlanCidr:
    def test_check_vxlan_cidr_success(self, monkeypatch):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        class _LegacyDict:
            _data: dict[str, str]

            def __init__(self, data: dict[str, str]):
                self._data = data

            def values(self) -> list[str]:
                return list(self._data.values())

            def keys(self) -> list[str]:
                return list(self._data.keys())

        monkeypatch.setattr(linux, "get_nics_by_cidr", MagicMock(return_value=[_LegacyDict({'eth0': '10.0.0.1'})]))
        monkeypatch.setattr(linux, "is_vif_on_bridge", MagicMock(return_value=False))

        req = _make_req({'cidr': '10.0.0.0/24', 'physicalInterfaceName': None, 'vtepip': None})
        result = plugin.check_vxlan_cidr(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert rsp['vtepIp'] == '10.0.0.1'

    def test_check_vxlan_cidr_multiple_interfaces_error(self, monkeypatch):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        class _LegacyDict:
            _data: dict[str, str]

            def __init__(self, data: dict[str, str]):
                self._data = data

            def values(self) -> list[str]:
                return list(self._data.values())

            def keys(self) -> list[str]:
                return list(self._data.keys())

        monkeypatch.setattr(linux, "get_nics_by_cidr", MagicMock(return_value=[
            _LegacyDict({'eth0': '10.0.0.1'}),
            _LegacyDict({'eth1': '10.0.0.1'}),
        ]))
        monkeypatch.setattr(linux, "is_vif_on_bridge", MagicMock(return_value=False))

        req = _make_req({'cidr': '10.0.0.0/24', 'physicalInterfaceName': None, 'vtepip': None})
        result = plugin.check_vxlan_cidr(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        assert 'multiple interfaces' in cast(str, rsp['error'])

    def test_check_vxlan_cidr_filters_by_interface(self, monkeypatch):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        class _LegacyDict:
            _data: dict[str, str]

            def __init__(self, data: dict[str, str]):
                self._data = data

            def values(self) -> list[str]:
                return list(self._data.values())

            def keys(self) -> list[str]:
                return list(self._data.keys())

        monkeypatch.setattr(linux, "get_nics_by_cidr", MagicMock(return_value=[
            _LegacyDict({'eth0': '10.0.0.2'}),
            _LegacyDict({'eth1': '10.0.0.3'}),
        ]))
        monkeypatch.setattr(linux, "is_vif_on_bridge", MagicMock(return_value=False))

        req = _make_req({'cidr': '10.0.0.0/24', 'physicalInterfaceName': 'eth1', 'vtepip': None})
        result = plugin.check_vxlan_cidr(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert rsp['physicalInterfaceName'] == 'eth1'


@pytest.mark.kvmagent
class TestNetworkPluginCreateVxlanBridges:
    def test_create_vxlan_bridges_success(self):
        plugin = _make_plugin()
        create_single = MagicMock()
        plugin.create_single_vxlan_bridge = create_single

        req = _make_req({
            'bridgeCmds': [
                {'bridgeName': 'br0', 'vni': 10, 'vtepIp': '10.0.0.1', 'peers': [], 'mtu': 1450, 'l2NetworkUuid': 'l2-uuid'},
            ]
        })
        result = plugin.create_vxlan_bridges(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert create_single.called

    def test_create_vxlan_bridges_runs_internal(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        iproute = cast(_IprouteModule, cast(object, importlib.import_module("zstacklib.utils.iproute")))

        linux.create_vxlan_interface = MagicMock()
        linux.create_vxlan_bridge = MagicMock()
        linux.set_device_uuid_alias = MagicMock()
        iproute.query_link = MagicMock(return_value=SimpleNamespace(mtu=1450))
        iproute.set_link_attribute = MagicMock()

        req = _make_req({
            'bridgeCmds': [
                {'bridgeName': 'br0', 'vni': 10, 'vtepIp': '10.0.0.1', 'peers': [], 'mtu': 1400, 'l2NetworkUuid': 'l2-uuid'},
                {'bridgeName': 'br1', 'vni': 11, 'vtepIp': '10.0.0.2', 'peers': ['10.0.0.3'], 'mtu': 1400, 'l2NetworkUuid': 'l2-uuid'},
            ]
        })
        result = plugin.create_vxlan_bridges(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert linux.create_vxlan_interface.call_count == 2


@pytest.mark.kvmagent
class TestNetworkPluginDeleteVxlanBridge:
    def test_delete_vxlan_bridge_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.delete_vxlan_bridge = MagicMock()

        req = _make_req({'bridgeName': 'br0', 'vni': 10, 'vtepIp': '10.0.0.1'})
        result = plugin.delete_vxlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_delete_vxlan_bridge_missing_params(self):
        plugin = _make_plugin()

        req = _make_req({'bridgeName': 'br0', 'vni': None, 'vtepIp': None})
        result = plugin.delete_vxlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False


@pytest.mark.kvmagent
class TestNetworkPluginPopulateVxlanFdb:
    def test_populate_vxlan_fdb_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.populate_vxlan_fdbs = MagicMock(return_value=True)

        req = _make_req({'vni': 10, 'peers': ['1.1.1.1']})
        result = plugin.populate_vxlan_fdb(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_populate_vxlan_fdb_failure_sets_error(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.populate_vxlan_fdbs = MagicMock(return_value=False)

        req = _make_req({'vni': 10, 'peers': ['1.1.1.1']})
        result = plugin.populate_vxlan_fdb(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        assert 'error on populate fdb' in cast(str, rsp['error'])


@pytest.mark.kvmagent
class TestNetworkPluginPopulateVxlanFdbs:
    def test_populate_vxlan_fdbs_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.get_interfs_from_uuids = MagicMock(return_value=['vxlan10'])
        linux.populate_vxlan_fdbs = MagicMock(return_value=True)

        req = _make_req({'networkUuids': ['net-1'], 'peers': ['1.1.1.1']})
        result = plugin.populate_vxlan_fdbs(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_populate_vxlan_fdbs_no_interfaces(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.get_interfs_from_uuids = MagicMock(return_value=[])
        linux.populate_vxlan_fdbs = MagicMock(return_value=True)

        req = _make_req({'networkUuids': ['net-1'], 'peers': ['1.1.1.1']})
        result = plugin.populate_vxlan_fdbs(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        linux.populate_vxlan_fdbs.assert_not_called()


@pytest.mark.kvmagent
class TestNetworkPluginDeleteVxlanFdbs:
    def test_delete_vxlan_fdbs_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.get_interfs_from_uuids = MagicMock(return_value=['vxlan10'])
        linux.delete_vxlan_fdbs = MagicMock(return_value=True)

        req = _make_req({'networkUuids': ['net-1'], 'peers': ['1.1.1.1']})
        result = plugin.delete_vxlan_fdbs(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_delete_vxlan_fdbs_failure(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.get_interfs_from_uuids = MagicMock(return_value=['vxlan10'])
        linux.delete_vxlan_fdbs = MagicMock(return_value=False)

        req = _make_req({'networkUuids': ['net-1'], 'peers': ['1.1.1.1']})
        result = plugin.delete_vxlan_fdbs(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        assert 'error on delete fdb' in cast(str, rsp['error'])


@pytest.mark.kvmagent
class TestNetworkPluginSetBridgeRouterPort:
    def test_set_bridge_router_port_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.write_file = MagicMock()

        req = _make_req({'nicNames': ['vnic0'], 'enable': True})
        result = plugin.set_bridge_router_port(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert linux.write_file.called

    def test_set_bridge_router_port_disable(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.write_file = MagicMock()

        req = _make_req({'nicNames': ['vnic0'], 'enable': False})
        result = plugin.set_bridge_router_port(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        linux.write_file.assert_called_once_with(
            '/sys/devices/virtual/net/vnic0/brport/multicast_router', '1'
        )


@pytest.mark.kvmagent
class TestNetworkPluginDeleteNovlanBridge:
    def test_delete_novlan_bridge_success(self):
        plugin = _make_plugin()
        delete_bridge = cast(MagicMock, importlib.import_module("kvmagent.plugins.network_plugin"))
        delete_bridge.del_novlan_bridge = MagicMock()

        req = _make_req({'bridgeName': 'br0', 'physicalInterfaceName': 'eth0'})
        result = plugin.delete_novlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_delete_novlan_bridge_error(self):
        plugin = _make_plugin()
        delete_bridge = cast(MagicMock, importlib.import_module("kvmagent.plugins.network_plugin"))
        delete_bridge.del_novlan_bridge = MagicMock(side_effect=Exception("fail"))

        req = _make_req({'bridgeName': 'br0', 'physicalInterfaceName': 'eth0'})
        result = plugin.delete_novlan_bridge(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        assert 'failed to delete bridge' in cast(str, rsp['error'])


@pytest.mark.kvmagent
class TestNetworkPluginDeleteMacvlanVlanEth:
    def test_delete_macvlan_vlan_eth_success(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))
        linux.delete_vlan_eth = MagicMock()

        req = _make_req({'physicalInterfaceName': 'eth0', 'vlan': 100})
        result = plugin.delete_macvlan_vlan_eth(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True

    def test_delete_macvlan_vlan_eth_error(self):
        plugin = _make_plugin()
        linux = cast(_LinuxModule, cast(object, importlib.import_module("zstacklib.utils.linux")))

        linux.delete_vlan_eth = MagicMock(side_effect=Exception("fail"))

        req = _make_req({'physicalInterfaceName': 'eth0', 'vlan': 100})
        result = plugin.delete_macvlan_vlan_eth(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is False
        assert 'failed to delete vlan eth' in cast(str, rsp['error'])


@pytest.mark.kvmagent
class TestNetworkPluginAttachNicToIpsetPath:
    def test_attach_nic_to_ipset_path_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        shell_call = MagicMock()
        shell.call = shell_call

        req = _make_req({
            'l2MacMap': {'l2-1': ['aa:bb:cc:dd:ee:ff']},
            'interfaceMap': {'l2-1': 'eth0'},
            'vlanMap': {'l2-1': 100},
        })
        result = plugin.attach_nic_to_ipset_path(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert shell_call.called

    def test_attach_nic_to_ipset_path_no_macs(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        shell_call = MagicMock()
        shell.call = shell_call

        req = _make_req({
            'l2MacMap': None,
            'interfaceMap': None,
            'vlanMap': None,
        })
        result = plugin.attach_nic_to_ipset_path(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        shell_call.assert_not_called()


@pytest.mark.kvmagent
class TestNetworkPluginDetachNicToIpsetPath:
    def test_detach_nic_to_ipset_path_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        iproute = cast(_IprouteModule, cast(object, importlib.import_module("zstacklib.utils.iproute")))

        shell_call = MagicMock()
        shell.call = shell_call
        iproute.config_link_isolated = MagicMock()

        req = _make_req({
            'l2MacMap': {'l2-1': ['aa:bb:cc:dd:ee:ff']},
            'interfaceMap': {'l2-1': 'eth0'},
            'vlanMap': {'l2-1': 100},
            'nicList': ['vnic0'],
        })
        result = plugin.detach_nic_to_ipset_path(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        iproute.config_link_isolated.assert_called()

    def test_detach_nic_to_ipset_path_no_macs(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))
        iproute = cast(_IprouteModule, cast(object, importlib.import_module("zstacklib.utils.iproute")))

        shell_call = MagicMock()
        shell.call = shell_call
        iproute.config_link_isolated = MagicMock()

        req = _make_req({
            'l2MacMap': None,
            'interfaceMap': None,
            'vlanMap': None,
            'nicList': [],
        })
        result = plugin.detach_nic_to_ipset_path(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        shell_call.assert_not_called()
        iproute.config_link_isolated.assert_not_called()


@pytest.mark.kvmagent
class TestNetworkPluginSyncIpsetPath:
    def test_sync_ipset_path_success(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        shell_call = MagicMock()
        shell.call = shell_call
        list_cmd = MagicMock()
        list_cmd.return_code = 0
        shell.ShellCmd = MagicMock(return_value=list_cmd)

        req = _make_req({
            'l2MacMap': {'l2-1': ['aa:bb:cc:dd:ee:ff']},
            'interfaceMap': {'l2-1': 'eth0'},
            'vlanMap': {'l2-1': 100},
        })
        result = plugin.sync_ipset_path(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert shell_call.called

    def test_sync_ipset_path_existing_list(self):
        plugin = _make_plugin()
        shell = cast(_ShellModule, cast(object, importlib.import_module("zstacklib.utils.shell")))

        shell_call = MagicMock()
        shell.call = shell_call
        list_cmd = MagicMock()
        list_cmd.return_code = 0
        shell.ShellCmd = MagicMock(return_value=list_cmd)

        req = _make_req({
            'l2MacMap': {'l2-1': ['aa:bb:cc:dd:ee:ff']},
            'interfaceMap': {'l2-1': 'eth0'},
            'vlanMap': {'l2-1': 100},
        })
        result = plugin.sync_ipset_path(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert any('ipset destroy isolated_eth0.100' in call.args[0] for call in shell_call.mock_calls)
