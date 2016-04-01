package main

import (
	"encoding/pem"
	"flag"
	"fmt"
	"io/ioutil"
	"log"
	"os"

	"github.com/docker/libtrust"
)

var (
	clientPrivateKeyFilename = "client_data/private_key.pem"
	trustedHostsFilename     = "client_data/trusted_hosts.pem"
)

var (
	fhost = flag.String("host", "localhost", "the trusted host name")
	fkey  = flag.String("key", "key.pem", "client private key")
	fcert = flag.String("cert", "cert.pem", "client certificate")
	fca   = flag.String("ca", "ca.pem", "the CA authority")
)

func parseArgs() {
	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: gencert <flags>\n")
		flag.PrintDefaults()
	}

	flag.Parse()
}

func writeFile(filename string, data []byte) {
	if err := ioutil.WriteFile(filename, data, 0640); err != nil {
		log.Fatal(err)
	}
}

func main() {
	parseArgs()

	key, err := libtrust.LoadKeyFile(clientPrivateKeyFilename)
	if err != nil {
		log.Fatal(err)
	}

	keyPEMBlock, err := key.PEMBlock()
	if err != nil {
		log.Fatal(err)
	}

	// Here we reset the headers to a nil map, in order not
	// to export optional PEM headers.
	keyPEMBlock.Headers = nil

	encodedPrivKey := pem.EncodeToMemory(keyPEMBlock)
	writeFile(*fkey, encodedPrivKey)

	cert, err := libtrust.GenerateSelfSignedClientCert(key)
	if err != nil {
		log.Fatal(err)
	}

	encodedCert := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: cert.Raw})
	writeFile(*fcert, encodedCert)

	trustedServerKeys, err := libtrust.LoadKeySetFile(trustedHostsFilename)
	if err != nil {
		log.Fatal(err)
	}

	trustedServerKeys, err = libtrust.FilterByHosts(trustedServerKeys, *fhost, false)
	if err != nil || len(trustedServerKeys) == 0 {
		log.Fatal(err)
	}

	caCert, err := libtrust.GenerateCACert(key, trustedServerKeys[0])
	if err != nil {
		log.Fatal(err)
	}

	encodedCert = pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caCert.Raw})
	writeFile(*fca, encodedCert)
}
