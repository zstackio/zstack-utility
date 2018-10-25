#!/usr/bin/env python
# encoding=utf-8
import argparse
from zstacklib import *

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy kvm agent")
start_time = datetime.now()
# set default value
file_root = "files/kvm"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
init = 'false'
zstack_repo = 'false'
chrony_servers = None
post_url = ""
pkg_kvmagent = ""
libvirtd_status = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None
libvirtd_conf_file = "/etc/libvirt/libvirtd.conf"
update_packages = 'false'

def update_libvritd_config(host_post_info):
    command = "grep -i ^host_uuid %s" % libvirtd_conf_file
    status, output = run_remote_command(command, host_post_info, True, True)
    # name: copy libvirtd conf
    copy_arg = CopyArg()
    copy_arg.src = "%s/libvirtd.conf" % file_root
    copy_arg.dest =  libvirtd_conf_file
    file_changed_flag = copy(copy_arg, host_post_info)
    if status is True:
        replace_content(libvirtd_conf_file, "regexp='#host_uuid.*' replace='%s'" % output, host_post_info)
    else:
        command = "uuidgen"
        status, output = run_remote_command(command, host_post_info, True, True)
        replace_content(libvirtd_conf_file, "regexp='#host_uuid.*' replace='host_uuid=\"%s\"'" % output , host_post_info)


    return file_changed_flag


def check_nested_kvm(host_post_info):
    enabled_nested_flag = False
    # enable nested kvm
    command = "cat /sys/module/kvm_intel/parameters/nested"
    (status, stdout) = run_remote_command(command, host_post_info, return_status=True, return_output=True)
    if "Y" in stdout:
        enabled_nested_flag = True
    else:
        command = "mkdir -p /etc/modprobe.d/ && echo 'options kvm_intel nested=1' >  /etc/modprobe.d/kvm-nested.conf"
        run_remote_command(command, host_post_info)

    #add kvm module and tun module
    modprobe_arg = ModProbeArg()
    modprobe_arg.name = 'kvm'
    modprobe_arg.state = 'present'
    modprobe(modprobe_arg, host_post_info)

    modprobe_arg = ModProbeArg()
    if 'intel' in get_remote_host_cpu(host_post_info).lower():
        # reload kvm_intel for enable nested kvm
        if enabled_nested_flag is False:
            command = "modprobe -r kvm_intel"
            run_remote_command(command, host_post_info, return_status=True)
        modprobe_arg.name = 'kvm_intel'
    elif 'amd' in get_remote_host_cpu(host_post_info).lower():
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

host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
host_post_info.post_url = post_url
host_post_info.chrony_servers = chrony_servers
host_post_info.private_key = args.private_key
host_post_info.remote_user = remote_user
host_post_info.remote_pass = remote_pass
host_post_info.remote_port = remote_port
if remote_pass is not None and remote_user != 'root':
    host_post_info.become = True

# get remote host arch
IS_AARCH64 = get_remote_host_arch(host_post_info) == 'aarch64'
if IS_AARCH64:
    dnsmasq_pkg = "%s/dnsmasq-2.76-2.el7.aarch64.rpm" % file_root
    dnsmasq_local_pkg = "%s/dnsmasq-2.76-2.el7.aarch64.rpm" % kvm_root
    collectd_pkg = "%s/collectd_exporter_aarch64" % file_root
    node_collectd_pkg = "%s/node_exporter_aarch64" % file_root
    qemu_img_pkg = "%s/qemu-img-aarch64" % file_root
    qemu_img_local_pkg = "%s/qemu-img-aarch64" % kvm_root
else:
    dnsmasq_pkg = "%s/dnsmasq-2.76-2.el7_4.2.x86_64.rpm" % file_root
    dnsmasq_local_pkg = "%s/dnsmasq-2.76-2.el7_4.2.x86_64.rpm" % kvm_root
    collectd_pkg = "%s/collectd_exporter" % file_root
    node_collectd_pkg = "%s/node_exporter" % file_root
    qemu_img_pkg = "%s/qemu-img-kvm" % file_root
    qemu_img_local_pkg = "%s/qemu-img-kvm" % kvm_root
collectd_local_pkg = "%s/collectd_exporter" % workplace
node_collectd_local_pkg = "%s/node_exporter" % workplace

# include zstacklib.py
(distro, distro_version, distro_release) = get_remote_host_info(host_post_info)
zstacklib_args = ZstackLibArgs()
zstacklib_args.distro = distro
zstacklib_args.distro_release = distro_release
zstacklib_args.distro_version = distro_version
zstacklib_args.zstack_repo = zstack_repo
zstacklib_args.yum_server = yum_server
zstacklib_args.zstack_root = zstack_root
zstacklib_args.host_post_info = host_post_info
zstacklib_args.pip_url = pip_url
zstacklib_args.trusted_host = trusted_host
zstacklib = ZstackLib(zstacklib_args)

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

run_remote_command("rm -rf %s/*" % kvm_root, host_post_info)

# aarch64 does not need to modprobe kvm
if not IS_AARCH64:
    check_nested_kvm(host_post_info)

if distro in RPM_BASED_OS:
    # handle zstack_repo
    if zstack_repo != 'false':
        qemu_pkg = 'qemu-kvm-ev' if distro_version >= 7 else 'qemu-kvm'
        extra_pkg = 'collectd-virt' if distro_version >= 7 else ""
        dep_list = "bridge-utils chrony conntrack-tools device-mapper-multipath dnsmasq edk2.git-ovmf-x64 expect hwdata iproute ipset iputils iscsi-initiator-utils libguestfs-tools libguestfs-winsupport libvirt libvirt-client libvirt-python lighttpd lvm2 lvm2-lockd net-tools nfs-utils nmap openssh-clients OVMF pciutils python-pyudev pv rsync sanlock sysfsutils sed sg3_utils smartmontools sshpass usbutils vconfig wget %s %s" % (qemu_pkg, extra_pkg)

        # name: install kvm related packages on RedHat based OS from user defined repo
        # update some packages if possible
        command = ("echo %s >/var/lib/zstack/dependencies && yum --enablerepo=%s clean metadata >/dev/null && pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'`' sanlock sysfsutils hwdata sg3_utils lvm2 lvm2-libs lvm2-lockd' && for pkg in %s; do yum --disablerepo=* --enablerepo=%s install -y $pkg >/dev/null || exit 1; done;") % (dep_list, zstack_repo, dep_list, dep_list if update_packages == 'true' else '$pkg_list', zstack_repo)
        host_post_info.post_label = "ansible.shell.install.pkg"
        host_post_info.post_label_param = dep_list
        run_remote_command(command, host_post_info)

        if IS_AARCH64:
            # name: aarch64 specific packages from user defined repos
            arm_dep_list = 'AAVMF edk2.git-aarch64'
            command = ("echo %s >>/var/lib/zstack/dependencies && yum --enablerepo=%s clean metadata && "
                       "pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'` && for pkg "
                       "in $pkg_list; do yum --disablerepo=* --enablerepo=%s "
                       "--nogpgcheck install -y $pkg; done;") % (arm_dep_list, zstack_repo, arm_dep_list, zstack_repo)
            host_post_info.post_label = "ansible.shell.install.pkg"
            host_post_info.post_label_param = "AAVMF,edk2.git-aarch64"
            run_remote_command(command, host_post_info)

    else:
        # name: install kvm related packages on RedHat based OS from online
        for pkg in ['openssh-clients', 'bridge-utils', 'wget', 'chrony', 'sed', 'libvirt-python', 'libvirt', 'nfs-utils', 'vconfig',
                    'libvirt-client', 'net-tools', 'iscsi-initiator-utils', 'lighttpd', 'dnsmasq', 'iproute', 'sshpass',
                    'libguestfs-winsupport', 'libguestfs-tools', 'pv', 'rsync', 'nmap', 'ipset', 'usbutils', 'pciutils', 'expect',
                    'lvm2', 'lvm2-lockd', 'sanlock', 'sysfsutils', 'smartmontools', 'device-mapper-multipath', 'hwdata', 'sg3_utils']:
            yum_install_package(pkg, host_post_info)
        if distro_version >= 7:
            # name: RHEL7 specific packages from online
            for pkg in ['qemu-kvm-ev', 'qemu-img-ev', 'collectd-virt']:
                yum_install_package(pkg, host_post_info)
        else:
            for pkg in ['qemu-kvm', 'qemu-img']:
                yum_install_package(pkg, host_post_info)

    # copy prometheus collectd_exporter
    copy_arg = CopyArg()
    copy_arg.src = collectd_pkg
    copy_arg.dest = collectd_local_pkg
    copy(copy_arg, host_post_info)

    # copy prometheus node_exporter
    copy_arg = CopyArg()
    copy_arg.src = node_collectd_pkg
    copy_arg.dest = node_collectd_local_pkg
    copy(copy_arg, host_post_info)

    # handle distro version specific task
    if distro_version < 7:
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
        # name: disable firewalld in RHEL7 and Centos7
        command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
        host_post_info.post_label = "ansible.shell.disable.service"
        host_post_info.post_label_param = "firewalld"
        run_remote_command(command, host_post_info)
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

    # name: copy ip6tables initial rules in RedHat
    IP6TABLE_SERVICE_FILE = '/usr/lib/systemd/system/ip6tables.service'
    copy_arg = CopyArg()
    copy_arg.src = "%s/ip6tables" % file_root
    copy_arg.dest = "/etc/sysconfig/ip6tables"
    copy(copy_arg, host_post_info)
    command = "sed -i 's/syslog.target,iptables.service/syslog.target iptables.service/' %s || true;" % IP6TABLE_SERVICE_FILE
    run_remote_command(command, host_post_info)
    service_status("ip6tables", "state=restarted enabled=yes", host_post_info)

    #we should check libvirtd config file status before restart the service
    libvirtd_conf_status = update_libvritd_config(host_post_info)
    if chroot_env == 'false':
        # name: enable libvirt daemon on RedHat based OS
        service_status("libvirtd", "state=started enabled=yes", host_post_info)
        if distro_version >= 7:
            # name: enable virtlockd daemon on RedHat based OS
            service_status("virtlockd", "state=stopped enabled=no", host_post_info)
            service_status("virtlogd", "state=started enabled=yes", host_post_info, True)

    # name: copy updated dnsmasq for RHEL6 and RHEL7
    copy_arg = CopyArg()
    copy_arg.src = "%s" % dnsmasq_pkg
    copy_arg.dest = "%s" % dnsmasq_local_pkg
    copy(copy_arg, host_post_info)
    # name: Update dnsmasq for RHEL6 and RHEL7
    command = "rpm -q dnsmasq-2.76 || yum install --nogpgcheck -y %s" % dnsmasq_local_pkg
    host_post_info.post_label = "ansible.shell.install.pkg"
    host_post_info.post_label_param = "dnsmasq-2.76"
    run_remote_command(command, host_post_info)
    # name: disable selinux on RedHat based OS
    set_selinux("state=disabled", host_post_info)
    run_remote_command("setenforce 0 || true", host_post_info)
    # name: copy sysconfig libvirtd conf in RedHat
    copy_arg = CopyArg()
    copy_arg.src = "%s/libvirtd" % file_root
    copy_arg.dest = "/etc/sysconfig/libvirtd"
    libvirtd_status = copy(copy_arg, host_post_info)

    # replace qemu-img binary
    command = "qemu-img --version | grep 'qemu-img version' | cut -d ' ' -f 3 | cut -d '(' -f 1"
    qemu_img_version = run_remote_command(command, host_post_info, False, True)
    if '2.6.0' not in qemu_img_version:
        copy_arg = CopyArg()
        copy_arg.src = "%s" % qemu_img_pkg
        copy_arg.dest = "%s" % qemu_img_local_pkg
        copy(copy_arg, host_post_info)

        command = "for i in {1..5}; do /bin/cp %s `which qemu-img` && break || sleep 2; done" % qemu_img_local_pkg
        host_post_info.post_label = "ansible.shell.install.pkg"
        host_post_info.post_label_param = "qemu-img"
        run_remote_command(command, host_post_info)

elif distro in DEB_BASED_OS:
    # name: install kvm related packages on Debian based OS
    install_pkg_list = ['qemu-kvm', 'bridge-utils', 'wget', 'qemu-utils', 'python-libvirt', 'libvirt-bin', 'chrony'
                        'vlan', 'libguestfs-tools', 'sed', 'nfs-common', 'open-iscsi','pv', 'usbutils', 'pciutils', 'expect',
                        'lighttpd', 'dnsmasq', 'sshpass', 'rsync', 'iputils-arping', 'nmap', 'collectd']
    apt_install_packages(install_pkg_list, host_post_info)
    # name: copy default libvirtd conf in Debian
    copy_arg = CopyArg()
    copy_arg.src = "%s/libvirt-bin" % file_root
    copy_arg.dest = '/etc/default/libvirt-bin'
    libvirt_bin_status = copy(copy_arg, host_post_info)
    # name: enable bridge forward on UBUNTU
    command = "modprobe br_netfilter; echo 1 > /proc/sys/net/bridge/bridge-nf-call-iptables ; " \
              "echo 1 > /proc/sys/net/ipv4/conf/default/forwarding"
    host_post_info.post_label = "ansible.shell.enable.module"
    host_post_info.post_label_param = "br_netfilter"
    run_remote_command(command, host_post_info)

else:
    error("unsupported OS!")


#set max performance 
# AliOS 7u2 does not support tuned-adm
if distro in RPM_BASED_OS and distro != "Alibaba":
    command = "tuned-adm profile virtual-host; echo virtual-host > /etc/tuned/active_profile"
    host_post_info.post_label = "ansible.shell.set.tuned.profile"
    host_post_info.post_label_param = "set profile as virtual-host"
    run_remote_command(command, host_post_info)

# name: remove libvirt default bridge
command = '(ifconfig virbr0 &> /dev/null && virsh net-destroy default > ' \
          '/dev/null && virsh net-undefine default > /dev/null) || true'
host_post_info.post_label = "ansible.shell.virsh.destroy.bridge"
host_post_info.post_label_param = None
run_remote_command(command, host_post_info)


# name: copy qemu conf
copy_arg = CopyArg()
copy_arg.src = "%s/qemu.conf" % file_root
copy_arg.dest = "/etc/libvirt/qemu.conf"
qemu_conf_status = copy(copy_arg, host_post_info)

# name: delete A2 qemu hook
command = "rm -f /etc/libvirt/hooks/qemu"
host_post_info.post_label = "ansible.shell.remove.file"
host_post_info.post_label_param = "/etc/libvirt/hooks/qemu"
run_remote_command(command, host_post_info)

# name: enable bridge forward
command = "echo 1 > /proc/sys/net/bridge/bridge-nf-call-iptables ; echo 1 > /proc/sys/net/ipv4/conf/default/forwarding ; echo 1 > /proc/sys/net/bridge/bridge-nf-call-ip6tables ; echo 1 > /proc/sys/net/ipv6/conf/default/forwarding"
host_post_info.post_label = "ansible.shell.enable.service"
host_post_info.post_label_param = "bridge forward"
run_remote_command(command, host_post_info)


# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/%s" % (kvm_root, pkg_zstacklib)
copy_zstacklib = copy(copy_arg, host_post_info)

# name: copy kvmagent
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_kvmagent)
copy_arg.dest = "%s/%s" % (kvm_root, pkg_kvmagent)
copy_kvmagent = copy(copy_arg, host_post_info)

# only for os using init.d not systemd
# name: copy kvm service file
copy_arg = CopyArg()
copy_arg.src = "files/kvm/zstack-kvmagent"
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, kvm_root)
    host_post_info.post_label = "ansible.shell.remove.file"
    host_post_info.post_label_param = "%s, %s" % (virtenv_path, kvm_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)
# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv --system-site-packages %s " % (virtenv_path, virtenv_path)
host_post_info.post_label = "ansible.shell.check.virtualenv"
host_post_info.post_label_param = None
run_remote_command(command, host_post_info)

# name: install zstacklib
if copy_zstacklib != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zstacklib"
    agent_install_arg.agent_root = kvm_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install_arg.virtualenv_site_packages = "yes"
    agent_install(agent_install_arg, host_post_info)

# name: install kvm agent
if copy_kvmagent != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "kvm agent"
    agent_install_arg.agent_root = kvm_root
    agent_install_arg.pkg_name = pkg_kvmagent
    agent_install_arg.virtualenv_site_packages = "yes"
    agent_install(agent_install_arg, host_post_info)

# name: add audit rules for signals
AUDIT_CONF_FILE = '/etc/audit/auditd.conf'
AUDIT_NUM_LOG = 50
command = "sed -i 's/num_logs = .*/num_logs = %d/' %s || true;" \
          "systemctl enable auditd; systemctl restart auditd || true; " \
          "auditctl -D -k zstack_log_kill || true; " \
          "auditctl -a always,exit -F arch=b64 -F a1=9 -S kill -k zstack_log_kill || true; " \
          "auditctl -a always,exit -F arch=b64 -F a1=15 -S kill -k zstack_log_kill || true" % (AUDIT_NUM_LOG, AUDIT_CONF_FILE)
host_post_info.post_label = "ansible.shell.audit.signal"
host_post_info.post_label_param = None
run_remote_command(command, host_post_info)

# handlers
if chroot_env == 'false':
    if distro in RPM_BASED_OS:
        if libvirtd_status != "changed:False" or libvirtd_conf_status != "changed:False" \
                or qemu_conf_status != "changed:False":
            # name: restart redhat libvirtd
            service_status("libvirtd", "state=restarted enabled=yes", host_post_info)
    elif distro in DEB_BASED_OS:
        if libvirt_bin_status != "changed:False" or libvirtd_conf_status != "changed:False" or qemu_conf_status != "changed:False":
            # name: restart debian libvirtd
            service_status("libvirt-bin", "state=restarted enabled=yes", host_post_info)
    # name: restart kvmagent, do not use ansible systemctl due to kvmagent can start by itself, so systemctl will not know
    # the kvm agent status when we want to restart it to use the latest kvm agent code
    if distro in RPM_BASED_OS and distro_version >= 7:
        command = "systemctl stop zstack-kvmagent && systemctl start zstack-kvmagent && systemctl enable zstack-kvmagent"
    elif distro in RPM_BASED_OS:
        command = "service zstack-kvmagent stop && service zstack-kvmagent start && chkconfig zstack-kvmagent on"
    elif distro in DEB_BASED_OS:
        command = "update-rc.d zstack-kvmagent start 97 3 4 5 . stop 3 0 1 2 6 . && service zstack-kvmagent stop && service zstack-kvmagent start"
    host_post_info.post_label = "ansible.shell.restart.service"
    host_post_info.post_label_param = "zstack-kvmagent"
    run_remote_command(command, host_post_info)


host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy kvm agent successful", host_post_info, "INFO")

sys.exit(0)
