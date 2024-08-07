#!/bin/bash

set -e

temp=`mktemp -d`

sed -n -e '1,/^exit 0$/!p' $0 > ${temp}/bm-instance-agent.tar.gz 2>/dev/null

# Check md5sum
pushd ${temp}
echo 'MD5_SUM' > md5sum
md5sum -c md5sum

pkill -9 shellinaboxd || true

tar -zxf bm-instance-agent.tar.gz

mkdir -p /var/lib/zstack/baremetalv2/bm-instance-agent/
mkdir -p /var/log/zstack/baremetalv2/
yes | cp ${temp}/bm-instance-agent.pex /var/lib/zstack/baremetalv2/bm-instance-agent/
yes | cp ${temp}/shellinaboxd-`uname -m` /var/lib/zstack/baremetalv2/bm-instance-agent/
yes | cp ${temp}/shellinaboxd-`uname -m` /usr/bin/shellinaboxd
if [ -f /etc/kylin-release ]; then
  yes | cp ${temp}/shellinaboxd-`uname -m`-kylin /var/lib/zstack/baremetalv2/bm-instance-agent/shellinaboxd-`uname -m`
  yes | cp ${temp}/shellinaboxd-`uname -m`-kylin /usr/bin/shellinaboxd
fi
yes | cp ${temp}/zwatch-vm-agent-`uname -m` /var/lib/zstack/baremetalv2/bm-instance-agent/

popd

sed -i '/SELINUX=/s/enforcing/permissive/g' /etc/selinux/config >/dev/null 2>&1 || true
setenforce 0 >/dev/null 2>&1 || true

mkdir -p /usr/lib/systemd/system/
cat << EOF > /usr/lib/systemd/system/zstack-baremetal-instance-agent.service
[Unit]
Description=ZStack baremetal instance agent
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=3
User=root
ExecStartPre=/bin/sh -c "/sbin/iptables -t filter -C INPUT -p tcp --dport=7090 -j ACCEPT 2>/dev/null || /sbin/iptables -t filter -I INPUT -p tcp --dport=7090 -j ACCEPT || true"
ExecStartPre=/bin/sh -c "/sbin/iptables -t filter -C INPUT -p tcp --dport=4200 -j ACCEPT 2>/dev/null || /sbin/iptables -t filter -I INPUT -p tcp --dport=4200 -j ACCEPT || true"
ExecStartPre=/bin/sh -c "firewall-cmd --permanent --add-port=7090/tcp && firewall-cmd --reload || true"
ExecStartPre=/bin/sh -c "firewall-cmd --permanent --add-port=4200/tcp && firewall-cmd --reload || true"
ExecStart=/var/lib/zstack/baremetalv2/bm-instance-agent/bm-instance-agent.pex --log-file=/var/log/zstack/baremetalv2/bm-instance-agent.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload \
    && systemctl enable zstack-baremetal-instance-agent \
    && systemctl restart zstack-baremetal-instance-agent

chmod +x /var/lib/zstack/baremetalv2/bm-instance-agent/zwatch-vm-agent-`uname -m`
/var/lib/zstack/baremetalv2/bm-instance-agent/zwatch-vm-agent-`uname -m` -i
if [ $? != 0 ]; then
     echo "install zwatch-vm-agent fail"
fi

echo "starting zwatch-vm-agent"
service zwatch-vm-agent start
if [ $? != 0 ]; then
     echo "service zwatch-vm-agent start fail"
     exit 1
fi

echo "start zwatch-vm-agent successfully"

rm -rf ${temp}

exit 0
