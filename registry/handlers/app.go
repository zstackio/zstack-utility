package handlers

import (
	"crypto/tls"
	"github.com/docker/libtrust"
	"log"
	"net"
	"net/http"

	"github.com/docker/distribution/context"
	storagedriver "github.com/docker/distribution/registry/storage/driver"
	"image-store/config"
	"image-store/registry/api/v1"
	"image-store/registry/storage/driver/factory"
	"image-store/router"
	"image-store/utils"
)

type App struct {
	rctx   context.Context // the root context
	Config *config.Configuration

	router *router.Router
	driver storagedriver.StorageDriver
}

func NewApp(config *config.Configuration) (*App, error) {
	app := &App{
		rctx:   context.Background(),
		Config: config,
		router: router.NewRouter(),
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

	// Build the handlers
	app.register(v1.RouteNameV1, HandleVersion).Methods("GET")
	app.register(v1.RouteNameList, HandleNameList).Methods("GET")
	app.register(v1.RouteNameTagList, HandleTagList).Methods("GET")

	app.register(v1.RouteNameManifest, GetManifest).Methods("GET")
	app.register(v1.RouteNameManifest, EnforceContentLength(PutManifest)).Methods("PUT")

	app.register(v1.RouteNameBlob, GetBlob).Methods("GET")
	app.register(v1.RouteNameUpload, EnforceContentLength(PrepareBlobUpload)).Methods("POST")

	app.register(v1.RouteNameUploadChunk, GetUploadProgress).Methods("GET")
	app.register(v1.RouteNameUploadChunk, UploadBlobChunk).Methods("PATCH")
	app.register(v1.RouteNameUploadChunk, CompleteUpload).Methods("PUT")
	app.register(v1.RouteNameUploadChunk, CancelUpload).Methods("DELETE")

	return app, nil
}

func (app *App) Run(logger *log.Logger) error {
	tlscfg := app.Config.TLS

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
		Addr:     app.Config.HTTP.Addr,
		Handler:  app.router,
		ErrorLog: logger,
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

func (app *App) register(routeName string, f ContextHandlerFunc) *router.Route {
	c1 := WithStorageDriver(app.rctx, app.driver)
	c2 := WithGlobalConfig(c1, app.Config)
	h := ContextAdapter{ctx: c2, handler: f}

	return app.router.Handle(routeName, h)
}
