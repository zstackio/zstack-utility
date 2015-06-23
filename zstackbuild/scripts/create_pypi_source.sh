#!/bin/bash
# Create pip source by https://github.com/wolever/pip2pi

DEFAULT_PYPI='https://pypi.python.org/simple/'
ZSTACK_PYPI_URL=${ZSTACK_PYPI_URL-$DEFAULT_PYPI}

pypi_local_folder=$1
requirement_file=$2

which pip2pi >/dev/null 2>&1 || pip install -i ${ZSTACK_PYPI_URL} pip2pi

pip2pi $pypi_local_folder --index-url ${ZSTACK_PYPI_URL} -r $requirement_file --normalize-package-names --no-use-wheel
