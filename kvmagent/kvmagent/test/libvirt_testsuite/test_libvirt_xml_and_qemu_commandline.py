from kvmagent.plugins import vm_plugin
from kvmagent.test.utils import vm_utils, network_utils, pytest_utils
from kvmagent.test.utils.stub import *
from zstacklib.test.utils import env, misc
from zstacklib.utils import bash
from unittest import TestCase

init_kvmagent()
vm_utils.init_vm_plugin()

__ENV_SETUP__ = {
    'self': {
    }
}

class TestLibvirtXml(TestCase, vm_utils.VmPluginTestStub):

    @classmethod
    def setUpClass(cls):
        network_utils.create_default_bridge_if_not_exist()

    @pytest_utils.ztest_decorater
    def test(self):
        self.libvirt_xml_and_qemu_commandline_check("4.9.0", "4.2.0")

    @bash.in_bash
    def libvirt_xml_and_qemu_commandline_check(self, libvirt_version, qemu_version):
        self.assertIsNotNone(libvirt_version, "missing libvirt version")
        self.assertIsNotNone(qemu_version, "missing qemu version")

        r1, _ = bash.bash_ro("rpm -qa | grep libvirt-%s" % libvirt_version)
        r2, _ = bash.bash_ro("rpm -qa | grep qemu-kvm-%s" % qemu_version)

        if r1 != 0 or r2 != 0:
            bash.bash_ro("yum install libvirt-%s* qemu-kvm-%s -y" % (libvirt_version, qemu_version))

        r1, _ = bash.bash_ro("rpm -qa | grep libvirt-%s" % libvirt_version)
        r2, _ = bash.bash_ro("rpm -qa | grep qemu-kvm-%s" % qemu_version)
        self.assertEqual(r1, 0, "failed to find rpm starts with libvirt-%s" % libvirt_version)
        self.assertEqual(r2, 0, "failed to find rpm starts with qemu-kvm-%s" % qemu_version)

        vm_uuid, vm = self._create_vm()

        r, output = bash.bash_ro("virsh dumpxml %s" % vm.vmInstanceUuid)

        # save xml from virsh dumpxml
        with open("libvirt_xml_%s_from_case.xml" % libvirt_version, "w") as f:
            f.write(output)

        case_dir = os.path.dirname(env.TEST_ROOT)

        r, output = bash.bash_ro('diff <(xmllint --c14n libvirt_xml_%s_from_case.xml) <(xmllint --c14n %s/libvirt_xml_%s.xml) --ignore-matching-lines="^<domain xmlns:qemu="'
                                  % (libvirt_version, case_dir, libvirt_version))

        self.assertEqual(r, 0, "libvirt xml is not the same as expected: %s" % output)

        r, output = bash.bash_ro("ps aux | grep qemu-kvm | grep %s" % vm.vmInstanceUuid)

        output = output.strip().split(' ')
        # start with /usr/libexec/qemu-kvm avoid dynamic output of ps aux
        output = output[output.index('/usr/libexec/qemu-kvm'):]
        # save qemu commandline from ps aux
        with open("qemu_commandline_%s_from_case.txt" % qemu_version, "w") as f:
            output = '\n'.join(output)
            f.write(output)

        r, output = bash.bash_ro('diff <(cat qemu_commandline_%s_from_case.txt) <(cat %s/qemu_commandline_%s.txt) -I "^secret,id=masterKey0" -I "^socket,id=charchannel0,fd="'
                                    % (qemu_version, case_dir, qemu_version))

        self.assertEqual(r, 0, "qemu commandline is not the same as expected: %s" % output)
        self._destroy_vm(vm.vmInstanceUuid)
