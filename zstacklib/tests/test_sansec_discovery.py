from types import SimpleNamespace

import pytest

from zstacklib.utils import pci, sansec


def device(device_id='7011', vendor_id='1ed4', address='0000:b3:00.0'):
    return SimpleNamespace(vendorId=vendor_id, deviceId=device_id, pciDeviceAddress=address,
                           type='Generic', addonInfo={}, dependentDevices=['0000:b3:01.1'])


@pytest.mark.parametrize('vendor,device_id,expected', [
    ('1ed4', '7011', True), ('1ED4', '1001', True), ('1ed4', '9999', False), ('10de', '7011', False),
])
def test_identification_is_limited_to_observed_ids(vendor, device_id, expected):
    assert sansec.probe(device(device_id, vendor), None) is expected


def test_unloaded_driver_is_still_discovered_without_claiming_health(tmp_path, monkeypatch):
    monkeypatch.setattr(sansec, 'SYSFS_DEVICES', str(tmp_path))
    to = device()
    assert pci.pci_device_probe(to, None)
    assert to.type == 'Crypto_Controller'
    assert to.addonInfo == {'cryptoQualification': 'DriverUnavailable', 'cryptoDriverVersion': None}
    assert 'healthStatus' not in to.addonInfo
    assert to.iommuGroup == ''


def test_one_multifunction_card_reports_one_crypto_pf_and_retains_pci_dependencies(tmp_path, monkeypatch):
    monkeypatch.setattr(sansec, 'SYSFS_DEVICES', str(tmp_path))
    addresses = ['0000:b3:00.%s' % index for index in range(4)]
    devices = []
    for address in addresses:
        path = tmp_path / address
        path.mkdir()
        (path / 'vendor').write_text('0x1ed4')
        (path / 'device').write_text('0x7011')
        to = device(address=address)
        to.dependentDevices = [other for other in addresses if other != address]
        devices.append(to)
    (tmp_path / addresses[0] / 'sriov_totalvfs').write_text('64')
    (tmp_path / addresses[0] / 'sriov_numvfs').write_text('0')

    for to in devices:
        pci.pci_device_probe(to, None)

    assert [to.pciDeviceAddress for to in devices if to.type == 'Crypto_Controller'] == [addresses[0]], \
        'One physical card must not become four independent crypto PF resources'
    assert all(to.type == 'Generic' and not to.addonInfo for to in devices[1:])
    assert devices[0].addonInfo['cryptoQualification'] == 'DriverUnavailable', \
        'Driver absence must not hide the physical card'
    assert devices[0].dependentDevices == addresses[1:], 'Companion functions remain PCI dependencies'
    assert pci.pci_device_probe(device('1001', address='0000:b3:01.1'), None), \
        'A VF function number must not be mistaken for a companion PF'


@pytest.mark.parametrize('layout', ['another_sriov_pf', 'no_primary', 'no_primary_sriov', 'different_vendor'])
def test_discovery_does_not_hide_a_function_without_a_known_companion_layout(tmp_path, monkeypatch, layout):
    monkeypatch.setattr(sansec, 'SYSFS_DEVICES', str(tmp_path))
    primary = tmp_path / '0000:b3:00.0'
    primary.mkdir()
    (primary / 'vendor').write_text('0x10de' if layout == 'different_vendor' else '0x1ed4')
    (primary / 'device').write_text('0x7011')
    if layout != 'no_primary_sriov':
        (primary / 'sriov_totalvfs').write_text('64')
    address = '0000:b4:00.1' if layout == 'no_primary' else '0000:b3:00.1'
    path = tmp_path / address
    path.mkdir()
    if layout == 'another_sriov_pf':
        (path / 'sriov_totalvfs').write_text('64')
    to = device(address=address)
    assert pci.pci_device_probe(to, None)
    assert to.type == 'Crypto_Controller', 'Only positively identified companion functions may be excluded'


def test_vf_reports_pf_driver_even_while_bound_to_vfio(tmp_path, monkeypatch):
    pf = tmp_path / '0000:b3:00.0'
    vf = tmp_path / '0000:b3:01.0'
    driver = tmp_path / 'drivers/swcsm'
    vfio = tmp_path / 'drivers/vfio-pci'
    for path in (pf, vf, driver, vfio):
        path.mkdir(parents=True)
    (pf / 'driver').symlink_to(driver)
    (vf / 'physfn').symlink_to(pf)
    (vf / 'driver').symlink_to(vfio)
    monkeypatch.setattr(sansec, 'SYSFS_DEVICES', str(tmp_path))
    (driver / 'module').mkdir()
    (driver / 'module/version').write_text('P62.0.00.009\n')
    to = device('1001', address=vf.name)
    assert sansec.init(to, None)
    assert to.addonInfo['cryptoQualification'] == 'Unverified'
    assert to.addonInfo['cryptoDriverVersion'] == 'P62.0.00.009'
    assert to.dependentDevices == ['0000:b3:01.1']
    assert 'healthStatus' not in to.addonInfo


def test_discovery_tracks_srcversion_when_vendor_driver_has_no_version(tmp_path, monkeypatch):
    pf = tmp_path / '0000:b3:00.0'
    driver = tmp_path / 'drivers/swcsm'
    pf.mkdir()
    (driver / 'module').mkdir(parents=True)
    (pf / 'driver').symlink_to(driver)
    source = driver / 'module/srcversion'
    source.write_text('FIRST-BUILD')
    monkeypatch.setattr(sansec, 'SYSFS_DEVICES', str(tmp_path))
    to = device()
    sansec.init(to, None)
    assert to.addonInfo['cryptoDriverVersion'] == 'FIRST-BUILD'
    source.write_text('SECOND-BUILD')
    sansec.init(to, None)
    assert to.addonInfo['cryptoDriverVersion'] == 'SECOND-BUILD', 'MN must see a changed driver fingerprint'


def test_unreadable_driver_version_does_not_abort_pci_discovery(tmp_path, monkeypatch):
    pf = tmp_path / '0000:b3:00.0'
    driver = tmp_path / 'drivers/swcsm'
    pf.mkdir()
    driver.mkdir(parents=True)
    (pf / 'driver').symlink_to(driver)
    monkeypatch.setattr(sansec, 'SYSFS_DEVICES', str(tmp_path))

    def unreadable(path):
        raise PermissionError('driver version cannot be read')

    monkeypatch.setattr(sansec.sansec_utils, 'driver_version', unreadable)
    to = device()
    assert sansec.init(to, None)
    assert to.addonInfo == {'cryptoQualification': 'Unverified', 'cryptoDriverVersion': None}


def test_pf_reports_current_vf_count_for_stateless_virtualization(tmp_path, monkeypatch):
    pf = tmp_path / '0000:b3:00.0'
    pf.mkdir()
    (pf / 'sriov_numvfs').write_text('2\n')
    monkeypatch.setattr(sansec, 'SYSFS_DEVICES', str(tmp_path))
    to = device()
    sansec.init(to, None)
    assert to.addonInfo['sriovNumVfs'] == 2, 'MN derives PF virtualization from the observed VF count'


def test_discovery_converges_only_to_a_zstack_declared_driver(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sansec.shell, 'call', calls.append)
    monkeypatch.setattr(sansec, 'MODULE_DIR', str(tmp_path / 'module'))
    monkeypatch.setattr(sansec.sansec_utils, 'MODULE_CONFIG', str(tmp_path / 'zstack-sansec.conf'))
    sansec.converge_driver()
    assert not calls, 'Without the ZStack VFnum file discovery must not load the driver'
    (tmp_path / 'zstack-sansec.conf').write_text('options swcsm VFnum=2\n')
    sansec.converge_driver()
    assert calls == ['modprobe swcsm']
    (tmp_path / 'module').mkdir()
    sansec.converge_driver()
    assert calls == ['modprobe swcsm'], 'A loaded driver is already converged'
