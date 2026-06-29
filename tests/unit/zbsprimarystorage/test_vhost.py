# -*- coding: utf-8 -*-
"""
Unit tests for the zbsadm-vhost shell-out wrappers in zbsprimarystorage.zbsutils.

Key contract: `zbsadm vhost create-bdev --volume <pool>/<file>_zbs_` strips the
`_zbs_` marker before libcbd opens the file, so the argument carries the suffix
while the real ZBS file name has none.
"""
from unittest.mock import patch, MagicMock

from zbsprimarystorage import zbsutils
from zbsprimarystorage import zbsagent


def _real_quote(s):
    return "'" + s.replace("'", "'\\''") + "'"


def _last_cmd():
    return zbsutils.shell.call.call_args[0][0]


class TestCreateVhostBdev:
    def test_appends_zbs_suffix_to_volume_arg(self):
        with patch.object(zbsutils.shell, 'call'):
            zbsutils.create_vhost_bdev("10.0.0.9", 22, "root", "pwd",
                                       "lpool1", "vol-uuid-1", "vhost-blk-1")
            cmd = _last_cmd()
            assert "--volume lpool1/vol-uuid-1_zbs_ " in cmd
            # the real zbs file name (no suffix) must NOT be what we pass verbatim
            assert "--volume lpool1/vol-uuid-1 " not in cmd

    def test_targets_host_and_names_bdev(self):
        with patch.object(zbsutils.shell, 'call'):
            zbsutils.create_vhost_bdev("10.0.0.9", 2222, "admin", "pwd",
                                       "lpool1", "vol-uuid-1", "vhost-blk-1")
            cmd = _last_cmd()
            assert cmd.startswith(zbsutils.ZBSADM_BIN_PATH + " vhost create-bdev")
            assert "--host 10.0.0.9" in cmd
            assert "--port 2222" in cmd
            assert "-u admin" in cmd
            assert "--name vhost-blk-1" in cmd

    def test_shellquotes_password(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote):
            zbsutils.create_vhost_bdev("10.0.0.9", 22, "root", "p@ss w'rd",
                                       "lpool1", "vol-uuid-1", "vhost-blk-1")
            cmd = _last_cmd()
            assert "-p 'p@ss w'\\''rd'" in cmd


class TestDeleteVhostBdev:
    def test_deletes_by_name_on_host(self):
        with patch.object(zbsutils.shell, 'call'):
            zbsutils.delete_vhost_bdev("10.0.0.9", 22, "root", "pwd", "vhost-blk-1")
            cmd = _last_cmd()
            assert cmd.startswith(zbsutils.ZBSADM_BIN_PATH + " vhost delete-bdev")
            assert "--host 10.0.0.9" in cmd
            assert "--name vhost-blk-1" in cmd


class TestDeployVhost:
    # cpuset uses bracket notation ([1-4]) and must be shell-quoted or bash globs
    # it against cwd filenames, so shellquote is the real impl in these tests.
    def test_auto_cpuset_pins_last_core_from_target_host_cpu_count(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, "8\n", "")):
            zbsutils.deploy_vhost("10.0.0.9", 22, "root", "pwd")
            cmd = _last_cmd()
            assert cmd.startswith(zbsutils.ZBSADM_BIN_PATH + " vhost deploy")
            assert "--host 10.0.0.9" in cmd
            # dedicate the last core (cpu_num-1), avoiding core 0 (OS/IRQ load).
            # count comes from the target host over SSH, not the zbs server.
            assert "--cpuset '[7]'" in cmd

    def test_cpuset_is_inferred_on_target_not_local(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, "8\n", "")) as ssh:
            zbsutils.deploy_vhost("10.0.0.9", 2222, "root", "pwd")
            ssh.assert_called_once_with("10.0.0.9", "pwd", "grep -c processor /proc/cpuinfo",
                                        user="root", port=2222)

    def test_single_cpu_host_falls_back_to_core0(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, "1\n", "")):
            zbsutils.deploy_vhost("10.0.0.9", 22, "root", "pwd")
            assert "--cpuset '[0]'" in _last_cmd()

    def test_omits_hugepage_args_so_zbsadm_defaults_apply(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, "8\n", "")):
            zbsutils.deploy_vhost("10.0.0.9", 22, "root", "pwd")
            cmd = _last_cmd()
            assert "--hugepage-size" not in cmd
            assert "--hugepage-dir" not in cmd

    def test_explicit_cpuset_overrides_auto(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, "8\n", "")):
            zbsutils.deploy_vhost("10.0.0.9", 22, "root", "pwd", cpuset="[1-4]")
            cmd = _last_cmd()
            assert "--cpuset '[1-4]'" in cmd
            assert "'[7]'" not in cmd

    def test_includes_hugepage_args_when_explicitly_set(self):
        with patch.object(zbsutils.shell, 'call'), \
             patch.object(zbsutils.linux, 'shellquote', side_effect=_real_quote), \
             patch.object(zbsutils.linux, 'sshpass_run', return_value=(0, "8\n", "")):
            zbsutils.deploy_vhost("10.0.0.9", 22, "root", "pwd",
                                  hugepage_size=2048, hugepage_dir="/dev/hugepages2m")
            cmd = _last_cmd()
            assert "--hugepage-size 2048" in cmd
            assert "--hugepage-dir /dev/hugepages2m" in cmd


class TestDestroyVhost:
    def test_targets_host(self):
        with patch.object(zbsutils.shell, 'call'):
            zbsutils.destroy_vhost("10.0.0.9", 22, "root", "pwd")
            cmd = _last_cmd()
            assert cmd.startswith(zbsutils.ZBSADM_BIN_PATH + " vhost destroy")
            assert "--host 10.0.0.9" in cmd


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
            # logical pool + volume go straight to the zbsadm create-bdev call
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
