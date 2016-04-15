package v1

const (
	// Path variable names
	PvnName      = "name"
	PvnReference = "reference"
	PvnDigest    = "digest"
	PvnUuid      = "uuid"
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

	// GET - download image blob.
	RouteNameBlob = "/v1/{name}/blobs/{digest}"

	// POST - to get an upload ID (uuid).
	RouteNameUpload = "/v1/{name}/blob-upload/"

	// GET - get upload progress.
	// PATCH - chunked upload.
	// DELETE - cancel upload.
	RouteNameUploadChunk = "/v1/{name}/blobs/uploads/{uuid}"
)
