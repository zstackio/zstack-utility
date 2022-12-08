import os

Out_flag = True

class PytestExtension(object):

    def setup_class(self):
        pass

    def teardown_class(self):
        if Out_flag:
            os._exit(0)
        os._exit(1)


def ztest_decorater(func):
    def wrapper(*args, **kwargs):
        global Out_flag
        last_out_flag = Out_flag
        Out_flag = False
        func(*args, **kwargs)
        Out_flag = last_out_flag

    return wrapper
