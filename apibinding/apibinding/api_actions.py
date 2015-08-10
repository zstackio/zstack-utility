from apibinding import inventory
from apibinding import api
from zstacklib.utils import jsonobject

class SilentAction(inventory.APISilentMsg):
    def __init__(self):
        super(SilentAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[SilentAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
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

class LogInByUserAction(inventory.APILogInByUserMsg):
    def __init__(self):
        super(LogInByUserAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
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

class LogInByAccountAction(inventory.APILogInByAccountMsg):
    def __init__(self):
        super(LogInByAccountAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
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

class LogOutAction(inventory.APILogOutMsg):
    def __init__(self):
        super(LogOutAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
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

class AddIscsiFileSystemBackendPrimaryStorageAction(inventory.APIAddIscsiFileSystemBackendPrimaryStorageMsg):
    def __init__(self):
        super(AddIscsiFileSystemBackendPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddIscsiFileSystemBackendPrimaryStorageAction] cannot be None')
        evt = api.async_call(self, self.sessionUuid)
        self.out = evt
        return self.out

class QueryIscsiFileSystemBackendPrimaryStorageAction(inventory.APIQueryIscsiFileSystemBackendPrimaryStorageMsg):
    def __init__(self):
        super(QueryIscsiFileSystemBackendPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.reply = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[QueryIscsiFileSystemBackendPrimaryStorageAction] cannot be None')
        reply = api.sync_call(self, self.sessionUuid)
        self.reply = reply
        self.out = reply.inventories
        return self.out

class UpdateIscsiFileSystemBackendPrimaryStorageAction(inventory.APIUpdateIscsiFileSystemBackendPrimaryStorageMsg):
    def __init__(self):
        super(UpdateIscsiFileSystemBackendPrimaryStorageAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[UpdateIscsiFileSystemBackendPrimaryStorageAction] cannot be None')
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

class RemoveNicFromLoadBalancerAction(inventory.APIRemoveNicFromLoadBalancerMsg):
    def __init__(self):
        super(RemoveNicFromLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveNicFromLoadBalancerAction] cannot be None')
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

class AddVipToLoadBalancerAction(inventory.APIAddVipToLoadBalancerMsg):
    def __init__(self):
        super(AddVipToLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[AddVipToLoadBalancerAction] cannot be None')
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

class RemoveVipFromLoadBalancerAction(inventory.APIRemoveVipFromLoadBalancerMsg):
    def __init__(self):
        super(RemoveVipFromLoadBalancerAction, self).__init__()
        self.sessionUuid = None
        self.out = None
    def run(self):
        if not self.sessionUuid:
            raise Exception('sessionUuid of action[RemoveVipFromLoadBalancerAction] cannot be None')
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