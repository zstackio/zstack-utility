import os
import re

from oslo_concurrency import processutils
from oslo_log import log as logging

from bm_instance_agent import exception
from bm_instance_agent.systems import base
from bm_instance_agent.common import utils as bm_utils

LOG = logging.getLogger(__name__)
multipath_conf_path = '/etc/multipath.conf'
multi_path_daemon_cofig = """
defaults {
        find_multipaths "yes"
        user_friendly_names "yes"
}
multipaths {

}
devices {
        device {
                vendor "ZStack"
                product "R_ZEBS"
                path_grouping_policy multibus
                path_checker tur
                path_selector "round-robin 0"
                hardware_handler "0"
                fast_io_fail_tmo 0
                failback immediate
                rr_weight priorities
                no_path_retry fail
        }
}
"""


def _check_initiator_config(instance_uuid):
    cmd = ["systemctl", "status", "iscsid"]
    _, stderr = processutils.trycmd(*cmd)
    if stderr:
        LOG.info("get iscsid status failed, try to restart iscsid service")
        cmd = 'systemctl restart iscsid'
        processutils.execute(cmd, shell=True)

    conf_path = '/etc/iscsi/initiatorname.iscsi'
    initiator = ('InitiatorName=iqn.2015-01.io.zstack:initiator.'
                 'instance.{uuid}').format(uuid=instance_uuid)

    update_conf = False
    if os.path.exists(conf_path):
        with open(conf_path, 'r') as f:
            if f.read().strip() != initiator:
                update_conf = True
    else:
        update_conf = True

    if update_conf:
        with open(conf_path, 'w') as f:
            f.write(initiator)
        LOG.info("initiator config changed, reload and restart iscsid")
        cmd = 'systemctl daemon-reload && systemctl restart iscsid'
        processutils.execute(cmd, shell=True)


def add_multipath_config(wwid, alias):
    config = """
multipath {{
    wwid {}
    alias {}
}}
""".format(wwid, alias)

    with open(multipath_conf_path, 'r+') as f:
        lines = f.readlines()

        update_buffer = []
        found_multi_paths = False

        for line in lines:
            if "wwid {}".format(wwid) in line:
                return False

        for line in lines:
            update_buffer.append(line)
            if not found_multi_paths and line.strip() == "multipaths {":
                update_buffer.append(config)
                found_multi_paths = True

        if not found_multi_paths:
            update_buffer.append("multipaths {\n")
            update_buffer.append(config)
            update_buffer.append("}\n")

        f.seek(0)
        f.writelines(update_buffer)
        f.flush()
        return True

def _start_multi_path_config(volume_wwid, alias):
    if not os.path.exists(multipath_conf_path):
        with open(multipath_conf_path, 'w') as f:
            f.write(multi_path_daemon_cofig)
            f.flush()
        LOG.info("multipath config not exists, create multipath conf to %s" % multipath_conf_path)

    is_update = add_multipath_config(volume_wwid, alias)

    if not is_update:
        return

    LOG.info("multipath config changed, try to restart multipathd service")
    cmd = 'systemctl restart multipathd'
    processutils.execute(cmd, shell=True)

    # Force refresh of multipath devices
    cmd = 'multipath -F'
    processutils.execute(cmd, shell=True)

    # Display detailed debug information for multipath devices
    cmd = 'multipath -v3'
    processutils.execute(cmd, shell=True)

class LinuxDriver(base.SystemDriverBase):

    driver_name = 'linux'

    def __init__(self):
        super(LinuxDriver, self).__init__()

    def ping(self, instance_obj):
        pass

    def reboot(self, instance_obj):
        cmd = ['shutdown', '-r', 'now']
        try:
            processutils.execute(*cmd)
        except Exception as e:
            if 'shutdown -r now' not in e:
                raise e

    def stop(self, instance_obj):
        cmd = ['shutdown', '-h', 'now']
        try:
            processutils.execute(*cmd)
        except Exception as e:
            if 'shutdown -h now' not in e:
                raise e

    def discovery_target(self, instance_obj):
        _check_initiator_config(instance_obj.uuid)
        target_name = ('iqn.2015-01.io.zstack:target'
                       '.instance.{uuid}').format(uuid=instance_obj.uuid)

        if instance_obj.custom_iqn:
            target_name = instance_obj.custom_iqn

        cmd = 'iscsiadm -m session | grep %s' % target_name
        LOG.info(cmd)
        stdout, stderr = processutils.trycmd(cmd, shell=True)
        if not stderr:
            LOG.info("iscsi target:%s has logged" % target_name)
            return

        discovery_cmd = 'iscsiadm -m discovery -t sendtargets -p {address}:{port}'.format(
                                    address=instance_obj.gateway_ip,
                                    port=3260,
                                    target_name=target_name)
        LOG.info(discovery_cmd)
        try:
            stdout, stderr = processutils.execute(discovery_cmd, shell=True)
            if target_name in stdout:
                LOG.info("login iscsi target: %s" % target_name)
                target_login_cmd = ('iscsiadm --mode node --targetname {target_name} '
                                    '-p {address}:{port} --login').format(
                    target_name=target_name,
                    address=instance_obj.gateway_ip,
                    port=3260)
                LOG.info(target_login_cmd)
                processutils.execute(target_login_cmd, shell=True)
            else:
                LOG.info("discovered targets not contains %s, skip login" % target_name)
        except processutils.ProcessExecutionError:
            LOG.info("no iscsi target found, skip login")
            return

    def discovery_volume_target(self, instance_obj, volume_obj, volume_access_path_gateway_ips):
        if not volume_obj.iscsi_path:
            return
        target_name = volume_obj.iscsi_path.replace('iscsi://', '').split("/")[1]
        self.discovery_target_through_access_path_gateway_ips(target_name, volume_access_path_gateway_ips)

        device_scsi_id = self.get_volume_scsi_id(target_name, volume_access_path_gateway_ips[0])
        if device_scsi_id:
            _start_multi_path_config(device_scsi_id, volume_obj.name)

    def get_volume_scsi_id(self, iqn, target_ip):
        cmd = 'iscsiadm -m session | grep %s | grep %s' % (iqn, target_ip)
        stdout, stderr = processutils.trycmd(cmd, shell=True)

        for line in stdout.split('\n'):
            if iqn in line:
                match = re.search(r'\[(\d+)\]', line)
                if match:
                    sid = match.group(1)
                    LOG.info("The sid logged in with iqn %s and ip %s is %s" % (iqn, target_ip, sid))
                    break
        if not sid:
            raise exception.IscsiSessionIdNotFound(volume_uuid=iqn, output=stdout)

        cmd = ['iscsiadm', '-m', 'session', '--sid', sid, '-P', '3']
        stdout, _ = processutils.execute(*cmd)
        flag = False
        device_name = None
        for line in stdout.split('\n'):
            if 'Lun: ' in line:
                flag = True
                continue

            if flag:
                device_name = line.split()[3]
                LOG.warning("find iscsi device name is %s" % device_name)
                break

        if not device_name:
            LOG.warning('failed to find iscsi device name, skip multipath config')
            return None

        cmd = '/usr/lib/udev/scsi_id -g -u /dev/%s' % device_name
        stdout, stderr = processutils.trycmd(cmd, shell=True)
        if stderr:
            LOG.info("failed to find iscsi id, because %s, skip multipath config" % stderr)
            return None
        return stdout

    def discovery_target_through_access_path_gateway_ips(self, target_name, volume_access_path_gateway_ips):
        for gateway_ip in volume_access_path_gateway_ips:
            self.login_target(target_name, gateway_ip)

        cmd = 'iscsiadm -m session --rescan'
        stdout, stderr = processutils.trycmd(cmd, shell=True)
        if stderr:
            LOG.info("iscsiadm -m session --rescan fail, because %s" % (stderr))

    def login_target(self, target_name, address_ip, port=3260):
        LOG.info("start login_target:%s by ip %s" % (target_name, address_ip))
        cmd = 'iscsiadm -m session | grep %s | grep %s' % (target_name, address_ip)
        LOG.info(cmd)
        stdout, stderr = processutils.trycmd(cmd, shell=True)
        if not stderr:
            LOG.info("iscsi target:%s has logged by %s" % (target_name, address_ip))
            return

        discovery_cmd = 'iscsiadm -m discovery -t sendtargets -p {address}:{port}'.format(
            address=address_ip,
            port=port,
            target_name=target_name)
        LOG.info(discovery_cmd)
        try:
            stdout, stderr = processutils.execute(discovery_cmd, shell=True)
            if target_name in stdout:
                target_login_cmd = ('iscsiadm --mode node --targetname {target_name} '
                                    '-p {address}:{port} --login').format(
                    target_name=target_name,
                    address=address_ip,
                    port=port)
                LOG.info(target_login_cmd)
                processutils.execute(target_login_cmd, shell=True)
            else:
                LOG.info("discovered targets not contains %s, skip login" % target_name)
        except processutils.ProcessExecutionError:
            LOG.info("no iscsi target found, skip login")
            return

    def attach_volume(self, instance_obj, volume_obj, volume_access_path_gateway_ips):
        """ Attach a given iSCSI lun

        First check the /etc/iscsi/initiatorname.iscsi whether corrent, if
        not, corrent the configuration, then rescan the iscsi session.
        """
        self.discovery_target(instance_obj)
        self.discovery_volume_target(instance_obj, volume_obj, volume_access_path_gateway_ips)
        _check_initiator_config(instance_obj.uuid)

        cmd = ['iscsiadm', '-m', 'session', '--rescan']
        # parameter[delay_on_retry] of func[processutils.execute] will not verify exit_code
        with bm_utils.transcantion(retries=5, sleep_time=10) as cursor:
            cursor.execute(processutils.execute, *cmd)

    def detach_volume(self, instance_obj, volume_obj, volume_access_path_gateway_ips):
        """ Detach a given iSCSI lun

        First check the volume whether attached, if attached, check the map
        between device name and scsi device is corrent, then umount the
        device and delete the device.

        An example of `iscsiadm -m session`::

        tcp: [5] 192.168.203.151:3260,1 iqn.2015-01.io.zstack:target.instance.4b47b010-0288-412c-96aa-8f47d7adcd07 (non-flash) # noqa

        Used part of `iscsiadm -m session --sid sid -P 3`::

                Attached SCSI devices:
                ************************
                Host Number: 11 State: running
                scsi11 Channel 00 Id 0 Lun: 0
                        Attached scsi disk sda          State: running
                scsi11 Channel 00 Id 0 Lun: 1
                        Attached scsi disk sdb          State: running
        """
        for volume_access_path_gateway_ip in volume_access_path_gateway_ips:
            self.detach_volume_for_target_ip(instance_obj, volume_obj, volume_access_path_gateway_ip)

    def detach_volume_for_target_ip(self, instance_obj, volume_obj, target_ip):
        # Get the session id
        sid = None
        volume_iqn = volume_obj.iscsi_path.replace('iscsi://', '').split("/")[1]
        if instance_obj.custom_iqn:
            iqn = instance_obj.custom_iqn
        elif volume_iqn:
            iqn = volume_iqn
        else:
            iqn = instance_obj.uuid

        cmd = 'iscsiadm -m session | grep %s | grep %s' % (iqn, target_ip)
        stdout, stderr = processutils.trycmd(cmd, shell=True)

        LOG.info("detach_volume iqn is %s, target ip is %s" % (iqn, target_ip))
        for line in stdout.split('\n'):
            if iqn in line:
                match = re.search(r'\[(\d+)\]', line)
                if match:
                    sid = match.group(1)
                    LOG.info("detach_volume sid is %s for %s" % (sid, target_ip))
                    break
        if not sid:
            raise exception.IscsiSessionIdNotFound(
                volume_uuid=volume_obj.uuid, output=stdout)

        # Get lun info
        host_num = ''
        device_scsi = ''
        device_name = ''

        cmd = ['iscsiadm', '-m', 'session', '--sid', sid, '-P', '3']
        stdout, _ = processutils.execute(*cmd)
        # Use the flag to tag find the lun dev
        flag = False
        for line in stdout.split('\n'):
            # Construct device scsi id, example: '11:0:0:3'
            if 'Host Number' in line:
                host_num = line.split()[2]
            elif 'Lun: {}'.format(volume_obj.device_id) in line:
                s = line.split()
                device_scsi = '{h}:{c}:{t}:{l}'.format(
                    h=int(host_num),
                    c=int(s[2]),
                    t=int(s[4]),
                    l=int(s[6]))
                flag = True
                continue
            # Get device name, example: 'sdc'
            if flag:
                s = line.split()
                device_name = s[3]
                LOG.warning("detach device name is %s" % device_name)
                break

        if not device_name or not device_scsi:
            msg = 'failed to find iscsi device, {volume_uuid}: {device_id}, skip detach device'.format(
                volume_uuid=volume_obj.uuid, device_id=volume_obj.device_id)
            LOG.warning(msg)
            return

        # Make sure the device_name and device_scsi are same device
        block_path = ('/sys/class/scsi_device/{device_scsi}/'
                      'device/block/').format(device_scsi=device_scsi)
        if device_name not in os.listdir(block_path):
            raise exception.IscsiDeviceNotMatch(
                volume_uuid=volume_obj.uuid,
                device_id=volume_obj.device_id,
                device_name=device_name)

        delete_path = ('/sys/class/scsi_device/{device_scsi}/'
                       'device/delete').format(device_scsi=device_scsi)
        cmd = 'echo 1 > {path}'.format(path=delete_path)
        processutils.execute(cmd, shell=True)

    def attach_port(self, instance_obj, network_obj):
        """ Attach a (list) port(s)
        """
        raise NotImplementedError()

    def detach_port(self, instance_obj, network_obj):
        """ Detach a (list) port(s)
        """
        raise NotImplementedError()

    def update_default_route(
            self, instance_obj, old_network_obj, new_network_obj):
        """ Update the default route(gateway)
        """
        raise NotImplementedError()

    def update_password(self, instance_obj, username, password):
        cmd = 'echo %s:%s | chpasswd' % (username, password)
        processutils.execute(cmd, shell=True)

    def console(self):
        """ Keep shellinaboxd process running

        The implementation is suck, the reason of not using
        processutils.execute is because it will stuck on close fds for some
        unknown reasons.
        """
        if not bm_utils.process_is_running('shellinaboxd'):
            cmd = 'shellinaboxd -b -t -s :SSH:127.0.0.1'
            f = os.popen(cmd)
            f.close()
            if not bm_utils.process_is_running('shellinaboxd'):
                raise exception.ProcessLaunchFailed(
                    process_name='shellinaboxd')

        return {'scheme': 'http', 'port': 4200}
