#!/usr/bin/env python
# encoding=utf-8
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import re
import shlex
from uuid import uuid4

from gpu_tools import GPU_TOOL_PATHS, build_gpu_tool_link_command
from zstacklib import *

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy kvm agent")
start_time = datetime.datetime.now()
# set default value
file_root = "files/kvm"
memory_optimization_bundle = os.path.join(file_root, 'memory-optimization', 'zstack-zram')
package_root = "/opt/zstack-dvd/Packages"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
init = 'false'
zstack_repo = 'false'
zstack_apt_source = 'false'
chrony_servers = None
post_url = ""
pkg_kvmagent = ""
libvirtd_status = ""
libvirtd_conf_status = ""
qemu_conf_status = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None
libvirtd_conf_file = "/etc/libvirt/libvirtd.conf"
skip_packages = ""
extra_packages = ""
update_packages = 'false'
zstack_lib_dir = "/var/lib/zstack"
zstack_libvirt_nwfilter_dir = "%s/nwfilter" % zstack_lib_dir
disableIp6Tables = 'false'
bridgeDisableIptables = 'false'
enableIpv6 = 'true'
isBareMetal2Gateway='false'
releasever = ''
unsupported_iproute_list = ["nfs4", "alinux4"]
unittest_flag = 'false'
isEnableKsm = 'none'
restart_libvirtd = 'false'
enable_spice_tls = None
enable_cgroup_device_acl = None
isRemoteCube = False
reserved_ports = "49152-49215"


# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy kvm to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')
args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/kvm/" % zstack_root
workplace = "%s/kvm" % zstack_root
kvm_root = "%s/package" % workplace
iproute_pkg = "%s/iproute-2.6.32-130.el6ost.netns.2.x86_64.rpm" % file_root
iproute_local_pkg = "%s/iproute-2.6.32-130.el6ost.netns.2.x86_64.rpm" % kvm_root
iproute_el7_pkg = "%s/iproute-4.20.0-1.x86_64.rpm" % file_root
iproute_el7_local_pkg = "%s/iproute-4.20.0-1.x86_64.rpm" % kvm_root

host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
host_post_info.host_uuid = host_uuid
host_post_info.post_url = post_url
host_post_info.chrony_servers = chrony_servers
host_post_info.private_key = args.private_key
host_post_info.remote_user = remote_user
host_post_info.remote_pass = remote_pass
host_post_info.remote_port = remote_port
if remote_pass is not None and remote_user != 'root':
    host_post_info.become = True

host_info = get_remote_host_info_obj(host_post_info)
host_info = upgrade_to_helix(host_info, host_post_info)
releasever = get_host_releasever(host_info)
host_post_info.releasever = releasever

# alinux4: also enable zstack-local repo for packages not in remote repos
if releasever == "alinux4" and zstack_repo != "false":
    repo_items = [r.strip() for r in zstack_repo.strip('"').split(",") if r.strip()]
    if "zstack-local" not in repo_items:
        repo_items.append("zstack-local")
        zstack_repo = ",".join(repo_items)

# get remote host arch
IS_AARCH64 = host_info.host_arch == 'aarch64'
IS_MIPS64EL = host_info.host_arch == 'mips64el'
IS_LOONGARCH64 = host_info.host_arch == 'loongarch64'

repo_dir = "/opt/zstack-dvd/{}".format(host_info.host_arch)
if unittest_flag != 'true' and not os.path.isdir(repo_dir):
    error("Missing directory '{}', please try 'zstack-upgrade -a {}_iso'".format(repo_dir, host_info.host_arch))



def update_libvirtd_config(host_post_info):
    # name: copy libvirtd conf to keep environment consistent,only update host_uuid
    copy_arg = CopyArg()
    copy_arg.src = "%s/libvirtd.conf" % file_root
    copy_arg.dest =  libvirtd_conf_file
    file_changed_flag = copy(copy_arg, host_post_info)
    replace_content(libvirtd_conf_file, "regexp='#host_uuid.*' replace='host_uuid=\"%s\"'" % uuid4(), host_post_info)

    return file_changed_flag


def deploy_libvirt_tls_certs(host_post_info):
    """Deploy TLS certificates for libvirt on the host.

    Generates a self-signed CA on the management node (if not present),
    then issues server and client certs for the KVM host and copies them
    to the standard libvirt PKI paths.
    """
    ca_dir = "%s/pki/CA" % zstack_lib_dir
    libvirt_pki_dir = "%s/pki/libvirt" % zstack_lib_dir

    # Step 1: CA should already exist on the management node (generated and
    # persisted by Java at MN startup via JsonLabelVO).
    command = "mkdir -p {ca_dir} {libvirt_pki_dir}".format(ca_dir=ca_dir, libvirt_pki_dir=libvirt_pki_dir)
    shell_return = os.system(command)
    if shell_return != 0:
        error("Failed to create local PKI directories for libvirt TLS")

    if not os.path.isfile("%s/cacert.pem" % ca_dir) or not os.path.isfile("%s/cakey.pem" % ca_dir):
        handle_ansible_info("Libvirt TLS CA not found at %s, skipping cert deployment" % ca_dir,
                            host_post_info, "WARNING")
        return

    host_ip = host_post_info.host
    cert_tmp_dir = "/tmp/zstack-libvirt-tls-%s" % host_ip.replace('.', '_')

    # Collect all IPs for certificate SAN (management + migration network)
    # tls_cert_ips is passed from Java as "ip1,ip2,ip3" via argument_dict
    all_ips = [host_ip]
    tls_cert_ips_val = globals().get('tls_cert_ips')
    if tls_cert_ips_val:
        all_ips = [ip.strip() for ip in tls_cert_ips_val.split(',') if ip.strip()]
        if host_ip not in all_ips:
            all_ips.insert(0, host_ip)
    # deduplicate while preserving order
    all_ips = list(dict.fromkeys(all_ips))
    san_entries = ','.join(['IP:%s' % ip for ip in all_ips])

    # Step 2: Check if the host already has a complete and valid cert set.
    # Both server and client certs are required for TLS migration.
    required_remote_files = [
        "/etc/pki/CA/cacert.pem",
        "/etc/pki/libvirt/servercert.pem",
        "/etc/pki/libvirt/private/serverkey.pem",
        "/etc/pki/libvirt/clientcert.pem",
        "/etc/pki/libvirt/private/clientkey.pem",
        # QEMU TLS migration data-plane certs
        "/etc/pki/qemu/ca-cert.pem",
        "/etc/pki/qemu/client-cert.pem",
        "/etc/pki/qemu/client-key.pem",
    ]
    check_cmd = " && ".join(["test -f %s" % f for f in required_remote_files])
    (status, _) = run_remote_command(check_cmd, host_post_info, return_status=True, return_output=True)
    if status == 0:
        # All files present – verify both server and client certs against
        # the *management-node* CA so we detect a stale / foreign CA.
        local_ca_md5 = os.popen("md5sum %s/cacert.pem | awk '{print $1}'" % ca_dir).read().strip()
        (_, remote_ca_md5) = run_remote_command(
            "md5sum /etc/pki/CA/cacert.pem | awk '{print $1}'",
            host_post_info, return_status=True, return_output=True)
        remote_ca_md5 = remote_ca_md5.strip()
        if local_ca_md5 == remote_ca_md5:
            verify_cmd = (
                "openssl verify -CAfile /etc/pki/CA/cacert.pem /etc/pki/libvirt/servercert.pem 2>&1 | grep -q ': OK' && "
                "openssl verify -CAfile /etc/pki/CA/cacert.pem /etc/pki/libvirt/clientcert.pem 2>&1 | grep -q ': OK'"
            )
            (verify_status, _) = run_remote_command(verify_cmd, host_post_info, return_status=True, return_output=True)
            if verify_status == 0:
                # Also check if cert SAN covers all required IPs
                san_check_cmd = "openssl x509 -in /etc/pki/libvirt/servercert.pem -noout -ext subjectAltName 2>/dev/null"
                (san_st, san_out) = run_remote_command(san_check_cmd, host_post_info, return_status=True, return_output=True)
                san_complete = True
                if san_st == 0 and san_out:
                    for ip in all_ips:
                        if 'IP Address:%s' % ip not in san_out:
                            handle_ansible_info("Cert SAN missing IP %s, re-deploying" % ip, host_post_info, "INFO")
                            san_complete = False
                            break
                if san_complete:
                    handle_ansible_info("Libvirt TLS certs already valid on host, skipping", host_post_info, "INFO")
                    return
        handle_ansible_info("Remote certs incomplete or CA mismatch, re-deploying", host_post_info, "INFO")

    # Step 3: Generate server and client certificates for this host
    command = (
        "mkdir -p {tmp} && "
        "openssl genrsa -out {tmp}/serverkey.pem 4096 && "
        "openssl req -new -key {tmp}/serverkey.pem "
        "  -out {tmp}/server.csr -subj '/O=ZStack/CN={ip}' && "
        "openssl x509 -req -days 3650 -in {tmp}/server.csr "
        "  -CA {ca_dir}/cacert.pem -CAkey {ca_dir}/cakey.pem "
        "  -CAcreateserial -out {tmp}/servercert.pem "
        "  -extfile <(printf 'subjectAltName={san}') && "
        "openssl genrsa -out {tmp}/clientkey.pem 4096 && "
        "openssl req -new -key {tmp}/clientkey.pem "
        "  -out {tmp}/client.csr -subj '/O=ZStack/CN={ip}' && "
        "openssl x509 -req -days 3650 -in {tmp}/client.csr "
        "  -CA {ca_dir}/cacert.pem -CAkey {ca_dir}/cakey.pem "
        "  -CAcreateserial -out {tmp}/clientcert.pem "
        "  -extfile <(printf 'subjectAltName={san}')"
    ).format(tmp=cert_tmp_dir, ca_dir=ca_dir, ip=host_ip, san=san_entries)
    srl_lock_path = "%s/cacert.srl.lock" % ca_dir
    with open(srl_lock_path, 'a') as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        shell_return = os.system("bash -c '%s'" % command.replace("'", "'\\''"))
    if shell_return != 0:
        error("Failed to generate TLS certs for host %s, cannot continue without certificates" % host_ip)

    # Step 4: Create directories and copy certs to the remote host
    # /etc/pki/qemu/ is required by QEMU for TLS migration data-plane
    # (VIR_MIGRATE_TLS flag). QEMU looks for ca-cert.pem, client-cert.pem,
    # client-key.pem under /etc/pki/qemu/ by default.
    command = "mkdir -p /etc/pki/CA /etc/pki/libvirt/private /etc/pki/qemu"
    run_remote_command(command, host_post_info)

    for src_file, dest_file in [
        ("%s/cacert.pem" % ca_dir, "/etc/pki/CA/cacert.pem"),
        ("%s/servercert.pem" % cert_tmp_dir, "/etc/pki/libvirt/servercert.pem"),
        ("%s/serverkey.pem" % cert_tmp_dir, "/etc/pki/libvirt/private/serverkey.pem"),
        ("%s/clientcert.pem" % cert_tmp_dir, "/etc/pki/libvirt/clientcert.pem"),
        ("%s/clientkey.pem" % cert_tmp_dir, "/etc/pki/libvirt/private/clientkey.pem"),
        # QEMU TLS migration certs (data-plane)
        ("%s/cacert.pem" % ca_dir, "/etc/pki/qemu/ca-cert.pem"),
        ("%s/servercert.pem" % cert_tmp_dir, "/etc/pki/qemu/server-cert.pem"),
        ("%s/serverkey.pem" % cert_tmp_dir, "/etc/pki/qemu/server-key.pem"),
        ("%s/clientcert.pem" % cert_tmp_dir, "/etc/pki/qemu/client-cert.pem"),
        ("%s/clientkey.pem" % cert_tmp_dir, "/etc/pki/qemu/client-key.pem"),
    ]:
        copy_arg = CopyArg()
        copy_arg.src = src_file
        copy_arg.dest = dest_file
        copy(copy_arg, host_post_info)

    # Step 5: Set proper permissions
    command = (
        "chmod 600 /etc/pki/libvirt/private/*.pem && "
        "chmod 644 /etc/pki/libvirt/*.pem /etc/pki/CA/cacert.pem && "
        "chmod 600 /etc/pki/qemu/*-key.pem && "
        "chmod 644 /etc/pki/qemu/ca-cert.pem /etc/pki/qemu/server-cert.pem /etc/pki/qemu/client-cert.pem"
    )
    run_remote_command(command, host_post_info)

    # Step 6: Cleanup temp dir
    command = "rm -rf %s" % cert_tmp_dir
    os.system(command)

    handle_ansible_info("Deployed TLS certs for libvirt on host %s (SAN: %s)" % (host_ip, san_entries), host_post_info, "INFO")

@with_arch(todo_list=['x86_64'], host_arch=host_info.host_arch)
def check_nested_kvm(host_post_info):
    """aarch64 does not need to modprobe kvm"""
    enabled_nested_flag = False
    # enable nested kvm
    command = "cat /sys/module/kvm_intel/parameters/nested"
    (status, stdout) = run_remote_command(command, host_post_info, return_status=True, return_output=True)
    if "Y" in stdout or "1" in stdout:
        enabled_nested_flag = True

    #add kvm module and tun module
    modprobe_arg = ModProbeArg()
    modprobe_arg.name = 'kvm'
    modprobe_arg.state = 'present'
    modprobe(modprobe_arg, host_post_info)

    modprobe_arg = ModProbeArg()
    if 'intel' in host_info.cpu_info or 'zhaoxin' in host_info.cpu_info:
        # reload kvm_intel for enable nested kvm
        command = "mkdir -p /etc/modprobe.d/ && echo 'options kvm_intel nested=1' >  /etc/modprobe.d/kvm-nested.conf"
        run_remote_command(command, host_post_info)
        if enabled_nested_flag is False:
            command = "modprobe -r kvm_intel"
            run_remote_command(command, host_post_info, return_status=True)
        modprobe_arg.name = 'kvm_intel'
    elif 'amd' in host_info.cpu_info or 'hygon' in host_info.cpu_info:
        command = "mkdir -p /etc/modprobe.d/ && echo 'options kvm_amd nested=1' >  /etc/modprobe.d/kvm-nested.conf"
        run_remote_command(command, host_post_info)
        if enabled_nested_flag is False:
            command = "modprobe -r kvm_amd"
            run_remote_command(command, host_post_info, return_status=True)
        modprobe_arg.name = 'kvm_amd'
    else:
        handle_ansible_info("Unknown CPU type detected when modprobe kvm", host_post_info, "WARNING")
    modprobe_arg.state = 'present'
    modprobe(modprobe_arg, host_post_info)

    modprobe_arg = ModProbeArg()
    modprobe_arg.name = 'tun'
    modprobe_arg.state = 'present'
    modprobe(modprobe_arg, host_post_info)


def load_zstacklib():
    """include zstacklib.py"""
    zstacklib_args = ZstackLibArgs()
    zstacklib_args.distro = host_info.distro
    zstacklib_args.distro_release = host_info.distro_release
    zstacklib_args.distro_version = host_info.major_version
    zstacklib_args.zstack_root = zstack_root
    zstacklib_args.zstack_repo = zstack_repo
    zstacklib_args.host_post_info = host_post_info
    zstacklib_args.pip_url = pip_url
    zstacklib_args.zstack_releasever = releasever
    zstacklib_args.trusted_host = trusted_host
    zstacklib_args.host_info = host_info
    if host_info.distro in DEB_BASED_OS:
        zstacklib_args.apt_server = yum_server
        zstacklib_args.zstack_apt_source = zstack_repo
    else :
        zstacklib_args.yum_server = yum_server
    zstacklib = ZstackLib(zstacklib_args)


load_zstacklib()


# name: judge this process is init install or upgrade
if file_dir_exist("path=" + kvm_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (kvm_root, virtenv_path)
    host_post_info.post_label = "ansible.shell.mkdir"
    host_post_info.post_label_param = "%s, %s" % (kvm_root, virtenv_path)
    run_remote_command(command, host_post_info)


run_remote_command("rm -rf {}/*; mkdir -p /usr/local/zstack/ || true".format(kvm_root), host_post_info)


def install_kvm_pkg():
    def rpm_based_install():
        os_base_dep = "bridge-utils chrony conntrack-tools cyrus-sasl-md5 device-mapper-multipath expect ipmitool iproute ipset \
                        usbredir-server iputils libvirt libvirt-client lighttpd lsof net-tools nfs-utils nmap openssh-clients \
                        smartmontools sshpass usbutils wget audit collectd-virt storcli nvme-cli pv rsync sed pciutils tar"

        distro_mapping = {
            'centos': 'vconfig iscsi-initiator-utils OpenIPMI-modalias OVMF mcelog MegaCli Arcconf python-pyudev kernel-devel libicu edac-utils',
            'kylin': 'vconfig open-iscsi python2-pyudev collectd-disk OpenIPMI libselinux-devel nettle tuned qemu-kvm libicu edac-utils lldpd freeipmi tcpdump',
            'uniontech': 'vconfig iscsi-initiator-utils OpenIPMI nettle qemu-kvm python-pyudev collectd-disk',
            'rocky': 'iscsi-initiator-utils OpenIPMI-modalias mcelog MegaCli Arcconf python-pyudev kernel-devel collectd-disk edac-utils',
            'alinux': 'iscsi-initiator-utils OpenIPMI-modalias mcelog MegaCli Arcconf kernel-devel edac-utils',
            'alibaba': 'iscsi-initiator-utils kernel-devel',
        }

        helix_rhel_rpms = ('iscsi-initiator-utils OpenIPMI-modalias mcelog '
                           'MegaCli Arcconf kernel-devel '
                           'edac-utils')

        py3_rpms = 'python3.11 python3.11-devel python3.11-pip libffi-devel openssl-devel'

        releasever_mapping = {
            'c74': 'qemu-kvm',
            'c76': 'qemu-kvm libvirt-admin seabios-bin nping elfutils-libelf-devel freeipmi %s' % py3_rpms,
            'c79': 'qemu-kvm libvirt-admin seabios-bin nping elfutils-libelf-devel freeipmi %s' % py3_rpms,
            'h76c': ('%s qemu-kvm libvirt-admin seabios-bin nping freeipmi '
                     'elfutils-libelf-devel vconfig OVMF libicu %s') % (helix_rhel_rpms, py3_rpms),
            'h79c': ('%s qemu-kvm libvirt-admin seabios-bin nping freeipmi '
                     'elfutils-libelf-devel vconfig OVMF libicu %s') % (helix_rhel_rpms, py3_rpms),
            'h84r': ('%s qemu-kvm libvirt-daemon libvirt-daemon-kvm freeipmi '
                     'seabios-bin elfutils-libelf-devel collectd-disk lldpd tcpdump %s') % (helix_rhel_rpms, py3_rpms),
            'uos20r': ('%s qemu-kvm libvirt-daemon libvirt-daemon-kvm freeipmi '
                     'seabios-bin elfutils-libelf-devel collectd-disk lldpd tcpdump %s') % (helix_rhel_rpms, py3_rpms),
            'rl84': 'qemu-kvm libvirt-daemon libvirt-daemon-kvm seabios-bin elfutils-libelf-devel lldpd',
            'euler20': 'vconfig open-iscsi OpenIPMI-modalias qemu python2-pyudev collectd-disk',
            'oe2203sp1': 'vconfig open-iscsi OpenIPMI-modalias qemu python2-pyudev collectd-disk edac-utils lldpd tcpdump',
            'oe2403sp1': 'vconfig open-iscsi qemu collectd-disk tcpdump %s' % py3_rpms,
            'ky10sp3': py3_rpms,
            'ky10sp3.2403': py3_rpms,
            'h2203sp1o': 'vconfig open-iscsi OpenIPMI-modalias qemu python2-pyudev collectd-disk edac-utils freeipmi lldpd tcpdump %s' % py3_rpms,
            'nfs4': 'vconfig iscsi-initiator-utils OpenIPMI nettle libselinux-devel iptables iptables-services qemu-kvm python2-pyudev collectd-disk',
            'alinux4': ('%s qemu-kvm libvirt-daemon libvirt-daemon-kvm freeipmi '
                        'seabios-bin elfutils-libelf-devel collectd-disk lldpd tcpdump %s') % (helix_rhel_rpms, py3_rpms),
        }

        edk2_mapping = {
            'x86_64': 'edk2-ovmf edk2.git-ovmf-x64',
            'aarch64': 'edk2-aarch64'
        }
        
        arch_exclude_mapping = {
            'loongarch64': 'edac-utils freeipmi lldpd libcbd',
            'x86_64_alinux4': 'usbredir-server storcli OpenIPMI-modalias MegaCli Arcconf edac-utils',
            'aarch64_alinux4': 'usbredir-server storcli OpenIPMI-modalias MegaCli Arcconf edac-utils lldpd edk2-ovmf edk2.git-ovmf-x64 mcelog seabios-bin'
        }

        arch_release_mapping = {
            'loongarch64_oe2403sp1': 'edk2-ovmf-loongarch64'
        }

        cube_distro_mapping = {
            'x86_64_centos': "lm_sensors",
            'aarch64_kylin': "lm_sensors edac-utils",
            'x86_64_kylin': "lm_sensors edac-utils Arcconf",
        }

        cube_releasever_mapping = {
            'h84r': "lm_sensors",
            'uos20r': "lm_sensors"
        }

        # handle zstack_repo
        if zstack_repo != 'false':
            distro_head = host_info.distro.split("_")[0] if releasever in kylin or releasever in uos else host_info.distro
            arch_release = "%s_%s" % (host_info.host_arch, releasever)
            common_dep_list = "%s %s %s %s %s" % (
                os_base_dep,
                distro_mapping.get(distro_head, ''),
                releasever_mapping.get(releasever, ''),
                edk2_mapping.get(host_info.host_arch, ''),
                arch_release_mapping.get(arch_release, ''))
            # common kvmagent deps of x86 and arm that need to update
            common_update_list = ("sanlock sysfsutils hwdata sg3_utils lvm2"
                                  " lvm2-libs lvm2-lockd systemd openssh"
                                  " glusterfs")
            common_no_update_list = "librbd1"
            # common kvmagent deps of x86 and arm that no need to update
            common_dep_list = "%s %s" % (common_dep_list, common_update_list)

            if isRemoteCube:
                cube_distro_info = host_info.host_arch + "_" + distro_head
                common_dep_list = "%s %s %s" % (common_dep_list, cube_distro_mapping.get(cube_distro_info, ''), cube_releasever_mapping.get(releasever, ''))

            dep_list = common_dep_list
            update_list = common_update_list
            no_update_list = common_no_update_list

            # libvirt does not need to be updated
            command = "which virsh"
            host_post_info.post_label = "ansible.shell.install.pkg"
            host_post_info.post_label_param = "libvirt"
            (status, output) = run_remote_command(command, host_post_info, True, True)
            if output:
                # python3-libvirt installation does not affect the libvirt installation
                command = (
                    "yum --disablerepo=* --enablerepo={0} --assumeno install python3-libvirt |awk '{{print $1}}' | grep -Ew '^\s*libvirt\s*$'").format(
                    zstack_repo)
                host_post_info.post_label = "ansible.shell.install.pkg"
                host_post_info.post_label_param = "python3-libvirt"
                (status, output) = run_remote_command(command, host_post_info, True, True)
                is_libvirt = lambda x: x.startswith("libvirt") and not x.startswith("libvirt-devel")
                if status is True:
                    dep_list = ' '.join([pkg for pkg in dep_list.split() if not is_libvirt(pkg)])
                else:
                    dep_list = ' '.join([pkg for pkg in dep_list.split() if pkg == 'python3-libvirt' or not is_libvirt(pkg)])

            # add extra package
            if extra_packages != '':
                dep_list = dep_list + " " + extra_packages

            exclude_pkgs = arch_exclude_mapping.get(host_info.host_arch + "_" + releasever, arch_exclude_mapping.get(host_info.host_arch, ""))
            if exclude_pkgs:
                dep_list = ' '.join([pkg for pkg in dep_list.split() if pkg not in exclude_pkgs.split()])

            # skip these packages when connect host
            _skip_list = re.split(r'[|;,\s]\s*', skip_packages)
            _skip_list.extend(["open-iscsi"])
            _dep_list = [ pkg for pkg in dep_list.split() if pkg not in _skip_list ]
            dep_list = ' '.join(_dep_list)
            if 'storcli' in _dep_list:
                update_list += ' storcli'

            # name: install/update kvm related packages on RedHat based OS from user defined repo
            command = ("echo {1} >/var/lib/zstack/dependencies && yum --disablerepo=* --enablerepo={0} clean metadata >/dev/null && \
                    pkg_list=`rpm -q {1} | grep \"not installed\" | awk '{{ print $2 }}'`' {2}' && \
                    for pkg in {4}; do yum --disablerepo=* --enablerepo={0} install -y $pkg >/dev/null || exit 1; done; \
                    pkg_list=`rpm -q {3} | grep \"not installed\" | awk '{{ print $2 }}'` && \
                    for pkg in $pkg_list; do yum --disablerepo=* --enablerepo={0} install -y $pkg >/dev/null || exit 1; done; \
                    ").format(zstack_repo, dep_list, update_list, no_update_list, dep_list if update_packages == 'true' else '$pkg_list')
            host_post_info.post_label = "ansible.shell.install.pkg"
            host_post_info.post_label_param = dep_list
            run_remote_command(command, host_post_info)
            if host_info.host_arch == 'loongarch64' and releasever in kylin and yum_check_package("qemu", host_post_info):
                command = "yum --disablerepo=* --enablerepo={0} install -y qemu-block-rbd;".format(zstack_repo)
                host_post_info.post_label_param = "qemu-block-rbd"
                run_remote_command(command, host_post_info)
        else:
            # name: install kvm related packages on RedHat based OS from online
            for pkg in ['zstack-release', 'openssh-clients', 'bridge-utils', 'wget', 'chrony', 'sed', 'libvirt', 'nfs-utils', 'vconfig',
                        'libvirt-client', 'net-tools', 'iscsi-initiator-utils', 'lighttpd', 'iproute', 'sshpass',
                        'libguestfs-winsupport', 'libguestfs-tools', 'pv', 'rsync', 'nmap', 'ipset', 'usbutils', 'pciutils', 'expect',
                        'lvm2', 'lvm2-lockd', 'sanlock', 'sysfsutils', 'smartmontools', 'device-mapper-multipath', 'hwdata', 'sg3_utils']:
                yum_install_package(pkg, host_post_info)
            if host_info.major_version >= 7:
                # name: RHEL7 specific packages from online
                for pkg in ['qemu-kvm', 'qemu-img', 'collectd-virt']:
                    yum_install_package(pkg, host_post_info)
            else:
                for pkg in ['qemu-kvm', 'qemu-img']:
                    yum_install_package(pkg, host_post_info)

        # handle distro version specific task
        if releasever not in unsupported_iproute_list and host_info.major_version < 7:
            # name: copy name space supported iproute for RHEL6
            copy_arg = CopyArg()
            copy_arg.src = iproute_pkg
            copy_arg.dest = iproute_local_pkg
            copy(copy_arg, host_post_info)
            # name: Update iproute for RHEL6
            command = "rpm -q iproute-2.6.32-130.el6ost.netns.2.x86_64 || yum install --nogpgcheck -y %s" % iproute_local_pkg
            host_post_info.post_label = "ansible.shell.install.pkg"
            host_post_info.post_label_param = "iproute-2.6.32-130.el6ost.netns.2.x86_64"
            run_remote_command(command, host_post_info)
            # name: disable NetworkManager in RHEL6 and Centos6
            network_manager_installed = yum_check_package("NetworkManager", host_post_info)
            if network_manager_installed is True:
                service_status("NetworkManager", "state=stopped enabled=no", host_post_info)
        else:
            if releasever not in unsupported_iproute_list and host_info.major_version == 7:
                # name: copy name space supported iproute for RHEL7
                copy_arg = CopyArg()
                copy_arg.src = iproute_el7_pkg
                copy_arg.dest = iproute_el7_local_pkg
                copy(copy_arg, host_post_info)
                # name: Update iproute for RHEL7
                command = "rpm -q iproute-4.20.0-1.x86_64 || yum install --nogpgcheck -y %s" % iproute_el7_local_pkg
                host_post_info.post_label = "ansible.shell.install.pkg"
                host_post_info.post_label_param = "iproute-4.20.0-1.x86_64"
                run_remote_command(command, host_post_info)
            # name: disable firewalld in RHEL7 and Centos7
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            host_post_info.post_label = "ansible.shell.disable.service"
            host_post_info.post_label_param = "firewalld"
            run_remote_command(command, host_post_info)
            if releasever in enable_networkmanager_list:
                # name: enable NetworkManager in euler20, arm and x86 ky10
                """config NetworkManager(fix 40371)"""
                NETWORKMANAGER_CONF_FILE = '/etc/NetworkManager/NetworkManager.conf'
                replace_content(NETWORKMANAGER_CONF_FILE, "regexp='.*no-auto-default=.*' replace='no-auto-default=*'",
                                host_post_info)
                service_status("NetworkManager", "state=started enabled=yes", host_post_info, ignore_error=True)
            else:
                # name: disable NetworkManager in RHEL7 and Centos7
                service_status("NetworkManager", "state=stopped enabled=no", host_post_info, ignore_error=True)

        if init == 'true':
            # name: copy iptables initial rules in RedHat
            copy_arg = CopyArg()
            copy_arg.src = "%s/iptables" % file_root
            copy_arg.dest = "/etc/sysconfig/iptables"
            copy(copy_arg, host_post_info)
            if chroot_env == 'false':
                # name: restart iptables
                # name: workaround RHEL7 iptables service issue
                command = 'mkdir -p /var/lock/subsys/'
                run_remote_command(command, host_post_info)
                service_status("iptables", "state=restarted enabled=yes", host_post_info)

        #we should check libvirtd config file status before restart the service
        libvirtd_conf_status = update_libvirtd_config(host_post_info)
        # deploy TLS certificates unconditionally - the function has built-in
        # idempotency checks and will skip if certs are already valid
        deploy_libvirt_tls_certs(host_post_info)
        # in the libvirtd 5.6.0 and later, the libvirtd daemon now prefers to uses systemd socket activation
        command = "libvirtd --version | grep 'libvirtd (libvirt) ' | cut -d ' ' -f 3 | cut -d '(' -f 1"
        (status, libvirtd_version) = run_remote_command(command, host_post_info, False, True)
        if NumericVersion(libvirtd_version) >= NumericVersion('5.6.0'):
            command = 'systemctl mask libvirtd.socket libvirtd-ro.socket libvirtd-admin.socket libvirtd-tls.socket libvirtd-tcp.socket'
            run_remote_command(command, host_post_info)
        if chroot_env == 'false':
            # name: enable libvirt daemon on RedHat based OS
            service_status("libvirtd", "state=started enabled=yes", host_post_info)
            if host_info.major_version >= 7:
                # name: enable virtlockd daemon on RedHat based OS
                service_status("virtlockd", "state=stopped enabled=no", host_post_info)
                service_status("virtlogd", "state=started enabled=yes", host_post_info, True)

        #run_remote_command(command, host_post_info)
        # name: disable selinux on RedHat based OS
        set_selinux("state=disabled", host_post_info)
        run_remote_command("setenforce 0 || true", host_post_info)
        # name: copy sysconfig libvirtd conf in RedHat
        copy_arg = CopyArg()
        copy_arg.src = "%s/libvirtd" % file_root
        copy_arg.dest = "/etc/sysconfig/libvirtd"
        libvirtd_status = copy(copy_arg, host_post_info)

        # replace qemu-img binary if qemu-img-ev before 2.12.0 is installed, to fix zstack-11004 / zstack-13594 / zstack-20983
        (status, qemu_img_version) = get_qemu_img_version(host_post_info)
        if qemu_img_version is None or qemu_img_version == '':
            error('cannot get qemu-img version!')
        if NumericVersion(qemu_img_version) < NumericVersion('2.12.0'):
            qemu_img_src = '{}/{}'.format(file_root, "qemu-img" if host_info.host_arch == 'x86_64' else "qemu-img_"+host_info.host_arch )
            qemu_img_dst = '{}/{}'.format(kvm_root, 'qemu-img')
            copy_to_remote(qemu_img_src, qemu_img_dst, None, host_post_info)

            command = "for i in {1..3}; do /bin/cp %s `which qemu-img` && break || sleep 2; done; sync" % qemu_img_dst
            host_post_info.post_label = "ansible.shell.install.pkg"
            host_post_info.post_label_param = "qemu-img"
            run_remote_command(command, host_post_info)

    def deb_based_install():
        # name: install kvm related packages on Debian based OS
        install_pkg_list = ['curl', 'qemu', 'qemu-system', 'bridge-utils', 'wget', 'qemu-utils', 'python3-libvirt',
                            'libvirt-daemon-system', 'libfdt-dev', 'libvirt-dev', 'libvirt-clients', 'chrony','vlan',
                            'libguestfs-tools', 'sed', 'nfs-common', 'open-iscsi','ebtables', 'pv', 'usbutils',
                            'pciutils', 'expect', 'lighttpd', 'sshpass', 'rsync', 'iputils-arping', 'nmap', 'collectd',
                            'iptables', 'python-pip', 'dmidecode', 'ovmf', 'auditd', 'ipset',
                            'multipath-tools', 'uuid-runtime', 'lvm2', 'lvm2-lockd', 'udev', 'sanlock', 'usbredirserver', 'python-pyudev']
        apt_install_packages(install_pkg_list, host_post_info)
        if zstack_repo == 'false':
            command_deb_list = "echo %s >/var/lib/zstack/dependencies".format(' '.join(install_pkg_list))
            run_remote_command(command_deb_list, host_post_info)
        # name: copy default libvirtd conf in Debian
        copy_arg = CopyArg()
        copy_arg.src = "%s/libvirt-bin" % file_root
        copy_arg.dest = '/etc/default/libvirt-bin'
        libvirt_bin_status = copy(copy_arg, host_post_info)
        # name: enable bridge forward on UBUNTU
        command = "modprobe br_netfilter"
        host_post_info.post_label = "ansible.shell.enable.module"
        host_post_info.post_label_param = "br_netfilter"
        run_remote_command(command, host_post_info)
        update_pkg_list = ['ebtables', 'python3-libvirt', 'qemu-system-arm']
        apt_update_packages(update_pkg_list, host_post_info)
        libvirtd_conf_status = update_libvirtd_config(host_post_info)
        # deploy TLS certificates unconditionally - idempotent, skips if valid
        deploy_libvirt_tls_certs(host_post_info)
        if chroot_env == 'false':
            # name: enable libvirt daemon on RedHat based OS
            service_status("libvirtd", "state=started enabled=yes", host_post_info)
        # name: copy default libvirtd conf in Debian
        copy_arg = CopyArg()
        copy_arg.src = "%s/libvirtd_debian" % file_root
        copy_arg.dest = "/etc/default/libvirtd"
        libvirtd_status = copy(copy_arg, host_post_info)

    def rpm_based_deprecated():
        rpm_deprecated = {
            "x86_64_c76": "",
            "x86_64_c79": "",
            "x86_64_c74": "",
        }

        rpm_deprecated_list = rpm_deprecated.get(host_info.host_arch + "_" + releasever, "")
        # new-add host
        if releasever in ['c76', 'c79', 'h76c', 'h79c', 'c74'] and "qemu-kvm" not in skip_packages:
            rpm_deprecated_list += " qemu-img-ev qemu-kvm-ev qemu-kvm-common-ev"

        rpm_deprecated_list += " lvm2-help"
        rpm_deprecated_list += " device-mapper-devel device-mapper-event-devel"

        if rpm_deprecated_list.strip():
            command = "yum --disablerepo=* remove %s -y;" % rpm_deprecated_list
            run_remote_command(command, host_post_info)

    if host_info.distro in RPM_BASED_OS:
        rpm_based_deprecated()
        rpm_based_install()
    elif host_info.distro in DEB_BASED_OS:
        deb_based_install()
    else:
        error("unsupported OS!")

def copy_tools():
    """copy binary tools"""
    tool_list = ['collectd_exporter', 'node_exporter', 'ipmi_exporter', 'dnsmasq', 'zwatch-vm-agent', 'zwatch-vm-agent_freebsd_amd64', 'pushgateway', 'sas3ircu', 'zs-raid-heartbeat']

    for tool in tool_list:
        arch_lable = '' if host_info.host_arch == 'x86_64' else '_' + host_info.host_arch
        real_name = tool + arch_lable
        if releasever == "oe2403sp1":
            real_name = real_name + '_abi2'
        pkg_path = os.path.join(file_root, real_name)

        if tool == "dnsmasq":
            pkg_dest_path = "/usr/local/zstack/dnsmasq"
        elif tool == "sas3ircu":
            pkg_dest_path = "/usr/bin/sas3ircu"
        else:
            pkg_dest_path = os.path.join(workplace, tool)
        if os.path.exists(pkg_path):
            copy_to_remote(pkg_path, pkg_dest_path, "mode=755", host_post_info)

    # create pushgateway persistence data directory
    command = 'mkdir -p %s' % os.path.join(zstack_lib_dir, 'prometheus', 'host_pushgateway')
    run_remote_command(command, host_post_info)

def copy_kvm_files():
    """copy kvmagent files and packages"""
    global qemu_conf_status, copy_zstacklib_status, copy_kvmagent_status, copy_smart_nics_status

    # copy agent files
    file_list = ["vm-tools.sh", "agent_version", "kvmagent-iptables", "shutdown_vm"]
    for file in file_list:
        _src = os.path.join(file_root, file)
        _dst = os.path.join(workplace, file)
        copy_to_remote(_src, _dst, None, host_post_info)

    # copy qemu configration file
    qemu_conf_src = os.path.join(file_root, "qemu.conf")
    qemu_conf_dst = "/etc/libvirt/qemu.conf"
    qemu_conf_status = copy_to_remote(qemu_conf_src, qemu_conf_dst, None, host_post_info)

    if enable_spice_tls == 'true':
        # unnote following lines in qemu.conf
        #spice_tls_x509_cert_dir = "/var/lib/zstack/kvm/package/spice-certs/"
        #spice_tls = 1
        replace_content(qemu_conf_dst, "regexp='^#spice_tls_x509_cert_dir.*' replace='spice_tls_x509_cert_dir = \"/var/lib/zstack/kvm/package/spice-certs/\"'", host_post_info)
        replace_content(qemu_conf_dst, "regexp='^#spice_tls.*' replace='spice_tls = 1'", host_post_info)
    elif enable_spice_tls == 'false':
        # disable spice_tls
        replace_content(qemu_conf_dst, "regexp='^spice_tls_x509_cert_dir = \"/var/lib/zstack/kvm/package/spice-certs/\"' replace='#spice_tls_x509_cert_dir ='", host_post_info)
        replace_content(qemu_conf_dst, "regexp='^spice_tls = 1' replace='#spice_tls = 1'", host_post_info)

    if enable_cgroup_device_acl == 'true':
        replace_content(qemu_conf_dst, "regexp='^#(cgroup_device_acl = \[|\s*\"/dev/.*\",|\s*\])' replace='\\1'", host_post_info)

        (status, stdout) = run_remote_command("ls /dev/infiniband/", host_post_info, return_status=True, return_output=True)
        if status is True:
            infiniband_devices = ['/dev/infiniband/' + item for item in stdout.split('\n')]
            formatted_devices = ',\\n    '.join('\\"%s\\"' % device for device in infiniband_devices)
            add_infiniband_devices_args = "regexp='(cgroup_device_acl\s*=\s*\[[^\]]*?,\s*)' replace='\\1" + formatted_devices + ",\\n    '"
            replace_content(qemu_conf_dst, add_infiniband_devices_args, host_post_info)

        # Add Hygon vfio and mdev devices to cgroup_device_acl (only for Hygon SE hosts).
        # Newer Hygon SE hosts may not expose /dev/hygon_psp_config, but still
        # expose the /dev/hct_share device that must be whitelisted.
        (is_hygon_host, _) = run_remote_command(
            "test -e /dev/hygon_psp_config || test -e /dev/hct_share",
            host_post_info, return_status=True, return_output=True)
        if is_hygon_host is True:
            # Pre-write a fixed range of /dev/vfio/1 to /dev/vfio/5000 to cover all possible iommu_group numbers
            # This avoids the chicken-and-egg problem where mdev devices don't exist yet during ansible deploy
            vfio_devices = ['/dev/vfio/%d' % i for i in range(1, 5001)]
            vfio_devices.append('/dev/vfio/vfio')
            vfio_devices.append('/dev/hygon_psp_config')
            vfio_devices.append('/dev/hct_share')

            # Format devices with 15 per line for better readability
            lines = []
            for i in range(0, len(vfio_devices), 15):
                chunk = vfio_devices[i:i+15]
                lines.append(', '.join('\\"%s\\"' % d for d in chunk))
            formatted_devices = ',\\n    '.join(lines)
            add_vfio_devices_args = "regexp='(cgroup_device_acl\s*=\s*\[[^\]]*?,\s*)' replace='\\1" + formatted_devices + ",\\n    '"
            replace_content(qemu_conf_dst, add_vfio_devices_args, host_post_info)

    # copy zstacklib pkg
    zslib_src = os.path.join("files/zstacklib", pkg_zstacklib)
    zslib_dst = os.path.join(kvm_root, pkg_zstacklib)
    copy_zstacklib_status = copy_to_remote(zslib_src, zslib_dst, None, host_post_info)

    # copy smart-nics file
    command = 'mkdir -p /usr/local/etc/zstack-ovs/'
    run_remote_command(command, host_post_info)
    smart_nics_src = os.path.join(file_root, "smart-nics.yaml")
    smart_nics_dst = "/usr/local/etc/zstack-ovs/smart-nics.yaml"
    copy_smart_nics_status = copy_to_remote(smart_nics_src, smart_nics_dst, None, host_post_info)

    # copy kvmagent pkg
    kvmagt_src = os.path.join(file_root, pkg_kvmagent)
    kvmagt_dst = os.path.join(kvm_root, pkg_kvmagent)
    copy_kvmagent_status = copy_to_remote(kvmagt_src, kvmagt_dst, None, host_post_info)

    # copy kvmagent service
    kvmagt_svc_src = "files/kvm/zstack-kvmagent"
    kvmagt_svc_dst = "/etc/init.d/"
    args = "mode=755"
    copy_to_remote(kvmagt_svc_src, kvmagt_svc_dst, args, host_post_info)

    # copy sysctl file
    sysctl_src = os.path.join(file_root, "sysctl")
    sysctl_dst = "/var/lib/zstack/kvm"
    args = "directory_mode=755"
    copy_to_remote(sysctl_src, sysctl_dst, args, host_post_info)
    command = 'sysctl -p /var/lib/zstack/kvm/sysctl/default.conf'
    run_remote_command(command, host_post_info)

    command = 'sysctl -w net.ipv4.ip_local_reserved_ports=%s,`cat /proc/sys/net/ipv4/ip_local_reserved_ports`' % reserved_ports
    run_remote_command(command, host_post_info)


def configure_host_ipv6():
    disable_ipv6 = '0' if enableIpv6 == 'true' else '1'

    update_file("/etc/sysctl.conf", "regexp='^net.ipv6.conf.all.disable_ipv6\\s*=.*' line='net.ipv6.conf.all.disable_ipv6 = %s'" % disable_ipv6, host_post_info)
    update_file("/etc/sysctl.conf", "regexp='^net.ipv6.conf.default.disable_ipv6\\s*=.*' line='net.ipv6.conf.default.disable_ipv6 = %s'" % disable_ipv6, host_post_info)
    run_remote_command("sysctl -w net.ipv6.conf.all.disable_ipv6=%s" % disable_ipv6, host_post_info)
    run_remote_command("sysctl -w net.ipv6.conf.default.disable_ipv6=%s" % disable_ipv6, host_post_info)

def copy_gpudriver():
    """copy mxgpu driver"""
    _src = "{}/mxgpu_driver.tar.gz".format(file_root)
    _dst = "/var/lib/zstack/mxgpu_driver.tar.gz"
    copy_to_remote(_src, _dst, None, host_post_info)

def create_virtio_driver_directory():
    _dst_path = "/var/lib/zstack/virtio-drivers/"
    run_remote_command("mkdir -p %s" % _dst_path, host_post_info)

@on_debian_based(host_info.distro)
def copy_ovmf_tools():
    _src = "/opt/zstack-dvd/{}/{}/ovmf_tools/".format(host_info.host_arch, releasever)
    _dst = "/usr/share/OVMF/"
    copy_to_remote(_src, _dst, None, host_post_info)


def copy_exporter_tools():
    """copy zs-exporter from mn_node to host_node"""
    file_list = ["process_exporter", "zstack_service_exporter"]
    for file in file_list:
        _src = '/opt/zstack-dvd/{}/{}/tools/{}'.format(host_info.host_arch, releasever, file)
        if os.path.exists(_src):
            _dst = os.path.join(workplace, file)
            copy_to_remote(_src, _dst, "mode=755", host_post_info)


def copy_lsusb_scripts():
    _src = os.path.join(file_root, "lsusb.py")
    _dst = "/usr/local/bin/"
    copy_to_remote(_src, _dst, "mode=755", host_post_info)

@on_redhat_based(host_info.distro)
def copy_zs_scripts():
    """copy zs-xxx from mn_node to host_node"""
    _src = '/opt/zstack-dvd/{}/{}/scripts/'.format(host_info.host_arch, releasever)
    _dst = '/usr/local/bin/'
    copy_to_remote(_src, _dst, "mode=755", host_post_info)

@on_redhat_based(host_info.distro)
def copy_grubaa64_efi():
    """copy grubaa64.efi from mn_node to bm2 gateway"""
    _src = os.path.join(file_root, "grubaa64.efi")
    _dst = "/var/lib/zstack/baremetalv2/tftpboot/"
    copy_to_remote(_src, _dst, "mode=755", host_post_info)


@on_redhat_based(host_info.distro, exclude=['alibaba'])
def set_max_performance():
    # AliOS 7u2 does not support tuned-adm
    command = "tuned-adm profile virtual-host; echo virtual-host > /etc/tuned/active_profile"
    host_post_info.post_label = "ansible.shell.set.tuned.profile"
    host_post_info.post_label_param = "set profile as virtual-host"
    run_remote_command(command, host_post_info)

@on_redhat_based(host_info.distro)
def copy_bond_conf():
    """copy bond.conf from mn_node to host_node"""
    _src = os.path.join(file_root, "bond.conf")
    _dst = "/etc/modprobe.d/"
    copy_to_remote(_src, _dst, "mode=644", host_post_info)


def copy_cube_tools():
    """copy cube required tools from mn_node to host_node"""
    cube_root_dst = "/usr/local/hyperconverged/"
    _src = os.path.join(cube_root_dst, "tools/hd_ctl")
    if isRemoteCube and os.path.exists(_src):
        _dst = os.path.join(cube_root_dst, "tools")
        copy_to_remote(_src, _dst, "mode=755", host_post_info)
        command = "ln -sf /usr/local/hyperconverged/tools/hd_ctl/hd_ctl /bin/"
        run_remote_command(command, host_post_info)


def do_libvirt_qemu_config():
    """special configration"""

    # remove libvirt default bridge
    command = '(ip addr show dev virbr0 &> /dev/null && virsh net-destroy default > ' \
              '/dev/null && virsh net-undefine default > /dev/null) || true'
    host_post_info.post_label = "ansible.shell.virsh.destroy.bridge"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)

    # delete A2 qemu hook
    command = "rm -f /etc/libvirt/hooks/qemu"
    host_post_info.post_label = "ansible.shell.remove.file"
    host_post_info.post_label_param = "/etc/libvirt/hooks/qemu"
    run_remote_command(command, host_post_info)


def do_network_config():
    # name: enable bridge forward
    if bridgeDisableIptables == "true":
        command = " [ `sysctl -n net.bridge.bridge-nf-call-iptables` -eq 1 ] && sysctl -w net.bridge.bridge-nf-call-iptables=0 >> /etc/sysctl.conf ; echo 1 > /proc/sys/net/bridge/bridge-nf-filter-vlan-tagged ; echo 1 > /proc/sys/net/ipv4/conf/default/forwarding"
        host_post_info.post_label = "ansible.shell.enable.service"
        host_post_info.post_label_param = "bridge forward"
        run_remote_command(command, host_post_info)
    else:
        command = " [ `sysctl -n net.bridge.bridge-nf-call-iptables` -eq 0 ] && sysctl -w net.bridge.bridge-nf-call-iptables=1 >> /etc/sysctl.conf ; echo 1 > /proc/sys/net/bridge/bridge-nf-filter-vlan-tagged ; echo 1 > /proc/sys/net/ipv4/conf/default/forwarding"
        host_post_info.post_label = "ansible.shell.enable.service"
        host_post_info.post_label_param = "bridge forward"
        run_remote_command(command, host_post_info)

    if disableIp6Tables != 'true':
        if host_info.distro in RPM_BASED_OS:
            # name: copy ip6tables initial rules in RedHat
            IP6TABLE_SERVICE_FILE = '/usr/lib/systemd/system/ip6tables.service'
            copy_arg = CopyArg()
            copy_arg.src = "%s/ip6tables" % file_root
            copy_arg.dest = "/etc/sysconfig/ip6tables"
            copy(copy_arg, host_post_info)
            run_remote_command('mkdir -p /var/lock/subsys/', host_post_info)
            replace_content(IP6TABLE_SERVICE_FILE, "regexp='syslog.target,iptables.service' replace='syslog.target iptables.service'", host_post_info)
            service_status("ip6tables", "state=restarted enabled=yes", host_post_info)
        elif host_info.distro in DEB_BASED_OS:
            copy_arg = CopyArg()
            copy_arg.src = "%s/ip6tables" % file_root
            copy_arg.dest = "/etc/iptables/rules.v6"
            copy(copy_arg, host_post_info)
            command = "ip6tables-save"
            run_remote_command(command, host_post_info)

        # name: copy libvirt nw-filter
        copy_arg = CopyArg()
        copy_arg.src = "%s/zstack-libvirt-nwfilter/" % file_root
        copy_arg.dest = "%s/" % zstack_libvirt_nwfilter_dir
        copy(copy_arg, host_post_info)

        # name: enable bridge forward
        command = "echo 1 > /proc/sys/net/bridge/bridge-nf-call-ip6tables ; echo 1 > /proc/sys/net/ipv6/conf/default/forwarding"
        host_post_info.post_label = "ansible.shell.enable.service"
        host_post_info.post_label_param = "bridge forward"
        run_remote_command(command, host_post_info)


def copy_spice_certificates_to_host():
    """copy spice certificates"""

    spice_certificates_path = os.path.join(file_root, "spice-certs")
    if not os.path.isdir(spice_certificates_path):
        return

    if kvm_root is not None:
        run_remote_command("rm -rf %s/%s && mkdir -p %s/%s " % (kvm_root, "spice-certs", kvm_root, "spice-certs"),
                           host_post_info)

    local_cert_dir = os.path.join(file_root, "spice-certs")
    copy_arg = CopyArg()
    copy_arg.src = "%s/%s" % (local_cert_dir, "ca-cert.pem")
    copy_arg.dest = "%s/%s/%s" % (kvm_root, "spice-certs", "ca-cert.pem")
    copy_arg.args = "mode=644"
    copy(copy_arg, host_post_info)

    copy_arg = CopyArg()
    copy_arg.src = "%s/%s" % (local_cert_dir, "ca-key.pem")
    copy_arg.dest = "%s/%s/%s" % (kvm_root, "spice-certs", "ca-key.pem")
    copy_arg.args = "mode=400"
    copy(copy_arg, host_post_info)

    copy_arg = CopyArg()
    copy_arg.src = "%s/%s" % (local_cert_dir, "server-cert.pem")
    copy_arg.dest = "%s/%s/%s" % (kvm_root, "spice-certs", "server-cert.pem")
    copy_arg.args = "mode=644"
    copy(copy_arg, host_post_info)

    copy_arg = CopyArg()
    copy_arg.src = "%s/%s" % (local_cert_dir, "server-key.pem")
    copy_arg.dest = "%s/%s/%s" % (kvm_root, "spice-certs", "server-key.pem")
    copy_arg.args = "mode=400"
    copy(copy_arg, host_post_info)

def install_virtualenv():
    """install virtualenv"""

    py_version = get_virtualenv_python_version(virtenv_path, host_post_info)
    if py_version and not py_version.startswith("3.11"):
        command = "rm -rf %s" % virtenv_path
        host_post_info.post_label = "ansible.shell.remove.file"
        host_post_info.post_label_param = "%s, %s" % (virtenv_path, kvm_root)
        run_remote_command(command, host_post_info)
        py_version = None

    if not py_version:
        # name: make sure virtualenv has been setup
        virtenv_flag = "--system-site-packages"
        # virtenv_flag = "" if unittest_flag == 'true' else "--system-site-packages"
        command = "python3.11 -m venv %s %s " % (virtenv_path, virtenv_flag)
        host_post_info.post_label = "ansible.shell.check.virtualenv"
        host_post_info.post_label_param = None
        run_remote_command(command, host_post_info)


def link_gpu_tools():
    for source_path in GPU_TOOL_PATHS:
        command = build_gpu_tool_link_command(virtenv_path, source_path)
        host_post_info.post_label = "ansible.shell.link.%s" % os.path.basename(source_path)
        host_post_info.post_label_param = None
        run_remote_command(command, host_post_info)


def install_agent_pkg():
    """install zstacklib and kvmagent on host"""

    if copy_zstacklib_status != "changed:False":
        agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
        agent_install_arg.agent_name = "zstacklib"
        agent_install_arg.agent_root = kvm_root
        agent_install_arg.pkg_name = pkg_zstacklib
        agent_install_arg.virtualenv_site_packages = "yes"
        agent_install(agent_install_arg, host_post_info)

    if copy_kvmagent_status != "changed:False":
        agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
        agent_install_arg.agent_name = "kvm agent"
        agent_install_arg.agent_root = kvm_root
        agent_install_arg.pkg_name = pkg_kvmagent
        agent_install_arg.virtualenv_site_packages = "yes"
        agent_install(agent_install_arg, host_post_info)

def copy_i40e_driver():
    """copy intel i40e ethernet dirver"""

    IS_X86_64 = host_info.host_arch == 'x86_64'
    if IS_X86_64:
        _src = os.path.join(file_root, "i40e_driver.tar.gz")
        _dst = "/var/lib/zstack/i40e_driver.tar.gz"
        copy_to_remote(_src, _dst, None, host_post_info)


def copy_ovs_tools():
    """copy ovs tools"""

    if host_info.host_arch != 'x86_64':
        return

    zs_network_path = os.path.join(zstack_lib_dir, "network")
    ovs_path = os.path.join(zs_network_path, "ovs-tools")

    command = "rm -rf %s; mkdir -p %s" % (ovs_path, zs_network_path)
    run_remote_command(command, host_post_info)

    _src = os.path.join(file_root, "ovs-tools.tar.gz")
    _dst = os.path.join(zs_network_path, "ovs-tools.tar.gz")
    copy_to_remote(_src, _dst, None, host_post_info)

    command = "tar -xzf %s -C %s/" % (_dst, zs_network_path)
    run_remote_command(command, host_post_info)


def copy_juicefs():
    """copy juicefs binary for Model Center storage mounting (ZSTAC-83157)"""
    if host_info.host_arch == 'aarch64':
        juicefs_binary = "juicefs-arm64"
    else:
        juicefs_binary = "juicefs-amd64"

    _src = os.path.join(file_root, juicefs_binary)
    if not os.path.exists(_src):
        handle_ansible_info("juicefs binary [%s] not found, skip copying" % _src, host_post_info, "WARNING")
        return

    _dst = "/usr/local/bin/juicefs"
    copy_to_remote(_src, _dst, "mode=755", host_post_info)

    command = "mkdir -p /var/cache/virtiofs/juicefs"
    host_post_info.post_label = "ansible.shell.juicefs.cache"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)

    handle_ansible_info("Successfully copied juicefs binary to %s" % _dst, host_post_info, "INFO")


def set_legacy_iptables_ebtables():
    """set legacy mode if needed; on alinux4 deploy ebtables wrapper for --logical-in compatibility."""
    if releasever == "alinux4" and host_info.distro in RPM_BASED_OS:
        # alinux4 has no ebtables-legacy; deploy wrapper that translates --logical-in to -i
        # and keep save/restore followers available for kvmagent rule checks.
        wrapper = (
            '#!/bin/bash\n'
            'args=()\n'
            'for arg in "$@"; do\n'
            '    case "$arg" in\n'
            '        --logical-in)  args+=("-i") ;;\n'
            '        --logical-out) args+=("-o") ;;\n'
            '        *)             args+=("$arg") ;;\n'
            '    esac\n'
            'done\n'
            'exec /usr/sbin/ebtables-nft "${args[@]}"\n'
        )
        command = (
            "printf '%%s' '%s' > /usr/local/sbin/ebtables-wrapper && "
            "chmod +x /usr/local/sbin/ebtables-wrapper && "
            "alternatives --install /usr/sbin/ebtables ebtables /usr/local/sbin/ebtables-wrapper 200 "
            "--slave /usr/sbin/ebtables-save ebtables-save /usr/sbin/ebtables-nft-save "
            "--slave /usr/sbin/ebtables-restore ebtables-restore /usr/sbin/ebtables-nft-restore || true"
        ) % wrapper
        host_post_info.post_label = "ansible.shell.switch.legacy-version"
        host_post_info.post_label_param = None
        run_remote_command(command, host_post_info)
    elif host_info.distro in DEB_BASED_OS and host_info.distro != 'kylin4.0.2':
        command = "update-alternatives --set iptables /usr/sbin/iptables-legacy;" \
                  "update-alternatives --set ebtables /usr/sbin/ebtables-legacy"
        host_post_info.post_label = "ansible.shell.switch.legacy-version"
        host_post_info.post_label_param = None
        run_remote_command(command, host_post_info)


def create_ovmf_symlinks():
    if releasever != "alinux4":
        return
    # edk2.git-ovmf-x64 is x86 firmware; aarch64 alinux4 uses edk2-aarch64 instead
    if host_info.host_arch != 'x86_64':
        return
    command = (
        "yum install -y --disablerepo='*' --enablerepo='zstack-local,zstack-mn' edk2.git-ovmf-x64 && "
        "cd /usr/share/edk2.git/ovmf-x64 && "
        "ln -sf OVMF_CODE-need-smm.fd OVMF_CODE-with-secboot.fd && "
        "ln -sf OVMF_VARS-need-smm.fd OVMF_VARS-with-secboot.fd"
    )
    host_post_info.post_label = "ansible.shell.install-edk2-git-ovmf"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)


def do_ksm_config():
    if isEnableKsm == 'none':
        return

    oprator = "1" if isEnableKsm == 'true' else "0"
    command = "echo %s > /sys/kernel/mm/ksm/run" % oprator
    host_post_info.post_label = "ansible.shell.host-ksm"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)


def _memory_supported_host():
    # get_host_releasever can fall back to the MN release. Use the Host's
    # actual ansible facts here; installation is not native ABI certification.
    facts = ' '.join(getattr(host_info, 'ansible_distribution', '').lower().split())
    return host_info.host_arch == 'x86_64' and facts in (
        'helix green obsidian 8.4r', 'helix green obsidian 8.4',
        'alibaba cloud linux pro edition 4', 'alibaba openanolis edition 4')


def _memory_optimization_rpm_input():
    """Validate the service RPM declaration before any Host repository install."""
    source = memory_optimization_bundle
    if not os.path.isdir(source):
        source = os.path.join(os.path.dirname(__file__), 'files', 'kvm',
                              'memory-optimization', 'zstack-zram')
    inventory_path = os.path.join(source, 'rpm-inventory.json')
    if not os.path.isdir(source):
        raise RuntimeError('MEMORY_OPTIMIZATION_RPM_MISSING:%s' % source)
    if os.path.islink(source) or os.path.islink(inventory_path) or not os.path.isfile(inventory_path):
        raise RuntimeError('MEMORY_OPTIMIZATION_RPM_INVENTORY_INVALID')
    try:
        with open(inventory_path) as stream:
            inventory = json.load(stream)
        build_manifest_path = os.path.join(source, 'BUILD-MANIFEST.json')
        if os.path.islink(build_manifest_path) or not os.path.isfile(build_manifest_path):
            raise ValueError('BUILD_MANIFEST_MISSING_OR_SYMLINK')
        with open(build_manifest_path) as stream:
            build_manifest = json.load(stream)
        package = inventory['package']
        source_pin = inventory['source']
        filename = package['filename']
        if (inventory.get('schemaVersion') != 3 or
                inventory.get('trustModel') != 'content-hash-pinned-not-signed' or
                package.get('name') != 'zstack-zram' or
                package.get('architecture') != 'x86_64' or
                not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', package.get('version', '')) or
                not re.fullmatch(r'[A-Za-z0-9._+~-]+', package.get('release', '')) or
                inventory.get('kernelOrModuleIncluded') is not False or
                inventory.get('configNoreplace') is not True or
                inventory.get('scriptletsEmpty') is not True or
                inventory.get('requiredFiles') != sorted([
                    '/etc/zram-memory/config.json',
                    '/usr/lib/systemd/system/zram-memory.service',
                    '/usr/local/libexec/zram-efficiency',
                    '/usr/local/bin/zram-efficiencyctl',
                    '/usr/local/libexec/zstack-zram/zramctl',
                    '/usr/local/libexec/zstack-zram/bootstrap-config',
                    '/usr/local/libexec/zstack/memory-optimization-bundle/bin/load-zram-module',
                    '/usr/local/libexec/zstack/memory-optimization-bundle/bin/check-qualification',
                    '/usr/share/zstack-zram/config.json']) or
                not re.fullmatch(r'zstack-zram-[0-9][A-Za-z0-9._+~-]*\.rpm', filename) or
                not re.fullmatch(r'[0-9a-f]{64}', package.get('sha256', '')) or
                not isinstance(package.get('bytes'), int) or package['bytes'] <= 0 or
                not re.fullmatch(r'[0-9a-f]{40}', source_pin.get('sourceRevision', '')) or
                not re.fullmatch(r'[0-9a-f]{64}', source_pin.get('dirtyPatchSha256', '')) or
                not re.fullmatch(r'[0-9a-f]{64}', source_pin.get('sourceSnapshotSha256', '')) or
                not re.fullmatch(r'[0-9a-f]{64}', source_pin.get('buildManifestSha256', '')) or
                not re.fullmatch(r'[0-9a-f]{64}', inventory.get('systemdUnitSha256', ''))):
            raise ValueError('RPM_INVENTORY_INVALID')
        installer = inventory.get('installer')
        if (not isinstance(installer, dict) or
                installer.get('filename') != 'install_memory_optimization_rpm.py' or
                not isinstance(installer.get('bytes'), int) or installer['bytes'] <= 0 or
                not re.fullmatch(r'[0-9a-f]{64}', installer.get('sha256', ''))):
            raise ValueError('RPM_INSTALLER_INVENTORY_INVALID')
        runtime_binaries = inventory.get('runtimeBinaries')
        required_runtime_binaries = {
            '/usr/local/libexec/zram-efficiency',
            '/usr/local/bin/zram-efficiencyctl',
        }
        if (not isinstance(runtime_binaries, dict) or
                set(runtime_binaries) != required_runtime_binaries or
                any(not isinstance(item, dict) or
                    not isinstance(item.get('bytes'), int) or item['bytes'] <= 0 or
                    not re.fullmatch(r'[0-9a-f]{64}', item.get('sha256', ''))
                    for item in runtime_binaries.values())):
            raise ValueError('RPM_RUNTIME_BINARY_INVENTORY_INVALID')
        rpm_files = inventory.get('rpmFiles')
        rpm_files_sha = inventory.get('rpmFilesSha256')
        if (not isinstance(rpm_files, list) or not rpm_files or
                any(not isinstance(path, str) or not path.startswith('/') or
                    '\n' in path or '\r' in path or '/..' in path.split('/')
                    for path in rpm_files) or
                rpm_files != sorted(set(rpm_files)) or
                not set(inventory['requiredFiles']).issubset(set(rpm_files)) or
                not required_runtime_binaries.issubset(set(rpm_files)) or
                not re.fullmatch(r'[0-9a-f]{64}', rpm_files_sha or '') or
                hashlib.sha256((''.join(path + '\n' for path in rpm_files)).encode()).hexdigest() != rpm_files_sha):
            raise ValueError('RPM_FILE_INVENTORY_INVALID')
        profiles = inventory.get('supportedHostProfiles')
        if not isinstance(profiles, list) or not profiles or len(set(profiles)) != len(profiles):
            raise ValueError('RPM_HOST_PROFILE_INVENTORY_INVALID')
        if any(not isinstance(item, str) or
               not re.fullmatch(r'[a-z0-9][a-z0-9._-]*', item) for item in profiles):
            raise ValueError('RPM_HOST_PROFILE_INVENTORY_INVALID')
        with open(build_manifest_path, 'rb') as stream:
            build_manifest_sha = hashlib.sha256(stream.read()).hexdigest()
        if (build_manifest_sha != source_pin['buildManifestSha256'] or
                build_manifest.get('schemaVersion') != 1 or
                build_manifest.get('package') != 'zstack-zram' or
                build_manifest.get('rpmVersion') != package['version'] or
                not (build_manifest.get('rpmRelease') == package['release'] or
                     package['release'].startswith(build_manifest.get('rpmRelease', '') + '.')) or
                build_manifest.get('sourceRevision') != source_pin['sourceRevision'] or
                build_manifest.get('sourceSnapshotSha256') != source_pin['sourceSnapshotSha256'] or
                build_manifest.get('dirtyPatchSha256') != source_pin['dirtyPatchSha256']):
            raise ValueError('BUILD_MANIFEST_PIN_MISMATCH')
        unit_records = [item for item in build_manifest.get('sourceFiles', [])
                        if item.get('path') == 'service/packaging/systemd/zram-memory.service']
        if len(unit_records) != 1 or unit_records[0].get('sha256') != inventory['systemdUnitSha256']:
            raise ValueError('RPM_UNIT_SOURCE_PIN_MISMATCH')
        profile = releasever
        if (host_info.host_arch != package['architecture'] or
                not _memory_supported_host() or profile not in profiles):
            raise ValueError('RPM_HOST_ABI_PROFILE_UNSUPPORTED:%s:%s' %
                             (getattr(host_info, 'host_arch', ''), profile))
        installer_path = os.path.join(source, installer['filename'])
        if os.path.islink(installer_path) or not os.path.isfile(installer_path):
            raise ValueError('RPM_INSTALLER_MISSING_OR_SYMLINK')
        if os.path.getsize(installer_path) != installer['bytes']:
            raise ValueError('RPM_INSTALLER_SIZE_MISMATCH')
        installer_digest = hashlib.sha256()
        with open(installer_path, 'rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                installer_digest.update(block)
        if installer_digest.hexdigest() != installer['sha256']:
            raise ValueError('RPM_INSTALLER_SHA256_MISMATCH')
        if filename != '%s-%s-%s.%s.rpm' % (package['name'], package['version'],
                                           package['release'], package['architecture']):
            raise ValueError('RPM_FILENAME_IDENTITY_MISMATCH')
        with open(inventory_path, 'rb') as stream:
            inventory_sha = hashlib.sha256(stream.read()).hexdigest()
        return {'source': source, 'inventory_path': inventory_path,
                'inventory': inventory,
                'inventory_sha256': inventory_sha,
                'installer_path': installer_path}
    except (IOError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RuntimeError('MEMORY_OPTIMIZATION_RPM_INVALID:%s' % exc)


def _install_memory_optimization_rpm(rpm_input):
    package = rpm_input['inventory']['package']
    if package['name'] in re.split(r'[|;,\s]\s*', skip_packages):
        return None
    # Do not require the Agent's zstack-owned directory to be root-owned.
    # Allocate a fresh private directory under the existing system temp root.
    prepare_command = (
        'set -eu; test -d /var/tmp && test ! -L /var/tmp; '
        'test "$(stat -c %u /var/tmp)" = 0; '
        'base_mode=$(stat -c %a /var/tmp); '
        '[ $((0$base_mode & 022)) -eq 0 ] || [ $((0$base_mode & 01000)) -ne 0 ]; '
        'umask 077; stage_dir=$(mktemp -d /var/tmp/zstack-zram.XXXXXXXX); '
        'test -d "$stage_dir" && test ! -L "$stage_dir"; '
        'test "$(stat -c %u "$stage_dir")" = 0; '
        'test "$(stat -c %a "$stage_dir")" = 700; printf "%s\\n" "$stage_dir"')
    ready, output = run_remote_command(prepare_command, host_post_info,
                                        return_status=True, return_output=True)
    deploy_dir = (output or '').strip()
    if not ready or not re.fullmatch(r'/var/tmp/zstack-zram\.[A-Za-z0-9]{8}', deploy_dir):
        return 'remote RPM staging directory validation failed'
    package_path = '%s/%s' % (deploy_dir, package['filename'])
    inventory_path = package_path + '.inventory.json'
    installer_path = deploy_dir + '/install_memory_optimization_rpm.py'
    dir_guard = ('check_root_dir() { test -d "$1" && test ! -L "$1" || return 1; '
                 'owner=$(stat -c %%u "$1") || return 1; '
                 'mode=$(stat -c %%a "$1") || return 1; '
                 'test "$owner" = 0 && test $((0$mode & 022)) -eq 0; }; '
                 'check_root_dir %s || exit 1' % shlex.quote(deploy_dir))
    copy_to_remote(rpm_input['inventory_path'], inventory_path, 'mode=0600', host_post_info)
    copy_to_remote(rpm_input['installer_path'], installer_path, 'mode=0700', host_post_info)
    rpm_file = shlex.quote(package_path)
    inventory_file = shlex.quote(inventory_path)
    installer_file = shlex.quote(installer_path)
    python = shlex.quote(os.path.join(virtenv_path, 'bin', 'python'))
    repo_options = ''
    if zstack_repo != 'false':
        repo_options = '--disablerepo="*" --enablerepo=%s ' % shlex.quote(zstack_repo.strip('"'))
    package_spec = '%s-%s-%s.%s' % (package['name'], package['version'],
                                    package['release'], package['architecture'])
    # Download, rather than install --downloadonly: a same-version reconnect
    # must still obtain and verify the RPM even if it is already installed.
    download = (
        'if ! dnf download --help >/dev/null 2>&1; then '
        'yum -y %s--exclude="kernel*" --setopt=install_weak_deps=False '
        'install dnf-plugins-core; fi; '
        'dnf -y --refresh %sdownload --arch=x86_64 --downloaddir=%s %s' %
        (repo_options, repo_options, shlex.quote(deploy_dir), shlex.quote(package_spec)))
    required_checks = ["printf '%%s\\n' \"$rpm_files\" | grep -Fxq %s || exit 1" %
                       shlex.quote(relative)
                       for relative in rpm_input['inventory']['requiredFiles']]
    required_checks.extend([
        'test "$(printf \'%%s\\n\' "$rpm_files" | LC_ALL=C sort | sha256sum | cut -d\' \' -f1)" = %s || exit 1' %
        shlex.quote(rpm_input['inventory']['rpmFilesSha256']),
        "if printf '%s\\n' \"$rpm_files\" | grep -Eq '\\.ko$|/lib/modules/'; then exit 1; "
        'else grep_status=$?; [ "$grep_status" -eq 1 ] || exit "$grep_status"; fi',
        # This fragment is inserted as a %s value below, not formatted again.
        'rpm_file_flags=$(rpm -qp --qf "[%{FILENAMES} %{FILEFLAGS:fflags}\\n]" "$rpm_file") || exit 1; '
        'printf "%s\\n" "$rpm_file_flags" | grep -Fxq \'/etc/zram-memory/config.json cn\' || exit 1',
    ])
    command = (
        'set -eu; %s; test ! -L %s || exit 1; test ! -L %s || exit 1; '
        'test ! -L %s || exit 1; '
        'test "$(stat -c %%a %s)" = 700; '
        'deploy_dir=%s; rpm_file=%s; inventory_file=%s; installer_file=%s; '
        'trap \'rm -f -- "$rpm_file" "$inventory_file" "$installer_file"; '
        'rmdir -- "$deploy_dir" 2>/dev/null || :\' EXIT; '
        '%s; test -f "$rpm_file" && test ! -L "$rpm_file"; '
        'printf "%%s  %%s\\n" %s "$rpm_file" | sha256sum -c - >/dev/null; '
        'printf "%%s  %%s\\n" %s "$inventory_file" | sha256sum -c - >/dev/null; '
        'host_arch=$(uname -m) || exit 1; test "$host_arch" = x86_64; '
        'rpm_arch_eval=$(rpm --eval %%{_arch}) || exit 1; test "$rpm_arch_eval" = x86_64; '
        'rpm_name=$(rpm -qp --qf %%{NAME} \"$rpm_file\") || exit 1; test "$rpm_name" = zstack-zram; '
        'rpm_version=$(rpm -qp --qf %%{VERSION} \"$rpm_file\") || exit 1; test "$rpm_version" = %s; '
        'rpm_release=$(rpm -qp --qf %%{RELEASE} \"$rpm_file\") || exit 1; test "$rpm_release" = %s; '
        'rpm_arch=$(rpm -qp --qf %%{ARCH} \"$rpm_file\") || exit 1; test "$rpm_arch" = x86_64; '
        'rpm_scripts=$(rpm -qp --scripts \"$rpm_file\") || exit 1; test -z "$rpm_scripts"; '
        'rpm_files=$(rpm -qpl \"$rpm_file\") || exit 1; %s; '
        'if [ -e /etc/zram-memory/config.json ] || [ -L /etc/zram-memory/config.json ]; then '
        '[ -f /etc/zram-memory/config.json ] && [ ! -L /etc/zram-memory/config.json ] || exit 1; fi; '
        'if [ -e /etc/systemd/system/zram-memory.service ] || [ -L /etc/systemd/system/zram-memory.service ]; then '
        '[ -f /etc/systemd/system/zram-memory.service ] && [ ! -L /etc/systemd/system/zram-memory.service ] || exit 1; fi; '
        'printf "%%s  %%s\\n" %s "$installer_file" | sha256sum -c - >/dev/null; '
        '%s "$installer_file" --inventory "$inventory_file" --rpm "$rpm_file" 2>&1' %
        (dir_guard, shlex.quote(package_path), shlex.quote(inventory_path),
         shlex.quote(installer_path), shlex.quote(deploy_dir),
         shlex.quote(deploy_dir), rpm_file, inventory_file, installer_file, download,
         package['sha256'], rpm_input['inventory_sha256'],
         package['version'], package['release'], '; '.join(required_checks),
         rpm_input['inventory']['installer']['sha256'], python)
    )
    status, output = run_remote_command(command, host_post_info,
                                        return_status=True, return_output=True)
    if not status:
        return 'RPM installer rejected package: %s' % (output or 'no installer details returned')
    return None


memory_optimization_warnings = []


def _memory_optimization_warning(message):
    """Memory optimization is optional: warn and keep deploying, then summarize what is unavailable."""
    memory_optimization_warnings.append(message)
    handle_ansible_info(message, host_post_info, 'WARNING')


def check_alinux_zram_driver():
    """Install the repo kmod that owns the running kernel's exact module path.

    This is an optional-feature check, not permission to disconnect a Host or
    replace a loaded module. Agent discovery rechecks the same running facts.
    """
    if releasever != 'alinux4' or not _memory_supported_host():
        return
    python = shlex.quote(os.path.join(virtenv_path, 'bin', 'python'))
    command = python + ' -m zstacklib.utils.zram_driver'
    status, output = run_remote_command('uname -r', host_post_info,
                                        return_status=True, return_output=True)
    if isinstance(output, bytes):
        output = output.decode('utf-8', 'replace')
    kernel = output.strip() if status and isinstance(output, str) else ''
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,254}', kernel):
        _memory_optimization_warning('ZRAM driver cannot identify the running kernel')
        return
    repo_options = ''
    if zstack_repo and zstack_repo != 'false':
        selected_repo = zstack_repo.strip('"')
        if not selected_repo or re.search(r'[\r\n]', selected_repo):
            _memory_optimization_warning('ZRAM driver repository configuration is invalid')
            return
        repo_options = '--disablerepo="*" --enablerepo=%s ' % shlex.quote(selected_repo)
    module_path = '/lib/modules/%s/updates/zstack-zram/zram.ko' % kernel
    query = ('yum -q %srepoquery --available --arch=x86_64 --file %s --qf %s' %
             (repo_options, shlex.quote(module_path),
              shlex.quote('%{name}\\t%{epoch}\\t%{version}\\t%{release}\\t%{arch}')))
    query_status, query_output = run_remote_command(
        query, host_post_info, return_status=True, return_output=True)
    if isinstance(query_output, bytes):
        query_output = query_output.decode('utf-8', 'replace')
    try:
        if not query_status:
            raise ValueError('ZRAM_DRIVER_REPOQUERY_FAILED')
        candidates = set()
        for line in query_output.splitlines():
            # The remote yum wrapper echoes the release name before the query result.
            if '\t' not in line:
                continue
            fields = line.split('\t')
            if len(fields) != 5:
                raise ValueError('ZRAM_DRIVER_REPOQUERY_OUTPUT_INVALID')
            name, epoch, version, package_release, arch = fields
            if name != 'kmod-zstack-zram' or arch != 'x86_64':
                continue
            epoch = '0' if epoch in ('', '(none)') else epoch
            if (not epoch.isdigit() or
                    not re.fullmatch(r'[A-Za-z0-9._+~^%-]+', version) or
                    not re.fullmatch(r'[A-Za-z0-9._+~^%-]+', package_release)):
                raise ValueError('ZRAM_DRIVER_REPOQUERY_OUTPUT_INVALID')
            candidates.add('%s-%s:%s-%s.%s' %
                           (name, epoch, version, package_release, arch))
        if not candidates:
            raise ValueError('ZRAM_DRIVER_PACKAGE_NOT_FOUND')
        if len(candidates) != 1:
            raise ValueError('ZRAM_DRIVER_PACKAGE_AMBIGUOUS')
        package = next(iter(candidates))
        if not re.fullmatch(r'kmod-zstack-zram-[0-9]+:[A-Za-z0-9._+~^%-]+-[A-Za-z0-9._+~^%-]+\.x86_64', package):
            raise ValueError('ZRAM_DRIVER_PACKAGE_IDENTITY_INVALID')
        requires_command = ('yum -q %srepoquery --requires %s' %
                            (repo_options, shlex.quote(package)))
        requires_status, requires_output = run_remote_command(
            requires_command, host_post_info, return_status=True, return_output=True)
        if isinstance(requires_output, bytes):
            requires_output = requires_output.decode('utf-8', 'replace')
        if not requires_status or not isinstance(requires_output, str):
            raise ValueError('ZRAM_DRIVER_REQUIREMENTS_UNAVAILABLE')
        kernel_requirements = re.findall(
            r'^kernel\(x86-64\)\s*=\s*([^\s]+)\s*$',
            requires_output, re.MULTILINE)
        if len(kernel_requirements) != 1:
            raise ValueError('ZRAM_DRIVER_KERNEL_REQUIREMENT_MISSING_OR_AMBIGUOUS')
        boot_image = shlex.quote('/boot/vmlinuz-%s' % kernel)
        owner_query = '%{EPOCH}\\t%{VERSION}-%{RELEASE}\\t%{ARCH}'
        owner_command = ('rpm -qf --qf %s -- %s' %
                         (shlex.quote(owner_query), boot_image))
        owner_status, owner_output = run_remote_command(
            owner_command, host_post_info, return_status=True, return_output=True)
        if isinstance(owner_output, bytes):
            owner_output = owner_output.decode('utf-8', 'replace')
        if not owner_status or not isinstance(owner_output, str):
            raise ValueError('ZRAM_DRIVER_KERNEL_OWNER_UNAVAILABLE')
        owner_fields = owner_output.strip().split('\t')
        if len(owner_fields) != 3:
            raise ValueError('ZRAM_DRIVER_KERNEL_OWNER_UNAVAILABLE')
        owner_epoch, owner_version_release, owner_arch = owner_fields
        owner_epoch = '0' if owner_epoch in ('', '(none)') else owner_epoch
        if (not owner_epoch.isdigit() or owner_arch != 'x86_64' or
                not re.fullmatch(r'[A-Za-z0-9._+~^%-]+', owner_version_release)):
            raise ValueError('ZRAM_DRIVER_KERNEL_OWNER_UNAVAILABLE')
        owner_evr = ('%s:%s' % (owner_epoch, owner_version_release)
                     if owner_epoch != '0' else owner_version_release)
        required_evr = kernel_requirements[0]
        if required_evr.startswith('0:'):
            required_evr = required_evr[2:]
        if owner_evr != required_evr:
            raise ValueError('ZRAM_DRIVER_KERNEL_REQUIREMENT_MISMATCH')
        provider_command = 'rpm -q --whatprovides %s --provides' % shlex.quote(
            'kernel(x86-64)')
        provider_status, provider_output = run_remote_command(
            provider_command, host_post_info, return_status=True, return_output=True)
        if isinstance(provider_output, bytes):
            provider_output = provider_output.decode('utf-8', 'replace')
        if (not provider_status or not isinstance(provider_output, str) or
                not provider_output.strip()):
            raise ValueError('ZRAM_DRIVER_KERNEL_PROVIDER_UNAVAILABLE')
        provider_versions = re.findall(
            r'^kernel\(x86-64\)\s*=\s*([^\s]+)\s*$',
            provider_output, re.MULTILINE)
        provider_versions = [value[2:] if value.startswith('0:') else value
                             for value in provider_versions]
        if required_evr not in provider_versions:
            raise ValueError('ZRAM_DRIVER_KERNEL_PROVIDER_MISMATCH')
        install = ('yum -y %s--exclude="kernel*" --setopt=install_weak_deps=False install %s' %
                   (repo_options, shlex.quote(package)))
    except ValueError as exc:
        _memory_optimization_warning('ZRAM driver package is unavailable for the running kernel: %s' % exc)
        return
    try:
        if not run_remote_command(install, host_post_info, return_status=True):
            _memory_optimization_warning('ZRAM driver exact package unavailable; KSM remains independent')
    except Exception as exc:
        _memory_optimization_warning('ZRAM driver installation failed; KSM remains independent: %s' % exc)
    status, output = run_remote_command(command, host_post_info,
                                        return_status=True, return_output=True)
    try:
        if isinstance(output, bytes):
            output = output.decode('utf-8', 'replace')
        report = json.loads(output) if status else {}
        if report.get('supported') is not True:
            # Only controlled reason/version fields, never arbitrary output.
            reason = report.get('reasonCode', 'ZRAM_DRIVER_OBSERVATION_FAILED')
            if not isinstance(reason, str) or not re.fullmatch(r'[A-Z_]+', reason):
                reason = 'ZRAM_DRIVER_OBSERVATION_FAILED'
            _memory_optimization_warning('ZRAM driver is not active/qualified: %s; no module was unloaded' % reason)
    except (ValueError, TypeError, AttributeError):
        _memory_optimization_warning('ZRAM driver observation failed; capability remains unavailable')


def install_memory_optimization_materials():
    """Validate the distro KSM package and install ZRAM materials if selected."""
    if not _memory_supported_host():
        return
    ksm_ready = run_remote_command(
        'set -eu; test "$(getconf PAGE_SIZE 2>/dev/null || echo 0)" = 4096; '
        'test -r /sys/kernel/mm/ksm/run; '
        'test -r /sys/kernel/mm/ksm/pages_to_scan; '
        'test -r /sys/kernel/mm/ksm/sleep_millisecs; '
        'test -x /usr/sbin/ksmtuned; test -x /usr/libexec/ksmctl; '
        'test -r /usr/lib/systemd/system/ksm.service; '
        'test -r /usr/lib/systemd/system/ksmtuned.service; '
        'test -f /etc/ksmtuned.conf; '
        'rpm -qf /usr/sbin/ksmtuned /usr/libexec/ksmctl '
        '/usr/lib/systemd/system/ksm.service '
        '/usr/lib/systemd/system/ksmtuned.service >/dev/null',
        host_post_info, return_status=True)
    if not ksm_ready:
        _memory_optimization_warning('native KSM tools unavailable; memory optimization materials skipped')
        return
    try:
        rpm_input = _memory_optimization_rpm_input()
    except RuntimeError as exc:
        _memory_optimization_warning('memory optimization RPM skipped: %s' % exc)
        return
    if rpm_input is None:
        return
    # RPM owns the service binaries, loader, unit, and noreplace config. The
    # package-manager transaction has no scriptlets and does not activate it.
    failure = _install_memory_optimization_rpm(rpm_input)
    if failure:
        _memory_optimization_warning('optional memory optimization RPM deployment did not complete: %s' % failure)


def do_auditd_config():
    """add audit rules for signals"""
    AUDIT_CONF_FILE = '/etc/audit/auditd.conf'
    AUDIT_NUM_LOG = 50
    replace_content(AUDIT_CONF_FILE, "regexp='num_logs = .*' replace='num_logs = %d'" % AUDIT_NUM_LOG, host_post_info)
    command = "systemctl enable auditd; systemctl restart auditd || true; " \
              "auditctl -D -k zstack_log_kill || true; " \
              "auditctl -a always,exit -F arch=b64 -F a1=9 -S kill -k zstack_log_kill || true; " \
              "auditctl -a always,exit -F arch=b64 -F a1=15 -S kill -k zstack_log_kill || true"
    host_post_info.post_label = "ansible.shell.audit.signal"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)

def do_systemd_config():
    systemd_config_file = '/etc/systemd/system.conf'
    command = "sed -i 's/\#\?DefaultTimeoutStartSec.*/DefaultTimeoutStartSec=10s/g' {0}; " \
              "sed -i 's/\#\?DefaultTimeoutStopSec.*/DefaultTimeoutStopSec=10s/g' {0}; " \
              "systemctl daemon-reload".format(systemd_config_file)
    host_post_info.post_label = "ansible.shell.configure.systemd"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)

def start_kvmagent():
    if chroot_env != 'false':
        return

    if init == 'true' or restart_libvirtd == 'true':
        # name: restart libvirtd when init installation to make sure qemu.conf changes
        # or restart libvirtd when restart_libvirtd is true (from control plane settings)
        # take effects
        service_status("libvirtd", "state=restarted enabled=yes", host_post_info)

    # name: restart kvmagent, do not use ansible systemctl due to kvmagent can start by itself, so systemctl will not know
    # the kvm agent status when we want to restart it to use the latest kvm agent code
    if host_info.distro in RPM_BASED_OS and host_info.major_version >= 7:
        # NOTE(weiw): dump threads and wait 1 second for dumping
        command = "pkill -USR2 -P 1 -ef 'kvmagent import kdaemon' || true && sleep 1"
        host_post_info.post_label = "ansible.shell.dump.service"
        host_post_info.post_label_param = "zstack-kvmagent"
        run_remote_command(command, host_post_info)
        command = "service zstack-kvmagent stop && service zstack-kvmagent start && chkconfig zstack-kvmagent on"
    elif host_info.distro in RPM_BASED_OS:
        command = "service zstack-kvmagent stop && service zstack-kvmagent start && chkconfig zstack-kvmagent on"
    elif host_info.distro in DEB_BASED_OS:
        command = "update-rc.d zstack-kvmagent start 97 3 4 5 . stop 3 0 1 2 6 . && service zstack-kvmagent stop && service zstack-kvmagent start"
    host_post_info.post_label = "ansible.shell.restart.service"
    host_post_info.post_label_param = "zstack-kvmagent"
    run_remote_command(command, host_post_info)

def modprobe_usb_module():
    command = "modprobe usb-storage; modprobe uas || true"
    host_post_info.post_label = "ansible.shell.modprobe.usb"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)

@with_arch(todo_list=['loongarch64'], host_arch=host_info.host_arch)
def modprobe_mpci_module():
    command = "ls /dev/wst-se"
    (status, stdout) = run_remote_command(command, host_post_info, return_status=True, return_output=True)
    if "wst-se" not in stdout:
        handle_ansible_info("No SE device", host_post_info, "WARNING")
        return

    (status, stdout) = run_remote_command("lsmod | grep mpci", host_post_info, return_status=True, return_output=True)
    if "mpci" in stdout:
        return
        
    """copy mpci.ko"""
    _src = "{}/mpci_{}".format(file_root, host_info.kernel_version)
    if not os.path.exists(_src):
        handle_ansible_info("There are no suitable SE drivers for this kernel", host_post_info, "WARNING")
        return

    _dst = "/lib/modules/{}/mpci.ko".format(host_info.kernel_version)
    copy_to_remote(_src, _dst, "mode=644", host_post_info)

    command = "depmod -a; modprobe vfio-mdev; modprobe mpci || true"
    host_post_info.post_label = "ansible.shell.modprobe.mpci"
    host_post_info.post_label_param = None
    run_remote_command(command, host_post_info)


def set_gpu_blacklist():
    gpu_name_list = "snd_hda_intel nouveau amdgpu"

    command = "for gpu_name in %s; \
        do cat /etc/modprobe.d/${gpu_name}-blacklist.conf | grep \"install ${gpu_name} /bin/false\" \
        || echo \"install ${gpu_name} /bin/false\" >> /etc/modprobe.d/${gpu_name}-blacklist.conf; done" % gpu_name_list
    run_remote_command(command, host_post_info)


def check_is_remote_cube():
    command = "ls /usr/local/hyperconverged"
    status = run_remote_command(command, host_post_info, return_status=True)
    global isRemoteCube
    isRemoteCube = status


check_is_remote_cube()
check_nested_kvm(host_post_info)
install_kvm_pkg()
copy_tools()
copy_kvm_files()
copy_exporter_tools()
copy_gpudriver()
copy_ovmf_tools()
copy_lsusb_scripts()
copy_zs_scripts()
copy_grubaa64_efi()
copy_bond_conf()
copy_i40e_driver()
copy_cube_tools()
copy_ovs_tools()
copy_juicefs()
create_virtio_driver_directory()
set_max_performance()
do_libvirt_qemu_config()
do_network_config()
configure_host_ipv6()
copy_spice_certificates_to_host()
install_virtualenv()
link_gpu_tools()
set_legacy_iptables_ebtables()
create_ovmf_symlinks()
install_agent_pkg()
do_auditd_config()
do_systemd_config()
# Service RPM adoption may restart the previous controller and invoke its
# module-loading hook. Prepare the exact-ABI disk package before that hook;
# this check itself never replaces a module already loaded in memory.
check_alinux_zram_driver()
install_memory_optimization_materials()
if memory_optimization_warnings:
    handle_ansible_info('memory optimization is unavailable or partial on this host: %s'
                        % '; '.join(memory_optimization_warnings), host_post_info, 'WARNING')
do_ksm_config()
modprobe_usb_module()
modprobe_mpci_module()
set_gpu_blacklist()
start_kvmagent()

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy kvm agent successful", host_post_info, "INFO")

sys.exit(0)
