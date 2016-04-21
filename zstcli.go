// This is the command line client tool for Zstack Image Store.
//
// usage:
//  zstcli [ -url localhost:8000 ] [ command ]
//
// command:
//  pull name[:reference]
//  push id[:tag]
//  search name
//  images

package main

import (
	"fmt"
	"os"
	"path"
	//	"io/ioutil"
	//	"log"

	"image-store/client"
)

var (
	privateKeyFilename   = "client_data/private_key.pem"
	trustedHostsFilename = "client_data/trusted_hosts.pem"
)

func main() {
	opt, err := client.ParseCmdLine()
	if err != nil {
		fmt.Println(err)
		fmt.Printf("Run '%s -h' for more information.\n", path.Base(os.Args[0]))
		return
	}

	opt.RunCmd(client.DefaultRunner)
	/*
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
	*/
}
