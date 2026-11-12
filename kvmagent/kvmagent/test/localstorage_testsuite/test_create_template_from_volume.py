from concurrent.futures import ThreadPoolExecutor
import os
import tempfile
from unittest import TestCase
from unittest.mock import patch

from kvmagent.plugins import localstorage
from zstacklib.utils import http, jsonobject, linux

PKG_NAME = __name__
__ENV_SETUP__ = {'self': {}}


class TestLocalStoragePlugin(TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='localstorage-template-')
        self.addCleanup(directory.cleanup)
        self.source = os.path.join(directory.name, 'source.qcow2')
        self.target = os.path.join(directory.name, 'template', 'image.qcow2')
        self.plugin = localstorage.LocalStoragePlugin()
        self.request = {http.REQUEST_BODY: jsonobject.dumps({
            'volumePath': self.source,
            'installPath': self.target,
            'storagePath': directory.name,
        })}

    def test_create_template_from_volume(self):
        base = os.path.join(os.path.dirname(self.source), 'base.qcow2')
        linux.qcow2_create(base, '64M')
        linux.qcow2_clone(base, self.source)
        with ThreadPoolExecutor(max_workers=1) as executor:
            response = jsonobject.loads(executor.submit(
                self.plugin.create_template_from_volume, self.request).result())

        self.assertNotEqual(False, response.success, response.error)
        self.assertEqual(64 * 1024 * 1024, response.size)
        self.assertTrue(os.path.exists(self.target))
        self.assertFalse(linux.qcow2_get_backing_file(self.target))
        self.assertTrue(os.path.exists(self.source))

    def test_create_template_from_volume_failure_removes_partial_file(self):
        with open(self.source, 'wb') as source:
            source.write(b'original source')

        def fail_conversion(source, target, **kwargs):
            with open(target, 'wb') as partial:
                partial.write(b'partial template')
            raise RuntimeError('injected conversion failure')

        # Production HTTP requests each run in a fresh thread with their own rollback stack.
        with patch.object(linux, 'create_template', side_effect=fail_conversion):
            with ThreadPoolExecutor(max_workers=1) as executor:
                response = jsonobject.loads(executor.submit(
                    self.plugin.create_template_from_volume, self.request).result())

        self.assertFalse(response.success)
        self.assertIn('injected conversion failure', response.error)
        self.assertFalse(os.path.exists(self.target))
        with open(self.source, 'rb') as source:
            self.assertEqual(b'original source', source.read())
