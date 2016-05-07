package handlers

import (
	"fmt"
	"github.com/docker/distribution/context"
	"net/http"
)

const emptyJSON = "{}"

// GET /v1/
func HandleVersion(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json; charset=UTF-8")
	fmt.Fprintln(w, emptyJSON)
	return
}

// GET /v1/{name} - list images by name
func HandleNameList(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	name, s := GetNameAndSfe(ctx, w, r)
	if s == nil {
		return
	}

	res, err := s.FindImages(ctx, name)
	NewHttpResult(res, err).WriteResponse(w)
}

// GET /v1/{name}/tags/ - list tags by name
func HandleTagList(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	name, s := GetNameAndSfe(ctx, w, r)
	if s == nil {
		return
	}

	res, err := s.ListTags(ctx, name)
	NewHttpResult(res, err).WriteResponse(w)
}
