'''
@author: wenhao.zhang
'''
import os
import hashlib
import tempfile
import unittest
from zstacklib.utils import bash
from zstacklib.utils import log

logger = log.get_logger(__name__)

# This case simulates the behavior of guest tools to check whether it is logically compatible
# with the current or previous versions of guest tools.
# 
# The main purpose of this case is to ensure that the `agent_version` file is compliant.
class TestGuestToolsAgentVersion(unittest.TestCase):
    agent_version_path = ''
    agent_version_directory = ''

    def setUp(self):
        current_path = os.path.dirname(os.path.abspath(__file__))
        self.agent_version_path = os.path.join(current_path, '..', '..', 'ansible', 'agent_version')
        self.agent_version_path = os.path.abspath(self.agent_version_path)
        self.assertTrue(
            os.path.exists(self.agent_version_path),
            'file [%s] is not exists' % self.agent_version_path)
        self.agent_version_directory = os.path.dirname(self.agent_version_path)

    # Test whether GuestTools (v4.2.0+) can parse agent version file 
    def testParseVersionFile(self):
        with open(self.agent_version_path, "r") as agent_version_file:
            text = agent_version_file.read()
        lines = text.splitlines()

        zwatch_latest_version = None
        for line in lines:
            if line.find('zwatch-vm-agent') >= 0:
                zwatch_latest_version = line.split('=')[1]
                break
        self.assertNotEqual(zwatch_latest_version, None)
        self.assertNotEqual(zwatch_latest_version, "")

    # Test whether GuestTools (v1.1.0 ~ 4.1, x86_64 / aarch64 / mips64el) can parse agent version file 
    def testParseVersionFileForGuestTools1_1_0(self):
        def checkParseByBash(pkg_name):
            r_bash, o_bash, _ = bash.bash_roe("grep -w '%s' %s | awk -F '=' '{print $2}'" % (pkg_name, self.agent_version_path))
            self.assertEqual(r_bash, 0)
            lines = o_bash.splitlines()

            self.assertTrue(len(lines) >= 2, "o_bash: [%s] is invalid, pkg_name=%s" % (o_bash, pkg_name))
            # assert not empty
            self.assertNotEqual(lines[0].strip(), "")  # GuestTools 1.1.1 ~ 4.1,  ZStack Cloud 3.9.0 ~ 4.1.x
            self.assertNotEqual(lines[1].strip(), "")  # GuestTools 1.1.0+,  ZStack Cloud 3.8.x

        checkParseByBash('zwatch-vm-agent.linux-amd64')
        checkParseByBash('zwatch-vm-agent.linux-aarch64')
        checkParseByBash('zwatch-vm-agent.linux-mips64el')

    # Whether md5sum of file is equals to agent_version
    def testCheckGuestToolsMd5(self):
        with open(self.agent_version_path, "r") as agent_version_file:
            text = agent_version_file.read()
        lines = text.splitlines()

        def md5InAgentVersionFile(pkg_name):
            for line in lines:
                if line.find('md5-%s' % pkg_name) >= 0:
                    return line.split('=')[1]
            self.fail('agent_version file does not contain md5 of %s' % pkg_name)

        def md5InRealFile(file_path):
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()

        def checkMd5(pkg_name, file_path):
            md5_agent_version = md5InAgentVersionFile(pkg_name)
            md5_real_file = md5InRealFile(file_path)
            self.assertEqual(md5_agent_version, md5_real_file,
                'md5sum of file[%s] is not equals to md5 in agent_version. Please edit agent_version file: md5-%s=%s' %
                        (file_path, pkg_name, md5_real_file))

        checkMd5('zwatch-vm-agent.linux-amd64', os.path.join(self.agent_version_directory, 'zwatch-vm-agent'))
        checkMd5('zwatch-vm-agent.linux-aarch64', os.path.join(self.agent_version_directory, 'zwatch-vm-agent_aarch64'))
        checkMd5('zwatch-vm-agent.linux-mips64el', os.path.join(self.agent_version_directory, 'zwatch-vm-agent_mips64el'))

        # Test when md5 check fail
        temp_directory = tempfile.mkdtemp()
        fake_path = os.path.join(temp_directory, 'fake-zwatch-vm-agent')
        with open(fake_path, 'w+') as f:
            f.write('\x7fELF This is a fake zwatch agent\x00')

        error = False
        try:
            checkMd5('zwatch-vm-agent.linux-amd64', fake_path)
        except AssertionError:
            logger.info('AssertionError is expected')
            error = True
        self.assertTrue(error, 'expect check md5 fail, but nothing happened')

if __name__ == "__main__":
    unittest.main()
