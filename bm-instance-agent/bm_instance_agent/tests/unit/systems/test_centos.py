import mock
import os

from bm_instance_agent.common import utils as bm_utils
from bm_instance_agent import exception
from bm_instance_agent import objects
from bm_instance_agent.systems.linux.distro import centos
from bm_instance_agent.tests import base
from bm_instance_agent.tests.unit import fake


class TestCentOSDriver(base.TestCase):

    @mock.patch('oslo_concurrency.processutils.execute')
    def test_reboot(self, mock_execute):
        mock_execute.return_value = None, None
        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))

        driver = centos.CentOSDriver()
        driver.reboot(instance_obj)

        cmd = ['shutdown', '-r', 'now']
        mock_execute.assert_called_once_with(*cmd)

    @mock.patch('oslo_concurrency.processutils.execute')
    def test_stop(self, mock_execute):
        mock_execute.return_value = None, None
        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))

        driver = centos.CentOSDriver()
        driver.stop(instance_obj)

        cmd = ['shutdown', '-h', 'now']
        mock_execute.assert_called_once_with(*cmd)

    @mock.patch('bm_instance_agent.systems.linux.driver.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_volume_attach(self, mock_execute, mock_open):
        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        volume_obj = objects.VolumeObj.from_json(
            bm_utils.camel_obj_to_snake(fake.VOLUME1))

        driver = centos.CentOSDriver()
        driver.attach_volume(instance_obj, volume_obj)

        mock_open.assert_called_once_with(
            '/etc/iscsi/initiatorname.iscsi', 'w')
        handle = mock_open().__enter__()
        handle.write.assert_called_once_with(
            'InitiatorName=iqn.2015-01.io.zstack:initiator.instance.'
            '7b432900-c0ad-47e7-b1c7-01b74961c235')

        calls = (
            mock.call(
                'systemctl daemon-reload && systemctl restart iscsid',
                shell=True),
            mock.call(*['iscsiadm', '-m', 'session', '--rescan'])
        )
        mock_execute.assert_has_calls(calls)

    @mock.patch('os.listdir')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_volume_detach(self, mock_execute, mock_listdir):
        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        volume_obj = objects.VolumeObj.from_json(
            bm_utils.camel_obj_to_snake(fake.VOLUME1))

        mock_listdir.return_value = ['sdb']

        mock_execute.side_effect = (
            (fake.ISCSI_SESSION1, None),
            (fake.ISCSI_SESSION_DETAIL1, None),
            (None, None))

        driver = centos.CentOSDriver()
        driver.detach_volume(instance_obj, volume_obj)

        calls = [
            mock.call(*['iscsiadm', '-m', 'session']),
            mock.call(
                *['iscsiadm', '-m', 'session', '--sid', '5', '-P', '3']),
            mock.call(
                'echo 1 > /sys/class/scsi_device/11:0:0:1/device/delete',
                shell=True)
        ]
        mock_execute.assert_has_calls(calls)

    @mock.patch('oslo_concurrency.processutils.execute')
    def test_volume_detach_session_id_not_exist(self, mock_execute):
        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        volume_obj = objects.VolumeObj.from_json(
            bm_utils.camel_obj_to_snake(fake.VOLUME1))

        mock_execute.side_effect = (
            (fake.ISCSI_SESSION2, None),)

        driver = centos.CentOSDriver()
        self.assertRaises(
            exception.IscsiSessionIdNotFound,
            driver.detach_volume, instance_obj, volume_obj)

    @mock.patch('oslo_concurrency.processutils.execute')
    def test_volume_detach_not_exist(self, mock_execute):
        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        volume_obj = objects.VolumeObj.from_json(
            bm_utils.camel_obj_to_snake(fake.VOLUME1))

        mock_execute.side_effect = (
            (fake.ISCSI_SESSION1, None),
            (fake.ISCSI_SESSION_DETAIL2, None))

        driver = centos.CentOSDriver()
        self.assertRaises(
            exception.IscsiDeviceNotFound,
            driver.detach_volume, instance_obj, volume_obj)

    @mock.patch('os.listdir')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_volume_detach_not_match(self, mock_execute, mock_listdir):
        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        volume_obj = objects.VolumeObj.from_json(
            bm_utils.camel_obj_to_snake(fake.VOLUME1))

        mock_listdir.return_value = ['sdc']

        mock_execute.side_effect = (
            (fake.ISCSI_SESSION1, None),
            (fake.ISCSI_SESSION_DETAIL1, None))

        driver = centos.CentOSDriver()
        self.assertRaises(
            exception.IscsiDeviceNotMatch,
            driver.detach_volume, instance_obj, volume_obj)

    @mock.patch('netifaces.AF_INET', 2)
    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_port_attach_not_default_route(
        self, mock_execute, mock_open, mock_ifaces, mock_ifaddr):
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT1_NONE_IP, fake.IFACE_PORT2_NONE_IP,
            fake.IFACE_PORT1_NONE_IP)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT1))

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.attach_port(instance_obj, network_obj)

        calls = (
            mock.call(*['ifdown', 'enp4s0f0']),
            mock.call(*['ifup', 'enp4s0f0'])
        )
        mock_execute.assert_has_calls(calls)

        conf = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=no
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f0
ONBOOT=yes
DEVICE=enp4s0f0
IPADDR=10.0.120.10
NETMASK=255.255.255.0

GATEWAY=10.0.120.1

'''
        handle.write.assert_called_once_with(conf)

    @mock.patch('netifaces.AF_INET', 2)
    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_port_attach_default_route_no_vlan(
        self, mock_execute, mock_open, mock_ifaces, mock_ifaddr):
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT1_NONE_IP, fake.IFACE_PORT2_NONE_IP,
            fake.IFACE_PORT2_NONE_IP)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT2))

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.attach_port(instance_obj, network_obj)

        calls = (
            mock.call(*['ifdown', 'enp4s0f1']),
            mock.call(*['ifup', 'enp4s0f1'])
        )
        mock_execute.assert_has_calls(calls)

        conf = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=yes
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f1
ONBOOT=yes
DEVICE=enp4s0f1
IPADDR=10.0.0.20
NETMASK=255.255.255.0

GATEWAY=10.0.0.1

'''
        handle.write.assert_called_once_with(conf)

    @mock.patch('netifaces.AF_INET', 2)
    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_port_attach_default_route_with_vlan(
        self, mock_execute, mock_open, mock_ifaces, mock_ifaddr):
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT3_NONE_IP, fake.IFACE_PORT2_NONE_IP,
            fake.IFACE_PORT3_NONE_IP)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT3))

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.attach_port(instance_obj, network_obj)

        calls = (
            mock.call(*['ifdown', 'enp4s0f1.130']),
            mock.call(*['ifup', 'enp4s0f1.130'])
        )
        mock_execute.assert_has_calls(calls)

        conf = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=yes
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f1.130
ONBOOT=yes
DEVICE=enp4s0f1.130
IPADDR=10.0.10.20
NETMASK=255.255.255.0

GATEWAY=10.0.10.1


VLAN=yes
'''
        handle.write.assert_called_once_with(conf)

    @mock.patch('netifaces.AF_INET', 2)
    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_port_attach_exist_diff_ip(
        self, mock_execute, mock_open, mock_ifaces, mock_ifaddr):
        iface_port = {
            17: [{
                'addr': '52:54:00:23:f1:c0',
                'broadcast': 'ff:ff:ff:ff:ff:ff'
            }],
            2: [{
                'addr': '10.0.1.1',
                'netmask': '255.255.0.0'
            }]
        }
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT1, fake.IFACE_PORT2_NONE_IP, iface_port)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT1))

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.attach_port(instance_obj, network_obj)

        calls = (
            mock.call(*['ifdown', 'enp4s0f0']),
            mock.call(*['ifup', 'enp4s0f0'])
        )
        mock_execute.assert_has_calls(calls)

        conf = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=no
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f0
ONBOOT=yes
DEVICE=enp4s0f0
IPADDR=10.0.120.10
NETMASK=255.255.255.0

GATEWAY=10.0.120.1

'''
        handle.write.assert_called_once_with(conf)

    @mock.patch('netifaces.AF_INET', 2)
    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_port_attach_exist_same_ip(
        self, mock_execute, mock_open, mock_ifaces, mock_ifaddr):
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT1, fake.IFACE_PORT2_NONE_IP,
            fake.IFACE_PORT1)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT1))

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.attach_port(instance_obj, network_obj)

        calls = (
            mock.call(*['ifdown', 'enp4s0f0']),
            mock.call(*['ifup', 'enp4s0f0'])
        )
        mock_execute.assert_has_calls(calls)

        conf = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=no
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f0
ONBOOT=yes
DEVICE=enp4s0f0
IPADDR=10.0.120.10
NETMASK=255.255.255.0

GATEWAY=10.0.120.1

'''
        handle.write.assert_called_once_with(conf)

    @mock.patch('netifaces.AF_INET', 2)
    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('os.remove')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_port_detach(
        self, mock_execute, mock_open, mock_rm, mock_ifaces, mock_ifaddr):
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT1, fake.IFACE_PORT2_NONE_IP,
            fake.IFACE_PORT1)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT1))

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.detach_port(instance_obj, network_obj)

        mock_rm.assert_called_once_with(
            '/etc/sysconfig/network-scripts/ifcfg-enp4s0f0')
        mock_execute.assert_called_once_with(*['ifdown', 'enp4s0f0'])

        conf = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=no
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f0
ONBOOT=yes
DEVICE=enp4s0f0
IPADDR=10.0.120.10
NETMASK=255.255.255.0

GATEWAY=10.0.120.1

'''
        handle.write.assert_called_once_with(conf)

    @mock.patch('netifaces.AF_INET', 2)
    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('os.remove')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_port_detach_vlan(
        self, mock_execute, mock_open, mock_rm, mock_ifaces, mock_ifaddr):
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT3, fake.IFACE_PORT2_NONE_IP,
            fake.IFACE_PORT3)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT3))

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.detach_port(instance_obj, network_obj)

        mock_rm.assert_called_once_with(
            '/etc/sysconfig/network-scripts/ifcfg-enp4s0f1.130')
        mock_execute.assert_called_once_with(*['ifdown', 'enp4s0f1.130'])

        conf = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=yes
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f1.130
ONBOOT=yes
DEVICE=enp4s0f1.130
IPADDR=10.0.10.20
NETMASK=255.255.255.0

GATEWAY=10.0.10.1


VLAN=yes
'''
        handle.write.assert_called_once_with(conf)

    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_default_route_change_params_no_old(
            self, mock_execute, mock_open, mock_ifaces, mock_ifaddr):
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT1, fake.IFACE_PORT2)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        old_network_obj = objects.NetworkObj.from_json(None)
        new_network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT2))

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.update_default_route(instance_obj,
                                    old_network_obj,
                                    new_network_obj)

        calls = (
            mock.call(*['ip', 'route', 'delete', 'default']),
            mock.call(
                *['ip', 'route', 'add', 'default', 'via',
                  '10.0.0.1', 'dev', 'enp4s0f1']),
        )
        mock_execute.assert_has_calls(calls)

        conf = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=yes
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f1
ONBOOT=yes
DEVICE=enp4s0f1
IPADDR=10.0.0.20
NETMASK=255.255.255.0

GATEWAY=10.0.0.1

'''
        handle.write.assert_called_once_with(conf)

    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_default_route_change_params_no_new(
            self, mock_execute, mock_open, mock_ifaces, mock_ifaddr):
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT1, fake.IFACE_PORT2)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        old_network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT1))
        new_network_obj = objects.NetworkObj.from_json(None)

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.update_default_route(instance_obj,
                                    old_network_obj,
                                    new_network_obj)

        mock_execute.assert_called_once_with(
            *['ip', 'route', 'delete', 'default'])

        conf = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=no
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f0
ONBOOT=yes
DEVICE=enp4s0f0
IPADDR=10.0.120.10
NETMASK=255.255.255.0

GATEWAY=10.0.120.1

'''
        handle.write.assert_called_once_with(conf)

    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_default_route_change_params_both_none(
            self, mock_execute, mock_open, mock_ifaces, mock_ifaddr):
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT1, fake.IFACE_PORT2)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        old_network_obj = objects.NetworkObj.from_json(None)
        new_network_obj = objects.NetworkObj.from_json(None)

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.update_default_route(instance_obj,
                                    old_network_obj,
                                    new_network_obj)

        mock_execute.assert_called_once_with(
            *['ip', 'route', 'delete', 'default'])

    @mock.patch('netifaces.AF_LINK', 17)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    @mock.patch('bm_instance_agent.systems.linux.distro.centos.open')
    @mock.patch('oslo_concurrency.processutils.execute')
    def test_default_route_change_params_both_exist(
            self, mock_execute, mock_open, mock_ifaces, mock_ifaddr):
        mock_execute.return_value = None, None
        mock_ifaces.return_value = ['enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = (
            fake.IFACE_PORT1, fake.IFACE_PORT2,
            fake.IFACE_PORT1, fake.IFACE_PORT2)

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))
        old_network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT1))
        new_network_obj = objects.NetworkObj.from_json(
            bm_utils.camel_obj_to_snake(fake.PORT2))

        handle = mock_open().__enter__()
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '../../../systems/linux/distro/centos_network_script.j2')
        with open(path, 'r') as f:
            handle.read.return_value = f.read()

        driver = centos.CentOSDriver()
        driver.update_default_route(instance_obj,
                                    old_network_obj,
                                    new_network_obj)

        calls = (
            mock.call(*['ip', 'route', 'delete', 'default']),
            mock.call(
                *['ip', 'route', 'add', 'default', 'via',
                  '10.0.0.1', 'dev', 'enp4s0f1'])
        )
        mock_execute.assert_has_calls(calls)

        conf_port1 = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=no
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f0
ONBOOT=yes
DEVICE=enp4s0f0
IPADDR=10.0.120.10
NETMASK=255.255.255.0

GATEWAY=10.0.120.1

'''
        conf_port2 = '''
# The Type could be ib or other, comment it, let sys to adjust the type.
# TYPE=Ethernet
PROXY_METHOD=none
BROWSER_ONLY=no
BOOTPROTO=none
DEFROUTE=yes
IPV4_FAILURE_FATAL=no
IPV6INIT=yes
IPV6_AUTOCONF=yes
IPV6_DEFROUTE=yes
IPV6_FAILURE_FATAL=no
IPV6_ADDR_GEN_MODE=stable-privacy
NAME=enp4s0f1
ONBOOT=yes
DEVICE=enp4s0f1
IPADDR=10.0.0.20
NETMASK=255.255.255.0

GATEWAY=10.0.0.1

'''
        calls = (
            mock.call(conf_port1),
            mock.call(conf_port2)
        )
        handle.write.assert_has_calls(calls)

    @mock.patch('oslo_concurrency.processutils.execute')
    def test_password_change(self, mock_execute):
        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))

        driver = centos.CentOSDriver()
        driver.update_password(instance_obj, 'username', 'newPassword')

        cmd = 'echo username:%s | chpasswd' % 'newPassword'
        mock_execute.assert_called_once_with(cmd, shell=True)

    @mock.patch('bm_instance_agent.common.utils.process_is_running')
    @mock.patch('bm_instance_agent.systems.linux.driver.open')
    @mock.patch('os.popen')
    def test_console(self, mock_popen, mock_open, mock_is_running):
        handle = mock_open().__enter__()
        mock_popen.return_value = handle
        mock_is_running.return_value = True

        driver = centos.CentOSDriver()
        ret = driver.console()

        data = {'port': 4200}
        self.assertEqual(data, ret)

        # mock_popen.assert_called_once_with(
        #     'shellinaboxd -b -t -s :SSH:127.0.0.1')

    @mock.patch('shutil.move')
    @mock.patch('os.chmod')
    @mock.patch('os.path.exists')
    @mock.patch('netifaces.AF_INET', 2)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    def test_provision_interface_conf_file_hidden(
        self, mock_ifaces, mock_ifaddr, mock_exists, mock_chmod, mock_move):
        mock_ifaces.return_value = ['eno1', 'enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = [
            fake.IFACE_PORT0, fake.IFACE_PORT1, fake.IFACE_PORT2]
        mock_exists.return_value = True

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))

        driver = centos.CentOSDriver()
        driver.ping(instance_obj)

        mock_chmod.assert_called_once_with(
            '/etc/sysconfig/network-scripts/ifcfg-eno1',
            0o000)
        mock_move.assert_called_once_with(
            '/etc/sysconfig/network-scripts/ifcfg-eno1',
            '/etc/sysconfig/network-scripts/.ifcfg-eno1')

    @mock.patch('shutil.move')
    @mock.patch('os.path.exists')
    @mock.patch('netifaces.AF_INET', 2)
    @mock.patch('netifaces.ifaddresses')
    @mock.patch('netifaces.interfaces')
    def test_provision_interface_conf_file_not_exist(
        self, mock_ifaces, mock_ifaddr, mock_exists, mock_move):
        mock_ifaces.return_value = ['eno1', 'enp4s0f0', 'enp4s0f1']
        mock_ifaddr.side_effect = [
            fake.IFACE_PORT0, fake.IFACE_PORT1, fake.IFACE_PORT2]
        mock_exists.return_value = False

        instance_obj = objects.BmInstanceObj.from_json(
            bm_utils.camel_obj_to_snake(fake.BM_INSTANCE1))

        driver = centos.CentOSDriver()
        driver.ping(instance_obj)

        mock_move.assert_not_called()
