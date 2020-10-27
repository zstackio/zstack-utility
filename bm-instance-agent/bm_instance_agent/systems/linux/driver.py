import os

from oslo_concurrency import processutils
from oslo_log import log as logging

from bm_instance_agent import exception
from bm_instance_agent.systems import base
from bm_instance_agent.common import utils as bm_utils

LOG = logging.getLogger(__name__)


class LinuxDriver(base.SystemDriverBase):

    driver_name = 'linux'

    def __init__(self):
        super(LinuxDriver, self).__init__()

    def reboot(self, instance_obj):
        cmd = ['shutdown', '-r', 'now']
        try:
            processutils.execute(*cmd)
        except Exception as e:
            if 'shutdown -r now' not in e:
                raise e

        # if stderr:
        #     raise exception.BmInstanceRebootFailed(bm_uuid=instance_obj.uuid,
        #                                            stderr=stderr)

    def stop(self, instance_obj):
        cmd = ['shutdown', '-h', 'now']
        try:
            processutils.execute(*cmd)
        except Exception as e:
            if 'shutdown -h now' not in e:
                raise e

        # if stderr:
        #     raise exception.BmInstanceRebootFailed(bm_uuid=instance_obj.uuid,
        #                                            stderr=stderr)

    def attach_volume(self, instance_obj, volume_obj):
        """ Attach a given iSCSI lun

        First check the /etc/iscsi/initiatorname.iscsi whether corrent, if
        not, corrent the configuration, then rescan the iscsi session.
        """
        conf_path = '/etc/iscsi/initiatorname.iscsi'
        initiator = ('InitiatorName=iqn.2015-01.io.zstack:initiator.'
                     'instance.{uuid}').format(uuid=instance_obj.uuid)
        with open(conf_path, 'w') as f:
            f.write(initiator)

        cmd = 'systemctl daemon-reload && systemctl restart iscsid'
        processutils.execute(cmd, shell=True)

        cmd = ['iscsiadm', '-m', 'session', '--rescan']
        processutils.execute(*cmd)

    def detach_volume(self, instance_obj, volume_obj):
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
        # Get the session id
        sid = None
        cmd = ['iscsiadm', '-m', 'session']
        stdout, _ = processutils.execute(*cmd)
        for line in stdout.split('\n'):
            if instance_obj.uuid in line:
                sid = line.split()[1][1]
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
                break

        if not device_name or not device_scsi:
            raise exception.IscsiDeviceNotFound(
                volume_uuid=volume_obj.uuid, device_id=volume_obj.device_id)

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

    def _pre_attach_port(self, instance_obj, network_obj):
        """ Configure the ip address and default route via iproute2
        """
        # Configure ip address
        for port in network_obj.ports:
            curr_address = bm_utils.get_addr(port.iface_name)
            if not curr_address.get('addr') == port.ip_address or \
                    not curr_address.get('netmask') == port.netmask:
                cmd = ['ip', 'address', 'flush', 'dev', port.iface_name]
                processutils.execute(*cmd)

                cidr = bm_utils.convert_netmask(port.netmask)
                addr = '%s/%d' % (port.ip_address, cidr)
                cmd = ['ip', 'address', 'add', addr, 'dev', port.iface_name]
                processutils.execute(*cmd)

                # Set the link up
                cmd = ['ip', 'link', 'set', 'dev', port.iface_name, 'up']
                processutils.execute(*cmd)

        # Configure default gateway
        gw_addr, gw_iface = bm_utils.get_gateway()
        if not network_obj.default_gw_addr or \
                gw_addr == network_obj.default_gw_addr:
            return

        if gw_addr:
            cmd = ['ip', 'route', 'delete', 'default', 'via', gw_addr,
                   'dev', gw_iface]
            processutils.execute(*cmd)

        cmd = ['ip', 'route', 'add', 'default', 'via',
               network_obj.default_gw_addr]
        processutils.execute(*cmd)

    def _post_attach_port(self, instance_obj, network_obj):
        """ Setup the persistent configuration files
        """

    def attach_port(self, instance_obj, network_obj):
        """ Attach a (list) port(s)
        """
        self._pre_attach_port(instance_obj, network_obj)
        self._post_attach_port(instance_obj, network_obj)

    def _pre_detach_port(self, instance_obj, network_obj):
        """ Flush the network interface configuration via iproute2
        """
        # Configure ip address
        for port in network_obj.ports:
            cmd = ['ip', 'address', 'flush', 'dev', port.iface_name]
            processutils.execute(*cmd)

    def _post_detach_port(self, instance_obj, network_obj):
        """ Flush or remove the configuration files
        """

    def detach_port(self, instance_obj, network_obj):
        self._pre_detach_port(instance_obj, network_obj)
        self._post_detach_port(instance_obj, network_obj)

    def update_default_route(
            self, instance_obj, old_network_obj, new_network_obj):
        """ Update the default route(gateway)
        """
        raise NotImplementedError()

    def update_password(self, instance_obj, password):
        cmd = 'echo root:%s | chpasswd' % password
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

        return {'port': 4200}
