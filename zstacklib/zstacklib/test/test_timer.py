'''

@author: root
'''
from zstacklib.utils import thread
import time
import threading
import sys

def hello(name, name2):
    print name
    print name2
    return True

@thread.AsyncThread
def th():
    while True:
        print 'xxx'
        time.sleep(1)
        
if __name__ == '__main__':
    #t = thread.timer(0.5, hello, args=['ni hao', 'world'])
    #t.start()
    #t = thread.timer(0.5, hello, args=['ni', 'hao'])
    #t.start()
    #t.cancel()
    #print 'xxxxxxxxxxxxxx'
    sys.exit(0)