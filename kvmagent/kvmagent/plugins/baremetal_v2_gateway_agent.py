import json
import os
import shutil

from jinja2 import Template
from zstacklib.utils import http
from zstacklib.utils import jsonobject
from zstacklib.utils import linux
from zstacklib.utils import linux_v2
from zstacklib.utils import log
from zstacklib.utils import shell

from kvmagent import kvmagent
from kvmagent.plugins.bmv2_gateway_agent import exception
from kvmagent.plugins.bmv2_gateway_agent.object import BmInstanceObj
from kvmagent.plugins.bmv2_gateway_agent.object import NetworkObj
from kvmagent.plugins.bmv2_gateway_agent.object import VolumeObj
from kvmagent.plugins.bmv2_gateway_agent import utils as bm_utils
from kvmagent.plugins.bmv2_gateway_agent import volume


logger = log.get_logger(__name__)


class BaremetalV2GatewayAgentPlugin(kvmagent.KvmAgent):

    BM_PREPARE_PROVISION_NETWORK_PATH = \
        '/baremetal_gateway_agent/v2/provision_network/prepare'
    BM_DESTROY_PROVISION_NETWORK_PATH = \
        '/baremetal_gateway_agent/v2/provision_network/destroy'
    BM_PREPARE_INSTANCE_PATH = \
        '/baremetal_gateway_agent/v2/instance/configurations/create'
    BM_DESTROY_INSTANCE_PATH = \
        '/baremetal_gateway_agent/v2/instance/configurations/delete'
    BM_ATTACH_VOLUME_PATH = \
        '/baremetal_gateway_agent/v2/instance/volume/prepare'
    BM_DETACH_VOLUME_PATH = \
        '/baremetal_gateway_agent/v2/instance/volume/destroy'
    BM_CONSOLE_PATH = \
        '/baremetal_gateway_agent/v2/instance/console'

    BAREMETAL_LIB_DIR = '/var/lib/zstack/baremetalv2/'
    BAREMETAL_LOG_DIR = '/var/log/zstack/baremetalv2/'
    PID_DIR = '/var/run/'

    # Dnsmasq configuration
    DNSMASQ_DIR = os.path.join(BAREMETAL_LIB_DIR, 'dnsmasq/')
    DNSMASQ_CONF_PATH = os.path.join(DNSMASQ_DIR, 'dnsmasq.conf')
    DNSMASQ_HOSTS_PATH = os.path.join(DNSMASQ_DIR, 'hosts')
    DNSMASQ_LEASE_PATH = os.path.join(DNSMASQ_DIR, 'leases')
    DNSMASQ_LOG_PATH=os.path.join(BAREMETAL_LOG_DIR, 'dnsmasq.log')
    DNSMASQ_PID_PATH = os.path.join(PID_DIR, 'zstack-bm-dnsmasq.pid')
    DNSMASQ_SYSTEMD_SERVICE_PATH = \
            '/usr/lib/systemd/system/zstack-baremetal-dnsmasq.service'

    TFTPBOOT_DIR = os.path.join(BAREMETAL_LIB_DIR, 'tftpboot/')
    PXELINUX_CFG_DIR = os.path.join(TFTPBOOT_DIR, 'pxelinux.cfg/')
    BOOT_IPXE_PATH = os.path.join(TFTPBOOT_DIR, 'boot.ipxe')
    DEFAULT_PXE_PATH = os.path.join(PXELINUX_CFG_DIR, 'default')

    NGINX_CONF_DIR = os.path.join(BAREMETAL_LIB_DIR, 'nginx')
    NGINX_CONF_PATH = os.path.join(NGINX_CONF_DIR, 'nginx.conf')
    NGINX_BM_AGENT_PROXY_CONF_DIR = os.path.join(NGINX_CONF_DIR, 'conf.d')
    NGINX_LOG_DIR = os.path.join(BAREMETAL_LOG_DIR, 'nginx')
    NGINX_PID_PATH = os.path.join(PID_DIR, 'zstack-bm-nginx.pid')
    NGINX_SYSTEMD_SERVICE_PATH = \
            '/usr/lib/systemd/system/zstack-baremetal-gateway-nginx.service'

    HTTPBOOT_DIR = os.path.join(BAREMETAL_LIB_DIR, 'httpboot/')
    ZSTACK_DVD_LINKED_DIR = os.path.join(HTTPBOOT_DIR, 'zstack-dvd')
    HTTP_PORT = 7090

    INSPECTOR_KS_CFG = os.path.join(HTTPBOOT_DIR, 'inspector.ks')

    BAREMETAL_GATEWAY_AGENT_CONF_CACHE = os.path.join(BAREMETAL_LIB_DIR,
                                                      '.bm-gateway.conf')

    @property
    def provision_network_conf(self):
        with open(self.BAREMETAL_GATEWAY_AGENT_CONF_CACHE, 'r') as f:
            raw_conf = json.loads(f.read())
        conf = NetworkObj.from_json({'body': {'provisionNetwork': raw_conf}})
        return conf

    def _ensure_env(self):
        """ Check the env whether ready
        """

        required_pkgs = ['nginx', 'dnsmasq', 'ipxe-bootimgs', 'socat', 'gc',
                         'xmlto', 'asciidoc', 'hmaccalc', 'newt-devel',
                         'perl-ExtUtils-Embed', 'pesign',
                         'elfutils-libelf-devel', 'elfutils-devel',
                         'zlib-devel', 'binutils-devel', 'bison',
                         'audit-libs-devel', 'java-devel', 'numactl-devel',
                         'pciutils-devel', 'ncurses-devel', 'python-docutils',
                         'flex', 'targetcli', 'syslinux']
        yum_release = kvmagent.get_host_yum_release()
        cmd = ('export YUM0={yum_release}; yum --disablerepo=* '
               '--enablerepo=zstack-mn clean all; '
               'pkg_list=`rpm -q {pkg_list} | grep "not installed" | awk '
               '\'{{ print $2 }}\'`; for pkg in $pkg_list; do yum '
               '--disablerepo=* --enablerepo=zstack-mn install -y '
               '$pkg > /dev/null || exit 1; done;').format(
                   yum_release=yum_release,
                   pkg_list=' '.join(required_pkgs))
        shell.call(cmd)

        # Create directories
        directories = [
            self.BAREMETAL_LIB_DIR,
            self.BAREMETAL_LOG_DIR,
            self.DNSMASQ_DIR,
            self.TFTPBOOT_DIR,
            self.PXELINUX_CFG_DIR,
            self.NGINX_BM_AGENT_PROXY_CONF_DIR,
            self.NGINX_LOG_DIR,
            self.HTTPBOOT_DIR
        ]
        cmd = 'mkdir -p {dirs}'.format(dirs=' '.join(directories))
        shell.call(cmd)

        # Prepare tftpboot, copy ipxe/pxelinux.0 rom
        # cmd = 'yes | cp -rf /usr/share/ipxe/* ''{tftpboot}'.format(
        #     tftpboot=self.TFTPBOOT_DIR)
        # shell.call(cmd)
        bm_utils.copy_dir_files_to_another_dir(
            '/usr/share/ipxe', self.TFTPBOOT_DIR)
        # bm_utils.copy_dir_files_to_another_dir(
        #     '/usr/share/syslinux', self.TFTPBOOT_DIR)
        shutil.copy('/usr/share/syslinux/pxelinux.0', self.TFTPBOOT_DIR)

        # Prepare httpboot, link zstack-dvd, copy kernel&initramfs
        if os.path.exists(self.ZSTACK_DVD_LINKED_DIR):
            os.unlink(self.ZSTACK_DVD_LINKED_DIR)
        # cmd = ('release=`cat /etc/zstack-release | awk \'{{ print $3 }}\'`; '
        #        'ln -s /opt/zstack-dvd/x86_64/$release '
        #        '{zstack_dvd_linked_dir}; '
        #        'yes | cp -rf {zstack_dvd_linked_dir}/images/pxeboot/* '
        #        '{httpboot}').format(
        #            zstack_dvd_linked_dir=self.ZSTACK_DVD_LINKED_DIR,
        #            httpboot=self.HTTPBOOT_DIR)
        # shell.call(cmd)
        os.symlink('/opt/zstack-dvd/x86_64/%s' % yum_release,
                   self.ZSTACK_DVD_LINKED_DIR)
        bm_utils.copy_dir_files_to_another_dir(
            os.path.join(self.ZSTACK_DVD_LINKED_DIR, 'images', 'pxeboot'),
            self.HTTPBOOT_DIR)
        bm_utils.copy_dir_files_to_another_dir(
            os.path.join(self.ZSTACK_DVD_LINKED_DIR, 'images', 'pxeboot'),
            self.TFTPBOOT_DIR)

        # Start and enable target service
        cmd = 'systemctl start target && systemctl enable target'
        shell.call(cmd)

        # Build nbd module and setup modprobe params
        build_script = ''
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  'bmv2_gateway_agent/scripts/build_nbd.sh'), 'r') as f:
            build_script = f.read()
        shell.call(build_script)

    def _load_template(self, template):
        """" Load jinja template
        """
        template_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'bmv2_gateway_agent/templates')
        k_v_mapping = {
            'boot.ipxe': os.path.join(template_dir, 'boot.ipxe.j2'),
            'config.ipxe': os.path.join(template_dir, 'config.ipxe.j2'),
            'default.pxe': os.path.join(template_dir, 'default.pxe.j2'),
            'dnsmasq.conf': os.path.join(template_dir, 'dnsmasq.conf.j2'),
            'inspector.ks': os.path.join(template_dir, 'inspector.ks.j2'),
            'nginx_proxy_to_mn': os.path.join(template_dir,
                                              'nginx-proxy-to-mn.conf.j2'),
            'nginx_proxy_to_agent_http': os.path.join(
                template_dir, 'nginx-proxy-to-agent-http.j2'),
            'nginx_proxy_to_agent_tcp': os.path.join(
                template_dir, 'nginx-proxy-to-agent-tcp.j2'),
            'nginx_systemd_service': os.path.join(
                template_dir, 'zstack-baremetal-gateway-nginx.service.j2'),
            'dnsmasq_systemd_service': os.path.join(
                template_dir, 'zstack-baremetal-dnsmasq.service.j2')
        }
        with open(k_v_mapping.get(template), 'r') as f:
            return Template(f.read())

    def _prepare_provision_network(self, network_obj):
        """ Prepare provision network

        :param network_obj: The network obj
        :type network_obj: NetworkObj
        """
        linux.flush_device_ip(network_obj.dhcp_interface)
        linux.set_device_ip(network_obj.dhcp_interface,
                            network_obj.provision_nic_ip,
                            network_obj.dhcp_range_netmask)
        shell.call('ip link set {nic} up'.format(
            nic=network_obj.dhcp_interface))

    def _destroy_provision_network(self, network_obj):
        """ Clear provision network configuration

        :param network_obj: The network obj
        :type network_obj: NetworkObj
        """
        linux.flush_device_ip(network_obj.dhcp_interface)

    def _prepare_dnsmasq(self, network_obj):
        """ Prepare dnsmasq configuration

        :param network_obj: The network obj
        :type network_obj: NetworkObj
        """
        template = self._load_template('dnsmasq.conf')
        ip_range = '{start},{end}'.format(
            start=network_obj.dhcp_range_start_ip,
            end=network_obj.dhcp_range_end_ip)
        conf = template.render(
            zstack_bm_dnsmasq_pid=self.DNSMASQ_PID_PATH,
            provision_dhcp_interface=network_obj.dhcp_interface,
            provision_network_dhcp_range = ip_range,
            provision_network_netmask=network_obj.dhcp_range_netmask,
            provision_network_gateway=network_obj.dhcp_range_gateway,
            provision_dhcp_hosts_file=self.DNSMASQ_HOSTS_PATH,
            provision_dhcp_leases_file=self.DNSMASQ_LEASE_PATH,
            bm_gateway_provision_ip=network_obj.provision_nic_ip,
            bm_gateway_tftpboot_dir=self.TFTPBOOT_DIR,
            provision_dhcp_log_path=self.DNSMASQ_LOG_PATH)
        with open(self.DNSMASQ_CONF_PATH, 'w') as f:
            f.write(conf)

        if not os.path.exists(self.DNSMASQ_SYSTEMD_SERVICE_PATH):
            dnsmasq_template = self._load_template('dnsmasq_systemd_service')
            dnsmasq_conf = dnsmasq_template.render(
                zstack_bm_dnsmasq_pid=self.DNSMASQ_PID_PATH,
                zstack_bm_dnsmasq_conf_path=self.DNSMASQ_CONF_PATH)
            with open(self.DNSMASQ_SYSTEMD_SERVICE_PATH, 'w') as f:
                f.write(dnsmasq_conf)
            cmd = 'systemctl daemon-reload'
            shell.call(cmd)

        cmd = ('systemctl start zstack-baremetal-dnsmasq && '
               'systemctl reload zstack-baremetal-dnsmasq')
        shell.call(cmd)

    def _destroy_dnsmasq(self):
        """ Destroy dnsmasq configuration
        """
        # pid = linux.find_process_by_cmdline([self.DNSMASQ_PID_PATH])
        # if pid:
        #     shell.call('kill %s' % pid)
        cmd = ('systemctl is-active zstack-baremetal-dnsmasq || exit 0; '
               'systemctl stop zstack-baremetal-dnsmasq.service')
        shell.call(cmd)

        linux.rm_file_force(self.DNSMASQ_HOSTS_PATH)
        linux.rm_file_force(self.DNSMASQ_LEASE_PATH)
        linux.rm_file_force(self.DNSMASQ_CONF_PATH)
        linux.rm_file_force(self.DNSMASQ_PID_PATH)

    def _create_dnsmasq_host(self, instance_obj):
        """ Create dnsmasq configuration
        """
        host = '{mac_addr},{ip_addr},set:instance'.format(
            mac_addr=instance_obj.provision_mac,
            ip_addr=instance_obj.provision_ip)

        dnsmasq_hosts = ''
        if os.path.exists(self.DNSMASQ_HOSTS_PATH):
            with open(self.DNSMASQ_HOSTS_PATH, 'r') as f:
                dnsmasq_hosts = f.read()

        if not host in dnsmasq_hosts:
            cmd = 'echo {host} >> {conf_path}'.format(
                host=host, conf_path=self.DNSMASQ_HOSTS_PATH)
            shell.call(cmd)

        # Ensure the ip address not leased by dnsmasq, if leased, remove the
        # record
        if os.path.exists(self.DNSMASQ_LEASE_PATH):
            with open(self.DNSMASQ_LEASE_PATH, 'r') as f:
                dnsmasq_leases = f.read()
            if instance_obj.provision_ip in dnsmasq_leases:
                cmd = 'sed -i /{ip_addr}/d {lease_path}'.format(
                    mac_addr=instance_obj.provision_mac,
                    ip_addr=instance_obj.provision_ip,
                    lease_path=self.DNSMASQ_LEASE_PATH)
                shell.call(cmd)

        cmd = ('systemctl start zstack-baremetal-dnsmasq && '
               'systemctl reload zstack-baremetal-dnsmasq')
        shell.call(cmd)

    def _delete_dnsmasq_host(self, instance_obj):
        """ Delete dnsmasq configuration
        """
        if not os.path.exists(self.DNSMASQ_HOSTS_PATH):
            return

        # Use . for regexp, to match ','(in hosts) and ' '(in leases)
        host = '{mac_addr}.{ip_addr}'.format(
            mac_addr=instance_obj.provision_mac,
            ip_addr=instance_obj.provision_ip)

        cmd = 'sed -i /{host}/d {conf_path}'.format(
            host=host, conf_path=self.DNSMASQ_HOSTS_PATH)
        shell.call(cmd)

        cmd = 'sed -i /{host}/d {lease_path}'.format(
            host=host, lease_path=self.DNSMASQ_LEASE_PATH)
        shell.call(cmd)

        # pid = linux.find_process_by_cmdline([self.DNSMASQ_PID_PATH])
        # cmd = 'kill -s SIGHUP {pid}'.format(pid=pid)
        cmd = ('systemctl start zstack-baremetal-dnsmasq && '
               'systemctl reload zstack-baremetal-dnsmasq')
        shell.call(cmd)

    def _prepare_nginx(self, network_obj):
        """ Prepare nginx configuration

        Include httpboot file server, mn proxy(callback and sendcommand).
        :param network_obj: The network obj
        :type network_obj: NetworkObj
        """
        template = self._load_template('nginx_proxy_to_mn')
        mn_callback_uri = 'http://{ip}:{port}'.format(
            ip=network_obj.callback_ip, port=network_obj.callback_port)
        conf = template.render(
            mn_callback_uri=mn_callback_uri,
            bm_gateway_httpboot=self.BAREMETAL_LIB_DIR,
            bm_agent_proxy_conf_dir=self.NGINX_BM_AGENT_PROXY_CONF_DIR,
            zstack_bm_nginx_log_dir=self.NGINX_LOG_DIR,
            zstack_bm_gateway_nginx_pid=self.NGINX_PID_PATH
        )
        with open(self.NGINX_CONF_PATH, 'w') as f:
            f.write(conf)

        if not os.path.exists(self.NGINX_SYSTEMD_SERVICE_PATH):
            bm_nginx_template = self._load_template('nginx_systemd_service')
            bm_nginx_conf = bm_nginx_template.render(
                zstack_bm_gateway_nginx_pid=self.NGINX_PID_PATH,
                zstack_bm_gateway_nginx_conf_path=self.NGINX_CONF_PATH)
            with open(self.NGINX_SYSTEMD_SERVICE_PATH, 'w') as f:
                f.write(bm_nginx_conf)
            cmd = 'systemctl daemon-reload'
            shell.call(cmd)

        cmd = ('systemctl start zstack-baremetal-gateway-nginx && '
               'systemctl reload zstack-baremetal-gateway-nginx')
        shell.call(cmd)

    def _destroy_nginx(self):
        """ Destroy nginx configration

        Include proxy shellinaboxd, proxy bm instance agent API, inspect http
        web server, mn proxy.
        """
        cmd = ('systemctl is-active zstack-baremetal-gateway-nginx || exit 0; '
               'systemctl stop zstack-baremetal-gateway-nginx.service')
        shell.call(cmd)
        # NOTE(ya.wang) The exist configuration file will rewrite during
        # network prepare, therefore the main conf do not need remove.
        # linux.rm_file_force(self.NGINX_CONF_PATH)
        linux.rm_dir_force(self.NGINX_BM_AGENT_PROXY_CONF_DIR)

    def _create_nginx_agent_proxy_configuration(self, instance_obj):
        """ Create one nginx configration

        Setup bm instance agent API proxy.
        """
        # Ensure the dir exist
        if not os.path.exists(self.NGINX_BM_AGENT_PROXY_CONF_DIR):
            cmd = 'mkdir -p {dir}'.format(
                dir=self.NGINX_BM_AGENT_PROXY_CONF_DIR)
            shell.call(cmd)

        template = self._load_template('nginx_proxy_to_agent_http')
        bm_gateway_callback_uri = (
            'http://{gw_ip}:{gw_port}/baremetal_instance_agent/v2/callback'
            ).format(
                gw_ip=self.provision_network_conf.provision_nic_ip,
                gw_port=self.HTTP_PORT
            )
        bm_agent_api_uri = (
            'http://{bm_instance_ip}:{bm_instance_port}/v2').format(
                bm_instance_ip=instance_obj.provision_ip,
                bm_instance_port=self.HTTP_PORT
            )
        conf = template.render(
            bm_instance_uuid=instance_obj.uuid,
            bm_gateway_callback_uri=bm_gateway_callback_uri,
            bm_agent_api_uri=bm_agent_api_uri
        )

        file_path = os.path.join(self.NGINX_BM_AGENT_PROXY_CONF_DIR,
                                 instance_obj.uuid + '.http')
        with open(file_path, 'w') as f:
            f.write(conf)

        cmd = ('systemctl start zstack-baremetal-gateway-nginx && '
               'systemctl reload zstack-baremetal-gateway-nginx')
        shell.call(cmd)

    def _delete_nginx_agent_proxy_configuration(self, instance_obj):
        """ Delete one nginx configration

        Delete bm instance agent API proxy and shellinaboxd proxy.
        """
        file_path = os.path.join(self.NGINX_BM_AGENT_PROXY_CONF_DIR,
                                 instance_obj.uuid + '.http')
        if not os.path.exists(file_path):
            msg = ('The nginx configuration file: {file_path} was '
                   'deleted before the operate').format(file_path=file_path)
            logger.warning(msg)
        linux.rm_file_force(file_path)

        file_path = os.path.join(self.NGINX_BM_AGENT_PROXY_CONF_DIR,
                                instance_obj.uuid + '.tcp')
        linux.rm_file_force(file_path)

        cmd = ('systemctl start zstack-baremetal-gateway-nginx && '
               'systemctl reload zstack-baremetal-gateway-nginx')
        shell.call(cmd)

    def _attach_volume(self, instance_obj, volume_obj):
        """ Attach a given volume

        Ceph: use qemu-nbd to attach rbd block device, then map the nbd device
        to a device-mapper device, final export the dm device as iSCSI target.
        Sharedblock: use qemu-nbd to connect the sblk device, then map the nbd
        device to a device-mapper device, final export the dm device as iSCSI
        target.
        NFS: Export the file as iSCSI target if it's raw.
        """

        # DmDeviceOperator(dev_obj).create()
        # NbdDeviceOperator(dev_obj).connect()
        # IscsiOperator(dev_obj).setup()
        volume_driver = volume.get_driver(instance_obj, volume_obj)
        volume_driver.attach()
        return volume_driver

    def _detach_volume(self, instance_obj, volume_obj):
        """ Detach a given volume
        """

        # IscsiOperator(dev_obj).revoke()
        # NbdDeviceOperator(dev_obj).disconnect()
        # DmDeviceOperator(dev_obj).remove()
        volume_driver = volume.get_driver(instance_obj, volume_obj)
        volume_driver.detach()
        return volume_driver

    @staticmethod
    def pre_take_volume_snapshot(cmd):
        """ Pre operation during take snapshot

        Suspend the device mapper dev before take snapshot.

        NOTE(ya.wang): Support shared block backend only.

        Example of cmd:
        {
            "vmUuid":"279a7944312b47ff933efdff542ec3f0",
            "volumeUuid":"489e231dcfe2487c9580034ed95d0680",
            "volume":{
                "installPath":"/dev/2611cba5038046bca64b7d966df4292b/fd31270d25f54a52b916b7015446ab2f",
                "deviceId":0,
                "deviceType":"file",
                "volumeUuid":"489e231dcfe2487c9580034ed95d0680",
                "useVirtio":true,
                "useVirtioSCSI":false,
                "shareable":false,
                "cacheMode":"none",
                "wwn":"0x000f33eedc1868d9",
                "bootOrder":0,
                "physicalBlockSize":0,
                "type":"Root",
                "format":"qcow2",
                "primaryStorageType":"SharedBlock"
            },
            "installPath":"/dev/2611cba5038046bca64b7d966df4292b/72a8809b48754d2f98cdbcc65f45d1b1",
            "fullSnapshot":false,
            "volumeInstallPath":"/dev/2611cba5038046bca64b7d966df4292b/fd31270d25f54a52b916b7015446ab2f",
            "newVolumeUuid":"72a8809b48754d2f98cdbcc65f45d1b1",
            "newVolumeInstallPath":"/dev/2611cba5038046bca64b7d966df4292b/72a8809b48754d2f98cdbcc65f45d1b1",
            "isBaremetal2InstanceOnlineSnapshot":true,
            "kvmHostAddons":{
                "qcow2Options":" -o cluster_size=2097152 "
            }
        }
        Need to point some params in cmd:
        volumeUuid: The origin volume's uuid, not snapshot
        volume.volumeUuid: Same as volumeUuid
        volume.installPath: If the volume has not snapshot, then the path is
          the volume's path, if the volume has snapshot, then the path is the
          snapshot's path
        installPath: The new snapshot's path
        volumeInstallPath: Same as volume.installPath
        newVolumeUuid: The new snapshot's uuid
        newVolumeInstallPath: San as installPath, the new snapshot's path
        isBaremetal2InstanceOnlineSnapshot: Flag that the snapshot action is
          for as online baremetal instance
        """
        instance_obj = BmInstanceObj()
        setattr(instance_obj, 'uuid', cmd.vmUuid)

        volume_map = json.loads(jsonobject.dumps(cmd.volume))
        src_volume = {'body': {
            'volume': {
                'uuid': volume_map.get('volumeUuid'),
                'primaryStorageType': volume_map.get('primaryStorageType'),
                'type': volume_map.get('type'),
                'path': volume_map.get('installPath'),
                'format': volume_map.get('format'),
                'deviceId': volume_map.get('deviceId')
            }
        }}
        src_volume_obj = VolumeObj.from_json(src_volume)
        src_volume_driver = volume.get_driver(instance_obj, src_volume_obj)

        dst_volume = { 'body': {
            'volume': {
                'uuid': src_volume_obj.uuid,
                'primaryStorageType': src_volume_obj.primary_storage_type,
                'type': src_volume_obj.type,
                'path': cmd.newVolumeInstallPath,
                'format': 'qcow2',
                'deviceId': src_volume_obj.device_id
            }
        }}
        dst_volume_obj = VolumeObj.from_json(dst_volume)
        dst_volume_driver = volume.get_driver(instance_obj, dst_volume_obj)

        src_volume_driver.pre_take_volume_snapshot()
        return src_volume_driver, dst_volume_driver

    @staticmethod
    def post_take_volume_snapshot(src_vol_driver, dst_vol_driver):
        """ Post operation during take snapshot

        Reload the device mapper table and resume it, then disconnect the
        old nbd device.

        NOTE(ya.wang): Support shared block backend only.
        """
        dst_vol_driver.post_take_volume_snapshot(src_vol_driver)

    @staticmethod
    def resume_device(vol_driver):
        """ Resume the device mapper
        """
        vol_driver.resume()

    def _open_console(self, instance_obj):
        """ Call bm instance to open the console/vnc and setup proxy on gw

        First need call bm instance agent to run tightvnc/shellinaboxd, then
        setup nginx proxy for shellinaboxd, or start a socat tcp proxy process
        for tightvnc.
        """
        file_path = os.path.join(self.NGINX_BM_AGENT_PROXY_CONF_DIR,
                                 instance_obj.uuid + '.tcp')

        if os.path.exists(file_path):
            remote_port = None
            local_port = None
            with open(file_path, 'r') as f:
                for line in f.readlines():
                    if 'listen' in line:
                        local_port = int(line.split()[-1].strip()[:-1])
                    if 'proxy_pass' in line:
                        remote_port = int(line.split(':')[-1].strip()[:-1])

            # Test wether the port can be reach
            if remote_port and linux_v2.check_remote_port_whether_open(
                instance_obj.provision_ip, remote_port):
                return local_port

        # If the conf not exist
        uri = 'http://{addr}:{port}/v2/console/prepare'.format(
            addr=instance_obj.provision_ip,
            port=self.HTTP_PORT,
            uuid=instance_obj.uuid)
        ret = http.json_post(uri, method='GET')
        # TODO(ya.wang) handle response
        ret = json.loads(ret) if isinstance(ret, str) else ret
        port = ret.get('port')

        gw_port = linux.get_free_port()

        template = self._load_template('nginx_proxy_to_agent_tcp')
        conf = template.render(
            gateway_port=gw_port,
            bm_instance_ip=instance_obj.provision_ip,
            bm_instance_vnc_port=port)


        with open(file_path, 'w') as f:
            f.write(conf)

        cmd = ('systemctl start zstack-baremetal-gateway-nginx && '
               'systemctl reload zstack-baremetal-gateway-nginx')
        shell.call(cmd)

        return gw_port

    def _prepare_ipxe_default_configuration(self, network_obj):
        """ Prepare ipxe default configuration

        :param network_obj: The network obj
        :type network_obj: NetworkObj
        """
        inspect_kernel_uri = 'http://{ip}:{port}/httpboot/vmlinuz'.format(
            ip=network_obj.provision_nic_ip, port=self.HTTP_PORT)
        inspect_initrd_uri = 'http://{ip}:{port}/httpboot/initrd.img'.format(
            ip=network_obj.provision_nic_ip, port=self.HTTP_PORT)
        inspect_ks_uri = 'http://{ip}:{port}/httpboot/inspector.ks'.format(
            ip=network_obj.provision_nic_ip, port=self.HTTP_PORT)

        ipxe_template = self._load_template('boot.ipxe')
        ipxe_conf = ipxe_template.render(
            inspect_kernel_uri=inspect_kernel_uri,
            inspect_initramfs_uri=inspect_initrd_uri,
            inspect_ks_uri=inspect_ks_uri)
        with open(self.BOOT_IPXE_PATH, 'w') as f:
            f.write(ipxe_conf)

        pxe_template = self._load_template('default.pxe')
        pxe_conf = pxe_template.render(
            inspect_ks_uri=inspect_ks_uri)
        with open(self.DEFAULT_PXE_PATH, 'w') as f:
            f.write(pxe_conf)

    def _create_ipxe_configuration(self, instance_obj, volume_drivers):
        """ Generate ipxe cfg for a bm instance
        """
        # Ensure pxelinux.cfg dir exist
        if not os.path.exists(self.PXELINUX_CFG_DIR):
            cmd = 'mkdir -p {dir}'.format(dir=self.PXELINUX_CFG_DIR)
            shell.call(cmd)

        # Due to the limit of iBFT, only add the root volume into ipxe conf
        volumes = {}
        for volume_driver in volume_drivers:
            if volume_driver.volume_obj.type == 'Root':
                uri = 'iscsi:{gw_ip}:::{lun_id}:{target}'.format(
                    gw_ip=self.provision_network_conf.provision_nic_ip,
                    lun_id=volume_driver.iscsi_lun,
                    target=volume_driver.iscsi_target)
                drive_id = '0x%x' % (128 + volume_driver.iscsi_lun)
                volumes[uri] = drive_id

        template = self._load_template('config.ipxe')
        conf = template.render(
            iscsi_initiator_iqn=volume_drivers[0].iscsi_acl,
            volumes=volumes)
        ipxe_file_name = instance_obj.provision_mac.replace(':', '-')
        ipxe_file_path = os.path.join(self.PXELINUX_CFG_DIR, ipxe_file_name)
        with open(ipxe_file_path, 'w') as f:
            f.write(conf)

    def _delete_ipxe_configuration(self, instance_obj):
        """ Delete a ipxe cfg for a bm instance
        """
        ipxe_file_name = instance_obj.provision_mac.replace(':', '-')
        ipxe_file_path = os.path.join(self.PXELINUX_CFG_DIR, ipxe_file_name)
        if not os.path.exists(ipxe_file_path):
            msg = ('The ipxe configuration file: {ipxe_file_path} was '
                   'deleted before the operate').format(
                       ipxe_file_path=ipxe_file_name)
            logger.warning(msg)
            return
        linux.rm_file_force(ipxe_file_path)

    def _append_conf_to_ipxe_configuration(self, instance_obj, volume_driver):
        """ Append a sanhook to a exist ipxe configuration
        """
        uri = 'iscsi:{gw_ip}:::{lun_id}:{target}'.format(
            gw_ip=self.provision_network_conf.provision_nic_ip,
            lun_id=volume_driver.iscsi_lun,
            target=volume_driver.iscsi_target)
        drive_id = '0x%x' % (128 + volume_driver.iscsi_lun)
        sanhook = ('sanhook --drive {drive_id} {uri} || goto '
                   'fail_iscsi_retry').format(drive_id=drive_id, uri=uri)
        sanunhook = 'sanunhook --drive {drive_id}'.format(drive_id=drive_id)

        ipxe_file_name = instance_obj.provision_mac.replace(':', '-')
        ipxe_file_path = os.path.join(self.PXELINUX_CFG_DIR, ipxe_file_name)

        with open(ipxe_file_path, 'r') as f:
            ipxe_conf = f.read()

        if not uri in ipxe_conf:
            cmd = 'sed -i "/sanboot/i {sanhook}" {file_path}'.format(
                sanhook=sanhook, file_path=ipxe_file_path)
            shell.call(cmd)

            cmd = 'sed -i "$ i {sanunhook}" {file_path}'.format(
                sanunhook=sanunhook, file_path=ipxe_file_path)
            shell.call(cmd)

    def _remove_conf_from_ipxe_configuration(self, instance_obj,
                                            volume_driver):
        """ Remove a sanhook to a exist ipxe configuration
        """
        drive_id = '0x%x' % (128 + volume_driver.iscsi_lun)
        reg_str = '--drive {drive_id}'.format(drive_id=drive_id)

        ipxe_file_name = instance_obj.provision_mac.replace(':', '-')
        ipxe_file_path = os.path.join(self.PXELINUX_CFG_DIR, ipxe_file_name)

        cmd = 'sed -i "/{reg_str}/d" {file_path}'.format(
            reg_str=reg_str, file_path=ipxe_file_path)
        shell.call(cmd)

    def _destroy_ipxe(self):
        """ Delete all ipxe configuration, exclude default ipxe conf
        """
        linux.rm_dir_force(self.PXELINUX_CFG_DIR)

    def _prepare_ks_configuration(self, network_obj):
        """ Prepare default kickstart configuration for inspect

        :param network_obj: The network obj
        :type network_obj: NetworkObj
        """
        network_inst_uri = 'http://{ip}:{port}/httpboot/zstack-dvd'.format(
            ip=network_obj.provision_nic_ip, port=self.HTTP_PORT)
        network_inst_repo_uri = \
            'http://{ip}:{port}/httpboot/zstack-dvd/Extra/qemu-kvm-ev'.format(
                ip=network_obj.provision_nic_ip, port=self.HTTP_PORT)
        send_hardware_infos_uri = (
            'http://{ip}:{port}/baremetal_instance_agent/v2/hardwareinfos'
            ).format(ip=network_obj.provision_nic_ip, port=self.HTTP_PORT)

        template = self._load_template('inspector.ks')
        conf = template.render(
            network_inst_uri=network_inst_uri,
            network_inst_repo_uri=network_inst_repo_uri,
            send_hardware_infos_uri=send_hardware_infos_uri
        )

        with open(self.INSPECTOR_KS_CFG, 'w') as f:
            f.write(conf)

    def _check_management_provision_network_mixed(self, network_obj):
        """ Check whether mgmt network nic and provision network nic same
        """
        mgmt_iface = linux.get_nic_name_by_ip(network_obj.management_ip)
        if mgmt_iface == network_obj.dhcp_interface:
            raise exception.ManagementNetProvisionNetMixed()

    @kvmagent.replyerror
    def prepare_network(self, req):
        """ Attach provision network

        Configure provision network/dnsmasq/ftp/tftp/ipxe.cfg/nginx/
        pushgateway
        req.body::
        {
            'provisionNetwork': {
                'dhcpInterface': 'eno1',
                'dhcpRangeStartIp': '10.0.201.20',
                'dhcpRangeEndIp': '10.0.201.30',
                'dhcpRangeNetmask': '255.255.255.0',
                'dhcpRangeGateway': '10.0.201.1',
                'provisionNicIp': '10.0.201.10',
                'managementIp': '10.0.201.101',
                'callBackIp': '10.1.1.10',
                'callBackPort': '8080'
            }
        }
        """
        network_obj = NetworkObj.from_json(req)
        self._check_management_provision_network_mixed(network_obj)
        self._ensure_env()
        with bm_utils.rollback(self.destroy_network, req):
            # Do not destroy previous configuration
            # self.destroy_network(req)

            self._prepare_provision_network(network_obj)
            self._prepare_dnsmasq(network_obj)
            self._prepare_nginx(network_obj)
            self._prepare_ipxe_default_configuration(network_obj)
            self._prepare_ks_configuration(network_obj)

            # save the provision network config for furthur usage
            with open(self.BAREMETAL_GATEWAY_AGENT_CONF_CACHE, 'w') as f:
                f.write(network_obj.to_json())

        return jsonobject.dumps(kvmagent.AgentResponse())

    @kvmagent.replyerror
    def destroy_network(self, req):
        """ Detach provision network

        Flush provision network/dnsmasq/ftp/tftp/ipxe.cfg/nginx/pushgateway
        configuration

        req.body::
        {
            'provisionNetwork': {
                'dhcpInterface': 'eno1',
                'dhcpRangeStartIp': '10.0.201.20',
                'dhcpRangeEndIp': '10.0.201.30',
                'dhcpRangeNetmask': '255.255.255.0',
                'dhcpRangeGateway': '10.0.201.1'
            }
        }
        """
        network_obj = NetworkObj.from_json(req)
        self._destroy_ipxe()
        self._destroy_nginx()
        self._destroy_dnsmasq()
        self._destroy_provision_network(network_obj)
        linux.rm_file_force(self.BAREMETAL_GATEWAY_AGENT_CONF_CACHE)

        return jsonobject.dumps(kvmagent.AgentResponse())

    @bm_utils.lock(name='baremetal_v2_volume_operator')
    @kvmagent.replyerror
    def prepare_instance(self, req):
        """ Prepare instance

        Configure dnsmasq/ipxe.cfg/nginx and attach volumes

        req.body::
        {
            'volumes': [
                {
                    "uuid": "uuid1",
                    "primaryStorageType": "NFS",
                    "type": "Root",
                    "path": "path/to/file",
                    "format": "qcow2",
                    "deviceId": 0
                },
                {
                    "uuid": "uuid2",
                    "primaryStorageType": "SharedBlock",
                    "type": "Data",
                    "path": "path/to/sblk",
                    "format": "raw",
                    "deviceId": 1
                },
                {
                    "uuid": "uuid3",
                    "primaryStorageType": "Ceph",
                    "type": "Data",
                    "path": "path/to/rbd",
                    "format": "qcow2",
                    "deviceId": 2
                }
            ],
            'bmInstance': {
                'uuid': 'uuid1',
                'provisionIp': '192.168.101.10',
                'provisionMac': 'aa:bb:cc:dd:ee:ff'
            }
        }
        """
        instance_obj = BmInstanceObj.from_json(req)
        volume_objs = VolumeObj.from_json_list(req)
        volume_drivers = []

        with bm_utils.rollback(self.destroy_instance, req):
            for volume_obj in volume_objs:
                volume_driver = volume.get_driver(instance_obj, volume_obj)
                volume_driver.attach()
                volume_drivers.append(volume_driver)

            self._create_dnsmasq_host(instance_obj)
            self._create_ipxe_configuration(instance_obj, volume_drivers)
            self._create_nginx_agent_proxy_configuration(instance_obj)

        return jsonobject.dumps(kvmagent.AgentResponse())

    @bm_utils.lock(name='baremetal_v2_volume_operator')
    @kvmagent.replyerror
    def destroy_instance(self, req):
        """ Stop instance

        Flush dnsmasq/ipxe.cfg/nginx configuration, detach volumes

        req.body::
        {
            'volumes': [
                {
                    "uuid": "uuid1",
                    "primaryStorageType": "NFS",
                    "type": "Root",
                    "path": "path/to/file",
                    "format": "qcow2",
                    "deviceId": 0
                },
                {
                    "uuid": "uuid2",
                    "primaryStorageType": "SharedBlock",
                    "type": "Data",
                    "path": "path/to/sblk",
                    "format": "raw",
                    "deviceId": 1
                },
                {
                    "uuid": "uuid3",
                    "primaryStorageType": "Ceph",
                    "type": "Data",
                    "path": "path/to/rbd",
                    "format": "qcow2",
                    "deviceId": 2
                }
            ],
            'bmInstance': {
                'uuid': 'uuid1',
                'provisionIp': '192.168.101.10',
                'provisionMac': 'aa:bb:cc:dd:ee:ff'
            }
        }
        """
        instance_obj = BmInstanceObj.from_json(req)
        volume_objs = VolumeObj.from_json_list(req)

        for volume_obj in volume_objs:
            volume_driver = volume.get_driver(instance_obj, volume_obj)
            volume_driver.detach()

        self._delete_dnsmasq_host(instance_obj)
        self._delete_ipxe_configuration(instance_obj)
        self._delete_nginx_agent_proxy_configuration(instance_obj)

        return jsonobject.dumps(kvmagent.AgentResponse())

    @bm_utils.lock(name='baremetal_v2_volume_operator')
    @kvmagent.replyerror
    def attach_volume(self, req):
        """ Attach volume

        Map volume to nbd device, then map nbd to md device, export md device
        as iSCSI target and configure ipxe.cfg

        req.body::
        {
            'volume': {
                'uuid': 'uuid1',
                'primaryStorageType': 'SharedBlock',
                'type': 'Data',
                'path': 'path/to/sblk',
                'format': 'qcow2',
                'deviceId': 3
            },
            'bmInstance': {
                'uuid': 'uuid1',
                'provisionIp': '192.168.101.10',
                'provisionMac': 'aa:bb:cc:dd:ee:ff'
            }
        }
        """
        instance_obj = BmInstanceObj.from_json(req)
        volume_obj = VolumeObj.from_json(req)
        with bm_utils.rollback(self.detach_volume, req):
            volume_driver = volume.get_driver(instance_obj, volume_obj)
            volume_driver.attach()

            # Due to the limit of iBFT, there is no need to add new lun
            # info into ipxe conf file
            # self._append_conf_to_ipxe_configuration(instance_obj,
            #                                         volume_driver)

        return jsonobject.dumps(kvmagent.AgentResponse())

    @bm_utils.lock(name='baremetal_v2_volume_operator')
    @kvmagent.replyerror
    def detach_volume(self, req):
        """ Detach volume

        Configure ipxe.cfg and remove iSCSI target/md device/nbd device

        req.body::
        {
            'volume': {
                'uuid': 'uuid1',
                'primaryStorageType': 'Sharedblock',
                'type': 'Data',
                'path': 'path/to/sblk',
                'format': 'qcow2',
                'deviceId': 3
            },
            'bmInstance': {
                'uuid': 'uuid1',
                'provisionIp': '192.168.101.10',
                'provisionMac': 'aa:bb:cc:dd:ee:ff'
            }
        }
        """
        instance_obj = BmInstanceObj.from_json(req)
        volume_obj = VolumeObj.from_json(req)
        volume_driver = volume.get_driver(instance_obj, volume_obj)
        volume_driver.detach()
        # The data lun's info is not in ipxe conf file now.
        # self._remove_conf_from_ipxe_configuration(instance_obj, volume_driver)

        return jsonobject.dumps(kvmagent.AgentResponse())

    @kvmagent.replyerror
    def console(self, req):
        """ Configure console forward

        First call bm instance agent to start tightvnc/shellinabox, then
        configure nginx proxy or start socat process

        req.body::
        {
            'bmInstance': {
                'uuid': 'uuid1',
                'provisionIp': '192.168.101.10',
                'provisionMac': 'aa:bb:cc:dd:ee:ff'
            }
        }
        """
        instance_obj = BmInstanceObj.from_json(req)

        port = self._open_console(instance_obj)

        rsp = kvmagent.AgentResponse()
        setattr(rsp, 'port', port)

        return jsonobject.dumps(rsp)

    def start(self):
        self.host_uuid = None

        http_server = kvmagent.get_http_server()
        http_server.register_async_uri(self.BM_PREPARE_PROVISION_NETWORK_PATH,
                                       self.prepare_network)
        http_server.register_async_uri(self.BM_DESTROY_PROVISION_NETWORK_PATH,
                                       self.destroy_network)
        http_server.register_async_uri(self.BM_PREPARE_INSTANCE_PATH,
                                       self.prepare_instance)
        http_server.register_async_uri(self.BM_DESTROY_INSTANCE_PATH,
                                       self.destroy_instance)
        http_server.register_async_uri(self.BM_ATTACH_VOLUME_PATH,
                                       self.attach_volume)
        http_server.register_async_uri(self.BM_DETACH_VOLUME_PATH,
                                       self.detach_volume)
        http_server.register_async_uri(self.BM_CONSOLE_PATH,
                                       self.console)

    def stop(self):
        pass

    def configure(self, config):
        self.config = config
