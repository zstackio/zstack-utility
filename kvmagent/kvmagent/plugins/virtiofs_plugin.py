# Copyright (c) 2025, ZStack, Inc.
# ZSTAC-83157: virtiofs plugin for VM host-source exports

import os
import shlex
import time
import traceback
import libvirt
from kvmagent import kvmagent
from kvmagent.plugins import virtiofs_device
from kvmagent.plugins import virtiofs_source
from zstacklib.utils import log, shell, http, jsonobject
from zstacklib.utils.qga import VmQga, is_qga_connected

logger = log.get_logger(__name__)

# virtiofs configuration constants
VIRTIOFS_DEFAULT_CACHE_MODE = virtiofs_device.DEFAULT_CACHE_MODE
VIRTIOFS_DEFAULT_QUEUE = virtiofs_device.DEFAULT_QUEUE
VALID_CACHE_MODES = virtiofs_device.VALID_CACHE_MODES

# QGA command timeout configuration
# QGA guest_exec_bash uses polling mechanism with 'wait' and 'retry' parameters:
#   - wait: seconds between status checks
#   - retry: number of polling attempts
#   - total_timeout = wait * retry
# These constants define the intended timeout in seconds; retry_count is derived
# by dividing timeout_secs by wait_interval_secs.
QGA_WAIT_INTERVAL_SECS = 1   # seconds between status checks
QGA_MKDIR_TIMEOUT_SECS = 10  # mkdir timeout in seconds (fast operation)
QGA_MOUNT_TIMEOUT_SECS = 30  # mount timeout in seconds (may take longer)
QGA_UMOUNT_TIMEOUT_SECS = 15 # umount timeout in seconds

# Helper to convert timeout seconds to retry count for guest_exec_bash
def _qga_retry_count(timeout_secs):
    """Convert timeout in seconds to QGA polling retry count."""
    return timeout_secs // QGA_WAIT_INTERVAL_SECS

# virtiofsd candidate paths (different distributions use different locations)
VIRTIOFSD_CANDIDATE_PATHS = [
    '/usr/libexec/virtiofsd',  # RHEL/CentOS
    '/usr/bin/virtiofsd',        # Ubuntu/Debian
    '/usr/local/bin/virtiofsd',  # Custom installation
]

# Global cache for virtiofsd path (initialized at plugin startup)
_virtiofsd_path = None


def _init_virtiofsd_path():
    """Initialize virtiofsd path at plugin startup.
    Checks pre-defined paths first, then falls back to 'which' command.
    """
    global _virtiofsd_path
    if _virtiofsd_path is not None:
        return _virtiofsd_path

    for path in VIRTIOFSD_CANDIDATE_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            _virtiofsd_path = path
            logger.info("Found virtiofsd at %s" % path)
            return _virtiofsd_path

    # Fallback to which command if pre-defined paths not found
    which_cmd = shell.ShellCmd("which virtiofsd 2>/dev/null")
    which_cmd(False)
    if which_cmd.return_code == 0:
        path = which_cmd.stdout.strip()
        if path and os.path.isfile(path):
            _virtiofsd_path = path
            logger.info("Found virtiofsd via which: %s" % path)
            return _virtiofsd_path

    logger.warning("virtiofsd not found in any known location")
    return None


def get_virtiofsd_path():
    """Get the cached virtiofsd path.
    Returns None if virtiofsd is not available.
    """
    return _virtiofsd_path


class AttachVirtiofsCmd(jsonobject.JsonObject):
    """Command to attach virtiofs filesystem to VM"""
    vmInstanceUuid = str
    tag = str           # virtiofs device tag
    sourcePath = str    # source path on host
    sourceType = str    # source provider type, default: preparedPath
    sourceUuid = str    # optional source identity
    sourceSpec = object # optional structured source spec
    mountPath = str     # mount path inside VM (for reference)
    cacheMode = str     # cache mode: none/auto/always (default: 'none')
    cache = str         # Java DTO field alias for cacheMode
    queue = int         # virtiofs queue size, default 1024


class DetachVirtiofsCmd(jsonobject.JsonObject):
    """Command to detach virtiofs filesystem from VM"""
    vmInstanceUuid = str
    tag = str           # virtiofs device tag


class VirtiofsResponse(jsonobject.JsonObject):
    success = bool
    error = str
    # QGA mount status (for attach operation)
    qgaMountAttempted = bool    # Whether QGA mount was attempted
    qgaMountSuccess = bool      # Whether QGA mount succeeded
    qgaMountError = str         # Error message if QGA mount failed


class VirtiofsStatusResponse(jsonobject.JsonObject):
    """Response for virtiofs status check"""
    libvirtVersion = str
    virtiofsHotplugSupported = bool


class PrepareHostModelCacheCmd(object):
    @log.sensitive_fields("storageUrl")
    def __init__(self):
        pass


def check_libvirt_version():
    """Check if libvirt version supports virtiofs hotplug (>= 7.9.0)"""
    try:
        ret = shell.call("virsh version")
        # Parse version using regex for more robust matching
        import re
        match = re.search(r'libvirt\s+(\d+)\.(\d+)\.(\d+)', ret, re.IGNORECASE)
        if match:
            major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
            version = "%d.%d.%d" % (major, minor, patch)
            if major > 7 or (major == 7 and minor >= 9):
                return True, version
            return False, version
        return False, "unknown"
    except Exception as e:
        logger.warning("Failed to check libvirt version: %s" % str(e))
        return False, str(e)


def verify_source_path(source_path):
    """Verify source path exists and is accessible

    Security: Uses os.path.realpath to resolve symlinks and ../ patterns
    to prevent path traversal attacks like '/root/../etc/passwd'.

    Returns the resolved real_path for use in XML construction.
    """
    return virtiofs_source.ensure_ready({
        'type': 'preparedPath',
        'sourcePath': source_path,
    }).path


def _verify_source_path_with_recovery(source_path):
    return verify_source_path(source_path)


def _ensure_source_for_attach(cmd):
    source_spec = virtiofs_source.SourceSpec.from_command(cmd)
    return virtiofs_source.ensure_ready(source_spec)


def build_virtiofs_xml(tag, source_path, cache_mode=VIRTIOFS_DEFAULT_CACHE_MODE, queue=VIRTIOFS_DEFAULT_QUEUE):
    """Build virtiofs device XML for libvirt attach

    Args:
        tag: virtiofs device tag
        source_path: source path on host (already verified)
        cache_mode: cache mode (none/auto/always), default 'none'
        queue: virtiofs queue size, default 1024

    Returns:
        str: libvirt filesystem device XML, or None if virtiofsd not found

    Note: Uses xml.sax.saxutils.escape to prevent XML injection attacks
    """
    virtiofsd_path = get_virtiofsd_path()
    if virtiofsd_path is None:
        raise Exception("virtiofsd binary not found. Please install virtiofsd package.")

    normalized_cache_mode = virtiofs_device.normalize_cache_mode(cache_mode, VIRTIOFS_DEFAULT_CACHE_MODE)
    if normalized_cache_mode != cache_mode:
        logger.warning("Invalid cacheMode[%s], using default '%s'" % (
            cache_mode, VIRTIOFS_DEFAULT_CACHE_MODE))
    normalized_queue = virtiofs_device.normalize_queue(queue, VIRTIOFS_DEFAULT_QUEUE)
    try:
        queue_as_int = int(queue)
    except Exception:
        queue_as_int = None
    if normalized_queue != queue_as_int:
        logger.warning("Invalid virtiofs queue[%s], using default '%s'" % (
            queue, VIRTIOFS_DEFAULT_QUEUE))

    return virtiofs_device.build_virtiofs_xml(
        tag, source_path, normalized_cache_mode, normalized_queue, virtiofsd_path, False, True, True)


def _get_cmd_attr(obj, name, default=None):
    try:
        if hasattr(obj, 'hasattr') and obj.hasattr(name):
            return getattr(obj, name)
    except Exception:
        pass
    return getattr(obj, name, default)


def _classify_host_model_cache_failure(error):
    error = str(error or '')
    lowered = error.lower()
    if 'mount model center' in lowered or 'model center mount' in lowered:
        return 'ModelSourceMount', 'JuicefsMountFailed'
    if 'capacity' in lowered or 'available' in lowered:
        return 'CapacityCheck', 'InsufficientHostCacheStorage'
    if 'permission' in lowered or 'denied' in lowered:
        return 'AgentExecution', 'PermissionDenied'
    if 'outside allowed' in lowered or 'must be absolute' in lowered or 'does not exist' in lowered or 'not a directory' in lowered:
        return 'PreparedSourceValidation', 'SourcePathInvalid'
    if 'timeout' in lowered:
        return 'AgentExecution', 'AgentTimeout'
    return 'AgentExecution', 'Unknown'


def get_vm_domain(vm_uuid):
    """Get libvirt domain for VM

    Note: The returned domain object keeps a reference to the libvirt connection.
    The connection will be closed when the domain object is garbage collected.
    """
    conn = None
    try:
        conn = libvirt.open('qemu:///system')
        if conn is None:
            raise Exception("Failed to open libvirt connection")

        # Try to find domain by UUID
        try:
            domain = conn.lookupByUUIDString(vm_uuid)
            return domain, conn
        except libvirt.libvirtError:
            # Try to find by name (zstack uses uuid as name)
            domain = conn.lookupByName(vm_uuid)
            return domain, conn
    except Exception as e:
        # Close connection on failure to prevent leaks
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        raise Exception("Failed to get VM domain[%s]: %s" % (vm_uuid, str(e)))


def check_vm_memory_backing(domain):
    """Check if VM has memoryBacking with shared access configured.

    virtiofs requires VM to have shared memory configured:
    <memoryBacking>
        <access mode='shared'/>
    </memoryBacking>

    Args:
        domain: libvirt domain object

    Returns:
        tuple: (has_memory_backing: bool, error_message: str or None)
    """
    try:
        import xml.etree.ElementTree as ET

        xml_desc = domain.XMLDesc(0)
        root = ET.fromstring(xml_desc)

        # Check for memoryBacking element
        memory_backing = root.find('memoryBacking')
        if memory_backing is None:
            return False, (
                "VM does not have shared memory configured. "
                "virtiofs requires memoryBacking with access mode='shared'. "
                "Please reboot the VM to enable virtiofs support."
            )

        # Check for access mode='shared'
        access = memory_backing.find('access')
        if access is None or access.get('mode') != 'shared':
            return False, (
                "VM does not have shared memory access mode configured. "
                "virtiofs requires <access mode='shared'/> in memoryBacking. "
                "Please reboot the VM to enable virtiofs support."
            )

        return True, None

    except Exception as e:
        logger.warning("Failed to check VM memoryBacking: %s" % str(e))
        # On error, allow the operation to proceed and let libvirt report the actual error
        return True, None


def mount_virtiofs_in_vm(domain, tag, mount_path):
    """Mount virtiofs filesystem inside VM using QGA

    Args:
        domain: libvirt domain object
        tag: virtiofs device tag
        mount_path: target mount path inside VM

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    # Track current QGA step and timeout for accurate error reporting
    # Initialize to "init" phase before any QGA operations
    current_qga_step = "init"
    current_qga_timeout_secs = QGA_MKDIR_TIMEOUT_SECS  # reasonable default for init phase

    try:
        # Check if QGA is connected
        if not is_qga_connected(domain):
            logger.warning("QGA not connected for VM[%s], cannot mount inside VM" % domain.name())
            return False, "QGA not connected for VM, unable to mount virtiofs source inside VM"

        qga = VmQga(domain)

        # Check QGA state
        if qga.state != VmQga.QGA_STATE_RUNNING:
            logger.warning("QGA not running for VM[%s], state=%s" % (domain.name(), qga.state))
            return False, "QGA is not running, unable to mount virtiofs source inside VM"

        # Check OS type - virtiofs only works on Linux
        if qga.os and 'mswindows' in qga.os.lower():
            logger.warning("Windows VM detected, virtiofs mount not supported")
            return False, "Windows VM does not support virtiofs mount"

        logger.info("Attempting to mount virtiofs inside VM[%s] via QGA, os=%s" % (
            domain.name(), qga.os))

        # Use shlex.quote to prevent command injection
        safe_mount_path = shlex.quote(mount_path)

        # 1. Create mount directory (with -p to create parent dirs)
        current_qga_step = "mkdir"
        current_qga_timeout_secs = QGA_MKDIR_TIMEOUT_SECS
        mkdir_cmd = "mkdir -p %s" % safe_mount_path

        logger.debug("QGA: executing mkdir command: %s" % mkdir_cmd)
        exitcode, stdout, stderr = qga.guest_exec_bash(mkdir_cmd, retry=_qga_retry_count(QGA_MKDIR_TIMEOUT_SECS))

        if exitcode != 0:
            error_msg = stderr if stderr else "unknown error"
            logger.error("Failed to create mount directory[%s]: %s" % (mount_path, error_msg))
            return False, "Failed to create mount directory in VM: %s" % error_msg

        # 2. Check if already mounted (use shorter timeout)
        # mountpoint -q returns: 0 if mount point, 1 if not mount point, >1 on error
        # guest_exec_bash does NOT raise exception on non-zero exitcode, only on timeout/connection errors
        current_qga_step = "mountpoint-check"
        current_qga_timeout_secs = QGA_MKDIR_TIMEOUT_SECS
        check_mount_cmd = "mountpoint -q %s" % safe_mount_path
        exitcode, _, _ = qga.guest_exec_bash(check_mount_cmd, retry=_qga_retry_count(QGA_MKDIR_TIMEOUT_SECS))
        if exitcode == 0:
            logger.info("Path[%s] is already a mount point in VM[%s]" % (mount_path, domain.name()))
            return True, None
        # exitcode 1 means not a mount point, continue to mount
        # exitcode >1 means error (e.g., path doesn't exist), but we still try mount

        # 3. Mount virtiofs with retry mechanism
        # First mount attempt may fail if virtiofs kernel module is not yet loaded.
        # Retry once after a short delay to handle this scenario.
        current_qga_step = "mount"
        current_qga_timeout_secs = QGA_MOUNT_TIMEOUT_SECS
        safe_tag = shlex.quote(tag)
        mount_cmd = "mount -t virtiofs -o ro %s %s" % (safe_tag, safe_mount_path)

        max_retries = 2
        last_error_msg = "unknown error"

        for attempt in range(max_retries):
            if attempt > 0:
                logger.info("QGA: retrying mount command (attempt %d/%d) after 1 second delay for VM[%s]" % (
                    attempt + 1, max_retries, domain.name()))
                time.sleep(1)

            logger.info("QGA: executing mount command (attempt %d/%d): %s" % (attempt + 1, max_retries, mount_cmd))
            exitcode, stdout, stderr = qga.guest_exec_bash(mount_cmd, retry=_qga_retry_count(QGA_MOUNT_TIMEOUT_SECS))

            if exitcode == 0:
                logger.info("Successfully mounted virtiofs[%s] to[%s] inside VM[%s] on attempt %d" % (
                    tag, mount_path, domain.name(), attempt + 1))
                return True, None

            # Mount failed, record error and retry
            last_error_msg = stderr if stderr else stdout if stdout else "unknown error"
            logger.warning("Mount attempt %d/%d failed for virtiofs[%s] to[%s] in VM[%s]: %s" % (
                attempt + 1, max_retries, tag, mount_path, domain.name(), last_error_msg))

        # All retries exhausted
        logger.error("Failed to mount virtiofs[%s] to[%s] in VM[%s] after %d attempts: %s" % (
            tag, mount_path, domain.name(), max_retries, last_error_msg))
        return False, "Failed to mount virtiofs source in VM: %s" % last_error_msg

    except Exception as e:
        error_str = str(e)
        # Check if it's a timeout error
        if 'timeout' in error_str.lower():
            logger.error("QGA command[%s] timeout during mount operation for VM[%s]" % (
                current_qga_step, domain.name()))
            return False, "Mount operation timed out in VM"
        logger.error("Exception during QGA mount: %s\n%s" % (error_str, traceback.format_exc()))
        return False, "Exception during QGA mount in VM: %s" % error_str


def unmount_virtiofs_in_vm(domain, tag):
    """Unmount virtiofs filesystem inside VM using QGA

    Args:
        domain: libvirt domain object
        tag: virtiofs device tag

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    # Track current QGA step and timeout for accurate error reporting
    # Initialize to "init" phase before any QGA operations
    current_qga_step = "init"
    current_qga_timeout_secs = QGA_MKDIR_TIMEOUT_SECS  # reasonable default for init phase

    try:
        qga = VmQga(domain)

        if qga.state != VmQga.QGA_STATE_RUNNING:
            logger.warning("QGA not running for VM[%s]" % domain.name())
            return False, "VM guest agent is not running"

        if qga.os and 'mswindows' in qga.os.lower():
            logger.warning("Windows VM detected, skip unmount")
            return True, None  # Windows doesn't support virtiofs mount

        # Find mount point by tag from /proc/mounts
        # /proc/mounts format: device mount_point fs_type options
        # For virtiofs: source-xxx /mnt/virtiofs/source virtiofs rw,...
        # Use awk -v to pass variable safely, avoiding nested quote issues
        current_qga_step = "find-mount"
        current_qga_timeout_secs = QGA_MKDIR_TIMEOUT_SECS
        safe_tag = shlex.quote(tag)
        find_mount_cmd = "awk -v tag=%s '$1==tag && $3==\"virtiofs\" {print $2}' /proc/mounts" % safe_tag
        exitcode, mount_path, stderr = qga.guest_exec_bash(find_mount_cmd, retry=_qga_retry_count(QGA_MKDIR_TIMEOUT_SECS))

        if exitcode != 0 or not mount_path or not mount_path.strip():
            logger.info("No mount point found for virtiofs tag[%s] in VM[%s], skip unmount" % (
                tag, domain.name()))
            return True, None

        mount_path = mount_path.strip()
        logger.info("Found mount point[%s] for virtiofs[%s] in VM[%s]" % (
            mount_path, tag, domain.name()))

        # Unmount
        current_qga_step = "umount"
        current_qga_timeout_secs = QGA_UMOUNT_TIMEOUT_SECS
        safe_mount_path = shlex.quote(mount_path)
        umount_cmd = "umount %s" % safe_mount_path

        logger.info("QGA: executing umount command: %s" % umount_cmd)
        exitcode, stdout, stderr = qga.guest_exec_bash(umount_cmd, retry=_qga_retry_count(QGA_UMOUNT_TIMEOUT_SECS))

        if exitcode != 0:
            # Try lazy unmount if regular unmount fails
            error_msg = stderr if stderr else "unknown error"
            logger.warning("Regular unmount failed: %s, trying lazy unmount" % error_msg)

            current_qga_step = "umount-lazy"
            umount_lazy_cmd = "umount -l %s" % safe_mount_path
            exitcode, stdout, stderr = qga.guest_exec_bash(umount_lazy_cmd, retry=_qga_retry_count(QGA_UMOUNT_TIMEOUT_SECS))

            if exitcode != 0:
                error_msg = stderr if stderr else "unknown error"
                logger.error("Lazy unmount also failed: %s" % error_msg)
                return False, "Failed to unmount virtiofs source in VM: %s" % error_msg

        logger.info("Successfully unmounted virtiofs[%s] from[%s] inside VM[%s]" % (
            tag, mount_path, domain.name()))
        return True, None

    except Exception as e:
        error_str = str(e)
        # Check if it's a timeout error
        if 'timeout' in error_str.lower():
            logger.error("QGA command[%s] timeout during unmount operation for VM[%s]" % (
                current_qga_step, domain.name()))
            return False, "Unmount operation timed out in VM"
        logger.error("Exception during QGA unmount: %s\n%s" % (error_str, traceback.format_exc()))
        return False, "Failed to unmount virtiofs source in VM: %s" % error_str


class VirtiofsPlugin(kvmagent.KvmAgent):
    """Virtiofs plugin for VM host-source exports"""

    ATTACH_VIRTIOFS_PATH = "/virtiofs/attach"
    DETACH_VIRTIOFS_PATH = "/virtiofs/detach"
    STATUS_VIRTIOFS_PATH = "/virtiofs/status"
    HOST_MODEL_CACHE_REPORT_PATH = "/virtiofs/host-model-cache/report"
    HOST_MODEL_CACHE_PREPARE_PATH = "/virtiofs/host-model-cache/prepare"
    HOST_MODEL_CACHE_CLEANUP_PATH = "/virtiofs/host-model-cache/cleanup"

    def start(self):
        """Initialize virtiofsd path and register HTTP endpoints."""
        _init_virtiofsd_path()

        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.ATTACH_VIRTIOFS_PATH, self.attach_virtiofs)
        http_server.register_async_uri(self.DETACH_VIRTIOFS_PATH, self.detach_virtiofs)
        http_server.register_async_uri(self.STATUS_VIRTIOFS_PATH, self.virtiofs_status)
        http_server.register_async_uri(self.HOST_MODEL_CACHE_REPORT_PATH, self.report_host_model_cache)
        http_server.register_async_uri(
            self.HOST_MODEL_CACHE_PREPARE_PATH,
            self.prepare_host_model_cache,
            cmd=PrepareHostModelCacheCmd())
        http_server.register_async_uri(self.HOST_MODEL_CACHE_CLEANUP_PATH, self.cleanup_host_model_cache)

    def stop(self):
        """No-op; virtiofs plugin has no background resources to clean up."""
        pass

    @kvmagent.replyerror
    def attach_virtiofs(self, req):
        """Attach virtiofs filesystem to running VM

        This function does two things:
        1. Hot-plug virtiofs device to VM via libvirt
        2. Mount virtiofs inside VM via QGA (if available)
        """
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VirtiofsResponse()
        rsp.success = False
        rsp.qgaMountAttempted = False
        rsp.qgaMountSuccess = False

        conn = None
        try:
            logger.info("Attaching virtiofs to VM[%s], tag=%s, source=%s, mountPath=%s, cacheMode=%s, queue=%s" % (
                cmd.vmInstanceUuid, cmd.tag, cmd.sourcePath, cmd.mountPath,
                _get_cmd_attr(cmd, 'cacheMode', _get_cmd_attr(cmd, 'cache', VIRTIOFS_DEFAULT_CACHE_MODE)),
                _get_cmd_attr(cmd, 'queue', VIRTIOFS_DEFAULT_QUEUE)))

            # 1. Ensure source path is ready on host and get resolved path.
            host_source = _ensure_source_for_attach(cmd)
            resolved_path = host_source.path

            # 2. Get VM domain
            domain, conn = get_vm_domain(cmd.vmInstanceUuid)

            # 3. Check if VM has memoryBacking configured (required for virtiofs)
            has_memory_backing, memory_backing_error = check_vm_memory_backing(domain)
            if not has_memory_backing:
                rsp.error = memory_backing_error
                return jsonobject.dumps(rsp)

            # 4. Build virtiofs XML using resolved path and cache/queue settings
            cache_mode = _get_cmd_attr(cmd, 'cacheMode', _get_cmd_attr(cmd, 'cache', VIRTIOFS_DEFAULT_CACHE_MODE))
            queue = _get_cmd_attr(cmd, 'queue', VIRTIOFS_DEFAULT_QUEUE)

            xml_str = build_virtiofs_xml(cmd.tag, resolved_path, cache_mode, queue)

            # 4. Attach device to running VM (hot-plug)
            domain.attachDeviceFlags(xml_str, libvirt.VIR_DOMAIN_AFFECT_LIVE)

            # 5. Also attach to config for persistence (VM restart)
            try:
                domain.attachDeviceFlags(xml_str, libvirt.VIR_DOMAIN_AFFECT_CONFIG)
            except Exception as e:
                logger.warning("Failed to attach virtiofs to config: %s" % str(e))

            logger.info("Successfully attached virtiofs device to VM[%s]" % cmd.vmInstanceUuid)

            # 6. Mount inside VM via QGA (if available)
            if cmd.mountPath:
                qga_success, qga_error = mount_virtiofs_in_vm(domain, cmd.tag, cmd.mountPath)
                rsp.qgaMountAttempted = True
                rsp.qgaMountSuccess = qga_success
                if qga_error:
                    rsp.qgaMountError = qga_error

                if not qga_success:
                    logger.warning("QGA mount failed for VM[%s] after virtiofs device attach; "
                                   "keeping libvirt device and returning success with warning detail: %s" % (
                        cmd.vmInstanceUuid, qga_error))
            else:
                logger.warning("No mountPath specified, skip VM internal mount")

            rsp.success = True
            logger.info("Virtiofs attach completed for VM[%s], qgaMount=%s" % (
                cmd.vmInstanceUuid, rsp.qgaMountSuccess))

        except Exception as e:
            logger.error("Failed to attach virtiofs: %s\n%s" % (str(e), traceback.format_exc()))
            rsp.error = str(e)
        finally:
            if conn is not None:
                conn.close()

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def detach_virtiofs(self, req):
        """Detach virtiofs filesystem from running VM

        This function does two things:
        1. Unmount virtiofs inside VM via QGA (if available)
        2. Hot-unplug virtiofs device from VM via libvirt
        """
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = VirtiofsResponse()
        rsp.success = False
        rsp.qgaMountAttempted = False
        rsp.qgaMountSuccess = False

        conn = None
        try:
            logger.info("Detaching virtiofs from VM[%s], tag=%s" % (
                cmd.vmInstanceUuid, cmd.tag))

            # Get VM domain
            domain, conn = get_vm_domain(cmd.vmInstanceUuid)

            # 1. Unmount inside VM via QGA first (if available)
            if is_qga_connected(domain):
                qga = VmQga(domain)
                if qga.state == VmQga.QGA_STATE_RUNNING:
                    rsp.qgaMountAttempted = True
                    unmount_success, unmount_error = unmount_virtiofs_in_vm(domain, cmd.tag)
                    rsp.qgaMountSuccess = unmount_success
                    if not unmount_success:
                        logger.warning("QGA unmount failed: %s" % unmount_error)
                        # Continue with detach anyway, the device will be removed

            # 2. Get XML for detach
            # Try live XML first (for hotplugged/transient devices), then fall back to inactive XML
            import xml.etree.ElementTree as ET

            def find_fs_xml_by_tag(xml_desc, tag):
                """Find filesystem device XML by tag"""
                if not xml_desc:
                    return None
                try:
                    root = ET.fromstring(xml_desc)
                    for fs in root.findall(".//filesystem[@type='mount']"):
                        target = fs.find('target')
                        if target is not None and target.get('dir') == tag:
                            return ET.tostring(fs, encoding='unicode')
                except Exception:
                    pass
                return None

            # First try live XML (for hotplugged devices)
            fs_xml = find_fs_xml_by_tag(domain.XMLDesc(0), cmd.tag)
            if fs_xml is None:
                # Fall back to inactive/config XML
                fs_xml = find_fs_xml_by_tag(domain.XMLDesc(libvirt.VIR_DOMAIN_XML_INACTIVE), cmd.tag)

            if fs_xml is None:
                raise Exception("virtiofs device with tag[%s] not found in VM config" % cmd.tag)

            # 3. Detach device from live VM
            domain.detachDeviceFlags(fs_xml, libvirt.VIR_DOMAIN_AFFECT_LIVE)

            # 4. Detach from config
            try:
                domain.detachDeviceFlags(fs_xml, libvirt.VIR_DOMAIN_AFFECT_CONFIG)
            except Exception as e:
                logger.warning("Failed to detach virtiofs from config: %s" % str(e))

            rsp.success = True
            logger.info("Successfully detached virtiofs from VM[%s]" % cmd.vmInstanceUuid)

        except Exception as e:
            logger.error("Failed to detach virtiofs: %s\n%s" % (str(e), traceback.format_exc()))
            rsp.error = str(e)
        finally:
            if conn is not None:
                conn.close()

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def virtiofs_status(self, req):
        """Check virtiofs support status"""
        rsp = VirtiofsStatusResponse()
        supported, version = check_libvirt_version()
        rsp.libvirtVersion = version
        rsp.virtiofsHotplugSupported = supported
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def report_host_model_cache(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = jsonobject.JsonObject()
        rsp.success = False
        try:
            source_root = _get_cmd_attr(cmd, 'sourceRoot', _get_cmd_attr(cmd, 'sourceRootPath', None))
            report = virtiofs_source.report_source_root(source_root)
            rsp.sourceRoot = report.get('sourceRoot')
            rsp.physicalTotalBytes = report.get('physicalTotalBytes')
            rsp.physicalAvailableBytes = report.get('physicalAvailableBytes')
            rsp.cacheEntries = report.get('cacheEntries', [])
            rsp.success = True
            logger.info("Reported host model cache root[%s], entries=%s, available=%s" % (
                rsp.sourceRoot, len(rsp.cacheEntries), rsp.physicalAvailableBytes))
        except Exception as e:
            logger.warning("Failed to report host model cache: %s" % str(e))
            rsp.error = str(e)
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def prepare_host_model_cache(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = jsonobject.JsonObject()
        rsp.success = False
        try:
            source_root = _get_cmd_attr(cmd, 'sourceRoot', _get_cmd_attr(cmd, 'sourceRootPath', None))
            source_path = _get_cmd_attr(cmd, 'sourcePath', None)
            required_capacity = _get_cmd_attr(cmd, 'requiredCapacityBytes', None)
            source_type = _get_cmd_attr(cmd, 'sourceType', 'preparedPath')
            if source_type == 'juicefsModelCenter':
                artifact_relative_path = _get_cmd_attr(cmd, 'artifactRelativePath', None)
                if not artifact_relative_path:
                    artifact_relative_path = _get_cmd_attr(cmd, 'modelRelativePath', None)
                storage_subdir = _get_cmd_attr(cmd, 'storageSubdir', None) or 'models'
                register_cache = _get_cmd_attr(cmd, 'registerCache', None)
                if register_cache is None:
                    register_cache = True
                entry = virtiofs_source.prepare_model_center_cache(
                    source_root,
                    source_path,
                    _get_cmd_attr(cmd, 'modelCenterUuid', None),
                    _get_cmd_attr(cmd, 'storageUrl', None),
                    artifact_relative_path,
                    required_capacity,
                    storage_subdir,
                    register_cache,
                    _get_cmd_attr(cmd, 'contentVersion', None))
            else:
                entry = virtiofs_source.prepare_host_model_cache(source_root, source_path, required_capacity)
            rsp.cacheEntry = entry
            if isinstance(entry, dict):
                rsp.prepareDecision = entry.get('prepareDecision')
                rsp.prepareReason = entry.get('prepareReason')
            rsp.success = True
            logger.info(
                "[host-model-cache-prepare] path=%s size=%s decision=%s reason=%s "
                "contentVersion=%s actions=%s" % (
                    entry.get('sourcePath') if isinstance(entry, dict) else None,
                    entry.get('sizeBytes') if isinstance(entry, dict) else None,
                    entry.get('prepareDecision') if isinstance(entry, dict) else None,
                    entry.get('prepareReason') if isinstance(entry, dict) else None,
                    entry.get('contentVersion') if isinstance(entry, dict) else None,
                    entry.get('prepareActions') if isinstance(entry, dict) else None,
                ))
        except Exception as e:
            phase, code = _classify_host_model_cache_failure(e)
            rsp.failurePhase = phase
            rsp.failureCode = code
            rsp.failureMessage = str(e)
            rsp.error = str(e)
            logger.warning(
                "[host-model-cache-prepare] failed phase=%s code=%s path=%s error=%s" % (
                    phase, code, _get_cmd_attr(cmd, 'sourcePath', None), str(e)))
        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def cleanup_host_model_cache(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = jsonobject.JsonObject()
        rsp.success = False
        try:
            source_root = _get_cmd_attr(cmd, 'sourceRoot', _get_cmd_attr(cmd, 'sourceRootPath', None))
            source_path = _get_cmd_attr(cmd, 'sourcePath', None)
            result = virtiofs_source.cleanup_host_model_cache(source_root, source_path)
            rsp.sourcePath = result.get('sourcePath')
            rsp.bytesReclaimed = result.get('bytesReclaimed')
            rsp.success = True
            logger.info("Cleaned host model cache path[%s], bytesReclaimed=%s" % (
                rsp.sourcePath, rsp.bytesReclaimed))
        except Exception as e:
            phase, code = _classify_host_model_cache_failure(e)
            rsp.failurePhase = phase
            rsp.failureCode = code
            rsp.failureMessage = str(e)
            rsp.error = str(e)
            logger.warning("Failed to cleanup host model cache, phase=%s code=%s error=%s" % (
                phase, code, str(e)))
        return jsonobject.dumps(rsp)
