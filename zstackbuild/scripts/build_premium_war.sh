#!/bin/bash
cd $1
chmod +x OEMNeutral.sh
./OEMNeutral.sh > /dev/null
sync
./runMavenProfile premium
./runMavenProfile deploydb
