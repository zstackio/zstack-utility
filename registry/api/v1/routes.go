package v1

import (
	"github.com/gorilla/mux"
	"net/http"
)

func NewRouter() *mux.Router {
	router := mux.NewRouter()
	router.StrictSlash(true)
	return router
}

func GetRequestVars(request *http.Request) map[string]string {
	return mux.Vars(request)
}
