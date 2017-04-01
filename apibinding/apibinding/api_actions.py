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

class AddOssFileBucketNameAction(inventory.APIAddOssFileBucketNameMsg):
    def __init__(self):
        super(AddOssFileBucketNameAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddOssFileBucketNameAction] cannot be None')
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

class CreateEcsInstanceFromLocalImageAction(inventory.APICreateEcsInstanceFromLocalImageMsg):
    def __init__(self):
        super(CreateEcsInstanceFromLocalImageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateEcsInstanceFromLocalImageAction] cannot be None')
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

class CreateRebootVmInstanceSchedulerAction(inventory.APICreateRebootVmInstanceSchedulerMsg):
    def __init__(self):
        super(CreateRebootVmInstanceSchedulerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateRebootVmInstanceSchedulerAction] cannot be None')
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

class CreateSchedulerMessageAction(inventory.APICreateSchedulerMessage):
    def __init__(self):
        super(CreateSchedulerMessageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateSchedulerMessageAction] cannot be None')
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

class CreateStartVmInstanceSchedulerAction(inventory.APICreateStartVmInstanceSchedulerMsg):
    def __init__(self):
        super(CreateStartVmInstanceSchedulerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateStartVmInstanceSchedulerAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class CreateStopVmInstanceSchedulerAction(inventory.APICreateStopVmInstanceSchedulerMsg):
    def __init__(self):
        super(CreateStopVmInstanceSchedulerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateStopVmInstanceSchedulerAction] cannot be None')
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

class CreateVmCpuAlarmAction(inventory.APICreateVmCpuAlarmMsg):
    def __init__(self):
        super(CreateVmCpuAlarmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVmCpuAlarmAction] cannot be None')
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

class CreateVolumeSnapshotSchedulerAction(inventory.APICreateVolumeSnapshotSchedulerMsg):
    def __init__(self):
        super(CreateVolumeSnapshotSchedulerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[CreateVolumeSnapshotSchedulerAction] cannot be None')
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

class DeleteAlarmAction(inventory.APIDeleteAlarmMsg):
    def __init__(self):
        super(DeleteAlarmAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteAlarmAction] cannot be None')
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

class DeleteOssFileBucketNameInLocalAction(inventory.APIDeleteOssFileBucketNameInLocalMsg):
    def __init__(self):
        super(DeleteOssFileBucketNameInLocalAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteOssFileBucketNameInLocalAction] cannot be None')
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

class DeleteSchedulerAction(inventory.APIDeleteSchedulerMsg):
    def __init__(self):
        super(DeleteSchedulerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DeleteSchedulerAction] cannot be None')
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

class DetachOssBucketToEcsDataCenterAction(inventory.APIDetachOssBucketToEcsDataCenterMsg):
    def __init__(self):
        super(DetachOssBucketToEcsDataCenterAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[DetachOssBucketToEcsDataCenterAction] cannot be None')
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

class GetHostMonitoringDataAction(inventory.APIGetHostMonitoringDataMsg):
    def __init__(self):
        super(GetHostMonitoringDataAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetHostMonitoringDataAction] cannot be None')
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

class GetVmMonitoringDataAction(inventory.APIGetVmMonitoringDataMsg):
    def __init__(self):
        super(GetVmMonitoringDataAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[GetVmMonitoringDataAction] cannot be None')
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

class MonitoringPassThroughAction(inventory.APIMonitoringPassThroughMsg):
    def __init__(self):
        super(MonitoringPassThroughAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[MonitoringPassThroughAction] cannot be None')
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

class QuerySchedulerAction(inventory.APIQuerySchedulerMsg):
    def __init__(self):
        super(QuerySchedulerAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QuerySchedulerAction] cannot be None')
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

class UpdateAlertAction(inventory.APIUpdateAlertMsg):
    def __init__(self):
        super(UpdateAlertAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateAlertAction] cannot be None')
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

class UpdateSchedulerAction(inventory.APIUpdateSchedulerMsg):
    def __init__(self):
        super(UpdateSchedulerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateSchedulerAction] cannot be None')
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