#/bin/bash

LOGFILE="/var/log/gateway_check.log"

expected_gateway=$1
vmInstanceUuid=`curl -s http://169.254.169.254/2009-04-04/meta-data/instance-id`
echo "vmInstanceUuid: $vmInstanceUuid"
echo "vmInstanceUuid: $vmInstanceUuid" >> $LOGFILE

check_gateway() {
    gateway=`ip route | grep default | awk '{print $3}'`
    if [ $expected_gateway = $gateway ];
    then
        echo $(date) "current gateway is $gateway"
        echo $(date) "current gateway is $gateway" >> $LOGFILE
        return
    fi

    #push message to MN
    echo $(date) "gateway is changed to $gateway"
    echo $(date) "gateway is changed to $gateway" >> $LOGFILE

    curl -H "Content-Type: application/json" -X POST -d "{\"vmInstanceUuid\": \"${vmInstanceUuid}\", \"expectedGateway\": \"${expected_gateway}\", \"gateway\": \"${gateway}\", \"repair\": \"False\"}" http://169.254.169.254/host/kvm/VmGatewayChanged
    #wait curl finish
    sleep 5

    #fix gateway
    for g in $gateway;
    do
        echo "delete wrong gateway $g"
        echo "delete wrong gateway $g" >> $LOGFILE
        ip route delete default via $g
    done

    ip route add default via $expected_gateway
    gateway=`ip route | grep default | awk '{print $3}'`

    echo "new gateway $gateway"
    echo "new gateway $gateway" >> $LOGFILE
    curl  -H "Content-Type: application/json" -X POST -d "{\"vmInstanceUuid\": \"${vmInstanceUuid}\", \"expectedGateway\": \"${expected_gateway}\", \"gateway\": \"${gateway}\", \"repair\": \"True\"}" http://169.254.169.254/host/kvm/VmGatewayChanged

    #wait curl finish
    sleep 5
}

for (( ; ; ))
do
    check_gateway
    sleep 30
done
