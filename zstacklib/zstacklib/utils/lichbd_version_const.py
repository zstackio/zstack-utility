class LichbdVersionConst(object):
    LICHBD_VERSION_Q4_2016 = 375
    def __init__(self):
        super(LichbdVersionConst, self).__init__()
class ConstError(TypeError):pass
def __setattr__(self, name, value):
    if self.__dict__.has_key(name):
        raise self.ConstError, "Can't rebind const (%s)" %name
    self.__dict__[name]=value