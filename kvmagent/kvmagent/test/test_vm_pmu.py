import unittest
import xml.etree.ElementTree as etree

from kvmagent.plugins import vm_plugin


class TestVmPmuConfig(unittest.TestCase):
    def setUp(self):
        self.features = etree.Element("features")

    def test_pmu_off_generates_xml(self):
        class Cmd(object):
            pmu = False

        vm_plugin.make_pmu_feature(Cmd(), self.features)

        pmu = self.features.find("pmu")
        self.assertIsNotNone(pmu)
        self.assertEqual("off", pmu.get("state"))

    def test_pmu_true_generates_no_xml(self):
        class Cmd(object):
            pmu = True

        vm_plugin.make_pmu_feature(Cmd(), self.features)

        self.assertIsNone(self.features.find("pmu"))

    def test_missing_pmu_attr_generates_no_xml(self):
        class Cmd(object):
            pass

        vm_plugin.make_pmu_feature(Cmd(), self.features)

        self.assertIsNone(self.features.find("pmu"))


if __name__ == "__main__":
    unittest.main()
