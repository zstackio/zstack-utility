import os
import time
import yaml

from zstacklib.utils import shell
from zstacklib.utils import log
from zstacklib.utils import lock

logger = log.get_logger(__name__)


class OvsError(Exception):
    '''ovs error'''


def write_sysfs(path, value, supressRaise=False):
    try:
        with open(path, 'w') as f:
            f.write(value)
    except Exception as e:
        logger.warn(str(e))
        if not supressRaise:
            raise OvsError(str(e))


def read_sysfs(path, supressRaise=False):
    ret = None
    try:
        with open(path, 'r') as f:
            ret = f.read().rstrip()
    except Exception as e:
        logger.warn(str(e))
        if not supressRaise:
            raise OvsError(str(e))

    return ret


def confirm_write_sysfs(path, value, times=3, sleep_time=3):
    for _ in range(0, times):
        write_sysfs(path, value, True)
        time.sleep(sleep_time)
        if read_sysfs(path, True) == value:
            return

    raise OvsError("write sysfs timeout")


def check_mlnx_ofed():
    # maybe we should check ofed version
    if shell.run("ofed_info -n") != 0:
        return False
    if not os.path.exists("/usr/share/openvswitch/scripts/ovs-ctl"):
        return False
    return True


def get_bridges():
    s = shell.ShellCmd("ovs-vsctl --timeout=5 list-br", None, False)
    s(False)
    if s.return_code != 0:
        raise OvsError("ovs error: {}".format(s.stderr))

    return s.stdout.strip().split('\n')


def get_bridge_ports(bridgeName):
    s = shell.ShellCmd(
        "ovs-vsctl --timeout=5 list-ports {}".format(bridgeName), None, False)
    s(False)
    if s.return_code != 0:
        raise OvsError("ovs error: {}".format(s.stderr))

    return s.stdout.strip().split('\n')


def get_bonds_interfaces(bondList):
    slaves_p = "/sys/class/net/{}/bonding/slaves"
    interface_list = []
    for b in bondList:
        tmp = slaves_p.format(b)
        tmp_list = read_sysfs(tmp).split()
        interface_list.extend(tmp_list)
    return interface_list


def get_interface_pcinum(interface):
    pci = None
    try:
        pci_path = '/sys/class/net/{}/device'
        pci = os.path.realpath(pci_path.format(interface)).split("/")[-1]
    except Exception as e:
        logger.warn(str(e))
    finally:
        return pci


def get_used_pci(vDPA_list):
    pci_used_list = []

    if vDPA_list == None:
        return pci_used_list

    for i in vDPA_list:
        s = shell.ShellCmd(
            "ovs-vsctl get Interface {} options:vdpa-accelerator-devargs".format(i), None, False)
        s(False)
        if s.return_code != 0:
            raise OvsError("ovs error: {}".format(s.stderr))

        pci_used_list.append(s.stdout.strip().strip('"'))

    return pci_used_list


def get_vfs_dict(interfaceName):
    """
    vfs_dict{'vf_representor', 'vf_pci'}
    """

    device_p = "/sys/class/net/{}/device/"
    vfs_dict = {}
    tmp_list = os.listdir(device_p.format(interfaceName))
    for vf in tmp_list:
        if vf.startswith("virtfn"):
            pci = os.path.realpath(device_p.format(
                interfaceName) + vf).split("/")[-1]
            vfs_dict[vf] = pci

    return vfs_dict


def get_free_pci(if_list, used_pci):

    # TODO: low performance
    def __calculate_free_pci(pci_dict, used_pci):
        count = 0
        for i in pci_dict:
            if pci_dict[i] not in used_pci:
                count += 1
        return count

    free_list_count = 0
    choosen_pci_dict = {}
    choosen_if = None
    for i in if_list:
        pci_dict = get_vfs_dict(i)
        tmp = __calculate_free_pci(pci_dict, used_pci)
        if tmp > free_list_count:
            free_list_count = tmp
            choosen_pci_dict = pci_dict
            choosen_if = i

    if free_list_count == 0:
        return None, None, None

    for i in choosen_pci_dict:
        if choosen_pci_dict[i] not in used_pci:
            return choosen_if, i, choosen_pci_dict[i]
    return None, None, None


def get_interface_offloadstatus(interface):
    smartnic_info_path = "/usr/local/etc/zstack/smart-nics.yaml"

    offload_status = {}

    with open(smartnic_info_path, 'r') as f:
        data = yaml.safe_load(f)

    for i in data:
        offload_status[i['nic']['vendor_device']] = "|".join(
            str(x) for x in i['nic']['offloadstatus'])

    vendor_device = get_interface_vendor_device(interface)

    if vendor_device in offload_status.keys():
        return offload_status[vendor_device]

    return None


def get_interface_vendor_device(interfaceName):
    vendor_path = '/sys/class/net/{}/device/vendor'.format(interfaceName)
    device_path = '/sys/class/net/{}/device/device'.format(interfaceName)

    vendor_id = read_sysfs(vendor_path)[2:6]
    device_id = read_sysfs(device_path)[2:6]

    return vendor_id + device_id


def set_interface_devlink_mode(interfaceName):
    devlink_mode = '/sys/class/net/{}/compat/devlink/mode'.format(
        interfaceName)
    totalvfs = '/sys/class/net/{}/device/sriov_totalvfs'.format(interfaceName)
    numvfs = '/sys/class/net/{}/device/sriov_numvfs'.format(interfaceName)
    driver_path = '/sys/class/net/{}/device/driver'.format(interfaceName)
    unbind_path = '/sys/class/net/{}/device/driver/unbind'.format(
        interfaceName)

    if read_sysfs(devlink_mode, True) == "switchdev":
        return

    # split vfs
    write_sysfs(numvfs, "0")

    default_list = os.listdir(driver_path)

    vfs_num = read_sysfs(totalvfs)
    write_sysfs(numvfs, vfs_num)

    current_list = os.listdir(driver_path)

    pci_list = list(set(current_list).difference(set(default_list)))

    for pci in pci_list:
        write_sysfs(unbind_path, pci)

    # wait unbind finished, It may take some time to unbind VFS
    for i in range(0, 5):
        if i == 5:
            raise OvsError()
        if len(os.listdir(driver_path)) != len(default_list):
            time.sleep(10)

    confirm_write_sysfs(devlink_mode, 'switchdev', 10, 5)


def set_vflag(bondName):

    slaves_p = "/sys/class/net/{}/bonding/slaves"

    if not os.path.exists(slaves_p.format(bondName)):
        return False

    interfaces = get_bonds_interfaces([bondName])
    if_pci_bdf = set()
    if_vendor = set()

    for i in interfaces:
        if_pci_bdf.add(get_interface_pcinum(i).split(".")[0])
        if_vendor.add(get_interface_vendor_device(i))

    # the pfs under vflag should come from the same nic.
    if len(if_vendor) != 1 or len(if_pci_bdf) != 1:
        return False

    # check vendor_device number
    if get_interface_offloadstatus(interfaces[0]) == None:
        return False

    for i in interfaces:
        # set devlink mode to switchdev
        set_interface_devlink_mode(i)

    return True


def set_dpdk_white_list(interfaceNames):
    dpdk_extra = ""

    s = shell.ShellCmd(
        "ovs-vsctl get Open_vSwitch . other_config:dpdk-extra", None, False)
    s(False)
    if s.return_code == 0:
        dpdk_extra = s.stdout.strip().strip('\n').strip('"')

    for i in interfaceNames:
        pci = get_interface_pcinum(i)
        if pci in dpdk_extra:
            continue
        else:
            if get_ofed_version() >= 5.2:
                dpdk_extra = dpdk_extra + "-a {},representor=[0-127],dv_flow_en=1,dv_esw_en=1,dv_xmeta_en=1 ".format(
                    pci)
            else:
                dpdk_extra = dpdk_extra + "-w {},representor=[0-127],dv_flow_en=1,dv_esw_en=1,dv_xmeta_en=1 ".format(
                    pci)

    ret = shell.run(
        'ovs-vsctl --timeout=5 --no-wait set Open_vSwitch . other_config:dpdk-extra="{}"'.format(dpdk_extra))

    if ret is not 0:
        logger.info(
            "set dpdk wihite list for {} failed".format(interfaceNames))
        return False
    return True


def generate_all_vDPA(bridgeName, bondName):

    # default vdpa source path
    vDPA_path = "/var/run/zstack-vdpa"

    interface_list = get_bridge_ports(bridgeName)

    if bondName not in interface_list:
        raise OvsError("bridge:{} don't have such bond:{}".format(
            bridgeName, bondName))

    try:
        if not os.path.exists(vDPA_path):
            os.mkdir(vDPA_path, 0755)
        sub_path = vDPA_path + '/' + bridgeName
        if not os.path.exists(sub_path):
            os.mkdir(sub_path, 0755)
        # we only need to provide a vDPA file path here,
        # and QEMU will create the actually file
    except Exception as e:
        logger.warn(str(e))

    if_list = get_bonds_interfaces([bondName])

    for i in if_list:
        vfs_dict = get_vfs_dict(i)

        for vf in vfs_dict:
            vDPA = sub_path + '/' + i + vf
            shell.run(
                'ovs-vsctl --timeout=5 add-port {} {} -- set Interface {} type=dpdkvdpa options:vdpa-socket-path={} options:vdpa-accelerator-devargs={} options:dpdk-devargs={},representor=[{}] options:vdpa-max-queues=8'.format(
                    bridgeName, i+vf, i+vf, vDPA, vfs_dict[vf], get_interface_pcinum(i), vf[6:]))


@lock.lock("get_vDPA")
def get_vDPA(vmUuid, nic):
    bridgeName = nic.bridgeName
    bondName = nic.physicalInterface
    vlanId = nic.vlanId
    nicInternalName = nic.nicInternalName

    interface_list = get_bridge_ports(bridgeName)

    if bondName not in interface_list:
        raise OvsError("bridge:{} don't have such bond:{}".format(
            bridgeName, bondName))

    # already exsit
    current_vDPA = shell.call(
        "ovs-vsctl --columns=name find interface external_ids:vm-id={} external_ids:iface-id={} | grep virtfn |cut -d ':' -f2".format(vmUuid, nicInternalName)).strip()
    if current_vDPA != '':
        vDPA_path = shell.call(
            "ovs-vsctl get interface {} options:vdpa-socket-path".format(current_vDPA)).strip().strip('"')
        return vDPA_path

    unused_vDPA_list = shell.call(
        "ovs-vsctl --columns=name find interface external_ids={} | grep virtfn |cut -d ':' -f2").split()

    if len(unused_vDPA_list) == 0:
        raise OvsError("vDPA resource exhausted")

    chosed_vDPA = unused_vDPA_list[0].strip()

    vDPA_path = shell.call(
        "ovs-vsctl get interface {} options:vdpa-socket-path".format(chosed_vDPA)).strip().strip('"')

    # set vmUuid
    shell.call("ovs-vsctl --timeout=2 set interface {} external_ids:vm-id={} external_ids:iface-id={}".format(
        chosed_vDPA, vmUuid, nicInternalName))

    if vlanId is not None:
        shell.run(
            'ovs-vsctl --timeout=5 set Port {} tag={}'.format(chosed_vDPA, vlanId))

    return vDPA_path


def free_vDPA(vmUuid, nicInternalName=None):

    vDPA_list = []

    if nicInternalName != None:
        vDPA_list = shell.call(
            "ovs-vsctl --columns=name find interface external_ids:vm-id={} external_ids:iface-id={} | grep virtfn |cut -d ':' -f2".format(vmUuid, nicInternalName)).strip().split()
    else:
        vDPA_list = shell.call(
            "ovs-vsctl --columns=name find interface external_ids:vm-id={} | grep virtfn |cut -d ':' -f2".format(vmUuid)).strip().split()

    for vDPA in vDPA_list:
        shell.run("ovs-vsctl remove interface {} external_ids vm-id".format(vDPA))
        shell.run(
            "ovs-vsctl remove interface {} external_ids iface-id".format(vDPA))
        shell.run("ovs-vsctl --timeout=5 remove Port {} tag".format(vDPA))

    vDPA_path = ''
    if nicInternalName != None and len(vDPA_list) != 0:
        vDPA_path = shell.call(
            "ovs-vsctl get interface {} options:vdpa-socket-path".format(vDPA_list[0])).strip().strip('"')
    return vDPA_path

def get_ofed_version():
    ofed_version = shell.call("ofed_info -n")

    return float(ofed_version.split('-')[0])


def check_ovs_status():

    for _ in range(0, 5):
        if shell.run("/usr/share/openvswitch/scripts/ovs-ctl status") == 0:
            return
        else:
            start_ovs()
            time.sleep(3)

    raise OvsError("cannot start ovs.")


def start_ovs():
    shell.run("/usr/share/openvswitch/scripts/ovs-ctl start")


def stop_ovs():
    shell.run("/usr/share/openvswitch/scripts/ovs-ctl stop")


def restart_ovs():
    shell.run("/usr/share/openvswitch/scripts/ovs-ctl restart")


def clear_ovsdb():
    devlink_mode = '/sys/class/net/{}/compat/devlink/mode'
    shell.run("systemctl restart ovsdb-server.service")

    br_list = get_bridges()

    for b in br_list:
        if b == '':
            continue
        interfaces = get_bonds_interfaces([b[3:]])
        for i in interfaces:
            if read_sysfs(devlink_mode.format(i), True) != "switchdev":
                shell.run("ovs-vsctl del-br {}".format(b))
                break

    #shell.run("systemctl restart openibd.service")

    shell.run("systemctl stop ovsdb-server.service")
