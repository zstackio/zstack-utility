import os
import unittest


def _load_vm_method_source(method_name):
    plugin_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), '..', 'plugins', 'vm_plugin.py'))
    with open(plugin_path, 'r') as fd:
        lines = fd.readlines()

    method_start = None
    for index, line in enumerate(lines):
        if line.startswith('    def %s(' % method_name):
            method_start = index
            break
    if method_start is None:
        raise AssertionError('Vm.%s not found' % method_name)

    start = method_start
    if start and lines[start - 1].startswith('    @'):
        start -= 1

    end = len(lines)
    for index in range(method_start + 1, len(lines)):
        if lines[index].startswith('    def ') or lines[index].startswith('    @'):
            end = index
            break
    return ''.join(lines[start:end])


class KvmError(Exception):
    pass


class KvmAgentStub(object):
    KvmError = KvmError


class LoggerStub(object):
    def debug(self, *args, **kwargs):
        pass


class QmpStub(object):
    def __init__(self):
        self.calls = []

    def execute_qmp_command(self, vm_uuid, command, **kwargs):
        self.calls.append((vm_uuid, command, kwargs))


class Obj(object):
    pass


class TestVmPluginLuksCbdResize(unittest.TestCase):
    def test_luks_cbd_format_node_uses_requested_size_after_backing_alignment(self):
        payload_offset = 8 * 1024 * 1024
        aligned_storage_size = 1073741825 + payload_offset + 1048575
        qmp = QmpStub()
        namespace = {
            'get_vm_blocks': lambda uuid: [{
                'qdev': '/machine/peripheral/virtio-disk1',
                'inserted': {
                    'node-name': 'drive-virtio-disk1-format',
                    'image': {
                        'format-specific': {
                            'data': {
                                'payload-offset': payload_offset,
                            },
                        },
                    },
                },
            }],
            'kvmagent': KvmAgentStub,
            'logger': LoggerStub(),
            'qmp': qmp,
        }
        source = 'class Vm(object):\n%s%s' % (
            _load_vm_method_source('_resize_luks_cbd_block_node'),
            _load_vm_method_source('_get_luks_payload_offset'))
        exec source in namespace

        vm = namespace['Vm']()
        vm.uuid = 'vm-uuid'
        vm._get_cbd_storage_size = lambda disk: aligned_storage_size

        volume = Obj()
        volume.deviceType = 'cbd'
        volume.deviceId = 1
        volume.volumeUuid = 'volume-uuid'

        target_disk = Obj()
        target_disk.alias = Obj()
        target_disk.alias.name_ = 'virtio-disk1'
        target_disk.encryption = Obj()

        requested_size = 1073741825
        vm._resize_luks_cbd_block_node(volume, target_disk, requested_size)

        self.assertEqual([
            ('vm-uuid', 'block_resize', {
                'node_name': 'drive-virtio-disk1-storage',
                'size': aligned_storage_size,
            }),
            ('vm-uuid', 'block_resize', {
                'node_name': 'drive-virtio-disk1-format',
                'size': requested_size,
            }),
        ], qmp.calls)


if __name__ == '__main__':
    unittest.main()
