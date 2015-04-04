#!/bin/sh

python setup.py bdist_egg
easy_install dist/*.egg
cp -f zstack-setting /usr/bin/zstack-setting
