#!bin/bash
sed -i "/md5.*linux-amd.*/s//md5-zwatch-vm-agent.linux-amd64=`md5sum zwatch-vm-agent | awk -F ' ' '{print $1}'`/g" agent_version
sed -i "/md5.*aarch.*/s//md5-zwatch-vm-agent.linux-aarch64=`md5sum zwatch-vm-agent_aarch64 | awk -F ' ' '{print $1}'`/g" agent_version
sed -i "/md5.*loongarch.*/s//md5-zwatch-vm-agent.linux-loongarch64=`md5sum zwatch-vm-agent_loongarch64 | awk -F ' ' '{print $1}'`/g" agent_version
sed -i "/md5.*mips.*/s//md5-zwatch-vm-agent.linux-mips64el=`md5sum zwatch-vm-agent_mips64el | awk -F ' ' '{print $1}'`/g" agent_version
sed -i "/md5.*freebsd.*/s//md5-zwatch-vm-agent.freebsd-amd64=`md5sum zwatch-vm-agent-freebsd | awk -F ' ' '{print $1}'`/g" agent_version