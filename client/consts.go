package client

import (
	"path"
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
