import json
from oslo_log import log as logging

from bm_instance_agent.common import utils
from bm_instance_agent import exception

LOG = logging.getLogger(__name__)


class Base(object):
    """ Construct obj from req body
    """

    k_v_mapping = {}

    allowed_keys = ['volume_access_path_gateway_ips']

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
                port_obj = PortObj.from_json(port_dict)
                obj.nics.append(port_obj)

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

    allowed_keys = ['uuid', 'device_id', 'iscsi_path']

    @classmethod
    def from_json(cls, volume):
        obj = cls()
        obj.construct(volume)
        return obj


class PortObj(Base):
    PORT_TYPE_PHY = 'physical'
    PORT_TYPE_BOND = 'bond'
    PORT_TYPE_VLAN = 'vlan'
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
    {
        'type': 'bond',        // physical, bond
        'ifaceName': 'bond0',  //
        'paras': '',           // link parameter, json string, from 'BondTO'
        'mac': 'aa:bb:cc:dd:ee:ff',
        'ipAddress': '10.0.120.10',
        'netmask': '255.255.255.0',
        'gateway': '10.0.120.1',
        'vlanId': '1024',
        'defaultRoute': True
    }
    `nextDefaultRoutePort` only used during port detach.
    """

    allowed_keys = ['type', 'paras', 'mac', 'ip_address', 'netmask', 'gateway',
                    'default_route', 'iface_name', 'vlan_id']

    @classmethod
    def from_json(cls, port):
        obj = cls()
        obj.construct(port)
        if not obj.type:
            obj.type = obj.PORT_TYPE_PHY

        iface_name = obj.iface_name
        spec_if_name = iface_name and iface_name != ''

        local_ifaces = utils.get_interfaces()
        if not spec_if_name and obj.mac not in local_ifaces:
            raise exception.NewtorkInterfaceNotFound(mac=obj.mac,
                                                     vlan_id=obj.vlan_id)
        # NOTE(ya.wang) For vlan nic, the name is 'iface.vlan_id', therefore
        # try to split it.
        if not spec_if_name:
            iface_name = local_ifaces.get(obj.mac).split('.')[0]
            obj.iface_name = iface_name

        if obj.vlan_id:
            setattr(obj, 'vlan_if_name', '{iface_name}.{vlan_id}'.format(
                iface_name=iface_name, vlan_id=obj.vlan_id))
        else:
            setattr(obj, 'vlan_if_name', None)

        LOG.info('get port object {}'.format(obj.__dict__))
        return obj

    def get_l3_interface(self):
        return self.vlan_if_name if self.vlan_if_name else self.iface_name


class BondPortParasObj(Base):
    """ Construct a bond port config:
        An example::
        {
            "name": "bond0",
            "salves": "ac:1f:6b:ea:b3:d8,ac:1f:6b:ee:4a:8f",
            "opts":"mode=1,miimon=100"
        }
        """

    allowed_keys = ['name', 'slaves', 'opts']

    @classmethod
    def from_json(cls, paras):

        if isinstance(paras, (str, unicode)):
            paras = json.loads(paras)

        obj = cls()
        obj.construct(paras)

        link_paras = {}
        if obj.opts:
            link_paras = utils.config_to_dict(obj.opts, ',', '=')
        setattr(obj, 'link_paras', link_paras)

        slave_macs = obj.slaves.split(',')
        if len(slave_macs) == 0:
            raise exception.NewtorkInterfaceConfigParasInvalid(exception_msg="bond salve is null")

        slave_list = []
        phy_interfaces = utils.get_phy_interfaces()
        for slave_mac in slave_macs:
            if slave_mac in phy_interfaces:
                slave_list.append({'iface_name': phy_interfaces[slave_mac], 'master': obj.name})
            else:
                raise exception.NewtorkInterfaceNotFound(mac=slave_mac, vlan_id=0)

        if not slave_list:
            raise exception.NewtorkInterfaceConfigParasInvalid(
                exception_msg="at least one slave is specified in the bond")
        setattr(obj, 'slave_list', slave_list)

        LOG.info('get bond port object {}'.format(obj.__dict__))
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
            port_obj = PortObj.from_json(port_dict)
            obj.ports.append(port_obj)

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
