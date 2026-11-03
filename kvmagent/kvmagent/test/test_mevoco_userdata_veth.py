import unittest

import mock

from kvmagent.plugins import mevoco


class FakeNetnsShell(object):
    def __init__(self, mac):
        self.mac = mac
        self.deleted_links = []

    def get_mac(self, link_name):
        return self.mac

    def del_link(self, link_name):
        self.deleted_links.append(link_name)


class TestUserdataVethPair(unittest.TestCase):
    def _run(self, outer_exist, inner_exist):
        shell = FakeNetnsShell('fa:16:3e:00:00:01' if inner_exist else None)
        patches = [
            mock.patch.object(mevoco.linux, 'is_network_device_existing', return_value=outer_exist),
            mock.patch.object(mevoco.iproute, 'IpNetnsShell', return_value=shell),
            mock.patch.object(mevoco.iproute, 'delete_link_no_error'),
            mock.patch.object(mevoco.iproute, 'add_link'),
            mock.patch.object(mevoco.iproute, 'set_link_attribute'),
        ]
        started = [p.start() for p in patches]
        try:
            mevoco.ensure_userdata_veth_pair('ns0', 'ud_outer9', 'ud_inner9', 65500)
            return shell, started[2], started[3], started[4]
        finally:
            for p in reversed(patches):
                p.stop()

    def test_keep_complete_pair(self):
        shell, delete_link, add_link, set_link_attribute = self._run(True, True)

        self.assertEqual([], shell.deleted_links)
        self.assertEqual(0, delete_link.call_count)
        self.assertEqual(0, add_link.call_count)
        self.assertEqual(0, set_link_attribute.call_count)

    def test_create_missing_pair(self):
        shell, delete_link, add_link, set_link_attribute = self._run(False, False)

        self.assertEqual([], shell.deleted_links)
        self.assertEqual(0, delete_link.call_count)
        add_link.assert_called_once_with('ud_outer9', 'veth', peer='ud_inner9')
        self.assertEqual(2, set_link_attribute.call_count)

    def test_recreate_when_outer_left_without_inner(self):
        shell, delete_link, add_link, set_link_attribute = self._run(True, False)

        self.assertEqual([], shell.deleted_links)
        delete_link.assert_called_once_with('ud_outer9')
        add_link.assert_called_once_with('ud_outer9', 'veth', peer='ud_inner9')
        self.assertEqual(2, set_link_attribute.call_count)

    def test_recreate_when_inner_left_without_outer(self):
        shell, delete_link, add_link, set_link_attribute = self._run(False, True)

        self.assertEqual(['ud_inner9'], shell.deleted_links)
        self.assertEqual(0, delete_link.call_count)
        add_link.assert_called_once_with('ud_outer9', 'veth', peer='ud_inner9')
        self.assertEqual(2, set_link_attribute.call_count)


if __name__ == "__main__":
    unittest.main()
