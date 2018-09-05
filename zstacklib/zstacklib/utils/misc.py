'''

@author: Frank
'''
import ConfigParser
import functools
import pprint
import traceback

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