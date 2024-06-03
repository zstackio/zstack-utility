import sys
sys.path.append("/var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages/")

import json
from zstacklib.utils import bash
from zstacklib.utils import lvm
from zstacklib.utils import log
from zstacklib.utils import qemu_img

log.configure_log("/var/log/zstack/convert_volume.log", log_to_console=False)
logger = log.get_logger(__name__)

START_TAG = "zs-start-convert"
DONE_TAG = "zs-convert-done"
RAW_SUFFIX = "_zs_convert_raw"
QCOW2_SUFFIX = "_zs_convert_qcow2"


@bash.in_bash
def get_volume_format(path):
    info = json.loads(bash.bash_o("%s %s --output json" % (qemu_img.subcmd('info'), path)))
    logger.debug(info)
    return info["format"]


def check(volume_abs_path, raw_volume_abs_path):
    with lvm.OperateLv(volume_abs_path, shared=False, delete_when_exception=False):
        if get_volume_format(volume_abs_path) == "raw":
            raise Exception("volume %s is raw format, no need to convert" % volume_abs_path)
        if lvm.has_lv_tag(volume_abs_path, START_TAG):
            raise Exception("there is tag %s on volume %s, there may other process processing, please check or wait" % (START_TAG, volume_abs_path))
        if lvm.has_lv_tag(volume_abs_path, DONE_TAG):
            raise Exception("there is tag %s on volume %s, there may other process processing, please check or wait" % (DONE_TAG, volume_abs_path))
    if lvm.lv_exists(raw_volume_abs_path):
        raise Exception("there is raw volume %s, there may other process processing, please check or wait" % raw_volume_abs_path)


@bash.in_bash
def qcow2_convert_to_raw(src, dst):
    return bash.bash_roe('%s -f qcow2 -O raw %s %s' % (qemu_img.subcmd('convert'), src, dst))


def do_convert(args):
    volume_abs_path = args[1]
    raw_volume_abs_path = volume_abs_path + RAW_SUFFIX
    qcow2_volume_abs_path = volume_abs_path + QCOW2_SUFFIX
    check(volume_abs_path, raw_volume_abs_path)

    volume_size = lvm.get_lv_size(volume_abs_path)
    lvm.create_lv_from_absolute_path(raw_volume_abs_path, volume_size)
    with lvm.RecursiveOperateLv(volume_abs_path, shared=False, delete_when_exception=False):
        with lvm.OperateLv(raw_volume_abs_path, shared=False, delete_when_exception=False):
            lvm.add_lv_tag(volume_abs_path, START_TAG)
            r, o, e = qcow2_convert_to_raw(volume_abs_path, raw_volume_abs_path)
            if r != 0:
                logger.warn("convert failed: %s, removing tag and raw volume")
                lvm.clean_lv_tag(volume_abs_path, START_TAG)
                lvm.delete_lv(raw_volume_abs_path)
                return
            lvm.add_lv_tag(volume_abs_path, DONE_TAG)
            lvm.clean_lv_tag(volume_abs_path, START_TAG)
            lvm.lv_rename(volume_abs_path, qcow2_volume_abs_path, overwrite=False)
            lvm.lv_rename(raw_volume_abs_path, volume_abs_path, overwrite=False)


def do_find_qcow2(vgUuid):
    paths = []
    raw_paths = bash.bash_o('lvs --nolocking -t --noheading -Slv_name=~".*%s" -Stags={%s} -opath %s' % (QCOW2_SUFFIX, DONE_TAG, vgUuid)).strip().splitlines()
    for raw_path in raw_paths:
        paths.append(raw_path.strip())
    sys.stdout.write(",".join(paths))
    sys.stdout.flush()
    return paths


def do_delete_qcwo2(op, vguuid):
    paths = do_find_qcow2(vguuid)
    if op == "find_qcow2":
        return
    for path in paths:
        lvm.delete_lv(path)


def main(args):
    if args[0] == "convert":
        do_convert(args)
    if args[0] == "find_qcow2":
        do_delete_qcwo2(args[0], args[1])
    if args[0] == "delete_qcow2":
        do_delete_qcwo2(args[0], args[1])


if __name__ == "__main__":
    main(sys.argv[1:])
