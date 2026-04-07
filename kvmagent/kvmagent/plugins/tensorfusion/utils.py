'''
TensorFusion shared utilities.

@author: tensorfusion
'''

import libvirt

from zstacklib.utils import log

logger = log.get_logger(__name__)


def is_vm_running(vm_uuid):
    """Check if a VM is still running in libvirt.

    Returns:
        True  - VM exists and is active.
        False - VM does not exist or is not active (safe to clean up workers).
        None  - Query failed due to libvirt error (caller should NOT assume
                the VM is gone; skipping cleanup is the safe choice).
    """
    try:
        from kvmagent.plugins.vm_plugin import LibvirtAutoReconnect

        @LibvirtAutoReconnect
        def _lookup(conn):
            return conn.lookupByName(vm_uuid)

        dom = _lookup()
        return dom.isActive() == 1
    except libvirt.libvirtError as e:
        if e.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
            return False
        logger.warn('is_vm_running: libvirt error checking VM %s: %s' % (vm_uuid, e))
        return None
    except Exception as e:
        logger.warn('is_vm_running: unexpected error checking VM %s: %s' % (vm_uuid, e))
        return None
