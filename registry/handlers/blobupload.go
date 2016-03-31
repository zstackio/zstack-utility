package handlers

import (
	"fmt"
	"net/http"
)

// POST /v1/{name}/blobs/uploads/
func HandleBlobUpload(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "handle upload")
	return
}

// GET    /v1/{name}/blobs/uploads/{uuid}
// PATCH  /v1/{name}/blobs/uploads/{uuid}
// PUT    /v1/{name}/blobs/uploads/{uuid}
// DELETE /v1/{name}/blobs/uploads/{uuid}
func HandleUploadEntity(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "handle upload entity")
	return
}
