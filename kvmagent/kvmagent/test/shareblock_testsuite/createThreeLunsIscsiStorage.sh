yum install targetcli  lvm2 lvm2-lockd sanlock -y

device1=`lsblk -o NAME -d|grep -v 'sda|vda'|grep -v NAME|awk 'NR==1'`
device2=`lsblk -o NAME -d|grep -v 'sda|vda'|grep -v NAME|awk 'NR==2'`
device3=`lsblk -o NAME -d|grep -v 'sda|vda'|grep -v NAME|awk 'NR==3'`

sed -i "s/sdb/$device1/g" ./saveconfig.json
sed -i "s/sdc/$device2/g" ./saveconfig.json
sed -i "s/sdd/$device3/g" ./saveconfig.json

targetctl restore ./saveconfig.json
mkdir -p /etc/sanlock/
touch /etc/sanlock/sanlock.conf
