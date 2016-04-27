package handlers

import (
	"fmt"
	"github.com/docker/distribution/context"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"net/http"
	"strings"
)

const emptyJSON = "{}"

// GET /v1/
func HandleVersion(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json; charset=UTF-8")
	fmt.Fprintln(w, emptyJSON)
	return
}

// TODO implement image search
func getNameTag(key string) (name string, tag string, err *errcode.Error) {
	ary := strings.Split(key, ":")

	switch len(ary) {
	default:
		err = errcode.BuildEInvalidParam(v1.PvnName, "unexpected format")
	case 1:
		name, tag = ary[0], "latest"
	case 2:
		name, tag = ary[0], ary[1]
	}

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
