#!/bin/sh

root_dir=`dirname $0`
cd $root_dir
rm -rf build dist appliancevm.egg-info
python setup.py sdist
pip uninstall -y appliancevm
pip install  dist/*.tar.gz
