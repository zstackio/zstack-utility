# -*- coding: utf-8 -*-
import unittest
import simplejson

from zstacklib.utils import multipath


class TestMultiPathConf(unittest.TestCase):
    def test(self):
        test_write_conf()


def test_write_conf():
    cmd_str = '{"blacklist":[{"device":[{"vendor":"IBM"},{"product":"3S42"}]},{"wwid":"36001405913ad48768b84db39bbcc5cb0"}]}'
    blacklist = simplejson.loads(cmd_str)["blacklist"]

    assert multipath.write_multipath_conf('multipath.conf', blacklist)
    assert not multipath.write_multipath_conf('multipath.conf')
    with open("multipath.conf",
         "r") as fd:
        text1 = multipath.parse_multipath_conf(fd)
    with open("multipath.conf.out", "r") as fd1:
        text2 = multipath.parse_multipath_conf(fd1)
    assert cmp(text1, text2) == 0

    #In multipath1.conf, we set the features "1 Queue" of the device_ if_ no_ path"， no_ path_ Retry 60,
    # we configure our default device, which will override features "1 Queue"_ if_ no_ path"， no_ path_ Retry 60,
    # change to feature 0 no_ path_ retry fail
    assert multipath.write_multipath_conf('multipath1.conf', blacklist)
    assert not multipath.write_multipath_conf('multipath1.conf', blacklist)
    with open("multipath1.conf",
         "r") as fd:
        text3 = multipath.parse_multipath_conf(fd)
    with open("multipath1.conf.out", "r") as fd1:
        text4 = multipath.parse_multipath_conf(fd1)
    assert cmp(text3, text4) == 0

    assert multipath.write_multipath_conf('multipath2.conf')
    assert not multipath.write_multipath_conf('multipath2.conf')
    with open("multipath2.conf",
         "r") as fd:
        text5 = multipath.parse_multipath_conf(fd)
    with open("multipath2.conf.out", "r") as fd1:
        text6 = multipath.parse_multipath_conf(fd1)
    assert cmp(text5, text6) == 0

    assert multipath.write_multipath_conf('multipath3.conf')
    assert not multipath.write_multipath_conf('multipath3.conf')
    with open("multipath3.conf",
              "r") as fd:
        text7 = multipath.parse_multipath_conf(fd)
    with open("multipath3.conf.out", "r") as fd1:
        text8 = multipath.parse_multipath_conf(fd1)
    assert cmp(text7, text8) == 0

    assert multipath.write_multipath_conf('multipath4.conf')
    assert not multipath.write_multipath_conf('multipath4.conf')
    with open("multipath4.conf",
              "r") as fd:
        text9 = multipath.parse_multipath_conf(fd)
    with open("multipath4.conf.out", "r") as fd1:
        text10 = multipath.parse_multipath_conf(fd1)
    assert cmp(text9, text10) == 0

if __name__ == '__main__':
    unittest.main()
