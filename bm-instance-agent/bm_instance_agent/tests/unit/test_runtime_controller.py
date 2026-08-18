import json
import importlib.util
import os
import sys
import types
import unittest


def _install_fake_pecan():
    if 'pecan' in sys.modules and 'pecan.rest' in sys.modules:
        return

    fake_request = types.SimpleNamespace(body='')
    fake_response = types.SimpleNamespace(status=None)

    def expose(template=None):
        def decorator(func):
            return func
        return decorator

    class RestController(object):
        pass

    pecan_module = types.ModuleType('pecan')
    pecan_module.expose = expose
    pecan_module.request = fake_request
    pecan_module.response = fake_response

    rest_module = types.ModuleType('pecan.rest')
    rest_module.RestController = RestController

    sys.modules['pecan'] = pecan_module
    sys.modules['pecan.rest'] = rest_module


_install_fake_pecan()

module_path = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    '..', '..', 'api', 'controllers', 'v2', 'runtime.py'))
module_spec = importlib.util.spec_from_file_location(
    'bm_instance_agent_runtime_controller_under_test',
    module_path)
runtime_controller = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(runtime_controller)


class FakeRuntimeManager(object):

    def __init__(self):
        self.prepare_payloads = []
        self.prepare_calls = []
        self.start_calls = []

    def materialize_prepare_payload(self, payload):
        self.prepare_payloads.append(payload)
        staged = json.loads(json.dumps(payload))
        staged['workloadSpec']['runtimeArtifact']['localPath'] = (
            '/var/lib/zstack/baremetal-runtime/artifacts/sha256-%s'
            % ('a' * 64))
        return staged

    def prepare_allocation(self, allocation_uuid, payload):
        self.prepare_calls.append((allocation_uuid, payload))
        return 201, {'phase': 'Prepared'}

    def start_allocation(self, allocation_uuid, payload):
        self.start_calls.append((allocation_uuid, payload))
        return 200, {'phase': 'Running'}


class RuntimeControllerTest(unittest.TestCase):

    def setUp(self):
        runtime_controller.request.body = ''
        runtime_controller.response.status = None
        self.runtime_manager = FakeRuntimeManager()

    def test_prepare_pre_stages_before_proxy_forward(self):
        payload = {
            'requestId': 'request-prepare-001',
            'generation': 7,
            'workloadSpec': {
                'allocationUuid': 'allocation-001',
                'runtimeArtifact': {
                    'kind': 'CondaPackage',
                    'digest': 'sha256:' + ('a' * 64),
                    'source': 'model-center:runtime/vllm-0.8.5',
                    'localPath': '/tmp/stale',
                    'materialization': {
                        'mode': 'ModelCenterArtifact',
                        'modelCenterUuid': '123e4567-e89b-12d3-a456-426614174000',
                        'artifactUuid': '123e4567-e89b-12d3-a456-426614174001',
                        'layout': 'CondaPrefix'
                    }
                }
            }
        }
        controller = runtime_controller.PrepareController(
            self.runtime_manager, 'allocation-001')
        runtime_controller.request.body = json.dumps(payload)

        body = controller.put()

        self.assertEqual(201, runtime_controller.response.status)
        self.assertEqual({'phase': 'Prepared'}, body)
        self.assertEqual([payload], self.runtime_manager.prepare_payloads)
        self.assertEqual(
            '/var/lib/zstack/baremetal-runtime/artifacts/sha256-%s' % ('a' * 64),
            self.runtime_manager.prepare_calls[0][1]['workloadSpec']['runtimeArtifact']['localPath'])

    def test_start_remains_passthrough(self):
        payload = {
            'requestId': 'request-start-001',
            'generation': 8
        }
        controller = runtime_controller.StartController(
            self.runtime_manager, 'allocation-001')
        runtime_controller.request.body = json.dumps(payload)

        body = controller.post()

        self.assertEqual(200, runtime_controller.response.status)
        self.assertEqual({'phase': 'Running'}, body)
        self.assertEqual([], self.runtime_manager.prepare_payloads)
        self.assertEqual([('allocation-001', payload)], self.runtime_manager.start_calls)
