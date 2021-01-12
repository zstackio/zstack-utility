'''

@author: zaifeng.wang
'''

import mock
import unittest
import zstacklib
from zstacklib.utils import lvm
from zstacklib.utils import bash


class Test(unittest.TestCase):

    def test_function_is_bad_vm_root_volume(self):

        def mock_shell_output(path):
            with open(path,'r') as r:
                lines=r.read()
            bash.bash_o = mock.Mock(return_value = lines)
        
        def test_function_works_or_not(expect_is_bad_volume):
            is_bad_volume = lvm.is_bad_vm_root_volume("/dev/0af3ac2a9388489d8dcb0f3bf89f1af1/84c16257085b40de9823dc79d8de18f7")
            self.assertEqual(is_bad_volume, expect_is_bad_volume)

        mock_shell_output("volume_not_exist.txt")
        test_function_works_or_not(False)

        mock_shell_output("good_running_vloume.txt")
        test_function_works_or_not(False)

        mock_shell_output("bad_blocked_vloume.txt")
        test_function_works_or_not(True)

        mock_shell_output("bad_output.txt")
        test_function_works_or_not(False)

if __name__ == "__main__":
    unittest.main()