import unittest
import re
import json

from zstacklib.utils import qmp

# ------------------------------------------------

test_qmp_command1 = '{"execute": "object-add", "arguments":{ "qom-type": "colo-compare", "id": "comp","props": { "primary_in": ' \
                    '"primary-in-c","secondary_in": "secondary-in-s","outdev":"primary-out-c", "iothread": "iothread", "vnet_hdr_support": true } } }'

# ------------------------------------------------
except_qmp_command1 = '{"execute": "object-add", "arguments": {"vnet_hdr_support": true, "iothread": "iothread", "secondary_in": ' \
                      '"secondary-in-s", "primary_in": "primary-in-c", "id": "comp", "qom-type": "colo-compare", "outdev": "primary-out-c"}}'

# ------------------------------------------------
test_qmp_command2 = '{"execute": "object-add", "arguments":{ "qom-type": "filter-mirror", "id": "fm-%s", "props": { "netdev": "hostnet%s",' \
                    ' "queue": "tx", "outdev": "zs-mirror-%s", "vnet_hdr_support": true} } }'


# ------------------------------------------------


class Test(unittest.TestCase):
    def test_function_is_bad_vm_root_volume(self):
        def remove_command_props_parameter(cmd):
            if re.match(r'.*object-add.*arguments.*props.*', cmd):
                j_cmd = json.loads(cmd)
                props = j_cmd.get("arguments").get("props")
                j_cmd.get("arguments").pop("props")
                j_cmd.get("arguments").update(props)
                cmd = json.dumps(j_cmd)
            return cmd

        assert remove_command_props_parameter(test_qmp_command1) == except_qmp_command1
        assert qmp.qmp_subcmd("6.2.0", test_qmp_command2) == remove_command_props_parameter(test_qmp_command2)


if __name__ == "__main__":
    unittest.main()
