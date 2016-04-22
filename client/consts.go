package client

import (
	"path"
	"strings"
)

const (
	rootDir              = "/tmp/zstore-local/registry/v1"
	defaultServer        = "localhost:8000"
	privateKeyFilename   = "client_data/private_key.pem"
	trustedHostsFilename = "client_data/trusted_hosts.pem"
)

func GetImageBlobPath(name string, digest string) string {
	return path.Join(rootDir, "blobs", digest)
}

func GetImageManifestPath(name string, imgid string) string {
	fname := imgid + ".json"
	return path.Join(rootDir, "repos", name, "manifests", "revisions", fname)
}

func GetImageFilePath(name string, imgid string) string {
	fname := GetImageManifestPath(name, imgid)
	return strings.TrimSuffix(fname, ".json") + ".qcow2"
}
