import contextlib
import importlib.util
import json
import re
import stat
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_MODULE = REPO_ROOT / "zstackctl" / "zstackctl" / "keycloak_config.py"
CTL_PY = REPO_ROOT / "zstackctl" / "zstackctl" / "ctl.py"


def _load_config_module():
    spec = importlib.util.spec_from_file_location("keycloak_config", CONFIG_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def _keycloak_server(initial_password="password"):
    state = {
        "password": initial_password,
        "requests": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, unused_format, *unused_args):
            pass

        def _read_body(self):
            return self.rfile.read(int(self.headers.get("Content-Length", "0")))

        def _send_json(self, status, body):
            encoded = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self):
            body = self._read_body()
            form = parse_qs(body.decode("utf-8"), keep_blank_values=True)
            state["requests"].append(("POST", self.path, form, dict(self.headers)))
            if self.path != "/realms/master/protocol/openid-connect/token":
                self.send_error(404)
                return
            if form.get("password") != [state["password"]]:
                self._send_json(401, {"error": "invalid_grant"})
                return
            self._send_json(200, {"access_token": "admin-token"})

        def do_GET(self):
            state["requests"].append(("GET", self.path, None, dict(self.headers)))
            parsed = urlparse(self.path)
            if parsed.path != "/admin/realms/master/users":
                self.send_error(404)
                return
            if parse_qs(parsed.query) != {"username": ["admin"], "exact": ["true"]}:
                self.send_error(400)
                return
            if self.headers.get("Authorization") != "Bearer admin-token":
                self.send_error(401)
                return
            self._send_json(200, [{"id": "master-admin-id", "username": "admin"}])

        def do_PUT(self):
            body = json.loads(self._read_body().decode("utf-8"))
            state["requests"].append(("PUT", self.path, body, dict(self.headers)))
            if self.path != "/admin/realms/master/users/master-admin-id/reset-password":
                self.send_error(404)
                return
            if self.headers.get("Authorization") != "Bearer admin-token":
                self.send_error(401)
                return
            state["password"] = body["value"]
            self.send_response(204)
            self.end_headers()

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    try:
        yield "http://127.0.0.1:%s" % server.server_port, state
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_admin_password_file_is_private_and_preserves_special_characters(tmp_path):
    config = _load_config_module()
    password_file = tmp_path / "conf" / "admin-password"
    password_file.parent.mkdir()

    config.write_admin_password(
        str(password_file),
        "custom password&+='caf\u00e9'",
        tmp_path.stat().st_uid,
        tmp_path.stat().st_gid,
    )

    assert password_file.read_text(encoding="utf-8") == "custom password&+='caf\u00e9'\n"
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o640
    with pytest.raises(ValueError, match="line breaks"):
        config.write_admin_password(str(password_file), "invalid\npassword")


def test_admin_password_file_uses_legacy_default_then_reads_rotated_value(tmp_path):
    config = _load_config_module()
    password_file = tmp_path / "conf" / "admin-password"
    password_file.parent.mkdir()

    assert config.read_admin_password(str(password_file), "password") == "password"
    config.write_admin_password(
        str(password_file), "rotated password&+='caf\u00e9'",
        tmp_path.stat().st_uid, tmp_path.stat().st_gid)
    assert config.read_admin_password(
        str(password_file), "password") == "rotated password&+='caf\u00e9'"


def test_password_file_snapshot_restores_content_and_absence(tmp_path):
    config = _load_config_module()
    password_file = tmp_path / "conf" / "admin-password"
    password_file.parent.mkdir()
    password_file.write_text("password\n", encoding="utf-8")
    password_file.chmod(0o600)

    original = config.snapshot_file(str(password_file))
    config.write_admin_password(
        str(password_file), "new-secret-value",
        tmp_path.stat().st_uid, tmp_path.stat().st_gid)
    config.restore_file(str(password_file), original)

    assert password_file.read_text(encoding="utf-8") == "password\n"
    assert stat.S_IMODE(password_file.stat().st_mode) == 0o600

    password_file.unlink()
    absent = config.snapshot_file(str(password_file))
    config.write_admin_password(
        str(password_file), "new-secret-value",
        tmp_path.stat().st_uid, tmp_path.stat().st_gid)
    config.restore_file(str(password_file), absent)
    assert not password_file.exists()


def test_keycloak_admin_client_changes_existing_password_through_admin_rest():
    config = _load_config_module()
    new_password = "rotated password&+='caf\u00e9'"

    with _keycloak_server() as (server_url, state):
        client = config.KeycloakAdminClient(server_url)
        user_id, token = client.change_password("admin", "password", new_password)

    assert user_id == "master-admin-id"
    assert token == "admin-token"
    assert state["password"] == new_password
    methods = [request[0] for request in state["requests"]]
    assert methods == ["POST", "GET", "PUT", "POST"]
    reset_request = state["requests"][2]
    assert reset_request[2] == {
        "type": "password",
        "value": new_password,
        "temporary": False,
    }


def test_keycloak_admin_authentication_error_does_not_expose_password():
    config = _load_config_module()
    supplied_password = "wrong-secret-value"

    with _keycloak_server() as (server_url, unused_state):
        client = config.KeycloakAdminClient(server_url)
        with pytest.raises(config.KeycloakAdminError) as error_info:
            client.change_password("admin", supplied_password, "new-secret-value")

    assert supplied_password not in str(error_info.value)
    assert "new-secret-value" not in str(error_info.value)


def test_authentication_failure_does_not_persist_password_configuration():
    config = _load_config_module()
    calls = []

    with _keycloak_server() as (server_url, unused_state):
        client = config.KeycloakAdminClient(server_url)
        with pytest.raises(config.KeycloakAdminError):
            config.rotate_admin_password(
                client,
                "admin",
                "wrong-current-password",
                "new-secret-value",
                lambda unused_password: calls.append("persist"),
                lambda: calls.append("restore"))

    assert calls == []


def test_configuration_failure_rolls_back_database_and_files_without_secret_in_error():
    config = _load_config_module()
    calls = []
    new_password = "new-secret-value"

    class Client:
        def change_password(self, username, current_password, changed_password):
            calls.append(("change", username, current_password, changed_password))
            return "master-admin-id", "new-token"

        def rollback_password(self, username, user_id, token, previous_password):
            calls.append(("rollback", username, user_id, token, previous_password))

    def persist_password(changed_password):
        calls.append(("persist", changed_password))
        raise RuntimeError(changed_password)

    def restore_password():
        calls.append(("restore",))

    with pytest.raises(config.KeycloakAdminError) as error_info:
        config.rotate_admin_password(
            Client(), "admin", "password", new_password,
            persist_password, restore_password)

    assert [call[0] for call in calls] == ["change", "persist", "rollback", "restore"]
    assert new_password not in str(error_info.value)
    assert "previous password was restored" in str(error_info.value)


def test_configuration_failure_restores_keycloak_password_through_admin_rest():
    config = _load_config_module()
    restored = []

    def fail_to_persist(unused_password):
        raise IOError("write failed")

    with _keycloak_server() as (server_url, state):
        client = config.KeycloakAdminClient(server_url)
        with pytest.raises(config.KeycloakAdminError):
            config.rotate_admin_password(
                client,
                "admin",
                "password",
                "new-secret-value",
                fail_to_persist,
                lambda: restored.append(True))

    assert state["password"] == "password"
    assert restored == [True]
    assert [request[0] for request in state["requests"]] == [
        "POST", "GET", "PUT", "POST", "PUT", "POST"
    ]


def test_start_extra_service_command_rotates_existing_keycloak_password():
    ctl_py = CTL_PY.read_text(encoding="utf-8")
    assert "class ChangeKeycloakAdminPasswordCmd(Command):" not in ctl_py
    assert "ChangeKeycloakAdminPasswordCmd()" not in ctl_py
    assert "@lock.file_lock('/run/zstack.keycloak.admin-password.lock')" in ctl_py
    assert (
        "write_admin_password(self.admin_password_path, password, 0, zstack_group.gr_gid)"
        not in ctl_py
    )
    assert "rotate_admin_password(" in ctl_py
    assert "copy_sensitive_file_to_peer" in ctl_py
    assert "morph_config_path" not in ctl_py
    assert "render_yaml_scalar" not in ctl_py
    assert "update_yaml_scalar" not in ctl_py

    start_command = re.search(
        r"^class StartExtraServicesCmd\(Command\):.*?(?=^class DiagnoseCmd\(Command\):)",
        ctl_py,
        re.MULTILINE | re.DOTALL,
    ).group(0)
    assert "self.name = 'start-extra-service'" in start_command
    assert (
        "self.sensitive_args = ['--change_admin_password', '--current_admin_password']"
        in start_command
    )
    assert "--change_admin_password" in start_command
    assert "--current_admin_password" in start_command
    assert "args.name != 'iam'" in start_command
    assert "service_instance.start(args.init)" in start_command
    assert "service_instance.change_admin_password(" in start_command

    iam_service = re.search(
        r"^class IamService\(ExtraService\):.*?(?=^class MorphService\(ExtraService\):)",
        ctl_py,
        re.MULTILINE | re.DOTALL,
    ).group(0)
    assert "systemctl restart %s; result=$?; exit $result" in iam_service
    assert "systemctl enable %s; result=$?; exit $result" in iam_service
    assert "systemctl restart morph; result=$?; exit $result" in iam_service


def test_ha_sensitive_copy_uses_same_directory_atomic_replace():
    ctl_py = CTL_PY.read_text(encoding="utf-8")
    copy_method = re.search(
        r"^    def copy_sensitive_file_to_peer\(.*?(?=^class MySqlCommandLineQuery)",
        ctl_py,
        re.MULTILINE | re.DOTALL,
    ).group(0)

    assert "os.path.dirname(dst_path)" in copy_method
    assert "sudo install -m 600" in copy_method
    assert "sudo tee" in copy_method
    assert "mv -f" in copy_method
    assert "remote_path = '/tmp/" not in copy_method
