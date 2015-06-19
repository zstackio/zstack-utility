#!/bin/bash
sed -i "s#^VIRTUAL_ENV=.*#VIRTUAL_ENV=/var/lib/zstack/virtualenv/`basename $1`#" $1/bin/activate
