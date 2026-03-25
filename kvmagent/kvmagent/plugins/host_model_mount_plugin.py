# Copyright (c) 2025, ZStack, Inc.
# ZSTAC-83157: Host model mount plugin for Model Center pre-mounting

import os
import re
import uuid
import shlex
import traceback
import jsonobject
from urllib.parse import urlsplit, urlunsplit
from kvmagent import kvmagent
from zstacklib.utils import log, shell, jsonutils

logger = log.get_logger(__name__)

# Base directory for Model Center mounts
MODEL_MOUNT_BASE = "/opt/zstack/models"

# UUID validation regex
UUID_RE = re.compile(r'^[0-9a-fA-F-]{36}$')


def _mask_url(url):
    """Mask sensitive info in URL for logging."""
    try:
        parts = urlsplit(url)
        if '@' not in parts.netloc:
            return url
        auth, host = parts.netloc.rsplit('@', 1)
        if ':' in auth:
            user, _ = auth.split(':', 1)
            masked_auth = ('%s:***' % user) if user else ':***'
        else:
            masked_auth = '***'
        return urlunsplit((parts.scheme, '%s@%s' % (masked_auth, host),
                          parts.path, parts.query, parts.fragment))
    except Exception:
        return '***'


class MountModelCenterCmd(jsonobject.JsonObject):
    """Command to mount Model Center storage to host"""
    modelCenterUuid = str
    storageUrl = str     # JuiceFS meta URL (e.g., redis://redis-host:6379/0)


class MountModelCenterResponse(jsonobject.JsonObject):
    success = bool
    error = str
    mountPoint = str


def ensure_mount_base_dir():
    """Ensure the base mount directory exists"""
    if not os.path.exists(MODEL_MOUNT_BASE):
        os.makedirs(MODEL_MOUNT_BASE, exist_ok=True)
        logger.info("Created model mount base directory: %s" % MODEL_MOUNT_BASE)


def check_juicefs_installed():
    """Check if juicefs binary is available

    Returns: (installed, error_message)
    """
    # Check common installation paths
    juicefs_paths = [
        "/usr/local/bin/juicefs",
        "/usr/bin/juicefs",
        "/opt/zstack/bin/juicefs"
    ]

    for path in juicefs_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            logger.debug("Found juicefs binary at %s" % path)
            return True, None

    # Try to find in PATH using shell.ShellCmd
    which_cmd = shell.ShellCmd("which juicefs")
    which_cmd(False)
    if which_cmd.return_code == 0:
        logger.debug("Found juicefs in PATH")
        return True, None

    error_msg = ("juicefs binary not found. Please install juicefs to "
                 "/usr/local/bin/juicefs or any location in PATH. "
                 "Download from: https://github.com/juicedata/juicefs/releases")
    return False, error_msg


def mount_juicefs(zdfs_url, mount_point):
    """Mount JuiceFS models directory to the specified mount point

    JuiceFS directory structure:
    /                           <- JuiceFS root
    ├── models/                 <- Models directory (physical host mounts this)
    │   └── {model_name}/
    │       └── {version}/
    │           └── model.yaml
    └── datasets/               <- Datasets directory (not needed on physical host)

    Model Center VM:
        - Mounts entire JuiceFS to /root/bentoml
        - Models at: /root/bentoml/models/{model_name}/

    Physical Host:
        - Mounts only models/ subdirectory using --subdir models
        - Mount point: /opt/zstack/models/{mcUuid}
        - Models at: /opt/zstack/models/{mcUuid}/{model_name}/
    """
    try:
        # Check if already mounted
        if os.path.ismount(mount_point):
            logger.info("Mount point %s is already mounted" % mount_point)
            return True, None

        # Create mount point
        os.makedirs(mount_point, exist_ok=True)

        # Check if juicefs binary is available
        installed, error_msg = check_juicefs_installed()
        if not installed:
            logger.error(error_msg)
            return False, error_msg

        # JuiceFS mount command
        # Mount only the models/ subdirectory using --subdir models
        # The zdfs_url is the meta URL (e.g., redis://redis-host:6379/0)
        cache_dir = "/var/cache/juicefs"
        # Use shlex.quote to prevent shell injection
        cmd = "juicefs mount %s %s --read-only -d --subdir models --cache-dir %s" % (
            shlex.quote(zdfs_url), shlex.quote(mount_point), shlex.quote(cache_dir))

        logger.info("Executing mount command for Model Center, mount_point=%s, url=%s" % (
            mount_point, _mask_url(zdfs_url)))

        mount_cmd = shell.ShellCmd(cmd)
        mount_cmd(False)
        if mount_cmd.return_code != 0:
            error_msg = mount_cmd.stderr or "Mount command failed"
            logger.error("Failed to mount JuiceFS: %s" % error_msg)
            return False, error_msg

        logger.info("Successfully mounted JuiceFS at %s" % mount_point)
        return True, None

    except Exception as e:
        logger.error("Exception during JuiceFS mount: %s" % str(e))
        return False, str(e)


class HostModelMountPlugin(kvmagent.KvmAgent):
    """Host model mount plugin for Model Center pre-mounting"""

    MOUNT_PATH = "/modelcenter/mount"
    LIST_PATH = "/modelcenter/list"

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.MOUNT_PATH, self.mount_model_center)
        http_server.register_async_uri(self.LIST_PATH, self.list_model_centers)

    def stop(self):
        pass

    @kvmagent.replyerror
    def mount_model_center(self, req):
        """Mount Model Center storage to host"""
        cmd = jsonobject.loads(req[http.REQUEST_BODY], MountModelCenterCmd)
        rsp = MountModelCenterResponse()
        rsp.success = False

        try:
            logger.info("Mounting Model Center[%s] with URL: %s" % (
                cmd.modelCenterUuid, _mask_url(cmd.storageUrl)))

            # Validate modelCenterUuid format to prevent path traversal
            if not cmd.modelCenterUuid or not UUID_RE.fullmatch(cmd.modelCenterUuid):
                rsp.error = "invalid modelCenterUuid"
                return jsonutils.dumps(rsp)

            # Ensure base directory exists
            ensure_mount_base_dir()

            # Build mount point path with boundary check
            mount_point = os.path.abspath(os.path.join(MODEL_MOUNT_BASE, cmd.modelCenterUuid))
            base_real = os.path.realpath(MODEL_MOUNT_BASE)
            target_real = os.path.realpath(mount_point)

            if os.path.commonpath([base_real, target_real]) != base_real:
                rsp.error = "invalid mount path"
                return jsonutils.dumps(rsp)

            rsp.mountPoint = mount_point

            # Mount
            success, error = mount_juicefs(cmd.storageUrl, mount_point)
            if success:
                rsp.success = True
                logger.info("Successfully mounted Model Center[%s] at %s" % (
                    cmd.modelCenterUuid, mount_point))
            else:
                rsp.error = error

        except Exception as e:
            logger.error("Failed to mount Model Center: %s\n%s" % (
                str(e), traceback.format_exc()))
            rsp.error = str(e)

        return jsonutils.dumps(rsp)

    @kvmagent.replyerror
    def list_model_centers(self, req):
        """List mounted Model Centers"""
        rsp = jsonobject.NewType()
        rsp.success = True
        rsp.mounts = []

        try:
            if os.path.exists(MODEL_MOUNT_BASE):
                for name in os.listdir(MODEL_MOUNT_BASE):
                    mount_point = os.path.join(MODEL_MOUNT_BASE, name)
                    is_mounted = os.path.ismount(mount_point)
                    rsp.mounts.append({
                        "modelCenterUuid": name,
                        "mountPoint": mount_point,
                        "isMounted": is_mounted
                    })
        except Exception as e:
            logger.error("Failed to list model centers: %s" % str(e))
            rsp.error = str(e)
            rsp.success = False

        return jsonutils.dumps(rsp)
