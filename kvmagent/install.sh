#!/bin/sh
root_dir=`dirname $0`
cd $root_dir
rm -rf build dist kvmagent.egg-info

python setup.py sdist
pip uninstall -y kvmagent
pip install  dist/*.tar.gz --force-reinstall
