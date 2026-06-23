import ast
import os
import unittest

from lxml import etree


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))


class Namespace(object):
    def __init__(self, **values):
        self.__dict__.update(values)

    def hasattr(self, name):
        return hasattr(self, name)


class DomainVolume(object):
    @classmethod
    def from_xmlobject(cls, disk):
        return cls()

    def over_incorrect_driver(self):
        return False


class MigrationDiskQueuesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.path.join(ROOT, 'kvmagent/kvmagent/plugins/vm_plugin.py')
        with open(path) as source:
            tree = ast.parse(source.read(), filename=path)
        names = ['e', 'VirtioCeph', 'VirtioSCSICeph', 'BlkCeph']
        nodes = [node for node in tree.body if getattr(node, 'name', None) in names]
        for owner, name in [('VmPlugin', '_get_new_disk'), ('Vm', '_build_domain_new_xml')]:
            parent = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner)
            method = next(node for node in parent.body if isinstance(node, ast.FunctionDef) and node.name == name)
            method.decorator_list = []
            nodes.append(method)
        scope = dict(etree=etree, ZS_XML_NAMESPACE='http://zstack.org', DomainVolume=DomainVolume,
                     file_volume_check=lambda volume: volume, logger=Namespace(info=lambda *args: None))
        eval(compile(ast.Module(body=nodes), path, 'exec'), scope)
        scope['VmPlugin'] = Namespace(_get_new_disk=scope['_get_new_disk'])
        cls.rebuild = staticmethod(scope['_get_new_disk'])
        cls.rebuild_domain = staticmethod(scope['_build_domain_new_xml'])

    def volume(self, kind, queues=None, backing=False, cdrom=False):
        chain = None
        if backing:
            chain = Namespace(
                _origin_xml_obj=etree.fromstring('<backingStore type="block"><source dev="/dev/base"/></backingStore>'),
                update_backing_store_type_to_block=lambda: None)
        return Namespace(deviceType=kind, format='qcow2', cacheMode='none',
                         installPath=dict(file='/new/data.qcow2', block='/dev/new', ceph='ceph://pool/new')[kind],
                         backing_store=chain, dvbs=chain, useVirtio=True, useVirtioSCSI=False,
                         multiQueues=queues, ioThreadId=None, physicalBlockSize=None, is_cdrom=cdrom,
                         secretUuid=None, monInfo=[], shareable=False, wwn='wwn-test')

    def disk(self, queues=None, bus='virtio', cdrom=False, nbd=False):
        root = etree.fromstring('''<disk type="block" device="disk">
          <driver name="qemu" type="qcow2" cache="none"/>
          <source dev="/dev/old"/><target dev="vdb" bus="virtio"/>
          <boot order="2"/><alias name="ua-data"/>
          <address type="pci" domain="0x0000" bus="0x00" slot="0x08" function="0x0"/>
          <wwn>wwn-test</wwn><serial>serial-test</serial>
        </disk>''')
        if queues is not None:
            root.find('driver').set('queues', queues)
        root.find('target').set('bus', bus)
        if cdrom:
            root.set('device', 'cdrom')
        if nbd:
            root.set('type', 'network')
            root.find('source').attrib.clear()
            root.find('source').attrib.update({'protocol': 'nbd', 'name': 'old'})
        return root

    def test_preserves_source_queues_for_each_backend(self):
        for kind in ['file', 'block', 'ceph']:
            for queues in ['4', '64']:
                result = self.rebuild(self.disk(queues), self.volume(kind))
                self.assertEqual(result.find('driver').get('queues'), queues, kind)

    def test_source_queues_override_current_target_config(self):
        for kind in ['file', 'block', 'ceph']:
            result = self.rebuild(self.disk('4'), self.volume(kind, '64'))
            self.assertEqual(result.find('driver').get('queues'), '4', kind)

    def test_absent_source_queues_never_uses_target_config(self):
        for kind in ['file', 'block', 'ceph']:
            for queues in ['64', None]:
                result = self.rebuild(self.disk(), self.volume(kind, queues))
                self.assertIsNone(result.find('driver').get('queues'), kind)

    def test_absent_source_driver_does_not_inject_queues(self):
        for kind in ['file', 'block', 'ceph']:
            old = self.disk()
            old.remove(old.find('driver'))
            result = self.rebuild(old, self.volume(kind, '64'))
            self.assertIsNone(result.find('driver').get('queues'), kind)

    def test_keeps_device_metadata_and_backing_store(self):
        for kind in ['file', 'block', 'ceph']:
            old = self.disk('4')
            metadata = dict((tag, etree.tostring(old.find(tag)))
                            for tag in ['target', 'boot', 'alias', 'address', 'wwn', 'serial'])
            result = self.rebuild(old, self.volume(kind, '64', backing=True))
            for tag, expected in metadata.items():
                self.assertEqual(etree.tostring(result.find(tag)), expected, (kind, tag))
            self.assertEqual(result.find('backingStore/source').get('dev'), '/dev/base')
            self.assertEqual(result.find('driver').get('queues'), '4')

    def test_nbd_recovery_keeps_live_queues(self):
        result = self.rebuild(self.disk('4', nbd=True), self.volume('ceph', '64'))
        self.assertEqual(result.find('driver').get('queues'), '4')
        self.assertEqual(result.find('source').get('protocol'), 'rbd')

    def test_non_migrated_disk_is_returned_unchanged(self):
        for queues in [None, '64']:
            old = self.disk(queues)
            self.assertIs(self.rebuild(old, None), old)

    def test_domain_rebuild_preserves_queues_and_other_disks(self):
        for kind in ['file', 'block', 'ceph']:
            changed = self.disk('64')
            unchanged = self.disk()
            unchanged.find('target').set('dev', 'vdc')
            untouched = etree.tostring(unchanged)
            domain = '<domain><devices>' + etree.tostring(changed) + untouched + '</devices></domain>'
            vm = Namespace(get_migratable_xml=lambda: domain, _split_legacy_rbd_snapshot=lambda root: False,
                           _get_target_disk_by_path=lambda path: ('virtio', 'vdb'))
            names, xml = self.rebuild_domain(vm, {'/dev/old': self.volume(kind, '4')})
            disks = etree.fromstring(xml).findall('devices/disk')
            self.assertEqual(list(names), ['vdb'])
            self.assertEqual(disks[0].find('driver').get('queues'), '64')
            self.assertEqual(etree.tostring(disks[1]), untouched)

    def test_scsi_and_cdrom_without_queues_keep_existing_behavior(self):
        result = self.rebuild(self.disk(bus='scsi'), self.volume('file'))
        self.assertEqual(result.find('target').get('bus'), 'scsi')
        self.assertIsNone(result.find('driver').get('queues'))
        result = self.rebuild(self.disk(bus='sata', cdrom=True), self.volume('block', cdrom=True))
        self.assertEqual(result.get('device'), 'cdrom')
        self.assertIsNotNone(result.find('readonly'))
        self.assertIsNone(result.find('driver').get('queues'))


if __name__ == '__main__':
    unittest.main()
