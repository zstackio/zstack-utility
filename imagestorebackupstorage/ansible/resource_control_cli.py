import json
import sys

from resource_control import ResourceControlManager, get_cpu_topology


def execute(action, command):
    if action == 'topology':
        return {'numa': {node_id: {'nodeId': node_id, 'onlineCpus': node['onlineCpus'], 'coreGroups': node['coreGroups']}
                         for node_id, node in get_cpu_topology().items() if node['onlineCpus']}}
    manager = ResourceControlManager()
    role = command['roleType']
    handles = command['handles']
    slice_name = command['sliceName']
    manager.validate_service_command(slice_name, handles)
    if action == 'apply':
        return manager.apply(role, command.get('cpuSet'), handles, command.get('memory'), slice_name,
                             command.get('isolationMode') or 'SHARED')
    if action == 'release':
        return manager.release(role, handles, slice_name)
    if action == 'services':
        return {'services': manager.inspect(role, handles, slice_name)}
    if action == 'restart':
        manager.restart(slice_name, handles)
        return {}
    raise ValueError('Unsupported resource control action[%s]' % action)


if __name__ == '__main__':
    response = execute(sys.argv[1], json.load(sys.stdin))
    response['success'] = True
    json.dump(response, sys.stdout)
