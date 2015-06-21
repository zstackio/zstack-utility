#!/bin/bash
chroot_env=$1
virtual_env_path=$2
if [ -d $chroot_env/$virtual_env_path ]; then
    rm -rf $chroot_env/$virtual_env_path
fi
shift
shift
chroot $chroot_env /bin/virtualenv $virtual_env_path $*
