import base64
import sys
import logging

sys.path.append("/var/lib/zstack/virtualenv/kvm/lib/python2.7/site-packages/")

from zstacklib.utils import bash
from zstacklib.utils import linux
from zstacklib.utils import lvm

logging.basicConfig(filename='/tmp/reset_mini_host.log', level=logging.DEBUG,
                        format='%(asctime)s %(process)d %(levelname)s %(funcName)s %(message)s')
logger = logging.getLogger(__name__)


@bash.in_bash
@linux.retry(times=3, sleep_time=1)
def stop_server():
    r, o, e = bash.bash_roe("zsha2 stop-node || zstack-ctl stop")
    r1, o1 = bash.bash_ro("pgrep -af -- '-DappName=zstack start'")
    if r1 == 0:
        raise Exception(
            "stop zstack failed, return code: %s, stdout: %s, stderr: %s, pgrep zstack return code: %s, stdout: %s" %
            (r, o, e, r1, o1))


@bash.in_bash
def stop_kvmagent():
    bash.bash_roe("/etc/init.d/zstack-kvmagent stop")
    bash.bash_roe("pkill -9 -f 'c from kvmagent import kdaemon'")


@bash.in_bash
def stop_vms():
    bash.bash_roe("pkill -f -9 '/usr/libexec/qemu-kvm -name guest'")


@bash.in_bash
def cleanup_storage():
    bash.bash_roe("drbdadm down all")
    bash.bash_r("/bin/rm /etc/drbd.d/*.res")
    lvm.wipe_fs(["/dev/sdb"])


@bash.in_bash
def cleanup_zstack():
    bash.bash_r("rm -rf /usr/local/zstack/apache-tomcat/logs/")
    bash.bash_r("rm -rf /var/log/zstack/")
    bash.bash_r("rm -rf /usr/local/zstack")
    bash.bash_r("bash /opt/zstack-dvd/x86_64/c76/zstack-installer.bin -D -I 127.0.0.1")
    bash.bash_r("bash /opt/zstack-dvd/x86_64/c76/zstack_mini_server.bin -a")
    bash.bash_r("systemctl disable zstack.service")


@bash.in_bash
def clear_network():
    all_links = [x.strip().strip(":") for x in bash.bash_o("ip -o link | awk '{print $2}'").strip().splitlines()]
    for i in all_links:
        if i not in ["lo", "eno1", "eno2", "ens2f0", "ens2f1"]:
            bash.bash_r("ip link del %s" % i.split("@")[0])


@bash.in_bash
def reset_network():
    bash.bash_r("ip link set dev eno1 nomaster; ip link set dev eno2 nomaster; ip link set dev ens2f0 nomaster; ip link set dev ens2f1 nomaster")
    bash.bash_r("ls /etc/sysconfig/network-scripts/ifcfg-* | grep -v ifcfg-lo | xargs /bin/rm")
    bash.bash_r("systemctl restart network")
    clear_network()
    bash.bash_r("ip r del default")
    sn = bash.bash_o("dmidecode -s system-serial-number").strip()
    if sn[-1] == "B":
        bash.bash_r(
            "export PATH=$PATH:/usr/local/bin/; /usr/local/bin/zs-network-setting -b eno1 100.66.66.67 255.255.255.0")
        bash.bash_r("ip link set dev eno1 master br_eno1")
        bash.bash_r("ip link set dev eno1 up")
    elif sn[-1] == "A":
        bash.bash_r(
            "export PATH=$PATH:/usr/local/bin/; /usr/local/bin/zs-network-setting -b eno1 100.66.66.66 255.255.255.0")
        bash.bash_r("ip link set dev eno1 master br_eno1")
        bash.bash_r("ip link set dev eno1 up")
    else:
        raise Exception("serial number not last with A or B!")
    # bash.bash_r("sed -i 's/ui_mode = .*/ui_mode = mini/g' /usr/local/zstack/apache-tomcat/webapps/zstack/WEB-INF/classes/zstack.properties")
    bash.bash_r("systemctl restart zstack-network-agent.service")


@bash.in_bash
def reset_system():
    reset_network()
    p = "enN0YWNrLm9yZ0A2MzdF"
    bash.bash_r("echo 'root:%s' | chpasswd" % base64.decodestring(p))


def main(args):
    stop_server()
    stop_kvmagent()
    stop_vms()
    cleanup_storage()
    cleanup_zstack()
    reset_system()


if __name__ == "__main__":
    main(sys.argv[1:])
