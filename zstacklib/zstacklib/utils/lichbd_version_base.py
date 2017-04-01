import os
import os.path
import errno
import functools
import traceback
import pprint
import threading
from zstacklib.utils import log

import zstacklib.utils.lichbd_version_const as lichbdconst

logger = log.get_logger(__name__)
class LichbdVersionBase(object):
	LICHBD_CMD_POOL_CREATE = 'lichbd mkpool'
	LICHBD_CMD_POOL_LS = 'lichbd lspools'
	LICHBD_CMD_POOL_RM = 'lichbd rmpool'
	LICHBD_CMD_VOL_CREATE = 'lichbd create'
	LICHBD_CMD_VOL_COPY = 'lichbd copy'
	LICHBD_CMD_VOL_IMPORT = 'lichbd import'
	LICHBD_CMD_VOL_EXPORT = 'lichbd export'
	LICHBD_CMD_VOL_RM = 'lichbd rm'
	LICHBD_CMD_VOL_MV = 'lichbd mv'
	LICHBD_CMD_VOL_INFO = 'lichbd info'
	LICHBD_CMD_SNAP_CREATE = 'lichbd snap create'
	LICHBD_CMD_SNAP_LS = 'lichbd snap ls'
	LICHBD_CMD_SNAP_RM = 'lichbd snap remove'
	LICHBD_CMD_SNAP_CLONE = 'lichbd clone'
	LICHBD_CMD_SNAP_ROLLBACK = 'lichbd snap rollback'
	LICHBD_CMD_SNAP_PROTECT= 'lichbd snap protect'
	LICHBD_CMD_SNAP_UNPROTECT = 'lichbd snap unprotect'
	def __init__(self):
		super(LichbdVersionBase, self).__init__()

#359 is the internalid of Q4 2016
class LichbdVersion359(LichbdVersionBase):
	def __init__(self):
		super(LichbdVersion359, self).__init__()

class LichbdVersionLatest(LichbdVersionBase):
	LICHBD_CMD_POOL_CREATE = 'lichbd pool create'
	LICHBD_CMD_POOL_LS = 'lichbd pool ls'
	LICHBD_CMD_POOL_RM = 'lichbd pool rm'
	LICHBD_CMD_VOL_CREATE = 'lichbd vol create'
	LICHBD_CMD_VOL_COPY = 'lichbd vol copy'
	LICHBD_CMD_VOL_IMPORT = 'lichbd vol import'
	LICHBD_CMD_VOL_EXPORT = 'lichbd vol export'
	LICHBD_CMD_VOL_RM = 'lichbd vol rm'
	LICHBD_CMD_VOL_MV = 'lichbd vol mv'
	LICHBD_CMD_VOL_INFO = 'lichbd vol info'
	LICHBD_CMD_SNAP_RM = 'lichbd snap rm'
	LICHBD_CMD_SNAP_CLONE = 'lichbd snap clone'
	def __init__(self):
		super(LichbdVersionLatest, self).__init__()


def get_lichbd_version_class(lichbd_version):
	version_class = None
	logger.warn("lichbd version is %s" % lichbd_version)
	if(lichbd_version <= lichbdconst.LichbdVersionConst.LICHBD_VERSION_Q4_2016):
		version_class = LichbdVersion359()
	else:
		version_class = LichbdVersionLatest()
	return version_class