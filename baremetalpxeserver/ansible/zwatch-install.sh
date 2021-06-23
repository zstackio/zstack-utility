#!/bin/bash

echo "installing zwatch-vm-agent"

export LANG=en_US.UTF-8
export LANGUAGE=en_US:

usage()
{
    echo "usage: zwatch-install.sh depolyServerIp"
}

if [ $# -ne 1 ]; then
    usage
    exit 1
fi

DEPLOY_SERVER=$1

LABLE=''
ARCH=`uname -m`

case `uname -s` in
  Linux)
    AGENT_OS="linux"
    ;;
  *)
    echo "Unsupported OS: $(uname -s)"
    exit 1
    ;;
esac

if [ x"$ARCH" != x"x86_64" ]; then
    LABLE="_$ARCH"
fi

BIN_NAME="zwatch-vm-agent${LABLE}"

NAME=zwatch-vm-agent.${AGENT_OS}-${ARCH}

echo "curl -s ftp://$DEPLOY_SERVER/agent_version"
AGENT_VERSION=`curl -s ftp://$DEPLOY_SERVER/agent_version`
if [[ ! ${AGENT_VERSION} =~ ${BIN_NAME} ]]; then
    echo "can't get the ${BIN_NAME} latest version"
    exit 1
fi

echo "downloading zwatch-vm-agent"
curl ftp://$DEPLOY_SERVER/zwatch-vm-agent --silent -O

BIN_MD5=`md5sum zwatch-vm-agent | awk '{print $1}'`
if [[ ! ${AGENT_VERSION} =~ "md5-${BIN_NAME}=${BIN_MD5}" ]]; then
    echo "there was an error downloading the zwatch-vm-agent, check md5sum fail"
    exit 1
fi


echo "install zwatch-vm-agent"
chmod +x zwatch-vm-agent
./zwatch-vm-agent -i
if [ $? != 0 ]; then
    echo "install zwatch-vm-agent fail"
    exit 1
fi

printf "\n" >> /usr/local/zstack/zwatch-vm-agent/conf.yaml
echo "pushGatewayUrl:  http://$DEPLOY_SERVER:9093" >> /usr/local/zstack/zwatch-vm-agent/conf.yaml
echo "versionFileUrl:  ftp://$DEPLOY_SERVER/agent_version" >> /usr/local/zstack/zwatch-vm-agent/conf.yaml

# baremetal instance Uuid is stored in /usr/local/zstack/baremetalInstanceUuid
# for version(before 3.8) there is no such file, we have to get baremetalInstanceUuid from /usr/local/bin/zstack_bm_agent.sh
if [ -f /usr/local/zstack/baremetalInstanceUuid ]; then
    BMUUID=`cat /usr/local/zstack/baremetalInstanceUuid`
else
    BMUUID=`grep "baremetalInstanceUuid" /usr/local/bin/zstack_bm_agent.sh  | awk -F '{' '{print $2}' | awk -F '}' '{print $1}' | awk -F ':' '{print $2}' | sed 's/"//g'`
fi
echo "vmInstanceUuid:  $BMUUID" >> /usr/local/zstack/zwatch-vm-agent/conf.yaml

echo "start zwatch-vm-agent"
service zwatch-vm-agent start
if [ $? != 0 ]; then
     echo "start zwatch-vm-agent failed"
     exit 1
fi

echo "start zwatch-vm-agent successflly"