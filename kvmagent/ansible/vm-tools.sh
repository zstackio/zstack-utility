#!/bin/bash

echo "installing zwatch-vm-agent"

export LANG=en_US.UTF-8
export LANGUAGE=en_US:

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

AGENT_VERSION=`curl -s http://169.254.169.254/agent_version`
if [[ ! ${AGENT_VERSION} =~ ${BIN_NAME} ]]; then
    echo "can't get the ${BIN_NAME} latest version"
    exit 1
fi

echo "downloading ${BIN_NAME}"
curl http://169.254.169.254/${BIN_NAME} --silent -O

BIN_MD5=`md5sum ${BIN_NAME} | awk '{print $1}'`
if [[ ! ${AGENT_VERSION} =~ "md5-${BIN_NAME}=${BIN_MD5}" ]]; then
    echo "there was an error downloading the ${BIN_NAME}, check md5sum fail"
    exit 1
fi

vmInstanceUuid=`curl http://169.254.169.254/2009-04-04/meta-data/instance-id`
version=`echo $AGENT_VERSION | awk -F '=' '{print $2}' | awk '{print $1}'`

echo "stopping zwatch-vm-agent"
service zwatch-vm-agent stop

echo "install ${BIN_NAME}"
chmod +x ${BIN_NAME}
./${BIN_NAME} -i
if [ $? != 0 ]; then
     curl -H "Content-Type: application/json" -H "commandpath: /host/zwatchInstallResult" -X POST -d "{\"vmInstanceUuid\": \"${vmInstanceUuid}\", \"version\": \"${InstallFailed}\"}" http://169.254.169.254/host/zwatchInstallResult
     echo "install ${BIN_NAME} fail"
     exit 1
fi


echo "starting zwatch-vm-agent"
service zwatch-vm-agent start
if [ $? != 0 ]; then
     curl -H "Content-Type: application/json" -H "commandpath: /host/zwatchInstallResult" -X POST -d "{\"vmInstanceUuid\": \"${vmInstanceUuid}\", \"version\": \"${InstallFailed}\"}" http://169.254.169.254/host/zwatchInstallResult
     echo "service zwatch-vm-agent start fail"
     exit 1
fi

curl -H "Content-Type: application/json" -H "commandpath: /host/zwatchInstallResult" -X POST -d "{\"vmInstanceUuid\": \"${vmInstanceUuid}\", \"version\": \"${version}\"}" http://169.254.169.254/host/zwatchInstallResult
echo "start zwatch-vm-agent successfully"
