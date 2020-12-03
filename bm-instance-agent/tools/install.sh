#!/bin/bash

set -e

temp=`mktemp -d`

sed -n -e '1,/^exit 0$/!p' $0 > ${temp}/bm-instance-agent.tar.gz 2>/dev/null

# Check md5sum
pushd ${temp}
echo 'MD5_SUM' > md5sum
md5sum -c md5sum

tar -zxf bm-instance-agent.tar.gz

mkdir -p /var/lib/zstack/baremetalv2/bm-instance-agent/
mkdir -p /var/log/zstack/baremetalv2/
yes | cp ${temp}/bm-instance-agent.pex /var/lib/zstack/baremetalv2/bm-instance-agent/
yes | cp ${temp}/shellinaboxd-`uname -i` /var/lib/zstack/baremetalv2/bm-instance-agent/
yes | cp ${temp}/shellinaboxd-`uname -i` /usr/bin/shellinaboxd

popd

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
ExecStartPre=/bin/sh -c "/sbin/iptables -t filter -C INPUT -p tcp --dport=7090 -j ACCEPT 2>/dev/null || /sbin/iptables -t filter -I INPUT -p tcp --dport=7090 -j ACCEPT"
ExecStartPre=/bin/sh -c "/sbin/iptables -t filter -C INPUT -p tcp --dport=4200 -j ACCEPT 2>/dev/null || /sbin/iptables -t filter -I INPUT -p tcp --dport=4200 -j ACCEPT"
ExecStart=/var/lib/zstack/baremetalv2/bm-instance-agent/bm-instance-agent.pex --log-file=/var/log/zstack/baremetalv2/bm-instance-agent.log

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload \
    && systemctl enable zstack-baremetal-instance-agent \
    && systemctl restart zstack-baremetal-instance-agent

rm -rf ${temp}

exit 0
