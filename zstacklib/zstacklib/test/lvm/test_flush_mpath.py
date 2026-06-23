import unittest
import mock

from zstacklib.utils import bash
from zstacklib.utils import lvm


# ZSTAC-86075 / TIC-5912: adding a SharedBlock LUN must not run a host-wide
# `systemctl reload multipathd` while a running VM passes a multipath LUN
# through (device='lun'), because the global reload's device-mapper
# suspend/resume window aborts in-flight IO on the in-use map -> guest
# BLOCK_IO_ERROR. flush_mpath() re-creates only the wiped disk's own map in
# that case, and keeps the original global reload otherwise.
class TestFlushMpath(unittest.TestCase):

    def _capture(self):
        issued = []
        bash.bash_roe = mock.Mock(side_effect=lambda cmd, *a, **k: issued.append(cmd))
        return issued

    def test_lun_passthrough_vm_running_uses_targeted_recreate(self):
        issued = self._capture()
        lvm.get_dm_wwid = mock.Mock(return_value="361449201002ef3fe11f8a16a00000011")
        lvm.is_running_vm_using_lun_passthrough = mock.Mock(return_value=True)

        lvm.flush_mpath("/dev/dm-38")

        self.assertIn("multipath -f /dev/dm-38", issued)
        self.assertIn("multipath 361449201002ef3fe11f8a16a00000011 && sleep 1", issued)
        self.assertFalse(any("systemctl reload multipathd" in c for c in issued),
                         "must not run host-wide multipathd reload when a LUN-passthrough VM is running")

    def test_no_lun_passthrough_vm_keeps_global_reload(self):
        issued = self._capture()
        lvm.get_dm_wwid = mock.Mock(return_value="361449201002ef3fe11f8a16a00000011")
        lvm.is_running_vm_using_lun_passthrough = mock.Mock(return_value=False)

        lvm.flush_mpath("/dev/dm-38")

        self.assertIn("multipath -f /dev/dm-38", issued)
        self.assertTrue(any("systemctl reload multipathd.service && sleep 1" in c for c in issued))

    def test_lun_passthrough_vm_but_unknown_wwid_falls_back_to_global_reload(self):
        issued = self._capture()
        lvm.get_dm_wwid = mock.Mock(return_value=None)
        lvm.is_running_vm_using_lun_passthrough = mock.Mock(return_value=True)

        lvm.flush_mpath("/dev/dm-38")

        self.assertTrue(any("systemctl reload multipathd.service && sleep 1" in c for c in issued))

    def test_is_running_vm_using_lun_passthrough_greps_live_xml(self):
        bash.bash_r = mock.Mock(return_value=0)
        self.assertTrue(lvm.is_running_vm_using_lun_passthrough())
        called = bash.bash_r.call_args[0][0]
        self.assertIn("device='lun'", called)
        self.assertIn(lvm.LIVE_LIBVIRT_XML_DIR, called)

        bash.bash_r = mock.Mock(return_value=1)
        self.assertFalse(lvm.is_running_vm_using_lun_passthrough())


if __name__ == "__main__":
    unittest.main()
