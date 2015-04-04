#!/bin/sh
root_dir=`dirname $0`
cd $root_dir
rm -rf build dist zstacklib.egg-info

python setup.py sdist
pip uninstall -y zstacklib
pip install  dist/*.tar.gz
# If you have own pypi server, please use following line.
#pip install  dist/*.tar.gz -i http://10.0.101.1/pypi/
