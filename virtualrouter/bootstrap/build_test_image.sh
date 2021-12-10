#!/bin/sh
#set -e
#set -x
#currently we only support CentOS 6.5 and Debian 7

DEBIAN='Debian'
CENTOS='CentOS'
UBUNTU='Ubuntu'
VERSION='6'
WORKSPACE=/root/build_zstack_test_image

MNT=`mktemp`
rm -f $MNT
mkdir -p $MNT

IMG_NAME=${WORKSPACE}/zstack-test-`date +%Y%m%d`.img
#IMG_SIZE=2500 #2500MB #for general test
#FS_BLOCK=511744 #2500MB - 1MB; 1block = 4k. #for general test
SWAP_SIZE=512000 #500*1024 = 500MB, swap block = 1k
IMG_SIZE=3500 #3500MB #for zstack installation test #3.5G image with 500M swap
FS_BLOCK=767744 #(3500 - 500 - 1)* 1024 / 4; 1block = 4k. #for general test

#IMG_SIZE=4000 #4000MB #for zstack installation test #4G image with 500M swap
#FS_BLOCK=895744 #3500MB - 1MB; 1block = 4k. #4G image with 500M swap

#IMG_SIZE=1300 #1.3G #smaller image for general test
#FS_BLOCK=332544 #1.3G-1M #smaller image for general test
OFFSET=1048576 #1M
#OFFSET2=2097151999 #2G-1
#OFFSET3=2097152000 #2G
OFFSET2=3145727999  #3500M -500M - 1 #filesystem offset
OFFSET3=3145728000  #3500M -500M

#OFFSET2=3670015999 #3500M - 1 #4G image with 500M swap
#OFFSET3=3670016000 #3500M  #4G image with 500M swap

#
#IMG_SIZE=2000 #2G
#FS_BLOCK=511744 #2G-1M 1block = 4k
##IMG_SIZE=1300 #1.3G
##FS_BLOCK=332544 #1.3G-1M
#OFFSET=1048576 #1M

umount_all() {
    umount $MNT/sys &>/dev/null || echo ''
    umount $MNT/dev &>/dev/null || echo ''
    umount $MNT/proc &>/dev/null  || echo ''
    umount $MNT &>/dev/null || echo ''
}

release_loop_devices() {
    [ -z $loopdev2 ] || losetup -d $loopdev2
    sync;sync;sync
    [ -z $loopdev1 ] || losetup -d $loopdev1
}

err_exit() {
    echo -e "\n\nERROR: $@"
    echo_bold "exit 1"
    exit 1
}

cleanup(){
    umount_all
    release_loop_devices
}

cleanup_redhat(){
    echo 'cleanup'
}

cleanup_debian(){
    echo 'cleanup'
}

call_exception(){
    cleanup
    rm -rf $MNT
    err_exit $*
}

echo_star() {
    echo_bold "*******************************************************************"
}

echo_blank_lines(){
    echo -e "\n\n"
}

cancel() {
	call_exception "User Interrupt by 'CTRL-C'"
}

trap cancel INT

in_chroot() {
    chroot $MNT $* || call_exception "ERROR: $@"
}

echo_bold(){
    echo -e "$(tput bold) - $1 \n$(tput sgr0)"
}

check_system() {
    echo_blank_lines
    echo_star
    echo_bold "Check System Environment ..."
    echo_star
    whoami | grep root > /dev/null
    [ $? -eq 1 ] && err_exit "The script must be run by root. "
    #CentOS 7 changed /etc/issue display. Will use redhat-release for redhat OS
    if [ -f /etc/redhat-release ]; then
        OS=`cat /etc/redhat-release|head -n1|awk '{print $1}'`
        grep " 6\." /etc/redhat-release >/dev/null && CENTOS_VERSION=6
        grep " 7\." /etc/redhat-release >/dev/null && CENTOS_VERSION=7
    else
        OS=`cat /etc/issue|head -n1|awk '{print $1}'`
    fi

    [ "$OS" != $CENTOS ] || [ "$OS" != $DEBIAN ] || [ "$OS" != $UBUNTU ]call_exception "Script required to be run on Debian or Centos OS. Current get: $OS"

    [ "$OS" == $CENTOS ] && check_centos_system
    [ "$OS" == $DEBIAN ] && check_debian_system
}

check_centos_system() {
    check_cmd yum
}

check_debian_system() {
    check_cmd debootstrap
}

check_cmd(){
    which $1|| err_exit "Not find tool: $1"
}

#####################################
# Create a bootable image           #
#####################################
create_base_image() {
    echo_blank_lines
    echo_star
    echo_bold "Create Base Image: ${IMG_NAME}. Size: ${IMG_SIZE}MB"
    echo_star
    check_cmd 'parted'
    check_cmd 'mkfs.ext4'
    check_cmd 'tune2fs'

    dd if=/dev/zero of=$IMG_NAME bs=1M seek=$IMG_SIZE count=1 || err_exit "Create image error. "
    loopdev1=`losetup -f`
    losetup $loopdev1 $IMG_NAME
    parted $loopdev1 -s 'mklabel msdos'
    parted $loopdev1 -s "mkpart primary ext4 ${OFFSET}B ${OFFSET2}B"
    parted $loopdev1 -s "mkpart primary linux-swap ${OFFSET3}B -1"
    parted $loopdev1 -s 'set 1 boot on'
    sync

    loopdev2=`losetup --show -o $OFFSET -f $loopdev1`
    # trick: If we don't specify block count 1023744, the filesystem size reported by partition table was 1M greater than size reported by super block,
    # this make system fail to boot. I suspect 'losetup -o' in just above line doesn't work as expected. However, explictly specifying block count makes
    # two size match
    mkfs.ext4 -L ROOT -b 4096 $loopdev2 $FS_BLOCK
    tune2fs -c 0 -i 0 $loopdev2 >/dev/null
    loopdev3=`losetup --show -o $OFFSET3 -f $loopdev1`
    mkswap -L SWAP $loopdev3 $SWAP_SIZE
    losetup -d $loopdev3
    sync
}

#####################################
# install system and configure      #
#####################################
install_system() {
    echo_blank_lines
    echo_star
    echo_bold "Install OS System into image and install GRUB."
    echo_star
    mount $loopdev2 $MNT
    [ $OS = $CENTOS ] && install_centos
    [ $OS = $DEBIAN ] && install_debian
    [ $OS = $UBUNTU ] && install_ubuntu
}

install_ubuntu(){
    #debootstrap --include=less,vim,sudo,openssh-server,acpid,python-virtualenv,netcat,telnet,dnsmasq,dnsmasq-base,dnsmasq-utils,python-setuptools,gcc,autoconf,curl,gfortran,python-pip,python-simplejson,python-cherrypy,python-routes,python-paramiko,python-pyparsing,python-dev,python-apt,tcpdump,iputils-arping,iptables $UBUNTU_OPTS $UBUNTU_RELEASE $MNT $UBUNTU_REPO || call_exception "cannot install $UBUNTU_RELEASE into $IMG_NAME"
    debootstrap --include=less,sudo,openssh-server,acpid,python-virtualenv,netcat,telnet,python-setuptools,gcc,autoconf,curl,gfortran,python-pip,python-simplejson,python-cherrypy,python-routes,python-paramiko,python-pyparsing,python-dev,python-apt,tcpdump,iputils-arping,iptables $UBUNTU_OPTS $UBUNTU_RELEASE $MNT $UBUNTU_REPO || call_exception "cannot install $UBUNTU_RELEASE into $IMG_NAME"
    echo_bold "Finishing base system installation"
    cat <<EOF > $MNT/etc/fstab
LABEL=ROOT /                   ext4    errors=remount-ro 0       1
LABEL=SWAP none                swap    sw 0
EOF
    
    mount --bind /dev/ $MNT/dev || call_exception "Can't mount /dev"
    in_chroot mount -t proc none /proc || call_exception "Can't mount /proc"
    in_chroot mount -t sysfs none /sys || call_exception  "Can't mount /sys"
    export LANG=C DEBIAN_FRONTEND=noninteractive
    in_chroot apt-get install -y -q linux-image-generic grub-pc || call_exception "Fail to install Linux kernel and grub2"
    echo "grub-install --target=i386-pc --modules=\"biosdisk part_msdos\"  $loopdev1" >$MNT/tmp/grub-install.sh
    in_chroot /bin/sh /tmp/grub-install.sh  || call_exception "Fail to install grub2"
    /bin/rm -f $MNT/tmp/grub-install.sh
    echo 'GRUB_TERMINAL="console"' >> $MNT/etc/default/grub
    echo 'GRUB_GFXPAYLOAD_LINUX=text' >> $MNT/etc/default/grub
    echo 'GRUB_CMDLINE_LINUX_DEFAULT="console=tty0"' >> $MNT/etc/default/grub
    sed -i -e 's/\(^GRUB_CMDLINE_LINUX.*\)"$/\1 nofb nomodeset vga=normal"/'  $MNT/etc/default/grub
    sed -i 's/GRUB_TIMEOUT=5/GRUB_TIMEOUT=0/' $MNT/etc/default/grub
    echo 'GRUB_DISABLE_OS_PROBER=true' >>  $MNT/etc/default/grub
    echo "grub-mkconfig -o /boot/grub/grub.cfg" >$MNT/tmp/grub-install.sh
    in_chroot /bin/sh /tmp/grub-install.sh  || call_exception "Fail to make grub2 conf"
    /bin/rm -f $MNT/tmp/grub-install.sh

    sed -i '/set root=/d' $MNT/boot/grub/grub.cfg
    sed -i "s%$loopdev1%LABEL=ROOT%"  $MNT/boot/grub/grub.cfg
    sed -i "s/search --no-floppy --fs-uuid --set=root .*$/search --no-floppy --set=root --label ROOT/" $MNT/boot/grub/grub.cfg
    sed -i "s/root=UUID=[A-Za-z0-9\-]*/root=LABEL=ROOT/" $MNT/boot/grub/grub.cfg
    sed -i '/loop/d' $MNT/boot/grub/grub.cfg
    
    #sed -i "s|${IMG_NAME}p1|/dev/vda1|g" $MNT/boot/grub/grub.cfg
    in_chroot umount /sys
    in_chroot umount /proc
    umount $MNT/dev
    echo_bold "Finishing grub installation"
}

install_debian(){
    #debootstrap --include=less,vim,sudo,openssh-server,acpid,python-virtualenv,netcat,telnet,dnsmasq,dnsmasq-utils,python-setuptools,gcc,autoconf,curl,gfortran,python-pip,python-simplejson,python-cherrypy,python-routes,python-paramiko,python-pyparsing,python-dev,python-apt,acpi-support-base,tcpdump,iputils-arping,iptables $DEBOOTSTRAP_OPTS $DEBIAN_RELEASE $MNT $DEBIAN_REPO || call_exception "cannot install $DEBIAN_RELEASE into $IMG_NAME"
    debootstrap --include=less,sudo,openssh-server,acpid,python-virtualenv,netcat,telnet,python-setuptools,gcc,autoconf,curl,gfortran,python-pip,python-simplejson,python-cherrypy,python-routes,python-paramiko,python-pyparsing,python-dev,python-apt,acpi-support-base,tcpdump,iputils-arping,iptables $DEBOOTSTRAP_OPTS $DEBIAN_RELEASE $MNT $DEBIAN_REPO || call_exception "cannot install $DEBIAN_RELEASE into $IMG_NAME"
    
    echo_bold "Finishing base system installation"
    cat <<EOF > $MNT/etc/fstab
LABEL=ROOT /                   ext4    errors=remount-ro 0       1
LABEL=SWAP none                swap    sw 0
EOF
    
    mount --bind /dev/ $MNT/dev || call_exception "Can't mount /dev"
    in_chroot mount -t proc none /proc || call_exception "Can't mount /proc"
    in_chroot mount -t sysfs none /sys || call_exception  "Can't mount /sys"
    export LANG=C DEBIAN_FRONTEND=noninteractive
    if [ $OS = $DEBIAN ]; then
        in_chroot apt-get install -y -q linux-image-amd64 grub-pc || call_exception "Fail to install Linux kernel and grub2"
    else
        in_chroot apt-get install -y -q linux-image-generic grub-pc || call_exception "Fail to install Linux kernel and grub2"
    fi
    cat <<EOF > $MNT/boot/grub/device.map
(hd0) $loopdev1
(hd0,1) $loopdev2
EOF
    in_chroot grub-install $loopdev1 || call_exception "Fail to install grub2"
    sed -i 's/GRUB_TIMEOUT=5/GRUB_TIMEOUT=0/' $MNT/etc/default/grub
    in_chroot update-grub || call_exception "Fail to update grub"
    sed -i '/loop/d' $MNT/boot/grub/grub.cfg
    #sed -i "s|${IMG_NAME}p1|/dev/vda1|g" $MNT/boot/grub/grub.cfg
    in_chroot umount /sys
    in_chroot umount /proc
    umount $MNT/dev
    echo_bold "Finishing grub installation"
}

install_centos(){
    mkdir -p $MNT/{proc,etc,dev,var/{cache,log,lock/rpm}}
    mknod $MNT/dev/console c 5 1
    mknod $MNT/dev/null c 1 3
    mknod $MNT/dev/zero c 1 5
    mknod $MNT/dev/random c 1 8
    mknod $MNT/dev/urandom c 1 9
    mount -t proc none $MNT/proc

    cat > $MNT/etc/fstab <<EOF
LABEL=ROOT          /             ext4           defaults 1 1
LABEL=SWAP          swap          swap    defaults 1 1
none                              /proc     proc           defaults 0 0
none                              /sys       sysfs          defaults 0 0
EOF

    cp -a /etc/yum* ${MNT}/etc/
    mkdir ${MNT}/etc/pki
    cp -a /etc/pki/rpm-gpg/ ${MNT}/etc/pki
    yum --installroot=$MNT -y --releasever=$CENTOS_VERSION groupinstall Base || call_exception "Fail to install Base system."
    yum --installroot=$MNT -y --releasever=$CENTOS_VERSION install kernel || call_exception "Fail to install kernel."
    #yum --installroot=$MNT -y --releasever=$CENTOS_VERSION install vim-enhanced vim-minimal openssh-server openssh-clients dhclient curl ntp dnsmasq dnsmasq-utils python-setuptools gcc python-devel autoconf tcpdump iputils|| call_exception "Fail to install vim-minimal openssh-server dhclient curl ntp dnsmasq."
    yum --installroot=$MNT -y --releasever=$CENTOS_VERSION install net-tools openssh-server openssh-clients dhclient curl ntp python-setuptools gcc python-devel autoconf tcpdump iputils vim-minimal|| call_exception "Fail to install vim-minimal openssh-server dhclient curl ntp dnsmasq."
    yum --installroot=$MNT -y --releasever=$CENTOS_VERSION install telnet nc python-pip fio|| call_exception "Fail to install network tools. "
    #yum --installroot=$MNT -y upgrade dnsmasq-2.66-3.1.x86_64.rpm || call_exception "Fail to upgrade dnsmasq."
    #yum --installroot=$MNT -y install dnsmasq-2.68-1.x86_64.rpm || call_exception "Fail to upgrade dnsmasq."
    #yum --installroot=$MNT -y --releasever=$CENTOS_VERSION install salt-minion || call_exception "Fail to install salt-minion. "
    # For security group testing, install 2 network packages.
    #Fedora and CentOS 7 special requirement
    [ "$CENTOS_VERSION" = "7" ] && (yum --installroot=$MNT -y --releasever=$CENTOS_VERSION install yum iptables|| call_exception "Fail to install yum and iptables ")
    [ "$CENTOS_VERSION" = "7" ] && (yum --installroot=$MNT -y --releasever=$CENTOS_VERSION install yum iptables-services|| call_exception "Fail to install yum and iptables-services ")

    #set default hostname
    echo $HOSTNAME > $MNT/etc/hostname
    echo "127.0.0.1 $HOSTNAME" >> $MNT/etc/hosts

    if [ "$CENTOS_VERSION" = '6' ]; then
        install_rh_grub
    elif [ "$CENTOS_VERSION" = '7' ]; then
        install_rh_grub2
    else
        call_exception "Can't install grub or installation failed. Target OS Version is $CENTOS_VERSION"
    fi
    in_chroot umount /proc
}

install_rh_grub(){
    mkdir -p $MNT/boot/grub
    cp /boot/grub/{stage1,stage2} $MNT/boot/grub
    grub << EOF &&
device (hd0) $IMG_NAME
root (hd0,0)
setup (hd0)
quit
EOF

    kern=$(basename $(ls  $MNT/boot/vmlinuz-*))
    ver=${kern#vmlinuz-}
    cat > $MNT/boot/grub/menu.lst << EOF
default 0
timeout 0

title       CentOS/Linux, kernel $ver
root        (hd0,0)
kernel      /boot/$kern root=LABEL=ROOT ro
initrd      /boot/initramfs-$ver.img
EOF
    pushd $MNT/boot/grub
    ln -s menu.lst grub.conf
    popd
}

install_rh_grub2(){
    mount --bind /dev/ $MNT/dev || call_exception "Can't mount /dev"
    in_chroot mount -t sysfs none /sys || call_exception  "Can't mount /sys"

    yum --installroot=$MNT -y --releasever=$CENTOS_VERSION install grub2 || call_exception "Fail to install Linux kernel and grub2"
    [ ! -b ${loopdev1}p1 ] && in_chroot ln -s $loopdev1 ${loopdev1}p1
    #ramdisk needs to include virtio drivers, otherwise image booting will fail
    kernel_version=`ls $MNT/lib/modules/`
    kernel_version=`basename $kernel_version`
    cat << EOF > $MNT/tmp/grub2-install.sh
grub2-install --modules="biosdisk part_msdos" --target=i386-pc $loopdev1 
dracut --kver $kernel_version --add-drivers "virtio_blk virtio_pci" -f
EOF
    in_chroot sh /tmp/grub2-install.sh
    rm -f $MNT/tmp/grub2-install.sh
    cat <<EOF >$MNT/etc/default/grub
GRUB_CMDLINE_LINUX="nofb nomodeset rhgb quiet"
GRUB_GFXPAYLOAD_LINUX=text
GRUB_TERMINAL="serial console"
GRUB_TIMEOUT=0
GRUB_DISABLE_OS_PROBER=true
GRUB_CMDLINE_LINUX_DEFAULT="console=tty0 console=ttyS0,115200"
GRUB_SERIAL_COMMAND="serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1"
EOF
    in_chroot grub2-mkconfig -o /boot/grub2/grub.cfg
    rm -f ${loopdev1}p1
    in_chroot umount /sys
    umount $MNT/dev
    
    echo_bold "Finishing grub installation"
}

configure_system() {
    echo_blank_lines
    echo_star
    echo_bold "Config virtualrouter services."
    echo_star
    [ $OS = $CENTOS ] && config_centos
    [ $OS = $DEBIAN ] && config_debian
    [ $OS = $UBUNTU ] && config_debian
    [ $OS = $UBUNTU ] && sed -i 's/PermitRootLogin.*/PermitRootLogin yes/' $MNT/etc/ssh/sshd_config

    #set default password for root user.
    echo "root:password" | in_chroot chpasswd
    #in CentOS 7, if not add a none root user, the root user is not able to be logined. 
    in_chroot useradd zstack

    #enable ip forward
    grep 'net.ipv4.ip_forward' $MNT/etc/sysctl.conf >/dev/null
    if [ $? -eq 0 ]; then
        sed -i 's/.*net.ipv4.ip_forward.*/net.ipv4.ip_forward = 1/' $MNT/etc/sysctl.conf
    else
        echo "net.ipv4.ip_forward = 1" >> $MNT/etc/sysctl.conf
    fi
}

config_debian(){
    #if need set http_proxy for apt. need to enable following line
    #cat <<EOF > $MNT/etc/apt/apt.conf
#Acquire::http::Proxy "http://YOUR_PROXY:PORT";
#EOF
    echo $HOSTNAME > $MNT/etc/hostname

    cat <<EOF > $MNT/etc/hosts
127.0.0.1       localhost
127.0.1.1 		$HOSTNAME

# The following lines are desirable for IPv6 capable hosts
::1     localhost ip6-localhost ip6-loopback
ff02::1 ip6-allnodes
ff02::2 ip6-allrouters
EOF

    cat <<EOF > $MNT/etc/network/interfaces
auto lo
iface lo inet loopback
auto eth0
iface eth0 inet dhcp
EOF

    sed -i '/^exit/d' $MNT/etc/rc.local

    cat >> $MNT/etc/rc.local <<EOF
device_id="0 1 2 3 4 5 6 7 8 9"
available_devices=''
for i in $device_id;do
    ip addr show dev eth$i >/dev/null 2>&1
    if [ $? -eq 0 ];then
        available_devices="$available_devices eth$i"
    fi
done
dhclient $available_devices
exit 0 
EOF

    chmod a+x  $MNT/etc/rc.local

    cat > $MNT/etc/resolv.conf <<EOF
nameserver $DNS_SERVER
EOF

}

config_centos() {
    in_chroot chkconfig abrt-ccpp off
    in_chroot chkconfig abrt-oops off
    in_chroot chkconfig abrtd off
    #in_chroot chkconfig kdump off
    in_chroot chkconfig lvm2-monitor off
    in_chroot chkconfig ntpd on
    in_chroot chkconfig sshd on
    #in_chroot chkconfig ip6tables on
    #[ "$CENTOS_VERSION" = "7" ] && (in_chroot chkconfig firewalld off || echo "That's okay that there is not firewalld in centos7 service.")
    in_chroot chkconfig iptables on

    #disable selinux. following line is not working
    #in_chroot sed -i 's/SELINUX=enforcing/SELINUX=disabled/g' /etc/selinux/config

    #TODO: Need to add DNS resolv.conf
    cat > $MNT/etc/resolv.conf <<EOF
nameserver $DNS_SERVER
EOF

    cat > $MNT/etc/sysconfig/network <<EOF
NETWORKING=yes
HOSTNAME=$HOSTNAME
NOZEROCONF=yes
EOF

    config_rh_rc_local
}

config_rh_rc_local(){
    cat > $MNT/etc/sysconfig/network-scripts/ifcfg-eth0 <<EOF
ONBOOT=yes
DEVICE=eth0
BOOTPROTO=none
EOF

    cat > $MNT/etc/sysconfig/network-scripts/ifcfg-eth1 <<EOF
ONBOOT=yes
DEVICE=eth1
BOOTPROTO=none
EOF

    cat > $MNT/etc/sysconfig/network-scripts/ifcfg-eth2 <<EOF
ONBOOT=yes
DEVICE=eth2
BOOTPROTO=none
EOF

    cat > $MNT/etc/sysconfig/network-scripts/ifcfg-eth3 <<EOF
ONBOOT=yes
DEVICE=eth3
BOOTPROTO=none
EOF

    cat > $MNT/etc/sysconfig/network-scripts/ifcfg-eth4 <<EOF
ONBOOT=yes
DEVICE=eth4
BOOTPROTO=none
EOF

    cat > $MNT/etc/sysconfig/network-scripts/ifcfg-eth5 <<EOF
ONBOOT=yes
DEVICE=eth5
BOOTPROTO=none
EOF

    cat > $MNT/etc/sysconfig/network-scripts/ifcfg-eth6 <<EOF
ONBOOT=yes
DEVICE=eth6
BOOTPROTO=none
EOF

    cat > $MNT/etc/sysconfig/network-scripts/ifcfg-eth7 <<EOF
ONBOOT=yes
DEVICE=eth7
BOOTPROTO=none
EOF

    cat > $MNT/etc/sysconfig/network-scripts/ifcfg-eth8 <<EOF
ONBOOT=yes
DEVICE=eth8
BOOTPROTO=none
EOF

    cat > $MNT/etc/sysconfig/network-scripts/ifcfg-eth9 <<EOF
ONBOOT=yes
DEVICE=eth9
BOOTPROTO=none
EOF

    cat >> $MNT/etc/rc.d/rc.local <<EOF
device_id="0 1 2 3 4 5 6 7 8 9"
available_devices=''
for i in $device_id;do
    ip addr show dev eth$i >/dev/null 2>&1
    if [ $? -eq 0 ];then
        available_devices="$available_devices eth$i"
    fi
done
dhclient $available_devices
EOF
    chmod a+x $MNT/etc/rc.d/rc.local

    if [ "$CENTOS_VERSION" = "7" ]; then
        cat <<EOF >> $MNT/usr/lib/systemd/system/rc-local.service

[Install]
WantedBy=multi-user.target
EOF
        in_chroot chkconfig rc-local on
    fi
}

#install zstack required python libs.
post_install(){
    echo_blank_lines
    echo_star
    echo_bold "Post Intallation -- install zstack required python libs."
    echo_star
    [ $OS = $CENTOS ] && post_install_centos
    [ $OS = $DEBIAN ] && post_install_debian
}

post_install_debian(){
    mount --bind /dev $MNT/dev
    chroot $MNT easy_install pickledb websockify
    umount $MNT/dev
}

post_install_centos() {
    mount --bind /dev $MNT/dev
    echo "easy_install --index-url=\"$pypi_url\" pip simplejson CherryPy routes paramiko \"pyparsing<=1.5.7\" pickledb websockify virtualenv " > $MNT/tmp/install_py.sh
    in_chroot sh /tmp/install_py.sh
    in_chroot sh /tmp/install_py.sh
    rm -f $MNT/tmp/install_py.sh
    in_chroot mkdir -p /var/lib/zstack/virtualenv/virtualrouter
    in_chroot virtualenv /var/lib/zstack/virtualenv/virtualrouter
    umount $MNT/dev
}

help(){
    echo "Usage:
    $0 [OPTIONS]

Options:
 [-d] DNS_SERVER_IP_Address
        Default is 8.8.8.8. It will be set to /etc/reslov.conf
 [-q]   If setting -q, it will generate qcow2 image. If not, it will generate 
        raw image. 
"
    exit 0
}

DNS_SERVER="8.8.8.8"
DEBOOTSTRAP_OPTS=""
DEBIAN_REPO="http://mirrors.163.com/debian"
DEBIAN_RELEASE='wheezy'
UBUNTU_OPTS="--components=main,universe"
UBUNTU_REPO="http://mirrors.163.com/ubuntu"
UBUNTU_RELEASE='trusty'
#CENTOS_VERSION="6.5"
CENTOS_VERSION="7"
HOSTNAME='zstack-test-image'
QCOW='No'

OPTIND=1
while getopts "d:p:qh" Option
do
    case $Option in
        d ) DNS_SERVER=$OPTARG ;;
        p ) pypi_url=$OPTARG ;;
        q ) QCOW='Yes' ;;
        h ) help;;
        * ) help;;
    esac
done

pypi_url=${pypi_url-'https://pypi.python.org/simple/'}

OPTIND=1
check_system

rm -rf $IMG_NAME
mkdir -p $WORKSPACE 

create_base_image
install_system
configure_system
#post_install
/bin/cp -f `dirname $0`/cleanup_old_logs.sh $MNT/etc/cron.hourly/
cleanup

if [ $QCOW = 'Yes' ]; then
    qemu-img convert -c -f raw -O qcow2 $IMG_NAME ${IMG_NAME}.qcow2
fi

echo_blank_lines
echo_star
if [ $QCOW = 'Yes' ]; then
    echo_bold "Successfully creating image: ${IMG_NAME}.qcow2"
else
    echo_bold "Successfully creating image: $IMG_NAME"
fi
echo_star
echo_blank_lines
