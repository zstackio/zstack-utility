
import unittest
from zstacklib.utils import form


class Test(unittest.TestCase):

    def test_form(self):
        l1 = form._load(o1)
        assert len(l1) == 2
        assert l1[1]['NAME'] == 'sdaj'
        assert l1[1]['STATE'] == 'blocked'

        l2 = form._load(o2)
        assert len(l2) == 2
        assert l2[1]['NAME'] == 'sdaj'
        assert l2[1]['STATE'] is None

        l3 = form._load(o3)
        assert len(l3) == 0

        l4 = form.load(o4)
        assert len(l4) == 0

        ex = None
        try:
            form._load(o4)
        except Exception as e:
            ex = e

        assert ex is not None


o1 = '''NAME TYPE STATE
cf1e9c4f3d674f159505c234c3e5356b-e7b20bbcad9f4e1499259e5b8ec0eccd lvm running
sdaj disk blocked'''


o2 = '''NAME TYPE STATE
cf1e9c4f3d674f159505c234c3e5356b-e7b20bbcad9f4e1499259e5b8ec0eccd lvm running
sdaj disk'''

o3 = 'NAME TYPE STATE'

o4 = '''NAME TYPE
cf1e9c4f3d674f159505c234c3e5356b-e7b20bbcad9f4e1499259e5b8ec0eccd lvm running
sdaj disk'''

if __name__ == "__main__":
    unittest.main()
