package main

import (
	"flag"
	"fmt"
	"log"
	"os"

	"image-store/config"
	"image-store/registry/handlers"
)

var fconf = flag.String("conf", "zstore.yaml", "zstore configure file")
var fpriv = flag.String("key", "privkey.pem", "server private key file")
var ftrusted = flag.String("trusted", "trusted.pem", "libtrust trusted clients")
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
	err := handlers.NewApp(c).Run(*fpriv, *ftrusted)
	if err != nil {
		log.Fatal(err)
	}
}
