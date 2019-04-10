'''

@author: kaicai.hu
'''

import unittest
import tempfile
from kvmagent import kvmagent
from kvmagent.plugins import vm_plugin
from zstacklib.utils import bash

class Test(unittest.TestCase):
    
    def testName(self):
        temp = tempfile.NamedTemporaryFile(prefix='grub', suffix='', dir='/tmp', mode='w+b', delete=True)
        try:
            temp.write('GRUB_CMDLINE_LINUX="crashkernel=auto rd.lvm.lv=zstack/root rd.lvm.lv=zstack/swap rhgb quiet d=d intel_iommu=on modprobe.blacklist=snd_hda_intel,amd76x_edac,vga16fb,nouveau,rivafb,nvidiafb,rivatv,amdgpu,radeon"\n')
            temp.seek(0)
            path = temp.name
            updateConfigration = vm_plugin.UpdateConfigration()
            updateConfigration.path = path
            updateConfigration.enableIommu = False
            success, error = updateConfigration.updateHostIommu()
            self.assertTrue(success)
            r_on, o_on, e_on = bash.bash_roe("grep -E 'intel_iommu(\ )*=(\ )*on' %s" % path)
            r_off, o_off, e_off = bash.bash_roe("grep -E 'intel_iommu(\ )*=(\ )*off' %s" % path)
            r_modprobe_blacklist, o_modprobe_blacklist, e_modprobe_blacklist = bash.bash_roe("grep -E 'modprobe.blacklist(\ )*='  %s" % path)
            self.assertNotEqual(r_on, 0)
            self.assertNotEqual(r_off, 0)
            self.assertNotEqual(r_modprobe_blacklist, 0)

            updateConfigration = vm_plugin.UpdateConfigration()
            updateConfigration.path = path
            updateConfigration.enableIommu = True
            success, error = updateConfigration.updateHostIommu()
            self.assertTrue(success)
            r_on, o_on, e_on = bash.bash_roe("grep -E 'intel_iommu(\ )*=(\ )*on' %s" % path)
            r_off, o_off, e_off = bash.bash_roe("grep -E 'intel_iommu(\ )*=(\ )*off' %s" % path)
            r_modprobe_blacklist, o_modprobe_blacklist, e_modprobe_blacklist = bash.bash_roe("grep -E 'modprobe.blacklist(\ )*='  %s" % path)
            self.assertEqual(r_on, 0)
            self.assertNotEqual(r_off, 0)
            self.assertEqual(r_modprobe_blacklist, 0)
        finally:
            temp.close()  

if __name__ == "__main__":
    unittest.main()