import os

from kvmagent.plugins.bmv2_gateway_agent import exception


class BaseVolume(object):

    def __init__(self, instance_obj, volume_obj):
        self.instance_obj = instance_obj
        self.volume_obj = volume_obj

        self.nbd_id = None

        self.check_exist()

    def check_exist(self):
        """ Check whether the volume exist
        """

    @property
    def instance_uuid(self):
        return self.instance_obj.uuid

    @property
    def volume_uuid(self):
        return self.volume_obj.uuid

    @property
    def volume_format(self):
        return self.volume_obj.format

    @property
    def nbd_backend(self):
        raise ValueError()

    @property
    def dm_backend(self):
        raise ValueError()

    @property
    def dm_backend_slave_name(self):
        raise ValueError()

    @property
    def iscsi_backend(self):
        raise ValueError()

    @property
    def nbd_socket(self):
        if not self.nbd_id:
            raise exception.NbdIdNotFound(instace_uuid=self.instance_uuid,
                                          volume_uuid=self.volume_uuid)
        return '{nbd_id}_{ins_uuid}_{vol_uuid}'.format(
            nbd_id=self.nbd_id,
            ins_uuid=self.instance_obj.uuid,
            vol_uuid=self.volume_obj.uuid)

    @property
    def nbd_dev(self):
        if not self.nbd_id:
            raise exception.NbdIdNotFound(instace_uuid=self.instance_uuid,
                                          volume_uuid=self.volume_uuid)
        return '/dev/nbd{nbd_id}'.format(nbd_id=self.nbd_id)

    @property
    def dm_name(self):
        return 'zstack_dm_{ins_uuid}_{vol_uuid}'.format(
            ins_uuid=self.instance_obj.uuid,
            vol_uuid=self.volume_obj.uuid)

    @property
    def dm_dev(self):
        return '/dev/mapper/{dm_name}'.format(dm_name=self.dm_name)

    @property
    def dm_id(self):
        if not os.path.exists(self.dm_dev):
            raise exception.DeviceNotExist(instance_uuid=self.instance_uuid,
                                           volume_uuid=self.volume_uuid,
                                           dev=self.dm_dev)

        # The return of os.readline(dm_dev) should like '../dm-{id}'
        real_dev = os.readlink(self.dm_dev)
        return real_dev.split('dm-')[-1]

    @property
    def dm_id_dev(self):
        return '/dev/dm-{id}'.format(id=self.dm_id)

    @property
    def dm_slaves(self):
        path = '/sys/block/dm-{dm_id}/slaves'.format(dm_id=self.dm_id)
        return os.listdir(path)

    @property
    def iscsi_backstore_name(self):
        # NOTE(ya.wang) The backstore name max length is 16 bytes
        # Use device id(iscsi lun id) to tag the backstore, the reason not
        # use vol uuid is because the snapshot's id will change.
        # return '{ins_uuid}_{vol_uuid}'.format(
        #     ins_uuid = self.instance_uuid[:7],
        #     vol_uuid = self.volume_uuid[:7])
        return '{ins_uuid}_{lun_id}'.format(
            ins_uuid=self.instance_uuid[:7],
            lun_id=self.iscsi_lun)

    @property
    def iscsi_target(self):
        return 'iqn.2015-01.io.zstack:target.instance.{ins_uuid}'.format(
            ins_uuid = self.instance_uuid)

    @property
    def iscsi_acl(self):
        return 'iqn.2015-01.io.zstack:initiator.instance.{ins_uuid}'.format(
            ins_uuid = self.instance_uuid)

    @property
    def iscsi_lun(self):
        return self.volume_obj.device_id

    def attach(self):
        raise NotImplementedError()

    def detach(self):
        raise NotImplementedError()

    def prepare_instance_resource(self):
        raise NotImplementedError()

    def destory_instance_resource(self):
        raise NotImplementedError()
