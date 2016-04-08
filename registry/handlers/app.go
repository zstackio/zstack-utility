package handlers

import (
	"crypto/tls"
	"github.com/docker/libtrust"
	"github.com/gorilla/mux"
	"net"
	"net/http"

	storagedriver "github.com/docker/distribution/registry/storage/driver"
	"golang.org/x/net/context"
	"image-store/config"
	"image-store/registry/api/v1"
	"image-store/registry/storage/driver/factory"
	"image-store/utils"
)

type App struct {
	rctx   context.Context // the root context
	Config *config.Configuration

	router *mux.Router
	driver storagedriver.StorageDriver
}

func NewApp(config *config.Configuration) (*App, error) {
	app := &App{
		rctx:   context.Background(),
		Config: config,
		router: v1.NewRouter(),
	}

	// Build the handlers
	app.register(v1.RouteNameV1, HandleVersion)
	app.register(v1.RouteNameList, HandleList)
	app.register(v1.RouteNameManifest, HandleManifest)
	app.register(v1.RouteNameBlob, HandleBlob)
	app.register(v1.RouteNameUpload, HandleBlobUpload)
	app.register(v1.RouteNameUploadChunk, HandleUploadEntity)

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

func (app *App) Run() error {
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
		Addr:    app.Config.HTTP.Addr,
		Handler: app.router,
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

func (app *App) register(routeName string, f ContextHandlerFunc) {
	c := context.WithValue(app.rctx, ContextKeyAppDriver, app.driver)
	h := ContextAdapter{ctx: c, handler: f}
	app.router.Handle(routeName, h)
}
