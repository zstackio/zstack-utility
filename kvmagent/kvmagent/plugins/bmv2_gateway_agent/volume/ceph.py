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
        self.config_xdc()

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
        shell.call("systemctl start target && systemctl enable target")

        helper.RbdImageOperator(self).connect()
        helper.IscsiOperator(self).setup()

    def detach(self):
        helper.IscsiOperator(self).revoke()
        helper.RbdImageOperator(self).disconnect()

    def detach_volume(self):
        self.detach()

    def prepare_instance_resource(self):
        pass

    def destroy_instance_resource(self):
        pass

    def pre_take_volume_snapshot(self):
        pass

    def post_take_volume_snapshot(self, src_vol):
        pass

    def resume(self):
        pass

    def rollback_volume_snapshot(self, src_vol):
        pass

    def get_lun_id(self):
        pass

    def roll_back_attach_volume(self):
        self.detach_volume()

    def config_xdc(self):
        # if gateway do not have xdc.conf, pass this step
        cfg_path = '/etc/xdc/xdc.conf'
        dirname = os.path.dirname(cfg_path)
        if not os.path.exists(dirname):
            return

        # if xdc_proxy_feature = true already exist, pass this step
        if shell.run("grep -c '^xdc_proxy_feature\s*=\s*true$' /etc/xdc/xdc.conf") == 0:
            return

        # do xdc config
        command = """sed -i '/^xdc_proxy_feature = true$/d' /etc/xdc/xdc.conf;
        echo xdc_proxy_feature = true >>/etc/xdc/xdc.conf;
        echo -e "iscsi_target_mod\ntarget_core_user\ntarget_core_iblock" > /etc/modules-load.d/target.conf;
        systemctl enable target;
        systemctl enable xdc
        """
        shell.call(command)
        raise Exception(
            " The gateway node has no LIO configurations."
            " So we have modified the configuration file."
            " Please reboot the gateway node and perform this operation again.")
