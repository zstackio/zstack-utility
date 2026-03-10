import re

from kvmagent.plugins.vms import vm_host_file

class TpmStateHostFile(object):
    def __init__(self):
        pass

    def read_file(self, to):
        # type: (vm_host_file.VmHostFileTO) -> vm_host_file.VmHostFileTO
        result = vm_host_file.VmHostFileTO()
        result.path = to.path
        result.type = to.type

        if not check_tpm_state_vm_host_file_path_format(result.path):
            result.error = 'invalid TPM state vm host file path ' + result.path
            return result
        vm_host_file.read_vm_host_file_targz(result)
        return result

    def write_file(self, to):
        # type: (vm_host_file.VmHostFileTO) -> None
        if not check_tpm_state_vm_host_file_path_format(to.path):
            raise Exception('invalid TPM state vm host file path ' + to.path)
        vm_host_file.write_vm_host_file(to)

def build_tpm_state_vm_host_folder_path(vm_uuid):
    # type: (str) -> str
    vm_uuid_with_hyphen = re.sub(
        r'^([a-fA-F0-9]{8})([a-fA-F0-9]{4})([a-fA-F0-9]{4})([a-fA-F0-9]{4})([a-fA-F0-9]{12})$',
        r'\1-\2-\3-\4-\5',
        vm_uuid
    )
    return "/var/lib/libvirt/swtpm/%s/" % (vm_uuid_with_hyphen)

def check_tpm_state_vm_host_file_path_format(path):
    # type: (str) -> bool
    if not path:
        return False

    path = path.rstrip('/')
    uuid_pattern = r'[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}'
    pattern = r'^/var/lib/libvirt/swtpm/({0})$'.format(uuid_pattern)
    return bool(re.match(pattern, path))
