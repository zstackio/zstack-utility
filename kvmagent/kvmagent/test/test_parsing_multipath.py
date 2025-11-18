# -*- coding: utf-8 -*-
import unittest
import simplejson
import difflib

from zstacklib.utils import multipath, linux


class TestGuestToolsAgentVersion(unittest.TestCase):
    def test(self):
        test_write_conf()


def write_multipath_conf(path, blacklist=None):
    with multipath.MultipathConfigUpdater(path) as updater:
        default_config_changed = updater.set_default_config()
        if blacklist:
            updater.config_section("blacklist", blacklist)

    if default_config_changed:
        print("multipath default config have been taken over by us\n")
        print("\n".join(difflib.ndiff(updater.old_config_str.splitlines(), updater.new_config_str.splitlines())))
    return updater.modified


def test_write_conf():
    cmd_str = '{"blacklist":[{"device":[{"vendor":"IBM"},{"product":"3S42"}]},{"wwid":"36001405913ad48768b84db39bbcc5cb0"}]}'
    blacklist = simplejson.loads(cmd_str)["blacklist"]

    assert write_multipath_conf('multipath.conf', blacklist)
    assert not write_multipath_conf('multipath.conf')
    with open("multipath.conf",
         "r") as fd:
        text1 = multipath.parse_multipath_conf(fd)
    with open("multipath.conf.out", "r") as fd1:
        text2 = multipath.parse_multipath_conf(fd1)
    assert text1 == text2

    #In multipath1.conf, we set the features "1 Queue" of the device_ if_ no_ path"， no_ path_ Retry 60,
    # we configure our default device, which will override features "1 Queue"_ if_ no_ path"， no_ path_ Retry 60,
    # change to feature 0 no_ path_ retry fail
    assert write_multipath_conf('multipath1.conf', blacklist)
    assert not write_multipath_conf('multipath1.conf', blacklist)
    with open("multipath1.conf",
         "r") as fd:
        text3 = multipath.parse_multipath_conf(fd)
    with open("multipath1.conf.out", "r") as fd1:
        text4 = multipath.parse_multipath_conf(fd1)
    assert text3 == text4

    assert write_multipath_conf('multipath2.conf')
    assert not write_multipath_conf('multipath2.conf')
    with open("multipath2.conf",
         "r") as fd:
        text5 = multipath.parse_multipath_conf(fd)
    with open("multipath2.conf.out", "r") as fd1:
        text6 = multipath.parse_multipath_conf(fd1)
    assert text5 == text6

    assert write_multipath_conf('multipath3.conf')
    assert not write_multipath_conf('multipath3.conf')
    with open("multipath3.conf",
              "r") as fd:
        text7 = multipath.parse_multipath_conf(fd)
    with open("multipath3.conf.out", "r") as fd1:
        text8 = multipath.parse_multipath_conf(fd1)
    assert text7 == text8

    assert write_multipath_conf('multipath4.conf')
    assert not write_multipath_conf('multipath4.conf')
    with open("multipath4.conf",
              "r") as fd:
        text9 = multipath.parse_multipath_conf(fd)
    with open("multipath4.conf.out", "r") as fd1:
        text10 = multipath.parse_multipath_conf(fd1)
    assert text9 == text10
    assert write_multipath_conf('multipath5.conf')
    assert not write_multipath_conf('multipath5.conf')

if __name__ == '__main__':
    unittest.main()
