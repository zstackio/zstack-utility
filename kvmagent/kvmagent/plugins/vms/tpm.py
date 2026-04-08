import os
import re

from kvmagent.plugins.vms import vm_host_file

from zstacklib.utils import shell

SWTPM_BASE = '/var/lib/libvirt/swtpm'
TPM_PERMALL_RELATIVE_PATH = os.path.join('tpm2', 'tpm2-00.permall')

def is_virsh_support_keep_tpm():
    return shell.run("virsh undefine --help | grep -q '\\-\\-keep-tpm'") == 0

VIRSH_SUPPORT_KEEP_TPM = is_virsh_support_keep_tpm()

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

def _uuid_with_hyphens(vm_uuid):
    # type: (str) -> str
    return re.sub(
        r'^([a-fA-F0-9]{8})([a-fA-F0-9]{4})([a-fA-F0-9]{4})([a-fA-F0-9]{4})([a-fA-F0-9]{12})$',
        r'\1-\2-\3-\4-\5',
        vm_uuid
    )

def build_tpm_state_vm_host_folder_path(vm_uuid):
    # type: (str) -> str
    return "%s/%s/" % (SWTPM_BASE, _uuid_with_hyphens(vm_uuid))

def build_tpm_permall_path(vm_uuid):
    # type: (str) -> str
    return os.path.join(SWTPM_BASE, _uuid_with_hyphens(vm_uuid), TPM_PERMALL_RELATIVE_PATH)

def check_tpm_state_vm_host_file_path_format(path):
    # type: (str) -> bool
    if not path:
        return False

    path = path.rstrip('/')
    uuid_pattern = r'[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}'
    pattern = r'^%s/({0})(\.snapshot-backup)?$'.format(uuid_pattern) % re.escape(SWTPM_BASE)
    return bool(re.match(pattern, path))
