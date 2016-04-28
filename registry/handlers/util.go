package handlers

import (
	"fmt"
	"github.com/docker/distribution/context"
	"github.com/docker/distribution/registry/storage/driver"
	"image-store/config"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/registry/storage"
	"image-store/router"
	"image-store/utils"
	"io"
	"net/http"
)

const (
	ctxKeyAppDriver = "app.driver"
	ctxKeyGlobalCfg = "app.cfg"
)

func GetStorageDriver(ctx context.Context) driver.StorageDriver {
	var d driver.StorageDriver

	if di := ctx.Value(ctxKeyAppDriver); di != nil {
		if value, ok := di.(driver.StorageDriver); ok {
			d = value
		}
	}

	return d
}

func GetGlobalConfig(ctx context.Context) *config.Configuration {
	if ci := ctx.Value(ctxKeyGlobalCfg); ci != nil {
		if value, ok := ci.(*config.Configuration); ok {
			return value
		}
	}

	return nil
}

func WithStorageDriver(ctx context.Context, d driver.StorageDriver) context.Context {
	return context.WithValue(ctx, ctxKeyAppDriver, d)
}

func WithGlobalConfig(ctx context.Context, c *config.Configuration) context.Context {
	return context.WithValue(ctx, ctxKeyGlobalCfg, c)
}

func getStorageFE(ctx context.Context, w http.ResponseWriter) storage.IStorageFE {
	if d := GetStorageDriver(ctx); d != nil {
		return storage.NewStorageFrontend(d)
	} else {
		WriteHttpError(w, errcode.NoStorageDriverError{}, http.StatusInternalServerError)
		return nil
	}
}

func GetNameAndSfe(ctx context.Context, w http.ResponseWriter, r *http.Request) (n string, s storage.IStorageFE) {
	n = router.GetRequestVar(r, v1.PvnName)
	s = getStorageFE(ctx, w)
	return
}

func GetManifestArgAndSfe(ctx context.Context, w http.ResponseWriter, r *http.Request) (n string, ref string, s storage.IStorageFE) {
	n = router.GetRequestVar(r, v1.PvnName)
	ref = router.GetRequestVar(r, v1.PvnReference)
	s = getStorageFE(ctx, w)
	return
}

// Get upload information and the name
func GetUploadInfoAndSfe(ctx context.Context, w http.ResponseWriter, r *http.Request) (n string, info *v1.UploadInfo, s storage.IStorageFE) {
	n = router.GetRequestVar(r, v1.PvnName)

	var ui v1.UploadInfo
	if err := utils.JsonDecode(r.Body, &ui); err != nil {
		fmt.Println(err)
		return
	}

	if !ui.Ok() {
		return
	}

	info = &ui
	s = getStorageFE(ctx, w)
	return
}

func GetBlobJsonSpec(ctx context.Context, w http.ResponseWriter, r *http.Request) (string, error) {
	n := router.GetRequestVar(r, v1.PvnName)
	d := router.GetRequestVar(r, v1.PvnDigest)
	s := getStorageFE(ctx, w)
	if s == nil {
		return "", fmt.Errorf("failed to build storage frontend searcher for blob digest: %s", d)
	}

	return s.GetBlobJsonSpec(n, d)
}

func GetBlobChunkReader(ctx context.Context, w http.ResponseWriter, r *http.Request) (io.ReadCloser, error) {
	n := router.GetRequestVar(r, v1.PvnName)
	d := router.GetRequestVar(r, v1.PvnDigest)
	h := router.GetRequestVar(r, v1.PvnHash)
	s := getStorageFE(ctx, w)
	if s == nil {
		return nil, fmt.Errorf("failed to build storage frontend searcher for blob digest: %s", d)
	}

	// TODO range read
	// In order to compute the chunk digest w/o reading partial chunks,
	// we can't continue from the point of interruption.
	return s.GetBlobChunkReader(ctx, n, d, h, 0)
}

func GetUploadQueryArgAndSfe(ctx context.Context, w http.ResponseWriter, r *http.Request) (n string, uu string, s storage.IStorageFE) {
	n = router.GetRequestVar(r, v1.PvnName)
	uu = router.GetRequestVar(r, v1.PvnUuid)
	s = getStorageFE(ctx, w)
	return
}
