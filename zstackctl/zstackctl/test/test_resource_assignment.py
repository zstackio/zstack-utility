#!/usr/bin/env python

import os
import shutil
import sys
import tempfile
import unittest


current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(current_dir)))

from zstackctl.resource_assignment import (
    MANAGEMENT_NODE_SERVICE,
    MANAGEMENT_NODE_SLICE,
    management_node_systemd_run_arguments,
    resource_assignment_enabled,
)


class ResourceAssignmentTest(unittest.TestCase):
    def setUp(self):
        self.cgroup_root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.cgroup_root)

    def test_existing_global_config_is_authoritative(self):
        self.assertTrue(resource_assignment_enabled([{'value': 'true'}], self.cgroup_root))

        open(os.path.join(self.cgroup_root, 'cgroup.controllers'), 'w').close()

        self.assertFalse(resource_assignment_enabled([{'value': 'false'}], self.cgroup_root))
        self.assertTrue(resource_assignment_enabled([{'value': 'TRUE'}], self.cgroup_root))

    def test_new_environment_defaults_from_unified_cgroup_v2(self):
        self.assertFalse(resource_assignment_enabled([], self.cgroup_root))

        open(os.path.join(self.cgroup_root, 'cgroup.controllers'), 'w').close()
        self.assertTrue(resource_assignment_enabled([], self.cgroup_root))

    def test_management_node_starts_as_a_tracked_role_service(self):
        arguments = management_node_systemd_run_arguments(
            '/opt/zstack/startup.sh', '/var/lib/zstack/management-server.pid')

        self.assertIn('--unit=%s' % MANAGEMENT_NODE_SERVICE, arguments)
        self.assertIn('--slice=%s' % MANAGEMENT_NODE_SLICE, arguments)
        self.assertIn('--property=PIDFile=/var/lib/zstack/management-server.pid', arguments)
        self.assertEqual(arguments[-3:], ['/bin/sh', '/opt/zstack/startup.sh', '-DappName=zstack'])


if __name__ == '__main__':
    unittest.main()
