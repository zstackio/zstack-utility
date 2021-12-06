import json

from bm_instance_agent.common import utils
from bm_instance_agent import exception


class Base(object):
    """ Construct obj from req body
    """

    k_v_mapping = {}

    allowed_keys = []

    def __init__(self):
        for v in self.k_v_mapping.values():
            setattr(self, v, None)

    @staticmethod
    def body(req):
        b_data = req.get('body', {})
        if isinstance(b_data, str):
            b_data = json.loads(b_data)
        return b_data

    def construct(self, data):
        for k in self.allowed_keys:
            setattr(self, k, data.get(k))

    def to_json(self):
        return {k: getattr(self, k) for k in self.allowed_keys}


class BmInstanceObj(Base):
    """ Construct a bm instance obj from req body

    Bm instance part of req::
    {
        'bmInstance': {
            'uuid': 'uuid',
            'provisionIp': '192.168.101.10',
            'provisionMac': 'aa:bb:cc:dd:ee:ff',
            'gatewayIp': '192.168.101.11',
            'nics': [
                {
                    'mac': 'aa:bb:cc:dd:ee:fe',
                    'ipAddress': '192.168.102.10',
                    'netmask': '255.255.255.0',
                    'gateway': '192.168.102.1',
                    'vlanId': '1024',
                    'defaultRoute': True
                }
            ]
        }
    }
    """

    allowed_keys = ['uuid', 'provision_ip', 'provision_mac', 'gateway_ip', 'custom_iqn', 'provision_type']

    @classmethod
    def from_json(cls, bm_instance):
        obj = cls()
        obj.construct(bm_instance)

        setattr(obj, 'nics', [])
        if 'nics' in bm_instance.keys():
            for port_dict in bm_instance['nics']:
                obj.nics.append(PortObj.from_json(port_dict))

        return obj


class VolumeObj(Base):
    """ Construct a volume obj from req body

    Volume part of req::
    {
        'volume': {
            'uuid': 'uuid',
            'primaryStorageType': 'NFS',
            'type': 'Data/Sys',
            'path': '/path/to/nfs/qcow2/volume',
            'format': 'qcow2',
            'deviceId': 2
        }
    }
    """

    allowed_keys = ['uuid', 'device_id']

    @classmethod
    def from_json(cls, volume):
        obj = cls()
        obj.construct(volume)
        return obj


class PortObj(Base):
    """ Construct a Port obj from req body

    A port example::
    {
        'mac': 'aa:bb:cc:dd:ee:ff',
        'ipAddress': '10.0.120.10',
        'netmask': '255.255.255.0',
        'gateway': '10.0.120.1',
        'vlanId': '1024',
        'defaultRoute': True
    }

    `nextDefaultRoutePort` only used during port detach.
    """

    allowed_keys = ['mac', 'ip_address', 'netmask', 'gateway',
                    'default_route', 'iface_name', 'vlan_id']

    @classmethod
    def from_json(cls, port):
        obj = cls()
        obj.construct(port)

        local_ifaces = utils.get_interfaces()
        if obj.mac not in local_ifaces:
            raise exception.NewtorkInterfaceNotFound(mac=obj.mac,
                                                     vlan_id=obj.vlan_id)
        # NOTE(ya.wang) For vlan nic, the name is 'iface.vlan_id', therefore
        # try to split it.
        iface_name = local_ifaces.get(obj.mac).split('.')[0]
        if obj.vlan_id:
            iface_name = '{iface_name}.{vlan_id}'.format(
                iface_name=iface_name, vlan_id=obj.vlan_id)
        setattr(obj, 'iface_name', iface_name)

        return obj


class NetworkObj(Base):
    """ Construct a network obj from req body

    single port req example::
    {
        'port': {
            'mac': '52:54:00:23:f1:c0',
            'ipAddress': '10.0.120.10',
            'netmask': '255.255.255.0',
            'gateway': '10.0.120.1',
            'vlanId': '1024',
            'defaultRoute': True
        }
    }

    multi ports req example::
    {
        'ports': [
            {
                'mac': '52:54:00:23:a1:c0',
                'ipAddress': '10.0.120.10',
                'netmask': '255.255.255.0',
                'gateway': '10.0.120.1',
                'vlanId': '1024',
                'defaultRoute': True
            },
            {
                'mac': '52:54:00:e5:c3:bf',
                'ipAddress': '10.0.130.10',
                'netmask': '255.255.255.0',
                'gateway': '10.0.130.1',
                'vlanId': '1024',
                'defaultRoute': False
            }
        ]
    }

    """

    @classmethod
    def from_json(cls, req):
        if not req:
            return None

        obj = cls()
        setattr(obj, 'default_gw_addr', '')
        setattr(obj, 'ports', [])

        ports = req if isinstance(req, list) else [req]
        for port_dict in ports:
            obj.ports.append(PortObj.from_json(port_dict))

            if port_dict.get('default_route'):
                obj.default_gw_addr = port_dict.get('gateway')
        return obj


class HeaderObj(Base):
    """ Construct a request header obj from req headers

    A req headers example::
    {
        'taskuuid': '4dca1e5c-6b25-498d-b89e-99c55b32bd81',
        'callbackurl': 'mn callback url',
        'Gateway-Callback-Uri': 'The callback url which proxy by gw nginx'
    }

    If callbackurl and Gateway-Callback-Uri both exist, use
    Gateway-Callback-Uri
    """

    allowed_keys = ['task_uuid', 'callback_url']

    @classmethod
    def from_headers(cls, headers):
        obj = cls()

        setattr(obj, 'task_uuid', headers.get('taskuuid'))

        if 'Gateway-Callback-Uri' in headers:
            setattr(obj, 'callback_url', headers.get('Gateway-Callback-Uri'))
        else:
            setattr(obj, 'callback_url', headers.get('callbackurl'))

        return obj
