import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bm_instance_agent import exception, manager
from bm_instance_agent.systems.linux.distro import kylin


class TestKylinProvisionBondDetach(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config = self.root / 'bonding.conf'
        self.original_config = (
            'add_dracutmodules+=" network "\n'
            'kernel_cmdline+=" bond=bond0:eth0,eth1:mode=1 ip=bond0:dhcp bootdev=bond0"\n'
            'kernel_cmdline+=" bond=bond0:eth0,eth1:mode=1 ip=bond0:dhcp"\n'
        )
        self.config.write_text(self.original_config)
        self.port = SimpleNamespace(
            type='bond', PORT_TYPE_BOND='bond', PORT_TYPE_PHY='physical',
            iface_name='bond0', mac='00:11:22:33:44:55',
            ip_address='192.0.2.10', netmask='255.255.255.0',
            gateway='192.0.2.1', default_route=False, vlan_if_name=None,
        )
        self.instance = SimpleNamespace(provision_mac=self.port.mac)
        self.network = SimpleNamespace(ports=[self.port])
        self.driver = kylin.KylinDriver()
        self.driver._detach_port = mock.Mock()
        self.driver._attach_port = mock.Mock()
        patches = [
            mock.patch.object(kylin, 'BOND_DRACUT_CONFIG_PATH', str(self.config), create=True),
            mock.patch.object(kylin.agent_utils, 'get_interface_by_mac', return_value='eth0'),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    @mock.patch.object(kylin.subprocess, 'check_call')
    def test_detach_restores_physical_ip_and_updates_boot_config(self, build):
        self.assertIs(self.driver.detach_port(self.instance, self.network), True)
        build.assert_called_once_with(['timeout', '-k', '5', '300', 'dracut', '-f'])
        physical = self.driver._attach_port.call_args.args[0]
        self.assertEqual((physical.type, physical.iface_name), ('physical', 'eth0'))
        self.assertEqual((physical.ip_address, physical.gateway), ('192.0.2.10', '192.0.2.1'))
        self.assertFalse(physical.default_route)
        self.assertEqual((self.port.type, self.port.iface_name), ('bond', 'bond0'))
        self.assertEqual(self.config.read_text(),
                         'add_dracutmodules+=" network "\n'
                         'kernel_cmdline+=" ip=eth0:dhcp bootdev=eth0"\n')

    @mock.patch.object(kylin.subprocess, 'check_call')
    def test_dracut_failure_restores_bond_and_config(self, build):
        build.side_effect = subprocess.CalledProcessError(1, ['dracut'])
        with self.assertRaises(subprocess.CalledProcessError):
            self.driver.detach_port(self.instance, self.network)
        self.assertEqual(self.config.read_text(), self.original_config)
        self.assertIs(self.driver._attach_port.call_args.args[0], self.port)
        self.assertEqual(self.driver._attach_port.call_count, 2)

    @mock.patch.object(kylin.subprocess, 'check_call')
    def test_dracut_timeout_restores_network_and_config(self, build):
        build.side_effect = subprocess.CalledProcessError(124, ['timeout', '300', 'dracut'])
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self.driver.detach_port(self.instance, self.network)
        self.assertEqual(error.exception.returncode, 124)
        self.assertEqual(self.config.read_text(), self.original_config)
        self.assertIs(self.driver._attach_port.call_args.args[0], self.port)

    @mock.patch.object(kylin.subprocess, 'check_call')
    def test_physical_restore_failure_rebuilds_original_bond(self, build):
        self.driver._attach_port.side_effect = [OSError('ifup failed'), None]
        with self.assertRaises(OSError):
            self.driver.detach_port(self.instance, self.network)
        self.assertIs(self.driver._attach_port.call_args.args[0], self.port)
        self.assertEqual(self.config.read_text(), self.original_config)
        build.assert_not_called()

    @mock.patch.object(kylin.subprocess, 'check_call')
    def test_new_boot_config_is_removed_when_build_fails(self, build):
        self.config.unlink()
        build.side_effect = subprocess.CalledProcessError(1, ['dracut'])
        with self.assertRaises(subprocess.CalledProcessError):
            self.driver.detach_port(self.instance, self.network)
        self.assertFalse(self.config.exists())

    def test_non_primary_bond_remains_unsupported(self):
        self.instance.provision_mac = '00:11:22:33:44:66'
        with self.assertRaises(exception.NewtorkInterfaceConfigParasInvalid):
            self.driver.detach_port(self.instance, self.network)
        self.driver._detach_port.assert_not_called()

    def test_physical_nic_uses_existing_detach_path(self):
        self.port.type = 'physical'
        self.assertIsNot(self.driver.detach_port(self.instance, self.network), True)
        self.driver._detach_port.assert_called_once_with(self.port)
        self.driver._attach_port.assert_not_called()

    @mock.patch.object(kylin.subprocess, 'check_call')
    def test_repeated_attach_after_detach_writes_one_bond_cmdline(self, build):
        self.driver.detach_port(self.instance, self.network)
        self.driver._read_slaves_from_sys = mock.Mock(return_value='eth0,eth1')
        self.driver._read_bonding_opts_from_ifcfg = mock.Mock(return_value='mode=1')
        exists = kylin.os.path.exists
        with mock.patch.object(kylin.os.path, 'exists', side_effect=lambda path:
                               path == '/etc/sysconfig/network-scripts/ifcfg-bond0' or exists(path)):
            for _ in range(3):
                self.driver.attach_port(self.instance, self.network)
                self.assertEqual(self.config.read_text(),
                                 'add_dracutmodules+=" network "\n'
                                 'kernel_cmdline+=" bond=bond0:eth0,eth1:mode=1 '
                                 'ip=bond0:dhcp bootdev=bond0"\n')

    @mock.patch.object(kylin.subprocess, 'check_call')
    def test_network_detach_failure_restores_original_bond(self, build):
        self.driver._detach_port.side_effect = OSError('ifdown failed')
        with self.assertRaisesRegex(OSError, 'ifdown failed'):
            self.driver.detach_port(self.instance, self.network)
        self.driver._attach_port.assert_called_once_with(self.port)
        build.assert_not_called()

    @mock.patch.object(kylin.subprocess, 'check_call')
    def test_restore_failure_reports_both_errors(self, build):
        build.side_effect = subprocess.CalledProcessError(1, ['dracut'])
        self.driver._attach_port.side_effect = [None, OSError('Bond restore failed')]
        with self.assertRaisesRegex(RuntimeError, 'dracut.*Bond restore failed'):
            self.driver.detach_port(self.instance, self.network)


class TestManagerProvisionNicRestore(unittest.TestCase):
    def test_restore_is_skipped_only_for_explicit_true(self):
        for driver_result in (None, False, True):
            with self.subTest(driver_result=driver_result):
                port = SimpleNamespace(mac='00:11:22:33:44:55', type='bond', iface_name='bond0')
                instance = SimpleNamespace(uuid='instance', provision_mac=port.mac)
                network = SimpleNamespace(ports=[port])
                agent = manager.AgentManager.__new__(manager.AgentManager)
                agent.driver = mock.Mock()
                agent.driver.detach_port.return_value = driver_result
                agent._check_uuid_corrent = mock.Mock()
                with mock.patch.object(manager.BmInstanceObj, 'from_json', return_value=instance), \
                        mock.patch.object(manager.NetworkObj, 'from_json', return_value=network), \
                        mock.patch.object(manager.bm_utils, 'get_interface_by_mac', return_value='eth0'):
                    agent.detach_port({}, {})
                if driver_result is True:
                    agent.driver.attach_port.assert_not_called()
                    self.assertEqual(port.type, 'bond')
                    continue
                agent.driver.attach_port.assert_called_once_with(instance, network)
                self.assertEqual((port.type, port.iface_name), ('physical', 'eth0'))
