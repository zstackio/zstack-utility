'''

@author: Frank
'''
import ConfigParser
import functools
import pprint
import traceback
import hashlib
import os

from zstacklib.utils import bash
from zstacklib.utils import log

logger = log.get_logger(__name__)


class Parser(ConfigParser.SafeConfigParser):
    def get(self, section, option, default=None):
        try:
            return ConfigParser.SafeConfigParser.get(self, section, option)
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


def isMiniHost():
    r, o = bash.bash_ro("dmidecode -s system-product-name")
    if r != 0:
        return False
    return hashlib.md5(o.decode("utf-8").strip().encode("utf-8")).hexdigest() in [
        "5fc8d2a363cdadac26f779074aab1a17",
        "39e7b016e11cc67bbdf885c4a1293546",
        "b525fe1f8611ce4583d07b0a2ffa8435",
        "d625b1b46d517889d49616b0b35831af",
        "c9142f6b3d8d911b83eed1eb239e773e",
        ]


def isHyperConvergedHost():
    hyper_converged_dir = "/usr/local/hyperconverged"
    if os.path.exists(hyper_converged_dir):
        return True
    else:
        return False
