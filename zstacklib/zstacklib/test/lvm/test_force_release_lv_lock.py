import time
import unittest
import mock
import logging
from zstacklib.utils import lvm
from zstacklib.utils import bash
from cachetools import TTLCache

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
        lvm.get_lv_size = mock.Mock(return_value="10485760")
        lvm.lv_uuid = mock.Mock(return_value="duci6c-WkvT-49f1-pajk-vqNF-9JlN-Nr8R5D")

        lv_path = "/dev/53ce31387e9745729844a7c2a09ed832/6932af51af3c47e495199f8b3a58bc50"
        def test_active_lv_with_check(sanlock_client_status=False, sanlock_direct_dump=None, expect=False):
            self.released = False
            self.sanlock_client_status = sanlock_client_status
            self.sanlock_direct_dump = sanlock_direct_dump
            try:
                lvm.active_lv_with_check(lv_path)
                self.assertEqual(expect, True, "lv change failed")
            except Exception as e:
                logger.debug(str(e))
                self.assertEqual(expect, False, "lv change failed")

        lvm.lv_offset = TTLCache(maxsize=10, ttl=3)
        test_active_lv_with_check(sanlock_client_status=True, expect=False)
        assert lvm.lv_offset.get(lv_path) is None

        test_active_lv_with_check(sanlock_client_status=False, sanlock_direct_dump="73400320 0001906629 0036", expect=True)
        assert lvm.lv_offset.get(lv_path) == "73400320"

        time.sleep(4)
        assert lvm.lv_offset.get(lv_path) is None
        test_active_lv_with_check(sanlock_client_status=False, sanlock_direct_dump="73400321 0001906629 0037", expect=False)
        assert lvm.lv_offset.get(lv_path) == "73400321"


if __name__ == '__main__':
    ## PYTHONPATH=/root/zstack-utility/zstacklib python test_force_release_lv_lock.py
    unittest.main()
