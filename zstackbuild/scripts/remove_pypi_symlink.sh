#!/bin/bash
for item in `find $1`; do
    if [ -L $item ]; then
        echo "Remove symbolic for $item"
        cd `dirname $item`
        base_file=`readlink $item`
        cp --remove-destination `readlink $item` $item
        rm -f $base_file
    fi
done
