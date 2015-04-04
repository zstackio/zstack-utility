#!/bin/sh

echo -e "\n**************************************************************"
echo "Check zstack Build and Running Environment"
echo -e "**************************************************************\n\n"

error_flag=0
warn_flag=0

check_msg(){
    echo -n "Check $1"
}

check_result(){
    if [ $1 -eq 0 ];then
        echo -e "\t... ... ... ... [\E[32mPass\E[30m]"
    else
        echo -e "\t... ... ... ... [\E[31mFail\E[30m]"
        error_flag=1
    fi
}

check_warn(){
    if [ $1 -eq 0 ];then
        echo -e "\t... ... ... ... [\E[32mPass\E[30m]"
    else
        echo -e "\t... ... ... ... [\E[33mWarn\E[30m]"
        warn_flag=1
    fi
}

#check ant
check_msg "#ant command"
which ant >/dev/null 2>&1
check_warn $?

#check maven
check_msg "#mvn command"
which mvn >/dev/null 2>&1
check_warn $?

#check tomcat TODO: need to add automation download/install tomcat
check_msg "apache-tomcat"
ls /root/apache-tomcat >/dev/null 2>&1
check_warn $?

#check elasticsearch. TODO: need to add automation download/install elasticsearch
check_msg "elasticsearch"
ls /root/elasticsearch >/dev/null 2>&1
check_warn $?

#check java
check_msg "#java command"
which java >/dev/null 2>&1
check_result $?

#check mysqld
check_msg "mysql server status"
service mysqld status >/dev/null 2>&1
check_result $?

#check puppet server
check_msg "puppet server status"
service puppetmaster status >/dev/null 2>&1
check_result $?

#check rabbitmq
check_msg "rabbitmq server status"
service rabbitmq-server status >/dev/null 2>&1
check_result $?

echo -e "\n\n**************************************************************"
if [ $error_flag -eq 0 ]; then
    echo "zstack environment checking pass."
    echo -e "**************************************************************"
else
    echo -e "zstack environment checking failed.\nPlease manually check and enable failed item!"
    echo -e "**************************************************************"
    exit 1
fi
