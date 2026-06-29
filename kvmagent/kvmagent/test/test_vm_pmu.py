"""
Test PMU configuration in VM XML generation.
See ZSTAC-76375: Kunpeng-920 7270Z kernel panic due to PMMIR_EL1.

Tests verify the PMU feature element generation logic used in
vm_plugin.py make_features(). Since make_features() is a nested
function that cannot be imported directly, we test the core logic
with realistic cmd objects, and also verify the XML structure matches
what libvirt expects.
"""

import unittest
from xml.etree import ElementTree as ET


class TestVmPmuConfig(unittest.TestCase):
    """Test that PMU feature is correctly added to VM XML."""

    PMU_OFF_UNSUPPORTED_DIST = {
        'alinux': ('4',),
    }

    @staticmethod
    def _new_domain_with_features():
        """Create a minimal domain XML root with features element."""
        root = ET.Element("domain")
        features = ET.SubElement(root, "features")
        ET.SubElement(features, "apic")
        ET.SubElement(features, "pae")
        ET.SubElement(features, "acpi")
        return root, features

    @staticmethod
    def is_pmu_off_unsupported_dist(dist_name, version_id):
        version_prefixes = TestVmPmuConfig.PMU_OFF_UNSUPPORTED_DIST.get(dist_name, ())
        return any(version_id.startswith(prefix) for prefix in version_prefixes)

    @classmethod
    def _apply_pmu_logic(cls, cmd, features, dist_name='kylin', version_id='4.19'):
        """Apply the exact same PMU logic as vm_plugin.py make_features().

        This mirrors the production code at vm_plugin.py:
            if hasattr(cmd, 'pmu') and cmd.pmu is False and not is_pmu_off_unsupported_dist():
                e(features, "pmu", attrib={'state': 'off'})
        """
        if hasattr(cmd, 'pmu') and cmd.pmu is False and not cls.is_pmu_off_unsupported_dist(dist_name, version_id):
            ET.SubElement(features, "pmu", attrib={'state': 'off'})

    def test_pmu_off_generates_xml(self):
        """When cmd.pmu is False, <pmu state='off'/> should be in features."""
        root, features = self._new_domain_with_features()

        class Cmd:
            pmu = False

        self._apply_pmu_logic(Cmd(), features)
        pmu = root.find('./features/pmu')
        self.assertIsNotNone(pmu, "PMU element should exist when pmu=False")
        self.assertEqual(pmu.get('state'), 'off', "PMU state should be 'off'")

    def test_pmu_true_no_pmu_element(self):
        """When cmd.pmu is True, no <pmu> element should be added."""
        root, features = self._new_domain_with_features()

        class Cmd:
            pmu = True

        self._apply_pmu_logic(Cmd(), features)
        pmu = root.find('./features/pmu')
        self.assertIsNone(pmu, "PMU element should NOT exist when pmu=True")

    def test_pmu_off_skips_unsupported_dist(self):
        """On PMU-off unsupported dist, pmu=False should not generate <pmu state='off'/>."""
        root, features = self._new_domain_with_features()

        class Cmd:
            pmu = False

        self._apply_pmu_logic(Cmd(), features, dist_name='alinux', version_id='4')
        pmu = root.find('./features/pmu')
        self.assertIsNone(pmu, "PMU element should NOT exist on PMU-off unsupported dist")

    def test_pmu_none_no_pmu_element(self):
        """When cmd.pmu is None, no <pmu> element should be added."""
        root, features = self._new_domain_with_features()

        class Cmd:
            pmu = None

        self._apply_pmu_logic(Cmd(), features)
        pmu = root.find('./features/pmu')
        self.assertIsNone(pmu, "PMU element should NOT exist when pmu=None")

    def test_no_pmu_attr_no_pmu_element(self):
        """When cmd has no pmu attribute, no <pmu> element should be added."""
        root, features = self._new_domain_with_features()

        class Cmd:
            pass

        self._apply_pmu_logic(Cmd(), features)
        pmu = root.find('./features/pmu')
        self.assertIsNone(pmu, "PMU element should NOT exist when cmd has no pmu attr")

    def test_pmu_element_position_in_features(self):
        """PMU element should be inside <features> alongside other elements."""
        root, features = self._new_domain_with_features()

        class Cmd:
            pmu = False

        self._apply_pmu_logic(Cmd(), features)

        children = [child.tag for child in features]
        self.assertIn('pmu', children, "PMU should be a child of features")
        self.assertIn('acpi', children, "ACPI should still be present")
        self.assertIn('apic', children, "APIC should still be present")

    def test_generated_xml_is_valid(self):
        """Verify the full XML output is well-formed and contains expected structure."""
        root, features = self._new_domain_with_features()

        class Cmd:
            pmu = False

        self._apply_pmu_logic(Cmd(), features)

        xml_str = ET.tostring(root, encoding='unicode')
        self.assertIn('<pmu state="off" />', xml_str)
        self.assertIn('<features>', xml_str)


if __name__ == "__main__":
    unittest.main()
