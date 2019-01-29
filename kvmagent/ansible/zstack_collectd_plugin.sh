#!/bin/bash

OSTNAME="${COLLECTD_HOSTNAME:-`hostname -f`}"
INTERVAL="${COLLECTD_INTERVAL:-10}"

submit_counters() {
    #get all interface
    eths=$(ls /sys/class/net)

    all_in_octets=0
    all_in_packets=0
    all_in_errors=0
    all_out_octets=0
    all_out_packets=0
    all_out_errors=0

    for eth in $eths:
    do
        if [[ $eth == "lo" ]]
        then
            continue
        fi

        if [[ $eth == "bonding_masters" ]]
        then
            continue
        fi

        if [[ $eth =~ ^(vnic).* ]]
        then
            continue
        fi

        if [[ $eth =~ ^(outer).* ]]
        then
            continue
        fi

        if [[ $eth =~ ^(br_).* ]]
        then
            continue
        fi

        res=$(ip link show $eth | grep 'MULTICAST,SLAVE')
        if [[ $res != "" ]]
        then
            continue
        fi

        #skip vxlan interface
        if [[ $eth =~ ^(vxlan).* ]]
        then
            continue
        fi

        #skip vlan interface
        if [[ $eth =~ [[:alpha:][:alnum:]]*\.[[:digit:]]+ ]]
        then
            continue
        fi

        num=$(cat /sys/class/net/$eth/statistics/rx_bytes)
        all_in_octets=$(($all_in_octets + num))

        num=$(cat /sys/class/net/$eth/statistics/rx_packets)
        all_in_packets=$(($all_in_packets + num))

        num=$(cat /sys/class/net/$eth/statistics/rx_errors)
        all_in_errors=$(($all_in_errors + num))

        num=$(cat /sys/class/net/$eth/statistics/tx_bytes)
        all_out_octets=$(($all_out_octets + num))

        num=$(cat /sys/class/net/$eth/statistics/tx_packets)
        all_out_packets=$(($all_out_packets + num))

        num=$(cat /sys/class/net/$eth/statistics/tx_errors)
        all_out_errors=$(($all_out_errors + num))

    done

    echo "PUTVAL $HOSTNAME/interface-all/if_rx_octets interval=$INTERVAL N:$all_in_octets"
    echo "PUTVAL $HOSTNAME/interface-all/if_rx_packets interval=$INTERVAL N:$all_in_packets"
    echo "PUTVAL $HOSTNAME/interface-all/if_rx_errors interval=$INTERVAL N:$all_in_errors"
    echo "PUTVAL $HOSTNAME/interface-all/if_tx_octets interval=$INTERVAL N:$all_out_octets"
    echo "PUTVAL $HOSTNAME/interface-all/if_tx_packets interval=$INTERVAL N:$all_out_packets"
    echo "PUTVAL $HOSTNAME/interface-all/if_tx_errors interval=$INTERVAL N:$all_out_errors"

}

while sleep "$INTERVAL"
do
    submit_counters
done