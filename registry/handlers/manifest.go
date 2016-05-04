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

// PUT  /v1/<name>/manifests/{tag}
// body: Image Manifest in JSON
func PutManifest(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	name, tag, s := GetManifestArgAndSfe(ctx, w, r)
	if s == nil {
		return
	}

	var imf v1.ImageManifest

	if err := utils.JsonDecode(r.Body, &imf); err != nil {
		e2 := errcode.BuildBadRequest("unexpected JSON body", err)
		WriteHttpError(w, e2, http.StatusBadRequest)
		return
	}

	id := imf.GenImageId()
	if imf.Id == "" {
		imf.Id = id
	}

	if !imf.Ok() {
		WriteHttpError(w, errcode.BuildEInvalidParam("manifest", "unexpected field"), http.StatusBadRequest)
		return
	}

	if err := s.PutManifest(ctx, name, tag, &imf); err != nil {
		WriteHttpError(w, err, http.StatusBadRequest)
		return
	}

	w.WriteHeader(http.StatusAccepted)
}
