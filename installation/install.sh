#!/bin/bash

# Mevoco Installer
# Usage: bash install.sh
traplogger () {
    echo -n $(date +%Y-%m-%d' '%H:%M:%S,$((`date +10#%N`/1000000))) | tee -a  $ZSTACK_TIMESTAMP_LOG 1>/dev/null
    echo -n "  [running line: $1]" |tee -a $ZSTACK_TIMESTAMP_LOG 1>/dev/null
    echo -n "  {command: $2}" |tee -a $ZSTACK_TIMESTAMP_LOG 1>/dev/null
    echo -e "  exited with status : $3\n" |tee -a $ZSTACK_TIMESTAMP_LOG 1>/dev/null
}

trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

#DEBUG='y'
if [ -n "$DEBUG" ]
then
set -x
fi

PROGNAME=$0
PRODUCT_NAME=${PRODUCT_NAME:-"ZStack"}
SS100='SS100'
SS100_STORAGE='SS100-Storage'
VERSION=${PRODUCT_VERSION:-""}
VERSION_RELEASE_NR=`echo $PRODUCT_VERSION | awk -F '.' '{print $1"."$2"."$3}'`
ZSTACK_INSTALL_ROOT=${ZSTACK_INSTALL_ROOT:-"/usr/local/zstack"}
MINI_INSTALL_ROOT=${ZSTACK_INSTALL_ROOT}/zstack-mini/

# zstack mini server before 1.1.0 is installed in /usr/local/zstack-mini
LEGACY_MINI_INSTALL_ROOT="/usr/local/zstack-mini/"

export TERM=xterm

OS=''
REDHAT_OS="CENTOS6 CENTOS7 RHEL7 ALIOS7 ISOFT4 KYLIN10 EULER20 UOS1020A"
DEBIAN_OS="UBUNTU14.04 UBUNTU16.04 UBUNTU KYLIN4.0.2 DEBIAN9 UOS20"
XINCHUANG_OS="ns10 uos20"
SUPPORTED_OS="$REDHAT_OS $DEBIAN_OS"
REDHAT_WITHOUT_CENTOS6=`echo $REDHAT_OS |sed s/CENTOS6//`

UPGRADE='n'
FORCE='n'
MINI_INSTALL='n'
SANYUAN_INSTALL='n'
SDS_INSTALL='n'
MANAGEMENT_INTERFACE=`ip route | grep default | head -n 1 | cut -d ' ' -f 5`
ZSTACK_INSTALL_LOG='/tmp/zstack_installation.log'
ZSTACKCTL_INSTALL_LOG='/tmp/zstack_ctl_installation.log'
ZSTACK_TIMESTAMP_LOG='/tmp/zstack_installation_timestamp.log'
[ -f $ZSTACK_TIMESTAMP_LOG ] && /bin/rm -f $ZSTACK_TIMESTAMP_LOG
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
CATALINA_ZSTACK_LIBS=$CATALINA_ZSTACK_PATH/WEB-INF/lib
ZSTACK_PROPERTIES=$CATALINA_ZSTACK_CLASSES/zstack.properties
ZSTACK_DB_DEPLOYER=$CATALINA_ZSTACK_CLASSES/deploydb.sh
CATALINA_ZSTACK_TOOLS=$CATALINA_ZSTACK_CLASSES/tools
ZSTACK_TOOLS_INSTALLER=$CATALINA_ZSTACK_TOOLS/install.sh
zstack_163_repo_file=/etc/yum.repos.d/zstack-163-yum.repo
zstack_ali_repo_file=/etc/yum.repos.d/zstack-aliyun-yum.repo
PRODUCT_TITLE_FILE='./product_title_file'
UPGRADE_LOCK=/tmp/zstack_upgrade.lock
MYSQL_CONF_FILE=''
AUDIT_RULE_FILE='/etc/audit/rules.d/audit.rules'
SDS_PORT='8056'

[ ! -z $http_proxy ] && HTTP_PROXY=$http_proxy

NEED_NFS=''
NEED_HTTP=''
NEED_DROP_DB=''
NEED_KEEP_DB=''
ONLY_INSTALL_LIBS=''
ONLY_INSTALL_ZSTACK=''
NOT_START_ZSTACK=''
NEED_SET_MN_IP=''
INSTALL_ENTERPRISE='n'
REPO_MATCHED='true'

MYSQL_ROOT_PASSWORD=''
MYSQL_PORT='3306'
MYSQL_NEW_ROOT_PASSWORD='zstack.mysql.password'
MYSQL_USER_PASSWORD='zstack.password'
MYSQL_UI_USER_PASSWORD='zstack.ui.password'

YUM_ONLINE_REPO='y'
INSTALL_MONITOR=''
UPGRADE_MONITOR=''
ONLY_UPGRADE_CTL=''
ZSTACK_START_TIMEOUT=1000
ZSTACK_PKG_MIRROR=''
PKG_MIRROR_163='163'
PKG_MIRROR_ALIYUN='aliyun'
#used for all in one installer and upgrader. 
ZSTACK_YUM_REPOS=''
ZSTACK_LOCAL_YUM_REPOS='zstack-local'
ZSTACK_MN_REPOS='zstack-mn,qemu-kvm-ev-mn'
ZSTACK_MN_UPGRADE_REPOS='zstack-mn'
MIRROR_163_YUM_REPOS='163base,163updates,163extras,ustcepel,163-qemu-ev'
MIRROR_163_YUM_WEBSITE='mirrors.163.com'
MIRROR_ALI_YUM_REPOS='alibase,aliupdates,aliextras,aliepel,ali-qemu-ev'
MIRROR_ALI_YUM_WEBSITE='mirrors.aliyun.com'
#used for zstack.properties Ansible.var.zstack_repo
ZSTACK_PROPERTIES_REPO=''
ZSTACK_ANSIBLE_EXECUTABLE='python2'
ZSTACK_OFFLINE_INSTALL='n'

QUIET_INSTALLATION=''
CHANGE_HOSTNAME=''
CHANGE_HOSTS=''
DELETE_PY_CRYPTO=''
SETUP_EPEL=''
CONSOLE_PROXY_ADDRESS=''
CURRENT_VERSION=''

LICENSE_PATH=''
LICENSE_FILE='zstack-license'
LICENSE_FOLDER='/var/lib/zstack/license/'
ZSTACK_TRIAL_LICENSE='./zstack_trial_license'
ZSTACK_OLD_LICENSE_FOLDER=$ZSTACK_INSTALL_ROOT/license

DEFAULT_MN_PORT='8080'
MN_PORT="$DEFAULT_MN_PORT"

DEFAULT_UI_PORT='5000'
RESOLV_CONF='/etc/resolv.conf'

BASEARCH=`uname -m`
ZSTACK_RELEASE=''
# start/stop zstack_tui
ZSTACK_TUI_SERVICE='/usr/lib/systemd/system/getty@tty1.service'
start_zstack_tui() {
  cat $ZSTACK_TUI_SERVICE 2>/dev/null | grep 'zstack_tui' >/dev/null 2>&1 || return
  sed -i 's/Restart=no/Restart=always/g' $ZSTACK_TUI_SERVICE 2>/dev/null
  systemctl daemon-reload
  systemctl start getty@tty1.service &
}

stop_zstack_tui() {
  [ -z $ZS_AUTO_INSTALL ] || return
  ps -ef | grep zstack_tui | grep -v 'grep' >/dev/null 2>&1 || return
  sed -i 's/Restart=always/Restart=no/g' $ZSTACK_TUI_SERVICE 2>/dev/null
  systemctl daemon-reload
  pkill -9 zstack_tui
}

disable_zstack_tui() {
  sed -i '/agetty -n/s/ -n -l \/usr\/local\/zstack_tui\/zstack_tui//g' $ZSTACK_TUI_SERVICE 2>/dev/null
  systemctl daemon-reload
}

kill_zstack_tui_and_restart_tty1(){
  pkill -9 zstack_tui
  systemctl restart getty@tty1.service
}

# stop zstack_tui to prevent zstack auto installation
stop_zstack_tui

#define extra upgrade params
#USE THIS PATTERN: upgrade_params_array[INDEX]='VERSION,PARAM'
#this params_array is appeared only once and not persisted
declare -a upgrade_params_array=(
    '1.3,-DsyncImageActualSize=true'
    '1.4,-DtapResourcesForBilling=true'
    '2.2.2,-DupdateLdapUidToLdapDn=true'
    '2.3.1,-Dzwatch.migrateFromOldMonitorImplementation=true'
    '3.2.0,-DupgradeVolumeQos=true'
    '3.3.0,-DaddCdRomToHistoricalVm=true'
    '3.4.0,-DupgradeTwoFactorAuthenticationSecret=true'
    '3.4.1,-DgenerateBillsImmediately=true'
    '3.5.0,-DupgradeVolumeBackupHistory=true'
    '3.6.0,-Diam2.upgradeIAM2Attribute=true'
    '3.7.0,-DImageStoreBackupStorage.enableQuota=true'
    '3.7.0,-DinitRunningVmPriority=true'
    '3.7.2,-DgeneratePriceEndDate=true'
    '3.8.0,-DinitRunningApplianceVmPriority=true'
    '3.9.0,-DupgradeDatabaseBackupHistory=true'
    '3.9.0,-DupgradeSchedulerJobHistory=true'
    '3.9.0,-Dft.upgradeFaultToleranceGlobalConfig=true'
    '3.10.0,-DupgradeVpcNetworkService=true'
    '4.0.0,-DupgradeVrToVpc=true'
    '4.0.0,-DsyncPciDeviceOfferingRef=true'
    '4.0.0,-DupgradeLoadBalancerServerGroup=true'
    '4.1.0,-DupgradeSystemVipNetworkServicesRefVO=true'
    '4.1.0,-Dlicense.upgradeLicenseRecords=true'
    '4.1.3,-DsyncInfluxdbRetentionConfig=true'
    '4.3.6,-DdeduplicateVolumeGc=true'
)
#other than the upon params_array, this one could be persisted in zstack.properties
declare -a upgrade_persist_params_array=(
    '3.9.0,InfluxDB.enable.message.retention=false'
)

#persist more when install/upgrade mini
upgrade_mini_persist_params(){
  ui_mode=`zstack-ctl show_configuration |awk '/ui_mode/{print $3}'` >/dev/null 2>&1
  if [ x"$MINI_INSTALL" = x"y" ] | [ x"$ui_mode" = x"mini" ];then
    upgrade_persist_params_array+=('4.0.0,Search.autoRegister=false')
  fi
}

#upgrade mini zwatch webhook
upgrade_mini_zwatch_webhook(){
  ui_mode=$(zstack-ctl get_configuration ui_mode)
  if [ x"$MINI_INSTALL" != x"y" ] & [ x"$ui_mode" != x"mini" ]; then
      return
  fi
  webhook=$(zstack-ctl get_configuration sns.systemTopic.endpoints.http.url | grep '/zwatch/webhook')
  
  if [ "$webhook" = "" ]; then
      return
  fi

  webhook=$(echo "$webhook" | sed 's/zwatch\/webhook/webhook\/zwatch/g')
  zstack-ctl configure sns.systemTopic.endpoints.http.url="$webhook" > /dev/null 2>&1
}

# version compare
# eg. 1 = 1.0
# eg. 4.08 < 4.08.01
vercomp () {
    if [[ $1 == $2 ]]
    then
        return 0
    fi
    local IFS=.
    local i ver1=($1) ver2=($2)
    # fill empty fields in ver1 with zeros
    for ((i=${#ver1[@]}; i<${#ver2[@]}; i++))
    do
        ver1[i]=0
    done
    for ((i=0; i<${#ver1[@]}; i++))
    do
        if [[ -z ${ver2[i]} ]]
        then
            # fill empty fields in ver2 with zeros
            ver2[i]=0
        fi
        if ((10#${ver1[i]} > 10#${ver2[i]}))
        then
            return 1
        fi
        if ((10#${ver1[i]} < 10#${ver2[i]}))
        then
            return 2
        fi
    done
    return 0
}

check_zstack_release(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ "$IS_YUM" = "y" ];then
        rpm -q zstack-release >/dev/null 2>&1
        if [ $? -eq 0 ];then
            ZSTACK_RELEASE=`rpm -qi zstack-release |awk -F ':' '/Version/{print $2}' |sed 's/ //g'`
            [ ! -f /etc/zstack-release ] && yum reinstall -y zstack-release > /dev/null 2>&1
        else
            ZSTACK_RELEASE=`rpm -q centos-release | awk -F '.' '{print $1}' | awk -F '-' '{print "c"$3$4}'`
            find /opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE -type f -name zstack-release-$ZSTACK_RELEASE-\* -exec rpm -i {} >/dev/null 2>&1 \; || \
                    fail2 "rpm package ${PRODUCT_NAME,,}-release is not installed, use ${PRODUCT_NAME,,}-upgrade -r/-a ${PRODUCT_NAME,,}-xxx.iso(>=3.7.0) to upgrade local repo and install ${PRODUCT_NAME,,}-release."
        fi
        source /etc/profile >/dev/null 2>&1
    else
        dpkg -l zstack-release > /dev/null 2>&1
        if [ $? -eq 0 ];then
            ZSTACK_RELEASE=`awk '{print $3}' /etc/zstack-release`
        else
            fail2 "deb package zstack-release is not installed, use zstack_install_kylin.sh -r xxx.iso to install zstack-dvd."
        fi
    fi
}

# get mn port from zstack properties
get_mn_port() {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    local zstack_properties=$ZSTACK_INSTALL_ROOT/$ZSTACK_PROPERTIES
    [ ! -f "$zstack_properties" ] && return

    local mn_port=`awk -F '=' '/RESTFacade.port/{ print $NF }' ${zstack_properties} | xargs`
    [ ! -z "$mn_port" ] && MN_PORT="$mn_port"
} >>$ZSTACK_INSTALL_LOG 2>&1

# adjust iptables rules before zstack installation/upgrade
pre_scripts_to_adjust_iptables_rules() {
  trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
  # allow remote mysql connection from 127.0.0.1
  if [ x"$UPGRADE" = x'n' ]; then
    db_port=$MYSQL_PORT
  else
    db_port=`zstack-ctl show_configuration | awk -F ':' '/DB.url/{ print $NF }'`
  fi
  iptables -L INPUT | grep 'zstack allow login mysql from 127.0.0.1' || \
  iptables -I INPUT -p tcp --dport ${db_port} -s 127.0.0.1 -j ACCEPT -m comment --comment 'zstack allow login mysql from 127.0.0.1'
} >>$ZSTACK_INSTALL_LOG 2>&1

# restore iptables rules after zstack installation/upgrade
post_scripts_to_restore_iptables_rules() {
  trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
  iptables -D INPUT `iptables -L INPUT --line-numbers | grep 'zstack allow login mysql from 127.0.0.1' | awk '{ print $1 }'`
  service iptables save
} >>$ZSTACK_INSTALL_LOG 2>&1

post_restore_source_on_debian() {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    mv /etc/apt/sources.list.d/tmp_bak/*.list /etc/apt/sources.list.d/ 2>/dev/null
    rm -rf /etc/apt/sources.list.d/tmp_bak/ 2>/dev/null
}

cleanup_function(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    /bin/rm -f $UPGRADE_LOCK
    /bin/rm -f $INSTALLATION_FAILURE
    /bin/rm -f $zstack_tmp_file
}

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
        # clean up iptables rules added by zstack installation script if failed
        post_scripts_to_restore_iptables_rules

        failure_reason=`cat $INSTALLATION_FAILURE`
        #tput cub 6
        if [ -z $DEBUG ]; then
            echo -e "$(tput setaf 1)\nFAIL\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
            echo -e "$(tput setaf 1)Reason: $failure_reason\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
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
    sync
    echo ""|tee -a $ZSTACK_INSTALL_LOG
    [ ! -z $PID ] && kill -9 $PID
    tput sgr0
    tput rc
    echo -e "$(tput setaf 3)Installation canceled by User\n$(tput sgr0)"
    echo "The detailed installation log could be found in $ZSTACK_INSTALL_LOG"
    cleanup_function
    exit 1
}

trap cancel INT

# The params is failed reason
fail(){
    sync
    #tput cub 6
    #echo -e "$(tput setaf 1) FAIL\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
    #echo -e "$(tput setaf 1)  Reason: $*\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
    cleanup_function
    #echo "-------------"
    echo "$*  \n\nThe detailed installation log could be found in $ZSTACK_INSTALL_LOG " > $INSTALLATION_FAILURE
    #echo "-------------"
    disable_zstack_tui
    exit 1
}

#not for spin task fail
fail2(){
    sync
    cleanup_function
    tput cub 6
    echo -e "$(tput setaf 1) \nFAIL\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
    echo -e "$(tput setaf 1) Reason: $*\n$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
    echo "-------------"
    echo "$*  \n\nThe detailed installation log could be found in $ZSTACK_INSTALL_LOG " > $INSTALLATION_FAILURE
    echo "-------------"
    disable_zstack_tui
    exit 1
}

pass(){
    #echo -e "$(tput setaf 2) PASS$(tput sgr0)"|tee -a $ZSTACK_INSTALL_LOG
    sync
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

enable_tomcat_linking() {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    local context_xml_file=$ZSTACK_INSTALL_ROOT/apache-tomcat/conf/context.xml
    if ! grep -q -w allowLinking $context_xml_file; then
        local new_line="    <Resources allowLinking=\"true\"></Resources>\r"
        sed -i "/<Context>/a\\$new_line" $context_xml_file
        echo "Tomcat allowLinking enabled." >>$ZSTACK_INSTALL_LOG
        sync
    fi
}

disable_tomcat_methods() {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    local web_xml_file=$ZSTACK_INSTALL_ROOT/apache-tomcat/conf/web.xml
    if ! grep -q "<security-constraint>" $web_xml_file; then
        sed -i "/<\/web-app>/d" $web_xml_file
        echo -e "$(cat <<EOF
    <security-constraint>\r
        <web-resource-collection>\r
            <web-resource-name>tomcat-security</web-resource-name>\r
            <url-pattern>/*</url-pattern>\r
            <http-method>OPTIONS</http-method>\r
            <http-method>TRACE</http-method>\r
            <http-method>PATCH</http-method>\r
            <http-method>COPY</http-method>\r
            <http-method>LINK</http-method>\r
            <http-method>UNLINK</http-method>\r
            <http-method>PURGE</http-method>\r
            <http-method>LOCK</http-method>\r
            <http-method>UNLOCK</http-method>\r
            <http-method>PROPFIND</http-method>\r
            <http-method>VIEW</http-method>\r
        </web-resource-collection>\r
        <auth-constraint></auth-constraint>\r
    </security-constraint>\r
\r
</web-app>\r
EOF
)" >> $web_xml_file
        echo "Tomcat HTTP methods updated." >>$ZSTACK_INSTALL_LOG
        sync
    fi
}

udpate_tomcat_info() {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    ## update catalina.jar/ServerInfo.properties
    local jar_file=$ZSTACK_INSTALL_ROOT/apache-tomcat/lib/catalina.jar

    local work_path=$PWD
    local temp_path=`mktemp`
    rm -f $temp_path
    mkdir -p $temp_path

    cd $temp_path
    jar xvf $jar_file > /dev/nul
    if [ $? -eq 0 ]; then
        local properties_file=org/apache/catalina/util/ServerInfo.properties
        if grep -q "server.info=Apache Tomcat" $properties_file; then
            sed -i "/^server.info=/c\server.info=X\r" $properties_file
            sed -i "/^server.number=/c\server.number=5.5\r" $properties_file
            sed -i "/^server.built=/c\server.built=Dec 1 2015 22:30:46 UTC\r" $properties_file
            sync

            jar cvf catalina.jar org META-INF > /dev/nul
            if [ $? -eq 0 ]; then
                rm -f $jar_file
                mv catalina.jar $jar_file
                chmod a+r $jar_file
                echo "Tomcat server info updated." >>$ZSTACK_INSTALL_LOG
            else
                echo "Zip $jar_file error." >>$ZSTACK_INSTALL_LOG
            fi
        fi
    else
        echo "Unzip $jar_file error." >>$ZSTACK_INSTALL_LOG
    fi

    rm -rf $temp_path
    cd $work_path
}

upgrade_tomcat_security() {
    echo_subtitle "Upgrade Tomcat Security"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

    enable_tomcat_linking
    disable_tomcat_methods
    udpate_tomcat_info

    pass
}

set_tomcat_config() {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    new_timeout=120000
    new_max_thread_num=400
    new_min_spare_threads=50
    new_max_queue_size=100
    tomcat_config_path=$ZSTACK_INSTALL_ROOT/apache-tomcat/conf

    sed -i 's/port="8080"/executor="tomcatThreadPool"  port="8080"/g' $tomcat_config_path/server.xml
    sed -i 's/connectionTimeout=".*"/connectionTimeout="'"$new_timeout"'"/' $tomcat_config_path/server.xml
    sed -i 's/redirectPort="8443" \/>/redirectPort="8443" maxHttpHeaderSize="65536" URIEncoding="UTF-8" useBodyEncodingForURI="UTF-8" \/>\n  \ \ \ \  <Executor name="tomcatThreadPool" namePrefix="catalina-exec-" maxThreads="'"$new_max_thread_num"'" minSpareThreads="'"$new_min_spare_threads"'" prestartminSpareThreads="true" maxQueueSize="'"$new_max_queue_size"'"\/>/g' $tomcat_config_path/server.xml
    sed -i 's/maxThreads=".*"/maxThreads="'"$new_max_thread_num"'"/' $tomcat_config_path/server.xml
    # Fix ZSTAC-13580
    sed -i -e '/allowLinking/d' -e  '/autoDeploy/a \ \ \ \ \ \ \ \ <Context path="/zstack" reloadable="false" crossContext="true" allowLinking="true"/>' $tomcat_config_path/server.xml
    sync

    enable_tomcat_linking
}

cs_check_hostname_zstack(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    which hostname &>/dev/null
    [ $? -ne 0 ] && return 

    current_hostname=`hostname`
    CHANGE_HOSTNAME=`echo $MANAGEMENT_IP | sed 's/\./-/g'`
    CURRENT_HOST_ITEM="$MANAGEMENT_IP $current_hostname"
    HOSTS_ITEM="$MANAGEMENT_IP $CHANGE_HOSTNAME"

    # current hostname is localhost
    if [ "localhost" = $current_hostname ] || [ "localhost.localdomain" = $current_hostname ] ; then
        which hostnamectl >>/dev/null 2>&1
        if [ $? -ne 0 ]; then
            #hostnamectl only valid in redhat OS.
            hostname $CHANGE_HOSTNAME
        else
            hostnamectl set-hostname $CHANGE_HOSTNAME >>$ZSTACK_INSTALL_LOG 2>&1
            #If /etc/hostname is same with CHANGE_HOSTNAME, but hostname 
            # command is different, hostnamectl will not change current 
            # hostname, so we need to manually reset current hostname as well.
            hostname $CHANGE_HOSTNAME >>$ZSTACK_INSTALL_LOG 2>&1
        fi
        # insert into /etc/hosts if $HOSTS_ITEM not exists
        grep -q "$HOSTS_ITEM" /etc/hosts || echo "$HOSTS_ITEM" >> /etc/hosts

        echo "Your OS hostname is set as $current_hostname, which will block vm live migration. You can set a special hostname, or directly use $CHANGE_HOSTNAME by running following commands in CentOS6:

        hostname $CHANGE_HOSTNAME
        echo $MANAGEMENT_IP $CHANGE_HOSTNAME >> /etc/hosts

or following commands in CentOS7:
        hostnamectl set-hostname $CHANGE_HOSTNAME
        hostname $CHANGE_HOSTNAME
        echo $MANAGEMENT_IP $CHANGE_HOSTNAME >> /etc/hosts

" >> $ZSTACK_INSTALL_LOG
        return 0
    fi

    # current hostname is not same with IP
    ip addr | grep inet |awk '{print $2}'|grep $current_hostname &> /dev/null
    if [ $? -ne 0 ]; then
        # insert into /etc/hosts if $CURRENT_HOST_ITEM not exists
        grep -q "$CURRENT_HOST_ITEM" /etc/hosts || echo "$CURRENT_HOST_ITEM" >> /etc/hosts
        # must reset hostname to keep it same with system to avoid of user manually modify /etc/hostname without reboot system before running installer.
        which hostnamectl >>/dev/null 2>&1
        if [ $? -ne 0 ]; then
            hostname $current_hostname
        else
            hostnamectl set-hostname $current_hostname >>$ZSTACK_INSTALL_LOG 2>&1
            hostname $current_hostname >>$ZSTACK_INSTALL_LOG 2>&1
        fi
        return 0
    fi

    # current hostname is same with IP
    echo "Your OS hostname is set as $current_hostname, which is same with your IP address. It will cause some problem.
Please fix it by running following commands in CentOS7:

    hostnamectl set-hostname MY_REAL_HOSTNAME
    hostname MY_REAL_HOSTNAME
    echo \"$current_hostname MY_REAL_HOSTNAME\" >>/etc/hosts

Or use other hostname setting method in other system. 
Then restart installation. 

You can also add '-q' to installer, then Installer will help you to set one.
" >> $ZSTACK_INSTALL_LOG
    which hostnamectl >>/dev/null 2>&1
    if [ $? -ne 0 ]; then
        hostname $CHANGE_HOSTNAME
    else
        hostnamectl set-hostname $CHANGE_HOSTNAME >>$ZSTACK_INSTALL_LOG 2>&1
        hostname $CHANGE_HOSTNAME >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    # insert into /etc/hosts if $HOSTS_ITEM not exists
    grep -q "$HOSTS_ITEM" /etc/hosts || echo "$HOSTS_ITEM" >> /etc/hosts
}

cs_check_hostname_mini () {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    which hostname &>/dev/null
    [ $? -ne 0 ] && return

    CURRENT_HOSTNAME=`hostname`
    CHANGE_HOSTNAME="zstack-mini-`dmidecode -s system-serial-number | tr -d '-' | awk '{print substr($0, length($0)-6)}' | tr 'A-Z' 'a-z'`"
    [ x"$CURRENT_HOSTNAME" = x"$CHANGE_HOSTNAME" ] && return
    
    which hostnamectl >>/dev/null 2>&1
    if [ $? -ne 0 ]; then
        hostname $CHANGE_HOSTNAME >>$ZSTACK_INSTALL_LOG 2>&1
    else
        hostnamectl set-hostname $CHANGE_HOSTNAME >>$ZSTACK_INSTALL_LOG 2>&1
        hostname $CHANGE_HOSTNAME >>$ZSTACK_INSTALL_LOG 2>&1
    fi
}

cs_check_mysql_password () {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    #If user didn't assign mysql root password, then check original zstack mysql password status
    if [ 'y' != $UPGRADE ]; then
        if [ -z $ONLY_INSTALL_ZSTACK ];then
            if [ "$IS_YUM" = "y" ];then
                rpm -qa | grep mysql-community >>$ZSTACK_INSTALL_LOG 2>&1 && mysql_community='y'
            else
                dpkg -l | grep mysql-community >>$ZSTACK_INSTALL_LOG 2>&1 && mysql_community='y'
            fi
            #[ "$mysql_community" = "y" ] && fail2 "Detect mysql-community installed, please uninstall it due to ${PRODUCT_NAME} will use mariadb."
        fi

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
                                fail2 "\nCannot login mysql!
     If you have mysql root password, please add option '-P MYSQL_ROOT_PASSWORD'.
     If you do not set mysql root password or mysql server is not started up, please add option '-q' and try again.\n"
                            fi
                        else
                            MYSQL_ROOT_PASSWORD=$MYSQL_NEW_ROOT_PASSWORD
                        fi
                    fi
                fi
            fi
        fi
    elif [ -z $ONLY_INSTALL_ZSTACK ] && [ -z $NEED_KEEP_DB ]; then
      # Fixes ZSTAC-18778
      # If database zstack-ui doesn't exists, then we need mysql root password when upgrading zstack.
      zstack-ctl show_ui_config 2>/dev/null | grep db_username >/dev/null 2>&1
      if [ $? -ne 0 ]; then
        # grant all to root@127.0.0.1
        mysql -uroot -p"$MYSQL_NEW_ROOT_PASSWORD" \
          -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' IDENTIFIED BY '$MYSQL_NEW_ROOT_PASSWORD' WITH GRANT OPTION; FLUSH PRIVILEGES" >/dev/null 2>&1
        [ $? -eq 0 ] || fail2 "Failed to login mysql, please specify mysql root password using -P MYSQL_ROOT_PASSWORD and try again."
      fi
    fi
}

cs_check_zstack_data_exist(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    cs_check_mysql_password
    if [ -z $ONLY_INSTALL_ZSTACK ] && [ 'y' != $UPGRADE ];then
        which mysql >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            # check zstack database
            mysql --user=root --password=$MYSQL_NEW_ROOT_PASSWORD --host=$MANAGEMENT_IP -e "use zstack" >/dev/null 2>&1
            if [ $? -eq  0 ];then
                if [ -z $NEED_DROP_DB ] && [ -z $NEED_KEEP_DB ];then
                fail2 'detected existing zstack database; if you are sure to drop it, please append parameter -D or use -k to keep the database'
                fi
            fi

            # check zstack_ui database
            mysql --user=root --password=$MYSQL_NEW_ROOT_PASSWORD --host=$MANAGEMENT_IP -e "use zstack_ui" >/dev/null 2>&1
            if [ $? -eq  0 ];then
                if [ -z $NEED_DROP_DB ] && [ -z $NEED_KEEP_DB ];then
                fail2 'detected existing zstack_ui database; if you are sure to drop it, please append parameter -D or use -k to keep the database'
                fi
            fi
        fi
    fi
}

#Do preinstallation checking for CentOS and Ubuntu and Database
check_system(){
    echo_title "Check System"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    cat /etc/*-release |egrep -i -h "centos |Red Hat Enterprise|Alibaba|NeoKylin|Kylin Linux Advanced Server release V10|openEuler|UnionTech OS Server release 20 \(kongzi\)" >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -eq 0 ]; then
        grep -qi 'CentOS release 6' /etc/system-release && OS="CENTOS6"
        grep -qi 'CentOS Linux release 7' /etc/system-release && OS="CENTOS7"
        grep -qi 'Red Hat Enterprise Linux Server release 7' /etc/system-release && OS="RHEL7"
        grep -qi 'Alibaba Group Enterprise Linux' /etc/system-release && OS="ALIOS7"
        grep -qi 'iSoft Linux release 4' /etc/system-release && OS="ISOFT4"
        grep -qi 'NeoKylin Linux' /etc/system-release && OS="RHEL7"
        grep -qi 'Kylin Linux Advanced Server release V10' /etc/system-release && OS="KYLIN10"
        grep -qi 'openEuler release 20.03 (LTS-SP1)' /etc/system-release && OS="EULER20"
        grep -qi 'UnionTech OS Server release 20 (kongzi)' /etc/system-release && OS="UOS1020A"
        if [[ -z "$OS" ]];then
            fail2 "Host OS checking failure: your system is: `cat /etc/redhat-release`, $PRODUCT_NAME management node only supports $SUPPORTED_OS currently"
        elif [[ $OS == "CENTOS7" ]];then
            rpm -q libvirt | grep 1.1.1-29 >/dev/null 2>&1 && fail2 "Your OS is old CentOS7, as its libvirt is `rpm -q libvirt`. \
              You need to use \`yum upgrade\` to upgrade your system to latest CentOS7."
        fi
    else
        grep -qi 'Debian GNU/Linux 9' /etc/issue && OS="DEBIAN9"
        grep -qi 'Ubuntu' /etc/issue && IS_UBUNTU='y'
        grep -qi 'Kylin 4.0.2' /etc/issue && OS="KYLIN4.0.2"
        grep -qi 'uos GNU/Linux 20' /etc/issue && OS="UOS20"
        grep -qi 'Uniontech OS Server 20' /etc/issue && OS="UOS20"
        if [ "$IS_UBUNTU" = "y" ]; then
            grep -qi '16.04' /etc/issue && OS="UBUNTU16.04"
            grep -qi '14.04' /etc/issue && OS="UBUNTU14.04"
            [ "$OS" != "UBUNTU16.04" -a "$OS" != "UBUNTU14.04" ] && fail2 "Host OS checking failure: your system is: $OS, $PRODUCT_NAME management node only support $SUPPORTED_OS currently"
            . /etc/lsb-release
        fi
        if [[ -z "$OS" ]];then
            fail2 "Host OS checking failure: your system is: `cat /etc/issue`, $PRODUCT_NAME management node only support $SUPPORTED_OS currently"
        fi
        export DEBIAN_FRONTEND=noninteractive
    fi

    if ! [[ $SUPPORTED_OS =~ $OS ]]; then
        #only support offline installation for CentoS7.x,Kylin4.0.2
        if [ -z "$YUM_ONLINE_REPO" ]; then
            fail2 "Your system is $OS . ${PRODUCT_NAME} installer can not use '-o' or '-R' option on your system. Please remove '-o' or '-R' option and try again."
        fi
    fi
    debug "Your system is: $OS"

    if [ x"$UPGRADE" = x'y' ]; then
        which zstack-ctl >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            fail2 "Did not find zstack-ctl. Can not use option '-u' to upgrade $PRODUCT_NAME . Please remove '-u' and do fresh installation."
        fi
    fi
    show_spinner cs_pre_check
    cs_check_epel
    if [ x"$MINI_INSTALL" = x"y" ];then
        cs_check_hostname_mini
    elif [ x"$UPGRADE" = x"y" ];then
        ui_mode=`zstack-ctl show_configuration |awk '/ui_mode/{print $3}'` >/dev/null 2>&1
        if [ x"$ui_mode" = x"" ];then
            echo 'ui_mode is not configured, it will be set based on your environment.' >>$ZSTACK_INSTALL_LOG 2>&1
            [ -d ${LEGACY_MINI_INSTALL_ROOT} -o -d $MINI_INSTALL_ROOT ] && zstack-ctl configure ui_mode=mini || zstack-ctl configure ui_mode=zstack
            [ -d ${LEGACY_MINI_INSTALL_ROOT} -o -d $MINI_INSTALL_ROOT ] && zstack-ctl configure log.management.server.retentionSizeGB=200
            [ -d ${LEGACY_MINI_INSTALL_ROOT} -o -d $MINI_INSTALL_ROOT ] && zstack-ctl configure AppCenter.server.mode=on
            ui_mode=`zstack-ctl show_configuration |awk '/ui_mode/{print $3}'`
        fi
        cs_check_hostname_zstack
    else
        cs_check_hostname_zstack
    fi
    show_spinner do_check_system
    cs_check_zstack_data_exist
    show_spinner cs_create_repo
    cs_check_python_installed
}

cs_create_repo(){
    echo_subtitle "Update Package Repository"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [[ $REDHAT_OS =~ $OS ]]; then
        create_yum_repo
    else
        create_apt_source
    fi
    pass
}

cs_check_python_installed(){
    # ansible1.9.6 is depended on by python2
    which python2 >/dev/null 2>&1
    [ $? -ne 0 ] && yum --disablerepo=* --enablerepo=zstack-local install -y python2 >/dev/null 2>&1
    [ ! -f /usr/bin/python -a -f /usr/bin/python2 ] && ln -s /usr/bin/python2 /usr/bin/python
}

cs_check_epel(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    [ -z $YUM_ONLINE_REPO ] && return
    [ ! -z $ZSTACK_PKG_MIRROR ] && return
    if [ "$OS" = "CENTOS7" -o "$OS" = "CENTOS6" ]; then 
        if [ ! -f /etc/yum.repos.d/epel.repo ]; then
            if [ x"$UPGRADE" != x'n' ]; then
                [ ! -z $ZSTACK_YUM_REPOS ] && return
            fi
#            if [ -z $QUIET_INSTALLATION ]; then
#                fail2 'You need to set /etc/yum.repos.d/epel.repo to install ZStack required libs from online. 
#
#Or you can choose to use -R 163 or -R aliyun to install.
#
#Or if you have set the epel in other file, rather than /etc/yum.repos.d/epel.repo, you can add -q to ask installer to ignore checking. The example for /etc/yum.repos.d/epel.repo is like:
#
##cat /etc/yum.repos.d/epel.repo
#[epel]
#name=Extra Packages for Enterprise Linux \$releasever - \$basearch
#mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-\$releasever&arch=\$basearch
#enabled=1
#gpgcheck=0
#
#'
#            else
                cat > /etc/yum.repos.d/epel.repo << EOF
[epel]
name=Extra Packages for Enterprise Linux \$releasever - \$basearch
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-\$releasever&arch=\$basearch
enabled=1
gpgcheck=0
EOF
                SETUP_EPEL='y'
#            fi
        fi
    elif [ "$OS" = $RHEL7 -o "$OS" = $ISOFT4 ]; then
        if [ ! -f /etc/yum.repos.d/epel.repo ]; then
            cat > /etc/yum.repos.d/epel.repo << EOF
[epel]
name=Extra Packages for Enterprise Linux 7 - \$basearch
mirrorlist=https://mirrors.fedoraproject.org/metalink?repo=epel-7&arch=\$basearch
enabled=1
gpgcheck=0
EOF
            SETUP_EPEL='y'
        fi
    fi
}

do_enable_sudo(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ -f /etc/sudoers ]; then
        grep 'zstack' /etc/sudoers &>/dev/null || echo 'zstack        ALL=(ALL)       NOPASSWD: ALL' >> /etc/sudoers
        grep '^root' /etc/sudoers &>/dev/null || echo 'root ALL=(ALL)       NOPASSWD: ALL' >> /etc/sudoers
        sed -i '/requiretty$/d' /etc/sudoers
    fi
}

do_config_networkmanager(){
    sed -i "s/^.*no-auto-default.*$/no-auto-default=*/g" /etc/NetworkManager/NetworkManager.conf > /dev/null 2>&1
}

do_config_limits(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ "$OS" == "KYLIN10" ]; then
      nr_open=1048576
    else
      nr_open=`sysctl -n fs.nr_open`
    fi
    cat > /etc/security/limits.d/10-zstack.conf << EOF
zstack  soft  nofile  $nr_open
zstack  hard  nofile  $nr_open
zstack  soft  nproc  $nr_open
zstack  hard  nproc  $nr_open
EOF
}

do_check_resolv_conf(){
    [ ! -f $RESOLV_CONF ] && touch $RESOLV_CONF
    chmod a+r $RESOLV_CONF
}

do_config_ansible(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    mkdir -p /etc/ansible
    mkdir -p /var/log/ansible
    [ -f /etc/ansible/ansible.cfg ] && return 0
cat > /etc/ansible/ansible.cfg << EOF
[defaults]
executable = /bin/bash
log_path = /var/log/ansible/ansible.log
EOF
}

do_check_system(){
    echo_subtitle "Check System"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

    if [ ! -z $LICENSE_PATH ]; then
      if [ ! -f $LICENSE_PATH ]; then
        fail "License path ${LICENSE_PATH} does not exists."
      fi
    fi

    if [ x"$UPGRADE" = x'n' ]; then
        if [ -d $ZSTACK_INSTALL_ROOT -o -f $ZSTACK_INSTALL_ROOT ];then
            echo "stop zstack all services" >>$ZSTACK_INSTALL_LOG
            zstack-ctl stop >>$ZSTACK_INSTALL_LOG 2>&1
            fail "$ZSTACK_INSTALL_ROOT is existing. Please delete it manually before installing a new ${PRODUCT_NAME}\n  You might want to save your previous ${PRODUCT_NAME,,}.properties by \`${PRODUCT_NAME,,}-ctl save_config\` and restore it later.\n All ${PRODUCT_NAME} services have been stopped. Run \`${PRODUCT_NAME,,}-ctl start\` to recover."
        fi

        # kill zstack if it's still running
        ZSTACK_PID=`ps aux | grep 'appName=zstack' | grep -v 'grep' | awk '{ print $2 }'`
        [ ! -z $ZSTACK_PID ] && pkill -9 $ZSTACK_PID
    elif [ ! -d $ZSTACK_INSTALL_ROOT -a ! -f $ZSTACK_INSTALL_ROOT ]; then
        fail "$ZSTACK_INSTALL_ROOT does not exist, maybe you need to install a new ${PRODUCT_NAME} instead of upgrading an old one."
    fi

    if [ `whoami` != 'root' ];then
        fail "User checking failure: ${PRODUCT_NAME} installation must be run with user: root . Current user is: `whoami`. Please append 'sudo'."
    fi

    if [ x"$ZSTACK_OFFLINE_INSTALL" = x'n' ];then
        ping -c 1 -w 1 $WEBSITE >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ]; then
            ping -c 1 -w 2 $WEBSITE >>$ZSTACK_INSTALL_LOG 2>&1
            if [ $? -ne 0 ]; then
                ping -c 1 -w 3 $WEBSITE >>$ZSTACK_INSTALL_LOG 2>&1
                if [ $? -ne 0 ]; then
                    fail "Network checking failure: can not reach $WEBSITE. Please make sure your DNS (/etc/resolv.conf) is configured correctly. Or you can override WEBSITE by \`export WEBSITE=YOUR_INTERNAL_YUM_SERVER\` before doing installation. "
                fi
            fi
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
    if [ $? -ne 0 ]; then
        useradd -d $ZSTACK_INSTALL_ROOT zstack >/dev/null >>$ZSTACK_INSTALL_LOG 2>&1
    elif [ $(readlink -f $ZSTACK_INSTALL_ROOT) != $(echo ~zstack) ] ; then
        #stop zstack before change zstack home dir
        which zstack-ctl >/dev/null 2>&1
        if [ $? -eq 0 ] ;then
            echo "\n${PRODUCT_NAME,,} host changed, before: $(echo ~zstack), now: $ZSTACK_INSTALL_ROOT, stopping ${PRODUCT_NAME,,}" >>$ZSTACK_INSTALL_LOG
            zstack-ctl stop >/dev/null 2>&1
        fi

        killall -u zstack >/dev/null 2>&1
        i=5
        while (ps -u zstack > /dev/null) && ((i-- > 0)); do
            sleep 1
        done
        killall -9 -u zstack >/dev/null 2>&1
        usermod -d $ZSTACK_INSTALL_ROOT zstack >/dev/null >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    zstack_home=`eval echo ~zstack`
    if [ ! -d $zstack_home ];then
        mkdir -p $zstack_home >>$ZSTACK_INSTALL_LOG 2>&1
        chown -R zstack:zstack $zstack_home >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    do_enable_sudo
    do_config_limits
    do_check_resolv_conf
    pass
}

ia_check_ip_hijack(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    HOSTNAME=`hostname`

    pintret=`ping -c 1 -W 2 $HOSTNAME 2>/dev/null | head -n1`
    echo $pintret | grep 'PING' > /dev/null
    if [ $? -eq 0 ]; then
        ip=`echo $pintret | cut -d' ' -f 3 | cut -d'(' -f 2 | cut -d')' -f 1`
        ip_1=`echo $ip | cut -d'.' -f 1`
        [ "127" = "$ip_1" ] && return 0

        ip addr | grep $ip > /dev/null
        [ $? -eq 0 ] && return 0

        echo "The hostname($HOSTNAME) of your machine is resolved to IP($ip) which is none of IPs of your machine.
        It's likely your DNS server has been hijacking, please try fixing it or add \"$MANAGEMENT_IP $HOSTNAME\" to /etc/hosts by \n\n \`echo \"$MANAGEMENT_IP $HOSTNAME\" >>/etc/hosts\`.
" >> $ZSTACK_INSTALL_LOG
    fi

    echo "$MANAGEMENT_IP $HOSTNAME" >>/etc/hosts
    CHANGE_HOSTS='$MANAGEMENT_IP $HOSTNAME'
}

ia_install_python_gcc_rh(){
    echo_subtitle "Install Python and GCC"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    req_pkgs='python2 python2-devel gcc'
    [ ! -d /usr/lib64/python2.7/site-packages/pycrypto-2.6.1-py2.7.egg-info ] && req_pkgs=${req_pkgs}" python2-crypto"
    if [ ! -z $ZSTACK_YUM_REPOS ];then
        if [ -z $DEBUG ];then
            yum clean metadata >/dev/null 2>&1
            yum -y --disablerepo="*" --enablerepo=$ZSTACK_YUM_REPOS install $req_pkgs>>$ZSTACK_INSTALL_LOG 2>&1
        else
            yum clean metadata >/dev/null 2>&1
            yum -y --disablerepo="*" --enablerepo=$ZSTACK_YUM_REPOS install $req_pkgs
        fi
    else
        if [ -z $DEBUG ];then
            yum clean metadata >/dev/null 2>&1
            yum -y install $req_pkgs>>$ZSTACK_INSTALL_LOG 2>&1
        else
            yum clean metadata >/dev/null 2>&1
            yum -y install $req_pkgs
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
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    which pip >/dev/null 2>&1 && which pip2 >/dev/null && return

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
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [[ $REDHAT_OS =~ $OS ]]; then
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
    do_config_ansible
    pass
}

ia_install_python_gcc_db(){
    echo_subtitle "Install Python GCC."
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ ! -z $DEBUG ]; then
        apt-get -y install python python-dev gcc
    else
        apt-get -y install python python-dev gcc >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    [ $? -ne 0 ] && fail "Install python and gcc fail."
    pass
}

ia_update_apt(){
    echo_subtitle "Update Apt Source"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    dpkg --configure --force-confold -a >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "execute \`dpkg --onfigure --force-confold -a\` failed."
    #Fix Ubuntu conflicted dpkg lock issue. 
    if [ -f /etc/init.d/unattended-upgrades ]; then
        /etc/init.d/unattended-upgrades stop  >>$ZSTACK_INSTALL_LOG 2>&1
        update-rc.d -f unattended-upgrades remove >>$ZSTACK_INSTALL_LOG 2>&1
        pid=`lsof /var/lib/dpkg/lock|grep lock|awk '{print $2}'`
        [ ! -z $pid ] && kill -9 $pid >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    apt-get clean >>$ZSTACK_INSTALL_LOG 2>&1
    apt-get update -o Acquire::http::No-Cache=True --fix-missing>>$ZSTACK_INSTALL_LOG 2>&1
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
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    show_download iz_download_zstack
    show_spinner uz_stop_zstack_ui
    show_spinner iz_unpack_zstack
}

# create symbol links for zstack-repo
create_symbol_link() {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    mkdir -p ${ZSTACK_HOME}/static/zstack-repo/
    if [ ! -L ${ZSTACK_HOME}/static/zstack-repo/x86_64 ];then
        ln -s /opt/zstack-dvd/x86_64 ${ZSTACK_HOME}/static/zstack-repo/x86_64 >/dev/null 2>&1
        ln -s /opt/zstack-dvd/aarch64 ${ZSTACK_HOME}/static/zstack-repo/aarch64 >/dev/null 2>&1
        ln -s /opt/zstack-dvd/mips64el ${ZSTACK_HOME}/static/zstack-repo/mips64el >/dev/null 2>&1
        ln -s /opt/zstack-dvd/loongarch64 ${ZSTACK_HOME}/static/zstack-repo/loongarch64 >/dev/null 2>&1
    fi
    chown -R zstack:zstack ${ZSTACK_HOME}/static/zstack-repo
}

iu_deploy_zstack_repo() {
    echo_subtitle "Deploy yum repo for ${PRODUCT_NAME}"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

    [ -z "$ZSTACK_RELEASE" ] && fail "failed to get ${PRODUCT_NAME,,} releasever, please make sure ${PRODUCT_NAME,,}-release is installed."
    create_symbol_link
}

iu_deploy_zstack_apt_source() {
    echo_subtitle "Deploy apt source for ${PRODUCT_NAME}"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

    create_symbol_link
}

unpack_zstack_into_tomcat(){
    echo_title "Install ${PRODUCT_NAME} Package"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    which unzip >/dev/null 2>&1
    if [ $? -ne 0 ];then
        show_spinner iz_install_unzip
    fi
    show_spinner iz_unzip_tomcat
    show_spinner iz_install_zstack
    if [[ $REDHAT_OS =~ $OS ]]; then
        show_spinner iu_deploy_zstack_repo
    elif [[ $DEBIAN_OS =~ $OS ]]; then
        show_spinner iu_deploy_zstack_apt_source
    fi
}

upgrade_zstack(){
    echo_title "Upgrade ${PRODUCT_NAME}"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

    if pgrep -x zstack-hamon >/dev/null; then
        fail2 "You are upgrading ${PRODUCT_NAME} under HA environment.\nPlease run: 'zsha2 upgrade-mn ${PRODUCT_NAME,,}-installer.bin' instead.\n"
    fi

    show_spinner uz_upgrade_tomcat
    show_spinner uz_upgrade_zstack_ctl

    # configure management.server.ip if not exists
    zstack-ctl show_configuration | grep '^[[:space:]]*management.server.ip' >/dev/null 2>&1
    [ $? -ne 0 ] && zstack-ctl configure management.server.ip="${MANAGEMENT_IP}"

    # configure chrony.serverIp if not exists
    zstack-ctl show_configuration | grep '^[[:space:]]*chrony.serverIp.' >/dev/null 2>&1
    [ $? -ne 0 ] && zstack-ctl configure chrony.serverIp.0="${MANAGEMENT_IP}"

    if [ ! -z $ONLY_UPGRADE_CTL ]; then
        return
    fi
    #rerun install system libs, upgrade might need new libs
    is_install_system_libs
    do_config_ansible
    show_spinner is_enable_chronyd
    show_spinner uz_stop_zstack
    show_spinner uz_upgrade_zstack
    show_spinner upgrade_tomcat_security
    if [[ $REDHAT_OS =~ $OS ]]; then
        show_spinner iu_deploy_zstack_repo
    elif [[ $DEBIAN_OS =~ $OS ]]; then
        show_spinner iu_deploy_zstack_apt_source
    fi
    show_spinner cp_third_party_tools

    cd /
    show_spinner cs_add_cronjob
    show_spinner cs_install_zstack_service
    show_spinner cs_enable_zstack_service
    show_spinner cs_config_zstack_properties
    show_spinner cs_append_iptables
    show_spinner cs_setup_nginx
    show_spinner cs_enable_usb_storage
    # if -i is used, then do not upgrade zstack ui
    if [ -z $ONLY_INSTALL_ZSTACK ]; then
        if [ x"$UI_INSTALLATION_STATUS" = x'y' -o x"$DASHBOARD_INSTALLATION_STATUS" = x'y' ]; then
            echo "upgrade ${PRODUCT_NAME,,} web ui" >>$ZSTACK_INSTALL_LOG
            rm -f /etc/init.d/zstack-dashboard
            rm -f /etc/init.d/zstack-ui
            show_spinner sd_install_zstack_ui
            zstack-ctl config_ui --init
            # try to deploy zstack_ui database, if already exists then do upgrade
            UI_DATABASE_EXISTS='y'
            mysql -uroot -p"$MYSQL_NEW_ROOT_PASSWORD" -h"$MANAGEMENT_IP" -e "use zstack_ui" >/dev/null 2>&1
            if [ $? -ne 0 ]; then
                UI_DATABASE_EXISTS='n'
            fi

            if [ -z $MYSQL_ROOT_PASSWORD ]; then
                if [ x"$UI_DATABASE_EXISTS" = x'n' ]; then
                    zstack-ctl deploy_ui_db --root-password="${MYSQL_NEW_ROOT_PASSWORD}" --zstack-ui-password="$MYSQL_UI_USER_PASSWORD" --host="$MANAGEMENT_IP" --port=${MYSQL_PORT} >>$ZSTACKCTL_INSTALL_LOG 2>&1
                fi
            else
                if [ x"$UI_DATABASE_EXISTS" = x'n' ]; then
                    zstack-ctl deploy_ui_db --root-password="${MYSQL_ROOT_PASSWORD}" --zstack-ui-password="$MYSQL_UI_USER_PASSWORD" --host="$MANAGEMENT_IP" --port=${MYSQL_PORT} >>$ZSTACKCTL_INSTALL_LOG 2>&1
                fi
            fi

            show_spinner uz_upgrade_zstack_ui_db
        fi
    elif [ -f /etc/init.d/zstack-ui ]; then
        # fill CATALINA_ZSTACK_TOOLS with old zstack_ui.bin if not exists
        /bin/cp -n $ZSTACK_INSTALL_ROOT/zstack-ui/zstack_ui.bin $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_TOOLS >/dev/null 2>&1
    fi

    #check old license folder and copy old license files to new folder.
    if [ -d $ZSTACK_OLD_LICENSE_FOLDER ] && [ ! -d $LICENSE_FOLDER ]; then
        mv $ZSTACK_OLD_LICENSE_FOLDER  $LICENSE_FOLDER >>$ZSTACK_INSTALL_LOG 2>&1
        chown -R zstack:zstack $LICENSE_FOLDER >>$ZSTACK_INSTALL_LOG 2>&1
    fi

    # check whether needs to install license or not
    # - If no mevoco.jar found, do not install license
    # - If both mevoco.jar and license.txt exist, do not install license
    # - If mevoco-2.*.jar exists but license.txt not exist, do not install license
    # - If mevoco-1.*.jar exists but license.txt not exists, then install license
    if [ x"$MEVOCO_1_EXISTS" = x'y' ]; then
        if [ ! -f $LICENSE_FOLDER/license.txt ]; then
            if [ -f $LICENSE_FOLDER/zstack_trial_license ]; then
                zstack-ctl install_license --license $LICENSE_FOLDER/zstack_trial_license >>$ZSTACK_INSTALL_LOG 2>&1
            fi
        fi
    fi

    upgrade_mini_persist_params

    #set zstack upgrade params 
    upgrade_params=''
    post_upgrade_version=`zstack-ctl get_version`
    echo "CURRENT_VERSION: $CURRENT_VERSION" >>$ZSTACK_INSTALL_LOG
    echo "post_upgrade_version: $post_upgrade_version" >>$ZSTACK_INSTALL_LOG
    for item in ${upgrade_params_array[*]}; do
        version=`echo $item | cut -d ',' -f 1`
        param=`echo $item | cut -d ',' -f 2`

        # pre < version && version <= post
        vercomp ${CURRENT_VERSION} ${version}; cmp1=$?
        vercomp ${version} ${post_upgrade_version}; cmp2=$?
        if [ ${cmp1} -eq 2 -a ${cmp2} -ne 1 ]; then
            upgrade_params="${upgrade_params} ${param}"
        fi
    done
    echo "upgrade_params: $upgrade_params" >>$ZSTACK_INSTALL_LOG
    [ ! -z "$upgrade_params" ] && zstack-ctl setenv ZSTACK_UPGRADE_PARAMS=$upgrade_params

    upgrade_persist_params=''
    for item in ${upgrade_persist_params_array[*]}; do
        version=`echo $item | cut -d ',' -f 1`
        param=`echo $item | cut -d ',' -f 2`

        # pre < version
        vercomp ${CURRENT_VERSION} ${version}; cmp1=$?
        if [ ${cmp1} -eq 2 ]; then
            upgrade_persist_params="${param}"
        fi
        echo "upgrade_persist_params: $upgrade_persist_params" >>$ZSTACK_INSTALL_LOG
    [ ! -z "$upgrade_persist_params" ] && zstack-ctl configure $upgrade_persist_params
    done


    # set ticket.sns.topic.http.url if not exists
    zstack-ctl show_configuration | grep 'ticket.sns.topic.http.url' >/dev/null 2>&1
    [ $? -ne 0 ] && zstack-ctl configure ticket.sns.topic.http.url=http://localhost:5000/zwatch/webhook

    # set sns.systemTopic.endpoints.http.url if not exists
    zstack-ctl show_configuration | grep 'sns.systemTopic.endpoints.http.url' >/dev/null 2>&1
    [ $? -ne 0 ] && zstack-ctl configure sns.systemTopic.endpoints.http.url=http://localhost:5000/zwatch/webhook

    # upgrade legacy mini zwatch webhook
    upgrade_mini_zwatch_webhook

    # update consoleProxyCertFile if necessary
    certfile=`zstack-ctl show_configuration | grep consoleProxyCertFile | grep /usr/local/zstack/zstack-ui/ | awk -F '=' '{ print $NF }'`
    [ x"$certfile" != x"" ] && zstack-ctl configure consoleProxyCertFile=`echo $certfile | sed "s~/usr/local/zstack/~$ZSTACK_INSTALL_ROOT/~g"`

    #When using -i option, will not upgrade kariosdb and not start zstack
    if [ -z $ONLY_INSTALL_ZSTACK ]; then

        #when using -k option, will not start zstack.
        if [ -z $NEED_KEEP_DB ] && [ $CURRENT_STATUS = 'y' ] && [ -z $NOT_START_ZSTACK ]; then
            show_spinner sz_start_zstack
            echo "start zstack-ui" >>$ZSTACK_INSTALL_LOG
            show_spinner sd_start_zstack_ui
        fi
    fi
}

cs_pre_check(){
    echo_subtitle "Pre-Checking"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

    if [ -f $PRODUCT_TITLE_FILE ]; then
        #check cpu number
        current_cpu=`cat /proc/cpuinfo |grep processor|wc -l`
        if [ $current_cpu -lt 4 ]; then
            fail "Your system only has $current_cpu CPUs. $PRODUCT_NAME needs at least 4 CPUs."
        fi
        current_memory=`free -m|grep Mem|awk '{print $2}'`
        # Save some memory for kdump etc.
        if [ $current_memory -lt 7168 ]; then
            fail "Your system only has $current_memory MB memory. $PRODUCT_NAME needs at least 8 GB memory, we recommend 12 GB."
        fi
    fi
    #change zstack.properties config
    if [ x"$UPGRADE" != x'n' ]; then
        sharedblock_check_qcow2_volume
        zstack_properties=`zstack-ctl status 2>/dev/null|grep zstack.properties|awk '{print $2}'`
    else
        zstack_properties=$ZSTACK_INSTALL_ROOT/$ZSTACK_PROPERTIES
    fi
    [ -f $zstack_properties ] && sed -i 's/Ansible.var.yum_repo/Ansible.var.zstack_repo/' $zstack_properties >>$ZSTACK_INSTALL_LOG 2>&1
    pass
}

sharedblock_check_qcow2_volume(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    vercomp '3.7.0' ${CURRENT_VERSION}; cmp=$?
    if [ ${cmp} -ne 1 ]; then
        return
    fi

    db_ip=`zstack-ctl getenv MYSQL_LATEST_IP | awk -F '=' '{print $2}'`
    db_port=`zstack-ctl getenv MYSQL_LATEST_PORT | awk -F '=' '{print $2}'`
    db_username=`zstack-ctl show_configuration | grep DB.user | awk -F '=' '{print $2}' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'`
    db_password=`zstack-ctl show_configuration | grep DB.password | awk -F '=' '{print $2}' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'`
    if [ x"$db_password" != "x" ]; then
        mysql --vertical -h $db_ip -P $db_port -u $db_username -p$db_password zstack -e 'select count(vol.uuid) from VolumeVO vol, PrimaryStorageVO ps where ps.Type="sharedblock" and vol.primaryStorageUuid = ps.uuid and vol.isShareable <> 0 and vol.format ="qcow2"' >>$ZSTACK_INSTALL_LOG 2>&1
        sql_running=$?
        result=`mysql --vertical -h $db_ip -P $db_port -u $db_username -p$db_password zstack -e 'select count(vol.uuid) from VolumeVO vol, PrimaryStorageVO ps where ps.Type="sharedblock" and vol.primaryStorageUuid = ps.uuid and vol.isShareable <> 0 and vol.format ="qcow2"' | grep count | awk -F ':' '{print $2}' | tr -d '[:space:]'`
    else
        mysql --vertical -h $db_ip -P $db_port -u $db_username zstack -e 'select count(vol.uuid) from VolumeVO vol, PrimaryStorageVO ps where ps.Type="sharedblock" and vol.primaryStorageUuid = ps.uuid and vol.isShareable <> 0 and vol.format ="qcow2"' >>$ZSTACK_INSTALL_LOG 2>&1
        sql_running=$?
        result=`mysql --vertical -h $db_ip -P $db_port -u $db_username zstack -e 'select count(vol.uuid) from VolumeVO vol, PrimaryStorageVO ps where ps.Type="sharedblock" and vol.primaryStorageUuid = ps.uuid and vol.isShareable <> 0 and vol.format ="qcow2"' | grep count | awk -F ':' '{print $2}' | tr -d '[:space:]'`
    fi
    if [ x"$sql_running" != x'0' ]; then
        echo "can not connect to mysql or execute sql, skip check qcow2 shared volume" >>$ZSTACK_INSTALL_LOG 2>&1
        return
    fi
    if [ x"$result" != x'0' ]; then
        fail "There are $result qcow2 format shared volume on sharedblock group primary storage, please contact technical support to convert volumes and then upgrade zstack"
    fi
}

install_ansible(){
    echo_title "Install Ansible"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [[ $REDHAT_OS =~ $OS ]]; then
        show_spinner ia_disable_selinux
        show_spinner ia_install_python_gcc_rh
    elif [[ $DEBIAN_OS =~ $OS ]]; then
        #if [ -z $ZSTACK_PKG_MIRROR ]; then
        #    show_spinner ia_update_apt
        #fi
        show_spinner ia_install_python_gcc_db
    fi
    show_spinner ia_install_ansible
}

iz_install_unzip(){
    echo_subtitle "Install unzip"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [[ $DEBIAN_OS =~ $OS ]]; then
        apt-get -y install unzip >>$ZSTACK_INSTALL_LOG 2>&1
        [ $? -ne 0 ] && fail "Install unzip fail."
        pass
        return
    fi

    if [ ! -z $ZSTACK_YUM_REPOS ];then
        yum clean metadata >/dev/null 2>&1
        yum -y --disablerepo="*" --enablerepo=$ZSTACK_YUM_REPOS install unzip>>$ZSTACK_INSTALL_LOG 2>&1
    else
        yum clean metadata >/dev/null 2>&1
        yum -y install $req_pkgs>>$ZSTACK_INSTALL_LOG 2>&1
    fi

    if [ $? -ne 0 ]; then
        fail "Install unzip fail."
    fi
    pass
}

is_install_general_libs_rh(){
    echo_subtitle "Install General Libraries (takes a couple of minutes)"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

    # Fix upgrade dependency conflicts
    if [ "$ZSTACK_RELEASE" == "ns10" ]; then
      vercomp "14.16.0" `rpm -q nodejs | awk -F '-' '{print $2}'`
      [ $? -eq 1 ] && removeable="nodejs" || removeable=""
      yum remove -y redis5 $removeable >>$ZSTACK_INSTALL_LOG 2>&1
    fi

    # Just install what is not installed
    deps_list="libselinux-python \
            java-1.8.0-openjdk \
            java-1.8.0-openjdk-devel \
            bridge-utils \
            wget \
            nfs-utils \
            rpcbind \
            vconfig \
            vim-minimal \
            python2-devel \
            gcc \
            grafana \
            autoconf \
            chrony \
            iptables \
            iptables-services \
            tar \
            gzip \
            unzip \
            httpd \
            openssh \
            openssh-clients \
            openssh-server \
            rsync \
            sshpass \
            sudo \
            bzip2 \
            libffi-devel \
            openssl-devel \
            net-tools \
            bash-completion \
            dmidecode \
            MySQL-python \
            ipmitool \
            nginx \
            psmisc \
            python2-backports-ssl_match_hostname \
            python2-setuptools \
            avahi \
            gnutls-utils \
            avahi-tools \
            audit \
            redis \
            nodejs"
    if [ "$BASEARCH" == "x86_64" ]; then
      deps_list="${deps_list} mcelog"
    fi
    always_update_list="openssh"
    missing_list=`LANG=en_US.UTF-8 && rpm -q $deps_list | grep 'not installed' | awk 'BEGIN{ORS=" "}{ print $2 }'`

    [ x"$ZSTACK_OFFLINE_INSTALL" = x'y' ] && missing_list=$deps_list
    if [ ! -z $ZSTACK_YUM_REPOS ]; then
        yum --disablerepo="*" --enablerepo=$ZSTACK_YUM_REPOS clean metadata >/dev/null 2>&1
        echo yum install --disablerepo="*" --enablerepo=$ZSTACK_YUM_REPOS -y general libs... >>$ZSTACK_INSTALL_LOG
        yum install --disablerepo="*" --enablerepo=$ZSTACK_YUM_REPOS -y $always_update_list $missing_list >>$ZSTACK_INSTALL_LOG 2>&1
    else
        yum clean metadata >/dev/null 2>&1
        echo "yum install -y libselinux-python java ..." >>$ZSTACK_INSTALL_LOG
        yum install -y $always_update_list $missing_list >>$ZSTACK_INSTALL_LOG 2>&1
    fi

    if [ $? -ne 0 ];then
        #yum clean metadata >/dev/null 2>&1
        fail "install system libraries failed."
    fi

    rpm -q java-1.8.0-openjdk >>$ZSTACK_INSTALL_LOG 2>&1 || java -version 2>&1 |grep 1.8 >/dev/null
    if [ $? -ne 0 ]; then
        fail "java-1.8.0-openjdk is not installed. Did you forget updating management node local repos to latest ${PRODUCT_NAME} ISO? Please use following steps to update local repos:
        1. # cd /opt
        2. # wget http://cdn.zstack.io/product_downloads/scripts/${PRODUCT_NAME,,}-upgrade
        3. download the latest ${PRODUCT_NAME} ISO from http://www.zstack.io/product_downloads into /opt
        4. # bash ${PRODUCT_NAME,,}-upgrade -r PATH_TO_LATEST_ZSTACK_ISO
        "
    else
        #yum clean metadata >/dev/null 2>&1
        #set java 8 as default jre.
        update-alternatives --install /usr/bin/java java /usr/lib/jvm/jre-1.8.0/bin/java 0 >>$ZSTACK_INSTALL_LOG 2>&1
        update-alternatives --set java /usr/lib/jvm/jre-1.8.0/bin/java >>$ZSTACK_INSTALL_LOG 2>&1
        pass
    fi
}

is_install_virtualenv(){
    echo_subtitle "Install Virtualenv"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
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
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    id -u nginx >/dev/null 2>&1 || useradd nginx >/dev/null 2>&1

    if [[ $DEBIAN_OS =~ $OS ]]; then
        #install openjdk ppa for openjdk-8

        # add-apt-repository ppa:openjdk-r/ppa -y >>$ZSTACK_INSTALL_LOG 2>&1
        apt-key update >>$ZSTACK_INSTALL_LOG 2>&1
        apt-get update >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    apt-get -y install --allow-unauthenticated \
        openjdk-8-jdk \
        bridge-utils \
        wget \
        auditd \
        curl \
        vlan \
        python-dev \
        python-pip \
        gcc \
        chrony \
        python-setuptools \
        >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "install system lib 1 failed"

    apt-get -y install --no-upgrade --allow-unauthenticated \
        sudo \
        >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "install system lib 2 failed"

    apt-get -y install --allow-unauthenticated \
        dmidecode \
        nfs-common \
        nfs-kernel-server \
        autoconf \
        netfilter-persistent \
        tar \
        gzip \
        grafana \
        sqlite3 \
        unzip \
        apache2 \
        rsync \
        sshpass \
        bzip2 \
        libffi-dev \
        libssl-dev \
        bash-completion \
        gnutls-bin \
        redis \
        nginx \
        nodejs \
        >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "install system lib 2 failed"

    if [ $OS == "UBUNTU14.04" ]; then
        #set java 8 as default jre.
        update-alternatives --install /usr/bin/java java /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java 0 >>$ZSTACK_INSTALL_LOG 2>&1
        update-alternatives --install /usr/bin/javac javac /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/javac 0 >>$ZSTACK_INSTALL_LOG 2>&1
        update-alternatives --set java /usr/lib/jvm/java-8-openjdk-amd64/jre/bin/java >>$ZSTACK_INSTALL_LOG 2>&1
        update-alternatives --set javac /usr/lib/jvm/java-8-openjdk-amd64/bin/javac >>$ZSTACK_INSTALL_LOG 2>&1
        #no service iptables
        [ ! -f /etc/init.d/iptables ] && [ -f /etc/init.d/iptables-persistent ] \
            && ln -s /etc/init.d/iptables-persistent /etc/init.d/iptables
    else
        #iptables-persistent broken from 14.04 to 16.04
        [ ! -f /etc/init.d/iptables-persistent ] && [ -f /etc/init.d/netfilter-persistent ] \
            && ln -s /etc/init.d/netfilter-persistent /etc/init.d/iptables-persistent
        [ ! -f /etc/init.d/iptables ] && [ -f /etc/init.d/netfilter-persistent ] \
            && ln -s /etc/init.d/netfilter-persistent /etc/init.d/iptables
        sudo /bin/systemctl daemon-reload >>$ZSTACK_INSTALL_LOG 2>&1
        sudo /bin/systemctl enable grafana-server >>$ZSTACK_INSTALL_LOG 2>&1
        sudo /bin/systemctl start grafana-server >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    pass
}

is_install_system_libs(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [[ $REDHAT_OS =~ $OS ]]; then
        show_spinner is_install_general_libs_rh
    else
        show_spinner is_install_general_libs_deb
    fi
}

install_system_libs(){
    echo_title "Install System Libs"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    is_install_system_libs
    #mysql will be installed by zstack-ctl later
    show_spinner ia_install_pip
    show_spinner is_install_virtualenv
    #enable chronyd
    show_spinner is_enable_chronyd
}

is_enable_chronyd(){
    echo_subtitle "Enable chronyd"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [[ $REDHAT_OS =~ $OS ]];then
        if [ x"$ZSTACK_OFFLINE_INSTALL" = x'n' ];then
            grep '^server 0.centos.pool.ntp.org' /etc/chrony.conf >/dev/null 2>&1
            if [ $? -ne 0 ]; then
                echo "server 0.pool.ntp.org iburst" >> /etc/chrony.conf
                echo "server 1.pool.ntp.org iburst" >> /etc/chrony.conf
            fi
        fi
        grep "^local stratum " -q /etc/chrony.conf >/dev/null 2>&1
        if [ $? -ne 0 ];then
            echo "local stratum 10" >> /etc/chrony.conf
        fi
        grep "^allow" -q /etc/chrony.conf >/dev/null 2>&1
        if [ $? -ne 0 ];then
            echo "allow 0.0.0.0/0" >> /etc/chrony.conf
        fi

        systemctl disable ntpd >> $ZSTACK_INSTALL_LOG 2>&1 || true
        systemctl enable chronyd.service >> $ZSTACK_INSTALL_LOG 2>&1
        systemctl restart chronyd.service >> $ZSTACK_INSTALL_LOG 2>&1
    else
        if [ x"$ZSTACK_OFFLINE_INSTALL" = x'n' ];then
            grep '^server 0.ubuntu.pool.ntp.org' /etc/chrony.conf >/dev/null 2>&1
            if [ $? -ne 0 ]; then
                echo "server 0.ubuntu.pool.ntp.org" >> /etc/chrony.conf
                echo "server ntp.ubuntu.com" >> /etc/chrony.conf
            fi
        fi
        grep "^local stratum " -q /etc/chrony.conf >/dev/null 2>&1
        if [ $? -ne 0 ];then
            echo "local stratum 10" >> /etc/chrony.conf
        fi
        grep "^allow" -q /etc/chrony.conf >/dev/null 2>&1
        if [ $? -ne 0 ];then
            echo "allow 0.0.0.0/0" >> /etc/chrony.conf
        fi
        update-rc.d chrony defaults >>$ZSTACK_INSTALL_LOG 2>&1
        service chrony restart >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    if [ $? -ne 0 ];then
        fail "failed to enable chrony service."
    fi

    pass
}

iz_download_zstack(){
    echo_subtitle "Download ${PRODUCT_NAME} package"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ -f $ZSTACK_ALL_IN_ONE ]; then
        cp $ZSTACK_ALL_IN_ONE $zstack_tmp_file >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ];then
           /bin/rm -f $zstack_tmp_file
           fail "failed to copy ${PRODUCT_NAME,,} all-in-one package from $ZSTACK_ALL_IN_ONE to $zstack_tmp_file"
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
                fail "need 'wget' or 'curl' to download ${PRODUCT_NAME,,} all in one package."
            fi 
        fi
        if [ $? -ne 0 ];then
           /bin/rm -f $zstack_tmp_file
           fail "failed to download ${PRODUCT_NAME,,} all-in-one package from $ZSTACK_ALL_IN_ONE"
        fi
    fi
    pass 
}

iz_unpack_zstack(){
    echo_subtitle "Unpack ${PRODUCT_NAME} package"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ x"$UPGRADE" = x'n' ]; then
        mkdir -p $ZSTACK_INSTALL_ROOT
        all_in_one=$ZSTACK_INSTALL_ROOT/zstack_all_in_one.tgz
        mv $zstack_tmp_file $all_in_one
        cd $ZSTACK_INSTALL_ROOT
        tar -zxf $all_in_one >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ];then
           fail "failed to unpack ${PRODUCT_NAME} package: $all_in_one."
        fi
        current_date=`date +%s`
        zstack_build_time=`stat zstack.war|grep Modify|awk '{ print substr($0, index($0,$2)) }'`
        zstack_build_date=`date --date="$zstack_build_time" +%s`
        if [ $zstack_build_date -gt $current_date ]; then
            fail "Your system time is earlier than ${PRODUCT_NAME} build time: $zstack_build_time . Please fix it."
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
        current_date=`date +%s`
        zstack_build_time=`stat zstack.war|grep Modify|awk '{ print substr($0, index($0,$2)) }'`
        zstack_build_date=`date --date="$zstack_build_time" +%s`
        if [ $zstack_build_date -gt $current_date ]; then
            fail "Your system time is earlier than ${PRODUCT_NAME} build time: $zstack_build_time . Please fix it."
        fi
    fi
    pass
}

uz_stop_zstack(){
    echo_subtitle "Stop ${PRODUCT_NAME}"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    zstack-ctl stop >>$ZSTACK_INSTALL_LOG 2>&1
    # make sure zstack is stopped
    ps axu | grep java | grep 'appName=zstack' >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -eq 0 ];then
        fail "Stop ${PRODUCT_NAME,,} failed!"
    fi
    pass
}

uz_stop_zstack_ui(){
    echo_subtitle "Stop ${PRODUCT_NAME} UI"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ -e $ZSTACK_HOME ]
    then
        zstack-ctl stop_ui >>$ZSTACK_INSTALL_LOG 2>&1
        sleep 3
        # make sure zstack ui is stopped
        zstack-ctl ui_status 2>/dev/null |grep 'UI status'|grep Running >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            fail "Failed to stop ${PRODUCT_NAME} UI! Maybe run zstack-ctl stop_ui by youself"
        fi
    elif [ -e "/var/run/zstack/zstack-ui.pid" ]
    then
        PID=`cat /var/run/zstack/zstack-ui.pid`
        if [ -n "$PID" ]
        then
            echo `kill -9 $PID`
        fi
    fi 
    if [ -d ${LEGACY_MINI_INSTALL_ROOT} -o -d ${MINI_INSTALL_ROOT} ]; then
        systemctl stop zstack-mini
        ps -ef | grep -w mini-server | grep -w java | grep -v 'grep' >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -eq 0 ]; then
            fail "Failed to stop ${PRODUCT_NAME} MINI UI!"
        fi
    fi
    pass
}

uz_upgrade_tomcat(){
    echo_subtitle "Upgrade apache-tomcat"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    ZSTACK_HOME=${ZSTACK_HOME:-`zstack-ctl getenv ZSTACK_HOME | awk -F '=' '{ print $2 }'`}
    ZSTACK_HOME=${ZSTACK_HOME:-"/usr/local/zstack/apache-tomcat/webapps/zstack/"}
    TOMCAT_PATH=${ZSTACK_HOME%/apache-tomcat*}

    local TOMCAT_FILE_OLD=$(basename $TOMCAT_PATH/apache-tomcat-*.zip)
    local TOMCAT_FILE_NEW=$(basename $upgrade_folder/apache-tomcat-*.zip)
    local TOMCAT_NAME_OLD=${TOMCAT_FILE_OLD%.*}
    local TOMCAT_NAME_NEW=${TOMCAT_FILE_NEW%.*}

    cd $upgrade_folder
    if [ "$TOMCAT_NAME_OLD" != "$TOMCAT_NAME_NEW" ]; then
        /bin/cp $TOMCAT_NAME_NEW.zip $TOMCAT_PATH
        unzip -o -d $TOMCAT_PATH $TOMCAT_NAME_NEW.zip >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ];then
           fail "failed to unzip Tomcat package: $upgrade_folder/$TOMCAT_NAME_NEW.zip."
        fi

        cd $TOMCAT_PATH
        rm -rf $TOMCAT_NAME_NEW/{webapps,logs}/*
        /bin/mv $TOMCAT_NAME_OLD/logs/* $TOMCAT_NAME_NEW/logs/
        /bin/mv $TOMCAT_NAME_OLD/bin/setenv.sh $TOMCAT_NAME_NEW/bin/
        /bin/mv $TOMCAT_NAME_OLD/webapps/zstack $TOMCAT_NAME_NEW/webapps/
        unzip -o -d $TOMCAT_NAME_NEW/webapps $upgrade_folder/libs/tomcat_root_app.zip >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ];then
           fail "failed to unzip Tomcat package: $upgrade_folder/libs/tomcat_root_app.zip."
        fi

        rm -rf $TOMCAT_NAME_OLD.zip $TOMCAT_NAME_OLD apache-tomcat VERSION
        ln -sf $TOMCAT_NAME_NEW apache-tomcat
        ln -sf apache-tomcat/webapps/zstack/VERSION VERSION
        chown -R zstack:zstack $TOMCAT_NAME_NEW.zip $TOMCAT_NAME_NEW apache-tomcat VERSION
        cd $upgrade_folder

        chmod a+x $TOMCAT_PATH/apache-tomcat/bin/*
        if [ $? -ne 0 ];then
           fail "chmod failed in: $TOMCAT_PATH/apache-tomcat/bin/*."
        fi

        #If tomcat use the default conf update it
        set_tomcat_config
    fi

    pass
}

uz_upgrade_zstack_ctl(){
    echo_subtitle "Upgrade ${PRODUCT_NAME,,}-ctl"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
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
        fail "failed to upgrade ${PRODUCT_NAME,,}-ctl"
    fi

    pass
}

get_mysql_conf_file(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ -f /etc/mysql/mariadb.conf.d/50-server.cnf ]; then
        #ubuntu 16.04
        MYSQL_CONF_FILE=/etc/mysql/mariadb.conf.d/50-server.cnf
    elif [ -f /etc/mysql/my.cnf ]; then
        # Ubuntu 14.04
        MYSQL_CONF_FILE=/etc/mysql/my.cnf
    elif [ -f /etc/my.cnf ]; then
        # centos
        MYSQL_CONF_FILE=/etc/my.cnf
    fi
}

upgrade_mysql_configuration(){
    echo "modify my.cnf" >>$ZSTACK_INSTALL_LOG 2>&1
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    get_mysql_conf_file

    grep 'log_bin_trust_function_creators=' $MYSQL_CONF_FILE >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "log_bin_trust_function_creators=1" >>$ZSTACK_INSTALL_LOG 2>&1
        sed -i '/\[mysqld\]/a log_bin_trust_function_creators=1\' $MYSQL_CONF_FILE
    fi

    # Fixes ZSTAC-24460
    # if max_allowed_packet is not configured, then update from default value 1M to 2M
    grep 'max_allowed_packet' $MYSQL_CONF_FILE >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "max_allowed_packet=2M" >>$ZSTACK_INSTALL_LOG 2>&1
        sed -i '/\[mysqld\]/a max_allowed_packet=2M\' $MYSQL_CONF_FILE
    fi

    if [ "$IS_UBUNTU" = "y" ]; then
        service mysql restart >>$ZSTACK_INSTALL_LOG 2>&1
    else
        systemctl restart mariadb.service >>$ZSTACK_INSTALL_LOG 2>&1
    fi
}

uz_upgrade_zstack(){
    echo_subtitle "Upgrade ${PRODUCT_NAME}"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    cd $upgrade_folder

    #Do not upgrade db, when using -i or -k
    if [ -z $ONLY_INSTALL_ZSTACK ] && [ -z $NEED_KEEP_DB ]; then
        upgrade_mysql_configuration
        if [ ! -z $DEBUG ]; then
            if [ x"$FORCE" = x'n' ];then
                zstack-ctl upgrade_db --dry-run
            else
                zstack-ctl upgrade_db --dry-run --force
            fi
        else
            if [ x"$FORCE" = x'n' ];then
                zstack-ctl upgrade_db --dry-run >>$ZSTACK_INSTALL_LOG 2>&1
            else
                zstack-ctl upgrade_db --dry-run --force >>$ZSTACK_INSTALL_LOG 2>&1
            fi
        fi
        if [ $? -ne 0 ];then
            cd /; rm -rf $upgrade_folder
            if [ x"$FORCE" = x'n' ]; then
                fail "Database upgrading dry-run failed. You probably should check SQL file conflict, or use -F option to force upgrade."
            else
                fail "Database upgrading dry-run failed. You probably should check SQL file conflict."
            fi
        fi
    fi

    if [ ! -z $DEBUG ]; then
        bash zstack/WEB-INF/classes/tools/install.sh zstack-cli
    else
        bash zstack/WEB-INF/classes/tools/install.sh zstack-cli >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    if [ $? -ne 0 ];then
        cd /; rm -rf $upgrade_folder
        fail "failed to upgrade ${PRODUCT_NAME,,}-cli"
    fi

    bash ${zstore_bin} >>$ZSTACK_INSTALL_LOG 2>&1
    chown -R zstack:zstack $ZSTACK_INSTALL_ROOT/imagestore >/dev/null 2>&1

    if [ ! -z $DEBUG ]; then
        zstack-ctl upgrade_management_node --war-file $upgrade_folder/zstack.war 
    else
        zstack-ctl upgrade_management_node --war-file $upgrade_folder/zstack.war >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    if [ $? -ne 0 ];then
        cd /; rm -rf $upgrade_folder
        fail "failed to upgrade local management node"
    fi

    #Do not upgrade db, when using -i
    if [ -z $ONLY_INSTALL_ZSTACK ] ; then
        cd /; rm -rf $upgrade_folder

        if [ -z $NEED_KEEP_DB ];then
            if [ ! -z $DEBUG ]; then
                if [ x"$FORCE" = x'n' ];then
                    zstack-ctl upgrade_db --update-schema-version
                else
                    zstack-ctl upgrade_db --force --update-schema-version
                fi
            else
                if [ x"$FORCE" = x'n' ];then
                    zstack-ctl upgrade_db --update-schema-version >>$ZSTACK_INSTALL_LOG 2>&1
                else
                    zstack-ctl upgrade_db --force --update-schema-version >>$ZSTACK_INSTALL_LOG 2>&1
                fi
            fi
        fi 

        if [ $? -ne 0 ];then
            fail "failed to upgrade database"
        fi
    fi

    pass
}

uz_upgrade_zstack_ui_db(){
    echo_subtitle "Upgrade ${PRODUCT_NAME} UI Database"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

    #Do not upgrade zstack_ui db when using -k
    if [ -z $NEED_KEEP_DB ]; then
        upgrade_mysql_configuration

        # upgrade zstack_ui database --dry-run
        if [ ! -z $DEBUG ]; then
            if [ x"$FORCE" = x'n' ];then
                zstack-ctl upgrade_ui_db --dry-run
            else
                zstack-ctl upgrade_ui_db --dry-run --force
            fi
        else
            if [ x"$FORCE" = x'n' ];then
                zstack-ctl upgrade_ui_db --dry-run >>$ZSTACK_INSTALL_LOG 2>&1
            else
                zstack-ctl upgrade_ui_db --dry-run --force >>$ZSTACK_INSTALL_LOG 2>&1
            fi
        fi
        if [ $? -ne 0 ];then
            if [ x"$FORCE" = x'n' ]; then
                fail "${PRODUCT_NAME} UI Database upgrading dry-run failed. You probably should check SQL file conflict, or use -F option to force upgrade."
            else
                fail "${PRODUCT_NAME} UI Database upgrading dry-run failed. You probably should check SQL file conflict."
            fi
        fi
    fi

    if [ -z $NEED_KEEP_DB ];then
        # upgrade zstack_ui database
        if [ ! -z $DEBUG ]; then
            if [ x"$FORCE" = x'n' ];then
                zstack-ctl upgrade_ui_db
            else
                zstack-ctl upgrade_ui_db --force
            fi
        else
            if [ x"$FORCE" = x'n' ];then
                zstack-ctl upgrade_ui_db >>$ZSTACK_INSTALL_LOG 2>&1
            else
                zstack-ctl upgrade_ui_db --force >>$ZSTACK_INSTALL_LOG 2>&1
            fi
        fi
    fi
    if [ $? -ne 0 ];then
        fail "failed to upgrade ${PRODUCT_NAME,,}_ui database"
    fi

    pass
}

iz_unzip_tomcat(){
    echo_subtitle "Unpack Tomcat"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
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

    #delete unused web app folders, 'ROOT' should be left
    find $ZSTACK_INSTALL_ROOT/apache-tomcat/webapps -mindepth 1 -not -name 'ROOT' -delete

    unzip -o -d apache-tomcat/webapps/ libs/tomcat_root_app.zip >>$ZSTACK_INSTALL_LOG 2>&1
    chmod a+x apache-tomcat/bin/*
    if [ $? -ne 0 ];then
       fail "chmod failed in: $ZSTACK_INSTALL_ROOT/apache-tomcat/bin/*."
    fi

    pass
}

iz_install_zstack(){
    echo_subtitle "Install ${PRODUCT_NAME} into Tomcat"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
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
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    cd $ZSTACK_INSTALL_ROOT
    bash $ZSTACK_TOOLS_INSTALLER zstack-cli >>$ZSTACK_INSTALL_LOG 2>&1

    if [ $? -ne 0 ];then
       fail "failed to install ${PRODUCT_NAME,,}-cli in $ZSTACK_INSTALL_ROOT/$ZSTACK_TOOLS_INSTALLER"
    fi

    bash ${zstore_bin} >>$ZSTACK_INSTALL_LOG 2>&1
    chown -R zstack:zstack $ZSTACK_INSTALL_ROOT/imagestore >/dev/null 2>&1
    pass
}

iz_install_zstackctl(){
    echo_subtitle "Install ${PRODUCT_NAME} Control Tool"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    cd $ZSTACK_INSTALL_ROOT
    bash $ZSTACK_TOOLS_INSTALLER zstack-ctl >>$ZSTACK_INSTALL_LOG 2>&1

    if [ $? -ne 0 ];then
       fail "failed to install ${PRODUCT_NAME,,}-ctl in $ZSTACK_INSTALL_ROOT/$ZSTACK_TOOLS_INSTALLER"
    fi
    pass
}

install_zstack_network()
{
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ "$BASEARCH" == 'x86_64' ]; then
        zsn_agent='zsn-agent.bin'
    else
        zsn_agent="zsn-agent.$BASEARCH.bin"
    fi
    bash $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_CLASSES/ansible/zsnagentansible/${zsn_agent}
    /bin/cp -f /usr/local/zstack/zsn-agent/bin/zstack-network-agent.service /usr/lib/systemd/system/
    pkill zsn-agent
    systemctl daemon-reload
    systemctl enable zstack-network-agent.service
    systemctl restart zstack-network-agent.service
} >>$ZSTACK_INSTALL_LOG 2>&1

cp_virtio_drivers(){
    if [ ! -e $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_TOOLS/virtio-drivers ]; then
        mkdir $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_TOOLS/virtio-drivers
    fi
    if [ "$BASEARCH" == 'aarch64' -o "$BASEARCH" == 'mips64el' -o "$BASEARCH" == 'loongarch64' ]; then
        return
    fi
    if [ -e "/opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/virtio-win_x86.vfd" ]; then
        /bin/cp /opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/virtio-win_x86.vfd $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_TOOLS/virtio-drivers/
    fi
    if [ -e "/opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/virtio-win_amd64.vfd" ]; then
        /bin/cp /opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/virtio-win_amd64.vfd $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_TOOLS/virtio-drivers/
    fi
}

cp_third_party_tools(){
    echo_subtitle "Copy third-party tools to ${PRODUCT_NAME} install path"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ -d "/opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/tools" ]; then
        /bin/cp -rn /opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/tools/* $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_TOOLS >/dev/null 2>&1
        chown -R zstack.zstack $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_TOOLS/*
    fi
    cp_virtio_drivers
    install_zstack_network
    pass
}

install_zstack(){
    echo_title "Install ${PRODUCT_NAME} Tools"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    echo ""
    show_spinner iz_chown_install_root
    show_spinner iz_install_zstackcli
    show_spinner iz_install_zstackctl
    show_spinner cp_third_party_tools
    if [ -z $ONLY_INSTALL_ZSTACK ]; then
        show_spinner sd_install_zstack_ui
        zstack-ctl config_ui --restore
    fi
}

install_db(){
    echo_title "Install Database"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    #generate ssh key for install mysql by ansible remote host
    ssh_tmp_dir=`mktemp`
    /bin/rm -rf $ssh_tmp_dir
    mkdir -p $ssh_tmp_dir
    show_spinner cs_gen_sshkey $ssh_tmp_dir
    #install mysql db
    show_spinner cs_install_mysql $ssh_tmp_dir
    #deploy initial database
    show_spinner cs_deploy_db
    #deploy initial database of zstack_ui
    show_spinner cs_deploy_ui_db
    #check hostname and ip again
    ia_check_ip_hijack
    cs_clean_ssh_tmp_key $ssh_tmp_dir
}

install_sds(){
    echo_title "Install SDS"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    show_spinner is_install_sds
    show_spinner is_append_iptables
}

setup_install_param(){
    echo_title "Setup Install Parameters"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    show_spinner sp_setup_install_param
}

sp_setup_install_param(){
    echo_subtitle "Setup Install Parameters"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ x"$MINI_INSTALL" = x"y" ];then
        show_spinner sd_install_zstack_mini_ui
        DEFAULT_UI_PORT=8200
        zstack-ctl configure ui_mode=mini
        zstack-ctl configure AppCenter.server.mode=on
        zstack-ctl configure log.management.server.retentionSizeGB=200
    else
        zstack-ctl configure ui_mode=zstack
    fi

    if [ x"$SANYUAN_INSTALL" = x"y" ];then
        zstack-ctl configure identity.init.type="PRIVILEGE_ADMIN"
        zstack-ctl configure sanyuan.installed=true
    fi

    # Port 9090 is already used by system service on KylinOS(ft2000)
    if [ $OS == "KYLIN4.0.2" ];then
        zstack-ctl configure Prometheus.port=9080
    fi
}

install_license(){
    echo_title "Install License"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    show_spinner il_install_license
}

il_install_license(){
    echo_subtitle "Install License"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    # if -L is set
    if [ ! -z $LICENSE_PATH ]; then
        if [ -f $LICENSE_PATH ]; then
            zstack-ctl install_license --license $LICENSE_PATH >>$ZSTACK_INSTALL_LOG 2>&1
        else
            fail "License path ${LICENSE_PATH} does not exists."
        fi
    elif [ x"$INSTALL_ENTERPRISE" = x'y' ]; then
      # if -E is set
      zstack-ctl install_license --license $ZSTACK_TRIAL_LICENSE >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    chown -R zstack:zstack /var/lib/zstack/license >>$ZSTACK_INSTALL_LOG 2>&1
    #cd $ZSTACK_INSTALL_ROOT
    #if [ -f $LICENSE_FILE ]; then
    #    zstack-ctl install_license --license $LICENSE_FILE >>$ZSTACK_INSTALL_LOG 2>&1
    #fi
    pass
}

config_system(){
    echo_title "Configure System"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    #show_spinner cs_flush_iptables
    show_spinner cs_config_zstack_properties
    show_spinner cs_config_generate_ssh_key
    show_spinner cs_config_tomcat
    show_spinner upgrade_tomcat_security
    show_spinner cs_install_zstack_service
    show_spinner cs_enable_zstack_service
    show_spinner cs_add_cronjob
    show_spinner cs_append_iptables
    show_spinner cs_setup_nginx
    show_spinner cs_enable_usb_storage
    if [ ! -z $NEED_NFS ];then
        show_spinner cs_setup_nfs
    fi
    if [ ! -z $NEED_HTTP ];then
        show_spinner cs_setup_http
    fi
    do_enable_sudo
    do_config_networkmanager
}

cs_add_cronjob(){
    echo_subtitle "Add cronjob to clean logs"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
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
        crontab - <<EOF
`crontab -l 2>/dev/null`
30 0,12 * * * zstack-ctl dump_mysql --keep-amount 14
EOF
    fi

    crontab - <<EOF
`crontab -l 2>/dev/null|sed '/zstack-ctl dump_cassandra/d'`
EOF
    pass
}

cs_config_zstack_properties(){
    echo_subtitle "Configure global properties"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

    if [ -d /var/lib/zstack ];then
        chown zstack:zstack /var/lib/zstack >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -ne 0 ];then
            fail "failed to change ownership for /var/lib/zstack"
        fi
    fi

    if [ ! -z $ZSTACK_PROPERTIES_REPO ];then
        zstack-ctl configure Ansible.var.zstack_repo=$ZSTACK_PROPERTIES_REPO
        if [ $? -ne 0 ];then
            fail "failed to add yum repo to $ZSTACK_PROPERTIES"
        fi
    fi

    if [ ! -z $CONSOLE_PROXY_ADDRESS ];then
        zstack-ctl configure consoleProxyOverriddenIp=${CONSOLE_PROXY_ADDRESS}
        if [ $? -ne 0 ];then
            fail "failed to update console proxy overridden IP to $CONSOLE_PROXY_ADDRESS"
        fi
    fi

    if [ ! -z $ZSTACK_ANSIBLE_EXECUTABLE ];then
        zstack-ctl configure Ansible.executable=${ZSTACK_ANSIBLE_EXECUTABLE}
        if [ $? -ne 0 ];then
            fail "failed to configure ansible executable to $ZSTACK_ANSIBLE_EXECUTABLE"
        fi
    fi

    pass
}

cs_config_generate_ssh_key(){
    echo_subtitle "Generate Local Ssh keys"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    #generate local ssh key
    rsa_key_folder=${ZSTACK_INSTALL_ROOT}/${CATALINA_ZSTACK_CLASSES}/ansible/rsaKeys
    /bin/rm -f ${rsa_key_folder}/*
    ssh-keygen -f ${rsa_key_folder}/id_rsa -N '' -m PEM -t rsa -q >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
        fail "failed to generate local ssh keys in ${rsa_key_folder}"
    fi
    chown -R zstack:zstack ${rsa_key_folder}
    pass
}

iz_chown_install_root(){
    echo_subtitle "Change Owner in ${PRODUCT_NAME}"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    chown -R zstack:zstack $ZSTACK_INSTALL_ROOT >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
        fail "failed to chown for $ZSTACK_INSTALL_ROOT with zstack:zstack"
    fi
    pass
}

cs_gen_sshkey(){
    echo_subtitle "Generate Temp SSH Key"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    [ ! -d /root/.ssh ] && mkdir -p /root/.ssh && chmod 700 /root/.ssh

    rsa_key_file=$1/id_rsa
    rsa_pub_key_file=$1/id_rsa.pub
    authorized_keys_file=/root/.ssh/authorized_keys
    ssh-keygen -t rsa -N '' -f $rsa_key_file >>$ZSTACK_INSTALL_LOG 2>&1 
    if [ ! -f $authorized_keys_file ]; then
        cat $rsa_pub_key_file > $authorized_keys_file
        chmod 600 $authorized_keys_file
    else
        ssh_pub_key=`cat $rsa_pub_key_file`
        grep $ssh_pub_key $authorized_keys_file >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            cat $rsa_pub_key_file >> $authorized_keys_file
        fi
    fi
    if [ -x /sbin/restorecon ]; then
        /sbin/restorecon /root/.ssh /root/.ssh/authorized_keys >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    pass
}

setup_audit_file(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ ! -f $AUDIT_RULE_FILE ]; then
        return 1
    fi

    get_mysql_conf_file
    zstack-ctl refresh_audit --add $ZSTACK_INSTALL_ROOT/$ZSTACK_PROPERTIES > /dev/null
    zstack-ctl refresh_audit --add $MYSQL_CONF_FILE > /dev/null
}

cs_install_mysql(){
    echo_subtitle "Install Mysql Server"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    rsa_key_file=$1/id_rsa
    if [ -z $ZSTACK_YUM_REPOS ];then
        if [ -z $MYSQL_ROOT_PASSWORD ]; then
            zstack-ctl install_db --host=$MANAGEMENT_IP --ssh-key=$rsa_key_file --root-password="$MYSQL_NEW_ROOT_PASSWORD" --debug >>$ZSTACK_INSTALL_LOG 2>&1
        else
            zstack-ctl install_db --host=$MANAGEMENT_IP --login-password="$MYSQL_ROOT_PASSWORD" --root-password="$MYSQL_NEW_ROOT_PASSWORD" --ssh-key=$rsa_key_file --debug >>$ZSTACK_INSTALL_LOG 2>&1
        fi
    else
        if [ -z $MYSQL_ROOT_PASSWORD ]; then
            zstack-ctl install_db --host=$MANAGEMENT_IP --ssh-key=$rsa_key_file --yum=$ZSTACK_YUM_REPOS --root-password="$MYSQL_NEW_ROOT_PASSWORD" >>$ZSTACK_INSTALL_LOG --debug 2>&1
        else
            zstack-ctl install_db --host=$MANAGEMENT_IP --login-password="$MYSQL_ROOT_PASSWORD" --root-password="$MYSQL_NEW_ROOT_PASSWORD" --ssh-key=$rsa_key_file --yum=$ZSTACK_YUM_REPOS --debug >>$ZSTACK_INSTALL_LOG 2>&1
        fi
    fi
    if [ $? -ne 0 ];then
        cs_clean_ssh_tmp_key $1
        fail "failed to install mysql server."
    fi
    pass
}

cs_clean_ssh_tmp_key(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    #echo_subtitle "Clean up ssh temp key"
    rsa_pub_key_file=$1/id_rsa.pub
    ssh_pub_key=`cat $rsa_pub_key_file`
    authorized_keys_file=/root/.ssh/authorized_keys
    sed -i "\;$ssh_pub_key;d" $authorized_keys_file >>$ZSTACK_INSTALL_LOG 2>&1
    /bin/rm -rf $1
    #pass
}

ia_disable_selinux(){
    echo_subtitle "Disable SELinux"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
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
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    iptables -F
    iptables -F -t nat
    [ $? -ne 0 ] && fail "disable iptables failed"
    pass
}

cs_config_tomcat(){
    echo_subtitle "Configure Tomcat Java Option"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    cat >> $ZSTACK_INSTALL_ROOT/apache-tomcat/bin/setenv.sh <<EOF
export CATALINA_OPTS=" -Djava.net.preferIPv4Stack=true -Dcom.sun.management.jmxremote=true -Djava.security.egd=file:/dev/./urandom"
EOF
    pass
}

cs_append_iptables(){
    echo_subtitle "Append iptables"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ "$NEED_SET_MN_IP" == "y" ]; then
        management_addr=`ip addr show |grep ${MANAGEMENT_IP}|awk '{print $2}'`
        ports=(3306)
        for port in ${ports[@]}
        do
            iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport $port -j REJECT" || iptables -A INPUT -p tcp --dport $port -j REJECT >>$ZSTACK_INSTALL_LOG 2>&1
            iptables-save | grep -- "-A INPUT -d $management_addr/32 -p tcp -m tcp --dport $port -j ACCEPT" || iptables -I INPUT -p tcp --dport $port -d $management_addr -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1
            iptables-save | grep -- "-A INPUT -d $management_addr/32 -p tcp -m tcp --dport $port -j ACCEPT" || iptables -I INPUT -p tcp --dport $port -d 127.0.0.1 -j ACCEPT >>$ZSTACK_INSTALL_LOG 2>&1

        done
        service iptables save >> $ZSTACK_INSTALL_LOG 2>&1
    fi

    pass
}
cs_install_zstack_service(){
    echo_subtitle "Install ${PRODUCT_NAME} management node"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    /bin/cp -f $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_CLASSES/install/zstack-server /etc/init.d
    chmod a+x /etc/init.d/zstack-server
    tomcat_folder_path=$ZSTACK_INSTALL_ROOT/apache-tomcat
    sed -i "s#^TOMCAT_PATH=.*#TOMCAT_PATH=$tomcat_folder_path#" /etc/init.d/zstack-server
    [ $? -ne 0 ] && fail "failed to install ${PRODUCT_NAME} management node."
    zstack-ctl setenv ZSTACK_HOME=$ZSTACK_HOME >> $ZSTACK_INSTALL_LOG 2>&1 
    [ $? -ne 0 ] && fail "failed to set ZSTACK_HOME path by ${PRODUCT_NAME,,}-ctl"
    pass
}

disable_probe_interfaces() {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if grep -E -sq '^Set[[:space:]]+probe_interfaces[[:space:]]+false' /etc/sudo.conf; then
        :
    else
        echo "Set probe_interfaces false" >> /etc/sudo.conf
    fi
}

cs_enable_zstack_service(){
    echo_subtitle "Enable ${PRODUCT_NAME} bootstrap service"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ -f /bin/systemctl ]; then
        cat > /etc/systemd/system/zstack.service <<EOF
[Unit]
Description=zstack Service
After=syslog.target network.target mariadb.service
Before=shutdown.target reboot.target halt.target

[Service]
Type=forking
User=root
ExecStart=/usr/bin/zstack-ctl start --daemon
ExecStop=/usr/bin/zstack-ctl stop
Restart=on-abort
RemainAfterExit=Yes
TimeoutStartSec=600
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF
        systemctl enable zstack.service  >> $ZSTACK_INSTALL_LOG 2>&1
    else
        which update-rc.d >>$ZSTACK_INSTALL_LOG 2>&1
        if [ $? -eq 0 ]; then
            update-rc.d zstack-server start 97 3 4 5 . stop 3 0 1 2 6 .  >> $ZSTACK_INSTALL_LOG 2>&1
        fi
    fi

    # work-around 'sudo' with large number of L2 devices
    # c.f. https://bugs.launchpad.net/ubuntu/+source/sudo/+bug/1272414
    disable_probe_interfaces

    pass
}

cs_setup_nfs(){
    echo_subtitle "Configure Local NFS Server"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    mkdir -p $NFS_FOLDER
    grep $NFS_FOLDER /etc/exports >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ]; then 
        echo "$NFS_FOLDER *(rw,sync,no_root_squash)" >> /etc/exports
    fi
    if [[ "$OS" = "CENTOS6" ]]; then
        chkconfig nfs on >>$ZSTACK_INSTALL_LOG 2>&1
        chkconfig rpcbind on >>$ZSTACK_INSTALL_LOG 2>&1
        service rpcbind restart >>$ZSTACK_INSTALL_LOG 2>&1
        service nfs restart >>$ZSTACK_INSTALL_LOG 2>&1
    elif [[ $REDHAT_WITHOUT_CENTOS6 =~ $OS ]]; then
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

cs_setup_nginx(){
    echo_subtitle "Configure Nginx Server"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
mkdir -p /etc/nginx/conf.d/mn_pxe/ && chmod -R 0777 /etc/nginx/conf.d/mn_pxe/
[ -f /etc/nginx/nginx.conf ] && cp -f /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bck
cat > /etc/nginx/nginx.conf << EOF
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log;
pid /run/nginx.pid;
include /usr/share/nginx/modules/*.conf;
events {
    worker_connections 1024;
}
http {
    access_log          /var/log/nginx/access.log;
    sendfile            on;
    tcp_nopush          on;
    tcp_nodelay         on;
    server_tokens       off;
    keepalive_timeout   1000;
    types_hash_max_size 2048;
    include             /etc/nginx/mime.types;
    default_type        application/octet-stream;

    map \$http_upgrade \$connection_upgrade {
        default upgrade;
        ''      close;
    }

    server {
        listen 8090;
        include /etc/nginx/conf.d/mn_pxe/*;
    }

    server {
        listen 7771;
        include /etc/nginx/conf.d/pxe_mn/*;
    }

    server {
        listen 7772;
        include /etc/nginx/conf.d/terminal/*;
    }
}
EOF
iptables-save 2>&1 | grep -- "-A INPUT -p tcp -m tcp --dport 8090 -j ACCEPT" > /dev/null 2>&1 || iptables -I INPUT -p tcp -m tcp --dport 8090 -j ACCEPT >/dev/null 2>&1
service iptables save >/dev/null 2>&1

# start nginx when it's necessary
systemctl stop nginx > /dev/null 2>&1
systemctl disable nginx > /dev/null 2>&1
}

cs_setup_http(){
    echo_subtitle "Configure Local HTTP Server"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    mkdir $HTTP_FOLDER
    chmod 777 $HTTP_FOLDER
    chmod o+x $ZSTACK_INSTALL_ROOT
    if [[ $REDHAT_WITHOUT_CENTOS6 =~ $OS ]]; then
        chkconfig httpd on >>$ZSTACK_INSTALL_LOG 2>&1
        cat > /etc/httpd/conf.d/zstack-http.conf <<EOF
Alias /image "$HTTP_FOLDER/"
<Directory $HTTP_FOLDER/>
    AllowOverride FileInfo AuthConfig Limit
    Options MultiViews Indexes SymLinksIfOwnerMatch IncludesNoExec
    Allow from all
    Require all granted
</Directory>
EOF
        service httpd restart >>$ZSTACK_INSTALL_LOG 2>&1
    elif [ $OS = "CENTOS6" ]; then
        chkconfig httpd on >>$ZSTACK_INSTALL_LOG 2>&1
        cat > /etc/httpd/conf.d/zstack-http.conf <<EOF
Alias /image "$HTTP_FOLDER/"
<Directory $HTTP_FOLDER/>
    AllowOverride FileInfo AuthConfig Limit
    Options MultiViews Indexes SymLinksIfOwnerMatch IncludesNoExec
    Allow from all
</Directory>
EOF
        service httpd restart >>$ZSTACK_INSTALL_LOG 2>&1
    else
        cat > /etc/apache2/conf-enabled/zstack-http.conf <<EOF
Alias /image "$HTTP_FOLDER/"
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
    iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport 80 -j ACCEPT" > /dev/null 2>&1 || iptables -I INPUT -p tcp -m tcp --dport 80 -j ACCEPT
    iptables-save | grep -- "-A INPUT -p tcp -m tcp --dport $MN_PORT -j ACCEPT" > /dev/null 2>&1 || iptables -I INPUT -p tcp -m tcp --dport "$MN_PORT" -j ACCEPT
    service iptables save
    pass
} >> $ZSTACK_INSTALL_LOG 2>&1

cs_enable_usb_storage(){
    echo_subtitle "Configure usb storage mod"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    lsmod | grep -q usb_storage
    if [[ $? -ne 0 ]]; then
        modprobe usb_storage 2>/dev/null || true
    fi

    [ -f /etc/modules-load.d/usb-storage.conf ] || echo 'usb_storage' > /etc/modules-load.d/usb-storage.conf || true
}

check_zstack_server(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    curl --noproxy -H "Content-Type: application/json" -d '{"org.zstack.header.apimediator.APIIsReadyToGoMsg": {}}' http://localhost:"$MN_PORT"/zstack/api >>$ZSTACK_INSTALL_LOG 2>&1
    return $?
}

start_zstack(){
    echo_title "Start ${PRODUCT_NAME} Server"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    show_spinner sz_start_zstack
}

cs_deploy_db(){
    echo_subtitle "Initialize Database"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
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
            fail "failed to deploy ${PRODUCT_NAME,,} database. You might want to add -D to drop previous ${PRODUCT_NAME,,} database or -k to keep previous ${PRODUCT_NAME,,} database"
        else
            cat $ZSTACKCTL_INSTALL_LOG >> $ZSTACK_INSTALL_LOG
            fail "failed to deploy ${PRODUCT_NAME} database. Please check mysql accessbility. If your mysql has set root password, please add parameter -PMYSQL_PASSWORD to rerun the installation."
        fi
    fi

    cat $ZSTACKCTL_INSTALL_LOG >> $ZSTACK_INSTALL_LOG
    pass
}

cs_deploy_ui_db(){
    echo_subtitle "Initialize ${PRODUCT_NAME} UI Database"
    echo "--------test start--------\n" >> $ZSTACKCTL_INSTALL_LOG
    echo "Initialize ${PRODUCT_NAME} UI Database\n" >> $ZSTACKCTL_INSTALL_LOG
    echo $MYSQL_PORT"\n" >> $ZSTACKCTL_INSTALL_LOG
    echo ${MYSQL_PORT}"\n" >> $ZSTACKCTL_INSTALL_LOG
    echo "--------test end--------\n" >> $ZSTACKCTL_INSTALL_LOG
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ -z $NEED_DROP_DB ]; then
        if [ -z $NEED_KEEP_DB ]; then
            zstack-ctl deploy_ui_db --root-password="$MYSQL_NEW_ROOT_PASSWORD" --zstack-ui-password="$MYSQL_UI_USER_PASSWORD" --host=${MANAGEMENT_IP} --port=${MYSQL_PORT} >>$ZSTACKCTL_INSTALL_LOG 2>&1
        else
            zstack-ctl deploy_ui_db --root-password="$MYSQL_NEW_ROOT_PASSWORD" --zstack-ui-password="$MYSQL_UI_USER_PASSWORD" --host=${MANAGEMENT_IP} --port=${MYSQL_PORT} --keep-db >>$ZSTACKCTL_INSTALL_LOG 2>&1
        fi
    else
        zstack-ctl deploy_ui_db --root-password="$MYSQL_NEW_ROOT_PASSWORD" --zstack-ui-password="$MYSQL_UI_USER_PASSWORD" --host=${MANAGEMENT_IP} --port=${MYSQL_PORT} --drop >>$ZSTACKCTL_INSTALL_LOG 2>&1
    fi
    if [ $? -ne 0 ];then
        grep 'detected existing zstack_ui database' $ZSTACKCTL_INSTALL_LOG >& /dev/null
        if [ $? -eq 0 ]; then
            cat $ZSTACKCTL_INSTALL_LOG >> $ZSTACK_INSTALL_LOG
            fail "failed to deploy ${PRODUCT_NAME} ui database. You might want to add -D to drop previous ${PRODUCT_NAME} ui database or -k to keep previous ${PRODUCT_NAME} ui database"
        else
            cat $ZSTACKCTL_INSTALL_LOG >> $ZSTACK_INSTALL_LOG
            fail "failed to deploy ${PRODUCT_NAME} ui database. Please check mysql accessbility. If your mysql has set root password, please add parameter -PMYSQL_PASSWORD to rerun the installation."
        fi
    fi

    cat $ZSTACKCTL_INSTALL_LOG >> $ZSTACK_INSTALL_LOG
    pass
}

sz_start_zstack(){
    echo_subtitle "Start ${PRODUCT_NAME} management node (takes a couple of minutes)"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    zstack-ctl stop_node -f >>$ZSTACK_INSTALL_LOG 2>&1
    zstack-ctl start_node --timeout=$ZSTACK_START_TIMEOUT >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "failed to start ${PRODUCT_NAME,,}"
    i=1
    while [ $i -lt 120 ]; do
        i=`expr $i + 1`
        check_zstack_server && pass && return
        sleep 1
    done
    fail "${PRODUCT_NAME,,} server failed to start in $i seconds"
}

# For UI 1.x
start_dashboard(){
    echo_title "Start ${PRODUCT_NAME} Dashboard"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    #show_spinner sd_install_dashboard_libs
    #make sure current folder is existed to avoid of possible dashboard start failure. 
    cd /
    show_spinner sd_start_dashboard
}

# For UI 2.0
start_zstack_ui(){
    echo_title "Start ${PRODUCT_NAME} Web UI"
    echo ""
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    cd /
    show_spinner sd_start_zstack_ui
}

# For UI 1.x and UI 2.0
sd_install_zstack_ui(){
    echo_subtitle "Install ${PRODUCT_NAME} Web UI (takes a couple of minutes)"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    zstack-ctl install_ui --force >>$ZSTACK_INSTALL_LOG 2>&1

    if [ $? -ne 0 ];then
        fail "failed to install ${PRODUCT_NAME} Web UI in $ZSTACK_INSTALL_ROOT"
    fi
    pass
}

# For MINI UI Server
sd_install_zstack_mini_ui(){
    echo_subtitle "Install ${PRODUCT_NAME} MINI-UI (takes a couple of minutes)"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    bash /opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/zstack_mini_server.bin -a >>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ];then
        fail "failed to install ${PRODUCT_NAME} MINI-UI in $MINI_INSTALL_ROOT"
    fi
    pass
}

# For UI 1.x
sd_start_dashboard(){
    echo_subtitle "Start ${PRODUCT_NAME} Dashboard"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    chmod a+x /etc/init.d/zstack-dashboard
    cd /
    /etc/init.d/zstack-dashboard restart >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "failed to start ${PRODUCT_NAME,,} dashboard"
    pass
}

# For UI 2.0
sd_start_zstack_ui(){
    echo_subtitle "Start ${PRODUCT_NAME} Web UI"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    zstack_home=$ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_PATH
    ui_logging_path=$zstack_home/../../logs/
    cd /
    ui_mode=`zstack-ctl get_configuration ui_mode`
    if [ x"$ui_mode" = x"zstack" ];then
        zstack-ctl start_ui >>$ZSTACK_INSTALL_LOG 2>&1
    elif [ x"$ui_mode" = x"mini" ];then
        systemctl start zstack-mini >>$ZSTACK_INSTALL_LOG 2>&1
    else
        fail "Unknown ui_mode, please make sure your configuration is correct."
    fi
    [ $? -ne 0 ] && fail "failed to start ${PRODUCT_NAME,,} web ui"
    pass
}

is_install_sds(){
    echo_subtitle "Install SDS"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    TMP=`mktemp -d /tmp/tmp-XXXXXX`
    trap "rm -rf $TMP* 2>/dev/null" EXIT
    tar -zxf /opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/ZCE-installer-SDS.tar.gz -C $TMP
    pushd $TMP >/dev/null
    sed -i "s/^PROMETHEUS_PORT=.*/PROMETHEUS_PORT=9089/g" install.conf
    bash install.sh ${MANAGEMENT_IP} >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "failed to install SDS"
    popd >/dev/null
    pass
}

is_append_iptables(){
    echo_subtitle "Append iptables"
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    iptables-save 2>&1 | grep -- "-A INPUT -p tcp -m tcp --dport $SDS_PORT -j ACCEPT" > /dev/null 2>&1 || iptables -I INPUT -p tcp -m tcp --dport $SDS_PORT -j ACCEPT >/dev/null 2>&1
    service iptables save >/dev/null 2>&1
    pass
}

get_higher_version() {
    echo "$@" | tr " " "\n" | sort -V | tail -1
}

#Ensure that the current version is lower than the upgrade version
check_version(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    # CURRENT_VERSION=`zstack-ctl status | awk '/version/{gsub(")",""); print $4 }'`
    CURRENT_VERSION=`awk '{print $2}' $ZSTACK_VERSION`
    UPGRADE_VERSION=${VERSION}
    if [ -z "$CURRENT_VERSION" -o -z "$UPGRADE_VERSION" ];then
        fail2 "Version verification failed! Cannot get your current version or upgrade version, please check ${PRODUCT_NAME,,} status and use the correct iso/bin to upgrade."
    fi
    HIGHER=`get_higher_version $CURRENT_VERSION $UPGRADE_VERSION`
    if [ x"$HIGHER" != x"$UPGRADE_VERSION" ];then
            fail2 "Upgrade version ($UPGRADE_VERSION) is lower than the current version ($CURRENT_VERSION), please download and use the higher one."
    fi
}

#create zstack local apt source list
create_apt_source(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    [ -f /etc/apt/sources.list ] && /bin/mv -f /etc/apt/sources.list /etc/apt/sources.list.zstack.`date +%Y-%m-%d_%H-%M-%S` >>$ZSTACK_INSTALL_LOG 2>&1
    cat > /etc/apt/sources.list << EOF
deb file:///opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/ Packages/
EOF
    mkdir -p /etc/apt/sources.list.d/tmp_bak
    mv /etc/apt/sources.list.d/!\(zstack-local.list\) /etc/apt/sources.list.d/tmp_bak/ 2>/dev/null
    #Fix Ubuntu conflicted dpkg lock issue.
    if [ -f /etc/init.d/unattended-upgrades ]; then
        /etc/init.d/unattended-upgrades stop  >>$ZSTACK_INSTALL_LOG 2>&1
        update-rc.d -f unattended-upgrades remove >>$ZSTACK_INSTALL_LOG 2>&1
        pid=`lsof /var/lib/dpkg/lock|grep lock|awk '{print $2}'`
        [ ! -z $pid ] && kill -9 $pid >>$ZSTACK_INSTALL_LOG 2>&1
        which systemctl >/dev/null 2>&1
        [ $? -eq 0 ] && systemctl stop apt-daily >>$ZSTACK_INSTALL_LOG 2>&1
    fi
    dpkg --configure --force-confold -a >>$ZSTACK_INSTALL_LOG 2>&1
    [ $? -ne 0 ] && fail "execute \`dpkg --configure --force-confold -a\` failed."
    apt-get clean >>$ZSTACK_INSTALL_LOG 2>&1
    apt-get update -o Acquire::http::No-Cache=True --fix-missing>>$ZSTACK_INSTALL_LOG 2>&1
    if [ $? -ne 0 ]; then
        fail "apt-get update package failed."
    fi
}


#create zstack local yum repo
create_yum_repo(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
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

[163-qemu-ev]
name=CentOS-\$releasever - QEMU EV
baseurl=http://mirrors.163.com/centos/\$releasever/virt/\$basearch/kvm-common/
gpgcheck=0
enabled=0

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

[ali-qemu-ev]
name=CentOS-\$releasever - QEMU EV
baseurl=http://mirrors.aliyun.com/centos/\$releasever/virt/\$basearch/kvm-common/
gpgcheck=0
enabled=0

EOF

}

set_zstack_repo(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    zstack-ctl setenv zstack_local_repo=$ZSTACK_YUM_REPOS 2>/dev/null
}

get_zstack_repo(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    ZSTACK_YUM_REPOS=`zstack-ctl getenv 2>/dev/null| grep 'zstack_local_repo' | awk -F'=' '{print $2}'`
    [ -z $ZSTACK_YUM_REPOS ] && ZSTACK_YUM_REPOS=`zstack-ctl show_configuration | grep 'Ansible.var.zstack_repo' | awk '{print $3}'|tr -d '\n'|tr -d '\r'`
    [ -z $ZSTACK_YUM_REPOS ] && ZSTACK_YUM_REPOS=`zstack-ctl show_configuration | grep 'Ansible.var.yum_repo' | awk '{print $3}'|tr -d '\n'|tr -d '\r'`
    if [ ! -z $ZSTACK_YUM_REPOS ];then
        ZSTACK_YUM_REPOS=`echo $ZSTACK_YUM_REPOS|sed 's/zstack-mn/zstack-local/g'`
        echo $ZSTACK_YUM_REPOS |grep "zstack-local" >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            ZSTACK_YUM_REPOS='zstack-local'
            ZSTACK_OFFLINE_INSTALL='y'
            ZSTACK_PROPERTIES_REPO=$ZSTACK_MN_REPOS
        fi
        echo $ZSTACK_YUM_REPOS |grep "ali" >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            ZSTACK_YUM_REPOS=$MIRROR_ALI_YUM_REPOS
            ZSTACK_PROPERTIES_REPO=$MIRROR_ALI_YUM_REPOS
        fi
        echo $ZSTACK_YUM_REPOS |grep "163" >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            ZSTACK_YUM_REPOS=$MIRROR_163_YUM_REPOS
            ZSTACK_PROPERTIES_REPO=$MIRROR_163_YUM_REPOS
        fi
        YUM_ONLINE_REPO=''
    fi
}

install_sync_repo_dependences() {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    pkg_list="createrepo curl rsync"
    if [ x"$OS" != x"KYLIN10" -a x"$OS" != x"EULER20" ]; then
        pkg_list="$pkg_list yum-utils"
    fi
    missing_list=`LANG=en_US.UTF-8 && rpm -q $pkg_list | grep 'not installed' | awk 'BEGIN{ORS=" "}{ print $2 }'`
    [ -z "$missing_list" ] || yum -y --disablerepo=* --enablerepo=zstack-local install ${missing_list} >>$ZSTACK_INSTALL_LOG 2>&1 || echo_hints_to_upgrade_iso
}

create_local_repo_files() {
trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
mkdir -p /opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/Extra/{qemu-kvm-ev,ceph,galera,virtio-win}

repo_file=/etc/yum.repos.d/zstack-local.repo
echo "create $repo_file" >> $ZSTACK_INSTALL_LOG
cat > $repo_file << EOF
[zstack-local]
name=zstack-local
baseurl=file:///opt/zstack-dvd/\$basearch/\$YUM0
gpgcheck=0
enabled=1
EOF

repo_file=/etc/yum.repos.d/qemu-kvm-ev.repo
echo "create $repo_file" >> $ZSTACK_INSTALL_LOG
cat > $repo_file << EOF
[qemu-kvm-ev]
name=Qemu KVM EV
baseurl=file:///opt/zstack-dvd/\$basearch/\$YUM0/Extra/qemu-kvm-ev
gpgcheck=0
enabled=0
EOF

repo_file=/etc/yum.repos.d/mlnx-ofed.repo
echo "create $repo_file" >> $ZSTACK_INSTALL_LOG
cat > $repo_file << EOF
[mlnx-ofed]
name=Mellanox OFED Driver
baseurl=file:///opt/zstack-dvd/\$basearch/\$YUM0/Extra/mlnx-ofed
gpgcheck=0
enabled=0
EOF

repo_file=/etc/yum.repos.d/ceph.repo
echo "create $repo_file" >> $ZSTACK_INSTALL_LOG
cat > $repo_file << EOF
[ceph]
name=Ceph
baseurl=file:///opt/zstack-dvd/\$basearch/\$YUM0/Extra/ceph
gpgcheck=0
enabled=0
EOF

repo_file=/etc/yum.repos.d/galera.repo
echo "create $repo_file" >> $ZSTACK_INSTALL_LOG
cat > $repo_file << EOF
[mariadb]
name = MariaDB
baseurl=file:///opt/zstack-dvd/\$basearch/\$YUM0/Extra/galera
gpgcheck=0
enabled=0
EOF

repo_file=/etc/yum.repos.d/virtio-win.repo
echo "create $repo_file" >> $ZSTACK_INSTALL_LOG
cat > $repo_file << EOF
[virtio-win]
name=virtio-win
baseurl=file:///opt/zstack-dvd/\$basearch/\$YUM0/Extra/virtio-win
gpgcheck=0
enabled=0
EOF

# Fixes ZSTAC-18536: delete invalid repo file virt-win.repo
invalid_virt_win_repo=/etc/yum.repos.d/virt-win.repo
[ -f $invalid_virt_win_repo ] && rm -f $invalid_virt_win_repo
}

check_hybrid_arch(){
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ -d /opt/zstack-dvd/x86_64 -a -d /opt/zstack-dvd/aarch64 ];then
        fail2 "Hybrid arch exists but repo not matched all, please contact and get correct iso to upgrade local repo first."
    fi
    REPO_MATCHED=false
}

create_local_source_list_files() {
    echo "create $list_file" >> $ZSTACK_INSTALL_LOG
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

list_file=/etc/apt/sources.list.d/zstack-local.list
cat > $list_file << EOF
deb file:///opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/ Packages/
EOF
}

check_sync_local_repos() {
  echo_subtitle "Check local repo version"
  trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
  if [[ $XINCHUANG_OS =~ $ZSTACK_RELEASE ]]; then
      SKIP_SYNC='y'
  fi
  [ -f ".repo_version" ] || fail2 "Cannot found current repo_version file, please make sure you have correct ${PRODUCT_NAME,,}-installer package."
  if [ -d /opt/zstack-dvd/$BASEARCH ];then
    for release in `ls /opt/zstack-dvd/$BASEARCH`;do
      cmp -s .repo_version /opt/zstack-dvd/$BASEARCH/$release/.repo_version || check_hybrid_arch
    done
  fi
  if [ x"$REPO_MATCHED" = x"true" ]; then
      return 0
  elif [ x"$SKIP_SYNC" = x'y' -o x"$BASEARCH" != x"x86_64" ]; then
      echo " ... $(tput setaf 1)NOT MATCH$(tput sgr0)" | tee -a $ZSTAC_INSTALL_LOG
      echo_hints_to_upgrade_iso
  else
      echo " ... $(tput setaf 3)NOT MATCH$(tput sgr0)" | tee -a $ZSTAC_INSTALL_LOG
  fi

echo_subtitle "Sync from repo.zstack.io (takes a couple of minutes)"
# if current local repo is based on centos7.2, then sync with eg. 2.3.1_c72
# if current local repo is based on centos7.4, then sync with eg. 2.3.1_c74
if [ x"$UPGRADE" = x'y' ]; then
    cluster_os_version=`mysql -uzstack -p"$MYSQL_USER_PASSWORD" zstack -e "select distinct tag from SystemTagVO where (resourceType='HostVO' and tag like '%os::version%');"`
    cluster_os_type=`echo -e "$cluster_os_version"|awk -F"::" '/version/{print $3}'|awk -F "." '{print "c"$1$2}'`
    [ -z "$cluster_os_type" ] && cluster_os_type=$ZSTACK_RELEASE
fi
if [ x"$ZSTACK_RELEASE" = x"c72" -o x"$ZSTACK_RELEASE" = x"c74" -o x"$ZSTACK_RELEASE" = x"c76" ];then
    BASEURL=rsync://rsync.repo.zstack.io/${VERSION_RELEASE_NR}/$BASEARCH/
    REMOTE_REPO_VERSION_URL=repo.zstack.io/${VERSION_RELEASE_NR}/$BASEARCH/
else
    BASEURL=rsync://rsync.repo.zstack.io/${VERSION_RELEASE_NR}/
    REMOTE_REPO_VERSION_URL=repo.zstack.io/${VERSION_RELEASE_NR}/
fi

LOCAL_ZSTAC_VERSION=$(awk '{print $NF}' $ZSTACK_HOME/VERSION)
if [[ $LOCAL_ZSTAC_VERSION == $VERSION_RELEASE_NR* ]]; then
    wget -q -O .remote_repo_version "${REMOTE_REPO_VERSION_URL}${ZSTACK_RELEASE}/.repo_version"
    if [ -s .remote_repo_version ]; then
        cmp -s .repo_version .remote_repo_version || echo_upgrade_local_repo_use_iso
    else
        fail2 "failed to update repo, can not find remote repo version, please download iso manually to upgrade your repo."
    fi
fi
# it takes about 2 min to compare md5sum of 1800+ files in iso
for os_release in $cluster_os_type;do
    [ ! -d /opt/zstack-dvd/$BASEARCH/$os_release ] && fail2 "$os_release cluster exists but no local repo matched, please download $os_release iso manually to upgrade your repo."
    umount /opt/zstack-dvd/$BASEARCH/$os_release/Extra/qemu-kvm-ev >/dev/null 2>&1
    rsync -aP --delete --exclude zstack-installer.bin --exclude .repo_version ${BASEURL}${os_release}/ /opt/zstack-dvd/$BASEARCH/$os_release/ >> $ZSTACK_INSTALL_LOG 2>&1 || echo_hints_to_upgrade_iso
    # update .repo_version after syncing
    cat .repo_version > /opt/zstack-dvd/$BASEARCH/$os_release/.repo_version
done

[ -f /etc/yum.repos.d/epel.repo ] && sed -i 's/enabled=1/enabled=0/g' /etc/yum.repos.d/epel.repo
export YUM0="$ZSTACK_RELEASE"
yum --enablerepo=* clean all >/dev/null 2>&1
rpm -qa | grep zstack-manager >/dev/null 2>&1 && yum --disablerepo=* --enablerepo=zstack-local -y install zstack-manager >/dev/null 2>&1 || true
rpm -qa | grep zstack-release >/dev/null 2>&1 || yum --disablerepo=* --enablerepo=zstack-local -y install zstack-release >/dev/null 2>&1 && true

cd /opt/zstack-dvd
rm -rf `ls -a|egrep -v "(x86_64|aarch64|mips64el|loongarch64)"`  > /dev/null 2>&1
cd - > /dev/null
if [ ! -f /opt/zstack-dvd/zstack-image-1.4.qcow2 ];then
    cp -rf /opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/zstack-image-1.4.qcow2 /opt/zstack-dvd/
    cp -rf /opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE/GPL /opt/zstack-dvd/
fi
pass
}

usage (){
    echo "
${PRODUCT_NAME} Installer.

The script can install ${PRODUCT_NAME} related software.

Warning: This script will disable SELinux on RedHat series OS (CentOS/Redhat RHEL)

Usage: ${PROGNAME} [options]

Options:
  -a    equal to -nH

  -c    Only upgrade ${PRODUCT_NAME,,}-ctl tool.

  -C    specify console proxy address.

  -d    print detailed installation log to screen
        By default the installation log will be saved to $ZSTACK_INSTALL_LOG

  -D    drop previous ${PRODUCT_NAME} database if it exists. An error will be raised
        if a previous ${PRODUCT_NAME} database is detected and no -D or -k option is provided.

  -E    Install ${PRODUCT_NAME} Enterprise version. This option is only valid after ${PRODUCT_NAME} 2.0.

  -f LOCAL_PATH_OR_URL_OF_ZSTACK_ALL_IN_ONE_PACKAGE
        file path to ${PRODUCT_NAME} all-in-one package. By default the script
        will download the all-in-one package from ${PRODUCT_NAME} official website.
        You can provide a local file path or a URL with option if you want to
        use a separate all-in-one package.

  -F    force upgrade management node mysql database. This option is only valid
        when using -u option. It will send --force parameter to 
        ${PRODUCT_NAME,,}-ctl upgrade_db

  -h    show help message

  -H IMAGE_FOLDER_PATH   
        setup an Apache HTTP server and use IMAGE_FOLDER_PATH as url:
        http://CURRENT_MACHINE_IP/image/ . Doesn't effect when use -u to upgrade
        ${PRODUCT_NAME,,} or -l to install some system libs. 

  -i    only install ${PRODUCT_NAME} management node and dependent packages.
        ${PRODUCT_NAME} won't automatically be started when use '-i'.

  -I MANAGEMENT_NODE_NETWORK_INTERFACE | MANAGEMENT_NODE_IP_ADDRESS
        e.g. -I eth0, -I eth0:1, -I 192.168.0.1
        the network interface (e.g. eth0) or IP address for management network.
        The IP address of this interface will be configured as IP of MySQL 
        server, if they are installed on this machine.
        Remote ${PRODUCT_NAME} managemet nodes will use this IP to access MySQL.
        By default, the installer script will grab the IP of
        interface providing default routing from routing table. 
        If multiple IP addresses share same net device, e.g. em1, em1:1, em1:2.
        The network interface should be the exact name, like -I em1:1

  -k    keep previous ${PRODUCT_NAME,,} DB if it exists. If using -k with -u, will not upgrade database or start management node. Do not use this option unless you really know what is means.

  -l    only just install ${PRODUCT_NAME} dependent libraries

  -L LICENSE_PATH
        path of the license file that needs to be installed automatically.

  -m    install monitor. Depends on monitor capability in package.

  -M    install monitor when upgrade. Used when upgrade ${PRODUCT_NAME} to Mevoco.

  -n NFS_PATH
        setup a NFS server and export the NFS path. Doesn't effect when use -u 
        to upgrade ${PRODUCT_NAME,,} or -l to install some system libs. 

  -o    offline installation. ${PRODUCT_NAME} required system libs will installed from ${PRODUCT_NAME,,} local repository, which is installed from ${PRODUCT_NAME} customed ISO. ${PRODUCT_NAME} customed ISO could be got from ${PRODUCT_NAME} community.

  -O    online installation. Mevoco don't support this option.

  -p MYSQL_PASSWORD
        password for MySQL user 'zstack' that is the user ${PRODUCT_NAME} management nodes use to access database. By default, an empty password is applied.

  -P MYSQL_PASSWORD
        password for MySQL root user. By default, an empty password is applied.

  -q    quiet installation. Installation will try to fix the system configuration issue, rather than quit installation process.

  -r ZSTACK_INSTALLATION_PATH
        the path where to install ${PRODUCT_NAME} management node.  The default path is $ZSTACK_INSTALL_ROOT

  -R ZSTACK_PKG_MIRROR
        which yum mirror user want to use to install ${PRODUCT_NAME} required CentOS rpm packages. User can choose 163 or aliyun, like -R aliyun, -R 163 
        Mevoco don't support this option.

  -t ZSTACK_START_TIMEOUT
        The timeout for waiting ${PRODUCT_NAME} start. The default value is $ZSTACK_START_TIMEOUT

  -T MYSQL_PORT   port for MySQL. 3306 is set by default

  -u    Upgrade ${PRODUCT_NAME,,} management node and database. Make sure to backup your database, before executing upgrade command: mysqldump -u root -proot_password --host mysql_ip --port mysql_port zstack > path_to_db_dump.sql

  -z    Only install ${PRODUCT_NAME}, without start ${PRODUCT_NAME} management node.
------------
Example:

Following command will install the ${PRODUCT_NAME} management node to /usr/local/zstack and all dependent packages:

. Apache Tomcat 7 with ${PRODUCT_NAME,,}.war deployed
. ${PRODUCT_NAME} web UI
. ${PRODUCT_NAME} command line tool (${PRODUCT_NAME,,}-cli)
. ${PRODUCT_NAME} control tool (${PRODUCT_NAME,,}-ctl)
. MySQL
. NFS server
. Apache HTTP server

And an empty password is set to the root user of MySQL.

# ${PROGNAME} -a

--

In addition to all above results, below command sets MySQL user 'zstack' password to DB_ZSTACK_PASSWORD by using the MySQL 'root' user password DB_ROOT_PASSWORD
, and uses the IP of eth1 for deploying MySQL.

# ${PROGNAME} -r /home/zstack -a -P DB_ROOT_PASSWORD -p DB_ZSTACK_PASSWORD -I eth1

--

Following command only installs ${PRODUCT_NAME} management node and dependent software.

# ${RPOGNAME} -i

--

Following command only installs ${PRODUCT_NAME} management node and monitor.

# ${PROGNAME} -m

--

Following command installs ${PRODUCT_NAME} management node and monitor. It will use aliyun yum mirror source.

# ${PROGNAME} -m -R aliyun

--

Following command installs ${PRODUCT_NAME} management node and monitor. It will use aliyun yum mirror source. It will also use quiet installation to try to fix system configuration issue. 

# ${PROGNAME} -m -R aliyun -q

------------
"
    exit 1
}

check_myarg() {
    myarg=$2
    initial=${myarg:0:1}
    if [ x"$initial" = x"-" ];then
        echo "Unexpected parameter for $1"
        exit 1
    fi
}

OPTIND=1
TEMP=`getopt -o f:H:I:n:p:P:r:R:t:y:acC:L:T:dDEFhiklmMNoOqsuz --long mini,SY,sds -- "$@"`
if [ $? != 0 ]; then
    usage
fi
eval set -- "$TEMP"
while :
do
    [ -z "$1" ] && break;
    case "$1" in
        -a ) NEED_NFS='y' && NEED_HTTP='y' && YUM_ONLINE_REPO='y';shift;;
        -c ) ONLY_UPGRADE_CTL='y' && UPGRADE='y';shift;;
        -C ) check_myarg $1 $2;CONSOLE_PROXY_ADDRESS=$2;shift 2;;
        -d ) DEBUG='y';shift;;
        -D ) NEED_DROP_DB='y';shift;;
        -E ) INSTALL_ENTERPRISE='y';shift;;
        -H ) check_myarg $1 $2;NEED_HTTP='y' && HTTP_FOLDER=$2;shift 2;;
        -f ) check_myarg $1 $2;ZSTACK_ALL_IN_ONE=$2;shift 2;;
        -F ) FORCE='y';shift;;
        -i ) ONLY_INSTALL_ZSTACK='y' && NEED_NFS='' && NEED_HTTP='' ;shift;;
        -I ) check_myarg $1 $2;MANAGEMENT_INTERFACE=$2 && NEED_SET_MN_IP='y';shift 2;;
        -k ) NEED_KEEP_DB='y';shift;;
        -l ) ONLY_INSTALL_LIBS='y';shift;;
        -L ) check_myarg $1 $2;LICENSE_PATH=$2;shift 2;;
        -m ) INSTALL_MONITOR='y';shift;;
        -M ) UPGRADE_MONITOR='y';shift;;
        -n ) check_myarg $1 $2;NEED_NFS='y' && NFS_FOLDER=$2;shift 2;;
        # -o: do not use yum online repo
        -o ) YUM_ONLINE_REPO='' && ZSTACK_OFFLINE_INSTALL='y' && 
        [ "zstack.org" = "$WEBSITE" ] && WEBSITE='localhost';shift;;
        # -O: use yum online repo
        -O ) if [ x"${CHECK_REPO_VERSION}" != x"True" ]; then
        YUM_ONLINE_REPO='y'
        ZSTACK_OFFLINE_INSTALL=''
        else
        fail2 "$PRODUCT_NAME don't support '-O' option! Please remove '-O' and try again."
        fi;shift;;
        -P ) check_myarg $1 $2;MYSQL_ROOT_PASSWORD=$2 && MYSQL_NEW_ROOT_PASSWORD=$2;shift 2;;
        -p ) check_myarg $1 $2;MYSQL_USER_PASSWORD=$2;shift 2;;
        -q ) QUIET_INSTALLATION='y';shift;;
        -r ) check_myarg $1 $2;ZSTACK_INSTALL_ROOT=$2;shift 2;;
        # -R: use yum third party repo
        -R ) check_myarg $1 $2;if [ x"${CHECK_REPO_VERSION}" != x"True" ]; then
        ZSTACK_PKG_MIRROR=$2
        YUM_ONLINE_REPO='y'
        ZSTACK_OFFLINE_INSTALL=''
        else
        fail2 "$PRODUCT_NAME don't support '-R' option! Please remove '-R' and try again."
        fi;shift 2;;
        # -s: skip syncing from repo.zstack.io
        -s ) SKIP_SYNC='y';shift;;
        -t ) check_myarg $1 $2;ZSTACK_START_TIMEOUT=$2;shift 2;;
        -T ) check_myarg $1 $2;MYSQL_PORT=$2;shift 2;;
        -u ) UPGRADE='y';shift;;
        -y ) check_myarg $1 $2;HTTP_PROXY=$2;shift 2;;
        -z ) NOT_START_ZSTACK='y';shift;;
        --mini) MINI_INSTALL='y';shift;;
        --SY) SANYUAN_INSTALL='y';shift;;
        --sds) SDS_INSTALL='y';shift;;
        --) shift;;
        * ) usage;;
    esac
done

# Fix bug ZSTAC-14090
[ $# -eq $((OPTIND-1)) ] || usage
OPTIND=1

# Fix ZSTAC-21974
get_mn_port

# Fix ZSTAC-22364
pre_scripts_to_adjust_iptables_rules


which yum >>$ZSTACK_INSTALL_LOG 2>&1 && IS_YUM='y'
which apt >>$ZSTACK_INSTALL_LOG 2>&1 && IS_APT='y'

if [ x"$ZSTACK_OFFLINE_INSTALL" = x'y' ]; then
    if [ ! -d /opt/zstack-dvd/$BASEARCH/ ]; then
        cd /opt/zstack-dvd/Packages/
        ZSTACK_RELEASE=`ls |grep centos-release|awk -F"." '{print $1}'|awk -F"-" '{print "c"$3$4}'| head -1`
        [ x"$ZSTACK_RELEASE" = x"c72" ] && ZSTACK_RELEASE="c74"
        mkdir -p /opt/zstack-dvd/$BASEARCH/$ZSTACK_RELEASE
        cd - > /dev/null
    else
        check_zstack_release
    fi
fi

if [ ! -z $ZSTACK_PKG_MIRROR ]; then
    if [ "$ZSTACK_PKG_MIRROR" != "$PKG_MIRROR_163" -a "$ZSTACK_PKG_MIRROR" != "$PKG_MIRROR_ALIYUN" ]; then
        fail2 "\n\tYou want to use yum mirror from '$ZSTACK_PKG_MIRROR' . But $PRODUCT_NAME only supports yum mirrors for '$PKG_MIRROR_ALIYUN' or '$PKG_MIRROR_163'. Please fix it and rerun the installation.\n\n"
    fi
    if [ x"$ZSTACK_PKG_MIRROR" = x"$PKG_MIRROR_163" ]; then
        ZSTACK_YUM_REPOS=$MIRROR_163_YUM_REPOS
        ZSTACK_PROPERTIES_REPO=$MIRROR_163_YUM_REPOS
        WEBSITE=$MIRROR_163_YUM_WEBSITE
    else
        ZSTACK_YUM_REPOS=$MIRROR_ALI_YUM_REPOS
        ZSTACK_PROPERTIES_REPO=$MIRROR_ALI_YUM_REPOS
        WEBSITE=$MIRROR_ALI_YUM_WEBSITE
    fi
elif [ -z $YUM_ONLINE_REPO ]; then
    ZSTACK_YUM_REPOS=$ZSTACK_LOCAL_YUM_REPOS
    ZSTACK_PROPERTIES_REPO=$ZSTACK_MN_REPOS
elif [ x"$UPGRADE" != x'n' ]; then
    get_zstack_repo
fi

# there is no zstack-ctl yet
#[ ! -z $ZSTACK_YUM_REPOS ] && set_zstack_repo

README=$ZSTACK_INSTALL_ROOT/readme

echo "${PRODUCT_NAME} installation root path: $ZSTACK_INSTALL_ROOT" >>$ZSTACK_INSTALL_LOG
[ -z $NFS_FOLDER ] && NFS_FOLDER=$ZSTACK_INSTALL_ROOT/nfs_root
echo "NFS Folder: $NFS_FOLDER" >> $ZSTACK_INSTALL_LOG
[ -z $HTTP_FOLDER ] && HTTP_FOLDER=$ZSTACK_INSTALL_ROOT/http_root
echo "HTTP Folder: $HTTP_FOLDER" >> $ZSTACK_INSTALL_LOG

pypi_source_easy_install="file://${ZSTACK_INSTALL_ROOT}/apache-tomcat/webapps/zstack/static/pypi/simple"
pypi_source_pip="file://${ZSTACK_INSTALL_ROOT}/apache-tomcat/webapps/zstack/static/pypi/simple"
unzip_el6_rpm="${ZSTACK_INSTALL_ROOT}/libs/unzip*el6*.rpm"

if [ `uname -m` == "aarch64" ]; then
    zstore_bin="${ZSTACK_INSTALL_ROOT}/${CATALINA_ZSTACK_CLASSES}/ansible/imagestorebackupstorage/zstack-store.aarch64.bin"
    unzip_el7_rpm="${ZSTACK_INSTALL_ROOT}/libs/unzip*el7*aarch64*.rpm"
else
    zstore_bin="${ZSTACK_INSTALL_ROOT}/${CATALINA_ZSTACK_CLASSES}/ansible/imagestorebackupstorage/zstack-store.bin"
    unzip_el7_rpm="${ZSTACK_INSTALL_ROOT}/libs/unzip*el7*x86_64*.rpm"
fi

if [ -z $MANAGEMENT_INTERFACE ]; then
    fail2 "Cannot identify default network interface. Please set management
   node IP address by '-I MANAGEMENT_NODE_IP_ADDRESS'."
fi

ip addr show $MANAGEMENT_INTERFACE >/dev/null 2>&1
if [ $? -ne 0 ];then
    ip addr show |grep $MANAGEMENT_INTERFACE |grep inet >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        fail2 "$MANAGEMENT_INTERFACE is not a recognized IP address or network interface name. Please assign correct IP address by '-I MANAGEMENT_NODE_IP_ADDRESS'. Use 'ip addr' to show all interface and IP address." 
    fi
    MANAGEMENT_IP=$MANAGEMENT_INTERFACE
else
    MANAGEMENT_IP=`ip -4 addr show ${MANAGEMENT_INTERFACE} | grep inet | head -1 | awk '{print $2}' | cut -f1  -d'/'`
    echo "Management node network interface: $MANAGEMENT_INTERFACE" >> $ZSTACK_INSTALL_LOG
    if [ -z $MANAGEMENT_IP ]; then
        fail2 "Can not identify IP address for interface: $MANAGEMENT_INTERFACE . Please assign correct interface by '-I MANAGEMENT_NODE_IP_ADDRESS', which has IP address. Use 'ip addr' to show all interface and IP address."
    fi
fi

echo "Management ip address: $MANAGEMENT_IP" >> $ZSTACK_INSTALL_LOG

# Copy zstack trial license into /var/lib/zstack/license
if [ -f $ZSTACK_TRIAL_LICENSE ]; then
  mkdir -p /var/lib/zstack/license
  /bin/cp -f $ZSTACK_TRIAL_LICENSE /var/lib/zstack/license
fi

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

echo_hints_to_upgrade_iso()
{
    echo
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    if [ x"${PRODUCT_NAME^^}" == x"ZSTACK" ]; then
        ISO_NAME="ZStack-x86-64-DVD-${VERSION_RELEASE_NR}.iso"
        UPGRADE_WIKI="http://www.zstack.io/support/productsupport/tutorial/"
        ISO_DOWNLOAD_LINK="http://www.zstack.io/product_downloads/"
    elif [ x"${PRODUCT_NAME^^}" == x"ZSTACK-COMMUNITY" ]; then
        ISO_NAME="ZStack-Community-x86-64-DVD-${VERSION_RELEASE_NR}.iso "
        UPGRADE_WIKI="http://www.zstack.io/community/tutorials/ISOupgrade/"
        ISO_DOWNLOAD_LINK="http://www.zstack.io/community/downloads/"
    elif [ x"${PRODUCT_NAME^^}" == x"ZSTACK-ENTERPRISE" ]; then
        ISO_NAME="ZStack-Enterprise-x86-64-DVD-${VERSION_RELEASE_NR}.iso"
        UPGRADE_WIKI="http://www.zstack.io/support/productsupport/tutorial/"
        ISO_DOWNLOAD_LINK="http://www.zstack.io/product_downloads/"
    else
        fail "The current local repo is not suitable for ${PRODUCT_NAME} installation.\n" \
            "Syncing local repo with repo.zstack.io has been failed too.\n" \
            "Please download proper ISO and upgrade the local repo first."
    fi

    fail "The current local repo is not suitable for ${PRODUCT_NAME} installation.\n" \
        "Syncing local repo with repo.zstack.io has been failed too.\n" \
        "Please download ${ISO_NAME} from ${ISO_DOWNLOAD_LINK} and run:\n" \
        "# wget http://cdn.zstack.io/product_downloads/scripts/${PRODUCT_NAME,,}-upgrade\n" \
        "# bash ${PRODUCT_NAME,,}-upgrade ${ISO_NAME}\n" \
        "For more information, see ${UPGRADE_WIKI}"
}

echo_upgrade_local_repo_use_iso() {
    echo
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG

    fail "The current local repo is not suitable for ${PRODUCT_NAME} installation.\n"\
        "required repo version($(cat .repo_version)) do not match remote repo version($(cat .remote_repo_version)).\n"\
        "Please download ISO and update you local repo\n"
}

echo_custom_pcidevice_xml_warning_if_need() {
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    zstack_home=`eval echo ~zstack`
    old_xml="$zstack_home/upgrade/`ls $zstack_home/upgrade/ -rt | tail -1`/zstack/WEB-INF/classes/mevoco/pciDevice/customPciDevices.xml"
    [ -f $old_xml ] || return

    new_xml="$zstack_home/apache-tomcat/webapps/zstack/WEB-INF/classes/mevoco/pciDevice/customPciDevices.xml"
    diff $old_xml $new_xml >/dev/null || echo -e "$(tput setaf 3) Your old customPciDevices.xml was saved in $old_xml"
}

echo_chrony_server_warning_if_need()
{
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    CHRONY_SERVER=(`zstack-ctl show_configuration | grep "^[[:space:]]*chrony.serverIp" | awk -F '=' '{print $2}' | sed s/[[:space:]]//g`)
    if [ ${#CHRONY_SERVER[*]} -eq 1 ]  && [ x${CHRONY_SERVER[0]} == x${MANAGEMENT_IP} ]; then
        echo  -e "$(tput setaf 3) - chrony server sources is set to management node by default.$(tput sgr0)"
        echo ""
    fi
}

check_ha_need_upgrade()
{
    trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
    [ x"$BASEARCH" != x"x86_64" ] && return
    [ x`systemctl is-enabled zstack-ha 2>/dev/null` != x"enabled" ] && return

    local newha="$ZSTACK_HOME/WEB-INF/classes/tools/zsha2"
    chmod u+x "$newha" 2>/dev/null
    [ -x "$newha" ] || return

    local curver=`zsha2 version 2>/dev/null | awk -F"[ ,]" '{print $2}'`
    local newver=`"$newha" version 2>/dev/null | awk -F"[ ,]" '{print $2}'`
    [ x"$curver" = x"$newver" ] && return

    local higher=`get_higher_version "$curver" "$newver"`
    if [ x"$higher" = x"$newver" ]; then
        echo  -e "$(tput setaf 3) - a newer version of zsha2 is available at $newha. $(tput sgr0)"
        echo
    fi
}

enforce_history() {
trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
mkdir -p /var/log/history.d/
cat << 'EOF' > /etc/logrotate.d/history
/var/log/history.d/history {
    create 0666 root root
    monthly
    rotate 6
    create
    dateext
    compress
    minsize 1M
}
EOF
cat << 'EOF' > /etc/profile.d/history.sh
shopt -s histappend
HISTTIMEFORMAT='%F %T '
HISTSIZE="5000"
HISTFILESIZE=5000
PROMPT_COMMAND='(umask 000; msg=$(history 1 | { read x y; echo $y; }); echo [$(who am i | awk "{print \$(NF-2),\$(NF-1),\$NF}")] [$(whoami)@`pwd`]" $msg" >>/var/log/history.d/history)'
export HISTTIMEFORMAT HISTSIZE HISTFILESIZE PROMPT_COMMAND
EOF
# modify libvirtd.qemu logrotate configuration file.
cat << 'EOF' > /etc/logrotate.d/libvirtd.qemu
/var/log/libvirt/qemu/*.log {
    weekly
    missingok
	notifempty
    rotate 2
    compress
    delaycompress
    copytruncate
}
EOF
}

# make sure local repo files exist
if [ "$IS_YUM" = "y" ];then
    # make sure local repo exist and dependences installed
    create_local_repo_files
elif [ "$IS_APT" = "y" ];then
    create_local_source_list_files
else
    fail2 "Command yum or apt not found, cannot create local repo."
fi


# CHECK_REPO_VERSION
if [ x"${CHECK_REPO_VERSION}" == x"True" ]; then
    echo_title "Check Repo Version"
    echo
    show_spinner check_sync_local_repos
fi
check_zstack_release

# whether mevoco-1\.*.jar exists
MEVOCO_1_EXISTS='n'
if [ -f $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_LIBS/mevoco-1\.*.jar ]; then
    MEVOCO_1_EXISTS='y'
fi

#set http_proxy if needed
if [ ! -z $HTTP_PROXY ]; then
    export http_proxy=$HTTP_PROXY
    export https_proxy=$HTTP_PROXY
fi

# enforce history
enforce_history

if [ x"$UPGRADE" = x'y' ]; then
    if [ -f $UPGRADE_LOCK ]; then
        echo -e "$(tput setaf 1) FAIL\n$(tput sgr0)"
        echo -e "$(tput setaf 1)  Reason: $UPGRADE_LOCK exist. If no other upgrading operation, please manually remove $UPGRADE_LOCK.\n$(tput sgr0)"
        exit 1
    fi

    ZSTACK_INSTALL_ROOT=`eval echo "~zstack"`
    ZSTACK_VERSION=$ZSTACK_INSTALL_ROOT/VERSION

    MINI_INSTALL_ROOT=${ZSTACK_INSTALL_ROOT}/zstack-mini/
    MINI_VERSION=${MINI_INSTALL_ROOT}/VERSION

    check_version
    touch $UPGRADE_LOCK
    upgrade_folder=`mktemp`
    rm -f $upgrade_folder
    mkdir -p $upgrade_folder
    zstack-ctl status 2>/dev/null|grep 'MN status' >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        zstack-ctl status 2>/dev/null |grep 'MN status'|grep Running >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            CURRENT_STATUS='y'
        else
            CURRENT_STATUS='n'
        fi
    else
        zstack-ctl status 2>/dev/null |grep Running >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            CURRENT_STATUS='y'
        else
            CURRENT_STATUS='n'
        fi
    fi
    UI_CURRENT_STATUS='n'
    # for zstack-mini-1.0.0, 'zstack-ctl stop' cannot stop mini-server
    [ -d /usr/local/zstack-mini ] && systemctl stop zstack-mini
    UI_INSTALLATION_STATUS='y'
    zstack-ctl status 2>/dev/null|grep -q 'UI status' >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        zstack-ctl status 2>/dev/null |grep 'UI status'|grep Running >/dev/null 2>&1
        if [ $? -eq 0 ]; then
            UI_CURRENT_STATUS='y'
        else
            UI_CURRENT_STATUS='n'
        fi
    fi

    DASHBOARD_CURRENT_STATUS='n'
    DASHBOARD_INSTALLATION_STATUS='n'
    if [ -f /etc/init.d/zstack-dashboard ]; then
        DASHBOARD_INSTALLATION_STATUS='y'
        /etc/init.d/zstack-dashboard status | grep -i 'running' > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            DASHBOARD_CURRENT_STATUS='y'
        fi
    fi
fi

#Set ZSTACK_HOME for zstack-ctl.
export ZSTACK_HOME=$ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_PATH
grep "ZSTACK_HOME" ~/.bashrc > /dev/null
if [ $? -eq 0 ]; then
    sed -i "s#export ZSTACK_HOME=.*#export ZSTACK_HOME=${ZSTACK_HOME}#" ~/.bashrc
else
    echo "export ZSTACK_HOME=${ZSTACK_HOME}" >> ~/.bashrc
fi

#Do preinstallation checking for CentOS and Ubuntu
check_system

if [ "$IS_YUM" = "y" ]; then
     install_sync_repo_dependences
fi

## set ln
cloudCtlPath="/usr/bin/cloud-ctl"
if [[ ! -f "$cloudCtlPath" ]]; then
  ln -s /usr/bin/zstack-ctl $cloudCtlPath
fi

cloudCliPath="/usr/bin/cloud-cli"
if [[ ! -f "$cloudCliPath" ]]; then
  ln -s /usr/bin/zstack-cli $cloudCliPath
fi

productCtlPath="/usr/bin/${PRODUCT_NAME,,}-ctl"
if [[ ! -f "$productCtlPath" ]]; then
  ln -s /usr/bin/zstack-ctl $productCtlPath
fi

productCliPath="/usr/bin/${PRODUCT_NAME,,}-cli"
if [[ ! -f "$productCliPath" ]]; then
  ln -s /usr/bin/zstack-cli $productCliPath
fi

#Download ${PRODUCT_NAME} all in one package
download_zstack

if [ x"$UPGRADE" = x'y' ]; then

    #only upgrade zstack
    upgrade_zstack

    #Setup audit.rules
    setup_audit_file

    cd /; rm -rf $upgrade_folder
    cleanup_function

    if [ ! -z $ONLY_UPGRADE_CTL ]; then
        echo_star_line
        echo -e "$(tput setaf 2)${PRODUCT_NAME,,}-ctl has been upgraded to version: ${VERSION}$(tput sgr0)"
        echo ""
        echo_star_line
        disable_zstack_tui
        kill_zstack_tui_and_restart_tty1
        exit 0
    fi

    [ -z $VERSION ] && VERSION=`zstack-ctl status 2>/dev/null|grep version|awk '{print $2}'`
    echo ""
    echo_star_line
    echo -e "$(tput setaf 2)${PRODUCT_NAME} has been successfully upgraded to version: ${VERSION}$(tput sgr0)"
    echo ""
    if [ x"$CURRENT_STATUS" = x'y' ]; then
        if [ -z $NEED_KEEP_DB ];then
            echo -e " $(tput setaf 2)Management node has been started up again.$(tput sgr0) You can use \`${PRODUCT_NAME,,}-ctl status\` to check its status."
        else
            echo -e " $(tput setaf 3)Management node is not started up, since using -k option to skip database upgrading.$(tput sgr0) You can use \`${PRODUCT_NAME,,}-ctl start\` to start all services, after upgrading database manually."
        fi
    else
        echo -e " $(tput setaf 3)Management node is not started. Please use \`${PRODUCT_NAME,,}-ctl start\` to start it up.$(tput sgr0)"
    fi
    echo ""
    if [ x"$UI_INSTALLATION_STATUS" = x'y' ]; then
        echo -e " $(tput setaf 2)${PRODUCT_NAME,,}-ui has been upgraded.$(tput sgr0)"
        echo ""
        if [ x"$UI_CURRENT_STATUS" = x'y' -o x"$DASHBOARD_CURRENT_STATUS" = x'y' ]; then
            echo -e " $(tput setaf 2)${PRODUCT_NAME,,}-ui has been started up again.$(tput sgr0)"
        else
            echo -e " $(tput setaf 3)${PRODUCT_NAME,,}-ui is not started. You can manually start it up by \`${PRODUCT_NAME,,}-ctl start_ui\`$(tput sgr0)"
        fi
    elif [ x"$DASHBOARD_INSTALLATION_STATUS" = x'y' ]; then
        echo -e " $(tput setaf 2)zstack-dashboard has been upgraded.$(tput sgr0)"
        echo ""
        if [ x"$UI_CURRENT_STATUS" = x'y' -o x"$DASHBOARD_CURRENT_STATUS" = x'y' ]; then
            echo -e " $(tput setaf 2)zstack-dashboard has been started up again.$(tput sgr0)"
        else
            echo -e " $(tput setaf 3)zstack-dashboard is not started. You can manually start it up by \`zstack-ctl start_ui\`$(tput sgr0)"
        fi
    else
        echo " ${PRODUCT_NAME} UI was not upgraded, since there wasn't UI installed before upgrading. You can manually install UI by \`${PRODUCT_NAME,,}-ctl install_ui\`"
    fi
    echo ""
    zstack_home=`eval echo ~zstack`
    echo_chrony_server_warning_if_need
    check_ha_need_upgrade
    #echo " Your old zstack was saved in $zstack_home/upgrade/`ls $zstack_home/upgrade/ -rt|tail -1`"
    echo_custom_pcidevice_xml_warning_if_need
    echo_star_line
    disable_zstack_tui
    kill_zstack_tui_and_restart_tty1
    post_scripts_to_restore_iptables_rules
    if [[ $DEBIAN_OS =~ $OS ]];then
        post_restore_source_on_debian
    fi
    exit 0
fi

#Install unzip and unpack zstack war into apache tomcat
unpack_zstack_into_tomcat

#Do not config NFS or HTTP when installing ZStack product
[ ! -z $INSTALL_MONITOR ] && NEED_NFS='' && NEED_HTTP=''

#Install ${PRODUCT_NAME} required system libs through ansible
install_system_libs

#Install Ansible
install_ansible

if [ ! -z $ONLY_INSTALL_LIBS ];then
    echo ""
    echo_star_line
    echo "Finish installing ${PRODUCT_NAME} dependent software."
    echo "${PRODUCT_NAME} management node and Tomcat are not installed."
    echo "P.S.: selinux is disabled!"
    echo_star_line
    disable_zstack_tui
    kill_zstack_tui_and_restart_tty1
    exit 0
fi

#Download and install ${PRODUCT_NAME} Package
install_zstack

#Post Configuration, including apache, zstack-server, NFS Server, HTTP Server
config_system

#If tomcat use the default conf update it
set_tomcat_config

if [ -f $ZSTACK_VERSION -a -z "$VERSION" ]; then
    VERSION=`cat $ZSTACK_VERSION`' '
else
    VERSION=''
fi

if [ ! -z $ONLY_INSTALL_ZSTACK ]; then
    echo ""
    echo_star_line
    echo "${PRODUCT_NAME} ${VERSION}management node is installed to $ZSTACK_INSTALL_ROOT."
    echo "Mysql and are not installed. You can use ${PRODUCT_NAME,,}-ctl to install them and start ${PRODUCT_NAME} service later. "
    echo_chrony_server_warning_if_need
    check_ha_need_upgrade
    echo_star_line
    disable_zstack_tui
    kill_zstack_tui_and_restart_tty1
    exit 0
fi

#Install Mysql
install_db

#Setup audit.rules
setup_audit_file

#Setup install parameters
setup_install_param

#Delete old monitoring data if NEED_DROP_DB
if [ -n "$NEED_DROP_DB" ]; then
  kill -9 `ps aux | grep "/var/lib/zstack/prometheus/data" | grep -v 'grep' | awk -F ' ' '{ print $2 }'` 2>/dev/null
  pkill -9 influxd 2>/dev/null
  rm -rf /var/lib/zstack/prometheus/data/*
  rm -rf /var/lib/zstack/prometheus/data2/*
  rm -rf /var/lib/zstack/influxdb/
fi

zstack-ctl configure management.server.ip="${MANAGEMENT_IP}"
if [ ! -z $NEED_SET_MN_IP ];then
    if [ -z $CONSOLE_PROXY_ADDRESS ];then
        zstack-ctl configure consoleProxyOverriddenIp="${MANAGEMENT_IP}"
    fi
fi

# configure chrony.serverIp if not exists
zstack-ctl show_configuration | grep '^[[:space:]]*chrony.serverIp.' >/dev/null 2>&1
[ $? -ne 0 ] && zstack-ctl configure chrony.serverIp.0="${MANAGEMENT_IP}"

#Install license
install_license

#Start ${PRODUCT_NAME} 
if [ -z $NOT_START_ZSTACK ]; then
    start_zstack
fi

#set http_proxy for install zstack-ui if needed.
if [ ! -z $HTTP_PROXY ]; then
    export http_proxy=$HTTP_PROXY
    export https_proxy=$HTTP_PROXY
fi

#Start ${PRODUCT_NAME}-UI
if [ -z $NOT_START_ZSTACK ]; then
    if [ -f $ZSTACK_INSTALL_ROOT/$CATALINA_ZSTACK_TOOLS/zstack_ui.bin ]; then
        start_zstack_ui
        rm -f /etc/init.d/zstack-dashboard
    else
        start_dashboard
        rm -f /etc/init.d/zstack-ui
    fi
fi

if [ -f /bin/systemctl ]; then
    systemctl start zstack.service >/dev/null 2>&1
fi

#Start bootstrap service for mini
if [ x"$MINI_INSTALL" = x"y" ];then
    install_zstack_network
    cp /opt/zstack-dvd/${BASEARCH}/${ZSTACK_RELEASE}/mini_auto_check /etc/init.d/
    chmod +x /etc/init.d/mini_auto_check
    echo "systemctl start zstack-network-agent" >> /etc/rc.local
    echo "[ -f /etc/init.d/mini_auto_check ] && bash /etc/init.d/mini_auto_check" >> /etc/rc.local
    echo "[ -f /etc/issue.bak ] && mv /etc/issue.bak /etc/issue" >> /etc/profile
    cp /etc/issue /etc/issue.bak
fi

config_journal(){
trap 'traplogger $LINENO "$BASH_COMMAND" $?'  DEBUG
#create journal log dir
    which systemd-tmpfiles >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        journal_path="/var/log/journal"
        if [ ! -d $journal_path ]; then
            mkdir -p $journal_path
            systemd-tmpfiles --create --prefix $journal_path >>$ZSTACK_INSTALL_LOG 2>&1
            systemctl restart systemd-journald
        fi
    fi
}

config_firewalld(){
    systemctl stop firewalld
    systemctl disable firewalld
}

config_journal
config_firewalld

#Install SDS
if [ x"$SDS_INSTALL" = x"y" ];then
    install_sds
fi

#Print all installation message
if [ -z $NOT_START_ZSTACK ]; then
    [ -z $VERSION ] && VERSION=`zstack-ctl status 2>/dev/null|grep version|awk '{print $2}'`
fi

echo ""
echo_star_line
touch $README

echo -e "${PRODUCT_NAME} All In One ${VERSION} Installation Completed:
 - UI is running, visit $(tput setaf 4)http://$MANAGEMENT_IP:$DEFAULT_UI_PORT$(tput sgr0) in Chrome
      Use $(tput setaf 3)${PRODUCT_NAME,,}-ctl [stop_ui|start_ui]$(tput sgr0) to stop/start the UI service

 - Management node is running
      Use $(tput setaf 3)${PRODUCT_NAME,,}-ctl [stop|start]$(tput sgr0) to stop/start it

 - ${PRODUCT_NAME} command line tool is installed: ${PRODUCT_NAME,,}-cli
 - ${PRODUCT_NAME} control tool is installed: ${PRODUCT_NAME,,}-ctl

 - For system security, change the mysql default password for 'root' user using \`mysqladmin -u root --password=OLD_PASSWORD password NEW_PASSWORD\`" | tee -a $README

if [ x"$SDS_INSTALL" = x"y" ];then
    echo " - SDS successfully installed, Please visit http://${MANAGEMENT_IP}:8056 to continue the installation"
fi

if [ ! -z QUIET_INSTALLATION ]; then
    if [ -z "$CHANGE_HOSTNAME" -a -z "$CHANGE_HOSTS" -a -z "$DELETE_PY_CRYPTO" -a -z "$SETUP_EPEL" ];then
        true
    else
        echo -e "\n$(tput setaf 6) User select QUIET installation. Installation does following changes for user:"
        if [ ! -z "$CHANGE_HOSTNAME" ]; then
            echo " - HOSTNAME is changed to '$CHANGE_HOSTNAME' to avoid of mysql server installation failure."
        fi
        if [ ! -z "$CHANGE_HOSTS" ]; then
            echo " - /etc/hosts is added a new line: '$CHANGE_HOSTNAME'"
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

echo_chrony_server_warning_if_need
check_ha_need_upgrade
echo_star_line
disable_zstack_tui
kill_zstack_tui_and_restart_tty1
post_scripts_to_restore_iptables_rules

