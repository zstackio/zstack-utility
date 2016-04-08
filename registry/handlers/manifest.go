package handlers

import (
	"fmt"
	"golang.org/x/net/context"
	"net/http"
)

// GET  /v2/<name>/manifests/{reference}
// HEAD /v2/<name>/manifests/{reference}
// PUT  /v2/<name>/manifests/{reference}
func HandleManifest(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "handle manifest")
	return
}
