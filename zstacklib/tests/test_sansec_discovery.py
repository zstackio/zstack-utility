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
