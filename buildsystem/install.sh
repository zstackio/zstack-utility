#!/bin/sh

python setup.py bdist_egg
easy_install dist/buildsystem*.egg
