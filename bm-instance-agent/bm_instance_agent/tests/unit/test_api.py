import json
import os
import time

import mock
from pecan import set_config
from pecan.testing import load_test_app

from bm_instance_agent.common import utils as bm_utils
from bm_instance_agent.systems import base as driver_base
from bm_instance_agent.tests import base
from bm_instance_agent.tests.unit import fake


def wait_func_called(mock_func, time_count=0):
    try:
        mock_func.assert_called()
        return
    except AssertionError as e:
        if time_count < 3:
            time.sleep(0.1)
            return wait_func_called(mock_func, time_count + 0.1)
        raise e


class ApiTestBase(base.TestCase):

    def setUp(self):
        super(ApiTestBase, self).setUp()
        self.app = load_test_app(os.path.join(
            os.path.dirname(__file__),
            '../../api/config.py'))

    def tearDown(self):
        super(ApiTestBase, self).tearDown()
        set_config({}, overwrite=True)


class ApiTest(ApiTestBase):

    @mock.patch('bm_instance_agent.systems.base.SystemDriverBase.ping')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    @mock.patch('bm_instance_agent.api.utils._post')
    def test_ping(self, mock_post, mock_driv, mock_ping):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_ping.return_value = None

        # Call the api
        data = {
            'bmInstance': fake.BM_INSTANCE1
        }
        resp = self.app.post('/v2/ping',
                             headers=fake.HEADERS,
                             params=json.dumps(data))
        self.assertEqual(200, resp.status_int)

        wait_func_called(mock_post)
        url = 'http://127.0.0.1:8080'
        headers = {'taskuuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c'}
        body = {
            'success': True,
            'error': None,
            'ping': {
                'bmInstanceUuid': '7b432900-c0ad-47e7-b1c7-01b74961c235'
            }
        }
        mock_post.assert_called_once_with(url, headers, body)

    @mock.patch('bm_instance_agent.manager.AgentManager.reboot')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    @mock.patch('bm_instance_agent.api.utils._post')
    def test_reboot(self, mock_post, mock_driv, mock_reboot):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_reboot.return_value = None
        self.test_ping()

        # Call the api
        data = {'bmInstance': fake.BM_INSTANCE1}
        resp = self.app.post('/v2/reboot',
                             headers=fake.HEADERS,
                             params=json.dumps(data))
        self.assertEqual(200, resp.status_int)

        # Wait the thread work done
        wait_func_called(mock_post)
        url = 'http://127.0.0.1:8080'
        headers = {'taskuuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c'}
        body = {
            'success': True,
            'error': None}
        calls = [mock.call(url, headers, body)]
        mock_post.assert_has_calls(calls)

        # Assert the call corrent
        mock_reboot.assert_called_once_with(
            bm_instance=bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))

    @mock.patch('bm_instance_agent.manager.AgentManager.stop')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    @mock.patch('bm_instance_agent.api.utils._post')
    def test_stop(self, mock_post, mock_driv, mock_stop):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_stop.return_value = None
        self.test_ping()

        # Call the api
        data = {'bmInstance': fake.BM_INSTANCE1}
        resp = self.app.post('/v2/stop',
                             headers=fake.HEADERS,
                             params=json.dumps(data))
        self.assertEqual(200, resp.status_int)

        # Wait the thread work done
        wait_func_called(mock_post)
        url = 'http://127.0.0.1:8080'
        headers = {'taskuuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c'}
        body = {
            'success': True,
            'error': None}
        calls = [mock.call(url, headers, body)]
        mock_post.assert_has_calls(calls)

        # Assert the call corrent
        mock_stop.assert_called_once_with(
            bm_instance=bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))

    @mock.patch('bm_instance_agent.manager.AgentManager.attach_volume')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    @mock.patch('bm_instance_agent.api.utils._post')
    def test_volume_attach(self, mock_post, mock_driv, mock_vol_attach):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_vol_attach.return_value = None
        self.test_ping()

        # Call the api
        data = {'bmInstance': fake.BM_INSTANCE1, 'volume': fake.VOLUME1}
        resp = self.app.post('/v2/volume/attach',
                             headers=fake.HEADERS,
                             params=json.dumps(data))
        self.assertEqual(200, resp.status_int)

        # Wait the thread work done
        wait_func_called(mock_post)
        url = 'http://127.0.0.1:8080'
        headers = {'taskuuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c'}
        body = {
            'success': True,
            'error': None}
        calls = [mock.call(url, headers, body)]
        mock_post.assert_has_calls(calls)

        # Assert the call corrent
        mock_vol_attach.assert_called_once_with(
            bm_instance=bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1),
            volume=bm_utils.camel_obj_to_snake(fake.VOLUME1))

    @mock.patch('bm_instance_agent.manager.AgentManager.detach_volume')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    @mock.patch('bm_instance_agent.api.utils._post')
    def test_volume_detach(self, mock_post, mock_driv, mock_vol_detach):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_vol_detach.return_value = None
        self.test_ping()

        # Call the api
        data = {'bmInstance': fake.BM_INSTANCE1, 'volume': fake.VOLUME1}
        resp = self.app.post('/v2/volume/detach',
                             headers=fake.HEADERS,
                             params=json.dumps(data))
        self.assertEqual(200, resp.status_int)

        # Wait the thread work done
        wait_func_called(mock_post)
        url = 'http://127.0.0.1:8080'
        headers = {'taskuuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c'}
        body = {
            'success': True,
            'error': None}
        calls = [mock.call(url, headers, body)]
        mock_post.assert_has_calls(calls)

        # Assert the call corrent
        mock_vol_detach.assert_called_once_with(
            bm_instance=bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1),
            volume=bm_utils.camel_obj_to_snake(fake.VOLUME1))

    @mock.patch('bm_instance_agent.manager.AgentManager.attach_port')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    @mock.patch('bm_instance_agent.api.utils._post')
    def test_port_attach(self, mock_post, mock_driv, mock_port_attach):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_port_attach.return_value = None
        self.test_ping()

        # Call the api
        data = {'bmInstance': fake.BM_INSTANCE1, 'nic': fake.PORT1}
        resp = self.app.post('/v2/nic/attach',
                             headers=fake.HEADERS,
                             params=json.dumps(data))
        self.assertEqual(200, resp.status_int)

        # Wait the thread work done
        wait_func_called(mock_post)
        url = 'http://127.0.0.1:8080'
        headers = {'taskuuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c'}
        body = {
            'success': True,
            'error': None}
        calls = [mock.call(url, headers, body)]
        mock_post.assert_has_calls(calls)

        # Assert the call corrent
        mock_port_attach.assert_called_once_with(
            bm_instance=bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1),
            port=bm_utils.camel_obj_to_snake(fake.PORT1))

    @mock.patch('bm_instance_agent.manager.AgentManager.detach_port')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    @mock.patch('bm_instance_agent.api.utils._post')
    def test_port_detach(self, mock_post, mock_driv, mock_port_detach):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_port_detach.return_value = None
        self.test_ping()

        # Call the api
        data = {'bmInstance': fake.BM_INSTANCE1, 'nic': fake.PORT1}
        resp = self.app.post('/v2/nic/detach',
                             headers=fake.HEADERS,
                             params=json.dumps(data))
        self.assertEqual(200, resp.status_int)

        # Wait the thread work done
        wait_func_called(mock_post)
        url = 'http://127.0.0.1:8080'
        headers = {'taskuuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c'}
        body = {
            'success': True,
            'error': None}
        calls = [mock.call(url, headers, body)]
        mock_post.assert_has_calls(calls)

        # Assert the call corrent
        mock_port_detach.assert_called_once_with(
            bm_instance=bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1),
            port=bm_utils.camel_obj_to_snake(fake.PORT1))

    @mock.patch('bm_instance_agent.manager.AgentManager.update_default_route')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    @mock.patch('bm_instance_agent.api.utils._post')
    def test_default_route_change(self, mock_post,
                                  mock_driv, mock_update_route):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_update_route.return_value = None
        self.test_ping()

        # Call the api
        data = {
            'bmInstance': fake.BM_INSTANCE1,
            'oldDefault': fake.PORT1,
            'newDefault': fake.PORT2
        }
        resp = self.app.post('/v2/defaultRoute/change',
                             headers=fake.HEADERS,
                             params=json.dumps(data))
        self.assertEqual(200, resp.status_int)

        # Wait the thread work done
        wait_func_called(mock_post)
        url = 'http://127.0.0.1:8080'
        headers = {'taskuuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c'}
        body = {
            'success': True,
            'error': None}
        calls = [mock.call(url, headers, body)]
        mock_post.assert_has_calls(calls)

        # Assert the call corrent
        mock_update_route.assert_called_once_with(
            bm_instance=bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1),
            old_default_port=bm_utils.camel_obj_to_snake(fake.PORT1),
            new_default_port=bm_utils.camel_obj_to_snake(fake.PORT2))

    @mock.patch('bm_instance_agent.manager.AgentManager.update_password')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    @mock.patch('bm_instance_agent.api.utils._post')
    def test_password_change(self, mock_post, mock_driv, mock_update_passwd):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_update_passwd.return_value = None
        self.test_ping()

        # Call the api
        data = {
            'username': 'username',
            'password': 'newPassword',
            'bmInstance': fake.BM_INSTANCE1
        }
        resp = self.app.post('/v2/password/change',
                             headers=fake.HEADERS,
                             params=json.dumps(data))
        self.assertEqual(200, resp.status_int)

        # Wait the thread work done
        wait_func_called(mock_post)
        url = 'http://127.0.0.1:8080'
        headers = {'taskuuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c'}
        body = {
            'success': True,
            'error': None
        }
        calls = [mock.call(url, headers, body)]
        mock_post.assert_has_calls(calls)

        # Assert the call corrent
        mock_update_passwd.assert_called_once_with(
            bm_instance=bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1),
            username='username',
            password='newPassword')

    @mock.patch('bm_instance_agent.manager.AgentManager.console')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    def test_console(self, mock_driv, mock_console):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_console.return_value = {'port': 12345}
        self.test_ping()

        # Call the api
        resp = self.app.get('/v2/console/prepare', headers=fake.HEADERS)
        self.assertEqual(200, resp.status_int)
        data = {
            'success': True,
            'error': None,
            'port': 12345}
        self.assertEqual(data, resp.json_body)

        # Assert the call exist
        mock_console.assert_called()
