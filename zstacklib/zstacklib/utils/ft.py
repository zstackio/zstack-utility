import json

from zstacklib.utils import bash
from zstacklib.utils import log

logger = log.get_logger(__name__)

@bash.in_bash
def execute_qmp_command(domain_id, command, error_out=False):
    r, o, e = bash.bash_roe("virsh qemu-monitor-command %s '%s' --pretty" % (domain_id, command))
    if e and "error: Timed out during operation: cannot acquire state change lock" in e:
        logger.debug("failed to execute qmp command %s" % command)
        if error_out:
            raise Exception("command not executed")
    
    return r, o, e


def check_if_need_to_update_quorum_children(vmInstanceUuid):
    r, o, err = execute_qmp_command(vmInstanceUuid, '{"execute": "query-block"}')
    if err:
        raise Exception("Failed to query qemu block, report error")
    
    blocks = json.loads(o)['return']
    for blk in blocks:
        inserted = blk.get('inserted')
        if not inserted:
            continue
        blk_file = inserted.get('file')
        if not blk_file or not blk_file.startswith('json:'):
            continue
        blk_file_obj = json.loads(blk_file[len('json:'):])
        children = blk_file_obj.get('children')
        if not children or len(children) == 1:
            continue

        blk_device_name = blk['device']
        execute_qmp_command(vmInstanceUuid,
                            '{"execute": "x-blockdev-change", "arguments": {"parent":'
                            ' "%s", "child": "children.1"}}' % blk_device_name)
        execute_qmp_command(vmInstanceUuid,
                            '{"execute": "human-monitor-command", "arguments":'
                            '{"command-line": "drive_del replication%s" } }' % blk_device_name[-1])
        

def stop_nbd_sever(vmInstanceUuid):
    execute_qmp_command(vmInstanceUuid, '{"execute": "nbd-server-stop"}')

def colo_lost_heartbeat(vmInstanceUuid):
    execute_qmp_command(vmInstanceUuid, '{"execute": "x-colo-lost-heartbeat"}')

def cleanup_secondary_vm_qom_if_needed(vmInstanceUuid):
    cleanup_qom_match_prefix_if_needed(vmInstanceUuid, ['red-secondary-', 'red-mirror-'])

def cleanup_primary_vm_qom(vmInstanceUuid):
    cleanup_qom_match_prefix_if_needed(vmInstanceUuid, ['zs-mirror-', 'primary-out-s-', 'primary-out-c-', 'secondary-in-s-', 'primary-in-s-', 'primary-in-c-'])

def cleanup_qom_match_prefix_if_needed(vmInstanceUuid, target_prefix_list=[]):
    r, o, err = execute_qmp_command(vmInstanceUuid, '{"execute": "qom-list", "arguments": { "path": "/chardevs" }}')
    if err:
        raise Exception("Failed to query qemu qom, report error")

    qom_list = json.loads(o)['return']

    for qom_entry in qom_list:
        if qom_entry['type'] != "child<chardev-socket>":
            continue

        qom_name = qom_entry['name']
        if any(prefix in qom_name for prefix in target_prefix_list):
            execute_qmp_command(vmInstanceUuid, '{"execute": "object-del","arguments":{"id":"%s"}}' % qom_name)

def cleanup_vm_before_setup_colo_primary_vm(vmInstanceUuid):
    check_if_need_to_update_quorum_children(vmInstanceUuid)
    stop_nbd_sever(vmInstanceUuid)
    cleanup_primary_vm_qom(vmInstanceUuid)
    colo_lost_heartbeat(vmInstanceUuid)
    cleanup_secondary_vm_qom_if_needed(vmInstanceUuid)
    