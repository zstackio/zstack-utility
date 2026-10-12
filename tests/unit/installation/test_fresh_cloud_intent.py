import os
import re
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET


class FreshCloudIntentTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fresh-cloud-intent-")
        self.helper = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "../../../installation/fresh_cloud_intent.sh"))
        self.install_root = os.path.join(self.root, "usr", "local", "zstack")
        self.system_root = os.path.join(self.root, "system")
        self.properties = os.path.join(self.install_root, "apache-tomcat", "webapps", "zstack",
                                       "WEB-INF", "classes", "zstack.properties")
        self.utility_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        self.online_installer = os.path.join(self.utility_root, "installation", "online_install.sh")

    @staticmethod
    def function_definition(source):
        match = re.search(r"(?ms)^zstack_is_fresh_cloud_install\(\) \{\n.*?^\}", source)
        if not match:
            raise AssertionError("fresh-cloud predicate function is missing")
        return match.group(0)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.root)

    def eligible(self, upgrade="n", only="", drop="", keep="", implementation="helper"):
        if implementation == "helper":
            with open(self.helper) as stream:
                source = stream.read()
        else:
            with open(self.online_installer) as stream:
                source = stream.read()
        function = self.function_definition(source)
        script = function + '\nzstack_is_fresh_cloud_install "$1" "$2" "$3" "$4" "$5" "$6" "$7"'
        return subprocess.call(["bash", "-c", script, "test", upgrade, only,
                                drop, keep, self.install_root, self.properties, self.system_root]) == 0

    def test_full_install_without_prior_identity_seeds_intent(self):
        self.assertTrue(self.eligible())

    def test_upgrade_only_keep_and_drop_never_seed_intent(self):
        self.assertFalse(self.eligible(upgrade="y"))
        self.assertFalse(self.eligible(only="y"))
        self.assertFalse(self.eligible(drop="y"))
        self.assertFalse(self.eligible(keep="y"))

    def test_online_embedded_predicate_runs_same_tempdir_behavior_matrix(self):
        original = (self.install_root, self.system_root, self.properties)
        try:
            for implementation in ("helper", "online"):
                self.install_root = os.path.join(self.root, implementation, "usr", "local", "zstack")
                self.system_root = os.path.join(self.root, implementation, "system")
                self.properties = os.path.join(self.install_root, "apache-tomcat", "webapps", "zstack",
                                               "WEB-INF", "classes", "zstack.properties")
                self.assertTrue(self.eligible(implementation=implementation))
                self.assertFalse(self.eligible(upgrade="y", implementation=implementation))
                os.makedirs(os.path.dirname(self.properties))
                with open(self.properties, "w") as stream:
                    stream.write("prior identity")
                self.assertFalse(self.eligible(implementation=implementation))
        finally:
            self.install_root, self.system_root, self.properties = original

    def test_existing_install_identity_blocks_intent(self):
        os.makedirs(self.install_root)
        with open(os.path.join(self.install_root, "VERSION"), "w") as stream:
            stream.write("fixture")
        self.assertFalse(self.eligible())

    def test_existing_properties_or_service_blocks_intent(self):
        os.makedirs(os.path.dirname(self.properties))
        with open(self.properties, "w") as stream:
            stream.write("fixture")
        self.assertFalse(self.eligible())
        os.remove(self.properties)
        service = os.path.join(self.system_root, "etc", "init.d", "zstack")
        os.makedirs(os.path.dirname(service))
        with open(service, "w") as stream:
            stream.write("fixture")
        self.assertFalse(self.eligible())

    def test_offline_helper_is_shipped_and_online_installer_embeds_equivalent_predicate(self):
        offline = os.path.join(self.utility_root, "installation", "install.sh")
        with open(offline) as stream:
            offline_source = stream.read()
        self.assertIn('if [ ! -r "$FRESH_CLOUD_INTENT_HELPER" ]; then', offline_source)
        self.assertIn('. "$FRESH_CLOUD_INTENT_HELPER"', offline_source)
        isolated_script = os.path.join(self.root, "install.sh")
        with open(isolated_script, "w") as stream:
            stream.write(offline_source)
        result = subprocess.run(["bash", isolated_script], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(1, result.returncode)
        self.assertIn("Required installer helper is missing", result.stderr)

        with open(self.helper) as stream:
            helper_source = stream.read()
        with open(self.online_installer) as stream:
            online_source = stream.read()
        self.assertEqual(self.function_definition(helper_source),
                         self.function_definition(online_source))
        self.assertNotIn('FRESH_CLOUD_INTENT_HELPER=', online_source)

        build_root = os.path.join(self.utility_root, "zstackbuild")
        project = ET.parse(os.path.join(build_root, "projects", "zstack-buildallinone.xml")).getroot()
        target_xml = ET.tostring(project, encoding="unicode")
        for name in ("${build.dir}", "${allinone.bin.dir}"):
            self.assertIn('file="${zstack.fresh.cloud.intent}" todir="%s"' % name, target_xml)
        for name in ("build.xml", "build.oss.xml"):
            build_xml = ET.parse(os.path.join(build_root, name)).getroot()
            properties = [node for node in build_xml.iter("property")
                          if node.attrib.get("name") == "zstack.fresh.cloud.intent"]
            self.assertEqual(1, len(properties), name)
            self.assertTrue(properties[0].attrib["location"].endswith("installation/fresh_cloud_intent.sh"))


if __name__ == "__main__":
    unittest.main()
