#!/usr/bin/env python
# encoding: utf-8
import argparse
import datetime
import os

from zstacklib import *

# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy baremetal pxeserver agent")
start_time = datetime.datetime.now()
# set default value
file_root = "files/baremetalpxeserver"
kvm_file_root = "files/kvm"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
zstack_repo = 'false'
post_url = ""
chrony_servers = None
pkg_baremetalpxeserver = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None
baremetalpxeserver_pushgateway_root="/var/lib/zstack/baremetal/"
baremetalpxeserver_pushgateway_persistence="/var/lib/zstack/baremetal/persistence.data"
baremetalpxeserver_pushgateway_port=9093
update_packages = 'false'

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy baremetal pxeserver agent to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/baremetalpxeserver/" % zstack_root
baremetalpxeserver_root = "%s/baremetalpxeserver/package" % zstack_root
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
# include zstacklib.py
host_info = get_remote_host_info_obj(host_post_info)
host_info = upgrade_to_helix(host_info, host_post_info)
releasever = get_host_releasever(host_info)
host_post_info.releasever = releasever

zstacklib_args = ZstackLibArgs()
zstacklib_args.distro = host_info.distro
zstacklib_args.distro_release = host_info.distro_release
zstacklib_args.distro_version = host_info.major_version
zstacklib_args.zstack_repo = zstack_repo
zstacklib_args.zstack_root = zstack_root
zstacklib_args.host_post_info = host_post_info
zstacklib_args.pip_url = pip_url
zstacklib_args.trusted_host = trusted_host
zstacklib_args.zstack_releasever = releasever
if host_info.distro in DEB_BASED_OS:
    zstacklib_args.apt_server = yum_server
    zstacklib_args.zstack_apt_source = zstack_repo
else :
    zstacklib_args.yum_server = yum_server
zstacklib = ZstackLib(zstacklib_args)

# name: judge this process is init install or upgrade
if file_dir_exist("path=" + baremetalpxeserver_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (baremetalpxeserver_root, virtenv_path)
    run_remote_command(command, host_post_info)

# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, baremetalpxeserver_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)

# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv-2.7 --system-site-packages %s " % (virtenv_path, virtenv_path)
run_remote_command(command, host_post_info)

# name: install dependencies
if host_info.distro in RPM_BASED_OS:
    dep_pkg = "dnsmasq nginx nginx-all-modules vsftpd nmap"
    if releasever in centos:
        dep_pkg = "{} syslinux".format(dep_pkg)
    else:
        dep_pkg = "{} net-tools".format(dep_pkg)
    if zstack_repo != 'false':
        command = ("pkg_list=`rpm -q %s | grep \"not installed\" | awk '{ print $2 }'` && for pkg in %s; do yum --disablerepo=* --enablerepo=%s install -y $pkg; done;") % \
                  (dep_pkg, dep_pkg if update_packages == 'true' else '$pkg_list', zstack_repo)
        run_remote_command(command, host_post_info)
    else:
        for pkg in ["dnsmasq", "nginx", "nginx-all-modules", "vsftpd", "syslinux", "nmap"]:
            yum_install_package(pkg, host_post_info)
    command = "(which firewalld && systemctl stop firewalld && systemctl enable firewalld) || true"
    run_remote_command(command, host_post_info)
    set_selinux("state=disabled", host_post_info)

elif host_info.distro in DEB_BASED_OS:
    install_pkg_list = ["dnsmasq", "vsftpd", "syslinux", "nginx", "nmap"]
    apt_install_packages(install_pkg_list, host_post_info)
    command = "(chmod 0644 /boot/vmlinuz*) || true"
else:
    error("unsupported OS!")

# name: check and mount /opt/zstack-dvd
command = """
archRelease="x86_64/c72 x86_64/c74 x86_64/c76 x86_64/c79 x86_64/h76c x86_64/h79c x86_64/h84r \
x86_64/ky10sp1 x86_64/ky10sp2 x86_64/ky10sp3 aarch64/ky10sp1 aarch64/ky10sp2 \
aarch64/ky10sp3 aarch64/oe2203sp1 aarch64/h2203sp1o mips64el/ky10sp1 loongarch64/ky10sp1 loongarch64/ky10sp3"

mkdir -p /var/lib/zstack/baremetal/{dnsmasq,ftp/{ks,zstack-dvd/{x86_64,aarch64,mips64el,loongarch64},scripts},tftpboot/{zstack/{x86_64,aarch64,mips64el,loongarch64},pxelinux.cfg,EFI/BOOT},vsftpd} /var/log/zstack/baremetal/;
rm -rf /var/lib/zstack/baremetal/tftpboot/{grubaa64.efi,grub.cfg-01-*};
is_repo_exist='false'
for AR in $archRelease;do
    [ ! -d /opt/zstack-dvd/$AR ] && continue
    is_repo_exist='true'
    arch=`echo $AR | awk -F '/' '{print $1}'`
    if grep "ftp/zstack-dvd/$arch" /etc/fstab; then
      if [ ! -d "$(grep "ftp/zstack-dvd/$arch" /etc/fstab | awk -F ' ' '{print $1}')" ]; then
        sed -i "/ftp\/zstack-dvd\/$arch/d" /etc/fstab
        umount /var/lib/zstack/baremetal/ftp/zstack-dvd/$arch
      fi
    fi
    cp -f /opt/zstack-dvd/$AR/isolinux/pxelinux.0 /var/lib/zstack/baremetal/tftpboot/;
    cp -f /opt/zstack-dvd/$AR/EFI/BOOT/grubx64.efi /var/lib/zstack/baremetal/tftpboot/EFI/BOOT/ && chmod 755 /var/lib/zstack/baremetal/tftpboot/EFI/BOOT/grubx64.efi;
    cp -f /opt/zstack-dvd/$AR/EFI/BOOT/grubaa64.efi /var/lib/zstack/baremetal/tftpboot/EFI/BOOT/ && chmod 755 /var/lib/zstack/baremetal/tftpboot/EFI/BOOT/grubaa64.efi;
    cp -f /opt/zstack-dvd/$AR/images/pxeboot/{vmlinuz,initrd.img} /var/lib/zstack/baremetal/tftpboot/zstack/$arch/;
    grep "ftp/zstack-dvd/$arch" /etc/fstab || echo "/opt/zstack-dvd/$AR /var/lib/zstack/baremetal/ftp/zstack-dvd/$arch none defaults,bind 0 0" >> /etc/fstab;
done
[ $is_repo_exist == 'true' ] || exit 1
mount -a;
"""
run_remote_command(command, host_post_info)

# name: config iptables
command = """
/bin/cp -f /etc/sysconfig/iptables-config /etc/sysconfig/iptables-config-bck;
sed -e '/IPTABLES_MODULES=/s/"nf_conntrack_ftp"".*$/""/g' \
    -e '/IPTABLES_MODULES=/s/nf_conntrack_ftp\s*//g' \
    -e '/IPTABLES_MODULES=/s/="/="nf_conntrack_ftp /g' \
    -e '/IPTABLES_MODULES=/s/\s*"$/"/g' \
    -i /etc/sysconfig/iptables-config;
/sbin/service iptables save;
/sbin/service iptables restart
systemctl enable iptables.service
"""
run_remote_command(command, host_post_info)

# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/" % baremetalpxeserver_root
copy_arg.args = "force=yes"
copy_zstacklib = copy(copy_arg, host_post_info)

if copy_zstacklib != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zstacklib"
    agent_install_arg.agent_root = baremetalpxeserver_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install(agent_install_arg, host_post_info)

# name: copy baremetal pxeserver agent
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_baremetalpxeserver)
copy_arg.dest = "%s/%s" % (baremetalpxeserver_root, pkg_baremetalpxeserver)
copy_arg.args = "force=yes"
copy_baremetalpxeserver = copy(copy_arg, host_post_info)

if copy_baremetalpxeserver != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "baremetalpxeserver"
    agent_install_arg.agent_root = baremetalpxeserver_root
    agent_install_arg.pkg_name = pkg_baremetalpxeserver
    agent_install(agent_install_arg, host_post_info)

# name: copy service file
# only support centos redhat debian and ubuntu
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-baremetalpxeserver" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

# name: copy shellinaboxd
shellinaboxd_name = "shellinaboxd_{}".format(host_info.host_arch)
VSFTPD_ROOT_PATH = "/var/lib/zstack/baremetal/ftp"
copy_arg = CopyArg()
copy_arg.args = "force=yes"
copy_arg.src = "%s/%s" % (file_root, shellinaboxd_name)
copy_arg.dest = os.path.join(VSFTPD_ROOT_PATH, "shellinaboxd")
copy(copy_arg, host_post_info)

# name: copy noVNC.tar.gz
copy_arg = CopyArg()
copy_arg.src = "%s/noVNC.tar.gz" % file_root
copy_arg.dest = "/var/lib/zstack/baremetal/"
copy_arg.args = "force=yes"
copy(copy_arg, host_post_info)

# name: copy zwatch-vm-agent
zwatch_vm_agent_name = "zwatch-vm-agent{}".format('' if host_info.host_arch == 'x86_64' else '_' + host_info.host_arch)
copy_arg = CopyArg()
copy_arg.src = os.path.join(kvm_file_root, zwatch_vm_agent_name)
copy_arg.dest = os.path.join(VSFTPD_ROOT_PATH, 'zwatch-vm-agent')
copy(copy_arg, host_post_info)

copy_arg = CopyArg()
copy_arg.src = "%s/agent_version" % file_root
copy_arg.dest = VSFTPD_ROOT_PATH
copy_arg.args = "force=yes"
copy(copy_arg, host_post_info)

copy_arg = CopyArg()
copy_arg.src = "%s/zwatch-install.sh" % file_root
copy_arg.dest = VSFTPD_ROOT_PATH
copy_arg.args = "force=yes"
copy(copy_arg, host_post_info)

copy_arg = CopyArg()
copy_arg.src = "%s/pxeServerPushGateway.service" % file_root
copy_arg.dest = "/etc/systemd/system/"
copy_arg.args = "force=yes"
copy(copy_arg, host_post_info)

copy_arg = CopyArg()
copy_arg.src = "%s/baremetal-iptables" % file_root
copy_arg.dest = "/var/lib/zstack/baremetal/baremetal-iptables"
copy_arg.args = "force=yes"
copy(copy_arg, host_post_info)

# name: copy pushgateway
pushgateway_name = "pushgateway_%s" % host_info.host_arch
copy_arg = CopyArg()
copy_arg.args = "mode=a+x"
copy_arg.src = "%s/%s" % (file_root, pushgateway_name)
copy_arg.dest = "%s/pushgateway" % baremetalpxeserver_pushgateway_root
copy(copy_arg, host_post_info)

run_remote_command(("systemctl restart pxeServerPushGateway"), host_post_info)

# name: restart baremetalpxeserveragent
if host_info.distro in RPM_BASED_OS:
    command = "service zstack-baremetalpxeserver stop && service zstack-baremetalpxeserver start && chkconfig zstack-baremetalpxeserver on"
elif host_info.distro in DEB_BASED_OS:
    command = "update-rc.d zstack-baremetalpxeserver start 97 3 4 5 . stop 3 0 1 2 6 . && service zstack-baremetalpxeserver stop && service zstack-baremetalpxeserver start"
run_remote_command(command, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy baremetal pxeserver agent successful", host_post_info, "INFO")

sys.exit(0)
