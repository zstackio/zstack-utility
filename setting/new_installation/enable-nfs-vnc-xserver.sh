systemctl start rpcbind.service 
systemctl start nfs-server.service 
systemctl start nfs-lock.service 
systemctl start nfs-idmap.service 
systemctl enable rpcbind.service 
systemctl enable nfs-server.service 
systemctl enable nfs-lock.service 
systemctl enable nfs-idmap.service

mkdir /home/nfs
echo /home/nfs *(rw,sync,no_root_squash) > /etc/exports
exportfs -a

#cp /lib/systemd/system/vncserver@.service /etc/systemd/system/vncserver@:1.service
#sed -i "s/<USER>/root/g" /etc/systemd/system/vncserver@:1.service
#systemctl daemon-reload
#systemctl enable vncserver@:1.service
#systemctl start vncserver@:1.service
