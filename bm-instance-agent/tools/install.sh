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
yes | cp ${temp}/service.conf /var/lib/zstack/baremetalv2/bm-instance-agent/service.conf

popd

sed -i '/SELINUX=/s/enforcing/permissive/g' /etc/selinux/config >/dev/null 2>&1 || true
setenforce 0 >/dev/null 2>&1 || true

if which systemctl &> /dev/null; then
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
ExecStart=/var/lib/zstack/baremetalv2/bm-instance-agent/bm-instance-agent.pex

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload \
        && systemctl enable zstack-baremetal-instance-agent \
        && systemctl restart zstack-baremetal-instance-agent
else
    cat << 'EOF' > /etc/init.d/zstack-baremetal-instance-agent
#!/bin/bash
# chkconfig: 2345 77 22
# description: ZStack Baremetal Agent Service

# return value
RETVAL=0
server_dir="/var/lib/zstack/baremetalv2/bm-instance-agent"
server_name="zstack-baremetal-instance-agent"


start() {
    echo -n "Starting ${server_name}:"
        /bin/sh -c "/sbin/iptables -t filter -C INPUT -p tcp --dport=7090 -j ACCEPT 2>/dev/null || /sbin/iptables -t filter -I INPUT -p tcp --dport=7090 -j ACCEPT || true"
        /bin/sh -c "/sbin/iptables -t filter -C INPUT -p tcp --dport=4200 -j ACCEPT 2>/dev/null || /sbin/iptables -t filter -I INPUT -p tcp --dport=4200 -j ACCEPT || true"
        PIDS=`ps -ef |grep .pex/unzipped_pexes |grep -v grep | awk '{print $2}'`
    if [ "$PIDS" != "" ]; then
        echo "${server_name} is runing!"
    else
        nohup /var/lib/zstack/baremetalv2/bm-instance-agent/bm-instance-agent.pex >> /nohup.log 2>&1 &
        echo ".... SUCCESS"
    fi
}


stop(){
    echo -n "Stopping ${server_name}:"
    PIDS=`ps -ef |grep .pex/unzipped_pexes |grep -v grep | awk '{print $2}'`
    if [ "$PIDS" == "" ];then
        echo "No pids exist, is ${server_name} running?"
    else
        for pid in $PIDS; do
            kill -9 "$pid"
            sleep 5
        done
        echo ".... SUCCESS"
    fi
}

status(){
    PIDS=`ps -ef |grep .pex/unzipped_pexes |grep -v grep | awk '{print $2}'`
    if [ "$PIDS" != "" ];then
        echo "${server_name} is running"
    else
        echo "${server_name} is stopped"
    fi
}

case "$1" in
        start)
                start
                ;;
        stop)
                stop
                ;;
        status)
                status
                ;;
        restart)
                stop
                status
                start
                sleep 5
                status
                RETVAL=$?
                ;;
        *)
                echo $"Usage: $0 {start|stop|status|restart}"
                exit 1
esac

exit $RETVAL
EOF

    cd /etc/init.d/
    chkconfig --add zstack-baremetal-instance-agent
    chkconfig --level 2345 zstack-baremetal-instance-agent on
    chmod +x zstack-baremetal-instance-agent
    bash zstack-baremetal-instance-agent restart
fi

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
