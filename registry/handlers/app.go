package handlers

import (
	"github.com/gorilla/mux"
	"net/http"

	"image-store/config"
	"image-store/registry/api/v1"
	"image-store/registry/storage/driver"
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

func (this *App) Run() error {
	http.ListenAndServe(":8000", this.router)
	return nil
}
