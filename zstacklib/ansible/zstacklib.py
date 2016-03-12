#!/usr/bin/env python
# encoding: utf-8
import os
import sys
#import argparse
from deploylib import *

class ZstackLib(object):
    def __init__(self,args):
        distro = args.distro
        distro_version = args.distro_version
        yum_repo = args.yum_repo
        yum_server = args.yum_server
        zstack_root = args.zstack_root
        host_post_info = args.host_post_info
        epel_repo_exist = file_dir_exist("path=/etc/yum.repos.d/epel.repo", host_post_info)
        if distro == "CentOS" or distro == "RedHat":
                #set ALIYUN mirror yum repo firstly avoid 'yum clean --enablerepo=alibase metadata' failed
            command = """
echo -e "#aliyun base
[alibase]
name=CentOS-\$releasever - Base - mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/\$releasever/os/\$basearch/
gpgcheck=0
enabled=0
#released updates
[aliupdates]
name=CentOS-\$releasever - Updates -mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/\$releasever/updates/\$basearch/
enabled=0
gpgcheck=0
[aliextras]
name=CentOS-\$releasever - Extras - mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/\$releasever/extras/\$basearch/
enabled=0
gpgcheck=0
[aliepel]
name=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com
baseurl=http://mirrors.aliyun.com/epel/\$releasever/\$basearch
failovermethod=priority
enabled=0
gpgcheck=0" > /etc/yum.repos.d/zstack-aliyun-yum.repo
        """
            run_remote_command(command, host_post_info)
            #yum_repo defined by user
            if yum_repo == "false":
                yum_install_package("libselinux-python", host_post_info)
                if epel_repo_exist is False:
                    copy_arg = CopyArg()
                    copy_arg.src = "files/zstacklib/epel-release-source.repo"
                    copy_arg.dest =  "/etc/yum.repos.d/"
                    copy(copy_arg, host_post_info)
                    #install epel-release
                    yum_enable_repo("epel-release","epel-release-source", host_post_info)
                    set_ini_file("/etc/yum.repos.d/epel.repo", 'epel', "enabled", "1", host_post_info)
                command = 'yum clean --enablerepo=alibase metadata'
                run_remote_command(command, host_post_info)
                for pkg in ["htop", "python-devel", "python-setuptools", "python-pip", "gcc", "autoconf", "ntp", "ntpdate"]:
                    yum_install_package(pkg, host_post_info)
            else:
                #set 163 mirror yum repo
                command = """
echo -e "#163 base
[163base]
name=CentOS-\$releasever - Base - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/\$releasever/os/\$basearch/
gpgcheck=0
enabled=0
#released updates
[163updates]
name=CentOS-\$releasever - Updates - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/\$releasever/updates/\$basearch/
enabled=0
gpgcheck=0
#additional packages that may be useful
[163extras]
name=CentOS-\$releasever - Extras - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/\$releasever/extras/\$basearch/
enabled=0
gpgcheck=0
[ustcepel]
name=Extra Packages for Enterprise Linux \$releasever - \$basearch - ustc
baseurl=http://centos.ustc.edu.cn/epel/\$releasever/\$basearch
failovermethod=priority
enabled=0
gpgcheck=0" > /etc/yum.repos.d/zstack-163-yum.repo
        """
                run_remote_command(command, host_post_info)
                #install libselinux-python and other command system libs from user defined repos
                #enable alibase repo for yum clean avoid no repo to be clean
                command = ("yum clean --enablerepo=alibase metadata && yum --disablerepo=* --enablerepo=%s --nogpgcheck install -y libselinux-python"
                           " python-devel python-setuptools python-pip gcc autoconf ntp ntpdate") % yum_repo
                run_remote_command(command, host_post_info)
                #command = ('yum clean --enablerepo=alibase metadata')
                #run_remote_command(command, host_post_info)
                #for pkg in ['libselinux-python','python-devel',' python-setuptools','python-pip','gcc','autoconf','ntp','ntpdate']:
                #    yum_install_package_via_repos(pkg,yum_repo, host_post_info)

            #enable ntp service for RedHat
            command = ('chkconfig ntpd on; service ntpd restart')
            run_remote_command(command, host_post_info)

        elif distro == "Debian" or distro == "Ubuntu":
            #install dependency packages for Debian based OS
            for pkg in ["python-dev","python-setuptools","python-pip","gcc","autoconf","ntp","ntpdate"]:
                apt_install_packages(pkg, host_post_info)

            #name: enable ntp service for Debian
            run_remote_command("update-rc.d ntp defaults; service ntp restart", host_post_info)

        else:
            print "ERROR: Unsupported distribution"
            sys.exit(1)

        #check the pip 7.0.3 exist in system
        pip_match = run_remote_command("pip --version | grep 7.0.3", host_post_info)
        if pip_match is False:
            #make dir for copy pip
            run_remote_command("mkdir -p %s" % zstack_root, host_post_info)
            #copy pip 7.0.3
            copy_arg = CopyArg()
            copy_arg.src = "files/pip-7.0.3.tar.gz"
            copy_arg.dest = "%s/pip-7.0.3.tar.gz" % zstack_root
            copy(copy_arg, host_post_info)
            #install pip 7.0.3
            pip_install_arg = PipInstallArg()
            pip_install_arg.extra_args = "--ignore-installed"
            pip_install_arg.name = "%s/pip-7.0.3.tar.gz" % zstack_root
            pip_install_package(pip_install_arg,host_post_info)
