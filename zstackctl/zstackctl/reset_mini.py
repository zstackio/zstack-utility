import base64
import functools
import inspect
import json
import logging
import re
import subprocess
import sys
import time
import os
import shutil
from jinja2 import Template


def retry(times=3, sleep_time=3):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            for i in range(0, times):
                try:
                    return f(*args, **kwargs)
                except:
                    time.sleep(sleep_time)
            raise

        return inner

    return wrap


def in_bash(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        __BASH_DEBUG_INFO__ = []

        start_time = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            end_time = time.time()
            logger.debug('BASH COMMAND DETAILS IN %s [cost %s ms]: %s' % (
            func.__name__, (end_time - start_time) * 1000, json.dumps(__BASH_DEBUG_INFO__)))
            del __BASH_DEBUG_INFO__

    return wrap


def __collect_locals_on_stack():
    frames = []
    frame = inspect.currentframe()
    while frame:
        frames.insert(0, frame)
        frame = frame.f_back

    ctx = {}
    for f in frames:
        ctx.update(f.f_locals)

    return ctx


def get_process(cmd, shell=None, workdir=None, pipe=None, executable=None):
    if pipe:
        return subprocess.Popen(cmd, shell=shell, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                close_fds=True, executable=executable, cwd=workdir)
    else:
        return subprocess.Popen(cmd, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                close_fds=True, executable=executable, cwd=workdir)


def bash_eval(raw_str, ctx=None):
    if not ctx:
        ctx = __collect_locals_on_stack()

    while True:
        unresolved = re.findall('{{(.+?)}}', raw_str)
        if not unresolved:
            break

        for u in unresolved:
            if u not in ctx:
                raise Exception('unresolved symbol {{%s}}' % u)

        tmpt = Template(raw_str)
        raw_str = tmpt.render(ctx)

    return raw_str


# @return: return code, stdout, stderr
def bash_roe(cmd, errorout=False, ret_code=0, pipe_fail=False):
    # type: (str, bool, int, bool) -> (int, str, str)
    ctx = __collect_locals_on_stack()

    cmd = bash_eval(cmd, ctx)
    p = get_process("/bin/bash", pipe=True)
    if pipe_fail:
        cmd = 'set -o pipefail; %s' % cmd
    o, e = p.communicate(cmd)
    r = p.returncode

    __BASH_DEBUG_INFO__ = ctx.get('__BASH_DEBUG_INFO__')
    if __BASH_DEBUG_INFO__ is not None:
        __BASH_DEBUG_INFO__.append({
            'cmd': cmd,
            'return_code': p.returncode,
            'stdout': o,
            'stderr': e
        })

    if r != ret_code and errorout:
        raise Exception('failed to execute bash[%s], return code: %s, stdout: %s, stderr: %s' % (cmd, r, o, e))
    if r == ret_code:
        e = None

    return r, o, e


# @return: return code, stdout
def bash_ro(cmd, pipe_fail=False):
    # type: (str, bool) -> (int, str)
    ret, o, _ = bash_roe(cmd, pipe_fail=pipe_fail)
    return ret, o


# @return: stdout
def bash_o(cmd, pipe_fail=False):
    # type: (str, bool) -> str
    _, o, _ = bash_roe(cmd, pipe_fail=pipe_fail)
    return o


# @return: return code
def bash_r(cmd, pipe_fail=False):
    ret, _, _ = bash_roe(cmd, pipe_fail=pipe_fail)
    return ret


def rm_file_force(fpath):
    try:
        os.remove(fpath)
    except:
        pass


def rm_dir_force(dpath, only_check=False):
    black_dpath_list = ["", "/", "*", "/root", "/var", "/bin", "/lib", "/sys"]
    if dpath.strip() in black_dpath_list:
        raise Exception("how dare you delete directory %s" % dpath)
    if os.path.exists(dpath) and not only_check:
        if os.path.isdir(dpath):
            shutil.rmtree(dpath)
        else:
            rm_file_force(dpath)
    else:
        return dpath


def umount_by_path(path):
    paths = get_mounted_url_by_dir(path)
    if not paths: return
    for p in paths:
        bash_r('umount -f -l %s' % p)


def get_mounted_url_by_dir(path):
    r, o = bash_ro("mount | grep '%s'" % path)
    if r:
        return []
    else:
        return [l.split(' ')[2] for l in o.splitlines()]


def get_disk_holders(disk_names):
    holders = []
    for disk_name in disk_names:
        p = "/sys/class/block/%s/holders/" % disk_name
        if not os.path.isdir(p):
            continue
        h = os.listdir(p)
        if len(h) == 0:
            continue
        holders.extend(h)
        holders.extend(get_disk_holders(h))
    holders.reverse()
    return holders


def drop_vg_lock(vgUuid):
    bash_roe("lvmlockctl --gl-disable %s" % vgUuid)
    bash_roe("lvmlockctl --drop %s" % vgUuid)


def remove_device_map_for_vg(vgUuid):
    o = bash_o("dmsetup ls | grep %s | awk '{print $1}'" % vgUuid).strip().splitlines()
    if len(o) == 0:
        return
    for dm in o:
        bash_roe("dmsetup remove %s" % dm.strip())


@in_bash
def wipe_fs(disks, expected_vg=None, with_lock=True):
    for disk in disks:
        exists_vg = None
        r = bash_r("pvdisplay %s | grep %s" % (disk, expected_vg))
        if r == 0:
            continue

        r, o = bash_ro("pvs --nolocking --noheading -o vg_name %s" % disk)
        if r == 0 and o.strip() != "":
            exists_vg = o.strip()

        need_flush_mpath = False

        bash_roe("partprobe -s %s" % disk)

        cmd_type = bash_o("lsblk %s -oTYPE | grep mpath" % disk)
        if cmd_type.strip() != "":
            need_flush_mpath = True

        bash_roe("wipefs -af %s" % disk)

        if need_flush_mpath:
            bash_roe("multipath -f %s && systemctl restart multipathd.service && sleep 1" % disk)

        for holder in get_disk_holders([disk.split("/")[-1]]):
            if not holder.startswith("dm-"):
                continue
            bash_roe("dmsetup remove /dev/%s" % holder)

        if exists_vg is not None:
            bash_r("grep %s /etc/drbd.d/* | awk '{print $1}' | sort | uniq | tr -d ':' | xargs rm" % exists_vg)
            logger.debug("found vg %s exists on this pv %s, start wipe" %
                         (exists_vg, disk))
            try:
                if with_lock:
                    drop_vg_lock(exists_vg)
                remove_device_map_for_vg(exists_vg)
            finally:
                pass


# from zstacklib.utils import bash
# from zstacklib.utils import linux
# from zstacklib.utils import lvm


logging.basicConfig(filename='/tmp/reset_mini_host.log', level=logging.DEBUG,
                    format='%(asctime)s %(process)d %(levelname)s %(funcName)s %(message)s')
logger = logging.getLogger(__name__)


@in_bash
@retry(times=3, sleep_time=1)
def stop_server():
    r, o, e = bash_roe("zsha2 stop-node || zstack-ctl stop")
    r1, o1 = bash_ro("pgrep -af -- '-DappName=zstack start'")
    if r1 == 0:
        raise Exception(
            "stop zstack failed, return code: %s, stdout: %s, stderr: %s, pgrep zstack return code: %s, stdout: %s" %
            (r, o, e, r1, o1))
    
    bash_roe("systemctl stop zstack-ha.service")
    bash_roe("systemctl disable zstack-ha.service")


@in_bash
def stop_kvmagent():
    bash_roe("/etc/init.d/zstack-kvmagent stop")
    bash_roe("pkill -9 -f 'c from kvmagent import kdaemon'")


@in_bash
def stop_vms():
    bash_roe("pkill -f -9 '/usr/libexec/qemu-kvm -name guest'")
    bash_roe("pkill -f -9 '/var/lib/zstack/colo/qemu-system-x86_64 -name guest'")
    time.sleep(1)


@in_bash
def cleanup_storage():
    def get_live_drbd_minor():
        return bash_o(
            "cat /proc/drbd | grep -E '^[[:space:]]*[0-9]+\: ' | awk '{print $1}' | cut -d ':' -f1").strip().splitlines()

    def kill_drbd_holder(minor):
        if minor == "" or minor is None:
            return
        lines = bash_o("lsof /dev/drbd%s | grep -v '^COMMAND'" % minor).splitlines()
        if len(lines) == 0:
            return
        for line in lines:
            bash_r("kill -9 %s" % line.split()[1])

    def get_mini_pv():
        vg_name = bash_o("vgs --nolocking -oname,tags | grep zs::ministorage | awk '{print $1}'").strip()
        pv_names = bash_o("pvs --nolocking -oname -Svg_name=%s | grep -v PV" % vg_name).strip().splitlines()
        return [p.strip() for p in pv_names]

    bash_r("rm -rf /zstack_bs")
    bash_roe("drbdadm down all")
    if len(get_live_drbd_minor()) != 0:
        for m in get_live_drbd_minor():
            kill_drbd_holder(m)
        bash_roe("drbdadm down all")
    bash_r("/bin/rm /etc/drbd.d/*.res")
    mini_cache_volume_mount_dir = "/var/lib/zstack/colo/cachevolumes/"
    umount_by_path(mini_cache_volume_mount_dir)
    rm_dir_force(mini_cache_volume_mount_dir)
    wipe_fs(get_mini_pv())


@in_bash
def cleanup_zstack():
    bash_r("mysql -uroot -pzstack.mysql.password -e 'STOP SLAVE; RESET SLAVE ALL;'")
    bash_r("rm -rf /usr/local/zstack/apache-tomcat/logs/")
    bash_r("rm -rf /var/log/zstack/")
    bash_r("rm -rf /usr/local/zstack")
    bash_r("bash /opt/zstack-dvd/x86_64/c76/zstack-installer.bin -D -I 127.0.0.1")
    bash_r("bash /opt/zstack-dvd/x86_64/c76/zstack_mini_server.bin -a")
    bash_r("systemctl disable zstack.service")


@in_bash
def clear_network():
    bash_r("iptables -F; iptables -t nat -F; iptables -t mangle -F; iptables -t raw -F")
    bash_r("ebtables -F; ebtables -t nat -F")
    all_links = [x.strip().strip(":") for x in bash_o("ip -o link | awk '{print $2}'").strip().splitlines()]
    for i in all_links:
        if i not in ["lo", "eno1", "eno2", "ens2f0", "ens2f1"]:
            bash_r("ip link del %s" % i.split("@")[0])


@in_bash
def reset_network():
    bash_r(
        "ip link set dev eno1 nomaster; ip link set dev eno2 nomaster; ip link set dev ens2f0 nomaster; ip link set dev ens2f1 nomaster")
    bash_r("ip -4 a flush eno1; ip -4 a flush eno2; ip -4 a flush ens2f0; ip -4 a flush ens2f1")
    bash_r("ip r del default")
    bash_r("ls /etc/sysconfig/network-scripts/ifcfg-* | grep -E 'ifcfg-eno1|ifcfg-eno2|ifcfg-ens2f0|ifcfg-ens2f1' | xargs sed -i -E 's/(IPADDR.*|NETMASK.*|GATEWAY.*|SLAVE.*|MASTER.*)//g'")
    bash_r("ls /etc/sysconfig/network-scripts/ifcfg-* | grep -Ev 'ifcfg-lo|ifcfg-eno1|ifcfg-eno2|ifcfg-ens2f0|ifcfg-ens2f1' | xargs /bin/rm")
    bash_r("systemctl restart network")
    clear_network()
    sn = bash_o("dmidecode -s system-serial-number").strip()
    if sn[-1] == "B":
        bash_r(
            "export PATH=$PATH:/usr/local/bin/; /usr/local/bin/zs-network-setting -i eno1 100.66.66.67 255.255.255.0")
        bash_r("ip link set dev eno1 up")
    elif sn[-1] == "A":
        bash_r(
            "export PATH=$PATH:/usr/local/bin/; /usr/local/bin/zs-network-setting -i eno1 100.66.66.66 255.255.255.0")
        bash_r("ip link set dev eno1 up")
    else:
        raise Exception("serial number not last with A or B!")
    # bash.bash_r("sed -i 's/ui_mode = .*/ui_mode = mini/g' /usr/local/zstack/apache-tomcat/webapps/zstack/WEB-INF/classes/zstack.properties")
    bash_r("systemctl restart zstack-network-agent.service")


@in_bash
def reset_system():
    reset_network()
    p = "enN0YWNrLm9yZ0A2MzdF"
    bash_r("echo 'root:%s' | chpasswd" % base64.decodestring(p))
    logger.info("reset system done")



def main(args):
    stop_server()
    stop_kvmagent()
    stop_vms()
    cleanup_storage()
    cleanup_zstack()
    reset_system()


if __name__ == "__main__":
    main(sys.argv[1:])
