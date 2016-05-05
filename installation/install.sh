#!/bin/bash
# Mevoco Installer
# Usage: bash install.sh
#DEBUG='y'
PRODUCT_NAME=${PRODUCT_NAME:-"ZStack"}
VERSION=${PRODUCT_VERSION:-""}
ZSTACK_INSTALL_ROOT=${ZSTACK_INSTALL_ROOT:-"/usr/local/zstack"}

CENTOS6='CENTOS6'
CENTOS7='CENTOS7'
UBUNTU1404='UBUNTU14.04'
UPGRADE='n'
FORCE='n'
MANAGEMENT_INTERFACE=`ip route | grep default | cut -d ' ' -f 5`
SUPPORTED_OS="$CENTOS6, $CENTOS7, $UBUNTU1404"
ZSTACK_INSTALL_LOG='/tmp/zstack_installation.log'
ZSTACKCTL_INSTALL_LOG='/tmp/zstack_ctl_installation.log'
[ -f $ZSTACK_INSTALL_LOG ] && /bin/rm -f $ZSTACK_INSTALL_LOG
INSTALLATION_FAILURE=/tmp/zstack_installation_failure_exit_code
[ -f $INSTALLATION_FAILURE ] && /bin/rm -f $INSTALLATION_FAILURE

WIDTH=`tput cols`
[ -z $WIDTH ] && WIDTH=80
HEIGHT=`tput lines`
[ -z $HEIGHT ] && HEIGHT=25
ZSTACK_INSTALLATION='$PRODUCT_NAME Intallation'
START_POINT=`expr $WIDTH / 2 + 9`
END_POINT=`expr $WIDTH - $START_POINT - 1`
STEP="1"

zstack_tmp_file=`mktemp`
ZSTACK_ALL_IN_ONE=${ZSTACK_ALL_IN_ONE-"http://download.zstack.org/releases/0.8/0.8.0/zstack-all-in-one-0.8.0.tgz"}
WEBSITE=${WEBSITE-'zstack.org'}
[ -z $WEBSITE ] && WEBSITE='zstack.org'
ZSTACK_VERSION=$ZSTACK_INSTALL_ROOT/VERSION
CATALINA_ZSTACK_PATH=apache-tomcat/webapps/zstack
CATALINA_ZSTACK_CLASSES=$CATALINA_ZSTACK_PATH/WEB-INF/classes
ZSTACK_PROPERTIES=$CATALINA_ZSTACK_CLASSES/zstack.properties
ZSTACK_DB_DEPLOYER=$CATALINA_ZSTACK_CLASSES/deploydb.sh
CATALINA_ZSTACK_TOOLS=$CATALINA_ZSTACK_CLASSES/tools
ZSTACK_TOOLS_INSTALLER=$CATALINA_ZSTACK_TOOLS/install.sh
zstack_163_repo_file=/etc/yum.repos.d/zstack-163-yum.repo
zstack_ali_repo_file=/etc/yum.repos.d/zstack-aliyun-yum.repo
PRODUCT_TITLE_FILE='./product_title_file'

[ ! -z $http_proxy ] && HTTP_PROXY=$http_proxy

NEED_NFS=''
NEED_HTTP=''
NEED_DROP_DB=''
NEED_KEEP_DB=''
ONLY_INSTALL_LIBS=''
ONLY_INSTALL_ZSTACK=''
NOT_START_ZSTACK=''
NEED_SET_MN_IP=''

MYSQL_ROOT_PASSWORD=''
MYSQL_NEW_ROOT_PASSWORD='zstack.mysql.password'
MYSQL_USER_PASSWORD='zstack.password'

YUM_ONLINE_REPO='y'
INSTALL_MONITOR=''
ZSTACK_START_TIMEOUT=300
ZSTACK_YUM_MIRROR=''
YUM_MIRROR_163='163'
YUM_MIRROR_ALIYUN='aliyun'
ZSTACK_YUM_REPOS=''
ZSTACK_LOCAL_YUM_REPOS='zstack-local'
MIRROR_163_YUM_REPOS='163base,163updates,163extras,ustcepel'
MIRROR_ALI_YUM_REPOS='alibase,aliupdates,aliextras,aliepel'

QUIET_INSTALLATION=''
CHANGE_HOSTNAME=''
CHANGE_HOSTS=''
DELETE_PY_CRYPTO=''
SETUP_EPEL=''
LICENSE_FILE='zstack-license'

show_download()
{
    $1 &
    PID=$!
    local delay=0.2
    ps -p $PID >/dev/null 2>&1
    sleep 0.05
    echo -n " ... "
    while [ $? -eq 0 ]; do
        if [ -z $DEBUG ];then
            local temp=`ls -sh $zstack_tmp_file 2>/dev/null|awk '{print $1}'`
            to_print="$temp"
            echo -n $to_print
            size=${#to_print} 
            sleep $delay
            count=0
            while [ $count -lt $size ]; do echo -ne "\b" ; count=`expr $count + 1`; done
        else
            sleep $delay
        fi
        ps -p $PID >/dev/null 2>&1
    done
    if [ -f $INSTALLATION_FAILURE ]; then
        failure_reason=`cat $INSTALLATION_FAILURE`
        #tput cub 6
        if [ -z $DEBUG ]; then
            echo -e "$(tput setaf 1)FAIL\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
            echo -e "$(tput setaf 1)  Reason: $failure_reason\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
        else
            echo "FAIL"
            echo "Reason: $failure_reason"
        fi
        exit 1
    else
        if  [ -z $DEBUG ]; then
            echo -e "$(tput setaf 2)PASS$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
        else
            echo "PASS"
        fi
    fi
}

show_spinner()
{
    $* &
    PID=$!
    local delay=0.1
    local spinstr='|/-\'
    spin[0]="-"
    spin[1]="\\"
    spin[2]="|"
    spin[3]="/"
    sleep 0.05
    echo -n " ... "
    while kill -0 $PID 2>/dev/null
    do
        if [ -z $DEBUG ];then
            for i in "${spin[@]}"
                do
                    echo -ne "$i"
                    sleep 0.1
                    echo -ne "\b"
            done
        else
            sleep 0.1
        fi
    done

    if [ -f $INSTALLATION_FAILURE ]; then
        failure_reason=`cat $INSTALLATION_FAILURE`
        #tput cub 6
        if [ -z $DEBUG ]; then
            echo -e "$(tput setaf 1)FAIL\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
            echo -e "$(tput setaf 1)  Reason: $failure_reason\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
        else
            echo "FAIL"
            echo "Reason: $failure_reason"
        fi
        exit 1
    else
        if [ -z $DEBUG ]; then
            echo -e "$(tput setaf 2)PASS$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
        else
            echo "PASS"
        fi
    fi
}

debug(){
    [ ! -z $DEBUG ] && echo "  [DEBUG]: " $*
}

echo_star_line(){
    i=0
    line=''
    while [ $i -lt $WIDTH ];do
        line=$line"_"
        i=`expr $i + 1 `
    done
    echo $line
}

cancel(){
    echo ""|tee -a $ZSTACK_INSTALL_LOG
    [ ! -z $PID ] && kill -9 $PID
    tput sgr0
    tput rc
    echo -e "$(tput setaf 3)Installation canceled by User\n$(tput sgr0)"
    echo "The detailed installation log could be found in $ZSTACK_INSTALL_LOG"
    /bin/rm -f $INSTALLATION_FAILURE
    /bin/rm -f $zstack_tmp_file
    exit 1
}

trap cancel INT

# The params is failed reason
fail(){
    #tput cub 6
    #echo -e "$(tput setaf 1) FAIL\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
    #echo -e "$(tput setaf 1)  Reason: $*\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
    echo "-------------"
    echo "$*  \n\nThe detailed installation log could be found in $ZSTACK_INSTALL_LOG " > $INSTALLATION_FAILURE
    echo "-------------"
    exit 1
}

#not for spin task fail
fail2(){
    tput cub 6
    echo -e "$(tput setaf 1) FAIL\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
    echo -e "$(tput setaf 1)  Reason: $*\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
    echo "-------------"
    echo "$*  \n\nThe detailed installation log could be found in $ZSTACK_INSTALL_LOG " > $INSTALLATION_FAILURE
    echo "-------------"
    exit 1
}

pass(){
    #echo -e "$(tput setaf 2) PASS$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
    return
}

echo_title(){
    echo "\n================">> $ZSTACK_INSTALL_LOG
    echo ""|tee -a $ZSTACK_INSTALL_LOG
    echo -n " ${STEP}. $*:" |tee -a $ZSTACK_INSTALL_LOG
    STEP=`expr $STEP + 1`
}

echo_subtitle(){
    echo "\n----------------" >> $ZSTACK_INSTALL_LOG
    echo -n "    $*:"|tee -a $ZSTACK_INSTALL_LOG
}

cs_check_hostname(){
    which hostname &>/dev/null
    [ $? -ne 0 ] && return 
    current_hostname=`hostname`
    if [ "localhost" = $current_hostname ] || [ "localhost.localdomain" = $current_hostname ] ; then
        CHANGE_HOSTNAME=`echo $MANAGEMENT_IP|sed 's/\./-/g'`
        CHANGE_HOSTS="127.0.0.1 $CHANGE_HOSTNAME"
        which hostnamectl >>/dev/null 2>&1
        if [ $? -ne 0 ]; then
            hostname $CHANGE_HOSTNAME
            echo "127.0.0.1 $CHANGE_HOSTNAME"  >>/etc/hosts
        else
            hostnamectl set-hostname $CHANGE_HOSTNAME >>$ZSTACK_INSTALL_LOG 2>&1
            echo "127.0.0.1 $CHANGE_HOSTNAME"  >>/etc/hosts
        fi
        echo "Your OS hostname is set as $current_hostname, which will block vm live migration. You can set a special hostname, or directly use $CHANGE_HOSTNAME by running following commands in CentOS6:

        hostname $CHANGE_HOSTNAME
        echo 127.0.0.1 $CHANGE_HOSTNAME >> /etc/hosts

or following commands in CentOS7:
        hostnamectl set-hostname $CHANGE_HOSTNAME
        echo 127.0.0.1 $CHANGE_HOSTNAME >> /etc/hosts

" >> $ZSTACK_INSTALL_LOG
        return 0
    fi

    ip addr | grep inet |awk '{print $2}'|grep $current_hostname &> /dev/null
    [ $? -ne 0 ] && return 0
    echo "Your OS hostname is set as $current_hostname, which is same with your IP address. It will make rabbitmq-server installation failed. 
Please fix it by running following commands in CentOS7:

    hostnamectl set-hostname MY_REAL_HOSTNAME
    echo \"$current_hostname MY_REAL_HOSTNAME\" >>/etc/hosts

Or use other hostname setting method in other system. 
Then restart installation. 

You can also add '-q' to installer, then Installer will help you to set one.
" >> $ZSTACK_INSTALL_LOG
    CHANGE_HOSTNAME=`echo $MANAGEMENT_IP|sed 's/\./-/g'`
    CHANGE_HOSTS="$current_hostname $CHANGE_HOSTNAME"
    which hostnamectl >>/dev/null 2>&1
    if [ $? -ne 0 ]; then
        hostname $CHANGE_HOSTNAME
        echo "$current_hostname $CHANGE_HOSTNAME" >>/etc/hosts
    else
        hostnamectl set-hostname $CHANGE_HOSTNAME >>$ZSTACK_INSTALL_LOG 2>&1
        echo "$current_hostname $CHANGE_HOSTNAME" >>/etc/hosts
    fi
}

#Do preinstallation checking for CentOS and Ubuntu
check_system(){
    echo_title "Check System"
    cat /etc/*-release |egrep -i -h "centos |Red Hat Enterprise" >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -eq 0 ]; then
        grep 'release 6' /etc/redhat-release >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -eq 0 ]; then
            OS=$CENTOS6
        else
            grep 'release 7' /etc/redhat-release >>$ZSTACK_INSTALL_LOG 2>&1
            if [ $? -eq 0 ]; then
                OS=$CENTOS7
                rpm -q libvirt |grep 1.1.1-29 >/dev/null 2>&1
                if [ $? -eq 0 ]; then
                    fail2 "Your OS is old CentOS7, as its libvirt is `rpm -q libvirt`. You need to use \`yum upgrade\` to upgrade your system to latest CentOS7."
                fi
            else
                fail2 "Host OS checking failure: your system is: `cat /etc/redhat-release`, we can only support $SUPPORTED_OS currently"
            fi
        fi
    else
        grep 'Ubuntu' /etc/issue >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -eq 0 ]; then
            OS=$UBUNTU1404
        else
            fail2 "Host OS checking failure: your system is: `cat /etc/issue`, we can only support $SUPPORTED_OS currently"
        fi
    fi
    
    if [ $OS = $CENTOS6 ]; then
        yum_repo_folder="${ZSTACK_INSTALL_ROOT}/apache-tomcat/webapps/zstack/static/centos6_repo"
        #only support online installation for CentoS6.x
        if [ -z "$YUM_ONLINE_REPO" -a -z "$ZSTACK_YUM_MIRROR" ]; then
            fail2 "Your system is $OS . ${PRODUCT_NAME} installer doesn't suport offline installation for $OS . Please do not use '-o' option to install. "
        fi
        yum_source="file://${yum_repo_folder}"
    elif [ $OS = $CENTOS7 ]; then
        yum_repo_folder="${ZSTACK_INSTALL_ROOT}/apache-tomcat/webapps/zstack/static/centos7_repo"
        yum_source="file://${yum_repo_folder}"
    fi
    debug "Your system is: $OS"

    if [ $UPGRADE = 'y' ]; then
        which zstack-ctl >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            fail2 "Did not find zstack-ctl. Can not use option '-u' to upgrade $PRODUCT_NAME . Please remove '-u' and do fresh installation."
        fi
    fi
    cs_check_epel
    cs_check_hostname
    show_spinner do_check_system
}

cs_check_epel(){
    [ -z $YUM_ONLINE_REPO ] && return
    [ ! -z $ZSTACK_YUM_MIRROR ] && return
    if [ "$OS" = $CENTOS7 -o "$OS" = $CENTOS6 ]; then 
        if [ ! -f /etc/yum.repos.d/epel.repo ]; then
            zstack-ctl show_configuration 2>/dev/null|grep Ansible.var.yum_repo >/dev/null 2>&1
            [ $? -eq 0 ] && return
            if [ -z $QUIET_INSTALLATION ]; then
                fail2 'You need to set /etc/yum.repos.d/epel.repo to install ZStack required libs from online. 

Or you can choose to use -R 163 or -R aliyun to install.

Or if you have set the epel in other file, rather than /etc/yum.repos.d/epel.repo, you can add -q to ask installer to ignore checking. The example for /etc/yum.repos.d/epel.repo is like:

#cat /etc/yum.repos.d/epel.repo
[epel]
name=Extra Packages for Enterprise Linux \$releasever - \$basearch
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-\$releasever&arch=\$basearch
enabled=1
gpgcheck=0

'
#            else
#                cat > /etc/yum.repos.d/epel.repo << EOF
#[epel]
#name=Extra Packages for Enterprise Linux \$releasever - \$basearch
#mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-\$releasever&arch=\$basearch
#enabled=1
#gpgcheck=0
#EOF
#                SETUP_EPEL='y'
            fi
        fi
    fi
}

do_enable_sudo(){
    if [ -f /etc/sudoers ]; then
        grep 'zstack' /etc/sudoers &>/dev/null || echo 'zstack        ALL=(ALL)       NOPASSWD: ALL' >> /etc/sudoers
        grep '^root' /etc/sudoers &>/dev/null || echo 'root ALL=(ALL)       NOPASSWD: ALL' >> /etc/sudoers
        sed -i '/requiretty$/d' /etc/sudoers
    fi
}

do_check_system(){
    if [ $UPGRADE = 'n' ]; then
        if [ -d $ZSTACK_INSTALL_ROOT -o -f $ZSTACK_INSTALL_ROOT ];then
            echo "stop zstack all services" >>$ZSTACK_INSTALL_LOG
            zstack-ctl stop >>$ZSTACK_INSTALL_LOG 2>&1
            fail "$ZSTACK_INSTALL_ROOT is existing. Please delete it manually before installing a new ${PRODUCT_NAME}\n  You might want to save your previous zstack.properties by \`zstack-ctl save_config\` and restore it later.\n All ZStack services have been stopped. Run \`zstack-ctl start\` to recover."
        fi
    fi

    if [ `whoami` != 'root' ];then
        fail "User checking failure: ${PRODUCT_NAME} installation must be run with user: root . Current user is: `whoami`. Please append 'sudo'."
    fi

    if [ ! -z $ZSTACK_YUM_REPOS ];then
        ping -c 1 -w 1 $WEBSITE >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ]; then
            fail "Network checking failure: can not reach $WEBSITE. Please make sure your DNS (/etc/resolv.conf) is configured correctly. Or you can override WEBSITE by \`export WEBSITE=YOUR_INTERNAL_YUM_SERVER\` before doing installation. "
        fi
    fi

    rpm -qi python-crypto >/dev/null 2>&1
    if [ $? -eq 0 ]; then 
        if [ -z $QUIET_INSTALLATION ]; then
            fail "need to manually remove python-crypto by \n\n \`rpm -ev python-crypto\` \n\n; otherwise it will conflict with ansible's pycrypto.

You can also add '-q' to installer, then Installer will help you to remove it.
"
        else
            rpm -ev python-crypto --nodeps >>$ZSTACK_INSTALL_LOG 2>&1
            DELETE_PY_CRYPTO='y'
        fi
        [ $? -ne 0 ] && fail "Uninstall python-crypto fail"
    fi

    ia_check_ip_hijack

    #add user: zstack and add sudo permission for it.
    id -u zstack >/dev/null 2>&1 
    if [ $? -eq 0 ]; then
        usermod -d $ZSTACK_INSTALL_ROOT zstack >/dev/null 2>&1
    else
        useradd -d $ZSTACK_INSTALL_ROOT zstack >/dev/null 2>&1
    fi
    zstack_home=`eval echo ~zstack`
    if [ ! -d $zstack_home ];then
        mkdir -p $zstack_home >>$ZSTACK_INSTALL_LOG 2>&1
        chown -R zstack.zstack $zstack_home >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    do_enable_sudo
    pass
}

ia_check_ip_hijack(){
    HOSTNAME=`hostname`
    
    pintret=`ping -c 1 -W 2 $HOSTNAME 2>/dev/null | head -n1`
    echo $pintret | grep 'PING' > /dev/null
    [ $? -ne 0 ] && return 0
    
    ip=`echo $pintret | cut -d' ' -f 3 | cut -d'(' -f 2 | cut -d')' -f 1`
    
    ip_1=`echo $ip | cut -d'.' -f 1`
    [ "127" = "$ip_1" ] && return 0
    
    ip addr | grep $ip > /dev/null
    [ $? -eq 0 ] && return 0
    
    echo "The hostname($HOSTNAME) of your machine is resolved to IP($ip) which is none of IPs of your machine.
    It's likely your DNS server has been hijacking, please try fixing it or add \"127.0.0.1 $HOSTNAME\" to /etc/hosts by \n\n \`echo \"127.0.0.1 $HOSTNAME\" >>/etc/hosts\`.
" >> $ZSTACK_INSTALL_LOG
    
    echo "127.0.0.1 $HOSTNAME" >>/etc/hosts
    CHANGE_HOSTS='127.0.0.1 $HOSTNAME'
}

ia_install_python_gcc_rh(){
    echo_subtitle "Install Python and GCC"
    if [ ! -z $ZSTACK_YUM_REPOS ];then
        if [ -z $DEBUG ];then
            yum clean metadata >/dev/null 2>&1
            yum -y --disablerepo="*" --enablerepo=$ZSTACK_YUM_REPOS install python python-devel python-setuptools gcc>>$ZSTACK_INSTALL_LOG 2>&1
        else
            yum clean metadata >/dev/null 2>&1
            yum -y --disablerepo="*" --enablerepo=$ZSTACK_YUM_REPOS install python python-devel python-setuptools gcc
        fi
    else
        if [ -z $DEBUG ];then
            yum clean metadata >/dev/null 2>&1
            yum -y install python python-devel python-setuptools gcc>>$ZSTACK_INSTALL_LOG 2>&1
        else
            yum clean metadata >/dev/null 2>&1
            yum -y install python python-devel python-setuptools gcc
        fi
    fi

    if [ $? -ne 0 ]; then
        yum clean metadata >/dev/null 2>&1
        fail "Install python and gcc fail."
    fi
    yum clean metadata >/dev/null 2>&1
    pass
}

ia_install_pip(){
    echo_subtitle "Install PIP"
    if [ ! -z $DEBUG ]; then
        easy_install -i $pypi_source_easy_install --upgrade pip
    else
        easy_install -i $pypi_source_easy_install --upgrade pip >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    [ $? -ne 0 ] && fail "install PIP failed"
    pass
}

ia_install_ansible(){
    echo_subtitle "Install Ansible"
    if [ $OS = $CENTOS7 -o $OS = $CENTOS6 ]; then
        yum remove -y ansible >>$ZSTACK_INSTALL_LOG 2>&1
    else
        apt-get --assume-yes remove ansible >>$ZSTACK_INSTALL_LOG 2>&1
    fi

    if [ ! -z $DEBUG ]; then
        pip install -i $pypi_source_pip --trusted-host localhost --ignore-installed ansible 
    else
        pip install -i $pypi_source_pip --trusted-host localhost --ignore-installed ansible >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    [ $? -ne 0 ] && fail "install Ansible failed"
    pass
}

ia_install_python_gcc_db(){
    echo_subtitle "Install Python GCC."
    if [ ! -z $DEBUG ]; then
        apt-get -y install python python-dev python-setuptools gcc 
    else
        apt-get -y install python python-dev python-setuptools gcc >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    [ $? -ne 0 ] && fail "Install python and gcc fail."
    pass
}

ia_update_apt(){
    echo_subtitle "Update Apt Source"
    dpkg --configure -a >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "execute \`dpkg -- configure -a\` failed."
    apt-get update >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ]; then 
        if [ -z $QUIET_INSTALLATION ]; then
            fail "Update apt source fail. If you do not need apt-get update, please add option '-q' and restart the installation. "
        fi
        echo "Update apt source failed. But you choose to skip the failure. " >>$ZSTACK_INSTALL_LOG
    fi
    pass
}

download_zstack(){
    echo_title "Get ${PRODUCT_NAME}"
    echo ""
    show_download iz_download_zstack
    show_spinner iz_unpack_zstack
}

unpack_zstack_into_tomcat(){
    echo_title "Install ${PRODUCT_NAME} Package"
    echo ""
    which unzip >/dev/null 2>&1
    if [ $? -ne 0 ];then
        show_spinner iz_install_unzip
    fi
    show_spinner iz_unzip_tomcat
    show_spinner iz_install_zstack
}

upgrade_zstack(){
    echo_title "Upgrade ${PRODUCT_NAME}"
    echo ""
    if [ -f $upgrade_folder/apache-cassandra* ]; then
        INSTALL_MONITOR='y'
    fi

    show_spinner uz_upgrade_zstack
    cd /
    show_spinner cs_add_cronjob
    show_spinner cs_enable_zstack_service

    if [ -z $ONLY_INSTALL_ZSTACK ]; then
        if [ ! -z $INSTALL_MONITOR ] ; then
            show_spinner iz_install_cassandra
            show_spinner sz_start_cassandra
            show_spinner iz_install_kairosdb
        fi
    
        if [ -z $NEED_KEEP_DB ];then
            if [ $CURRENT_STATUS = 'y' ]; then
                if [ -z $NOT_START_ZSTACK ]; then
                    if [ ! -z $INSTALL_MONITOR ] ; then
                        show_spinner sz_start_kairosdb
                    fi
                    show_spinner cs_config_zstack_properties
                    show_spinner sz_start_zstack
                fi
            fi
        fi
    
        if [ $UI_INSTALLATION_STATUS = 'y' ]; then
            if [ $UI_CURRENT_STATUS = 'y' ]; then
                echo "upgrade dashboard" >>$ZSTACK_INSTALL_LOG
                /etc/init.d/zstack-dashboard stop >>$ZSTACK_INSTALL_LOG 2>&1
                show_spinner sd_install_dashboard
                echo "start dashboard" >>$ZSTACK_INSTALL_LOG
                show_spinner sd_start_dashboard
            else
                echo "upgrade dashboard" >>$ZSTACK_INSTALL_LOG
                show_spinner sd_install_dashboard
            fi
        fi
    else
        if [ -z $NEED_KEEP_DB ];then
            if [ $CURRENT_STATUS = 'y' ]; then
                if [ -z $NOT_START_ZSTACK ]; then
                    show_spinner cs_config_zstack_properties
                    show_spinner sz_start_zstack
                fi
            fi
        fi
    fi
}

install_ansible(){
    echo_title "Install Ansible"
    echo ""
    if [ $OS = $CENTOS7 -o $OS = $CENTOS6 ]; then
        show_spinner ia_disable_selinux
        show_spinner ia_install_python_gcc_rh
        show_spinner ia_install_pip
        show_spinner ia_install_ansible
    elif [ $OS = $UBUNTU1404 ]; then
        export DEBIAN_FRONTEND=noninteractive
        show_spinner ia_update_apt
        show_spinner ia_install_python_gcc_db
        show_spinner ia_install_pip
        show_spinner ia_install_ansible
    fi
}

iz_install_unzip(){
    echo_subtitle "Install unzip"
    if [ $OS = $UBUNTU1404 ]; then
        apt-get -y install unzip >>$ZSTACK_INSTALL_LOG 2>&1
        [ $? -ne 0 ] && fail "Install unzip fail."
        pass
        return
    fi
    if [ $OS = $CENTOS6 ]; then
        rpm -ivh $unzip_el6_rpm >>$ZSTACK_INSTALL_LOG 2>&1
    else
        rpm -ivh $unzip_el7_rpm >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    [ $? -ne 0 ] && fail "Install unzip fail."
    pass
}

is_install_general_libs_rh(){
    echo_subtitle "Install General Libraries (takes a couple of minutes)"
    yum clean metadata >/dev/null 2>&1
    which mysql >/dev/null 2>&1
    if [ $? -eq 0 ];then
        mysql_pkg=''
    else
        mysql_pkg='mysql'
    fi
    if [ ! -z $ZSTACK_YUM_REPOS ]; then
        echo yum install --disablerepo="*" --enablerepo=$ZSTACK_YUM_REPOS -y general libs... >>$ZSTACK_INSTALL_LOG
        yum install --disablerepo="*" --enablerepo=$ZSTACK_YUM_REPOS -y \
            libselinux-python \
            java-1.7.0-openjdk \
            qemu-kvm \
            bridge-utils \
            wget \
            qemu-img \
            libvirt-python \
            libvirt \
            nfs-utils \
            rpcbind \
            vconfig \
            libvirt-client \
            python-devel \
            gcc \
            autoconf \
            iptables \
            tar \
            gzip \
            unzip \
            httpd \
            openssh \
            openssh-clients \
            openssh-server \
            sshpass \
            sudo \
            ntp \
            ntpdate \
            bzip2 \
            net-tools \
            $mysql_pkg \
            >>$ZSTACK_INSTALL_LOG 2>&1
    else
        echo "yum install -y libselinux-python java ..." >>$ZSTACK_INSTALL_LOG
        yum install -y \
            libselinux-python \
            java-1.7.0-openjdk \
            qemu-kvm \
            bridge-utils \
            wget \
            qemu-img \
            libvirt-python \
            libvirt \
            nfs-utils \
            rpcbind \
            vconfig \
            libvirt-client \
            python-devel \
            gcc \
            autoconf \
            iptables \
            tar \
            gzip \
            unzip \
            httpd \
            openssh \
            openssh-clients \
            openssh-server \
            sshpass \
            sudo \
            ntp \
            ntpdate \
            bzip2 \
            net-tools \
            $mysql_pkg \
            >>$ZSTACK_INSTALL_LOG 2>&1
    fi

    if [ $? -ne 0 ];then
        yum clean metadata >/dev/null 2>&1
        fail "install system libraries failed."
    else
        yum clean metadata >/dev/null 2>&1
        pass
    fi
}

is_install_virtualenv(){
    echo_subtitle "Install Virtualenv"
    if [ ! -z $DEBUG ]; then
        pip install -i $pypi_source_pip --trusted-host localhost --ignore-installed virtualenv
    else
        pip install -i $pypi_source_pip --trusted-host localhost --ignore-installed virtualenv >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    [ $? -ne 0 ] && fail "install virtualenv failed"
    pass
}

is_install_general_libs_deb(){
    echo_subtitle "Install General Libraries (takes a couple of minutes)"
    which mysql >/dev/null 2>&1
    if [ $? -eq 0 ];then
        mysql_pkg=''
    else
        mysql_pkg='mysql-client'
    fi
    apt-get -y install \
        openjdk-7-jdk \
        qemu-kvm \
        bridge-utils \
        wget \
        qemu-utils \
        python-libvirt \
        libvirt-bin \
        vlan \
        nfs-common \
        nfs-kernel-server \
        python-dev \
        gcc \
        autoconf \
        iptables \
        tar \
        gzip \
        unzip \
        apache2 \
        sshpass \
        sudo \
        ntp  \
        ntpdate \
        bzip2 \
        $mysql_pkg \
        >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "install virtualenv failed"
    pass
}

install_system_libs(){
    echo_title "Install System Libs"
    echo ""
    if [ $OS != $UBUNTU1404 ]; then
        show_spinner is_install_general_libs_rh
    else
        show_spinner is_install_general_libs_deb
    fi
    #mysql and rabbitmq will be installed by zstack-ctl later
    show_spinner is_install_virtualenv
    #enable ntpd
    show_spinner is_enable_ntpd
}

is_enable_ntpd(){
    echo_subtitle "Enable NTP"
    if [ $OS != $UBUNTU1404 ];then
        grep '^server 0.centos.pool.ntp.org' /etc/ntp.conf >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            echo "server 0.centos.pool.ntp.org iburst" >> /etc/ntp.conf
            echo "server 1.centos.pool.ntp.org iburst" >> /etc/ntp.conf
        fi
        chkconfig ntpd on >>$ZSTACK_INSTALL_LOG 2>&1
        service ntpd restart >>$ZSTACK_INSTALL_LOG 2>&1
    else
        grep '^server 0.ubuntu.pool.ntp.org' /etc/ntp.conf >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            echo "server 0.ubuntu.pool.ntp.org" >> /etc/ntp.conf
            echo "server ntp.ubuntu.com" >> /etc/ntp.conf
        fi
        update-rc.d ntp defaults >>$ZSTACK_INSTALL_LOG 2>&1
        service ntp restart >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    if [ $? -ne 0 ];then
        fail "failed to enable ntpd service."
    fi
    pass
}

iz_download_zstack(){
    echo_subtitle "Download ${PRODUCT_NAME} package"
    if [ -f $ZSTACK_ALL_IN_ONE ]; then
        cp $ZSTACK_ALL_IN_ONE $zstack_tmp_file >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ];then
           /bin/rm -f $zstack_tmp_file
           fail "failed to copy zstack all-in-one package from $ZSTACK_ALL_IN_ONE to $zstack_tmp_file"
        fi
    else
        which wget >/dev/null 2>&1 
        if [ $? -eq 0 ]; then
            wget -w 10 -O $zstack_tmp_file $ZSTACK_ALL_IN_ONE >>$ZSTACK_INSTALL_LOG 2>&1
        else
            which curl >/dev/null 2>&1 
            if [ $? -eq 0 ]; then
                curl -L $ZSTACK_ALL_IN_ONE -o $zstack_tmp_file >>$ZSTACK_INSTALL_LOG 2>&1
            else
                fail "need 'wget' or 'curl' to download zstack all in one package."
            fi 
        fi
        if [ $? -ne 0 ];then
           /bin/rm -f $zstack_tmp_file
           fail "failed to download zstack all-in-one package from $ZSTACK_ALL_IN_ONE"
        fi
    fi
    pass 
}

iz_unpack_zstack(){
    echo_subtitle "Unpack ${PRODUCT_NAME} package"
    if [ $UPGRADE = 'n' ]; then
        mkdir -p $ZSTACK_INSTALL_ROOT
        all_in_one=$ZSTACK_INSTALL_ROOT/zstack_all_in_one.tgz
        mv $zstack_tmp_file $all_in_one
        cd $ZSTACK_INSTALL_ROOT
        tar -zxf $all_in_one >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ];then
           fail "failed to unpack ${PRODUCT_NAME} package: $all_in_one."
        fi
    else
        all_in_one=$upgrade_folder/zstack_all_in_one.tgz
        mv $zstack_tmp_file $all_in_one
        cd $upgrade_folder
        tar -zxf $all_in_one >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ];then
            cd /; rm -rf $upgrade_folder 
            fail "failed to unpack ${PRODUCT_NAME} package: $all_in_one."
        fi
    fi
    pass
}

uz_upgrade_zstack(){
    echo_subtitle "Upgrade ${PRODUCT_NAME}"
    cd $upgrade_folder
    unzip -d zstack zstack.war >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
        cd /; rm -rf $upgrade_folder
        fail "failed to unzip zstack.war to $upgrade_folder/zstack"
    fi

    if [ ! -z $DEBUG ]; then
        bash zstack/WEB-INF/classes/tools/install.sh zstack-ctl 
    else
        bash zstack/WEB-INF/classes/tools/install.sh zstack-ctl >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    if [ $? -ne 0 ];then
        cd /; rm -rf $upgrade_folder
        fail "failed to upgrade zstack-ctl"
    fi

    zstack-ctl stop >>$ZSTACK_INSTALL_LOG 2>&1

    if [ -z $ONLY_INSTALL_ZSTACK ]; then
        if [ ! -z $DEBUG ]; then
            if [ $FORCE = 'n' ];then
                zstack-ctl upgrade_db --dry-run
            else
                zstack-ctl upgrade_db --dry-run --force
            fi
        else
            if [ $FORCE = 'n' ];then
                zstack-ctl upgrade_db --dry-run >>$ZSTACK_INSTALL_LOG 2>&1
            else
                zstack-ctl upgrade_db --dry-run --force >>$ZSTACK_INSTALL_LOG 2>&1
            fi
        fi
        if [ $? -ne 0 ];then
            cd /; rm -rf $upgrade_folder
            fail "Database upgrading dry-run failed. You probably should use -F option to do force upgrading."
        fi
    fi

    if [ ! -z $DEBUG ]; then
        bash zstack/WEB-INF/classes/tools/install.sh zstack-cli
    else
        bash zstack/WEB-INF/classes/tools/install.sh zstack-cli >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    if [ $? -ne 0 ];then
        cd /; rm -rf $upgrade_folder
        fail "failed to upgrade zstack-cli"
    fi

    if [ ! -z $DEBUG ]; then
        zstack-ctl upgrade_management_node --war-file $upgrade_folder/zstack.war 
    else
        zstack-ctl upgrade_management_node --war-file $upgrade_folder/zstack.war >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    if [ $? -ne 0 ];then
        cd /; rm -rf $upgrade_folder
        fail "failed to upgrade local management node"
    fi

    if [ -z $ONLY_INSTALL_ZSTACK ] ; then
        if [ -f $upgrade_folder/apache-cassandra* ]; then
            /bin/cp -f $upgrade_folder/apache-cassandra*.gz $ZSTACK_INSTALL_ROOT  >>$ZSTACK_INSTALL_LOG 2>&1
            /bin/cp -f $upgrade_folder/kairosdb*.gz $ZSTACK_INSTALL_ROOT  >>$ZSTACK_INSTALL_LOG 2>&1
        fi
    
        cd /; rm -rf $upgrade_folder
    
        if [ -z $NEED_KEEP_DB ];then
            if [ ! -z $DEBUG ]; then
                if [ $FORCE = 'n' ];then
                    zstack-ctl upgrade_db
                else
                    zstack-ctl upgrade_db --force
                fi
            else
                if [ $FORCE = 'n' ];then
                    zstack-ctl upgrade_db >>$ZSTACK_INSTALL_LOG 2>&1
                else
                    zstack-ctl upgrade_db --force >>$ZSTACK_INSTALL_LOG 2>&1
                fi
            fi
        fi 
    
        if [ $? -ne 0 ];then
            fail "failed to upgrade database"
        fi
        #reset rabbitmq, since rabbitmq queue was changed.
        echo "reset rabbitmq" >>$ZSTACK_INSTALL_LOG 2>&1
        rabbitmqctl stop_app  >>$ZSTACK_INSTALL_LOG 2>&1
        rabbitmqctl reset  >>$ZSTACK_INSTALL_LOG 2>&1
        rabbitmqctl start_app  >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ];then
            fail "failed to reset rabbitmq and start rabbitmq"
        fi
    fi

    pass
}

iz_unzip_tomcat(){
    echo_subtitle "Unpack Tomcat"
    cd $ZSTACK_INSTALL_ROOT
    unzip apache-tomcat*.zip >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
       fail "failed to unzip Tomcat package: $ZSTACK_INSTALL_ROOT/apache-tomcat*.zip."
    fi
    apache_temp=`mktemp`
    apache_zip=`ls apache-tomcat*.zip`
    mv $apache_zip $apache_temp
    ln -s apache-tomcat* apache-tomcat
    mv $apache_temp $apache_zip

    #delete unused web app folders 
    rm -rf $ZSTACK_INSTALL_ROOT/apache-tomcat/webapps/*

    chmod a+x apache-tomcat/bin/*
    if [ $? -ne 0 ];then
       fail "chmod failed in: $ZSTACK_INSTALL_ROOT/apache-tomcat/bin/*."
    fi

    pass
}

iz_install_zstack(){
    echo_subtitle "Install ${PRODUCT_NAME} into Tomcat"
    cd $ZSTACK_INSTALL_ROOT
    unzip -d $CATALINA_ZSTACK_PATH zstack.war >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
       fail "failed to install zstack.war to $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_PATH."
    fi
    ln -s $CATALINA_ZSTACK_PATH/VERSION $ZSTACK_INSTALL_ROOT/VERSION  
    pass
}

iz_install_zstackcli(){
    echo_subtitle "Install ${PRODUCT_NAME} Command Line Tool"
    cd $ZSTACK_INSTALL_ROOT
    bash $ZSTACK_TOOLS_INSTALLER zstack-cli >>$ZSTACK_INSTALL_LOG 2>&1

    if [ $? -ne 0 ];then
       fail "failed to install zstackcli in $ZSTACK_INSTALL_ROOT/$ZSTACK_TOOLS_INSTALLER"
    fi
    pass
}

iz_install_zstackctl(){
    echo_subtitle "Install ${PRODUCT_NAME} Control Tool"
    cd $ZSTACK_INSTALL_ROOT
    bash $ZSTACK_TOOLS_INSTALLER zstack-ctl >>$ZSTACK_INSTALL_LOG 2>&1

    if [ $? -ne 0 ];then
       fail "failed to install zstackctl in $ZSTACK_INSTALL_ROOT/$ZSTACK_TOOLS_INSTALLER"
    fi
    pass
}

iz_install_cassandra(){
    echo_subtitle "Install Cassandra"
    zstack-ctl cassandra --stop >>$ZSTACK_INSTALL_LOG 2>&1
    zstack-ctl install_cassandra "{\"rpc_address\":\"$MANAGEMENT_IP\", \"listen_address\":\"$MANAGEMENT_IP\"}" >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
       fail "failed to install Cassandra"
    fi
    pass
}

iz_install_kairosdb(){
    echo_subtitle "Install Kairosdb"
    zstack-ctl kairosdb --stop >>$ZSTACK_INSTALL_LOG 2>&1
    zstack-ctl install_kairosdb --listen-address $MANAGEMENT_IP  >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
       fail "failed to install Kairosdb"
    fi
    pass
}

install_zstack(){
    echo_title "Install ${PRODUCT_NAME} Tools"
    echo ""
    show_spinner iz_chown_install_root
    show_spinner iz_install_zstackcli
    show_spinner iz_install_zstackctl
    [ -z $ONLY_INSTALL_ZSTACK ] && show_spinner sd_install_dashboard

    #install license
    cd $ZSTACK_INSTALL_ROOT
    if [ -f $LICENSE_FILE ]; then
        zstack-ctl install_license --license $LICENSE_FILE >>$ZSTACK_INSTALL_LOG 2>&1
    fi

    [ -z $INSTALL_MONITOR ] && return
    show_spinner iz_install_cassandra
    #Do not deploy cassandra when only install zstack by option -i.
    # This is for HA deployment. 
    [ -z $ONLY_INSTALL_ZSTACK ] && show_spinner sz_start_cassandra
    show_spinner iz_install_kairosdb
}

install_db_msgbus(){
    echo_title "Install Database and Message Bus"
    echo ""
    #generate ssh key for install mysql and rabbitmq by ansible remote host
    ssh_tmp_dir=`mktemp`
    /bin/rm -rf $ssh_tmp_dir
    mkdir -p $ssh_tmp_dir
    show_spinner cs_gen_sshkey $ssh_tmp_dir
    #install mysql db
    show_spinner cs_install_mysql $ssh_tmp_dir
    #deploy initial database
    show_spinner cs_deploy_db
    #install rabbitmq server
    show_spinner cs_install_rabbitmq $ssh_tmp_dir
    cs_clean_ssh_tmp_key $ssh_tmp_dir
    #show_spinner cs_start_rabbitmq
}

config_system(){
    echo_title "Configure System"
    echo ""
    #show_spinner cs_flush_iptables
    show_spinner cs_config_zstack_properties
    show_spinner cs_config_generate_ssh_key
    show_spinner cs_config_tomcat
    show_spinner cs_install_zstack_service
    show_spinner cs_enable_zstack_service
    show_spinner cs_add_cronjob
    if [ ! -z $NEED_NFS ];then
        show_spinner cs_setup_nfs
    fi
    if [ ! -z $NEED_HTTP ];then
        show_spinner cs_setup_http
    fi
    do_enable_sudo
}

cs_add_cronjob(){
    echo_subtitle "Add cronjob to clean logs"
    cat >/etc/cron.daily/zstack_archive_logs.sh <<EOF
#!/bin/bash
zstack_home=\`zstack-ctl status|grep ZSTACK_HOME|awk '{print \$2}'\`
mn_log_folder=\$zstack_home/../../logs/

[ ! -d \$mn_log_folder ] && exit 0

target_file="localhost_access_log*.txt management-server*.log catalina*.log localhost*.log"
for file in \$target_file; do
    cd \$mn_log_folder
    find \$file -mtime +1 -exec gzip {} \;
done
EOF
    chmod a+x /etc/cron.daily/zstack_archive_logs.sh

    crontab -l 2>/dev/null |grep 'zstack-ctl dump_mysql' >/dev/null
    if [ $? -ne 0 ]; then
        crontab <<EOF
`crontab -l 2>/dev/null`
30 0,12 * * * zstack-ctl dump_mysql --keep-amount 14
EOF
    fi

    pass
}

cs_config_zstack_properties(){
    echo_subtitle "Config zstack.properties"
    if [ ! -z $ZSTACK_YUM_REPOS ];then
        zstack-ctl configure Ansible.var.yum_repo=$ZSTACK_YUM_REPOS
    fi
    if [ $? -ne 0 ];then
        fail "failed to add yum repo to $ZSTACK_PROPERTIES"
    fi
    pass
}

cs_config_generate_ssh_key(){
    echo_subtitle "Generate Local Ssh keys"
    #generate local ssh key
    rsa_key_folder=${ZSTACK_INSTALL_ROOT}/${CATALINA_ZSTACK_CLASSES}/ansible/rsaKeys
    /bin/rm -f ${rsa_key_folder}/*
    ssh-keygen -f ${rsa_key_folder}/id_rsa -N '' -q >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
        fail "failed to generate local ssh keys in ${rsa_key_folder}"
    fi
    chown -R zstack.zstack ${rsa_key_folder}
    pass
}

iz_chown_install_root(){
    echo_subtitle "Change Owner in ${PRODUCT_NAME}"
    chown -R zstack.zstack $ZSTACK_INSTALL_ROOT >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
        fail "failed to chown for $ZSTACK_INSTALL_ROOT with zstack.zstack"
    fi
    pass
}

cs_gen_sshkey(){
    echo_subtitle "Generate Temp SSH Key"
    [ ! -d /root/.ssh ] && mkdir -p /root/.ssh && chmod 700 /root/.ssh
    
    dsa_key_file=$1/id_dsa
    dsa_pub_key_file=$1/id_dsa.pub
    authorized_keys_file=/root/.ssh/authorized_keys
    ssh-keygen -t dsa -N '' -f $dsa_key_file >>$ZSTACK_INSTALL_LOG 2>&1 
    if [ ! -f $authorized_keys_file ]; then
        cat $dsa_pub_key_file > $authorized_keys_file
        chmod 600 $authorized_keys_file
    else
        ssh_pub_key=`cat $dsa_pub_key_file`
        grep $ssh_pub_key $authorized_keys_file >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            cat $dsa_pub_key_file >> $authorized_keys_file
        fi
    fi
    if [ -x /sbin/restorecon ]; then
        /sbin/restorecon /root/.ssh /root/.ssh/authorized_keys >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    pass
}

cs_install_mysql(){
    echo_subtitle "Install Mysql Server"
    dsa_key_file=$1/id_dsa
    if [ -z $ZSTACK_YUM_REPOS ];then
        if [ -z $MYSQL_ROOT_PASSWORD ]; then
            zstack-ctl install_db --host=$MANAGEMENT_IP --ssh-key=$dsa_key_file --root-password="$MYSQL_NEW_ROOT_PASSWORD" --debug >>$ZSTACK_INSTALL_LOG 2>&1
        else
            zstack-ctl install_db --host=$MANAGEMENT_IP --login-password="$MYSQL_ROOT_PASSWORD" --root-password="$MYSQL_NEW_ROOT_PASSWORD" --ssh-key=$dsa_key_file --debug >>$ZSTACK_INSTALL_LOG 2>&1
        fi
    else
        if [ -z $MYSQL_ROOT_PASSWORD ]; then
            zstack-ctl install_db --host=$MANAGEMENT_IP --ssh-key=$dsa_key_file --yum=$ZSTACK_YUM_REPOS --root-password="$MYSQL_NEW_ROOT_PASSWORD" >>$ZSTACK_INSTALL_LOG --debug 2>&1
        else
            zstack-ctl install_db --host=$MANAGEMENT_IP --login-password="$MYSQL_ROOT_PASSWORD" --root-password="$MYSQL_NEW_ROOT_PASSWORD" --ssh-key=$dsa_key_file --yum=$ZSTACK_YUM_REPOS --debug >>$ZSTACK_INSTALL_LOG 2>&1
        fi
    fi
    if [ $? -ne 0 ];then
        cs_clean_ssh_tmp_key $1
        fail "failed to install mysql server."
    fi
    pass
}

cs_install_rabbitmq(){
    echo_subtitle "Install Rabbitmq Server"
    dsa_key_file=$1/id_dsa
    if [ -z $ZSTACK_YUM_REPOS ];then
        echo "zstack-ctl install_rabbitmq --host=$MANAGEMENT_IP --ssh-key=$dsa_key_file" >>$ZSTACK_INSTALL_LOG
        zstack-ctl install_rabbitmq --host=$MANAGEMENT_IP --ssh-key=$dsa_key_file --debug >>$ZSTACK_INSTALL_LOG 2>&1
    else
        echo "zstack-ctl install_rabbitmq --host=$MANAGEMENT_IP --ssh-key=$dsa_key_file --yum=$ZSTACK_YUM_REPOS" >>$ZSTACK_INSTALL_LOG
        zstack-ctl install_rabbitmq --host=$MANAGEMENT_IP --ssh-key=$dsa_key_file --yum=$ZSTACK_YUM_REPOS --debug >>$ZSTACK_INSTALL_LOG 2>&1
    fi

    if [ $? -ne 0 ];then
        cs_clean_ssh_tmp_key $1
        fail "failed to install rabbitmq server."
    fi
    pass
}

cs_clean_ssh_tmp_key(){
    #echo_subtitle "Clean up ssh temp key"
    dsa_pub_key_file=$1/id_dsa.pub
    ssh_pub_key=`cat $dsa_pub_key_file`
    authorized_keys_file=/root/.ssh/authorized_keys
    sed -i "\;$ssh_pub_key;d" $authorized_keys_file >>$ZSTACK_INSTALL_LOG 2>&1
    /bin/rm -rf $1
    #pass
}

ia_disable_selinux(){
    echo_subtitle "Disable SELinux"
    which setenforce >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -eq 0 ];then
        setenforce 0 >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ]; then
            setenforce 0 2>&1 |grep -i 'selinux is disabled' >>$ZSTACK_INSTALL_LOG 2>&1
            [ $? -ne 0 ] && fail "failed to disable selinux."
        fi

        if [ -f /etc/sysconfig/selinux ]; then
            sed -i 's/SELINUX=enforcing/SELINUX=disabled/' /etc/sysconfig/selinux >>$ZSTACK_INSTALL_LOG 2>&1
        fi
        [ $? -ne 0 ] && fail "failed to modify selinux config file: /etc/sysconfig/selinux"
    fi
    pass
}

cs_flush_iptables(){
    echo_subtitle "Flush iptables rules"
    iptables -F
    iptables -F -t nat
    [ $? -ne 0 ] && fail "disable iptables failed"
    pass
}

cs_config_tomcat(){
    echo_subtitle "Configure Tomcat Java Option"
    cat >> $ZSTACK_INSTALL_ROOT/apache-tomcat/bin/setenv.sh <<EOF
export CATALINA_OPTS=" -Djava.net.preferIPv4Stack=true -Dcom.sun.management.jmxremote=true -Djava.security.egd=file:/dev/./urandom"
EOF
    pass
}

cs_install_zstack_service(){
    echo_subtitle "Install ${PRODUCT_NAME} management node"
    /bin/cp -f $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_CLASSES/install/zstack-server /etc/init.d
    chmod a+x /etc/init.d/zstack-server
    tomcat_folder_path=$ZSTACK_INSTALL_ROOT/apache-tomcat
    sed -i "s#^TOMCAT_PATH=.*#TOMCAT_PATH=$tomcat_folder_path#" /etc/init.d/zstack-server
    [ $? -ne 0 ] && fail "failed to install ${PRODUCT_NAME} management node."
    zstack-ctl setenv ZSTACK_HOME=$ZSTACK_HOME >> $ZSTACK_INSTALL_LOG 2>&1 
    [ $? -ne 0 ] && fail "failed to set ZSTACK_HOME path by zstack-ctl"
    pass
}

cs_enable_zstack_service(){
    echo_subtitle "Enable ${PRODUCT_NAME} bootstrap service"
    if [ -f /bin/systemctl ]; then
        cat > /etc/systemd/system/zstack.service <<EOF
[Unit]
Description=zstack Service
After=syslog.target network.target
Before=shutdown.target reboot.target halt.target

[Service]
Type=forking
User=root
ExecStart=/usr/bin/zstack-ctl start --daemon
ExecStop=/usr/bin/zstack-ctl stop
Restart=on-abort
RemainAfterExit=Yes
TimeoutStartSec=300
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
        systemctl enable zstack.service  >> $ZSTACK_INSTALL_LOG 2>&1
    fi
    pass
}

cs_setup_nfs(){
    echo_subtitle "Configure Local NFS Server"
    mkdir -p $NFS_FOLDER
    grep $NFS_FOLDER /etc/exports >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ]; then 
        echo "$NFS_FOLDER *(rw,sync,no_root_squash)" >> /etc/exports
    fi
    if [ $OS = $CENTOS6 ]; then
        chkconfig nfs on >>$ZSTACK_INSTALL_LOG 2>&1
        chkconfig rpcbind on >>$ZSTACK_INSTALL_LOG 2>&1
        service rpcbind restart >>$ZSTACK_INSTALL_LOG 2>&1
        service nfs restart >>$ZSTACK_INSTALL_LOG 2>&1
    elif [ $OS = $CENTOS7 ]; then
        systemctl enable rpcbind >>$ZSTACK_INSTALL_LOG 2>&1
        systemctl enable nfs-server >>$ZSTACK_INSTALL_LOG 2>&1
        systemctl enable nfs-lock >>$ZSTACK_INSTALL_LOG 2>&1
        systemctl enable nfs-idmap >>$ZSTACK_INSTALL_LOG 2>&1
        systemctl restart rpcbind >>$ZSTACK_INSTALL_LOG 2>&1
        systemctl restart nfs-server >>$ZSTACK_INSTALL_LOG 2>&1
        systemctl restart nfs-lock >>$ZSTACK_INSTALL_LOG 2>&1
        systemctl restart nfs-idmap >>$ZSTACK_INSTALL_LOG 2>&1
    else
        service nfs-kernel-server restart >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    [ $? -ne 0 ] && fail "failed to setup NFS server"
    iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 111 -j ACCEPT" > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        iptables -I INPUT -p tcp -m tcp --dport 111 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
        iptables -I INPUT -p udp -m udp --dport 111 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
        iptables -I INPUT -p tcp -m tcp --dport 2049 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
        iptables -I INPUT -p tcp -m tcp --dport 32803  -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
        iptables -I INPUT -p udp -m udp --dport 32769 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
        iptables -I INPUT -p tcp -m tcp --dport 892 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
        iptables -I INPUT -p udp -m udp --dport 892 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
        iptables -I INPUT -p tcp -m tcp --dport 875 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
        iptables -I INPUT -p udp -m udp --dport 875 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
        iptables -I INPUT -p tcp -m tcp --dport 662 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
        iptables -I INPUT -p udp -m udp --dport 662 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    pass
}

cs_setup_http(){
    echo_subtitle "Configure Local HTTP Server"
    mkdir $HTTP_FOLDER
    chmod 777 $HTTP_FOLDER
    chmod o+x $ZSTACK_INSTALL_ROOT
    if [ $OS = $CENTOS7 ]; then
        chkconfig httpd on >>$ZSTACK_INSTALL_LOG 2>&1
        cat > /etc/httpd/conf.d/zstack-http.conf <<EOF
Alias /image/ "$HTTP_FOLDER/"
<Directory $HTTP_FOLDER/>
    AllowOverride FileInfo AuthConfig Limit
    Options MultiViews Indexes SymLinksIfOwnerMatch IncludesNoExec
    Allow from all
    Require all granted
</Directory>
EOF
        service httpd restart >>$ZSTACK_INSTALL_LOG 2>&1
    elif [ $OS = $CENTOS6 ]; then
        chkconfig httpd on >>$ZSTACK_INSTALL_LOG 2>&1
        cat > /etc/httpd/conf.d/zstack-http.conf <<EOF
Alias /image/ "$HTTP_FOLDER/"
<Directory $HTTP_FOLDER/>
    AllowOverride FileInfo AuthConfig Limit
    Options MultiViews Indexes SymLinksIfOwnerMatch IncludesNoExec
    Allow from all
</Directory>
EOF
        service httpd restart >>$ZSTACK_INSTALL_LOG 2>&1
    else
        cat > /etc/apache2/conf-enabled/zstack-http.conf <<EOF
Alias /image/ "$HTTP_FOLDER/"
<Directory $HTTP_FOLDER/>
    AllowOverride FileInfo AuthConfig Limit
    Options MultiViews Indexes SymLinksIfOwnerMatch IncludesNoExec
    Allow from all
    AllowOverride None
    Options None
    Require all granted
</Directory>
EOF
        /etc/init.d/apache2 restart >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    [ $? -ne 0 ] && fail "failed to setup HTTP Server"
    iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 80 -j ACCEPT" > /dev/null 2>&1 || iptables -I INPUT -p tcp -m tcp --dport 80 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
    pass
}

check_zstack_server(){
    curl --noproxy -H "Content-Type: application/json" -d '{"org.zstack.header.apimediator.APIIsReadyToGoMsg": {}}' http://localhost:8080/zstack/api >>$ZSTACK_INSTALL_LOG 2>&1
    return $?
}

sz_start_cassandra(){
    echo_subtitle "Start Cassandra"
    zstack-ctl cassandra --stop >>$ZSTACK_INSTALL_LOG 2>&1
    zstack-ctl cassandra --start --wait-timeout=180 >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
       fail "failed to start Cassandra"
    fi
    #zstack-ctl deploy_cassandra_db  >>$ZSTACK_INSTALL_LOG 2>&1
    #if [ $? -ne 0 ];then
    #   fail "failed to deploy Cassandra db"
    #fi
    pass
}

sz_start_kairosdb(){
    echo_subtitle "Start Kairosdb"
    zstack-ctl kairosdb --stop >>$ZSTACK_INSTALL_LOG 2>&1
    zstack-ctl kairosdb --start --wait-timeout=60 >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
       fail "failed to start Kairosdb"
    fi
    pass
}

start_monitor(){
    echo_title "Start Monitor"
    echo ""
    show_spinner sz_start_kairosdb
}

start_zstack(){
    echo_title "Start ${PRODUCT_NAME} Server"
    echo ""
    show_spinner sz_start_zstack
}

cs_deploy_db(){
    echo_subtitle "Initialize Database"
    if [ -z $NEED_DROP_DB ]; then
        if [ -z $NEED_KEEP_DB ]; then
            zstack-ctl deploydb --root-password="$MYSQL_NEW_ROOT_PASSWORD" --zstack-password="$MYSQL_USER_PASSWORD" --host=$MANAGEMENT_IP >>$ZSTACKCTL_INSTALL_LOG 2>&1
        else
            zstack-ctl deploydb --root-password="$MYSQL_NEW_ROOT_PASSWORD" --zstack-password="$MYSQL_USER_PASSWORD" --host=$MANAGEMENT_IP --keep-db >>$ZSTACKCTL_INSTALL_LOG 2>&1
        fi
    else
        zstack-ctl deploydb --root-password="$MYSQL_NEW_ROOT_PASSWORD" --zstack-password="$MYSQL_USER_PASSWORD" --host=$MANAGEMENT_IP --drop >>$ZSTACKCTL_INSTALL_LOG 2>&1
    fi
    if [ $? -ne 0 ];then
        grep 'detected existing zstack database' $ZSTACKCTL_INSTALL_LOG >& /dev/null
        if [ $? -eq 0 ]; then
            cat $ZSTACKCTL_INSTALL_LOG >> $ZSTACK_INSTALL_LOG
            fail "failed to deploy ${PRODUCT_NAME} database. You might want to add -D to drop previous ${PRODUCT_NAME} database or -k to keep previous zstack database"
        else
            cat $ZSTACKCTL_INSTALL_LOG >> $ZSTACK_INSTALL_LOG
            fail "failed to deploy ${PRODUCT_NAME} database. Please check mysql accessbility. If your mysql has set root password, please add parameter -PMYSQL_PASSWORD to rerun the installation."
        fi
    fi

    cat $ZSTACKCTL_INSTALL_LOG >> $ZSTACK_INSTALL_LOG
    pass
}

sz_start_zstack(){
    echo_subtitle "Start ${PRODUCT_NAME} management node (takes a couple of minutes)"
    zstack-ctl stop_node -f >>$ZSTACK_INSTALL_LOG 2>&1
    zstack-ctl start_node --timeout=$ZSTACK_START_TIMEOUT >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "failed to start zstack"
    i=1
    while [ $i -lt 120 ]; do
        i=`expr $i + 1`
        check_zstack_server && pass && return
        sleep 1
    done
    fail "zstack server failed to start in $i seconds"
}

start_dashboard(){
    echo_title "Start ${PRODUCT_NAME} Web UI"
    echo ""
    #show_spinner sd_install_dashboard_libs
    #make sure current folder is existed to avoid of possible dashboard start failure. 
    cd /
    show_spinner sd_start_dashboard
}

sd_install_dashboard(){
    echo_subtitle "Install ${PRODUCT_NAME} Web UI (takes a couple of minutes)"
    zstack-ctl install_ui >>$ZSTACK_INSTALL_LOG 2>&1

    if [ $? -ne 0 ];then
        fail "failed to install zstack-dashboard in $ZSTACK_INSTALL_ROOT"
    fi
    pass
}

sd_start_dashboard(){
    echo_subtitle "Start ${PRODUCT_NAME} Dashboard"
    chmod a+x /etc/init.d/zstack-dashboard
    cd /
    /etc/init.d/zstack-dashboard restart >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "failed to zstack dashboard start"
    pass
}

#create zstack log yum repo
create_yum_repo(){
    cat > $zstack_163_repo_file << EOF
#163 base
[163base]
name=CentOS-\$releasever - Base - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/\$releasever/os/\$basearch/
#mirrorlist=http://mirrorlist.centos.org/?release=\$releasever&arch=\$basearch&repo=os
gpgcheck=0
enabled=0
gpgkey=http://mirrors.163.com/centos/RPM-GPG-KEY-CentOS-\$releasever
 
#released updates 
[163updates]
name=CentOS-\$releasever - Updates - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/\$releasever/updates/\$basearch/
#mirrorlist=http://mirrorlist.centos.org/?release=\$releasever&arch=\$basearch&repo=updates
enabled=0
gpgcheck=0
gpgkey=http://mirrors.163.com/centos/RPM-GPG-KEY-CentOS-\$releasever
 
#additional packages that may be useful
[163extras]
name=CentOS-\$releasever - Extras - mirrors.163.com
failovermethod=priority
baseurl=http://mirrors.163.com/centos/\$releasever/extras/\$basearch/
#mirrorlist=http://mirrorlist.centos.org/?release=\$releasever&arch=\$basearch&repo=extras
enabled=0
gpgcheck=0
gpgkey=http://mirrors.163.com/centos/RPM-GPG-KEY-CentOS-\$releasever
 
[ustcepel]
name=Extra Packages for Enterprise Linux \$releasever - \$basearce - USTC EPEL
baseurl=http://centos.ustc.edu.cn/epel/\$releasever/\$basearch
#mirrorlist=https://mirrors.fedoraproject.org/met163nk?repo=epel-7&arch=\$basearch
failovermethod=priority
enabled=0
gpgcheck=0
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL-\$releasever
EOF

    cat > $zstack_ali_repo_file << EOF
#aliyun base
[alibase]
name=CentOS-\$releasever - Base - mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/\$releasever/os/\$basearch/
#mirrorlist=http://mirrorlist.centos.org/?release=\$releasever&arch=\$basearch&repo=os
gpgcheck=0
enabled=0
gpgkey=http://mirrors.aliyun.com/centos/RPM-GPG-KEY-CentOS-\$releasever
 
#released updates 
[aliupdates]
name=CentOS-\$releasever - Updates - mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/\$releasever/updates/\$basearch/
#mirrorlist=http://mirrorlist.centos.org/?release=\$releasever&arch=\$basearch&repo=updates
enabled=0
gpgcheck=0
gpgkey=http://mirrors.aliyun.com/centos/RPM-GPG-KEY-CentOS-\$releasever
 
#additional packages that may be useful
[aliextras]
name=CentOS-\$releasever - Extras - mirrors.aliyun.com
failovermethod=priority
baseurl=http://mirrors.aliyun.com/centos/\$releasever/extras/\$basearch/
#mirrorlist=http://mirrorlist.centos.org/?release=\$releasever&arch=\$basearch&repo=extras
enabled=0
gpgcheck=0
gpgkey=http://mirrors.aliyun.com/centos/RPM-GPG-KEY-CentOS-\$releasever
 
[aliepel]
name=Extra Packages for Enterprise Linux \$releasever - \$basearce - mirrors.aliyun.com
baseurl=http://mirrors.aliyun.com/epel/\$releasever/\$basearch
#mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-7&arch=\$basearch
failovermethod=priority
enabled=0
gpgcheck=0
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-EPEL-\$releasever
EOF

}


help (){
    echo "
${PRODUCT_NAME} Installer.

The script can install ${PRODUCT_NAME} related software.

Warning: This script will disable SELinux on RedHat series OS (CentOS/Redhat RHEL)

Usage: $0 [options]

Options:
  -a    equal to -nHD

  -d    print detailed installation log to screen
        By default the installation log will be saved to $ZSTACK_INSTALL_LOG

  -D    drop previous ${PRODUCT_NAME} database if it exists. An error will be raised
        if a previous ${PRODUCT_NAME} database is detected and no -D or -k option is provided.

  -f LOCAL_PATH_OR_URL_OF_ZSTACK_ALL_IN_ONE_PACKAGE
        file path to ${PRODUCT_NAME} all-in-one package. By default the script
        will download the all-in-one package from ${PRODUCT_NAME} official website.
        You can provide a local file path or a URL with option if you want to
        use a separate all-in-one package.

  -F    force upgrade management node mysql database. This option is only valid
        when using -u option. It will send --force parameter to 
        zstack-ctl upgrade_db

  -h    show help message

  -H IMAGE_FOLDER_PATH   
        setup an Apache HTTP server and use IMAGE_FOLDER_PATH as url:
        http://CURRENT_MACHINE_IP/image/ . Doesn't effect when use -u to upgrade
        zstack or -l to install some system libs. 

  -i    only install ${PRODUCT_NAME} management node and dependent packages

  -I MANAGEMENT_NODE_NETWORK_INTERFACE | MANAGEMENT_NODE_IP_ADDRESS
        e.g. -I eth0, -I eth0:1, -I 192.168.0.1
        the network interface (e.g. eth0) or IP address for management network.
        The IP address of this interface will be configured as IP of MySQL 
        server and RabbitMQ server, if they are installed on this machine.
        Remote ${PRODUCT_NAME} managemet nodes will use this IP to access MySQL and 
        RabbitMQ. By default, the installer script will grab the IP of 
        interface providing default routing from routing table. 
        If multiple IP addresses share same net device, e.g. em1, em1:1, em1:2.
        The network interface should be the exact name, like -I em1:1

  -k    keep previous zstack DB if it exists. If using -k with -u, will not upgrade database not start management node.

  -l    only just install ${PRODUCT_NAME} dependent libraries

  -m    install monitor. Depends on monitor capability in package.

  -n NFS_PATH
        setup a NFS server and export the NFS path. Doesn't effect when use -u 
        to upgrade zstack or -l to install some system libs. 

  -o    offline installation. ${PRODUCT_NAME} required system libs will installed from zstack local repository, which is installed from ZStack customed ISO. ZStack customed ISO could be got from ZStack community.

  -p MYSQL_PASSWORD
        password for MySQL user 'zstack' that is the user ${PRODUCT_NAME} management nodes use to access database. By default, an empty password is applied.

  -P MYSQL_PASSWORD
        password for MySQL root user. By default, an empty password is applied.

  -q    quiet installation. Installation will try to fix the system configuration issue, rather than quit installation process.

  -r ZSTACK_INSTALLATION_PATH
        the path where to install ${PRODUCT_NAME} management node.  The default path is $ZSTACK_INSTALL_ROOT

  -R ZSTACK_YUM_MIRROR
        which yum mirror user want to use to install ZStack required CentOS rpm packages. User can choose 163 or aliyun, like -R aliyun, -R 163 

  -t ZSTACK_START_TIMEOUT
        The timeout for waiting ZStack start. The default value is $ZSTACK_START_TIMEOUT

  -u    Upgrade zstack management node and database. Make sure to backup your database, before executing upgrade command: mysqldump -u root -proot_password --host mysql_ip --port mysql_port zstack > path_to_db_dump.sql

  -z    Only install ZStack, without start ZStack management node.
------------
Example:

Following command will install the ${PRODUCT_NAME} management node to /usr/local/zstack and all dependent packages:

. Apache Tomcat 7 with zstack.war deployed
. ${PRODUCT_NAME} web UI
. ${PRODUCT_NAME} command line tool (zstack-cli)
. ${PRODUCT_NAME} control tool (zstack-ctl)
. MySQL
. RabbitMQ server
. NFS server
. Apache HTTP server

And an empty password is set to the root user of MySQL.

# $0 -a

--

In addition to all above results, below command sets MySQL user 'zstack' password to DB_ZSTACK_PASSWORD by using the MySQL 'root' user password DB_ROOT_PASSWORD
, and uses the IP of eth1 for deploying MySQL and RabbitMQ.

# $0 -r /home/zstack -a -P DB_ROOT_PASSWORD -p DB_ZSTACK_PASSWORD -I eth1

--

Following command only installs ${PRODUCT_NAME} management node and dependent software.

# $0 -i

--

Following command only installs ${PRODUCT_NAME} management node and monitor.

# $0 -m

--

Following command installs ${PRODUCT_NAME} management node and monitor. It will use aliyun yum mirror source.

# $0 -m -R aliyun

--

Following command installs ${PRODUCT_NAME} management node and monitor. It will use aliyun yum mirror source. It will also use quiet installation to try to fix system configuration issue. 

# $0 -m -R aliyun -q

------------
"
    exit 1
}

OPTIND=1
while getopts "f:H:I:n:p:P:r:R:t:y:adDFhiklmNoquz" Option
do
    case $Option in
        a ) NEED_NFS='y' && NEED_HTTP='y' && YUM_ONLINE_REPO='y';;
        d ) DEBUG='y';;
        D ) NEED_DROP_DB='y';;
        H ) NEED_HTTP='y' && HTTP_FOLDER=$OPTARG;;
        f ) ZSTACK_ALL_IN_ONE=$OPTARG;;
        F ) FORCE='y';;
        i ) ONLY_INSTALL_ZSTACK='y' && NEED_NFS='' && NEED_HTTP='' ;;
        I ) MANAGEMENT_INTERFACE=$OPTARG && NEED_SET_MN_IP='y';;
        k ) NEED_KEEP_DB='y';;
        l ) ONLY_INSTALL_LIBS='y';;
        m ) INSTALL_MONITOR='y';;
        n ) NEED_NFS='y' && NFS_FOLDER=$OPTARG;;
        o ) YUM_ONLINE_REPO='' && [ "zstack.org" = "$WEBSITE" ] && WEBSITE='localhost';; #do not use yum online repo.
        P ) MYSQL_ROOT_PASSWORD=$OPTARG && MYSQL_NEW_ROOT_PASSWORD=$OPTARG;;
        p ) MYSQL_USER_PASSWORD=$OPTARG;;
        q ) QUIET_INSTALLATION='y';;
        r ) ZSTACK_INSTALL_ROOT=$OPTARG;;
        R ) ZSTACK_YUM_MIRROR=$OPTARG && YUM_ONLINE_REPO='';;
        t ) ZSTACK_START_TIMEOUT=$OPTARG;;
        u ) UPGRADE='y';;
        y ) HTTP_PROXY=$OPTARG;;
        z ) NOT_START_ZSTACK='y';;
        * ) help;;
    esac
done
OPTIND=1

if [ ! -z $ZSTACK_YUM_MIRROR ]; then
    if [ "$ZSTACK_YUM_MIRROR" != "$YUM_MIRROR_163" -a "$ZSTACK_YUM_MIRROR" != "$YUM_MIRROR_ALIYUN" ]; then
        echo -e "\n\tYou want to use yum mirror from '$ZSTACK_YUM_MIRROR' . But we only support yum mirrors for '$YUM_MIRROR_163' or '$YUM_MIRROR_ALIYUN'. Please fix it and rerun the installation.\n\n"
        exit 1
    fi
    if [ $ZSTACK_YUM_MIRROR = $YUM_MIRROR_163 ]; then
        ZSTACK_YUM_REPOS=$MIRROR_163_YUM_REPOS
    else
        ZSTACK_YUM_REPOS=$MIRROR_ALI_YUM_REPOS
    fi
else
    if [ -z $YUM_ONLINE_REPO ]; then
        ZSTACK_YUM_REPOS=$ZSTACK_LOCAL_YUM_REPOS
    fi
fi

README=$ZSTACK_INSTALL_ROOT/readme

echo "${PRODUCT_NAME} installation root path: $ZSTACK_INSTALL_ROOT" >>$ZSTACK_INSTALL_LOG
[ -z $NFS_FOLDER ] && NFS_FOLDER=$ZSTACK_INSTALL_ROOT/nfs_root
echo "NFS Folder: $NFS_FOLDER" >> $ZSTACK_INSTALL_LOG
[ -z $HTTP_FOLDER ] && HTTP_FOLDER=$ZSTACK_INSTALL_ROOT/http_root
echo "HTTP Folder: $HTTP_FOLDER" >> $ZSTACK_INSTALL_LOG

pypi_source_easy_install="file://${ZSTACK_INSTALL_ROOT}/apache-tomcat/webapps/zstack/static/pypi/simple"
pypi_source_pip="file://${ZSTACK_INSTALL_ROOT}/apache-tomcat/webapps/zstack/static/pypi/simple"
unzip_el7_rpm="${ZSTACK_INSTALL_ROOT}/libs/unzip*el7*.rpm"
unzip_el6_rpm="${ZSTACK_INSTALL_ROOT}/libs/unzip*el6*.rpm"

if [ -z $MANAGEMENT_INTERFACE ]; then
    echo "Cannot not identify default network interface. Please set management
   node IP address by '-I MANAGEMENT_NODE_IP_ADDRESS'."
    exit 1
fi

ip addr show $MANAGEMENT_INTERFACE >/dev/null 2>&1
if [ $? -ne 0 ];then
    ip addr show |grep $MANAGEMENT_INTERFACE |grep inet >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "$MANAGEMENT_INTERFACE is not a recognized IP address or network interface name. Please assign correct IP address by '-I MANAGEMENT_NODE_IP_ADDRESS'" 
        exit 1
    fi
    MANAGEMENT_IP=$MANAGEMENT_INTERFACE
else
    MANAGEMENT_IP=`ip -4 addr show ${MANAGEMENT_INTERFACE} | grep inet | head -1 | awk '{print $2}' | cut -f1  -d'/'`
    echo "Management node network interface: $MANAGEMENT_INTERFACE" >> $ZSTACK_INSTALL_LOG
fi

echo "Management ip address: $MANAGEMENT_IP" >> $ZSTACK_INSTALL_LOG

#If user didn't assign mysql root password, then check original zstack mysql password status
if [ -z $MYSQL_ROOT_PASSWORD ] && [ -z $ONLY_INSTALL_ZSTACK ]; then
    which mysql >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        #check if mysql server is running
        ps -aef|grep mysqld |grep -v grep >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            mysql -u root --password='' -e 'exit' >/dev/null 2>&1
            if [ $? -ne 0 ]; then
                mysql -u root --password=$MYSQL_NEW_ROOT_PASSWORD -e 'exit' >/dev/null 2>&1
                if [ $? -ne 0 ]; then
                    if [ -z $QUIET_INSTALLATION ]; then
                        echo ""
                        echo "Cannot not login mysql!
 If you have mysql root password, please add option '-P MYSQL_ROOT_PASSWORD'.
 If you do not set mysql root password or mysql server is not started up, please add option '-q' and try again."
                        echo ""
                        exit 1
                    fi
                else
                    MYSQL_ROOT_PASSWORD=$MYSQL_NEW_ROOT_PASSWORD
                fi
            fi
        fi
    fi
fi

#Set ZSTACK_HOME for zstack-ctl.
export ZSTACK_HOME=$ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_PATH

if [ -f $PRODUCT_TITLE_FILE ]; then
    cat $PRODUCT_TITLE_FILE
else
echo ""
echo_star_line
echo ' _________ _____  _    ____ _  __'
echo '|__  / ___|_   _|/ \  / ___| |/ /'
echo "  / /\___ \ | | / _ \| |   | ' / "
echo ' / /_ ___) || |/ ___ \ |___| . \ '
echo '/____|____/ |_/_/   \_\____|_|\_\'
echo '                                 '
sleep 0.1
echo '    _    _     _       ___ _   _    ___  _   _ _____ '
echo '   / \  | |   | |     |_ _| \ | |  / _ \| \ | | ____|'
echo '  / _ \ | |   | |      | ||  \| | | | | |  \| |  _|  '
echo ' / ___ \| |___| |___   | || |\  | | |_| | |\  | |___ '
echo '/_/   \_\_____|_____| |___|_| \_|  \___/|_| \_|_____|'
echo '                                                     '
sleep 0.3
echo ' ___ _   _ ____ _____  _    _     _        _  _____ ___ ___  _   _ '
echo '|_ _| \ | / ___|_   _|/ \  | |   | |      / \|_   _|_ _/ _ \| \ | |'
echo ' | ||  \| \___ \ | | / _ \ | |   | |     / _ \ | |  | | | | |  \| |'
echo ' | || |\  |___) || |/ ___ \| |___| |___ / ___ \| |  | | |_| | |\  |'
echo '|___|_| \_|____/ |_/_/   \_\_____|_____/_/   \_\_| |___\___/|_| \_|'
echo '                                                                   '
echo_star_line
sleep 0.3
echo ""
fi

#set http_proxy if needed
if [ ! -z $HTTP_PROXY ]; then
    export http_proxy=$HTTP_PROXY
    export https_proxy=$HTTP_PROXY
fi

if [ $UPGRADE = 'y' ]; then
    upgrade_folder=`mktemp`
    rm -f $upgrade_folder
    mkdir -p $upgrade_folder
    zstack-ctl status |grep 'Running' >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        CURRENT_STATUS='y'
    else
        CURRENT_STATUS='n'
    fi
    UI_CURRENT_STATUS='n'
    UI_INSTALLATION_STATUS='n'
    if [ -f /etc/init.d/zstack-dashboard ]; then
        UI_INSTALLATION_STATUS='y'
        /etc/init.d/zstack-dashboard status | grep -i 'running' > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            UI_CURRENT_STATUS='y'
        fi
    fi
fi

#Do preinstallation checking for CentOS and Ubuntu
check_system

if [ $OS != $UBUNTU1404 ]; then
    create_yum_repo
fi

#Download ${PRODUCT_NAME} all in one package
download_zstack

if [ $UPGRADE = 'y' ]; then
    #only upgrade zstack
    upgrade_zstack
    cd /; rm -rf $upgrade_zstack

    [ -z $VERSION ] && VERSION=`zstack-ctl status|grep version|awk '{print $2}'`
    echo ""
    echo_star_line
    echo -e "$(tput setaf 2)${PRODUCT_NAME} in $ZSTACK_INSTALL_ROOT has been successfully upgraded to version: ${VERSION}$(tput sgr0)"
    echo ""
    if [ $CURRENT_STATUS = 'y' ]; then
        if [ -z $NEED_KEEP_DB ];then
            echo -e " $(tput setaf 2)Management node has been started up again.$(tput sgr0) You can use \`zstack-ctl status\` to check its status."
        else
            echo -e " $(tput setaf 3)Management node is not started up, since using -k option to skip database upgrading.$(tput sgr0) You can use \`zstack-ctl start\` to start all services, after upgrading database manually."
        fi
    else
        echo -e " $(tput setaf 3)Management node is not started. Please use \`zstack-ctl start\` to start it up.$(tput sgr0)"
    fi
    echo ""
    if [ $UI_INSTALLATION_STATUS = 'y' ]; then
        echo -e " $(tput setaf 2)UI has been upgraded.$(tput sgr0)"
        echo ""
        if [ $UI_CURRENT_STATUS = 'y' ]; then
            echo -e " $(tput setaf 2)UI daemon has been started up again.$(tput sgr0)"
        else
            echo -e " $(tput setaf 3)UI daemon is not started. You can manually start it up by \`zstack-ctl start_ui\`$(tput sgr0)"
        fi
    else
        echo " UI was not upgraded, since there wasn't UI installed before upgrading. You can manually install UI by \`zstack-ctl install_ui\`"
    fi
    echo ""
    zstack_home=`eval echo ~zstack`
    echo " Your old zstack was saved in $zstack_home/upgrade/`ls $zstack_home/upgrade/ -rt|tail -1`"
    echo_star_line
    exit 0
else
    #stop zstack before installation.
    which zstack-ctl >/dev/null 2>&1
    if [ $? -eq 0 ];then
        zstack-ctl stop >/dev/null 2>&1
    fi
fi

#Install unzip and unpack zstack war into apache tomcat
unpack_zstack_into_tomcat

#doesn't need use to send -m option to install monitor.
[ -f "$ZSTACK_INSTALL_ROOT/kairosdb-1.1.1-1.tar.gz" ] && INSTALL_MONITOR='y'

#Do not config NFS or HTTP when installing ZStack product
[ ! -z $INSTALL_MONITOR ] && NEED_NFS='' && NEED_HTTP=''

#Install Ansible 
install_ansible

#Install ${PRODUCT_NAME} required system libs through ansible
install_system_libs

if [ ! -z $ONLY_INSTALL_LIBS ];then
    echo ""
    echo_star_line
    echo "Finish installing ${PRODUCT_NAME} dependent software."
    echo "${PRODUCT_NAME} management node and Tomcat are not installed."
    echo "P.S.: selinux is disabled!"
    echo_star_line
    exit 0
fi

#Download and install ${PRODUCT_NAME} Package
install_zstack

#Post Configuration, including apache, zstack-server, NFS Server, HTTP Server
config_system

if [ -f $ZSTACK_VERSION -a -z "$VERSION" ]; then
    VERSION=`cat $ZSTACK_VERSION`' '
else
    VERSION=''
fi

if [ ! -z $ONLY_INSTALL_ZSTACK ]; then
    echo ""
    echo_star_line
    echo "${PRODUCT_NAME} ${VERSION}management node is installed to $ZSTACK_INSTALL_ROOT."
    echo "Mysql and RabbitMQ are not installed. You can use zstack-ctl to install them and start ${PRODUCT_NAME} service later. "
    echo_star_line
    exit 0
fi

#Install Mysql and Rabbitmq
install_db_msgbus

if [ ! -z $NEED_SET_MN_IP ];then
    zstack-ctl configure management.server.ip=${MANAGEMENT_IP}
fi

if [ ! -z $INSTALL_MONITOR ]; then
    start_monitor
fi

#Start ${PRODUCT_NAME} 
if [ -z $NOT_START_ZSTACK ]; then
    start_zstack
fi

#set http_proxy for install zstack-dashboard if needed.
if [ ! -z $HTTP_PROXY ]; then
    export http_proxy=$HTTP_PROXY
    export https_proxy=$HTTP_PROXY
fi

#Start ${PRODUCT_NAME}-Dashboard
if [ -z $NOT_START_ZSTACK ]; then
    start_dashboard
fi

if [ -f /bin/systemctl ]; then
    systemctl start zstack.service >/dev/null 2>&1
fi

#Print all installation message
if [ -z $NOT_START_ZSTACK ]; then
    [ -z $VERSION ] && VERSION=`zstack-ctl status|grep version|awk '{print $2}'`
fi

echo ""
echo_star_line
touch $README
echo -e "${PRODUCT_NAME} All In One ${VERSION} Installation Completed:
 - Installation path: $ZSTACK_INSTALL_ROOT

 - UI is running, visit $(tput setaf 4)http://$MANAGEMENT_IP:5000$(tput sgr0) in Chrome or Firefox
      Use $(tput setaf 3)zstack-ctl [stop_ui|start_ui]$(tput sgr0) to stop/start the UI service

 - Management node is running
      Use $(tput setaf 3)zstack-ctl [stop|start]$(tput sgr0) to stop/start it

 - ${PRODUCT_NAME} command line tool is installed: zstack-cli
 - ${PRODUCT_NAME} control tool is installed: zstack-ctl

 - For system security, $(tput setaf 4) database root password is set to: $MYSQL_NEW_ROOT_PASSWORD $(tput sgr0) . You can use \`mysqladmin -u root --password=$MYSQL_NEW_ROOT_PASSWORD password NEW_PASSWORD\` to change it. To be noticed: ${PRODUCT_NAME} will use 'zstack' user to access database. Change 'root' password won't impact 'zstack' access database."|tee -a $README

if [ ! -z QUIET_INSTALLATION ]; then
    if [ -z "$CHANGE_HOSTNAME" -a -z "$CHANGE_HOSTS" -a -z "$DELETE_PY_CRYPTO" -a -z "$SETUP_EPEL" ];then
        true
    else
        echo -e "\n$(tput setaf 6) User select QUIET installation. Installation does following changes for user:"
        if [ ! -z "$CHANGE_HOSTNAME" ]; then
            echo " - HOSTNAME is changed to '$CHANGE_HOSTNAME' to avoid of rabbitmq and mysql server installation failure."
        fi
        if [ ! -z "$CHANGE_HOSTS" ]; then
            echo " - /etc/hosts is added a new line: '$CHANGE_HOSTNAME' to avoid of rabbitmq server installation failure."
        fi
        if [ ! -z "$DELETE_PY_CRYPTO" ]; then
            echo " - 'python-crypto' rpm is removed to avoid of confliction with Ansible."
        fi
        if [ ! -z "$SETUP_EPEL" ]; then
            echo " - /etc/yum.repos.d/epel.repo is helped to setup to use standard mirror."
        fi
        echo -e "$(tput sgr0)\n"
    fi
fi
[ ! -z $NEED_NFS ] && echo -e "$(tput setaf 7) - $MANAGEMENT_IP:$NFS_FOLDER is configured for primary storage as an EXAMPLE$(tput sgr0)"
[ ! -z $NEED_HTTP ] && echo -e "$(tput setaf 7) - http://$MANAGEMENT_IP/image is ready for storing images as an EXAMPLE.  After copy your_image_name to the folder $HTTP_FOLDER, your image local url is http://$MANAGEMENT_IP/image/your_image_name$(tput sgr0)"
echo -e "$(tput setaf 7) - You can use \`zstack-ctl install_management_node --host=remote_ip\` to install more management nodes$(tput sgr0)"
echo_star_line
