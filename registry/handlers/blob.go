package handlers

import (
	"fmt"
	"github.com/docker/distribution/context"
	"image-store/registry/api/errcode"
	"io"
	"net/http"
)

// GET  /v1/{name}/blobs/{digest}
func GetBlobJson(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	ps, err := GetBlobJsonSpec(ctx, w, r)
	if err != nil {
		WriteHttpError(w, err, http.StatusBadRequest)
		return
	}

	d := GetStorageDriver(ctx)
	if err != nil {
		WriteHttpError(w, errcode.NoStorageDriverError{}, http.StatusInternalServerError)
		return
	}

	content, err := d.GetContent(ctx, ps)
	if err != nil {
		WriteHttpError(w, err, http.StatusBadRequest)
		return
	}

	w.Header().Set("Content-Type", "application/json; charset=UTF-8")
	fmt.Fprint(w, string(content))
}

// GET /v1/{name}/blobs/{digest}/chunks/{hash}
func GetBlobChunk(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	reader, err := GetBlobChunkReader(ctx, w, r)
	if err != nil {
		WriteHttpError(w, err, http.StatusBadRequest)
		return
	}

	defer reader.Close()

	w.Header().Set("Content-Type", "application/octet-stream")
	io.Copy(w, reader)
}
