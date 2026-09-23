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
    @pytest.mark.parametrize("wrapper,operation,args,options", [
        (zbsutils.create_vhost_bdev, "create-bdev", ("lpool1", "vol-uuid-1", "vhost-blk-1"),
         ["--volume", "lpool1/vol-uuid-1_zbs_", "--name", "vhost-blk-1", "--silent"]),
        (zbsutils.delete_vhost_bdev, "delete-bdev", ("vhost-blk-1",), ["--name", "vhost-blk-1", "--silent"]),
    ])
    def test_uses_host_config_without_credentials(self, wrapper, operation, args, options):
        with patch.object(zbsutils.shell, 'call', return_value="result"), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote):
            assert wrapper("10.0.0.9", *args) == "result"
            expected = [zbsutils.ZBSADM_BIN_PATH, "vhost", operation, "--host", "10.0.0.9"] + options
            assert shlex.split(_last_cmd()) == expected


class TestDeployClient:
    def test_preserves_ssh_credentials_and_password_quoting(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote):
            zbsutils.deploy_client("10.0.0.9", 2222, "admin", "p@ss w'rd")
            assert shlex.split(_last_cmd()) == [
                zbsutils.ZBSADM_BIN_PATH, "client", "deploy", "--host", "10.0.0.9", "--port", "2222",
                "-u", "admin", "-p", "p@ss w'rd", "--silent"]


def _status(vhosts, success=True, code=0):
    return json.dumps({"success": success, "error": {"code": code, "message": "query failed"}, "vhosts": vhosts})


_RUNNING = _status([{"ip": "10.0.0.9", "status": "running"}])
_STOPPED = _status([{"ip": "10.0.0.9", "status": "stopped"}])


class TestVhostStatus:
    def test_status_uses_target_host_without_container_name_or_credentials(self):
        with patch.object(zbsutils.shell, 'call', return_value=_RUNNING), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils.linux, 'sshpass_run') as ssh:
            assert zbsutils.get_vhost_target_status("10.0.0.9") == "running"
            assert shlex.split(_last_cmd()) == [
                "timeout", "-k", "5", "15", zbsutils.ZBSADM_BIN_PATH,
                "vhost", "status", "--host", "10.0.0.9", "--silent"]
            ssh.assert_not_called()

    @pytest.mark.parametrize("records,running", [
        ([{"ip": "10.0.0.9", "status": "running"}], True),
        ([{"ip": "10.0.0.9", "status": "stopped"}], False),
        ([{"ip": "10.0.0.9", "status": None}], False),
        ([{"ip": "10.0.0.90", "status": "running"}], False),
        ([{"ip": "10.0.0.8", "status": "running"}, {"ip": "10.0.0.9", "status": "stopped"}], False),
        ([], False),
    ])
    def test_matches_only_requested_host(self, records, running):
        with patch.object(zbsutils.shell, 'call', return_value=_status(records)):
            assert zbsutils.is_vhost_target_running("10.0.0.9") is running

    @pytest.mark.parametrize("output", [
        _status([], success=False), _status([], code=42), "not json", "{}", "null", "[]",
        '{"success":true,"error":{"code":0}}',
        '{"success":true,"error":{"code":0},"vhosts":{}}',
        _status([{"status": "running"}]), _status([{"ip": "10.0.0.9"}]),
    ])
    def test_failed_or_malformed_query_is_not_healthy(self, output):
        with patch.object(zbsutils.shell, 'call', return_value=output):
            with pytest.raises(Exception):
                zbsutils.is_vhost_target_running("10.0.0.9")

    @pytest.mark.parametrize("ip", [None, ""])
    def test_missing_host_does_not_query_all_hosts(self, ip):
        with patch.object(zbsutils.shell, 'call') as query:
            with pytest.raises(ValueError, match="hostIp"):
                zbsutils.is_vhost_target_running(ip)
            query.assert_not_called()


class TestCheckVhost:
    @pytest.mark.parametrize("ready", [True, False])
    def test_checks_existing_target_without_deployment(self, ready):
        body = '{"hostIp":"10.0.0.9"}'
        with patch.object(zbsutils, 'wait_vhost_target_ready', return_value=ready) as check:
            rsp = zbsagent.jsonobject.loads(zbsagent.ZbsAgent().check_vhost(_req(body)))
            check.assert_called_once_with("10.0.0.9")
            assert rsp.success is ready
            if not ready:
                assert "10.0.0.9" in rsp.error
                assert "ZStone" in rsp.error

    def test_registers_mds_health_and_existing_check(self):
        with patch.object(zbsagent.ZbsAgent.http_server, 'register_async_uri') as register:
            agent = zbsagent.ZbsAgent()
            routes = {call.args[0]: call.args[1] for call in register.call_args_list}
            assert routes['/zbs/primarystorage/vhost/check'] == agent.check_vhost
            assert routes['/zbs/primarystorage/vhost/target/health'] == agent.check_vhost_target_health
            assert '/zbs/primarystorage/vhost/deploy' not in routes
            assert '/zbs/primarystorage/vhost/destroy' not in routes

    def test_ready_wait_retries_then_recovers_without_ssh_credentials(self):
        with patch.object(zbsutils.shell, 'call', side_effect=[_STOPPED, _STOPPED, _RUNNING]) as query, \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils.linux, 'sshpass_run') as ssh, \
             patch.object(zbsutils.time, 'sleep') as sleep:
            assert zbsutils.wait_vhost_target_ready("10.0.0.9", retries=3) is True
            assert query.call_count == 3
            assert sleep.call_count == 2
            assert all("docker" not in call.args[0] for call in query.call_args_list)
            ssh.assert_not_called()

    def test_unavailable_target_stops_after_last_attempt_without_sleep(self):
        with patch.object(zbsutils.shell, 'call', return_value=_STOPPED) as query, \
             patch.object(zbsutils.time, 'sleep') as sleep:
            assert zbsutils.wait_vhost_target_ready("10.0.0.9", retries=3) is False
            assert query.call_count == 3
            assert sleep.call_count == 2

    def test_readiness_reserves_kill_time_within_twenty_second_budget(self):
        now = [100.0]

        def query_status(command):
            soft_timeout = float(shlex.split(command)[3])
            assert soft_timeout + 5 <= 120 - now[0]
            now[0] += 6
            return _STOPPED

        def sleep(seconds):
            now[0] += seconds

        with patch.object(zbsutils.shell, 'call', side_effect=query_status) as query, \
             patch.object(zbsutils.time, 'time', side_effect=lambda: now[0]), \
             patch.object(zbsutils.time, 'sleep', side_effect=sleep):
            assert zbsutils.wait_vhost_target_ready("10.0.0.9") is False
            assert query.call_count == 3
            assert now[0] <= 120


class TestVhostHealthHandler:
    @pytest.mark.parametrize("output,running", [(_RUNNING, True), (_STOPPED, False), (_status([]), False)])
    def test_health_queries_status_once(self, output, running):
        with patch.object(zbsutils.shell, 'call', return_value=output) as query, \
             patch.object(zbsutils.time, 'sleep') as sleep:
            response = zbsagent.ZbsAgent().check_vhost_target_health(_req('{"hostIp":"10.0.0.9"}'))
            rsp = zbsagent.jsonobject.loads(response)
            assert rsp.success is True
            assert rsp.targetRunning is running
            query.assert_called_once()
            sleep.assert_not_called()

    @pytest.mark.parametrize("handler", ["check_vhost", "check_vhost_target_health"])
    @pytest.mark.parametrize("error", ["exit code 1: connection failed", "exit code 124: timed out"])
    def test_query_exception_uses_replyerror_without_retry(self, handler, error):
        with patch.object(zbsutils.shell, 'call', side_effect=RuntimeError(error)) as query:
            response = getattr(zbsagent.ZbsAgent(), handler)(_req('{"hostIp":"10.0.0.9"}'))
            rsp = zbsagent.jsonobject.loads(response)
            assert rsp.success is False
            assert error in rsp.error
            query.assert_called_once()

    @pytest.mark.parametrize("handler", ["check_vhost", "check_vhost_target_health"])
    @pytest.mark.parametrize("body", ['{}', '{"hostIp":""}', '{"hostIp":null}'])
    def test_missing_host_is_agent_error_without_query(self, handler, body):
        with patch.object(zbsutils.shell, 'call') as query:
            rsp = zbsagent.jsonobject.loads(getattr(zbsagent.ZbsAgent(), handler)(_req(body)))
            assert rsp.success is False
            assert "hostIp" in rsp.error
            query.assert_not_called()

    @pytest.mark.parametrize("handler", ["check_vhost", "check_vhost_target_health"])
    @pytest.mark.parametrize("output", [_status([], success=False), _status([], code=42), "not json", "{}"])
    def test_query_contract_error_is_agent_failure(self, handler, output):
        with patch.object(zbsutils.shell, 'call', return_value=output) as query:
            rsp = zbsagent.jsonobject.loads(getattr(zbsagent.ZbsAgent(), handler)(_req('{"hostIp":"10.0.0.9"}')))
            assert rsp.success is False
            assert rsp.error
            if "query failed" in output:
                assert "query failed" in rsp.error
            query.assert_called_once()


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
        body = ('{"hostIp": "10.0.0.9", "logicalPool": "lpool1", "volume": "vol-uuid-1", '
                '"bdevName": "vhost-blk-1"}')
        with patch.object(zbsagent.zbsutils, 'create_vhost_bdev', return_value=_OK) as cb:
            out = zbsagent.ZbsAgent.create_vhost_bdev(MagicMock(), _req(body))
            cb.assert_called_once_with("10.0.0.9", "lpool1", "vol-uuid-1", "vhost-blk-1")
            r = zbsagent.jsonobject.loads(out)
            assert r.success is True
            assert r.socketPath == zbsutils.VHOST_SOCKET_DIR + "/vhost-blk-1"

    def test_failure_is_reported_not_swallowed(self):
        body = ('{"hostIp": "10.0.0.9", "logicalPool": "lpool1", "volume": "vol-uuid-1", '
                '"bdevName": "vhost-blk-1"}')
        with patch.object(zbsagent.zbsutils, 'create_vhost_bdev', return_value=_FAIL):
            out = zbsagent.ZbsAgent.create_vhost_bdev(MagicMock(), _req(body))
            r = zbsagent.jsonobject.loads(out)
            assert r.success is False
            assert "boom" in r.error


class TestDeleteVhostBdevHandler:
    def test_deletes_named_bdev(self):
        body = '{"hostIp": "10.0.0.9", "bdevName": "vhost-blk-1"}'
        with patch.object(zbsagent.zbsutils, 'delete_vhost_bdev', return_value=_OK) as db:
            out = zbsagent.ZbsAgent.delete_vhost_bdev(MagicMock(), _req(body))
            db.assert_called_once_with("10.0.0.9", "vhost-blk-1")
            assert zbsagent.jsonobject.loads(out).success is True
