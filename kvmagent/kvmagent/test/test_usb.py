import unittest

import pytest

from zstacklib.utils import linux


class Test(unittest.TestCase):
    def test_allocate_usb_controller(self):
        usb_manager = linux.VmUsbManager()
        # invalid usb version
        with pytest.raises(Exception):
            usb_manager.request_slot(4)

        # test usb version 1, controller 0
        assert usb_manager.request_slot(1) == 0

        # test usb version 1, controller 2
        assert usb_manager.request_slot(1) == 2

        # test usb version 2, controller 1
        for _ in range(6):
            assert usb_manager.request_slot(2) == 1

        # test usb version 2, controller 2
        for _ in range(2):
            assert usb_manager.request_slot(2) == 2

        # test usb version 3, controller 2
        assert usb_manager.request_slot(3) == 2

        # insufficient usb controllers
        with pytest.raises(Exception):
            usb_manager.request_slot(3)


if __name__ == "__main__":
    unittest.main()
