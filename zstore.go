package main

import (
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"os"
	"path"

	"image-store/config"
	"image-store/registry/handlers"
)

var (
	// Command line flags
	fconf = flag.String("conf", "zstore.yaml", "zstore configure file")
	flogf = flag.String("logfile", "error.log", "error log file")

	// The program name
	progname = path.Base(os.Args[0])
)

func parseArgs() {
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: %s [OPTION]\n", progname)
		flag.PrintDefaults()
	}

	flag.Parse()
}

func main() {
	parseArgs()

	f, err := os.OpenFile(*flogf, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		fmt.Fprintln(os.Stderr, "failed to open log file:", err)
		return
	}

	defer f.Close()

	dat, err := ioutil.ReadFile(*fconf)
	if err != nil {
		fmt.Fprintln(os.Stderr, "failed to open configure file:", err)
		return
	}

	cfg, err := config.Parse(dat)
	if err != nil {
		fmt.Fprintln(os.Stderr, "failed to parse configure file:", err)
		return
	}

	app, err := handlers.NewApp(cfg)
	if err != nil {
		fmt.Fprintln(os.Stderr, "failed to create server instance:", err)
		return
	}

	logger := log.New(f, "", log.LstdFlags|log.Lmicroseconds)
	err = app.Run(logger)
	if err != nil {
		fmt.Fprintln(os.Stderr, "server aborted:", err)
		return
	}
}
