package handlers

import (
	"crypto/tls"
	"github.com/docker/libtrust"
	//"github.com/gorilla/context"
	"github.com/gorilla/mux"
	"net"
	"net/http"

	storagedriver "github.com/docker/distribution/registry/storage/driver"
	"image-store/config"
	"image-store/registry/api/v1"
	"image-store/registry/storage/driver/factory"
	"image-store/utils"
)

type App struct {
	config *config.Configuration

	router *mux.Router
	driver storagedriver.StorageDriver
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

func NewApp(config *config.Configuration) (*App, error) {
	app := &App{
		config: config,
		router: buildRouter(),
	}

	// Get storage parameters.
	storageParams, err := config.Storage.Parameters()
	if err != nil {
		return nil, err
	}

	typ, _ := config.Storage.Type()
	app.driver, err = factory.Create(typ, storageParams)
	if err != nil {
		return nil, err
	}

	return app, nil
}

func (this *App) Run() error {
	tlscfg := this.config.TLS

	// load the server private key
	serverKey, err := libtrust.LoadKeyFile(tlscfg.PrivateKey)
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
	trustedClients, err := libtrust.LoadKeySetFile(tlscfg.TrustedClient)
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
		Addr:    this.config.HTTP.Addr,
		Handler: this.router,
	}

	// Listen and server HTTPS using the libtrust TLS config.
	listener, err := net.Listen("tcp", server.Addr)
	if err != nil {
		return err
	}

	tlsListener := tls.NewListener(listener, tlsConfig)
	server.Serve(tlsListener)

	return nil
}
