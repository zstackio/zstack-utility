import mock

from bm_instance_agent import exception as bm_exception
from bm_instance_agent import manager
from bm_instance_agent.systems import base as driver_base
from bm_instance_agent.tests import base
from bm_instance_agent.tests.unit import fake


class TestManager(base.TestCase):

    @mock.patch('bm_instance_agent.systems.base.SystemDriverBase.ping')
    @mock.patch('bm_instance_agent.systems.base.SystemDriverBase.'
                'update_password')
    @mock.patch('bm_instance_agent.manager.AgentManager._load_driver')
    def test_ping_bm_uuid_not_corrent(self,
                                      mock_driv,
                                      mock_driv_update_password,
                                      mock_ping):
        mock_driv.return_value = driver_base.SystemDriverBase()
        mock_driv_update_password.return_value = None
        mock_ping.return_value = None

        mgmt = manager.AgentManager()
        mgmt.ping(fake.BM_INSTANCE1)
        self.assertRaises(bm_exception.BmInstanceUuidConflict,
                          mgmt.update_password,
                          fake.BM_INSTANCE2,
                          'newPassword')
        manager.DRIVER = None

    @mock.patch('os.name', 'posix')
    @mock.patch('cpuinfo.get_cpu_info')
    @mock.patch('distro.major_version')
    @mock.patch('distro.id')
    def test_load_driver_centos_system(
        self, mock_id, mock_major, mock_cpuinfo):
        mock_id.return_value = 'centos'
        mock_major.return_value = '8'
        mock_cpuinfo.return_value = fake.CPUINFO_X86

        mgmt = manager.AgentManager()
        self.assertEqual('centos', mgmt.driver.driver_name)
        manager.DRIVER = None

    @mock.patch('os.name', 'posix')
    @mock.patch('cpuinfo.get_cpu_info')
    @mock.patch('distro.major_version')
    @mock.patch('distro.id')
    def test_load_driver_centos_v7_x86(
        self, mock_id, mock_major, mock_cpuinfo):
        mock_id.return_value = 'centos'
        mock_major.return_value = '7'
        mock_cpuinfo.return_value = fake.CPUINFO_X86

        mgmt = manager.AgentManager()
        self.assertEqual('centos_v7_x86', mgmt.driver.driver_name)
        manager.DRIVER = None

    @mock.patch('os.name', 'posix')
    @mock.patch('cpuinfo.get_cpu_info')
    @mock.patch('distro.major_version')
    @mock.patch('distro.id')
    def test_load_driver_centos_v7_arm(
        self, mock_id, mock_major, mock_cpuinfo):
        mock_id.return_value = 'centos'
        mock_major.return_value = '7'
        mock_cpuinfo.return_value = fake.CPUINFO_ARM

        mgmt = manager.AgentManager()
        self.assertEqual('centos_v7_arm', mgmt.driver.driver_name)
        manager.DRIVER = None

    @mock.patch('os.name', 'posix')
    @mock.patch('cpuinfo.get_cpu_info')
    @mock.patch('distro.major_version')
    @mock.patch('distro.id')
    def test_load_driver_linux(
        self, mock_id, mock_major, mock_cpuinfo):
        mock_id.return_value = 'ubuntu'
        mock_major.return_value = '18'
        mock_cpuinfo.return_value = fake.CPUINFO_X86

        mgmt = manager.AgentManager()
        self.assertEqual('linux', mgmt.driver.driver_name)
        manager.DRIVER = None

    @mock.patch('os.name', 'nt')
    @mock.patch('cpuinfo.get_cpu_info')
    @mock.patch('distro.major_version')
    @mock.patch('distro.id')
    def test_load_driver_windows_system(
        self, mock_id, mock_major, mock_cpuinfo):
        mock_id.return_value = ''
        mock_major.return_value = ''
        mock_cpuinfo.return_value = fake.CPUINFO_X86

        mgmt = manager.AgentManager()
        self.assertEqual('windows', mgmt.driver.driver_name)
        manager.DRIVER = None
