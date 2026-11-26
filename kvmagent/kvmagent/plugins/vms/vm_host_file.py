import base64
import errno
import os
import pipes
import shutil
import tarfile
import tempfile

from zstacklib.utils import bash
from zstacklib.utils import log

logger = log.get_logger(__name__)

ALLOWED_PATH_PREFIXS = [
    '/var/lib/libvirt/qemu/nvram/',
    '/var/lib/libvirt/swtpm/',
]

ALLOWED_FILE_MAX_SIZE_BYTES = 16777216 # 16MB

class VmHostFileContentFormat(object):
    """file format constants, mirrors org.zstack.header.vm.additions.VmHostFileContentFormat"""
    RAW = 'Raw'
    TARBALL_GZIP = 'TarballGzip'


class VmHostFileOperation(object):
    """operation constants, mirrors org.zstack.header.vm.additions.VmHostFileOperation"""
    WRITE = 'Write'
    PREPARE = 'Prepare'
    DELETE = 'Delete'


class VmHostFileTO(object):
    def __init__(self):
        self.path = ''
        self.type = ''
        self.fileFormat = ''
        self.operation = ''
        self.contentBase64 = ''
        self.error = None  # type: str

class VmHostFileBackupJob(object):
    def __init__(self):
        self.srcPath = None   # type: str
        self.destPath = None  # type: str
        self.type = None      # type: str

def is_allowed_paths(path):
    # type: (str) -> bool
    if not path:
        return False
    raw_segments = [seg for seg in path.split(os.sep) if seg]
    if '..' in raw_segments:
        return False

    normalized = os.path.normpath(path)
    real_path = os.path.realpath(normalized)
    for prefix in ALLOWED_PATH_PREFIXS:
        # normpath strips trailing slash, e.g. "/var/lib/" -> "/var/lib"
        norm_prefix = os.path.normpath(prefix)
        real_prefix = os.path.realpath(norm_prefix)
        if real_path.startswith(real_prefix + os.sep):
            return True

    return False

def read_vm_host_file_base64(to):
    # type: (VmHostFileTO) -> None
    if not is_allowed_paths(to.path):
        to.error = "%s is not in allowed path" % to.path
        return
    if not os.path.isfile(to.path):
        to.error = "Path %s does not exist" % to.path
        return

    try:
        file_size = os.path.getsize(to.path)
        if file_size > ALLOWED_FILE_MAX_SIZE_BYTES:
            to.error = "File %s size %d exceeds limit %d" % (to.path, file_size, ALLOWED_FILE_MAX_SIZE_BYTES)
            return
    except (OSError, IOError) as e:
        to.error = "Failed to get file size: %s" % str(e)
        return

    try:
        with open(to.path, 'rb') as f:
            content = f.read()
    except (OSError, IOError) as e:
        to.error = 'failed to read vm host file on %s: %s' % (to.path, str(e))
        return

    to.fileFormat = 'Raw'
    to.contentBase64 = base64.b64encode(content)

def read_vm_host_file_targz(to):
    # type: (VmHostFileTO) -> None
    if not is_allowed_paths(to.path):
        to.error = "%s is not in allowed path" % to.path
        return
    if not os.path.exists(to.path):
        to.error = "Path %s does not exist" % to.path
        return

    tmp_dir = tempfile.mkdtemp(prefix="host_file_read_tgz_")
    tmp_tar_path = os.path.join(tmp_dir, "archive.tar.gz")

    try:
        base_path = to.path.rstrip("/")
        base_dir = os.path.dirname(base_path)
        target_name = os.path.basename(base_path)
        cmd = "tar -czf %s -C %s %s" % (pipes.quote(tmp_tar_path), pipes.quote(base_dir), pipes.quote(target_name))
        r, _, e = bash.bash_roe(cmd)
        if r != 0:
            to.error = "Failed to tar file: %s, stderr: %s" % (cmd, e)
            return

        if not os.path.isfile(tmp_tar_path):
            to.error = "Tarball was not created at %s" % tmp_tar_path
            return

        file_size = os.path.getsize(tmp_tar_path)
        if file_size > ALLOWED_FILE_MAX_SIZE_BYTES:
            to.error = "Tar File size %d exceeds limit %d" % (file_size, ALLOWED_FILE_MAX_SIZE_BYTES)
            return

        with open(tmp_tar_path, 'rb') as f:
            content = f.read()

        to.fileFormat = 'TarballGzip'
        to.contentBase64 = base64.b64encode(content)
    except Exception as ex:
        to.error = "Internal error during read_vm_host_file_targz: %s" % str(ex)
    finally:
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)

def _resolve_operation(to):
    # type: (VmHostFileTO) -> str
    """Resolve the operation from the TO fields.

    New MN sends ``operation`` explicitly (Write / Prepare / Delete).
    """
    if to.operation:
        return to.operation

    return VmHostFileOperation.WRITE


def write_vm_host_file(to):
    # type: (VmHostFileTO) -> None
    if not is_allowed_paths(to.path):
        to.error = "%s is not in allowed path" % to.path
        return

    operation = _resolve_operation(to)
    logger.debug('try to %s VmHostFile %s' % (operation, to.path))

    if operation == VmHostFileOperation.PREPARE:
        _prepare_vm_host_file(to.path)
    elif operation == VmHostFileOperation.DELETE:
        _delete_vm_host_file(to.path)
    elif operation == VmHostFileOperation.WRITE:
        _write_vm_host_file(to)
    else:
        raise ValueError("Unsupported operation: %s" % operation)


def _write_vm_host_file(to):
    # type: (VmHostFileTO) -> None
    if not to.contentBase64:
        raise ValueError("contentBase64 is required for fileFormat: %s" % to.fileFormat)
    try:
        # raw_data is str in python 2.7
        raw_data = base64.b64decode(to.contentBase64) # type: str
    except Exception as e:
        raise ValueError("Failed to decode base64 content: %s" % str(e))

    file_format = to.fileFormat or VmHostFileContentFormat.RAW
    if file_format == VmHostFileContentFormat.RAW:
        _write_vm_host_file_with_raw_format(to.path, raw_data)
    elif file_format == VmHostFileContentFormat.TARBALL_GZIP:
        _write_vm_host_file_with_targz_format(to.path, raw_data)
    else:
        raise ValueError("Unsupported fileFormat: %s" % to.fileFormat)

def _write_vm_host_file_with_raw_format(path, raw_data):
    # type: (str, str) -> None
    target_dir = os.path.dirname(path)
    try:
        os.makedirs(target_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:  # ignore folder already exists error
            raise

    try:
        with open(path, 'wb') as f:
            f.write(raw_data)
            f.flush()
            os.fsync(f.fileno())
    except (IOError, OSError) as e:
        raise IOError("Failed to write file at %s: %s" % (path, str(e)))

def _write_vm_host_file_with_targz_format(path, raw_data):
    # type: (str, str) -> None
    target_dir = os.path.dirname(path)
    try:
        os.makedirs(target_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:  # ignore folder already exists error
            raise

    tmp_work_dir = tempfile.mkdtemp(prefix="host_file_tgz_")
    tmp_tar_file = os.path.join(tmp_work_dir, "data.tar.gz")
    extract_dir = os.path.join(tmp_work_dir, "out")
    os.makedirs(extract_dir)

    try:
        with open(tmp_tar_file, 'wb') as f:
            f.write(raw_data)
            f.flush()
            os.fsync(f.fileno())

        with tarfile.open(tmp_tar_file, 'r:gz') as tar:
            for member in tar.getmembers():
                normalized = os.path.normpath(member.name)
                if os.path.isabs(member.name) or normalized.startswith('..'):
                    raise ValueError("Unsafe tar entry detected: %s" % member.name)

                if member.issym() or member.islnk():
                    raise ValueError("Symbolic or hard links are not allowed: %s" % member.name)

                if member.isdev() or member.ischr() or member.isblk() or member.isfifo():
                    raise ValueError("Device files or special files are not allowed: %s" % member.name)

        cmd = "tar -xzf %s -C %s" % (pipes.quote(tmp_tar_file), pipes.quote(extract_dir))
        r, _, e = bash.bash_roe(cmd)
        if r != 0:
            raise RuntimeError("Failed to untar data: %s, stderr: %s" % (cmd, e))

        items = os.listdir(extract_dir)
        if not items:
            raise ValueError("Tarball is empty, nothing to write to %s" % path)
        if len(items) != 1:
            raise ValueError("Tarball must contain exactly one top-level entry, got %d" % len(items))

        if os.path.exists(path):
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)

        source_content = os.path.join(extract_dir, items[0])
        shutil.move(source_content, path)

    except Exception as ex:
        raise IOError("Failed to process TarballGzip for %s: %s" % (path, str(ex)))
    finally:
        if os.path.exists(tmp_work_dir):
            shutil.rmtree(tmp_work_dir)


def _delete_vm_host_file(path):
    # type: (str) -> None
    """Delete a file or directory at *path*.

    If *path* is a directory it is removed recursively.  If *path* does not
    exist the call is a no-op so the operation is idempotent.

    After removing the target, any empty ancestor directories that are still
    inside the ALLOWED_PATH_PREFIXS are cleaned up as well.
    """
    if not os.path.exists(path):
        logger.debug('delete vm host file skipped, path does not exist: %s' % path)
        return

    if os.path.isdir(path):
        shutil.rmtree(path)
        logger.debug('deleted vm host file directory: %s' % path)
    else:
        os.remove(path)
        logger.debug('deleted vm host file: %s' % path)

    parent = os.path.dirname(path.rstrip('/'))
    for prefix in ALLOWED_PATH_PREFIXS:
        prefix = prefix.rstrip('/')
        if not parent.startswith(prefix):
            continue
        while parent != prefix and parent > prefix:
            if not os.path.isdir(parent):
                break
            try:
                os.rmdir(parent)
                logger.debug('cleaned up empty ancestor directory: %s' % parent)
            except OSError:
                # directory not empty or other error: stop climbing
                break
            parent = os.path.dirname(parent)
        break


def _prepare_vm_host_file(path):
    # type: (str) -> None
    # only create folder
    target_dir = os.path.dirname(path)
    try:
        os.makedirs(target_dir)
    except OSError as e:
        if e.errno != errno.EEXIST:  # ignore folder already exists error
            raise


def backup_vm_host_files(backup_jobs):
    """Execute a list of VmHostFileBackupJob: copy srcPath -> destPath.

    Each job copies a file or directory.  If destPath already exists it is
    removed first so that the copy is always clean.  Both srcPath and destPath
    must pass ``is_allowed_paths()`` security check.

    :param backup_jobs: list of VmHostFileBackupJob (jsonobject or dict),
                        may be None or empty.
    """
    if not backup_jobs:
        return

    for job in backup_jobs:
        # compatible with both dict and jsonobject dynamic attribute access
        if isinstance(job, dict):
            src = job.get('srcPath')
            dst = job.get('destPath')
            file_type = job.get('type')
        else:
            src = getattr(job, 'srcPath', None)
            dst = getattr(job, 'destPath', None)
            file_type = getattr(job, 'type', None)

        if not src or not dst:
            raise Exception("VmHostFileBackupJob srcPath and destPath are required")

        if not is_allowed_paths(src):
            raise Exception("%s is not in allowed path" % src)
        if not is_allowed_paths(dst):
            raise Exception("%s is not in allowed path" % dst)

        if not os.path.exists(src):
            raise Exception("backup source %s does not exist" % src)

        logger.debug("VmHostFileBackupJob[type=%s]: copy %s -> %s" % (file_type, src, dst))

        # remove existing dest first to ensure a clean copy
        dst_normalized = dst.rstrip('/')
        src_normalized = src.rstrip('/')
        src_real = os.path.realpath(src_normalized)
        dst_real = os.path.realpath(dst_normalized)

        if src_real == dst_real:
            raise Exception("srcPath and destPath must not be the same: %s" % src)
        if src_real.startswith(dst_real + os.sep) or dst_real.startswith(src_real + os.sep):
            raise Exception("srcPath and destPath must not overlap: %s -> %s" % (src, dst))

        if os.path.exists(dst_normalized):
            if os.path.isdir(dst_normalized):
                shutil.rmtree(dst_normalized)
            else:
                os.remove(dst_normalized)

        # ensure parent directory exists
        dst_parent = os.path.dirname(dst_normalized)
        if dst_parent:
            try:
                os.makedirs(dst_parent, 0o755)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise

        # copy file or directory
        if os.path.isdir(src_normalized):
            for root, dirs, files in os.walk(src_normalized):
                for name in dirs + files:
                    p = os.path.join(root, name)
                    if os.path.islink(p):
                        raise Exception("Symbolic link is not allowed in backup source: %s" % p)
            shutil.copytree(src_normalized, dst_normalized)
        else:
            shutil.copy2(src_normalized, dst_normalized)
