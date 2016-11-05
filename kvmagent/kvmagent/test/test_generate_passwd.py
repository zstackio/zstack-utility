'''

@author: mingjian
'''
from kvmagent import kvmagent
from kvmagent.plugins import generate_passwd
from zstacklib.utils import log
import os

logger = log.get_logger(__name__)

if __name__ == "__main__":
    logger.debug("test")
    test = ChangePasswd()
    test.passwd="password"
    test.account="root"
    test.image="image.qcow2"
    test.generate_passwd()