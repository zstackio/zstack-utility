BM_INSTANCE_BASE_SCHEMA = {
    'type': 'object',
    'properties': {
        'uuid': {'type': 'string'},
        'provision_ip': {'type': 'string'},
        'provision_mac': {'type': 'string'},
        'custom_iqn': {'type': 'string'}
    },
    'required': ['uuid', 'provision_ip', 'provision_mac']
}


PING_V2_SCHEMA = {
    'type': 'object',
    'properties': {
        'bm_instance': BM_INSTANCE_BASE_SCHEMA
    }
}


REBOOT_V2_SCHEMA = {
    'type': 'object',
    'properties': {
        'bm_instance': BM_INSTANCE_BASE_SCHEMA
    }
}


STOP_V2_SCHEMA = {
    'type': 'object',
    'properties': {
        'bm_instance': BM_INSTANCE_BASE_SCHEMA
    }
}


VOLUME_ATTACH_V2_SCHEMA = {
    'type': 'object',
    'properties': {
        'volume': {
            'type': 'object',
            'properties': {
                'uuid': {'type': 'string'},
                'type': {'type': 'string', 'enum': ['Root', 'Data']},
                'format': {'type': 'string', 'enum': ['raw', 'qcow2']},
                'device_id': {'type': 'string'},
                'primary_storage_type': {
                    'type': 'string',
                    'enum': ['Ceph', 'NFS', 'SharedBlock']
                }
            },
            'required': ['uuid', 'type', 'format', 'device_id',
                         'primary_storage_type']
        },
        'bm_instance': BM_INSTANCE_BASE_SCHEMA
    }
}


VOLUME_DETACH_V2_SCHEMA = VOLUME_ATTACH_V2_SCHEMA


NIC_BASE_SCHEMA = {
    'type': 'object',
    'properties': {
        'mac': {'type': 'string'},
        'ip_address': {'type': 'string'},
        'netmask': {'type', 'string'},
        'gateway': {'type': 'string'},
        'default_route': {'type': 'boolean'}
    },
    'required': ['mac', 'ip_address', 'netmask', 'gateway', 'default_route']
}


NIC_ATTACH_V2_SCHEMA = {
    'type': 'object',
    'properties': {
        'nic': NIC_BASE_SCHEMA,
        'bm_instance': BM_INSTANCE_BASE_SCHEMA
    }
}


NIC_DETACH_V2_SCHEMA = NIC_ATTACH_V2_SCHEMA


DEFAULT_ROUTE_CHANGE_V2_SCHEMA = {
    'type': 'object',
    'properties': {
        'old_default': NIC_BASE_SCHEMA,
        'new_default': NIC_BASE_SCHEMA,
        'bm_instance': BM_INSTANCE_BASE_SCHEMA
    }
}


PASSWORD_CHANGE_V2_SCHEMA = {
    'type': 'object',
    'properties': {
        'password': {'type': 'string'},
        'bm_instance': BM_INSTANCE_BASE_SCHEMA
    }
}
