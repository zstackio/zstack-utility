#!/bin/bash
cd $1
./runMavenProfile premium
./runMavenProfile deploydb
