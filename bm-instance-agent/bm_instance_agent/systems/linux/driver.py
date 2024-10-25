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
        device {
                vendor "ET"
                product "ET_WDS"
                hardware_handler "0"
                path_grouping_policy "multibus"
                path_selector "queue-length 0"
                failback immediate
                path_checker           tur
                prio                   const
                no_path_retry fail
                fast_io_fail_tmo 120
        }
}
"""


def _check_initiator_config(instance_uuid):
    cmd = 'which systemctl > /dev/null 2>&1 && systemctl status iscsid || service iscsid status'
    stdout, stderr = processutils.trycmd(cmd, shell=True)
    if stderr:
        LOG.info("get iscsid status failed, try to restart iscsid service")
        cmd = 'systemctl restart iscsid || service iscsid restart'
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
        cmd = 'which systemctl > /dev/null 2>&1 && systemctl restart iscsid || service iscsid restart'
        processutils.execute(cmd, shell=True)


def _check_multi_path_config():
    if not os.path.exists(multipath_conf_path):
        with open(multipath_conf_path, 'w') as f:
            f.write(multi_path_daemon_cofig)
            f.flush()
        LOG.info("multipath config not exists, create multipath conf to %s" % multipath_conf_path)

    cmd = 'which systemctl > /dev/null 2>&1 && systemctl status multipathd || service multipathd status'
    stdout, stderr = processutils.trycmd(cmd, shell=True)
    if stderr:
        LOG.info("get multipathd status failed, try to restart multipathd service")
        cmd = 'which systemctl > /dev/null 2>&1 && systemctl restart multipathd || service multipathd restart'
        processutils.execute(cmd, shell=True)

    # Display detailed debug information for multipath devices
    cmd = 'multipath -v3'
    processutils.execute(cmd, shell=True)


def rescan_sids_target_name(target_name):
    cmd = "iscsiadm -m session | grep {} | awk '{{print $2}}' | tr -d '[]'".format(target_name)
    LOG.info(cmd)
    stdout, stderr = processutils.trycmd(cmd, shell=True)
    if stderr:
        LOG.info("iscsiadm -m session grep %s failed, because %s" % (target_name, stderr))
        return
    session_ids = stdout.strip().split('\n')
    for session_id in session_ids:
        if not session_id:
            continue
        rescan_cmd = 'iscsiadm -m session -r %s --rescan' % session_id
        LOG.info(rescan_cmd)
        stdout, stderr = processutils.trycmd(rescan_cmd, shell=True)
        if stderr:
            LOG.info("iscsiadm -m session -r %s --rescan fail, because %s" % (session_id, stderr))


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
        rescan_sids_target_name(target_name)

    def discovery_volume_target(self, instance_obj, volume_obj, volume_access_path_gateway_ips):
        if not volume_obj.iscsi_path:
            return
        target_name = volume_obj.iscsi_path.replace('iscsi://', '').split("/")[1]
        self.discovery_target_through_access_path_gateway_ips(target_name, volume_access_path_gateway_ips)

    def discovery_target_through_access_path_gateway_ips(self, target_name, volume_access_path_gateway_ips):
        for gateway_ip in volume_access_path_gateway_ips:
            if not target_name:
                discovery_cmd = "timeout 5 iscsiadm -m discovery -t sendtargets -p {address}:{port} | awk '{{print $2}}'".format(address=gateway_ip, port=3260)
                stdout, stderr = processutils.trycmd(discovery_cmd, shell=True)
                if stderr:
                    raise Exception("discovered targets fail, %s" % stderr)
                target_name = stdout.strip()
            self.login_target(target_name, gateway_ip)
        rescan_sids_target_name(target_name)

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
        _check_multi_path_config()

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
            cmd = 'shellinaboxd -b -t -s \':SSH:127.0.0.1:%s\'' % bm_utils.get_ssh_port()
            f = os.popen(cmd)
            f.close()
            if not bm_utils.process_is_running('shellinaboxd'):
                raise exception.ProcessLaunchFailed(
                    process_name='shellinaboxd')

        return {'scheme': 'http', 'port': 4200}
