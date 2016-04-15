package router

import (
	"github.com/gorilla/mux"
	"net/http"
)

// Router is a copy of Router from "github.com/gorilla/mux"
type Router struct {
	*mux.Router
}

type Route struct {
	*mux.Route
}

func NewRouter() *Router {
	router := mux.NewRouter()
	router.StrictSlash(true)
	return &Router{router}
}

func (r *Router) Handle(path string, handler http.Handler) *Route {
	route := r.Router.Handle(path, handler)
	return &Route{route}
}

func GetRequestVars(r *http.Request) map[string]string {
	return mux.Vars(r)
}

func GetRequestVar(r *http.Request, key string) string {
	vars := GetRequestVars(r)

	if vars != nil {
		return vars[key]
	}

	return ""
}
