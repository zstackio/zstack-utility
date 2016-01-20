#!/bin/bash
cd $1
mvn -DskipTests clean install
