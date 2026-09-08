import os
import re
import threading

from zstacklib.system.filesystem import get_mounts, read_file
from zstacklib.utils import shell

HUGEPAGE_SIZE_BYTES = 2 * 1024 * 1024
HUGEPAGE_DIR = "/sys/kernel/mm/hugepages/hugepages-2048kB"
HUGEPAGE_NR_PATH = HUGEPAGE_DIR + "/nr_hugepages"
HUGEPAGE_FREE_PATH = HUGEPAGE_DIR + "/free_hugepages"
_HUGEPAGE_LOCK = threading.RLock()


def mem_to_pages(nbytes, page_size=HUGEPAGE_SIZE_BYTES):
    return (int(nbytes) + page_size - 1) // page_size


def get_default_page_size():
    default_size = 0
    for line in read_file("/proc/meminfo").splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0] == "Hugepagesize:" and fields[2] == "kB":
            default_size = int(fields[1]) * 1024
            break
    if default_size <= 0:
        raise ValueError('unable to determine default hugepage size from /proc/meminfo')
    sizes = []
    for mount in get_mounts():
        if mount.fs_type == "hugetlbfs":
            path = re.sub(r'\\([0-7]{3})', lambda match: chr(int(match.group(1), 8)), mount.mount_point)
            sizes.append(os.statvfs(path).f_bsize)
    if not sizes:
        raise RuntimeError('no hugetlbfs mount found')
    return default_size if default_size in sizes else sizes[0]


def _hugepage_path(page_size, counter):
    return "/sys/kernel/mm/hugepages/hugepages-%dkB/%s" % (page_size // 1024, counter)


def _read_hugepage_nr(page_size=HUGEPAGE_SIZE_BYTES):
    path = _hugepage_path(page_size, "nr_hugepages")
    if not os.path.exists(path):
        raise Exception("hugepage sysfs not found: %s" % path)
    return int(shell.call("cat %s" % path).strip() or "0")


def _read_hugepage_free(page_size=HUGEPAGE_SIZE_BYTES):
    path = _hugepage_path(page_size, "free_hugepages")
    if not os.path.exists(path):
        raise Exception("hugepage sysfs not found: %s" % path)
    return int(shell.call("cat %s" % path).strip() or "0")


def ensure_free_hugepages(need_pages, page_size=HUGEPAGE_SIZE_BYTES):
    with _HUGEPAGE_LOCK:
        free = _read_hugepage_free(page_size)
        if free >= need_pages:
            return
        total = _read_hugepage_nr(page_size)
        target = total + (need_pages - free)
        shell.call("echo %d > %s" % (target, _hugepage_path(page_size, "nr_hugepages")))
        got = _read_hugepage_free(page_size)
        if got < need_pages:
            raise Exception("failed to free %d hugepages, only %d free after growing to %d; "
                            "free up memory on the host" % (need_pages, got, target))


def reclaim_hugepages(slack=0, page_size=HUGEPAGE_SIZE_BYTES):
    with _HUGEPAGE_LOCK:
        free = _read_hugepage_free(page_size)
        total = _read_hugepage_nr(page_size)
        keep = (total - free) + slack
        if keep < total:
            shell.call("echo %d > %s" % (keep, _hugepage_path(page_size, "nr_hugepages")))
