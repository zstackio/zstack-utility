'''

@author: Frank
'''
try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser
import functools
import pprint
import traceback
import hashlib
import os

from contextlib import contextmanager
from zstacklib.utils import bash
from zstacklib.utils import log
from zstacklib.utils import linux
from zstacklib.utils import pycompat

logger = log.get_logger(__name__)


def _md5_of_bash_output(o):
    # shell.get_process 启用 universal_newlines 后，py2 下 bash_ro 返回 bytes、
    # py3 下返回 str。先归一成文本再算 md5，两种解释器结果一致。
    if not isinstance(o, pycompat.string_types):
        o = o.decode("utf-8")
    return hashlib.md5(o.strip().encode("utf-8")).hexdigest()


class Parser(ConfigParser.ConfigParser):
    def get(self, section, option, default=None):
        try:
            return ConfigParser.ConfigParser.get(self, section, option)
        except ConfigParser.NoOptionError:
            return default


def ignoreerror(func):
    @functools.wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            content = traceback.format_exc()
            err = '%s\n%s\nargs:%s' % (str(e), content, pprint.pformat([args, kwargs]))
            logger.warn(err)
    return wrap


class IgnoreError(object):
    def __init__(self):
        pass

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            content = traceback.format_exc()
            err = '%s\n%s\n' % (str(exc_val), content)
            logger.warn(err)


@linux.with_arch(todo_list=['x86_64'])
def isMiniHost():
    r, o = bash.bash_ro("dmidecode -s system-product-name")
    if r != 0:
        return False
    return _md5_of_bash_output(o) in [
        "5fc8d2a363cdadac26f779074aab1a17",
        "39e7b016e11cc67bbdf885c4a1293546",
        "b525fe1f8611ce4583d07b0a2ffa8435",
        "d625b1b46d517889d49616b0b35831af",
        "c9142f6b3d8d911b83eed1eb239e773e",
        ]


def isHyperConvergedHost():
    r, o = bash.bash_ro("bootstrap is_deployed")
    if r != 0 or o.strip() != "true":
        return False
    return True


@contextmanager
def ignore_exception(exception_type, message=None):
    try:
        yield
    except exception_type as ex:
        if message is not None and message not in str(ex):
            raise ex
        logger.debug("exception caught by the ignore_exception func : %s" % str(ex))
