#!/usr/bin/env python
# encoding: utf-8
import argparse
from zstacklib import *
from datetime import datetime


# create log
logger_dir = "/var/log/zstack/"
create_log(logger_dir)
banner("Starting to deploy sftpbackup storage agent")
start_time = datetime.now()
# set default value
file_root = "files/sftpbackupstorage"
pip_url = "https=//pypi.python.org/simple/"
proxy = ""
sproxy = ""
chroot_env = 'false'
zstack_repo = 'false'
current_dir = os.path.dirname(os.path.realpath(__file__))
post_url = ""
pkg_sftpbackupstorage = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None

# get parameter from shell
parser = argparse.ArgumentParser(description='Deploy sftpbackupstorage to host')
parser.add_argument('-i', type=str, help="""specify inventory host file
                        default=/etc/ansible/hosts""")
parser.add_argument('--private-key', type=str, help='use this file to authenticate the connection')
parser.add_argument('-e', type=str, help='set additional variables as key=value or YAML/JSON')

args = parser.parse_args()
argument_dict = eval(args.e)

# update the variable from shell arguments
locals().update(argument_dict)
virtenv_path = "%s/virtualenv/sftpbackupstorage/" % zstack_root
sftp_root = "%s/sftpbackupstorage/package" % zstack_root
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
if file_dir_exist("path=" + sftp_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (sftp_root, virtenv_path)
    run_remote_command(command, host_post_info)

run_remote_command("rm -rf %s/*" % sftp_root, host_post_info)

if distro == "RedHat" or distro == "CentOS":
    if zstack_repo != 'false':
        # name: install sftp backup storage related packages on RedHat based OS from local
        command = ("pkg_list=`rpm -q openssh-clients qemu-img-ev libvirt libguestfs-winsupport libguestfs-tools | grep \"not installed\" | awk '{ print $2 }'` && for pkg"
                   " in $pkg_list; do yum --disablerepo=* --enablerepo=%s install -y $pkg; done;") % zstack_repo
        run_remote_command(command, host_post_info)
    else:
        # name: install sftp backup storage related packages on RedHat based OS from online
        for pkg in [ "openssh-clients", "qemu-img-ev", "libvirt", "libguestfs-winsupport", "libguestfs-tools"]:
            yum_install_package(pkg, host_post_info)

elif distro == "Debian" or distro == "Ubuntu":
    install_pkg_list = ["openssh-client", "qemu-utils", "libvirt-bin", "libguestfs-winsupport", "libguestfs-tools"]
    apt_install_packages(install_pkg_list, host_post_info)

else:
    error("unsupported OS!")

# name: install virtualenv
virtual_env_status = check_and_install_virtual_env(virtualenv_version, trusted_host, pip_url, host_post_info)
if virtual_env_status is False:
    command = "rm -rf %s && rm -rf %s" % (virtenv_path, sftp_root)
    run_remote_command(command, host_post_info)
    sys.exit(1)

# name: make sure virtualenv has been setup
command = "[ -f %s/bin/python ] || virtualenv %s " % (virtenv_path, virtenv_path)
run_remote_command(command, host_post_info)

# name: add public key
authorized_key("root", current_dir + "/id_rsa.sftp.pub", host_post_info)

# name: copy zstacklib
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/%s" % (sftp_root, pkg_zstacklib)
zstacklib_copy_result = copy(copy_arg, host_post_info)

# name: install zstacklib
if zstacklib_copy_result != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "zstacklib"
    agent_install_arg.agent_root = sftp_root
    agent_install_arg.pkg_name = pkg_zstacklib
    agent_install(agent_install_arg, host_post_info)

# name: copy sftp
copy_arg = CopyArg()
copy_arg.src = "%s/%s" % (file_root, pkg_sftpbackupstorage)
copy_arg.dest = "%s/%s" % (sftp_root, pkg_sftpbackupstorage)
sftp_copy_result = copy(copy_arg, host_post_info)

# name: copy sftp backup storage service file
copy_arg = CopyArg()
copy_arg.src = "%s/zstack-sftpbackupstorage" % file_root
copy_arg.dest = "/etc/init.d/"
copy_arg.args = "mode=755"
copy(copy_arg, host_post_info)

# name: install sftp
if sftp_copy_result != "changed:False":
    agent_install_arg = AgentInstallArg(trusted_host, pip_url, virtenv_path, init_install)
    agent_install_arg.agent_name = "sftpbackupstorage"
    agent_install_arg.agent_root = sftp_root
    agent_install_arg.pkg_name = pkg_sftpbackupstorage
    agent_install(agent_install_arg, host_post_info)

# name: restart sftp
if chroot_env == 'false':
    if distro == "RedHat" or distro == "CentOS":
        # some users meet restart can't work on their system
        command = "service zstack-sftpbackupstorage stop && service zstack-sftpbackupstorage start && chkconfig zstack-sftpbackupstorage on"
    elif distro == "Debian" or distro == "Ubuntu":
        command = "service zstack-sftpbackupstorage stop && service zstack-sftpbackupstorage start && update-rc.d zstack-sftpbackupstorage enable"
    run_remote_command(command, host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploysftpbackupstorage agent successful", host_post_info, "INFO")
sys.exit(0)
