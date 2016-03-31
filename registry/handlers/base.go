package handlers

import (
	"fmt"
	"net/http"
)

// GET /v1/
func HandleVersion(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "base")
	return
}

// GET /v1/{name}
func HandleList(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "search name")
	return
}
