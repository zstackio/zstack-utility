import os
import re
import subprocess
import tempfile
import unittest


class FreshCloudIntentTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="fresh-cloud-intent-")
        self.install_root = os.path.join(self.root, "usr", "local", "zstack")
        self.system_root = os.path.join(self.root, "system")
        self.properties = os.path.join(self.install_root, "apache-tomcat", "webapps", "zstack",
                                       "WEB-INF", "classes", "zstack.properties")
        self.utility_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
        self.offline_installer = os.path.join(self.utility_root, "installation", "install.sh")
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

    def eligible(self, upgrade="n", only="", drop="", keep="", implementation="offline"):
        path = self.offline_installer if implementation == "offline" else self.online_installer
        with open(path) as stream:
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
            for implementation in ("offline", "online"):
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

    def test_installer_modes_and_all_prior_identity_paths_block_fresh_defaults(self):
        identities = (os.path.join(self.install_root, "VERSION"), self.properties,
                      os.path.join(self.system_root, "etc/init.d/zstack"),
                      os.path.join(self.system_root, "usr/lib/systemd/system/zstack.service"),
                      os.path.join(self.system_root, "etc/systemd/system/zstack.service"))
        for implementation in ("offline", "online"):
            for mode in ({"upgrade": "y"}, {"only": "y"}, {"drop": "y"}, {"keep": "y"}):
                with self.subTest(implementation=implementation, mode=mode):
                    self.assertFalse(self.eligible(implementation=implementation, **mode))
            for identity in identities:
                with self.subTest(implementation=implementation, identity=identity):
                    os.makedirs(os.path.dirname(identity), exist_ok=True)
                    with open(identity, "w") as stream:
                        stream.write("existing installation")
                    self.assertFalse(self.eligible(implementation=implementation))
                    os.remove(identity)

    def test_deploydb_arguments_preserve_new_install_and_keep_drop_paths(self):
        for installer in (self.offline_installer, self.online_installer):
            with open(installer) as stream:
                source = stream.read()
            function = re.search(r"(?ms)^cs_deploy_db\(\)\s*\{\n.*?^\}", source).group(0)
            for fresh, drop, keep, expected in (("y", "", "", "--fresh-cloud-bootstrap"),
                                                ("n", "", "", None),
                                                ("n", "y", "", "--drop"),
                                                ("n", "", "y", "--keep-db")):
                with self.subTest(installer=installer, fresh=fresh, drop=drop, keep=keep):
                    call_log = os.path.join(self.root, "ctl-arguments")
                    env = os.environ.copy()
                    env.update(FRESH_CLOUD_BOOTSTRAP=fresh, NEED_DROP_DB=drop, NEED_KEEP_DB=keep,
                               MYSQL_NEW_ROOT_PASSWORD="fixture", MYSQL_ROOT_PASSWORD="fixture",
                               MYSQL_USER_PASSWORD="fixture", MANAGEMENT_IP="127.0.0.1",
                               ZSTACKCTL_INSTALL_LOG=os.path.join(self.root, "ctl.log"),
                               ZSTACK_INSTALL_LOG=os.path.join(self.root, "installer.log"),
                               CALL_LOG=call_log)
                    stubs = '''
traplogger() { :; }
echo_subtitle() { :; }
pass() { :; }
fail() { exit 1; }
zstack-ctl() { printf '%s\\n' "$@" > "$CALL_LOG"; }
'''
                    subprocess.check_call(["bash", "-c", stubs + function + "\ncs_deploy_db"], env=env)
                    with open(call_log) as stream:
                        arguments = stream.read().splitlines()
                    self.assertEqual("deploydb", arguments[0])
                    flags = [arg for arg in arguments if arg in
                             ("--fresh-cloud-bootstrap", "--drop", "--keep-db")]
                    self.assertEqual([expected] if expected else [], flags)


if __name__ == "__main__":
    unittest.main()
