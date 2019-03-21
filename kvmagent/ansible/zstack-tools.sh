#!/bin/bash

echo "installing zwatch-vm-agent"

export LANG=en_US.UTF-8
export LANGUAGE=en_US:

case `uname -s` in
  Linux)
    AGENT_OS="linux"
    ;;
  *)
    echo "Unsupported OS: $(uname -s)"
    exit 1
    ;;
esac

if [[ `uname -m` = "x86_64" ]]; then
    ARCH="amd64"
else
    ARCH="386"
fi

BIN_NAME=zwatch-vm-agent.${AGENT_OS}-${ARCH}.bin

NAME=zwatch-vm-agent.${AGENT_OS}-${ARCH}

AGENT_VERSION=`curl -s http://169.254.169.254/agent_version`
if [[ ! ${AGENT_VERSION} =~ $NAME ]]; then
    echo "can't get the ${BIN_NAME} latest version"
    exit 1
fi

echo "downloading ${BIN_NAME}"
curl http://169.254.169.254/${BIN_NAME} --silent -O

BIN_MD5=`md5sum ${BIN_NAME} | awk '{print $1}'`
if [[ ! ${AGENT_VERSION} =~ "md5-$NAME=${BIN_MD5}" ]]; then
    echo "there was an error downloading the ${BIN_NAME}, check md5sum fail"
    exit 1
fi


echo "install ${BIN_NAME}"
chmod +x ${BIN_NAME}
./${BIN_NAME} -id i
if [ $? != 0 ]; then
     echo "install ${BIN_NAME} fail"
     exit 1
fi


echo "start zwatch-vm-agent"
service zwatch-vm-agent start
if [ $? != 0 ]; then
     echo "service zwatch-vm-agent start fail"
     exit 1
fi

echo zwatch-vm-agent installed and runing
