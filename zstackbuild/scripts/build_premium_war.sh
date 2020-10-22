#!/bin/bash
cd $1
chmod +x OEMNeutral.sh
bash -xe OEMNeutral.sh > a || sleep 36000
./runMavenProfile premium
./runMavenProfile deploydb
