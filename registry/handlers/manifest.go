package handlers

import (
	"fmt"
	"github.com/docker/distribution/context"
	"net/http"
)

// GET  /v2/<name>/manifests/{reference}
// HEAD /v2/<name>/manifests/{reference}
// PUT  /v2/<name>/manifests/{reference}
func HandleManifest(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "handle manifest")
	return
}
