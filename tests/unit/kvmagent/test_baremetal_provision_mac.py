"""Exercise the production DHCP writer with real files and no gateway services."""
import ast
import os
from pathlib import Path
import shutil
import tempfile
from types import MethodType, SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _writer(tmp_path):
    source = Path(__file__).resolve().parents[3] / 'kvmagent/kvmagent/plugins/baremetal_v2_gateway_agent.py'
    plugin = next(node for node in ast.parse(source.read_text()).body
                  if isinstance(node, ast.ClassDef) and node.name == 'BaremetalV2GatewayAgentPlugin')
    method = next(node for node in plugin.body if isinstance(node, ast.FunctionDef)
                  and node.name == '_append_dnsmasq_configuration')
    namespace = dict(os=os, shutil=shutil, tempfile=tempfile, shell=MagicMock(),
                     lock=SimpleNamespace(lock=lambda name: lambda func: func))
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), namespace)  # noqa: S102 - run the repository method in an isolated test namespace
    writer = SimpleNamespace(
        DNSMASQ_HOSTS_PATH=str(tmp_path / 'hosts'),
        DNSMASQ_OPTS_PATH=str(tmp_path / 'opts'),
        DNSMASQ_LEASE_PATH=str(tmp_path / 'leases'),
        _load_template=MagicMock(return_value=MagicMock(render=MagicMock(return_value='tag:instance-a,option:tftp-server,10.0.0.1'))),
    )
    writer.write = MethodType(namespace['_append_dnsmasq_configuration'], writer)
    return writer


def _instance(mac='aa:bb:cc:dd:ee:02', extra=None):
    return SimpleNamespace(uuid='instance-a', provision_mac=mac,
                           provision_ip='10.0.0.10', gateway_ip='10.0.0.1',
                           extra_provision_nic_infos=extra or [])


def test_mac_refresh_replaces_all_old_instance_hosts_and_preserves_neighbors(tmp_path):
    writer = _writer(tmp_path)
    hosts = Path(writer.DNSMASQ_HOSTS_PATH)
    neighbor = 'aa:bb:cc:dd:ee:ff,10.0.0.20,set:instance,set:instance-a-other\n'
    hosts.write_text('aa:bb:cc:dd:ee:01,10.0.0.10,set:instance,set:instance-a\n'
                     'aa:bb:cc:dd:ee:03,10.0.0.11,set:instance,set:instance-a\n' + neighbor)
    hosts.chmod(0o640)
    instance = _instance(extra=[SimpleNamespace(provision_mac='aa:bb:cc:dd:ee:04', provision_ip='10.0.0.11')])
    writer.write(instance)
    writer.write(instance)
    assert hosts.read_text().splitlines() == [neighbor.strip(),
        'aa:bb:cc:dd:ee:02,10.0.0.10,set:instance,set:instance-a',
        'aa:bb:cc:dd:ee:04,10.0.0.11,set:instance,set:instance-a']
    assert hosts.stat().st_mode & 0o777 == 0o640
    assert Path(writer.DNSMASQ_OPTS_PATH).read_text().count('tag:instance-a') == 1


def test_first_configuration_creates_host_file(tmp_path):
    writer = _writer(tmp_path)
    writer.write(_instance())
    assert Path(writer.DNSMASQ_HOSTS_PATH).read_text() == \
        'aa:bb:cc:dd:ee:02,10.0.0.10,set:instance,set:instance-a\n'


def test_missing_provision_mac_keeps_existing_configuration(tmp_path):
    writer = _writer(tmp_path)
    hosts = Path(writer.DNSMASQ_HOSTS_PATH)
    hosts.write_text('unchanged\n')
    writer.write(_instance(mac=None))
    assert hosts.read_text() == 'unchanged\n'


def test_failed_atomic_replace_preserves_previous_hosts(tmp_path, monkeypatch):
    writer = _writer(tmp_path)
    hosts = Path(writer.DNSMASQ_HOSTS_PATH)
    hosts.write_text('old configuration\n')
    monkeypatch.setattr(os, 'rename', MagicMock(side_effect=OSError('replacement failed')))
    with pytest.raises(OSError, match='replacement failed'):
        writer.write(_instance())
    assert hosts.read_text() == 'old configuration\n'
    assert sorted(p.name for p in tmp_path.iterdir()) == ['hosts']
