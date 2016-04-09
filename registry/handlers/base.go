package handlers

import (
	"encoding/json"
	"fmt"
	"github.com/docker/distribution/context"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/router"
	"net/http"
)

const emptyJSON = "{}"

// GET /v1/
func HandleVersion(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	fmt.Fprintln(w, emptyJSON)
	return
}

// GET /v1/{name}
func HandleList(ctx context.Context, w http.ResponseWriter, r *http.Request) {
	name := "/" + router.GetRequestVar(r, v1.PvnName)

	d := GetStorageDriver(ctx)
	if d == nil {
		WriteHttpError(w, &errcode.ENoStorageDriver)
		return
	}

	res, err := d.List(ctx, name)
	if err != nil {
		WriteHttpError(w, errcode.BuildENotFound(name, err))
		return
	}

	if err := json.NewEncoder(w).Encode(res); err != nil {
		panic(err)
	}

	return
}
