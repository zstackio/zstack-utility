import ast
import imp
import json
import os
import re
import shlex
import types
import unittest
from distutils.version import LooseVersion
from xml.etree import ElementTree as ET


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))


class Namespace(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Logger(object):
    def __getattr__(self, name):
        return lambda *args: None


def load_functions(path, names, scope, owner=None):
    with open(path) as source:
        tree = ast.parse(source.read(), filename=path)
    if owner:
        tree = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner)
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in nodes:
        node.decorator_list = []
    assert len(nodes) == len(names)
    eval(compile(ast.Module(body=nodes), path, 'exec'), scope)


class IsoTrayTest(unittest.TestCase):
    def setUp(self):
        self.xmlobject = imp.load_source('iso_xmlobject', os.path.join(ROOT, 'zstacklib/zstacklib/utils/xmlobject.py'))
        logger = Logger()
        self.qmp_scope = dict(json=json, re=re, LooseVersion=LooseVersion, QEMU_VERSION='6.2.0', logger=logger)
        load_functions(os.path.join(ROOT, 'zstacklib/zstacklib/utils/qmp.py'),
                       ['execute_qmp_command', 'qmp_subcmd'], self.qmp_scope)
        self.qmp = Namespace(**self.qmp_scope)
        libvirt = Namespace(libvirtError=RuntimeError, VIR_DOMAIN_AFFECT_LIVE=1, VIR_DOMAIN_DEVICE_MODIFY_FORCE=4)
        self.scope = dict(json=json, logger=logger, xmlobject=self.xmlobject, etree=ET, qmp=self.qmp,
                          libvirt=libvirt, LIBVIRT_MAJOR_VERSION=8, HOST_ARCH='x86_64',
                          get_volume_actual_installpath=lambda path: path,
                          linux=Namespace(wait_callback_success=lambda check, *args: check(None)),
                          kvmagent=Namespace(KvmError=RuntimeError))
        path = os.path.join(ROOT, 'kvmagent/kvmagent/plugins/vm_plugin.py')
        load_functions(path, ['find_domain_cdrom_alias_name', 'find_domain_cdrom_address', 'e',
                              'iso_check', 'get_vm_blocks', 'execute_qmp_command'], self.scope)
        methods = dict(self.scope)
        names = ['open_cdrom_tray', 'attach_iso', 'detach_iso', '_get_controller_type', '_get_iso_target_dev']
        load_functions(path, names, methods, 'Vm')
        self.Vm = type('Vm', (object,), dict((name, methods[name]) for name in names))
        self.Vm._get_iso_target_dev = staticmethod(methods['_get_iso_target_dev'])
        self.Vm.ISO_DEVICE_LETTERS = ['c', 'd', 'e']
        self.Vm.disk_source_attrname = {'file': 'file'}
        self.scope['Vm'] = methods['Vm'] = self.Vm
        self.vm = self.Vm()
        self.vm.uuid = 'vm-iso-tray'
        self.calls = []

    def test_repeated_changes_open_only_selected_device(self):
        self.check_iso_changes()

    def test_qmp_failures_allow_iso_changes(self):
        for command in ['query-block', 'blockdev-open-tray']:
            self.check_iso_changes(command)

    def test_malformed_qmp_responses_allow_iso_changes(self):
        for command in ['query-block', 'blockdev-open-tray']:
            for body in ['not-json', '{}']:
                self.check_iso_changes(command, (0, body, ''))

    def check_iso_changes(self, failed_command=None, failure=(1, '', 'monitor failed')):
        self.calls = []
        for bus, machine, arch in [('ide', 'pc-i440fx-rhel7.6.0', 'x86_64'),
                                   ('sata', 'pc-q35-rhel8.6.0', 'x86_64'),
                                   ('scsi', 'virt', 'aarch64')]:
            self.scope['HOST_ARCH'] = self.Vm._get_iso_target_dev.__globals__['HOST_ARCH'] = arch
            self.Vm.attach_iso.__globals__['HOST_ARCH'] = arch
            root = ET.fromstring('<domain><os><type machine="%s"/></os><devices/></domain>' % machine)
            disks, blocks = [], []
            for index, letter in enumerate(self.Vm.ISO_DEVICE_LETTERS):
                disk = ET.SubElement(root.find('devices'), 'disk', device='cdrom', type='file')
                ET.SubElement(disk, 'target', dev=self.Vm._get_iso_target_dev(letter), bus=bus)
                alias = '%s0-0-%d' % (bus, index + 1)
                ET.SubElement(disk, 'alias', name=alias)
                ET.SubElement(disk, 'address', type='drive', controller='0', bus='0', target='0', unit=str(index + 1))
                disks.append(disk)
                blocks.append(dict(qdev=alias, tray_open=False))

            def monitor(command):
                args = shlex.split(command)
                self.assertEqual(args[:3], ['virsh', 'qemu-monitor-command', self.vm.uuid])
                request = json.loads(args[3])
                self.calls.append(request)
                if request['execute'] == failed_command:
                    return failure
                if request['execute'] == 'query-block':
                    return 0, json.dumps({'return': blocks}), ''
                self.assertEqual(request['execute'], 'blockdev-open-tray')
                selected = [b for b in blocks if b['qdev'] == request['arguments']['id']]
                self.assertEqual(len(selected), 1)
                selected[0]['tray_open'] = True
                return 0, '{"return": {}, "id": "libvirt-909"}', ''

            def update(xml, flags):
                requested = ET.fromstring(xml)
                index = next(i for i, d in enumerate(disks) if d.find('target').get('dev') == requested.find('target').get('dev'))
                self.assertEqual([b['tray_open'] for b in blocks],
                                 [False] * 3 if failed_command else [i == index for i in range(3)])
                if disks[index].find('source') is not None:
                    disks[index].remove(disks[index].find('source'))
                if requested.find('source') is not None:
                    disks[index].append(requested.find('source'))
                blocks[index]['tray_open'] = False
                self.vm.domain_xmlobject = self.xmlobject.loads(ET.tostring(root))

            self.qmp_scope['bash'] = Namespace(bash_roe=monitor)
            self.vm.domain = Namespace(XMLDesc=lambda flags: ET.tostring(root), updateDeviceFlags=update)
            self.vm.domain_xmlobject = self.xmlobject.loads(ET.tostring(root))
            self.scope['get_vm_by_uuid'] = self.Vm.attach_iso.__globals__['get_vm_by_uuid'] = lambda uuid: self.vm
            for repeat in range(2):
                for action in ['attach_iso', 'detach_iso']:
                    for index in range(3):
                        iso = Namespace(deviceId=index, path='/test.iso', isEmpty=False, protocol=None)
                        getattr(self.vm, action)(Namespace(vmUuid=self.vm.uuid, deviceId=index, iso=iso))
        self.assertEqual(len(self.calls), 36 if failed_command == 'query-block' else 72)

    def test_missing_alias(self):
        for disk in ['', '<disk device="disk"><target dev="hdc"/></disk>', '<disk device="cdrom"/>',
                     '<disk device="cdrom"><target dev="hdd"/></disk>', '<disk device="cdrom"><target dev="hdc"/></disk>']:
            self.assertIsNone(self.scope['find_domain_cdrom_alias_name']('<domain><devices>%s</devices></domain>' % disk, 'hdc'))

    def test_unidentified_device_is_skipped(self):
        def unexpected(command):
            self.fail('An unidentified tray must not be opened')
        self.qmp_scope['bash'] = Namespace(bash_roe=unexpected)
        for alias, blocks in [(None, []), ('ide0-0-1', []), ('ide0-0-1', [dict(qdev='ide0-0-2', tray_open=False)]),
                              ('ide0-0-1', [dict(qdev='ide0-0-1')]), ('ide0-0-1', [dict(tray_open=False)])]:
            self.Vm.open_cdrom_tray.__globals__['get_vm_blocks'] = lambda uuid: blocks
            self.vm.open_cdrom_tray(self.vm.uuid, alias)

    def test_qmp_failures_allow_existing_fallback(self):
        for response in [(1, '', 'failed'), (0, '{"error":{"class":"DeviceNotFound"}}', '')]:
            self.qmp_scope['bash'] = Namespace(bash_roe=lambda command: response)
            self.vm.open_cdrom_tray(self.vm.uuid, 'ide0-0-1')
            self.Vm.open_cdrom_tray.__globals__['get_vm_blocks'] = lambda uuid: [dict(qdev='ide0-0-1', tray_open=False)]
            self.vm.open_cdrom_tray(self.vm.uuid, 'ide0-0-1')


if __name__ == '__main__':
    unittest.main()
