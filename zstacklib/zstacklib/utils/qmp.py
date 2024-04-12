from zstacklib.utils import log, bash, jsonobject, qemu
import json
import re
from distutils.version import LooseVersion

logger = log.get_logger(__name__)
QEMU_VERSION = qemu.get_version()


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


def get_yank_instances(vm):
    r, o, e = execute_qmp_command(vm, '{"execute": "query-yank" }')
    if r != 0:
        logger.warn("query yank failed of vm[uuid: %s]" % vm)
        return None

    results = json.loads(o)['return']
    return [result['node-name'] for result in results if result.get('type') == 'block-node']


def do_yank(vm):
    instances = get_yank_instances(vm)
    if not instances:
        return False

    for instance in instances:
        execute_qmp_command(vm,
                            '{ "execute": "yank", "arguments": { "instances": [{"type":"block-node","node-name":"%s"}] } }' % instance)
    return True


def get_block_job_ids(vm):
    r, o, err = execute_qmp_command(vm, '{"execute":"query-block-jobs"}')
    if err:
        return
    jobs = json.loads(o)['return']
    return [job['device'] for job in jobs]


def block_job_cancel(vm, device):
    execute_qmp_command(vm,
                        '{"execute": "block-job-cancel", "arguments":{ "device": "%s"}}' % device)


@bash.in_bash
def execute_qmp_command(domain_id, command):
    return bash.bash_roe("virsh qemu-monitor-command %s '%s' --pretty" % (domain_id, qmp_subcmd(QEMU_VERSION, command)))


def qmp_subcmd(qemu_version, s_cmd):
    # object-add option props (removed in 6.0).
    # Specify the properties for the object as top-level arguments instead.
    # qmp command example:
    # '{"execute": "object-add", "arguments":{ "qom-type": "colo-compare", "id": "comp-%s",
    #              "props": { "primary_in": "primary-in-c-%s", "secondary_in": "secondary-in-s-%s",
    #              "outdev":"primary-out-c-%s", "iothread": "iothread%s", "vnet_hdr_support": true } } }'
    # expect results:
    # '{"execute": "object-add", "arguments": {"vnet_hdr_support": true, "iothread": "iothread%s",
    #              "secondary_in": "secondary-in-s-%s", "primary_in": "primary-in-c-%s", "id": "comp-%s",
    #              "qom-type": "colo-compare", "outdev": "primary-out-c-%s"}}'
    if LooseVersion(qemu_version) >= LooseVersion("6.0.0") and re.match(r'.*object-add.*arguments.*props.*', s_cmd):
        j_cmd = json.loads(s_cmd)
        props = j_cmd.get("arguments").get("props")
        j_cmd.get("arguments").pop("props")
        j_cmd.get("arguments").update(props)
        s_cmd = json.dumps(j_cmd)
    return s_cmd
