package v1

import (
	"path"
)

const (
	// Path variable names
	PvnName      = "name"
	PvnReference = "reference"
	PvnDigest    = "digest"
	PvnUuid      = "uuid"
	PvnHash      = "hash"

	// HTTP Header Name
	HnChunkHash  = "X-Chunk-Hash"  // sha256(chunk)
	HnChunkIndex = "X-Chunk-Index" // start from 1

	ChunkStartIndex = 1

	// The blob chunk size in byte (all chunks are of size 16 MB)
	// except the last chunk of a blob.
	BlobChunkSize = 16 * 1024 * 1024
)

const (
	// GET - check version.
	RouteNameV1 = "/v1/"

	// GET - list images by name.
	RouteNameList = "/v1/{name}"

	// GET - list tags by name.
	RouteNameTagList = "/v1/{name}/tags"

	// GET - pull manifest.
	// PUT - push manifest.
	RouteNameManifest = "/v1/{name}/manifests/{reference}"

	// GET - get image blob json.
	RouteNameBlobJson = "/v1/{name}/blobs/{digest}"

	// GET - download a chunk of an image blob
	RouteNameBlobChunk = "/v1/{name}/blobs/{digest}/chunks/{hash}"

	// POST - to get an upload ID (uuid).
	RouteNameUpload = "/v1/{name}/blob-upload/"

	// GET - get upload progress.
	// PATCH - chunked upload.
	// DELETE - cancel upload.
	RouteNameUploadChunk = "/v1/{name}/blobs/uploads/{uuid}"
)

func GetManifestRoute(name string, reference string) string {
	return path.Join(RouteNameV1, name, "manifests", reference)
}

func GetTagListRoute(name string) string {
	return path.Join(RouteNameV1, name, "tags")
}

func GetImageBlobRoute(name string, digest string) string {
	return path.Join(RouteNameV1, name, "blobs", digest)
}

func GetUploadRoute(name string) string {
	return path.Join(RouteNameV1, name, "blob-upload") + "/"
}

func GetUploadIdRoute(name string, id string) string {
	return path.Join(RouteNameV1, name, "blobs", "uploads", id)
}
