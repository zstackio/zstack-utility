

class NotNoneField(object):
    pass


class NotNoneList(object):
    pass


class OptionalList(object):
    pass


class NotNoneMap(object):
    pass


class OptionalMap(object):
    pass

class Session(object):
    def __init__(self):
        self.uuid = None


class ErrorCode(object):
    def __init__(self):
        self.code = None
        self.description = None
        self.details = None
        self.elaboration = None
        self.cause = None


class APIMessage(object):
    def __init__(self):
        super(APIMessage, self).__init__()
        self.timeout = None
        self.session = None


APIDELETEMESSAGE_FULL_NAME = 'org.zstack.header.message.APIDeleteMessage'
class APIDeleteMessage(APIMessage):
    FULL_NAME='org.zstack.header.message.APIDeleteMessage'
    def __init__(self):
        super(APIDeleteMessage, self).__init__()
        self.deleteMode = None


class NOLTriple(object):
    def __init__(self):
        self.name = None
        self.op = None
        self.vals = None


class NOVTriple(object):
    def __init__(self):
        self.name = None
        self.op = None
        self.val = None


APISILENTMSG_FULL_NAME = 'org.zstack.test.multinodes.APISilentMsg'
class APISilentMsg(APIMessage):
    FULL_NAME='org.zstack.test.multinodes.APISilentMsg'
    def __init__(self):
        super(APISilentMsg, self).__init__()


APISYNCCALLMESSAGE_FULL_NAME = 'org.zstack.header.message.APISyncCallMessage'
class APISyncCallMessage(APIMessage):
    FULL_NAME='org.zstack.header.message.APISyncCallMessage'
    def __init__(self):
        super(APISyncCallMessage, self).__init__()


APIQUERYMESSAGE_FULL_NAME = 'org.zstack.header.query.APIQueryMessage'
class APIQueryMessage(APISyncCallMessage):
    FULL_NAME='org.zstack.header.query.APIQueryMessage'
    def __init__(self):
        super(APIQueryMessage, self).__init__()
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()


APIQUERYGLOBALCONFIGMSG_FULL_NAME = 'org.zstack.core.config.APIQueryGlobalConfigMsg'
class APIQueryGlobalConfigMsg(APIQueryMessage):
    FULL_NAME='org.zstack.core.config.APIQueryGlobalConfigMsg'
    def __init__(self):
        super(APIQueryGlobalConfigMsg, self).__init__()


APIGETGLOBALCONFIGMSG_FULL_NAME = 'org.zstack.core.config.APIGetGlobalConfigMsg'
class APIGetGlobalConfigMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.core.config.APIGetGlobalConfigMsg'
    def __init__(self):
        super(APIGetGlobalConfigMsg, self).__init__()
        #mandatory field
        self.category = NotNoneField()
        #mandatory field
        self.name = NotNoneField()


MESSAGE_FULL_NAME = 'org.zstack.header.message.Message'
class Message(object):
    def __init__(self):
        pass


MESSAGEREPLY_FULL_NAME = 'org.zstack.header.message.MessageReply'
class MessageReply(Message):
    FULL_NAME='org.zstack.header.message.MessageReply'
    def __init__(self):
        super(MessageReply, self).__init__()
        self.success = None
        self.error = None


APIREPLY_FULL_NAME = 'org.zstack.header.message.APIReply'
class APIReply(MessageReply):
    FULL_NAME='org.zstack.header.message.APIReply'
    def __init__(self):
        super(APIReply, self).__init__()


APIGETGLOBALCONFIGREPLY_FULL_NAME = 'org.zstack.core.config.APIGetGlobalConfigReply'
class APIGetGlobalConfigReply(APIReply):
    FULL_NAME='org.zstack.core.config.APIGetGlobalConfigReply'
    def __init__(self):
        super(APIGetGlobalConfigReply, self).__init__()
        self.inventory = None


APIQUERYREPLY_FULL_NAME = 'org.zstack.header.query.APIQueryReply'
class APIQueryReply(APIReply):
    FULL_NAME='org.zstack.header.query.APIQueryReply'
    def __init__(self):
        super(APIQueryReply, self).__init__()
        self.total = None


APIQUERYGLOBALCONFIGREPLY_FULL_NAME = 'org.zstack.core.config.APIQueryGlobalConfigReply'
class APIQueryGlobalConfigReply(APIQueryReply):
    FULL_NAME='org.zstack.core.config.APIQueryGlobalConfigReply'
    def __init__(self):
        super(APIQueryGlobalConfigReply, self).__init__()
        self.inventories = OptionalList()


APILISTGLOBALCONFIGREPLY_FULL_NAME = 'org.zstack.core.config.APIListGlobalConfigReply'
class APIListGlobalConfigReply(APIReply):
    FULL_NAME='org.zstack.core.config.APIListGlobalConfigReply'
    def __init__(self):
        super(APIListGlobalConfigReply, self).__init__()
        self.inventories = None


APIUPDATEGLOBALCONFIGMSG_FULL_NAME = 'org.zstack.core.config.APIUpdateGlobalConfigMsg'
class APIUpdateGlobalConfigMsg(APIMessage):
    FULL_NAME='org.zstack.core.config.APIUpdateGlobalConfigMsg'
    def __init__(self):
        super(APIUpdateGlobalConfigMsg, self).__init__()
        #mandatory field
        self.category = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.value = None


APIGENERATEINVENTORYQUERYDETAILSMSG_FULL_NAME = 'org.zstack.header.query.APIGenerateInventoryQueryDetailsMsg'
class APIGenerateInventoryQueryDetailsMsg(APIMessage):
    FULL_NAME='org.zstack.header.query.APIGenerateInventoryQueryDetailsMsg'
    def __init__(self):
        super(APIGenerateInventoryQueryDetailsMsg, self).__init__()
        self.outputDir = None
        self.basePackageNames = OptionalList()


APIGENERATEQUERYABLEFIELDSMSG_FULL_NAME = 'org.zstack.header.query.APIGenerateQueryableFieldsMsg'
class APIGenerateQueryableFieldsMsg(APIMessage):
    FULL_NAME='org.zstack.header.query.APIGenerateQueryableFieldsMsg'
    def __init__(self):
        super(APIGenerateQueryableFieldsMsg, self).__init__()
        self.PYTHON_FORMAT = None
        self.format = None
        self.outputFolder = None


APIGETCPUMEMORYCAPACITYREPLY_FULL_NAME = 'org.zstack.header.allocator.APIGetCpuMemoryCapacityReply'
class APIGetCpuMemoryCapacityReply(APIReply):
    FULL_NAME='org.zstack.header.allocator.APIGetCpuMemoryCapacityReply'
    def __init__(self):
        super(APIGetCpuMemoryCapacityReply, self).__init__()
        self.totalCpu = None
        self.availableCpu = None
        self.totalMemory = None
        self.availableMemory = None


APIGETHOSTALLOCATORSTRATEGIESMSG_FULL_NAME = 'org.zstack.header.allocator.APIGetHostAllocatorStrategiesMsg'
class APIGetHostAllocatorStrategiesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.allocator.APIGetHostAllocatorStrategiesMsg'
    def __init__(self):
        super(APIGetHostAllocatorStrategiesMsg, self).__init__()


APIGETCPUMEMORYCAPACITYMSG_FULL_NAME = 'org.zstack.header.allocator.APIGetCpuMemoryCapacityMsg'
class APIGetCpuMemoryCapacityMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.allocator.APIGetCpuMemoryCapacityMsg'
    def __init__(self):
        super(APIGetCpuMemoryCapacityMsg, self).__init__()
        self.zoneUuids = OptionalList()
        self.clusterUuids = OptionalList()
        self.hostUuids = OptionalList()
        self.all = None


APIGETHOSTALLOCATORSTRATEGIESREPLY_FULL_NAME = 'org.zstack.header.allocator.APIGetHostAllocatorStrategiesReply'
class APIGetHostAllocatorStrategiesReply(APIReply):
    FULL_NAME='org.zstack.header.allocator.APIGetHostAllocatorStrategiesReply'
    def __init__(self):
        super(APIGetHostAllocatorStrategiesReply, self).__init__()
        self.hostAllocatorStrategies = OptionalList()


APISEARCHREPLY_FULL_NAME = 'org.zstack.header.search.APISearchReply'
class APISearchReply(APIReply):
    FULL_NAME='org.zstack.header.search.APISearchReply'
    def __init__(self):
        super(APISearchReply, self).__init__()
        self.content = None


APISEARCHVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APISearchVmInstanceReply'
class APISearchVmInstanceReply(APISearchReply):
    FULL_NAME='org.zstack.header.vm.APISearchVmInstanceReply'
    def __init__(self):
        super(APISearchVmInstanceReply, self).__init__()


APIUPDATEVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIUpdateVmInstanceMsg'
class APIUpdateVmInstanceMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIUpdateVmInstanceMsg'
    def __init__(self):
        super(APIUpdateVmInstanceMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        #valid values: [Stopped, Running]
        self.state = None
        self.defaultL3NetworkUuid = None


APIGETVMATTACHABLEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableL3NetworkMsg'
class APIGetVmAttachableL3NetworkMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableL3NetworkMsg'
    def __init__(self):
        super(APIGetVmAttachableL3NetworkMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()


APIGETREPLY_FULL_NAME = 'org.zstack.header.search.APIGetReply'
class APIGetReply(APIReply):
    FULL_NAME='org.zstack.header.search.APIGetReply'
    def __init__(self):
        super(APIGetReply, self).__init__()
        self.inventory = None


APIGETVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmInstanceReply'
class APIGetVmInstanceReply(APIGetReply):
    FULL_NAME='org.zstack.header.vm.APIGetVmInstanceReply'
    def __init__(self):
        super(APIGetVmInstanceReply, self).__init__()


APIGETVMATTACHABLEDATAVOLUMEREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableDataVolumeReply'
class APIGetVmAttachableDataVolumeReply(APIReply):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableDataVolumeReply'
    def __init__(self):
        super(APIGetVmAttachableDataVolumeReply, self).__init__()
        self.inventories = OptionalList()


APIGETVMMIGRATIONCANDIDATEHOSTSREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmMigrationCandidateHostsReply'
class APIGetVmMigrationCandidateHostsReply(APIReply):
    FULL_NAME='org.zstack.header.vm.APIGetVmMigrationCandidateHostsReply'
    def __init__(self):
        super(APIGetVmMigrationCandidateHostsReply, self).__init__()
        self.inventories = OptionalList()


APIMIGRATEVMMSG_FULL_NAME = 'org.zstack.header.vm.APIMigrateVmMsg'
class APIMigrateVmMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIMigrateVmMsg'
    def __init__(self):
        super(APIMigrateVmMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.hostUuid = None


APISTOPVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIStopVmInstanceMsg'
class APIStopVmInstanceMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIStopVmInstanceMsg'
    def __init__(self):
        super(APIStopVmInstanceMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APILISTVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIListVmInstanceReply'
class APIListVmInstanceReply(APIReply):
    FULL_NAME='org.zstack.header.vm.APIListVmInstanceReply'
    def __init__(self):
        super(APIListVmInstanceReply, self).__init__()
        self.inventories = OptionalList()


APICHANGEINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.vm.APIChangeInstanceOfferingMsg'
class APIChangeInstanceOfferingMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIChangeInstanceOfferingMsg'
    def __init__(self):
        super(APIChangeInstanceOfferingMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.instanceOfferingUuid = NotNoneField()


APIGETVMATTACHABLEDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableDataVolumeMsg'
class APIGetVmAttachableDataVolumeMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableDataVolumeMsg'
    def __init__(self):
        super(APIGetVmAttachableDataVolumeMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()


APIQUERYVMNICMSG_FULL_NAME = 'org.zstack.header.vm.APIQueryVmNicMsg'
class APIQueryVmNicMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.vm.APIQueryVmNicMsg'
    def __init__(self):
        super(APIQueryVmNicMsg, self).__init__()


APILISTVMNICREPLY_FULL_NAME = 'org.zstack.header.vm.APIListVmNicReply'
class APIListVmNicReply(APIReply):
    FULL_NAME='org.zstack.header.vm.APIListVmNicReply'
    def __init__(self):
        super(APIListVmNicReply, self).__init__()
        self.inventories = OptionalList()


APIATTACHL3NETWORKTOVMMSG_FULL_NAME = 'org.zstack.header.vm.APIAttachL3NetworkToVmMsg'
class APIAttachL3NetworkToVmMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIAttachL3NetworkToVmMsg'
    def __init__(self):
        super(APIAttachL3NetworkToVmMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()


APIDESTROYVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIDestroyVmInstanceMsg'
class APIDestroyVmInstanceMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.vm.APIDestroyVmInstanceMsg'
    def __init__(self):
        super(APIDestroyVmInstanceMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIGETVMMIGRATIONCANDIDATEHOSTSMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmMigrationCandidateHostsMsg'
class APIGetVmMigrationCandidateHostsMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.vm.APIGetVmMigrationCandidateHostsMsg'
    def __init__(self):
        super(APIGetVmMigrationCandidateHostsMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()


APIQUERYVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIQueryVmInstanceMsg'
class APIQueryVmInstanceMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.vm.APIQueryVmInstanceMsg'
    def __init__(self):
        super(APIQueryVmInstanceMsg, self).__init__()


APIDETACHL3NETWORKFROMVMMSG_FULL_NAME = 'org.zstack.header.vm.APIDetachL3NetworkFromVmMsg'
class APIDetachL3NetworkFromVmMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIDetachL3NetworkFromVmMsg'
    def __init__(self):
        super(APIDetachL3NetworkFromVmMsg, self).__init__()
        #mandatory field
        self.vmNicUuid = NotNoneField()


APIQUERYVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIQueryVmInstanceReply'
class APIQueryVmInstanceReply(APIQueryReply):
    FULL_NAME='org.zstack.header.vm.APIQueryVmInstanceReply'
    def __init__(self):
        super(APIQueryVmInstanceReply, self).__init__()
        self.inventories = OptionalList()


APIREBOOTVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIRebootVmInstanceMsg'
class APIRebootVmInstanceMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIRebootVmInstanceMsg'
    def __init__(self):
        super(APIRebootVmInstanceMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIQUERYVMNICREPLY_FULL_NAME = 'org.zstack.header.vm.APIQueryVmNicReply'
class APIQueryVmNicReply(APIQueryReply):
    FULL_NAME='org.zstack.header.vm.APIQueryVmNicReply'
    def __init__(self):
        super(APIQueryVmNicReply, self).__init__()
        self.inventories = OptionalList()


APIGETVMATTACHABLEL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableL3NetworkReply'
class APIGetVmAttachableL3NetworkReply(APIReply):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableL3NetworkReply'
    def __init__(self):
        super(APIGetVmAttachableL3NetworkReply, self).__init__()
        self.inventories = OptionalList()


APICREATEMESSAGE_FULL_NAME = 'org.zstack.header.message.APICreateMessage'
class APICreateMessage(APIMessage):
    FULL_NAME='org.zstack.header.message.APICreateMessage'
    def __init__(self):
        super(APICreateMessage, self).__init__()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()


APICREATEVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APICreateVmInstanceMsg'
class APICreateVmInstanceMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.vm.APICreateVmInstanceMsg'
    def __init__(self):
        super(APICreateVmInstanceMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.instanceOfferingUuid = NotNoneField()
        #mandatory field
        self.imageUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuids = NotNoneList()
        #valid values: [UserVm, ApplianceVm]
        self.type = None
        self.rootDiskOfferingUuid = None
        self.dataDiskOfferingUuids = OptionalList()
        self.zoneUuid = None
        self.clusterUuid = None
        self.hostUuid = None
        self.description = None
        self.defaultL3NetworkUuid = None


APISTARTVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIStartVmInstanceMsg'
class APIStartVmInstanceMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIStartVmInstanceMsg'
    def __init__(self):
        super(APIStartVmInstanceMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APICHANGEIMAGESTATEMSG_FULL_NAME = 'org.zstack.header.image.APIChangeImageStateMsg'
class APIChangeImageStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.image.APIChangeImageStateMsg'
    def __init__(self):
        super(APIChangeImageStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIUPDATEIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIUpdateImageMsg'
class APIUpdateImageMsg(APIMessage):
    FULL_NAME='org.zstack.header.image.APIUpdateImageMsg'
    def __init__(self):
        super(APIUpdateImageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.guestOsType = None
        #valid values: [RootVolumeTemplate, DataVolumeTemplate, ISO]
        self.mediaType = None
        #valid values: [raw, qcow2, iso]
        self.format = None
        self.system = None
        #valid values: [Linux, Windows, Other, Paravirtualization]
        self.platform = None


APIDELETEIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIDeleteImageMsg'
class APIDeleteImageMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.image.APIDeleteImageMsg'
    def __init__(self):
        super(APIDeleteImageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.backupStorageUuids = OptionalList()


APIGETIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIGetImageReply'
class APIGetImageReply(APIGetReply):
    FULL_NAME='org.zstack.header.image.APIGetImageReply'
    def __init__(self):
        super(APIGetImageReply, self).__init__()


APIQUERYIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIQueryImageReply'
class APIQueryImageReply(APIQueryReply):
    FULL_NAME='org.zstack.header.image.APIQueryImageReply'
    def __init__(self):
        super(APIQueryImageReply, self).__init__()
        self.inventories = OptionalList()


APILISTIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIListImageReply'
class APIListImageReply(APIReply):
    FULL_NAME='org.zstack.header.image.APIListImageReply'
    def __init__(self):
        super(APIListImageReply, self).__init__()
        self.inventories = OptionalList()


APICREATEDATAVOLUMETEMPLATEFROMVOLUMEMSG_FULL_NAME = 'org.zstack.header.image.APICreateDataVolumeTemplateFromVolumeMsg'
class APICreateDataVolumeTemplateFromVolumeMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.image.APICreateDataVolumeTemplateFromVolumeMsg'
    def __init__(self):
        super(APICreateDataVolumeTemplateFromVolumeMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.volumeUuid = NotNoneField()
        self.backupStorageUuids = OptionalList()


APICREATEROOTVOLUMETEMPLATEFROMROOTVOLUMEMSG_FULL_NAME = 'org.zstack.header.image.APICreateRootVolumeTemplateFromRootVolumeMsg'
class APICreateRootVolumeTemplateFromRootVolumeMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.image.APICreateRootVolumeTemplateFromRootVolumeMsg'
    def __init__(self):
        super(APICreateRootVolumeTemplateFromRootVolumeMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.guestOsType = None
        self.backupStorageUuids = OptionalList()
        #mandatory field
        self.rootVolumeUuid = NotNoneField()
        #valid values: [Linux, Windows, Other, Paravirtualization]
        self.platform = None
        self.system = None


APISEARCHIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APISearchImageReply'
class APISearchImageReply(APISearchReply):
    FULL_NAME='org.zstack.header.image.APISearchImageReply'
    def __init__(self):
        super(APISearchImageReply, self).__init__()


APIQUERYIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIQueryImageMsg'
class APIQueryImageMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.image.APIQueryImageMsg'
    def __init__(self):
        super(APIQueryImageMsg, self).__init__()


APICREATEROOTVOLUMETEMPLATEFROMVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.image.APICreateRootVolumeTemplateFromVolumeSnapshotMsg'
class APICreateRootVolumeTemplateFromVolumeSnapshotMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.image.APICreateRootVolumeTemplateFromVolumeSnapshotMsg'
    def __init__(self):
        super(APICreateRootVolumeTemplateFromVolumeSnapshotMsg, self).__init__()
        #mandatory field
        self.snapshotUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.guestOsType = None
        self.backupStorageUuids = OptionalList()
        #valid values: [Linux, Windows, Other, Paravirtualization]
        self.platform = None
        self.system = None


APIADDIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIAddImageMsg'
class APIAddImageMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.image.APIAddImageMsg'
    def __init__(self):
        super(APIAddImageMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.url = NotNoneField()
        #valid values: [RootVolumeTemplate, ISO, DataVolumeTemplate]
        self.mediaType = None
        self.guestOsType = None
        self.system = None
        #mandatory field
        self.format = NotNoneField()
        #valid values: [Linux, Windows, Other, Paravirtualization]
        self.platform = None
        #mandatory field
        self.backupStorageUuids = NotNoneList()
        self.type = None


APIREQUESTCONSOLEACCESSMSG_FULL_NAME = 'org.zstack.header.console.APIRequestConsoleAccessMsg'
class APIRequestConsoleAccessMsg(APIMessage):
    FULL_NAME='org.zstack.header.console.APIRequestConsoleAccessMsg'
    def __init__(self):
        super(APIRequestConsoleAccessMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()


APIBACKUPDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIBackupDataVolumeMsg'
class APIBackupDataVolumeMsg(APIMessage):
    FULL_NAME='org.zstack.header.volume.APIBackupDataVolumeMsg'
    def __init__(self):
        super(APIBackupDataVolumeMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.backupStorageUuid = None


APIATTACHDATAVOLUMETOVMMSG_FULL_NAME = 'org.zstack.header.volume.APIAttachDataVolumeToVmMsg'
class APIAttachDataVolumeToVmMsg(APIMessage):
    FULL_NAME='org.zstack.header.volume.APIAttachDataVolumeToVmMsg'
    def __init__(self):
        super(APIAttachDataVolumeToVmMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.volumeUuid = NotNoneField()


APIUPDATEVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIUpdateVolumeMsg'
class APIUpdateVolumeMsg(APIMessage):
    FULL_NAME='org.zstack.header.volume.APIUpdateVolumeMsg'
    def __init__(self):
        super(APIUpdateVolumeMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIQUERYVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIQueryVolumeMsg'
class APIQueryVolumeMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.volume.APIQueryVolumeMsg'
    def __init__(self):
        super(APIQueryVolumeMsg, self).__init__()


APICREATEDATAVOLUMEFROMVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.volume.APICreateDataVolumeFromVolumeSnapshotMsg'
class APICreateDataVolumeFromVolumeSnapshotMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.volume.APICreateDataVolumeFromVolumeSnapshotMsg'
    def __init__(self):
        super(APICreateDataVolumeFromVolumeSnapshotMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.volumeSnapshotUuid = NotNoneField()
        self.primaryStorageUuid = None


APICREATEDATAVOLUMEFROMVOLUMETEMPLATEMSG_FULL_NAME = 'org.zstack.header.volume.APICreateDataVolumeFromVolumeTemplateMsg'
class APICreateDataVolumeFromVolumeTemplateMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.volume.APICreateDataVolumeFromVolumeTemplateMsg'
    def __init__(self):
        super(APICreateDataVolumeFromVolumeTemplateMsg, self).__init__()
        #mandatory field
        self.imageUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        self.hostUuid = None


APIGETVOLUMEFORMATREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeFormatReply'
class APIGetVolumeFormatReply(APIReply):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeFormatReply'
    def __init__(self):
        super(APIGetVolumeFormatReply, self).__init__()
        self.formats = OptionalList()


APIDETACHDATAVOLUMEFROMVMMSG_FULL_NAME = 'org.zstack.header.volume.APIDetachDataVolumeFromVmMsg'
class APIDetachDataVolumeFromVmMsg(APIMessage):
    FULL_NAME='org.zstack.header.volume.APIDetachDataVolumeFromVmMsg'
    def __init__(self):
        super(APIDetachDataVolumeFromVmMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIGETDATAVOLUMEATTACHABLEVMREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetDataVolumeAttachableVmReply'
class APIGetDataVolumeAttachableVmReply(APIReply):
    FULL_NAME='org.zstack.header.volume.APIGetDataVolumeAttachableVmReply'
    def __init__(self):
        super(APIGetDataVolumeAttachableVmReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APIQueryVolumeReply'
class APIQueryVolumeReply(APIQueryReply):
    FULL_NAME='org.zstack.header.volume.APIQueryVolumeReply'
    def __init__(self):
        super(APIQueryVolumeReply, self).__init__()
        self.inventories = OptionalList()


APICREATEDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APICreateDataVolumeMsg'
class APICreateDataVolumeMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.volume.APICreateDataVolumeMsg'
    def __init__(self):
        super(APICreateDataVolumeMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.diskOfferingUuid = NotNoneField()


APIGETVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeReply'
class APIGetVolumeReply(APIGetReply):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeReply'
    def __init__(self):
        super(APIGetVolumeReply, self).__init__()


APILISTVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APIListVolumeReply'
class APIListVolumeReply(APIReply):
    FULL_NAME='org.zstack.header.volume.APIListVolumeReply'
    def __init__(self):
        super(APIListVolumeReply, self).__init__()
        self.inventories = OptionalList()


APIGETDATAVOLUMEATTACHABLEVMMSG_FULL_NAME = 'org.zstack.header.volume.APIGetDataVolumeAttachableVmMsg'
class APIGetDataVolumeAttachableVmMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.volume.APIGetDataVolumeAttachableVmMsg'
    def __init__(self):
        super(APIGetDataVolumeAttachableVmMsg, self).__init__()
        #mandatory field
        self.volumeUuid = NotNoneField()


APIGETVOLUMEFORMATMSG_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeFormatMsg'
class APIGetVolumeFormatMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeFormatMsg'
    def __init__(self):
        super(APIGetVolumeFormatMsg, self).__init__()


APISEARCHVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APISearchVolumeReply'
class APISearchVolumeReply(APISearchReply):
    FULL_NAME='org.zstack.header.volume.APISearchVolumeReply'
    def __init__(self):
        super(APISearchVolumeReply, self).__init__()


APIDELETEDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIDeleteDataVolumeMsg'
class APIDeleteDataVolumeMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.volume.APIDeleteDataVolumeMsg'
    def __init__(self):
        super(APIDeleteDataVolumeMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APICREATEVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.volume.APICreateVolumeSnapshotMsg'
class APICreateVolumeSnapshotMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.volume.APICreateVolumeSnapshotMsg'
    def __init__(self):
        super(APICreateVolumeSnapshotMsg, self).__init__()
        #mandatory field
        self.volumeUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None


APICHANGEVOLUMESTATEMSG_FULL_NAME = 'org.zstack.header.volume.APIChangeVolumeStateMsg'
class APIChangeVolumeStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.volume.APIChangeVolumeStateMsg'
    def __init__(self):
        super(APIChangeVolumeStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIISREADYTOGOREPLY_FULL_NAME = 'org.zstack.header.apimediator.APIIsReadyToGoReply'
class APIIsReadyToGoReply(APIReply):
    FULL_NAME='org.zstack.header.apimediator.APIIsReadyToGoReply'
    def __init__(self):
        super(APIIsReadyToGoReply, self).__init__()
        self.managementNodeId = None


APIISREADYTOGOMSG_FULL_NAME = 'org.zstack.header.apimediator.APIIsReadyToGoMsg'
class APIIsReadyToGoMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.apimediator.APIIsReadyToGoMsg'
    def __init__(self):
        super(APIIsReadyToGoMsg, self).__init__()
        self.managementNodeId = None


APIGENERATEAPITYPESCRIPTDEFINITIONMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateApiTypeScriptDefinitionMsg'
class APIGenerateApiTypeScriptDefinitionMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIGenerateApiTypeScriptDefinitionMsg'
    def __init__(self):
        super(APIGenerateApiTypeScriptDefinitionMsg, self).__init__()
        self.outputPath = None


APIDELETEDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIDeleteDiskOfferingMsg'
class APIDeleteDiskOfferingMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.configuration.APIDeleteDiskOfferingMsg'
    def __init__(self):
        super(APIDeleteDiskOfferingMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APISEARCHINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APISearchInstanceOfferingReply'
class APISearchInstanceOfferingReply(APISearchReply):
    FULL_NAME='org.zstack.header.configuration.APISearchInstanceOfferingReply'
    def __init__(self):
        super(APISearchInstanceOfferingReply, self).__init__()


APIGENERATEGROOVYCLASSMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateGroovyClassMsg'
class APIGenerateGroovyClassMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIGenerateGroovyClassMsg'
    def __init__(self):
        super(APIGenerateGroovyClassMsg, self).__init__()
        self.outputPath = None
        self.basePackageNames = OptionalList()


APIQUERYINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIQueryInstanceOfferingMsg'
class APIQueryInstanceOfferingMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.configuration.APIQueryInstanceOfferingMsg'
    def __init__(self):
        super(APIQueryInstanceOfferingMsg, self).__init__()


APIUPDATEINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIUpdateInstanceOfferingMsg'
class APIUpdateInstanceOfferingMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIUpdateInstanceOfferingMsg'
    def __init__(self):
        super(APIUpdateInstanceOfferingMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.description = NotNoneField()


APICREATEINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APICreateInstanceOfferingMsg'
class APICreateInstanceOfferingMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.configuration.APICreateInstanceOfferingMsg'
    def __init__(self):
        super(APICreateInstanceOfferingMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.cpuNum = NotNoneField()
        #mandatory field
        self.cpuSpeed = NotNoneField()
        #mandatory field
        self.memorySize = NotNoneField()
        self.allocatorStrategy = None
        self.sortKey = None
        self.type = None


APIGENERATEAPIJSONTEMPLATEMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateApiJsonTemplateMsg'
class APIGenerateApiJsonTemplateMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIGenerateApiJsonTemplateMsg'
    def __init__(self):
        super(APIGenerateApiJsonTemplateMsg, self).__init__()
        self.exportPath = None
        self.basePackageNames = OptionalList()


APILISTDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIListDiskOfferingReply'
class APIListDiskOfferingReply(APIReply):
    FULL_NAME='org.zstack.header.configuration.APIListDiskOfferingReply'
    def __init__(self):
        super(APIListDiskOfferingReply, self).__init__()
        self.inventories = OptionalList()


APICREATEDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APICreateDiskOfferingMsg'
class APICreateDiskOfferingMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.configuration.APICreateDiskOfferingMsg'
    def __init__(self):
        super(APICreateDiskOfferingMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.diskSize = NotNoneField()
        self.sortKey = None
        self.allocationStrategy = None
        #valid values: [zstack]
        self.type = None


APILISTINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIListInstanceOfferingReply'
class APIListInstanceOfferingReply(APIReply):
    FULL_NAME='org.zstack.header.configuration.APIListInstanceOfferingReply'
    def __init__(self):
        super(APIListInstanceOfferingReply, self).__init__()
        self.inventories = OptionalList()


APIDELETEINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIDeleteInstanceOfferingMsg'
class APIDeleteInstanceOfferingMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.configuration.APIDeleteInstanceOfferingMsg'
    def __init__(self):
        super(APIDeleteInstanceOfferingMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIGENERATESQLVOVIEWMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateSqlVOViewMsg'
class APIGenerateSqlVOViewMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIGenerateSqlVOViewMsg'
    def __init__(self):
        super(APIGenerateSqlVOViewMsg, self).__init__()
        self.basePackageNames = OptionalList()


APIGENERATETESTLINKDOCUMENTMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateTestLinkDocumentMsg'
class APIGenerateTestLinkDocumentMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIGenerateTestLinkDocumentMsg'
    def __init__(self):
        super(APIGenerateTestLinkDocumentMsg, self).__init__()
        self.outputDir = None


APISEARCHDNSREPLY_FULL_NAME = 'org.zstack.header.configuration.APISearchDnsReply'
class APISearchDnsReply(APISearchReply):
    FULL_NAME='org.zstack.header.configuration.APISearchDnsReply'
    def __init__(self):
        super(APISearchDnsReply, self).__init__()


APIGETINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIGetInstanceOfferingReply'
class APIGetInstanceOfferingReply(APIGetReply):
    FULL_NAME='org.zstack.header.configuration.APIGetInstanceOfferingReply'
    def __init__(self):
        super(APIGetInstanceOfferingReply, self).__init__()


APIQUERYDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIQueryDiskOfferingReply'
class APIQueryDiskOfferingReply(APIQueryReply):
    FULL_NAME='org.zstack.header.configuration.APIQueryDiskOfferingReply'
    def __init__(self):
        super(APIQueryDiskOfferingReply, self).__init__()
        self.inventories = OptionalList()


APICHANGEINSTANCEOFFERINGSTATEMSG_FULL_NAME = 'org.zstack.header.configuration.APIChangeInstanceOfferingStateMsg'
class APIChangeInstanceOfferingStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIChangeInstanceOfferingStateMsg'
    def __init__(self):
        super(APIChangeInstanceOfferingStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIGENERATESQLINDEXMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateSqlIndexMsg'
class APIGenerateSqlIndexMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIGenerateSqlIndexMsg'
    def __init__(self):
        super(APIGenerateSqlIndexMsg, self).__init__()
        self.outputPath = None
        self.basePackageNames = OptionalList()


APIQUERYDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIQueryDiskOfferingMsg'
class APIQueryDiskOfferingMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.configuration.APIQueryDiskOfferingMsg'
    def __init__(self):
        super(APIQueryDiskOfferingMsg, self).__init__()


APISEARCHDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APISearchDiskOfferingReply'
class APISearchDiskOfferingReply(APISearchReply):
    FULL_NAME='org.zstack.header.configuration.APISearchDiskOfferingReply'
    def __init__(self):
        super(APISearchDiskOfferingReply, self).__init__()


APIGENERATESQLFOREIGNKEYMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateSqlForeignKeyMsg'
class APIGenerateSqlForeignKeyMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIGenerateSqlForeignKeyMsg'
    def __init__(self):
        super(APIGenerateSqlForeignKeyMsg, self).__init__()
        self.outputPath = None
        self.basePackageNames = OptionalList()


APIUPDATEDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIUpdateDiskOfferingMsg'
class APIUpdateDiskOfferingMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIUpdateDiskOfferingMsg'
    def __init__(self):
        super(APIUpdateDiskOfferingMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APICHANGEDISKOFFERINGSTATEMSG_FULL_NAME = 'org.zstack.header.configuration.APIChangeDiskOfferingStateMsg'
class APIChangeDiskOfferingStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIChangeDiskOfferingStateMsg'
    def __init__(self):
        super(APIChangeDiskOfferingStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIGETDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIGetDiskOfferingReply'
class APIGetDiskOfferingReply(APIGetReply):
    FULL_NAME='org.zstack.header.configuration.APIGetDiskOfferingReply'
    def __init__(self):
        super(APIGetDiskOfferingReply, self).__init__()


APIQUERYINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIQueryInstanceOfferingReply'
class APIQueryInstanceOfferingReply(APIQueryReply):
    FULL_NAME='org.zstack.header.configuration.APIQueryInstanceOfferingReply'
    def __init__(self):
        super(APIQueryInstanceOfferingReply, self).__init__()
        self.inventories = OptionalList()


APILISTPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIListPrimaryStorageReply'
class APIListPrimaryStorageReply(APIReply):
    FULL_NAME='org.zstack.header.storage.primary.APIListPrimaryStorageReply'
    def __init__(self):
        super(APIListPrimaryStorageReply, self).__init__()
        self.inventories = OptionalList()


APIGETPRIMARYSTORAGETYPESMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageTypesMsg'
class APIGetPrimaryStorageTypesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageTypesMsg'
    def __init__(self):
        super(APIGetPrimaryStorageTypesMsg, self).__init__()


APIGETPRIMARYSTORAGETYPESREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageTypesReply'
class APIGetPrimaryStorageTypesReply(APIReply):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageTypesReply'
    def __init__(self):
        super(APIGetPrimaryStorageTypesReply, self).__init__()
        self.primaryStorageTypes = OptionalList()


APIATTACHPRIMARYSTORAGETOCLUSTERMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIAttachPrimaryStorageToClusterMsg'
class APIAttachPrimaryStorageToClusterMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIAttachPrimaryStorageToClusterMsg'
    def __init__(self):
        super(APIAttachPrimaryStorageToClusterMsg, self).__init__()
        #mandatory field
        self.clusterUuid = NotNoneField()
        #mandatory field
        self.primaryStorageUuid = NotNoneField()


CREATETEMPLATEFROMVOLUMEONPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.CreateTemplateFromVolumeOnPrimaryStorageReply'
class CreateTemplateFromVolumeOnPrimaryStorageReply(APIReply):
    FULL_NAME='org.zstack.header.storage.primary.CreateTemplateFromVolumeOnPrimaryStorageReply'
    def __init__(self):
        super(CreateTemplateFromVolumeOnPrimaryStorageReply, self).__init__()
        self.templateBackupStorageInstallPath = None
        self.format = None


APIGETPRIMARYSTORAGECAPACITYMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageCapacityMsg'
class APIGetPrimaryStorageCapacityMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageCapacityMsg'
    def __init__(self):
        super(APIGetPrimaryStorageCapacityMsg, self).__init__()
        self.zoneUuids = OptionalList()
        self.clusterUuids = OptionalList()
        self.primaryStorageUuids = OptionalList()
        self.all = None


APIUPDATEPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIUpdatePrimaryStorageMsg'
class APIUpdatePrimaryStorageMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIUpdatePrimaryStorageMsg'
    def __init__(self):
        super(APIUpdatePrimaryStorageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIGETPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageReply'
class APIGetPrimaryStorageReply(APIGetReply):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageReply'
    def __init__(self):
        super(APIGetPrimaryStorageReply, self).__init__()


APISEARCHPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APISearchPrimaryStorageReply'
class APISearchPrimaryStorageReply(APISearchReply):
    FULL_NAME='org.zstack.header.storage.primary.APISearchPrimaryStorageReply'
    def __init__(self):
        super(APISearchPrimaryStorageReply, self).__init__()


APIQUERYPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIQueryPrimaryStorageMsg'
class APIQueryPrimaryStorageMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIQueryPrimaryStorageMsg'
    def __init__(self):
        super(APIQueryPrimaryStorageMsg, self).__init__()


APICHANGEPRIMARYSTORAGESTATEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIChangePrimaryStorageStateMsg'
class APIChangePrimaryStorageStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIChangePrimaryStorageStateMsg'
    def __init__(self):
        super(APIChangePrimaryStorageStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIGETPRIMARYSTORAGEALLOCATORSTRATEGIESREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesReply'
class APIGetPrimaryStorageAllocatorStrategiesReply(APIReply):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesReply'
    def __init__(self):
        super(APIGetPrimaryStorageAllocatorStrategiesReply, self).__init__()
        self.primaryStorageAllocatorStrategies = OptionalList()


APISYNCPRIMARYSTORAGECAPACITYMSG_FULL_NAME = 'org.zstack.header.storage.primary.APISyncPrimaryStorageCapacityMsg'
class APISyncPrimaryStorageCapacityMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.primary.APISyncPrimaryStorageCapacityMsg'
    def __init__(self):
        super(APISyncPrimaryStorageCapacityMsg, self).__init__()
        #mandatory field
        self.primaryStorageUuid = NotNoneField()


APIQUERYPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIQueryPrimaryStorageReply'
class APIQueryPrimaryStorageReply(APIQueryReply):
    FULL_NAME='org.zstack.header.storage.primary.APIQueryPrimaryStorageReply'
    def __init__(self):
        super(APIQueryPrimaryStorageReply, self).__init__()
        self.inventories = OptionalList()


APIDELETEPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIDeletePrimaryStorageMsg'
class APIDeletePrimaryStorageMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIDeletePrimaryStorageMsg'
    def __init__(self):
        super(APIDeletePrimaryStorageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIRECONNECTPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIReconnectPrimaryStorageMsg'
class APIReconnectPrimaryStorageMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIReconnectPrimaryStorageMsg'
    def __init__(self):
        super(APIReconnectPrimaryStorageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIDETACHPRIMARYSTORAGEFROMCLUSTERMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIDetachPrimaryStorageFromClusterMsg'
class APIDetachPrimaryStorageFromClusterMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIDetachPrimaryStorageFromClusterMsg'
    def __init__(self):
        super(APIDetachPrimaryStorageFromClusterMsg, self).__init__()
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()


APIGETPRIMARYSTORAGECAPACITYREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageCapacityReply'
class APIGetPrimaryStorageCapacityReply(APIReply):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageCapacityReply'
    def __init__(self):
        super(APIGetPrimaryStorageCapacityReply, self).__init__()
        self.totalCapacity = None
        self.availableCapacity = None


APIGETPRIMARYSTORAGEALLOCATORSTRATEGIESMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesMsg'
class APIGetPrimaryStorageAllocatorStrategiesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesMsg'
    def __init__(self):
        super(APIGetPrimaryStorageAllocatorStrategiesMsg, self).__init__()


APIQUERYVOLUMESNAPSHOTTREEMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeMsg'
class APIQueryVolumeSnapshotTreeMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeMsg'
    def __init__(self):
        super(APIQueryVolumeSnapshotTreeMsg, self).__init__()


APIDELETEVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotMsg'
class APIDeleteVolumeSnapshotMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotMsg'
    def __init__(self):
        super(APIDeleteVolumeSnapshotMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIQUERYVOLUMESNAPSHOTREPLY_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotReply'
class APIQueryVolumeSnapshotReply(APIQueryReply):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotReply'
    def __init__(self):
        super(APIQueryVolumeSnapshotReply, self).__init__()
        self.inventories = OptionalList()


APIUPDATEVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIUpdateVolumeSnapshotMsg'
class APIUpdateVolumeSnapshotMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.snapshot.APIUpdateVolumeSnapshotMsg'
    def __init__(self):
        super(APIUpdateVolumeSnapshotMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIQUERYVOLUMESNAPSHOTTREEREPLY_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeReply'
class APIQueryVolumeSnapshotTreeReply(APIQueryReply):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeReply'
    def __init__(self):
        super(APIQueryVolumeSnapshotTreeReply, self).__init__()
        self.inventories = OptionalList()


APIDELETEVOLUMESNAPSHOTFROMBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotFromBackupStorageMsg'
class APIDeleteVolumeSnapshotFromBackupStorageMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotFromBackupStorageMsg'
    def __init__(self):
        super(APIDeleteVolumeSnapshotFromBackupStorageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.backupStorageUuids = NotNoneList()


APIQUERYVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotMsg'
class APIQueryVolumeSnapshotMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotMsg'
    def __init__(self):
        super(APIQueryVolumeSnapshotMsg, self).__init__()


APIREVERTVOLUMEFROMSNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIRevertVolumeFromSnapshotMsg'
class APIRevertVolumeFromSnapshotMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.snapshot.APIRevertVolumeFromSnapshotMsg'
    def __init__(self):
        super(APIRevertVolumeFromSnapshotMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIBACKUPVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIBackupVolumeSnapshotMsg'
class APIBackupVolumeSnapshotMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.snapshot.APIBackupVolumeSnapshotMsg'
    def __init__(self):
        super(APIBackupVolumeSnapshotMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.backupStorageUuid = None


APIGETVOLUMESNAPSHOTTREEMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeMsg'
class APIGetVolumeSnapshotTreeMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeMsg'
    def __init__(self):
        super(APIGetVolumeSnapshotTreeMsg, self).__init__()
        self.volumeUuid = None
        self.treeUuid = None


APIGETVOLUMESNAPSHOTTREEREPLY_FULL_NAME = 'org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeReply'
class APIGetVolumeSnapshotTreeReply(APIReply):
    FULL_NAME='org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeReply'
    def __init__(self):
        super(APIGetVolumeSnapshotTreeReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIQueryBackupStorageMsg'
class APIQueryBackupStorageMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIQueryBackupStorageMsg'
    def __init__(self):
        super(APIQueryBackupStorageMsg, self).__init__()


APISEARCHBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APISearchBackupStorageReply'
class APISearchBackupStorageReply(APISearchReply):
    FULL_NAME='org.zstack.header.storage.backup.APISearchBackupStorageReply'
    def __init__(self):
        super(APISearchBackupStorageReply, self).__init__()


APIATTACHBACKUPSTORAGETOZONEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIAttachBackupStorageToZoneMsg'
class APIAttachBackupStorageToZoneMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIAttachBackupStorageToZoneMsg'
    def __init__(self):
        super(APIAttachBackupStorageToZoneMsg, self).__init__()
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.backupStorageUuid = NotNoneField()


APIGETBACKUPSTORAGECAPACITYREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageCapacityReply'
class APIGetBackupStorageCapacityReply(APIReply):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageCapacityReply'
    def __init__(self):
        super(APIGetBackupStorageCapacityReply, self).__init__()
        self.totalCapacity = None
        self.availableCapacity = None


APIGETBACKUPSTORAGETYPESMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageTypesMsg'
class APIGetBackupStorageTypesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageTypesMsg'
    def __init__(self):
        super(APIGetBackupStorageTypesMsg, self).__init__()


APICHANGEBACKUPSTORAGESTATEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIChangeBackupStorageStateMsg'
class APIChangeBackupStorageStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIChangeBackupStorageStateMsg'
    def __init__(self):
        super(APIChangeBackupStorageStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIQUERYBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIQueryBackupStorageReply'
class APIQueryBackupStorageReply(APIQueryReply):
    FULL_NAME='org.zstack.header.storage.backup.APIQueryBackupStorageReply'
    def __init__(self):
        super(APIQueryBackupStorageReply, self).__init__()
        self.inventories = OptionalList()


APIGETBACKUPSTORAGETYPESREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageTypesReply'
class APIGetBackupStorageTypesReply(APIReply):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageTypesReply'
    def __init__(self):
        super(APIGetBackupStorageTypesReply, self).__init__()
        self.backupStorageTypes = OptionalList()


APISCANBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIScanBackupStorageMsg'
class APIScanBackupStorageMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIScanBackupStorageMsg'
    def __init__(self):
        super(APIScanBackupStorageMsg, self).__init__()
        self.backupStorageUuid = None


APIGETBACKUPSTORAGECAPACITYMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageCapacityMsg'
class APIGetBackupStorageCapacityMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageCapacityMsg'
    def __init__(self):
        super(APIGetBackupStorageCapacityMsg, self).__init__()
        self.zoneUuids = OptionalList()
        self.backupStorageUuids = OptionalList()
        self.all = None


APIDETACHBACKUPSTORAGEFROMZONEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIDetachBackupStorageFromZoneMsg'
class APIDetachBackupStorageFromZoneMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIDetachBackupStorageFromZoneMsg'
    def __init__(self):
        super(APIDetachBackupStorageFromZoneMsg, self).__init__()
        #mandatory field
        self.backupStorageUuid = NotNoneField()
        #mandatory field
        self.zoneUuid = NotNoneField()


APIUPDATEBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIUpdateBackupStorageMsg'
class APIUpdateBackupStorageMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIUpdateBackupStorageMsg'
    def __init__(self):
        super(APIUpdateBackupStorageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIGETBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageReply'
class APIGetBackupStorageReply(APIGetReply):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageReply'
    def __init__(self):
        super(APIGetBackupStorageReply, self).__init__()


APILISTBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIListBackupStorageReply'
class APIListBackupStorageReply(APIReply):
    FULL_NAME='org.zstack.header.storage.backup.APIListBackupStorageReply'
    def __init__(self):
        super(APIListBackupStorageReply, self).__init__()
        self.inventories = OptionalList()


APIDELETEBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIDeleteBackupStorageMsg'
class APIDeleteBackupStorageMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIDeleteBackupStorageMsg'
    def __init__(self):
        super(APIDeleteBackupStorageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIADDDNSTOL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIAddDnsToL3NetworkMsg'
class APIAddDnsToL3NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.l3.APIAddDnsToL3NetworkMsg'
    def __init__(self):
        super(APIAddDnsToL3NetworkMsg, self).__init__()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.dns = NotNoneField()


APICREATEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APICreateL3NetworkMsg'
class APICreateL3NetworkMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.network.l3.APICreateL3NetworkMsg'
    def __init__(self):
        super(APICreateL3NetworkMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        self.system = None
        self.dnsDomain = None


APILISTIPRANGEREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIListIpRangeReply'
class APIListIpRangeReply(APIReply):
    FULL_NAME='org.zstack.header.network.l3.APIListIpRangeReply'
    def __init__(self):
        super(APIListIpRangeReply, self).__init__()
        self.inventories = OptionalList()


APIGETFREEIPMSG_FULL_NAME = 'org.zstack.header.network.l3.APIGetFreeIpMsg'
class APIGetFreeIpMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.l3.APIGetFreeIpMsg'
    def __init__(self):
        super(APIGetFreeIpMsg, self).__init__()
        self.l3NetworkUuid = None
        self.ipRangeUuid = None
        self.limit = None


APISEARCHL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APISearchL3NetworkReply'
class APISearchL3NetworkReply(APISearchReply):
    FULL_NAME='org.zstack.header.network.l3.APISearchL3NetworkReply'
    def __init__(self):
        super(APISearchL3NetworkReply, self).__init__()


APIUPDATEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIUpdateL3NetworkMsg'
class APIUpdateL3NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.l3.APIUpdateL3NetworkMsg'
    def __init__(self):
        super(APIUpdateL3NetworkMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.system = None


APIGETL3NETWORKTYPESREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetL3NetworkTypesReply'
class APIGetL3NetworkTypesReply(APIReply):
    FULL_NAME='org.zstack.header.network.l3.APIGetL3NetworkTypesReply'
    def __init__(self):
        super(APIGetL3NetworkTypesReply, self).__init__()
        self.l3NetworkTypes = OptionalList()


APIDELETEIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIDeleteIpRangeMsg'
class APIDeleteIpRangeMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.network.l3.APIDeleteIpRangeMsg'
    def __init__(self):
        super(APIDeleteIpRangeMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APICHANGEL3NETWORKSTATEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIChangeL3NetworkStateMsg'
class APIChangeL3NetworkStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.l3.APIChangeL3NetworkStateMsg'
    def __init__(self):
        super(APIChangeL3NetworkStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIGETL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetL3NetworkReply'
class APIGetL3NetworkReply(APIGetReply):
    FULL_NAME='org.zstack.header.network.l3.APIGetL3NetworkReply'
    def __init__(self):
        super(APIGetL3NetworkReply, self).__init__()


APIGETIPADDRESSCAPACITYREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetIpAddressCapacityReply'
class APIGetIpAddressCapacityReply(APIReply):
    FULL_NAME='org.zstack.header.network.l3.APIGetIpAddressCapacityReply'
    def __init__(self):
        super(APIGetIpAddressCapacityReply, self).__init__()
        self.totalCapacity = None
        self.availableCapacity = None


APIADDIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIAddIpRangeMsg'
class APIAddIpRangeMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.network.l3.APIAddIpRangeMsg'
    def __init__(self):
        super(APIAddIpRangeMsg, self).__init__()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.startIp = NotNoneField()
        #mandatory field
        self.endIp = NotNoneField()
        #mandatory field
        self.netmask = NotNoneField()
        #mandatory field
        self.gateway = NotNoneField()


APIGETL3NETWORKTYPESMSG_FULL_NAME = 'org.zstack.header.network.l3.APIGetL3NetworkTypesMsg'
class APIGetL3NetworkTypesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.network.l3.APIGetL3NetworkTypesMsg'
    def __init__(self):
        super(APIGetL3NetworkTypesMsg, self).__init__()


APIADDIPRANGEBYNETWORKCIDRMSG_FULL_NAME = 'org.zstack.header.network.l3.APIAddIpRangeByNetworkCidrMsg'
class APIAddIpRangeByNetworkCidrMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.network.l3.APIAddIpRangeByNetworkCidrMsg'
    def __init__(self):
        super(APIAddIpRangeByNetworkCidrMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.networkCidr = NotNoneField()


APIQUERYL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIQueryL3NetworkReply'
class APIQueryL3NetworkReply(APIQueryReply):
    FULL_NAME='org.zstack.header.network.l3.APIQueryL3NetworkReply'
    def __init__(self):
        super(APIQueryL3NetworkReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIQueryIpRangeMsg'
class APIQueryIpRangeMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.l3.APIQueryIpRangeMsg'
    def __init__(self):
        super(APIQueryIpRangeMsg, self).__init__()


APIGETFREEIPREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetFreeIpReply'
class APIGetFreeIpReply(APIReply):
    FULL_NAME='org.zstack.header.network.l3.APIGetFreeIpReply'
    def __init__(self):
        super(APIGetFreeIpReply, self).__init__()
        self.inventories = OptionalList()


APIREMOVEDNSFROML3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIRemoveDnsFromL3NetworkMsg'
class APIRemoveDnsFromL3NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.l3.APIRemoveDnsFromL3NetworkMsg'
    def __init__(self):
        super(APIRemoveDnsFromL3NetworkMsg, self).__init__()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.dns = NotNoneField()


APIQUERYIPRANGEREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIQueryIpRangeReply'
class APIQueryIpRangeReply(APIQueryReply):
    FULL_NAME='org.zstack.header.network.l3.APIQueryIpRangeReply'
    def __init__(self):
        super(APIQueryIpRangeReply, self).__init__()
        self.inventories = OptionalList()


APILISTL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIListL3NetworkReply'
class APIListL3NetworkReply(APIReply):
    FULL_NAME='org.zstack.header.network.l3.APIListL3NetworkReply'
    def __init__(self):
        super(APIListL3NetworkReply, self).__init__()
        self.inventories = OptionalList()


APIGETIPADDRESSCAPACITYMSG_FULL_NAME = 'org.zstack.header.network.l3.APIGetIpAddressCapacityMsg'
class APIGetIpAddressCapacityMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.network.l3.APIGetIpAddressCapacityMsg'
    def __init__(self):
        super(APIGetIpAddressCapacityMsg, self).__init__()
        self.zoneUuids = OptionalList()
        self.l3NetworkUuids = OptionalList()
        self.ipRangeUuids = OptionalList()
        self.all = None


APIDELETEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIDeleteL3NetworkMsg'
class APIDeleteL3NetworkMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.network.l3.APIDeleteL3NetworkMsg'
    def __init__(self):
        super(APIDeleteL3NetworkMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIUPDATEIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIUpdateIpRangeMsg'
class APIUpdateIpRangeMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.l3.APIUpdateIpRangeMsg'
    def __init__(self):
        super(APIUpdateIpRangeMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIQUERYL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIQueryL3NetworkMsg'
class APIQueryL3NetworkMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.l3.APIQueryL3NetworkMsg'
    def __init__(self):
        super(APIQueryL3NetworkMsg, self).__init__()


APIQUERYNETWORKSERVICEL3NETWORKREFREPLY_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceL3NetworkRefReply'
class APIQueryNetworkServiceL3NetworkRefReply(APIQueryReply):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceL3NetworkRefReply'
    def __init__(self):
        super(APIQueryNetworkServiceL3NetworkRefReply, self).__init__()
        self.inventories = OptionalList()


APIATTACHNETWORKSERVICETOL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.service.APIAttachNetworkServiceToL3NetworkMsg'
class APIAttachNetworkServiceToL3NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.service.APIAttachNetworkServiceToL3NetworkMsg'
    def __init__(self):
        super(APIAttachNetworkServiceToL3NetworkMsg, self).__init__()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.networkServices = NotNoneMap()


APIADDNETWORKSERVICEPROVIDERMSG_FULL_NAME = 'org.zstack.header.network.service.APIAddNetworkServiceProviderMsg'
class APIAddNetworkServiceProviderMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.service.APIAddNetworkServiceProviderMsg'
    def __init__(self):
        super(APIAddNetworkServiceProviderMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.description = NotNoneField()
        #mandatory field
        self.networkServiceTypes = NotNoneList()
        #mandatory field
        self.type = NotNoneField()


APISEARCHNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APISearchNetworkServiceProviderReply'
class APISearchNetworkServiceProviderReply(APISearchReply):
    FULL_NAME='org.zstack.header.network.service.APISearchNetworkServiceProviderReply'
    def __init__(self):
        super(APISearchNetworkServiceProviderReply, self).__init__()


APIQUERYNETWORKSERVICEL3NETWORKREFMSG_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceL3NetworkRefMsg'
class APIQueryNetworkServiceL3NetworkRefMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceL3NetworkRefMsg'
    def __init__(self):
        super(APIQueryNetworkServiceL3NetworkRefMsg, self).__init__()


APIATTACHNETWORKSERVICEPROVIDERTOL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.service.APIAttachNetworkServiceProviderToL2NetworkMsg'
class APIAttachNetworkServiceProviderToL2NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.service.APIAttachNetworkServiceProviderToL2NetworkMsg'
    def __init__(self):
        super(APIAttachNetworkServiceProviderToL2NetworkMsg, self).__init__()
        #mandatory field
        self.networkServiceProviderUuid = NotNoneField()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()


APIGETNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APIGetNetworkServiceProviderReply'
class APIGetNetworkServiceProviderReply(APIGetReply):
    FULL_NAME='org.zstack.header.network.service.APIGetNetworkServiceProviderReply'
    def __init__(self):
        super(APIGetNetworkServiceProviderReply, self).__init__()


APIDETACHNETWORKSERVICEPROVIDERFROML2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.service.APIDetachNetworkServiceProviderFromL2NetworkMsg'
class APIDetachNetworkServiceProviderFromL2NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.service.APIDetachNetworkServiceProviderFromL2NetworkMsg'
    def __init__(self):
        super(APIDetachNetworkServiceProviderFromL2NetworkMsg, self).__init__()
        #mandatory field
        self.networkServiceProviderUuid = NotNoneField()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()


APIQUERYNETWORKSERVICEPROVIDERMSG_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceProviderMsg'
class APIQueryNetworkServiceProviderMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceProviderMsg'
    def __init__(self):
        super(APIQueryNetworkServiceProviderMsg, self).__init__()


APIGETNETWORKSERVICETYPESMSG_FULL_NAME = 'org.zstack.header.network.service.APIGetNetworkServiceTypesMsg'
class APIGetNetworkServiceTypesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.network.service.APIGetNetworkServiceTypesMsg'
    def __init__(self):
        super(APIGetNetworkServiceTypesMsg, self).__init__()


APIGETNETWORKSERVICETYPESREPLY_FULL_NAME = 'org.zstack.header.network.service.APIGetNetworkServiceTypesReply'
class APIGetNetworkServiceTypesReply(APIReply):
    FULL_NAME='org.zstack.header.network.service.APIGetNetworkServiceTypesReply'
    def __init__(self):
        super(APIGetNetworkServiceTypesReply, self).__init__()
        self.serviceAndProviderTypes = OptionalMap()


APILISTNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APIListNetworkServiceProviderReply'
class APIListNetworkServiceProviderReply(APIReply):
    FULL_NAME='org.zstack.header.network.service.APIListNetworkServiceProviderReply'
    def __init__(self):
        super(APIListNetworkServiceProviderReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceProviderReply'
class APIQueryNetworkServiceProviderReply(APIQueryReply):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceProviderReply'
    def __init__(self):
        super(APIQueryNetworkServiceProviderReply, self).__init__()
        self.inventories = OptionalList()


APIATTACHL2NETWORKTOCLUSTERMSG_FULL_NAME = 'org.zstack.header.network.l2.APIAttachL2NetworkToClusterMsg'
class APIAttachL2NetworkToClusterMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.l2.APIAttachL2NetworkToClusterMsg'
    def __init__(self):
        super(APIAttachL2NetworkToClusterMsg, self).__init__()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()


APIQUERYL2VLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APIQueryL2VlanNetworkMsg'
class APIQueryL2VlanNetworkMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.l2.APIQueryL2VlanNetworkMsg'
    def __init__(self):
        super(APIQueryL2VlanNetworkMsg, self).__init__()


APIGETL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2VlanNetworkReply'
class APIGetL2VlanNetworkReply(APIGetReply):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2VlanNetworkReply'
    def __init__(self):
        super(APIGetL2VlanNetworkReply, self).__init__()


APIGETL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2NetworkReply'
class APIGetL2NetworkReply(APIGetReply):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2NetworkReply'
    def __init__(self):
        super(APIGetL2NetworkReply, self).__init__()


APICREATEL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APICreateL2NetworkMsg'
class APICreateL2NetworkMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.network.l2.APICreateL2NetworkMsg'
    def __init__(self):
        super(APICreateL2NetworkMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.physicalInterface = NotNoneField()
        self.type = None


APICREATEL2VLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APICreateL2VlanNetworkMsg'
class APICreateL2VlanNetworkMsg(APICreateL2NetworkMsg):
    FULL_NAME='org.zstack.header.network.l2.APICreateL2VlanNetworkMsg'
    def __init__(self):
        super(APICreateL2VlanNetworkMsg, self).__init__()
        #mandatory field
        self.vlan = NotNoneField()


APIQUERYL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIQueryL2VlanNetworkReply'
class APIQueryL2VlanNetworkReply(APIQueryReply):
    FULL_NAME='org.zstack.header.network.l2.APIQueryL2VlanNetworkReply'
    def __init__(self):
        super(APIQueryL2VlanNetworkReply, self).__init__()
        self.inventories = OptionalList()


APIDETACHL2NETWORKFROMCLUSTERMSG_FULL_NAME = 'org.zstack.header.network.l2.APIDetachL2NetworkFromClusterMsg'
class APIDetachL2NetworkFromClusterMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.l2.APIDetachL2NetworkFromClusterMsg'
    def __init__(self):
        super(APIDetachL2NetworkFromClusterMsg, self).__init__()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()


APIGETL2NETWORKTYPESREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2NetworkTypesReply'
class APIGetL2NetworkTypesReply(APIReply):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2NetworkTypesReply'
    def __init__(self):
        super(APIGetL2NetworkTypesReply, self).__init__()
        self.l2NetworkTypes = OptionalList()


APILISTL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIListL2VlanNetworkReply'
class APIListL2VlanNetworkReply(APIReply):
    FULL_NAME='org.zstack.header.network.l2.APIListL2VlanNetworkReply'
    def __init__(self):
        super(APIListL2VlanNetworkReply, self).__init__()
        self.inventories = OptionalList()


APIDELETEL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APIDeleteL2NetworkMsg'
class APIDeleteL2NetworkMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.network.l2.APIDeleteL2NetworkMsg'
    def __init__(self):
        super(APIDeleteL2NetworkMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APISEARCHL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APISearchL2VlanNetworkReply'
class APISearchL2VlanNetworkReply(APISearchReply):
    FULL_NAME='org.zstack.header.network.l2.APISearchL2VlanNetworkReply'
    def __init__(self):
        super(APISearchL2VlanNetworkReply, self).__init__()


APIQUERYL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIQueryL2NetworkReply'
class APIQueryL2NetworkReply(APIQueryReply):
    FULL_NAME='org.zstack.header.network.l2.APIQueryL2NetworkReply'
    def __init__(self):
        super(APIQueryL2NetworkReply, self).__init__()
        self.inventories = OptionalList()


APICREATEL2NOVLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APICreateL2NoVlanNetworkMsg'
class APICreateL2NoVlanNetworkMsg(APICreateL2NetworkMsg):
    FULL_NAME='org.zstack.header.network.l2.APICreateL2NoVlanNetworkMsg'
    def __init__(self):
        super(APICreateL2NoVlanNetworkMsg, self).__init__()


APISEARCHL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APISearchL2NetworkReply'
class APISearchL2NetworkReply(APISearchReply):
    FULL_NAME='org.zstack.header.network.l2.APISearchL2NetworkReply'
    def __init__(self):
        super(APISearchL2NetworkReply, self).__init__()


APILISTL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIListL2NetworkReply'
class APIListL2NetworkReply(APIReply):
    FULL_NAME='org.zstack.header.network.l2.APIListL2NetworkReply'
    def __init__(self):
        super(APIListL2NetworkReply, self).__init__()
        self.inventories = OptionalList()


APIUPDATEL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APIUpdateL2NetworkMsg'
class APIUpdateL2NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.l2.APIUpdateL2NetworkMsg'
    def __init__(self):
        super(APIUpdateL2NetworkMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIGETL2NETWORKTYPESMSG_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2NetworkTypesMsg'
class APIGetL2NetworkTypesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2NetworkTypesMsg'
    def __init__(self):
        super(APIGetL2NetworkTypesMsg, self).__init__()


APIQUERYL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APIQueryL2NetworkMsg'
class APIQueryL2NetworkMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.l2.APIQueryL2NetworkMsg'
    def __init__(self):
        super(APIQueryL2NetworkMsg, self).__init__()


APIDELETESEARCHINDEXMSG_FULL_NAME = 'org.zstack.header.search.APIDeleteSearchIndexMsg'
class APIDeleteSearchIndexMsg(APIMessage):
    FULL_NAME='org.zstack.header.search.APIDeleteSearchIndexMsg'
    def __init__(self):
        super(APIDeleteSearchIndexMsg, self).__init__()
        self.indexName = None


APISEARCHGENERATESQLTRIGGERMSG_FULL_NAME = 'org.zstack.header.search.APISearchGenerateSqlTriggerMsg'
class APISearchGenerateSqlTriggerMsg(APIMessage):
    FULL_NAME='org.zstack.header.search.APISearchGenerateSqlTriggerMsg'
    def __init__(self):
        super(APISearchGenerateSqlTriggerMsg, self).__init__()
        self.resultPath = None


APICREATESEARCHINDEXMSG_FULL_NAME = 'org.zstack.header.search.APICreateSearchIndexMsg'
class APICreateSearchIndexMsg(APIMessage):
    FULL_NAME='org.zstack.header.search.APICreateSearchIndexMsg'
    def __init__(self):
        super(APICreateSearchIndexMsg, self).__init__()
        #mandatory field
        self.inventoryNames = NotNoneList()
        self.isRecreate = None


APIQUERYUSERTAGMSG_FULL_NAME = 'org.zstack.header.tag.APIQueryUserTagMsg'
class APIQueryUserTagMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.tag.APIQueryUserTagMsg'
    def __init__(self):
        super(APIQueryUserTagMsg, self).__init__()


APIQUERYSYSTEMTAGMSG_FULL_NAME = 'org.zstack.header.tag.APIQuerySystemTagMsg'
class APIQuerySystemTagMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.tag.APIQuerySystemTagMsg'
    def __init__(self):
        super(APIQuerySystemTagMsg, self).__init__()


APIDELETETAGMSG_FULL_NAME = 'org.zstack.header.tag.APIDeleteTagMsg'
class APIDeleteTagMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.tag.APIDeleteTagMsg'
    def __init__(self):
        super(APIDeleteTagMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIQUERYUSERTAGREPLY_FULL_NAME = 'org.zstack.header.tag.APIQueryUserTagReply'
class APIQueryUserTagReply(APIQueryReply):
    FULL_NAME='org.zstack.header.tag.APIQueryUserTagReply'
    def __init__(self):
        super(APIQueryUserTagReply, self).__init__()
        self.inventories = OptionalList()


APICREATETAGMSG_FULL_NAME = 'org.zstack.header.tag.APICreateTagMsg'
class APICreateTagMsg(APIMessage):
    FULL_NAME='org.zstack.header.tag.APICreateTagMsg'
    def __init__(self):
        super(APICreateTagMsg, self).__init__()
        #mandatory field
        self.resourceType = NotNoneField()
        #mandatory field
        self.resourceUuid = NotNoneField()
        #mandatory field
        self.tag = NotNoneField()


APICREATEUSERTAGMSG_FULL_NAME = 'org.zstack.header.tag.APICreateUserTagMsg'
class APICreateUserTagMsg(APICreateTagMsg):
    FULL_NAME='org.zstack.header.tag.APICreateUserTagMsg'
    def __init__(self):
        super(APICreateUserTagMsg, self).__init__()


APICREATESYSTEMTAGMSG_FULL_NAME = 'org.zstack.header.tag.APICreateSystemTagMsg'
class APICreateSystemTagMsg(APICreateTagMsg):
    FULL_NAME='org.zstack.header.tag.APICreateSystemTagMsg'
    def __init__(self):
        super(APICreateSystemTagMsg, self).__init__()


APIQUERYTAGMSG_FULL_NAME = 'org.zstack.header.tag.APIQueryTagMsg'
class APIQueryTagMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.tag.APIQueryTagMsg'
    def __init__(self):
        super(APIQueryTagMsg, self).__init__()
        self.systemTag = None


APIQUERYSYSTEMTAGREPLY_FULL_NAME = 'org.zstack.header.tag.APIQuerySystemTagReply'
class APIQuerySystemTagReply(APIQueryReply):
    FULL_NAME='org.zstack.header.tag.APIQuerySystemTagReply'
    def __init__(self):
        super(APIQuerySystemTagReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYTAGREPLY_FULL_NAME = 'org.zstack.header.tag.APIQueryTagReply'
class APIQueryTagReply(APIQueryReply):
    FULL_NAME='org.zstack.header.tag.APIQueryTagReply'
    def __init__(self):
        super(APIQueryTagReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYMANAGEMENTNODEREPLY_FULL_NAME = 'org.zstack.header.managementnode.APIQueryManagementNodeReply'
class APIQueryManagementNodeReply(APIQueryReply):
    FULL_NAME='org.zstack.header.managementnode.APIQueryManagementNodeReply'
    def __init__(self):
        super(APIQueryManagementNodeReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYMANAGEMENTNODEMSG_FULL_NAME = 'org.zstack.header.managementnode.APIQueryManagementNodeMsg'
class APIQueryManagementNodeMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.managementnode.APIQueryManagementNodeMsg'
    def __init__(self):
        super(APIQueryManagementNodeMsg, self).__init__()


APILISTMANAGEMENTNODEREPLY_FULL_NAME = 'org.zstack.header.managementnode.APIListManagementNodeReply'
class APIListManagementNodeReply(APIReply):
    FULL_NAME='org.zstack.header.managementnode.APIListManagementNodeReply'
    def __init__(self):
        super(APIListManagementNodeReply, self).__init__()
        self.inventories = OptionalList()


APISEARCHCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APISearchClusterReply'
class APISearchClusterReply(APISearchReply):
    FULL_NAME='org.zstack.header.cluster.APISearchClusterReply'
    def __init__(self):
        super(APISearchClusterReply, self).__init__()


APILISTCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APIListClusterReply'
class APIListClusterReply(APIReply):
    FULL_NAME='org.zstack.header.cluster.APIListClusterReply'
    def __init__(self):
        super(APIListClusterReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYCLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APIQueryClusterMsg'
class APIQueryClusterMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.cluster.APIQueryClusterMsg'
    def __init__(self):
        super(APIQueryClusterMsg, self).__init__()


APIDELETECLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APIDeleteClusterMsg'
class APIDeleteClusterMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.cluster.APIDeleteClusterMsg'
    def __init__(self):
        super(APIDeleteClusterMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIUPDATECLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APIUpdateClusterMsg'
class APIUpdateClusterMsg(APIMessage):
    FULL_NAME='org.zstack.header.cluster.APIUpdateClusterMsg'
    def __init__(self):
        super(APIUpdateClusterMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIGETCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APIGetClusterReply'
class APIGetClusterReply(APIGetReply):
    FULL_NAME='org.zstack.header.cluster.APIGetClusterReply'
    def __init__(self):
        super(APIGetClusterReply, self).__init__()


APICREATECLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APICreateClusterMsg'
class APICreateClusterMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.cluster.APICreateClusterMsg'
    def __init__(self):
        super(APICreateClusterMsg, self).__init__()
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        #valid values: [KVM, Simulator]
        self.hypervisorType = NotNoneField()
        #valid values: [zstack]
        self.type = None


APICHANGECLUSTERSTATEMSG_FULL_NAME = 'org.zstack.header.cluster.APIChangeClusterStateMsg'
class APIChangeClusterStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.cluster.APIChangeClusterStateMsg'
    def __init__(self):
        super(APIChangeClusterStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIQUERYCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APIQueryClusterReply'
class APIQueryClusterReply(APIQueryReply):
    FULL_NAME='org.zstack.header.cluster.APIQueryClusterReply'
    def __init__(self):
        super(APIQueryClusterReply, self).__init__()
        self.inventories = OptionalList()


APILISTUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APIListUserReply'
class APIListUserReply(APIReply):
    FULL_NAME='org.zstack.header.identity.APIListUserReply'
    def __init__(self):
        super(APIListUserReply, self).__init__()
        self.inventories = OptionalList()


APIATTACHPOLICYTOUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIAttachPolicyToUserGroupMsg'
class APIAttachPolicyToUserGroupMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIAttachPolicyToUserGroupMsg'
    def __init__(self):
        super(APIAttachPolicyToUserGroupMsg, self).__init__()
        #mandatory field
        self.policyUuid = NotNoneField()
        #mandatory field
        self.groupUuid = NotNoneField()


APIREMOVEUSERFROMGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIRemoveUserFromGroupMsg'
class APIRemoveUserFromGroupMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIRemoveUserFromGroupMsg'
    def __init__(self):
        super(APIRemoveUserFromGroupMsg, self).__init__()
        #mandatory field
        self.userUuid = NotNoneField()
        #mandatory field
        self.groupUuid = NotNoneField()


APIATTACHPOLICYTOUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIAttachPolicyToUserMsg'
class APIAttachPolicyToUserMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIAttachPolicyToUserMsg'
    def __init__(self):
        super(APIAttachPolicyToUserMsg, self).__init__()
        #mandatory field
        self.userUuid = NotNoneField()
        #mandatory field
        self.policyUuid = NotNoneField()


APIQUERYUSERGROUPREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryUserGroupReply'
class APIQueryUserGroupReply(APIQueryReply):
    FULL_NAME='org.zstack.header.identity.APIQueryUserGroupReply'
    def __init__(self):
        super(APIQueryUserGroupReply, self).__init__()
        self.inventories = OptionalList()


APIRESETUSERPASSWORDMSG_FULL_NAME = 'org.zstack.header.identity.APIResetUserPasswordMsg'
class APIResetUserPasswordMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIResetUserPasswordMsg'
    def __init__(self):
        super(APIResetUserPasswordMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.password = NotNoneField()


APIGETUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetUserReply'
class APIGetUserReply(APIGetReply):
    FULL_NAME='org.zstack.header.identity.APIGetUserReply'
    def __init__(self):
        super(APIGetUserReply, self).__init__()


APIGETACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetAccountReply'
class APIGetAccountReply(APIGetReply):
    FULL_NAME='org.zstack.header.identity.APIGetAccountReply'
    def __init__(self):
        super(APIGetAccountReply, self).__init__()


APIQUERYUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryUserReply'
class APIQueryUserReply(APIQueryReply):
    FULL_NAME='org.zstack.header.identity.APIQueryUserReply'
    def __init__(self):
        super(APIQueryUserReply, self).__init__()
        self.inventories = OptionalList()


APIADDUSERTOGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIAddUserToGroupMsg'
class APIAddUserToGroupMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIAddUserToGroupMsg'
    def __init__(self):
        super(APIAddUserToGroupMsg, self).__init__()
        #mandatory field
        self.userUuid = NotNoneField()
        #mandatory field
        self.groupUuid = NotNoneField()


APIQUERYQUOTAMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryQuotaMsg'
class APIQueryQuotaMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.identity.APIQueryQuotaMsg'
    def __init__(self):
        super(APIQueryQuotaMsg, self).__init__()


APILISTACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIListAccountReply'
class APIListAccountReply(APIReply):
    FULL_NAME='org.zstack.header.identity.APIListAccountReply'
    def __init__(self):
        super(APIListAccountReply, self).__init__()
        self.inventories = OptionalList()


APISEARCHPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchPolicyReply'
class APISearchPolicyReply(APISearchReply):
    FULL_NAME='org.zstack.header.identity.APISearchPolicyReply'
    def __init__(self):
        super(APISearchPolicyReply, self).__init__()


APISHARERESOURCEMSG_FULL_NAME = 'org.zstack.header.identity.APIShareResourceMsg'
class APIShareResourceMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIShareResourceMsg'
    def __init__(self):
        super(APIShareResourceMsg, self).__init__()
        #mandatory field
        self.resourceUuids = NotNoneList()
        self.accountUuids = OptionalList()
        self.toPublic = None


APICREATEACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APICreateAccountMsg'
class APICreateAccountMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.identity.APICreateAccountMsg'
    def __init__(self):
        super(APICreateAccountMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        #valid values: [SystemAdmin, Normal]
        self.type = None


APIDELETEACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APIDeleteAccountMsg'
class APIDeleteAccountMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.identity.APIDeleteAccountMsg'
    def __init__(self):
        super(APIDeleteAccountMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APICREATEUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APICreateUserGroupMsg'
class APICreateUserGroupMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.identity.APICreateUserGroupMsg'
    def __init__(self):
        super(APICreateUserGroupMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None


APIQUERYACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryAccountReply'
class APIQueryAccountReply(APIQueryReply):
    FULL_NAME='org.zstack.header.identity.APIQueryAccountReply'
    def __init__(self):
        super(APIQueryAccountReply, self).__init__()
        self.inventories = OptionalList()


APICREATEUSERMSG_FULL_NAME = 'org.zstack.header.identity.APICreateUserMsg'
class APICreateUserMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.identity.APICreateUserMsg'
    def __init__(self):
        super(APICreateUserMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.password = NotNoneField()


APISESSIONMESSAGE_FULL_NAME = 'org.zstack.header.identity.APISessionMessage'
class APISessionMessage(APISyncCallMessage):
    FULL_NAME='org.zstack.header.identity.APISessionMessage'
    def __init__(self):
        super(APISessionMessage, self).__init__()


APILOGINBYUSERMSG_FULL_NAME = 'org.zstack.header.identity.APILogInByUserMsg'
class APILogInByUserMsg(APISessionMessage):
    FULL_NAME='org.zstack.header.identity.APILogInByUserMsg'
    def __init__(self):
        super(APILogInByUserMsg, self).__init__()
        #mandatory field
        self.accountUuid = NotNoneField()
        #mandatory field
        self.userName = NotNoneField()
        #mandatory field
        self.password = NotNoneField()


APILOGOUTREPLY_FULL_NAME = 'org.zstack.header.identity.APILogOutReply'
class APILogOutReply(APIReply):
    FULL_NAME='org.zstack.header.identity.APILogOutReply'
    def __init__(self):
        super(APILogOutReply, self).__init__()


APISEARCHUSERGROUPREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchUserGroupReply'
class APISearchUserGroupReply(APISearchReply):
    FULL_NAME='org.zstack.header.identity.APISearchUserGroupReply'
    def __init__(self):
        super(APISearchUserGroupReply, self).__init__()


APIDETACHPOLICYFROMUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIDetachPolicyFromUserGroupMsg'
class APIDetachPolicyFromUserGroupMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIDetachPolicyFromUserGroupMsg'
    def __init__(self):
        super(APIDetachPolicyFromUserGroupMsg, self).__init__()
        #mandatory field
        self.policyUuid = NotNoneField()
        #mandatory field
        self.groupUuid = NotNoneField()


APIGETPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetPolicyReply'
class APIGetPolicyReply(APIGetReply):
    FULL_NAME='org.zstack.header.identity.APIGetPolicyReply'
    def __init__(self):
        super(APIGetPolicyReply, self).__init__()


APIUPDATEQUOTAMSG_FULL_NAME = 'org.zstack.header.identity.APIUpdateQuotaMsg'
class APIUpdateQuotaMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIUpdateQuotaMsg'
    def __init__(self):
        super(APIUpdateQuotaMsg, self).__init__()
        #mandatory field
        self.identityUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.value = NotNoneField()


APILOGINREPLY_FULL_NAME = 'org.zstack.header.identity.APILogInReply'
class APILogInReply(APIReply):
    FULL_NAME='org.zstack.header.identity.APILogInReply'
    def __init__(self):
        super(APILogInReply, self).__init__()
        self.inventory = None


APILISTPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APIListPolicyReply'
class APIListPolicyReply(APIReply):
    FULL_NAME='org.zstack.header.identity.APIListPolicyReply'
    def __init__(self):
        super(APIListPolicyReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryAccountMsg'
class APIQueryAccountMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.identity.APIQueryAccountMsg'
    def __init__(self):
        super(APIQueryAccountMsg, self).__init__()


APIQUERYPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryPolicyMsg'
class APIQueryPolicyMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.identity.APIQueryPolicyMsg'
    def __init__(self):
        super(APIQueryPolicyMsg, self).__init__()


APIQUERYUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryUserMsg'
class APIQueryUserMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.identity.APIQueryUserMsg'
    def __init__(self):
        super(APIQueryUserMsg, self).__init__()


APIDELETEPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APIDeletePolicyMsg'
class APIDeletePolicyMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.identity.APIDeletePolicyMsg'
    def __init__(self):
        super(APIDeletePolicyMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIREVOKERESOURCESHARINGMSG_FULL_NAME = 'org.zstack.header.identity.APIRevokeResourceSharingMsg'
class APIRevokeResourceSharingMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIRevokeResourceSharingMsg'
    def __init__(self):
        super(APIRevokeResourceSharingMsg, self).__init__()
        #mandatory field
        self.resourceUuids = NotNoneList()
        self.toPublic = None
        self.accountUuids = OptionalList()
        self.all = None


APIQUERYQUOTAREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryQuotaReply'
class APIQueryQuotaReply(APIQueryReply):
    FULL_NAME='org.zstack.header.identity.APIQueryQuotaReply'
    def __init__(self):
        super(APIQueryQuotaReply, self).__init__()
        self.inventories = OptionalList()


APIGETUSERGROUPREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetUserGroupReply'
class APIGetUserGroupReply(APIGetReply):
    FULL_NAME='org.zstack.header.identity.APIGetUserGroupReply'
    def __init__(self):
        super(APIGetUserGroupReply, self).__init__()


APIRESETACCOUNTPASSWORDMSG_FULL_NAME = 'org.zstack.header.identity.APIResetAccountPasswordMsg'
class APIResetAccountPasswordMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIResetAccountPasswordMsg'
    def __init__(self):
        super(APIResetAccountPasswordMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.password = NotNoneField()


APILOGINBYACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APILogInByAccountMsg'
class APILogInByAccountMsg(APISessionMessage):
    FULL_NAME='org.zstack.header.identity.APILogInByAccountMsg'
    def __init__(self):
        super(APILogInByAccountMsg, self).__init__()
        #mandatory field
        self.accountName = NotNoneField()
        #mandatory field
        self.password = NotNoneField()


APIVALIDATESESSIONMSG_FULL_NAME = 'org.zstack.header.identity.APIValidateSessionMsg'
class APIValidateSessionMsg(APISessionMessage):
    FULL_NAME='org.zstack.header.identity.APIValidateSessionMsg'
    def __init__(self):
        super(APIValidateSessionMsg, self).__init__()
        #mandatory field
        self.sessionUuid = NotNoneField()


APIQUERYPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryPolicyReply'
class APIQueryPolicyReply(APIQueryReply):
    FULL_NAME='org.zstack.header.identity.APIQueryPolicyReply'
    def __init__(self):
        super(APIQueryPolicyReply, self).__init__()
        self.inventories = OptionalList()


APISEARCHACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchAccountReply'
class APISearchAccountReply(APISearchReply):
    FULL_NAME='org.zstack.header.identity.APISearchAccountReply'
    def __init__(self):
        super(APISearchAccountReply, self).__init__()


APIDELETEUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIDeleteUserMsg'
class APIDeleteUserMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.identity.APIDeleteUserMsg'
    def __init__(self):
        super(APIDeleteUserMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APISEARCHUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchUserReply'
class APISearchUserReply(APISearchReply):
    FULL_NAME='org.zstack.header.identity.APISearchUserReply'
    def __init__(self):
        super(APISearchUserReply, self).__init__()


APIDELETEUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIDeleteUserGroupMsg'
class APIDeleteUserGroupMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.identity.APIDeleteUserGroupMsg'
    def __init__(self):
        super(APIDeleteUserGroupMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APILOGOUTMSG_FULL_NAME = 'org.zstack.header.identity.APILogOutMsg'
class APILogOutMsg(APISessionMessage):
    FULL_NAME='org.zstack.header.identity.APILogOutMsg'
    def __init__(self):
        super(APILogOutMsg, self).__init__()
        self.sessionUuid = None


APICREATEPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APICreatePolicyMsg'
class APICreatePolicyMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.identity.APICreatePolicyMsg'
    def __init__(self):
        super(APICreatePolicyMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.statements = NotNoneList()


APIDETACHPOLICYFROMUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIDetachPolicyFromUserMsg'
class APIDetachPolicyFromUserMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIDetachPolicyFromUserMsg'
    def __init__(self):
        super(APIDetachPolicyFromUserMsg, self).__init__()
        #mandatory field
        self.policyUuid = NotNoneField()
        #mandatory field
        self.userUuid = NotNoneField()


APIVALIDATESESSIONREPLY_FULL_NAME = 'org.zstack.header.identity.APIValidateSessionReply'
class APIValidateSessionReply(APIReply):
    FULL_NAME='org.zstack.header.identity.APIValidateSessionReply'
    def __init__(self):
        super(APIValidateSessionReply, self).__init__()
        self.validSession = None


APIQUERYUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryUserGroupMsg'
class APIQueryUserGroupMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.identity.APIQueryUserGroupMsg'
    def __init__(self):
        super(APIQueryUserGroupMsg, self).__init__()


APIGETZONEREPLY_FULL_NAME = 'org.zstack.header.zone.APIGetZoneReply'
class APIGetZoneReply(APIGetReply):
    FULL_NAME='org.zstack.header.zone.APIGetZoneReply'
    def __init__(self):
        super(APIGetZoneReply, self).__init__()


APIUPDATEZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIUpdateZoneMsg'
class APIUpdateZoneMsg(APIMessage):
    FULL_NAME='org.zstack.header.zone.APIUpdateZoneMsg'
    def __init__(self):
        super(APIUpdateZoneMsg, self).__init__()
        self.name = None
        self.description = None
        #mandatory field
        self.uuid = NotNoneField()


APISEARCHZONEREPLY_FULL_NAME = 'org.zstack.header.zone.APISearchZoneReply'
class APISearchZoneReply(APISearchReply):
    FULL_NAME='org.zstack.header.zone.APISearchZoneReply'
    def __init__(self):
        super(APISearchZoneReply, self).__init__()


APILISTZONESREPLY_FULL_NAME = 'org.zstack.header.zone.APIListZonesReply'
class APIListZonesReply(APIReply):
    FULL_NAME='org.zstack.header.zone.APIListZonesReply'
    def __init__(self):
        super(APIListZonesReply, self).__init__()
        self.inventories = OptionalList()


APIDELETEZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIDeleteZoneMsg'
class APIDeleteZoneMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.zone.APIDeleteZoneMsg'
    def __init__(self):
        super(APIDeleteZoneMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APICREATEZONEMSG_FULL_NAME = 'org.zstack.header.zone.APICreateZoneMsg'
class APICreateZoneMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.zone.APICreateZoneMsg'
    def __init__(self):
        super(APICreateZoneMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #valid values: [zstack]
        self.type = None


APIQUERYZONEREPLY_FULL_NAME = 'org.zstack.header.zone.APIQueryZoneReply'
class APIQueryZoneReply(APIQueryReply):
    FULL_NAME='org.zstack.header.zone.APIQueryZoneReply'
    def __init__(self):
        super(APIQueryZoneReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIQueryZoneMsg'
class APIQueryZoneMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.zone.APIQueryZoneMsg'
    def __init__(self):
        super(APIQueryZoneMsg, self).__init__()


APICHANGEZONESTATEMSG_FULL_NAME = 'org.zstack.header.zone.APIChangeZoneStateMsg'
class APIChangeZoneStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.zone.APIChangeZoneStateMsg'
    def __init__(self):
        super(APIChangeZoneStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIGETHYPERVISORTYPESREPLY_FULL_NAME = 'org.zstack.header.host.APIGetHypervisorTypesReply'
class APIGetHypervisorTypesReply(APIReply):
    FULL_NAME='org.zstack.header.host.APIGetHypervisorTypesReply'
    def __init__(self):
        super(APIGetHypervisorTypesReply, self).__init__()
        self.hypervisorTypes = OptionalList()


APICHANGEHOSTSTATEMSG_FULL_NAME = 'org.zstack.header.host.APIChangeHostStateMsg'
class APIChangeHostStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.host.APIChangeHostStateMsg'
    def __init__(self):
        super(APIChangeHostStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable, maintain]
        self.stateEvent = NotNoneField()


APIGETHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APIGetHostReply'
class APIGetHostReply(APIGetReply):
    FULL_NAME='org.zstack.header.host.APIGetHostReply'
    def __init__(self):
        super(APIGetHostReply, self).__init__()


APILISTHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APIListHostReply'
class APIListHostReply(APIReply):
    FULL_NAME='org.zstack.header.host.APIListHostReply'
    def __init__(self):
        super(APIListHostReply, self).__init__()
        self.inventories = OptionalList()


APIRECONNECTHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIReconnectHostMsg'
class APIReconnectHostMsg(APIMessage):
    FULL_NAME='org.zstack.header.host.APIReconnectHostMsg'
    def __init__(self):
        super(APIReconnectHostMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIUPDATEHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIUpdateHostMsg'
class APIUpdateHostMsg(APIMessage):
    FULL_NAME='org.zstack.header.host.APIUpdateHostMsg'
    def __init__(self):
        super(APIUpdateHostMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIDELETEHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIDeleteHostMsg'
class APIDeleteHostMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.host.APIDeleteHostMsg'
    def __init__(self):
        super(APIDeleteHostMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APISEARCHHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APISearchHostReply'
class APISearchHostReply(APISearchReply):
    FULL_NAME='org.zstack.header.host.APISearchHostReply'
    def __init__(self):
        super(APISearchHostReply, self).__init__()


APIQUERYHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APIQueryHostReply'
class APIQueryHostReply(APIQueryReply):
    FULL_NAME='org.zstack.header.host.APIQueryHostReply'
    def __init__(self):
        super(APIQueryHostReply, self).__init__()
        self.inventories = OptionalList()


APIGETHYPERVISORTYPESMSG_FULL_NAME = 'org.zstack.header.host.APIGetHypervisorTypesMsg'
class APIGetHypervisorTypesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.host.APIGetHypervisorTypesMsg'
    def __init__(self):
        super(APIGetHypervisorTypesMsg, self).__init__()


APIQUERYHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIQueryHostMsg'
class APIQueryHostMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.host.APIQueryHostMsg'
    def __init__(self):
        super(APIQueryHostMsg, self).__init__()


APIADDHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIAddHostMsg'
class APIAddHostMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.host.APIAddHostMsg'
    def __init__(self):
        super(APIAddHostMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.managementIp = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()


APIADDSIMULATORHOSTMSG_FULL_NAME = 'org.zstack.header.simulator.APIAddSimulatorHostMsg'
class APIAddSimulatorHostMsg(APIAddHostMsg):
    FULL_NAME='org.zstack.header.simulator.APIAddSimulatorHostMsg'
    def __init__(self):
        super(APIAddSimulatorHostMsg, self).__init__()
        #mandatory field
        self.memoryCapacity = NotNoneField()
        #mandatory field
        self.cpuCapacity = NotNoneField()


APIADDPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIAddPrimaryStorageMsg'
class APIAddPrimaryStorageMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIAddPrimaryStorageMsg'
    def __init__(self):
        super(APIAddPrimaryStorageMsg, self).__init__()
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        #mandatory field
        self.zoneUuid = NotNoneField()


APIADDSIMULATORPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.simulator.storage.primary.APIAddSimulatorPrimaryStorageMsg'
class APIAddSimulatorPrimaryStorageMsg(APIAddPrimaryStorageMsg):
    FULL_NAME='org.zstack.header.simulator.storage.primary.APIAddSimulatorPrimaryStorageMsg'
    def __init__(self):
        super(APIAddSimulatorPrimaryStorageMsg, self).__init__()
        self.totalCapacity = None
        self.availableCapacity = None


APIADDBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIAddBackupStorageMsg'
class APIAddBackupStorageMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIAddBackupStorageMsg'
    def __init__(self):
        super(APIAddBackupStorageMsg, self).__init__()
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None


APIADDSIMULATORBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.simulator.storage.backup.APIAddSimulatorBackupStorageMsg'
class APIAddSimulatorBackupStorageMsg(APIAddBackupStorageMsg):
    FULL_NAME='org.zstack.header.simulator.storage.backup.APIAddSimulatorBackupStorageMsg'
    def __init__(self):
        super(APIAddSimulatorBackupStorageMsg, self).__init__()
        self.totalCapacity = None
        self.availableCapacity = None


APIQUERYAPPLIANCEVMMSG_FULL_NAME = 'org.zstack.appliancevm.APIQueryApplianceVmMsg'
class APIQueryApplianceVmMsg(APIQueryMessage):
    FULL_NAME='org.zstack.appliancevm.APIQueryApplianceVmMsg'
    def __init__(self):
        super(APIQueryApplianceVmMsg, self).__init__()


APIQUERYAPPLIANCEVMREPLY_FULL_NAME = 'org.zstack.appliancevm.APIQueryApplianceVmReply'
class APIQueryApplianceVmReply(APIQueryReply):
    FULL_NAME='org.zstack.appliancevm.APIQueryApplianceVmReply'
    def __init__(self):
        super(APIQueryApplianceVmReply, self).__init__()
        self.inventories = OptionalList()


APILISTAPPLIANCEVMREPLY_FULL_NAME = 'org.zstack.appliancevm.APIListApplianceVmReply'
class APIListApplianceVmReply(APIReply):
    FULL_NAME='org.zstack.appliancevm.APIListApplianceVmReply'
    def __init__(self):
        super(APIListApplianceVmReply, self).__init__()
        self.inventories = OptionalList()


APIADDISCSIPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.iscsi.APIAddIScsiPrimaryStorageMsg'
class APIAddIScsiPrimaryStorageMsg(APIAddPrimaryStorageMsg):
    FULL_NAME='org.zstack.storage.primary.iscsi.APIAddIScsiPrimaryStorageMsg'
    def __init__(self):
        super(APIAddIScsiPrimaryStorageMsg, self).__init__()
        self.chapUsername = None
        self.chapPassword = None


APIADDISCSIFILESYSTEMBACKENDPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.iscsi.APIAddIscsiFileSystemBackendPrimaryStorageMsg'
class APIAddIscsiFileSystemBackendPrimaryStorageMsg(APIAddIScsiPrimaryStorageMsg):
    FULL_NAME='org.zstack.storage.primary.iscsi.APIAddIscsiFileSystemBackendPrimaryStorageMsg'
    def __init__(self):
        super(APIAddIscsiFileSystemBackendPrimaryStorageMsg, self).__init__()
        #mandatory field
        self.hostname = NotNoneField()
        #mandatory field
        self.sshUsername = NotNoneField()
        #mandatory field
        self.sshPassword = NotNoneField()
        self.filesystemType = None


APIQUERYISCSIFILESYSTEMBACKENDPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.iscsi.APIQueryIscsiFileSystemBackendPrimaryStorageMsg'
class APIQueryIscsiFileSystemBackendPrimaryStorageMsg(APIQueryMessage):
    FULL_NAME='org.zstack.storage.primary.iscsi.APIQueryIscsiFileSystemBackendPrimaryStorageMsg'
    def __init__(self):
        super(APIQueryIscsiFileSystemBackendPrimaryStorageMsg, self).__init__()


APIQUERYISCSIFILESYSTEMBACKENDPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.primary.iscsi.APIQueryIscsiFileSystemBackendPrimaryStorageReply'
class APIQueryIscsiFileSystemBackendPrimaryStorageReply(APIQueryReply):
    FULL_NAME='org.zstack.storage.primary.iscsi.APIQueryIscsiFileSystemBackendPrimaryStorageReply'
    def __init__(self):
        super(APIQueryIscsiFileSystemBackendPrimaryStorageReply, self).__init__()
        self.inventories = OptionalList()


APIUPDATEISCSIFILESYSTEMBACKENDPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.iscsi.APIUpdateIscsiFileSystemBackendPrimaryStorageMsg'
class APIUpdateIscsiFileSystemBackendPrimaryStorageMsg(APIUpdatePrimaryStorageMsg):
    FULL_NAME='org.zstack.storage.primary.iscsi.APIUpdateIscsiFileSystemBackendPrimaryStorageMsg'
    def __init__(self):
        super(APIUpdateIscsiFileSystemBackendPrimaryStorageMsg, self).__init__()
        self.chapUsername = None
        self.chapPassword = None
        self.sshUsername = None
        self.sshPassword = None


APIADDLOCALPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.local.APIAddLocalPrimaryStorageMsg'
class APIAddLocalPrimaryStorageMsg(APIAddPrimaryStorageMsg):
    FULL_NAME='org.zstack.storage.primary.local.APIAddLocalPrimaryStorageMsg'
    def __init__(self):
        super(APIAddLocalPrimaryStorageMsg, self).__init__()


APIUPDATEKVMHOSTMSG_FULL_NAME = 'org.zstack.kvm.APIUpdateKVMHostMsg'
class APIUpdateKVMHostMsg(APIUpdateHostMsg):
    FULL_NAME='org.zstack.kvm.APIUpdateKVMHostMsg'
    def __init__(self):
        super(APIUpdateKVMHostMsg, self).__init__()
        self.username = None
        self.password = None


APIADDKVMHOSTMSG_FULL_NAME = 'org.zstack.kvm.APIAddKVMHostMsg'
class APIAddKVMHostMsg(APIAddHostMsg):
    FULL_NAME='org.zstack.kvm.APIAddKVMHostMsg'
    def __init__(self):
        super(APIAddKVMHostMsg, self).__init__()
        #mandatory field
        self.username = NotNoneField()
        #mandatory field
        self.password = NotNoneField()


APIADDNFSPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.nfs.APIAddNfsPrimaryStorageMsg'
class APIAddNfsPrimaryStorageMsg(APIAddPrimaryStorageMsg):
    FULL_NAME='org.zstack.storage.primary.nfs.APIAddNfsPrimaryStorageMsg'
    def __init__(self):
        super(APIAddNfsPrimaryStorageMsg, self).__init__()


APIQUERYSFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageMsg'
class APIQuerySftpBackupStorageMsg(APIQueryMessage):
    FULL_NAME='org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageMsg'
    def __init__(self):
        super(APIQuerySftpBackupStorageMsg, self).__init__()


APIRECONNECTSFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIReconnectSftpBackupStorageMsg'
class APIReconnectSftpBackupStorageMsg(APIMessage):
    FULL_NAME='org.zstack.storage.backup.sftp.APIReconnectSftpBackupStorageMsg'
    def __init__(self):
        super(APIReconnectSftpBackupStorageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIUPDATESFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIUpdateSftpBackupStorageMsg'
class APIUpdateSftpBackupStorageMsg(APIUpdateBackupStorageMsg):
    FULL_NAME='org.zstack.storage.backup.sftp.APIUpdateSftpBackupStorageMsg'
    def __init__(self):
        super(APIUpdateSftpBackupStorageMsg, self).__init__()
        self.username = None
        self.password = None


APIGETSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APIGetSftpBackupStorageReply'
class APIGetSftpBackupStorageReply(APIGetReply):
    FULL_NAME='org.zstack.storage.backup.sftp.APIGetSftpBackupStorageReply'
    def __init__(self):
        super(APIGetSftpBackupStorageReply, self).__init__()


APIQUERYSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageReply'
class APIQuerySftpBackupStorageReply(APIQueryReply):
    FULL_NAME='org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageReply'
    def __init__(self):
        super(APIQuerySftpBackupStorageReply, self).__init__()
        self.inventories = OptionalList()


APIADDSFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIAddSftpBackupStorageMsg'
class APIAddSftpBackupStorageMsg(APIAddBackupStorageMsg):
    FULL_NAME='org.zstack.storage.backup.sftp.APIAddSftpBackupStorageMsg'
    def __init__(self):
        super(APIAddSftpBackupStorageMsg, self).__init__()
        #mandatory field
        self.hostname = NotNoneField()
        #mandatory field
        self.username = NotNoneField()
        #mandatory field
        self.password = NotNoneField()


APISEARCHSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APISearchSftpBackupStorageReply'
class APISearchSftpBackupStorageReply(APISearchReply):
    FULL_NAME='org.zstack.storage.backup.sftp.APISearchSftpBackupStorageReply'
    def __init__(self):
        super(APISearchSftpBackupStorageReply, self).__init__()


APISEARCHVIRTUALROUTERVMREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APISearchVirtualRouterVmReply'
class APISearchVirtualRouterVmReply(APISearchReply):
    FULL_NAME='org.zstack.network.service.virtualrouter.APISearchVirtualRouterVmReply'
    def __init__(self):
        super(APISearchVirtualRouterVmReply, self).__init__()


APIRECONNECTVIRTUALROUTERMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIReconnectVirtualRouterMsg'
class APIReconnectVirtualRouterMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIReconnectVirtualRouterMsg'
    def __init__(self):
        super(APIReconnectVirtualRouterMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()


APICREATEVIRTUALROUTERVMMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APICreateVirtualRouterVmMsg'
class APICreateVirtualRouterVmMsg(APICreateVmInstanceMsg):
    FULL_NAME='org.zstack.network.service.virtualrouter.APICreateVirtualRouterVmMsg'
    def __init__(self):
        super(APICreateVirtualRouterVmMsg, self).__init__()
        #mandatory field
        self.managementNetworkUuid = NotNoneField()
        #mandatory field
        self.publicNetworkUuid = NotNoneField()
        #mandatory field
        self.networkServicesProvided = NotNoneList()


APIQUERYVIRTUALROUTEROFFERINGMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIQueryVirtualRouterOfferingMsg'
class APIQueryVirtualRouterOfferingMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIQueryVirtualRouterOfferingMsg'
    def __init__(self):
        super(APIQueryVirtualRouterOfferingMsg, self).__init__()


APICREATEVIRTUALROUTEROFFERINGMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APICreateVirtualRouterOfferingMsg'
class APICreateVirtualRouterOfferingMsg(APICreateInstanceOfferingMsg):
    FULL_NAME='org.zstack.network.service.virtualrouter.APICreateVirtualRouterOfferingMsg'
    def __init__(self):
        super(APICreateVirtualRouterOfferingMsg, self).__init__()
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.managementNetworkUuid = NotNoneField()
        #mandatory field
        self.imageUuid = NotNoneField()
        self.publicNetworkUuid = None
        self.isDefault = None


APIQUERYVIRTUALROUTERVMMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIQueryVirtualRouterVmMsg'
class APIQueryVirtualRouterVmMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIQueryVirtualRouterVmMsg'
    def __init__(self):
        super(APIQueryVirtualRouterVmMsg, self).__init__()


APIGETVIRTUALROUTEROFFERINGREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIGetVirtualRouterOfferingReply'
class APIGetVirtualRouterOfferingReply(APIGetReply):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIGetVirtualRouterOfferingReply'
    def __init__(self):
        super(APIGetVirtualRouterOfferingReply, self).__init__()


APISEARCHVIRTUALROUTEROFFINGREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APISearchVirtualRouterOffingReply'
class APISearchVirtualRouterOffingReply(APISearchReply):
    FULL_NAME='org.zstack.network.service.virtualrouter.APISearchVirtualRouterOffingReply'
    def __init__(self):
        super(APISearchVirtualRouterOffingReply, self).__init__()


APIQUERYVIRTUALROUTEROFFERINGREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIQueryVirtualRouterOfferingReply'
class APIQueryVirtualRouterOfferingReply(APIQueryReply):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIQueryVirtualRouterOfferingReply'
    def __init__(self):
        super(APIQueryVirtualRouterOfferingReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYVIRTUALROUTERVMREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIQueryVirtualRouterVmReply'
class APIQueryVirtualRouterVmReply(APIQueryReply):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIQueryVirtualRouterVmReply'
    def __init__(self):
        super(APIQueryVirtualRouterVmReply, self).__init__()
        self.inventories = OptionalList()


APIATTACHPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIAttachPortForwardingRuleMsg'
class APIAttachPortForwardingRuleMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.portforwarding.APIAttachPortForwardingRuleMsg'
    def __init__(self):
        super(APIAttachPortForwardingRuleMsg, self).__init__()
        #mandatory field
        self.ruleUuid = NotNoneField()
        #mandatory field
        self.vmNicUuid = NotNoneField()


APIDETACHPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIDetachPortForwardingRuleMsg'
class APIDetachPortForwardingRuleMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.portforwarding.APIDetachPortForwardingRuleMsg'
    def __init__(self):
        super(APIDetachPortForwardingRuleMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIQUERYPORTFORWARDINGRULEREPLY_FULL_NAME = 'org.zstack.network.service.portforwarding.APIQueryPortForwardingRuleReply'
class APIQueryPortForwardingRuleReply(APIQueryReply):
    FULL_NAME='org.zstack.network.service.portforwarding.APIQueryPortForwardingRuleReply'
    def __init__(self):
        super(APIQueryPortForwardingRuleReply, self).__init__()
        self.inventories = OptionalList()


APIGETPORTFORWARDINGATTACHABLEVMNICSMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsMsg'
class APIGetPortForwardingAttachableVmNicsMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsMsg'
    def __init__(self):
        super(APIGetPortForwardingAttachableVmNicsMsg, self).__init__()
        #mandatory field
        self.ruleUuid = NotNoneField()


APILISTPORTFORWARDINGRULEREPLY_FULL_NAME = 'org.zstack.network.service.portforwarding.APIListPortForwardingRuleReply'
class APIListPortForwardingRuleReply(APIReply):
    FULL_NAME='org.zstack.network.service.portforwarding.APIListPortForwardingRuleReply'
    def __init__(self):
        super(APIListPortForwardingRuleReply, self).__init__()
        self.inventories = OptionalList()


APICHANGEPORTFORWARDINGRULESTATEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIChangePortForwardingRuleStateMsg'
class APIChangePortForwardingRuleStateMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.portforwarding.APIChangePortForwardingRuleStateMsg'
    def __init__(self):
        super(APIChangePortForwardingRuleStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIUPDATEPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIUpdatePortForwardingRuleMsg'
class APIUpdatePortForwardingRuleMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.portforwarding.APIUpdatePortForwardingRuleMsg'
    def __init__(self):
        super(APIUpdatePortForwardingRuleMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIGETPORTFORWARDINGATTACHABLEVMNICSREPLY_FULL_NAME = 'org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsReply'
class APIGetPortForwardingAttachableVmNicsReply(APIReply):
    FULL_NAME='org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsReply'
    def __init__(self):
        super(APIGetPortForwardingAttachableVmNicsReply, self).__init__()
        self.inventories = OptionalList()


APICREATEPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APICreatePortForwardingRuleMsg'
class APICreatePortForwardingRuleMsg(APICreateMessage):
    FULL_NAME='org.zstack.network.service.portforwarding.APICreatePortForwardingRuleMsg'
    def __init__(self):
        super(APICreatePortForwardingRuleMsg, self).__init__()
        #mandatory field
        self.vipUuid = NotNoneField()
        #mandatory field
        self.vipPortStart = NotNoneField()
        self.vipPortEnd = None
        self.privatePortStart = None
        self.privatePortEnd = None
        #mandatory field
        #valid values: [TCP, UDP]
        self.protocolType = NotNoneField()
        self.vmNicUuid = None
        self.allowedCidr = None
        #mandatory field
        self.name = NotNoneField()
        self.description = None


APIQUERYPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIQueryPortForwardingRuleMsg'
class APIQueryPortForwardingRuleMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.service.portforwarding.APIQueryPortForwardingRuleMsg'
    def __init__(self):
        super(APIQueryPortForwardingRuleMsg, self).__init__()


APIDELETEPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIDeletePortForwardingRuleMsg'
class APIDeletePortForwardingRuleMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.network.service.portforwarding.APIDeletePortForwardingRuleMsg'
    def __init__(self):
        super(APIDeletePortForwardingRuleMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIDETACHEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIDetachEipMsg'
class APIDetachEipMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.eip.APIDetachEipMsg'
    def __init__(self):
        super(APIDetachEipMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIGETEIPATTACHABLEVMNICSMSG_FULL_NAME = 'org.zstack.network.service.eip.APIGetEipAttachableVmNicsMsg'
class APIGetEipAttachableVmNicsMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.network.service.eip.APIGetEipAttachableVmNicsMsg'
    def __init__(self):
        super(APIGetEipAttachableVmNicsMsg, self).__init__()
        self.eipUuid = None
        self.vipUuid = None


APIUPDATEEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIUpdateEipMsg'
class APIUpdateEipMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.eip.APIUpdateEipMsg'
    def __init__(self):
        super(APIUpdateEipMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIQUERYEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIQueryEipMsg'
class APIQueryEipMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.service.eip.APIQueryEipMsg'
    def __init__(self):
        super(APIQueryEipMsg, self).__init__()


APIQUERYEIPREPLY_FULL_NAME = 'org.zstack.network.service.eip.APIQueryEipReply'
class APIQueryEipReply(APIQueryReply):
    FULL_NAME='org.zstack.network.service.eip.APIQueryEipReply'
    def __init__(self):
        super(APIQueryEipReply, self).__init__()
        self.inventories = OptionalList()


APICHANGEEIPSTATEMSG_FULL_NAME = 'org.zstack.network.service.eip.APIChangeEipStateMsg'
class APIChangeEipStateMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.eip.APIChangeEipStateMsg'
    def __init__(self):
        super(APIChangeEipStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIDELETEEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIDeleteEipMsg'
class APIDeleteEipMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.network.service.eip.APIDeleteEipMsg'
    def __init__(self):
        super(APIDeleteEipMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APICREATEEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APICreateEipMsg'
class APICreateEipMsg(APICreateMessage):
    FULL_NAME='org.zstack.network.service.eip.APICreateEipMsg'
    def __init__(self):
        super(APICreateEipMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.vipUuid = NotNoneField()
        self.vmNicUuid = None


APIATTACHEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIAttachEipMsg'
class APIAttachEipMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.eip.APIAttachEipMsg'
    def __init__(self):
        super(APIAttachEipMsg, self).__init__()
        #mandatory field
        self.eipUuid = NotNoneField()
        #mandatory field
        self.vmNicUuid = NotNoneField()


APIGETEIPATTACHABLEVMNICSREPLY_FULL_NAME = 'org.zstack.network.service.eip.APIGetEipAttachableVmNicsReply'
class APIGetEipAttachableVmNicsReply(APIReply):
    FULL_NAME='org.zstack.network.service.eip.APIGetEipAttachableVmNicsReply'
    def __init__(self):
        super(APIGetEipAttachableVmNicsReply, self).__init__()
        self.inventories = OptionalList()


APICHANGESECURITYGROUPSTATEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIChangeSecurityGroupStateMsg'
class APIChangeSecurityGroupStateMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIChangeSecurityGroupStateMsg'
    def __init__(self):
        super(APIChangeSecurityGroupStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APIDETACHSECURITYGROUPFROML3NETWORKMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDetachSecurityGroupFromL3NetworkMsg'
class APIDetachSecurityGroupFromL3NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIDetachSecurityGroupFromL3NetworkMsg'
    def __init__(self):
        super(APIDetachSecurityGroupFromL3NetworkMsg, self).__init__()
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()


APILISTSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIListSecurityGroupReply'
class APIListSecurityGroupReply(APIReply):
    FULL_NAME='org.zstack.network.securitygroup.APIListSecurityGroupReply'
    def __init__(self):
        super(APIListSecurityGroupReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYSECURITYGROUPRULEREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupRuleReply'
class APIQuerySecurityGroupRuleReply(APIQueryReply):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupRuleReply'
    def __init__(self):
        super(APIQuerySecurityGroupRuleReply, self).__init__()
        self.inventories = OptionalList()


APIDELETESECURITYGROUPRULEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteSecurityGroupRuleMsg'
class APIDeleteSecurityGroupRuleMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteSecurityGroupRuleMsg'
    def __init__(self):
        super(APIDeleteSecurityGroupRuleMsg, self).__init__()
        #mandatory field
        self.ruleUuids = NotNoneList()


APICREATESECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APICreateSecurityGroupMsg'
class APICreateSecurityGroupMsg(APICreateMessage):
    FULL_NAME='org.zstack.network.securitygroup.APICreateSecurityGroupMsg'
    def __init__(self):
        super(APICreateSecurityGroupMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None


APIGETCANDIDATEVMNICFORSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupReply'
class APIGetCandidateVmNicForSecurityGroupReply(APIReply):
    FULL_NAME='org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupReply'
    def __init__(self):
        super(APIGetCandidateVmNicForSecurityGroupReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYVMNICINSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupMsg'
class APIQueryVmNicInSecurityGroupMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupMsg'
    def __init__(self):
        super(APIQueryVmNicInSecurityGroupMsg, self).__init__()


APILISTVMNICINSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIListVmNicInSecurityGroupReply'
class APIListVmNicInSecurityGroupReply(APIReply):
    FULL_NAME='org.zstack.network.securitygroup.APIListVmNicInSecurityGroupReply'
    def __init__(self):
        super(APIListVmNicInSecurityGroupReply, self).__init__()
        self.inventories = OptionalList()


APIQUERYSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupMsg'
class APIQuerySecurityGroupMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupMsg'
    def __init__(self):
        super(APIQuerySecurityGroupMsg, self).__init__()


APIADDSECURITYGROUPRULEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIAddSecurityGroupRuleMsg'
class APIAddSecurityGroupRuleMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIAddSecurityGroupRuleMsg'
    def __init__(self):
        super(APIAddSecurityGroupRuleMsg, self).__init__()
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
        self.rules = NotNoneList()


APIQUERYSECURITYGROUPRULEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupRuleMsg'
class APIQuerySecurityGroupRuleMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupRuleMsg'
    def __init__(self):
        super(APIQuerySecurityGroupRuleMsg, self).__init__()


APIDELETESECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteSecurityGroupMsg'
class APIDeleteSecurityGroupMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteSecurityGroupMsg'
    def __init__(self):
        super(APIDeleteSecurityGroupMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIUPDATESECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIUpdateSecurityGroupMsg'
class APIUpdateSecurityGroupMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIUpdateSecurityGroupMsg'
    def __init__(self):
        super(APIUpdateSecurityGroupMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIDELETEVMNICFROMSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteVmNicFromSecurityGroupMsg'
class APIDeleteVmNicFromSecurityGroupMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteVmNicFromSecurityGroupMsg'
    def __init__(self):
        super(APIDeleteVmNicFromSecurityGroupMsg, self).__init__()
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
        self.vmNicUuids = NotNoneList()


APIQUERYSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupReply'
class APIQuerySecurityGroupReply(APIQueryReply):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupReply'
    def __init__(self):
        super(APIQuerySecurityGroupReply, self).__init__()
        self.inventories = OptionalList()


APIGETCANDIDATEVMNICFORSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupMsg'
class APIGetCandidateVmNicForSecurityGroupMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupMsg'
    def __init__(self):
        super(APIGetCandidateVmNicForSecurityGroupMsg, self).__init__()
        #mandatory field
        self.securityGroupUuid = NotNoneField()


APIATTACHSECURITYGROUPTOL3NETWORKMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIAttachSecurityGroupToL3NetworkMsg'
class APIAttachSecurityGroupToL3NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIAttachSecurityGroupToL3NetworkMsg'
    def __init__(self):
        super(APIAttachSecurityGroupToL3NetworkMsg, self).__init__()
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()


APIADDVMNICTOSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIAddVmNicToSecurityGroupMsg'
class APIAddVmNicToSecurityGroupMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIAddVmNicToSecurityGroupMsg'
    def __init__(self):
        super(APIAddVmNicToSecurityGroupMsg, self).__init__()
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
        self.vmNicUuids = NotNoneList()


APIQUERYVMNICINSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupReply'
class APIQueryVmNicInSecurityGroupReply(APIQueryReply):
    FULL_NAME='org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupReply'
    def __init__(self):
        super(APIQueryVmNicInSecurityGroupReply, self).__init__()
        self.inventories = OptionalList()


APIDELETEVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APIDeleteVipMsg'
class APIDeleteVipMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.network.service.vip.APIDeleteVipMsg'
    def __init__(self):
        super(APIDeleteVipMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIUPDATEVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APIUpdateVipMsg'
class APIUpdateVipMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.vip.APIUpdateVipMsg'
    def __init__(self):
        super(APIUpdateVipMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None


APIQUERYVIPREPLY_FULL_NAME = 'org.zstack.network.service.vip.APIQueryVipReply'
class APIQueryVipReply(APIQueryReply):
    FULL_NAME='org.zstack.network.service.vip.APIQueryVipReply'
    def __init__(self):
        super(APIQueryVipReply, self).__init__()
        self.inventories = OptionalList()


APICHANGEVIPSTATEMSG_FULL_NAME = 'org.zstack.network.service.vip.APIChangeVipStateMsg'
class APIChangeVipStateMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.vip.APIChangeVipStateMsg'
    def __init__(self):
        super(APIChangeVipStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()


APICREATEVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APICreateVipMsg'
class APICreateVipMsg(APICreateMessage):
    FULL_NAME='org.zstack.network.service.vip.APICreateVipMsg'
    def __init__(self):
        super(APICreateVipMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        self.allocatorStrategy = None
        self.requiredIp = None


APIQUERYVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APIQueryVipMsg'
class APIQueryVipMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.service.vip.APIQueryVipMsg'
    def __init__(self):
        super(APIQueryVipMsg, self).__init__()


api_names = [
    'APISilentMsg',
    'APIQueryGlobalConfigMsg',
    'APIGetGlobalConfigMsg',
    'APIGetGlobalConfigReply',
    'APIQueryGlobalConfigReply',
    'APIListGlobalConfigReply',
    'APIUpdateGlobalConfigMsg',
    'APIGenerateInventoryQueryDetailsMsg',
    'APIGenerateQueryableFieldsMsg',
    'APIGetCpuMemoryCapacityReply',
    'APIGetHostAllocatorStrategiesMsg',
    'APIGetCpuMemoryCapacityMsg',
    'APIGetHostAllocatorStrategiesReply',
    'APISearchVmInstanceReply',
    'APIUpdateVmInstanceMsg',
    'APIGetVmAttachableL3NetworkMsg',
    'APIGetVmInstanceReply',
    'APIGetVmAttachableDataVolumeReply',
    'APIGetVmMigrationCandidateHostsReply',
    'APIMigrateVmMsg',
    'APIStopVmInstanceMsg',
    'APIListVmInstanceReply',
    'APIChangeInstanceOfferingMsg',
    'APIGetVmAttachableDataVolumeMsg',
    'APIQueryVmNicMsg',
    'APIListVmNicReply',
    'APIAttachL3NetworkToVmMsg',
    'APIDestroyVmInstanceMsg',
    'APIGetVmMigrationCandidateHostsMsg',
    'APIQueryVmInstanceMsg',
    'APIDetachL3NetworkFromVmMsg',
    'APIQueryVmInstanceReply',
    'APIRebootVmInstanceMsg',
    'APIQueryVmNicReply',
    'APIGetVmAttachableL3NetworkReply',
    'APICreateVmInstanceMsg',
    'APIStartVmInstanceMsg',
    'APIChangeImageStateMsg',
    'APIUpdateImageMsg',
    'APIDeleteImageMsg',
    'APIGetImageReply',
    'APIQueryImageReply',
    'APIListImageReply',
    'APICreateDataVolumeTemplateFromVolumeMsg',
    'APICreateRootVolumeTemplateFromRootVolumeMsg',
    'APISearchImageReply',
    'APIQueryImageMsg',
    'APICreateRootVolumeTemplateFromVolumeSnapshotMsg',
    'APIAddImageMsg',
    'APIRequestConsoleAccessMsg',
    'APIBackupDataVolumeMsg',
    'APIAttachDataVolumeToVmMsg',
    'APIUpdateVolumeMsg',
    'APIQueryVolumeMsg',
    'APICreateDataVolumeFromVolumeSnapshotMsg',
    'APICreateDataVolumeFromVolumeTemplateMsg',
    'APIGetVolumeFormatReply',
    'APIDetachDataVolumeFromVmMsg',
    'APIGetDataVolumeAttachableVmReply',
    'APIQueryVolumeReply',
    'APICreateDataVolumeMsg',
    'APIGetVolumeReply',
    'APIListVolumeReply',
    'APIGetDataVolumeAttachableVmMsg',
    'APIGetVolumeFormatMsg',
    'APISearchVolumeReply',
    'APIDeleteDataVolumeMsg',
    'APICreateVolumeSnapshotMsg',
    'APIChangeVolumeStateMsg',
    'APIIsReadyToGoReply',
    'APIIsReadyToGoMsg',
    'APIGenerateApiTypeScriptDefinitionMsg',
    'APIDeleteDiskOfferingMsg',
    'APISearchInstanceOfferingReply',
    'APIGenerateGroovyClassMsg',
    'APIQueryInstanceOfferingMsg',
    'APIUpdateInstanceOfferingMsg',
    'APICreateInstanceOfferingMsg',
    'APIGenerateApiJsonTemplateMsg',
    'APIListDiskOfferingReply',
    'APICreateDiskOfferingMsg',
    'APIListInstanceOfferingReply',
    'APIDeleteInstanceOfferingMsg',
    'APIGenerateSqlVOViewMsg',
    'APIGenerateTestLinkDocumentMsg',
    'APISearchDnsReply',
    'APIGetInstanceOfferingReply',
    'APIQueryDiskOfferingReply',
    'APIChangeInstanceOfferingStateMsg',
    'APIGenerateSqlIndexMsg',
    'APIQueryDiskOfferingMsg',
    'APISearchDiskOfferingReply',
    'APIGenerateSqlForeignKeyMsg',
    'APIUpdateDiskOfferingMsg',
    'APIChangeDiskOfferingStateMsg',
    'APIGetDiskOfferingReply',
    'APIQueryInstanceOfferingReply',
    'APIListPrimaryStorageReply',
    'APIGetPrimaryStorageTypesMsg',
    'APIGetPrimaryStorageTypesReply',
    'APIAttachPrimaryStorageToClusterMsg',
    'CreateTemplateFromVolumeOnPrimaryStorageReply',
    'APIGetPrimaryStorageCapacityMsg',
    'APIUpdatePrimaryStorageMsg',
    'APIGetPrimaryStorageReply',
    'APISearchPrimaryStorageReply',
    'APIQueryPrimaryStorageMsg',
    'APIChangePrimaryStorageStateMsg',
    'APIGetPrimaryStorageAllocatorStrategiesReply',
    'APISyncPrimaryStorageCapacityMsg',
    'APIQueryPrimaryStorageReply',
    'APIDeletePrimaryStorageMsg',
    'APIReconnectPrimaryStorageMsg',
    'APIDetachPrimaryStorageFromClusterMsg',
    'APIGetPrimaryStorageCapacityReply',
    'APIGetPrimaryStorageAllocatorStrategiesMsg',
    'APIQueryVolumeSnapshotTreeMsg',
    'APIDeleteVolumeSnapshotMsg',
    'APIQueryVolumeSnapshotReply',
    'APIUpdateVolumeSnapshotMsg',
    'APIQueryVolumeSnapshotTreeReply',
    'APIDeleteVolumeSnapshotFromBackupStorageMsg',
    'APIQueryVolumeSnapshotMsg',
    'APIRevertVolumeFromSnapshotMsg',
    'APIBackupVolumeSnapshotMsg',
    'APIGetVolumeSnapshotTreeMsg',
    'APIGetVolumeSnapshotTreeReply',
    'APIQueryBackupStorageMsg',
    'APISearchBackupStorageReply',
    'APIAttachBackupStorageToZoneMsg',
    'APIGetBackupStorageCapacityReply',
    'APIGetBackupStorageTypesMsg',
    'APIChangeBackupStorageStateMsg',
    'APIQueryBackupStorageReply',
    'APIGetBackupStorageTypesReply',
    'APIScanBackupStorageMsg',
    'APIGetBackupStorageCapacityMsg',
    'APIDetachBackupStorageFromZoneMsg',
    'APIUpdateBackupStorageMsg',
    'APIGetBackupStorageReply',
    'APIListBackupStorageReply',
    'APIDeleteBackupStorageMsg',
    'APIAddDnsToL3NetworkMsg',
    'APICreateL3NetworkMsg',
    'APIListIpRangeReply',
    'APIGetFreeIpMsg',
    'APISearchL3NetworkReply',
    'APIUpdateL3NetworkMsg',
    'APIGetL3NetworkTypesReply',
    'APIDeleteIpRangeMsg',
    'APIChangeL3NetworkStateMsg',
    'APIGetL3NetworkReply',
    'APIGetIpAddressCapacityReply',
    'APIAddIpRangeMsg',
    'APIGetL3NetworkTypesMsg',
    'APIAddIpRangeByNetworkCidrMsg',
    'APIQueryL3NetworkReply',
    'APIQueryIpRangeMsg',
    'APIGetFreeIpReply',
    'APIRemoveDnsFromL3NetworkMsg',
    'APIQueryIpRangeReply',
    'APIListL3NetworkReply',
    'APIGetIpAddressCapacityMsg',
    'APIDeleteL3NetworkMsg',
    'APIUpdateIpRangeMsg',
    'APIQueryL3NetworkMsg',
    'APIQueryNetworkServiceL3NetworkRefReply',
    'APIAttachNetworkServiceToL3NetworkMsg',
    'APIAddNetworkServiceProviderMsg',
    'APISearchNetworkServiceProviderReply',
    'APIQueryNetworkServiceL3NetworkRefMsg',
    'APIAttachNetworkServiceProviderToL2NetworkMsg',
    'APIGetNetworkServiceProviderReply',
    'APIDetachNetworkServiceProviderFromL2NetworkMsg',
    'APIQueryNetworkServiceProviderMsg',
    'APIGetNetworkServiceTypesMsg',
    'APIGetNetworkServiceTypesReply',
    'APIListNetworkServiceProviderReply',
    'APIQueryNetworkServiceProviderReply',
    'APIAttachL2NetworkToClusterMsg',
    'APIQueryL2VlanNetworkMsg',
    'APIGetL2VlanNetworkReply',
    'APIGetL2NetworkReply',
    'APICreateL2VlanNetworkMsg',
    'APIQueryL2VlanNetworkReply',
    'APIDetachL2NetworkFromClusterMsg',
    'APIGetL2NetworkTypesReply',
    'APIListL2VlanNetworkReply',
    'APIDeleteL2NetworkMsg',
    'APISearchL2VlanNetworkReply',
    'APIQueryL2NetworkReply',
    'APICreateL2NoVlanNetworkMsg',
    'APISearchL2NetworkReply',
    'APIListL2NetworkReply',
    'APIUpdateL2NetworkMsg',
    'APIGetL2NetworkTypesMsg',
    'APIQueryL2NetworkMsg',
    'APIDeleteSearchIndexMsg',
    'APISearchGenerateSqlTriggerMsg',
    'APICreateSearchIndexMsg',
    'APIQueryUserTagMsg',
    'APIQuerySystemTagMsg',
    'APIDeleteTagMsg',
    'APIQueryUserTagReply',
    'APICreateUserTagMsg',
    'APICreateSystemTagMsg',
    'APIQueryTagMsg',
    'APIQuerySystemTagReply',
    'APIQueryTagReply',
    'APIQueryManagementNodeReply',
    'APIQueryManagementNodeMsg',
    'APIListManagementNodeReply',
    'APISearchClusterReply',
    'APIListClusterReply',
    'APIQueryClusterMsg',
    'APIDeleteClusterMsg',
    'APIUpdateClusterMsg',
    'APIGetClusterReply',
    'APICreateClusterMsg',
    'APIChangeClusterStateMsg',
    'APIQueryClusterReply',
    'APIListUserReply',
    'APIAttachPolicyToUserGroupMsg',
    'APIRemoveUserFromGroupMsg',
    'APIAttachPolicyToUserMsg',
    'APIQueryUserGroupReply',
    'APIResetUserPasswordMsg',
    'APIGetUserReply',
    'APIGetAccountReply',
    'APIQueryUserReply',
    'APIAddUserToGroupMsg',
    'APIQueryQuotaMsg',
    'APIListAccountReply',
    'APISearchPolicyReply',
    'APIShareResourceMsg',
    'APICreateAccountMsg',
    'APIDeleteAccountMsg',
    'APICreateUserGroupMsg',
    'APIQueryAccountReply',
    'APICreateUserMsg',
    'APILogInByUserMsg',
    'APILogOutReply',
    'APISearchUserGroupReply',
    'APIDetachPolicyFromUserGroupMsg',
    'APIGetPolicyReply',
    'APIUpdateQuotaMsg',
    'APILogInReply',
    'APIListPolicyReply',
    'APIQueryAccountMsg',
    'APIQueryPolicyMsg',
    'APIQueryUserMsg',
    'APIDeletePolicyMsg',
    'APIRevokeResourceSharingMsg',
    'APIQueryQuotaReply',
    'APIGetUserGroupReply',
    'APIResetAccountPasswordMsg',
    'APILogInByAccountMsg',
    'APIValidateSessionMsg',
    'APIQueryPolicyReply',
    'APISearchAccountReply',
    'APIDeleteUserMsg',
    'APISearchUserReply',
    'APIDeleteUserGroupMsg',
    'APILogOutMsg',
    'APICreatePolicyMsg',
    'APIDetachPolicyFromUserMsg',
    'APIValidateSessionReply',
    'APIQueryUserGroupMsg',
    'APIGetZoneReply',
    'APIUpdateZoneMsg',
    'APISearchZoneReply',
    'APIListZonesReply',
    'APIDeleteZoneMsg',
    'APICreateZoneMsg',
    'APIQueryZoneReply',
    'APIQueryZoneMsg',
    'APIChangeZoneStateMsg',
    'APIGetHypervisorTypesReply',
    'APIChangeHostStateMsg',
    'APIGetHostReply',
    'APIListHostReply',
    'APIReconnectHostMsg',
    'APIUpdateHostMsg',
    'APIDeleteHostMsg',
    'APISearchHostReply',
    'APIQueryHostReply',
    'APIGetHypervisorTypesMsg',
    'APIQueryHostMsg',
    'APIAddSimulatorHostMsg',
    'APIAddSimulatorPrimaryStorageMsg',
    'APIAddSimulatorBackupStorageMsg',
    'APIQueryApplianceVmMsg',
    'APIQueryApplianceVmReply',
    'APIListApplianceVmReply',
    'APIAddIscsiFileSystemBackendPrimaryStorageMsg',
    'APIQueryIscsiFileSystemBackendPrimaryStorageMsg',
    'APIQueryIscsiFileSystemBackendPrimaryStorageReply',
    'APIUpdateIscsiFileSystemBackendPrimaryStorageMsg',
    'APIAddLocalPrimaryStorageMsg',
    'APIUpdateKVMHostMsg',
    'APIAddKVMHostMsg',
    'APIAddNfsPrimaryStorageMsg',
    'APIQuerySftpBackupStorageMsg',
    'APIReconnectSftpBackupStorageMsg',
    'APIUpdateSftpBackupStorageMsg',
    'APIGetSftpBackupStorageReply',
    'APIQuerySftpBackupStorageReply',
    'APIAddSftpBackupStorageMsg',
    'APISearchSftpBackupStorageReply',
    'APISearchVirtualRouterVmReply',
    'APIReconnectVirtualRouterMsg',
    'APICreateVirtualRouterVmMsg',
    'APIQueryVirtualRouterOfferingMsg',
    'APICreateVirtualRouterOfferingMsg',
    'APIQueryVirtualRouterVmMsg',
    'APIGetVirtualRouterOfferingReply',
    'APISearchVirtualRouterOffingReply',
    'APIQueryVirtualRouterOfferingReply',
    'APIQueryVirtualRouterVmReply',
    'APIAttachPortForwardingRuleMsg',
    'APIDetachPortForwardingRuleMsg',
    'APIQueryPortForwardingRuleReply',
    'APIGetPortForwardingAttachableVmNicsMsg',
    'APIListPortForwardingRuleReply',
    'APIChangePortForwardingRuleStateMsg',
    'APIUpdatePortForwardingRuleMsg',
    'APIGetPortForwardingAttachableVmNicsReply',
    'APICreatePortForwardingRuleMsg',
    'APIQueryPortForwardingRuleMsg',
    'APIDeletePortForwardingRuleMsg',
    'APIDetachEipMsg',
    'APIGetEipAttachableVmNicsMsg',
    'APIUpdateEipMsg',
    'APIQueryEipMsg',
    'APIQueryEipReply',
    'APIChangeEipStateMsg',
    'APIDeleteEipMsg',
    'APICreateEipMsg',
    'APIAttachEipMsg',
    'APIGetEipAttachableVmNicsReply',
    'APIChangeSecurityGroupStateMsg',
    'APIDetachSecurityGroupFromL3NetworkMsg',
    'APIListSecurityGroupReply',
    'APIQuerySecurityGroupRuleReply',
    'APIDeleteSecurityGroupRuleMsg',
    'APICreateSecurityGroupMsg',
    'APIGetCandidateVmNicForSecurityGroupReply',
    'APIQueryVmNicInSecurityGroupMsg',
    'APIListVmNicInSecurityGroupReply',
    'APIQuerySecurityGroupMsg',
    'APIAddSecurityGroupRuleMsg',
    'APIQuerySecurityGroupRuleMsg',
    'APIDeleteSecurityGroupMsg',
    'APIUpdateSecurityGroupMsg',
    'APIDeleteVmNicFromSecurityGroupMsg',
    'APIQuerySecurityGroupReply',
    'APIGetCandidateVmNicForSecurityGroupMsg',
    'APIAttachSecurityGroupToL3NetworkMsg',
    'APIAddVmNicToSecurityGroupMsg',
    'APIQueryVmNicInSecurityGroupReply',
    'APIDeleteVipMsg',
    'APIUpdateVipMsg',
    'APIQueryVipReply',
    'APIChangeVipStateMsg',
    'APICreateVipMsg',
    'APIQueryVipMsg',
]

class GlobalConfigInventory(object):
    def __init__(self):
        self.name = None
        self.category = None
        self.description = None
        self.defaultValue = None
        self.value = None

    def evaluate(self, inv):
        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'category'):
            self.category = inv.category
        else:
            self.category = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'defaultValue'):
            self.defaultValue = inv.defaultValue
        else:
            self.defaultValue = None

        if hasattr(inv, 'value'):
            self.value = inv.value
        else:
            self.value = None



class VmInstanceInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.zoneUuid = None
        self.clusterUuid = None
        self.imageUuid = None
        self.hostUuid = None
        self.lastHostUuid = None
        self.instanceOfferingUuid = None
        self.rootVolumeUuid = None
        self.platform = None
        self.defaultL3NetworkUuid = None
        self.type = None
        self.hypervisorType = None
        self.memorySize = None
        self.cpuNum = None
        self.cpuSpeed = None
        self.allocatorStrategy = None
        self.createDate = None
        self.lastOpDate = None
        self.state = None
        self.internalId = None
        self.vmNics = None
        self.allVolumes = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'zoneUuid'):
            self.zoneUuid = inv.zoneUuid
        else:
            self.zoneUuid = None

        if hasattr(inv, 'clusterUuid'):
            self.clusterUuid = inv.clusterUuid
        else:
            self.clusterUuid = None

        if hasattr(inv, 'imageUuid'):
            self.imageUuid = inv.imageUuid
        else:
            self.imageUuid = None

        if hasattr(inv, 'hostUuid'):
            self.hostUuid = inv.hostUuid
        else:
            self.hostUuid = None

        if hasattr(inv, 'lastHostUuid'):
            self.lastHostUuid = inv.lastHostUuid
        else:
            self.lastHostUuid = None

        if hasattr(inv, 'instanceOfferingUuid'):
            self.instanceOfferingUuid = inv.instanceOfferingUuid
        else:
            self.instanceOfferingUuid = None

        if hasattr(inv, 'rootVolumeUuid'):
            self.rootVolumeUuid = inv.rootVolumeUuid
        else:
            self.rootVolumeUuid = None

        if hasattr(inv, 'platform'):
            self.platform = inv.platform
        else:
            self.platform = None

        if hasattr(inv, 'defaultL3NetworkUuid'):
            self.defaultL3NetworkUuid = inv.defaultL3NetworkUuid
        else:
            self.defaultL3NetworkUuid = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'hypervisorType'):
            self.hypervisorType = inv.hypervisorType
        else:
            self.hypervisorType = None

        if hasattr(inv, 'memorySize'):
            self.memorySize = inv.memorySize
        else:
            self.memorySize = None

        if hasattr(inv, 'cpuNum'):
            self.cpuNum = inv.cpuNum
        else:
            self.cpuNum = None

        if hasattr(inv, 'cpuSpeed'):
            self.cpuSpeed = inv.cpuSpeed
        else:
            self.cpuSpeed = None

        if hasattr(inv, 'allocatorStrategy'):
            self.allocatorStrategy = inv.allocatorStrategy
        else:
            self.allocatorStrategy = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'internalId'):
            self.internalId = inv.internalId
        else:
            self.internalId = None

        if hasattr(inv, 'vmNics'):
            self.vmNics = inv.vmNics
        else:
            self.vmNics = None

        if hasattr(inv, 'allVolumes'):
            self.allVolumes = inv.allVolumes
        else:
            self.allVolumes = None



class ImageInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.state = None
        self.status = None
        self.size = None
        self.md5Sum = None
        self.url = None
        self.mediaType = None
        self.guestOsType = None
        self.type = None
        self.platform = None
        self.format = None
        self.system = None
        self.createDate = None
        self.lastOpDate = None
        self.backupStorageRefs = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'status'):
            self.status = inv.status
        else:
            self.status = None

        if hasattr(inv, 'size'):
            self.size = inv.size
        else:
            self.size = None

        if hasattr(inv, 'md5Sum'):
            self.md5Sum = inv.md5Sum
        else:
            self.md5Sum = None

        if hasattr(inv, 'url'):
            self.url = inv.url
        else:
            self.url = None

        if hasattr(inv, 'mediaType'):
            self.mediaType = inv.mediaType
        else:
            self.mediaType = None

        if hasattr(inv, 'guestOsType'):
            self.guestOsType = inv.guestOsType
        else:
            self.guestOsType = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'platform'):
            self.platform = inv.platform
        else:
            self.platform = None

        if hasattr(inv, 'format'):
            self.format = inv.format
        else:
            self.format = None

        if hasattr(inv, 'system'):
            self.system = inv.system
        else:
            self.system = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'backupStorageRefs'):
            self.backupStorageRefs = inv.backupStorageRefs
        else:
            self.backupStorageRefs = None



class ConsoleProxyInventory(object):
    def __init__(self):
        self.uuid = None
        self.vmInstanceUuid = None
        self.agentIp = None
        self.token = None
        self.agentType = None
        self.proxyHostname = None
        self.proxyPort = None
        self.targetHostname = None
        self.targetPort = None
        self.scheme = None
        self.proxyIdentity = None
        self.status = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'vmInstanceUuid'):
            self.vmInstanceUuid = inv.vmInstanceUuid
        else:
            self.vmInstanceUuid = None

        if hasattr(inv, 'agentIp'):
            self.agentIp = inv.agentIp
        else:
            self.agentIp = None

        if hasattr(inv, 'token'):
            self.token = inv.token
        else:
            self.token = None

        if hasattr(inv, 'agentType'):
            self.agentType = inv.agentType
        else:
            self.agentType = None

        if hasattr(inv, 'proxyHostname'):
            self.proxyHostname = inv.proxyHostname
        else:
            self.proxyHostname = None

        if hasattr(inv, 'proxyPort'):
            self.proxyPort = inv.proxyPort
        else:
            self.proxyPort = None

        if hasattr(inv, 'targetHostname'):
            self.targetHostname = inv.targetHostname
        else:
            self.targetHostname = None

        if hasattr(inv, 'targetPort'):
            self.targetPort = inv.targetPort
        else:
            self.targetPort = None

        if hasattr(inv, 'scheme'):
            self.scheme = inv.scheme
        else:
            self.scheme = None

        if hasattr(inv, 'proxyIdentity'):
            self.proxyIdentity = inv.proxyIdentity
        else:
            self.proxyIdentity = None

        if hasattr(inv, 'status'):
            self.status = inv.status
        else:
            self.status = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class VolumeInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.primaryStorageUuid = None
        self.vmInstanceUuid = None
        self.diskOfferingUuid = None
        self.rootImageUuid = None
        self.installPath = None
        self.type = None
        self.format = None
        self.size = None
        self.deviceId = None
        self.state = None
        self.status = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'primaryStorageUuid'):
            self.primaryStorageUuid = inv.primaryStorageUuid
        else:
            self.primaryStorageUuid = None

        if hasattr(inv, 'vmInstanceUuid'):
            self.vmInstanceUuid = inv.vmInstanceUuid
        else:
            self.vmInstanceUuid = None

        if hasattr(inv, 'diskOfferingUuid'):
            self.diskOfferingUuid = inv.diskOfferingUuid
        else:
            self.diskOfferingUuid = None

        if hasattr(inv, 'rootImageUuid'):
            self.rootImageUuid = inv.rootImageUuid
        else:
            self.rootImageUuid = None

        if hasattr(inv, 'installPath'):
            self.installPath = inv.installPath
        else:
            self.installPath = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'format'):
            self.format = inv.format
        else:
            self.format = None

        if hasattr(inv, 'size'):
            self.size = inv.size
        else:
            self.size = None

        if hasattr(inv, 'deviceId'):
            self.deviceId = inv.deviceId
        else:
            self.deviceId = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'status'):
            self.status = inv.status
        else:
            self.status = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class InstanceOfferingInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.cpuNum = None
        self.cpuSpeed = None
        self.memorySize = None
        self.type = None
        self.allocatorStrategy = None
        self.sortKey = None
        self.createDate = None
        self.lastOpDate = None
        self.state = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'cpuNum'):
            self.cpuNum = inv.cpuNum
        else:
            self.cpuNum = None

        if hasattr(inv, 'cpuSpeed'):
            self.cpuSpeed = inv.cpuSpeed
        else:
            self.cpuSpeed = None

        if hasattr(inv, 'memorySize'):
            self.memorySize = inv.memorySize
        else:
            self.memorySize = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'allocatorStrategy'):
            self.allocatorStrategy = inv.allocatorStrategy
        else:
            self.allocatorStrategy = None

        if hasattr(inv, 'sortKey'):
            self.sortKey = inv.sortKey
        else:
            self.sortKey = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None



class DiskOfferingInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.diskSize = None
        self.sortKey = None
        self.state = None
        self.type = None
        self.createDate = None
        self.lastOpDate = None
        self.allocatorStrategy = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'diskSize'):
            self.diskSize = inv.diskSize
        else:
            self.diskSize = None

        if hasattr(inv, 'sortKey'):
            self.sortKey = inv.sortKey
        else:
            self.sortKey = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'allocatorStrategy'):
            self.allocatorStrategy = inv.allocatorStrategy
        else:
            self.allocatorStrategy = None



class PrimaryStorageInventory(object):
    def __init__(self):
        self.uuid = None
        self.zoneUuid = None
        self.name = None
        self.url = None
        self.description = None
        self.totalCapacity = None
        self.availableCapacity = None
        self.totalPhysicalCapacity = None
        self.availablePhysicalCapacity = None
        self.type = None
        self.state = None
        self.status = None
        self.mountPath = None
        self.createDate = None
        self.lastOpDate = None
        self.attachedClusterUuids = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'zoneUuid'):
            self.zoneUuid = inv.zoneUuid
        else:
            self.zoneUuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'url'):
            self.url = inv.url
        else:
            self.url = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'totalCapacity'):
            self.totalCapacity = inv.totalCapacity
        else:
            self.totalCapacity = None

        if hasattr(inv, 'availableCapacity'):
            self.availableCapacity = inv.availableCapacity
        else:
            self.availableCapacity = None

        if hasattr(inv, 'totalPhysicalCapacity'):
            self.totalPhysicalCapacity = inv.totalPhysicalCapacity
        else:
            self.totalPhysicalCapacity = None

        if hasattr(inv, 'availablePhysicalCapacity'):
            self.availablePhysicalCapacity = inv.availablePhysicalCapacity
        else:
            self.availablePhysicalCapacity = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'status'):
            self.status = inv.status
        else:
            self.status = None

        if hasattr(inv, 'mountPath'):
            self.mountPath = inv.mountPath
        else:
            self.mountPath = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'attachedClusterUuids'):
            self.attachedClusterUuids = inv.attachedClusterUuids
        else:
            self.attachedClusterUuids = None



class BackupStorageInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.url = None
        self.description = None
        self.totalCapacity = None
        self.availableCapacity = None
        self.type = None
        self.state = None
        self.status = None
        self.createDate = None
        self.lastOpDate = None
        self.attachedZoneUuids = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'url'):
            self.url = inv.url
        else:
            self.url = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'totalCapacity'):
            self.totalCapacity = inv.totalCapacity
        else:
            self.totalCapacity = None

        if hasattr(inv, 'availableCapacity'):
            self.availableCapacity = inv.availableCapacity
        else:
            self.availableCapacity = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'status'):
            self.status = inv.status
        else:
            self.status = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'attachedZoneUuids'):
            self.attachedZoneUuids = inv.attachedZoneUuids
        else:
            self.attachedZoneUuids = None



class IpRangeInventory(object):
    def __init__(self):
        self.uuid = None
        self.l3NetworkUuid = None
        self.name = None
        self.description = None
        self.startIp = None
        self.endIp = None
        self.netmask = None
        self.gateway = None
        self.networkCidr = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'l3NetworkUuid'):
            self.l3NetworkUuid = inv.l3NetworkUuid
        else:
            self.l3NetworkUuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'startIp'):
            self.startIp = inv.startIp
        else:
            self.startIp = None

        if hasattr(inv, 'endIp'):
            self.endIp = inv.endIp
        else:
            self.endIp = None

        if hasattr(inv, 'netmask'):
            self.netmask = inv.netmask
        else:
            self.netmask = None

        if hasattr(inv, 'gateway'):
            self.gateway = inv.gateway
        else:
            self.gateway = None

        if hasattr(inv, 'networkCidr'):
            self.networkCidr = inv.networkCidr
        else:
            self.networkCidr = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class L3NetworkInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.type = None
        self.zoneUuid = None
        self.l2NetworkUuid = None
        self.state = None
        self.dnsDomain = None
        self.system = None
        self.createDate = None
        self.lastOpDate = None
        self.dns = None
        self.ipRanges = None
        self.networkServices = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'zoneUuid'):
            self.zoneUuid = inv.zoneUuid
        else:
            self.zoneUuid = None

        if hasattr(inv, 'l2NetworkUuid'):
            self.l2NetworkUuid = inv.l2NetworkUuid
        else:
            self.l2NetworkUuid = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'dnsDomain'):
            self.dnsDomain = inv.dnsDomain
        else:
            self.dnsDomain = None

        if hasattr(inv, 'system'):
            self.system = inv.system
        else:
            self.system = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'dns'):
            self.dns = inv.dns
        else:
            self.dns = None

        if hasattr(inv, 'ipRanges'):
            self.ipRanges = inv.ipRanges
        else:
            self.ipRanges = None

        if hasattr(inv, 'networkServices'):
            self.networkServices = inv.networkServices
        else:
            self.networkServices = None



class L2NetworkInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.zoneUuid = None
        self.physicalInterface = None
        self.type = None
        self.createDate = None
        self.lastOpDate = None
        self.attachedClusterUuids = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'zoneUuid'):
            self.zoneUuid = inv.zoneUuid
        else:
            self.zoneUuid = None

        if hasattr(inv, 'physicalInterface'):
            self.physicalInterface = inv.physicalInterface
        else:
            self.physicalInterface = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'attachedClusterUuids'):
            self.attachedClusterUuids = inv.attachedClusterUuids
        else:
            self.attachedClusterUuids = None



class L2VlanNetworkInventory(L2NetworkInventory):
    def __init__(self):
        super(L2VlanNetworkInventory, self).__init__()
        self.vlan = None

    def evaluate(self, inv):
        super(L2VlanNetworkInventory, self).evaluate(inv)
        if hasattr(inv, 'vlan'):
            self.vlan = inv.vlan
        else:
            self.vlan = None



class ManagementNodeInventory(object):
    def __init__(self):
        self.uuid = None
        self.hostName = None
        self.joinDate = None
        self.heartBeat = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'hostName'):
            self.hostName = inv.hostName
        else:
            self.hostName = None

        if hasattr(inv, 'joinDate'):
            self.joinDate = inv.joinDate
        else:
            self.joinDate = None

        if hasattr(inv, 'heartBeat'):
            self.heartBeat = inv.heartBeat
        else:
            self.heartBeat = None



class ClusterInventory(object):
    def __init__(self):
        self.name = None
        self.uuid = None
        self.description = None
        self.state = None
        self.hypervisorType = None
        self.createDate = None
        self.lastOpDate = None
        self.zoneUuid = None
        self.type = None

    def evaluate(self, inv):
        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'hypervisorType'):
            self.hypervisorType = inv.hypervisorType
        else:
            self.hypervisorType = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'zoneUuid'):
            self.zoneUuid = inv.zoneUuid
        else:
            self.zoneUuid = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None



class UserInventory(object):
    def __init__(self):
        self.uuid = None
        self.accountUuid = None
        self.name = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'accountUuid'):
            self.accountUuid = inv.accountUuid
        else:
            self.accountUuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class UserGroupInventory(object):
    def __init__(self):
        self.uuid = None
        self.accountUuid = None
        self.name = None
        self.description = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'accountUuid'):
            self.accountUuid = inv.accountUuid
        else:
            self.accountUuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class SessionInventory(object):
    def __init__(self):
        self.uuid = None
        self.accountUuid = None
        self.userUuid = None
        self.expiredDate = None
        self.createDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'accountUuid'):
            self.accountUuid = inv.accountUuid
        else:
            self.accountUuid = None

        if hasattr(inv, 'userUuid'):
            self.userUuid = inv.userUuid
        else:
            self.userUuid = None

        if hasattr(inv, 'expiredDate'):
            self.expiredDate = inv.expiredDate
        else:
            self.expiredDate = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None



class PolicyInventory(object):
    def __init__(self):
        self.statements = None
        self.name = None
        self.uuid = None
        self.accountUuid = None

    def evaluate(self, inv):
        if hasattr(inv, 'statements'):
            self.statements = inv.statements
        else:
            self.statements = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'accountUuid'):
            self.accountUuid = inv.accountUuid
        else:
            self.accountUuid = None



class AccountInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class ZoneInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.state = None
        self.type = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class HostInventory(object):
    def __init__(self):
        self.zoneUuid = None
        self.name = None
        self.uuid = None
        self.clusterUuid = None
        self.description = None
        self.managementIp = None
        self.hypervisorType = None
        self.state = None
        self.status = None
        self.totalCpuCapacity = None
        self.availableCpuCapacity = None
        self.totalMemoryCapacity = None
        self.availableMemoryCapacity = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'zoneUuid'):
            self.zoneUuid = inv.zoneUuid
        else:
            self.zoneUuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'clusterUuid'):
            self.clusterUuid = inv.clusterUuid
        else:
            self.clusterUuid = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'managementIp'):
            self.managementIp = inv.managementIp
        else:
            self.managementIp = None

        if hasattr(inv, 'hypervisorType'):
            self.hypervisorType = inv.hypervisorType
        else:
            self.hypervisorType = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'status'):
            self.status = inv.status
        else:
            self.status = None

        if hasattr(inv, 'totalCpuCapacity'):
            self.totalCpuCapacity = inv.totalCpuCapacity
        else:
            self.totalCpuCapacity = None

        if hasattr(inv, 'availableCpuCapacity'):
            self.availableCpuCapacity = inv.availableCpuCapacity
        else:
            self.availableCpuCapacity = None

        if hasattr(inv, 'totalMemoryCapacity'):
            self.totalMemoryCapacity = inv.totalMemoryCapacity
        else:
            self.totalMemoryCapacity = None

        if hasattr(inv, 'availableMemoryCapacity'):
            self.availableMemoryCapacity = inv.availableMemoryCapacity
        else:
            self.availableMemoryCapacity = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class ApplianceVmInventory(VmInstanceInventory):
    def __init__(self):
        super(ApplianceVmInventory, self).__init__()
        self.applianceVmType = None
        self.managementNetworkUuid = None
        self.defaultRouteL3NetworkUuid = None
        self.status = None

    def evaluate(self, inv):
        super(ApplianceVmInventory, self).evaluate(inv)
        if hasattr(inv, 'applianceVmType'):
            self.applianceVmType = inv.applianceVmType
        else:
            self.applianceVmType = None

        if hasattr(inv, 'managementNetworkUuid'):
            self.managementNetworkUuid = inv.managementNetworkUuid
        else:
            self.managementNetworkUuid = None

        if hasattr(inv, 'defaultRouteL3NetworkUuid'):
            self.defaultRouteL3NetworkUuid = inv.defaultRouteL3NetworkUuid
        else:
            self.defaultRouteL3NetworkUuid = None

        if hasattr(inv, 'status'):
            self.status = inv.status
        else:
            self.status = None



class IscsiFileSystemBackendPrimaryStorageInventory(PrimaryStorageInventory):
    def __init__(self):
        super(IscsiFileSystemBackendPrimaryStorageInventory, self).__init__()
        self.chapUsername = None
        self.chapPassword = None
        self.hostname = None
        self.sshUsername = None
        self.sshPassword = None
        self.filesystemType = None

    def evaluate(self, inv):
        super(IscsiFileSystemBackendPrimaryStorageInventory, self).evaluate(inv)
        if hasattr(inv, 'chapUsername'):
            self.chapUsername = inv.chapUsername
        else:
            self.chapUsername = None

        if hasattr(inv, 'chapPassword'):
            self.chapPassword = inv.chapPassword
        else:
            self.chapPassword = None

        if hasattr(inv, 'hostname'):
            self.hostname = inv.hostname
        else:
            self.hostname = None

        if hasattr(inv, 'sshUsername'):
            self.sshUsername = inv.sshUsername
        else:
            self.sshUsername = None

        if hasattr(inv, 'sshPassword'):
            self.sshPassword = inv.sshPassword
        else:
            self.sshPassword = None

        if hasattr(inv, 'filesystemType'):
            self.filesystemType = inv.filesystemType
        else:
            self.filesystemType = None



class KVMHostInventory(HostInventory):
    def __init__(self):
        super(KVMHostInventory, self).__init__()
        self.username = None
        self.password = None

    def evaluate(self, inv):
        super(KVMHostInventory, self).evaluate(inv)
        if hasattr(inv, 'username'):
            self.username = inv.username
        else:
            self.username = None

        if hasattr(inv, 'password'):
            self.password = inv.password
        else:
            self.password = None



class SftpBackupStorageInventory(BackupStorageInventory):
    def __init__(self):
        super(SftpBackupStorageInventory, self).__init__()
        self.hostname = None
        self.username = None

    def evaluate(self, inv):
        super(SftpBackupStorageInventory, self).evaluate(inv)
        if hasattr(inv, 'hostname'):
            self.hostname = inv.hostname
        else:
            self.hostname = None

        if hasattr(inv, 'username'):
            self.username = inv.username
        else:
            self.username = None



class VirtualRouterOfferingInventory(InstanceOfferingInventory):
    def __init__(self):
        super(VirtualRouterOfferingInventory, self).__init__()
        self.managementNetworkUuid = None
        self.publicNetworkUuid = None
        self.zoneUuid = None
        self.isDefault = None
        self.imageUuid = None

    def evaluate(self, inv):
        super(VirtualRouterOfferingInventory, self).evaluate(inv)
        if hasattr(inv, 'managementNetworkUuid'):
            self.managementNetworkUuid = inv.managementNetworkUuid
        else:
            self.managementNetworkUuid = None

        if hasattr(inv, 'publicNetworkUuid'):
            self.publicNetworkUuid = inv.publicNetworkUuid
        else:
            self.publicNetworkUuid = None

        if hasattr(inv, 'zoneUuid'):
            self.zoneUuid = inv.zoneUuid
        else:
            self.zoneUuid = None

        if hasattr(inv, 'isDefault'):
            self.isDefault = inv.isDefault
        else:
            self.isDefault = None

        if hasattr(inv, 'imageUuid'):
            self.imageUuid = inv.imageUuid
        else:
            self.imageUuid = None



class VirtualRouterVmInventory(ApplianceVmInventory):
    def __init__(self):
        super(VirtualRouterVmInventory, self).__init__()
        self.publicNetworkUuid = None

    def evaluate(self, inv):
        super(VirtualRouterVmInventory, self).evaluate(inv)
        if hasattr(inv, 'publicNetworkUuid'):
            self.publicNetworkUuid = inv.publicNetworkUuid
        else:
            self.publicNetworkUuid = None



class VmNicSecurityGroupRefInventory(object):
    def __init__(self):
        self.uuid = None
        self.vmNicUuid = None
        self.securityGroupUuid = None
        self.vmInstanceUuid = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'vmNicUuid'):
            self.vmNicUuid = inv.vmNicUuid
        else:
            self.vmNicUuid = None

        if hasattr(inv, 'securityGroupUuid'):
            self.securityGroupUuid = inv.securityGroupUuid
        else:
            self.securityGroupUuid = None

        if hasattr(inv, 'vmInstanceUuid'):
            self.vmInstanceUuid = inv.vmInstanceUuid
        else:
            self.vmInstanceUuid = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class SecurityGroupRuleInventory(object):
    def __init__(self):
        self.uuid = None
        self.securityGroupUuid = None
        self.type = None
        self.startPort = None
        self.endPort = None
        self.protocol = None
        self.state = None
        self.allowedCidr = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'securityGroupUuid'):
            self.securityGroupUuid = inv.securityGroupUuid
        else:
            self.securityGroupUuid = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'startPort'):
            self.startPort = inv.startPort
        else:
            self.startPort = None

        if hasattr(inv, 'endPort'):
            self.endPort = inv.endPort
        else:
            self.endPort = None

        if hasattr(inv, 'protocol'):
            self.protocol = inv.protocol
        else:
            self.protocol = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'allowedCidr'):
            self.allowedCidr = inv.allowedCidr
        else:
            self.allowedCidr = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class SecurityGroupInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.state = None
        self.createDate = None
        self.lastOpDate = None
        self.internalId = None
        self.rules = None
        self.attachedL3NetworkUuids = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'internalId'):
            self.internalId = inv.internalId
        else:
            self.internalId = None

        if hasattr(inv, 'rules'):
            self.rules = inv.rules
        else:
            self.rules = None

        if hasattr(inv, 'attachedL3NetworkUuids'):
            self.attachedL3NetworkUuids = inv.attachedL3NetworkUuids
        else:
            self.attachedL3NetworkUuids = None



class SecurityGroupRuleAO(object):
    def __init__(self):
        self.type = None
        self.startPort = None
        self.endPort = None
        self.protocol = None
        self.allowedCidr = None

    def evaluate(self, inv):
        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'startPort'):
            self.startPort = inv.startPort
        else:
            self.startPort = None

        if hasattr(inv, 'endPort'):
            self.endPort = inv.endPort
        else:
            self.endPort = None

        if hasattr(inv, 'protocol'):
            self.protocol = inv.protocol
        else:
            self.protocol = None

        if hasattr(inv, 'allowedCidr'):
            self.allowedCidr = inv.allowedCidr
        else:
            self.allowedCidr = None



SIMULATOR_HYPERVISOR_TYPE = 'Simulator'
SIMULATOR_BACKUP_STORAGE_TYPE = 'SimulatorBackupStorage'
USER_VM_TYPE = 'UserVm'
ISCSI_FILE_SYSTEM_BACKEND_PRIMARY_STORAGE_TYPE = 'IscsiFileSystemBackendPrimaryStorage'
NFS_PRIMARY_STORAGE_TYPE = 'NFS'
VR_PUBLIC_NIC_META = '1'
VR_MANAGEMENT_NIC_META = '2'
VR_MANAGEMENT_AND_PUBLIC_NIC_META = '3'
L2_NO_VLAN_NETWORK_TYPE = 'L2NoVlanNetwork'
L2_VLAN_NETWORK_TYPE = 'L2VlanNetwork'
INGRESS = 'Ingress'
EGRESS = 'Egress'
TCP = 'TCP'
UDP = 'UDP'
ICMP = 'ICMP'
SIMULATOR_PRIMARY_STORAGE_TYPE = 'SimulatorPrimaryStorage'
VIRTUAL_ROUTER_PROVIDER_TYPE = 'VirtualRouter'
VIRTUAL_ROUTER_VM_TYPE = 'VirtualRouter'
VIRTUAL_ROUTER_OFFERING_TYPE = 'VirtualRouter'
L3_BASIC_NETWORK_TYPE = 'L3BasicNetwork'
FIRST_AVAILABLE_IP_ALLOCATOR_STRATEGY = 'FirstAvailableIpAllocatorStrategy'
RANDOM_IP_ALLOCATOR_STRATEGY = 'RandomIpAllocatorStrategy'
ZSTACK_CLUSTER_TYPE = 'zstack'
LOCAL_STORAGE_TYPE = 'LocalStorage'
SFTP_BACKUP_STORAGE_TYPE = 'SftpBackupStorage'
AND_EQ = 'AND_EQ'
AND_NOT_EQ = 'AND_NOT_EQ'
AND_GT = 'AND_GT'
AND_GTE = 'AND_GTE'
AND_LT = 'AND_LT'
AND_LTE = 'AND_LTE'
AND_IN = 'AND_IN'
AND_NOT_IN = 'AND_NOT_IN'
OR_EQ = 'OR_EQ'
OR_NOT_EQ = 'OR_NOT_EQ'
OR_GT = 'OR_GT'
OR_GTE = 'OR_GTE'
OR_LT = 'OR_LT'
OR_LTE = 'OR_LTE'
OR_IN = 'OR_IN'
OR_NOT_IN = 'OR_NOT_IN'
KVM_HYPERVISOR_TYPE = 'KVM'
INITIAL_SYSTEM_ADMIN_UUID = '36c27e8ff05c4780bf6d2fa65700f22e'
INITIAL_SYSTEM_ADMIN_NAME = 'admin'
INITIAL_SYSTEM_ADMIN_PASSWORD = 'b109f3bbbc244eb82441917ed06d618b9008dd09b3befd1b5e07394c706a8bb980b1d7785e5976ec049b46df5f1326af5a2ea6d103fd07c95385ffab0cacbc86'
ZSTACK_IMAGE_TYPE = 'zstack'
CREATED = 'Created'
STARTING = 'Starting'
RUNNING = 'Running'
STOPPING = 'Stopping'
STOPPED = 'Stopped'
REBOOTING = 'Rebooting'
DESTROYING = 'Destroying'
DESTROYED = 'Destroyed'
MIGRATING = 'Migrating'
EXPUNGING = 'Expunging'
ERROR = 'Error'
UNKNOWN = 'Unknown'
DEFAULT_PRIMARY_STORAGE_ALLOCATION_STRATEGY_TYPE = 'DefaultPrimaryStorageAllocationStrategy'

class GlobalConfig_CLOUDBUS(object):
    STATISTICS_ON = 'statistics.on'

    @staticmethod
    def get_category():
        return 'cloudBus'

class GlobalConfig_EIP(object):
    SNATINBOUNDTRAFFIC = 'snatInboundTraffic'

    @staticmethod
    def get_category():
        return 'eip'

class GlobalConfig_APPLIANCEVM(object):
    CONNECT_TIMEOUT = 'connect.timeout'
    SSH_TIMEOUT = 'ssh.timeout'
    AGENT_DEPLOYONSTART = 'agent.deployOnStart'

    @staticmethod
    def get_category():
        return 'applianceVm'

class GlobalConfig_VM(object):
    INSTANCEOFFERING_SETNULLWHENDELETING = 'instanceOffering.setNullWhenDeleting'
    DATAVOLUME_DELETEONVMDESTROY = 'dataVolume.deleteOnVmDestroy'

    @staticmethod
    def get_category():
        return 'vm'

class GlobalConfig_HOST(object):
    LOAD_ALL = 'load.all'
    LOAD_PARALLELISMDEGREE = 'load.parallelismDegree'
    PING_INTERVAL = 'ping.interval'
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'
    MAINTENANCEMODE_IGNOREERROR = 'maintenanceMode.ignoreError'
    CONNECTION_AUTORECONNECTONERROR = 'connection.autoReconnectOnError'

    @staticmethod
    def get_category():
        return 'host'

class GlobalConfig_OTHERS(object):
    TEST2 = 'Test2'

    @staticmethod
    def get_category():
        return 'Others'

class GlobalConfig_SECURITYGROUP(object):
    HOST_FAILUREWORKERINTERVAL = 'host.failureWorkerInterval'
    EGRESS_DEFAULTPOLICY = 'egress.defaultPolicy'
    INGRESS_DEFAULTPOLICY = 'ingress.defaultPolicy'
    REFRESH_DELAYINTERVAL = 'refresh.delayInterval'
    HOST_FAILURERESOLVEPERTIME = 'host.failureResolvePerTime'

    @staticmethod
    def get_category():
        return 'securityGroup'

class GlobalConfig_VIRTUALROUTER(object):
    AGENT_DEPLOYONSTART = 'agent.deployOnStart'
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'
    DNSMASQ_RESTARTAFTERNUMBEROFSIGUSER1 = 'dnsmasq.restartAfterNumberOfSIGUSER1'
    COMMAND_PARALLELISMDEGREE = 'command.parallelismDegree'
    PING_INTERVAL = 'ping.interval'

    @staticmethod
    def get_category():
        return 'virtualRouter'

class GlobalConfig_VOLUMESNAPSHOT(object):
    BACKUP_PARALLELISMDEGREE = 'backup.parallelismDegree'
    INCREMENTALSNAPSHOT_MAXNUM = 'incrementalSnapshot.maxNum'
    DELETE_PARALLELISMDEGREE = 'delete.parallelismDegree'

    @staticmethod
    def get_category():
        return 'volumeSnapshot'

class GlobalConfig_MANAGEMENTSERVER(object):
    NODE_JOINDELAY = 'node.joinDelay'
    NODE_HEARTBEATINTERVAL = 'node.heartbeatInterval'

    @staticmethod
    def get_category():
        return 'managementServer'

class GlobalConfig_BACKUPSTORAGE(object):
    PING_INTERVAL = 'ping.interval'
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'
    RESERVEDCAPACITY = 'reservedCapacity'

    @staticmethod
    def get_category():
        return 'backupStorage'

class GlobalConfig_LOG(object):
    ENABLED = 'enabled'

    @staticmethod
    def get_category():
        return 'log'

class GlobalConfig_IDENTITY(object):
    SESSION_CLEANUP_INTERVAL = 'session.cleanup.interval'
    ADMIN_SHOWALLRESOURCE = 'admin.showAllResource'
    SESSION_MAXCONCURRENT = 'session.maxConcurrent'
    SESSION_TIMEOUT = 'session.timeout'

    @staticmethod
    def get_category():
        return 'identity'

class GlobalConfig_HOSTALLOCATOR(object):
    USEPAGINATION = 'usePagination'
    RESERVEDCAPACITY_HOSTLEVEL = 'reservedCapacity.hostLevel'
    RESERVEDCAPACITY_CLUSTERLEVEL = 'reservedCapacity.clusterLevel'
    RESERVEDCAPACITY_ZONELEVEL = 'reservedCapacity.zoneLevel'
    PAGINATIONLIMIT = 'paginationLimit'

    @staticmethod
    def get_category():
        return 'hostAllocator'

class GlobalConfig_QUOTA(object):
    SECURITYGROUP_NUM = 'securityGroup.num'
    L3_NUM = 'l3.num'
    VOLUME_CAPACITY = 'volume.capacity'
    VM_MEMORYSIZE = 'vm.memorySize'
    PORTFORWARDING_NUM = 'portForwarding.num'
    EIP_NUM = 'eip.num'
    VIP_NUM = 'vip.num'
    VOLUME_DATA_NUM = 'volume.data.num'
    VM_NUM = 'vm.num'
    VM_CPUNUM = 'vm.cpuNum'

    @staticmethod
    def get_category():
        return 'quota'

class GlobalConfig_TEST(object):
    TEST3 = 'Test3'
    TEST = 'Test'
    TEST4 = 'Test4'

    @staticmethod
    def get_category():
        return 'Test'

class GlobalConfig_CONSOLE(object):
    PROXY_IDLETIMEOUT = 'proxy.idleTimeout'

    @staticmethod
    def get_category():
        return 'console'

class GlobalConfig_VOLUME(object):
    DISKOFFERING_SETNULLWHENDELETING = 'diskOffering.setNullWhenDeleting'

    @staticmethod
    def get_category():
        return 'volume'

class GlobalConfig_PORTFORWARDING(object):
    SNATINBOUNDTRAFFIC = 'snatInboundTraffic'

    @staticmethod
    def get_category():
        return 'portForwarding'

class GlobalConfig_NFSPRIMARYSTORAGE(object):
    MOUNT_BASE = 'mount.base'

    @staticmethod
    def get_category():
        return 'nfsPrimaryStorage'

class GlobalConfig_CONFIGURATION(object):
    KEY_PUBLIC = 'key.public'
    KEY_PRIVATE = 'key.private'

    @staticmethod
    def get_category():
        return 'configuration'

class GlobalConfig_PRIMARYSTORAGE(object):
    IMAGECACHE_GARBAGECOLLECTOR_INTERVAL = 'imageCache.garbageCollector.interval'
    RESERVEDCAPACITY = 'reservedCapacity'

    @staticmethod
    def get_category():
        return 'primaryStorage'

class GlobalConfig_KVM(object):
    HOST_DNSCHECKLIST = 'host.DNSCheckList'
    VM_MIGRATIONQUANTITY = 'vm.migrationQuantity'
    RESERVEDCPU = 'reservedCpu'
    DATAVOLUME_MAXNUM = 'dataVolume.maxNum'
    RESERVEDMEMORY = 'reservedMemory'
    HOST_SYNCLEVEL = 'host.syncLevel'

    @staticmethod
    def get_category():
        return 'kvm'


class QueryObjectVolumeInventory(object):
     PRIMITIVE_FIELDS = ['status','vmInstanceUuid','primaryStorageUuid','state','format','type','lastOpDate','size','description','name','installPath','diskOfferingUuid','rootImageUuid','uuid','createDate','deviceId','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['diskOffering','vmInstance','snapshot','image','primaryStorage']
     QUERY_OBJECT_MAP = {
        'diskOffering' : 'QueryObjectDiskOfferingInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'snapshot' : 'QueryObjectVolumeSnapshotInventory',
        'image' : 'QueryObjectImageInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
     }

class QueryObjectPortForwardingRuleInventory(object):
     PRIMITIVE_FIELDS = ['allowedCidr','protocolType','state','privatePortEnd','lastOpDate','vipPortStart','vipPortEnd','vmNicUuid','vipIp','guestIp','description','name','privatePortStart','uuid','createDate','vipUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vip','vmNic']
     QUERY_OBJECT_MAP = {
        'vip' : 'QueryObjectVipInventory',
        'vmNic' : 'QueryObjectVmNicInventory',
     }

class QueryObjectApplianceVmFirewallRuleInventory(object):
     PRIMITIVE_FIELDS = ['l3NetworkUuid','protocol','allowCidr','applianceVmUuid','endPort','sourceIp','destIp','createDate','lastOpDate','startPort','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectL2VlanNetworkInventory(object):
     PRIMITIVE_FIELDS = ['description','physicalInterface','name','vlan','zoneUuid','uuid','createDate','type','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','zone','cluster']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectVirtualRouterVipInventory(object):
     PRIMITIVE_FIELDS = ['virtualRouterVmUuid','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['applianceVm','vip']
     QUERY_OBJECT_MAP = {
        'vip' : 'QueryObjectVipInventory',
        'applianceVm' : 'QueryObjectApplianceVmInventory',
     }

class QueryObjectIscsiFileSystemBackendPrimaryStorageInventory(object):
     PRIMITIVE_FIELDS = ['totalPhysicalCapacity','chapUsername','status','availablePhysicalCapacity','state','mountPath','hostname','zoneUuid','type','lastOpDate','url','totalCapacity','sshUsername','filesystemType','description','name','availableCapacity','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume','volumeSnapshot','zone','cluster']
     QUERY_OBJECT_MAP = {
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'volume' : 'QueryObjectVolumeInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectNetworkServiceL3NetworkRefInventory(object):
     PRIMITIVE_FIELDS = ['l3NetworkUuid','networkServiceProviderUuid','networkServiceType','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','serviceProvider']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'serviceProvider' : 'QueryObjectNetworkServiceProviderInventory',
     }

class QueryObjectL2NetworkClusterRefInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','l2NetworkUuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l2Network','cluster']
     QUERY_OBJECT_MAP = {
        'l2Network' : 'QueryObjectL2NetworkInventory',
        'cluster' : 'QueryObjectClusterInventory',
     }

class QueryObjectSystemTagInventory(object):
     PRIMITIVE_FIELDS = ['inherent','tag','resourceUuid','uuid','createDate','type','lastOpDate','resourceType','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVmNicSecurityGroupRefInventory(object):
     PRIMITIVE_FIELDS = ['vmNicUuid','vmInstanceUuid','securityGroupUuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['securityGroup','vmNic']
     QUERY_OBJECT_MAP = {
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
        'vmNic' : 'QueryObjectVmNicInventory',
     }

class QueryObjectImageBackupStorageRefInventory(object):
     PRIMITIVE_FIELDS = ['imageUuid','installPath','backupStorageUuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','backupStorage']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
     }

class QueryObjectDiskOfferingInventory(object):
     PRIMITIVE_FIELDS = ['description','name','state','allocatorStrategy','uuid','createDate','type','sortKey','lastOpDate','diskSize','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
     }

class QueryObjectVmInstanceInventory(object):
     PRIMITIVE_FIELDS = ['imageUuid','platform','cpuSpeed','memorySize','defaultL3NetworkUuid','cpuNum','clusterUuid','state','hostUuid','allocatorStrategy','zoneUuid','type','lastOpDate','rootVolumeUuid','instanceOfferingUuid','description','name','uuid','createDate','hypervisorType','lastHostUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNics','allVolumes','vmNics','host','allVolumes','image','cluster','rootVolume','zone','instanceOffering']
     QUERY_OBJECT_MAP = {
        'host' : 'QueryObjectHostInventory',
        'vmNics' : 'QueryObjectVmNicInventory',
        'allVolumes' : 'QueryObjectVolumeInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'image' : 'QueryObjectImageInventory',
        'zone' : 'QueryObjectZoneInventory',
        'rootVolume' : 'QueryObjectVolumeInventory',
        'instanceOffering' : 'QueryObjectInstanceOfferingInventory',
     }

class QueryObjectSecurityGroupInventory(object):
     PRIMITIVE_FIELDS = ['description','name','state','uuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['rules','l3Network','vmNic']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'vmNic' : 'QueryObjectVmNicInventory',
        'rules' : 'QueryObjectSecurityGroupRuleInventory',
     }

class QueryObjectVmNicInventory(object):
     PRIMITIVE_FIELDS = ['l3NetworkUuid','gateway','vmInstanceUuid','mac','uuid','createDate','lastOpDate','deviceId','metaData','netmask','ip','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['eip','l3Network','vmInstance','portForwarding','securityGroup']
     QUERY_OBJECT_MAP = {
        'eip' : 'QueryObjectEipInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
     }

class QueryObjectHostCapacityInventory(object):
     PRIMITIVE_FIELDS = ['availableCpu','totalMemory','availableMemory','totalCpu','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectSecurityGroupL3NetworkRefInventory(object):
     PRIMITIVE_FIELDS = ['l3NetworkUuid','securityGroupUuid','uuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','securityGroup']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
     }

class QueryObjectVolumeSnapshotTreeInventory(object):
     PRIMITIVE_FIELDS = ['volumeUuid','current','uuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['snapshot','volume']
     QUERY_OBJECT_MAP = {
        'snapshot' : 'QueryObjectVolumeSnapshotInventory',
        'volume' : 'QueryObjectVolumeInventory',
     }

class QueryObjectUserPolicyRefInventory(object):
     PRIMITIVE_FIELDS = ['createDate','lastOpDate','userUuid','policyUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['policy','user']
     QUERY_OBJECT_MAP = {
        'policy' : 'QueryObjectPolicyInventory',
        'user' : 'QueryObjectUserInventory',
     }

class QueryObjectZoneInventory(object):
     PRIMITIVE_FIELDS = ['description','name','state','uuid','createDate','type','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','host','l2Network','vmInstance','cluster','primaryStorage','backupStorage']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'host' : 'QueryObjectHostInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'l2Network' : 'QueryObjectL2NetworkInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
     }

class QueryObjectClusterInventory(object):
     PRIMITIVE_FIELDS = ['description','name','state','zoneUuid','uuid','type','createDate','lastOpDate','hypervisorType','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['host','vmInstance','zone','l2Network','primaryStorage']
     QUERY_OBJECT_MAP = {
        'host' : 'QueryObjectHostInventory',
        'l2Network' : 'QueryObjectL2NetworkInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectNetworkServiceProviderL2NetworkRefInventory(object):
     PRIMITIVE_FIELDS = ['networkServiceProviderUuid','l2NetworkUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectInstanceOfferingInventory(object):
     PRIMITIVE_FIELDS = ['cpuSpeed','memorySize','cpuNum','description','name','state','allocatorStrategy','uuid','createDate','sortKey','type','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmInstance']
     QUERY_OBJECT_MAP = {
        'vmInstance' : 'QueryObjectVmInstanceInventory',
     }

class QueryObjectUserGroupUserRefInventory(object):
     PRIMITIVE_FIELDS = ['createDate','lastOpDate','userUuid','groupUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['group','user']
     QUERY_OBJECT_MAP = {
        'group' : 'QueryObjectUserGroupInventory',
        'user' : 'QueryObjectUserInventory',
     }

class QueryObjectAccountInventory(object):
     PRIMITIVE_FIELDS = ['name','uuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['quota','policy','group','user']
     QUERY_OBJECT_MAP = {
        'quota' : 'QueryObjectQuotaInventory',
        'policy' : 'QueryObjectPolicyInventory',
        'group' : 'QueryObjectUserGroupInventory',
        'user' : 'QueryObjectUserInventory',
     }

class QueryObjectUserGroupInventory(object):
     PRIMITIVE_FIELDS = ['description','name','uuid','createDate','accountUuid','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account','policy','user']
     QUERY_OBJECT_MAP = {
        'account' : 'QueryObjectAccountInventory',
        'policy' : 'QueryObjectPolicyInventory',
        'user' : 'QueryObjectUserInventory',
     }

class QueryObjectUserGroupPolicyRefInventory(object):
     PRIMITIVE_FIELDS = ['createDate','lastOpDate','policyUuid','groupUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['policy','group']
     QUERY_OBJECT_MAP = {
        'policy' : 'QueryObjectPolicyInventory',
        'group' : 'QueryObjectUserGroupInventory',
     }

class QueryObjectVirtualRouterVmInventory(object):
     PRIMITIVE_FIELDS = ['cpuSpeed','clusterUuid','state','zoneUuid','allocatorStrategy','type','lastOpDate','applianceVmType','rootVolumeUuid','description','name','createDate','hypervisorType','publicNetworkUuid','imageUuid','platform','status','defaultL3NetworkUuid','memorySize','cpuNum','hostUuid','defaultRouteL3NetworkUuid','instanceOfferingUuid','uuid','managementNetworkUuid','lastHostUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['allVolumes','vmNics','host','vmNics','allVolumes','cluster','image','zone','rootVolume','virtualRouterOffering','vip','eip','portForwarding']
     QUERY_OBJECT_MAP = {
        'eip' : 'QueryObjectEipInventory',
        'vip' : 'QueryObjectVipInventory',
        'host' : 'QueryObjectHostInventory',
        'vmNics' : 'QueryObjectVmNicInventory',
        'allVolumes' : 'QueryObjectVolumeInventory',
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
        'image' : 'QueryObjectImageInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'virtualRouterOffering' : 'QueryObjectVirtualRouterOfferingInventory',
        'rootVolume' : 'QueryObjectVolumeInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectBackupStorageZoneRefInventory(object):
     PRIMITIVE_FIELDS = ['id','backupStorageUuid','zoneUuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['backupStorage','zone']
     QUERY_OBJECT_MAP = {
        'backupStorage' : 'QueryObjectBackupStorageInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectBackupStorageInventory(object):
     PRIMITIVE_FIELDS = ['totalCapacity','status','description','name','state','availableCapacity','uuid','createDate','type','lastOpDate','url','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volumeSnapshot','image','zone']
     QUERY_OBJECT_MAP = {
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'image' : 'QueryObjectImageInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectUserTagInventory(object):
     PRIMITIVE_FIELDS = ['tag','resourceUuid','uuid','createDate','type','lastOpDate','resourceType','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectIpRangeInventory(object):
     PRIMITIVE_FIELDS = ['l3NetworkUuid','gateway','endIp','startIp','networkCidr','description','name','uuid','createDate','lastOpDate','netmask','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
     }

class QueryObjectL2NetworkInventory(object):
     PRIMITIVE_FIELDS = ['description','physicalInterface','name','zoneUuid','uuid','createDate','type','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','zone','cluster']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectEipInventory(object):
     PRIMITIVE_FIELDS = ['vmNicUuid','vipIp','guestIp','description','name','state','uuid','createDate','vipUuid','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vip','vmNic']
     QUERY_OBJECT_MAP = {
        'vip' : 'QueryObjectVipInventory',
        'vmNic' : 'QueryObjectVmNicInventory',
     }

class QueryObjectVolumeSnapshotBackupStorageRefInventory(object):
     PRIMITIVE_FIELDS = ['installPath','backupStorageUuid','volumeSnapshotUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volumeSnapshot','backupStorage']
     QUERY_OBJECT_MAP = {
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
     }

class QueryObjectVirtualRouterPortForwardingRuleRefInventory(object):
     PRIMITIVE_FIELDS = ['virtualRouterVmUuid','uuid','vipUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['applianceVm','vip','portForwarding']
     QUERY_OBJECT_MAP = {
        'vip' : 'QueryObjectVipInventory',
        'applianceVm' : 'QueryObjectApplianceVmInventory',
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
     }

class QueryObjectHostInventory(object):
     PRIMITIVE_FIELDS = ['availableMemoryCapacity','totalCpuCapacity','status','clusterUuid','state','managementIp','zoneUuid','lastOpDate','totalMemoryCapacity','availableCpuCapacity','description','name','uuid','createDate','hypervisorType','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmInstance','cluster','zone']
     QUERY_OBJECT_MAP = {
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectUserInventory(object):
     PRIMITIVE_FIELDS = ['name','uuid','createDate','accountUuid','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account','policy','group']
     QUERY_OBJECT_MAP = {
        'account' : 'QueryObjectAccountInventory',
        'policy' : 'QueryObjectPolicyInventory',
        'group' : 'QueryObjectUserGroupInventory',
     }

class QueryObjectPrimaryStorageCapacityInventory(object):
     PRIMITIVE_FIELDS = ['totalPhysicalCapacity','totalCapacity','availablePhsicalCapacity','availableCapacity','uuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVolumeSnapshotInventory(object):
     PRIMITIVE_FIELDS = ['primaryStorageInstallPath','status','parentUuid','treeUuid','primaryStorageUuid','state','format','type','lastOpDate','size','volumeUuid','description','name','uuid','createDate','latest','volumeType','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['backupStorageRefs','tree','backupStorageRef','volume','primaryStorage','backupStorage']
     QUERY_OBJECT_MAP = {
        'tree' : 'QueryObjectVolumeSnapshotTreeInventory',
        'backupStorageRef' : 'QueryObjectVolumeSnapshotBackupStorageRefInventory',
        'backupStorageRefs' : 'QueryObjectVolumeSnapshotBackupStorageRefInventory',
        'volume' : 'QueryObjectVolumeInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
     }

class QueryObjectNetworkServiceTypeInventory(object):
     PRIMITIVE_FIELDS = ['networkServiceProviderUuid','type','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectL3NetworkInventory(object):
     PRIMITIVE_FIELDS = ['l2NetworkUuid','state','zoneUuid','type','lastOpDate','system','dnsDomain','description','name','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['ipRanges','networkServices','l2Network','vmNic','zone','serviceProvider']
     QUERY_OBJECT_MAP = {
        'ipRanges' : 'QueryObjectIpRangeInventory',
        'networkServices' : 'QueryObjectNetworkServiceL3NetworkRefInventory',
        'l2Network' : 'QueryObjectL2NetworkInventory',
        'vmNic' : 'QueryObjectVmNicInventory',
        'serviceProvider' : 'QueryObjectNetworkServiceProviderInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectQuotaInventory(object):
     PRIMITIVE_FIELDS = ['identityType','name','value','identityUuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account']
     QUERY_OBJECT_MAP = {
        'account' : 'QueryObjectAccountInventory',
     }

class QueryObjectVirtualRouterOfferingInventory(object):
     PRIMITIVE_FIELDS = ['imageUuid','cpuSpeed','memorySize','cpuNum','state','allocatorStrategy','zoneUuid','sortKey','type','lastOpDate','isDefault','description','name','uuid','createDate','managementNetworkUuid','publicNetworkUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','managementL3Network','publicL3Network','zone']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'managementL3Network' : 'QueryObjectL3NetworkInventory',
        'publicL3Network' : 'QueryObjectL3NetworkInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectManagementNodeInventory(object):
     PRIMITIVE_FIELDS = ['joinDate','hostName','heartBeat','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVirtualRouterEipRefInventory(object):
     PRIMITIVE_FIELDS = ['virtualRouterVmUuid','eipUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['applianceVm','eip']
     QUERY_OBJECT_MAP = {
        'eip' : 'QueryObjectEipInventory',
        'applianceVm' : 'QueryObjectApplianceVmInventory',
     }

class QueryObjectConsoleProxyInventory(object):
     PRIMITIVE_FIELDS = ['vmInstanceUuid','agentIp','status','proxyPort','proxyIdentity','lastOpDate','scheme','token','proxyHostname','targetPort','agentType','uuid','createDate','targetHostname','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectSftpBackupStorageInventory(object):
     PRIMITIVE_FIELDS = ['totalCapacity','status','description','name','state','availableCapacity','hostname','uuid','createDate','type','lastOpDate','url','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volumeSnapshot','image','zone']
     QUERY_OBJECT_MAP = {
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'image' : 'QueryObjectImageInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectPrimaryStorageInventory(object):
     PRIMITIVE_FIELDS = ['totalPhysicalCapacity','status','availablePhysicalCapacity','state','mountPath','zoneUuid','type','lastOpDate','url','totalCapacity','description','name','availableCapacity','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volumeSnapshot','volume','zone','cluster']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectImageInventory(object):
     PRIMITIVE_FIELDS = ['platform','status','state','md5Sum','format','type','lastOpDate','url','mediaType','size','system','description','name','guestOsType','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['backupStorageRefs','volume','backupStorage']
     QUERY_OBJECT_MAP = {
        'backupStorageRefs' : 'QueryObjectImageBackupStorageRefInventory',
        'volume' : 'QueryObjectVolumeInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
     }

class QueryObjectGlobalConfigInventory(object):
     PRIMITIVE_FIELDS = ['category','description','name','value','defaultValue','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectApplianceVmInventory(object):
     PRIMITIVE_FIELDS = ['cpuSpeed','clusterUuid','state','zoneUuid','allocatorStrategy','type','applianceVmType','rootVolumeUuid','lastOpDate','description','name','createDate','hypervisorType','imageUuid','platform','status','defaultL3NetworkUuid','memorySize','cpuNum','hostUuid','defaultRouteL3NetworkUuid','instanceOfferingUuid','uuid','lastHostUuid','managementNetworkUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['allVolumes','vmNics','host','vmNics','allVolumes','cluster','image','zone','rootVolume','virtualRouterOffering','vip','eip','portForwarding']
     QUERY_OBJECT_MAP = {
        'eip' : 'QueryObjectEipInventory',
        'vip' : 'QueryObjectVipInventory',
        'host' : 'QueryObjectHostInventory',
        'vmNics' : 'QueryObjectVmNicInventory',
        'allVolumes' : 'QueryObjectVolumeInventory',
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
        'image' : 'QueryObjectImageInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'virtualRouterOffering' : 'QueryObjectVirtualRouterOfferingInventory',
        'rootVolume' : 'QueryObjectVolumeInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectPolicyInventory(object):
     PRIMITIVE_FIELDS = ['name','uuid','accountUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account','group','user']
     QUERY_OBJECT_MAP = {
        'account' : 'QueryObjectAccountInventory',
        'group' : 'QueryObjectUserGroupInventory',
        'user' : 'QueryObjectUserInventory',
     }

class QueryObjectSimulatorHostInventory(object):
     PRIMITIVE_FIELDS = ['memoryCapacity','availableMemoryCapacity','totalCpuCapacity','status','clusterUuid','state','managementIp','zoneUuid','lastOpDate','totalMemoryCapacity','availableCpuCapacity','cpuCapacity','description','name','uuid','createDate','hypervisorType','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectL3NetworkDnsInventory(object):
     PRIMITIVE_FIELDS = ['l3NetworkUuid','dns','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectKVMHostInventory(object):
     PRIMITIVE_FIELDS = ['availableMemoryCapacity','totalCpuCapacity','status','clusterUuid','state','managementIp','zoneUuid','lastOpDate','totalMemoryCapacity','username','availableCpuCapacity','description','name','uuid','createDate','hypervisorType','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmInstance','cluster','zone']
     QUERY_OBJECT_MAP = {
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectNetworkServiceProviderInventory(object):
     PRIMITIVE_FIELDS = ['description','name','uuid','createDate','type','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectIpUseInventory(object):
     PRIMITIVE_FIELDS = ['details','serviceId','use','usedIpUuid','uuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectPrimaryStorageClusterRefInventory(object):
     PRIMITIVE_FIELDS = ['id','primaryStorageUuid','clusterUuid','createDate','lastOpDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','primaryStorage']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
     }

class QueryObjectVipInventory(object):
     PRIMITIVE_FIELDS = ['l3NetworkUuid','gateway','state','peerL3NetworkUuid','lastOpDate','netmask','ip','description','name','useFor','uuid','createDate','serviceProvider','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['eip','portForwarding']
     QUERY_OBJECT_MAP = {
        'eip' : 'QueryObjectEipInventory',
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
     }

class QueryObjectAccountResourceRefInventory(object):
     PRIMITIVE_FIELDS = ['resourceUuid','isShared','permission','createDate','accountUuid','lastOpDate','ownerAccountUuid','resourceType','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectSecurityGroupRuleInventory(object):
     PRIMITIVE_FIELDS = ['allowedCidr','protocol','endPort','state','securityGroupUuid','uuid','createDate','type','lastOpDate','startPort','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['securityGroup']
     QUERY_OBJECT_MAP = {
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
     }


queryMessageInventoryMap = {
     'APIQueryVolumeMsg' : QueryObjectVolumeInventory,
     'APIQueryPortForwardingRuleMsg' : QueryObjectPortForwardingRuleInventory,
     'APIQueryL2VlanNetworkMsg' : QueryObjectL2VlanNetworkInventory,
     'APIQueryHostMsg' : QueryObjectHostInventory,
     'APIQueryUserMsg' : QueryObjectUserInventory,
     'APIQueryIscsiFileSystemBackendPrimaryStorageMsg' : QueryObjectIscsiFileSystemBackendPrimaryStorageInventory,
     'APIQueryNetworkServiceL3NetworkRefMsg' : QueryObjectNetworkServiceL3NetworkRefInventory,
     'APIQuerySystemTagMsg' : QueryObjectSystemTagInventory,
     'APIQueryVolumeSnapshotMsg' : QueryObjectVolumeSnapshotInventory,
     'APIQueryDiskOfferingMsg' : QueryObjectDiskOfferingInventory,
     'APIQueryL3NetworkMsg' : QueryObjectL3NetworkInventory,
     'APIQueryQuotaMsg' : QueryObjectQuotaInventory,
     'APIQueryVirtualRouterOfferingMsg' : QueryObjectVirtualRouterOfferingInventory,
     'APIQueryVmInstanceMsg' : QueryObjectVmInstanceInventory,
     'APIQueryManagementNodeMsg' : QueryObjectManagementNodeInventory,
     'APIQuerySecurityGroupMsg' : QueryObjectSecurityGroupInventory,
     'APIQueryVmNicMsg' : QueryObjectVmNicInventory,
     'APIQuerySftpBackupStorageMsg' : QueryObjectSftpBackupStorageInventory,
     'APIQueryPrimaryStorageMsg' : QueryObjectPrimaryStorageInventory,
     'APIQueryImageMsg' : QueryObjectImageInventory,
     'APIQueryGlobalConfigMsg' : QueryObjectGlobalConfigInventory,
     'APIQueryVolumeSnapshotTreeMsg' : QueryObjectVolumeSnapshotTreeInventory,
     'APIQueryApplianceVmMsg' : QueryObjectApplianceVmInventory,
     'APIQueryZoneMsg' : QueryObjectZoneInventory,
     'APIQueryClusterMsg' : QueryObjectClusterInventory,
     'APIQueryPolicyMsg' : QueryObjectPolicyInventory,
     'APIQueryInstanceOfferingMsg' : QueryObjectInstanceOfferingInventory,
     'APIQueryNetworkServiceProviderMsg' : QueryObjectNetworkServiceProviderInventory,
     'APIQueryAccountMsg' : QueryObjectAccountInventory,
     'APIQueryUserGroupMsg' : QueryObjectUserGroupInventory,
     'APIQueryVirtualRouterVmMsg' : QueryObjectVirtualRouterVmInventory,
     'APIQueryBackupStorageMsg' : QueryObjectBackupStorageInventory,
     'APIQueryUserTagMsg' : QueryObjectUserTagInventory,
     'APIQueryIpRangeMsg' : QueryObjectIpRangeInventory,
     'APIQueryVipMsg' : QueryObjectVipInventory,
     'APIQueryL2NetworkMsg' : QueryObjectL2NetworkInventory,
     'APIQuerySecurityGroupRuleMsg' : QueryObjectSecurityGroupRuleInventory,
     'APIQueryEipMsg' : QueryObjectEipInventory,
}
