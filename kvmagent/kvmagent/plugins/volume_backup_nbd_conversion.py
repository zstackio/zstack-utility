'''
Volume backup encryption-attribute conversion (host side).

kvmagent drives the whole forest NBD conversion data-plane itself: it calls the
four zstore backup-forest endpoints (export-prepare / import-prepare /
import-commit, plus import-abort on failure) directly via `zstcli forest`
against the backup-storage agent (plain HTTP, port 8001, no rootca), and runs
qemu-storage-daemon + qemu-img in between. The management node sends one
self-contained command carrying the whole backup DAG plus the backup-storage
endpoints, and gets back the committed installPaths keyed by oldInstallPath.
'''
import json
import os
import shutil
import subprocess
import tempfile
import time

from kvmagent import kvmagent
from kvmagent.plugins.imagestore import ImageStoreClient
from kvmagent.plugins import volume_secret
from zstacklib.utils import log
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils import qemu_img

logger = log.get_logger(__name__)

VOLUME_BACKUP_QCOW2_CLUSTER_SIZE = 16384


class ConvertVolumeBackupNbdForestCmd(kvmagent.AgentCommand):
    @log.sensitive_fields("encryptedDek")
    def __init__(self):
        super(ConvertVolumeBackupNbdForestCmd, self).__init__()
        self.taskUuid = None
        self.bsAgentHost = None
        self.bsAgentPort = 0
        self.nbdHost = None
        self.targetChainName = None
        self.targetEncrypted = False
        self.uploadConcurrency = 0
        self.encryptedDek = None
        self.leafInstallPaths = []


class ConvertVolumeBackupNbdForestRsp(kvmagent.AgentResponse):
    def __init__(self):
        super(ConvertVolumeBackupNbdForestRsp, self).__init__()
        self.installPaths = {}


class _VolumeBackupNbdConversionNode(object):
    def __init__(self, value, index):
        self.index = index
        self.old_install_path = value['installPath']
        self.parent_install_path = value.get('parentNodeId') or None
        self.virtual_size = long(value['virtualSize'])
        self.arch = value.get('arch')
        self.author = value.get('author')
        self.description = value.get('description')
        self.source_export_name = value['exportName']
        self.source_encrypted = None
        self.target_export_name = None


class VolumeBackupNbdQsd(object):
    def __init__(self, task_dir, name, blockdevs, exports, secret_file=None, secret_id=None):
        self.task_dir = task_dir
        self.name = name
        self.blockdevs = blockdevs
        self.exports = exports
        self.secret_file = secret_file
        self.secret_id = secret_id
        self.work_dir = os.path.join(task_dir, name)
        self.socket_path = os.path.join(self.work_dir, 'nbd.sock')
        self.pid_path = os.path.join(self.work_dir, 'qsd.pid')
        self.log_path = os.path.join(self.work_dir, 'qsd.log')
        self.process = None
        self.log_file = None

    def start(self):
        os.makedirs(self.work_dir)
        args = ['qemu-storage-daemon', '--pidfile', self.pid_path]
        if self.secret_file:
            args.extend(['--object', 'secret,id=%s,format=raw,file=%s' %
                         (self.secret_id, self.secret_file)])
        for blockdev in self.blockdevs:
            args.extend(['--blockdev', json.dumps(blockdev, separators=(',', ':'))])
        args.extend(['--nbd-server', 'addr.type=unix,addr.path=%s,max-connections=0' % self.socket_path])
        for node_name, export_name, writable in self.exports:
            args.extend(['--export', 'type=nbd,id=%s,node-name=%s,writable=%s,name=%s' %
                         (export_name, node_name, 'on' if writable else 'off', export_name)])

        try:
            self.log_file = open(self.log_path, 'w')
            self.process = subprocess.Popen(args, stdout=self.log_file, stderr=subprocess.STDOUT,
                                            close_fds=True)
            self._wait_for_socket()
        except Exception:
            self.cleanup()
            raise

    def _wait_for_socket(self):
        deadline = time.time() + max(30, len(self.blockdevs) * 3)
        while time.time() < deadline:
            if os.path.exists(self.pid_path) and os.path.exists(self.socket_path):
                return
            if self.process.poll() is not None:
                raise Exception('qemu-storage-daemon[%s] exited: %s' % (self.name, self._log_content()))
            time.sleep(0.1)
        raise Exception('qemu-storage-daemon[%s] did not create %s: %s' %
                        (self.name, self.socket_path, self._log_content()))

    def _log_content(self):
        if self.log_file:
            self.log_file.flush()
        if not os.path.exists(self.log_path):
            return ''
        with open(self.log_path, 'r') as fd:
            return fd.read()

    def url(self, export_name):
        return 'nbd+unix:///%s?socket=%s' % (export_name, self.socket_path)

    def cleanup(self):
        try:
            if self.process and self.process.poll() is None:
                linux.kill_process(self.process.pid, is_exception=False)
            if self.process:
                self.process.wait()
        except OSError:
            pass
        finally:
            if self.log_file:
                self.log_file.close()
                self.log_file = None
            shutil.rmtree(self.work_dir, ignore_errors=True)


class VolumeBackupNbdConversionSession(object):
    def __init__(self, cmd):
        self.task_uuid = cmd.taskUuid
        self.nbd_host = cmd.nbdHost
        self.target_chain_name = cmd.targetChainName
        self.target_encrypted = bool(cmd.targetEncrypted)
        self.bs_agent_host = cmd.bsAgentHost
        self.bs_agent_port = cmd.bsAgentPort
        self.imagestore_client = ImageStoreClient()
        self.upload_concurrency = int(cmd.uploadConcurrency or 0)
        self.encrypted_dek = cmd.encryptedDek
        self.leaf_install_paths = [str(p) for p in (cmd.leafInstallPaths or []) if p]
        if not self.leaf_install_paths:
            raise Exception('leafInstallPaths is required')
        if self.target_encrypted and not self.encrypted_dek:
            raise Exception('backup encryption conversion requires encryptedDek')
        self.nodes = []
        self.nodes_by_path = {}
        self.source_nbd_port = None
        self.target_nbd_port = None
        self.task_dir = None
        self.qsds = []
        self.source_urls = {}
        self.target_urls = {}

    def run(self):
        try:
            self._export_prepare()
            carrier_sizes = self.measure()
            import_nodes = self._import_prepare(carrier_sizes)
            image_end_offsets = self.convert()
            return self._commit(import_nodes, image_end_offsets)
        except Exception:
            try:
                self.imagestore_client.abort_backup_forest_import(
                    self.bs_agent_host, self.bs_agent_port, self.task_uuid,
                    [node.old_install_path for node in self.nodes])
            except Exception as e:
                logger.warn('failed to abort backup forest conversion task[%s]: %s' %
                            (self.task_uuid, str(e)))
            raise

    def _export_prepare(self):
        reply = self.imagestore_client.prepare_backup_forest_export(
            self.bs_agent_host, self.bs_agent_port, self.task_uuid, self.leaf_install_paths)
        self.source_nbd_port = reply.get('port')
        nodes = [_VolumeBackupNbdConversionNode(value, index)
                 for index, value in enumerate(reply.get('nodes') or [])]
        if not nodes:
            raise Exception('source NBD forest export returned no nodes')
        nodes_by_path = {}
        for node in nodes:
            if node.old_install_path in nodes_by_path:
                raise Exception('source NBD forest export returned duplicate installPath[%s]' %
                                node.old_install_path)
            nodes_by_path[node.old_install_path] = node
        for node in nodes:
            if node.parent_install_path and node.parent_install_path not in nodes_by_path:
                raise Exception('source NBD forest export node[%s] parent[%s] is missing from the returned DAG' %
                                (node.old_install_path, node.parent_install_path))
        for leaf in self.leaf_install_paths:
            if leaf not in nodes_by_path:
                raise Exception('source NBD forest export did not return requested leaf installPath[%s]' % leaf)
        self.nodes_by_path = nodes_by_path
        self.nodes = nodes

    def _import_prepare(self, carrier_sizes):
        import_nodes = []
        for node in self.nodes:
            import_nodes.append({
                'nodeId': node.old_install_path,
                'parentNodeId': node.parent_install_path or '',
                'carrierSize': carrier_sizes[node.old_install_path],
                'virtualSize': node.virtual_size,
                'targetEncrypted': self.target_encrypted,
                'name': self.target_chain_name,
                'arch': node.arch or '',
                'author': node.author or '',
                'description': node.description or '',
            })
        reply = self.imagestore_client.prepare_backup_forest_import(
            self.bs_agent_host, self.bs_agent_port, self.task_uuid, import_nodes)
        self.target_nbd_port = reply.get('port')
        export_name_by_id = {}
        for node in reply.get('nodes') or []:
            node_id = node.get('nodeId')
            export_name = node.get('exportName')
            if not node_id or not export_name or node_id in export_name_by_id:
                raise Exception('target NBD forest import returned invalid or duplicate node')
            export_name_by_id[node_id] = export_name
        expected = set(node.old_install_path for node in self.nodes)
        if set(export_name_by_id.keys()) != expected:
            raise Exception('target NBD forest import nodeIds do not match the converted DAG')
        for node in self.nodes:
            node.target_export_name = export_name_by_id[node.old_install_path]
        return import_nodes

    def _commit(self, import_nodes, image_end_offsets):
        reply = self.imagestore_client.commit_backup_forest_import(
            self.bs_agent_host, self.bs_agent_port, self.task_uuid, self.upload_concurrency,
            import_nodes, image_end_offsets)
        install_paths = reply.get('installPaths') or {}
        expected = set(node.old_install_path for node in self.nodes)
        if set(install_paths.keys()) != expected:
            raise Exception('backup forest commit installPath keys do not match the converted DAG')
        seen = set()
        for node in self.nodes:
            new_install_path = install_paths.get(node.old_install_path)
            if not new_install_path or new_install_path in seen:
                raise Exception('backup forest commit returned empty or duplicate new installPath for %s' %
                                node.old_install_path)
            seen.add(new_install_path)
        return install_paths

    def _start_qsd(self, name, blockdevs, exports, secret_file=None, secret_id=None):
        qsd = VolumeBackupNbdQsd(self.task_dir, name, blockdevs, exports, secret_file, secret_id)
        self.qsds.append(qsd)
        qsd.start()
        return qsd

    def _resolve_source_encryption(self):
        for node in self.nodes:
            if node.source_encrypted is not None:
                continue
            image_opts = ','.join([
                'driver=qcow2',
                'file.driver=nbd',
                'file.server.type=inet',
                'file.server.host=%s' % self.nbd_host,
                'file.server.port=%s' % self.source_nbd_port,
                'file.export=%s' % node.source_export_name,
            ])
            result = json.loads(shell.call(' '.join([
                qemu_img.subcmd('info'), '--output=json', '--image-opts', linux.shellquote(image_opts)
            ])))
            if result.get('format') != 'qcow2':
                raise Exception('source node[%s] is not qcow2' % node.old_install_path)
            encrypt = result.get('format-specific', {}).get('data', {}).get('encrypt')
            node.source_encrypted = result.get('encrypted') is True or (
                    isinstance(encrypt, dict) and bool(encrypt.get('format') or encrypt.get('key-secret')))
        if any(node.source_encrypted for node in self.nodes) and not self.encrypted_dek:
            raise Exception('backup encryption conversion requires encryptedDek')

    def _start_source_graph_qsd(self):
        if self.source_urls:
            return
        self._resolve_source_encryption()
        self.task_dir = tempfile.mkdtemp(prefix='zstack-vbk-nbd-%s-' % self.task_uuid[:36], dir='/tmp')
        blockdevs = []
        exports = []
        for node in self.nodes:
            raw_name = 'source-raw-%s' % node.index
            node.source_qcow_name = 'source-qcow-%s' % node.index
            blockdevs.append({
                'driver': 'nbd',
                'node-name': raw_name,
                'read-only': True,
                'server': {
                    'type': 'inet',
                    'host': self.nbd_host,
                    'port': str(self.source_nbd_port),
                },
                'export': node.source_export_name,
            })
            qcow = {
                'driver': 'qcow2',
                'node-name': node.source_qcow_name,
                'read-only': True,
                'file': raw_name,
            }
            if node.parent_install_path:
                qcow['backing'] = self.nodes_by_path[node.parent_install_path].source_qcow_name
            if node.source_encrypted:
                qcow['encrypt'] = {
                    'format': 'luks',
                    'key-secret': 'source_luks_sec',
                }
            blockdevs.append(qcow)
            exports.append((node.source_qcow_name, 'source-%s' % node.index, False))
        source_encrypted = any(node.source_encrypted for node in self.nodes)
        with volume_secret.luks_secret_channel(
                self.encrypted_dek if source_encrypted else None) as secret_file:
            qsd = self._start_qsd('source', blockdevs, exports, secret_file, 'source_luks_sec')
        for node in self.nodes:
            export_name = 'source-%s' % node.index
            self.source_urls[node.old_install_path] = qsd.url(export_name)

    def measure(self):
        self._start_source_graph_qsd()
        sizes = {}
        for node in self.nodes:
            source = self.source_urls[node.old_install_path]
            with volume_secret.luks_secret_channel(
                    self.encrypted_dek if self.target_encrypted else None) as secret_file:
                options = [qemu_img.subcmd('measure'), '--output=json', '-f raw']
                output_options = ['cluster_size=%s' % VOLUME_BACKUP_QCOW2_CLUSTER_SIZE]
                if secret_file:
                    options.append(volume_secret.target_secret_option(secret_file))
                    output_options.extend(['encrypt.format=luks', 'encrypt.key-secret=target_luks_sec'])
                options.append('-o %s' % ','.join(output_options))
                options.extend(['-O qcow2', linux.shellquote(source)])
                result = json.loads(shell.call(' '.join(options)))
            size = result.get('fully-allocated')
            if size is None:
                raise Exception('qemu-img measure did not return fully-allocated for %s' % node.old_install_path)
            sizes[node.old_install_path] = long(size)
        return sizes

    def _format_target_node(self, node, backing):
        with volume_secret.luks_secret_channel(
                self.encrypted_dek if self.target_encrypted else None) as secret_file:
            options = [qemu_img.subcmd('create'), '-u', '-f qcow2']
            output_options = ['cluster_size=%s' % VOLUME_BACKUP_QCOW2_CLUSTER_SIZE]
            if secret_file:
                options.append(volume_secret.target_secret_option(secret_file))
                output_options.extend(['encrypt.format=luks', 'encrypt.key-secret=target_luks_sec'])
            options.append('-o %s' % ','.join(output_options))
            if backing:
                options.extend(['-b %s' % linux.shellquote(backing), '-F raw'])
            options.extend([linux.shellquote('nbd://%s:%s/%s' % (
                self.nbd_host, self.target_nbd_port, node.target_export_name)), str(node.virtual_size)])
            shell.check_run(' '.join(options))

    def _convert_node(self, node, backing):
        source = self.source_urls[node.old_install_path]
        with volume_secret.luks_secret_channel(
                self.encrypted_dek if self.target_encrypted else None) as secret_file:
            options = [qemu_img.subcmd('convert'), '-n', '-f raw']
            if secret_file:
                options.append(volume_secret.target_secret_option(secret_file))
            options.append('--target-image-opts')
            if backing:
                options.extend(['-F raw', '-B %s' % linux.shellquote(backing)])
            options.extend([linux.shellquote(source),
                            linux.shellquote(volume_secret.nbd_target_image_options(
                                self.nbd_host, self.target_nbd_port,
                                node.target_export_name, self.target_encrypted))])
            shell.check_run(' '.join(options))

    def _check_node(self, node):
        with volume_secret.luks_secret_channel(
                self.encrypted_dek if self.target_encrypted else None) as secret_file:
            options = [qemu_img.subcmd('check'), '--output=json']
            if secret_file:
                options.append(volume_secret.target_secret_option(secret_file))
            options.extend(['--image-opts', linux.shellquote(volume_secret.nbd_target_image_options(
                self.nbd_host, self.target_nbd_port, node.target_export_name, self.target_encrypted))])
            result = json.loads(shell.call(' '.join(options)))
        return result['image-end-offset']

    def _start_target_backing_qsd(self, node):
        blockdevs = [{
            'driver': 'nbd',
            'node-name': 'target-raw',
            'read-only': True,
            'server': {
                'type': 'inet',
                'host': self.nbd_host,
                'port': str(self.target_nbd_port),
            },
            'export': node.target_export_name,
        }, {
            'driver': 'qcow2',
            'node-name': 'target-qcow',
            'read-only': True,
            'file': 'target-raw',
        }]
        if self.target_encrypted:
            blockdevs[1]['encrypt'] = {
                'format': 'luks',
                'key-secret': 'target_luks_sec',
            }
        target_export_name = 'target-%s' % node.index
        with volume_secret.luks_secret_channel(
                self.encrypted_dek if self.target_encrypted else None) as secret_file:
            qsd = self._start_qsd('target-backing-%s' % node.index, blockdevs,
                                  [('target-qcow', target_export_name, False)],
                                  secret_file, 'target_luks_sec')
        return qsd, qsd.url(target_export_name)

    def convert(self):
        self._start_source_graph_qsd()
        image_end_offsets = {}
        target_backing_qsds = []
        for node in self.nodes:
            parent = node.parent_install_path
            backing = None
            if parent:
                backing = self.target_urls.get(parent) or self.source_urls[parent]
            self._format_target_node(node, backing)
            self._convert_node(node, backing)
            image_end_offsets[node.old_install_path] = self._check_node(node)
            backing_qsd, target_url = self._start_target_backing_qsd(node)
            target_backing_qsds.append(backing_qsd)
            self.target_urls[node.old_install_path] = target_url
        for qsd in reversed(target_backing_qsds):
            qsd.cleanup()
            self.qsds.remove(qsd)
        for node in self.nodes:
            if not node.parent_install_path:
                continue
            with volume_secret.luks_secret_channel(
                    self.encrypted_dek if self.target_encrypted else None) as secret_file:
                options = [qemu_img.subcmd('rebase'), '-F qcow2', '-u',
                           '-b %s' % linux.shellquote('Z')]
                if secret_file:
                    options.append(volume_secret.target_secret_option(secret_file))
                options.extend(['--image-opts', linux.shellquote(volume_secret.nbd_target_image_options(
                    self.nbd_host, self.target_nbd_port, node.target_export_name, self.target_encrypted))])
                shell.check_run(' '.join(options))
        return image_end_offsets

    def cleanup(self):
        for qsd in reversed(self.qsds):
            try:
                qsd.cleanup()
            except Exception as e:
                logger.warn('failed to clean backup conversion QSD: %s' % str(e))
        self.qsds = []
        if self.task_dir and os.path.exists(self.task_dir):
            shutil.rmtree(self.task_dir, ignore_errors=True)
        self.task_dir = None


def convert_volume_backup_nbd_forest(cmd):
    session = VolumeBackupNbdConversionSession(cmd)
    try:
        return session.run()
    finally:
        session.cleanup()
