import os


GLOBAL_CONFIG_CATEGORY = 'physicalServer'
GLOBAL_CONFIG_NAME = 'resourceAssignment.enabled'
MANAGEMENT_NODE_SERVICE = 'zstack-management-node.service'
MANAGEMENT_NODE_SLICE = 'zstack-management.slice'
RESOURCE_ASSIGNMENT_DROP_IN = ('/etc/systemd/system/%s.d/50-zstack-resource-assignment.conf' % MANAGEMENT_NODE_SERVICE)


def resource_assignment_enabled(rows, cgroup_root='/sys/fs/cgroup'):
    if rows:
        return str(rows[0].get('value', '')).strip().lower() == 'true'
    return os.path.isfile(os.path.join(cgroup_root, 'cgroup.controllers'))


def management_node_systemd_run_arguments(start_script, pid_file):
    return [
        'systemd-run',
        '--unit=%s' % MANAGEMENT_NODE_SERVICE,
        '--slice=%s' % MANAGEMENT_NODE_SLICE,
        '--uid=zstack',
        '--service-type=forking',
        '--property=PIDFile=%s' % pid_file,
        '--collect',
        '/bin/sh',
        start_script,
        '-DappName=zstack',
    ]
