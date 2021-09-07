import os

from zstacklib.utils import lvm
from zstacklib.utils import shell

from kvmagent.plugins.bmv2_gateway_agent import exception
from kvmagent.plugins.bmv2_gateway_agent import utils as bm_utils
from kvmagent.plugins.bmv2_gateway_agent.volume import base
from kvmagent.plugins.bmv2_gateway_agent.volume import helper


class CephVolume(base.BaseVolume):

    def __init__(self, *args, **kwargs):
        super(CephVolume, self).__init__(*args, **kwargs)

    def check_exist(self):
        """ Check whether the volume exist
        """
        helper.RbdImageOperator._check_rbd_image(self.real_path)

    @property
    def nbd_backend(self):
        return self.real_path

    @property
    def iscsi_backend(self):
        return self.nbd_dev

    @property
    def real_path(self):
        return self.volume_obj.path.replace('ceph://', '')

    def attach(self):
        helper.RbdImageOperator(self).connect()
        helper.IscsiOperator(self).setup()

    def detach(self):
        helper.IscsiOperator(self).revoke()
        helper.RbdImageOperator(self).disconnect()

    def pre_take_volume_snapshot(self):
        pass

    def post_take_volume_snapshot(self, src_vol):
        pass

    def resume(self):
        pass

    def rollback_volume_snapshot(self, src_vol):
        pass
