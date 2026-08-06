import io
import json
import os
import stat
import tempfile

try:
    from urllib import quote, urlencode
    from urllib2 import HTTPError, Request, URLError, urlopen
except ImportError:
    from urllib.error import HTTPError, URLError
    from urllib.parse import quote, urlencode
    from urllib.request import Request, urlopen


try:
    text_type = unicode
except NameError:
    text_type = str


def _to_text(value):
    if isinstance(value, text_type):
        return value
    return value.decode('utf-8')


def _urlencode(values):
    encoded_values = {}
    for key, value in values.items():
        encoded_values[key] = value.encode('utf-8') if isinstance(value, text_type) else value
    return urlencode(encoded_values)


def validate_admin_password(password):
    password = _to_text(password)
    if not password:
        raise ValueError('Keycloak admin password cannot be empty')
    if '\n' in password or '\r' in password:
        raise ValueError('Keycloak admin password cannot contain line breaks')
    return password


class KeycloakAdminError(Exception):
    pass


def read_admin_password(path, default_password):
    default_password = validate_admin_password(default_password)
    if not os.path.isfile(path):
        return default_password

    with io.open(path, 'r', encoding='utf-8') as stream:
        password = stream.read().rstrip('\r\n')
    return validate_admin_password(password) if password else default_password


def snapshot_file(path):
    if not os.path.exists(path):
        return None

    current = os.stat(path)
    with io.open(path, 'r', encoding='utf-8') as stream:
        content = stream.read()
    return {
        'content': content,
        'mode': stat.S_IMODE(current.st_mode),
        'owner_uid': current.st_uid,
        'owner_gid': current.st_gid,
    }


def _write_text(path, content, mode=None, owner_uid=None, owner_gid=None):
    directory = os.path.dirname(path)
    fd, temporary_path = tempfile.mkstemp(prefix='.keycloak-', dir=directory)
    try:
        with io.open(fd, 'w', encoding='utf-8', closefd=True) as stream:
            stream.write(content)
        if mode is None:
            current = os.stat(path)
            os.chmod(temporary_path, stat.S_IMODE(current.st_mode))
            os.chown(temporary_path, current.st_uid, current.st_gid)
        else:
            os.chmod(temporary_path, mode)
        if owner_uid is not None and owner_gid is not None:
            os.chown(temporary_path, owner_uid, owner_gid)
        os.rename(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


def restore_file(path, snapshot):
    if snapshot is None:
        if os.path.exists(path):
            os.remove(path)
        return

    _write_text(
        path,
        snapshot['content'],
        snapshot['mode'],
        snapshot['owner_uid'],
        snapshot['owner_gid'])


def write_admin_password(path, password, owner_uid=None, owner_gid=None):
    password = validate_admin_password(password)
    if not os.path.isdir(os.path.dirname(path)):
        raise ValueError('Keycloak configuration directory does not exist')
    _write_text(path, password + '\n', 0o640, owner_uid, owner_gid)


class KeycloakAdminClient(object):
    def __init__(self, server_url, timeout=10, request_opener=None):
        self.server_url = server_url.rstrip('/')
        self.timeout = timeout
        self.request_opener = request_opener or urlopen

    @staticmethod
    def _request_body(value):
        if isinstance(value, text_type):
            return value.encode('utf-8')
        return value

    def _request(self, operation, method, path, body=None, headers=None):
        request = Request(
            self.server_url + path,
            data=self._request_body(body) if body is not None else None,
            headers=headers or {})
        request.get_method = lambda: method
        try:
            response = self.request_opener(request, timeout=self.timeout)
            try:
                return response.getcode(), response.read()
            finally:
                response.close()
        except HTTPError as e:
            status = e.code
            try:
                e.close()
            except Exception:
                pass
            raise KeycloakAdminError('%s failed with HTTP %s' % (operation, status))
        except URLError:
            raise KeycloakAdminError('%s failed because Keycloak is unavailable' % operation)
        except (IOError, OSError):
            raise KeycloakAdminError('%s failed because Keycloak is unavailable' % operation)
        except Exception:
            raise KeycloakAdminError('%s failed because Keycloak is unavailable' % operation)

    @staticmethod
    def _parse_json(operation, body):
        try:
            if not isinstance(body, text_type):
                body = body.decode('utf-8')
            return json.loads(body)
        except (TypeError, ValueError):
            raise KeycloakAdminError('%s returned an invalid response' % operation)

    def authenticate(self, username, password):
        password = validate_admin_password(password)
        body = _urlencode({
            'grant_type': 'password',
            'client_id': 'admin-cli',
            'username': _to_text(username),
            'password': password,
        })
        operation = 'Keycloak admin authentication'
        status, response_body = self._request(
            operation,
            'POST',
            '/realms/master/protocol/openid-connect/token',
            body,
            {'Content-Type': 'application/x-www-form-urlencoded'})
        if status != 200:
            raise KeycloakAdminError('%s returned HTTP %s' % (operation, status))
        response = self._parse_json(operation, response_body)
        token = response.get('access_token') if isinstance(response, dict) else None
        if not token:
            raise KeycloakAdminError('%s did not return an access token' % operation)
        return token

    def find_exact_user_id(self, token, username):
        username = _to_text(username)
        query = _urlencode({'username': username, 'exact': 'true'})
        operation = 'Keycloak admin user lookup'
        status, response_body = self._request(
            operation,
            'GET',
            '/admin/realms/master/users?' + query,
            headers={'Authorization': 'Bearer %s' % token})
        if status != 200:
            raise KeycloakAdminError('%s returned HTTP %s' % (operation, status))
        response = self._parse_json(operation, response_body)
        matches = [
            user for user in response
            if isinstance(user, dict) and user.get('username') == username and user.get('id')
        ] if isinstance(response, list) else []
        if len(matches) != 1:
            raise KeycloakAdminError(
                '%s expected exactly one matching user, found %s' % (operation, len(matches)))
        return matches[0]['id']

    def reset_password(self, token, user_id, password):
        password = validate_admin_password(password)
        body = json.dumps({
            'type': 'password',
            'value': password,
            'temporary': False,
        }, ensure_ascii=True)
        operation = 'Keycloak admin password reset'
        quoted_user_id = quote(_to_text(user_id).encode('utf-8'), safe='')
        status, unused_response_body = self._request(
            operation,
            'PUT',
            '/admin/realms/master/users/%s/reset-password' % quoted_user_id,
            body,
            {
                'Authorization': 'Bearer %s' % token,
                'Content-Type': 'application/json',
            })
        if status != 204:
            raise KeycloakAdminError('%s returned HTTP %s' % (operation, status))

    def change_password(self, username, current_password, new_password):
        current_password = validate_admin_password(current_password)
        new_password = validate_admin_password(new_password)
        current_token = self.authenticate(username, current_password)
        user_id = self.find_exact_user_id(current_token, username)
        self.reset_password(current_token, user_id, new_password)
        try:
            new_token = self.authenticate(username, new_password)
        except KeycloakAdminError:
            try:
                self.reset_password(current_token, user_id, current_password)
            except KeycloakAdminError:
                raise KeycloakAdminError(
                    'Keycloak rejected the new password and automatic rollback failed')
            raise KeycloakAdminError(
                'Keycloak rejected the new password; the previous password was restored')
        return user_id, new_token

    def rollback_password(self, username, user_id, token, previous_password):
        self.reset_password(token, user_id, previous_password)
        self.authenticate(username, previous_password)


def rotate_admin_password(client, username, current_password, new_password,
                          persist_password, restore_password):
    user_id, rollback_token = client.change_password(
        username, current_password, new_password)
    try:
        persist_password(new_password)
    except Exception:
        rollback_failed = False
        try:
            client.rollback_password(
                username, user_id, rollback_token, current_password)
        except Exception:
            rollback_failed = True
        try:
            restore_password()
        except Exception:
            rollback_failed = True
        if rollback_failed:
            raise KeycloakAdminError(
                'Keycloak password configuration failed and automatic rollback did not complete')
        raise KeycloakAdminError(
            'Keycloak password configuration failed; the previous password was restored')
