#!/bin/sh

root_dir=`dirname $0`
cd $root_dir
rm -rf build dist virtualrouter.egg-info
python setup.py sdist
pip uninstall -y virtualrouter
pip install  dist/*.tar.gz
