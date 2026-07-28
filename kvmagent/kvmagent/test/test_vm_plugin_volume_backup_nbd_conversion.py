import contextlib
import json
import os
import sys
import types
import unittest


def _identity_decorator(*args, **kwargs):
    if args and callable(args[0]) and len(args) == 1 and not kwargs:
        return args[0]
    return lambda func: func


def _module(name, path=None):
    module = types.ModuleType(name)
    if path:
        module.__path__ = [path]
    sys.modules[name] = module
    return module


def _install_import_stubs():
    package_dir = os.path.dirname(os.path.dirname(__file__))

    kvmagent_pkg = _module('kvmagent', package_dir)
    kvmagent_mod = _module('kvmagent.kvmagent')

    class AgentCommand(object):
        pass

    class AgentResponse(object):
        def __init__(self):
            self.success = True
            self.error = None

    kvmagent_mod.AgentCommand = AgentCommand
    kvmagent_mod.AgentResponse = AgentResponse
    kvmagent_mod.replyerror = _identity_decorator
    kvmagent_pkg.kvmagent = kvmagent_mod

    _module('kvmagent.plugins', os.path.join(package_dir, 'plugins'))

    zstacklib_pkg = _module('zstacklib')
    utils_pkg = _module('zstacklib.utils')
    zstacklib_pkg.utils = utils_pkg

    class Logger(object):
        def warn(self, *args, **kwargs):
            pass

    for name in ['bash', 'jsonobject', 'linux', 'qemu_img', 'report', 'shell', 'traceable_shell']:
        module = _module('zstacklib.utils.' + name)
        setattr(utils_pkg, name, module)

    log_mod = _module('zstacklib.utils.log')
    log_mod.get_logger = lambda name: Logger()
    log_mod.sensitive_fields = _identity_decorator
    utils_pkg.log = log_mod
    utils_pkg.report.log = log_mod
    utils_pkg.report.linux = utils_pkg.linux

    utils_pkg.bash.bash_progress_1 = lambda *args, **kwargs: (None, None, None)
    utils_pkg.bash.bash_r = lambda *args, **kwargs: 0
    utils_pkg.bash.bash_roe = lambda *args, **kwargs: (0, '', '')
    utils_pkg.bash.in_bash = _identity_decorator
    utils_pkg.linux.kill_process = lambda *args, **kwargs: None
    utils_pkg.linux.rm_file_force = lambda path: os.remove(path) if os.path.exists(path) else None
    utils_pkg.linux.shellquote = lambda value: value
    utils_pkg.qemu_img.subcmd = lambda name: 'qemu-img %s' % name


_install_import_stubs()

from kvmagent.plugins import volume_backup_nbd_conversion as vbnc


class AttrDict(dict):
    __getattr__ = dict.get


class FakeQsd(object):
    def __init__(self, root, name, blockdevs, exports, secret_file, secret_id):
        self.name = name
        self.blockdevs = blockdevs
        self.exports = exports
        self.secret_file = secret_file
        self.secret_id = secret_id
        self.work_dir = os.path.join(root, name)
        self.socket_path = os.path.join(self.work_dir, 'nbd.sock')
        self.cleaned = False
        os.makedirs(self.work_dir)
        for filename in ['nbd.sock', 'qsd.pid', 'qsd.log']:
            open(os.path.join(self.work_dir, filename), 'w').close()

    def url(self, export_name):
        return 'nbd+unix:///%s?socket=%s' % (export_name, self.socket_path)

    def cleanup(self):
        self.cleaned = True


class FakeConversionSession(vbnc.VolumeBackupNbdConversionSession):
    """Real session logic, but QSD processes and the key-agent secret channel
    are faked so run() can be exercised end-to-end off a real KVM host."""

    instances = []

    def __init__(self, cmd):
        self.started_qsds = []
        FakeConversionSession.instances.append(self)
        super(FakeConversionSession, self).__init__(cmd)

    def _start_qsd(self, name, blockdevs, exports, secret_file=None, secret_id=None):
        qsd = FakeQsd(self.task_dir, name, blockdevs, exports, secret_file, secret_id)
        self.qsds.append(qsd)
        self.started_qsds.append(qsd)
        return qsd

def _idx(install_path):
    return int(install_path.rsplit('node-', 1)[-1])


class TestVolumeBackupNbdConversion(unittest.TestCase):
    def setUp(self):
        FakeConversionSession.instances = []
        self.calls = []
        self.check_runs = []
        # forest data-plane state
        self.forest_verbs = []
        self.forest_commands = []
        self.forest_requests = {}
        self.all_install_paths = []
        self.dag_nodes = []
        self.target_chain = None
        self.export_port = 21001
        self.import_port = 22002
        self.commit_reply = None
        # qemu state
        self.measure_count = 0
        self.check_count = 0
        self.fail_convert_index = None
        self.source_encryption_by_index = {}
        self.secret_channel_count = 0

        self._orig_call = getattr(vbnc.shell, 'call', None)
        self._orig_check_run = getattr(vbnc.shell, 'check_run', None)
        self._orig_subcmd = getattr(vbnc.qemu_img, 'subcmd', None)
        self._orig_shellquote = getattr(vbnc.linux, 'shellquote', None)
        self._orig_luks_secret_channel = vbnc.volume_secret.luks_secret_channel
        vbnc.shell.call = self._call
        vbnc.shell.check_run = self._check_run
        vbnc.qemu_img.subcmd = lambda name: 'qemu-img %s' % name
        vbnc.linux.shellquote = lambda value: value
        vbnc.volume_secret.luks_secret_channel = self._luks_secret_channel

    def tearDown(self):
        self._restore(vbnc.shell, 'call', self._orig_call)
        self._restore(vbnc.shell, 'check_run', self._orig_check_run)
        self._restore(vbnc.qemu_img, 'subcmd', self._orig_subcmd)
        self._restore(vbnc.linux, 'shellquote', self._orig_shellquote)
        vbnc.volume_secret.luks_secret_channel = self._orig_luks_secret_channel

    @staticmethod
    def _restore(module, attr, original):
        if original is None:
            if hasattr(module, attr):
                delattr(module, attr)
        else:
            setattr(module, attr, original)

    # ---- shell mocks -------------------------------------------------------

    @contextlib.contextmanager
    def _luks_secret_channel(self, encrypted_dek):
        if not encrypted_dek:
            yield None
            return
        secret_file = '/tmp/test-vbk-secret-%s' % self.secret_channel_count
        self.secret_channel_count += 1
        yield secret_file

    def _call(self, command):
        self.calls.append(command)
        if command.startswith(vbnc.ImageStoreClient.ZSTORE_CLI_BIN):
            return self._forest_call(command)
        if command.startswith('qemu-img measure'):
            self.measure_count += 1
            return json.dumps({'fully-allocated': 1048576 + self.measure_count})
        if command.startswith('qemu-img check'):
            self.check_count += 1
            return json.dumps({'image-end-offset': 2097152 + self.check_count})
        if command.startswith('qemu-img info'):
            for index, encrypted in self.source_encryption_by_index.items():
                if 'file.export=sexport-%s' % index in command:
                    return json.dumps({'format': 'qcow2', 'encrypted': encrypted})
        raise Exception('unexpected shell.call: %s' % command)

    def _check_run(self, command):
        self.check_runs.append(command)
        if command.startswith('qemu-img convert'):
            convert_index = len([c for c in self.check_runs if c.startswith('qemu-img convert')]) - 1
            if convert_index == self.fail_convert_index:
                raise Exception('injected qemu-img convert failure')
        return 0

    def _forest_call(self, command):
        tokens = command.split()
        url = tokens[tokens.index('-url') + 1]
        verb = tokens[tokens.index('forest') + 1]
        path = tokens[tokens.index('-args-json-file') + 1]
        with open(path) as fd:
            request = json.load(fd)
        self.forest_verbs.append(verb)
        self.forest_commands.append(command)
        self.forest_requests[verb] = {'url': url, 'request': request}
        if verb == 'export-prepare':
            return json.dumps(self._export_response())
        if verb == 'import-prepare':
            return json.dumps(self._import_response(request))
        if verb == 'import-commit':
            return json.dumps(self._commit_response(request))
        if verb == 'import-abort':
            return json.dumps({})
        raise Exception('unexpected forest verb: %s' % verb)

    def _export_response(self):
        nodes = [self._export_node(n['installPath'], n['parentInstallPath'],
                                   n['virtualSize'], n['arch'])
                 for n in self.dag_nodes]
        return {'port': self.export_port, 'nodes': nodes}

    @staticmethod
    def _export_node(install_path, parent=None, virtual_size=64 * 1024 * 1024, arch='x86_64'):
        node = {
            'installPath': install_path,
            'exportName': 'sexport-%s' % _idx(install_path),
            'virtualSize': virtual_size,
            'arch': arch,
        }
        if parent:
            node['parentNodeId'] = parent
        return node

    def _import_response(self, request):
        nodes = [{'nodeId': n['nodeId'], 'exportName': 'timport-%s' % _idx(n['nodeId'])}
                 for n in request['nodes']]
        return {'port': self.import_port, 'nodes': nodes}

    def _commit_response(self, request):
        if self.commit_reply is not None:
            return self.commit_reply
        install_paths = dict((old, 'zstore://%s/new-%s' % (self.target_chain, _idx(old)))
                             for old in request['imageEndOffsets'].keys())
        return {'installPaths': install_paths}

    # ---- fixtures ----------------------------------------------------------

    @staticmethod
    def _node(index, parent=None, source_encrypted=False, arch='x86_64'):
        """A source DAG node as the *agent* would report it in export-prepare.
        `source_encrypted` is a test-only marker driving the qemu-img info probe
        mock (the command no longer carries per-node source encryption)."""
        return {
            'installPath': 'zstore://chain/node-%s' % index,
            'parentInstallPath': None if parent is None else 'zstore://chain/node-%s' % parent,
            'virtualSize': 64 * 1024 * 1024,
            'arch': arch,
            'source_encrypted': source_encrypted,
        }

    @staticmethod
    def _cmd(leaf_install_paths, target_encrypted, encryption=True, upload_concurrency=0,
             task_uuid='task-vbk-test', **overrides):
        cmd = {
            'taskUuid': task_uuid,
            'bsAgentHost': 'agent.host.test',
            'bsAgentPort': 8001,
            'nbdHost': 'nbd.host.test',
            'targetChainName': 'targetchain-uuid',
            'targetEncrypted': target_encrypted,
            'uploadConcurrency': upload_concurrency,
            'leafInstallPaths': leaf_install_paths,
        }
        if encryption:
            cmd['encryptedDek'] = 'sealed-dek'
        cmd.update(overrides)
        return AttrDict(cmd)

    def _prepare_dag(self, nodes):
        """Wire the harness so export-prepare returns this whole DAG, and return
        the leaf installPaths the command must carry (nodes with no children)."""
        self.dag_nodes = nodes
        self.all_install_paths = [n['installPath'] for n in nodes]
        parents = set(n['parentInstallPath'] for n in nodes if n['parentInstallPath'])
        for n in nodes:
            if n.get('source_encrypted') is not None:
                self.source_encryption_by_index[_idx(n['installPath'])] = n['source_encrypted']
        return [n['installPath'] for n in nodes if n['installPath'] not in parents]

    def _session(self, nodes, target_encrypted, **kw):
        leaves = self._prepare_dag(nodes)
        cmd = self._cmd(leaves, target_encrypted, **kw)
        self.target_chain = cmd['targetChainName']
        return FakeConversionSession(cmd)

    @staticmethod
    def _linear(count, source_encrypted=False):
        return [TestVolumeBackupNbdConversion._node(
            i, None if i == 0 else i - 1, source_encrypted=source_encrypted)
            for i in range(count)]

    def _run(self, session):
        try:
            return session.run()
        finally:
            session.cleanup()

    @staticmethod
    def _source_qsd(session):
        return [qsd for qsd in session.started_qsds if qsd.name == 'source'][0]

    @staticmethod
    def _qcow_blockdevs(qsd):
        return [b for b in qsd.blockdevs if b['driver'] == 'qcow2']

    def _convert_cmds(self):
        return [c for c in self.check_runs if c.startswith('qemu-img convert')]

    def _create_cmds(self):
        return [c for c in self.check_runs if c.startswith('qemu-img create')]

    def _rebase_cmds(self):
        return [c for c in self.check_runs if c.startswith('qemu-img rebase')]

    def _run_entrypoint(self, cmd):
        session_class = vbnc.VolumeBackupNbdConversionSession
        vbnc.VolumeBackupNbdConversionSession = FakeConversionSession
        try:
            return vbnc.convert_volume_backup_nbd_forest(cmd)
        finally:
            vbnc.VolumeBackupNbdConversionSession = session_class

    # ---- end-to-end contract ----------------------------------------------

    def test_forked_dag_happy_path_preserves_protocol_and_cleans_up(self):
        nodes = [self._node(0), self._node(1, 0), self._node(2, 1),
                 self._node(3, 2), self._node(4, 2)]
        leaves = self._prepare_dag(nodes)
        cmd = self._cmd(leaves, True, upload_concurrency=4)
        self.target_chain = cmd['targetChainName']

        install_paths = self._run_entrypoint(cmd)
        session = FakeConversionSession.instances[-1]

        self.assertEqual(['export-prepare', 'import-prepare', 'import-commit'],
                         self.forest_verbs)
        export_request = self.forest_requests['export-prepare']['request']
        self.assertEqual({'zstore://chain/node-3', 'zstore://chain/node-4'},
                         set(export_request['leafInstallPaths']))

        import_request = self.forest_requests['import-prepare']['request']
        import_nodes = import_request['nodes']
        self.assertEqual(set(self.all_install_paths),
                         set(node['nodeId'] for node in import_nodes))
        self.assertEqual(dict((node['installPath'], node['parentInstallPath'] or '')
                              for node in nodes),
                         dict((node['nodeId'], node['parentNodeId']) for node in import_nodes))
        self.assertTrue(all(node['name'] == self.target_chain for node in import_nodes))
        self.assertTrue(all(node['carrierSize'] > 0 for node in import_nodes))

        commit_request = self.forest_requests['import-commit']['request']
        self.assertEqual(import_nodes, commit_request['nodes'])
        self.assertEqual(set(self.all_install_paths),
                         set(commit_request['imageEndOffsets']))
        self.assertTrue(all(offset > 0
                            for offset in commit_request['imageEndOffsets'].values()))
        self.assertEqual(4, commit_request['uploadConcurrency'])

        for command in self.forest_commands:
            self.assertIn(' -url agent.host.test:8001 ', ' %s ' % command)
            self.assertNotIn('nbd.host.test', command)
            self.assertNotIn('-rootca', command)
            self.assertNotIn('https', command)

        expected_paths = dict((path, 'zstore://%s/new-%s' %
                               (self.target_chain, _idx(path)))
                              for path in self.all_install_paths)
        self.assertEqual(expected_paths, install_paths)
        self.assertEqual(5, len(self._convert_cmds()))
        self.assertIn('-B nbd+unix:///target-2?socket=', self._convert_cmds()[3])
        self.assertIn('-B nbd+unix:///target-2?socket=', self._convert_cmds()[4])
        self.assertEqual(1, len([qsd for qsd in session.started_qsds
                                 if qsd.name == 'target-backing-2']))
        self.assertIsNone(session.task_dir)
        self.assertTrue(all(qsd.cleaned for qsd in session.started_qsds))

    def test_convert_failure_aborts_once_and_cleans_up(self):
        leaves = self._prepare_dag(self._linear(5))
        cmd = self._cmd(leaves, True)
        self.target_chain = cmd['targetChainName']
        self.fail_convert_index = 2

        with self.assertRaises(Exception) as ctx:
            self._run_entrypoint(cmd)

        self.assertIn('injected qemu-img convert failure', str(ctx.exception))
        self.assertEqual(1, self.forest_verbs.count('import-abort'))
        self.assertNotIn('import-commit', self.forest_verbs)
        abort_request = self.forest_requests['import-abort']['request']
        self.assertEqual('task-vbk-test', abort_request['taskUuid'])
        self.assertEqual(set(self.all_install_paths), set(abort_request['installPaths']))
        session = FakeConversionSession.instances[-1]
        self.assertIsNone(session.task_dir)
        self.assertTrue(all(qsd.cleaned for qsd in session.started_qsds))

    def test_commit_rejects_duplicate_install_paths(self):
        session = self._session(self._linear(2), False)
        self.commit_reply = {'installPaths': {
            'zstore://chain/node-0': 'zstore://targetchain-uuid/dup',
            'zstore://chain/node-1': 'zstore://targetchain-uuid/dup',
        }}
        with self.assertRaises(Exception) as ctx:
            self._run(session)
        self.assertIn('duplicate', str(ctx.exception))

    def test_encrypted_target_requires_dek(self):
        with self.assertRaises(Exception) as ctx:
            self._session(self._linear(1), True, encryption=False)
        self.assertIn('encryptedDek', str(ctx.exception))

    # ---- qemu-img mechanics ------------------------------------------------

    def test_plain_to_encrypted_builds_encrypted_target_chain(self):
        """Plain source -> encrypted target: source read plain, every target
        create/convert/rebase carries the LUKS target secret, and children back
        onto the freshly-converted parent carrier."""
        session = self._session(self._linear(5), True)
        offsets = session.run()
        try:
            self.assertEqual(5, len(offsets))
            self.assertEqual(5, len(self._create_cmds()))
            self.assertEqual(5, len(self._convert_cmds()))
            self.assertEqual(4, len(self._rebase_cmds()))
            self.assertTrue(all(' -n ' in c for c in self._convert_cmds()))
            self.assertTrue(all('--target-image-opts' in c for c in self._convert_cmds()))
            self.assertTrue(all(' -u ' in c for c in self._create_cmds()))
            self.assertTrue(all('cluster_size=16384' in c for c in self._create_cmds()))
            self.assertTrue(all('target_luks_sec' in c for c in
                                self._create_cmds() + self._convert_cmds() + self._rebase_cmds()))
            self.assertNotIn('-B ', self._convert_cmds()[0])
            self.assertIn('-B nbd+unix:///target-0?socket=', self._convert_cmds()[1])
            # target endpoint comes from the import-prepare reply, not the command
            for index, command in enumerate(self._create_cmds()):
                self.assertIn('nbd://nbd.host.test:%s/timport-%s' % (self.import_port, index), command)
            source_qcow = self._qcow_blockdevs(self._source_qsd(session))
            self.assertTrue(all('encrypt' not in b for b in source_qcow))
            backing = [q for q in session.started_qsds if q.name.startswith('target-backing-')]
            self.assertTrue(all('encrypt' in self._qcow_blockdevs(q)[0] for q in backing))
            self.assertTrue(all(q.blockdevs[0]['server']['type'] == 'inet' for q in backing))
            self.assertFalse(any(q.name.startswith('target-carrier-') for q in session.started_qsds))
        finally:
            session.cleanup()

    def test_encrypted_to_plain_uses_source_secret_only(self):
        session = self._session(self._linear(5, source_encrypted=True), False)
        try:
            self.assertEqual(5, len(session.run()))
            source_qsd = self._source_qsd(session)
            self.assertEqual('source_luks_sec', source_qsd.secret_id)
            self.assertTrue(all(b['encrypt']['key-secret'] == 'source_luks_sec'
                                for b in self._qcow_blockdevs(source_qsd)))
            self.assertTrue(all('target_luks_sec' not in c
                                for c in self.calls + self.check_runs))
        finally:
            session.cleanup()

    def test_mixed_source_dag_binds_secret_per_node(self):
        """Per invariant #1 the whole chain converts (no external ancestor).
        Each node's source qcow carries the LUKS secret only if that node is
        itself encrypted; the root convert has no -B backing."""
        nodes = [
            self._node(0, source_encrypted=True),
            self._node(1, parent=0, source_encrypted=False),
            self._node(2, parent=1, source_encrypted=True),
            self._node(3, parent=2, source_encrypted=False),
        ]
        session = self._session(nodes, False)
        try:
            offsets = session.run()
            self.assertEqual({n['installPath'] for n in nodes}, set(offsets))
            source_qcow = self._qcow_blockdevs(self._source_qsd(session))
            encrypted_indexes = [i for i, b in enumerate(source_qcow) if 'encrypt' in b]
            self.assertEqual([0, 2], encrypted_indexes)
            self.assertNotIn('-B ', self._convert_cmds()[0])
        finally:
            session.cleanup()

if __name__ == '__main__':
    unittest.main()
