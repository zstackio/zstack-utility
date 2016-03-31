package main

import (
	"flag"
	"fmt"
	"os"

	"image-store/config"
	"image-store/registry/handlers"
)

var fconf = flag.String("conf", "zstore.yaml", "zstore configure file")
var fpriv = flag.String("key", "privkey.pem", "server private key file")
var ftrusted = flag.String("trusted", "trusted.pem", "trusted clients")
var faddress = flag.String("address", "localhost:8888", "server address")

func parseArgs() {
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: licgen <flags>\n")
		flag.PrintDefaults()
	}

	flag.Parse()
}

func main() {
	parseArgs()

	c := &config.Configuration{}
	handlers.NewApp(c).Run()
}
