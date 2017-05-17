#!/bin/bash
cd $1
cd mevoco-ui-server
export PATH=$PATH:`pwd`/grails/bin/
sh ./gradlew
sed -i '/^UI_PATH=/s/UI_PATH=.*$/UI_PATH=..\/mevoco-ui2/g' build.sh
sed -i '/^UI_SERVER_PATH=/s/UI_SERVER_PATH=.*$/UI_SERVER_PATH=..\/mevoco-ui-server/g' build.sh
sh build.sh
