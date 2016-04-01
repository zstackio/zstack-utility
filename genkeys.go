package main

import (
	"log"
	"os"

	"github.com/docker/libtrust"
	"image-store/utils"
)

func addExtendedFields(serverKey libtrust.PrivateKey) {
	host, err := os.Hostname()
	if err != nil {
		log.Fatal(err)
	}

	// initialize the hosts list
	hosts := []string{"localhost", host}

	ips, err := utils.ListIPStrings()
	if err != nil {
		log.Fatal(err)
	}

	// Set the list of addresses to use for the server.
	hosts = append(hosts, ips...)
	serverKey.AddExtendedField("hosts", hosts)
}

func main() {
	// Generate client key.
	clientKey, err := libtrust.GenerateECP384PrivateKey()
	if err != nil {
		log.Fatal(err)
	}

	for _, d := range []string{"client_data", "server_data"} {
		os.Mkdir(d, 0755)
	}

	// Add a comment for the client key.
	clientKey.AddExtendedField("comment", "Trusted TLS Client")

	// Save the client key, public and private versions.
	err = libtrust.SaveKey("client_data/private_key.pem", clientKey)
	if err != nil {
		log.Fatal(err)
	}

	err = libtrust.SavePublicKey("client_data/public_key.pem", clientKey.PublicKey())
	if err != nil {
		log.Fatal(err)
	}

	// Generate server key.
	serverKey, err := libtrust.GenerateECP384PrivateKey()
	if err != nil {
		log.Fatal(err)
	}

	addExtendedFields(serverKey)

	// Save the server key, public and private versions.
	err = libtrust.SaveKey("server_data/private_key.pem", serverKey)
	if err != nil {
		log.Fatal(err)
	}

	err = libtrust.SavePublicKey("server_data/public_key.pem", serverKey.PublicKey())
	if err != nil {
		log.Fatal(err)
	}

	// Generate Authorized Keys file for server.
	err = libtrust.AddKeySetFile("server_data/trusted_clients.pem", clientKey.PublicKey())
	if err != nil {
		log.Fatal(err)
	}

	// Generate Known Host Keys file for client.
	err = libtrust.AddKeySetFile("client_data/trusted_hosts.pem", serverKey.PublicKey())
	if err != nil {
		log.Fatal(err)
	}
}
