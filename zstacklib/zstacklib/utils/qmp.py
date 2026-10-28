from __future__ import annotations
from zstacklib.utils import log, bash, qemu
import json
import errno
import socket
import logging
import re
from distutils.version import LooseVersion


logger = log.get_logger(__name__)
QEMU_VERSION = qemu.QEMU_VERSION


def get_vm_block_nodes(domain_uuid):
    block_nodes = execute_qmp_command(domain_uuid, "query-named-block-nodes")
    if not block_nodes:
        raise Exception("no block nodes found on vm[uuid:{}]".format(domain_uuid))

    return block_nodes


def get_block_node_name_and_file(domain_id):
    block_nodes = get_vm_block_nodes(domain_id)
    node_name_and_files = {}
    for block_node in block_nodes:
        node_name_and_files[block_node['node-name']] = block_node["file"]
    return node_name_and_files


def get_yank_instances(vm):
    results = execute_qmp_command(vm, "query-yank", raise_exception=False)
    if results:
        return [result['node-name'] for result in results if result.get('type') == 'block-node']


def do_yank(vm):
    instances = get_yank_instances(vm)
    if not instances:
        return False

    for instance in instances:
        execute_qmp_command(vm, "yank", raise_exception=False,
                            instances=[{"type": "block-node", "node-name": instance}])
    return True


def get_block_job_ids(vm):
    jobs = execute_qmp_command(vm, "query-block-jobs")
    if jobs:
        return [job['device'] for job in jobs]

def query_block_jobs_by_device(vm):
    jobs = execute_qmp_command(vm, "query-block-jobs")
    return {job['device']: job for job in jobs}

def block_job_cancel(vm, device):
    execute_qmp_command(vm, "block-job-cancel", raise_exception=False, device=device)


def migrate_set_speed(vm, bandwidth):
    """
    :param vm: domain uuid
    :param bandwidth: in bytes
    """
    execute_qmp_command(vm, "migrate-set-parameters", max_bandwidth=bandwidth)

def block_job_set_speed(vm, device, bandwidth):
    """
    :param vm: domain uuid
    :param device:  device name in block job, can be found by query-block-jobs
    :param bandwidth: in bytes
    """
    execute_qmp_command(vm, "block-job-set-speed", device=device, speed=bandwidth)


@bash.in_bash
def _execute_qmp_command(domain_id, command, raise_exception=True):
    r, o, e = bash.bash_roe("virsh qemu-monitor-command %s '%s'" % (domain_id, qmp_subcmd(QEMU_VERSION, command)))
    if r == 0:
        ret = json.loads(o.strip())
        if "error" not in ret:
            return ret["return"]
        err_msg = "Failed to execute qmp command '{}', vmUuid:{}, error:{}".format(command, domain_id, ret["error"])
    else:
        err_msg = "Failed to execute qmp command '{}', vmUuid:{}, retcode:{}, stderr:{}".format(command, domain_id, r, e)

    if raise_exception:
        raise Exception(err_msg)
    logger.warn(err_msg)


def execute_qmp_command(domain, name, raise_exception=True, **kwargs):
    """
    Execute a QMP command on a domain
    :param domain:
    :param name:
    :param kwargs:
        qemu monitor command arguments
        ignore_error: ignore error if True
    :return:
    """

    qmp_cmd = {'execute': name}
    for k, v in list(kwargs.items()):
        if "_" in k:
            kwargs[k.replace("_", "-")] = v
            del kwargs[k]

    qmp_cmd['arguments'] = kwargs
    return _execute_qmp_command(domain, json.dumps(qmp_cmd), raise_exception)


def qmp_subcmd(qemu_version, s_cmd):
    # object-add option props (removed in 6.0).
    # Specify the properties for the object as top-level arguments instead.
    # qmp command example:
    # '{"execute": "object-add", "arguments":{ "qom-type": "colo-compare", "id": "comp-%s",
    #              "props": { "primary_in": "primary-in-c-%s", "secondary_in": "secondary-in-s-%s",
    #              "outdev":"primary-out-c-%s", "iothread": "iothread%s", "vnet_hdr_support": true } } }'
    # expect results:
    # '{"execute": "object-add", "arguments": {"vnet_hdr_support": true, "iothread": "iothread%s",
    #              "secondary_in": "secondary-in-s-%s", "primary_in": "primary-in-c-%s", "id": "comp-%s",
    #              "qom-type": "colo-compare", "outdev": "primary-out-c-%s"}}'
    if LooseVersion(qemu_version) >= LooseVersion("6.0.0") and re.match(r'.*object-add.*arguments.*props.*', s_cmd):
        j_cmd = json.loads(s_cmd)
        props = j_cmd.get("arguments").get("props")
        j_cmd.get("arguments").pop("props")
        j_cmd.get("arguments").update(props)
        s_cmd = json.dumps(j_cmd)
    return s_cmd



class QMPError(Exception):
    """
    QMP base exception
    """


class QMPConnectError(QMPError):
    """
    QMP connection exception
    """


class QMPCapabilitiesError(QMPError):
    """
    QMP negotiate capabilities exception
    """


class QMPTimeoutError(QMPError):
    """
    QMP timeout exception
    """


class QEMUMonitorProtocol:
    """
    Provide an API to connect to QEMU via QEMU Monitor Protocol (QMP) and then
    allow to handle commands.
    """

    def __init__(self, address):
        """
        Create a QEMUMonitorProtocol class.

        @param address: QEMU address, can be either a unix socket path (string)
                        or a tuple in the form ( address, port ) for a TCP
                        connection
        @raise OSError on socket connection errors
        @note No connection is established, this is done by the connect() or
              accept() methods
        """
        self.__events = []
        self.__address = address
        self.__sock = self.__get_sock()
        self.__sockfile = None

    def __get_sock(self):
        if isinstance(self.__address, tuple):
            family = socket.AF_INET
        else:
            family = socket.AF_UNIX
        return socket.socket(family, socket.SOCK_STREAM)

    def __negotiate_capabilities(self):
        greeting = self.__json_read()
        if greeting is None or "QMP" not in greeting:
            raise QMPConnectError
        # Greeting seems ok, negotiate capabilities
        resp = self._cmd('qmp_capabilities')
        if resp and "return" in resp:
            return greeting
        raise QMPCapabilitiesError

    def __json_read(self):
        while True:
            data = self.__sockfile.readline()
            if not data:
                return None
            resp = json.loads(data)
            if 'event' in resp:
                continue
            return resp


    def __enter__(self):
        # Implement context manager enter function.
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        # Implement context manager exit function.
        self.close()
        return False

    def accept(self, timeout=15.0):
        """
        Await connection from QMP Monitor and perform capabilities negotiation.

        @param timeout: timeout in seconds (nonnegative float number, or
                        None). The value passed will set the behavior of the
                        underneath QMP socket as described in [1]. Default value
                        is set to 15.0.
        @return QMP greeting dict
        @raise OSError on socket connection errors
        @raise QMPConnectError if the greeting is not received
        @raise QMPCapabilitiesError if fails to negotiate capabilities

        [1]
        https://docs.python.org/3/library/socket.html#socket.socket.settimeout
        """
        self.__sock.settimeout(timeout)
        self.__sock, _ = self.__sock.accept()
        self.__sockfile = self.__sock.makefile()
        return self.__negotiate_capabilities()

    def _cmd_obj(self, qmp_cmd):
        """
        Send a QMP command to the QMP Monitor.

        @param qmp_cmd: QMP command to be sent as a Python dict
        @return QMP response as a Python dict or None if the connection has
                been closed
        """
        logger.debug(">>> %s", qmp_cmd)
        try:
            self.__sock.sendall(json.dumps(qmp_cmd).encode('utf-8'))
        except OSError as err:
            if err.errno == errno.EPIPE:
                return None
            raise err
        resp = self.__json_read()
        logger.debug("<<< %s", resp)
        return resp

    def _cmd(self, name, args=None, cmd_id=None):
        """
        Build a QMP command and send it to the QMP Monitor.

        @param name: command name (string)
        @param args: command arguments (dict)
        @param cmd_id: command id (dict, list, string or int)
        """
        qmp_cmd = {'execute': name}
        if args:
            qmp_cmd['arguments'] = args
        if cmd_id:
            qmp_cmd['id'] = cmd_id
        return self._cmd_obj(qmp_cmd)

    def command(self, cmd, **kwds):
        """
        Build and send a QMP command to the monitor, report errors if any
        """
        if kwds:
            for k, v in list(kwds.items()):
                if "_" in k:
                    kwds[k.replace("_", "-")] = v
                    del kwds[k]
        ret = self._cmd(cmd, kwds)
        if "error" in ret:
            raise Exception(ret['error']['desc'])
        return ret['return']


    def close(self):
        """
        Close the socket and socket file.
        """
        if self.__sock:
            self.__sock.close()
        if self.__sockfile:
            self.__sockfile.close()

    def settimeout(self, timeout):
        """
        Set the socket timeout.

        @param timeout (float): timeout in seconds, or None.
        @note This is a wrap around socket.settimeout
        """
        self.__sock.settimeout(timeout)
