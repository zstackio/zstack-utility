__author__ = 'Wave'

from cStringIO import StringIO
from email import message_from_file
from email.mime.multipart import MIMEMultipart
import os
import platform

from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import lock
from zstacklib.utils import uuidhelper
from zstacklib.utils.bash import *

from kvmagent import kvmagent

HOST_ARCH = platform.machine()

LIGHTTPD_CONF = '''\
server.document-root = "{{http_root}}"

server.port = {{port}}
server.bind = "0.0.0.0"
dir-listing.activate = "enable"
index-file.names = ( "index.html" )

server.modules += ("mod_proxy", "mod_rewrite", "mod_access", "mod_accesslog",)
accesslog.filename = "/var/log/lighttpd/lighttpd_access.log"
server.errorlog = "/var/log/lighttpd/lighttpd_error.log"

$REQUEST_HEADER["X-Instance-ID"] =~ "^(.*)$" {
    $HTTP["url"] =~ "^/metrics/job" {
        proxy.server = ( "" =>
           ( ( "host" => "{{pushgateway_ip}}", "port" => {{pushgateway_port}} ) )
        )
{% for inst_uuid in userdata_vm_uuid -%}
    } else $REQUEST_HEADER["X-Instance-ID"] == "{{inst_uuid}}" {
        url.rewrite-once = (
            "^/zwatch-vm-agent.linux-amd64.bin$" => "/zwatch-vm-agent",
            "^/zwatch-vm-agent.freebsd-amd64.bin$" => "/zwatch-vm-agent-freebsd",
            "^/zwatch-vm-agent.linux-aarch64.bin$" => "/zwatch-vm-agent_aarch64",
            "^/zwatch-vm-agent.linux-mips64el.bin$" => "/collectd_exporter_mips64el",
            "^/zwatch-vm-agent.linux-loongarch64.bin$" => "/collectd_exporter_loongarch64",
            "^/agent-tools-update.sh$" => "/vm-tools.sh",
            "^/.*/meta-data/(.+)$" => "/{{inst_uuid}}/meta-data/$1",
            "^/.*/meta-data$" => "/{{inst_uuid}}/meta-data",
            "^/.*/meta-data/$" => "/{{inst_uuid}}/meta-data/",
            "^/.*/user-data$" => "/{{inst_uuid}}/user-data",
            "^/.*/user_data$" => "/{{inst_uuid}}/user_data",
            "^/.*/meta_data.json$" => "/{{inst_uuid}}/meta_data.json",
            "^/.*/password$" => "/{{inst_uuid}}/password",
            "^/.*/$" => "/{{inst_uuid}}/$1"
        )
        dir-listing.activate = "enable"
{% endfor -%}
    } else $REQUEST_HEADER["X-Instance-ID"] =~ "^(.*)$" {
        url.rewrite-once = (
            "^/zwatch-vm-agent.linux-amd64.bin$" => "/zwatch-vm-agent",
            "^/zwatch-vm-agent.freebsd-amd64.bin$" => "/zwatch-vm-agent-freebsd",
            "^/zwatch-vm-agent.linux-aarch64.bin$" => "/zwatch-vm-agent_aarch64",
            "^/zwatch-vm-agent.linux-mips64el.bin$" => "/collectd_exporter_mips64el",
            "^/zwatch-vm-agent.linux-loongarch64.bin$" => "/collectd_exporter_loongarch64",
            "^/agent-tools-update.sh$" => "/vm-tools.sh",
            "^/.*/meta-data/(.+)$" => "/zstack-default/meta-data/$1",
            "^/.*/meta-data$" => "/zstack-default/meta-data",
            "^/.*/meta-data/$" => "/zstack-default/meta-data/",
            "^/.*/user-data$" => "/zstack-default/user-data",
            "^/.*/user_data$" => "/zstack-default/user_data",
            "^/.*/meta_data.json$" => "/zstack-default/meta_data.json",
            "^/.*/password$" => "/zstack-default/password",
            "^/.*/$" => "/zstack-default/$1"
        )
        dir-listing.activate = "enable"
    }
}

mimetype.assign = (
  ".html" => "text/html",
  ".txt" => "text/plain",
  ".jpg" => "image/jpeg",
  ".png" => "image/png"
)'''


class TfNetProviderUserdata(kvmagent.KvmAgent):

    TF_NET_APPLY_USER_DATA = "/tfnetworkprovider/userdata/apply"
    TF_NET_RELEASE_USER_DATA = "/tfnetworkprovider/userdata/release"
    TF_NET_BATCH_USER_DATA = "/tfnetworkprovider/userdata/batchapply"

    TF_USERDATA_ROOT = "/var/lib/zstack/tf_userdata"

    KVM_HOST_PUSHGATEWAY_IP = "0.0.0.0"
    KVM_HOST_PUSHGATEWAY_PORT = "9092"

    def __init__(self):
        self.userdata_vms_tf = set()

    def start(self):
        http_server = kvmagent.get_http_server()

        http_server.register_async_uri(self.TF_NET_APPLY_USER_DATA,
                                       self.apply_userdata_for_tf)
        http_server.register_async_uri(self.TF_NET_RELEASE_USER_DATA,
                                       self.release_userdata_for_tf)
        http_server.register_async_uri(self.TF_NET_BATCH_USER_DATA,
                                       self.batch_apply_userdata_for_tf)

    def stop(self):
        pass

    @kvmagent.replyerror
    @lock.lock('tf_lighttpd')
    def apply_userdata_for_tf(self, req):
        """
        Generate new lighttpd.conf, vm userdata file and
        restart lighttpd process
        :params req: dict, {"header" : req.headers, "body": req.body}
        :returns: str
        """
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        self._apply_userdata_tf_config(cmd.userdata)
        self._apply_userdata_tf_file(cmd.userdata)
        # TODO:(Wave) Later maybe we should use nginx which supports reload,
        # so we don't need to kill the http server process and start it again.
        self._apply_userdata_restart_tf_httpd()
        return jsonobject.dumps(kvmagent.AgentResponse())

    @in_bash
    def _apply_userdata_tf_config(self, userdata):
        """
        :params userdata: zstacklib.utils.jsonobject.JsonObject
        :returns: None
        """

        def create_default_userdata(http_root):
            root = os.path.join(http_root, "zstack-default")
            meta_root = os.path.join(root, 'meta-data')
            if not os.path.exists(meta_root):
                linux.mkdir(meta_root)

            index_file_path = os.path.join(meta_root, 'index.html')
            linux.write_file(index_file_path, '', True)

        def apply_zwatch_vm_agent(http_root):
            agent_file_source_path = "/var/lib/zstack/kvm/zwatch-vm-agent"
            freebsd_agent_file_source_path = "/var/lib/zstack/kvm/zwatch-vm-agent-freebsd"
            if not os.path.exists(agent_file_source_path):
                logger.error("Can't find file %s" % agent_file_source_path)
                return

            if HOST_ARCH == 'x86_64' and not os.path.exists(freebsd_agent_file_source_path):
                logger.error("Can't find file %s" % freebsd_agent_file_source_path)
                return

            agent_file_target_path = os.path.join(http_root, "zwatch-vm-agent")
            if not os.path.exists(agent_file_target_path):
                bash_r("ln -s %s %s" % (agent_file_source_path, agent_file_target_path))
            elif not os.path.islink(agent_file_target_path):
                linux.rm_file_force(agent_file_target_path)
                bash_r("ln -s %s %s" % (agent_file_source_path, agent_file_target_path))

            freebsd_agent_file_target_path = os.path.join(http_root, "zwatch-vm-agent-freebsd")
            if not os.path.exists(freebsd_agent_file_target_path):
                bash_r("ln -s %s %s" % (freebsd_agent_file_source_path, freebsd_agent_file_target_path))
            elif not os.path.islink(freebsd_agent_file_target_path):
                linux.rm_file_force(freebsd_agent_file_target_path)
                bash_r("ln -s %s %s" % (freebsd_agent_file_source_path, freebsd_agent_file_target_path))

            tool_sh_file_path = "/var/lib/zstack/kvm/vm-tools.sh"
            if not os.path.exists(tool_sh_file_path):
                logger.error("Can't find file %s" % tool_sh_file_path)
                return
            target_tool_sh_file_path = os.path.join(http_root, "vm-tools.sh")
            if not os.path.exists(target_tool_sh_file_path):
                bash_r("ln -s %s %s" % (tool_sh_file_path, target_tool_sh_file_path))
            elif not os.path.islink(target_tool_sh_file_path):
                linux.rm_file_force(target_tool_sh_file_path)
                bash_r("ln -s %s %s" % (tool_sh_file_path, target_tool_sh_file_path))

            version_file_path = "/var/lib/zstack/kvm/agent_version"
            if not os.path.exists(version_file_path):
                logger.error("Can't find file %s" % version_file_path)
                return
            target_version_file_path = os.path.join(http_root, "agent_version")
            if not os.path.exists(target_version_file_path):
                bash_r("ln -s %s %s" % (version_file_path, target_version_file_path))
            elif not os.path.islink(target_version_file_path):
                linux.rm_file_force(target_version_file_path)
                bash_r("ln -s %s %s" % (version_file_path, target_version_file_path))

        root_dir = self.TF_USERDATA_ROOT
        if not os.path.exists(root_dir):
            linux.mkdir(root_dir)

        conf_path = os.path.join(self.TF_USERDATA_ROOT, 'lighttpd.conf')
        http_root = os.path.join(self.TF_USERDATA_ROOT, 'html')

        # Add missing dash '-' to match "X-Instance-ID" from TF network.
        # 8c766113567a482dbf3cbeafa7beda89 ->
        # 8c766113-567a-482d-bf3c-beafa7beda89
        vm_uuid = uuidhelper.to_full_uuid(userdata.metadata.vmUuid)
        if vm_uuid not in self.userdata_vms_tf:
            self.userdata_vms_tf.add(vm_uuid)

        template = Template(LIGHTTPD_CONF)
        conf = template.render({
            'http_root': http_root,
            'port': userdata.port,
            'userdata_vm_uuid': self.userdata_vms_tf,
            'pushgateway_ip': self.KVM_HOST_PUSHGATEWAY_IP,



            'pushgateway_port': self.KVM_HOST_PUSHGATEWAY_PORT,
        })

        linux.mkdir(http_root, 0777)

        if not os.path.exists(conf_path):
            linux.write_file(conf_path, conf, True)
        else:
            with open(conf_path, 'r') as fd:
                current_conf = fd.read()

            if current_conf != conf:
                linux.write_file(conf_path, conf, True)

        create_default_userdata(http_root)
        apply_zwatch_vm_agent(http_root)

    @in_bash
    def _apply_userdata_tf_file(self, userdata):
        """
        :params userdata: zstacklib.utils.jsonobject.JsonObject
        :returns: None
        """
        def pack_userdata(userdata_list):
            if len(userdata_list) == 1:
                return userdata_list[0]

            combined_message = MIMEMultipart()
            for ud in userdata_list:
                ud = ud.strip()
                msg = message_from_file(StringIO(ud))
                for part in msg.walk():
                    if part.get_content_maintype() == 'multipart':
                        continue
                    combined_message.attach(part)

            return combined_message.__str__()

        http_root = os.path.join(self.TF_USERDATA_ROOT, 'html')
        vm_uuid = userdata.metadata.vmUuid
        meta_data_json = '''\
{
    "uuid": "{{vmInstanceUuid}}"
}'''
        tmpt = Template(meta_data_json)
        conf = tmpt.render({
            'vmInstanceUuid': vm_uuid
        })

        root = os.path.join(http_root, uuidhelper.to_full_uuid(vm_uuid))
        meta_root = os.path.join(root, 'meta-data')
        if not os.path.exists(meta_root):
            linux.mkdir(meta_root)

        index_file_path = os.path.join(meta_root, 'index.html')
        write_content = "instance-id"
        if userdata.metadata.vmHostname:
            write_content += "\nlocal-hostname"
        linux.write_file(index_file_path, write_content, True)

        instance_id_file_path = os.path.join(meta_root, 'instance-id')
        linux.write_file(instance_id_file_path, vm_uuid, True)

        if userdata.metadata.vmHostname:
            vm_hostname_file_path = os.path.join(meta_root, 'local-hostname')
            linux.write_file(vm_hostname_file_path,
                             userdata.metadata.vmHostname, True)

        if userdata.userdataList:
            userdata_file_path = os.path.join(root, 'user-data')
            linux.write_file(userdata_file_path,
                             pack_userdata(userdata.userdataList), True)

            windows_meta_data_json_path = os.path.join(root, 'meta_data.json')
            linux.write_file(windows_meta_data_json_path, conf, True)

            windows_userdata_file_path = os.path.join(root, 'user_data')
            linux.write_file(windows_userdata_file_path,
                             pack_userdata(userdata.userdataList), True)

            windows_meta_data_password = os.path.join(root, 'password')
            linux.write_file(windows_meta_data_password, '', True)

        if userdata.agentConfig:
            pvpanic_file_path = os.path.join(meta_root, 'pvpanic')
            panic = userdata.agentConfig.pvpanic if userdata.agentConfig.pvpanic else 'disable'
            linux.write_file(pvpanic_file_path, panic, True)

    @in_bash
    def _apply_userdata_restart_tf_httpd(self):
        def check(_):
            pid = linux.find_process_by_cmdline([conf_path])
            return pid is not None

        conf_path = os.path.join(self.TF_USERDATA_ROOT, 'lighttpd.conf')
        pid = linux.find_process_by_cmdline([conf_path])
        if pid:
            linux.kill_process(pid, timeout=10)

        linux.mkdir('/var/log/lighttpd', 0o750)
        # restart lighttpd to load new configuration
        shell.call('lighttpd -f %s' % conf_path)
        if not linux.wait_callback_success(check, None, 10):
            raise Exception('lighttpd[conf-file:%s] is not running '
                            'after being started %s seconds' % (conf_path, 10))

    @kvmagent.replyerror
    def release_userdata_for_tf(self, req):
        """Delete vm userdata folder and remove vm_uuid
        from self.userdata_vms_tf
        :params req: dict, {"header" : req.headers, "body": req.body}
        :returns: str
        """
        cmd = jsonobject.loads(req[http.REQUEST_BODY])
        vm_uuid = uuidhelper.to_full_uuid(cmd.vmUuid)
        vm_folder = os.path.join(self.TF_USERDATA_ROOT, 'html', vm_uuid)
        linux.rm_dir_force(vm_folder)
        if vm_uuid in self.userdata_vms_tf:
            self.userdata_vms_tf.remove(vm_uuid)

        return jsonobject.dumps(kvmagent.AgentResponse())

    @kvmagent.replyerror
    @lock.lock('tf_lighttpd')
    def batch_apply_userdata_for_tf(self, req):
        """kill lighttpd process, add vm_uuid to self.userdata_vms_tf
        :params req: dict, {"header" : req.headers, "body": req.body}
        :returns: str
        """
        cmd = jsonobject.loads(req[http.REQUEST_BODY])

        if cmd.rebuild:
            # kill lighttpd process using tf_userdata folder
            # which will be restarted later
            pattern = self.TF_USERDATA_ROOT.replace("/", "\/")
            shell.call('pkill -9 -f "lighttpd.*%s" || true' % pattern)

        for u in cmd.userdata:
            vm_uuid = uuidhelper.to_full_uuid(u.metadata.vmUuid)
            if vm_uuid not in self.userdata_vms_tf:
                self.userdata_vms_tf.add(vm_uuid)

        if cmd.userdata:
            # We just apply lighttpd.conf once, because all vm_uuid are in
            # self.self.userdata_vms_tf
            self._apply_userdata_tf_config(cmd.userdata[0])

        for ud in cmd.userdata:
            self._apply_userdata_tf_file(ud)

        if self.userdata_vms_tf:
            self._apply_userdata_restart_tf_httpd()

        return jsonobject.dumps(kvmagent.AgentResponse())