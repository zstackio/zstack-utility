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


def _lscpu(*rows):
    return "CPU NODE SOCKET CORE\n%s\n" % "\n".join(rows)


class TestVhostCommands:
    @pytest.mark.parametrize("port,username,password", [(22, "root", "pwd"), (2222, "admin", "p@ss w'rd")])
    @pytest.mark.parametrize("wrapper,operation,args,options", [
        (zbsutils.deploy_vhost, "deploy", ("[4,5,6,7]", 2, "/dev/hugepages2m"),
         ["--cpuset", "[4,5,6,7]", "--silent", "--hugepage-size", "2", "--hugepage-dir", "/dev/hugepages2m"]),
        (zbsutils.destroy_vhost, "destroy", (), ["--silent"]),
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


class TestVhostAutoCpuset:
    def test_selects_four_cpus_from_largest_numa_node(self):
        output = _lscpu(
            "0 0 0 0",
            "1 1 0 0",
            "2 0 0 1",
            "3 1 0 1",
            "4 0 0 2",
            "5 1 0 2",
            "7 1 0 3",
        )
        with patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, output, "")):
            assert zbsutils.vhost_auto_cpuset("10.0.0.9", 22, "root", "pwd") == \
                "[1,3,5,7]"

    def test_tied_node_sizes_choose_node_with_highest_cpu_id(self):
        output = _lscpu(
            "0 0 0 0",
            "1 0 0 1",
            "2 0 0 2",
            "3 0 0 3",
            "4 1 0 0",
            "5 1 0 1",
            "6 1 0 2",
            "7 1 0 3",
        )
        with patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, output, "")):
            assert zbsutils.vhost_auto_cpuset("10.0.0.9", 22, "root", "pwd") == \
                "[4,5,6,7]"

    def test_never_crosses_numa_nodes_with_interleaved_cpu_ids(self):
        output = _lscpu(
            "0 0 0 0",
            "1 1 0 0",
            "2 0 0 1",
            "3 1 0 1",
            "4 0 0 2",
            "5 1 0 2",
            "6 0 0 3",
            "7 1 0 3",
            "8 0 0 4",
        )
        with patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, output, "")):
            assert zbsutils.vhost_auto_cpuset("10.0.0.9", 22, "root", "pwd") == \
                "[2,4,6,8]"

    def test_prefers_distinct_physical_cores_before_smt_siblings(self):
        output = _lscpu(
            "0 0 0 0",
            "1 0 0 1",
            "2 0 0 3",
            "3 0 0 3",
            "4 0 0 2",
            "5 0 0 2",
            "6 0 0 1",
            "7 0 0 0",
        )
        with patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, output, "")):
            assert zbsutils.vhost_auto_cpuset("10.0.0.9", 22, "root", "pwd") == \
                "[3,5,6,7]"

    def test_same_core_id_on_different_sockets_is_a_distinct_physical_core(self):
        output = _lscpu(
            "0 0 0 0",
            "1 0 0 1",
            "2 0 1 1",
            "3 0 1 1",
            "4 0 1 0",
            "5 0 1 0",
            "6 0 0 1",
            "7 0 0 0",
        )
        with patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, output, "")):
            assert zbsutils.vhost_auto_cpuset("10.0.0.9", 22, "root", "pwd") == \
                "[3,5,6,7]"

    def test_fills_remaining_slots_with_highest_smt_siblings(self):
        output = _lscpu(
            "0 0 0 0",
            "1 0 0 1",
            "2 0 0 0",
            "3 0 0 1",
            "4 0 0 0",
            "5 0 0 1",
        )
        with patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, output, "")):
            assert zbsutils.vhost_auto_cpuset("10.0.0.9", 22, "root", "pwd") == \
                "[2,3,4,5]"

    def test_uses_all_cpus_when_largest_node_has_fewer_than_four(self):
        output = _lscpu(
            "0 0 0 0",
            "1 1 0 0",
            "2 0 0 1",
            "3 1 0 1",
            "5 1 0 2",
        )
        with patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, output, "")):
            assert zbsutils.vhost_auto_cpuset("10.0.0.9", 22, "root", "pwd") == \
                "[1,3,5]"

    def test_queries_only_online_cpu_topology_from_target(self):
        output = "CPU NODE SOCKET CORE\n9 0 1 2\n"
        with patch.object(zbsutils.linux, 'sshpass_run',
                          return_value=(0, output, "")) as ssh:
            assert zbsutils.vhost_auto_cpuset("10.0.0.9", "2222", "admin", "secret") == \
                "[9]"
            ssh.assert_called_once_with(
                "10.0.0.9", "secret", "LC_ALL=C lscpu --online -e=CPU,NODE,SOCKET,CORE",
                user="admin", port=2222)

    def test_ssh_failure_includes_target_and_original_error(self):
        with patch.object(zbsutils.linux, 'sshpass_run',
                          return_value=(255, "", "permission denied")):
            with pytest.raises(Exception) as exc_info:
                zbsutils.vhost_auto_cpuset("10.0.0.9", 22, "root", "pwd")
        assert "10.0.0.9" in str(exc_info.value)
        assert "permission denied" in str(exc_info.value)

    def test_empty_topology_includes_target(self):
        output = _lscpu()
        with patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, output, "")):
            with pytest.raises(Exception) as exc_info:
                zbsutils.vhost_auto_cpuset("10.0.0.9", 22, "root", "pwd")
        assert "10.0.0.9" in str(exc_info.value)


class TestDeployVhost:
    def test_default_deploy_uses_auto_cpuset_for_target(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils, 'vhost_auto_cpuset',
                          return_value="[4,5,6,7]") as auto_cpuset, \
             patch.object(zbsutils, 'ensure_2m_hugetlbfs_mount',
                          return_value="/dev/hugepages2m"):
            zbsutils.deploy_vhost("10.0.0.9", 22, "root", "pwd")
            assert _last_cmd() == (
                "/usr/local/bin/zbsadm vhost deploy --host 10.0.0.9 --cpuset '[4,5,6,7]' --silent "
                "--hugepage-dir /dev/hugepages2m")
            auto_cpuset.assert_called_once_with("10.0.0.9", 22, "root", "pwd")

    def test_uses_existing_2mb_hugetlbfs_mount_when_hugepage_dir_not_set(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils, 'vhost_auto_cpuset', return_value="[4,5,6,7]"), \
             patch.object(zbsutils.linux, 'sshpass_run', side_effect=[
                 (0, "/dev/hugepages\n", ""),
             ]) as ssh:
            zbsutils.deploy_vhost("10.0.0.9", 22, "root", "pwd")
            cmd = _last_cmd()
            assert "--hugepage-dir /dev/hugepages" in cmd
            assert ssh.call_args_list[0][0][2].startswith("findmnt")
            assert "\\$2" in ssh.call_args_list[0][0][2]
            assert "\\$1" in ssh.call_args_list[0][0][2]

    def test_mounts_2mb_hugetlbfs_when_target_has_none(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils, 'vhost_auto_cpuset', return_value="[4,5,6,7]"), \
             patch.object(zbsutils.linux, 'sshpass_run', side_effect=[
                 (0, "", ""),
                 (0, "", ""),
             ]) as ssh:
            zbsutils.deploy_vhost("10.0.0.9", 22, "root", "pwd")
            cmd = _last_cmd()
            assert "--hugepage-dir /dev/hugepages2m" in cmd
            assert "mount -t hugetlbfs -o pagesize=2M none '/dev/hugepages2m'" in ssh.call_args_list[1][0][2]

    def test_explicit_cpuset_overrides_auto(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils, 'vhost_auto_cpuset') as auto_cpuset, \
             patch.object(zbsutils, 'ensure_2m_hugetlbfs_mount',
                          return_value="/dev/hugepages2m"):
            zbsutils.deploy_vhost("10.0.0.9", 22, "root", "pwd", cpuset="[1-4]")
            cmd = _last_cmd()
            assert "--cpuset '[1-4]'" in cmd
            auto_cpuset.assert_not_called()

    def test_includes_hugepage_args_when_explicitly_set(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils, 'vhost_auto_cpuset', return_value="[4,5,6,7]"):
            zbsutils.deploy_vhost("10.0.0.9", 22, "root", "pwd",
                                  hugepage_size=2048, hugepage_dir="/dev/hugepages2m")
            cmd = _last_cmd()
            assert "--hugepage-size 2048" in cmd
            assert "--hugepage-dir /dev/hugepages2m" in cmd

    def test_handler_forwards_hugepage_args_to_zbsadm(self):
        body = '{"hostIp":"10.0.0.9","sshPort":22,"sshUsername":"root","sshPassword":"pwd",' \
               '"hugepageSize":1024,"hugepageDir":"/dev/hugepages2m"}'
        with patch.object(zbsutils, 'deploy_vhost', return_value=_OK) as deploy, \
             patch.object(zbsutils, 'wait_vhost_target_ready', return_value=True):
            zbsagent.ZbsAgent().deploy_vhost(_req(body))
            deploy.assert_called_once_with("10.0.0.9", 22, "root", "pwd",
                                           hugepage_size=1024, hugepage_dir="/dev/hugepages2m")

    def test_waits_for_target_ready_after_deploy(self):
        body = '{"hostIp":"10.0.0.9","sshPort":22,"sshUsername":"root","sshPassword":"pwd"}'
        with patch.object(zbsutils, 'deploy_vhost', return_value=_OK), \
             patch.object(zbsutils, 'wait_vhost_target_ready', return_value=True) as wait_ready:
            out = zbsagent.ZbsAgent().deploy_vhost(_req(body))
            wait_ready.assert_called_once_with("10.0.0.9", 22, "root", "pwd")
            assert zbsagent.jsonobject.loads(out).success is True

    def test_custom_credentials_reach_cpuset_mount_and_ready_probes(self):
        body = json.dumps(dict(hostIp="10.0.0.9", sshPort=2222, sshUsername="admin", sshPassword="p@ss w'rd"))
        topology = _lscpu("4 0 0 0", "5 0 0 1", "6 0 0 2", "7 0 0 3")
        with patch.object(zbsutils.shell, 'call', return_value=_OK), \
             patch.object(zbsutils.linux, 'sshpass_run', side_effect=[
                 (0, topology, ""), (0, "", ""), (0, "", ""), (0, "", "")]) as ssh:
            out = zbsagent.ZbsAgent().deploy_vhost(_req(body))
            assert zbsagent.jsonobject.loads(out).success is True
            assert shlex.split(_last_cmd()) == [
                zbsutils.ZBSADM_BIN_PATH, "vhost", "deploy", "--host", "10.0.0.9", "--cpuset", "[4,5,6,7]",
                "--silent", "--hugepage-dir", "/dev/hugepages2m"]
            assert ssh.call_count == 4
            for args, kwargs in ssh.call_args_list:
                assert args[:2] == ("10.0.0.9", "p@ss w'rd")
                assert kwargs == dict(user="admin", port=2222)
            commands = [call.args[2] for call in ssh.call_args_list]
            assert commands[0] == zbsutils.VHOST_CPU_TOPOLOGY_CMD
            assert commands[1].startswith("findmnt")
            assert "mount -t hugetlbfs -o pagesize=2M" in commands[2]
            assert "docker ps" in commands[3] and "/var/zbsvhost/sockets/admin.sock" in commands[3]

    @pytest.mark.parametrize("failure", [Exception("host not found"),
                                       '{"success":false,"error":{"message":"private_key_file required"}}'])
    def test_cli_failure_reaches_response_without_ready_poll(self, failure):
        body = '{"hostIp":"10.0.0.9","sshPort":22,"sshUsername":"root","sshPassword":"pwd"}'
        with patch.object(zbsutils.shell, 'call', side_effect=[failure]), \
             patch.object(zbsutils, 'vhost_auto_cpuset', return_value="[4,5,6,7]"), \
             patch.object(zbsutils, 'ensure_2m_hugetlbfs_mount', return_value="/dev/hugepages2m"), \
             patch.object(zbsutils, 'wait_vhost_target_ready') as wait_ready:
            response = zbsagent.jsonobject.loads(zbsagent.ZbsAgent().deploy_vhost(_req(body)))
            assert response.success is False
            reason = str(failure) if isinstance(failure, Exception) else "private_key_file required"
            assert reason in response.error
            wait_ready.assert_not_called()

    def test_ready_timeout_fails_deploy(self):
        body = '{"hostIp":"10.0.0.9","sshPort":22,"sshUsername":"root","sshPassword":"pwd"}'
        with patch.object(zbsutils, 'deploy_vhost', return_value=_OK), \
             patch.object(zbsutils, 'wait_vhost_target_ready', return_value=False):
            out = zbsagent.ZbsAgent().deploy_vhost(_req(body))
            r = zbsagent.jsonobject.loads(out)
            assert r.success is False
            assert "not ready" in r.error

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
