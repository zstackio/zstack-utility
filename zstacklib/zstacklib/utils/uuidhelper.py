'''

@author: frank
'''

from uuid import uuid4

class UUID(object):
    '''
    classdocs
    '''
    @staticmethod
    def uuid():
        return str(uuid4()).replace('-', '')

def uuid():
    return str(uuid4()).replace('-', '')

def to_concise_uuid(uuidstr):
    return uuidstr.replace('-', '')

def to_full_uuid(uuidstr):
    return '%s-%s-%s-%s-%s' % (uuidstr[0:8], uuidstr[8:12], uuidstr[12:16], uuidstr[16:20], uuidstr[20:])

def to_simplify_uuid(uuidstr):
    return '%s%s%s%s%s' % (uuidstr[0:8], uuidstr[9:13], uuidstr[14:18], uuidstr[19:23], uuidstr[24:])


def get_vm_uuid():
    return str(uuid4())
