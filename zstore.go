package main

import (
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"os"

	"image-store/config"
	"image-store/registry/handlers"
)

var fconf = flag.String("conf", "zstore.yaml", "zstore configure file")

func parseArgs() {
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: licgen <flags>\n")
		flag.PrintDefaults()
	}

	flag.Parse()
}

func main() {
	parseArgs()

	dat, err := ioutil.ReadFile(*fconf)
	if err != nil {
		log.Fatal(err)
	}

	cfg, err := config.Parse(dat)
	if err != nil {
		log.Fatal(err)
	}

	app, err := handlers.NewApp(cfg)
	if err != nil {
		log.Fatal(err)
	}

	err = app.Run()
	if err != nil {
		log.Fatal(err)
	}
}
