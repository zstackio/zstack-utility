#!/bin/sh

root_dir=`dirname $0`
cd $root_dir
rm -rf build dist sftpbackupstorage.egg-info

python setup.py sdist
pip uninstall -y sftpbackupstroage
pip install  dist/*.tar.gz
