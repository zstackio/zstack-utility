import json
import unittest

import mock

from kvmagent.plugins import mevoco
from zstacklib.utils import http, jsonobject


class TestBatchDhcpRebuild(unittest.TestCase):
    def apply_batch(self, flags):
        infos = []
        for index, flag in enumerate(flags):
            info = {'dhcp': [{'namespaceName': 'ns-%s' % index}]}
            if flag is not None:
                info['rebuild'] = flag
            infos.append(info)
        plugin = mevoco.Mevoco()
        with mock.patch.object(plugin, 'do_apply_dhcp') as apply:
            response = jsonobject.loads(plugin.batch_apply_dhcp({
                http.REQUEST_BODY: json.dumps({'dhcpInfos': infos})
            }))
        self.assertTrue(response.success)
        self.assertEqual(1, apply.call_count)
        namespaces, rebuild = apply.call_args[0]
        self.assertEqual(len(flags), len(namespaces))
        for index in range(len(flags)):
            self.assertEqual(1, len(namespaces['ns-%s' % index]))
        return rebuild

    def test_nested_rebuild(self):
        self.assertIs(True, self.apply_batch([True]))

    def test_mixed_commands_rebuild(self):
        self.assertIs(True, self.apply_batch([False, True, False]))

    def test_incremental_batch(self):
        self.assertIs(False, self.apply_batch([False, False]))

    def test_missing_nested_flag_is_incremental(self):
        self.assertIs(False, self.apply_batch([None]))

    def test_empty_batch(self):
        self.assertIs(False, self.apply_batch([]))
