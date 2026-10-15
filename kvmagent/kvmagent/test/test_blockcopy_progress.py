import ast
import logging
import os
import time
import traceback
import types
import unittest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))


def load_definition(path, names, namespace):
    with open(os.path.join(REPO_ROOT, path)) as source:
        node = ast.parse(source.read(), filename=path)
    for name in names:
        node = next(child for child in node.body if getattr(child, 'name', None) == name)
    module = ast.Module(body=[node])
    eval(compile(module, path, 'exec'), namespace)
    return namespace[names[-1]]


class TestBlockCopyProgress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Load the production definitions without importing host-only libvirt dependencies.
        cls.namespace = {'logger': logging.getLogger(__name__), 'time': time, 'traceback': traceback}
        cls.namespace['thread'] = types.ModuleType('thread')
        cls.namespace['thread'].AsyncThread = lambda function: function
        cls.namespace['plugin'] = types.ModuleType('plugin')
        cls.namespace['plugin'].TaskDaemon = object
        cls.namespace['libvirt'] = types.ModuleType('libvirt')
        cls.namespace['libvirt'].libvirtError = type('libvirtError', (Exception,), {})
        cls.namespace['qmp'] = types.ModuleType('qmp')
        cls.namespace['jsonobject'] = types.ModuleType('jsonobject')
        cls.namespace['jsonobject'].JsonObject = load_definition(
            'zstacklib/zstacklib/utils/jsonobject.py', ['JsonObject'], cls.namespace)
        cls.namespace['linux'] = types.ModuleType('linux')
        cls.namespace['linux'].get_exception_stacktrace = load_definition(
            'zstacklib/zstacklib/utils/linux.py', ['get_exception_stacktrace'], cls.namespace)
        cls.namespace['linux'].wait_callback_success = load_definition(
            'zstacklib/zstacklib/utils/linux.py', ['wait_callback_success'], cls.namespace)
        report_path = 'zstacklib/zstacklib/utils/report.py'
        for name in ['get_scale', 'get_exact_percent_from_scale', 'get_exact_percent',
                     'get_task_stage', 'AutoReporter']:
            load_definition(report_path, [name], cls.namespace)
        cls.daemon_class = load_definition('kvmagent/kvmagent/plugins/vm_plugin.py',
                                          ['VmPlugin', '_do_block_copy', 'BlockCopyDaemon'], cls.namespace)

    def setUp(self):
        self.jobs = []
        self.namespace['vmUuid'] = 'test-vm'
        self.namespace['qmp'].execute_qmp_command = lambda *args, **kwargs: self.jobs
        self.spec = self.namespace['JsonObject']()
        self.spec.threadContext = {'task-stage': '0-89'}
        self.namespace['task_spec'] = self.spec
        self.daemon = object.__new__(self.daemon_class)
        self.report = self.namespace['JsonObject']()
        self.report.detail = None
        self.reporter = self.namespace['AutoReporter'](self.report, self.daemon._get_percent,
                                                      self.daemon._get_detail, timeout=5)
        self.daemon.progress_reporter = self.reporter

    def set_job(self, total, offset):
        self.jobs = [{'status': 'running', 'len': total, 'offset': offset}]

    def test_zero_total_waits_for_progress(self):
        self.set_job(0, 0)
        self.assertIsNone(self.daemon._get_percent())
        self.set_job(1000, 500)
        self.assertEqual(44, self.daemon._get_percent())

    def test_negative_total_is_not_reported(self):
        self.set_job(-1, 0)
        self.assertIsNone(self.daemon._get_percent())

    def test_reporter_continues_after_zero_total(self):
        self.set_job(0, 0)
        reports = []
        polls = [0]

        def query(*args, **kwargs):
            polls[0] += 1
            if polls[0] > 1:
                self.set_job(1000, 500)
            return self.jobs

        def record(percent, flag, detail):
            reports.append((percent, flag, detail.total, detail.remain))
            self.reporter.close()

        self.namespace['qmp'].execute_qmp_command = query
        self.report.progress_report = record
        self.reporter.start()
        self.assertEqual([('44', 'report', 1000, 500)], reports)

    def test_missing_job_is_not_reported(self):
        for jobs in [None, [], [{'status': 'concluded', 'len': 1000, 'offset': 1000}]]:
            self.jobs = jobs
            self.assertIsNone(self.daemon._get_percent())

    def test_task_stage_and_completion_cap_are_preserved(self):
        self.spec.threadContext['task-stage'] = '10-90'
        self.set_job(1000, 500)
        self.assertEqual(50, self.daemon._get_percent())
        self.set_job(1000, 1000)
        self.assertEqual(89, self.daemon._get_percent())
        self.spec.threadContext['task-stage'] = '0-0'
        self.assertEqual(0, self.daemon._get_percent())


if __name__ == '__main__':
    unittest.main()
