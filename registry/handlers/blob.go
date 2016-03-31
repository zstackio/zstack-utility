package handlers

import (
	"fmt"
	"net/http"
)

// GET  /v2/{name}/blobs/{digest}
// HEAD /v2/{name}/blobs/{digest}
func HandleBlob(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "handle blob")
	return
}
