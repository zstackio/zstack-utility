#!/bin/bash
DEFAULT_PYPI='https://pypi.python.org/simple/'
ZSTACK_PYPI_URL=${ZSTACK_PYPI_URL-$DEFAULT_PYPI}
chroot_env=$1
virtual_env_path=$2
lib_path=$3
lib_name=/zstack_libs/`basename $lib_path`
rm -f ${chroot_env}${lib_name}
mkdir ${chroot_env}/zstack_libs
cp $lib_path ${chroot_env}/${lib_name}
chroot $chroot_env $virtual_env_path/bin/pip install -i $ZSTACK_PYPI_URL ${lib_name}
