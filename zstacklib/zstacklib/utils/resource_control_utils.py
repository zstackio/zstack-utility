import os
import re

MAX_CPU_TOKEN_DIGITS = 10
KIBIBYTE = 1024
MEBIBYTE = KIBIBYTE * KIBIBYTE
CPU_ONLINE = '/sys/devices/system/cpu/online'


class ResourceControlError(Exception):
    pass


def mkdir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def read(path):
    with open(path, 'rb') as stream:
        return text(stream.read())


def write(path, value):
    with open(path, 'wb') as stream:
        stream.write(value.encode('ascii'))


def normalize(value):
    value = text(value).strip()
    if not value:
        return ''
    ranges = []
    for token in value.split(','):
        if re.match(r'^[0-9]+$', token):
            if len(token) > MAX_CPU_TOKEN_DIGITS:
                raise ResourceControlError('CPU set item[%s] is too large' % token)
            cpu = int(token)
            ranges.append((cpu, cpu))
            continue
        match = re.match(r'^([0-9]+)-([0-9]+)$', token)
        if (not match or len(match.group(1)) > MAX_CPU_TOKEN_DIGITS
                or len(match.group(2)) > MAX_CPU_TOKEN_DIGITS):
            raise ResourceControlError('CPU set item[%s] has an invalid format' % token)
        start = int(match.group(1))
        end = int(match.group(2))
        if start > end:
            raise ResourceControlError('CPU set range[%s] has an invalid order' % token)
        ranges.append((start, end))

    merged = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return ','.join(str(start) if start == end else '%s-%s' % (start, end) for start, end in merged)


def count(value):
    count = 0
    for token in normalize(value).split(','):
        if '-' not in token:
            count += 1
            continue
        start, end = token.split('-', 1)
        count += int(end) - int(start) + 1
    return count


def is_subset(candidate, allowed):
    allowed_ranges = ranges(allowed)
    allowed_index = 0
    for start, end in ranges(candidate):
        while (allowed_index < len(allowed_ranges) and allowed_ranges[allowed_index][1] < start):
            allowed_index += 1
        if (allowed_index >= len(allowed_ranges)
                or allowed_ranges[allowed_index][0] > start
                or allowed_ranges[allowed_index][1] < end):
            return False
    return True


def ranges(value):
    result = []
    for token in normalize(value).split(','):
        if '-' in token:
            start, end = token.split('-', 1)
            result.append((int(start), int(end)))
        elif token:
            cpu = int(token)
            result.append((cpu, cpu))
    return result


def under_root(root, path):
    if path != root and not path.startswith(root + os.sep):
        raise ResourceControlError('Control group path[%s] is outside root[%s]' % (path, root))


def decode_mount_path(value):
    return value.replace('\\040', ' ').replace('\\011', '\t').replace('\\012', '\n').replace('\\134', '\\')


def text(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace')
    return value


def validate_cpu_set(cpu_set):
    normalized = normalize('' if cpu_set is None else cpu_set)
    if not normalized:
        raise ResourceControlError('CPU set cannot be empty')
    online = normalize(read(CPU_ONLINE))
    if not is_subset(normalized, online):
        raise ResourceControlError('CPU set[%s] contains CPUs outside online CPU set[%s]' % (normalized, online))
    return normalized
