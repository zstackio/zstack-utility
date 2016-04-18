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

func getImageSearcher(ctx context.Context, w http.ResponseWriter) *storage.ImageSearcher {
	if d := GetStorageDriver(ctx); d != nil {
		return storage.NewSearcher(d)
	} else {
		WriteHttpError(w, errcode.NoStorageDriverError{}, http.StatusInternalServerError)
		return nil
	}
}

func GetNameAndSearcher(ctx context.Context, w http.ResponseWriter, r *http.Request) (n string, s *storage.ImageSearcher) {
	n = router.GetRequestVar(r, v1.PvnName)
	s = getImageSearcher(ctx, w)
	return
}

func GetManifestArgAndSearcher(ctx context.Context, w http.ResponseWriter, r *http.Request) (n string, ref string, s *storage.ImageSearcher) {
	n = router.GetRequestVar(r, v1.PvnName)
	ref = router.GetRequestVar(r, v1.PvnReference)
	s = getImageSearcher(ctx, w)
	return
}

// Get upload information and the name
func GetUploadInfoAndSearcher(ctx context.Context, w http.ResponseWriter, r *http.Request) (n string, info *storage.UploadInfo, s *storage.ImageSearcher) {
	n = router.GetRequestVar(r, v1.PvnName)

	var ui storage.UploadInfo
	if err := DecodeRequest(r, &ui); err != nil {
		fmt.Println(err)
		return
	}

	if !utils.IsBlobDigest(ui.Digest) {
		return
	}

	info = &ui
	s = getImageSearcher(ctx, w)
	return
}

func GetBlobPathSpec(ctx context.Context, w http.ResponseWriter, r *http.Request) (string, error) {
	n := router.GetRequestVar(r, v1.PvnName)
	d := router.GetRequestVar(r, v1.PvnDigest)
	s := getImageSearcher(ctx, w)
	if s == nil {
		return "", fmt.Errorf("failed to build image searcher for blob digest: %s", d)
	}

	return s.GetBlobPathSpec(n, d)
}
