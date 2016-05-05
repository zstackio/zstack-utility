

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
class APIDeleteMessage(object):
    FULL_NAME='org.zstack.header.message.APIDeleteMessage'
    def __init__(self):
        self.deleteMode = None
        self.session = None
        self.timeout = None


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


APIQUERYAPPLIANCEVMREPLY_FULL_NAME = 'org.zstack.appliancevm.APIQueryApplianceVmReply'
class APIQueryApplianceVmReply(object):
    FULL_NAME='org.zstack.appliancevm.APIQueryApplianceVmReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYAPPLIANCEVMMSG_FULL_NAME = 'org.zstack.appliancevm.APIQueryApplianceVmMsg'
class APIQueryApplianceVmMsg(object):
    FULL_NAME='org.zstack.appliancevm.APIQueryApplianceVmMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APILISTAPPLIANCEVMREPLY_FULL_NAME = 'org.zstack.appliancevm.APIListApplianceVmReply'
class APIListApplianceVmReply(object):
    FULL_NAME='org.zstack.appliancevm.APIListApplianceVmReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIADDMONTOCEPHPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.ceph.primary.APIAddMonToCephPrimaryStorageMsg'
class APIAddMonToCephPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.ceph.primary.APIAddMonToCephPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.monUrls = NotNoneList()
        self.session = None
        self.timeout = None


APIADDCEPHPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.ceph.primary.APIAddCephPrimaryStorageMsg'
class APIAddCephPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.ceph.primary.APIAddCephPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.monUrls = NotNoneList()
        self.rootVolumePoolName = None
        self.dataVolumePoolName = None
        self.imageCachePoolName = None
        self.url = None
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIREMOVEMONFROMCEPHPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.ceph.primary.APIRemoveMonFromCephPrimaryStorageMsg'
class APIRemoveMonFromCephPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.ceph.primary.APIRemoveMonFromCephPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.monHostnames = NotNoneList()
        self.session = None
        self.timeout = None


APIQUERYCEPHPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.ceph.primary.APIQueryCephPrimaryStorageMsg'
class APIQueryCephPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.ceph.primary.APIQueryCephPrimaryStorageMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIADDMONTOCEPHBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.ceph.backup.APIAddMonToCephBackupStorageMsg'
class APIAddMonToCephBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.ceph.backup.APIAddMonToCephBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.monUrls = NotNoneList()
        self.session = None
        self.timeout = None


APIADDCEPHBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.ceph.backup.APIAddCephBackupStorageMsg'
class APIAddCephBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.ceph.backup.APIAddCephBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.monUrls = NotNoneList()
        self.poolName = None
        self.url = None
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIREMOVEMONFROMCEPHBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.ceph.backup.APIRemoveMonFromCephBackupStorageMsg'
class APIRemoveMonFromCephBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.ceph.backup.APIRemoveMonFromCephBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.monHostnames = NotNoneList()
        self.session = None
        self.timeout = None


APIQUERYCEPHBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.ceph.backup.APIQueryCephBackupStorageMsg'
class APIQueryCephBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.ceph.backup.APIQueryCephBackupStorageMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIGETGLOBALCONFIGMSG_FULL_NAME = 'org.zstack.core.config.APIGetGlobalConfigMsg'
class APIGetGlobalConfigMsg(object):
    FULL_NAME='org.zstack.core.config.APIGetGlobalConfigMsg'
    def __init__(self):
        #mandatory field
        self.category = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYGLOBALCONFIGREPLY_FULL_NAME = 'org.zstack.core.config.APIQueryGlobalConfigReply'
class APIQueryGlobalConfigReply(object):
    FULL_NAME='org.zstack.core.config.APIQueryGlobalConfigReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIGETGLOBALCONFIGREPLY_FULL_NAME = 'org.zstack.core.config.APIGetGlobalConfigReply'
class APIGetGlobalConfigReply(object):
    FULL_NAME='org.zstack.core.config.APIGetGlobalConfigReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIQUERYGLOBALCONFIGMSG_FULL_NAME = 'org.zstack.core.config.APIQueryGlobalConfigMsg'
class APIQueryGlobalConfigMsg(object):
    FULL_NAME='org.zstack.core.config.APIQueryGlobalConfigMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APILISTGLOBALCONFIGREPLY_FULL_NAME = 'org.zstack.core.config.APIListGlobalConfigReply'
class APIListGlobalConfigReply(object):
    FULL_NAME='org.zstack.core.config.APIListGlobalConfigReply'
    def __init__(self):
        self.inventories = None
        self.success = None
        self.error = None


APIUPDATEGLOBALCONFIGMSG_FULL_NAME = 'org.zstack.core.config.APIUpdateGlobalConfigMsg'
class APIUpdateGlobalConfigMsg(object):
    FULL_NAME='org.zstack.core.config.APIUpdateGlobalConfigMsg'
    def __init__(self):
        #mandatory field
        self.category = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.value = None
        self.session = None
        self.timeout = None


APIGETEIPATTACHABLEVMNICSMSG_FULL_NAME = 'org.zstack.network.service.eip.APIGetEipAttachableVmNicsMsg'
class APIGetEipAttachableVmNicsMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APIGetEipAttachableVmNicsMsg'
    def __init__(self):
        self.eipUuid = None
        self.vipUuid = None
        self.session = None
        self.timeout = None


APIGETEIPATTACHABLEVMNICSREPLY_FULL_NAME = 'org.zstack.network.service.eip.APIGetEipAttachableVmNicsReply'
class APIGetEipAttachableVmNicsReply(object):
    FULL_NAME='org.zstack.network.service.eip.APIGetEipAttachableVmNicsReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIQueryEipMsg'
class APIQueryEipMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APIQueryEipMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIUPDATEEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIUpdateEipMsg'
class APIUpdateEipMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APIUpdateEipMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APICHANGEEIPSTATEMSG_FULL_NAME = 'org.zstack.network.service.eip.APIChangeEipStateMsg'
class APIChangeEipStateMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APIChangeEipStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIDETACHEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIDetachEipMsg'
class APIDetachEipMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APIDetachEipMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIATTACHEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIAttachEipMsg'
class APIAttachEipMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APIAttachEipMsg'
    def __init__(self):
        #mandatory field
        self.eipUuid = NotNoneField()
        #mandatory field
        self.vmNicUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIDELETEEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIDeleteEipMsg'
class APIDeleteEipMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APIDeleteEipMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APICREATEEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APICreateEipMsg'
class APICreateEipMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APICreateEipMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.vipUuid = NotNoneField()
        self.vmNicUuid = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYEIPREPLY_FULL_NAME = 'org.zstack.network.service.eip.APIQueryEipReply'
class APIQueryEipReply(object):
    FULL_NAME='org.zstack.network.service.eip.APIQueryEipReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIADDFUSIONSTORBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.fusionstor.backup.APIAddFusionstorBackupStorageMsg'
class APIAddFusionstorBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.backup.APIAddFusionstorBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.monUrls = NotNoneList()
        self.poolName = None
        self.url = None
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIREMOVEMONFROMFUSIONSTORBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.fusionstor.backup.APIRemoveMonFromFusionstorBackupStorageMsg'
class APIRemoveMonFromFusionstorBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.backup.APIRemoveMonFromFusionstorBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.monHostnames = NotNoneList()
        self.session = None
        self.timeout = None


APIADDMONTOFUSIONSTORBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.fusionstor.backup.APIAddMonToFusionstorBackupStorageMsg'
class APIAddMonToFusionstorBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.backup.APIAddMonToFusionstorBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.monUrls = NotNoneList()
        self.session = None
        self.timeout = None


APIQUERYFUSIONSTORBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.fusionstor.backup.APIQueryFusionstorBackupStorageMsg'
class APIQueryFusionstorBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.backup.APIQueryFusionstorBackupStorageMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIADDMONTOFUSIONSTORPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.fusionstor.primary.APIAddMonToFusionstorPrimaryStorageMsg'
class APIAddMonToFusionstorPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.primary.APIAddMonToFusionstorPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.monUrls = NotNoneList()
        self.session = None
        self.timeout = None


APIREMOVEMONFROMFUSIONSTORPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.fusionstor.primary.APIRemoveMonFromFusionstorPrimaryStorageMsg'
class APIRemoveMonFromFusionstorPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.primary.APIRemoveMonFromFusionstorPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.monHostnames = NotNoneList()
        self.session = None
        self.timeout = None


APIQUERYFUSIONSTORPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.fusionstor.primary.APIQueryFusionstorPrimaryStorageMsg'
class APIQueryFusionstorPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.primary.APIQueryFusionstorPrimaryStorageMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIADDFUSIONSTORPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.fusionstor.primary.APIAddFusionstorPrimaryStorageMsg'
class APIAddFusionstorPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.primary.APIAddFusionstorPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.monUrls = NotNoneList()
        self.rootVolumePoolName = None
        self.dataVolumePoolName = None
        self.imageCachePoolName = None
        self.url = None
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYNETWORKSERVICEL3NETWORKREFREPLY_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceL3NetworkRefReply'
class APIQueryNetworkServiceL3NetworkRefReply(object):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceL3NetworkRefReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIGETNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APIGetNetworkServiceProviderReply'
class APIGetNetworkServiceProviderReply(object):
    FULL_NAME='org.zstack.header.network.service.APIGetNetworkServiceProviderReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIATTACHNETWORKSERVICEPROVIDERTOL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.service.APIAttachNetworkServiceProviderToL2NetworkMsg'
class APIAttachNetworkServiceProviderToL2NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.service.APIAttachNetworkServiceProviderToL2NetworkMsg'
    def __init__(self):
        #mandatory field
        self.networkServiceProviderUuid = NotNoneField()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        self.session = None
        self.timeout = None


APILISTNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APIListNetworkServiceProviderReply'
class APIListNetworkServiceProviderReply(object):
    FULL_NAME='org.zstack.header.network.service.APIListNetworkServiceProviderReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYNETWORKSERVICEL3NETWORKREFMSG_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceL3NetworkRefMsg'
class APIQueryNetworkServiceL3NetworkRefMsg(object):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceL3NetworkRefMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIQUERYNETWORKSERVICEPROVIDERMSG_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceProviderMsg'
class APIQueryNetworkServiceProviderMsg(object):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceProviderMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIDETACHNETWORKSERVICEPROVIDERFROML2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.service.APIDetachNetworkServiceProviderFromL2NetworkMsg'
class APIDetachNetworkServiceProviderFromL2NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.service.APIDetachNetworkServiceProviderFromL2NetworkMsg'
    def __init__(self):
        #mandatory field
        self.networkServiceProviderUuid = NotNoneField()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIDETACHNETWORKSERVICEFROML3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.service.APIDetachNetworkServiceFromL3NetworkMsg'
class APIDetachNetworkServiceFromL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.service.APIDetachNetworkServiceFromL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.networkServices = NotNoneMap()
        self.session = None
        self.timeout = None


APIQUERYNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceProviderReply'
class APIQueryNetworkServiceProviderReply(object):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceProviderReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIADDNETWORKSERVICEPROVIDERMSG_FULL_NAME = 'org.zstack.header.network.service.APIAddNetworkServiceProviderMsg'
class APIAddNetworkServiceProviderMsg(object):
    FULL_NAME='org.zstack.header.network.service.APIAddNetworkServiceProviderMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.description = NotNoneField()
        #mandatory field
        self.networkServiceTypes = NotNoneList()
        #mandatory field
        self.type = NotNoneField()
        self.session = None
        self.timeout = None


APIGETNETWORKSERVICETYPESREPLY_FULL_NAME = 'org.zstack.header.network.service.APIGetNetworkServiceTypesReply'
class APIGetNetworkServiceTypesReply(object):
    FULL_NAME='org.zstack.header.network.service.APIGetNetworkServiceTypesReply'
    def __init__(self):
        self.serviceAndProviderTypes = OptionalMap()
        self.success = None
        self.error = None


APIATTACHNETWORKSERVICETOL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.service.APIAttachNetworkServiceToL3NetworkMsg'
class APIAttachNetworkServiceToL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.service.APIAttachNetworkServiceToL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.networkServices = NotNoneMap()
        self.session = None
        self.timeout = None


APISEARCHNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APISearchNetworkServiceProviderReply'
class APISearchNetworkServiceProviderReply(object):
    FULL_NAME='org.zstack.header.network.service.APISearchNetworkServiceProviderReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIGETNETWORKSERVICETYPESMSG_FULL_NAME = 'org.zstack.header.network.service.APIGetNetworkServiceTypesMsg'
class APIGetNetworkServiceTypesMsg(object):
    FULL_NAME='org.zstack.header.network.service.APIGetNetworkServiceTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APIDELETEL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APIDeleteL2NetworkMsg'
class APIDeleteL2NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APIDeleteL2NetworkMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APILISTL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIListL2VlanNetworkReply'
class APIListL2VlanNetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIListL2VlanNetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIATTACHL2NETWORKTOCLUSTERMSG_FULL_NAME = 'org.zstack.header.network.l2.APIAttachL2NetworkToClusterMsg'
class APIAttachL2NetworkToClusterMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APIAttachL2NetworkToClusterMsg'
    def __init__(self):
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIQueryL2NetworkReply'
class APIQueryL2NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIQueryL2NetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APILISTL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIListL2NetworkReply'
class APIListL2NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIListL2NetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APICREATEL2NOVLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APICreateL2NoVlanNetworkMsg'
class APICreateL2NoVlanNetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APICreateL2NoVlanNetworkMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.physicalInterface = NotNoneField()
        self.type = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIGETL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2NetworkReply'
class APIGetL2NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2NetworkReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIQUERYL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIQueryL2VlanNetworkReply'
class APIQueryL2VlanNetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIQueryL2VlanNetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYL2VLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APIQueryL2VlanNetworkMsg'
class APIQueryL2VlanNetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APIQueryL2VlanNetworkMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APISEARCHL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APISearchL2NetworkReply'
class APISearchL2NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APISearchL2NetworkReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIDETACHL2NETWORKFROMCLUSTERMSG_FULL_NAME = 'org.zstack.header.network.l2.APIDetachL2NetworkFromClusterMsg'
class APIDetachL2NetworkFromClusterMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APIDetachL2NetworkFromClusterMsg'
    def __init__(self):
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()
        self.session = None
        self.timeout = None


APISEARCHL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APISearchL2VlanNetworkReply'
class APISearchL2VlanNetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APISearchL2VlanNetworkReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIGETL2NETWORKTYPESMSG_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2NetworkTypesMsg'
class APIGetL2NetworkTypesMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2NetworkTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APICREATEL2VLANNETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APICreateL2VlanNetworkMsg'
class APICreateL2VlanNetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APICreateL2VlanNetworkMsg'
    def __init__(self):
        #mandatory field
        self.vlan = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.physicalInterface = NotNoneField()
        self.type = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIGETL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2VlanNetworkReply'
class APIGetL2VlanNetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2VlanNetworkReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIUPDATEL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APIUpdateL2NetworkMsg'
class APIUpdateL2NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APIUpdateL2NetworkMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIGETL2NETWORKTYPESREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2NetworkTypesReply'
class APIGetL2NetworkTypesReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2NetworkTypesReply'
    def __init__(self):
        self.l2NetworkTypes = OptionalList()
        self.success = None
        self.error = None


APIQUERYL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APIQueryL2NetworkMsg'
class APIQueryL2NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APIQueryL2NetworkMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIUPDATEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIUpdateL3NetworkMsg'
class APIUpdateL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIUpdateL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.system = None
        self.session = None
        self.timeout = None


APIADDIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIAddIpRangeMsg'
class APIAddIpRangeMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIAddIpRangeMsg'
    def __init__(self):
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
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIADDIPRANGEBYNETWORKCIDRMSG_FULL_NAME = 'org.zstack.header.network.l3.APIAddIpRangeByNetworkCidrMsg'
class APIAddIpRangeByNetworkCidrMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIAddIpRangeByNetworkCidrMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.networkCidr = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APILISTL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIListL3NetworkReply'
class APIListL3NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIListL3NetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIQueryL3NetworkReply'
class APIQueryL3NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIQueryL3NetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIQueryL3NetworkMsg'
class APIQueryL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIQueryL3NetworkMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIGETIPADDRESSCAPACITYMSG_FULL_NAME = 'org.zstack.header.network.l3.APIGetIpAddressCapacityMsg'
class APIGetIpAddressCapacityMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetIpAddressCapacityMsg'
    def __init__(self):
        self.zoneUuids = OptionalList()
        self.l3NetworkUuids = OptionalList()
        self.ipRangeUuids = OptionalList()
        self.all = None
        self.session = None
        self.timeout = None


APILISTIPRANGEREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIListIpRangeReply'
class APIListIpRangeReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIListIpRangeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIADDDNSTOL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIAddDnsToL3NetworkMsg'
class APIAddDnsToL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIAddDnsToL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.dns = NotNoneField()
        self.session = None
        self.timeout = None


APICREATEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APICreateL3NetworkMsg'
class APICreateL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APICreateL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        self.system = None
        self.dnsDomain = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APICHECKIPAVAILABILITYREPLY_FULL_NAME = 'org.zstack.header.network.l3.APICheckIpAvailabilityReply'
class APICheckIpAvailabilityReply(object):
    FULL_NAME='org.zstack.header.network.l3.APICheckIpAvailabilityReply'
    def __init__(self):
        self.available = None
        self.success = None
        self.error = None


APISEARCHL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APISearchL3NetworkReply'
class APISearchL3NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l3.APISearchL3NetworkReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIGETL3NETWORKTYPESMSG_FULL_NAME = 'org.zstack.header.network.l3.APIGetL3NetworkTypesMsg'
class APIGetL3NetworkTypesMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetL3NetworkTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APIREMOVEDNSFROML3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIRemoveDnsFromL3NetworkMsg'
class APIRemoveDnsFromL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIRemoveDnsFromL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.dns = NotNoneField()
        self.session = None
        self.timeout = None


APIGETIPADDRESSCAPACITYREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetIpAddressCapacityReply'
class APIGetIpAddressCapacityReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetIpAddressCapacityReply'
    def __init__(self):
        self.totalCapacity = None
        self.availableCapacity = None
        self.success = None
        self.error = None


APIQUERYIPRANGEREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIQueryIpRangeReply'
class APIQueryIpRangeReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIQueryIpRangeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIGETFREEIPMSG_FULL_NAME = 'org.zstack.header.network.l3.APIGetFreeIpMsg'
class APIGetFreeIpMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetFreeIpMsg'
    def __init__(self):
        self.l3NetworkUuid = None
        self.ipRangeUuid = None
        self.limit = None
        self.session = None
        self.timeout = None


APICHANGEL3NETWORKSTATEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIChangeL3NetworkStateMsg'
class APIChangeL3NetworkStateMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIChangeL3NetworkStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIDELETEIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIDeleteIpRangeMsg'
class APIDeleteIpRangeMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIDeleteIpRangeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIGETL3NETWORKTYPESREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetL3NetworkTypesReply'
class APIGetL3NetworkTypesReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetL3NetworkTypesReply'
    def __init__(self):
        self.l3NetworkTypes = OptionalList()
        self.success = None
        self.error = None


APIGETL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetL3NetworkReply'
class APIGetL3NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetL3NetworkReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIDELETEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIDeleteL3NetworkMsg'
class APIDeleteL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIDeleteL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIQUERYIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIQueryIpRangeMsg'
class APIQueryIpRangeMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIQueryIpRangeMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIGETFREEIPREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetFreeIpReply'
class APIGetFreeIpReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetFreeIpReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APICHECKIPAVAILABILITYMSG_FULL_NAME = 'org.zstack.header.network.l3.APICheckIpAvailabilityMsg'
class APICheckIpAvailabilityMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APICheckIpAvailabilityMsg'
    def __init__(self):
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.ip = NotNoneField()
        self.session = None
        self.timeout = None


APIUPDATEIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIUpdateIpRangeMsg'
class APIUpdateIpRangeMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIUpdateIpRangeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIQUERYREPLY_FULL_NAME = 'org.zstack.header.query.APIQueryReply'
class APIQueryReply(object):
    FULL_NAME='org.zstack.header.query.APIQueryReply'
    def __init__(self):
        self.total = None
        self.success = None
        self.error = None


APIGENERATEQUERYABLEFIELDSMSG_FULL_NAME = 'org.zstack.header.query.APIGenerateQueryableFieldsMsg'
class APIGenerateQueryableFieldsMsg(object):
    FULL_NAME='org.zstack.header.query.APIGenerateQueryableFieldsMsg'
    def __init__(self):
        self.PYTHON_FORMAT = None
        self.format = None
        self.outputFolder = None
        self.session = None
        self.timeout = None


APIGENERATEINVENTORYQUERYDETAILSMSG_FULL_NAME = 'org.zstack.header.query.APIGenerateInventoryQueryDetailsMsg'
class APIGenerateInventoryQueryDetailsMsg(object):
    FULL_NAME='org.zstack.header.query.APIGenerateInventoryQueryDetailsMsg'
    def __init__(self):
        self.outputDir = None
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None


APIREPLY_FULL_NAME = 'org.zstack.header.message.APIReply'
class APIReply(object):
    FULL_NAME='org.zstack.header.message.APIReply'
    def __init__(self):
        self.success = None
        self.error = None


APICREATEMESSAGE_FULL_NAME = 'org.zstack.header.message.APICreateMessage'
class APICreateMessage(object):
    FULL_NAME='org.zstack.header.message.APICreateMessage'
    def __init__(self):
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APISEARCHREPLY_FULL_NAME = 'org.zstack.header.search.APISearchReply'
class APISearchReply(object):
    FULL_NAME='org.zstack.header.search.APISearchReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APICREATESEARCHINDEXMSG_FULL_NAME = 'org.zstack.header.search.APICreateSearchIndexMsg'
class APICreateSearchIndexMsg(object):
    FULL_NAME='org.zstack.header.search.APICreateSearchIndexMsg'
    def __init__(self):
        #mandatory field
        self.inventoryNames = NotNoneList()
        self.isRecreate = None
        self.session = None
        self.timeout = None


APISEARCHGENERATESQLTRIGGERMSG_FULL_NAME = 'org.zstack.header.search.APISearchGenerateSqlTriggerMsg'
class APISearchGenerateSqlTriggerMsg(object):
    FULL_NAME='org.zstack.header.search.APISearchGenerateSqlTriggerMsg'
    def __init__(self):
        self.resultPath = None
        self.session = None
        self.timeout = None


APIDELETESEARCHINDEXMSG_FULL_NAME = 'org.zstack.header.search.APIDeleteSearchIndexMsg'
class APIDeleteSearchIndexMsg(object):
    FULL_NAME='org.zstack.header.search.APIDeleteSearchIndexMsg'
    def __init__(self):
        self.indexName = None
        self.session = None
        self.timeout = None


APIATTACHPOLICYTOUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIAttachPolicyToUserMsg'
class APIAttachPolicyToUserMsg(object):
    FULL_NAME='org.zstack.header.identity.APIAttachPolicyToUserMsg'
    def __init__(self):
        #mandatory field
        self.userUuid = NotNoneField()
        #mandatory field
        self.policyUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIUPDATEUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIUpdateUserMsg'
class APIUpdateUserMsg(object):
    FULL_NAME='org.zstack.header.identity.APIUpdateUserMsg'
    def __init__(self):
        self.uuid = None
        self.password = None
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIGETACCOUNTQUOTAUSAGEMSG_FULL_NAME = 'org.zstack.header.identity.APIGetAccountQuotaUsageMsg'
class APIGetAccountQuotaUsageMsg(object):
    FULL_NAME='org.zstack.header.identity.APIGetAccountQuotaUsageMsg'
    def __init__(self):
        self.uuid = None
        self.session = None
        self.timeout = None


APIVALIDATESESSIONREPLY_FULL_NAME = 'org.zstack.header.identity.APIValidateSessionReply'
class APIValidateSessionReply(object):
    FULL_NAME='org.zstack.header.identity.APIValidateSessionReply'
    def __init__(self):
        self.validSession = None
        self.success = None
        self.error = None


APILOGINBYACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APILogInByAccountMsg'
class APILogInByAccountMsg(object):
    FULL_NAME='org.zstack.header.identity.APILogInByAccountMsg'
    def __init__(self):
        #mandatory field
        self.accountName = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        self.session = None
        self.timeout = None


APISESSIONMESSAGE_FULL_NAME = 'org.zstack.header.identity.APISessionMessage'
class APISessionMessage(object):
    FULL_NAME='org.zstack.header.identity.APISessionMessage'
    def __init__(self):
        self.session = None
        self.timeout = None


APIVALIDATESESSIONMSG_FULL_NAME = 'org.zstack.header.identity.APIValidateSessionMsg'
class APIValidateSessionMsg(object):
    FULL_NAME='org.zstack.header.identity.APIValidateSessionMsg'
    def __init__(self):
        #mandatory field
        self.sessionUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIDELETEUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIDeleteUserGroupMsg'
class APIDeleteUserGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDeleteUserGroupMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIQUERYACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryAccountReply'
class APIQueryAccountReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryAccountReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIGETPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetPolicyReply'
class APIGetPolicyReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetPolicyReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIDELETEUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIDeleteUserMsg'
class APIDeleteUserMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDeleteUserMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIATTACHPOLICIESTOUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIAttachPoliciesToUserMsg'
class APIAttachPoliciesToUserMsg(object):
    FULL_NAME='org.zstack.header.identity.APIAttachPoliciesToUserMsg'
    def __init__(self):
        #mandatory field
        self.userUuid = NotNoneField()
        #mandatory field
        self.policyUuids = NotNoneList()
        self.session = None
        self.timeout = None


APILOGINREPLY_FULL_NAME = 'org.zstack.header.identity.APILogInReply'
class APILogInReply(object):
    FULL_NAME='org.zstack.header.identity.APILogInReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APILOGINBYUSERMSG_FULL_NAME = 'org.zstack.header.identity.APILogInByUserMsg'
class APILogInByUserMsg(object):
    FULL_NAME='org.zstack.header.identity.APILogInByUserMsg'
    def __init__(self):
        self.accountUuid = None
        self.accountName = None
        #mandatory field
        self.userName = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        self.session = None
        self.timeout = None


APIGETUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetUserReply'
class APIGetUserReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetUserReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APICREATEUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APICreateUserGroupMsg'
class APICreateUserGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APICreateUserGroupMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APILISTPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APIListPolicyReply'
class APIListPolicyReply(object):
    FULL_NAME='org.zstack.header.identity.APIListPolicyReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APILISTUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APIListUserReply'
class APIListUserReply(object):
    FULL_NAME='org.zstack.header.identity.APIListUserReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETRESOURCEACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetResourceAccountReply'
class APIGetResourceAccountReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetResourceAccountReply'
    def __init__(self):
        self.inventories = OptionalMap()
        self.success = None
        self.error = None


APIUPDATEUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIUpdateUserGroupMsg'
class APIUpdateUserGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APIUpdateUserGroupMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APICHECKAPIPERMISSIONREPLY_FULL_NAME = 'org.zstack.header.identity.APICheckApiPermissionReply'
class APICheckApiPermissionReply(object):
    FULL_NAME='org.zstack.header.identity.APICheckApiPermissionReply'
    def __init__(self):
        self.inventory = OptionalMap()
        self.success = None
        self.error = None


APIADDUSERTOGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIAddUserToGroupMsg'
class APIAddUserToGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APIAddUserToGroupMsg'
    def __init__(self):
        #mandatory field
        self.userUuid = NotNoneField()
        #mandatory field
        self.groupUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIUPDATEQUOTAMSG_FULL_NAME = 'org.zstack.header.identity.APIUpdateQuotaMsg'
class APIUpdateQuotaMsg(object):
    FULL_NAME='org.zstack.header.identity.APIUpdateQuotaMsg'
    def __init__(self):
        #mandatory field
        self.identityUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.value = NotNoneField()
        self.session = None
        self.timeout = None


APILOGOUTMSG_FULL_NAME = 'org.zstack.header.identity.APILogOutMsg'
class APILogOutMsg(object):
    FULL_NAME='org.zstack.header.identity.APILogOutMsg'
    def __init__(self):
        self.sessionUuid = None
        self.session = None
        self.timeout = None


APIQUERYSHAREDRESOURCEMSG_FULL_NAME = 'org.zstack.header.identity.APIQuerySharedResourceMsg'
class APIQuerySharedResourceMsg(object):
    FULL_NAME='org.zstack.header.identity.APIQuerySharedResourceMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APICREATEUSERMSG_FULL_NAME = 'org.zstack.header.identity.APICreateUserMsg'
class APICreateUserMsg(object):
    FULL_NAME='org.zstack.header.identity.APICreateUserMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        self.description = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIDETACHPOLICIESFROMUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIDetachPoliciesFromUserMsg'
class APIDetachPoliciesFromUserMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDetachPoliciesFromUserMsg'
    def __init__(self):
        #mandatory field
        self.policyUuids = NotNoneList()
        #mandatory field
        self.userUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETUSERGROUPREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetUserGroupReply'
class APIGetUserGroupReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetUserGroupReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIQUERYPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryPolicyReply'
class APIQueryPolicyReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryPolicyReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIDETACHPOLICYFROMUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIDetachPolicyFromUserMsg'
class APIDetachPolicyFromUserMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDetachPolicyFromUserMsg'
    def __init__(self):
        #mandatory field
        self.policyUuid = NotNoneField()
        #mandatory field
        self.userUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYQUOTAREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryQuotaReply'
class APIQueryQuotaReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryQuotaReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APISHARERESOURCEMSG_FULL_NAME = 'org.zstack.header.identity.APIShareResourceMsg'
class APIShareResourceMsg(object):
    FULL_NAME='org.zstack.header.identity.APIShareResourceMsg'
    def __init__(self):
        #mandatory field
        self.resourceUuids = NotNoneList()
        self.accountUuids = OptionalList()
        self.toPublic = None
        self.session = None
        self.timeout = None


APIQUERYSHAREDRESOURCEREPLY_FULL_NAME = 'org.zstack.header.identity.APIQuerySharedResourceReply'
class APIQuerySharedResourceReply(object):
    FULL_NAME='org.zstack.header.identity.APIQuerySharedResourceReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIDELETEPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APIDeletePolicyMsg'
class APIDeletePolicyMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDeletePolicyMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIQUERYUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryUserGroupMsg'
class APIQueryUserGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APIQueryUserGroupMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIGETACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetAccountReply'
class APIGetAccountReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetAccountReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIQUERYQUOTAMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryQuotaMsg'
class APIQueryQuotaMsg(object):
    FULL_NAME='org.zstack.header.identity.APIQueryQuotaMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APISEARCHUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchUserReply'
class APISearchUserReply(object):
    FULL_NAME='org.zstack.header.identity.APISearchUserReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIQUERYACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryAccountMsg'
class APIQueryAccountMsg(object):
    FULL_NAME='org.zstack.header.identity.APIQueryAccountMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIREMOVEUSERFROMGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIRemoveUserFromGroupMsg'
class APIRemoveUserFromGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APIRemoveUserFromGroupMsg'
    def __init__(self):
        #mandatory field
        self.userUuid = NotNoneField()
        #mandatory field
        self.groupUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYACCOUNTRESOURCEREFREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryAccountResourceRefReply'
class APIQueryAccountResourceRefReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryAccountResourceRefReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYACCOUNTRESOURCEREFMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryAccountResourceRefMsg'
class APIQueryAccountResourceRefMsg(object):
    FULL_NAME='org.zstack.header.identity.APIQueryAccountResourceRefMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIQUERYUSERGROUPREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryUserGroupReply'
class APIQueryUserGroupReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryUserGroupReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APISEARCHACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchAccountReply'
class APISearchAccountReply(object):
    FULL_NAME='org.zstack.header.identity.APISearchAccountReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APICHECKAPIPERMISSIONMSG_FULL_NAME = 'org.zstack.header.identity.APICheckApiPermissionMsg'
class APICheckApiPermissionMsg(object):
    FULL_NAME='org.zstack.header.identity.APICheckApiPermissionMsg'
    def __init__(self):
        self.userUuid = None
        #mandatory field
        self.apiNames = NotNoneList()
        self.session = None
        self.timeout = None


APISEARCHPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchPolicyReply'
class APISearchPolicyReply(object):
    FULL_NAME='org.zstack.header.identity.APISearchPolicyReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIQUERYUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryUserMsg'
class APIQueryUserMsg(object):
    FULL_NAME='org.zstack.header.identity.APIQueryUserMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APICREATEPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APICreatePolicyMsg'
class APICreatePolicyMsg(object):
    FULL_NAME='org.zstack.header.identity.APICreatePolicyMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.statements = NotNoneList()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIDETACHPOLICYFROMUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIDetachPolicyFromUserGroupMsg'
class APIDetachPolicyFromUserGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDetachPolicyFromUserGroupMsg'
    def __init__(self):
        #mandatory field
        self.policyUuid = NotNoneField()
        #mandatory field
        self.groupUuid = NotNoneField()
        self.session = None
        self.timeout = None


APICREATEACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APICreateAccountMsg'
class APICreateAccountMsg(object):
    FULL_NAME='org.zstack.header.identity.APICreateAccountMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        #valid values: [SystemAdmin, Normal]
        self.type = None
        self.description = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APILOGOUTREPLY_FULL_NAME = 'org.zstack.header.identity.APILogOutReply'
class APILogOutReply(object):
    FULL_NAME='org.zstack.header.identity.APILogOutReply'
    def __init__(self):
        self.success = None
        self.error = None


APIQUERYUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryUserReply'
class APIQueryUserReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryUserReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIATTACHPOLICYTOUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIAttachPolicyToUserGroupMsg'
class APIAttachPolicyToUserGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APIAttachPolicyToUserGroupMsg'
    def __init__(self):
        #mandatory field
        self.policyUuid = NotNoneField()
        #mandatory field
        self.groupUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETRESOURCEACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APIGetResourceAccountMsg'
class APIGetResourceAccountMsg(object):
    FULL_NAME='org.zstack.header.identity.APIGetResourceAccountMsg'
    def __init__(self):
        #mandatory field
        self.resourceUuids = NotNoneList()
        self.session = None
        self.timeout = None


APIREVOKERESOURCESHARINGMSG_FULL_NAME = 'org.zstack.header.identity.APIRevokeResourceSharingMsg'
class APIRevokeResourceSharingMsg(object):
    FULL_NAME='org.zstack.header.identity.APIRevokeResourceSharingMsg'
    def __init__(self):
        #mandatory field
        self.resourceUuids = NotNoneList()
        self.toPublic = None
        self.accountUuids = OptionalList()
        self.all = None
        self.session = None
        self.timeout = None


APICHANGERESOURCEOWNERMSG_FULL_NAME = 'org.zstack.header.identity.APIChangeResourceOwnerMsg'
class APIChangeResourceOwnerMsg(object):
    FULL_NAME='org.zstack.header.identity.APIChangeResourceOwnerMsg'
    def __init__(self):
        #mandatory field
        self.accountUuid = NotNoneField()
        #mandatory field
        self.resourceUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIUPDATEACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APIUpdateAccountMsg'
class APIUpdateAccountMsg(object):
    FULL_NAME='org.zstack.header.identity.APIUpdateAccountMsg'
    def __init__(self):
        self.uuid = None
        self.password = None
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APISEARCHUSERGROUPREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchUserGroupReply'
class APISearchUserGroupReply(object):
    FULL_NAME='org.zstack.header.identity.APISearchUserGroupReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIGETACCOUNTQUOTAUSAGEREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetAccountQuotaUsageReply'
class APIGetAccountQuotaUsageReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetAccountQuotaUsageReply'
    def __init__(self):
        self.usages = OptionalList()
        self.success = None
        self.error = None


APIDELETEACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APIDeleteAccountMsg'
class APIDeleteAccountMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDeleteAccountMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIQUERYPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryPolicyMsg'
class APIQueryPolicyMsg(object):
    FULL_NAME='org.zstack.header.identity.APIQueryPolicyMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APILISTACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIListAccountReply'
class APIListAccountReply(object):
    FULL_NAME='org.zstack.header.identity.APIListAccountReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETVMCONSOLEADDRESSMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmConsoleAddressMsg'
class APIGetVmConsoleAddressMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmConsoleAddressMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APICHANGEINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.vm.APIChangeInstanceOfferingMsg'
class APIChangeInstanceOfferingMsg(object):
    FULL_NAME='org.zstack.header.vm.APIChangeInstanceOfferingMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.instanceOfferingUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETVMHOSTNAMEREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmHostnameReply'
class APIGetVmHostnameReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmHostnameReply'
    def __init__(self):
        self.hostname = None
        self.success = None
        self.error = None


APICREATEVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APICreateVmInstanceMsg'
class APICreateVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APICreateVmInstanceMsg'
    def __init__(self):
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
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIGETVMCONSOLEADDRESSREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmConsoleAddressReply'
class APIGetVmConsoleAddressReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmConsoleAddressReply'
    def __init__(self):
        self.hostIp = None
        self.port = None
        self.protocol = None
        self.success = None
        self.error = None


APILISTVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIListVmInstanceReply'
class APIListVmInstanceReply(object):
    FULL_NAME='org.zstack.header.vm.APIListVmInstanceReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APISTARTVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIStartVmInstanceMsg'
class APIStartVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIStartVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETVMBOOTORDERREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmBootOrderReply'
class APIGetVmBootOrderReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmBootOrderReply'
    def __init__(self):
        self.order = OptionalList()
        self.success = None
        self.error = None


APIQUERYVMNICMSG_FULL_NAME = 'org.zstack.header.vm.APIQueryVmNicMsg'
class APIQueryVmNicMsg(object):
    FULL_NAME='org.zstack.header.vm.APIQueryVmNicMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIQUERYVMNICREPLY_FULL_NAME = 'org.zstack.header.vm.APIQueryVmNicReply'
class APIQueryVmNicReply(object):
    FULL_NAME='org.zstack.header.vm.APIQueryVmNicReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIUPDATEVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIUpdateVmInstanceMsg'
class APIUpdateVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIUpdateVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        #valid values: [Stopped, Running]
        self.state = None
        self.defaultL3NetworkUuid = None
        #valid values: [Linux, Windows, Other, Paravirtualization, WindowsVirtio]
        self.platform = None
        self.session = None
        self.timeout = None


APIATTACHISOTOVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIAttachIsoToVmInstanceMsg'
class APIAttachIsoToVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIAttachIsoToVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.isoUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIDELETEVMHOSTNAMEMSG_FULL_NAME = 'org.zstack.header.vm.APIDeleteVmHostnameMsg'
class APIDeleteVmHostnameMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDeleteVmHostnameMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIGETVMHOSTNAMEMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmHostnameMsg'
class APIGetVmHostnameMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmHostnameMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETVMMIGRATIONCANDIDATEHOSTSMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmMigrationCandidateHostsMsg'
class APIGetVmMigrationCandidateHostsMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmMigrationCandidateHostsMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIQueryVmInstanceReply'
class APIQueryVmInstanceReply(object):
    FULL_NAME='org.zstack.header.vm.APIQueryVmInstanceReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APILISTVMNICREPLY_FULL_NAME = 'org.zstack.header.vm.APIListVmNicReply'
class APIListVmNicReply(object):
    FULL_NAME='org.zstack.header.vm.APIListVmNicReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETVMATTACHABLEL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableL3NetworkReply'
class APIGetVmAttachableL3NetworkReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableL3NetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIDETACHISOFROMVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIDetachIsoFromVmInstanceMsg'
class APIDetachIsoFromVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDetachIsoFromVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETVMATTACHABLEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableL3NetworkMsg'
class APIGetVmAttachableL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIREBOOTVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIRebootVmInstanceMsg'
class APIRebootVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIRebootVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIQueryVmInstanceMsg'
class APIQueryVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIQueryVmInstanceMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APISETVMSTATICIPMSG_FULL_NAME = 'org.zstack.header.vm.APISetVmStaticIpMsg'
class APISetVmStaticIpMsg(object):
    FULL_NAME='org.zstack.header.vm.APISetVmStaticIpMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.ip = NotNoneField()
        self.session = None
        self.timeout = None


APIGETVMATTACHABLEDATAVOLUMEREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableDataVolumeReply'
class APIGetVmAttachableDataVolumeReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableDataVolumeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIATTACHL3NETWORKTOVMMSG_FULL_NAME = 'org.zstack.header.vm.APIAttachL3NetworkToVmMsg'
class APIAttachL3NetworkToVmMsg(object):
    FULL_NAME='org.zstack.header.vm.APIAttachL3NetworkToVmMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIDESTROYVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIDestroyVmInstanceMsg'
class APIDestroyVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDestroyVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIGETVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmInstanceReply'
class APIGetVmInstanceReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmInstanceReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIMIGRATEVMMSG_FULL_NAME = 'org.zstack.header.vm.APIMigrateVmMsg'
class APIMigrateVmMsg(object):
    FULL_NAME='org.zstack.header.vm.APIMigrateVmMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.hostUuid = None
        self.session = None
        self.timeout = None


APIDELETEVMSTATICIPMSG_FULL_NAME = 'org.zstack.header.vm.APIDeleteVmStaticIpMsg'
class APIDeleteVmStaticIpMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDeleteVmStaticIpMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APISETVMBOOTORDERMSG_FULL_NAME = 'org.zstack.header.vm.APISetVmBootOrderMsg'
class APISetVmBootOrderMsg(object):
    FULL_NAME='org.zstack.header.vm.APISetVmBootOrderMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.bootOrder = OptionalList()
        self.session = None
        self.timeout = None


APISTOPVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIStopVmInstanceMsg'
class APIStopVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIStopVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIEXPUNGEVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIExpungeVmInstanceMsg'
class APIExpungeVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIExpungeVmInstanceMsg'
    def __init__(self):
        self.uuid = None
        self.session = None
        self.timeout = None


APIGETVMBOOTORDERMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmBootOrderMsg'
class APIGetVmBootOrderMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmBootOrderMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APISEARCHVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APISearchVmInstanceReply'
class APISearchVmInstanceReply(object):
    FULL_NAME='org.zstack.header.vm.APISearchVmInstanceReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIRECOVERVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIRecoverVmInstanceMsg'
class APIRecoverVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIRecoverVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETVMMIGRATIONCANDIDATEHOSTSREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmMigrationCandidateHostsReply'
class APIGetVmMigrationCandidateHostsReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmMigrationCandidateHostsReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETVMATTACHABLEDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableDataVolumeMsg'
class APIGetVmAttachableDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableDataVolumeMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None


APISETVMHOSTNAMEMSG_FULL_NAME = 'org.zstack.header.vm.APISetVmHostnameMsg'
class APISetVmHostnameMsg(object):
    FULL_NAME='org.zstack.header.vm.APISetVmHostnameMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.hostname = NotNoneField()
        self.session = None
        self.timeout = None


APIDETACHL3NETWORKFROMVMMSG_FULL_NAME = 'org.zstack.header.vm.APIDetachL3NetworkFromVmMsg'
class APIDetachL3NetworkFromVmMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDetachL3NetworkFromVmMsg'
    def __init__(self):
        #mandatory field
        self.vmNicUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGENERATESQLINDEXMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateSqlIndexMsg'
class APIGenerateSqlIndexMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateSqlIndexMsg'
    def __init__(self):
        self.outputPath = None
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None


APIGENERATEGROOVYCLASSMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateGroovyClassMsg'
class APIGenerateGroovyClassMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateGroovyClassMsg'
    def __init__(self):
        self.outputPath = None
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIQueryInstanceOfferingMsg'
class APIQueryInstanceOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIQueryInstanceOfferingMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIGENERATESQLVOVIEWMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateSqlVOViewMsg'
class APIGenerateSqlVOViewMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateSqlVOViewMsg'
    def __init__(self):
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None


APIGETGLOBALPROPERTYMSG_FULL_NAME = 'org.zstack.header.configuration.APIGetGlobalPropertyMsg'
class APIGetGlobalPropertyMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGetGlobalPropertyMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APISEARCHINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APISearchInstanceOfferingReply'
class APISearchInstanceOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APISearchInstanceOfferingReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIDELETEINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIDeleteInstanceOfferingMsg'
class APIDeleteInstanceOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIDeleteInstanceOfferingMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIQUERYDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIQueryDiskOfferingMsg'
class APIQueryDiskOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIQueryDiskOfferingMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIGENERATESQLFOREIGNKEYMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateSqlForeignKeyMsg'
class APIGenerateSqlForeignKeyMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateSqlForeignKeyMsg'
    def __init__(self):
        self.outputPath = None
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None


APIGENERATEAPIJSONTEMPLATEMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateApiJsonTemplateMsg'
class APIGenerateApiJsonTemplateMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateApiJsonTemplateMsg'
    def __init__(self):
        self.exportPath = None
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None


APICHANGEDISKOFFERINGSTATEMSG_FULL_NAME = 'org.zstack.header.configuration.APIChangeDiskOfferingStateMsg'
class APIChangeDiskOfferingStateMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIChangeDiskOfferingStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIGETDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIGetDiskOfferingReply'
class APIGetDiskOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIGetDiskOfferingReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIQUERYDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIQueryDiskOfferingReply'
class APIQueryDiskOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIQueryDiskOfferingReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APICHANGEINSTANCEOFFERINGSTATEMSG_FULL_NAME = 'org.zstack.header.configuration.APIChangeInstanceOfferingStateMsg'
class APIChangeInstanceOfferingStateMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIChangeInstanceOfferingStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIDELETEDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIDeleteDiskOfferingMsg'
class APIDeleteDiskOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIDeleteDiskOfferingMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIGETINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIGetInstanceOfferingReply'
class APIGetInstanceOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIGetInstanceOfferingReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGENERATEAPITYPESCRIPTDEFINITIONMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateApiTypeScriptDefinitionMsg'
class APIGenerateApiTypeScriptDefinitionMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateApiTypeScriptDefinitionMsg'
    def __init__(self):
        self.outputPath = None
        self.session = None
        self.timeout = None


APIGETGLOBALPROPERTYREPLY_FULL_NAME = 'org.zstack.header.configuration.APIGetGlobalPropertyReply'
class APIGetGlobalPropertyReply(object):
    FULL_NAME='org.zstack.header.configuration.APIGetGlobalPropertyReply'
    def __init__(self):
        self.properties = OptionalList()
        self.success = None
        self.error = None


APIGENERATETESTLINKDOCUMENTMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateTestLinkDocumentMsg'
class APIGenerateTestLinkDocumentMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateTestLinkDocumentMsg'
    def __init__(self):
        self.outputDir = None
        self.session = None
        self.timeout = None


APISEARCHDNSREPLY_FULL_NAME = 'org.zstack.header.configuration.APISearchDnsReply'
class APISearchDnsReply(object):
    FULL_NAME='org.zstack.header.configuration.APISearchDnsReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APICREATEDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APICreateDiskOfferingMsg'
class APICreateDiskOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APICreateDiskOfferingMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.diskSize = NotNoneField()
        self.sortKey = None
        self.allocationStrategy = None
        #valid values: [zstack]
        self.type = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APILISTINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIListInstanceOfferingReply'
class APIListInstanceOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIListInstanceOfferingReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APICREATEINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APICreateInstanceOfferingMsg'
class APICreateInstanceOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APICreateInstanceOfferingMsg'
    def __init__(self):
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
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIUPDATEDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIUpdateDiskOfferingMsg'
class APIUpdateDiskOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIUpdateDiskOfferingMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APILISTDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIListDiskOfferingReply'
class APIListDiskOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIListDiskOfferingReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIUPDATEINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIUpdateInstanceOfferingMsg'
class APIUpdateInstanceOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIUpdateInstanceOfferingMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APISEARCHDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APISearchDiskOfferingReply'
class APISearchDiskOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APISearchDiskOfferingReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIQUERYINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIQueryInstanceOfferingReply'
class APIQueryInstanceOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIQueryInstanceOfferingReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APIQueryVolumeReply'
class APIQueryVolumeReply(object):
    FULL_NAME='org.zstack.header.volume.APIQueryVolumeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIGETDATAVOLUMEATTACHABLEVMMSG_FULL_NAME = 'org.zstack.header.volume.APIGetDataVolumeAttachableVmMsg'
class APIGetDataVolumeAttachableVmMsg(object):
    FULL_NAME='org.zstack.header.volume.APIGetDataVolumeAttachableVmMsg'
    def __init__(self):
        #mandatory field
        self.volumeUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIBACKUPDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIBackupDataVolumeMsg'
class APIBackupDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIBackupDataVolumeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.backupStorageUuid = None
        self.session = None
        self.timeout = None


APICREATEDATAVOLUMEFROMVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.volume.APICreateDataVolumeFromVolumeSnapshotMsg'
class APICreateDataVolumeFromVolumeSnapshotMsg(object):
    FULL_NAME='org.zstack.header.volume.APICreateDataVolumeFromVolumeSnapshotMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.volumeSnapshotUuid = NotNoneField()
        self.primaryStorageUuid = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIATTACHDATAVOLUMETOVMMSG_FULL_NAME = 'org.zstack.header.volume.APIAttachDataVolumeToVmMsg'
class APIAttachDataVolumeToVmMsg(object):
    FULL_NAME='org.zstack.header.volume.APIAttachDataVolumeToVmMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.volumeUuid = NotNoneField()
        self.session = None
        self.timeout = None


APISEARCHVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APISearchVolumeReply'
class APISearchVolumeReply(object):
    FULL_NAME='org.zstack.header.volume.APISearchVolumeReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APICREATEDATAVOLUMEFROMVOLUMETEMPLATEMSG_FULL_NAME = 'org.zstack.header.volume.APICreateDataVolumeFromVolumeTemplateMsg'
class APICreateDataVolumeFromVolumeTemplateMsg(object):
    FULL_NAME='org.zstack.header.volume.APICreateDataVolumeFromVolumeTemplateMsg'
    def __init__(self):
        #mandatory field
        self.imageUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        self.hostUuid = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIQueryVolumeMsg'
class APIQueryVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIQueryVolumeMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APICHANGEVOLUMESTATEMSG_FULL_NAME = 'org.zstack.header.volume.APIChangeVolumeStateMsg'
class APIChangeVolumeStateMsg(object):
    FULL_NAME='org.zstack.header.volume.APIChangeVolumeStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APILISTVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APIListVolumeReply'
class APIListVolumeReply(object):
    FULL_NAME='org.zstack.header.volume.APIListVolumeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIDETACHDATAVOLUMEFROMVMMSG_FULL_NAME = 'org.zstack.header.volume.APIDetachDataVolumeFromVmMsg'
class APIDetachDataVolumeFromVmMsg(object):
    FULL_NAME='org.zstack.header.volume.APIDetachDataVolumeFromVmMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APICREATEDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APICreateDataVolumeMsg'
class APICreateDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APICreateDataVolumeMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.diskOfferingUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIGETDATAVOLUMEATTACHABLEVMREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetDataVolumeAttachableVmReply'
class APIGetDataVolumeAttachableVmReply(object):
    FULL_NAME='org.zstack.header.volume.APIGetDataVolumeAttachableVmReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeReply'
class APIGetVolumeReply(object):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIDELETEDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIDeleteDataVolumeMsg'
class APIDeleteDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIDeleteDataVolumeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APICREATEVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.volume.APICreateVolumeSnapshotMsg'
class APICreateVolumeSnapshotMsg(object):
    FULL_NAME='org.zstack.header.volume.APICreateVolumeSnapshotMsg'
    def __init__(self):
        #mandatory field
        self.volumeUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIGETVOLUMEFORMATMSG_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeFormatMsg'
class APIGetVolumeFormatMsg(object):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeFormatMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APIGETVOLUMEFORMATREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeFormatReply'
class APIGetVolumeFormatReply(object):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeFormatReply'
    def __init__(self):
        self.formats = OptionalList()
        self.success = None
        self.error = None


APIUPDATEVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIUpdateVolumeMsg'
class APIUpdateVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIUpdateVolumeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIEXPUNGEDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIExpungeDataVolumeMsg'
class APIExpungeDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIExpungeDataVolumeMsg'
    def __init__(self):
        self.uuid = None
        self.session = None
        self.timeout = None


APIRECOVERDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIRecoverDataVolumeMsg'
class APIRecoverDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIRecoverDataVolumeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYUSERTAGMSG_FULL_NAME = 'org.zstack.header.tag.APIQueryUserTagMsg'
class APIQueryUserTagMsg(object):
    FULL_NAME='org.zstack.header.tag.APIQueryUserTagMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIDELETETAGMSG_FULL_NAME = 'org.zstack.header.tag.APIDeleteTagMsg'
class APIDeleteTagMsg(object):
    FULL_NAME='org.zstack.header.tag.APIDeleteTagMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIQUERYTAGREPLY_FULL_NAME = 'org.zstack.header.tag.APIQueryTagReply'
class APIQueryTagReply(object):
    FULL_NAME='org.zstack.header.tag.APIQueryTagReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APICREATEUSERTAGMSG_FULL_NAME = 'org.zstack.header.tag.APICreateUserTagMsg'
class APICreateUserTagMsg(object):
    FULL_NAME='org.zstack.header.tag.APICreateUserTagMsg'
    def __init__(self):
        #mandatory field
        self.resourceType = NotNoneField()
        #mandatory field
        self.resourceUuid = NotNoneField()
        #mandatory field
        self.tag = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYUSERTAGREPLY_FULL_NAME = 'org.zstack.header.tag.APIQueryUserTagReply'
class APIQueryUserTagReply(object):
    FULL_NAME='org.zstack.header.tag.APIQueryUserTagReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APICREATESYSTEMTAGMSG_FULL_NAME = 'org.zstack.header.tag.APICreateSystemTagMsg'
class APICreateSystemTagMsg(object):
    FULL_NAME='org.zstack.header.tag.APICreateSystemTagMsg'
    def __init__(self):
        #mandatory field
        self.resourceType = NotNoneField()
        #mandatory field
        self.resourceUuid = NotNoneField()
        #mandatory field
        self.tag = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYSYSTEMTAGREPLY_FULL_NAME = 'org.zstack.header.tag.APIQuerySystemTagReply'
class APIQuerySystemTagReply(object):
    FULL_NAME='org.zstack.header.tag.APIQuerySystemTagReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIUPDATESYSTEMTAGMSG_FULL_NAME = 'org.zstack.header.tag.APIUpdateSystemTagMsg'
class APIUpdateSystemTagMsg(object):
    FULL_NAME='org.zstack.header.tag.APIUpdateSystemTagMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.tag = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYSYSTEMTAGMSG_FULL_NAME = 'org.zstack.header.tag.APIQuerySystemTagMsg'
class APIQuerySystemTagMsg(object):
    FULL_NAME='org.zstack.header.tag.APIQuerySystemTagMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIQUERYTAGMSG_FULL_NAME = 'org.zstack.header.tag.APIQueryTagMsg'
class APIQueryTagMsg(object):
    FULL_NAME='org.zstack.header.tag.APIQueryTagMsg'
    def __init__(self):
        self.systemTag = None
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
        self.session = None
        self.timeout = None


APIRECONNECTPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIReconnectPrimaryStorageMsg'
class APIReconnectPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIReconnectPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETPRIMARYSTORAGEALLOCATORSTRATEGIESREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesReply'
class APIGetPrimaryStorageAllocatorStrategiesReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesReply'
    def __init__(self):
        self.primaryStorageAllocatorStrategies = OptionalList()
        self.success = None
        self.error = None


CREATETEMPLATEFROMVOLUMEONPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.CreateTemplateFromVolumeOnPrimaryStorageReply'
class CreateTemplateFromVolumeOnPrimaryStorageReply(object):
    FULL_NAME='org.zstack.header.storage.primary.CreateTemplateFromVolumeOnPrimaryStorageReply'
    def __init__(self):
        self.templateBackupStorageInstallPath = None
        self.format = None
        self.success = None
        self.error = None


APILISTPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIListPrimaryStorageReply'
class APIListPrimaryStorageReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIListPrimaryStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIDELETEPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIDeletePrimaryStorageMsg'
class APIDeletePrimaryStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIDeletePrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APISEARCHPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APISearchPrimaryStorageReply'
class APISearchPrimaryStorageReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APISearchPrimaryStorageReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIGETPRIMARYSTORAGETYPESMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageTypesMsg'
class APIGetPrimaryStorageTypesMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APIGETPRIMARYSTORAGETYPESREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageTypesReply'
class APIGetPrimaryStorageTypesReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageTypesReply'
    def __init__(self):
        self.primaryStorageTypes = OptionalList()
        self.success = None
        self.error = None


APIDETACHPRIMARYSTORAGEFROMCLUSTERMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIDetachPrimaryStorageFromClusterMsg'
class APIDetachPrimaryStorageFromClusterMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIDetachPrimaryStorageFromClusterMsg'
    def __init__(self):
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIATTACHPRIMARYSTORAGETOCLUSTERMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIAttachPrimaryStorageToClusterMsg'
class APIAttachPrimaryStorageToClusterMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIAttachPrimaryStorageToClusterMsg'
    def __init__(self):
        #mandatory field
        self.clusterUuid = NotNoneField()
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIUPDATEPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIUpdatePrimaryStorageMsg'
class APIUpdatePrimaryStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIUpdatePrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APICHANGEPRIMARYSTORAGESTATEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIChangePrimaryStorageStateMsg'
class APIChangePrimaryStorageStateMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIChangePrimaryStorageStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIGETPRIMARYSTORAGEALLOCATORSTRATEGIESMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesMsg'
class APIGetPrimaryStorageAllocatorStrategiesMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APIQUERYPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIQueryPrimaryStorageReply'
class APIQueryPrimaryStorageReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIQueryPrimaryStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIGETPRIMARYSTORAGECAPACITYREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageCapacityReply'
class APIGetPrimaryStorageCapacityReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageCapacityReply'
    def __init__(self):
        self.totalCapacity = None
        self.availableCapacity = None
        self.totalPhysicalCapacity = None
        self.availablePhysicalCapacity = None
        self.success = None
        self.error = None


APIGETPRIMARYSTORAGECAPACITYMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageCapacityMsg'
class APIGetPrimaryStorageCapacityMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageCapacityMsg'
    def __init__(self):
        self.zoneUuids = OptionalList()
        self.clusterUuids = OptionalList()
        self.primaryStorageUuids = OptionalList()
        self.all = None
        self.session = None
        self.timeout = None


APIQUERYPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIQueryPrimaryStorageMsg'
class APIQueryPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIQueryPrimaryStorageMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APISYNCPRIMARYSTORAGECAPACITYMSG_FULL_NAME = 'org.zstack.header.storage.primary.APISyncPrimaryStorageCapacityMsg'
class APISyncPrimaryStorageCapacityMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APISyncPrimaryStorageCapacityMsg'
    def __init__(self):
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageReply'
class APIGetPrimaryStorageReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIREVERTVOLUMEFROMSNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIRevertVolumeFromSnapshotMsg'
class APIRevertVolumeFromSnapshotMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIRevertVolumeFromSnapshotMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYVOLUMESNAPSHOTTREEREPLY_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeReply'
class APIQueryVolumeSnapshotTreeReply(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIUPDATEVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIUpdateVolumeSnapshotMsg'
class APIUpdateVolumeSnapshotMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIUpdateVolumeSnapshotMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIGETVOLUMESNAPSHOTTREEMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeMsg'
class APIGetVolumeSnapshotTreeMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeMsg'
    def __init__(self):
        self.volumeUuid = None
        self.treeUuid = None
        self.session = None
        self.timeout = None


APIQUERYVOLUMESNAPSHOTREPLY_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotReply'
class APIQueryVolumeSnapshotReply(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIDELETEVOLUMESNAPSHOTFROMBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotFromBackupStorageMsg'
class APIDeleteVolumeSnapshotFromBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotFromBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.backupStorageUuids = NotNoneList()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIQUERYVOLUMESNAPSHOTTREEMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeMsg'
class APIQueryVolumeSnapshotTreeMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIGETVOLUMESNAPSHOTTREEREPLY_FULL_NAME = 'org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeReply'
class APIGetVolumeSnapshotTreeReply(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIDELETEVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotMsg'
class APIDeleteVolumeSnapshotMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIBACKUPVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIBackupVolumeSnapshotMsg'
class APIBackupVolumeSnapshotMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIBackupVolumeSnapshotMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.backupStorageUuid = None
        self.session = None
        self.timeout = None


APIQUERYVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotMsg'
class APIQueryVolumeSnapshotMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIQUERYBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIQueryBackupStorageReply'
class APIQueryBackupStorageReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APIQueryBackupStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIGETBACKUPSTORAGETYPESMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageTypesMsg'
class APIGetBackupStorageTypesMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APIDELETEBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIDeleteBackupStorageMsg'
class APIDeleteBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIDeleteBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIATTACHBACKUPSTORAGETOZONEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIAttachBackupStorageToZoneMsg'
class APIAttachBackupStorageToZoneMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIAttachBackupStorageToZoneMsg'
    def __init__(self):
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.backupStorageUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETBACKUPSTORAGECAPACITYREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageCapacityReply'
class APIGetBackupStorageCapacityReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageCapacityReply'
    def __init__(self):
        self.totalCapacity = None
        self.availableCapacity = None
        self.success = None
        self.error = None


APIGETBACKUPSTORAGETYPESREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageTypesReply'
class APIGetBackupStorageTypesReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageTypesReply'
    def __init__(self):
        self.backupStorageTypes = OptionalList()
        self.success = None
        self.error = None


APIGETBACKUPSTORAGECAPACITYMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageCapacityMsg'
class APIGetBackupStorageCapacityMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageCapacityMsg'
    def __init__(self):
        self.zoneUuids = OptionalList()
        self.backupStorageUuids = OptionalList()
        self.all = None
        self.session = None
        self.timeout = None


APIRECONNECTBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIReconnectBackupStorageMsg'
class APIReconnectBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIReconnectBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APICHANGEBACKUPSTORAGESTATEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIChangeBackupStorageStateMsg'
class APIChangeBackupStorageStateMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIChangeBackupStorageStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APISEARCHBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APISearchBackupStorageReply'
class APISearchBackupStorageReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APISearchBackupStorageReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIGETBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageReply'
class APIGetBackupStorageReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APISCANBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIScanBackupStorageMsg'
class APIScanBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIScanBackupStorageMsg'
    def __init__(self):
        self.backupStorageUuid = None
        self.session = None
        self.timeout = None


APIUPDATEBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIUpdateBackupStorageMsg'
class APIUpdateBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIUpdateBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APILISTBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIListBackupStorageReply'
class APIListBackupStorageReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APIListBackupStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIQueryBackupStorageMsg'
class APIQueryBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIQueryBackupStorageMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIDETACHBACKUPSTORAGEFROMZONEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIDetachBackupStorageFromZoneMsg'
class APIDetachBackupStorageFromZoneMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIDetachBackupStorageFromZoneMsg'
    def __init__(self):
        #mandatory field
        self.backupStorageUuid = NotNoneField()
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYZONEREPLY_FULL_NAME = 'org.zstack.header.zone.APIQueryZoneReply'
class APIQueryZoneReply(object):
    FULL_NAME='org.zstack.header.zone.APIQueryZoneReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APISEARCHZONEREPLY_FULL_NAME = 'org.zstack.header.zone.APISearchZoneReply'
class APISearchZoneReply(object):
    FULL_NAME='org.zstack.header.zone.APISearchZoneReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APICREATEZONEMSG_FULL_NAME = 'org.zstack.header.zone.APICreateZoneMsg'
class APICreateZoneMsg(object):
    FULL_NAME='org.zstack.header.zone.APICreateZoneMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #valid values: [zstack]
        self.type = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APICHANGEZONESTATEMSG_FULL_NAME = 'org.zstack.header.zone.APIChangeZoneStateMsg'
class APIChangeZoneStateMsg(object):
    FULL_NAME='org.zstack.header.zone.APIChangeZoneStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIGETZONEREPLY_FULL_NAME = 'org.zstack.header.zone.APIGetZoneReply'
class APIGetZoneReply(object):
    FULL_NAME='org.zstack.header.zone.APIGetZoneReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIQUERYZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIQueryZoneMsg'
class APIQueryZoneMsg(object):
    FULL_NAME='org.zstack.header.zone.APIQueryZoneMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIDELETEZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIDeleteZoneMsg'
class APIDeleteZoneMsg(object):
    FULL_NAME='org.zstack.header.zone.APIDeleteZoneMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIUPDATEZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIUpdateZoneMsg'
class APIUpdateZoneMsg(object):
    FULL_NAME='org.zstack.header.zone.APIUpdateZoneMsg'
    def __init__(self):
        self.name = None
        self.description = None
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APILISTZONESREPLY_FULL_NAME = 'org.zstack.header.zone.APIListZonesReply'
class APIListZonesReply(object):
    FULL_NAME='org.zstack.header.zone.APIListZonesReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIEXPUNGEIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIExpungeImageMsg'
class APIExpungeImageMsg(object):
    FULL_NAME='org.zstack.header.image.APIExpungeImageMsg'
    def __init__(self):
        #mandatory field
        self.imageUuid = NotNoneField()
        self.backupStorageUuids = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIQueryImageReply'
class APIQueryImageReply(object):
    FULL_NAME='org.zstack.header.image.APIQueryImageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APICREATEROOTVOLUMETEMPLATEFROMROOTVOLUMEMSG_FULL_NAME = 'org.zstack.header.image.APICreateRootVolumeTemplateFromRootVolumeMsg'
class APICreateRootVolumeTemplateFromRootVolumeMsg(object):
    FULL_NAME='org.zstack.header.image.APICreateRootVolumeTemplateFromRootVolumeMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.guestOsType = None
        self.backupStorageUuids = OptionalList()
        #mandatory field
        self.rootVolumeUuid = NotNoneField()
        #valid values: [Linux, Windows, Other, Paravirtualization, WindowsVirtio]
        self.platform = None
        self.system = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIADDIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIAddImageMsg'
class APIAddImageMsg(object):
    FULL_NAME='org.zstack.header.image.APIAddImageMsg'
    def __init__(self):
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
        #valid values: [Linux, Windows, Other, Paravirtualization, WindowsVirtio]
        self.platform = None
        #mandatory field
        self.backupStorageUuids = NotNoneList()
        self.type = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIGETIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIGetImageReply'
class APIGetImageReply(object):
    FULL_NAME='org.zstack.header.image.APIGetImageReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APICREATEDATAVOLUMETEMPLATEFROMVOLUMEMSG_FULL_NAME = 'org.zstack.header.image.APICreateDataVolumeTemplateFromVolumeMsg'
class APICreateDataVolumeTemplateFromVolumeMsg(object):
    FULL_NAME='org.zstack.header.image.APICreateDataVolumeTemplateFromVolumeMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.volumeUuid = NotNoneField()
        self.backupStorageUuids = OptionalList()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIRECOVERIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIRecoverImageMsg'
class APIRecoverImageMsg(object):
    FULL_NAME='org.zstack.header.image.APIRecoverImageMsg'
    def __init__(self):
        #mandatory field
        self.imageUuid = NotNoneField()
        self.backupStorageUuids = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIQueryImageMsg'
class APIQueryImageMsg(object):
    FULL_NAME='org.zstack.header.image.APIQueryImageMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APICREATEROOTVOLUMETEMPLATEFROMVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.image.APICreateRootVolumeTemplateFromVolumeSnapshotMsg'
class APICreateRootVolumeTemplateFromVolumeSnapshotMsg(object):
    FULL_NAME='org.zstack.header.image.APICreateRootVolumeTemplateFromVolumeSnapshotMsg'
    def __init__(self):
        #mandatory field
        self.snapshotUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.guestOsType = None
        self.backupStorageUuids = OptionalList()
        #valid values: [Linux, Windows, Other, Paravirtualization, WindowsVirtio]
        self.platform = None
        self.system = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIUPDATEIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIUpdateImageMsg'
class APIUpdateImageMsg(object):
    FULL_NAME='org.zstack.header.image.APIUpdateImageMsg'
    def __init__(self):
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
        #valid values: [Linux, Windows, Other, Paravirtualization, WindowsVirtio]
        self.platform = None
        self.session = None
        self.timeout = None


APICHANGEIMAGESTATEMSG_FULL_NAME = 'org.zstack.header.image.APIChangeImageStateMsg'
class APIChangeImageStateMsg(object):
    FULL_NAME='org.zstack.header.image.APIChangeImageStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APILISTIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIListImageReply'
class APIListImageReply(object):
    FULL_NAME='org.zstack.header.image.APIListImageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APISEARCHIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APISearchImageReply'
class APISearchImageReply(object):
    FULL_NAME='org.zstack.header.image.APISearchImageReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIDELETEIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIDeleteImageMsg'
class APIDeleteImageMsg(object):
    FULL_NAME='org.zstack.header.image.APIDeleteImageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.backupStorageUuids = OptionalList()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIQUERYHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIQueryHostMsg'
class APIQueryHostMsg(object):
    FULL_NAME='org.zstack.header.host.APIQueryHostMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIGETHYPERVISORTYPESREPLY_FULL_NAME = 'org.zstack.header.host.APIGetHypervisorTypesReply'
class APIGetHypervisorTypesReply(object):
    FULL_NAME='org.zstack.header.host.APIGetHypervisorTypesReply'
    def __init__(self):
        self.hypervisorTypes = OptionalList()
        self.success = None
        self.error = None


APIGETHYPERVISORTYPESMSG_FULL_NAME = 'org.zstack.header.host.APIGetHypervisorTypesMsg'
class APIGetHypervisorTypesMsg(object):
    FULL_NAME='org.zstack.header.host.APIGetHypervisorTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APISEARCHHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APISearchHostReply'
class APISearchHostReply(object):
    FULL_NAME='org.zstack.header.host.APISearchHostReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIGETHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APIGetHostReply'
class APIGetHostReply(object):
    FULL_NAME='org.zstack.header.host.APIGetHostReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIDELETEHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIDeleteHostMsg'
class APIDeleteHostMsg(object):
    FULL_NAME='org.zstack.header.host.APIDeleteHostMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIUPDATEHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIUpdateHostMsg'
class APIUpdateHostMsg(object):
    FULL_NAME='org.zstack.header.host.APIUpdateHostMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.managementIp = None
        self.session = None
        self.timeout = None


APILISTHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APIListHostReply'
class APIListHostReply(object):
    FULL_NAME='org.zstack.header.host.APIListHostReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APICHANGEHOSTSTATEMSG_FULL_NAME = 'org.zstack.header.host.APIChangeHostStateMsg'
class APIChangeHostStateMsg(object):
    FULL_NAME='org.zstack.header.host.APIChangeHostStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable, maintain]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIRECONNECTHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIReconnectHostMsg'
class APIReconnectHostMsg(object):
    FULL_NAME='org.zstack.header.host.APIReconnectHostMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APIQueryHostReply'
class APIQueryHostReply(object):
    FULL_NAME='org.zstack.header.host.APIQueryHostReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIREQUESTCONSOLEACCESSMSG_FULL_NAME = 'org.zstack.header.console.APIRequestConsoleAccessMsg'
class APIRequestConsoleAccessMsg(object):
    FULL_NAME='org.zstack.header.console.APIRequestConsoleAccessMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIRECONNECTCONSOLEPROXYAGENTMSG_FULL_NAME = 'org.zstack.header.console.APIReconnectConsoleProxyAgentMsg'
class APIReconnectConsoleProxyAgentMsg(object):
    FULL_NAME='org.zstack.header.console.APIReconnectConsoleProxyAgentMsg'
    def __init__(self):
        self.agentUuids = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYCONSOLEPROXYAGENTREPLY_FULL_NAME = 'org.zstack.header.console.APIQueryConsoleProxyAgentReply'
class APIQueryConsoleProxyAgentReply(object):
    FULL_NAME='org.zstack.header.console.APIQueryConsoleProxyAgentReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYCONSOLEPROXYAGENTMSG_FULL_NAME = 'org.zstack.header.console.APIQueryConsoleProxyAgentMsg'
class APIQueryConsoleProxyAgentMsg(object):
    FULL_NAME='org.zstack.header.console.APIQueryConsoleProxyAgentMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APILISTCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APIListClusterReply'
class APIListClusterReply(object):
    FULL_NAME='org.zstack.header.cluster.APIListClusterReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APIQueryClusterReply'
class APIQueryClusterReply(object):
    FULL_NAME='org.zstack.header.cluster.APIQueryClusterReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APICREATECLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APICreateClusterMsg'
class APICreateClusterMsg(object):
    FULL_NAME='org.zstack.header.cluster.APICreateClusterMsg'
    def __init__(self):
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
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIDELETECLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APIDeleteClusterMsg'
class APIDeleteClusterMsg(object):
    FULL_NAME='org.zstack.header.cluster.APIDeleteClusterMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APISEARCHCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APISearchClusterReply'
class APISearchClusterReply(object):
    FULL_NAME='org.zstack.header.cluster.APISearchClusterReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIGETCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APIGetClusterReply'
class APIGetClusterReply(object):
    FULL_NAME='org.zstack.header.cluster.APIGetClusterReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIUPDATECLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APIUpdateClusterMsg'
class APIUpdateClusterMsg(object):
    FULL_NAME='org.zstack.header.cluster.APIUpdateClusterMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIQUERYCLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APIQueryClusterMsg'
class APIQueryClusterMsg(object):
    FULL_NAME='org.zstack.header.cluster.APIQueryClusterMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APICHANGECLUSTERSTATEMSG_FULL_NAME = 'org.zstack.header.cluster.APIChangeClusterStateMsg'
class APIChangeClusterStateMsg(object):
    FULL_NAME='org.zstack.header.cluster.APIChangeClusterStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIGETHOSTALLOCATORSTRATEGIESMSG_FULL_NAME = 'org.zstack.header.allocator.APIGetHostAllocatorStrategiesMsg'
class APIGetHostAllocatorStrategiesMsg(object):
    FULL_NAME='org.zstack.header.allocator.APIGetHostAllocatorStrategiesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APIGETCPUMEMORYCAPACITYMSG_FULL_NAME = 'org.zstack.header.allocator.APIGetCpuMemoryCapacityMsg'
class APIGetCpuMemoryCapacityMsg(object):
    FULL_NAME='org.zstack.header.allocator.APIGetCpuMemoryCapacityMsg'
    def __init__(self):
        self.zoneUuids = OptionalList()
        self.clusterUuids = OptionalList()
        self.hostUuids = OptionalList()
        self.all = None
        self.session = None
        self.timeout = None


APIGETHOSTALLOCATORSTRATEGIESREPLY_FULL_NAME = 'org.zstack.header.allocator.APIGetHostAllocatorStrategiesReply'
class APIGetHostAllocatorStrategiesReply(object):
    FULL_NAME='org.zstack.header.allocator.APIGetHostAllocatorStrategiesReply'
    def __init__(self):
        self.hostAllocatorStrategies = OptionalList()
        self.success = None
        self.error = None


APIGETCPUMEMORYCAPACITYREPLY_FULL_NAME = 'org.zstack.header.allocator.APIGetCpuMemoryCapacityReply'
class APIGetCpuMemoryCapacityReply(object):
    FULL_NAME='org.zstack.header.allocator.APIGetCpuMemoryCapacityReply'
    def __init__(self):
        self.totalCpu = None
        self.availableCpu = None
        self.totalMemory = None
        self.availableMemory = None
        self.success = None
        self.error = None


APIGETVERSIONMSG_FULL_NAME = 'org.zstack.header.managementnode.APIGetVersionMsg'
class APIGetVersionMsg(object):
    FULL_NAME='org.zstack.header.managementnode.APIGetVersionMsg'
    def __init__(self):
        self.session = None
        self.timeout = None


APIGETVERSIONREPLY_FULL_NAME = 'org.zstack.header.managementnode.APIGetVersionReply'
class APIGetVersionReply(object):
    FULL_NAME='org.zstack.header.managementnode.APIGetVersionReply'
    def __init__(self):
        self.version = None
        self.success = None
        self.error = None


APILISTMANAGEMENTNODEREPLY_FULL_NAME = 'org.zstack.header.managementnode.APIListManagementNodeReply'
class APIListManagementNodeReply(object):
    FULL_NAME='org.zstack.header.managementnode.APIListManagementNodeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYMANAGEMENTNODEMSG_FULL_NAME = 'org.zstack.header.managementnode.APIQueryManagementNodeMsg'
class APIQueryManagementNodeMsg(object):
    FULL_NAME='org.zstack.header.managementnode.APIQueryManagementNodeMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIQUERYMANAGEMENTNODEREPLY_FULL_NAME = 'org.zstack.header.managementnode.APIQueryManagementNodeReply'
class APIQueryManagementNodeReply(object):
    FULL_NAME='org.zstack.header.managementnode.APIQueryManagementNodeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIISREADYTOGOMSG_FULL_NAME = 'org.zstack.header.apimediator.APIIsReadyToGoMsg'
class APIIsReadyToGoMsg(object):
    FULL_NAME='org.zstack.header.apimediator.APIIsReadyToGoMsg'
    def __init__(self):
        self.managementNodeId = None
        self.session = None
        self.timeout = None


APIISREADYTOGOREPLY_FULL_NAME = 'org.zstack.header.apimediator.APIIsReadyToGoReply'
class APIIsReadyToGoReply(object):
    FULL_NAME='org.zstack.header.apimediator.APIIsReadyToGoReply'
    def __init__(self):
        self.managementNodeId = None
        self.success = None
        self.error = None


APIQUERYISCSIFILESYSTEMBACKENDPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.primary.iscsi.APIQueryIscsiFileSystemBackendPrimaryStorageReply'
class APIQueryIscsiFileSystemBackendPrimaryStorageReply(object):
    FULL_NAME='org.zstack.storage.primary.iscsi.APIQueryIscsiFileSystemBackendPrimaryStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYISCSIFILESYSTEMBACKENDPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.iscsi.APIQueryIscsiFileSystemBackendPrimaryStorageMsg'
class APIQueryIscsiFileSystemBackendPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.primary.iscsi.APIQueryIscsiFileSystemBackendPrimaryStorageMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIADDISCSIFILESYSTEMBACKENDPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.iscsi.APIAddIscsiFileSystemBackendPrimaryStorageMsg'
class APIAddIscsiFileSystemBackendPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.primary.iscsi.APIAddIscsiFileSystemBackendPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.hostname = NotNoneField()
        #mandatory field
        self.sshUsername = NotNoneField()
        #mandatory field
        self.sshPassword = NotNoneField()
        self.filesystemType = None
        self.chapUsername = None
        self.chapPassword = None
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIUPDATEISCSIFILESYSTEMBACKENDPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.iscsi.APIUpdateIscsiFileSystemBackendPrimaryStorageMsg'
class APIUpdateIscsiFileSystemBackendPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.primary.iscsi.APIUpdateIscsiFileSystemBackendPrimaryStorageMsg'
    def __init__(self):
        self.chapUsername = None
        self.chapPassword = None
        self.sshUsername = None
        self.sshPassword = None
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIKVMRUNSHELLMSG_FULL_NAME = 'org.zstack.kvm.APIKvmRunShellMsg'
class APIKvmRunShellMsg(object):
    FULL_NAME='org.zstack.kvm.APIKvmRunShellMsg'
    def __init__(self):
        #mandatory field
        self.hostUuids = NotNoneList()
        #mandatory field
        self.script = NotNoneField()
        self.session = None
        self.timeout = None


APIUPDATEKVMHOSTMSG_FULL_NAME = 'org.zstack.kvm.APIUpdateKVMHostMsg'
class APIUpdateKVMHostMsg(object):
    FULL_NAME='org.zstack.kvm.APIUpdateKVMHostMsg'
    def __init__(self):
        self.username = None
        self.password = None
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.managementIp = None
        self.session = None
        self.timeout = None


APIADDKVMHOSTMSG_FULL_NAME = 'org.zstack.kvm.APIAddKVMHostMsg'
class APIAddKVMHostMsg(object):
    FULL_NAME='org.zstack.kvm.APIAddKVMHostMsg'
    def __init__(self):
        #mandatory field
        self.username = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.managementIp = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIREFRESHLOADBALANCERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIRefreshLoadBalancerMsg'
class APIRefreshLoadBalancerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIRefreshLoadBalancerMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYLOADBALANCERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIQueryLoadBalancerMsg'
class APIQueryLoadBalancerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIQueryLoadBalancerMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APICREATELOADBALANCERLISTENERMSG_FULL_NAME = 'org.zstack.network.service.lb.APICreateLoadBalancerListenerMsg'
class APICreateLoadBalancerListenerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APICreateLoadBalancerListenerMsg'
    def __init__(self):
        #mandatory field
        self.loadBalancerUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.instancePort = None
        #mandatory field
        self.loadBalancerPort = NotNoneField()
        #valid values: [tcp, http]
        self.protocol = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIREMOVEVMNICFROMLOADBALANCERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIRemoveVmNicFromLoadBalancerMsg'
class APIRemoveVmNicFromLoadBalancerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIRemoveVmNicFromLoadBalancerMsg'
    def __init__(self):
        #mandatory field
        self.vmNicUuids = NotNoneList()
        #mandatory field
        self.listenerUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYLOADBALANCERREPLY_FULL_NAME = 'org.zstack.network.service.lb.APIQueryLoadBalancerReply'
class APIQueryLoadBalancerReply(object):
    FULL_NAME='org.zstack.network.service.lb.APIQueryLoadBalancerReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIDELETELOADBALANCERLISTENERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIDeleteLoadBalancerListenerMsg'
class APIDeleteLoadBalancerListenerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIDeleteLoadBalancerListenerMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIADDVMNICTOLOADBALANCERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIAddVmNicToLoadBalancerMsg'
class APIAddVmNicToLoadBalancerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIAddVmNicToLoadBalancerMsg'
    def __init__(self):
        #mandatory field
        self.vmNicUuids = NotNoneList()
        #mandatory field
        self.listenerUuid = NotNoneField()
        self.session = None
        self.timeout = None


APICREATELOADBALANCERMSG_FULL_NAME = 'org.zstack.network.service.lb.APICreateLoadBalancerMsg'
class APICreateLoadBalancerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APICreateLoadBalancerMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.vipUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIDELETELOADBALANCERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIDeleteLoadBalancerMsg'
class APIDeleteLoadBalancerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIDeleteLoadBalancerMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIQUERYLOADBALANCERLISTENERREPLY_FULL_NAME = 'org.zstack.network.service.lb.APIQueryLoadBalancerListenerReply'
class APIQueryLoadBalancerListenerReply(object):
    FULL_NAME='org.zstack.network.service.lb.APIQueryLoadBalancerListenerReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYLOADBALANCERLISTENERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIQueryLoadBalancerListenerMsg'
class APIQueryLoadBalancerListenerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIQueryLoadBalancerListenerMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIQUERYLOCALSTORAGERESOURCEREFMSG_FULL_NAME = 'org.zstack.storage.primary.local.APIQueryLocalStorageResourceRefMsg'
class APIQueryLocalStorageResourceRefMsg(object):
    FULL_NAME='org.zstack.storage.primary.local.APIQueryLocalStorageResourceRefMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIGETLOCALSTORAGEHOSTDISKCAPACITYREPLY_FULL_NAME = 'org.zstack.storage.primary.local.APIGetLocalStorageHostDiskCapacityReply'
class APIGetLocalStorageHostDiskCapacityReply(object):
    FULL_NAME='org.zstack.storage.primary.local.APIGetLocalStorageHostDiskCapacityReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APILOCALSTORAGEGETVOLUMEMIGRATABLEHOSTSMSG_FULL_NAME = 'org.zstack.storage.primary.local.APILocalStorageGetVolumeMigratableHostsMsg'
class APILocalStorageGetVolumeMigratableHostsMsg(object):
    FULL_NAME='org.zstack.storage.primary.local.APILocalStorageGetVolumeMigratableHostsMsg'
    def __init__(self):
        #mandatory field
        self.volumeUuid = NotNoneField()
        self.session = None
        self.timeout = None


APILOCALSTORAGEMIGRATEVOLUMEMSG_FULL_NAME = 'org.zstack.storage.primary.local.APILocalStorageMigrateVolumeMsg'
class APILocalStorageMigrateVolumeMsg(object):
    FULL_NAME='org.zstack.storage.primary.local.APILocalStorageMigrateVolumeMsg'
    def __init__(self):
        #mandatory field
        self.volumeUuid = NotNoneField()
        #mandatory field
        self.destHostUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIGETLOCALSTORAGEHOSTDISKCAPACITYMSG_FULL_NAME = 'org.zstack.storage.primary.local.APIGetLocalStorageHostDiskCapacityMsg'
class APIGetLocalStorageHostDiskCapacityMsg(object):
    FULL_NAME='org.zstack.storage.primary.local.APIGetLocalStorageHostDiskCapacityMsg'
    def __init__(self):
        self.hostUuid = None
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIADDLOCALPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.local.APIAddLocalPrimaryStorageMsg'
class APIAddLocalPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.primary.local.APIAddLocalPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYLOCALSTORAGERESOURCEREFREPLY_FULL_NAME = 'org.zstack.storage.primary.local.APIQueryLocalStorageResourceRefReply'
class APIQueryLocalStorageResourceRefReply(object):
    FULL_NAME='org.zstack.storage.primary.local.APIQueryLocalStorageResourceRefReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APILOCALSTORAGEGETVOLUMEMIGRATABLEREPLY_FULL_NAME = 'org.zstack.storage.primary.local.APILocalStorageGetVolumeMigratableReply'
class APILocalStorageGetVolumeMigratableReply(object):
    FULL_NAME='org.zstack.storage.primary.local.APILocalStorageGetVolumeMigratableReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIADDNFSPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.nfs.APIAddNfsPrimaryStorageMsg'
class APIAddNfsPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.primary.nfs.APIAddNfsPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIUPDATEPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIUpdatePortForwardingRuleMsg'
class APIUpdatePortForwardingRuleMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIUpdatePortForwardingRuleMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIGETPORTFORWARDINGATTACHABLEVMNICSMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsMsg'
class APIGetPortForwardingAttachableVmNicsMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsMsg'
    def __init__(self):
        #mandatory field
        self.ruleUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIDETACHPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIDetachPortForwardingRuleMsg'
class APIDetachPortForwardingRuleMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIDetachPortForwardingRuleMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIATTACHPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIAttachPortForwardingRuleMsg'
class APIAttachPortForwardingRuleMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIAttachPortForwardingRuleMsg'
    def __init__(self):
        #mandatory field
        self.ruleUuid = NotNoneField()
        #mandatory field
        self.vmNicUuid = NotNoneField()
        self.session = None
        self.timeout = None


APICREATEPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APICreatePortForwardingRuleMsg'
class APICreatePortForwardingRuleMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APICreatePortForwardingRuleMsg'
    def __init__(self):
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
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIDELETEPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIDeletePortForwardingRuleMsg'
class APIDeletePortForwardingRuleMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIDeletePortForwardingRuleMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIGETPORTFORWARDINGATTACHABLEVMNICSREPLY_FULL_NAME = 'org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsReply'
class APIGetPortForwardingAttachableVmNicsReply(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APICHANGEPORTFORWARDINGRULESTATEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIChangePortForwardingRuleStateMsg'
class APIChangePortForwardingRuleStateMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIChangePortForwardingRuleStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYPORTFORWARDINGRULEREPLY_FULL_NAME = 'org.zstack.network.service.portforwarding.APIQueryPortForwardingRuleReply'
class APIQueryPortForwardingRuleReply(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIQueryPortForwardingRuleReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APILISTPORTFORWARDINGRULEREPLY_FULL_NAME = 'org.zstack.network.service.portforwarding.APIListPortForwardingRuleReply'
class APIListPortForwardingRuleReply(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIListPortForwardingRuleReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIQueryPortForwardingRuleMsg'
class APIQueryPortForwardingRuleMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIQueryPortForwardingRuleMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIQUERYSECURITYGROUPRULEREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupRuleReply'
class APIQuerySecurityGroupRuleReply(object):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupRuleReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APICHANGESECURITYGROUPSTATEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIChangeSecurityGroupStateMsg'
class APIChangeSecurityGroupStateMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIChangeSecurityGroupStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIADDSECURITYGROUPRULEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIAddSecurityGroupRuleMsg'
class APIAddSecurityGroupRuleMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIAddSecurityGroupRuleMsg'
    def __init__(self):
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
        self.rules = NotNoneList()
        self.session = None
        self.timeout = None


APIDETACHSECURITYGROUPFROML3NETWORKMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDetachSecurityGroupFromL3NetworkMsg'
class APIDetachSecurityGroupFromL3NetworkMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIDetachSecurityGroupFromL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIDELETEVMNICFROMSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteVmNicFromSecurityGroupMsg'
class APIDeleteVmNicFromSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteVmNicFromSecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
        self.vmNicUuids = NotNoneList()
        self.session = None
        self.timeout = None


APIDELETESECURITYGROUPRULEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteSecurityGroupRuleMsg'
class APIDeleteSecurityGroupRuleMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteSecurityGroupRuleMsg'
    def __init__(self):
        #mandatory field
        self.ruleUuids = NotNoneList()
        self.session = None
        self.timeout = None


APIDELETESECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteSecurityGroupMsg'
class APIDeleteSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteSecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APIATTACHSECURITYGROUPTOL3NETWORKMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIAttachSecurityGroupToL3NetworkMsg'
class APIAttachSecurityGroupToL3NetworkMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIAttachSecurityGroupToL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIADDVMNICTOSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIAddVmNicToSecurityGroupMsg'
class APIAddVmNicToSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIAddVmNicToSecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        #mandatory field
        self.vmNicUuids = NotNoneList()
        self.session = None
        self.timeout = None


APIQUERYVMNICINSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupReply'
class APIQueryVmNicInSecurityGroupReply(object):
    FULL_NAME='org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIUPDATESECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIUpdateSecurityGroupMsg'
class APIUpdateSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIUpdateSecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIGETCANDIDATEVMNICFORSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupMsg'
class APIGetCandidateVmNicForSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYVMNICINSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupMsg'
class APIQueryVmNicInSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APICREATESECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APICreateSecurityGroupMsg'
class APICreateSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APICreateSecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIGETCANDIDATEVMNICFORSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupReply'
class APIGetCandidateVmNicForSecurityGroupReply(object):
    FULL_NAME='org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupReply'
class APIQuerySecurityGroupReply(object):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APILISTVMNICINSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIListVmNicInSecurityGroupReply'
class APIListVmNicInSecurityGroupReply(object):
    FULL_NAME='org.zstack.network.securitygroup.APIListVmNicInSecurityGroupReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APILISTSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIListSecurityGroupReply'
class APIListSecurityGroupReply(object):
    FULL_NAME='org.zstack.network.securitygroup.APIListSecurityGroupReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYSECURITYGROUPRULEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupRuleMsg'
class APIQuerySecurityGroupRuleMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupRuleMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIQUERYSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupMsg'
class APIQuerySecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIGETSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APIGetSftpBackupStorageReply'
class APIGetSftpBackupStorageReply(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APIGetSftpBackupStorageReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIRECONNECTSFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIReconnectSftpBackupStorageMsg'
class APIReconnectSftpBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APIReconnectSftpBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None


APIQUERYSFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageMsg'
class APIQuerySftpBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIUPDATESFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIUpdateSftpBackupStorageMsg'
class APIUpdateSftpBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APIUpdateSftpBackupStorageMsg'
    def __init__(self):
        self.username = None
        self.password = None
        self.hostname = None
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIADDSFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIAddSftpBackupStorageMsg'
class APIAddSftpBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APIAddSftpBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.hostname = NotNoneField()
        #mandatory field
        self.username = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageReply'
class APIQuerySftpBackupStorageReply(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APISEARCHSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APISearchSftpBackupStorageReply'
class APISearchSftpBackupStorageReply(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APISearchSftpBackupStorageReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIADDSHAREDMOUNTPOINTPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.primary.smp.APIAddSharedMountPointPrimaryStorageMsg'
class APIAddSharedMountPointPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.primary.smp.APIAddSharedMountPointPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIADDSIMULATORBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.simulator.storage.backup.APIAddSimulatorBackupStorageMsg'
class APIAddSimulatorBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.simulator.storage.backup.APIAddSimulatorBackupStorageMsg'
    def __init__(self):
        self.totalCapacity = None
        self.availableCapacity = None
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIADDSIMULATORPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.simulator.storage.primary.APIAddSimulatorPrimaryStorageMsg'
class APIAddSimulatorPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.header.simulator.storage.primary.APIAddSimulatorPrimaryStorageMsg'
    def __init__(self):
        self.totalCapacity = None
        self.availableCapacity = None
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIADDSIMULATORHOSTMSG_FULL_NAME = 'org.zstack.header.simulator.APIAddSimulatorHostMsg'
class APIAddSimulatorHostMsg(object):
    FULL_NAME='org.zstack.header.simulator.APIAddSimulatorHostMsg'
    def __init__(self):
        #mandatory field
        self.memoryCapacity = NotNoneField()
        #mandatory field
        self.cpuCapacity = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.managementIp = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYVIPREPLY_FULL_NAME = 'org.zstack.network.service.vip.APIQueryVipReply'
class APIQueryVipReply(object):
    FULL_NAME='org.zstack.network.service.vip.APIQueryVipReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIUPDATEVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APIUpdateVipMsg'
class APIUpdateVipMsg(object):
    FULL_NAME='org.zstack.network.service.vip.APIUpdateVipMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APICHANGEVIPSTATEMSG_FULL_NAME = 'org.zstack.network.service.vip.APIChangeVipStateMsg'
class APIChangeVipStateMsg(object):
    FULL_NAME='org.zstack.network.service.vip.APIChangeVipStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None


APIDELETEVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APIDeleteVipMsg'
class APIDeleteVipMsg(object):
    FULL_NAME='org.zstack.network.service.vip.APIDeleteVipMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None


APICREATEVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APICreateVipMsg'
class APICreateVipMsg(object):
    FULL_NAME='org.zstack.network.service.vip.APICreateVipMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        self.allocatorStrategy = None
        self.requiredIp = None
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APIQueryVipMsg'
class APIQueryVipMsg(object):
    FULL_NAME='org.zstack.network.service.vip.APIQueryVipMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APISEARCHVIRTUALROUTERVMREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APISearchVirtualRouterVmReply'
class APISearchVirtualRouterVmReply(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APISearchVirtualRouterVmReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIUPDATEVIRTUALROUTEROFFERINGMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIUpdateVirtualRouterOfferingMsg'
class APIUpdateVirtualRouterOfferingMsg(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIUpdateVirtualRouterOfferingMsg'
    def __init__(self):
        self.isDefault = None
        self.imageUuid = None
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None


APIRECONNECTVIRTUALROUTERMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIReconnectVirtualRouterMsg'
class APIReconnectVirtualRouterMsg(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIReconnectVirtualRouterMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None


APICREATEVIRTUALROUTEROFFERINGMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APICreateVirtualRouterOfferingMsg'
class APICreateVirtualRouterOfferingMsg(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APICreateVirtualRouterOfferingMsg'
    def __init__(self):
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.managementNetworkUuid = NotNoneField()
        #mandatory field
        self.imageUuid = NotNoneField()
        self.publicNetworkUuid = None
        self.isDefault = None
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
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYVIRTUALROUTEROFFERINGMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIQueryVirtualRouterOfferingMsg'
class APIQueryVirtualRouterOfferingMsg(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIQueryVirtualRouterOfferingMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APIQUERYVIRTUALROUTEROFFERINGREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIQueryVirtualRouterOfferingReply'
class APIQueryVirtualRouterOfferingReply(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIQueryVirtualRouterOfferingReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYVIRTUALROUTERVMMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIQueryVirtualRouterVmMsg'
class APIQueryVirtualRouterVmMsg(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIQueryVirtualRouterVmMsg'
    def __init__(self):
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
        self.session = None
        self.timeout = None


APISEARCHVIRTUALROUTEROFFINGREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APISearchVirtualRouterOffingReply'
class APISearchVirtualRouterOffingReply(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APISearchVirtualRouterOffingReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APICREATEVIRTUALROUTERVMMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APICreateVirtualRouterVmMsg'
class APICreateVirtualRouterVmMsg(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APICreateVirtualRouterVmMsg'
    def __init__(self):
        #mandatory field
        self.managementNetworkUuid = NotNoneField()
        #mandatory field
        self.publicNetworkUuid = NotNoneField()
        #mandatory field
        self.networkServicesProvided = NotNoneList()
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
        self.resourceUuid = None
        self.userTags = OptionalList()
        self.systemTags = OptionalList()
        self.session = None
        self.timeout = None


APIQUERYVIRTUALROUTERVMREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIQueryVirtualRouterVmReply'
class APIQueryVirtualRouterVmReply(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIQueryVirtualRouterVmReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIGETVIRTUALROUTEROFFERINGREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIGetVirtualRouterOfferingReply'
class APIGetVirtualRouterOfferingReply(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIGetVirtualRouterOfferingReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


api_names = [
    'APIQueryApplianceVmReply',
    'APIQueryApplianceVmMsg',
    'APIListApplianceVmReply',
    'APIAddMonToCephPrimaryStorageMsg',
    'APIAddCephPrimaryStorageMsg',
    'APIRemoveMonFromCephPrimaryStorageMsg',
    'APIQueryCephPrimaryStorageMsg',
    'APIAddMonToCephBackupStorageMsg',
    'APIAddCephBackupStorageMsg',
    'APIRemoveMonFromCephBackupStorageMsg',
    'APIQueryCephBackupStorageMsg',
    'APIGetGlobalConfigMsg',
    'APIQueryGlobalConfigReply',
    'APIGetGlobalConfigReply',
    'APIQueryGlobalConfigMsg',
    'APIListGlobalConfigReply',
    'APIUpdateGlobalConfigMsg',
    'APIGetEipAttachableVmNicsMsg',
    'APIGetEipAttachableVmNicsReply',
    'APIQueryEipMsg',
    'APIUpdateEipMsg',
    'APIChangeEipStateMsg',
    'APIDetachEipMsg',
    'APIAttachEipMsg',
    'APIDeleteEipMsg',
    'APICreateEipMsg',
    'APIQueryEipReply',
    'APIAddFusionstorBackupStorageMsg',
    'APIRemoveMonFromFusionstorBackupStorageMsg',
    'APIAddMonToFusionstorBackupStorageMsg',
    'APIQueryFusionstorBackupStorageMsg',
    'APIAddMonToFusionstorPrimaryStorageMsg',
    'APIRemoveMonFromFusionstorPrimaryStorageMsg',
    'APIQueryFusionstorPrimaryStorageMsg',
    'APIAddFusionstorPrimaryStorageMsg',
    'APIQueryNetworkServiceL3NetworkRefReply',
    'APIGetNetworkServiceProviderReply',
    'APIAttachNetworkServiceProviderToL2NetworkMsg',
    'APIListNetworkServiceProviderReply',
    'APIQueryNetworkServiceL3NetworkRefMsg',
    'APIQueryNetworkServiceProviderMsg',
    'APIDetachNetworkServiceProviderFromL2NetworkMsg',
    'APIDetachNetworkServiceFromL3NetworkMsg',
    'APIQueryNetworkServiceProviderReply',
    'APIAddNetworkServiceProviderMsg',
    'APIGetNetworkServiceTypesReply',
    'APIAttachNetworkServiceToL3NetworkMsg',
    'APISearchNetworkServiceProviderReply',
    'APIGetNetworkServiceTypesMsg',
    'APIDeleteL2NetworkMsg',
    'APIListL2VlanNetworkReply',
    'APIAttachL2NetworkToClusterMsg',
    'APIQueryL2NetworkReply',
    'APIListL2NetworkReply',
    'APICreateL2NoVlanNetworkMsg',
    'APIGetL2NetworkReply',
    'APIQueryL2VlanNetworkReply',
    'APIQueryL2VlanNetworkMsg',
    'APISearchL2NetworkReply',
    'APIDetachL2NetworkFromClusterMsg',
    'APISearchL2VlanNetworkReply',
    'APIGetL2NetworkTypesMsg',
    'APICreateL2VlanNetworkMsg',
    'APIGetL2VlanNetworkReply',
    'APIUpdateL2NetworkMsg',
    'APIGetL2NetworkTypesReply',
    'APIQueryL2NetworkMsg',
    'APIUpdateL3NetworkMsg',
    'APIAddIpRangeMsg',
    'APIAddIpRangeByNetworkCidrMsg',
    'APIListL3NetworkReply',
    'APIQueryL3NetworkReply',
    'APIQueryL3NetworkMsg',
    'APIGetIpAddressCapacityMsg',
    'APIListIpRangeReply',
    'APIAddDnsToL3NetworkMsg',
    'APICreateL3NetworkMsg',
    'APICheckIpAvailabilityReply',
    'APISearchL3NetworkReply',
    'APIGetL3NetworkTypesMsg',
    'APIRemoveDnsFromL3NetworkMsg',
    'APIGetIpAddressCapacityReply',
    'APIQueryIpRangeReply',
    'APIGetFreeIpMsg',
    'APIChangeL3NetworkStateMsg',
    'APIDeleteIpRangeMsg',
    'APIGetL3NetworkTypesReply',
    'APIGetL3NetworkReply',
    'APIDeleteL3NetworkMsg',
    'APIQueryIpRangeMsg',
    'APIGetFreeIpReply',
    'APICheckIpAvailabilityMsg',
    'APIUpdateIpRangeMsg',
    'APIQueryReply',
    'APIGenerateQueryableFieldsMsg',
    'APIGenerateInventoryQueryDetailsMsg',
    'APIReply',
    'APICreateMessage',
    'APISearchReply',
    'APICreateSearchIndexMsg',
    'APISearchGenerateSqlTriggerMsg',
    'APIDeleteSearchIndexMsg',
    'APIAttachPolicyToUserMsg',
    'APIUpdateUserMsg',
    'APIGetAccountQuotaUsageMsg',
    'APIValidateSessionReply',
    'APILogInByAccountMsg',
    'APISessionMessage',
    'APIValidateSessionMsg',
    'APIDeleteUserGroupMsg',
    'APIQueryAccountReply',
    'APIGetPolicyReply',
    'APIDeleteUserMsg',
    'APIAttachPoliciesToUserMsg',
    'APILogInReply',
    'APILogInByUserMsg',
    'APIGetUserReply',
    'APICreateUserGroupMsg',
    'APIListPolicyReply',
    'APIListUserReply',
    'APIGetResourceAccountReply',
    'APIUpdateUserGroupMsg',
    'APICheckApiPermissionReply',
    'APIAddUserToGroupMsg',
    'APIUpdateQuotaMsg',
    'APILogOutMsg',
    'APIQuerySharedResourceMsg',
    'APICreateUserMsg',
    'APIDetachPoliciesFromUserMsg',
    'APIGetUserGroupReply',
    'APIQueryPolicyReply',
    'APIDetachPolicyFromUserMsg',
    'APIQueryQuotaReply',
    'APIShareResourceMsg',
    'APIQuerySharedResourceReply',
    'APIDeletePolicyMsg',
    'APIQueryUserGroupMsg',
    'APIGetAccountReply',
    'APIQueryQuotaMsg',
    'APISearchUserReply',
    'APIQueryAccountMsg',
    'APIRemoveUserFromGroupMsg',
    'APIQueryAccountResourceRefReply',
    'APIQueryAccountResourceRefMsg',
    'APIQueryUserGroupReply',
    'APISearchAccountReply',
    'APICheckApiPermissionMsg',
    'APISearchPolicyReply',
    'APIQueryUserMsg',
    'APICreatePolicyMsg',
    'APIDetachPolicyFromUserGroupMsg',
    'APICreateAccountMsg',
    'APILogOutReply',
    'APIQueryUserReply',
    'APIAttachPolicyToUserGroupMsg',
    'APIGetResourceAccountMsg',
    'APIRevokeResourceSharingMsg',
    'APIChangeResourceOwnerMsg',
    'APIUpdateAccountMsg',
    'APISearchUserGroupReply',
    'APIGetAccountQuotaUsageReply',
    'APIDeleteAccountMsg',
    'APIQueryPolicyMsg',
    'APIListAccountReply',
    'APIGetVmConsoleAddressMsg',
    'APIChangeInstanceOfferingMsg',
    'APIGetVmHostnameReply',
    'APICreateVmInstanceMsg',
    'APIGetVmConsoleAddressReply',
    'APIListVmInstanceReply',
    'APIStartVmInstanceMsg',
    'APIGetVmBootOrderReply',
    'APIQueryVmNicMsg',
    'APIQueryVmNicReply',
    'APIUpdateVmInstanceMsg',
    'APIAttachIsoToVmInstanceMsg',
    'APIDeleteVmHostnameMsg',
    'APIGetVmHostnameMsg',
    'APIGetVmMigrationCandidateHostsMsg',
    'APIQueryVmInstanceReply',
    'APIListVmNicReply',
    'APIGetVmAttachableL3NetworkReply',
    'APIDetachIsoFromVmInstanceMsg',
    'APIGetVmAttachableL3NetworkMsg',
    'APIRebootVmInstanceMsg',
    'APIQueryVmInstanceMsg',
    'APISetVmStaticIpMsg',
    'APIGetVmAttachableDataVolumeReply',
    'APIAttachL3NetworkToVmMsg',
    'APIDestroyVmInstanceMsg',
    'APIGetVmInstanceReply',
    'APIMigrateVmMsg',
    'APIDeleteVmStaticIpMsg',
    'APISetVmBootOrderMsg',
    'APIStopVmInstanceMsg',
    'APIExpungeVmInstanceMsg',
    'APIGetVmBootOrderMsg',
    'APISearchVmInstanceReply',
    'APIRecoverVmInstanceMsg',
    'APIGetVmMigrationCandidateHostsReply',
    'APIGetVmAttachableDataVolumeMsg',
    'APISetVmHostnameMsg',
    'APIDetachL3NetworkFromVmMsg',
    'APIGenerateSqlIndexMsg',
    'APIGenerateGroovyClassMsg',
    'APIQueryInstanceOfferingMsg',
    'APIGenerateSqlVOViewMsg',
    'APIGetGlobalPropertyMsg',
    'APISearchInstanceOfferingReply',
    'APIDeleteInstanceOfferingMsg',
    'APIQueryDiskOfferingMsg',
    'APIGenerateSqlForeignKeyMsg',
    'APIGenerateApiJsonTemplateMsg',
    'APIChangeDiskOfferingStateMsg',
    'APIGetDiskOfferingReply',
    'APIQueryDiskOfferingReply',
    'APIChangeInstanceOfferingStateMsg',
    'APIDeleteDiskOfferingMsg',
    'APIGetInstanceOfferingReply',
    'APIGenerateApiTypeScriptDefinitionMsg',
    'APIGetGlobalPropertyReply',
    'APIGenerateTestLinkDocumentMsg',
    'APISearchDnsReply',
    'APICreateDiskOfferingMsg',
    'APIListInstanceOfferingReply',
    'APICreateInstanceOfferingMsg',
    'APIUpdateDiskOfferingMsg',
    'APIListDiskOfferingReply',
    'APIUpdateInstanceOfferingMsg',
    'APISearchDiskOfferingReply',
    'APIQueryInstanceOfferingReply',
    'APIQueryVolumeReply',
    'APIGetDataVolumeAttachableVmMsg',
    'APIBackupDataVolumeMsg',
    'APICreateDataVolumeFromVolumeSnapshotMsg',
    'APIAttachDataVolumeToVmMsg',
    'APISearchVolumeReply',
    'APICreateDataVolumeFromVolumeTemplateMsg',
    'APIQueryVolumeMsg',
    'APIChangeVolumeStateMsg',
    'APIListVolumeReply',
    'APIDetachDataVolumeFromVmMsg',
    'APICreateDataVolumeMsg',
    'APIGetDataVolumeAttachableVmReply',
    'APIGetVolumeReply',
    'APIDeleteDataVolumeMsg',
    'APICreateVolumeSnapshotMsg',
    'APIGetVolumeFormatMsg',
    'APIGetVolumeFormatReply',
    'APIUpdateVolumeMsg',
    'APIExpungeDataVolumeMsg',
    'APIRecoverDataVolumeMsg',
    'APIQueryUserTagMsg',
    'APIDeleteTagMsg',
    'APIQueryTagReply',
    'APICreateUserTagMsg',
    'APIQueryUserTagReply',
    'APICreateSystemTagMsg',
    'APIQuerySystemTagReply',
    'APIUpdateSystemTagMsg',
    'APIQuerySystemTagMsg',
    'APIQueryTagMsg',
    'APIReconnectPrimaryStorageMsg',
    'APIGetPrimaryStorageAllocatorStrategiesReply',
    'CreateTemplateFromVolumeOnPrimaryStorageReply',
    'APIListPrimaryStorageReply',
    'APIDeletePrimaryStorageMsg',
    'APISearchPrimaryStorageReply',
    'APIGetPrimaryStorageTypesMsg',
    'APIGetPrimaryStorageTypesReply',
    'APIDetachPrimaryStorageFromClusterMsg',
    'APIAttachPrimaryStorageToClusterMsg',
    'APIUpdatePrimaryStorageMsg',
    'APIChangePrimaryStorageStateMsg',
    'APIGetPrimaryStorageAllocatorStrategiesMsg',
    'APIQueryPrimaryStorageReply',
    'APIGetPrimaryStorageCapacityReply',
    'APIGetPrimaryStorageCapacityMsg',
    'APIQueryPrimaryStorageMsg',
    'APISyncPrimaryStorageCapacityMsg',
    'APIGetPrimaryStorageReply',
    'APIRevertVolumeFromSnapshotMsg',
    'APIQueryVolumeSnapshotTreeReply',
    'APIUpdateVolumeSnapshotMsg',
    'APIGetVolumeSnapshotTreeMsg',
    'APIQueryVolumeSnapshotReply',
    'APIDeleteVolumeSnapshotFromBackupStorageMsg',
    'APIQueryVolumeSnapshotTreeMsg',
    'APIGetVolumeSnapshotTreeReply',
    'APIDeleteVolumeSnapshotMsg',
    'APIBackupVolumeSnapshotMsg',
    'APIQueryVolumeSnapshotMsg',
    'APIQueryBackupStorageReply',
    'APIGetBackupStorageTypesMsg',
    'APIDeleteBackupStorageMsg',
    'APIAttachBackupStorageToZoneMsg',
    'APIGetBackupStorageCapacityReply',
    'APIGetBackupStorageTypesReply',
    'APIGetBackupStorageCapacityMsg',
    'APIReconnectBackupStorageMsg',
    'APIChangeBackupStorageStateMsg',
    'APISearchBackupStorageReply',
    'APIGetBackupStorageReply',
    'APIScanBackupStorageMsg',
    'APIUpdateBackupStorageMsg',
    'APIListBackupStorageReply',
    'APIQueryBackupStorageMsg',
    'APIDetachBackupStorageFromZoneMsg',
    'APIQueryZoneReply',
    'APISearchZoneReply',
    'APICreateZoneMsg',
    'APIChangeZoneStateMsg',
    'APIGetZoneReply',
    'APIQueryZoneMsg',
    'APIDeleteZoneMsg',
    'APIUpdateZoneMsg',
    'APIListZonesReply',
    'APIExpungeImageMsg',
    'APIQueryImageReply',
    'APICreateRootVolumeTemplateFromRootVolumeMsg',
    'APIAddImageMsg',
    'APIGetImageReply',
    'APICreateDataVolumeTemplateFromVolumeMsg',
    'APIRecoverImageMsg',
    'APIQueryImageMsg',
    'APICreateRootVolumeTemplateFromVolumeSnapshotMsg',
    'APIUpdateImageMsg',
    'APIChangeImageStateMsg',
    'APIListImageReply',
    'APISearchImageReply',
    'APIDeleteImageMsg',
    'APIQueryHostMsg',
    'APIGetHypervisorTypesReply',
    'APIGetHypervisorTypesMsg',
    'APISearchHostReply',
    'APIGetHostReply',
    'APIDeleteHostMsg',
    'APIUpdateHostMsg',
    'APIListHostReply',
    'APIChangeHostStateMsg',
    'APIReconnectHostMsg',
    'APIQueryHostReply',
    'APIRequestConsoleAccessMsg',
    'APIReconnectConsoleProxyAgentMsg',
    'APIQueryConsoleProxyAgentReply',
    'APIQueryConsoleProxyAgentMsg',
    'APIListClusterReply',
    'APIQueryClusterReply',
    'APICreateClusterMsg',
    'APIDeleteClusterMsg',
    'APISearchClusterReply',
    'APIGetClusterReply',
    'APIUpdateClusterMsg',
    'APIQueryClusterMsg',
    'APIChangeClusterStateMsg',
    'APIGetHostAllocatorStrategiesMsg',
    'APIGetCpuMemoryCapacityMsg',
    'APIGetHostAllocatorStrategiesReply',
    'APIGetCpuMemoryCapacityReply',
    'APIGetVersionMsg',
    'APIGetVersionReply',
    'APIListManagementNodeReply',
    'APIQueryManagementNodeMsg',
    'APIQueryManagementNodeReply',
    'APIIsReadyToGoMsg',
    'APIIsReadyToGoReply',
    'APIQueryIscsiFileSystemBackendPrimaryStorageReply',
    'APIQueryIscsiFileSystemBackendPrimaryStorageMsg',
    'APIAddIscsiFileSystemBackendPrimaryStorageMsg',
    'APIUpdateIscsiFileSystemBackendPrimaryStorageMsg',
    'APIKvmRunShellMsg',
    'APIUpdateKVMHostMsg',
    'APIAddKVMHostMsg',
    'APIRefreshLoadBalancerMsg',
    'APIQueryLoadBalancerMsg',
    'APICreateLoadBalancerListenerMsg',
    'APIRemoveVmNicFromLoadBalancerMsg',
    'APIQueryLoadBalancerReply',
    'APIDeleteLoadBalancerListenerMsg',
    'APIAddVmNicToLoadBalancerMsg',
    'APICreateLoadBalancerMsg',
    'APIDeleteLoadBalancerMsg',
    'APIQueryLoadBalancerListenerReply',
    'APIQueryLoadBalancerListenerMsg',
    'APIQueryLocalStorageResourceRefMsg',
    'APIGetLocalStorageHostDiskCapacityReply',
    'APILocalStorageGetVolumeMigratableHostsMsg',
    'APILocalStorageMigrateVolumeMsg',
    'APIGetLocalStorageHostDiskCapacityMsg',
    'APIAddLocalPrimaryStorageMsg',
    'APIQueryLocalStorageResourceRefReply',
    'APILocalStorageGetVolumeMigratableReply',
    'APIAddNfsPrimaryStorageMsg',
    'APIUpdatePortForwardingRuleMsg',
    'APIGetPortForwardingAttachableVmNicsMsg',
    'APIDetachPortForwardingRuleMsg',
    'APIAttachPortForwardingRuleMsg',
    'APICreatePortForwardingRuleMsg',
    'APIDeletePortForwardingRuleMsg',
    'APIGetPortForwardingAttachableVmNicsReply',
    'APIChangePortForwardingRuleStateMsg',
    'APIQueryPortForwardingRuleReply',
    'APIListPortForwardingRuleReply',
    'APIQueryPortForwardingRuleMsg',
    'APIQuerySecurityGroupRuleReply',
    'APIChangeSecurityGroupStateMsg',
    'APIAddSecurityGroupRuleMsg',
    'APIDetachSecurityGroupFromL3NetworkMsg',
    'APIDeleteVmNicFromSecurityGroupMsg',
    'APIDeleteSecurityGroupRuleMsg',
    'APIDeleteSecurityGroupMsg',
    'APIAttachSecurityGroupToL3NetworkMsg',
    'APIAddVmNicToSecurityGroupMsg',
    'APIQueryVmNicInSecurityGroupReply',
    'APIUpdateSecurityGroupMsg',
    'APIGetCandidateVmNicForSecurityGroupMsg',
    'APIQueryVmNicInSecurityGroupMsg',
    'APICreateSecurityGroupMsg',
    'APIGetCandidateVmNicForSecurityGroupReply',
    'APIQuerySecurityGroupReply',
    'APIListVmNicInSecurityGroupReply',
    'APIListSecurityGroupReply',
    'APIQuerySecurityGroupRuleMsg',
    'APIQuerySecurityGroupMsg',
    'APIGetSftpBackupStorageReply',
    'APIReconnectSftpBackupStorageMsg',
    'APIQuerySftpBackupStorageMsg',
    'APIUpdateSftpBackupStorageMsg',
    'APIAddSftpBackupStorageMsg',
    'APIQuerySftpBackupStorageReply',
    'APISearchSftpBackupStorageReply',
    'APIAddSharedMountPointPrimaryStorageMsg',
    'APIAddSimulatorBackupStorageMsg',
    'APIAddSimulatorPrimaryStorageMsg',
    'APIAddSimulatorHostMsg',
    'APIQueryVipReply',
    'APIUpdateVipMsg',
    'APIChangeVipStateMsg',
    'APIDeleteVipMsg',
    'APICreateVipMsg',
    'APIQueryVipMsg',
    'APISearchVirtualRouterVmReply',
    'APIUpdateVirtualRouterOfferingMsg',
    'APIReconnectVirtualRouterMsg',
    'APICreateVirtualRouterOfferingMsg',
    'APIQueryVirtualRouterOfferingMsg',
    'APIQueryVirtualRouterOfferingReply',
    'APIQueryVirtualRouterVmMsg',
    'APISearchVirtualRouterOffingReply',
    'APICreateVirtualRouterVmMsg',
    'APIQueryVirtualRouterVmReply',
    'APIGetVirtualRouterOfferingReply',
]

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



class AccountInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
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



class SharedResourceInventory(object):
    def __init__(self):
        self.ownerAccountUuid = None
        self.receiverAccountUuid = None
        self.toPublic = None
        self.resourceType = None
        self.resourceUuid = None
        self.lastOpDate = None
        self.createDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'ownerAccountUuid'):
            self.ownerAccountUuid = inv.ownerAccountUuid
        else:
            self.ownerAccountUuid = None

        if hasattr(inv, 'receiverAccountUuid'):
            self.receiverAccountUuid = inv.receiverAccountUuid
        else:
            self.receiverAccountUuid = None

        if hasattr(inv, 'toPublic'):
            self.toPublic = inv.toPublic
        else:
            self.toPublic = None

        if hasattr(inv, 'resourceType'):
            self.resourceType = inv.resourceType
        else:
            self.resourceType = None

        if hasattr(inv, 'resourceUuid'):
            self.resourceUuid = inv.resourceUuid
        else:
            self.resourceUuid = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

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



class UserInventory(object):
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
        self.systemUsedCapacity = None
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

        if hasattr(inv, 'systemUsedCapacity'):
            self.systemUsedCapacity = inv.systemUsedCapacity
        else:
            self.systemUsedCapacity = None

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



VIRTUAL_ROUTER_PROVIDER_TYPE = 'VirtualRouter'
VIRTUAL_ROUTER_VM_TYPE = 'VirtualRouter'
VIRTUAL_ROUTER_OFFERING_TYPE = 'VirtualRouter'
VR_PUBLIC_NIC_META = '1'
VR_MANAGEMENT_NIC_META = '2'
VR_MANAGEMENT_AND_PUBLIC_NIC_META = '3'
SYSTEMADMIN = 'SystemAdmin'
NORMAL = 'Normal'
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
NFS_PRIMARY_STORAGE_TYPE = 'NFS'
L3_BASIC_NETWORK_TYPE = 'L3BasicNetwork'
FIRST_AVAILABLE_IP_ALLOCATOR_STRATEGY = 'FirstAvailableIpAllocatorStrategy'
RANDOM_IP_ALLOCATOR_STRATEGY = 'RandomIpAllocatorStrategy'
SIMULATOR_PRIMARY_STORAGE_TYPE = 'SimulatorPrimaryStorage'
INGRESS = 'Ingress'
EGRESS = 'Egress'
L2_NO_VLAN_NETWORK_TYPE = 'L2NoVlanNetwork'
L2_VLAN_NETWORK_TYPE = 'L2VlanNetwork'
KVM_HYPERVISOR_TYPE = 'KVM'
TCP = 'TCP'
UDP = 'UDP'
ICMP = 'ICMP'
ZSTACK_IMAGE_TYPE = 'zstack'
ZSTACK_CLUSTER_TYPE = 'zstack'
USER_VM_TYPE = 'UserVm'
SFTP_BACKUP_STORAGE_TYPE = 'SftpBackupStorage'
SIMULATOR_BACKUP_STORAGE_TYPE = 'SimulatorBackupStorage'
CEPH_BACKUP_STORAGE_TYPE = 'Ceph'
CEPH_PRIMARY_STORAGE_TYPE = 'Ceph'
INITIAL_SYSTEM_ADMIN_UUID = '36c27e8ff05c4780bf6d2fa65700f22e'
INITIAL_SYSTEM_ADMIN_NAME = 'admin'
INITIAL_SYSTEM_ADMIN_PASSWORD = 'b109f3bbbc244eb82441917ed06d618b9008dd09b3befd1b5e07394c706a8bb980b1d7785e5976ec049b46df5f1326af5a2ea6d103fd07c95385ffab0cacbc86'
FUSIONSTOR_BACKUP_STORAGE_TYPE = 'Fusionstor'
FUSIONSTOR_PRIMARY_STORAGE_TYPE = 'Fusionstor'
DEFAULT_PRIMARY_STORAGE_ALLOCATION_STRATEGY_TYPE = 'DefaultPrimaryStorageAllocationStrategy'
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
ISCSI_FILE_SYSTEM_BACKEND_PRIMARY_STORAGE_TYPE = 'IscsiFileSystemBackendPrimaryStorage'
SIMULATOR_HYPERVISOR_TYPE = 'Simulator'
LOCAL_STORAGE_TYPE = 'LocalStorage'

class GlobalConfig_CONSOLE(object):
    PROXY_IDLETIMEOUT = 'proxy.idleTimeout'
    AGENT_PING_INTERVAL = 'agent.ping.interval'

    @staticmethod
    def get_category():
        return 'console'

class GlobalConfig_IMAGE(object):
    EXPUNGEPERIOD = 'expungePeriod'
    DELETIONPOLICY = 'deletionPolicy'
    EXPUNGEINTERVAL = 'expungeInterval'

    @staticmethod
    def get_category():
        return 'image'

class GlobalConfig_NFSPRIMARYSTORAGE(object):
    MOUNT_BASE = 'mount.base'

    @staticmethod
    def get_category():
        return 'nfsPrimaryStorage'

class GlobalConfig_VOLUMESNAPSHOT(object):
    BACKUP_PARALLELISMDEGREE = 'backup.parallelismDegree'
    DELETE_PARALLELISMDEGREE = 'delete.parallelismDegree'
    INCREMENTALSNAPSHOT_MAXNUM = 'incrementalSnapshot.maxNum'

    @staticmethod
    def get_category():
        return 'volumeSnapshot'

class GlobalConfig_PORTFORWARDING(object):
    SNATINBOUNDTRAFFIC = 'snatInboundTraffic'

    @staticmethod
    def get_category():
        return 'portForwarding'

class GlobalConfig_KVM(object):
    VM_CONSOLEMODE = 'vm.consoleMode'
    DATAVOLUME_MAXNUM = 'dataVolume.maxNum'
    RESERVEDMEMORY = 'reservedMemory'
    HOST_SYNCLEVEL = 'host.syncLevel'
    HOST_DNSCHECKLIST = 'host.DNSCheckList'
    VMSYNCONHOSTPING = 'vmSyncOnHostPing'
    VM_CPUMODE = 'vm.cpuMode'
    REDHAT_LIVESNAPSHOTON = 'redhat.liveSnapshotOn'
    VM_CACHEMODE = 'vm.cacheMode'
    VM_MIGRATIONQUANTITY = 'vm.migrationQuantity'
    RESERVEDCPU = 'reservedCpu'

    @staticmethod
    def get_category():
        return 'kvm'

class GlobalConfig_MANAGEMENTSERVER(object):
    NODE_HEARTBEATINTERVAL = 'node.heartbeatInterval'
    NODE_JOINDELAY = 'node.joinDelay'

    @staticmethod
    def get_category():
        return 'managementServer'

class GlobalConfig_FUSIONSTOR(object):
    IMAGECACHE_CLEANUP_INTERVAL = 'imageCache.cleanup.interval'
    PRIMARYSTORAGE_DELETEPOOL = 'primaryStorage.deletePool'
    BACKUPSTORAGE_IMAGE_DOWNLOAD_TIMEOUT = 'backupStorage.image.download.timeout'

    @staticmethod
    def get_category():
        return 'fusionstor'

class GlobalConfig_LOG(object):
    ENABLED = 'enabled'

    @staticmethod
    def get_category():
        return 'log'

class GlobalConfig_SECURITYGROUP(object):
    REFRESH_DELAYINTERVAL = 'refresh.delayInterval'
    INGRESS_DEFAULTPOLICY = 'ingress.defaultPolicy'
    HOST_FAILUREWORKERINTERVAL = 'host.failureWorkerInterval'
    EGRESS_DEFAULTPOLICY = 'egress.defaultPolicy'
    HOST_FAILURERESOLVEPERTIME = 'host.failureResolvePerTime'

    @staticmethod
    def get_category():
        return 'securityGroup'

class GlobalConfig_HOSTALLOCATOR(object):
    PAGINATIONLIMIT = 'paginationLimit'
    RESERVEDCAPACITY_ZONELEVEL = 'reservedCapacity.zoneLevel'
    RESERVEDCAPACITY_HOSTLEVEL = 'reservedCapacity.hostLevel'
    RESERVEDCAPACITY_CLUSTERLEVEL = 'reservedCapacity.clusterLevel'
    USEPAGINATION = 'usePagination'

    @staticmethod
    def get_category():
        return 'hostAllocator'

class GlobalConfig_APPLIANCEVM(object):
    CONNECT_TIMEOUT = 'connect.timeout'
    AGENT_DEPLOYONSTART = 'agent.deployOnStart'
    SSH_TIMEOUT = 'ssh.timeout'

    @staticmethod
    def get_category():
        return 'applianceVm'

class GlobalConfig_EIP(object):
    SNATINBOUNDTRAFFIC = 'snatInboundTraffic'

    @staticmethod
    def get_category():
        return 'eip'

class GlobalConfig_VIRTUALROUTER(object):
    COMMAND_PARALLELISMDEGREE = 'command.parallelismDegree'
    AGENT_DEPLOYONSTART = 'agent.deployOnStart'
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'
    PING_INTERVAL = 'ping.interval'
    DNSMASQ_RESTARTAFTERNUMBEROFSIGUSER1 = 'dnsmasq.restartAfterNumberOfSIGUSER1'

    @staticmethod
    def get_category():
        return 'virtualRouter'

class GlobalConfig_VOLUME(object):
    EXPUNGEPERIOD = 'expungePeriod'
    DISKOFFERING_SETNULLWHENDELETING = 'diskOffering.setNullWhenDeleting'
    DELETIONPOLICY = 'deletionPolicy'
    EXPUNGEINTERVAL = 'expungeInterval'

    @staticmethod
    def get_category():
        return 'volume'

class GlobalConfig_CEPH(object):
    PRIMARYSTORAGE_DELETEPOOL = 'primaryStorage.deletePool'
    IMAGECACHE_CLEANUP_INTERVAL = 'imageCache.cleanup.interval'
    BACKUPSTORAGE_IMAGE_DOWNLOAD_TIMEOUT = 'backupStorage.image.download.timeout'

    @staticmethod
    def get_category():
        return 'ceph'

class GlobalConfig_CLOUDBUS(object):
    STATISTICS_ON = 'statistics.on'

    @staticmethod
    def get_category():
        return 'cloudBus'

class GlobalConfig_LOADBALANCER(object):
    CONNECTIONIDLETIMEOUT = 'connectionIdleTimeout'
    HEALTHCHECKINTERVAL = 'healthCheckInterval'
    MAXCONNECTION = 'maxConnection'
    HEALTHCHECKTARGET = 'healthCheckTarget'
    HEALTHCHECKTIMEOUT = 'healthCheckTimeout'
    BALANCERALGORITHM = 'balancerAlgorithm'
    HEALTHYTHRESHOLD = 'healthyThreshold'
    UNHEALTHYTHRESHOLD = 'unhealthyThreshold'

    @staticmethod
    def get_category():
        return 'loadBalancer'

class GlobalConfig_IDENTITY(object):
    SESSION_CLEANUP_INTERVAL = 'session.cleanup.interval'
    ACCOUNT_API_CONTROL = 'account.api.control'
    SESSION_MAXCONCURRENT = 'session.maxConcurrent'
    ADMIN_SHOWALLRESOURCE = 'admin.showAllResource'
    SESSION_TIMEOUT = 'session.timeout'

    @staticmethod
    def get_category():
        return 'identity'

class GlobalConfig_BACKUPSTORAGE(object):
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'
    RESERVEDCAPACITY = 'reservedCapacity'
    PING_INTERVAL = 'ping.interval'

    @staticmethod
    def get_category():
        return 'backupStorage'

class GlobalConfig_VM(object):
    EXPUNGEPERIOD = 'expungePeriod'
    DELETIONPOLICY = 'deletionPolicy'
    DATAVOLUME_DELETEONVMDESTROY = 'dataVolume.deleteOnVmDestroy'
    INSTANCEOFFERING_SETNULLWHENDELETING = 'instanceOffering.setNullWhenDeleting'
    EXPUNGEINTERVAL = 'expungeInterval'

    @staticmethod
    def get_category():
        return 'vm'

class GlobalConfig_QUOTA(object):
    VOLUME_DATA_NUM = 'volume.data.num'
    VM_CPUNUM = 'vm.cpuNum'
    LOADBALANCER_NUM = 'loadBalancer.num'
    L3_NUM = 'l3.num'
    SECURITYGROUP_NUM = 'securityGroup.num'
    VM_MEMORYSIZE = 'vm.memorySize'
    PORTFORWARDING_NUM = 'portForwarding.num'
    VIP_NUM = 'vip.num'
    VM_NUM = 'vm.num'
    VOLUME_CAPACITY = 'volume.capacity'
    EIP_NUM = 'eip.num'

    @staticmethod
    def get_category():
        return 'quota'

class GlobalConfig_HOST(object):
    LOAD_PARALLELISMDEGREE = 'load.parallelismDegree'
    LOAD_ALL = 'load.all'
    CONNECTION_AUTORECONNECTONERROR = 'connection.autoReconnectOnError'
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'
    MAINTENANCEMODE_IGNOREERROR = 'maintenanceMode.ignoreError'
    PING_INTERVAL = 'ping.interval'

    @staticmethod
    def get_category():
        return 'host'

class GlobalConfig_PRIMARYSTORAGE(object):
    RESERVEDCAPACITY = 'reservedCapacity'
    IMAGECACHE_GARBAGECOLLECTOR_INTERVAL = 'imageCache.garbageCollector.interval'

    @staticmethod
    def get_category():
        return 'primaryStorage'


class QueryObjectSecurityGroupRuleInventory(object):
     PRIMITIVE_FIELDS = ['startPort','protocol','securityGroupUuid','allowedCidr','lastOpDate','state','type','uuid','endPort','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['securityGroup']
     QUERY_OBJECT_MAP = {
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
     }

class QueryObjectEipInventory(object):
     PRIMITIVE_FIELDS = ['guestIp','vipIp','vmNicUuid','vipUuid','name','lastOpDate','description','state','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNic','vip']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'vip' : 'QueryObjectVipInventory',
     }

class QueryObjectSystemTagInventory(object):
     PRIMITIVE_FIELDS = ['lastOpDate','tag','type','uuid','inherent','resourceUuid','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectL3NetworkDnsInventory(object):
     PRIMITIVE_FIELDS = ['dns','lastOpDate','l3NetworkUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVipInventory(object):
     PRIMITIVE_FIELDS = ['ip','useFor','description','l3NetworkUuid','uuid','netmask','name','serviceProvider','lastOpDate','peerL3NetworkUuid','state','gateway','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['portForwarding','loadBalancer','eip']
     QUERY_OBJECT_MAP = {
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
        'loadBalancer' : 'QueryObjectLoadBalancerInventory',
        'eip' : 'QueryObjectEipInventory',
     }

class QueryObjectVirtualRouterVipInventory(object):
     PRIMITIVE_FIELDS = ['virtualRouterVmUuid','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vip','applianceVm']
     QUERY_OBJECT_MAP = {
        'vip' : 'QueryObjectVipInventory',
        'applianceVm' : 'QueryObjectApplianceVmInventory',
     }

class QueryObjectL2NetworkInventory(object):
     PRIMITIVE_FIELDS = ['physicalInterface','name','zoneUuid','lastOpDate','description','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','zone','cluster']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectImageBackupStorageRefInventory(object):
     PRIMITIVE_FIELDS = ['installPath','lastOpDate','imageUuid','backupStorageUuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','backupStorage']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
     }

class QueryObjectApplianceVmInventory(object):
     PRIMITIVE_FIELDS = ['cpuSpeed','zoneUuid','description','type','managementNetworkUuid','uuid','platform','defaultRouteL3NetworkUuid','applianceVmType','hostUuid','lastOpDate','instanceOfferingUuid','state','imageUuid','createDate','clusterUuid','allocatorStrategy','hypervisorType','cpuNum','defaultL3NetworkUuid','lastHostUuid','memorySize','rootVolumeUuid','name','status','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNics','allVolumes','cluster','image','vmNics','virtualRouterOffering','allVolumes','zone','host','rootVolume','portForwarding','vip','eip']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'image' : 'QueryObjectImageInventory',
        'vmNics' : 'QueryObjectVmNicInventory',
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
        'allVolumes' : 'QueryObjectVolumeInventory',
        'virtualRouterOffering' : 'QueryObjectVirtualRouterOfferingInventory',
        'zone' : 'QueryObjectZoneInventory',
        'host' : 'QueryObjectHostInventory',
        'rootVolume' : 'QueryObjectVolumeInventory',
        'vip' : 'QueryObjectVipInventory',
        'eip' : 'QueryObjectEipInventory',
     }

class QueryObjectVolumeSnapshotTreeInventory(object):
     PRIMITIVE_FIELDS = ['current','volumeUuid','lastOpDate','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume','snapshot']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'snapshot' : 'QueryObjectVolumeSnapshotInventory',
     }

class QueryObjectPolicyInventory(object):
     PRIMITIVE_FIELDS = ['name','accountUuid','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account','user','group']
     QUERY_OBJECT_MAP = {
        'user' : 'QueryObjectUserInventory',
        'account' : 'QueryObjectAccountInventory',
        'group' : 'QueryObjectUserGroupInventory',
     }

class QueryObjectNetworkServiceProviderL2NetworkRefInventory(object):
     PRIMITIVE_FIELDS = ['l2NetworkUuid','networkServiceProviderUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectLocalStorageResourceRefInventory(object):
     PRIMITIVE_FIELDS = ['size','hostUuid','lastOpDate','primaryStorageUuid','resourceUuid','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume','image','snapshot']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'image' : 'QueryObjectImageInventory',
        'snapshot' : 'QueryObjectVolumeSnapshotInventory',
     }

class QueryObjectUserInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','accountUuid','description','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account','group','policy']
     QUERY_OBJECT_MAP = {
        'account' : 'QueryObjectAccountInventory',
        'group' : 'QueryObjectUserGroupInventory',
        'policy' : 'QueryObjectPolicyInventory',
     }

class QueryObjectCephBackupStorageInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','description','type','uuid','url','totalCapacity','fsid','name','lastOpDate','state','poolName','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['mons','mons','image','volumeSnapshot','zone']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'mons' : 'QueryObjectCephBackupStorageMonInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectCephPrimaryStorageMonInventory(object):
     PRIMITIVE_FIELDS = ['hostname','monPort','lastOpDate','primaryStorageUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVmNicSecurityGroupRefInventory(object):
     PRIMITIVE_FIELDS = ['vmNicUuid','securityGroupUuid','lastOpDate','vmInstanceUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNic','securityGroup']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
     }

class QueryObjectManagementNodeInventory(object):
     PRIMITIVE_FIELDS = ['hostName','joinDate','heartBeat','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectCephBackupStorageMonInventory(object):
     PRIMITIVE_FIELDS = ['hostname','monPort','lastOpDate','backupStorageUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectHostCapacityInventory(object):
     PRIMITIVE_FIELDS = ['totalMemory','totalCpu','availableMemory','availableCpu','uuid','totalPhysicalMemory','availablePhysicalMemory','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectAccountResourceRefInventory(object):
     PRIMITIVE_FIELDS = ['lastOpDate','accountUuid','resourceUuid','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVolumeInventory(object):
     PRIMITIVE_FIELDS = ['installPath','format','description','type','uuid','deviceId','diskOfferingUuid','size','name','lastOpDate','state','primaryStorageUuid','vmInstanceUuid','rootImageUuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','vmInstance','diskOffering','primaryStorage','localStorageHostRef','snapshot']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'diskOffering' : 'QueryObjectDiskOfferingInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
        'localStorageHostRef' : 'QueryObjectLocalStorageResourceRefInventory',
        'snapshot' : 'QueryObjectVolumeSnapshotInventory',
     }

class QueryObjectCephPrimaryStorageInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','mountPath','imageCachePoolName','zoneUuid','description','rootVolumePoolName','systemUsedCapacity','type','uuid','totalPhysicalCapacity','url','totalCapacity','fsid','name','lastOpDate','state','dataVolumePoolName','availablePhysicalCapacity','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['mons','volume','volumeSnapshot','mons','zone','cluster']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'mons' : 'QueryObjectCephPrimaryStorageMonInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectPrimaryStorageInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','mountPath','zoneUuid','description','systemUsedCapacity','type','uuid','totalPhysicalCapacity','url','totalCapacity','name','lastOpDate','state','availablePhysicalCapacity','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume','volumeSnapshot','zone','cluster']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectSecurityGroupInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','description','state','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['rules','vmNic','l3Network']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'rules' : 'QueryObjectSecurityGroupRuleInventory',
     }

class QueryObjectSimulatorHostInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','zoneUuid','availableCpuCapacity','description','cpuCapacity','hypervisorType','totalMemoryCapacity','uuid','memoryCapacity','managementIp','name','lastOpDate','totalCpuCapacity','availableMemoryCapacity','state','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectZoneInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','description','state','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','vmInstance','l3Network','host','primaryStorage','l2Network','backupStorage']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
        'host' : 'QueryObjectHostInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
        'l2Network' : 'QueryObjectL2NetworkInventory',
     }

class QueryObjectConsoleProxyAgentInventory(object):
     PRIMITIVE_FIELDS = ['managementIp','lastOpDate','description','state','type','uuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVolumeSnapshotBackupStorageRefInventory(object):
     PRIMITIVE_FIELDS = ['installPath','volumeSnapshotUuid','backupStorageUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volumeSnapshot','backupStorage']
     QUERY_OBJECT_MAP = {
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
     }

class QueryObjectVirtualRouterPortForwardingRuleRefInventory(object):
     PRIMITIVE_FIELDS = ['vipUuid','virtualRouterVmUuid','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['portForwarding','vip','applianceVm']
     QUERY_OBJECT_MAP = {
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
        'vip' : 'QueryObjectVipInventory',
        'applianceVm' : 'QueryObjectApplianceVmInventory',
     }

class QueryObjectSecurityGroupL3NetworkRefInventory(object):
     PRIMITIVE_FIELDS = ['securityGroupUuid','lastOpDate','l3NetworkUuid','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','securityGroup']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
     }

class QueryObjectUserGroupInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','accountUuid','description','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account','user','policy']
     QUERY_OBJECT_MAP = {
        'user' : 'QueryObjectUserInventory',
        'account' : 'QueryObjectAccountInventory',
        'policy' : 'QueryObjectPolicyInventory',
     }

class QueryObjectVirtualRouterVmInventory(object):
     PRIMITIVE_FIELDS = ['cpuSpeed','zoneUuid','description','type','managementNetworkUuid','uuid','platform','defaultRouteL3NetworkUuid','applianceVmType','hostUuid','lastOpDate','publicNetworkUuid','instanceOfferingUuid','state','imageUuid','createDate','clusterUuid','allocatorStrategy','hypervisorType','cpuNum','defaultL3NetworkUuid','lastHostUuid','memorySize','rootVolumeUuid','name','status','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNics','allVolumes','cluster','image','vmNics','virtualRouterOffering','allVolumes','zone','host','rootVolume','portForwarding','loadBalancer','vip','eip']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'image' : 'QueryObjectImageInventory',
        'vmNics' : 'QueryObjectVmNicInventory',
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
        'allVolumes' : 'QueryObjectVolumeInventory',
        'virtualRouterOffering' : 'QueryObjectVirtualRouterOfferingInventory',
        'zone' : 'QueryObjectZoneInventory',
        'loadBalancer' : 'QueryObjectLoadBalancerInventory',
        'host' : 'QueryObjectHostInventory',
        'rootVolume' : 'QueryObjectVolumeInventory',
        'vip' : 'QueryObjectVipInventory',
        'eip' : 'QueryObjectEipInventory',
     }

class QueryObjectFusionstorBackupStorageMonInventory(object):
     PRIMITIVE_FIELDS = ['hostname','monPort','lastOpDate','backupStorageUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectIpRangeInventory(object):
     PRIMITIVE_FIELDS = ['endIp','startIp','netmask','name','lastOpDate','description','l3NetworkUuid','uuid','gateway','networkCidr','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
     }

class QueryObjectVirtualRouterLoadBalancerRefInventory(object):
     PRIMITIVE_FIELDS = ['loadBalancerUuid','lastOpDate','id','virtualRouterVmUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['virtualRouterVm','loadBalancer']
     QUERY_OBJECT_MAP = {
        'virtualRouterVm' : 'QueryObjectVirtualRouterVmInventory',
        'loadBalancer' : 'QueryObjectLoadBalancerInventory',
     }

class QueryObjectClusterInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','zoneUuid','description','state','hypervisorType','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmInstance','zone','host','l2Network','primaryStorage']
     QUERY_OBJECT_MAP = {
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'zone' : 'QueryObjectZoneInventory',
        'host' : 'QueryObjectHostInventory',
        'l2Network' : 'QueryObjectL2NetworkInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
     }

class QueryObjectIscsiFileSystemBackendPrimaryStorageInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','mountPath','zoneUuid','chapUsername','description','systemUsedCapacity','type','uuid','totalPhysicalCapacity','url','hostname','sshUsername','totalCapacity','name','lastOpDate','state','filesystemType','availablePhysicalCapacity','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume','volumeSnapshot','zone','cluster']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectVmInstanceInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','cpuSpeed','allocatorStrategy','zoneUuid','description','hypervisorType','type','uuid','platform','cpuNum','defaultL3NetworkUuid','lastHostUuid','memorySize','rootVolumeUuid','hostUuid','name','lastOpDate','instanceOfferingUuid','state','imageUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNics','allVolumes','cluster','image','vmNics','allVolumes','zone','host','instanceOffering','rootVolume']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'image' : 'QueryObjectImageInventory',
        'vmNics' : 'QueryObjectVmNicInventory',
        'allVolumes' : 'QueryObjectVolumeInventory',
        'zone' : 'QueryObjectZoneInventory',
        'host' : 'QueryObjectHostInventory',
        'instanceOffering' : 'QueryObjectInstanceOfferingInventory',
        'rootVolume' : 'QueryObjectVolumeInventory',
     }

class QueryObjectL2NetworkClusterRefInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','l2NetworkUuid','lastOpDate','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','l2Network']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'l2Network' : 'QueryObjectL2NetworkInventory',
     }

class QueryObjectSharedResourceInventory(object):
     PRIMITIVE_FIELDS = ['receiverAccountUuid','ownerAccountUuid','lastOpDate','toPublic','resourceUuid','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectLoadBalancerListenerVmNicRefInventory(object):
     PRIMITIVE_FIELDS = ['listenerUuid','vmNicUuid','lastOpDate','id','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNic','listener']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'listener' : 'QueryObjectLoadBalancerListenerInventory',
     }

class QueryObjectHostInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','zoneUuid','availableCpuCapacity','description','hypervisorType','totalMemoryCapacity','uuid','managementIp','name','lastOpDate','totalCpuCapacity','availableMemoryCapacity','state','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','vmInstance','zone']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectConsoleProxyInventory(object):
     PRIMITIVE_FIELDS = ['agentType','scheme','proxyIdentity','uuid','targetPort','agentIp','token','proxyPort','proxyHostname','targetHostname','lastOpDate','vmInstanceUuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectApplianceVmFirewallRuleInventory(object):
     PRIMITIVE_FIELDS = ['startPort','destIp','protocol','applianceVmUuid','sourceIp','lastOpDate','allowCidr','l3NetworkUuid','endPort','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectInstanceOfferingInventory(object):
     PRIMITIVE_FIELDS = ['memorySize','sortKey','cpuSpeed','allocatorStrategy','name','lastOpDate','description','state','type','uuid','cpuNum','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmInstance']
     QUERY_OBJECT_MAP = {
        'vmInstance' : 'QueryObjectVmInstanceInventory',
     }

class QueryObjectQuotaInventory(object):
     PRIMITIVE_FIELDS = ['identityType','identityUuid','name','lastOpDate','value','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account']
     QUERY_OBJECT_MAP = {
        'account' : 'QueryObjectAccountInventory',
     }

class QueryObjectVirtualRouterOfferingInventory(object):
     PRIMITIVE_FIELDS = ['cpuSpeed','allocatorStrategy','zoneUuid','description','type','managementNetworkUuid','uuid','cpuNum','isDefault','memorySize','sortKey','name','lastOpDate','publicNetworkUuid','state','imageUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','zone','managementL3Network','publicL3Network']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'zone' : 'QueryObjectZoneInventory',
        'managementL3Network' : 'QueryObjectL3NetworkInventory',
        'publicL3Network' : 'QueryObjectL3NetworkInventory',
     }

class QueryObjectDiskOfferingInventory(object):
     PRIMITIVE_FIELDS = ['diskSize','sortKey','allocatorStrategy','name','lastOpDate','description','state','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
     }

class QueryObjectBackupStorageZoneRefInventory(object):
     PRIMITIVE_FIELDS = ['zoneUuid','lastOpDate','id','backupStorageUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['zone','backupStorage']
     QUERY_OBJECT_MAP = {
        'zone' : 'QueryObjectZoneInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
     }

class QueryObjectVirtualRouterEipRefInventory(object):
     PRIMITIVE_FIELDS = ['eipUuid','virtualRouterVmUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['eip','applianceVm']
     QUERY_OBJECT_MAP = {
        'eip' : 'QueryObjectEipInventory',
        'applianceVm' : 'QueryObjectApplianceVmInventory',
     }

class QueryObjectKVMHostInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','zoneUuid','availableCpuCapacity','description','hypervisorType','totalMemoryCapacity','uuid','managementIp','name','lastOpDate','totalCpuCapacity','availableMemoryCapacity','state','username','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','vmInstance','zone']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectVolumeSnapshotInventory(object):
     PRIMITIVE_FIELDS = ['primaryStorageInstallPath','volumeType','volumeUuid','treeUuid','format','description','type','uuid','parentUuid','size','name','lastOpDate','state','primaryStorageUuid','latest','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['backupStorageRefs','volume','backupStorageRef','tree','primaryStorage','localStorageHostRef','backupStorage']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'backupStorageRefs' : 'QueryObjectVolumeSnapshotBackupStorageRefInventory',
        'backupStorageRef' : 'QueryObjectVolumeSnapshotBackupStorageRefInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
        'tree' : 'QueryObjectVolumeSnapshotTreeInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
        'localStorageHostRef' : 'QueryObjectLocalStorageResourceRefInventory',
     }

class QueryObjectGlobalConfigInventory(object):
     PRIMITIVE_FIELDS = ['defaultValue','name','description','category','value','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectIpUseInventory(object):
     PRIMITIVE_FIELDS = ['use','usedIpUuid','lastOpDate','details','serviceId','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectUserGroupUserRefInventory(object):
     PRIMITIVE_FIELDS = ['groupUuid','userUuid','lastOpDate','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['user','group']
     QUERY_OBJECT_MAP = {
        'user' : 'QueryObjectUserInventory',
        'group' : 'QueryObjectUserGroupInventory',
     }

class QueryObjectNetworkServiceL3NetworkRefInventory(object):
     PRIMITIVE_FIELDS = ['networkServiceType','networkServiceProviderUuid','l3NetworkUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','serviceProvider']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'serviceProvider' : 'QueryObjectNetworkServiceProviderInventory',
     }

class QueryObjectFusionstorBackupStorageInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','description','type','uuid','url','totalCapacity','fsid','name','lastOpDate','state','poolName','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['mons','mons','image','volumeSnapshot','zone']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'mons' : 'QueryObjectFusionstorBackupStorageMonInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectUserGroupPolicyRefInventory(object):
     PRIMITIVE_FIELDS = ['policyUuid','groupUuid','lastOpDate','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['group','policy']
     QUERY_OBJECT_MAP = {
        'group' : 'QueryObjectUserGroupInventory',
        'policy' : 'QueryObjectPolicyInventory',
     }

class QueryObjectPrimaryStorageClusterRefInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','lastOpDate','id','primaryStorageUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','primaryStorage']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
     }

class QueryObjectFusionstorPrimaryStorageInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','mountPath','imageCachePoolName','zoneUuid','description','rootVolumePoolName','systemUsedCapacity','type','uuid','totalPhysicalCapacity','url','totalCapacity','fsid','name','lastOpDate','state','dataVolumePoolName','availablePhysicalCapacity','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['mons','volume','volumeSnapshot','mons','zone','cluster']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'mons' : 'QueryObjectFusionstorPrimaryStorageMonInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectNetworkServiceTypeInventory(object):
     PRIMITIVE_FIELDS = ['networkServiceProviderUuid','type','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectL2VlanNetworkInventory(object):
     PRIMITIVE_FIELDS = ['vlan','physicalInterface','name','zoneUuid','lastOpDate','description','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','zone','cluster']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectAccountInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','description','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['quota','user','group','policy']
     QUERY_OBJECT_MAP = {
        'quota' : 'QueryObjectQuotaInventory',
        'user' : 'QueryObjectUserInventory',
        'group' : 'QueryObjectUserGroupInventory',
        'policy' : 'QueryObjectPolicyInventory',
     }

class QueryObjectPortForwardingRuleInventory(object):
     PRIMITIVE_FIELDS = ['vipUuid','description','protocolType','privatePortStart','uuid','guestIp','vipPortStart','vipIp','vipPortEnd','vmNicUuid','name','allowedCidr','lastOpDate','privatePortEnd','state','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNic','vip']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'vip' : 'QueryObjectVipInventory',
     }

class QueryObjectSftpBackupStorageInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','description','type','uuid','url','hostname','totalCapacity','name','lastOpDate','state','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','volumeSnapshot','zone']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectL3NetworkInventory(object):
     PRIMITIVE_FIELDS = ['zoneUuid','description','type','uuid','dnsDomain','system','l2NetworkUuid','name','lastOpDate','state','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['networkServices','ipRanges','vmNic','zone','l2Network','serviceProvider']
     QUERY_OBJECT_MAP = {
        'ipRanges' : 'QueryObjectIpRangeInventory',
        'vmNic' : 'QueryObjectVmNicInventory',
        'zone' : 'QueryObjectZoneInventory',
        'serviceProvider' : 'QueryObjectNetworkServiceProviderInventory',
        'l2Network' : 'QueryObjectL2NetworkInventory',
        'networkServices' : 'QueryObjectNetworkServiceL3NetworkRefInventory',
     }

class QueryObjectVmNicInventory(object):
     PRIMITIVE_FIELDS = ['ip','l3NetworkUuid','uuid','deviceId','mac','metaData','netmask','lastOpDate','gateway','vmInstanceUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['portForwarding','vmInstance','l3Network','eip','securityGroup','loadBalancerListener']
     QUERY_OBJECT_MAP = {
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
        'eip' : 'QueryObjectEipInventory',
        'loadBalancerListener' : 'QueryObjectLoadBalancerListenerInventory',
     }

class QueryObjectImageInventory(object):
     PRIMITIVE_FIELDS = ['format','description','mediaType','type','uuid','url','platform','guestOsType','system','size','md5Sum','name','lastOpDate','state','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['backupStorageRefs','volume','backupStorage']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'backupStorageRefs' : 'QueryObjectImageBackupStorageRefInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
     }

class QueryObjectUserPolicyRefInventory(object):
     PRIMITIVE_FIELDS = ['policyUuid','userUuid','lastOpDate','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['user','policy']
     QUERY_OBJECT_MAP = {
        'user' : 'QueryObjectUserInventory',
        'policy' : 'QueryObjectPolicyInventory',
     }

class QueryObjectPrimaryStorageCapacityInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','totalCapacity','lastOpDate','systemUsedCapacity','uuid','totalPhysicalCapacity','availablePhysicalCapacity','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectFusionstorPrimaryStorageMonInventory(object):
     PRIMITIVE_FIELDS = ['hostname','monPort','lastOpDate','primaryStorageUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectBackupStorageInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','totalCapacity','name','lastOpDate','description','state','type','uuid','url','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','volumeSnapshot','zone']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectLoadBalancerListenerInventory(object):
     PRIMITIVE_FIELDS = ['instancePort','loadBalancerUuid','protocol','name','lastOpDate','description','uuid','loadBalancerPort','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNicRefs','loadBalancer','vmNic']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'loadBalancer' : 'QueryObjectLoadBalancerInventory',
        'vmNicRefs' : 'QueryObjectLoadBalancerListenerVmNicRefInventory',
     }

class QueryObjectUserTagInventory(object):
     PRIMITIVE_FIELDS = ['lastOpDate','tag','type','uuid','resourceUuid','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectNetworkServiceProviderInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','description','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectLoadBalancerInventory(object):
     PRIMITIVE_FIELDS = ['vipUuid','name','description','state','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['listeners','listeners','vip']
     QUERY_OBJECT_MAP = {
        'listeners' : 'QueryObjectLoadBalancerListenerInventory',
        'vip' : 'QueryObjectVipInventory',
     }


queryMessageInventoryMap = {
     'APIQueryQuotaMsg' : QueryObjectQuotaInventory,
     'APIQuerySecurityGroupRuleMsg' : QueryObjectSecurityGroupRuleInventory,
     'APIQueryEipMsg' : QueryObjectEipInventory,
     'APIQuerySystemTagMsg' : QueryObjectSystemTagInventory,
     'APIQueryVipMsg' : QueryObjectVipInventory,
     'APIQueryVirtualRouterOfferingMsg' : QueryObjectVirtualRouterOfferingInventory,
     'APIQueryDiskOfferingMsg' : QueryObjectDiskOfferingInventory,
     'APIQueryL2NetworkMsg' : QueryObjectL2NetworkInventory,
     'APIQueryApplianceVmMsg' : QueryObjectApplianceVmInventory,
     'APIQueryVolumeSnapshotTreeMsg' : QueryObjectVolumeSnapshotTreeInventory,
     'APIQueryPolicyMsg' : QueryObjectPolicyInventory,
     'APIQueryLocalStorageResourceRefMsg' : QueryObjectLocalStorageResourceRefInventory,
     'APIQueryUserMsg' : QueryObjectUserInventory,
     'APIQueryCephBackupStorageMsg' : QueryObjectCephBackupStorageInventory,
     'APIQueryVolumeSnapshotMsg' : QueryObjectVolumeSnapshotInventory,
     'APIQueryGlobalConfigMsg' : QueryObjectGlobalConfigInventory,
     'APIQueryNetworkServiceL3NetworkRefMsg' : QueryObjectNetworkServiceL3NetworkRefInventory,
     'APIQueryManagementNodeMsg' : QueryObjectManagementNodeInventory,
     'APIQueryFusionstorBackupStorageMsg' : QueryObjectFusionstorBackupStorageInventory,
     'APIQueryAccountResourceRefMsg' : QueryObjectAccountResourceRefInventory,
     'APIQueryVolumeMsg' : QueryObjectVolumeInventory,
     'APIQueryFusionstorPrimaryStorageMsg' : QueryObjectFusionstorPrimaryStorageInventory,
     'APIQueryCephPrimaryStorageMsg' : QueryObjectCephPrimaryStorageInventory,
     'APIQueryL2VlanNetworkMsg' : QueryObjectL2VlanNetworkInventory,
     'APIQueryAccountMsg' : QueryObjectAccountInventory,
     'APIQueryPrimaryStorageMsg' : QueryObjectPrimaryStorageInventory,
     'APIQueryPortForwardingRuleMsg' : QueryObjectPortForwardingRuleInventory,
     'APIQuerySecurityGroupMsg' : QueryObjectSecurityGroupInventory,
     'APIQueryZoneMsg' : QueryObjectZoneInventory,
     'APIQueryConsoleProxyAgentMsg' : QueryObjectConsoleProxyAgentInventory,
     'APIQuerySftpBackupStorageMsg' : QueryObjectSftpBackupStorageInventory,
     'APIQueryL3NetworkMsg' : QueryObjectL3NetworkInventory,
     'APIQueryUserGroupMsg' : QueryObjectUserGroupInventory,
     'APIQueryVmNicMsg' : QueryObjectVmNicInventory,
     'APIQueryVirtualRouterVmMsg' : QueryObjectVirtualRouterVmInventory,
     'APIQueryImageMsg' : QueryObjectImageInventory,
     'APIQueryIpRangeMsg' : QueryObjectIpRangeInventory,
     'APIQueryClusterMsg' : QueryObjectClusterInventory,
     'APIQueryIscsiFileSystemBackendPrimaryStorageMsg' : QueryObjectIscsiFileSystemBackendPrimaryStorageInventory,
     'APIQueryVmInstanceMsg' : QueryObjectVmInstanceInventory,
     'APIQuerySharedResourceMsg' : QueryObjectSharedResourceInventory,
     'APIQueryHostMsg' : QueryObjectHostInventory,
     'APIQueryBackupStorageMsg' : QueryObjectBackupStorageInventory,
     'APIQueryLoadBalancerListenerMsg' : QueryObjectLoadBalancerListenerInventory,
     'APIQueryInstanceOfferingMsg' : QueryObjectInstanceOfferingInventory,
     'APIQueryUserTagMsg' : QueryObjectUserTagInventory,
     'APIQueryNetworkServiceProviderMsg' : QueryObjectNetworkServiceProviderInventory,
     'APIQueryLoadBalancerMsg' : QueryObjectLoadBalancerInventory,
}
