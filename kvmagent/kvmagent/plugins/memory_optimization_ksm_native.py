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
    """Return the smallest native KSM_SLEEP_MSEC which yields at least the requested sysfs value.

    The supported EL8 vendor script calculates
    ``max(10, configured * 16GiB / MemTotal)`` using integer division, which
    below 16 GiB cannot always reach the value exactly; it is then one
    millisecond longer.
    """
    if (isinstance(policy_msec, bool) or not isinstance(policy_msec, INTEGER_TYPES) or
            policy_msec < 10 or isinstance(memtotal_kb, bool) or
            not isinstance(memtotal_kb, INTEGER_TYPES) or memtotal_kb <= 0):
        raise NativeKsmConfigError('KSM_SLEEP_UNREPRESENTABLE')

    # Find the smallest native setting that reaches the desired integer output.
    native = (policy_msec * memtotal_kb + SLEEP_BASE_KB - 1) // SLEEP_BASE_KB
    return max(native, 1)



def _customer_lines(existing_text):
    """The lines of the file outside the managed block, without the blank line added before it."""
    lines = (existing_text or '').splitlines()
    if sum(1 for line in lines if line == MANAGED_BEGIN) > 1:
        raise NativeKsmConfigError('KSM_CONFIG_MULTIPLE_MANAGED_BLOCKS')
    output = []
    in_managed = False
    for line in lines:
        if line == MANAGED_BEGIN:
            if in_managed:
                raise NativeKsmConfigError('KSM_CONFIG_NESTED_MANAGED_BLOCK')
            in_managed = True
            if output and output[-1] == '':
                output.pop()
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
    return output


def remove_config(existing_text):
    """Take the managed block out, leaving the customer content as it was."""
    output = _customer_lines(existing_text)
    return '\n'.join(output) + '\n' if output else ''


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

    # ksmtuned sources this file as shell: the appended managed block wins over
    # earlier customer assignments without rewriting them.
    output = _customer_lines(existing_text)

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
