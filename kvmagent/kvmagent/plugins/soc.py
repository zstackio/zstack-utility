import ctypes
from kvmagent import kvmagent
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils.bash import in_bash
from zstacklib.utils import jsonobject
from soc_handler import soc_handler

logger = log.get_logger(__name__)

CARD_SO_PATH = "/opt/SSCard/sharedlib/libcheck.so"


class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None


class GetCardIDRsp(AgentRsp):
    def __init__(self):
        super(GetCardIDRsp, self).__init__()
        self.cardId = None


class SocCreateVmRsp(AgentRsp):
    def __init__(self):
        super(SocCreateVmRsp, self).__init__()


class Soc(kvmagent.KvmAgent):
    SOC_CREATE_VM_PATH = "/vm/soc/create"
    SOC_CREATE_SNAPSHOT_PATH = "/vm/soc/createSnapshot"
    SOC_DELETE_BACKUP_PATH = "/vm/soc/deleteBackup"
    SOC_DELETE_VM_PATH = "/vm/soc/delete"
    SOC_DELETE_SNAPSHOT_PATH = "/vm/soc/deleteSnapshot"
    SOC_MIGRATE_VM_PATH = "/vm/soc/migrate"
    SOC_RECOVER_FROM_BACKUP_PATH = "/vm/soc/recover"
    SOC_REVERT_SNAPSHOT_PATH = "/vm/soc/revert"
    SOC_GET_CARD_ID_PATH = "/soc/card/id"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.SOC_CREATE_VM_PATH, self.soc_create_vm)
        http_server.register_async_uri(self.SOC_CREATE_SNAPSHOT_PATH, self.soc_create_snapshot)
        http_server.register_async_uri(self.SOC_DELETE_BACKUP_PATH, self.soc_delete_backup)
        http_server.register_async_uri(self.SOC_DELETE_VM_PATH, self.soc_delete_vm)
        http_server.register_async_uri(self.SOC_DELETE_SNAPSHOT_PATH, self.soc_delete_snapshot)
        http_server.register_async_uri(self.SOC_MIGRATE_VM_PATH, self.soc_migrate_vm)
        http_server.register_async_uri(self.SOC_RECOVER_FROM_BACKUP_PATH, self.soc_recover_from_backup)
        http_server.register_async_uri(self.SOC_REVERT_SNAPSHOT_PATH, self.soc_revert_snapshot)
        http_server.register_async_uri(self.SOC_GET_CARD_ID_PATH, self.soc_get_card_id)

    def stop(self):
        pass

    @kvmagent.replyerror
    @in_bash
    def soc_get_card_id(self, req):
        rsp = GetCardIDRsp()
        opt = ctypes.create_string_buffer(1024)
        so = ctypes.cdll.LoadLibrary(CARD_SO_PATH)
        ret = so.rbow_sscard_opt_read(opt, 16)
        if ret != 16 and ret != 32 and ret != 48:
            raise Exception("get SSCard info error")
        rsp.cardId = opt.raw[0:16]
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def soc_revert_snapshot(self, req):
        rsp = AgentRsp()
        handler = soc_handler.get_soc_handler(req)
        ret, msg = handler.revert_snapshot(req)
        if ret != 0:
            rsp.success = False
            rsp.error = msg

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def soc_recover_from_backup(self, req):
        rsp = AgentRsp()
        handler = soc_handler.get_soc_handler(req)
        ret, msg = handler.recover_backup(req)
        if ret != 0:
            rsp.success = False
            rsp.error = msg

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def soc_migrate_vm(self, req):
        rsp = AgentRsp()
        handler = soc_handler.get_soc_handler(req)
        ret, msg = handler.migrate_vm(req)
        if ret != 0:
            rsp.success = False
            rsp.error = msg

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def soc_delete_snapshot(self, req):
        rsp = AgentRsp()
        handler = soc_handler.get_soc_handler(req)
        ret, msg = handler.delete_snapshot(req)
        if ret != 0:
            rsp.success = False
            rsp.error = msg

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def soc_delete_vm(self, req):
        rsp = AgentRsp()
        handler = soc_handler.get_soc_handler(req)
        ret, msg = handler.delete_vm(req)
        if ret != 0:
            rsp.success = False
            rsp.error = msg

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def soc_delete_backup(self, req):
        rsp = AgentRsp()
        handler = soc_handler.get_soc_handler(req)
        ret, msg = handler.delete_backup(req)
        if ret != 0:
            rsp.success = False
            rsp.error = msg

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def soc_create_vm(self, req):
        rsp = AgentRsp()
        handler = soc_handler.get_soc_handler(req)
        ret, msg = handler.create_vm(req)
        if ret != 0:
            rsp.success = False
            rsp.error = msg

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    @in_bash
    def soc_create_snapshot(self, req):
        rsp = AgentRsp()
        handler = soc_handler.get_soc_handler(req)
        ret, msg = handler.create_snapshot(req)
        if ret != 0:
            rsp.success = False
            rsp.error = msg

        return jsonobject.dumps(rsp)