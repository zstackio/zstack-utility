"""Keep extension resources alive until the caller finishes the prepared command."""

from contextlib import ExitStack, contextmanager


_command_extensions = {}


def register_extension(extension_name, command_extension):
    registered_extension = _command_extensions.get(extension_name)
    if registered_extension is not None and registered_extension is not command_extension:
        raise ValueError('ImageStore extension is already registered: %s' % extension_name)
    _command_extensions[extension_name] = command_extension


@contextmanager
def prepare_image_add_command(command_line, addons=None, device_id=None):
    if not _command_extensions:
        raise RuntimeError('ImageStore extensions are not configured')
    with ExitStack() as stack:
        for command_extension in _command_extensions.values():
            command_line = stack.enter_context(command_extension.prepare_image_add_command(command_line, addons, device_id))
        yield command_line


@contextmanager
def prepare_image_pull_command(command_line, addons=None):
    if not _command_extensions:
        raise RuntimeError('ImageStore extensions are not configured')
    with ExitStack() as stack:
        for command_extension in _command_extensions.values():
            command_line = stack.enter_context(command_extension.prepare_image_pull_command(command_line, addons))
        yield command_line


@contextmanager
def prepare_volume_backup_command(command_line, addons, device_id):
    if not _command_extensions:
        raise RuntimeError('ImageStore extensions are not configured')
    with ExitStack() as stack:
        for command_extension in _command_extensions.values():
            command_line = stack.enter_context(command_extension.prepare_volume_backup_command(command_line, addons, device_id))
        yield command_line


@contextmanager
def prepare_batch_backup_command(command_line, addons, backup_args, device_ids):
    if not _command_extensions:
        raise RuntimeError('ImageStore extensions are not configured')
    with ExitStack() as stack:
        for command_extension in _command_extensions.values():
            command_line = stack.enter_context(command_extension.prepare_batch_backup_command(command_line, addons, backup_args, device_ids))
        yield command_line
