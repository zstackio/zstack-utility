import time

from kvmagent.test.utils import pytest_utils
from kvmagent.test.utils.stub import *
from kvmagent.plugins.ha_plugin import HaPlugin, logger
from zstacklib.test.utils import env
from zstacklib.utils.http import REQUEST_BODY
from zstacklib.utils import bash, jsonobject, shell
from unittest import TestCase, mock


init_kvmagent()

PKG_NAME = __name__

__ENV_SETUP__ = {
    'self': {}
}


## describe: case will manage by ztest
class TestHaPreFenceVmOnSuspectHost(TestCase, pytest_utils.PytestExtension):
    @classmethod
    def setUpClass(cls):
        cls.ha_plugin = HaPlugin()
        cls.vm_uuid = 'zstac83890-fence-ssh-kill-0001'
        cls.workdir = '/tmp/zstac83890-fence'

    def _cleanup_qemu_like_process(self):
        bash.bash_ro("pkill -9 -f '[q]emu-[ks].*%s' 2>/dev/null || true" % self.vm_uuid)
        bash.bash_ro("rm -rf %s" % self.workdir)

    def _qemu_like_process_exists(self):
        r, o = bash.bash_ro("pgrep -f '[q]emu-[ks].*%s'" % self.vm_uuid)
        return r == 0 and o.strip() != ''

    def _wait_qemu_like_process_started(self):
        for _ in range(20):
            if self._qemu_like_process_exists():
                return
            time.sleep(0.5)
        self.fail('failed to start qemu-like process for vm[%s]' % self.vm_uuid)

    def _wait_qemu_like_process_killed(self):
        for _ in range(20):
            if not self._qemu_like_process_exists():
                return
            time.sleep(0.5)
        self.fail('qemu-like process still alive after pre-fence for vm[%s]' % self.vm_uuid)

    def _start_qemu_like_process(self):
        bash.bash_errorout('mkdir -p %s' % self.workdir)
        bash.bash_errorout(
            "nohup bash -c 'exec -a \"qemu-system-x86_64 -name guest=%s\" sleep 300' "
            "> %s/qemu-like.log 2>&1 &" % (self.vm_uuid, self.workdir)
        )
        self._wait_qemu_like_process_started()

    def _make_request_without_logging_private_key(self, body):
        return {
            REQUEST_BODY: jsonobject.dumps(body, include_protected_attr=True)
        }

    def _get_current_host_ssh_ip(self):
        current_host = env.get_test_environment_metadata()
        target_ip = current_host.get('ip', '') if hasattr(current_host, 'get') else ''
        target_ip = target_ip.strip() if target_ip else ''
        if target_ip:
            return target_ip

        r, o = bash.bash_ro(
            "ip -4 route get 1.1.1.1 | awk '{for (i=1; i<=NF; i++) if ($i == \"src\") {print $(i+1); exit}}'"
        )
        if r == 0 and o.strip():
            return o.strip().splitlines()[0]

        return '127.0.0.1'

    def test_pre_fence_ssh_unreachable_classification(self):
        self.assertTrue(self.ha_plugin._is_pre_fence_ssh_unreachable(
            255, '', 'ssh: connect to host 192.0.2.10 port 22: Connection timed out'))
        self.assertTrue(self.ha_plugin._is_pre_fence_ssh_unreachable(
            255, '', 'ssh: connect to host 192.0.2.10 port 22: No route to host'))
        self.assertTrue(self.ha_plugin._is_pre_fence_ssh_unreachable(
            255, '', 'ssh: connect to host 192.0.2.10 port 22: Connection refused'))
        self.assertTrue(self.ha_plugin._is_pre_fence_ssh_unreachable(
            255, '', 'ssh: connect to host fd54:8970:2::10 port 22: Network is unreachable'))

        self.assertFalse(self.ha_plugin._is_pre_fence_ssh_unreachable(
            255, '', 'Permission denied (publickey,password).'))
        self.assertFalse(self.ha_plugin._is_pre_fence_ssh_unreachable(
            255, '', 'Authentication failed.'))
        self.assertFalse(self.ha_plugin._is_pre_fence_ssh_unreachable(
            1, '', 'local command failed'))
        self.assertFalse(self.ha_plugin._is_pre_fence_ssh_unreachable(
            124, '', 'Network is unreachable'))

    @pytest_utils.ztest_decorater
    def test_pre_fence_tries_ips_until_success(self):
        dead = (0, 'QEMU_DEAD', '')
        unreachable = (255, '', 'Connection timed out')
        network_unreachable = (255, '', 'Network is unreachable')
        cases = [
            ([unreachable, dead], True, 2),
            ([dead, dead], True, 1),
            ([unreachable, unreachable], True, 2),
            ([dead, network_unreachable], True, 1),
            ([network_unreachable, dead], True, 2),
            ([network_unreachable, network_unreachable], True, 2),
            ([dead, (2, 'QEMU_ALIVE', '')], True, 1),
            ([(2, 'QEMU_ALIVE', ''), dead], True, 2),
            ([(255, '', 'Permission denied'), dead], True, 2),
            ([(124, '', ''), dead], True, 2),
            ([RuntimeError('ssh execution failed'), dead], True, 2),
            ([(2, 'QEMU_ALIVE', ''), unreachable], False, 2),
        ]
        for target_ips in [['192.0.2.10', '198.51.100.10'],
                           ['192.0.2.10', 'fd54:8970:2::10'],
                           ['fd54:8970:2::10', 'fd54:8970:2::11']]:
            for results, success, call_count in cases:
                with mock.patch.object(shell, 'ShellCmd') as ssh:
                    ssh.side_effect = [result if isinstance(result, Exception) else
                                       mock.Mock(return_code=result[0], stdout=result[1], stderr=result[2])
                                       for result in results]
                    rsp = jsonobject.loads(self.ha_plugin.fence_vm_on_suspect_host(
                        self._make_request_without_logging_private_key({
                            'vmUuid': self.vm_uuid,
                            'targetHostUuid': 'pre-fence-target-host',
                            'targetHostIp': target_ips[0],
                            'targetHostExtraIps': target_ips[1:],
                        })))
                    self.assertEqual(success, rsp.success, str(results))
                    self.assertEqual(call_count, ssh.call_count, str(results))
                    self.assertIn('root@' + target_ips[0], ssh.call_args_list[0][0][0])
                    if call_count == 2:
                        self.assertIn('root@' + target_ips[1], ssh.call_args_list[1][0][0])

    @pytest_utils.ztest_decorater
    def test_pre_fence_accepts_legacy_target_ip(self):
        for target_ip in ['192.0.2.10', 'fd54:8970:2::10', ' fd54:8970:2::10 ', 'host.example']:
            with mock.patch.object(shell, 'ShellCmd') as ssh:
                ssh.return_value = mock.Mock(return_code=0, stdout='QEMU_DEAD', stderr='')
                rsp = jsonobject.loads(self.ha_plugin.fence_vm_on_suspect_host(
                    self._make_request_without_logging_private_key({
                        'vmUuid': self.vm_uuid,
                        'targetHostUuid': 'pre-fence-target-host',
                        'targetHostIp': target_ip,
                    })))
                self.assertTrue(rsp.success)
                self.assertEqual(1, ssh.call_count)
                command = ssh.call_args[0][0]
                self.assertIn('root@' + target_ip.strip(), command)

    @pytest_utils.ztest_decorater
    def test_pre_fence_accepts_only_extra_ips(self):
        with mock.patch.object(shell, 'ShellCmd') as ssh:
            ssh.return_value = mock.Mock(return_code=0, stdout='QEMU_DEAD', stderr='')
            rsp = jsonobject.loads(self.ha_plugin.fence_vm_on_suspect_host(
                self._make_request_without_logging_private_key({
                    'vmUuid': self.vm_uuid,
                    'targetHostUuid': 'pre-fence-target-host',
                    'targetHostExtraIps': ['192.0.2.10'],
                })))
            self.assertTrue(rsp.success)
            self.assertEqual(1, ssh.call_count)
            self.assertIn('root@192.0.2.10', ssh.call_args[0][0])

    @pytest_utils.ztest_decorater
    def test_pre_fence_preserves_all_failure_reasons(self):
        results = [(1, 'REMOTE_FAILED', ''), (255, '', 'Permission denied (publickey)')]
        for outcomes in [results, [RuntimeError('ssh execution failed'), (2, 'QEMU_ALIVE', '')],
                         [(255, '', 'Permission denied'), (1, 'REMOTE_FAILED', '')]]:
            with mock.patch.object(shell, 'ShellCmd') as ssh, \
                    mock.patch.object(logger, 'error') as error_log:
                ssh.side_effect = [result if isinstance(result, Exception) else
                                   mock.Mock(return_code=result[0], stdout=result[1], stderr=result[2])
                                   for result in outcomes]
                rsp = jsonobject.loads(self.ha_plugin.fence_vm_on_suspect_host(
                    self._make_request_without_logging_private_key({
                        'vmUuid': self.vm_uuid,
                        'targetHostUuid': 'pre-fence-target-host',
                        'targetHostIp': '192.0.2.10',
                        'targetHostExtraIps': ['fd54:8970:2::10'],
                    })))
                self.assertFalse(rsp.success)
                self.assertEqual(2, ssh.call_count)
                for ip in ['192.0.2.10', 'fd54:8970:2::10']:
                    self.assertIn(ip, rsp.error)
                if isinstance(outcomes[0], Exception):
                    self.assertIn('ssh execution failed', rsp.error)
                    self.assertIn('qemu still alive', rsp.error)
                else:
                    self.assertIn('REMOTE_FAILED', rsp.error)
                    self.assertIn('Permission denied', rsp.error)
                self.assertEqual(3, error_log.call_count)

    @pytest_utils.ztest_decorater
    def test_pre_fence_rejects_missing_targets(self):
        for body in [{'vmUuid': self.vm_uuid, 'targetHostUuid': 'pre-fence-target-host',
                      'targetHostExtraIps': []},
                     {'vmUuid': self.vm_uuid, 'targetHostUuid': 'pre-fence-target-host', 'targetHostIp': ' '}]:
            with mock.patch.object(shell, 'ShellCmd') as ssh:
                rsp = jsonobject.loads(self.ha_plugin.fence_vm_on_suspect_host(
                    self._make_request_without_logging_private_key(body)))
                self.assertFalse(rsp.success)
                ssh.assert_not_called()

    @pytest_utils.ztest_decorater
    def test_fence_vm_on_suspect_host_ssh_kills_qemu_process(self):
        target_ip = self._get_current_host_ssh_ip()
        self._cleanup_qemu_like_process()
        try:
            self._start_qemu_like_process()

            rsp = self.ha_plugin.fence_vm_on_suspect_host(self._make_request_without_logging_private_key({
                'vmUuid': self.vm_uuid,
                'targetHostUuid': 'zstac83890-target-host',
                'targetHostIp': target_ip,
                'targetHostUsername': 'root',
                'targetHostPrivateKey': env.get_private_key(),
                'targetHostSshPort': 22,
                'sshTimeoutSec': 20
            }))
            rsp = jsonobject.loads(rsp)

            self.assertEqual(True, rsp.success, rsp.error)
            self._wait_qemu_like_process_killed()
        finally:
            self._cleanup_qemu_like_process()
