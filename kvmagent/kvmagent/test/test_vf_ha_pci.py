"""Exercise the real HA handler and bond attach path without a libvirt daemon."""
import ast
import json
import logging
from pathlib import Path
import re
import types
import unittest
import xml.etree.ElementTree as ET


class Obj(types.SimpleNamespace):
    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return None

    def put(self, name, value):
        setattr(self, name, value)


def dumps(value):
    return json.dumps(value, default=vars)


def loads(value):
    return json.loads(value, object_hook=lambda fields: Obj(**fields))


source = Path(__file__).resolve().parents[1] / 'plugins/vm_plugin.py'
tree = ast.parse(source.read_text())
ctx = dict(etree=ET, logger=logging.getLogger(__name__),
           e=lambda parent, tag, text=None, attrib=None: ET.SubElement(parent, tag, attrib or {}),
           jsonobject=Obj(loads=loads, dumps=dumps, JsonObject=Obj),
           parse_pci_device_address=lambda address: re.split('[:.]', address),
           normalize_pci_address=lambda address: address,
           ovs=Obj(OvsDpdkSupportVnic=[]), http=Obj(REQUEST_BODY='body'),
           libvirt=Obj(VIR_DOMAIN_AFFECT_LIVE=1),
           linux=Obj(wait_callback_success=lambda callback, **kw: callback(None)),
           ChangeVfNicHaStateRsp=lambda: Obj(success=True, error=None))


def load_method(owner, name):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    method.decorator_list = []
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), ctx)
    return ctx[name]


Vm = type('Vm', (), dict(
    VM_STATE_RUNNING='Running', VM_STATE_PAUSED='Paused',
    _build_interface_xml=staticmethod(load_method('Vm', '_build_interface_xml')),
    _interface_cmd_to_xml=load_method('Vm', '_interface_cmd_to_xml'),
    _attach_vf_bond=load_method('Vm', '_attach_vf_bond')))
ctx['Vm'] = Vm
ha_handler = load_method('VmPlugin', 'set_vf_nic_state')


class VfHaPciTest(unittest.TestCase):
    def nic(self):
        return Obj(type='VF', mac='fa:01:02:03:04:05', nicInternalName='vnic1.0', mtu=1500,
                   bridgeName='br_test', vHostAddOn=Obj(queueNum=1),
                   pciDeviceAddress='0000:17:10.1', extraPciDeviceAddresses=['0000:18:10.1'],
                   pci=Obj(type='pci', domain='0x0000', bus='0x00', slot='0x08', function='0x0'),
                   secondaryPci=Obj(type='pci', domain='0x0000', bus='0x00', slot='0x09', function='0x0'))

    def source_address(self, xml):
        return xml.find('source/address').attrib

    def test_ha_reconnect_and_enable_use_auto_pci_for_single_and_paired_vfs(self):
        for state in ('Reconnecting', 'Enabled'):
            for paired in (False, True):
                with self.subTest(state=state, paired=paired):
                    nic = self.nic()
                    if not paired:
                        nic.extraPciDeviceAddresses = []
                    original = dumps(nic)
                    vm = Obj(uuid='vm', state='Running', domain_xmlobject=Obj(
                        devices=Obj(get_child_node_as_list=lambda _: [])))
                    ctx['get_vm_by_uuid'] = lambda _: vm
                    attached = []
                    plugin = Obj(set_domain_network_device=lambda uuid, xml, operate_type:
                                 attached.append(ET.fromstring(xml)))
                    reply = loads(ha_handler(plugin, {'body': dumps(Obj(vmUuid='vm', nic=nic, haState=state))}))
                    self.assertTrue(reply.success, reply.error)
                    vfs = [xml for xml in attached if xml.get('type') == 'hostdev']
                    self.assertEqual(2 if paired else 1, len(vfs))
                    self.assertEqual(['0x17', '0x18'] if paired else ['0x17'],
                                     [self.source_address(xml)['bus'] for xml in vfs])
                    self.assertTrue(all(xml.find('address').attrib == {'type': 'pci'} for xml in vfs))
                    self.assertEqual(original, dumps(nic))

    def test_user_vm_bond_attach_preserves_distinct_guest_addresses(self):
        for state in ('Running', 'Stopped'):
            with self.subTest(state=state):
                cmd = Obj(nic=self.nic())
                original = dumps(cmd)
                attached = []
                vm = Vm()
                vm.state = state
                vm._vf_device_xml = lambda address: next((xml for xml in attached
                    if self.source_address(xml)['bus'] == '0x' + address.split(':')[1]), None)
                vm.domain = Obj(attachDeviceFlags=lambda xml, flags: attached.append(ET.fromstring(xml)),
                                attachDevice=lambda xml: attached.append(ET.fromstring(xml)))
                vm._attach_vf_bond(cmd)
                self.assertEqual(['0x08', '0x09'], [xml.find('address').get('slot') for xml in attached])
                self.assertEqual(['0x17', '0x18'], [self.source_address(xml)['bus'] for xml in attached])
                self.assertEqual(original, dumps(cmd))


if __name__ == '__main__':
    unittest.main()
