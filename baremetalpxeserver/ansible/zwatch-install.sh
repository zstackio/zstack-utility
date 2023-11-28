#!/bin/bash

echo "installing zwatch-vm-agent"

export LANG=en_US.UTF-8
export LANGUAGE=en_US:

SKIP_MD5_CHECK=""
LOGPATH=/var/log/zstack
LOGFLLE=zwatch-update.log
LOGPATH_EXISTS=""

TEMP_PATH="/tmp/zstack/"

usage()
{
    echo "usage: zwatch-install.sh depolyServerIp"
}

if [ $# -ne 1 ]; then
    usage
    exit 1
fi

DEPLOY_SERVER=$1

case `uname -s` in
  Linux)
    AGENT_OS="linux"
    ;;
# baremetalpxaeserver do not support Freebsd
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
  # in baremetal pxe server, send result to host is not allowed. we only save result to logger
  log_info "install result (only to logger): $1" not-print-to-screen
}

check_version_file() {
  log_info "Get agent version description file from 'ftp://$DEPLOY_SERVER/agent_version'"
  AGENT_VERSION=`curl -s ftp://$DEPLOY_SERVER/agent_version`
  if [[ ! ${AGENT_VERSION} =~ ${BIN_NAME} ]]; then
    log_info "Fail to parse agent_version file"
    log_info "agent_version context: ${AGENT_VERSION}" not-print-to-screen
    log_info "agent tools file name: ${BIN_NAME}" not-print-to-screen
    exit 1
  fi
}

# baremetalpxaeserver do not support Freebsd
download_agent_tools() {
  if [ ! -z $TEMP_PATH ]; then
    mkdir $TEMP_PATH
  fi
  cd $TEMP_PATH
  curl ftp://$DEPLOY_SERVER/zwatch-vm-agent --silent -o zwatch-vm-agent.download
  cd - &> /dev/null
}

clean_download_file() {
  rm -rf $TEMP_PATH
}

check_md5() {
  if [ x"$SKIP_MD5_CHECK" == x"y" ]; then
    return
  fi

  BIN_MD5=`md5sum $TEMP_PATH/zwatch-vm-agent.download | awk '{print $1}'`
  if [[ ! ${AGENT_VERSION} =~ "md5-${BIN_NAME}=${BIN_MD5}" ]]; then
    log_info "there was an error downloading the zwatch-vm-agent, check md5sum fail"
    exit 1
  fi
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
    log_info "service zwatch-vm-agent start fail"
    exit 1
  fi
}

save_baremetal_uuid_to_local() {
  CONF_PATH=/usr/local/zstack/zwatch-vm-agent/conf.yaml
  printf "# write by zwatch-install.sh\n" >> $CONF_PATH
  sed -i '/pushGatewayUrl:/d' $CONF_PATH
  echo "pushGatewayUrl:  http://$DEPLOY_SERVER:9093" >> $CONF_PATH
  sed -i '/versionFileUrl:/d' $CONF_PATH
  echo "versionFileUrl:  ftp://$DEPLOY_SERVER/agent_version" >> $CONF_PATH
  
  # baremetal instance Uuid is stored in /usr/local/zstack/baremetalInstanceUuid
  # for version(before 3.8) there is no such file, we have to get baremetalInstanceUuid from /usr/local/bin/zstack_bm_agent.sh
  if [ -f /usr/local/zstack/baremetalInstanceUuid ]; then
      BMUUID=`cat /usr/local/zstack/baremetalInstanceUuid`
  else
      BMUUID=`grep "baremetalInstanceUuid" /usr/local/bin/zstack_bm_agent.sh  | awk -F '{' '{print $2}' | awk -F '}' '{print $1}' | awk -F ':' '{print $2}' | sed 's/"//g'`
  fi
  sed -i '/vmInstanceUuid:/d' $CONF_PATH
  echo "vmInstanceUuid:  $BMUUID" >> $CONF_PATH
}

# process

log_info "installing zwatch-vm-agent"
check_version_file

log_info "downloading zwatch-vm-agent"
download_agent_tools
check_md5

log_info "install zwatch-vm-agent"
install_agent_tools
save_baremetal_uuid_to_local

log_info "starting zwatch-vm-agent"
start_agent_tools

log_info "start zwatch-vm-agent successfully"