package client

import (
	"path"
)

const (
	rootDir = "/tmp/zstore/registry/v1"
)

func GetImageBlobPath(name string, digest string) string {
	return path.Join(rootDir, "blobs", digest)
}
