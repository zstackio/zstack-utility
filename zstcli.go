// This is the command line client tool for Zstack Image Store.
//
// usage:
//  zstcli [ -url localhost:8000 ] [ command ]
//
// command:
//  pull name[:tag]
//  push id[:tag]
//  search name
//  images

package main

import (
	"fmt"
	"io/ioutil"
	"log"
	"os"

	"image-store/client"
)

var (
	privateKeyFilename   = "client_data/private_key.pem"
	trustedHostsFilename = "client_data/trusted_hosts.pem"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Println("usage:", os.Args[0], "server-addr")
		return
	}

	serverAddress := os.Args[1]

	cln, err := client.New(privateKeyFilename, trustedHostsFilename, serverAddress)
	if err != nil {
		fmt.Println(err)
		return
	}

	var makeRequest = func(url string) {
		resp, err := cln.Get(url)
		if err != nil {
			log.Fatal(err)
		}
		defer resp.Body.Close()

		body, err := ioutil.ReadAll(resp.Body)
		if err != nil {
			log.Fatal(err)
		}

		log.Println(resp.Status)
		log.Println(string(body))
	}

	// Make the request to the trusted server!
	makeRequest("v1")
}
