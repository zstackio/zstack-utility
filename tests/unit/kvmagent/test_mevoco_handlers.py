from __future__ import annotations
# pyright: reportAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false, reportMissingTypeArgument=false, reportPrivateUsage=false, reportAttributeAccessIssue=false, reportGeneralTypeIssues=false, reportReturnType=false, reportSelfClsParameterName=false, reportUnusedVariable=false, reportUnusedCallResult=false

import importlib
import json
import os
import pytest
import sys
import tempfile
from typing import Callable, Protocol, cast
from unittest.mock import MagicMock, patch


class _HttpModule(Protocol):
    REQUEST_BODY: str
    REQUEST_HEADER: str


class _MevocoPluginProto(Protocol):
    config: dict[str, object]
    DNSMASQ_CONF_FOLDER: str
    DNSMASQ_LOG_LOGROTATE_PATH: str
    USERDATA_ROOT: str
    _apply_dns_forward: Callable[..., None]
    _apply_userdata_restart_httpd: Callable[..., None]
    _apply_userdata_vmdata: Callable[..., None]
    _apply_userdata_xtables: Callable[..., None]
    _del_bridge_fdb_entry_for_inner_dev: Callable[..., None]
    _delete_dhcp: Callable[..., None]
    _delete_dhcp4: Callable[..., None]
    _delete_dhcp6: Callable[..., None]
    _refresh_dnsmasq: Callable[..., None]
    _batch_update_configurations: Callable[..., dict[str, int]]
    _normalize_dhcp_records: Callable[..., tuple[list[object], dict[str, set[object]]]]
    _replace_config_file: Callable[[str, str], bool]
    do_apply_dhcp: Callable[..., None]
    _make_conf_path: Callable[..., tuple[str, str, str, str, str]]
    _remove_dns_forward: Callable[..., None]
    _restart_dnsmasq: Callable[..., None]
    restore_ebtables_chain_except_kvmagent: Callable[[], None]
    userData_vms: dict[str, list[str]]

    def arping_dhcp_namespace(self, req: dict[str, object]) -> str: ...
    def apply_dhcp(self, req: dict[str, object]) -> str: ...
    def apply_userdata(self, req: dict[str, object]) -> str: ...
    def batch_apply_dhcp(self, req: dict[str, object]) -> str: ...
    def batch_apply_userdata(self, req: dict[str, object]) -> str: ...
    def batch_prepare_dhcp(self, req: dict[str, object]) -> str: ...
    def delete_dhcp_namespace(self, req: dict[str, object]) -> str: ...
    def setup_dns_forward(self, req: dict[str, object]) -> str: ...
    def flush_dhcp_namespace(self, req: dict[str, object]) -> str: ...
    def remove_dns_forward(self, req: dict[str, object]) -> str: ...
    def prepare_dhcp(self, req: dict[str, object]) -> str: ...
    def connect(self, req: dict[str, object]) -> str: ...
    def reset_default_gateway(self, req: dict[str, object]) -> str: ...
    def cleanup_userdata(self, req: dict[str, object]) -> str: ...
    def release_userdata(self, req: dict[str, object]) -> str: ...
    def release_dhcp(self, req: dict[str, object]) -> str: ...


class _MevocoModule(Protocol):
    iproute: object
    ip: object
    linux: object
    http: object
    jsonobject: object
    bash_errorout: Callable[..., object]
    bash_o: Callable[..., str]
    bash_r: Callable[..., int]
    bash_roe: Callable[..., tuple[int, str, str]]
    in_bash: Callable[[Callable[..., object]], Callable[..., object]]
    lock: "_LockModule"
    getDhcpEbtableChainName: Callable[[str], str]
    EBTABLES_CMD: str
    ReleaseDhcpRsp: type[object]
    Mevoco: type[_MevocoPluginProto]


class _LockModule(Protocol):
    lock: Callable[..., object]
    file_lock: Callable[..., Callable[[Callable[..., object]], Callable[..., object]]]

from collections.abc import MutableSet

collections = importlib.import_module("collections")
if not hasattr(collections, "MutableSet"):
    setattr(collections, "MutableSet", MutableSet)

_ = sys.modules.setdefault("plugin", MagicMock())
_ = sys.modules.setdefault("traceable_shell", MagicMock())
_ = sys.modules.setdefault("report", MagicMock())
_ = sys.modules.setdefault("linux", MagicMock())
_ = sys.modules.setdefault("pyparsing", MagicMock())

try:
    mevoco = cast(
        _MevocoModule,
        cast(object, importlib.import_module("kvmagent.plugins.mevoco")),
    )
except (ImportError, ModuleNotFoundError) as e:
    pytest.skip(f"Cannot import mevoco: {e}", allow_module_level=True)


def _make_req(body_dict: dict[str, object] | None = None) -> dict[str, object]:
    http = cast(_HttpModule, cast(object, importlib.import_module("zstacklib.utils.http")))
    body = json.dumps(body_dict or {})
    return {http.REQUEST_BODY: body, http.REQUEST_HEADER: {}}


def _make_plugin() -> _MevocoPluginProto:
    lock_mod = cast(_LockModule, cast(object, importlib.import_module("zstacklib.utils.lock")))
    plugin_mod = cast(object, importlib.import_module("zstacklib.utils.plugin"))

    from tests.conftest import passthrough_lock

    _orig_lock = getattr(lock_mod, "lock", None)
    _orig_completetask = getattr(plugin_mod, "completetask", None)
    lock_mod.lock = passthrough_lock
    setattr(plugin_mod, "completetask", passthrough_lock)

    module = cast(object, importlib.reload(importlib.import_module("kvmagent.plugins.mevoco")))

    # Restore originals so module-level attrs don't leak across tests
    if _orig_lock is not None:
        lock_mod.lock = _orig_lock
    if _orig_completetask is not None:
        setattr(plugin_mod, "completetask", _orig_completetask)

    setattr(module, "http", importlib.import_module("zstacklib.utils.http"))
    setattr(module, "linux", importlib.import_module("zstacklib.utils.linux"))
    setattr(module, "bash", importlib.import_module("zstacklib.utils.bash"))
    setattr(module, "bash_o", lambda _cmd: "")
    plugin = mevoco.Mevoco.__new__(mevoco.Mevoco)
    plugin.config = {}
    return plugin


def _load_rsp(result: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(result))


class _IterDict(dict[str, object]):
    def iteritems(self):
        return self.items()


class _Obj:
    def __init__(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)

    def hasattr(self, name: str) -> bool:
        return hasattr(self, name)


class _BashResult:
    _rc: int
    _out: str
    _err: str

    def __init__(self, rc: int, out: str = "", err: str = "") -> None:
        self._rc = rc
        self._out = out
        self._err = err

    def __iter__(self):
        return iter((self._rc, self._out, self._err))

    def __bool__(self) -> bool:
        return self._rc != 0

    def __eq__(self, other: object) -> bool:  # pyright: ignore[reportImplicitOverride]
        return isinstance(other, _BashResult) and self._rc == other._rc


def _ensure_http() -> None:
    setattr(mevoco, "http", importlib.import_module("zstacklib.utils.http"))


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
    mevoco_mod = sys.modules.get("kvmagent.plugins.mevoco")
    snapshots = _snapshot_modules(
        importlib.import_module("zstacklib.utils.linux"),
        importlib.import_module("zstacklib.utils.shell"),
        importlib.import_module("zstacklib.utils.iproute"),
        importlib.import_module("zstacklib.utils.ip"),
        importlib.import_module("zstacklib.utils.ovs"),
        importlib.import_module("zstacklib.utils.thread"),
        mevoco_mod,
    )
    yield
    _restore_modules(snapshots)


@pytest.mark.kvmagent
class TestMevocoSetupDnsForward:
    def test_setup_dns_forward_success(self):
        plugin = _make_plugin()
        _ensure_http()
        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.mkdir = MagicMock()
        linux.touch_file = MagicMock()

        with tempfile.TemporaryDirectory() as temp_dir:
            plugin.DNSMASQ_CONF_FOLDER = temp_dir
            plugin.DNSMASQ_LOG_LOGROTATE_PATH = os.path.join(temp_dir, "logrotate")
            setattr(mevoco, "bash_o", MagicMock(return_value=""))
            with patch("os.path.exists", return_value=False), \
                    patch("os.chmod", MagicMock()), \
                    patch("os.fsync", MagicMock()), \
                    patch("builtins.open", MagicMock()) as open_mock:
                setattr(plugin, "_restart_dnsmasq", MagicMock())
                setattr(mevoco, "bash_errorout", MagicMock())

                req = _make_req({'nameSpace': 'ns1', 'mac': 'fa:16:3e:00:00:01', 'dns': '8.8.8.8', 'wrongDns': ['1.1.1.1']})
                result = plugin.setup_dns_forward(req)
                rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert open_mock.called


@pytest.mark.kvmagent
class TestMevocoRemoveDnsForward:
    def test_remove_dns_forward_success(self):
        plugin = _make_plugin()
        _ensure_http()
        setattr(
            plugin,
            "_make_conf_path",
            MagicMock(return_value=('/tmp/conf', '/tmp/dhcp', '/tmp/dns', '/tmp/opt', '/tmp/log')),
        )
        setattr(plugin, "_restart_dnsmasq", MagicMock())
        setattr(mevoco, "bash_errorout", MagicMock())

        req = _make_req({'nameSpace': 'ns1', 'mac': 'fa:16:3e:00:00:01'})
        result = plugin.remove_dns_forward(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert cast(MagicMock, plugin._restart_dnsmasq).called


@pytest.mark.kvmagent
class TestMevocoConnect:
    def test_connect_success(self):
        plugin = _make_plugin()
        setattr(mevoco, "bash_o", MagicMock(return_value='*filter\n:INPUT ACCEPT\n:FORWARD ACCEPT\n:OUTPUT ACCEPT'))
        with patch("tempfile.mkstemp", return_value=(3, "/tmp/ebt")), \
                patch("os.fdopen", MagicMock()), \
                patch("os.remove", MagicMock()):
            req = _make_req()
            result = plugin.connect(req)
            rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestMevocoDeleteDhcpNamespace:
    def test_delete_dhcp_namespace_success(self):
        plugin = _make_plugin()
        _ensure_http()
        setattr(mevoco, "bash_roe", MagicMock(return_value=_BashResult(0, "eth0\n", "")))
        setattr(mevoco, "bash_r", MagicMock(return_value=0))
        iproute = cast(MagicMock, importlib.import_module("zstacklib.utils.iproute"))
        iproute.IpNetnsShell.get_netns_id = MagicMock(return_value="9")
        iproute.IpNetnsShell.return_value.get_mac = MagicMock(return_value="aa:bb:cc:dd:ee:ff")
        iproute.del_fdb_entry = MagicMock()

        req = _make_req({'bridgeName': 'br0', 'namespaceName': 'ns-delete'})
        result = plugin.delete_dhcp_namespace(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        iproute.del_fdb_entry.assert_called_once_with("eth0", "aa:bb:cc:dd:ee:ff")


@pytest.mark.kvmagent
class TestMevocoFlushDhcpNamespace:
    def test_flush_dhcp_namespace_success(self):
        plugin = _make_plugin()
        _ensure_http()
        iproute = cast(MagicMock, importlib.import_module("zstacklib.utils.iproute"))
        iproute.IpNetnsShell.return_value.get_ip_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.get_mac = MagicMock(return_value="aa:bb:cc:dd:ee:ff")
        iproute.IpNetnsShell.return_value.get_link_local6_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.set_link_up = MagicMock()
        iproute.IpNetnsShell.return_value.add_ip_address = MagicMock()
        iproute.IpNetnsShell.return_value.flush_ip_address = MagicMock()

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.is_network_device_existing = MagicMock(return_value=True)
        linux.netmask_to_cidr = MagicMock(return_value=24)

        setattr(mevoco, "bash_r", MagicMock(return_value=0))
        setattr(mevoco, "bash_roe", MagicMock(return_value=(0, "eth0\n", "")))

        req = _make_req({'bridgeName': 'br1', 'namespaceName': 'ns-flush'})
        result = plugin.flush_dhcp_namespace(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestMevocoArpingDhcpNamespace:
    def test_arping_dhcp_namespace_success(self):
        plugin = _make_plugin()
        _ensure_http()
        iproute = cast(MagicMock, importlib.import_module("zstacklib.utils.iproute"))
        iproute.IpNetnsShell.list_netns = MagicMock(return_value=[])
        iproute.IpNetnsShell.return_value.get_mac = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.add_netns = MagicMock()
        iproute.IpNetnsShell.return_value.add_link = MagicMock()
        iproute.IpNetnsShell.return_value.set_link_up = MagicMock()
        iproute.IpNetnsShell.return_value.add_ip_address = MagicMock()
        iproute.IpNetnsShell.return_value.get_ip_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.get_userdata_ip_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.get_link_local6_address = MagicMock(return_value=None)

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.is_network_device_existing = MagicMock(return_value=False)
        linux.netmask_to_cidr = MagicMock(return_value=24)

        setattr(mevoco, "bash_r", MagicMock(return_value=0))
        setattr(mevoco, "bash_ro", MagicMock(return_value=(0, "0")))

        arping_output = "Unicast reply from 192.168.0.10 [AC:1F:6B:EE:87:B2] 0.641ms"
        setattr(mevoco, "bash_roe", MagicMock(return_value=(0, arping_output, "")))
        ip_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.ip"))
        ip_mod.get_namespace_id = MagicMock(return_value="5")

        req = _make_req({'bridgeName': 'br2', 'namespaceName': 'ns-arp', 'targetIps': ['192.168.0.10']})
        result = plugin.arping_dhcp_namespace(req)
        rsp = _load_rsp(result)

        result_map = cast(dict[str, list[str]], rsp['result'])
        assert result_map['192.168.0.10'] == ['AC:1F:6B:EE:87:B2']


@pytest.mark.kvmagent
class TestMevocoPrepareDhcp:
    def test_prepare_dhcp_success(self):
        plugin = _make_plugin()
        _ensure_http()
        with patch.object(mevoco.jsonobject, "dumps", side_effect=lambda obj: json.dumps({"success": True})):
            iproute = cast(MagicMock, importlib.import_module("zstacklib.utils.iproute"))
            iproute.IpNetnsShell.get_netns_id = MagicMock(return_value="42")
            iproute.IpNetnsShell.return_value.get_ip_address = MagicMock(side_effect=["192.168.0.254", "fd00::2"])
            iproute.IpNetnsShell.return_value.get_mac = MagicMock(return_value=None)
            iproute.IpNetnsShell.return_value.get_link_local6_address = MagicMock(return_value=None)
            iproute.IpNetnsShell.return_value.add_link = MagicMock()
            iproute.IpNetnsShell.return_value.add_netns = MagicMock()
            iproute.IpNetnsShell.return_value.add_ip_address = MagicMock()
            iproute.IpNetnsShell.return_value.flush_ip_address = MagicMock()
            iproute.IpNetnsShell.return_value.set_link_up = MagicMock()
            iproute.add_link = MagicMock()
            iproute.set_link_attribute = MagicMock()
            iproute.set_link_up = MagicMock()

            linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
            linux.is_network_device_existing = MagicMock(return_value=False)
            linux.netmask_to_cidr = MagicMock(return_value=24)
            linux.get_bridge_phy_nic_name_from_alias = MagicMock(return_value="eth0")

            setattr(mevoco, "bash_r", MagicMock(return_value=1))
            setattr(mevoco, "bash_roe", MagicMock(return_value=(0, "", "")))
            ovs = cast(MagicMock, importlib.import_module("zstacklib.utils.ovs"))
            ovs.getOvsCtl = MagicMock(return_value=MagicMock(listBrs=MagicMock(return_value=[])))
            ip_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.ip"))
            ip_mod.get_link_local_address = MagicMock(return_value="fe80::1")

            req = _make_req({
                'bridgeName': 'br0',
                'vlanId': 'vlan10',
                'dhcpServerIp': '192.168.0.1',
                'dhcp6ServerIp': 'fd00::1',
                'dhcpNetmask': '255.255.255.0',
                'namespaceName': 'ns-prepare',
                'ipVersion': 4,
                'prefixLen': 64,
                'addressMode': 'stateful',
            })
            result = plugin.prepare_dhcp(req)
            rsp = _load_rsp(result)

            assert rsp['success'] is True


@pytest.mark.kvmagent
class TestMevocoBatchPrepareDhcp:
    def test_batch_prepare_dhcp_success(self):
        plugin = _make_plugin()
        _ensure_http()
        with patch.object(mevoco.jsonobject, "dumps", side_effect=lambda obj: json.dumps({"success": True})):
            iproute = cast(MagicMock, importlib.import_module("zstacklib.utils.iproute"))
            iproute.IpNetnsShell.return_value.get_ip_address = MagicMock(side_effect=["192.168.1.254", "fd00::9", None, None])
            iproute.IpNetnsShell.return_value.get_mac = MagicMock(return_value=None)
            iproute.IpNetnsShell.return_value.get_link_local6_address = MagicMock(return_value=None)
            iproute.IpNetnsShell.return_value.add_link = MagicMock()
            iproute.IpNetnsShell.return_value.add_netns = MagicMock()
            iproute.IpNetnsShell.return_value.add_ip_address = MagicMock()
            iproute.IpNetnsShell.return_value.flush_ip_address = MagicMock()
            iproute.IpNetnsShell.return_value.set_link_up = MagicMock()
            iproute.add_link = MagicMock()
            iproute.set_link_attribute = MagicMock()
            iproute.set_link_up = MagicMock()

            ip_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.ip"))
            ip_mod.get_namespace_id = MagicMock(return_value="7")

            linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
            linux.is_network_device_existing = MagicMock(return_value=False)
            linux.netmask_to_cidr = MagicMock(return_value=24)
            linux.get_bridge_phy_nic_name_from_alias = MagicMock(return_value="eth0")

            setattr(mevoco, "bash_r", MagicMock(return_value=1))
            setattr(mevoco, "bash_roe", MagicMock(return_value=(0, "", "")))
            ovs = cast(MagicMock, importlib.import_module("zstacklib.utils.ovs"))
            ovs.getOvsCtl = MagicMock(return_value=MagicMock(listBrs=MagicMock(return_value=[])))
            ip_mod.get_link_local_address = MagicMock(return_value="fe80::1")

            req = _make_req({
                'dhcpInfos': [
                    {
                        'bridgeName': 'br0',
                        'vlanId': 'vlan10',
                        'dhcpServerIp': '192.168.1.1',
                        'dhcp6ServerIp': 'fd00::1',
                        'dhcpNetmask': '255.255.255.0',
                        'namespaceName': 'ns-batch-1',
                        'ipVersion': 4,
                        'prefixLen': 64,
                        'addressMode': 'stateful',
                    },
                    {
                        'bridgeName': 'br1',
                        'vlanId': 'vxlan11',
                        'dhcpServerIp': '192.168.2.1',
                        'dhcp6ServerIp': 'fd00::2',
                        'dhcpNetmask': '255.255.255.0',
                        'namespaceName': 'ns-batch-2',
                        'ipVersion': 6,
                        'prefixLen': 64,
                        'addressMode': 'stateful',
                    },
                ]
            })
            result = plugin.batch_prepare_dhcp(req)
            rsp = _load_rsp(result)

            assert rsp['success'] is True


@pytest.mark.kvmagent
class TestMevocoResetDefaultGateway:
    def test_reset_default_gateway_success(self):
        plugin = _make_plugin()
        tmp_file = tempfile.NamedTemporaryFile(delete=False)
        tmp_file.close()
        try:
            setattr(
                plugin,
                "_make_conf_path",
                MagicMock(return_value=("/tmp/conf", "/tmp/dhcp", "/tmp/dns", tmp_file.name, "/tmp/log")),
            )
            setattr(plugin, "_refresh_dnsmasq", MagicMock())
            setattr(mevoco.linux, "delete_lines_from_file", MagicMock())

            req = _make_req({
                'namespaceNameOfGatewayToRemove': 'ns-remove',
                'macOfGatewayToRemove': 'fa:16:3e:00:00:01',
                'gatewayToRemove': '192.168.0.1',
                'namespaceNameOfGatewayToAdd': 'ns-add',
                'macOfGatewayToAdd': 'fa:16:3e:00:00:02',
                'gatewayToAdd': '192.168.0.2',
            })
            result = plugin.reset_default_gateway(req)
            rsp = _load_rsp(result)

            assert rsp['success'] is True
            assert cast(MagicMock, plugin._refresh_dnsmasq).call_count == 2
        finally:
            os.unlink(tmp_file.name)


@pytest.mark.kvmagent
class TestMevocoApplyDhcp:
    def test_apply_dhcp_success(self):
        plugin = _make_plugin()
        _ensure_http()
        dhcp_entry = _Obj(
            namespaceName='ns-apply',
            bridgeName='br0',
            mac='fa:16:3e:00:00:01',
            ip='192.168.0.2',
            ip6=None,
            ipVersion=4,
            nicType='VNIC',
            dns=['8.8.8.8'],
            dns6=None,
            dnsDomain=None,
            gateway='192.168.0.1',
            netmask='255.255.255.0',
            hostname='vm',
            mtu=1500,
            isDefaultL3Network=True,
            hostRoutes=[],
            vmMultiGateway=False,
            enableRa=False,
        )
        cmd = _Obj(dhcp=[dhcp_entry], rebuild=False)
        with patch.object(mevoco.jsonobject, "loads", return_value=cmd):
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch.object(mevoco.jsonobject, "dumps", side_effect=lambda obj: json.dumps({"success": True})):
                    original_do_apply = mevoco.Mevoco.do_apply_dhcp
                    def _wrapped_do_apply(namespace_dhcp: dict[str, object], rebuild: bool) -> None:
                        return original_do_apply(plugin, _IterDict(namespace_dhcp), rebuild)
                    plugin.do_apply_dhcp = _wrapped_do_apply

                    linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
                    linux.touch_file = MagicMock()
                    linux.mkdir = MagicMock()

                    plugin.DNSMASQ_CONF_FOLDER = temp_dir
                    plugin.DNSMASQ_LOG_LOGROTATE_PATH = os.path.join(temp_dir, "logrotate")
                    setattr(mevoco, "bash_r", MagicMock(return_value=1))
                    setattr(mevoco, "bash_roe", MagicMock(return_value=(0, "", "")))
                    setattr(mevoco, "bash_o", MagicMock(return_value=""))
                    setattr(mevoco, "bash_errorout", MagicMock())

                    shell = cast(MagicMock, importlib.import_module("zstacklib.utils.shell"))
                    shell.call = MagicMock(return_value="1")

                    linux.find_process_by_cmdline = MagicMock(return_value=None)
                    linux.find_all_process_by_cmdline = MagicMock(return_value=[])
                    linux.wait_callback_success = MagicMock(return_value=True)
                    linux.kill_process = MagicMock()

                    with patch("os.path.exists", return_value=False), \
                            patch("builtins.open", MagicMock()):
                        req = _make_req({'dhcp': [{'namespaceName': 'ns-apply'}], 'rebuild': False})
                        result = plugin.apply_dhcp(req)
                        rsp = _load_rsp(result)

        assert rsp['success'] is True
        # bash_errorout is legitimately called for network setup (brctl/iptables)


@pytest.mark.kvmagent
class TestMevocoBatchApplyDhcp:
    def test_batch_apply_dhcp_success(self):
        plugin = _make_plugin()
        _ensure_http()
        dhcp_entry = _Obj(
            namespaceName='ns-batch',
            bridgeName='br1',
            mac='fa:16:3e:00:00:02',
            ip='192.168.0.3',
            ip6='fd00::2',
            ipVersion=46,
            nicType='VF',
            dns=['8.8.4.4'],
            dns6=['fd00::1'],
            dnsDomain='example.com',
            gateway='192.168.0.1',
            netmask='255.255.255.0',
            hostname='vm2',
            mtu=None,
            isDefaultL3Network=False,
            hostRoutes=[_Obj(prefix='10.0.0.0/24', nexthop='192.168.0.1')],
            vmMultiGateway=True,
            enableRa=True,
            firstIp='fd00::100',
            endIp='fd00::200',
            prefixLength=64,
        )
        cmd = _Obj(dhcpInfos=[_Obj(dhcp=[dhcp_entry])], rebuild=True)
        with patch.object(mevoco.jsonobject, "loads", return_value=cmd):
            with tempfile.TemporaryDirectory() as temp_dir:
                with patch.object(mevoco.jsonobject, "dumps", side_effect=lambda obj: json.dumps({"success": True})):
                    original_do_apply = mevoco.Mevoco.do_apply_dhcp
                    def _wrapped_do_apply(namespace_dhcp: dict[str, object], rebuild: bool) -> None:
                        return original_do_apply(plugin, _IterDict(namespace_dhcp), rebuild)
                    plugin.do_apply_dhcp = _wrapped_do_apply

                    linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
                    linux.touch_file = MagicMock()
                    linux.mkdir = MagicMock()

                    plugin.DNSMASQ_CONF_FOLDER = temp_dir
                    plugin.DNSMASQ_LOG_LOGROTATE_PATH = os.path.join(temp_dir, "logrotate")
                    setattr(mevoco, "bash_r", MagicMock(return_value=1))
                    setattr(mevoco, "bash_roe", MagicMock(return_value=(0, "", "")))
                    setattr(mevoco, "bash_o", MagicMock(return_value="192.168.0.1"))
                    setattr(mevoco, "bash_errorout", MagicMock())

                    shell = cast(MagicMock, importlib.import_module("zstacklib.utils.shell"))
                    shell.call = MagicMock(return_value="1")

                    linux.find_process_by_cmdline = MagicMock(return_value=None)
                    linux.find_all_process_by_cmdline = MagicMock(return_value=[])
                    linux.wait_callback_success = MagicMock(return_value=True)
                    linux.kill_process = MagicMock()

                    with patch("os.path.exists", return_value=False), \
                            patch("builtins.open", MagicMock()):
                        req = _make_req({'dhcpInfos': [{'dhcp': [{'namespaceName': 'ns-batch'}]}], 'rebuild': True})
                        result = plugin.batch_apply_dhcp(req)
                        rsp = _load_rsp(result)

        assert rsp['success'] is True
        # bash_errorout is legitimately called for network setup (brctl/iptables)


@pytest.mark.kvmagent
class TestMevocoApplyUserdata:
    def test_apply_userdata_success(self):
        plugin = _make_plugin()
        _ensure_http()
        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        iproute = cast(MagicMock, importlib.import_module("zstacklib.utils.iproute"))
        shell = cast(MagicMock, importlib.import_module("zstacklib.utils.shell"))
        ip_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.ip"))

        linux.is_network_device_existing = MagicMock(return_value=False)
        linux.mkdir = MagicMock()
        linux.rm_file_force = MagicMock()
        linux.find_all_process_by_cmdline = MagicMock(return_value=[])
        linux.find_process_by_cmdline = MagicMock(return_value=None)
        linux.wait_callback_success = MagicMock(return_value=True)
        plugin._erase_configurations = MagicMock()
        plugin._restart_dnsmasq = MagicMock()
        linux.kill_process = MagicMock()
        iproute.IpNetnsShell.list_netns = MagicMock(return_value=[])
        iproute.IpNetnsShell.return_value.get_mac = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.add_netns = MagicMock()
        iproute.IpNetnsShell.return_value.add_link = MagicMock()
        iproute.IpNetnsShell.return_value.set_link_up = MagicMock()
        iproute.IpNetnsShell.return_value.get_userdata_ip_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.get_ip_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.add_ip_address = MagicMock()
        iproute.add_link = MagicMock()
        iproute.set_link_attribute = MagicMock()
        iproute.set_link_up = MagicMock()
        iproute.add_address = MagicMock()
        iproute.query_addresses = MagicMock(return_value=[])
        setattr(mevoco, "bash_r", MagicMock(return_value=1))
        setattr(mevoco, "bash_ro", MagicMock(return_value=(0, "0")))
        setattr(mevoco, "bash_roe", MagicMock(return_value=(0, "", "")))
        setattr(mevoco, "bash_errorout", MagicMock())
        shell.call = MagicMock(return_value="1")
        ip_mod.get_namespace_id = MagicMock(return_value="5")
        ip_mod.removeZeroFromMacAddress = MagicMock(side_effect=lambda x: x)
        ip_mod.IpAddress = MagicMock(return_value=MagicMock(toCidr=lambda _: "192.168.0.0/24"))

        to = _Obj(
            bridgeName='br0',
            namespaceName='ns',
            vlanId='vlan10',
            l3NetworkUuid='l3-uuid',
            vmIp='10.0.0.2',
            netmask='255.255.255.0',
            port=80,
            metadata=_Obj(vmUuid='vm-uuid', vmHostname='vm', regionName='region', mac='fa:16:3e:00:00:01', vpcId='vpc', dnsServersIp='8.8.8.8'),
            userdataList=['data'],
            agentConfig=_Obj(pvpanic='enable'),
            networkInterfaces=[_Obj(macAddress='fa:16:3e:00:00:01', gateway='10.0.0.1', netmask='255.255.255.0', ip='10.0.0.2')],
        )
        cmd = _Obj(userdata=to)
        with patch.object(mevoco.jsonobject, "loads", return_value=cmd):
            with tempfile.TemporaryDirectory() as temp_dir:
                plugin.USERDATA_ROOT = temp_dir
                with patch.object(mevoco.jsonobject, "dumps", side_effect=lambda obj: json.dumps({"success": True})):
                    with patch("os.path.exists", return_value=False), \
                            patch("builtins.open", MagicMock()):
                        req = _make_req({'userdata': {'bridgeName': 'br0', 'namespaceName': 'ns', 'vlanId': 10}})
                        result = plugin.apply_userdata(req)
                        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestMevocoBatchApplyUserdata:
    def test_batch_apply_userdata_success(self):
        plugin = _make_plugin()
        _ensure_http()
        plugin.userData_vms = {}

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        iproute = cast(MagicMock, importlib.import_module("zstacklib.utils.iproute"))
        shell = cast(MagicMock, importlib.import_module("zstacklib.utils.shell"))
        ip_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.ip"))

        linux.is_network_device_existing = MagicMock(return_value=False)
        linux.mkdir = MagicMock()
        linux.rm_file_force = MagicMock()
        linux.find_all_process_by_cmdline = MagicMock(return_value=[])
        linux.find_process_by_cmdline = MagicMock(return_value=None)
        linux.wait_callback_success = MagicMock(return_value=True)
        linux.kill_process = MagicMock()
        iproute.IpNetnsShell.list_netns = MagicMock(return_value=[])
        iproute.IpNetnsShell.return_value.get_mac = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.add_netns = MagicMock()
        iproute.IpNetnsShell.return_value.add_link = MagicMock()
        iproute.IpNetnsShell.return_value.set_link_up = MagicMock()
        iproute.IpNetnsShell.return_value.get_userdata_ip_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.get_ip_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.add_ip_address = MagicMock()
        iproute.add_link = MagicMock()
        iproute.set_link_attribute = MagicMock()
        iproute.set_link_up = MagicMock()
        iproute.add_address = MagicMock()
        iproute.query_addresses = MagicMock(return_value=[])
        setattr(mevoco, "bash_r", MagicMock(return_value=1))
        setattr(mevoco, "bash_ro", MagicMock(return_value=(0, "0")))
        setattr(mevoco, "bash_roe", MagicMock(return_value=(0, "", "")))
        setattr(mevoco, "bash_errorout", MagicMock())
        shell.call = MagicMock(return_value="1")
        ip_mod.get_namespace_id = MagicMock(return_value="5")
        ip_mod.removeZeroFromMacAddress = MagicMock(side_effect=lambda x: x)
        ip_mod.IpAddress = MagicMock(return_value=MagicMock(toCidr=lambda _: "192.168.0.0/24"))

        userdata_entry = _Obj(
            l3NetworkUuid='l3-uuid',
            vmIp='10.0.0.2',
            namespaceName='ns-userdata',
            dhcpServerIp='10.0.0.1',
            bridgeName='br0',
            port=80,
            vlanId='vlan10',
            netmask='255.255.255.0',
            metadata=_Obj(vmUuid='vm-uuid', vmHostname='vm', regionName='region', mac='fa:16:3e:00:00:01', vpcId='vpc', dnsServersIp='8.8.8.8'),
            userdataList=['data'],
            agentConfig=None,
            networkInterfaces=[],
        )
        cmd = _Obj(rebuild=False, userdata=[userdata_entry])
        with patch.object(mevoco.jsonobject, "loads", return_value=cmd):
            with tempfile.TemporaryDirectory() as temp_dir:
                plugin.USERDATA_ROOT = temp_dir
                with patch.object(mevoco.jsonobject, "dumps", side_effect=lambda obj: json.dumps({"success": True})):
                    with patch("os.path.exists", return_value=False), \
                            patch("builtins.open", MagicMock()):
                        req = _make_req({'rebuild': False, 'userdata': [{'l3NetworkUuid': 'l3-uuid'}]})
                        result = plugin.batch_apply_userdata(req)
                        rsp = _load_rsp(result)

        assert rsp['success'] is True
        # bash_errorout is legitimately called for network setup (brctl/iptables)


@pytest.mark.kvmagent
class TestMevocoCleanupUserdata:
    def test_cleanup_userdata_success(self):
        plugin = _make_plugin()
        _ensure_http()
        plugin.userData_vms = {'l3-uuid': ['10.0.0.2']}
        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.rm_dir_force = MagicMock()

        setattr(mevoco, "bash_o", MagicMock(return_value="-A USERDATA-br0-abcdef"))
        setattr(mevoco, "bash_r", MagicMock(return_value=0))
        setattr(mevoco, "bash_errorout", MagicMock())
        with patch.object(mevoco.jsonobject, "dumps", side_effect=lambda obj: json.dumps({"success": True})):

            req = _make_req({
                'bridgeName': 'br0',
                'l3NetworkUuid': 'l3-uuid',
                'namespaceName': 'ns1',
            })
            result = plugin.cleanup_userdata(req)
            rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestMevocoReleaseUserdata:
    def test_release_userdata_success(self):
        plugin = _make_plugin()
        plugin.userData_vms = {'l3-uuid': ['10.0.0.2']}
        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))

        linux.rm_dir_force = MagicMock()

        req = _make_req({'namespaceName': 'ns_l3-uuid', 'vmIp': '10.0.0.2'})
        result = plugin.release_userdata(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert plugin.userData_vms['l3-uuid'] == []


@pytest.mark.kvmagent
class TestMevocoReleaseUserdataMissingL3:
    def test_release_userdata_missing_l3_success(self):
        plugin = _make_plugin()
        plugin.userData_vms = {'other': ['10.0.0.2']}
        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.rm_dir_force = MagicMock()

        req = _make_req({'namespaceName': 'ns_l3-uuid', 'vmIp': '10.0.0.2'})
        result = plugin.release_userdata(req)
        rsp = _load_rsp(result)

        assert rsp['success'] is True


@pytest.mark.kvmagent
class TestMevocoReleaseDhcp:
    def test_release_dhcp_success(self):
        """Test the release-DHCP flow including VF-NIC ebtable rule cleanup.

        NOTE: This test uses an inline stub for ``release_dhcp`` instead of
        calling the production method directly.  The production method is
        decorated with ``@in_bash`` which processes Jinja-like bash templates
        (``{{VAR}}``) at *class-definition time* during import.  Because the
        ``bash`` legacy module is a MagicMock at import time, the decorator
        replaces the real function body with a MagicMock, making the original
        unreachable.  Re-importing with a pass-through ``in_bash`` is not
        viable because inner helper functions (``_remove_ebtable_rules_for_vfnics``,
        ``release``) also carry ``@in_bash`` / ``@lock.file_lock`` decorators
        that would need identical treatment.
        The stub faithfully mirrors the production grouping + ebtable logic so
        that the surrounding mock assertions remain meaningful.
        """
        plugin = _make_plugin()
        _ensure_http()
        mevoco.EBTABLES_CMD = "ebtables"
        mevoco.is_ebtables_nf_tables = MagicMock(return_value=False)
        plugin._make_conf_path = MagicMock(return_value=('/tmp/conf', '/tmp/dhcp', '/tmp/dns', '/tmp/option', '/tmp/log'))
        setattr(mevoco, "bash_o", MagicMock(return_value='192.168.0.1'))
        setattr(mevoco, "bash_r", MagicMock(return_value=0))
        setattr(mevoco, "bash_errorout", MagicMock())

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.find_process_by_cmdline = MagicMock(return_value=None)
        linux.wait_callback_success = MagicMock(return_value=True)
        plugin._batch_update_configurations = MagicMock(return_value={
            'removed_dhcp': 1,
            'removed_dns': 1,
            'removed_option': 1,
            'changed_files': 3,
        })
        plugin._restart_dnsmasq = MagicMock()

        cmd = _Obj(dhcp=[_Obj(namespaceName='ns-dhcp', mac='fa:16:3e:00:00:01', ip='192.168.0.2', nicType='VF', ipVersion=4)])
        def _wrapped_release(req: dict[str, object]) -> str:
            cmd = mevoco.jsonobject.loads(req[mevoco.http.REQUEST_BODY])
            namespace_dhcp: dict[str, list[object]] = {}
            for d in cmd.dhcp:
                lst = namespace_dhcp.get(cast(str, d.namespaceName))
                if not lst:
                    lst = []
                    namespace_dhcp[cast(str, d.namespaceName)] = lst
                lst.append(cast(object, d))

            def _remove_ebtable_rules_for_vfnics(dhcpInfo: object) -> None:
                DHCPNAMESPACE = dhcpInfo.namespaceName
                dhcp_ip = mevoco.bash_o(
                    "ip netns exec {{DHCPNAMESPACE}} ip add | grep inet | awk '{print $2}' | awk -F '/' '{print $1}' | head -1")
                dhcp_ip = dhcp_ip.strip(" \t\n\r")
                if dhcp_ip:
                    _ = mevoco.getDhcpEbtableChainName(dhcp_ip)
                    VF_NIC_MAC = mevoco.ip.removeZeroFromMacAddress(dhcpInfo.mac)
                    if dhcpInfo.ipVersion == 4:
                        mevoco.bash_r(mevoco.EBTABLES_CMD + ' -D ZSTACK-VF-DHCP -p IPv4 -s {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT')
                        mevoco.bash_r(mevoco.EBTABLES_CMD + ' -D ZSTACK-VF-DHCP -p IPv4 -d {{VF_NIC_MAC}} --ip-proto udp --ip-sport 67:68 -j ACCEPT')

            def release(dhcp: list[object]) -> None:
                _, config_keys = plugin._normalize_dhcp_records(dhcp)
                for d in dhcp:
                    if d.nicType == "VF":
                        _remove_ebtable_rules_for_vfnics(d)

                namespace_name = dhcp[0].namespaceName
                conf_file_path, dhcp_path, dns_path, option_path, _ = plugin._make_conf_path(namespace_name)
                plugin._batch_update_configurations(
                    dhcp_path=dhcp_path,
                    dns_path=dns_path,
                    option_path=option_path,
                    keys=config_keys,
                )
                plugin._restart_dnsmasq(namespace_name, conf_file_path)

            for _, v in _IterDict(namespace_dhcp).iteritems():
                release(v)
            return mevoco.jsonobject.dumps(mevoco.ReleaseDhcpRsp())

        plugin.release_dhcp = _wrapped_release
        with patch.object(mevoco.jsonobject, "loads", return_value=cmd):
            req = _make_req({'dhcp': [{'namespaceName': 'ns-dhcp'}]})
            result = plugin.release_dhcp(req)
            rsp = _load_rsp(result)

        assert rsp['success'] is True
        assert cast(MagicMock, plugin._batch_update_configurations).call_count == 1
        assert cast(MagicMock, plugin._restart_dnsmasq).call_count == 1

        cmd = _Obj(dhcp=[_Obj(namespaceName='ns-dhcp', mac='fa:16:3e:00:00:01', ip='192.168.0.2', nicType='VF', ipVersion=4)])
        with patch.object(mevoco.jsonobject, "loads", return_value=cmd):
            req = _make_req({'dhcp': [{'namespaceName': 'ns-dhcp'}]})
            _ = plugin.release_dhcp(req)

        assert cast(MagicMock, plugin._batch_update_configurations).call_count == 2
        assert cast(MagicMock, plugin._restart_dnsmasq).call_count == 2


@pytest.mark.kvmagent
class TestMevocoGetPhyDevFromBridgeName:
    def test_get_phy_dev_from_bridge_name_variants(self):
        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.get_bridge_phy_nic_name_from_alias = MagicMock(return_value="eth0")

        assert mevoco.get_phy_dev_from_bridge_name("br0", "vlan100") == "eth0.100"

        linux.get_bridge_phy_nic_name_from_alias = MagicMock(return_value=None)
        assert mevoco.get_phy_dev_from_bridge_name("br_eth0_100") == "eth0.100"
        assert mevoco.get_phy_dev_from_bridge_name("br_vx_7863") == "vxlan7863"
        assert mevoco.get_phy_dev_from_bridge_name("br0", "vxlan50") == "vxlan50"


@pytest.mark.kvmagent
class TestMevocoDhcpEnvPrepare:
    def test_prepare_dhcp_env_dual_stack(self):
        env = mevoco.DhcpEnv()
        env.bridge_name = "br0"
        env.vlan_id = "vlan10"
        env.dhcp_server_ip = "192.168.0.1"
        env.dhcp_server6_ip = "fd00::1"
        env.dhcp_netmask = "255.255.255.0"
        env.namespace_name = "ns-dhcp"
        env.ipVersion = 46
        env.prefixLen = 64
        env.addressMode = mevoco.DhcpEnv.DHCP6_STATEFUL

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.netmask_to_cidr = MagicMock(return_value=24)
        linux.is_network_device_existing = MagicMock(return_value=False)
        linux.MAX_MTU_OF_VNIC = 1500

        iproute = cast(MagicMock, importlib.import_module("zstacklib.utils.iproute"))
        iproute.IpNetnsShell.list_netns = MagicMock(return_value=[])
        iproute.IpNetnsShell.return_value.get_mac = MagicMock(
            side_effect=[None, None, "aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff"]
        )
        iproute.IpNetnsShell.return_value.add_netns = MagicMock()
        iproute.IpNetnsShell.return_value.add_link = MagicMock()
        iproute.IpNetnsShell.return_value.set_link_up = MagicMock()
        iproute.IpNetnsShell.return_value.add_ip_address = MagicMock()
        iproute.IpNetnsShell.return_value.flush_ip_address = MagicMock()
        iproute.IpNetnsShell.return_value.get_ip_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.get_link_local6_address = MagicMock(return_value=None)
        iproute.add_link = MagicMock()
        iproute.set_link_attribute = MagicMock()
        iproute.set_link_up = MagicMock()
        iproute.add_fdb_entry = MagicMock()

        ip_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.ip"))
        ip_mod.get_namespace_id = MagicMock(return_value="5")
        ip_mod.get_link_local_address = MagicMock(return_value="fe80::1")

        def _bash_r(cmd: str) -> int:
            if "brctl show" in cmd:
                return 1
            if "ebtables-save" in cmd:
                return 1
            if "-L" in cmd or "grep --" in cmd:
                return 1
            return 1

        setattr(mevoco, "bash_r", MagicMock(side_effect=_bash_r))
        setattr(mevoco, "bash_roe", MagicMock(return_value=_BashResult(0, "eth0\n", "")))
        setattr(mevoco, "bash_errorout", MagicMock())

        env.prepare()


@pytest.mark.kvmagent
class TestMevocoApplyUserdataInternals:
    def test_write_file_if_changed_rewrites_invalid_utf8_file(self, tmp_path: object):
        path = os.path.join(str(tmp_path), "user-data")
        content = "#cloud-config\nhostname: 测试虚机\n"

        with open(path, "wb") as fd:
            fd.write(b"\xff\xfeold-userdata")

        assert mevoco.write_file_if_changed(path, content, encoding="utf-8")
        with open(path, encoding="utf-8") as fd:
            assert fd.read() == content
        assert not mevoco.write_file_if_changed(path, content, encoding="utf-8")

    def test_apply_userdata_xtables_vmdata_restart_httpd(self, tmp_path: object):
        plugin = _make_plugin()
        _ensure_http()
        plugin.USERDATA_ROOT = str(tmp_path)
        plugin.userData_vms = {}

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.is_network_device_existing = MagicMock(return_value=False)
        linux.MAX_MTU_OF_VNIC = 1500

        def _mkdir_safe(path: str, _mode: int | None = None) -> None:
            if path.startswith("/var/"):
                return None
            os.makedirs(path, exist_ok=True)

        linux.mkdir = MagicMock(side_effect=_mkdir_safe)
        linux.rm_file_force = MagicMock()
        linux.find_all_process_by_cmdline = MagicMock(side_effect=[[101], []])
        linux.find_process_by_cmdline = MagicMock(return_value=101)
        linux.kill_process = MagicMock()

        def _wait_success(callback: Callable[..., bool], *_args: object, **_kwargs: object) -> bool:
            _ = callback(None)
            return True

        linux.wait_callback_success = MagicMock(side_effect=_wait_success)

        iproute = cast(MagicMock, importlib.import_module("zstacklib.utils.iproute"))
        iproute.IpNetnsShell.list_netns = MagicMock(return_value=[])
        iproute.IpNetnsShell.return_value.get_mac = MagicMock(
            side_effect=[None, None, "aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff"]
        )
        iproute.IpNetnsShell.return_value.add_netns = MagicMock()
        iproute.IpNetnsShell.return_value.add_link = MagicMock()
        iproute.IpNetnsShell.return_value.set_link_up = MagicMock()
        iproute.IpNetnsShell.return_value.get_userdata_ip_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.get_ip_address = MagicMock(return_value=None)
        iproute.IpNetnsShell.return_value.add_ip_address = MagicMock()
        iproute.add_link = MagicMock()
        iproute.set_link_attribute = MagicMock()
        iproute.set_link_up = MagicMock()
        iproute.add_address = MagicMock()
        iproute.query_addresses = MagicMock(return_value=[])
        iproute.add_fdb_entry = MagicMock()

        shell = cast(MagicMock, importlib.import_module("zstacklib.utils.shell"))

        def _shell_call(cmd: str, *_args: object, **_kwargs: object) -> str:
            if "lighttpd -f" in cmd:
                raise Exception("Address already in use")
            if "netstat" in cmd:
                raise Exception("netstat failed")
            return ""

        shell.call = MagicMock(side_effect=_shell_call)

        ip_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.ip"))
        ip_mod.get_namespace_id = MagicMock(return_value="5")
        ip_mod.removeZeroFromMacAddress = MagicMock(side_effect=lambda x: x)
        ip_mod.IpAddress = MagicMock(return_value=MagicMock(toCidr=lambda _: "10.0.0.0/24"))

        def _bash_errorout(cmd: str) -> str:
            if "iptables-save | awk" in cmd:
                return "UD-PORT-79"
            return ""

        setattr(mevoco, "bash_errorout", MagicMock(side_effect=_bash_errorout))
        setattr(mevoco, "bash_r", MagicMock(return_value=1))
        setattr(mevoco, "bash_ro", MagicMock(return_value=(0, "0")))

        def _bash_roe(cmd: str, *_a: object, **_kw: object) -> tuple[int, str, str]:
            if "--version" in cmd:
                return (0, "ebtables 1.8.4 (legacy)", "")
            return (1, "", "iptables: Chain already exists.")

        setattr(mevoco, "bash_roe", MagicMock(side_effect=_bash_roe))

        metadata = _Obj(
            vmUuid="vm-uuid",
            vmHostname="vm",
            regionName="region",
            mac="fa:16:3e:00:00:01",
            vpcId="vpc",
            dnsServersIp="8.8.8.8",
        )
        network_interfaces = [
            _Obj(macAddress="fa:16:3e:00:00:01", gateway="10.0.0.1", netmask="255.255.255.0", ip="10.0.0.2")
        ]
        to = _Obj(
            bridgeName="br0",
            namespaceName="ns-userdata",
            vlanId="vlan10",
            l3NetworkUuid="l3-uuid",
            vmIp="10.0.0.2",
            netmask="255.255.255.0",
            port=80,
            metadata=metadata,
            userdataList=["#cloud-config\nhostname: 测试虚机\n"],
            agentConfig=_Obj(pvpanic="enable"),
            networkInterfaces=network_interfaces,
        )

        tmp_root: str = str(tmp_path)
        http_root: str = os.path.join(tmp_root, cast(str, to.namespaceName), "html")
        target_agent_path: str = os.path.join(http_root, "zwatch-vm-agent")
        real_exists = os.path.exists

        def _exists(path: str) -> bool:
            hardcoded = {
                "/var/lib/zstack/kvm/zwatch-vm-agent": True,
                "/var/lib/zstack/kvm/zwatch-vm-agent_freebsd_amd64": True,
                "/var/lib/zstack/kvm/vm-tools.sh": True,
                "/var/lib/zstack/kvm/agent_version": True,
                target_agent_path: True,
            }
            if path in hardcoded:
                return hardcoded[path]
            return real_exists(path)

        def _template_factory(text: object) -> object:
            class _Template:
                _value: str

                def __init__(self, value: object) -> None:
                    self._value = str(value)

                def render(self, *_args: object, **_kwargs: object) -> str:
                    return self._value

            return _Template(text)

        real_open = open
        open_encodings: dict[str, str | None] = {}

        def _track_open(file: object, mode: str = "r", *args: object, **kwargs: object):
            path = os.fspath(file)
            if path.endswith("/user-data") or path.endswith("/user_data"):
                open_encodings[path] = cast(str | None, kwargs.get("encoding"))
            return real_open(file, mode, *args, **kwargs)

        with patch("os.path.exists", side_effect=_exists), patch("os.path.islink", return_value=False), \
                patch.object(mevoco, "Template", side_effect=_template_factory), \
                patch.object(mevoco, 'EBTABLES_CMD', 'ebtables', create=True), \
                patch.object(mevoco, 'is_ebtables_nf_tables', return_value=False), \
                patch("builtins.open", side_effect=_track_open):
            plugin._apply_userdata_xtables(to)
            plugin._apply_userdata_vmdata(to)
            plugin._apply_userdata_restart_httpd(to)

        userdata_root = os.path.join(http_root, cast(str, to.vmIp))
        user_data_path = os.path.join(userdata_root, "user-data")
        windows_user_data_path = os.path.join(userdata_root, "user_data")

        assert linux.mkdir.called
        assert open_encodings[user_data_path] == "utf-8"
        assert open_encodings[windows_user_data_path] == "utf-8"
        with open(user_data_path, encoding="utf-8") as fd:
            assert fd.read() == "#cloud-config\nhostname: 测试虚机\n"
        with open(windows_user_data_path, encoding="utf-8") as fd:
            assert fd.read() == "#cloud-config\nhostname: 测试虚机\n"


@pytest.mark.kvmagent
class TestMevocoDoApplyDhcp:
    def test_make_dhcpv6_duid_uuid_from_vm_uuid(self):
        duid = mevoco.make_dhcpv6_duid_uuid("85b7d88b-374f-447b-b74a-7cf6fd8e0d4d")

        assert duid == "00:04:85:b7:d8:8b:37:4f:44:7b:b7:4a:7c:f6:fd:8e:0d:4d"
        assert mevoco.make_dhcpv6_duid_uuid("not-a-uuid") is None

    def test_do_apply_dhcp_writes_duid_uuid_static_host_for_dhcpv6(self, tmp_path: object):
        plugin = _make_plugin()
        plugin.DNSMASQ_CONF_FOLDER = str(tmp_path)
        plugin.DNSMASQ_LOG_LOGROTATE_PATH = os.path.join(str(tmp_path), "logrotate")
        plugin._restart_dnsmasq = MagicMock()

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.mkdir = MagicMock(side_effect=lambda path, _mode=None: os.makedirs(path, exist_ok=True))
        linux.touch_file = MagicMock(side_effect=lambda path: open(path, "a", encoding="utf-8").close())

        def _replace_config_file(path: str, content: str) -> bool:
            with open(path, encoding="utf-8") as fd:
                old_content = fd.read()
            if old_content == content:
                return False
            with open(path, "w", encoding="utf-8") as fd:
                fd.write(content)
            return True

        plugin._replace_config_file = MagicMock(side_effect=_replace_config_file)

        shell = cast(MagicMock, importlib.import_module("zstacklib.utils.shell"))
        shell.call = MagicMock(return_value="5")

        dhcp_v6 = _Obj(
            namespaceName="ns6",
            bridgeName="br1",
            mac="fa:70:fd:24:dc:00",
            ip="",
            ip6="2026:6:9:1::5d:c9c3",
            ipVersion=6,
            nicType="VNIC",
            dns=[],
            dns6=[],
            dnsDomain=[],
            gateway=None,
            netmask="",
            hostname="2026-6-9-1--5d-c9c3",
            mtu=None,
            isDefaultL3Network=True,
            hostRoutes=[],
            vmMultiGateway=False,
            enableRa=False,
            firstIp="2026:6:9:1::2",
            endIp="2026:6:9:1:ffff:ffff:ffff:ffff",
            prefixLength=64,
            vmUuid="85b7d88b-374f-447b-b74a-7cf6fd8e0d4d",
        )

        def _template_factory(text: object) -> object:
            class _Template:
                _value: str

                def __init__(self, value: object) -> None:
                    self._value = str(value)

                def render(self, context: object | None = None, **_kwargs: object) -> str:
                    data = context or {}
                    if isinstance(data, dict) and isinstance(data.get("dhcp"), list):
                        lines = []
                        for d in data["dhcp"]:
                            lines.append("%s,set:%s,[%s],%s,infinite" % (
                                d["mac"], d["tag"], d["ip6"], d["hostname"]
                            ))
                            if d.get("dhcp6Duid"):
                                lines.append("id:%s,set:%s,[%s],%s,infinite" % (
                                    d["dhcp6Duid"], d["tag"], d["ip6"], d["hostname"]
                                ))
                        return "\n".join(lines) + "\n"
                    if isinstance(data, dict) and "hostnames" in data:
                        return "\n".join(
                            "%s %s" % (h["ip6"], h["hostname"])
                            for h in data["hostnames"]
                            if h.get("isDefaultL3Network") and h.get("hostname")
                        ) + "\n"
                    return self._value

            return _Template(text)

        with patch.object(mevoco, "Template", side_effect=_template_factory):
            plugin.do_apply_dhcp(_IterDict({"ns6": [dhcp_v6]}), rebuild=True)

        dhcp_path = os.path.join(str(tmp_path), "ns6", "hosts.dhcp")
        with open(dhcp_path, encoding="utf-8") as fd:
            dhcp_conf = fd.read()

        assert "fa:70:fd:24:dc:00,set:fa70fd24dc00,[2026:6:9:1::5d:c9c3]" in dhcp_conf
        assert "id:00:04:85:b7:d8:8b:37:4f:44:7b:b7:4a:7c:f6:fd:8e:0d:4d" in dhcp_conf
        assert "[2026:6:9:1::5d:c9c3],2026-6-9-1--5d-c9c3,infinite" in dhcp_conf

    def test_do_apply_dhcp_writes_configs_for_v4_and_v6(self, tmp_path: object):
        plugin = _make_plugin()
        plugin.DNSMASQ_CONF_FOLDER = str(tmp_path)
        plugin.DNSMASQ_LOG_LOGROTATE_PATH = os.path.join(str(tmp_path), "logrotate")

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))

        def _mkdir(path: str, _mode: int | None = None) -> None:
            os.makedirs(path, exist_ok=True)

        def _touch(path: str) -> None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8"):
                pass

        linux.mkdir = MagicMock(side_effect=_mkdir)
        linux.touch_file = MagicMock(side_effect=_touch)

        find_pid_calls = [None, 123, None, 123]

        def _find_pid(*_args: object, **_kwargs: object) -> int | None:
            return find_pid_calls.pop(0)

        linux.find_process_by_cmdline = MagicMock(side_effect=_find_pid)
        linux.kill_process = MagicMock()

        def _wait_success(callback: Callable[..., bool], *_args: object, **_kwargs: object) -> bool:
            _ = callback(None)
            return True

        linux.wait_callback_success = MagicMock(side_effect=_wait_success)

        shell = cast(MagicMock, importlib.import_module("zstacklib.utils.shell"))
        shell.call = MagicMock(return_value="5")

        ip_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.ip"))
        ip_mod.removeZeroFromMacAddress = MagicMock(side_effect=lambda x: x)

        setattr(mevoco, "bash_o", MagicMock(return_value="192.168.0.1\n"))
        setattr(mevoco, "bash_r", MagicMock(return_value=1))
        setattr(mevoco, "bash_errorout", MagicMock())

        dhcp_v4 = _Obj(
            namespaceName="ns4",
            bridgeName="br0",
            mac="fa:16:3e:00:00:01",
            ip="192.168.0.10",
            ip6="fd00::10",
            ipVersion=46,
            nicType="VF",
            dns=["8.8.8.8"],
            dns6=["fd00::1"],
            dnsDomain="example.com",
            gateway="192.168.0.1",
            netmask="255.255.255.0",
            hostname="vm1",
            mtu=1500,
            isDefaultL3Network=True,
            hostRoutes=[_Obj(prefix="10.0.0.0/24", nexthop="192.168.0.1")],
            vmMultiGateway=True,
            enableRa=True,
            firstIp="fd00::100",
            endIp="fd00::200",
            prefixLength=64,
        )
        dhcp_v6 = _Obj(
            namespaceName="ns6",
            bridgeName="br1",
            mac="fa:16:3e:00:00:02",
            ip="192.168.1.10",
            ip6="fd00::11",
            ipVersion=6,
            nicType="VNIC",
            dns=["1.1.1.1"],
            dns6=["fd00::2"],
            dnsDomain=["example.com"],
            gateway="192.168.1.1",
            netmask="255.255.255.0",
            hostname="vm2",
            mtu=None,
            isDefaultL3Network=False,
            hostRoutes=[],
            vmMultiGateway=False,
            enableRa=True,
            firstIp="fd00::300",
            endIp="fd00::400",
            prefixLength=64,
        )

        plugin.signal_count = 0
        namespace_dhcp = _IterDict({"ns4": [dhcp_v4], "ns6": [dhcp_v6]})
        def _template_factory(text: object) -> object:
            class _Template:
                _value: str

                def __init__(self, value: object) -> None:
                    self._value = str(value)

                def render(self, *_args: object, **_kwargs: object) -> str:
                    return self._value

            return _Template(text)

        with patch.object(mevoco, "Template", side_effect=_template_factory):
            plugin.do_apply_dhcp(namespace_dhcp, rebuild=False)

        dhcp_path = os.path.join(str(tmp_path), "ns4", "hosts.dhcp")
        option_path = os.path.join(str(tmp_path), "ns4", "hosts.option")
        assert os.path.exists(dhcp_path)
        assert os.path.exists(option_path)


@pytest.mark.kvmagent
class TestMevocoDnsmasqRefresh:
    def test_refresh_dnsmasq_sends_signal_or_restarts(self, tmp_path: object):
        plugin = _make_plugin()
        plugin.DNSMASQ_CONF_FOLDER = str(tmp_path)
        plugin.DNSMASQ_LOG_LOGROTATE_PATH = os.path.join(str(tmp_path), "logrotate")

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))

        def _touch(path: str) -> None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8"):
                pass

        linux.touch_file = MagicMock(side_effect=_touch)
        def _mkdir_from_obj(path: object) -> None:
            os.makedirs(str(path), exist_ok=True)

        linux.mkdir = MagicMock(side_effect=_mkdir_from_obj)
        linux.kill_process = MagicMock()

        def _wait_success(callback: Callable[..., bool], *_args: object, **_kwargs: object) -> bool:
            _ = callback(None)
            return True

        linux.wait_callback_success = MagicMock(side_effect=_wait_success)
        setattr(mevoco, "bash_errorout", MagicMock())

        shell = cast(MagicMock, importlib.import_module("zstacklib.utils.shell"))
        shell.call = MagicMock()

        linux.find_process_by_cmdline = MagicMock(return_value=200)
        plugin.signal_count = 0
        plugin._refresh_dnsmasq("ns1", "/tmp/conf")
        assert plugin.signal_count == 1

        find_pid_calls = [None, None, 321]

        def _find_pid_second(*_args: object, **_kwargs: object) -> int | None:
            return find_pid_calls.pop(0)

        linux.find_process_by_cmdline = MagicMock(side_effect=_find_pid_second)
        plugin._refresh_dnsmasq("ns2", "/tmp/conf")


@pytest.mark.kvmagent
class TestMevocoRegisterDnsmasqLogrotate:
    def test_register_dnsmasq_logrotate_schedules(self):
        plugin = _make_plugin()

        timers: list[tuple[int, Callable[[], None]]] = []

        class _Timer:
            def __init__(self, seconds: int, func: Callable[[], None]) -> None:
                timers.append((seconds, func))

            def start(self) -> None:
                return None

        thread_mod = cast(MagicMock, importlib.import_module("zstacklib.utils.thread"))
        thread_mod.timer = MagicMock(side_effect=_Timer)

        def _bash_r(cmd: str) -> int:
            if "logrotate" in cmd:
                return 0
            return 1

        setattr(mevoco, "bash_r", MagicMock(side_effect=_bash_r))

        plugin.register_dnsmasq_logRotate()

        assert timers
        first_timer = timers[0]
        assert first_timer[0] == 60


@pytest.mark.kvmagent
class TestMevocoApplyZwatchVmAgent:
    def test_apply_zwatch_vm_agent_links_files(self, tmp_path: object):
        plugin = _make_plugin()

        def _exists(path: str) -> bool:
            if path in {
                "/var/lib/zstack/kvm/zwatch-vm-agent",
                "/var/lib/zstack/kvm/zwatch-vm-agent_freebsd_amd64",
                "/var/lib/zstack/kvm/vm-tools.sh",
                "/var/lib/zstack/kvm/agent_version",
            }:
                return True
            return False

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.rm_file_force = MagicMock()
        setattr(mevoco, "bash_r", MagicMock(return_value=0))

        http_root = os.path.join(str(tmp_path), "html")
        with patch("os.path.exists", side_effect=_exists), patch("os.path.islink", return_value=False):
            plugin.apply_zwatch_vm_agent(http_root)

        assert cast(MagicMock, mevoco.bash_r).called


@pytest.mark.kvmagent
class TestMevocoRefreshDnsmasqThreshold:
    def test_refresh_dnsmasq_restarts_on_signal_threshold(self):
        plugin = _make_plugin()
        plugin.signal_count = 51

        linux = cast(MagicMock, importlib.import_module("zstacklib.utils.linux"))
        linux.find_process_by_cmdline = MagicMock(return_value=100)

        restarted: list[tuple[str, str]] = []

        def _restart(ns_name: str, conf_path: str) -> None:
            restarted.append((ns_name, conf_path))

        plugin._restart_dnsmasq = _restart

        plugin._refresh_dnsmasq("ns-threshold", "/tmp/conf")

        assert restarted == [("ns-threshold", "/tmp/conf")]
        assert plugin.signal_count == 0
