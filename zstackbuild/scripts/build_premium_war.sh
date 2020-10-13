#!/bin/bash
cd $1
chmod +x OEMNeutral.sh
./OEMNeutral.sh
./runMavenProfile premium
./runMavenProfile deploydb
