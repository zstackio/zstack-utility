#!/usr/bin/env python
# encoding: utf-8
# for python 2.x

from argparse import ArgumentParser, RawTextHelpFormatter

import os
import hashlib

class AgentVersionItem(object):
    def __init__(self, name):
        self.name = str(name)
        self.md5 = ''
        self.filepath = ''

    @property
    def compatible_text(self):
        return 'compatible-version-of-zwatch-vm-agent.%s=4.2.0' % self.name

    @property
    def md5_text(self):
        return 'md5-zwatch-vm-agent.%s=%s' % (self.name, self.md5)

    def with_filepath(self, filepath):
        self.filepath = filepath
        return self
    
    def calculate_md5(self):
        if not os.path.exists(self.filepath):
            return
        with open(self.filepath, 'r') as f:
            # file size < 15M
            m = hashlib.md5(f.read())
            self.md5 = m.hexdigest()

    def is_valid(self):
        return bool(self.md5)

class AgentVersionBuilder(object):
    def __init__(self, sourcepath, outputpath):
        self.sourcepath = str(sourcepath).strip()
        self.outputpath = str(outputpath).strip()
        self.items = [
            AgentVersionItem('linux-amd64').with_filepath('zwatch-vm-agent'),
            AgentVersionItem('linux-aarch64').with_filepath('zwatch-vm-agent_aarch64'),
            AgentVersionItem('linux-mips64el').with_filepath('zwatch-vm-agent_mips64el'),
            AgentVersionItem('linux-loongarch64').with_filepath('zwatch-vm-agent_loongarch64'),
            AgentVersionItem('freebsd-amd64').with_filepath('zwatch-vm-agent-freebsd')
        ]

    def _read_version_from_source(self):
        version_line = ''
        path = os.path.join(self.sourcepath, 'src', 'zwatch-vm-agent', 'utils', 'config.go')
        with open(path, 'r') as f:
            for l in f.readlines():
                index = l.find('VERSION')
                if index == -1 or l.find('=', index + len('VERSION')) == -1:
                    continue
                version_line = l
                break

        if version_line == '':
            raise Exception('failed to find version in file %s' % path)
        text = version_line.split()[-1]
        if text.startswith('"'):
            text = text[1:-1]
        return text

    def write(self):
        lines_for_compatible = ''
        lines_for_md5 = ''

        for item in self.items:
            item.calculate_md5()
            if not item.is_valid():
                continue
            lines_for_compatible += ('# %s\n' % item.compatible_text) # must start with '#'
            lines_for_md5 += ('%s\n' % item.md5_text)

        with open(self.outputpath, 'w') as f:
            f.write('''zwatch-vm-agent=%s

# This agent version text file is generated by agent_version_generator_py2 script,
# and the comments below are due to compatibility (version <= 4.2).
# Please DO NOT DELETE or MODIFY them!
# See more in ZSTAC-41487
#
%s
%s''' % (self._read_version_from_source(), lines_for_compatible, lines_for_md5))

if __name__ == '__main__':
    parser = ArgumentParser("agent_version_generator_py2", description=__doc__, formatter_class=RawTextHelpFormatter)
    parser.add_argument('-s', '--sourcepath', required=True, default="", help='the source path for zstack-zwatch project')
    parser.add_argument('-o', '--outputpath', required=True, default="", help='the agent version file path for output')
    args = parser.parse_args()

    builder = AgentVersionBuilder(args.sourcepath, args.outputpath)
    builder.write()
