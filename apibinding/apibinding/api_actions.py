from apibinding import inventory
from apibinding import api
from zstacklib.utils import jsonobject

class AddAliyunKeySecretAction(inventory.APIAddAliyunKeySecretMsg):
    def __init__(self):
        super(AddAliyunKeySecretAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddAliyunKeySecretAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddCephBackupStorageAction(inventory.APIAddCephBackupStorageMsg):
    def __init__(self):
        super(AddCephBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddCephBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddCephPrimaryStorageAction(inventory.APIAddCephPrimaryStorageMsg):
    def __init__(self):
        super(AddCephPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddCephPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddCephPrimaryStoragePoolAction(inventory.APIAddCephPrimaryStoragePoolMsg):
    def __init__(self):
        super(AddCephPrimaryStoragePoolAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddCephPrimaryStoragePoolAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddConnectionAccessPointFromRemoteAction(inventory.APIAddConnectionAccessPointFromRemoteMsg):
    def __init__(self):
        super(AddConnectionAccessPointFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddConnectionAccessPointFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddDataCenterFromRemoteAction(inventory.APIAddDataCenterFromRemoteMsg):
    def __init__(self):
        super(AddDataCenterFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddDataCenterFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddDisasterImageStoreBackupStorageAction(inventory.APIAddDisasterImageStoreBackupStorageMsg):
    def __init__(self):
        super(AddDisasterImageStoreBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddDisasterImageStoreBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddDnsToL3NetworkAction(inventory.APIAddDnsToL3NetworkMsg):
    def __init__(self):
        super(AddDnsToL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddDnsToL3NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddFusionstorBackupStorageAction(inventory.APIAddFusionstorBackupStorageMsg):
    def __init__(self):
        super(AddFusionstorBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddFusionstorBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddFusionstorPrimaryStorageAction(inventory.APIAddFusionstorPrimaryStorageMsg):
    def __init__(self):
        super(AddFusionstorPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddFusionstorPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddIdentityZoneFromRemoteAction(inventory.APIAddIdentityZoneFromRemoteMsg):
    def __init__(self):
        super(AddIdentityZoneFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddIdentityZoneFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddImageAction(inventory.APIAddImageMsg):
    def __init__(self):
        super(AddImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddImageStoreBackupStorageAction(inventory.APIAddImageStoreBackupStorageMsg):
    def __init__(self):
        super(AddImageStoreBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddImageStoreBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddIpRangeAction(inventory.APIAddIpRangeMsg):
    def __init__(self):
        super(AddIpRangeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddIpRangeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddIpRangeByNetworkCidrAction(inventory.APIAddIpRangeByNetworkCidrMsg):
    def __init__(self):
        super(AddIpRangeByNetworkCidrAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddIpRangeByNetworkCidrAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddKVMHostAction(inventory.APIAddKVMHostMsg):
    def __init__(self):
        super(AddKVMHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddKVMHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddLdapServerAction(inventory.APIAddLdapServerMsg):
    def __init__(self):
        super(AddLdapServerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddLdapServerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddLocalPrimaryStorageAction(inventory.APIAddLocalPrimaryStorageMsg):
    def __init__(self):
        super(AddLocalPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddLocalPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddMonToCephBackupStorageAction(inventory.APIAddMonToCephBackupStorageMsg):
    def __init__(self):
        super(AddMonToCephBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddMonToCephBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddMonToCephPrimaryStorageAction(inventory.APIAddMonToCephPrimaryStorageMsg):
    def __init__(self):
        super(AddMonToCephPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddMonToCephPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddMonToFusionstorBackupStorageAction(inventory.APIAddMonToFusionstorBackupStorageMsg):
    def __init__(self):
        super(AddMonToFusionstorBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddMonToFusionstorBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddMonToFusionstorPrimaryStorageAction(inventory.APIAddMonToFusionstorPrimaryStorageMsg):
    def __init__(self):
        super(AddMonToFusionstorPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddMonToFusionstorPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddNetworkServiceProviderAction(inventory.APIAddNetworkServiceProviderMsg):
    def __init__(self):
        super(AddNetworkServiceProviderAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddNetworkServiceProviderAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddNfsPrimaryStorageAction(inventory.APIAddNfsPrimaryStorageMsg):
    def __init__(self):
        super(AddNfsPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddNfsPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddNodeToSurfsBackupStorageAction(inventory.APIAddNodeToSurfsBackupStorageMsg):
    def __init__(self):
        super(AddNodeToSurfsBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddNodeToSurfsBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddNodeToSurfsPrimaryStorageAction(inventory.APIAddNodeToSurfsPrimaryStorageMsg):
    def __init__(self):
        super(AddNodeToSurfsPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddNodeToSurfsPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddOssBucketFromRemoteAction(inventory.APIAddOssBucketFromRemoteMsg):
    def __init__(self):
        super(AddOssBucketFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddOssBucketFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddSchedulerJobToSchedulerTriggerAction(inventory.APIAddSchedulerJobToSchedulerTriggerMsg):
    def __init__(self):
        super(AddSchedulerJobToSchedulerTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddSchedulerJobToSchedulerTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddSecurityGroupRuleAction(inventory.APIAddSecurityGroupRuleMsg):
    def __init__(self):
        super(AddSecurityGroupRuleAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddSecurityGroupRuleAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddSftpBackupStorageAction(inventory.APIAddSftpBackupStorageMsg):
    def __init__(self):
        super(AddSftpBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddSftpBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddSharedMountPointPrimaryStorageAction(inventory.APIAddSharedMountPointPrimaryStorageMsg):
    def __init__(self):
        super(AddSharedMountPointPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddSharedMountPointPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddSimulatorBackupStorageAction(inventory.APIAddSimulatorBackupStorageMsg):
    def __init__(self):
        super(AddSimulatorBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddSimulatorBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddSimulatorHostAction(inventory.APIAddSimulatorHostMsg):
    def __init__(self):
        super(AddSimulatorHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddSimulatorHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddSimulatorPrimaryStorageAction(inventory.APIAddSimulatorPrimaryStorageMsg):
    def __init__(self):
        super(AddSimulatorPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddSimulatorPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddSurfsBackupStorageAction(inventory.APIAddSurfsBackupStorageMsg):
    def __init__(self):
        super(AddSurfsBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddSurfsBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddSurfsPrimaryStorageAction(inventory.APIAddSurfsPrimaryStorageMsg):
    def __init__(self):
        super(AddSurfsPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddSurfsPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddUserToGroupAction(inventory.APIAddUserToGroupMsg):
    def __init__(self):
        super(AddUserToGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddUserToGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddVCenterAction(inventory.APIAddVCenterMsg):
    def __init__(self):
        super(AddVCenterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddVCenterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddVRouterRouteEntryAction(inventory.APIAddVRouterRouteEntryMsg):
    def __init__(self):
        super(AddVRouterRouteEntryAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddVRouterRouteEntryAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddVmNicToLoadBalancerAction(inventory.APIAddVmNicToLoadBalancerMsg):
    def __init__(self):
        super(AddVmNicToLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddVmNicToLoadBalancerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddVmNicToSecurityGroupAction(inventory.APIAddVmNicToSecurityGroupMsg):
    def __init__(self):
        super(AddVmNicToSecurityGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddVmNicToSecurityGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddXSkyPrimaryStorageAction(inventory.APIAddXSkyPrimaryStorageMsg):
    def __init__(self):
        super(AddXSkyPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddXSkyPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AddZsesPrimaryStorageAction(inventory.APIAddZsesPrimaryStorageMsg):
    def __init__(self):
        super(AddZsesPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddZsesPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachAliyunDiskToEcsAction(inventory.APIAttachAliyunDiskToEcsMsg):
    def __init__(self):
        super(AttachAliyunDiskToEcsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachAliyunDiskToEcsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachAliyunKeyAction(inventory.APIAttachAliyunKeyMsg):
    def __init__(self):
        super(AttachAliyunKeyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachAliyunKeyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachBackupStorageToZoneAction(inventory.APIAttachBackupStorageToZoneMsg):
    def __init__(self):
        super(AttachBackupStorageToZoneAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachBackupStorageToZoneAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachDataVolumeToVmAction(inventory.APIAttachDataVolumeToVmMsg):
    def __init__(self):
        super(AttachDataVolumeToVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachDataVolumeToVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachEipAction(inventory.APIAttachEipMsg):
    def __init__(self):
        super(AttachEipAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachEipAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachHybridEipToEcsAction(inventory.APIAttachHybridEipToEcsMsg):
    def __init__(self):
        super(AttachHybridEipToEcsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachHybridEipToEcsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachIsoToVmInstanceAction(inventory.APIAttachIsoToVmInstanceMsg):
    def __init__(self):
        super(AttachIsoToVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachIsoToVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachL2NetworkToClusterAction(inventory.APIAttachL2NetworkToClusterMsg):
    def __init__(self):
        super(AttachL2NetworkToClusterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachL2NetworkToClusterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachL3NetworkToVmAction(inventory.APIAttachL3NetworkToVmMsg):
    def __init__(self):
        super(AttachL3NetworkToVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachL3NetworkToVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachMonitorTriggerActionToTriggerAction(inventory.APIAttachMonitorTriggerActionToTriggerMsg):
    def __init__(self):
        super(AttachMonitorTriggerActionToTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachMonitorTriggerActionToTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachNetworkServiceProviderToL2NetworkAction(inventory.APIAttachNetworkServiceProviderToL2NetworkMsg):
    def __init__(self):
        super(AttachNetworkServiceProviderToL2NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachNetworkServiceProviderToL2NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachNetworkServiceToL3NetworkAction(inventory.APIAttachNetworkServiceToL3NetworkMsg):
    def __init__(self):
        super(AttachNetworkServiceToL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachNetworkServiceToL3NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachOssBucketToEcsDataCenterAction(inventory.APIAttachOssBucketToEcsDataCenterMsg):
    def __init__(self):
        super(AttachOssBucketToEcsDataCenterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachOssBucketToEcsDataCenterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachPciDeviceToVmAction(inventory.APIAttachPciDeviceToVmMsg):
    def __init__(self):
        super(AttachPciDeviceToVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachPciDeviceToVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachPoliciesToUserAction(inventory.APIAttachPoliciesToUserMsg):
    def __init__(self):
        super(AttachPoliciesToUserAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachPoliciesToUserAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachPolicyToUserAction(inventory.APIAttachPolicyToUserMsg):
    def __init__(self):
        super(AttachPolicyToUserAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachPolicyToUserAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachPolicyToUserGroupAction(inventory.APIAttachPolicyToUserGroupMsg):
    def __init__(self):
        super(AttachPolicyToUserGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachPolicyToUserGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachPortForwardingRuleAction(inventory.APIAttachPortForwardingRuleMsg):
    def __init__(self):
        super(AttachPortForwardingRuleAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachPortForwardingRuleAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachPrimaryStorageToClusterAction(inventory.APIAttachPrimaryStorageToClusterMsg):
    def __init__(self):
        super(AttachPrimaryStorageToClusterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachPrimaryStorageToClusterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachSecurityGroupToL3NetworkAction(inventory.APIAttachSecurityGroupToL3NetworkMsg):
    def __init__(self):
        super(AttachSecurityGroupToL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachSecurityGroupToL3NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachUsbDeviceToVmAction(inventory.APIAttachUsbDeviceToVmMsg):
    def __init__(self):
        super(AttachUsbDeviceToVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachUsbDeviceToVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class AttachVRouterRouteTableToVRouterAction(inventory.APIAttachVRouterRouteTableToVRouterMsg):
    def __init__(self):
        super(AttachVRouterRouteTableToVRouterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AttachVRouterRouteTableToVRouterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class BackupDataVolumeAction(inventory.APIBackupDataVolumeMsg):
    def __init__(self):
        super(BackupDataVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[BackupDataVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class BackupDatabaseToPublicCloudAction(inventory.APIBackupDatabaseToPublicCloudMsg):
    def __init__(self):
        super(BackupDatabaseToPublicCloudAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[BackupDatabaseToPublicCloudAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class BackupStorageMigrateImageAction(inventory.APIBackupStorageMigrateImageMsg):
    def __init__(self):
        super(BackupStorageMigrateImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[BackupStorageMigrateImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class BackupVolumeSnapshotAction(inventory.APIBackupVolumeSnapshotMsg):
    def __init__(self):
        super(BackupVolumeSnapshotAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[BackupVolumeSnapshotAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CalculateAccountSpendingAction(inventory.APICalculateAccountSpendingMsg):
    def __init__(self):
        super(CalculateAccountSpendingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CalculateAccountSpendingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeBackupStorageStateAction(inventory.APIChangeBackupStorageStateMsg):
    def __init__(self):
        super(ChangeBackupStorageStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeBackupStorageStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeClusterStateAction(inventory.APIChangeClusterStateMsg):
    def __init__(self):
        super(ChangeClusterStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeClusterStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeDiskOfferingStateAction(inventory.APIChangeDiskOfferingStateMsg):
    def __init__(self):
        super(ChangeDiskOfferingStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeDiskOfferingStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeEipStateAction(inventory.APIChangeEipStateMsg):
    def __init__(self):
        super(ChangeEipStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeEipStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeHostStateAction(inventory.APIChangeHostStateMsg):
    def __init__(self):
        super(ChangeHostStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeHostStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeIPSecConnectionStateAction(inventory.APIChangeIPSecConnectionStateMsg):
    def __init__(self):
        super(ChangeIPSecConnectionStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeIPSecConnectionStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeImageStateAction(inventory.APIChangeImageStateMsg):
    def __init__(self):
        super(ChangeImageStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeImageStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeInstanceOfferingAction(inventory.APIChangeInstanceOfferingMsg):
    def __init__(self):
        super(ChangeInstanceOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeInstanceOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeInstanceOfferingStateAction(inventory.APIChangeInstanceOfferingStateMsg):
    def __init__(self):
        super(ChangeInstanceOfferingStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeInstanceOfferingStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeL3NetworkStateAction(inventory.APIChangeL3NetworkStateMsg):
    def __init__(self):
        super(ChangeL3NetworkStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeL3NetworkStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeMediaStateAction(inventory.APIChangeMediaStateMsg):
    def __init__(self):
        super(ChangeMediaStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeMediaStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeMonitorTriggerActionStateAction(inventory.APIChangeMonitorTriggerActionStateMsg):
    def __init__(self):
        super(ChangeMonitorTriggerActionStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeMonitorTriggerActionStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeMonitorTriggerStateAction(inventory.APIChangeMonitorTriggerStateMsg):
    def __init__(self):
        super(ChangeMonitorTriggerStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeMonitorTriggerStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangePortForwardingRuleStateAction(inventory.APIChangePortForwardingRuleStateMsg):
    def __init__(self):
        super(ChangePortForwardingRuleStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangePortForwardingRuleStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangePrimaryStorageStateAction(inventory.APIChangePrimaryStorageStateMsg):
    def __init__(self):
        super(ChangePrimaryStorageStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangePrimaryStorageStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeResourceOwnerAction(inventory.APIChangeResourceOwnerMsg):
    def __init__(self):
        super(ChangeResourceOwnerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeResourceOwnerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeSchedulerStateAction(inventory.APIChangeSchedulerStateMsg):
    def __init__(self):
        super(ChangeSchedulerStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeSchedulerStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeSecurityGroupStateAction(inventory.APIChangeSecurityGroupStateMsg):
    def __init__(self):
        super(ChangeSecurityGroupStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeSecurityGroupStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeVipStateAction(inventory.APIChangeVipStateMsg):
    def __init__(self):
        super(ChangeVipStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeVipStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeVmPasswordAction(inventory.APIChangeVmPasswordMsg):
    def __init__(self):
        super(ChangeVmPasswordAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeVmPasswordAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeVolumeStateAction(inventory.APIChangeVolumeStateMsg):
    def __init__(self):
        super(ChangeVolumeStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeVolumeStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ChangeZoneStateAction(inventory.APIChangeZoneStateMsg):
    def __init__(self):
        super(ChangeZoneStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ChangeZoneStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CheckApiPermissionAction(inventory.APICheckApiPermissionMsg):
    def __init__(self):
        super(CheckApiPermissionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CheckApiPermissionAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CheckIpAvailabilityAction(inventory.APICheckIpAvailabilityMsg):
    def __init__(self):
        super(CheckIpAvailabilityAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CheckIpAvailabilityAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CleanInvalidLdapBindingAction(inventory.APICleanInvalidLdapBindingMsg):
    def __init__(self):
        super(CleanInvalidLdapBindingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CleanInvalidLdapBindingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CleanUpImageCacheOnPrimaryStorageAction(inventory.APICleanUpImageCacheOnPrimaryStorageMsg):
    def __init__(self):
        super(CleanUpImageCacheOnPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CleanUpImageCacheOnPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CloneEcsInstanceFromLocalVmAction(inventory.APICloneEcsInstanceFromLocalVmMsg):
    def __init__(self):
        super(CloneEcsInstanceFromLocalVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CloneEcsInstanceFromLocalVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CloneVmInstanceAction(inventory.APICloneVmInstanceMsg):
    def __init__(self):
        super(CloneVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CloneVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CommitVolumeAsImageAction(inventory.APICommitVolumeAsImageMsg):
    def __init__(self):
        super(CommitVolumeAsImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CommitVolumeAsImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateAccountAction(inventory.APICreateAccountMsg):
    def __init__(self):
        super(CreateAccountAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateAccountAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateAliyunDiskFromRemoteAction(inventory.APICreateAliyunDiskFromRemoteMsg):
    def __init__(self):
        super(CreateAliyunDiskFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateAliyunDiskFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateAliyunSnapshotRemoteAction(inventory.APICreateAliyunSnapshotRemoteMsg):
    def __init__(self):
        super(CreateAliyunSnapshotRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateAliyunSnapshotRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateAliyunVpcVirtualRouterEntryRemoteAction(inventory.APICreateAliyunVpcVirtualRouterEntryRemoteMsg):
    def __init__(self):
        super(CreateAliyunVpcVirtualRouterEntryRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateAliyunVpcVirtualRouterEntryRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateBaremetalChassisAction(inventory.APICreateBaremetalChassisMsg):
    def __init__(self):
        super(CreateBaremetalChassisAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateBaremetalChassisAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateBaremetalHostCfgAction(inventory.APICreateBaremetalHostCfgMsg):
    def __init__(self):
        super(CreateBaremetalHostCfgAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateBaremetalHostCfgAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateBaremetalPxeServerAction(inventory.APICreateBaremetalPxeServerMsg):
    def __init__(self):
        super(CreateBaremetalPxeServerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateBaremetalPxeServerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateClusterAction(inventory.APICreateClusterMsg):
    def __init__(self):
        super(CreateClusterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateClusterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateConnectionBetweenL3NetworkAndAliyunVSwitchAction(inventory.APICreateConnectionBetweenL3NetworkAndAliyunVSwitchMsg):
    def __init__(self):
        super(CreateConnectionBetweenL3NetworkAndAliyunVSwitchAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateConnectionBetweenL3NetworkAndAliyunVSwitchAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateDataVolumeAction(inventory.APICreateDataVolumeMsg):
    def __init__(self):
        super(CreateDataVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateDataVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateDataVolumeFromVolumeSnapshotAction(inventory.APICreateDataVolumeFromVolumeSnapshotMsg):
    def __init__(self):
        super(CreateDataVolumeFromVolumeSnapshotAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateDataVolumeFromVolumeSnapshotAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateDataVolumeFromVolumeTemplateAction(inventory.APICreateDataVolumeFromVolumeTemplateMsg):
    def __init__(self):
        super(CreateDataVolumeFromVolumeTemplateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateDataVolumeFromVolumeTemplateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateDataVolumeTemplateFromVolumeAction(inventory.APICreateDataVolumeTemplateFromVolumeMsg):
    def __init__(self):
        super(CreateDataVolumeTemplateFromVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateDataVolumeTemplateFromVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateDiskOfferingAction(inventory.APICreateDiskOfferingMsg):
    def __init__(self):
        super(CreateDiskOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateDiskOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateEcsImageFromEcsSnapshotAction(inventory.APICreateEcsImageFromEcsSnapshotMsg):
    def __init__(self):
        super(CreateEcsImageFromEcsSnapshotAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEcsImageFromEcsSnapshotAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateEcsImageFromLocalImageAction(inventory.APICreateEcsImageFromLocalImageMsg):
    def __init__(self):
        super(CreateEcsImageFromLocalImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEcsImageFromLocalImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateEcsInstanceFromEcsImageAction(inventory.APICreateEcsInstanceFromEcsImageMsg):
    def __init__(self):
        super(CreateEcsInstanceFromEcsImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEcsInstanceFromEcsImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateEcsSecurityGroupRemoteAction(inventory.APICreateEcsSecurityGroupRemoteMsg):
    def __init__(self):
        super(CreateEcsSecurityGroupRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEcsSecurityGroupRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateEcsSecurityGroupRuleRemoteAction(inventory.APICreateEcsSecurityGroupRuleRemoteMsg):
    def __init__(self):
        super(CreateEcsSecurityGroupRuleRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEcsSecurityGroupRuleRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateEcsVSwitchRemoteAction(inventory.APICreateEcsVSwitchRemoteMsg):
    def __init__(self):
        super(CreateEcsVSwitchRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEcsVSwitchRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateEcsVpcRemoteAction(inventory.APICreateEcsVpcRemoteMsg):
    def __init__(self):
        super(CreateEcsVpcRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEcsVpcRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateEipAction(inventory.APICreateEipMsg):
    def __init__(self):
        super(CreateEipAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEipAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateEmailMediaAction(inventory.APICreateEmailMediaMsg):
    def __init__(self):
        super(CreateEmailMediaAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEmailMediaAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateEmailMonitorTriggerActionAction(inventory.APICreateEmailMonitorTriggerActionMsg):
    def __init__(self):
        super(CreateEmailMonitorTriggerActionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEmailMonitorTriggerActionAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateHybridEipAction(inventory.APICreateHybridEipMsg):
    def __init__(self):
        super(CreateHybridEipAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateHybridEipAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateIPsecConnectionAction(inventory.APICreateIPsecConnectionMsg):
    def __init__(self):
        super(CreateIPsecConnectionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateIPsecConnectionAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateInstanceOfferingAction(inventory.APICreateInstanceOfferingMsg):
    def __init__(self):
        super(CreateInstanceOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateInstanceOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateL2NoVlanNetworkAction(inventory.APICreateL2NoVlanNetworkMsg):
    def __init__(self):
        super(CreateL2NoVlanNetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateL2NoVlanNetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateL2VlanNetworkAction(inventory.APICreateL2VlanNetworkMsg):
    def __init__(self):
        super(CreateL2VlanNetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateL2VlanNetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateL2VxlanNetworkAction(inventory.APICreateL2VxlanNetworkMsg):
    def __init__(self):
        super(CreateL2VxlanNetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateL2VxlanNetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateL2VxlanNetworkPoolAction(inventory.APICreateL2VxlanNetworkPoolMsg):
    def __init__(self):
        super(CreateL2VxlanNetworkPoolAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateL2VxlanNetworkPoolAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateL3NetworkAction(inventory.APICreateL3NetworkMsg):
    def __init__(self):
        super(CreateL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateL3NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateLdapBindingAction(inventory.APICreateLdapBindingMsg):
    def __init__(self):
        super(CreateLdapBindingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateLdapBindingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateLoadBalancerAction(inventory.APICreateLoadBalancerMsg):
    def __init__(self):
        super(CreateLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateLoadBalancerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateLoadBalancerListenerAction(inventory.APICreateLoadBalancerListenerMsg):
    def __init__(self):
        super(CreateLoadBalancerListenerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateLoadBalancerListenerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateMessageAction(inventory.APICreateMessage):
    def __init__(self):
        super(CreateMessageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateMessageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateMonitorTriggerAction(inventory.APICreateMonitorTriggerMsg):
    def __init__(self):
        super(CreateMonitorTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateMonitorTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateOSSProtectionSiteAction(inventory.APICreateOSSProtectionSiteMsg):
    def __init__(self):
        super(CreateOSSProtectionSiteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateOSSProtectionSiteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateOssBackupBucketRemoteAction(inventory.APICreateOssBackupBucketRemoteMsg):
    def __init__(self):
        super(CreateOssBackupBucketRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateOssBackupBucketRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateOssBucketRemoteAction(inventory.APICreateOssBucketRemoteMsg):
    def __init__(self):
        super(CreateOssBucketRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateOssBucketRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreatePciDeviceOfferingAction(inventory.APICreatePciDeviceOfferingMsg):
    def __init__(self):
        super(CreatePciDeviceOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreatePciDeviceOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreatePolicyAction(inventory.APICreatePolicyMsg):
    def __init__(self):
        super(CreatePolicyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreatePolicyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreatePortForwardingRuleAction(inventory.APICreatePortForwardingRuleMsg):
    def __init__(self):
        super(CreatePortForwardingRuleAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreatePortForwardingRuleAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateProtectionGatewayAction(inventory.APICreateProtectionGatewayMsg):
    def __init__(self):
        super(CreateProtectionGatewayAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateProtectionGatewayAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateProtectionGroupAction(inventory.APICreateProtectionGroupMsg):
    def __init__(self):
        super(CreateProtectionGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateProtectionGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateProtectionPolicyAction(inventory.APICreateProtectionPolicyMsg):
    def __init__(self):
        super(CreateProtectionPolicyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateProtectionPolicyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateResourcePriceAction(inventory.APICreateResourcePriceMsg):
    def __init__(self):
        super(CreateResourcePriceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateResourcePriceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateRootVolumeTemplateFromRootVolumeAction(inventory.APICreateRootVolumeTemplateFromRootVolumeMsg):
    def __init__(self):
        super(CreateRootVolumeTemplateFromRootVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateRootVolumeTemplateFromRootVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateRootVolumeTemplateFromVolumeSnapshotAction(inventory.APICreateRootVolumeTemplateFromVolumeSnapshotMsg):
    def __init__(self):
        super(CreateRootVolumeTemplateFromVolumeSnapshotAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateRootVolumeTemplateFromVolumeSnapshotAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateRouterInterfacePairRemoteAction(inventory.APICreateRouterInterfacePairRemoteMsg):
    def __init__(self):
        super(CreateRouterInterfacePairRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateRouterInterfacePairRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateSchedulerJobAction(inventory.APICreateSchedulerJobMsg):
    def __init__(self):
        super(CreateSchedulerJobAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateSchedulerJobAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateSchedulerTriggerAction(inventory.APICreateSchedulerTriggerMsg):
    def __init__(self):
        super(CreateSchedulerTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateSchedulerTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateSearchIndexAction(inventory.APICreateSearchIndexMsg):
    def __init__(self):
        super(CreateSearchIndexAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateSearchIndexAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateSecurityGroupAction(inventory.APICreateSecurityGroupMsg):
    def __init__(self):
        super(CreateSecurityGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateSecurityGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateSystemTagAction(inventory.APICreateSystemTagMsg):
    def __init__(self):
        super(CreateSystemTagAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateSystemTagAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateUserAction(inventory.APICreateUserMsg):
    def __init__(self):
        super(CreateUserAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateUserAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateUserGroupAction(inventory.APICreateUserGroupMsg):
    def __init__(self):
        super(CreateUserGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateUserGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateUserTagAction(inventory.APICreateUserTagMsg):
    def __init__(self):
        super(CreateUserTagAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateUserTagAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVRouterRouteTableAction(inventory.APICreateVRouterRouteTableMsg):
    def __init__(self):
        super(CreateVRouterRouteTableAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVRouterRouteTableAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVipAction(inventory.APICreateVipMsg):
    def __init__(self):
        super(CreateVipAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVipAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVirtualRouterOfferingAction(inventory.APICreateVirtualRouterOfferingMsg):
    def __init__(self):
        super(CreateVirtualRouterOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVirtualRouterOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVirtualRouterVmAction(inventory.APICreateVirtualRouterVmMsg):
    def __init__(self):
        super(CreateVirtualRouterVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVirtualRouterVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVmInstanceAction(inventory.APICreateVmInstanceMsg):
    def __init__(self):
        super(CreateVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVniRangeAction(inventory.APICreateVniRangeMsg):
    def __init__(self):
        super(CreateVniRangeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVniRangeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVolumeSnapshotAction(inventory.APICreateVolumeSnapshotMsg):
    def __init__(self):
        super(CreateVolumeSnapshotAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVolumeSnapshotAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVpcUserVpnGatewayRemoteAction(inventory.APICreateVpcUserVpnGatewayRemoteMsg):
    def __init__(self):
        super(CreateVpcUserVpnGatewayRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVpcUserVpnGatewayRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVpcVRouterAction(inventory.APICreateVpcVRouterMsg):
    def __init__(self):
        super(CreateVpcVRouterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVpcVRouterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVpcVpnConnectionRemoteAction(inventory.APICreateVpcVpnConnectionRemoteMsg):
    def __init__(self):
        super(CreateVpcVpnConnectionRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVpcVpnConnectionRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVpnIkeConfigAction(inventory.APICreateVpnIkeConfigMsg):
    def __init__(self):
        super(CreateVpnIkeConfigAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVpnIkeConfigAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateVpnIpsecConfigAction(inventory.APICreateVpnIpsecConfigMsg):
    def __init__(self):
        super(CreateVpnIpsecConfigAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVpnIpsecConfigAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateWebhookAction(inventory.APICreateWebhookMsg):
    def __init__(self):
        super(CreateWebhookAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateWebhookAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateZoneAction(inventory.APICreateZoneMsg):
    def __init__(self):
        super(CreateZoneAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateZoneAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DebugSignalAction(inventory.APIDebugSignalMsg):
    def __init__(self):
        super(DebugSignalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DebugSignalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteAccountAction(inventory.APIDeleteAccountMsg):
    def __init__(self):
        super(DeleteAccountAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteAccountAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteAlertAction(inventory.APIDeleteAlertMsg):
    def __init__(self):
        super(DeleteAlertAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteAlertAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteAliyunDiskFromLocalAction(inventory.APIDeleteAliyunDiskFromLocalMsg):
    def __init__(self):
        super(DeleteAliyunDiskFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteAliyunDiskFromLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteAliyunDiskFromRemoteAction(inventory.APIDeleteAliyunDiskFromRemoteMsg):
    def __init__(self):
        super(DeleteAliyunDiskFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteAliyunDiskFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteAliyunKeySecretAction(inventory.APIDeleteAliyunKeySecretMsg):
    def __init__(self):
        super(DeleteAliyunKeySecretAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteAliyunKeySecretAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteAliyunRouteEntryRemoteAction(inventory.APIDeleteAliyunRouteEntryRemoteMsg):
    def __init__(self):
        super(DeleteAliyunRouteEntryRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteAliyunRouteEntryRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteAliyunSnapshotFromLocalAction(inventory.APIDeleteAliyunSnapshotFromLocalMsg):
    def __init__(self):
        super(DeleteAliyunSnapshotFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteAliyunSnapshotFromLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteAliyunSnapshotFromRemoteAction(inventory.APIDeleteAliyunSnapshotFromRemoteMsg):
    def __init__(self):
        super(DeleteAliyunSnapshotFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteAliyunSnapshotFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteAllEcsInstancesFromDataCenterAction(inventory.APIDeleteAllEcsInstancesFromDataCenterMsg):
    def __init__(self):
        super(DeleteAllEcsInstancesFromDataCenterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteAllEcsInstancesFromDataCenterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteBackupFileInPublicAction(inventory.APIDeleteBackupFileInPublicMsg):
    def __init__(self):
        super(DeleteBackupFileInPublicAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteBackupFileInPublicAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteBackupStorageAction(inventory.APIDeleteBackupStorageMsg):
    def __init__(self):
        super(DeleteBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteBaremetalChassisAction(inventory.APIDeleteBaremetalChassisMsg):
    def __init__(self):
        super(DeleteBaremetalChassisAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteBaremetalChassisAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteBaremetalHostCfgAction(inventory.APIDeleteBaremetalHostCfgMsg):
    def __init__(self):
        super(DeleteBaremetalHostCfgAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteBaremetalHostCfgAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteBaremetalPxeServerAction(inventory.APIDeleteBaremetalPxeServerMsg):
    def __init__(self):
        super(DeleteBaremetalPxeServerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteBaremetalPxeServerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteCephPrimaryStoragePoolAction(inventory.APIDeleteCephPrimaryStoragePoolMsg):
    def __init__(self):
        super(DeleteCephPrimaryStoragePoolAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteCephPrimaryStoragePoolAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteClusterAction(inventory.APIDeleteClusterMsg):
    def __init__(self):
        super(DeleteClusterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteClusterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteConnectionAccessPointLocalAction(inventory.APIDeleteConnectionAccessPointLocalMsg):
    def __init__(self):
        super(DeleteConnectionAccessPointLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteConnectionAccessPointLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteConnectionBetweenL3NetWorkAndAliyunVSwitchAction(inventory.APIDeleteConnectionBetweenL3NetWorkAndAliyunVSwitchMsg):
    def __init__(self):
        super(DeleteConnectionBetweenL3NetWorkAndAliyunVSwitchAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteConnectionBetweenL3NetWorkAndAliyunVSwitchAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteDataCenterInLocalAction(inventory.APIDeleteDataCenterInLocalMsg):
    def __init__(self):
        super(DeleteDataCenterInLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteDataCenterInLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteDataVolumeAction(inventory.APIDeleteDataVolumeMsg):
    def __init__(self):
        super(DeleteDataVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteDataVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteDiskOfferingAction(inventory.APIDeleteDiskOfferingMsg):
    def __init__(self):
        super(DeleteDiskOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteDiskOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsImageLocalAction(inventory.APIDeleteEcsImageLocalMsg):
    def __init__(self):
        super(DeleteEcsImageLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsImageLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsImageRemoteAction(inventory.APIDeleteEcsImageRemoteMsg):
    def __init__(self):
        super(DeleteEcsImageRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsImageRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsInstanceAction(inventory.APIDeleteEcsInstanceMsg):
    def __init__(self):
        super(DeleteEcsInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsInstanceLocalAction(inventory.APIDeleteEcsInstanceLocalMsg):
    def __init__(self):
        super(DeleteEcsInstanceLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsInstanceLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsSecurityGroupInLocalAction(inventory.APIDeleteEcsSecurityGroupInLocalMsg):
    def __init__(self):
        super(DeleteEcsSecurityGroupInLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsSecurityGroupInLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsSecurityGroupRemoteAction(inventory.APIDeleteEcsSecurityGroupRemoteMsg):
    def __init__(self):
        super(DeleteEcsSecurityGroupRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsSecurityGroupRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsSecurityGroupRuleRemoteAction(inventory.APIDeleteEcsSecurityGroupRuleRemoteMsg):
    def __init__(self):
        super(DeleteEcsSecurityGroupRuleRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsSecurityGroupRuleRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsVSwitchInLocalAction(inventory.APIDeleteEcsVSwitchInLocalMsg):
    def __init__(self):
        super(DeleteEcsVSwitchInLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsVSwitchInLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsVSwitchRemoteAction(inventory.APIDeleteEcsVSwitchRemoteMsg):
    def __init__(self):
        super(DeleteEcsVSwitchRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsVSwitchRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsVpcInLocalAction(inventory.APIDeleteEcsVpcInLocalMsg):
    def __init__(self):
        super(DeleteEcsVpcInLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsVpcInLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEcsVpcRemoteAction(inventory.APIDeleteEcsVpcRemoteMsg):
    def __init__(self):
        super(DeleteEcsVpcRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEcsVpcRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteEipAction(inventory.APIDeleteEipMsg):
    def __init__(self):
        super(DeleteEipAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteEipAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteExportedImageFromBackupStorageAction(inventory.APIDeleteExportedImageFromBackupStorageMsg):
    def __init__(self):
        super(DeleteExportedImageFromBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteExportedImageFromBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteGCJobAction(inventory.APIDeleteGCJobMsg):
    def __init__(self):
        super(DeleteGCJobAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteGCJobAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteHostAction(inventory.APIDeleteHostMsg):
    def __init__(self):
        super(DeleteHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteHybridEipFromLocalAction(inventory.APIDeleteHybridEipFromLocalMsg):
    def __init__(self):
        super(DeleteHybridEipFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteHybridEipFromLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteHybridEipRemoteAction(inventory.APIDeleteHybridEipRemoteMsg):
    def __init__(self):
        super(DeleteHybridEipRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteHybridEipRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteIPsecConnectionAction(inventory.APIDeleteIPsecConnectionMsg):
    def __init__(self):
        super(DeleteIPsecConnectionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteIPsecConnectionAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteIdentityZoneInLocalAction(inventory.APIDeleteIdentityZoneInLocalMsg):
    def __init__(self):
        super(DeleteIdentityZoneInLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteIdentityZoneInLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteImageAction(inventory.APIDeleteImageMsg):
    def __init__(self):
        super(DeleteImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteInstanceOfferingAction(inventory.APIDeleteInstanceOfferingMsg):
    def __init__(self):
        super(DeleteInstanceOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteInstanceOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteIpRangeAction(inventory.APIDeleteIpRangeMsg):
    def __init__(self):
        super(DeleteIpRangeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteIpRangeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteL2NetworkAction(inventory.APIDeleteL2NetworkMsg):
    def __init__(self):
        super(DeleteL2NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteL2NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteL3NetworkAction(inventory.APIDeleteL3NetworkMsg):
    def __init__(self):
        super(DeleteL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteL3NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteLdapBindingAction(inventory.APIDeleteLdapBindingMsg):
    def __init__(self):
        super(DeleteLdapBindingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteLdapBindingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteLdapServerAction(inventory.APIDeleteLdapServerMsg):
    def __init__(self):
        super(DeleteLdapServerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteLdapServerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteLoadBalancerAction(inventory.APIDeleteLoadBalancerMsg):
    def __init__(self):
        super(DeleteLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteLoadBalancerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteLoadBalancerListenerAction(inventory.APIDeleteLoadBalancerListenerMsg):
    def __init__(self):
        super(DeleteLoadBalancerListenerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteLoadBalancerListenerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteMediaAction(inventory.APIDeleteMediaMsg):
    def __init__(self):
        super(DeleteMediaAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteMediaAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteMonitorTriggerAction(inventory.APIDeleteMonitorTriggerMsg):
    def __init__(self):
        super(DeleteMonitorTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteMonitorTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteMonitorTriggerActionAction(inventory.APIDeleteMonitorTriggerActionMsg):
    def __init__(self):
        super(DeleteMonitorTriggerActionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteMonitorTriggerActionAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteNicQosAction(inventory.APIDeleteNicQosMsg):
    def __init__(self):
        super(DeleteNicQosAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteNicQosAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteNotificationsAction(inventory.APIDeleteNotificationsMsg):
    def __init__(self):
        super(DeleteNotificationsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteNotificationsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteOssBucketFileRemoteAction(inventory.APIDeleteOssBucketFileRemoteMsg):
    def __init__(self):
        super(DeleteOssBucketFileRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteOssBucketFileRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteOssBucketNameLocalAction(inventory.APIDeleteOssBucketNameLocalMsg):
    def __init__(self):
        super(DeleteOssBucketNameLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteOssBucketNameLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteOssBucketRemoteAction(inventory.APIDeleteOssBucketRemoteMsg):
    def __init__(self):
        super(DeleteOssBucketRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteOssBucketRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeletePciDeviceAction(inventory.APIDeletePciDeviceMsg):
    def __init__(self):
        super(DeletePciDeviceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeletePciDeviceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeletePciDeviceOfferingAction(inventory.APIDeletePciDeviceOfferingMsg):
    def __init__(self):
        super(DeletePciDeviceOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeletePciDeviceOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeletePolicyAction(inventory.APIDeletePolicyMsg):
    def __init__(self):
        super(DeletePolicyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeletePolicyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeletePortForwardingRuleAction(inventory.APIDeletePortForwardingRuleMsg):
    def __init__(self):
        super(DeletePortForwardingRuleAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeletePortForwardingRuleAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeletePrimaryStorageAction(inventory.APIDeletePrimaryStorageMsg):
    def __init__(self):
        super(DeletePrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeletePrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteProtectionGroupAction(inventory.APIDeleteProtectionGroupMsg):
    def __init__(self):
        super(DeleteProtectionGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteProtectionGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteResourcePriceAction(inventory.APIDeleteResourcePriceMsg):
    def __init__(self):
        super(DeleteResourcePriceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteResourcePriceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteRouterInterfaceLocalAction(inventory.APIDeleteRouterInterfaceLocalMsg):
    def __init__(self):
        super(DeleteRouterInterfaceLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteRouterInterfaceLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteRouterInterfaceRemoteAction(inventory.APIDeleteRouterInterfaceRemoteMsg):
    def __init__(self):
        super(DeleteRouterInterfaceRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteRouterInterfaceRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteSchedulerJobAction(inventory.APIDeleteSchedulerJobMsg):
    def __init__(self):
        super(DeleteSchedulerJobAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteSchedulerJobAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteSchedulerTriggerAction(inventory.APIDeleteSchedulerTriggerMsg):
    def __init__(self):
        super(DeleteSchedulerTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteSchedulerTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteSearchIndexAction(inventory.APIDeleteSearchIndexMsg):
    def __init__(self):
        super(DeleteSearchIndexAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteSearchIndexAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteSecurityGroupAction(inventory.APIDeleteSecurityGroupMsg):
    def __init__(self):
        super(DeleteSecurityGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteSecurityGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteSecurityGroupRuleAction(inventory.APIDeleteSecurityGroupRuleMsg):
    def __init__(self):
        super(DeleteSecurityGroupRuleAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteSecurityGroupRuleAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteTagAction(inventory.APIDeleteTagMsg):
    def __init__(self):
        super(DeleteTagAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteTagAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteUserAction(inventory.APIDeleteUserMsg):
    def __init__(self):
        super(DeleteUserAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteUserAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteUserGroupAction(inventory.APIDeleteUserGroupMsg):
    def __init__(self):
        super(DeleteUserGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteUserGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVCenterAction(inventory.APIDeleteVCenterMsg):
    def __init__(self):
        super(DeleteVCenterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVCenterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVRouterRouteEntryAction(inventory.APIDeleteVRouterRouteEntryMsg):
    def __init__(self):
        super(DeleteVRouterRouteEntryAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVRouterRouteEntryAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVRouterRouteTableAction(inventory.APIDeleteVRouterRouteTableMsg):
    def __init__(self):
        super(DeleteVRouterRouteTableAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVRouterRouteTableAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVipAction(inventory.APIDeleteVipMsg):
    def __init__(self):
        super(DeleteVipAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVipAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVipQosAction(inventory.APIDeleteVipQosMsg):
    def __init__(self):
        super(DeleteVipQosAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVipQosAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVirtualBorderRouterLocalAction(inventory.APIDeleteVirtualBorderRouterLocalMsg):
    def __init__(self):
        super(DeleteVirtualBorderRouterLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVirtualBorderRouterLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVirtualRouterLocalAction(inventory.APIDeleteVirtualRouterLocalMsg):
    def __init__(self):
        super(DeleteVirtualRouterLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVirtualRouterLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVmConsolePasswordAction(inventory.APIDeleteVmConsolePasswordMsg):
    def __init__(self):
        super(DeleteVmConsolePasswordAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVmConsolePasswordAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVmHostnameAction(inventory.APIDeleteVmHostnameMsg):
    def __init__(self):
        super(DeleteVmHostnameAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVmHostnameAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVmInstanceHaLevelAction(inventory.APIDeleteVmInstanceHaLevelMsg):
    def __init__(self):
        super(DeleteVmInstanceHaLevelAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVmInstanceHaLevelAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVmNicFromSecurityGroupAction(inventory.APIDeleteVmNicFromSecurityGroupMsg):
    def __init__(self):
        super(DeleteVmNicFromSecurityGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVmNicFromSecurityGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVmSshKeyAction(inventory.APIDeleteVmSshKeyMsg):
    def __init__(self):
        super(DeleteVmSshKeyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVmSshKeyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVmStaticIpAction(inventory.APIDeleteVmStaticIpMsg):
    def __init__(self):
        super(DeleteVmStaticIpAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVmStaticIpAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVniRangeAction(inventory.APIDeleteVniRangeMsg):
    def __init__(self):
        super(DeleteVniRangeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVniRangeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVolumeQosAction(inventory.APIDeleteVolumeQosMsg):
    def __init__(self):
        super(DeleteVolumeQosAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVolumeQosAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVolumeSnapshotAction(inventory.APIDeleteVolumeSnapshotMsg):
    def __init__(self):
        super(DeleteVolumeSnapshotAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVolumeSnapshotAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVolumeSnapshotFromBackupStorageAction(inventory.APIDeleteVolumeSnapshotFromBackupStorageMsg):
    def __init__(self):
        super(DeleteVolumeSnapshotFromBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVolumeSnapshotFromBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVpcIkeConfigLocalAction(inventory.APIDeleteVpcIkeConfigLocalMsg):
    def __init__(self):
        super(DeleteVpcIkeConfigLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVpcIkeConfigLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVpcIpSecConfigLocalAction(inventory.APIDeleteVpcIpSecConfigLocalMsg):
    def __init__(self):
        super(DeleteVpcIpSecConfigLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVpcIpSecConfigLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVpcUserVpnGatewayLocalAction(inventory.APIDeleteVpcUserVpnGatewayLocalMsg):
    def __init__(self):
        super(DeleteVpcUserVpnGatewayLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVpcUserVpnGatewayLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVpcUserVpnGatewayRemoteAction(inventory.APIDeleteVpcUserVpnGatewayRemoteMsg):
    def __init__(self):
        super(DeleteVpcUserVpnGatewayRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVpcUserVpnGatewayRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVpcVpnConnectionLocalAction(inventory.APIDeleteVpcVpnConnectionLocalMsg):
    def __init__(self):
        super(DeleteVpcVpnConnectionLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVpcVpnConnectionLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVpcVpnConnectionRemoteAction(inventory.APIDeleteVpcVpnConnectionRemoteMsg):
    def __init__(self):
        super(DeleteVpcVpnConnectionRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVpcVpnConnectionRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteVpcVpnGatewayLocalAction(inventory.APIDeleteVpcVpnGatewayLocalMsg):
    def __init__(self):
        super(DeleteVpcVpnGatewayLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteVpcVpnGatewayLocalAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteWebhookAction(inventory.APIDeleteWebhookMsg):
    def __init__(self):
        super(DeleteWebhookAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteWebhookAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DeleteZoneAction(inventory.APIDeleteZoneMsg):
    def __init__(self):
        super(DeleteZoneAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteZoneAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DestroyVmInstanceAction(inventory.APIDestroyVmInstanceMsg):
    def __init__(self):
        super(DestroyVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DestroyVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachAliyunDiskFromEcsAction(inventory.APIDetachAliyunDiskFromEcsMsg):
    def __init__(self):
        super(DetachAliyunDiskFromEcsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachAliyunDiskFromEcsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachAliyunKeyAction(inventory.APIDetachAliyunKeyMsg):
    def __init__(self):
        super(DetachAliyunKeyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachAliyunKeyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachBackupStorageFromZoneAction(inventory.APIDetachBackupStorageFromZoneMsg):
    def __init__(self):
        super(DetachBackupStorageFromZoneAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachBackupStorageFromZoneAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachDataVolumeFromVmAction(inventory.APIDetachDataVolumeFromVmMsg):
    def __init__(self):
        super(DetachDataVolumeFromVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachDataVolumeFromVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachEipAction(inventory.APIDetachEipMsg):
    def __init__(self):
        super(DetachEipAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachEipAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachHybridEipFromEcsAction(inventory.APIDetachHybridEipFromEcsMsg):
    def __init__(self):
        super(DetachHybridEipFromEcsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachHybridEipFromEcsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachIsoFromVmInstanceAction(inventory.APIDetachIsoFromVmInstanceMsg):
    def __init__(self):
        super(DetachIsoFromVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachIsoFromVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachL2NetworkFromClusterAction(inventory.APIDetachL2NetworkFromClusterMsg):
    def __init__(self):
        super(DetachL2NetworkFromClusterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachL2NetworkFromClusterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachL3NetworkFromVmAction(inventory.APIDetachL3NetworkFromVmMsg):
    def __init__(self):
        super(DetachL3NetworkFromVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachL3NetworkFromVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachMonitorTriggerActionFromTriggerAction(inventory.APIDetachMonitorTriggerActionFromTriggerMsg):
    def __init__(self):
        super(DetachMonitorTriggerActionFromTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachMonitorTriggerActionFromTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachNetworkServiceFromL3NetworkAction(inventory.APIDetachNetworkServiceFromL3NetworkMsg):
    def __init__(self):
        super(DetachNetworkServiceFromL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachNetworkServiceFromL3NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachNetworkServiceProviderFromL2NetworkAction(inventory.APIDetachNetworkServiceProviderFromL2NetworkMsg):
    def __init__(self):
        super(DetachNetworkServiceProviderFromL2NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachNetworkServiceProviderFromL2NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachOssBucketFromEcsDataCenterAction(inventory.APIDetachOssBucketFromEcsDataCenterMsg):
    def __init__(self):
        super(DetachOssBucketFromEcsDataCenterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachOssBucketFromEcsDataCenterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachPciDeviceFromVmAction(inventory.APIDetachPciDeviceFromVmMsg):
    def __init__(self):
        super(DetachPciDeviceFromVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachPciDeviceFromVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachPoliciesFromUserAction(inventory.APIDetachPoliciesFromUserMsg):
    def __init__(self):
        super(DetachPoliciesFromUserAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachPoliciesFromUserAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachPolicyFromUserAction(inventory.APIDetachPolicyFromUserMsg):
    def __init__(self):
        super(DetachPolicyFromUserAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachPolicyFromUserAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachPolicyFromUserGroupAction(inventory.APIDetachPolicyFromUserGroupMsg):
    def __init__(self):
        super(DetachPolicyFromUserGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachPolicyFromUserGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachPortForwardingRuleAction(inventory.APIDetachPortForwardingRuleMsg):
    def __init__(self):
        super(DetachPortForwardingRuleAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachPortForwardingRuleAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachPrimaryStorageFromClusterAction(inventory.APIDetachPrimaryStorageFromClusterMsg):
    def __init__(self):
        super(DetachPrimaryStorageFromClusterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachPrimaryStorageFromClusterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachSecurityGroupFromL3NetworkAction(inventory.APIDetachSecurityGroupFromL3NetworkMsg):
    def __init__(self):
        super(DetachSecurityGroupFromL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachSecurityGroupFromL3NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachUsbDeviceFromVmAction(inventory.APIDetachUsbDeviceFromVmMsg):
    def __init__(self):
        super(DetachUsbDeviceFromVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachUsbDeviceFromVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DetachVRouterRouteTableFromVRouterAction(inventory.APIDetachVRouterRouteTableFromVRouterMsg):
    def __init__(self):
        super(DetachVRouterRouteTableFromVRouterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachVRouterRouteTableFromVRouterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class DownloadBackupFileFromPublicCloudAction(inventory.APIDownloadBackupFileFromPublicCloudMsg):
    def __init__(self):
        super(DownloadBackupFileFromPublicCloudAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DownloadBackupFileFromPublicCloudAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ExportImageFromBackupStorageAction(inventory.APIExportImageFromBackupStorageMsg):
    def __init__(self):
        super(ExportImageFromBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ExportImageFromBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ExpungeDataVolumeAction(inventory.APIExpungeDataVolumeMsg):
    def __init__(self):
        super(ExpungeDataVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ExpungeDataVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ExpungeImageAction(inventory.APIExpungeImageMsg):
    def __init__(self):
        super(ExpungeImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ExpungeImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ExpungeVmInstanceAction(inventory.APIExpungeVmInstanceMsg):
    def __init__(self):
        super(ExpungeVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ExpungeVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GCAliyunSnapshotRemoteAction(inventory.APIGCAliyunSnapshotRemoteMsg):
    def __init__(self):
        super(GCAliyunSnapshotRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GCAliyunSnapshotRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GenerateApiJsonTemplateAction(inventory.APIGenerateApiJsonTemplateMsg):
    def __init__(self):
        super(GenerateApiJsonTemplateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GenerateApiJsonTemplateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GenerateApiTypeScriptDefinitionAction(inventory.APIGenerateApiTypeScriptDefinitionMsg):
    def __init__(self):
        super(GenerateApiTypeScriptDefinitionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GenerateApiTypeScriptDefinitionAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GenerateGroovyClassAction(inventory.APIGenerateGroovyClassMsg):
    def __init__(self):
        super(GenerateGroovyClassAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GenerateGroovyClassAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GenerateInventoryQueryDetailsAction(inventory.APIGenerateInventoryQueryDetailsMsg):
    def __init__(self):
        super(GenerateInventoryQueryDetailsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GenerateInventoryQueryDetailsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GenerateQueryableFieldsAction(inventory.APIGenerateQueryableFieldsMsg):
    def __init__(self):
        super(GenerateQueryableFieldsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GenerateQueryableFieldsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GenerateSqlForeignKeyAction(inventory.APIGenerateSqlForeignKeyMsg):
    def __init__(self):
        super(GenerateSqlForeignKeyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GenerateSqlForeignKeyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GenerateSqlIndexAction(inventory.APIGenerateSqlIndexMsg):
    def __init__(self):
        super(GenerateSqlIndexAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GenerateSqlIndexAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GenerateSqlVOViewAction(inventory.APIGenerateSqlVOViewMsg):
    def __init__(self):
        super(GenerateSqlVOViewAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GenerateSqlVOViewAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GenerateTestLinkDocumentAction(inventory.APIGenerateTestLinkDocumentMsg):
    def __init__(self):
        super(GenerateTestLinkDocumentAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GenerateTestLinkDocumentAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetAccountQuotaUsageAction(inventory.APIGetAccountQuotaUsageMsg):
    def __init__(self):
        super(GetAccountQuotaUsageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetAccountQuotaUsageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetAttachablePublicL3ForVRouterAction(inventory.APIGetAttachablePublicL3ForVRouterMsg):
    def __init__(self):
        super(GetAttachablePublicL3ForVRouterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetAttachablePublicL3ForVRouterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetAvailableTriggersAction(inventory.APIGetAvailableTriggersMsg):
    def __init__(self):
        super(GetAvailableTriggersAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetAvailableTriggersAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetBackupStorageCandidatesForImageMigrationAction(inventory.APIGetBackupStorageCandidatesForImageMigrationMsg):
    def __init__(self):
        super(GetBackupStorageCandidatesForImageMigrationAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetBackupStorageCandidatesForImageMigrationAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetBackupStorageCapacityAction(inventory.APIGetBackupStorageCapacityMsg):
    def __init__(self):
        super(GetBackupStorageCapacityAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetBackupStorageCapacityAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetBackupStorageTypesAction(inventory.APIGetBackupStorageTypesMsg):
    def __init__(self):
        super(GetBackupStorageTypesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetBackupStorageTypesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetCandidateBackupStorageForCreatingImageAction(inventory.APIGetCandidateBackupStorageForCreatingImageMsg):
    def __init__(self):
        super(GetCandidateBackupStorageForCreatingImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetCandidateBackupStorageForCreatingImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetCandidateIsoForAttachingVmAction(inventory.APIGetCandidateIsoForAttachingVmMsg):
    def __init__(self):
        super(GetCandidateIsoForAttachingVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetCandidateIsoForAttachingVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetCandidatePrimaryStoragesForCreatingVmAction(inventory.APIGetCandidatePrimaryStoragesForCreatingVmMsg):
    def __init__(self):
        super(GetCandidatePrimaryStoragesForCreatingVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetCandidatePrimaryStoragesForCreatingVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetCandidateVmForAttachingIsoAction(inventory.APIGetCandidateVmForAttachingIsoMsg):
    def __init__(self):
        super(GetCandidateVmForAttachingIsoAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetCandidateVmForAttachingIsoAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetCandidateVmNicForSecurityGroupAction(inventory.APIGetCandidateVmNicForSecurityGroupMsg):
    def __init__(self):
        super(GetCandidateVmNicForSecurityGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetCandidateVmNicForSecurityGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetCandidateVmNicsForLoadBalancerAction(inventory.APIGetCandidateVmNicsForLoadBalancerMsg):
    def __init__(self):
        super(GetCandidateVmNicsForLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetCandidateVmNicsForLoadBalancerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetCandidateZonesClustersHostsForCreatingVmAction(inventory.APIGetCandidateZonesClustersHostsForCreatingVmMsg):
    def __init__(self):
        super(GetCandidateZonesClustersHostsForCreatingVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetCandidateZonesClustersHostsForCreatingVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetConnectionAccessPointFromRemoteAction(inventory.APIGetConnectionAccessPointFromRemoteMsg):
    def __init__(self):
        super(GetConnectionAccessPointFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetConnectionAccessPointFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetConnectionBetweenL3NetworkAndAliyunVSwitchAction(inventory.APIGetConnectionBetweenL3NetworkAndAliyunVSwitchMsg):
    def __init__(self):
        super(GetConnectionBetweenL3NetworkAndAliyunVSwitchAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetConnectionBetweenL3NetworkAndAliyunVSwitchAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetCpuMemoryCapacityAction(inventory.APIGetCpuMemoryCapacityMsg):
    def __init__(self):
        super(GetCpuMemoryCapacityAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetCpuMemoryCapacityAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetCreateEcsImageProgressAction(inventory.APIGetCreateEcsImageProgressMsg):
    def __init__(self):
        super(GetCreateEcsImageProgressAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetCreateEcsImageProgressAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetCurrentTimeAction(inventory.APIGetCurrentTimeMsg):
    def __init__(self):
        super(GetCurrentTimeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetCurrentTimeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetDataCenterFromRemoteAction(inventory.APIGetDataCenterFromRemoteMsg):
    def __init__(self):
        super(GetDataCenterFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetDataCenterFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetDataVolumeAttachableVmAction(inventory.APIGetDataVolumeAttachableVmMsg):
    def __init__(self):
        super(GetDataVolumeAttachableVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetDataVolumeAttachableVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetEcsInstanceTypeAction(inventory.APIGetEcsInstanceTypeMsg):
    def __init__(self):
        super(GetEcsInstanceTypeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetEcsInstanceTypeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetEcsInstanceVncUrlAction(inventory.APIGetEcsInstanceVncUrlMsg):
    def __init__(self):
        super(GetEcsInstanceVncUrlAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetEcsInstanceVncUrlAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetEipAttachableVmNicsAction(inventory.APIGetEipAttachableVmNicsMsg):
    def __init__(self):
        super(GetEipAttachableVmNicsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetEipAttachableVmNicsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetFreeIpAction(inventory.APIGetFreeIpMsg):
    def __init__(self):
        super(GetFreeIpAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetFreeIpAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetGlobalConfigAction(inventory.APIGetGlobalConfigMsg):
    def __init__(self):
        super(GetGlobalConfigAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetGlobalConfigAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetGlobalPropertyAction(inventory.APIGetGlobalPropertyMsg):
    def __init__(self):
        super(GetGlobalPropertyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetGlobalPropertyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetHostAllocatorStrategiesAction(inventory.APIGetHostAllocatorStrategiesMsg):
    def __init__(self):
        super(GetHostAllocatorStrategiesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetHostAllocatorStrategiesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetHostIommuStateAction(inventory.APIGetHostIommuStateMsg):
    def __init__(self):
        super(GetHostIommuStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetHostIommuStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetHostIommuStatusAction(inventory.APIGetHostIommuStatusMsg):
    def __init__(self):
        super(GetHostIommuStatusAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetHostIommuStatusAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetHypervisorTypesAction(inventory.APIGetHypervisorTypesMsg):
    def __init__(self):
        super(GetHypervisorTypesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetHypervisorTypesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetIdentityZoneFromRemoteAction(inventory.APIGetIdentityZoneFromRemoteMsg):
    def __init__(self):
        super(GetIdentityZoneFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetIdentityZoneFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetImageQgaAction(inventory.APIGetImageQgaMsg):
    def __init__(self):
        super(GetImageQgaAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetImageQgaAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetImagesFromImageStoreBackupStorageAction(inventory.APIGetImagesFromImageStoreBackupStorageMsg):
    def __init__(self):
        super(GetImagesFromImageStoreBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetImagesFromImageStoreBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetInterdependentL3NetworksImagesAction(inventory.APIGetInterdependentL3NetworksImagesMsg):
    def __init__(self):
        super(GetInterdependentL3NetworksImagesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetInterdependentL3NetworksImagesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetIpAddressCapacityAction(inventory.APIGetIpAddressCapacityMsg):
    def __init__(self):
        super(GetIpAddressCapacityAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetIpAddressCapacityAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetL2NetworkTypesAction(inventory.APIGetL2NetworkTypesMsg):
    def __init__(self):
        super(GetL2NetworkTypesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetL2NetworkTypesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetL3NetworkDhcpIpAddressAction(inventory.APIGetL3NetworkDhcpIpAddressMsg):
    def __init__(self):
        super(GetL3NetworkDhcpIpAddressAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetL3NetworkDhcpIpAddressAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetL3NetworkMtuAction(inventory.APIGetL3NetworkMtuMsg):
    def __init__(self):
        super(GetL3NetworkMtuAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetL3NetworkMtuAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetL3NetworkRouterInterfaceIpAction(inventory.APIGetL3NetworkRouterInterfaceIpMsg):
    def __init__(self):
        super(GetL3NetworkRouterInterfaceIpAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetL3NetworkRouterInterfaceIpAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetL3NetworkTypesAction(inventory.APIGetL3NetworkTypesMsg):
    def __init__(self):
        super(GetL3NetworkTypesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetL3NetworkTypesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetLicenseCapabilitiesAction(inventory.APIGetLicenseCapabilitiesMsg):
    def __init__(self):
        super(GetLicenseCapabilitiesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetLicenseCapabilitiesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetLicenseInfoAction(inventory.APIGetLicenseInfoMsg):
    def __init__(self):
        super(GetLicenseInfoAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetLicenseInfoAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetLocalStorageHostDiskCapacityAction(inventory.APIGetLocalStorageHostDiskCapacityMsg):
    def __init__(self):
        super(GetLocalStorageHostDiskCapacityAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetLocalStorageHostDiskCapacityAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetMonitorItemAction(inventory.APIGetMonitorItemMsg):
    def __init__(self):
        super(GetMonitorItemAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetMonitorItemAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetNetworkServiceTypesAction(inventory.APIGetNetworkServiceTypesMsg):
    def __init__(self):
        super(GetNetworkServiceTypesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetNetworkServiceTypesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetNicQosAction(inventory.APIGetNicQosMsg):
    def __init__(self):
        super(GetNicQosAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetNicQosAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetOssBackupBucketFromRemoteAction(inventory.APIGetOssBackupBucketFromRemoteMsg):
    def __init__(self):
        super(GetOssBackupBucketFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetOssBackupBucketFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetOssBucketFileFromRemoteAction(inventory.APIGetOssBucketFileFromRemoteMsg):
    def __init__(self):
        super(GetOssBucketFileFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetOssBucketFileFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetOssBucketNameFromRemoteAction(inventory.APIGetOssBucketNameFromRemoteMsg):
    def __init__(self):
        super(GetOssBucketNameFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetOssBucketNameFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetPciDeviceCandidatesForAttachingVmAction(inventory.APIGetPciDeviceCandidatesForAttachingVmMsg):
    def __init__(self):
        super(GetPciDeviceCandidatesForAttachingVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetPciDeviceCandidatesForAttachingVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetPortForwardingAttachableVmNicsAction(inventory.APIGetPortForwardingAttachableVmNicsMsg):
    def __init__(self):
        super(GetPortForwardingAttachableVmNicsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetPortForwardingAttachableVmNicsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetPrimaryStorageAllocatorStrategiesAction(inventory.APIGetPrimaryStorageAllocatorStrategiesMsg):
    def __init__(self):
        super(GetPrimaryStorageAllocatorStrategiesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetPrimaryStorageAllocatorStrategiesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetPrimaryStorageCandidatesForVolumeMigrationAction(inventory.APIGetPrimaryStorageCandidatesForVolumeMigrationMsg):
    def __init__(self):
        super(GetPrimaryStorageCandidatesForVolumeMigrationAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetPrimaryStorageCandidatesForVolumeMigrationAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetPrimaryStorageCapacityAction(inventory.APIGetPrimaryStorageCapacityMsg):
    def __init__(self):
        super(GetPrimaryStorageCapacityAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetPrimaryStorageCapacityAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetPrimaryStorageTypesAction(inventory.APIGetPrimaryStorageTypesMsg):
    def __init__(self):
        super(GetPrimaryStorageTypesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetPrimaryStorageTypesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetProtectionGatewaysAction(inventory.APIGetProtectionGatewaysMsg):
    def __init__(self):
        super(GetProtectionGatewaysAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetProtectionGatewaysAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetProtectionGroupsAction(inventory.APIGetProtectionGroupsMsg):
    def __init__(self):
        super(GetProtectionGroupsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetProtectionGroupsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetProtectionHostsAction(inventory.APIGetProtectionHostsMsg):
    def __init__(self):
        super(GetProtectionHostsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetProtectionHostsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetProtectionPoliciesAction(inventory.APIGetProtectionPoliciesMsg):
    def __init__(self):
        super(GetProtectionPoliciesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetProtectionPoliciesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetProtectionPoolsAction(inventory.APIGetProtectionPoolsMsg):
    def __init__(self):
        super(GetProtectionPoolsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetProtectionPoolsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetProtectionSitesAction(inventory.APIGetProtectionSitesMsg):
    def __init__(self):
        super(GetProtectionSitesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetProtectionSitesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetProtectionVolumesAction(inventory.APIGetProtectionVolumesMsg):
    def __init__(self):
        super(GetProtectionVolumesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetProtectionVolumesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetResourceAccountAction(inventory.APIGetResourceAccountMsg):
    def __init__(self):
        super(GetResourceAccountAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetResourceAccountAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetResourceNamesAction(inventory.APIGetResourceNamesMsg):
    def __init__(self):
        super(GetResourceNamesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetResourceNamesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetTaskProgressAction(inventory.APIGetTaskProgressMsg):
    def __init__(self):
        super(GetTaskProgressAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetTaskProgressAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetUsbDeviceCandidatesForAttachingVmAction(inventory.APIGetUsbDeviceCandidatesForAttachingVmMsg):
    def __init__(self):
        super(GetUsbDeviceCandidatesForAttachingVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetUsbDeviceCandidatesForAttachingVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVCenterDVSwitchesAction(inventory.APIGetVCenterDVSwitchesMsg):
    def __init__(self):
        super(GetVCenterDVSwitchesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVCenterDVSwitchesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVRouterRouteTableAction(inventory.APIGetVRouterRouteTableMsg):
    def __init__(self):
        super(GetVRouterRouteTableAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVRouterRouteTableAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVersionAction(inventory.APIGetVersionMsg):
    def __init__(self):
        super(GetVersionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVersionAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVipQosAction(inventory.APIGetVipQosMsg):
    def __init__(self):
        super(GetVipQosAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVipQosAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVipUsedPortsAction(inventory.APIGetVipUsedPortsMsg):
    def __init__(self):
        super(GetVipUsedPortsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVipUsedPortsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmAttachableDataVolumeAction(inventory.APIGetVmAttachableDataVolumeMsg):
    def __init__(self):
        super(GetVmAttachableDataVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmAttachableDataVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmAttachableL3NetworkAction(inventory.APIGetVmAttachableL3NetworkMsg):
    def __init__(self):
        super(GetVmAttachableL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmAttachableL3NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmBootOrderAction(inventory.APIGetVmBootOrderMsg):
    def __init__(self):
        super(GetVmBootOrderAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmBootOrderAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmCapabilitiesAction(inventory.APIGetVmCapabilitiesMsg):
    def __init__(self):
        super(GetVmCapabilitiesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmCapabilitiesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmConsoleAddressAction(inventory.APIGetVmConsoleAddressMsg):
    def __init__(self):
        super(GetVmConsoleAddressAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmConsoleAddressAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmConsolePasswordAction(inventory.APIGetVmConsolePasswordMsg):
    def __init__(self):
        super(GetVmConsolePasswordAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmConsolePasswordAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmHostnameAction(inventory.APIGetVmHostnameMsg):
    def __init__(self):
        super(GetVmHostnameAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmHostnameAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmInstanceHaLevelAction(inventory.APIGetVmInstanceHaLevelMsg):
    def __init__(self):
        super(GetVmInstanceHaLevelAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmInstanceHaLevelAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmMigrationCandidateHostsAction(inventory.APIGetVmMigrationCandidateHostsMsg):
    def __init__(self):
        super(GetVmMigrationCandidateHostsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmMigrationCandidateHostsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmMonitorNumberAction(inventory.APIGetVmMonitorNumberMsg):
    def __init__(self):
        super(GetVmMonitorNumberAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmMonitorNumberAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmQgaAction(inventory.APIGetVmQgaMsg):
    def __init__(self):
        super(GetVmQgaAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmQgaAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmRDPAction(inventory.APIGetVmRDPMsg):
    def __init__(self):
        super(GetVmRDPAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmRDPAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmSshKeyAction(inventory.APIGetVmSshKeyMsg):
    def __init__(self):
        super(GetVmSshKeyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmSshKeyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmStartingCandidateClustersHostsAction(inventory.APIGetVmStartingCandidateClustersHostsMsg):
    def __init__(self):
        super(GetVmStartingCandidateClustersHostsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmStartingCandidateClustersHostsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVmUsbRedirectAction(inventory.APIGetVmUsbRedirectMsg):
    def __init__(self):
        super(GetVmUsbRedirectAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmUsbRedirectAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVolumeCapabilitiesAction(inventory.APIGetVolumeCapabilitiesMsg):
    def __init__(self):
        super(GetVolumeCapabilitiesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVolumeCapabilitiesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVolumeFormatAction(inventory.APIGetVolumeFormatMsg):
    def __init__(self):
        super(GetVolumeFormatAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVolumeFormatAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVolumeQosAction(inventory.APIGetVolumeQosMsg):
    def __init__(self):
        super(GetVolumeQosAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVolumeQosAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVolumeSnapshotTreeAction(inventory.APIGetVolumeSnapshotTreeMsg):
    def __init__(self):
        super(GetVolumeSnapshotTreeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVolumeSnapshotTreeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetVpcVpnConfigurationFromRemoteAction(inventory.APIGetVpcVpnConfigurationFromRemoteMsg):
    def __init__(self):
        super(GetVpcVpnConfigurationFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVpcVpnConfigurationFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class GetZoneAction(inventory.APIGetZoneMsg):
    def __init__(self):
        super(GetZoneAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetZoneAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class IsOpensourceVersionAction(inventory.APIIsOpensourceVersionMsg):
    def __init__(self):
        super(IsOpensourceVersionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[IsOpensourceVersionAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class IsReadyToGoAction(inventory.APIIsReadyToGoMsg):
    def __init__(self):
        super(IsReadyToGoAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[IsReadyToGoAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class KvmRunShellAction(inventory.APIKvmRunShellMsg):
    def __init__(self):
        super(KvmRunShellAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[KvmRunShellAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class LocalStorageGetVolumeMigratableHostsAction(inventory.APILocalStorageGetVolumeMigratableHostsMsg):
    def __init__(self):
        super(LocalStorageGetVolumeMigratableHostsAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[LocalStorageGetVolumeMigratableHostsAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class LocalStorageMigrateVolumeAction(inventory.APILocalStorageMigrateVolumeMsg):
    def __init__(self):
        super(LocalStorageMigrateVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[LocalStorageMigrateVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class LogInByAccountAction(inventory.APILogInByAccountMsg):
    def __init__(self):
        super(LogInByAccountAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class LogInByLdapAction(inventory.APILogInByLdapMsg):
    def __init__(self):
        super(LogInByLdapAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class LogInByUserAction(inventory.APILogInByUserMsg):
    def __init__(self):
        super(LogInByUserAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class LogOutAction(inventory.APILogOutMsg):
    def __init__(self):
        super(LogOutAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class MigrateVmAction(inventory.APIMigrateVmMsg):
    def __init__(self):
        super(MigrateVmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[MigrateVmAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class PauseVmInstanceAction(inventory.APIPauseVmInstanceMsg):
    def __init__(self):
        super(PauseVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[PauseVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class PowerOffBaremetalHostAction(inventory.APIPowerOffBaremetalHostMsg):
    def __init__(self):
        super(PowerOffBaremetalHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[PowerOffBaremetalHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class PowerOnBaremetalHostAction(inventory.APIPowerOnBaremetalHostMsg):
    def __init__(self):
        super(PowerOnBaremetalHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[PowerOnBaremetalHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class PowerResetBaremetalHostAction(inventory.APIPowerResetBaremetalHostMsg):
    def __init__(self):
        super(PowerResetBaremetalHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[PowerResetBaremetalHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class PowerStatusBaremetalHostAction(inventory.APIPowerStatusBaremetalHostMsg):
    def __init__(self):
        super(PowerStatusBaremetalHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[PowerStatusBaremetalHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class PrimaryStorageMigrateVolumeAction(inventory.APIPrimaryStorageMigrateVolumeMsg):
    def __init__(self):
        super(PrimaryStorageMigrateVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[PrimaryStorageMigrateVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class PrometheusQueryLabelValuesAction(inventory.APIPrometheusQueryLabelValuesMsg):
    def __init__(self):
        super(PrometheusQueryLabelValuesAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[PrometheusQueryLabelValuesAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class PrometheusQueryMetadataAction(inventory.APIPrometheusQueryMetadataMsg):
    def __init__(self):
        super(PrometheusQueryMetadataAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[PrometheusQueryMetadataAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class PrometheusQueryPassThroughAction(inventory.APIPrometheusQueryPassThroughMsg):
    def __init__(self):
        super(PrometheusQueryPassThroughAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[PrometheusQueryPassThroughAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class PrometheusQueryVmMonitoringDataAction(inventory.APIPrometheusQueryVmMonitoringDataMsg):
    def __init__(self):
        super(PrometheusQueryVmMonitoringDataAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[PrometheusQueryVmMonitoringDataAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ProvisionBaremetalHostAction(inventory.APIProvisionBaremetalHostMsg):
    def __init__(self):
        super(ProvisionBaremetalHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ProvisionBaremetalHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class QueryAccountAction(inventory.APIQueryAccountMsg):
    def __init__(self):
        super(QueryAccountAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryAccountAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryAccountResourceRefAction(inventory.APIQueryAccountResourceRefMsg):
    def __init__(self):
        super(QueryAccountResourceRefAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryAccountResourceRefAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryAlertAction(inventory.APIQueryAlertMsg):
    def __init__(self):
        super(QueryAlertAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryAlertAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryAliyunDiskFromLocalAction(inventory.APIQueryAliyunDiskFromLocalMsg):
    def __init__(self):
        super(QueryAliyunDiskFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryAliyunDiskFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryAliyunKeySecretAction(inventory.APIQueryAliyunKeySecretMsg):
    def __init__(self):
        super(QueryAliyunKeySecretAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryAliyunKeySecretAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryAliyunRouteEntryFromLocalAction(inventory.APIQueryAliyunRouteEntryFromLocalMsg):
    def __init__(self):
        super(QueryAliyunRouteEntryFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryAliyunRouteEntryFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryAliyunSnapshotFromLocalAction(inventory.APIQueryAliyunSnapshotFromLocalMsg):
    def __init__(self):
        super(QueryAliyunSnapshotFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryAliyunSnapshotFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryAliyunVirtualRouterFromLocalAction(inventory.APIQueryAliyunVirtualRouterFromLocalMsg):
    def __init__(self):
        super(QueryAliyunVirtualRouterFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryAliyunVirtualRouterFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryApplianceVmAction(inventory.APIQueryApplianceVmMsg):
    def __init__(self):
        super(QueryApplianceVmAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryApplianceVmAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryBackupStorageAction(inventory.APIQueryBackupStorageMsg):
    def __init__(self):
        super(QueryBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryBackupStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryBaremetalChassisAction(inventory.APIQueryBaremetalChassisMsg):
    def __init__(self):
        super(QueryBaremetalChassisAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryBaremetalChassisAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryBaremetalHardwareInfoAction(inventory.APIQueryBaremetalHardwareInfoMsg):
    def __init__(self):
        super(QueryBaremetalHardwareInfoAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryBaremetalHardwareInfoAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryBaremetalHostCfgAction(inventory.APIQueryBaremetalHostCfgMsg):
    def __init__(self):
        super(QueryBaremetalHostCfgAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryBaremetalHostCfgAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryBaremetalPxeServerAction(inventory.APIQueryBaremetalPxeServerMsg):
    def __init__(self):
        super(QueryBaremetalPxeServerAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryBaremetalPxeServerAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryCephBackupStorageAction(inventory.APIQueryCephBackupStorageMsg):
    def __init__(self):
        super(QueryCephBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryCephBackupStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryCephPrimaryStorageAction(inventory.APIQueryCephPrimaryStorageMsg):
    def __init__(self):
        super(QueryCephPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryCephPrimaryStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryCephPrimaryStoragePoolAction(inventory.APIQueryCephPrimaryStoragePoolMsg):
    def __init__(self):
        super(QueryCephPrimaryStoragePoolAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryCephPrimaryStoragePoolAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryClusterAction(inventory.APIQueryClusterMsg):
    def __init__(self):
        super(QueryClusterAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryClusterAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryConnectionAccessPointFromLocalAction(inventory.APIQueryConnectionAccessPointFromLocalMsg):
    def __init__(self):
        super(QueryConnectionAccessPointFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryConnectionAccessPointFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryConnectionBetweenL3NetworkAndAliyunVSwitchAction(inventory.APIQueryConnectionBetweenL3NetworkAndAliyunVSwitchMsg):
    def __init__(self):
        super(QueryConnectionBetweenL3NetworkAndAliyunVSwitchAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryConnectionBetweenL3NetworkAndAliyunVSwitchAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryConsoleProxyAgentAction(inventory.APIQueryConsoleProxyAgentMsg):
    def __init__(self):
        super(QueryConsoleProxyAgentAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryConsoleProxyAgentAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryDataCenterFromLocalAction(inventory.APIQueryDataCenterFromLocalMsg):
    def __init__(self):
        super(QueryDataCenterFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryDataCenterFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryDiskOfferingAction(inventory.APIQueryDiskOfferingMsg):
    def __init__(self):
        super(QueryDiskOfferingAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryDiskOfferingAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryEcsImageFromLocalAction(inventory.APIQueryEcsImageFromLocalMsg):
    def __init__(self):
        super(QueryEcsImageFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryEcsImageFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryEcsInstanceFromLocalAction(inventory.APIQueryEcsInstanceFromLocalMsg):
    def __init__(self):
        super(QueryEcsInstanceFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryEcsInstanceFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryEcsSecurityGroupFromLocalAction(inventory.APIQueryEcsSecurityGroupFromLocalMsg):
    def __init__(self):
        super(QueryEcsSecurityGroupFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryEcsSecurityGroupFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryEcsSecurityGroupRuleFromLocalAction(inventory.APIQueryEcsSecurityGroupRuleFromLocalMsg):
    def __init__(self):
        super(QueryEcsSecurityGroupRuleFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryEcsSecurityGroupRuleFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryEcsVSwitchFromLocalAction(inventory.APIQueryEcsVSwitchFromLocalMsg):
    def __init__(self):
        super(QueryEcsVSwitchFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryEcsVSwitchFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryEcsVpcFromLocalAction(inventory.APIQueryEcsVpcFromLocalMsg):
    def __init__(self):
        super(QueryEcsVpcFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryEcsVpcFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryEipAction(inventory.APIQueryEipMsg):
    def __init__(self):
        super(QueryEipAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryEipAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryEmailMediaAction(inventory.APIQueryEmailMediaMsg):
    def __init__(self):
        super(QueryEmailMediaAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryEmailMediaAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryEmailTriggerActionAction(inventory.APIQueryEmailTriggerActionMsg):
    def __init__(self):
        super(QueryEmailTriggerActionAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryEmailTriggerActionAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryFusionstorBackupStorageAction(inventory.APIQueryFusionstorBackupStorageMsg):
    def __init__(self):
        super(QueryFusionstorBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryFusionstorBackupStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryFusionstorPrimaryStorageAction(inventory.APIQueryFusionstorPrimaryStorageMsg):
    def __init__(self):
        super(QueryFusionstorPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryFusionstorPrimaryStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryGCJobAction(inventory.APIQueryGCJobMsg):
    def __init__(self):
        super(QueryGCJobAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryGCJobAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryGlobalConfigAction(inventory.APIQueryGlobalConfigMsg):
    def __init__(self):
        super(QueryGlobalConfigAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryGlobalConfigAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryHostAction(inventory.APIQueryHostMsg):
    def __init__(self):
        super(QueryHostAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryHostAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryHybridEipFromLocalAction(inventory.APIQueryHybridEipFromLocalMsg):
    def __init__(self):
        super(QueryHybridEipFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryHybridEipFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryIPSecConnectionAction(inventory.APIQueryIPSecConnectionMsg):
    def __init__(self):
        super(QueryIPSecConnectionAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryIPSecConnectionAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryIdentityZoneFromLocalAction(inventory.APIQueryIdentityZoneFromLocalMsg):
    def __init__(self):
        super(QueryIdentityZoneFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryIdentityZoneFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryImageAction(inventory.APIQueryImageMsg):
    def __init__(self):
        super(QueryImageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryImageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryImageStoreBackupStorageAction(inventory.APIQueryImageStoreBackupStorageMsg):
    def __init__(self):
        super(QueryImageStoreBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryImageStoreBackupStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryInstanceOfferingAction(inventory.APIQueryInstanceOfferingMsg):
    def __init__(self):
        super(QueryInstanceOfferingAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryInstanceOfferingAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryIpRangeAction(inventory.APIQueryIpRangeMsg):
    def __init__(self):
        super(QueryIpRangeAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryIpRangeAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryL2NetworkAction(inventory.APIQueryL2NetworkMsg):
    def __init__(self):
        super(QueryL2NetworkAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryL2NetworkAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryL2VlanNetworkAction(inventory.APIQueryL2VlanNetworkMsg):
    def __init__(self):
        super(QueryL2VlanNetworkAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryL2VlanNetworkAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryL2VxlanNetworkAction(inventory.APIQueryL2VxlanNetworkMsg):
    def __init__(self):
        super(QueryL2VxlanNetworkAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryL2VxlanNetworkAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryL2VxlanNetworkPoolAction(inventory.APIQueryL2VxlanNetworkPoolMsg):
    def __init__(self):
        super(QueryL2VxlanNetworkPoolAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryL2VxlanNetworkPoolAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryL3NetworkAction(inventory.APIQueryL3NetworkMsg):
    def __init__(self):
        super(QueryL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryL3NetworkAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryLdapBindingAction(inventory.APIQueryLdapBindingMsg):
    def __init__(self):
        super(QueryLdapBindingAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryLdapBindingAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryLdapServerAction(inventory.APIQueryLdapServerMsg):
    def __init__(self):
        super(QueryLdapServerAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryLdapServerAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryLoadBalancerAction(inventory.APIQueryLoadBalancerMsg):
    def __init__(self):
        super(QueryLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryLoadBalancerAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryLoadBalancerListenerAction(inventory.APIQueryLoadBalancerListenerMsg):
    def __init__(self):
        super(QueryLoadBalancerListenerAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryLoadBalancerListenerAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryLocalStorageResourceRefAction(inventory.APIQueryLocalStorageResourceRefMsg):
    def __init__(self):
        super(QueryLocalStorageResourceRefAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryLocalStorageResourceRefAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryManagementNodeAction(inventory.APIQueryManagementNodeMsg):
    def __init__(self):
        super(QueryManagementNodeAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryManagementNodeAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryMediaAction(inventory.APIQueryMediaMsg):
    def __init__(self):
        super(QueryMediaAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryMediaAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryMonitorTriggerAction(inventory.APIQueryMonitorTriggerMsg):
    def __init__(self):
        super(QueryMonitorTriggerAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryMonitorTriggerAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryMonitorTriggerActionAction(inventory.APIQueryMonitorTriggerActionMsg):
    def __init__(self):
        super(QueryMonitorTriggerActionAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryMonitorTriggerActionAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryNetworkServiceL3NetworkRefAction(inventory.APIQueryNetworkServiceL3NetworkRefMsg):
    def __init__(self):
        super(QueryNetworkServiceL3NetworkRefAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryNetworkServiceL3NetworkRefAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryNetworkServiceProviderAction(inventory.APIQueryNetworkServiceProviderMsg):
    def __init__(self):
        super(QueryNetworkServiceProviderAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryNetworkServiceProviderAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryNotificationAction(inventory.APIQueryNotificationMsg):
    def __init__(self):
        super(QueryNotificationAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryNotificationAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryNotificationSubscriptionAction(inventory.APIQueryNotificationSubscriptionMsg):
    def __init__(self):
        super(QueryNotificationSubscriptionAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryNotificationSubscriptionAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryOssBucketFileNameAction(inventory.APIQueryOssBucketFileNameMsg):
    def __init__(self):
        super(QueryOssBucketFileNameAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryOssBucketFileNameAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryPciDeviceAction(inventory.APIQueryPciDeviceMsg):
    def __init__(self):
        super(QueryPciDeviceAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryPciDeviceAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryPciDeviceOfferingAction(inventory.APIQueryPciDeviceOfferingMsg):
    def __init__(self):
        super(QueryPciDeviceOfferingAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryPciDeviceOfferingAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryPciDevicePciDeviceOfferingAction(inventory.APIQueryPciDevicePciDeviceOfferingMsg):
    def __init__(self):
        super(QueryPciDevicePciDeviceOfferingAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryPciDevicePciDeviceOfferingAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryPolicyAction(inventory.APIQueryPolicyMsg):
    def __init__(self):
        super(QueryPolicyAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryPolicyAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryPortForwardingRuleAction(inventory.APIQueryPortForwardingRuleMsg):
    def __init__(self):
        super(QueryPortForwardingRuleAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryPortForwardingRuleAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryPrimaryStorageAction(inventory.APIQueryPrimaryStorageMsg):
    def __init__(self):
        super(QueryPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryPrimaryStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryQuotaAction(inventory.APIQueryQuotaMsg):
    def __init__(self):
        super(QueryQuotaAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryQuotaAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryResourcePriceAction(inventory.APIQueryResourcePriceMsg):
    def __init__(self):
        super(QueryResourcePriceAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryResourcePriceAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryRouterInterfaceFromLocalAction(inventory.APIQueryRouterInterfaceFromLocalMsg):
    def __init__(self):
        super(QueryRouterInterfaceFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryRouterInterfaceFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QuerySchedulerJobAction(inventory.APIQuerySchedulerJobMsg):
    def __init__(self):
        super(QuerySchedulerJobAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySchedulerJobAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QuerySchedulerTriggerAction(inventory.APIQuerySchedulerTriggerMsg):
    def __init__(self):
        super(QuerySchedulerTriggerAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySchedulerTriggerAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QuerySecurityGroupAction(inventory.APIQuerySecurityGroupMsg):
    def __init__(self):
        super(QuerySecurityGroupAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySecurityGroupAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QuerySecurityGroupRuleAction(inventory.APIQuerySecurityGroupRuleMsg):
    def __init__(self):
        super(QuerySecurityGroupRuleAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySecurityGroupRuleAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QuerySftpBackupStorageAction(inventory.APIQuerySftpBackupStorageMsg):
    def __init__(self):
        super(QuerySftpBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySftpBackupStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryShareableVolumeVmInstanceRefAction(inventory.APIQueryShareableVolumeVmInstanceRefMsg):
    def __init__(self):
        super(QueryShareableVolumeVmInstanceRefAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryShareableVolumeVmInstanceRefAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QuerySharedResourceAction(inventory.APIQuerySharedResourceMsg):
    def __init__(self):
        super(QuerySharedResourceAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySharedResourceAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QuerySurfsBackupStorageAction(inventory.APIQuerySurfsBackupStorageMsg):
    def __init__(self):
        super(QuerySurfsBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySurfsBackupStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QuerySurfsPoolClassAction(inventory.APIQuerySurfsPoolClassMsg):
    def __init__(self):
        super(QuerySurfsPoolClassAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySurfsPoolClassAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QuerySurfsPrimaryStorageAction(inventory.APIQuerySurfsPrimaryStorageMsg):
    def __init__(self):
        super(QuerySurfsPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySurfsPrimaryStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QuerySystemTagAction(inventory.APIQuerySystemTagMsg):
    def __init__(self):
        super(QuerySystemTagAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySystemTagAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryTagAction(inventory.APIQueryTagMsg):
    def __init__(self):
        super(QueryTagAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryTagAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryUsbDeviceAction(inventory.APIQueryUsbDeviceMsg):
    def __init__(self):
        super(QueryUsbDeviceAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryUsbDeviceAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryUserAction(inventory.APIQueryUserMsg):
    def __init__(self):
        super(QueryUserAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryUserAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryUserGroupAction(inventory.APIQueryUserGroupMsg):
    def __init__(self):
        super(QueryUserGroupAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryUserGroupAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryUserTagAction(inventory.APIQueryUserTagMsg):
    def __init__(self):
        super(QueryUserTagAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryUserTagAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVCenterAction(inventory.APIQueryVCenterMsg):
    def __init__(self):
        super(QueryVCenterAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVCenterAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVCenterBackupStorageAction(inventory.APIQueryVCenterBackupStorageMsg):
    def __init__(self):
        super(QueryVCenterBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVCenterBackupStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVCenterClusterAction(inventory.APIQueryVCenterClusterMsg):
    def __init__(self):
        super(QueryVCenterClusterAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVCenterClusterAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVCenterDatacenterAction(inventory.APIQueryVCenterDatacenterMsg):
    def __init__(self):
        super(QueryVCenterDatacenterAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVCenterDatacenterAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVCenterPrimaryStorageAction(inventory.APIQueryVCenterPrimaryStorageMsg):
    def __init__(self):
        super(QueryVCenterPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVCenterPrimaryStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVRouterRouteEntryAction(inventory.APIQueryVRouterRouteEntryMsg):
    def __init__(self):
        super(QueryVRouterRouteEntryAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVRouterRouteEntryAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVRouterRouteTableAction(inventory.APIQueryVRouterRouteTableMsg):
    def __init__(self):
        super(QueryVRouterRouteTableAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVRouterRouteTableAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVipAction(inventory.APIQueryVipMsg):
    def __init__(self):
        super(QueryVipAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVipAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVirtualBorderRouterFromLocalAction(inventory.APIQueryVirtualBorderRouterFromLocalMsg):
    def __init__(self):
        super(QueryVirtualBorderRouterFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVirtualBorderRouterFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVirtualRouterOfferingAction(inventory.APIQueryVirtualRouterOfferingMsg):
    def __init__(self):
        super(QueryVirtualRouterOfferingAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVirtualRouterOfferingAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVirtualRouterVRouterRouteTableRefAction(inventory.APIQueryVirtualRouterVRouterRouteTableRefMsg):
    def __init__(self):
        super(QueryVirtualRouterVRouterRouteTableRefAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVirtualRouterVRouterRouteTableRefAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVirtualRouterVmAction(inventory.APIQueryVirtualRouterVmMsg):
    def __init__(self):
        super(QueryVirtualRouterVmAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVirtualRouterVmAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVmInstanceAction(inventory.APIQueryVmInstanceMsg):
    def __init__(self):
        super(QueryVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVmInstanceAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVmNicAction(inventory.APIQueryVmNicMsg):
    def __init__(self):
        super(QueryVmNicAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVmNicAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVmNicInSecurityGroupAction(inventory.APIQueryVmNicInSecurityGroupMsg):
    def __init__(self):
        super(QueryVmNicInSecurityGroupAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVmNicInSecurityGroupAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVniRangeAction(inventory.APIQueryVniRangeMsg):
    def __init__(self):
        super(QueryVniRangeAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVniRangeAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVolumeAction(inventory.APIQueryVolumeMsg):
    def __init__(self):
        super(QueryVolumeAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVolumeAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVolumeSnapshotAction(inventory.APIQueryVolumeSnapshotMsg):
    def __init__(self):
        super(QueryVolumeSnapshotAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVolumeSnapshotAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVolumeSnapshotTreeAction(inventory.APIQueryVolumeSnapshotTreeMsg):
    def __init__(self):
        super(QueryVolumeSnapshotTreeAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVolumeSnapshotTreeAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVpcIkeConfigFromLocalAction(inventory.APIQueryVpcIkeConfigFromLocalMsg):
    def __init__(self):
        super(QueryVpcIkeConfigFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVpcIkeConfigFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVpcIpSecConfigFromLocalAction(inventory.APIQueryVpcIpSecConfigFromLocalMsg):
    def __init__(self):
        super(QueryVpcIpSecConfigFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVpcIpSecConfigFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVpcUserVpnGatewayFromLocalAction(inventory.APIQueryVpcUserVpnGatewayFromLocalMsg):
    def __init__(self):
        super(QueryVpcUserVpnGatewayFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVpcUserVpnGatewayFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVpcVpnConnectionFromLocalAction(inventory.APIQueryVpcVpnConnectionFromLocalMsg):
    def __init__(self):
        super(QueryVpcVpnConnectionFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVpcVpnConnectionFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVpcVpnGatewayFromLocalAction(inventory.APIQueryVpcVpnGatewayFromLocalMsg):
    def __init__(self):
        super(QueryVpcVpnGatewayFromLocalAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVpcVpnGatewayFromLocalAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryVtepAction(inventory.APIQueryVtepMsg):
    def __init__(self):
        super(QueryVtepAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryVtepAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryWebhookAction(inventory.APIQueryWebhookMsg):
    def __init__(self):
        super(QueryWebhookAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryWebhookAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class QueryZoneAction(inventory.APIQueryZoneMsg):
    def __init__(self):
        super(QueryZoneAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryZoneAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class RebootEcsInstanceAction(inventory.APIRebootEcsInstanceMsg):
    def __init__(self):
        super(RebootEcsInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RebootEcsInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RebootVmInstanceAction(inventory.APIRebootVmInstanceMsg):
    def __init__(self):
        super(RebootVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RebootVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ReclaimSpaceFromImageStoreAction(inventory.APIReclaimSpaceFromImageStoreMsg):
    def __init__(self):
        super(ReclaimSpaceFromImageStoreAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ReclaimSpaceFromImageStoreAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ReconnectBackupStorageAction(inventory.APIReconnectBackupStorageMsg):
    def __init__(self):
        super(ReconnectBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ReconnectBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ReconnectConsoleProxyAgentAction(inventory.APIReconnectConsoleProxyAgentMsg):
    def __init__(self):
        super(ReconnectConsoleProxyAgentAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ReconnectConsoleProxyAgentAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ReconnectHostAction(inventory.APIReconnectHostMsg):
    def __init__(self):
        super(ReconnectHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ReconnectHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ReconnectImageStoreBackupStorageAction(inventory.APIReconnectImageStoreBackupStorageMsg):
    def __init__(self):
        super(ReconnectImageStoreBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ReconnectImageStoreBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ReconnectPrimaryStorageAction(inventory.APIReconnectPrimaryStorageMsg):
    def __init__(self):
        super(ReconnectPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ReconnectPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ReconnectSftpBackupStorageAction(inventory.APIReconnectSftpBackupStorageMsg):
    def __init__(self):
        super(ReconnectSftpBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ReconnectSftpBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ReconnectVirtualRouterAction(inventory.APIReconnectVirtualRouterMsg):
    def __init__(self):
        super(ReconnectVirtualRouterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ReconnectVirtualRouterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RecoverDataVolumeAction(inventory.APIRecoverDataVolumeMsg):
    def __init__(self):
        super(RecoverDataVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RecoverDataVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RecoverImageAction(inventory.APIRecoverImageMsg):
    def __init__(self):
        super(RecoverImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RecoverImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RecoverVmInstanceAction(inventory.APIRecoverVmInstanceMsg):
    def __init__(self):
        super(RecoverVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RecoverVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RecoveryImageFromImageStoreBackupStorageAction(inventory.APIRecoveryImageFromImageStoreBackupStorageMsg):
    def __init__(self):
        super(RecoveryImageFromImageStoreBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RecoveryImageFromImageStoreBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RecoveryVirtualBorderRouterRemoteAction(inventory.APIRecoveryVirtualBorderRouterRemoteMsg):
    def __init__(self):
        super(RecoveryVirtualBorderRouterRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RecoveryVirtualBorderRouterRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RefreshLoadBalancerAction(inventory.APIRefreshLoadBalancerMsg):
    def __init__(self):
        super(RefreshLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RefreshLoadBalancerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ReimageVmInstanceAction(inventory.APIReimageVmInstanceMsg):
    def __init__(self):
        super(ReimageVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ReimageVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ReloadLicenseAction(inventory.APIReloadLicenseMsg):
    def __init__(self):
        super(ReloadLicenseAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ReloadLicenseAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RemoveDnsFromL3NetworkAction(inventory.APIRemoveDnsFromL3NetworkMsg):
    def __init__(self):
        super(RemoveDnsFromL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveDnsFromL3NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RemoveMonFromCephBackupStorageAction(inventory.APIRemoveMonFromCephBackupStorageMsg):
    def __init__(self):
        super(RemoveMonFromCephBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveMonFromCephBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RemoveMonFromCephPrimaryStorageAction(inventory.APIRemoveMonFromCephPrimaryStorageMsg):
    def __init__(self):
        super(RemoveMonFromCephPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveMonFromCephPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RemoveMonFromFusionstorBackupStorageAction(inventory.APIRemoveMonFromFusionstorBackupStorageMsg):
    def __init__(self):
        super(RemoveMonFromFusionstorBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveMonFromFusionstorBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RemoveMonFromFusionstorPrimaryStorageAction(inventory.APIRemoveMonFromFusionstorPrimaryStorageMsg):
    def __init__(self):
        super(RemoveMonFromFusionstorPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveMonFromFusionstorPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RemoveNodeFromSurfsBackupStorageAction(inventory.APIRemoveNodeFromSurfsBackupStorageMsg):
    def __init__(self):
        super(RemoveNodeFromSurfsBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveNodeFromSurfsBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RemoveNodeFromSurfsPrimaryStorageAction(inventory.APIRemoveNodeFromSurfsPrimaryStorageMsg):
    def __init__(self):
        super(RemoveNodeFromSurfsPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveNodeFromSurfsPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RemoveSchedulerJobFromSchedulerTriggerAction(inventory.APIRemoveSchedulerJobFromSchedulerTriggerMsg):
    def __init__(self):
        super(RemoveSchedulerJobFromSchedulerTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveSchedulerJobFromSchedulerTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RemoveUserFromGroupAction(inventory.APIRemoveUserFromGroupMsg):
    def __init__(self):
        super(RemoveUserFromGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveUserFromGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RemoveVmNicFromLoadBalancerAction(inventory.APIRemoveVmNicFromLoadBalancerMsg):
    def __init__(self):
        super(RemoveVmNicFromLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveVmNicFromLoadBalancerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RequestBaremetalConsoleAccessAction(inventory.APIRequestBaremetalConsoleAccessMsg):
    def __init__(self):
        super(RequestBaremetalConsoleAccessAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RequestBaremetalConsoleAccessAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RequestConsoleAccessAction(inventory.APIRequestConsoleAccessMsg):
    def __init__(self):
        super(RequestConsoleAccessAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RequestConsoleAccessAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ResizeRootVolumeAction(inventory.APIResizeRootVolumeMsg):
    def __init__(self):
        super(ResizeRootVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ResizeRootVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ResumeVmInstanceAction(inventory.APIResumeVmInstanceMsg):
    def __init__(self):
        super(ResumeVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ResumeVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RevertVolumeFromSnapshotAction(inventory.APIRevertVolumeFromSnapshotMsg):
    def __init__(self):
        super(RevertVolumeFromSnapshotAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RevertVolumeFromSnapshotAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class RevokeResourceSharingAction(inventory.APIRevokeResourceSharingMsg):
    def __init__(self):
        super(RevokeResourceSharingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RevokeResourceSharingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ScanBackupStorageAction(inventory.APIScanBackupStorageMsg):
    def __init__(self):
        super(ScanBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ScanBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SearchGenerateSqlTriggerAction(inventory.APISearchGenerateSqlTriggerMsg):
    def __init__(self):
        super(SearchGenerateSqlTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SearchGenerateSqlTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SessionMessageAction(inventory.APISessionMessage):
    def __init__(self):
        super(SessionMessageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetImageQgaAction(inventory.APISetImageQgaMsg):
    def __init__(self):
        super(SetImageQgaAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetImageQgaAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetL3NetworkMtuAction(inventory.APISetL3NetworkMtuMsg):
    def __init__(self):
        super(SetL3NetworkMtuAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetL3NetworkMtuAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetL3NetworkRouterInterfaceIpAction(inventory.APISetL3NetworkRouterInterfaceIpMsg):
    def __init__(self):
        super(SetL3NetworkRouterInterfaceIpAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetL3NetworkRouterInterfaceIpAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetNicQosAction(inventory.APISetNicQosMsg):
    def __init__(self):
        super(SetNicQosAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetNicQosAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVipQosAction(inventory.APISetVipQosMsg):
    def __init__(self):
        super(SetVipQosAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVipQosAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVmBootOrderAction(inventory.APISetVmBootOrderMsg):
    def __init__(self):
        super(SetVmBootOrderAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVmBootOrderAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVmConsolePasswordAction(inventory.APISetVmConsolePasswordMsg):
    def __init__(self):
        super(SetVmConsolePasswordAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVmConsolePasswordAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVmHostnameAction(inventory.APISetVmHostnameMsg):
    def __init__(self):
        super(SetVmHostnameAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVmHostnameAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVmInstanceHaLevelAction(inventory.APISetVmInstanceHaLevelMsg):
    def __init__(self):
        super(SetVmInstanceHaLevelAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVmInstanceHaLevelAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVmMonitorNumberAction(inventory.APISetVmMonitorNumberMsg):
    def __init__(self):
        super(SetVmMonitorNumberAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVmMonitorNumberAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVmQgaAction(inventory.APISetVmQgaMsg):
    def __init__(self):
        super(SetVmQgaAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVmQgaAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVmRDPAction(inventory.APISetVmRDPMsg):
    def __init__(self):
        super(SetVmRDPAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVmRDPAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVmSshKeyAction(inventory.APISetVmSshKeyMsg):
    def __init__(self):
        super(SetVmSshKeyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVmSshKeyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVmStaticIpAction(inventory.APISetVmStaticIpMsg):
    def __init__(self):
        super(SetVmStaticIpAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVmStaticIpAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVmUsbRedirectAction(inventory.APISetVmUsbRedirectMsg):
    def __init__(self):
        super(SetVmUsbRedirectAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVmUsbRedirectAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SetVolumeQosAction(inventory.APISetVolumeQosMsg):
    def __init__(self):
        super(SetVolumeQosAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SetVolumeQosAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ShareResourceAction(inventory.APIShareResourceMsg):
    def __init__(self):
        super(ShareResourceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[ShareResourceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class StartBaremetalPxeServerAction(inventory.APIStartBaremetalPxeServerMsg):
    def __init__(self):
        super(StartBaremetalPxeServerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[StartBaremetalPxeServerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class StartEcsInstanceAction(inventory.APIStartEcsInstanceMsg):
    def __init__(self):
        super(StartEcsInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[StartEcsInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class StartVmInstanceAction(inventory.APIStartVmInstanceMsg):
    def __init__(self):
        super(StartVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[StartVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class StopBaremetalPxeServerAction(inventory.APIStopBaremetalPxeServerMsg):
    def __init__(self):
        super(StopBaremetalPxeServerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[StopBaremetalPxeServerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class StopEcsInstanceAction(inventory.APIStopEcsInstanceMsg):
    def __init__(self):
        super(StopEcsInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[StopEcsInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class StopVmInstanceAction(inventory.APIStopVmInstanceMsg):
    def __init__(self):
        super(StopVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[StopVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncAliyunRouteEntryFromRemoteAction(inventory.APISyncAliyunRouteEntryFromRemoteMsg):
    def __init__(self):
        super(SyncAliyunRouteEntryFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncAliyunRouteEntryFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncAliyunSnapshotRemoteAction(inventory.APISyncAliyunSnapshotRemoteMsg):
    def __init__(self):
        super(SyncAliyunSnapshotRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncAliyunSnapshotRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncAliyunVirtualRouterFromRemoteAction(inventory.APISyncAliyunVirtualRouterFromRemoteMsg):
    def __init__(self):
        super(SyncAliyunVirtualRouterFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncAliyunVirtualRouterFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncConnectionAccessPointFromRemoteAction(inventory.APISyncConnectionAccessPointFromRemoteMsg):
    def __init__(self):
        super(SyncConnectionAccessPointFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncConnectionAccessPointFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncDataCenterFromRemoteAction(inventory.APISyncDataCenterFromRemoteMsg):
    def __init__(self):
        super(SyncDataCenterFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncDataCenterFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncDiskFromAliyunFromRemoteAction(inventory.APISyncDiskFromAliyunFromRemoteMsg):
    def __init__(self):
        super(SyncDiskFromAliyunFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncDiskFromAliyunFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncEcsImageFromRemoteAction(inventory.APISyncEcsImageFromRemoteMsg):
    def __init__(self):
        super(SyncEcsImageFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncEcsImageFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncEcsInstanceFromRemoteAction(inventory.APISyncEcsInstanceFromRemoteMsg):
    def __init__(self):
        super(SyncEcsInstanceFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncEcsInstanceFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncEcsSecurityGroupFromRemoteAction(inventory.APISyncEcsSecurityGroupFromRemoteMsg):
    def __init__(self):
        super(SyncEcsSecurityGroupFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncEcsSecurityGroupFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncEcsSecurityGroupRuleFromRemoteAction(inventory.APISyncEcsSecurityGroupRuleFromRemoteMsg):
    def __init__(self):
        super(SyncEcsSecurityGroupRuleFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncEcsSecurityGroupRuleFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncEcsVSwitchFromRemoteAction(inventory.APISyncEcsVSwitchFromRemoteMsg):
    def __init__(self):
        super(SyncEcsVSwitchFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncEcsVSwitchFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncEcsVpcFromRemoteAction(inventory.APISyncEcsVpcFromRemoteMsg):
    def __init__(self):
        super(SyncEcsVpcFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncEcsVpcFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncHybridEipFromRemoteAction(inventory.APISyncHybridEipFromRemoteMsg):
    def __init__(self):
        super(SyncHybridEipFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncHybridEipFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncIdentityFromRemoteAction(inventory.APISyncIdentityFromRemoteMsg):
    def __init__(self):
        super(SyncIdentityFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncIdentityFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncImageFromImageStoreBackupStorageAction(inventory.APISyncImageFromImageStoreBackupStorageMsg):
    def __init__(self):
        super(SyncImageFromImageStoreBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncImageFromImageStoreBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncImageSizeAction(inventory.APISyncImageSizeMsg):
    def __init__(self):
        super(SyncImageSizeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncImageSizeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncPrimaryStorageCapacityAction(inventory.APISyncPrimaryStorageCapacityMsg):
    def __init__(self):
        super(SyncPrimaryStorageCapacityAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncPrimaryStorageCapacityAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncRouterInterfaceFromRemoteAction(inventory.APISyncRouterInterfaceFromRemoteMsg):
    def __init__(self):
        super(SyncRouterInterfaceFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncRouterInterfaceFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncVirtualBorderRouterFromRemoteAction(inventory.APISyncVirtualBorderRouterFromRemoteMsg):
    def __init__(self):
        super(SyncVirtualBorderRouterFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncVirtualBorderRouterFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncVolumeSizeAction(inventory.APISyncVolumeSizeMsg):
    def __init__(self):
        super(SyncVolumeSizeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncVolumeSizeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncVpcUserVpnGatewayFromRemoteAction(inventory.APISyncVpcUserVpnGatewayFromRemoteMsg):
    def __init__(self):
        super(SyncVpcUserVpnGatewayFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncVpcUserVpnGatewayFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncVpcVpnConnectionFromRemoteAction(inventory.APISyncVpcVpnConnectionFromRemoteMsg):
    def __init__(self):
        super(SyncVpcVpnConnectionFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncVpcVpnConnectionFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class SyncVpcVpnGatewayFromRemoteAction(inventory.APISyncVpcVpnGatewayFromRemoteMsg):
    def __init__(self):
        super(SyncVpcVpnGatewayFromRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SyncVpcVpnGatewayFromRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class TerminateVirtualBorderRouterRemoteAction(inventory.APITerminateVirtualBorderRouterRemoteMsg):
    def __init__(self):
        super(TerminateVirtualBorderRouterRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[TerminateVirtualBorderRouterRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class TriggerGCJobAction(inventory.APITriggerGCJobMsg):
    def __init__(self):
        super(TriggerGCJobAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[TriggerGCJobAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateAccountAction(inventory.APIUpdateAccountMsg):
    def __init__(self):
        super(UpdateAccountAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateAccountAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateAliyunDiskAction(inventory.APIUpdateAliyunDiskMsg):
    def __init__(self):
        super(UpdateAliyunDiskAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateAliyunDiskAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateAliyunKeySecretAction(inventory.APIUpdateAliyunKeySecretMsg):
    def __init__(self):
        super(UpdateAliyunKeySecretAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateAliyunKeySecretAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateAliyunSnapshotAction(inventory.APIUpdateAliyunSnapshotMsg):
    def __init__(self):
        super(UpdateAliyunSnapshotAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateAliyunSnapshotAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateAliyunVirtualRouterAction(inventory.APIUpdateAliyunVirtualRouterMsg):
    def __init__(self):
        super(UpdateAliyunVirtualRouterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateAliyunVirtualRouterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateBackupStorageAction(inventory.APIUpdateBackupStorageMsg):
    def __init__(self):
        super(UpdateBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateBaremetalChassisAction(inventory.APIUpdateBaremetalChassisMsg):
    def __init__(self):
        super(UpdateBaremetalChassisAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateBaremetalChassisAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateBaremetalPxeServerAction(inventory.APIUpdateBaremetalPxeServerMsg):
    def __init__(self):
        super(UpdateBaremetalPxeServerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateBaremetalPxeServerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateCephBackupStorageMonAction(inventory.APIUpdateCephBackupStorageMonMsg):
    def __init__(self):
        super(UpdateCephBackupStorageMonAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateCephBackupStorageMonAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateCephPrimaryStorageMonAction(inventory.APIUpdateCephPrimaryStorageMonMsg):
    def __init__(self):
        super(UpdateCephPrimaryStorageMonAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateCephPrimaryStorageMonAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateCephPrimaryStoragePoolAction(inventory.APIUpdateCephPrimaryStoragePoolMsg):
    def __init__(self):
        super(UpdateCephPrimaryStoragePoolAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateCephPrimaryStoragePoolAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateClusterAction(inventory.APIUpdateClusterMsg):
    def __init__(self):
        super(UpdateClusterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateClusterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateConnectionBetweenL3NetWorkAndAliyunVSwitchAction(inventory.APIUpdateConnectionBetweenL3NetWorkAndAliyunVSwitchMsg):
    def __init__(self):
        super(UpdateConnectionBetweenL3NetWorkAndAliyunVSwitchAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateConnectionBetweenL3NetWorkAndAliyunVSwitchAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateDiskOfferingAction(inventory.APIUpdateDiskOfferingMsg):
    def __init__(self):
        super(UpdateDiskOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateDiskOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateEcsImageAction(inventory.APIUpdateEcsImageMsg):
    def __init__(self):
        super(UpdateEcsImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateEcsImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateEcsInstanceAction(inventory.APIUpdateEcsInstanceMsg):
    def __init__(self):
        super(UpdateEcsInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateEcsInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateEcsInstanceVncPasswordAction(inventory.APIUpdateEcsInstanceVncPasswordMsg):
    def __init__(self):
        super(UpdateEcsInstanceVncPasswordAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateEcsInstanceVncPasswordAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateEcsSecurityGroupAction(inventory.APIUpdateEcsSecurityGroupMsg):
    def __init__(self):
        super(UpdateEcsSecurityGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateEcsSecurityGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateEcsVSwitchAction(inventory.APIUpdateEcsVSwitchMsg):
    def __init__(self):
        super(UpdateEcsVSwitchAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateEcsVSwitchAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateEcsVpcAction(inventory.APIUpdateEcsVpcMsg):
    def __init__(self):
        super(UpdateEcsVpcAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateEcsVpcAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateEipAction(inventory.APIUpdateEipMsg):
    def __init__(self):
        super(UpdateEipAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateEipAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateEmailMediaAction(inventory.APIUpdateEmailMediaMsg):
    def __init__(self):
        super(UpdateEmailMediaAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateEmailMediaAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateEmailMonitorTriggerActionAction(inventory.APIUpdateEmailMonitorTriggerActionMsg):
    def __init__(self):
        super(UpdateEmailMonitorTriggerActionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateEmailMonitorTriggerActionAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateEncryptKeyAction(inventory.APIUpdateEncryptKeyMsg):
    def __init__(self):
        super(UpdateEncryptKeyAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateEncryptKeyAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateFusionstorBackupStorageMonAction(inventory.APIUpdateFusionstorBackupStorageMonMsg):
    def __init__(self):
        super(UpdateFusionstorBackupStorageMonAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateFusionstorBackupStorageMonAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateFusionstorPrimaryStorageMonAction(inventory.APIUpdateFusionstorPrimaryStorageMonMsg):
    def __init__(self):
        super(UpdateFusionstorPrimaryStorageMonAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateFusionstorPrimaryStorageMonAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateGlobalConfigAction(inventory.APIUpdateGlobalConfigMsg):
    def __init__(self):
        super(UpdateGlobalConfigAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateGlobalConfigAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateHostAction(inventory.APIUpdateHostMsg):
    def __init__(self):
        super(UpdateHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateHostIommuStateAction(inventory.APIUpdateHostIommuStateMsg):
    def __init__(self):
        super(UpdateHostIommuStateAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateHostIommuStateAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateHybridEipAction(inventory.APIUpdateHybridEipMsg):
    def __init__(self):
        super(UpdateHybridEipAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateHybridEipAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateIPsecConnectionAction(inventory.APIUpdateIPsecConnectionMsg):
    def __init__(self):
        super(UpdateIPsecConnectionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateIPsecConnectionAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateImageAction(inventory.APIUpdateImageMsg):
    def __init__(self):
        super(UpdateImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateImageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateImageStoreBackupStorageAction(inventory.APIUpdateImageStoreBackupStorageMsg):
    def __init__(self):
        super(UpdateImageStoreBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateImageStoreBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateInstanceOfferingAction(inventory.APIUpdateInstanceOfferingMsg):
    def __init__(self):
        super(UpdateInstanceOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateInstanceOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateIpRangeAction(inventory.APIUpdateIpRangeMsg):
    def __init__(self):
        super(UpdateIpRangeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateIpRangeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateKVMHostAction(inventory.APIUpdateKVMHostMsg):
    def __init__(self):
        super(UpdateKVMHostAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateKVMHostAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateL2NetworkAction(inventory.APIUpdateL2NetworkMsg):
    def __init__(self):
        super(UpdateL2NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateL2NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateL3NetworkAction(inventory.APIUpdateL3NetworkMsg):
    def __init__(self):
        super(UpdateL3NetworkAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateL3NetworkAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateLdapServerAction(inventory.APIUpdateLdapServerMsg):
    def __init__(self):
        super(UpdateLdapServerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateLdapServerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateLicenseAction(inventory.APIUpdateLicenseMsg):
    def __init__(self):
        super(UpdateLicenseAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateLicenseAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateLoadBalancerAction(inventory.APIUpdateLoadBalancerMsg):
    def __init__(self):
        super(UpdateLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateLoadBalancerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateLoadBalancerListenerAction(inventory.APIUpdateLoadBalancerListenerMsg):
    def __init__(self):
        super(UpdateLoadBalancerListenerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateLoadBalancerListenerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateMonitorTriggerAction(inventory.APIUpdateMonitorTriggerMsg):
    def __init__(self):
        super(UpdateMonitorTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateMonitorTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateNotificationsStatusAction(inventory.APIUpdateNotificationsStatusMsg):
    def __init__(self):
        super(UpdateNotificationsStatusAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateNotificationsStatusAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateOssBucketAction(inventory.APIUpdateOssBucketMsg):
    def __init__(self):
        super(UpdateOssBucketAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateOssBucketAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdatePciDeviceAction(inventory.APIUpdatePciDeviceMsg):
    def __init__(self):
        super(UpdatePciDeviceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdatePciDeviceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdatePortForwardingRuleAction(inventory.APIUpdatePortForwardingRuleMsg):
    def __init__(self):
        super(UpdatePortForwardingRuleAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdatePortForwardingRuleAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdatePrimaryStorageAction(inventory.APIUpdatePrimaryStorageMsg):
    def __init__(self):
        super(UpdatePrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdatePrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateQuotaAction(inventory.APIUpdateQuotaMsg):
    def __init__(self):
        super(UpdateQuotaAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateQuotaAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateRouteInterfaceRemoteAction(inventory.APIUpdateRouteInterfaceRemoteMsg):
    def __init__(self):
        super(UpdateRouteInterfaceRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateRouteInterfaceRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateSchedulerJobAction(inventory.APIUpdateSchedulerJobMsg):
    def __init__(self):
        super(UpdateSchedulerJobAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateSchedulerJobAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateSchedulerTriggerAction(inventory.APIUpdateSchedulerTriggerMsg):
    def __init__(self):
        super(UpdateSchedulerTriggerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateSchedulerTriggerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateSecurityGroupAction(inventory.APIUpdateSecurityGroupMsg):
    def __init__(self):
        super(UpdateSecurityGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateSecurityGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateSftpBackupStorageAction(inventory.APIUpdateSftpBackupStorageMsg):
    def __init__(self):
        super(UpdateSftpBackupStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateSftpBackupStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateSurfsBackupStorageNodeAction(inventory.APIUpdateSurfsBackupStorageNodeMsg):
    def __init__(self):
        super(UpdateSurfsBackupStorageNodeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateSurfsBackupStorageNodeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateSurfsPrimaryStorageNodeAction(inventory.APIUpdateSurfsPrimaryStorageNodeMsg):
    def __init__(self):
        super(UpdateSurfsPrimaryStorageNodeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateSurfsPrimaryStorageNodeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateSystemTagAction(inventory.APIUpdateSystemTagMsg):
    def __init__(self):
        super(UpdateSystemTagAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateSystemTagAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateUsbDeviceAction(inventory.APIUpdateUsbDeviceMsg):
    def __init__(self):
        super(UpdateUsbDeviceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateUsbDeviceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateUserAction(inventory.APIUpdateUserMsg):
    def __init__(self):
        super(UpdateUserAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateUserAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateUserGroupAction(inventory.APIUpdateUserGroupMsg):
    def __init__(self):
        super(UpdateUserGroupAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateUserGroupAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateVCenterAction(inventory.APIUpdateVCenterMsg):
    def __init__(self):
        super(UpdateVCenterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateVCenterAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateVipAction(inventory.APIUpdateVipMsg):
    def __init__(self):
        super(UpdateVipAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateVipAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateVirtualBorderRouterRemoteAction(inventory.APIUpdateVirtualBorderRouterRemoteMsg):
    def __init__(self):
        super(UpdateVirtualBorderRouterRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateVirtualBorderRouterRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateVirtualRouterOfferingAction(inventory.APIUpdateVirtualRouterOfferingMsg):
    def __init__(self):
        super(UpdateVirtualRouterOfferingAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateVirtualRouterOfferingAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateVmInstanceAction(inventory.APIUpdateVmInstanceMsg):
    def __init__(self):
        super(UpdateVmInstanceAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateVmInstanceAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateVolumeAction(inventory.APIUpdateVolumeMsg):
    def __init__(self):
        super(UpdateVolumeAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateVolumeAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateVolumeSnapshotAction(inventory.APIUpdateVolumeSnapshotMsg):
    def __init__(self):
        super(UpdateVolumeSnapshotAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateVolumeSnapshotAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateVpcUserVpnGatewayAction(inventory.APIUpdateVpcUserVpnGatewayMsg):
    def __init__(self):
        super(UpdateVpcUserVpnGatewayAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateVpcUserVpnGatewayAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateVpcVpnConnectionRemoteAction(inventory.APIUpdateVpcVpnConnectionRemoteMsg):
    def __init__(self):
        super(UpdateVpcVpnConnectionRemoteAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateVpcVpnConnectionRemoteAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateVpcVpnGatewayAction(inventory.APIUpdateVpcVpnGatewayMsg):
    def __init__(self):
        super(UpdateVpcVpnGatewayAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateVpcVpnGatewayAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateWebhookAction(inventory.APIUpdateWebhookMsg):
    def __init__(self):
        super(UpdateWebhookAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateWebhookAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class UpdateZoneAction(inventory.APIUpdateZoneMsg):
    def __init__(self):
        super(UpdateZoneAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateZoneAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class ValidateSessionAction(inventory.APIValidateSessionMsg):
    def __init__(self):
        super(ValidateSessionAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out