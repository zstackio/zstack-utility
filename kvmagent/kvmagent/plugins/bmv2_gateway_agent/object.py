import json
import os
import tempfile

from zstacklib.utils import shell

# from kvmagent.plugins.bmv2_gateway_agent import exception


class Base(object):
    """ Construct obj from req body
    """

    k_v_mapping = {}

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
        for k, v in self.k_v_mapping.items():
            if k in data.keys():
                setattr(self, v, data[k])
            if v in data.keys():
                setattr(self, v, data[v])

    @classmethod
    def construct_list(cls, items):
        obj = cls()
        for data in items:
            for k, v in obj.k_v_mapping.items():
                if k in data.keys():
                    setattr(obj, v, data[k])
            yield obj

    def to_json(self):
        return json.dumps(
            {k: getattr(self, k) for k in self.k_v_mapping.values()})


class BmInstanceObj(Base):
    """ Construct a bm instance obj from req body

    Bm instance part of req::
    {
        'bmInstance': {
            'uuid': 'uuid',
            'provisionIp': '192.168.101.10',
            'provisionMac': '00-00-00-00-00-00',
            'gatewayIp': '10.0.0.2'
        }
    }
    """

    k_v_mapping = {
        'uuid': 'uuid',
        'provisionIp': 'provision_ip',
        'provisionMac': 'provision_mac',
        'imageUuid': 'image_uuid',
        'gatewayIp': 'gateway_ip',
        'architecture': 'architecture',
        'customIqn': 'customIqn',
        'provisionType': 'provisionType'
    }

    @classmethod
    def from_json(cls, req):
        obj = cls()
        obj.construct(obj.body(req).get('bmInstance', {}))

        return obj


class NetworkObj(Base):
    """ Construct a network obj from req body
    
    A req body example::
    {
        'provisionNetwork': {
            'dhcpInterface': 'eno1',
            'dhcpRangeStartIp': '10.0.201.20',
            'dhcpRangeEndIp': '10.0.201.30',
            'dhcpRangeNetmask': '255.255.255.0',
            'dhcpRangeGateway': '10.0.201.1',
            'provisionNicIp': '10.0.201.10',
            'managementIp': '10.0.201.101',
            'callBackIp': '10.1.1.10',
            'callBackPort': '8080',
            'baremetal2InstanceProxyPort': '7090'
        }
    }
    """

    k_v_mapping = {
        'dhcpInterface': 'dhcp_interface',
        'dhcpRangeStartIp': 'dhcp_range_start_ip',
        'dhcpRangeEndIp': 'dhcp_range_end_ip',
        'dhcpRangeNetmask': 'dhcp_range_netmask',
        'dhcpRangeGateway': 'dhcp_range_gateway',
        'provisionNicIp': 'provision_nic_ip',
        'managementIp': 'management_ip',
        'callBackIp': 'callback_ip',
        'callBackPort': 'callback_port',
        'baremetal2InstanceProxyPort': 'baremetal_instance_proxy_port',
        'extraBootParams': 'extra_boot_params',
        'sendCommandUrl': 'send_command_url'
    }

    @classmethod
    def from_json(cls, req):
        obj = cls()
        obj.construct(obj.body(req).get('provisionNetwork', {}))

        bm_instance_objs = []
        bm_instances = obj.body(req).get(
            'provisionNetwork', {}).get('bmInstances')
        if bm_instances:
            for bm_instance in bm_instances:
                bm_instance_obj = BmInstanceObj.from_json(
                    {'body': {'bmInstance': bm_instance}})
                bm_instance_objs.append(bm_instance_obj)
        return obj, bm_instance_objs


class VolumeObj(Base):
    """ Construct a volume obj from req body

    Volume part of req::
    {
        'volume': {
            'uuid': 'uuid',
            'primaryStorageType': 'NFS',
            'type': 'Root/Data',
            'path': '/path/to/nfs/qcow2/volume',
            'format': 'qcow2'
        }
    }
    """

    k_v_mapping = {
        'uuid': 'uuid',
        'primaryStorageType': 'primary_storage_type',
        'type': 'type',
        'path': 'path',
        'format': 'format',
        'isShareable': 'is_shareable',
        'deviceId': 'device_id',
        'token': 'token',
        'tpTimeout': 'tpTimeout',
        'monIp': 'monIp',
        'iscsiPath': 'iscsiPath'
    }

    @classmethod
    def from_json(cls, req):
        obj = cls()
        obj.construct(obj.body(req).get('volume', {}))
        return obj

    @classmethod
    def from_json_list(cls, req):
        for vol in cls.body(req).get('volumes'):
            obj = cls()
            obj.construct(vol)
            yield obj


class TargetcliConfObj(object):
    """ Construct a object refer to targetcli configuration

    Load current targetcli configuration, assume the target has only one tpg.

    The loaded configuration example::
    {
        'storages': {
            'name1': {
                'dev': 'dev1',
                'plugin': enum['block', 'fileio', 'pscsi', 'ramdisk'],
                'wwn': 'bd8d596f-8bca-4524-97cf-19a297836df8'
            },
            'name2': {
                'dev': 'dev2',
                'plugin': enum['block', 'fileio', 'pscsi', 'ramdisk'],
                'wwn': '7698dfab-ffff-4cb3-b65b-926b1fe66b84'
            }
        },
        'targets': {
            'wwn1': {
                'luns': {
                    'storage_name1': 0,
                    'storage_name2': 1
                },
                'acls': ['node_wwn1']
            },
            'wwn2': {
                'luns': {
                    'storage_name3': '3'
                },
                'acls': ['node_wwn2', 'node_wwn3']
            }
        }
    }
    """

    def __init__(self, volume):
        self.volume = volume
        self.storages = {}
        self.targets = {}

        self.refresh()

    def refresh(self):
        temp_file = tempfile.mktemp()
        cmd = 'targetcli / saveconfig {temp_file}'.format(temp_file=temp_file)
        shell.call(cmd)
        with open(temp_file, 'r') as f:
            conf_raw = json.loads(f.read())
        os.remove(temp_file)

        for storage_obj in conf_raw.get('storage_objects'):
            name = storage_obj.get('name')
            self.storages[name] = {
                'dev': storage_obj.get('dev'),
                'wwn': storage_obj.get('wwn'),
                'plugin': storage_obj.get('plugin')
            }

        for target in conf_raw.get('targets'):
            wwn = target.get('wwn')
            tpg = target.get('tpgs')[0]

            target = {}
            target['acls'] = \
                [x.get('node_wwn') for x in tpg.get('node_acls')]
            luns = tpg.get('luns')
            target['luns'] = \
                {x.get('storage_object'): int(x.get('index')) for x in luns}

            self.targets.update({wwn: target})

    @property
    def backstore(self):
        return self.storages.get(self.volume.iscsi_backstore_name, {})

    @property
    def target(self):
        return self.targets.get(self.volume.iscsi_target, {})

    @property
    def luns(self):
        return self.targets.get(self.volume.iscsi_target, {}).get('luns', {})

    @property
    def acls(self):
        return self.targets.get(self.volume.iscsi_target, {}).get('acls', [])

    @property
    def lun_exist(self):
        backstore_full_path = '/backstores/block/{name}'.format(
            name=self.volume.iscsi_backstore_name)
        return True if backstore_full_path in self.luns else False

    @property
    def acl_exist(self):
        return True if self.volume.iscsi_acl in self.acls else False
