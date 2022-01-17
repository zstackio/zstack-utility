from zstacklib.utils import shell
from zstacklib.utils import linux

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
        RbdDeviceOperator(self.volume_obj.monIp, self.volume_obj.token, self.volume_obj.tpTimeout).connect(
            self.instance_obj, self.volume_obj)

    def detach(self):
        RbdDeviceOperator(self.volume_obj.monIp, self.volume_obj.token, self.volume_obj.tpTimeout).disconnect(
            self.instance_obj, self.volume_obj)

    def detach_volume(self):
        RbdDeviceOperator(self.volume_obj.monIp, self.volume_obj.token, self.volume_obj.tpTimeout).detach_volume(
            self.instance_obj, self.volume_obj)

    def prepare_instance_resource(self):
        instance_gateway_ip = self.instance_obj.gateway_ip
        mon_ip = self.volume_obj.monIp
        dev_name = linux.find_route_interface_by_destination_ip(mon_ip)
        snat_ip = linux.find_route_interface_ip_by_destination_ip(mon_ip)

        created_iqn = RbdDeviceOperator(mon_ip, self.volume_obj.token, self.volume_obj.tpTimeout).prepare(
            self.instance_obj, self.volume_obj, snat_ip)

        if self.instance_obj.customIqn and self.instance_obj.customIqn == created_iqn:
            return

        self.instance_obj.customIqn = created_iqn
        shell.run("iptables -t nat -A PREROUTING -s %s -d %s -p tcp --dport 3260 -j DNAT --to-destination %s:3260" %
                  (self.instance_obj.provision_ip, instance_gateway_ip, mon_ip))
        if snat_ip != mon_ip:
            shell.run("iptables -t nat -A POSTROUTING -s %s -o %s -j SNAT --to-source %s" % (
            self.instance_obj.provision_ip, dev_name, snat_ip))


    def destroy_instance_resource(self):
        instance_gateway_ip = self.instance_obj.gateway_ip
        mon_ip = self.volume_obj.monIp
        snat_ip = linux.find_route_interface_ip_by_destination_ip(mon_ip)

        RbdDeviceOperator(mon_ip, self.volume_obj.token, self.volume_obj.tpTimeout).destory(self.instance_obj)

        # Random monIp will delete the incorrect ip rule, find the mon ip used for creation
        # Example of iptables rule:
        # -A PREROUTING -s 10.90.0.4/32 -d 10.90.0.3/32 -p tcp -m tcp --dport 3260 -j DNAT --to-destination 172.25.13.96:3260
        ips = shell.call(
            '''iptables-save|awk '{if($2=="PREROUTING"&&$4 =="%s/32"&&$15 =="--to-destination") print $16}' ''' % self.instance_obj.provision_ip).splitlines()

        for ip in ips:
            old_mon_ip = ip.strip().split(":")[0]
            shell.run("iptables -t nat -D PREROUTING -s %s -d %s -p tcp --dport 3260 -j DNAT --to-destination %s:3260" %
                      (self.instance_obj.provision_ip, instance_gateway_ip, old_mon_ip))
            if snat_ip != old_mon_ip:
                dev_name = linux.find_route_interface_by_destination_ip(old_mon_ip)
                shell.run("iptables -t nat -D POSTROUTING -s %s -o %s -j SNAT --to-source %s" % (
                    self.instance_obj.provision_ip, dev_name, snat_ip))

    def pre_take_volume_snapshot(self):
        pass

    def post_take_volume_snapshot(self, src_vol):
        pass

    def resume(self):
        pass

    def rollback_volume_snapshot(self, src_vol):
        pass

    def get_lun_id(self):
        lun_id = RbdDeviceOperator(self.volume_obj.monIp, self.volume_obj.token, self.volume_obj.tpTimeout).get_lun_id(self.volume_obj)
        return lun_id
