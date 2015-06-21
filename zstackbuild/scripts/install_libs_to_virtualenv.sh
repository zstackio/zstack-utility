#!/bin/bash
DEFAULT_PYPI='https://pypi.python.org/simple/'
ZSTACK_PYPI_URL=${ZSTACK_PYPI_URL-$DEFAULT_PYPI}
virtual_env_path=$1
lib_name=$2
. $virtual_env_path/bin/activate 
pip install -i $ZSTACK_PYPI_URL $lib_name || (deactivate && exit 1)
deactivate
