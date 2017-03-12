#!/usr/bin/env python
# encoding: utf-8
import argparse
from zstacklib import *

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy ceph primary agent")
start_time = datetime.now()
# set default value
file_root = "files/cephp"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
zstack_repo = 'false'
post_url = ""
pkg_cephpagent = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None


# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy ceph primary strorage to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/cephp/" % zstack_root
cephp_root = "%s/cephp/package" % zstack_root
host_post_info = HostPostInfo()
host_post_info.host_inventory = args.i
host_post_info.host = host
host_post_info.post_url = post_url
host_post_info.private_key = args.private_key
host_post_info.remote_user = remote_user
host_post_info.remote_pass = remote_pass
host_post_info.remote_port = remote_port
if remote_pass is not None and remote_user != 'root':
    host_post_info.become = True

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
if file_dir_exist("path=" + cephp_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (cephp_root, virtenv_path)
    run_remote_command(command, host_post_info)

run_remote_command("rm -rf %s/*" % cephp_root, host_post_info)

if distro == "RedHat" or distro == "CentOS":
    if zstack_repo != 'false':
        command = ("pkg_list=`rpm -q wget qemu-img-ev libvirt libguestfs-winsupport libguestfs-tools"
                   " | grep \"not installed\" | awk '{ print $2 }'` && for pkg"
                   " in $pkg_list; do yum --disablerepo=* --enablerepo=%s install -y $pkg; done;") % zstack_repo
        run_remote_command(command, host_post_info)
        if distro_version >= 7:
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            run_remote_command(command, host_post_info)
    else:
        for pkg in ["wget", "qemu-img-ev", "libvirt", "libguestfs-winsupport", "libguestfs-tools"]:
            yum_install_package(pkg, host_post_info)
        if distro_version >= 7:
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            run_remote_command(command, host_post_info)
    set_selinux("state=disabled", host_post_info)
    # name: enable libvirt daemon on RedHat based OS
    service_status("libvirtd", "state=started enabled=yes", host_post_info)
    if distro_version >= 7:
        # name: enable virtlockd daemon on RedHat based OS
        service_status("virtlockd", "state=started enabled=yes", host_post_info)
    # name: copy sysconfig libvirtd conf in RedHat
    copy_arg = CopyArg()
    copy_arg.src = "%s/../kvm/libvirtd" % file_root
    copy_arg.dest = "/etc/sysconfig/libvirtd"
    libvirtd_status = copy(copy_arg, host_post_info)

elif distro == "Debian" or distro == "Ubuntu":
    install_pkg_list = ["wget", "qemu-utils","libvirt-bin", "libguestfs-tools"]
    apt_install_packages(install_pkg_list, host_post_info)
    command = "(chmod 0644 /boot/vmlinuz*) || true"
    run_remote_command(command, host_post_info)
    # name: copy default libvirtd conf in Debian
    copy_arg = CopyArg()
    copy_arg.src = "%s/../kvm/libvirt-bin" % file_root
    copy_arg.dest = '/etc/default/libvirt-bin'
    libvirt_bin_status = copy(copy_arg, host_post_info)
    if libvirt_bin_status != "changed:False":
        # name: restart debian libvirtd
        service_status("libvirt-bin", "state=restarted enabled=yes", host_post_info)
else:
    error("unsupported OS!")

# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, cephp_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)

# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv --system-site-packages %s " % (virtenv_path, virtenv_path)
run_remote_command(command, host_post_info)

# name: copy zstacklib and install
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/%s" % (cephp_root, pkg_zstacklib)
zstack_lib_copy = copy(copy_arg, host_post_info)
if zstack_lib_copy != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zstacklib"
    agent_install_arg.agent_root = cephp_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install(agent_install_arg, host_post_info)

# name: copy ceph primarystorage agent
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_cephpagent)
copy_arg.dest = "%s/%s" % (cephp_root, pkg_cephpagent)
cephpagent_copy = copy(copy_arg, host_post_info)
if cephpagent_copy != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "ceph_primarystorage"
    agent_install_arg.agent_root = cephp_root
    agent_install_arg.pkg_name = pkg_cephpagent
    agent_install(agent_install_arg, host_post_info)

# name: copy service file
# only support centos redhat debian and ubuntu
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-ceph-primarystorage" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)
# name: restart cephpagent
if distro == "RedHat" or distro == "CentOS":
    command = "service zstack-ceph-primarystorage stop && service zstack-ceph-primarystorage start" \
              " && chkconfig zstack-ceph-primarystorage on"
elif distro == "Debian" or distro == "Ubuntu":
    command = "update-rc.d zstack-ceph-primarystorage start 97 3 4 5 . stop 3 0 1 2 6 . && service zstack-ceph-primarystorage stop && service zstack-ceph-primarystorage start"
run_remote_command(command, host_post_info)
# change ceph config
set_ini_file("/etc/ceph/ceph.conf", 'global', "rbd_default_format", "2", host_post_info)

# name: remove libvirt default bridge
command = '(ifconfig virbr0 &> /dev/null && virsh net-destroy default > ' \
          '/dev/null && virsh net-undefine default > /dev/null) || true'
host_post_info.post_label = "ansible.shell.virsh.destroy.bridge"
host_post_info.post_label_param = None
run_remote_command(command, host_post_info)

# name: copy libvirtd conf
copy_arg = CopyArg()
copy_arg.src = "%s/../kvm/libvirtd.conf" % file_root
copy_arg.dest = "/etc/libvirt/libvirtd.conf"
libvirtd_conf_status = copy(copy_arg, host_post_info)

# name: copy qemu conf
copy_arg = CopyArg()
copy_arg.src = "%s/../kvm/qemu.conf" % file_root
copy_arg.dest = "/etc/libvirt/qemu.conf"
qemu_conf_status = copy(copy_arg, host_post_info)

# name: delete A2 qemu hook
command = "rm -f /etc/libvirt/hooks/qemu"
host_post_info.post_label = "ansible.shell.remove.file"
host_post_info.post_label_param = "/etc/libvirt/hooks/qemu"
run_remote_command(command, host_post_info)

# name: restart libvirt
if distro == "RedHat" or distro == "CentOS":
    if libvirtd_status != "changed:False" or libvirtd_conf_status != "changed:False" \
            or qemu_conf_status != "changed:False":
        # name: restart redhat libvirtd
        service_status("libvirtd", "state=restarted enabled=yes", host_post_info)
elif distro == "Debian" or distro == "Ubuntu":
    if libvirt_bin_status != "changed:False" or libvirtd_conf_status != "changed:False" \
            or qemu_conf_status != "changed:False":
        # name: restart debian libvirtd
        service_status("libvirt-bin", "state=restarted enabled=yes", host_post_info)
run_remote_command(command, host_post_info)
# change ceph config
set_ini_file("/etc/ceph/ceph.conf", 'global', "rbd_default_format", "2", host_post_info)



host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy ceph primary agent successful", host_post_info, "INFO")

sys.exit(0)
