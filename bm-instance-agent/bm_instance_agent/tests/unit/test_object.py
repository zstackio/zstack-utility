import copy

import mock

from bm_instance_agent.common import utils as bm_utils
from bm_instance_agent import objects
from bm_instance_agent.tests import base
from bm_instance_agent.tests.unit import fake


class TestObject(base.TestCase):

    def test_bm_instance_obj(self):
        bm_instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))

        data = {
            'uuid': '7b432900-c0ad-47e7-b1c7-01b74961c235',
            'provision_ip': '192.168.101.10',
            'provision_mac': '52:54:00:3b:a5:1f'
        }
        self.assertEqual(data, bm_instance_obj.to_json())

    def test_volume_obj(self):
        volume_obj = objects.VolumeObj.from_json(
            bm_utils.camel_obj_to_snake(fake.VOLUME1))

        data = {
            'uuid': '529c7537-3c94-499e-add7-551ab27205f2',
            'device_id': 1,
        }
        self.assertEqual(data, volume_obj.to_json())

    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    def test_network_obj(self, mock_ifaces, mock_ifaddr):
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (fake.IFACE_PORT1, fake.IFACE_PORT2)
        network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT2))

        data = {
            'mac': '52:54:00:4a:c0:1f',
            'ip_address': '10.0.0.20',
            'netmask': '255.255.255.0',
            'gateway': '10.0.0.1',
            'default_route': True,
            'iface_name': 'enp4s0f1'
        }
        self.assertEqual(data, network_obj.ports[0].to_json())
        self.assertEqual('10.0.0.1', network_obj.default_gw_addr)

    def test_header_obj(self):
        header_obj = objects.HeaderObj.from_headers(fake.HEADERS)

        data = {
            'task_uuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c',
            'callback_url': 'http://127.0.0.1:8080'
        }
        self.assertEqual(data, header_obj.to_json())

    def test_header_obj_with_gateway_cb_url(self):
        headers = copy.deepcopy(fake.HEADERS)
        headers.update({'Gateway-Callback-Uri': 'http://127.0.0.1:9090'})
        header_obj = objects.HeaderObj.from_headers(headers)

        data = {
            'task_uuid': 'd123d27c-4b4f-4368-a33c-acfc5d9eaf2c',
            'callback_url': 'http://127.0.0.1:9090'
        }
        self.assertEqual(data, header_obj.to_json())
