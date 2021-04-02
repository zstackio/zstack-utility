# -*- coding: utf-8 -*-
from zstacklib.utils import multipath

if __name__ == '__main__':
    multipath.write_multipath_conf('kvmagent/test/multipath.conf')
    with open("kvmagent/test/multipath.conf",
         "r") as fd:
        text1 = multipath.parse_multipath_conf(fd)
    with open("kvmagent/test/multipath.conf.out", "r") as fd1:
        text2 = multipath.parse_multipath_conf(fd1)
    assert cmp(text1, text2) == 0

    #In multipath1.conf, we set the features "1 Queue" of the device_ if_ no_ path"， no_ path_ Retry 60,
    # we configure our default device, which will override features "1 Queue"_ if_ no_ path"， no_ path_ Retry 60,
    # change to feature 0 no_ path_ retry fail
    multipath.write_multipath_conf('kvmagent/test/multipath1.conf')
    with open("kvmagent/test/multipath1.conf",
         "r") as fd:
        text3 = multipath.parse_multipath_conf(fd)
    with open("kvmagent/test/multipath1.conf.out", "r") as fd1:
        text4 = multipath.parse_multipath_conf(fd1)
    assert cmp(text3, text4) == 0

    multipath.write_multipath_conf('kvmagent/test/multipath2.conf')
    with open("kvmagent/test/multipath2.conf",
         "r") as fd:
        text5 = multipath.parse_multipath_conf(fd)
    with open("kvmagent/test/multipath2.conf.out", "r") as fd1:
        text6 = multipath.parse_multipath_conf(fd1)
    assert cmp(text5, text6) == 0