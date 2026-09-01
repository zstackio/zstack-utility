import unittest
import mock
import logging
from zstacklib.utils import lvm
from zstacklib.utils import bash

logger = logging.getLogger(__name__)

class TestCase(unittest.TestCase):
    released = None
    sanlock_client_status = None
    sanlock_direct_dump = None

    def test_func_active_with_check(self):

        def mock_shell_output():
            def bash_roe(cmd):
                if "sanlock client status" in cmd and self.sanlock_client_status:
                    return 0, "r lvm_53ce31387e9745729844a7c2a09ed832:duci6c-WkvT-49f1-pajk-vqNF-9JlN-Nr8R5D:/dev/mapper/53ce31387e9745729844a7c2a09ed832-lvmlock:73400320:3 p 93956", ""
                elif "sanlock direct dump" in cmd:
                    return 0, self.sanlock_direct_dump, ""
                elif "sanlock direct init" in cmd:
                    self.released = True
                    return 0, "", ""
                else:
                    return -1, "", ""

            def bash_r(cmd):
                r, _, _ = bash_roe(cmd)
                return r

            def bash_o(cmd):
                _, o, _ = bash_roe(cmd)
                return o

            bash.bash_roe = mock.Mock(side_effect=bash_roe)
            bash.bash_r = mock.Mock(side_effect=bash_r)
            bash.bash_o = mock.Mock(side_effect=bash_o)

        def mock_active_lv():
            def active_lv(path, shared=False):
                if self.released:
                    return
                raise Exception("\n\n   LV locked by other host   \n\n")
            lvm.active_lv = mock.Mock(side_effect=active_lv)

        mock_active_lv()
        mock_shell_output()
        lvm.get_lockspace = mock.Mock(return_value="lvm_53ce31387e9745729844a7c2a09ed832:36:/dev/mapper/53ce31387e9745729844a7c2a09ed832-lvmlock:0")
        lvm.sanlock.get_sector_size = mock.Mock(return_value=512)

        lv_path = "/dev/53ce31387e9745729844a7c2a09ed832/6932af51af3c47e495199f8b3a58bc50"
        def test_active_lv_with_check(sanlock_client_status=False, sanlock_direct_dump=None,
                                      lock_offset=73400320, expect=False):
            self.released = False
            self.sanlock_client_status = sanlock_client_status
            self.sanlock_direct_dump = sanlock_direct_dump or \
                "%s lvm_53ce31387e9745729844a7c2a09ed832 duci6c-WkvT-49f1-pajk-vqNF-9JlN-Nr8R5D 0001906629 0036 0001 1" % lock_offset
            lvm.get_lv_attr = mock.Mock(return_value={
                "lv_uuid": "duci6c-WkvT-49f1-pajk-vqNF-9JlN-Nr8R5D",
                "lv_lockargs": "1.0.0:%s" % lock_offset,
            })
            try:
                lvm.active_lv_with_check(lv_path)
                self.assertEqual(expect, True, "lv change failed")
            except Exception as e:
                logger.debug(str(e))
                self.assertEqual(expect, False, "lv change failed")

        test_active_lv_with_check(sanlock_client_status=True, expect=False)
        test_active_lv_with_check(sanlock_client_status=False,
                                  sanlock_direct_dump="73400320 lvm_53ce31387e9745729844a7c2a09ed832 duci6c-WkvT-49f1-pajk-vqNF-9JlN-Nr8R5D 0001906629 0036 0001 1",
                                  expect=True)
        test_active_lv_with_check(sanlock_client_status=False,
                                  sanlock_direct_dump="73400321 lvm_53ce31387e9745729844a7c2a09ed832 duci6c-WkvT-49f1-pajk-vqNF-9JlN-Nr8R5D 0001906629 0037 0001 1",
                                  lock_offset=73400321, expect=False)


if __name__ == '__main__':
    ## PYTHONPATH=/root/zstack-utility/zstacklib python test_force_release_lv_lock.py
    unittest.main()
