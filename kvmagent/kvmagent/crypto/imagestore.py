import json
import os
import shlex
import tempfile
from contextlib import contextmanager

from kvmagent.crypto import secret


KEY_AGENT_PROVIDER = 'unix:///var/run/key-agent/key-agent.sock'


@contextmanager
def temporary_json(content):
    descriptor, path = tempfile.mkstemp(prefix='zstcli-encryption-', suffix='.json')
    try:
        with os.fdopen(descriptor, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(content, stream)
        yield path
    finally:
        secret.remove_sensitive_file(path, 'imagestore.temporary_json')


@contextmanager
def with_encryption_json(command_line, content):
    if content is None:
        yield command_line
        return
    with temporary_json(content) as path:
        yield '%s -encryption-json-file %s -secret-channel-provider %s' % (
            command_line, shlex.quote(path), KEY_AGENT_PROVIDER)
