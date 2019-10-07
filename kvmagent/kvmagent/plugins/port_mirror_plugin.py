'''

@author: zhanyong.miao
'''
import copy
from kvmagent import kvmagent
from zstacklib.utils import jsonobject
from zstacklib.utils import http
from zstacklib.utils import log
from zstacklib.utils import lock
from zstacklib.utils import shell
from zstacklib.utils import linux
from zstacklib.utils.bash import *
import os
import traceback
import netaddr

KVM_APPLY_MIRROR_SESSION_SOURCE = "/portmirror/apply/source"
KVM_RELEASE_MIRROR_SESSION_SOURCE = "/portmirror/release/source"
KVM_APPLY_MIRROR_SESSION_DEST = "/portmirror/apply/dest"
KVM_RELEASE_MIRROR_SESSION_DEST = "/portmirror/release/dest"

logger = log.get_logger(__name__)

class Tunnel:
    def __init__(self):
        self.dev = None
        self.uuid = None
        self.localIp = None
        self.remoteIp = None
        self.prefix = None
        self.gw = None
        self.key = None

class Mirror:
    def __init__(self):
        self.type = None
        self.snic = None
        self.dnic = None
        self.bridge = None
        self.mName = None

class ApplyMirrorSessionOnKVMCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ApplyMirrorSessionOnKVMCmd, self).__init__()
        self.tunnel = None
        self.mirror = None
        self.isLocal = None

class ApplyMirrorSessionOnKVMResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ApplyMirrorSessionOnKVMResponse, self).__init__()

class ReleaseMirrorSessionOnKVMCmd(kvmagent.AgentCommand):
    def __init__(self):
        super(ReleaseMirrorSessionOnKVMCmd, self).__init__()
        self.tunnel = None
        self.mirror = None
        self.isLocal = None

class ReleaseMirrorSessionOnKVMResponse(kvmagent.AgentResponse):
    def __init__(self):
        super(ReleaseMirrorSessionOnKVMResponse, self).__init__()

class PortMirrorPlugin(kvmagent.KvmAgent):
    '''
    classdocs
    '''

    def _create_gre_device(self, device_name, rec_device_name, local_ip, prefix, remote_ip, key):
        shell_cmd = shell.ShellCmd("ip add | grep '%s'" % local_ip)
        shell_cmd(False)
        if shell_cmd.return_code != 0:
            add_cmd = shell.ShellCmd("ip add add %s/%d dev %s" % (local_ip, prefix, device_name))
            add_cmd()
        create_cmd = shell.ShellCmd("ip link add %s type gretap remote %s local %s ttl 255 key %d" % (rec_device_name, remote_ip, local_ip, key))
        create_cmd(False)
        if create_cmd.return_code == 0:
            shell.ShellCmd('ip link set %s up' % rec_device_name)

        '''       
        ip add add 169.254.100.143/24 dev bond1
        ip link add rec_vnic47.0 type gretap remote 169.254.100.150 local 169.254.100.143 ttl 255 key 1
        ip link set rec_vnic47.0 up
        '''
    def _delete_gre_device(self, device_name, rec_device_name, local_ip, prefix, remote_ip, key):
        shell.ShellCmd("ip link del '%s'" % rec_device_name)
        shell_cmd = shell.ShellCmd("ip link show|grep 'rec_vnic'")
        shell_cmd(False)
        if shell_cmd.return_code != 0:
            ip_cmd = shell.ShellCmd("ip add del %s/%d dev %s" % (local_ip, prefix, device_name))
            ip_cmd(False)

    def _set_redirect_config(self, device_name, mirror_device_name):
        shell_cmd = shell.ShellCmd("tc qdisc show dev %s |grep 'qdisc ingress'" % device_name)
        shell_cmd(False)
        if shell_cmd.return_code != 0:
            shell.call("tc qdisc add dev %s ingress" % device_name)
            shell.call('tc filter add dev %s parent ffff: protocol all u32 match u8 0 0 action mirred egress mirror dev %s' % (device_name, mirror_device_name))

    def _clear_redirect_config(self, device_name, mirror_device_name):
        shell_cmd = shell.ShellCmd("tc qdisc show dev %s |grep 'qdisc ingress'" % device_name)
        shell_cmd(False)
        if shell_cmd.return_code == 0:
            shell.call("tc qdisc del dev %s ingress" % device_name)

    def _set_mirror_src_config(self, device_name, mirror_device_name, direction):
        if (direction == "Egress" or direction == "Bidirection"):
            shell_cmd = shell.ShellCmd("tc qdisc show dev %s |grep 'qdisc ingress'" % device_name)
            shell_cmd(False)
            if shell_cmd.return_code != 0:
                shell.call("tc qdisc add dev %s ingress" % device_name)
                shell.call('tc filter add dev %s parent ffff: protocol all u32 match u8 0 0 action mirred egress mirror dev %s' % (device_name, mirror_device_name))

        if (direction == "Ingress" or direction == "Bidirection"):
            shell_cmd = shell.ShellCmd("tc qdisc show dev %s |grep 'qdisc prio 1:'" % device_name)
            shell_cmd(False)
            if shell_cmd.return_code != 0:
                shell.call("tc qdisc add dev %s handle 1: root prio" % device_name)
                shell.call('tc filter add dev %s parent 1: protocol all u32 match u8 0 0 action mirred egress mirror dev %s' % (device_name, mirror_device_name))

    def _clear_mirror_src_config(self, device_name, direction):
        shell_cmd = shell.ShellCmd("tc qdisc show dev %s |grep 'qdisc ingress'" % device_name)
        shell_cmd(False)
        if shell_cmd.return_code == 0:
            shell.call("tc qdisc del dev %s ingress" % device_name)

        shell_cmd = shell.ShellCmd("tc qdisc show dev %s |grep 'qdisc prio 1:'" % device_name)
        shell_cmd(False)
        if shell_cmd.return_code == 0:
            shell.call("tc qdisc del dev %s root" % device_name)

    def _set_mirror_dst_config(self, device_name, mirror_device_name):
        shell_cmd = shell.ShellCmd("ip link show dev br_monitor")
        shell_cmd(False)
        if shell_cmd.return_code != 0:
            add_cmd = shell.ShellCmd("ip link add br_monitor type bridge && ip link set dev br_monitor up")
            add_cmd()

        shell.call("ip link set dev %s master br_monitor" % mirror_device_name)
        shell.call("ip link set dev %s master br_monitor" % device_name)

    def _clear_mirror_dst_config(self, bridge_name, device_name,mirror_device_name):
        shell.call("ip link set dev %s master %s" % (device_name, bridge_name))
        '''
         ip link add br_monitor type bridge
        ip link set dev br_monitor up
        ip link set dev vnic25.0 master br_monitor
        ip link set dev rec_vnic25.0 master br_monitor
        '''
    def _apply_mirror_session_local(self, src_device_name, dst_device_name, direction):
        self._set_mirror_src_config(src_device_name, dst_device_name, direction)
        self._set_mirror_dst_config(dst_device_name, dst_device_name)

    def _release_mirror_session_local(self, src_device_name, dst_device_name, direction, bridge_name):
        self._clear_mirror_src_config(src_device_name, direction)
        self._clear_mirror_dst_config(bridge_name, dst_device_name)

    def _ifup_device_if_down(self, device_name):
        state_path = '/sys/class/net/%s/operstate' % device_name

        if not os.path.exists(state_path):
            raise Exception('cannot find %s' % state_path)

        with open(state_path, 'r') as fd:
            state = fd.read()

        if 'up' in state:
            return

        shell.call('ip link set %s up' % device_name)

    @kvmagent.replyerror
    def apply_mirror_session(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ApplyMirrorSessionOnKVMResponse()

        '''
        check if the endpoints of session both are in this host
        if yes, just configure the mirror and skip the gre tunnel setup
       
        "tunnel":{"dev":"br_eth1","localIp":"192.168.100.185","remoteIp":"192.168.100.185",
                  "gw":"192.168.100.1","prefix":24,"id":1},
        "mirror":{"type":"Ingress","snic":"vnic47.0","dnic":"vnic47.1"},
        '''
        if cmd.isLocal:
            self._apply_mirror_session_local(cmd.mirror.snic, cmd.mirror.dnic, cmd.mirror.type)
        else:
            rec_name = cmd.mirror.mName
            self._create_gre_device(cmd.tunnel.dev, rec_name, cmd.tunnel.localIp, cmd.tunnel.prefix, cmd.tunnel.remoteIp, cmd.tunnel.key)
            self._set_mirror_src_config(cmd.mirror.snic, rec_name, cmd.mirror.type)
        logger.debug('successfully apply mirror device [%s] to device[%s]' % (cmd.mirror.snic, cmd.mirror.dnic))
        return jsonobject.dumps(rsp)

    @lock.lock('port_mirror')
    @kvmagent.replyerror
    def release_mirror_session(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ReleaseMirrorSessionOnKVMResponse()

        if cmd.isLocal:
            self._release_mirror_session_local(cmd.mirror.snic, cmd.mirror.dnic, cmd.mirror.type, cmd.mirror.bridge)
        else:
            rec_name = cmd.mirror.mName
            self._clear_mirror_src_config(cmd.mirror.snic, cmd.mirror.type)
            self._delete_gre_device(cmd.tunnel.dev, rec_name, cmd.tunnel.localIp, cmd.tunnel.prefix, cmd.tunnel.remoteIp, cmd.tunnel.id)
            logger.debug('successfully release mirror device [%s] to device[%s]' % (cmd.mirror.snic, cmd.mirror.dnic))

        return jsonobject.dumps(rsp)

    @kvmagent.replyerror
    def apply_mirror_session_dest(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ApplyMirrorSessionOnKVMResponse()

        '''
        check if the endpoints of session both are in this host
        if yes, just configure the mirror and skip the gre tunnel setup
        '''

        if cmd.isLocal:
            rsp.error = 'unable to apply mirror device [%s] to device[%s] in same hypervisor' % (cmd.mirror.snic, cmd.mirror.dnic)
            rsp.success = False
        else:
            rec_name = cmd.mirror.mName
            self._create_gre_device(cmd.tunnel.dev, rec_name, cmd.tunnel.localIp, cmd.tunnel.prefix, cmd.tunnel.remoteIp, cmd.tunnel.key)
            self._set_mirror_dst_config(cmd.mirror.dnic, rec_name)
            self._set_redirect_config(rec_name, cmd.mirror.dnic)
            logger.debug('successfully apply mirror device [%s] to device[%s]' % (cmd.mirror.snic, cmd.mirror.dnic))

        return jsonobject.dumps(rsp)

    @lock.lock('port_mirror')
    @kvmagent.replyerror
    def release_mirror_session_dest(self, req):
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        rsp = ReleaseMirrorSessionOnKVMResponse()

        if cmd.isLocal:
            rsp.error = 'unable to release mirror device [%s] to device[%s] in same hypervisor' % (cmd.mirror.snic, cmd.mirror.dnic)
            rsp.success = False
        else:
            rec_name = cmd.mirror.mName
            self._clear_redirect_config(rec_name, cmd.mirror.dnic)
            self._clear_mirror_dst_config(cmd.mirror.bridge, cmd.mirror.dnic, rec_name)
            self._delete_gre_device(cmd.tunnel.dev, rec_name, cmd.tunnel.localIp, cmd.tunnel.prefix, cmd.tunnel.remoteIp, cmd.tunnel.id)
            logger.debug('successfully release mirror device [%s] to device[%s]' % (cmd.mirror.snic, cmd.mirror.dnic))

        return jsonobject.dumps(rsp)

    def start(self):
        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(KVM_APPLY_MIRROR_SESSION_SOURCE, self.apply_mirror_session)
        http_server.register_async_uri(KVM_RELEASE_MIRROR_SESSION_SOURCE, self.release_mirror_session)
        http_server.register_async_uri(KVM_APPLY_MIRROR_SESSION_DEST, self.apply_mirror_session_dest)
        http_server.register_async_uri(KVM_RELEASE_MIRROR_SESSION_DEST, self.release_mirror_session_dest)

    def stop(self):
        pass
