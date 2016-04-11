#!/bin/bash
if [ "$(ps -ef | grep "haproxy-systemd-wrapper"| grep -v grep )" == "" ]
then
    service haproxy restart
    sleep 5
    if [ "$(ps -ef | grep "haproxy-systemd-wrapper"| grep -v grep )" == "" ]
        then
        pkill keepalived
    fi
fi