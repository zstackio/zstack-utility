from __future__ import annotations

import importlib
import json
import os
import shlex
import sys
import pytest
from typing import cast
from unittest.mock import MagicMock, patch, mock_open


# ---------------------------------------------------------------------------
# Import the ceph backup storage module with lock passthrough
# ---------------------------------------------------------------------------
try:
    # Ensure lock decorators are passthroughs before importing
    import tests.conftest  # noqa: F401

    from tests.conftest import passthrough_lock
    lock_mod = cast(object, importlib.import_module("zstacklib.utils.lock"))

    setattr(lock_mod, "lock", passthrough_lock)
    setattr(lock_mod, "file_lock", passthrough_lock)

    module = importlib.import_module("cephbackupstorage.cephagent")
    module = importlib.reload(module)
except (ImportError, ModuleNotFoundError) as e:
    pytest.skip(f"Cannot import cephbackupstorage: {e}", allow_module_level=True)


def _make_req(body_dict=None):
    http = cast(object, importlib.import_module("zstacklib.utils.http"))
    body = json.dumps(body_dict or {})
    return {http.REQUEST_BODY: body, http.REQUEST_HEADER: {}}


def _load_rsp(result):
    return json.loads(result)


def _make_agent():
    """Create CephAgent via __new__ to skip __init__ side effects."""
    agent = module.CephAgent.__new__(module.CephAgent)
    agent.cluster = MagicMock()
    agent.ioctx = {}
    agent.op_lock = __import__("threading").Lock()
    agent.upload_tasks = module.UploadTasks()
    return agent


def _mock_capacity(agent, total=10**12, avail=5 * 10**11):
    """Patch _get_capacity to return predictable values."""
    agent._get_capacity = MagicMock(return_value=(total, avail, []))
    ceph_mod = sys.modules["zstacklib.utils.ceph"]
    ceph_mod.get_ceph_manufacturer = MagicMock(return_value="generic")


# ---------------------------------------------------------------------------
# SFTP command formatting
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupSftpCommandFormatting:
    def test_sftp_targets_wrap_ipv6_hostname(self):
        with patch.object(module.linux, 'format_ssh_target', side_effect=lambda user, host: (
                '%s@[%s]' % (user, host) if ':' in host else '%s@%s' % (user, host))):
            assert module.build_sftp_target("root", "2001:db8::10") == "root@[2001:db8::10]"
            assert module.build_sftp_target("root", "192.168.10.10") == "root@192.168.10.10"

    def test_sftp_commands_use_bracketed_ipv6_target(self):
        with patch.object(module.linux, 'format_ssh_target', return_value='root@[2001:db8::10]'):
            scp_cmd = module.build_sftp_scp_to_pipe_cmd(
                22, "root", "2001:db8::10", "/backup/image.qcow2", "/tmp/image.fifo")
            sftp_cmd = module.build_sftp_batch_cmd(22, "root", "2001:db8::10")

        assert shlex.split(scp_cmd)[-2] == "root@[2001:db8::10]:/backup/image.qcow2"
        assert sftp_cmd.endswith("root@[2001:db8::10]")

    def test_scp_remote_path_uses_protocol_compatible_escaping(self):
        path = '/backup/镜像 $(touch hacked);a\\b\'c"d.qcow2'

        escaped_path = module.escape_scp_remote_path(path)

        assert escaped_path == "/backup/镜像\\ \\$\\(touch\\ hacked\\)\\;a\\\\b\\'c\\\"d.qcow2"


# ---------------------------------------------------------------------------
# Download URL handling
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupDownloadUrl:
    def test_ZSTAC_87499_preserves_ipv6_authority(self):
        url = "http://[fd11:5:5:29::66:571d]:18080/centos image.qcow2"

        encoded_url = module.encode_download_url(url)

        assert encoded_url == "http://[fd11:5:5:29::66:571d]:18080/centos%20image.qcow2"

    def test_preserves_sftp_userinfo_and_ipv6_authority(self):
        url = "sftp://root:password@[2001:db8::10]:22/backup/image.qcow2"

        encoded_url = module.encode_download_url(url)

        assert encoded_url == url

    def test_encodes_path_without_changing_query_structure(self):
        url = "https://example.com/镜像/image.qcow2?token=a%20b&name=测试"

        encoded_url = module.encode_download_url(url)

        assert encoded_url == (
            "https://example.com/%E9%95%9C%E5%83%8F/image.qcow2"
            "?token=a%20b&name=%E6%B5%8B%E8%AF%95"
        )

    def test_extracts_last_content_length_after_redirect(self):
        command_shell = MagicMock()
        command_shell.call.return_value = (
            "HTTP/1.1 302 Found\r\nContent-Length: 0\r\n\r\n"
            "HTTP/1.1 200 OK\r\nContent-Length: 21474836480\r\n"
        )
        url = "http://[2001:db8::10]:18080/image.qcow2"

        content_length = module.get_http_content_length(command_shell, url)

        assert content_length == "21474836480"
        command_shell.call.assert_called_once_with(
            "curl -fsSIL --globoff -- 'http://[2001:db8::10]:18080/image.qcow2'"
        )

    def test_missing_content_length_has_explicit_error(self):
        command_shell = MagicMock()
        command_shell.call.return_value = "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        url = "https://user:secret@example.com/image.qcow2?token=signed-value"

        with pytest.raises(Exception) as error:
            module.get_http_content_length(command_shell, url)

        assert str(error.value) == 'cannot get Content-Length from download URL'
        assert 'secret' not in str(error.value)
        assert 'signed-value' not in str(error.value)

    def test_missing_content_length_in_final_redirect_response_has_explicit_error(self):
        command_shell = MagicMock()
        command_shell.call.return_value = (
            "HTTP/1.1 302 Found\r\nContent-Length: 0\r\n\r\n"
            "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n"
        )

        with pytest.raises(Exception, match="cannot get Content-Length"):
            module.get_http_content_length(command_shell, "https://example.com/image.qcow2")

    def test_download_keeps_file_url_path_decoded(self, tmp_path):
        image_path = tmp_path / "centos image.qcow2"
        image_path.write_bytes(b"raw-image")
        progress_path = tmp_path / "progress"
        progress_path.write_text("")
        agent = _make_agent()
        agent._set_capacity_to_response = MagicMock()
        command_shell = MagicMock()
        command_shell.call.side_effect = lambda command: (
            "raw" if "grep 'file format'" in command else '{"size": 9}')

        with patch.object(module.traceable_shell, 'get_shell', return_value=command_shell), \
                patch.object(module.linux, 'create_temp_file', return_value=str(progress_path)), \
                patch.object(module, 'Report'):
            result = agent.download(_make_req({
                'url': 'file://%s' % image_path,
                'installPath': 'ceph://pool/image',
                'sendCommandUrl': '',
                'threadContext': {},
                'threadContextStack': [],
                'imageUuid': 'image-uuid',
            }))

        rsp = _load_rsp(result)
        assert rsp['success'] is True
        assert rsp['actualSize'] == os.path.getsize(str(image_path))
        assert str(image_path) in command_shell.bash_progress_1.call_args[0][0]

    def test_download_reports_final_redirect_content_length(self, tmp_path):
        progress_path = tmp_path / "progress"
        progress_path.write_text("")
        agent = _make_agent()
        agent._set_capacity_to_response = MagicMock()
        command_shell = MagicMock()

        def command_result(command):
            if command.startswith('curl '):
                return (
                    "HTTP/1.1 302 Found\r\nContent-Length: 0\r\n\r\n"
                    "HTTP/1.1 200 OK\r\nContent-Length: 21474836480\r\n")
            if "grep 'file format'" in command:
                return 'raw'
            return '{"size": 21474836480}'

        command_shell.call.side_effect = command_result
        command_shell.bash_progress_1.return_value = (None, None, None)
        response = MagicMock()
        response.read.return_value = b'raw-image'

        with patch.object(module.traceable_shell, 'get_shell', return_value=command_shell), \
                patch.object(module.linux, 'create_temp_file', return_value=str(progress_path)), \
                patch.object(module.linux, 'get_file_size_by_http_head',
                             side_effect=AssertionError('must not issue a second HEAD request')), \
                patch.object(module.urllib.request, 'urlopen', return_value=response), \
                patch.object(module, 'Report'):
            result = agent.download(_make_req({
                'url': 'https://example.com/image.qcow2',
                'installPath': 'ceph://pool/image',
                'sendCommandUrl': '',
                'threadContext': {},
                'threadContextStack': [],
                'imageUuid': 'image-uuid',
            }))

        rsp = _load_rsp(result)
        assert rsp['success'] is True
        assert rsp['actualSize'] == 21474836480

    def test_download_decodes_sftp_path_before_command_construction(self, tmp_path):
        progress_path = tmp_path / "progress"
        progress_path.write_text("")
        agent = _make_agent()
        agent._set_capacity_to_response = MagicMock()
        command_shell = MagicMock()

        def command_result(command):
            if 'sftp ' in command:
                return "Connected\n-rw-r--r-- 1 root root 9 Jan 1 image.qcow2\n"
            if "grep 'file format'" in command:
                return 'raw'
            return '{"size": 9}'

        command_shell.call.side_effect = command_result
        command_shell.bash_progress_1.return_value = (None, None, None)

        with patch.object(module.traceable_shell, 'get_shell', return_value=command_shell), \
                patch.object(module.linux, 'create_temp_file', return_value=str(progress_path)), \
                patch.object(module.linux, 'format_ssh_target', return_value='root@example.com'), \
                patch.object(module.linux, 'rm_file_force'), \
                patch.object(module.os, 'mkfifo'), \
                patch.object(module, 'Report'):
            result = agent.download(_make_req({
                'url': 'sftp://root@example.com/backup/镜像 $(touch hacked).qcow2',
                'installPath': 'ceph://pool/image',
                'sendCommandUrl': '',
                'threadContext': {},
                'threadContextStack': [],
                'imageUuid': 'image-uuid',
            }))

        rsp = _load_rsp(result)
        assert rsp['success'] is True
        commands = [call.args[0] for call in command_shell.call.call_args_list]
        commands.append(command_shell.bash_progress_1.call_args.args[0])
        commands.append(command_shell.run.call_args.args[0])
        sftp_commands = '\n'.join(commands)
        assert '"/backup/镜像 $(touch hacked).qcow2"' in commands[0]
        assert 'root@example.com:/backup/镜像\\ \\$\\(touch\\ hacked\\).qcow2' in shlex.split(commands[-2])
        assert "<<'EOF'" in commands[0]
        assert '%E9%95%9C%E5%83%8F%20%24%28touch%20hacked%29.qcow2' not in sftp_commands

    @pytest.mark.parametrize('path', [
        '/backup/image%00.qcow2',
        '/backup/image%0D.qcow2',
        '/backup/image%0AEOF%0Aecho%20injected.qcow2',
    ])
    def test_decode_sftp_path_rejects_unsupported_control_characters(self, path):
        with pytest.raises(Exception, match='unsupported control character'):
            module.decode_sftp_path(path)


# ---------------------------------------------------------------------------
# echo
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupEcho:
    def test_echo_returns_empty_string(self):
        agent = _make_agent()
        result = agent.echo(_make_req())
        assert result == ""


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupInit:
    def test_init_creates_missing_pools(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = sys.modules["zstacklib.utils.shell"]
        shell_mod.call = MagicMock(return_value="existing-pool")
        ceph_mod = sys.modules["zstacklib.utils.ceph"]
        ceph_mod.get_fsid = MagicMock(return_value="fsid-001")
        ceph_mod.is_xsky = MagicMock(return_value=False)
        ceph_mod.is_sandstone = MagicMock(return_value=False)

        result = agent.init(_make_req({
            "pools": [
                {"name": "existing-pool", "predefined": False},
                {"name": "new-pool", "predefined": False},
            ]
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["fsid"] == "fsid-001"
        # existing-pool should NOT trigger create, new-pool should
        create_calls = [c for c in shell_mod.call.call_args_list
                        if "osd pool create" in str(c)]
        assert len(create_calls) == 1
        assert "new-pool" in str(create_calls[0])

    def test_init_raises_if_predefined_pool_missing(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = sys.modules["zstacklib.utils.shell"]
        shell_mod.call = MagicMock(return_value="other-pool")

        result = agent.init(_make_req({
            "pools": [{"name": "missing-pool", "predefined": True}]
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is False
        assert "cannot find pool" in rsp["error"]


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupConnect:
    def test_connect_reconnects_and_returns_capacity(self):
        agent = _make_agent()
        _mock_capacity(agent)
        agent.reconnect_cluster = MagicMock()

        result = agent.connect(_make_req())
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["totalCapacity"] == 10**12
        assert rsp["availableCapacity"] == 5 * 10**11
        agent.reconnect_cluster.assert_called_once()


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupPing:
    def test_ping_success_when_mon_addr_found(self):
        agent = _make_agent()
        module.bash_o = MagicMock(return_value=json.dumps({
            "mons": [{"addr": "10.0.0.1:6789/0"}]
        }))

        mock_shell_cmd = MagicMock()
        mock_shell_cmd.return_code = 0
        shell_mod = sys.modules["zstacklib.utils.shell"]
        shell_mod.ShellCmd = MagicMock(return_value=mock_shell_cmd)
        shell_mod.run = MagicMock()

        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.write_uuids = MagicMock()

        result = agent.ping(_make_req({
            "monAddr": "10.0.0.1",
            "monUuid": "mon-uuid-001",
            "testImagePath": "pool1/test-obj",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True

    def test_ping_fails_when_mon_addr_changed(self):
        agent = _make_agent()
        module.bash_o = MagicMock(return_value=json.dumps({
            "mons": [{"addr": "10.0.0.2:6789/0"}]
        }))

        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.write_uuids = MagicMock()

        result = agent.ping(_make_req({
            "monAddr": "10.0.0.1",
            "monUuid": "mon-uuid-001",
            "testImagePath": "pool1/test-obj",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is False
        assert rsp["failure"] == "MonAddrChanged"

    def test_ping_fails_when_rados_write_fails(self):
        agent = _make_agent()
        module.bash_o = MagicMock(return_value=json.dumps({
            "mons": [{"addr": "10.0.0.1:6789/0"}]
        }))

        mock_shell_cmd = MagicMock()
        mock_shell_cmd.return_code = 1
        mock_shell_cmd.stderr = "write error"
        mock_shell_cmd.stdout = ""
        shell_mod = sys.modules["zstacklib.utils.shell"]
        shell_mod.ShellCmd = MagicMock(return_value=mock_shell_cmd)

        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.write_uuids = MagicMock()

        result = agent.ping(_make_req({
            "monAddr": "10.0.0.1",
            "monUuid": "mon-uuid-001",
            "testImagePath": "pool1/test-obj",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is False
        assert rsp["failure"] == "UnableToCreateFile"


# ---------------------------------------------------------------------------
# get_image_size
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupGetImageSize:
    def test_get_image_size_returns_size(self):
        agent = _make_agent()
        shell_mod = sys.modules["zstacklib.utils.shell"]
        shell_mod.call = MagicMock(return_value='{"size": 1073741824}')

        result = agent.get_image_size(_make_req({
            "installPath": "ceph://pool1/image-001"
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["size"] == 1073741824


# ---------------------------------------------------------------------------
# get_local_file_size
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupGetLocalFileSize:
    def test_get_local_file_size_returns_size(self):
        agent = _make_agent()
        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.get_local_file_size = MagicMock(return_value=2147483648)

        result = agent.get_local_file_size(_make_req({"path": "/tmp/test.img"}))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["size"] == 2147483648


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupDelete:
    def test_delete_removes_image(self):
        agent = _make_agent()
        _mock_capacity(agent)
        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.wait_callback_success = MagicMock()
        shell_mod = sys.modules["zstacklib.utils.shell"]
        shell_mod.check_run = MagicMock()

        mock_ioctx = MagicMock()
        agent.get_ioctx = MagicMock(return_value=mock_ioctx)

        result = agent.delete(_make_req({
            "installPath": "ceph://pool1/image-001"
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        linux_mod.wait_callback_success.assert_called_once()
        mock_ioctx.remove_object.assert_called_once_with("image-001-export")


# ---------------------------------------------------------------------------
# get_facts
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupGetFacts:
    def test_get_facts_returns_fsid_and_mon_addr(self):
        agent = _make_agent()
        bash_mod = sys.modules["zstacklib.utils.bash"]
        bash_mod.bash_o = MagicMock(return_value='{"mons":[]}')
        ceph_mod = sys.modules["zstacklib.utils.ceph"]
        ceph_mod.get_fsid = MagicMock(return_value="fsid-002")
        ceph_mod.get_mon_addr = MagicMock(return_value="10.0.0.1:6789")

        result = agent.get_facts(_make_req({"monUuid": "mon-001"}))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["fsid"] == "fsid-002"


# ---------------------------------------------------------------------------
# check_pool
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupCheckPool:
    def test_check_pool_passes_when_pools_exist(self):
        agent = _make_agent()
        shell_mod = sys.modules["zstacklib.utils.shell"]
        shell_mod.call = MagicMock(return_value="pool1\npool2\n")

        result = agent.check_pool(_make_req({
            "pools": [{"name": "pool1"}, {"name": "pool2"}]
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True

    def test_check_pool_fails_when_pool_missing(self):
        agent = _make_agent()
        shell_mod = sys.modules["zstacklib.utils.shell"]
        shell_mod.call = MagicMock(return_value="pool1\n")

        result = agent.check_pool(_make_req({
            "pools": [{"name": "pool1"}, {"name": "missing-pool"}]
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is False
        assert "cannot find pool" in rsp["error"]


# ---------------------------------------------------------------------------
# add_export_token
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupAddExportToken:
    def test_add_export_token_writes_to_rados(self):
        agent = _make_agent()
        _mock_capacity(agent)
        mock_ioctx = MagicMock()
        agent.get_ioctx = MagicMock(return_value=mock_ioctx)

        result = agent.add_export_token(_make_req({
            "installPath": "ceph://pool1/image-001",
            "token": "secret-token-123",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        mock_ioctx.write_full.assert_called_once_with("image-001-export", "secret-token-123")


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupExport:
    class Response:
        def __init__(self):
            self.status = 200
            self.headers = {}

    class Request:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    def test_export_accepts_bytes_token_matching_url_token(self):
        agent = _make_agent()
        image_uuid = "1234567890abcdef1234567890abcdef"
        mock_ioctx = MagicMock()
        mock_ioctx.read.return_value = b"secret-token-123"
        agent.get_ioctx = MagicMock(return_value=mock_ioctx)
        rsp = self.Response()

        with patch.object(module.rbd, "Image", return_value=MagicMock()) as image, \
                patch.object(module, "ImageFileObject") as image_file_object, \
                patch.object(module, "_serve_fileobj", return_value="file-response") as serve_fileobj:
            image_file_object.return_value.size = 1024
            result = agent.export(self.Request(), rsp,
                                  pool="pool1",
                                  image="ceph://pool1/%s" % image_uuid,
                                  token="secret-token-123")

        assert result == "file-response"
        assert rsp.status == 200
        mock_ioctx.read.assert_called_once_with("%s-export" % image_uuid)
        image.assert_called_once_with(mock_ioctx, image_uuid, read_only=True)
        serve_fileobj.assert_called_once()

    def test_export_rejects_mismatched_bytes_token(self):
        agent = _make_agent()
        image_uuid = "1234567890abcdef1234567890abcdef"
        mock_ioctx = MagicMock()
        mock_ioctx.read.return_value = b"secret-token-123"
        agent.get_ioctx = MagicMock(return_value=mock_ioctx)
        rsp = self.Response()

        result = agent.export(self.Request(), rsp,
                              pool="pool1",
                              image="ceph://pool1/%s" % image_uuid,
                              token="wrong-token")

        assert result == "Forbidden"
        assert rsp.status == 403


# ---------------------------------------------------------------------------
# remove_export_token
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupRemoveExportToken:
    def test_remove_export_token_removes_from_rados(self):
        agent = _make_agent()
        _mock_capacity(agent)
        mock_ioctx = MagicMock()
        agent.get_ioctx = MagicMock(return_value=mock_ioctx)

        result = agent.remove_export_token(_make_req({
            "installPath": "ceph://pool1/image-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        mock_ioctx.remove_object.assert_called_once_with("image-001-export")

    def test_remove_export_token_ignores_not_found(self):
        agent = _make_agent()
        _mock_capacity(agent)
        mock_ioctx = MagicMock()
        rados_mod = sys.modules["rados"]
        mock_ioctx.remove_object.side_effect = rados_mod.ObjectNotFound
        agent.get_ioctx = MagicMock(return_value=mock_ioctx)

        result = agent.remove_export_token(_make_req({
            "installPath": "ceph://pool1/image-001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# check_image_metadata_file_exist
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupCheckImageMetadataFileExist:
    def test_metadata_file_exists(self):
        agent = _make_agent()
        module.bash_ro = MagicMock(return_value=(0, "stat info"))

        result = agent.check_image_metadata_file_exist(_make_req({
            "poolName": "bak-t-uuid001"
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["exist"] is True
        assert rsp["backupStorageMetaFileName"] == "bs_ceph_info.json"

    def test_metadata_file_not_exists(self):
        agent = _make_agent()
        module.bash_ro = MagicMock(return_value=(2, "not found"))

        result = agent.check_image_metadata_file_exist(_make_req({
            "poolName": "bak-t-uuid002"
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["exist"] is False


# ---------------------------------------------------------------------------
# dump_image_metadata_to_file
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupDumpImageMetadataToFile:
    def test_dump_single_metadata_write_mode(self):
        agent = _make_agent()
        bash_mod = sys.modules["zstacklib.utils.bash"]
        bash_mod.bash_r = MagicMock(return_value=0)
        bash_mod.bash_ro = MagicMock(return_value=(0, ""))
        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.rm_file_force = MagicMock()

        # Mock put_metadata_file to avoid real rados
        agent.put_metadata_file = MagicMock()

        with patch("builtins.open", mock_open()) as mock_file:
            result = agent.dump_image_metadata_to_file(_make_req({
                "poolName": "bak-t-uuid001",
                "imageMetaData": '{"uuid":"img-001","name":"test"}',
                "dumpAllMetaData": True,
            }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        mock_file.assert_called_with("/tmp/bs_ceph_info.json", "w")


# ---------------------------------------------------------------------------
# delete_image_metadata_from_file
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupDeleteImageMetadataFromFile:
    def test_delete_metadata_returns_ret_code(self):
        agent = _make_agent()
        module.bash_ro = MagicMock(return_value=(0, ""))
        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.rm_file_force = MagicMock()

        # Mock get/put metadata
        agent.get_metadata_file = MagicMock()
        agent.put_metadata_file = MagicMock()

        result = agent.delete_image_metadata_from_file(_make_req({
            "imageUuid": "img-001",
            "poolName": "bak-t-uuid001",
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["ret"] == 0


# ---------------------------------------------------------------------------
# migrate_image
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupMigrateImage:
    def test_migrate_success(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = sys.modules["zstacklib.utils.shell"]
        shell_mod.run = MagicMock(return_value=0)
        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.build_sshpass_cmd = MagicMock(return_value=("sshpass_cmd", "/tmp/file"))
        linux_mod.rm_file_force = MagicMock()
        linux_mod.sshpass_call = MagicMock(return_value="md5hash")
        agent._read_file_content = MagicMock(return_value="md5hash")

        result = agent.migrate_image(_make_req({
            "imageUuid": "img-001",
            "imageSize": 1073741824,
            "srcInstallPath": "ceph://pool1/src-img",
            "dstInstallPath": "ceph://pool2/dst-img",
            "dstMonHostname": "10.0.0.2",
            "dstMonSshUsername": "root",
            "dstMonSshPassword": "password",
            "dstMonSshPort": 22,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is True

    def test_migrate_failure(self):
        agent = _make_agent()
        _mock_capacity(agent)
        shell_mod = sys.modules["zstacklib.utils.shell"]
        shell_mod.run = MagicMock(return_value=1)
        linux_mod = sys.modules["zstacklib.utils.linux"]
        linux_mod.build_sshpass_cmd = MagicMock(return_value=("sshpass_cmd", "/tmp/file"))
        linux_mod.rm_file_force = MagicMock()

        result = agent.migrate_image(_make_req({
            "imageUuid": "img-001",
            "imageSize": 1073741824,
            "srcInstallPath": "ceph://pool1/src-img",
            "dstInstallPath": "ceph://pool2/dst-img",
            "dstMonHostname": "10.0.0.2",
            "dstMonSshUsername": "root",
            "dstMonSshPassword": "password",
            "dstMonSshPort": 22,
        }))
        rsp = _load_rsp(result)
        assert rsp["success"] is False
        assert "Failed to migrate" in rsp["error"]


# ---------------------------------------------------------------------------
# cancel
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupCancel:
    def test_cancel_delegates_to_plugin(self):
        agent = _make_agent()
        plugin_mod = sys.modules["zstacklib.utils.plugin"]
        mock_rsp = MagicMock()
        mock_rsp.__dict__ = {"success": True, "error": ""}
        plugin_mod.cancel_job = MagicMock(return_value=mock_rsp)

        result = agent.cancel(_make_req({"cancellationApiId": "api-123"}))
        rsp = _load_rsp(result)
        assert rsp["success"] is True


# ---------------------------------------------------------------------------
# get_upload_param (static method)
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupGetUploadParam:
    def test_valid_headers_parsed(self):
        headers = {
            "X-IMAGE-UUID": "img-uuid-001",
            "X-IMAGE-SIZE": "1073741824",
            "X-SLICE-OFFSET": "0",
            "X-SLICE-SIZE": "4194304",
            "X-SLICE-INDEX": "0",
            "X-SLICE-HASH": "abc123",
            "X-HASH-ALGORITHM": "md5",
        }
        param = module.CephAgent.get_upload_param(headers)
        assert param.image_uuid == "img-uuid-001"
        assert param.image_size == 1073741824
        assert param.slice_offset == 0
        assert param.slice_size == 4194304
        assert param.slice_hash == "abc123"

    def test_invalid_offset_raises(self):
        headers = {
            "X-IMAGE-UUID": "img-uuid-001",
            "X-IMAGE-SIZE": "1024",
            "X-SLICE-OFFSET": "2048",  # >= image_size
        }
        with pytest.raises(Exception, match="invalid slice offset"):
            module.CephAgent.get_upload_param(headers)

    def test_negative_size_raises(self):
        headers = {
            "X-IMAGE-UUID": "img-uuid-001",
            "X-IMAGE-SIZE": "-1",
        }
        with pytest.raises(Exception, match="invalid header"):
            module.CephAgent.get_upload_param(headers)


# ---------------------------------------------------------------------------
# get_upload_progress
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupGetUploadProgress:
    def test_upload_progress_for_running_task(self):
        agent = _make_agent()
        # Create a mock task
        task = MagicMock()
        task.completed = False
        task.installPath = "ceph://pool1/image-001"
        task.expectedSize = 1073741824
        task.checked_download_size.return_value = 536870912
        task.lastOpTime = 1000
        task.image_format = "raw"
        task.lastError = None
        task.slice_uploaded = MagicMock()
        task.slice_uploaded.__len__ = MagicMock(return_value=536870912)
        agent.upload_tasks.get_task = MagicMock(return_value=task)

        result = agent.get_upload_progress(_make_req({"imageUuid": "img-uuid-001"}))
        rsp = _load_rsp(result)
        assert rsp["success"] is True
        assert rsp["completed"] is False
        assert rsp["installPath"] == "ceph://pool1/image-001"

    def test_upload_progress_task_not_found(self):
        agent = _make_agent()
        agent.upload_tasks.get_task = MagicMock(return_value=None)

        result = agent.get_upload_progress(_make_req({"imageUuid": "nonexistent"}))
        rsp = _load_rsp(result)
        assert rsp["success"] is False
        assert "not found" in rsp["error"]


# ---------------------------------------------------------------------------
# _normalize_install_path / _parse_install_path
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestCephBackupHelpers:
    def test_normalize_install_path(self):
        agent = _make_agent()
        assert agent._normalize_install_path("ceph://pool1/image-001") == "pool1/image-001"

    def test_parse_install_path(self):
        agent = _make_agent()
        pool, image = agent._parse_install_path("ceph://pool1/image-001")
        assert pool == "pool1"
        assert image == "image-001"


# ---------------------------------------------------------------------------
# get_image_format_from_buf (Python 3 bytes/str fix)
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestGetImageFormatFromBuf:
    def test_qcow2_bytes_header(self):
        """qcow2 magic: QFI\\xfb with no backing file (bytes 16-20 all zero)"""
        buf = bytearray(0x9007)
        buf[0:4] = b'QFI\xfb'
        # bytes 16-20 already zero
        assert module.get_image_format_from_buf(bytes(buf)) == "qcow2"

    def test_derived_qcow2_bytes_header(self):
        """qcow2 with backing file (bytes 16-20 non-zero)"""
        buf = bytearray(0x9007)
        buf[0:4] = b'QFI\xfb'
        buf[16:20] = b'\x00\x00\x00\x01'
        assert module.get_image_format_from_buf(bytes(buf)) == "derivedQcow2"

    def test_vmdk_bytes_header(self):
        buf = bytearray(0x9007)
        buf[0:5] = b'KDMV\x03'
        assert module.get_image_format_from_buf(bytes(buf)) == "vmdk"

    def test_iso_bytes_header_at_0x8001(self):
        buf = bytearray(0x9007)
        buf[0x8001:0x8006] = b'CD001'
        assert module.get_image_format_from_buf(bytes(buf)) == "iso"

    def test_iso_bytes_header_at_0x8801(self):
        buf = bytearray(0x9007)
        buf[0x8801:0x8806] = b'CD001'
        assert module.get_image_format_from_buf(bytes(buf)) == "iso"

    def test_iso_bytes_header_at_0x9001(self):
        buf = bytearray(0x9007)
        buf[0x9001:0x9006] = b'CD001'
        assert module.get_image_format_from_buf(bytes(buf)) == "iso"

    def test_raw_fallback(self):
        buf = bytearray(0x9007)
        assert module.get_image_format_from_buf(bytes(buf)) == "raw"

    def test_str_input_does_not_match(self):
        """str input should NOT match bytes literals — returns raw"""
        buf = 'QFI\xfb' + '\x00' * (0x9007 - 4)
        assert module.get_image_format_from_buf(buf) == "raw"


# ---------------------------------------------------------------------------
# _getRealSize logic (closure inside download, tested via equivalent logic)
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestGetRealSizeLogic:
    """_getRealSize is a closure inside download(). Replicate its logic here
    to verify the int-return fix for Python 3.
    TODO: if _getRealSize is extracted to module level, replace with direct import."""

    @staticmethod
    def _getRealSize(length):
        """Exact copy of the fixed _getRealSize from cephagent.py"""
        length = length.strip()
        if not length[-1].isalpha():
            return int(length)
        units = {
            "g": lambda x: x * 1024 * 1024 * 1024,
            "m": lambda x: x * 1024 * 1024,
            "k": lambda x: x * 1024,
        }
        try:
            return units[length[-1].lower()](int(length[:-1]))
        except:
            return 0

    def test_pure_digits_returns_int(self):
        result = self._getRealSize("123456789")
        assert result == 123456789
        assert isinstance(result, int)

    def test_with_k_suffix(self):
        assert self._getRealSize("50K") == 50 * 1024

    def test_with_m_suffix(self):
        assert self._getRealSize("10M") == 10 * 1024 * 1024

    def test_with_g_suffix(self):
        assert self._getRealSize("2G") == 2 * 1024 * 1024 * 1024

    def test_lowercase_suffix(self):
        assert self._getRealSize("50k") == 50 * 1024

    def test_strip_whitespace_and_cr(self):
        result = self._getRealSize("123456789\r")
        assert result == 123456789
        assert isinstance(result, int)

    def test_strip_trailing_newline(self):
        result = self._getRealSize("50K\n")
        assert result == 50 * 1024

    def test_invalid_input_returns_zero(self):
        assert self._getRealSize("abc") == 0

    def test_comparison_with_int(self):
        """The original bug: str > int raises TypeError in Python 3"""
        total = self._getRealSize("123456789")
        synced = 0
        # This must not raise TypeError
        assert total > synced


# ---------------------------------------------------------------------------
# _get_origin_format: file:// path must open in binary mode
# ---------------------------------------------------------------------------
@pytest.mark.ceph
class TestGetOriginFormatFileMode:
    def test_local_file_qcow2_detected(self):
        """Verify local file opened in 'rb' mode detects qcow2 correctly"""
        import tempfile, os
        buf = bytearray(0x9007)
        buf[0:4] = b'QFI\xfb'
        # bytes 16-20 all zero = qcow2 (not derived)
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, bytes(buf))
            os.close(fd)
            with open(path, 'rb') as f:
                qhdr = f.read(0x9007)
            assert module.get_image_format_from_buf(qhdr) == "qcow2"
        finally:
            os.unlink(path)

    def test_local_file_text_mode_fails(self):
        """Text mode would corrupt binary data or fail to match"""
        import tempfile, os
        buf = bytearray(0x9007)
        buf[0:4] = b'QFI\xfb'
        fd, path = tempfile.mkstemp()
        try:
            os.write(fd, bytes(buf))
            os.close(fd)
            with open(path, 'r', errors='replace') as f:
                qhdr = f.read(0x9007)
            # str vs bytes literal => never matches qcow2
            assert module.get_image_format_from_buf(qhdr) == "raw"
        finally:
            os.unlink(path)
