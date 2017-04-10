import zstacklib.utils.lichbd_version_base as lichbdbase

import os
import os.path
import errno
import functools
import traceback
import pprint
import threading
from zstacklib.utils import log
import zstacklib.utils.shell as shell

logger = log.get_logger(__name__)

class VersionFactory(object):
	LICHBD_VERSION = None
	versionClass = None
	def __init__(self):
		self.LICHBD_VERSION = shell.call("/opt/fusionstack/lich/sbin/lichd -v | grep InternalID | awk '{print $2}'").strip()
		self.initVersionClass()

	def initVersionClass(self):
		self.versionNum = None
		try:
			self.versionNum = long(self.LICHBD_VERSION)
		except:
			#375 is the first internalid of lichbd new commands
			self.versionNum = 375
		VersionFactory.versionClass = lichbdbase.get_lichbd_version_class(self.versionNum)

def get_lichbd_version_class():
	#if not initialized
	if(VersionFactory.versionClass == None):
		#initialize
		VersionFactory()
	return VersionFactory.versionClass
