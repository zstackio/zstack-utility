yum install targetcli  lvm2 lvm2-lockd sanlock -y

deviceName=`lsblk -o NAME -d|grep -v sda|grep -v NAME|awk 'NR==1'`

sed -i "s/sdb/$deviceName/g" ./saveconfig.json

targetctl restore ./saveconfig.json
mkdir -p /etc/sanlock/
touch /etc/sanlock/sanlock.conf