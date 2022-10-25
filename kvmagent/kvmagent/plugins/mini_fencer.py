#!/usr/bin/env python
import functools
import sys
import commands
import logging
import time
import re
import signal
import threading

from zstacklib.utils import iproute

FENCER_TAG = "zs::ministorage::fencer"
MANAGEMENT_TAG = "zs::ministorage::management"

MINI_FENCER_KEY = "/usr/local/zstack/mini_fencer.key"
PEER_USERNAME = ""
PEER_MGMT_ADDR = ""

FENCE_GW_RESULT = None
OUTDATE_PEER_RESULT = None
FENCE_GW_EXISTS = True

OVERALL_TIMEOUT = 50

logger = logging.getLogger(__name__)


def set_timeout(num, callback):
    def wrap(func):
        def handle(signum, frame):
            raise RuntimeError

        def to_do(*args, **kwargs):
            try:
                signal.signal(signal.SIGALRM, handle)
                signal.alarm(num)
                r = func(*args, **kwargs)
                signal.alarm(0)
                return r
            except RuntimeError as e:
                callback()

        return to_do

    return wrap


def retry(times=5, sleep_time=1):
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
            logger.error("The task failed,  detail:\n%s" % last_err)
        return inner
    return wrap


def getstatusoutput(c):
    # type: (str) -> (int, str)
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


def test_fencer(vg_name, resource_name):
    logger.debug("run test_fencer %s" % resource_name)
    global FENCE_GW_RESULT
    FENCE_GW_RESULT = do_test_fencer(vg_name)


def do_test_fencer(vg_name):
    # type: (str) -> bool
    global FENCE_GW_EXISTS
    r, fencer_ip = getstatusoutput("timeout 3 vgs %s -otags --nolocking -t --noheading | tr ',' '\\n' | grep %s" % (vg_name, FENCER_TAG))
    if r == 0 and fencer_ip and fencer_ip != "" and is_ip_address(fencer_ip):
        fencer_ip = fencer_ip.strip().split("::")[-1]
        FENCE_GW_EXISTS = True
        return test_ip_address(fencer_ip)

    has_zsha2, o = getstatusoutput("/usr/local/bin/zsha2 show-config")
    if has_zsha2 == 0:
        r, fencer_ip = getstatusoutput("/usr/local/bin/zsha2 show-config | grep -w 'gw' | awk '{print $NF}'")
        fencer_ip = fencer_ip.strip().strip("\",") if fencer_ip is not None else fencer_ip
        if r == 0 and is_ip_address(fencer_ip):
            FENCE_GW_EXISTS = True
            return test_ip_address(fencer_ip)

    r, default_gateway = getstatusoutput("ip r get 8.8.8.8 | head -n1 | grep -o 'via.*dev' | awk '{print $2}'")
    if r == 0 and default_gateway and default_gateway != "" and is_ip_address(default_gateway):
        FENCE_GW_EXISTS = True
        return test_ip_address(default_gateway)

    FENCE_GW_EXISTS = False
    mgmt_ip = getoutput("timeout 3 vgs %s -otags --nolocking -t --noheading | tr ',' '\\n' | grep %s" % (vg_name, MANAGEMENT_TAG))
    mgmt_ip = mgmt_ip.strip().split("::")[-1]
    if not is_ip_address(mgmt_ip):
        logger.error("can not get mgmt nic")
        return False
    mgmt_device = iproute.query_addresses_by_ip(mgmt_ip)[0].ifname
    return test_device(mgmt_device, 12) is None


def test_device(device, ttl=12):
    # type: (str, int) -> bool or None
    if ttl == 1:
        return None
    device = device.strip()
    is_bridge, o = getstatusoutput("brctl show %s" % device)
    if is_bridge == 0 and "can't get info" not in o.lower():
        _, o = getstatusoutput("brctl show %s | awk '{print $NF}' | grep -vw interfaces" % device)
        for i in o.splitlines():
            r = test_device(i.strip(), ttl-1)
            if r:
                return r

    if "." in device:
        return test_device(device.split(".", ttl-1)[0])

    is_bonding, o = getstatusoutput("cat /sys/class/net/%s/bonding/mii_status" % device)
    if is_bonding == 0:
        return "up" in o

    physical_nics = getoutput("find /sys/class/net -type l -not -lname '*virtual*' -printf '%f\\n'").splitlines()
    if True in [p.strip() == device for p in physical_nics]:
        return getoutput("/sys/class/net/%s/carrier" % device) == 1

    return None


def is_ip_address(ip):
    if re.match(r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$", ip):
        return True
    return False


def test_ip_address(ip):
    # type: (str) -> bool
    device = iproute.get_routes_by_ip(ip)[0].get_related_link_device().ifname
    for i in range(3):
        r, o = getstatusoutput("timeout 2 arping -b -c 1 -w 1 -I %s %s" % (device, ip))
        if r == 0:
            return True
    return False


def outdate_peer(resource_name):
    logger.debug("run outdate_peer %s" % resource_name)
    r, o = getstatusoutput("timeout 5 ssh -i %s %s@%s 'drbdadm outdate %s'" % (MINI_FENCER_KEY, PEER_USERNAME, PEER_MGMT_ADDR, resource_name))
    global OUTDATE_PEER_RESULT
    OUTDATE_PEER_RESULT = r == 0


def fence_self(resource_name, drbd_path):
    r, qemu_pid = getstatusoutput("timeout 3 lsof -c qemu-kvm | grep -w %s" % drbd_path)
    if r == 0:
        qemu_pid = qemu_pid.split()[1]
        run("timeout 3 kill -9 %s" % qemu_pid)
    run("timeout 3 drbdadm resume-io %s" % resource_name)
    run("timeout 3 drbdadm secondary %s" % resource_name)
    run("timeout 3 drbdadm outdate %s" % resource_name)


def timeout_callback():
    logger.error("overall timeout for %s seconds!" % OVERALL_TIMEOUT)
    if FENCE_GW_RESULT is False and OUTDATE_PEER_RESULT is False:
        logger.error("keep resource %s io suspend" % sys.argv[1])
        exit(0)
    else:
        logger.error("leave resource %s io resume" % sys.argv[1])
        exit(4)


# @set_timeout(OVERALL_TIMEOUT, timeout_callback)
def main():
    resource_name = sys.argv[1]
    logger.debug("fencer fired by resource %s" % resource_name)
    resource_path = getoutput(
        "grep -E 'disk.*/dev/' /etc/drbd.d/%s.res -m1 | awk '{print $2}' | tr -d ';'" % resource_name)
    vg_name = resource_path.split("/")[2]
    drbd_path = "/dev/drbd%s" % getoutput("cat /etc/drbd.d/%s.res | grep minor -m1 | awk '{print $NF}'" % resource_name).strip(";\n")
    try:
        t1 = threading.Thread(target=test_fencer, args=(vg_name, resource_name))
        t2 = threading.Thread(target=outdate_peer, args=(resource_name,))
        t1.start()
        t2.start()

        for i in range(32):
            if FENCE_GW_RESULT is None or OUTDATE_PEER_RESULT is None:
                time.sleep(0.5)
                continue
            elif FENCE_GW_EXISTS and FENCE_GW_RESULT is False and OUTDATE_PEER_RESULT is False:
                logger.info("resource %s fence result: fence self" % resource_name)
                fence_self(resource_name, drbd_path)
                exit(5)
            else:
                logger.info("resource %s fence result: not fence" % resource_name)
                exit(4)
        logger.error("timeout for 15 seconds! resume resource %s IO" % sys.argv[1])
        exit(4)
    except Exception as e:
        logger.error("resouce %s fence get error" % resource_name)
        logger.error(e.message)
        if FENCE_GW_RESULT is False and OUTDATE_PEER_RESULT is False:
            logger.error("keep resource %s io suspend" % resource_name)
            exit(5)
        else:
            logger.error("leave resource %s io resume" % resource_name)
            exit(4)


if __name__ == '__main__':
    logging.basicConfig(filename='/var/log/zstack/mini-fencer.log', level=logging.DEBUG,
                        format='%(asctime)s %(process)d %(levelname)s %(funcName)s %(message)s')
    main()
