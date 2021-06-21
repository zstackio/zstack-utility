from zstacklib.utils import shell
from zstacklib.utils import thirdparty_ceph

from kvmagent.plugins.bmv2_gateway_agent.volume import base
from kvmagent.plugins.bmv2_gateway_agent.volume import helper
from zstacklib.utils.thirdparty_ceph import RbdDeviceOperator


class ThirdPartyCephVolume(base.BaseVolume):

    def __init__(self, *args, **kwargs):
        super(ThirdPartyCephVolume, self).__init__(*args, **kwargs)


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
    def iscsi_target(self):
        if self.instance_obj.customIqn:
            return self.instance_obj.customIqn
        else:
            return 'iqn.2015-01.io.zstack:target.instance.{ins_uuid}'.format(
                ins_uuid=self.instance_uuid)

    @property
    def real_path(self):
        return self.volume_obj.path.replace('ceph://', '')

    def attach(self):
        instance_gateway_ip = self.instance_obj.gateway_ip
        host_ip = RbdDeviceOperator()._get_mon_ip_token(self.volume_obj.token)[0]
        shell.run("iptables -t nat -A PREROUTING -d %s -p tcp --dport 3260 -j DNAT --to-destination %s:3260" % (
            instance_gateway_ip, host_ip))
        shell.call("systemctl stop target && systemctl disable target")

        created_iqn = self.sdk_attach(self.volume_obj, self.instance_obj)
        self.instance_obj.customIqn = created_iqn

    def detach(self):
        self.sdk_detach(self.volume_obj, self.instance_obj)

        instance_gateway_ip = self.instance_obj.gateway_ip
        host_ip = RbdDeviceOperator()._get_mon_ip_token(self.volume_obj.token)[0]
        shell.run("iptables -t nat -D PREROUTING -d %s -p tcp --dport 3260 -j DNAT --to-destination %s:3260" % (
            instance_gateway_ip, host_ip))

    @staticmethod
    def sdk_attach(volume_obj, instance_obj):
        token = volume_obj.token
        volume_name = volume_obj.uuid
        func_timeout = volume_obj.tpTimeout

        iqn = thirdparty_ceph.RbdDeviceOperator().connect(token, instance_obj, volume_name, func_timeout)
        return iqn

    @staticmethod
    def sdk_detach(volume_obj, instance_obj):
        token = volume_obj.token
        target_iqn = instance_obj.customIqn
        func_timeout = volume_obj.tpTimeout

        thirdparty_ceph.RbdDeviceOperator().disconnect(token, target_iqn, func_timeout)

    def pre_take_volume_snapshot(self):
        pass

    def post_take_volume_snapshot(self, src_vol):
        pass

    def resume(self):
        pass

    def rollback_volume_snapshot(self, src_vol):
        pass



