yum install targetcli  lvm2 lvm2-lockd sanlock -y

device1=`lsblk -o NAME -d|grep -v sda|grep -v NAME|awk 'NR==1'`
device2=`lsblk -o NAME -d|grep -v sda|grep -v NAME|awk 'NR==2'`

sed -i "s/sdb/$device1/g" ./twolunssaveconfig.json
sed -i "s/sdc/$device2/g" ./twolunssaveconfig.json

targetctl restore ./twolunssaveconfig.json
mkdir -p /etc/sanlock/
touch /etc/sanlock/sanlock.conf