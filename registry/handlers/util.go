package handlers

import (
	"github.com/docker/distribution/context"
	"github.com/docker/distribution/registry/storage/driver"
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
