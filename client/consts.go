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

var ImageRepoTopDir = path.Join(rootDir, "repos")

// fs layout of disk images, manifests, working directories etc.
func GetImageBlobPath(name string, blobsum string) string {
	return path.Join(rootDir, "blobs", blobsum)
}

func GetBlobDownloadDir(name string, blobsum string) string {
	return path.Join(rootDir, "wip", name, blobsum)
}

func GetImageManifestPath(name string, imgid string) string {
	fname := imgid + ".json"
	return path.Join(ImageRepoTopDir, name, "manifests", "revisions", fname)
}

func GetImageFilePath(name string, imgid string) string {
	fname := GetImageManifestPath(name, imgid)
	return strings.TrimSuffix(fname, ".json") + ".qcow2"
}

func GetImageTagPath(name string, tag string) string {
	return path.Join(ImageRepoTopDir, name, "manifests", "tags", tag)
}
