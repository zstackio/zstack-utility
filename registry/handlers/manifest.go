package handlers

import (
	"github.com/docker/distribution/context"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/utils"
	"net/http"
)

// GET  /v1/<name>/manifests/{reference}
func GetManifest(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	name, ref, s := GetManifestArgAndSfe(ctx, w, r)
	if s == nil {
		return
	}

	res, err := s.GetManifest(ctx, name, ref)
	NewHttpResult(res, err).WriteResponse(w)
}

// PUT  /v1/<name>/manifests/{refrence}
// body: Image Manifest in JSON
func PutManifest(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	name, ref, s := GetManifestArgAndSfe(ctx, w, r)
	if s == nil {
		return
	}

	var imf v1.ImageManifest

	if err := utils.JsonDecode(r.Body, &imf); err != nil {
		e2 := errcode.BuildBadRequest("unexpected body format", err)
		WriteHttpError(w, e2, http.StatusBadRequest)
		return
	}

	if err := s.PutManifest(ctx, name, ref, &imf); err != nil {
		WriteHttpError(w, err, http.StatusBadRequest)
		return
	}

	w.WriteHeader(http.StatusAccepted)
}
