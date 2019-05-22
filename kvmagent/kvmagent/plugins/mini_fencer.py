#!/usr/bin/env python
import functools
import sys
import commands
import logging
import time
import re

logging.basicConfig(filename='/var/log/zstack/mini-fencer.log', level=logging.DEBUG, format='%(asctime)s %(levelname)s %(funcName)s %(message)s')
logger = logging.getLogger(__name__)

FENCER_TAG = "zs::ministorage::fencer"
MANAGEMENT_TAG = "zs::ministorage::management"


def retry(times=3, sleep_time=1):
    def wrap(f):
        @functools.wraps(f)
        def inner(*args, **kwargs):
            last_err = None
            for i in range(0, times):
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    logger.error(e)
                    time.sleep(sleep_time)
                logger.error("The task failed, please make sure the host can be connected and no error happened, then try again. "
                             "Below is detail:\n %s" % last_err)
        return inner
    return wrap


def getstatusoutput(c):
    start_time = time.time()
    r, o = commands.getstatusoutput(c)
    end_time = time.time()
    logger.debug("command:[%s], returnCode:[%s], output:[%s], spendTime:[%s] ms" % (c, r, o, (end_time - start_time) * 1000))
    return r, o


def getoutput(c):
    return getstatusoutput(c)[1]


@retry()
def run(c):
    r, o = getstatusoutput(c)
    if r != 0:
        raise Exception("run command[%s] failed[return code: %s, output: %s]" % (c, r, o))


def test_fencer(vg_name):
    # type: (str) -> bool
    r, fencer_ip = getstatusoutput("vgs %s -otags --nolocking --noheading | tr ',' '\n' | grep %s" % (vg_name, FENCER_TAG))
    if r == 0 and fencer_ip and fencer_ip != "" and is_ip_address(fencer_ip):
        fencer_ip = fencer_ip.strip().split("::")[-1]
        return test_ip_address(fencer_ip)

    has_zsha2, o = getstatusoutput("zsha2 show-config")
    if has_zsha2 == 0:
        r, fencer_ip = getstatusoutput("zsha2 show-config | grep -w 'gw' | awk '{print $NF}'").strip().strip("\",")
        if r == 0 and is_ip_address(fencer_ip):
            return test_ip_address(fencer_ip)

    r, default_gateway = getstatusoutput("ip r get 8.8.8.8 | head -n1 | grep -o 'via.*dev' | awk '{print $2}'")
    if r == 0 and default_gateway and default_gateway != "" and is_ip_address(default_gateway):
        return test_ip_address(default_gateway)

    mgmt_ip = getoutput("vgs %s -otags --nolocking --noheading | tr ',' '\n' | grep %s" % (vg_name, MANAGEMENT_TAG))
    mgmt_ip = mgmt_ip.strip().split("::")[-1]
    mgmt_device = getoutput("ip a | grep %s | awk '{print $NF}'" % mgmt_ip)
    return test_device(mgmt_device, 12) is not False


def test_device(device, ttl=12):
    # type: (str) -> bool or None
    if ttl == 1:
        return None
    is_bridge, o = getstatusoutput("brctl show %s" % device)
    if is_bridge:
        _, o = getstatusoutput("brctl show %s | awk '{print $NF}' | grep -vw interfaces" % device)
        for i in o.splitlines():
            r = test_device(i, ttl-1)
            if r:
                return r

    if "." in device:
        return test_device(device.split(".", ttl-1)[0])

    is_bonding, o = getstatusoutput("cat /sys/class/net/%s/bonding/mii_status" % device)
    if is_bonding:
        return "up" in o

    physical_nics = getoutput("find /sys/class/net -type l -not -lname '*virtual*' -printf '%f\n'").splitlines()
    if True in [p.strip() == device for p in physical_nics]:
        return getoutput("/sys/class/net/%s/carrier" % device) == 1

    return None


def is_ip_address(ip):
    if re.match(r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$", ip):
        return True
    return False


def test_ip_address(ip):
    # type: (str) -> bool
    device = getoutput("ip r get %s | grep -Eo 'dev.*src' | awk '{print $2}'" % ip)
    for i in range(5):
        r, o = getstatusoutput("timeout 2 arping -b -c 1 -w 1 -I %s %s" % (device, ip))
        if r == 0:
            return True
    return False


def fence_self(resource_name, drbd_path):
    qemu_pid = getoutput("lsof -c qemu-kvm | grep -w %s | awk '{print $2}'" % drbd_path)
    run("kill -9 %s" % qemu_pid)
    run("drbdadm resume-io %s" % resource_name)
    run("drbdadm secondary %s" % resource_name)
    # run("drbdadm outdate %s" % resource_name)


def main():
    resource_name = sys.argv[1]
    resource_path = getoutput(
        "grep -E 'disk.*/dev/' /etc/drbd.d/%s.res -m1 | awk '{print $2}' | tr -d ';'" % resource_name)
    vg_name = resource_path.split("/")[2]
    drbd_path = "/dev/drbd%s" % getoutput("cat /etc/drbd.d/%s.res | grep minor -m1 | awk '{print $NF}'" % resource_name).strip(";\n")
    try:
        if test_fencer(vg_name) is False:
            fence_self(resource_name, drbd_path)
        else:
            exit(4)
    except Exception as e:
        logger.error(e)
        exit(4)


if __name__ == '__main__':
    main()
