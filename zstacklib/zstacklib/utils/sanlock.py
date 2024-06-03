from zstacklib.utils import bash

@bash.in_bash
def dd_check_lockspace(path):
    return bash.bash_r("dd if=%s of=/dev/null bs=1M count=1 iflag=direct" % path)

@bash.in_bash
def vertify_delta_lease(vg_uuid, host_id):
    r, o = bash.bash_ro("sanlock direct read_leader -s lvm_%s:%s:/dev/mapper/%s-lvmlock:0" % (vg_uuid, host_id, vg_uuid))
    if r != 0:
        raise Exception("detected sanlock metadata corruption at offset %s length 512 on /dev/mapper/%s-lvmlock, the "
                        "content read is:\n%s\nWe suspect that there has been a storage malfunction!" % (int(host_id)*512-512, vg_uuid, o))


@bash.in_bash
def vertify_paxos_lease(vg_uuid, resource_name, offset):
    return bash.bash_roe("sanlock client read -r lvm_%s:%s:/dev/mapper/%s-lvmlock:%s" % (vg_uuid, resource_name, vg_uuid, offset))