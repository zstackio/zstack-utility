#!/bin/bash
set -x
cd $1
versionfile="zsha2"
if [ ! -f ${versionfile} ];then
	touch ${versionfile}
fi

echo "$2" > ${versionfile}
