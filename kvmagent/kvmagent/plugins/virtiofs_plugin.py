# Copyright (c) 2025, ZStack, Inc.
# ZSTAC-83157: virtiofs plugin for VM model mount

import os
import shlex
import traceback
import libvirt
from xml.sax.saxutils import escape as xml_escape
from kvmagent import kvmagent
from zstacklib.utils import log, shell, http, jsonobject
from zstacklib.utils.qga import VmQga, is_qga_connected

logger = log.get_logger(__name__)


class AttachVirtiofsCmd(jsonobject.JsonObject):
    """Command to attach virtiofs filesystem to VM"""
    vmInstanceUuid = str
    tag = str           # virtiofs device tag
    sourcePath = str    # source path on host
    mountPath = str     # mount path inside VM (for reference)


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
    if not source_path:
        raise Exception("sourcePath is required")

    if not os.path.exists(source_path):
        raise Exception("sourcePath[%s] does not exist" % source_path)

    if not os.path.isdir(source_path):
        raise Exception("sourcePath[%s] is not a directory" % source_path)

    # Resolve symlinks and normalize path
    real_path = os.path.realpath(source_path)

    # Security check: whitelist mode - only allow paths under model mount base
    # This prevents arbitrary host directories from being exposed to VMs
    allowed_base = os.path.realpath('/opt/zstack/models')
    if real_path != allowed_base and not real_path.startswith(allowed_base + '/'):
        raise Exception("sourcePath[%s] resolves to path[%s] outside allowed model directory[%s]" % (
            source_path, real_path, allowed_base))

    return real_path


def build_virtiofs_xml(tag, source_path):
    """Build virtiofs device XML for libvirt attach

    Note: Uses xml.sax.saxutils.escape to prevent XML injection attacks
    """
    safe_source_path = xml_escape(source_path)
    safe_tag = xml_escape(tag)
    return '''<filesystem type='mount' accessmode='passthrough'>
    <driver type='virtiofs'/>
    <source dir='%s'/>
    <target dir='%s'/>
    <binary path='/usr/libexec/virtiofsd' xattr='on'>
        <cache mode='auto'/>
        <sandbox mode='namespace'/>
    </binary>
</filesystem>''' % (safe_source_path, safe_tag)


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
        raise Exception("Failed to get VM domain[%s]: %s" % (vm_uuid, str(e))) from e


def mount_virtiofs_in_vm(domain, tag, mount_path):
    """Mount virtiofs filesystem inside VM using QGA

    Args:
        domain: libvirt domain object
        tag: virtiofs device tag
        mount_path: target mount path inside VM

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    try:
        # Check if QGA is connected
        if not is_qga_connected(domain):
            logger.warning("QGA not connected for VM[%s], cannot mount inside VM" % domain.name())
            return False, "QGA not connected, please mount manually: mount -t virtiofs %s %s" % (tag, mount_path)

        qga = VmQga(domain)

        # Check QGA state
        if qga.state != VmQga.QGA_STATE_RUNNING:
            logger.warning("QGA not running for VM[%s], state=%s" % (domain.name(), qga.state))
            return False, "QGA not running, please mount manually: mount -t virtiofs %s %s" % (tag, mount_path)

        # Check OS type - virtiofs only works on Linux
        if qga.os and 'mswindows' in qga.os.lower():
            logger.warning("Windows VM detected, virtiofs mount not supported")
            return False, "Windows VM does not support virtiofs mount via QGA"

        logger.info("Attempting to mount virtiofs inside VM[%s] via QGA, os=%s" % (
            domain.name(), qga.os))

        # 1. Create mount directory (with -p to create parent dirs)
        # Use shlex.quote to prevent command injection
        safe_mount_path = shlex.quote(mount_path)
        mkdir_cmd = "mkdir -p %s" % safe_mount_path

        logger.debug("QGA: executing mkdir command: %s" % mkdir_cmd)
        exitcode, stdout, stderr = qga.guest_exec_bash(mkdir_cmd)

        if exitcode != 0:
            error_msg = stderr if stderr else "unknown error"
            logger.error("Failed to create mount directory[%s]: %s" % (mount_path, error_msg))
            return False, "Failed to create mount directory: %s" % error_msg

        # 2. Check if already mounted
        check_mount_cmd = "mountpoint -q %s" % safe_mount_path
        try:
            exitcode, _, _ = qga.guest_exec_bash(check_mount_cmd)
            if exitcode == 0:
                logger.info("Path[%s] is already a mount point in VM[%s]" % (mount_path, domain.name()))
                return True, None
        except Exception:
            # mountpoint returns non-zero if not a mount point, which raises exception
            pass

        # 3. Mount virtiofs
        # Use guest_exec_command for safer argument passing
        mount_cmd = "mount -t virtiofs %s %s" % (shlex.quote(tag), safe_mount_path)

        logger.info("QGA: executing mount command: %s" % mount_cmd)
        exitcode, stdout, stderr = qga.guest_exec_bash(mount_cmd)

        if exitcode != 0:
            error_msg = stderr if stderr else stdout if stdout else "unknown error"
            logger.error("Failed to mount virtiofs[%s] to[%s]: %s" % (tag, mount_path, error_msg))
            return False, "Mount failed: %s. Please mount manually: mount -t virtiofs %s %s" % (
                error_msg, tag, mount_path)

        logger.info("Successfully mounted virtiofs[%s] to[%s] inside VM[%s]" % (
            tag, mount_path, domain.name()))
        return True, None

    except Exception as e:
        logger.error("Exception during QGA mount: %s\n%s" % (str(e), traceback.format_exc()))
        return False, "QGA mount failed: %s. Please mount manually: mount -t virtiofs %s %s" % (
            str(e), tag, mount_path)


def unmount_virtiofs_in_vm(domain, tag):
    """Unmount virtiofs filesystem inside VM using QGA

    Args:
        domain: libvirt domain object
        tag: virtiofs device tag

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    try:
        qga = VmQga(domain)

        if qga.state != VmQga.QGA_STATE_RUNNING:
            logger.warning("QGA not running for VM[%s]" % domain.name())
            return False, "QGA not running"

        if qga.os and 'mswindows' in qga.os.lower():
            logger.warning("Windows VM detected, skip unmount")
            return True, None  # Windows doesn't support virtiofs mount

        # Find mount point by tag from /proc/mounts
        # /proc/mounts format: device mount_point fs_type options
        # For virtiofs: model-xxx /mnt/models/qwen virtiofs rw,...
        # We need to match: ^{tag}\s+\S+\s+virtiofs
        safe_tag = shlex.quote(tag)
        # Use awk to properly parse fields and match device name with virtiofs type
        find_mount_cmd = "awk '$1==%s && $3==\"virtiofs\" {print $2}' /proc/mounts" % safe_tag
        exitcode, mount_path, stderr = qga.guest_exec_bash(find_mount_cmd)

        if exitcode != 0 or not mount_path or not mount_path.strip():
            logger.info("No mount point found for virtiofs tag[%s] in VM[%s], skip unmount" % (
                tag, domain.name()))
            return True, None

        mount_path = mount_path.strip()
        logger.info("Found mount point[%s] for virtiofs[%s] in VM[%s]" % (
            mount_path, tag, domain.name()))

        # Unmount
        safe_mount_path = shlex.quote(mount_path)
        umount_cmd = "umount %s" % safe_mount_path

        logger.info("QGA: executing umount command: %s" % umount_cmd)
        exitcode, stdout, stderr = qga.guest_exec_bash(umount_cmd)

        if exitcode != 0:
            # Try lazy unmount if regular unmount fails
            error_msg = stderr if stderr else "unknown error"
            logger.warning("Regular unmount failed: %s, trying lazy unmount" % error_msg)

            umount_lazy_cmd = "umount -l %s" % safe_mount_path
            exitcode, stdout, stderr = qga.guest_exec_bash(umount_lazy_cmd)

            if exitcode != 0:
                error_msg = stderr if stderr else "unknown error"
                logger.error("Lazy unmount also failed: %s" % error_msg)
                return False, "Unmount failed: %s" % error_msg

        logger.info("Successfully unmounted virtiofs[%s] from[%s] inside VM[%s]" % (
            tag, mount_path, domain.name()))
        return True, None

    except Exception as e:
        logger.error("Exception during QGA unmount: %s\n%s" % (str(e), traceback.format_exc()))
        return False, "QGA unmount failed: %s" % str(e)


class VirtiofsPlugin(kvmagent.KvmAgent):
    """Virtiofs plugin for VM model mount"""

    ATTACH_VIRTIOFS_PATH = "/virtiofs/attach"
    DETACH_VIRTIOFS_PATH = "/virtiofs/detach"
    STATUS_VIRTIOFS_PATH = "/virtiofs/status"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.ATTACH_VIRTIOFS_PATH, self.attach_virtiofs)
        http_server.register_async_uri(self.DETACH_VIRTIOFS_PATH, self.detach_virtiofs)
        http_server.register_async_uri(self.STATUS_VIRTIOFS_PATH, self.virtiofs_status)

    def stop(self):
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
            logger.info("Attaching virtiofs to VM[%s], tag=%s, source=%s, mountPath=%s" % (
                cmd.vmInstanceUuid, cmd.tag, cmd.sourcePath, cmd.mountPath))

            # 1. Verify source path on host and get resolved path
            resolved_path = verify_source_path(cmd.sourcePath)

            # 2. Get VM domain
            domain, conn = get_vm_domain(cmd.vmInstanceUuid)

            # 3. Build virtiofs XML using resolved path
            xml_str = build_virtiofs_xml(cmd.tag, resolved_path)

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
