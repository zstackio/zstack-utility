'''

@author: frank
'''

import os
import re

b = 1
k = b * 1024
m = k * 1024
g = m * 1024
t = g * 1024

class Byte(object):
    '''
    classdocs
    '''
    @staticmethod
    def toByte(s):
        return s
    @staticmethod
    def toKiloByte(s):
        return (s/(k/b))
    @staticmethod
    def toMegaByte(s):
        return (s/(m/b))
    @staticmethod
    def toGigaByte(s):
        return (s/(g/b))
    @staticmethod
    def toTeraByte(s):
        return (s/(t/b))

class KiloByte(object):
    '''
    classdocs
    '''
    @staticmethod
    def toByte(s):
        return (s*(k/b))
    @staticmethod
    def toKiloByte(s):
        return s
    @staticmethod
    def toMegaByte(s):
        return (s/(m/k))
    @staticmethod
    def toGigaByte(s):
        return (s/(g/k))
    @staticmethod
    def toTeraByte(s):
        return (s/(t/k))
    
class MegaByte(object):
    '''
    classdocs
    '''
    @staticmethod
    def toByte(s):
        return (s*(m/b))
    @staticmethod
    def toKiloByte(s):
        return (s*(m/k))
    @staticmethod
    def toMegaByte(s):
        return s
    @staticmethod
    def toGigaByte(s):
        return (s/(g/m))
    @staticmethod
    def toTeraByte(s):
        return (s/(t/m))

class GigaByte(object):
    '''
    classdocs
    '''
    @staticmethod
    def toByte(s):
        return (s*(g/b))
    @staticmethod
    def toKiloByte(s):
        return (s*(g/k))
    @staticmethod
    def toMegaByte(s):
        return (s*(g/m))
    @staticmethod
    def toGigaByte(s):
        return s
    @staticmethod
    def toTeraByte(s):
        return (s/(t/g))

class TeraByte(object):
    '''
    classdocs
    '''
    @staticmethod
    def toByte(s):
        return (s*(t/b))
    @staticmethod
    def toKiloByte(s):
        return (s*(t/k))
    @staticmethod
    def toMegaByte(s):
        return (s*(t/m))
    @staticmethod
    def toGigaByte(s):
        return (s*(t/g))
    @staticmethod
    def toTeraByte(s):
        return s

# for unit lookup, in upper cases.
units = {
    "B": 1,
    "K": 1024,    "KIB": 1024,
    "M": 1024**2, "MIB": 1024**2,
    "G": 1024**3, "GIB": 1024**3,
    "T": 1024**4, "TIB": 1024**4,
}

def get_size(size):
    """convert a size string to bytes
    get_size("1024")     -> 1024,
    get_size("1024K")    -> 1048576,
    get_size("1.5K")     -> 1536,
    get_size("1024 K")   -> 1048576,
    get_size("1024 KiB") -> 1048576,
    """
    if size.isdigit():
        return int(size)

    def do_get_size(num, unit):
        u = units[unit]
        if num.find('.') == -1:
            return int(num) * u
        return int(float(num) * u)

    s = size.strip().upper()
    if s.find(' ') == -1:
        num, unit = re.sub(r"([\d.]+)", r"\1 ", s).split()
    else:
        num, unit = s.split()

    try:
        return do_get_size(num, unit)
    except KeyError:
	raise Exception('unknown size unit[%s]' % size)
