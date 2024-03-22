#!/usr/bin/env python
import argparse
import os
import subprocess
import sys
import socket

parser = argparse.ArgumentParser(description="Configure IPv6 on a ZStack host interface.")
parser.add_argument("-i", "--interface", required=True, help="Network interface to configure (e.g., eth0)")
parser.add_argument("ipv6_address", help="IPv6 address")
parser.add_argument("prefix_length", help="Prefix length (e.g., 64)")
parser.add_argument("-g", "--gateway", help="IPv6 gateway address", default="")
args = parser.parse_args()

config_file = "/etc/sysconfig/network-scripts/ifcfg-{}".format(args.interface)


def is_valid_ipv6_address(ipv6addr):
    try:
        socket.inet_pton(socket.AF_INET6, ipv6addr)
        return True
    except socket.error:
        return False


def is_valid_prefix_length(length):
    """Validate if the prefix length is valid (should be between 0 and 128)."""
    try:
        length = int(length)
        return 0 <= length <= 128
    except ValueError:
        return False


def run_command(command):
    try:
        result = subprocess.call(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result == 0:
            print("Command executed successfully: %s" % ' '.join(command))
        else:
            print("Command failed with return code %d: %s" % (result, ' '.join(command)))
    except subprocess.CalledProcessError as e:
        print("Error executing command: %s" % str(e))


# Validate IPv6 address
if not is_valid_ipv6_address(args.ipv6_address):
    print("Error: The provided IPv6 address is invalid.")
    sys.exit(1)

# Validate prefix length
if not is_valid_prefix_length(args.prefix_length):
    print("Error: The provided prefix length is invalid. It should be a number between 0 and 128.")
    sys.exit(1)

if args.gateway and not is_valid_ipv6_address(args.gateway):
    print("Error: The provided IPv6 gateway is invalid.")
    sys.exit(1)

with open(config_file, 'r') as file:
    lines = file.readlines()

with open(config_file, 'w') as file:
    for line in lines:
        if not line.startswith("IPV6ADDR") and not line.startswith("IPV6_DEFAULTGW") and not line.startswith(
                "IPV6INIT"):
            file.write(line)

    file.write("IPV6INIT=yes\n")
    file.write("IPV6ADDR={}/{}\n".format(args.ipv6_address, args.prefix_length))
    if args.gateway:
        file.write("IPV6_DEFAULTGW={}\n".format(args.gateway))

# run_command(["systemctl", "restart", "network"])
if os.path.exists("/usr/bin/nmcli"):
    run_command(["nmcli", "connection", "load", config_file])
    run_command(["nmcli", "connection", "up", args.interface])
else:
    run_command(["ifdown", args.interface])
    run_command(["ifup", args.interface])
print("IPv6 configuration updated and {} interface reloaded.".format(args.interface))
