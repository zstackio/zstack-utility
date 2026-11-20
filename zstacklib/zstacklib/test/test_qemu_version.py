import importlib.util
import os
import sys
import types
import unittest
from unittest import mock


class TestQemuVersion(unittest.TestCase):
    def load_qemu(self):
        modules = {
            name: types.ModuleType(name)
            for name in ['bash', 'log', 'jsonobject', 'shell', 'linux',
                         'zstacklib', 'zstacklib.utils',
                         'zstacklib.utils.qemu_img']
        }
        modules['zstacklib'].utils = modules['zstacklib.utils']
        for name in ['bash', 'log', 'jsonobject', 'shell', 'linux']:
            modules['zstacklib.utils.' + name] = modules[name]
            setattr(modules['zstacklib.utils'], name, modules[name])
        modules['zstacklib.utils'].qemu_img = modules['zstacklib.utils.qemu_img']
        modules['log'].get_logger = mock.Mock(return_value=mock.Mock())
        modules['shell'].call = mock.Mock(return_value='6.2.0')
        modules['bash'].bash_roe = mock.Mock(
            return_value=(0, 'QEMU emulator version 6.2.0 (qemu-kvm-6.2.0)\n', '')
        )
        modules['linux'].get_vm_pid = mock.Mock()
        modules['linux'].get_process_start_time = mock.Mock()
        modules['linux'].HOST_ARCH = 'x86_64'

        qemu_path = os.path.join(
            os.path.dirname(__file__), '..', 'utils', 'qemu.py'
        )
        spec = importlib.util.spec_from_file_location('zstacklib.utils.qemu_under_test', qemu_path)
        qemu = importlib.util.module_from_spec(spec)

        with mock.patch.dict(sys.modules, modules), \
                mock.patch('os.path.exists', return_value=True):
            spec.loader.exec_module(qemu)

        return qemu

    def test_get_version_does_not_depend_on_libvirt(self):
        qemu = self.load_qemu()
        qemu.shell.call.assert_not_called()
        qemu.shell.call.reset_mock()
        qemu.get_path = mock.Mock(return_value='/usr/libexec/qemu-kvm')
        qemu.get_version_from_exe_file2 = mock.Mock(return_value='6.2.0')

        self.assertEqual('6.2.0', qemu.get_version())
        qemu.get_version_from_exe_file2.assert_called_once_with(
            '/usr/libexec/qemu-kvm'
        )
        qemu.shell.call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
