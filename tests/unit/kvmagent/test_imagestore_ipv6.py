import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from kvmagent.crypto.ceph import operations as ceph


def _load_imagestore_module():
    bash_module = sys.modules.get('zstacklib.utils.bash')
    if bash_module is not None and not hasattr(bash_module, 'bash_progress_1'):
        bash_module.bash_progress_1 = lambda *args, **kwargs: (0, '', None)

    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / 'kvmagent' / 'kvmagent' / 'plugins' / 'imagestore.py'
    spec = importlib.util.spec_from_file_location('imagestore_under_test', str(module_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


imagestore = _load_imagestore_module()
ImageStoreClient = imagestore.ImageStoreClient


TEST_IPV6_ADDRESS = '2001:db8::10'
TEST_IPV4_ADDRESS = '192.168.10.10'
TEST_IMAGE_PATH = 'zstore://image-name/image-id'
TEST_PRIMARY_PATH = '/zstack_ps/rootVolumes/volume.qcow2'


def test_imagestore_client_registry_url_wraps_ipv6_only_once():
    client = ImageStoreClient()

    assert client._build_registry_url(TEST_IPV4_ADDRESS) == '192.168.10.10:8000'
    assert client._build_registry_url(TEST_IPV6_ADDRESS) == '[2001:db8::10]:8000'
    assert client._build_registry_url('[2001:db8::10]') == '[2001:db8::10]:8000'


def test_download_from_imagestore_uses_bracketed_ipv6_registry_url(monkeypatch, configured_volume_extensions):
    client = ImageStoreClient()
    commands = []

    monkeypatch.setattr(client, '_check_zstore_cli', lambda: None)
    monkeypatch.setattr(imagestore.shell, 'call', lambda command: commands.append(command) or '')

    client.download_from_imagestore(
        None,
        TEST_IPV6_ADDRESS,
        TEST_IMAGE_PATH,
        TEST_PRIMARY_PATH,
    )

    assert len(commands) == 1
    assert ' -url [2001:db8::10]:8000 ' in commands[0]


@pytest.mark.parametrize("hostname", [TEST_IPV6_ADDRESS, f"[{TEST_IPV6_ADDRESS}]"])
def test_ceph_encrypted_download_uses_bracketed_ipv6_registry_url(monkeypatch, hostname):
    client = ImageStoreClient()
    cmd = SimpleNamespace(hostname=hostname, backupStorageInstallPath=TEST_IMAGE_PATH,
                          primaryStorageInstallPath='ceph://pool/volume', encryptedDek='wrapped')
    commands = []
    monkeypatch.setattr(client, '_check_zstore_cli', lambda: None)
    monkeypatch.setattr(ceph, '_config', lambda _: '/etc/ceph.conf')
    monkeypatch.setattr(ceph, '_rbd_exists', lambda *_: False)
    monkeypatch.setattr(ceph, '_rbd_rename', lambda *_: None)
    monkeypatch.setattr(ceph, '_verified_state', lambda *_: None)
    monkeypatch.setattr(ceph, 'run_checked', lambda command, **_: commands.append(command))

    assert ceph.download_encrypted_imagestore(cmd, client)
    assert len(commands) == 1
    command = commands[0]
    assert command[command.index('-url') + 1] == '[2001:db8::10]:8000'
