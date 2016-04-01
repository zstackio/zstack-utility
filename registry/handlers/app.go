package handlers

import (
	"crypto/tls"
	"github.com/docker/libtrust"
	"github.com/gorilla/mux"
	"net"
	"net/http"

	"image-store/config"
	"image-store/registry/api/v1"
	"image-store/registry/storage/driver"
	"image-store/utils"
)

type App struct {
	Config *config.Configuration

	router *mux.Router
	driver driver.StorageDriver
}

func createDriverInstance() driver.StorageDriver {
	// TODO: sth. like factory.Create(...)
	s := driver.StorageDriver{}
	return s
}

func buildRouter() *mux.Router {
	r := v1.NewRouter()

	r.HandleFunc(v1.RouteNameV1, HandleVersion).Methods("GET")
	r.HandleFunc(v1.RouteNameList, HandleList).Methods("GET")
	r.HandleFunc(v1.RouteNameManifest, HandleManifest)
	r.HandleFunc(v1.RouteNameBlob, HandleBlob)
	r.HandleFunc(v1.RouteNameUpload, HandleBlobUpload).Methods("POST")
	r.HandleFunc(v1.RouteNameUploadChunk, HandleUploadEntity)

	return r
}

func NewApp(config *config.Configuration) *App {
	app := &App{
		Config: config,
		router: buildRouter(),
		driver: createDriverInstance(),
	}

	return app
}

func (this *App) Run(privKeyFile string, trustedClientsFile string) error {
	// load the server private key
	serverKey, err := libtrust.LoadKeyFile(privKeyFile)
	if err != nil {
		return err
	}

	ips, err := utils.ListIPs()
	if err != nil {
		return err
	}

	// generate a self-signed server for the server
	selfSignedCert, err := libtrust.GenerateSelfSignedServerCert(
		serverKey, []string{"localhost"}, ips)
	if err != nil {
		return err
	}

	// load trusted clients
	trustedClients, err := libtrust.LoadKeySetFile(trustedClientsFile)
	if err != nil {
		return err
	}

	// create CA pool using trusted client keys.
	caPool, err := libtrust.GenerateCACertPool(serverKey, trustedClients)
	if err != nil {
		return err
	}

	// create the TLS config, require client cert authentication
	tlsConfig := &tls.Config{
		Certificates: []tls.Certificate{
			tls.Certificate{
				Certificate: [][]byte{selfSignedCert.Raw},
				PrivateKey:  serverKey.CryptoPrivateKey(),
				Leaf:        selfSignedCert,
			},
		},
		ClientAuth: tls.RequireAndVerifyClientCert,
		ClientCAs:  caPool,
	}

	// create the HTTP server
	server := &http.Server{
		Addr:    ":8000",
		Handler: this.router,
	}

	// Listen and server HTTPS using the libtrust TLS config.
	listener, err := net.Listen("tcp", server.Addr)
	if err != nil {
		return err
	}

	tlsListener := tls.NewListener(listener, tlsConfig)
	server.Serve(tlsListener)
	//http.ListenAndServe(":8000", this.router)
	return nil
}
