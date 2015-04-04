sysctl -w net.ipv4.ip_forward=1

iptables -A FORWARD -i eth1 -j ACCEPT
iptables -A FORWARD -o eth1 -j ACCEPT
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE


iptables -t nat -A PREROUTING -p tcp --dport=5905 -j DNAT -i eth0 --to-destination 10.0.101.10:5901
iptables -t nat -A PREROUTING -p tcp --dport=5906 -j DNAT -i eth0 --to-destination 10.0.101.11:5901
iptables -t nat -A PREROUTING -p tcp --dport=5907 -j DNAT -i eth0 --to-destination 10.0.101.12:5901
iptables -t nat -A PREROUTING -p tcp --dport=5908 -j DNAT -i eth0 --to-destination 10.0.101.13:5901
