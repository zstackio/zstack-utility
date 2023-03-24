#!/bin/bash

export LANG=en_US.UTF-8
export LANGUAGE=en_US:

SKIP_MD5_CHECK=""
LOGPATH=/var/log/zstack
LOGFLLE=zwatch-update.log
LOGPATH_EXISTS=""

TEMP_PATH="/tmp/zstack/"

while :
do
  [ -z "$1" ] && break;
  case "$1" in
    --skip-md5-check ) SKIP_MD5_CHECK='y'; shift;;
    --log-path ) LOGPATH=$2; shift 2;;
  esac
done

case `uname -s` in
  Linux)
    AGENT_OS="linux"
    ;;
  FreeBSD)
    AGENT_OS="freebsd"
    ;;
  *)
    echo "Unsupported OS: $(uname -s)"
    exit 1
    ;;
esac

ARCH=`uname -m`
if [ x"$ARCH" == x"x86_64" ]; then
  LABLE=".${AGENT_OS}-amd64"
else
  LABLE=".${AGENT_OS}-${ARCH}"
fi
BIN_NAME="zwatch-vm-agent${LABLE}"

if [ -d $LOGPATH ]; then
  LOGPATH_EXISTS="y"
fi
version=""

# functions

log_info() {
  if [ x"$LOGPATH_EXISTS" == x"y" ]; then
    echo "$(date) $1" >> "${LOGPATH}/${LOGFLLE}"
  fi
  if [ -z $2 ]; then
    echo $1
  fi
}

send_install_result() {
  curl -H "Content-Type: application/json" -H "commandpath: /host/zwatchInstallResult" -X POST -d "{\"vmInstanceUuid\": \"${vmInstanceUuid}\", \"version\": \"$1\"}" http://169.254.169.254/host/zwatchInstallResult
}

check_version_file() {
  AGENT_VERSION=`curl -s http://169.254.169.254/agent_version`
  if [[ ! ${AGENT_VERSION} =~ ${BIN_NAME} ]]; then
    log_info "Fail to parse agent_version file"
    log_info "agent_version context: ${AGENT_VERSION}" not-print-to-screen
    log_info "agent tools file name: ${BIN_NAME}" not-print-to-screen
    exit 1
  fi
}

download_agent_tools() {
  if [ ! -z $TEMP_PATH ]; then
    mkdir $TEMP_PATH
  fi
  cd $TEMP_PATH
  if [ x"$AGENT_OS" == x"freebsd" ]; then
    curl http://169.254.169.254/zwatch-vm-agent-freebsd --silent -o zwatch-vm-agent.download
  else
    curl http://169.254.169.254/zwatch-vm-agent --silent -o zwatch-vm-agent.download
  fi
  cd - &> /dev/null
}

clean_download_file() {
  rm -rf $TEMP_PATH
}

check_md5() {
  if [ x"$SKIP_MD5_CHECK" == x"y" ]; then
    return
  fi

  if [ x"$AGENT_OS" == x"freebsd" ]; then
    BIN_MD5=`md5 $TEMP_PATH/zwatch-vm-agent.download | awk '{print $4}'`
  else
    BIN_MD5=`md5sum $TEMP_PATH/zwatch-vm-agent.download | awk '{print $1}'`
  fi
  if [[ ! ${AGENT_VERSION} =~ "md5-${BIN_NAME}=${BIN_MD5}" ]]; then
    log_info "there was an error downloading the zwatch-vm-agent, check md5sum fail"
    exit 1
  fi
}

query_agent_info() {
  vmInstanceUuid=`curl --silent http://169.254.169.254/2009-04-04/meta-data/instance-id`
  version=`echo "$AGENT_VERSION" | grep "zwatch-vm-agent=" | awk -F '=' '{print $2}'`
}

install_agent_tools() {
  cd $TEMP_PATH
  chmod +x zwatch-vm-agent.download
  bash -x ./zwatch-vm-agent.download
  cd - &> /dev/null
  clean_download_file
  if [ $? != 0 ]; then
    send_install_result "InstallFailed"
    log_info "install zwatch-vm-agent fail"
    exit 1
  fi
}

start_agent_tools() {
  service zwatch-vm-agent restart

  if [ $? != 0 ]; then
    send_install_result "InstallFailed"
    log_info "service zwatch-vm-agent start fail"
    exit 1
  fi

  os_type=`cat /etc/os-release | grep -i "^ID=" | cut -d '=' -f 2 | cut -d '"' -f 2`
  os_version=`cat /etc/os-release | grep -i "^VERSION_ID=" | cut -d '=' -f 2 | cut -d '"' -f 2`
  result="version=${version},os_type=${os_type} ${os_version},platform=$(uname -s)"
  send_install_result "$result"
  log_info "send_install_result: ${result}"
  if [ $? != 0 ]; then
    log_info "send_install_result fail"
  fi
}

# process

log_info "installing zwatch-vm-agent"
check_version_file

log_info "downloading zwatch-vm-agent"
download_agent_tools
check_md5
query_agent_info

log_info "install zwatch-vm-agent"
install_agent_tools

log_info "starting zwatch-vm-agent"
start_agent_tools

log_info "start zwatch-vm-agent successfully"
