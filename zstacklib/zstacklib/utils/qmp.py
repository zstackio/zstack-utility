import bash
import json
import qemu
from distutils.version import LooseVersion

def qmp_subcmd(s_cmd):
    # object-add option props (removed in 6.0).
    # Specify the properties for the object as top-level arguments instead.
    if LooseVersion(qemu.get_version()) >= LooseVersion("6.0.0") and re.match(r'.*object-add.*arguments.*props.*', s_cmd):
            j_cmd = json.loads(s_cmd)
            props = j_cmd.get("arguments").get("props")
            j_cmd.get("arguments").pop("props")
            j_cmd.get("arguments").update(props)
            s_cmd = json.dumps(j_cmd)
    return s_cmd


@bash.in_bash
def execute_qmp_command(domain_id, command):
    return bash.bash_roe("virsh qemu-monitor-command %s '%s' --pretty" % (domain_id, qmp_subcmd(command)))


def vm_query_jobs(vm_uuid):
    r, o, e = execute_qmp_command(vm_uuid, '{"execute":"query-jobs"}')
    if r != 0:
        raise Exception("Failed to query jobs on vm[uuid:{}], error:{}".format(vm_uuid, e))

    return json.loads(o.strip())["return"]


def vm_query_block_jobs(vm_uuid):
    r, o, e = execute_qmp_command(vm_uuid, '{"execute":"query-block-jobs"}')
    if r != 0:
        raise Exception("Failed to query block jobs on vm[uuid:{}], error:{}".format(vm_uuid, e))

    return json.loads(o.strip())["return"]


def vm_dismiss_block_job(vm_uuid):
    jobs = vm_query_jobs(vm_uuid)
    if not jobs:
        return

    for job in jobs:
        if job['status'] == "concluded":
            execute_qmp_command(vm_uuid, '{"execute":"block-job-dismiss", "arguments": {"id":"%s"}}' % job['id'])
    return
