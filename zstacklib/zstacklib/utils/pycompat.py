'''双模兼容层：同时支持 python2.7 与 python3。'''

import sys

PY2 = sys.version_info[0] == 2
PY3 = not PY2

if PY2:
    string_types = (basestring,)          # noqa: F821
    integer_types = (int, long)           # noqa: F821
    text_type = unicode                   # noqa: F821
    binary_type = str
else:
    string_types = (str,)
    integer_types = (int,)
    text_type = str
    binary_type = bytes


def iteritems(d):
    return d.iteritems() if PY2 else iter(d.items())


def iterkeys(d):
    return d.iterkeys() if PY2 else iter(d.keys())


def itervalues(d):
    return d.itervalues() if PY2 else iter(d.values())


def has_key(d, k):
    return k in d


def with_metaclass(meta, *bases):
    '''双模元类注入。

    py3 不支持 `__metaclass__` 类属性，而 `metaclass=` 关键字是 py3-only 语法，
    会打断 py2。此函数通过临时基类在两种解释器下都完成元类注入。
    '''
    if not bases:
        bases = (object,)
    return meta("_NewBase", bases, {})
