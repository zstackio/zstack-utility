#!/bin/bash

#download
curl http://169.254.169.254/zwatch-vm-agent.bin --silent -O

chmod +x zwatch-vm-agent.bin
./zwatch-vm-agent.bin -id i

#start
service zwatch-vm-agent start

echo zwatch-vm-agent installed and runing