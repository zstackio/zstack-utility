import base64
import errno
import os
import pipes
import shutil
import tarfile
import tempfile

from zstacklib.utils import bash

ALLOWED_PATH_PREFIXS = [
    '/var/lib/libvirt/qemu/nvram/',
    '/var/lib/libvirt/swtpm/',
]

ALLOWED_FILE_MAX_SIZE_BYTES = 16777216 # 16MB

class VmHostFileTO(object):
    def __init__(self):
        self.path = ''
        self.type = ''
        self.fileFormat = ''
        self.contentBase64 = ''
        self.error = None  # type: str

def is_allowed_paths(path):
    # type: (str) -> bool
    if not path:
        return False
    return path.startswith(tuple(ALLOWED_PATH_PREFIXS))

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

def write_vm_host_file(to):
    # type: (VmHostFileTO) -> None
    if not is_allowed_paths(to.path):
        to.error = "%s is not in allowed path" % to.path
        return
    if not to.contentBase64:
        return

    try:
        # raw_data is str in python 2.7
        raw_data = base64.b64decode(to.contentBase64) # type: str
    except Exception as e:
        raise ValueError("Failed to decode base64 content: %s" % str(e))

    if to.fileFormat == 'Raw':
        _write_vm_host_file_with_raw_format(to.path, raw_data)
    elif to.fileFormat == 'TarballGzip':
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
