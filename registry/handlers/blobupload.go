package handlers

import (
	"fmt"
	"github.com/docker/distribution/context"
	"net/http"
)

// POST /v1/{name}/blobs/uploads/
func HandleBlobUpload(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "handle upload")
	return
}

// GET    /v1/{name}/blobs/uploads/{uuid}
// PATCH  /v1/{name}/blobs/uploads/{uuid}
// PUT    /v1/{name}/blobs/uploads/{uuid}
// DELETE /v1/{name}/blobs/uploads/{uuid}
func HandleUploadEntity(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "handle upload entity")
	return
}
