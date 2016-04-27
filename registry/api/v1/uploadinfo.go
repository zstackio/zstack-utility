package v1

import "encoding/json"

// The information needed to prepare uploading image blob.
//
// The image blobs are arranged as a hash list:
//  c.f. https://en.wikipedia.org/wiki/Hash_list
//
// The top hash (sha256 digest) represents the hash of whole blob contents.
// The chunks contains the sha1 digest for its chunk blobs, in order.
//
// Top-Hash = sha256(Chunk[0] + chunk[1] + ... + chunk[n])
// The top hash is used to identify the whole image blob.
type UploadInfo struct {
	Size int64 `json:"size"` // total size
}

// Check whether an upload information is acceptable
func (ui *UploadInfo) Ok() bool {
	// TODO set a limit for the maximum size and number
	return ui.Size > 0
}

// Marshal the upload info into a string
func (ui *UploadInfo) String() string {
	buf, _ := json.Marshal(ui)
	return string(buf)
}

// To download an image blob, we first need to acquire its download info.
type DownloadInfo struct {
	Size   int64    `json:"size"`   // total size
	Chunks []string `json:"chunks"` // hash of chunks
}
