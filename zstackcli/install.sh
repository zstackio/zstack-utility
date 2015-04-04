#!/bin/sh
root_dir=`dirname $0`
cd $root_dir
rm -rf build dist zstackcli.egg-info

which virtualenv &>/dev/null
[ $? -ne 0 ] && echo "Need to install virtualenv before install zstack-cli." && exit 1
VIRTUAL_ENV=/var/lib/zstack/virtualenv/zstackcli
[ ! -d $VIRTUAL_ENV ] && virtualenv $VIRTUAL_ENV
source $VIRTUAL_ENV/bin/activate

[ -d ../apibinding ] && ../apibinding/install.sh
[ -d ../zstacklib ] && ../zstacklib/install.sh

python setup.py sdist
pip install --ignore-installed dist/*.tar.gz
# If you have own pypi server, please use followin line.
#pip install --ignore-installed dist/*.tar.gz -i http://10.0.101.1/pypi/simple
