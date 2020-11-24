from kvmagent.plugins.bmv2_gateway_agent import exception
from kvmagent.plugins.bmv2_gateway_agent.volume import sharedblock


mapping = {
    'sharedblock': sharedblock.SharedBlockVolume
}


def get_driver(instance_obj, volume_obj):
    ps_type = volume_obj.primary_storage_type.lower()
    if ps_type not in mapping.keys():
        raise exception.PrimaryStorageTypeNotSupport(
            primary_storage_type=ps_type)
    return mapping.get(ps_type)(instance_obj, volume_obj)
