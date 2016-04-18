package handlers

import (
	"errors"
	"fmt"
	"github.com/docker/distribution/context"
	"image-store/registry/api/errcode"
	"net/http"
)

// POST /v1/{name}/blob-upload/
// {
//   "digest": "...",
// }
//
// Returns HTTP Accepted, with a Location header to be PATCH with.
func PrepareBlobUpload(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	n, info, s := GetUploadInfoAndSearcher(ctx, w, r)
	if info == nil {
		WriteHttpError(w, errors.New("invalid digest"), http.StatusBadRequest)
		return
	}

	if s == nil {
		return
	}

	loc, err := s.PrepareBlobUpload(ctx, n, info)
	if err != nil {
		switch err.(type) {
		case errcode.ConflictError, *errcode.ConflictError:
			WriteHttpError(w, err, http.StatusConflict)
		default:
			WriteHttpError(w, err, http.StatusBadRequest)
		}

		return
	}

	w.Header().Set("Location", loc)
	w.WriteHeader(http.StatusAccepted)
}

// GET    /v1/{name}/blobs/uploads/{uuid}
// PATCH  /v1/{name}/blobs/uploads/{uuid}
// DELETE /v1/{name}/blobs/uploads/{uuid}
func HandleUploadEntity(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "handle upload entity")
	return
}
