#!/bin/bash
cd $1
cd premium
chmod +x OEMNeutral.sh
./OEMNeutral.sh
cd ..
./runMavenProfile premium
./runMavenProfile deploydb
