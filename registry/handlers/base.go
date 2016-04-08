package handlers

import (
	"fmt"
	"golang.org/x/net/context"
	"net/http"
)

// GET /v1/
func HandleVersion(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "base")
	return
}

// GET /v1/{name}
func HandleList(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "search name")
	return
}
