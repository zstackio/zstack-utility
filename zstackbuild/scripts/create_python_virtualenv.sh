#!/bin/bash
virtual_env_path=$1
if [ -d $virtual_env_path ]; then
    rm -rf $virtual_env_path
fi
shift
virtualenv $virtual_env_path $*
