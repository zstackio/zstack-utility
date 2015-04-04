#!/bin/bash
# This script should be same with zstack-utility/virtualrouter/bootstrap
#set -x
ZSTACK_LIB_DIR='/var/lib/zstack'
TA_VIRTUALEVN_ROOT=$ZSTACK_LIB_DIR/virtualenv/testagent
ZSTACK_PYPI_URL=${ZSTACK_PYPI_URL-'https://pypi.python.org/simple/'}

echo_bold(){
    echo -e "$(tput bold) - $1 \n$(tput sgr0)"
}

echo $0 $*

help(){
    echo "Usage: 
        $0 [Options]

        Update VR VR_IMAGE_PATH with providing packages.

Options:
    -A ANSIBLE_DIR
                [Required] The target ansible folder with all latest service
                packages. After building zstack-utility, it should be in 
                zstackbuild/target/zstack-assemble/WEB-INF/classes/ansible/
    -i VR_IMAGE_PATH
                [Required] The Virtual Router Image path. 
    -b BOOT_STRAP_SCRIPT
                [Optional] The new vr bootstrap script, which will be executed
                when vr system is booting.
    -t ZSTACK_TEST_AGENT_PATH
                [Optional] The new zstacktestagent.tgz
    -h          Show this message and exit.
"
    exit 1
}

VR_IMAGE_PATH=''
BOOT_STRAP_SCRIPT=''
ZSTACK_TEST_AGENT_PATH=''
ANSIBLE_DIR=''

OPTIND=1
while getopts "a:i:b:t:h" Option
do
    case $Option in
        a ) ANSIBLE_DIR=$OPTARG;;
        i ) VR_IMAGE_PATH=$OPTARG;;
        b ) BOOT_STRAP_SCRIPT=$OPTARG;;
        t ) ZSTACK_TEST_AGENT_PATH=$OPTARG;;
        h ) help;;
        * ) help;;
    esac
done
OPTIND=1

if [ -z $VR_IMAGE_PATH ];then
    help
fi

if [ ! -f $VR_IMAGE_PATH ];then
    echo_bold "Did not find vr image: $VR_IMAGE_PATH"
    exit
fi

if [ -z $ANSIBLE_DIR ] || [ ! -d $ANSIBLE_DIR ]; then 
    help
fi

echo_bold "begin to update $VR_IMAGE_PATH"

bootstrap_basename=`basename $2`
bootsect=`kpartx -l $VR_IMAGE_PATH |head -1| awk '{print $NF}'`
offset=`echo $bootsect*512|bc`
#For compatible for debian
MNT=`mktemp`
rm -rf $MNT
mkdir -p $MNT

NEW_ANSIBLE_DIR=`mktemp`
rm -f $NEW_ANSIBLE_DIR
mkdir -p $NEW_ANSIBLE_DIR/files

cleanup() {
    sync;sync;sync
    umount $MNT
    rm -f $ansible_inventory
    rm -rf $NEW_ANSIBLE_DIR
    mount|grep $VR_IMAGE_PATH
    if [ $? -eq 0 ]; then
        udisk_mount_folder=`mount|grep $VR_IMAGE_PATH|awk '{print $3}'`
        umount $udisk_mount_folder
    fi
    mount|grep $MNT
    if [ $? -eq 0 ]; then
        echo "umount $MNT failure. Please cleanup $MNT manualy!!"
        exit 1
    fi
    rm -rf $MNT
}

exception() {
    echo $*
    cleanup
    exit 1
}

cancel() {
        exception "User Interrupt by 'CTRL-C'"
}
trap cancel INT

enable_service() {
    chroot $MNT which chkconfig
    if [ $? -eq 0 ]; then
        chroot $MNT /bin/env PATH=$PATH:/bin:/sbin:/usr/bin:/usr/sbin chkconfig $1 on || exception "Fail to enable $1 service by chkconfig"
    else
        chroot $MNT which update-rc.d
        if [ $? -eq 0 ]; then
            LANG=C chroot $MNT update-rc.d $1 defaults || exception "Fail to enable $1 service by update-rc.d"
        else
            exception "Fail to enable $1 service, since not find chkconfig or update-rc.d"
        fi
    fi
}

mount -ooffset=$offset $VR_IMAGE_PATH $MNT||exception "Fail to mount $VR_IMAGE_PATH to $MNT"
if [ ! -z $BOOT_STRAP_SCRIPT ]; then
    /bin/cp -f $BOOT_STRAP_SCRIPT $MNT/sbin/
    
    #old_script=`grep python $MNT/etc/rc.local|awk '{print $NF}'`
    #sed -i '/python/d' $MNT/etc/rc.local
    #echo "python /sbin/$bootstrap_basename" >> $MNT/etc/rc.local
fi

ansible_inventory=`mktemp`
cat > $ansible_inventory << EOF
[chroot]
$MNT ansible_connection=chroot
EOF

cp -a $ANSIBLE_DIR/* $NEW_ANSIBLE_DIR/files

cd $NEW_ANSIBLE_DIR
find . -name *.yaml -exec ln -s {} \;

echo_bold "Update Virtual Router ..."
ansible-playbook virtualrouter.yaml -i $ansible_inventory -e "gather_facts=No zstack_root=/var/lib/zstack/ pkg_virtualrouter=virtualrouter-0.6.tar.gz pypi_url=$ZSTACK_PYPI_URL pkg_zstacklib=zstacklib-0.6.tar.gz host=chroot chroot=true" || exception "Update Virtual Router Failed"

echo_bold "Update Virtual Router Successfully"

echo_bold "Update Appliance VM service..."
ansible-playbook appliancevm.yaml -i $ansible_inventory -e "zstack_root=/var/lib/zstack/ pkg_appliancevm=appliancevm-0.6.tar.gz pypi_url=$ZSTACK_PYPI_URL pkg_zstacklib=zstacklib-0.6.tar.gz host=chroot chroot=true" || exception "Update Appliance VM Failed"
echo_bold "Update Appliance VM Successfully"

#if [ ! -z $ZSTACK_TEST_AGENT_PATH ]; then
#    echo_bold "Begin to install zstacktestagent"
#    cat > $MNT/tmp/install_testagent.sh <<EOF
#export PATH=$PATH:/bin:/sbin:/usr/bin:/usr/sbin
#[ -f TA_VIRTUALEVN_ROOT/bin/activate ] || virtualenv $TA_VIRTUALEVN_ROOT
#. $TA_VIRTUALEVN_ROOT/bin/activate
#pip install --ignore-installed -i $ZSTACK_PYPI_URL $ZSTACK_LIB_DIR/zstacktestagent/zstacktestagent*.gz
#EOF
#    mkdir -p $MNT/var/lib/zstack/zstacktestagent
#    /bin/cp -f $ZSTACK_TEST_AGENT_PATH $MNT/var/lib/zstack/zstacktestagent/
#    chroot $MNT /bin/sh /tmp/install_testagent.sh || exception "Fail to install testagent."
#fi

cleanup
qcow_img_name=`basename $VR_IMAGE_PATH|awk -F'.' '{print $1}'`.qcow2
qcow_img=`dirname $VR_IMAGE_PATH`/$qcow_img_name
/bin/rm -f $qcow_img
echo_bold "Begin to create qcow2 file: $qcow_img, needs some minutes..."
qemu-img convert -c -f raw -O qcow2 $VR_IMAGE_PATH $qcow_img
echo_bold "$VR_IMAGE_PATH has been updated. New qcow2 image: $qcow_img is created."

