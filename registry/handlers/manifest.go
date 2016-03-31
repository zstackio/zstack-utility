package handlers

import (
	"fmt"
	"net/http"
)

// GET  /v2/<name>/manifests/{reference}
// HEAD /v2/<name>/manifests/{reference}
// PUT  /v2/<name>/manifests/{reference}
func HandleManifest(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "handle manifest")
	return
}
