package handlers

import (
	"errors"
	"github.com/docker/distribution/context"
	"image-store/registry/api/errcode"
	"net/http"
	"path"
)

// GET  /v1/{name}/blobs/{digest}
func GetBlob(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	ps, err := GetBlobPathSpec(ctx, w, r)
	if err != nil {
		WriteHttpError(w, err, http.StatusBadRequest)
		return
	}

	d := GetStorageDriver(ctx)
	if err != nil {
		WriteHttpError(w, errcode.NoStorageDriverError{}, http.StatusInternalServerError)
		return
	}

	if d.Name() != "filesystem" {
		WriteHttpError(w, errcode.NotSupportedError{Op: "getblob"}, http.StatusInternalServerError)
		return
	}

	cfg := GetGlobalConfig(ctx)
	if cfg == nil {
		WriteHttpError(w, errors.New("missing configuration"), http.StatusInternalServerError)
		return
	}

	v := cfg.Storage["filesystem"]["rootdirectory"]
	if rootdir, ok := v.(string); ok {
		http.ServeFile(w, r, path.Join(rootdir, ps))
		return
	}

	WriteHttpError(w, errors.New("invalid configuration"), http.StatusInternalServerError)
}
