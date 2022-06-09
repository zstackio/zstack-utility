class BmV2InstanceAgentException(Exception):
    """ The base exception class for all exceptions this agent raises."""
    def __init__(self, msg=None):
        self.msg = self.__class__.__name__ if msg is None else msg
        super(BmV2InstanceAgentException, self).__init__(self.msg)


class Conflict(BmV2InstanceAgentException):

    code = 409


class BmInstanceUuidConflict(Conflict):

    def __init__(self, **kwargs):
        msg = ('The requested instance id: {req_instance_uuid} not equal to '
               'the exist instance id: {exist_instance_uuid}, please check '
               'the network configuration').format(**kwargs)
        super(BmInstanceUuidConflict, self).__init__(msg)


class BmInstanceRebootFailed(BmV2InstanceAgentException):

    def __init__(self, **kwargs):
        msg = ('The reboot action failed to execute, instance: {bm_uuid}, '
               'stderr: {stderr}').format(**kwargs)
        super(BmInstanceRebootFailed, self).__init__(msg)


class BmInstanceStopFailed(BmV2InstanceAgentException):

    def __init__(self, **kwargs):
        msg = ('The stop action failed to execute, instance: {bm_uuid}, '
               'stderr: {stderr}').format(**kwargs)
        super(BmInstanceStopFailed, self).__init__(msg)


class NewtorkInterfaceNotFound(BmV2InstanceAgentException):

    def __init__(self, **kwargs):
        msg = ('Unable to find a network interface matching the mac '
               'address: {mac}, vlan id: {vlan_id}').format(**kwargs)
        super(NewtorkInterfaceNotFound, self).__init__(msg)

class NewtorkInterfaceConfigParasInvalid(BmV2InstanceAgentException):

    def __init__(self, **kwargs):
        msg = 'The port configuration parameter is invalid: {exception_msg}'.format(**kwargs)
        super(NewtorkInterfaceConfigParasInvalid, self).__init__(msg)


class IscsiSessionIdNotFound(BmV2InstanceAgentException):

    def __init__(self, **kwargs):
        msg = ('Unable to find the iscsi session id during detaching '
               'volume: {volume_uuid}, the raw output: {output}'
               ).format(**kwargs)
        super(IscsiSessionIdNotFound, self).__init__(msg)


class IscsiDeviceNotFound(BmV2InstanceAgentException):

    def __init__(self, **kwargs):
        msg = ('Unable to find the iscsi device matching the lun '
               'id: {device_id} during detaching volume: {volume_uuid}'
               ).format(**kwargs)
        super(IscsiDeviceNotFound, self).__init__(msg)


class IscsiDeviceNotMatch(BmV2InstanceAgentException):

    def __init__(self, **kwargs):
        msg = ('The block device found via device id: {device_id} not '
               'match the block device: {device_name} during detaching '
               'volume: {volume_uuid}').format(**kwargs)
        super(IscsiDeviceNotMatch, self).__init__(msg)


class ProcessLaunchFailed(BmV2InstanceAgentException):

    def __init__(self, **kwargs):
        msg = ('Failed to launch {process_name}').format(**kwargs)
        super(ProcessLaunchFailed, self).__init__(msg)


class DefaultGatewayAddressNotEqual(BmV2InstanceAgentException):

    def __init__(self, **kwargs):
        msg = ('The old default gateway address: {old_address} not '
               'equal to the exist gateway address: {exist_address}'
               ).format(**kwargs)
        super(DefaultGatewayAddressNotEqual, self).__init__(msg)


class CPUArchNotSupport(BmV2InstanceAgentException):

    def __init__(self, **kwargs):
        msg = ('The cpu arch: {cpu_arch} not support currently.').format(
            **kwargs)
        super(CPUArchNotSupport, self).__init__(msg)
