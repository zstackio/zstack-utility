#!/usr/bin/env python
# encoding: utf-8
import argparse
from zstacklib import *
from distutils.version import LooseVersion

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
chrony_servers = None
pkg_cephpagent = ""
virtualenv_version = "12.1.1"
remote_user = "root"
remote_pass = None
remote_port = None
host_uuid = None


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
host_post_info.host_uuid = host_uuid
host_post_info.post_url = post_url
host_post_info.chrony_servers = chrony_servers
host_post_info.private_key = args.private_key
host_post_info.remote_user = remote_user
host_post_info.remote_pass = remote_pass
host_post_info.remote_port = remote_port
if remote_pass is not None and remote_user != 'root':
    host_post_info.become = True

IS_AARCH64 = get_remote_host_arch(host_post_info) == 'aarch64'
if IS_AARCH64:
    qemu_img_pkg = "files/kvm/qemu-img-aarch64"
    qemu_img_local_pkg = "%s/qemu-img-aarch64" % cephp_root

# include zstacklib.py
(distro, major_version, distro_release, distro_version) = get_remote_host_info(host_post_info)
releasever = get_host_releasever([distro, distro_release, distro_version])
host_post_info.releasever = releasever

zstacklib_args = ZstackLibArgs()
zstacklib_args.distro = distro
zstacklib_args.distro_release = distro_release
zstacklib_args.distro_version = distro_version
zstacklib_args.zstack_repo = zstack_repo
zstacklib_args.zstack_root = zstack_root
zstacklib_args.host_post_info = host_post_info
zstacklib_args.pip_url = pip_url
zstacklib_args.trusted_host = trusted_host
zstacklib_args.zstack_releasever = releasever
if distro in DEB_BASED_OS:
    zstacklib_args.apt_server = yum_server
    zstacklib_args.zstack_apt_source = zstack_repo
else :
    zstacklib_args.yum_server = yum_server
zstacklib = ZstackLib(zstacklib_args)


# name: judge this process is init install or upgrade
if file_dir_exist("path=" + cephp_root, host_post_info):
    init_install = False
else:
    init_install = True
    # name: create root directories
    command = 'mkdir -p %s %s' % (cephp_root, virtenv_path)
    run_remote_command(command, host_post_info)

if distro in RPM_BASED_OS:
    if zstack_repo != 'false':
        command = """pkg_list=`rpm -q wget {} nmap| grep "not installed" | awk '{{ print $2 }}'` && for pkg"""\
                """ in $pkg_list; do yum --disablerepo=* --enablerepo={} install -y $pkg; done;"""\
                .format(qemu_alias.get(releasever, "qemu-kvm-ev"), zstack_repo)
        run_remote_command(command, host_post_info)
        if distro_version >= 7:
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            run_remote_command(command, host_post_info)
    else:
        for pkg in ["wget", "nmap", qemu_alias.get(releasever, "qemu-kvm-ev")]:
            yum_install_package(pkg, host_post_info)
        if distro_version >= 7:
            command = "(which firewalld && service firewalld stop && chkconfig firewalld off) || true"
            run_remote_command(command, host_post_info)
    set_selinux("state=disabled", host_post_info)

    # replace qemu-img binary if qemu-img-ev before 2.12.0 is installed, to fix zstack-11004 / zstack-13594 / zstack-20983
    command = "qemu-img --version | grep 'qemu-img version' | cut -d ' ' -f 3 | cut -d '(' -f 1"
    (status, qemu_img_version) = run_remote_command(command, host_post_info, False, True)
    if IS_AARCH64 and LooseVersion(qemu_img_version) < LooseVersion('2.12.0'):
        copy_arg = CopyArg()
        copy_arg.src = "%s" % qemu_img_pkg
        copy_arg.dest = "%s" % qemu_img_local_pkg
        copy(copy_arg, host_post_info)

        command = "for i in {1..5}; do /bin/cp %s `which qemu-img` && break || sleep 2; done; sync" % qemu_img_local_pkg
        host_post_info.post_label = "ansible.shell.install.pkg"
        host_post_info.post_label_param = "qemu-img"
        run_remote_command(command, host_post_info)

elif distro in DEB_BASED_OS:
    install_pkg_list = ["wget", "qemu-utils","libvirt-bin", "libguestfs-tools"]
    apt_install_packages(install_pkg_list, host_post_info)
    command = "(chmod 0644 /boot/vmlinuz*) || true"
    run_remote_command(command, host_post_info)
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

# name: install python pkg
extra_args = "\"--trusted-host %s -i %s \"" % (trusted_host, pip_url)
pip_install_arg = PipInstallArg()
pip_install_arg.extra_args = extra_args
pip_install_arg.name = "python-cephlibs"
pip_install_package(pip_install_arg, host_post_info)

# name: copy zstacklib and install
copy_arg = CopyArg()
copy_arg.src = "files/zstacklib/%s" % pkg_zstacklib
copy_arg.dest = "%s/" % cephp_root
copy_arg.args = "force=yes"
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
copy_arg.args = "force=yes"
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

copy_arg = CopyArg()
copy_arg.src = "%s/cephps-iptables" % file_root
copy_arg.dest = "/var/lib/zstack/cephp/package/cephps-iptables"
copy_arg.args = "force=yes"
copy(copy_arg, host_post_info)

# name: restart cephpagent
if distro in RPM_BASED_OS:
    command = "service zstack-ceph-primarystorage stop && service zstack-ceph-primarystorage start" \
              " && chkconfig zstack-ceph-primarystorage on"
elif distro in DEB_BASED_OS:
    command = "update-rc.d zstack-ceph-primarystorage start 97 3 4 5 . stop 3 0 1 2 6 . && service zstack-ceph-primarystorage stop && service zstack-ceph-primarystorage start"
run_remote_command(command, host_post_info)

# change ceph config
# xsky does not need this configuration
#    xsky v3.1.x rbd_default_format = 2 (by default)
#    xsky v3.2.x rbd_default_format = 128 (by default)
command = "test -f /usr/bin/xms-cli"
status = run_remote_command(command, host_post_info, True, False)
if status is False:
    set_ini_file("/etc/ceph/ceph.conf", 'global', "rbd_default_format", "2", host_post_info)

host_post_info.start_time = start_time
handle_ansible_info("SUCC: Deploy ceph primary agent successful", host_post_info, "INFO")

sys.exit(0)
