'''

@author: frank
'''
import unittest
import types
import inspect
from zstacklib.utils import jsonobject

class A(object):
    def __init__(self):
        self.name = "hello"
        self.male = False
        
class C(object):
    def __init__(self):
        self.age = 19
        
class B(A):
    def __init__(self):
        super(B, self).__init__()
        self.address = "home"
        self.lst = [1,2,3]
        self.c = C()
        self.cs = [C(), C()]
        
class Test(unittest.TestCase):
    def test_json(self):
        b = B()
        jstr = jsonobject.dumps(b)
        nb = jsonobject.loads(jstr)
        self.assertEqual(2, len(nb.cs))
        self.assertEqual(3, len(nb.lst))
        self.assertEqual(1, nb.lst[0])
        self.assertEqual('home', nb.address)
        self.assertEqual(19, nb.c.age)
        self.assertEqual('hello', nb.name)
        self.assertFalse(nb.male)
        jstr2 = jsonobject.dumps(nb)
        self.assertEqual(jstr, jstr2)
        jb = jsonobject.loads(jstr)
        print jb.xxxxx
        print jb.lst

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()