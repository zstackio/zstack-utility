from zstacklib.utils import log, bash, jsonobject

logger = log.get_logger(__name__)


class QmpResult(object):
    def __init__(self, result):
        # type: (dict) -> None
        self.id = result.get("id", None)
        self.error = result.get("error", None)
        self.error_class = None
        self.error_desc = None
        if self.error is not None:
            self.error_class = self.error["class"]
            self.error_desc = self.error["desc"]


def get_vm_block_nodes(domain_uuid):
    r, o, err = bash.bash_roe("virsh qemu-monitor-command %s '{\"execute\":\"query-named-block-nodes\"}' --pretty" % domain_uuid)
    if r != 0:
        raise Exception("failed to query block nodes on vm[uuid:{}], libvirt error:{}".format(domain_uuid, err))

    block_nodes = jsonobject.loads(o)["return"]
    if not block_nodes:
        raise Exception("no block nodes found on vm[uuid:{}]".format(domain_uuid))

    return block_nodes


def get_block_node_name_and_file(domain_id):
    block_nodes = get_vm_block_nodes(domain_id)
    node_name_and_files = {}
    for block_node in block_nodes:
        node_name_and_files[block_node['node-name']] = block_node["file"]
    return node_name_and_files
