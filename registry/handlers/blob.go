package handlers

import (
	"fmt"
	"github.com/docker/distribution/context"
	"net/http"
)

// GET  /v2/{name}/blobs/{digest}
// HEAD /v2/{name}/blobs/{digest}
func HandleBlob(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "handle blob")
	return
}
