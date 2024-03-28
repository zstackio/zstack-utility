from kvmagent.plugins.bmv2_gateway_agent.volume import base

from zstacklib.utils import shell, linux


class ExponVolume(base.BaseVolume):

    def __init__(self, *args, **kwargs):
        super(ExponVolume, self).__init__(*args, **kwargs)

    def check_exist(self):
        pass

    @property
    def nbd_backend(self):
        return self.real_path

    @property
    def iscsi_backend(self):
        return self.nbd_dev

    @property
    def iscsi_target(self):
        return self.volume_obj.targetIqn

    @property
    def real_path(self):
        return self.volume_obj.path.replace('expon://', '')

    def attach(self):
        pass

    def detach(self):
        pass

    def detach_volume(self):
        pass

# monIp: 172.27.16.181,172.27.16.99,...
    def prepare_instance_resource(self):
        instance_gateway_ip = self.instance_obj.gateway_ip
        mon_ip = self.volume_obj.monIp
        dev_name = linux.find_route_interface_by_destination_ip(mon_ip)
        shell.run("iptables -t nat -A PREROUTING -s %s -d %s -p tcp --dport 3260 -j DNAT --to-destination %s:3260" %
                  (self.instance_obj.provision_ip, instance_gateway_ip, mon_ip))
        shell.run("iptables -t nat -A POSTROUTING -s %s -o %s -j SNAT --to-source %s" % (
            self.instance_obj.provision_ip, dev_name, mon_ip))

    def destroy_instance_resource(self):
        instance_gateway_ip = self.instance_obj.gateway_ip
        mon_ip = self.volume_obj.monIp
        dev_name = linux.find_route_interface_by_destination_ip(mon_ip)
        shell.run("iptables -t nat -D PREROUTING -s %s -d %s -p tcp --dport 3260 -j DNAT --to-destination %s:3260" %
                  (self.instance_obj.provision_ip, instance_gateway_ip, mon_ip))
        shell.run("iptables -t nat -D POSTROUTING -s %s -o %s -j SNAT --to-source %s" % (
            self.instance_obj.provision_ip, dev_name, mon_ip))

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