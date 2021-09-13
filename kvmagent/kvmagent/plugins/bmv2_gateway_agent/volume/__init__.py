from kvmagent.plugins.bmv2_gateway_agent import exception
from kvmagent.plugins.bmv2_gateway_agent.volume import ceph
from kvmagent.plugins.bmv2_gateway_agent.volume import sharedblock
from kvmagent.plugins.bmv2_gateway_agent.volume import thirdparty_ceph

mapping = {
    'ceph': ceph.CephVolume,
    'sharedblock': sharedblock.SharedBlockVolume,
    'thirdpartyCeph': thirdparty_ceph.ThirdPartyCephVolume
}


def get_driver(instance_obj, volume_obj):
    ps_type = volume_obj.primary_storage_type.lower()
    if is_third_party_ceph(volume_obj):
        ps_type = 'thirdpartyCeph'
    if ps_type not in mapping:
        raise exception.PrimaryStorageTypeNotSupport(
            primary_storage_type=ps_type)
    return mapping.get(ps_type)(instance_obj, volume_obj)


def is_third_party_ceph(token_object):
    return hasattr(token_object, "token") and token_object.token