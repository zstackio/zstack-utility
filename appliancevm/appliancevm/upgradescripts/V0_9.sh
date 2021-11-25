#!/bin/sh

# before 0.9, the sshd binds to 0.0.0.0 by default.
# now it only binds to the management nic eth0

set -o pipefail
ipaddr=`ip addr show dev eth0 |grep inet|grep -v inet6|awk -F'inet' '{print $2}'|awk '{print $1}'|awk -F'/' '{print $1}'`
set +o pipefail

grep "^ListenAddress" /etc/ssh/sshd_config >/dev/null
if [ $? -ne 0 ]; then
    echo "ListenAddress $ipaddr" >> /etc/ssh/sshd_config
    set -u
    /etc/init.d/sshd restart

    for i in {1..30}
    do
        /etc/init.d/sshd status
        if [ $? -eq 0 ]; then
            exit 0
        fi
        sleep 0.5
    done

    >$2 echo "failed sshd is not running after 15s"
    exit 1
fi

exit 0


