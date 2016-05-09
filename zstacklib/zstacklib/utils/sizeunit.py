'''

@author: frank
'''

import os

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
        
def get_size(size):
    size = size.lower()

    if size.isdigit():
        return size

    def strip_size_unit():
        return float(size[:-1])

    if size.endswith('b') or size.endswith('B'):
        return Byte.toByte(strip_size_unit())
    elif size.endswith('k') or size.endswith('K'):
        return KiloByte.toByte(strip_size_unit())
    elif size.endswith('m') or size.endswith('M'):
        return MegaByte.toByte(strip_size_unit())
    elif size.endswith('g') or size.endswith('G'):
        return GigaByte.toByte(strip_size_unit())
    elif size.endswith('t') or size.endswith('T'):
        return TeraByte.toByte(strip_size_unit())

