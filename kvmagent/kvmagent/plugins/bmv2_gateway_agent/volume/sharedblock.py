import os

from zstacklib.utils import shell
from zstacklib.utils import lvm

from kvmagent.plugins.bmv2_gateway_agent import exception
from kvmagent.plugins.bmv2_gateway_agent import utils as bm_utils
from kvmagent.plugins.bmv2_gateway_agent.volume import base
from kvmagent.plugins.bmv2_gateway_agent.volume import helper


class SharedBlockVolume(base.BaseVolume):

    def __init__(self, *args, **kwargs):
        super(SharedBlockVolume, self).__init__(*args, **kwargs)

    def check_exist(self):
        """ Check whether the volume exist

        For shared block, check both lv path and device mapper path.
        """

        if not os.path.exists(self.real_path):
            lvm.active_lv(self.real_path)
           # raise exception.DeviceNotExist(
           #     instance_uuid=self.instance_uuid,
           #     volume_uuid=self.volume_uuid,
           #     dev=self.real_path)

    @property
    def nbd_backend(self):
        return self.real_path

    @property
    def dm_backend(self):
        return self.nbd_dev

    @property
    def dm_backend_slave_name(self):
        return self.nbd_dev.split('/')[-1]

    @property
    def iscsi_backend(self):
        return self.dm_id_dev

    @property
    def real_path(self):
        """ Get the shared block's real path

        Mark the shared block lun active, and check the device whether exist.
        Note that the kernel will create a device mapper dev to point the lv
        is added. A symbolic link /dev/VG-Name/LVName pointing to the device
        node is also added. Therefore here will be three dev point the the
        lv: `/dev/dm-X`, `/dev/VG-Name/LVName`, `/dev/mapper/VGName-LVName`.

        The src path in volume params should like
        `sharedblock://VG-Name/LVName`, so convert it to real path
        `/dev/VG-Name/LVName`
        """
        path = self.volume_obj.path.replace('sharedblock://', '/dev/')

        return path

    # @property
    # def dm_name(self):
    #     """ Construct device mapper dev name

    #     As metion in real_path, the device mapper dev already created
    #     during mark the shared block lun active, therefore the only thing
    #     need to do is get the exist dm name
    #     """
    #     vg_name, lv_name = self.real_path.split('/')[-2:]
    #     return '{vg_name}-{lv_name}'.format(vg_name=vg_name, lv_name=lv_name)

    def attach(self):
        helper.NbdDeviceOperator(self).connect()
        helper.DmDeviceOperator(self).create()
        helper.IscsiOperator(self).setup()

    def detach(self):
        helper.IscsiOperator(self).revoke()
        helper.DmDeviceOperator(self).remove()
        helper.NbdDeviceOperator(self).disconnect()
        # Do not remove the dm device, because it was created by kernel
        # helper.DmDeviceOperator(self).remove()
        lvm.deactive_lv(self.real_path)

    def prepare_instance_resource(self):
        pass

    def destroy_instance_resource(self):
        pass

    def pre_take_volume_snapshot(self):
        # NOTE: self is src_vol
        nbd_operator = helper.NbdDeviceOperator(self)
        nbd_operator.fetch_nbd_id()

        dm_operator = helper.DmDeviceOperator(self)
        with bm_utils.rollback(dm_operator.resume):
            dm_operator.suspend()
            nbd_operator.disconnect()

    def post_take_volume_snapshot(self, src_vol):
        # NOTE: self is dst_vol
        src_nbd_operator = helper.NbdDeviceOperator(src_vol)
        with bm_utils.rollback(src_nbd_operator.connect):
            # Use src vol to init dm device operator
            dm_operator = helper.DmDeviceOperator(src_vol)
            # Use dst vol to init nbd device operator
            nbd_operator = helper.NbdDeviceOperator(self)

            nbd_operator.connect()

            with bm_utils.rollback(nbd_operator.disconnect):
                dm_operator.reload(self)

            dm_operator.resume()
            # helper.NbdDeviceOperator(src_vol).disconnect()

            # Rename the dm dev to new volume's dm name
            #dm_operator.rename(self)

    def resume(self):
        # NOTE: self should be src_vol
        helper.DmDeviceOperator(self).resume()

    def rollback_volume_snapshot(self, src_vol):
        """ Rollback volume snapshot if the action failed
        """
        src_nbd_operator = helper.NbdDeviceOperator(src_vol)
        snapshot_nbd_operator = helper.NbdDeviceOperator(self)
        dm_operator = helper.DmDeviceOperator(src_vol)
        def _rollback():
            # Set snapshot vol nbd id to None to disconnect the nbd id
            self.nbd_id = None
            snapshot_nbd_operator.disconnect()
            # No need to set src vol nbd id to None, because the volume
            # operate processed one by one.
            # src_vol.nbd_id = None
            src_nbd_operator.connect()
            dm_operator.reload(src_vol)
            dm_operator.resume()

        with bm_utils.transcantion(retries=5, sleep_time=1) as cursor:
            cursor.execute(_rollback)
