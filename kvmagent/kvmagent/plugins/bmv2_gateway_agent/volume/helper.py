# coding=utf-8
import os
import socket
import commands

from zstacklib.utils import log
from zstacklib.utils import shell

from kvmagent.plugins.bmv2_gateway_agent import exception
from kvmagent.plugins.bmv2_gateway_agent.object import TargetcliConfObj
from kvmagent.plugins.bmv2_gateway_agent import utils as bm_utils


logger = log.get_logger(__name__)


class RbdImageOperator(object):
    """ A tool class to operate rbd image
    """

    def __init__(self, volume):
        self.volume = volume
        self._prepare_rbd_nbd()
        self._check_required_commands()

    @staticmethod
    def _prepare_rbd_nbd():
        """
        1、get ceph version
        2、try to find same version rbd-nbd rpm
        3、check installed rbd-nbd version
        4、install or upgrade rbd-nbd
        """
        def _install_or_upgrade_rpm(rpm_path):
            shell.call('rpm -Uvh %s' % rpm_path)

        def _get_package_version(pkg_name, raise_exception=False):
            _rc, version = commands.getstatusoutput('rpm -qa %s' % pkg_name)
            if _rc or (not version and raise_exception):
                raise exception.CephPackageNotFound(cmd=pkg_name)
            return version

        ceph_version = _get_package_version("ceph", True)
        current_rbd_nbd_version = _get_package_version("rbd-nbd")

        dest_rbd_nbd_version = ceph_version.replace("ceph", "rbd-nbd", 1)
        _s, path = commands.getstatusoutput('find / -xdev -name \'%s\'.rpm | head -1' % dest_rbd_nbd_version)

        logger.info("current rbd-nbd version:%s , dest version: %s" % (current_rbd_nbd_version, dest_rbd_nbd_version))
        if not current_rbd_nbd_version and not path:
            raise exception.CephPackageNotFound(cmd=['rbd-nbd'])

        if not current_rbd_nbd_version and path:
            logger.info("found rbd-nbd %s, install it" % path)
            _install_or_upgrade_rpm(path)
            return

        if current_rbd_nbd_version and not path:
            return

        if dest_rbd_nbd_version != current_rbd_nbd_version:
            logger.info("Found a newer version %s, current %s, try to upgrade it" %
                        (dest_rbd_nbd_version, current_rbd_nbd_version))
            _install_or_upgrade_rpm(path)

    @staticmethod
    def _check_required_commands():
        """
        check if ceph/rbd/rbd-nbd installed
        """
        required_cmds = ['ceph', 'rbd', 'rbd-nbd']
        for cmd in required_cmds:
            _s, _ = commands.getstatusoutput('which %s' % cmd)
            if _s:
                raise exception.CephCommandsNotExist(cmds=required_cmds)

    @staticmethod
    def _check_rbd_image(image_path):
        """
        check if rbd image exists
        """
        _s, _ = commands.getstatusoutput('rbd info %s' % image_path)
        if _s:
            raise exception.RbdImageNotExist(path=image_path)

    def connect(self):
        NbdDeviceOperator(self.volume).connect(src_type='rbd')

    def disconnect(self):
        NbdDeviceOperator(self.volume).disconnect(src_type='rbd')


class NbdDeviceOperator(object):
    """ A tool class to operate nbd device
    """

    QEMU_NBD_SOCKET_DIR = '/var/lock/zstack-qemu-nbd/'

    def __init__(self, volume):
        self.volume = volume

        self.used_nbd_ids = []
        self.vol_nbd_backend_mapping = {}
        self.vol_bm_instance_mapping = {}

        self._prepare()

    def _prepare(self):
        if not os.path.exists(self.QEMU_NBD_SOCKET_DIR):
            os.mkdir(self.QEMU_NBD_SOCKET_DIR)

    def _get_exist_nbd_device(self):
        for nbd_socket in os.listdir(self.QEMU_NBD_SOCKET_DIR):
            nbd_id, instance_uuid, volume_uuid = nbd_socket.split('_')

            # Check whether the nbd device is connected
            # If the device not connected, remove the socket file
            pid_path = os.path.join('/sys/block/nbd{}'.format(nbd_id),
                                    'pid')
            if not os.path.exists(pid_path):
                msg = ('The nbd device {nbd_id} was disconnected which is '
                       'unexpected, remove the socket file {socket_file}, '
                       'instance: {instance_uuid}, volume: {volume_uuid}'
                       ).format(
                           nbd_id=nbd_id,
                           socket_file=nbd_socket,
                           instance_uuid=instance_uuid,
                           volume_uuid=volume_uuid)
                logger.warning(msg)
                os.remove(os.path.join(self.QEMU_NBD_SOCKET_DIR, nbd_socket))
                continue

            # Get the source file/dev/rbd path
            with open(pid_path, 'r') as f:
                pid = f.read().strip('\n')

            if not os.path.exists('/proc/{}'.format(pid)):
                continue
            with open('/proc/{}/cmdline'.format(pid), 'r') as f:
                cmdline = f.read().strip('\n')
            nbd_backend = cmdline.split('\x00')[-2]

            yield instance_uuid, volume_uuid, nbd_backend, nbd_id

    def fetch_nbd_id(self):
        """ Try to get the a nbd id for self.volume

        This method should only called during snapshot, it need the old
        nbd device id
        """
        self._refresh()
        if not self.volume.nbd_id:
            raise exception.NbdIdNotFound(
                instance_uuid=self.volume.instance_uuid,
                volume_uuid=self.volume.volume_uuid)

    def _refresh(self):
        self.used_nbd_ids = []
        self.vol_nbd_backend_mapping = {}
        self.vol_bm_instance_mapping = {}
        for ins_uuid, vol_uuid, nbd_backend, nbd_id in \
                self._get_exist_nbd_device():
            self.used_nbd_ids.append(nbd_id)
            self.vol_nbd_backend_mapping[vol_uuid] = nbd_backend
            self.vol_bm_instance_mapping[vol_uuid] = ins_uuid

            if self.volume.instance_uuid == ins_uuid \
                    and self.volume.volume_uuid == vol_uuid \
                    and self.volume.nbd_backend == nbd_backend:
                self.volume.nbd_id = nbd_id

    @staticmethod
    def _check_nbd_dev_empty(nbd_id):
        with open('/sys/block/nbd{}/size'.format(nbd_id), 'r') as f:
            size = f.read()
        if int(size) > 0:
            return False
        return True

    def _get_available_nbd_id(self):
        """ Find a available nbd id and return
        """
        block_devices = os.listdir('/sys/block/')
        all_nbd_ids = []
        for dev in block_devices:
            if dev.startswith('nbd'):
                all_nbd_ids.append(int(dev.split('nbd')[-1]))

        available_nbd_ids = sorted(set(all_nbd_ids) - set(self.used_nbd_ids))

        if not available_nbd_ids:
            raise exception.NoAvailableNbdDevice(
                instance_uuid=self.volume.instance_uuid,
                volume_uuid=self.volume.volume_uuid)

        for nbd_id in available_nbd_ids:
            if self._check_nbd_dev_empty(nbd_id):
                return str(nbd_id)

    def connect(self, src_type='qemu'):
        """ Connect src file/blk/rbd to a nbd device

        if src_type == 'qemu':
            qemu-nbd --format qcow2 --connect /dev/nbdX --socket /var/lock/zstack-qemu-nbd/X path #noqa

        if src_type == 'rbd':
            rbd-nbd map pri-v-r-48328ff2f70d42faa61756faa4c9e98d/a36c7603eee64ec8b4f98c176ccbf5a2
        """

        def _connect():
            # NOTE(ya.wang) Too early to refresh the nbd device dict is not a
            # good idea, new nbd map may created by another thread after the
            # refresh.
            self._refresh()

            # Check the volume whether in use
            vol_uuid = self.volume.volume_uuid
            if self.vol_nbd_backend_mapping.get(vol_uuid) == self.volume.nbd_backend and self.vol_bm_instance_mapping.get(vol_uuid) == self.volume.instance_uuid:
                msg = ('The volume {volume_uuid} had been connected by instance {instance_uuid} before '
                       'the operate').format(
                    volume_uuid=self.volume.volume_uuid, instance_uuid=self.volume.instance_uuid)
                logger.info(msg)
                return

            if not self.volume.nbd_id:
                self.volume.nbd_id = self._get_available_nbd_id()
            socket_path = os.path.join(self.QEMU_NBD_SOCKET_DIR,
                                       self.volume.nbd_socket)
            if src_type == 'qemu':
                # Log the lsof output, to record which process is using the blk.
                logger.info(shell.call('lsof %s' % self.volume.nbd_backend, exception=False))
                cmd = ('qemu-nbd --format {format} --fork {cacheMode}--connect /dev/nbd{nbd_id} '
                       '--socket {socket_path} {nbd_backend}').format(
                            format=self.volume.volume_format,
                            cacheMode="--nocache " if self.volume.is_shareable else "",
                            nbd_id=self.volume.nbd_id,
                            socket_path=socket_path,
                            nbd_backend=self.volume.nbd_backend)
            else:
                socket.socket(socket.AF_UNIX).bind(socket_path)
                cmd = ('rbd-nbd map --device /dev/nbd{nbd_id} '
                       '{nbd_backend}').format(
                            nbd_id=self.volume.nbd_id,
                            nbd_backend=self.volume.nbd_backend)
            shell.check_run(cmd)

        def _check_connected():
            if self._check_nbd_dev_empty(self.volume.nbd_id):
                raise exception.NbdDeviceFailedConnect(
                    instance_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    nbd_dev=self.volume.nbd_dev,
                    nbd_backend=self.volume.nbd_backend)

        with bm_utils.transcantion(retries=5, sleep_time=1) as cursor:
            cursor.execute(_connect)

        # Check the nbd dev connected
        with bm_utils.transcantion(retries=5, sleep_time=1) as cursor:
            cursor.execute(_check_connected)

    def disconnect(self, src_type='qemu'):
        """ Disconnect a nbd device
        """
        def _disconnect():
            if src_type == 'qemu':
                cmd = 'qemu-nbd --disconnect /dev/nbd{nbd_id}'.format(
                    nbd_id=self.volume.nbd_id)
            else:
                cmd = 'rbd-nbd unmap /dev/nbd{nbd_id}'.format(
                    nbd_id=self.volume.nbd_id)
            shell.call(cmd)

        def _check_disconnected():
            if not self._check_nbd_dev_empty(self.volume.nbd_id):
                raise exception.NbdDeviceFailedDisconnect(
                    instance_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    nbd_dev=self.volume.nbd_dev,
                    nbd_backend=self.volume.nbd_backend)

        self._refresh()

        # Check whether the device is connected
        if not self.volume.nbd_id or \
                self._check_nbd_dev_empty(self.volume.nbd_id):
            msg = ('The nbd dev {nbd_id} was disconnected before the '
                   'operate. instance: {instance}, volume: {volume}').format(
                       nbd_id=self.volume.nbd_id,
                       instance=self.volume.instance_uuid,
                       volume=self.volume.volume_uuid)
            logger.info(msg)
            return

        with bm_utils.transcantion(retries=3) as cursor:
            cursor.execute(_disconnect)

        # Check the nbd dev disconnected
        with bm_utils.transcantion(retries=5, sleep_time=1) as cursor:
            cursor.execute(_check_disconnected)


class DmDeviceOperator(object):
    """ A tool class to operate device mapper dev
    """

    def __init__(self, volume):
        self.volume = volume

    def _check_dm_dev_exist(self):
        if not os.path.exists(self.volume.dm_dev):
            return False
        return True

    def _check_is_suspend(self):
        with open('/sys/block/dm-{dm_id}/dm/suspended'.format(
            dm_id=self.volume.dm_id), 'r') as f:
            suspended = int(f.read())
        return True if suspended == 1 else False

    def create(self):
        """ Create device mapper
        """
        def _create():
            # NOTE(ya.wang) Check the device mapper whether created first.
            # The shared block lvs will create device mapper dev automatic,
            # therefore only rename the device mapper
            if os.path.exists(self.volume.dm_dev):
                msg = ('The device mapper {dm_dev} had been created.').format(
                    dm_dev=self.volume.dm_dev)
                logger.info(msg)
                return
            cmd = ('echo "0 `blockdev --getsz {dm_backend}` linear '
                   '{dm_backend} 0" | dmsetup create {dm_name}').format(
                       dm_backend=self.volume.dm_backend,
                       dm_name=self.volume.dm_name)
            shell.call(cmd)

        def _check_created():
            if not self._check_dm_dev_exist():
                raise exception.DeviceMapperFailedCreate(
                    instance_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    dm_name=self.volume.dm_name,
                    dm_backend=self.volume.dm_backend)

        if self._check_dm_dev_exist():
            msg = ('The device mapper {dm_name} exist, skip create it.'
                   'instance: {instance_uuid}, volume: {volume_uuid}'
                   ).format(
                       dm_name=self.volume.dm_name,
                       instance_uuid=self.volume.instance_uuid,
                       volume_uuid=self.volume.volume_uuid)
            logger.info(msg)

        with bm_utils.transcantion(retries=3) as cursor:
            cursor.execute(_create)

        # Check dm dev crated
        with bm_utils.transcantion(retries=5) as cursor:
            cursor.execute(_check_created)

    def remove(self):
        """ Remove device mapper
        """
        def _remove():
            cmd = 'dmsetup remove {dm_dev}'.format(
                dm_dev=self.volume.dm_dev)
            shell.call(cmd)

        def _check_removed():
            if self._check_dm_dev_exist():
                raise exception.DeviceMapperFailedRemove(
                    instance_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    dm_name=self.volume.dm_name,
                    dm_backend=self.volume.dm_backend)

        if not self._check_dm_dev_exist():
            msg = ('The device mapper dev was removed before the operate, '
                   'dm dev: {dm_dev}, instance: {instance}, volume: {volume}'
                   ).format(
                       dm_dev=self.volume.dm_dev,
                       instance=self.volume.instance_uuid,
                       volume=self.volume.volume_uuid)
            logger.warning(msg)
            return

        with bm_utils.transcantion(retries=3) as cursor:
            cursor.execute(_remove)

        with bm_utils.transcantion(retries=5) as cursor:
            cursor.execute(_check_removed)

    # TODO(ya.wang) Need a new implementation
    def reload(self, dst_volume):
        """ Reload the device mapper dev, set a new dev as it's backend
        """

        def _check_reload_add_new_nbd_success():
            if dst_volume.dm_backend_slave_name not in self.volume.dm_slaves:
                raise exception.DeviceMapperFailedReload(
                    instance_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    dm_name=self.volume.dm_name,
                    src_dm_backend=self.volume.dm_backend,
                    dst_dm_backend=dst_volume.dm_backend)

        def _check_reload_remove_old_nbd_success():
            if self.volume.dm_backend_slave_name in self.volume.dm_slaves:
                raise exception.DeviceMapperFailedReload(
                    instance_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    dm_name=self.volume.dm_name,
                    src_dm_backend=self.volume.dm_backend,
                    dst_dm_backend=dst_volume.dm_backend)

        def _reload():
            # self._suspend()

            cmd = ('dmsetup reload {dm_name} --table "0 `blockdev --getsz '
                   '{dst_backend_dev}` linear {dst_backend_dev} 0"').format(
                    dm_name=self.volume.dm_name,
                    dst_backend_dev=dst_volume.dm_backend)
            shell.call(cmd)
            with bm_utils.transcantion(retries=5) as cursor:
                cursor.execute(_check_reload_add_new_nbd_success)

            # self._resume()
            # with bm_utils.transcantion(retries=5) as cursor:
            #     cursor.execute(_check_reload_remove_old_nbd_success)

        with bm_utils.transcantion(retries=3) as cursor:
            cursor.execute(_reload)

    def suspend(self):
        """ Suspend the device mapper dev
        """
        def _do_suspend():
            cmd = 'dmsetup suspend {dm_name}'.format(
                dm_name=self.volume.dm_name)
            shell.call(cmd)

        def _check_suspend():
            if not self._check_is_suspend():
                raise exception.DeviceMapperFailedSuspend(
                    instace_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    dm_name=self.volume.dm_name,
                    dm_backend=self.volume.dm_backend)

        if not self._check_dm_dev_exist():
            raise exception.DeviceNotExist(
                instance_uuid=self.volume.instance_uuid,
                volume_uuid=self.volume.volume_uuid,
                dev=self.volume.dm_dev)

        with bm_utils.transcantion(retries=3) as cursor:
            cursor.execute(_do_suspend)

        with bm_utils.transcantion(retries=5) as cursor:
            cursor.execute(_check_suspend)

    def resume(self):
        """ Resume the device mapper dev
        """
        def _do_resume():
            cmd = 'dmsetup resume {dm_name}'.format(
                dm_name=self.volume.dm_name)
            shell.call(cmd)

        def _check_resume():
            if self._check_is_suspend():
                raise exception.DeviceMapperFailedResume(
                    instace_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    dm_name=self.volume.dm_name,
                    dm_backend=self.volume.dm_backend)

        if not self._check_dm_dev_exist():
            raise exception.DeviceNotExist(
                instance_uuid=self.volume.instance_uuid,
                volume_uuid=self.volume.volume_uuid,
                dev=self.volume.dm_dev)

        with bm_utils.transcantion(retries=3) as cursor:
            cursor.execute(_do_resume)

        with bm_utils.transcantion(retries=5) as cursor:
            cursor.execute(_check_resume)

    def rename(self, dst_volume):

        def _do_rename():
            cmd = 'dmsetup rename {old_name} {new_name}'.format(
                old_name=self.volume.dm_name, new_name=dst_volume.dm_name)
            shell.call(cmd)

        with bm_utils.transcantion(retries=3) as cursor:
            cursor.execute(_do_rename)


class IscsiOperator(object):
    """ A tool class to operate iscsi
    """

    def __init__(self, volume):
        self.volume = volume
        self.current_conf = {}
        self._prepare()
        self.conf = TargetcliConfObj(self.volume)

    def _prepare(self):
        """ Load current configuration and disable auto_save_on_exit
        """
        # Disable auto save on exit
        cmd = 'targetcli / set global auto_save_on_exit=false'
        shell.call(cmd)

        # Remove saved configuration
        # The backstores is device mapper dev, which created by agent, and
        # will disappera after reboot, therefore we don't need restore the
        # targetcli configuration.
        if os.path.exists('/etc/target/saveconfig.json'):
            os.remove('/etc/target/saveconfig.json')

    def setup(self):
        # self._load_conf()
        self.conf.refresh()
        def _create_backstore():
            if self.conf.backstore:
                msg = ('The backstore {backstore} already created, skip the '
                       'creation, instance: {instance_uuid}, volume: '
                       '{volume_uuid}').format(
                           backstore=self.volume.iscsi_backstore_name,
                           instance_uuid=self.volume.instance_uuid,
                           volume_uuid=self.volume.volume_uuid)
                logger.info(msg)
                return
            cmd = ('targetcli /backstores/block/ create '
                   '{backstore} {iscsi_backend}').format(
                       backstore=self.volume.iscsi_backstore_name,
                       iscsi_backend=self.volume.iscsi_backend)
            shell.call(cmd)

        # Create target
        def _create_target():
            if self.conf.target:
                msg = ('The target {target} already created, skip '
                       'creation').format(target=self.volume.iscsi_target)
                logger.info(msg)
                return
            cmd = 'targetcli /iscsi/ create {target}'.format(
                target = self.volume.iscsi_target)
            shell.call(cmd)

            cmd = 'targetcli /iscsi/{target}/tpg1 set attribute authentication=0 demo_mode_write_protect=0 generate_node_acls=1 cache_dynamic_acls=1'.format(
                target = self.volume.iscsi_target)
            shell.call(cmd)

        # Setup lun
        def _create_lun():
            if self.conf.lun_exist:
                msg = ('The lun lun{lun} already created, skip the creation. '
                       'backstore: {backstore}, instance: {instance_uuid}, '
                       'volume: {volume_uuid}').format(
                           lun=self.volume.iscsi_lun,
                           backstore=self.volume.iscsi_backstore_name,
                           instance_uuid=self.volume.instance_uuid,
                           volume_uuid=self.volume.volume_uuid)
                logger.warn(msg)
                return

            cmd = ('targetcli /iscsi/{target}/tpg1/luns create '
                   '/backstores/block/{backstore} {lun}').format(
                       target=self.volume.iscsi_target,
                       backstore=self.volume.iscsi_backstore_name,
                       lun=self.volume.iscsi_lun)
            shell.call(cmd)

        # Setup acl
        def _create_acl():
            if self.conf.acl_exist:
                msg = ('The acl {acl} already created, skip the '
                       'creation, instance: {instance_uuid}').format(
                           acl=self.volume.iscsi_acl,
                           instance_uuid=self.volume.instance_uuid)
                logger.info(msg)
                return

            cmd = 'targetcli /iscsi/{target}/tpg1/acls create {auth}'.format(
                target=self.volume.iscsi_target,
                auth=self.volume.iscsi_acl)
            shell.call(cmd)

        def _check_created():
            self.conf.refresh()
            # Check backstore
            if not self.conf.backstore:
                raise exception.IscsiBackstoreFailedCreate(
                    instance_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    iscsi_backend=self.volume.iscsi_backend,
                    backstore=self.volume.iscsi_backstore_name)

            # Check target
            if not self.conf.target:
                raise exception.IscsiTargetFailedCreate(
                    instance_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    iscsi_backend=self.volume.iscsi_backend,
                    target=self.volume.iscsi_target)

            # Check lun
            if not self.conf.lun_exist:
                raise exception.IscsiLunFailedCreate(
                    instance_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    iscsi_backend=self.volume.iscsi_backend,
                    lun=self.volume.iscsi_lun)

            # Check acl
            if not self.conf.acl_exist:
                raise exception.IscsiAclFailedCreate(
                    instance_uuid=self.volume.instance_uuid,
                    volume_uuid=self.volume.volume_uuid,
                    iscsi_backend=self.volume.iscsi_backend,
                    acl=self.volume.iscsi_acl)

        with bm_utils.transcantion(retries=3) as cursor:
            cursor.execute(_create_backstore)
            cursor.execute(_create_target)
            cursor.execute(_create_lun)
            cursor.execute(_create_acl)

        with bm_utils.transcantion(retries=5) as cursor:
            cursor.execute(_check_created)

    def revoke(self):
        # self._load_conf()
        self.conf.refresh()

        def _revoke_lun():
            if not self.conf.lun_exist:
                msg = ('The lun lun{lun} not exist during revoke, backstore: '
                       '{backstore}, instance: {instance_uuid}, volume: '
                       '{volume_uuid}').format(
                           lun=self.volume.iscsi_lun,
                           backstore=self.volume.iscsi_backstore_name,
                           instance_uuid=self.volume.instance_uuid,
                           volume_uuid=self.volume.volume_uuid)
                logger.warning(msg)
                return

            cmd = ('targetcli /iscsi/{target}/tpg1/luns delete '
                    'lun{index}').format(
                        target=self.volume.iscsi_target,
                        index=self.volume.iscsi_lun)
            shell.call(cmd)

        def _revoke_backstore():
            if not self.conf.backstore:
                msg = ('The backstore {backstore} not exist during revoke, '
                       'instance: {instance_uuid}, volume: '
                       '{volume_uuid}').format(
                           backstore=self.volume.iscsi_backstore_name,
                           instance_uuid=self.volume.instance_uuid,
                           volume_uuid=self.volume.volume_uuid)
                logger.warning(msg)
                return

            cmd = ('targetcli /backstores/block delete '
                    '{backstore}').format(
                        backstore=self.volume.iscsi_backstore_name)
            shell.call(cmd)

        def _revoke_acl():
            if not self.conf.acl_exist:
                msg = ('The acl {acl} not exist during revoke, '
                       'instance: {instance_uuid}').format(
                           acl=self.volume.iscsi_acl,
                           instance_uuid=self.volume.instance_uuid)
                logger.warning(msg)
                return

            if len(self.conf.luns) <= 1:
                cmd = ('targetcli /iscsi/{target}/tpg1/acls delete '
                        '{acl}').format(
                            target=self.volume.iscsi_target,
                            acl=self.volume.iscsi_acl)
                shell.call(cmd)

        def _revoke_target():
            if not self.conf.target:
                msg = ('The target {target} not exist during revoke, '
                       'instance: {instance_uuid}').format(
                           target=self.volume.iscsi_target,
                           instance_uuid=self.volume.instance_uuid)
                logger.warning(msg)
                return
            if len(self.conf.luns) <= 1:
                cmd = 'targetcli /iscsi/ delete {target}'.format(
                            target=self.volume.iscsi_target)
                shell.call(cmd)

        with bm_utils.transcantion(retries=3) as cursor:
            cursor.execute(_revoke_lun)
            cursor.execute(_revoke_backstore)
            cursor.execute(_revoke_acl)
            cursor.execute(_revoke_target)
