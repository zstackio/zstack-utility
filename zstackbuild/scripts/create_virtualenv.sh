#!/bin/bash
# Create virtualenv folder

DEFAULT_PYPI='https://pypi.python.org/simple/'
ZSTACK_PYPI_URL=${ZSTACK_PYPI_URL-$DEFAULT_PYPI}

virtualenv_path=$1
shift

which virtualenv >/dev/null 2>&1 || pip install -i ${ZSTACK_PYPI_URL} virtualenv==12.1.1

virtualenv $virtualenv_path

$virtualenv_path/bin/pip install -i ${ZSTACK_PYPI_URL} $*
