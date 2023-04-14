yum -y install nfs-utils rpcbind
[ ! -d /nfs_root ] && mkdir /nfs_root
echo "/nfs_root *(rw,sync,no_root_squash)" >/etc/exports
systemctl restart nfslock.service
systemctl restart rpcbind.service
systemctl restart nfs.service
systemctl status nfs.service
sudo iptables -I INPUT -p tcp -m tcp --dport 2049 -j ACCEPT
sudo iptables -I INPUT -p tcp -m tcp --dport 111 -j ACCEPT
systemctl enable /usr/lib/systemd/system/nfs-server.service
chkconfig rpcbind on