#!/bin/sh

rm -rf $CATALINA_HOME/webapps/zstack*
cp build/zstack.war $CATALINA_HOME/webapps/
