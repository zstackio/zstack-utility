'''

@author: YYK
'''
from __future__ import annotations
import pickledb
import os

ZSTACK_FILEDB_DIR="/var/lib/zstack/pickledb/"

class FileDB(object):
    '''Wrap pickledb and provide unified file based database operations'''
    def __init__(self, file_name, is_abs_path=False):
        if not is_abs_path:
            file_path = os.path.join(ZSTACK_FILEDB_DIR, file_name)
        else:
            file_path = file_name
        file_dir = os.path.dirname(file_path)
        if not os.path.exists(file_dir):
            os.makedirs(file_dir, 0o755)
        #force save for each db operation.
        self.file_db = pickledb.PickleDB(file_path, True, None)

    def get(self, key):
        try:
            return self.file_db.get(key)
        except:
            return None
    
    def set(self, key, value):
        self.file_db.set(key, value)
    
    def rem(self, key):
        self.file_db.rem(key)

    def get_all(self):
        return self.file_db.db

    def close(self):
        pass
