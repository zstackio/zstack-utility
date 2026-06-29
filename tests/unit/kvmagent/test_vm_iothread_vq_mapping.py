# -*- coding: utf-8 -*-

import pytest

from kvmagent.plugins import vm_plugin


class Volume(object):
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __getattr__(self, name):
        return None

    def hasattr(self, name):
        return name in self.__dict__


def cbd_volume(**kwargs):
    values = {
        'deviceType': 'cbd',
        'useVirtio': True,
        'useVirtioSCSI': False,
        'multiQueues': '16',
        'ioThreads': 8,
        'volumeUuid': 'volume-uuid',
        'deviceId': 1,
    }
    values.update(kwargs)
    return Volume(**values)


def drive_address(controller, unit):
    return Volume(type='drive', controller=str(controller), unit=str(unit))


def pci_address(**kwargs):
    values = {
        'type': 'pci',
        'domain': '0x0000',
        'bus': '0x00',
        'slot': '0x05',
        'function': '0x0',
    }
    values.update(kwargs)
    return Volume(**values)


def disk_with_target(bus):
    disk = vm_plugin.etree.Element('disk')
    vm_plugin.e(disk, 'target', None, {'dev': 'sd%s' % vm_plugin.Vm.DEVICE_LETTERS[1], 'bus': bus})
    return disk


class EmptyAddons(object):
    def __init__(self):
        self.attachedDataVolumes = []

    def __bool__(self):
        return False

    __nonzero__ = __bool__


def no_retry(*args, **kwargs):
    def decorator(func):
        return func
    return decorator


class FakeLibvirtError(Exception):
    pass


CLEAN_DOMAIN_XML = '<domain><devices/></domain>'


class FakeDetachDomain(object):
    def detachDeviceFlags(self, xml, flags):
        return None


class FakeTargetDisk(object):
    def __init__(self, disk_xml):
        self.disk_xml = disk_xml

    def dump(self):
        return self.disk_xml


class FakeVm(object):
    def __init__(self, domain_xml):
        self.domain_xml = domain_xml

    def _get_target_disk(self, volume, is_exception=False):
        return None, None


class DetachVolumeCleanupContext(object):
    def __init__(self, vm, volume, detached_aliases, deleted_iothreads):
        self.vm = vm
        self.volume = volume
        self.detached_aliases = detached_aliases
        self.deleted_iothreads = deleted_iothreads


def scsi_disk_xml(iothread_ids, dev='sdb', controller='1'):
    iothreads_xml = '\n'.join(
        ['                  <iothread id="%s"><queue id="0"/></iothread>' % iothread_id
         for iothread_id in iothread_ids])
    iothreads = '''
                <iothreads>
%s
                </iothreads>''' % iothreads_xml if iothread_ids else ''
    return '''
            <disk type="network" device="disk">
              <driver name="qemu" type="raw">
%s
              </driver>
              <target dev="%s" bus="scsi"/>
              <address type="drive" controller="%s"/>
            </disk>
            ''' % (iothreads, dev, controller)


def scsi_controller_domain_xml(iothread_ids, queues='4', index='1', alias='scsi1', extra_devices=''):
    iothreads_xml = '\n'.join(
        ['              <iothread id="%s"><queue id="0"/></iothread>' % iothread_id
         for iothread_id in iothread_ids])
    iothreads = '''
            <iothreads>
%s
            </iothreads>''' % iothreads_xml if iothread_ids else ''
    return '''
    <domain>
      <devices>
        <controller type="scsi" model="virtio-scsi" index="%s">
          <driver queues="%s">
%s
          </driver>
          <alias name="%s"/>
        </controller>
%s
      </devices>
    </domain>
    ''' % (index, queues, iothreads, alias, extra_devices)


def domain_xml_with_iothread_disk(iothread_ids, dev='sdc', controller='1'):
    return '''
    <domain>
      <devices>
%s
      </devices>
    </domain>
    ''' % scsi_disk_xml(iothread_ids, dev, controller)


def fake_wait_callback_success(callback, callback_data=None, timeout=60, interval=1,
                               ignore_exception_in_callback=False):
    for _ in range(4):
        if callback(callback_data):
            return True
    return False


def stub_detach_volume_dependencies(monkeypatch, vm, disk_xml, current_xmls,
                                    detached_aliases, deleted_iothreads,
                                    wait_callback_success=None,
                                    detach_controller_result=None,
                                    del_iothread_result=None):
    current_vms = [FakeVm(domain_xml) for domain_xml in current_xmls]

    def fake_get_vm_by_uuid(uuid):
        return current_vms.pop(0) if current_vms else FakeVm(current_xmls[-1])

    def fake_detach_controller(alias):
        detached_aliases.append(alias)
        return detach_controller_result(vm.uuid, alias) if callable(detach_controller_result) else detach_controller_result

    def fake_del_iothread(uuid, iothread_id):
        deleted_iothreads.append(iothread_id)
        return del_iothread_result(uuid, iothread_id) if callable(del_iothread_result) else del_iothread_result

    monkeypatch.setattr(vm_plugin.linux, 'retry', no_retry)
    monkeypatch.setattr(vm_plugin.linux, 'wait_callback_success',
                        wait_callback_success or (lambda callback, *args: callback(None)))
    monkeypatch.setattr(vm_plugin.libvirt, 'libvirtError', RuntimeError)
    monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', fake_get_vm_by_uuid)
    monkeypatch.setattr(vm_plugin, 'is_libvirt_support_blockdev', lambda version: True)
    monkeypatch.setattr(vm, 'detach_controller_by_alias', fake_detach_controller)
    monkeypatch.setattr(vm_plugin.VmPlugin, 'del_io_thread', staticmethod(fake_del_iothread))
    monkeypatch.setattr(vm, '_get_target_disk', lambda v: (FakeTargetDisk(disk_xml), 'sdb'))


def setup_detach_volume_cleanup(monkeypatch, controller_xml, disk_xml, current_xmls,
                                wait_callback_success=None, detach_controller_result=None,
                                del_iothread_result=None, volume_kwargs=None):
    vm = vm_plugin.Vm()
    vm.uuid = 'vm-uuid'
    vm.domain = FakeDetachDomain()
    vm.domain_xml = controller_xml
    volume_args = {
        'useVirtio': False,
        'useVirtioSCSI': True,
        'installPath': 'cbd:test-volume',
        'volumeUuid': 'volume-uuid',
    }
    volume_args.update(volume_kwargs or {})
    detached_aliases = []
    deleted_iothreads = []
    stub_detach_volume_dependencies(
        monkeypatch, vm, disk_xml, current_xmls, detached_aliases, deleted_iothreads,
        wait_callback_success, detach_controller_result, del_iothread_result)
    return DetachVolumeCleanupContext(vm, cbd_volume(**volume_args), detached_aliases, deleted_iothreads)


@pytest.mark.kvmagent
def test_is_virtio_blk_excludes_virtio_scsi():
    assert vm_plugin.is_virtio_blk(cbd_volume(useVirtio=True, useVirtioSCSI=False))
    assert not vm_plugin.is_virtio_blk(cbd_volume(useVirtio=True, useVirtioSCSI=True))
    assert not vm_plugin.is_virtio_blk(cbd_volume(useVirtio=False, useVirtioSCSI=False))


@pytest.mark.kvmagent
def test_iothread_vq_mapping_allocator_distributes_queues_to_larger_iothread_ids_first():
    volume = cbd_volume(ioThreads=7)

    allocator = vm_plugin.IothreadVqMappingAllocator.allocate(volume, set())

    assert allocator.iothread_ids == [101, 102, 103, 104, 105, 106, 107]
    assert allocator.queue_ids_by_iothread[101] == [0, 1]
    assert allocator.queue_ids_by_iothread[102] == [2, 3]
    assert allocator.queue_ids_by_iothread[103] == [4, 5]
    assert allocator.queue_ids_by_iothread[104] == [6, 7]
    assert allocator.queue_ids_by_iothread[105] == [8, 9]
    assert allocator.queue_ids_by_iothread[106] == [10, 11, 12]
    assert allocator.queue_ids_by_iothread[107] == [13, 14, 15]


@pytest.mark.kvmagent
def test_iothread_vq_mapping_allocator_uses_one_iothread_per_queue_when_count_matches_queue_count():
    volume = cbd_volume(multiQueues='8', ioThreads=8)

    allocator = vm_plugin.IothreadVqMappingAllocator.allocate(volume, set())

    assert allocator.iothread_ids == [101, 102, 103, 104, 105, 106, 107, 108]
    assert allocator.queue_ids_by_iothread[101] == [0]
    assert allocator.queue_ids_by_iothread[108] == [7]


@pytest.mark.kvmagent
def test_iothread_vq_mapping_allocator_avoids_existing_iothread_ids():
    volume = cbd_volume(multiQueues='4', ioThreads=4)

    allocator = vm_plugin.IothreadVqMappingAllocator.allocate(volume, set([101, 103]))

    assert allocator.iothread_ids == [102, 104, 105, 106]


@pytest.mark.kvmagent
def test_iothread_vq_mapping_allocator_reports_id_exhaustion():
    used_ids = set(range(vm_plugin.AUTOMATIC_IOTHREAD_ID_START, vm_plugin.AUTOMATIC_IOTHREAD_ID_LIMIT + 1))

    with pytest.raises(Exception) as exc:
        vm_plugin.IothreadVqMappingAllocator.allocate_iothread_ids(1, used_ids)

    assert 'no id available' in str(exc.value)


@pytest.mark.kvmagent
def test_prepare_scsi_controller_indexes_reuses_manual_iothread_controller():
    volume1 = cbd_volume(useVirtio=False, useVirtioSCSI=True, ioThreadId=101, deviceId=1)
    volume2 = cbd_volume(volumeUuid='volume-uuid-2', useVirtio=False, useVirtioSCSI=True, ioThreadId=101, deviceId=2)

    vm_plugin.IothreadVqMappingAllocator.prepare_scsi_controller_indexes([volume1, volume2])

    assert volume1.controllerIndex == 1
    assert volume2.controllerIndex == 1


@pytest.mark.kvmagent
def test_manual_iothread_pin_disables_automatic_iothread_vq_mapping():
    volume = cbd_volume(ioThreadId=3)

    assert vm_plugin.IothreadVqMappingAllocator.allocate(volume, set()) is None


@pytest.mark.kvmagent
def test_missing_iothreads_disables_automatic_iothread_vq_mapping():
    volume = cbd_volume()
    delattr(volume, 'ioThreads')

    assert vm_plugin.IothreadVqMappingAllocator.allocate(volume, set()) is None


@pytest.mark.kvmagent
def test_non_cbd_volume_can_use_dedicated_scsi_controller_without_automatic_mapping():
    volume = cbd_volume(deviceType='ceph', useVirtio=False, useVirtioSCSI=True, multiQueues='4')

    assert vm_plugin.IothreadVqMappingAllocator.needs_automatic_mapping(volume) is False
    assert vm_plugin.IothreadVqMappingAllocator.needs_dedicated_scsi_controller(volume) is True


@pytest.mark.kvmagent
def test_set_device_address_ignores_conflicting_virtio_scsi_persisted_controller():
    disk = disk_with_target('scsi')
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=True,
        multiQueues='0',
        ioThreads=0,
        ioThreadId=0,
        controllerIndex=1,
        deviceAddress=drive_address(1, 1),
    )

    vm_plugin.Vm.set_device_address(disk, volume)

    address = disk.find('address')
    assert address.get('type') == 'drive'
    assert address.get('controller') == '0'
    assert address.get('unit') == str(vm_plugin.Vm.get_device_unit(volume.deviceId))


@pytest.mark.kvmagent
def test_set_device_address_ignores_non_virtio_scsi_persisted_controller():
    disk = disk_with_target('scsi')
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=False,
        multiQueues='0',
        ioThreads=0,
        ioThreadId=0,
        controllerIndex=1,
        deviceAddress=drive_address(1, 1),
    )

    vm_plugin.Vm.set_device_address(disk, volume)

    address = disk.find('address')
    assert address.get('type') == 'drive'
    assert address.get('controller') == '0'
    assert address.get('unit') == str(vm_plugin.Vm.get_device_unit(volume.deviceId))


@pytest.mark.kvmagent
def test_set_device_address_reuses_matching_virtio_scsi_persisted_controller():
    disk = disk_with_target('scsi')
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=True,
        multiQueues='4',
        ioThreads=4,
        ioThreadId=0,
        controllerIndex=1,
        deviceAddress=drive_address(1, 7),
    )

    vm_plugin.Vm.set_device_address(disk, volume)

    address = disk.find('address')
    assert address.get('type') == 'drive'
    assert address.get('controller') == '1'
    assert address.get('unit') == '7'


@pytest.mark.kvmagent
def test_set_device_address_ignores_default_controller_when_dedicated_plan_exists():
    disk = disk_with_target('scsi')
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=True,
        multiQueues='4',
        ioThreads=4,
        ioThreadId=0,
        controllerIndex=1,
        deviceAddress=drive_address(0, 5),
    )

    vm_plugin.Vm.set_device_address(disk, volume)

    address = disk.find('address')
    assert address.get('type') == 'drive'
    assert address.get('controller') == '1'
    assert address.get('unit') == str(vm_plugin.Vm.get_device_unit(volume.deviceId))


@pytest.mark.kvmagent
def test_set_device_address_ignores_mismatched_dedicated_persisted_controller():
    disk = disk_with_target('scsi')
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=True,
        multiQueues='4',
        ioThreads=4,
        ioThreadId=0,
        controllerIndex=2,
        deviceAddress=drive_address(1, 7),
    )

    vm_plugin.Vm.set_device_address(disk, volume)

    address = disk.find('address')
    assert address.get('type') == 'drive'
    assert address.get('controller') == '2'
    assert address.get('unit') == str(vm_plugin.Vm.get_device_unit(volume.deviceId))


@pytest.mark.kvmagent
def test_set_device_address_checks_occupied_units_on_dedicated_controller():
    class FakeAttachVm(object):
        def get_occupied_disk_address_units(self, bus, controller):
            assert bus == 'scsi'
            assert controller == 2
            return [vm_plugin.Vm.get_device_unit(1)]

    disk = disk_with_target('scsi')
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=True,
        multiQueues='4',
        ioThreads=4,
        ioThreadId=0,
        controllerIndex=2,
        deviceAddress=drive_address(1, 7),
    )

    vm_plugin.Vm.set_device_address(disk, volume, FakeAttachVm())

    address = disk.find('address')
    assert address.get('type') == 'drive'
    assert address.get('controller') == '2'
    assert address.get('unit') == str(vm_plugin.Vm.get_device_unit(1) + 1)


@pytest.mark.kvmagent
def test_set_device_address_falls_back_to_default_controller_and_bumps_occupied_unit():
    class FakeAttachVm(object):
        def get_occupied_disk_address_units(self, bus, controller):
            assert bus == 'scsi'
            assert controller == 0
            return [vm_plugin.Vm.get_device_unit(1)]

    disk = disk_with_target('scsi')
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=True,
        multiQueues='0',
        ioThreads=0,
        ioThreadId=0,
        controllerIndex=1,
        deviceAddress=drive_address(1, 1),
    )

    vm_plugin.Vm.set_device_address(disk, volume, FakeAttachVm())

    address = disk.find('address')
    assert address.get('type') == 'drive'
    assert address.get('controller') == '0'
    assert address.get('unit') == str(vm_plugin.Vm.get_device_unit(1) + 1)


@pytest.mark.kvmagent
def test_set_device_address_keeps_default_virtio_scsi_persisted_controller():
    disk = disk_with_target('scsi')
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=True,
        multiQueues='0',
        ioThreads=0,
        ioThreadId=0,
        deviceAddress=drive_address(0, 5),
    )

    vm_plugin.Vm.set_device_address(disk, volume)

    address = disk.find('address')
    assert address.get('type') == 'drive'
    assert address.get('controller') == '0'
    assert address.get('unit') == '5'


@pytest.mark.kvmagent
@pytest.mark.parametrize('controller, unit', [
    (None, 5),
    ('', 5),
    (0, None),
    (0, ''),
])
def test_set_device_address_replans_incomplete_virtio_scsi_persisted_drive_address(controller, unit):
    disk = disk_with_target('scsi')
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=True,
        multiQueues='0',
        ioThreads=0,
        ioThreadId=0,
        deviceAddress=Volume(type='drive', controller=controller, unit=unit),
    )

    vm_plugin.Vm.set_device_address(disk, volume)

    address = disk.find('address')
    assert address.get('type') == 'drive'
    assert address.get('controller') == '0'
    assert address.get('unit') == str(vm_plugin.Vm.get_device_unit(volume.deviceId))


@pytest.mark.kvmagent
def test_set_device_address_keeps_virtio_blk_pci_address():
    disk = disk_with_target('virtio')
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=False,
        deviceAddress=pci_address(slot='0x09'),
    )

    vm_plugin.Vm.set_device_address(disk, volume)

    address = disk.find('address')
    assert address.get('type') == 'pci'
    assert address.get('slot') == '0x09'


@pytest.mark.kvmagent
def test_iothread_vq_mapping_allocator_writes_individual_queues():
    volume = cbd_volume(ioThreads=7)
    allocator = vm_plugin.IothreadVqMappingAllocator.allocate(volume, set())
    driver = vm_plugin.etree.Element('driver')

    vm_plugin.IothreadVqMappingAllocator.apply(driver, allocator)

    iothreads = driver.findall('./iothreads/iothread')
    assert iothreads[-2].get('id') == '106'
    assert [q.get('id') for q in iothreads[-2].findall('queue')] == ['10', '11', '12']
    assert iothreads[-1].get('id') == '107'
    assert [q.get('id') for q in iothreads[-1].findall('queue')] == ['13', '14', '15']


@pytest.mark.kvmagent
def test_get_new_cbd_disk_keeps_existing_iothread_vq_mapping_for_migration():
    old_disk = vm_plugin.etree.fromstring('''
    <disk type="network" device="disk">
      <driver name="qemu" type="raw" cache="none" discard="unmap" queues="4">
        <iothreads>
          <iothread id="101"><queue id="0-1"/></iothread>
          <iothread id="102"><queue id="2-3"/></iothread>
        </iothreads>
      </driver>
      <source protocol="cbd" name="old"/>
      <target dev="vdb" bus="virtio"/>
    </disk>
    ''')
    volume = cbd_volume(
        installPath='cbd:new-volume',
        dev_letter='b',
        multiQueues=None,
        ioThreads=None,
        physicalBlockSize=None,
    )

    new_disk = vm_plugin.VmPlugin._get_new_disk(old_disk, volume)

    driver = new_disk.find('driver')
    assert driver.get('queues') == '4'
    iothreads = driver.findall('./iothreads/iothread')
    assert [i.get('id') for i in iothreads] == ['101', '102']
    assert [q.get('id') for q in iothreads[0].findall('queue')] == ['0', '1']
    assert [q.get('id') for q in iothreads[1].findall('queue')] == ['2', '3']


def migration_domain_with_virtio_disks(count=1, queues='4'):
    driver_queues = '' if queues is None else ' queues="%s"' % queues
    disks = ''.join([
        '''
        <disk type="network" device="disk">
          <driver name="qemu" type="raw" cache="none" discard="unmap"%s/>
          <source protocol="cbd" name="old-%s"/>
          <target dev="vd%s" bus="virtio"/>
        </disk>
        ''' % (driver_queues, index, chr(ord('a') + index))
        for index in range(count)
    ])
    return vm_plugin.etree.fromstring('<domain><devices>%s</devices></domain>' % disks)


@pytest.mark.kvmagent
def test_migration_cbd_disk_allocates_iothread_vq_mapping_from_driver_queues():
    root = migration_domain_with_virtio_disks()
    disk = root.find('./devices/disk')
    volume = cbd_volume(multiQueues='16', ioThreads=2)

    vm_plugin.VmPlugin._apply_migration_iothread_vq_mapping(root, disk, volume)

    driver = disk.find('driver')
    assert driver.get('queues') == '4'
    iothreads = driver.findall('./iothreads/iothread')
    assert [i.get('id') for i in iothreads] == ['101', '102']
    assert [q.get('id') for q in iothreads[0].findall('queue')] == ['0', '1']
    assert [q.get('id') for q in iothreads[1].findall('queue')] == ['2', '3']
    assert root.find('iothreads').text == '2'
    assert [i.get('id') for i in root.findall('./iothreadids/iothread')] == ['101', '102']


@pytest.mark.kvmagent
def test_migration_cbd_disk_without_driver_queues_does_not_allocate_iothread_vq_mapping():
    root = migration_domain_with_virtio_disks(queues=None)
    disk = root.find('./devices/disk')
    volume = cbd_volume(multiQueues='16', ioThreads=2)

    vm_plugin.VmPlugin._apply_migration_iothread_vq_mapping(root, disk, volume)

    assert disk.find('./driver/iothreads') is None
    assert root.find('iothreads') is None
    assert root.find('iothreadids') is None


@pytest.mark.kvmagent
def test_migration_cbd_disks_allocate_distinct_iothread_ids():
    root = migration_domain_with_virtio_disks(count=2)
    volume = cbd_volume(multiQueues='16', ioThreads=2)

    for disk in root.findall('./devices/disk'):
        vm_plugin.VmPlugin._apply_migration_iothread_vq_mapping(root, disk, volume)

    disk_iothread_ids = [
        [i.get('id') for i in disk.findall('./driver/iothreads/iothread')]
        for disk in root.findall('./devices/disk')
    ]
    assert disk_iothread_ids == [['101', '102'], ['103', '104']]
    assert root.find('iothreads').text == '4'
    assert [i.get('id') for i in root.findall('./iothreadids/iothread')] == ['101', '102', '103', '104']


@pytest.mark.kvmagent
def test_get_new_cbd_scsi_disk_does_not_write_queues_on_disk_driver():
    old_disk = vm_plugin.etree.fromstring('''
    <disk type="network" device="disk">
      <driver name="qemu" type="raw" cache="none" discard="unmap"/>
      <source protocol="cbd" name="old"/>
      <target dev="sdb" bus="scsi"/>
    </disk>
    ''')
    volume = cbd_volume(
        installPath='cbd:new-volume',
        dev_letter='b',
        useVirtio=True,
        useVirtioSCSI=True,
        multiQueues='4',
        physicalBlockSize=None,
        wwn='123456789abcdef0',
    )

    new_disk = vm_plugin.VmPlugin._get_new_disk(old_disk, volume)

    driver = new_disk.find('driver')
    assert driver.get('queues') is None
    assert driver.find('iothreads') is None
    assert new_disk.find('target').get('bus') == 'scsi'


@pytest.mark.kvmagent
def test_migration_cbd_scsi_controller_allocates_iothread_vq_mapping_from_controller_queues():
    root = vm_plugin.etree.fromstring('''
    <domain>
      <devices>
        <controller type="scsi" model="virtio-scsi" index="1">
          <driver queues="4"/>
          <alias name="scsi1"/>
        </controller>
        <disk type="network" device="disk">
          <driver name="qemu" type="raw" cache="none" discard="unmap"/>
          <source protocol="cbd" name="old"/>
          <target dev="sdb" bus="scsi"/>
          <address type="drive" controller="1"/>
        </disk>
      </devices>
    </domain>
    ''')
    old_disk = root.find('./devices/disk')
    volume = cbd_volume(
        installPath='cbd:new-volume',
        dev_letter='b',
        useVirtio=True,
        useVirtioSCSI=False,
        multiQueues='16',
        ioThreads=2,
        physicalBlockSize=None,
        wwn='123456789abcdef0',
    )

    new_disk = vm_plugin.VmPlugin._get_new_disk(old_disk, volume)
    vm_plugin.VmPlugin._apply_migration_iothread_vq_mapping(root, new_disk, volume)

    disk_driver = new_disk.find('driver')
    controller_driver = root.find('./devices/controller/driver')
    iothreads = controller_driver.findall('./iothreads/iothread')
    assert disk_driver.get('queues') is None
    assert disk_driver.find('iothreads') is None
    assert controller_driver.get('queues') == '4'
    assert [i.get('id') for i in iothreads] == ['101', '102']
    assert [q.get('id') for q in iothreads[0].findall('queue')] == ['0', '1']
    assert [q.get('id') for q in iothreads[1].findall('queue')] == ['2', '3']
    assert root.find('iothreads').text == '2'
    assert [i.get('id') for i in root.findall('./iothreadids/iothread')] == ['101', '102']


@pytest.mark.kvmagent
def test_add_scsi_controller_records_alias_before_attach(monkeypatch):
    class FakeDomain(object):
        def attachDeviceFlags(self, xml, flags):
            raise RuntimeError('attach failed')

    class FakeVm(object):
        domain = FakeDomain()

        def find_scsi_controller_by_iothread(self, io_thread_id):
            return "0"

    aliases = []
    monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', lambda uuid: FakeVm())
    monkeypatch.setattr(vm_plugin.VmPlugin, 'get_next_scsi_controller_index', staticmethod(lambda vm: 3))

    with pytest.raises(RuntimeError):
        vm_plugin.VmPlugin.add_scsi_controller_with_driver('vm-uuid', queues=4, created_aliases=aliases)

    assert aliases == ['scsi3']


@pytest.mark.kvmagent
def test_attach_data_volume_failure_cleans_created_mapping(monkeypatch):
    attached_disk_xml = []

    class FakeDomain(object):
        def attachDeviceFlags(self, xml, flags):
            attached_disk_xml.append(xml)
            raise RuntimeError('disk attach failed')

    vm = vm_plugin.Vm()
    vm.uuid = 'vm-uuid'
    vm.domain = FakeDomain()
    volume = cbd_volume(
        useVirtio=True,
        useVirtioSCSI=True,
        installPath='cbd:test-volume',
        wwn='123456789abcdef0',
        physicalBlockSize=None,
    )
    created_iothreads = []
    deleted_iothreads = []
    detached_aliases = []

    def fake_add_controller(vm_uuid, io_thread_id=None, queues=None, mapping_allocator=None, created_aliases=None):
        created_aliases.append('scsi5')
        return 5

    monkeypatch.setattr(vm_plugin.linux, 'retry', no_retry)
    monkeypatch.setattr(vm_plugin.linux, 'wait_callback_success', lambda callback, *args: callback(None))
    monkeypatch.setattr(vm_plugin.libvirt, 'libvirtError', RuntimeError)
    monkeypatch.setattr(vm_plugin, 'file_volume_check', lambda v: v)
    monkeypatch.setattr(vm_plugin, 'get_vm_by_uuid', lambda uuid: FakeVm(CLEAN_DOMAIN_XML))
    monkeypatch.setattr(vm_plugin.Vm, 'set_device_address', staticmethod(lambda *args: None))
    monkeypatch.setattr(vm_plugin.VmPlugin, 'get_iothread_info', staticmethod(lambda uuid: []))
    monkeypatch.setattr(vm_plugin.VmPlugin, 'add_io_thread',
                        staticmethod(lambda uuid, iothread_id: created_iothreads.append(iothread_id) or None))
    monkeypatch.setattr(vm_plugin.VmPlugin, 'del_io_thread',
                        staticmethod(lambda uuid, iothread_id: deleted_iothreads.append(iothread_id) or None))
    monkeypatch.setattr(vm_plugin.VmPlugin, 'add_scsi_controller_with_driver', staticmethod(fake_add_controller))
    monkeypatch.setattr(vm, 'detach_controller_by_alias',
                        lambda alias: detached_aliases.append(alias) or None)

    with pytest.raises(vm_plugin.kvmagent.KvmError):
        vm._attach_data_volume(volume, EmptyAddons())

    assert created_iothreads == [101, 102, 103, 104, 105, 106, 107, 108]
    assert sorted(deleted_iothreads) == created_iothreads
    assert detached_aliases == ['scsi5']
    disk = vm_plugin.etree.fromstring(attached_disk_xml[0])
    assert disk.find('driver').get('queues') is None
    assert disk.find('driver').find('iothreads') is None
    assert disk.find('target').get('bus') == 'scsi'


@pytest.mark.kvmagent
def test_detach_data_volume_keeps_referenced_iothread(monkeypatch):
    controller_xml = scsi_controller_domain_xml([101, 102], queues='16')
    referenced_xml = domain_xml_with_iothread_disk([101])
    ctx = setup_detach_volume_cleanup(
        monkeypatch, controller_xml, scsi_disk_xml([101, 102]), [CLEAN_DOMAIN_XML, controller_xml, referenced_xml])

    ctx.vm._detach_data_volume(ctx.volume)

    assert ctx.detached_aliases == ['scsi1']
    assert ctx.deleted_iothreads == [102]


@pytest.mark.kvmagent
def test_detach_data_volume_keeps_controller_with_attached_disk(monkeypatch):
    still_attached_disk_xml = scsi_disk_xml([101], dev='sdc')
    controller_xml = scsi_controller_domain_xml([101])
    still_attached_xml = scsi_controller_domain_xml([101], extra_devices=still_attached_disk_xml)
    ctx = setup_detach_volume_cleanup(
        monkeypatch, controller_xml, scsi_disk_xml([101]), [CLEAN_DOMAIN_XML, still_attached_xml])

    ctx.vm._detach_data_volume(ctx.volume)

    assert ctx.detached_aliases == []
    assert ctx.deleted_iothreads == []


@pytest.mark.kvmagent
def test_detach_data_volume_retries_iothread_cleanup_after_stale_reference(monkeypatch):
    controller_xml = scsi_controller_domain_xml([101])
    ctx = setup_detach_volume_cleanup(
        monkeypatch, controller_xml, scsi_disk_xml([101]),
        [CLEAN_DOMAIN_XML, controller_xml, controller_xml, CLEAN_DOMAIN_XML],
        fake_wait_callback_success)

    ctx.vm._detach_data_volume(ctx.volume)

    assert ctx.detached_aliases == ['scsi1']
    assert ctx.deleted_iothreads == [101]


@pytest.mark.kvmagent
def test_detach_data_volume_waits_for_controller_cleanup_without_iothreads(monkeypatch):
    controller_xml = scsi_controller_domain_xml([])
    ctx = setup_detach_volume_cleanup(
        monkeypatch, controller_xml, scsi_disk_xml([]),
        [CLEAN_DOMAIN_XML, controller_xml, controller_xml, CLEAN_DOMAIN_XML],
        fake_wait_callback_success)

    ctx.vm._detach_data_volume(ctx.volume)

    assert ctx.detached_aliases == ['scsi1']
    assert ctx.deleted_iothreads == []


@pytest.mark.kvmagent
def test_detach_data_volume_waits_after_controller_cleanup_command_error(monkeypatch):
    controller_xml = scsi_controller_domain_xml([101])
    ctx = setup_detach_volume_cleanup(
        monkeypatch, controller_xml, scsi_disk_xml([101]),
        [CLEAN_DOMAIN_XML, controller_xml, controller_xml, CLEAN_DOMAIN_XML],
        fake_wait_callback_success,
        detach_controller_result='error: detach failed')

    ctx.vm._detach_data_volume(ctx.volume)

    assert ctx.detached_aliases == ['scsi1']
    assert ctx.deleted_iothreads == [101]


@pytest.mark.kvmagent
def test_detach_data_volume_reports_iothread_cleanup_command_error(monkeypatch):
    controller_xml = scsi_controller_domain_xml([101])
    ctx = setup_detach_volume_cleanup(
        monkeypatch, controller_xml, scsi_disk_xml([101]), [CLEAN_DOMAIN_XML, CLEAN_DOMAIN_XML, CLEAN_DOMAIN_XML],
        fake_wait_callback_success,
        del_iothread_result='error: iothreaddel failed')

    ctx.vm._detach_data_volume(ctx.volume)

    assert ctx.detached_aliases == ['scsi1']
    assert set(ctx.deleted_iothreads) == set([101])
