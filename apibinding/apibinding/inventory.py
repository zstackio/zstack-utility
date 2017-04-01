

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
        self.opaque = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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


APICREATEVMCPUALARMMSG_FULL_NAME = 'org.zstack.alert.APICreateVmCpuAlarmMsg'
class APICreateVmCpuAlarmMsg(object):
    FULL_NAME='org.zstack.alert.APICreateVmCpuAlarmMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.conditionName = NotNoneField()
        #mandatory field
        self.conditionOperator = NotNoneField()
        #mandatory field
        self.conditionValue = NotNoneField()
        self.conditionDuration = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEALARMMSG_FULL_NAME = 'org.zstack.alert.APIDeleteAlarmMsg'
class APIDeleteAlarmMsg(object):
    FULL_NAME='org.zstack.alert.APIDeleteAlarmMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIUPDATEALERTMSG_FULL_NAME = 'org.zstack.alert.APIUpdateAlertMsg'
class APIUpdateAlertMsg(object):
    FULL_NAME='org.zstack.alert.APIUpdateAlertMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        #valid values: [Active, Muted]
        self.status = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APILISTAPPLIANCEVMREPLY_FULL_NAME = 'org.zstack.appliancevm.APIListApplianceVmReply'
class APIListApplianceVmReply(object):
    FULL_NAME='org.zstack.appliancevm.APIListApplianceVmReply'
    def __init__(self):
        self.inventories = OptionalList()
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYAPPLIANCEVMREPLY_FULL_NAME = 'org.zstack.appliancevm.APIQueryApplianceVmReply'
class APIQueryApplianceVmReply(object):
    FULL_NAME='org.zstack.appliancevm.APIQueryApplianceVmReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APICALCULATEACCOUNTSPENDINGMSG_FULL_NAME = 'org.zstack.billing.APICalculateAccountSpendingMsg'
class APICalculateAccountSpendingMsg(object):
    FULL_NAME='org.zstack.billing.APICalculateAccountSpendingMsg'
    def __init__(self):
        #mandatory field
        self.accountUuid = NotNoneField()
        self.dateStart = None
        self.dateEnd = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICALCULATEACCOUNTSPENDINGREPLY_FULL_NAME = 'org.zstack.billing.APICalculateAccountSpendingReply'
class APICalculateAccountSpendingReply(object):
    FULL_NAME='org.zstack.billing.APICalculateAccountSpendingReply'
    def __init__(self):
        self.total = None
        self.spending = OptionalList()
        self.success = None
        self.error = None


APICREATERESOURCEPRICEMSG_FULL_NAME = 'org.zstack.billing.APICreateResourcePriceMsg'
class APICreateResourcePriceMsg(object):
    FULL_NAME='org.zstack.billing.APICreateResourcePriceMsg'
    def __init__(self):
        #mandatory field
        #valid values: [cpu, memory, rootVolume, dataVolume]
        self.resourceName = NotNoneField()
        self.resourceUnit = None
        #mandatory field
        self.timeUnit = NotNoneField()
        #mandatory field
        self.price = NotNoneField()
        self.accountUuid = None
        self.dateInLong = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETERESOURCEPRICEMSG_FULL_NAME = 'org.zstack.billing.APIDeleteResourcePriceMsg'
class APIDeleteResourcePriceMsg(object):
    FULL_NAME='org.zstack.billing.APIDeleteResourcePriceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYRESOURCEPRICEMSG_FULL_NAME = 'org.zstack.billing.APIQueryResourcePriceMsg'
class APIQueryResourcePriceMsg(object):
    FULL_NAME='org.zstack.billing.APIQueryResourcePriceMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYRESOURCEPRICEREPLY_FULL_NAME = 'org.zstack.billing.APIQueryResourcePriceReply'
class APIQueryResourcePriceReply(object):
    FULL_NAME='org.zstack.billing.APIQueryResourcePriceReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETGLOBALCONFIGREPLY_FULL_NAME = 'org.zstack.core.config.APIGetGlobalConfigReply'
class APIGetGlobalConfigReply(object):
    FULL_NAME='org.zstack.core.config.APIGetGlobalConfigReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APILISTGLOBALCONFIGREPLY_FULL_NAME = 'org.zstack.core.config.APIListGlobalConfigReply'
class APIListGlobalConfigReply(object):
    FULL_NAME='org.zstack.core.config.APIListGlobalConfigReply'
    def __init__(self):
        self.inventories = None
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYGLOBALCONFIGREPLY_FULL_NAME = 'org.zstack.core.config.APIQueryGlobalConfigReply'
class APIQueryGlobalConfigReply(object):
    FULL_NAME='org.zstack.core.config.APIQueryGlobalConfigReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDEBUGSIGNALMSG_FULL_NAME = 'org.zstack.core.debug.APIDebugSignalMsg'
class APIDebugSignalMsg(object):
    FULL_NAME='org.zstack.core.debug.APIDebugSignalMsg'
    def __init__(self):
        #mandatory field
        self.signals = NotNoneList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEGCJOBMSG_FULL_NAME = 'org.zstack.core.gc.APIDeleteGCJobMsg'
class APIDeleteGCJobMsg(object):
    FULL_NAME='org.zstack.core.gc.APIDeleteGCJobMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYGCJOBMSG_FULL_NAME = 'org.zstack.core.gc.APIQueryGCJobMsg'
class APIQueryGCJobMsg(object):
    FULL_NAME='org.zstack.core.gc.APIQueryGCJobMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYGCJOBREPLY_FULL_NAME = 'org.zstack.core.gc.APIQueryGCJobReply'
class APIQueryGCJobReply(object):
    FULL_NAME='org.zstack.core.gc.APIQueryGCJobReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APITRIGGERGCJOBMSG_FULL_NAME = 'org.zstack.core.gc.APITriggerGCJobMsg'
class APITriggerGCJobMsg(object):
    FULL_NAME='org.zstack.core.gc.APITriggerGCJobMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETENOTIFICATIONSMSG_FULL_NAME = 'org.zstack.core.notification.APIDeleteNotificationsMsg'
class APIDeleteNotificationsMsg(object):
    FULL_NAME='org.zstack.core.notification.APIDeleteNotificationsMsg'
    def __init__(self):
        #mandatory field
        self.uuids = NotNoneList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYNOTIFICATIONMSG_FULL_NAME = 'org.zstack.core.notification.APIQueryNotificationMsg'
class APIQueryNotificationMsg(object):
    FULL_NAME='org.zstack.core.notification.APIQueryNotificationMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYNOTIFICATIONREPLY_FULL_NAME = 'org.zstack.core.notification.APIQueryNotificationReply'
class APIQueryNotificationReply(object):
    FULL_NAME='org.zstack.core.notification.APIQueryNotificationReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYNOTIFICATIONSUBSCRIPTIONMSG_FULL_NAME = 'org.zstack.core.notification.APIQueryNotificationSubscriptionMsg'
class APIQueryNotificationSubscriptionMsg(object):
    FULL_NAME='org.zstack.core.notification.APIQueryNotificationSubscriptionMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYNOTIFICATIONSUBSCRIPTIONREPLY_FULL_NAME = 'org.zstack.core.notification.APIQueryNotificationSubscriptionReply'
class APIQueryNotificationSubscriptionReply(object):
    FULL_NAME='org.zstack.core.notification.APIQueryNotificationSubscriptionReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIUPDATENOTIFICATIONSSTATUSMSG_FULL_NAME = 'org.zstack.core.notification.APIUpdateNotificationsStatusMsg'
class APIUpdateNotificationsStatusMsg(object):
    FULL_NAME='org.zstack.core.notification.APIUpdateNotificationsStatusMsg'
    def __init__(self):
        #mandatory field
        self.uuids = NotNoneList()
        #mandatory field
        #valid values: [Unread, Read]
        self.status = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICHANGESCHEDULERSTATEMSG_FULL_NAME = 'org.zstack.core.scheduler.APIChangeSchedulerStateMsg'
class APIChangeSchedulerStateMsg(object):
    FULL_NAME='org.zstack.core.scheduler.APIChangeSchedulerStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETESCHEDULERMSG_FULL_NAME = 'org.zstack.core.scheduler.APIDeleteSchedulerMsg'
class APIDeleteSchedulerMsg(object):
    FULL_NAME='org.zstack.core.scheduler.APIDeleteSchedulerMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYSCHEDULERMSG_FULL_NAME = 'org.zstack.core.scheduler.APIQuerySchedulerMsg'
class APIQuerySchedulerMsg(object):
    FULL_NAME='org.zstack.core.scheduler.APIQuerySchedulerMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYSCHEDULERREPLY_FULL_NAME = 'org.zstack.core.scheduler.APIQuerySchedulerReply'
class APIQuerySchedulerReply(object):
    FULL_NAME='org.zstack.core.scheduler.APIQuerySchedulerReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIUPDATESCHEDULERMSG_FULL_NAME = 'org.zstack.core.scheduler.APIUpdateSchedulerMsg'
class APIUpdateSchedulerMsg(object):
    FULL_NAME='org.zstack.core.scheduler.APIUpdateSchedulerMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.schedulerName = None
        self.schedulerDescription = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEVMINSTANCEHALEVELMSG_FULL_NAME = 'org.zstack.ha.APIDeleteVmInstanceHaLevelMsg'
class APIDeleteVmInstanceHaLevelMsg(object):
    FULL_NAME='org.zstack.ha.APIDeleteVmInstanceHaLevelMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMINSTANCEHALEVELMSG_FULL_NAME = 'org.zstack.ha.APIGetVmInstanceHaLevelMsg'
class APIGetVmInstanceHaLevelMsg(object):
    FULL_NAME='org.zstack.ha.APIGetVmInstanceHaLevelMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMINSTANCEHALEVELREPLY_FULL_NAME = 'org.zstack.ha.APIGetVmInstanceHaLevelReply'
class APIGetVmInstanceHaLevelReply(object):
    FULL_NAME='org.zstack.ha.APIGetVmInstanceHaLevelReply'
    def __init__(self):
        self.level = None
        self.success = None
        self.error = None


APISETVMINSTANCEHALEVELMSG_FULL_NAME = 'org.zstack.ha.APISetVmInstanceHaLevelMsg'
class APISetVmInstanceHaLevelMsg(object):
    FULL_NAME='org.zstack.ha.APISetVmInstanceHaLevelMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [NeverStop, OnHostFailure]
        self.level = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIADDALIYUNKEYSECRETMSG_FULL_NAME = 'org.zstack.header.aliyun.account.APIAddAliyunKeySecretMsg'
class APIAddAliyunKeySecretMsg(object):
    FULL_NAME='org.zstack.header.aliyun.account.APIAddAliyunKeySecretMsg'
    def __init__(self):
        #mandatory field
        self.key = NotNoneField()
        #mandatory field
        self.secret = NotNoneField()
        self.accountUuid = None
        self.description = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEALIYUNKEYSECRETMSG_FULL_NAME = 'org.zstack.header.aliyun.account.APIDeleteAliyunKeySecretMsg'
class APIDeleteAliyunKeySecretMsg(object):
    FULL_NAME='org.zstack.header.aliyun.account.APIDeleteAliyunKeySecretMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYALIYUNKEYSECRETMSG_FULL_NAME = 'org.zstack.header.aliyun.account.APIQueryAliyunKeySecretMsg'
class APIQueryAliyunKeySecretMsg(object):
    FULL_NAME='org.zstack.header.aliyun.account.APIQueryAliyunKeySecretMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYALIYUNKEYSECRETREPLY_FULL_NAME = 'org.zstack.header.aliyun.account.APIQueryAliyunKeySecretReply'
class APIQueryAliyunKeySecretReply(object):
    FULL_NAME='org.zstack.header.aliyun.account.APIQueryAliyunKeySecretReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APICLONEECSINSTANCEFROMLOCALVMMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APICloneEcsInstanceFromLocalVmMsg'
class APICloneEcsInstanceFromLocalVmMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APICloneEcsInstanceFromLocalVmMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATEECSINSTANCEFROMLOCALIMAGEMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APICreateEcsInstanceFromLocalImageMsg'
class APICreateEcsInstanceFromLocalImageMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APICreateEcsInstanceFromLocalImageMsg'
    def __init__(self):
        #valid values: [cloud, cloud_efficiency, cloud_ssd, ephemeral_ssd]
        self.ecsRootVolumeType = None
        self.description = None
        self.ecsRootVolumeGBSize = None
        #valid values: [atomic, permissive]
        self.createMode = None
        self.privateIpAddress = None
        self.ecsInstanceName = None
        #valid values: [true, false]
        self.allocatePublicIp = None
        #mandatory field
        self.identityZoneUuid = NotNoneField()
        #mandatory field
        self.backupStorageUuid = NotNoneField()
        #mandatory field
        self.imageUuid = NotNoneField()
        #mandatory field
        self.instanceOfferingUuid = NotNoneField()
        #mandatory field
        self.ecsVSwitchUuid = NotNoneField()
        #mandatory field
        self.ecsSecurityGroupUuid = NotNoneField()
        #mandatory field
        #valid regex values: ^[a-zA-Z]\w{7,17}$
        self.ecsRootPassword = NotNoneField()
        #mandatory field
        self.ecsBandWidth = NotNoneField()
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEALLECSINSTANCESFROMDATACENTERMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APIDeleteAllEcsInstancesFromDataCenterMsg'
class APIDeleteAllEcsInstancesFromDataCenterMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APIDeleteAllEcsInstancesFromDataCenterMsg'
    def __init__(self):
        #mandatory field
        self.dataCenterUuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEECSINSTANCEMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APIDeleteEcsInstanceMsg'
class APIDeleteEcsInstanceMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APIDeleteEcsInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETECSINSTANCEVNCURLMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APIGetEcsInstanceVncUrlMsg'
class APIGetEcsInstanceVncUrlMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APIGetEcsInstanceVncUrlMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETECSINSTANCEVNCURLREPLY_FULL_NAME = 'org.zstack.header.aliyun.ecs.APIGetEcsInstanceVncUrlReply'
class APIGetEcsInstanceVncUrlReply(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APIGetEcsInstanceVncUrlReply'
    def __init__(self):
        self.ecsId = None
        self.vncUrl = None
        self.success = None
        self.error = None


APIQUERYECSINSTANCEFROMLOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APIQueryEcsInstanceFromLocalMsg'
class APIQueryEcsInstanceFromLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APIQueryEcsInstanceFromLocalMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYECSINSTANCEFROMLOCALREPLY_FULL_NAME = 'org.zstack.header.aliyun.ecs.APIQueryEcsInstanceFromLocalReply'
class APIQueryEcsInstanceFromLocalReply(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APIQueryEcsInstanceFromLocalReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIREBOOTECSINSTANCEMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APIRebootEcsInstanceMsg'
class APIRebootEcsInstanceMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APIRebootEcsInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISTARTECSINSTANCEMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APIStartEcsInstanceMsg'
class APIStartEcsInstanceMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APIStartEcsInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISTOPECSINSTANCEMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APIStopEcsInstanceMsg'
class APIStopEcsInstanceMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APIStopEcsInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISYNCECSINSTANCEFROMREMOTEMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APISyncEcsInstanceFromRemoteMsg'
class APISyncEcsInstanceFromRemoteMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APISyncEcsInstanceFromRemoteMsg'
    def __init__(self):
        #mandatory field
        self.dataCenterUuid = NotNoneField()
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIUPDATEECSINSTANCEVNCPASSWORDMSG_FULL_NAME = 'org.zstack.header.aliyun.ecs.APIUpdateEcsInstanceVncPasswordMsg'
class APIUpdateEcsInstanceVncPasswordMsg(object):
    FULL_NAME='org.zstack.header.aliyun.ecs.APIUpdateEcsInstanceVncPasswordMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid regex values: [A-Za-z0-9]{6}
        self.password = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATEECSIMAGEFROMLOCALIMAGEMSG_FULL_NAME = 'org.zstack.header.aliyun.image.APICreateEcsImageFromLocalImageMsg'
class APICreateEcsImageFromLocalImageMsg(object):
    FULL_NAME='org.zstack.header.aliyun.image.APICreateEcsImageFromLocalImageMsg'
    def __init__(self):
        #mandatory field
        self.imageUuid = NotNoneField()
        #mandatory field
        self.dataCenterUuid = NotNoneField()
        #mandatory field
        self.backupStorageUuid = NotNoneField()
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEECSIMAGELOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.image.APIDeleteEcsImageLocalMsg'
class APIDeleteEcsImageLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.image.APIDeleteEcsImageLocalMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEECSIMAGEREMOTEMSG_FULL_NAME = 'org.zstack.header.aliyun.image.APIDeleteEcsImageRemoteMsg'
class APIDeleteEcsImageRemoteMsg(object):
    FULL_NAME='org.zstack.header.aliyun.image.APIDeleteEcsImageRemoteMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYECSIMAGEFROMLOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.image.APIQueryEcsImageFromLocalMsg'
class APIQueryEcsImageFromLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.image.APIQueryEcsImageFromLocalMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYECSIMAGEFROMLOCALREPLY_FULL_NAME = 'org.zstack.header.aliyun.image.APIQueryEcsImageFromLocalReply'
class APIQueryEcsImageFromLocalReply(object):
    FULL_NAME='org.zstack.header.aliyun.image.APIQueryEcsImageFromLocalReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APISYNCECSIMAGEFROMREMOTEMSG_FULL_NAME = 'org.zstack.header.aliyun.image.APISyncEcsImageFromRemoteMsg'
class APISyncEcsImageFromRemoteMsg(object):
    FULL_NAME='org.zstack.header.aliyun.image.APISyncEcsImageFromRemoteMsg'
    def __init__(self):
        #mandatory field
        self.dataCenterUuid = NotNoneField()
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEECSSECURITYGROUPINLOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.network.group.APIDeleteEcsSecurityGroupInLocalMsg'
class APIDeleteEcsSecurityGroupInLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.network.group.APIDeleteEcsSecurityGroupInLocalMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYECSSECURITYGROUPFROMLOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.network.group.APIQueryEcsSecurityGroupFromLocalMsg'
class APIQueryEcsSecurityGroupFromLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.network.group.APIQueryEcsSecurityGroupFromLocalMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYECSSECURITYGROUPFROMLOCALREPLY_FULL_NAME = 'org.zstack.header.aliyun.network.group.APIQueryEcsSecurityGroupFromLocalReply'
class APIQueryEcsSecurityGroupFromLocalReply(object):
    FULL_NAME='org.zstack.header.aliyun.network.group.APIQueryEcsSecurityGroupFromLocalReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYECSSECURITYGROUPRULEFROMLOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.network.group.APIQueryEcsSecurityGroupRuleFromLocalMsg'
class APIQueryEcsSecurityGroupRuleFromLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.network.group.APIQueryEcsSecurityGroupRuleFromLocalMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYECSSECURITYGROUPRULEFROMLOCALREPLY_FULL_NAME = 'org.zstack.header.aliyun.network.group.APIQueryEcsSecurityGroupRuleFromLocalReply'
class APIQueryEcsSecurityGroupRuleFromLocalReply(object):
    FULL_NAME='org.zstack.header.aliyun.network.group.APIQueryEcsSecurityGroupRuleFromLocalReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APISYNCECSSECURITYGROUPFROMREMOTEMSG_FULL_NAME = 'org.zstack.header.aliyun.network.group.APISyncEcsSecurityGroupFromRemoteMsg'
class APISyncEcsSecurityGroupFromRemoteMsg(object):
    FULL_NAME='org.zstack.header.aliyun.network.group.APISyncEcsSecurityGroupFromRemoteMsg'
    def __init__(self):
        #mandatory field
        self.ecsVpcUuid = NotNoneField()
        self.ecsSecurityGroupId = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEECSVSWITCHINLOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.network.vpc.APIDeleteEcsVSwitchInLocalMsg'
class APIDeleteEcsVSwitchInLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.network.vpc.APIDeleteEcsVSwitchInLocalMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEECSVPCINLOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.network.vpc.APIDeleteEcsVpcInLocalMsg'
class APIDeleteEcsVpcInLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.network.vpc.APIDeleteEcsVpcInLocalMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIECSQUERYVPCFROMLOCALREPLY_FULL_NAME = 'org.zstack.header.aliyun.network.vpc.APIEcsQueryVpcFromLocalReply'
class APIEcsQueryVpcFromLocalReply(object):
    FULL_NAME='org.zstack.header.aliyun.network.vpc.APIEcsQueryVpcFromLocalReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYECSVSWITCHFROMLOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.network.vpc.APIQueryEcsVSwitchFromLocalMsg'
class APIQueryEcsVSwitchFromLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.network.vpc.APIQueryEcsVSwitchFromLocalMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYECSVSWITCHFROMLOCALREPLY_FULL_NAME = 'org.zstack.header.aliyun.network.vpc.APIQueryEcsVSwitchFromLocalReply'
class APIQueryEcsVSwitchFromLocalReply(object):
    FULL_NAME='org.zstack.header.aliyun.network.vpc.APIQueryEcsVSwitchFromLocalReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYECSVPCFROMLOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.network.vpc.APIQueryEcsVpcFromLocalMsg'
class APIQueryEcsVpcFromLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.network.vpc.APIQueryEcsVpcFromLocalMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISYNCECSVSWITCHFROMREMOTEMSG_FULL_NAME = 'org.zstack.header.aliyun.network.vpc.APISyncEcsVSwitchFromRemoteMsg'
class APISyncEcsVSwitchFromRemoteMsg(object):
    FULL_NAME='org.zstack.header.aliyun.network.vpc.APISyncEcsVSwitchFromRemoteMsg'
    def __init__(self):
        #mandatory field
        self.identityZoneUuid = NotNoneField()
        self.vSwitchId = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISYNCECSVPCFROMREMOTEMSG_FULL_NAME = 'org.zstack.header.aliyun.network.vpc.APISyncEcsVpcFromRemoteMsg'
class APISyncEcsVpcFromRemoteMsg(object):
    FULL_NAME='org.zstack.header.aliyun.network.vpc.APISyncEcsVpcFromRemoteMsg'
    def __init__(self):
        #mandatory field
        self.dataCenterUuid = NotNoneField()
        self.ecsVpcId = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIADDOSSFILEBUCKETNAMEMSG_FULL_NAME = 'org.zstack.header.aliyun.oss.APIAddOssFileBucketNameMsg'
class APIAddOssFileBucketNameMsg(object):
    FULL_NAME='org.zstack.header.aliyun.oss.APIAddOssFileBucketNameMsg'
    def __init__(self):
        #mandatory field
        self.ossBucketName = NotNoneField()
        #mandatory field
        self.regionId = NotNoneField()
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIATTACHOSSBUCKETTOECSDATACENTERMSG_FULL_NAME = 'org.zstack.header.aliyun.oss.APIAttachOssBucketToEcsDataCenterMsg'
class APIAttachOssBucketToEcsDataCenterMsg(object):
    FULL_NAME='org.zstack.header.aliyun.oss.APIAttachOssBucketToEcsDataCenterMsg'
    def __init__(self):
        #mandatory field
        self.ossBucketUuid = NotNoneField()
        #mandatory field
        self.dataCenterUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEOSSFILEBUCKETNAMEINLOCALMSG_FULL_NAME = 'org.zstack.header.aliyun.oss.APIDeleteOssFileBucketNameInLocalMsg'
class APIDeleteOssFileBucketNameInLocalMsg(object):
    FULL_NAME='org.zstack.header.aliyun.oss.APIDeleteOssFileBucketNameInLocalMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDETACHOSSBUCKETTOECSDATACENTERMSG_FULL_NAME = 'org.zstack.header.aliyun.oss.APIDetachOssBucketToEcsDataCenterMsg'
class APIDetachOssBucketToEcsDataCenterMsg(object):
    FULL_NAME='org.zstack.header.aliyun.oss.APIDetachOssBucketToEcsDataCenterMsg'
    def __init__(self):
        #mandatory field
        self.ossBucketUuid = NotNoneField()
        #mandatory field
        self.dataCenterUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETOSSBUCKETNAMEFROMREMOTEMSG_FULL_NAME = 'org.zstack.header.aliyun.oss.APIGetOssBucketNameFromRemoteMsg'
class APIGetOssBucketNameFromRemoteMsg(object):
    FULL_NAME='org.zstack.header.aliyun.oss.APIGetOssBucketNameFromRemoteMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETOSSBUCKETNAMEFROMREMOTEREPLY_FULL_NAME = 'org.zstack.header.aliyun.oss.APIGetOssBucketNameFromRemoteReply'
class APIGetOssBucketNameFromRemoteReply(object):
    FULL_NAME='org.zstack.header.aliyun.oss.APIGetOssBucketNameFromRemoteReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYOSSBUCKETFILENAMEMSG_FULL_NAME = 'org.zstack.header.aliyun.oss.APIQueryOssBucketFileNameMsg'
class APIQueryOssBucketFileNameMsg(object):
    FULL_NAME='org.zstack.header.aliyun.oss.APIQueryOssBucketFileNameMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYOSSBUCKETFILENAMEREPLY_FULL_NAME = 'org.zstack.header.aliyun.oss.APIQueryOssBucketFileNameReply'
class APIQueryOssBucketFileNameReply(object):
    FULL_NAME='org.zstack.header.aliyun.oss.APIQueryOssBucketFileNameReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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


APIGETHOSTALLOCATORSTRATEGIESMSG_FULL_NAME = 'org.zstack.header.allocator.APIGetHostAllocatorStrategiesMsg'
class APIGetHostAllocatorStrategiesMsg(object):
    FULL_NAME='org.zstack.header.allocator.APIGetHostAllocatorStrategiesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETHOSTALLOCATORSTRATEGIESREPLY_FULL_NAME = 'org.zstack.header.allocator.APIGetHostAllocatorStrategiesReply'
class APIGetHostAllocatorStrategiesReply(object):
    FULL_NAME='org.zstack.header.allocator.APIGetHostAllocatorStrategiesReply'
    def __init__(self):
        self.hostAllocatorStrategies = OptionalList()
        self.success = None
        self.error = None


APIISREADYTOGOMSG_FULL_NAME = 'org.zstack.header.apimediator.APIIsReadyToGoMsg'
class APIIsReadyToGoMsg(object):
    FULL_NAME='org.zstack.header.apimediator.APIIsReadyToGoMsg'
    def __init__(self):
        self.managementNodeId = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIISREADYTOGOREPLY_FULL_NAME = 'org.zstack.header.apimediator.APIIsReadyToGoReply'
class APIIsReadyToGoReply(object):
    FULL_NAME='org.zstack.header.apimediator.APIIsReadyToGoReply'
    def __init__(self):
        self.managementNodeId = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETECLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APIDeleteClusterMsg'
class APIDeleteClusterMsg(object):
    FULL_NAME='org.zstack.header.cluster.APIDeleteClusterMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APIGetClusterReply'
class APIGetClusterReply(object):
    FULL_NAME='org.zstack.header.cluster.APIGetClusterReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APILISTCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APIListClusterReply'
class APIListClusterReply(object):
    FULL_NAME='org.zstack.header.cluster.APIListClusterReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYCLUSTERMSG_FULL_NAME = 'org.zstack.header.cluster.APIQueryClusterMsg'
class APIQueryClusterMsg(object):
    FULL_NAME='org.zstack.header.cluster.APIQueryClusterMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APIQueryClusterReply'
class APIQueryClusterReply(object):
    FULL_NAME='org.zstack.header.cluster.APIQueryClusterReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APISEARCHCLUSTERREPLY_FULL_NAME = 'org.zstack.header.cluster.APISearchClusterReply'
class APISearchClusterReply(object):
    FULL_NAME='org.zstack.header.cluster.APISearchClusterReply'
    def __init__(self):
        self.content = None
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.memorySize = NotNoneField()
        self.allocatorStrategy = None
        self.sortKey = None
        self.type = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIDeleteDiskOfferingMsg'
class APIDeleteDiskOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIDeleteDiskOfferingMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIDeleteInstanceOfferingMsg'
class APIDeleteInstanceOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIDeleteInstanceOfferingMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGENERATEAPIJSONTEMPLATEMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateApiJsonTemplateMsg'
class APIGenerateApiJsonTemplateMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateApiJsonTemplateMsg'
    def __init__(self):
        self.exportPath = None
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGENERATEAPITYPESCRIPTDEFINITIONMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateApiTypeScriptDefinitionMsg'
class APIGenerateApiTypeScriptDefinitionMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateApiTypeScriptDefinitionMsg'
    def __init__(self):
        self.outputPath = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGENERATEGROOVYCLASSMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateGroovyClassMsg'
class APIGenerateGroovyClassMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateGroovyClassMsg'
    def __init__(self):
        self.outputPath = None
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGENERATESQLFOREIGNKEYMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateSqlForeignKeyMsg'
class APIGenerateSqlForeignKeyMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateSqlForeignKeyMsg'
    def __init__(self):
        self.outputPath = None
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGENERATESQLINDEXMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateSqlIndexMsg'
class APIGenerateSqlIndexMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateSqlIndexMsg'
    def __init__(self):
        self.outputPath = None
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGENERATESQLVOVIEWMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateSqlVOViewMsg'
class APIGenerateSqlVOViewMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateSqlVOViewMsg'
    def __init__(self):
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGENERATETESTLINKDOCUMENTMSG_FULL_NAME = 'org.zstack.header.configuration.APIGenerateTestLinkDocumentMsg'
class APIGenerateTestLinkDocumentMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGenerateTestLinkDocumentMsg'
    def __init__(self):
        self.outputDir = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIGetDiskOfferingReply'
class APIGetDiskOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIGetDiskOfferingReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETGLOBALPROPERTYMSG_FULL_NAME = 'org.zstack.header.configuration.APIGetGlobalPropertyMsg'
class APIGetGlobalPropertyMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIGetGlobalPropertyMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETGLOBALPROPERTYREPLY_FULL_NAME = 'org.zstack.header.configuration.APIGetGlobalPropertyReply'
class APIGetGlobalPropertyReply(object):
    FULL_NAME='org.zstack.header.configuration.APIGetGlobalPropertyReply'
    def __init__(self):
        self.properties = OptionalList()
        self.success = None
        self.error = None


APIGETINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIGetInstanceOfferingReply'
class APIGetInstanceOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIGetInstanceOfferingReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APILISTDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIListDiskOfferingReply'
class APIListDiskOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIListDiskOfferingReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APILISTINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIListInstanceOfferingReply'
class APIListInstanceOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIListInstanceOfferingReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYDISKOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIQueryDiskOfferingMsg'
class APIQueryDiskOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIQueryDiskOfferingMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIQueryDiskOfferingReply'
class APIQueryDiskOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIQueryDiskOfferingReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYINSTANCEOFFERINGMSG_FULL_NAME = 'org.zstack.header.configuration.APIQueryInstanceOfferingMsg'
class APIQueryInstanceOfferingMsg(object):
    FULL_NAME='org.zstack.header.configuration.APIQueryInstanceOfferingMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APIQueryInstanceOfferingReply'
class APIQueryInstanceOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APIQueryInstanceOfferingReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APISEARCHDISKOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APISearchDiskOfferingReply'
class APISearchDiskOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APISearchDiskOfferingReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISEARCHDNSREPLY_FULL_NAME = 'org.zstack.header.configuration.APISearchDnsReply'
class APISearchDnsReply(object):
    FULL_NAME='org.zstack.header.configuration.APISearchDnsReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISEARCHINSTANCEOFFERINGREPLY_FULL_NAME = 'org.zstack.header.configuration.APISearchInstanceOfferingReply'
class APISearchInstanceOfferingReply(object):
    FULL_NAME='org.zstack.header.configuration.APISearchInstanceOfferingReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYCONSOLEPROXYAGENTMSG_FULL_NAME = 'org.zstack.header.console.APIQueryConsoleProxyAgentMsg'
class APIQueryConsoleProxyAgentMsg(object):
    FULL_NAME='org.zstack.header.console.APIQueryConsoleProxyAgentMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYCONSOLEPROXYAGENTREPLY_FULL_NAME = 'org.zstack.header.console.APIQueryConsoleProxyAgentReply'
class APIQueryConsoleProxyAgentReply(object):
    FULL_NAME='org.zstack.header.console.APIQueryConsoleProxyAgentReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIRECONNECTCONSOLEPROXYAGENTMSG_FULL_NAME = 'org.zstack.header.console.APIReconnectConsoleProxyAgentMsg'
class APIReconnectConsoleProxyAgentMsg(object):
    FULL_NAME='org.zstack.header.console.APIReconnectConsoleProxyAgentMsg'
    def __init__(self):
        self.agentUuids = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIREQUESTCONSOLEACCESSMSG_FULL_NAME = 'org.zstack.header.console.APIRequestConsoleAccessMsg'
class APIRequestConsoleAccessMsg(object):
    FULL_NAME='org.zstack.header.console.APIRequestConsoleAccessMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIUPDATEENCRYPTKEYMSG_FULL_NAME = 'org.zstack.header.core.encrypt.APIUpdateEncryptKeyMsg'
class APIUpdateEncryptKeyMsg(object):
    FULL_NAME='org.zstack.header.core.encrypt.APIUpdateEncryptKeyMsg'
    def __init__(self):
        #mandatory field
        self.encryptKey = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETTASKPROGRESSMSG_FULL_NAME = 'org.zstack.header.core.progress.APIGetTaskProgressMsg'
class APIGetTaskProgressMsg(object):
    FULL_NAME='org.zstack.header.core.progress.APIGetTaskProgressMsg'
    def __init__(self):
        self.apiId = None
        self.all = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETTASKPROGRESSREPLY_FULL_NAME = 'org.zstack.header.core.progress.APIGetTaskProgressReply'
class APIGetTaskProgressReply(object):
    FULL_NAME='org.zstack.header.core.progress.APIGetTaskProgressReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APICREATESCHEDULERMESSAGE_FULL_NAME = 'org.zstack.header.core.scheduler.APICreateSchedulerMessage'
class APICreateSchedulerMessage(object):
    FULL_NAME='org.zstack.header.core.scheduler.APICreateSchedulerMessage'
    def __init__(self):
        #mandatory field
        self.schedulerName = NotNoneField()
        self.schedulerDescription = None
        #mandatory field
        #valid values: [simple, cron]
        self.type = NotNoneField()
        self.interval = None
        self.repeatCount = None
        self.startTime = None
        self.cron = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIADDDATACENTERFROMREMOTEMSG_FULL_NAME = 'org.zstack.header.datacenter.APIAddDataCenterFromRemoteMsg'
class APIAddDataCenterFromRemoteMsg(object):
    FULL_NAME='org.zstack.header.datacenter.APIAddDataCenterFromRemoteMsg'
    def __init__(self):
        #mandatory field
        self.regionId = NotNoneField()
        #mandatory field
        #valid values: [aliyun]
        self.type = NotNoneField()
        self.description = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEDATACENTERINLOCALMSG_FULL_NAME = 'org.zstack.header.datacenter.APIDeleteDataCenterInLocalMsg'
class APIDeleteDataCenterInLocalMsg(object):
    FULL_NAME='org.zstack.header.datacenter.APIDeleteDataCenterInLocalMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETDATACENTERFROMREMOTEMSG_FULL_NAME = 'org.zstack.header.datacenter.APIGetDataCenterFromRemoteMsg'
class APIGetDataCenterFromRemoteMsg(object):
    FULL_NAME='org.zstack.header.datacenter.APIGetDataCenterFromRemoteMsg'
    def __init__(self):
        #mandatory field
        #valid values: [aliyun]
        self.type = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETDATACENTERFROMREMOTEREPLY_FULL_NAME = 'org.zstack.header.datacenter.APIGetDataCenterFromRemoteReply'
class APIGetDataCenterFromRemoteReply(object):
    FULL_NAME='org.zstack.header.datacenter.APIGetDataCenterFromRemoteReply'
    def __init__(self):
        self.dataCenterList = OptionalList()
        self.success = None
        self.error = None


APIQUERYDATACENTERFROMLOCALMSG_FULL_NAME = 'org.zstack.header.datacenter.APIQueryDataCenterFromLocalMsg'
class APIQueryDataCenterFromLocalMsg(object):
    FULL_NAME='org.zstack.header.datacenter.APIQueryDataCenterFromLocalMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYDATACENTERFROMLOCALREPLY_FULL_NAME = 'org.zstack.header.datacenter.APIQueryDataCenterFromLocalReply'
class APIQueryDataCenterFromLocalReply(object):
    FULL_NAME='org.zstack.header.datacenter.APIQueryDataCenterFromLocalReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIDeleteHostMsg'
class APIDeleteHostMsg(object):
    FULL_NAME='org.zstack.header.host.APIDeleteHostMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APIGetHostReply'
class APIGetHostReply(object):
    FULL_NAME='org.zstack.header.host.APIGetHostReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETHYPERVISORTYPESMSG_FULL_NAME = 'org.zstack.header.host.APIGetHypervisorTypesMsg'
class APIGetHypervisorTypesMsg(object):
    FULL_NAME='org.zstack.header.host.APIGetHypervisorTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETHYPERVISORTYPESREPLY_FULL_NAME = 'org.zstack.header.host.APIGetHypervisorTypesReply'
class APIGetHypervisorTypesReply(object):
    FULL_NAME='org.zstack.header.host.APIGetHypervisorTypesReply'
    def __init__(self):
        self.hypervisorTypes = OptionalList()
        self.success = None
        self.error = None


APILISTHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APIListHostReply'
class APIListHostReply(object):
    FULL_NAME='org.zstack.header.host.APIListHostReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIQueryHostMsg'
class APIQueryHostMsg(object):
    FULL_NAME='org.zstack.header.host.APIQueryHostMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APIQueryHostReply'
class APIQueryHostReply(object):
    FULL_NAME='org.zstack.header.host.APIQueryHostReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIRECONNECTHOSTMSG_FULL_NAME = 'org.zstack.header.host.APIReconnectHostMsg'
class APIReconnectHostMsg(object):
    FULL_NAME='org.zstack.header.host.APIReconnectHostMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHHOSTREPLY_FULL_NAME = 'org.zstack.header.host.APISearchHostReply'
class APISearchHostReply(object):
    FULL_NAME='org.zstack.header.host.APISearchHostReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYHYBRIDEIPFROMLOCALMSG_FULL_NAME = 'org.zstack.header.hybrid.network.eip.APIQueryHybridEipFromLocalMsg'
class APIQueryHybridEipFromLocalMsg(object):
    FULL_NAME='org.zstack.header.hybrid.network.eip.APIQueryHybridEipFromLocalMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYHYBRIDEIPFROMLOCALREPLY_FULL_NAME = 'org.zstack.header.hybrid.network.eip.APIQueryHybridEipFromLocalReply'
class APIQueryHybridEipFromLocalReply(object):
    FULL_NAME='org.zstack.header.hybrid.network.eip.APIQueryHybridEipFromLocalReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICHECKAPIPERMISSIONMSG_FULL_NAME = 'org.zstack.header.identity.APICheckApiPermissionMsg'
class APICheckApiPermissionMsg(object):
    FULL_NAME='org.zstack.header.identity.APICheckApiPermissionMsg'
    def __init__(self):
        self.userUuid = None
        #mandatory field
        self.apiNames = NotNoneList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICHECKAPIPERMISSIONREPLY_FULL_NAME = 'org.zstack.header.identity.APICheckApiPermissionReply'
class APICheckApiPermissionReply(object):
    FULL_NAME='org.zstack.header.identity.APICheckApiPermissionReply'
    def __init__(self):
        self.inventory = OptionalMap()
        self.success = None
        self.error = None


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATEUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APICreateUserGroupMsg'
class APICreateUserGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APICreateUserGroupMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APIDeleteAccountMsg'
class APIDeleteAccountMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDeleteAccountMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APIDeletePolicyMsg'
class APIDeletePolicyMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDeletePolicyMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIDeleteUserGroupMsg'
class APIDeleteUserGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDeleteUserGroupMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEUSERMSG_FULL_NAME = 'org.zstack.header.identity.APIDeleteUserMsg'
class APIDeleteUserMsg(object):
    FULL_NAME='org.zstack.header.identity.APIDeleteUserMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETACCOUNTQUOTAUSAGEMSG_FULL_NAME = 'org.zstack.header.identity.APIGetAccountQuotaUsageMsg'
class APIGetAccountQuotaUsageMsg(object):
    FULL_NAME='org.zstack.header.identity.APIGetAccountQuotaUsageMsg'
    def __init__(self):
        self.uuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETACCOUNTQUOTAUSAGEREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetAccountQuotaUsageReply'
class APIGetAccountQuotaUsageReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetAccountQuotaUsageReply'
    def __init__(self):
        self.usages = OptionalList()
        self.success = None
        self.error = None


APIGETACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetAccountReply'
class APIGetAccountReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetAccountReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetPolicyReply'
class APIGetPolicyReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetPolicyReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETRESOURCEACCOUNTMSG_FULL_NAME = 'org.zstack.header.identity.APIGetResourceAccountMsg'
class APIGetResourceAccountMsg(object):
    FULL_NAME='org.zstack.header.identity.APIGetResourceAccountMsg'
    def __init__(self):
        #mandatory field
        self.resourceUuids = NotNoneList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETRESOURCEACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetResourceAccountReply'
class APIGetResourceAccountReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetResourceAccountReply'
    def __init__(self):
        self.inventories = OptionalMap()
        self.success = None
        self.error = None


APIGETUSERGROUPREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetUserGroupReply'
class APIGetUserGroupReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetUserGroupReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APIGetUserReply'
class APIGetUserReply(object):
    FULL_NAME='org.zstack.header.identity.APIGetUserReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APILISTACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIListAccountReply'
class APIListAccountReply(object):
    FULL_NAME='org.zstack.header.identity.APIListAccountReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APILOGINREPLY_FULL_NAME = 'org.zstack.header.identity.APILogInReply'
class APILogInReply(object):
    FULL_NAME='org.zstack.header.identity.APILogInReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APILOGOUTMSG_FULL_NAME = 'org.zstack.header.identity.APILogOutMsg'
class APILogOutMsg(object):
    FULL_NAME='org.zstack.header.identity.APILogOutMsg'
    def __init__(self):
        self.sessionUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APILOGOUTREPLY_FULL_NAME = 'org.zstack.header.identity.APILogOutReply'
class APILogOutReply(object):
    FULL_NAME='org.zstack.header.identity.APILogOutReply'
    def __init__(self):
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryAccountReply'
class APIQueryAccountReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryAccountReply'
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYACCOUNTRESOURCEREFREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryAccountResourceRefReply'
class APIQueryAccountResourceRefReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryAccountResourceRefReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYPOLICYMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryPolicyMsg'
class APIQueryPolicyMsg(object):
    FULL_NAME='org.zstack.header.identity.APIQueryPolicyMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryPolicyReply'
class APIQueryPolicyReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryPolicyReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYQUOTAREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryQuotaReply'
class APIQueryQuotaReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryQuotaReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYSHAREDRESOURCEMSG_FULL_NAME = 'org.zstack.header.identity.APIQuerySharedResourceMsg'
class APIQuerySharedResourceMsg(object):
    FULL_NAME='org.zstack.header.identity.APIQuerySharedResourceMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYSHAREDRESOURCEREPLY_FULL_NAME = 'org.zstack.header.identity.APIQuerySharedResourceReply'
class APIQuerySharedResourceReply(object):
    FULL_NAME='org.zstack.header.identity.APIQuerySharedResourceReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYUSERGROUPMSG_FULL_NAME = 'org.zstack.header.identity.APIQueryUserGroupMsg'
class APIQueryUserGroupMsg(object):
    FULL_NAME='org.zstack.header.identity.APIQueryUserGroupMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYUSERGROUPREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryUserGroupReply'
class APIQueryUserGroupReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryUserGroupReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APIQueryUserReply'
class APIQueryUserReply(object):
    FULL_NAME='org.zstack.header.identity.APIQueryUserReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHACCOUNTREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchAccountReply'
class APISearchAccountReply(object):
    FULL_NAME='org.zstack.header.identity.APISearchAccountReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISEARCHPOLICYREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchPolicyReply'
class APISearchPolicyReply(object):
    FULL_NAME='org.zstack.header.identity.APISearchPolicyReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISEARCHUSERGROUPREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchUserGroupReply'
class APISearchUserGroupReply(object):
    FULL_NAME='org.zstack.header.identity.APISearchUserGroupReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISEARCHUSERREPLY_FULL_NAME = 'org.zstack.header.identity.APISearchUserReply'
class APISearchUserReply(object):
    FULL_NAME='org.zstack.header.identity.APISearchUserReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISESSIONMESSAGE_FULL_NAME = 'org.zstack.header.identity.APISessionMessage'
class APISessionMessage(object):
    FULL_NAME='org.zstack.header.identity.APISessionMessage'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIVALIDATESESSIONMSG_FULL_NAME = 'org.zstack.header.identity.APIValidateSessionMsg'
class APIValidateSessionMsg(object):
    FULL_NAME='org.zstack.header.identity.APIValidateSessionMsg'
    def __init__(self):
        #mandatory field
        self.sessionUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIVALIDATESESSIONREPLY_FULL_NAME = 'org.zstack.header.identity.APIValidateSessionReply'
class APIValidateSessionReply(object):
    FULL_NAME='org.zstack.header.identity.APIValidateSessionReply'
    def __init__(self):
        self.validSession = None
        self.success = None
        self.error = None


APIADDIDENTITYZONEFROMREMOTEMSG_FULL_NAME = 'org.zstack.header.identityzone.APIAddIdentityZoneFromRemoteMsg'
class APIAddIdentityZoneFromRemoteMsg(object):
    FULL_NAME='org.zstack.header.identityzone.APIAddIdentityZoneFromRemoteMsg'
    def __init__(self):
        #mandatory field
        self.dataCenterUuid = NotNoneField()
        self.zoneId = None
        #mandatory field
        #valid values: [aliyun]
        self.type = NotNoneField()
        self.description = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEIDENTITYZONEINLOCALMSG_FULL_NAME = 'org.zstack.header.identityzone.APIDeleteIdentityZoneInLocalMsg'
class APIDeleteIdentityZoneInLocalMsg(object):
    FULL_NAME='org.zstack.header.identityzone.APIDeleteIdentityZoneInLocalMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETIDENTITYZONEFROMREMOTEMSG_FULL_NAME = 'org.zstack.header.identityzone.APIGetIdentityZoneFromRemoteMsg'
class APIGetIdentityZoneFromRemoteMsg(object):
    FULL_NAME='org.zstack.header.identityzone.APIGetIdentityZoneFromRemoteMsg'
    def __init__(self):
        #mandatory field
        #valid values: [aliyun]
        self.type = NotNoneField()
        self.dataCenterUuid = None
        self.regionId = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETIDENTITYZONEFROMREMOTEREPLY_FULL_NAME = 'org.zstack.header.identityzone.APIGetIdentityZoneFromRemoteReply'
class APIGetIdentityZoneFromRemoteReply(object):
    FULL_NAME='org.zstack.header.identityzone.APIGetIdentityZoneFromRemoteReply'
    def __init__(self):
        self.identityZoneList = OptionalList()
        self.success = None
        self.error = None


APIQUERYIDENTITYZONEFROMLOCALMSG_FULL_NAME = 'org.zstack.header.identityzone.APIQueryIdentityZoneFromLocalMsg'
class APIQueryIdentityZoneFromLocalMsg(object):
    FULL_NAME='org.zstack.header.identityzone.APIQueryIdentityZoneFromLocalMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYIDENTITYZONEFROMLOCALREPLY_FULL_NAME = 'org.zstack.header.identityzone.APIQueryIdentityZoneFromLocalReply'
class APIQueryIdentityZoneFromLocalReply(object):
    FULL_NAME='org.zstack.header.identityzone.APIQueryIdentityZoneFromLocalReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        #mandatory field
        self.backupStorageUuids = NotNoneList()
        #valid values: [Linux, Windows, Other, Paravirtualization, WindowsVirtio]
        self.platform = None
        self.system = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIEXPUNGEIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIExpungeImageMsg'
class APIExpungeImageMsg(object):
    FULL_NAME='org.zstack.header.image.APIExpungeImageMsg'
    def __init__(self):
        #mandatory field
        self.imageUuid = NotNoneField()
        self.backupStorageUuids = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCANDIDATEBACKUPSTORAGEFORCREATINGIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIGetCandidateBackupStorageForCreatingImageMsg'
class APIGetCandidateBackupStorageForCreatingImageMsg(object):
    FULL_NAME='org.zstack.header.image.APIGetCandidateBackupStorageForCreatingImageMsg'
    def __init__(self):
        self.volumeUuid = None
        self.volumeSnapshotUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCANDIDATEBACKUPSTORAGEFORCREATINGIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIGetCandidateBackupStorageForCreatingImageReply'
class APIGetCandidateBackupStorageForCreatingImageReply(object):
    FULL_NAME='org.zstack.header.image.APIGetCandidateBackupStorageForCreatingImageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETIMAGEQGAMSG_FULL_NAME = 'org.zstack.header.image.APIGetImageQgaMsg'
class APIGetImageQgaMsg(object):
    FULL_NAME='org.zstack.header.image.APIGetImageQgaMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETIMAGEQGAREPLY_FULL_NAME = 'org.zstack.header.image.APIGetImageQgaReply'
class APIGetImageQgaReply(object):
    FULL_NAME='org.zstack.header.image.APIGetImageQgaReply'
    def __init__(self):
        self.uuid = None
        self.enable = None
        self.success = None
        self.error = None


APIGETIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIGetImageReply'
class APIGetImageReply(object):
    FULL_NAME='org.zstack.header.image.APIGetImageReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APILISTIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIListImageReply'
class APIListImageReply(object):
    FULL_NAME='org.zstack.header.image.APIListImageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIQueryImageMsg'
class APIQueryImageMsg(object):
    FULL_NAME='org.zstack.header.image.APIQueryImageMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APIQueryImageReply'
class APIQueryImageReply(object):
    FULL_NAME='org.zstack.header.image.APIQueryImageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIRECOVERIMAGEMSG_FULL_NAME = 'org.zstack.header.image.APIRecoverImageMsg'
class APIRecoverImageMsg(object):
    FULL_NAME='org.zstack.header.image.APIRecoverImageMsg'
    def __init__(self):
        #mandatory field
        self.imageUuid = NotNoneField()
        self.backupStorageUuids = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHIMAGEREPLY_FULL_NAME = 'org.zstack.header.image.APISearchImageReply'
class APISearchImageReply(object):
    FULL_NAME='org.zstack.header.image.APISearchImageReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISETIMAGEQGAMSG_FULL_NAME = 'org.zstack.header.image.APISetImageQgaMsg'
class APISetImageQgaMsg(object):
    FULL_NAME='org.zstack.header.image.APISetImageQgaMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.enable = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISYNCIMAGESIZEMSG_FULL_NAME = 'org.zstack.header.image.APISyncImageSizeMsg'
class APISyncImageSizeMsg(object):
    FULL_NAME='org.zstack.header.image.APISyncImageSizeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCURRENTTIMEMSG_FULL_NAME = 'org.zstack.header.managementnode.APIGetCurrentTimeMsg'
class APIGetCurrentTimeMsg(object):
    FULL_NAME='org.zstack.header.managementnode.APIGetCurrentTimeMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCURRENTTIMEREPLY_FULL_NAME = 'org.zstack.header.managementnode.APIGetCurrentTimeReply'
class APIGetCurrentTimeReply(object):
    FULL_NAME='org.zstack.header.managementnode.APIGetCurrentTimeReply'
    def __init__(self):
        self.currentTime = OptionalMap()
        self.success = None
        self.error = None


APIGETVERSIONMSG_FULL_NAME = 'org.zstack.header.managementnode.APIGetVersionMsg'
class APIGetVersionMsg(object):
    FULL_NAME='org.zstack.header.managementnode.APIGetVersionMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYMANAGEMENTNODEREPLY_FULL_NAME = 'org.zstack.header.managementnode.APIQueryManagementNodeReply'
class APIQueryManagementNodeReply(object):
    FULL_NAME='org.zstack.header.managementnode.APIQueryManagementNodeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APICREATEMESSAGE_FULL_NAME = 'org.zstack.header.message.APICreateMessage'
class APICreateMessage(object):
    FULL_NAME='org.zstack.header.message.APICreateMessage'
    def __init__(self):
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIREPLY_FULL_NAME = 'org.zstack.header.message.APIReply'
class APIReply(object):
    FULL_NAME='org.zstack.header.message.APIReply'
    def __init__(self):
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEL2NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l2.APIDeleteL2NetworkMsg'
class APIDeleteL2NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APIDeleteL2NetworkMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2NetworkReply'
class APIGetL2NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2NetworkReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETL2NETWORKTYPESMSG_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2NetworkTypesMsg'
class APIGetL2NetworkTypesMsg(object):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2NetworkTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETL2NETWORKTYPESREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2NetworkTypesReply'
class APIGetL2NetworkTypesReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2NetworkTypesReply'
    def __init__(self):
        self.l2NetworkTypes = OptionalList()
        self.success = None
        self.error = None


APIGETL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIGetL2VlanNetworkReply'
class APIGetL2VlanNetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIGetL2VlanNetworkReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APILISTL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIListL2NetworkReply'
class APIListL2NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIListL2NetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APILISTL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIListL2VlanNetworkReply'
class APIListL2VlanNetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIListL2VlanNetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIQueryL2NetworkReply'
class APIQueryL2NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIQueryL2NetworkReply'
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APIQueryL2VlanNetworkReply'
class APIQueryL2VlanNetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APIQueryL2VlanNetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APISEARCHL2NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APISearchL2NetworkReply'
class APISearchL2NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APISearchL2NetworkReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISEARCHL2VLANNETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l2.APISearchL2VlanNetworkReply'
class APISearchL2VlanNetworkReply(object):
    FULL_NAME='org.zstack.header.network.l2.APISearchL2VlanNetworkReply'
    def __init__(self):
        self.content = None
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICHECKIPAVAILABILITYREPLY_FULL_NAME = 'org.zstack.header.network.l3.APICheckIpAvailabilityReply'
class APICheckIpAvailabilityReply(object):
    FULL_NAME='org.zstack.header.network.l3.APICheckIpAvailabilityReply'
    def __init__(self):
        self.available = None
        self.success = None
        self.error = None


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIDeleteIpRangeMsg'
class APIDeleteIpRangeMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIDeleteIpRangeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.network.l3.APIDeleteL3NetworkMsg'
class APIDeleteL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIDeleteL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETFREEIPMSG_FULL_NAME = 'org.zstack.header.network.l3.APIGetFreeIpMsg'
class APIGetFreeIpMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetFreeIpMsg'
    def __init__(self):
        self.l3NetworkUuid = None
        self.ipRangeUuid = None
        self.start = None
        self.limit = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETFREEIPREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetFreeIpReply'
class APIGetFreeIpReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetFreeIpReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETIPADDRESSCAPACITYREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetIpAddressCapacityReply'
class APIGetIpAddressCapacityReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetIpAddressCapacityReply'
    def __init__(self):
        self.totalCapacity = None
        self.availableCapacity = None
        self.success = None
        self.error = None


APIGETL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetL3NetworkReply'
class APIGetL3NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetL3NetworkReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETL3NETWORKTYPESMSG_FULL_NAME = 'org.zstack.header.network.l3.APIGetL3NetworkTypesMsg'
class APIGetL3NetworkTypesMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetL3NetworkTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETL3NETWORKTYPESREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIGetL3NetworkTypesReply'
class APIGetL3NetworkTypesReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIGetL3NetworkTypesReply'
    def __init__(self):
        self.l3NetworkTypes = OptionalList()
        self.success = None
        self.error = None


APILISTIPRANGEREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIListIpRangeReply'
class APIListIpRangeReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIListIpRangeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APILISTL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIListL3NetworkReply'
class APIListL3NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIListL3NetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYIPRANGEMSG_FULL_NAME = 'org.zstack.header.network.l3.APIQueryIpRangeMsg'
class APIQueryIpRangeMsg(object):
    FULL_NAME='org.zstack.header.network.l3.APIQueryIpRangeMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYIPRANGEREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIQueryIpRangeReply'
class APIQueryIpRangeReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIQueryIpRangeReply'
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APIQueryL3NetworkReply'
class APIQueryL3NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l3.APIQueryL3NetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.network.l3.APISearchL3NetworkReply'
class APISearchL3NetworkReply(object):
    FULL_NAME='org.zstack.header.network.l3.APISearchL3NetworkReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APIGetNetworkServiceProviderReply'
class APIGetNetworkServiceProviderReply(object):
    FULL_NAME='org.zstack.header.network.service.APIGetNetworkServiceProviderReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETNETWORKSERVICETYPESMSG_FULL_NAME = 'org.zstack.header.network.service.APIGetNetworkServiceTypesMsg'
class APIGetNetworkServiceTypesMsg(object):
    FULL_NAME='org.zstack.header.network.service.APIGetNetworkServiceTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETNETWORKSERVICETYPESREPLY_FULL_NAME = 'org.zstack.header.network.service.APIGetNetworkServiceTypesReply'
class APIGetNetworkServiceTypesReply(object):
    FULL_NAME='org.zstack.header.network.service.APIGetNetworkServiceTypesReply'
    def __init__(self):
        self.serviceAndProviderTypes = OptionalMap()
        self.success = None
        self.error = None


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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYNETWORKSERVICEL3NETWORKREFREPLY_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceL3NetworkRefReply'
class APIQueryNetworkServiceL3NetworkRefReply(object):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceL3NetworkRefReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYNETWORKSERVICEPROVIDERMSG_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceProviderMsg'
class APIQueryNetworkServiceProviderMsg(object):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceProviderMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APIQueryNetworkServiceProviderReply'
class APIQueryNetworkServiceProviderReply(object):
    FULL_NAME='org.zstack.header.network.service.APIQueryNetworkServiceProviderReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APISEARCHNETWORKSERVICEPROVIDERREPLY_FULL_NAME = 'org.zstack.header.network.service.APISearchNetworkServiceProviderReply'
class APISearchNetworkServiceProviderReply(object):
    FULL_NAME='org.zstack.header.network.service.APISearchNetworkServiceProviderReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIGENERATEINVENTORYQUERYDETAILSMSG_FULL_NAME = 'org.zstack.header.query.APIGenerateInventoryQueryDetailsMsg'
class APIGenerateInventoryQueryDetailsMsg(object):
    FULL_NAME='org.zstack.header.query.APIGenerateInventoryQueryDetailsMsg'
    def __init__(self):
        self.outputDir = None
        self.basePackageNames = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGENERATEQUERYABLEFIELDSMSG_FULL_NAME = 'org.zstack.header.query.APIGenerateQueryableFieldsMsg'
class APIGenerateQueryableFieldsMsg(object):
    FULL_NAME='org.zstack.header.query.APIGenerateQueryableFieldsMsg'
    def __init__(self):
        self.PYTHON_FORMAT = None
        self.format = None
        self.outputFolder = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYREPLY_FULL_NAME = 'org.zstack.header.query.APIQueryReply'
class APIQueryReply(object):
    FULL_NAME='org.zstack.header.query.APIQueryReply'
    def __init__(self):
        self.total = None
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETESEARCHINDEXMSG_FULL_NAME = 'org.zstack.header.search.APIDeleteSearchIndexMsg'
class APIDeleteSearchIndexMsg(object):
    FULL_NAME='org.zstack.header.search.APIDeleteSearchIndexMsg'
    def __init__(self):
        self.indexName = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHGENERATESQLTRIGGERMSG_FULL_NAME = 'org.zstack.header.search.APISearchGenerateSqlTriggerMsg'
class APISearchGenerateSqlTriggerMsg(object):
    FULL_NAME='org.zstack.header.search.APISearchGenerateSqlTriggerMsg'
    def __init__(self):
        self.resultPath = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHREPLY_FULL_NAME = 'org.zstack.header.search.APISearchReply'
class APISearchReply(object):
    FULL_NAME='org.zstack.header.search.APISearchReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.importImages = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIDeleteBackupStorageMsg'
class APIDeleteBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIDeleteBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEEXPORTEDIMAGEFROMBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIDeleteExportedImageFromBackupStorageMsg'
class APIDeleteExportedImageFromBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIDeleteExportedImageFromBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.backupStorageUuid = NotNoneField()
        #mandatory field
        self.imageUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIEXPORTIMAGEFROMBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIExportImageFromBackupStorageMsg'
class APIExportImageFromBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIExportImageFromBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.backupStorageUuid = NotNoneField()
        #mandatory field
        self.imageUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETBACKUPSTORAGECAPACITYMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageCapacityMsg'
class APIGetBackupStorageCapacityMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageCapacityMsg'
    def __init__(self):
        self.zoneUuids = OptionalList()
        self.backupStorageUuids = OptionalList()
        self.all = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETBACKUPSTORAGECAPACITYREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageCapacityReply'
class APIGetBackupStorageCapacityReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageCapacityReply'
    def __init__(self):
        self.totalCapacity = None
        self.availableCapacity = None
        self.success = None
        self.error = None


APIGETBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageReply'
class APIGetBackupStorageReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETBACKUPSTORAGETYPESMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageTypesMsg'
class APIGetBackupStorageTypesMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETBACKUPSTORAGETYPESREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIGetBackupStorageTypesReply'
class APIGetBackupStorageTypesReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APIGetBackupStorageTypesReply'
    def __init__(self):
        self.backupStorageTypes = OptionalList()
        self.success = None
        self.error = None


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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APIQueryBackupStorageReply'
class APIQueryBackupStorageReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APIQueryBackupStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIRECONNECTBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIReconnectBackupStorageMsg'
class APIReconnectBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIReconnectBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISCANBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.backup.APIScanBackupStorageMsg'
class APIScanBackupStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.backup.APIScanBackupStorageMsg'
    def __init__(self):
        self.backupStorageUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.backup.APISearchBackupStorageReply'
class APISearchBackupStorageReply(object):
    FULL_NAME='org.zstack.header.storage.backup.APISearchBackupStorageReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICHANGEPRIMARYSTORAGESTATEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIChangePrimaryStorageStateMsg'
class APIChangePrimaryStorageStateMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIChangePrimaryStorageStateMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [enable, disable, maintain, deleting]
        self.stateEvent = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICLEANUPIMAGECACHEONPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APICleanUpImageCacheOnPrimaryStorageMsg'
class APICleanUpImageCacheOnPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APICleanUpImageCacheOnPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICOMMITVOLUMEASIMAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APICommitVolumeAsImageMsg'
class APICommitVolumeAsImageMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APICommitVolumeAsImageMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.guestOsType = None
        #valid values: [Linux, Windows, Other, Paravirtualization, WindowsVirtio]
        self.platform = None
        self.system = None
        #mandatory field
        self.volumeUuid = NotNoneField()
        self.primaryStorageUuid = None
        #mandatory field
        self.backupStorageUuids = NotNoneList()
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIDeletePrimaryStorageMsg'
class APIDeletePrimaryStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIDeletePrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETPRIMARYSTORAGEALLOCATORSTRATEGIESMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesMsg'
class APIGetPrimaryStorageAllocatorStrategiesMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETPRIMARYSTORAGEALLOCATORSTRATEGIESREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesReply'
class APIGetPrimaryStorageAllocatorStrategiesReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageAllocatorStrategiesReply'
    def __init__(self):
        self.primaryStorageAllocatorStrategies = OptionalList()
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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


APIGETPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageReply'
class APIGetPrimaryStorageReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETPRIMARYSTORAGETYPESMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageTypesMsg'
class APIGetPrimaryStorageTypesMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageTypesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETPRIMARYSTORAGETYPESREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIGetPrimaryStorageTypesReply'
class APIGetPrimaryStorageTypesReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIGetPrimaryStorageTypesReply'
    def __init__(self):
        self.primaryStorageTypes = OptionalList()
        self.success = None
        self.error = None


APILISTPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIListPrimaryStorageReply'
class APIListPrimaryStorageReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIListPrimaryStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIQueryPrimaryStorageMsg'
class APIQueryPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIQueryPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APIQueryPrimaryStorageReply'
class APIQueryPrimaryStorageReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APIQueryPrimaryStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIRECONNECTPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIReconnectPrimaryStorageMsg'
class APIReconnectPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIReconnectPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.APISearchPrimaryStorageReply'
class APISearchPrimaryStorageReply(object):
    FULL_NAME='org.zstack.header.storage.primary.APISearchPrimaryStorageReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISYNCPRIMARYSTORAGECAPACITYMSG_FULL_NAME = 'org.zstack.header.storage.primary.APISyncPrimaryStorageCapacityMsg'
class APISyncPrimaryStorageCapacityMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APISyncPrimaryStorageCapacityMsg'
    def __init__(self):
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIUPDATEPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.header.storage.primary.APIUpdatePrimaryStorageMsg'
class APIUpdatePrimaryStorageMsg(object):
    FULL_NAME='org.zstack.header.storage.primary.APIUpdatePrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.url = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


CREATETEMPLATEFROMVOLUMEONPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.header.storage.primary.CreateTemplateFromVolumeOnPrimaryStorageReply'
class CreateTemplateFromVolumeOnPrimaryStorageReply(object):
    FULL_NAME='org.zstack.header.storage.primary.CreateTemplateFromVolumeOnPrimaryStorageReply'
    def __init__(self):
        self.templateBackupStorageInstallPath = None
        self.format = None
        self.success = None
        self.error = None


APIBACKUPVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIBackupVolumeSnapshotMsg'
class APIBackupVolumeSnapshotMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIBackupVolumeSnapshotMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.backupStorageUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotMsg'
class APIDeleteVolumeSnapshotMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIDeleteVolumeSnapshotMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVOLUMESNAPSHOTTREEMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeMsg'
class APIGetVolumeSnapshotTreeMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeMsg'
    def __init__(self):
        self.volumeUuid = None
        self.treeUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVOLUMESNAPSHOTTREEREPLY_FULL_NAME = 'org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeReply'
class APIGetVolumeSnapshotTreeReply(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIGetVolumeSnapshotTreeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYVOLUMESNAPSHOTMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotMsg'
class APIQueryVolumeSnapshotMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVOLUMESNAPSHOTREPLY_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotReply'
class APIQueryVolumeSnapshotReply(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYVOLUMESNAPSHOTTREEMSG_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeMsg'
class APIQueryVolumeSnapshotTreeMsg(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVOLUMESNAPSHOTTREEREPLY_FULL_NAME = 'org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeReply'
class APIQueryVolumeSnapshotTreeReply(object):
    FULL_NAME='org.zstack.header.storage.snapshot.APIQueryVolumeSnapshotTreeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETETAGMSG_FULL_NAME = 'org.zstack.header.tag.APIDeleteTagMsg'
class APIDeleteTagMsg(object):
    FULL_NAME='org.zstack.header.tag.APIDeleteTagMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYSYSTEMTAGMSG_FULL_NAME = 'org.zstack.header.tag.APIQuerySystemTagMsg'
class APIQuerySystemTagMsg(object):
    FULL_NAME='org.zstack.header.tag.APIQuerySystemTagMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYSYSTEMTAGREPLY_FULL_NAME = 'org.zstack.header.tag.APIQuerySystemTagReply'
class APIQuerySystemTagReply(object):
    FULL_NAME='org.zstack.header.tag.APIQuerySystemTagReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYTAGREPLY_FULL_NAME = 'org.zstack.header.tag.APIQueryTagReply'
class APIQueryTagReply(object):
    FULL_NAME='org.zstack.header.tag.APIQueryTagReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYUSERTAGMSG_FULL_NAME = 'org.zstack.header.tag.APIQueryUserTagMsg'
class APIQueryUserTagMsg(object):
    FULL_NAME='org.zstack.header.tag.APIQueryUserTagMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYUSERTAGREPLY_FULL_NAME = 'org.zstack.header.tag.APIQueryUserTagReply'
class APIQueryUserTagReply(object):
    FULL_NAME='org.zstack.header.tag.APIQueryUserTagReply'
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIATTACHL3NETWORKTOVMMSG_FULL_NAME = 'org.zstack.header.vm.APIAttachL3NetworkToVmMsg'
class APIAttachL3NetworkToVmMsg(object):
    FULL_NAME='org.zstack.header.vm.APIAttachL3NetworkToVmMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        self.staticIp = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICHANGEVMPASSWORDMSG_FULL_NAME = 'org.zstack.header.vm.APIChangeVmPasswordMsg'
class APIChangeVmPasswordMsg(object):
    FULL_NAME='org.zstack.header.vm.APIChangeVmPasswordMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid regex values: [\da-zA-Z-`=\\\[\];',./~!@#$%^&*()_+|{}:"<>?]{1,}
        self.password = NotNoneField()
        #mandatory field
        self.account = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICLONEVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APICloneVmInstanceMsg'
class APICloneVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APICloneVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        #valid values: [InstantStart, JustCreate]
        self.strategy = None
        #mandatory field
        self.names = NotNoneList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATEREBOOTVMINSTANCESCHEDULERMSG_FULL_NAME = 'org.zstack.header.vm.APICreateRebootVmInstanceSchedulerMsg'
class APICreateRebootVmInstanceSchedulerMsg(object):
    FULL_NAME='org.zstack.header.vm.APICreateRebootVmInstanceSchedulerMsg'
    def __init__(self):
        #mandatory field
        self.vmUuid = NotNoneField()
        #mandatory field
        self.schedulerName = NotNoneField()
        self.schedulerDescription = None
        #mandatory field
        #valid values: [simple, cron]
        self.type = NotNoneField()
        self.interval = None
        self.repeatCount = None
        self.startTime = None
        self.cron = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATESTARTVMINSTANCESCHEDULERMSG_FULL_NAME = 'org.zstack.header.vm.APICreateStartVmInstanceSchedulerMsg'
class APICreateStartVmInstanceSchedulerMsg(object):
    FULL_NAME='org.zstack.header.vm.APICreateStartVmInstanceSchedulerMsg'
    def __init__(self):
        #mandatory field
        self.vmUuid = NotNoneField()
        self.clusterUuid = None
        self.hostUuid = None
        #mandatory field
        self.schedulerName = NotNoneField()
        self.schedulerDescription = None
        #mandatory field
        #valid values: [simple, cron]
        self.type = NotNoneField()
        self.interval = None
        self.repeatCount = None
        self.startTime = None
        self.cron = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATESTOPVMINSTANCESCHEDULERMSG_FULL_NAME = 'org.zstack.header.vm.APICreateStopVmInstanceSchedulerMsg'
class APICreateStopVmInstanceSchedulerMsg(object):
    FULL_NAME='org.zstack.header.vm.APICreateStopVmInstanceSchedulerMsg'
    def __init__(self):
        #mandatory field
        self.vmUuid = NotNoneField()
        #mandatory field
        self.schedulerName = NotNoneField()
        self.schedulerDescription = None
        #mandatory field
        #valid values: [simple, cron]
        self.type = NotNoneField()
        self.interval = None
        self.repeatCount = None
        self.startTime = None
        self.cron = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.primaryStorageUuidForRootVolume = None
        self.description = None
        self.defaultL3NetworkUuid = None
        #valid values: [InstantStart, JustCreate]
        self.strategy = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETENICQOSMSG_FULL_NAME = 'org.zstack.header.vm.APIDeleteNicQosMsg'
class APIDeleteNicQosMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDeleteNicQosMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        #valid values: [in, out]
        self.direction = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEVMCONSOLEPASSWORDMSG_FULL_NAME = 'org.zstack.header.vm.APIDeleteVmConsolePasswordMsg'
class APIDeleteVmConsolePasswordMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDeleteVmConsolePasswordMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEVMHOSTNAMEMSG_FULL_NAME = 'org.zstack.header.vm.APIDeleteVmHostnameMsg'
class APIDeleteVmHostnameMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDeleteVmHostnameMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEVMSSHKEYMSG_FULL_NAME = 'org.zstack.header.vm.APIDeleteVmSshKeyMsg'
class APIDeleteVmSshKeyMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDeleteVmSshKeyMsg'
    def __init__(self):
        self.uuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDESTROYVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIDestroyVmInstanceMsg'
class APIDestroyVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDestroyVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDETACHISOFROMVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIDetachIsoFromVmInstanceMsg'
class APIDetachIsoFromVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDetachIsoFromVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDETACHL3NETWORKFROMVMMSG_FULL_NAME = 'org.zstack.header.vm.APIDetachL3NetworkFromVmMsg'
class APIDetachL3NetworkFromVmMsg(object):
    FULL_NAME='org.zstack.header.vm.APIDetachL3NetworkFromVmMsg'
    def __init__(self):
        #mandatory field
        self.vmNicUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIEXPUNGEVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIExpungeVmInstanceMsg'
class APIExpungeVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIExpungeVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCANDIDATEISOFORATTACHINGVMMSG_FULL_NAME = 'org.zstack.header.vm.APIGetCandidateIsoForAttachingVmMsg'
class APIGetCandidateIsoForAttachingVmMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetCandidateIsoForAttachingVmMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCANDIDATEISOFORATTACHINGVMREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetCandidateIsoForAttachingVmReply'
class APIGetCandidateIsoForAttachingVmReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetCandidateIsoForAttachingVmReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETCANDIDATEVMFORATTACHINGISOMSG_FULL_NAME = 'org.zstack.header.vm.APIGetCandidateVmForAttachingIsoMsg'
class APIGetCandidateVmForAttachingIsoMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetCandidateVmForAttachingIsoMsg'
    def __init__(self):
        #mandatory field
        self.isoUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCANDIDATEVMFORATTACHINGISOREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetCandidateVmForAttachingIsoReply'
class APIGetCandidateVmForAttachingIsoReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetCandidateVmForAttachingIsoReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETCANDIDATEZONESCLUSTERSHOSTSFORCREATINGVMMSG_FULL_NAME = 'org.zstack.header.vm.APIGetCandidateZonesClustersHostsForCreatingVmMsg'
class APIGetCandidateZonesClustersHostsForCreatingVmMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetCandidateZonesClustersHostsForCreatingVmMsg'
    def __init__(self):
        #mandatory field
        self.instanceOfferingUuid = NotNoneField()
        #mandatory field
        self.imageUuid = NotNoneField()
        #mandatory field
        self.l3NetworkUuids = NotNoneList()
        self.rootDiskOfferingUuid = None
        self.dataDiskOfferingUuids = OptionalList()
        self.zoneUuid = None
        self.clusterUuid = None
        self.defaultL3NetworkUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCANDIDATEZONESCLUSTERSHOSTSFORCREATINGVMREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetCandidateZonesClustersHostsForCreatingVmReply'
class APIGetCandidateZonesClustersHostsForCreatingVmReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetCandidateZonesClustersHostsForCreatingVmReply'
    def __init__(self):
        self.zones = OptionalList()
        self.clusters = OptionalList()
        self.hosts = OptionalList()
        self.success = None
        self.error = None


APIGETINTERDEPENDENTL3NETWORKIMAGEREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetInterdependentL3NetworkImageReply'
class APIGetInterdependentL3NetworkImageReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetInterdependentL3NetworkImageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETINTERDEPENDENTL3NETWORKSIMAGESMSG_FULL_NAME = 'org.zstack.header.vm.APIGetInterdependentL3NetworksImagesMsg'
class APIGetInterdependentL3NetworksImagesMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetInterdependentL3NetworksImagesMsg'
    def __init__(self):
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.l3NetworkUuids = OptionalList()
        self.imageUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETNICQOSMSG_FULL_NAME = 'org.zstack.header.vm.APIGetNicQosMsg'
class APIGetNicQosMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetNicQosMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETNICQOSREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetNicQosReply'
class APIGetNicQosReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetNicQosReply'
    def __init__(self):
        self.outboundBandwidth = None
        self.inboundBandwidth = None
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMATTACHABLEDATAVOLUMEREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableDataVolumeReply'
class APIGetVmAttachableDataVolumeReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableDataVolumeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETVMATTACHABLEL3NETWORKMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableL3NetworkMsg'
class APIGetVmAttachableL3NetworkMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableL3NetworkMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMATTACHABLEL3NETWORKREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmAttachableL3NetworkReply'
class APIGetVmAttachableL3NetworkReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmAttachableL3NetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETVMBOOTORDERMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmBootOrderMsg'
class APIGetVmBootOrderMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmBootOrderMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMBOOTORDERREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmBootOrderReply'
class APIGetVmBootOrderReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmBootOrderReply'
    def __init__(self):
        self.order = OptionalList()
        self.success = None
        self.error = None


APIGETVMCAPABILITIESMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmCapabilitiesMsg'
class APIGetVmCapabilitiesMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmCapabilitiesMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMCAPABILITIESREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmCapabilitiesReply'
class APIGetVmCapabilitiesReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmCapabilitiesReply'
    def __init__(self):
        self.capabilities = OptionalMap()
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMCONSOLEADDRESSREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmConsoleAddressReply'
class APIGetVmConsoleAddressReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmConsoleAddressReply'
    def __init__(self):
        self.hostIp = None
        self.port = None
        self.protocol = None
        self.success = None
        self.error = None


APIGETVMCONSOLEPASSWORDMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmConsolePasswordMsg'
class APIGetVmConsolePasswordMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmConsolePasswordMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMCONSOLEPASSWORDREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmConsolePasswordReply'
class APIGetVmConsolePasswordReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmConsolePasswordReply'
    def __init__(self):
        self.consolePassword = None
        self.success = None
        self.error = None


APIGETVMHOSTNAMEMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmHostnameMsg'
class APIGetVmHostnameMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmHostnameMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMHOSTNAMEREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmHostnameReply'
class APIGetVmHostnameReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmHostnameReply'
    def __init__(self):
        self.hostname = None
        self.success = None
        self.error = None


APIGETVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmInstanceReply'
class APIGetVmInstanceReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmInstanceReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIGETVMMIGRATIONCANDIDATEHOSTSMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmMigrationCandidateHostsMsg'
class APIGetVmMigrationCandidateHostsMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmMigrationCandidateHostsMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMMIGRATIONCANDIDATEHOSTSREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmMigrationCandidateHostsReply'
class APIGetVmMigrationCandidateHostsReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmMigrationCandidateHostsReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETVMQGAMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmQgaMsg'
class APIGetVmQgaMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmQgaMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMQGAREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmQgaReply'
class APIGetVmQgaReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmQgaReply'
    def __init__(self):
        self.uuid = None
        self.enable = None
        self.success = None
        self.error = None


APIGETVMSSHKEYMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmSshKeyMsg'
class APIGetVmSshKeyMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmSshKeyMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMSSHKEYREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmSshKeyReply'
class APIGetVmSshKeyReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmSshKeyReply'
    def __init__(self):
        self.sshKey = None
        self.success = None
        self.error = None


APIGETVMSTARTINGCANDIDATECLUSTERSHOSTSMSG_FULL_NAME = 'org.zstack.header.vm.APIGetVmStartingCandidateClustersHostsMsg'
class APIGetVmStartingCandidateClustersHostsMsg(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmStartingCandidateClustersHostsMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMSTARTINGCANDIDATECLUSTERSHOSTSREPLY_FULL_NAME = 'org.zstack.header.vm.APIGetVmStartingCandidateClustersHostsReply'
class APIGetVmStartingCandidateClustersHostsReply(object):
    FULL_NAME='org.zstack.header.vm.APIGetVmStartingCandidateClustersHostsReply'
    def __init__(self):
        self.hostInventories = OptionalList()
        self.clusterInventories = OptionalList()
        self.success = None
        self.error = None


APILISTVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIListVmInstanceReply'
class APIListVmInstanceReply(object):
    FULL_NAME='org.zstack.header.vm.APIListVmInstanceReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APILISTVMNICREPLY_FULL_NAME = 'org.zstack.header.vm.APIListVmNicReply'
class APIListVmNicReply(object):
    FULL_NAME='org.zstack.header.vm.APIListVmNicReply'
    def __init__(self):
        self.inventories = OptionalList()
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIPAUSEVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIPauseVmInstanceMsg'
class APIPauseVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIPauseVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIQueryVmInstanceMsg'
class APIQueryVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIQueryVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APIQueryVmInstanceReply'
class APIQueryVmInstanceReply(object):
    FULL_NAME='org.zstack.header.vm.APIQueryVmInstanceReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVMNICREPLY_FULL_NAME = 'org.zstack.header.vm.APIQueryVmNicReply'
class APIQueryVmNicReply(object):
    FULL_NAME='org.zstack.header.vm.APIQueryVmNicReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIREBOOTVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIRebootVmInstanceMsg'
class APIRebootVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIRebootVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIRECOVERVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIRecoverVmInstanceMsg'
class APIRecoverVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIRecoverVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIREIMAGEVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIReimageVmInstanceMsg'
class APIReimageVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIReimageVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIRESUMEVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIResumeVmInstanceMsg'
class APIResumeVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIResumeVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHVMINSTANCEREPLY_FULL_NAME = 'org.zstack.header.vm.APISearchVmInstanceReply'
class APISearchVmInstanceReply(object):
    FULL_NAME='org.zstack.header.vm.APISearchVmInstanceReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISETNICQOSMSG_FULL_NAME = 'org.zstack.header.vm.APISetNicQosMsg'
class APISetNicQosMsg(object):
    FULL_NAME='org.zstack.header.vm.APISetNicQosMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.outboundBandwidth = None
        self.inboundBandwidth = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISETVMBOOTORDERMSG_FULL_NAME = 'org.zstack.header.vm.APISetVmBootOrderMsg'
class APISetVmBootOrderMsg(object):
    FULL_NAME='org.zstack.header.vm.APISetVmBootOrderMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.bootOrder = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISETVMCONSOLEPASSWORDMSG_FULL_NAME = 'org.zstack.header.vm.APISetVmConsolePasswordMsg'
class APISetVmConsolePasswordMsg(object):
    FULL_NAME='org.zstack.header.vm.APISetVmConsolePasswordMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.consolePassword = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISETVMQGAMSG_FULL_NAME = 'org.zstack.header.vm.APISetVmQgaMsg'
class APISetVmQgaMsg(object):
    FULL_NAME='org.zstack.header.vm.APISetVmQgaMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.enable = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISETVMSSHKEYMSG_FULL_NAME = 'org.zstack.header.vm.APISetVmSshKeyMsg'
class APISetVmSshKeyMsg(object):
    FULL_NAME='org.zstack.header.vm.APISetVmSshKeyMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.SshKey = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISTARTVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIStartVmInstanceMsg'
class APIStartVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIStartVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.clusterUuid = None
        self.hostUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISTOPVMINSTANCEMSG_FULL_NAME = 'org.zstack.header.vm.APIStopVmInstanceMsg'
class APIStopVmInstanceMsg(object):
    FULL_NAME='org.zstack.header.vm.APIStopVmInstanceMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #valid values: [grace, cold]
        self.type = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.cpuNum = None
        self.memorySize = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIBACKUPDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIBackupDataVolumeMsg'
class APIBackupDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIBackupDataVolumeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.backupStorageUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATEDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APICreateDataVolumeMsg'
class APICreateDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APICreateDataVolumeMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.diskOfferingUuid = NotNoneField()
        self.primaryStorageUuid = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATEVOLUMESNAPSHOTSCHEDULERMSG_FULL_NAME = 'org.zstack.header.volume.APICreateVolumeSnapshotSchedulerMsg'
class APICreateVolumeSnapshotSchedulerMsg(object):
    FULL_NAME='org.zstack.header.volume.APICreateVolumeSnapshotSchedulerMsg'
    def __init__(self):
        #mandatory field
        self.volumeUuid = NotNoneField()
        #mandatory field
        self.snapShotName = NotNoneField()
        self.volumeSnapshotDescription = None
        #mandatory field
        self.schedulerName = NotNoneField()
        self.schedulerDescription = None
        #mandatory field
        #valid values: [simple, cron]
        self.type = NotNoneField()
        self.interval = None
        self.repeatCount = None
        self.startTime = None
        self.cron = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIDeleteDataVolumeMsg'
class APIDeleteDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIDeleteDataVolumeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEVOLUMEQOSMSG_FULL_NAME = 'org.zstack.header.volume.APIDeleteVolumeQosMsg'
class APIDeleteVolumeQosMsg(object):
    FULL_NAME='org.zstack.header.volume.APIDeleteVolumeQosMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDETACHDATAVOLUMEFROMVMMSG_FULL_NAME = 'org.zstack.header.volume.APIDetachDataVolumeFromVmMsg'
class APIDetachDataVolumeFromVmMsg(object):
    FULL_NAME='org.zstack.header.volume.APIDetachDataVolumeFromVmMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.vmUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIEXPUNGEDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIExpungeDataVolumeMsg'
class APIExpungeDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIExpungeDataVolumeMsg'
    def __init__(self):
        self.uuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETDATAVOLUMEATTACHABLEVMMSG_FULL_NAME = 'org.zstack.header.volume.APIGetDataVolumeAttachableVmMsg'
class APIGetDataVolumeAttachableVmMsg(object):
    FULL_NAME='org.zstack.header.volume.APIGetDataVolumeAttachableVmMsg'
    def __init__(self):
        #mandatory field
        self.volumeUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETDATAVOLUMEATTACHABLEVMREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetDataVolumeAttachableVmReply'
class APIGetDataVolumeAttachableVmReply(object):
    FULL_NAME='org.zstack.header.volume.APIGetDataVolumeAttachableVmReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIGETVOLUMECAPABILITIESMSG_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeCapabilitiesMsg'
class APIGetVolumeCapabilitiesMsg(object):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeCapabilitiesMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVOLUMECAPABILITIESREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeCapabilitiesReply'
class APIGetVolumeCapabilitiesReply(object):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeCapabilitiesReply'
    def __init__(self):
        self.capabilities = OptionalMap()
        self.success = None
        self.error = None


APIGETVOLUMEFORMATMSG_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeFormatMsg'
class APIGetVolumeFormatMsg(object):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeFormatMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVOLUMEFORMATREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeFormatReply'
class APIGetVolumeFormatReply(object):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeFormatReply'
    def __init__(self):
        self.formats = OptionalList()
        self.success = None
        self.error = None


APIGETVOLUMEQOSMSG_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeQosMsg'
class APIGetVolumeQosMsg(object):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeQosMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVOLUMEQOSREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeQosReply'
class APIGetVolumeQosReply(object):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeQosReply'
    def __init__(self):
        self.volumeUuid = None
        self.volumeBandwidth = None
        self.success = None
        self.error = None


APIGETVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APIGetVolumeReply'
class APIGetVolumeReply(object):
    FULL_NAME='org.zstack.header.volume.APIGetVolumeReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APILISTVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APIListVolumeReply'
class APIListVolumeReply(object):
    FULL_NAME='org.zstack.header.volume.APIListVolumeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIQueryVolumeMsg'
class APIQueryVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIQueryVolumeMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APIQueryVolumeReply'
class APIQueryVolumeReply(object):
    FULL_NAME='org.zstack.header.volume.APIQueryVolumeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIRECOVERDATAVOLUMEMSG_FULL_NAME = 'org.zstack.header.volume.APIRecoverDataVolumeMsg'
class APIRecoverDataVolumeMsg(object):
    FULL_NAME='org.zstack.header.volume.APIRecoverDataVolumeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHVOLUMEREPLY_FULL_NAME = 'org.zstack.header.volume.APISearchVolumeReply'
class APISearchVolumeReply(object):
    FULL_NAME='org.zstack.header.volume.APISearchVolumeReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APISETVOLUMEQOSMSG_FULL_NAME = 'org.zstack.header.volume.APISetVolumeQosMsg'
class APISetVolumeQosMsg(object):
    FULL_NAME='org.zstack.header.volume.APISetVolumeQosMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        #mandatory field
        self.volumeBandwidth = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISYNCVOLUMESIZEMSG_FULL_NAME = 'org.zstack.header.volume.APISyncVolumeSizeMsg'
class APISyncVolumeSizeMsg(object):
    FULL_NAME='org.zstack.header.volume.APISyncVolumeSizeMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATEZONEMSG_FULL_NAME = 'org.zstack.header.zone.APICreateZoneMsg'
class APICreateZoneMsg(object):
    FULL_NAME='org.zstack.header.zone.APICreateZoneMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIDeleteZoneMsg'
class APIDeleteZoneMsg(object):
    FULL_NAME='org.zstack.header.zone.APIDeleteZoneMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETZONEMSG_FULL_NAME = 'org.zstack.header.zone.APIGetZoneMsg'
class APIGetZoneMsg(object):
    FULL_NAME='org.zstack.header.zone.APIGetZoneMsg'
    def __init__(self):
        self.uuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETZONEREPLY_FULL_NAME = 'org.zstack.header.zone.APIGetZoneReply'
class APIGetZoneReply(object):
    FULL_NAME='org.zstack.header.zone.APIGetZoneReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APILISTZONESREPLY_FULL_NAME = 'org.zstack.header.zone.APIListZonesReply'
class APIListZonesReply(object):
    FULL_NAME='org.zstack.header.zone.APIListZonesReply'
    def __init__(self):
        self.inventories = OptionalList()
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATEIPSECCONNECTIONMSG_FULL_NAME = 'org.zstack.ipsec.APICreateIPsecConnectionMsg'
class APICreateIPsecConnectionMsg(object):
    FULL_NAME='org.zstack.ipsec.APICreateIPsecConnectionMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.l3NetworkUuid = NotNoneField()
        #mandatory field
        self.peerAddress = NotNoneField()
        #valid values: [psk, certs]
        self.authMode = None
        #mandatory field
        self.authKey = NotNoneField()
        #mandatory field
        self.vipUuid = NotNoneField()
        #mandatory field
        self.peerCidrs = NotNoneList()
        #valid values: [md5, sha1, sha256, sha384, sha512]
        self.ikeAuthAlgorithm = None
        #valid values: [3des, aes-128, aes-192, aes-256]
        self.ikeEncryptionAlgorithm = None
        self.ikeDhGroup = None
        #valid values: [md5, sha1, sha256, sha384, sha512]
        self.policyAuthAlgorithm = None
        #valid values: [3des, aes-128, aes-192, aes-256]
        self.policyEncryptionAlgorithm = None
        #valid values: [dh-group2, dh-group5, dh-group14, dh-group15, dh-group16, dh-group17, dh-group18, dh-group19, dh-group20, dh-group21, dh-group22, dh-group23, dh-group24, dh-group25, dh-group26]
        self.pfs = None
        #valid values: [tunnel, transport]
        self.policyMode = None
        #valid values: [esp, ah, ah-esp]
        self.transformProtocol = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEIPSECCONNECTIONMSG_FULL_NAME = 'org.zstack.ipsec.APIDeleteIPsecConnectionMsg'
class APIDeleteIPsecConnectionMsg(object):
    FULL_NAME='org.zstack.ipsec.APIDeleteIPsecConnectionMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYIPSECCONNECTIONMSG_FULL_NAME = 'org.zstack.ipsec.APIQueryIPSecConnectionMsg'
class APIQueryIPSecConnectionMsg(object):
    FULL_NAME='org.zstack.ipsec.APIQueryIPSecConnectionMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYIPSECCONNECTIONREPLY_FULL_NAME = 'org.zstack.ipsec.APIQueryIPSecConnectionReply'
class APIQueryIPSecConnectionReply(object):
    FULL_NAME='org.zstack.ipsec.APIQueryIPSecConnectionReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIADDKVMHOSTMSG_FULL_NAME = 'org.zstack.kvm.APIAddKVMHostMsg'
class APIAddKVMHostMsg(object):
    FULL_NAME='org.zstack.kvm.APIAddKVMHostMsg'
    def __init__(self):
        #mandatory field
        self.username = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        self.sshPort = None
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.managementIp = NotNoneField()
        #mandatory field
        self.clusterUuid = NotNoneField()
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIUPDATEKVMHOSTMSG_FULL_NAME = 'org.zstack.kvm.APIUpdateKVMHostMsg'
class APIUpdateKVMHostMsg(object):
    FULL_NAME='org.zstack.kvm.APIUpdateKVMHostMsg'
    def __init__(self):
        self.username = None
        self.password = None
        self.sshPort = None
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.managementIp = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIADDLDAPSERVERMSG_FULL_NAME = 'org.zstack.ldap.APIAddLdapServerMsg'
class APIAddLdapServerMsg(object):
    FULL_NAME='org.zstack.ldap.APIAddLdapServerMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.description = NotNoneField()
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.base = NotNoneField()
        #mandatory field
        self.username = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        #mandatory field
        #valid values: [None, TLS]
        self.encryption = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICLEANINVALIDLDAPBINDINGMSG_FULL_NAME = 'org.zstack.ldap.APICleanInvalidLdapBindingMsg'
class APICleanInvalidLdapBindingMsg(object):
    FULL_NAME='org.zstack.ldap.APICleanInvalidLdapBindingMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATELDAPBINDINGMSG_FULL_NAME = 'org.zstack.ldap.APICreateLdapBindingMsg'
class APICreateLdapBindingMsg(object):
    FULL_NAME='org.zstack.ldap.APICreateLdapBindingMsg'
    def __init__(self):
        #mandatory field
        self.ldapUid = NotNoneField()
        #mandatory field
        self.accountUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETELDAPBINDINGMSG_FULL_NAME = 'org.zstack.ldap.APIDeleteLdapBindingMsg'
class APIDeleteLdapBindingMsg(object):
    FULL_NAME='org.zstack.ldap.APIDeleteLdapBindingMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETELDAPSERVERMSG_FULL_NAME = 'org.zstack.ldap.APIDeleteLdapServerMsg'
class APIDeleteLdapServerMsg(object):
    FULL_NAME='org.zstack.ldap.APIDeleteLdapServerMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APILOGINBYLDAPMSG_FULL_NAME = 'org.zstack.ldap.APILogInByLdapMsg'
class APILogInByLdapMsg(object):
    FULL_NAME='org.zstack.ldap.APILogInByLdapMsg'
    def __init__(self):
        #mandatory field
        self.uid = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APILOGINBYLDAPREPLY_FULL_NAME = 'org.zstack.ldap.APILogInByLdapReply'
class APILogInByLdapReply(object):
    FULL_NAME='org.zstack.ldap.APILogInByLdapReply'
    def __init__(self):
        self.inventory = None
        self.accountInventory = None
        self.success = None
        self.error = None


APIQUERYLDAPBINDINGMSG_FULL_NAME = 'org.zstack.ldap.APIQueryLdapBindingMsg'
class APIQueryLdapBindingMsg(object):
    FULL_NAME='org.zstack.ldap.APIQueryLdapBindingMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYLDAPBINDINGREPLY_FULL_NAME = 'org.zstack.ldap.APIQueryLdapBindingReply'
class APIQueryLdapBindingReply(object):
    FULL_NAME='org.zstack.ldap.APIQueryLdapBindingReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYLDAPSERVERMSG_FULL_NAME = 'org.zstack.ldap.APIQueryLdapServerMsg'
class APIQueryLdapServerMsg(object):
    FULL_NAME='org.zstack.ldap.APIQueryLdapServerMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYLDAPSERVERREPLY_FULL_NAME = 'org.zstack.ldap.APIQueryLdapServerReply'
class APIQueryLdapServerReply(object):
    FULL_NAME='org.zstack.ldap.APIQueryLdapServerReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIUPDATELDAPSERVERMSG_FULL_NAME = 'org.zstack.ldap.APIUpdateLdapServerMsg'
class APIUpdateLdapServerMsg(object):
    FULL_NAME='org.zstack.ldap.APIUpdateLdapServerMsg'
    def __init__(self):
        #mandatory field
        self.ldapServerUuid = NotNoneField()
        self.name = None
        self.description = None
        self.url = None
        self.base = None
        self.username = None
        self.password = None
        #valid values: [None, TLS]
        self.encryption = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETLICENSECAPABILITIESMSG_FULL_NAME = 'org.zstack.license.APIGetLicenseCapabilitiesMsg'
class APIGetLicenseCapabilitiesMsg(object):
    FULL_NAME='org.zstack.license.APIGetLicenseCapabilitiesMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETLICENSECAPABILITIESREPLY_FULL_NAME = 'org.zstack.license.APIGetLicenseCapabilitiesReply'
class APIGetLicenseCapabilitiesReply(object):
    FULL_NAME='org.zstack.license.APIGetLicenseCapabilitiesReply'
    def __init__(self):
        self.capabilities = OptionalMap()
        self.success = None
        self.error = None


APIGETLICENSEINFOMSG_FULL_NAME = 'org.zstack.license.APIGetLicenseInfoMsg'
class APIGetLicenseInfoMsg(object):
    FULL_NAME='org.zstack.license.APIGetLicenseInfoMsg'
    def __init__(self):
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETLICENSEINFOREPLY_FULL_NAME = 'org.zstack.license.APIGetLicenseInfoReply'
class APIGetLicenseInfoReply(object):
    FULL_NAME='org.zstack.license.APIGetLicenseInfoReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIRELOADLICENSEMSG_FULL_NAME = 'org.zstack.license.APIReloadLicenseMsg'
class APIReloadLicenseMsg(object):
    FULL_NAME='org.zstack.license.APIReloadLicenseMsg'
    def __init__(self):
        self.managementNodeUuids = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIRELOADLICENSEREPLY_FULL_NAME = 'org.zstack.license.APIReloadLicenseReply'
class APIReloadLicenseReply(object):
    FULL_NAME='org.zstack.license.APIReloadLicenseReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIQUERYSHAREABLEVOLUMEVMINSTANCEREFMSG_FULL_NAME = 'org.zstack.mevoco.APIQueryShareableVolumeVmInstanceRefMsg'
class APIQueryShareableVolumeVmInstanceRefMsg(object):
    FULL_NAME='org.zstack.mevoco.APIQueryShareableVolumeVmInstanceRefMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYSHAREABLEVOLUMEVMINSTANCEREFREPLY_FULL_NAME = 'org.zstack.mevoco.APIQueryShareableVolumeVmInstanceRefReply'
class APIQueryShareableVolumeVmInstanceRefReply(object):
    FULL_NAME='org.zstack.mevoco.APIQueryShareableVolumeVmInstanceRefReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIGETHOSTMONITORINGDATAMSG_FULL_NAME = 'org.zstack.monitoring.APIGetHostMonitoringDataMsg'
class APIGetHostMonitoringDataMsg(object):
    FULL_NAME='org.zstack.monitoring.APIGetHostMonitoringDataMsg'
    def __init__(self):
        self.hostUuid = None
        #mandatory field
        self.query = NotNoneMap()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETHOSTMONITORINGDATAREPLY_FULL_NAME = 'org.zstack.monitoring.APIGetHostMonitoringDataReply'
class APIGetHostMonitoringDataReply(object):
    FULL_NAME='org.zstack.monitoring.APIGetHostMonitoringDataReply'
    def __init__(self):
        self.data = OptionalMap()
        self.success = None
        self.error = None


APIGETVMMONITORINGDATAMSG_FULL_NAME = 'org.zstack.monitoring.APIGetVmMonitoringDataMsg'
class APIGetVmMonitoringDataMsg(object):
    FULL_NAME='org.zstack.monitoring.APIGetVmMonitoringDataMsg'
    def __init__(self):
        self.vmInstanceUuid = None
        #mandatory field
        self.query = NotNoneMap()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVMMONITORINGDATAREPLY_FULL_NAME = 'org.zstack.monitoring.APIGetVmMonitoringDataReply'
class APIGetVmMonitoringDataReply(object):
    FULL_NAME='org.zstack.monitoring.APIGetVmMonitoringDataReply'
    def __init__(self):
        self.data = OptionalMap()
        self.success = None
        self.error = None


APIMONITORINGPASSTHROUGHMSG_FULL_NAME = 'org.zstack.monitoring.APIMonitoringPassThroughMsg'
class APIMonitoringPassThroughMsg(object):
    FULL_NAME='org.zstack.monitoring.APIMonitoringPassThroughMsg'
    def __init__(self):
        #mandatory field
        self.apiPath = NotNoneField()
        self.query = OptionalMap()
        #valid values: [GET, POST, DELETE, PUT, HEAD]
        self.httpMethod = None
        self.httpHeaders = OptionalList()
        self.successStatusCodes = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIMONITORINGPASSTHROUGHREPLY_FULL_NAME = 'org.zstack.monitoring.APIMonitoringPassThroughReply'
class APIMonitoringPassThroughReply(object):
    FULL_NAME='org.zstack.monitoring.APIMonitoringPassThroughReply'
    def __init__(self):
        self.data = OptionalMap()
        self.success = None
        self.error = None


APICREATEL2VXLANNETWORKMSG_FULL_NAME = 'org.zstack.network.l2.vxlan.vxlanNetwork.APICreateL2VxlanNetworkMsg'
class APICreateL2VxlanNetworkMsg(object):
    FULL_NAME='org.zstack.network.l2.vxlan.vxlanNetwork.APICreateL2VxlanNetworkMsg'
    def __init__(self):
        self.vni = None
        #mandatory field
        self.poolUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.physicalInterface = None
        self.type = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYL2VXLANNETWORKMSG_FULL_NAME = 'org.zstack.network.l2.vxlan.vxlanNetwork.APIQueryL2VxlanNetworkMsg'
class APIQueryL2VxlanNetworkMsg(object):
    FULL_NAME='org.zstack.network.l2.vxlan.vxlanNetwork.APIQueryL2VxlanNetworkMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYL2VXLANNETWORKREPLY_FULL_NAME = 'org.zstack.network.l2.vxlan.vxlanNetwork.APIQueryL2VxlanNetworkReply'
class APIQueryL2VxlanNetworkReply(object):
    FULL_NAME='org.zstack.network.l2.vxlan.vxlanNetwork.APIQueryL2VxlanNetworkReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APICREATEL2VXLANNETWORKPOOLMSG_FULL_NAME = 'org.zstack.network.l2.vxlan.vxlanNetworkPool.APICreateL2VxlanNetworkPoolMsg'
class APICreateL2VxlanNetworkPoolMsg(object):
    FULL_NAME='org.zstack.network.l2.vxlan.vxlanNetworkPool.APICreateL2VxlanNetworkPoolMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.zoneUuid = NotNoneField()
        self.physicalInterface = None
        self.type = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATEVNIRANGEMSG_FULL_NAME = 'org.zstack.network.l2.vxlan.vxlanNetworkPool.APICreateVniRangeMsg'
class APICreateVniRangeMsg(object):
    FULL_NAME='org.zstack.network.l2.vxlan.vxlanNetworkPool.APICreateVniRangeMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        #mandatory field
        self.startVni = NotNoneField()
        #mandatory field
        self.endVni = NotNoneField()
        #mandatory field
        self.l2NetworkUuid = NotNoneField()
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYL2VXLANNETWORKPOOLMSG_FULL_NAME = 'org.zstack.network.l2.vxlan.vxlanNetworkPool.APIQueryL2VxlanNetworkPoolMsg'
class APIQueryL2VxlanNetworkPoolMsg(object):
    FULL_NAME='org.zstack.network.l2.vxlan.vxlanNetworkPool.APIQueryL2VxlanNetworkPoolMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYL2VXLANNETWORKPOOLREPLY_FULL_NAME = 'org.zstack.network.l2.vxlan.vxlanNetworkPool.APIQueryL2VxlanNetworkPoolReply'
class APIQueryL2VxlanNetworkPoolReply(object):
    FULL_NAME='org.zstack.network.l2.vxlan.vxlanNetworkPool.APIQueryL2VxlanNetworkPoolReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYVNIRANGEMSG_FULL_NAME = 'org.zstack.network.l2.vxlan.vxlanNetworkPool.APIQueryVniRangeMsg'
class APIQueryVniRangeMsg(object):
    FULL_NAME='org.zstack.network.l2.vxlan.vxlanNetworkPool.APIQueryVniRangeMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVNIRANGEREPLY_FULL_NAME = 'org.zstack.network.l2.vxlan.vxlanNetworkPool.APIQueryVniRangeReply'
class APIQueryVniRangeReply(object):
    FULL_NAME='org.zstack.network.l2.vxlan.vxlanNetworkPool.APIQueryVniRangeReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APICREATESECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APICreateSecurityGroupMsg'
class APICreateSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APICreateSecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETESECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteSecurityGroupMsg'
class APIDeleteSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteSecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETESECURITYGROUPRULEMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIDeleteSecurityGroupRuleMsg'
class APIDeleteSecurityGroupRuleMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIDeleteSecurityGroupRuleMsg'
    def __init__(self):
        #mandatory field
        self.ruleUuids = NotNoneList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCANDIDATEVMNICFORSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupMsg'
class APIGetCandidateVmNicForSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.securityGroupUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCANDIDATEVMNICFORSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupReply'
class APIGetCandidateVmNicForSecurityGroupReply(object):
    FULL_NAME='org.zstack.network.securitygroup.APIGetCandidateVmNicForSecurityGroupReply'
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


APILISTVMNICINSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIListVmNicInSecurityGroupReply'
class APIListVmNicInSecurityGroupReply(object):
    FULL_NAME='org.zstack.network.securitygroup.APIListVmNicInSecurityGroupReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupMsg'
class APIQuerySecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYSECURITYGROUPREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupReply'
class APIQuerySecurityGroupReply(object):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYSECURITYGROUPRULEREPLY_FULL_NAME = 'org.zstack.network.securitygroup.APIQuerySecurityGroupRuleReply'
class APIQuerySecurityGroupRuleReply(object):
    FULL_NAME='org.zstack.network.securitygroup.APIQuerySecurityGroupRuleReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYVMNICINSECURITYGROUPMSG_FULL_NAME = 'org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupMsg'
class APIQueryVmNicInSecurityGroupMsg(object):
    FULL_NAME='org.zstack.network.securitygroup.APIQueryVmNicInSecurityGroupMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIDeleteEipMsg'
class APIDeleteEipMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APIDeleteEipMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDETACHEIPMSG_FULL_NAME = 'org.zstack.network.service.eip.APIDetachEipMsg'
class APIDetachEipMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APIDetachEipMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETEIPATTACHABLEVMNICSMSG_FULL_NAME = 'org.zstack.network.service.eip.APIGetEipAttachableVmNicsMsg'
class APIGetEipAttachableVmNicsMsg(object):
    FULL_NAME='org.zstack.network.service.eip.APIGetEipAttachableVmNicsMsg'
    def __init__(self):
        self.eipUuid = None
        self.vipUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYEIPREPLY_FULL_NAME = 'org.zstack.network.service.eip.APIQueryEipReply'
class APIQueryEipReply(object):
    FULL_NAME='org.zstack.network.service.eip.APIQueryEipReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETL3NETWORKDHCPIPADDRESSMSG_FULL_NAME = 'org.zstack.network.service.flat.APIGetL3NetworkDhcpIpAddressMsg'
class APIGetL3NetworkDhcpIpAddressMsg(object):
    FULL_NAME='org.zstack.network.service.flat.APIGetL3NetworkDhcpIpAddressMsg'
    def __init__(self):
        self.l3NetworkUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETL3NETWORKDHCPIPADDRESSREPLY_FULL_NAME = 'org.zstack.network.service.flat.APIGetL3NetworkDhcpIpAddressReply'
class APIGetL3NetworkDhcpIpAddressReply(object):
    FULL_NAME='org.zstack.network.service.flat.APIGetL3NetworkDhcpIpAddressReply'
    def __init__(self):
        self.ip = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETELOADBALANCERLISTENERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIDeleteLoadBalancerListenerMsg'
class APIDeleteLoadBalancerListenerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIDeleteLoadBalancerListenerMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETELOADBALANCERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIDeleteLoadBalancerMsg'
class APIDeleteLoadBalancerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIDeleteLoadBalancerMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCANDIDATEVMNICSFORLOADBALANCERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIGetCandidateVmNicsForLoadBalancerMsg'
class APIGetCandidateVmNicsForLoadBalancerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIGetCandidateVmNicsForLoadBalancerMsg'
    def __init__(self):
        #mandatory field
        self.listenerUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETCANDIDATEVMNICSFORLOADBALANCERREPLY_FULL_NAME = 'org.zstack.network.service.lb.APIGetCandidateVmNicsForLoadBalancerReply'
class APIGetCandidateVmNicsForLoadBalancerReply(object):
    FULL_NAME='org.zstack.network.service.lb.APIGetCandidateVmNicsForLoadBalancerReply'
    def __init__(self):
        self.inventories = OptionalList()
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYLOADBALANCERLISTENERREPLY_FULL_NAME = 'org.zstack.network.service.lb.APIQueryLoadBalancerListenerReply'
class APIQueryLoadBalancerListenerReply(object):
    FULL_NAME='org.zstack.network.service.lb.APIQueryLoadBalancerListenerReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYLOADBALANCERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIQueryLoadBalancerMsg'
class APIQueryLoadBalancerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIQueryLoadBalancerMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYLOADBALANCERREPLY_FULL_NAME = 'org.zstack.network.service.lb.APIQueryLoadBalancerReply'
class APIQueryLoadBalancerReply(object):
    FULL_NAME='org.zstack.network.service.lb.APIQueryLoadBalancerReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIREFRESHLOADBALANCERMSG_FULL_NAME = 'org.zstack.network.service.lb.APIRefreshLoadBalancerMsg'
class APIRefreshLoadBalancerMsg(object):
    FULL_NAME='org.zstack.network.service.lb.APIRefreshLoadBalancerMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIDeletePortForwardingRuleMsg'
class APIDeletePortForwardingRuleMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIDeletePortForwardingRuleMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDETACHPORTFORWARDINGRULEMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIDetachPortForwardingRuleMsg'
class APIDetachPortForwardingRuleMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIDetachPortForwardingRuleMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETPORTFORWARDINGATTACHABLEVMNICSMSG_FULL_NAME = 'org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsMsg'
class APIGetPortForwardingAttachableVmNicsMsg(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsMsg'
    def __init__(self):
        #mandatory field
        self.ruleUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETPORTFORWARDINGATTACHABLEVMNICSREPLY_FULL_NAME = 'org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsReply'
class APIGetPortForwardingAttachableVmNicsReply(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIGetPortForwardingAttachableVmNicsReply'
    def __init__(self):
        self.inventories = OptionalList()
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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYPORTFORWARDINGRULEREPLY_FULL_NAME = 'org.zstack.network.service.portforwarding.APIQueryPortForwardingRuleReply'
class APIQueryPortForwardingRuleReply(object):
    FULL_NAME='org.zstack.network.service.portforwarding.APIQueryPortForwardingRuleReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APIDeleteVipMsg'
class APIDeleteVipMsg(object):
    FULL_NAME='org.zstack.network.service.vip.APIDeleteVipMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVIPMSG_FULL_NAME = 'org.zstack.network.service.vip.APIQueryVipMsg'
class APIQueryVipMsg(object):
    FULL_NAME='org.zstack.network.service.vip.APIQueryVipMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.memorySize = NotNoneField()
        self.allocatorStrategy = None
        self.sortKey = None
        self.type = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.primaryStorageUuidForRootVolume = None
        self.description = None
        self.defaultL3NetworkUuid = None
        #valid values: [InstantStart, JustCreate]
        self.strategy = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVIRTUALROUTEROFFERINGREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIGetVirtualRouterOfferingReply'
class APIGetVirtualRouterOfferingReply(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIGetVirtualRouterOfferingReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIQUERYVIRTUALROUTEROFFERINGMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIQueryVirtualRouterOfferingMsg'
class APIQueryVirtualRouterOfferingMsg(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIQueryVirtualRouterOfferingMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVIRTUALROUTERVMREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIQueryVirtualRouterVmReply'
class APIQueryVirtualRouterVmReply(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIQueryVirtualRouterVmReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIRECONNECTVIRTUALROUTERMSG_FULL_NAME = 'org.zstack.network.service.virtualrouter.APIReconnectVirtualRouterMsg'
class APIReconnectVirtualRouterMsg(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APIReconnectVirtualRouterMsg'
    def __init__(self):
        #mandatory field
        self.vmInstanceUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHVIRTUALROUTEROFFINGREPLY_FULL_NAME = 'org.zstack.network.service.virtualrouter.APISearchVirtualRouterOffingReply'
class APISearchVirtualRouterOffingReply(object):
    FULL_NAME='org.zstack.network.service.virtualrouter.APISearchVirtualRouterOffingReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIPROMETHEUSQUERYLABELVALUESMSG_FULL_NAME = 'org.zstack.prometheus.APIPrometheusQueryLabelValuesMsg'
class APIPrometheusQueryLabelValuesMsg(object):
    FULL_NAME='org.zstack.prometheus.APIPrometheusQueryLabelValuesMsg'
    def __init__(self):
        #mandatory field
        self.labels = NotNoneList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIPROMETHEUSQUERYLABELVALUESREPLY_FULL_NAME = 'org.zstack.prometheus.APIPrometheusQueryLabelValuesReply'
class APIPrometheusQueryLabelValuesReply(object):
    FULL_NAME='org.zstack.prometheus.APIPrometheusQueryLabelValuesReply'
    def __init__(self):
        self.inventories = OptionalMap()
        self.success = None
        self.error = None


APIPROMETHEUSQUERYMETADATAMSG_FULL_NAME = 'org.zstack.prometheus.APIPrometheusQueryMetadataMsg'
class APIPrometheusQueryMetadataMsg(object):
    FULL_NAME='org.zstack.prometheus.APIPrometheusQueryMetadataMsg'
    def __init__(self):
        #mandatory field
        self.matches = NotNoneList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIPROMETHEUSQUERYMETADATAREPLY_FULL_NAME = 'org.zstack.prometheus.APIPrometheusQueryMetadataReply'
class APIPrometheusQueryMetadataReply(object):
    FULL_NAME='org.zstack.prometheus.APIPrometheusQueryMetadataReply'
    def __init__(self):
        self.inventories = OptionalMap()
        self.success = None
        self.error = None


APIPROMETHEUSQUERYPASSTHROUGHMSG_FULL_NAME = 'org.zstack.prometheus.APIPrometheusQueryPassThroughMsg'
class APIPrometheusQueryPassThroughMsg(object):
    FULL_NAME='org.zstack.prometheus.APIPrometheusQueryPassThroughMsg'
    def __init__(self):
        self.instant = None
        self.startTime = None
        self.endTime = None
        self.step = None
        #mandatory field
        self.expression = NotNoneField()
        self.relativeTime = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIPROMETHEUSQUERYVMMONITORINGDATAMSG_FULL_NAME = 'org.zstack.prometheus.APIPrometheusQueryVmMonitoringDataMsg'
class APIPrometheusQueryVmMonitoringDataMsg(object):
    FULL_NAME='org.zstack.prometheus.APIPrometheusQueryVmMonitoringDataMsg'
    def __init__(self):
        #mandatory field
        self.vmUuids = NotNoneList()
        self.instant = None
        self.startTime = None
        self.endTime = None
        self.step = None
        #mandatory field
        self.expression = NotNoneField()
        self.relativeTime = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIPROMETHEUSQUERYVMMONITORINGDATAREPLY_FULL_NAME = 'org.zstack.prometheus.APIPrometheusQueryVmMonitoringDataReply'
class APIPrometheusQueryVmMonitoringDataReply(object):
    FULL_NAME='org.zstack.prometheus.APIPrometheusQueryVmMonitoringDataReply'
    def __init__(self):
        self.inventories = OptionalMap()
        self.success = None
        self.error = None


APIADDIMAGESTOREBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.imagestore.APIAddImageStoreBackupStorageMsg'
class APIAddImageStoreBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.backup.imagestore.APIAddImageStoreBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.hostname = NotNoneField()
        #mandatory field
        self.username = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        self.sshPort = None
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        self.importImages = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYIMAGESTOREBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.imagestore.APIQueryImageStoreBackupStorageMsg'
class APIQueryImageStoreBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.backup.imagestore.APIQueryImageStoreBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYIMAGESTOREBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.imagestore.APIQueryImageStoreBackupStorageReply'
class APIQueryImageStoreBackupStorageReply(object):
    FULL_NAME='org.zstack.storage.backup.imagestore.APIQueryImageStoreBackupStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIRECLAIMSPACEFROMIMAGESTOREMSG_FULL_NAME = 'org.zstack.storage.backup.imagestore.APIReclaimSpaceFromImageStoreMsg'
class APIReclaimSpaceFromImageStoreMsg(object):
    FULL_NAME='org.zstack.storage.backup.imagestore.APIReclaimSpaceFromImageStoreMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIRECONNECTIMAGESTOREBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.imagestore.APIReconnectImageStoreBackupStorageMsg'
class APIReconnectImageStoreBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.backup.imagestore.APIReconnectImageStoreBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIUPDATEIMAGESTOREBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.imagestore.APIUpdateImageStoreBackupStorageMsg'
class APIUpdateImageStoreBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.backup.imagestore.APIUpdateImageStoreBackupStorageMsg'
    def __init__(self):
        self.username = None
        self.password = None
        self.hostname = None
        self.sshPort = None
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.sshPort = None
        #mandatory field
        self.url = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        self.description = None
        self.type = None
        self.importImages = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APIGetSftpBackupStorageReply'
class APIGetSftpBackupStorageReply(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APIGetSftpBackupStorageReply'
    def __init__(self):
        self.inventory = None
        self.success = None
        self.error = None


APIQUERYSFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageMsg'
class APIQuerySftpBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageReply'
class APIQuerySftpBackupStorageReply(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APIQuerySftpBackupStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APISEARCHSFTPBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.storage.backup.sftp.APISearchSftpBackupStorageReply'
class APISearchSftpBackupStorageReply(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APISearchSftpBackupStorageReply'
    def __init__(self):
        self.content = None
        self.success = None
        self.error = None


APIUPDATESFTPBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.backup.sftp.APIUpdateSftpBackupStorageMsg'
class APIUpdateSftpBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.backup.sftp.APIUpdateSftpBackupStorageMsg'
    def __init__(self):
        self.username = None
        self.password = None
        self.hostname = None
        self.sshPort = None
        #mandatory field
        self.uuid = NotNoneField()
        self.name = None
        self.description = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.importImages = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYCEPHBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.ceph.backup.APIQueryCephBackupStorageMsg'
class APIQueryCephBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.ceph.backup.APIQueryCephBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIUPDATECEPHBACKUPSTORAGEMONMSG_FULL_NAME = 'org.zstack.storage.ceph.backup.APIUpdateCephBackupStorageMonMsg'
class APIUpdateCephBackupStorageMonMsg(object):
    FULL_NAME='org.zstack.storage.ceph.backup.APIUpdateCephBackupStorageMonMsg'
    def __init__(self):
        #mandatory field
        self.monUuid = NotNoneField()
        self.hostname = None
        self.sshUsername = None
        self.sshPassword = None
        self.sshPort = None
        self.monPort = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIADDCEPHPRIMARYSTORAGEPOOLMSG_FULL_NAME = 'org.zstack.storage.ceph.primary.APIAddCephPrimaryStoragePoolMsg'
class APIAddCephPrimaryStoragePoolMsg(object):
    FULL_NAME='org.zstack.storage.ceph.primary.APIAddCephPrimaryStoragePoolMsg'
    def __init__(self):
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        #mandatory field
        self.poolName = NotNoneField()
        self.description = None
        self.errorIfNotExist = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETECEPHPRIMARYSTORAGEPOOLMSG_FULL_NAME = 'org.zstack.storage.ceph.primary.APIDeleteCephPrimaryStoragePoolMsg'
class APIDeleteCephPrimaryStoragePoolMsg(object):
    FULL_NAME='org.zstack.storage.ceph.primary.APIDeleteCephPrimaryStoragePoolMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYCEPHPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.ceph.primary.APIQueryCephPrimaryStorageMsg'
class APIQueryCephPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.ceph.primary.APIQueryCephPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYCEPHPRIMARYSTORAGEPOOLMSG_FULL_NAME = 'org.zstack.storage.ceph.primary.APIQueryCephPrimaryStoragePoolMsg'
class APIQueryCephPrimaryStoragePoolMsg(object):
    FULL_NAME='org.zstack.storage.ceph.primary.APIQueryCephPrimaryStoragePoolMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYCEPHPRIMARYSTORAGEPOOLREPLY_FULL_NAME = 'org.zstack.storage.ceph.primary.APIQueryCephPrimaryStoragePoolReply'
class APIQueryCephPrimaryStoragePoolReply(object):
    FULL_NAME='org.zstack.storage.ceph.primary.APIQueryCephPrimaryStoragePoolReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIUPDATECEPHPRIMARYSTORAGEMONMSG_FULL_NAME = 'org.zstack.storage.ceph.primary.APIUpdateCephPrimaryStorageMonMsg'
class APIUpdateCephPrimaryStorageMonMsg(object):
    FULL_NAME='org.zstack.storage.ceph.primary.APIUpdateCephPrimaryStorageMonMsg'
    def __init__(self):
        #mandatory field
        self.monUuid = NotNoneField()
        self.hostname = None
        self.sshUsername = None
        self.sshPassword = None
        self.sshPort = None
        self.monPort = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.importImages = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYFUSIONSTORBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.storage.fusionstor.backup.APIQueryFusionstorBackupStorageMsg'
class APIQueryFusionstorBackupStorageMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.backup.APIQueryFusionstorBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIUPDATEFUSIONSTORBACKUPSTORAGEMONMSG_FULL_NAME = 'org.zstack.storage.fusionstor.backup.APIUpdateFusionstorBackupStorageMonMsg'
class APIUpdateFusionstorBackupStorageMonMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.backup.APIUpdateFusionstorBackupStorageMonMsg'
    def __init__(self):
        #mandatory field
        self.monUuid = NotNoneField()
        self.hostname = None
        self.sshUsername = None
        self.sshPassword = None
        self.sshPort = None
        self.monPort = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYFUSIONSTORPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.storage.fusionstor.primary.APIQueryFusionstorPrimaryStorageMsg'
class APIQueryFusionstorPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.primary.APIQueryFusionstorPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIUPDATEFUSIONSTORPRIMARYSTORAGEMONMSG_FULL_NAME = 'org.zstack.storage.fusionstor.primary.APIUpdateFusionstorPrimaryStorageMonMsg'
class APIUpdateFusionstorPrimaryStorageMonMsg(object):
    FULL_NAME='org.zstack.storage.fusionstor.primary.APIUpdateFusionstorPrimaryStorageMonMsg'
    def __init__(self):
        #mandatory field
        self.monUuid = NotNoneField()
        self.hostname = None
        self.sshUsername = None
        self.sshPassword = None
        self.sshPort = None
        self.monPort = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETLOCALSTORAGEHOSTDISKCAPACITYMSG_FULL_NAME = 'org.zstack.storage.primary.local.APIGetLocalStorageHostDiskCapacityMsg'
class APIGetLocalStorageHostDiskCapacityMsg(object):
    FULL_NAME='org.zstack.storage.primary.local.APIGetLocalStorageHostDiskCapacityMsg'
    def __init__(self):
        self.hostUuid = None
        #mandatory field
        self.primaryStorageUuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APILOCALSTORAGEGETVOLUMEMIGRATABLEREPLY_FULL_NAME = 'org.zstack.storage.primary.local.APILocalStorageGetVolumeMigratableReply'
class APILocalStorageGetVolumeMigratableReply(object):
    FULL_NAME='org.zstack.storage.primary.local.APILocalStorageGetVolumeMigratableReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.success = None
        self.error = None


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
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYLOCALSTORAGERESOURCEREFMSG_FULL_NAME = 'org.zstack.storage.primary.local.APIQueryLocalStorageResourceRefMsg'
class APIQueryLocalStorageResourceRefMsg(object):
    FULL_NAME='org.zstack.storage.primary.local.APIQueryLocalStorageResourceRefMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYLOCALSTORAGERESOURCEREFREPLY_FULL_NAME = 'org.zstack.storage.primary.local.APIQueryLocalStorageResourceRefReply'
class APIQueryLocalStorageResourceRefReply(object):
    FULL_NAME='org.zstack.storage.primary.local.APIQueryLocalStorageResourceRefReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


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
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIADDVCENTERMSG_FULL_NAME = 'org.zstack.vmware.APIAddVCenterMsg'
class APIAddVCenterMsg(object):
    FULL_NAME='org.zstack.vmware.APIAddVCenterMsg'
    def __init__(self):
        #mandatory field
        self.username = NotNoneField()
        #mandatory field
        self.password = NotNoneField()
        #mandatory field
        self.zoneUuid = NotNoneField()
        #mandatory field
        self.name = NotNoneField()
        #mandatory field
        self.https = NotNoneField()
        #mandatory field
        self.domainName = NotNoneField()
        self.description = None
        self.resourceUuid = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIDELETEVCENTERMSG_FULL_NAME = 'org.zstack.vmware.APIDeleteVCenterMsg'
class APIDeleteVCenterMsg(object):
    FULL_NAME='org.zstack.vmware.APIDeleteVCenterMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.deleteMode = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVCENTERDVSWITCHESMSG_FULL_NAME = 'org.zstack.vmware.APIGetVCenterDVSwitchesMsg'
class APIGetVCenterDVSwitchesMsg(object):
    FULL_NAME='org.zstack.vmware.APIGetVCenterDVSwitchesMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIGETVCENTERDVSWITCHESREPLY_FULL_NAME = 'org.zstack.vmware.APIGetVCenterDVSwitchesReply'
class APIGetVCenterDVSwitchesReply(object):
    FULL_NAME='org.zstack.vmware.APIGetVCenterDVSwitchesReply'
    def __init__(self):
        self.vcUuid = None
        self.inventories = OptionalList()
        self.success = None
        self.error = None


APIQUERYVCENTERBACKUPSTORAGEMSG_FULL_NAME = 'org.zstack.vmware.APIQueryVCenterBackupStorageMsg'
class APIQueryVCenterBackupStorageMsg(object):
    FULL_NAME='org.zstack.vmware.APIQueryVCenterBackupStorageMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVCENTERBACKUPSTORAGEREPLY_FULL_NAME = 'org.zstack.vmware.APIQueryVCenterBackupStorageReply'
class APIQueryVCenterBackupStorageReply(object):
    FULL_NAME='org.zstack.vmware.APIQueryVCenterBackupStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYVCENTERCLUSTERMSG_FULL_NAME = 'org.zstack.vmware.APIQueryVCenterClusterMsg'
class APIQueryVCenterClusterMsg(object):
    FULL_NAME='org.zstack.vmware.APIQueryVCenterClusterMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVCENTERCLUSTERREPLY_FULL_NAME = 'org.zstack.vmware.APIQueryVCenterClusterReply'
class APIQueryVCenterClusterReply(object):
    FULL_NAME='org.zstack.vmware.APIQueryVCenterClusterReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYVCENTERDATACENTERMSG_FULL_NAME = 'org.zstack.vmware.APIQueryVCenterDatacenterMsg'
class APIQueryVCenterDatacenterMsg(object):
    FULL_NAME='org.zstack.vmware.APIQueryVCenterDatacenterMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVCENTERDATACENTERREPLY_FULL_NAME = 'org.zstack.vmware.APIQueryVCenterDatacenterReply'
class APIQueryVCenterDatacenterReply(object):
    FULL_NAME='org.zstack.vmware.APIQueryVCenterDatacenterReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYVCENTERMSG_FULL_NAME = 'org.zstack.vmware.APIQueryVCenterMsg'
class APIQueryVCenterMsg(object):
    FULL_NAME='org.zstack.vmware.APIQueryVCenterMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVCENTERPRIMARYSTORAGEMSG_FULL_NAME = 'org.zstack.vmware.APIQueryVCenterPrimaryStorageMsg'
class APIQueryVCenterPrimaryStorageMsg(object):
    FULL_NAME='org.zstack.vmware.APIQueryVCenterPrimaryStorageMsg'
    def __init__(self):
        #mandatory field
        self.conditions = NotNoneList()
        self.limit = None
        self.start = None
        self.count = None
        self.groupBy = None
        self.replyWithCount = None
        self.sortBy = None
        #valid values: [asc, desc]
        self.sortDirection = None
        self.fields = OptionalList()
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


APIQUERYVCENTERPRIMARYSTORAGEREPLY_FULL_NAME = 'org.zstack.vmware.APIQueryVCenterPrimaryStorageReply'
class APIQueryVCenterPrimaryStorageReply(object):
    FULL_NAME='org.zstack.vmware.APIQueryVCenterPrimaryStorageReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIQUERYVCENTERREPLY_FULL_NAME = 'org.zstack.vmware.APIQueryVCenterReply'
class APIQueryVCenterReply(object):
    FULL_NAME='org.zstack.vmware.APIQueryVCenterReply'
    def __init__(self):
        self.inventories = OptionalList()
        self.total = None
        self.success = None
        self.error = None


APIUPDATEVCENTERMSG_FULL_NAME = 'org.zstack.vmware.APIUpdateVCenterMsg'
class APIUpdateVCenterMsg(object):
    FULL_NAME='org.zstack.vmware.APIUpdateVCenterMsg'
    def __init__(self):
        #mandatory field
        self.uuid = NotNoneField()
        self.username = None
        self.password = None
        self.domainName = None
        self.session = None
        self.timeout = None
        self.systemTags = OptionalList()
        self.userTags = OptionalList()


api_names = [
    'APIAddAliyunKeySecretMsg',
    'APIAddCephBackupStorageMsg',
    'APIAddCephPrimaryStorageMsg',
    'APIAddCephPrimaryStoragePoolMsg',
    'APIAddDataCenterFromRemoteMsg',
    'APIAddDnsToL3NetworkMsg',
    'APIAddFusionstorBackupStorageMsg',
    'APIAddFusionstorPrimaryStorageMsg',
    'APIAddIdentityZoneFromRemoteMsg',
    'APIAddImageMsg',
    'APIAddImageStoreBackupStorageMsg',
    'APIAddIpRangeByNetworkCidrMsg',
    'APIAddIpRangeMsg',
    'APIAddKVMHostMsg',
    'APIAddLdapServerMsg',
    'APIAddLocalPrimaryStorageMsg',
    'APIAddMonToCephBackupStorageMsg',
    'APIAddMonToCephPrimaryStorageMsg',
    'APIAddMonToFusionstorBackupStorageMsg',
    'APIAddMonToFusionstorPrimaryStorageMsg',
    'APIAddNetworkServiceProviderMsg',
    'APIAddNfsPrimaryStorageMsg',
    'APIAddOssFileBucketNameMsg',
    'APIAddSecurityGroupRuleMsg',
    'APIAddSftpBackupStorageMsg',
    'APIAddSharedMountPointPrimaryStorageMsg',
    'APIAddSimulatorBackupStorageMsg',
    'APIAddSimulatorHostMsg',
    'APIAddSimulatorPrimaryStorageMsg',
    'APIAddUserToGroupMsg',
    'APIAddVCenterMsg',
    'APIAddVmNicToLoadBalancerMsg',
    'APIAddVmNicToSecurityGroupMsg',
    'APIAttachBackupStorageToZoneMsg',
    'APIAttachDataVolumeToVmMsg',
    'APIAttachEipMsg',
    'APIAttachIsoToVmInstanceMsg',
    'APIAttachL2NetworkToClusterMsg',
    'APIAttachL3NetworkToVmMsg',
    'APIAttachNetworkServiceProviderToL2NetworkMsg',
    'APIAttachNetworkServiceToL3NetworkMsg',
    'APIAttachOssBucketToEcsDataCenterMsg',
    'APIAttachPoliciesToUserMsg',
    'APIAttachPolicyToUserGroupMsg',
    'APIAttachPolicyToUserMsg',
    'APIAttachPortForwardingRuleMsg',
    'APIAttachPrimaryStorageToClusterMsg',
    'APIAttachSecurityGroupToL3NetworkMsg',
    'APIBackupDataVolumeMsg',
    'APIBackupVolumeSnapshotMsg',
    'APICalculateAccountSpendingMsg',
    'APICalculateAccountSpendingReply',
    'APIChangeBackupStorageStateMsg',
    'APIChangeClusterStateMsg',
    'APIChangeDiskOfferingStateMsg',
    'APIChangeEipStateMsg',
    'APIChangeHostStateMsg',
    'APIChangeImageStateMsg',
    'APIChangeInstanceOfferingMsg',
    'APIChangeInstanceOfferingStateMsg',
    'APIChangeL3NetworkStateMsg',
    'APIChangePortForwardingRuleStateMsg',
    'APIChangePrimaryStorageStateMsg',
    'APIChangeResourceOwnerMsg',
    'APIChangeSchedulerStateMsg',
    'APIChangeSecurityGroupStateMsg',
    'APIChangeVipStateMsg',
    'APIChangeVmPasswordMsg',
    'APIChangeVolumeStateMsg',
    'APIChangeZoneStateMsg',
    'APICheckApiPermissionMsg',
    'APICheckApiPermissionReply',
    'APICheckIpAvailabilityMsg',
    'APICheckIpAvailabilityReply',
    'APICleanInvalidLdapBindingMsg',
    'APICleanUpImageCacheOnPrimaryStorageMsg',
    'APICloneEcsInstanceFromLocalVmMsg',
    'APICloneVmInstanceMsg',
    'APICommitVolumeAsImageMsg',
    'APICreateAccountMsg',
    'APICreateClusterMsg',
    'APICreateDataVolumeFromVolumeSnapshotMsg',
    'APICreateDataVolumeFromVolumeTemplateMsg',
    'APICreateDataVolumeMsg',
    'APICreateDataVolumeTemplateFromVolumeMsg',
    'APICreateDiskOfferingMsg',
    'APICreateEcsImageFromLocalImageMsg',
    'APICreateEcsInstanceFromLocalImageMsg',
    'APICreateEipMsg',
    'APICreateIPsecConnectionMsg',
    'APICreateInstanceOfferingMsg',
    'APICreateL2NoVlanNetworkMsg',
    'APICreateL2VlanNetworkMsg',
    'APICreateL2VxlanNetworkMsg',
    'APICreateL2VxlanNetworkPoolMsg',
    'APICreateL3NetworkMsg',
    'APICreateLdapBindingMsg',
    'APICreateLoadBalancerListenerMsg',
    'APICreateLoadBalancerMsg',
    'APICreateMessage',
    'APICreatePolicyMsg',
    'APICreatePortForwardingRuleMsg',
    'APICreateRebootVmInstanceSchedulerMsg',
    'APICreateResourcePriceMsg',
    'APICreateRootVolumeTemplateFromRootVolumeMsg',
    'APICreateRootVolumeTemplateFromVolumeSnapshotMsg',
    'APICreateSchedulerMessage',
    'APICreateSearchIndexMsg',
    'APICreateSecurityGroupMsg',
    'APICreateStartVmInstanceSchedulerMsg',
    'APICreateStopVmInstanceSchedulerMsg',
    'APICreateSystemTagMsg',
    'APICreateUserGroupMsg',
    'APICreateUserMsg',
    'APICreateUserTagMsg',
    'APICreateVipMsg',
    'APICreateVirtualRouterOfferingMsg',
    'APICreateVirtualRouterVmMsg',
    'APICreateVmCpuAlarmMsg',
    'APICreateVmInstanceMsg',
    'APICreateVniRangeMsg',
    'APICreateVolumeSnapshotMsg',
    'APICreateVolumeSnapshotSchedulerMsg',
    'APICreateZoneMsg',
    'APIDebugSignalMsg',
    'APIDeleteAccountMsg',
    'APIDeleteAlarmMsg',
    'APIDeleteAliyunKeySecretMsg',
    'APIDeleteAllEcsInstancesFromDataCenterMsg',
    'APIDeleteBackupStorageMsg',
    'APIDeleteCephPrimaryStoragePoolMsg',
    'APIDeleteClusterMsg',
    'APIDeleteDataCenterInLocalMsg',
    'APIDeleteDataVolumeMsg',
    'APIDeleteDiskOfferingMsg',
    'APIDeleteEcsImageLocalMsg',
    'APIDeleteEcsImageRemoteMsg',
    'APIDeleteEcsInstanceMsg',
    'APIDeleteEcsSecurityGroupInLocalMsg',
    'APIDeleteEcsVSwitchInLocalMsg',
    'APIDeleteEcsVpcInLocalMsg',
    'APIDeleteEipMsg',
    'APIDeleteExportedImageFromBackupStorageMsg',
    'APIDeleteGCJobMsg',
    'APIDeleteHostMsg',
    'APIDeleteIPsecConnectionMsg',
    'APIDeleteIdentityZoneInLocalMsg',
    'APIDeleteImageMsg',
    'APIDeleteInstanceOfferingMsg',
    'APIDeleteIpRangeMsg',
    'APIDeleteL2NetworkMsg',
    'APIDeleteL3NetworkMsg',
    'APIDeleteLdapBindingMsg',
    'APIDeleteLdapServerMsg',
    'APIDeleteLoadBalancerListenerMsg',
    'APIDeleteLoadBalancerMsg',
    'APIDeleteNicQosMsg',
    'APIDeleteNotificationsMsg',
    'APIDeleteOssFileBucketNameInLocalMsg',
    'APIDeletePolicyMsg',
    'APIDeletePortForwardingRuleMsg',
    'APIDeletePrimaryStorageMsg',
    'APIDeleteResourcePriceMsg',
    'APIDeleteSchedulerMsg',
    'APIDeleteSearchIndexMsg',
    'APIDeleteSecurityGroupMsg',
    'APIDeleteSecurityGroupRuleMsg',
    'APIDeleteTagMsg',
    'APIDeleteUserGroupMsg',
    'APIDeleteUserMsg',
    'APIDeleteVCenterMsg',
    'APIDeleteVipMsg',
    'APIDeleteVmConsolePasswordMsg',
    'APIDeleteVmHostnameMsg',
    'APIDeleteVmInstanceHaLevelMsg',
    'APIDeleteVmNicFromSecurityGroupMsg',
    'APIDeleteVmSshKeyMsg',
    'APIDeleteVmStaticIpMsg',
    'APIDeleteVolumeQosMsg',
    'APIDeleteVolumeSnapshotFromBackupStorageMsg',
    'APIDeleteVolumeSnapshotMsg',
    'APIDeleteZoneMsg',
    'APIDestroyVmInstanceMsg',
    'APIDetachBackupStorageFromZoneMsg',
    'APIDetachDataVolumeFromVmMsg',
    'APIDetachEipMsg',
    'APIDetachIsoFromVmInstanceMsg',
    'APIDetachL2NetworkFromClusterMsg',
    'APIDetachL3NetworkFromVmMsg',
    'APIDetachNetworkServiceFromL3NetworkMsg',
    'APIDetachNetworkServiceProviderFromL2NetworkMsg',
    'APIDetachOssBucketToEcsDataCenterMsg',
    'APIDetachPoliciesFromUserMsg',
    'APIDetachPolicyFromUserGroupMsg',
    'APIDetachPolicyFromUserMsg',
    'APIDetachPortForwardingRuleMsg',
    'APIDetachPrimaryStorageFromClusterMsg',
    'APIDetachSecurityGroupFromL3NetworkMsg',
    'APIEcsQueryVpcFromLocalReply',
    'APIExportImageFromBackupStorageMsg',
    'APIExpungeDataVolumeMsg',
    'APIExpungeImageMsg',
    'APIExpungeVmInstanceMsg',
    'APIGenerateApiJsonTemplateMsg',
    'APIGenerateApiTypeScriptDefinitionMsg',
    'APIGenerateGroovyClassMsg',
    'APIGenerateInventoryQueryDetailsMsg',
    'APIGenerateQueryableFieldsMsg',
    'APIGenerateSqlForeignKeyMsg',
    'APIGenerateSqlIndexMsg',
    'APIGenerateSqlVOViewMsg',
    'APIGenerateTestLinkDocumentMsg',
    'APIGetAccountQuotaUsageMsg',
    'APIGetAccountQuotaUsageReply',
    'APIGetAccountReply',
    'APIGetBackupStorageCapacityMsg',
    'APIGetBackupStorageCapacityReply',
    'APIGetBackupStorageReply',
    'APIGetBackupStorageTypesMsg',
    'APIGetBackupStorageTypesReply',
    'APIGetCandidateBackupStorageForCreatingImageMsg',
    'APIGetCandidateBackupStorageForCreatingImageReply',
    'APIGetCandidateIsoForAttachingVmMsg',
    'APIGetCandidateIsoForAttachingVmReply',
    'APIGetCandidateVmForAttachingIsoMsg',
    'APIGetCandidateVmForAttachingIsoReply',
    'APIGetCandidateVmNicForSecurityGroupMsg',
    'APIGetCandidateVmNicForSecurityGroupReply',
    'APIGetCandidateVmNicsForLoadBalancerMsg',
    'APIGetCandidateVmNicsForLoadBalancerReply',
    'APIGetCandidateZonesClustersHostsForCreatingVmMsg',
    'APIGetCandidateZonesClustersHostsForCreatingVmReply',
    'APIGetClusterReply',
    'APIGetCpuMemoryCapacityMsg',
    'APIGetCpuMemoryCapacityReply',
    'APIGetCurrentTimeMsg',
    'APIGetCurrentTimeReply',
    'APIGetDataCenterFromRemoteMsg',
    'APIGetDataCenterFromRemoteReply',
    'APIGetDataVolumeAttachableVmMsg',
    'APIGetDataVolumeAttachableVmReply',
    'APIGetDiskOfferingReply',
    'APIGetEcsInstanceVncUrlMsg',
    'APIGetEcsInstanceVncUrlReply',
    'APIGetEipAttachableVmNicsMsg',
    'APIGetEipAttachableVmNicsReply',
    'APIGetFreeIpMsg',
    'APIGetFreeIpReply',
    'APIGetGlobalConfigMsg',
    'APIGetGlobalConfigReply',
    'APIGetGlobalPropertyMsg',
    'APIGetGlobalPropertyReply',
    'APIGetHostAllocatorStrategiesMsg',
    'APIGetHostAllocatorStrategiesReply',
    'APIGetHostMonitoringDataMsg',
    'APIGetHostMonitoringDataReply',
    'APIGetHostReply',
    'APIGetHypervisorTypesMsg',
    'APIGetHypervisorTypesReply',
    'APIGetIdentityZoneFromRemoteMsg',
    'APIGetIdentityZoneFromRemoteReply',
    'APIGetImageQgaMsg',
    'APIGetImageQgaReply',
    'APIGetImageReply',
    'APIGetInstanceOfferingReply',
    'APIGetInterdependentL3NetworkImageReply',
    'APIGetInterdependentL3NetworksImagesMsg',
    'APIGetIpAddressCapacityMsg',
    'APIGetIpAddressCapacityReply',
    'APIGetL2NetworkReply',
    'APIGetL2NetworkTypesMsg',
    'APIGetL2NetworkTypesReply',
    'APIGetL2VlanNetworkReply',
    'APIGetL3NetworkDhcpIpAddressMsg',
    'APIGetL3NetworkDhcpIpAddressReply',
    'APIGetL3NetworkReply',
    'APIGetL3NetworkTypesMsg',
    'APIGetL3NetworkTypesReply',
    'APIGetLicenseCapabilitiesMsg',
    'APIGetLicenseCapabilitiesReply',
    'APIGetLicenseInfoMsg',
    'APIGetLicenseInfoReply',
    'APIGetLocalStorageHostDiskCapacityMsg',
    'APIGetLocalStorageHostDiskCapacityReply',
    'APIGetNetworkServiceProviderReply',
    'APIGetNetworkServiceTypesMsg',
    'APIGetNetworkServiceTypesReply',
    'APIGetNicQosMsg',
    'APIGetNicQosReply',
    'APIGetOssBucketNameFromRemoteMsg',
    'APIGetOssBucketNameFromRemoteReply',
    'APIGetPolicyReply',
    'APIGetPortForwardingAttachableVmNicsMsg',
    'APIGetPortForwardingAttachableVmNicsReply',
    'APIGetPrimaryStorageAllocatorStrategiesMsg',
    'APIGetPrimaryStorageAllocatorStrategiesReply',
    'APIGetPrimaryStorageCapacityMsg',
    'APIGetPrimaryStorageCapacityReply',
    'APIGetPrimaryStorageReply',
    'APIGetPrimaryStorageTypesMsg',
    'APIGetPrimaryStorageTypesReply',
    'APIGetResourceAccountMsg',
    'APIGetResourceAccountReply',
    'APIGetSftpBackupStorageReply',
    'APIGetTaskProgressMsg',
    'APIGetTaskProgressReply',
    'APIGetUserGroupReply',
    'APIGetUserReply',
    'APIGetVCenterDVSwitchesMsg',
    'APIGetVCenterDVSwitchesReply',
    'APIGetVersionMsg',
    'APIGetVersionReply',
    'APIGetVirtualRouterOfferingReply',
    'APIGetVmAttachableDataVolumeMsg',
    'APIGetVmAttachableDataVolumeReply',
    'APIGetVmAttachableL3NetworkMsg',
    'APIGetVmAttachableL3NetworkReply',
    'APIGetVmBootOrderMsg',
    'APIGetVmBootOrderReply',
    'APIGetVmCapabilitiesMsg',
    'APIGetVmCapabilitiesReply',
    'APIGetVmConsoleAddressMsg',
    'APIGetVmConsoleAddressReply',
    'APIGetVmConsolePasswordMsg',
    'APIGetVmConsolePasswordReply',
    'APIGetVmHostnameMsg',
    'APIGetVmHostnameReply',
    'APIGetVmInstanceHaLevelMsg',
    'APIGetVmInstanceHaLevelReply',
    'APIGetVmInstanceReply',
    'APIGetVmMigrationCandidateHostsMsg',
    'APIGetVmMigrationCandidateHostsReply',
    'APIGetVmMonitoringDataMsg',
    'APIGetVmMonitoringDataReply',
    'APIGetVmQgaMsg',
    'APIGetVmQgaReply',
    'APIGetVmSshKeyMsg',
    'APIGetVmSshKeyReply',
    'APIGetVmStartingCandidateClustersHostsMsg',
    'APIGetVmStartingCandidateClustersHostsReply',
    'APIGetVolumeCapabilitiesMsg',
    'APIGetVolumeCapabilitiesReply',
    'APIGetVolumeFormatMsg',
    'APIGetVolumeFormatReply',
    'APIGetVolumeQosMsg',
    'APIGetVolumeQosReply',
    'APIGetVolumeReply',
    'APIGetVolumeSnapshotTreeMsg',
    'APIGetVolumeSnapshotTreeReply',
    'APIGetZoneMsg',
    'APIGetZoneReply',
    'APIIsReadyToGoMsg',
    'APIIsReadyToGoReply',
    'APIKvmRunShellMsg',
    'APIListAccountReply',
    'APIListApplianceVmReply',
    'APIListBackupStorageReply',
    'APIListClusterReply',
    'APIListDiskOfferingReply',
    'APIListGlobalConfigReply',
    'APIListHostReply',
    'APIListImageReply',
    'APIListInstanceOfferingReply',
    'APIListIpRangeReply',
    'APIListL2NetworkReply',
    'APIListL2VlanNetworkReply',
    'APIListL3NetworkReply',
    'APIListManagementNodeReply',
    'APIListNetworkServiceProviderReply',
    'APIListPolicyReply',
    'APIListPortForwardingRuleReply',
    'APIListPrimaryStorageReply',
    'APIListSecurityGroupReply',
    'APIListUserReply',
    'APIListVmInstanceReply',
    'APIListVmNicInSecurityGroupReply',
    'APIListVmNicReply',
    'APIListVolumeReply',
    'APIListZonesReply',
    'APILocalStorageGetVolumeMigratableHostsMsg',
    'APILocalStorageGetVolumeMigratableReply',
    'APILocalStorageMigrateVolumeMsg',
    'APILogInByAccountMsg',
    'APILogInByLdapMsg',
    'APILogInByLdapReply',
    'APILogInByUserMsg',
    'APILogInReply',
    'APILogOutMsg',
    'APILogOutReply',
    'APIMigrateVmMsg',
    'APIMonitoringPassThroughMsg',
    'APIMonitoringPassThroughReply',
    'APIPauseVmInstanceMsg',
    'APIPrometheusQueryLabelValuesMsg',
    'APIPrometheusQueryLabelValuesReply',
    'APIPrometheusQueryMetadataMsg',
    'APIPrometheusQueryMetadataReply',
    'APIPrometheusQueryPassThroughMsg',
    'APIPrometheusQueryVmMonitoringDataMsg',
    'APIPrometheusQueryVmMonitoringDataReply',
    'APIQueryAccountMsg',
    'APIQueryAccountReply',
    'APIQueryAccountResourceRefMsg',
    'APIQueryAccountResourceRefReply',
    'APIQueryAliyunKeySecretMsg',
    'APIQueryAliyunKeySecretReply',
    'APIQueryApplianceVmMsg',
    'APIQueryApplianceVmReply',
    'APIQueryBackupStorageMsg',
    'APIQueryBackupStorageReply',
    'APIQueryCephBackupStorageMsg',
    'APIQueryCephPrimaryStorageMsg',
    'APIQueryCephPrimaryStoragePoolMsg',
    'APIQueryCephPrimaryStoragePoolReply',
    'APIQueryClusterMsg',
    'APIQueryClusterReply',
    'APIQueryConsoleProxyAgentMsg',
    'APIQueryConsoleProxyAgentReply',
    'APIQueryDataCenterFromLocalMsg',
    'APIQueryDataCenterFromLocalReply',
    'APIQueryDiskOfferingMsg',
    'APIQueryDiskOfferingReply',
    'APIQueryEcsImageFromLocalMsg',
    'APIQueryEcsImageFromLocalReply',
    'APIQueryEcsInstanceFromLocalMsg',
    'APIQueryEcsInstanceFromLocalReply',
    'APIQueryEcsSecurityGroupFromLocalMsg',
    'APIQueryEcsSecurityGroupFromLocalReply',
    'APIQueryEcsSecurityGroupRuleFromLocalMsg',
    'APIQueryEcsSecurityGroupRuleFromLocalReply',
    'APIQueryEcsVSwitchFromLocalMsg',
    'APIQueryEcsVSwitchFromLocalReply',
    'APIQueryEcsVpcFromLocalMsg',
    'APIQueryEipMsg',
    'APIQueryEipReply',
    'APIQueryFusionstorBackupStorageMsg',
    'APIQueryFusionstorPrimaryStorageMsg',
    'APIQueryGCJobMsg',
    'APIQueryGCJobReply',
    'APIQueryGlobalConfigMsg',
    'APIQueryGlobalConfigReply',
    'APIQueryHostMsg',
    'APIQueryHostReply',
    'APIQueryHybridEipFromLocalMsg',
    'APIQueryHybridEipFromLocalReply',
    'APIQueryIPSecConnectionMsg',
    'APIQueryIPSecConnectionReply',
    'APIQueryIdentityZoneFromLocalMsg',
    'APIQueryIdentityZoneFromLocalReply',
    'APIQueryImageMsg',
    'APIQueryImageReply',
    'APIQueryImageStoreBackupStorageMsg',
    'APIQueryImageStoreBackupStorageReply',
    'APIQueryInstanceOfferingMsg',
    'APIQueryInstanceOfferingReply',
    'APIQueryIpRangeMsg',
    'APIQueryIpRangeReply',
    'APIQueryL2NetworkMsg',
    'APIQueryL2NetworkReply',
    'APIQueryL2VlanNetworkMsg',
    'APIQueryL2VlanNetworkReply',
    'APIQueryL2VxlanNetworkMsg',
    'APIQueryL2VxlanNetworkPoolMsg',
    'APIQueryL2VxlanNetworkPoolReply',
    'APIQueryL2VxlanNetworkReply',
    'APIQueryL3NetworkMsg',
    'APIQueryL3NetworkReply',
    'APIQueryLdapBindingMsg',
    'APIQueryLdapBindingReply',
    'APIQueryLdapServerMsg',
    'APIQueryLdapServerReply',
    'APIQueryLoadBalancerListenerMsg',
    'APIQueryLoadBalancerListenerReply',
    'APIQueryLoadBalancerMsg',
    'APIQueryLoadBalancerReply',
    'APIQueryLocalStorageResourceRefMsg',
    'APIQueryLocalStorageResourceRefReply',
    'APIQueryManagementNodeMsg',
    'APIQueryManagementNodeReply',
    'APIQueryNetworkServiceL3NetworkRefMsg',
    'APIQueryNetworkServiceL3NetworkRefReply',
    'APIQueryNetworkServiceProviderMsg',
    'APIQueryNetworkServiceProviderReply',
    'APIQueryNotificationMsg',
    'APIQueryNotificationReply',
    'APIQueryNotificationSubscriptionMsg',
    'APIQueryNotificationSubscriptionReply',
    'APIQueryOssBucketFileNameMsg',
    'APIQueryOssBucketFileNameReply',
    'APIQueryPolicyMsg',
    'APIQueryPolicyReply',
    'APIQueryPortForwardingRuleMsg',
    'APIQueryPortForwardingRuleReply',
    'APIQueryPrimaryStorageMsg',
    'APIQueryPrimaryStorageReply',
    'APIQueryQuotaMsg',
    'APIQueryQuotaReply',
    'APIQueryReply',
    'APIQueryResourcePriceMsg',
    'APIQueryResourcePriceReply',
    'APIQuerySchedulerMsg',
    'APIQuerySchedulerReply',
    'APIQuerySecurityGroupMsg',
    'APIQuerySecurityGroupReply',
    'APIQuerySecurityGroupRuleMsg',
    'APIQuerySecurityGroupRuleReply',
    'APIQuerySftpBackupStorageMsg',
    'APIQuerySftpBackupStorageReply',
    'APIQueryShareableVolumeVmInstanceRefMsg',
    'APIQueryShareableVolumeVmInstanceRefReply',
    'APIQuerySharedResourceMsg',
    'APIQuerySharedResourceReply',
    'APIQuerySystemTagMsg',
    'APIQuerySystemTagReply',
    'APIQueryTagMsg',
    'APIQueryTagReply',
    'APIQueryUserGroupMsg',
    'APIQueryUserGroupReply',
    'APIQueryUserMsg',
    'APIQueryUserReply',
    'APIQueryUserTagMsg',
    'APIQueryUserTagReply',
    'APIQueryVCenterBackupStorageMsg',
    'APIQueryVCenterBackupStorageReply',
    'APIQueryVCenterClusterMsg',
    'APIQueryVCenterClusterReply',
    'APIQueryVCenterDatacenterMsg',
    'APIQueryVCenterDatacenterReply',
    'APIQueryVCenterMsg',
    'APIQueryVCenterPrimaryStorageMsg',
    'APIQueryVCenterPrimaryStorageReply',
    'APIQueryVCenterReply',
    'APIQueryVipMsg',
    'APIQueryVipReply',
    'APIQueryVirtualRouterOfferingMsg',
    'APIQueryVirtualRouterOfferingReply',
    'APIQueryVirtualRouterVmMsg',
    'APIQueryVirtualRouterVmReply',
    'APIQueryVmInstanceMsg',
    'APIQueryVmInstanceReply',
    'APIQueryVmNicInSecurityGroupMsg',
    'APIQueryVmNicInSecurityGroupReply',
    'APIQueryVmNicMsg',
    'APIQueryVmNicReply',
    'APIQueryVniRangeMsg',
    'APIQueryVniRangeReply',
    'APIQueryVolumeMsg',
    'APIQueryVolumeReply',
    'APIQueryVolumeSnapshotMsg',
    'APIQueryVolumeSnapshotReply',
    'APIQueryVolumeSnapshotTreeMsg',
    'APIQueryVolumeSnapshotTreeReply',
    'APIQueryZoneMsg',
    'APIQueryZoneReply',
    'APIRebootEcsInstanceMsg',
    'APIRebootVmInstanceMsg',
    'APIReclaimSpaceFromImageStoreMsg',
    'APIReconnectBackupStorageMsg',
    'APIReconnectConsoleProxyAgentMsg',
    'APIReconnectHostMsg',
    'APIReconnectImageStoreBackupStorageMsg',
    'APIReconnectPrimaryStorageMsg',
    'APIReconnectSftpBackupStorageMsg',
    'APIReconnectVirtualRouterMsg',
    'APIRecoverDataVolumeMsg',
    'APIRecoverImageMsg',
    'APIRecoverVmInstanceMsg',
    'APIRefreshLoadBalancerMsg',
    'APIReimageVmInstanceMsg',
    'APIReloadLicenseMsg',
    'APIReloadLicenseReply',
    'APIRemoveDnsFromL3NetworkMsg',
    'APIRemoveMonFromCephBackupStorageMsg',
    'APIRemoveMonFromCephPrimaryStorageMsg',
    'APIRemoveMonFromFusionstorBackupStorageMsg',
    'APIRemoveMonFromFusionstorPrimaryStorageMsg',
    'APIRemoveUserFromGroupMsg',
    'APIRemoveVmNicFromLoadBalancerMsg',
    'APIReply',
    'APIRequestConsoleAccessMsg',
    'APIResumeVmInstanceMsg',
    'APIRevertVolumeFromSnapshotMsg',
    'APIRevokeResourceSharingMsg',
    'APIScanBackupStorageMsg',
    'APISearchAccountReply',
    'APISearchBackupStorageReply',
    'APISearchClusterReply',
    'APISearchDiskOfferingReply',
    'APISearchDnsReply',
    'APISearchGenerateSqlTriggerMsg',
    'APISearchHostReply',
    'APISearchImageReply',
    'APISearchInstanceOfferingReply',
    'APISearchL2NetworkReply',
    'APISearchL2VlanNetworkReply',
    'APISearchL3NetworkReply',
    'APISearchNetworkServiceProviderReply',
    'APISearchPolicyReply',
    'APISearchPrimaryStorageReply',
    'APISearchReply',
    'APISearchSftpBackupStorageReply',
    'APISearchUserGroupReply',
    'APISearchUserReply',
    'APISearchVirtualRouterOffingReply',
    'APISearchVirtualRouterVmReply',
    'APISearchVmInstanceReply',
    'APISearchVolumeReply',
    'APISearchZoneReply',
    'APISessionMessage',
    'APISetImageQgaMsg',
    'APISetNicQosMsg',
    'APISetVmBootOrderMsg',
    'APISetVmConsolePasswordMsg',
    'APISetVmHostnameMsg',
    'APISetVmInstanceHaLevelMsg',
    'APISetVmQgaMsg',
    'APISetVmSshKeyMsg',
    'APISetVmStaticIpMsg',
    'APISetVolumeQosMsg',
    'APIShareResourceMsg',
    'APIStartEcsInstanceMsg',
    'APIStartVmInstanceMsg',
    'APIStopEcsInstanceMsg',
    'APIStopVmInstanceMsg',
    'APISyncEcsImageFromRemoteMsg',
    'APISyncEcsInstanceFromRemoteMsg',
    'APISyncEcsSecurityGroupFromRemoteMsg',
    'APISyncEcsVSwitchFromRemoteMsg',
    'APISyncEcsVpcFromRemoteMsg',
    'APISyncImageSizeMsg',
    'APISyncPrimaryStorageCapacityMsg',
    'APISyncVolumeSizeMsg',
    'APITriggerGCJobMsg',
    'APIUpdateAccountMsg',
    'APIUpdateAlertMsg',
    'APIUpdateBackupStorageMsg',
    'APIUpdateCephBackupStorageMonMsg',
    'APIUpdateCephPrimaryStorageMonMsg',
    'APIUpdateClusterMsg',
    'APIUpdateDiskOfferingMsg',
    'APIUpdateEcsInstanceVncPasswordMsg',
    'APIUpdateEipMsg',
    'APIUpdateEncryptKeyMsg',
    'APIUpdateFusionstorBackupStorageMonMsg',
    'APIUpdateFusionstorPrimaryStorageMonMsg',
    'APIUpdateGlobalConfigMsg',
    'APIUpdateHostMsg',
    'APIUpdateImageMsg',
    'APIUpdateImageStoreBackupStorageMsg',
    'APIUpdateInstanceOfferingMsg',
    'APIUpdateIpRangeMsg',
    'APIUpdateKVMHostMsg',
    'APIUpdateL2NetworkMsg',
    'APIUpdateL3NetworkMsg',
    'APIUpdateLdapServerMsg',
    'APIUpdateNotificationsStatusMsg',
    'APIUpdatePortForwardingRuleMsg',
    'APIUpdatePrimaryStorageMsg',
    'APIUpdateQuotaMsg',
    'APIUpdateSchedulerMsg',
    'APIUpdateSecurityGroupMsg',
    'APIUpdateSftpBackupStorageMsg',
    'APIUpdateSystemTagMsg',
    'APIUpdateUserGroupMsg',
    'APIUpdateUserMsg',
    'APIUpdateVCenterMsg',
    'APIUpdateVipMsg',
    'APIUpdateVirtualRouterOfferingMsg',
    'APIUpdateVmInstanceMsg',
    'APIUpdateVolumeMsg',
    'APIUpdateVolumeSnapshotMsg',
    'APIUpdateZoneMsg',
    'APIValidateSessionMsg',
    'APIValidateSessionReply',
    'CreateTemplateFromVolumeOnPrimaryStorageReply',
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
        self.agentPort = None

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

        if hasattr(inv, 'agentPort'):
            self.agentPort = inv.agentPort
        else:
            self.agentPort = None



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



class EcsInstanceConsoleProxyInventory(object):
    def __init__(self):
        self.uuid = None
        self.ecsInstanceUuid = None
        self.vncUrl = None
        self.vncPassword = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'ecsInstanceUuid'):
            self.ecsInstanceUuid = inv.ecsInstanceUuid
        else:
            self.ecsInstanceUuid = None

        if hasattr(inv, 'vncUrl'):
            self.vncUrl = inv.vncUrl
        else:
            self.vncUrl = None

        if hasattr(inv, 'vncPassword'):
            self.vncPassword = inv.vncPassword
        else:
            self.vncPassword = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class EcsInstanceInventory(object):
    def __init__(self):
        self.uuid = None
        self.localVmInstanceUuid = None
        self.ecsInstanceId = None
        self.name = None
        self.ecsStatus = None
        self.ecsInstanceRootPassword = None
        self.cpuCores = None
        self.memorySize = None
        self.ecsInstanceType = None
        self.ecsBandWidth = None
        self.ecsRootVolumeId = None
        self.ecsRootVolumeCategory = None
        self.ecsRootVolumeSize = None
        self.privateIpAddresse = None
        self.ecsEipUuid = None
        self.ecsVpcUuid = None
        self.ecsVSwitchUuid = None
        self.ecsImageUuid = None
        self.ecsSecurityGroupUuid = None
        self.identityZoneUuid = None
        self.createDate = None
        self.lastOpDate = None
        self.description = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'localVmInstanceUuid'):
            self.localVmInstanceUuid = inv.localVmInstanceUuid
        else:
            self.localVmInstanceUuid = None

        if hasattr(inv, 'ecsInstanceId'):
            self.ecsInstanceId = inv.ecsInstanceId
        else:
            self.ecsInstanceId = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'ecsStatus'):
            self.ecsStatus = inv.ecsStatus
        else:
            self.ecsStatus = None

        if hasattr(inv, 'ecsInstanceRootPassword'):
            self.ecsInstanceRootPassword = inv.ecsInstanceRootPassword
        else:
            self.ecsInstanceRootPassword = None

        if hasattr(inv, 'cpuCores'):
            self.cpuCores = inv.cpuCores
        else:
            self.cpuCores = None

        if hasattr(inv, 'memorySize'):
            self.memorySize = inv.memorySize
        else:
            self.memorySize = None

        if hasattr(inv, 'ecsInstanceType'):
            self.ecsInstanceType = inv.ecsInstanceType
        else:
            self.ecsInstanceType = None

        if hasattr(inv, 'ecsBandWidth'):
            self.ecsBandWidth = inv.ecsBandWidth
        else:
            self.ecsBandWidth = None

        if hasattr(inv, 'ecsRootVolumeId'):
            self.ecsRootVolumeId = inv.ecsRootVolumeId
        else:
            self.ecsRootVolumeId = None

        if hasattr(inv, 'ecsRootVolumeCategory'):
            self.ecsRootVolumeCategory = inv.ecsRootVolumeCategory
        else:
            self.ecsRootVolumeCategory = None

        if hasattr(inv, 'ecsRootVolumeSize'):
            self.ecsRootVolumeSize = inv.ecsRootVolumeSize
        else:
            self.ecsRootVolumeSize = None

        if hasattr(inv, 'privateIpAddresse'):
            self.privateIpAddresse = inv.privateIpAddresse
        else:
            self.privateIpAddresse = None

        if hasattr(inv, 'ecsEipUuid'):
            self.ecsEipUuid = inv.ecsEipUuid
        else:
            self.ecsEipUuid = None

        if hasattr(inv, 'ecsVpcUuid'):
            self.ecsVpcUuid = inv.ecsVpcUuid
        else:
            self.ecsVpcUuid = None

        if hasattr(inv, 'ecsVSwitchUuid'):
            self.ecsVSwitchUuid = inv.ecsVSwitchUuid
        else:
            self.ecsVSwitchUuid = None

        if hasattr(inv, 'ecsImageUuid'):
            self.ecsImageUuid = inv.ecsImageUuid
        else:
            self.ecsImageUuid = None

        if hasattr(inv, 'ecsSecurityGroupUuid'):
            self.ecsSecurityGroupUuid = inv.ecsSecurityGroupUuid
        else:
            self.ecsSecurityGroupUuid = None

        if hasattr(inv, 'identityZoneUuid'):
            self.identityZoneUuid = inv.identityZoneUuid
        else:
            self.identityZoneUuid = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None



class EcsImageInventory(object):
    def __init__(self):
        self.uuid = None
        self.localImageUuid = None
        self.ecsImageId = None
        self.name = None
        self.ecsImageSize = None
        self.description = None
        self.dataCenterUuid = None
        self.platform = None
        self.type = None
        self.ossMd5Sum = None
        self.format = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'localImageUuid'):
            self.localImageUuid = inv.localImageUuid
        else:
            self.localImageUuid = None

        if hasattr(inv, 'ecsImageId'):
            self.ecsImageId = inv.ecsImageId
        else:
            self.ecsImageId = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'ecsImageSize'):
            self.ecsImageSize = inv.ecsImageSize
        else:
            self.ecsImageSize = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'dataCenterUuid'):
            self.dataCenterUuid = inv.dataCenterUuid
        else:
            self.dataCenterUuid = None

        if hasattr(inv, 'platform'):
            self.platform = inv.platform
        else:
            self.platform = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'ossMd5Sum'):
            self.ossMd5Sum = inv.ossMd5Sum
        else:
            self.ossMd5Sum = None

        if hasattr(inv, 'format'):
            self.format = inv.format
        else:
            self.format = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class EcsImageMd5SumMappingInventory(object):
    def __init__(self):
        self.id = None
        self.qcow2Md5Sum = None
        self.rawMd5Sum = None
        self.ossBucketName = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'id'):
            self.id = inv.id
        else:
            self.id = None

        if hasattr(inv, 'qcow2Md5Sum'):
            self.qcow2Md5Sum = inv.qcow2Md5Sum
        else:
            self.qcow2Md5Sum = None

        if hasattr(inv, 'rawMd5Sum'):
            self.rawMd5Sum = inv.rawMd5Sum
        else:
            self.rawMd5Sum = None

        if hasattr(inv, 'ossBucketName'):
            self.ossBucketName = inv.ossBucketName
        else:
            self.ossBucketName = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class EcsSecurityGroupInventory(object):
    def __init__(self):
        self.uuid = None
        self.ecsVpcUuid = None
        self.securityGroupId = None
        self.securityGroupName = None
        self.description = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'ecsVpcUuid'):
            self.ecsVpcUuid = inv.ecsVpcUuid
        else:
            self.ecsVpcUuid = None

        if hasattr(inv, 'securityGroupId'):
            self.securityGroupId = inv.securityGroupId
        else:
            self.securityGroupId = None

        if hasattr(inv, 'securityGroupName'):
            self.securityGroupName = inv.securityGroupName
        else:
            self.securityGroupName = None

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



class EcsSecurityGroupRuleInventory(object):
    def __init__(self):
        self.uuid = None
        self.ecsSecurityGroupUuid = None
        self.protocol = None
        self.portRange = None
        self.cidrIp = None
        self.priority = None
        self.direction = None
        self.nicType = None
        self.policy = None
        self.sourceGroupId = None
        self.description = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'ecsSecurityGroupUuid'):
            self.ecsSecurityGroupUuid = inv.ecsSecurityGroupUuid
        else:
            self.ecsSecurityGroupUuid = None

        if hasattr(inv, 'protocol'):
            self.protocol = inv.protocol
        else:
            self.protocol = None

        if hasattr(inv, 'portRange'):
            self.portRange = inv.portRange
        else:
            self.portRange = None

        if hasattr(inv, 'cidrIp'):
            self.cidrIp = inv.cidrIp
        else:
            self.cidrIp = None

        if hasattr(inv, 'priority'):
            self.priority = inv.priority
        else:
            self.priority = None

        if hasattr(inv, 'direction'):
            self.direction = inv.direction
        else:
            self.direction = None

        if hasattr(inv, 'nicType'):
            self.nicType = inv.nicType
        else:
            self.nicType = None

        if hasattr(inv, 'policy'):
            self.policy = inv.policy
        else:
            self.policy = None

        if hasattr(inv, 'sourceGroupId'):
            self.sourceGroupId = inv.sourceGroupId
        else:
            self.sourceGroupId = None

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



class EcsVSwitchInventory(object):
    def __init__(self):
        self.uuid = None
        self.vSwitchId = None
        self.status = None
        self.cidrBlock = None
        self.availableIpAddressCount = None
        self.description = None
        self.vSwitchName = None
        self.ecsVpcUuid = None
        self.identityZoneUuid = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'vSwitchId'):
            self.vSwitchId = inv.vSwitchId
        else:
            self.vSwitchId = None

        if hasattr(inv, 'status'):
            self.status = inv.status
        else:
            self.status = None

        if hasattr(inv, 'cidrBlock'):
            self.cidrBlock = inv.cidrBlock
        else:
            self.cidrBlock = None

        if hasattr(inv, 'availableIpAddressCount'):
            self.availableIpAddressCount = inv.availableIpAddressCount
        else:
            self.availableIpAddressCount = None

        if hasattr(inv, 'description'):
            self.description = inv.description
        else:
            self.description = None

        if hasattr(inv, 'vSwitchName'):
            self.vSwitchName = inv.vSwitchName
        else:
            self.vSwitchName = None

        if hasattr(inv, 'ecsVpcUuid'):
            self.ecsVpcUuid = inv.ecsVpcUuid
        else:
            self.ecsVpcUuid = None

        if hasattr(inv, 'identityZoneUuid'):
            self.identityZoneUuid = inv.identityZoneUuid
        else:
            self.identityZoneUuid = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class EcsVpcInventory(object):
    def __init__(self):
        self.uuid = None
        self.ecsVpcId = None
        self.dataCenterUuid = None
        self.status = None
        self.deleted = None
        self.vpcName = None
        self.cidrBlock = None
        self.vRouterId = None
        self.description = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'ecsVpcId'):
            self.ecsVpcId = inv.ecsVpcId
        else:
            self.ecsVpcId = None

        if hasattr(inv, 'dataCenterUuid'):
            self.dataCenterUuid = inv.dataCenterUuid
        else:
            self.dataCenterUuid = None

        if hasattr(inv, 'status'):
            self.status = inv.status
        else:
            self.status = None

        if hasattr(inv, 'deleted'):
            self.deleted = inv.deleted
        else:
            self.deleted = None

        if hasattr(inv, 'vpcName'):
            self.vpcName = inv.vpcName
        else:
            self.vpcName = None

        if hasattr(inv, 'cidrBlock'):
            self.cidrBlock = inv.cidrBlock
        else:
            self.cidrBlock = None

        if hasattr(inv, 'vRouterId'):
            self.vRouterId = inv.vRouterId
        else:
            self.vRouterId = None

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



class OssBucketEcsDataCenterRefInventory(object):
    def __init__(self):
        self.id = None
        self.ossBucketUuid = None
        self.dataCenterUuid = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'id'):
            self.id = inv.id
        else:
            self.id = None

        if hasattr(inv, 'ossBucketUuid'):
            self.ossBucketUuid = inv.ossBucketUuid
        else:
            self.ossBucketUuid = None

        if hasattr(inv, 'dataCenterUuid'):
            self.dataCenterUuid = inv.dataCenterUuid
        else:
            self.dataCenterUuid = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class OssBucketInventory(object):
    def __init__(self):
        self.uuid = None
        self.bucketName = None
        self.regionId = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'bucketName'):
            self.bucketName = inv.bucketName
        else:
            self.bucketName = None

        if hasattr(inv, 'regionId'):
            self.regionId = inv.regionId
        else:
            self.regionId = None

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



class SchedulerInventory(object):
    def __init__(self):
        self.uuid = None
        self.targetResourceUuid = None
        self.schedulerName = None
        self.schedulerJob = None
        self.schedulerType = None
        self.schedulerInterval = None
        self.repeatCount = None
        self.cronScheduler = None
        self.startTime = None
        self.stopTime = None
        self.createDate = None
        self.lastOpDate = None
        self.jobClassName = None
        self.jobData = None
        self.state = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'targetResourceUuid'):
            self.targetResourceUuid = inv.targetResourceUuid
        else:
            self.targetResourceUuid = None

        if hasattr(inv, 'schedulerName'):
            self.schedulerName = inv.schedulerName
        else:
            self.schedulerName = None

        if hasattr(inv, 'schedulerJob'):
            self.schedulerJob = inv.schedulerJob
        else:
            self.schedulerJob = None

        if hasattr(inv, 'schedulerType'):
            self.schedulerType = inv.schedulerType
        else:
            self.schedulerType = None

        if hasattr(inv, 'schedulerInterval'):
            self.schedulerInterval = inv.schedulerInterval
        else:
            self.schedulerInterval = None

        if hasattr(inv, 'repeatCount'):
            self.repeatCount = inv.repeatCount
        else:
            self.repeatCount = None

        if hasattr(inv, 'cronScheduler'):
            self.cronScheduler = inv.cronScheduler
        else:
            self.cronScheduler = None

        if hasattr(inv, 'startTime'):
            self.startTime = inv.startTime
        else:
            self.startTime = None

        if hasattr(inv, 'stopTime'):
            self.stopTime = inv.stopTime
        else:
            self.stopTime = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None

        if hasattr(inv, 'jobClassName'):
            self.jobClassName = inv.jobClassName
        else:
            self.jobClassName = None

        if hasattr(inv, 'jobData'):
            self.jobData = inv.jobData
        else:
            self.jobData = None

        if hasattr(inv, 'state'):
            self.state = inv.state
        else:
            self.state = None



class DataCenterInventory(object):
    def __init__(self):
        self.uuid = None
        self.deleted = None
        self.regionName = None
        self.dcType = None
        self.regionId = None
        self.defaultVpc = None
        self.description = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'deleted'):
            self.deleted = inv.deleted
        else:
            self.deleted = None

        if hasattr(inv, 'regionName'):
            self.regionName = inv.regionName
        else:
            self.regionName = None

        if hasattr(inv, 'dcType'):
            self.dcType = inv.dcType
        else:
            self.dcType = None

        if hasattr(inv, 'regionId'):
            self.regionId = inv.regionId
        else:
            self.regionId = None

        if hasattr(inv, 'defaultVpc'):
            self.defaultVpc = inv.defaultVpc
        else:
            self.defaultVpc = None

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



class HybridEipAddressInventory(object):
    def __init__(self):
        self.uuid = None
        self.eipId = None
        self.bandWidth = None
        self.allocateResourceUuid = None
        self.allocateResourceType = None
        self.status = None
        self.eipAddress = None
        self.eipType = None
        self.description = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'eipId'):
            self.eipId = inv.eipId
        else:
            self.eipId = None

        if hasattr(inv, 'bandWidth'):
            self.bandWidth = inv.bandWidth
        else:
            self.bandWidth = None

        if hasattr(inv, 'allocateResourceUuid'):
            self.allocateResourceUuid = inv.allocateResourceUuid
        else:
            self.allocateResourceUuid = None

        if hasattr(inv, 'allocateResourceType'):
            self.allocateResourceType = inv.allocateResourceType
        else:
            self.allocateResourceType = None

        if hasattr(inv, 'status'):
            self.status = inv.status
        else:
            self.status = None

        if hasattr(inv, 'eipAddress'):
            self.eipAddress = inv.eipAddress
        else:
            self.eipAddress = None

        if hasattr(inv, 'eipType'):
            self.eipType = inv.eipType
        else:
            self.eipType = None

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



class AvailableIdentityZonesInventory(object):
    def __init__(self):
        self.uuid = None
        self.accountUuid = None
        self.zoneId = None
        self.type = None
        self.dataCenterUuid = None
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

        if hasattr(inv, 'zoneId'):
            self.zoneId = inv.zoneId
        else:
            self.zoneId = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'dataCenterUuid'):
            self.dataCenterUuid = inv.dataCenterUuid
        else:
            self.dataCenterUuid = None

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



class AvailableInstanceTypeInventory(object):
    def __init__(self):
        self.uuid = None
        self.accountUuid = None
        self.instanceType = None
        self.diskCategories = None
        self.resourceType = None
        self.izUuid = None
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

        if hasattr(inv, 'instanceType'):
            self.instanceType = inv.instanceType
        else:
            self.instanceType = None

        if hasattr(inv, 'diskCategories'):
            self.diskCategories = inv.diskCategories
        else:
            self.diskCategories = None

        if hasattr(inv, 'resourceType'):
            self.resourceType = inv.resourceType
        else:
            self.resourceType = None

        if hasattr(inv, 'izUuid'):
            self.izUuid = inv.izUuid
        else:
            self.izUuid = None

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



class IdentityZoneInventory(object):
    def __init__(self):
        self.uuid = None
        self.deleted = None
        self.dataCenterUuid = None
        self.zoneId = None
        self.type = None
        self.zoneName = None
        self.defaultVSwitch = None
        self.description = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'deleted'):
            self.deleted = inv.deleted
        else:
            self.deleted = None

        if hasattr(inv, 'dataCenterUuid'):
            self.dataCenterUuid = inv.dataCenterUuid
        else:
            self.dataCenterUuid = None

        if hasattr(inv, 'zoneId'):
            self.zoneId = inv.zoneId
        else:
            self.zoneId = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'zoneName'):
            self.zoneName = inv.zoneName
        else:
            self.zoneName = None

        if hasattr(inv, 'defaultVSwitch'):
            self.defaultVSwitch = inv.defaultVSwitch
        else:
            self.defaultVSwitch = None

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



class ImageInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.exportUrl = None
        self.state = None
        self.status = None
        self.size = None
        self.actualSize = None
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

        if hasattr(inv, 'exportUrl'):
            self.exportUrl = inv.exportUrl
        else:
            self.exportUrl = None

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

        if hasattr(inv, 'actualSize'):
            self.actualSize = inv.actualSize
        else:
            self.actualSize = None

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
        self.actualSize = None
        self.deviceId = None
        self.state = None
        self.status = None
        self.createDate = None
        self.lastOpDate = None
        self.isShareable = None

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

        if hasattr(inv, 'actualSize'):
            self.actualSize = inv.actualSize
        else:
            self.actualSize = None

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

        if hasattr(inv, 'isShareable'):
            self.isShareable = inv.isShareable
        else:
            self.isShareable = None



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



class HybridAccountInventory(object):
    def __init__(self):
        self.uuid = None
        self.accountUuid = None
        self.userUuid = None
        self.type = None
        self.key = None
        self.secret = None
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

        if hasattr(inv, 'userUuid'):
            self.userUuid = inv.userUuid
        else:
            self.userUuid = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'key'):
            self.key = inv.key
        else:
            self.key = None

        if hasattr(inv, 'secret'):
            self.secret = inv.secret
        else:
            self.secret = None

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



class KVMHostInventory(HostInventory):
    def __init__(self):
        super(KVMHostInventory, self).__init__()
        self.username = None
        self.password = None
        self.sshPort = None

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

        if hasattr(inv, 'sshPort'):
            self.sshPort = inv.sshPort
        else:
            self.sshPort = None



class LdapAccountRefInventory(object):
    def __init__(self):
        self.uuid = None
        self.ldapUid = None
        self.ldapServerUuid = None
        self.accountUuid = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'ldapUid'):
            self.ldapUid = inv.ldapUid
        else:
            self.ldapUid = None

        if hasattr(inv, 'ldapServerUuid'):
            self.ldapServerUuid = inv.ldapServerUuid
        else:
            self.ldapServerUuid = None

        if hasattr(inv, 'accountUuid'):
            self.accountUuid = inv.accountUuid
        else:
            self.accountUuid = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class LdapServerInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.url = None
        self.base = None
        self.username = None
        self.password = None
        self.encryption = None
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

        if hasattr(inv, 'url'):
            self.url = inv.url
        else:
            self.url = None

        if hasattr(inv, 'base'):
            self.base = inv.base
        else:
            self.base = None

        if hasattr(inv, 'username'):
            self.username = inv.username
        else:
            self.username = None

        if hasattr(inv, 'password'):
            self.password = inv.password
        else:
            self.password = None

        if hasattr(inv, 'encryption'):
            self.encryption = inv.encryption
        else:
            self.encryption = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class ShareableVolumeVmInstanceRefInventory(object):
    def __init__(self):
        self.uuid = None
        self.volumeUuid = None
        self.vmInstanceUuid = None
        self.deviceId = None
        self.createDate = None
        self.lastOpDate = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'volumeUuid'):
            self.volumeUuid = inv.volumeUuid
        else:
            self.volumeUuid = None

        if hasattr(inv, 'vmInstanceUuid'):
            self.vmInstanceUuid = inv.vmInstanceUuid
        else:
            self.vmInstanceUuid = None

        if hasattr(inv, 'deviceId'):
            self.deviceId = inv.deviceId
        else:
            self.deviceId = None

        if hasattr(inv, 'createDate'):
            self.createDate = inv.createDate
        else:
            self.createDate = None

        if hasattr(inv, 'lastOpDate'):
            self.lastOpDate = inv.lastOpDate
        else:
            self.lastOpDate = None



class VtepInventory(object):
    def __init__(self):
        self.uuid = None
        self.hostUuid = None
        self.vtepIp = None
        self.port = None
        self.type = None
        self.poolUuid = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'hostUuid'):
            self.hostUuid = inv.hostUuid
        else:
            self.hostUuid = None

        if hasattr(inv, 'vtepIp'):
            self.vtepIp = inv.vtepIp
        else:
            self.vtepIp = None

        if hasattr(inv, 'port'):
            self.port = inv.port
        else:
            self.port = None

        if hasattr(inv, 'type'):
            self.type = inv.type
        else:
            self.type = None

        if hasattr(inv, 'poolUuid'):
            self.poolUuid = inv.poolUuid
        else:
            self.poolUuid = None



class L2VxlanNetworkInventory(L2NetworkInventory):
    def __init__(self):
        super(L2VxlanNetworkInventory, self).__init__()
        self.vni = None
        self.poolUuid = None

    def evaluate(self, inv):
        super(L2VxlanNetworkInventory, self).evaluate(inv)
        if hasattr(inv, 'vni'):
            self.vni = inv.vni
        else:
            self.vni = None

        if hasattr(inv, 'poolUuid'):
            self.poolUuid = inv.poolUuid
        else:
            self.poolUuid = None



class L2VxlanNetworkPoolInventory(L2NetworkInventory):
    def __init__(self):
        super(L2VxlanNetworkPoolInventory, self).__init__()
        self.attachedVtepRefs = None
        self.attachedVxlanNetworkRefs = None
        self.attachedVniRanges = None
        self.attachedCidrs = None

    def evaluate(self, inv):
        super(L2VxlanNetworkPoolInventory, self).evaluate(inv)
        if hasattr(inv, 'attachedVtepRefs'):
            self.attachedVtepRefs = inv.attachedVtepRefs
        else:
            self.attachedVtepRefs = None

        if hasattr(inv, 'attachedVxlanNetworkRefs'):
            self.attachedVxlanNetworkRefs = inv.attachedVxlanNetworkRefs
        else:
            self.attachedVxlanNetworkRefs = None

        if hasattr(inv, 'attachedVniRanges'):
            self.attachedVniRanges = inv.attachedVniRanges
        else:
            self.attachedVniRanges = None

        if hasattr(inv, 'attachedCidrs'):
            self.attachedCidrs = inv.attachedCidrs
        else:
            self.attachedCidrs = None



class VniRangeInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.startVni = None
        self.endVni = None
        self.l2NetworkUuid = None

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

        if hasattr(inv, 'startVni'):
            self.startVni = inv.startVni
        else:
            self.startVni = None

        if hasattr(inv, 'endVni'):
            self.endVni = inv.endVni
        else:
            self.endVni = None

        if hasattr(inv, 'l2NetworkUuid'):
            self.l2NetworkUuid = inv.l2NetworkUuid
        else:
            self.l2NetworkUuid = None



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



class ImageStoreBackupStorageInventory(BackupStorageInventory):
    def __init__(self):
        super(ImageStoreBackupStorageInventory, self).__init__()
        self.hostname = None
        self.username = None
        self.sshPort = None

    def evaluate(self, inv):
        super(ImageStoreBackupStorageInventory, self).evaluate(inv)
        if hasattr(inv, 'hostname'):
            self.hostname = inv.hostname
        else:
            self.hostname = None

        if hasattr(inv, 'username'):
            self.username = inv.username
        else:
            self.username = None

        if hasattr(inv, 'sshPort'):
            self.sshPort = inv.sshPort
        else:
            self.sshPort = None



class SftpBackupStorageInventory(BackupStorageInventory):
    def __init__(self):
        super(SftpBackupStorageInventory, self).__init__()
        self.hostname = None
        self.username = None
        self.sshPort = None

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

        if hasattr(inv, 'sshPort'):
            self.sshPort = inv.sshPort
        else:
            self.sshPort = None



class ESXHostInventory(HostInventory):
    def __init__(self):
        super(ESXHostInventory, self).__init__()
        self.vCenterUuid = None
        self.morval = None

    def evaluate(self, inv):
        super(ESXHostInventory, self).evaluate(inv)
        if hasattr(inv, 'vCenterUuid'):
            self.vCenterUuid = inv.vCenterUuid
        else:
            self.vCenterUuid = None

        if hasattr(inv, 'morval'):
            self.morval = inv.morval
        else:
            self.morval = None



class VCenterBackupStorageInventory(BackupStorageInventory):
    def __init__(self):
        super(VCenterBackupStorageInventory, self).__init__()
        self.vCenterUuid = None

    def evaluate(self, inv):
        super(VCenterBackupStorageInventory, self).evaluate(inv)
        if hasattr(inv, 'vCenterUuid'):
            self.vCenterUuid = inv.vCenterUuid
        else:
            self.vCenterUuid = None



class VCenterClusterInventory(ClusterInventory):
    def __init__(self):
        super(VCenterClusterInventory, self).__init__()
        self.vCenterUuid = None
        self.morval = None

    def evaluate(self, inv):
        super(VCenterClusterInventory, self).evaluate(inv)
        if hasattr(inv, 'vCenterUuid'):
            self.vCenterUuid = inv.vCenterUuid
        else:
            self.vCenterUuid = None

        if hasattr(inv, 'morval'):
            self.morval = inv.morval
        else:
            self.morval = None



class VCenterDatacenterInventory(object):
    def __init__(self):
        self.uuid = None
        self.vCenterUuid = None
        self.name = None
        self.morval = None

    def evaluate(self, inv):
        if hasattr(inv, 'uuid'):
            self.uuid = inv.uuid
        else:
            self.uuid = None

        if hasattr(inv, 'vCenterUuid'):
            self.vCenterUuid = inv.vCenterUuid
        else:
            self.vCenterUuid = None

        if hasattr(inv, 'name'):
            self.name = inv.name
        else:
            self.name = None

        if hasattr(inv, 'morval'):
            self.morval = inv.morval
        else:
            self.morval = None



class VCenterInventory(object):
    def __init__(self):
        self.uuid = None
        self.name = None
        self.description = None
        self.domainName = None
        self.userName = None
        self.zoneUuid = None
        self.password = None
        self.https = None
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

        if hasattr(inv, 'domainName'):
            self.domainName = inv.domainName
        else:
            self.domainName = None

        if hasattr(inv, 'userName'):
            self.userName = inv.userName
        else:
            self.userName = None

        if hasattr(inv, 'zoneUuid'):
            self.zoneUuid = inv.zoneUuid
        else:
            self.zoneUuid = None

        if hasattr(inv, 'password'):
            self.password = inv.password
        else:
            self.password = None

        if hasattr(inv, 'https'):
            self.https = inv.https
        else:
            self.https = None

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



class VCenterPrimaryStorageInventory(PrimaryStorageInventory):
    def __init__(self):
        super(VCenterPrimaryStorageInventory, self).__init__()
        self.vCenterUuid = None

    def evaluate(self, inv):
        super(VCenterPrimaryStorageInventory, self).evaluate(inv)
        if hasattr(inv, 'vCenterUuid'):
            self.vCenterUuid = inv.vCenterUuid
        else:
            self.vCenterUuid = None



#AccountConstant
INITIAL_SYSTEM_ADMIN_UUID = '36c27e8ff05c4780bf6d2fa65700f22e'
INITIAL_SYSTEM_ADMIN_NAME = 'admin'
INITIAL_SYSTEM_ADMIN_PASSWORD = 'b109f3bbbc244eb82441917ed06d618b9008dd09b3befd1b5e07394c706a8bb980b1d7785e5976ec049b46df5f1326af5a2ea6d103fd07c95385ffab0cacbc86'

#AccountType
SYSTEMADMIN = 'SystemAdmin'
NORMAL = 'Normal'

#CephConstants
CEPH_BACKUP_STORAGE_TYPE = 'Ceph'
CEPH_PRIMARY_STORAGE_TYPE = 'Ceph'

#ClusterConstant
ZSTACK_CLUSTER_TYPE = 'zstack'

#ESXConstant
VMWARE_HYPERVISOR_TYPE = 'ESX'
VMWARE_IMAGE_TYPE = 'vmware'

#FusionstorConstants
FUSIONSTOR_BACKUP_STORAGE_TYPE = 'Fusionstor'
FUSIONSTOR_PRIMARY_STORAGE_TYPE = 'Fusionstor'

#ImageConstant
ZSTACK_IMAGE_TYPE = 'zstack'

#ImageStoreBackupStorageConstant
IMAGE_STORE_BACKUP_STORAGE_TYPE = 'ImageStoreBackupStorage'

#KVMConstant
KVM_HYPERVISOR_TYPE = 'KVM'

#L2NetworkConstant
L2_NO_VLAN_NETWORK_TYPE = 'L2NoVlanNetwork'
L2_VLAN_NETWORK_TYPE = 'L2VlanNetwork'

#L3NetworkConstant
L3_BASIC_NETWORK_TYPE = 'L3BasicNetwork'
FIRST_AVAILABLE_IP_ALLOCATOR_STRATEGY = 'FirstAvailableIpAllocatorStrategy'
RANDOM_IP_ALLOCATOR_STRATEGY = 'RandomIpAllocatorStrategy'

#LocalStorageConstants
LOCAL_STORAGE_TYPE = 'LocalStorage'

#MevocoKVMConstant

#NfsPrimaryStorageConstant
NFS_PRIMARY_STORAGE_TYPE = 'NFS'

#PrimaryStorageConstant
DEFAULT_PRIMARY_STORAGE_ALLOCATION_STRATEGY_TYPE = 'DefaultPrimaryStorageAllocationStrategy'

#QueryOp

#SearchOp
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

#SecurityGroupRuleProtocolType
TCP = 'TCP'
UDP = 'UDP'
ICMP = 'ICMP'

#SecurityGroupRuleType
INGRESS = 'Ingress'
EGRESS = 'Egress'

#SftpBackupStorageConstant
SFTP_BACKUP_STORAGE_TYPE = 'SftpBackupStorage'

#SimulatorBackupStorageConstant
SIMULATOR_BACKUP_STORAGE_TYPE = 'SimulatorBackupStorage'

#SimulatorConstant
SIMULATOR_HYPERVISOR_TYPE = 'Simulator'

#SimulatorPrimaryStorageConstant
SIMULATOR_PRIMARY_STORAGE_TYPE = 'SimulatorPrimaryStorage'

#VCenterConstant
VCENTER_CLUSTER_TYPE = 'vmware'
VCENTER_BACKUP_STORAGE_TYPE = 'VCenter'
VCENTER_PRIMARY_STORAGE_TYPE = 'VCenter'

#VirtualRouterConstant
VIRTUAL_ROUTER_PROVIDER_TYPE = 'VirtualRouter'
VIRTUAL_ROUTER_VM_TYPE = 'VirtualRouter'
VIRTUAL_ROUTER_OFFERING_TYPE = 'VirtualRouter'

#VirtualRouterNicMetaData
VR_PUBLIC_NIC_META = '1'
VR_MANAGEMENT_NIC_META = '2'
VR_MANAGEMENT_AND_PUBLIC_NIC_META = '3'

#VmInstanceConstant
USER_VM_TYPE = 'UserVm'

#VmInstanceState
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
PAUSING = 'Pausing'
PAUSED = 'Paused'
RESUMING = 'Resuming'
ERROR = 'Error'
UNKNOWN = 'Unknown'

#VxlanNetworkConstant
VXLAN_NETWORK_TYPE = 'VxlanNetwork'

#VxlanNetworkPoolConstant
VXLAN_NETWORK_POOL_TYPE = 'VxlanNetworkPool'
VXLAN_NETWORK_TYPE = 'VxlanNetwork'
RANDOM_VNI_ALLOCATOR_STRATEGY = 'RandomVniAllocatorStrategy'

#GlobalConfigPythonConstant
class GlobalConfig_APPLIANCEVM(object):
    SSH_TIMEOUT = 'ssh.timeout'
    CONNECT_TIMEOUT = 'connect.timeout'
    AGENT_DEPLOYONSTART = 'agent.deployOnStart'

    @staticmethod
    def get_category():
        return 'applianceVm'

class GlobalConfig_BACKUPSTORAGE(object):
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'
    RESERVEDCAPACITY = 'reservedCapacity'
    PING_INTERVAL = 'ping.interval'

    @staticmethod
    def get_category():
        return 'backupStorage'

class GlobalConfig_BILLING(object):
    SAMPLING_INTERVAL = 'sampling.interval'

    @staticmethod
    def get_category():
        return 'billing'

class GlobalConfig_CEPH(object):
    BACKUPSTORAGE_MON_RECONNECTDELAY = 'backupStorage.mon.reconnectDelay'
    BACKUPSTORAGE_MON_AUTORECONNECT = 'backupStorage.mon.autoReconnect'
    PRIMARYSTORAGE_MON_AUTORECONNECT = 'primaryStorage.mon.autoReconnect'
    IMAGECACHE_CLEANUP_INTERVAL = 'imageCache.cleanup.interval'
    PRIMARYSTORAGE_MON_RECONNECTDELAY = 'primaryStorage.mon.reconnectDelay'
    PRIMARYSTORAGE_DELETEPOOL = 'primaryStorage.deletePool'
    BACKUPSTORAGE_IMAGE_DOWNLOAD_TIMEOUT = 'backupStorage.image.download.timeout'

    @staticmethod
    def get_category():
        return 'ceph'

class GlobalConfig_CLOUDBUS(object):
    STATISTICS_ON = 'statistics.on'

    @staticmethod
    def get_category():
        return 'cloudBus'

class GlobalConfig_CONSOLE(object):
    AGENT_PING_INTERVAL = 'agent.ping.interval'
    PROXY_IDLETIMEOUT = 'proxy.idleTimeout'

    @staticmethod
    def get_category():
        return 'console'

class GlobalConfig_EIP(object):
    SNATINBOUNDTRAFFIC = 'snatInboundTraffic'

    @staticmethod
    def get_category():
        return 'eip'

class GlobalConfig_ENCRYPT(object):
    ENCRYPT_ALGORITHM = 'encrypt.algorithm'

    @staticmethod
    def get_category():
        return 'encrypt'

class GlobalConfig_FUSIONSTOR(object):
    IMAGECACHE_CLEANUP_INTERVAL = 'imageCache.cleanup.interval'
    BACKUPSTORAGE_MON_AUTORECONNECT = 'backupStorage.mon.autoReconnect'
    BACKUPSTORAGE_MON_RECONNECTDELAY = 'backupStorage.mon.reconnectDelay'
    PRIMARYSTORAGE_DELETEPOOL = 'primaryStorage.deletePool'
    PRIMARYSTORAGE_MON_RECONNECTDELAY = 'primaryStorage.mon.reconnectDelay'
    PRIMARYSTORAGE_MON_AUTORECONNECT = 'primaryStorage.mon.autoReconnect'
    BACKUPSTORAGE_IMAGE_DOWNLOAD_TIMEOUT = 'backupStorage.image.download.timeout'

    @staticmethod
    def get_category():
        return 'fusionstor'

class GlobalConfig_GC(object):
    ORPHANJOBSCANINTERVAL = 'orphanJobScanInterval'

    @staticmethod
    def get_category():
        return 'gc'

class GlobalConfig_HA(object):
    HOST_SELFFENCER_MAXATTEMPTS = 'host.selfFencer.maxAttempts'
    HOST_CHECK_SUCCESSTIMES = 'host.check.successTimes'
    ENABLE = 'enable'
    HOST_CHECK_INTERVAL = 'host.check.interval'
    NEVERSTOPVM_RETRY_DELAY = 'neverStopVm.retry.delay'
    HOST_SELFFENCER_STORAGECHECKER_TIMEOUT = 'host.selfFencer.storageChecker.timeout'
    HOST_CHECK_SUCCESSINTERVAL = 'host.check.successInterval'
    HOST_CHECK_SUCCESSRATIO = 'host.check.successRatio'
    HOST_CHECK_MAXATTEMPTS = 'host.check.maxAttempts'
    HOST_SELFFENCER_INTERVAL = 'host.selfFencer.interval'

    @staticmethod
    def get_category():
        return 'ha'

class GlobalConfig_HOST(object):
    LOAD_PARALLELISMDEGREE = 'load.parallelismDegree'
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'
    LOAD_ALL = 'load.all'
    CONNECTION_AUTORECONNECTONERROR = 'connection.autoReconnectOnError'
    CPU_OVERPROVISIONING_RATIO = 'cpu.overProvisioning.ratio'
    MAINTENANCEMODE_IGNOREERROR = 'maintenanceMode.ignoreError'
    RECONNECTALLONBOOT = 'reconnectAllOnBoot'
    PING_INTERVAL = 'ping.interval'

    @staticmethod
    def get_category():
        return 'host'

class GlobalConfig_HOSTALLOCATOR(object):
    PAGINATIONLIMIT = 'paginationLimit'
    RESERVEDCAPACITY_ZONELEVEL = 'reservedCapacity.zoneLevel'
    RESERVEDCAPACITY_HOSTLEVEL = 'reservedCapacity.hostLevel'
    USEPAGINATION = 'usePagination'
    RESERVEDCAPACITY_CLUSTERLEVEL = 'reservedCapacity.clusterLevel'

    @staticmethod
    def get_category():
        return 'hostAllocator'

class GlobalConfig_IDENTITY(object):
    SESSION_CLEANUP_INTERVAL = 'session.cleanup.interval'
    SESSION_MAXCONCURRENT = 'session.maxConcurrent'
    ACCOUNT_API_CONTROL = 'account.api.control'
    ADMIN_SHOWALLRESOURCE = 'admin.showAllResource'
    SESSION_TIMEOUT = 'session.timeout'

    @staticmethod
    def get_category():
        return 'identity'

class GlobalConfig_IMAGE(object):
    EXPUNGEPERIOD = 'expungePeriod'
    DELETIONPOLICY = 'deletionPolicy'
    DELETION_GCINTERVAL = 'deletion.gcInterval'
    ENABLERESETPASSWORD = 'enableResetPassword'
    EXPUNGEINTERVAL = 'expungeInterval'

    @staticmethod
    def get_category():
        return 'image'

class GlobalConfig_KVM(object):
    HOST_DNSCHECKALIYUN = 'host.DNSCheckAliyun'
    RESERVEDMEMORY = 'reservedMemory'
    HOST_SYNCLEVEL = 'host.syncLevel'
    VM_CPUMODE = 'vm.cpuMode'
    VM_CACHEMODE = 'vm.cacheMode'
    HOST_DNSCHECK163 = 'host.DNSCheck163'
    RESERVEDCPU = 'reservedCpu'
    VM_CONSOLEMODE = 'vm.consoleMode'
    DATAVOLUME_MAXNUM = 'dataVolume.maxNum'
    HOST_DNSCHECKLIST = 'host.DNSCheckList'
    VMSYNCONHOSTPING = 'vmSyncOnHostPing'
    REDHAT_LIVESNAPSHOTON = 'redhat.liveSnapshotOn'
    VM_MIGRATIONQUANTITY = 'vm.migrationQuantity'

    @staticmethod
    def get_category():
        return 'kvm'

class GlobalConfig_LOADBALANCER(object):
    HEALTHCHECKINTERVAL = 'healthCheckInterval'
    MAXCONNECTION = 'maxConnection'
    HEALTHCHECKTARGET = 'healthCheckTarget'
    HEALTHCHECKTIMEOUT = 'healthCheckTimeout'
    UNHEALTHYTHRESHOLD = 'unhealthyThreshold'
    CONNECTIONIDLETIMEOUT = 'connectionIdleTimeout'
    BALANCERALGORITHM = 'balancerAlgorithm'
    HEALTHYTHRESHOLD = 'healthyThreshold'

    @staticmethod
    def get_category():
        return 'loadBalancer'

class GlobalConfig_LOG(object):
    ENABLED = 'enabled'

    @staticmethod
    def get_category():
        return 'log'

class GlobalConfig_LOGGING(object):
    LOCALE = 'locale'

    @staticmethod
    def get_category():
        return 'logging'

class GlobalConfig_MANAGEMENTSERVER(object):
    NODE_HEARTBEATINTERVAL = 'node.heartbeatInterval'
    NODE_JOINDELAY = 'node.joinDelay'

    @staticmethod
    def get_category():
        return 'managementServer'

class GlobalConfig_MEVOCO(object):
    DISTRIBUTEIMAGE_CONCURRENCY = 'distributeImage.concurrency'
    APIRETRY_INTERVAL_VM = 'apiRetry.interval.vm'
    APIRETRY_VM = 'apiRetry.vm'
    OVERPROVISIONING_MEMORY = 'overProvisioning.memory'
    DISTRIBUTEIMAGE = 'distributeImage'
    THRESHOLD_PRIMARYSTORAGE_PHYSICALCAPACITY = 'threshold.primaryStorage.physicalCapacity'
    HOSTALLOCATORSTRATEGY = 'hostAllocatorStrategy'
    OVERPROVISIONING_PRIMARYSTORAGE = 'overProvisioning.primaryStorage'

    @staticmethod
    def get_category():
        return 'mevoco'

class GlobalConfig_MONITOR(object):
    HOST_INTERVAL = 'host.interval'
    VM_INTERVAL = 'vm.interval'

    @staticmethod
    def get_category():
        return 'monitor'

class GlobalConfig_NFSPRIMARYSTORAGE(object):
    DELETION_GCINTERVAL = 'deletion.gcInterval'
    MOUNT_BASE = 'mount.base'

    @staticmethod
    def get_category():
        return 'nfsPrimaryStorage'

class GlobalConfig_PORTFORWARDING(object):
    SNATINBOUNDTRAFFIC = 'snatInboundTraffic'

    @staticmethod
    def get_category():
        return 'portForwarding'

class GlobalConfig_PRIMARYSTORAGE(object):
    PING_INTERVAL = 'ping.interval'
    RESERVEDCAPACITY = 'reservedCapacity'
    IMAGECACHE_GARBAGECOLLECTOR_INTERVAL = 'imageCache.garbageCollector.interval'
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'

    @staticmethod
    def get_category():
        return 'primaryStorage'

class GlobalConfig_QUOTA(object):
    IMAGE_SIZE = 'image.size'
    VOLUME_DATA_NUM = 'volume.data.num'
    L3_NUM = 'l3.num'
    SECURITYGROUP_NUM = 'securityGroup.num'
    SCHEDULER_NUM = 'scheduler.num'
    VM_MEMORYSIZE = 'vm.memorySize'
    PORTFORWARDING_NUM = 'portForwarding.num'
    EIP_NUM = 'eip.num'
    IMAGE_NUM = 'image.num'
    VM_CPUNUM = 'vm.cpuNum'
    VM_TOTALNUM = 'vm.totalNum'
    SNAPSHOT_VOLUME_NUM = 'snapshot.volume.num'
    LOADBALANCER_NUM = 'loadBalancer.num'
    VIP_NUM = 'vip.num'
    VM_NUM = 'vm.num'
    VOLUME_CAPACITY = 'volume.capacity'

    @staticmethod
    def get_category():
        return 'quota'

class GlobalConfig_REST(object):
    COMPLETEDAPI_EXPIREDPERIOD = 'completedApi.expiredPeriod'
    EXPIREDAPI_SCANINTERVAL = 'expiredApi.scanInterval'

    @staticmethod
    def get_category():
        return 'rest'

class GlobalConfig_SECURITYGROUP(object):
    INGRESS_DEFAULTPOLICY = 'ingress.defaultPolicy'
    HOST_FAILUREWORKERINTERVAL = 'host.failureWorkerInterval'
    REFRESH_DELAYINTERVAL = 'refresh.delayInterval'
    EGRESS_DEFAULTPOLICY = 'egress.defaultPolicy'
    HOST_FAILURERESOLVEPERTIME = 'host.failureResolvePerTime'

    @staticmethod
    def get_category():
        return 'securityGroup'

class GlobalConfig_SHAREDMOUNTPOINTPRIMARYSTORAGE(object):
    DELETION_GCINTERVAL = 'deletion.gcInterval'

    @staticmethod
    def get_category():
        return 'sharedMountPointPrimaryStorage'

class GlobalConfig_VIRTUALROUTER(object):
    AGENT_DEPLOYONSTART = 'agent.deployOnStart'
    SSH_PORT = 'ssh.port'
    PING_PARALLELISMDEGREE = 'ping.parallelismDegree'
    VROUTER_PASSWORD = 'vrouter.password'
    COMMAND_PARALLELISMDEGREE = 'command.parallelismDegree'
    SSH_USERNAME = 'ssh.username'
    PING_INTERVAL = 'ping.interval'
    DNSMASQ_RESTARTAFTERNUMBEROFSIGUSER1 = 'dnsmasq.restartAfterNumberOfSIGUSER1'

    @staticmethod
    def get_category():
        return 'virtualRouter'

class GlobalConfig_VM(object):
    VIDEOTYPE = 'videoType'
    DATAVOLUME_DELETEONVMDESTROY = 'dataVolume.deleteOnVmDestroy'
    EXPUNGEPERIOD = 'expungePeriod'
    DELETIONPOLICY = 'deletionPolicy'
    CLEANTRAFFIC = 'cleanTraffic'
    INSTANCEOFFERING_SETNULLWHENDELETING = 'instanceOffering.setNullWhenDeleting'
    EXPUNGEINTERVAL = 'expungeInterval'

    @staticmethod
    def get_category():
        return 'vm'

class GlobalConfig_VOLUME(object):
    EXPUNGEPERIOD = 'expungePeriod'
    DISKOFFERING_SETNULLWHENDELETING = 'diskOffering.setNullWhenDeleting'
    DELETIONPOLICY = 'deletionPolicy'
    EXPUNGEINTERVAL = 'expungeInterval'

    @staticmethod
    def get_category():
        return 'volume'

class GlobalConfig_VOLUMESNAPSHOT(object):
    BACKUP_PARALLELISMDEGREE = 'backup.parallelismDegree'
    DELETE_PARALLELISMDEGREE = 'delete.parallelismDegree'
    INCREMENTALSNAPSHOT_MAXNUM = 'incrementalSnapshot.maxNum'

    @staticmethod
    def get_category():
        return 'volumeSnapshot'


#QueryObjectInventory
class QueryObjectAccountInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','description','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['quota','user','group','policy']
     QUERY_OBJECT_MAP = {
        'quota' : 'QueryObjectQuotaInventory',
        'user' : 'QueryObjectUserInventory',
        'group' : 'QueryObjectUserGroupInventory',
        'policy' : 'QueryObjectPolicyInventory',
     }

class QueryObjectAccountResourceRefInventory(object):
     PRIMITIVE_FIELDS = ['lastOpDate','accountUuid','resourceUuid','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectAlertInventory(object):
     PRIMITIVE_FIELDS = ['opaque','count','lastOpDate','details','uuid','status','createDate','labels','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectApplianceVmFirewallRuleInventory(object):
     PRIMITIVE_FIELDS = ['startPort','destIp','protocol','applianceVmUuid','sourceIp','lastOpDate','allowCidr','l3NetworkUuid','endPort','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectApplianceVmInventory(object):
     PRIMITIVE_FIELDS = ['cpuSpeed','zoneUuid','description','type','managementNetworkUuid','uuid','platform','defaultRouteL3NetworkUuid','applianceVmType','hostUuid','lastOpDate','instanceOfferingUuid','state','imageUuid','createDate','clusterUuid','allocatorStrategy','hypervisorType','cpuNum','defaultL3NetworkUuid','lastHostUuid','memorySize','rootVolumeUuid','name','agentPort','status','__userTag__','__systemTag__']
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

class QueryObjectAvailableIdentityZonesInventory(object):
     PRIMITIVE_FIELDS = ['lastOpDate','accountUuid','zoneId','dataCenterUuid','description','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectAvailableInstanceTypeInventory(object):
     PRIMITIVE_FIELDS = ['izUuid','diskCategories','instanceType','lastOpDate','accountUuid','description','uuid','resourceType','createDate','__userTag__','__systemTag__']
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

class QueryObjectBackupStorageZoneRefInventory(object):
     PRIMITIVE_FIELDS = ['zoneUuid','lastOpDate','id','backupStorageUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['zone','backupStorage']
     QUERY_OBJECT_MAP = {
        'zone' : 'QueryObjectZoneInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
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

class QueryObjectCephBackupStorageMonInventory(object):
     PRIMITIVE_FIELDS = ['sshPort','monUuid','hostname','monAddr','sshUsername','monPort','lastOpDate','sshPassword','backupStorageUuid','createDate','status','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
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

class QueryObjectCephPrimaryStorageMonInventory(object):
     PRIMITIVE_FIELDS = ['sshPort','monUuid','hostname','monAddr','sshUsername','monPort','lastOpDate','sshPassword','primaryStorageUuid','createDate','status','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectCephPrimaryStoragePoolInventory(object):
     PRIMITIVE_FIELDS = ['lastOpDate','description','primaryStorageUuid','uuid','poolName','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectClusterInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','zoneUuid','description','state','hypervisorType','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmInstance','zone','host','l2VlanNetwork','l2Network','primaryStorage']
     QUERY_OBJECT_MAP = {
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'zone' : 'QueryObjectZoneInventory',
        'l2VlanNetwork' : 'QueryObjectL2NetworkInventory',
        'host' : 'QueryObjectHostInventory',
        'l2Network' : 'QueryObjectL2NetworkInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
     }

class QueryObjectConsoleProxyAgentInventory(object):
     PRIMITIVE_FIELDS = ['managementIp','lastOpDate','description','state','type','uuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectConsoleProxyInventory(object):
     PRIMITIVE_FIELDS = ['agentType','scheme','proxyIdentity','uuid','targetPort','agentIp','token','proxyPort','proxyHostname','targetHostname','lastOpDate','vmInstanceUuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectDataCenterInventory(object):
     PRIMITIVE_FIELDS = ['deleted','regionId','dcType','regionName','lastOpDate','description','defaultVpc','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['ossBucket']
     QUERY_OBJECT_MAP = {
        'ossBucket' : 'QueryObjectOssBucketInventory',
     }

class QueryObjectDataVolumeUsageInventory(object):
     PRIMITIVE_FIELDS = ['volumeUuid','volumeName','lastOpDate','accountUuid','volumeStatus','id','inventory','volumeSize','dateInLong','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectDiskOfferingInventory(object):
     PRIMITIVE_FIELDS = ['diskSize','sortKey','allocatorStrategy','name','lastOpDate','description','state','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
     }

class QueryObjectESXHostInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','morval','zoneUuid','availableCpuCapacity','description','hypervisorType','totalMemoryCapacity','uuid','managementIp','name','lastOpDate','vCenterUuid','totalCpuCapacity','availableMemoryCapacity','state','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','vmInstance','zone']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectEcsImageInventory(object):
     PRIMITIVE_FIELDS = ['ossMd5Sum','ecsImageId','format','description','type','uuid','platform','name','ecsImageSize','lastOpDate','localImageUuid','dataCenterUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectEcsImageMd5SumMappingInventory(object):
     PRIMITIVE_FIELDS = ['rawMd5Sum','lastOpDate','id','ossBucketName','qcow2Md5Sum','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectEcsInstanceConsoleProxyInventory(object):
     PRIMITIVE_FIELDS = ['ecsInstanceUuid','lastOpDate','vncUrl','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectEcsInstanceInventory(object):
     PRIMITIVE_FIELDS = ['ecsInstanceType','ecsImageUuid','ecsVpcUuid','ecsRootVolumeId','identityZoneUuid','description','uuid','privateIpAddresse','ecsInstanceId','memorySize','ecsStatus','cpuCores','ecsBandWidth','ecsRootVolumeSize','ecsEipUuid','name','lastOpDate','localVmInstanceUuid','ecsVSwitchUuid','ecsSecurityGroupUuid','ecsRootVolumeCategory','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectEcsSecurityGroupInventory(object):
     PRIMITIVE_FIELDS = ['securityGroupId','securityGroupName','ecsVpcUuid','lastOpDate','description','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectEcsSecurityGroupRuleInventory(object):
     PRIMITIVE_FIELDS = ['portRange','description','priority','uuid','protocol','nicType','lastOpDate','ecsSecurityGroupUuid','cidrIp','direction','policy','sourceGroupId','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectEcsVSwitchInventory(object):
     PRIMITIVE_FIELDS = ['vSwitchName','availableIpAddressCount','vSwitchId','ecsVpcUuid','cidrBlock','identityZoneUuid','lastOpDate','description','uuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectEcsVpcInventory(object):
     PRIMITIVE_FIELDS = ['ecsVpcId','vpcName','vRouterId','deleted','cidrBlock','lastOpDate','dataCenterUuid','description','uuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectEipInventory(object):
     PRIMITIVE_FIELDS = ['guestIp','vipIp','vmNicUuid','vipUuid','name','lastOpDate','description','state','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNic','vip']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'vip' : 'QueryObjectVipInventory',
     }

class QueryObjectFusionstorBackupStorageInventory(object):
     PRIMITIVE_FIELDS = ['sshPort','availableCapacity','description','type','uuid','url','totalCapacity','fsid','name','lastOpDate','state','poolName','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['mons','mons','image','volumeSnapshot','zone']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'mons' : 'QueryObjectFusionstorBackupStorageMonInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectFusionstorBackupStorageMonInventory(object):
     PRIMITIVE_FIELDS = ['sshPort','monUuid','hostname','monAddr','sshUsername','monPort','lastOpDate','sshPassword','backupStorageUuid','createDate','status','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
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

class QueryObjectFusionstorPrimaryStorageMonInventory(object):
     PRIMITIVE_FIELDS = ['sshPort','monUuid','hostname','monAddr','sshUsername','monPort','lastOpDate','sshPassword','primaryStorageUuid','createDate','status','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectGarbageCollectorInventory(object):
     PRIMITIVE_FIELDS = ['managementNodeUuid','name','context','lastOpDate','runnerClass','type','uuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectGlobalConfigInventory(object):
     PRIMITIVE_FIELDS = ['defaultValue','name','description','category','value','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectHostCapacityInventory(object):
     PRIMITIVE_FIELDS = ['totalMemory','totalCpu','availableMemory','availableCpu','uuid','cpuSockets','totalPhysicalMemory','availablePhysicalMemory','cpuNum','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectHostInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','zoneUuid','availableCpuCapacity','description','hypervisorType','totalMemoryCapacity','uuid','managementIp','name','lastOpDate','totalCpuCapacity','availableMemoryCapacity','state','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','vmInstance','zone']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectHybridAccountInventory(object):
     PRIMITIVE_FIELDS = ['userUuid','lastOpDate','accountUuid','description','type','uuid','key','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectHybridEipAddressInventory(object):
     PRIMITIVE_FIELDS = ['bandWidth','allocateResourceType','eipType','allocateResourceUuid','eipAddress','eipId','lastOpDate','description','uuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['ecs']
     QUERY_OBJECT_MAP = {
        'ecs' : 'QueryObjectEcsInstanceInventory',
     }

class QueryObjectIPsecConnectionInventory(object):
     PRIMITIVE_FIELDS = ['authKey','transformProtocol','vipUuid','description','l3NetworkUuid','uuid','policyMode','peerAddress','authMode','policyAuthAlgorithm','policyEncryptionAlgorithm','ikeDhGroup','name','lastOpDate','state','ikeAuthAlgorithm','pfs','ikeEncryptionAlgorithm','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['peerCidrs','l3Network','vip']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'peerCidrs' : 'QueryObjectIPsecPeerCidrInventory',
        'vip' : 'QueryObjectVipInventory',
     }

class QueryObjectIPsecPeerCidrInventory(object):
     PRIMITIVE_FIELDS = ['lastOpDate','cidr','uuid','connectionUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectIdentityZoneInventory(object):
     PRIMITIVE_FIELDS = ['deleted','lastOpDate','dataCenterUuid','zoneId','description','zoneName','type','uuid','defaultVSwitch','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectImageBackupStorageRefInventory(object):
     PRIMITIVE_FIELDS = ['installPath','lastOpDate','imageUuid','backupStorageUuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','backupStorage']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
     }

class QueryObjectImageInventory(object):
     PRIMITIVE_FIELDS = ['actualSize','format','description','mediaType','type','uuid','url','platform','guestOsType','system','size','exportUrl','md5Sum','name','lastOpDate','state','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['backupStorageRefs','volume','backupStorage']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'backupStorageRefs' : 'QueryObjectImageBackupStorageRefInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
     }

class QueryObjectImageStoreBackupStorageInventory(object):
     PRIMITIVE_FIELDS = ['sshPort','availableCapacity','description','type','uuid','url','hostname','totalCapacity','name','lastOpDate','state','username','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','volumeSnapshot','zone']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectInstanceOfferingInventory(object):
     PRIMITIVE_FIELDS = ['memorySize','sortKey','cpuSpeed','allocatorStrategy','name','lastOpDate','description','state','type','uuid','cpuNum','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmInstance']
     QUERY_OBJECT_MAP = {
        'vmInstance' : 'QueryObjectVmInstanceInventory',
     }

class QueryObjectIpRangeInventory(object):
     PRIMITIVE_FIELDS = ['endIp','startIp','netmask','name','lastOpDate','description','l3NetworkUuid','uuid','gateway','networkCidr','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
     }

class QueryObjectIpUseInventory(object):
     PRIMITIVE_FIELDS = ['use','usedIpUuid','lastOpDate','details','serviceId','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectKVMHostInventory(object):
     PRIMITIVE_FIELDS = ['sshPort','clusterUuid','zoneUuid','availableCpuCapacity','description','hypervisorType','totalMemoryCapacity','uuid','managementIp','name','lastOpDate','totalCpuCapacity','availableMemoryCapacity','state','username','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','vmInstance','zone']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectL2NetworkClusterRefInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','l2NetworkUuid','lastOpDate','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','l2Network']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'l2Network' : 'QueryObjectL2NetworkInventory',
     }

class QueryObjectL2NetworkInventory(object):
     PRIMITIVE_FIELDS = ['physicalInterface','name','zoneUuid','lastOpDate','description','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','zone','cluster']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectL2VlanNetworkInventory(object):
     PRIMITIVE_FIELDS = ['vlan','physicalInterface','name','zoneUuid','lastOpDate','description','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','zone','cluster']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectL2VxlanNetworkInventory(object):
     PRIMITIVE_FIELDS = ['vni','physicalInterface','name','zoneUuid','lastOpDate','description','poolUuid','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vxlanPool','l3Network','zone','cluster']
     QUERY_OBJECT_MAP = {
        'vxlanPool' : 'QueryObjectL2VxlanNetworkPoolInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectL2VxlanNetworkPoolInventory(object):
     PRIMITIVE_FIELDS = ['physicalInterface','zoneUuid','description','type','uuid','name','lastOpDate','attachedCidrs','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['attachedVtepRefs','attachedVxlanNetworkRefs','attachedVniRanges','l2VxlanNetwork','l3Network','zone','vniRange','vtep','cluster']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'attachedVniRanges' : 'QueryObjectVniRangeInventory',
        'l2VxlanNetwork' : 'QueryObjectL2VxlanNetworkInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'attachedVtepRefs' : 'QueryObjectVtepInventory',
        'zone' : 'QueryObjectZoneInventory',
        'vniRange' : 'QueryObjectVniRangeInventory',
        'attachedVxlanNetworkRefs' : 'QueryObjectL2VxlanNetworkInventory',
        'vtep' : 'QueryObjectVtepInventory',
     }

class QueryObjectL3NetworkDnsInventory(object):
     PRIMITIVE_FIELDS = ['dns','lastOpDate','l3NetworkUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
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

class QueryObjectLdapAccountRefInventory(object):
     PRIMITIVE_FIELDS = ['lastOpDate','ldapUid','accountUuid','uuid','ldapServerUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectLdapServerInventory(object):
     PRIMITIVE_FIELDS = ['password','encryption','name','lastOpDate','description','uuid','url','base','username','createDate','__userTag__','__systemTag__']
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

class QueryObjectLoadBalancerListenerInventory(object):
     PRIMITIVE_FIELDS = ['instancePort','loadBalancerUuid','protocol','name','lastOpDate','description','uuid','loadBalancerPort','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNicRefs','loadBalancer','vmNic']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'loadBalancer' : 'QueryObjectLoadBalancerInventory',
        'vmNicRefs' : 'QueryObjectLoadBalancerListenerVmNicRefInventory',
     }

class QueryObjectLoadBalancerListenerVmNicRefInventory(object):
     PRIMITIVE_FIELDS = ['listenerUuid','vmNicUuid','lastOpDate','id','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNic','listener']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'listener' : 'QueryObjectLoadBalancerListenerInventory',
     }

class QueryObjectLocalStorageResourceRefInventory(object):
     PRIMITIVE_FIELDS = ['size','hostUuid','lastOpDate','primaryStorageUuid','resourceUuid','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume','image','snapshot']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'image' : 'QueryObjectImageInventory',
        'snapshot' : 'QueryObjectVolumeSnapshotInventory',
     }

class QueryObjectManagementNodeInventory(object):
     PRIMITIVE_FIELDS = ['hostName','joinDate','heartBeat','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectNetworkServiceL3NetworkRefInventory(object):
     PRIMITIVE_FIELDS = ['networkServiceType','networkServiceProviderUuid','l3NetworkUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','serviceProvider']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'serviceProvider' : 'QueryObjectNetworkServiceProviderInventory',
     }

class QueryObjectNetworkServiceProviderInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','description','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectNetworkServiceProviderL2NetworkRefInventory(object):
     PRIMITIVE_FIELDS = ['l2NetworkUuid','networkServiceProviderUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectNetworkServiceTypeInventory(object):
     PRIMITIVE_FIELDS = ['networkServiceProviderUuid','type','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectNotificationInventory(object):
     PRIMITIVE_FIELDS = ['opaque','type','uuid','content','sender','name','lastOpDate','arguments','time','resourceUuid','status','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectNotificationSubscriptionInventory(object):
     PRIMITIVE_FIELDS = ['filter','name','lastOpDate','description','uuid','notificationName','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectOssBucketEcsDataCenterRefInventory(object):
     PRIMITIVE_FIELDS = ['ossBucketUuid','lastOpDate','dataCenterUuid','id','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['dataCenter','ossBucket']
     QUERY_OBJECT_MAP = {
        'dataCenter' : 'QueryObjectDataCenterInventory',
        'ossBucket' : 'QueryObjectOssBucketInventory',
     }

class QueryObjectOssBucketInventory(object):
     PRIMITIVE_FIELDS = ['bucketName','regionId','lastOpDate','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['dataCenter']
     QUERY_OBJECT_MAP = {
        'dataCenter' : 'QueryObjectDataCenterInventory',
     }

class QueryObjectPolicyInventory(object):
     PRIMITIVE_FIELDS = ['name','accountUuid','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account','user','group']
     QUERY_OBJECT_MAP = {
        'user' : 'QueryObjectUserInventory',
        'account' : 'QueryObjectAccountInventory',
        'group' : 'QueryObjectUserGroupInventory',
     }

class QueryObjectPortForwardingRuleInventory(object):
     PRIMITIVE_FIELDS = ['vipUuid','description','protocolType','privatePortStart','uuid','guestIp','vipPortStart','vipIp','vipPortEnd','vmNicUuid','name','allowedCidr','lastOpDate','privatePortEnd','state','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNic','vip']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'vip' : 'QueryObjectVipInventory',
     }

class QueryObjectPriceInventory(object):
     PRIMITIVE_FIELDS = ['resourceUnit','price','lastOpDate','resourceName','uuid','timeUnit','dateInLong','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectPrimaryStorageCapacityInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','totalCapacity','lastOpDate','systemUsedCapacity','uuid','totalPhysicalCapacity','availablePhysicalCapacity','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectPrimaryStorageClusterRefInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','lastOpDate','id','primaryStorageUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['cluster','primaryStorage']
     QUERY_OBJECT_MAP = {
        'cluster' : 'QueryObjectClusterInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
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

class QueryObjectQuotaInventory(object):
     PRIMITIVE_FIELDS = ['identityType','identityUuid','name','lastOpDate','value','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account']
     QUERY_OBJECT_MAP = {
        'account' : 'QueryObjectAccountInventory',
     }

class QueryObjectRootVolumeUsageInventory(object):
     PRIMITIVE_FIELDS = ['volumeUuid','vmUuid','volumeName','lastOpDate','accountUuid','volumeStatus','id','inventory','volumeSize','dateInLong','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectSchedulerInventory(object):
     PRIMITIVE_FIELDS = ['schedulerInterval','schedulerType','targetResourceUuid','uuid','schedulerJob','cronScheduler','lastOpDate','startTime','stopTime','state','schedulerName','repeatCount','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectSecurityGroupInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','description','state','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['rules','vmNic','l3Network']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'rules' : 'QueryObjectSecurityGroupRuleInventory',
     }

class QueryObjectSecurityGroupL3NetworkRefInventory(object):
     PRIMITIVE_FIELDS = ['securityGroupUuid','lastOpDate','l3NetworkUuid','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['l3Network','securityGroup']
     QUERY_OBJECT_MAP = {
        'l3Network' : 'QueryObjectL3NetworkInventory',
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
     }

class QueryObjectSecurityGroupRuleInventory(object):
     PRIMITIVE_FIELDS = ['startPort','protocol','securityGroupUuid','allowedCidr','lastOpDate','state','type','uuid','endPort','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['securityGroup']
     QUERY_OBJECT_MAP = {
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
     }

class QueryObjectSftpBackupStorageInventory(object):
     PRIMITIVE_FIELDS = ['sshPort','availableCapacity','description','type','uuid','url','hostname','totalCapacity','name','lastOpDate','state','username','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','volumeSnapshot','zone']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectShareableVolumeVmInstanceRefInventory(object):
     PRIMITIVE_FIELDS = ['volumeUuid','lastOpDate','uuid','deviceId','vmInstanceUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectSharedResourceInventory(object):
     PRIMITIVE_FIELDS = ['receiverAccountUuid','ownerAccountUuid','lastOpDate','toPublic','resourceUuid','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectSimulatorHostInventory(object):
     PRIMITIVE_FIELDS = ['clusterUuid','zoneUuid','availableCpuCapacity','description','cpuCapacity','hypervisorType','totalMemoryCapacity','uuid','memoryCapacity','managementIp','name','lastOpDate','totalCpuCapacity','availableMemoryCapacity','state','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectSystemTagInventory(object):
     PRIMITIVE_FIELDS = ['lastOpDate','tag','type','uuid','inherent','resourceUuid','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectUserGroupInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','accountUuid','description','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account','user','policy']
     QUERY_OBJECT_MAP = {
        'user' : 'QueryObjectUserInventory',
        'account' : 'QueryObjectAccountInventory',
        'policy' : 'QueryObjectPolicyInventory',
     }

class QueryObjectUserGroupPolicyRefInventory(object):
     PRIMITIVE_FIELDS = ['policyUuid','groupUuid','lastOpDate','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['group','policy']
     QUERY_OBJECT_MAP = {
        'group' : 'QueryObjectUserGroupInventory',
        'policy' : 'QueryObjectPolicyInventory',
     }

class QueryObjectUserGroupUserRefInventory(object):
     PRIMITIVE_FIELDS = ['groupUuid','userUuid','lastOpDate','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['user','group']
     QUERY_OBJECT_MAP = {
        'user' : 'QueryObjectUserInventory',
        'group' : 'QueryObjectUserGroupInventory',
     }

class QueryObjectUserInventory(object):
     PRIMITIVE_FIELDS = ['name','lastOpDate','accountUuid','description','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['account','group','policy']
     QUERY_OBJECT_MAP = {
        'account' : 'QueryObjectAccountInventory',
        'group' : 'QueryObjectUserGroupInventory',
        'policy' : 'QueryObjectPolicyInventory',
     }

class QueryObjectUserPolicyRefInventory(object):
     PRIMITIVE_FIELDS = ['policyUuid','userUuid','lastOpDate','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['user','policy']
     QUERY_OBJECT_MAP = {
        'user' : 'QueryObjectUserInventory',
        'policy' : 'QueryObjectPolicyInventory',
     }

class QueryObjectUserTagInventory(object):
     PRIMITIVE_FIELDS = ['lastOpDate','tag','type','uuid','resourceUuid','resourceType','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVCenterBackupStorageInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','description','type','uuid','url','totalCapacity','name','lastOpDate','vCenterUuid','state','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','volumeSnapshot','zone']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectVCenterClusterInventory(object):
     PRIMITIVE_FIELDS = ['morval','name','lastOpDate','zoneUuid','vCenterUuid','description','state','hypervisorType','type','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVCenterDatacenterInventory(object):
     PRIMITIVE_FIELDS = ['morval','name','vCenterUuid','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVCenterInventory(object):
     PRIMITIVE_FIELDS = ['domainName','name','zoneUuid','lastOpDate','description','https','state','userName','uuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVCenterPrimaryStorageInventory(object):
     PRIMITIVE_FIELDS = ['availableCapacity','mountPath','zoneUuid','description','systemUsedCapacity','type','uuid','totalPhysicalCapacity','url','totalCapacity','name','lastOpDate','vCenterUuid','state','availablePhysicalCapacity','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume','volumeSnapshot','zone','cluster']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'cluster' : 'QueryObjectClusterInventory',
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'zone' : 'QueryObjectZoneInventory',
     }

class QueryObjectVipInventory(object):
     PRIMITIVE_FIELDS = ['ip','useFor','description','l3NetworkUuid','uuid','netmask','name','serviceProvider','lastOpDate','peerL3NetworkUuid','state','gateway','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['portForwarding','loadBalancer','eip']
     QUERY_OBJECT_MAP = {
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
        'loadBalancer' : 'QueryObjectLoadBalancerInventory',
        'eip' : 'QueryObjectEipInventory',
     }

class QueryObjectVirtualRouterEipRefInventory(object):
     PRIMITIVE_FIELDS = ['eipUuid','virtualRouterVmUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['eip','applianceVm']
     QUERY_OBJECT_MAP = {
        'eip' : 'QueryObjectEipInventory',
        'applianceVm' : 'QueryObjectApplianceVmInventory',
     }

class QueryObjectVirtualRouterLoadBalancerRefInventory(object):
     PRIMITIVE_FIELDS = ['loadBalancerUuid','lastOpDate','id','virtualRouterVmUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['virtualRouterVm','loadBalancer']
     QUERY_OBJECT_MAP = {
        'virtualRouterVm' : 'QueryObjectVirtualRouterVmInventory',
        'loadBalancer' : 'QueryObjectLoadBalancerInventory',
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

class QueryObjectVirtualRouterPortForwardingRuleRefInventory(object):
     PRIMITIVE_FIELDS = ['vipUuid','virtualRouterVmUuid','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['portForwarding','vip','applianceVm']
     QUERY_OBJECT_MAP = {
        'portForwarding' : 'QueryObjectPortForwardingRuleInventory',
        'vip' : 'QueryObjectVipInventory',
        'applianceVm' : 'QueryObjectApplianceVmInventory',
     }

class QueryObjectVirtualRouterVipInventory(object):
     PRIMITIVE_FIELDS = ['virtualRouterVmUuid','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vip','applianceVm']
     QUERY_OBJECT_MAP = {
        'vip' : 'QueryObjectVipInventory',
        'applianceVm' : 'QueryObjectApplianceVmInventory',
     }

class QueryObjectVirtualRouterVmInventory(object):
     PRIMITIVE_FIELDS = ['cpuSpeed','zoneUuid','description','type','managementNetworkUuid','uuid','platform','defaultRouteL3NetworkUuid','applianceVmType','hostUuid','lastOpDate','publicNetworkUuid','instanceOfferingUuid','state','imageUuid','createDate','clusterUuid','allocatorStrategy','hypervisorType','cpuNum','defaultL3NetworkUuid','lastHostUuid','memorySize','rootVolumeUuid','name','agentPort','status','__userTag__','__systemTag__']
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

class QueryObjectVmNicSecurityGroupRefInventory(object):
     PRIMITIVE_FIELDS = ['vmNicUuid','securityGroupUuid','lastOpDate','vmInstanceUuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vmNic','securityGroup']
     QUERY_OBJECT_MAP = {
        'vmNic' : 'QueryObjectVmNicInventory',
        'securityGroup' : 'QueryObjectSecurityGroupInventory',
     }

class QueryObjectVmUsageInventory(object):
     PRIMITIVE_FIELDS = ['memorySize','vmUuid','name','lastOpDate','accountUuid','id','state','inventory','cpuNum','dateInLong','rootVolumeSize','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = []
     QUERY_OBJECT_MAP = {
     }

class QueryObjectVniRangeInventory(object):
     PRIMITIVE_FIELDS = ['endVni','startVni','l2NetworkUuid','name','description','uuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vxlanPool']
     QUERY_OBJECT_MAP = {
        'vxlanPool' : 'QueryObjectL2VxlanNetworkPoolInventory',
     }

class QueryObjectVolumeInventory(object):
     PRIMITIVE_FIELDS = ['installPath','actualSize','format','description','type','uuid','deviceId','diskOfferingUuid','size','name','lastOpDate','isShareable','state','primaryStorageUuid','vmInstanceUuid','rootImageUuid','status','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['image','vmInstance','diskOffering','primaryStorage','localStorageHostRef','snapshot']
     QUERY_OBJECT_MAP = {
        'image' : 'QueryObjectImageInventory',
        'vmInstance' : 'QueryObjectVmInstanceInventory',
        'diskOffering' : 'QueryObjectDiskOfferingInventory',
        'primaryStorage' : 'QueryObjectPrimaryStorageInventory',
        'localStorageHostRef' : 'QueryObjectLocalStorageResourceRefInventory',
        'snapshot' : 'QueryObjectVolumeSnapshotInventory',
     }

class QueryObjectVolumeSnapshotBackupStorageRefInventory(object):
     PRIMITIVE_FIELDS = ['installPath','volumeSnapshotUuid','backupStorageUuid','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volumeSnapshot','backupStorage']
     QUERY_OBJECT_MAP = {
        'volumeSnapshot' : 'QueryObjectVolumeSnapshotInventory',
        'backupStorage' : 'QueryObjectBackupStorageInventory',
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

class QueryObjectVolumeSnapshotTreeInventory(object):
     PRIMITIVE_FIELDS = ['current','volumeUuid','lastOpDate','uuid','createDate','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['volume','snapshot']
     QUERY_OBJECT_MAP = {
        'volume' : 'QueryObjectVolumeInventory',
        'snapshot' : 'QueryObjectVolumeSnapshotInventory',
     }

class QueryObjectVtepInventory(object):
     PRIMITIVE_FIELDS = ['hostUuid','port','type','poolUuid','uuid','vtepIp','__userTag__','__systemTag__']
     EXPANDED_FIELDS = ['vxlanPool']
     QUERY_OBJECT_MAP = {
        'vxlanPool' : 'QueryObjectL2VxlanNetworkPoolInventory',
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


#QueryMessageInventoryMap
queryMessageInventoryMap = {
     'APIQueryAccountMsg' : QueryObjectAccountInventory,
     'APIQueryAccountResourceRefMsg' : QueryObjectAccountResourceRefInventory,
     'APIQueryAliyunKeySecretMsg' : QueryObjectHybridAccountInventory,
     'APIQueryApplianceVmMsg' : QueryObjectApplianceVmInventory,
     'APIQueryBackupStorageMsg' : QueryObjectBackupStorageInventory,
     'APIQueryCephBackupStorageMsg' : QueryObjectCephBackupStorageInventory,
     'APIQueryCephPrimaryStorageMsg' : QueryObjectCephPrimaryStorageInventory,
     'APIQueryCephPrimaryStoragePoolMsg' : QueryObjectCephPrimaryStoragePoolInventory,
     'APIQueryClusterMsg' : QueryObjectClusterInventory,
     'APIQueryConsoleProxyAgentMsg' : QueryObjectConsoleProxyAgentInventory,
     'APIQueryDataCenterFromLocalMsg' : QueryObjectDataCenterInventory,
     'APIQueryDiskOfferingMsg' : QueryObjectDiskOfferingInventory,
     'APIQueryEcsImageFromLocalMsg' : QueryObjectEcsImageInventory,
     'APIQueryEcsInstanceFromLocalMsg' : QueryObjectEcsInstanceInventory,
     'APIQueryEcsSecurityGroupFromLocalMsg' : QueryObjectEcsSecurityGroupInventory,
     'APIQueryEcsSecurityGroupRuleFromLocalMsg' : QueryObjectEcsSecurityGroupRuleInventory,
     'APIQueryEcsVSwitchFromLocalMsg' : QueryObjectEcsVSwitchInventory,
     'APIQueryEcsVpcFromLocalMsg' : QueryObjectEcsVpcInventory,
     'APIQueryEipMsg' : QueryObjectEipInventory,
     'APIQueryFusionstorBackupStorageMsg' : QueryObjectFusionstorBackupStorageInventory,
     'APIQueryFusionstorPrimaryStorageMsg' : QueryObjectFusionstorPrimaryStorageInventory,
     'APIQueryGCJobMsg' : QueryObjectGarbageCollectorInventory,
     'APIQueryGlobalConfigMsg' : QueryObjectGlobalConfigInventory,
     'APIQueryHostMsg' : QueryObjectHostInventory,
     'APIQueryHybridEipFromLocalMsg' : QueryObjectHybridEipAddressInventory,
     'APIQueryIPSecConnectionMsg' : QueryObjectIPsecConnectionInventory,
     'APIQueryIdentityZoneFromLocalMsg' : QueryObjectIdentityZoneInventory,
     'APIQueryImageMsg' : QueryObjectImageInventory,
     'APIQueryImageStoreBackupStorageMsg' : QueryObjectImageStoreBackupStorageInventory,
     'APIQueryInstanceOfferingMsg' : QueryObjectInstanceOfferingInventory,
     'APIQueryIpRangeMsg' : QueryObjectIpRangeInventory,
     'APIQueryL2NetworkMsg' : QueryObjectL2NetworkInventory,
     'APIQueryL2VlanNetworkMsg' : QueryObjectL2VlanNetworkInventory,
     'APIQueryL2VxlanNetworkPoolMsg' : QueryObjectL2VxlanNetworkInventory,
     'APIQueryL3NetworkMsg' : QueryObjectL3NetworkInventory,
     'APIQueryLdapBindingMsg' : QueryObjectLdapAccountRefInventory,
     'APIQueryLdapServerMsg' : QueryObjectLdapServerInventory,
     'APIQueryLoadBalancerListenerMsg' : QueryObjectLoadBalancerListenerInventory,
     'APIQueryLoadBalancerMsg' : QueryObjectLoadBalancerInventory,
     'APIQueryLocalStorageResourceRefMsg' : QueryObjectLocalStorageResourceRefInventory,
     'APIQueryManagementNodeMsg' : QueryObjectManagementNodeInventory,
     'APIQueryNetworkServiceL3NetworkRefMsg' : QueryObjectNetworkServiceL3NetworkRefInventory,
     'APIQueryNetworkServiceProviderMsg' : QueryObjectNetworkServiceProviderInventory,
     'APIQueryNotificationMsg' : QueryObjectNotificationInventory,
     'APIQueryNotificationSubscriptionMsg' : QueryObjectNotificationSubscriptionInventory,
     'APIQueryOssBucketFileNameMsg' : QueryObjectOssBucketInventory,
     'APIQueryPolicyMsg' : QueryObjectPolicyInventory,
     'APIQueryPortForwardingRuleMsg' : QueryObjectPortForwardingRuleInventory,
     'APIQueryPrimaryStorageMsg' : QueryObjectPrimaryStorageInventory,
     'APIQueryQuotaMsg' : QueryObjectQuotaInventory,
     'APIQueryResourcePriceMsg' : QueryObjectPriceInventory,
     'APIQuerySchedulerMsg' : QueryObjectSchedulerInventory,
     'APIQuerySecurityGroupMsg' : QueryObjectSecurityGroupInventory,
     'APIQuerySecurityGroupRuleMsg' : QueryObjectSecurityGroupRuleInventory,
     'APIQuerySftpBackupStorageMsg' : QueryObjectSftpBackupStorageInventory,
     'APIQueryShareableVolumeVmInstanceRefMsg' : QueryObjectShareableVolumeVmInstanceRefInventory,
     'APIQuerySharedResourceMsg' : QueryObjectSharedResourceInventory,
     'APIQuerySystemTagMsg' : QueryObjectSystemTagInventory,
     'APIQueryUserGroupMsg' : QueryObjectUserGroupInventory,
     'APIQueryUserMsg' : QueryObjectUserInventory,
     'APIQueryUserTagMsg' : QueryObjectUserTagInventory,
     'APIQueryVCenterBackupStorageMsg' : QueryObjectVCenterBackupStorageInventory,
     'APIQueryVCenterClusterMsg' : QueryObjectVCenterClusterInventory,
     'APIQueryVCenterDatacenterMsg' : QueryObjectVCenterDatacenterInventory,
     'APIQueryVCenterMsg' : QueryObjectVCenterInventory,
     'APIQueryVCenterPrimaryStorageMsg' : QueryObjectVCenterPrimaryStorageInventory,
     'APIQueryVipMsg' : QueryObjectVipInventory,
     'APIQueryVirtualRouterOfferingMsg' : QueryObjectVirtualRouterOfferingInventory,
     'APIQueryVirtualRouterVmMsg' : QueryObjectVirtualRouterVmInventory,
     'APIQueryVmInstanceMsg' : QueryObjectVmInstanceInventory,
     'APIQueryVmNicMsg' : QueryObjectVmNicInventory,
     'APIQueryVniRangeMsg' : QueryObjectVniRangeInventory,
     'APIQueryVolumeMsg' : QueryObjectVolumeInventory,
     'APIQueryVolumeSnapshotMsg' : QueryObjectVolumeSnapshotInventory,
     'APIQueryVolumeSnapshotTreeMsg' : QueryObjectVolumeSnapshotTreeInventory,
     'APIQueryZoneMsg' : QueryObjectZoneInventory,
}
