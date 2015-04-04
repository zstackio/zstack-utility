'''

@author: frank
'''
import unittest
from ..utils import shell
import subprocess

class TestShell(unittest.TestCase):

    def test_success(self):
        cmd = shell.ShellCmd('ls')
        cmd()
        shell.ShellCmd('ls')()
        
    def test_success2(self):
        out = shell.ShellCmd("cat /proc/cpuinfo  | grep 'cpu MHz' | tail -n 1")()
        (name, speed) = out.split(':')
        speed = speed.strip()
        print speed
    
    def test_failure(self):
        cmd = shell.ShellCmd('find -name nothing')
        cmd()
        self.assertRaises(subprocess.CalledProcessError)

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()