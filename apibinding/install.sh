#!/bin/sh
root_dir=`dirname $0`
cd $root_dir
rm -rf build dist apibinding.egg-info

python setup.py sdist
pip uninstall -y apibinding
pip install --upgrade dist/*.tar.gz
