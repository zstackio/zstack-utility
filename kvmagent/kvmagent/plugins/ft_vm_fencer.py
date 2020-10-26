from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import lvm
from zstacklib.utils import thread
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
            raid_info = bash_o("/opt/MegaRAID/MegaCli/MegaCli64 -LDInfo -LALL -aAll | grep -E 'Target Id|State'").strip().splitlines()
            target_id = state = "unknown"
            for info in raid_info:
                if "Target Id" in info:
                    continue
                else:
                    state = info.strip().split(" ")[-1].lower()
                    if state == "optimal":
                        continue
                    
                    # raid is degraded
                    logger.debug("raid is degraded, kill ft vms if needed")
                    kill_fault_tolerance_vms()
                    return

            disk_info = bash_o(
                "/opt/MegaRAID/MegaCli/MegaCli64 -PDList -aAll | grep -E 'Slot Number|DiskGroup|Firmware state|Drive Temperature'").strip().splitlines()
            need_failover_count = 0
            for info in disk_info:
                if "Slot Number" in info or "DiskGroup" in info or "Drive Temperature" in info:
                    continue
                else:
                    state = info.strip().split(":")[-1].lower()
                    if "online" in state or "jobd" in state:
                        continue
                    else:
                        need_failover_count += 1
            
            logger.debug("failure disk number: %s" % need_failover_count)
            if need_failover_count >= 2:
                kill_fault_tolerance_vms()

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

        @thread.AsyncThread
        @in_bash
        def ft_vm_management_network_fencer(peer_host_management_network_ip, current_host_management_network_ip, peer_host_storage_network_ip, host_uuid, created_time):
            while self.run_fencer(host_uuid, created_time):
                if do_test_network(peer_host_management_network_ip):
                    logger.debug("test connection to %s success" % peer_host_management_network_ip)
                    time.sleep(5)
                    continue
                
                # # management network ip lost, test if storage network available
                # storage_network_availability = do_test_network(peer_host_storage_network_ip)

                # test management network
                mgmt_device = getoutput("ip a | grep %s | awk '{print $NF}'" % current_host_management_network_ip).strip()
                management_network_available = False if len(mgmt_device) == 0 else test_device(mgmt_device, 5) is not None
                if management_network_available:
                    time.sleep(5)
                    continue    
                
                logger.debug("network down, need to kill ft vm")
                kill_fault_tolerance_vms()

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