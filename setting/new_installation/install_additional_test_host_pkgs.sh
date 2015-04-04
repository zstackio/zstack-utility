rpm --import /etc/pki/rpm-gpg/*

yum install -y vim
yum groupinstall -y "Gnome Desktop"
yum install -y tigervnc-server
yum install -y pyparsing python-CherryPy python-simplejson python-routes python-paramiko python-pip

export http_proxy=proxy02.pd.intel.com:911
rpm -ivh http://yum.puppetlabs.com/fedora/f18/products/i386/puppetlabs-release-18-7.noarch.rpm
yum install -y puppet

yum install -y rabbitmq-server

yum install -y mysql mysql-server
systemctl enable mysqld.service
systemctl start mysqld.service

yum install -y ant maven

cat > /root/.m2/settings.xml <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<settings>
 <proxies>
  <proxy>
    <active>true</active>
    <protocol>http</protocol>
    <host>proxy02.pd.intel.com</host>
    <port>911</port>
  </proxy>
 </proxies>
</settings>
EOF

yum install -y qemu-system-x86 libvirt-daemon-kvm
yum install -y ntp

ln -s /root /home/root
mkdir /home/sftpBackupStorage
