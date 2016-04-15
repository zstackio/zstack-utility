package handlers

import (
	"github.com/docker/distribution/context"
	"github.com/docker/distribution/registry/storage/driver"
	"image-store/registry/api/errcode"
	"image-store/registry/api/v1"
	"image-store/registry/storage"
	"image-store/router"
	"net/http"
)

const ctxKeyAppDriver = "app.driver"

func GetStorageDriver(ctx context.Context) driver.StorageDriver {
	var d driver.StorageDriver

	if di := ctx.Value(ctxKeyAppDriver); di != nil {
		if value, ok := di.(driver.StorageDriver); ok {
			d = value
		}
	}

	return d
}

func WithStorageDriver(ctx context.Context, d driver.StorageDriver) context.Context {
	return context.WithValue(ctx, ctxKeyAppDriver, d)
}

func getImageSearcher(ctx context.Context, w http.ResponseWriter) *storage.ImageSearcher {
	if d := GetStorageDriver(ctx); d != nil {
		return storage.NewSearcher(d)
	} else {
		WriteHttpError(w, &errcode.ENoStorageDriver, http.StatusInternalServerError)
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
