import unittest
import mock
from zstacklib.utils import bash
from zstacklib.utils import lvm


class TestPlugin(unittest.TestCase):

    def test_load_xml(self):
        with open("da3515fb4b374aa9b818c094b61f814a.xml", 'r') as f:
            test_xml = f.read()
        vm = lvm.VmStruct()
        vm.load_from_xml(test_xml)
        self.assertTrue(vm.root_volume == "/dev/cf1e9c4f3d674f159505c234c3e5356b/5eba462401b44e51b0efc0ce35e42391")
        self.assertTrue(len(vm.volumes) == 2)
        self.assertTrue("/dev/cf1e9c4f3d674f159505c234c3e5356b/5eba462401b44e51b0efc0ce35e42391" in vm.volumes)
        self.assertTrue("/dev/e2402ed34190477cb9b4ae3a2cc58db6/eb4a2df6f6ab4fee9bc62eef07e7ce38" in vm.volumes)

    def test_get_running_vm(self):
        lvm.LIVE_LIBVIRT_XML_DIR = "./"
        lvm.is_bad_vm_root_volume = mock.Mock(return_value=True)
        bash.bash_r = mock.Mock(return_value=0)
        vms = lvm.get_running_vm_root_volume_on_pv("e2402ed34190477cb9b4ae3a2cc58db6", [])
        self.assertTrue(vms[0].uuid == "dbf309aab92a4abc80392e5879b2efb6")
        self.assertTrue(vms[0].root_volume == "/dev/e2402ed34190477cb9b4ae3a2cc58db6/63bb085d717547999dce0fb340bb0257")
        self.assertTrue(vms[0].pid == "41856")
        self.assertTrue(len(vms) == 1)


if __name__ == "__main__":
    unittest.main()
