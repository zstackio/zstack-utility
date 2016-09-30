'''

@author: Frank
'''
import ConfigParser

class Parser(ConfigParser.SafeConfigParser):
    def get(self, section, option, default=None):
        try:
            return ConfigParser.SafeConfigParser.get(self, section, option)
        except ConfigParser.NoOptionError:
            return default