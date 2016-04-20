package v1

import (
	"image-store/utils"
)

// The information needed to prepare uploading image blob.
type UploadInfo struct {
	Digest string `json:"digest"`
}

// Check whether an upload information is acceptable
func (ui *UploadInfo) Ok() bool {
	if !utils.IsBlobDigest(ui.Digest) {
		return false
	}

	return true
}
