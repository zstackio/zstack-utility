from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import lvm
from zstacklib.utils import thread
from zstacklib.utils import drbd
from zstacklib.utils import qemu_img
from zstacklib.utils.bash import *
import os.path
import time
import traceback
import threading
import commands

logger = log.get_logger(__name__)

class AgentRsp(object):
    def __init__(self):
        self.success = True
        self.error = None

class ReportHostMaintainCmd(object):
    def __init__(self):
        self.hostUuid = None

class FaultToleranceFecnerPlugin(kvmagent.KvmAgent):
    SETUP_SELF_FENCER_PATH = "/ft/selffencer/setup"

    def __init__(self):
        # {host_uuid: created_time} e.g. {'07ee15b2f68648abb489f43182bd59d7': 1544513500.163033}
        self.run_fencer_timestamp = {}  # type: dict[str, float]
        self.fencer_fire_timestamp = {}  # type: dict[str, float]
        self.fencer_lock = threading.RLock()

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.SETUP_SELF_FENCER_PATH, self.setup_ft_self_fencer)

        def start_raid_heartbeat():
            pid = linux.find_process_by_cmdline(['zs-raid-heartbeat'])
            if pid:
                return
            
            shell.call('/var/lib/zstack/kvm/zs-raid-heartbeat')

        start_raid_heartbeat()

    @kvmagent.replyerror
    def setup_ft_self_fencer(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        peer_host_management_network_ip = cmd.peerHostManagementNetworkIp
        current_host_management_network_ip = cmd.hostManagementIp
        peer_host_storage_network_ip = cmd.peerHostStorageNetworkIp
        host_uuid = cmd.hostUuid

        def getstatusoutput(c):
            # type: (str) -> (int, str)
            start_time = time.time()
            r, o = commands.getstatusoutput(c)
            end_time = time.time()
            logger.debug("command:[%s], returnCode:[%s], output:[%s], spendTime:[%s] ms" % (c, r, o, (end_time - start_time) * 1000))
            return r, o

        def getoutput(c):
            return getstatusoutput(c)[1]

        @thread.AsyncThread
        def host_disk_raid_state_fencer(host_uuid, created_time):
            while self.run_fencer(host_uuid, created_time):
                do_host_disk_raid_state_fencer()
                time.sleep(5)

        @in_bash
        def do_host_disk_raid_state_fencer():
            disk_info = bash_o(
                "/opt/MegaRAID/MegaCli/MegaCli64 -PDList -aAll | grep -E 'Slot Number|DiskGroup|Firmware state|Drive Temperature'").strip().splitlines()
            
            group_health_dict = {}
            disk_group = "unknown"
            for info in disk_info:
                if "Slot Number" in info or "Drive Temperature" in info:
                    continue
                elif "DiskGroup" in info:
                    kvs = info.replace("Drive's position: ", "").split(",")
                    disk_group = filter(lambda x: "DiskGroup" in x, kvs)[0]
                    disk_group = disk_group.split(" ")[-1]
                else:
                    disk_group = "unknown" if disk_group is None else disk_group
                    state = info.strip().split(":")[-1].lower()
                    if "jobd" in state or "rebuild" in state or disk_group == "unknown":
                        continue
                    elif "online" in state:
                        health_count = group_health_dict.get(disk_group)
                        if health_count is None:
                            group_health_dict[disk_group] = 1
                        else:
                            health_count += 1
                            group_health_dict[disk_group] = health_count
                    else:
                        continue

            logger.debug("health disk info: %s" % group_health_dict)
            if group_health_dict.get("0") is None:
                linux.write_file('/proc/sys/kernel/sysrq', '1')
                linux.write_file('/proc/sysrq-trigger', 'o')
            else:
                # if all disks in raid5(for volume creation) is removed, 
                # no disk group will be found so maintain current host
                if group_health_dict.get("1") is None:
                    report_to_mn_for_host_maintenance()
                    return

                for key, value in group_health_dict.iteritems():
                    if key == "1" and value <= 2:
                        report_to_mn_for_host_maintenance()

        def report_to_mn_for_host_maintenance():
            url = self.config.get(kvmagent.SEND_COMMAND_URL)
            if not url:
                logger.warn('cannot find SEND_COMMAND_URL, unable to report self fencer triggered on [psList:%s]' % ps_uuids)
                return

            host_uuid = self.config.get(kvmagent.HOST_UUID)
            if not host_uuid:
                logger.warn(
                    'cannot find HOST_UUID, unable to report self fencer triggered on [psList:%s]' % ps_uuids)
                return

            cmd = ReportHostMaintainCmd()
            cmd.hostUuid = host_uuid

            logger.debug(
                'host[uuid:%s] triggered self fencer, report it to %s' % (
                    host_uuid, url))
            http.json_dump_post(url, cmd, {'commandpath': '/kvm/requestmaintainhost'})

        @in_bash
        def stop_management_node():
            r, o, e = bash_roe("/usr/local/bin/zsha2 stop-node -stopvip || zstack-ctl stop")
            r1, o1 = bash_ro("pgrep -af -- '-DappName=zstack start'")
            if r1 == 0:
                raise Exception(
                    "stop zstack failed, return code: %s, stdout: %s, stderr: %s, pgrep zstack return code: %s, stdout: %s" %
                    (r, o, e, r1, o1))
            
            return True

        @in_bash
        def recover_management_node():
            r, o, e = bash_roe("/usr/local/bin/zsha2 start-node")
        
        @in_bash
        def kill_fault_tolerance_vms():
            # kill all vm
            zstack_uuid_pattern = "'[0-9a-f]{8}[0-9a-f]{4}[1-5][0-9a-f]{3}[89ab][0-9a-f]{3}[0-9a-f]{12}'"

            virsh_list = shell.call("virsh list --all")
            logger.debug("virsh_list:\n" + virsh_list)

            vm_in_process_uuid_list = shell.call("virsh list | egrep -o " + zstack_uuid_pattern + " | sort | uniq")
            logger.debug('vm_in_process_uuid_list:\n' + vm_in_process_uuid_list)

            # kill vm's qemu process
            vm_pids_dict = {}
            for vm_uuid in vm_in_process_uuid_list.split('\n'):
                vm_uuid = vm_uuid.strip(' \t\n\r')
                if not vm_uuid:
                    continue

                r, o, e = bash_roe("""virsh qemu-monitor-command %s '{"execute":"query-colo-status"}' --pretty""" % vm_uuid)
                colo_status = json.loads(o).get('return')
                if colo_status is None:
                    # no colo status means not a colo vm, no need to kill it
                    continue
                
                mode = colo_status['mode']
                if mode == 'none':
                    # colo is not take effects no need to kill it
                    continue

                vm_pid = shell.call("ps aux | grep colo\/qemu-system | grep -v grep | awk '/%s/{print $2}'" % vm_uuid)
                vm_pid = vm_pid.strip(' \t\n\r')
                vm_pids_dict[vm_uuid] = vm_pid
            
            for vm_uuid, vm_pid in vm_pids_dict.items():
                kill = shell.ShellCmd('kill -9 %s' % vm_pid)
                kill(False)
                if kill.return_code == 0:
                    logger.warn('kill the vm[uuid:%s, pid:%s]' % (vm_uuid, vm_pid))
                else:
                    logger.warn('failed to kill the vm[uuid:%s, pid:%s] %s' % (vm_uuid, vm_pid, kill.stderr))

        @in_bash
        def secondary_drbd_if_peer_is_primary():
            drbd_resources = shell.call("find /etc/drbd.d/*.res | awk -F '.res' '{print $1}' | cut -d/ -f 4")
            for dbrd_res_uuid in drbd_resources.split("\n"):
                try:
                    drbdResource = drbd.DrbdResource(dbrd_res_uuid)
                    # if management network down and both side of drbd is primary, demote current node's drbd
                    if drbdResource.get_remote_role() == drbd.DrbdRole.Primary and drbdResource.get_role() == drbd.DrbdRole.Primary:
                        drbdResource.demote()
                except Exception as e:
                    logger.debug("failed to check drbd status of resource[uuid:%s], because %s", dbrd_res_uuid, e)


        @thread.AsyncThread
        @in_bash
        def ft_vm_management_network_fencer(peer_host_management_network_ip, current_host_management_network_ip, peer_host_storage_network_ip, host_uuid, created_time):
            mn_fenced = False
            while self.run_fencer(host_uuid, created_time):
                if do_test_network(peer_host_management_network_ip):
                    logger.debug("test connection to %s success" % peer_host_management_network_ip)
                    time.sleep(5)

                    if mn_fenced:
                        recover_management_node()
                        mn_fenced = False

                    continue
                
                # # management network ip lost, test if storage network available
                # storage_network_availability = do_test_network(peer_host_storage_network_ip)

                # test management network
                mgmt_device = getoutput("ip a | grep %s | awk '{print $NF}'" % current_host_management_network_ip).strip()
                management_network_available = False if len(mgmt_device) == 0 else test_device(mgmt_device, 5) is not None
                if management_network_available:
                    time.sleep(5)
                    if mn_fenced:
                        recover_management_node()
                        mn_fenced = False
                    continue    
                
                logger.debug("network down, need to kill ft vm")
                kill_fault_tolerance_vms()
                mn_fenced = stop_management_node()
                secondary_drbd_if_peer_is_primary()

        @in_bash
        def test_device(device, ttl=12):
            # type: (str, int) -> bool or None
            if ttl == 1:
                return None
            device = device.strip()
            is_bridge, o = getstatusoutput("brctl show %s" % device)
            if is_bridge == 0 and "can't get info" not in o.lower():
                return_code, stdout = getstatusoutput("ip -br -4 addr show %s" % device)
                # if device is not in up status
                if return_code == 0 and len(stdout.strip()) == 0:
                    return None

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

        def do_test_network(target_ip):
            total_times = 2
            success = 0
            for i in range(0, total_times):
                if shell.run("nmap --host-timeout 10s -sP -PI %s | grep -q 'Host is up'" % target_ip) == 0:
                    success += 1
                time.sleep(1)

            logger.debug("total :%s, success: %s" % (total_times, success))
            if success == total_times:
                return True
            else:
                return False
        
        created_time = time.time()
        self.setup_fencer(host_uuid, created_time)
        ft_vm_management_network_fencer(peer_host_management_network_ip, current_host_management_network_ip, peer_host_storage_network_ip, host_uuid, created_time)
        host_disk_raid_state_fencer(host_uuid, created_time)
        return jsonobject.dumps(AgentRsp())

    def run_fencer(self, host_uuid, created_time):
        with self.fencer_lock:
            if not self.run_fencer_timestamp[host_uuid] or self.run_fencer_timestamp[host_uuid] > created_time:
                return False

            self.run_fencer_timestamp[host_uuid] = created_time
            return True

    def setup_fencer(self, host_uuid, created_time):
        with self.fencer_lock:
            self.run_fencer_timestamp[host_uuid] = created_time

    def cancel_fencer(self, host_uuid):
        with self.fencer_lock:
            self.run_fencer_timestamp.pop(host_uuid, None)

    def stop(self):
        pass

    def configure(self, config):
        self.config = config
