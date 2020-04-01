import sqlite3


class Sqlite(object):
    def __init__(self, db_path):
        self.db_path = db_path

    def __enter__(self):
        self.connect = sqlite3.connect(self.db_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.connect.close()

    def execute(self, *args, **kwargs):
        with self.connect:
            return self.connect.execute(*args, **kwargs)

