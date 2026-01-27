import os
import sys
import types

import pytest


@pytest.fixture
def pci_module(monkeypatch):
    if sys.version_info[0] < 3:
        from zstacklib.utils import pci
        return pci

    import importlib.util
    import zstacklib.utils

    for name in ('log', 'linux', 'sizeunit', 'bash'):
        module = types.ModuleType('zstacklib.utils.' + name)
        if name == 'log':
            module.get_logger = lambda _: None
        if name == 'bash':
            module.bash_roe = lambda *_: None
        monkeypatch.setitem(sys.modules, module.__name__, module)
        monkeypatch.setattr(zstacklib.utils, name, module, raising=False)

    source = os.path.join(os.path.dirname(__file__), '..', 'zstacklib', 'utils', 'pci.py')
    spec = importlib.util.spec_from_file_location('pci_mapping_test', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PCI_HOSTDEV = """<hostdev type="pci">
  <source><address domain="0x0000" bus="0x3b" slot="0x00" function="0x0"/></source>
  <address domain="0x0000" bus="0x05" slot="0x00" function="0x0"/>
</hostdev>"""
MDEV_HOSTDEV = """<hostdev type="mdev">
  <source><address uuid="a297db4a-f4c2-11e6-90f5-d3b88d6c9525"/></source>
  <address domain="0x0000" bus="0x06" slot="0x00" function="0x0"/>
</hostdev>"""


class Domain:
    def __init__(self, hostdevs):
        self.hostdevs = hostdevs

    def XMLDesc(self):
        return "<domain><devices>%s</devices></domain>" % self.hostdevs


@pytest.mark.parametrize("hostdevs", [
    MDEV_HOSTDEV + PCI_HOSTDEV,
    PCI_HOSTDEV + MDEV_HOSTDEV,
])
def test_mixed_pci_and_mdev_maps_only_pci(pci_module, hostdevs):
    assert pci_module.get_pci_passthrough_mapping(Domain(hostdevs)) == {"0000:05:00.0": "0000:3b:00.0"}


def test_only_mdev_has_no_pci_mapping(pci_module):
    assert pci_module.get_pci_passthrough_mapping(Domain(MDEV_HOSTDEV)) == {}
