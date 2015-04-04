#!/bin/bash
#clean up old logs to save disk space. This should be put in cronjob
max_line=100000
for file in `find /var/log/ -name '*.log'`; do
    lines=`wc -l $file|awk '{print $1}'`
    if [ $lines -gt $max_line ]; then
        echo $file $lines
        need_removed_lines=`expr $lines - $max_line + 10000`
        sed -i "1,${need_removed_lines}d" $file
        sleep 0.1
    fi
done
