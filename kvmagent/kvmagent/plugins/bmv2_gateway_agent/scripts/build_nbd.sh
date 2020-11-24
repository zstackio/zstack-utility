#! /bin/bash

# check nbd.ko exist
# exit if the mod load
lsmod | grep nbd && exit 0
# if not load, check the mod exist and try to load it.
if [[ `find /lib/modules/$(uname -r) -type f -name 'nbd.ko' | wc -l ` -gt 0 ]]; then
    modprobe nbd
    if [[ $? -lt 0 ]]; then
        modprobe -r nbd && exit 0
    fi
    # failed to load, remove the mod and build it again
    # rm -rf `find /usr/modules$(uname -r) -type f -name 'nbd.ko'`
    # depmod -a
fi

# build

currkernel=/usr/src/kernels/$(uname -r)

tempdir=`mktemp -d`
kernel=`uname -r | awk -F '.x86_64' '{ print $1}'`
yumdownloader --disablerepo=* --enablerepo=zstack-mn --archlist src --destdir=$tempdir kernel-$kernel
rpm -ivh -r $tempdir $tempdir/kernel-$kernel*
cd $tempdir/root/rpmbuild/SOURCES
tar Jxf ./linux-$kernel* && cd ./linux-$kernel
make mrproper
cp $currkernel/Module.symvers ./
cp /boot/config-$(uname -r) ./.config
make oldconfig
make prepare
make scripts
sed -i 's/REQ_TYPE_SPECIAL/REQ_TYPE_DRV_PRIV/' drivers/block/nbd.c
make CONFIG_STACK_VALIDATION= CONFIG_BLK_DEV_NBD=m M=drivers/block
cp drivers/block/nbd.ko /lib/modules/$(uname -r)/kernel/drivers/block/
depmod -a

echo 'options nbd max_part=16 nbds_max=64' > /etc/modprobe.d/nbd.conf

modprobe nbd

echo 'nbd' > /etc/modules-load.d/nbd.conf

rm -rf $tempdir
