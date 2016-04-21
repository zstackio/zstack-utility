package client

import (
	"path"
)

const (
	rootDir       = "/tmp/zstore/registry/v1"
	defaultServer = "localhost:8000"
)

func GetImageBlobPath(name string, digest string) string {
	return path.Join(rootDir, "blobs", digest)
}
