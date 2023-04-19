'''

@author: frank
'''
import unittest
import time
import threading
from zstacklib.utils.thread import ThreadFacade
from zstacklib.utils.thread import AsyncThread


class TestThreadFacade(unittest.TestCase):
    
    def _do(self, name, value=None):
        self.ok = name
        self.value = value;
        
    def test_run_in_thread(self):
        t = ThreadFacade.run_in_thread(self._do, ["ok"], {"value":"world"})
        t.join()
        self.assertEqual("ok", self.ok)
        self.assertEqual("world", self.value)
    
    @AsyncThread
    def _do_async(self, ok, value=None):
        self.async_thread_name = threading.current_thread().getName()
        self.async_ok = ok
        self.async_value = value
        
    def test_async_thread(self):
        t = self._do_async("ok", value="world")
        t.join()
        self.assertEqual('_do_async', self.async_thread_name)
        self.assertEqual("ok", self.async_ok)
        self.assertEqual("world", self.async_value)

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()