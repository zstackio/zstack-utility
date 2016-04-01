package utils

import "net"

func ListIPs() (ips []net.IP, err error) {
	addrs, err := net.InterfaceAddrs()

	if err != nil {
		return
	}

	for _, addr := range addrs {
		var ip net.IP
		switch v := addr.(type) {
		case *net.IPNet:
			ip = v.IP
		case *net.IPAddr:
			ip = v.IP
		}

		if ip.To4() != nil {
			ips = append(ips, ip)
		}
	}

	return
}

func ListIPStrings() (strs []string, err error) {
	ips, err := ListIPs()
	if err != nil {
		return
	}

	for _, ip := range ips {
		strs = append(strs, ip.String())
	}

	return
}
