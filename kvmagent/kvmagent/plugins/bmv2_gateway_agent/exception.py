class BmV2GwAgentException(Exception):
    """ The base exception class for all exceptions this agent raises."""
    def __init__(self, msg=None):
        self.msg = self.__class__.__name__ if msg is None else msg
        super(BmV2GwAgentException, self).__init__(self.msg)


class NbdIdNotFound(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to find the nbd device id, instance: {instance_uuid}, '
               'volume: {volume_uuid}').format(**kwargs)
        super(NbdIdNotFound, self).__init__(msg)


class NoAvailableNbdDevice(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Can not find available nbd device to connect, try increase '
               '`nbds_max` param during modprobe nbd, instance: '
               '{instance_uuid}, volume: {volume_uuid}').format(**kwargs)
        super(NoAvailableNbdDevice, self).__init__(msg)


class NbdDeviceFailedConnect(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to connect nbd device {nbd_dev}, check the '
               'system log for more information, instance: {instance_uuid}, '
               'volume: {volume_uuid}, backend dev: {nbd_backend}'
               ).format(**kwargs)
        super(NbdDeviceFailedConnect, self).__init__(msg)


class NbdDeviceFailedDisconnect(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('The nbd device {nbd_dev} failed to disconnect, check the '
               'system log for more information, instance: {instance_uuid}, '
               'volume: {volume_uuid}, backend dev: {nbd_backend}'
               ).format(**kwargs)
        super(NbdDeviceFailedDisconnect, self).__init__(msg)


class DeviceMapperFailedCreate(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to create device mapper {dm_name}, check the system '
               'log for more information, instance: {instance_uuid}, '
               'volume: {volume_uuid}, backend dev: {dm_backend}'
               ).format(**kwargs)
        super(DeviceMapperFailedCreate, self).__init__(msg)


class DeviceMapperFailedRemove(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to remove device mapper {dm_name}, check the system '
               'log for more information, instance: {instance_uuid}, '
               'volume: {volume_uuid}, backend dev: {dm_backend}'
               ).format(**kwargs)
        super(DeviceMapperFailedRemove, self).__init__(msg)


class DeviceMapperFailedReload(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to reload device mapper {dm_name}, {dst_dm_backend} '
               'not in dm table, check the system log for more information, '
               'instance: {instance_uuid}, volume: {volume_uuid}, source '
               'backend dev: {src_dm_backend}, dst backend dev: '
               '{dst_dm_backend}').format(**kwargs)
        super(DeviceMapperFailedReload, self).__init__(msg)


class DeviceMapperFailedSuspend(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to suspend device mapper {dm_name}, check the system '
               'log for more information, instance: {instance_uuid}, '
               'volume: {volume_uuid}, backend dev: {dm_backend}'
               ).format(**kwargs)
        super(DeviceMapperFailedSuspend, self).__init__(msg)


class DeviceMapperFailedResume(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to resume device mapper {dm_name}, check the system '
               'log for more information, instance: {instance_uuid}, '
               'volume: {volume_uuid}, backend dev: {dm_backend}'
               ).format(**kwargs)
        super(DeviceMapperFailedResume, self).__init__(msg)


class IscsiBackstoreFailedCreate(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to create targetcli backstore {backstore}, check the '
               'system log for more information, instance: {instance_uuid}, '
               'volume: {volume_uuid}, backend dev: {iscsi_backend}'
               ).format(**kwargs)
        super(IscsiBackstoreFailedCreate, self).__init__(msg)


class IscsiTargetFailedCreate(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to create targetcli target {target}, check the '
               'system log for more information, instance: {instance_uuid}, '
               'volume: {volume_uuid}, backend dev: {iscsi_backend}'
               ).format(**kwargs)
        super(IscsiTargetFailedCreate, self).__init__(msg)


class IscsiLunFailedCreate(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to create targetcli lun {lun}, check the '
               'system log for more information, instance: {instance_uuid}, '
               'volume: {volume_uuid}, backend dev: {iscsi_backend}'
               ).format(**kwargs)
        super(IscsiLunFailedCreate, self).__init__(msg)


class IscsiAclFailedCreate(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to create targetcli acl {acl}, check the '
               'system log for more information, instance: {instance_uuid}, '
               'volume: {volume_uuid}, backend dev: {iscsi_backend}'
               ).format(**kwargs)
        super(IscsiLunFailedCreate, self).__init__(msg)


class DeviceNotExist(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('The device {dev} not exist, instance: {instance_uuid}, '
               'volume: {volume_uuid}').format(**kwargs)
        super(DeviceNotExist, self).__init__(msg)


class PrimaryStorageTypeNotSupport(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('The primary storage type: {primary_storage_type} not '
               'support yet.').format(**kwargs)
        super(PrimaryStorageTypeNotSupport, self).__init__(msg)


class ManagementNetProvisionNetMixed(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('The management network interface and provision network '
               'interface are mixed, please choose another network '
               'interface and try again.')
        super(ManagementNetProvisionNetMixed, self).__init__(msg)


class LockNotRelease(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('The lock {name} is acquired by thread {thread}, acquired '
               'time: {time}, timeout: {timeout}').format(**kwargs)
        super(LockNotRelease, self).__init__(msg)


class PortInUse(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('The port {port} is in using, please change the port and '
               'try again').format(**kwargs)
        super(PortInUse, self).__init__(msg)


class CephCommandsNotExist(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Not all commands of {cmds} can be found in the gateway').format(**kwargs)
        super(CephCommandsNotExist, self).__init__(msg)


class RbdImageNotExist(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('RBD image {path} can not be found in the gateway').format(**kwargs)
        super(RbdImageNotExist, self).__init__(msg)


class CephPackageNotFound(BmV2GwAgentException):

    def __init__(self, **kwargs):
        msg = ('Package {cmd} info can not be found in the gateway').format(**kwargs)
        super(CephPackageNotFound, self).__init__(msg)

