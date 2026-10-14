# -*- coding: utf-8 -*-
"""Pure helpers for translating KSM policy to a vendor ksmtuned config.

This module deliberately does not execute the configuration as shell input or
perform service/sysfs writes.  Those operations remain in the privileged Agent
under its existing host writer lock and operation journal.
"""

import re

try:
    INTEGER_TYPES = (int, long)  # noqa: F821 (Python 2 Agent runtime)
except NameError:
    INTEGER_TYPES = (int,)


MANAGED_BEGIN = '# BEGIN ZSTACK MEMORY OPTIMIZATION'
MANAGED_END = '# END ZSTACK MEMORY OPTIMIZATION'
SLEEP_BASE_KB = 16 * 1024 * 1024


class NativeKsmConfigError(ValueError):
    pass


def parse_memtotal_kb(meminfo):
    """Extract one valid MemTotal value from procfs-compatible text."""
    matches = re.findall(r'(?m)^MemTotal:\s*([0-9]+)\s+kB\s*$', meminfo or '')
    if len(matches) != 1 or int(matches[0]) <= 0:
        raise NativeKsmConfigError('KSM_MEMTOTAL_UNKNOWN')
    return int(matches[0])


def native_sleep_msec(policy_msec, memtotal_kb):
    """Return a native KSM_SLEEP_MSEC which yields the requested sysfs value.

    The supported EL8 vendor script calculates
    ``max(10, configured * 16GiB / MemTotal)`` using integer division.  We
    reject values it cannot represent exactly rather than acknowledging a
    different applied sleep interval.
    """
    if (isinstance(policy_msec, bool) or not isinstance(policy_msec, INTEGER_TYPES) or
            policy_msec < 10 or isinstance(memtotal_kb, bool) or
            not isinstance(memtotal_kb, INTEGER_TYPES) or memtotal_kb <= 0):
        raise NativeKsmConfigError('KSM_SLEEP_UNREPRESENTABLE')

    # Find the smallest native setting that reaches the desired integer output.
    native = (policy_msec * memtotal_kb + SLEEP_BASE_KB - 1) // SLEEP_BASE_KB
    native = max(native, 1)
    effective = max(10, native * SLEEP_BASE_KB // memtotal_kb)
    if effective != policy_msec:
        raise NativeKsmConfigError('KSM_SLEEP_UNREPRESENTABLE')
    return native


def _managed_expected_values(pages_to_scan, native_sleep):
    return {
        'KSM_NPAGES_MIN': pages_to_scan,
        'KSM_NPAGES_MAX': pages_to_scan,
        'KSM_NPAGES_BOOST': 0,
        'KSM_NPAGES_DECAY': 0,
        'KSM_SLEEP_MSEC': native_sleep,
        'KSM_THRES_COEF': 100,
        'KSM_THRES_CONST': 2048,
    }


def _custom_native_assignments(text):
    """Read native keys without evaluating shell syntax or changing user bytes."""
    managed_keys = set(_managed_expected_values(1, 1))
    result = {}
    for number, line in enumerate((text or '').splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        match = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)$', stripped)
        if not match or match.group(1) not in managed_keys:
            continue
        key, raw_value = match.groups()
        value_match = re.match(r'^([0-9]+)\s*(?:#.*)?$', raw_value)
        if not value_match:
            raise NativeKsmConfigError('KSM_CONFIG_CUSTOM_VALUE_UNKNOWN:%s:%d' %
                                       (key, number))
        value = int(value_match.group(1))
        result[key] = value
    return result


def render_config(existing_text, revision, pages_to_scan, native_sleep):
    """Append one managed block, preserving all customer content outside it.

    The block sets fixed min/max and zero boost/decay so the vendor adaptive
    loop becomes a constant-rate scanner.  THRES_COEF=100 prevents its normal
    low-memory stop predicate for nonnegative qemu committed memory.
    """
    if (isinstance(revision, bool) or not isinstance(revision, INTEGER_TYPES) or revision < 1 or
            isinstance(pages_to_scan, bool) or not isinstance(pages_to_scan, INTEGER_TYPES) or
            pages_to_scan < 1 or isinstance(native_sleep, bool) or
            not isinstance(native_sleep, INTEGER_TYPES) or native_sleep < 1):
        raise NativeKsmConfigError('KSM_CONFIG_VALUE_INVALID')

    text = existing_text or ''
    lines = text.splitlines()
    if sum(1 for line in lines if line == MANAGED_BEGIN) > 1:
        raise NativeKsmConfigError('KSM_CONFIG_MULTIPLE_MANAGED_BLOCKS')
    outside_managed = []
    in_existing_managed = False
    for line in lines:
        if line == MANAGED_BEGIN:
            in_existing_managed = True
            continue
        if line == MANAGED_END:
            in_existing_managed = False
            continue
        if not in_existing_managed:
            outside_managed.append(line)
    custom_values = _custom_native_assignments('\n'.join(outside_managed))
    expected_values = _managed_expected_values(pages_to_scan, native_sleep)
    for key, value in custom_values.items():
        if key in expected_values and value != expected_values[key]:
            raise NativeKsmConfigError('KSM_CONFIG_CUSTOM_VALUE_CONFLICT:%s' % key)
    output = []
    in_managed = False
    for line in lines:
        if line == MANAGED_BEGIN:
            if in_managed:
                raise NativeKsmConfigError('KSM_CONFIG_NESTED_MANAGED_BLOCK')
            in_managed = True
            continue
        if line == MANAGED_END:
            if not in_managed:
                raise NativeKsmConfigError('KSM_CONFIG_UNMATCHED_MANAGED_END')
            in_managed = False
            continue
        if not in_managed:
            output.append(line)
    if in_managed:
        raise NativeKsmConfigError('KSM_CONFIG_UNTERMINATED_MANAGED_BLOCK')

    # The vendor script sources this file; values are validated decimal
    # literals and operation identity is intentionally not interpolated.
    block = [
        MANAGED_BEGIN,
        '# CONFIG_REVISION=%d' % revision,
        'KSM_NPAGES_MIN=%d' % pages_to_scan,
        'KSM_NPAGES_MAX=%d' % pages_to_scan,
        'KSM_NPAGES_BOOST=0',
        'KSM_NPAGES_DECAY=0',
        'KSM_SLEEP_MSEC=%d' % native_sleep,
        'KSM_THRES_COEF=100',
        'KSM_THRES_CONST=2048',
        MANAGED_END,
    ]
    if output and output[-1] != '':
        output.append('')
    output.extend(block)
    return '\n'.join(output) + '\n'


def managed_config_values(text):
    """Read the final managed block without sourcing arbitrary shell syntax."""
    lines = (text or '').splitlines()
    starts = [i for i, line in enumerate(lines) if line == MANAGED_BEGIN]
    if not starts:
        return None
    if len(starts) != 1:
        raise NativeKsmConfigError('KSM_CONFIG_MULTIPLE_MANAGED_BLOCKS')
    start = starts[0]
    try:
        end = lines.index(MANAGED_END, start + 1)
    except ValueError:
        raise NativeKsmConfigError('KSM_CONFIG_UNTERMINATED_MANAGED_BLOCK')
    if any(line == MANAGED_BEGIN for line in lines[start + 1:end]):
        raise NativeKsmConfigError('KSM_CONFIG_NESTED_MANAGED_BLOCK')
    values = {}
    for line in lines[start + 1:end]:
        match = re.match(r'^([A-Z_][A-Z0-9_]*)=([0-9]+)$', line)
        if match:
            key, value = match.groups()
            if key in values:
                raise NativeKsmConfigError('KSM_CONFIG_DUPLICATE_KEY:%s' % key)
            values[key] = int(value)
    required = set(('KSM_NPAGES_MIN', 'KSM_NPAGES_MAX', 'KSM_NPAGES_BOOST',
                    'KSM_NPAGES_DECAY', 'KSM_SLEEP_MSEC', 'KSM_THRES_COEF',
                    'KSM_THRES_CONST'))
    if set(values) != required:
        raise NativeKsmConfigError('KSM_CONFIG_MANAGED_BLOCK_INCOMPLETE')
    revision_match = re.match(r'^# CONFIG_REVISION=([1-9][0-9]*)$', lines[start + 1])
    if not revision_match:
        raise NativeKsmConfigError('KSM_CONFIG_REVISION_UNKNOWN')
    values['CONFIG_REVISION'] = int(revision_match.group(1))
    return values
