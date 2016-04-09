package handlers

import (
	"fmt"
	"github.com/docker/distribution/context"
	"net/http"
)

const emptyJSON = "{}"

// GET /v1/
func HandleVersion(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Length", fmt.Sprint(len(emptyJSON)))

	fmt.Fprint(w, emptyJSON)
	return
}

// GET /v1/{name}
func HandleList(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "search name")
	return
}
