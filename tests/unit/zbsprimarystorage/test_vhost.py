"""
Unit tests for the zbsadm-vhost shell-out wrappers in zbsprimarystorage.zbsutils.

Key contract: `zbsadm vhost create-bdev --volume <pool>/<file>_zbs_` strips the
`_zbs_` marker before libcbd opens the file, so the argument carries the suffix
while the real ZBS file name has none.
"""
import json
import shlex
from unittest.mock import patch, MagicMock

import pytest

from zbsprimarystorage import zbsutils
from zbsprimarystorage import zbsagent


def _real_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def _last_cmd():
    return zbsutils.shell.call.call_args[0][0]


class TestVhostCommands:
    @pytest.mark.parametrize("port,username,password", [(22, "root", "pwd"), (2222, "admin", "p@ss w'rd")])
    @pytest.mark.parametrize("wrapper,operation,args,options", [
        (zbsutils.create_vhost_bdev, "create-bdev", ("lpool1", "vol-uuid-1", "vhost-blk-1"),
         ["--volume", "lpool1/vol-uuid-1_zbs_", "--name", "vhost-blk-1", "--silent"]),
        (zbsutils.delete_vhost_bdev, "delete-bdev", ("vhost-blk-1",), ["--name", "vhost-blk-1", "--silent"]),
    ])
    def test_uses_host_config_without_credentials(self, port, username, password, wrapper, operation, args, options):
        with patch.object(zbsutils.shell, 'call', return_value="result"), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote):
            assert wrapper("10.0.0.9", port, username, password, *args) == "result"
            expected = [zbsutils.ZBSADM_BIN_PATH, "vhost", operation, "--host", "10.0.0.9"] + options
            assert shlex.split(_last_cmd()) == expected
            assert password not in _last_cmd()


class TestDeployClient:
    def test_preserves_ssh_credentials_and_password_quoting(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote):
            zbsutils.deploy_client("10.0.0.9", 2222, "admin", "p@ss w'rd")
            assert shlex.split(_last_cmd()) == [
                zbsutils.ZBSADM_BIN_PATH, "client", "deploy", "--host", "10.0.0.9", "--port", "2222",
                "-u", "admin", "-p", "p@ss w'rd", "--silent"]


class TestCheckVhost:
    @pytest.mark.parametrize("ready", [True, False])
    def test_checks_existing_target_without_deployment(self, ready):
        body = '{"hostIp":"10.0.0.9","sshPort":2222,"sshUsername":"admin","sshPassword":"secret"}'
        with patch.object(zbsutils, 'wait_vhost_target_ready', return_value=ready) as check, \
             patch.object(zbsutils.shell, 'call') as shell_call:
            rsp = zbsagent.jsonobject.loads(zbsagent.ZbsAgent().check_vhost(_req(body)))
            check.assert_called_once_with("10.0.0.9", 2222, "admin", "secret")
            shell_call.assert_not_called()
            assert rsp.success is ready
            if not ready:
                assert "10.0.0.9" in rsp.error
                assert "ZStone" in rsp.error

    def test_check_reports_ssh_failure_without_deployment(self):
        body = '{"hostIp":"10.0.0.9","sshPort":22,"sshUsername":"root","sshPassword":"pwd"}'
        with patch.object(zbsutils.linux, 'sshpass_run', side_effect=RuntimeError('permission denied')), \
             patch.object(zbsutils.shell, 'call') as shell_call:
            rsp = zbsagent.jsonobject.loads(zbsagent.ZbsAgent().check_vhost(_req(body)))
            assert rsp.success is False
            assert 'permission denied' in rsp.error
            shell_call.assert_not_called()

    def test_registers_check_without_deployment_endpoints(self):
        with patch.object(zbsagent.ZbsAgent.http_server, 'register_async_uri') as register:
            agent = zbsagent.ZbsAgent()
            routes = {call.args[0]: call.args[1] for call in register.call_args_list}
            assert routes['/zbs/primarystorage/vhost/check'] == agent.check_vhost
            assert '/zbs/primarystorage/vhost/deploy' not in routes
            assert '/zbs/primarystorage/vhost/destroy' not in routes

    def test_unavailable_target_fails_after_bounded_read_only_probes(self):
        body = '{"hostIp":"10.0.0.9","sshPort":22,"sshUsername":"root","sshPassword":"pwd"}'
        with patch.object(zbsutils.linux, 'sshpass_run', return_value=(1, "", "")) as ssh, \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils.time, 'sleep'), \
             patch.object(zbsutils.shell, 'call') as shell_call:
            rsp = zbsagent.jsonobject.loads(zbsagent.ZbsAgent().check_vhost(_req(body)))
            assert rsp.success is False
            assert ssh.call_count == 40
            assert all(call.args[2].startswith('docker ps ') for call in ssh.call_args_list)
            shell_call.assert_not_called()

    def test_ready_wait_checks_container_and_admin_sock(self):
        calls = {'n': 0}

        def ssh(*args, **kwargs):
            calls['n'] += 1
            return (0 if calls['n'] == 3 else 1, "", "")

        with patch.object(zbsutils.linux, 'sshpass_run', side_effect=ssh) as sshpass, \
             patch.object(zbsutils.time, 'sleep') as sleep:
            assert zbsutils.wait_vhost_target_ready("10.0.0.9", 2222, "root", "pwd",
                                                    retries=3, interval=0.1) is True

            cmd = sshpass.call_args[0][2]
            assert "docker ps" in cmd
            assert "name=^/zbsvhost-10.0.0.9$" in cmd
            assert "/var/zbsvhost/sockets/admin.sock" in cmd
            assert sleep.call_count == 2


class TestVhostSocketPath:
    def test_socket_path_is_dir_slash_bdev_name(self):
        assert zbsutils.vhost_socket_path("vhost-blk-1") == \
            zbsutils.VHOST_SOCKET_DIR + "/vhost-blk-1"


_OK = '{"success": true, "error": {"code": 0, "message": ""}}'
_FAIL = '{"success": false, "error": {"code": 410032, "message": "boom"}}'


def _req(body):
    return {zbsagent.http.REQUEST_BODY: body}


class TestCreateVhostBdevHandler:
    def test_creates_bdev_and_returns_socket_path(self):
        body = ('{"hostIp": "10.0.0.9", "sshPort": 22, "sshUsername": "root", '
                '"sshPassword": "pwd", "logicalPool": "lpool1", "volume": "vol-uuid-1", '
                '"bdevName": "vhost-blk-1"}')
        with patch.object(zbsagent.zbsutils, 'create_vhost_bdev', return_value=_OK) as cb:
            out = zbsagent.ZbsAgent.create_vhost_bdev(MagicMock(), _req(body))
            cb.assert_called_once_with("10.0.0.9", 22, "root", "pwd",
                                       "lpool1", "vol-uuid-1", "vhost-blk-1")
            r = zbsagent.jsonobject.loads(out)
            assert r.success is True
            assert r.socketPath == zbsutils.VHOST_SOCKET_DIR + "/vhost-blk-1"

    def test_failure_is_reported_not_swallowed(self):
        body = ('{"hostIp": "10.0.0.9", "sshPort": 22, "sshUsername": "root", '
                '"sshPassword": "pwd", "logicalPool": "lpool1", "volume": "vol-uuid-1", '
                '"bdevName": "vhost-blk-1"}')
        with patch.object(zbsagent.zbsutils, 'create_vhost_bdev', return_value=_FAIL):
            out = zbsagent.ZbsAgent.create_vhost_bdev(MagicMock(), _req(body))
            r = zbsagent.jsonobject.loads(out)
            assert r.success is False
            assert "boom" in r.error


class TestDeleteVhostBdevHandler:
    def test_deletes_named_bdev(self):
        body = ('{"hostIp": "10.0.0.9", "sshPort": 22, "sshUsername": "root", '
                '"sshPassword": "pwd", "bdevName": "vhost-blk-1"}')
        with patch.object(zbsagent.zbsutils, 'delete_vhost_bdev', return_value=_OK) as db:
            out = zbsagent.ZbsAgent.delete_vhost_bdev(MagicMock(), _req(body))
            db.assert_called_once_with("10.0.0.9", 22, "root", "pwd", "vhost-blk-1")
            assert zbsagent.jsonobject.loads(out).success is True
