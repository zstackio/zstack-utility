import re
import subprocess
import xml.etree.ElementTree as etree


QEMU_NS = 'http://libvirt.org/schemas/domain/qemu/1.0'
COMMANDLINE_TAGS = ('qemu:commandline', '{%s}commandline' % QEMU_NS)
ARG_TAGS = ('qemu:arg', '{%s}arg' % QEMU_NS)
MIGRATION_PROPERTY = 'ramfb.x-migrate='


def supports_migration(binary):
    try:
        result = subprocess.run([binary, '-device', 'ramfb,help'],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = (result.stdout or '') + '\n' + (result.stderr or '')
    return result.returncode == 0 and re.search(r'^\s*x-migrate\s*=', output, re.M) is not None


def _commandlines(root):
    return [node for node in root if node.tag in COMMANDLINE_TAGS]


def _is_migration_pair(first, second):
    return (first.tag in ARG_TAGS and second.tag in ARG_TAGS and
            first.get('value') == '-global' and
            second.get('value', '').startswith(MIGRATION_PROPERTY))


def _migration_values(root):
    values = []
    for commandline in _commandlines(root):
        nodes = list(commandline)
        for first, second in zip(nodes, nodes[1:]):
            if _is_migration_pair(first, second):
                values.append(second.get('value'))
    return values


def _append_values(root, values):
    if not values:
        return
    commandlines = _commandlines(root)
    if commandlines:
        commandline = commandlines[0]
    else:
        # The VM builder uses literal prefixes until its final serialization.
        tag = 'qemu:commandline' if root.get('xmlns:qemu') == QEMU_NS else COMMANDLINE_TAGS[1]
        commandline = etree.SubElement(root, tag)
    tag = 'qemu:arg' if commandline.tag == 'qemu:commandline' else ARG_TAGS[1]
    for value in values:
        etree.SubElement(commandline, tag, value='-global')
        etree.SubElement(commandline, tag, value=value)


def enable_migration(root):
    if not any(model.get('type') == 'ramfb' for model in root.findall('devices/video/model')):
        return False
    if _migration_values(root):
        return False
    binary = root.findtext('devices/emulator')
    if not binary or not supports_migration(binary):
        return False
    _append_values(root, [MIGRATION_PROPERTY + 'on'])
    return True


def restore_migration(root, saved):
    # The saved stream fixes this property; current host capability cannot
    # change it when restoring an older memory snapshot.
    values = _migration_values(saved)
    for commandline in _commandlines(root):
        nodes = list(commandline)
        removed = False
        index = 0
        while index + 1 < len(nodes):
            first, second = nodes[index:index + 2]
            if _is_migration_pair(first, second):
                commandline.remove(first)
                commandline.remove(second)
                removed = True
                index += 2
            else:
                index += 1
        if removed and len(commandline) == 0:
            root.remove(commandline)
    _append_values(root, values)
