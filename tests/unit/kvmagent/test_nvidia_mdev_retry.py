import ast
import functools
import io
import json
import os
import re
import textwrap
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]


def definition(path, name, namespace, indent=''):
    source = (ROOT / path).read_text()
    match = re.search(r'^' + indent + r'def ' + name + r'\(.*?(?=^' + indent + r'(?:def |@)|\Z)',
                      source, re.M | re.S)
    exec(compile(ast.parse(textwrap.dedent(match.group())), path, 'exec'), namespace)
    return namespace[name]


class BashError(Exception):
    pass


class NvidiaMdevRetryTest(unittest.TestCase):
    def setUp(self):
        self.sleep = MagicMock()
        retry = definition('zstacklib/zstacklib/utils/linux.py', 'retry',
                           {'functools': functools, 'time': SimpleNamespace(sleep=self.sleep)})
        self.attempts = []
        self.failures = 1
        self.files = []
        self.ns = {
            'linux': SimpleNamespace(retry=retry), 'os': os, 'uuid': uuid,
            'logger': MagicMock(), 'bash_roe': self.bash_roe,
            'GenerateVfioMdevDevicesRsp': lambda: SimpleNamespace(success=True, mdevUuids=[]),
            'jsonobject': SimpleNamespace(dumps=lambda obj: json.dumps(vars(obj))),
            'open': self.open_file,
        }
        self.generate = definition('kvmagent/kvmagent/plugins/host_plugin.py',
                                   '_generate_nvidia_vfio_mdev_devices', self.ns, '    ')
        self.cmd = SimpleNamespace(pciDeviceAddress='0000:65:00.0', mdevSpecTypeId='0x123',
                                   mdevUuids=['1fdcb01994f240ea9d2670e3eb3cd1cc'])

    def bash_roe(self, command, errorout=False):
        self.attempts.append(command)
        if len(self.attempts) <= self.failures:
            if errorout:
                raise BashError('Could not acquire UnbindLock')
            return 1, '', 'Could not acquire UnbindLock'
        return 0, '', ''

    def open_file(self, path, mode):
        stream = io.StringIO()
        stream.close = lambda: None
        self.files.append((path, stream))
        return stream

    def exists(self, path):
        return path == '/usr/lib/nvidia/sriov-manage' or path.endswith('/mdev_supported_types/nvidia-291')

    def test_first_lock_failure_retries_and_restores_original_uuid(self):
        with patch.object(os.path, 'exists', side_effect=self.exists):
            result = json.loads(self.generate(None, self.cmd))
        self.assertTrue(result['success'])
        self.assertEqual(2, len(self.attempts))
        self.sleep.assert_called_once_with(5)
        self.assertEqual(str(uuid.UUID(self.cmd.mdevUuids[0])), self.files[0][1].getvalue())

    def test_persistent_lock_failure_exhausts_budget_without_creating_devices(self):
        self.failures = 30
        with patch.object(os.path, 'exists', side_effect=self.exists):
            with self.assertRaisesRegex(BashError, 'UnbindLock'):
                self.generate(None, self.cmd)
        self.assertEqual(30, len(self.attempts))
        self.assertEqual(30, self.sleep.call_count)
        self.assertEqual([], self.files)

    def test_success_does_not_retry(self):
        self.failures = 0
        with patch.object(os.path, 'exists', side_effect=self.exists):
            self.assertTrue(json.loads(self.generate(None, self.cmd))['success'])
        self.assertEqual(1, len(self.attempts))
        self.sleep.assert_not_called()

    def test_existing_marker_skips_regeneration(self):
        with patch.object(os.path, 'exists', return_value=True):
            self.assertTrue(json.loads(self.generate(None, self.cmd))['success'])
        self.assertEqual([], self.attempts)
        self.assertEqual([], self.files)


if __name__ == '__main__':
    unittest.main()
