

class NotNoneField(object):
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


APISYNCCALLMESSAGE_FULL_NAME = 'org.zstack.header.message.APISyncCallMessage'
class APISyncCallMessage(APIMessage):
    FULL_NAME='org.zstack.header.message.APISyncCallMessage'
    def __init__(self):
        super(APISyncCallMessage, self).__init__()


APILISTMESSAGE_FULL_NAME = 'org.zstack.header.message.APIListMessage'
class APIListMessage(APISyncCallMessage):
    FULL_NAME='org.zstack.header.message.APIListMessage'
    def __init__(self):
        super(APIListMessage, self).__init__()
        self.length = None
        self.offset = None
        self.uuids = None


APIDELETEMESSAGE_FULL_NAME = 'org.zstack.header.message.APIDeleteMessage'
class APIDeleteMessage(APIMessage):
    FULL_NAME='org.zstack.header.message.APIDeleteMessage'
    def __init__(self):
        super(APIDeleteMessage, self).__init__()
        self.deleteMode = None


APISEARCHMESSAGE_FULL_NAME = 'org.zstack.header.search.APISearchMessage'
class APISearchMessage(APIMessage):
    FULL_NAME='org.zstack.header.search.APISearchMessage'
    def __init__(self):
        super(APISearchMessage, self).__init__()
        self.fields = None
        self.nameOpValueTriples = None
        self.nameOpListTriples = None
        self.start = None
        self.size = None
        self.inventoryUuid = None


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


APILISTGLOBALCONFIGMSG_FULL_NAME = 'org.zstack.core.config.APIListGlobalConfigMsg'
class APIListGlobalConfigMsg(APIListMessage):
    FULL_NAME='org.zstack.core.config.APIListGlobalConfigMsg'
    def __init__(self):
        super(APIListGlobalConfigMsg, self).__init__()
        self.ids = None


APIGETGLOBALCONFIGMSG_FULL_NAME = 'org.zstack.core.config.APIGetGlobalConfigMsg'
class APIGetGlobalConfigMsg(APIMessage):
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
        self.inventory = NotNoneField()


APIQUERYMESSAGE_FULL_NAME = 'org.zstack.header.query.APIQueryMessage'
class APIQueryMessage(APISyncCallMessage):
    FULL_NAME='org.zstack.header.query.APIQueryMessage'
    def __init__(self):
        super(APIQueryMessage, self).__init__()
        #mandatory field
        self.conditions = NotNoneField()
        self.limit = None
        self.start = None
        self.count = None


APIQUERYTAGMSG_FULL_NAME = 'org.zstack.tag.APIQueryTagMsg'
class APIQueryTagMsg(APIQueryMessage):
    FULL_NAME='org.zstack.tag.APIQueryTagMsg'
    def __init__(self):
        super(APIQueryTagMsg, self).__init__()
        self.systemTag = None


APIQUERYTAGREPLY_FULL_NAME = 'org.zstack.tag.APIQueryTagReply'
class APIQueryTagReply(APIReply):
    FULL_NAME='org.zstack.tag.APIQueryTagReply'
    def __init__(self):
        super(APIQueryTagReply, self).__init__()
        self.inventories = None


APIGENERATEINVENTORYQUERYDETAILSMSG_FULL_NAME = 'org.zstack.header.query.APIGenerateInventoryQueryDetailsMsg'
class APIGenerateInventoryQueryDetailsMsg(APIMessage):
    FULL_NAME='org.zstack.header.query.APIGenerateInventoryQueryDetailsMsg'
    def __init__(self):
        super(APIGenerateInventoryQueryDetailsMsg, self).__init__()
        self.outputDir = None
        self.basePackageNames = None


APIQUERYCOUNTREPLY_FULL_NAME = 'org.zstack.header.query.APIQueryCountReply'
class APIQueryCountReply(APIReply):
    FULL_NAME='org.zstack.header.query.APIQueryCountReply'
    def __init__(self):
        super(APIQueryCountReply, self).__init__()
        self.amount = None


APIRETRIEVEHOSTCAPACITYMSG_FULL_NAME = 'org.zstack.header.allocator.APIRetrieveHostCapacityMsg'
class APIRetrieveHostCapacityMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.allocator.APIRetrieveHostCapacityMsg'
    def __init__(self):
        super(APIRetrieveHostCapacityMsg, self).__init__()
        #mandatory field
        self.selector = NotNoneField()
        #mandatory field
        self.selectorUuid = NotNoneField()


APIRETRIEVEHOSTCAPACITYREPLY_FULL_NAME = 'org.zstack.header.allocator.APIRetrieveHostCapacityReply'
class APIRetrieveHostCapacityReply(APIReply):
    FULL_NAME='org.zstack.header.allocator.APIRetrieveHostCapacityReply'
    def __init__(self):
        super(APIRetrieveHostCapacityReply, self).__init__()
        self.totalCpu = None
        self.usedCpu = None
        self.totalMemory = None
        self.usedMemory = None


APIGETHOSTALLOCATORSTRATEGIESMSG_FULL_NAME = 'org.zstack.header.allocator.APIGetHostAllocatorStrategiesMsg'
class APIGetHostAllocatorStrategiesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.allocator.APIGetHostAllocatorStrategiesMsg'
    def __init__(self):
        super(APIGetHostAllocatorStrategiesMsg, self).__init__()


APIGETHOSTALLOCATORSTRATEGIESREPLY_FULL_NAME = 'org.zstack.header.allocator.APIGetHostAllocatorStrategiesReply'
class APIGetHostAllocatorStrategiesReply(APIReply):
    FULL_NAME='org.zstack.header.allocator.APIGetHostAllocatorStrategiesReply'
    def __init__(self):
        super(APIGetHostAllocatorStrategiesReply, self).__init__()
        self.hostAllocatorStrategies = None


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


APIATTACHVOLUMETOVMMSG_FULL_NAME = 'org.zstack.header.vm.APIAttachVolumeToVmMsg'
class APIAttachVolumeToVmMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIAttachVolumeToVmMsg'
    def __init__(self):
        super(APIAttachVolumeToVmMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.volumeUuid = NotNoneField()


APIDETACHVOLUMEFROMVMMSG_FULL_NAME = 'org.zstack.header.vm.APIDetachVolumeFromVmMsg'
class APIDetachVolumeFromVmMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIDetachVolumeFromVmMsg'
    def __init__(self):
        super(APIDetachVolumeFromVmMsg, self).__init__()
        #mandatory field
        self.volumeUuid = NotNoneField()


APILISTVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIListVmInstanceReply'
class APIListVmInstanceReply(APIReply):
    FULL_NAME='org.zstack.header.vm.APIListVmInstanceReply'
    def __init__(self):
        super(APIListVmInstanceReply, self).__init__()
        self.inventories = None


APISEARCHVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APISearchVmInstanceMsg'
class APISearchVmInstanceMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.vm.APISearchVmInstanceMsg'
    def __init__(self):
        super(APISearchVmInstanceMsg, self).__init__()


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
        self.inventories = None


APIDESTROYVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIDestroyVmInstanceMsg'
class APIDestroyVmInstanceMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.vm.APIDestroyVmInstanceMsg'
    def __init__(self):
        super(APIDestroyVmInstanceMsg, self).__init__()
        self.uuid = None


APIQUERYVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIQueryVmInstanceMsg'
class APIQueryVmInstanceMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.vm.APIQueryVmInstanceMsg'
    def __init__(self):
        super(APIQueryVmInstanceMsg, self).__init__()


APILISTVMNICMSG_FULL_NAME = 'org.zstack.header.vm.APIListVmNicMsg'
class APIListVmNicMsg(APIListMessage):
    FULL_NAME='org.zstack.header.vm.APIListVmNicMsg'
    def __init__(self):
        super(APIListVmNicMsg, self).__init__()


APIATTACHNICTOVMMSG_FULL_NAME = 'org.zstack.header.vm.APIAttachNicToVmMsg'
class APIAttachNicToVmMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIAttachNicToVmMsg'
    def __init__(self):
        super(APIAttachNicToVmMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()


APILISTVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIListVmInstanceMsg'
class APIListVmInstanceMsg(APIListMessage):
    FULL_NAME='org.zstack.header.vm.APIListVmInstanceMsg'
    def __init__(self):
        super(APIListVmInstanceMsg, self).__init__()


APIQUERYVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIQueryVmInstanceReply'
class APIQueryVmInstanceReply(APIReply):
    FULL_NAME='org.zstack.header.vm.APIQueryVmInstanceReply'
    def __init__(self):
        super(APIQueryVmInstanceReply, self).__init__()
        self.inventories = None


APIREBOOTVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIRebootVmInstanceMsg'
class APIRebootVmInstanceMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIRebootVmInstanceMsg'
    def __init__(self):
        super(APIRebootVmInstanceMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIQUERYVMNICREPLY_FULL_NAME = 'org.zstack.header.vm.APIQueryVmNicReply'
class APIQueryVmNicReply(APIReply):
    FULL_NAME='org.zstack.header.vm.APIQueryVmNicReply'
    def __init__(self):
        super(APIQueryVmNicReply, self).__init__()
        self.inventories = None


APICREATEMESSAGE_FULL_NAME = 'org.zstack.header.message.APICreateMessage'
class APICreateMessage(APIMessage):
    FULL_NAME='org.zstack.header.message.APICreateMessage'
    def __init__(self):
        super(APICreateMessage, self).__init__()
        self.resourceUuid = None


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
        self.l3NetworkUuids = NotNoneField()
        self.type = None
        self.rootDiskOfferingUuid = None
        self.dataDiskOfferingUuids = None
        self.zoneUuid = None
        self.clusterUuid = None
        self.hostUuid = None
        self.description = None


APIGETMESSAGE_FULL_NAME = 'org.zstack.header.search.APIGetMessage'
class APIGetMessage(APIMessage):
    FULL_NAME='org.zstack.header.search.APIGetMessage'
    def __init__(self):
        super(APIGetMessage, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIGETVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmInstanceMsg'
class APIGetVmInstanceMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.vm.APIGetVmInstanceMsg'
    def __init__(self):
        super(APIGetVmInstanceMsg, self).__init__()


APISTARTVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIStartVmInstanceMsg'
class APIStartVmInstanceMsg(APIMessage):
    FULL_NAME='org.zstack.header.vm.APIStartVmInstanceMsg'
    def __init__(self):
        super(APIStartVmInstanceMsg, self).__init__()
        self.uuid = None


APICREATETEMPLATEFROMROOTVOLUMEMSG_FULL_NAME = 'org.zstack.header.image.APICreateTemplateFromRootVolumeMsg'
class APICreateTemplateFromRootVolumeMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.image.APICreateTemplateFromRootVolumeMsg'
    def __init__(self):
        super(APICreateTemplateFromRootVolumeMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.guestOsType = NotNoneField()
        #mandatory field
        self.backupStorageUuid = NotNoneField()
        #mandatory field
        self.rootVolumeUuid = NotNoneField()
        #mandatory field
        #valid values: [64, 32]
        self.bits = NotNoneField()


APICHANGEIMAGESTATEMSG_FULL_NAME = 'org.zstack.header.image.APIChangeImageStateMsg'
class APIChangeImageStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.image.APIChangeImageStateMsg'
    def __init__(self):
        super(APIChangeImageStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.stateEvent = NotNoneField()


APIGETIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIGetImageMsg'
class APIGetImageMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.image.APIGetImageMsg'
    def __init__(self):
        super(APIGetImageMsg, self).__init__()


APICREATETEMPLATEFROMVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.image.APICreateTemplateFromVolumeSnapshotMsg'
class APICreateTemplateFromVolumeSnapshotMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.image.APICreateTemplateFromVolumeSnapshotMsg'
    def __init__(self):
        super(APICreateTemplateFromVolumeSnapshotMsg, self).__init__()
        #mandatory field
        self.snapshotUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.guestOsType = NotNoneField()
        #mandatory field
        #valid values: [64, 32]
        self.bits = NotNoneField()
        self.backupStorageUuid = None
        self.failOverToOtherBackupStorage = None


APIDELETEIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIDeleteImageMsg'
class APIDeleteImageMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.image.APIDeleteImageMsg'
    def __init__(self):
        super(APIDeleteImageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APISEARCHIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APISearchImageMsg'
class APISearchImageMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.image.APISearchImageMsg'
    def __init__(self):
        super(APISearchImageMsg, self).__init__()


APIGETIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIGetImageReply'
class APIGetImageReply(APIGetReply):
    FULL_NAME='org.zstack.header.image.APIGetImageReply'
    def __init__(self):
        super(APIGetImageReply, self).__init__()


APIQUERYIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIQueryImageReply'
class APIQueryImageReply(APIReply):
    FULL_NAME='org.zstack.header.image.APIQueryImageReply'
    def __init__(self):
        super(APIQueryImageReply, self).__init__()
        self.inventories = None


APILISTIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIListImageReply'
class APIListImageReply(APIReply):
    FULL_NAME='org.zstack.header.image.APIListImageReply'
    def __init__(self):
        super(APIListImageReply, self).__init__()
        self.inventories = None


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


APILISTIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIListImageMsg'
class APIListImageMsg(APIListMessage):
    FULL_NAME='org.zstack.header.image.APIListImageMsg'
    def __init__(self):
        super(APIListImageMsg, self).__init__()


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
        #mandatory field
        #valid values: [64, 32]
        self.bits = NotNoneField()
        #mandatory field
        #valid values: [Template, ISO]
        self.format = NotNoneField()
        #mandatory field
        self.guestOsType = NotNoneField()
        self.hypervisorType = None
        #mandatory field
        self.backupStorageUuid = NotNoneField()
        self.imageType = None
        self.imageSize = None


APIREQUESTCONSOLEACCESSMSG_FULL_NAME = 'org.zstack.header.console.APIRequestConsoleAccessMsg'
class APIRequestConsoleAccessMsg(APIMessage):
    FULL_NAME='org.zstack.header.console.APIRequestConsoleAccessMsg'
    def __init__(self):
        super(APIRequestConsoleAccessMsg, self).__init__()
        #mandatory field
        self.vmInstanceUuid = NotNoneField()


APISEARCHVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APISearchVolumeMsg'
class APISearchVolumeMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.volume.APISearchVolumeMsg'
    def __init__(self):
        super(APISearchVolumeMsg, self).__init__()


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


APIQUERYVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APIQueryVolumeReply'
class APIQueryVolumeReply(APIReply):
    FULL_NAME='org.zstack.header.volume.APIQueryVolumeReply'
    def __init__(self):
        super(APIQueryVolumeReply, self).__init__()
        self.inventories = None


APIGETVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeMsg'
class APIGetVolumeMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeMsg'
    def __init__(self):
        super(APIGetVolumeMsg, self).__init__()


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
        self.inventories = None


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


APILISTVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIListVolumeMsg'
class APIListVolumeMsg(APIListMessage):
    FULL_NAME='org.zstack.header.volume.APIListVolumeMsg'
    def __init__(self):
        super(APIListVolumeMsg, self).__init__()


APICHANGEVOLUMESTATEMSG_FULL_NAME = 'org.zstack.header.volume.APIChangeVolumeStateMsg'
class APIChangeVolumeStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.volume.APIChangeVolumeStateMsg'
    def __init__(self):
        super(APIChangeVolumeStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.stateEvent = NotNoneField()


APIISREADYTOGOMSG_FULL_NAME = 'org.zstack.header.apimediator.APIIsReadyToGoMsg'
class APIIsReadyToGoMsg(APIMessage):
    FULL_NAME='org.zstack.header.apimediator.APIIsReadyToGoMsg'
    def __init__(self):
        super(APIIsReadyToGoMsg, self).__init__()
        self.managementNodeId = None


APILISTDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIListDiskOfferingMsg'
class APIListDiskOfferingMsg(APIListMessage):
    FULL_NAME='org.zstack.header.configuration.APIListDiskOfferingMsg'
    def __init__(self):
        super(APIListDiskOfferingMsg, self).__init__()


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
        self.basePackageNames = None


APIQUERYINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIQueryInstanceOfferingMsg'
class APIQueryInstanceOfferingMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.configuration.APIQueryInstanceOfferingMsg'
    def __init__(self):
        super(APIQueryInstanceOfferingMsg, self).__init__()


APIGENERATEAPIJSONTEMPLATEMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateApiJsonTemplateMsg'
class APIGenerateApiJsonTemplateMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIGenerateApiJsonTemplateMsg'
    def __init__(self):
        super(APIGenerateApiJsonTemplateMsg, self).__init__()
        self.exportPath = None
        self.basePackageNames = None


APILISTDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIListDiskOfferingReply'
class APIListDiskOfferingReply(APIReply):
    FULL_NAME='org.zstack.header.configuration.APIListDiskOfferingReply'
    def __init__(self):
        super(APIListDiskOfferingReply, self).__init__()
        self.inventories = None


APIGETINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIGetInstanceOfferingMsg'
class APIGetInstanceOfferingMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.configuration.APIGetInstanceOfferingMsg'
    def __init__(self):
        super(APIGetInstanceOfferingMsg, self).__init__()


APIADDDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIAddDiskOfferingMsg'
class APIAddDiskOfferingMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.configuration.APIAddDiskOfferingMsg'
    def __init__(self):
        super(APIAddDiskOfferingMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.diskSize = NotNoneField()
        self.sortKey = None
        self.allocatorStrategy = None
        self.type = None


APILISTINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIListInstanceOfferingMsg'
class APIListInstanceOfferingMsg(APIListMessage):
    FULL_NAME='org.zstack.header.configuration.APIListInstanceOfferingMsg'
    def __init__(self):
        super(APIListInstanceOfferingMsg, self).__init__()


APISEARCHDNSMSG_FULL_NAME = 'org.zstack.header.configuration.APISearchDnsMsg'
class APISearchDnsMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.configuration.APISearchDnsMsg'
    def __init__(self):
        super(APISearchDnsMsg, self).__init__()


APILISTINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIListInstanceOfferingReply'
class APIListInstanceOfferingReply(APIReply):
    FULL_NAME='org.zstack.header.configuration.APIListInstanceOfferingReply'
    def __init__(self):
        super(APIListInstanceOfferingReply, self).__init__()
        self.inventories = None


APISEARCHDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APISearchDiskOfferingMsg'
class APISearchDiskOfferingMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.configuration.APISearchDiskOfferingMsg'
    def __init__(self):
        super(APISearchDiskOfferingMsg, self).__init__()


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
        self.basePackageNames = None


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
class APIQueryDiskOfferingReply(APIReply):
    FULL_NAME='org.zstack.header.configuration.APIQueryDiskOfferingReply'
    def __init__(self):
        super(APIQueryDiskOfferingReply, self).__init__()
        self.inventories = None


APICHANGEINSTANCEOFFERINGSTATEMSG_FULL_NAME = 'org.zstack.header.configuration.APIChangeInstanceOfferingStateMsg'
class APIChangeInstanceOfferingStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIChangeInstanceOfferingStateMsg'
    def __init__(self):
        super(APIChangeInstanceOfferingStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.stateEvent = NotNoneField()


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


APIGETDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIGetDiskOfferingMsg'
class APIGetDiskOfferingMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.configuration.APIGetDiskOfferingMsg'
    def __init__(self):
        super(APIGetDiskOfferingMsg, self).__init__()


APIADDINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIAddInstanceOfferingMsg'
class APIAddInstanceOfferingMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.configuration.APIAddInstanceOfferingMsg'
    def __init__(self):
        super(APIAddInstanceOfferingMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.cpuNum = NotNoneField()
        #mandatory field
        self.cpuSpeed = NotNoneField()
        #mandatory field
        self.memorySize = NotNoneField()
        self.hostTag = None
        self.allocatorStrategy = None
        self.sortKey = None
        self.type = None
        self.ha = None


APICHANGEDISKOFFERINGSTATEMSG_FULL_NAME = 'org.zstack.header.configuration.APIChangeDiskOfferingStateMsg'
class APIChangeDiskOfferingStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.configuration.APIChangeDiskOfferingStateMsg'
    def __init__(self):
        super(APIChangeDiskOfferingStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.stateEvent = NotNoneField()


APIGETDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIGetDiskOfferingReply'
class APIGetDiskOfferingReply(APIGetReply):
    FULL_NAME='org.zstack.header.configuration.APIGetDiskOfferingReply'
    def __init__(self):
        super(APIGetDiskOfferingReply, self).__init__()


APISEARCHINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APISearchInstanceOfferingMsg'
class APISearchInstanceOfferingMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.configuration.APISearchInstanceOfferingMsg'
    def __init__(self):
        super(APISearchInstanceOfferingMsg, self).__init__()


APIQUERYINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIQueryInstanceOfferingReply'
class APIQueryInstanceOfferingReply(APIReply):
    FULL_NAME='org.zstack.header.configuration.APIQueryInstanceOfferingReply'
    def __init__(self):
        super(APIQueryInstanceOfferingReply, self).__init__()
        self.inventories = None


APILISTPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIListPrimaryStorageReply'
class APIListPrimaryStorageReply(APIReply):
    FULL_NAME='org.zstack.header.storage.primary.APIListPrimaryStorageReply'
    def __init__(self):
        super(APIListPrimaryStorageReply, self).__init__()
        self.inventories = None


APIATTACHPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIAttachPrimaryStorageMsg'
class APIAttachPrimaryStorageMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIAttachPrimaryStorageMsg'
    def __init__(self):
        super(APIAttachPrimaryStorageMsg, self).__init__()
        #mandatory field
        self.clusterUuid = NotNoneField()
        #mandatory field
        self.primaryStorageUuid = NotNoneField()


APISEARCHPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APISearchPrimaryStorageMsg'
class APISearchPrimaryStorageMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.storage.primary.APISearchPrimaryStorageMsg'
    def __init__(self):
        super(APISearchPrimaryStorageMsg, self).__init__()


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
        self.primaryStorageTypes = None


APILISTPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIListPrimaryStorageMsg'
class APIListPrimaryStorageMsg(APIListMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIListPrimaryStorageMsg'
    def __init__(self):
        super(APIListPrimaryStorageMsg, self).__init__()


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


APIDETACHPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIDetachPrimaryStorageMsg'
class APIDetachPrimaryStorageMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIDetachPrimaryStorageMsg'
    def __init__(self):
        super(APIDetachPrimaryStorageMsg, self).__init__()
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()


APIGETPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageMsg'
class APIGetPrimaryStorageMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageMsg'
    def __init__(self):
        super(APIGetPrimaryStorageMsg, self).__init__()


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
        #valid values: [enable, disable, maintain]
        self.stateEvent = NotNoneField()


APIGETPRIMARYSTORAGEALLOCATORSTRATEGIESREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesReply'
class APIGetPrimaryStorageAllocatorStrategiesReply(APIReply):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesReply'
    def __init__(self):
        super(APIGetPrimaryStorageAllocatorStrategiesReply, self).__init__()
        self.primaryStorageAllocatorStrategies = None


APIQUERYPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIQueryPrimaryStorageReply'
class APIQueryPrimaryStorageReply(APIReply):
    FULL_NAME='org.zstack.header.storage.primary.APIQueryPrimaryStorageReply'
    def __init__(self):
        super(APIQueryPrimaryStorageReply, self).__init__()
        self.inventories = None


APIDELETEPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIDeletePrimaryStorageMsg'
class APIDeletePrimaryStorageMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIDeletePrimaryStorageMsg'
    def __init__(self):
        super(APIDeletePrimaryStorageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


CREATETEMPLATEFROMROOTVOLUMEONPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.CreateTemplateFromRootVolumeOnPrimaryStorageReply'
class CreateTemplateFromRootVolumeOnPrimaryStorageReply(APIReply):
    FULL_NAME='org.zstack.header.storage.primary.CreateTemplateFromRootVolumeOnPrimaryStorageReply'
    def __init__(self):
        super(CreateTemplateFromRootVolumeOnPrimaryStorageReply, self).__init__()
        self.templateBackupStorageInstallPath = None


APIGETPRIMARYSTORAGEALLOCATORSTRATEGIESMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesMsg'
class APIGetPrimaryStorageAllocatorStrategiesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesMsg'
    def __init__(self):
        super(APIGetPrimaryStorageAllocatorStrategiesMsg, self).__init__()


APIDELETEVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotMsg'
class APIDeleteVolumeSnapshotMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotMsg'
    def __init__(self):
        super(APIDeleteVolumeSnapshotMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIQUERYVOLUMESNAPSHOTREPLY_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotReply'
class APIQueryVolumeSnapshotReply(APIReply):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotReply'
    def __init__(self):
        super(APIQueryVolumeSnapshotReply, self).__init__()
        self.inventories = None


APIDELETEVOLUMESNAPSHOTFROMBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotFromBackupStorageMsg'
class APIDeleteVolumeSnapshotFromBackupStorageMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotFromBackupStorageMsg'
    def __init__(self):
        super(APIDeleteVolumeSnapshotFromBackupStorageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.backupStorageUuids = NotNoneField()


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
        self.uuid = None


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
        self.inventories = None


APIQUERYBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIQueryBackupStorageMsg'
class APIQueryBackupStorageMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIQueryBackupStorageMsg'
    def __init__(self):
        super(APIQueryBackupStorageMsg, self).__init__()


APILISTBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIListBackupStorageMsg'
class APIListBackupStorageMsg(APIListMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIListBackupStorageMsg'
    def __init__(self):
        super(APIListBackupStorageMsg, self).__init__()


APISEARCHBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APISearchBackupStorageReply'
class APISearchBackupStorageReply(APISearchReply):
    FULL_NAME='org.zstack.header.storage.backup.APISearchBackupStorageReply'
    def __init__(self):
        super(APISearchBackupStorageReply, self).__init__()


APISEARCHBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APISearchBackupStorageMsg'
class APISearchBackupStorageMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.storage.backup.APISearchBackupStorageMsg'
    def __init__(self):
        super(APISearchBackupStorageMsg, self).__init__()


APIGETBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageMsg'
class APIGetBackupStorageMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageMsg'
    def __init__(self):
        super(APIGetBackupStorageMsg, self).__init__()


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
        #valid values: [enable, disable, maintain]
        self.stateEvent = NotNoneField()


APIQUERYBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIQueryBackupStorageReply'
class APIQueryBackupStorageReply(APIReply):
    FULL_NAME='org.zstack.header.storage.backup.APIQueryBackupStorageReply'
    def __init__(self):
        super(APIQueryBackupStorageReply, self).__init__()
        self.inventories = None


APIGETBACKUPSTORAGETYPESREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageTypesReply'
class APIGetBackupStorageTypesReply(APIReply):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageTypesReply'
    def __init__(self):
        super(APIGetBackupStorageTypesReply, self).__init__()
        self.backupStorageTypes = None


APISCANBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIScanBackupStorageMsg'
class APIScanBackupStorageMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIScanBackupStorageMsg'
    def __init__(self):
        super(APIScanBackupStorageMsg, self).__init__()
        self.backupStorageUuid = None


APIATTACHBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIAttachBackupStorageMsg'
class APIAttachBackupStorageMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIAttachBackupStorageMsg'
    def __init__(self):
        super(APIAttachBackupStorageMsg, self).__init__()
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.backupStorageUuid = NotNoneField()


APIDETACHBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIDetachBackupStorageMsg'
class APIDetachBackupStorageMsg(APIMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIDetachBackupStorageMsg'
    def __init__(self):
        super(APIDetachBackupStorageMsg, self).__init__()
        #mandatory field
        self.backupStorageUuid = NotNoneField()
        #mandatory field
        self.zoneUuid = NotNoneField()


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
        self.inventories = None


APIDELETEBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIDeleteBackupStorageMsg'
class APIDeleteBackupStorageMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.storage.backup.APIDeleteBackupStorageMsg'
    def __init__(self):
        super(APIDeleteBackupStorageMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APILISTL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIListL3NetworkMsg'
class APIListL3NetworkMsg(APIListMessage):
    FULL_NAME='org.zstack.header.network.APIListL3NetworkMsg'
    def __init__(self):
        super(APIListL3NetworkMsg, self).__init__()


APIQUERYNETWORKSERVICEL3NETWORKREFREPLY_FULL_NAME = 'org.zstack.header.network.APIQueryNetworkServiceL3NetworkRefReply'
class APIQueryNetworkServiceL3NetworkRefReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIQueryNetworkServiceL3NetworkRefReply'
    def __init__(self):
        super(APIQueryNetworkServiceL3NetworkRefReply, self).__init__()
        self.inventories = None


APIADDDNSTOL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIAddDnsToL3NetworkMsg'
class APIAddDnsToL3NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.APIAddDnsToL3NetworkMsg'
    def __init__(self):
        super(APIAddDnsToL3NetworkMsg, self).__init__()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.dns = NotNoneField()
        self.sortKey = None


APICREATEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APICreateL3NetworkMsg'
class APICreateL3NetworkMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.network.APICreateL3NetworkMsg'
    def __init__(self):
        super(APICreateL3NetworkMsg, self).__init__()
        self.name = None
        self.description = None
        #mandatory field
        self.type = NotNoneField()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        self.trafficType = None


APILISTIPRANGEREPLY_FULL_NAME = 'org.zstack.header.network.APIListIpRangeReply'
class APIListIpRangeReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIListIpRangeReply'
    def __init__(self):
        super(APIListIpRangeReply, self).__init__()
        self.inventories = None


APISEARCHL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APISearchL3NetworkReply'
class APISearchL3NetworkReply(APISearchReply):
    FULL_NAME='org.zstack.header.network.APISearchL3NetworkReply'
    def __init__(self):
        super(APISearchL3NetworkReply, self).__init__()


APIGETL3NETWORKTYPESREPLY_FULL_NAME = 'org.zstack.header.network.APIGetL3NetworkTypesReply'
class APIGetL3NetworkTypesReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIGetL3NetworkTypesReply'
    def __init__(self):
        super(APIGetL3NetworkTypesReply, self).__init__()
        self.l3NetworkTypes = None


APIDELETEIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.APIDeleteIpRangeMsg'
class APIDeleteIpRangeMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.network.APIDeleteIpRangeMsg'
    def __init__(self):
        super(APIDeleteIpRangeMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIATTACHL2NETWORKTOCLUSTERMSG_FULL_NAME = 'org.zstack.header.network.APIAttachL2NetworkToClusterMsg'
class APIAttachL2NetworkToClusterMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.APIAttachL2NetworkToClusterMsg'
    def __init__(self):
        super(APIAttachL2NetworkToClusterMsg, self).__init__()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()


APIQUERYL2VLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIQueryL2VlanNetworkMsg'
class APIQueryL2VlanNetworkMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.APIQueryL2VlanNetworkMsg'
    def __init__(self):
        super(APIQueryL2VlanNetworkMsg, self).__init__()


APICHANGEL3NETWORKSTATEMSG_FULL_NAME = 'org.zstack.header.network.APIChangeL3NetworkStateMsg'
class APIChangeL3NetworkStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.APIChangeL3NetworkStateMsg'
    def __init__(self):
        super(APIChangeL3NetworkStateMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.stateEvent = NotNoneField()


APIATTACHNETWORKSERVICETOL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIAttachNetworkServiceToL3NetworkMsg'
class APIAttachNetworkServiceToL3NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.APIAttachNetworkServiceToL3NetworkMsg'
    def __init__(self):
        super(APIAttachNetworkServiceToL3NetworkMsg, self).__init__()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.networkServices = NotNoneField()


APIGETL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APIGetL3NetworkReply'
class APIGetL3NetworkReply(APIGetReply):
    FULL_NAME='org.zstack.header.network.APIGetL3NetworkReply'
    def __init__(self):
        super(APIGetL3NetworkReply, self).__init__()


APIGETL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APIGetL2VlanNetworkReply'
class APIGetL2VlanNetworkReply(APIGetReply):
    FULL_NAME='org.zstack.header.network.APIGetL2VlanNetworkReply'
    def __init__(self):
        super(APIGetL2VlanNetworkReply, self).__init__()


APIADDNETWORKSERVICEPROVIDERMSG_FULL_NAME = 'org.zstack.header.network.APIAddNetworkServiceProviderMsg'
class APIAddNetworkServiceProviderMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.APIAddNetworkServiceProviderMsg'
    def __init__(self):
        super(APIAddNetworkServiceProviderMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.description = NotNoneField()
        #mandatory field
        self.networkServiceTypes = NotNoneField()
        #mandatory field
        self.type = NotNoneField()


APIGETL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APIGetL2NetworkReply'
class APIGetL2NetworkReply(APIGetReply):
    FULL_NAME='org.zstack.header.network.APIGetL2NetworkReply'
    def __init__(self):
        super(APIGetL2NetworkReply, self).__init__()


APIGETL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIGetL3NetworkMsg'
class APIGetL3NetworkMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.network.APIGetL3NetworkMsg'
    def __init__(self):
        super(APIGetL3NetworkMsg, self).__init__()


APIGETL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIGetL2NetworkMsg'
class APIGetL2NetworkMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.network.APIGetL2NetworkMsg'
    def __init__(self):
        super(APIGetL2NetworkMsg, self).__init__()


APILISTL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIListL2NetworkMsg'
class APIListL2NetworkMsg(APIListMessage):
    FULL_NAME='org.zstack.header.network.APIListL2NetworkMsg'
    def __init__(self):
        super(APIListL2NetworkMsg, self).__init__()


APISEARCHL2VLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.APISearchL2VlanNetworkMsg'
class APISearchL2VlanNetworkMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.network.APISearchL2VlanNetworkMsg'
    def __init__(self):
        super(APISearchL2VlanNetworkMsg, self).__init__()


APICREATEL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APICreateL2NetworkMsg'
class APICreateL2NetworkMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.network.APICreateL2NetworkMsg'
    def __init__(self):
        super(APICreateL2NetworkMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.physicalInterface = NotNoneField()
        #mandatory field
        self.type = NotNoneField()


APICREATEL2VLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.APICreateL2VlanNetworkMsg'
class APICreateL2VlanNetworkMsg(APICreateL2NetworkMsg):
    FULL_NAME='org.zstack.header.network.APICreateL2VlanNetworkMsg'
    def __init__(self):
        super(APICreateL2VlanNetworkMsg, self).__init__()
        #mandatory field
        self.vlan = NotNoneField()


APIADDIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.APIAddIpRangeMsg'
class APIAddIpRangeMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.network.APIAddIpRangeMsg'
    def __init__(self):
        super(APIAddIpRangeMsg, self).__init__()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        self.name = None
        self.description = None
        #mandatory field
        self.startIp = NotNoneField()
        #mandatory field
        self.endIp = NotNoneField()
        #mandatory field
        self.netmask = NotNoneField()
        #mandatory field
        self.gateway = NotNoneField()


APIGETL3NETWORKTYPESMSG_FULL_NAME = 'org.zstack.header.network.APIGetL3NetworkTypesMsg'
class APIGetL3NetworkTypesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.network.APIGetL3NetworkTypesMsg'
    def __init__(self):
        super(APIGetL3NetworkTypesMsg, self).__init__()


APIQUERYL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APIQueryL2VlanNetworkReply'
class APIQueryL2VlanNetworkReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIQueryL2VlanNetworkReply'
    def __init__(self):
        super(APIQueryL2VlanNetworkReply, self).__init__()
        self.inventories = None


APIDETACHL2NETWORKFROMCLUSTERMSG_FULL_NAME = 'org.zstack.header.network.APIDetachL2NetworkFromClusterMsg'
class APIDetachL2NetworkFromClusterMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.APIDetachL2NetworkFromClusterMsg'
    def __init__(self):
        super(APIDetachL2NetworkFromClusterMsg, self).__init__()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()


APISEARCHNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.APISearchNetworkServiceProviderReply'
class APISearchNetworkServiceProviderReply(APISearchReply):
    FULL_NAME='org.zstack.header.network.APISearchNetworkServiceProviderReply'
    def __init__(self):
        super(APISearchNetworkServiceProviderReply, self).__init__()


APISEARCHL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APISearchL3NetworkMsg'
class APISearchL3NetworkMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.network.APISearchL3NetworkMsg'
    def __init__(self):
        super(APISearchL3NetworkMsg, self).__init__()


APIGETL2NETWORKTYPESREPLY_FULL_NAME = 'org.zstack.header.network.APIGetL2NetworkTypesReply'
class APIGetL2NetworkTypesReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIGetL2NetworkTypesReply'
    def __init__(self):
        super(APIGetL2NetworkTypesReply, self).__init__()
        self.l2NetworkTypes = None


APILISTL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APIListL2VlanNetworkReply'
class APIListL2VlanNetworkReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIListL2VlanNetworkReply'
    def __init__(self):
        super(APIListL2VlanNetworkReply, self).__init__()
        self.inventories = None


APIQUERYNETWORKSERVICEL3NETWORKREFMSG_FULL_NAME = 'org.zstack.header.network.APIQueryNetworkServiceL3NetworkRefMsg'
class APIQueryNetworkServiceL3NetworkRefMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.APIQueryNetworkServiceL3NetworkRefMsg'
    def __init__(self):
        super(APIQueryNetworkServiceL3NetworkRefMsg, self).__init__()


APIDELETEL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIDeleteL2NetworkMsg'
class APIDeleteL2NetworkMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.network.APIDeleteL2NetworkMsg'
    def __init__(self):
        super(APIDeleteL2NetworkMsg, self).__init__()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()


APIATTACHNETWORKSERVICEPROVIDERTOL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIAttachNetworkServiceProviderToL2NetworkMsg'
class APIAttachNetworkServiceProviderToL2NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.APIAttachNetworkServiceProviderToL2NetworkMsg'
    def __init__(self):
        super(APIAttachNetworkServiceProviderToL2NetworkMsg, self).__init__()
        #mandatory field
        self.networkServiceProviderUuid = NotNoneField()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()


APIGETNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.APIGetNetworkServiceProviderReply'
class APIGetNetworkServiceProviderReply(APIGetReply):
    FULL_NAME='org.zstack.header.network.APIGetNetworkServiceProviderReply'
    def __init__(self):
        super(APIGetNetworkServiceProviderReply, self).__init__()


APIQUERYL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APIQueryL3NetworkReply'
class APIQueryL3NetworkReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIQueryL3NetworkReply'
    def __init__(self):
        super(APIQueryL3NetworkReply, self).__init__()
        self.inventories = None


APISEARCHL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APISearchL2VlanNetworkReply'
class APISearchL2VlanNetworkReply(APISearchReply):
    FULL_NAME='org.zstack.header.network.APISearchL2VlanNetworkReply'
    def __init__(self):
        super(APISearchL2VlanNetworkReply, self).__init__()


APISEARCHNETWORKSERVICEPROVIDERMSG_FULL_NAME = 'org.zstack.header.network.APISearchNetworkServiceProviderMsg'
class APISearchNetworkServiceProviderMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.network.APISearchNetworkServiceProviderMsg'
    def __init__(self):
        super(APISearchNetworkServiceProviderMsg, self).__init__()


APIQUERYIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.APIQueryIpRangeMsg'
class APIQueryIpRangeMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.APIQueryIpRangeMsg'
    def __init__(self):
        super(APIQueryIpRangeMsg, self).__init__()


APIQUERYL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APIQueryL2NetworkReply'
class APIQueryL2NetworkReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIQueryL2NetworkReply'
    def __init__(self):
        super(APIQueryL2NetworkReply, self).__init__()
        self.inventories = None


APISEARCHL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APISearchL2NetworkMsg'
class APISearchL2NetworkMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.network.APISearchL2NetworkMsg'
    def __init__(self):
        super(APISearchL2NetworkMsg, self).__init__()


APIDETACHNETWORKSERVICEPROVIDERFROML2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIDetachNetworkServiceProviderFromL2NetworkMsg'
class APIDetachNetworkServiceProviderFromL2NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.APIDetachNetworkServiceProviderFromL2NetworkMsg'
    def __init__(self):
        super(APIDetachNetworkServiceProviderFromL2NetworkMsg, self).__init__()
        #mandatory field
        self.networkServiceProviderUuid = NotNoneField()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()


APIDELETEIPRANGECARRIERMSG_FULL_NAME = 'org.zstack.header.network.APIDeleteIpRangeCarrierMsg'
class APIDeleteIpRangeCarrierMsg(APIDeleteIpRangeMsg):
    FULL_NAME='org.zstack.header.network.APIDeleteIpRangeCarrierMsg'
    def __init__(self):
        super(APIDeleteIpRangeCarrierMsg, self).__init__()
        self.l3NetworkUuid = None


APIREMOVEDNSFROML3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIRemoveDnsFromL3NetworkMsg'
class APIRemoveDnsFromL3NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.APIRemoveDnsFromL3NetworkMsg'
    def __init__(self):
        super(APIRemoveDnsFromL3NetworkMsg, self).__init__()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.dns = NotNoneField()


APIQUERYNETWORKSERVICEPROVIDERMSG_FULL_NAME = 'org.zstack.header.network.APIQueryNetworkServiceProviderMsg'
class APIQueryNetworkServiceProviderMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.APIQueryNetworkServiceProviderMsg'
    def __init__(self):
        super(APIQueryNetworkServiceProviderMsg, self).__init__()


APIQUERYIPRANGEREPLY_FULL_NAME = 'org.zstack.header.network.APIQueryIpRangeReply'
class APIQueryIpRangeReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIQueryIpRangeReply'
    def __init__(self):
        super(APIQueryIpRangeReply, self).__init__()
        self.inventories = None


APILISTIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.APIListIpRangeMsg'
class APIListIpRangeMsg(APIListMessage):
    FULL_NAME='org.zstack.header.network.APIListIpRangeMsg'
    def __init__(self):
        super(APIListIpRangeMsg, self).__init__()


APILISTL2VLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIListL2VlanNetworkMsg'
class APIListL2VlanNetworkMsg(APIListMessage):
    FULL_NAME='org.zstack.header.network.APIListL2VlanNetworkMsg'
    def __init__(self):
        super(APIListL2VlanNetworkMsg, self).__init__()


APISEARCHL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APISearchL2NetworkReply'
class APISearchL2NetworkReply(APISearchReply):
    FULL_NAME='org.zstack.header.network.APISearchL2NetworkReply'
    def __init__(self):
        super(APISearchL2NetworkReply, self).__init__()


APIGETNETWORKSERVICETYPESMSG_FULL_NAME = 'org.zstack.header.network.APIGetNetworkServiceTypesMsg'
class APIGetNetworkServiceTypesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.network.APIGetNetworkServiceTypesMsg'
    def __init__(self):
        super(APIGetNetworkServiceTypesMsg, self).__init__()


APIGETNETWORKSERVICETYPESREPLY_FULL_NAME = 'org.zstack.header.network.APIGetNetworkServiceTypesReply'
class APIGetNetworkServiceTypesReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIGetNetworkServiceTypesReply'
    def __init__(self):
        super(APIGetNetworkServiceTypesReply, self).__init__()
        self.serviceAndProviderTypes = None


APILISTL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APIListL2NetworkReply'
class APIListL2NetworkReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIListL2NetworkReply'
    def __init__(self):
        super(APIListL2NetworkReply, self).__init__()
        self.inventories = None


APIGETL2VLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIGetL2VlanNetworkMsg'
class APIGetL2VlanNetworkMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.network.APIGetL2VlanNetworkMsg'
    def __init__(self):
        super(APIGetL2VlanNetworkMsg, self).__init__()


APIGETNETWORKSERVICEPROVIDERMSG_FULL_NAME = 'org.zstack.header.network.APIGetNetworkServiceProviderMsg'
class APIGetNetworkServiceProviderMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.network.APIGetNetworkServiceProviderMsg'
    def __init__(self):
        super(APIGetNetworkServiceProviderMsg, self).__init__()


APILISTL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.APIListL3NetworkReply'
class APIListL3NetworkReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIListL3NetworkReply'
    def __init__(self):
        super(APIListL3NetworkReply, self).__init__()
        self.inventories = None


APIDELETEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIDeleteL3NetworkMsg'
class APIDeleteL3NetworkMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.network.APIDeleteL3NetworkMsg'
    def __init__(self):
        super(APIDeleteL3NetworkMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APILISTNETWORKSERVICEPROVIDERMSG_FULL_NAME = 'org.zstack.header.network.APIListNetworkServiceProviderMsg'
class APIListNetworkServiceProviderMsg(APIListMessage):
    FULL_NAME='org.zstack.header.network.APIListNetworkServiceProviderMsg'
    def __init__(self):
        super(APIListNetworkServiceProviderMsg, self).__init__()


APILISTNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.APIListNetworkServiceProviderReply'
class APIListNetworkServiceProviderReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIListNetworkServiceProviderReply'
    def __init__(self):
        super(APIListNetworkServiceProviderReply, self).__init__()
        self.inventories = None


APIQUERYNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.APIQueryNetworkServiceProviderReply'
class APIQueryNetworkServiceProviderReply(APIReply):
    FULL_NAME='org.zstack.header.network.APIQueryNetworkServiceProviderReply'
    def __init__(self):
        super(APIQueryNetworkServiceProviderReply, self).__init__()
        self.inventories = None


APIGETL2NETWORKTYPESMSG_FULL_NAME = 'org.zstack.header.network.APIGetL2NetworkTypesMsg'
class APIGetL2NetworkTypesMsg(APISyncCallMessage):
    FULL_NAME='org.zstack.header.network.APIGetL2NetworkTypesMsg'
    def __init__(self):
        super(APIGetL2NetworkTypesMsg, self).__init__()


APIATTACHDNSTOL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIAttachDnsToL3NetworkMsg'
class APIAttachDnsToL3NetworkMsg(APIMessage):
    FULL_NAME='org.zstack.header.network.APIAttachDnsToL3NetworkMsg'
    def __init__(self):
        super(APIAttachDnsToL3NetworkMsg, self).__init__()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.dnsUuid = NotNoneField()


APIQUERYL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIQueryL2NetworkMsg'
class APIQueryL2NetworkMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.APIQueryL2NetworkMsg'
    def __init__(self):
        super(APIQueryL2NetworkMsg, self).__init__()


APIQUERYL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.APIQueryL3NetworkMsg'
class APIQueryL3NetworkMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.network.APIQueryL3NetworkMsg'
    def __init__(self):
        super(APIQueryL3NetworkMsg, self).__init__()


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
        self.inventoryNames = NotNoneField()
        self.isRecreate = None


APIQUERYMANAGEMENTNODEREPLY_FULL_NAME = 'org.zstack.header.managementnode.APIQueryManagementNodeReply'
class APIQueryManagementNodeReply(APIReply):
    FULL_NAME='org.zstack.header.managementnode.APIQueryManagementNodeReply'
    def __init__(self):
        super(APIQueryManagementNodeReply, self).__init__()
        self.inventories = None


APIQUERYMANAGEMENTNODEMSG_FULL_NAME = 'org.zstack.header.managementnode.APIQueryManagementNodeMsg'
class APIQueryManagementNodeMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.managementnode.APIQueryManagementNodeMsg'
    def __init__(self):
        super(APIQueryManagementNodeMsg, self).__init__()


APILISTMANAGEMENTNODEMSG_FULL_NAME = 'org.zstack.header.managementnode.APIListManagementNodeMsg'
class APIListManagementNodeMsg(APIListMessage):
    FULL_NAME='org.zstack.header.managementnode.APIListManagementNodeMsg'
    def __init__(self):
        super(APIListManagementNodeMsg, self).__init__()


APILISTMANAGEMENTNODEREPLY_FULL_NAME = 'org.zstack.header.managementnode.APIListManagementNodeReply'
class APIListManagementNodeReply(APIReply):
    FULL_NAME='org.zstack.header.managementnode.APIListManagementNodeReply'
    def __init__(self):
        super(APIListManagementNodeReply, self).__init__()
        self.inventories = None


APISEARCHCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APISearchClusterReply'
class APISearchClusterReply(APISearchReply):
    FULL_NAME='org.zstack.header.cluster.APISearchClusterReply'
    def __init__(self):
        super(APISearchClusterReply, self).__init__()


APILISTCLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APIListClusterMsg'
class APIListClusterMsg(APIListMessage):
    FULL_NAME='org.zstack.header.cluster.APIListClusterMsg'
    def __init__(self):
        super(APIListClusterMsg, self).__init__()


APILISTCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APIListClusterReply'
class APIListClusterReply(APIReply):
    FULL_NAME='org.zstack.header.cluster.APIListClusterReply'
    def __init__(self):
        super(APIListClusterReply, self).__init__()
        self.inventories = None


APIGETCLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APIGetClusterMsg'
class APIGetClusterMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.cluster.APIGetClusterMsg'
    def __init__(self):
        super(APIGetClusterMsg, self).__init__()


APISEARCHCLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APISearchClusterMsg'
class APISearchClusterMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.cluster.APISearchClusterMsg'
    def __init__(self):
        super(APISearchClusterMsg, self).__init__()


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
        self.hypervisorType = NotNoneField()
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
class APIQueryClusterReply(APIReply):
    FULL_NAME='org.zstack.header.cluster.APIQueryClusterReply'
    def __init__(self):
        super(APIQueryClusterReply, self).__init__()
        self.inventories = None


APILISTUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APIListUserReply'
class APIListUserReply(APIReply):
    FULL_NAME='org.zstack.header.identity.APIListUserReply'
    def __init__(self):
        super(APIListUserReply, self).__init__()
        self.inventories = None


APIATTACHPOLICYTOUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIAttachPolicyToUserGroupMsg'
class APIAttachPolicyToUserGroupMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIAttachPolicyToUserGroupMsg'
    def __init__(self):
        super(APIAttachPolicyToUserGroupMsg, self).__init__()
        #mandatory field
        self.policyUuid = NotNoneField()
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


APIGETACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APIGetAccountMsg'
class APIGetAccountMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.identity.APIGetAccountMsg'
    def __init__(self):
        super(APIGetAccountMsg, self).__init__()


APILISTACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APIListAccountMsg'
class APIListAccountMsg(APIListMessage):
    FULL_NAME='org.zstack.header.identity.APIListAccountMsg'
    def __init__(self):
        super(APIListAccountMsg, self).__init__()


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


APILISTACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIListAccountReply'
class APIListAccountReply(APIReply):
    FULL_NAME='org.zstack.header.identity.APIListAccountReply'
    def __init__(self):
        super(APIListAccountReply, self).__init__()
        self.inventories = None


APISEARCHPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchPolicyReply'
class APISearchPolicyReply(APISearchReply):
    FULL_NAME='org.zstack.header.identity.APISearchPolicyReply'
    def __init__(self):
        super(APISearchPolicyReply, self).__init__()


APILISTPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APIListPolicyMsg'
class APIListPolicyMsg(APIListMessage):
    FULL_NAME='org.zstack.header.identity.APIListPolicyMsg'
    def __init__(self):
        super(APIListPolicyMsg, self).__init__()


APICREATEACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APICreateAccountMsg'
class APICreateAccountMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APICreateAccountMsg'
    def __init__(self):
        super(APICreateAccountMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.password = NotNoneField()


APICREATEUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APICreateUserGroupMsg'
class APICreateUserGroupMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APICreateUserGroupMsg'
    def __init__(self):
        super(APICreateUserGroupMsg, self).__init__()
        #mandatory field
        self.groupName = NotNoneField()
        self.groupDescription = None


APICREATEUSERMSG_FULL_NAME = 'org.zstack.header.identity.APICreateUserMsg'
class APICreateUserMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APICreateUserMsg'
    def __init__(self):
        super(APICreateUserMsg, self).__init__()
        #mandatory field
        self.userName = NotNoneField()
        self.password = None


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


APISEARCHACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APISearchAccountMsg'
class APISearchAccountMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.identity.APISearchAccountMsg'
    def __init__(self):
        super(APISearchAccountMsg, self).__init__()


APISEARCHPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APISearchPolicyMsg'
class APISearchPolicyMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.identity.APISearchPolicyMsg'
    def __init__(self):
        super(APISearchPolicyMsg, self).__init__()


APIGETUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIGetUserMsg'
class APIGetUserMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.identity.APIGetUserMsg'
    def __init__(self):
        super(APIGetUserMsg, self).__init__()


APIGETUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIGetUserGroupMsg'
class APIGetUserGroupMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.identity.APIGetUserGroupMsg'
    def __init__(self):
        super(APIGetUserGroupMsg, self).__init__()


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


APIATTACHUSERTOUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIAttachUserToUserGroupMsg'
class APIAttachUserToUserGroupMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APIAttachUserToUserGroupMsg'
    def __init__(self):
        super(APIAttachUserToUserGroupMsg, self).__init__()
        #mandatory field
        self.userUuid = NotNoneField()
        #mandatory field
        self.groupUuid = NotNoneField()


APIGETPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetPolicyReply'
class APIGetPolicyReply(APIGetReply):
    FULL_NAME='org.zstack.header.identity.APIGetPolicyReply'
    def __init__(self):
        super(APIGetPolicyReply, self).__init__()


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
        self.inventories = None


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
        self.accountUuidToReset = NotNoneField()
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


APISEARCHACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchAccountReply'
class APISearchAccountReply(APISearchReply):
    FULL_NAME='org.zstack.header.identity.APISearchAccountReply'
    def __init__(self):
        super(APISearchAccountReply, self).__init__()


APISEARCHUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APISearchUserGroupMsg'
class APISearchUserGroupMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.identity.APISearchUserGroupMsg'
    def __init__(self):
        super(APISearchUserGroupMsg, self).__init__()


APILISTUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIListUserMsg'
class APIListUserMsg(APIListMessage):
    FULL_NAME='org.zstack.header.identity.APIListUserMsg'
    def __init__(self):
        super(APIListUserMsg, self).__init__()


APISEARCHUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchUserReply'
class APISearchUserReply(APISearchReply):
    FULL_NAME='org.zstack.header.identity.APISearchUserReply'
    def __init__(self):
        super(APISearchUserReply, self).__init__()


APISEARCHUSERMSG_FULL_NAME = 'org.zstack.header.identity.APISearchUserMsg'
class APISearchUserMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.identity.APISearchUserMsg'
    def __init__(self):
        super(APISearchUserMsg, self).__init__()


APILOGOUTMSG_FULL_NAME = 'org.zstack.header.identity.APILogOutMsg'
class APILogOutMsg(APISessionMessage):
    FULL_NAME='org.zstack.header.identity.APILogOutMsg'
    def __init__(self):
        super(APILogOutMsg, self).__init__()
        self.sessionUuid = None


APIGETPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APIGetPolicyMsg'
class APIGetPolicyMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.identity.APIGetPolicyMsg'
    def __init__(self):
        super(APIGetPolicyMsg, self).__init__()


APICREATEPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APICreatePolicyMsg'
class APICreatePolicyMsg(APIMessage):
    FULL_NAME='org.zstack.header.identity.APICreatePolicyMsg'
    def __init__(self):
        super(APICreatePolicyMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.policyData = NotNoneField()


APIVALIDATESESSIONREPLY_FULL_NAME = 'org.zstack.header.identity.APIValidateSessionReply'
class APIValidateSessionReply(APIReply):
    FULL_NAME='org.zstack.header.identity.APIValidateSessionReply'
    def __init__(self):
        super(APIValidateSessionReply, self).__init__()


APIGETZONEREPLY_FULL_NAME = 'org.zstack.header.zone.APIGetZoneReply'
class APIGetZoneReply(APIGetReply):
    FULL_NAME='org.zstack.header.zone.APIGetZoneReply'
    def __init__(self):
        super(APIGetZoneReply, self).__init__()


APIGETZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIGetZoneMsg'
class APIGetZoneMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.zone.APIGetZoneMsg'
    def __init__(self):
        super(APIGetZoneMsg, self).__init__()


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
        self.inventories = None


APIDELETEZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIDeleteZoneMsg'
class APIDeleteZoneMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.zone.APIDeleteZoneMsg'
    def __init__(self):
        super(APIDeleteZoneMsg, self).__init__()
        self.uuid = None


APICREATEZONEMSG_FULL_NAME = 'org.zstack.header.zone.APICreateZoneMsg'
class APICreateZoneMsg(APICreateMessage):
    FULL_NAME='org.zstack.header.zone.APICreateZoneMsg'
    def __init__(self):
        super(APICreateZoneMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None


APIQUERYZONEREPLY_FULL_NAME = 'org.zstack.header.zone.APIQueryZoneReply'
class APIQueryZoneReply(APIReply):
    FULL_NAME='org.zstack.header.zone.APIQueryZoneReply'
    def __init__(self):
        super(APIQueryZoneReply, self).__init__()
        self.inventories = None


APISEARCHZONEMSG_FULL_NAME = 'org.zstack.header.zone.APISearchZoneMsg'
class APISearchZoneMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.zone.APISearchZoneMsg'
    def __init__(self):
        super(APISearchZoneMsg, self).__init__()


APIQUERYZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIQueryZoneMsg'
class APIQueryZoneMsg(APIQueryMessage):
    FULL_NAME='org.zstack.header.zone.APIQueryZoneMsg'
    def __init__(self):
        super(APIQueryZoneMsg, self).__init__()


APILISTZONESMSG_FULL_NAME = 'org.zstack.header.zone.APIListZonesMsg'
class APIListZonesMsg(APIListMessage):
    FULL_NAME='org.zstack.header.zone.APIListZonesMsg'
    def __init__(self):
        super(APIListZonesMsg, self).__init__()


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
        self.hypervisorTypes = None


APICHANGEHOSTSTATEMSG_FULL_NAME = 'org.zstack.header.host.APIChangeHostStateMsg'
class APIChangeHostStateMsg(APIMessage):
    FULL_NAME='org.zstack.header.host.APIChangeHostStateMsg'
    def __init__(self):
        super(APIChangeHostStateMsg, self).__init__()
        self.uuid = None
        self.stateEvent = None


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
        self.inventories = None


APIRECONNECTHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIReconnectHostMsg'
class APIReconnectHostMsg(APIMessage):
    FULL_NAME='org.zstack.header.host.APIReconnectHostMsg'
    def __init__(self):
        super(APIReconnectHostMsg, self).__init__()
        self.uuid = None


APILISTHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIListHostMsg'
class APIListHostMsg(APIListMessage):
    FULL_NAME='org.zstack.header.host.APIListHostMsg'
    def __init__(self):
        super(APIListHostMsg, self).__init__()


APIDELETEHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIDeleteHostMsg'
class APIDeleteHostMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.header.host.APIDeleteHostMsg'
    def __init__(self):
        super(APIDeleteHostMsg, self).__init__()
        self.uuid = None


APISEARCHHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APISearchHostReply'
class APISearchHostReply(APISearchReply):
    FULL_NAME='org.zstack.header.host.APISearchHostReply'
    def __init__(self):
        super(APISearchHostReply, self).__init__()


APIGETHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIGetHostMsg'
class APIGetHostMsg(APIGetMessage):
    FULL_NAME='org.zstack.header.host.APIGetHostMsg'
    def __init__(self):
        super(APIGetHostMsg, self).__init__()


APIQUERYHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APIQueryHostReply'
class APIQueryHostReply(APIReply):
    FULL_NAME='org.zstack.header.host.APIQueryHostReply'
    def __init__(self):
        super(APIQueryHostReply, self).__init__()
        self.inventories = None


APISEARCHHOSTMSG_FULL_NAME = 'org.zstack.header.host.APISearchHostMsg'
class APISearchHostMsg(APISearchMessage):
    FULL_NAME='org.zstack.header.host.APISearchHostMsg'
    def __init__(self):
        super(APISearchHostMsg, self).__init__()


APIGETHYPERVISORTYPESMSG_FULL_NAME = 'org.zstack.header.host.APIGetHypervisorTypesMsg'
class APIGetHypervisorTypesMsg(APIListMessage):
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
        self.hostTags = None


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
        #mandatory field
        self.type = NotNoneField()
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
        #mandatory field
        self.type = NotNoneField()


APIADDSIMULATORBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.simulator.storage.backup.APIAddSimulatorBackupStorageMsg'
class APIAddSimulatorBackupStorageMsg(APIAddBackupStorageMsg):
    FULL_NAME='org.zstack.header.simulator.storage.backup.APIAddSimulatorBackupStorageMsg'
    def __init__(self):
        super(APIAddSimulatorBackupStorageMsg, self).__init__()
        self.totalCapacity = None
        self.availableCapacity = None


APILISTAPPLIANCEVMMSG_FULL_NAME = 'org.zstack.appliancevm.APIListApplianceVmMsg'
class APIListApplianceVmMsg(APIListMessage):
    FULL_NAME='org.zstack.appliancevm.APIListApplianceVmMsg'
    def __init__(self):
        super(APIListApplianceVmMsg, self).__init__()


APIQUERYAPPLIANCEVMMSG_FULL_NAME = 'org.zstack.appliancevm.APIQueryApplianceVmMsg'
class APIQueryApplianceVmMsg(APIQueryMessage):
    FULL_NAME='org.zstack.appliancevm.APIQueryApplianceVmMsg'
    def __init__(self):
        super(APIQueryApplianceVmMsg, self).__init__()


APIQUERYAPPLIANCEVMREPLY_FULL_NAME = 'org.zstack.appliancevm.APIQueryApplianceVmReply'
class APIQueryApplianceVmReply(APIReply):
    FULL_NAME='org.zstack.appliancevm.APIQueryApplianceVmReply'
    def __init__(self):
        super(APIQueryApplianceVmReply, self).__init__()
        self.inventories = None


APILISTAPPLIANCEVMREPLY_FULL_NAME = 'org.zstack.appliancevm.APIListApplianceVmReply'
class APIListApplianceVmReply(APIReply):
    FULL_NAME='org.zstack.appliancevm.APIListApplianceVmReply'
    def __init__(self):
        super(APIListApplianceVmReply, self).__init__()
        self.inventories = None


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


APIGETSFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIGetSftpBackupStorageMsg'
class APIGetSftpBackupStorageMsg(APIGetMessage):
    FULL_NAME='org.zstack.storage.backup.sftp.APIGetSftpBackupStorageMsg'
    def __init__(self):
        super(APIGetSftpBackupStorageMsg, self).__init__()


APISEARCHSFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APISearchSftpBackupStorageMsg'
class APISearchSftpBackupStorageMsg(APISearchMessage):
    FULL_NAME='org.zstack.storage.backup.sftp.APISearchSftpBackupStorageMsg'
    def __init__(self):
        super(APISearchSftpBackupStorageMsg, self).__init__()


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
        self.backupStorageUuid = None


APIGETSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APIGetSftpBackupStorageReply'
class APIGetSftpBackupStorageReply(APIGetReply):
    FULL_NAME='org.zstack.storage.backup.sftp.APIGetSftpBackupStorageReply'
    def __init__(self):
        super(APIGetSftpBackupStorageReply, self).__init__()


APIQUERYSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageReply'
class APIQuerySftpBackupStorageReply(APIReply):
    FULL_NAME='org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageReply'
    def __init__(self):
        super(APIQuerySftpBackupStorageReply, self).__init__()
        self.inventories = None


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


APISEARCHVIRTUALROUTERVMREPLY_FULL_NAME = 'org.zstack.network.serviceprovider.virtualrouter.APISearchVirtualRouterVmReply'
class APISearchVirtualRouterVmReply(APISearchReply):
    FULL_NAME='org.zstack.network.serviceprovider.virtualrouter.APISearchVirtualRouterVmReply'
    def __init__(self):
        super(APISearchVirtualRouterVmReply, self).__init__()


APIADDVIRTUALROUTEROFFERINGMSG_FULL_NAME = 'org.zstack.network.serviceprovider.virtualrouter.APIAddVirtualRouterOfferingMsg'
class APIAddVirtualRouterOfferingMsg(APIAddInstanceOfferingMsg):
    FULL_NAME='org.zstack.network.serviceprovider.virtualrouter.APIAddVirtualRouterOfferingMsg'
    def __init__(self):
        super(APIAddVirtualRouterOfferingMsg, self).__init__()
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.managementNetworkUuid = NotNoneField()
        #mandatory field
        self.imageUuid = NotNoneField()
        self.publicNetworkUuid = None
        self.isDefault = None


APICREATEVIRTUALROUTERVMMSG_FULL_NAME = 'org.zstack.network.serviceprovider.virtualrouter.APICreateVirtualRouterVmMsg'
class APICreateVirtualRouterVmMsg(APICreateVmInstanceMsg):
    FULL_NAME='org.zstack.network.serviceprovider.virtualrouter.APICreateVirtualRouterVmMsg'
    def __init__(self):
        super(APICreateVirtualRouterVmMsg, self).__init__()
        #mandatory field
        self.managementNetworkUuid = NotNoneField()
        #mandatory field
        self.publicNetworkUuid = NotNoneField()
        #mandatory field
        self.networkServicesProvided = NotNoneField()


APIGETVIRTUALROUTEROFFERINGMSG_FULL_NAME = 'org.zstack.network.serviceprovider.virtualrouter.APIGetVirtualRouterOfferingMsg'
class APIGetVirtualRouterOfferingMsg(APIGetMessage):
    FULL_NAME='org.zstack.network.serviceprovider.virtualrouter.APIGetVirtualRouterOfferingMsg'
    def __init__(self):
        super(APIGetVirtualRouterOfferingMsg, self).__init__()


APISEARCHVIRTUALROUTERVMMSG_FULL_NAME = 'org.zstack.network.serviceprovider.virtualrouter.APISearchVirtualRouterVmMsg'
class APISearchVirtualRouterVmMsg(APISearchMessage):
    FULL_NAME='org.zstack.network.serviceprovider.virtualrouter.APISearchVirtualRouterVmMsg'
    def __init__(self):
        super(APISearchVirtualRouterVmMsg, self).__init__()


APIQUERYVIRTUALROUTEROFFERINGMSG_FULL_NAME = 'org.zstack.network.serviceprovider.virtualrouter.APIQueryVirtualRouterOfferingMsg'
class APIQueryVirtualRouterOfferingMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.serviceprovider.virtualrouter.APIQueryVirtualRouterOfferingMsg'
    def __init__(self):
        super(APIQueryVirtualRouterOfferingMsg, self).__init__()


APIGETVIRTUALROUTEROFFERINGREPLY_FULL_NAME = 'org.zstack.network.serviceprovider.virtualrouter.APIGetVirtualRouterOfferingReply'
class APIGetVirtualRouterOfferingReply(APIGetReply):
    FULL_NAME='org.zstack.network.serviceprovider.virtualrouter.APIGetVirtualRouterOfferingReply'
    def __init__(self):
        super(APIGetVirtualRouterOfferingReply, self).__init__()


APISEARCHVIRTUALROUTEROFFINGMSG_FULL_NAME = 'org.zstack.network.serviceprovider.virtualrouter.APISearchVirtualRouterOffingMsg'
class APISearchVirtualRouterOffingMsg(APISearchMessage):
    FULL_NAME='org.zstack.network.serviceprovider.virtualrouter.APISearchVirtualRouterOffingMsg'
    def __init__(self):
        super(APISearchVirtualRouterOffingMsg, self).__init__()


APISEARCHVIRTUALROUTEROFFINGREPLY_FULL_NAME = 'org.zstack.network.serviceprovider.virtualrouter.APISearchVirtualRouterOffingReply'
class APISearchVirtualRouterOffingReply(APISearchReply):
    FULL_NAME='org.zstack.network.serviceprovider.virtualrouter.APISearchVirtualRouterOffingReply'
    def __init__(self):
        super(APISearchVirtualRouterOffingReply, self).__init__()


APIQUERYVIRTUALROUTEROFFERINGREPLY_FULL_NAME = 'org.zstack.network.serviceprovider.virtualrouter.APIQueryVirtualRouterOfferingReply'
class APIQueryVirtualRouterOfferingReply(APIReply):
    FULL_NAME='org.zstack.network.serviceprovider.virtualrouter.APIQueryVirtualRouterOfferingReply'
    def __init__(self):
        super(APIQueryVirtualRouterOfferingReply, self).__init__()
        self.inventories = None


APIATTACHPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.APIAttachPortForwardingRuleMsg'
class APIAttachPortForwardingRuleMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.APIAttachPortForwardingRuleMsg'
    def __init__(self):
        super(APIAttachPortForwardingRuleMsg, self).__init__()
        #mandatory field
        self.ruleUuid = NotNoneField()
        #mandatory field
        self.vmNicUuid = NotNoneField()


APIDETACHPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.APIDetachPortForwardingRuleMsg'
class APIDetachPortForwardingRuleMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.APIDetachPortForwardingRuleMsg'
    def __init__(self):
        super(APIDetachPortForwardingRuleMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIQUERYPORTFORWARDINGRULEREPLY_FULL_NAME = 'org.zstack.network.service.APIQueryPortForwardingRuleReply'
class APIQueryPortForwardingRuleReply(APIReply):
    FULL_NAME='org.zstack.network.service.APIQueryPortForwardingRuleReply'
    def __init__(self):
        super(APIQueryPortForwardingRuleReply, self).__init__()
        self.inventories = None


APILISTPORTFORWARDINGRULEREPLY_FULL_NAME = 'org.zstack.network.service.APIListPortForwardingRuleReply'
class APIListPortForwardingRuleReply(APIReply):
    FULL_NAME='org.zstack.network.service.APIListPortForwardingRuleReply'
    def __init__(self):
        super(APIListPortForwardingRuleReply, self).__init__()
        self.inventories = None


APILISTPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.APIListPortForwardingRuleMsg'
class APIListPortForwardingRuleMsg(APIListMessage):
    FULL_NAME='org.zstack.network.service.APIListPortForwardingRuleMsg'
    def __init__(self):
        super(APIListPortForwardingRuleMsg, self).__init__()


APICREATEPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.APICreatePortForwardingRuleMsg'
class APICreatePortForwardingRuleMsg(APICreateMessage):
    FULL_NAME='org.zstack.network.service.APICreatePortForwardingRuleMsg'
    def __init__(self):
        super(APICreatePortForwardingRuleMsg, self).__init__()
        #mandatory field
        self.vipUuid = NotNoneField()
        #mandatory field
        self.vipPortStart = NotNoneField()
        self.vipPortEnd = None
        #mandatory field
        self.privatePortStart = NotNoneField()
        self.privatePortEnd = None
        #mandatory field
        self.protocolType = NotNoneField()
        self.vmNicUuid = None
        self.allowedCidr = None
        self.name = None
        self.description = None


APIQUERYPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.APIQueryPortForwardingRuleMsg'
class APIQueryPortForwardingRuleMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.service.APIQueryPortForwardingRuleMsg'
    def __init__(self):
        super(APIQueryPortForwardingRuleMsg, self).__init__()


APIDELETEPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.APIDeletePortForwardingRuleMsg'
class APIDeletePortForwardingRuleMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.network.service.APIDeletePortForwardingRuleMsg'
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


APIQUERYEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIQueryEipMsg'
class APIQueryEipMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.service.eip.APIQueryEipMsg'
    def __init__(self):
        super(APIQueryEipMsg, self).__init__()


APIQUERYEIPREPLY_FULL_NAME = 'org.zstack.network.service.eip.APIQueryEipReply'
class APIQueryEipReply(APIReply):
    FULL_NAME='org.zstack.network.service.eip.APIQueryEipReply'
    def __init__(self):
        super(APIQueryEipReply, self).__init__()
        self.inventories = None


APIDELETEEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIDeleteEipMsg'
class APIDeleteEipMsg(APIDeleteMessage):
    FULL_NAME='org.zstack.network.service.eip.APIDeleteEipMsg'
    def __init__(self):
        super(APIDeleteEipMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APICREATEEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APICreateEipMsg'
class APICreateEipMsg(APIMessage):
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


APICHANGESECURITYGROUPSTATEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIChangeSecurityGroupStateMsg'
class APIChangeSecurityGroupStateMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIChangeSecurityGroupStateMsg'
    def __init__(self):
        super(APIChangeSecurityGroupStateMsg, self).__init__()
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
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
        self.inventories = None


APIDELETESECURITYGROUPRULEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteSecurityGroupRuleMsg'
class APIDeleteSecurityGroupRuleMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteSecurityGroupRuleMsg'
    def __init__(self):
        super(APIDeleteSecurityGroupRuleMsg, self).__init__()
        #mandatory field
        self.ruleUuids = NotNoneField()


APICREATESECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APICreateSecurityGroupMsg'
class APICreateSecurityGroupMsg(APICreateMessage):
    FULL_NAME='org.zstack.network.securitygroup.APICreateSecurityGroupMsg'
    def __init__(self):
        super(APICreateSecurityGroupMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None


APILISTVMNICINSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIListVmNicInSecurityGroupMsg'
class APIListVmNicInSecurityGroupMsg(APIListMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIListVmNicInSecurityGroupMsg'
    def __init__(self):
        super(APIListVmNicInSecurityGroupMsg, self).__init__()


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
        self.inventories = None


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
        self.rules = NotNoneField()


APILISTSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIListSecurityGroupMsg'
class APIListSecurityGroupMsg(APIListMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIListSecurityGroupMsg'
    def __init__(self):
        super(APIListSecurityGroupMsg, self).__init__()


APIDELETESECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteSecurityGroupMsg'
class APIDeleteSecurityGroupMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteSecurityGroupMsg'
    def __init__(self):
        super(APIDeleteSecurityGroupMsg, self).__init__()
        #mandatory field
        self.securityGroupUuid = NotNoneField()


APIDELETEVMNICFROMSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteVmNicFromSecurityGroupMsg'
class APIDeleteVmNicFromSecurityGroupMsg(APIMessage):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteVmNicFromSecurityGroupMsg'
    def __init__(self):
        super(APIDeleteVmNicFromSecurityGroupMsg, self).__init__()
        self.securityGroupUuid = None
        self.vmNicUuid = None


APIQUERYSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupReply'
class APIQuerySecurityGroupReply(APIReply):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupReply'
    def __init__(self):
        super(APIQuerySecurityGroupReply, self).__init__()
        self.inventories = None


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
        self.vmNicUuids = NotNoneField()


APIQUERYVMNICINSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupReply'
class APIQueryVmNicInSecurityGroupReply(APIReply):
    FULL_NAME='org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupReply'
    def __init__(self):
        super(APIQueryVmNicInSecurityGroupReply, self).__init__()
        self.inventories = None


APIDELETEVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APIDeleteVipMsg'
class APIDeleteVipMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.vip.APIDeleteVipMsg'
    def __init__(self):
        super(APIDeleteVipMsg, self).__init__()
        #mandatory field
        self.uuid = NotNoneField()


APIQUERYVIPREPLY_FULL_NAME = 'org.zstack.network.service.vip.APIQueryVipReply'
class APIQueryVipReply(APIReply):
    FULL_NAME='org.zstack.network.service.vip.APIQueryVipReply'
    def __init__(self):
        super(APIQueryVipReply, self).__init__()
        self.inventories = None


APICREATEVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APICreateVipMsg'
class APICreateVipMsg(APIMessage):
    FULL_NAME='org.zstack.network.service.vip.APICreateVipMsg'
    def __init__(self):
        super(APICreateVipMsg, self).__init__()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        self.allocateStrategy = None


APIQUERYVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APIQueryVipMsg'
class APIQueryVipMsg(APIQueryMessage):
    FULL_NAME='org.zstack.network.service.vip.APIQueryVipMsg'
    def __init__(self):
        super(APIQueryVipMsg, self).__init__()


api_names = [
    'APISilentMsg',
    'APIListGlobalConfigMsg',
    'APIGetGlobalConfigMsg',
    'APIGetGlobalConfigReply',
    'APIListGlobalConfigReply',
    'APIUpdateGlobalConfigMsg',
    'APIQueryTagMsg',
    'APIQueryTagReply',
    'APIGenerateInventoryQueryDetailsMsg',
    'APIQueryCountReply',
    'APIRetrieveHostCapacityMsg',
    'APIRetrieveHostCapacityReply',
    'APIGetHostAllocatorStrategiesMsg',
    'APIGetHostAllocatorStrategiesReply',
    'APISearchVmInstanceReply',
    'APIGetVmInstanceReply',
    'APIMigrateVmMsg',
    'APIStopVmInstanceMsg',
    'APIAttachVolumeToVmMsg',
    'APIDetachVolumeFromVmMsg',
    'APIListVmInstanceReply',
    'APISearchVmInstanceMsg',
    'APIQueryVmNicMsg',
    'APIListVmNicReply',
    'APIDestroyVmInstanceMsg',
    'APIQueryVmInstanceMsg',
    'APIListVmNicMsg',
    'APIAttachNicToVmMsg',
    'APIListVmInstanceMsg',
    'APIQueryVmInstanceReply',
    'APIRebootVmInstanceMsg',
    'APIQueryVmNicReply',
    'APICreateVmInstanceMsg',
    'APIGetVmInstanceMsg',
    'APIStartVmInstanceMsg',
    'APICreateTemplateFromRootVolumeMsg',
    'APIChangeImageStateMsg',
    'APIGetImageMsg',
    'APICreateTemplateFromVolumeSnapshotMsg',
    'APIDeleteImageMsg',
    'APISearchImageMsg',
    'APIGetImageReply',
    'APIQueryImageReply',
    'APIListImageReply',
    'APISearchImageReply',
    'APIQueryImageMsg',
    'APIListImageMsg',
    'APIAddImageMsg',
    'APIRequestConsoleAccessMsg',
    'APISearchVolumeMsg',
    'APIQueryVolumeMsg',
    'APICreateDataVolumeFromVolumeSnapshotMsg',
    'APIQueryVolumeReply',
    'APIGetVolumeMsg',
    'APICreateDataVolumeMsg',
    'APIGetVolumeReply',
    'APIListVolumeReply',
    'APISearchVolumeReply',
    'APIDeleteDataVolumeMsg',
    'APICreateVolumeSnapshotMsg',
    'APIListVolumeMsg',
    'APIChangeVolumeStateMsg',
    'APIIsReadyToGoMsg',
    'APIListDiskOfferingMsg',
    'APIDeleteDiskOfferingMsg',
    'APISearchInstanceOfferingReply',
    'APIGenerateGroovyClassMsg',
    'APIQueryInstanceOfferingMsg',
    'APIGenerateApiJsonTemplateMsg',
    'APIListDiskOfferingReply',
    'APIGetInstanceOfferingMsg',
    'APIAddDiskOfferingMsg',
    'APIListInstanceOfferingMsg',
    'APISearchDnsMsg',
    'APIListInstanceOfferingReply',
    'APISearchDiskOfferingMsg',
    'APIDeleteInstanceOfferingMsg',
    'APIGenerateSqlVOViewMsg',
    'APIGenerateTestLinkDocumentMsg',
    'APISearchDnsReply',
    'APIGetInstanceOfferingReply',
    'APIQueryDiskOfferingReply',
    'APIChangeInstanceOfferingStateMsg',
    'APIQueryDiskOfferingMsg',
    'APISearchDiskOfferingReply',
    'APIGetDiskOfferingMsg',
    'APIAddInstanceOfferingMsg',
    'APIChangeDiskOfferingStateMsg',
    'APIGetDiskOfferingReply',
    'APISearchInstanceOfferingMsg',
    'APIQueryInstanceOfferingReply',
    'APIListPrimaryStorageReply',
    'APIAttachPrimaryStorageMsg',
    'APISearchPrimaryStorageMsg',
    'APIGetPrimaryStorageTypesMsg',
    'APIGetPrimaryStorageTypesReply',
    'APIListPrimaryStorageMsg',
    'APIGetPrimaryStorageReply',
    'APISearchPrimaryStorageReply',
    'APIDetachPrimaryStorageMsg',
    'APIGetPrimaryStorageMsg',
    'APIQueryPrimaryStorageMsg',
    'APIChangePrimaryStorageStateMsg',
    'APIGetPrimaryStorageAllocatorStrategiesReply',
    'APIQueryPrimaryStorageReply',
    'APIDeletePrimaryStorageMsg',
    'CreateTemplateFromRootVolumeOnPrimaryStorageReply',
    'APIGetPrimaryStorageAllocatorStrategiesMsg',
    'APIDeleteVolumeSnapshotMsg',
    'APIQueryVolumeSnapshotReply',
    'APIDeleteVolumeSnapshotFromBackupStorageMsg',
    'APIQueryVolumeSnapshotMsg',
    'APIRevertVolumeFromSnapshotMsg',
    'APIBackupVolumeSnapshotMsg',
    'APIGetVolumeSnapshotTreeMsg',
    'APIGetVolumeSnapshotTreeReply',
    'APIQueryBackupStorageMsg',
    'APIListBackupStorageMsg',
    'APISearchBackupStorageReply',
    'APISearchBackupStorageMsg',
    'APIGetBackupStorageMsg',
    'APIGetBackupStorageTypesMsg',
    'APIChangeBackupStorageStateMsg',
    'APIQueryBackupStorageReply',
    'APIGetBackupStorageTypesReply',
    'APIScanBackupStorageMsg',
    'APIAttachBackupStorageMsg',
    'APIDetachBackupStorageMsg',
    'APIGetBackupStorageReply',
    'APIListBackupStorageReply',
    'APIDeleteBackupStorageMsg',
    'APIListL3NetworkMsg',
    'APIQueryNetworkServiceL3NetworkRefReply',
    'APIAddDnsToL3NetworkMsg',
    'APICreateL3NetworkMsg',
    'APIListIpRangeReply',
    'APISearchL3NetworkReply',
    'APIGetL3NetworkTypesReply',
    'APIDeleteIpRangeMsg',
    'APIAttachL2NetworkToClusterMsg',
    'APIQueryL2VlanNetworkMsg',
    'APIChangeL3NetworkStateMsg',
    'APIAttachNetworkServiceToL3NetworkMsg',
    'APIGetL3NetworkReply',
    'APIGetL2VlanNetworkReply',
    'APIAddNetworkServiceProviderMsg',
    'APIGetL2NetworkReply',
    'APIGetL3NetworkMsg',
    'APIGetL2NetworkMsg',
    'APIListL2NetworkMsg',
    'APISearchL2VlanNetworkMsg',
    'APICreateL2VlanNetworkMsg',
    'APIAddIpRangeMsg',
    'APIGetL3NetworkTypesMsg',
    'APIQueryL2VlanNetworkReply',
    'APIDetachL2NetworkFromClusterMsg',
    'APISearchNetworkServiceProviderReply',
    'APISearchL3NetworkMsg',
    'APIGetL2NetworkTypesReply',
    'APIListL2VlanNetworkReply',
    'APIQueryNetworkServiceL3NetworkRefMsg',
    'APIDeleteL2NetworkMsg',
    'APIAttachNetworkServiceProviderToL2NetworkMsg',
    'APIGetNetworkServiceProviderReply',
    'APIQueryL3NetworkReply',
    'APISearchL2VlanNetworkReply',
    'APISearchNetworkServiceProviderMsg',
    'APIQueryIpRangeMsg',
    'APIQueryL2NetworkReply',
    'APISearchL2NetworkMsg',
    'APIDetachNetworkServiceProviderFromL2NetworkMsg',
    'APIDeleteIpRangeCarrierMsg',
    'APIRemoveDnsFromL3NetworkMsg',
    'APIQueryNetworkServiceProviderMsg',
    'APIQueryIpRangeReply',
    'APIListIpRangeMsg',
    'APIListL2VlanNetworkMsg',
    'APISearchL2NetworkReply',
    'APIGetNetworkServiceTypesMsg',
    'APIGetNetworkServiceTypesReply',
    'APIListL2NetworkReply',
    'APIGetL2VlanNetworkMsg',
    'APIGetNetworkServiceProviderMsg',
    'APIListL3NetworkReply',
    'APIDeleteL3NetworkMsg',
    'APIListNetworkServiceProviderMsg',
    'APIListNetworkServiceProviderReply',
    'APIQueryNetworkServiceProviderReply',
    'APIGetL2NetworkTypesMsg',
    'APIAttachDnsToL3NetworkMsg',
    'APIQueryL2NetworkMsg',
    'APIQueryL3NetworkMsg',
    'APIDeleteSearchIndexMsg',
    'APISearchGenerateSqlTriggerMsg',
    'APICreateSearchIndexMsg',
    'APIQueryManagementNodeReply',
    'APIQueryManagementNodeMsg',
    'APIListManagementNodeMsg',
    'APIListManagementNodeReply',
    'APISearchClusterReply',
    'APIListClusterMsg',
    'APIListClusterReply',
    'APIGetClusterMsg',
    'APISearchClusterMsg',
    'APIQueryClusterMsg',
    'APIDeleteClusterMsg',
    'APIGetClusterReply',
    'APICreateClusterMsg',
    'APIChangeClusterStateMsg',
    'APIQueryClusterReply',
    'APIListUserReply',
    'APIAttachPolicyToUserGroupMsg',
    'APIAttachPolicyToUserMsg',
    'APIGetAccountMsg',
    'APIListAccountMsg',
    'APIGetUserReply',
    'APIGetAccountReply',
    'APIListAccountReply',
    'APISearchPolicyReply',
    'APIListPolicyMsg',
    'APICreateAccountMsg',
    'APICreateUserGroupMsg',
    'APICreateUserMsg',
    'APILogInByUserMsg',
    'APISearchAccountMsg',
    'APISearchPolicyMsg',
    'APIGetUserMsg',
    'APIGetUserGroupMsg',
    'APILogOutReply',
    'APISearchUserGroupReply',
    'APIAttachUserToUserGroupMsg',
    'APIGetPolicyReply',
    'APILogInReply',
    'APIListPolicyReply',
    'APIGetUserGroupReply',
    'APIResetAccountPasswordMsg',
    'APILogInByAccountMsg',
    'APIValidateSessionMsg',
    'APISearchAccountReply',
    'APISearchUserGroupMsg',
    'APIListUserMsg',
    'APISearchUserReply',
    'APISearchUserMsg',
    'APILogOutMsg',
    'APIGetPolicyMsg',
    'APICreatePolicyMsg',
    'APIValidateSessionReply',
    'APIGetZoneReply',
    'APIGetZoneMsg',
    'APISearchZoneReply',
    'APIListZonesReply',
    'APIDeleteZoneMsg',
    'APICreateZoneMsg',
    'APIQueryZoneReply',
    'APISearchZoneMsg',
    'APIQueryZoneMsg',
    'APIListZonesMsg',
    'APIChangeZoneStateMsg',
    'APIGetHypervisorTypesReply',
    'APIChangeHostStateMsg',
    'APIGetHostReply',
    'APIListHostReply',
    'APIReconnectHostMsg',
    'APIListHostMsg',
    'APIDeleteHostMsg',
    'APISearchHostReply',
    'APIGetHostMsg',
    'APIQueryHostReply',
    'APISearchHostMsg',
    'APIGetHypervisorTypesMsg',
    'APIQueryHostMsg',
    'APIAddSimulatorHostMsg',
    'APIAddSimulatorPrimaryStorageMsg',
    'APIAddSimulatorBackupStorageMsg',
    'APIListApplianceVmMsg',
    'APIQueryApplianceVmMsg',
    'APIQueryApplianceVmReply',
    'APIListApplianceVmReply',
    'APIAddKVMHostMsg',
    'APIAddNfsPrimaryStorageMsg',
    'APIGetSftpBackupStorageMsg',
    'APISearchSftpBackupStorageMsg',
    'APIQuerySftpBackupStorageMsg',
    'APIReconnectSftpBackupStorageMsg',
    'APIGetSftpBackupStorageReply',
    'APIQuerySftpBackupStorageReply',
    'APIAddSftpBackupStorageMsg',
    'APISearchSftpBackupStorageReply',
    'APISearchVirtualRouterVmReply',
    'APIAddVirtualRouterOfferingMsg',
    'APICreateVirtualRouterVmMsg',
    'APIGetVirtualRouterOfferingMsg',
    'APISearchVirtualRouterVmMsg',
    'APIQueryVirtualRouterOfferingMsg',
    'APIGetVirtualRouterOfferingReply',
    'APISearchVirtualRouterOffingMsg',
    'APISearchVirtualRouterOffingReply',
    'APIQueryVirtualRouterOfferingReply',
    'APIAttachPortForwardingRuleMsg',
    'APIDetachPortForwardingRuleMsg',
    'APIQueryPortForwardingRuleReply',
    'APIListPortForwardingRuleReply',
    'APIListPortForwardingRuleMsg',
    'APICreatePortForwardingRuleMsg',
    'APIQueryPortForwardingRuleMsg',
    'APIDeletePortForwardingRuleMsg',
    'APIDetachEipMsg',
    'APIQueryEipMsg',
    'APIQueryEipReply',
    'APIDeleteEipMsg',
    'APICreateEipMsg',
    'APIAttachEipMsg',
    'APIChangeSecurityGroupStateMsg',
    'APIDetachSecurityGroupFromL3NetworkMsg',
    'APIListSecurityGroupReply',
    'APIDeleteSecurityGroupRuleMsg',
    'APICreateSecurityGroupMsg',
    'APIListVmNicInSecurityGroupMsg',
    'APIQueryVmNicInSecurityGroupMsg',
    'APIListVmNicInSecurityGroupReply',
    'APIQuerySecurityGroupMsg',
    'APIAddSecurityGroupRuleMsg',
    'APIListSecurityGroupMsg',
    'APIDeleteSecurityGroupMsg',
    'APIDeleteVmNicFromSecurityGroupMsg',
    'APIQuerySecurityGroupReply',
    'APIAttachSecurityGroupToL3NetworkMsg',
    'APIAddVmNicToSecurityGroupMsg',
    'APIQueryVmNicInSecurityGroupReply',
    'APIDeleteVipMsg',
    'APIQueryVipReply',
    'APICreateVipMsg',
    'APIQueryVipMsg',
]

class GlobalConfigInventory(object):
    def __init__(self):
        self.id = None
        self.name = None
        self.category = None
        self.description = None
        self.defaultValue = None
        self.value = None

    def evaluate(self, inv):
        if hasattr(inv, 'id'):
            self.id = inv.id
        else:
            self.id = None

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
        self.type = None
        self.hypervisorType = None
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

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

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
        self.bits = None
        self.url = None
        self.installUrl = None
        self.format = None
        self.hypervisorType = None
        self.guestOsType = None
        self.backupStorageUuid = None
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

        if hasattr(inv, 'bits'):
            self.bits = inv.bits
        else:
            self.bits = None

        if hasattr(inv, 'url'):
            self.url = inv.url
        else:
            self.url = None

        if hasattr(inv, 'installUrl'):
            self.installUrl = inv.installUrl
        else:
            self.installUrl = None

        if hasattr(inv, 'format'):
            self.format = inv.format
        else:
            self.format = None

        if hasattr(inv, 'hypervisorType'):
            self.hypervisorType = inv.hypervisorType
        else:
            self.hypervisorType = None

        if hasattr(inv, 'guestOsType'):
            self.guestOsType = inv.guestOsType
        else:
            self.guestOsType = None

        if hasattr(inv, 'backupStorageUuid'):
            self.backupStorageUuid = inv.backupStorageUuid
        else:
            self.backupStorageUuid = None

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
        self.rootImageUuid = None
        self.installUrl = None
        self.volumeType = None
        self.hypervisorType = None
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

        if hasattr(inv, 'rootImageUuid'):
            self.rootImageUuid = inv.rootImageUuid
        else:
            self.rootImageUuid = None

        if hasattr(inv, 'installUrl'):
            self.installUrl = inv.installUrl
        else:
            self.installUrl = None

        if hasattr(inv, 'volumeType'):
            self.volumeType = inv.volumeType
        else:
            self.volumeType = None

        if hasattr(inv, 'hypervisorType'):
            self.hypervisorType = inv.hypervisorType
        else:
            self.hypervisorType = None

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
        self.hostTag = None
        self.type = None
        self.allocatorStrategy = None
        self.sortKey = None
        self.createDate = None
        self.lastOpDate = None
        self.visible = None
        self.ha = None
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

        if hasattr(inv, 'hostTag'):
            self.hostTag = inv.hostTag
        else:
            self.hostTag = None

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

        if hasattr(inv, 'visible'):
            self.visible = inv.visible
        else:
            self.visible = None

        if hasattr(inv, 'ha'):
            self.ha = inv.ha
        else:
            self.ha = None

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
        self.type = None
        self.state = None
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

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None

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

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



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



class L3NetworkInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.type = None
        self.trafficType = None
        self.zoneUuid = None
        self.l2NetworkUuid = None
        self.state = None
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

        if hasattr(inv, 'trafficType'):
            self.trafficType = inv.trafficType
        else:
            self.trafficType = None

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
        self.managementNodeId = None
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

        if hasattr(inv, 'managementNodeId'):
            self.managementNodeId = inv.managementNodeId
        else:
            self.managementNodeId = None

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
        self.securityKey = None
        self.token = None
        self.createDate = None
        self.lastOpDate = None
        self.groups = None
        self.policies = None

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

        if hasattr(inv, 'securityKey'):
            self.securityKey = inv.securityKey
        else:
            self.securityKey = None

        if hasattr(inv, 'token'):
            self.token = inv.token
        else:
            self.token = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'groups'):
            self.groups = inv.groups
        else:
            self.groups = None

        if hasattr(inv, 'policies'):
            self.policies = inv.policies
        else:
            self.policies = None



class UserGroupInventory(object):
    def __init__(self):
        self.uuid = None
        self.accountUuid = None
        self.name = None
        self.description = None
        self.createDate = None
        self.lastOpDate = None
        self.policies = None

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

        if hasattr(inv, 'policies'):
            self.policies = inv.policies
        else:
            self.policies = None



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
        self.uuid = None
        self.name = None
        self.accountUuid = None
        self.type = None
        self.data = None
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

        if hasattr(inv, 'accountUuid'):
            self.accountUuid = inv.accountUuid
        else:
            self.accountUuid = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'data'):
            self.data = inv.data
        else:
            self.data = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



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
        self.connectionState = None
        self.createDate = None
        self.lastOpDate = None
        self.hostTags = None

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

        if hasattr(inv, 'connectionState'):
            self.connectionState = inv.connectionState
        else:
            self.connectionState = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'hostTags'):
            self.hostTags = inv.hostTags
        else:
            self.hostTags = None



class ApplianceVmInventory(VmInstanceInventory):
    def __init__(self):
        super(ApplianceVmInventory, self).__init__()
        self.applianceVmType = None
        self.managementNicUuid = None
        self.defaultRouteL3NetworkUuid = None
        self.firewallRules = None

    def evaluate(self, inv):
        super(ApplianceVmInventory, self).evaluate(inv)
        if hasattr(inv, 'applianceVmType'):
            self.applianceVmType = inv.applianceVmType
        else:
            self.applianceVmType = None

        if hasattr(inv, 'managementNicUuid'):
            self.managementNicUuid = inv.managementNicUuid
        else:
            self.managementNicUuid = None

        if hasattr(inv, 'defaultRouteL3NetworkUuid'):
            self.defaultRouteL3NetworkUuid = inv.defaultRouteL3NetworkUuid
        else:
            self.defaultRouteL3NetworkUuid = None

        if hasattr(inv, 'firewallRules'):
            self.firewallRules = inv.firewallRules
        else:
            self.firewallRules = None



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



KVM_HYPERVISOR_TYPE = 'KVM'
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
L2_NO_VLAN_NETWORK_TYPE = 'L2NoVlanNetwork'
L2_VLAN_NETWORK_TYPE = 'L2VlanNetwork'
SIMULATOR_PRIMARY_STORAGE_TYPE = 'SimulatorPrimaryStorage'
SIMULATOR_BACKUP_STORAGE_TYPE = 'SimulatorBackupStorage'
ZSTACK_IMAGE_TYPE = 'zstack'
VIRTUAL_ROUTER_PROVIDER_TYPE = 'VirtualRouter'
VIRTUAL_ROUTER_VM_TYPE = 'VirtualRouter'
VIRTUAL_ROUTER_OFFERING_TYPE = 'VirtualRouter'
INGRESS = 'Ingress'
EGRESS = 'Egress'
VR_PUBLIC_NIC_META = '1'
VR_MANAGEMENT_NIC_META = '2'
VR_MANAGEMENT_AND_PUBLIC_NIC_META = '3'
SFTP_BACKUP_STORAGE_TYPE = 'SftpBackupStorage'
ZSTACK_CLUSTER_TYPE = 'zstack'
NFS_PRIMARY_STORAGE_TYPE = 'NFS'
SIMULATOR_HYPERVISOR_TYPE = 'Simulator'
USER_VM_TYPE = 'UserVm'
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
INITIAL_SYSTEM_ADMIN_UUID = '36c27e8ff05c4780bf6d2fa65700f22e'
INITIAL_SYSTEM_ADMIN_NAME = 'admin'
INITIAL_SYSTEM_ADMIN_PASSWORD = 'b109f3bbbc244eb82441917ed06d618b9008dd09b3befd1b5e07394c706a8bb980b1d7785e5976ec049b46df5f1326af5a2ea6d103fd07c95385ffab0cacbc86'
L3_BASIC_NETWORK_TYPE = 'L3BasicNetwork'
FIRST_AVAILABLE_IP_ALLOCATOR_STRATEGY = 'FirstAvailableIpAllocatorStrategy'
RANDOM_IP_ALLOCATOR_STRATEGY = 'RandomIpAllocatorStrategy'
TCP = 'TCP'
UDP = 'UDP'
ICMP = 'ICMP'
DEFAULT_PRIMARY_STORAGE_ALLOCATION_STRATEGY_TYPE = 'DefaultPrimaryStorageAllocationStrategy'

class GlobalConfig_VM(object):
    DATAVOLUME_DELETEONVMDESTROY = 'dataVolume.deleteOnVmDestroy'

    @staticmethod
    def get_category():
        return 'vm'

class GlobalConfig_EIP(object):
    SNATINBOUNDTRAFFIC = 'snatInboundTraffic'

    @staticmethod
    def get_category():
        return 'eip'

class GlobalConfig_SEARCH(object):
    DEFAULTSEARCHSIZE = 'DefaultSearchSize'

    @staticmethod
    def get_category():
        return 'Search'

class GlobalConfig_HOST(object):
    PING_INTERVAL = 'ping.interval'
    PING_DELAY = 'ping.delay'
    PING_TIMEOUT = 'ping.timeout'
    TRACK_PARALLELISMDEGREE = 'track.parallelismDegree'
    LOAD_PARALLELISMDEGREE = 'load.parallelismDegree'
    MAINTENANCEMODE_IGNOREERROR = 'maintenanceMode.ignoreError'
    LOAD_SIMULTANEOUS = 'load.simultaneous'
    CONNECTION_AUTORECONNECTONERROR = 'connection.autoReconnectOnError'

    @staticmethod
    def get_category():
        return 'host'

class GlobalConfig_OTHERS(object):
    TEST2 = 'Test2'

    @staticmethod
    def get_category():
        return 'Others'

class GlobalConfig_SNAPSHOT(object):
    BACKUP_PARALLELISMDEGREE = 'backup.parallelismDegree'
    DELETE_PARALLELISMDEGREE = 'delete.parallelismDegree'
    INCREMENTALSNAPSHOT_MAXNUM = 'incrementalSnapshot.maxNum'

    @staticmethod
    def get_category():
        return 'snapshot'

class GlobalConfig_SECURITYGROUP(object):
    REFRESH_DELAYINTERVAL = 'refresh.delayInterval'
    HOST_FAILUREWORKERINTERVAL = 'host.failureWorkerInterval'
    HOST_FAILURERESOLVEPERTIME = 'host.failureResolvePerTime'

    @staticmethod
    def get_category():
        return 'securityGroup'

class GlobalConfig_APPLIANCE_VM(object):
    CONNECT_TIMEOUT = 'connect.timeout'

    @staticmethod
    def get_category():
        return 'appliance.vm'

class GlobalConfig_MANAGEMENTSERVER(object):
    NODE_JOINDELAY = 'node.joinDelay'
    NODE_HEARTBEATINTERVAL = 'node.heartbeatInterval'

    @staticmethod
    def get_category():
        return 'managementServer'

class GlobalConfig_BACKUPSTORAGE(object):
    DISK_THRESHOLD = 'disk.threshold'
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'
    PING_INTERVAL = 'ping.interval'

    @staticmethod
    def get_category():
        return 'backupStorage'

class GlobalConfig_IDENTITY(object):
    SESSION_CLEANUP_INTERVAL = 'session.cleanup.interval'
    SESSION_TIMEOUT = 'session.timeout'
    SESSION_MAXCONCURRENT = 'session.maxConcurrent'

    @staticmethod
    def get_category():
        return 'identity'

class GlobalConfig_HOSTALLOCATOR(object):
    CPU_THRESHOLD = 'cpu.threshold'
    MEMORY_THRESHOLD = 'memory.threshold'

    @staticmethod
    def get_category():
        return 'hostAllocator'

class GlobalConfig_CONSOLE(object):
    PROXY_IDLETIMEOUT = 'proxy.idleTimeout'

    @staticmethod
    def get_category():
        return 'console'

class GlobalConfig_TEST(object):
    HIDDENTEST = 'HiddenTest'
    TEST = 'Test'
    TEST3 = 'Test3'
    TEST4 = 'Test4'

    @staticmethod
    def get_category():
        return 'Test'

class GlobalConfig_PUPPET(object):
    USEJOBQUEUE = 'useJobQueue'

    @staticmethod
    def get_category():
        return 'puppet'

class GlobalConfig_NFSPRIMARYSTORAGE(object):
    MOUNT_BASE = 'mount.base'

    @staticmethod
    def get_category():
        return 'nfsPrimaryStorage'

class GlobalConfig_CONFIGURATION(object):
    KEY_PRIVATE = 'key.private'
    KEY_PUBLIC = 'key.public'

    @staticmethod
    def get_category():
        return 'configuration'

class GlobalConfig_PRIMARYSTORAGE(object):
    IMAGECACHE_GARBAGECOLLECTOR_INTERVAL = 'imageCache.garbageCollector.interval'

    @staticmethod
    def get_category():
        return 'primaryStorage'

class GlobalConfig_SALT(object):
    MINION_APPLYSTATE_RETRY_INTERVAL = 'minion.applyState.retry.interval'
    MINION_APPLYSTATE_RETRY = 'minion.applyState.retry'
    MINION_SETUPINJOB = 'minion.setupInJob'

    @staticmethod
    def get_category():
        return 'salt'

class GlobalConfig_KVM(object):
    PING_TIMEOUT = 'ping.timeout'
    VM_MIGRATIONQUANTITY = 'vm.migrationQuantity'

    @staticmethod
    def get_category():
        return 'kvm'
