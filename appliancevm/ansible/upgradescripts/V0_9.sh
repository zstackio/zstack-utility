#!/bin/sh

# before 0.9, the sshd binds to 0.0.0.0 by default.
# now it only binds to the management nic eth0

set -o pipefail
ipaddr=`/sbin/ifconfig eth0 | grep 'inet addr:' | cut -d: -f2 | awk '{ print $1}'`
set +o pipefail

grep "^ListenAddress" /etc/ssh/sshd_config >/dev/null
if [ $? -ne 0 ]; then
    echo "ListenAddress $ipaddr" >> /etc/ssh/sshd_config
    set -u
    /etc/init.d/sshd restart
fi

exit 0


